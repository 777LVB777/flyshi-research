"""Prepare a v783 mushroom-body response check using Shiu et al. model code."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path
from time import perf_counter

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_ROOT = ROOT / "third_party" / "Drosophila_brain_model"
sys.path.insert(0, str(UPSTREAM_ROOT))

from brian2 import Hz, ms, seed as brian_seed  # noqa: E402
from model import default_params, run_exp  # noqa: E402
import utils as utl  # noqa: E402


IDS_PATH = ROOT / "repro" / "mushroom_body" / "neuron_ids_783.json"
RESULTS_DIR = ROOT / "repro" / "mushroom_body" / "results"
ODOR_A_GLOMERULUS = "DA1"
ODOR_B_GLOMERULUS = "DL2d"
SIDE = "left"


def parser() -> argparse.ArgumentParser:
    command = (
        "uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/check_mb_response.py "
        "--trials 5 --rate-hz 150 --seed 20260316"
    )
    argument_parser = argparse.ArgumentParser(
        description="Run baseline, DA1, and DL2d v783 mushroom-body checks.",
        epilog=f"Exact run command:\n  {command}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    argument_parser.add_argument("--trials", type=int, default=5, help="Trials per condition (default: 5).")
    argument_parser.add_argument("--rate-hz", type=float, default=150.0, help="PN stimulation rate in Hz (default: 150).")
    argument_parser.add_argument("--seed", type=int, default=20260316, help="Brian2/NumPy seed per condition.")
    argument_parser.add_argument("--duration-ms", type=float, default=1000.0, help="Trial duration in ms (default: 1000).")
    return argument_parser


def read_ids() -> dict[str, object]:
    return json.loads(IDS_PATH.read_text())


def ids(records: list[dict[str, object]]) -> list[int]:
    return [int(record["root_id"]) for record in records]


def rates_for(rates: object, experiment_name: str, neuron_ids: list[int]) -> dict[int, float]:
    return {
        neuron_id: float(rates.loc[neuron_id, experiment_name]) if neuron_id in rates.index else 0.0
        for neuron_id in neuron_ids
    }


def annotated_rates(records: list[dict[str, object]], rates: dict[int, float]) -> list[dict[str, object]]:
    return [
        {
            "root_id": int(record["root_id"]),
            "cell_type": record.get("cell_type", ""),
            "side": record.get("side", ""),
            "rate_hz": rates[int(record["root_id"])],
        }
        for record in records
        if rates[int(record["root_id"])] > 0
    ]


def run_condition(
    name: str,
    stimulated_ids: list[int],
    payload: dict[str, object],
    args: argparse.Namespace,
    scratch_dir: Path,
) -> dict[str, object]:
    """Run one condition and return only derived summaries, never raw spikes."""
    np.random.seed(args.seed)
    brian_seed(args.seed)
    params = default_params.copy()
    params["t_run"] = args.duration_ms * ms
    params["n_run"] = args.trials
    params["r_poi"] = args.rate_hz * Hz

    output_dir = scratch_dir / name
    output_dir.mkdir()
    start = perf_counter()
    run_exp(
        exp_name=name,
        neu_exc=stimulated_ids,
        path_res=output_dir,
        path_comp=UPSTREAM_ROOT / "Completeness_783.csv",
        path_con=UPSTREAM_ROOT / "Connectivity_783.parquet",
        params=params,
        n_proc=1,
    )
    runtime_seconds = perf_counter() - start
    spikes = utl.load_exps([output_dir / f"{name}.parquet"])
    rates, _ = utl.get_rate(spikes, params["t_run"], params["n_run"])

    kcs = payload["kenyon_cells"]["records"]
    mbons = payload["mbons"]["records"]
    pam = payload["pam_dopamine_neurons"]["records"]
    ppl1 = payload["ppl1_dopamine_neurons"]["records"]
    apl = payload["apl_neurons"]["records"]
    kc_rates = rates_for(rates, name, ids(kcs))
    mbon_rates = rates_for(rates, name, ids(mbons))
    pam_rates = rates_for(rates, name, ids(pam))
    ppl1_rates = rates_for(rates, name, ids(ppl1))
    apl_rates = rates_for(rates, name, ids(apl))
    active_kcs = sorted(neuron_id for neuron_id, rate in kc_rates.items() if rate > 0)

    return {
        "condition": name,
        "stimulated_pn_ids": stimulated_ids,
        "runtime_seconds": runtime_seconds,
        "spike_count": len(spikes),
        "kc": {
            "count": len(kc_rates),
            "active_count_gt_0_hz": len(active_kcs),
            "active_fraction_gt_0_hz": len(active_kcs) / len(kc_rates),
            "active_count_gt_5_hz": sum(rate > 5 for rate in kc_rates.values()),
            "active_fraction_gt_5_hz": sum(rate > 5 for rate in kc_rates.values()) / len(kc_rates),
            "mean_rate_hz": sum(kc_rates.values()) / len(kc_rates),
            "active_ids_gt_0_hz": active_kcs,
        },
        "mbons_nonzero": annotated_rates(mbons, mbon_rates),
        "pam_nonzero": annotated_rates(pam, pam_rates),
        "ppl1_nonzero": annotated_rates(ppl1, ppl1_rates),
        "apl_nonzero": annotated_rates(apl, apl_rates),
    }


def jaccard(first: list[int], second: list[int]) -> float:
    first_set, second_set = set(first), set(second)
    union = first_set | second_set
    return len(first_set & second_set) / len(union) if union else 0.0


def write_csv(summary: dict[str, object], output: Path) -> None:
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["condition", "group", "root_id", "cell_type", "side", "rate_hz"])
        writer.writeheader()
        for condition in summary["conditions"]:
            for group in ("mbons_nonzero", "pam_nonzero", "ppl1_nonzero", "apl_nonzero"):
                for row in condition[group]:
                    writer.writerow({"condition": condition["condition"], "group": group, **row})


def main() -> None:
    args = parser().parse_args()
    if args.trials <= 0 or args.rate_hz < 0 or args.duration_ms <= 0:
        raise ValueError("trials and duration must be positive; rate must be non-negative")
    payload = read_ids()
    groups = payload["uniglomerular_antenna_lobe_projection_neurons"]["groups_by_glomerulus_and_side"]
    odor_a = groups[ODOR_A_GLOMERULUS][SIDE]
    odor_b = groups[ODOR_B_GLOMERULUS][SIDE]

    with tempfile.TemporaryDirectory(prefix="flyshi-mb-check-") as temporary_directory:
        scratch_dir = Path(temporary_directory)
        baseline = run_condition("baseline", [], payload, args, scratch_dir)
        condition_a = run_condition("odor_a_da1_left", odor_a, payload, args, scratch_dir)
        condition_b = run_condition("odor_b_dl2d_left", odor_b, payload, args, scratch_dir)

    overlap = jaccard(condition_a["kc"]["active_ids_gt_0_hz"], condition_b["kc"]["active_ids_gt_0_hz"])
    summary = {
        "flywire_version": "783",
        "annotation_release": payload["annotation_source"],
        "parameters": {
            "trials": args.trials,
            "duration_ms": args.duration_ms,
            "stimulation_rate_hz": args.rate_hz,
            "seed": args.seed,
            "n_proc": 1,
        },
        "glomeruli": {
            "odor_a": {"glomerulus": ODOR_A_GLOMERULUS, "side": SIDE, "pn_count": len(odor_a)},
            "odor_b": {"glomerulus": ODOR_B_GLOMERULUS, "side": SIDE, "pn_count": len(odor_b)},
        },
        "conditions": [baseline, condition_a, condition_b],
        "odor_a_vs_b_active_kc_jaccard_gt_0_hz": overlap,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    json_path = RESULTS_DIR / f"mb_response_seed_{args.seed}.json"
    csv_path = RESULTS_DIR / f"mb_response_seed_{args.seed}.csv"
    json_path.write_text(json.dumps(summary, indent=2) + "\n")
    write_csv(summary, csv_path)

    for condition in summary["conditions"]:
        kc = condition["kc"]
        print(
            f"{condition['condition']}: KC >0 Hz={kc['active_fraction_gt_0_hz']:.4%}, "
            f">5 Hz={kc['active_fraction_gt_5_hz']:.4%}, mean={kc['mean_rate_hz']:.4f} Hz, "
            f"nonzero MBONs={len(condition['mbons_nonzero'])}"
        )
    print(f"Odor A/B active-KC Jaccard (>0 Hz): {overlap:.6f}")
    print(f"Summary JSON: {json_path}")
    print(f"Summary CSV: {csv_path}")


if __name__ == "__main__":
    main()
