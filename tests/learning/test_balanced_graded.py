from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import graded_check as gc  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "repro" / "mushroom_body" / "run_graded_encoding_balanced.py"
DOC = REPO / "docs" / "design" / "graded-encoding-balanced.md"


def load_runner():
    spec = importlib.util.spec_from_file_location("balanced_graded_runner_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def weighted_label(sign: int = 0) -> str:
    """A label the CIRCUIT-80 table weights: ``sign`` +1/-1 picks that sign, 0 any."""
    weights = gc.load_sign_table("circuit_80").weights
    return next(name for name, weight in weights.items()
                if (weight == sign if sign else weight != 0))


def write_fake_value_files(runner, directory: Path, values, no_rate: float = 0.0,
                           sign: int = 0) -> None:
    """``values`` are YES rates; ``no_rate`` is the NO rate of every instance. A
    ``no_rate`` above the YES rates makes the contrast NEGATIVE, as the real balanced
    data is at some values."""
    label = weighted_label(sign)
    seeds = runner.NOISE_SEEDS + (runner.PRIMARY_SEED,)
    for seed_index, seed in enumerate(seeds):
        # Small seed-dependent slope makes the measured change noise nonzero.
        slope_noise = (seed_index - 2) * 0.05 if seed != runner.PRIMARY_SEED else 0.0
        for value_index, (value, mbon_value) in enumerate(zip(runner.VALUES, values)):
            payload = {
                "feature_value": value,
                "mbon_labels": [label],
                "yes_mbon_rates_hz": [float(mbon_value + slope_noise * value_index)],
                "no_mbon_rates_hz": [float(no_rate)],
            }
            runner.output_path(value, directory, seed=seed).write_text(json.dumps(payload))


def test_balanced_spec_pins_three_outcomes_and_feature_value_axis() -> None:
    text = " ".join(DOC.read_text().split())
    for needle in (
        "**Status: PRE-STATED; NOT RUN.**",
        "**SUPERSEDED**",
        "0.00, 0.25, 0.50, 0.75, 1.00",
        "nominal, pre-balance YES price-pool rate",
        "**ACCEPTED**",
        "**USABLE RANGE**",
        "**FAIL**",
        "longest strictly monotonic **contiguous** sub-range",
        "there is no fallback",
        "`d_AA = 5.10 Hz` is **not used",
        "`sqrt(2) × d_AA`",
        "d_change(a,b)",
        "50` dedicated noise-floor simulations",
        "60 results",
    ):
        assert needle in text


def test_balanced_analysis_fake_that_should_pass_and_fake_that_must_not(tmp_path) -> None:
    runner = load_runner()
    passing = tmp_path / "passing"
    passing.mkdir()
    write_fake_value_files(runner, passing, [0.0, 10.0, 20.0, 30.0, 40.0])
    passed = runner.analyze(log=lambda _: None, results_dir=passing)
    assert passed.verdict is gc.Verdict.ACCEPTED
    assert passed.endpoint_noise_hz > 0.0
    assert passed.endpoint_threshold_hz == pytest.approx(3.0 * passed.endpoint_noise_hz)

    failing = tmp_path / "failing"
    failing.mkdir()
    write_fake_value_files(runner, failing, [5.0, 5.0, 5.0, 5.0, 5.0])
    assert runner.analyze(log=lambda _: None, results_dir=failing).verdict is gc.Verdict.FAIL


def test_analyzer_refuses_verdict_without_dedicated_noise_files(tmp_path) -> None:
    runner = load_runner()
    table = gc.load_sign_table("circuit_80")
    label = next(name for name, weight in table.weights.items() if weight != 0)
    for value in runner.VALUES:
        runner.output_path(value, tmp_path).write_text(
            json.dumps(
                {
                    "mbon_labels": [label],
                    "yes_mbon_rates_hz": [value],
                    "no_mbon_rates_hz": [0.0],
                }
            )
        )
    assert runner.analyze(log=lambda _: None, results_dir=tmp_path) is None


# ---- REGRESSION: the contrast is negative wherever NO fired harder --------------- #
def test_analysis_handles_negative_contrasts(tmp_path) -> None:
    """The spec's S(v) = CIRCUIT(m_yes) - CIRCUIT(m_no) is defined for any rates. The
    contrast m_yes - m_no is negative wherever NO fired harder, so scoring it directly
    hit the readout's ``rates must be >= 0`` guard and crashed the analysis after all
    60 simulations had already run."""
    runner = load_runner()
    directory = tmp_path / "negative"
    directory.mkdir()
    # every YES rate is below the NO rate, on an approach-like (+1) MBON:
    # all five contrasts, and therefore all five scores, are negative
    write_fake_value_files(runner, directory, [0.0, 10.0, 20.0, 30.0, 40.0],
                           no_rate=100.0, sign=1)
    result = runner.analyze(log=lambda _: None, results_dir=directory)
    assert result is not None  # no ValueError
    assert all(score < 0 for score in result.scores)
    assert result.verdict is gc.Verdict.ACCEPTED  # still strictly monotonic


def test_scores_are_the_difference_of_the_two_framing_scores(tmp_path) -> None:
    """Pre-stated definition (spec section 3), checked against hand arithmetic: a
    constant NO offset shifts every score by the same amount and cannot change the
    shape of the sequence."""
    runner = load_runner()
    plain, offset = tmp_path / "plain", tmp_path / "offset"
    plain.mkdir(), offset.mkdir()
    yes_rates = [0.0, 10.0, 20.0, 30.0, 40.0]
    write_fake_value_files(runner, plain, yes_rates, no_rate=0.0)
    write_fake_value_files(runner, offset, yes_rates, no_rate=100.0)
    a = runner.analyze(log=lambda _: None, results_dir=plain)
    b = runner.analyze(log=lambda _: None, results_dir=offset)
    weight = gc.load_sign_table("circuit_80").weights[weighted_label()]
    for plain_score, offset_score in zip(a.scores, b.scores):
        assert offset_score == pytest.approx(plain_score - weight * 100.0)
    # the Euclidean gates use the contrast, which the offset leaves unchanged
    assert b.endpoint_distance_hz == pytest.approx(a.endpoint_distance_hz)
    assert b.endpoint_threshold_hz == pytest.approx(a.endpoint_threshold_hz)


def test_evaluate_balanced_takes_yes_no_pairs_not_contrasts() -> None:
    """The primary sequence must be scored from the raw rate vectors; passing a
    contrast vector where a rate vector belongs is what produced the crash."""
    runner = load_runner()
    labels = [weighted_label(sign=1)]
    pairs = [(np.array([float(v)]), np.array([100.0])) for v in (0.0, 10.0, 20.0, 30.0, 40.0)]
    repeats = {
        seed: [np.array([float(v) - 100.0 + 0.1 * index]) for v in (0.0, 10.0, 20.0, 30.0, 40.0)]
        for index, seed in enumerate(runner.NOISE_SEEDS)
    }
    result = runner.evaluate_balanced(pairs, repeats, labels)
    assert len(result.scores) == 5 and all(score < 0 for score in result.scores)
    with pytest.raises((ValueError, TypeError)):
        runner.evaluate_balanced([p[0] - p[1] for p in pairs], repeats, labels)
