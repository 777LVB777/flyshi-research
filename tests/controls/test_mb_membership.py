"""The FROZEN mushroom-body shuffle-scope rule (decided 2026-09-22).

The predicates are tested on fake annotation rows; the real frozen artifact is
checked as data (small JSON), never by re-reading the annotation table and never
by touching the connectivity parquet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flyshi_research.controls.mb_membership import (
    EXPECTED_COUNTS,
    MEMBERSHIP_RULE,
    canonical_json,
    file_sha256,
    membership_payload,
    select_membership,
    sha256_of,
)

REPO = Path(__file__).resolve().parents[2]
FROZEN = REPO / "repro" / "connectome" / "mb_membership_783.json"
SIDECAR = REPO / "repro" / "connectome" / "mb_membership_783.json.sha256"


def row(root_id: int, cell_class: str = "", cell_type: str = "") -> dict:
    return {"root_id": root_id, "cell_class": cell_class, "cell_type": cell_type}


FAKE_ROWS = [
    row(1, "Kenyon_Cell", "KCg-m"),
    row(2, "MBON", "MBON01"),
    row(3, "DAN", "PAM01"),
    row(4, "DAN", "PPL101"),
    row(5, "ALPN", "APL"),          # APL is selected by cell_type, whatever its class
    row(6, "DAN", "PPL201"),        # PPL2 is NOT in the frozen rule
    row(7, "ALPN", "DA1_lPN"),      # projection neuron: outside the scope
    row(8, "MBON", ""),             # unnamed MBON instance is still an MBON
]


def test_rule_selects_exactly_the_five_declared_classes():
    m = select_membership(FAKE_ROWS)
    assert m.by_class == {
        "kenyon_cells": (1,),
        "mbons": (2, 8),
        "pam_dopamine_neurons": (3,),
        "ppl1_dopamine_neurons": (4,),
        "apl_neurons": (5,),
    }
    assert m.root_ids == (1, 2, 3, 4, 5, 8)  # PPL2 and the ALPN are excluded


def test_rule_names_are_frozen_and_documented():
    assert [name for name, _, _ in MEMBERSHIP_RULE] == [
        "kenyon_cells", "mbons", "pam_dopamine_neurons", "ppl1_dopamine_neurons", "apl_neurons"]
    assert set(EXPECTED_COUNTS) == {name for name, _, _ in MEMBERSHIP_RULE}


def test_pam_and_ppl1_need_the_dan_class_not_just_the_name():
    m = select_membership([row(1, "MBON", "PAM01-like"), row(2, "DAN", "PAM01")])
    assert m.by_class["pam_dopamine_neurons"] == (2,)
    assert m.by_class["mbons"] == (1,)


def test_completeness_filter_drops_neurons_the_model_does_not_contain():
    m = select_membership(FAKE_ROWS, eligible_root_ids=[1, 2])
    assert m.root_ids == (1, 2)


def test_missing_or_blank_annotations_are_not_selected():
    m = select_membership([row(1), {"root_id": 2, "cell_class": None, "cell_type": "nan"}])
    assert m.root_ids == ()
    with pytest.raises(ValueError):
        select_membership([{"cell_class": "MBON"}])


def test_a_duplicated_row_is_counted_once():
    m = select_membership([row(1, "Kenyon_Cell"), row(1, "Kenyon_Cell")])
    assert m.by_class["kenyon_cells"] == (1,) and m.root_ids == (1,)


def test_count_mismatches_are_reported_not_silently_accepted():
    m = select_membership(FAKE_ROWS)
    mismatches = m.count_mismatches()
    assert mismatches["kenyon_cells"] == (EXPECTED_COUNTS["kenyon_cells"], 1)
    payload = membership_payload(m, eligible_neuron_count=len(FAKE_ROWS))
    assert payload["count_mismatches"]["mbons"] == {"expected": 96, "observed": 2}
    assert payload["scope"] == "mushroom-body"


def test_payload_serialisation_and_hash_are_stable():
    m = select_membership(FAKE_ROWS)
    a = canonical_json(membership_payload(m, eligible_neuron_count=8))
    b = canonical_json(membership_payload(m, eligible_neuron_count=8))
    assert a == b and sha256_of(a) == sha256_of(b)
    assert json.loads(a)["root_ids"] == [1, 2, 3, 4, 5, 8]


# ---- the real frozen artifact (read as data; no annotation table, no parquet) ---- #
def test_frozen_membership_file_matches_its_recorded_hash():
    assert FROZEN.exists() and SIDECAR.exists()
    assert file_sha256(FROZEN) == SIDECAR.read_text().split()[0]


def test_frozen_membership_counts_match_the_known_counts():
    payload = json.loads(FROZEN.read_text())
    assert payload["counts"] == EXPECTED_COUNTS
    assert payload["count_mismatches"] == {}
    ids = payload["root_ids"]
    assert len(ids) == payload["root_id_count"] == sum(EXPECTED_COUNTS.values())
    assert ids == sorted(set(ids))  # sorted, de-duplicated: the shuffle's eligibility list


def test_frozen_membership_records_its_source_and_the_decision():
    payload = json.loads(FROZEN.read_text())
    assert payload["annotation_source"]["release_tag"] == "v3.1.0"
    assert payload["scope"] == "mushroom-body"
    assert "open-decisions.md" in payload["decision"]


def test_the_recorded_hash_in_the_docs_matches_the_frozen_file():
    """A doc that quotes a stale hash would make the frozen scope unverifiable."""
    digest = file_sha256(FROZEN)
    for doc in ("docs/preregistration.md",
                "docs/design/degree-preserving-connectome-control.md",
                "docs/design/open-decisions.md"):
        assert digest in (REPO / doc).read_text(), doc
