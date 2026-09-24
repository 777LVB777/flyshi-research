#!/usr/bin/env python3
"""Left-only population-scaling diagnostic: where does a left-only ladder ignite?

Pre-stated protocol: docs/design/left-only-population-scaling-diagnostic.md,
written before this code and before any run.

DIAGNOSTIC, NOT A VALIDATION. It measures; it does not judge. No pass criterion,
no verdict field; PASS/FAIL and ACCEPTED / USABLE RANGE / FAIL are deliberately
absent, as they belong to validations.

The bilateral 90 Hz ladder (100, 200, 300, 500 KCs) rerun with the encoder's pools
drawn from LEFT-hemisphere Kenyon cells only, nested in the same pool order.
Four conditions x six seeds = 24 simulations. The left-only pool diagnostic's
100-KC files hold the same pool but at 150 Hz, so they are not reused.

Running without --analyze-only or --dry-run executes 24 real Brian2 simulations
and loads the connectome. Importing this file, --dry-run and --analyze-only do
neither.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling runners; import no Brian2 at module level

from flyshi_research.learning.encoder import KCEncoder  # noqa: E402
from run_left_only_pool_diagnostic import (  # noqa: E402
    IGNITION_SPREAD_FRACTION,
    kc_side_map,
    left_kc_ids,
    statistics,
)
from run_population_scaling_diagnostic import (  # noqa: E402
    LADDER_POOL_ORDER,
    POPULATIONS,
    SECONDS_PER_BUILD,
    SECONDS_PER_SIMULATION,
)

RESULTS_DIR = HERE / "results"
IDS_PATH = HERE / "neuron_ids_783.json"

# ---- fixed by the pre-statement (spec section 2) ------------------------------ #
POOL_SIDE = "left"
RATE_HZ = 90.0
SEEDS: Tuple[int, ...] = (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
DURATION_MS = 1000.0
TRIALS = 5


@dataclass(frozen=True)
class Condition:
    name: str
    n_pools: int
    bilateral: str  # the population-scaling condition at the same count and rate

    @property
    def n_kcs(self) -> int:
        return 100 * self.n_pools

    @property
    def total_drive_hz(self) -> float:
        return self.n_kcs * RATE_HZ

    def pools(self) -> Tuple[str, ...]:
        return LADDER_POOL_ORDER[: self.n_pools]


CONDITIONS: Tuple[Condition, ...] = (
    Condition("left_ladder_100", 1, "ladder_100"),
    Condition("left_ladder_200", 2, "ladder_200"),
    Condition("left_ladder_300", 3, "ladder_300"),
    Condition("left_ladder_500", 5, "ladder_500"),
)
BY_NAME: Dict[str, Condition] = {c.name: c for c in CONDITIONS}


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_left_only_population_scaling_diagnostic.py"
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


def output_path(condition: str, seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"left_only_scaling_{condition}_seed_{seed}.json"


def bilateral_path(condition: str, seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"population_scaling_{condition}_seed_{seed}.json"


def summary_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "left_only_scaling_summary.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, separators=(",", ":")))
    partial.replace(path)


def planned_pairs() -> Tuple[Tuple[str, int], ...]:
    return tuple((c.name, seed) for c in CONDITIONS for seed in SEEDS)


def missing_pairs(results_dir: Path = RESULTS_DIR) -> List[Tuple[str, int]]:
    return [(name, seed) for name, seed in planned_pairs()
            if not output_path(name, seed, results_dir).exists()]


def missing_bilateral(results_dir: Path = RESULTS_DIR) -> List[Tuple[str, int]]:
    return [(c.bilateral, seed) for c in CONDITIONS for seed in SEEDS
            if not bilateral_path(c.bilateral, seed, results_dir).exists()]


# --------------------------------------------------------------------------- #
# the stimulus (pure data; no Brian2, no connectome)
# --------------------------------------------------------------------------- #
def left_ladder_pools(ids_path: Path = IDS_PATH) -> Dict[str, List[int]]:
    """Every rung's KC IDs, drawn by the encoder from left-hemisphere KCs only.

    Aborts unless each rung is exactly its count, all left, and contains the rung
    below it: one-sidedness and nesting are the design, so they are asserted.
    """
    sides = kc_side_map(ids_path)
    encoder = KCEncoder(left_kc_ids(ids_path))
    rungs: Dict[str, List[int]] = {}
    previous: set = set()
    for condition in CONDITIONS:
        kcs = sorted(int(i) for name in condition.pools() for i in encoder.pools[name])
        if len(set(kcs)) != condition.n_kcs:
            raise RuntimeError(f"{condition.name}: expected {condition.n_kcs} KCs, "
                               f"drew {len(set(kcs))}")
        wrong = [i for i in kcs if sides.get(i) != POOL_SIDE]
        if wrong:
            raise RuntimeError(f"{condition.name}: {len(wrong)} KCs are not "
                               f"{POOL_SIDE}-hemisphere")
        if not previous <= set(kcs):
            raise RuntimeError(f"{condition.name}: does not contain the rung below it")
        previous = set(kcs)
        rungs[condition.name] = kcs
    return rungs


def stimulus_for(condition: Condition, ids_path: Path = IDS_PATH) -> Dict[int, float]:
    return {kc_id: RATE_HZ for kc_id in left_ladder_pools(ids_path)[condition.name]}


# --------------------------------------------------------------------------- #
# simulation (the only part that constructs the model)
# --------------------------------------------------------------------------- #
def simulate_missing(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
                     log: Callable[[str], None] = print) -> None:
    todo = missing_pairs(results_dir)
    for name, seed in planned_pairs():
        if (name, seed) not in todo:
            log(f"Output exists, skipping: {output_path(name, seed, results_dir).name}")
    if not todo:
        return

    from run_population_scaling_diagnostic import _build_population_simulator

    rungs = left_ladder_pools(ids_path)  # validated before the model is built
    sim = _build_population_simulator()
    for name, seed in todo:
        condition = BY_NAME[name]
        rates = {kc_id: RATE_HZ for kc_id in rungs[name]}
        populations = sim.present_populations(rates, seed, DURATION_MS, TRIALS)
        _write_json(
            output_path(name, seed, results_dir),
            {
                "condition": name,
                "bilateral_counterpart": condition.bilateral,
                "pool_side": POOL_SIDE,
                "pools": list(condition.pools()),
                "n_kcs_driven": condition.n_kcs,
                "per_kc_rate_hz": RATE_HZ,
                "total_drive_hz": condition.total_drive_hz,
                "stimulated_kc_ids": rungs[name],
                "mbon_labels": list(sim.mbon_type_labels),
                "population_ids": {p: list(sim.population_ids[p]) for p in POPULATIONS},
                "rates_hz": {p: np.asarray(v, dtype=float).tolist()
                             for p, v in populations.items()},
                "seed": seed,
                "duration_ms": DURATION_MS,
                "trials": TRIALS,
            },
        )
        log(f"{name} ({condition.n_kcs} left KCs at {RATE_HZ:g} Hz), seed {seed}: "
            f"wrote {output_path(name, seed, results_dir).name}")


# --------------------------------------------------------------------------- #
# measurement (no verdict: this is a diagnostic)
# --------------------------------------------------------------------------- #
def side_counts(kc_ids: Sequence[int], sides: Mapping[int, str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for kc_id in kc_ids:
        key = sides.get(int(kc_id), "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def rung_statistics(payloads: Sequence[Mapping], sides: Mapping[int, str]) -> dict:
    """The left-only pool diagnostic's statistics, plus measured vs imposed KC rate."""
    labels = payloads[0]["mbon_labels"]
    if any(p["mbon_labels"] != labels for p in payloads):
        raise ValueError(f"{payloads[0]['condition']}: MBON label order differs between seeds")
    stats = statistics(payloads, sides)
    imposed = float(payloads[0]["per_kc_rate_hz"])
    kc_ids = [int(i) for i in payloads[0]["population_ids"]["kenyon_cells"]]
    stimulated = set(int(i) for i in payloads[0]["stimulated_kc_ids"])
    is_stim = np.array([i in stimulated for i in kc_ids])
    measured = [float(np.asarray(p["rates_hz"]["kenyon_cells"], dtype=float)[is_stim].mean())
                for p in payloads]
    stats.update({
        "pool_side_counts": side_counts(payloads[0]["stimulated_kc_ids"], sides),
        "stimulated_kc_imposed_rate_hz": imposed,
        "stimulated_kc_measured_rate_per_seed_hz": measured,
        "stimulated_kc_measured_over_imposed": float(np.mean(measured)) / imposed,
    })
    return stats


