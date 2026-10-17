#!/usr/bin/env python3
"""Run Phase 2's 120 (chain, arm) jobs as parallel processes, as RAM safely allows.

The synthetic sweep's launcher loop, unchanged (memory rule, re-check before each
start, staggered starts, per-job restart, lock file, one thread per worker), driving
``run_real_market_experiment.py --job ID --run-dir DIR`` instead. When all 120 jobs
exist it computes the pre-stated verdict (``--finish`` does the same by hand).

Prerequisites, in order: ``--prepare`` (chains and frozen comparator), then
``--drive-check`` and the owner's sign-off (phase2-design.md, Section 3).

RUNNING THIS WITHOUT --dry-run STARTS BRIAN2 SIMULATIONS. --dry-run prints the plan
and a time estimate and simulates nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from flyshi_research.learning import real_market as rm  # noqa: E402
from launch_first_learning_parallel import (  # noqa: E402
    DEFAULT_GB_PER_PROC,
    DEFAULT_STAGGER_S,
    available_gb,
    default_headroom_gb,
    detect_resources,
    estimate_makespan,
    plan_slots,
)
from launch_synthetic_market_parallel import PLANNING_SECONDS_PER_RUN, Launcher  # noqa: E402

RUNNER = HERE / "run_real_market_experiment.py"


def worker_argv(job: rm.RealJob, run_dir: Path, python: str = sys.executable) -> List[str]:
    return [python, str(RUNNER), "--job", job.id, "--run-dir", str(run_dir)]


class RealLauncher(Launcher):
    """The synthetic launcher's scheduling loop over Phase 2 jobs."""

    def __init__(self, run_dir: Path, slots: int, gb_per_proc: float = DEFAULT_GB_PER_PROC,
                 headroom_gb: float = 2.0, stagger_s: float = DEFAULT_STAGGER_S, poll_s: float = 5.0,
                 argv_for=None, mem_reader=available_gb, log=print, finish=None) -> None:
        if slots < 1:
            raise ValueError("slots must be >= 1")
        import run_real_market_experiment as runner

        self.base, self.slots = Path(run_dir), slots
        self.gb_per_proc, self.headroom_gb = gb_per_proc, headroom_gb
        self.stagger_s, self.poll_s, self.mem_reader, self.log = stagger_s, poll_s, mem_reader, log
        self.argv_for = argv_for or (lambda j: worker_argv(j, self.base))
        self.paths = runner.Paths(self.base)
        self.finish = finish or (lambda: runner.finish(self.base))
        self.log_dir = self.paths.logs
        self.arms = None
        self.jobs = rm.plan_jobs()
        self.all_jobs = self.jobs


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--run-dir", type=Path, required=True, help="The directory --prepare wrote.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--gb-per-proc", type=float, default=DEFAULT_GB_PER_PROC)
    p.add_argument("--headroom-gb", type=float, default=None)
    p.add_argument("--max-procs", type=int, default=None)
    p.add_argument("--stagger-s", type=float, default=DEFAULT_STAGGER_S)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if not (args.run_dir / "manifest.json").exists():
        raise SystemExit(f"{args.run_dir} has no manifest.json: run --prepare first")
    res = detect_resources()
    head = default_headroom_gb(res.total_gb) if args.headroom_gb is None else args.headroom_gb
    slots = plan_slots(res, args.gb_per_proc, head, args.max_procs)
    jobs = rm.plan_jobs()
    import run_real_market_experiment as runner

    paths = runner.Paths(args.run_dir)
    done = [j.id for j in jobs if paths.done(j)]
    print(f"machine: {res.total_gb:.1f} GB RAM, {res.available_gb:.1f} GB available, {res.cores} cores "
          f"-> {slots} processes")
    print(f"jobs: {len(jobs)} ({len(done)} done); {sum(j.n_runs for j in jobs)} runs")
    if slots < 1:
        print("NOT ENOUGH RAM for one process under these settings; nothing will be started.")
        return 2
    m = estimate_makespan(jobs, slots, PLANNING_SECONDS_PER_RUN / 60.0, done=done)
    print(f"estimate at {PLANNING_SECONDS_PER_RUN:g} s/run (UNVERIFIED; network builds not counted): {m / 60:.1f} h")
    if args.dry_run:
        print("dry run: no process started, nothing written.")
        return 0
    result = RealLauncher(args.run_dir, slots, args.gb_per_proc, head, args.stagger_s).run()
    if result["verdict"] is not None:
        print(f"success: {result['verdict']['success']}")
        return 0
    print(f"[launcher] not finished: failed {result['failed']}, blocked {result['blocked']}.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
