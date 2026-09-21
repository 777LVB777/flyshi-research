from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import graded_check as gc  # noqa: E402
from flyshi_research.learning.params import EncoderParams  # noqa: E402
from flyshi_research.learning.readout import SignTable  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
IDS_PATH = REPO / "repro" / "mushroom_body" / "neuron_ids_783.json"
DOC = REPO / "docs" / "design" / "graded-encoding.md"
RATES = gc.PRESTATED_RATES_HZ

# Tiny table/labels: A approach-like (+1), B avoidance-like (-1); "Z" unlisted.
TABLE = SignTable("t", {"A": 1, "B": -1})
LABELS = ["A", "A", "B", "B", "Z"]


def vecs(a_by_rate, b=0.0, z=0.0):
    """MBON vectors over LABELS: both A instances at a(r), both B at b, Z at z."""
    return {r: [a_by_rate(r), a_by_rate(r), b, b, z] for r in RATES}


# ---- the pre-stated constants ---------------------------------------------- #
def test_prestated_constants():
    assert RATES == (30.0, 60.0, 90.0, 120.0, 150.0)
    assert gc.D_AA_NOISE_FLOOR_HZ == 5.10 and gc.NOISE_MARGIN == 3.0
    assert gc.DISTANCE_THRESHOLD_HZ == pytest.approx(15.30)
    assert gc.MIN_SUBRANGE_RATES == 3
    assert (gc.PRESTATED_DURATION_MS, gc.PRESTATED_TRIALS) == (1000.0, 5)
    assert (gc.PRESTATED_KC_SET_SIZE, gc.PRESTATED_KC_SET_SEED) == (100, 20260316)
    assert (gc.PRESTATED_SIGN_TABLE, gc.PRESTATED_AGGREGATION) == ("circuit_80", "type_mean")
    assert [v.value for v in gc.Verdict] == ["ACCEPTED", "USABLE RANGE", "FAIL"]


def test_design_doc_states_the_same_numbers_and_the_three_outcomes():
    text = " ".join(DOC.read_text().split())  # whitespace-normalised: independent of line wrapping
    for needle in ("30, 60, 90, 120 and 150", "20260316", "5.10", "15.30", "strictly monotonic",
                   "circuit_80", "type_mean", "1000 ms", "ACCEPTED", "USABLE RANGE", "FAIL",
                   "at least three", "saturation", "tie-break", "sub-range gate",
                   "own endpoint distance", "equal the validated range", "min_rate_hz"):
        assert needle in text, needle
    assert "value encoding by rate fails" in text and "before any learning experiment" in text
    # the revision was made before any run, and the doc says so
    assert "revised before the test was run" in text
    # both revisions are recorded as having been made before any run
    assert "sub-range gate was added before any run" in text


# ---- monotonic runs -------------------------------------------------------- #
@pytest.mark.parametrize(
    "values,expected",
    [
        ([1, 2, 3, 4, 5], (True, "increasing")),
        ([5, 4, 3, 2, 1], (True, "decreasing")),
        ([1, 2, 2, 4, 5], (False, "none")),  # a tie is a violation
        ([1, 3, 2, 4, 5], (False, "none")),  # a reversal
        ([0, 0, 0, 0, 0], (False, "none")),  # flat
    ],
)
def test_strictly_monotonic(values, expected):
    assert gc.strictly_monotonic(values) == expected


def spans(values):
    return [(r.start, r.end, r.direction) for r in gc.monotonic_runs(values)]


def test_monotonic_runs_are_maximal_and_share_turning_points():
    assert spans([1, 2, 3, 4, 5]) == [(0, 4, "increasing")]
    assert spans([1, 3, 2, 4, 5]) == [(0, 1, "increasing"), (1, 2, "decreasing"), (2, 4, "increasing")]
    assert spans([5, 15, 25, 35, 35]) == [(0, 3, "increasing")]  # a tie ends the run
    assert spans([0, 0, 6, 12, 30]) == [(1, 4, "increasing")]  # ... and belongs to none
    assert spans([2, 2, 2, 2, 2]) == []


