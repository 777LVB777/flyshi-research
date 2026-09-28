"""Graded-encoding VALIDATION (left-only, mirrored, no balancing): stimuli, verdict,
recruitment and the validation enforcement rules.

FAKE DATA ONLY for every simulated quantity. The real simulator is never
constructed, the connectome is never opened, and no simulation is run. The frozen
neuron-ID table is read as data, the way the runner reads it. Pre-stated protocol:
docs/design/graded-encoding-left-only-mirrored.md.

Fakes use one MBON instance of a type CIRCUIT-80 weights +1, so its per-type-mean
score equals its rate and S_s(v) = m_yes - m_no = the (1-D) contrast c_s(v).
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
SCRIPT = HERE / "run_graded_encoding_left_only_mirrored.py"
LADDER_SCRIPT = HERE / "run_left_only_population_scaling_diagnostic.py"
DOC = REPO / "docs" / "design" / "graded-encoding-left-only-mirrored.md"
IDS = HERE / "neuron_ids_783.json"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_runner():
    return load(SCRIPT, "graded_left_mirrored_runner_test")


def approach_label() -> str:
    return next(name for name, weight in gc.load_sign_table("circuit_80").weights.items()
                if weight == 1)


# ---- fakes ------------------------------------------------------------------------ #
LEFT = list(range(1000, 2000))
RIGHT = list(range(5000, 5600))
ALL_KCS = LEFT + RIGHT


def fake_ids_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [{"root_id": i, "side": "left"} for i in LEFT]
    records += [{"root_id": i, "side": "right"} for i in RIGHT]
    path.write_text(json.dumps({"kenyon_cells": {"records": records}}))
    return path


def pattern(k: int, i: int) -> float:
    """Deterministic zero-ish noise in [-1, 1] for seed index k, value index i."""
    return ((k * 7 + i * 3) % 5 - 2) / 2.0


def curve(f, amp=0.3, endpoint_amp=None, primary_extra=None):
    """c_s(v_i) = f[i] + noise. ``endpoint_amp`` adds large repeat-seed noise at the
    top value only; ``primary_extra`` overrides the primary seed's contrasts."""
    def c(runner, seed, i):
        k = runner.SEEDS.index(seed)
        if primary_extra is not None and seed == runner.PRIMARY_SEED:
            return primary_extra[i]
        value = f[i] + amp * pattern(k, i)
        if endpoint_amp and i == len(f) - 1 and seed != runner.PRIMARY_SEED:
            value += endpoint_amp * (1 if k % 2 else -1)
        return value
    return c


def fake_payload(runner, value, framing, seed, stim, mbon_rate, event=None):
    stimulated = set(stim["stimulated_kc_ids"])
    free = [i for i in ALL_KCS if i not in stimulated]
    pool_of = {kc: pool for pool, members in stim["pools"].items() for kc in members}
    fraction, rate = event or (0.0, 0.0)
    recruited = set(free[: int(round(fraction * len(free)))])
    kc_row = [stim["pool_rates_hz"][pool_of[kc]] if kc in stimulated
              else (rate if kc in recruited else 0.0) for kc in ALL_KCS]
    return {
        "value": value, "framing": framing,
        "presented_price_value": runner.presented_value(value, framing),
        "variant": "unbalanced", "pool_side": "left",
        "pools": stim["pools"], "pool_rates_hz": stim["pool_rates_hz"],
        "n_kcs_driven": len(stimulated), "total_drive_hz": stim["total_drive_hz"],
        "stimulated_kc_ids": stim["stimulated_kc_ids"],
        "mbon_labels": [approach_label()],
        "population_ids": {"mbons": [1], "kenyon_cells": ALL_KCS, "apl_neurons": [2, 3],
                           "pam_dopamine_neurons": [4], "ppl1_dopamine_neurons": [5]},
        "rates_hz": {"mbons": [mbon_rate], "kenyon_cells": kc_row, "apl_neurons": [150.0, 150.0],
                     "pam_dopamine_neurons": [1.0], "ppl1_dopamine_neurons": [2.0]},
        "per_trial_rates_hz": {"kenyon_cells": [kc_row] * runner.TRIALS,
                               "mbons": [[mbon_rate]] * runner.TRIALS,
                               "apl_neurons": [[150.0, 150.0]] * runner.TRIALS},
        "seed": seed, "duration_ms": 1000.0, "trials": runner.TRIALS,
    }


