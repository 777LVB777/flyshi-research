"""Left-only population-scaling diagnostic: stimulus, statistics and guards.

FAKE DATA ONLY for every simulated quantity. The real simulator is never
constructed, the connectome is never opened, and no simulation is run. The frozen
neuron-ID table is read as data, the way the runner reads it. Pre-stated protocol:
docs/design/left-only-population-scaling-diagnostic.md.
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
SCRIPT = HERE / "run_left_only_population_scaling_diagnostic.py"
LEFT_ONLY_SCRIPT = HERE / "run_left_only_pool_diagnostic.py"
DOC = REPO / "docs" / "design" / "left-only-population-scaling-diagnostic.md"
IDS = HERE / "neuron_ids_783.json"
RESULTS = HERE / "results"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_runner():
    return load(SCRIPT, "left_only_scaling_runner_test")


def approach_label() -> str:
    return next(name for name, weight in gc.load_sign_table("circuit_80").weights.items()
                if weight == 1)


# fake ID table ranges: left 1000-1599, right 5000-5599
FREE_LEFT = [1500 + i for i in range(50)]
FREE_RIGHT = [5400 + i for i in range(50)]


def fake_ids_file(path: Path) -> Path:
    records = [{"root_id": 1000 + i, "side": "left"} for i in range(600)]
    records += [{"root_id": 5000 + i, "side": "right"} for i in range(600)]
    path.write_text(json.dumps({"kenyon_cells": {"records": records}}))
    return path


def left_stimulated(n: int):
    return list(range(1000, 1000 + n))


def bilateral_stimulated(n: int):
    return list(range(1000, 1000 + n // 2)) + list(range(5000, 5000 + n // 2))


def write_seed_files(runner, path_for, *, condition: str, stimulated, spread_per_seed,
                     stim_rate=None, apl_per_seed=None, mbon_per_seed=None,
                     labels=None) -> None:
    """``spread_per_seed``: the fraction of the 100 fake free KCs active per seed.
    Free LEFT KCs are activated first, so a 50% spread is all-left."""
    free = FREE_LEFT + FREE_RIGHT
    kc_ids = list(stimulated) + free
    for index, seed in enumerate(runner.SEEDS):
        n_active = int(round(spread_per_seed[index] * len(free)))
        free_rates = [5.0] * n_active + [0.0] * (len(free) - n_active)
        payload = {
            "condition": condition,
            "n_kcs_driven": len(stimulated),
            "per_kc_rate_hz": runner.RATE_HZ,
            "total_drive_hz": len(stimulated) * runner.RATE_HZ,
            "stimulated_kc_ids": list(stimulated),
            "mbon_labels": labels or [approach_label()],
            "population_ids": {
                "mbons": [1], "kenyon_cells": kc_ids, "apl_neurons": [2, 3],
                "pam_dopamine_neurons": [4], "ppl1_dopamine_neurons": [5],
            },
            "rates_hz": {
                "mbons": [float((mbon_per_seed or [10.0] * 6)[index])],
                "kenyon_cells": [stim_rate or runner.RATE_HZ] * len(stimulated) + free_rates,
                "apl_neurons": [float((apl_per_seed or [150.0] * 6)[index])] * 2,
                "pam_dopamine_neurons": [1.0],
                "ppl1_dopamine_neurons": [2.0],
            },
            "seed": seed,
            "duration_ms": runner.DURATION_MS,
            "trials": runner.TRIALS,
        }
        target = path_for(condition, seed)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload))


CONTAINED = [0.0] * 6
IGNITED = [0.66] * 6


def write_all(runner, directory: Path, *, left_spread=None, bilateral_spread=None,
              **kwargs) -> None:
    """Fake left-only and bilateral files for every rung; spreads keyed by KC count."""
    left_spread = left_spread or {}
    bilateral_spread = bilateral_spread or {}
    for c in runner.CONDITIONS:
        write_seed_files(runner, lambda n, s: runner.output_path(n, s, directory),
                         condition=c.name, stimulated=left_stimulated(c.n_kcs),
                         spread_per_seed=left_spread.get(c.n_kcs, CONTAINED), **kwargs)
        write_seed_files(runner, lambda n, s: runner.bilateral_path(n, s, directory),
                         condition=c.bilateral, stimulated=bilateral_stimulated(c.n_kcs),
                         spread_per_seed=bilateral_spread.get(c.n_kcs, CONTAINED))


# ---- the plan is the pre-stated one ---------------------------------------------- #
def test_spec_pins_the_ladder_and_its_diagnostic_status() -> None:
    text = " ".join(DOC.read_text().split())
    for needle in ("**Status: PRE-STATED; NOT RUN.**", "`is_a_validation: false`",
                   "**No pass criterion**", "**4 conditions × 6 seeds = 24 simulations.**",
                   "**90 Hz**", "left-hemisphere KCs only", "**Nested**",
                   "rerun rather than reused", "**150 Hz**", "Cannot:",
                   "Separate hemisphere from pool draw", "Test a five-pool stimulus",
                   "`bilateral_reference`", "about 20.3 minutes"):
        assert needle in text, needle


def test_runner_constants_match_the_pre_statement() -> None:
    runner = load_runner()
    assert [(c.name, c.n_kcs, c.bilateral) for c in runner.CONDITIONS] == [
        ("left_ladder_100", 100, "ladder_100"), ("left_ladder_200", 200, "ladder_200"),
        ("left_ladder_300", 300, "ladder_300"), ("left_ladder_500", 500, "ladder_500"),
    ]
    assert runner.RATE_HZ == 90.0 and runner.POOL_SIDE == "left"
    assert runner.SEEDS == (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
    assert (runner.DURATION_MS, runner.TRIALS) == (1000.0, 5)
    assert runner.LADDER_POOL_ORDER == (
        "recent_change", "time_to_resolution", "liquidity", "signal", "price")
    assert len(runner.planned_pairs()) == 24


# ---- the stimulus ---------------------------------------------------------------- #
def test_rungs_are_nested_left_only_and_the_right_size_from_the_real_table() -> None:
    """Read as data: no simulator, no connectome."""
    runner = load_runner()
    rungs = runner.left_ladder_pools(IDS)
    sides = runner.kc_side_map(IDS)
    previous: set = set()
    for c in runner.CONDITIONS:
        kcs = rungs[c.name]
        assert len(kcs) == len(set(kcs)) == c.n_kcs
        assert {sides[i] for i in kcs} == {"left"}
        assert previous <= set(kcs)
        previous = set(kcs)
        assert runner.stimulus_for(c, IDS) == {i: 90.0 for i in kcs}
    assert runner.left_ladder_pools(IDS) == rungs  # deterministic


def test_the_100_rung_is_the_left_only_diagnostic_pool_but_not_its_stimulus() -> None:
    """Same pool; different rate. That is why the rung is rerun, not reused."""
    runner = load_runner()
    left_only = load(LEFT_ONLY_SCRIPT, "left_only_runner_for_scaling_test")
    assert runner.left_ladder_pools(IDS)["left_ladder_100"] == left_only.left_only_pool(IDS)
    assert left_only.RATE_HZ == 150.0 != runner.RATE_HZ
    for seed in runner.SEEDS:
        assert runner.output_path("left_ladder_100", seed) != left_only.output_path(seed)
    existing = RESULTS / "left_only_pool_seed_20260316.json"
    if existing.exists():
        assert json.loads(existing.read_text())["per_kc_rate_hz"] == 150.0


def test_overlap_with_the_committed_bilateral_rungs_is_as_stated() -> None:
    runner = load_runner()
    rungs = runner.left_ladder_pools(IDS)
    expected = {"ladder_100": 3, "ladder_200": 10, "ladder_300": 20, "ladder_500": 50}
    for c in runner.CONDITIONS:
        path = runner.bilateral_path(c.bilateral, runner.SEEDS[0], RESULTS)
        if not path.exists():
            pytest.skip("bilateral population-scaling results not present")
        other = {int(i) for i in json.loads(path.read_text())["stimulated_kc_ids"]}
        assert len(set(rungs[c.name]) & other) == expected[c.bilateral]


class _FakeEncoder:
    pools_by_name: dict = {}

    def __init__(self, kc_ids) -> None:
        self.pools = {k: np.array(v) for k, v in self.pools_by_name.items()}


def _fake_pools(names, blocks):
    return dict(zip(names, blocks))


def test_overlapping_pools_are_rejected(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    blocks = [list(range(1000, 1100))] * 5  # every pool the same 100 KCs
    monkeypatch.setattr(_FakeEncoder, "pools_by_name",
                        _fake_pools(runner.LADDER_POOL_ORDER, blocks))
    monkeypatch.setattr(runner, "KCEncoder", _FakeEncoder)
    with pytest.raises(RuntimeError, match="expected 200 KCs"):
        runner.left_ladder_pools(ids)


def test_a_right_hemisphere_kc_in_a_pool_is_rejected(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    blocks = [list(range(1000 + 100 * k, 1100 + 100 * k)) for k in range(5)]
    blocks[1] = list(range(5000, 5100))  # second pool is right-hemisphere
    monkeypatch.setattr(_FakeEncoder, "pools_by_name",
                        _fake_pools(runner.LADDER_POOL_ORDER, blocks))
    monkeypatch.setattr(runner, "KCEncoder", _FakeEncoder)
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        runner.left_ladder_pools(ids)


# ---- the measurement ------------------------------------------------------------- #
def test_summary_reports_statistics_and_no_verdict(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, bilateral_spread={200: IGNITED, 300: IGNITED, 500: IGNITED})
    summary = runner.summarise(tmp_path, ids, log=lambda _: None)
    assert summary["is_a_validation"] is False
    assert summary["has_pass_criterion"] is False
    assert "verdict" not in summary and "pass" not in summary
    text = json.dumps(summary)
    for banned in ("PASS", "FAIL", "ACCEPTED", "USABLE RANGE"):
        assert banned not in text, banned
    for name, stats in summary["conditions"].items():
        for key in ("ignited_runs", "ignited_per_seed",
                    "nonstimulated_kc_active_fraction_by_side_per_seed",
                    "active_mbons", "active_mbons_per_seed", "apl_mean_rate_hz",
                    "apl_per_seed_mean_hz", "score_mean", "score_sd", "score_per_seed",
                    "stimulated_kc_imposed_rate_hz",
                    "stimulated_kc_measured_rate_per_seed_hz",
                    "stimulated_kc_measured_over_imposed"):
            assert key in stats, (name, key)
    assert "not a five-pool encoder stimulus" in summary["comparison_note"]
    assert "150 Hz" in summary["not_reused_note"]


def test_bilateral_reference_mirrors_the_left_only_statistics(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, bilateral_spread={200: IGNITED, 300: IGNITED, 500: IGNITED})
    summary = runner.summarise(tmp_path, ids, log=lambda _: None)
    reference = summary["bilateral_reference"]
    assert list(reference) == ["ladder_100", "ladder_200", "ladder_300", "ladder_500"]
    assert set(reference["ladder_200"]) >= set(summary["conditions"]["left_ladder_200"]) - {"pools"}
    assert [reference[k]["ignited_runs"] for k in reference] == [0, 6, 6, 6]
    assert reference["ladder_200"]["pool_side_counts"] == {"left": 100, "right": 100}
    assert summary["conditions"]["left_ladder_200"]["pool_side_counts"] == {"left": 200}
    # fake bilateral left half is 1000..1099, inside the left rung's 1000..1199
    assert reference["ladder_200"]["kcs_shared_with_left_only_rung"] == 100
    assert reference["ladder_200"]["left_only_counterpart"] == "left_ladder_200"


def test_ladder_table_puts_left_and_bilateral_side_by_side(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path,
              left_spread={300: [0.0, 0.66, 0.0, 0.66, 0.0, 0.0], 500: IGNITED},
              bilateral_spread={200: IGNITED, 300: IGNITED, 500: IGNITED})
    ladder = runner.summarise(tmp_path, ids, log=lambda _: None)["ladder"]
    assert [row["n_kcs"] for row in ladder] == [100, 200, 300, 500]
    assert [row["ignited_runs_left_only"] for row in ladder] == [0, 0, 2, 6]
    assert [row["ignited_runs_bilateral"] for row in ladder] == [0, 6, 6, 6]
    assert ladder[3]["total_drive_hz"] == 45_000


def test_spread_is_split_by_hemisphere_per_seed(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, left_spread={200: [0.0, 0.5, 0.0, 1.0, 0.0, 0.0]})
    stats = runner.summarise(tmp_path, ids, log=lambda _: None)["conditions"]["left_ladder_200"]
    by_side = stats["nonstimulated_kc_active_fraction_by_side_per_seed"]
    assert len(by_side) == 6 and set(by_side[0]) == {"left", "right"}
    assert by_side[1] == {"left": pytest.approx(1.0), "right": pytest.approx(0.0)}
    assert by_side[3] == {"left": pytest.approx(1.0), "right": pytest.approx(1.0)}
    assert stats["ignited_per_seed"] == [False, True, False, True, False, False]


def test_measured_stimulated_rate_is_reported_against_imposed(tmp_path) -> None:
    """A fake whose driven KCs fire at half the imposed rate must say so."""
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, stim_rate=45.0)
    stats = runner.summarise(tmp_path, ids, log=lambda _: None)["conditions"]["left_ladder_100"]
    assert stats["stimulated_kc_imposed_rate_hz"] == 90.0
    assert stats["stimulated_kc_measured_rate_per_seed_hz"] == pytest.approx([45.0] * 6)
    assert stats["stimulated_kc_measured_over_imposed"] == pytest.approx(0.5)


def test_apl_active_mbons_and_score_spread_read_out_from_the_fakes(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, apl_per_seed=[166.0, 253.0, 190.0, 200.0, 210.0, 199.0],
              mbon_per_seed=[10.0, 60.0, 30.0, 80.0, 20.0, 70.0])
    stats = runner.summarise(tmp_path, ids, log=lambda _: None)["conditions"]["left_ladder_500"]
    assert stats["apl_per_seed_mean_hz"] == pytest.approx([166, 253, 190, 200, 210, 199])
    assert stats["active_mbons_per_seed"] == [1] * 6
    assert stats["score_sd"] > 20.0


# ---- completeness, restartability, and staying off the model --------------------- #
def test_no_summary_until_all_twenty_four_left_only_results_exist(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path)
    assert runner.missing_pairs(tmp_path) == []
    runner.output_path("left_ladder_300", runner.SEEDS[4], tmp_path).unlink()
    assert runner.missing_pairs(tmp_path) == [("left_ladder_300", runner.SEEDS[4])]
    assert runner.summarise(tmp_path, ids, log=lambda _: None) is None
    assert not runner.summary_path(tmp_path).exists()


def test_no_summary_without_the_bilateral_reference(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path)
    runner.bilateral_path("ladder_500", runner.SEEDS[0], tmp_path).unlink()
    messages = []
    assert runner.summarise(tmp_path, ids, log=messages.append) is None
    assert "bilateral reference" in messages[0]
    assert not runner.summary_path(tmp_path).exists()


def test_mismatched_labels_between_seeds_are_an_error(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path)
    path = runner.output_path("left_ladder_100", runner.SEEDS[0], tmp_path)
    payload = json.loads(path.read_text())
    payload["mbon_labels"] = ["MBON99"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        runner.summarise(tmp_path, ids, log=lambda _: None)


def test_dry_run_prints_the_plan_and_writes_nothing(tmp_path, capsys) -> None:
    runner = load_runner()
    assert runner.main(["--dry-run", "--results-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "planned simulations: 24" in out and "to run: 24" in out
    assert "no pass criterion" in out and "estimated runtime: 20.3 min" in out
    assert "{'left': 500}" in out and "NOT reused" in out
    assert "bilateral reference files: 0 of 24 present" in out
    assert not any(tmp_path.iterdir())


def test_dry_run_counts_completed_work(tmp_path, capsys) -> None:
    runner = load_runner()
    write_all(runner, tmp_path)
    runner.output_path("left_ladder_200", runner.SEEDS[2], tmp_path).unlink()
    runner.main(["--dry-run", "--results-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "already done: 23, to run: 1" in out
    assert "bilateral reference files: 24 of 24 present" in out


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
