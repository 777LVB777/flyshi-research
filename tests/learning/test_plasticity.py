from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning.params import PlasticityParams  # noqa: E402
from flyshi_research.learning.plasticity import (  # noqa: E402
    CompartmentMap,
    DecisionQueue,
    DuplicateMarketError,
    PlasticKCMBON,
    UnknownMarketError,
    depress,
    drift,
    kc_eligibility,
)
from flyshi_research.learning.readout import (  # noqa: E402
    circuit_score,
    load_dopamine_counts,
    load_sign_table,
)
from flyshi_research.learning.reward import dopamine_signal, profit_reward  # noqa: E402

# 7 MBONs. PPL1 compartments: MBON11, MBON12. PAM compartments: MBON05, MBON03, MBON09.
# MBON24 is not in the dopamine table; MBON08 has no annotated dopamine input.
LABELS = ["MBON11", "MBON12", "MBON05", "MBON03", "MBON09", "MBON24", "MBON08"]
PPL1_COLS = [0, 1]
PAM_COLS = [2, 3, 4]
NO_COMPARTMENT_COLS = [5, 6]

N_KC = 40
CUE_A = np.arange(0, 10)
CUE_B = np.arange(10, 20)
IDLE = np.arange(20, 40)

# drift off by default so each test isolates one mechanism
P = PlasticityParams(learning_rate=0.5, floor_fraction=0.2, drift_rate=0.05,
                     drift_steps_per_resolution=0, kc_active_threshold_hz=1.0,
                     kc_rate_ref_hz=100.0)


def pattern(idx, rate=100.0, n=N_KC):
    p = np.zeros(n)
    p[idx] = rate
    return p


@pytest.fixture
def w0():
    return np.random.default_rng(0).uniform(0.5, 2.0, size=(N_KC, len(LABELS)))


@pytest.fixture
def cmap():
    return CompartmentMap.from_dopamine_counts(LABELS, load_dopamine_counts(), 80)


# ---- compartment map ------------------------------------------------------- #
def test_compartment_map_families_and_exclusions(cmap):
    assert cmap.masks["PPL1"].tolist() == [1, 1, 0, 0, 0, 0, 0]
    assert cmap.masks["PAM"].tolist() == [0, 0, 1, 1, 1, 0, 0]


@pytest.mark.parametrize("pct", [70, 80, 90])
def test_compartment_map_agrees_with_circuit_signs(pct):
    """Same dominant-family rule as the readout: PAM <-> avoidance-like, PPL1 <-> approach-like."""
    labels = sorted(load_dopamine_counts()) + ["MBON24", "MBON26"]
    cm = CompartmentMap.from_dopamine_counts(labels, load_dopamine_counts(), pct)
    table = load_sign_table(f"circuit_{pct}")
    for j, l in enumerate(labels):
        assert cm.masks["PAM"][j] == (table.weight(l) == -1)
        assert cm.masks["PPL1"][j] == (table.weight(l) == +1)
    assert not cm.masks["PAM"][-2:].any() and not cm.masks["PPL1"][-2:].any()  # unlisted


def test_compartment_map_validation():
    with pytest.raises(ValueError):
        CompartmentMap(3, {"PAM": np.ones(4)})
    with pytest.raises(ValueError):
        CompartmentMap(3, {"PAM": np.array([0, 2.0, 0])})


# ---- eligibility ----------------------------------------------------------- #
def test_eligibility_thresholding_and_saturation():
    e = kc_eligibility([0.0, 1.0, 1.5, 50.0, 100.0, 400.0], P)
    assert e.tolist() == [0.0, 0.0, 0.015, 0.5, 1.0, 1.0]  # <=1 Hz inactive; saturates at 1


