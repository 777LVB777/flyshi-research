from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from flyshi_research.learning.bias_mitigation import (  # noqa: E402
    INNATE_SCORE_SUBTRACTION,
    NO_MITIGATION,
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
        # 900 left-hemisphere KCs followed by 300 right-hemisphere KCs, so a
        # bilateral draw is possible and the left-only guard has something to stop.
        self.left_kc_ids = [900000000000000000 + i for i in range(900)]
        self.right_kc_ids = [910000000000000000 + i for i in range(300)]
        self.kc_ids = self.left_kc_ids + self.right_kc_ids
        self.kc_sides = {**{k: "left" for k in self.left_kc_ids},
                         **{k: "right" for k in self.right_kc_ids}}
        self.mbon_ids = [800000000000000001, 800000000000000002]
        self.mbon_labels = ["MBON11", "MBON05"]  # approach-like, avoidance-like
        self._index = {kc_id: i for i, kc_id in enumerate(self.kc_ids)}
        self._W0 = np.ones((len(self.kc_ids), 2), dtype=float)
        self._W = self._W0.copy()
        self.sensitive = sensitive
        self._learned = False
        self._signal_ids = set(KCEncoder(self.left_kc_ids).pools["signal"].tolist())
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

    #: ``{seed: (trial, kc_ids, rate)}``: inject a single-trial recruitment event
    events: dict = {}

    def present_trials(self, rates, seed, duration_ms, n_trials):
        kc, mbon = self.present(rates, seed, duration_ms, n_trials)
        per_trial = np.tile(kc, (n_trials, 1))
        if seed in self.events:
            trial, ids, rate = self.events[seed]
            for kc_id in ids:
                per_trial[trial, self._index[kc_id]] = rate
            kc = per_trial.mean(axis=0)
        apl = np.full((n_trials, 2), 150.0)
        return kc, mbon, per_trial, apl


def small_config(mitigation=NO_MITIGATION):
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


def run(cfg, *args, sim=None, **kwargs):
    sim = sim or FakeMarketSimulator(True)
    return sm.run_dataset(sim, cfg, *args, kc_sides=sim.kc_sides, **kwargs)


def all_outputs(sensitive: bool, cfg: sm.SyntheticConfig):
    outputs = {}
    for strength in cfg.signal_strengths:
        for seed in cfg.market_seeds:
            innate = None
            if cfg.mitigation == INNATE_SCORE_SUBTRACTION:
                fake = FakeMarketSimulator(sensitive)
                innate = sm.compute_innate_scores(fake, cfg, strength, seed, kc_sides=fake.kc_sides)
            for condition in sm.CONDITIONS:
                fake = FakeMarketSimulator(sensitive)
                outputs[(strength, seed, condition)] = sm.run_dataset(
                    fake, cfg, strength, seed, condition,
                    kc_sides=fake.kc_sides, innate_scores=innate,
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


@pytest.mark.parametrize("mitigation", [TOTAL_DRIVE_BALANCING, INNATE_SCORE_SUBTRACTION])
def test_verdict_logic_still_holds_for_the_historical_alternatives(mitigation) -> None:
    cfg = small_config(mitigation)
    assert not sm.evaluate_signal_requirement(all_outputs(False, cfg), cfg)["success"]


def test_job_plans_and_run_counts_for_every_mitigation() -> None:
    """Four training conditions since 2026-09-22: the drift-off sensitivity check is
    its own condition, so the decided plan (no mitigation, 2026-10-09) is 100 jobs /
    20,000 runs, each one 200-run chain."""
    none = sm.SyntheticConfig()
    assert none.mitigation == NO_MITIGATION
    assert len(sm.plan_jobs(none)) == 100
    assert sm.estimated_run_count(none) == 20_000
    assert sm.critical_path_runs(none) == 200
    assert not any(job.deps for job in sm.plan_jobs(none))
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


def test_runner_dry_run_defaults_to_no_mitigation_and_writes_nothing(tmp_path, capsys) -> None:
    runner = _load_script(RUNNER_PATH, "synthetic_runner_test")
    assert runner.main(["--dry-run", "--results-base", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "20000" in output and "mitigation: none" in output
    assert "unbalanced Option B" in output and "LEFT-hemisphere KCs only" in output
    assert "total_drive_balancing" not in output and "25000" not in output
    # stale claims removed 2026-10-09
    assert "run_cue_rates" not in output and "Fast-runner equivalence" not in output
    assert not any(tmp_path.iterdir())


def test_parallel_launcher_dry_run_starts_no_process(tmp_path, capsys) -> None:
    launcher = _load_script(LAUNCHER_PATH, "synthetic_launcher_test")
    assert launcher.main([
        "--dry-run", "--results-base", str(tmp_path), "--max-procs", "3",
        "--gb-per-proc", "0.001", "--headroom-gb", "0",  # independent of this machine's RAM
    ]) == 0
    output = capsys.readouterr().out
    assert "jobs: 100" in output and "mitigation: none" in output
    assert "concurrency: floor(" in output and "-> " in output
    assert not any(tmp_path.iterdir())


# ---- drift-off condition and the left-only post-hoc rescoring (2026-09-22) ---- #
def test_drift_off_is_its_own_condition_and_runs_with_drift_disabled() -> None:
    cfg = replace(small_config(), plasticity=PlasticityParams(learning_rate=0.3, drift_rate=0.25))
    out = run(cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT_DRIFT_OFF)
    assert sm.PROFIT_DRIFT_OFF in sm.CONDITIONS and out["drift_rate"] == 0.0
    # the configured drift rate is untouched for every other condition
    profit = run(cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT)
    assert profit["drift_rate"] == 0.25


def test_drift_off_teaches_like_the_profit_arm_when_drift_is_already_zero() -> None:
    """Same teaching signal, same seeds: with drift_rate = 0 in the config the two
    conditions must agree exactly, so any later difference is drift and nothing else."""
    cfg = small_config()  # drift_rate = 0.0
    kw = dict(strength=0.8, market_seed=sm.MARKET_SEEDS[0])
    a = run(cfg, condition=sm.PROFIT, **kw)
    b = run(cfg, condition=sm.PROFIT_DRIFT_OFF, **kw)
    assert [r["action"] for r in a["test"]] == [r["action"] for r in b["test"]]
    assert [r["score_difference"] for r in a["test"]] == [r["score_difference"] for r in b["test"]]


def test_drift_off_diverges_from_the_profit_arm_once_drift_is_on() -> None:
    cfg = replace(small_config(), plasticity=PlasticityParams(learning_rate=0.3, drift_rate=0.5))
    kw = dict(strength=0.8, market_seed=sm.MARKET_SEEDS[0])
    a = run(cfg, condition=sm.PROFIT, **kw)
    b = run(cfg, condition=sm.PROFIT_DRIFT_OFF, **kw)
    assert [r["score_difference"] for r in a["test"]] != [r["score_difference"] for r in b["test"]]


def test_runs_save_per_mbon_rates_and_the_instance_labels() -> None:
    cfg = small_config()
    sim = FakeMarketSimulator(True)
    out = sm.run_dataset(sim, cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT, kc_sides=sim.kc_sides)
    assert out["mbon_ids"] == list(sim.mbon_ids) and out["mbon_labels"] == list(sim.mbon_labels)
    for row in out["train"] + out["test"]:
        assert len(row["mbon_yes"]) == len(row["mbon_no"]) == len(sim.mbon_ids)


def test_left_only_rescoring_adds_no_simulation_and_keeps_the_run_untouched() -> None:
    """Post-hoc rescoring of the runs as they happened. Unlike the first learning test
    this is NOT exact: the loop here is closed (score -> action -> teaching), so the
    decision loop is not replayed and the saved run must be left untouched."""
    cfg = small_config()
    sim = FakeMarketSimulator(True)
    out = sm.run_dataset(sim, cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT, kc_sides=sim.kc_sides)
    sides = {int(i): ("left" if n == 0 else "right") for n, i in enumerate(sim.mbon_ids)}
    calls_before = sim.present_calls
    left = sm.left_only_rescore(out, cfg, sides=sides)
    assert sim.present_calls == calls_before  # nothing was simulated
    assert left["n_instances"] == 1 and left["side"] == "left"
    assert len(left["test"]) == len(out["test"])
    assert all(0.0 <= row["raw_probability"] <= 1.0 for row in left["test"])
    assert left["note"].startswith("post-hoc rescoring")


# ---- left-only pools, the guard and no balance pool (decided 2026-10-09) ---- #
class _RecordingSim(FakeMarketSimulator):
    """Records every presented stimulus so tests can inspect what reached the model."""

    def __init__(self) -> None:
        super().__init__(True)
        self.presented = []

    def present_trials(self, rates, seed, duration_ms, n_trials):
        self.presented.append(dict(rates))
        return super().present_trials(rates, seed, duration_ms, n_trials)


def _tiny_config(mitigation=NO_MITIGATION):
    return replace(small_config(mitigation), markets_per_seed=12)


def test_every_presented_kc_is_left_hemisphere_and_no_balance_pool_is_presented() -> None:
    sim = _RecordingSim()
    cfg = _tiny_config()
    sm.run_dataset(sim, cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT, kc_sides=sim.kc_sides)
    encoder = sm.setup_encoder(sim, cfg, sim.kc_sides)
    balance = set(encoder.balance_pool.tolist())
    feature = {int(k) for pool in encoder.pools.values() for k in pool}
    assert len(sim.presented) == 2 * cfg.markets_per_seed
    for rates in sim.presented:
        assert all(sim.kc_sides[k] == "left" for k in rates)
        assert not balance & set(rates)
        assert set(rates) == feature and len(rates) == 500  # the five feature pools only


def test_bilateral_kc_table_cannot_produce_bilateral_pools() -> None:
    """The original hemisphere bug: KCEncoder(sim.kc_ids) over both hemispheres."""
    sim = FakeMarketSimulator(True)
    bilateral = KCEncoder(sim.kc_ids)
    assert any(sim.kc_sides[int(k)] == "right" for p in bilateral.pools.values() for k in p)
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        sm.assert_pools_left_only(bilateral, sim.kc_sides)
    left = sm.setup_encoder(sim, small_config(), sim.kc_sides)
    sm.assert_pools_left_only(left, sim.kc_sides)  # must not raise


def test_guard_rejects_a_right_kc_in_the_balance_pool_and_unannotated_kcs() -> None:
    sim = FakeMarketSimulator(True)
    encoder = sm.setup_encoder(sim, small_config(), sim.kc_sides)
    sides = dict(sim.kc_sides)
    sides[int(encoder.balance_pool[0])] = "right"
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        sm.assert_pools_left_only(encoder, sides)
    del sides[int(encoder.balance_pool[0])]  # unannotated counts as not left
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        sm.assert_pools_left_only(encoder, sides)


def test_run_dataset_refuses_to_run_without_the_hemisphere_table() -> None:
    sim = FakeMarketSimulator(True)
    with pytest.raises(TypeError, match="kc_sides"):
        sm.run_dataset(sim, _tiny_config(), 0.8, sm.MARKET_SEEDS[0], sm.PROFIT)
    with pytest.raises(TypeError, match="kc_sides"):
        sm.compute_innate_scores(sim, _tiny_config(), 0.8, sm.MARKET_SEEDS[0])


def test_all_right_hemisphere_table_aborts_before_any_presentation() -> None:
    sim = _RecordingSim()
    all_right = {k: "right" for k in sim.kc_ids}
    with pytest.raises(RuntimeError):
        sm.run_dataset(sim, _tiny_config(), 0.8, sm.MARKET_SEEDS[0], sm.PROFIT, kc_sides=all_right)
    assert sim.presented == []


def test_a_presented_balance_pool_aborts_the_unbalanced_sweep(monkeypatch) -> None:
    """If the balanced construction ever leaked into the no-mitigation sweep (for
    example through the encoder-wide default), the run must stop, not continue."""
    monkeypatch.setattr(sm, "option_b_variant", lambda cfg: sm.OPTION_B_BALANCED)
    sim = _RecordingSim()
    with pytest.raises(RuntimeError, match="balance pool present"):
        sm.run_dataset(sim, _tiny_config(), 0.8, sm.MARKET_SEEDS[0], sm.PROFIT, kc_sides=sim.kc_sides)


def test_variant_is_always_explicit_and_unbalanced_unless_balancing_is_named() -> None:
    assert sm.option_b_variant(sm.SyntheticConfig()) == sm.OPTION_B_UNBALANCED
    assert sm.option_b_variant(sm.SyntheticConfig(mitigation=INNATE_SCORE_SUBTRACTION)) == sm.OPTION_B_UNBALANCED
    assert sm.option_b_variant(sm.SyntheticConfig(mitigation=TOTAL_DRIVE_BALANCING)) == sm.OPTION_B_BALANCED


def test_the_real_runner_passes_the_shared_left_kc_table_and_guards_before_running() -> None:
    """Source-level guard, as for the graded runners: the job branch must build the
    hemisphere table from the shared ``kc_side_map`` and apply the guard."""
    import inspect
    import sys as _sys
    runner = _load_script(RUNNER_PATH, "synthetic_runner_guard_test")
    assert runner.kc_side_map is _sys.modules["run_left_only_pool_diagnostic"].kc_side_map
    src = inspect.getsource(runner.main)
    assert "kc_sides = kc_side_map(args.ids)" in src
    assert "sm.setup_encoder(sim, cfg, kc_sides)" in src
    assert src.count("kc_sides=kc_sides") == 2  # innate and condition branches
    assert "KCEncoder(sim.kc_ids)" not in inspect.getsource(sm)


def test_runner_and_launcher_default_to_no_mitigation() -> None:
    runner = _load_script(RUNNER_PATH, "synthetic_runner_default_test")
    launcher = _load_script(LAUNCHER_PATH, "synthetic_launcher_default_test")
    assert runner.parser().parse_args([]).mitigation == NO_MITIGATION
    assert launcher.parser().parse_args([]).mitigation == NO_MITIGATION
    assert sm.SyntheticConfig().mitigation == NO_MITIGATION


# ---- launcher: RAM rule and staggered starts (ported 2026-10-09) ------------ #
def test_launcher_uses_the_first_learning_ram_rule() -> None:
    launcher = _load_script(LAUNCHER_PATH, "synthetic_launcher_ram_test")
    import sys as _sys
    first = _sys.modules["launch_first_learning_parallel"]  # the module the launcher reuses
    assert launcher.plan_slots is first.plan_slots and launcher.acquire_lock is first.acquire_lock
    ccx33 = first.Resources(32.0, 31.0, 8, "test")
    ccx43 = first.Resources(64.0, 62.5, 16, "test")
    assert launcher.plan_slots(ccx33, 5.0, first.default_headroom_gb(32.0)) == 5
    assert launcher.plan_slots(ccx43, 5.0, first.default_headroom_gb(64.0)) == 11
    cfg = sm.SyntheticConfig()
    hours = launcher.estimate_makespan(sm.plan_jobs(cfg), 11, 55 / 60) / 60
    assert hours == pytest.approx(10 * 200 * 55 / 3600)  # 10 waves of 200-run chains


def test_launcher_waits_for_memory_and_staggers_starts(tmp_path) -> None:
    """Scheduling only: workers are trivial subprocesses that write the job file."""
    import sys as _sys
    launcher_mod = _load_script(LAUNCHER_PATH, "synthetic_launcher_sched_test")
    cfg = replace(sm.SyntheticConfig(), signal_strengths=(0.8,), market_seeds=(20261001,))
    readings = iter([None] + [100.0] * 1000)
    starts = []

    def argv_for(job):
        out = sm.results_dir_for(tmp_path, cfg) / "parts" / (job.id.replace(":", "_") + ".json")
        starts.append(job.id)
        return [_sys.executable, "-c",
                f"import pathlib; p=pathlib.Path({str(out)!r}); p.parent.mkdir(parents=True, exist_ok=True); p.write_text('{{}}')"]

    low_memory = {"n": 0}

    def mem():
        low_memory["n"] += 1
        return 0.5 if low_memory["n"] <= 3 else next(readings)  # first checks: not enough RAM

    run = launcher_mod.Launcher(cfg, tmp_path, slots=4, stagger_s=0.0, poll_s=0.01,
                                argv_for=argv_for, mem_reader=mem, log=lambda m: None,
                                finish=lambda: {"signal_requirement": None})
    result = run.run()
    assert sorted(result["done"]) == sorted(j.id for j in sm.plan_jobs(cfg))
    assert result["failed"] == [] and result["verdict"] == {"signal_requirement": None}
    assert low_memory["n"] > 3  # it re-read memory instead of starting regardless
    assert not (run.log_dir / "launcher.lock").exists()


# ---- innate policy: learning-off decisions versus price (2026-10-09) -------- #
def test_innate_policy_reports_betting_against_the_higher_priced_side() -> None:
    rows = []
    for i, price in enumerate(np.linspace(0.02, 0.98, 49)):
        diff = -35.0 * (2 * price - 1)  # the inferred drive term: favours the cheaper side
        rows.append({"quote": float(price), "score_difference": float(diff),
                     "drive_yes_hz": 45_000 + 6_000 * (2 * price - 1),
                     "drive_no_hz": 45_000 - 6_000 * (2 * price - 1)})
    pol = sm.innate_policy(rows)
    assert pol["fraction_backing_higher_priced_side"] == 0.0
    assert pol["score_vs_price_slope_hz"] == pytest.approx(-70.0)
    assert pol["score_vs_price_r"] == pytest.approx(-1.0)
    assert pol["score_vs_drive_difference_slope_hz_per_khz"] == pytest.approx(-35.0 / 12.0)
    assert len(pol["by_price_bin"]) == sm.INNATE_POLICY_PRICE_BINS
    assert pol["by_price_bin"][0]["fraction_yes"] == 1.0 and pol["by_price_bin"][-1]["fraction_no"] == 1.0
    assert sum(b["n"] for b in pol["by_price_bin"]) == 49
    assert "never gating" in pol["note"]


def test_innate_policy_counts_ties_and_handles_constant_scores() -> None:
    rows = [{"quote": p, "score_difference": 0.0} for p in (0.2, 0.5, 0.8)]
    pol = sm.innate_policy(rows)
    assert pol["fraction_tie"] == 1.0 and pol["fraction_backing_higher_priced_side"] is None
    assert pol["score_vs_price_r"] is None


def test_innate_policy_is_reported_per_strength_and_pooled_and_never_gates() -> None:
    cfg = small_config()
    outputs = all_outputs(False, cfg)
    verdict = sm.evaluate_signal_requirement(outputs, cfg)
    per = verdict["strengths"]["0.8"]["innate_policy"]
    assert per["n_decisions"] == cfg.markets_per_seed * len(cfg.market_seeds)
    assert verdict["innate_policy_pooled"]["n_decisions"] == per["n_decisions"]
    # learning-off rows carry the exact presented drives of both framings
    row = outputs[(0.8, cfg.market_seeds[0], sm.LEARNING_OFF)]["test"][0]
    assert row["drive_yes_hz"] > 0 and row["drive_no_hz"] > 0
    # changing the innate report cannot change the gate
    assert verdict["success"] is False


def test_setup_encoder_applies_the_guard_even_if_the_left_filter_is_bypassed(monkeypatch) -> None:
    """Defence in depth: if pools ever came out bilateral despite the left-only
    filter (here: an encoder that ignores its input and draws from both
    hemispheres), setup_encoder must still abort - so the guard must be wired in."""
    sim = _RecordingSim()
    real_encoder = sm.KCEncoder
    monkeypatch.setattr(sm, "KCEncoder", lambda ids, params=None: real_encoder(sim.kc_ids, params=params))
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        sm.setup_encoder(sim, _tiny_config(), sim.kc_sides)
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        sm.run_dataset(sim, _tiny_config(), 0.8, sm.MARKET_SEEDS[0], sm.PROFIT, kc_sides=sim.kc_sides)
    assert sim.presented == []


# ---- recent_change bound +-1 (decided 2026-10-09, Proposal A) ---------------- #
def test_recent_change_bound_is_plus_minus_one_and_never_binds_in_the_sweep() -> None:
    from flyshi_research.learning.params import EncoderParams
    from flyshi_research.simulator import generate_signal_markets
    spec = {f.name: f for f in EncoderParams().features}["recent_change"]
    assert (spec.min_value, spec.max_value, spec.mirror_for_no) == (-1.0, 1.0, True)
    cfg = sm.SyntheticConfig()
    changes = [m.recent_change for s in cfg.signal_strengths for seed in cfg.market_seeds
               for m in generate_signal_markets(cfg.markets_per_seed, seed, s, cfg.price_deviation)]
    assert max(abs(c) for c in changes) < 1.0  # the clip never binds
    assert np.mean(np.abs(changes) > 0.2) > 0.5  # most would have clipped at the old +-0.2


def test_widening_the_clip_leaves_every_other_market_quantity_unchanged() -> None:
    """Only the clip changed: the generator's random stream is untouched."""
    from flyshi_research.simulator import generate_signal_markets
    markets = generate_signal_markets(100, sm.MARKET_SEEDS[0], 0.4, 0.2)
    prev = 0.5
    for m in markets:
        assert m.recent_change == pytest.approx(m.quote - prev)
        prev = m.quote



# ---- per-decision ignition tracking (decided 2026-10-09) ---------------------- #
def test_ignition_record_measures_each_trial_by_hemisphere() -> None:
    cfg = sm.SyntheticConfig()
    kc_ids = list(range(10))
    sides = {i: ("left" if i < 6 else "right") for i in kc_ids}
    stimulated = [0, 1]
    rates = np.zeros((3, 10))
    rates[:, :2] = 90.0             # stimulated KCs, never counted
    rates[1, [2, 3, 6]] = [8.0, 6.0, 4.0]  # trial 1: 3 of 8 free KCs (2 left, 1 right)
    rates[2, 4] = 0.5               # at the threshold: not recruited (strictly above)
    apl = np.array([[140.0, 150.0], [170.0, 180.0], [145.0, 145.0]])
    rec = sm.ignition_record(kc_ids, rates, apl, stimulated, sides, cfg)
    assert rec["spread"] == [0.0, 0.375, 0.0]
    assert rec["spread_left"] == [0.0, 0.5, 0.0] and rec["spread_right"] == [0.0, 0.25, 0.0]
    assert rec["n_recruited"] == [0, 3, 0]
    assert rec["recruited_mean_hz"] == [None, 6.0, None]
    assert rec["apl_hz"] == [145.0, 175.0, 145.0]
    assert rec["ignited_any_trial"] is True
    quiet = sm.ignition_record(kc_ids, rates[[0, 2]], apl[[0, 2]], stimulated, sides, cfg)
    assert quiet["ignited_any_trial"] is False


def test_one_recruited_kc_is_not_ignition_but_a_population_event_is() -> None:
    """The extremes diagnostic's single steadily-driven KC (1 of ~4,677) must not be
    labelled ignited; a 1%+ population event in a single trial must."""
    cfg = sm.SyntheticConfig()
    kc_ids = list(range(1000))
    sides = {i: "left" for i in kc_ids}
    one = np.zeros((5, 1000)); one[:, 999] = 22.0
    assert not sm.ignition_record(kc_ids, one, np.zeros((5, 1)), [0], sides, cfg)["ignited_any_trial"]
    event = np.zeros((5, 1000)); event[2, 500:520] = 8.0  # 20 of 999 free KCs, one trial
    assert sm.ignition_record(kc_ids, event, np.zeros((5, 1)), [0], sides, cfg)["ignited_any_trial"]


def test_every_decision_records_both_framings_per_trial() -> None:
    cfg = _tiny_config()
    sim = FakeMarketSimulator(True)
    out = sm.run_dataset(sim, cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT, kc_sides=sim.kc_sides)
    for row in out["train"] + out["test"]:
        for key in ("ignition_yes", "ignition_no"):
            rec = row[key]
            assert len(rec["spread"]) == len(rec["apl_hz"]) == cfg.trials
            assert rec["ignited_any_trial"] is False  # the fake drives no free KC


def test_an_injected_single_trial_event_is_recorded_on_that_decision() -> None:
    cfg = replace(_tiny_config(), trials=5)
    sim = FakeMarketSimulator(True)
    seed = sm.simulation_seed(cfg, 0.8, sm.MARKET_SEEDS[0], 3)
    free = [k for k in sim.left_kc_ids if k not in set(sm.setup_encoder(sim, cfg, sim.kc_sides)
                                                        .balance_pool.tolist())
            and all(k not in p for p in sm.setup_encoder(sim, cfg, sim.kc_sides).pools.values())]
    sim.events = {seed: (2, free[:50], 8.0)}
    out = sm.run_dataset(sim, cfg, 0.8, sm.MARKET_SEEDS[0], sm.PROFIT, kc_sides=sim.kc_sides)
    rows = out["train"] + out["test"]
    flagged = [r["sequence"] for r in rows if r["ignition_yes"]["ignited_any_trial"]]
    assert flagged == [3]
    rec = rows[3]["ignition_yes"]
    assert rec["n_recruited"][2] == 50 and rec["n_recruited"][0] == 0
    assert rec["spread_right"][2] == 0.0 and rec["spread_left"][2] > 0.0


def test_ignition_thresholds_are_in_the_config_hash() -> None:
    base = sm.SyntheticConfig()
    assert (base.ignition_active_hz, base.ignition_spread_fraction) == (0.5, 0.01)
    assert replace(base, ignition_spread_fraction=0.02).config_hash() != base.config_hash()


def _flag(outputs, condition, seed, sequence):
    for row in outputs[(0.8, seed, condition)]["test"]:
        if row["sequence"] == sequence:
            row["ignition_no"] = {**row["ignition_no"], "ignited_any_trial": True}


def test_sensitivity_excludes_markets_ignited_in_either_gate_arm_and_never_gates() -> None:
    cfg = small_config()
    outputs = all_outputs(True, cfg)
    base = sm.evaluate_signal_requirement(outputs, cfg)
    seed0, seed1 = cfg.market_seeds[0], cfg.market_seeds[1]
    _flag(outputs, sm.PROFIT, seed0, cfg.train_count)        # excluded (profit arm)
    _flag(outputs, sm.LEARNING_OFF, seed1, cfg.train_count)  # excluded (learning-off arm)
    _flag(outputs, sm.ACCURACY, seed1, cfg.train_count + 1)  # not a gate arm: kept
    verdict = sm.evaluate_signal_requirement(outputs, cfg)
    sens = verdict["strengths"]["0.8"]["sensitivity_excluding_ignited"]
    n = cfg.test_count * len(cfg.market_seeds)
    assert sens["available"] and sens["n_test_markets"] == n
    assert sens["n_excluded"] == 2 and sens["n_remaining"] == n - 2
    assert "never gating" in sens["note"]
    # the gate itself is untouched by ignition flags
    for key in ("success", "signal_requirement"):
        assert verdict[key] == base[key]
    assert verdict["strengths"]["0.8"]["passes"] == base["strengths"]["0.8"]["passes"]
    exposure = verdict["strengths"]["0.8"]["ignition_exposure"]
    assert exposure[sm.ACCURACY]["test_decisions_with_ignited_framing"] == 1
    assert verdict["sensitivity_excluding_ignited_smallest_strength"] in (None, 0.8)


def test_sensitivity_without_exclusions_matches_the_gate_markets() -> None:
    cfg = small_config()
    verdict = sm.evaluate_signal_requirement(all_outputs(True, cfg), cfg)
    sens = verdict["strengths"]["0.8"]["sensitivity_excluding_ignited"]
    assert sens["n_excluded"] == 0
    gate = verdict["strengths"]["0.8"]["profit_improvement_vs_market"]
    # same markets, different (pre-stated) bootstrap seeds: same point estimate
    assert sens["profit_improvement_vs_market"]["estimate"] == pytest.approx(gate["estimate"])


def test_runner_bins_by_trial_with_the_shared_function_and_no_longer_uses_present() -> None:
    import inspect
    import sys as _sys
    runner = _load_script(RUNNER_PATH, "synthetic_runner_trials_test")
    assert runner.bin_spikes is _sys.modules["run_left_only_realistic_drive_diagnostic"].bin_spikes
    src = inspect.getsource(runner.build_sweep_simulator)
    assert "_build_population_simulator" in src and "bin_spikes(" in src
    assert "sim = build_sweep_simulator()" in inspect.getsource(runner.main)
    assert "sim.present(" not in inspect.getsource(sm)


def test_ignited_training_presentations_are_counted_per_arm_and_strength_and_never_gate() -> None:
    cfg = small_config()
    outputs = all_outputs(True, cfg)
    base = sm.evaluate_signal_requirement(outputs, cfg)
    seed = cfg.market_seeds[0]
    for condition in (sm.PROFIT, sm.LEARNING_OFF):
        row = outputs[(0.8, seed, condition)]["train"][0]
        side = "ignition_yes" if row["action"] == sm.Action.YES.value else "ignition_no"
        spread = list(row[side]["spread"])
        spread[-1] = 0.65  # one ignited trial, in the chosen (taught) framing
        row[side] = {**row[side], "spread": spread, "ignited_any_trial": True}
    verdict = sm.evaluate_signal_requirement(outputs, cfg)
    counts = verdict["ignited_training_presentations"]
    assert counts["available"] and "never gating" in counts["note"]
    n_train = cfg.train_count * len(cfg.market_seeds)
    profit = counts[sm.PROFIT]["by_strength"]["0.8"]
    assert profit["training_decisions"] == n_train == profit["teaching_decisions"]
    assert profit["training_decisions_with_ignited_framing"] == 1
    assert profit["teaching_decisions_with_ignited_framing"] == 1
    assert profit["teaching_decisions_chosen_framing_ignited"] == 1
    assert profit["ignited_trials_in_teaching_decisions"] == 1
    assert counts[sm.PROFIT]["all_strengths"]["teaching_decisions_with_ignited_framing"] == 1
    off = counts[sm.LEARNING_OFF]["by_strength"]["0.8"]
    assert off["training_decisions_with_ignited_framing"] == 1 and off["teaching_decisions"] == 0
    assert counts[sm.ACCURACY]["all_strengths"]["training_decisions_with_ignited_framing"] == 0
    for key in ("success", "signal_requirement"):
        assert verdict[key] == base[key]
