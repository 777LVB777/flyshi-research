"""First learning test ignition re-check: recorder, validity gate, pre-stated readings.

FAKE data only; Brian2 is never imported and the connectome is never opened.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import first_learning as fl  # noqa: E402
from flyshi_research.learning import synthetic_market as sm  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "repro" / "mushroom_body"
SCRIPT = HERE / "run_first_learning_ignition_recheck.py"
RUNNER = HERE / "run_first_learning_test.py"
DOC = REPO / "docs" / "design" / "first-learning-ignition-recheck-diagnostic.md"
SEEDS = (20260317, 20260318, 20260319, 20260320, 20260321)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rc():
    return _load(SCRIPT, "first_learning_ignition_recheck_test")


@pytest.fixture(scope="module")
def runner():
    return _load(RUNNER, "first_learning_runner_for_recheck_test")


class _Spikes:
    """Minimal stand-in for run_cue_rates' spike table."""

    def __init__(self, flywire_id, trial):
        self._d = {"flywire_id": list(flywire_id), "trial": list(trial)}

    def __len__(self):
        return len(self._d["flywire_id"])

    def __getitem__(self, k):
        return self._d[k]


# ---- spec and guards --------------------------------------------------------------- #
def test_spec_is_a_diagnostic_written_before_the_code():
    text = " ".join(DOC.read_text().split())
    assert "is_a_validation: false" in text and "no verdict" in text
    assert "written 2026-10-12, before the code and before any run" in text
    assert "If any value differs: STOP." in text


def test_config_is_the_original_first_learning_test(rc):
    assert rc.recheck_config().config_hash() == "6fea97ac91"


def test_refuses_to_write_into_or_beside_the_original(rc):
    for bad in (rc.RESULTS_ROOT, rc.ORIGINAL_DIR, rc.ORIGINAL_DIR / "sub"):
        with pytest.raises(SystemExit):
            rc.check_base(bad)
    assert rc.check_base(rc.RECHECK_BASE) == rc.RECHECK_BASE.resolve()
    assert fl.results_dir_for(rc.RECHECK_BASE, rc.recheck_config()) != rc.ORIGINAL_DIR


# ---- recorder: never alters the scores --------------------------------------------- #
def test_per_trial_counts_sum_to_the_trial_mean_counts(runner):
    flyid2i = {101: 0, 102: 1, 103: 2}
    spikes = _Spikes([101, 101, 102, 103, 101, 103], [0, 1, 1, 2, 2, 2])
    per = runner.per_trial_counts(spikes, flyid2i, 3, 3)
    assert per.tolist() == [[1, 0, 0], [1, 1, 0], [1, 0, 2]]
    pooled = np.bincount([flyid2i[f] for f in spikes["flywire_id"]], minlength=3)
    assert per.sum(axis=0).tolist() == pooled.tolist()
    assert runner.per_trial_counts(_Spikes([], []), flyid2i, 3, 2).tolist() == [[0, 0, 0], [0, 0, 0]]
    with pytest.raises(ValueError):
        runner.per_trial_counts(_Spikes([101], [3]), flyid2i, 3, 3)


def test_trial_sink_is_off_by_default(runner):
    src = RUNNER.read_text()
    assert "self.trial_sink = None" in src
    # the returned trial means are still computed by the original line
    assert "rate = counts / (duration_ms / 1000.0 * n_trials)" in src


def test_recorder_writes_one_file_per_presentation_and_identifies_the_cue(rc, tmp_path):
    rec = rc.TrialRecorder(tmp_path, {"A": [1, 2], "B": [3, 4]}, np.array([0, 1, 2, 3]),
                           np.array([4]), np.array([5]))
    rec.job = "posttest:main:20260317"
    counts = np.arange(12).reshape(2, 6)
    rec({3: 150.0, 4: 150.0}, 20260317, 1000.0, 2, counts)
    path = rc.trial_file(tmp_path, rec.job, 20260317, "B")
    with np.load(path) as z:
        assert str(z["cue"]) == "B" and z["kc"].tolist() == [[0, 1, 2, 3], [6, 7, 8, 9]]
        assert z["mbon"].tolist() == [[4], [10]] and z["apl"].tolist() == [[5], [11]]
    with pytest.raises(RuntimeError):
        rec({1: 150.0, 3: 150.0}, 20260317, 1000.0, 2, counts)