# ---- core rule ------------------------------------------------------------- #
def test_only_matching_compartment_weights_change(w0, cmap):
    new = depress(w0, w0, pattern(CUE_A), {"PPL1": 1.0}, cmap, P)
    for rows in (CUE_A,):
        assert (new[np.ix_(rows, PPL1_COLS)] < w0[np.ix_(rows, PPL1_COLS)]).all()
    other_cols = PAM_COLS + NO_COMPARTMENT_COLS
    assert np.array_equal(new[:, other_cols], w0[:, other_cols])  # bit-identical

    new = depress(w0, w0, pattern(CUE_A), {"PAM": 1.0}, cmap, P)
    assert (new[np.ix_(CUE_A, PAM_COLS)] < w0[np.ix_(CUE_A, PAM_COLS)]).all()
    other_cols = PPL1_COLS + NO_COMPARTMENT_COLS
    assert np.array_equal(new[:, other_cols], w0[:, other_cols])


def test_mbons_in_no_compartment_never_change(w0, cmap):
    new = depress(w0, w0, pattern(CUE_A), {"PAM": 1.0, "PPL1": 1.0}, cmap, P)
    assert np.array_equal(new[:, NO_COMPARTMENT_COLS], w0[:, NO_COMPARTMENT_COLS])


def test_inactive_kcs_weights_do_not_change(w0, cmap):
    p = pattern(CUE_A)
    p[5:10] = 0.5  # below the 1 Hz active threshold: not "recently active"
    new = depress(w0, w0, p, {"PPL1": 1.0}, cmap, P)
    assert np.array_equal(new[5:10], w0[5:10])  # sub-threshold KCs: untouched
    assert np.array_equal(new[IDLE], w0[IDLE])  # silent KCs: untouched
    assert (new[np.ix_(np.arange(5), PPL1_COLS)] < w0[np.ix_(np.arange(5), PPL1_COLS)]).all()


def test_depression_grows_with_dopamine_strength_and_eligibility(w0, cmap):
    weak = depress(w0, w0, pattern(CUE_A, 100), {"PPL1": 0.2}, cmap, P)
    strong = depress(w0, w0, pattern(CUE_A, 100), {"PPL1": 0.8}, cmap, P)
    dim = depress(w0, w0, pattern(CUE_A, 30), {"PPL1": 0.8}, cmap, P)
    r, c = CUE_A[0], PPL1_COLS[0]
    assert strong[r, c] < weak[r, c] < w0[r, c]
    assert strong[r, c] < dim[r, c] < w0[r, c]


def test_zero_dopamine_or_zero_learning_rate_is_a_no_op(w0, cmap):
    assert np.array_equal(depress(w0, w0, pattern(CUE_A), {}, cmap, P), w0)
    assert np.array_equal(depress(w0, w0, pattern(CUE_A), {"PPL1": 0.0}, cmap, P), w0)
    off = PlasticityParams(learning_rate=0.0, drift_steps_per_resolution=0)
    assert np.array_equal(depress(w0, w0, pattern(CUE_A), {"PPL1": 1.0}, cmap, off), w0)


def test_inputs_are_not_mutated(w0, cmap):
    w, snap = w0.copy(), w0.copy()
    p = pattern(CUE_A)
    depress(w, w0, p, {"PPL1": 1.0}, cmap, P)
    drift(w, w0, P, 3)
    assert np.array_equal(w, snap) and np.array_equal(p, pattern(CUE_A))


def test_floor_holds_under_repeated_punishment(w0, cmap):
    floor = P.floor_fraction * w0
    w = w0.copy()
    prev = w.copy()
    for _ in range(500):
        w = depress(w, w0, pattern(CUE_A), {"PPL1": 1.0}, cmap, P)
        assert (w >= floor).all()  # never below the floor, at any step
        assert (w <= prev).all()  # depression never increases a weight
        prev = w
    # ... and it actually gets there (floor is reached, not just respected)
    assert np.allclose(w[np.ix_(CUE_A, PPL1_COLS)], floor[np.ix_(CUE_A, PPL1_COLS)], atol=1e-9)


def test_floor_holds_even_with_maximal_step_and_start_at_floor(w0, cmap):
    big = PlasticityParams(learning_rate=1.0, floor_fraction=0.3, drift_steps_per_resolution=0)
    w = depress(w0, w0, pattern(CUE_A), {"PPL1": 1.0, "PAM": 1.0}, cmap, big)
    assert (w >= 0.3 * w0 - 1e-15).all()
    again = depress(w, w0, pattern(CUE_A), {"PPL1": 1.0}, cmap, big)
    assert (again >= 0.3 * w0 - 1e-15).all()


