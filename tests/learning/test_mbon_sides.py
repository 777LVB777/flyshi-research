"""Frozen MBON side labels and the left-only readout (sensitivity check, 2026-09-22)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning.mbon_sides import (  # noqa: E402
    LEFT,
    RIGHT,
    load_mbon_sides,
    one_side_score,
    restrict_to_side,
    side_mask,
)
from flyshi_research.learning.readout import circuit_score, load_sign_table  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MEMBERSHIP = REPO / "repro" / "connectome" / "mb_membership_783.json"

FAKE_SIDES = {1: LEFT, 2: RIGHT, 3: LEFT, 4: RIGHT}
FAKE_IDS = [1, 2, 3, 4]
FAKE_LABELS = ["MBON11", "MBON11", "MBON05", "MBON05"]  # approach, approach, avoid, avoid
FAKE_RATES = [10.0, 30.0, 4.0, 8.0]


def test_side_mask_picks_one_hemisphere_in_input_order():
    assert side_mask(FAKE_IDS, LEFT, FAKE_SIDES).tolist() == [True, False, True, False]
    assert side_mask(FAKE_IDS, RIGHT, FAKE_SIDES).tolist() == [False, True, False, True]


def test_an_unknown_mbon_is_an_error_not_a_silent_exclusion():
    with pytest.raises(KeyError):
        side_mask([1, 99], LEFT, FAKE_SIDES)


def test_restrict_keeps_rates_and_labels_aligned():
    rates, labels = restrict_to_side(FAKE_RATES, FAKE_LABELS, FAKE_IDS, LEFT, FAKE_SIDES)
    assert rates.tolist() == [10.0, 4.0] and labels == ["MBON11", "MBON05"]
    with pytest.raises(ValueError):
        restrict_to_side(FAKE_RATES[:3], FAKE_LABELS, FAKE_IDS, LEFT, FAKE_SIDES)


def test_left_only_score_equals_scoring_the_left_instances_alone():
    table = load_sign_table("circuit_80")
    left = one_side_score(FAKE_RATES, FAKE_LABELS, FAKE_IDS, table, LEFT, sides=FAKE_SIDES)
    assert left.score == pytest.approx(circuit_score([10.0, 4.0], ["MBON11", "MBON05"], table).score)
    assert left.n_instances == 2


def test_left_only_differs_from_the_bilateral_primary_when_the_sides_differ():
    """Silent or differently-driven contralateral instances move the per-type mean,
    which is exactly why the hemisphere choice needed a decision."""
    table = load_sign_table("circuit_80")
    both = circuit_score(FAKE_RATES, FAKE_LABELS, table).score
    left = one_side_score(FAKE_RATES, FAKE_LABELS, FAKE_IDS, table, LEFT, sides=FAKE_SIDES).score
    assert left != pytest.approx(both)


# ---- the frozen table (read as data; no annotation TSV, no simulation) ---- #
def test_frozen_side_table_has_every_modelled_mbon_split_by_hemisphere():
    sides = load_mbon_sides()
    assert len(sides) == 96
    counts = {side: sum(1 for s in sides.values() if s == side) for side in (LEFT, RIGHT)}
    assert counts == {LEFT: 48, RIGHT: 48}


def test_frozen_side_table_covers_exactly_the_frozen_membership_mbons():
    membership = json.loads(MEMBERSHIP.read_text())["root_ids_by_class"]["mbons"]
    assert sorted(load_mbon_sides()) == sorted(membership)


def test_side_mask_over_the_real_ids_selects_the_left_half():
    ids = sorted(load_mbon_sides())
    assert int(side_mask(ids, LEFT).sum()) == 48
