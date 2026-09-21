from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning.params import RewardParams  # noqa: E402
from flyshi_research.learning.reward import (  # noqa: E402
    Family,
    brier,
    brier_improvement_reward,
    dopamine_signal,
    profit_reward,
)

P = RewardParams()


# ---- profit ---------------------------------------------------------------- #
def test_profit_is_normalised_linearly_inside_bounds():
    r = profit_reward(0.4, P)
    assert r.value == pytest.approx(0.4) and not r.clipped and r.kind == "profit"
    assert profit_reward(-0.25, P).value == pytest.approx(-0.25)
    assert profit_reward(2.0, RewardParams(profit_scale=4.0)).value == pytest.approx(0.5)


def test_profit_clips_to_bounds_and_reports_it():
    hi, lo = profit_reward(3.0, P), profit_reward(-9.0, P)
    assert (hi.value, lo.value) == (1.0, -1.0)
    assert hi.clipped and lo.clipped
    assert hi.raw == 3.0  # raw value is preserved for logging
    assert not profit_reward(1.0, P).clipped  # exactly at the bound is not clipping


@pytest.mark.parametrize("huge", [1e6, 1e300, -1e6, -1e300])
def test_single_huge_outcome_cannot_exceed_bound(huge):
    r = profit_reward(huge, P)
    assert abs(r.value) <= 1.0
    sig = dopamine_signal(r, P)
    assert 0.0 <= sig.magnitude <= 1.0
    assert 0.0 <= sig.rate_hz <= P.dopamine_max_rate_hz


def test_huge_outcome_is_no_more_powerful_than_a_bound_sized_one():
    assert dopamine_signal(profit_reward(1e9, P), P).rate_hz == \
        dopamine_signal(profit_reward(1.0, P), P).rate_hz


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_profit_raises(bad):
    with pytest.raises(ValueError):
        profit_reward(bad, P)


# ---- Brier improvement ----------------------------------------------------- #
def test_brier_values():
    assert brier(0.7, 1) == pytest.approx(0.09)
    assert brier(0.7, 0) == pytest.approx(0.49)


def test_brier_improvement_sign_follows_forecast_quality():
    good = brier_improvement_reward(0.9, 1, P)  # better than 0.5 baseline
    bad = brier_improvement_reward(0.1, 1, P)  # worse than baseline
    assert good.value > 0 and bad.value < 0
    assert good.kind == "brier"
    assert brier_improvement_reward(0.5, 1, P).value == 0.0  # same as baseline


def test_brier_improvement_is_symmetric_across_outcomes():
    assert brier_improvement_reward(0.8, 1, P).value == \
        pytest.approx(brier_improvement_reward(0.2, 0, P).value)


def test_brier_improvement_scaling_and_clipping():
    perfect = brier_improvement_reward(1.0, 1, P)  # 0.25 improvement / 0.25 scale
    assert perfect.value == pytest.approx(1.0) and not perfect.clipped
    worst = brier_improvement_reward(0.0, 1, P)  # -0.25
    assert worst.value == pytest.approx(-1.0)
    # vs a strong baseline the same forecast can improve by more than the scale -> clipped
    r = brier_improvement_reward(1.0, 1, P, baseline_prob=0.0)  # improvement 1.0 / 0.25
    assert r.clipped and r.value == 1.0


def test_brier_baseline_can_be_market_price():
    r = brier_improvement_reward(0.6, 1, P, baseline_prob=0.6)
    assert r.value == 0.0  # "same as the market" earns nothing


def test_brier_rejects_bad_inputs():
    with pytest.raises(ValueError):
        brier_improvement_reward(1.2, 1, P)
    with pytest.raises(ValueError):
        brier_improvement_reward(0.5, 2, P)
    with pytest.raises(ValueError):
        brier_improvement_reward(float("nan"), 1, P)


# ---- dopamine mapping ------------------------------------------------------ #
def test_positive_reward_selects_pam_negative_selects_ppl1():
    pos = dopamine_signal(profit_reward(0.5, P), P)
    neg = dopamine_signal(profit_reward(-0.5, P), P)
    assert pos.family == Family.PAM and neg.family == Family.PPL1
    assert pos.strengths() == {"PAM": 0.5}
    assert neg.strengths() == {"PPL1": 0.5}


def test_rate_scales_with_magnitude_and_is_bounded():
    q = RewardParams(dopamine_max_rate_hz=200.0)
    assert dopamine_signal(profit_reward(0.25, q), q).rate_hz == pytest.approx(50.0)
    assert dopamine_signal(profit_reward(-1.0, q), q).rate_hz == pytest.approx(200.0)
    rates = [dopamine_signal(profit_reward(x, q), q).rate_hz for x in np.linspace(-5, 5, 41)]
    assert min(rates) >= 0 and max(rates) <= 200.0


def test_rate_depends_on_magnitude_not_sign():
    a = dopamine_signal(profit_reward(0.3, P), P)
    b = dopamine_signal(profit_reward(-0.3, P), P)
    assert a.rate_hz == pytest.approx(b.rate_hz)


def test_zero_reward_and_dead_zone_give_no_stimulation():
    zero = dopamine_signal(profit_reward(0.0, P), P)
    assert zero.family is None and zero.rate_hz == 0.0 and zero.strengths() == {}
    q = RewardParams(dead_zone=0.1)
    small = dopamine_signal(profit_reward(0.05, q), q)
    assert small.family is None and small.rate_hz == 0.0
    assert dopamine_signal(profit_reward(0.2, q), q).family == Family.PAM


def test_profit_and_accuracy_arms_can_disagree_on_the_same_market():
    """Right forecast that still lost money: accuracy rewards, profit punishes."""
    accuracy = dopamine_signal(brier_improvement_reward(0.6, 1, P), P)
    profit = dopamine_signal(profit_reward(-0.3, P), P)  # e.g. lost to spread/fees
    assert accuracy.family == Family.PAM and profit.family == Family.PPL1
