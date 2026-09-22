from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from flyshi_research.learning.bias_mitigation import (  # noqa: E402
    INNATE_SCORE_SUBTRACTION,
    TOTAL_DRIVE_BALANCING,
)
from flyshi_research.learning.params import PlasticityParams  # noqa: E402
from flyshi_research.learning.encoder import KCEncoder  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO / "repro" / "mushroom_body" / "run_synthetic_market_experiment.py"
LAUNCHER_PATH = REPO / "repro" / "mushroom_body" / "launch_synthetic_market_parallel.py"


class FakeMarketSimulator:
    """Two-output linear fake whose output either does or does not see learned weights."""

    def __init__(self, sensitive: bool = True) -> None:
        self.kc_ids = [900000000000000000 + i for i in range(900)]
        self.mbon_ids = [800000000000000001, 800000000000000002]
        self.mbon_labels = ["MBON11", "MBON05"]  # approach-like, avoidance-like
        self._index = {kc_id: i for i, kc_id in enumerate(self.kc_ids)}
        self._W0 = np.ones((len(self.kc_ids), 2), dtype=float)
        self._W = self._W0.copy()
        self.sensitive = sensitive
        self._learned = False
        self._signal_ids = set(KCEncoder(self.kc_ids).pools["signal"].tolist())
        self.present_calls = 0

    def baseline_weights(self):
        return self._W0.copy()

    def set_weights(self, weights):
        self._W = np.asarray(weights).copy() if self.sensitive else self._W0.copy()
        self._learned = self.sensitive and not np.array_equal(self._W, self._W0)

    def present(self, rates, seed, duration_ms, n_trials):
        del duration_ms
        self.present_calls += 1
        kc = np.zeros(len(self.kc_ids))
        for kc_id, rate in rates.items():
            kc[self._index[kc_id]] = rate
        drive = 0.002 * kc @ self._W
        # Equal built-in intensity term in both outputs: it cancels only when
        # framings have equal total drive or exact innate scores are subtracted.
        intensity = 0.0005 * kc.sum()
        rng = np.random.default_rng(seed)
        noise = rng.normal(0.0, 0.002 / np.sqrt(n_trials), 2)
        # Deliberately learnable fake: once a real weight update reaches output,
        # it exposes the signal pool in the correct signed direction. The
        # no-learning fake can never activate this term.
        signal_rate = np.mean([rates.get(kc_id, 0.0) for kc_id in self._signal_ids])
        semantic = 20.0 * (signal_rate - 90.0) / 60.0 if self._learned else 0.0
        learned_term = np.array([semantic / 2.0, -semantic / 2.0])
        return kc, np.maximum(0.0, 20.0 + intensity + drive + learned_term + noise)


def small_config(mitigation=TOTAL_DRIVE_BALANCING):
    return sm.SyntheticConfig(
        mitigation=mitigation,
        signal_strengths=(0.8,),
        market_seeds=sm.MARKET_SEEDS,
        markets_per_seed=300,
        price_deviation=0.40,
        trials=1,
        score_scale=2.0,
        bootstrap_resamples=300,
        plasticity=PlasticityParams(learning_rate=0.3, drift_rate=0.0),
        prestated=False,
    )


def all_outputs(sensitive: bool, cfg: sm.SyntheticConfig):
    outputs = {}
    for strength in cfg.signal_strengths:
        for seed in cfg.market_seeds:
            innate = None
            if cfg.mitigation == INNATE_SCORE_SUBTRACTION:
                innate = sm.compute_innate_scores(FakeMarketSimulator(sensitive), cfg, strength, seed)
            for condition in sm.CONDITIONS:
                outputs[(strength, seed, condition)] = sm.run_dataset(
                    FakeMarketSimulator(sensitive), cfg, strength, seed, condition,
                    innate_scores=innate,
                )
    return outputs


def test_fake_with_no_learning_must_not_pass() -> None:
    cfg = small_config()
    verdict = sm.evaluate_signal_requirement(all_outputs(False, cfg), cfg)
    assert not verdict["success"]
    assert verdict["signal_requirement"] is None


def test_fake_with_learning_must_pass() -> None:
    cfg = small_config()
    verdict = sm.evaluate_signal_requirement(all_outputs(True, cfg), cfg)
    assert verdict["success"], verdict
    assert verdict["signal_requirement"] == 0.8


