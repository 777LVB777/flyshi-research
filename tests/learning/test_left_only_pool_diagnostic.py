"""Left-only pool diagnostic: stimulus, statistics and guards.

FAKE DATA ONLY for every simulated quantity. The real simulator is never
constructed, the connectome is never opened, and no simulation is run. The frozen
neuron-ID table is read as data, the way the runner reads it. Pre-stated protocol:
docs/design/left-only-pool-diagnostic.md.
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
SCRIPT = REPO / "repro" / "mushroom_body" / "run_left_only_pool_diagnostic.py"
DOC = REPO / "docs" / "design" / "left-only-pool-diagnostic.md"
IDS = REPO / "repro" / "mushroom_body" / "neuron_ids_783.json"


def load_runner():
    spec = importlib.util.spec_from_file_location("left_only_runner_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def approach_label() -> str:
    return next(name for name, weight in gc.load_sign_table("circuit_80").weights.items()
                if weight == 1)


def fake_ids_file(path: Path, n_left: int = 300, n_right: int = 300) -> Path:
    """A stand-in neuron-ID table: left KCs first, then right."""
    records = [{"root_id": 1000 + i, "side": "left"} for i in range(n_left)]
    records += [{"root_id": 5000 + i, "side": "right"} for i in range(n_right)]
    path.write_text(json.dumps({"kenyon_cells": {"records": records}}))
    return path


def write_fake(runner, directory: Path, *, spread_per_seed, apl_per_seed=None,
               mbon_per_seed=None, condition: str = None, stimulated=None,
               n_free: int = 100) -> None:
    """One fake MBON and ``n_free`` non-stimulated KCs whose active fraction is set
    per seed, so contained (0.0) and ignited runs can both be produced."""
    directory.mkdir(parents=True, exist_ok=True)
    label = approach_label()
    stimulated = stimulated or list(range(1000, 1100))
    # inside the fake ID table's ranges, and clear of every stimulated set used here
    free_left = [1150 + i for i in range(n_free // 2)]
    free_right = [5200 + i for i in range(n_free // 2)]
    kc_ids = list(stimulated) + free_left + free_right
    for index, seed in enumerate(runner.SEEDS):
        fraction = spread_per_seed[index]
        n_active = int(round(fraction * n_free))
        free_rates = [5.0] * n_active + [0.0] * (n_free - n_active)
        payload = {
            "condition": condition or "left_only_100at150",
            "pool_name": runner.POOL_NAME,
            "pool_side": runner.POOL_SIDE,
            "n_kcs_driven": len(stimulated),
            "per_kc_rate_hz": runner.RATE_HZ,
            "total_drive_hz": len(stimulated) * runner.RATE_HZ,
            "stimulated_kc_ids": list(stimulated),
            "mbon_labels": [label],
            "population_ids": {
                "mbons": [1], "kenyon_cells": kc_ids, "apl_neurons": [2, 3],
                "pam_dopamine_neurons": [4], "ppl1_dopamine_neurons": [5],
            },
            "rates_hz": {
                "mbons": [float((mbon_per_seed or [10.0] * 6)[index])],
                "kenyon_cells": [runner.RATE_HZ] * len(stimulated) + free_rates,
                "apl_neurons": [float((apl_per_seed or [200.0] * 6)[index])] * 2,
                "pam_dopamine_neurons": [1.0],
                "ppl1_dopamine_neurons": [2.0],
            },
            "seed": seed,
            "duration_ms": runner.DURATION_MS,
            "trials": runner.TRIALS,
        }
        name = (directory / f"population_scaling_{condition}_seed_{seed}.json") if condition \
            else runner.output_path(seed, directory)
        name.write_text(json.dumps(payload))


# ---- the plan is the pre-stated one ---------------------------------------------- #
def test_spec_pins_the_stimulus_and_its_diagnostic_status() -> None:
    text = " ".join(DOC.read_text().split())
    for needle in ("**Status: PRE-STATED; NOT RUN.**", "`is_a_validation: false`",
                   "**No pass criterion**", "**6 simulations.**", "150 Hz",
                   "left-hemisphere KCs only", "Cannot:",
                   "Separate hemisphere from identity in one step"):
        assert needle in text, needle


def test_runner_constants_match_the_pre_statement() -> None:
    runner = load_runner()
    assert runner.POOL_NAME == "recent_change" and runner.POOL_SIDE == "left"
    assert runner.RATE_HZ == 150.0
    assert runner.SEEDS == (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
    assert (runner.DURATION_MS, runner.TRIALS) == (1000.0, 5)
    assert runner.BILATERAL_CONDITION == "anchor_100at150"
    assert runner.IGNITION_SPREAD_FRACTION == 0.01


# ---- the stimulus ---------------------------------------------------------------- #
def test_pool_is_one_hundred_left_hemisphere_kcs_from_the_real_table() -> None:
    """Read as data: no simulator, no connectome."""
    runner = load_runner()
    pool = runner.left_only_pool(IDS)
    sides = runner.kc_side_map(IDS)
    assert len(pool) == 100
    assert {sides[i] for i in pool} == {"left"}
    assert len(runner.left_kc_ids(IDS)) == 2580
    assert runner.stimulus(IDS) == {i: 150.0 for i in pool}


def test_pool_is_deterministic_and_differs_from_the_bilateral_pool() -> None:
    runner = load_runner()
    assert runner.left_only_pool(IDS) == runner.left_only_pool(IDS)
    bilateral = REPO / "repro" / "mushroom_body" / "results" / \
        "population_scaling_anchor_100at150_seed_20260316.json"
    if bilateral.exists():  # only once the population-scaling run exists
        other = {int(i) for i in json.loads(bilateral.read_text())["stimulated_kc_ids"]}
        assert set(runner.left_only_pool(IDS)) != other


def test_a_right_hemisphere_contaminated_table_is_rejected(tmp_path) -> None:
    """The one-sidedness of the pool is the point, so it is asserted, not assumed."""
    runner = load_runner()
    ids = tmp_path / "ids.json"
    records = [{"root_id": 1000 + i, "side": "left"} for i in range(50)]
    records += [{"root_id": 5000 + i, "side": "right"} for i in range(400)]
    ids.write_text(json.dumps({"kenyon_cells": {"records": records}}))
    with pytest.raises(Exception):  # too few left KCs for the encoder's pools
        runner.left_only_pool(ids)


# ---- the measurement ------------------------------------------------------------- #
def test_summary_reports_statistics_and_no_verdict(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_fake(runner, tmp_path, spread_per_seed=[0.0, 0.66, 0.0, 0.65, 0.66, 0.0])
    summary = runner.summarise(tmp_path, ids, log=lambda _: None)
    assert summary["is_a_validation"] is False
    assert summary["has_pass_criterion"] is False
    assert "verdict" not in summary
    text = json.dumps(summary)
    for banned in ("PASS", "FAIL", "ACCEPTED", "USABLE RANGE"):
        assert banned not in text, banned
    left = summary["left_only"]
    for key in ("score_sd", "mbon_vector_distance_hz", "active_mbons", "apl_mean_rate_hz",
                "nonstimulated_kc_active_fraction_per_seed", "ignited_per_seed",
                "ignited_runs", "pam_mean_rate_hz", "ppl1_mean_rate_hz"):
        assert key in left


def test_ignition_label_counts_runs_and_is_declared_not_a_criterion(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_fake(runner, tmp_path, spread_per_seed=[0.0, 0.66, 0.0, 0.65, 0.66, 0.0])
    summary = runner.summarise(tmp_path, ids, log=lambda _: None)
    left = summary["left_only"]
    assert left["ignited_per_seed"] == [False, True, False, True, True, False]
    assert left["ignited_runs"] == 3
    assert "not a pass criterion" in left["ignition_label_note"]


def test_a_fully_contained_fake_and_a_fully_ignited_fake_both_read_out(tmp_path) -> None:
    """A fake that must NOT be reported as contained: every run spreads."""
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    contained = tmp_path / "contained"
    write_fake(runner, contained, spread_per_seed=[0.0] * 6)
    quiet = runner.summarise(contained, ids, log=lambda _: None)["left_only"]
    assert quiet["ignited_runs"] == 0
    assert quiet["nonstimulated_kc_active_fraction"] == 0.0

    ignited = tmp_path / "ignited"
    write_fake(runner, ignited, spread_per_seed=[0.66] * 6,
               mbon_per_seed=[10.0, 60.0, 30.0, 80.0, 20.0, 70.0])
    loud = runner.summarise(ignited, ids, log=lambda _: None)["left_only"]
    assert loud["ignited_runs"] == 6
    assert loud["nonstimulated_kc_active_fraction"] == pytest.approx(0.66)
    assert loud["score_sd"] > 20.0


def test_spread_is_reported_per_hemisphere(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_fake(runner, tmp_path, spread_per_seed=[0.0, 0.5, 0.0, 0.5, 0.5, 0.0])
    left = runner.summarise(tmp_path, ids, log=lambda _: None)["left_only"]
    by_side = left["nonstimulated_kc_active_fraction_by_side_per_seed"]
    assert len(by_side) == 6 and set(by_side[0]) == {"left", "right"}
    # the fakes activate the left free KCs first, so a 50% overall spread is left-only
    assert by_side[1]["left"] == pytest.approx(1.0)
    assert by_side[1]["right"] == pytest.approx(0.0)


def test_apl_rates_are_recorded_per_seed(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_fake(runner, tmp_path, spread_per_seed=[0.0] * 6,
               apl_per_seed=[166.0, 253.0, 190.0, 200.0, 210.0, 199.0])
    left = runner.summarise(tmp_path, ids, log=lambda _: None)["left_only"]
    assert left["apl_per_seed_mean_hz"] == pytest.approx([166, 253, 190, 200, 210, 199])


def test_bilateral_reference_is_used_when_present_and_absent_otherwise(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_fake(runner, tmp_path, spread_per_seed=[0.0, 0.66, 0.0, 0.65, 0.66, 0.0])
    assert runner.summarise(tmp_path, ids, log=lambda _: None)["bilateral_reference"] is None

    write_fake(runner, tmp_path, spread_per_seed=[0.0, 0.66, 0.66, 0.65, 0.66, 0.0],
               condition=runner.BILATERAL_CONDITION,
               stimulated=list(range(1000, 1050)) + list(range(5000, 5050)))
    summary = runner.summarise(tmp_path, ids, log=lambda _: None)
    reference = summary["bilateral_reference"]
    assert reference["condition"] == "anchor_100at150"
    assert reference["ignited_runs"] == 4
    assert reference["pool_side_counts"] == {"left": 50, "right": 50}
    assert "not separated by this run alone" in summary["comparison_note"]


# ---- completeness, restartability, and staying off the model --------------------- #
def test_no_summary_until_all_six_results_exist(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_fake(runner, tmp_path, spread_per_seed=[0.0] * 6)
    assert runner.missing_seeds(tmp_path) == []
    runner.output_path(runner.SEEDS[4], tmp_path).unlink()
    assert runner.missing_seeds(tmp_path) == [runner.SEEDS[4]]
    assert runner.summarise(tmp_path, ids, log=lambda _: None) is None
    assert not runner.summary_path(tmp_path).exists()


def test_mismatched_labels_between_seeds_are_an_error(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_fake(runner, tmp_path, spread_per_seed=[0.0] * 6)
    path = runner.output_path(runner.SEEDS[0], tmp_path)
    payload = json.loads(path.read_text())
    payload["mbon_labels"] = ["MBON99"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        runner.summarise(tmp_path, ids, log=lambda _: None)


def test_dry_run_prints_the_plan_and_writes_nothing(tmp_path, capsys) -> None:
    runner = load_runner()
    assert runner.main(["--dry-run", "--results-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "planned simulations: 6" in out and "to run: 6" in out
    assert "no pass criterion" in out and "estimated runtime" in out
    assert "sides {'left': 100}" in out
    assert not any(tmp_path.iterdir())


def test_dry_run_counts_completed_work(tmp_path, capsys) -> None:
    runner = load_runner()
    fake_ids_file(tmp_path / "ids.json")
    write_fake(runner, tmp_path, spread_per_seed=[0.0] * 6)
    runner.output_path(runner.SEEDS[2], tmp_path).unlink()
    runner.main(["--dry-run", "--results-dir", str(tmp_path)])
    assert "already done: 5, to run: 1" in capsys.readouterr().out


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
