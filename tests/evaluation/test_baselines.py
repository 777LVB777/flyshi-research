from __future__ import annotations

import inspect

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.evaluation.baselines import (  # noqa: E402
    ALWAYS_BASE_RATE,
    BASELINE_NAMES,
    LOGISTIC_REGRESSION,
    MARKET_PRICE,
    MOMENTUM,
    RANDOM,
    decisions_from_forecasts,
    encoder_feature_names,
    fit_baselines,
    fit_logistic_regression,
    observations_from_markets,
    outcomes_from_markets,
    phase0_feature_matrix,
)
from flyshi_research.evaluation.calibration import (  # noqa: E402
    PlattScaler,
    fit_and_apply_calibration,
)
from flyshi_research.simulator import Action, Decision, Market, MarketObservation  # noqa: E402


FEATURE_NAMES = ("price", "recent_change", "time_to_resolution", "liquidity")


def _training_data():
    observations = tuple(
        MarketObservation(quote=quote) for quote in (0.1, 0.25, 0.4, 0.6, 0.75, 0.9)
    )
    outcomes = np.array([0, 0, 0, 1, 1, 1])
    changes = np.array([-0.05, 0.02, -0.1, 0.1, -0.02, 0.05])
    features = np.column_stack(
        ([o.quote for o in observations], changes, np.full(6, 30.0), np.full(6, 0.5))
    )
    return observations, outcomes, features


def _test_data():
    observations = (MarketObservation(0.2), MarketObservation(0.5), MarketObservation(0.8))
    features = np.array(
        [[0.2, 0.1, 10.0, 0.4], [0.5, -0.2, 20.0, 0.5], [0.8, 0.4, 30.0, 0.6]]
    )
    return observations, features


def test_encoder_feature_names_come_from_encoder_configuration() -> None:
    assert encoder_feature_names() == FEATURE_NAMES
    assert encoder_feature_names(include_optional=True) == FEATURE_NAMES + ("signal",)


def test_phase0_adapters_reuse_simulator_types_and_expose_only_price() -> None:
    markets = [Market(0.7, 0.4, 1), Market(0.2, 0.6, 0)]
    observations = observations_from_markets(markets)
    assert observations == (MarketObservation(0.4), MarketObservation(0.6))
    assert np.array_equal(outcomes_from_markets(markets), [1, 0])
    assert np.array_equal(phase0_feature_matrix(observations), [[0.4], [0.6]])


def test_known_raw_predictions_for_base_price_and_momentum() -> None:
    train_observations, outcomes, train_features = _training_data()
    suite = fit_baselines(train_observations, outcomes, train_features, FEATURE_NAMES, seed=7)
    test_observations, test_features = _test_data()
    forecasts = suite.predict(test_observations, test_features)

    assert tuple(forecasts) == BASELINE_NAMES
    assert forecasts[ALWAYS_BASE_RATE].uncalibrated == pytest.approx([0.5, 0.5, 0.5])
    assert forecasts[MARKET_PRICE].uncalibrated == pytest.approx([0.2, 0.5, 0.8])
    # quote + recent change, clipped to [0,1]
    assert forecasts[MOMENTUM].uncalibrated == pytest.approx([0.3, 0.3, 1.0])


def test_random_baseline_is_seeded_and_independent_of_quotes() -> None:
    train_observations, outcomes, train_features = _training_data()
    suite_a = fit_baselines(train_observations, outcomes, train_features, FEATURE_NAMES, seed=19)
    suite_b = fit_baselines(train_observations, outcomes, train_features, FEATURE_NAMES, seed=19)
    observations, features = _test_data()
    changed_observations = tuple(MarketObservation(1.0 - o.quote) for o in observations)
    changed_features = features.copy()
    changed_features[:, 0] = [o.quote for o in changed_observations]
    a = suite_a.predict(observations, features)[RANDOM].uncalibrated
    b = suite_b.predict(changed_observations, changed_features)[RANDOM].uncalibrated
    assert np.array_equal(a, b)


def test_numpy_logistic_regression_learns_a_simple_separation() -> None:
    features = np.array([[-3.0], [-2.0], [-1.0], [1.0], [2.0], [3.0]])
    outcomes = np.array([0, 0, 0, 1, 1, 1])
    model = fit_logistic_regression(features, outcomes, l2=0.1)
    predictions = model.predict_proba([[-2.5], [2.5]])
    assert predictions[0] < 0.5 < predictions[1]
    assert predictions[0] < predictions[1]


