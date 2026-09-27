#!/usr/bin/env python3
"""Retrospective rate-weighted recruitment measure, applied to saved results.

Reads existing per-(condition, seed) result files only. Runs no simulation and
loads no connectome. Computes, alongside the existing binary >1% active-fraction
ignition label (unchanged, not replaced), the mean rate among the non-stimulated
KCs that ARE active (>0.5 Hz) -- ``recruited_kc_mean_rate_hz``. This distinguishes
a weak, low-rate recruitment event from a strong, saturating one, which the binary
label cannot: both count as "ignited" once the active fraction exceeds 1%,
whatever the rate of the recruited cells.

Definition (fixed here, for this retrospective pass):

    N               = non-stimulated Kenyon cells (population_ids minus
                       stimulated_kc_ids)
    active(N)       = {i in N : rate_i > 0.5 Hz}          (unchanged threshold)
    active_fraction = |active(N)| / |N|                    (unchanged; existing
                                                             ignition label
                                                             thresholds this >1%)
    recruited_kc_mean_rate_hz   = mean(rate_i for i in active(N))
                                   -- null if active(N) is empty
    recruited_kc_median_rate_hz = median(rate_i for i in active(N))
                                   -- null if active(N) is empty

``recruited_kc_mean_rate_hz`` is null, not zero, when nothing is recruited: zero
recruited KCs is not the same claim as recruited KCs firing at 0 Hz, and
conflating the two would hide exactly the distinction this measure exists to
make.

Usage: python analyze_recruitment_intensity.py [--json OUT.json]
Prints a table to stdout; writes the full per-seed data to JSON if --json is
given. This script is analysis-only: it is not part of any pre-stated protocol,
produces no verdict, and does not alter any existing result or summary file.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
ACTIVE_HZ = 0.5  # matches POPULATIONS["kenyon_cells"].active_hz elsewhere
IGNITION_SPREAD_FRACTION = 0.01  # unchanged; the existing binary label's threshold

# (family, condition, seeds) -- the complete set of saved per-seed files as of
# 2026-09-27. Discovered from repro/mushroom_body/results/*.json; not hardcoded
# from any doc so a missing/extra file is visible rather than silently skipped.
SEEDS = (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)

POPULATION_SCALING_CONDITIONS = (
    "ladder_100", "ladder_200", "ladder_300", "ladder_400", "ladder_500",
    "anchor_100at150", "drive_matched_500at30",
)
LEFT_LADDER_CONDITIONS = (
    "left_ladder_100", "left_ladder_200", "left_ladder_300", "left_ladder_500",
)


def population_scaling_path(condition: str, seed: int) -> Path:
    return RESULTS_DIR / f"population_scaling_{condition}_seed_{seed}.json"


def left_ladder_path(condition: str, seed: int) -> Path:
    return RESULTS_DIR / f"left_only_scaling_{condition}_seed_{seed}.json"


def left_only_pool_path(seed: int) -> Path:
    return RESULTS_DIR / f"left_only_pool_seed_{seed}.json"


def recruitment_stats(payload: dict) -> Dict[str, Optional[float]]:
    kc_ids = payload["population_ids"]["kenyon_cells"]
    kc_rates = payload["rates_hz"]["kenyon_cells"]
    stimulated = set(int(i) for i in payload["stimulated_kc_ids"])
    non_stim_rates = [r for i, r in zip(kc_ids, kc_rates) if int(i) not in stimulated]
    n_non_stim = len(non_stim_rates)
    active = [r for r in non_stim_rates if r > ACTIVE_HZ]
    active_fraction = len(active) / n_non_stim if n_non_stim else float("nan")
    return {
        "n_non_stimulated": n_non_stim,
        "n_active": len(active),
        "active_fraction": active_fraction,
        "ignited": active_fraction > IGNITION_SPREAD_FRACTION,
        "recruited_kc_mean_rate_hz": st.mean(active) if active else None,
        "recruited_kc_median_rate_hz": st.median(active) if active else None,
        "recruited_kc_max_rate_hz": max(active) if active else None,
    }


def load_family(path_fn, conditions, seeds=SEEDS) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for condition in conditions:
        rows = []
        for seed in seeds:
            path = path_fn(condition, seed)
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            row = {"condition": condition, "seed": seed}
            row.update(recruitment_stats(payload))
            rows.append(row)
        if rows:
            out[condition] = rows
    return out


def load_left_only_pool(seeds=SEEDS) -> List[dict]:
    rows = []
    for seed in seeds:
        path = left_only_pool_path(seed)
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        row = {"condition": "left_only_pool_150hz", "seed": seed}
        row.update(recruitment_stats(payload))
        rows.append(row)
    return rows


def condition_summary(rows: List[dict]) -> dict:
    ignited = sum(1 for r in rows if r["ignited"])
    recruited_rates = [r["recruited_kc_mean_rate_hz"] for r in rows
                       if r["recruited_kc_mean_rate_hz"] is not None]
    return {
        "n_seeds": len(rows),
        "ignited_count": ignited,
        "active_fraction_per_seed": [r["active_fraction"] for r in rows],
        "recruited_kc_mean_rate_hz_per_seed": [r["recruited_kc_mean_rate_hz"] for r in rows],
        "recruited_kc_mean_rate_hz_mean_over_ignited_seeds":
            (st.mean(recruited_rates) if recruited_rates else None),
    }


def fmt(x) -> str:
    if x is None:
        return "   --  "
    return f"{x:7.2f}"


def print_table(title: str, families: Dict[str, List[dict]]) -> None:
    print(f"\n=== {title} ===")
    header = f"  {'condition':28s} {'seed':>10s}  active%  ignited  recruited_mean_Hz  recruited_median_Hz"
    print(header)
    for condition, rows in families.items():
        for r in rows:
            print(f"  {condition:28s} {r['seed']:>10d}  "
                  f"{r['active_fraction']*100:6.1f}%  {'yes' if r['ignited'] else 'no ':7s}  "
                  f"{fmt(r['recruited_kc_mean_rate_hz'])}  {fmt(r['recruited_kc_median_rate_hz'])}")
        s = condition_summary(rows)
        mean_recruited = s["recruited_kc_mean_rate_hz_mean_over_ignited_seeds"]
        print(f"  {condition:28s} {'mean':>10s}  "
              f"{'':7s}  {s['ignited_count']}/{s['n_seeds']} ignited      "
              f"{fmt(mean_recruited)}  (mean over ignited seeds only)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--json", type=Path, default=None)
    args = p.parse_args()

    population_scaling = load_family(population_scaling_path, POPULATION_SCALING_CONDITIONS)
    left_ladder = load_family(left_ladder_path, LEFT_LADDER_CONDITIONS)
    left_only_pool_rows = load_left_only_pool()

    print_table("Bilateral population-scaling ladder (existing conditions)", population_scaling)
    print_table("Left-only population-scaling ladder", left_ladder)
    if left_only_pool_rows:
        print_table("Left-only pool diagnostic (150 Hz)",
                     {"left_only_pool_150hz": left_only_pool_rows})

    if args.json:
        payload = {
            "note": "analysis-only; not a validation; no verdict; no simulation run",
            "active_threshold_hz": ACTIVE_HZ,
            "ignition_spread_fraction": IGNITION_SPREAD_FRACTION,
            "population_scaling": {c: condition_summary(r) | {"per_seed": r}
                                    for c, r in population_scaling.items()},
            "left_ladder": {c: condition_summary(r) | {"per_seed": r}
                             for c, r in left_ladder.items()},
            "left_only_pool_150hz": (condition_summary(left_only_pool_rows) | {"per_seed": left_only_pool_rows})
                                     if left_only_pool_rows else None,
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=1))
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
