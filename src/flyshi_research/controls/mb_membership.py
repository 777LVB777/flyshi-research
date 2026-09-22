"""FROZEN annotation rule for the mushroom-body shuffle scope.

Decided 2026-09-22 (docs/design/open-decisions.md, item 1): the degree-preserving
shuffle's PRIMARY scope is mushroom-body-only, and its membership is

    Kenyon cells + MBONs + PAM + PPL1 + APL

as annotated in the pinned FlyWire annotation release, restricted to the neurons
the model actually contains (``Completeness_783.csv``). ``MEMBERSHIP_RULE`` below
is that rule in code. It is FROZEN: a class may be added or a predicate changed
only by editing this module, re-generating the root-ID file
(``repro/connectome/prepare_mb_membership.py``) and recording the new file hash
BEFORE any shuffle is generated - never after seeing a result.

This module is plain Python: it takes annotation rows as mappings, so the rule
can be tested on fake rows without reading the real table. The script that reads
the real TSV lives in ``repro/connectome/``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Sequence, Tuple

# Pinned annotation release (same one prepare_neuron_ids.py recorded).
ANNOTATION_SOURCE = {
    "repository": "https://github.com/flyconnectome/flywire_annotations",
    "release_tag": "v3.1.0",
    "commit": "8587524c1748ce5ef2080822a2fc890fc03bf597",
    "table": "supplemental_files/Supplemental_file1_neuron_annotations.tsv",
    "license": "unverified: no LICENSE file at the recorded official repository commit",
}

COMPLETENESS_SOURCE = "third_party/Drosophila_brain_model/Completeness_783.csv"

# Counts this project has already observed for these classes in v783. They are a
# pre-stated CHECK, not a target: a mismatch is reported, never fixed by adjusting
# the rule (docs/design/degree-preserving-connectome-control.md).
EXPECTED_COUNTS: Dict[str, int] = {
    "kenyon_cells": 5177,
    "mbons": 96,
    "pam_dopamine_neurons": 307,
    "ppl1_dopamine_neurons": 16,
    "apl_neurons": 2,
}


def _text(row: Mapping[str, object], column: str) -> str:
    value = row.get(column)
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def _is_kenyon_cell(row: Mapping[str, object]) -> bool:
    return _text(row, "cell_class") == "Kenyon_Cell"


def _is_mbon(row: Mapping[str, object]) -> bool:
    return _text(row, "cell_class") == "MBON"


def _is_pam(row: Mapping[str, object]) -> bool:
    return _text(row, "cell_class") == "DAN" and _text(row, "cell_type").startswith("PAM")


def _is_ppl1(row: Mapping[str, object]) -> bool:
    return _text(row, "cell_class") == "DAN" and _text(row, "cell_type").startswith("PPL1")


def _is_apl(row: Mapping[str, object]) -> bool:
    return _text(row, "cell_type") == "APL"


#: class name -> (predicate, human-readable rule). Order fixes the report order.
MEMBERSHIP_RULE: Tuple[Tuple[str, Callable[[Mapping[str, object]], bool], str], ...] = (
    ("kenyon_cells", _is_kenyon_cell, "cell_class == 'Kenyon_Cell'"),
    ("mbons", _is_mbon, "cell_class == 'MBON'"),
    ("pam_dopamine_neurons", _is_pam, "cell_class == 'DAN' and cell_type starts with 'PAM'"),
    ("ppl1_dopamine_neurons", _is_ppl1, "cell_class == 'DAN' and cell_type starts with 'PPL1'"),
    ("apl_neurons", _is_apl, "cell_type == 'APL'"),
)

RULE_DESCRIPTION = {name: text for name, _, text in MEMBERSHIP_RULE}

RULE_NOTES = (
    "Eligible rows are restricted to root IDs present in Completeness_783.csv, i.e. "
    "the neurons the model contains. A neuron matching more than one class is counted "
    "once in the root-ID list and once per class it matches in the per-class counts. "
    "Edges are shuffled only when BOTH endpoints are in the root-ID list; boundary and "
    "non-MB edges are left untouched."
)


@dataclass(frozen=True)
class Membership:
    """Per-class root IDs plus the merged, sorted, de-duplicated list."""

    by_class: Dict[str, Tuple[int, ...]]
    root_ids: Tuple[int, ...]

    @property
    def counts(self) -> Dict[str, int]:
        return {name: len(ids) for name, ids in self.by_class.items()}

    def count_mismatches(self) -> Dict[str, Tuple[int, int]]:
        """class -> (expected, observed) for every class that does not match."""
        return {
            name: (expected, len(self.by_class.get(name, ())))
            for name, expected in EXPECTED_COUNTS.items()
            if len(self.by_class.get(name, ())) != expected
        }


def select_membership(
    rows: Iterable[Mapping[str, object]],
    eligible_root_ids: Sequence[int] | None = None,
) -> Membership:
    """Apply the frozen rule to annotation rows.

    ``rows`` need only carry ``root_id``, ``cell_class`` and ``cell_type``.
    ``eligible_root_ids`` (the model's neuron set) filters the rows; passing None
    skips that filter and is only for testing the predicates themselves.
    """
    eligible = None if eligible_root_ids is None else set(int(i) for i in eligible_root_ids)
    by_class: Dict[str, List[int]] = {name: [] for name, _, _ in MEMBERSHIP_RULE}
    seen: Dict[str, set] = {name: set() for name, _, _ in MEMBERSHIP_RULE}
    for row in rows:
        if "root_id" not in row:
            raise ValueError("annotation row without a root_id")
        root_id = int(row["root_id"])
        if eligible is not None and root_id not in eligible:
            continue
        for name, predicate, _ in MEMBERSHIP_RULE:
            if predicate(row) and root_id not in seen[name]:
                seen[name].add(root_id)
                by_class[name].append(root_id)
    merged = sorted({i for ids in by_class.values() for i in ids})
    return Membership(
        by_class={name: tuple(sorted(ids)) for name, ids in by_class.items()},
        root_ids=tuple(merged),
    )


def membership_payload(membership: Membership, *, eligible_neuron_count: int) -> dict:
    """The frozen root-ID file's contents (consumed by --mb-root-ids)."""
    return {
        "schema_version": 1,
        "flywire_version": "783",
        "scope": "mushroom-body",
        "decision": "docs/design/open-decisions.md item 1, resolved 2026-09-22",
        "annotation_source": dict(ANNOTATION_SOURCE),
        "completeness_source": {
            "path": COMPLETENESS_SOURCE,
            "eligible_neuron_count": int(eligible_neuron_count),
        },
        "rule": dict(RULE_DESCRIPTION),
        "rule_notes": RULE_NOTES,
        "expected_counts": dict(EXPECTED_COUNTS),
        "counts": membership.counts,
        "count_mismatches": {
            name: {"expected": exp, "observed": obs}
            for name, (exp, obs) in membership.count_mismatches().items()
        },
        "root_id_count": len(membership.root_ids),
        "root_ids_by_class": {name: list(ids) for name, ids in membership.by_class.items()},
        "root_ids": list(membership.root_ids),
    }


def canonical_json(payload: Mapping) -> str:
    """Byte-stable serialisation: the hash is taken over exactly this text."""
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def file_sha256(path: str | Path) -> str:
    return sha256_of(Path(path).read_text())