def test_untouched_weights_are_never_rewritten_even_below_the_floor(w0, cmap):
    """Depression must not 'repair' entries it has no business touching."""
    low = w0 * 0.05  # every weight starts well below the floor (0.2 * w0)
    new = depress(low, w0, pattern(CUE_A), {"PPL1": 1.0}, cmap, P)
    touched = np.zeros(low.shape, dtype=bool)
    touched[np.ix_(CUE_A, PPL1_COLS)] = True
    assert np.array_equal(new[~touched], low[~touched])  # untouched: bit-identical
    assert (new[touched] >= P.floor_fraction * w0[touched] - 1e-15).all()  # touched: floor wins


def test_negative_baseline_weights_weaken_toward_zero_and_respect_floor(cmap):
    W0 = -np.ones((N_KC, len(LABELS)))
    w = W0.copy()
    for _ in range(100):
        w = depress(w, W0, pattern(CUE_A), {"PPL1": 1.0}, cmap, P)
    sub = w[np.ix_(CUE_A, PPL1_COLS)]
    assert (sub > -1.0).all()  # magnitude reduced
    assert (sub <= -P.floor_fraction + 1e-12).all()  # magnitude never below floor


# ---- drift ----------------------------------------------------------------- #
def test_drift_restores_weights_with_no_dopamine(w0, cmap):
    w = w0.copy()
    for _ in range(50):
        w = depress(w, w0, pattern(CUE_A), {"PPL1": 1.0}, cmap, P)
    assert not np.allclose(w, w0)
    for _ in range(600):
        w = drift(w, w0, P)
    assert np.allclose(w, w0, atol=1e-10)


def test_drift_matches_closed_form_and_is_monotone(w0, cmap):
    depressed = depress(w0, w0, pattern(CUE_A), {"PPL1": 1.0}, cmap, P)
    gap0 = np.abs(depressed - w0)
    after_10 = drift(depressed, w0, P, 10)
    assert np.allclose(np.abs(after_10 - w0), gap0 * (1 - P.drift_rate) ** 10)
    stepwise = depressed
    for _ in range(10):
        stepwise = drift(stepwise, w0, P)
    assert np.allclose(stepwise, after_10)
    assert (np.abs(after_10 - w0) <= gap0 + 1e-15).all()


def test_drift_is_a_no_op_at_baseline_and_when_rate_is_zero(w0):
    assert np.array_equal(drift(w0, w0, P, 25), w0)
    off = PlasticityParams(drift_rate=0.0)
    w = w0 * 0.7
    assert np.array_equal(drift(w, w0, off, 25), w)


def test_drift_pulls_toward_baseline_from_above_too(w0):
    up = w0 * 1.5
    assert (np.abs(drift(up, w0, P, 5) - w0) < np.abs(up - w0)).all()


# ---- queue ----------------------------------------------------------------- #
def test_queue_basics_and_defensive_copy():
    q = DecisionQueue(N_KC)
    p = pattern(CUE_A)
    q.record("m1", p, side="YES")
    p[:] = 0  # caller mutates their array afterwards
    got = q.peek("m1")
    assert got.kc_pattern[CUE_A].tolist() == [100.0] * 10 and got.meta == {"side": "YES"}
    assert not got.kc_pattern.flags.writeable
    assert "m1" in q and len(q) == 1 and q.pending_ids() == ["m1"]
    q.pop("m1")
    assert len(q) == 0 and "m1" not in q


def test_queue_errors():
    q = DecisionQueue(N_KC)
    q.record("m1", pattern(CUE_A))
    with pytest.raises(DuplicateMarketError):
        q.record("m1", pattern(CUE_B))
    with pytest.raises(UnknownMarketError):
        q.pop("nope")
    with pytest.raises(ValueError):
        q.record("bad", np.zeros(N_KC + 1))
    with pytest.raises(ValueError):
        q.record("neg", -np.ones(N_KC))
    q.discard("m1")
    q.discard("m1")  # no-op when absent
    assert len(q) == 0