# ---- validity gate ----------------------------------------------------------------- #
def _fake_set():
    row = lambda s: {"seed": s, "score_A": 1.5, "score_B": -2.25, "mbon_A": [1.0, 2.0], "mbon_B": [3.0, 4.0]}
    cond = {"posttest": {"per_seed": [row(s) for s in SEEDS]},
            "training_curve": [{"k": 0, "cue": "A", "score": 0.5, "teaching": {"PAM": 1.0}, "n_eligible_kc": 100}],
            "weight_summary": {"other_rows_changed": 0}}
    return {"pretest": [row(s) for s in SEEDS],
            "conditions": {c.name: copy.deepcopy(cond) for c in fl.CONDITIONS}}


def test_identical_results_are_valid_and_any_difference_is_not(rc):
    a = _fake_set()
    assert rc.validity_mismatches(a, copy.deepcopy(a)) == []
    for mutate in (lambda d: d["pretest"][2].__setitem__("score_A", 1.5 + 1e-12),
                   lambda d: d["conditions"]["main"]["posttest"]["per_seed"][0].__setitem__("mbon_B", [3.0, 4.0001]),
                   lambda d: d["conditions"]["b_reward_b"]["training_curve"][0].__setitem__("n_eligible_kc", 3423),
                   lambda d: d["conditions"]["d_punish_a"]["weight_summary"].__setitem__("other_rows_changed", 1)):
        b = copy.deepcopy(a)
        mutate(b)
        assert len(rc.validity_mismatches(a, b)) == 1


# ---- ignition labelling: the sweep's exact rule ------------------------------------- #
def test_presentation_record_uses_the_sweep_definition(rc):
    kc_ids = list(range(1, 211))  # 10 stimulated + 200 free
    meta = {"kc_ids": kc_ids, "cue_sets": {"A": kc_ids[:10]}}
    sides = {k: ("left" if k % 2 else "right") for k in kc_ids}
    kc = np.zeros((3, 210), dtype=np.uint16)
    kc[:, :10] = 150
    kc[0, 10:12] = 1        # 2 free KCs at 1 Hz: 1.0% -> NOT above 1%
    kc[1, 10:13] = 1        # 3 free KCs: 1.5% -> ignited (a single spike counts, as in the sweep)
    kc[2, 10:150] = 20      # cascade
    npz = {"duration_ms": 1000.0, "kc": kc, "mbon": np.ones((3, 2), dtype=np.uint16),
           "apl": np.ones((3, 1), dtype=np.uint16), "cue": "A", "seed": 1, "job": "pretest:1"}

    class _RO:
        def score(self, m):
            return float(np.sum(m))

    p = rc.presentation_record(npz, meta, _RO(), sides, sm.SyntheticConfig())
    assert p["ignited"] == [False, True, True]
    assert p["ignition"]["n_recruited"] == [2, 3, 140]
    assert p["trial_scores"] == [2.0, 2.0, 2.0]


# ---- pre-stated readings ------------------------------------------------------------ #
def _stage(scores, ignited=None):
    """scores: {seed: {cue: [5 trial scores]}}; ignited: {(seed, cue): [5 flags]}."""
    ignited = ignited or {}
    return {(s, c): {"trial_scores": v, "ignited": ignited.get((s, c), [False] * 5)}
            for s, cues in scores.items() for c, v in cues.items()}