def test_select_usable_subrange_picks_the_longest():
    best, tied = gc.select_usable_subrange([5, 15, 25, 35, 35])
    assert (best.start, best.end) == (0, 3) and best.n_rates == 4 and tied == (best,)
    best, _ = gc.select_usable_subrange([0, 0, 6, 12, 30])
    assert (best.start, best.end) == (1, 4)
    best, _ = gc.select_usable_subrange([10, 5, 20, 30, 25])  # breaks at BOTH ends
    assert (best.start, best.end, best.direction) == (1, 3, "increasing")


def test_select_usable_subrange_requires_at_least_three_rates():
    assert gc.select_usable_subrange([3, 40, 10, 60, 45]) == (None, ())  # zigzag: runs of 2
    assert gc.select_usable_subrange([1, 2, 2, 3, 3]) == (None, ())
    best, _ = gc.select_usable_subrange([1, 2, 3, 2, 1], min_rates=3)
    assert best is not None
    assert gc.select_usable_subrange([1, 2, 1, 2, 1], min_rates=2)[0] is not None  # param honoured


def test_tie_break_larger_score_change_then_lower_start():
    # Rise of 35 (rates idx 0-2) vs fall of 20 (idx 2-4): same length, larger change wins.
    best, tied = gc.select_usable_subrange([5, 20, 40, 30, 20])
    assert (best.start, best.end, best.direction) == (0, 2, "increasing")
    assert [(r.start, r.end) for r in tied] == [(0, 2), (2, 4)]  # both are reported
    # Fall is now the bigger change: it wins although it starts later.
    best, _ = gc.select_usable_subrange([30, 35, 40, 20, 0])
    assert (best.start, best.end, best.direction) == (2, 4, "decreasing")
    # Exactly equal change: the lower starting rate wins.
    best, _ = gc.select_usable_subrange([0, 10, 20, 10, 0])
    assert (best.start, best.end) == (0, 2)


def test_euclidean():
    assert gc.euclidean([0, 0], [3, 4]) == 5.0
    with pytest.raises(ValueError):
        gc.euclidean([0], [0, 1])


# ---- ACCEPTED ---------------------------------------------------------------- #
def test_accepted_when_monotonic_across_all_five_and_far_from_noise():
    r = gc.evaluate(vecs(lambda x: x / 10.0), LABELS, TABLE)  # A: 3,6,9,12,15 Hz
    assert r.scores == (3.0, 6.0, 9.0, 12.0, 15.0)  # type mean: two A instances -> one vote
    assert r.monotonic and r.direction == "increasing"
    assert r.distance_lo_hi_hz == pytest.approx(np.sqrt(2 * 12.0**2))  # 16.97 Hz
    assert r.distance_ok
    assert r.verdict == gc.Verdict.ACCEPTED and r.accepted
    assert r.validated_range_hz == (30.0, 150.0) and r.fail_reasons == ()


def test_decreasing_scores_also_count_as_monotonic():
    r = gc.evaluate(vecs(lambda x: 20.0 - x / 10.0), LABELS, TABLE)
    assert r.verdict == gc.Verdict.ACCEPTED and r.direction == "decreasing"
    assert r.validated_direction == "decreasing"


# ---- USABLE RANGE ------------------------------------------------------------ #
def a_shape(*values):
    """A response with the given CIRCUIT score at 30, 60, 90, 120, 150 Hz."""
    table = dict(zip(RATES, values))
    return vecs(lambda x: table[x])


def test_saturation_at_the_top_gives_a_usable_range():
    """The motivating case: response rises then plateaus at high rates."""
    r = gc.evaluate(a_shape(5, 15, 25, 35, 35), LABELS, TABLE)
    assert r.distance_ok and not r.monotonic
    assert r.verdict == gc.Verdict.USABLE_RANGE and not r.accepted
    assert r.validated_range_hz == (30.0, 120.0) and r.validated_direction == "increasing"
    assert r.fail_reasons == ()


