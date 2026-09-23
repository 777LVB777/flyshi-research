#!/usr/bin/env python3
"""Unbalanced single-framing score diagnostic: does g(v) vary monotonically?

Pre-stated protocol: docs/design/unbalanced-single-framing-diagnostic.md, written
before this code and before any run. Nothing here may be changed to fit a result.

g(v) = CIRCUIT(m_yes(v)) for the UNBALANCED mirrored encoder: the YES framing
only, price pool varying, the four midpoint features present as a 400-KC 90 Hz
background, no balancing pool presented. Five values x six seeds = 30 simulations.

This is a DIAGNOSTIC, not a validation: it cannot authorise the encoder for any
experiment. Its verdict vocabulary is deliberately PASS/FAIL, separate from the
preregistered graded tests' ACCEPTED / USABLE RANGE / FAIL.

Running without ``--analyze-only`` or ``--dry-run`` executes 30 real Brian2
simulations and loads the connectome. Importing this file, ``--dry-run`` and
``--analyze-only`` do neither.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from flyshi_research.learning import graded_check as gc
from flyshi_research.learning.encoder import BALANCE_FEATURE, KCEncoder
from flyshi_research.learning.params import OPTION_B_UNBALANCED
from flyshi_research.learning.readout import circuit_score, load_sign_table

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"

# ---- everything below is FIXED by the pre-statement (spec sections 2-5) -------- #
VALUES: Tuple[float, ...] = (0.05, 0.22, 0.41, 0.63, 0.88)
SEEDS: Tuple[int, ...] = (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
FIXED_FEATURES: Dict[str, float] = {
    "recent_change": 0.0,
    "time_to_resolution": 182.5,
    "liquidity": 0.5,
    "signal": 0.5,
}
DURATION_MS = 1000.0
TRIALS = 5
SIGN_TABLE = "circuit_80"
AGGREGATION = "type_mean"
NOISE_MARGIN = gc.NOISE_MARGIN  # 3.0, the same factor the graded specs use
PASS, FAIL = "PASS", "FAIL"

# Planning figure only, from the completed balanced run on the author's machine
# (30 result files spanning 2,931 s of wall clock for 60 simulations) and the
# fast-runner log (44-48 s per 1000 ms x 5-trial run). UNVERIFIED for any other
# machine; it is never used by the verdict.
SECONDS_PER_SIMULATION = 50.5
SECONDS_PER_BUILD = 4.0


def nominal_rate_hz(value: float, min_rate_hz: float = 30.0, max_rate_hz: float = 150.0) -> float:
    """The price pool's rate at this feature value (linear, as the encoder maps it)."""
    return min_rate_hz + value * (max_rate_hz - min_rate_hz)


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_unbalanced_g_diagnostic.py"
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
    return p


def output_path(value: float, results_dir: Path = RESULTS_DIR, seed: int = SEEDS[0]) -> Path:
    key = format(value, ".2f").replace(".", "p")
    return results_dir / f"unbalanced_g_value_{key}_seed_{seed}.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, separators=(",", ":")))
    partial.replace(path)


def planned_pairs() -> Tuple[Tuple[int, float], ...]:
    """Every (seed, value) the pre-statement requires, in run order."""
    return tuple((seed, value) for seed in SEEDS for value in VALUES)


def missing_pairs(results_dir: Path = RESULTS_DIR) -> List[Tuple[int, float]]:
    """The planned pairs with no result file yet; the runner is restartable."""
    return [
        (seed, value)
        for seed, value in planned_pairs()
        if not output_path(value, results_dir, seed=seed).exists()
    ]


