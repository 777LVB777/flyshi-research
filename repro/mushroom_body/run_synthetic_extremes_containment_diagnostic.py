#!/usr/bin/env python3
"""Synthetic-market extremes containment diagnostic: ignition at the sweep's edges.

Pre-stated protocol: docs/design/synthetic-extremes-containment-diagnostic.md,
written before this code and before any run.

DIAGNOSTIC, NOT A VALIDATION. It measures; it does not judge. No pass criterion,
no verdict field; PASS/FAIL and ACCEPTED / USABLE RANGE / FAIL are deliberately
absent, as they belong to validations.

Six presentations of the synthetic-market sweep, chosen by a fixed rule from all
5,000 presentations the decided sweep will make (5 strengths x 5 market seeds x 100
markets x 2 framings), with the sweep's own encoder (left-only pools, mirrored NO
framing, unbalanced; recent_change bound +-1 since 2026-10-09): the three highest
total drives (all above 60,000 Hz, the highest drive ever run left-only), the
lowest and the highest price-pool rate
(prices outside the validated 0.06-0.94), and the lowest total drive. Six stimuli
x two seeds = 12 simulations. Every run records MBON, Kenyon cell, APL, PAM and
PPL1 trial-mean rates, plus per-trial Kenyon cell, MBON and APL rates.

Running without --analyze-only or --dry-run executes 12 real Brian2 simulations
and loads the connectome. Importing this file, --dry-run and --analyze-only do
neither.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling runners; none imports Brian2 at module level

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from flyshi_research.learning.encoder import BALANCE_FEATURE, NO, YES, KCEncoder  # noqa: E402
from flyshi_research.simulator import generate_signal_markets  # noqa: E402
from run_left_only_pool_diagnostic import IGNITION_SPREAD_FRACTION, kc_side_map, left_kc_ids  # noqa: E402
from run_left_only_realistic_drive_diagnostic import (  # noqa: E402
    MAX_FILE_BYTES,
    PER_TRIAL_POPULATIONS,
    _present_with_trials,
    _write_json,
    check_no_verdict,
    stimulus_statistics,
)
from run_population_scaling_diagnostic import POPULATIONS, SECONDS_PER_BUILD  # noqa: E402

RESULTS_DIR = HERE / "results"
IDS_PATH = HERE / "neuron_ids_783.json"
SPEC = "docs/design/synthetic-extremes-containment-diagnostic.md"

# ---- fixed by the pre-statement (spec sections 2-4) ------------------------------ #
POOL_SIDE = "left"
SEEDS: Tuple[int, ...] = (20261101, 20261102)  # unused by any earlier run or the sweep
DURATION_MS = 1000.0
TRIALS = 5
#: the highest total drive ever presented with left-only pools (realistic-drive diagnostic)
CONTAINED_DRIVE_CEILING_HZ = 60_000.0
#: the ACCEPTED validation's price coverage: set B and its mirror (0.06-0.94)
VALIDATED_PRICE_RATE_HZ = (37.2, 142.8)
N_HIGHEST_DRIVE = 3
#: planning figure (speed calibration, 500 KCs x 1000 ms x 5 trials; development Mac)
SECONDS_PER_SIMULATION = 55.0


@dataclass(frozen=True)
class Selected:
    name: str
    rule: str
    strength: float
    market_seed: int
    index: int
    framing: str

    def key(self) -> Tuple[float, int, int, str]:
        return (self.strength, self.market_seed, self.index, self.framing)


#: The selection the rule produces for the sweep as it stands (spec section 3). The
#: runner recomputes the rule and aborts unless it reproduces exactly this table, so
#: any change to the sweep's markets or encoder forces a new dated revision.
#: REVISED 2026-10-09 for recent_change bound +-1 (spec section 3, revision note).
#: Superseded original (bound +-0.2), kept for the record:
#:   highest_drive_1 0.8/20261005/25/NO, highest_drive_2 0.8/20261001/57/NO,
#:   highest_drive_3 0.8/20261004/5/NO, lowest_price_rate 0.0/20261001/51/YES,
#:   highest_price_rate 0.0/20261001/17/YES, lowest_drive 0.0/20261005/61/NO.
EXPECTED_SELECTION: Tuple[Tuple[str, float, int, int, str], ...] = (
    ("highest_drive_1", 0.8, 20261004, 7, YES),
    ("highest_drive_2", 0.8, 20261001, 17, YES),
    ("highest_drive_3", 0.8, 20261005, 25, NO),
    ("lowest_price_rate", 0.0, 20261001, 51, YES),
    ("highest_price_rate", 0.0, 20261001, 98, YES),
    ("lowest_drive", 0.0, 20261005, 61, NO),
)


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_synthetic_extremes_containment_diagnostic.py"
    )
    p = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog=f"Exact pre-stated run:\n  {command}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--analyze-only", action="store_true",
                   help="Summarise existing files; never simulates.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the selected stimuli, the plan and the runtime estimate; never simulates.")
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--ids", type=Path, default=IDS_PATH)
    return p


def output_path(stimulus: str, seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"synthetic_extremes_{stimulus}_seed_{seed}.json"


def summary_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "synthetic_extremes_containment_summary.json"


# --------------------------------------------------------------------------- #
# the selection rule (pure data; no Brian2, no connectome)
# --------------------------------------------------------------------------- #
def sweep_encoder(ids_path: Path = IDS_PATH) -> Tuple[KCEncoder, Dict[int, str]]:
    """The sweep's encoder: left-hemisphere KCs only, guarded exactly as the sweep is."""
    sides = kc_side_map(ids_path)
    encoder = KCEncoder(left_kc_ids(ids_path), params=sm.SyntheticConfig().encoder)
    sm.assert_pools_left_only(encoder, sides)
    return encoder, sides


