#!/usr/bin/env python3
"""From measured calibration figures: the best process count, finish dates and cost.

Reads a ``calibrate_server.py`` result (default: the newest file in
results/server_calibration/). For every measured N it checks that N processes fit
in memory under the launcher's rule, using the measured peak per process plus a
margin, then schedules the remaining sweep jobs exactly as the launcher does
(``estimate_makespan``, phase 1 first) at that N's measured seconds per run plus its
measured build time. Prints, per N and for the best N: when phase 1 and phase 2
finish, and what each costs at --price-per-hour.

"Best" = the most runs per hour among the N that fit in memory; an N within 2% of
the best throughput but with fewer processes is preferred (less memory risk).
Only measured N are candidates: throughput between them is not interpolated.

Simulates nothing. Safe anywhere; reads only the calibration file and which job
files exist.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path
from typing import List, Optional, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from launch_first_learning_parallel import estimate_makespan  # noqa: E402

CALIBRATION_DIR = HERE / "results" / "server_calibration"
RESULTS_BASE = HERE / "results"
PRICE_PER_HOUR = 0.266  # USD, CCX33, as given 2026-10-11; check the Hetzner console
MEMORY_MARGIN = 1.15     # budget per process = measured peak x this, rounded up to 0.1 GB
TIE_FRACTION = 0.02


def newest_calibration(directory: Path = CALIBRATION_DIR) -> Path:
    files = sorted(directory.glob("calibration_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(f"no calibration file in {directory}; run calibrate_server.py first")
    return files[-1]


def gb_budget(peak_gb: float, margin: float = MEMORY_MARGIN) -> float:
    return math.ceil(peak_gb * margin * 10) / 10


def fits(n: int, peak_gb: float, available_gb: float, headroom_gb: float) -> bool:
    """The launcher's rule: floor((available - headroom) / GB per process) >= n."""
    return math.floor((available_gb - headroom_gb) / gb_budget(peak_gb)) >= n


def phase_jobs(jobs: Sequence[sm.Job], phase: int) -> List[sm.Job]:
    return [j for j in jobs if j.kind == "condition" and sm.phase_of(j.condition) == phase]


def plan(level: dict, jobs: Sequence[sm.Job], done: Sequence[str], price: float) -> dict:
    """Hours (from now) until phase 1 and phase 2 are complete at this level's N."""
    n = level["procs_run"]
    minutes = level["seconds_per_run_mean"] / 60.0
    first = level.get("first_run_done_after_s_max") or level["seconds_per_run_mean"]
    build_minutes = max(0.0, first - level["seconds_per_run_mean"]) / 60.0
    p1 = phase_jobs(jobs, 1)
    # Phase 1 jobs all start before any phase 2 job and every job is equally long,
    # so phase 1 ends when it would have ended alone.
    h1 = estimate_makespan(p1, n, minutes, build_minutes, done) / 60.0
    total = estimate_makespan(jobs, n, minutes, build_minutes, done) / 60.0
    return {"procs": n, "seconds_per_run": level["seconds_per_run_mean"],
            "runs_per_hour": level["runs_per_hour"], "build_minutes": build_minutes,
            "phase1_hours": h1, "total_hours": total,
            "phase1_cost": h1 * price, "phase2_cost": (total - h1) * price,
            "total_cost": total * price}


def choose(plans: Sequence[dict]) -> Optional[dict]:
    if not plans:
        return None
    top = max(p["runs_per_hour"] for p in plans)
    near = [p for p in plans if p["runs_per_hour"] >= top * (1 - TIE_FRACTION)]
    return min(near, key=lambda p: p["procs"])


