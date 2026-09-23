"""Unbalanced single-framing score diagnostic: plan, verdict logic and guards.

FAKE DATA ONLY. The real simulator is never constructed, the connectome is never
opened, and no simulation is run. Pre-stated protocol:
docs/design/unbalanced-single-framing-diagnostic.md.
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
SCRIPT = REPO / "repro" / "mushroom_body" / "run_unbalanced_g_diagnostic.py"
DOC = REPO / "docs" / "design" / "unbalanced-single-framing-diagnostic.md"


def load_runner():
    spec = importlib.util.spec_from_file_location("unbalanced_g_runner_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def approach_label() -> str:
    """A label the CIRCUIT-80 table weights +1, so score == rate for one instance."""
    return next(name for name, weight in gc.load_sign_table("circuit_80").weights.items()
                if weight == 1)


def write_fake(runner, directory: Path, rates, seed_offsets=None, per_seed=None) -> None:
    """One fake MBON instance per file.

    ``rates``: the base rate at each of the five values. ``seed_offsets``: a
    constant added to every value for that seed (noise that cancels in the mean).
    ``per_seed``: {seed: [rates...]} overriding the base for that seed.
    """
    directory.mkdir(parents=True, exist_ok=True)
    label = approach_label()
    offsets = seed_offsets or {seed: 0.0 for seed in runner.SEEDS}
    for seed in runner.SEEDS:
        values = list((per_seed or {}).get(seed, rates))
        for value, rate in zip(runner.VALUES, values):
            runner.output_path(value, directory, seed=seed).write_text(json.dumps({
                "feature_value": value,
                "mbon_labels": [label],
                "yes_mbon_rates_hz": [float(rate + offsets[seed])],
                "seed": seed,
            }))


# ---- the plan is the pre-stated one ---------------------------------------------- #
def test_spec_pins_the_value_set_seeds_and_rule() -> None:
    text = " ".join(DOC.read_text().split())
    for needle in ("**Status: PRE-STATED; NOT RUN.", "v = 0.05, 0.22, 0.41, 0.63, 0.88",
                   "36.0, 56.4, 79.2, 105.6, 135.6 Hz", "**30 simulations**",
                   "seed mean, not on one seed", "larger of the two endpoint noise estimates",
                   "This is a diagnostic, not a validation"):
        assert needle in text, needle


def test_runner_constants_match_the_pre_statement() -> None:
    runner = load_runner()
    assert runner.VALUES == (0.05, 0.22, 0.41, 0.63, 0.88)
    assert runner.SEEDS == (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
    assert (runner.DURATION_MS, runner.TRIALS) == (1000.0, 5)
    assert (runner.SIGN_TABLE, runner.AGGREGATION) == ("circuit_80", "type_mean")
    assert runner.NOISE_MARGIN == 3.0
    assert runner.FIXED_FEATURES == {"recent_change": 0.0, "time_to_resolution": 182.5,
                                     "liquidity": 0.5, "signal": 0.5}
    assert len(runner.planned_pairs()) == 30
    assert [runner.nominal_rate_hz(v) for v in runner.VALUES] == pytest.approx(
        [36.0, 56.4, 79.2, 105.6, 135.6])


def test_value_set_has_no_reflective_pair_and_no_midpoint() -> None:
    """The point of this set: reusable by a later contrast test without the
    redundancy or the structurally forced zero that broke the balanced run."""
    runner = load_runner()
    values = runner.VALUES
    assert all(abs(v - 0.5) > 1e-12 for v in values)
    sums = [a + b for i, a in enumerate(values) for b in values[i + 1:]]
    assert all(abs(s - 1.0) > 1e-12 for s in sums)
    # every mirrored partner stays inside the encoder's 30-150 Hz range
    assert all(30.0 <= runner.nominal_rate_hz(1 - v) <= 150.0 for v in values)


# ---- verdict logic --------------------------------------------------------------- #
def test_clean_monotone_fake_passes(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path, [10.0, 20.0, 30.0, 40.0, 50.0])
    result = runner.analyze(log=lambda _: None, results_dir=tmp_path)
    assert result.verdict == runner.PASS
    assert result.monotonic and result.direction == "increasing"
    assert result.mean_scores == pytest.approx((10.0, 20.0, 30.0, 40.0, 50.0))
    assert result.endpoint_distance_hz == pytest.approx(40.0)
    assert result.fail_reasons == ()


def test_non_monotone_fake_must_not_pass(tmp_path) -> None:
    """A fake with a scrambled sequence must FAIL even though its endpoints are
    far apart and its noise is zero."""
    runner = load_runner()
    write_fake(runner, tmp_path, [10.0, 50.0, 20.0, 60.0, 30.0])
    result = runner.analyze(log=lambda _: None, results_dir=tmp_path)
    assert result.verdict == runner.FAIL
    assert not result.monotonic
    assert any("not strictly monotonic" in reason for reason in result.fail_reasons)


def test_monotone_but_noise_dominated_fake_must_not_pass(tmp_path) -> None:
    """The failure mode this diagnostic exists to detect: a tidy monotone mean whose
    swing is smaller than the run-to-run noise of the same stimulus."""
    runner = load_runner()
    offsets = dict(zip(runner.SEEDS, (-5.0, -3.0, -1.0, 1.0, 3.0, 5.0)))
    write_fake(runner, tmp_path, [10.0, 11.0, 12.0, 13.0, 14.0], seed_offsets=offsets)
    result = runner.analyze(log=lambda _: None, results_dir=tmp_path)
    assert result.monotonic  # the mean sequence is clean ...
    assert result.verdict == runner.FAIL  # ... and it still must not pass
    assert result.endpoint_distance_hz == pytest.approx(4.0)
    assert result.endpoint_noise_hz == pytest.approx(70.0 / 15.0)
    assert result.threshold_hz == pytest.approx(3.0 * 70.0 / 15.0)
    assert any("below its measured threshold" in reason for reason in result.fail_reasons)


def test_ties_break_monotonicity(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path, [10.0, 20.0, 20.0, 40.0, 50.0])
    assert runner.analyze(log=lambda _: None, results_dir=tmp_path).verdict == runner.FAIL


# ---- the two approved judgement choices ------------------------------------------ #
def test_monotonicity_is_judged_on_the_six_seed_mean_not_one_seed(tmp_path) -> None:
    """Approved 2026-09-23 and scoped to this diagnostic: one seed's sequence may be
    scrambled by noise while the replicated mean is monotone."""
    runner = load_runner()
    scrambled = [10.0, 25.0, 15.0, 40.0, 50.0]  # not monotone on its own
    write_fake(runner, tmp_path, [10.0, 20.0, 30.0, 40.0, 50.0],
               per_seed={runner.SEEDS[0]: scrambled})
    result = runner.analyze(log=lambda _: None, results_dir=tmp_path)
    assert not gc.strictly_monotonic(result.per_seed_scores[runner.SEEDS[0]])[0]
    assert result.monotonic and result.verdict == runner.PASS
    assert result.mean_scores[1] == pytest.approx((25.0 + 20.0 * 5) / 6)


def test_endpoint_noise_takes_the_larger_of_the_two_endpoints(tmp_path) -> None:
    """Approved 2026-09-23: same-stimulus noise varied ~7x across stimuli in the
    balanced run, so the conservative endpoint is used and both are reported."""
    runner = load_runner()
    base = [10.0, 20.0, 30.0, 40.0, 50.0]
    noisy_high = {seed: base[:-1] + [50.0 + shift]
                  for seed, shift in zip(runner.SEEDS, (-6.0, -4.0, -2.0, 2.0, 4.0, 6.0))}
    write_fake(runner, tmp_path, base, per_seed=noisy_high)
    result = runner.analyze(log=lambda _: None, results_dir=tmp_path)
    assert result.low_endpoint_noise_hz == pytest.approx(0.0)
    assert result.high_endpoint_noise_hz > 0.0
    assert result.endpoint_noise_hz == pytest.approx(result.high_endpoint_noise_hz)
    assert result.threshold_hz == pytest.approx(3.0 * result.high_endpoint_noise_hz)


# ---- completeness, restartability, and what the verdict file records -------------- #
def test_no_verdict_until_all_thirty_results_exist(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path, [10.0, 20.0, 30.0, 40.0, 50.0])
    assert runner.missing_pairs(tmp_path) == []
    runner.output_path(runner.VALUES[2], tmp_path, seed=runner.SEEDS[3]).unlink()
    assert runner.missing_pairs(tmp_path) == [(runner.SEEDS[3], runner.VALUES[2])]
    assert runner.analyze(log=lambda _: None, results_dir=tmp_path) is None
    assert not (tmp_path / "unbalanced_g_diagnostic_verdict.json").exists()


def test_verdict_file_records_both_noises_the_rule_and_its_own_status(tmp_path) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path, [10.0, 20.0, 30.0, 40.0, 50.0])
    runner.analyze(log=lambda _: None, results_dir=tmp_path)
    saved = json.loads((tmp_path / "unbalanced_g_diagnostic_verdict.json").read_text())
    assert saved["prestated_diagnostic"] is True and saved["is_a_validation"] is False
    assert saved["verdict"] == runner.PASS
    assert saved["feature_values"] == list(runner.VALUES)
    assert saved["seeds"] == list(runner.SEEDS)
    assert len(saved["per_seed_scores"]) == 6
    assert saved["noise_margin"] == 3.0
    for key in ("low_endpoint_noise_hz", "high_endpoint_noise_hz", "endpoint_noise_hz",
                "same_stimulus_noise_hz", "mean_scores", "monotonic_six_seed_mean"):
        assert key in saved


def test_evaluate_rejects_wrong_seeds_or_missing_values() -> None:
    runner = load_runner()
    labels = [approach_label()]
    good = {seed: [np.array([float(i)]) for i in range(5)] for seed in runner.SEEDS}
    runner.evaluate_diagnostic(good, labels)  # does not raise
    with pytest.raises(ValueError):
        runner.evaluate_diagnostic({s: v for s, v in list(good.items())[:5]}, labels)
    with pytest.raises(ValueError):
        runner.evaluate_diagnostic({s: v[:4] for s, v in good.items()}, labels)


# ---- the dry run and analysis never touch the model ------------------------------ #
def test_dry_run_prints_the_plan_and_writes_nothing(tmp_path, capsys) -> None:
    runner = load_runner()
    assert runner.main(["--dry-run", "--results-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "planned simulations: 30" in out and "to run: 30" in out
    assert "estimated runtime" in out and "unbalanced" in out
    assert "No connectome loaded" in out
    assert not any(tmp_path.iterdir())


def test_dry_run_counts_completed_work(tmp_path, capsys) -> None:
    runner = load_runner()
    write_fake(runner, tmp_path, [10.0, 20.0, 30.0, 40.0, 50.0])
    runner.output_path(runner.VALUES[0], tmp_path, seed=runner.SEEDS[0]).unlink()
    runner.main(["--dry-run", "--results-dir", str(tmp_path)])
    assert "already done: 29, to run: 1" in capsys.readouterr().out


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
        "('brian2', 'run_first_learning_test', 'fast_runner', 'pandas')]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
