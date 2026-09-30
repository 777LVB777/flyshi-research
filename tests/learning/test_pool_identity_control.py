"""Pool-identity control (DIAGNOSTIC): stimuli, statistics, readings, enforcement,
restart and flags.

FAKE DATA ONLY. The ID table is a fake written to tmp_path, every MBON/KC rate is
a fake, the real simulator is never constructed, the connectome is never opened,
and no simulation is run. Pre-stated protocol: docs/design/pool-identity-control.md.

Fakes use two MBON instances of one type that CIRCUIT-80 weights +1. The per-type
mean then scores their mean, so with m_yes = 100 + (c +/- g)/2 and m_no = 100 -
(c +/- g)/2 the score is S = c, while g moves the vector without moving the score.
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
SCRIPT = HERE / "run_pool_identity_control.py"
DOC = REPO / "docs" / "design" / "pool-identity-control.md"


def load_runner():
    spec = importlib.util.spec_from_file_location("pool_identity_control_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def wobble(k: int, i: int) -> float:
    """Deterministic zero-ish noise in [-1, 1] for seed index k, value index i."""
    return ((k * 7 + i * 3) % 5 - 2) / 2.0


def arm(f, g=(0.0, 0.0, 0.0), amp=0.3, g_amp=0.3):
    """Scalar contrast f[i] and score-invisible vector component g[i], plus noise."""
    def c(runner, seed, i):
        k = runner.SEEDS.index(seed)
        return f[i] + amp * wobble(k, i), g[i] + g_amp * wobble(k + 2, i)
    return c


BASE = [-4.0, -16.0, -29.0]


def fake_payload(runner, value, framing, seed, stim, mbons, repro=False):
    stimulated = set(stim["stimulated_kc_ids"])
    pool_of = {kc: pool for pool, members in stim["pools"].items() for kc in members}
    kc_row = [stim["pool_rates_hz"][pool_of[kc]] if kc in stimulated else 0.0 for kc in ALL_KCS]
    return {
        "value": value, "framing": framing,
        "presented_price_value": runner.mirrored.presented_value(value, framing),
        "variant": "unbalanced", "pool_side": "left",
        "pools": stim["pools"], "pool_rates_hz": stim["pool_rates_hz"],
        "n_kcs_driven": len(stimulated), "total_drive_hz": stim["total_drive_hz"],
        "stimulated_kc_ids": stim["stimulated_kc_ids"],
        "mbon_labels": [approach_label(), approach_label()],
        "population_ids": {"mbons": [1, 6], "kenyon_cells": ALL_KCS, "apl_neurons": [2, 3],
                           "pam_dopamine_neurons": [4], "ppl1_dopamine_neurons": [5]},
        "rates_hz": {"mbons": mbons, "kenyon_cells": kc_row, "apl_neurons": [150.0, 150.0],
                     "pam_dopamine_neurons": [1.0], "ppl1_dopamine_neurons": [2.0]},
        "per_trial_rates_hz": {"kenyon_cells": [kc_row] * runner.TRIALS,
                               "mbons": [mbons] * runner.TRIALS,
                               "apl_neurons": [[150.0, 150.0]] * runner.TRIALS},
        "seed": seed, "duration_ms": 1000.0, "trials": runner.TRIALS,
    }


def mbon_pair(c: float, g: float, framing: str):
    sign = 1 if framing == "YES" else -1
    return [100.0 + sign * (c + g) / 2, 100.0 + sign * (c - g) / 2]


def write_all(runner, directory: Path, ids: Path, p_arm, q_arm, skip=(), skip_price=(),
              skip_repro=False, repro_shift=0.0):
    directory.mkdir(parents=True, exist_ok=True)
    built = runner.build_stimuli(ids)
    for value, framing, seed in runner.planned_presentations():
        i = runner.VALUES.index(value)
        arms = built["by_value"][value][framing]
        if (value, framing, seed) not in skip_price:
            pc, pg = p_arm(runner, seed, i)
            runner.price_arm_path(value, framing, seed, directory).write_text(json.dumps(
                fake_payload(runner, value, framing, seed, arms["P"], mbon_pair(pc, pg, framing))))
        if (value, framing, seed) not in skip:
            qc, qg = q_arm(runner, seed, i)
            runner.output_path(value, framing, seed, directory).write_text(json.dumps(
                fake_payload(runner, value, framing, seed, arms["Q"], mbon_pair(qc, qg, framing))))
    if not skip_repro:
        value, framing, seed = runner.REPRO_CHECK
        pc, pg = p_arm(runner, seed, runner.VALUES.index(value))
        mbons = [m + repro_shift for m in mbon_pair(pc, pg, framing)]
        runner.repro_path(directory).write_text(json.dumps(fake_payload(
            runner, value, framing, seed, built["by_value"][value][framing]["P"], mbons)))


def run(runner, tmp_path, p_arm, q_arm, **kw):
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path / "r", ids, p_arm, q_arm, **kw)
    return runner.summarise(tmp_path / "r", ids, log=lambda _: None), tmp_path / "r", ids


def primary(summary):
    return summary["changes"][summary["primary_change"]]


# ---- the pre-statement --------------------------------------------------------------- #
def test_spec_pins_the_design_and_its_diagnostic_status() -> None:
    text = " ".join(DOC.read_text().split())
    for needle in ("**Status: PRE-STATED, 2026-09-30; NOT RUN.**",
                   "**THIS IS A DIAGNOSTIC, NOT A VALIDATION**", "`is_a_validation: false`",
                   "`has_pass_criterion: false`", "no `verdict` field", "`check_no_verdict`",
                   "**Substitute-pool seed 20260930.**", "`V = (0.56, 0.73, 0.94)`",
                   "= **36**", "**Total: 37 simulations.**", "**PRIMARY:** `S(0.94)`",
                   "no independence assumption and no `√2` or `√n` factor",
                   "**have been seen**", "beyond the price arm's floor only",
                   "not a pass criterion", "run_pool_identity_control.py"):
        assert needle in text, needle


def test_runner_constants_match_the_pre_statement() -> None:
    runner = load_runner()
    runner.check_constants()
    assert runner.VALUES == (0.56, 0.73, 0.94)
    assert runner.SUBSTITUTE_SEED == 20260930 and runner.POOL_SIZE == 100
    assert runner.PRIMARY_CHANGE == (0.50, 0.94) and runner.NOISE_MARGIN == gc.NOISE_MARGIN
    assert runner.planned_simulations() == 37 and len(runner.planned_presentations()) == 36
    assert len(runner.splits()) == 10


@pytest.mark.parametrize("name,value", [("NOISE_MARGIN", 2.0), ("VALUES", (0.56, 0.94)),
                                        ("SUBSTITUTE_SEED", 1), ("PRIMARY_CHANGE", (0.56, 0.94))])
def test_a_changed_constant_is_refused(monkeypatch, name, value) -> None:
    runner = load_runner()
    monkeypatch.setattr(runner, name, value)
    with pytest.raises(ValueError):
        runner.check_constants()


# ---- stimuli -------------------------------------------------------------------------- #
def test_substitute_pool_is_left_disjoint_and_arms_match_in_drive(tmp_path) -> None:
    runner = load_runner()
    built = runner.build_stimuli(fake_ids_file(tmp_path / "ids.json"))
    q = built["substitute_pool"]
    encoder_ids = {i for ids in built["encoder_pools"].values() for i in ids}
    assert len(q) == 100 and len(encoder_ids) == 800
    assert set(q) <= set(LEFT) and not set(q) & encoder_ids
    for value in runner.VALUES:
        for framing in runner.FRAMINGS:
            p, s = built["by_value"][value][framing]["P"], built["by_value"][value][framing]["Q"]
            assert s["total_drive_hz"] == pytest.approx(p["total_drive_hz"], abs=1e-6)
            assert len(s["stimulated_kc_ids"]) == 500 and "price" not in s["pools"]
            assert s["pool_rates_hz"]["substitute"] == p["pool_rates_hz"]["price"]


def test_substitute_draw_is_deterministic_and_excludes_every_encoder_pool() -> None:
    runner = load_runner()
    ids = list(range(300))
    a = runner.draw_substitute_pool(ids, range(0, 200), seed=7, size=50)
    assert a == runner.draw_substitute_pool(list(reversed(ids)), range(0, 200), seed=7, size=50)
    assert min(a) >= 200 and len(set(a)) == 50
    with pytest.raises(RuntimeError):
        runner.draw_substitute_pool(ids, range(0, 260), seed=7, size=50)


def test_a_right_hemisphere_substitute_aborts(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    monkeypatch.setattr(runner, "draw_substitute_pool", lambda *a, **k: RIGHT[:100])
    with pytest.raises(RuntimeError, match="not left"):
        runner.build_stimuli(fake_ids_file(tmp_path / "ids.json"))


def test_a_substitute_overlapping_an_encoder_pool_aborts(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    real = runner.draw_substitute_pool

    def overlapping(left, excluded, *a, **k):
        return sorted(list(excluded)[:1] + real(left, excluded)[1:])

    monkeypatch.setattr(runner, "draw_substitute_pool", overlapping)
    with pytest.raises(RuntimeError):
        runner.build_stimuli(ids)


def test_arms_differing_in_more_than_the_swap_abort(monkeypatch) -> None:
    runner = load_runner()
    monkeypatch.setattr(runner, "N_KCS_PER_FRAMING", 3)
    p = {"rates_by_kc_id": {1: 90.0, 2: 90.0, 3: 50.0}, "pools": {"bg": [1, 2], "price": [3]},
         "pool_rates_hz": {"bg": 90.0, "price": 50.0}, "total_drive_hz": 230.0}
    q = runner.substitute_record(p, [3], [4])
    runner._check_arms(0.5, "YES", p, q, [3], [4])  # the pure swap is accepted
    # same KC count, drive and rate multiset, but a background KC's rate moved onto Q
    moved = dict(q, rates_by_kc_id={**q["rates_by_kc_id"], 1: 50.0, 4: 90.0})
    with pytest.raises(RuntimeError, match="background"):
        runner._check_arms(0.5, "YES", p, moved, [3], [4])
    wrong_drive = dict(q, total_drive_hz=231.0)
    with pytest.raises(RuntimeError, match="drive"):
        runner._check_arms(0.5, "YES", p, wrong_drive, [3], [4])


# ---- statistics ----------------------------------------------------------------------- #
def test_split_floor_and_cross_are_the_stated_means() -> None:
    runner = load_runner()
    p = {s: float(k) for k, s in enumerate(runner.SEEDS)}
    expected_w = np.mean([abs(np.mean([p[s] for s in h1]) - np.mean([p[s] for s in h2]))
                          for h1, h2 in runner.splits()])
    assert runner.split_floor(p) == pytest.approx(expected_w)
    assert runner.split_cross(p, p) == pytest.approx(expected_w)  # Q = P gives X = W
    shifted = {s: v + 10.0 for s, v in p.items()}
    assert runner.split_cross(shifted, p) > 3 * runner.split_floor(p)
    assert all(runner.SEEDS[0] in h1 and len(h1) == len(h2) == 3 for h1, h2 in runner.splits())


def test_reading_uses_the_price_floor_and_reports_the_larger_one() -> None:
    runner = load_runner()
    assert runner.reading(2.9, 1.0, 0.5) == (runner.WITHIN, runner.WITHIN)
    assert runner.reading(3.1, 1.0, 0.5) == (runner.BEYOND, runner.BEYOND)
    assert runner.reading(3.1, 1.0, 2.0) == (runner.BEYOND, runner.WITHIN)


# ---- outcomes, on fake data ------------------------------------------------------------ #
def test_identical_arms_read_within_noise_on_both(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, arm(BASE), arm(BASE))
    pr = primary(out)
    assert pr["primary"] and out["primary_change"] == "0.50->0.94"
    assert pr["scalar"]["reading"] == pr["vector"]["reading"] == runner.WITHIN
    assert pr["scalar"]["ratio_R"] == pytest.approx(1.0)
    assert pr["scalar"]["mean_P_hz"] == pytest.approx(np.mean(
        [BASE[2] + 0.3 * wobble(k, 2) for k in range(6)]))
    assert "largely generic drive" in out["primary_interpretation"]


def test_score_invisible_vector_difference_reads_scalar_within_vector_beyond(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, arm(BASE), arm(BASE, g=(5.0, 20.0, 40.0)))
    pr = primary(out)
    assert pr["scalar"]["reading"] == runner.WITHIN
    assert pr["vector"]["reading"] == runner.BEYOND
    assert pr["vector"]["cosine_P_Q"] < pr["vector"]["split_half_cosine_P"]
    assert pr["vector"]["orthogonal_component_hz"] > 0
    assert "present in the MBON vector" in out["primary_interpretation"]


def test_half_the_score_change_reads_beyond_noise_with_r_one_half(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, arm(BASE), arm([v / 2 for v in BASE]))
    pr = primary(out)
    assert pr["scalar"]["reading"] == pr["vector"]["reading"] == runner.BEYOND
    assert pr["scalar"]["ratio_R"] == pytest.approx(0.5, abs=0.02)
    assert "pool identity contributes" in out["primary_interpretation"]


def test_a_noisier_substitute_is_reported_as_beyond_the_price_floor_only(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, arm(BASE, amp=0.1), arm(BASE, amp=4.0))
    pr = primary(out)["scalar"]
    assert pr["reading"] == runner.BEYOND
    assert pr["reading_against_larger_floor"] == runner.WITHIN
    assert out["primary_price_floor_only"]["scalar"] is True


def test_flagged_scalar_with_vector_beyond_is_not_attributed_to_identity(tmp_path) -> None:
    """Spec 5.2: a scalar reading beyond only the price arm's floor is not attributed
    to pool identity, so the 5.3 'pool identity contributes to S' row is withheld."""
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, arm(BASE, amp=0.1), arm(BASE, g=(5.0, 20.0, 40.0), amp=4.0))
    pr = primary(out)
    assert pr["scalar"]["reading"] == runner.BEYOND
    assert pr["scalar"]["reading_against_larger_floor"] == runner.WITHIN
    assert pr["vector"]["reading"] == pr["vector"]["reading_against_larger_floor"] == runner.BEYOND
    assert out["primary_price_floor_only"] == {"scalar": True, "vector": False}
    text = out["primary_interpretation"]
    assert "pool identity contributes" not in text and "largely generic drive" not in text
    assert "scalar beyond the price arm's floor only: not attributed to pool identity" in text
    assert "pool identity is present in the MBON vector" in text


def _part(reading, larger):
    return {"reading": reading, "reading_against_larger_floor": larger}


@pytest.mark.parametrize("scalar,vector,present,absent", [
    (("beyond_noise", "within_noise"), ("beyond_noise", "beyond_noise"),
     ["scalar beyond the price arm's floor only", "present in the MBON vector"],
     ["contributes"]),
    (("beyond_noise", "within_noise"), ("within_noise", "within_noise"),
     ["scalar beyond the price arm's floor only", "vector within noise"],
     ["contributes", "generic drive"]),
    (("within_noise", "within_noise"), ("beyond_noise", "within_noise"),
     ["scalar within noise", "vector beyond the price arm's floor only"],
     ["present in the MBON vector", "generic drive"]),
    (("beyond_noise", "beyond_noise"), ("beyond_noise", "beyond_noise"),
     ["pool identity contributes to S"], ["floor only"]),
])
def test_interpretation_follows_the_robustness_flag(scalar, vector, present, absent) -> None:
    runner = load_runner()
    text = runner.interpretation({"scalar": _part(*scalar), "vector": _part(*vector)})
    for needle in present:
        assert needle in text, needle
    for needle in absent:
        assert needle not in text, needle


def test_only_step_changes_carry_single_seed_distances(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, arm(BASE), arm(BASE))
    for name, ch in out["changes"].items():
        has = ch["vector"]["d_change_P_hz"] is not None
        assert has == (not name.startswith("0.50"))
        assert ch["primary"] == (name == "0.50->0.94")


def test_reproducibility_check_is_labelled_when_it_differs(tmp_path) -> None:
    runner = load_runner()
    same, _, _ = run(runner, tmp_path / "a", arm(BASE), arm(BASE))
    assert same["reproducibility_check"]["identical"] is True
    changed, _, _ = run(runner, tmp_path / "b", arm(BASE), arm(BASE), repro_shift=0.25)
    rc = changed["reproducibility_check"]
    assert rc["identical"] is False and rc["label"] == runner.REPRO_CHANGED
    assert rc["max_abs_difference_hz"]["mbons"] == pytest.approx(0.25)
    assert "reading" in primary(changed)["scalar"]  # readings still computed, not suppressed


def test_substitute_rates_and_recruitment_are_reported_for_all_36(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, arm(BASE), arm(BASE))
    assert len(out["recruitment_by_substitute_presentation"]) == 36
    assert out["ignited_substitute_presentations"] == 0
    assert all(r["measured_over_imposed"] == pytest.approx(1.0)
               for r in out["substitute_rate_measured"])


# ---- refusal to summarise ---------------------------------------------------------------- #
@pytest.mark.parametrize("kw", [{"skip": {(0.73, "NO", 20260318)}},
                                {"skip_price": {(0.94, "YES", 20260321)}},
                                {"skip_repro": True}])
def test_no_summary_while_anything_is_missing(tmp_path, kw) -> None:
    runner = load_runner()
    out, directory, _ = run(runner, tmp_path, arm(BASE), arm(BASE), **kw)
    assert out is None and not runner.summary_path(directory).exists()


def test_a_file_whose_stimulus_is_not_the_pre_stated_one_is_refused(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path / "r", ids, arm(BASE), arm(BASE))
    path = runner.output_path(0.56, "YES", 20260317, tmp_path / "r")
    payload = json.loads(path.read_text())
    payload["pool_rates_hz"]["substitute"] = 90.0
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="saved stimulus differs"):
        runner.summarise(tmp_path / "r", ids, log=lambda _: None)


def test_a_presentation_file_carrying_a_verdict_is_refused(tmp_path) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path / "r", ids, arm(BASE), arm(BASE))
    path = runner.output_path(0.94, "NO", 20260316, tmp_path / "r")
    path.write_text(json.dumps({**json.loads(path.read_text()), "verdict": "x"}))
    with pytest.raises(ValueError):
        runner.summarise(tmp_path / "r", ids, log=lambda _: None)


# ---- diagnostic enforcement (the same check as the other diagnostics) ------------------------ #
def test_summary_is_a_bare_measurement_under_the_diagnostic_check(tmp_path) -> None:
    runner = load_runner()
    import run_left_only_realistic_drive_diagnostic as realistic
    assert runner.check_no_verdict is realistic.check_no_verdict
    for name, q in (("a", arm(BASE)), ("b", arm(BASE, g=(5.0, 20.0, 40.0))),
                    ("c", arm([v / 2 for v in BASE]))):
        out, directory, _ = run(runner, tmp_path / name, arm(BASE), q)
        saved = json.loads(runner.summary_path(directory).read_text())
        assert saved["is_a_validation"] is False and saved["has_pass_criterion"] is False
        assert "verdict" not in json.dumps(saved)
        runner.check_no_verdict(saved)


@pytest.mark.parametrize("change", [{"verdict": "within"}, {"is_a_validation": True},
                                    {"has_pass_criterion": True}, {"note": "FAIL"},
                                    {"note": "PASS"}])
def test_enforcement_rejects_validation_language(tmp_path, change) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, arm(BASE), arm(BASE))
    with pytest.raises(ValueError):
        runner.check_no_verdict({**out, **change})


@pytest.mark.xfail(strict=True, reason="canary: a summary carrying a verdict must never "
                   "get through the enforcement check; if this ever passes, the suite fails")
def test_canary_a_verdict_bearing_summary_gets_through(tmp_path) -> None:
    runner = load_runner()
    out, _, _ = run(runner, tmp_path, arm(BASE), arm(BASE))
    runner.check_no_verdict({**out, "verdict": "PASS"})


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
        self.population_ids = {"mbons": [1, 6], "kenyon_cells": ALL_KCS, "apl_neurons": [2, 3],
                               "pam_dopamine_neurons": [4], "ppl1_dopamine_neurons": [5]}
        order = [i for p in self.population_ids.values() for i in p]
        flyid2i = {f: n for n, f in enumerate(order)}
        self.population_index = {p: np.array([flyid2i[i] for i in ids])
                                 for p, ids in self.population_ids.items()}
        self.bundle = {"params": {}, "flyid2i": flyid2i, "n": len(order)}
        self._ms = 1.0
        self._fr = self
        self.mbon_type_labels = [approach_label(), approach_label()]
        self.calls = []

    def run_cue_rates(self, bundle, rates, n_trials, seed, name):
        self.calls.append((seed, frozenset(rates)))
        ids = [kc for _ in range(n_trials) for kc in rates]
        trials = [t for t in range(n_trials) for _ in rates]
        return _FakeSpikes(ids, trials), {}


def test_simulate_missing_runs_the_check_first_then_only_missing_files(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    missing = {(0.73, "NO", 20260318), (0.94, "YES", 20260316)}
    write_all(runner, tmp_path, ids, arm(BASE), arm(BASE), skip=missing, skip_repro=True)
    sim = _FakeSim()
    import run_population_scaling_diagnostic as psd
    monkeypatch.setattr(psd, "_build_population_simulator", lambda: sim)
    runner.simulate_missing(tmp_path, ids, log=lambda _: None)
    built = runner.build_stimuli(ids)
    price = frozenset(built["by_value"][0.94]["YES"]["P"]["rates_by_kc_id"])
    assert sim.calls[0] == (20260316, price)  # the reproducibility check, first
    assert sorted(seed for seed, _ in sim.calls[1:]) == [20260316, 20260318]
    saved = json.loads(runner.output_path(0.73, "NO", 20260318, tmp_path).read_text())
    assert saved["arm"] == "substitute" and saved["substitute_pool_seed"] == 20260930
    assert saved["pool_rates_hz"]["substitute"] == pytest.approx(62.4)
    assert set(saved["stimulated_kc_ids"]) >= set(built["substitute_pool"])
    assert saved["pair_d_yes_hz"] - saved["pair_d_no_hz"] == pytest.approx(5_520.0)
    assert set(saved["per_trial_rates_hz"]) == {"kenyon_cells", "mbons", "apl_neurons"}
    assert "verdict" not in json.dumps(saved)
    assert runner.repro_path(tmp_path).exists()
    assert not runner.summary_path(tmp_path).exists()


def test_simulate_missing_builds_no_model_when_everything_exists(tmp_path, monkeypatch) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids, arm(BASE), arm(BASE))
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
    for fragment in ("DRY RUN", "not a validation", "all hold", "planned simulations: 37",
                     "to run: 37", "estimated runtime: 33.6 min", "31.2 min",
                     "price arm: 0 of 36"):
        assert fragment in text, fragment
    assert "PASS" not in text
    assert not out.exists()


def test_dry_run_counts_completed_work(tmp_path, capsys) -> None:
    runner = load_runner()
    ids = fake_ids_file(tmp_path / "ids.json")
    write_all(runner, tmp_path, ids, arm(BASE), arm(BASE),
              skip={p for p in runner.planned_presentations() if p[2] == 20260321})
    runner.dry_run(tmp_path, ids)
    text = capsys.readouterr().out
    assert "already done: 31, to run: 6" in text and "price arm: 36 of 36" in text
    assert f"estimated runtime: {(6 * 54.4 + 4) / 60:.1f} min" in text


def test_dry_run_and_analyze_only_are_mutually_exclusive(tmp_path) -> None:
    runner = load_runner()
    with pytest.raises(SystemExit):
        runner.main(["--dry-run", "--analyze-only", "--results-dir", str(tmp_path)])


@pytest.mark.parametrize("flag", ["--dry-run", "--analyze-only"])
def test_flag_never_imports_brian2_or_a_backend(tmp_path, flag) -> None:
    ids = fake_ids_file(tmp_path / "ids.json")
    code = (
        "import sys, runpy\n"
        f"sys.argv = ['x', '{flag}', '--results-dir', {str(tmp_path / 'r')!r}, "
        f"'--ids', {str(ids)!r}]\n"
        "try:\n"
        f"    runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "('brian2', 'run_first_learning_test', 'fast_runner', 'check_mb_response', 'pandas')]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
