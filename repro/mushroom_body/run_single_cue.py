"""Run ONE KC-direct cue set (A or B) at a chosen simulation seed and save its
per-MBON firing rates. Purpose: the noise-floor experiment for MBON separability
(docs/design/mbon-separability.md) — rerun the SAME cue under different --seed
values to measure run-to-run noise (A vs A'), for comparison against the existing
A-vs-B difference (signal).

Reuses check_mb_response.py's KC-direct machinery (select_disjoint_kc_sets,
run_condition, annotation/ID loading); no simulation or rate logic is duplicated.
One invocation = one cue at one seed at one (duration, trials) cell. Restartable:
skips if the output file already exists.

This script is analysis infrastructure; running it DOES execute a Brian2
simulation, so run it yourself in a terminal (see --help), not inside Codex.
"""

from __future__ import annotations

import argparse
import csv
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import check_mb_response as mbr


def parser() -> argparse.ArgumentParser:
    example = (
        "uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_single_cue.py "
        "--cue a --seed 20260317 --duration-ms 1000 --trials 5"
    )
    p = argparse.ArgumentParser(
        description=(
            "Run one KC-direct cue set (A or B) at one seed; save per-MBON rates. "
            "For the MBON-separability noise-floor experiment (see "
            "docs/design/mbon-separability.md)."
        ),
        epilog=(
            f"Example:\n  {example}\n\n"
            "Runs a Brian2 simulation; on macOS use `caffeinate -i`. Vary --seed to "
            "get independent noise realizations of the SAME cue. Keep --kc-set-seed "
            "fixed so the identical Kenyon-cell set is stimulated every time."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--cue", choices=["a", "b"], default="a", help="Which disjoint KC set to stimulate (default: a).")
    p.add_argument("--seed", type=int, required=True, help="Simulation seed (Brian2/NumPy). Vary this to sample run-to-run noise.")
    p.add_argument("--duration-ms", type=float, default=1000.0, help="Trial duration in ms (default: 1000).")
    p.add_argument("--trials", type=int, default=5, help="Trials per run (default: 5).")
    p.add_argument("--pn-rate", type=float, default=150.0, help="KC stimulation rate in Hz (default: 150).")
    p.add_argument("--kc-set-size", type=int, default=100, help="KC set size per cue (default: 100).")
    p.add_argument(
        "--kc-set-seed",
        type=int,
        default=20260316,
        help="Seed selecting the two disjoint KC sets (default: 20260316). Keep fixed across noise runs.",
    )
    return p


def output_path(args: argparse.Namespace) -> Path:
    name = (
        f"mbon_noise_floor_cue_{args.cue}"
        f"_duration_ms_{args.duration_ms:g}_trials_{args.trials}"
        f"_pn_rate_hz_{args.pn_rate:g}"
        f"_kc_size_{args.kc_set_size}_kc_seed_{args.kc_set_seed}"
        f"_seed_{args.seed}.csv"
    )
    return mbr.RESULTS_DIR / name


def main() -> None:
    args = parser().parse_args()
    if args.trials <= 0 or args.duration_ms <= 0 or args.kc_set_size <= 0:
        raise ValueError("trials, duration, and kc-set-size must be positive")

    out_path = output_path(args)
    if out_path.exists():
        print(f"Output already exists, skipping (restartable): {out_path}")
        return

    payload = mbr.read_ids()
    annotations = mbr.load_annotations()
    pn_glomerulus = mbr.pn_glomerulus_map(payload)
    total_brain_neurons = len(pd.read_csv(mbr.UPSTREAM_ROOT / "Completeness_783.csv", index_col=0))

    set_a, set_b = mbr.select_disjoint_kc_sets(
        payload["kenyon_cells"]["records"], args.kc_set_size, args.kc_set_seed
    )
    stim_ids = set_a if args.cue == "a" else set_b
    condition_name = "kc_set_a" if args.cue == "a" else "kc_set_b"
    target_kc_ids = set(stim_ids)

    condition_args = SimpleNamespace(
        seed=args.seed, duration_ms=args.duration_ms, trials=args.trials, pn_rate=args.pn_rate
    )

    with tempfile.TemporaryDirectory(prefix="flyshi-mb-noise-") as temporary_directory:
        scratch_dir = Path(temporary_directory)
        result = mbr.run_condition(
            condition_name, stim_ids, payload, condition_args, scratch_dir,
            annotations, pn_glomerulus, target_kc_ids, total_brain_neurons,
        )

    mbr.RESULTS_DIR.mkdir(exist_ok=True)
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["seed", "duration_ms", "trials", "cue", "root_id", "cell_type", "side", "rate_hz"]
        )
        writer.writeheader()
        for row in result["mbons_nonzero"]:
            writer.writerow({
                "seed": args.seed, "duration_ms": args.duration_ms, "trials": args.trials,
                "cue": args.cue, **row,
            })

    n_nonzero = len(result["mbons_nonzero"])
    runtime = result["runtime_seconds"]
    print(
        f"cue {args.cue} @ seed {args.seed}, {args.duration_ms:g}ms x {args.trials} trials: "
        f"{n_nonzero} nonzero MBONs, runtime {runtime:.1f}s"
    )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
