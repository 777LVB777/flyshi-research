"""Population-scaling diagnostic: plan, statistics and guards.

FAKE DATA ONLY. The real simulator is never constructed, the connectome is never
opened, and no simulation is run. Pre-stated protocol:
docs/design/population-scaling-diagnostic.md.
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
from flyshi_research.learning.encoder import KCEncoder  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "repro" / "mushroom_body" / "run_population_scaling_diagnostic.py"
DOC = REPO / "docs" / "design" / "population-scaling-diagnostic.md"


def load_runner():
    spec = importlib.util.spec_from_file_location("population_scaling_runner_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def approach_label() -> str:
    return next(name for name, weight in gc.load_sign_table("circuit_80").weights.items()
                if weight == 1)


def write_fake(runner, directory: Path, *, mbon_by_condition=None, kc_active=0,
               apl_rate=0.0, seed_jitter=None) -> None:
    """Fake results for every (condition, seed).

    ``mbon_by_condition``: {condition: [rate per seed]} for the single fake MBON.
    ``kc_active``: how many NON-stimulated KCs fire. ``seed_jitter``: added to the
    MBON rate per seed, so score SD can be dialled per condition.
    """
    directory.mkdir(parents=True, exist_ok=True)
    label = approach_label()
    for condition in runner.CONDITIONS:
        n_stim = condition.n_kcs
        kc_ids = list(range(1000, 1000 + n_stim + 20))  # 20 non-stimulated KCs
        stimulated = kc_ids[:n_stim]
        for index, seed in enumerate(runner.SEEDS):
            base = (mbon_by_condition or {}).get(condition.name, [10.0] * len(runner.SEEDS))
            rate = base[index] + ((seed_jitter or {}).get(condition.name, 0.0) * index)
            kc_rates = [condition.rate_hz] * n_stim + \
                       [5.0] * kc_active + [0.0] * (20 - kc_active)
            runner.output_path(condition.name, seed, directory).write_text(json.dumps({
                "condition": condition.name,
                "role": condition.role,
                "n_kcs_driven": condition.n_kcs,
                "per_kc_rate_hz": condition.rate_hz,
                "total_drive_hz": condition.total_drive_hz,
                "pools": list(condition.pools()),
                "stimulated_kc_ids": stimulated,
                "mbon_labels": [label],
                "population_ids": {
                    "mbons": [1], "kenyon_cells": kc_ids, "apl_neurons": [2, 3],
                    "pam_dopamine_neurons": [4], "ppl1_dopamine_neurons": [5],
                },
                "rates_hz": {
                    "mbons": [float(rate)],
                    "kenyon_cells": [float(x) for x in kc_rates],
                    "apl_neurons": [float(apl_rate), float(apl_rate)],
                    "pam_dopamine_neurons": [1.0],
                    "ppl1_dopamine_neurons": [2.0],
                },
                "seed": seed,
                "duration_ms": runner.DURATION_MS,
                "trials": runner.TRIALS,
            }))


# ---- the plan is the pre-stated one ---------------------------------------------- #
def test_spec_pins_the_conditions_and_its_diagnostic_status() -> None:
    text = " ".join(DOC.read_text().split())
    for needle in ("**Status: PRE-STATED; NOT RUN.**", "is_a_validation: false",
                   "**It has no pass criterion**", "7 conditions × 6 seeds = 42 simulations",
                   "ladder_400", "drive_matched_500at30", "anchor_100at150",
                   "`recent_change`, `time_to_resolution`, `liquidity`, `signal`, `price`",
                   "Cannot:"):
        assert needle in text, needle


def test_conditions_match_the_pre_statement() -> None:
    runner = load_runner()
    assert [c.name for c in runner.CONDITIONS] == [
        "ladder_100", "ladder_200", "ladder_300", "ladder_400", "ladder_500",
        "drive_matched_500at30", "anchor_100at150"]
    assert [c.n_kcs for c in runner.CONDITIONS] == [100, 200, 300, 400, 500, 500, 100]
    assert [c.rate_hz for c in runner.CONDITIONS] == [90, 90, 90, 90, 90, 30, 150]
    assert runner.SEEDS == (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
    assert (runner.DURATION_MS, runner.TRIALS) == (1000.0, 5)
    assert len(runner.planned_pairs()) == 42
    assert runner.LADDER_POOL_ORDER == (
        "recent_change", "time_to_resolution", "liquidity", "signal", "price")


def test_the_drive_matched_pair_really_matches_on_drive() -> None:
    runner = load_runner()
    a, b = runner.BY_NAME["drive_matched_500at30"], runner.BY_NAME["anchor_100at150"]
    assert a.total_drive_hz == b.total_drive_hz == 15000.0
    assert a.n_kcs == 5 * b.n_kcs  # the only thing that differs
    # and 15,000 Hz is the validated cue's drive: 100 KCs at 150 Hz
    assert b.n_kcs == 100 and b.rate_hz == 150.0


def test_ladder_pools_are_nested_and_400_is_the_background() -> None:
    """Nesting matters: each rung adds KCs rather than re-drawing them, so the
    ladder varies count without also varying pool identity."""
    runner = load_runner()
    rungs = [c for c in runner.CONDITIONS if c.name.startswith("ladder_")]
    for earlier, later in zip(rungs, rungs[1:]):
        assert set(earlier.pools()) < set(later.pools())
    background = runner.BY_NAME["ladder_400"].pools()
    assert set(background) == {"recent_change", "time_to_resolution", "liquidity", "signal"}
    assert "price" not in background  # the unbalanced diagnostic's background exactly
    assert runner.BY_NAME["anchor_100at150"].pools() == runner.BY_NAME["ladder_100"].pools()


def test_stimulus_uses_the_encoder_pools_and_has_the_right_size() -> None:
    runner = load_runner()
    encoder = KCEncoder([900000000000000000 + i for i in range(2000)])
    for condition in runner.CONDITIONS:
        rates = runner.stimulus_for(encoder, condition)
        assert len(rates) == condition.n_kcs
        assert set(rates.values()) == {condition.rate_hz}
        pooled = set()
        for pool in condition.pools():
            pooled |= set(int(i) for i in encoder.pools[pool])
        assert set(rates) == pooled


# ---- the measurement ------------------------------------------------------------- #
def test_summary_reports_statistics_and_no_verdict(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path)
    summary = runner.summarise(results_dir=tmp_path, log=lambda _: None)
    assert summary["is_a_validation"] is False
    assert summary["has_pass_criterion"] is False
    assert "verdict" not in summary and "pass" not in summary
    text = json.dumps(summary)
    for banned in ("PASS", "FAIL", "ACCEPTED", "USABLE RANGE"):
        assert banned not in text, banned
    assert set(summary["conditions"]) == {c.name for c in runner.CONDITIONS}
    for stats in summary["conditions"].values():
        for key in ("score_sd", "mbon_vector_distance_hz", "active_mbons",
                    "apl_mean_rate_hz", "nonstimulated_kc_active_fraction",
                    "pam_mean_rate_hz", "ppl1_mean_rate_hz", "score_per_seed"):
            assert key in stats
        assert len(stats["score_per_seed"]) == 6


def test_score_sd_and_vector_distance_track_the_fake_noise(tmp_path) -> None:
    runner = load_runner()
    quiet = [10.0] * 6
    noisy = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    write_fake(runner, tmp_path, mbon_by_condition={
        "ladder_100": quiet, "ladder_500": noisy})
    summary = runner.summarise(results_dir=tmp_path, log=lambda _: None)
    assert summary["conditions"]["ladder_100"]["score_sd"] == pytest.approx(0.0)
    assert summary["conditions"]["ladder_500"]["score_sd"] > 15.0
    assert summary["conditions"]["ladder_100"]["mbon_vector_distance_hz"] == pytest.approx(0.0)
    assert summary["conditions"]["ladder_500"]["mbon_vector_distance_hz"] > 0.0


def test_ladder_table_is_ordered_by_kc_count(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path)
    summary = runner.summarise(results_dir=tmp_path, log=lambda _: None)
    counts = [row["n_kcs"] for row in summary["ladder"]]
    assert counts == [100, 200, 300, 400, 500]
    assert all("score_sd" in row and "active_mbons" in row for row in summary["ladder"])


def test_non_stimulated_kc_fraction_is_measured_not_assumed(tmp_path) -> None:
    """The antennal-lobe failure's sparseness signature; 0 and >0 must both read out."""
    runner = load_runner()
    write_fake(runner, tmp_path, kc_active=0)
    quiet = runner.summarise(results_dir=tmp_path, log=lambda _: None)
    assert quiet["conditions"]["ladder_100"]["nonstimulated_kc_active_fraction"] == 0.0

    other = tmp_path / "spreading"
    write_fake(runner, other, kc_active=10)  # 10 of 20 non-stimulated KCs firing
    spreading = runner.summarise(results_dir=other, log=lambda _: None)
    assert spreading["conditions"]["ladder_100"]["nonstimulated_kc_active_fraction"] == \
        pytest.approx(0.5)


