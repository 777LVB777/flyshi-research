"""Run the first learning test's jobs as parallel processes, as many as RAM safely allows.

The protocol (docs/design/first-learning-test.md, section 10) splits into independent
jobs; each runs in its own process via ``run_first_learning_test.py --job ID`` and
writes its own result file. When every job is done this launcher merges the files and
writes the verdict (``run_first_learning_test.py --finish`` does the same by hand).

What runs in parallel and what cannot:
  * the 5 conditions' TRAINING jobs run side by side, but inside one condition the
    N = 40 training presentations are strictly sequential (each sees the weights
    learned so far), so one training job is the longest chain;
  * each test seed (cue A then cue B) is its own job: 5 pre-training jobs (any time)
    and 5 post-test jobs per condition (after that condition's training).

Concurrency: floor((available RAM - headroom) / GB per process), capped at the core
count. Each process needs ~4-5 GB (the user's figure; NOT MEASURED on the server), so
the default is 5 GB. Headroom defaults to max(2 GB, 10% of total RAM). Before starting
each extra job the launcher re-reads available RAM and waits if it has dropped, and it
staggers starts so network builds (which load the connectome) do not all peak at once.

UNVERIFIED: that several processes compiling Brian2's Cython code into the shared
cache (~/.cython/brian_extensions) at once is safe. Brian2's
codegen.runtime.cython.multiprocess_safe preference (file locks) is believed to be on
by default in 2.5.1; the staggered start also makes simultaneous compiles less likely.
Each worker gets OMP/OPENBLAS/MKL_NUM_THREADS=1 so processes do not fight over cores.

Restartable: finished jobs are skipped (their result file exists); an interrupted
training job resumes from its per-presentation checkpoint. A lock file stops two
launchers from working on the same results directory.

RUNNING THIS WITHOUT --dry-run STARTS BRIAN2 SIMULATIONS. Run it on the server inside
tmux (docs/cloud/server-setup.md). --dry-run prints the plan and a time estimate and
simulates nothing.
"""

from __future__ import annotations

import argparse
import math
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set

from flyshi_research.learning import first_learning as fl

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_first_learning_test.py"
RESULTS_BASE = HERE / "results"

GB = 1024 ** 3
DEFAULT_GB_PER_PROC = 5.0
DEFAULT_STAGGER_S = 60.0  # placeholder: network build time on the server is NOT MEASURED
THREAD_ENV = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}


# --------------------------------------------------------------------------- #
# resources
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Resources:
    total_gb: float
    available_gb: float
    cores: int
    source: str  # where the numbers came from


def _meminfo(path: str = "/proc/meminfo") -> Dict[str, float]:
    out = {}
    with open(path) as fh:
        for line in fh:
            key, rest = line.split(":", 1)
            out[key] = float(rest.split()[0]) * 1024 / GB  # kB -> GB
    return out


def available_gb() -> Optional[float]:
    """Current MemAvailable (Linux). None where it cannot be read."""
    try:
        return _meminfo()["MemAvailable"]
    except (OSError, KeyError, ValueError):
        return None


def detect_resources() -> Resources:
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    try:
        m = _meminfo()
        return Resources(m["MemTotal"], m["MemAvailable"], cores, "/proc/meminfo MemAvailable")
    except (OSError, KeyError, ValueError):
        pass
    if platform.system() == "Darwin":  # dry-run convenience only; the real run is on Linux
        total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                   text=True, check=True).stdout) / GB
        return Resources(total, total * 0.5, cores, "macOS: total RAM; 'available' GUESSED as 50%")
    raise SystemExit("cannot read available RAM on this system; pass --max-procs")


def default_headroom_gb(total_gb: float) -> float:
    return max(2.0, 0.10 * total_gb)


def plan_slots(res: Resources, gb_per_proc: float = DEFAULT_GB_PER_PROC,
               headroom_gb: Optional[float] = None, max_procs: Optional[int] = None) -> int:
    """floor((available - headroom) / gb_per_proc), capped by cores and --max-procs.
    0 means not even one process fits safely."""
    if gb_per_proc <= 0:
        raise ValueError("gb_per_proc must be positive")
    head = default_headroom_gb(res.total_gb) if headroom_gb is None else headroom_gb
    by_ram = int(math.floor(max(0.0, res.available_gb - head) / gb_per_proc))
    slots = min(by_ram, res.cores)
    if max_procs is not None:
        slots = min(slots, max_procs)
    return max(0, slots)