def make_net(w0, cmap, params=P):
    return PlasticKCMBON(w0, cmap, params)


def test_queue_applies_update_to_the_right_decision(w0, cmap):
    net = make_net(w0, cmap)
    net.record_decision("mA", pattern(CUE_A))
    net.record_decision("mB", pattern(CUE_B))
    net.resolve("mA", {"PPL1": 1.0})
    W = net.weights
    assert (W[np.ix_(CUE_A, PPL1_COLS)] < w0[np.ix_(CUE_A, PPL1_COLS)]).all()
    assert np.array_equal(W[CUE_B], w0[CUE_B])  # B has not resolved: untouched
    assert "mA" not in net.queue and "mB" in net.queue


def test_out_of_order_resolution_with_multiple_pending_markets(w0, cmap):
    net = make_net(w0, cmap)
    cue_c = np.arange(20, 30)
    for mid, cue in (("m1", CUE_A), ("m2", CUE_B), ("m3", cue_c)):
        net.record_decision(mid, pattern(cue))
    assert net.queue.pending_ids() == ["m1", "m2", "m3"]

    net.resolve("m3", {"PAM": 0.6})  # last decision resolves first
    W = net.weights
    assert (W[np.ix_(cue_c, PAM_COLS)] < w0[np.ix_(cue_c, PAM_COLS)]).all()
    assert np.array_equal(W[CUE_A], w0[CUE_A]) and np.array_equal(W[CUE_B], w0[CUE_B])

    net.resolve("m1", {"PPL1": 1.0})  # then the first
    W = net.weights
    assert (W[np.ix_(CUE_A, PPL1_COLS)] < w0[np.ix_(CUE_A, PPL1_COLS)]).all()
    assert np.array_equal(W[CUE_B], w0[CUE_B])  # m2 still pending and untouched
    assert net.queue.pending_ids() == ["m2"]

    net.resolve("m2", {"PPL1": 0.5})
    assert (net.weights[np.ix_(CUE_B, PPL1_COLS)] < w0[np.ix_(CUE_B, PPL1_COLS)]).all()
    assert len(net.queue) == 0


def test_resolution_order_does_not_change_result_without_drift(w0, cmap):
    """Depression toward a common floor commutes, so only drift makes order matter."""
    outcomes = {"m1": {"PPL1": 1.0}, "m2": {"PAM": 0.7}, "m3": {"PPL1": 0.4}}
    cues = {"m1": CUE_A, "m2": CUE_A, "m3": np.arange(5, 15)}  # overlapping cues
    results = []
    for order in (["m1", "m2", "m3"], ["m3", "m1", "m2"], ["m2", "m3", "m1"]):
        net = make_net(w0, cmap)
        for mid, cue in cues.items():
            net.record_decision(mid, pattern(cue))
        for mid in order:
            net.resolve(mid, outcomes[mid])
        results.append(net.weights.copy())
    assert np.allclose(results[0], results[1]) and np.allclose(results[0], results[2])


def test_resolve_unknown_market_raises_and_changes_nothing(w0, cmap):
    net = make_net(w0, cmap)
    net.record_decision("m1", pattern(CUE_A))
    with pytest.raises(UnknownMarketError):
        net.resolve("ghost", {"PPL1": 1.0})
    assert np.array_equal(net.weights, w0) and len(net.queue) == 1


def test_failed_resolution_keeps_market_pending(w0, cmap):
    net = make_net(w0, cmap)
    net.record_decision("m1", pattern(CUE_A))
    with pytest.raises(ValueError, match="not in compartment map"):
        net.resolve("m1", {"PPL2": 1.0})  # typo'd dopamine type
    assert "m1" in net.queue and np.array_equal(net.weights, w0)
    net.resolve("m1", {"PPL1": 1.0})  # can still be resolved correctly
    assert "m1" not in net.queue


