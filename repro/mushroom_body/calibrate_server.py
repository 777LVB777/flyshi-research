#!/usr/bin/env python3
"""Measure the sweep's real throughput on this machine: N concurrent jobs for a fixed time.

For each N in --procs (default 1, 4, 8) this starts N real sweep jobs
(``run_synthetic_market_experiment.py --job ID``, the first N jobs in run order,
each a different job) with the launcher's environment (one thread per process),
waits until every one has finished its network build and first run, then measures
for --minutes. It reports, per N:

- seconds per simulation run, per process (mean interval between consecutive runs
  inside the window; the build and the first run are excluded);
- peak resident memory per process (largest VmHWM / ru_maxrss of any worker);
- runs per hour for the whole machine (sum over processes of 3600 / s per run);
- the lowest MemAvailable seen while the level ran.

Then it stops the workers. The job outputs are never written: each job is a
500-run chain and is stopped long before its end, and the workers write into a
scratch results directory that is deleted afterwards. Nothing in the real results
directory is touched. A level whose memory runs short starts fewer processes than
asked (same rule as the launcher: a process starts only while MemAvailable minus
headroom is at least --gb-per-proc) and says so.

THIS RUNS REAL BRIAN2 SIMULATIONS. Default cost: about 1 h of server time
(3 levels x (ramp + first run + 12 min)). Run it on the server inside tmux:

    .venv-shiu/bin/python repro/mushroom_body/calibrate_server.py
    .venv-shiu/bin/python repro/mushroom_body/server_eta.py      # reads the newest file

--dry-run prints the plan and starts nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from launch_first_learning_parallel import (  # noqa: E402
    DEFAULT_GB_PER_PROC,
    THREAD_ENV,
    available_gb,
    default_headroom_gb,
    detect_resources,
)
from run_synthetic_market_experiment import PROGRESS_TAG  # noqa: E402

RUNNER = HERE / "run_synthetic_market_experiment.py"
OUT_DIR = HERE / "results" / "server_calibration"
DEFAULT_PROCS = (1, 4, 8)
DEFAULT_MINUTES = 12.0
DEFAULT_STAGGER_S = 30.0
PROGRESS_RE = re.compile(r"^\[progress\] (\S+) run (\d+)/(\d+) t=([\d.]+) maxrss_gb=([\d.]+)")


@dataclass
class Worker:
    job: str
    proc: subprocess.Popen
    log: Path
    started: float
    peak_hwm_gb: float = 0.0
    times: List[float] = field(default_factory=list)
    maxrss_gb: float = 0.0

    def read_progress(self) -> None:
        self.times, self.maxrss_gb = parse_progress(self.log.read_text(errors="replace"))


def parse_progress(text: str) -> tuple:
    """(completion times of each run, largest maxrss_gb reported) from a job log."""
    times, rss = [], 0.0
    for line in text.splitlines():
        m = PROGRESS_RE.match(line)
        if m:
            times.append(float(m.group(4)))
            rss = max(rss, float(m.group(5)))
    return times, rss


def seconds_per_run(times: Sequence[float], window_start: float, window_end: float) -> Optional[dict]:
    """Mean interval between consecutive run completions that both lie in the window."""
    inside = [t for t in times if window_start <= t <= window_end]
    if len(inside) < 2:
        return None
    intervals = [b - a for a, b in zip(inside, inside[1:])]
    return {"runs_in_window": len(inside), "mean_s": (inside[-1] - inside[0]) / (len(inside) - 1),
            "min_s": min(intervals), "max_s": max(intervals)}


def vm_hwm_gb(pid: int) -> Optional[float]:
    """Peak resident set of a live process (Linux VmHWM); None elsewhere or once gone."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return float(line.split()[1]) / 1024 ** 2  # kB -> GB
    except OSError:
        pass
    return None


def summarise_level(n_asked: int, workers: Sequence[Worker], window: tuple,
                    min_available: Optional[float], note: Optional[str]) -> dict:
    per_process = []
    for w in workers:
        w.read_progress()
        rate = seconds_per_run(w.times, *window)
        build = (w.times[0] - w.started) if w.times else None
        per_process.append({
            "job": w.job,
            "seconds_per_run": rate,
            "first_run_done_after_s": build,
            "peak_rss_gb": max(w.peak_hwm_gb, w.maxrss_gb) or None,
        })
    rates = [p["seconds_per_run"]["mean_s"] for p in per_process if p["seconds_per_run"]]
    peaks = [p["peak_rss_gb"] for p in per_process if p["peak_rss_gb"]]
    complete = len(rates) == len(workers) and len(workers) > 0
    first = [p["first_run_done_after_s"] for p in per_process if p["first_run_done_after_s"]]
    return {
        "procs_asked": n_asked,
        "procs_run": len(workers),
        "window_s": window[1] - window[0],
        "seconds_per_run_mean": sum(rates) / len(rates) if rates else None,
        "seconds_per_run_max_process": max(rates) if rates else None,
        "runs_per_hour": sum(3600.0 / r for r in rates) if complete else None,
        "peak_rss_gb_max": max(peaks) if peaks else None,
        "first_run_done_after_s_max": max(first) if first else None,
        "min_available_gb": min_available,
        "complete": complete,
        "note": note,
        "per_process": per_process,
    }