# --------------------------------------------------------------------------- #
# scheduling (shared by the real launcher and the time estimate)
# --------------------------------------------------------------------------- #
def next_ready(pending: Sequence[fl.Job], done: Set[str]) -> Optional[fl.Job]:
    """First pending job whose dependencies are all done, in plan order (training
    first: it is the longest chain)."""
    for j in pending:
        if all(d in done for d in j.deps):
            return j
    return None


def estimate_makespan(jobs: Sequence[fl.Job], slots: int, run_minutes: float,
                      build_minutes: float = 0.0, done: Sequence[str] = ()) -> float:
    """Minutes until every job is done, if each job takes build + n_runs * run_minutes
    and the launcher schedules exactly as below. Every run is given the same length:
    this ignores that a training run is 1 trial and a test run is 5."""
    if slots < 1:
        raise ValueError("slots must be >= 1")
    done_set = set(done)
    pending = [j for j in jobs if j.id not in done_set]
    running: List[tuple] = []  # (end time, job id)
    t = 0.0
    while pending or running:
        while len(running) < slots:
            j = next_ready(pending, done_set)
            if j is None:
                break
            pending.remove(j)
            running.append((t + build_minutes + j.n_runs * run_minutes, j.id))
        if not running:
            raise RuntimeError("jobs with unmet dependencies: " + ", ".join(j.id for j in pending))
        running.sort()
        t = running[0][0]
        while running and running[0][0] == t:
            done_set.add(running.pop(0)[1])
    return t


# --------------------------------------------------------------------------- #
# the launcher
# --------------------------------------------------------------------------- #
def worker_argv(job: fl.Job, results_base: Path, smoke: bool, python: str = sys.executable) -> List[str]:
    argv = [python, str(RUNNER), "--job", job.id, "--results-base", str(results_base)]
    return argv + (["--smoke"] if smoke else [])


class LockHeld(RuntimeError):
    pass