def test_decline_after_a_peak_at_the_top_gives_a_usable_range():
    r = gc.evaluate(a_shape(5, 15, 25, 35, 30), LABELS, TABLE)
    assert r.verdict == gc.Verdict.USABLE_RANGE and r.validated_range_hz == (30.0, 120.0)


def test_silent_low_rates_give_a_usable_range_at_the_bottom():
    r = gc.evaluate(a_shape(0, 0, 6, 12, 30), LABELS, TABLE)  # nothing until 60-90 Hz
    assert r.verdict == gc.Verdict.USABLE_RANGE and r.validated_range_hz == (60.0, 150.0)


def test_breaks_at_both_ends_leave_the_middle_three_rates():
    r = gc.evaluate(a_shape(10, 5, 20, 30, 25), LABELS, TABLE)
    assert r.verdict == gc.Verdict.USABLE_RANGE and r.validated_range_hz == (60.0, 120.0)


def test_an_interior_break_is_usable_if_a_three_rate_run_remains():
    r = gc.evaluate(a_shape(3, 20, 10, 25, 40), LABELS, TABLE)
    assert r.verdict == gc.Verdict.USABLE_RANGE and r.validated_range_hz == (90.0, 150.0)


def test_tied_longest_subranges_are_reported_and_resolved_by_the_prestated_tie_break():
    r = gc.evaluate(a_shape(5, 20, 40, 30, 20), LABELS, TABLE)  # rises 30-90, falls 90-150
    assert r.verdict == gc.Verdict.USABLE_RANGE
    assert r.validated_range_hz == (30.0, 90.0) and r.validated_direction == "increasing"
    assert r.tied_longest_subranges_hz == ((30.0, 90.0), (90.0, 150.0))
    assert any("tied for longest" in l for l in r.summary_lines())


def test_usable_range_summary_says_the_encoder_bounds_must_be_restricted():
    r = gc.evaluate(a_shape(5, 15, 25, 35, 35), LABELS, TABLE)
    text = "\n".join(r.summary_lines())
    assert "VERDICT: USABLE RANGE" in text
    assert "must EQUAL 30-120 Hz" in text and "before any learning experiment" in text


def test_a_usable_range_whose_own_change_clears_the_noise_passes_the_subrange_gate():
    r = gc.evaluate(a_shape(5, 15, 25, 35, 35), LABELS, TABLE)  # chosen 30-120: 5 -> 35
    assert r.verdict == gc.Verdict.USABLE_RANGE
    assert r.chosen_subrange_hz == (30.0, 120.0)
    assert r.chosen_subrange_distance_hz == pytest.approx(np.sqrt(2) * 30.0)
    assert r.chosen_subrange_distance_ok is True
    assert any("sub-range gate" in l and "pass" in l for l in r.summary_lines())


def test_subrange_gate_uses_mbon_vectors_not_scores():
    """Scores over the chosen sub-range barely move (5 -> 7), but an unlisted MBON type
    'Z' (weight 0) changes a lot there: the MBON VECTOR distance is large, so it passes."""
    z = {30.0: 0.0, 60.0: 15.0, 90.0: 30.0, 120.0: 30.0, 150.0: 30.0}
    a = {30.0: 5.0, 60.0: 6.0, 90.0: 7.0, 120.0: 6.5, 150.0: 20.0}  # chosen run: 30-90 Hz
    with_z = {r: [a[r], a[r], 0.0, 0.0, z[r]] for r in RATES}
    r = gc.evaluate(with_z, LABELS, TABLE)
    assert r.chosen_subrange_hz == (30.0, 90.0) and r.scores[:3] == (5.0, 6.0, 7.0)
    assert r.chosen_subrange_distance_hz > 30.0 and r.verdict == gc.Verdict.USABLE_RANGE
    no_z = {r_: [a[r_], a[r_], 0.0, 0.0, 0.0] for r_ in RATES}  # same scores, Z silent
    r2 = gc.evaluate(no_z, LABELS, TABLE)
    assert r2.scores == r.scores and r2.chosen_subrange_distance_hz == pytest.approx(np.sqrt(2) * 2.0)
    assert r2.verdict == gc.Verdict.FAIL


