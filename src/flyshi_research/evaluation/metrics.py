"""Pure-numpy forecast, calibration, trading, and uncertainty metrics.

Bootstrap intervals resample *markets*, never individual trades.  If there is
one row per market, omit ``market_ids``.  If a market has multiple dependent
trade rows, pass repeated ``market_ids``; the complete block of rows for each
sampled market is retained together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple, Union

import numpy as np

from flyshi_research.simulator import Action

LOG_LOSS_EPSILON = 1e-15


def _one_dimensional(values: object, name: str, *, allow_empty: bool = False) -> np.ndarray:
    arr = np.asarray(values)
    if arr.ndim != 1 or (arr.size == 0 and not allow_empty):
        qualifier = "a one-dimensional array" if allow_empty else "a non-empty one-dimensional array"
        raise ValueError(f"{name} must be {qualifier}")
    return arr


def _probabilities(values: object) -> np.ndarray:
    arr = _one_dimensional(values, "probabilities").astype(np.float64)
    if not np.all(np.isfinite(arr)) or np.any((arr < 0.0) | (arr > 1.0)):
        raise ValueError("probabilities must be finite and in [0, 1]")
    return arr


def _outcomes(values: object, size: int) -> np.ndarray:
    arr = _one_dimensional(values, "outcomes").astype(np.float64)
    if arr.size != size:
        raise ValueError("outcomes and probabilities must have the same length")
    if not np.all(np.isfinite(arr)) or np.any((arr != 0.0) & (arr != 1.0)):
        raise ValueError("outcomes must contain only 0 and 1")
    return arr


def brier_score(probabilities: object, outcomes: object) -> float:
    """Mean squared error of binary probability forecasts."""
    p = _probabilities(probabilities)
    y = _outcomes(outcomes, p.size)
    return float(np.mean((p - y) ** 2))


def log_loss(
    probabilities: object, outcomes: object, *, epsilon: float = LOG_LOSS_EPSILON
) -> float:
    """Mean binary log loss after clipping probabilities to ``[epsilon, 1-epsilon]``.

    The default ``epsilon=1e-15`` keeps endpoint forecasts finite while changing
    ordinary probabilities negligibly.  The original forecasts are not mutated.
    """
    if not 0.0 < epsilon < 0.5:
        raise ValueError("epsilon must be in (0, 0.5)")
    p = _probabilities(probabilities)
    y = _outcomes(outcomes, p.size)
    clipped = np.clip(p, epsilon, 1.0 - epsilon)
    return float(-np.mean(y * np.log(clipped) + (1.0 - y) * np.log1p(-clipped)))


@dataclass(frozen=True, eq=False)
class ReliabilityDiagram:
    """Equal-width calibration bins and expected calibration error.

    Bins are ``[edge_i, edge_(i+1))`` except the final bin, which includes 1.
    Empty bins have ``NaN`` mean forecast and outcome rate and zero count.  ECE
    is the count-weighted mean absolute gap over non-empty bins.
    """

    bin_edges: np.ndarray
    counts: np.ndarray
    mean_probabilities: np.ndarray
    observed_frequencies: np.ndarray
    expected_calibration_error: float


def reliability_diagram(
    probabilities: object, outcomes: object, *, n_bins: int = 10
) -> ReliabilityDiagram:
    """Return equal-width reliability-diagram data and ECE."""
    if not isinstance(n_bins, int) or isinstance(n_bins, bool) or n_bins < 1:
        raise ValueError("n_bins must be an integer >= 1")
    p = _probabilities(probabilities)
    y = _outcomes(outcomes, p.size)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # floor implements left-inclusive bins; min puts p=1 in the final bin.
    assignments = np.minimum((p * n_bins).astype(np.int64), n_bins - 1)
    counts = np.bincount(assignments, minlength=n_bins).astype(np.int64)
    mean_p = np.full(n_bins, np.nan, dtype=np.float64)
    mean_y = np.full(n_bins, np.nan, dtype=np.float64)
    for bin_index in range(n_bins):
        selected = assignments == bin_index
        if np.any(selected):
            mean_p[bin_index] = float(np.mean(p[selected]))
            mean_y[bin_index] = float(np.mean(y[selected]))
    occupied = counts > 0
    ece = float(np.sum(counts[occupied] * np.abs(mean_p[occupied] - mean_y[occupied])) / p.size)
    return ReliabilityDiagram(edges, counts, mean_p, mean_y, ece)


def expected_calibration_error(
    probabilities: object, outcomes: object, *, n_bins: int = 10
) -> float:
    """Count-weighted equal-width expected calibration error."""
    return reliability_diagram(probabilities, outcomes, n_bins=n_bins).expected_calibration_error


def _actions(values: Sequence[Action]) -> Tuple[Action, ...]:
    actions = tuple(values)
    if not actions:
        raise ValueError("actions must not be empty")
    if any(not isinstance(action, Action) for action in actions):
        raise ValueError("actions must contain Action values")
    return actions


def _nonnegative_vector(values: object, name: str, size: int) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim == 0:
        arr = np.full(size, float(arr), dtype=np.float64)
    if arr.ndim != 1 or arr.size != size:
        raise ValueError(f"{name} must be scalar or match the number of markets")
    if not np.all(np.isfinite(arr)) or np.any(arr < 0.0):
        raise ValueError(f"{name} must be finite and non-negative")
    return arr


def per_market_pnl(
    quotes: object,
    outcomes: object,
    actions: Sequence[Action],
    *,
    fee_per_trade: object = 0.0,
    spread: object = 0.0,
    stake: object = 1.0,
) -> np.ndarray:
    """One-contract P&L for each market after fees and spread.

    ``quote`` is the YES mid-price and ``spread`` is the full bid-ask width.
    An acted-on position pays half the spread at entry and settles without a
    second spread: YES gross P&L is ``outcome - quote`` and NO gross P&L is
    ``quote - outcome``.  Both gross P&L and costs scale with ``stake``;
    abstentions are exactly zero.  This explicit cost convention is an
    **unverified placeholder** until a real market dataset and its fee schedule
    are selected.
    """
    q = _probabilities(quotes)
    y = _outcomes(outcomes, q.size)
    action_values = _actions(actions)
    if len(action_values) != q.size:
        raise ValueError("actions must match the number of markets")
    fees = _nonnegative_vector(fee_per_trade, "fee_per_trade", q.size)
    spreads = _nonnegative_vector(spread, "spread", q.size)
    stakes = _nonnegative_vector(stake, "stake", q.size)

    result = np.zeros(q.size, dtype=np.float64)
    yes = np.fromiter((a is Action.YES for a in action_values), dtype=bool, count=q.size)
    no = np.fromiter((a is Action.NO for a in action_values), dtype=bool, count=q.size)
    traded = yes | no
    result[yes] = y[yes] - q[yes]
    result[no] = q[no] - y[no]
    result[traded] -= fees[traded] + 0.5 * spreads[traded]
    result *= stakes
    return result


def pnl_after_fees_and_spread(*args: object, **kwargs: object) -> float:
    """Total P&L; arguments are those of :func:`per_market_pnl`."""
    return float(np.sum(per_market_pnl(*args, **kwargs)))


def maximum_drawdown(per_market_profit: object) -> float:
    """Largest absolute peak-to-trough loss in ordered cumulative P&L.

    The initial cumulative P&L of zero is included as a possible peak.  This is
    an absolute stake-unit drawdown, not a percentage (no capital base is assumed).
    """
    profit = _one_dimensional(per_market_profit, "per_market_profit", allow_empty=True).astype(np.float64)
    if not np.all(np.isfinite(profit)):
        raise ValueError("per_market_profit must be finite")
    cumulative = np.concatenate(([0.0], np.cumsum(profit)))
    running_peak = np.maximum.accumulate(cumulative)
    return float(np.max(running_peak - cumulative))


def turnover(actions: Sequence[Action], *, stake: object = 1.0) -> float:
    """Sum of absolute opening stake for YES/NO actions; abstentions add zero."""
    action_values = _actions(actions)
    stakes = _nonnegative_vector(stake, "stake", len(action_values))
    traded = np.fromiter((a is not Action.ABSTAIN for a in action_values), dtype=bool)
    return float(np.sum(stakes[traded]))


def abstention_rate(actions: Sequence[Action]) -> float:
    """Fraction of market decisions that are ABSTAIN."""
    action_values = _actions(actions)
    return float(np.mean([action is Action.ABSTAIN for action in action_values]))


@dataclass(frozen=True)
class BootstrapInterval:
    estimate: float
    lower: float
    upper: float
    confidence_level: float
    n_resamples: int
    seed: int
    resampling_unit: str = "market"


BootstrapData = Union[object, Tuple[object, ...]]


def bootstrap_confidence_interval(
    data: BootstrapData,
    statistic: Callable[..., float],
    *,
    confidence_level: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 0,
    market_ids: Optional[object] = None,
) -> BootstrapInterval:
    """Seeded percentile interval from a market-level cluster bootstrap.

    Arrays must share their first dimension.  ``statistic`` receives either one
    resampled array or one positional array per tuple element.  With no
    ``market_ids``, every row is declared to be one market.  Repeated IDs enable
    multiple dependent rows/trades per market; whole market blocks are sampled
    together.  The method is the ordinary percentile bootstrap.
    """
    arrays = tuple(np.asarray(item) for item in data) if isinstance(data, tuple) else (np.asarray(data),)
    if not arrays or arrays[0].ndim == 0 or arrays[0].shape[0] == 0:
        raise ValueError("bootstrap data must contain at least one market row")
    n_rows = arrays[0].shape[0]
    if any(array.ndim == 0 or array.shape[0] != n_rows for array in arrays):
        raise ValueError("all bootstrap arrays must share their first dimension")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be in (0, 1)")
    if not isinstance(n_resamples, int) or isinstance(n_resamples, bool) or n_resamples < 1:
        raise ValueError("n_resamples must be an integer >= 1")

    if market_ids is None:
        ids = np.arange(n_rows)
    else:
        ids = _one_dimensional(market_ids, "market_ids")
        if ids.size != n_rows:
            raise ValueError("market_ids must match the number of rows")
    unique_ids = np.unique(ids)
    row_blocks = [np.flatnonzero(ids == market_id) for market_id in unique_ids]

    def call_statistic(parts: Tuple[np.ndarray, ...]) -> float:
        value = statistic(*parts) if len(parts) > 1 else statistic(parts[0])
        scalar = float(value)
        if not np.isfinite(scalar):
            raise ValueError("statistic must return a finite scalar")
        return scalar

    estimate = call_statistic(arrays)
    rng = np.random.default_rng(seed)
    replicates = np.empty(n_resamples, dtype=np.float64)
    for index in range(n_resamples):
        selected_markets = rng.integers(0, len(row_blocks), size=len(row_blocks))
        selected_rows = np.concatenate([row_blocks[i] for i in selected_markets])
        replicates[index] = call_statistic(tuple(array[selected_rows] for array in arrays))
    alpha = (1.0 - confidence_level) / 2.0
    lower, upper = np.quantile(replicates, [alpha, 1.0 - alpha])
    return BootstrapInterval(
        estimate=estimate,
        lower=float(lower),
        upper=float(upper),
        confidence_level=confidence_level,
        n_resamples=n_resamples,
        seed=int(seed),
    )
