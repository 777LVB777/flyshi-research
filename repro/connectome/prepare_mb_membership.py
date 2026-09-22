#!/usr/bin/env python3
"""Freeze the mushroom-body shuffle-scope membership from the pinned annotations.

Reads the FlyWire annotation TSV and Completeness_783.csv only (never the
connectivity parquet, and no simulation), applies the frozen rule in
``flyshi_research.controls.mb_membership``, writes the root-ID file and records
its SHA-256 in a sidecar file.

    .venv-shiu/bin/python repro/connectome/prepare_mb_membership.py           # write
    .venv-shiu/bin/python repro/connectome/prepare_mb_membership.py --check   # verify

Per-class counts are compared with the counts this project has already observed.
A mismatch is REPORTED and makes the command exit non-zero; the rule is never
adjusted to make the numbers agree.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from flyshi_research.controls.mb_membership import (
    ANNOTATION_SOURCE,
    MEMBERSHIP_RULE,
    canonical_json,
    file_sha256,
    membership_payload,
    select_membership,
    sha256_of,
)

ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS = ROOT / "third_party" / "flywire_annotations" / "supplemental_files" / "Supplemental_file1_neuron_annotations.tsv"
COMPLETENESS = ROOT / "third_party" / "Drosophila_brain_model" / "Completeness_783.csv"
OUTPUT = ROOT / "repro" / "connectome" / "mb_membership_783.json"
COLUMNS = ["root_id", "cell_class", "cell_type", "side"]


def build() -> tuple[dict, str]:
    annotations = pd.read_csv(ANNOTATIONS, sep="\t", low_memory=False, usecols=COLUMNS)
    completeness = pd.read_csv(COMPLETENESS, index_col=0)
    eligible = completeness.index.astype("int64").tolist()
    eligible_rows = annotations[annotations["root_id"].isin(set(eligible))]
    membership = select_membership(eligible_rows.to_dict("records"), eligible)
    payload = membership_payload(membership, eligible_neuron_count=int(len(eligible_rows)))
    return payload, canonical_json(payload)


def report(payload: dict) -> None:
    print(f"annotation release: {ANNOTATION_SOURCE['release_tag']} ({ANNOTATION_SOURCE['commit'][:12]})")
    print(f"eligible annotated neurons in the model: {payload['completeness_source']['eligible_neuron_count']:,}")
    for name, _, rule in MEMBERSHIP_RULE:
        observed = payload["counts"][name]
        expected = payload["expected_counts"][name]
        flag = "OK" if observed == expected else f"MISMATCH (expected {expected})"
        print(f"  {name:<24} {observed:>6,}  [{rule}]  {flag}")
    print(f"  {'merged root IDs':<24} {payload['root_id_count']:>6,}  (de-duplicated across classes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="Rebuild and compare with the existing file instead of writing.")
    args = parser.parse_args()

    payload, text = build()
    report(payload)
    digest = sha256_of(text)
    print(f"sha256: {digest}")

    if payload["count_mismatches"]:
        for name, pair in sorted(payload["count_mismatches"].items()):
            print(f"COUNT MISMATCH: {name}: expected {pair['expected']}, observed {pair['observed']}",
                  file=sys.stderr)
        print("Membership NOT written: resolve the mismatch before freezing.", file=sys.stderr)
        return 1

    if args.check:
        if not args.output.exists():
            print(f"missing {args.output}", file=sys.stderr)
            return 1
        existing = file_sha256(args.output)
        if existing != digest:
            print(f"HASH MISMATCH: file {existing} != rebuilt {digest}", file=sys.stderr)
            return 1
        print(f"{args.output.name} matches the rebuilt membership.")
        return 0

    args.output.write_text(text)
    (args.output.parent / (args.output.name + ".sha256")).write_text(f"{digest}  {args.output.name}\n")
    print(f"Wrote {args.output} and {args.output.name}.sha256")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
