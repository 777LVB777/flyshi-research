"""Analysis-only: check fast_runner (new path) against the existing path on the
same cue/seeds/settings, per the pre-stated criteria in docs/design/fast-runner.md.
No simulation. Reads existing CSVs only.

Old path (reference): mbon_noise_floor_cue_a_duration_ms_1000_trials_5_..._seed_S.csv
New path (fast):       fast_mbon_cue_a_duration_ms_1000_trials_5_..._seed_S.csv
Existing cue-B (for the sign check): the 1000/5 kc_set_b column of the speed
calibration MBON-rate CSV (seed 20260316).
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RES = Path(__file__).resolve().parent / "results"
CALIB = RES / "speed_calibration_mbon_rates_kc_size_100_kc_seed_20260316_pn_rate_hz_150_seed_20260316.csv"

DUR, TRI = 1000.0, 5
SEEDS = [20260317, 20260318, 20260319, 20260320, 20260321]
D_AA_NOISE_FLOOR = 5.10  # Hz, from docs/design/mbon-separability.md (measured same-cue noise)

# 8 consistent discriminators and their established sign of (mean cue A - cue B),
# from docs/design/mbon-separability.md §1.
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


def new_path_csv(seed: int) -> Path:
    return RES / (f"fast_mbon_cue_a_duration_ms_{DUR:g}_trials_{TRI}"
                  f"_pn_rate_hz_150_kc_size_100_kc_seed_20260316_seed_{seed}.csv")


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
    seeds_present = [s for s in SEEDS if old_path_csv(s).exists() and new_path_csv(s).exists()]
    missing = [s for s in SEEDS if s not in seeds_present]
    print(f"seeds with BOTH old & new CSV: {seeds_present}")
    if missing:
        print(f"seeds still missing a new-path (fast) CSV: {missing}")
    if not seeds_present:
        print("\nNo fast-path outputs yet. Run fast_runner.py for these seeds first "
              "(see docs/design/fast-runner.md), then re-run this.")
        return

    # (1) mean Euclidean distance between old-path and new-path MBON rate vectors
    dists = []
    print("\nPer-seed old-vs-new MBON-rate Euclidean distance:")
    for s in seeds_present:
        d = euclid(rates(old_path_csv(s)), rates(new_path_csv(s)))
        dists.append(d)
        print(f"  seed {s}: {d:.3f} Hz")
    mean_d = float(np.mean(dists))
    print(f"\nmean old-vs-new distance = {mean_d:.3f} Hz")
    print(f"pre-stated tolerance (noise floor d_AA) = {D_AA_NOISE_FLOOR:.2f} Hz")
    crit1 = mean_d <= D_AA_NOISE_FLOOR
    print(f"CRITERION 1 (mean distance <= {D_AA_NOISE_FLOOR:.2f}): {'PASS' if crit1 else 'FAIL'}")

    # (2) all 8 discriminators keep the same sign of (cue A - cue B) under the new path
    B = cueB_rates()
    newA_mean = {}
    for rid in DISCRIMINATORS:
        vals = [rates(new_path_csv(s)).get(rid, 0.0) for s in seeds_present]
        newA_mean[rid] = float(np.mean(vals))
    print("\nSign check on the 8 discriminators (new-path mean cue A vs existing cue B):")
    n_ok = 0
    for rid, (label, established) in DISCRIMINATORS.items():
        diff = newA_mean[rid] - B.get(rid, 0.0)
        obs = int(np.sign(diff))
        ok = (obs == established)  # sign of (cue A - cue B) must match the established direction
        n_ok += ok
        print(f"  {label} (…{rid % 100000:05d}): meanA_new={newA_mean[rid]:6.1f} "
              f"B={B.get(rid,0.0):6.1f} diff={diff:+6.1f} "
              f"sign={obs:+d} established={established:+d} {'ok' if ok else 'MISMATCH'}")
    crit2 = n_ok == len(DISCRIMINATORS)
    print(f"CRITERION 2 (all 8 signs match): {n_ok}/8 -> {'PASS' if crit2 else 'FAIL'}")

    print("\n=== EQUIVALENCE VERDICT ===")
    if crit1 and crit2:
        print("ACCEPTED: new path is equivalent to the existing path within the pre-stated bounds.")
    else:
        print("NOT ACCEPTED: at least one pre-stated criterion failed (see above).")
    print("\n(Speedup is reported by fast_runner.py's own build/sim timing vs the "
          "~28 s/run existing-path baseline; see docs/design/fast-runner.md.)")


if __name__ == "__main__":
    main()
