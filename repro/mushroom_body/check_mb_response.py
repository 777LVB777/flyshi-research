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
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_ROOT = ROOT / "third_party" / "Drosophila_brain_model"
sys.path.insert(0, str(UPSTREAM_ROOT))

from brian2 import Hz, mV, ms, seed as brian_seed  # noqa: E402
import model as shiu_model  # noqa: E402
from model import default_params, run_exp  # noqa: E402
import utils as utl  # noqa: E402


IDS_PATH = ROOT / "repro" / "mushroom_body" / "neuron_ids_783.json"
RESULTS_DIR = ROOT / "repro" / "mushroom_body" / "results"
FLYWIRE_ANNOTATIONS = ROOT / "third_party" / "flywire_annotations" / "supplemental_files" / "Supplemental_file1_neuron_annotations.tsv"
ODOR_A_GLOMERULUS = "DA1"
ODOR_B_GLOMERULUS = "DL2d"
SIDE = "left"


def parser() -> argparse.ArgumentParser:
    command = (
        "uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/check_mb_response.py "
        "--trials 5 --pn-rate 150 --seed 20260316"
    )
    argument_parser = argparse.ArgumentParser(
        description="Run baseline, DA1, and DL2d v783 mushroom-body checks.",
        epilog=f"Exact run command:\n  {command}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    argument_parser.add_argument("--trials", type=int, default=5, help="Trials per condition (default: 5).")
    argument_parser.add_argument("--pn-rate", "--rate-hz", dest="pn_rate", type=float, default=150.0, help="PN stimulation rate in Hz (default: 150).")
    argument_parser.add_argument("--seed", type=int, default=20260316, help="Brian2/NumPy seed per condition.")
    argument_parser.add_argument("--duration-ms", type=float, default=1000.0, help="Trial duration in ms (default: 1000).")
    argument_parser.add_argument("--kc-kc-off", action="store_true", help="Candidate diagnostic: zero only KC-to-KC weights in memory after upstream model construction.")
    argument_parser.add_argument(
        "--dan-kc-off",
        action="store_true",
        help=(
            "Candidate diagnostic: zero synapses from annotated dopaminergic neurons "
            "(PAM, PPL1, and other cell_class=='DAN' subtypes) onto KCs, in memory only. "
            "Rationale: these DAN->KC synapses are currently treated as fast excitatory "
            "(see docs/reproduction/mushroom_body_check.md); in vivo dopamine acts as a "
            "slow modulator of KC plasticity, not a fast driver of KC spiking."
        ),
    )
    argument_parser.add_argument(
        "--modulatory-fast-off",
        action="store_true",
        help=(
            "Candidate diagnostic: zero all outgoing synapses from any neuron whose "
            "predicted fast transmitter (top_nt) is dopamine, serotonin, or octopamine, "
            "in memory only. Rationale: these three transmitters are biological "
            "neuromodulators, not fast ionotropic transmitters, so the model's blanket "
            "fast-excitatory sign for them is suspect. CAVEAT: about half of the "
            "synapses this flag removes originate from Kenyon cells themselves, because "
            "the EM neurotransmitter classifier mispredicts nearly all KCs as top_nt== "
            "'dopamine' (true/known transmitter is acetylcholine); see "
            "docs/reproduction/mushroom_body_check.md before interpreting results."
        ),
    )
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


def kc_by_side(records: list[dict[str, object]], rates: dict[int, float]) -> dict[str, dict[str, float | int]]:
    """Summarize all annotated KCs by their annotation side."""
    summary: dict[str, dict[str, float | int]] = {}
    for side in ("left", "right"):
        side_rates = [rates[int(record["root_id"])] for record in records if record["side"] == side]
        summary[side] = {
            "count": len(side_rates),
            "active_count_gt_0_hz": sum(rate > 0 for rate in side_rates),
            "active_fraction_gt_0_hz": sum(rate > 0 for rate in side_rates) / len(side_rates),
            "active_count_gt_5_hz": sum(rate > 5 for rate in side_rates),
            "active_fraction_gt_5_hz": sum(rate > 5 for rate in side_rates) / len(side_rates),
            "mean_rate_hz": sum(side_rates) / len(side_rates),
        }
    return summary


def load_annotations() -> pd.DataFrame:
    """Load the official flywire_annotations release used by prepare_neuron_ids.py."""
    return pd.read_csv(
        FLYWIRE_ANNOTATIONS,
        sep="\t",
        low_memory=False,
        usecols=["root_id", "cell_class", "cell_type", "top_nt"],
    )


def dan_ids_from_annotations() -> list[int]:
    """All annotated dopaminergic neurons: PAM, PPL1, and other DAN subtypes (e.g. PPL2)."""
    annotations = load_annotations()
    dans = annotations[annotations["cell_class"] == "DAN"]
    return sorted(int(root_id) for root_id in dans["root_id"])


def modulatory_ids_from_annotations() -> list[int]:
    """Neurons whose predicted fast transmitter (top_nt) is dopamine, serotonin, or octopamine.

    Includes Kenyon cells: the EM neurotransmitter classifier mispredicts ~99.9% of
    KCs as top_nt=='dopamine' even though their known/literature transmitter is
    acetylcholine (see docs/reproduction/mushroom_body_check.md).
    """
    annotations = load_annotations()
    modulatory = annotations[annotations["top_nt"].isin(["dopamine", "serotonin", "octopamine"])]
    return sorted(int(root_id) for root_id in modulatory["root_id"])


def brian_indices(neuron_ids: list[int], index_by_id: dict[int, int]) -> np.ndarray:
    return np.array([index_by_id[neuron_id] for neuron_id in neuron_ids if neuron_id in index_by_id], dtype=int)


def zero_between(synapses, pre_indices: np.ndarray, post_indices: np.ndarray) -> int:
    """Zero synapse weights where both endpoints match; return the number zeroed."""
    mask = np.isin(np.asarray(synapses.i[:]), pre_indices) & np.isin(np.asarray(synapses.j[:]), post_indices)
    indices = np.flatnonzero(mask)
    synapses.w[indices] = 0 * mV
    return int(len(indices))


def zero_from(synapses, pre_indices: np.ndarray) -> int:
    """Zero all outgoing synapse weights from the given presynaptic indices; return count zeroed."""
    mask = np.isin(np.asarray(synapses.i[:]), pre_indices)
    indices = np.flatnonzero(mask)
    synapses.w[indices] = 0 * mV
    return int(len(indices))


def report_synapse_removal_counts(args: argparse.Namespace, kc_ids: list[int]) -> None:
    """Print, from the connectivity table alone, how many synapses each active
    diagnostic flag will zero. Purely informational; does not touch Brian2."""
    if not (args.dan_kc_off or args.modulatory_fast_off):
        return
    connectivity = pd.read_parquet(
        UPSTREAM_ROOT / "Connectivity_783.parquet",
        columns=["Presynaptic_ID", "Postsynaptic_ID", "Connectivity"],
    )
    kc_id_set = set(kc_ids)
    if args.dan_kc_off:
        dan_ids = set(dan_ids_from_annotations())
        removed = connectivity[
            connectivity["Presynaptic_ID"].isin(dan_ids) & connectivity["Postsynaptic_ID"].isin(kc_id_set)
        ]
        print(
            f"    --dan-kc-off will zero {int(removed['Connectivity'].sum())} synapses "
            f"({len(removed)} pre/post pairs) from {len(dan_ids)} annotated DANs onto {len(kc_ids)} KCs."
        )
    if args.modulatory_fast_off:
        modulatory_ids = set(modulatory_ids_from_annotations())
        removed = connectivity[connectivity["Presynaptic_ID"].isin(modulatory_ids)]
        kc_share = removed[removed["Presynaptic_ID"].isin(kc_id_set)]["Connectivity"].sum()
        total = int(removed["Connectivity"].sum())
        kc_fraction = kc_share / total if total else 0.0
        print(
            f"    --modulatory-fast-off will zero {total} synapses ({len(removed)} pairs) "
            f"from {len(modulatory_ids)} neurons with top_nt in "
            f"{{dopamine, serotonin, octopamine}}, network-wide. "
            f"{kc_fraction:.1%} of the removed synapses originate from Kenyon cells "
            f"(misclassified top_nt, true transmitter acetylcholine) rather than true "
            f"dopaminergic/serotonergic/octopaminergic neurons."
        )


def install_diagnostic_silencers(args: argparse.Namespace, kc_ids: list[int]):
    """Return the original upstream silencer after composing in-memory synapse masks
    for every requested diagnostic (--kc-kc-off, --dan-kc-off, --modulatory-fast-off).

    These are candidate diagnostic manipulations only, not validated fixes. None of
    them edit upstream source or connectivity files; all masking happens on the live
    brian2.Synapses object after upstream model construction.
    """
    if not (args.kc_kc_off or args.dan_kc_off or args.modulatory_fast_off):
        return None

    completeness = pd.read_csv(UPSTREAM_ROOT / "Completeness_783.csv", index_col=0)
    index_by_id = {int(root_id): index for index, root_id in enumerate(completeness.index)}
    kc_indices = brian_indices(kc_ids, index_by_id)

    manipulations: list = []
    if args.kc_kc_off:
        manipulations.append(lambda synapses: zero_between(synapses, kc_indices, kc_indices))
    if args.dan_kc_off:
        dan_indices = brian_indices(dan_ids_from_annotations(), index_by_id)
        manipulations.append(lambda synapses: zero_between(synapses, dan_indices, kc_indices))
    if args.modulatory_fast_off:
        modulatory_indices = brian_indices(modulatory_ids_from_annotations(), index_by_id)
        manipulations.append(lambda synapses: zero_from(synapses, modulatory_indices))

    original_silence = shiu_model.silence

    def combined_silence(silenced_indices, synapses):
        synapses = original_silence(silenced_indices, synapses)
        for mask_fn in manipulations:
            mask_fn(synapses)
        return synapses

    shiu_model.silence = combined_silence
    return original_silence


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
    params["r_poi"] = args.pn_rate * Hz

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
            "by_side": kc_by_side(kcs, kc_rates),
        },
        "kc_rates_hz_by_id": kc_rates,
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