def test_every_baseline_uses_the_same_shared_calibrator_and_keeps_raw_output() -> None:
    train_observations, outcomes, train_features = _training_data()
    suite = fit_baselines(train_observations, outcomes, train_features, FEATURE_NAMES, seed=5)
    observations, features = _test_data()
    forecasts = suite.predict(observations, features)
    assert set(suite.calibrators) == set(BASELINE_NAMES)
    for name in BASELINE_NAMES:
        assert isinstance(suite.calibrators[name], PlattScaler)
        assert forecasts[name].calibrated == pytest.approx(
            suite.calibrators[name].predict(forecasts[name].uncalibrated)
        )
        assert forecasts[name].selected(use_calibration=False) == pytest.approx(
            forecasts[name].uncalibrated
        )


def test_shared_calibration_fits_train_only_and_reports_uncalibrated() -> None:
    result = fit_and_apply_calibration(
        [0.1, 0.3, 0.7, 0.9], [0, 0, 1, 1], [0.2, 0.8]
    )
    assert np.array_equal(result.uncalibrated_test, [0.2, 0.8])
    assert result.calibrated_test[0] < result.calibrated_test[1]
    assert np.all((result.calibrated_test >= 0.0) & (result.calibrated_test <= 1.0))


def test_no_baseline_can_receive_or_read_test_labels() -> None:
    """The fitting API has no test split; held-out prediction has no label argument."""
    assert "test" not in inspect.signature(fit_baselines).parameters
    assert "outcomes" not in inspect.signature(
        # Bound predict signature is (observations, features), with no labels.
        type(fit_baselines(*_training_data(), FEATURE_NAMES)).predict
    ).parameters

    class PoisonObservation:
        def __init__(self, quote: float) -> None:
            self.quote = quote

        @property
        def outcome(self):
            raise AssertionError("a held-out outcome was accessed")

    train_observations, outcomes, train_features = _training_data()
    suite = fit_baselines(train_observations, outcomes, train_features, FEATURE_NAMES, seed=11)
    _, features = _test_data()
    poison = tuple(PoisonObservation(q) for q in (0.2, 0.5, 0.8))
    forecasts = suite.predict(poison, features)  # type: ignore[arg-type]
    assert set(forecasts) == set(BASELINE_NAMES)


def test_base_rate_changes_with_training_labels_only() -> None:
    observations, _, features = _training_data()
    low = fit_baselines(observations, [0, 0, 0, 0, 0, 1], features, FEATURE_NAMES)
    high = fit_baselines(observations, [0, 1, 1, 1, 1, 1], features, FEATURE_NAMES)
    test_observations, test_features = _test_data()
    assert low.predict(test_observations, test_features)[ALWAYS_BASE_RATE].uncalibrated == pytest.approx(
        [1.0 / 6.0] * 3
    )
    assert high.predict(test_observations, test_features)[ALWAYS_BASE_RATE].uncalibrated == pytest.approx(
        [5.0 / 6.0] * 3
    )


def test_phase0_price_only_schema_runs_all_baselines() -> None:
    markets = [Market(0.2, 0.1, 0), Market(0.4, 0.4, 0), Market(0.6, 0.6, 1), Market(0.8, 0.9, 1)]
    observations = observations_from_markets(markets)
    suite = fit_baselines(
        observations,
        outcomes_from_markets(markets),
        phase0_feature_matrix(observations),
        ("price",),
    )
    forecasts = suite.predict(observations, phase0_feature_matrix(observations))
    assert set(forecasts) == set(BASELINE_NAMES)
    assert forecasts[MOMENTUM].uncalibrated == pytest.approx(forecasts[MARKET_PRICE].uncalibrated)


def test_decisions_from_forecasts_reuses_simulator_types() -> None:
    observations = [MarketObservation(0.4), MarketObservation(0.6), MarketObservation(0.5)]
    decisions = decisions_from_forecasts([0.7, 0.2, 0.5], observations)
    assert decisions == (
        Decision(0.7, Action.YES),
        Decision(0.2, Action.NO),
        Decision(0.5, Action.ABSTAIN),
    )


def test_unknown_or_misaligned_feature_schema_is_rejected() -> None:
    observations, outcomes, features = _training_data()
    with pytest.raises(ValueError, match="not used by the encoder"):
        fit_baselines(observations, outcomes, features, ("price", "x", "a", "b"))
    bad = features.copy()
    bad[:, 0] += 0.01
    with pytest.raises(ValueError, match="price feature"):
        fit_baselines(observations, outcomes, bad, FEATURE_NAMES)
