from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import graded_check as gc  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "repro" / "mushroom_body" / "run_graded_encoding_balanced.py"
DOC = REPO / "docs" / "design" / "graded-encoding-balanced.md"


def load_runner():
    spec = importlib.util.spec_from_file_location("balanced_graded_runner_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fake_value_files(runner, directory: Path, values) -> None:
    table = gc.load_sign_table("circuit_80")
    label = next(name for name, weight in table.weights.items() if weight != 0)
    seeds = runner.NOISE_SEEDS + (runner.PRIMARY_SEED,)
    for seed_index, seed in enumerate(seeds):
        # Small seed-dependent slope makes the measured change noise nonzero.
        slope_noise = (seed_index - 2) * 0.05 if seed != runner.PRIMARY_SEED else 0.0
        for value_index, (value, mbon_value) in enumerate(zip(runner.VALUES, values)):
            payload = {
                "feature_value": value,
                "mbon_labels": [label],
                "yes_mbon_rates_hz": [float(mbon_value + slope_noise * value_index)],
                "no_mbon_rates_hz": [0.0],
            }
            runner.output_path(value, directory, seed=seed).write_text(json.dumps(payload))


def test_balanced_spec_pins_three_outcomes_and_feature_value_axis() -> None:
    text = " ".join(DOC.read_text().split())
    for needle in (
        "**Status: PRE-STATED; NOT RUN.**",
        "**SUPERSEDED**",
        "0.00, 0.25, 0.50, 0.75, 1.00",
        "nominal, pre-balance YES price-pool rate",
        "**ACCEPTED**",
        "**USABLE RANGE**",
        "**FAIL**",
        "longest strictly monotonic **contiguous** sub-range",
        "there is no fallback",
        "`d_AA = 5.10 Hz` is **not used",
        "`sqrt(2) × d_AA`",
        "d_change(a,b)",
        "50` dedicated noise-floor simulations",
        "60 results",
    ):
        assert needle in text


def test_balanced_analysis_fake_that_should_pass_and_fake_that_must_not(tmp_path) -> None:
    runner = load_runner()
    passing = tmp_path / "passing"
    passing.mkdir()
    write_fake_value_files(runner, passing, [0.0, 10.0, 20.0, 30.0, 40.0])
    passed = runner.analyze(log=lambda _: None, results_dir=passing)
    assert passed.verdict is gc.Verdict.ACCEPTED
    assert passed.endpoint_noise_hz > 0.0
    assert passed.endpoint_threshold_hz == pytest.approx(3.0 * passed.endpoint_noise_hz)

    failing = tmp_path / "failing"
    failing.mkdir()
    write_fake_value_files(runner, failing, [5.0, 5.0, 5.0, 5.0, 5.0])
    assert runner.analyze(log=lambda _: None, results_dir=failing).verdict is gc.Verdict.FAIL


def test_analyzer_refuses_verdict_without_dedicated_noise_files(tmp_path) -> None:
    runner = load_runner()
    table = gc.load_sign_table("circuit_80")
    label = next(name for name, weight in table.weights.items() if weight != 0)
    for value in runner.VALUES:
        runner.output_path(value, tmp_path).write_text(
            json.dumps(
                {
                    "mbon_labels": [label],
                    "yes_mbon_rates_hz": [value],
                    "no_mbon_rates_hz": [0.0],
                }
            )
        )
    assert runner.analyze(log=lambda _: None, results_dir=tmp_path) is None
