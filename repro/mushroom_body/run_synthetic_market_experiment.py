#!/usr/bin/env python3
"""Run the pre-stated synthetic-market signal sweep.

Without ``--dry-run``, job execution constructs the real Brian2 backend and runs
simulations.  Tests and dry-run never do so.  See
docs/design/synthetic-market-experiment.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from flyshi_research.learning import synthetic_market as sm

HERE = Path(__file__).resolve().parent
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


def plan_lines(cfg: sm.SyntheticConfig, results_base: Path) -> list[str]:
    jobs = sm.plan_jobs(cfg)
    return [
        "Synthetic-market experiment: PLAN (dry run; nothing is simulated)",
        f"  mitigation: {cfg.mitigation}",
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
        "  Wall-clock time is UNVERIFIED.",
        "  Fast-runner equivalence and real run_cue_rates execution remain UNVERIFIED prerequisites.",
    ]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--mitigation", choices=sm.MITIGATIONS,
                   help="Required for a real run; deliberately has no default.")
    p.add_argument("--dry-run", action="store_true", help="Print plans only; simulate nothing.")
    p.add_argument("--results-base", type=Path, default=RESULTS_BASE)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--job", help="Run one job ID.")
    group.add_argument("--list-jobs", action="store_true")
    group.add_argument("--finish", action="store_true", help="Evaluate completed jobs; no simulation.")
    return p


def _config(mitigation: str) -> sm.SyntheticConfig:
    return sm.SyntheticConfig(mitigation=mitigation)


def _require_mitigation(args: argparse.Namespace) -> sm.SyntheticConfig:
    if not args.mitigation:
        raise SystemExit("choose --mitigation total_drive_balancing or innate_score_subtraction")
    return _config(args.mitigation)


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
    if args.dry_run and not args.mitigation:
        for mitigation in sm.MITIGATIONS:
            print("\n".join(plan_lines(_config(mitigation), args.results_base)))
        print("OPEN DECISION: choose exactly one mitigation before any real run.")
        return 0
    cfg = _require_mitigation(args)
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
    from run_first_learning_test import FastRunnerSimulator
    from flyshi_research.learning.first_learning import ExperimentConfig

    sim = FastRunnerSimulator(ExperimentConfig())
    if selected.kind == "innate":
        scores = sm.compute_innate_scores(sim, cfg, selected.strength, selected.market_seed)
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
            innate_scores=innate,
        )
    _write_json(paths.output(selected), output)
    print(f"{selected.id}: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
