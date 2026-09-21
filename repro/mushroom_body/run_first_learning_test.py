"""First learning test: does the circuit learn that cue A is rewarded and cue B is not?

Pre-stated spec: docs/design/first-learning-test.md (written before this code and
before any run). Experiment logic and verdict: flyshi_research.learning.first_learning
(pure numpy, tested on fake simulators). This file adds only the real simulator
backend (fast_runner's per-neuron-rate path) and the command line.

RUNNING THIS WITHOUT --dry-run EXECUTES BRIAN2 SIMULATIONS (about 260 runs at the
placeholder N = 40) and loads the full connectome. Run it yourself; on macOS use
`caffeinate -i`. It depends on the fast runner, whose equivalence test against the
existing path HAS NOT BEEN RUN, and on run_cue_rates, which has never executed a
real net.run (docs/design/fast-runner.md).

Restartable: completed stages are skipped; an interrupted training stage resumes
from its per-presentation checkpoint.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Mapping, Tuple

import numpy as np

from flyshi_research.learning import first_learning as fl

HERE = Path(__file__).resolve().parent
RESULTS_BASE = HERE / "results"


# --------------------------------------------------------------------------- #
# real backend (lazy Brian2 imports; never constructed by --dry-run or the tests)
# --------------------------------------------------------------------------- #
class FastRunnerSimulator:
    """fl.Simulator on the real model via fast_runner.build_network/run_cue_rates."""

    def __init__(self, cfg: fl.ExperimentConfig) -> None:
        sys.path.insert(0, str(HERE))
        import check_mb_response as mbr  # noqa: E402  (imports Brian2 + upstream model)
        import fast_runner as fr  # noqa: E402
        from brian2 import ms, volt  # noqa: E402
        from model import default_params  # noqa: E402

        self._fr, self._ms, self._volt = fr, ms, volt
        payload = mbr.read_ids()
        kcs = payload["kenyon_cells"]["records"]
        mbons = payload["mbons"]["records"]
        self.kc_ids = [int(r["root_id"]) for r in kcs]
        self.mbon_ids = [int(r["root_id"]) for r in mbons]
        self.mbon_labels = [r["cell_type"] for r in mbons]
        set_a, set_b = mbr.select_disjoint_kc_sets(kcs, cfg.kc_set_size, cfg.kc_set_seed)
        self.cue_sets = {fl.CUE_A: set_a, fl.CUE_B: set_b}

        params = default_params.copy()
        self.bundle = fr.build_network(params, mbr.UPSTREAM_ROOT / "Completeness_783.csv",
                                       mbr.UPSTREAM_ROOT / "Connectivity_783.parquet")
        flyid2i = self.bundle["flyid2i"]
        kc_idx = np.array([flyid2i[k] for k in self.kc_ids])
        mbon_idx = np.array([flyid2i[m] for m in self.mbon_ids])
        self._kc_brian = kc_idx
        self._mbon_brian = mbon_idx

        # KC->MBON synapses: one Brian2 synapse per connectivity row (upstream create_model).
        syn = self.bundle["syn"]
        pre = np.asarray(syn.i[:])
        post = np.asarray(syn.j[:])
        kc_row = np.full(self.bundle["n"], -1)
        kc_row[kc_idx] = np.arange(len(kc_idx))
        mbon_col = np.full(self.bundle["n"], -1)
        mbon_col[mbon_idx] = np.arange(len(mbon_idx))
        sel = np.flatnonzero((kc_row[pre] >= 0) & (mbon_col[post] >= 0))
        self._syn_idx = sel
        self._rows = kc_row[pre[sel]]
        self._cols = mbon_col[post[sel]]
        if len(set(zip(self._rows.tolist(), self._cols.tolist()))) != sel.size:
            raise RuntimeError("duplicate KC->MBON synapses for one pair; dense matrix cannot represent them")
        W0 = np.zeros((len(kc_idx), len(mbon_idx)))
        W0[self._rows, self._cols] = np.asarray(syn.w[:])[sel]  # volts, units stripped
        # (a zero-weight synapse simply stays 0 under the rule: floor and drift target are 0)
        self._W0 = W0
        print(f"[backend] {sel.size} KC->MBON synapses; build {self.bundle['build_seconds']:.1f}s")

    def baseline_weights(self) -> np.ndarray:
        return self._W0.copy()

    def set_weights(self, weights: np.ndarray) -> None:
        # run_cue_rates saves and re-applies syn.w across its restore(), so this persists.
        self.bundle["syn"].w[self._syn_idx] = np.asarray(weights)[self._rows, self._cols] * self._volt

    def present(self, rates_by_kc_id: Mapping[int, float], seed: int,
                duration_ms: float, n_trials: int) -> Tuple[np.ndarray, np.ndarray]:
        self.bundle["params"]["t_run"] = duration_ms * self._ms
        spikes, _ = self._fr.run_cue_rates(self.bundle, dict(rates_by_kc_id), n_trials, seed, "cue")
        counts = np.bincount(np.array([self.bundle["flyid2i"][f] for f in spikes["flywire_id"]], dtype=int),
                             minlength=self.bundle["n"]) if len(spikes) else np.zeros(self.bundle["n"])
        # mean over trials of count/duration == utils.get_rate's per-trial mean
        rate = counts / (duration_ms / 1000.0 * n_trials)
        return rate[self._kc_brian], rate[self._mbon_brian]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def plan_lines(cfg: fl.ExperimentConfig, results_base: Path) -> list:
    rc = fl.run_count(cfg)
    d = fl.results_dir_for(results_base, cfg)
    order = fl.training_order(cfg)
    lines = [
        "First learning test: PLAN (dry run; nothing is simulated)",
        f"  pre-stated test: {cfg.prestated}   config hash: {cfg.config_hash()}   results: {d}",
        f"  cues: 2 x {cfg.kc_set_size} KCs (kc-set-seed {cfg.kc_set_seed}) at {cfg.cue_rate_hz:g} Hz",
        f"  test seeds: {list(cfg.test_seeds)}  ({cfg.test_duration_ms:g} ms x {cfg.test_trials} trials)",
        f"  training: N = {cfg.n_training} ({cfg.train_duration_ms:g} ms x {cfg.train_trials} trial), "
        f"order seed {cfg.order_seed}, seeds {cfg.train_seed_base}..{cfg.train_seed_base + cfg.n_training - 1}",
        f"  order: {''.join(order)}",
        "  conditions:",
    ]
    for c in fl.CONDITIONS:
        done = (d / f"condition_{c.name}.json").exists()
        ck = (d / f"checkpoint_{c.name}.npz").exists()
        lines.append(f"    {c.name:18s} {c.description}{'  [done]' if done else '  [checkpoint]' if ck else ''}")
    lines += [
        f"  plasticity (placeholders): {cfg.plasticity}",
        f"  reward strength {cfg.reward_strength:g}; recorded PAM rate "
        f"{cfg.reward_strength * cfg.reward.dopamine_max_rate_hz:g} Hz (UNANCHORED, not simulated)",
        "  ESTIMATED SIMULATION RUNS:",
        f"    pre-training test (shared): {rc.pretest}",
        f"    per condition: {rc.per_condition_training} training + {rc.per_condition_posttest} post-test",
        f"    total: {rc.pretest} + {rc.n_conditions} x {rc.per_condition_training + rc.per_condition_posttest}"
        f" = {rc.total} runs ({rc.simulated_trial_seconds(cfg):g} simulated trial-seconds) + 1 network build",
        "  Wall-clock time: unknown (local timings unusable).",
        "  DEPENDS ON the fast runner, whose equivalence test has NOT been run.",
    ]
    return lines


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="First learning test (see docs/design/first-learning-test.md).",
        epilog=("Full pre-stated run (Brian2; use caffeinate -i):\n"
                "  caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- \\\n"
                "    .venv-shiu/bin/python repro/mushroom_body/run_first_learning_test.py\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dry-run", action="store_true", help="Print the plan and run-count estimate; simulate nothing.")
    p.add_argument("--smoke", action="store_true", help="Tiny pipeline check (NOT the pre-stated test).")
    p.add_argument("--results-base", type=Path, default=RESULTS_BASE)
    return p


def main(argv=None) -> None:
    args = parser().parse_args(argv)
    cfg = fl.ExperimentConfig.smoke() if args.smoke else fl.ExperimentConfig()
    if args.dry_run:
        print("\n".join(plan_lines(cfg, args.results_base)))
        return
    sim = FastRunnerSimulator(cfg)
    verdict = fl.Experiment(sim, cfg, args.results_base).run()
    print("\n".join(fl.summary_lines(verdict)))


if __name__ == "__main__":
    main()