def write_kc_rates_csv(summary: dict[str, object], payload: dict[str, object], output: Path) -> None:
    kc_sides = {int(record["root_id"]): record["side"] for record in payload["kenyon_cells"]["records"]}
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["condition", "root_id", "side", "rate_hz"])
        writer.writeheader()
        for condition in summary["conditions"]:
            for root_id, rate in condition.pop("kc_rates_hz_by_id").items():
                writer.writerow({"condition": condition["condition"], "root_id": root_id, "side": kc_sides[int(root_id)], "rate_hz": rate})


def main() -> None:
    args = parser().parse_args()
    if args.trials <= 0 or args.pn_rate < 0 or args.duration_ms <= 0:
        raise ValueError("trials and duration must be positive; rate must be non-negative")
    payload = read_ids()
    groups = payload["uniglomerular_antenna_lobe_projection_neurons"]["groups_by_glomerulus_and_side"]
    odor_a = groups[ODOR_A_GLOMERULUS][SIDE]
    odor_b = groups[ODOR_B_GLOMERULUS][SIDE]

    kc_ids = ids(payload["kenyon_cells"]["records"])
    report_synapse_removal_counts(args, kc_ids)
    original_silence = install_diagnostic_silencers(args, kc_ids)
    try:
        with tempfile.TemporaryDirectory(prefix="flyshi-mb-check-") as temporary_directory:
            scratch_dir = Path(temporary_directory)
            baseline = run_condition("baseline", [], payload, args, scratch_dir)
            condition_a = run_condition("odor_a_da1_left", odor_a, payload, args, scratch_dir)
            condition_b = run_condition("odor_b_dl2d_left", odor_b, payload, args, scratch_dir)
    finally:
        if original_silence is not None:
            shiu_model.silence = original_silence

    overlap = jaccard(condition_a["kc"]["active_ids_gt_0_hz"], condition_b["kc"]["active_ids_gt_0_hz"])
    summary = {
        "flywire_version": "783",
        "annotation_release": payload["annotation_source"],
        "parameters": {
            "trials": args.trials,
            "duration_ms": args.duration_ms,
            "pn_rate_hz": args.pn_rate,
            "seed": args.seed,
            "n_proc": 1,
            "kc_kc_off": args.kc_kc_off,
            "dan_kc_off": args.dan_kc_off,
            "modulatory_fast_off": args.modulatory_fast_off,
        },
        "glomeruli": {
            "odor_a": {"glomerulus": ODOR_A_GLOMERULUS, "side": SIDE, "pn_count": len(odor_a)},
            "odor_b": {"glomerulus": ODOR_B_GLOMERULUS, "side": SIDE, "pn_count": len(odor_b)},
        },
        "conditions": [baseline, condition_a, condition_b],
        "odor_a_vs_b_active_kc_jaccard_gt_0_hz": overlap,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    suffix = (
        f"seed_{args.seed}_trials_{args.trials}_duration_ms_{args.duration_ms:g}"
        f"_pn_rate_hz_{args.pn_rate:g}"
        + ("_kc_kc_off" if args.kc_kc_off else "")
        + ("_dan_kc_off" if args.dan_kc_off else "")
        + ("_modulatory_fast_off" if args.modulatory_fast_off else "")
    )
    json_path = RESULTS_DIR / f"mb_response_{suffix}.json"
    csv_path = RESULTS_DIR / f"mb_response_{suffix}.csv"
    kc_rates_path = RESULTS_DIR / f"mb_kc_rates_{suffix}.csv"
    write_kc_rates_csv(summary, payload, kc_rates_path)
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
    print(f"Per-KC rates CSV: {kc_rates_path}")


if __name__ == "__main__":
    main()
