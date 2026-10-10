#!/usr/bin/env python3
"""Low-drive ignition follow-up: how often do the sweep's lowest-drive stimuli ignite?

Pre-stated protocol: docs/design/low-drive-ignition-followup-diagnostic.md, written
before this code and before any run.

DIAGNOSTIC, NOT A VALIDATION. It measures; it does not judge. No pass criterion,
no verdict field; PASS/FAIL and ACCEPTED / USABLE RANGE / FAIL are deliberately
absent, as they belong to validations.

Ten presentations of the decided synthetic-market sweep (left-only pools, mirrored
NO framing, unbalanced, recent_change bound +-1): all 6 presentations below 25 kHz
total drive, plus 4 in 25-30 kHz chosen by a fixed rule. Ten seeds each = 100
simulations, with per-trial KC, MBON and APL rates. Reports the ignition rate per
run and per trial with exact (Clopper-Pearson) 95% intervals, and compares the
20-30 kHz window with neighbouring drive levels from already-saved left-only runs.

Running without --analyze-only or --dry-run executes 100 real Brian2 simulations
and loads the connectome. Importing this file, --dry-run and --analyze-only do
neither.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass
from math import comb
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling runners; none imports Brian2 at module level

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from flyshi_research.learning.encoder import BALANCE_FEATURE, NO, YES  # noqa: E402
from run_left_only_pool_diagnostic import IGNITION_SPREAD_FRACTION, kc_side_map  # noqa: E402
from run_left_only_realistic_drive_diagnostic import (  # noqa: E402
    MAX_FILE_BYTES,
    PER_TRIAL_POPULATIONS,
    _present_with_trials,
    _write_json,
    check_no_verdict,
    stimulus_statistics,
)
from run_population_scaling_diagnostic import ACTIVE_HZ, POPULATIONS, SECONDS_PER_BUILD  # noqa: E402
from run_synthetic_extremes_containment_diagnostic import (  # noqa: E402
    sweep_encoder,
    sweep_presentations,
)

RESULTS_DIR = HERE / "results"
IDS_PATH = HERE / "neuron_ids_783.json"
SPEC = "docs/design/low-drive-ignition-followup-diagnostic.md"

# ---- fixed by the pre-statement (spec sections 2-5) ------------------------------ #
POOL_SIDE = "left"
SEEDS: Tuple[int, ...] = tuple(range(20261201, 20261211))  # ten seeds, unused before
DURATION_MS = 1000.0
TRIALS = 5
LOW_BAND_HZ = (0.0, 25_000.0)        # every sweep presentation in this band
MID_BAND_HZ = (25_000.0, 30_000.0)   # four presentations from this band
MID_TARGETS_HZ = (26_000.0, 27_000.0, 28_000.0, 29_000.0)
WINDOW_HZ = (20_000.0, 30_000.0)
#: neighbouring drive bands for the comparison (spec section 6)
NEIGHBOUR_BANDS: Tuple[Tuple[str, float, float], ...] = (
    ("below_window_0_20khz", 0.0, 20_000.0),
    ("above_window_30_40khz", 30_000.0, 40_000.0),
    ("above_window_40_70khz", 40_000.0, 70_000.0),
)
#: already-saved left-only result families used for the comparison (spec section 6)
NEIGHBOUR_FAMILIES: Tuple[str, ...] = (
    "left_only_pool_seed_*.json",
    "left_only_scaling_left_ladder_*_seed_*.json",
    "left_only_realistic_drive_*_seed_*.json",
    "graded_left_mirrored_value_*_seed_*.json",
    "pool_identity_*_seed_*.json",
    "synthetic_extremes_*_seed_*.json",
)
CI_LEVEL = 0.95
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


#: The table the rule produced when this was pre-stated (spec section 3). The runner
#: recomputes the rule and aborts unless it reproduces exactly this table.
EXPECTED_SELECTION: Tuple[Tuple[str, float, int, int, str], ...] = (
    ("below25_1", 0.0, 20261005, 61, NO),
    ("below25_2", 0.1, 20261005, 61, NO),
    ("below25_3", 0.2, 20261005, 61, NO),
    ("below25_4", 0.4, 20261005, 61, NO),
    ("below25_5", 0.8, 20261005, 61, NO),
    ("below25_6", 0.8, 20261004, 23, YES),
    ("band25_30_near26k", 0.8, 20261004, 56, NO),
    ("band25_30_near27k", 0.1, 20261003, 61, NO),
    ("band25_30_near28k", 0.8, 20261004, 81, YES),
    ("band25_30_near29k", 0.1, 20261005, 14, NO),
)


def parser() -> argparse.ArgumentParser:
    command = ".venv-shiu/bin/python repro/mushroom_body/run_low_drive_ignition_followup_diagnostic.py"
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
    return results_dir / f"low_drive_followup_{stimulus}_seed_{seed}.json"


def summary_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "low_drive_followup_summary.json"


# --------------------------------------------------------------------------- #
# the selection rule (pure data; no Brian2, no connectome)
# --------------------------------------------------------------------------- #
def select(rows: Sequence[dict]) -> List[Tuple[Selected, dict]]:
    """The pre-stated rule (spec section 3). Ties break in sweep order.

    1. Every presentation below 25 kHz, in ascending drive (several may be the
       same market at different strengths: that is how often the sweep shows it).
    2. For each target 26, 27, 28, 29 kHz, the 25-30 kHz presentation closest to
       it, from a market not already selected in either step.
    """
    order = {id(r): n for n, r in enumerate(rows)}
    chosen: List[Tuple[Selected, dict]] = []
    low = [r for r in rows if LOW_BAND_HZ[0] <= r["total_drive_hz"] < LOW_BAND_HZ[1]]
    for n, row in enumerate(sorted(low, key=lambda r: (r["total_drive_hz"], order[id(r)])), start=1):
        chosen.append((Selected(f"below25_{n}", "below 25 kHz", row["strength"], row["market_seed"],
                                row["index"], row["framing"]), row))
    mid = [r for r in rows if MID_BAND_HZ[0] <= r["total_drive_hz"] < MID_BAND_HZ[1]]
    for target in MID_TARGETS_HZ:
        used = {(s.market_seed, s.index) for s, _ in chosen}
        pool = [r for r in mid if (r["market_seed"], r["index"]) not in used]
        if not pool:
            raise RuntimeError(f"no unused 25-30 kHz market for target {target:g} Hz")
        row = min(pool, key=lambda r: (abs(r["total_drive_hz"] - target), order[id(r)]))
        chosen.append((Selected(f"band25_30_near{int(target / 1000)}k", f"25-30 kHz, closest to {target:g} Hz",
                                row["strength"], row["market_seed"], row["index"], row["framing"]), row))
    return chosen


def build_stimuli(ids_path: Path = IDS_PATH) -> Dict[str, dict]:
    encoder, _ = sweep_encoder(ids_path)
    chosen = select(sweep_presentations(sm.pre_revision_config(), encoder))  # pre-revision design
    got = tuple((s.name, s.strength, s.market_seed, s.index, s.framing) for s, _ in chosen)
    if got != EXPECTED_SELECTION:
        raise RuntimeError("the selection rule no longer reproduces the pre-stated table "
                           f"(spec section 3):\n  got {got}\n  expected {EXPECTED_SELECTION}")
    pool_ids = {name: sorted(int(i) for i in ids) for name, ids in encoder.pools.items()}
    built = {}
    for sel, row in chosen:
        stim = row["stimulus"]
        if BALANCE_FEATURE in stim.feature_rates_hz or stim.kc_ids.size != 500:
            raise RuntimeError(f"{sel.name}: not the sweep's unbalanced 500-KC stimulus")
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
                "pool_side": POOL_SIDE,
                "pools": stim["pools"],
                "pool_rates_hz": stim["pool_rates_hz"],
                "n_kcs_driven": len(stim["stimulated_kc_ids"]),
                "per_kc_rate_hz": None,
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
def clopper_pearson(k: int, n: int, level: float = CI_LEVEL) -> Tuple[Optional[float], Optional[float]]:
    """Exact binomial interval for k of n (bisection on the binomial tail)."""
    if n == 0:
        return None, None
    alpha = 1.0 - level

    def tail_ge(p):  # P(X >= k)
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))

    def tail_le(p):  # P(X <= k)
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))

    def solve(f, target, increasing):
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if (f(mid) < target) == increasing:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(tail_ge, alpha / 2, True)
    upper = 1.0 if k == n else solve(tail_le, alpha / 2, False)
    return lower, upper


def fisher_one_sided_greater(k1: int, n1: int, k2: int, n2: int) -> Optional[float]:
    """P(a group-1 count >= k1 | margins): is group 1's rate higher than group 2's?"""
    if n1 == 0 or n2 == 0:
        return None
    total_k, total_n = k1 + k2, n1 + n2
    denom = comb(total_n, total_k)
    return float(sum(comb(n1, i) * comb(n2, total_k - i)
                     for i in range(k1, min(n1, total_k) + 1)) / denom)


def rate(k: int, n: int) -> dict:
    lower, upper = clopper_pearson(k, n)
    return {"k": k, "n": n, "rate": (k / n) if n else None,
            "ci95_lower": lower, "ci95_upper": upper}


def _free_mask(payload: Mapping) -> np.ndarray:
    kc_ids = np.asarray(payload["population_ids"]["kenyon_cells"], dtype=np.int64)
    return ~np.isin(kc_ids, np.asarray(payload["stimulated_kc_ids"], dtype=np.int64))


def run_labels(payload: Mapping) -> dict:
    """Trial-mean label (as in every earlier diagnostic) and, where saved, per-trial labels."""
    free = _free_mask(payload)
    kc = np.asarray(payload["rates_hz"]["kenyon_cells"], dtype=float)
    out = {"drive_hz": float(payload["total_drive_hz"]),
           "ignited_trial_mean": bool(((kc > ACTIVE_HZ) & free).sum() / free.sum() > IGNITION_SPREAD_FRACTION)}
    trials = payload.get("per_trial_rates_hz", {}).get("kenyon_cells")
    if trials is not None:
        spreads = [float(((np.asarray(t) > ACTIVE_HZ) & free).sum() / free.sum()) for t in trials]
        out["trial_ignited"] = [s > IGNITION_SPREAD_FRACTION for s in spreads]
        out["trial_spread"] = spreads
    return out


def neighbour_comparison(results_dir: Path, new_labels: Sequence[dict]) -> dict:
    """Ignition by drive band in already-saved left-only runs, against the new runs."""
    saved = []
    for pattern in NEIGHBOUR_FAMILIES:
        for path in sorted(glob.glob(str(results_dir / pattern))):
            if "summary" in path:
                continue
            saved.append({"file": Path(path).name, **run_labels(json.loads(Path(path).read_text()))})
    new_runs = sum(1 for _ in new_labels)
    new_run_k = sum(l["ignited_trial_mean"] for l in new_labels)
    new_trials = [t for l in new_labels for t in l["trial_ignited"]]
    out = {"new_runs_trial_mean_label": rate(new_run_k, new_runs),
           "new_trials": rate(sum(new_trials), len(new_trials)),
           "prior_runs_in_window": [], "bands": {}}
    lo_w, hi_w = WINDOW_HZ
    out["prior_runs_in_window"] = [
        {"file": s["file"], "drive_hz": s["drive_hz"], "ignited_trial_mean": s["ignited_trial_mean"]}
        for s in saved if lo_w <= s["drive_hz"] < hi_w]
    for name, lo, hi in NEIGHBOUR_BANDS:
        band = [s for s in saved if lo <= s["drive_hz"] < hi]
        k = sum(s["ignited_trial_mean"] for s in band)
        with_trials = [t for s in band if "trial_ignited" in s for t in s["trial_ignited"]]
        p_run = fisher_one_sided_greater(new_run_k, new_runs, k, len(band))
        p_trial = (fisher_one_sided_greater(sum(new_trials), len(new_trials),
                                            sum(with_trials), len(with_trials))
                   if with_trials else None)
        out["bands"][name] = {
            "drive_hz": [lo, hi],
            "runs_trial_mean_label": rate(k, len(band)),
            "trials": rate(sum(with_trials), len(with_trials)) if with_trials else None,
            "fisher_one_sided_p_new_runs_higher": p_run,
            "fisher_one_sided_p_new_trials_higher": p_trial,
            "reading_runs": (None if p_run is None else
                             "elevated in the window" if p_run < 0.05 else "not distinguishable"),
        }
    out["comparison_note"] = (
        "Neighbouring bands are already-saved runs of different constructions (uniform-rate "
        "ladders, single-feature graded stimuli, sweep presentations), not a matched control; "
        "the readings describe rates and are not a pass criterion.")
    return out


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
    all_labels: List[dict] = []
    groups: Dict[str, List[dict]] = {"below25": [], "band25_30": []}
    for name, stim in planned.items():
        payloads = [json.loads(output_path(name, s, results_dir).read_text()) for s in SEEDS]
        if payloads[0]["stimulated_kc_ids"] != stim["stimulated_kc_ids"]:
            raise ValueError(f"{name}: saved stimulated KCs differ from the pre-stated stimulus")
        labels = [run_labels(p) for p in payloads]
        all_labels += labels
        groups["below25" if name.startswith("below25") else "band25_30"] += labels
        trials = [t for l in labels for t in l["trial_ignited"]]
        apl = [np.asarray(p["per_trial_rates_hz"]["apl_neurons"], dtype=float).mean(axis=1)
               for p in payloads]
        apl_ign = [float(a[t]) for a, l in zip(apl, labels) for t, i in enumerate(l["trial_ignited"]) if i]
        apl_quiet = [float(a[t]) for a, l in zip(apl, labels) for t, i in enumerate(l["trial_ignited"]) if not i]
        per_stimulus[name] = {
            "rule": stim["selected"].rule,
            "sweep_presentation": payloads[0]["sweep_presentation"],
            "features": stim["features"],
            "runs_any_trial_ignited": rate(sum(any(l["trial_ignited"]) for l in labels), len(labels)),
            "runs_trial_mean_label": rate(sum(l["ignited_trial_mean"] for l in labels), len(labels)),
            "trials_ignited": rate(sum(trials), len(trials)),
            "trial_spread_per_seed": [l["trial_spread"] for l in labels],
            "apl_hz_ignited_trials_mean": float(np.mean(apl_ign)) if apl_ign else None,
            "apl_hz_other_trials_mean": float(np.mean(apl_quiet)) if apl_quiet else None,
            **stimulus_statistics(payloads, sides),
        }

    def pooled(labels):
        trials = [t for l in labels for t in l["trial_ignited"]]
        return {"runs_any_trial_ignited": rate(sum(any(l["trial_ignited"]) for l in labels), len(labels)),
                "runs_trial_mean_label": rate(sum(l["ignited_trial_mean"] for l in labels), len(labels)),
                "trials_ignited": rate(sum(trials), len(trials))}

    summary = {
        "prestated_diagnostic": True,
        "is_a_validation": False,
        "has_pass_criterion": False,
        "spec": SPEC,
        "seeds": list(SEEDS),
        "duration_ms": DURATION_MS,
        "trials": TRIALS,
        "pool_side": POOL_SIDE,
        "ignition_label_spread_fraction": IGNITION_SPREAD_FRACTION,
        "active_hz": ACTIVE_HZ,
        "ci_level": CI_LEVEL,
        "per_trial_populations": list(PER_TRIAL_POPULATIONS),
        "stimuli": per_stimulus,
        "pooled": {"all": pooled(all_labels), **{g: pooled(v) for g, v in groups.items()}},
        "neighbour_comparison": neighbour_comparison(results_dir, all_labels),
        "scope_note": (
            "Ten of the sweep's own presentations at baseline weights, ten seeds each. Five of "
            "the six below-25 kHz presentations are one market at five signal strengths. Says "
            "nothing about learned weights, other markets, or mechanism."),
    }
    check_no_verdict(summary)
    _write_json(summary_path(results_dir), summary)
    log("=== Low-drive ignition follow-up (MEASUREMENT; no verdict, no pass criterion) ===")
    log(f"{'stimulus':<22}{'driveHz':>9}{'runs(any trial)':>17}{'trials':>9}{'APL ign/other':>16}")
    for name, s in per_stimulus.items():
        r, t = s["runs_any_trial_ignited"], s["trials_ignited"]
        a1, a2 = s["apl_hz_ignited_trials_mean"], s["apl_hz_other_trials_mean"]
        log(f"{name:<22}{s['total_drive_hz']:>9,.0f}{r['k']:>11}/{r['n']:<5}{t['k']:>4}/{t['n']:<4}"
            f"{('--' if a1 is None else f'{a1:.0f}'):>8}/{('--' if a2 is None else f'{a2:.0f}'):<7}")
    for g, v in summary["pooled"].items():
        r, t = v["runs_any_trial_ignited"], v["trials_ignited"]
        log(f"pooled {g:<10} runs {r['k']}/{r['n']} [{r['ci95_lower']:.3f}, {r['ci95_upper']:.3f}]  "
            f"trials {t['k']}/{t['n']} [{t['ci95_lower']:.3f}, {t['ci95_upper']:.3f}]")
    for name, b in summary["neighbour_comparison"]["bands"].items():
        r = b["runs_trial_mean_label"]
        log(f"neighbour {name:<24} runs {r['k']}/{r['n']}  p(new higher) "
            f"{b['fisher_one_sided_p_new_runs_higher']}  -> {b['reading_runs']}")
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
    log("Low-drive ignition follow-up: PLAN (dry run; nothing is simulated)")
    log("  DIAGNOSTIC, not a validation: is_a_validation false, no pass criterion")
    log(f"  pools: left-hemisphere only, guarded; seeds {SEEDS[0]}-{SEEDS[-1]} ({len(SEEDS)}); "
        f"{DURATION_MS:g} ms x {TRIALS} trials")
    log(f"  {'stimulus':<22}{'sweep presentation':<34}{'price':>6}{'driveHz':>9}")
    for name, s in stimuli.items():
        sel = s["selected"]
        where = f"s={sel.strength:g} seed={sel.market_seed} m={sel.index} {sel.framing}"
        log(f"  {name:<22}{where:<34}{s['quote']:>6.3f}{s['total_drive_hz']:>9,.0f}")
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
