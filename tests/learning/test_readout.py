from __future__ import annotations

import json

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning.readout import (  # noqa: E402
    Choice,
    SignTable,
    circuit_score,
    decide,
    dominant_family,
    load_dopamine_counts,
    load_sign_table,
)


# ---- dominant-family rule ------------------------------------------------- #
def test_dominant_family_basic_and_boundary():
    assert dominant_family(90, 10, 80) == "PAM"  # exactly 90%
    assert dominant_family(80, 20, 80) == "PAM"  # exactly at threshold counts (>=)
    assert dominant_family(79, 21, 80) is None
    assert dominant_family(10, 90, 80) == "PPL1"
    assert dominant_family(0, 0, 80) is None  # no annotated input
    with pytest.raises(ValueError):
        dominant_family(1, 1, 50)  # 50% would allow both families
    with pytest.raises(ValueError):
        dominant_family(1, 1, 101)


# ---- sign tables loaded from data, checked against the design doc --------- #
def test_circuit_80_matches_design_doc_assignments():
    t = load_sign_table("circuit_80")
    avoidance = ["MBON01", "MBON02", "MBON03", "MBON04", "MBON05", "MBON06", "MBON07",
                 "MBON09", "MBON10", "MBON21"]
    approach = ["MBON11", "MBON12", "MBON13", "MBON14", "MBON15", "MBON16", "MBON17",
                "MBON18", "MBON19"]
    for l in avoidance:
        assert t.weight(l) == -1, l
    for l in approach:
        assert t.weight(l) == +1, l
    assert t.weight("MBON08") == 0  # no direct annotated dopamine input (reported exception)
    assert t.is_listed("MBON08")


def test_circuit_70_equals_80_and_90_changes_as_documented():
    t70, t80, t90 = (load_sign_table(f"circuit_{x}") for x in (70, 80, 90))
    assert dict(t70.weights) == dict(t80.weights)  # doc: "No type reverses sign"
    assert t90.weight("MBON03") == -1  # 99.9% PAM stays
    assert t90.weight("MBON04") == 0  # 88.7% PAM drops out at 90%
    assert t90.weight("MBON10") == 0  # 85.3% PAM drops out
    assert t90.weight("MBON15") == 0  # 86.7% PPL1 drops out
    # the four confident behavioural labels still agree at every threshold
    for t in (t70, t80, t90):
        assert (t.weight("MBON05"), t.weight("MBON21")) == (-1, -1)
        assert (t.weight("MBON11"), t.weight("MBON12")) == (1, 1)


def test_circuit_tables_only_differ_at_documented_labels():
    t80, t90 = load_sign_table("circuit_80"), load_sign_table("circuit_90")
    changed = {l for l in t80.weights if t80.weight(l) != t90.weight(l)}
    assert changed == {"MBON04", "MBON10", "MBON15"}


def test_strict_and_group_tables():
    strict, group = load_sign_table("strict"), load_sign_table("group")
    assert {l: w for l, w in strict.weights.items()} == {
        "MBON05": -1, "MBON21": -1, "MBON11": 1, "MBON12": 1}
    for l, w in strict.weights.items():
        assert group.weight(l) == w  # GROUP = STRICT + group-level labels
    for l in ("MBON01", "MBON03", "MBON04"):
        assert group.weight(l) == -1
    for l in ("MBON08", "MBON09", "MBON15", "MBON16", "MBON17", "MBON18", "MBON19"):
        assert group.weight(l) == +1
    assert group.weight("MBON02") == 0  # conflicted: excluded from both
    assert strict.weight("MBON03") == 0  # group-only label not in STRICT


def test_unknown_table_name_raises():
    with pytest.raises(ValueError, match="unknown sign table"):
        load_sign_table("bogus")


def test_tables_are_loaded_from_data_files_not_hardcoded(tmp_path):
    """A custom data dir changes the table: proves the values come from files."""
    (tmp_path / "mbon_dopamine_input.json").write_text(json.dumps(
        {"counts": {"MBON01": {"pam": 1, "ppl1": 99}, "MBON02": {"pam": 99, "ppl1": 1}}}))
    (tmp_path / "mbon_sign_tables.json").write_text(json.dumps(
        {"tables": {"strict": {"weights": {"MBON02": 1}}}}))
    c = load_sign_table("circuit_80", data_dir=tmp_path)
    assert (c.weight("MBON01"), c.weight("MBON02")) == (1, -1)  # opposite of the real data
    assert load_sign_table("strict", data_dir=tmp_path).weight("MBON02") == 1


def test_sign_table_from_json_and_validation(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"weights": {"MBON01": 1, "MBON02": -1}, "description": "x"}))
    t = SignTable.from_json(p)
    assert (t.weight("MBON01"), t.weight("MBON02"), t.weight("MBON99")) == (1, -1, 0)
    with pytest.raises(ValueError):
        SignTable("bad", {"MBON01": 2})


def test_dopamine_counts_file_is_well_formed():
    counts = load_dopamine_counts()
    assert len(counts) == 20 and counts["MBON03"] == (1818, 2)
    assert all(p >= 0 and q >= 0 for p, q in counts.values())


# ---- scoring -------------------------------------------------------------- #
TABLE = SignTable("t", {"A": 1, "B": -1, "Z": 0})