# ---- FAIL -------------------------------------------------------------------- #
def test_fail_when_monotonic_but_the_change_is_within_noise():
    # A rises 1 Hz across the whole range: distance = sqrt(2) ~ 1.4 Hz << 15.3
    r = gc.evaluate(vecs(lambda x: 10.0 + (x - 30.0) / 120.0), LABELS, TABLE)
    assert r.monotonic and not r.distance_ok
    assert r.verdict == gc.Verdict.FAIL and r.validated_range_hz is None
    assert len(r.fail_reasons) == 1 and "endpoint distance" in r.fail_reasons[0]


def test_fail_when_no_three_rate_monotonic_subrange_exists_even_if_endpoints_are_far():
    r = gc.evaluate(a_shape(3, 40, 10, 60, 45), LABELS, TABLE)  # zigzag, endpoints 42*sqrt(2) apart
    assert r.distance_ok and r.verdict == gc.Verdict.FAIL
    assert len(r.fail_reasons) == 1 and "no strictly monotonic contiguous sub-range" in r.fail_reasons[0]


def test_fail_lists_both_reasons_when_both_apply():
    r = gc.evaluate(a_shape(5, 20, 10, 25, 5), LABELS, TABLE)  # zigzag AND endpoints equal
    assert r.verdict == gc.Verdict.FAIL and len(r.fail_reasons) == 2


def test_fail_when_everything_is_tied():
    r = gc.evaluate(a_shape(5, 5, 5, 5, 5), LABELS, TABLE)
    assert r.verdict == gc.Verdict.FAIL and r.validated_range_hz is None


def test_fail_when_the_chosen_subrange_change_is_inside_the_noise_even_though_the_endpoints_are_far():
    """The closed loophole. Endpoints: 5 -> 35 (sqrt(2)*30 = 42 Hz, passes). Chosen sub-range
    30-90 Hz: 5 -> 15 (sqrt(2)*10 = 14.1 Hz < 15.30), so it does NOT clear the noise: FAIL."""
    r = gc.evaluate(a_shape(5, 10, 15, 14, 35), LABELS, TABLE)
    assert r.distance_ok and not r.monotonic
    assert r.chosen_subrange_hz == (30.0, 90.0)
    assert r.chosen_subrange_distance_hz == pytest.approx(np.sqrt(2) * 10.0)
    assert r.chosen_subrange_distance_ok is False
    assert r.verdict == gc.Verdict.FAIL and r.validated_range_hz is None
    assert len(r.fail_reasons) == 1 and "chosen sub-range 30-90 Hz" in r.fail_reasons[0]
    text = "\n".join(r.summary_lines())
    assert "sub-range gate" in text and "FAIL" in text
    assert "encoder must change before any learning experiment" in text


def test_subrange_gate_boundary_is_inclusive():
    thr = gc.DISTANCE_THRESHOLD_HZ

    def shape(sub_change):  # one instance: distance == |change|; chosen run is 30-90 Hz
        vals = [0.0, sub_change / 2, sub_change, sub_change * 0.9, 2 * thr + sub_change]
        return {r: [v] for r, v in zip(RATES, vals)}

    at = gc.evaluate(shape(thr), ["A"], TABLE)
    assert at.chosen_subrange_hz == (30.0, 90.0) and at.chosen_subrange_distance_ok is True
    assert at.verdict == gc.Verdict.USABLE_RANGE
    under = gc.evaluate(shape(thr * (1 - 1e-6)), ["A"], TABLE)
    assert under.chosen_subrange_distance_ok is False and under.verdict == gc.Verdict.FAIL