def write_all(runner, directory: Path, ids: Path, contrast, skip=(), events=None):
    """Every (value, framing, seed) file. m_yes = 100 + c/2, m_no = 100 - c/2."""
    directory.mkdir(parents=True, exist_ok=True)
    pairs = runner.build_pairs(ids)
    for value, framing, seed in runner.planned_presentations():
        if (value, framing, seed) in skip:
            continue
        c = contrast(runner, seed, runner.VALUES.index(value))
        rate = 100.0 + c / 2 if framing == "YES" else 100.0 - c / 2
        payload = fake_payload(runner, value, framing, seed, pairs[value][framing], rate,
                               event=(events or {}).get((value, framing, seed)))
        runner.output_path(value, framing, seed, directory).write_text(json.dumps(payload))


MONOTONE = [-4.0, -10.0, -17.0, -24.0, -32.0]
REVERSES_AT_TOP = [-4.0, -10.0, -17.0, -24.0, -18.0]
ZIGZAG = [-4.0, -10.0, -5.0, -12.0, -6.0]


def run(runner, tmp_path, contrast, **kw):
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path / "r", ids, contrast, **kw)
    return runner.analyze(tmp_path / "r", ids, log=lambda _: None), tmp_path / "r", ids


# ---- the pre-statement --------------------------------------------------------------- #
def test_spec_freezes_set_b_and_records_the_erratum() -> None:
    text = " ".join(DOC.read_text().split())
    for fragment in ("THIS IS A VALIDATION", "FROZEN, 2026-09-27",
                     "0.56, 0.64, 0.73, 0.83, 0.94", "**60 presentations**",
                     "(value, framing, seed)", "ACCEPTED", "USABLE RANGE",
                     "Deliberate change: monotonicity on the seed mean",
                     "measured directly, never derived analytically"):
        assert fragment in text, fragment


def test_constants_are_the_pre_stated_ones() -> None:
    runner = load_runner()
    runner.check_constants()
    assert runner.VALUES == (0.56, 0.64, 0.73, 0.83, 0.94)
    assert runner.PRIMARY_SEED == 20260316
    assert runner.REPEAT_SEEDS == (20260317, 20260318, 20260319, 20260320, 20260321)
    assert runner.NOISE_MARGIN == gc.NOISE_MARGIN == 3.0
    assert runner.MIN_SUBRANGE_VALUES == gc.MIN_SUBRANGE_RATES == 3
    assert (runner.SIGN_TABLE, runner.AGGREGATION) == ("circuit_80", "type_mean")
    assert (runner.DURATION_MS, runner.TRIALS) == (1000.0, 5)
    assert runner.VERDICTS == ("ACCEPTED", "USABLE RANGE", "FAIL")


def test_a_changed_constant_is_refused(monkeypatch) -> None:
    runner = load_runner()
    monkeypatch.setattr(runner, "NOISE_MARGIN", 2.0)
    with pytest.raises(ValueError, match="noise margin"):
        runner.check_constants()


def test_sixty_presentations_one_per_value_framing_seed_repeats_first() -> None:
    runner = load_runner()
    plan = runner.planned_presentations()
    assert len(plan) == len(set(plan)) == 60
    assert {seed for _, _, seed in plan[:50]} == set(runner.REPEAT_SEEDS)
    assert {seed for _, _, seed in plan[50:]} == {runner.PRIMARY_SEED}
    assert len({runner.output_path(*p) for p in plan}) == 60


# ---- the stimuli, from the real ID table (data, no simulation) ---------------------- #
def test_real_pairs_obey_every_section_3_1_check() -> None:
    runner = load_runner()
    sides = runner.kc_side_map(IDS)
    ladder = load(LADDER_SCRIPT, "left_ladder_for_mirrored_test")
    pairs = runner.build_pairs(IDS)
    feature_kcs = set(ladder.left_ladder_pools(IDS)["left_ladder_500"])
    for v, pair in pairs.items():
        for framing in ("YES", "NO"):
            ids = pair[framing]["stimulated_kc_ids"]
            assert set(ids) == feature_kcs and all(sides[i] == "left" for i in ids)
            assert "__total_drive_balance__" not in pair[framing]["pool_rates_hz"]
        assert pair["YES"]["pool_rates_hz"]["price"] == pytest.approx(30 + 120 * v)
        assert pair["NO"]["pool_rates_hz"]["price"] == pytest.approx(30 + 120 * (1 - v))
        assert pair["d_yes_hz"] - pair["d_no_hz"] == pytest.approx(12_000 * (2 * v - 1))
        assert pair["d_yes_hz"] + pair["d_no_hz"] == pytest.approx(90_000)