def test_job_plans_and_run_counts_for_both_open_mitigations() -> None:
    """Four training conditions since 2026-09-22: the drift-off sensitivity check is
    its own condition, so the selected plan is 100 jobs / 20,000 runs (was 75/15,000)."""
    balanced = sm.SyntheticConfig(mitigation=TOTAL_DRIVE_BALANCING)
    innate = sm.SyntheticConfig(mitigation=INNATE_SCORE_SUBTRACTION)
    assert len(sm.plan_jobs(balanced)) == 100
    assert sm.estimated_run_count(balanced) == 20_000
    assert len(sm.plan_jobs(innate)) == 125
    assert sm.estimated_run_count(innate) == 25_000
    assert all(job.deps for job in sm.plan_jobs(innate) if job.kind == "condition")


def _load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runner_dry_run_defaults_to_selected_mitigation_and_writes_nothing(tmp_path, capsys) -> None:
    runner = _load_script(RUNNER_PATH, "synthetic_runner_test")
    assert runner.main(["--dry-run", "--results-base", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "20000" in output and "total_drive_balancing" in output
    assert "OPEN DECISION" not in output and "25000" not in output
    assert not any(tmp_path.iterdir())


def test_parallel_launcher_dry_run_starts_no_process(tmp_path, capsys) -> None:
    launcher = _load_script(LAUNCHER_PATH, "synthetic_launcher_test")
    assert launcher.main([
        "--dry-run", "--mitigation", TOTAL_DRIVE_BALANCING,
        "--results-base", str(tmp_path), "--max-procs", "3",
    ]) == 0
    assert "100 jobs" in capsys.readouterr().out
    assert not any(tmp_path.iterdir())


# ---- drift-off condition and the left-only recompute (decided 2026-09-22) ---- #
def test_drift_off_is_its_own_condition_and_runs_with_drift_disabled() -> None:
    cfg = replace(small_config(), plasticity=PlasticityParams(learning_rate=0.3, drift_rate=0.25))
    out = sm.run_dataset(FakeMarketSimulator(True), cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT_DRIFT_OFF)
    assert sm.PROFIT_DRIFT_OFF in sm.CONDITIONS and out["drift_rate"] == 0.0
    # the configured drift rate is untouched for every other condition
    profit = sm.run_dataset(FakeMarketSimulator(True), cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT)
    assert profit["drift_rate"] == 0.25


def test_drift_off_teaches_like_the_profit_arm_when_drift_is_already_zero() -> None:
    """Same teaching signal, same seeds: with drift_rate = 0 in the config the two
    conditions must agree exactly, so any later difference is drift and nothing else."""
    cfg = small_config()  # drift_rate = 0.0
    kw = dict(strength=0.8, market_seed=sm.MARKET_SEEDS[0])
    a = sm.run_dataset(FakeMarketSimulator(True), cfg, condition=sm.PROFIT, **kw)
    b = sm.run_dataset(FakeMarketSimulator(True), cfg, condition=sm.PROFIT_DRIFT_OFF, **kw)
    assert [r["action"] for r in a["test"]] == [r["action"] for r in b["test"]]
    assert [r["score_difference"] for r in a["test"]] == [r["score_difference"] for r in b["test"]]


def test_drift_off_diverges_from_the_profit_arm_once_drift_is_on() -> None:
    cfg = replace(small_config(), plasticity=PlasticityParams(learning_rate=0.3, drift_rate=0.5))
    kw = dict(strength=0.8, market_seed=sm.MARKET_SEEDS[0])
    a = sm.run_dataset(FakeMarketSimulator(True), cfg, condition=sm.PROFIT, **kw)
    b = sm.run_dataset(FakeMarketSimulator(True), cfg, condition=sm.PROFIT_DRIFT_OFF, **kw)
    assert [r["score_difference"] for r in a["test"]] != [r["score_difference"] for r in b["test"]]


def test_runs_save_per_mbon_rates_and_the_instance_labels() -> None:
    cfg = small_config()
    sim = FakeMarketSimulator(True)
    out = sm.run_dataset(sim, cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT)
    assert out["mbon_ids"] == list(sim.mbon_ids) and out["mbon_labels"] == list(sim.mbon_labels)
    for row in out["train"] + out["test"]:
        assert len(row["mbon_yes"]) == len(row["mbon_no"]) == len(sim.mbon_ids)


def test_left_only_rescoring_adds_no_simulation_and_keeps_the_run_untouched() -> None:
    cfg = small_config()
    sim = FakeMarketSimulator(True)
    out = sm.run_dataset(sim, cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT)
    sides = {int(i): ("left" if n == 0 else "right") for n, i in enumerate(sim.mbon_ids)}
    calls_before = sim.present_calls
    left = sm.left_only_scores(out, cfg, sides=sides)
    assert sim.present_calls == calls_before  # nothing was simulated
    assert left["n_instances"] == 1 and left["side"] == "left"
    assert len(left["test"]) == len(out["test"])
    assert all(0.0 <= row["raw_probability"] <= 1.0 for row in left["test"])
    assert left["note"].startswith("re-scored from saved rates")