def test_resolve_applies_drift_after_depression(w0, cmap):
    p = PlasticityParams(learning_rate=0.5, floor_fraction=0.2, drift_rate=0.1,
                         drift_steps_per_resolution=2, kc_rate_ref_hz=100.0)
    net = make_net(w0, cmap, p)
    net.record_decision("m1", pattern(CUE_A))
    W = net.resolve("m1", {"PPL1": 1.0})
    expected = drift(depress(w0, w0, pattern(CUE_A), {"PPL1": 1.0}, cmap, p), w0, p, 2)
    assert np.allclose(W, expected)


def test_no_dopamine_resolution_only_drifts_and_dequeues(w0, cmap):
    p = PlasticityParams(learning_rate=0.5, floor_fraction=0.2, drift_rate=0.1,
                         drift_steps_per_resolution=1, kc_rate_ref_hz=100.0)
    net = make_net(w0, cmap, p)
    net.record_decision("m0", pattern(CUE_A))
    net.record_decision("m1", pattern(CUE_A))
    net.resolve("m0", {"PPL1": 1.0})
    before = net.weights.copy()
    net.resolve("m1", {})  # e.g. reward exactly 0 -> reward.dopamine_signal(...).strengths() == {}
    assert len(net.queue) == 0
    assert (np.abs(net.weights - w0) <= np.abs(before - w0) + 1e-15).all()  # drifted back


def test_weights_view_is_read_only_and_reset_restores(w0, cmap):
    net = make_net(w0, cmap)
    with pytest.raises(ValueError):
        net.weights[0, 0] = 9.0
    net.record_decision("m1", pattern(CUE_A))
    net.resolve("m1", {"PPL1": 1.0})
    net.record_decision("m2", pattern(CUE_B))
    net.reset()
    assert np.array_equal(net.weights, w0) and len(net.queue) == 0
    net.record_decision("m2", pattern(CUE_B))  # id is free again after reset


def test_advance_is_drift_only(w0, cmap):
    net = make_net(w0, cmap)
    net.record_decision("m1", pattern(CUE_A))
    net.resolve("m1", {"PPL1": 1.0})
    dev = np.abs(net.weights - w0).sum()
    net.advance(20)
    assert np.abs(net.weights - w0).sum() < dev * (1 - P.drift_rate) ** 20 + 1e-9


def test_custom_fine_grained_dopamine_types(w0):
    """Keys are arbitrary: a per-type map ('PAM06'-style) works the same way."""
    m = np.zeros(len(LABELS))
    m[3] = 1.0
    cm = CompartmentMap(len(LABELS), {"PAM06": m, "PAM07": np.zeros(len(LABELS))})
    new = depress(w0, w0, pattern(CUE_A), {"PAM06": 1.0}, cm, P)
    assert (new[CUE_A, 3] < w0[CUE_A, 3]).all()
    others = [j for j in range(len(LABELS)) if j != 3]
    assert np.array_equal(new[:, others], w0[:, others])
    assert np.array_equal(depress(w0, w0, pattern(CUE_A), {"PAM07": 1.0}, cm, P), w0)


def test_shape_and_value_validation(w0, cmap):
    with pytest.raises(ValueError):
        depress(w0, w0[:, :3], pattern(CUE_A), {"PPL1": 1.0}, cmap, P)
    with pytest.raises(ValueError):
        depress(w0, w0, pattern(CUE_A, n=N_KC + 1), {"PPL1": 1.0}, cmap, P)
    with pytest.raises(ValueError):
        depress(w0, w0, pattern(CUE_A), {"PPL1": 1.5}, cmap, P)
    with pytest.raises(ValueError):
        depress(w0, w0, pattern(CUE_A), {"PPL1": float("nan")}, cmap, P)
    with pytest.raises(ValueError):
        depress(w0[:, :3], w0[:, :3], pattern(CUE_A), {"PPL1": 1.0}, cmap, P)  # map size mismatch
    bad = w0.copy()
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        depress(bad, w0, pattern(CUE_A), {"PPL1": 1.0}, cmap, P)


# ---- THE IMPORTANT ONE: "everything smells bad" ---------------------------- #
def toy_rates(W, kc_pattern):
    """Linear stand-in for the simulator: MBON rate = sum_k W[k, j] * KC rate_k."""
    return kc_pattern @ W