def test_a_background_off_its_mirror_fixed_point_breaks_the_swap_and_aborts(
    tmp_path, monkeypatch
) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    monkeypatch.setitem(runner.BACKGROUND, "recent_change", 0.1)
    with pytest.raises(RuntimeError, match=r"NO\(v\) is not YES\(1-v\)"):
        runner.build_pairs(ids)


def test_a_right_hemisphere_kc_aborts_before_any_stimulus(tmp_path, monkeypatch) -> None:
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
        runner.build_pairs(ids)


# ---- the three outcomes ---------------------------------------------------------------- #
def test_outcome_accepted(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, curve(MONOTONE))
    assert out["verdict"] == "ACCEPTED"
    assert out["monotonic_on_seed_mean"] is True and out["direction"] == "decreasing"
    assert out["endpoint_gate_met"] is True
    assert out["validated_value_range"] == [0.56, 0.94]
    assert out["reflected_value_range_by_identity"] == pytest.approx([0.06, 0.44])
    assert out["seed_mean_scores"] == pytest.approx(MONOTONE, abs=0.5)
    runner.check_validation_output(out)


def test_outcome_usable_range(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, curve(REVERSES_AT_TOP))
    assert out["verdict"] == "USABLE RANGE"
    assert out["monotonic_on_seed_mean"] is False and out["endpoint_gate_met"] is True
    assert out["chosen_subrange_values"] == [0.56, 0.83]
    assert out["validated_value_range"] == [0.56, 0.83]
    assert out["reflected_value_range_by_identity"] == pytest.approx([0.17, 0.44])
    assert out["chosen_subrange_distance_hz"] >= out["chosen_subrange_threshold_hz"]
    runner.check_validation_output(out)


def test_outcome_fail_on_the_endpoint_gate(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, curve(MONOTONE, endpoint_amp=25.0))
    assert out["verdict"] == "FAIL"
    assert out["monotonic_on_seed_mean"] is True  # monotone, yet the noise gate decides
    assert out["endpoint_gate_met"] is False
    assert out["validated_value_range"] is None
    assert any("endpoint distance" in r for r in out["fail_reasons"])
    runner.check_validation_output(out)


def test_outcome_fail_with_no_three_value_sub_range(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, curve(ZIGZAG))
    assert out["verdict"] == "FAIL"
    assert out["chosen_subrange_values"] is None
    assert any("sub-range" in r for r in out["fail_reasons"])


# ---- the rule's parts ------------------------------------------------------------------ #
def test_monotonicity_is_judged_on_the_seed_mean_not_the_primary_seed(tmp_path) -> None:
    runner = load_runner()
    # the primary seed alone reverses (old single-seed rule: not monotonic) ...
    primary = [-4.0, -10.0, -9.0, -24.0, -32.0]
    out, _, _ = run(runner, tmp_path, curve(MONOTONE, primary_extra=primary))
    assert gc.strictly_monotonic(primary)[0] is False
    # ... but the six-seed mean is monotone, and that is what decides
    assert out["monotonic_on_seed_mean"] is True and out["verdict"] == "ACCEPTED"
    assert out["scores_by_seed"][str(runner.PRIMARY_SEED)] == pytest.approx(primary)


def test_d_change_uses_only_the_repeat_seeds(tmp_path) -> None:
    runner = load_runner()
    base, _, _ = run(runner, tmp_path / "a", curve(MONOTONE))
    noisy_primary = [m + 7.0 * pattern(0, i) for i, m in enumerate(MONOTONE)]
    moved, _, _ = run(runner, tmp_path / "b", curve(MONOTONE, primary_extra=noisy_primary))
    assert moved["change_noise_all_pairs_hz"] == pytest.approx(base["change_noise_all_pairs_hz"])
    assert moved["endpoint_distance_hz"] != pytest.approx(base["endpoint_distance_hz"])


def test_every_pair_has_a_directly_measured_noise_floor(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, curve(MONOTONE))
    assert len(out["change_noise_all_pairs_hz"]) == 10
    assert out["endpoint_threshold_hz"] == pytest.approx(3.0 * out["endpoint_change_noise_hz"])
    assert out["endpoint_change_noise_hz"] == pytest.approx(
        out["change_noise_all_pairs_hz"]["0.56-0.94"])


def test_evaluate_scores_through_circuit_score_difference() -> None:
    runner = load_runner()
    label = approach_label()
    pairs = {s: [(np.array([100.0 + m / 2]), np.array([100.0 - m / 2])) for m in MONOTONE]
             for s in runner.SEEDS}
    result = runner.evaluate(pairs, [label])
    assert result.seed_mean_scores == pytest.approx(MONOTONE)