# --------------------------------------------------------------------------- #
# simulation (the only part that constructs the model)
# --------------------------------------------------------------------------- #
def simulate_missing(results_dir: Path = RESULTS_DIR, log: Callable[[str], None] = print) -> None:
    todo = missing_pairs(results_dir)
    for seed, value in planned_pairs():
        if (seed, value) not in todo:
            log(f"Output exists, skipping: {output_path(value, results_dir, seed=seed).name}")
    if not todo:
        return

    from run_first_learning_test import FastRunnerSimulator
    from flyshi_research.learning.first_learning import ExperimentConfig

    sim = FastRunnerSimulator(ExperimentConfig())
    encoder = KCEncoder(sim.kc_ids)
    for seed, value in todo:
        # The unbalanced variant's YES stimulus: feature pools only, no balancing
        # pool. Feature pools are the encoder's usual seeded pools, so they are
        # identical to those of the balanced run and the two are comparable.
        pair = encoder.option_b_stimuli({"price": value, **FIXED_FEATURES},
                                        variant=OPTION_B_UNBALANCED)
        stimulus = pair.yes
        if BALANCE_FEATURE in stimulus.feature_rates_hz:
            raise RuntimeError("balancing pool present in the unbalanced stimulus; aborting")
        _, mbon = sim.present(stimulus.rates_by_kc_id(), seed, DURATION_MS, TRIALS)
        _write_json(
            output_path(value, results_dir, seed=seed),
            {
                "feature_value": value,
                "nominal_price_pool_rate_hz": nominal_rate_hz(value),
                "option_b_variant": OPTION_B_UNBALANCED,
                "framing": "YES",
                "feature_rates_hz": stimulus.feature_rates_hz,
                "total_drive_hz": float(np.sum(stimulus.rates_hz)),
                "n_kcs_driven": int(stimulus.rates_hz.size),
                "mbon_labels": list(sim.mbon_labels),
                "yes_mbon_rates_hz": np.asarray(mbon, dtype=float).tolist(),
                "seed": seed,
                "duration_ms": DURATION_MS,
                "trials": TRIALS,
            },
        )
        log(
            f"seed {seed}, value {value:.2f} (price pool {nominal_rate_hz(value):g} Hz): "
            f"wrote {output_path(value, results_dir, seed=seed).name}"
        )


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DiagnosticResult:
    verdict: str
    mean_scores: Tuple[float, ...]
    per_seed_scores: Dict[int, Tuple[float, ...]]
    monotonic: bool
    direction: str
    same_stimulus_noise_hz: Tuple[float, ...]
    endpoint_distance_hz: float
    endpoint_noise_hz: float
    low_endpoint_noise_hz: float
    high_endpoint_noise_hz: float
    threshold_hz: float
    fail_reasons: Tuple[str, ...]


def mean_pairwise_distance(vectors: Sequence[np.ndarray]) -> float:
    return float(np.mean([gc.euclidean(a, b) for a, b in combinations(vectors, 2)]))


def evaluate_diagnostic(
    vectors: Mapping[int, Sequence[np.ndarray]], labels: Sequence[str]
) -> DiagnosticResult:
    """Apply the pre-stated rule (spec section 5).

    ``vectors[seed][i]`` is the MBON rate vector at ``VALUES[i]``. Monotonicity is
    judged on the SIX-SEED MEAN, not on one seed, and the endpoint noise is the
    LARGER of the two endpoint same-stimulus noises; both are pre-stated choices.
    """
    if set(vectors) != set(SEEDS):
        raise ValueError("need exactly the six pre-stated seeds")
    if any(len(v) != len(VALUES) for v in vectors.values()):
        raise ValueError("each seed must carry all five values")
    table = load_sign_table(SIGN_TABLE)

    per_seed = {
        seed: tuple(circuit_score(v, labels, table, AGGREGATION).score for v in by_value)
        for seed, by_value in vectors.items()
    }
    mean_scores = tuple(
        float(np.mean([per_seed[seed][i] for seed in SEEDS])) for i in range(len(VALUES))
    )
    monotonic, direction = gc.strictly_monotonic(mean_scores)

    noise = tuple(
        mean_pairwise_distance([vectors[seed][i] for seed in SEEDS]) for i in range(len(VALUES))
    )
    endpoint_distance = float(
        np.mean([gc.euclidean(vectors[seed][-1], vectors[seed][0]) for seed in SEEDS])
    )
    low, high = noise[0], noise[-1]
    endpoint_noise = max(low, high)
    threshold = NOISE_MARGIN * endpoint_noise

    fail_reasons: List[str] = []
    if not monotonic:
        fail_reasons.append(
            "the six-seed mean score sequence is not strictly monotonic across the five values"
        )
    if endpoint_distance < threshold:
        fail_reasons.append(
            f"endpoint distance {endpoint_distance:.2f} Hz is below its measured "
            f"threshold {threshold:.2f} Hz ({NOISE_MARGIN:g} x {endpoint_noise:.2f} Hz)"
        )
    return DiagnosticResult(
        verdict=FAIL if fail_reasons else PASS,
        mean_scores=mean_scores,
        per_seed_scores=per_seed,
        monotonic=monotonic,
        direction=direction,
        same_stimulus_noise_hz=noise,
        endpoint_distance_hz=endpoint_distance,
        endpoint_noise_hz=endpoint_noise,
        low_endpoint_noise_hz=low,
        high_endpoint_noise_hz=high,
        threshold_hz=threshold,
        fail_reasons=tuple(fail_reasons),
    )