def sweep_presentations(cfg: sm.SyntheticConfig, encoder: KCEncoder) -> List[dict]:
    """Every presentation the decided sweep makes, in sweep order. Learning changes
    weights, never stimuli, so each arm presents exactly these stimuli."""
    out = []
    for strength in cfg.signal_strengths:
        for seed in cfg.market_seeds:
            markets = generate_signal_markets(cfg.markets_per_seed, seed, strength, cfg.price_deviation)
            for index, market in enumerate(markets):
                pair = encoder.option_b_stimuli(sm.market_features(market),
                                                variant=sm.option_b_variant(cfg))
                for framing, stim in ((YES, pair.yes), (NO, pair.no)):
                    out.append({
                        "strength": strength, "market_seed": seed, "index": index,
                        "framing": framing, "quote": market.quote,
                        "features": sm.market_features(market),
                        "total_drive_hz": float(np.sum(stim.rates_hz)),
                        "price_rate_hz": float(stim.feature_rates_hz["price"]),
                        "pool_rates_hz": {k: float(v) for k, v in stim.feature_rates_hz.items()},
                        "stimulus": stim,
                    })
    return out


def select(cfg: sm.SyntheticConfig, encoder: KCEncoder) -> List[Tuple[Selected, dict]]:
    """The pre-stated rule (spec section 3). Ties break in sweep order. At most one
    presentation per market: a market's price, recent change, time to resolution and
    liquidity are the same at every strength (only the signal pool differs), so two
    picks from one market would be near-duplicate stimuli."""
    rows = sweep_presentations(cfg, encoder)
    order = {id(r): n for n, r in enumerate(rows)}
    chosen: List[Tuple[Selected, dict]] = []

    def identity(row):
        return (row["market_seed"], row["index"])

    def take(name, rule, key, count=1):
        taken = 0
        for row in sorted(rows, key=lambda r: (key(r), order[id(r)])):
            if any(identity(row) == identity(c) for _, c in chosen):
                continue
            label = name if count == 1 else f"{name}_{taken + 1}"
            chosen.append((Selected(label, rule, row["strength"], row["market_seed"],
                                    row["index"], row["framing"]), row))
            taken += 1
            if taken == count:
                return
        raise RuntimeError(f"rule {name!r} found too few distinct stimuli")

    take("highest_drive", "highest total drive", lambda r: -r["total_drive_hz"], N_HIGHEST_DRIVE)
    take("lowest_price_rate", "lowest price-pool rate", lambda r: r["price_rate_hz"])
    take("highest_price_rate", "highest price-pool rate", lambda r: -r["price_rate_hz"])
    take("lowest_drive", "lowest total drive", lambda r: r["total_drive_hz"])
    return chosen


def check_selection(chosen: Sequence[Tuple[Selected, dict]]) -> None:
    """The properties the pre-statement promises, then the frozen table."""
    for sel, row in chosen:
        if sel.rule == "highest total drive" and not row["total_drive_hz"] > CONTAINED_DRIVE_CEILING_HZ:
            raise RuntimeError(f"{sel.name}: drive {row['total_drive_hz']:g} Hz is not above "
                               f"{CONTAINED_DRIVE_CEILING_HZ:g} Hz")
        if "price-pool" in sel.rule:
            lo, hi = VALIDATED_PRICE_RATE_HZ
            if lo <= row["price_rate_hz"] <= hi:
                raise RuntimeError(f"{sel.name}: price-pool rate {row['price_rate_hz']:g} Hz "
                                   "lies inside the validated range")
        stim = row["stimulus"]
        if BALANCE_FEATURE in stim.feature_rates_hz or stim.kc_ids.size != 500:
            raise RuntimeError(f"{sel.name}: not the sweep's unbalanced 500-KC stimulus")
    got = tuple((s.name, s.strength, s.market_seed, s.index, s.framing) for s, _ in chosen)
    if got != EXPECTED_SELECTION:
        raise RuntimeError("the selection rule no longer reproduces the pre-stated table "
                           f"(spec section 3):\n  got {got}\n  expected {EXPECTED_SELECTION}")