# ---- recruitment beside the ignition label ---------------------------------------------- #
def test_recruitment_is_reported_beside_the_label_for_all_sixty(tmp_path) -> None:
    runner = load_runner()
    event = {(0.73, "NO", 20260318): (0.5, 1.2), (0.94, "YES", 20260316): (0.4, 25.0)}
    out, _, _ = run(runner, tmp_path, curve(MONOTONE), events=event)
    rows = out["recruitment_by_presentation"]
    assert len(rows) == 60 and out["ignited_presentations"] == 2
    for row in rows:
        for key in ("ignited", "nonstimulated_kc_active_fraction",
                    "nonstimulated_kc_active_fraction_by_side",
                    "recruited_kc_mean_rate_hz", "recruited_kc_median_rate_hz",
                    "recruited_kc_mean_rate_hz_per_trial", "apl_mean_rate_hz"):
            assert key in row, key
    by = {(r["value"], r["framing"], r["seed"]): r for r in rows}
    weak, strong = by[(0.73, "NO", 20260318)], by[(0.94, "YES", 20260316)]
    assert weak["ignited"] and strong["ignited"]  # the binary label cannot tell them apart
    assert weak["recruited_kc_mean_rate_hz"] == pytest.approx(1.2)
    assert strong["recruited_kc_mean_rate_hz"] == pytest.approx(25.0)
    contained = by[(0.56, "YES", 20260317)]
    assert contained["ignited"] is False and contained["recruited_kc_mean_rate_hz"] is None
    assert out["verdict"] == "ACCEPTED"  # ignition is reported, not gated


# ---- no verdict ---------------------------------------------------------------------------- #
def test_no_verdict_while_one_presentation_is_missing(tmp_path) -> None:
    runner = load_runner()
    lines = []
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path / "r", ids, curve(MONOTONE), skip={(0.83, "NO", 20260316)})
    assert runner.analyze(tmp_path / "r", ids, log=lines.append) is None
    assert "missing 1 of 60" in lines[0]
    assert not runner.verdict_path(tmp_path / "r").exists()


def test_no_verdict_from_a_file_whose_stimulus_is_not_the_pre_stated_one(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path / "r", ids, curve(MONOTONE))
    path = runner.output_path(0.64, "NO", 20260319, tmp_path / "r")
    payload = json.loads(path.read_text())
    payload["pool_rates_hz"]["price"] = 106.8  # the YES rate: an unmirrored NO
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="differs from the pre-stated"):
        runner.analyze(tmp_path / "r", ids, log=lambda _: None)
    assert not runner.verdict_path(tmp_path / "r").exists()


def test_no_verdict_when_a_presentation_file_carries_one(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path / "r", ids, curve(MONOTONE))
    path = runner.output_path(0.56, "YES", 20260317, tmp_path / "r")
    payload = json.loads(path.read_text())
    payload["verdict"] = "ACCEPTED"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="carries a verdict"):
        runner.analyze(tmp_path / "r", ids, log=lambda _: None)
    assert not runner.verdict_path(tmp_path / "r").exists()


@pytest.mark.xfail(strict=True, reason="canary: a verdict must never be produced from 59 "
                   "of 60 presentations; if this ever passes, the suite fails")
def test_canary_a_verdict_is_produced_from_an_incomplete_set(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path / "r", ids, curve(MONOTONE), skip={(0.94, "YES", 20260316)})
    assert runner.analyze(tmp_path / "r", ids, log=lambda _: None) is not None


# ---- validation enforcement (NOT the diagnostic rules) ---------------------------------- #
def _good(runner, verdict="ACCEPTED"):
    return {"is_a_validation": True, "has_pass_criterion": True, "spec": runner.SPEC,
            "values": list(runner.VALUES), "verdict": verdict}


@pytest.mark.parametrize("verdict", ["ACCEPTED", "USABLE RANGE", "FAIL"])
def test_enforcement_accepts_each_verdict_of_the_vocabulary(verdict) -> None:
    runner = load_runner()
    runner.check_validation_output(_good(runner, verdict))