def test_score_is_sign_weighted_sum():
    r = circuit_score([10.0, 4.0, 100.0, 7.0], ["A", "B", "Z", "?"], TABLE)
    assert r.score == pytest.approx(6.0)
    assert (r.n_approach, r.n_avoidance, r.n_zero, r.n_unlisted) == (1, 1, 1, 1)
    assert r.unlisted_labels == ("?",) and r.n_weighted == 2


def test_score_counts_every_instance():
    r = circuit_score([5.0, 5.0, 5.0], ["A", "A", "A"], TABLE)
    assert r.score == 15.0  # sum over instances, not a per-type mean


def test_score_input_validation():
    with pytest.raises(ValueError):
        circuit_score([1.0], ["A", "B"], TABLE)  # length mismatch
    with pytest.raises(ValueError):
        circuit_score([float("nan")], ["A"], TABLE)
    with pytest.raises(ValueError):
        circuit_score([-1.0], ["A"], TABLE)


# ---- decisions ------------------------------------------------------------ #
LABELS = ["A", "B"]


def test_higher_score_wins_when_margin_clears_threshold():
    d = decide([50.0, 10.0], [20.0, 10.0], LABELS, TABLE, margin_threshold=5.0)
    assert d.choice == Choice.YES and d.margin == pytest.approx(30.0)
    assert (d.score_yes, d.score_no) == (40.0, 10.0)
    d = decide([20.0, 10.0], [50.0, 10.0], LABELS, TABLE, margin_threshold=5.0)
    assert d.choice == Choice.NO


def test_avoidance_activity_lowers_score():
    # Same approach activity, but YES framing has more avoidance activity -> NO wins.
    d = decide([30.0, 40.0], [30.0, 5.0], LABELS, TABLE)
    assert d.choice == Choice.NO


def test_ties_abstain_even_with_zero_threshold():
    assert decide([30.0, 5.0], [30.0, 5.0], LABELS, TABLE, 0.0).choice == Choice.ABSTAIN


def test_float_noise_is_a_tie():
    a = 0.1 + 0.2
    assert decide([a, 0.0], [0.3, 0.0], LABELS, TABLE, 0.0).choice == Choice.ABSTAIN


def test_small_margins_abstain_and_boundary_is_exclusive():
    args = ([50.0, 0.0], [45.0, 0.0], LABELS, TABLE)
    assert decide(*args, margin_threshold=10.0).choice == Choice.ABSTAIN  # margin 5 < 10
    assert decide(*args, margin_threshold=5.0).choice == Choice.ABSTAIN  # margin == threshold
    assert decide(*args, margin_threshold=4.9).choice == Choice.YES


def test_all_zero_weight_labels_raise_instead_of_silent_abstain():
    with pytest.raises(ValueError, match="nonzero weight"):
        decide([1.0], [2.0], ["MBON-05"], load_sign_table("strict"))  # wrong label format


def test_negative_threshold_rejected():
    with pytest.raises(ValueError):
        decide([1.0, 1.0], [1.0, 1.0], LABELS, TABLE, margin_threshold=-1.0)


def test_swapping_sign_tables_changes_the_decision():
    labels = ["MBON05", "MBON11", "MBON03", "MBON09"]
    # YES run: only MBON03 fires (group-only avoidance). NO run: only MBON09 fires
    # (group-level approach label, but PAM-dominant in the circuit).
    yes = [0.0, 0.0, 40.0, 0.0]
    no = [0.0, 0.0, 0.0, 40.0]
    strict = decide(yes, no, labels, load_sign_table("strict"), 0.0)
    group = decide(yes, no, labels, load_sign_table("group"), 0.0)
    circuit = decide(yes, no, labels, load_sign_table("circuit_80"), 0.0)
    # STRICT: neither MBON03 nor MBON09 carries weight -> 0 vs 0 -> tie.
    assert strict.choice == Choice.ABSTAIN and strict.table_name == "strict"
    # GROUP: MBON03 avoidance (-40) vs MBON09 approach (+40) -> NO scores higher.
    assert group.choice == Choice.NO and group.table_name == "group"
    assert (group.score_yes, group.score_no) == (-40.0, 40.0)
    # CIRCUIT@80: MBON09 is PAM-dominant -> avoidance-like too (-40 vs -40) -> tie.
    assert circuit.choice == Choice.ABSTAIN and circuit.table_name == "circuit_80"
    assert (circuit.score_yes, circuit.score_no) == (-40.0, -40.0)


def test_strict_table_ignores_group_only_types():
    labels = ["MBON05", "MBON11", "MBON03"]
    d = decide([0.0, 0.0, 99.0], [0.0, 0.0, 0.0], labels, load_sign_table("strict"), 0.0)
    assert d.choice == Choice.ABSTAIN  # MBON03 carries no STRICT weight
    assert d.n_weighted == 2


def test_circuit_variants_can_disagree_at_90():
    labels = ["MBON04", "MBON11"]
    # only MBON04 differs between the framings; it is avoidance-like at 80 but zero at 90
    yes, no = [30.0, 10.0], [0.0, 10.0]
    assert decide(yes, no, labels, load_sign_table("circuit_80"), 0.0).choice == Choice.NO
    assert decide(yes, no, labels, load_sign_table("circuit_90"), 0.0).choice == Choice.ABSTAIN
