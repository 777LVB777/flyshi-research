"""Low-drive ignition follow-up diagnostic: selection rule, statistics, no verdict.

FAKE simulator only; Brian2 is never imported and the connectome is never opened.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from test_synthetic_extremes_containment_diagnostic import (  # noqa: E402
    LEFT,
    _FakeSim,
    _patch_sim,
    fake_ids_file,
)

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "repro" / "mushroom_body"
SCRIPT = HERE / "run_low_drive_ignition_followup_diagnostic.py"
DOC = REPO / "docs" / "design" / "low-drive-ignition-followup-diagnostic.md"
IDS = HERE / "neuron_ids_783.json"


@pytest.fixture(scope="module")
def runner():
    spec = importlib.util.spec_from_file_location("low_drive_followup_runner_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_spec_pins_status_count_seeds_and_table(runner) -> None:
    text = " ".join(DOC.read_text().split())
    assert "THIS IS A DIAGNOSTIC, NOT A VALIDATION" in text and "**100 simulations**" in text
    assert runner.SEEDS == tuple(range(20261201, 20261211))
    for name, strength, seed, index, framing in runner.EXPECTED_SELECTION:
        assert f"| `{name}` | {strength}, {seed}, {index}, {framing} |" in text, name
    assert "Five of the six below-25 kHz presentations are one market" in text


def test_the_rule_reproduces_the_table_and_its_properties(runner) -> None:
    built = runner.build_stimuli(IDS)
    names = list(built)
    assert names == [row[0] for row in runner.EXPECTED_SELECTION] and len(names) == 10
    low = [s for n, s in built.items() if n.startswith("below25")]
    mid = [s for n, s in built.items() if n.startswith("band25_30")]
    assert len(low) == 6 and all(s["total_drive_hz"] < 25_000 for s in low)
    assert len(mid) == 4 and all(25_000 <= s["total_drive_hz"] < 30_000 for s in mid)
    mid_markets = {(s["selected"].market_seed, s["selected"].index) for s in mid}
    low_markets = {(s["selected"].market_seed, s["selected"].index) for s in low}
    assert len(mid_markets) == 4 and not mid_markets & low_markets
    for target, s in zip(runner.MID_TARGETS_HZ, mid):
        assert abs(s["total_drive_hz"] - target) < 500
    for s in built.values():
        assert len(s["stimulated_kc_ids"]) == 500


def test_a_changed_selection_aborts_before_any_model(runner, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner, "EXPECTED_SELECTION", runner.EXPECTED_SELECTION[1:])
    sim = _FakeSim()
    _patch_sim(monkeypatch, sim)
    with pytest.raises(RuntimeError, match="no longer reproduces"):
        runner.simulate_missing(tmp_path, IDS, log=lambda m: None)
    assert sim.calls == []


def test_clopper_pearson_matches_known_values(runner) -> None:
    lo, hi = runner.clopper_pearson(2, 8)
    assert lo == pytest.approx(0.0319, abs=1e-4) and hi == pytest.approx(0.6509, abs=1e-4)
    assert runner.clopper_pearson(0, 18) == (0.0, pytest.approx(0.1853, abs=1e-4))
    assert runner.clopper_pearson(10, 10)[1] == 1.0
    assert runner.clopper_pearson(0, 0) == (None, None)


def test_fisher_one_sided_matches_hand_values(runner) -> None:
    # 2/8 vs 0/18: P = C(8,2)/C(26,2) = 28/325
    assert runner.fisher_one_sided_greater(2, 8, 0, 18) == pytest.approx(28 / 325)
    assert runner.fisher_one_sided_greater(0, 10, 0, 10) == pytest.approx(1.0)
    assert runner.fisher_one_sided_greater(1, 0, 0, 5) is None


def test_runs_one_hundred_then_reports_rates_per_run_and_per_trial(runner, monkeypatch, tmp_path) -> None:
    ids = fake_ids_file(tmp_path / "ids.json")
    out = tmp_path / "out"
    stimuli = runner.build_stimuli(ids)
    stimulated = set().union(*(s["stimulated_kc_ids"] for s in stimuli.values()))
    free = [k for k in LEFT if k not in stimulated]
    sim = _FakeSim(recruit=free[:50])  # every trial of every run labelled ignited
    _patch_sim(monkeypatch, sim)
    runner.simulate_missing(out, ids, log=lambda m: None)
    assert len(sim.calls) == 100
    summary = runner.summarise(out, ids, log=lambda m: None)
    runner.check_no_verdict(summary)
    assert summary["is_a_validation"] is False and summary["has_pass_criterion"] is False
    pooled = summary["pooled"]["all"]
    assert pooled["runs_any_trial_ignited"]["k"] == 100 and pooled["trials_ignited"]["n"] == 500
    assert summary["pooled"]["below25"]["runs_any_trial_ignited"]["n"] == 60
    assert summary["pooled"]["band25_30"]["runs_any_trial_ignited"]["n"] == 40
    s = summary["stimuli"]["below25_1"]
    assert s["trials_ignited"]["k"] == 50 and s["apl_hz_ignited_trials_mean"] is not None
    # no neighbouring files in this directory: bands are empty, readings absent
    for band in summary["neighbour_comparison"]["bands"].values():
        assert band["runs_trial_mean_label"]["n"] == 0 and band["reading_runs"] is None


def test_neighbour_comparison_reads_the_saved_bands(runner) -> None:
    results = HERE / "results"
    if not list(results.glob("left_only_scaling_left_ladder_300_seed_*.json")):
        pytest.skip("saved left-only results not present")
    quiet = [{"ignited_trial_mean": False, "trial_ignited": [False] * 5}] * 100
    c = runner.neighbour_comparison(results, quiet)
    bands = c["bands"]
    assert bands["below_window_0_20khz"]["runs_trial_mean_label"]["n"] == 18
    assert bands["above_window_30_40khz"]["runs_trial_mean_label"]["n"] == 20
    assert bands["above_window_40_70khz"]["runs_trial_mean_label"]["n"] == 134
    assert all(b["runs_trial_mean_label"]["k"] == 0 for b in bands.values())
    assert sum(r["ignited_trial_mean"] for r in c["prior_runs_in_window"]) == 2
    assert all(b["reading_runs"] == "not distinguishable" for b in bands.values())


def test_dry_run_simulates_and_writes_nothing(runner, monkeypatch, tmp_path, capsys) -> None:
    sim = _FakeSim()
    _patch_sim(monkeypatch, sim)
    assert runner.main(["--dry-run", "--results-dir", str(tmp_path / "r"), "--ids", str(IDS)]) == 0
    text = capsys.readouterr().out
    assert "simulations to run: 100 of 100" in text and "not a validation" in text
    assert sim.calls == [] and not (tmp_path / "r").exists()
