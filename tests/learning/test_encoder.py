from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning.encoder import (  # noqa: E402
    KCEncoder,
    assign_pools,
    option_b_stimuli,
    value_to_rate,
)
from flyshi_research.learning.params import EncoderParams, FeatureSpec  # noqa: E402

# Synthetic stand-ins for left-hemisphere KC root IDs (same magnitude as FlyWire
# IDs, so int64 handling is exercised). No real IDs are hardcoded anywhere.
KC_IDS = [720575940600000000 + 7 * i for i in range(2000)]
FEATURES = {
    "price": 0.7,
    "recent_change": 0.05,
    "time_to_resolution": 30.0,
    "liquidity": 0.4,
}
NAMES = ["price", "recent_change", "time_to_resolution", "liquidity", "signal"]


def make_encoder(seed=1, **kw):
    return KCEncoder(KC_IDS, seed=seed, params=EncoderParams(**kw))


# ---- pools ---------------------------------------------------------------- #
def test_pools_are_disjoint_and_correct_size():
    enc = make_encoder()
    seen = set()
    for name, pool in enc.pools.items():
        assert pool.size == enc.params.pool_size
        assert len(np.unique(pool)) == pool.size
        assert not (seen & set(pool.tolist())), f"{name} overlaps an earlier pool"
        seen |= set(pool.tolist())
    assert set(enc.pools) == set(NAMES)


def test_pools_come_from_supplied_ids_only():
    enc = make_encoder()
    allowed = set(KC_IDS)
    for pool in enc.pools.values():
        assert set(pool.tolist()) <= allowed


def test_same_seed_same_pools_different_seed_different_pools():
    a, b, c = make_encoder(seed=5), make_encoder(seed=5), make_encoder(seed=6)
    for n in NAMES:
        assert np.array_equal(a.pools[n], b.pools[n])
    assert any(not np.array_equal(a.pools[n], c.pools[n]) for n in NAMES)


def test_pools_independent_of_input_order():
    shuffled = list(reversed(KC_IDS))
    a = KCEncoder(KC_IDS, seed=3)
    b = KCEncoder(shuffled, seed=3)
    for n in NAMES:
        assert np.array_equal(a.pools[n], b.pools[n])


def test_default_seed_comes_from_params():
    a = KCEncoder(KC_IDS)
    b = KCEncoder(KC_IDS, seed=EncoderParams().pool_seed)
    assert np.array_equal(a.pools["price"], b.pools["price"])


def test_too_few_kcs_raises():
    with pytest.raises(ValueError, match="need"):
        assign_pools(KC_IDS[:499], NAMES, pool_size=100, seed=0)


def test_duplicate_kc_ids_raise():
    with pytest.raises(ValueError, match="duplicates"):
        assign_pools(KC_IDS[:600] + [KC_IDS[0]], NAMES, pool_size=100, seed=0)


def test_float_kc_ids_rejected_not_silently_truncated():
    with pytest.raises(TypeError):
        assign_pools(np.array(KC_IDS, dtype=np.float64), NAMES, pool_size=100, seed=0)


def test_large_ids_survive_exactly():
    enc = make_encoder()
    ids = np.concatenate(list(enc.pools.values()))
    assert ids.dtype == np.int64
    assert set(ids.tolist()) <= set(KC_IDS)  # exact equality, no float rounding


# ---- rate mapping --------------------------------------------------------- #
def test_rate_mapping_is_linear_and_hits_endpoints():
    spec = FeatureSpec("x", 0.0, 10.0)
    assert value_to_rate(0.0, spec, 0.0, 150.0)[0] == 0.0
    assert value_to_rate(10.0, spec, 0.0, 150.0)[0] == 150.0
    assert value_to_rate(5.0, spec, 0.0, 150.0)[0] == 75.0
    assert value_to_rate(5.0, spec, 20.0, 120.0)[0] == 70.0  # min_rate offset honoured


def test_rates_stay_within_bounds_including_out_of_range():
    enc = make_encoder(min_rate_hz=10.0, max_rate_hz=140.0)
    for price in (-5.0, 0.0, 0.33, 1.0, 9.0):
        for side in ("YES", "NO"):
            st = enc.encode({**FEATURES, "price": price}, side)
            assert st.rates_hz.min() >= 10.0
            assert st.rates_hz.max() <= 140.0


def test_out_of_range_is_clipped_and_reported():
    enc = make_encoder()
    st = enc.encode({**FEATURES, "price": 1.7, "liquidity": -0.2}, "YES")
    assert st.was_clipped
    by_name = {c.feature: c for c in st.clip_events}
    assert set(by_name) == {"price", "liquidity"}
    assert by_name["price"].direction == "high" and by_name["price"].raw == 1.7
    assert by_name["price"].clipped_to == 1.0
    assert by_name["liquidity"].direction == "low"
    assert st.feature_rates_hz["price"] == enc.params.max_rate_hz
    assert st.feature_rates_hz["liquidity"] == enc.params.min_rate_hz


