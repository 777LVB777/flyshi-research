"""Parallel execution, readout sensitivity variants and the plain-language report.

FAKE simulators only (from test_first_learning); the launcher is exercised with real
subprocesses whose worker runs one job on the fake simulator. Brian2 is never imported.
"""

from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import first_learning as fl  # noqa: E402
from test_first_learning import LABELS, FakeSim, all_results  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MB = REPO / "repro" / "mushroom_body"
TESTS = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, MB / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


L = load("launch_first_learning_parallel")
R = load("report_first_learning")
RUNNER = load("run_first_learning_test")
QUIET = dict(log=lambda s: None)


def sequential(base, cfg=None, sim=None):
    cfg = cfg or fl.ExperimentConfig()
    return fl.Experiment(sim or FakeSim(), cfg, base, **QUIET).run()


# ---- the job plan ------------------------------------------------------------------ #
def test_job_plan_covers_the_protocol_exactly_once():
    cfg = fl.ExperimentConfig()
    jobs = fl.plan_jobs(cfg)
    assert len(jobs) == 5 + 5 + 25 and len({j.id for j in jobs}) == len(jobs)
    assert sum(j.n_runs for j in jobs) == fl.run_count(cfg).total == 260
    ids = {j.id for j in jobs}
    for j in jobs:
        assert set(j.deps) <= ids
        if j.kind == "posttest":
            assert j.deps == (f"train:{j.condition}",)
        else:
            assert j.deps == ()  # training and pre-test depend on nothing
    assert fl.critical_path_runs(cfg) == 42  # 40 sequential training runs + one test seed


def test_jobs_in_separate_processes_any_order_give_identical_results(tmp_path):
    """Each job gets a FRESH simulator (as a separate process would), jobs run in a
    shuffled dependency-respecting order; the result files equal the sequential run's."""
    cfg = fl.ExperimentConfig()
    sequential(tmp_path / "seq", cfg)
    jobs = fl.plan_jobs(cfg)
    rng = random.Random(3)
    done, todo = set(), list(jobs)
    while todo:
        ready = [j for j in todo if set(j.deps) <= done]
        j = rng.choice(ready)
        fl.Experiment(FakeSim(), cfg, tmp_path / "par", **QUIET).run_job(j.id)
        todo.remove(j)
        done.add(j.id)
    fl.finish(fl.results_dir_for(tmp_path / "par", cfg), cfg)
    a, b = (all_results(fl.results_dir_for(tmp_path / x, cfg)) for x in ("seq", "par"))
    assert a == b and "verdict.json" in a and "condition_main.json" in a
    assert json.loads(a["verdict.json"])["verdict"] == fl.DEMONSTRATED


def test_posttest_refuses_to_run_before_its_training(tmp_path):
    exp = fl.Experiment(FakeSim(), fl.ExperimentConfig(), tmp_path, **QUIET)
    with pytest.raises(RuntimeError, match="needs train:main"):
        exp.run_job("posttest:main:20260317")
    with pytest.raises(ValueError, match="unknown job"):
        exp.run_job("train:nonexistent")


def test_a_finished_job_is_not_redone(tmp_path):
    cfg = fl.ExperimentConfig()
    fl.Experiment(FakeSim(), cfg, tmp_path, **QUIET).run_job("train:main")
    again = FakeSim()
    fl.Experiment(again, cfg, tmp_path, **QUIET).run_job("train:main")
    assert again.calls == 0


def test_merged_results_count_as_done_even_without_the_job_files(tmp_path):
    """E.g. only the merged files were copied back: nothing may be re-simulated."""
    import shutil
    cfg = fl.ExperimentConfig()
    sequential(tmp_path, cfg)
    d = fl.results_dir_for(tmp_path, cfg)
    shutil.rmtree(d / "parts")
    paths = fl.ResultPaths(d)
    assert all(paths.job_done(j) for j in fl.plan_jobs(cfg))
    again = FakeSim()
    assert fl.Experiment(again, cfg, tmp_path, **QUIET).run()["verdict"] == fl.DEMONSTRATED
    assert again.calls == 0


