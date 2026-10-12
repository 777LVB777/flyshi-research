"""Phase-1-only verdict (2026-10-11 budget revision): gate, reports and not-run arms.

FAKE job outputs only (the fake simulator of test_synthetic_market). No real result
file is opened; Brian2 is never imported.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from test_synthetic_market import (  # noqa: E402
    FakeMarketSimulator,
    _set_test_forecast,
    small_config,
)

REPO = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO / "repro" / "mushroom_body" / "run_synthetic_market_experiment.py"
BLINDED_ROW_FIELDS = ("outcome", "quote", "raw_probability", "action", "score_difference",
                      "mbon_yes", "mbon_no", "calibrated_probability")


def _config():
    return replace(small_config(), signal_strengths=(0.0, 0.8), markets_per_seed=60, bootstrap_resamples=200)


def _outputs(cfg, arms=sm.CONDITIONS):
    out = {}
    for strength in cfg.signal_strengths:
        for seed in cfg.market_seeds:
            for condition in arms:
                fake = FakeMarketSimulator(True)
                out[(strength, seed, condition)] = sm.run_dataset(
                    fake, cfg, strength, seed, condition, kc_sides=fake.kc_sides)
    return out


@pytest.fixture(scope="module")
def full():
    cfg = _config()
    return cfg, _outputs(cfg)


def _phase1_only(outputs):
    return {k: copy.deepcopy(v) for k, v in outputs.items() if k[2] in sm.PHASE1_ARMS}


# ---- the gate is the pre-stated one, restricted to the phase 1 arms -------------------- #
def test_phase1_gate_equals_the_full_sweep_gate_on_the_same_outputs(full):
    cfg, outputs = full
    whole = sm.evaluate_signal_requirement(outputs, cfg)
    p1 = sm.evaluate_phase1(_phase1_only(outputs), cfg)
    for key in ("success", "signal_requirement", "higher_strength_failures", "null_control",
                "market_comparator", "sensitivity_excluding_ignited_smallest_strength"):
        assert p1[key] == whole[key], key
    for st in ("0.0", "0.8"):
        a, b = p1["strengths"][st], whole["strengths"][st]
        for key in ("profit_improvement_vs_market", "profit_improvement_vs_learning_off", "passes", "role",
                    "prestated_power_note", "sensitivity_excluding_ignited", "baselines", "innate_policy"):
            assert a[key] == b[key], (st, key)
        for arm in sm.PHASE1_ARMS:
            assert a["circuit"][arm] == b["circuit"][arm]
    assert p1["strengths"]["0.8"]["secondary_profit_vs_strength0"] == whole["strengths"]["0.8"]["secondary_profit_vs_strength0"]


def test_dropped_arms_are_reported_not_run_everywhere_an_arm_appears(full):
    cfg, outputs = full
    p1 = sm.evaluate_phase1(_phase1_only(outputs), cfg)
    note = "not run (dropped for budget, 2026-10-11)"
    assert p1["arms_not_run"] == {sm.ACCURACY: note, sm.PROFIT_DRIFT_OFF: note}
    assert p1["arms_evaluated"] == [sm.PROFIT, sm.LEARNING_OFF]
    assert "2026-10-11 budget revision" in p1["evaluation"] and "before any phase 1 result was read" in p1["evaluation"]
    for entry in p1["strengths"].values():
        assert entry["circuit"][sm.ACCURACY] == note and entry["circuit"][sm.PROFIT_DRIFT_OFF] == note
        assert entry["ignition_exposure"][sm.ACCURACY] == note
    assert p1["ignited_training_presentations"][sm.PROFIT_DRIFT_OFF] == note


def test_phase2_outputs_are_never_read_and_missing_phase1_outputs_refuse(full):
    cfg, outputs = full
    junk = _phase1_only(outputs)
    for s in cfg.signal_strengths:  # unreadable phase 2 "outputs": any access would raise
        for seed in cfg.market_seeds:
            junk[(s, seed, sm.ACCURACY)] = {}
    sm.evaluate_phase1(junk, cfg)
    incomplete = _phase1_only(outputs)
    del incomplete[(0.8, cfg.market_seeds[0], sm.LEARNING_OFF)]
    with pytest.raises(ValueError, match="phase 1 job output"):
        sm.evaluate_phase1(incomplete, cfg)


def test_full_sweep_evaluation_still_requires_every_arm(full):
    cfg, outputs = full
    with pytest.raises(KeyError):
        sm.evaluate_signal_requirement(_phase1_only(outputs), cfg)
    with pytest.raises(ValueError):
        sm.evaluate_signal_requirement(outputs, cfg, arms=(sm.PROFIT, sm.ACCURACY))


# ---- pre-stated null control, readings ------------------------------------------------- #
def test_null_control_failure_is_reported_and_blocks_the_requirement(full):
    cfg, outputs = full
    p1in = _phase1_only(outputs)
    for strength in cfg.signal_strengths:
        _set_test_forecast(p1in, cfg, strength, sm.PROFIT, lambda r: 0.01 + 0.98 * r["outcome"])
    p1 = sm.evaluate_phase1(p1in, cfg)
    assert p1["null_control"]["passes"] is True and p1["signal_requirement"] is None and not p1["success"]
    assert p1["readings"]["overall"].startswith("NULL CONTROL FAILED")


def test_a_pass_above_zero_sets_the_requirement_with_prestated_labels(full):
    cfg, outputs = full
    p1in = _phase1_only(outputs)
    _set_test_forecast(p1in, cfg, 0.8, sm.PROFIT, lambda r: 0.01 + 0.98 * r["outcome"])
    for seed in cfg.market_seeds:
        for p, o in zip(p1in[(0.0, seed, sm.PROFIT)]["test"], p1in[(0.0, seed, sm.LEARNING_OFF)]["test"]):
            p["calibrated_probability"] = o["calibrated_probability"]
    p1 = sm.evaluate_phase1(p1in, cfg)
    assert p1["success"] and p1["signal_requirement"] == 0.8
    assert p1["readings"]["overall"] == "signal requirement: 0.8"
    assert "learning effect, any source" in p1["readings"]["0.8"]
    assert p1["readings"]["0.0"] == "null control did not pass, as expected"


def _verdict_stub(strengths, passes, null_passes=False, requirement=None, higher=()):
    return {"strengths": {str(s): {"passes": p} for s, p in zip(strengths, passes)},
            "null_control": {"passes": null_passes,
                             "interpretation": ("NULL CONTROL FAILED: x" if null_passes
                                                else "null control did not pass, as expected")},
            "signal_requirement": requirement, "higher_strength_failures": list(higher)}


def test_non_pass_readings_are_ambiguous_and_0p4_is_undetermined():
    cfg = sm.SyntheticConfig()
    r = sm.phase1_readings(_verdict_stub(cfg.signal_strengths, [False] * 4), cfg)
    assert r["overall"] == "no signal requirement demonstrated within 0.4-1"
    for st in ("0.4", "0.8", "1.0"):
        assert "(a) no learning of the signal" in r[st] and "(b) learning-induced ignition" in r[st]
        assert "cannot turn it into a pass" in r[st]
    assert "undetermined, not absent" in r["0.4"] and "undetermined" not in r["0.8"]
    assert "cannot rescue or overturn" in r["sensitivity"]
    r2 = sm.phase1_readings(_verdict_stub(cfg.signal_strengths, [False, True, False, True], requirement=0.4,
                                          higher=(0.8,)), cfg)
    assert r2["overall"] == "signal requirement: 0.4" and "0.8" in r2["instability"]


# ---- exclusion sensitivity (pre-stated 2026-10-09) -------------------------------------- #
def test_exclusion_sensitivity_counts_ignited_test_markets_from_both_phase1_arms(full):
    cfg, outputs = full
    p1in = _phase1_only(outputs)
    seed = cfg.market_seeds[0]
    for arm, seq in ((sm.PROFIT, cfg.train_count), (sm.LEARNING_OFF, cfg.train_count + 1)):
        for row in p1in[(0.8, seed, arm)]["test"]:
            if row["sequence"] == seq:
                row["ignition_yes"] = {**row["ignition_yes"], "ignited_any_trial": True}
    sens = sm.evaluate_phase1(p1in, cfg)["strengths"]["0.8"]["sensitivity_excluding_ignited"]
    assert sens["available"] and sens["n_excluded"] == 2
    assert sens["n_remaining"] == sens["n_test_markets"] - 2


# ---- ignition report (pre-stated 2026-10-12, point 4) ----------------------------------- #
def _ignite(row, framing, trial, spread=0.66, n=3100):
    rec = copy.deepcopy(row[f"ignition_{framing}"])
    rec["spread"][trial] = spread
    rec["n_recruited"][trial] = n
    rec["recruited_mean_hz"][trial] = 20.0
    rec["apl_hz"][trial] = 250.0
    rec["ignited_any_trial"] = True
    row[f"ignition_{framing}"] = rec


def test_ignition_report_reads_only_the_whitelisted_fields(full):
    cfg, outputs = full
    stripped = _phase1_only(outputs)
    for out in stripped.values():
        for split in ("train", "test"):
            for row in out[split]:
                for f in BLINDED_ROW_FIELDS:
                    row.pop(f, None)
    rep = sm.ignition_report(stripped, cfg)
    assert rep["available"] and set(rep["by_arm"]) == set(sm.PHASE1_ARMS)


def test_ignition_report_counts_blocks_bands_and_differences(full):
    cfg, outputs = full
    p1in = _phase1_only(outputs)
    seed = cfg.market_seeds[0]
    rows = {r["sequence"]: r for split in ("train", "test") for r in p1in[(0.8, seed, sm.PROFIT)][split]}
    rows[3]["drive_yes_hz"] = 27_000.0
    _ignite(rows[3], "yes", 0)                       # training block 0, 25-30 kHz band
    rows[cfg.train_count + 5]["drive_no_hz"] = 45_000.0
    _ignite(rows[cfg.train_count + 5], "no", 0)      # test, 40-50 kHz band
    rep = sm.ignition_report(p1in, cfg)
    prof = rep["by_arm"][sm.PROFIT]["0.8"]
    n_trials = 2 * cfg.trials * cfg.markets_per_seed * len(cfg.market_seeds)
    assert prof["trials"]["ignited"] == 2 and prof["trials"]["total"] == n_trials
    assert prof["decisions_with_ignited_framing"]["train"]["ignited"] == 1
    assert prof["decisions_with_ignited_framing"]["test"]["ignited"] == 1
    assert prof["presentations_by_ignited_trials"]["1"] == 2
    assert prof["ignited_trials_detail"]["spread"]["median"] == pytest.approx(0.66)
    blocks = {b["first_sequence"]: b for b in prof["rise_during_training"]["blocks"]}
    assert blocks[0]["ignited_trials"] == 1 and blocks[0]["split"] == "train"
    assert prof["drive_bands"]["25-30 kHz"]["ignited"] == 1 and prof["drive_bands"]["40-50 kHz"]["ignited"] == 1
    assert prof["framing"]["yes"]["ignited"] == 1 and prof["framing"]["no"]["ignited"] == 1
    assert sum(b["total"] for b in prof["drive_bands"].values()) == n_trials
    comp = rep["per_strength_comparison"]["0.8"]
    assert comp["profit_minus_learning_off"]["difference"] == pytest.approx(2 / n_trials)
    assert comp["profit_minus_profit_at_strength0"]["difference"] == pytest.approx(2 / n_trials)
    assert "profit_minus_profit_at_strength0" not in rep["per_strength_comparison"]["0.0"]
    assert "never gating" in rep["note"]


def test_wilson_and_newcombe_match_published_values():
    lo, hi = sm.wilson_interval(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)
    lo, hi = sm.wilson_interval(5, 10)
    assert (lo, hi) == (pytest.approx(0.2366, abs=1e-4), pytest.approx(0.7634, abs=1e-4))
    d = sm.newcombe_difference(56, 70, 48, 80)  # Newcombe (1998), example (a): 0.0524 to 0.3339
    assert d["difference"] == pytest.approx(0.2)
    assert d["lower"] == pytest.approx(0.0524, abs=1e-4) and d["upper"] == pytest.approx(0.3339, abs=1e-4)


# ---- the runner entry point, on fake job files ------------------------------------------ #
def _runner():
    spec = importlib.util.spec_from_file_location("sweep_runner_phase1_test", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_finish_phase1_reads_only_phase1_files_and_writes_its_own_verdict(full, tmp_path):
    cfg, outputs = full
    runner = _runner()
    paths = runner.Paths(sm.results_dir_for(tmp_path, cfg))
    for job in sm.plan_jobs(cfg, sm.PHASE1_ARMS):
        if job.kind == "condition":
            runner._write_json(paths.output(job), outputs[(job.strength, job.market_seed, job.condition)])
    verdict = runner.finish_phase1(cfg, tmp_path)
    written = json.loads((paths.directory / "verdict_phase1.json").read_text())
    assert written["arms_not_run"] == verdict["arms_not_run"]
    assert not (paths.directory / "verdict.json").exists()
    with pytest.raises(RuntimeError, match="missing job output"):
        runner.finish(cfg, tmp_path)  # the full verdict still needs every arm
    assert runner.parser().parse_args(["--finish-phase1"]).finish_phase1
