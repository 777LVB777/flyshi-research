#!/usr/bin/env python3
"""Cross-platform check: re-simulate one saved Mac presentation on this machine and compare.

Pre-stated in docs/cloud/ccx33-run-plan.md, section 3, before any server run.

The presentation is the pool-identity control's reproducibility stimulus: the
left-only mirrored validation's price arm at v = 0.94, YES, seed 20260316. Its Mac
result is ``graded_left_mirrored_value_0p94_YES_seed_20260316.json``, and the Mac
re-simulated it identically on 2026-09-30 (``pool_identity_repro_check.json``).

It is simulated TWICE here, in one process, with the same seed. Readings:

- ``SERVER_NONDETERMINISTIC``: the two server runs differ. Restarted jobs and
  jobs run apart would then not reproduce. Do not start the sweep.
- ``IDENTICAL``: run 1 equals the Mac file exactly (every population's trial-mean
  and per-trial rates, and the population IDs).
- ``CONSISTENT_WITHIN_NOISE``: not identical, but every difference is at most the
  measured noise floor: the largest of the 15 pairwise differences between the six
  Mac seeds (20260316-20260321) of this same stimulus, for the CIRCUIT-80 per-type
  mean score and for each population's rate vector (Euclidean distance). The
  floors are recomputed here from the saved files, never typed in.
- ``INCONSISTENT``: any difference beyond its floor. Do not start the sweep.

Running without --dry-run builds the model and runs 2 real Brian2 simulations
(about 2 minutes). --dry-run reads saved files only and prints the floors.
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import sys
import time
from itertools import combinations
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from flyshi_research.learning.encoder import YES  # noqa: E402
from flyshi_research.learning.readout import circuit_score, load_sign_table  # noqa: E402

RESULTS_DIR = HERE / "results"
IDS_PATH = HERE / "neuron_ids_783.json"
VALUE, FRAMING, SEED = 0.94, YES, 20260316
MAC_SEEDS = (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
SIGN_TABLE, AGGREGATION = "circuit_80", "type_mean"
SCORE = "circuit80_type_mean_score"

IDENTICAL = "IDENTICAL"
WITHIN = "CONSISTENT_WITHIN_NOISE"
INCONSISTENT = "INCONSISTENT"
NONDETERMINISTIC = "SERVER_NONDETERMINISTIC"
ACTIONS = {
    IDENTICAL: "start the sweep; server results are bit-comparable with the Mac's",
    WITHIN: ("start the sweep; record that server and Mac differ within single-run noise; label "
             "any server-vs-Mac comparison 'across a platform change'"),
    INCONSISTENT: ("do NOT start the sweep; record the differences and the environment; "
                   "investigate before spending compute (see the run plan, section 3)"),
    NONDETERMINISTIC: ("do NOT start the sweep: the same seed gives different results on this "
                       "machine, so restarts and split arms would not reproduce"),
}


def mac_path(seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"graded_left_mirrored_value_0p94_YES_seed_{seed}.json"


def out_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"cross_platform_check_{socket.gethostname()}.json"


def score(payload: Mapping) -> float:
    table = load_sign_table(SIGN_TABLE)
    return float(circuit_score(np.asarray(payload["rates_hz"]["mbons"], dtype=float),
                               payload["mbon_labels"], table, AGGREGATION).score)


def distances(a: Mapping, b: Mapping) -> Dict[str, float]:
    """Euclidean distance per population, plus |score difference|."""
    out = {p: float(np.linalg.norm(np.asarray(a["rates_hz"][p], dtype=float)
                                   - np.asarray(b["rates_hz"][p], dtype=float)))
           for p in a["rates_hz"]}
    out[SCORE] = abs(score(a) - score(b))
    return out


def noise_floors(mac_seeds: Sequence[Mapping]) -> Dict[str, float]:
    """Largest of the pairwise seed-to-seed differences, per quantity."""
    pairs = [distances(a, b) for a, b in combinations(mac_seeds, 2)]
    return {k: max(d[k] for d in pairs) for k in pairs[0]}


def identical(a: Mapping, b: Mapping) -> bool:
    if a["population_ids"] != b["population_ids"] or set(a["rates_hz"]) != set(b["rates_hz"]):
        return False
    for key in ("rates_hz", "per_trial_rates_hz"):
        for p in a.get(key, {}):
            x, y = np.asarray(a[key][p], dtype=float), np.asarray(b[key].get(p, []), dtype=float)
            if x.shape != y.shape or not np.array_equal(x, y):
                return False
    return True


def max_abs_differences(a: Mapping, b: Mapping) -> Dict[str, Optional[float]]:
    out = {}
    for p in a["rates_hz"]:
        x, y = np.asarray(a["rates_hz"][p], dtype=float), np.asarray(b["rates_hz"][p], dtype=float)
        out[p] = float(np.max(np.abs(x - y))) if x.shape == y.shape else None
    return out


def classify(run1: Mapping, run2: Mapping, mac: Mapping, mac_seeds: Sequence[Mapping]) -> dict:
    floors = noise_floors(mac_seeds)
    server_vs_mac = distances(run1, mac)
    if not identical(run1, run2):
        reading = NONDETERMINISTIC
    elif identical(run1, mac):
        reading = IDENTICAL
    elif all(server_vs_mac[k] <= floors[k] for k in floors):
        reading = WITHIN
    else:
        reading = INCONSISTENT
    return {
        "reading": reading,
        "action": ACTIONS[reading],
        "server_runs_identical": identical(run1, run2),
        "max_abs_difference_hz": max_abs_differences(run1, mac),
        "server_vs_mac": server_vs_mac,
        "noise_floor": floors,
        "beyond_floor": sorted(k for k in floors if server_vs_mac[k] > floors[k]),
        "noise_floor_rule": "largest of the 15 pairwise differences between the six Mac seeds "
                            "of the same stimulus (score: |dS|; populations: Euclidean distance)",
    }


def load_mac(results_dir: Path = RESULTS_DIR) -> tuple:
    seeds = [json.loads(mac_path(s, results_dir).read_text()) for s in MAC_SEEDS]
    return seeds[MAC_SEEDS.index(SEED)], seeds


def simulate(ids_path: Path = IDS_PATH) -> tuple:
    """Two runs of the stimulus on this machine. Imports Brian2, builds the model."""
    import run_pool_identity_control as pi
    from run_left_only_realistic_drive_diagnostic import _present_with_trials
    from run_population_scaling_diagnostic import _build_population_simulator

    stim = pi.build_stimuli(ids_path)["by_value"][VALUE][FRAMING]["P"]
    mac, _ = load_mac()
    pi._check_saved(mac, stim, VALUE, FRAMING, SEED, "Mac file")  # same stimulus, or abort
    sim = _build_population_simulator()
    runs = []
    for _ in range(2):
        t0 = time.time()
        means, trials = _present_with_trials(sim, stim["rates_by_kc_id"], SEED,
                                             pi.DURATION_MS, pi.TRIALS)
        payload = pi._presentation_payload(sim, stim, means, trials, VALUE, FRAMING, SEED)
        payload["seconds"] = time.time() - t0
        runs.append(payload)
    return runs[0], runs[1]


def environment() -> dict:
    import subprocess
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    return {"hostname": socket.gethostname(), "platform": platform.platform(),
            "machine": platform.machine(), "python": platform.python_version(),
            "git_head": run(["git", "-C", str(HERE), "rev-parse", "HEAD"]),
            "gcc": (run(["g++", "--version"]) or "").split("\n")[0] or None,
            "pip_freeze": (run([sys.executable, "-m", "pip", "freeze"]) or "").splitlines()}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dry-run", action="store_true", help="Print the floors; simulate nothing.")
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    args = p.parse_args(argv)
    mac, seeds = load_mac(args.results_dir)
    floors = noise_floors(seeds)
    print(f"stimulus: v={VALUE} {FRAMING} seed {SEED}; Mac file {mac_path(SEED, args.results_dir).name}")
    print("noise floors (largest Mac seed-to-seed difference): "
          + ", ".join(f"{k} {v:.2f} Hz" for k, v in floors.items()))
    if args.dry_run:
        print("dry run: nothing simulated, nothing written.")
        return 0
    out = out_path(args.results_dir)
    if out.exists():
        print(f"Output exists, skipping: {out.name} (delete it to re-check)")
        result = json.loads(out.read_text())
    else:
        run1, run2 = simulate()
        result = {"kind": "cross_platform_check", "spec": "docs/cloud/ccx33-run-plan.md section 3",
                  "presentation": {"value": VALUE, "framing": FRAMING, "seed": SEED},
                  "environment": environment(),
                  "seconds_per_simulation": [run1.pop("seconds"), run2.pop("seconds")],
                  **classify(run1, run2, mac, seeds), "server_run": run1}
        out.write_text(json.dumps(result, separators=(",", ":")))
    print(f"reading: {result['reading']}")
    print("server vs Mac: " + ", ".join(f"{k} {v:.4g}" for k, v in result["server_vs_mac"].items()))
    if result["beyond_floor"]:
        print(f"beyond the floor: {', '.join(result['beyond_floor'])}")
    print(f"action (pre-stated): {result['action']}")
    print(f"wrote {out}")
    return 0 if result["reading"] in (IDENTICAL, WITHIN) else 1


if __name__ == "__main__":
    sys.exit(main())
