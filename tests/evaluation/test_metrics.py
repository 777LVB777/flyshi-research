from __future__ import annotations

from math import log

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.evaluation.metrics import (  # noqa: E402
    abstention_rate,
    bootstrap_confidence_interval,
    brier_score,
    expected_calibration_error,
    log_loss,
    maximum_drawdown,
    per_market_pnl,
    pnl_after_fees_and_spread,
    reliability_diagram,
    turnover,
)
from flyshi_research.simulator import Action  # noqa: E402


def test_brier_score_hand_calculation() -> None:
    # ((0.2 - 0)^2 + (0.8 - 1)^2) / 2 = 0.04
    assert brier_score([0.2, 0.8], [0, 1]) == pytest.approx(0.04)


def test_log_loss_hand_calculation() -> None:
    expected = -(log(0.8) + log(0.7)) / 2.0
    assert log_loss([0.8, 0.3], [1, 0]) == pytest.approx(expected)


def test_log_loss_clips_endpoint_probabilities_without_mutating_input() -> None:
    probabilities = np.array([0.0, 1.0])
    assert log_loss(probabilities, [1, 0], epsilon=1e-6) == pytest.approx(-log(1e-6))
    assert np.array_equal(probabilities, [0.0, 1.0])


def test_reliability_diagram_and_ece_hand_calculation() -> None:
    # Equal-width bins: [0,.5) has p-bar=.1/y-bar=.5; [.5,1] has .8/1.
    result = reliability_diagram([0.0, 0.2, 0.6, 1.0], [0, 1, 1, 1], n_bins=2)
    assert np.array_equal(result.bin_edges, [0.0, 0.5, 1.0])
    assert np.array_equal(result.counts, [2, 2])
    assert result.mean_probabilities == pytest.approx([0.1, 0.8])
    assert result.observed_frequencies == pytest.approx([0.5, 1.0])
    # .5 * |.1-.5| + .5 * |.8-1| = .3
    assert result.expected_calibration_error == pytest.approx(0.3)
    assert expected_calibration_error([0.0, 0.2, 0.6, 1.0], [0, 1, 1, 1], n_bins=2) == pytest.approx(0.3)


def test_reliability_diagram_reports_empty_bins_as_nan() -> None:
    result = reliability_diagram([0.1, 0.2], [0, 1], n_bins=3)
    assert np.array_equal(result.counts, [2, 0, 0])
    assert np.isnan(result.mean_probabilities[1:]).all()
    assert np.isnan(result.observed_frequencies[1:]).all()


def test_pnl_after_fees_and_spread_hand_calculation() -> None:
    actions = [Action.YES, Action.NO, Action.ABSTAIN]
    per_market = per_market_pnl(
        [0.4, 0.3, 0.5],
        [1, 0, 1],
        actions,
        fee_per_trade=0.01,
        spread=0.02,
    )
    # YES: 1-.4-.01 fee-.01 half-spread=.58; NO: .3-0-.01-.01=.28.
    assert per_market == pytest.approx([0.58, 0.28, 0.0])
    assert pnl_after_fees_and_spread(
        [0.4, 0.3, 0.5], [1, 0, 1], actions, fee_per_trade=0.01, spread=0.02
    ) == pytest.approx(0.86)


def test_pnl_costs_and_profit_scale_with_stake() -> None:
    assert per_market_pnl(
        [0.4], [1], [Action.YES], fee_per_trade=0.01, spread=0.02, stake=2.0
    ) == pytest.approx([1.16])


def test_maximum_drawdown_hand_calculation_and_empty_series() -> None:
    # Cumulative including initial 0: 0,2,1,-2,2,1; max peak-to-trough = 4.
    assert maximum_drawdown([2, -1, -3, 4, -1]) == pytest.approx(4.0)
    assert maximum_drawdown([]) == 0.0


def test_turnover_and_abstention_rate_hand_calculation() -> None:
    actions = [Action.YES, Action.NO, Action.ABSTAIN]
    assert turnover(actions, stake=[2.0, 3.0, 5.0]) == pytest.approx(5.0)
    assert abstention_rate(actions) == pytest.approx(1.0 / 3.0)


def test_bootstrap_interval_is_seeded_and_resamples_linked_market_rows() -> None:
    probabilities = np.array([0.2, 0.8, 0.6, 0.4])
    outcomes = np.array([0, 1, 1, 0])
    first = bootstrap_confidence_interval(
        (probabilities, outcomes), brier_score, n_resamples=200, seed=17
    )
    second = bootstrap_confidence_interval(
        (probabilities, outcomes), brier_score, n_resamples=200, seed=17
    )
    assert first == second
    assert first.estimate == pytest.approx(brier_score(probabilities, outcomes))
    assert first.lower <= first.estimate <= first.upper
    assert first.resampling_unit == "market"


def test_bootstrap_keeps_dependent_rows_from_one_market_together() -> None:
    # Each market's two rows are identical. Cluster resampling therefore cannot
    # create a replicate mean other than 0, 5, or 10.
    values = np.array([0.0, 0.0, 10.0, 10.0])
    interval = bootstrap_confidence_interval(
        values,
        np.mean,
        n_resamples=100,
        seed=3,
        market_ids=["a", "a", "b", "b"],
    )
    assert interval.estimate == 5.0
    assert interval.lower == 0.0
    assert interval.upper == 10.0


def test_bootstrap_interval_has_roughly_nominal_synthetic_coverage() -> None:
    """Deterministic Monte Carlo check, tolerant of ordinary finite-sample error."""
    truth = 0.35
    generator = np.random.default_rng(20260921)
    covered = 0
    repetitions = 80
    for repetition in range(repetitions):
        sample = generator.binomial(1, truth, size=200)
        interval = bootstrap_confidence_interval(
            sample,
            np.mean,
            confidence_level=0.90,
            n_resamples=400,
            seed=5000 + repetition,
        )
        covered += interval.lower <= truth <= interval.upper
    coverage = covered / repetitions
    assert 0.80 <= coverage <= 0.98


@pytest.mark.parametrize(
    "function,args",
    [
        (brier_score, ([0.2], [2])),
        (log_loss, ([float("nan")], [0])),
        (turnover, (["YES"],)),
        (abstention_rate, ([],)),
    ],
)
def test_invalid_metric_inputs_raise(function, args) -> None:
    with pytest.raises(ValueError):
        function(*args)
