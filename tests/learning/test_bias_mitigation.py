from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning.bias_mitigation import (  # noqa: E402
    INNATE_SCORE_SUBTRACTION,
    TOTAL_DRIVE_BALANCING,
    score_difference,
    select_balance_pool,
    total_drive_balance,
)
from flyshi_research.learning.encoder import KCEncoder  # noqa: E402


KC_IDS = np.arange(1000, 3000, dtype=np.int64)
FEATURES = {
    "price": 0.8,
    "recent_change": 0.15,
    "time_to_resolution": 30.0,
    "liquidity": 0.4,
    "signal": 0.9,
}


class IntensityBiasedFake:
    """Score has no semantics: it is exactly proportional to total input rate."""

    @staticmethod
    def score(stimulus) -> float:
        return -0.01 * float(np.sum(stimulus.rates_hz))


def test_total_drive_balancing_removes_a_fake_builtin_intensity_bias() -> None:
    encoder = KCEncoder(KC_IDS)
    pair = encoder.option_b_stimuli(FEATURES)
    fake = IntensityBiasedFake()
    before = fake.score(pair.yes) - fake.score(pair.no)
    assert before != 0.0
    occupied = np.concatenate(list(encoder.pools.values()))
    pool = select_balance_pool(KC_IDS, occupied, pool_size=300, seed=9)
    balanced = total_drive_balance(pair, pool, min_rate_hz=30.0, max_rate_hz=150.0)
    assert np.sum(balanced.yes.rates_hz) == pytest.approx(np.sum(balanced.no.rates_hz))
    after = score_difference(
        fake.score(balanced.yes), fake.score(balanced.no), mitigation=TOTAL_DRIVE_BALANCING
    )
    assert after == pytest.approx(0.0, abs=1e-12)


def test_innate_score_subtraction_removes_the_same_fake_intensity_bias() -> None:
    pair = KCEncoder(KC_IDS).option_b_stimuli(FEATURES)
    fake = IntensityBiasedFake()
    innate_yes, innate_no = fake.score(pair.yes), fake.score(pair.no)
    assert innate_yes - innate_no != 0.0
    difference = score_difference(
        innate_yes,
        innate_no,
        mitigation=INNATE_SCORE_SUBTRACTION,
        innate_yes_score=innate_yes,
        innate_no_score=innate_no,
    )
    assert difference == pytest.approx(0.0, abs=1e-12)


def test_innate_subtraction_preserves_an_additive_learned_difference() -> None:
    assert score_difference(
        13.0,
        7.0,
        mitigation=INNATE_SCORE_SUBTRACTION,
        innate_yes_score=10.0,
        innate_no_score=8.0,
    ) == pytest.approx(4.0)


def test_balance_pool_is_seeded_disjoint_and_capacity_checked() -> None:
    occupied = KC_IDS[:500]
    a = select_balance_pool(KC_IDS, occupied, pool_size=300, seed=7)
    b = select_balance_pool(KC_IDS, occupied, pool_size=300, seed=7)
    assert np.array_equal(a, b)
    assert not set(a) & set(occupied)
    with pytest.raises(ValueError, match="not enough"):
        select_balance_pool(KC_IDS, occupied, pool_size=1600, seed=7)
