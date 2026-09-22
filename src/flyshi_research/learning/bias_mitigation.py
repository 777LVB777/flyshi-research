"""Legacy helpers for the Option-B input-intensity-bias alternatives.

Total-drive balancing is now selected and implemented directly by
``KCEncoder.option_b_stimuli``. The standalone pool functions remain for tests
and historical comparison; new code should use the encoder default. Innate-score
subtraction is not selected. Behavior on the real model remains unverified.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Tuple

import numpy as np

from .encoder import OptionBStimuli, Stimulus

TOTAL_DRIVE_BALANCING = "total_drive_balancing"
INNATE_SCORE_SUBTRACTION = "innate_score_subtraction"
MITIGATIONS = (TOTAL_DRIVE_BALANCING, INNATE_SCORE_SUBTRACTION)


def select_balance_pool(
    all_kc_ids: Iterable[int], occupied_kc_ids: Iterable[int], *, pool_size: int, seed: int
) -> np.ndarray:
    """Select a deterministic filler pool disjoint from encoder feature pools."""
    ids = np.asarray(list(all_kc_ids))
    if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer):
        raise TypeError("all_kc_ids must be a one-dimensional integer collection")
    available = np.asarray(sorted(set(map(int, ids)) - set(map(int, occupied_kc_ids))), dtype=np.int64)
    if pool_size < 1 or available.size < pool_size:
        raise ValueError("not enough unused KCs for the balance pool")
    rng = np.random.default_rng(seed)
    return np.sort(available[rng.permutation(available.size)[:pool_size]])


def _with_filler(stimulus: Stimulus, ids: np.ndarray, rate: float) -> Stimulus:
    return replace(
        stimulus,
        kc_ids=np.concatenate((stimulus.kc_ids, ids)),
        rates_hz=np.concatenate((stimulus.rates_hz, np.full(ids.size, rate))),
        feature_rates_hz={**stimulus.feature_rates_hz, "__balance__": float(rate)},
        feature_values={**stimulus.feature_values, "__balance__": float(rate)},
    )


def total_drive_balance(
    stimuli: OptionBStimuli,
    balance_kc_ids: Iterable[int],
    *,
    min_rate_hz: float,
    max_rate_hz: float,
) -> OptionBStimuli:
    """Add filler KCs so YES and NO have identical summed input rates.

    The higher-drive framing gives every filler KC ``min_rate_hz``.  The lower
    framing raises its filler rate just enough to match.  The pool must be large
    enough that this rate remains within the validated encoder range.  Equal
    total drive does *not* prove equal circuit effect; that remains unverified.
    """
    ids = np.asarray(list(balance_kc_ids))
    if ids.ndim != 1 or ids.size == 0 or not np.issubdtype(ids.dtype, np.integer):
        raise TypeError("balance_kc_ids must be a non-empty integer collection")
    if len(np.unique(ids)) != ids.size:
        raise ValueError("balance_kc_ids contains duplicates")
    occupied = set(stimuli.yes.kc_ids.tolist()) | set(stimuli.no.kc_ids.tolist())
    if occupied & set(ids.tolist()):
        raise ValueError("balance pool overlaps an encoder feature pool")
    yes_total = float(np.sum(stimuli.yes.rates_hz))
    no_total = float(np.sum(stimuli.no.rates_hz))
    difference = abs(yes_total - no_total)
    low_rate = min_rate_hz + difference / ids.size
    if low_rate > max_rate_hz + 1e-12:
        raise ValueError("balance pool is too small to equalise drive within validated rates")
    if yes_total >= no_total:
        yes_rate, no_rate = min_rate_hz, low_rate
    else:
        yes_rate, no_rate = low_rate, min_rate_hz
    balanced = OptionBStimuli(
        _with_filler(stimuli.yes, ids.astype(np.int64), yes_rate),
        _with_filler(stimuli.no, ids.astype(np.int64), no_rate),
    )
    if not np.isclose(np.sum(balanced.yes.rates_hz), np.sum(balanced.no.rates_hz)):
        raise AssertionError("internal error: total drive was not balanced")
    return balanced


def score_difference(
    yes_score: float,
    no_score: float,
    *,
    mitigation: str,
    innate_yes_score: float | None = None,
    innate_no_score: float | None = None,
) -> float:
    """Return the Option-B score difference after the named mitigation."""
    if mitigation == TOTAL_DRIVE_BALANCING:
        return float(yes_score - no_score)
    if mitigation != INNATE_SCORE_SUBTRACTION:
        raise ValueError(f"unknown intensity-bias mitigation {mitigation!r}")
    if innate_yes_score is None or innate_no_score is None:
        raise ValueError("innate-score subtraction requires both pre-learning scores")
    return float((yes_score - innate_yes_score) - (no_score - innate_no_score))