def test_verdict_from_files_alone_matches_and_needs_no_simulator(tmp_path):
    cfg = fl.ExperimentConfig()
    v = sequential(tmp_path, cfg)
    d = fl.results_dir_for(tmp_path, cfg)
    assert fl.evaluate_results(d, cfg) == json.loads((d / "verdict.json").read_text())
    assert json.loads(json.dumps(v)) == fl.evaluate_results(d, cfg)


def test_results_including_job_files_stay_under_1mb(tmp_path):
    labels = [m["cell_type"] for m in json.loads((MB / "neuron_ids_783.json").read_text())["mbons"]["records"]]
    sequential(tmp_path, sim=FakeSim(labels=labels, n_kc=300))
    d = fl.results_dir_for(tmp_path, fl.ExperimentConfig())
    total = sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
    assert 0 < total < 1_000_000, total


def test_config_round_trips_through_its_json():
    for cfg in (fl.ExperimentConfig(), fl.ExperimentConfig.smoke()):
        again = fl.ExperimentConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
        assert again == cfg and again.config_hash() == cfg.config_hash()


# ---- readout sensitivity variants ------------------------------------------------- #
def test_every_preregistered_variant_is_reported_and_never_changes_the_verdict(tmp_path):
    v = sequential(tmp_path)
    assert v["verdict"] == fl.DEMONSTRATED
    assert set(v["readout_sensitivity"]) == {
        "circuit_70", "circuit_90", "circuit_80_no_gamma3", "strict", "group",
        "circuit_80|instance_sum", fl.LEFT_ONLY_KEY}
    assert ("circuit_80_no_gamma3", "type_mean") in fl.READOUT_VARIANTS
    # circuit_70 is identical to circuit_80 on these labels, so it must agree exactly
    assert v["readout_sensitivity"]["circuit_70"]["conditions"]["main"]["delta"] == pytest.approx(
        v["conditions"]["main"]["delta"])


def test_gamma3_variant_exposes_an_effect_carried_only_by_mbon09(tmp_path):
    """If the whole learning effect sits in MBON09, the primary readout says DEMONSTRATED
    and the preregistered gamma3 variant must not."""
    sim = FakeSim()
    only09 = [i for i, l in enumerate(LABELS) if l == "MBON09"]
    mask = np.zeros(len(LABELS), dtype=bool)
    mask[only09] = True
    sim._W0[:, ~mask] = 0.0
    sim._W = sim._W0.copy()
    v = sequential(tmp_path, sim=sim)
    assert v["verdict"] == fl.DEMONSTRATED
    g3 = v["readout_sensitivity"]["circuit_80_no_gamma3"]
    assert g3["verdict"] == fl.NOT_DEMONSTRATED
    assert g3["conditions"]["main"]["delta"] == pytest.approx(0.0, abs=1e-9)
    text = "\n".join(R.report_lines(fl.results_dir_for(tmp_path, fl.ExperimentConfig())))
    assert "does not survive removing MBON09/MBON08" in text
    assert "must be reported as depending on the readout" in text


# ---- launcher: resources and concurrency ------------------------------------------ #
def test_meminfo_is_read_in_gb(tmp_path):
    p = tmp_path / "meminfo"
    p.write_text("MemTotal:       32768000 kB\nMemFree:  100 kB\nMemAvailable:   31457280 kB\n")
    m = L._meminfo(str(p))
    assert m["MemTotal"] == pytest.approx(32768000 / 1024 / 1024)
    assert m["MemAvailable"] == pytest.approx(30.0)


@pytest.mark.parametrize("total,avail,cores,expect", [
    (32, 31.0, 8, 5),     # CCX33-like: floor((31 - 3.2) / 5)
    (64, 62.5, 16, 11),   # CCX43-like: floor((62.5 - 6.4) / 5)
    (64, 62.5, 4, 4),     # capped by cores
    (8, 4.0, 8, 0),       # this Mac: not even one process fits safely
])
def test_concurrency_is_ram_bound_with_headroom(total, avail, cores, expect):
    assert L.plan_slots(L.Resources(total, avail, cores, "t")) == expect


def test_max_procs_only_lowers_concurrency():
    r = L.Resources(64, 62.5, 16, "t")
    assert L.plan_slots(r, max_procs=3) == 3
    assert L.plan_slots(r, max_procs=50) == 11