def stop(workers: Sequence[Worker], grace_s: float = 30.0) -> None:
    for w in workers:
        if w.proc.poll() is None:
            w.proc.send_signal(signal.SIGTERM)
    deadline = time.monotonic() + grace_s
    for w in workers:
        try:
            w.proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            w.proc.kill()
            w.proc.wait()


def run_level(n: int, jobs: Sequence[sm.Job], scratch: Path, minutes: float, stagger_s: float,
              gb_per_proc: float, headroom_gb: float,
              argv_for: Callable[[sm.Job, Path], List[str]],
              mem_reader: Callable[[], Optional[float]] = available_gb,
              log: Callable[[str], None] = print, poll_s: float = 5.0,
              ready_timeout_s: float = 1800.0) -> dict:
    """Start up to n workers (staggered, memory-checked), wait for each worker's first
    run, measure for ``minutes``, stop them all, and summarise."""
    logs = scratch / f"n{n}"
    logs.mkdir(parents=True, exist_ok=True)
    workers: List[Worker] = []
    note = None
    min_avail = mem_reader()
    try:
        for job in jobs[:n]:
            avail = mem_reader()
            if workers and avail is not None and avail - headroom_gb < gb_per_proc:
                note = (f"memory-limited: started {len(workers)} of {n} "
                        f"({avail:.1f} GB available, {headroom_gb:.1f} GB headroom, "
                        f"{gb_per_proc:g} GB per process needed)")
                log(f"[calibrate] N={n}: {note}")
                break
            path = logs / (job.id.replace(":", "_") + ".log")
            fh = open(path, "w")
            proc = subprocess.Popen(argv_for(job, scratch / "results"), stdout=fh,
                                    stderr=subprocess.STDOUT, env={**os.environ, **THREAD_ENV})
            fh.close()  # the child holds its own handle
            workers.append(Worker(job.id, proc, path, time.time()))
            log(f"[calibrate] N={n}: started {job.id} ({len(workers)}/{n})")
            if len(workers) < n:
                _wait(stagger_s, workers, mem_reader, poll_s, lambda a: None)
        # wait until every worker has completed its first run
        deadline = time.monotonic() + ready_timeout_s
        while True:
            for w in workers:
                w.read_progress()
            if all(w.times for w in workers):
                break
            dead = [w.job for w in workers if w.proc.poll() is not None]
            if dead:
                raise RuntimeError(f"worker(s) exited before their first run: {dead}; "
                                   f"see logs in {logs}")
            if time.monotonic() > deadline:
                raise RuntimeError(f"no first run within {ready_timeout_s:.0f} s; see {logs}")
            min_avail = _min(min_avail, mem_reader())
            _sample_hwm(workers)
            time.sleep(poll_s)
        start = max(w.times[0] for w in workers)  # after the slowest first run
        log(f"[calibrate] N={len(workers)}: all running; measuring for {minutes:g} min")

        def track(avail):
            nonlocal min_avail
            min_avail = _min(min_avail, avail)

        _wait(minutes * 60.0, workers, mem_reader, poll_s, track)
        end = time.time()
        died = [w.job for w in workers if w.proc.poll() is not None]
        if died:
            note = (note + "; " if note else "") + f"worker(s) exited during the window: {died}"
    finally:
        _sample_hwm(workers)
        stop(workers)
    return summarise_level(n, workers, (start, end), min_avail, note)