def acquire_lock(path: Path) -> None:
    """One launcher per results directory. A lock left by a dead process is replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(path.read_text().strip() or 0)
                os.kill(pid, 0)
            except (ValueError, ProcessLookupError):
                path.unlink(missing_ok=True)  # stale: its launcher is gone
                continue
            except PermissionError:
                pass  # process exists (owned by someone else)
            raise LockHeld(f"another launcher (pid {path.read_text().strip()}) holds {path}")
        with os.fdopen(fd, "w") as fh:
            fh.write(str(os.getpid()))
        return
    raise LockHeld(f"could not acquire {path}")


class Launcher:
    def __init__(self, cfg: fl.ExperimentConfig, results_base: Path, slots: int,
                 gb_per_proc: float = DEFAULT_GB_PER_PROC, headroom_gb: float = 2.0,
                 stagger_s: float = DEFAULT_STAGGER_S, poll_s: float = 5.0,
                 argv_for: Optional[Callable[[fl.Job], List[str]]] = None,
                 mem_reader: Callable[[], Optional[float]] = available_gb,
                 log: Callable[[str], None] = print, smoke: bool = False) -> None:
        if slots < 1:
            raise ValueError("slots must be >= 1")
        self.cfg, self.base, self.slots = cfg, Path(results_base), slots
        self.gb_per_proc, self.headroom_gb = gb_per_proc, headroom_gb
        self.stagger_s, self.poll_s, self.mem_reader, self.log = stagger_s, poll_s, mem_reader, log
        self.argv_for = argv_for or (lambda j: worker_argv(j, self.base, smoke))
        self.dir = fl.results_dir_for(self.base, cfg)
        self.paths = fl.ResultPaths(self.dir)
        self.log_dir = self.base / f"logs_first_learning_{cfg.config_hash()}"
        self.jobs = fl.plan_jobs(cfg)

    def _log_path(self, job: fl.Job) -> Path:
        return self.log_dir / (job.id.replace(":", "_") + ".log")

    def _memory_ok(self) -> bool:
        avail = self.mem_reader()
        return avail is None or avail - self.headroom_gb >= self.gb_per_proc

    def run(self) -> dict:
        """Run every unfinished job; returns {"done": [...], "failed": [...], "verdict": ...}."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        lock = self.log_dir / "launcher.lock"
        acquire_lock(lock)
        try:
            return self._run()
        finally:
            lock.unlink(missing_ok=True)

    def _run(self) -> dict:
        done = {j.id for j in self.jobs if self.paths.job_done(j)}
        pending = [j for j in self.jobs if j.id not in done]
        failed: List[str] = []
        blocked: Set[str] = set()
        running: Dict[str, tuple] = {}  # job id -> (Popen, job, log handle)
        last_start = -math.inf
        self.log(f"[launcher] {len(done)} jobs already done, {len(pending)} to run, "
                 f"up to {self.slots} at once; logs in {self.log_dir}")
        try:
            while pending or running:
                # reap finished processes
                for jid in list(running):
                    proc, job, fh = running[jid]
                    if proc.poll() is None:
                        continue
                    fh.close()
                    del running[jid]
                    if proc.returncode == 0 and self.paths.job_output(job).exists():
                        done.add(jid)
                        self.log(f"[launcher] done   {jid}")
                    else:
                        failed.append(jid)
                        self.log(f"[launcher] FAILED {jid} (exit {proc.returncode}); see {self._log_path(job)}")
                # jobs that depend on a failure cannot run this time
                for j in list(pending):
                    if any(d in failed or d in blocked for d in j.deps):
                        pending.remove(j)
                        blocked.add(j.id)
                # start new work
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
            result["verdict"] = fl.finish(self.dir, self.cfg)
        return result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="On the server, inside tmux:\n"
                                       "  .venv-shiu/bin/python repro/mushroom_body/launch_first_learning_parallel.py\n")
    p.add_argument("--dry-run", action="store_true", help="Print resources, plan and time estimate; run nothing.")
    p.add_argument("--smoke", action="store_true", help="Tiny pipeline check config (NOT the pre-stated test).")
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
    cfg = fl.ExperimentConfig.smoke() if args.smoke else fl.ExperimentConfig()
    res = detect_resources()
    head = default_headroom_gb(res.total_gb) if args.headroom_gb is None else args.headroom_gb
    slots = plan_slots(res, args.gb_per_proc, head, args.max_procs)
    paths = fl.ResultPaths(fl.results_dir_for(args.results_base, cfg))
    jobs = fl.plan_jobs(cfg)
    done = [j.id for j in jobs if paths.job_done(j)]
    print(f"machine: {res.total_gb:.1f} GB RAM, {res.available_gb:.1f} GB available ({res.source}), "
          f"{res.cores} cores")
    print(f"concurrency: floor(({res.available_gb:.1f} - {head:.1f} headroom) / {args.gb_per_proc:g} GB) "
          f"capped at {res.cores} cores{f' and --max-procs {args.max_procs}' if args.max_procs else ''} "
          f"-> {slots} processes")
    print(f"jobs: {len(jobs)} ({len(done)} done); runs per job: training {cfg.n_training} "
          f"(sequential), each test seed 2; pre-stated test: {cfg.prestated}")
    if slots >= 1:
        for per_run, label in ((0.5, "optimistic 30 s/run"), (10.0, "pessimistic 10 min/run")):
            m = estimate_makespan(jobs, slots, per_run, done=done)
            print(f"estimate ({label}, network builds not counted): {m / 60:.1f} h")
    if slots < 1:
        print("NOT ENOUGH RAM for one process under these settings; nothing will be started.")
        return 2
    if args.dry_run:
        return 0
    launcher = Launcher(cfg, args.results_base, slots, args.gb_per_proc, head, args.stagger_s,
                        smoke=args.smoke)
    result = launcher.run()
    if result["verdict"] is not None:
        print("\n".join(fl.summary_lines(result["verdict"])))
        print("Plain-language report: .venv-shiu/bin/python repro/mushroom_body/report_first_learning.py")
        return 0
    print(f"[launcher] not finished: failed {result['failed']}, blocked {result['blocked']}. "
          "Fix the cause (see the logs) and re-run this command; finished jobs are skipped.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
