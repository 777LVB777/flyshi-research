#!/usr/bin/env python3
"""Graded-encoding VALIDATION: left-only pools, mirrored NO framing, no balancing.

Pre-stated protocol: docs/design/graded-encoding-left-only-mirrored.md, written
before this code and before any run. Nothing here may be changed to fit a result.

THIS IS A VALIDATION (is_a_validation: true, has_pass_criterion: true). It returns
exactly one verdict from the preregistered vocabulary ACCEPTED / USABLE RANGE /
FAIL. The diagnostic word PASS is not part of that vocabulary and never appears in
its output.

Value set B (frozen): v = 0.56, 0.64, 0.73, 0.83, 0.94. YES presents price at v,
NO presents it at 1-v (mirroring); no balance pool; pools drawn from LEFT-hemisphere
KCs only. Six seeds x five values x two framings = 60 simulations, one presentation
each, one file per (value, framing, seed).

S_s(v) = CIRCUIT(m_yes) - CIRCUIT(m_no) (CIRCUIT-80, per-type mean). Monotonicity is
judged on the six-seed mean (spec section 7); the endpoint and sub-range gates use
the primary seed's contrast vectors against 3 x d_change measured directly from the
five repeat seeds (spec sections 5-6).

Running without --analyze-only or --dry-run executes 60 real Brian2 simulations
and loads the connectome. Importing this file, --dry-run and --analyze-only do
neither.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling runners; import no Brian2 at module level

from flyshi_research.learning import graded_check as gc  # noqa: E402
from flyshi_research.learning.encoder import BALANCE_FEATURE, KCEncoder, NO, YES  # noqa: E402
from flyshi_research.learning.params import OPTION_B_UNBALANCED  # noqa: E402
from flyshi_research.learning.readout import (  # noqa: E402
    circuit_score_difference,
    load_sign_table,
)
from analyze_recruitment_intensity import recruitment_from_rates  # noqa: E402
from run_left_only_pool_diagnostic import (  # noqa: E402
    IGNITION_SPREAD_FRACTION,
    _spread,
    kc_side_map,
    left_kc_ids,
)
from run_left_only_realistic_drive_diagnostic import (  # noqa: E402
    MAX_FILE_BYTES,
    PER_TRIAL_POPULATIONS,
    _present_with_trials,
    _write_json,
)
from run_population_scaling_diagnostic import POPULATIONS, SECONDS_PER_BUILD  # noqa: E402
from run_unbalanced_g_diagnostic import _assert_pools_left_only  # noqa: E402

RESULTS_DIR = HERE / "results"
IDS_PATH = HERE / "neuron_ids_783.json"
SPEC = "docs/design/graded-encoding-left-only-mirrored.md"

# ---- FIXED by the pre-statement (spec sections 3-6); set B frozen 2026-09-27 ------ #
VALUES: Tuple[float, ...] = (0.56, 0.64, 0.73, 0.83, 0.94)
FRAMINGS: Tuple[str, ...] = (YES, NO)
PRIMARY_SEED = 20260316
REPEAT_SEEDS: Tuple[int, ...] = (20260317, 20260318, 20260319, 20260320, 20260321)
SEEDS: Tuple[int, ...] = (PRIMARY_SEED,) + REPEAT_SEEDS
BACKGROUND: Dict[str, float] = {
    "recent_change": 0.0,
    "time_to_resolution": 182.5,
    "liquidity": 0.5,
    "signal": 0.5,
}
POOL_SIDE = "left"
VARIANT = OPTION_B_UNBALANCED
N_KCS_PER_FRAMING = 500
DURATION_MS = 1000.0
TRIALS = 5
SIGN_TABLE = "circuit_80"
AGGREGATION = "type_mean"
NOISE_MARGIN = 3.0
MIN_SUBRANGE_VALUES = 3
MIN_RATE_HZ, MAX_RATE_HZ = 30.0, 150.0

# ---- validation vocabulary and enforcement (spec section 9) ----------------------- #
VERDICTS: Tuple[str, ...] = (gc.Verdict.ACCEPTED.value, gc.Verdict.USABLE_RANGE.value,
                             gc.Verdict.FAIL.value)
FORBIDDEN_WORD = "PASS"  # the diagnostic vocabulary; never valid in a validation

# Planning figure only: 54.4 s between consecutive result files of the left-only
# realistic-drive diagnostic on the author's machine, at this drive level. The older
# 50.5 s figure is also reported. UNVERIFIED elsewhere; never used by the verdict.
SECONDS_PER_SIMULATION = 54.4
SECONDS_PER_SIMULATION_OLD = 50.5


def nominal_rate_hz(value: float) -> float:
    return MIN_RATE_HZ + value * (MAX_RATE_HZ - MIN_RATE_HZ)


def presented_value(value: float, framing: str) -> float:
    """The price value each framing presents: v for YES, 1-v for NO (mirroring)."""
    return value if framing == YES else round(1.0 - value, 12)


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_graded_encoding_left_only_mirrored.py"
    )
    p = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog=f"Exact pre-stated run:\n  {command}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--analyze-only", action="store_true",
                   help="Compute the verdict from existing files; never simulates.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan and the runtime estimate; never simulates.")
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--ids", type=Path, default=IDS_PATH)
    return p


def _key(value: float) -> str:
    return format(value, ".2f").replace(".", "p")


def output_path(value: float, framing: str, seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"graded_left_mirrored_value_{_key(value)}_{framing}_seed_{seed}.json"


def verdict_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "graded_left_mirrored_verdict.json"


def planned_presentations() -> Tuple[Tuple[float, str, int], ...]:
    """Every (value, framing, seed), in run order: repeat seeds first, primary last."""
    return tuple((value, framing, seed)
                 for seed in REPEAT_SEEDS + (PRIMARY_SEED,)
                 for value in VALUES for framing in FRAMINGS)


def missing_presentations(results_dir: Path = RESULTS_DIR) -> List[Tuple[float, str, int]]:
    return [p for p in planned_presentations() if not output_path(*p, results_dir).exists()]


# --------------------------------------------------------------------------- #
# the stimuli (pure data; no Brian2, no connectome) - spec section 3.1
# --------------------------------------------------------------------------- #
def _stimulus_record(stim, pool_ids: Mapping[str, List[int]]) -> dict:
    rates = stim.rates_by_kc_id()
    return {
        "rates_by_kc_id": rates,
        "stimulated_kc_ids": sorted(rates),
        "pools": {name: pool_ids[name] for name in stim.feature_rates_hz},
        "pool_rates_hz": {k: float(v) for k, v in stim.feature_rates_hz.items()},
        "total_drive_hz": float(np.sum(stim.rates_hz)),
    }


def build_pairs(ids_path: Path = IDS_PATH) -> Dict[float, dict]:
    """Every (YES, NO) pair from one left-only encoder, with every section 3.1 check.

    Aborts unless: every drawn KC is left-hemisphere; NO(v) equals YES(1-v)
    bit-for-bit; neither framing carries the balance pool; each drives 500 KCs;
    nothing is clipped; D_YES - D_NO equals 12,000 x (2v - 1) Hz.
    """
    encoder = KCEncoder(left_kc_ids(ids_path))
    _assert_pools_left_only(encoder, ids_path=ids_path)
    pool_ids = {name: sorted(int(i) for i in ids) for name, ids in encoder.pools.items()}
    pairs: Dict[float, dict] = {}
    for value in VALUES:
        pair = encoder.option_b_stimuli({"price": value, **BACKGROUND}, variant=VARIANT)
        mirror = encoder.option_b_stimuli({"price": presented_value(value, NO), **BACKGROUND},
                                          variant=VARIANT).yes
        if not (np.array_equal(pair.no.kc_ids, mirror.kc_ids)
                and np.array_equal(pair.no.rates_hz, mirror.rates_hz)):
            raise RuntimeError(f"v={value}: NO(v) is not YES(1-v) bit-for-bit")
        for framing, stim in ((YES, pair.yes), (NO, pair.no)):
            if BALANCE_FEATURE in stim.feature_rates_hz:
                raise RuntimeError(f"v={value} {framing}: balance pool present")
            if stim.kc_ids.size != N_KCS_PER_FRAMING:
                raise RuntimeError(f"v={value} {framing}: drives {stim.kc_ids.size} KCs, "
                                   f"expected {N_KCS_PER_FRAMING}")
        if pair.was_clipped:
            raise RuntimeError(f"v={value}: a feature value was clipped")
        d_yes = float(np.sum(pair.yes.rates_hz))
        d_no = float(np.sum(pair.no.rates_hz))
        expected = 100 * (nominal_rate_hz(value) - nominal_rate_hz(1.0 - value))
        if not np.isclose(d_yes - d_no, expected, rtol=0.0, atol=1e-6):
            raise RuntimeError(f"v={value}: D_YES - D_NO = {d_yes - d_no:g} Hz, "
                               f"expected {expected:g} Hz")
        pairs[value] = {
            YES: _stimulus_record(pair.yes, pool_ids),
            NO: _stimulus_record(pair.no, pool_ids),
            "d_yes_hz": d_yes,
            "d_no_hz": d_no,
        }
    return pairs


# --------------------------------------------------------------------------- #
# simulation (the only part that constructs the model)
# --------------------------------------------------------------------------- #
def simulate_missing(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
                     log: Callable[[str], None] = print) -> None:
    todo = missing_presentations(results_dir)
    for presentation in planned_presentations():
        if presentation not in todo:
            log(f"Output exists, skipping: {output_path(*presentation, results_dir).name}")
    if not todo:
        return

    from run_population_scaling_diagnostic import _build_population_simulator

    pairs = build_pairs(ids_path)  # every section 3.1 check, before the model is built
    sim = _build_population_simulator()
    for value, framing, seed in todo:
        stim = pairs[value][framing]
        means, trials = _present_with_trials(sim, stim["rates_by_kc_id"], seed,
                                             DURATION_MS, TRIALS)
        _write_json(
            output_path(value, framing, seed, results_dir),
            {
                "value": value,
                "framing": framing,
                "presented_price_value": presented_value(value, framing),
                "nominal_price_rate_hz": stim["pool_rates_hz"]["price"],
                "variant": VARIANT,
                "pool_side": POOL_SIDE,
                "pools": stim["pools"],
                "pool_rates_hz": stim["pool_rates_hz"],
                "n_kcs_driven": len(stim["stimulated_kc_ids"]),
                "total_drive_hz": stim["total_drive_hz"],
                "pair_d_yes_hz": pairs[value]["d_yes_hz"],
                "pair_d_no_hz": pairs[value]["d_no_hz"],
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
        log(f"v={value:.2f} {framing:<3} (price {stim['pool_rates_hz']['price']:.1f} Hz, "
            f"{stim['total_drive_hz']:,.0f} Hz), seed {seed}: "
            f"wrote {output_path(value, framing, seed, results_dir).name}")


# --------------------------------------------------------------------------- #
# the verdict (pure numpy) - spec sections 4-7
# --------------------------------------------------------------------------- #
def change_noise(contrasts: Mapping[int, Sequence[np.ndarray]], a: int, b: int) -> float:
    """d_change(a,b): mean pairwise distance between the five repeat seeds'
    estimates of c(b) - c(a). Measured directly; never derived analytically."""
    changes = [np.asarray(contrasts[seed][b]) - np.asarray(contrasts[seed][a])
               for seed in REPEAT_SEEDS]
    return float(np.mean([gc.euclidean(x, y) for x, y in combinations(changes, 2)]))


@dataclass(frozen=True)
class MirroredResult:
    verdict: str
    scores_by_seed: Dict[int, Tuple[float, ...]]
    seed_mean_scores: Tuple[float, ...]
    monotonic: bool
    direction: str
    endpoint_distance_hz: float
    endpoint_change_noise_hz: float
    endpoint_threshold_hz: float
    endpoint_gate_met: bool
    chosen_subrange: Optional[Tuple[float, float]]
    tied_subranges: Tuple[Tuple[float, float], ...]
    chosen_subrange_distance_hz: Optional[float]
    chosen_subrange_change_noise_hz: Optional[float]
    chosen_subrange_threshold_hz: Optional[float]
    validated_value_range: Optional[Tuple[float, float]]
    reflected_value_range: Optional[Tuple[float, float]]
    change_noise_all_pairs_hz: Dict[str, float]
    fail_reasons: Tuple[str, ...]


def evaluate(pairs_by_seed: Mapping[int, Sequence[Tuple[np.ndarray, np.ndarray]]],
             labels: Sequence[str]) -> MirroredResult:
    """Apply the pre-stated three-outcome rule.

    ``pairs_by_seed``: for each of the six seeds, the (m_yes, m_no) MBON rate
    vectors at each of the five values, in VALUES order.
    """
    if set(pairs_by_seed) != set(SEEDS):
        raise ValueError(f"need exactly the seeds {SEEDS}")
    if any(len(pairs) != len(VALUES) for pairs in pairs_by_seed.values()):
        raise ValueError("every seed needs all five values")
    table = load_sign_table(SIGN_TABLE)
    scores = {
        seed: tuple(float(circuit_score_difference(yes, no, labels, table, AGGREGATION))
                    for yes, no in pairs)
        for seed, pairs in pairs_by_seed.items()
    }
    contrasts = {seed: [np.asarray(yes, dtype=float) - np.asarray(no, dtype=float)
                        for yes, no in pairs]
                 for seed, pairs in pairs_by_seed.items()}
    mean = tuple(float(np.mean([scores[s][i] for s in SEEDS])) for i in range(len(VALUES)))
    monotonic, direction = gc.strictly_monotonic(mean)
    best, tied = gc.select_usable_subrange(mean, MIN_SUBRANGE_VALUES)

    last = len(VALUES) - 1
    primary = contrasts[PRIMARY_SEED]
    endpoint_distance = gc.euclidean(primary[0], primary[last])
    endpoint_noise = change_noise(contrasts, 0, last)
    endpoint_threshold = NOISE_MARGIN * endpoint_noise
    endpoint_met = endpoint_distance >= endpoint_threshold

    chosen = sub_distance = sub_noise = sub_threshold = None
    if best is not None:
        chosen = (VALUES[best.start], VALUES[best.end])
        sub_distance = gc.euclidean(primary[best.start], primary[best.end])
        sub_noise = change_noise(contrasts, best.start, best.end)
        sub_threshold = NOISE_MARGIN * sub_noise

    reasons: List[str] = []
    if not endpoint_met:
        reasons.append(f"endpoint distance {endpoint_distance:.2f} Hz is below its measured "
                       f"threshold {endpoint_threshold:.2f} Hz (3 x {endpoint_noise:.2f} Hz)")
    if best is None:
        reasons.append("no strictly monotonic contiguous sub-range of the seed-mean score "
                       f"spans at least {MIN_SUBRANGE_VALUES} values")
    elif not monotonic and sub_distance < sub_threshold:
        reasons.append(f"chosen sub-range v={chosen[0]:.2f}-{chosen[1]:.2f} distance "
                       f"{sub_distance:.2f} Hz is below its measured threshold "
                       f"{sub_threshold:.2f} Hz")

    if reasons:
        verdict, validated = gc.Verdict.FAIL.value, None
    elif monotonic:
        verdict, validated = gc.Verdict.ACCEPTED.value, (VALUES[0], VALUES[last])
    else:
        verdict, validated = gc.Verdict.USABLE_RANGE.value, chosen
    reflected = (round(1 - validated[1], 12), round(1 - validated[0], 12)) if validated else None

    return MirroredResult(
        verdict=verdict,
        scores_by_seed=scores,
        seed_mean_scores=mean,
        monotonic=monotonic,
        direction=direction,
        endpoint_distance_hz=endpoint_distance,
        endpoint_change_noise_hz=endpoint_noise,
        endpoint_threshold_hz=endpoint_threshold,
        endpoint_gate_met=endpoint_met,
        chosen_subrange=chosen,
        tied_subranges=tuple((VALUES[r.start], VALUES[r.end]) for r in tied),
        chosen_subrange_distance_hz=sub_distance,
        chosen_subrange_change_noise_hz=sub_noise,
        chosen_subrange_threshold_hz=sub_threshold,
        validated_value_range=validated,
        reflected_value_range=reflected,
        change_noise_all_pairs_hz={
            f"{VALUES[i]:.2f}-{VALUES[j]:.2f}": change_noise(contrasts, i, j)
            for i, j in combinations(range(len(VALUES)), 2)
        },
        fail_reasons=tuple(reasons),
    )


# --------------------------------------------------------------------------- #
# recruitment intensity beside the ignition label (every presentation)
# --------------------------------------------------------------------------- #
def presentation_recruitment(payload: Mapping, sides: Mapping[int, str]) -> dict:
    kc_ids = payload["population_ids"]["kenyon_cells"]
    mean = recruitment_from_rates(kc_ids, payload["rates_hz"]["kenyon_cells"],
                                  payload["stimulated_kc_ids"])
    per_trial = [recruitment_from_rates(kc_ids, row, payload["stimulated_kc_ids"])
                 for row in payload["per_trial_rates_hz"]["kenyon_cells"]]
    spread = _spread(payload, sides)
    return {
        "value": payload["value"],
        "framing": payload["framing"],
        "seed": payload["seed"],
        "ignited": bool(spread["overall"] > IGNITION_SPREAD_FRACTION),
        "nonstimulated_kc_active_fraction": spread["overall"],
        "nonstimulated_kc_active_fraction_by_side": {
            k: v for k, v in spread.items() if k != "overall"},
        "recruited_kc_mean_rate_hz": mean["recruited_kc_mean_rate_hz"],
        "recruited_kc_median_rate_hz": mean["recruited_kc_median_rate_hz"],
        "recruited_kc_mean_rate_hz_per_trial": [t["recruited_kc_mean_rate_hz"] for t in per_trial],
        "apl_mean_rate_hz": float(np.mean(payload["rates_hz"]["apl_neurons"])),
    }


# --------------------------------------------------------------------------- #
# validation enforcement (spec section 9) - NOT the diagnostic rules
# --------------------------------------------------------------------------- #
def _keys(obj):
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _keys(v)


def check_validation_output(verdict_file: Mapping) -> None:
    """Raise unless the verdict file obeys the validation rules of spec section 9."""
    if verdict_file.get("is_a_validation") is not True:
        raise ValueError("is_a_validation must be True")
    if verdict_file.get("has_pass_criterion") is not True:
        raise ValueError("has_pass_criterion must be True")
    if verdict_file.get("verdict") not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}, got "
                         f"{verdict_file.get('verdict')!r}")
    if sum(1 for k in _keys(verdict_file) if k == "verdict") != 1:
        raise ValueError("exactly one verdict key is allowed")
    if FORBIDDEN_WORD in json.dumps(verdict_file):
        raise ValueError(f"the diagnostic word {FORBIDDEN_WORD} appears in a validation output")
    if verdict_file.get("spec") != SPEC or list(verdict_file.get("values", ())) != list(VALUES):
        raise ValueError("verdict file does not name the pre-stated spec and value set")


def check_presentation_file(payload: Mapping) -> None:
    """Per-(value, framing, seed) files carry data only, never a verdict."""
    if any(k == "verdict" for k in _keys(payload)):
        raise ValueError("a per-presentation file carries a verdict")


def check_constants() -> None:
    """The runner's gate constants must equal the pre-stated ones (spec section 9.5)."""
    if NOISE_MARGIN != 3.0 or NOISE_MARGIN != gc.NOISE_MARGIN:
        raise ValueError("noise margin differs from the pre-stated factor 3")
    if MIN_SUBRANGE_VALUES != 3 or MIN_SUBRANGE_VALUES != gc.MIN_SUBRANGE_RATES:
        raise ValueError("minimum sub-range differs from the pre-stated three values")
    if VALUES != (0.56, 0.64, 0.73, 0.83, 0.94):
        raise ValueError("value set differs from the frozen set B")
    if SEEDS != (20260316, 20260317, 20260318, 20260319, 20260320, 20260321):
        raise ValueError("seeds differ from the pre-statement")


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #
def analyze(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
            log: Callable[[str], None] = print) -> Optional[dict]:
    check_constants()
    missing = missing_presentations(results_dir)
    if missing:
        log(f"No verdict: missing {len(missing)} of {len(planned_presentations())} "
            "(value, framing, seed) results")
        return None
    planned = build_pairs(ids_path)  # re-runs every section 3.1 check
    sides = kc_side_map(ids_path)

    payloads: Dict[Tuple[float, str, int], dict] = {}
    for value, framing, seed in planned_presentations():
        payload = json.loads(output_path(value, framing, seed, results_dir).read_text())
        check_presentation_file(payload)
        stim = planned[value][framing]
        if (payload["stimulated_kc_ids"] != stim["stimulated_kc_ids"]
                or payload["pool_rates_hz"] != stim["pool_rates_hz"]
                or payload["framing"] != framing or payload["seed"] != seed):
            raise ValueError(f"v={value} {framing} seed {seed}: saved stimulus differs from "
                             "the pre-stated one; no verdict")
        payloads[(value, framing, seed)] = payload

    labels = payloads[(VALUES[0], YES, PRIMARY_SEED)]["mbon_labels"]
    if any(p["mbon_labels"] != labels for p in payloads.values()):
        raise ValueError("MBON label order differs between files; no verdict")

    def mbon(value, framing, seed):
        return np.asarray(payloads[(value, framing, seed)]["rates_hz"]["mbons"], dtype=float)

    result = evaluate({seed: [(mbon(v, YES, seed), mbon(v, NO, seed)) for v in VALUES]
                       for seed in SEEDS}, labels)
    recruitment = [presentation_recruitment(payloads[p], sides)
                   for p in planned_presentations()]

    verdict_file = {
        "prestated_test": True,
        "is_a_validation": True,
        "has_pass_criterion": True,
        "spec": SPEC,
        "verdict": result.verdict,
        "encoder": {"pool_side": POOL_SIDE, "variant": VARIANT, "framing_rule": "mirrored",
                    "balance_pool_presented": False, "pool_seed": 20260401},
        "values": list(VALUES),
        "yes_price_rates_hz": [nominal_rate_hz(v) for v in VALUES],
        "no_price_rates_hz": [nominal_rate_hz(1 - v) for v in VALUES],
        "pair_drive_difference_hz": [planned[v]["d_yes_hz"] - planned[v]["d_no_hz"]
                                     for v in VALUES],
        "primary_seed": PRIMARY_SEED,
        "repeat_seeds": list(REPEAT_SEEDS),
        "scores_by_seed": {str(s): list(v) for s, v in result.scores_by_seed.items()},
        "seed_mean_scores": list(result.seed_mean_scores),
        "monotonic_on_seed_mean": result.monotonic,
        "direction": result.direction,
        "endpoint_distance_hz": result.endpoint_distance_hz,
        "endpoint_change_noise_hz": result.endpoint_change_noise_hz,
        "endpoint_threshold_hz": result.endpoint_threshold_hz,
        "endpoint_gate_met": result.endpoint_gate_met,
        "change_noise_all_pairs_hz": result.change_noise_all_pairs_hz,
        "noise_margin": NOISE_MARGIN,
        "min_subrange_values": MIN_SUBRANGE_VALUES,
        "chosen_subrange_values": list(result.chosen_subrange) if result.chosen_subrange else None,
        "tied_longest_subranges": [list(t) for t in result.tied_subranges],
        "chosen_subrange_distance_hz": result.chosen_subrange_distance_hz,
        "chosen_subrange_change_noise_hz": result.chosen_subrange_change_noise_hz,
        "chosen_subrange_threshold_hz": result.chosen_subrange_threshold_hz,
        "validated_value_range": (list(result.validated_value_range)
                                  if result.validated_value_range else None),
        "reflected_value_range_by_identity": (list(result.reflected_value_range)
                                              if result.reflected_value_range else None),
        "fail_reasons": list(result.fail_reasons),
        "recruitment_by_presentation": recruitment,
        "ignited_presentations": sum(r["ignited"] for r in recruitment),
        "notes": {
            "monotonicity": "judged on the six-seed mean score (spec 7, a dated change); "
                            "distance gates use the primary seed against 3 x d_change "
                            "from the five repeat seeds",
            "reflection": "the reflected interval is validated by the exact identity "
                          "S(1-v) = -S(v), not by a separate measurement",
            "drive": "D_YES - D_NO = 12,000 x (2v - 1) Hz: S confounds price-pool identity "
                     "with total drive; intensity-bias mitigation remains open (spec 2.3)",
            "ignition": "reported, not gated",
        },
    }
    check_validation_output(verdict_file)
    _write_json(verdict_path(results_dir), verdict_file)

    log("=== Graded-encoding validation: left-only, mirrored, no balancing ===")
    log(f"{'v':>5}{'YES Hz':>8}{'NO Hz':>8}{'mean S':>10}  per-seed S")
    for i, v in enumerate(VALUES):
        per_seed = " ".join(f"{result.scores_by_seed[s][i]:8.2f}" for s in SEEDS)
        log(f"{v:>5.2f}{nominal_rate_hz(v):>8.1f}{nominal_rate_hz(1 - v):>8.1f}"
            f"{result.seed_mean_scores[i]:>10.3f}  {per_seed}")
    log(f"seed-mean S strictly monotonic: {result.monotonic} ({result.direction})")
    log(f"endpoint gate: {result.endpoint_distance_hz:.2f} Hz vs "
        f"{result.endpoint_threshold_hz:.2f} Hz (3 x {result.endpoint_change_noise_hz:.2f}): "
        f"{'met' if result.endpoint_gate_met else 'not met'}")
    if result.chosen_subrange and not result.monotonic:
        log(f"chosen sub-range v={result.chosen_subrange[0]:.2f}-{result.chosen_subrange[1]:.2f}: "
            f"{result.chosen_subrange_distance_hz:.2f} Hz vs "
            f"{result.chosen_subrange_threshold_hz:.2f} Hz")
    log("recruitment beside the ignition label (label: ign/con; recruited Hz):")
    for seed in SEEDS:
        cells = []
        for r in (r for r in recruitment if r["seed"] == seed):
            rate = r["recruited_kc_mean_rate_hz"]
            cells.append(f"{r['value']:.2f}{r['framing'][0]}:"
                         f"{'ign' if r['ignited'] else 'con'}"
                         f"({'--' if rate is None else f'{rate:.2f}'})")
        log(f"  {seed}: " + " ".join(cells))
    log(f"ignited presentations: {verdict_file['ignited_presentations']} of {len(recruitment)}")
    for reason in result.fail_reasons:
        log(f"  reason: {reason}")
    log(f"VERDICT: {result.verdict}")
    if result.validated_value_range:
        lo, hi = result.validated_value_range
        log(f"validated v {lo:.2f}-{hi:.2f}; reflected v {result.reflected_value_range[0]:.2f}-"
            f"{result.reflected_value_range[1]:.2f} by identity")
    log(f"Wrote {verdict_path(results_dir).name}")
    return verdict_file


