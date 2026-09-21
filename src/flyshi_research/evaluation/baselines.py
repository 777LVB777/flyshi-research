"""Conventional forecast baselines on one explicit train/test split.

Fitting accepts training labels only.  Prediction accepts
:class:`~flyshi_research.simulator.MarketObservation` objects and feature rows,
but no test labels.  All methods use the exact same supplied rows and the shared
Platt calibration function.  Both raw and calibrated test forecasts are kept.

The logistic model uses exactly the feature columns supplied to the encoder.
Feature names are checked against ``EncoderParams.features``; Phase 0 currently
exposes only ``price``, while the planned study supplies all four required
features (and optionally ``signal`` for synthetic markets).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Tuple

import numpy as np

from flyshi_research.learning.params import EncoderParams
from flyshi_research.simulator import Action, Decision, Market, MarketObservation

from .calibration import PlattScaler, fit_and_apply_calibration

RANDOM = "random"
ALWAYS_BASE_RATE = "always_base_rate"
MARKET_PRICE = "market_price"
MOMENTUM = "momentum"
LOGISTIC_REGRESSION = "logistic_regression"
BASELINE_NAMES = (RANDOM, ALWAYS_BASE_RATE, MARKET_PRICE, MOMENTUM, LOGISTIC_REGRESSION)

_RANDOM_TEST_STREAM_XOR = 0x9E3779B9


def encoder_feature_names(*, include_optional: bool = False) -> Tuple[str, ...]:
    """Canonical feature names from the actual encoder configuration."""
    return tuple(
        spec.name for spec in EncoderParams().features if include_optional or spec.required
    )


def observations_from_markets(markets: Sequence[Market]) -> Tuple[MarketObservation, ...]:
    """Expose only public quotes from simulator markets; hidden state is dropped."""
    return tuple(MarketObservation(quote=float(market.quote)) for market in markets)


def outcomes_from_markets(markets: Sequence[Market]) -> np.ndarray:
    """Extract resolved labels for the training/evaluation boundary."""
    return np.asarray([market.outcome for market in markets], dtype=np.int64)


def phase0_feature_matrix(observations: Sequence[MarketObservation]) -> np.ndarray:
    """Feature matrix for Phase 0, whose complete information set is ``price``."""
    return np.asarray([[observation.quote] for observation in observations], dtype=np.float64)


def _outcomes(values: object, size: int) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1 or arr.size != size:
        raise ValueError("train_outcomes must be one-dimensional and match training rows")
    if not np.all(np.isfinite(arr)) or np.any((arr != 0.0) & (arr != 1.0)):
        raise ValueError("train_outcomes must contain only 0 and 1")
    return arr


def _quotes(observations: Sequence[MarketObservation]) -> np.ndarray:
    if not observations:
        raise ValueError("observations must not be empty")
    quotes = np.asarray([observation.quote for observation in observations], dtype=np.float64)
    if not np.all(np.isfinite(quotes)) or np.any((quotes < 0.0) | (quotes > 1.0)):
        raise ValueError("observation quotes must be finite probabilities in [0, 1]")
    return quotes


def _features(
    values: object, size: int, feature_names: Sequence[str]
) -> Tuple[np.ndarray, Tuple[str, ...]]:
    names = tuple(feature_names)
    if not names or len(set(names)) != len(names):
        raise ValueError("feature_names must be non-empty and unique")
    allowed = {spec.name for spec in EncoderParams().features}
    unknown = set(names) - allowed
    if unknown:
        raise ValueError(f"features not used by the encoder: {sorted(unknown)}")
    if "price" not in names:
        raise ValueError("feature_names must include the encoder's price feature")
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape != (size, len(names)):
        raise ValueError("feature matrix shape must be (number of observations, number of names)")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("features must be finite")
    return matrix, names


def _sigmoid(values: np.ndarray) -> np.ndarray:
    out = np.empty_like(values, dtype=np.float64)
    nonnegative = values >= 0.0
    out[nonnegative] = 1.0 / (1.0 + np.exp(-values[nonnegative]))
    exponent = np.exp(values[~nonnegative])
    out[~nonnegative] = exponent / (1.0 + exponent)
    return out


@dataclass(frozen=True, eq=False)
class LogisticRegressionModel:
    """NumPy binary logistic regression with train-only standardisation."""

    coefficients: np.ndarray
    intercept: float
    feature_mean: np.ndarray
    feature_scale: np.ndarray

    def predict_proba(self, features: object) -> np.ndarray:
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != self.coefficients.size:
            raise ValueError("features have the wrong number of columns")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("features must be finite")
        standardized = (matrix - self.feature_mean) / self.feature_scale
        return _sigmoid(standardized @ self.coefficients + self.intercept)


def fit_logistic_regression(
    features: object,
    outcomes: object,
    *,
    l2: float = 1.0,
    max_iter: int = 100,
    tolerance: float = 1e-10,
) -> LogisticRegressionModel:
    """Fit binary logistic regression by Newton/IRLS updates.

    The intercept is unpenalised and the coefficients receive fixed L2=1.0.
    This default is an **unverified placeholder** to freeze or tune using
    training data only before the preregistered study; scikit-learn is not used.
    """
    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("features must be a non-empty two-dimensional matrix")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("features must be finite")
    y = _outcomes(outcomes, matrix.shape[0])
    if not np.isfinite(l2) or l2 <= 0.0:
        raise ValueError("l2 must be finite and > 0")
    if max_iter < 1 or tolerance <= 0.0:
        raise ValueError("max_iter and tolerance must be positive")

    mean = np.mean(matrix, axis=0)
    scale = np.std(matrix, axis=0)
    scale = np.where(scale > 0.0, scale, 1.0)
    standardized = (matrix - mean) / scale
    design = np.column_stack((np.ones(matrix.shape[0]), standardized))
    parameters = np.zeros(design.shape[1], dtype=np.float64)
    penalty = np.diag(np.concatenate(([0.0], np.full(matrix.shape[1], l2))))

    for _ in range(max_iter):
        fitted = _sigmoid(design @ parameters)
        gradient = design.T @ (fitted - y) + penalty @ parameters
        weights = np.maximum(fitted * (1.0 - fitted), 1e-12)
        hessian = design.T @ (weights[:, None] * design) + penalty
        step = np.linalg.pinv(hessian) @ gradient
        parameters -= step
        if float(np.max(np.abs(step))) <= tolerance:
            break
    if not np.all(np.isfinite(parameters)):
        raise RuntimeError("logistic regression did not produce finite parameters")
    return LogisticRegressionModel(parameters[1:], float(parameters[0]), mean, scale)


def _momentum_forecast(
    quotes: np.ndarray, features: np.ndarray, feature_names: Tuple[str, ...]
) -> np.ndarray:
    """Quote plus recent quoted-probability change, clipped to [0, 1].

    Phase 0 has no recent-change field, so its momentum baseline reduces to the
    market-price baseline.  The lookback defining ``recent_change`` remains an
    unverified design choice in ``EncoderParams``.
    """
    if "recent_change" not in feature_names:
        return quotes.copy()
    change = features[:, feature_names.index("recent_change")]
    return np.clip(quotes + change, 0.0, 1.0)


@dataclass(frozen=True, eq=False)
class BaselineForecast:
    """Test forecasts with mandatory raw and calibrated versions."""

    name: str
    uncalibrated: np.ndarray
    calibrated: np.ndarray

    def selected(self, *, use_calibration: bool = True) -> np.ndarray:
        return self.calibrated.copy() if use_calibration else self.uncalibrated.copy()


@dataclass(frozen=True, eq=False)
class FittedBaselineSuite:
    """Five fitted baselines and train-only calibrators for one feature schema."""

    feature_names: Tuple[str, ...]
    base_rate: float
    logistic_model: LogisticRegressionModel
    calibrators: Mapping[str, PlattScaler]
    random_test_seed: int

    def predict(
        self,
        observations: Sequence[MarketObservation],
        features: object,
    ) -> Dict[str, BaselineForecast]:
        """Predict a held-out split.  Deliberately accepts no outcome labels."""
        quotes = _quotes(observations)
        matrix, names = _features(features, quotes.size, self.feature_names)
        if names != self.feature_names:
            raise AssertionError("stored feature schema changed unexpectedly")
        raw: Dict[str, np.ndarray] = {
            RANDOM: np.random.default_rng(self.random_test_seed).random(quotes.size),
            ALWAYS_BASE_RATE: np.full(quotes.size, self.base_rate),
            MARKET_PRICE: quotes.copy(),
            MOMENTUM: _momentum_forecast(quotes, matrix, names),
            LOGISTIC_REGRESSION: self.logistic_model.predict_proba(matrix),
        }
        return {
            name: BaselineForecast(name, values, self.calibrators[name].predict(values))
            for name, values in raw.items()
        }


def fit_baselines(
    train_observations: Sequence[MarketObservation],
    train_outcomes: object,
    train_features: object,
    feature_names: Sequence[str],
    *,
    seed: int = 0,
    logistic_l2: float = 1.0,
) -> FittedBaselineSuite:
    """Fit every baseline and its shared calibration step on one training split.

    The returned suite has no path to test labels.  Random training/test streams
    are separate deterministic streams derived from ``seed``.
    """
    quotes = _quotes(train_observations)
    matrix, names = _features(train_features, quotes.size, feature_names)
    y = _outcomes(train_outcomes, quotes.size)
    price_column = matrix[:, names.index("price")]
    if not np.allclose(price_column, quotes, rtol=0.0, atol=1e-12):
        raise ValueError("the price feature must equal MarketObservation.quote")

    logistic = fit_logistic_regression(matrix, y, l2=logistic_l2)
    train_raw: Dict[str, np.ndarray] = {
        RANDOM: np.random.default_rng(seed).random(quotes.size),
        ALWAYS_BASE_RATE: np.full(quotes.size, float(np.mean(y))),
        MARKET_PRICE: quotes.copy(),
        MOMENTUM: _momentum_forecast(quotes, matrix, names),
        LOGISTIC_REGRESSION: logistic.predict_proba(matrix),
    }
    # Supplying the same arrays for train/test here fits each scaler and returns
    # its object.  The shared function is identical to the one neural forecasts use.
    calibrators = {
        name: fit_and_apply_calibration(values, y, values).scaler
        for name, values in train_raw.items()
    }
    return FittedBaselineSuite(
        feature_names=names,
        base_rate=float(np.mean(y)),
        logistic_model=logistic,
        calibrators=calibrators,
        random_test_seed=int(seed) ^ _RANDOM_TEST_STREAM_XOR,
    )


def decisions_from_forecasts(
    probabilities: object,
    observations: Sequence[MarketObservation],
    *,
    abstain_margin: float = 0.0,
) -> Tuple[Decision, ...]:
    """Turn forecasts into simulator Decisions with one shared edge rule.

    Choose YES above ``quote + margin``, NO below ``quote - margin``, and ABSTAIN
    otherwise.  The margin must be selected from training data only.
    """
    forecasts = np.asarray(probabilities, dtype=np.float64)
    quotes = _quotes(observations)
    if forecasts.ndim != 1 or forecasts.size != quotes.size:
        raise ValueError("probabilities must match observations")
    if not np.all(np.isfinite(forecasts)) or np.any((forecasts < 0.0) | (forecasts > 1.0)):
        raise ValueError("probabilities must be finite and in [0, 1]")
    if not np.isfinite(abstain_margin) or abstain_margin < 0.0:
        raise ValueError("abstain_margin must be finite and non-negative")
    decisions = []
    for probability, quote in zip(forecasts, quotes):
        if probability > quote + abstain_margin:
            action = Action.YES
        elif probability < quote - abstain_margin:
            action = Action.NO
        else:
            action = Action.ABSTAIN
        decisions.append(Decision(float(probability), action))
    return tuple(decisions)
