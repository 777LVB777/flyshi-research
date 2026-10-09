"""Synthetic-market extremes containment diagnostic: selection rule, guards, no verdict.

FAKE simulator only; Brian2 is never imported and the connectome is never opened.
The frozen neuron-ID table is read as data where the real pools are checked.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import graded_check as gc  # noqa: E402
from flyshi_research.learning.encoder import BALANCE_FEATURE  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "repro" / "mushroom_body"
SCRIPT = HERE / "run_synthetic_extremes_containment_diagnostic.py"
DOC = REPO / "docs" / "design" / "synthetic-extremes-containment-diagnostic.md"
IDS = HERE / "neuron_ids_783.json"
VALIDATION_FILE = HERE / "results" / "graded_left_mirrored_value_0p94_YES_seed_20260316.json"

LEFT = list(range(1000, 2000))
RIGHT = list(range(5000, 5600))
ALL_KCS = LEFT + RIGHT


def load_runner():
    spec = importlib.util.spec_from_file_location("synthetic_extremes_runner_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return load_runner()


def fake_ids_file(path: Path) -> Path:
    records = [{"root_id": i, "side": "left"} for i in LEFT]
    records += [{"root_id": i, "side": "right"} for i in RIGHT]
    path.write_text(json.dumps({"kenyon_cells": {"records": records}}))
    return path


def approach_label() -> str:
    return next(n for n, w in gc.load_sign_table("circuit_80").weights.items() if w == 1)


class _FakeSpikes:
    def __init__(self, flywire_id, trial) -> None:
        self._cols = {"flywire_id": list(flywire_id), "trial": list(trial)}

    def __len__(self) -> int:
        return len(self._cols["trial"])

    def __getitem__(self, key):
        return self._cols[key]


class _FakeSim:
    """Population simulator stand-in. ``recruit`` free KCs fire in every trial."""

    def __init__(self, recruit=()) -> None:
        self.population_ids = {"mbons": [1], "kenyon_cells": ALL_KCS, "apl_neurons": [2, 3],
                               "pam_dopamine_neurons": [4], "ppl1_dopamine_neurons": [5]}
        order = [i for p in self.population_ids.values() for i in p]
        flyid2i = {f: n for n, f in enumerate(order)}
        self.population_index = {p: np.array([flyid2i[i] for i in ids])
                                 for p, ids in self.population_ids.items()}
        self.bundle = {"params": {}, "flyid2i": flyid2i, "n": len(order)}
        self._ms, self._fr = 1.0, self
        self.mbon_type_labels = [approach_label()]
        self.recruit = list(recruit)
        self.calls = []

    def run_cue_rates(self, bundle, rates, n_trials, seed, name):
        self.calls.append((seed, dict(rates)))
        ids, trials = [], []
        for t in range(n_trials):
            ids += list(rates) + self.recruit + [1]
            trials += [t] * (len(rates) + len(self.recruit) + 1)
        return _FakeSpikes(ids, trials), {}


def _patch_sim(monkeypatch, sim):
    import run_population_scaling_diagnostic as ps
    monkeypatch.setattr(ps, "_build_population_simulator", lambda: sim)


# ---- the pre-statement ------------------------------------------------------- #
def test_spec_pins_the_diagnostic_status_count_and_seeds(runner) -> None:
    text = " ".join(DOC.read_text().split())
    assert "THIS IS A DIAGNOSTIC, NOT A VALIDATION" in text
    assert "`is_a_validation: false`" in text and "**12 simulations**" in text
    assert "20261101 and 20261102" in text
    assert runner.SEEDS == (20261101, 20261102)
    assert (runner.DURATION_MS, runner.TRIALS) == (1000.0, 5)
    assert "REVISION 2026-10-09 (before any run): `recent_change` bound ±1" in text
    revised = text[text.index("REVISION 2026-10-09 (before any run)"):text.index("SUPERSEDED")]
    for name, strength, seed, index, framing in runner.EXPECTED_SELECTION:
        assert f"| `{name}` | {strength}, {seed}, {index}, {framing} |" in revised, name
    assert "106 of 5,000 presentations (2.12%)" in text


def test_importing_and_dry_run_import_no_brian2() -> None:
    import subprocess
    code = (f"import sys; sys.argv = ['x', '--dry-run', '--results-dir', '/nonexistent-dir']\n"
            f"import runpy; runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n")
    check = "import sys; assert 'brian2' not in sys.modules, 'brian2 imported'"
    # run_path exits via SystemExit(0); check sys.modules in an atexit hook
    code = "import atexit\natexit.register(lambda: exec(" + repr(check) + "))\n" + code
    subprocess.run([sys.executable, "-c", code], check=True, cwd=REPO, capture_output=True)


# ---- the selection rule ------------------------------------------------------- #
def test_the_rule_reproduces_the_pre_stated_table(runner) -> None:
    built = runner.build_stimuli(IDS)
    assert list(built) == [row[0] for row in runner.EXPECTED_SELECTION]
    markets = {(s["selected"].market_seed, s["selected"].index) for s in built.values()}
    assert len(markets) == 6  # one pick per market
    drives = [built[f"highest_drive_{i}"]["total_drive_hz"] for i in (1, 2, 3)]
    assert all(d > 60_000 for d in drives) and drives == sorted(drives, reverse=True)
    assert built["lowest_price_rate"]["pool_rates_hz"]["price"] < 37.2
    assert built["highest_price_rate"]["pool_rates_hz"]["price"] > 142.8
    assert built["lowest_drive"]["total_drive_hz"] < 39_600


def test_every_stimulus_is_left_only_unbalanced_500_kcs(runner) -> None:
    sides = runner.kc_side_map(IDS)
    for name, stim in runner.build_stimuli(IDS).items():
        assert len(stim["stimulated_kc_ids"]) == 500, name
        assert BALANCE_FEATURE not in stim["pool_rates_hz"]
        assert all(sides[k] == "left" for k in stim["stimulated_kc_ids"])


@pytest.mark.skipif(not VALIDATION_FILE.exists(), reason="validation result file not present")
def test_pools_are_the_accepted_validations_pools(runner) -> None:
    saved = json.loads(VALIDATION_FILE.read_text())["pools"]
    stim = runner.build_stimuli(IDS)["highest_drive_1"]
    for pool, members in saved.items():
        assert stim["pools"][pool] == sorted(int(i) for i in members), pool


def test_a_changed_selection_aborts_before_any_model_is_built(runner, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner, "EXPECTED_SELECTION", runner.EXPECTED_SELECTION[:-1])
    sim = _FakeSim()
    _patch_sim(monkeypatch, sim)
    with pytest.raises(RuntimeError, match="no longer reproduces"):
        runner.simulate_missing(tmp_path, IDS, log=lambda m: None)
    assert sim.calls == [] and not any(tmp_path.iterdir())


def test_a_right_hemisphere_pool_kc_aborts_before_any_model_is_built(runner, monkeypatch, tmp_path) -> None:
    ids = fake_ids_file(tmp_path / "ids.json")
    monkeypatch.setattr(runner, "left_kc_ids", lambda path: ALL_KCS)  # a bilateral draw
    sim = _FakeSim()
    _patch_sim(monkeypatch, sim)
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        runner.simulate_missing(tmp_path / "out", ids, log=lambda m: None)
    assert sim.calls == []


# ---- simulation and summary on the fake ------------------------------------- #
def test_runs_twelve_then_summarises_a_bare_measurement(runner, monkeypatch, tmp_path) -> None:
    ids = fake_ids_file(tmp_path / "ids.json")
    out = tmp_path / "out"
    stimuli = runner.build_stimuli(ids)
    stimulated = set().union(*(s["stimulated_kc_ids"] for s in stimuli.values()))
    free = [k for k in LEFT if k not in stimulated]
    sim = _FakeSim(recruit=free[:50])  # ~5% of free KCs active: labelled ignited
    _patch_sim(monkeypatch, sim)
    runner.simulate_missing(out, ids, log=lambda m: None)
    assert len(sim.calls) == 12
    assert {seed for seed, _ in sim.calls} == set(runner.SEEDS)
    runner.simulate_missing(out, ids, log=lambda m: None)  # all exist: nothing re-run
    assert len(sim.calls) == 12
    summary = runner.summarise(out, ids, log=lambda m: None)
    assert summary["is_a_validation"] is False and summary["has_pass_criterion"] is False
    runner.check_no_verdict(summary)
    for row in summary["table"]:
        assert row["ignited_runs"] == 2
        assert row["recruited_kc_mean_rate_hz_over_recruiting_seeds"] is not None
    saved = json.loads(runner.output_path("highest_drive_1", runner.SEEDS[0], out).read_text())
    assert saved["sweep_presentation"]["framing"] == runner.EXPECTED_SELECTION[0][4]
    assert set(saved["per_trial_rates_hz"]) == {"kenyon_cells", "mbons", "apl_neurons"}


def test_no_summary_until_every_file_exists(runner, monkeypatch, tmp_path) -> None:
    ids = fake_ids_file(tmp_path / "ids.json")
    assert runner.summarise(tmp_path / "empty", ids, log=lambda m: None) is None


def test_dry_run_simulates_and_writes_nothing(runner, monkeypatch, tmp_path, capsys) -> None:
    sim = _FakeSim()
    _patch_sim(monkeypatch, sim)
    assert runner.main(["--dry-run", "--results-dir", str(tmp_path / "r"), "--ids", str(IDS)]) == 0
    text = capsys.readouterr().out
    assert "simulations to run: 12 of 12" in text and "not a validation" in text
    assert sim.calls == [] and not (tmp_path / "r").exists()