# --------------------------------------------------------------------------- #
# dry run
# --------------------------------------------------------------------------- #
def estimated_seconds(n_todo: int, per_simulation: float = SECONDS_PER_SIMULATION) -> float:
    return n_todo * per_simulation + (SECONDS_PER_BUILD if n_todo else 0.0)


def dry_run(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
            log: Callable[[str], None] = print) -> int:
    check_constants()
    todo = missing_presentations(results_dir)
    total = len(planned_presentations())
    log("Graded-encoding validation (left-only, mirrored, no balancing): DRY RUN")
    log(f"spec: {SPEC} (PRE-STATED; value set B frozen)")
    log("THIS IS A VALIDATION: verdict ACCEPTED / USABLE RANGE / FAIL, produced only "
        f"when all {total} presentations exist")
    try:
        pairs = build_pairs(ids_path)
        log("section 3.1 checks: left-only pools, NO(v) == YES(1-v), no balance pool, "
            "500 KCs per framing, no clipping, drive difference as stated: all hold")
    except (OSError, RuntimeError, KeyError, ValueError) as exc:
        pairs = {}
        log(f"section 3.1 checks could not be completed from {ids_path}: {exc}")
    log(f"{'v':>5}{'YES Hz':>8}{'NO Hz':>8}{'D_YES':>9}{'D_NO':>9}{'D_YES-D_NO':>12}")
    for v in VALUES:
        if v in pairs:
            d_yes, d_no = pairs[v]["d_yes_hz"], pairs[v]["d_no_hz"]
            log(f"{v:>5.2f}{nominal_rate_hz(v):>8.1f}{nominal_rate_hz(1 - v):>8.1f}"
                f"{d_yes:>9,.0f}{d_no:>9,.0f}{d_yes - d_no:>12,.0f}")
    log(f"seeds: primary {PRIMARY_SEED}, repeats {list(REPEAT_SEEDS)} (repeats run first)")
    log(f"presentation: {DURATION_MS:g} ms x {TRIALS} trials; one simulation per "
        "(value, framing, seed)")
    log(f"recorded populations (trial mean): {list(POPULATIONS)}; "
        f"per trial: {list(PER_TRIAL_POPULATIONS)}")
    log(f"planned simulations: {total}  (already done: {total - len(todo)}, "
        f"to run: {len(todo)})")
    log(f"estimated runtime: {estimated_seconds(len(todo)) / 60:.1f} min at "
        f"{SECONDS_PER_SIMULATION:g} s per simulation "
        f"({estimated_seconds(len(todo), SECONDS_PER_SIMULATION_OLD) / 60:.1f} min at "
        f"{SECONDS_PER_SIMULATION_OLD:g} s) + one {SECONDS_PER_BUILD:g} s build; "
        "author's machine, UNVERIFIED elsewhere")
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
    return 0 if analyze(args.results_dir, args.ids) is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
