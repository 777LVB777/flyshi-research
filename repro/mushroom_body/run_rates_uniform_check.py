"""Per-neuron-rate path (`run_cue_rates`) equivalence check, uniform-rate case.

Why this exists (see docs/design/fast-runner.md, section 6, and its "Unverified"
note): the fast-runner equivalence test that was run and ACCEPTED (git commit
`6a00cdd`) exercised `run_cue`, the SCALAR-rate entry point. Our learning code
calls `run_cue_rates`, the PER-NEURON-rate entry point (`Stimulus.rates_by_kc_id()`
in the encoder), which has never executed a real `net.run`. `run_cue_rates` is
mathematically expected to reduce to `run_cue` when every stimulated neuron is
given the SAME rate, because `_apply_trial_state` builds one dense per-neuron
rate vector either way (see `rate_vector` in fast_runner.py) -- but that has not
been checked against the real model.

This script stimulates cue A's full 100-KC pool through `run_cue_rates`, giving
EVERY one of those 100 KCs the identical 150 Hz rate (rather than one scalar
argument), and saves per-MBON rates in the same CSV schema `fast_runner.py`
uses, under a name that cannot collide with the existing `fast_mbon_cue_a_*`
(run_cue) files: `fast_rates_mbon_cue_a_...`.

Comparison against the existing cue-A reference data (same pre-stated tolerance
as the run_cue equivalence test: mean distance <= 5.10 Hz, and the same 8
discriminator signs) is done separately, with no simulation, by
`compare_rates_equivalence.py`.

This module only prepares the check. RUNNING IT IS A SIMULATION -- run it
yourself in a normal terminal (see --help / the command below), not inside an
agent session.
"""
from __future__ import annotations

import argparse
import csv

import check_mb_response as mbr
from fast_runner import build_network, run_cue_rates, mbon_rates, default_params
from brian2 import Hz, ms


def parser() -> argparse.ArgumentParser:
    example = (
        "uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_rates_uniform_check.py "
        "--seed 20260317 --duration-ms 1000 --trials 5"
    )
    p = argparse.ArgumentParser(
        description=(
            "Equivalence check for run_cue_rates (per-neuron rate map), uniform-rate "
            "case: every KC in cue A's pool is given the SAME rate (default 150 Hz), "
            "which run_cue_rates should treat identically to run_cue's scalar path. "
            "Compares against the existing cue-A reference data at the pre-stated "
            "5.10 Hz tolerance and the 8-discriminator sign check "
            "(see docs/design/fast-runner.md, section 6, and compare_rates_equivalence.py)."
        ),
        epilog=f"Example:\n  {example}\n\nRuns a Brian2 simulation; on macOS use `caffeinate -i`.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--seed", type=int, required=True,
                    help="Base simulation seed (Brian2/NumPy). Use the same 5 seeds as the "
                         "run_cue equivalence test: 20260317-20260321.")
    p.add_argument("--duration-ms", type=float, default=1000.0, help="Trial duration in ms (default: 1000).")
    p.add_argument("--trials", type=int, default=5, help="Trials per run (default: 5).")
    p.add_argument("--rate", type=float, default=150.0,
                    help="The SAME rate (Hz) given to every KC in cue A's pool (default: 150, "
                         "matching the run_cue equivalence test).")
    p.add_argument("--kc-set-size", type=int, default=100, help="KC set size per cue (default: 100).")
    p.add_argument("--kc-set-seed", type=int, default=20260316,
                    help="Seed selecting the disjoint KC sets (default: 20260316).")
    return p


def output_path(args: argparse.Namespace):
    name = (
        f"fast_rates_mbon_cue_a"
        f"_duration_ms_{args.duration_ms:g}_trials_{args.trials}"
        f"_pn_rate_hz_{args.rate:g}"
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

    params = default_params.copy()
    params["t_run"] = args.duration_ms * ms
    params["n_run"] = args.trials
    params["r_poi"] = args.rate * Hz  # not used by run_cue_rates itself; kept for parity with run_cue's params

    payload = mbr.read_ids()
    set_a, _set_b = mbr.select_disjoint_kc_sets(
        payload["kenyon_cells"]["records"], args.kc_set_size, args.kc_set_seed
    )
    # The one thing this script changes relative to fast_runner.py's run_cue path:
    # every id in cue A's pool gets an EXPLICIT per-neuron entry in the rate map,
    # all set to the SAME value, instead of one scalar passed to run_cue.
    rates_by_flyid = {int(fid): args.rate for fid in set_a}
    exp_name = "kc_set_a_rates_uniform"

    bundle = build_network(params, mbr.UPSTREAM_ROOT / "Completeness_783.csv",
                           mbr.UPSTREAM_ROOT / "Connectivity_783.parquet")
    spikes, timing = run_cue_rates(bundle, rates_by_flyid, args.trials, args.seed, exp_name)
    rows = mbon_rates(spikes, payload, params, exp_name)

    mbr.RESULTS_DIR.mkdir(exist_ok=True)
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["seed", "duration_ms", "trials", "cue", "root_id", "cell_type", "side", "rate_hz"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({"seed": args.seed, "duration_ms": args.duration_ms,
                             "trials": args.trials, "cue": "a", **row})

    b = timing["build_seconds"]; s = timing["sim_seconds_total"]
    print(f"cue a (run_cue_rates, uniform {args.rate:g} Hz) @ seed {args.seed}, "
          f"{args.duration_ms:g}ms x {args.trials} trials (FAST path, per-neuron-rate entry point):")
    print(f"  build once = {b:.1f}s ; simulate = {s:.1f}s total "
          f"({', '.join(f'{x:.1f}' for x in timing['sim_seconds_per_trial'])} per trial)")
    print(f"  {len(rows)} nonzero MBONs. Wrote {out_path}")
    print(f"  [timing] build_seconds={b:.3f} sim_seconds_total={s:.3f}")


if __name__ == "__main__":
    main()