def test_in_range_values_report_no_clipping():
    st = make_encoder().encode(FEATURES, "YES")
    assert not st.was_clipped and st.clip_events == ()


def test_clipping_is_reported_for_both_framings_of_option_b():
    pair = make_encoder().option_b_stimuli({**FEATURES, "price": 2.0})
    assert pair.yes.was_clipped and pair.no.was_clipped and pair.was_clipped


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_values_raise(bad):
    with pytest.raises(ValueError, match="non-finite"):
        make_encoder().encode({**FEATURES, "price": bad})


# ---- encode validation ---------------------------------------------------- #
def test_missing_required_feature_and_unknown_feature_raise():
    enc = make_encoder()
    with pytest.raises(ValueError, match="missing required"):
        enc.encode({"price": 0.5})
    with pytest.raises(ValueError, match="unknown features"):
        enc.encode({**FEATURES, "prise": 0.5})
    with pytest.raises(ValueError, match="side"):
        enc.encode(FEATURES, side="MAYBE")


def test_optional_signal_feature_omitted_or_present():
    enc = make_encoder()
    no_signal = enc.encode(FEATURES)
    assert no_signal.omitted == ("signal",)
    assert no_signal.kc_ids.size == 4 * enc.params.pool_size
    with_signal = enc.encode({**FEATURES, "signal": 0.9})
    assert with_signal.omitted == ()
    assert with_signal.kc_ids.size == 5 * enc.params.pool_size
    # Absent optional feature must not shift other pools (pools are fixed up front).
    assert set(no_signal.kc_ids.tolist()) <= set(with_signal.kc_ids.tolist())


def test_stimulus_kcs_belong_to_the_right_pool_at_the_right_rate():
    enc = make_encoder()
    st = enc.encode(FEATURES, "YES")
    for name in FEATURES:
        pool = set(enc.pools[name].tolist())
        rates = {r for i, r in zip(st.kc_ids.tolist(), st.rates_hz.tolist()) if i in pool}
        assert rates == {st.feature_rates_hz[name]}
    assert st.feature_rates_hz["price"] == pytest.approx(30.0 + 0.7 * (150.0 - 30.0))  # 114 Hz


def test_driven_drops_zero_rate_kcs():
    enc = make_encoder(min_rate_hz=0.0)  # explicit override: the default (30 Hz) has no zero-rate pool
    st = enc.encode({**FEATURES, "price": 0.0}, "YES")  # price pool at 0 Hz
    ids, rates = st.driven()
    assert (rates > 0).all()
    assert not set(enc.pools["price"].tolist()) & set(ids.tolist())


# ---- Option B ------------------------------------------------------------- #
def test_option_b_no_price_is_one_minus_p():
    enc = make_encoder()
    pair = option_b_stimuli(enc, FEATURES)  # module-level form
    assert pair.yes.side == "YES" and pair.no.side == "NO"
    assert pair.yes.feature_values["price"] == pytest.approx(0.7)
    assert pair.no.feature_values["price"] == pytest.approx(0.3)
    assert pair.yes.feature_rates_hz["price"] == pytest.approx(30.0 + 0.7 * 120.0)  # 114 Hz
    assert pair.no.feature_rates_hz["price"] == pytest.approx(30.0 + 0.3 * 120.0)  # 66 Hz


def test_option_b_stimuli_differ_only_where_intended():
    enc = make_encoder()
    pair = enc.option_b_stimuli(FEATURES)
    # Same KCs are driven in both framings (same pools) ...
    assert np.array_equal(pair.yes.kc_ids, pair.no.kc_ids)
    # ... price and (directional) recent_change differ ...
    assert pair.yes.feature_rates_hz["price"] != pair.no.feature_rates_hz["price"]
    assert pair.yes.feature_rates_hz["recent_change"] != pair.no.feature_rates_hz["recent_change"]
    # ... side-neutral features are identical.
    for neutral in ("time_to_resolution", "liquidity"):
        assert pair.yes.feature_rates_hz[neutral] == pair.no.feature_rates_hz[neutral]
    assert not np.array_equal(pair.yes.rates_hz, pair.no.rates_hz)


def test_recent_change_mirrors_sign_under_no():
    enc = make_encoder()
    pair = enc.option_b_stimuli({**FEATURES, "recent_change": 0.15})
    assert pair.yes.feature_values["recent_change"] == pytest.approx(0.15)
    assert pair.no.feature_values["recent_change"] == pytest.approx(-0.15)


def test_option_b_is_symmetric_at_coin_flip_price():
    """At p=0.5 with neutral directional features, YES and NO stimuli coincide."""
    enc = make_encoder()
    feats = {**FEATURES, "price": 0.5, "recent_change": 0.0, "signal": 0.5}
    pair = enc.option_b_stimuli(feats)
    assert np.array_equal(pair.yes.rates_hz, pair.no.rates_hz)


