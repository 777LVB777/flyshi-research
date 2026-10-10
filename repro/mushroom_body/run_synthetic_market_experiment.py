#!/usr/bin/env python3
"""Run the pre-stated synthetic-market signal sweep.

Without ``--dry-run``, job execution constructs the real Brian2 backend and runs
simulations.  Tests and dry-run never do so.  See
docs/design/synthetic-market-experiment.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling runners; none imports Brian2 at module level

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
# The ONE shared definition of "left", as in the fixed graded runners.
from run_left_only_pool_diagnostic import IDS_PATH, kc_side_map  # noqa: E402
# Per-trial binning shared with the diagnostics, so ignition is measured identically.
from run_left_only_realistic_drive_diagnostic import bin_spikes  # noqa: E402

RESULTS_BASE = HERE / "results"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, separators=(",", ":")))
    temporary.replace(path)


class Paths:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.parts = directory / "parts"

    def output(self, job: sm.Job) -> Path:
        return self.parts / (job.id.replace(":", "_") + ".json")

    def done(self, job: sm.Job) -> bool:
        return self.output(job).exists()


def build_sweep_simulator():
    """The real backend plus per-trial readout (decided 2026-10-09).

    Wraps the population simulator (a ``FastRunnerSimulator`` that also indexes APL)
    and adds ``present_trials``: one ``run_cue_rates`` call, binned by trial with the
    diagnostics' ``bin_spikes``. Its trial means equal ``FastRunnerSimulator.present``
    exactly, so scores and eligibility are unchanged by the tracking. Imports Brian2.
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
        return (mean[sim._kc_brian], mean[sim._mbon_brian],
                per_trial[:, sim._kc_brian], per_trial[:, apl_index])

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
    group = p.add_mutually_exclusive_group()
    group.add_argument("--job", help="Run one job ID.")
    group.add_argument("--list-jobs", action="store_true")
    group.add_argument("--finish", action="store_true", help="Evaluate completed jobs; no simulation.")
    return p


def _config(mitigation: str) -> sm.SyntheticConfig:
    return sm.SyntheticConfig(mitigation=mitigation)


def _load_outputs(cfg: sm.SyntheticConfig, paths: Paths) -> dict:
    outputs = {}
    for job in sm.plan_jobs(cfg):
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
        for job in jobs:
            dependencies = f" after {','.join(job.deps)}" if job.deps else ""
            print(f"{job.id:48s} {job.n_runs:4d} runs  {'done' if paths.done(job) else 'todo'}{dependencies}")
        return 0
    if args.finish:
        verdict = finish(cfg, args.results_base)
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
    kc_sides = kc_side_map(args.ids)
    sim = build_sweep_simulator()
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
