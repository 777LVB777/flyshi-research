#!/usr/bin/env python3
"""Run the pre-stated synthetic-market signal sweep.

Without ``--dry-run``, job execution constructs the real Brian2 backend and runs
simulations.  Tests and dry-run never do so.  See
docs/design/synthetic-market-experiment.md.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling runners; none imports Brian2 at module level

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
# The ONE shared definition of "left", as in the fixed graded runners.
from run_left_only_pool_diagnostic import IDS_PATH, kc_side_map  # noqa: E402
# Per-trial binning shared with the diagnostics, so ignition is measured identically.
from run_left_only_realistic_drive_diagnostic import bin_spikes  # noqa: E402

RESULTS_BASE = HERE / "results"


def _write_json(path: Path, value: object) -> None:
    """Atomic and durable: the file appears under its final name only complete and on
    disk (fsync before the rename, then the directory), so a crash or power loss
    leaves either no job file or a whole one, never a truncated one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with open(temporary, "w") as fh:
        fh.write(json.dumps(value, separators=(",", ":")))
        fh.flush()
        os.fsync(fh.fileno())
    temporary.replace(path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read_output(path: Path) -> Optional[dict]:
    """The job file's content, or None if it is missing, empty or not a whole JSON
    object (e.g. truncated by a crash on a filesystem that lost the write)."""
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


class Paths:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.parts = directory / "parts"
        self.logs = directory / "logs"

    def output(self, job: sm.Job) -> Path:
        return self.parts / (job.id.replace(":", "_") + ".json")

    def log(self, job: sm.Job) -> Path:
        return self.logs / (job.id.replace(":", "_") + ".log")

    def done(self, job: sm.Job) -> bool:
        """Done means a whole, parseable job file. A damaged file counts as not done,
        so the job is re-run and its file replaced."""
        return read_output(self.output(job)) is not None


#: one line per simulation run in the job log; read by monitor_sweep.py and
#: calibrate_server.py. Format: [progress] <job> run <n>/<total> t=<unix s> maxrss_gb=<x>
PROGRESS_TAG = "[progress]"
START_TAG = "[start]"


def peak_rss_gb() -> float:
    """This process's peak resident memory (ru_maxrss: KB on Linux, bytes on macOS)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 ** 3 if sys.platform == "darwin" else 1024 ** 2)


def progress_printer(job_id: str, total_runs: int) -> Callable[[int], None]:
    def report(n: int) -> None:
        print(f"{PROGRESS_TAG} {job_id} run {n}/{total_runs} t={time.time():.2f} "
              f"maxrss_gb={peak_rss_gb():.3f}", flush=True)
    return report


def build_sweep_simulator(progress: Optional[Callable[[int], None]] = None):
    """The real backend plus per-trial readout (decided 2026-10-09).

    Wraps the population simulator (a ``FastRunnerSimulator`` that also indexes APL)
    and adds ``present_trials``: one ``run_cue_rates`` call, binned by trial with the
    diagnostics' ``bin_spikes``. Its trial means equal ``FastRunnerSimulator.present``
    exactly, so scores and eligibility are unchanged by the tracking. Imports Brian2.
    ``progress(n)`` is called after the n-th run; it only reports, never alters a run.
    """
    import numpy as np
    from run_population_scaling_diagnostic import _build_population_simulator

    sim = _build_population_simulator()
    apl_index = sim.population_index["apl_neurons"]

    def present_trials(rates_by_kc_id, seed, duration_ms, n_trials):
        sim.bundle["params"]["t_run"] = duration_ms * sim._ms
        spikes, _ = sim._fr.run_cue_rates(sim.bundle, dict(rates_by_kc_id), n_trials, seed,
                                          "synthetic_market")
        if len(spikes):
            index = np.array([sim.bundle["flyid2i"][f] for f in spikes["flywire_id"]], dtype=int)
            trial = np.asarray(spikes["trial"], dtype=int)
        else:
            index = trial = np.zeros(0, dtype=int)
        per_trial, mean = bin_spikes(index, trial, sim.bundle["n"], n_trials, duration_ms)
        runs[0] += 1
        if progress is not None:
            progress(runs[0])
        return (mean[sim._kc_brian], mean[sim._mbon_brian],
                per_trial[:, sim._kc_brian], per_trial[:, apl_index])

    runs = [0]
    sim.present_trials = present_trials
    return sim


def plan_lines(cfg: sm.SyntheticConfig, results_base: Path) -> list[str]:
    jobs = sm.plan_jobs(cfg)
    return [
        "Synthetic-market experiment: PLAN (dry run; nothing is simulated)",
        f"  mitigation: {cfg.mitigation}"
        + ("  (decided 2026-10-09: none; raw CIRCUIT-80 per-type-mean score)"
           if cfg.mitigation == sm.NO_MITIGATION else "  (NAMED HISTORICAL ALTERNATIVE, not the decided sweep)"),
        f"  encoder: {sm.option_b_variant(cfg)} Option B, mirrored NO framing, "
        f"{cfg.encoder.min_rate_hz:g}-{cfg.encoder.max_rate_hz:g} Hz, "
        f"pools of {cfg.encoder.pool_size} KCs (pool seed {cfg.encoder.pool_seed})",
        "  pools: LEFT-hemisphere KCs only; assert_pools_left_only aborts before any presentation",
        f"  ignition tracking: per trial, per framing (active > {cfg.ignition_active_hz:g} Hz, "
        f"ignited > {cfg.ignition_spread_fraction:.0%} of non-stimulated KCs); reported, never gating",
        f"  strengths: {list(cfg.signal_strengths)}",
        f"  market seeds: {list(cfg.market_seeds)}",
        f"  markets: {cfg.markets_per_seed}/seed ({cfg.train_count} chronological train, "
        f"{cfg.test_count} test)",
        f"  presentation: {cfg.duration_ms:g} ms x {cfg.trials} trials, Option B (2 runs/market)",
        f"  conditions: {list(sm.CONDITIONS)}",
        f"  parallel jobs: {len(jobs)}; longest dependency chain: {sm.critical_path_runs(cfg)} runs",
        f"  ESTIMATED SIMULATION RUNS: {sm.estimated_run_count(cfg)}",
        f"  simulated trial-seconds: {sm.estimated_run_count(cfg) * cfg.duration_ms / 1000 * cfg.trials:g}",
        f"  results: {sm.results_dir_for(results_base, cfg)}",
        f"  per job: {2 * cfg.markets_per_seed} strictly sequential runs ({cfg.train_count} train markets, then {cfg.test_count} test)",
        "  Wall-clock time and memory per process on the server are UNVERIFIED.",
    ]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--mitigation", choices=sm.MITIGATIONS,
                   default=sm.NO_MITIGATION,
                   help="Default 'none' (decided 2026-10-09): the ACCEPTED encoder and the raw"
                   " score. total_drive_balancing and innate_score_subtraction are retained"
                   " only as named historical alternatives.")
    p.add_argument("--dry-run", action="store_true", help="Print plans only; simulate nothing.")
    p.add_argument("--results-base", type=Path, default=RESULTS_BASE)
    p.add_argument("--ids", type=Path, default=IDS_PATH,
                   help="Frozen neuron-ID table giving each KC's hemisphere.")
    p.add_argument("--arms", type=lambda v: tuple(a for a in v.split(",") if a),
                   help="With --list-jobs: only these arms (comma-separated).")
    p.add_argument("--phase", type=int, choices=sorted(sm.RUN_PHASES),
                   help="With --list-jobs: only this phase's arms (1: profit, learning_off;"
                   " 2: accuracy, profit_drift_off).")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--job", help="Run one job ID.")
    group.add_argument("--list-jobs", action="store_true")
    group.add_argument("--finish", action="store_true", help="Evaluate completed jobs; no simulation.")
    group.add_argument("--finish-phase1", action="store_true",
                       help="Phase 1 only (2026-10-11 budget revision): the pre-stated gate and reports from"
                       " profit and learning_off; accuracy and profit_drift_off reported as not run."
                       " Writes verdict_phase1.json; no simulation.")
    return p


def _config(mitigation: str) -> sm.SyntheticConfig:
    return sm.SyntheticConfig(mitigation=mitigation)


def _load_outputs(cfg: sm.SyntheticConfig, paths: Paths, arms=None) -> dict:
    outputs = {}
    for job in sm.plan_jobs(cfg, arms):
        if job.kind != "condition":
            continue
        path = paths.output(job)
        if not path.exists():
            raise RuntimeError(f"missing job output {job.id}")
        outputs[(job.strength, job.market_seed, job.condition)] = json.loads(path.read_text())
    return outputs


def finish(cfg: sm.SyntheticConfig, results_base: Path) -> dict:
    directory = sm.results_dir_for(results_base, cfg)
    paths = Paths(directory)
    verdict = sm.evaluate_signal_requirement(_load_outputs(cfg, paths), cfg)
    _write_json(directory / "verdict.json", verdict)
    return verdict


def finish_phase1(cfg: sm.SyntheticConfig, results_base: Path) -> dict:
    """Reads only the phase 1 job files (profit, learning_off); writes verdict_phase1.json."""
    directory = sm.results_dir_for(results_base, cfg)
    paths = Paths(directory)
    verdict = sm.evaluate_phase1(_load_outputs(cfg, paths, sm.PHASE1_ARMS), cfg)
    _write_json(directory / "verdict_phase1.json", verdict)
    return verdict


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    cfg = _config(args.mitigation)
    directory = sm.results_dir_for(args.results_base, cfg)
    paths = Paths(directory)
    if args.dry_run:
        print("\n".join(plan_lines(cfg, args.results_base)))
        return 0
    jobs = sm.plan_jobs(cfg)
    if args.list_jobs:
        arms = sm.RUN_PHASES[args.phase] if args.phase else args.arms
        for job in sm.run_order(sm.plan_jobs(cfg, arms)):
            dependencies = f" after {','.join(job.deps)}" if job.deps else ""
            print(f"{job.id:48s} {job.n_runs:4d} runs  {'done' if paths.done(job) else 'todo'}{dependencies}")
        return 0
    if args.finish:
        verdict = finish(cfg, args.results_base)
        print(json.dumps(verdict, indent=2))
        return 0
    if args.finish_phase1:
        verdict = finish_phase1(cfg, args.results_base)
        print(json.dumps(verdict, indent=2))
        return 0
    selected = next((job for job in jobs if job.id == args.job), None)
    if selected is None:
        raise SystemExit("--job with a valid job ID is required; use --list-jobs")
    if paths.done(selected):
        print(f"{selected.id}: already done")
        return 0
    for dependency in selected.deps:
        dependency_job = next(job for job in jobs if job.id == dependency)
        if not paths.done(dependency_job):
            raise SystemExit(f"{selected.id} requires {dependency}")

    # Lazy import: this is the only branch that loads Brian2/connectome data.
    print(f"{START_TAG} {selected.id} t={time.time():.2f} pid={os.getpid()}", flush=True)
    kc_sides = kc_side_map(args.ids)
    sim = build_sweep_simulator(progress_printer(selected.id, selected.n_runs))
    # Fail before the first presentation (and before any job file exists) if the
    # pools would not be left-only. run_dataset applies the same guard again.
    sm.setup_encoder(sim, cfg, kc_sides)
    if selected.kind == "innate":
        scores = sm.compute_innate_scores(sim, cfg, selected.strength, selected.market_seed,
                                          kc_sides=kc_sides)
        output = {"strength": selected.strength, "market_seed": selected.market_seed, "scores": scores}
    else:
        innate = None
        if selected.deps:
            dependency_job = next(job for job in jobs if job.id == selected.deps[0])
            innate = json.loads(paths.output(dependency_job).read_text())["scores"]
        output = sm.run_dataset(
            sim,
            cfg,
            selected.strength,
            selected.market_seed,
            selected.condition,
            kc_sides=kc_sides,
            innate_scores=innate,
        )
    _write_json(paths.output(selected), output)
    print(f"{selected.id}: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
