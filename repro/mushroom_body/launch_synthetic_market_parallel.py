#!/usr/bin/env python3
"""Parallel launcher for synthetic-market jobs; dry-run is simulation-free."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from flyshi_research.learning import synthetic_market as sm

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_synthetic_market_experiment.py"
RESULTS_BASE = HERE / "results"
THREAD_ENV = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}


def acquire_lock(path: Path) -> None:
    """Prevent two launchers from scheduling the same restartable jobs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(path.read_text())
                os.kill(pid, 0)
            except (ValueError, ProcessLookupError):
                path.unlink(missing_ok=True)
                continue
            raise RuntimeError(f"another launcher (pid {pid}) holds {path}")
        with os.fdopen(descriptor, "w") as handle:
            handle.write(str(os.getpid()))
        return
    raise RuntimeError(f"could not acquire {path}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split(";")[0])
    p.add_argument("--mitigation", default=sm.TOTAL_DRIVE_BALANCING, choices=sm.MITIGATIONS)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-procs", type=int, default=1,
                   help="Maximum workers; default 1 because real per-process RAM is UNVERIFIED.")
    p.add_argument("--results-base", type=Path, default=RESULTS_BASE)
    p.add_argument("--poll-seconds", type=float, default=5.0)
    return p


def worker_argv(job: sm.Job, mitigation: str, results_base: Path) -> list[str]:
    return [sys.executable, str(RUNNER), "--mitigation", mitigation, "--job", job.id,
            "--results-base", str(results_base)]


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.max_procs < 1:
        raise SystemExit("--max-procs must be >= 1")
    cfg = sm.SyntheticConfig(mitigation=args.mitigation)
    jobs = sm.plan_jobs(cfg)
    if args.dry_run:
        print(f"Synthetic launcher dry run: {len(jobs)} jobs, {sm.estimated_run_count(cfg)} runs, "
              f"up to {args.max_procs} processes")
        print("Memory per process and wall-clock time are UNVERIFIED; no process started.")
        return 0

    # Import the simulation-free path helper only after dry-run exits.
    import run_synthetic_market_experiment as runner

    paths = runner.Paths(sm.results_dir_for(args.results_base, cfg))
    lock = paths.directory / "logs" / "launcher.lock"
    acquire_lock(lock)
    pending = [job for job in jobs if not paths.done(job)]
    running: dict[str, tuple[subprocess.Popen, object]] = {}
    failed: list[str] = []
    try:
        while pending or running:
            for job_id in list(running):
                process, handle = running[job_id]
                if process.poll() is None:
                    continue
                handle.close()
                del running[job_id]
                if process.returncode:
                    failed.append(job_id)
            done = {job.id for job in jobs if paths.done(job)}
            for job in list(pending):
                if any(dependency in failed for dependency in job.deps):
                    pending.remove(job)
            while len(running) < args.max_procs:
                ready = next((job for job in pending if all(dep in done for dep in job.deps)), None)
                if ready is None:
                    break
                pending.remove(ready)
                log_path = paths.directory / "logs" / (ready.id.replace(":", "_") + ".log")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                handle = open(log_path, "a")
                environment = {**os.environ, **THREAD_ENV}
                process = subprocess.Popen(
                    worker_argv(ready, cfg.mitigation, args.results_base),
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    env=environment,
                )
                running[ready.id] = (process, handle)
            if pending or running:
                time.sleep(args.poll_seconds)
        if failed:
            print(f"failed jobs: {failed}")
            return 1
        verdict = runner.finish(cfg, args.results_base)
        print(f"signal requirement: {verdict['signal_requirement']}")
        return 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
