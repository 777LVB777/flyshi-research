"""First learning test: experiment logic and verdict on FAKE simulators only.

The real simulator is never constructed here. The fakes return synthetic MBON rates
from a toy linear model, so we can check that the verdict detects learning when the
fake learns, and refuses to when it does not.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import first_learning as fl  # noqa: E402
from flyshi_research.learning.params import PlasticityParams  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "repro" / "mushroom_body" / "run_first_learning_test.py"
DOC = REPO / "docs" / "design" / "first-learning-test.md"
IDS = REPO / "repro" / "mushroom_body" / "neuron_ids_783.json"

# PPL1 compartment / approach-like: MBON11, MBON12. PAM / avoidance-like: MBON05, MBON03,
# MBON09. MBON24: in no compartment, zero weight.
LABELS = ["MBON11", "MBON11", "MBON12", "MBON05", "MBON05", "MBON03", "MBON09", "MBON24"]
APPROACH_COLS = [0, 1, 2]


class Interrupted(RuntimeError):
    pass


class FakeSim:
    """Toy linear 'network': MBON rate = base + sign * gain * (KC rates @ W) + noise.

    Knobs make it fail in specific ways:
      sensitive=False  ignores set_weights (weights never reach the output);
      sign=-1          KC->MBON synapses inhibitory (learning moves the wrong way);
      leak>0           a cue-A-specific output creeps up with every presentation
                       (state leaking between runs, independent of learning);
      generalize>0     changes in A's weights spill onto any presented cue;
      symmetric=True   cue B's KC->MBON rows are a copy of cue A's.
    Noise is a deterministic function of (seed, cue), like a seeded simulator.
    """

    def __init__(self, labels=LABELS, n_kc=60, noise_sd=1.0, base=20.0, sign=+1,
                 sensitive=True, leak=0.0, generalize=0.0, symmetric=True, fail_after=None,
                 wseed=0):
        rng = np.random.default_rng(wseed)
        self.kc_ids = [900000000000000000 + 7 * i for i in range(n_kc)]  # 64-bit-sized IDs
        self.mbon_ids = [800000000000000000 + i for i in range(len(labels))]
        self.mbon_labels = list(labels)
        self.cue_sets = {"A": self.kc_ids[0:20], "B": self.kc_ids[20:40]}
        W0 = rng.uniform(0.5, 1.5, (n_kc, len(labels))) * (rng.random((n_kc, len(labels))) < 0.8)
        if symmetric:
            W0[20:40] = W0[0:20]
        self._W0, self._W = W0, W0.copy()
        self._index = {k: i for i, k in enumerate(self.kc_ids)}
        self.noise_sd, self.base, self.sign = noise_sd, base, sign
        self.sensitive, self.leak, self.generalize = sensitive, leak, generalize
        self.fail_after, self.calls = fail_after, 0
        self.log = []  # (seed, duration_ms, n_trials, cue) per present() call

    def baseline_weights(self):
        return self._W0.copy()

    def set_weights(self, W):
        if self.sensitive:
            self._W = np.array(W, dtype=float)

    def present(self, rates, seed, duration_ms, n_trials):
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise Interrupted("simulated crash")
        self.calls += 1
        kc = np.zeros(len(self.kc_ids))
        for k, r in rates.items():
            kc[self._index[k]] = r
        drive = 0.01 * kc @ self._W
        if self.generalize:
            drive = drive + self.generalize * 0.01 * 150.0 * (self._W[0:20] - self._W0[0:20]).sum(axis=0)
        is_a = int(min(rates)) == self.cue_sets["A"][0]
        self.log.append((seed, duration_ms, n_trials, "A" if is_a else "B"))
        rng = np.random.default_rng([seed, 1 if is_a else 2])
        mbon = self.base + self.sign * drive + rng.normal(0, self.noise_sd / np.sqrt(n_trials), drive.size)
        if self.leak and is_a:
            mbon[APPROACH_COLS] += self.leak * self.calls
        return kc, np.clip(mbon, 0.0, None)


def run(tmp_path, sim, cfg=None, **kw):
    cfg = cfg or fl.ExperimentConfig()
    return fl.Experiment(sim, cfg, tmp_path, log=lambda s: None, **kw).run()


# ---- the verdict detects learning, and refuses it when it isn't there ------------ #
def test_learning_is_detected_when_the_fake_learns(tmp_path):
    v = run(tmp_path, FakeSim())
    assert v["verdict"] == fl.DEMONSTRATED, fl.summary_lines(v)
    c = v["conditions"]
    assert c["main"]["delta"] >= v["threshold"] > 0
    # Symmetric fake, but A and B are rewarded at different positions of the order, so
    # drift acts on them for different times: near-mirror, not exact.
    assert c["b_reward_b"]["delta"] == pytest.approx(-c["main"]["delta"], rel=0.05)
    assert c["a_plasticity_off"]["delta"] == 0.0  # frozen weights + same seeds reproduce exactly
    assert set(c) == {"main", "a_plasticity_off", "b_reward_b", "d_punish_a"}  # the gates
    cd = v["reported_diagnostics"]["c_reward_both"]  # (c) is REPORTED, not gated
    assert abs(cd["delta"]) < 0.05 * c["main"]["delta"]
    assert v["failed_controls"] == []


def test_not_demonstrated_when_weights_never_reach_the_output(tmp_path):
    v = run(tmp_path, FakeSim(sensitive=False))
    assert v["verdict"] == fl.NOT_DEMONSTRATED
    assert all(c["delta"] == 0.0 for c in v["conditions"].values())


def test_not_demonstrated_when_the_effect_is_within_noise(tmp_path):
    v = run(tmp_path, FakeSim(noise_sd=300.0, base=2000.0))
    assert v["verdict"] == fl.NOT_DEMONSTRATED
    assert abs(v["conditions"]["main"]["delta"]) < v["threshold"]


def test_a_large_move_in_the_wrong_direction_is_not_learning(tmp_path):
    v = run(tmp_path, FakeSim(sign=-1, base=200.0))
    assert v["conditions"]["main"]["delta"] <= -v["threshold"]  # big, but negative
    assert v["verdict"] == fl.NOT_DEMONSTRATED


def test_confounded_when_output_drifts_without_learning(tmp_path):
    v = run(tmp_path, FakeSim(leak=0.5))
    assert v["conditions"]["main"]["pass"]
    assert v["verdict"] == fl.CONFOUNDED
    assert "a_plasticity_off" in v["failed_controls"]


def test_confounded_when_punishing_a_spills_onto_b_everything_smells_bad(tmp_path):
    v = run(tmp_path, FakeSim(generalize=1.0))
    assert v["conditions"]["main"]["pass"]
    assert v["verdict"] == fl.CONFOUNDED
    assert "d_punish_a" in v["failed_controls"]


def test_control_c_alone_can_no_longer_cause_confounded(tmp_path):
    """Cues A and B drive different MBON populations, so rewarding both moves A-B by more
    than the noise even under perfectly cue-specific learning. That used to make the
    verdict CONFOUNDED; (c) is now a reported diagnostic and the verdict follows the
    specificity controls (a), (b), (d)."""
    v = run(tmp_path, FakeSim(symmetric=False, noise_sd=0.2))
    cd = v["reported_diagnostics"]["c_reward_both"]
    assert cd["exceeds_3_sigma"] and abs(cd["delta_over_sigma"]) > 3  # (c) does separate the cues ...
    assert v["verdict"] == fl.DEMONSTRATED and v["failed_controls"] == []  # ... and does not matter
    assert "c_reward_both" not in v["conditions"]
    # and the reported number is explained by cue-specific additive learning here
    assert cd["additive_prediction_main_plus_b"] == pytest.approx(cd["delta"], abs=1e-6)
    assert "REPORTED ONLY" in "\n".join(fl.summary_lines(v))


def test_control_c_result_is_kept_in_the_saved_output(tmp_path):
    run(tmp_path, FakeSim())
    d = fl.results_dir_for(tmp_path, fl.ExperimentConfig())
    assert (d / "condition_c_reward_both.json").exists()  # still simulated and saved
    saved = json.loads((d / "verdict.json").read_text())
    assert set(saved["reported_diagnostics"]["c_reward_both"]) == {
        "delta", "delta_over_sigma", "exceeds_3_sigma", "additive_prediction_main_plus_b",
        "residual_from_additive_prediction"}


def test_learning_weights_only_touch_the_trained_cue_rows(tmp_path):
    run(tmp_path, FakeSim())
    d = fl.results_dir_for(tmp_path, fl.ExperimentConfig())
    main = json.loads((d / "condition_main.json").read_text())["weight_summary"]
    assert main["other_rows_changed"] == 0
    assert main["rows_B_cols_PAM_fraction_of_baseline"] == 1.0
    assert main["rows_B_cols_PPL1_fraction_of_baseline"] == 1.0
    assert main["rows_A_cols_PPL1_fraction_of_baseline"] == 1.0  # reward -> PAM only
    assert main["rows_A_cols_PAM_fraction_of_baseline"] < 0.5
    off = json.loads((d / "condition_a_plasticity_off.json").read_text())["weight_summary"]
    assert off["rows_A_cols_PAM_fraction_of_baseline"] == 1.0


# ---- pure verdict logic ------------------------------------------------------------ #
def rows(pairs, seeds=(1, 2, 3, 4, 5)):
    return [{"seed": s, "score_A": a, "score_B": b} for s, (a, b) in zip(seeds, pairs)]


PRE = rows([(10, 0), (11.5, 0.5), (8.5, -0.5), (10.7, 0.2), (9.3, -0.2)])
D_PRE = [r["score_A"] - r["score_B"] for r in PRE]
SIGMA = float(np.std(D_PRE, ddof=1))
SIGMA_B = float(np.std([r["score_B"] for r in PRE], ddof=1))


def shifted(delta_a=0.0, delta_b=0.0):
    """Post-test rows = PRE with score_A shifted by delta_a and score_B by delta_b."""
    return rows([(r["score_A"] + delta_a, r["score_B"] + delta_b) for r in PRE])


def posts(main, a=0.0, b=None, c=0.0, d_b=0.0):
    return {"main": shifted(main), "a_plasticity_off": shifted(a),
            "b_reward_b": shifted(-main if b is None else b), "c_reward_both": shifted(c),
            "d_punish_a": shifted(-5.0, d_b)}


def test_noise_is_the_sample_sd_of_the_pre_training_difference():
    v = fl.evaluate_scores(PRE, posts(5.0), fl.ExperimentConfig())
    assert v["sigma"] == pytest.approx(SIGMA) and v["threshold"] == pytest.approx(3 * SIGMA)


def test_threshold_boundary_is_inclusive_for_main_and_b():
    T = 3 * SIGMA
    assert fl.evaluate_scores(PRE, posts(T), fl.ExperimentConfig())["verdict"] == fl.DEMONSTRATED
    v = fl.evaluate_scores(PRE, posts(T * 0.999), fl.ExperimentConfig())
    assert v["verdict"] == fl.NOT_DEMONSTRATED


def test_control_b_must_reverse():
    v = fl.evaluate_scores(PRE, posts(5.0, b=+5.0), fl.ExperimentConfig())
    assert v["verdict"] == fl.CONFOUNDED and v["failed_controls"] == ["b_reward_b"]


def test_control_a_must_stay_within_noise():
    v = fl.evaluate_scores(PRE, posts(5.0, a=3.0), fl.ExperimentConfig())
    assert v["verdict"] == fl.CONFOUNDED and v["failed_controls"] == ["a_plasticity_off"]


def test_control_c_is_reported_but_never_gates_the_verdict():
    T = 3 * SIGMA
    for c in (0.0, 0.5 * T, 10 * T, -10 * T):  # however large, in either direction
        v = fl.evaluate_scores(PRE, posts(5.0, c=c), fl.ExperimentConfig())
        assert v["verdict"] == fl.DEMONSTRATED and v["failed_controls"] == [], c
        cd = v["reported_diagnostics"]["c_reward_both"]
        assert cd["delta"] == pytest.approx(c)
        assert cd["exceeds_3_sigma"] is (abs(c) >= T)
    v = fl.evaluate_scores(PRE, posts(5.0, c=99.0, a=3.0), fl.ExperimentConfig())
    assert v["failed_controls"] == ["a_plasticity_off"]  # a real control failure still counts


def test_control_c_additive_prediction_is_main_plus_reward_b():
    v = fl.evaluate_scores(PRE, posts(6.0, b=-2.0, c=5.0), fl.ExperimentConfig())
    cd = v["reported_diagnostics"]["c_reward_both"]
    assert cd["additive_prediction_main_plus_b"] == pytest.approx(4.0)
    assert cd["residual_from_additive_prediction"] == pytest.approx(1.0)


def test_smells_bad_control_uses_cue_b_score_and_its_own_noise():
    T_b = 3 * SIGMA_B
    ok = fl.evaluate_scores(PRE, posts(5.0, d_b=0.99 * T_b), fl.ExperimentConfig())
    assert ok["threshold_B"] == pytest.approx(T_b) and ok["conditions"]["d_punish_a"]["pass"]
    for d_b in (T_b, -T_b):  # B moving by 3 sigma_B either way fails
        v = fl.evaluate_scores(PRE, posts(5.0, d_b=d_b), fl.ExperimentConfig())
        assert v["verdict"] == fl.CONFOUNDED and v["failed_controls"] == ["d_punish_a"]


def test_zero_noise_is_inconclusive_not_a_free_pass():
    flat = rows([(10, 0)] * 5)
    v = fl.evaluate_scores(flat, {k: flat for k in posts(0).keys()}, fl.ExperimentConfig())
    assert v["verdict"] == fl.INCONCLUSIVE and "noise" in v["reason"]


def test_missing_gating_condition_is_inconclusive_missing_diagnostic_is_not():
    p = posts(5.0)
    del p["b_reward_b"]
    assert fl.evaluate_scores(PRE, p, fl.ExperimentConfig())["verdict"] == fl.INCONCLUSIVE
    p = posts(5.0)
    del p["c_reward_both"]  # (c) is not required for a verdict
    v = fl.evaluate_scores(PRE, p, fl.ExperimentConfig())
    assert v["verdict"] == fl.DEMONSTRATED and v["reported_diagnostics"]["c_reward_both"] is None


def test_missing_seed_alignment_raises():
    p = posts(5.0)
    p["main"] = rows([(1, 0)] * 5, seeds=(9, 8, 7, 6, 5))  # test seeds must match the pre-test
    with pytest.raises(ValueError, match="seeds differ"):
        fl.evaluate_scores(PRE, p, fl.ExperimentConfig())


# ---- protocol --------------------------------------------------------------------- #
def test_training_order_alternates_in_pairs_balanced_and_seeded():
    cfg = fl.ExperimentConfig()
    o = fl.training_order(cfg)
    assert len(o) == 40 and o.count("A") == o.count("B") == 20
    assert all(sorted(o[i:i + 2]) == ["A", "B"] for i in range(0, 40, 2))
    assert "AAA" not in "".join(o) and "BBB" not in "".join(o)
    assert o == fl.training_order(cfg)
    assert o != fl.training_order(replace(cfg, order_seed=1))


def test_teaching_signals():
    cfg = fl.ExperimentConfig()
    assert fl.teaching_signal(None, cfg) == ({}, 0.0)
    assert fl.teaching_signal(+1, cfg) == ({"PAM": 1.0}, 150.0)
    assert fl.teaching_signal(-1, cfg) == ({"PPL1": 1.0}, 150.0)


def test_conditions_are_the_prestated_five():
    by = {c.name: c for c in fl.CONDITIONS}
    assert set(by) == {"main", "a_plasticity_off", "b_reward_b", "c_reward_both", "d_punish_a"}
    assert (by["main"].after_a, by["main"].after_b) == (1, None)
    assert not by["a_plasticity_off"].plastic
    assert (by["b_reward_b"].after_a, by["b_reward_b"].after_b) == (None, 1)
    assert (by["c_reward_both"].after_a, by["c_reward_both"].after_b) == (1, 1)
    assert [c.name for c in fl.CONDITIONS if not c.gating] == ["c_reward_both"]  # only (c) is not a gate
    assert fl.GATING_CONDITIONS == ("main", "a_plasticity_off", "b_reward_b", "d_punish_a")
    assert (by["d_punish_a"].after_a, by["d_punish_a"].after_b) == (-1, None)


def test_run_count_estimate():
    rc = fl.run_count(fl.ExperimentConfig())
    assert (rc.pretest, rc.per_condition_training, rc.per_condition_posttest) == (10, 40, 10)
    assert rc.total == 260
    assert rc.simulated_trial_seconds(fl.ExperimentConfig()) == 500.0


def test_every_protocol_call_matches_the_estimate(tmp_path):
    sim = FakeSim()
    run(tmp_path, sim)
    assert sim.calls == fl.run_count(fl.ExperimentConfig()).total


def test_config_validation_and_hash():
    with pytest.raises(ValueError):
        fl.ExperimentConfig(n_training=39)
    with pytest.raises(ValueError):
        fl.ExperimentConfig(test_seeds=(1,))
    with pytest.raises(ValueError):
        fl.ExperimentConfig(train_seed_base=20260317)  # overlaps test seeds
    a = fl.ExperimentConfig()
    assert a.config_hash() == fl.ExperimentConfig().config_hash()
    assert a.config_hash() != fl.ExperimentConfig(
        plasticity=PlasticityParams(learning_rate=0.2)).config_hash()
    assert fl.ExperimentConfig.smoke().prestated is False


def test_spec_states_the_same_protocol():
    text = " ".join(DOC.read_text().split())
    for needle in ("20260316", "20260317", "20260321", "20260402", "20260500", "150 Hz",
                   "1000 ms × 5 trials", "1000 ms × 1 trial", "ddof = 1", "3σ", "N = 40",
                   "260 runs", "INCONCLUSIVE", "NOT DEMONSTRATED", "CONFOUNDED",
                   "LEARNING DEMONSTRATED", "unanchored", "equivalence test", "per-type mean",
                   "must not be tuned on this test's results", "reported diagnostic",
                   "Control (c) alone can never produce this verdict",
                   "no dopamine release or dopamine-neuron activity is simulated",
                   "represented abstractly", "Revision history", "control (c) demoted"):
        assert needle in text, needle


# ---- restartability and output size ----------------------------------------------- #
def all_results(d):
    return {p.name: p.read_text() for p in sorted(d.glob("*.json"))}


# (crash point in simulator calls, calls the resumed run must make). Saved work:
# pre-test is not checkpointed (redone if interrupted); each training presentation is;
# a partly done post-test is redone.
@pytest.mark.parametrize("crash_at,resumed_calls", [
    (5, 260),                  # inside the pre-training test
    (10 + 25, 260 - 10 - 25),  # main condition, after training presentation 25
    (10 + 45, 260 - 10 - 40),  # main condition, inside its post-test
    (10 + 50 + 43, 260 - 10 - 50 - 40),  # control (a), inside its post-test
])
def test_interrupted_run_resumes_to_identical_results(tmp_path, crash_at, resumed_calls):
    cfg = fl.ExperimentConfig()
    clean = tmp_path / "clean"
    run(clean, FakeSim(), cfg)
    crashy = tmp_path / "crashy"
    with pytest.raises(Interrupted):
        run(crashy, FakeSim(fail_after=crash_at), cfg)
    resumed = FakeSim()
    run(crashy, resumed, cfg)
    d_clean, d_crash = fl.results_dir_for(clean, cfg), fl.results_dir_for(crashy, cfg)
    assert all_results(d_clean) == all_results(d_crash)
    assert not list(d_crash.glob("checkpoint_*")) and not list(d_crash.glob("*.partial*"))
    assert resumed.calls == resumed_calls  # finished work was not redone


def test_completed_experiment_is_not_rerun(tmp_path):
    run(tmp_path, FakeSim())
    again = FakeSim()
    run(tmp_path, again)
    assert again.calls == 0


def test_changed_config_cannot_mix_with_existing_results(tmp_path):
    cfg = fl.ExperimentConfig()
    d = fl.results_dir_for(tmp_path, cfg)
    d.mkdir(parents=True)
    (d / "config.json").write_text("{}")
    with pytest.raises(RuntimeError, match="does not match"):
        fl.Experiment(FakeSim(), cfg, tmp_path, log=lambda s: None)


def test_results_are_under_1mb_at_real_size(tmp_path):
    labels = [m["cell_type"] for m in json.loads(IDS.read_text())["mbons"]["records"]]
    assert len(labels) == 96
    run(tmp_path, FakeSim(labels=labels, n_kc=300))
    d = fl.results_dir_for(tmp_path, fl.ExperimentConfig())
    total = sum(p.stat().st_size for p in d.iterdir())
    assert 0 < total < 1_000_000, total


# ---- the script: dry run only, never the real simulator ----------------------------- #
def test_dry_run_prints_the_plan_and_never_imports_brian2(tmp_path):
    code = (
        "import sys, runpy\n"
        f"sys.argv = ['x', '--dry-run', '--results-base', {str(tmp_path)!r}]\n"
        f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in ('brian2', 'fast_runner', 'check_mb_response')]\n"
        "assert not bad, bad\n"
    )
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout
    assert "= 260 runs" in out and "500 simulated trial-seconds" in out
    assert "equivalence test has NOT been run" in out and "UNANCHORED" in out
    assert not any(tmp_path.iterdir())  # dry run writes nothing


def test_smoke_dry_run_is_labelled_and_small(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("rflt", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main(["--dry-run", "--smoke", "--results-base", str(tmp_path)])
    out = capsys.readouterr().out
    assert "pre-stated test: False" in out and "= 34 runs" in out


def test_simulator_receives_the_prestated_seeds_durations_and_cues(tmp_path):
    cfg = fl.ExperimentConfig()
    sim = FakeSim()
    run(tmp_path, sim, cfg)
    test_block = [(s, 1000.0, 5, cue) for s in cfg.test_seeds for cue in ("A", "B")]
    train_block = [(20260500 + k, 1000.0, 1, cue) for k, cue in enumerate(fl.training_order(cfg))]
    expected = test_block + (train_block + test_block) * len(fl.CONDITIONS)
    assert sim.log == expected


def test_training_presentations_see_the_weights_learned_so_far(tmp_path):
    """Learning curve: in the main condition, cue A's score during training rises as it is
    rewarded (which requires the learned weights to reach the simulator between steps);
    with plasticity off, it does not."""
    run(tmp_path, FakeSim(noise_sd=0.2))
    d = fl.results_dir_for(tmp_path, fl.ExperimentConfig())

    def a_scores(name):
        curve = json.loads((d / f"condition_{name}.json").read_text())["training_curve"]
        return [c["score"] for c in curve if c["cue"] == "A"]

    main, off = a_scores("main"), a_scores("a_plasticity_off")
    assert np.mean(main[-5:]) > np.mean(main[:5]) + 10.0
    assert abs(np.mean(off[-5:]) - np.mean(off[:5])) < 1.0


def test_experiment_verdict_needs_gating_condition_files_but_not_control_c(tmp_path):
    cfg = fl.ExperimentConfig()
    exp = fl.Experiment(FakeSim(), cfg, tmp_path, log=lambda s: None)
    exp.run()
    by = {c.name: c for c in fl.CONDITIONS}
    exp.condition_path(by["c_reward_both"]).unlink()  # the diagnostic was not run / lost
    v = exp.evaluate()
    assert v["verdict"] == fl.DEMONSTRATED and v["reported_diagnostics"]["c_reward_both"] is None
    exp.condition_path(by["b_reward_b"]).unlink()  # a gate is missing: cannot decide
    v = exp.evaluate()
    assert v["verdict"] == fl.INCONCLUSIVE and "b_reward_b" in v["reason"]
