"""Derive v783 mushroom-body ID lists from the official annotation release."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS = ROOT / "third_party" / "flywire_annotations" / "supplemental_files" / "Supplemental_file1_neuron_annotations.tsv"
COMPLETENESS = ROOT / "third_party" / "Drosophila_brain_model" / "Completeness_783.csv"
OUTPUT = ROOT / "repro" / "mushroom_body" / "neuron_ids_783.json"


def records(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, object]]:
    """Return stable, JSON-safe annotation records for selected neurons."""
    return [
        {column: (int(row[column]) if column == "root_id" else str(row[column])) for column in columns}
        for _, row in frame.sort_values("root_id")[columns].iterrows()
    ]


def main() -> None:
    annotations = pd.read_csv(ANNOTATIONS, sep="\t", low_memory=False)
    completeness = pd.read_csv(COMPLETENESS, index_col=0)
    complete_ids = set(completeness.index.astype("int64"))
    annotations = annotations[annotations["root_id"].isin(complete_ids)].copy()

    pns = annotations[
        (annotations["cell_class"] == "ALPN")
        & (annotations["cell_sub_class"] == "uniglomerular")
    ].copy()
    pns["glomerulus"] = pns["cell_type"].str.extract(r"^([^_]+)")[0]
    pn_groups: dict[str, dict[str, list[int]]] = {}
    for (glomerulus, side), group in pns.groupby(["glomerulus", "side"], dropna=True):
        pn_groups.setdefault(str(glomerulus), {})[str(side)] = sorted(group["root_id"].astype(int).tolist())

    kcs = annotations[annotations["cell_class"] == "Kenyon_Cell"]
    mbons = annotations[annotations["cell_class"] == "MBON"]
    pam = annotations[
        (annotations["cell_class"] == "DAN")
        & annotations["cell_type"].fillna("").str.startswith("PAM")
    ]
    ppl1 = annotations[
        (annotations["cell_class"] == "DAN")
        & annotations["cell_type"].fillna("").str.startswith("PPL1")
    ]
    apl = annotations[annotations["cell_type"] == "APL"]

    payload = {
        "schema_version": 1,
        "flywire_version": "783",
        "annotation_source": {
            "repository": "https://github.com/flyconnectome/flywire_annotations",
            "release_tag": "v3.1.0",
            "commit": "8587524c1748ce5ef2080822a2fc890fc03bf597",
            "table": "supplemental_files/Supplemental_file1_neuron_annotations.tsv",
            "license": "unverified: no LICENSE file at the recorded official repository commit",
        },
        "completeness_source": {
            "path": "third_party/Drosophila_brain_model/Completeness_783.csv",
            "eligible_neuron_count": int(len(annotations)),
        },
        "selection_rules": {
            "uniglomerular_antenna_lobe_projection_neurons": {
                "columns": {"cell_class": "ALPN", "cell_sub_class": "uniglomerular"},
                "glomerulus": "prefix of cell_type before the first underscore",
                "side_column": "side",
            },
            "kenyon_cells": {"columns": {"cell_class": "Kenyon_Cell"}},
            "mbons": {"columns": {"cell_class": "MBON"}},
            "pam_dopamine_neurons": {
                "columns": {"cell_class": "DAN", "cell_type_prefix": "PAM"},
            },
            "ppl1_dopamine_neurons": {
                "columns": {"cell_class": "DAN", "cell_type_prefix": "PPL1"},
            },
            "apl_neurons": {"columns": {"cell_type": "APL"}},
        },
        "uniglomerular_antenna_lobe_projection_neurons": {
            "count": int(len(pns)),
            "groups_by_glomerulus_and_side": pn_groups,
            "records": records(pns, ["root_id", "cell_type", "side"]),
        },
        "kenyon_cells": {
            "count": int(len(kcs)),
            "records": records(kcs, ["root_id", "cell_sub_class", "cell_type", "side"]),
        },
        "mbons": {
            "count": int(len(mbons)),
            "records": records(mbons, ["root_id", "cell_type", "side"]),
        },
        "pam_dopamine_neurons": {
            "count": int(len(pam)),
            "records": records(pam, ["root_id", "cell_type", "side"]),
        },
        "ppl1_dopamine_neurons": {
            "count": int(len(ppl1)),
            "records": records(ppl1, ["root_id", "cell_type", "side"]),
        },
        "apl_neurons": {
            "count": int(len(apl)),
            "records": records(apl, ["root_id", "cell_class", "cell_type", "side"]),
        },
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