@pytest.mark.parametrize("change", [
    {"verdict": "PASS"}, {"verdict": None}, {"verdict": "contained"},
    {"is_a_validation": False}, {"has_pass_criterion": False},
    {"notes": "this would PASS"}, {"extra": {"verdict": "FAIL"}},
    {"spec": "docs/design/graded-encoding-balanced.md"}, {"values": [0.05, 0.22]},
])
def test_enforcement_rejects_diagnostic_or_malformed_output(change) -> None:
    runner = load_runner()
    with pytest.raises(ValueError):
        runner.check_validation_output({**_good(runner), **change})


def test_the_diagnostic_enforcement_would_reject_a_valid_verdict() -> None:
    """Guard against reusing the wrong rules: a correct validation output fails the
    diagnostic check, so the two must stay separate."""
    runner = load_runner()
    diagnostic = load(HERE / "run_left_only_realistic_drive_diagnostic.py",
                      "realistic_drive_for_mirrored_test")
    with pytest.raises(ValueError):
        diagnostic.check_no_verdict(_good(runner))


def test_real_verdict_file_contains_no_diagnostic_word(tmp_path) -> None:
    runner = load_runner()
    for name, f in (("a", MONOTONE), ("u", REVERSES_AT_TOP), ("f", ZIGZAG)):
        out, directory, _ = run(runner, tmp_path / name, curve(f))
        saved = json.loads(runner.verdict_path(directory).read_text())
        assert saved == json.loads(json.dumps(out))
        assert "PASS" not in json.dumps(saved)
        runner.check_validation_output(saved)


# ---- simulation plumbing, with a fake simulator ------------------------------------------ #
class _FakeSpikes:
    def __init__(self, flywire_id, trial) -> None:
        self._cols = {"flywire_id": list(flywire_id), "trial": list(trial)}

    def __len__(self) -> int:
        return len(self._cols["trial"])

    def __getitem__(self, key):
        return self._cols[key]


class _FakeSim:
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
        self.calls.append((seed, rates[min(rates)]))
        ids = [kc for _ in range(n_trials) for kc in rates]
        trials = [t for t in range(n_trials) for _ in rates]
        return _FakeSpikes(ids, trials), {}


def test_simulate_missing_runs_only_missing_files_and_writes_no_verdict(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    missing = {(0.64, "NO", 20260318), (0.94, "YES", 20260316)}
    write_all(runner, tmp_path, ids, curve(MONOTONE), skip=missing)
    sim = _FakeSim()
    import run_population_scaling_diagnostic as psd
    monkeypatch.setattr(psd, "_build_population_simulator", lambda: sim)
    runner.simulate_missing(tmp_path, ids, log=lambda _: None)
    assert sorted(seed for seed, _ in sim.calls) == [20260316, 20260318]
    saved = json.loads(runner.output_path(0.64, "NO", 20260318, tmp_path).read_text())
    runner.check_presentation_file(saved)
    assert saved["framing"] == "NO" and saved["presented_price_value"] == pytest.approx(0.36)
    assert saved["pool_rates_hz"]["price"] == pytest.approx(73.2)
    assert saved["pair_d_yes_hz"] - saved["pair_d_no_hz"] == pytest.approx(3_360.0)
    assert set(saved["per_trial_rates_hz"]) == {"kenyon_cells", "mbons", "apl_neurons"}
    assert not runner.verdict_path(tmp_path).exists()


def test_simulate_missing_builds_no_model_when_everything_exists(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids, curve(MONOTONE))
    import run_population_scaling_diagnostic as psd

    def boom():
        raise AssertionError("model built although every file exists")

    monkeypatch.setattr(psd, "_build_population_simulator", boom)
    runner.simulate_missing(tmp_path, ids, log=lambda _: None)


# ---- dry run and flags --------------------------------------------------------------------- #
def test_dry_run_prints_the_plan_and_writes_nothing(tmp_path, capsys) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    out = tmp_path / "results"
    assert runner.main(["--dry-run", "--results-dir", str(out), "--ids", str(ids)]) == 0
    text = capsys.readouterr().out
    for fragment in ("DRY RUN", "THIS IS A VALIDATION", "all hold", "planned simulations: 60",
                     "to run: 60", "estimated runtime: 54.5 min", "50.6 min"):
        assert fragment in text, fragment
    assert "PASS" not in text
    assert not out.exists()


def test_dry_run_counts_completed_work(tmp_path, capsys) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids, curve(MONOTONE),
              skip={p for p in runner.planned_presentations() if p[2] == runner.PRIMARY_SEED})
    runner.dry_run(tmp_path, ids)
    text = capsys.readouterr().out
    assert "already done: 50, to run: 10" in text
    assert f"estimated runtime: {(10 * 54.4 + 4) / 60:.1f} min" in text


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
