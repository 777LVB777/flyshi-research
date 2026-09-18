"""Calibrate the cheapest --stim-mode kc duration/trial settings that still
separate two disjoint KC sets at the MBON readout.

Reuses check_mb_response.py's existing KC-direct machinery (select_disjoint_kc_sets,
run_condition, jaccard, annotation/ID loading) rather than duplicating any
simulation or rate-analysis logic. See docs/design/speed-calibration.md for the
pre-stated grid, separation-score definition, and acceptance rule.
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

import check_mb_response as mbr


DURATIONS_MS = [1000.0, 500.0, 200.0, 100.0]
TRIALS_GRID = [5, 2, 1]
BASELINE_TRIALS = max(TRIALS_GRID)  # baseline is run once per duration, at the
# largest trial count in the grid, then reused as the reference for every
# trial-count cell at that duration (per task: "baseline once per duration,
# not per cell").

# Empirical per-run costs, all measured at duration_ms=1000, trials=5 (so
# stimulus_seconds == trials == 5 for every one of these 15 logged runs --
# duration was never varied historically, so these numbers cannot by
# themselves distinguish "cost scales with stimulus-seconds" from "cost
# scales with trial count regardless of duration"; that is exactly what this
# grid will determine). Source: repro/mushroom_body/run_log_*.txt, "Elapsed
# time" lines, 2026-09-16/17 runs (dan_kc_off, kckc_off, pn50, diagnostics,
# kc_direct):
#   elapsed_s = [19,23,23, 20,22,22, 18,65,52, 16,27,25, 25,34,184]
# Two of these (pn50's 65s/52s and kc_direct's 184s) are documented as
# unexplained/likely host-load anomalies in docs/reproduction/mushroom_body_check.md
# ("Timing anomaly: kc_set_b runtime (unexplained)") rather than attributable
# to any model parameter swept here.
EMPIRICAL_MEDIAN_SECONDS_PER_STIMULUS_SECOND = 4.6  # median(elapsed)/5, all 15 runs
EMPIRICAL_MEAN_SECONDS_PER_STIMULUS_SECOND = 7.67  # mean(elapsed)/5, all 15 runs (outliers included)
EMPIRICAL_CLEAN_MEDIAN_SECONDS_PER_TRIAL = 4.5  # median/5 over the 12 runs excluding the 3 documented anomalies
EMPIRICAL_MEAN_SECONDS_PER_TRIAL_WITH_OUTLIERS = 7.67  # numerically equal to the stim-second mean at duration=1000ms

ACCEPTANCE_MIN_SEPARATION_RATIO = 0.9
ACCEPTANCE_MAX_NONSTIM_KC_FRACTION = 0.10
REFERENCE_DURATION_MS = 1000.0
REFERENCE_TRIALS = 5
RUNTIME_WARNING_THRESHOLD_SECONDS = 45 * 60


def parser() -> argparse.ArgumentParser:
    command = (
        "uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/calibrate_speed.py"
    )
    argument_parser = argparse.ArgumentParser(
        description=(
            "Sweep --stim-mode kc duration/trial settings (see "
            "docs/design/speed-calibration.md for the pre-stated grid and "
            "acceptance rule) to find the cheapest configuration that still "
            "separates two disjoint 100-KC sets at the MBON readout."
        ),
        epilog=(
            f"Exact run command:\n  {command}\n\n"
            "This runs many short Brian2 simulations serially and can take "
            "several minutes. On macOS, prefix with `caffeinate -i` so the "
            "machine does not sleep mid-run:\n"
            f"  caffeinate -i {command}\n\n"
            "Use --dry-run first to see the planned grid and runtime estimate "
            "without simulating anything."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    argument_parser.add_argument("--pn-rate", type=float, default=150.0, help="PN/KC stimulation rate in Hz (default: 150).")
    argument_parser.add_argument("--seed", type=int, default=20260316, help="Brian2/NumPy seed per condition (default: 20260316).")
    argument_parser.add_argument("--kc-set-size", type=int, default=100, help="KC set size per condition (default: 100).")
    argument_parser.add_argument(
        "--kc-set-seed",
        type=int,
        default=20260316,
        help="Seed for the two disjoint KC sets, independent of --seed (default: 20260316).",
    )
    argument_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the grid plan and runtime estimate only; do not run any simulation.",
    )
    return argument_parser


def exact_command(args: argparse.Namespace) -> str:
    return (
        "uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/calibrate_speed.py "
        f"--pn-rate {args.pn_rate:g} --seed {args.seed} "
        f"--kc-set-size {args.kc_set_size} --kc-set-seed {args.kc_set_seed}"
    )


def stimulus_seconds(duration_ms: float, trials: int) -> float:
    return (duration_ms / 1000.0) * trials


def total_stimulus_seconds() -> float:
    baseline_total = sum(stimulus_seconds(duration_ms, BASELINE_TRIALS) for duration_ms in DURATIONS_MS)
    cells_total = sum(
        2 * stimulus_seconds(duration_ms, trials) for duration_ms in DURATIONS_MS for trials in TRIALS_GRID
    )
    return baseline_total + cells_total


def total_trial_equivalents() -> int:
    baseline_total = len(DURATIONS_MS) * BASELINE_TRIALS
    cells_total = sum(2 * trials for _ in DURATIONS_MS for trials in TRIALS_GRID)
    return baseline_total + cells_total


def print_plan(args: argparse.Namespace) -> float:
    """Print the grid and two competing, log-grounded cost projections; return
    the higher (more conservative) of the two totals in seconds."""
    print("Speed calibration grid plan (--stim-mode kc, via check_mb_response.run_condition):")
    print(
        f"  kc-set-size={args.kc_set_size}  kc-set-seed={args.kc_set_seed}  "
        f"pn-rate={args.pn_rate:g} Hz  seed={args.seed}"
    )
    print(f"  Baseline: run once per duration, at trials={BASELINE_TRIALS} (largest trial count in the grid).")
    print()
    print(
        "  Empirical basis (repro/mushroom_body/run_log_*.txt, 15 prior runs, all at "
        "duration_ms=1000/trials=5): elapsed seconds ranged 16-184s (median 23s, "
        "mean 38.3s). Two runs (pn50's 65s/52s, kc_direct's 184s) are documented "
        "unexplained host-load anomalies (mushroom_body_check.md), not attributable "
        "to any swept parameter; excluding them, the remaining 12 runs have median "
        "22.5s / mean 22.8s."
    )
    total_stim_s = total_stimulus_seconds()
    total_trials = total_trial_equivalents()
    optimistic = total_stim_s * EMPIRICAL_MEDIAN_SECONDS_PER_STIMULUS_SECOND
    stim_model_worst = total_stim_s * EMPIRICAL_MEAN_SECONDS_PER_STIMULUS_SECOND
    trial_model_clean = total_trials * EMPIRICAL_CLEAN_MEDIAN_SECONDS_PER_TRIAL
    trial_model_worst = total_trials * EMPIRICAL_MEAN_SECONDS_PER_TRIAL_WITH_OUTLIERS
    print()
    print(
        "  Two competing cost models (duration was never varied historically, so "
        "these cannot yet be distinguished empirically -- resolving this is part "
        "of what this grid is for):"
    )
    print(
        f"    Stimulus-second model (cost scales with duration_ms x trials): "
        f"{optimistic:.0f}s (~{optimistic / 60:.1f} min) at the median rate, "
        f"{stim_model_worst:.0f}s (~{stim_model_worst / 60:.1f} min) at the outlier-inclusive mean rate."
    )
    print(
        "    Trial-dominated model (model.py's run_trial() calls create_model() -- "
        "rebuilding the whole network from the connectivity parquet -- once per "
        "trial, serially (n_proc=1), so cost may not shrink with shorter duration): "
        f"{trial_model_clean:.0f}s (~{trial_model_clean / 60:.1f} min) at the clean "
        f"median per-trial rate, {trial_model_worst:.0f}s (~{trial_model_worst / 60:.1f} min) "
        "at the outlier-inclusive mean per-trial rate."
    )
    worst_case = max(optimistic, stim_model_worst, trial_model_clean, trial_model_worst)
    print()
    print(f"  MOST CONSERVATIVE estimate across both models: {worst_case:.0f}s (~{worst_case / 60:.1f} min).")
    if worst_case > RUNTIME_WARNING_THRESHOLD_SECONDS:
        print(
            "  WARNING: the conservative estimate exceeds ~45 minutes. Proposed reduced "
            "grid: drop trials=2 (keep only trials in {5, 1}) at every duration, cutting "
            "12 grid cells to 8 (~33% less work). Tradeoff: trials=2 is the grid's only "
            "interior sample of the duration/trials interaction; dropping it means the "
            "acceptance decision would rest on just the two extremes (5 and 1 trials) "
            "per duration, so a non-monotonic effect at trials=2 would be missed."
        )
    else:
        print(
            "  This is comfortably under the ~45-minute threshold, so the full grid "
            "above runs as specified -- no reduction is proposed."
        )
    print()
    print(
        "  Reuse note: the duration_ms=1000/trials=5 cell (the single most expensive "
        "cell, including the documented 184s anomaly) was already run in a prior "
        "--stim-mode kc diagnostic with identical seed/pn-rate/kc-set-seed/kc-set-size. "
        "If that result file is found (see calibration_dir()/seed_cache_from_existing_run), "
        "it is reused instead of re-simulated, saving ~243s of duplicate work."
    )
    return worst_case


def calibration_dir(args: argparse.Namespace) -> Path:
    suffix = (
        f"kc_size_{args.kc_set_size}_kc_seed_{args.kc_set_seed}"
        f"_pn_rate_hz_{args.pn_rate:g}_seed_{args.seed}"
    )
    return mbr.RESULTS_DIR / f"speed_calibration_{suffix}"


def existing_reference_run_path(args: argparse.Namespace) -> Path:
    """Path check_mb_response.py would have used for a plain (no diagnostic
    flags) --stim-mode kc run at the grid's reference cell (1000 ms, 5 trials)
    with these exact seed/pn-rate/kc-set parameters."""
    suffix = (
        f"seed_{args.seed}_trials_{REFERENCE_TRIALS}_duration_ms_{REFERENCE_DURATION_MS:g}"
        f"_pn_rate_hz_{args.pn_rate:g}_stim_kc_size_{args.kc_set_size}_kc_seed_{args.kc_set_seed}"
    )
    return mbr.RESULTS_DIR / f"mb_response_{suffix}.json"


def seed_cache_from_existing_run(args: argparse.Namespace, out_dir: Path) -> None:
    """Reuse a prior plain check_mb_response.py --stim-mode kc run for the
    (1000 ms, 5 trials) reference cell instead of re-simulating it, if one
    exists with identical parameters. This is the grid's single most
    expensive cell (it includes the documented 184s kc_set_b anomaly), so
    reuse meaningfully lowers actual runtime. No-ops if the calibration's own
    cache already covers this cell, or if no matching prior run is found."""
    baseline_path = out_dir / f"baseline_duration_ms_{REFERENCE_DURATION_MS:g}.json"
    cell_path = out_dir / f"cell_duration_ms_{REFERENCE_DURATION_MS:g}_trials_{REFERENCE_TRIALS}.json"
    if baseline_path.exists() and cell_path.exists():
        return
    source_path = existing_reference_run_path(args)
    if not source_path.exists():
        return
    payload = json.loads(source_path.read_text())
    parameters = payload.get("parameters", {})
    matches = (
        parameters.get("stim_mode") == "kc"
        and parameters.get("trials") == REFERENCE_TRIALS
        and parameters.get("duration_ms") == REFERENCE_DURATION_MS
        and parameters.get("pn_rate_hz") == args.pn_rate
        and parameters.get("seed") == args.seed
        and parameters.get("kc_set_size") == args.kc_set_size
        and parameters.get("kc_set_seed") == args.kc_set_seed
    )
    conditions = {condition["condition"]: condition for condition in payload.get("conditions", [])}
    if not matches or not {"baseline", "kc_set_a", "kc_set_b"} <= set(conditions):
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    if not baseline_path.exists():
        baseline_path.write_text(json.dumps(slim_condition(conditions["baseline"]), indent=2))
        print(f"[baseline] duration_ms={REFERENCE_DURATION_MS:g}: reused from {source_path.name} (not re-simulated)")
    if not cell_path.exists():
        cell_result = {
            "duration_ms": REFERENCE_DURATION_MS,
            "trials": REFERENCE_TRIALS,
            "condition_a": slim_condition(conditions["kc_set_a"]),
            "condition_b": slim_condition(conditions["kc_set_b"]),
        }
        cell_path.write_text(json.dumps(cell_result, indent=2))
        print(
            f"[cell] duration_ms={REFERENCE_DURATION_MS:g} trials={REFERENCE_TRIALS}: "
            f"reused from {source_path.name} (not re-simulated)"
        )


def output_suffix(args: argparse.Namespace) -> str:
    return (
        f"kc_size_{args.kc_set_size}_kc_seed_{args.kc_set_seed}"
        f"_pn_rate_hz_{args.pn_rate:g}_seed_{args.seed}"
    )


def slim_condition(result: dict) -> dict:
    """Whitelist the fields this calibration needs; drops the large per-KC/per-PN
    rate dicts and top-active-cell-type lists that check_mb_response.py's own
    writers handle, so cached files stay well under 1 MB regardless of grid size."""
    kc = result["kc"]
    return {
        "condition": result["condition"],
        "runtime_seconds": result["runtime_seconds"],
        "spike_count": result["spike_count"],
        "kc": {
            "count": kc["count"],
            "active_count_gt_0_hz": kc["active_count_gt_0_hz"],
            "active_fraction_gt_0_hz": kc["active_fraction_gt_0_hz"],
            "mean_rate_hz": kc["mean_rate_hz"],
        },
        "kc_target_vs_nontarget": result["kc_target_vs_nontarget"],
        "mbons_nonzero": result["mbons_nonzero"],
        "pam_nonzero": result["pam_nonzero"],
        "ppl1_nonzero": result["ppl1_nonzero"],
        "apl_nonzero": result["apl_nonzero"],
        "active_nonstim_pn_count": result["active_nonstim_pn_count"],
        "brain_wide": {
            "active_neuron_count": result["brain_wide"]["active_neuron_count"],
            "active_neuron_fraction": result["brain_wide"]["active_neuron_fraction"],
        },
    }


def make_args(duration_ms: float, trials: int, args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        trials=trials,
        pn_rate=args.pn_rate,
        seed=args.seed,
        duration_ms=duration_ms,
        stim_mode="kc",
    )


def run_or_load_baseline(
    duration_ms: float,
    args: argparse.Namespace,
    payload: dict,
    annotations: pd.DataFrame,
    pn_glomerulus: dict,
    total_brain_neurons: int,
    out_dir: Path,
) -> dict:
    path = out_dir / f"baseline_duration_ms_{duration_ms:g}.json"
    if path.exists():
        print(f"[baseline] duration_ms={duration_ms:g}: cached, skipped")
        return json.loads(path.read_text())
    print(f"[baseline] duration_ms={duration_ms:g}: running ({BASELINE_TRIALS} trials)...")
    condition_args = make_args(duration_ms, BASELINE_TRIALS, args)
    with tempfile.TemporaryDirectory(prefix="flyshi-mb-calibrate-") as temporary_directory:
        scratch_dir = Path(temporary_directory)
        result = mbr.run_condition(
            "baseline", [], payload, condition_args, scratch_dir, annotations, pn_glomerulus, set(), total_brain_neurons
        )
    slim = slim_condition(result)
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(slim, indent=2))
    return slim


def run_or_load_cell(
    duration_ms: float,
    trials: int,
    args: argparse.Namespace,
    payload: dict,
    annotations: pd.DataFrame,
    pn_glomerulus: dict,
    total_brain_neurons: int,
    out_dir: Path,
) -> dict:
    path = out_dir / f"cell_duration_ms_{duration_ms:g}_trials_{trials}.json"
    if path.exists():
        print(f"[cell] duration_ms={duration_ms:g} trials={trials}: cached, skipped")
        return json.loads(path.read_text())
    print(f"[cell] duration_ms={duration_ms:g} trials={trials}: running (set_a, set_b)...")
    condition_args = make_args(duration_ms, trials, args)
    kc_set_a, kc_set_b = mbr.select_disjoint_kc_sets(
        payload["kenyon_cells"]["records"], args.kc_set_size, args.kc_set_seed
    )
    target_a, target_b = set(kc_set_a), set(kc_set_b)
    with tempfile.TemporaryDirectory(prefix="flyshi-mb-calibrate-") as temporary_directory:
        scratch_dir = Path(temporary_directory)
        condition_a = mbr.run_condition(
            "kc_set_a", kc_set_a, payload, condition_args, scratch_dir, annotations, pn_glomerulus, target_a, total_brain_neurons
        )
        condition_b = mbr.run_condition(
            "kc_set_b", kc_set_b, payload, condition_args, scratch_dir, annotations, pn_glomerulus, target_b, total_brain_neurons
        )
    result = {
        "duration_ms": duration_ms,
        "trials": trials,
        "condition_a": slim_condition(condition_a),
        "condition_b": slim_condition(condition_b),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    return result


def cosine_distance(vector_a: dict[int, float], vector_b: dict[int, float]) -> float | None:
    """1 - cosine similarity between per-MBON rate vectors, restricted to MBONs
    nonzero in EITHER condition (the union support). Rates are non-negative, so
    the result lies in [0, 1]: 0 means the two conditions drive the MBON
    population in the same relative proportions, 1 means fully separated.

    Conventions for degenerate cases (documented in docs/design/speed-calibration.md):
    - If NEITHER condition drives any MBON (union support is empty), the score
      is undefined and this returns None -- there is nothing to compare.
    - If exactly one condition drives no MBON in the support (the other has
      some), similarity is treated as 0 (dot product is literally 0), so the
      distance is 1.0 -- maximally separated, by convention.
    """
    support = sorted(
        neuron_id
        for neuron_id in set(vector_a) | set(vector_b)
        if vector_a.get(neuron_id, 0.0) > 0 or vector_b.get(neuron_id, 0.0) > 0
    )
    if not support:
        return None
    rates_a = np.array([vector_a.get(neuron_id, 0.0) for neuron_id in support])
    rates_b = np.array([vector_b.get(neuron_id, 0.0) for neuron_id in support])
    denominator = np.linalg.norm(rates_a) * np.linalg.norm(rates_b)
    similarity = float(np.dot(rates_a, rates_b) / denominator) if denominator > 0 else 0.0
    return 1.0 - similarity


def summarize_cell(cell_result: dict, baseline_result: dict) -> dict:
    condition_a = cell_result["condition_a"]
    condition_b = cell_result["condition_b"]
    mbon_rates_a = {row["root_id"]: row["rate_hz"] for row in condition_a["mbons_nonzero"]}
    mbon_rates_b = {row["root_id"]: row["rate_hz"] for row in condition_b["mbons_nonzero"]}
    mbon_identity_jaccard = mbr.jaccard(list(mbon_rates_a), list(mbon_rates_b))
    separation_score = cosine_distance(mbon_rates_a, mbon_rates_b)

    target_a = condition_a["kc_target_vs_nontarget"]
    target_b = condition_b["kc_target_vs_nontarget"]
    nonstim_left_a = target_a["nontarget_by_side"]["left"]["active_fraction_gt_0_hz"]
    nonstim_right_a = target_a["nontarget_by_side"]["right"]["active_fraction_gt_0_hz"]
    nonstim_left_b = target_b["nontarget_by_side"]["left"]["active_fraction_gt_0_hz"]
    nonstim_right_b = target_b["nontarget_by_side"]["right"]["active_fraction_gt_0_hz"]

    return {
        "duration_ms": cell_result["duration_ms"],
        "trials": cell_result["trials"],
        "runtime_seconds_a": condition_a["runtime_seconds"],
        "runtime_seconds_b": condition_b["runtime_seconds"],
        "runtime_seconds_baseline": baseline_result["runtime_seconds"],
        "total_wall_seconds": condition_a["runtime_seconds"] + condition_b["runtime_seconds"],
        "target_mean_rate_hz_a": target_a["target"]["mean_rate_hz"],
        "target_mean_rate_hz_b": target_b["target"]["mean_rate_hz"],
        "nonstim_kc_active_fraction_left_a": nonstim_left_a,
        "nonstim_kc_active_fraction_right_a": nonstim_right_a,
        "nonstim_kc_active_fraction_left_b": nonstim_left_b,
        "nonstim_kc_active_fraction_right_b": nonstim_right_b,
        "nonstim_kc_active_fraction_max": max(nonstim_left_a, nonstim_right_a, nonstim_left_b, nonstim_right_b),
        "n_mbons_nonzero_a": len(mbon_rates_a),
        "n_mbons_nonzero_b": len(mbon_rates_b),
        "mbon_identity_jaccard": mbon_identity_jaccard,
        "separation_score_cosine_distance": separation_score,
        "baseline_active_fraction_gt_0_hz": baseline_result["kc"]["active_fraction_gt_0_hz"],
    }


def write_summary_csv(rows: list[dict], output: Path) -> None:
    fieldnames = [
        "duration_ms", "trials", "runtime_seconds_a", "runtime_seconds_b", "runtime_seconds_baseline",
        "total_wall_seconds", "target_mean_rate_hz_a", "target_mean_rate_hz_b",
        "nonstim_kc_active_fraction_left_a", "nonstim_kc_active_fraction_right_a",
        "nonstim_kc_active_fraction_left_b", "nonstim_kc_active_fraction_right_b",
        "nonstim_kc_active_fraction_max", "n_mbons_nonzero_a", "n_mbons_nonzero_b",
        "mbon_identity_jaccard", "separation_score_cosine_distance",
        "separation_score_ratio_to_reference", "baseline_active_fraction_gt_0_hz", "passes_acceptance",
    ]
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (-r["duration_ms"], -r["trials"])):
            writer.writerow(row)


def write_mbon_rates_csv(cells: dict[tuple[float, int], dict], output: Path) -> None:
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["duration_ms", "trials", "condition", "root_id", "cell_type", "side", "rate_hz"]
        )
        writer.writeheader()
        for (duration_ms, trials), cell in sorted(cells.items(), key=lambda item: (-item[0][0], -item[0][1])):
            for condition_key, condition_name in (("condition_a", "kc_set_a"), ("condition_b", "kc_set_b")):
                for row in cell[condition_key]["mbons_nonzero"]:
                    writer.writerow(
                        {"duration_ms": duration_ms, "trials": trials, "condition": condition_name, **row}
                    )


def main() -> None:
    args = parser().parse_args()
    if args.kc_set_size <= 0:
        raise ValueError("--kc-set-size must be positive")
    if args.pn_rate < 0:
        raise ValueError("--pn-rate must be non-negative")

    print_plan(args)
    if args.dry_run:
        print()
        print("Dry run: no simulation was executed.")
        return

    print()
    print(f"Exact command being run:\n  {exact_command(args)}")
    print("Reminder: on macOS, run this under `caffeinate -i` to prevent sleep mid-run.")
    print()

    payload = mbr.read_ids()
    annotations = mbr.load_annotations()
    pn_glomerulus = mbr.pn_glomerulus_map(payload)
    total_brain_neurons = len(pd.read_csv(mbr.UPSTREAM_ROOT / "Completeness_783.csv", index_col=0))
    out_dir = calibration_dir(args)
    seed_cache_from_existing_run(args, out_dir)

    baselines: dict[float, dict] = {}
    for duration_ms in DURATIONS_MS:
        baselines[duration_ms] = run_or_load_baseline(
            duration_ms, args, payload, annotations, pn_glomerulus, total_brain_neurons, out_dir
        )

    cells: dict[tuple[float, int], dict] = {}
    for duration_ms in DURATIONS_MS:
        for trials in TRIALS_GRID:
            cells[(duration_ms, trials)] = run_or_load_cell(
                duration_ms, trials, args, payload, annotations, pn_glomerulus, total_brain_neurons, out_dir
            )

    rows = [summarize_cell(cells[key], baselines[key[0]]) for key in cells]
    reference_row = next(
        row for row in rows if row["duration_ms"] == REFERENCE_DURATION_MS and row["trials"] == REFERENCE_TRIALS
    )
    reference_score = reference_row["separation_score_cosine_distance"]
    for row in rows:
        score = row["separation_score_cosine_distance"]
        if reference_score is None or score is None or reference_score <= 0:
            row["separation_score_ratio_to_reference"] = None
            row["passes_acceptance"] = False
            continue
        ratio = score / reference_score
        row["separation_score_ratio_to_reference"] = ratio
        row["passes_acceptance"] = bool(
            ratio >= ACCEPTANCE_MIN_SEPARATION_RATIO
            and row["nonstim_kc_active_fraction_max"] < ACCEPTANCE_MAX_NONSTIM_KC_FRACTION
        )

    suffix = output_suffix(args)
    summary_path = mbr.RESULTS_DIR / f"speed_calibration_summary_{suffix}.csv"
    mbon_rates_path = mbr.RESULTS_DIR / f"speed_calibration_mbon_rates_{suffix}.csv"
    write_summary_csv(rows, summary_path)
    write_mbon_rates_csv(cells, mbon_rates_path)

    print()
    for row in sorted(rows, key=lambda r: (-r["duration_ms"], -r["trials"])):
        ratio = row["separation_score_ratio_to_reference"]
        ratio_str = f"{ratio:.3f}" if ratio is not None else "n/a"
        print(
            f"duration_ms={row['duration_ms']:>6g} trials={row['trials']}: "
            f"wall={row['total_wall_seconds']:.1f}s  "
            f"separation={row['separation_score_cosine_distance']}  "
            f"ratio_to_ref={ratio_str}  "
            f"nonstim_kc_max={row['nonstim_kc_active_fraction_max']:.4%}  "
            f"passes={row['passes_acceptance']}"
        )
    print()
    print(f"Summary CSV: {summary_path}")
    print(f"Per-MBON rate CSV: {mbon_rates_path}")
    print(f"Per-cell/baseline cache (restart source): {out_dir}")


if __name__ == "__main__":
    main()