def report(calibration: dict, done: Sequence[str], price: float, start: dt.datetime,
           budget: Optional[float] = None) -> List[str]:
    cfg = sm.SyntheticConfig()
    if calibration.get("config_hash") not in (None, cfg.config_hash()):
        raise SystemExit(f"calibration was for config {calibration['config_hash']}, "
                         f"this sweep is {cfg.config_hash()}")
    jobs = sm.run_order(sm.plan_jobs(cfg))
    machine = calibration["machine"]
    lines = [f"calibration: {calibration['environment'].get('hostname')}, "
             f"{machine['total_gb']:.1f} GB RAM, {machine['available_gb_at_start']:.1f} GB available, "
             f"{machine['logical_cpus']} logical CPUs; price ${price:g}/h; start {start:%Y-%m-%d %H:%M} UTC",
             f"jobs: {len(jobs)} ({len(done)} already done); phase 1 = {len(phase_jobs(jobs, 1))} "
             f"(profit, learning_off), phase 2 = {len(phase_jobs(jobs, 2))} (accuracy, profit_drift_off)",
             "",
             "| N | s/run | runs/h | peak GB/proc | fits in RAM | phase 1 done | all done | "
             "phase 1 cost | phase 2 cost | total |",
             "|---:|---:|---:|---:|---|---|---|---:|---:|---:|"]
    candidates = []
    for level in calibration["levels"]:
        usable = level.get("complete") and level.get("seconds_per_run_mean") and level.get("peak_rss_gb_max")
        if not usable:
            lines.append(f"| {level['procs_asked']} | incomplete measurement ({level.get('note')}) "
                         "| | | | | | | | |")
            continue
        ok = fits(level["procs_run"], level["peak_rss_gb_max"], machine["available_gb_at_start"],
                  machine["headroom_gb"])
        p = plan(level, jobs, done, price)
        p["fits"], p["peak_gb"] = ok, level["peak_rss_gb_max"]
        if ok:
            candidates.append(p)
        lines.append(
            f"| {p['procs']} | {p['seconds_per_run']:.1f} | {p['runs_per_hour']:.0f} | {p['peak_gb']:.2f} | "
            f"{'yes' if ok else 'NO'} | {_date(start, p['phase1_hours'])} | {_date(start, p['total_hours'])} | "
            f"${p['phase1_cost']:.0f} | ${p['phase2_cost']:.0f} | ${p['total_cost']:.0f} |")
    best = choose(candidates)
    lines.append("")
    if best is None:
        lines.append("NO measured process count fits in memory with a usable measurement. "
                     "Re-run calibrate_server.py with smaller --procs.")
        return lines
    measured = sorted(lv["procs_run"] for lv in calibration["levels"])
    lines += [
        f"BEST: N = {best['procs']} processes, {best['runs_per_hour']:.0f} runs/h "
        f"({best['seconds_per_run']:.1f} s per run per process)",
        f"  phase 1 (gate arms) complete: {_date(start, best['phase1_hours'])} "
        f"(+{best['phase1_hours']:.0f} h), cost ${best['phase1_cost']:.2f}",
        f"  phase 2 complete (whole sweep): {_date(start, best['total_hours'])} "
        f"(+{best['total_hours']:.0f} h), phase 2 cost ${best['phase2_cost']:.2f}",
        f"  total ${best['total_cost']:.2f} at ${price:g}/h, server time only "
        "(setup, calibration and copying not included)",
    ]
    if budget is not None:
        lines.append(f"  budget ${budget:g}: {'within' if best['total_cost'] <= budget else 'EXCEEDED'}, "
                     f"${budget - best['total_cost']:.2f} left")
    if best["procs"] == max(measured):
        lines.append(f"  note: the best N is the largest measured; throughput above {best['procs']} "
                     "was not measured.")
    lines += [
        "",
        "launcher command (inside tmux):",
        f"  .venv-shiu/bin/python repro/mushroom_body/launch_synthetic_market_parallel.py "
        f"--max-procs {best['procs']} --gb-per-proc {gb_budget(best['peak_gb']):g}",
        f"  (--gb-per-proc = measured peak {best['peak_gb']:.2f} GB x {MEMORY_MARGIN}; add --dry-run "
        "first and check it reports the same process count)",
    ]
    return lines


def _date(start: dt.datetime, hours: float) -> str:
    return (start + dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")


def done_jobs(results_base: Path) -> List[str]:
    import run_synthetic_market_experiment as runner
    cfg = sm.SyntheticConfig()
    paths = runner.Paths(sm.results_dir_for(results_base, cfg))
    return [j.id for j in sm.plan_jobs(cfg) if paths.done(j)]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--calibration", type=Path, default=None,
                   help="calibrate_server.py output (default: newest in results/server_calibration).")
    p.add_argument("--price-per-hour", type=float, default=PRICE_PER_HOUR)
    p.add_argument("--budget", type=float, default=None, help="Optional total budget in USD.")
    p.add_argument("--start", default=None,
                   help="Start time, ISO 8601 UTC (default: now).")
    p.add_argument("--results-base", type=Path, default=RESULTS_BASE,
                   help="Count jobs already done here (default: the real results directory).")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    path = args.calibration or newest_calibration()
    calibration = json.loads(path.read_text())
    start = (dt.datetime.fromisoformat(args.start) if args.start
             else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, second=0, microsecond=0))
    print(f"from {path}")
    print("\n".join(report(calibration, done_jobs(args.results_base), args.price_per_hour,
                           start, args.budget)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
