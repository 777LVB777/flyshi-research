"""Analysis-only: check run_cue_rates (uniform-rate case, produced by
run_rates_uniform_check.py) against the existing-path cue-A reference data, at
the SAME pre-stated criteria as the run_cue equivalence test in
docs/design/fast-runner.md, section 4 (which is already ACCEPTED -- git commit
`6a00cdd` -- for the SCALAR-rate entry point, run_cue). This script checks the
still-unverified PER-NEURON-rate entry point, run_cue_rates, which is what the
learning code actually calls.

No simulation. Reads existing CSVs only.

Old path (reference, unchanged from the run_cue check):
  mbon_noise_floor_cue_a_duration_ms_1000_trials_5_..._seed_S.csv
New path (this check, run_cue_rates with every cue-A KC at the same 150 Hz):
  fast_rates_mbon_cue_a_duration_ms_1000_trials_5_..._seed_S.csv
Existing cue-B (for the sign check): the 1000/5 kc_set_b column of the speed
calibration MBON-rate CSV (seed 20260316) -- same as the run_cue check.

Bonus, NON-GATING diagnostic (not one of the two pre-stated criteria): also
compares run_cue_rates' output directly against the ALREADY-ACCEPTED run_cue
fast-path output (fast_mbon_cue_a_...), which used the same seeds and the same
150 Hz scalar rate. If run_cue_rates truly reduces to run_cue when every rate
is equal, this distance should be ~0 Hz (same weights, same seeding, same
per-trial reset -- the only implementation difference is a per-neuron rate
vector with all-equal entries vs. a scalar broadcast). This diagnostic cannot
by itself change the ACCEPTED/NOT ACCEPTED verdict below, which is decided
only by criteria 1 and 2 against the old-path reference, exactly as for run_cue.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RES = Path(__file__).resolve().parent / "results"
CALIB = RES / "speed_calibration_mbon_rates_kc_size_100_kc_seed_20260316_pn_rate_hz_150_seed_20260316.csv"

DUR, TRI, RATE = 1000.0, 5, 150.0
SEEDS = [20260317, 20260318, 20260319, 20260320, 20260321]
D_AA_NOISE_FLOOR = 5.10  # Hz, from docs/design/mbon-separability.md (measured same-cue noise)

# 8 consistent discriminators and their established sign of (mean cue A - cue B),
# from docs/design/mbon-separability.md §1. Same table as compare_equivalence.py.
DISCRIMINATORS = {
    720575940624590316: ("MBON03", -1),
    720575940617552340: ("MBON02", +1),
    720575940652390134: ("MBON07", -1),
    720575940617302365: ("MBON07", -1),
    720575940628734376: ("MBON04", -1),
    720575940629981440: ("MBON26", -1),
    720575940623201833: ("MBON11", +1),
    720575940617567206: ("MBON23", -1),
}


def old_path_csv(seed: int) -> Path:
    return RES / (f"mbon_noise_floor_cue_a_duration_ms_{DUR:g}_trials_{TRI}"
                  f"_pn_rate_hz_150_kc_size_100_kc_seed_20260316_seed_{seed}.csv")


def rates_new_csv(seed: int) -> Path:
    """run_cue_rates output (this check): every cue-A KC given the SAME rate."""
    return RES / (f"fast_rates_mbon_cue_a_duration_ms_{DUR:g}_trials_{TRI}"
                  f"_pn_rate_hz_{RATE:g}_kc_size_100_kc_seed_20260316_seed_{seed}.csv")


def scalar_new_csv(seed: int) -> Path:
    """run_cue output (already ACCEPTED, commit 6a00cdd): the bonus diagnostic target."""
    return RES / (f"fast_mbon_cue_a_duration_ms_{DUR:g}_trials_{TRI}"
                  f"_pn_rate_hz_{RATE:g}_kc_size_100_kc_seed_20260316_seed_{seed}.csv")


def rates(path: Path) -> dict[int, float]:
    df = pd.read_csv(path)
    return dict(zip(df.root_id.astype(int), df.rate_hz.astype(float)))


def cueB_rates() -> dict[int, float]:
    df = pd.read_csv(CALIB)
    sub = df[(df.duration_ms == DUR) & (df.trials == TRI) & (df.condition == "kc_set_b")]
    return dict(zip(sub.root_id.astype(int), sub.rate_hz.astype(float)))


def euclid(a: dict, b: dict) -> float:
    support = sorted(set(a) | set(b))
    va = np.array([a.get(i, 0.0) for i in support])
    vb = np.array([b.get(i, 0.0) for i in support])
    return float(np.linalg.norm(va - vb))


def main() -> None:
    seeds_present = [s for s in SEEDS if old_path_csv(s).exists() and rates_new_csv(s).exists()]
    missing = [s for s in SEEDS if s not in seeds_present]
    print(f"seeds with BOTH old-path reference & run_cue_rates output: {seeds_present}")
    if missing:
        print(f"seeds still missing a run_cue_rates output: {missing}")
    if not seeds_present:
        print("\nNo run_cue_rates outputs yet. Run run_rates_uniform_check.py for these seeds "
              "first (see docs/design/fast-runner.md, section 6), then re-run this.")
        return

    # (1) mean Euclidean distance between old-path and run_cue_rates MBON rate vectors
    dists = []
    print("\nPer-seed old-path-vs-run_cue_rates MBON-rate Euclidean distance:")
    for s in seeds_present:
        d = euclid(rates(old_path_csv(s)), rates(rates_new_csv(s)))
        dists.append(d)
        print(f"  seed {s}: {d:.3f} Hz")
    mean_d = float(np.mean(dists))
    print(f"\nmean old-path-vs-run_cue_rates distance = {mean_d:.3f} Hz")
    print(f"pre-stated tolerance (noise floor d_AA) = {D_AA_NOISE_FLOOR:.2f} Hz")
    crit1 = mean_d <= D_AA_NOISE_FLOOR
    print(f"CRITERION 1 (mean distance <= {D_AA_NOISE_FLOOR:.2f}): {'PASS' if crit1 else 'FAIL'}")

    # (2) all 8 discriminators keep the same sign of (cue A - cue B) under run_cue_rates
    B = cueB_rates()
    newA_mean = {}
    for rid in DISCRIMINATORS:
        vals = [rates(rates_new_csv(s)).get(rid, 0.0) for s in seeds_present]
        newA_mean[rid] = float(np.mean(vals))
    print("\nSign check on the 8 discriminators (run_cue_rates mean cue A vs existing cue B):")
    n_ok = 0
    for rid, (label, established) in DISCRIMINATORS.items():
        diff = newA_mean[rid] - B.get(rid, 0.0)
        obs = int(np.sign(diff))
        ok = (obs == established)
        n_ok += ok
        print(f"  {label} (…{rid % 100000:05d}): meanA_new={newA_mean[rid]:6.1f} "
              f"B={B.get(rid,0.0):6.1f} diff={diff:+6.1f} "
              f"sign={obs:+d} established={established:+d} {'ok' if ok else 'MISMATCH'}")
    crit2 = n_ok == len(DISCRIMINATORS)
    print(f"CRITERION 2 (all 8 signs match): {n_ok}/8 -> {'PASS' if crit2 else 'FAIL'}")

    print("\n=== run_cue_rates EQUIVALENCE VERDICT (vs. existing-path cue-A reference) ===")
    if crit1 and crit2:
        print("ACCEPTED: run_cue_rates (uniform-rate case) is equivalent to the existing path "
              "within the pre-stated bounds.")
    else:
        print("NOT ACCEPTED: at least one pre-stated criterion failed (see above).")

    # --- Bonus, NON-GATING diagnostic: run_cue_rates vs. the already-accepted run_cue output ---
    scalar_present = [s for s in seeds_present if scalar_new_csv(s).exists()]
    print("\n--- Bonus diagnostic (does not affect the verdict above) ---")
    if not scalar_present:
        print("No matching run_cue (scalar-path) outputs found to cross-check against; skipping.")
        return
    print(f"seeds with both run_cue_rates and run_cue outputs: {scalar_present}")
    bonus_dists = []
    for s in scalar_present:
        d = euclid(rates(rates_new_csv(s)), rates(scalar_new_csv(s)))
        bonus_dists.append(d)
        print(f"  seed {s}: run_cue_rates vs run_cue distance = {d:.3f} Hz")
    print(f"mean run_cue_rates-vs-run_cue distance = {float(np.mean(bonus_dists)):.3f} Hz "
          "(expected to be ~0 Hz if run_cue_rates reduces to run_cue at equal rates; "
          "this is a diagnostic only, not one of the two pre-stated criteria).")


if __name__ == "__main__":
    main()