def analyze(
    log: Callable[[str], None] = print, results_dir: Path = RESULTS_DIR
) -> Optional[DiagnosticResult]:
    missing = missing_pairs(results_dir)
    if missing:
        log(f"Cannot analyse: missing {len(missing)} of {len(planned_pairs())} value/seed results")
        return None
    payloads = {
        seed: [json.loads(output_path(v, results_dir, seed=seed).read_text()) for v in VALUES]
        for seed in SEEDS
    }
    labels = payloads[SEEDS[0]][0]["mbon_labels"]
    if any(p["mbon_labels"] != labels for by_value in payloads.values() for p in by_value):
        raise ValueError("MBON label order differs between result files")
    vectors = {
        seed: [np.asarray(p["yes_mbon_rates_hz"], dtype=float) for p in by_value]
        for seed, by_value in payloads.items()
    }
    result = evaluate_diagnostic(vectors, labels)

    log("=== Unbalanced single-framing score diagnostic (DIAGNOSTIC, not a validation) ===")
    for value, mean, noise in zip(VALUES, result.mean_scores, result.same_stimulus_noise_hz):
        log(f"value={value:.2f} price_pool={nominal_rate_hz(value):6.1f}Hz "
            f"mean_g={mean:10.3f}  same-stimulus noise={noise:8.2f} Hz")
    for seed in SEEDS:
        log(f"  seed {seed}: " + ", ".join(f"{s:.2f}" for s in result.per_seed_scores[seed]))
    log(f"endpoint distance {result.endpoint_distance_hz:.2f} Hz; endpoint noise "
        f"{result.endpoint_noise_hz:.2f} Hz (low {result.low_endpoint_noise_hz:.2f}, "
        f"high {result.high_endpoint_noise_hz:.2f}); threshold {result.threshold_hz:.2f} Hz")
    log(f"monotonic (six-seed mean): {result.monotonic} ({result.direction})")
    for reason in result.fail_reasons:
        log(f"  fail: {reason}")
    log(f"VERDICT: {result.verdict}")

    _write_json(
        results_dir / "unbalanced_g_diagnostic_verdict.json",
        {
            "prestated_diagnostic": True,
            "is_a_validation": False,
            "spec": "docs/design/unbalanced-single-framing-diagnostic.md",
            "verdict": result.verdict,
            "feature_values": list(VALUES),
            "nominal_price_pool_rates_hz": [nominal_rate_hz(v) for v in VALUES],
            "seeds": list(SEEDS),
            "mean_scores": list(result.mean_scores),
            "per_seed_scores": {str(s): list(v) for s, v in result.per_seed_scores.items()},
            "monotonic_six_seed_mean": result.monotonic,
            "direction": result.direction,
            "same_stimulus_noise_hz": list(result.same_stimulus_noise_hz),
            "endpoint_distance_hz": result.endpoint_distance_hz,
            "low_endpoint_noise_hz": result.low_endpoint_noise_hz,
            "high_endpoint_noise_hz": result.high_endpoint_noise_hz,
            "endpoint_noise_hz": result.endpoint_noise_hz,
            "noise_margin": NOISE_MARGIN,
            "threshold_hz": result.threshold_hz,
            "fail_reasons": list(result.fail_reasons),
        },
    )
    return result


# --------------------------------------------------------------------------- #
# dry run
# --------------------------------------------------------------------------- #
def dry_run(results_dir: Path = RESULTS_DIR, log: Callable[[str], None] = print) -> int:
    todo = missing_pairs(results_dir)
    total = len(planned_pairs())
    seconds = len(todo) * SECONDS_PER_SIMULATION + (SECONDS_PER_BUILD if todo else 0.0)
    log("Unbalanced single-framing score diagnostic: DRY RUN")
    log(f"spec: docs/design/unbalanced-single-framing-diagnostic.md (PRE-STATED)")
    log(f"encoder: {OPTION_B_UNBALANCED}, YES framing only, no balancing pool")
    log(f"fixed features: {FIXED_FEATURES} (400 KCs at 90 Hz background)")
    log("values and nominal price-pool rates:")
    for value in VALUES:
        log(f"  v={value:.2f} -> {nominal_rate_hz(value):6.1f} Hz")
    log(f"seeds: {list(SEEDS)}")
    log(f"presentation: {DURATION_MS:g} ms x {TRIALS} trials")
    log(f"planned simulations: {total}  (already done: {total - len(todo)}, to run: {len(todo)})")
    log(f"estimated runtime: {seconds / 60:.1f} min "
        f"({SECONDS_PER_SIMULATION:g} s per simulation + one {SECONDS_PER_BUILD:g} s build; "
        "measured on the author's machine during the balanced run, UNVERIFIED elsewhere)")
    log(f"verdict rule: six-seed mean strictly monotonic AND endpoint distance >= "
        f"{NOISE_MARGIN:g} x max(endpoint same-stimulus noise)")
    log("No connectome loaded, no model built, no simulation run, nothing written.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.dry_run and args.analyze_only:
        raise SystemExit("--dry-run and --analyze-only are mutually exclusive")
    if args.dry_run:
        return dry_run(args.results_dir)
    if not args.analyze_only:
        simulate_missing(args.results_dir)
    return 0 if analyze(results_dir=args.results_dir) is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