def test_repeated_punishment_on_one_cue_leaves_the_other_cue_untouched(w0, cmap):
    """Prior work learned a blanket aversion. Punishing cue A over and over must not
    move ANY weight that cue B (a disjoint KC pool) uses - checked with drift ON and
    with the full default parameter set, not just the isolated test parameters."""
    for params in (P, PlasticityParams()):
        net = make_net(w0, cmap, params)
        for i in range(200):
            net.record_decision(f"m{i}", pattern(CUE_A))
            net.resolve(f"m{i}", {"PPL1": 1.0})  # punish cue A every time
        W = net.weights

        # Cue A really did learn (so this test can fail) ...
        assert (W[np.ix_(CUE_A, PPL1_COLS)] < 0.9 * w0[np.ix_(CUE_A, PPL1_COLS)]).all()
        # ... cue B's KC->MBON weights are bit-identical to the connectome on ALL MBONs ...
        assert np.array_equal(W[CUE_B], w0[CUE_B])
        # ... as are all idle KCs, and cue A's non-punished (PAM / no-compartment) columns.
        assert np.array_equal(W[IDLE], w0[IDLE])
        untouched = PAM_COLS + NO_COMPARTMENT_COLS
        assert np.array_equal(W[np.ix_(CUE_A, untouched)], w0[np.ix_(CUE_A, untouched)])
        # Consequently cue B's MBON output is exactly what it was before any learning.
        assert np.array_equal(toy_rates(W, pattern(CUE_B)), toy_rates(w0, pattern(CUE_B)))


def test_punishment_lowers_only_the_punished_cues_circuit_score(w0, cmap):
    table = load_sign_table("circuit_80")

    def score(W, cue):
        return circuit_score(toy_rates(W, pattern(cue)), LABELS, table).score

    base_a, base_b = score(w0, CUE_A), score(w0, CUE_B)
    net = make_net(w0, cmap)
    for i in range(50):
        net.record_decision(f"m{i}", pattern(CUE_A))
        net.resolve(f"m{i}", {"PPL1": 1.0})
    assert score(net.weights, CUE_A) < base_a  # punished cue: weaker approach drive
    assert score(net.weights, CUE_B) == base_b  # other cue: unchanged
    # the floor bounds how far the punished cue's score can fall
    floor_w = w0.copy()
    floor_w[np.ix_(CUE_A, PPL1_COLS)] *= P.floor_fraction
    assert score(net.weights, CUE_A) >= score(floor_w, CUE_A) - 1e-9


def test_reward_raises_and_punishment_lowers_a_cues_score(w0, cmap):
    """Sign consistency between plasticity and the CIRCUIT readout: reward (PAM)
    depresses avoidance-like MBONs -> score up; punishment (PPL1) depresses
    approach-like MBONs -> score down."""
    table = load_sign_table("circuit_80")

    def score(W):
        return circuit_score(toy_rates(W, pattern(CUE_A)), LABELS, table).score

    base = score(w0)
    for outcome, direction in ((-0.8, -1), (+0.8, +1)):
        net = make_net(w0, cmap)
        net.record_decision("m", pattern(CUE_A))
        sig = dopamine_signal(profit_reward(outcome))
        net.resolve("m", sig.strengths())
        assert direction * (score(net.weights) - base) > 0, outcome


def test_cues_that_share_kcs_do_interfere_on_the_shared_rows(w0, cmap):
    """Documents the limit of the guarantee: it is per-KC. Overlapping pools share rows."""
    overlap_b = np.concatenate([CUE_B, CUE_A[:2]])  # shares KCs 0 and 1 with cue A
    net = make_net(w0, cmap)
    net.record_decision("m", pattern(CUE_A))
    net.resolve("m", {"PPL1": 1.0})
    W = net.weights
    assert (W[np.ix_(CUE_A[:2], PPL1_COLS)] < w0[np.ix_(CUE_A[:2], PPL1_COLS)]).all()
    assert np.array_equal(W[CUE_B], w0[CUE_B])
    rates_before = toy_rates(w0, pattern(overlap_b))
    rates_after = toy_rates(W, pattern(overlap_b))
    assert not np.array_equal(rates_before, rates_after)
