"""Market outcome -> dopamine (teaching) stimulation.

Pure numpy/stdlib; no Brian2, no simulation. Two preregistered reward arms:

  * profit-based (headline): how much money the decision made or lost;
  * accuracy-based (comparison): Brier-score improvement of the forecast.

Each is divided by a scale and CLIPPED to [-1, 1] so no single outcome can
dominate learning (design doc 4c). Positive reward -> PAM (reward family)
stimulation; negative -> PPL1 (punishment family); the stimulation rate is
proportional to |reward|. "Reward"/"punishment" are engineering labels for a
teaching signal, not claims about experience.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

import numpy as np

from .params import RewardParams


class Family(str, Enum):
    PAM = "PAM"  # reward-family dopamine neurons
    PPL1 = "PPL1"  # punishment-family dopamine neurons


@dataclass(frozen=True)
class Reward:
    kind: str  # "profit" or "brier"
    raw: float  # profit, or Brier improvement (before scaling/clipping)
    value: float  # normalised, clipped to [-1, 1]
    clipped: bool  # True if |raw / scale| exceeded 1 and was clipped


@dataclass(frozen=True)
class DopamineSignal:
    """What to stimulate after an outcome. ``family`` is None (and rate 0) when
    there is nothing to teach (reward within the dead zone)."""

    family: Optional[Family]
    magnitude: float  # in [0, 1]; = |reward value|
    rate_hz: float  # magnitude * dopamine_max_rate_hz
    reward: Reward

    def strengths(self) -> Dict[str, float]:
        """``{family_name: magnitude}`` in the form ``plasticity`` consumes ({} if none)."""
        if self.family is None:
            return {}
        return {self.family.value: self.magnitude}


def _finite(x: float, what: str) -> float:
    v = float(x)
    if not np.isfinite(v):
        raise ValueError(f"{what} must be finite, got {x!r}")
    return v


def _normalise(kind: str, raw: float, scale: float) -> Reward:
    ratio = raw / scale
    value = float(np.clip(ratio, -1.0, 1.0))
    return Reward(kind=kind, raw=raw, value=value, clipped=abs(ratio) > 1.0)


def profit_reward(profit: float, params: Optional[RewardParams] = None) -> Reward:
    """Profit-based reward. ``profit`` is net of fees/spread, in the same units as
    ``params.profit_scale`` (default: stake units)."""
    p = params or RewardParams()
    return _normalise("profit", _finite(profit, "profit"), p.profit_scale)


def brier(forecast_prob: float, outcome: int) -> float:
    f = _finite(forecast_prob, "forecast_prob")
    if not 0.0 <= f <= 1.0:
        raise ValueError(f"forecast_prob must be in [0, 1], got {forecast_prob!r}")
    if outcome not in (0, 1):
        raise ValueError(f"outcome must be 0 or 1, got {outcome!r}")
    return (f - outcome) ** 2


def brier_improvement_reward(
    forecast_prob: float,
    outcome: int,
    params: Optional[RewardParams] = None,
    baseline_prob: Optional[float] = None,
) -> Reward:
    """Accuracy-based reward: ``Brier(baseline) - Brier(forecast)`` (positive when
    the forecast beat the baseline), scaled and clipped.

    ``baseline_prob`` defaults to ``params.brier_baseline_prob`` (0.5). Which
    baseline is right (0.5 / market price / running base rate) is an OPEN
    design question; pass the market price here to reward "beat the market".
    """
    p = params or RewardParams()
    base = p.brier_baseline_prob if baseline_prob is None else baseline_prob
    improvement = brier(base, outcome) - brier(forecast_prob, outcome)
    return _normalise("brier", improvement, p.brier_scale)


def dopamine_signal(reward: Reward, params: Optional[RewardParams] = None) -> DopamineSignal:
    """Map a normalised reward to a dopamine-neuron stimulation.

    Positive -> PAM, negative -> PPL1, rate = |value| * dopamine_max_rate_hz
    (so rate is always within [0, dopamine_max_rate_hz]). |value| <= dead_zone
    (including exactly 0) -> no stimulation.
    """
    p = params or RewardParams()
    mag = abs(reward.value)
    if mag <= p.dead_zone or mag == 0.0:
        return DopamineSignal(family=None, magnitude=0.0, rate_hz=0.0, reward=reward)
    family = Family.PAM if reward.value > 0 else Family.PPL1
    return DopamineSignal(
        family=family, magnitude=mag, rate_hz=mag * p.dopamine_max_rate_hz, reward=reward
    )
