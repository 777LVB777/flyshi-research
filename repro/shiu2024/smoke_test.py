"""Minimal FlyWire v630 sugar-gustatory smoke test for Shiu et al. (2024)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from time import perf_counter

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_ROOT = REPOSITORY_ROOT / "third_party" / "Drosophila_brain_model"
sys.path.insert(0, str(UPSTREAM_ROOT))

from brian2 import ms, prefs  # noqa: E402
from model import default_params, run_exp  # noqa: E402
import utils as utl  # noqa: E402


SUGAR_GUSTATORY_NEURONS = [
    720575940624963786,
    720575940630233916,
    720575940637568838,
    720575940638202345,
    720575940617000768,
    720575940630797113,
    720575940632889389,
    720575940621754367,
    720575940621502051,
    720575940640649691,
    720575940639332736,
    720575940616885538,
    720575940639198653,
    720575940620900446,
    720575940617937543,
    720575940632425919,
    720575940633143833,
    720575940612670570,
    720575940628853239,
    720575940629176663,
    720575940611875570,
]


def main() -> None:
    """Run two short trials; neural and stimulation defaults remain unchanged."""
    params = default_params.copy()
    params["t_run"] = 10 * ms
    params["n_run"] = 2

    with tempfile.TemporaryDirectory(prefix="flyshi-shiu-smoke-") as temp_dir:
        output_dir = Path(temp_dir) / "results"
        output_dir.mkdir()
        start = perf_counter()
        run_exp(
            exp_name="sugar_gustatory_smoke",
            neu_exc=SUGAR_GUSTATORY_NEURONS,
            path_res=output_dir,
            path_comp=UPSTREAM_ROOT / "2023_03_23_completeness_630_final.csv",
            path_con=UPSTREAM_ROOT / "2023_03_23_connectivity_630_final.parquet",
            params=params,
            n_proc=1,
        )
        elapsed_seconds = perf_counter() - start

        spikes = utl.load_exps([output_dir / "sugar_gustatory_smoke.parquet"])
        rates, _ = utl.get_rate(spikes, t_run=params["t_run"], n_run=params["n_run"])
        top = rates.sort_values("sugar_gustatory_smoke", ascending=False).head(10)

    print(f"BRIAN2_CODEGEN_TARGET={prefs.codegen.target}")
    print("TRIAL_DURATION_MS=10")
    print("TRIAL_COUNT=2")
    print(f"RUNTIME_SECONDS={elapsed_seconds:.3f}")
    print(f"SPIKE_COUNT={len(spikes)}")
    print("TOP_RESPONDING_NEURONS_HZ")
    for flywire_id, row in top.iterrows():
        print(f"{flywire_id}\t{row['sugar_gustatory_smoke']:.6f}")


if __name__ == "__main__":
    main()
