#!/usr/bin/env python3
"""Left-only pool diagnostic: hemisphere or pool identity?

Pre-stated protocol: docs/design/left-only-pool-diagnostic.md, written before this
code and before any run.

DIAGNOSTIC, NOT A VALIDATION. It measures; it does not judge. No pass criterion,
no verdict field; PASS/FAIL and ACCEPTED / USABLE RANGE / FAIL are deliberately
absent, as they belong to validations.

One stimulus: the encoder's own drawing procedure restricted to LEFT-hemisphere
Kenyon cells, 100 KCs at 150 Hz (15,000 Hz total drive) - the same count, rate and
drive as the bilateral ``anchor_100at150`` condition, which ignited in 4 of 6
runs, and as the historical cue-A cell, which stayed contained in 5 of 5.

Six seeds = 6 simulations. Every run records MBON, Kenyon cell, APL, PAM and PPL1
rates, as the population-scaling runner does.

Running without --analyze-only or --dry-run executes 6 real Brian2 simulations and
loads the connectome. Importing this file, --dry-run and --analyze-only do neither.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling runner; imports no Brian2 at module level

from flyshi_research.learning import graded_check as gc  # noqa: E402
from flyshi_research.learning.encoder import KCEncoder  # noqa: E402
from flyshi_research.learning.readout import circuit_score, load_sign_table  # noqa: E402
from run_population_scaling_diagnostic import (  # noqa: E402
    ACTIVE_HZ,
    POPULATIONS,
    SECONDS_PER_BUILD,
    SECONDS_PER_SIMULATION,
)

RESULTS_DIR = HERE / "results"
IDS_PATH = HERE / "neuron_ids_783.json"

# ---- fixed by the pre-statement (spec section 2) ------------------------------ #
POOL_NAME = "recent_change"  # the population-scaling ladder's first pool
POOL_SIDE = "left"
RATE_HZ = 150.0
SEEDS: Tuple[int, ...] = (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
DURATION_MS = 1000.0
TRIALS = 5
SIGN_TABLE = "circuit_80"
AGGREGATION = "type_mean"
#: reporting label only, never a pass criterion (spec section 3)
IGNITION_SPREAD_FRACTION = 0.01
#: the bilateral condition this is compared against, if its files are present
BILATERAL_CONDITION = "anchor_100at150"


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_left_only_pool_diagnostic.py"
    )
    p = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog=f"Exact pre-stated run:\n  {command}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--analyze-only", action="store_true",
                   help="Summarise existing files; never simulates.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan and the runtime estimate; never simulates.")
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--ids", type=Path, default=IDS_PATH)
    return p


def output_path(seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"left_only_pool_seed_{seed}.json"


def summary_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "left_only_pool_summary.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, separators=(",", ":")))
    partial.replace(path)


def missing_seeds(results_dir: Path = RESULTS_DIR) -> List[int]:
    return [seed for seed in SEEDS if not output_path(seed, results_dir).exists()]


# --------------------------------------------------------------------------- #
# the stimulus (pure data; no Brian2, no connectome)
# --------------------------------------------------------------------------- #
def kc_side_map(ids_path: Path = IDS_PATH) -> Dict[int, str]:
    records = json.loads(Path(ids_path).read_text())["kenyon_cells"]["records"]
    return {int(r["root_id"]): str(r["side"]) for r in records}


def left_kc_ids(ids_path: Path = IDS_PATH) -> List[int]:
    return sorted(i for i, side in kc_side_map(ids_path).items() if side == POOL_SIDE)


def left_only_pool(ids_path: Path = IDS_PATH) -> List[int]:
    """The encoder's own pool, drawn from left-hemisphere KCs only.

    Aborts unless the result is exactly 100 KCs, every one annotated left: the
    whole point of this run is that the pool is one-sided.
    """
    sides = kc_side_map(ids_path)
    encoder = KCEncoder(left_kc_ids(ids_path))
    pool = [int(i) for i in encoder.pools[POOL_NAME]]
    if len(pool) != 100:
        raise RuntimeError(f"expected a 100-KC pool, drew {len(pool)}")
    wrong = [i for i in pool if sides.get(i) != POOL_SIDE]
    if wrong:
        raise RuntimeError(f"{len(wrong)} pool KCs are not {POOL_SIDE}-hemisphere")
    return sorted(pool)


def stimulus(ids_path: Path = IDS_PATH) -> Dict[int, float]:
    return {kc_id: RATE_HZ for kc_id in left_only_pool(ids_path)}


# --------------------------------------------------------------------------- #
# simulation (the only part that constructs the model)
# --------------------------------------------------------------------------- #
def simulate_missing(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
                     log: Callable[[str], None] = print) -> None:
    todo = missing_seeds(results_dir)
    for seed in SEEDS:
        if seed not in todo:
            log(f"Output exists, skipping: {output_path(seed, results_dir).name}")
    if not todo:
        return

    from run_population_scaling_diagnostic import _build_population_simulator

    rates = stimulus(ids_path)
    stimulated = sorted(rates)
    sim = _build_population_simulator()
    for seed in todo:
        populations = sim.present_populations(rates, seed, DURATION_MS, TRIALS)
        _write_json(
            output_path(seed, results_dir),
            {
                "condition": "left_only_100at150",
                "pool_name": POOL_NAME,
                "pool_side": POOL_SIDE,
                "n_kcs_driven": len(stimulated),
                "per_kc_rate_hz": RATE_HZ,
                "total_drive_hz": len(stimulated) * RATE_HZ,
                "stimulated_kc_ids": stimulated,
                "mbon_labels": list(sim.mbon_type_labels),
                "population_ids": {p: list(sim.population_ids[p]) for p in POPULATIONS},
                "rates_hz": {p: np.asarray(v, dtype=float).tolist()
                             for p, v in populations.items()},
                "seed": seed,
                "duration_ms": DURATION_MS,
                "trials": TRIALS,
            },
        )
        log(f"left-only pool ({len(stimulated)} KCs at {RATE_HZ:g} Hz), seed {seed}: "
            f"wrote {output_path(seed, results_dir).name}")


# --------------------------------------------------------------------------- #
# measurement (no verdict: this is a diagnostic)
# --------------------------------------------------------------------------- #
def mean_pairwise_distance(vectors: Sequence[np.ndarray]) -> float:
    return float(np.mean([gc.euclidean(a, b) for a, b in combinations(vectors, 2)]))


def _spread(payload: Mapping, sides: Optional[Mapping[int, str]] = None) -> Dict[str, float]:
    """Non-stimulated KC active fraction, overall and per hemisphere."""
    kc_ids = [int(i) for i in payload["population_ids"]["kenyon_cells"]]
    rate = np.asarray(payload["rates_hz"]["kenyon_cells"], dtype=float)
    stimulated = set(int(i) for i in payload["stimulated_kc_ids"])
    free = np.array([i not in stimulated for i in kc_ids])
    out = {"overall": float((rate[free] > ACTIVE_HZ).mean())}
    if sides:
        for hemisphere in ("left", "right"):
            mask = np.array([(i not in stimulated) and sides.get(i) == hemisphere
                             for i in kc_ids])
            out[hemisphere] = float((rate[mask] > ACTIVE_HZ).mean()) if mask.any() else float("nan")
    return out


def statistics(payloads: Sequence[Mapping], sides: Optional[Mapping[int, str]] = None) -> dict:
    table = load_sign_table(SIGN_TABLE)
    labels = payloads[0]["mbon_labels"]
    mbon = [np.asarray(p["rates_hz"]["mbons"], dtype=float) for p in payloads]
    kc = [np.asarray(p["rates_hz"]["kenyon_cells"], dtype=float) for p in payloads]
    apl = [np.asarray(p["rates_hz"]["apl_neurons"], dtype=float) for p in payloads]
    pam = [np.asarray(p["rates_hz"]["pam_dopamine_neurons"], dtype=float) for p in payloads]
    ppl1 = [np.asarray(p["rates_hz"]["ppl1_dopamine_neurons"], dtype=float) for p in payloads]

    scores = [circuit_score(v, labels, table, AGGREGATION).score for v in mbon]
    spreads = [_spread(p, sides) for p in payloads]
    kc_ids = [int(i) for i in payloads[0]["population_ids"]["kenyon_cells"]]
    stimulated = set(int(i) for i in payloads[0]["stimulated_kc_ids"])
    is_stim = np.array([i in stimulated for i in kc_ids])
    ignited = [s["overall"] > IGNITION_SPREAD_FRACTION for s in spreads]

    return {
        "n_seeds": len(payloads),
        "n_kcs_driven": payloads[0]["n_kcs_driven"],
        "per_kc_rate_hz": payloads[0]["per_kc_rate_hz"],
        "total_drive_hz": payloads[0]["total_drive_hz"],
        "score_per_seed": [float(s) for s in scores],
        "score_mean": float(np.mean(scores)),
        "score_sd": float(np.std(scores, ddof=1)),
        "mbon_vector_distance_hz": mean_pairwise_distance(mbon),
        "active_mbons_per_seed": [int((v > ACTIVE_HZ).sum()) for v in mbon],
        "active_mbons": float(np.mean([(v > ACTIVE_HZ).sum() for v in mbon])),
        "mbon_mean_rate_hz": float(np.mean(mbon)),
        "stimulated_kc_mean_rate_hz": float(np.mean([v[is_stim].mean() for v in kc])),
        "nonstimulated_kc_active_fraction_per_seed": [s["overall"] for s in spreads],
        "nonstimulated_kc_active_fraction": float(np.mean([s["overall"] for s in spreads])),
        "nonstimulated_kc_active_fraction_by_side_per_seed": [
            {k: v for k, v in s.items() if k != "overall"} for s in spreads],
        "nonstimulated_kc_mean_rate_hz": float(np.mean([v[~is_stim].mean() for v in kc])),
        "apl_mean_rate_hz": float(np.mean(apl)),
        "apl_per_seed_mean_hz": [float(v.mean()) for v in apl],
        "pam_mean_rate_hz": float(np.mean(pam)),
        "active_pam": float(np.mean([(v > ACTIVE_HZ).sum() for v in pam])),
        "ppl1_mean_rate_hz": float(np.mean(ppl1)),
        "active_ppl1": float(np.mean([(v > ACTIVE_HZ).sum() for v in ppl1])),
        "ignited_per_seed": ignited,
        "ignited_runs": int(sum(ignited)),
        "ignition_label_note": (
            f"a run is labelled ignited when its non-stimulated KC active fraction "
            f"exceeds {IGNITION_SPREAD_FRACTION:.0%}; a reporting label, not a pass criterion"
        ),
    }


def bilateral_comparison(results_dir: Path, sides: Optional[Mapping[int, str]]) -> Optional[dict]:
    """The same statistics for ``anchor_100at150``, when those files are present."""
    paths = [results_dir / f"population_scaling_{BILATERAL_CONDITION}_seed_{seed}.json"
             for seed in SEEDS]
    if not all(p.exists() for p in paths):
        return None
    payloads = [json.loads(p.read_text()) for p in paths]
    stats = statistics(payloads, sides)
    pool_sides = {}
    if sides:
        for kc_id in payloads[0]["stimulated_kc_ids"]:
            key = sides.get(int(kc_id), "unknown")
            pool_sides[key] = pool_sides.get(key, 0) + 1
    return {"condition": BILATERAL_CONDITION, "pool_side_counts": pool_sides, **stats}


def summarise(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
              log: Callable[[str], None] = print) -> Optional[dict]:
    missing = missing_seeds(results_dir)
    if missing:
        log(f"Cannot summarise: missing {len(missing)} of {len(SEEDS)} seed results")
        return None
    payloads = [json.loads(output_path(seed, results_dir).read_text()) for seed in SEEDS]
    labels = payloads[0]["mbon_labels"]
    if any(p["mbon_labels"] != labels for p in payloads):
        raise ValueError("MBON label order differs between seed files")
    sides = kc_side_map(ids_path) if Path(ids_path).exists() else None
    left = statistics(payloads, sides)
    bilateral = bilateral_comparison(results_dir, sides)

    summary = {
        "prestated_diagnostic": True,
        "is_a_validation": False,
        "has_pass_criterion": False,
        "spec": "docs/design/left-only-pool-diagnostic.md",
        "seeds": list(SEEDS),
        "duration_ms": DURATION_MS,
        "trials": TRIALS,
        "left_only": {"condition": "left_only_100at150", "pool_name": POOL_NAME,
                      "pool_side": POOL_SIDE, **left},
        "bilateral_reference": bilateral,
        "comparison_note": (
            "Same count, rate and total drive as the bilateral pool. This pool is "
            "left-only AND a different draw, so hemisphere and pool identity are not "
            "separated by this run alone (spec 4). Six runs estimate an ignition "
            "count, not a rate."
        ),
        "historical_reference_note": (
            "The historical cue-A cell is a second left-only point at this drive "
            "(0 of 5 runs spread, d_AA = 5.10 Hz), but used a different pool and path "
            "and saved no KC, APL, PAM or PPL1 rates."
        ),
    }
    _write_json(summary_path(results_dir), summary)

    log("=== Left-only pool diagnostic (MEASUREMENT; no verdict, no pass criterion) ===")
    log(f"pool: {POOL_NAME}, {POOL_SIDE}-hemisphere only, {left['n_kcs_driven']} KCs at "
        f"{left['per_kc_rate_hz']:g} Hz ({left['total_drive_hz']:,.0f} Hz total drive)")
    log(f"{'seed':>10}{'spread':>9}{'APL Hz':>9}{'actMBON':>9}{'score':>9}  state")
    for index, seed in enumerate(SEEDS):
        log(f"{seed:>10}{100 * left['nonstimulated_kc_active_fraction_per_seed'][index]:>8.1f}%"
            f"{left['apl_per_seed_mean_hz'][index]:>9.1f}"
            f"{left['active_mbons_per_seed'][index]:>9d}"
            f"{left['score_per_seed'][index]:>9.1f}  "
            f"{'ignited' if left['ignited_per_seed'][index] else 'contained'}")
    log(f"left-only: {left['ignited_runs']}/{len(SEEDS)} runs ignited; "
        f"score SD {left['score_sd']:.2f} Hz")
    if bilateral:
        log(f"bilateral {BILATERAL_CONDITION} (same drive): "
            f"{bilateral['ignited_runs']}/{len(SEEDS)} ignited; "
            f"score SD {bilateral['score_sd']:.2f} Hz; pool {bilateral['pool_side_counts']}")
    else:
        log(f"bilateral reference absent ({BILATERAL_CONDITION} files not found)")
    log(f"Wrote {summary_path(results_dir).name}")
    return summary


# --------------------------------------------------------------------------- #
# dry run
# --------------------------------------------------------------------------- #
def dry_run(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
            log: Callable[[str], None] = print) -> int:
    todo = missing_seeds(results_dir)
    seconds = len(todo) * SECONDS_PER_SIMULATION + (SECONDS_PER_BUILD if todo else 0.0)
    log("Left-only pool diagnostic: DRY RUN")
    log("spec: docs/design/left-only-pool-diagnostic.md (PRE-STATED)")
    log("DIAGNOSTIC, not a validation: no pass criterion, no verdict is produced")
    try:
        pool = left_only_pool(ids_path)
        sides = kc_side_map(ids_path)
        counts: Dict[str, int] = {}
        for kc_id in pool:
            counts[sides[kc_id]] = counts.get(sides[kc_id], 0) + 1
        log(f"pool '{POOL_NAME}' drawn from {len(left_kc_ids(ids_path)):,} "
            f"{POOL_SIDE}-hemisphere KCs: {len(pool)} KCs, sides {counts}")
    except (OSError, RuntimeError, KeyError) as exc:
        log(f"pool could not be built from {ids_path}: {exc}")
    log(f"rate: {RATE_HZ:g} Hz on every pool KC -> {100 * RATE_HZ:,.0f} Hz total drive")
    log("matches anchor_100at150 (bilateral, 4/6 ignited) and the historical cue-A cell")
    log(f"seeds: {list(SEEDS)}")
    log(f"presentation: {DURATION_MS:g} ms x {TRIALS} trials")
    log(f"recorded populations: {list(POPULATIONS)}")
    log(f"planned simulations: {len(SEEDS)}  "
        f"(already done: {len(SEEDS) - len(todo)}, to run: {len(todo)})")
    log(f"estimated runtime: {seconds / 60:.1f} min "
        f"({SECONDS_PER_SIMULATION:g} s per simulation + one {SECONDS_PER_BUILD:g} s build; "
        "measured on the author's machine, UNVERIFIED elsewhere)")
    log("No connectome loaded, no model built, no simulation run, nothing written.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.dry_run and args.analyze_only:
        raise SystemExit("--dry-run and --analyze-only are mutually exclusive")
    if args.dry_run:
        return dry_run(args.results_dir, args.ids)
    if not args.analyze_only:
        simulate_missing(args.results_dir, args.ids)
    return 0 if summarise(args.results_dir, args.ids) is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