def test_makespan_estimate_is_bounded_by_the_training_chain():
    jobs = fl.plan_jobs(fl.ExperimentConfig())
    assert L.estimate_makespan(jobs, 1, 1.0) == 260  # one process: everything in sequence
    assert L.estimate_makespan(jobs, 5, 1.0) == 52
    assert L.estimate_makespan(jobs, 11, 1.0) == 46
    assert L.estimate_makespan(jobs, 100, 1.0) == 42  # critical path: 40 training + 2
    done = [j.id for j in jobs if j.kind != "posttest"]
    assert L.estimate_makespan(jobs, 25, 1.0, done=done) == 2  # only post-tests left


def test_launcher_dry_run_prints_plan_and_estimate(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(L, "detect_resources", lambda: L.Resources(32, 31.0, 8, "test"))
    assert L.main(["--dry-run", "--results-base", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "-> 5 processes" in out and "8.7 h" in out and "0.4 h" in out
    assert not any(tmp_path.iterdir())  # dry run writes nothing
    monkeypatch.setattr(L, "detect_resources", lambda: L.Resources(8, 4.0, 8, "test"))
    assert L.main(["--dry-run", "--results-base", str(tmp_path)]) == 2


# ---- launcher: real subprocesses with a fake-simulator worker ---------------------- #
WORKER = """
import sys
sys.path.insert(0, {tests!r})
from pathlib import Path
from flyshi_research.learning import first_learning as fl
from test_first_learning import FakeSim
job, base, fail = sys.argv[1], sys.argv[2], sys.argv[3]
if job == fail:
    raise SystemExit(3)
fl.Experiment(FakeSim(), fl.ExperimentConfig(), Path(base), log=lambda s: None).run_job(job)
"""


def launcher(tmp_path, base, fail="none", slots=4):
    worker = tmp_path / "worker.py"
    worker.write_text(WORKER.format(tests=str(TESTS)))
    logs = []
    la = L.Launcher(fl.ExperimentConfig(), base, slots, stagger_s=0.0, poll_s=0.02,
                    argv_for=lambda j: [sys.executable, str(worker), j.id, str(base), fail],
                    mem_reader=lambda: None, log=logs.append)
    return la, logs


def test_launcher_runs_all_jobs_in_parallel_and_matches_the_sequential_run(tmp_path):
    cfg = fl.ExperimentConfig()
    sequential(tmp_path / "seq", cfg)
    la, logs = launcher(tmp_path, tmp_path / "par")
    res = la.run()
    assert res["failed"] == [] and len(res["done"]) == 35
    assert res["verdict"]["verdict"] == fl.DEMONSTRATED
    a, b = (all_results(fl.results_dir_for(tmp_path / x, cfg)) for x in ("seq", "par"))
    assert a == b
    assert max(int(m.split("(")[1].split("/")[0]) for m in logs if "start" in m) <= 4
    # restartable: a second launch finds nothing to do
    la2, logs2 = launcher(tmp_path, tmp_path / "par")
    assert la2.run()["verdict"]["verdict"] == fl.DEMONSTRATED
    assert not [m for m in logs2 if "start" in m]


def test_failed_job_blocks_only_its_dependents_and_a_rerun_completes(tmp_path):
    base = tmp_path / "par"
    la, logs = launcher(tmp_path, base, fail="train:main")
    res = la.run()
    assert res["failed"] == ["train:main"] and res["verdict"] is None
    assert res["blocked"] == sorted(f"posttest:main:{s}" for s in fl.ExperimentConfig().test_seeds)
    assert len(res["done"]) == 35 - 1 - 5  # everything else still ran
    la2, logs2 = launcher(tmp_path, base)
    res2 = la2.run()
    assert res2["verdict"]["verdict"] == fl.DEMONSTRATED
    assert len([m for m in logs2 if "start" in m]) == 6  # only the failed job and its dependents


def test_launcher_waits_for_ram_before_adding_a_process(tmp_path):
    """With RAM reported as too low, only one process runs at a time (never zero)."""
    worker = tmp_path / "worker.py"
    worker.write_text(WORKER.format(tests=str(TESTS)))
    logs = []
    la = L.Launcher(fl.ExperimentConfig(), tmp_path / "p", 4, gb_per_proc=5, headroom_gb=2,
                    stagger_s=0.0, poll_s=0.02, mem_reader=lambda: 6.0, log=logs.append,
                    argv_for=lambda j: [sys.executable, str(worker), j.id, str(tmp_path / "p"), "x"])
    assert la.run()["verdict"] is not None
    assert {m.split("(")[1].split("/")[0] for m in logs if "start" in m} == {"1"}


def test_one_launcher_per_results_directory(tmp_path):
    lock = tmp_path / "launcher.lock"
    L.acquire_lock(lock)
    with pytest.raises(L.LockHeld):
        L.acquire_lock(lock)
    lock.write_text("999999999")  # a launcher that no longer exists
    L.acquire_lock(lock)
    assert lock.read_text() == str(__import__("os").getpid())


# ---- runner CLI: job management never needs Brian2 --------------------------------- #
def test_list_jobs_and_finish_never_import_brian2(tmp_path):
    sequential(tmp_path)
    for flag in ("--list-jobs", "--finish"):
        code = (
            "import sys, runpy\n"
            f"sys.argv = ['x', {flag!r}, '--results-base', {str(tmp_path)!r}]\n"
            f"runpy.run_path({str(MB / 'run_first_learning_test.py')!r}, run_name='__main__')\n"
            "bad = [m for m in sys.modules if m.split('.')[0] in ('brian2', 'fast_runner', 'check_mb_response')]\n"
            "assert not bad, bad\n"
        )
        out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout
        assert ("train:main" in out and "done" in out) if flag == "--list-jobs" else "VERDICT" in out


def test_unknown_job_is_rejected_before_the_network_is_built(tmp_path):
    with pytest.raises(SystemExit, match="unknown job"):
        RUNNER.main(["--job", "train:bogus", "--results-base", str(tmp_path)])
    assert "brian2" not in sys.modules


# ---- plain-language report --------------------------------------------------------- #
def test_report_states_verdict_controls_variants_and_numbers(tmp_path):
    v = sequential(tmp_path)
    d = fl.results_dir_for(tmp_path, fl.ExperimentConfig())
    before = sorted(p.name for p in d.rglob("*"))
    text = "\n".join(R.report_lines(d))
    assert sorted(p.name for p in d.rglob("*")) == before  # the report writes nothing
    assert f"**Verdict: {fl.DEMONSTRATED}**" in text
    for needle in ("Control (a)", "Control (b)", "Control (d)", "Control (c)", "not a gate",
                   "PASS", "γ3", "STRICT", "GROUP", "70%", "90%", "summed per neuron",
                   f"σ = {v['sigma']:.2f}", f"3σ = {v['threshold']:.2f}", "represented abstractly",
                   "jobs finished: 35 of 35", "equivalence test"):
        assert needle in text, needle
    assert "NOT the pre-stated test" not in text


def test_report_flags_failures_smoke_runs_and_incomplete_results(tmp_path):
    sequential(tmp_path / "leak", sim=FakeSim(leak=0.5))
    text = "\n".join(R.report_lines(fl.results_dir_for(tmp_path / "leak", fl.ExperimentConfig())))
    assert f"**Verdict: {fl.CONFOUNDED}**" in text and "**FAIL**" in text

    smoke = fl.ExperimentConfig.smoke()
    fl.Experiment(FakeSim(), smoke, tmp_path / "smoke", **QUIET).run_job("train:main")
    text = "\n".join(R.report_lines(fl.results_dir_for(tmp_path / "smoke", smoke)))
    assert "NOT the pre-stated test" in text and fl.INCONCLUSIVE in text
    assert "verdict.json not written yet" in text

    assert R.main(["--results-dir", str(tmp_path / "nothing")]) == 2


def test_report_cli_writes_the_same_text_to_a_file(tmp_path, capsys):
    sequential(tmp_path)
    out = tmp_path / "report.md"
    assert R.main(["--results-base", str(tmp_path), "--out", str(out)]) == 0
    assert capsys.readouterr().out == out.read_text()
