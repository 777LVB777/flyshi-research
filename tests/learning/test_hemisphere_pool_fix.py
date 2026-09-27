"""Left-hemisphere-only fix for the two graded encoding runners.

Both `run_graded_encoding_balanced.py` and `run_unbalanced_g_diagnostic.py` used
to build `KCEncoder(sim.kc_ids)` with ALL Kenyon cells (both hemispheres), even
though their own pre-statements required left-hemisphere-only pools
(`docs/design/bilateral-pool-draw-finding.md`). This tests the fix: both now
draw from `left_kc_ids()` and abort via `_assert_pools_left_only` if any drawn
KC is not annotated left.

FAKE DATA ONLY. The real simulator is never constructed, the connectome is never
opened, and no simulation is run. The frozen neuron-ID table is read as data
(the way the runners read it), not simulated.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "repro" / "mushroom_body"
BALANCED_SCRIPT = HERE / "run_graded_encoding_balanced.py"
UNBALANCED_SCRIPT = HERE / "run_unbalanced_g_diagnostic.py"
LEFT_ONLY_POOL_SCRIPT = HERE / "run_left_only_pool_diagnostic.py"
BALANCED_DOC = REPO / "docs" / "design" / "balanced-encoding-failure.md"
UNBALANCED_DOC = REPO / "docs" / "design" / "unbalanced-single-framing-diagnostic.md"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNERS = {
    "balanced": (BALANCED_SCRIPT, "graded_balanced_for_hemisphere_fix_test"),
    "unbalanced": (UNBALANCED_SCRIPT, "unbalanced_g_for_hemisphere_fix_test"),
}


@pytest.fixture(params=["balanced", "unbalanced"])
def runner(request):
    script, name = RUNNERS[request.param]
    return load(script, name)


def fake_ids_file(path: Path) -> Path:
    records = [{"root_id": 1000 + i, "side": "left"} for i in range(600)]
    records += [{"root_id": 5000 + i, "side": "right"} for i in range(600)]
    path.write_text(json.dumps({"kenyon_cells": {"records": records}}))
    return path


class _FakeEncoder:
    """Exposes only what `_assert_pools_left_only` reads: `.pools`, `.balance_pool`."""

    def __init__(self, pools: dict, balance_pool) -> None:
        self.pools = {name: np.array(ids) for name, ids in pools.items()}
        self.balance_pool = np.array(balance_pool)


# ---- importing no Brian2 ---------------------------------------------------- #
def test_importing_the_runners_constructs_no_model(runner) -> None:
    # load() above already imported the module; reaching here means importing
    # it did not construct FastRunnerSimulator or open the connectome.
    assert hasattr(runner, "simulate_missing")


# ---- both runners share one left-KC source, not two copies ------------------ #
def test_left_kc_ids_and_kc_side_map_are_the_shared_functions(runner) -> None:
    # The runner imports these via `from run_left_only_pool_diagnostic import ...`
    # (ordinary sys.path-based import, cached in sys.modules under that plain
    # name), not a private copy. Confirm the runner's names are that exact
    # module's functions, so the two graded runners cannot silently diverge from
    # run_left_only_pool_diagnostic's definition of "left".
    left_only_pool = sys.modules["run_left_only_pool_diagnostic"]
    assert runner.left_kc_ids is left_only_pool.left_kc_ids
    assert runner.kc_side_map is left_only_pool.kc_side_map


# ---- the guard itself --------------------------------------------------------- #
def test_assert_pools_left_only_passes_when_every_kc_is_left(runner, tmp_path) -> None:
    ids = fake_ids_file(tmp_path / "ids.json")
    encoder = _FakeEncoder(
        pools={
            "price": range(1000, 1100),
            "recent_change": range(1100, 1200),
            "time_to_resolution": range(1200, 1300),
            "liquidity": range(1300, 1400),
            "signal": range(1400, 1500),
        },
        balance_pool=range(1500, 1600),
    )
    runner._assert_pools_left_only(encoder, ids_path=ids)  # must not raise


def test_assert_pools_left_only_rejects_a_right_hemisphere_kc_in_a_feature_pool(
    runner, tmp_path
) -> None:
    ids = fake_ids_file(tmp_path / "ids.json")
    encoder = _FakeEncoder(
        pools={
            "price": range(1000, 1100),
            "recent_change": list(range(1100, 1199)) + [5000],  # one right KC
            "time_to_resolution": range(1200, 1300),
            "liquidity": range(1300, 1400),
            "signal": range(1400, 1500),
        },
        balance_pool=range(1500, 1600),
    )
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        runner._assert_pools_left_only(encoder, ids_path=ids)


def test_assert_pools_left_only_rejects_a_right_hemisphere_kc_in_the_balance_pool(
    runner, tmp_path
) -> None:
    ids = fake_ids_file(tmp_path / "ids.json")
    encoder = _FakeEncoder(
        pools={
            "price": range(1000, 1100),
            "recent_change": range(1100, 1200),
            "time_to_resolution": range(1200, 1300),
            "liquidity": range(1300, 1400),
            "signal": range(1400, 1500),
        },
        balance_pool=list(range(1500, 1599)) + [5099],  # one right KC
    )
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        runner._assert_pools_left_only(encoder, ids_path=ids)


def test_assert_pools_left_only_rejects_an_all_bilateral_draw(runner, tmp_path) -> None:
    """The exact shape of the original bug: every pool ~50/50 split."""
    ids = fake_ids_file(tmp_path / "ids.json")
    encoder = _FakeEncoder(
        pools={
            "price": list(range(1000, 1050)) + list(range(5000, 5050)),
            "recent_change": list(range(1050, 1100)) + list(range(5050, 5100)),
            "time_to_resolution": list(range(1100, 1150)) + list(range(5100, 5150)),
            "liquidity": list(range(1150, 1200)) + list(range(5150, 5200)),
            "signal": list(range(1200, 1250)) + list(range(5200, 5250)),
        },
        balance_pool=list(range(1250, 1400)) + list(range(5250, 5400)),
    )
    with pytest.raises(RuntimeError, match="not left-hemisphere"):
        runner._assert_pools_left_only(encoder, ids_path=ids)


# ---- source-level guard: simulate_missing must draw from left_kc_ids() ------- #
def test_simulate_missing_draws_from_left_kc_ids_and_asserts(runner) -> None:
    src = inspect.getsource(runner.simulate_missing)
    assert "KCEncoder(left_kc_ids())" in src
    assert "KCEncoder(sim.kc_ids)" not in src
    assert "_assert_pools_left_only(encoder)" in src


# ---- both docs note the fix postdates the recorded FAILs --------------------- #
def test_balanced_doc_notes_the_fix_postdates_the_recorded_fail() -> None:
    text = " ".join(BALANCED_DOC.read_text().split())
    assert "Fix status" in text
    assert "postdates" in text
    assert "No rerun has been performed" in text


def test_unbalanced_doc_notes_the_fix_postdates_the_recorded_fail() -> None:
    text = " ".join(UNBALANCED_DOC.read_text().split())
    assert "Fix status" in text
    assert "postdates" in text
    assert "No rerun has been performed" in text


# ---- neither doc's recorded verdict/numbers were altered by the fix --------- #
def test_balanced_doc_still_records_the_original_fail_numbers() -> None:
    text = " ".join(BALANCED_DOC.read_text().split())
    assert "FAIL" in text
    assert "+30.306" in text  # v=0.00 score, from the original recorded table
    assert "NOT VIABLE" in text


def test_unbalanced_doc_still_records_the_original_fail_verdict() -> None:
    text = " ".join(UNBALANCED_DOC.read_text().split())
    assert "VERDICT: FAIL" in text
    assert "321.90" in text  # endpoint distance, from the original recorded run
