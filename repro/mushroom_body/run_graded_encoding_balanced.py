#!/usr/bin/env python3
"""Balanced Option-B graded-encoding re-validation.

Pre-stated protocol: docs/design/graded-encoding-balanced.md. Running without
``--analyze-only`` executes 60 real Brian2 simulations and loads the connectome.
Importing this file and analysis-only operation do neither.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Tuple

import numpy as np

from flyshi_research.learning import graded_check as gc
from flyshi_research.learning.encoder import BALANCE_FEATURE, KCEncoder
from flyshi_research.learning.readout import circuit_score_difference, load_sign_table

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
NOMINAL_RATES = gc.PRESTATED_RATES_HZ
PRIMARY_SEED = 20260316
NOISE_SEEDS = (20260317, 20260318, 20260319, 20260320, 20260321)
FIXED_FEATURES = {
    "recent_change": 0.0,
    "time_to_resolution": 182.5,
    "liquidity": 0.5,
    "signal": 0.5,
}


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_graded_encoding_balanced.py"
    )
    p = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog=f"Exact pre-stated run:\n  {command}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--analyze-only", action="store_true")
    return p


def output_path(
    value: float, results_dir: Path = RESULTS_DIR, seed: int = PRIMARY_SEED
) -> Path:
    key = format(value, ".2f").replace(".", "p")
    return results_dir / f"graded_encoding_balanced_value_{key}_seed_{seed}.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, separators=(",", ":")))
    partial.replace(path)


def simulate_missing(log: Callable[[str], None] = print) -> None:
    """Run missing pairs. This is the only function that constructs the model."""
    # Noise repeats deliberately run before the held-out primary seed.
    ordered = tuple((seed, value) for seed in NOISE_SEEDS + (PRIMARY_SEED,) for value in VALUES)
    todo = [(seed, value) for seed, value in ordered if not output_path(value, seed=seed).exists()]
    for seed, value in ordered:
        if (seed, value) not in todo:
            log(f"Output exists, skipping: {output_path(value, seed=seed).name}")
    if not todo:
        return

    from run_first_learning_test import FastRunnerSimulator
    from flyshi_research.learning.first_learning import ExperimentConfig

    sim = FastRunnerSimulator(ExperimentConfig())
    encoder = KCEncoder(sim.kc_ids)
    for seed, value in todo:
        pair = encoder.option_b_stimuli({"price": value, **FIXED_FEATURES})
        yes_total = float(np.sum(pair.yes.rates_hz))
        no_total = float(np.sum(pair.no.rates_hz))
        if not np.isclose(yes_total, no_total, atol=1e-10, rtol=0.0):
            raise RuntimeError("Option B total-drive invariant failed; aborting without a verdict")
        _, yes_mbon = sim.present(pair.yes.rates_by_kc_id(), seed, 1000.0, 5)
        _, no_mbon = sim.present(pair.no.rates_by_kc_id(), seed, 1000.0, 5)
        nominal = NOMINAL_RATES[VALUES.index(value)]
        _write_json(
            output_path(value, seed=seed),
            {
                "feature_value": value,
                "nominal_prebalance_yes_price_rate_hz": nominal,
                "yes_feature_rates_hz": pair.yes.feature_rates_hz,
                "no_feature_rates_hz": pair.no.feature_rates_hz,
                "yes_total_drive_hz": yes_total,
                "no_total_drive_hz": no_total,
                "balance_feature": BALANCE_FEATURE,
                "mbon_labels": list(sim.mbon_labels),
                "yes_mbon_rates_hz": np.asarray(yes_mbon, dtype=float).tolist(),
                "no_mbon_rates_hz": np.asarray(no_mbon, dtype=float).tolist(),
                "seed": seed,
                "duration_ms": 1000.0,
                "trials": 5,
            },
        )
        log(
            f"seed {seed}, value {value:.2f} (nominal {nominal:g} Hz): "
            f"wrote {output_path(value, seed=seed).name}"
        )


@dataclass(frozen=True)
class BalancedResult:
    verdict: gc.Verdict
    scores: Tuple[float, ...]
    monotonic: bool
    direction: str
    endpoint_distance_hz: float
    endpoint_noise_hz: float
    endpoint_threshold_hz: float
    validated_range_hz: Optional[Tuple[float, float]]
    chosen_subrange_hz: Optional[Tuple[float, float]]
    chosen_subrange_distance_hz: Optional[float]
    chosen_subrange_noise_hz: Optional[float]
    chosen_subrange_threshold_hz: Optional[float]
    fail_reasons: Tuple[str, ...]


def _rate_vectors(payload: Mapping[str, object]) -> Tuple[np.ndarray, np.ndarray]:
    """The raw (YES, NO) MBON rate vectors of one value/seed result."""
    return (
        np.asarray(payload["yes_mbon_rates_hz"], dtype=float),
        np.asarray(payload["no_mbon_rates_hz"], dtype=float),
    )


def _contrast(payload: Mapping[str, object]) -> np.ndarray:
    """c(v) = m_yes(v) - m_no(v). Used for the Euclidean gates only: it is a signed
    contrast, not a rate vector, so it is never passed to the readout (spec 3)."""
    yes, no = _rate_vectors(payload)
    return yes - no


def change_noise_floor(
    repeats: Mapping[int, Sequence[np.ndarray]], start: int, end: int
) -> float:
    """Mean pairwise distance between repeated estimates of one contrast change."""
    changes = [repeats[seed][end] - repeats[seed][start] for seed in NOISE_SEEDS]
    distances = [
        gc.euclidean(changes[i], changes[j])
        for i in range(len(changes))
        for j in range(i + 1, len(changes))
    ]
    return float(np.mean(distances))


def evaluate_balanced(
    primary: Sequence[Tuple[np.ndarray, np.ndarray]],
    repeats: Mapping[int, Sequence[np.ndarray]],
    labels: Sequence[str],
) -> BalancedResult:
    """Apply the pre-stated rule with pair-specific measured noise thresholds.

    ``primary``: the (YES, NO) rate-vector pair per feature value, at the primary
    seed. The pre-stated score is ``S(v) = CIRCUIT(m_yes(v)) - CIRCUIT(m_no(v))``
    (spec 3), so each framing is scored as the rate vector it is and the two scores
    are subtracted. ``repeats``: contrast vectors per noise seed - they feed only
    the Euclidean noise floors, which need no score.
    """
    if len(primary) != len(VALUES) or set(repeats) != set(NOISE_SEEDS):
        raise ValueError("need all five primary values and all five noise seeds")
    if any(len(vectors) != len(VALUES) for vectors in repeats.values()):
        raise ValueError("each noise seed must contain all five values")
    table = load_sign_table("circuit_80")
    scores = tuple(
        circuit_score_difference(yes, no, labels, table, "type_mean") for yes, no in primary
    )
    contrasts = tuple(yes - no for yes, no in primary)
    monotonic, direction = gc.strictly_monotonic(scores)
    best, _ = gc.select_usable_subrange(scores)

    endpoint_distance = gc.euclidean(contrasts[0], contrasts[-1])
    endpoint_noise = change_noise_floor(repeats, 0, len(VALUES) - 1)
    endpoint_threshold = gc.NOISE_MARGIN * endpoint_noise
    endpoint_ok = endpoint_distance >= endpoint_threshold

    chosen = sub_distance = sub_noise = sub_threshold = None
    if best is not None:
        chosen = (NOMINAL_RATES[best.start], NOMINAL_RATES[best.end])
        sub_distance = gc.euclidean(contrasts[best.start], contrasts[best.end])
        sub_noise = change_noise_floor(repeats, best.start, best.end)
        sub_threshold = gc.NOISE_MARGIN * sub_noise

    fail_reasons = []
    if not endpoint_ok:
        fail_reasons.append(
            f"endpoint distance {endpoint_distance:.2f} Hz is below its measured "
            f"threshold {endpoint_threshold:.2f} Hz"
        )
    if best is None:
        fail_reasons.append("no strictly monotonic contiguous sub-range spans at least three values")
    elif best.n_rates < len(VALUES) and sub_distance < sub_threshold:
        fail_reasons.append(
            f"chosen sub-range {chosen[0]:g}-{chosen[1]:g} Hz distance "
            f"{sub_distance:.2f} Hz is below its measured threshold {sub_threshold:.2f} Hz"
        )

    if fail_reasons:
        verdict = gc.Verdict.FAIL
        validated = None
    elif monotonic:
        verdict = gc.Verdict.ACCEPTED
        validated = (NOMINAL_RATES[0], NOMINAL_RATES[-1])
    else:
        verdict = gc.Verdict.USABLE_RANGE
        validated = chosen
    return BalancedResult(
        verdict=verdict,
        scores=scores,
        monotonic=monotonic,
        direction=direction,
        endpoint_distance_hz=endpoint_distance,
        endpoint_noise_hz=endpoint_noise,
        endpoint_threshold_hz=endpoint_threshold,
        validated_range_hz=validated,
        chosen_subrange_hz=chosen,
        chosen_subrange_distance_hz=sub_distance,
        chosen_subrange_noise_hz=sub_noise,
        chosen_subrange_threshold_hz=sub_threshold,
        fail_reasons=tuple(fail_reasons),
    )


def analyze(log: Callable[[str], None] = print, results_dir: Path = RESULTS_DIR):
    required = tuple((seed, value) for seed in NOISE_SEEDS + (PRIMARY_SEED,) for value in VALUES)
    missing = [
        (seed, value)
        for seed, value in required
        if not output_path(value, results_dir, seed=seed).exists()
    ]
    if missing:
        log(f"Cannot analyse: missing {len(missing)} value/seed results")
        return None
    payloads = {
        seed: [json.loads(output_path(v, results_dir, seed=seed).read_text()) for v in VALUES]
        for seed in NOISE_SEEDS + (PRIMARY_SEED,)
    }
    labels = payloads[PRIMARY_SEED][0]["mbon_labels"]
    if any(
        payload["mbon_labels"] != labels
        for by_value in payloads.values()
        for payload in by_value
    ):
        raise ValueError("MBON label order differs between value files")
    contrasts = {
        seed: [_contrast(payload) for payload in by_value]
        for seed, by_value in payloads.items()
    }
    # The primary seed keeps its raw YES/NO vectors: the score is the difference of
    # the two framings' scores (spec 3), not the score of their contrast.
    primary_pairs = [_rate_vectors(payload) for payload in payloads[PRIMARY_SEED]]
    result = evaluate_balanced(
        primary_pairs,
        {seed: contrasts[seed] for seed in NOISE_SEEDS},
        labels,
    )
    log("=== Balanced graded-encoding re-validation ===")
    for value, rate, score in zip(VALUES, NOMINAL_RATES, result.scores):
        log(f"value={value:.2f} nominal_prebalance_rate={rate:g}Hz contrast_score={score:.3f}")
    log(
        f"endpoint contrast distance: {result.endpoint_distance_hz:.2f} Hz; "
        f"noise {result.endpoint_noise_hz:.2f} Hz; "
        f"threshold {result.endpoint_threshold_hz:.2f} Hz"
    )
    log(f"VERDICT: {result.verdict.value}")
    verdict = {
        "prestated_test": True,
        "verdict": result.verdict.value,
        "feature_values": list(VALUES),
        "nominal_prebalance_rates_hz": list(NOMINAL_RATES),
        "contrast_scores": list(result.scores),
        "monotonic_all_five_values": result.monotonic,
        "direction": result.direction,
        "endpoint_contrast_distance_hz": result.endpoint_distance_hz,
        "endpoint_change_noise_hz": result.endpoint_noise_hz,
        "endpoint_distance_threshold_hz": result.endpoint_threshold_hz,
        "noise_seeds": list(NOISE_SEEDS),
        "all_pair_change_noise_hz": {
            f"{VALUES[i]:.2f}-{VALUES[j]:.2f}": change_noise_floor(
                {seed: contrasts[seed] for seed in NOISE_SEEDS}, i, j
            )
            for i in range(len(VALUES))
            for j in range(i + 1, len(VALUES))
        },
        "validated_nominal_rate_range_hz": (
            list(result.validated_range_hz) if result.validated_range_hz else None
        ),
        "validated_feature_value_range": (
            [VALUES[NOMINAL_RATES.index(result.validated_range_hz[0])],
             VALUES[NOMINAL_RATES.index(result.validated_range_hz[1])]]
            if result.validated_range_hz else None
        ),
        "chosen_subrange_nominal_rate_hz": (
            list(result.chosen_subrange_hz) if result.chosen_subrange_hz else None
        ),
        "chosen_subrange_distance_hz": result.chosen_subrange_distance_hz,
        "chosen_subrange_change_noise_hz": result.chosen_subrange_noise_hz,
        "chosen_subrange_threshold_hz": result.chosen_subrange_threshold_hz,
        "fail_reasons": list(result.fail_reasons),
    }
    _write_json(results_dir / "graded_encoding_balanced_verdict.json", verdict)
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.analyze_only:
        simulate_missing()
    return 0 if analyze() is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