def test_no_fallback_to_a_tied_subrange_that_would_pass():
    """Literal rule: the gate applies to THE chosen sub-range. Two sub-ranges tie for longest;
    the tie-break picks 30-90 Hz (larger CIRCUIT-score change) but its MBON-vector change is spread
    thinly over many types (8.8 Hz), while 90-150 Hz would pass (20 Hz). Verdict: FAIL."""
    table = SignTable("t", {**{f"T{i}": 1 for i in range(16)}, "C": 1})
    labels = [f"T{i}" for i in range(16)] + ["C"]
    t_vals = [0.0, 1.1, 2.2, 2.2, 2.2]  # 16 types rise together during 30-90 Hz
    c_vals = [20.0, 20.0, 20.0, 10.0, 0.0]  # one type falls during 90-150 Hz
    vec = {r: [t] * 16 + [c] for r, t, c in zip(RATES, t_vals, c_vals)}
    r = gc.evaluate(vec, labels, table)
    assert r.tied_longest_subranges_hz == ((30.0, 90.0), (90.0, 150.0))
    assert r.distance_ok  # endpoints are far apart (~21.9 Hz)
    assert r.chosen_subrange_hz == (30.0, 90.0)  # larger score change (35.2 vs 20)
    assert r.chosen_subrange_distance_hz == pytest.approx(8.8)
    assert gc.euclidean(vec[90.0], vec[150.0]) >= gc.DISTANCE_THRESHOLD_HZ  # the alternative passes
    assert r.verdict == gc.Verdict.FAIL and r.validated_range_hz is None


def test_endpoint_gate_uses_the_30_and_150_hz_vectors_even_if_the_subrange_excludes_one():
    """Literal rule: 'endpoint distance' means 30 vs 150 Hz. Here the 60-150 Hz sub-range
    changes a lot (0 -> 45, so it would pass its own gate) but 30 Hz and 150 Hz look alike
    (40 vs 45), so it FAILS."""
    r = gc.evaluate(a_shape(40, 0, 20, 30, 45), LABELS, TABLE)
    assert not r.distance_ok and r.verdict == gc.Verdict.FAIL
    assert r.chosen_subrange_hz == (60.0, 150.0) and r.chosen_subrange_distance_ok is True
    assert len(r.fail_reasons) == 1 and "endpoint distance" in r.fail_reasons[0]


def test_fail_summary_says_the_encoder_must_change():
    r = gc.evaluate(a_shape(3, 40, 10, 60, 45), LABELS, TABLE)
    text = "\n".join(r.summary_lines())
    assert "VERDICT: FAIL" in text
    assert "value encoding by rate fails" in text.lower()
    assert "encoder must change before any learning experiment" in text


def test_distance_threshold_boundary_is_inclusive():
    # One instance, so the Euclidean distance is exactly |change|: put it AT the threshold.
    thr = gc.DISTANCE_THRESHOLD_HZ

    def one_instance(total_change):
        return {r: [(r - 30.0) / 120.0 * total_change] for r in RATES}

    at = gc.evaluate(one_instance(thr), ["A"], TABLE)
    assert at.distance_ok and at.verdict == gc.Verdict.ACCEPTED  # == 15.30 passes (>=)
    just_under = gc.evaluate(one_instance(thr * (1 - 1e-6)), ["A"], TABLE)
    assert not just_under.distance_ok and just_under.monotonic
    assert just_under.verdict == gc.Verdict.FAIL


def test_score_uses_the_type_mean_over_all_instances_including_silent():
    v = {r: [30.0, 0.0, 0.0, 0.0, 0.0] for r in RATES}  # one A instance fires, one is silent
    assert gc.evaluate(v, LABELS, TABLE).scores[0] == 15.0  # mean of (30, 0), not 30


def test_avoidance_like_activity_lowers_the_score():
    r = gc.evaluate(vecs(lambda x: 10.0, b=4.0), LABELS, TABLE)
    assert r.scores[0] == 10.0 - 4.0


def test_requires_exactly_the_five_prestated_rates():
    ok = vecs(lambda x: x)
    with pytest.raises(ValueError, match="pre-stated"):
        gc.evaluate({r: ok[r] for r in RATES[:4]}, LABELS, TABLE)
    with pytest.raises(ValueError, match="pre-stated"):
        gc.evaluate({**ok, 45.0: ok[30.0]}, LABELS, TABLE)