def test_apl_rate_is_recorded_per_condition(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path, apl_rate=137.0)
    summary = runner.summarise(results_dir=tmp_path, log=lambda _: None)
    assert summary["conditions"]["ladder_500"]["apl_mean_rate_hz"] == pytest.approx(137.0)
    assert len(summary["conditions"]["ladder_500"]["apl_per_seed_mean_hz"]) == 6


def test_paired_comparisons_are_reported_with_their_caveats(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path)
    summary = runner.summarise(results_dir=tmp_path, log=lambda _: None)
    drive = summary["drive_matched_comparison"]
    assert drive["total_drive_hz"] == 15000.0
    assert "isolates count from drive" in drive["note"]
    assert set(drive) >= {"kc_100_at_150", "kc_500_at_30"}
    hist = summary["historical_comparison"]
    assert hist["historical_d_aa_hz"] == 5.10
    assert "not a replication" in hist["note"]


# ---- completeness, restartability, and staying off the model --------------------- #
def test_no_summary_until_all_forty_two_results_exist(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path)
    assert runner.missing_pairs(tmp_path) == []
    runner.output_path("ladder_300", runner.SEEDS[2], tmp_path).unlink()
    assert runner.missing_pairs(tmp_path) == [("ladder_300", runner.SEEDS[2])]
    assert runner.summarise(results_dir=tmp_path, log=lambda _: None) is None
    assert not runner.summary_path(tmp_path).exists()


def test_mismatched_labels_between_seeds_are_an_error(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path)
    path = runner.output_path("ladder_100", runner.SEEDS[0], tmp_path)
    payload = json.loads(path.read_text())
    payload["mbon_labels"] = ["MBON99"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        runner.summarise(results_dir=tmp_path, log=lambda _: None)


def test_dry_run_prints_the_plan_and_writes_nothing(tmp_path, capsys) -> None:
    runner = load_runner()
    assert runner.main(["--dry-run", "--results-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "planned simulations: 42" in out and "to run: 42" in out
    assert "no pass criterion" in out and "estimated runtime" in out
    assert "apl_neurons" in out
    assert not any(tmp_path.iterdir())


def test_dry_run_counts_completed_work(tmp_path, capsys) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path)
    runner.output_path("ladder_200", runner.SEEDS[1], tmp_path).unlink()
    runner.main(["--dry-run", "--results-dir", str(tmp_path)])
    assert "already done: 41, to run: 1" in capsys.readouterr().out


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
