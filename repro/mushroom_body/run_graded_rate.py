"""Graded-rate encoding test: does the MBON readout track the KC firing rate?

Pre-stated design and acceptance criterion: docs/design/graded-encoding.md
(written BEFORE any run). Verdict logic: flyshi_research.learning.graded_check.

One KC pool (set A: --kc-set-size 100, --kc-set-seed 20260316) is stimulated at
30, 60, 90, 120 and 150 Hz for 1000 ms x 5 trials at ONE fixed seed. For each rate
the per-MBON rates are saved; then the CIRCUIT score (per-type mean, 80% table) and
the Euclidean distance between the 30 Hz and 150 Hz MBON vectors are checked
against the pre-stated three-outcome rule (ACCEPTED / USABLE RANGE / FAIL; see the
doc, which records that the rule was revised twice before any run).

Uses the EXISTING upstream path (check_mb_response.run_condition, exactly as
run_single_cue.py does), NOT fast_runner: the noise floor d_AA = 5.10 Hz was
measured on that path, and the fast path's equivalence run has not been done.

Restartable: a rate whose output CSV already exists is skipped; the analysis is
recomputed every time (cheap) and needs no simulation (--analyze-only).

RUNNING THIS EXECUTES BRIAN2 SIMULATIONS (5 runs, roughly 30 s each plus start-up).
Run it yourself in a terminal; on macOS use `caffeinate -i`.
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from flyshi_research.learning import graded_check as gc

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
IDS_PATH = HERE / "neuron_ids_783.json"
# Existing-path cue-A run at seed 20260316, 1000 ms x 5 trials (used only for a diagnostic).
CALIB = RESULTS_DIR / "speed_calibration_mbon_rates_kc_size_100_kc_seed_20260316_pn_rate_hz_150_seed_20260316.csv"
FIELDNAMES = ["seed", "duration_ms", "trials", "rate_hz_stim", "root_id", "cell_type", "side", "rate_hz"]


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_graded_rate.py"
    )
    p = argparse.ArgumentParser(
        description="Graded-rate encoding test (see docs/design/graded-encoding.md).",
        epilog=(
            f"Exact pre-stated run (no arguments needed; defaults ARE the pre-stated settings):\n"
            f"  {command}\n\n"
            "Analysis only, no simulation (needs the five result CSVs):\n"
            "  .venv-shiu/bin/python repro/mushroom_body/run_graded_rate.py --analyze-only\n\n"
            "Overriding any setting below (e.g. a short smoke run) is allowed but the verdict is then "
            "labelled NOT THE PRE-STATED TEST."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--analyze-only", action="store_true", help="Skip simulation; analyse existing CSVs.")
    p.add_argument("--seed", type=int, default=gc.PRESTATED_SEED, help="Simulation seed, same for all rates.")
    p.add_argument("--duration-ms", type=float, default=gc.PRESTATED_DURATION_MS)
    p.add_argument("--trials", type=int, default=gc.PRESTATED_TRIALS)
    p.add_argument("--kc-set-size", type=int, default=gc.PRESTATED_KC_SET_SIZE)
    p.add_argument("--kc-set-seed", type=int, default=gc.PRESTATED_KC_SET_SEED)
    return p


def output_path(rate: float, args: argparse.Namespace, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / (
        f"graded_rate_cue_a_stim_hz_{rate:g}"
        f"_duration_ms_{args.duration_ms:g}_trials_{args.trials}"
        f"_kc_size_{args.kc_set_size}_kc_seed_{args.kc_set_seed}"
        f"_seed_{args.seed}.csv"
    )


def summary_stem(args: argparse.Namespace) -> str:
    return (
        f"graded_rate_cue_a_duration_ms_{args.duration_ms:g}_trials_{args.trials}"
        f"_kc_size_{args.kc_set_size}_kc_seed_{args.kc_set_seed}_seed_{args.seed}"
    )


def is_prestated(args: argparse.Namespace) -> bool:
    return (
        args.seed == gc.PRESTATED_SEED
        and args.duration_ms == gc.PRESTATED_DURATION_MS
        and args.trials == gc.PRESTATED_TRIALS
        and args.kc_set_size == gc.PRESTATED_KC_SET_SIZE
        and args.kc_set_seed == gc.PRESTATED_KC_SET_SEED
    )


# --------------------------------------------------------------------------- #
# simulation (Brian2; lazy imports so --analyze-only and the tests never load it)
# --------------------------------------------------------------------------- #
def simulate_missing(args: argparse.Namespace, log: Callable[[str], None] = print) -> None:
    todo = [r for r in gc.PRESTATED_RATES_HZ if not output_path(r, args).exists()]
    for r in gc.PRESTATED_RATES_HZ:
        if r not in todo:
            log(f"Output already exists, skipping (restartable): {output_path(r, args).name}")
    if not todo:
        return

    import check_mb_response as mbr  # noqa: E402  (imports Brian2 and the upstream model)

    payload = mbr.read_ids()
    annotations = mbr.load_annotations()
    pn_glomerulus = mbr.pn_glomerulus_map(payload)
    total_brain_neurons = len(pd.read_csv(mbr.UPSTREAM_ROOT / "Completeness_783.csv", index_col=0))
    set_a, _set_b = mbr.select_disjoint_kc_sets(
        payload["kenyon_cells"]["records"], args.kc_set_size, args.kc_set_seed
    )
    target_kc_ids = set(set_a)

    RESULTS_DIR.mkdir(exist_ok=True)
    for rate in todo:
        condition_args = SimpleNamespace(
            seed=args.seed, duration_ms=args.duration_ms, trials=args.trials, pn_rate=rate
        )
        with tempfile.TemporaryDirectory(prefix="flyshi-mb-graded-") as tmp:
            result = mbr.run_condition(
                "kc_set_a", set_a, payload, condition_args, Path(tmp),
                annotations, pn_glomerulus, target_kc_ids, total_brain_neurons,
            )
        out = output_path(rate, args)
        tmp_out = out.with_suffix(".csv.partial")  # write-then-rename: a killed run leaves no half file
        with tmp_out.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in result["mbons_nonzero"]:
                writer.writerow({
                    "seed": args.seed, "duration_ms": args.duration_ms, "trials": args.trials,
                    "rate_hz_stim": rate, "root_id": row["root_id"], "cell_type": row["cell_type"],
                    "side": row["side"], "rate_hz": row["rate_hz"],
                })
        tmp_out.replace(out)
        log(f"{rate:g} Hz: {len(result['mbons_nonzero'])} nonzero MBONs, "
            f"runtime {result['runtime_seconds']:.1f}s -> {out.name}")


# --------------------------------------------------------------------------- #
# analysis (no simulation)
# --------------------------------------------------------------------------- #
def load_vector(path: Path, mbon_records: List[dict]) -> np.ndarray:
    """Per-MBON rate vector over ALL MBON instances (both hemispheres); MBONs absent
    from the CSV did not fire (rate exactly 0) and are zero-filled."""
    df = pd.read_csv(path)
    by_id: Dict[int, float] = dict(zip(df.root_id.astype(int), df.rate_hz.astype(float)))
    known = {int(r["root_id"]) for r in mbon_records}
    stray = set(by_id) - known
    if stray:
        raise ValueError(f"{path.name}: {len(stray)} root IDs are not MBONs in {IDS_PATH.name}")
    return np.array([by_id.get(int(r["root_id"]), 0.0) for r in mbon_records])


def existing_cue_a_vector(mbon_records: List[dict], calib: Path = CALIB) -> Optional[np.ndarray]:
    if not calib.exists():
        return None
    df = pd.read_csv(calib)
    sub = df[(df.duration_ms == gc.PRESTATED_DURATION_MS) & (df.trials == gc.PRESTATED_TRIALS)
             & (df.condition == "kc_set_a")]
    if sub.empty:
        return None
    by_id = dict(zip(sub.root_id.astype(int), sub.rate_hz.astype(float)))
    return np.array([by_id.get(int(r["root_id"]), 0.0) for r in mbon_records])


def analyze(
    args: argparse.Namespace,
    log: Callable[[str], None] = print,
    results_dir: Path = RESULTS_DIR,
    ids_path: Path = IDS_PATH,
    calib: Path = CALIB,
    write: bool = True,
) -> Optional[gc.GradedResult]:
    missing = [r for r in gc.PRESTATED_RATES_HZ if not output_path(r, args, results_dir).exists()]
    if missing:
        log(f"Cannot analyse yet: missing results for {[f'{r:g}' for r in missing]} Hz "
            "(run without --analyze-only to simulate them).")
        return None

    mbons = json.loads(ids_path.read_text())["mbons"]["records"]
    labels = [r["cell_type"] for r in mbons]
    vectors = {r: load_vector(output_path(r, args, results_dir), mbons) for r in gc.PRESTATED_RATES_HZ}
    result = gc.evaluate(vectors, labels)

    prestated = is_prestated(args)
    log("")
    log("=== Graded-rate encoding test ===")
    if not prestated:
        log("!!! NOT THE PRE-STATED TEST: settings differ from docs/design/graded-encoding.md; "
            "this verdict is exploratory only. !!!")
    for line in result.summary_lines():
        log(line)

    repro = None
    ref = existing_cue_a_vector(mbons, calib)
    if ref is not None and prestated:
        repro = gc.euclidean(vectors[150.0], ref)
        log(f"diagnostic: 150 Hz run vs existing cue-A run (same seed/path): {repro:.2f} Hz "
            f"(same-cue noise floor {gc.D_AA_NOISE_FLOOR_HZ} Hz; a much larger value would point "
            "to a setup difference, not to the encoding)")

    if write:
        stem = summary_stem(args)
        with (results_dir / f"{stem}_summary.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["stim_rate_hz", "circuit_score", "n_nonzero_mbons", "dist_from_30hz"])
            for row in zip(result.rates_hz, result.scores, result.n_nonzero_mbons,
                           result.distances_from_lowest_hz):
                w.writerow(row)
        rng = result.validated_range_hz
        verdict = {
            "prestated_test": prestated,
            "verdict": result.verdict.value,
            "accepted": result.accepted,
            # rates the encoder's bounds may use: full range / restricted sub-range / null on FAIL
            "validated_range_hz": list(rng) if rng else None,
            "validated_direction": result.validated_direction,
            "tied_longest_subranges_hz": [list(t) for t in result.tied_longest_subranges_hz],
            "fail_reasons": list(result.fail_reasons),
            "monotonic_all_five_rates": result.monotonic,
            "direction": result.direction,
            "distance_30_150_hz": result.distance_lo_hi_hz,
            "distance_threshold_hz": result.distance_threshold_hz,
            "chosen_subrange_hz": list(result.chosen_subrange_hz) if result.chosen_subrange_hz else None,
            "chosen_subrange_distance_hz": result.chosen_subrange_distance_hz,
            "chosen_subrange_distance_ok": result.chosen_subrange_distance_ok,
            "scores": dict(zip(map(str, result.rates_hz), result.scores)),
            "seed": args.seed,
            "repro_diagnostic_hz": repro,
        }
        (results_dir / f"{stem}_verdict.json").write_text(json.dumps(verdict, indent=2))
        log(f"Wrote {stem}_summary.csv and {stem}_verdict.json in {results_dir}")
    return result


def main() -> None:
    args = parser().parse_args()
    if args.trials <= 0 or args.duration_ms <= 0 or args.kc_set_size <= 0:
        raise ValueError("trials, duration-ms and kc-set-size must be positive")
    if not args.analyze_only:
        simulate_missing(args)
    analyze(args)


if __name__ == "__main__":
    main()
