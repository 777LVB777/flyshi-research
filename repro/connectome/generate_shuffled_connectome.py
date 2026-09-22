#!/usr/bin/env python3
"""Generate a degree-preserving shuffled v783 connectome on a server.

The --dry-run path is simulation-free, does not import pandas, and does not open
the connectivity file.  A real run is intentionally explicit and potentially
large; its memory use and runtime remain unverified.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

from flyshi_research.controls.shuffled_connectome import (
    ConnectivityTable,
    mushroom_body_scope_mask,
    shuffle_connectivity,
    validate_shuffle,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "third_party" / "Drosophila_brain_model" / "Connectivity_783.parquet"
DEFAULT_COMPLETENESS = ROOT / "third_party" / "Drosophila_brain_model" / "Completeness_783.csv"
UNVERIFIED_EDGE_ESTIMATE = 15_000_000
BYTES_PER_EDGE_ESTIMATE = 640
BYTES_PER_NEURON_ESTIMATE = 128
UNVERIFIED_NEURON_ESTIMATE = 138_625


def estimate_peak_bytes(n_edges: int, n_neurons: int = UNVERIFIED_NEURON_ESTIMATE) -> int:
    """Conservative planning estimate, not a measured resource bound."""
    if n_edges < 1 or n_neurons < 1:
        raise ValueError("edge and neuron estimates must be positive")
    return BYTES_PER_EDGE_ESTIMATE * n_edges + BYTES_PER_NEURON_ESTIMATE * n_neurons


def gibibytes(n_bytes: int) -> float:
    return n_bytes / 1024**3


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--scope", required=True, choices=("mushroom-body", "whole-network"),
                   help="Required; deliberately no default. mushroom-body is the preregistered "
                        "primary scope (decided 2026-09-22); whole-network is exploratory only.")
    p.add_argument("--seed", required=True, type=int)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path,
                   help="Required for a real run; must be outside third_party/.")
    p.add_argument("--completeness", type=Path, default=DEFAULT_COMPLETENESS)
    p.add_argument("--mb-root-ids", type=Path,
                   help="JSON list (or {'root_ids': [...]}); required for mushroom-body real runs.")
    p.add_argument("--swaps-per-edge", type=float, default=10.0)
    p.add_argument("--max-attempt-factor", type=float, default=100.0)
    p.add_argument("--allow-self-loops", action=argparse.BooleanOptionalAction, default=None,
                   help="Permit/reject loops; omitted means infer permission from input.")
    p.add_argument("--allow-parallel-edges", action=argparse.BooleanOptionalAction, default=None,
                   help="Permit/reject parallel edges; omitted means infer permission from input.")
    p.add_argument("--estimated-edges", type=int, default=UNVERIFIED_EDGE_ESTIMATE,
                   help="Planning value used only by dry-run (default is UNVERIFIED).")
    p.add_argument("--dry-run", action="store_true")
    return p


def _load_mb_ids(path: Path) -> np.ndarray:
    payload = json.loads(path.read_text())
    values = payload.get("root_ids") if isinstance(payload, dict) else payload
    array = np.asarray(values)
    if array.ndim != 1 or array.size == 0 or not np.issubdtype(array.dtype, np.integer):
        raise ValueError("MB membership must be a non-empty JSON integer list")
    if np.unique(array).size != array.size:
        raise ValueError("MB membership contains duplicate root IDs")
    return array.astype(np.int64)


def _validate_output_path(path: Path, input_path: Path) -> None:
    resolved = path.expanduser().resolve()
    third_party = (ROOT / "third_party").resolve()
    if resolved == input_path.expanduser().resolve():
        raise ValueError("output must not overwrite the input")
    if resolved.is_relative_to(third_party):
        raise ValueError("output must not be written under third_party/")
    manifest = resolved.with_suffix(resolved.suffix + ".manifest.json")
    if resolved.exists() or Path(str(resolved) + ".partial").exists() or manifest.exists():
        raise FileExistsError(f"refusing to overwrite existing artifact: {resolved}")


def _dry_run(args: argparse.Namespace) -> int:
    peak = estimate_peak_bytes(args.estimated_edges)
    eligible = "all rows" if args.scope == "whole-network" else "unknown until MB IDs are loaded"
    print("Degree-preserving connectome shuffle: DRY RUN")
    print(f"scope: {args.scope} (explicit; no scope was selected by the implementation)")
    print(f"seed: {args.seed}")
    print(f"planning rows: {args.estimated_edges:,} (UNVERIFIED; input file was not opened)")
    print(f"eligible rows: {eligible}")
    print(f"requested swaps: {args.swaps_per_edge:g} per eligible row")
    print(f"estimated peak memory: {gibibytes(peak):.1f} GiB (UNVERIFIED)")
    print(f"recommended RAM with 2x headroom: {gibibytes(2 * peak):.1f} GiB (UNVERIFIED)")
    print("No parquet loaded, no output written, and no simulation run.")
    return 0


def _index_to_root_ids(completeness_path: Path, pd) -> np.ndarray:
    completeness = pd.read_csv(completeness_path, index_col=0)
    ids = completeness.index.to_numpy(dtype=np.int64, copy=True)
    if np.unique(ids).size != ids.size:
        raise ValueError("Completeness index contains duplicate root IDs")
    return ids


def _validate_endpoint_ids(frame, index_to_id: np.ndarray) -> None:
    pre = frame["Presynaptic_Index"].to_numpy(dtype=np.int64, copy=False)
    post = frame["Postsynaptic_Index"].to_numpy(dtype=np.int64, copy=False)
    if np.any(pre < 0) or np.any(post < 0) or np.any(pre >= index_to_id.size) or np.any(post >= index_to_id.size):
        raise ValueError("connectivity contains a neuron index outside Completeness_783.csv")
    if not np.array_equal(index_to_id[pre], frame["Presynaptic_ID"].to_numpy(dtype=np.int64)):
        raise ValueError("Presynaptic_Index and Presynaptic_ID are inconsistent")
    if not np.array_equal(index_to_id[post], frame["Postsynaptic_ID"].to_numpy(dtype=np.int64)):
        raise ValueError("Postsynaptic_Index and Postsynaptic_ID are inconsistent")


def _real_run(args: argparse.Namespace) -> int:
    if args.output is None:
        raise ValueError("--output is required unless --dry-run is used")
    if args.scope == "mushroom-body" and args.mb_root_ids is None:
        raise ValueError("--mb-root-ids is required for mushroom-body scope")
    if args.swaps_per_edge <= 0 or args.max_attempt_factor < 1:
        raise ValueError("swap rate must be positive and attempt factor must be at least one")
    _validate_output_path(args.output, args.input)

    # Heavy dependency and data reads occur only after all dry-run exits.
    import pandas as pd

    required = {
        "Presynaptic_Index", "Postsynaptic_Index", "Presynaptic_ID", "Postsynaptic_ID",
        "Connectivity", "Excitatory x Connectivity",
    }
    frame = pd.read_parquet(args.input)
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"connectivity file is missing columns: {sorted(missing)}")
    index_to_id = _index_to_root_ids(args.completeness, pd)
    _validate_endpoint_ids(frame, index_to_id)

    signed_weight = frame["Excitatory x Connectivity"].to_numpy(copy=False)
    sign = np.sign(signed_weight).astype(np.int8)
    if np.any(sign == 0):
        raise ValueError("zero signed weights have no defined sign")
    table = ConnectivityTable(
        frame["Presynaptic_Index"].to_numpy(dtype=np.int64, copy=True),
        frame["Postsynaptic_Index"].to_numpy(dtype=np.int64, copy=True),
        frame["Connectivity"].to_numpy(copy=True),
        sign,
    )
    if args.scope == "whole-network":
        eligible = None
    else:
        mb_root_ids = _load_mb_ids(args.mb_root_ids)
        id_mask = np.isin(index_to_id, mb_root_ids)
        missing_ids = mb_root_ids[~np.isin(mb_root_ids, index_to_id)]
        if missing_ids.size:
            raise ValueError(f"{missing_ids.size} MB root IDs are absent from Completeness_783.csv")
        eligible = mushroom_body_scope_mask(table, np.flatnonzero(id_mask))
        if np.count_nonzero(eligible) < 2:
            raise ValueError("MB membership selects fewer than two internal edges")

    eligible_count = table.n_edges if eligible is None else int(np.count_nonzero(eligible))
    n_swaps = int(round(args.swaps_per_edge * eligible_count))
    max_attempts = int(round(args.max_attempt_factor * n_swaps))
    result = shuffle_connectivity(
        table,
        seed=args.seed,
        n_swaps=n_swaps,
        max_attempts=max_attempts,
        eligible_mask=eligible,
        allow_self_loops=args.allow_self_loops,
        allow_parallel_edges=args.allow_parallel_edges,
    )
    validate_shuffle(table, result, eligible_mask=eligible, maximum_overlap=0.50)

    shuffled = result.table
    frame["Presynaptic_Index"] = shuffled.pre
    frame["Postsynaptic_Index"] = shuffled.post
    frame["Presynaptic_ID"] = index_to_id[shuffled.pre]
    frame["Postsynaptic_ID"] = index_to_id[shuffled.post]
    # Connectivity and Excitatory x Connectivity remain on their source rows.
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(str(output) + ".partial")
    frame.to_parquet(partial, index=False)
    os.replace(partial, output)

    manifest = {
        "method": "directed_double_edge_swap",
        "input": str(args.input.expanduser().resolve()),
        "output": str(output),
        "scope": args.scope,
        "mb_root_ids": None if args.mb_root_ids is None else str(args.mb_root_ids.resolve()),
        "seed": args.seed,
        "edges": table.n_edges,
        "eligible_edges": result.eligible_edges,
        "requested_swaps": result.requested_swaps,
        "accepted_swaps": result.accepted_swaps,
        "attempts": result.attempts,
        "original_edge_overlap_fraction": result.overlap_fraction,
        "allow_self_loops": result.allow_self_loops,
        "allow_parallel_edges": result.allow_parallel_edges,
        "sign_policy": "sign and synapse count stay with source edge row",
        "status": "UNVERIFIED by simulation",
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.dry_run:
        return _dry_run(args)
    return _real_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