def _load(paths: Sequence[Path]) -> List[dict]:
    return [json.loads(p.read_text()) for p in paths]


def summarise(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
              log: Callable[[str], None] = print) -> Optional[dict]:
    missing = missing_pairs(results_dir)
    if missing:
        log(f"Cannot summarise: missing {len(missing)} of {len(planned_pairs())} "
            "left-only condition/seed results")
        return None
    missing_ref = missing_bilateral(results_dir)
    if missing_ref:
        log(f"Cannot summarise: missing {len(missing_ref)} of {len(planned_pairs())} "
            "bilateral reference results (population_scaling_ladder_*)")
        return None
    sides = kc_side_map(ids_path)

    left: Dict[str, dict] = {}
    bilateral: Dict[str, dict] = {}
    for c in CONDITIONS:
        left_payloads = _load([output_path(c.name, s, results_dir) for s in SEEDS])
        ref_payloads = _load([bilateral_path(c.bilateral, s, results_dir) for s in SEEDS])
        left[c.name] = {"pools": list(c.pools()), **rung_statistics(left_payloads, sides)}
        shared = (set(int(i) for i in left_payloads[0]["stimulated_kc_ids"])
                  & set(int(i) for i in ref_payloads[0]["stimulated_kc_ids"]))
        bilateral[c.bilateral] = {
            "left_only_counterpart": c.name,
            "kcs_shared_with_left_only_rung": len(shared),
            **rung_statistics(ref_payloads, sides),
        }

    ladder = [
        {
            "n_kcs": c.n_kcs,
            "total_drive_hz": c.total_drive_hz,
            "left_only": c.name,
            "bilateral": c.bilateral,
            "ignited_runs_left_only": left[c.name]["ignited_runs"],
            "ignited_runs_bilateral": bilateral[c.bilateral]["ignited_runs"],
            "spread_left_only": left[c.name]["nonstimulated_kc_active_fraction"],
            "spread_bilateral": bilateral[c.bilateral]["nonstimulated_kc_active_fraction"],
            "active_mbons_left_only": left[c.name]["active_mbons"],
            "active_mbons_bilateral": bilateral[c.bilateral]["active_mbons"],
            "apl_hz_left_only": left[c.name]["apl_mean_rate_hz"],
            "apl_hz_bilateral": bilateral[c.bilateral]["apl_mean_rate_hz"],
            "score_sd_left_only": left[c.name]["score_sd"],
            "score_sd_bilateral": bilateral[c.bilateral]["score_sd"],
        }
        for c in CONDITIONS
    ]

    summary = {
        "prestated_diagnostic": True,
        "is_a_validation": False,
        "has_pass_criterion": False,
        "spec": "docs/design/left-only-population-scaling-diagnostic.md",
        "seeds": list(SEEDS),
        "duration_ms": DURATION_MS,
        "trials": TRIALS,
        "per_kc_rate_hz": RATE_HZ,
        "pool_side": POOL_SIDE,
        "ladder_pool_order": list(LADDER_POOL_ORDER),
        "ignition_label_spread_fraction": IGNITION_SPREAD_FRACTION,
        "conditions": left,
        "bilateral_reference": bilateral,
        "ladder": ladder,
        "comparison_note": (
            "Matched count and rate. Each left-only rung is a different set of cells "
            "from its bilateral counterpart, so hemisphere and pool draw stay "
            "confounded (spec 4). One nested pool sequence at one uniform rate: "
            "not a five-pool encoder stimulus, not an independent redraw."
        ),
        "not_reused_note": (
            "left_only_pool_seed_*.json hold the same 100-KC pool as left_ladder_100 "
            "but at 150 Hz, so the stimulus is not identical and they are not used."
        ),
    }
    _write_json(summary_path(results_dir), summary)

    log("=== Left-only population-scaling diagnostic "
        "(MEASUREMENT; no verdict, no pass criterion) ===")
    log(f"{'KCs':>5}{'ign L':>7}{'ign B':>7}{'spread L':>10}{'spread B':>10}"
        f"{'actMBON L':>11}{'actMBON B':>11}{'APL L':>8}{'APL B':>8}{'SD L':>8}{'SD B':>8}")
    for row in ladder:
        log(f"{row['n_kcs']:>5}"
            f"{row['ignited_runs_left_only']:>5}/6{row['ignited_runs_bilateral']:>5}/6"
            f"{100 * row['spread_left_only']:>9.1f}%{100 * row['spread_bilateral']:>9.1f}%"
            f"{row['active_mbons_left_only']:>11.1f}{row['active_mbons_bilateral']:>11.1f}"
            f"{row['apl_hz_left_only']:>8.1f}{row['apl_hz_bilateral']:>8.1f}"
            f"{row['score_sd_left_only']:>8.2f}{row['score_sd_bilateral']:>8.2f}")
    log(f"Wrote {summary_path(results_dir).name}")
    return summary