def test_diagnostics_are_reported_but_do_not_change_the_verdict():
    r = gc.evaluate(vecs(lambda x: x / 10.0), LABELS, TABLE)
    assert r.distances_from_lowest_hz[0] == 0.0
    assert r.vector_distance_nondecreasing
    assert r.n_nonzero_mbons == (2,) * 5
    assert r.n_mbons_active == 2 and r.n_mbons_weakly_monotonic == 2
    assert r.chosen_subrange_hz == (30.0, 150.0)  # monotonic: the chosen sub-range IS the full range
    assert r.chosen_subrange_distance_hz == pytest.approx(r.distance_lo_hi_hz)
    text = "\n".join(r.summary_lines())
    assert "VERDICT: ACCEPTED" in text and "single seed" not in text  # note lives on the object
    assert "single seed" in r.score_noise_note


def test_default_table_is_circuit_80_from_the_data_file():
    """With no table given, the pre-stated CIRCUIT 80% table is loaded from data."""
    mbons = json.loads(IDS_PATH.read_text())["mbons"]["records"]
    labels = [m["cell_type"] for m in mbons]
    v = {r: np.zeros(len(mbons)) for r in RATES}
    for r in RATES:  # approach-like MBON11 rises with the stimulus rate
        for i, lab in enumerate(labels):
            if lab == "MBON11":
                v[r][i] = r / 5.0
    res = gc.evaluate(v, labels)
    assert res.scores[0] == pytest.approx(30.0 / 5.0)  # both MBON11 instances at 6 Hz -> mean 6
    assert res.monotonic and res.direction == "increasing"
    # two MBON11 instances each rising 6 -> 30 Hz: sqrt(2) * 24 = 33.9 Hz >= 15.3 -> ACCEPTED
    assert res.distance_lo_hi_hz == pytest.approx(np.sqrt(2) * 24.0)
    assert res.verdict == gc.Verdict.ACCEPTED


# ---- what the verdict means for the encoder's rate bounds -------------------- #
def test_validated_encoder_bounds_follow_the_verdict():
    accepted = gc.evaluate(vecs(lambda x: x / 10.0), LABELS, TABLE)
    usable = gc.evaluate(a_shape(5, 15, 25, 35, 35), LABELS, TABLE)
    fail = gc.evaluate(a_shape(3, 40, 10, 60, 45), LABELS, TABLE)
    assert gc.validated_encoder_bounds(accepted) == (30.0, 150.0)  # all five rates
    assert gc.validated_encoder_bounds(usable) == (30.0, 120.0)  # the sub-range
    with pytest.raises(ValueError, match="encoder must change"):
        gc.validated_encoder_bounds(fail)


def test_encoder_params_for_sets_min_and_max_and_keeps_everything_else():
    usable = gc.evaluate(a_shape(0, 0, 6, 12, 30), LABELS, TABLE)  # validated 60-150
    base = EncoderParams(pool_size=50, pool_seed=7)
    p = gc.encoder_params_for(usable, base)
    assert (p.min_rate_hz, p.max_rate_hz) == (60.0, 150.0)
    assert p.pool_size == 50 and p.pool_seed == 7 and p.features == base.features
    gc.require_encoder_matches(p, usable)  # passes


def test_require_encoder_matches_rejects_any_other_bounds():
    usable = gc.evaluate(a_shape(5, 15, 25, 35, 35), LABELS, TABLE)  # validated 30-120
    with pytest.raises(ValueError, match="do not equal the validated range"):
        gc.require_encoder_matches(EncoderParams(), usable)  # default is 30-150: too wide
    with pytest.raises(ValueError, match="do not equal"):
        gc.require_encoder_matches(EncoderParams(min_rate_hz=40.0, max_rate_hz=120.0), usable)
    fail = gc.evaluate(a_shape(3, 40, 10, 60, 45), LABELS, TABLE)
    with pytest.raises(ValueError, match="encoder must change"):
        gc.require_encoder_matches(EncoderParams(), fail)


def test_placeholder_encoder_bounds_sit_inside_the_tested_range_and_match_accepted():
    """The encoder cannot emit a rate below anything the graded test covers, and the
    placeholder equals what an ACCEPTED verdict would validate."""
    p = EncoderParams()
    assert p.min_rate_hz >= gc.PRESTATED_RATES_HZ[0] and p.max_rate_hz <= gc.PRESTATED_RATES_HZ[-1]
    accepted = gc.evaluate(vecs(lambda x: x / 10.0), LABELS, TABLE)
    gc.require_encoder_matches(p, accepted)


