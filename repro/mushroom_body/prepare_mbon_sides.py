#!/usr/bin/env python3
"""Freeze the left/right side label of every modelled MBON from the annotations.

Reads the pinned FlyWire annotation TSV and Completeness_783.csv only (no
connectivity parquet, no simulation) and writes
``src/flyshi_research/learning/data/mbon_sides_783.json``, which
``flyshi_research.learning.mbon_sides`` loads. The left-only readout
(a preregistered sensitivity check, decided 2026-09-22) is computed from saved
per-MBON rates using this table.

    .venv-shiu/bin/python repro/mushroom_body/prepare_mbon_sides.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from flyshi_research.controls.mb_membership import (
    ANNOTATION_SOURCE,
    COMPLETENESS_SOURCE,
    EXPECTED_COUNTS,
    canonical_json,
    file_sha256,
    sha256_of,
)

ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS = ROOT / "third_party" / "flywire_annotations" / "supplemental_files" / "Supplemental_file1_neuron_annotations.tsv"
COMPLETENESS = ROOT / "third_party" / "Drosophila_brain_model" / "Completeness_783.csv"
OUTPUT = ROOT / "src" / "flyshi_research" / "learning" / "data" / "mbon_sides_783.json"


def build() -> tuple[dict, str]:
    annotations = pd.read_csv(ANNOTATIONS, sep="\t", low_memory=False,
                              usecols=["root_id", "cell_class", "cell_type", "side"])
    completeness = pd.read_csv(COMPLETENESS, index_col=0)
    eligible = set(completeness.index.astype("int64").tolist())
    mbons = annotations[(annotations["cell_class"] == "MBON")
                        & (annotations["root_id"].isin(eligible))].sort_values("root_id")
    records = [
        {"root_id": int(row.root_id), "cell_type": str(row.cell_type), "side": str(row.side)}
        for row in mbons.itertuples()
    ]
    counts: dict[str, int] = {}
    for record in records:
        counts[record["side"]] = counts.get(record["side"], 0) + 1
    payload = {
        "schema_version": 1,
        "flywire_version": "783",
        "decision": "docs/design/open-decisions.md item 2, resolved 2026-09-22",
        "description": (
            "Frozen side label per modelled MBON instance. The PRIMARY readout uses all "
            "instances in both hemispheres; the left-only readout is a preregistered "
            "sensitivity check and is recomputed from saved per-MBON rates."
        ),
        "annotation_source": dict(ANNOTATION_SOURCE),
        "completeness_source": {"path": COMPLETENESS_SOURCE},
        "selection_rule": "cell_class == 'MBON', restricted to Completeness_783.csv; side column copied verbatim",
        "expected_mbon_count": EXPECTED_COUNTS["mbons"],
        "count": len(records),
        "counts_by_side": dict(sorted(counts.items())),
        "records": records,
    }
    return payload, canonical_json(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload, text = build()
    digest = sha256_of(text)
    print(f"MBON instances: {payload['count']} (expected {payload['expected_mbon_count']})")
    print(f"by side: {payload['counts_by_side']}")
    print(f"sha256: {digest}")
    if payload["count"] != payload["expected_mbon_count"]:
        print("COUNT MISMATCH: not written; report it rather than adjusting the rule.", file=sys.stderr)
        return 1

    if args.check:
        if not args.output.exists():
            print(f"missing {args.output}", file=sys.stderr)
            return 1
        existing = file_sha256(args.output)
        if existing != digest:
            print(f"HASH MISMATCH: file {existing} != rebuilt {digest}", file=sys.stderr)
            return 1
        print(f"{args.output.name} matches the rebuilt table.")
        return 0

    args.output.write_text(text)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