def build_stimuli(ids_path: Path = IDS_PATH) -> Dict[str, dict]:
    encoder, _ = sweep_encoder(ids_path)
    chosen = select(sm.SyntheticConfig(), encoder)
    check_selection(chosen)
    pool_ids = {name: sorted(int(i) for i in ids) for name, ids in encoder.pools.items()}
    built = {}
    for sel, row in chosen:
        stim = row["stimulus"]
        rates = stim.rates_by_kc_id()
        built[sel.name] = {
            "selected": sel,
            "rates_by_kc_id": rates,
            "stimulated_kc_ids": sorted(rates),
            "pools": {name: pool_ids[name] for name in stim.feature_rates_hz},
            "pool_rates_hz": row["pool_rates_hz"],
            "total_drive_hz": row["total_drive_hz"],
            "quote": row["quote"],
            "features": row["features"],
            "clipped": [e.feature for e in stim.clip_events],
        }
    return built


def planned_pairs(names: Sequence[str]) -> Tuple[Tuple[str, int], ...]:
    return tuple((name, seed) for name in names for seed in SEEDS)


# --------------------------------------------------------------------------- #
# simulation (the only part that constructs the model)
# --------------------------------------------------------------------------- #
def simulate_missing(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
                     log: Callable[[str], None] = print) -> None:
    stimuli = build_stimuli(ids_path)  # selected and checked before the model is built
    todo = [(n, s) for n, s in planned_pairs(list(stimuli))
            if not output_path(n, s, results_dir).exists()]
    if not todo:
        log("All outputs exist; nothing to simulate.")
        return

    from run_population_scaling_diagnostic import _build_population_simulator

    sim = _build_population_simulator()
    for name, seed in todo:
        stim, sel = stimuli[name], stimuli[name]["selected"]
        means, trials = _present_with_trials(sim, stim["rates_by_kc_id"], seed, DURATION_MS, TRIALS)
        _write_json(
            output_path(name, seed, results_dir),
            {
                "stimulus": name,
                "rule": sel.rule,
                "sweep_presentation": {"strength": sel.strength, "market_seed": sel.market_seed,
                                       "index": sel.index, "framing": sel.framing},
                "variant": sm.OPTION_B_UNBALANCED,
                "framing": sel.framing,
                "price_value": stim["quote"],
                "features": stim["features"],
                "clipped_features": stim["clipped"],
                "pool_side": POOL_SIDE,
                "pools": stim["pools"],
                "pool_rates_hz": stim["pool_rates_hz"],
                "n_kcs_driven": len(stim["stimulated_kc_ids"]),
                "per_kc_rate_hz": None,  # unequal across pools; see pool_rates_hz
                "total_drive_hz": stim["total_drive_hz"],
                "stimulated_kc_ids": stim["stimulated_kc_ids"],
                "mbon_labels": list(sim.mbon_type_labels),
                "population_ids": {p: list(sim.population_ids[p]) for p in POPULATIONS},
                "rates_hz": {p: np.asarray(v, dtype=float).tolist() for p, v in means.items()},
                "per_trial_rates_hz": {p: np.asarray(v, dtype=float).tolist()
                                       for p, v in trials.items()},
                "seed": seed,
                "duration_ms": DURATION_MS,
                "trials": TRIALS,
            },
            max_bytes=MAX_FILE_BYTES,
        )
        log(f"{name} ({stim['total_drive_hz']:,.0f} Hz), seed {seed}: "
            f"wrote {output_path(name, seed, results_dir).name}")