# ---- the script's analysis path, on synthetic result files (no simulation) -- #
def load_script():
    pytest.importorskip("pandas")
    spec = importlib.util.spec_from_file_location(
        "run_graded_rate", REPO / "repro" / "mushroom_body" / "run_graded_rate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # top level imports numpy/pandas only, never Brian2
    return mod


def prestated_args(**over):
    base = dict(seed=gc.PRESTATED_SEED, duration_ms=gc.PRESTATED_DURATION_MS,
                trials=gc.PRESTATED_TRIALS, kc_set_size=gc.PRESTATED_KC_SET_SIZE,
                kc_set_seed=gc.PRESTATED_KC_SET_SEED)
    base.update(over)
    return SimpleNamespace(**base)


def write_results(script, args, results_dir, a_by_rate, skip=()):
    """Write one CSV per rate in the runner's format: only MBONs that fired."""
    mbons = json.loads(IDS_PATH.read_text())["mbons"]["records"]
    for rate in RATES:
        if rate in skip:
            continue
        rows = ["seed,duration_ms,trials,rate_hz_stim,root_id,cell_type,side,rate_hz"]
        for m in mbons:
            val = a_by_rate(rate) if m["cell_type"] == "MBON11" else 0.0
            if val > 0:
                rows.append(f"{args.seed},{args.duration_ms},{args.trials},{rate:g},"
                            f"{m['root_id']},{m['cell_type']},{m['side']},{val}")
        script.output_path(rate, args, results_dir).write_text("\n".join(rows) + "\n")


def run_script_analysis(tmp_path, a_by_rate):
    script, args = load_script(), prestated_args()
    write_results(script, args, tmp_path, a_by_rate)
    lines = []
    res = script.analyze(args, log=lines.append, results_dir=tmp_path, calib=tmp_path / "none.csv")
    verdict = json.loads((tmp_path / f"{script.summary_stem(args)}_verdict.json").read_text())
    return res, verdict, "\n".join(lines)


def test_script_analysis_accepts_a_monotonic_synthetic_response(tmp_path):
    res, verdict, out = run_script_analysis(tmp_path, lambda r: r / 5.0)  # MBON11: 6..30 Hz
    assert res is not None and res.accepted and res.verdict == gc.Verdict.ACCEPTED
    assert res.scores == pytest.approx((6.0, 12.0, 18.0, 24.0, 30.0))
    assert "VERDICT: ACCEPTED" in out and "NOT THE PRE-STATED TEST" not in out
    assert verdict["verdict"] == "ACCEPTED" and verdict["accepted"] is True
    assert verdict["prestated_test"] is True and verdict["fail_reasons"] == []
    assert verdict["validated_range_hz"] == [30.0, 150.0]
    assert verdict["monotonic_all_five_rates"] is True
    assert (tmp_path / f"{load_script().summary_stem(prestated_args())}_summary.csv").exists()


def test_script_analysis_reports_a_usable_range_for_a_partly_monotonic_response(tmp_path):
    shape = {30.0: 5.0, 60.0: 20.0, 90.0: 10.0, 120.0: 25.0, 150.0: 40.0}  # dip at 90 Hz
    res, verdict, out = run_script_analysis(tmp_path, lambda r: shape[r])
    assert res.verdict == gc.Verdict.USABLE_RANGE and not res.accepted
    assert "VERDICT: USABLE RANGE" in out and "must EQUAL 90-150 Hz" in out
    assert verdict["verdict"] == "USABLE RANGE" and verdict["accepted"] is False
    assert verdict["validated_range_hz"] == [90.0, 150.0]
    assert verdict["validated_direction"] == "increasing"
    assert verdict["monotonic_all_five_rates"] is False and verdict["fail_reasons"] == []
    assert verdict["chosen_subrange_hz"] == [90.0, 150.0]
    assert verdict["chosen_subrange_distance_ok"] is True


def test_script_analysis_reports_saturation_as_a_usable_range(tmp_path):
    sat = {30.0: 5.0, 60.0: 15.0, 90.0: 25.0, 120.0: 30.0, 150.0: 30.0}  # plateau at the top
    res, verdict, _ = run_script_analysis(tmp_path, lambda r: sat[r])
    assert verdict["verdict"] == "USABLE RANGE" and verdict["validated_range_hz"] == [30.0, 120.0]


def test_script_analysis_fails_a_subrange_that_does_not_clear_the_noise(tmp_path):
    shape = {30.0: 5.0, 60.0: 10.0, 90.0: 15.0, 120.0: 14.0, 150.0: 35.0}  # chosen 30-90: 5 -> 15
    res, verdict, out = run_script_analysis(tmp_path, lambda r: shape[r])
    assert res.verdict == gc.Verdict.FAIL and verdict["verdict"] == "FAIL"
    assert verdict["validated_range_hz"] is None
    assert verdict["chosen_subrange_hz"] == [30.0, 90.0]
    assert verdict["chosen_subrange_distance_ok"] is False
    assert "chosen sub-range 30-90 Hz" in verdict["fail_reasons"][0]
    assert "sub-range gate" in out


def test_script_analysis_reports_fail_with_reasons_and_no_validated_range(tmp_path):
    shape = {30.0: 5.0, 60.0: 40.0, 90.0: 10.0, 120.0: 60.0, 150.0: 45.0}  # zigzag
    res, verdict, out = run_script_analysis(tmp_path, lambda r: shape[r])
    assert res.verdict == gc.Verdict.FAIL
    assert "VERDICT: FAIL" in out and "encoder must change before any learning experiment" in out
    assert verdict["verdict"] == "FAIL" and verdict["accepted"] is False
    assert verdict["validated_range_hz"] is None and verdict["validated_direction"] is None
    assert verdict["fail_reasons"] and "no strictly monotonic" in verdict["fail_reasons"][0]


def test_script_analysis_waits_for_all_five_rates(tmp_path):
    script, args = load_script(), prestated_args()
    write_results(script, args, tmp_path, lambda r: r / 5.0, skip=(120.0,))
    lines = []
    assert script.analyze(args, log=lines.append, results_dir=tmp_path) is None
    assert "120" in "\n".join(lines) and "missing" in "\n".join(lines)
    assert not list(tmp_path.glob("*verdict.json"))  # no verdict from partial data


def test_script_labels_non_prestated_settings_as_exploratory(tmp_path):
    script = load_script()
    args = prestated_args(duration_ms=100.0, trials=1)  # e.g. a smoke run
    assert not script.is_prestated(args) and script.is_prestated(prestated_args())
    write_results(script, args, tmp_path, lambda r: r / 5.0)
    lines = []
    script.analyze(args, log=lines.append, results_dir=tmp_path, write=False)
    assert "NOT THE PRE-STATED TEST" in "\n".join(lines)


def test_script_output_names_are_per_rate_and_per_setting():
    script = load_script()
    a, b = prestated_args(), prestated_args(seed=1)
    names = {script.output_path(r, a, Path(".")).name for r in RATES}
    assert len(names) == 5  # one file per rate
    assert script.output_path(30.0, a, Path(".")) != script.output_path(30.0, b, Path("."))


def test_script_rejects_result_files_containing_non_mbon_ids(tmp_path):
    script, args = load_script(), prestated_args()
    write_results(script, args, tmp_path, lambda r: r / 5.0)
    bad = script.output_path(30.0, args, tmp_path)
    bad.write_text(bad.read_text() + f"1,1000,5,30,123,MBON99,left,4.0\n")
    with pytest.raises(ValueError, match="not MBONs"):
        script.analyze(args, log=lambda s: None, results_dir=tmp_path, write=False)


def test_script_defaults_are_the_prestated_settings():
    script = load_script()
    ns = script.parser().parse_args([])
    assert script.is_prestated(ns) and not ns.analyze_only