def test_mirror_flag_is_configurable_price_only():
    price_only = tuple(
        FeatureSpec(f.name, f.min_value, f.max_value, mirror_for_no=(f.name == "price"),
                    required=f.required)
        for f in EncoderParams().features
    )
    enc = make_encoder(features=price_only)
    pair = enc.option_b_stimuli({**FEATURES, "recent_change": 0.15})
    assert pair.yes.feature_rates_hz["recent_change"] == pair.no.feature_rates_hz["recent_change"]
    assert pair.yes.feature_rates_hz["price"] != pair.no.feature_rates_hz["price"]


def test_mirroring_applies_after_clipping():
    enc = make_encoder()
    pair = enc.option_b_stimuli({**FEATURES, "price": 1.4})  # clipped to 1.0, NO -> 0.0
    assert pair.yes.feature_values["price"] == 1.0
    assert pair.no.feature_values["price"] == 0.0
    assert pair.no.feature_rates_hz["price"] == enc.params.min_rate_hz


# ---- runner hand-off -------------------------------------------------------- #
def test_rates_by_kc_id_is_the_runner_mapping_with_exact_python_int_ids():
    enc = make_encoder()
    st = enc.encode(FEATURES, "YES")
    m = st.rates_by_kc_id()
    assert len(m) == st.kc_ids.size
    assert all(type(k) is int and type(v) is float for k, v in m.items())
    assert set(m) <= set(KC_IDS)  # exact 64-bit IDs survive
    for name in FEATURES:  # per-feature rate lands on that feature's pool
        assert {m[int(i)] for i in enc.pools[name]} == {st.feature_rates_hz[name]}


def test_rates_by_kc_id_driven_only_drops_zero_rate_kcs():
    enc = make_encoder(min_rate_hz=0.0)  # explicit override: the default (30 Hz) has no zero-rate pool
    st = enc.encode({**FEATURES, "price": 0.0}, "YES")  # price pool at 0 Hz
    assert set(enc.pools["price"].tolist()) <= set(st.rates_by_kc_id())
    driven = st.rates_by_kc_id(driven_only=True)
    assert all(v > 0 for v in driven.values())
    assert not set(enc.pools["price"].tolist()) & set(driven)


# ---- the decided NO-framing mirroring rule --------------------------------- #
def test_decided_mirroring_rule_evidence_features_mirror_neutral_ones_do_not():
    """DECIDED (design doc 4a): price, recent_change and signal are evidence for or
    against YES, so they flip under NO. time_to_resolution and liquidity mean the
    same thing for both framings, so they do not."""
    specs = {f.name: f for f in EncoderParams().features}
    assert {n for n, f in specs.items() if f.mirror_for_no} == {"price", "recent_change", "signal"}
    assert {n for n, f in specs.items() if not f.mirror_for_no} == {"time_to_resolution", "liquidity"}
    enc = make_encoder()
    pair = enc.option_b_stimuli({**FEATURES, "signal": 0.9})
    for name in ("price", "recent_change", "signal"):
        assert pair.yes.feature_values[name] != pair.no.feature_values[name], name
    assert pair.yes.feature_values["signal"] == pytest.approx(0.9)
    assert pair.no.feature_values["signal"] == pytest.approx(0.1)
    for name in ("time_to_resolution", "liquidity"):
        assert pair.yes.feature_values[name] == pair.no.feature_values[name], name


# ---- default rate bounds: nothing below the graded test's lowest rate --------- #
def test_default_encoder_never_emits_a_rate_below_the_lowest_tested_rate():
    """The placeholder bounds are 30-150 Hz, the range the graded-rate test covers, so the
    encoder cannot emit a rate outside anything tested - whatever the inputs, either
    framing, in or out of range."""
    enc = KCEncoder(KC_IDS, seed=1)
    assert (enc.params.min_rate_hz, enc.params.max_rate_hz) == (30.0, 150.0)
    for price in (-9.0, 0.0, 0.5, 1.0, 9.0):
        for change in (-5.0, 0.0, 5.0):
            for tt in (-1.0, 0.0, 400.0):
                for side in ("YES", "NO"):
                    st = enc.encode({"price": price, "recent_change": change,
                                     "time_to_resolution": tt, "liquidity": 0.0, "signal": 0.0},
                                    side)
                    assert st.rates_hz.min() >= 30.0 and st.rates_hz.max() <= 150.0


def test_at_the_default_minimum_value_a_pool_fires_at_30_hz_not_zero():
    """Consequence of the 30 Hz floor: no feature pool is silent, even at its minimum value."""
    enc = KCEncoder(KC_IDS, seed=1)
    st = enc.encode({"price": 0.0, "recent_change": -0.2, "time_to_resolution": 0.0,
                     "liquidity": 0.0, "signal": 0.0})
    assert set(st.feature_rates_hz.values()) == {30.0}
    ids, rates = st.driven()
    assert ids.size == st.kc_ids.size  # every pool KC is driven