# --------------------------------------------------------------------------- #
# dry run
# --------------------------------------------------------------------------- #
def dry_run(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
            log: Callable[[str], None] = print) -> int:
    todo = missing_pairs(results_dir)
    total = len(planned_pairs())
    seconds = len(todo) * SECONDS_PER_SIMULATION + (SECONDS_PER_BUILD if todo else 0.0)
    log("Left-only population-scaling diagnostic: DRY RUN")
    log("spec: docs/design/left-only-population-scaling-diagnostic.md (PRE-STATED)")
    log("DIAGNOSTIC, not a validation: no pass criterion, no verdict is produced")
    log(f"ladder pool order: {list(LADDER_POOL_ORDER)} (nested, {POOL_SIDE}-hemisphere only)")
    try:
        rungs = left_ladder_pools(ids_path)
        sides = kc_side_map(ids_path)
    except (OSError, RuntimeError, KeyError, ValueError) as exc:
        rungs, sides = {}, {}
        log(f"pools could not be built from {ids_path}: {exc}")
    log(f"{'condition':<18}{'KCs':>5}{'rateHz':>8}{'driveHz':>10}  sides / bilateral counterpart")
    for c in CONDITIONS:
        composition = side_counts(rungs[c.name], sides) if c.name in rungs else "?"
        log(f"{c.name:<18}{c.n_kcs:>5}{RATE_HZ:>8.0f}{c.total_drive_hz:>10,.0f}  "
            f"{composition} / {c.bilateral}")
    log("left_only_pool_seed_*.json NOT reused: same 100-KC pool, but 150 Hz, not 90 Hz")
    log(f"seeds: {list(SEEDS)}")
    log(f"presentation: {DURATION_MS:g} ms x {TRIALS} trials")
    log(f"recorded populations: {list(POPULATIONS)}")
    ref_missing = missing_bilateral(results_dir)
    log(f"bilateral reference files: {total - len(ref_missing)} of {total} present"
        + ("" if not ref_missing else " (summary will not be written until all are)"))
    log(f"planned simulations: {total}  (already done: {total - len(todo)}, to run: {len(todo)})")
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
