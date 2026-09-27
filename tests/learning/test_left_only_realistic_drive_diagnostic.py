"""Left-only realistic-drive diagnostic: stimuli, per-trial binning, measures, guards.

FAKE DATA ONLY for every simulated quantity. The real simulator is never
constructed, the connectome is never opened, and no simulation is run. The frozen
neuron-ID table is read as data, the way the runner reads it. Pre-stated protocol:
docs/design/left-only-realistic-drive-diagnostic.md.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import graded_check as gc  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "repro" / "mushroom_body"
SCRIPT = HERE / "run_left_only_realistic_drive_diagnostic.py"
LADDER_SCRIPT = HERE / "run_left_only_population_scaling_diagnostic.py"
DOC = REPO / "docs" / "design" / "left-only-realistic-drive-diagnostic.md"
IDS = HERE / "neuron_ids_783.json"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_runner():
    return load(SCRIPT, "left_only_realistic_drive_runner_test")


def approach_label() -> str:
    return next(name for name, weight in gc.load_sign_table("circuit_80").weights.items()
                if weight == 1)


# ---- fakes ----------------------------------------------------------------------- #
# fake ID table: left 1000-1999 (enough for 800 pool KCs), right 5000-5599
LEFT = list(range(1000, 2000))
RIGHT = list(range(5000, 5600))
ALL_KCS = LEFT + RIGHT


def fake_ids_file(path: Path) -> Path:
    records = [{"root_id": i, "side": "left"} for i in LEFT]
    records += [{"root_id": i, "side": "right"} for i in RIGHT]
    path.write_text(json.dumps({"kenyon_cells": {"records": records}}))
    return path


def fake_payload(runner, name, seed, stim, *, event=None, mbon_rate=10.0, apl=150.0):
    """One fake result file.

    ``event``: (fraction of free KCs recruited, their rate in Hz, trials in which
    they fire). Free LEFT KCs are recruited first. Stimulated KCs fire at their
    pool's imposed rate in every trial.
    """
    stimulated = set(stim["stimulated_kc_ids"])
    free = [i for i in ALL_KCS if i not in stimulated]
    pool_of = {kc: pool for pool, members in stim["pools"].items() for kc in members}
    fraction, rate, event_trials = event or (0.0, 0.0, ())
    recruited = set(free[: int(round(fraction * len(free)))])
    per_trial_kc = []
    for t in range(runner.TRIALS):
        row = []
        for kc in ALL_KCS:
            if kc in stimulated:
                row.append(stim["pool_rates_hz"][pool_of[kc]])
            elif kc in recruited and t in event_trials:
                row.append(rate)
            else:
                row.append(0.0)
        per_trial_kc.append(row)
    per_trial_mbon = [[mbon_rate]] * runner.TRIALS
    per_trial_apl = [[apl, apl]] * runner.TRIALS
    mean = lambda rows: np.mean(np.asarray(rows, dtype=float), axis=0).tolist()  # noqa: E731
    return {
        "stimulus": name,
        "variant": runner.BY_NAME[name].variant,
        "framing": "YES",
        "price_value": runner.BY_NAME[name].price_value,
        "pool_side": "left",
        "pools": stim["pools"],
        "pool_rates_hz": stim["pool_rates_hz"],
        "n_kcs_driven": len(stimulated),
        "per_kc_rate_hz": None,
        "total_drive_hz": stim["total_drive_hz"],
        "stimulated_kc_ids": stim["stimulated_kc_ids"],
        "mbon_labels": [approach_label()],
        "population_ids": {"mbons": [1], "kenyon_cells": ALL_KCS, "apl_neurons": [2, 3],
                           "pam_dopamine_neurons": [4], "ppl1_dopamine_neurons": [5]},
        "rates_hz": {"mbons": mean(per_trial_mbon), "kenyon_cells": mean(per_trial_kc),
                     "apl_neurons": mean(per_trial_apl),
                     "pam_dopamine_neurons": [1.0], "ppl1_dopamine_neurons": [2.0]},
        "per_trial_rates_hz": {"kenyon_cells": per_trial_kc, "mbons": per_trial_mbon,
                               "apl_neurons": per_trial_apl},
        "seed": seed,
        "duration_ms": 1000.0,
        "trials": runner.TRIALS,
    }


def write_all(runner, directory: Path, ids: Path, events=None, skip=()):
    """Every (stimulus, seed) file; ``events[(stimulus, seed)]`` as in fake_payload."""
    stimuli = runner.build_stimuli(ids)
    for index, (name, seed) in enumerate(runner.planned_pairs()):
        if (name, seed) in skip:
            continue
        payload = fake_payload(runner, name, seed, stimuli[name],
                               event=(events or {}).get((name, seed)),
                               mbon_rate=10.0 + (index % 6))
        runner.output_path(name, seed, directory).write_text(json.dumps(payload))
    return stimuli


class _FakeSpikes:
    def __init__(self, flywire_id, trial) -> None:
        self._cols = {"flywire_id": list(flywire_id), "trial": list(trial)}

    def __len__(self) -> int:
        return len(self._cols["trial"])

    def __getitem__(self, key):
        return self._cols[key]


class _FakeSim:
    """What the runner reads from the population simulator, and nothing else."""

    def __init__(self) -> None:
        self.population_ids = {"mbons": [1], "kenyon_cells": ALL_KCS, "apl_neurons": [2, 3],
                               "pam_dopamine_neurons": [4], "ppl1_dopamine_neurons": [5]}
        order = [i for p in self.population_ids.values() for i in p]
        flyid2i = {f: n for n, f in enumerate(order)}
        self.population_index = {p: np.array([flyid2i[i] for i in ids])
                                 for p, ids in self.population_ids.items()}
        self.bundle = {"params": {}, "flyid2i": flyid2i, "n": len(order)}
        self._ms = 1.0
        self._fr = self
        self.mbon_type_labels = [approach_label()]
        self.calls = []

    def run_cue_rates(self, bundle, rates, n_trials, seed, name):
        self.calls.append(seed)
        ids, trials = [], []
        for t in range(n_trials):  # each stimulated KC 1 spike/trial; APL 3 in trial 0
            ids += list(rates)
            trials += [t] * len(rates)
        ids += [2, 2, 2]
        trials += [0, 0, 0]
        return _FakeSpikes(ids, trials), {}


# ---- the pre-statement ----------------------------------------------------------- #
def test_spec_pins_the_stimuli_seeds_scope_and_diagnostic_status() -> None:
    text = " ".join(DOC.read_text().split())
    for fragment in ("PRE-STATED", "DIAGNOSTIC, NOT A VALIDATION",
                     "7 stimuli × 6 seeds = 42 simulations",
                     "20260316, 20260317, 20260318, 20260319, 20260320, 20260321",
                     "1000 ms × 5 trials", "Per-trial rates for Kenyon cells, MBONs and APL",
                     "Address the mirroring antisymmetry", "independent of hemisphere",
                     "The binary label is kept, not replaced", "5 MB per file"):
        assert fragment in text, fragment
    for name in ("unbalanced_v0p05", "unbalanced_v0p88", "balanced_v0p00", "balanced_v0p25"):
        assert name in text


def test_runner_constants_match_the_pre_statement() -> None:
    runner = load_runner()
    assert runner.SEEDS == (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
    assert (runner.DURATION_MS, runner.TRIALS) == (1000.0, 5)
    assert runner.FRAMING == "YES" and runner.POOL_SIDE == "left"
    assert [s.price_value for s in runner.STIMULI] == [0.05, 0.22, 0.41, 0.63, 0.88, 0.0, 0.25]
    assert len(runner.planned_pairs()) == 42
    assert runner.PER_TRIAL_POPULATIONS == ("kenyon_cells", "mbons", "apl_neurons")
    assert runner.MAX_FILE_BYTES == 5 * 1024 * 1024
    assert runner.IGNITION_SPREAD_FRACTION == 0.01


# ---- the stimuli, from the real ID table (data, no simulation) ------------------- #
def test_real_stimuli_are_left_only_and_match_the_spec_table() -> None:
    runner = load_runner()
    sides = runner.kc_side_map(IDS)
    stimuli = runner.build_stimuli(IDS)
    assert {n: s["total_drive_hz"] for n, s in stimuli.items()} == runner.EXPECTED_TOTAL_DRIVE_HZ
    for name, s in stimuli.items():
        assert all(sides[i] == "left" for i in s["stimulated_kc_ids"]), name
        assert len(s["stimulated_kc_ids"]) == (800 if name.startswith("balanced") else 500)
    assert stimuli["balanced_v0p00"]["pool_rates_hz"]["__total_drive_balance__"] == 70.0
    assert stimuli["balanced_v0p25"]["pool_rates_hz"]["__total_drive_balance__"] == 50.0


def test_feature_pools_are_left_ladder_500s_and_the_balance_pool_is_new() -> None:
    runner = load_runner()
    ladder = load(LADDER_SCRIPT, "left_ladder_for_realistic_drive_test")
    stimuli = runner.build_stimuli(IDS)
    feature_kcs = set(stimuli["unbalanced_v0p05"]["stimulated_kc_ids"])
    assert feature_kcs == set(ladder.left_ladder_pools(IDS)["left_ladder_500"])
    balance = set(stimuli["balanced_v0p00"]["pools"]["__total_drive_balance__"])
    assert len(balance) == 300 and not balance & feature_kcs


def test_a_right_hemisphere_kc_in_a_pool_aborts_before_any_stimulus(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")

    class _Encoder:
        def __init__(self, kc_ids) -> None:
            self.pools = {"price": np.array(list(range(1000, 1099)) + [5000])}
            self.balance_pool = np.array(range(1100, 1400))

        def option_b_stimuli(self, *a, **k):  # pragma: no cover - must not be reached
            raise AssertionError("stimulus built despite a right-hemisphere KC")

    monkeypatch.setattr(runner, "KCEncoder", _Encoder)
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        runner.build_stimuli(ids)


def test_a_total_drive_that_differs_from_the_spec_aborts(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    monkeypatch.setitem(runner.EXPECTED_TOTAL_DRIVE_HZ, "unbalanced_v0p41", 44_000.0)
    with pytest.raises(RuntimeError, match="unbalanced_v0p41: total drive"):
        runner.build_stimuli(ids)


# ---- per-trial binning ------------------------------------------------------------ #
def test_bin_spikes_keeps_trials_separate_and_its_mean_matches_the_old_path() -> None:
    runner = load_runner()
    index = np.array([0, 0, 1, 1, 1, 2])
    trial = np.array([0, 1, 0, 0, 4, 2])
    per_trial, mean = runner.bin_spikes(index, trial, 3, 5, 1000.0)
    assert per_trial.shape == (5, 3)
    assert per_trial[:, 1].tolist() == [2.0, 0.0, 0.0, 0.0, 1.0]
    counts = np.bincount(index, minlength=3)
    assert np.allclose(mean, counts / (1.0 * 5))  # population-scaling runner's formula


def test_bin_spikes_rejects_a_trial_outside_the_run() -> None:
    runner = load_runner()
    with pytest.raises(ValueError, match="trial index"):
        runner.bin_spikes(np.array([0]), np.array([5]), 1, 5, 1000.0)


def test_present_with_trials_returns_means_for_all_and_trials_for_three() -> None:
    runner = load_runner()
    sim = _FakeSim()
    means, trials = runner._present_with_trials(sim, {1000: 90.0, 1001: 90.0}, 7, 1000.0, 5)
    assert set(means) == set(runner.POPULATIONS)
    assert set(trials) == set(runner.PER_TRIAL_POPULATIONS)
    assert trials["apl_neurons"][:, 0].tolist() == [3.0, 0.0, 0.0, 0.0, 0.0]
    assert means["apl_neurons"][0] == pytest.approx(0.6)
    kc = trials["kenyon_cells"]
    assert kc.shape == (5, len(ALL_KCS)) and kc[:, :2].tolist() == [[1.0, 1.0]] * 5


def test_simulate_missing_runs_only_missing_pairs_and_saves_per_trial_rates(
    tmp_path, monkeypatch
) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids, skip={("balanced_v0p25", 20260321),
                                           ("unbalanced_v0p05", 20260316)})
    sim = _FakeSim()
    import run_population_scaling_diagnostic as psd
    monkeypatch.setattr(psd, "_build_population_simulator", lambda: sim)
    runner.simulate_missing(tmp_path, ids, log=lambda _: None)
    assert sorted(sim.calls) == [20260316, 20260321]
    saved = json.loads(runner.output_path("balanced_v0p25", 20260321, tmp_path).read_text())
    assert set(saved["per_trial_rates_hz"]) == {"kenyon_cells", "mbons", "apl_neurons"}
    assert len(saved["per_trial_rates_hz"]["kenyon_cells"]) == 5
    assert saved["framing"] == "YES" and saved["n_kcs_driven"] == 800
    assert "verdict" not in saved


def test_simulate_missing_builds_no_model_when_everything_exists(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids)
    import run_population_scaling_diagnostic as psd

    def boom():
        raise AssertionError("model built although every file exists")

    monkeypatch.setattr(psd, "_build_population_simulator", boom)
    runner.simulate_missing(tmp_path, ids, log=lambda _: None)


def test_an_oversized_file_is_refused_and_nothing_is_written(tmp_path) -> None:
    runner = load_runner()
    target = tmp_path / "x.json"
    with pytest.raises(RuntimeError, match="ceiling"):
        runner._write_json(target, {"a": list(range(1000))}, max_bytes=100)
    assert not target.exists() and not list(tmp_path.iterdir())


# ---- the measurement --------------------------------------------------------------- #
def test_summary_is_a_bare_measurement(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids)
    summary = runner.summarise(tmp_path, ids, log=lambda _: None)
    assert summary["is_a_validation"] is False
    assert summary["has_pass_criterion"] is False
    assert "verdict" not in summary and "pass" not in summary
    text = json.dumps(summary)
    for banned in ("PASS", "FAIL", "ACCEPTED", "USABLE RANGE"):
        assert banned not in text, banned
    assert "mirroring antisymmetry" in summary["scope_note"]
    assert "No bilateral run exists" in summary["bilateral_reference_note"]
    saved = json.loads(runner.summary_path(tmp_path).read_text())
    runner.check_no_verdict(saved)


def test_every_stimulus_reports_the_label_and_recruitment_side_by_side(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids)
    summary = runner.summarise(tmp_path, ids, log=lambda _: None)
    assert set(summary["stimuli"]) == set(runner.BY_NAME)
    for name, stats in summary["stimuli"].items():
        for key in ("ignited_runs", "ignited_per_seed",
                    "nonstimulated_kc_active_fraction_per_seed",
                    "nonstimulated_kc_active_fraction_by_side_per_seed",
                    "recruited_kc_mean_rate_hz_per_seed",
                    "recruited_kc_median_rate_hz_per_seed",
                    "recruited_kc_mean_rate_hz_per_trial",
                    "nonstimulated_kc_active_fraction_per_trial",
                    "active_mbons_per_seed", "apl_per_seed_mean_hz", "apl_per_trial_mean_hz",
                    "score_per_seed", "score_mean", "score_sd", "mbon_vector_distance_hz",
                    "stimulated_kc_by_pool"):
            assert key in stats, (name, key)
        assert len(stats["ignited_per_seed"]) == len(stats["recruited_kc_mean_rate_hz_per_seed"]) == 6
        assert all(len(t) == 5 for t in stats["recruited_kc_mean_rate_hz_per_trial"])


def test_recruitment_separates_a_weak_event_from_a_strong_one(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    all_trials = tuple(range(5))
    write_all(runner, tmp_path, ids, events={
        ("unbalanced_v0p41", 20260316): (0.6, 1.2, all_trials),
        ("unbalanced_v0p41", 20260317): (0.6, 25.0, all_trials),
    })
    stats = runner.summarise(tmp_path, ids, log=lambda _: None)["stimuli"]["unbalanced_v0p41"]
    assert stats["ignited_per_seed"][:2] == [True, True]  # the binary label: identical
    weak, strong = stats["recruited_kc_mean_rate_hz_per_seed"][:2]
    assert weak == pytest.approx(1.2) and strong == pytest.approx(25.0)
    assert stats["recruited_kc_mean_rate_hz_per_seed"][2:] == [None] * 4  # null, not 0
    assert stats["ignited_runs"] == 2


def test_per_trial_recruitment_places_an_event_in_its_trial(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids, events={("balanced_v0p00", 20260318): (0.5, 30.0, (3,))})
    stats = runner.summarise(tmp_path, ids, log=lambda _: None)["stimuli"]["balanced_v0p00"]
    trials = stats["recruited_kc_mean_rate_hz_per_trial"][2]
    assert trials == [None, None, None, pytest.approx(30.0), None]
    # the trial mean still labels the run, and averages the event down
    assert stats["ignited_per_seed"][2] is True
    assert stats["recruited_kc_mean_rate_hz_per_seed"][2] == pytest.approx(6.0)
    assert stats["nonstimulated_kc_active_fraction_per_trial"][2][3] == pytest.approx(0.5, abs=1e-3)


def test_spread_is_split_by_hemisphere(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    # free KCs: 200 left (1000-1999 minus 800) then 600 right; recruit the first 25%
    write_all(runner, tmp_path, ids, events={("balanced_v0p25", 20260316): (0.25, 5.0, (0, 1))})
    stats = runner.summarise(tmp_path, ids, log=lambda _: None)["stimuli"]["balanced_v0p25"]
    by_side = stats["nonstimulated_kc_active_fraction_by_side_per_seed"][0]
    assert by_side["left"] == pytest.approx(1.0) and by_side["right"] == pytest.approx(0.0)


def test_measured_rate_is_reported_against_imposed_per_pool(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids)
    pools = runner.summarise(tmp_path, ids, log=lambda _: None)["stimuli"]["balanced_v0p00"][
        "stimulated_kc_by_pool"]
    assert pools["price"]["imposed_rate_hz"] == 30.0
    assert pools["__total_drive_balance__"]["imposed_rate_hz"] == 70.0
    assert pools["__total_drive_balance__"]["n_kcs"] == 300
    for pool in pools.values():
        assert pool["measured_over_imposed"] == pytest.approx(1.0)
        assert len(pool["measured_rate_per_seed_hz"]) == 6


def test_no_summary_until_all_forty_two_results_exist(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids, skip={("unbalanced_v0p63", 20260319)})
    lines = []
    assert runner.summarise(tmp_path, ids, log=lines.append) is None
    assert "missing 1 of 42" in lines[0]
    assert not runner.summary_path(tmp_path).exists()


def test_a_file_from_a_different_stimulus_is_refused(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids)
    path = runner.output_path("unbalanced_v0p22", runner.SEEDS[0], tmp_path)
    payload = json.loads(path.read_text())
    payload["stimulated_kc_ids"] = payload["stimulated_kc_ids"][:-1] + [5000]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="differ"):
        runner.summarise(tmp_path, ids, log=lambda _: None)
    assert not runner.summary_path(tmp_path).exists()


# ---- enforcement -------------------------------------------------------------------- #
CLEAN = {"is_a_validation": False, "has_pass_criterion": False, "stimuli": {}}


@pytest.mark.parametrize("bad", [
    {**CLEAN, "verdict": "contained"},
    {**CLEAN, "stimuli": {"x": {"passed": True}}},
    {**CLEAN, "note": "this would PASS"},
    {**CLEAN, "note": "USABLE RANGE 30-90 Hz"},
    {**CLEAN, "is_a_validation": True},
    {**CLEAN, "has_pass_criterion": True},
    {"stimuli": {}},
])
def test_check_no_verdict_rejects_validation_language(bad) -> None:
    runner = load_runner()
    with pytest.raises(ValueError):
        runner.check_no_verdict(bad)


def test_check_no_verdict_accepts_a_bare_measurement() -> None:
    load_runner().check_no_verdict(CLEAN)


@pytest.mark.xfail(strict=True, reason="canary: a summary carrying a verdict must never "
                   "get through the enforcement check; if this ever passes, the suite fails")
def test_canary_a_verdict_bearing_summary_gets_through() -> None:
    load_runner().check_no_verdict({**CLEAN, "verdict": "PASS"})


# ---- dry run and flags ------------------------------------------------------------- #
def test_dry_run_prints_the_plan_and_writes_nothing(tmp_path, capsys) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    out = tmp_path / "results"
    assert runner.main(["--dry-run", "--results-dir", str(out), "--ids", str(ids)]) == 0
    text = capsys.readouterr().out
    for fragment in ("DRY RUN", "not a validation", "YES only", "planned simulations: 42",
                     "to run: 42", "estimated runtime: 35.4 min", "per trial"):
        assert fragment in text, fragment
    assert not out.exists()


def test_dry_run_counts_completed_work(tmp_path, capsys) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids, skip={(n, s) for n, s in runner.planned_pairs()
                                           if n.startswith("balanced")})
    runner.dry_run(tmp_path, ids)
    text = capsys.readouterr().out
    assert "already done: 30, to run: 12" in text
    assert f"estimated runtime: {(12 * 50.5 + 4) / 60:.1f} min" in text


def test_dry_run_and_analyze_only_are_mutually_exclusive(tmp_path) -> None:
    runner = load_runner()
    with pytest.raises(SystemExit):
        runner.main(["--dry-run", "--analyze-only", "--results-dir", str(tmp_path)])


@pytest.mark.parametrize("flag", ["--dry-run", "--analyze-only"])
def test_flag_never_imports_brian2_or_a_backend(tmp_path, flag) -> None:
    code = (
        "import sys, runpy\n"
        f"sys.argv = ['x', '{flag}', '--results-dir', {str(tmp_path)!r}]\n"
        "try:\n"
        f"    runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "('brian2', 'run_first_learning_test', 'fast_runner', 'check_mb_response', 'pandas')]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
