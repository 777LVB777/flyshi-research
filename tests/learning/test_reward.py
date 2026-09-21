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


def test_brier_improvement_is_measured_against_the_market_price():
    """DECIDED baseline: accuracy reward = improvement over the market's own forecast."""
    # market says 0.6, YES happens. Forecast 0.9 is closer than 0.6 -> reward.
    better = brier_improvement_reward(0.9, 1, market_price=0.6, params=P)
    assert better.raw == pytest.approx((0.6 - 1) ** 2 - (0.9 - 1) ** 2)  # 0.16 - 0.01
    assert better.value > 0 and better.kind == "brier"
    # Forecast 0.5 is worse than the market's 0.6 -> punishment (it would have BEATEN a 0.5 baseline).
    worse = brier_improvement_reward(0.5, 1, market_price=0.6, params=P)
    assert worse.value < 0


def test_echoing_the_market_earns_exactly_zero_whatever_happens():
    for price in (0.05, 0.6, 0.97):
        for outcome in (0, 1):
            r = brier_improvement_reward(price, outcome, price, P)
            assert r.raw == 0.0 and r.value == 0.0
            assert dopamine_signal(r, P).family is None  # nothing to teach


def test_brier_improvement_sign_follows_who_was_closer():
    assert brier_improvement_reward(0.9, 1, 0.7, P).value > 0  # we were closer
    assert brier_improvement_reward(0.4, 1, 0.7, P).value < 0  # market was closer
    assert brier_improvement_reward(0.1, 0, 0.3, P).value > 0  # closer on a NO outcome


def test_brier_improvement_is_symmetric_across_outcomes():
    assert brier_improvement_reward(0.8, 1, 0.6, P).value == \
        pytest.approx(brier_improvement_reward(0.2, 0, 0.4, P).value)


def test_brier_improvement_scaling_and_clipping():
    perfect = brier_improvement_reward(1.0, 1, market_price=0.5, params=P)  # 0.25 / 0.25
    assert perfect.value == pytest.approx(1.0) and not perfect.clipped
    worst = brier_improvement_reward(0.0, 1, market_price=0.5, params=P)  # -0.25
    assert worst.value == pytest.approx(-1.0)
    # against a confident-and-wrong market the same forecast beats it by more than the scale
    r = brier_improvement_reward(1.0, 1, market_price=0.0, params=P)  # improvement 1.0 / 0.25
    assert r.clipped and r.value == 1.0


def test_brier_reward_against_market_is_small_for_small_edges():
    """Documents why the placeholder brier_scale (0.25) is probably too big here."""
    # a 2-point edge over the market (0.62 vs 0.60, YES happens): improvement
    # 0.16 - 0.1444 = 0.0156, i.e. only ~6% of the 0.25 scale.
    r = brier_improvement_reward(0.62, 1, market_price=0.60, params=P)
    assert r.raw == pytest.approx(0.0156)
    assert 0 < r.value < 0.1
    assert dopamine_signal(r, P).rate_hz < 0.1 * P.dopamine_max_rate_hz


def test_baseline_override_is_a_named_variant_not_the_default():
    """baseline_prob=0.5 recovers the old uninformative-baseline behaviour."""
    default = brier_improvement_reward(0.9, 1, market_price=0.6, params=P)
    variant = brier_improvement_reward(0.9, 1, market_price=0.6, params=P, baseline_prob=0.5)
    assert variant.raw == pytest.approx(0.25 - 0.01)
    assert variant.raw != default.raw


def test_market_price_is_required():
    with pytest.raises(TypeError):
        brier_improvement_reward(0.9, 1)  # type: ignore[call-arg]


def test_brier_rejects_bad_inputs():
    with pytest.raises(ValueError):
        brier_improvement_reward(1.2, 1, 0.5, P)
    with pytest.raises(ValueError):
        brier_improvement_reward(0.5, 2, 0.5, P)
    with pytest.raises(ValueError):
        brier_improvement_reward(float("nan"), 1, 0.5, P)
    with pytest.raises(ValueError):
        brier_improvement_reward(0.5, 1, 1.5, P)  # market price outside [0, 1]
    with pytest.raises(ValueError):
        brier_improvement_reward(0.5, 1, float("nan"), P)


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
    accuracy = dopamine_signal(brier_improvement_reward(0.7, 1, market_price=0.5, params=P), P)
    profit = dopamine_signal(profit_reward(-0.3, P), P)  # e.g. lost to spread/fees
    assert accuracy.family == Family.PAM and profit.family == Family.PPL1