def _min(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return b if a is None else a if b is None else min(a, b)


def _sample_hwm(workers: Sequence[Worker]) -> None:
    for w in workers:
        hwm = vm_hwm_gb(w.proc.pid)
        if hwm is not None:
            w.peak_hwm_gb = max(w.peak_hwm_gb, hwm)


def _wait(seconds: float, workers, mem_reader, poll_s, track) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        _sample_hwm(workers)
        track(mem_reader())
        time.sleep(min(poll_s, max(0.0, end - time.monotonic())))


def environment() -> dict:
    """Provenance: what produced these figures."""
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    cpu = None
    try:
        cpu = next((line.split(":", 1)[1].strip() for line in
                    Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), None)
    except OSError:
        pass
    return {"hostname": socket.gethostname(), "platform": platform.platform(),
            "python": platform.python_version(), "cpu_model": cpu,
            "lscpu": run(["lscpu"]), "git_head": run(["git", "-C", str(HERE), "rev-parse", "HEAD"]),
            "gcc": (run(["g++", "--version"]) or "").split("\n")[0] or None}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--procs", type=lambda v: tuple(int(x) for x in v.split(",")),
                   default=DEFAULT_PROCS, help="Process counts to measure (default 1,4,8).")
    p.add_argument("--minutes", type=float, default=DEFAULT_MINUTES,
                   help="Measurement window per level, after every worker's first run (default 12).")
    p.add_argument("--stagger-s", type=float, default=DEFAULT_STAGGER_S,
                   help="Seconds between worker starts within a level (default 30).")
    p.add_argument("--gb-per-proc", type=float, default=DEFAULT_GB_PER_PROC,
                   help="Memory a new worker needs before it is started (default 5).")
    p.add_argument("--headroom-gb", type=float, default=None,
                   help="RAM kept free (default max(2 GB, 10%% of total), as the launcher).")
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--dry-run", action="store_true", help="Print the plan; start nothing.")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if not args.procs or min(args.procs) < 1:
        raise SystemExit("--procs must be positive integers")
    cfg = sm.SyntheticConfig()
    jobs = sm.run_order(sm.plan_jobs(cfg))
    res = detect_resources()
    head = default_headroom_gb(res.total_gb) if args.headroom_gb is None else args.headroom_gb
    print(f"machine: {res.total_gb:.1f} GB RAM, {res.available_gb:.1f} GB available ({res.source}), "
          f"{res.cores} logical CPUs")
    print(f"levels: N = {', '.join(map(str, args.procs))}; window {args.minutes:g} min after every "
          f"worker's first run; starts {args.stagger_s:g} s apart")
    print(f"workload: the real sweep runner on jobs {jobs[0].id} ... (first N in run order), "
          "outputs never written (stopped mid-chain, scratch directory)")
    if args.dry_run:
        print("dry run: nothing started.")
        return 0
    scratch = Path(tempfile.mkdtemp(prefix="flyshi_calibration_"))
    levels = []
    started = time.time()
    try:
        for n in args.procs:
            levels.append(run_level(
                n, jobs, scratch, args.minutes, args.stagger_s, args.gb_per_proc, head,
                argv_for=lambda job, base: [sys.executable, str(RUNNER), "--job", job.id,
                                            "--results-base", str(base)]))
            print(format_level(levels[-1]), flush=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    record = {
        "kind": "server_calibration",
        "config_hash": cfg.config_hash(),
        "started_unix": started,
        "finished_unix": time.time(),
        "machine": {"total_gb": res.total_gb, "available_gb_at_start": res.available_gb,
                    "logical_cpus": res.cores, "headroom_gb": head},
        "environment": environment(),
        "minutes_per_level": args.minutes,
        "levels": levels,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / (f"calibration_{socket.gethostname()}_"
                          f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(started))}.json")
    out.write_text(json.dumps(record, indent=1))
    print()
    print(format_table(levels))
    print(f"\nwrote {out}\nnext: .venv-shiu/bin/python repro/mushroom_body/server_eta.py --calibration {out}")
    return 0


def format_level(level: dict) -> str:
    s = level["seconds_per_run_mean"]
    r = level["runs_per_hour"]
    m = level["peak_rss_gb_max"]
    return (f"[calibrate] N={level['procs_run']}: "
            f"{f'{s:.1f} s/run' if s else 'no rate'}, "
            f"{f'{r:.0f} runs/h' if r else 'runs/h n/a'}, "
            f"peak {f'{m:.2f} GB' if m else 'n/a'}/process"
            + (f" ({level['note']})" if level["note"] else ""))


def format_table(levels: Sequence[dict]) -> str:
    rows = ["| N asked | N run | s per run (mean / slowest process) | runs per hour | "
            "peak memory per process | lowest MemAvailable |",
            "|---:|---:|---:|---:|---:|---:|"]
    for lv in levels:
        def f(x, fmt):
            return format(x, fmt) if x is not None else "n/a"
        rows.append(f"| {lv['procs_asked']} | {lv['procs_run']} | "
                    f"{f(lv['seconds_per_run_mean'], '.1f')} / {f(lv['seconds_per_run_max_process'], '.1f')} | "
                    f"{f(lv['runs_per_hour'], '.0f')} | {f(lv['peak_rss_gb_max'], '.2f')} GB | "
                    f"{f(lv['min_available_gb'], '.1f')} GB |")
    return "\n".join(rows)


if __name__ == "__main__":
    sys.exit(main())
