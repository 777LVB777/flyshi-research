#!/usr/bin/env python3
"""One-screen status of the synthetic-market sweep. Reads files and the process table only.

Prints: jobs done / running / remaining (per phase), failed or interrupted jobs,
damaged job files, runs per hour, ETA, memory, disk, the launcher's state, and
ignition flags in finished jobs.

BLINDING (pre-stated 2026-10-11, spec Section 7): this prints operational
quantities only. It never reads a score, action, forecast, outcome or P/L, and
never computes a gate statistic. The ignition count is the pre-stated
operational flag (reported, never gating), shown as one total.

    .venv-shiu/bin/python repro/mushroom_body/monitor_sweep.py
    ssh flyshi 'cd ~/flyshi-research && .venv-shiu/bin/python repro/mushroom_body/monitor_sweep.py'
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from launch_first_learning_parallel import _meminfo  # noqa: E402
import run_synthetic_market_experiment as runner  # noqa: E402  (no Brian2 at import)

RESULTS_BASE = HERE / "results"
RATE_WINDOW_H = 6.0
STALL_MINUTES = 15.0
PROGRESS_RE = re.compile(r"^\[progress\] (\S+) run (\d+)/(\d+) t=([\d.]+) maxrss_gb=([\d.]+)")
JOB_ARG_RE = re.compile(r"run_synthetic_market_experiment\.py.*--job (\S+)")


@dataclass
class JobLog:
    runs: int = 0           # runs completed in the current (latest) attempt
    last_t: Optional[float] = None
    maxrss_gb: float = 0.0  # peak of the current attempt
    peak_gb: float = 0.0    # peak of any attempt
    attempts: int = 0
    times: tuple = ()       # completion times of every run, all attempts
    last_line: str = ""


def read_log(path: Path) -> JobLog:
    out = JobLog()
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return out
    times = []
    for line in text.splitlines():
        if line.startswith(runner.START_TAG):
            out.attempts += 1
            out.runs, out.maxrss_gb = 0, 0.0
        m = PROGRESS_RE.match(line)
        if m:
            out.runs = int(m.group(2))
            out.last_t = float(m.group(4))
            out.maxrss_gb = max(out.maxrss_gb, float(m.group(5)))
            out.peak_gb = max(out.peak_gb, out.maxrss_gb)
            times.append(out.last_t)
        if line.strip():
            out.last_line = line.strip()
    out.times = tuple(times)
    return out


def running_workers() -> Dict[str, dict]:
    """job id -> {pid, rss_gb} for every live sweep worker (ps works on Linux and macOS)."""
    try:
        text = subprocess.run(["ps", "-eo", "pid=,rss=,args="], capture_output=True, text=True,
                              timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    out = {}
    for line in text.splitlines():
        m = JOB_ARG_RE.search(line)
        if m:
            pid, rss = line.split()[:2]
            out[m.group(1)] = {"pid": int(pid), "rss_gb": int(rss) / 1024 ** 2}
    return out


def launcher_state(lock: Path) -> str:
    try:
        pid = int(lock.read_text().strip())
    except (OSError, ValueError):
        return "NOT RUNNING (no lock file)"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return f"NOT RUNNING (stale lock, pid {pid})"
    except PermissionError:
        pass
    return f"running (pid {pid})"


def ignition_flags(output: dict) -> int:
    """Decisions in one finished job with an ignited framing (train and test)."""
    return sum(sm._ignited(r) for split in ("train", "test") for r in output.get(split, []))


def status(results_base: Path = RESULTS_BASE, now: Optional[float] = None,
           workers: Optional[Dict[str, dict]] = None,
           meminfo: Optional[Dict[str, float]] = None) -> List[str]:
    now = time.time() if now is None else now
    cfg = sm.SyntheticConfig()
    jobs = sm.run_order(sm.plan_jobs(cfg))
    paths = runner.Paths(sm.results_dir_for(results_base, cfg))
    workers = running_workers() if workers is None else workers

    done, damaged, running, failed, todo = [], [], [], [], []
    ignited_decisions, ignited_jobs = 0, []
    logs = {j.id: read_log(paths.log(j)) for j in jobs}
    for j in jobs:
        out_file = paths.output(j)
        output = runner.read_output(out_file)
        if output is not None:
            done.append(j)
            n = ignition_flags(output)
            if n:
                ignited_decisions += n
                ignited_jobs.append(j.id)
        elif j.id in workers:
            if out_file.exists():
                damaged.append(j)
            running.append(j)
        else:
            if out_file.exists():
                damaged.append(j)
            (failed if paths.log(j).exists() else todo).append(j)

    total_runs = sum(j.n_runs for j in jobs)
    runs_done = sum(j.n_runs for j in done)
    runs_running = sum(min(logs[j.id].runs, j.n_runs) for j in running)
    since = now - RATE_WINDOW_H * 3600
    recent = sum(1 for log in logs.values() for t in log.times if t >= since)
    first = min((t for log in logs.values() for t in log.times), default=None)
    window_h = min(RATE_WINDOW_H, (now - first) / 3600) if first else 0.0
    rate = recent / window_h if window_h > 0.05 else None

    def phase_count(group, phase):
        return sum(1 for j in group if j.kind == "condition" and sm.phase_of(j.condition) == phase)

    lines = [f"sweep {cfg.config_hash()}  {dt.datetime.fromtimestamp(now, dt.timezone.utc):%Y-%m-%d %H:%M} UTC  "
             f"launcher: {launcher_state(paths.logs / 'launcher.lock')}",
             f"jobs: {len(done)} done / {len(running)} running / "
             f"{len(jobs) - len(done) - len(running)} remaining of {len(jobs)}"]
    for phase, arms in sm.RUN_PHASES.items():
        n = sum(1 for j in jobs if j.kind == "condition" and sm.phase_of(j.condition) == phase)
        lines.append(f"  phase {phase} ({', '.join(arms)}): {phase_count(done, phase)}/{n} done, "
                     f"{phase_count(running, phase)} running")
    lines.append(f"runs: {runs_done:,} in finished jobs + {runs_running:,} in running jobs "
                 f"= {runs_done + runs_running:,} of {total_runs:,}")
    if rate:
        remaining = total_runs - runs_done - runs_running
        p1_left = sum(j.n_runs for j in jobs if j.kind == "condition" and sm.phase_of(j.condition) == 1
                      and j not in done) - sum(min(logs[j.id].runs, j.n_runs) for j in running
                                                if sm.phase_of(j.condition) == 1)
        eta = lambda runs: dt.datetime.fromtimestamp(now + runs / rate * 3600, dt.timezone.utc)  # noqa: E731
        lines.append(f"rate: {rate:.0f} runs/h over the last {window_h:.1f} h")
        lines.append(f"ETA at this rate: phase 1 {eta(max(p1_left, 0)):%Y-%m-%d %H:%M} UTC, "
                     f"all {eta(remaining):%Y-%m-%d %H:%M} UTC "
                     "(the last wave's tail is not modelled; server_eta.py schedules it)")
    else:
        lines.append("rate: no progress lines yet")
    stalled = [j.id for j in running
               if logs[j.id].last_t is not None and now - logs[j.id].last_t > STALL_MINUTES * 60]
    for j in running:
        w, log = workers[j.id], logs[j.id]
        lines.append(f"  running {j.id}: run {log.runs}/{j.n_runs}, rss {w['rss_gb']:.2f} GB, "
                     f"peak {log.maxrss_gb:.2f} GB, attempt {max(log.attempts, 1)}"
                     + ("  STALLED?" if j.id in stalled else ""))
    if failed:
        lines.append(f"FAILED or interrupted (log exists, no job file, not running): {len(failed)}")
        for j in failed[:10]:
            lines.append(f"  {j.id}: last log line: {logs[j.id].last_line[:160]}")
        lines.append("  re-run the launcher in tmux: finished jobs are skipped, these restart from 0")
    else:
        lines.append("failed: none")
    if damaged:
        lines.append(f"DAMAGED job files (exist, not whole JSON; will be re-run): "
                     f"{', '.join(j.id for j in damaged)}")
    try:
        m = _meminfo() if meminfo is None else meminfo
        lines.append(f"memory: {m['MemTotal']:.1f} GB total, {m['MemAvailable']:.1f} GB available"
                     + (f"; workers {sum(w['rss_gb'] for w in workers.values()):.1f} GB "
                        f"(largest {max(w['rss_gb'] for w in workers.values()):.2f} GB)" if workers else ""))
    except (OSError, KeyError, ValueError):
        lines.append("memory: /proc/meminfo not available here")
    peaks = [logs[j.id].peak_gb for j in jobs if logs[j.id].peak_gb]
    if peaks:
        lines.append(f"peak memory of any job so far: {max(peaks):.2f} GB")
    disk = shutil.disk_usage(results_base if results_base.exists() else Path.home())
    lines.append(f"disk: {disk.free / 1024 ** 3:.1f} GB free")
    lines.append(f"ignition (operational flag, never gating): {ignited_decisions} decisions with an "
                 f"ignited framing in {len(ignited_jobs)} of {len(done)} finished jobs"
                 + (f"; e.g. {', '.join(ignited_jobs[:3])}" if ignited_jobs else ""))
    return lines


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--results-base", type=Path, default=RESULTS_BASE)
    args = p.parse_args(argv)
    print("\n".join(status(args.results_base)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
