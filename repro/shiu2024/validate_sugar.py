"""Full default-parameter sugar-validation run for the Shiu et al. model."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from time import perf_counter

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_ROOT = REPOSITORY_ROOT / "third_party" / "Drosophila_brain_model"
sys.path.insert(0, str(UPSTREAM_ROOT))

from brian2 import seed  # noqa: E402
from model import default_params, run_exp  # noqa: E402
import utils as utl  # noqa: E402


SUGAR_GUSTATORY_NEURONS = [
    720575940624963786, 720575940630233916, 720575940637568838,
    720575940638202345, 720575940617000768, 720575940630797113,
    720575940632889389, 720575940621754367, 720575940621502051,
    720575940640649691, 720575940639332736, 720575940616885538,
    720575940639198653, 720575940620900446, 720575940617937543,
    720575940632425919, 720575940633143833, 720575940612670570,
    720575940628853239, 720575940629176663, 720575940611875570,
]
READOUTS = {
    "MN9_left_contralateral": 720575940660219265,
    "MN9_right_ipsilateral": 720575940645521262,
}
SEED = 20260316
EXPERIMENT_NAME = "sugar_default"


def run_once(output_dir: Path) -> tuple[object, float, int]:
    """Run upstream defaults once and return rates, runtime, and spike count."""
    np.random.seed(SEED)
    seed(SEED)
    start = perf_counter()
    run_exp(
        exp_name=EXPERIMENT_NAME,
        neu_exc=SUGAR_GUSTATORY_NEURONS,
        path_res=output_dir,
        path_comp=UPSTREAM_ROOT / "2023_03_23_completeness_630_final.csv",
        path_con=UPSTREAM_ROOT / "2023_03_23_connectivity_630_final.parquet",
        params=default_params,
        n_proc=1,
    )
    runtime = perf_counter() - start
    spikes = utl.load_exps([output_dir / f"{EXPERIMENT_NAME}.parquet"])
    rates, _ = utl.get_rate(spikes, default_params["t_run"], default_params["n_run"])
    return rates, runtime, len(spikes)


def rate_or_zero(rates: object, flywire_id: int) -> float:
    """Read a rate from a sparse upstream output table."""
    column = EXPERIMENT_NAME
    return float(rates.loc[flywire_id, column]) if flywire_id in rates.index else 0.0


def main() -> None:
    """Run two seeded full-default repetitions and compare rate tables exactly."""
    with tempfile.TemporaryDirectory(prefix="flyshi-shiu-validation-") as temp_dir:
        root = Path(temp_dir)
        first_output, second_output = root / "first", root / "second"
        first_output.mkdir()
        second_output.mkdir()
        first_rates, first_runtime, first_spikes = run_once(first_output)
        second_rates, second_runtime, second_spikes = run_once(second_output)

    first_full = first_rates.reindex(columns=[EXPERIMENT_NAME]).fillna(0).sort_index()
    second_full = second_rates.reindex(columns=[EXPERIMENT_NAME]).fillna(0).sort_index()
    deterministic = first_full.equals(second_full) and first_spikes == second_spikes
    downstream = first_full.drop(index=SUGAR_GUSTATORY_NEURONS, errors="ignore")
    top_downstream = downstream.sort_values(EXPERIMENT_NAME, ascending=False).head(10)

    print("VALIDATION_PARAMETERS")
    print("TRIAL_DURATION_MS=1000")
    print("TRIAL_COUNT=30")
    print("STIMULATION_RATE_HZ=150")
    print(f"SEED={SEED}")
    print(f"FIRST_RUNTIME_SECONDS={first_runtime:.3f}")
    print(f"SECOND_RUNTIME_SECONDS={second_runtime:.3f}")
    print(f"FIRST_SPIKE_COUNT={first_spikes}")
    print(f"SECOND_SPIKE_COUNT={second_spikes}")
    print(f"IDENTICAL_SEEDED_RESULTS={deterministic}")
    print("READOUT_RATES_HZ")
    for name, flywire_id in READOUTS.items():
        print(f"{name}\t{flywire_id}\t{rate_or_zero(first_full, flywire_id):.6f}")
    print("TOP_DOWNSTREAM_NEURONS_HZ")
    for flywire_id, row in top_downstream.iterrows():
        print(f"{flywire_id}\t{row[EXPERIMENT_NAME]:.6f}")


if __name__ == "__main__":
    main()