# --------------------------------------------------------------------------- #
# measurement (no verdict: this is a diagnostic)
# --------------------------------------------------------------------------- #
def summarise(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
              log: Callable[[str], None] = print) -> Optional[dict]:
    planned = build_stimuli(ids_path)
    missing = [(n, s) for n, s in planned_pairs(list(planned))
               if not output_path(n, s, results_dir).exists()]
    if missing:
        log(f"Cannot summarise: missing {len(missing)} of {len(planned) * len(SEEDS)} results")
        return None
    sides = kc_side_map(ids_path)
    per_stimulus: Dict[str, dict] = {}
    for name, stim in planned.items():
        payloads = [json.loads(output_path(name, s, results_dir).read_text()) for s in SEEDS]
        if payloads[0]["stimulated_kc_ids"] != stim["stimulated_kc_ids"]:
            raise ValueError(f"{name}: saved stimulated KCs differ from the pre-stated stimulus")
        per_stimulus[name] = {"rule": stim["selected"].rule,
                              "sweep_presentation": payloads[0]["sweep_presentation"],
                              "features": stim["features"],
                              **stimulus_statistics(payloads, sides)}
    table = [{
        "stimulus": name,
        "rule": s["rule"],
        "total_drive_hz": s["total_drive_hz"],
        "price_rate_hz": s["pool_rates_hz"]["price"],
        "ignited_runs": s["ignited_runs"],
        "spread": s["nonstimulated_kc_active_fraction"],
        "recruited_kc_mean_rate_hz_over_recruiting_seeds":
            s["recruited_kc_mean_rate_hz_over_recruiting_seeds"],
        "active_mbons": s["active_mbons"],
        "apl_hz": s["apl_mean_rate_hz"],
        "score_mean": s["score_mean"],
    } for name, s in per_stimulus.items()]
    summary = {
        "prestated_diagnostic": True,
        "is_a_validation": False,
        "has_pass_criterion": False,
        "spec": SPEC,
        "seeds": list(SEEDS),
        "duration_ms": DURATION_MS,
        "trials": TRIALS,
        "pool_side": POOL_SIDE,
        "contained_drive_ceiling_hz": CONTAINED_DRIVE_CEILING_HZ,
        "validated_price_rate_hz": list(VALIDATED_PRICE_RATE_HZ),
        "ignition_label_spread_fraction": IGNITION_SPREAD_FRACTION,
        "per_trial_populations": list(PER_TRIAL_POPULATIONS),
        "stimuli": per_stimulus,
        "table": table,
        "scope_note": (
            "Containment and recruitment at six of the sweep's own presentations, two "
            "seeds each, at baseline weights. Says nothing about learned weights, the "
            "score's relation to price, or any presentation not listed."
        ),
    }
    check_no_verdict(summary)
    _write_json(summary_path(results_dir), summary)
    log("=== Synthetic extremes containment diagnostic (MEASUREMENT; no verdict, no pass criterion) ===")
    log(f"{'stimulus':<22}{'driveHz':>9}{'priceHz':>9}{'ign':>6}{'spread':>8}{'recruitHz':>10}"
        f"{'actMBON':>9}{'APL':>8}")
    for row in table:
        r = row["recruited_kc_mean_rate_hz_over_recruiting_seeds"]
        log(f"{row['stimulus']:<22}{row['total_drive_hz']:>9,.0f}{row['price_rate_hz']:>9.1f}"
            f"{row['ignited_runs']:>4}/{len(SEEDS)}{100 * row['spread']:>7.1f}%"
            f"{('--' if r is None else f'{r:.2f}'):>10}{row['active_mbons']:>9.1f}{row['apl_hz']:>8.1f}")
    log(f"Wrote {summary_path(results_dir).name}")
    return summary


# --------------------------------------------------------------------------- #
# dry run
# --------------------------------------------------------------------------- #
def dry_run(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
            log: Callable[[str], None] = print) -> None:
    stimuli = build_stimuli(ids_path)
    todo = [(n, s) for n, s in planned_pairs(list(stimuli))
            if not output_path(n, s, results_dir).exists()]
    log("Synthetic extremes containment diagnostic: PLAN (dry run; nothing is simulated)")
    log("  DIAGNOSTIC, not a validation: is_a_validation false, no pass criterion")
    log(f"  pools: left-hemisphere only, guarded; seeds {list(SEEDS)}; "
        f"{DURATION_MS:g} ms x {TRIALS} trials")
    log(f"  {'stimulus':<22}{'sweep presentation':<34}{'price':>6}{'priceHz':>9}{'driveHz':>9}")
    for name, s in stimuli.items():
        sel = s["selected"]
        where = f"s={sel.strength:g} seed={sel.market_seed} m={sel.index} {sel.framing}"
        log(f"  {name:<22}{where:<34}{s['quote']:>6.3f}{s['pool_rates_hz']['price']:>9.1f}"
            f"{s['total_drive_hz']:>9,.0f}")
    seconds = len(todo) * SECONDS_PER_SIMULATION + (SECONDS_PER_BUILD if todo else 0.0)
    log(f"  simulations to run: {len(todo)} of {len(stimuli) * len(SEEDS)}; "
        f"estimated {seconds / 60:.0f} min at {SECONDS_PER_SIMULATION:g} s each (UNVERIFIED)")


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.dry_run:
        dry_run(args.results_dir, args.ids)
        return 0
    if not args.analyze_only:
        simulate_missing(args.results_dir, args.ids)
    return 0 if summarise(args.results_dir, args.ids) is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
