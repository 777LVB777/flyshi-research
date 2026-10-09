#!/usr/bin/env python3
"""Run the synthetic-market sweep's jobs as parallel processes, as many as RAM safely allows.

The protocol (docs/design/synthetic-market-experiment.md, section 7) splits into 100
independent ``(strength, market seed, condition)`` jobs; each runs in its own process
via ``run_synthetic_market_experiment.py --job ID`` and writes its own result file.
Inside a job the 100 markets are strictly sequential (each training market sees the
weights learned so far), so one job is the longest chain. When every job is done
this launcher evaluates the pre-stated gate (``--finish`` does the same by hand).

Concurrency, memory re-check and staggered starts are the first learning launcher's
rule, reused from ``launch_first_learning_parallel.py``: floor((available RAM -
headroom) / GB per process), capped at the core count and --max-procs. The 5 GB per
process is the working figure (4-5 GB), NOT MEASURED on the server. Headroom defaults
to max(2 GB, 10% of total RAM). Before starting each extra job the launcher re-reads
available RAM and waits if it has dropped, and it staggers starts so network builds
(which load the connectome) do not all peak at once.

Restartable per job: finished job files are skipped; an interrupted job restarts its
100-market chain (no per-market checkpoint). A lock file stops two launchers from
working on the same results directory. Each worker gets OMP/OPENBLAS/MKL_NUM_THREADS=1.

RUNNING THIS WITHOUT --dry-run STARTS BRIAN2 SIMULATIONS. Run it on the server inside
tmux (docs/cloud/server-setup.md). --dry-run prints the plan and a time estimate and
simulates nothing.
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling scripts; none imports Brian2 at module level

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from launch_first_learning_parallel import (  # noqa: E402
    DEFAULT_GB_PER_PROC,
    DEFAULT_STAGGER_S,
    THREAD_ENV,
    acquire_lock,
    available_gb,
    default_headroom_gb,
    detect_resources,
    estimate_makespan,
    next_ready,
    plan_slots,
)

RUNNER = HERE / "run_synthetic_market_experiment.py"
RESULTS_BASE = HERE / "results"
#: planning figure for the dry-run estimate only (speed calibration measured 54.4 s
#: for 500 KCs x 1000 ms x 5 trials on the development Mac; NOT measured on the server)
PLANNING_SECONDS_PER_RUN = 55.0


def worker_argv(job: sm.Job, mitigation: str, results_base: Path,
                python: str = sys.executable) -> List[str]:
    return [python, str(RUNNER), "--mitigation", mitigation, "--job", job.id,
            "--results-base", str(results_base)]


class Launcher:
    def __init__(self, cfg: sm.SyntheticConfig, results_base: Path, slots: int,
                 gb_per_proc: float = DEFAULT_GB_PER_PROC, headroom_gb: float = 2.0,
                 stagger_s: float = DEFAULT_STAGGER_S, poll_s: float = 5.0,
                 argv_for: Optional[Callable[[sm.Job], List[str]]] = None,
                 mem_reader: Callable[[], Optional[float]] = available_gb,
                 log: Callable[[str], None] = print,
                 finish: Optional[Callable[[], dict]] = None) -> None:
        if slots < 1:
            raise ValueError("slots must be >= 1")
        # Imported here, not at module level, so --dry-run stays as light as possible.
        import run_synthetic_market_experiment as runner

        self.cfg, self.base, self.slots = cfg, Path(results_base), slots
        self.gb_per_proc, self.headroom_gb = gb_per_proc, headroom_gb
        self.stagger_s, self.poll_s, self.mem_reader, self.log = stagger_s, poll_s, mem_reader, log
        self.argv_for = argv_for or (lambda j: worker_argv(j, cfg.mitigation, self.base))
        self.paths = runner.Paths(sm.results_dir_for(self.base, cfg))
        self.finish = finish or (lambda: runner.finish(cfg, self.base))
        self.log_dir = self.paths.directory / "logs"
        self.jobs = sm.plan_jobs(cfg)

    def _log_path(self, job: sm.Job) -> Path:
        return self.log_dir / (job.id.replace(":", "_") + ".log")

    def _memory_ok(self) -> bool:
        avail = self.mem_reader()
        return avail is None or avail - self.headroom_gb >= self.gb_per_proc

    def run(self) -> dict:
        """Run every unfinished job; returns {"done", "failed", "blocked", "verdict"}."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        lock = self.log_dir / "launcher.lock"
        acquire_lock(lock)
        try:
            return self._run()
        finally:
            lock.unlink(missing_ok=True)

    def _run(self) -> dict:
        done = {j.id for j in self.jobs if self.paths.done(j)}
        pending = [j for j in self.jobs if j.id not in done]
        failed: List[str] = []
        blocked: Set[str] = set()
        running: Dict[str, tuple] = {}  # job id -> (Popen, job, log handle)
        last_start = -math.inf
        self.log(f"[launcher] {len(done)} jobs already done, {len(pending)} to run, "
                 f"up to {self.slots} at once; logs in {self.log_dir}")
        try:
            while pending or running:
                for jid in list(running):
                    proc, job, fh = running[jid]
                    if proc.poll() is None:
                        continue
                    fh.close()
                    del running[jid]
                    if proc.returncode == 0 and self.paths.done(job):
                        done.add(jid)
                        self.log(f"[launcher] done   {jid}")
                    else:
                        failed.append(jid)
                        self.log(f"[launcher] FAILED {jid} (exit {proc.returncode}); see {self._log_path(job)}")
                for j in list(pending):
                    if any(d in failed or d in blocked for d in j.deps):
                        pending.remove(j)
                        blocked.add(j.id)
                if len(running) < self.slots and time.monotonic() - last_start >= self.stagger_s:
                    j = next_ready(pending, done)
                    if j is not None and (not running or self._memory_ok()):
                        pending.remove(j)
                        self._log_path(j).parent.mkdir(parents=True, exist_ok=True)
                        fh = open(self._log_path(j), "a")
                        env = {**os.environ, **THREAD_ENV}
                        running[j.id] = (subprocess.Popen(self.argv_for(j), stdout=fh,
                                                          stderr=subprocess.STDOUT, env=env), j, fh)
                        last_start = time.monotonic()
                        self.log(f"[launcher] start  {j.id} ({len(running)}/{self.slots} running)")
                        continue
                    # otherwise: waiting for RAM, a free slot, or the stagger interval
                if pending and not running and next_ready(pending, done) is None:
                    break  # nothing can ever become ready
                time.sleep(self.poll_s)
        except KeyboardInterrupt:
            self.log("[launcher] interrupted: stopping workers (re-run to resume)")
            for proc, _, fh in running.values():
                proc.terminate()
            for proc, _, fh in running.values():
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                fh.close()
            raise
        result = {"done": sorted(done), "failed": sorted(failed), "blocked": sorted(blocked),
                  "verdict": None}
        if not failed and not blocked and len(done) == len(self.jobs):
            result["verdict"] = self.finish()
        return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="On the server, inside tmux:\n"
                                       "  .venv-shiu/bin/python repro/mushroom_body/launch_synthetic_market_parallel.py\n")
    p.add_argument("--mitigation", default=sm.NO_MITIGATION, choices=sm.MITIGATIONS,
                   help="Default 'none' (decided 2026-10-09).")
    p.add_argument("--dry-run", action="store_true", help="Print resources, plan and time estimate; run nothing.")
    p.add_argument("--results-base", type=Path, default=RESULTS_BASE)
    p.add_argument("--gb-per-proc", type=float, default=DEFAULT_GB_PER_PROC,
                   help="RAM budget per simulation process in GB (default 5; not measured on the server).")
    p.add_argument("--headroom-gb", type=float, default=None,
                   help="RAM kept free for the system (default max(2 GB, 10%% of total)).")
    p.add_argument("--max-procs", type=int, default=None, help="Upper limit on simultaneous processes.")
    p.add_argument("--stagger-s", type=float, default=DEFAULT_STAGGER_S,
                   help="Seconds between process starts (default 60).")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.max_procs is not None and args.max_procs < 1:
        raise SystemExit("--max-procs must be >= 1")
    cfg = sm.SyntheticConfig(mitigation=args.mitigation)
    res = detect_resources()
    head = default_headroom_gb(res.total_gb) if args.headroom_gb is None else args.headroom_gb
    slots = plan_slots(res, args.gb_per_proc, head, args.max_procs)
    jobs = sm.plan_jobs(cfg)
    import run_synthetic_market_experiment as runner  # simulation-free paths helper

    paths = runner.Paths(sm.results_dir_for(args.results_base, cfg))
    done = [j.id for j in jobs if paths.done(j)]
    print(f"machine: {res.total_gb:.1f} GB RAM, {res.available_gb:.1f} GB available ({res.source}), "
          f"{res.cores} cores")
    print(f"concurrency: floor(({res.available_gb:.1f} - {head:.1f} headroom) / {args.gb_per_proc:g} GB) "
          f"capped at {res.cores} cores{f' and --max-procs {args.max_procs}' if args.max_procs else ''} "
          f"-> {slots} processes")
    print(f"mitigation: {cfg.mitigation}; jobs: {len(jobs)} ({len(done)} done); "
          f"{sm.estimated_run_count(cfg)} runs; longest chain {sm.critical_path_runs(cfg)} runs")
    if slots >= 1:
        m = estimate_makespan(jobs, slots, PLANNING_SECONDS_PER_RUN / 60.0, done=done)
        print(f"estimate at {PLANNING_SECONDS_PER_RUN:g} s/run (UNVERIFIED on the server; "
              f"network builds not counted): {m / 60:.1f} h")
    else:
        print("NOT ENOUGH RAM for one process under these settings; nothing will be started.")
        return 2
    if args.dry_run:
        print("dry run: no process started, nothing written.")
        return 0
    launcher = Launcher(cfg, args.results_base, slots, args.gb_per_proc, head, args.stagger_s)
    result = launcher.run()
    if result["verdict"] is not None:
        print(f"signal requirement: {result['verdict']['signal_requirement']}")
        return 0
    print(f"[launcher] not finished: failed {result['failed']}, blocked {result['blocked']}. "
          "Fix the cause (see the logs) and re-run this command; finished jobs are skipped.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
