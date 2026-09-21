"""Shared probability calibration for neural and non-neural methods.

The shared step is Platt scaling on the logit of a method's raw probability::

    calibrated = sigmoid(slope * logit(raw_probability) + intercept)

The two parameters are fitted from *training outcomes only* by Newton updates
on regularised binary log loss.  Raw probabilities are clipped to
``[1e-15, 1 - 1e-15]`` before taking the logit.  The tiny fixed L2 penalty is a
numerical safeguard, not a searched hyperparameter.  Every method must call
``fit_and_apply_calibration`` with the same settings.  Its return value always
contains both calibrated and uncalibrated predictions so both can be reported.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PROBABILITY_EPSILON = 1e-15


def _probabilities(values: object, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(arr)) or np.any((arr < 0.0) | (arr > 1.0)):
        raise ValueError(f"{name} must contain finite probabilities in [0, 1]")
    return arr


def _outcomes(values: object, expected_size: int) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1 or arr.size != expected_size:
        raise ValueError("outcomes must be one-dimensional and match predictions")
    if not np.all(np.isfinite(arr)) or np.any((arr != 0.0) & (arr != 1.0)):
        raise ValueError("outcomes must contain only 0 and 1")
    return arr


def _sigmoid(values: np.ndarray) -> np.ndarray:
    """Overflow-safe sigmoid."""
    out = np.empty_like(values, dtype=np.float64)
    nonnegative = values >= 0.0
    out[nonnegative] = 1.0 / (1.0 + np.exp(-values[nonnegative]))
    exp_values = np.exp(values[~nonnegative])
    out[~nonnegative] = exp_values / (1.0 + exp_values)
    return out


def _logit(probabilities: np.ndarray, epsilon: float) -> np.ndarray:
    clipped = np.clip(probabilities, epsilon, 1.0 - epsilon)
    return np.log(clipped) - np.log1p(-clipped)


@dataclass(frozen=True)
class PlattScaler:
    """Fitted two-parameter probability calibrator."""

    slope: float
    intercept: float
    epsilon: float = PROBABILITY_EPSILON

    def predict(self, probabilities: object) -> np.ndarray:
        raw = _probabilities(probabilities, "probabilities")
        return _sigmoid(self.slope * _logit(raw, self.epsilon) + self.intercept)


def fit_platt_scaler(
    probabilities: object,
    outcomes: object,
    *,
    l2: float = 1e-6,
    max_iter: int = 100,
    tolerance: float = 1e-10,
    epsilon: float = PROBABILITY_EPSILON,
) -> PlattScaler:
    """Fit Platt scaling using training predictions and training labels only.

    ``l2`` is applied to both parameters so all-zero/all-one training outcomes
    and constant raw predictions still have a finite solution.  These defaults
    are fixed across methods and are not tuned per baseline.
    """
    raw = _probabilities(probabilities, "probabilities")
    y = _outcomes(outcomes, raw.size)
    if not np.isfinite(l2) or l2 <= 0.0:
        raise ValueError("l2 must be finite and > 0")
    if max_iter < 1:
        raise ValueError("max_iter must be >= 1")
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("tolerance must be finite and > 0")
    if not 0.0 < epsilon < 0.5:
        raise ValueError("epsilon must be in (0, 0.5)")

    design = np.column_stack((_logit(raw, epsilon), np.ones(raw.size)))
    parameters = np.zeros(2, dtype=np.float64)
    regularizer = np.eye(2, dtype=np.float64) * l2

    for _ in range(max_iter):
        fitted = _sigmoid(design @ parameters)
        gradient = design.T @ (fitted - y) + l2 * parameters
        weights = np.maximum(fitted * (1.0 - fitted), 1e-12)
        hessian = design.T @ (weights[:, None] * design) + regularizer
        step = np.linalg.solve(hessian, gradient)
        parameters -= step
        if float(np.max(np.abs(step))) <= tolerance:
            break

    if not np.all(np.isfinite(parameters)):
        raise RuntimeError("Platt scaling did not produce finite parameters")
    return PlattScaler(float(parameters[0]), float(parameters[1]), epsilon)


@dataclass(frozen=True, eq=False)
class CalibratedPredictions:
    """Raw and calibrated forecasts for the same train/test split."""

    uncalibrated_train: np.ndarray
    uncalibrated_test: np.ndarray
    calibrated_train: np.ndarray
    calibrated_test: np.ndarray
    scaler: PlattScaler


def fit_and_apply_calibration(
    train_probabilities: object,
    train_outcomes: object,
    test_probabilities: object,
    **fit_kwargs: object,
) -> CalibratedPredictions:
    """Fit on the training split, then transform train and test predictions.

    No test outcomes are accepted.  This is the single shared calibration entry
    point for neural and non-neural methods.  The uncalibrated arrays remain in
    the result for the design's mandatory uncalibrated report.
    """
    train = _probabilities(train_probabilities, "train_probabilities")
    test = _probabilities(test_probabilities, "test_probabilities")
    scaler = fit_platt_scaler(train, train_outcomes, **fit_kwargs)
    return CalibratedPredictions(
        uncalibrated_train=train.copy(),
        uncalibrated_test=test.copy(),
        calibrated_train=scaler.predict(train),
        calibrated_test=scaler.predict(test),
        scaler=scaler,
    )