def _flat(stage):
    return {s: {c: float(np.mean(stage[(s, c)]["trial_scores"])) for c in ("A", "B")} for s in SEEDS}


def test_main_reading_without_cascades(rc):
    pre = _stage({s: {"A": [-68] * 5, "B": [-86] * 5} for s in SEEDS})
    post = _stage({s: {"A": [90] * 5, "B": [-86] * 5} for s in SEEDS})
    r = rc.main_reading(pre, post, _flat(pre), _flat(post), list(SEEDS), 6.545)
    assert r["reading"].startswith("no test-time cascade in main")
    assert r["delta"] == pytest.approx(158.0)


def test_main_reading_measures_the_shift_from_one_cascaded_trial(rc):
    pre = _stage({s: {"A": [-68 + i * 0.1] * 5, "B": [-86] * 5} for i, s in enumerate(SEEDS)})
    trials = [90, 90, 90, 90, 15]  # one cascade trial pulls the presentation mean down by 15
    post = _stage({s: {"A": (trials if s == 20260318 else [90] * 5), "B": [-86] * 5} for s in SEEDS},
                  {(20260318, "A"): [False, False, False, False, True]})
    r = rc.main_reading(pre, post, _flat(pre), _flat(post), list(SEEDS), 6.545)
    assert r["ignited_trials_posttest"] == 1
    assert r["shift"] == pytest.approx(-3.0)  # -15 on one seed of five
    assert r["reading"].endswith("the main result does not depend on them")


def test_split_reading_explained_partly_and_not(rc):
    pre = _stage({s: {"A": [-68] * 5, "B": [-86] * 5} for s in SEEDS})
    # seeds 18/20: two cascaded trials at -300 drag B down; the other trials look like 17/19/21
    def post_for(cascade_score):
        b = {s: [95] * 5 for s in SEEDS}
        flags = {}
        for s in (20260318, 20260320):
            b[s] = [95, 95, 95, cascade_score, cascade_score]
            flags[(s, "B")] = [False, False, False, True, True]
        return _stage({s: {"A": [-66] * 5, "B": b[s]} for s in SEEDS}, flags)

    post = post_for(-100)
    r = rc.split_reading(pre, post, _flat(pre), _flat(post))
    assert r["reading"] == "test-time cascades explain the split" and r["reduction"] == pytest.approx(1.0)

    # cascades present in 18/20, but the non-ignited trials still differ: partly / not
    post2 = _stage({s: {"A": [-66] * 5, "B": ([60, 60, 60, -100, -100] if s in (20260318, 20260320) else [95] * 5)}
                    for s in SEEDS},
                   {(s, "B"): [False, False, False, True, True] for s in (20260318, 20260320)})
    r2 = rc.split_reading(pre, post2, _flat(pre), _flat(post2))
    assert r2["reading"] == "test-time cascades partly explain the split"


def test_split_reading_exact_confound_and_reversed_pattern(rc):
    pre = _stage({s: {"A": [-68] * 5, "B": [-86] * 5} for s in SEEDS})
    post = _stage({s: {"A": [-66] * 5, "B": ([17] * 5 if s in (20260318, 20260320) else [95] * 5)} for s in SEEDS},
                  {(s, "B"): [True] * 5 for s in (20260318, 20260320)})
    assert rc.split_reading(pre, post, _flat(pre), _flat(post))["reading"].startswith(
        "the split coincides exactly with test-time cascades")
    rev = _stage({s: {"A": [-66] * 5, "B": [95] * 5} for s in SEEDS},
                 {(20260317, "B"): [True, False, False, False, False]})
    assert rc.split_reading(pre, rev, _flat(pre), _flat(rev))["reading"].startswith("do not explain as hypothesised")
    none = _stage({s: {"A": [-66] * 5, "B": [95] * 5} for s in SEEDS})
    assert rc.split_reading(pre, none, _flat(pre), _flat(none))["reading"] == "do not explain (condition (i) fails)"
