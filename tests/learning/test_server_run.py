"""CCX33 run preparation (2026-10-11): two-phase run order, arm-subset identity,
calibration, ETA, cross-platform check, monitor, backups and recovery.

No Brian2: workers are subprocesses running the fake market simulator, or trivial
scripts that print progress lines."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from flyshi_research.learning.params import PlasticityParams  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MB = REPO / "repro" / "mushroom_body"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(MB))


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


LAUNCHER = load(MB / "launch_synthetic_market_parallel.py", "server_run_launcher")
import run_synthetic_market_experiment as RUNNER  # noqa: E402
CAL = load(MB / "calibrate_server.py", "server_run_calibrate")
ETA = load(MB / "server_eta.py", "server_run_eta")
XP = load(MB / "cross_platform_check.py", "server_run_cross_platform")
MON = load(MB / "monitor_sweep.py", "server_run_monitor")
BACKUP = load(REPO / "scripts" / "cloud" / "backup_results.py", "server_run_backup")


# ---- 1. two-phase run order ------------------------------------------------------ #
def test_phases_split_the_arms_and_change_no_configuration():
    cfg = sm.SyntheticConfig()
    assert cfg.config_hash() == "a325e6b206"  # the order is not part of the config
    assert sm.RUN_PHASES[1] == sm.GATE_ARMS == (sm.PROFIT, sm.LEARNING_OFF) == sm.SENSITIVITY_ARMS
    assert sm.RUN_PHASES[2] == (sm.ACCURACY, sm.PROFIT_DRIFT_OFF)
    one, two = (sm.plan_jobs(cfg, sm.RUN_PHASES[p]) for p in (1, 2))
    assert len(one) == len(two) == 160
    assert sum(j.n_runs for j in one) == sum(j.n_runs for j in two) == 80_000
    assert sorted(j.id for j in one + two) == sorted(j.id for j in sm.plan_jobs(cfg))
    assert {j for j in sm.plan_jobs(cfg) if j.condition in sm.GATE_ARMS} == set(one)
    with pytest.raises(ValueError, match="unknown arm"):
        sm.plan_jobs(cfg, ("profit", "nonsense"))


def test_run_order_starts_every_phase_1_job_before_any_phase_2_job():
    order = sm.run_order(sm.plan_jobs(sm.SyntheticConfig()))
    phases = [sm.phase_of(j.condition) for j in order]
    assert phases == sorted(phases) and phases.count(1) == 160
    # within a phase the plan order is kept (strength-major: the null control first)
    assert [j.strength for j in order[:40]] == [0.0] * 40


def test_innate_dependencies_follow_a_selected_arm():
    from flyshi_research.learning.bias_mitigation import INNATE_SCORE_SUBTRACTION
    cfg = sm.SyntheticConfig(mitigation=INNATE_SCORE_SUBTRACTION)
    jobs = sm.plan_jobs(cfg, (sm.PROFIT,))
    assert len([j for j in jobs if j.kind == "innate"]) == 80
    assert sm.run_order(jobs)[0].kind == "innate"


def tiny_config():
    return replace(sm.SyntheticConfig(), signal_strengths=(0.0, 0.8), market_seeds=sm.MARKET_SEEDS[:2],
                   markets_per_seed=20, trials=1, score_scale=2.0, bootstrap_resamples=50,
                   plasticity=PlasticityParams(learning_rate=0.3, drift_rate=0.0), prestated=False)


WORKER = """
import sys
sys.path.insert(0, {tests!r}); sys.path.insert(0, {mb!r})
from pathlib import Path
from dataclasses import replace
from flyshi_research.learning import synthetic_market as sm
from flyshi_research.learning.params import PlasticityParams
import run_synthetic_market_experiment as runner
from test_synthetic_market import FakeMarketSimulator
cfg = replace(sm.SyntheticConfig(), signal_strengths=(0.0, 0.8), market_seeds=sm.MARKET_SEEDS[:2],
              markets_per_seed=20, trials=1, score_scale=2.0, bootstrap_resamples=50,
              plasticity=PlasticityParams(learning_rate=0.3, drift_rate=0.0), prestated=False)
job = next(j for j in sm.plan_jobs(cfg) if j.id == sys.argv[1])
fake = FakeMarketSimulator(True)
out = sm.run_dataset(fake, cfg, job.strength, job.market_seed, job.condition, kc_sides=fake.kc_sides)
runner._write_json(runner.Paths(sm.results_dir_for(Path(sys.argv[2]), cfg)).output(job), out)
"""


def launcher_for(tmp_path, base, arms=None, finished=None):
    worker = tmp_path / "worker.py"
    worker.write_text(WORKER.format(tests=str(TESTS), mb=str(MB)))
    finished = finished if finished is not None else []
    return LAUNCHER.Launcher(tiny_config(), base, slots=4, stagger_s=0.0, poll_s=0.02,
                             argv_for=lambda j: [sys.executable, str(worker), j.id, str(base)],
                             mem_reader=lambda: None, log=lambda m: None,
                             finish=lambda: finished.append(1) or {"signal_requirement": None},
                             arms=arms)


def parts(base):
    d = sm.results_dir_for(base, tiny_config()) / "parts"
    return {p.name: p.read_bytes() for p in sorted(d.glob("*.json"))}


def test_job_outputs_are_identical_whether_arms_run_together_or_apart(tmp_path):
    finished_apart, finished_together = [], []
    first = launcher_for(tmp_path, tmp_path / "apart", sm.RUN_PHASES[1], finished_apart).run()
    # phase 1 alone: every selected job done, but no verdict (the sweep is incomplete)
    assert first["failed"] == [] and len(first["done"]) == 8
    assert first["verdict"] is None and first["sweep_complete"] is False and not finished_apart
    second = launcher_for(tmp_path, tmp_path / "apart", sm.RUN_PHASES[2], finished_apart).run()
    assert second["sweep_complete"] and finished_apart == [1]
    together = launcher_for(tmp_path, tmp_path / "together", None, finished_together).run()
    assert together["sweep_complete"] and finished_together == [1]
    apart, joint = parts(tmp_path / "apart"), parts(tmp_path / "together")
    assert len(apart) == 16 and apart == joint  # byte for byte
    # and equal to running each chain directly, in this process
    from test_synthetic_market import FakeMarketSimulator
    cfg = tiny_config()
    for job in sm.plan_jobs(cfg):
        fake = FakeMarketSimulator(True)
        direct = sm.run_dataset(fake, cfg, job.strength, job.market_seed, job.condition,
                                kc_sides=fake.kc_sides)
        assert json.loads(apart[job.id.replace(":", "_") + ".json"]) == json.loads(
            json.dumps(direct, separators=(",", ":")))


def test_launcher_cli_phase_and_arms(tmp_path, capsys):
    common = ["--dry-run", "--results-base", str(tmp_path), "--gb-per-proc", "0.001",
              "--headroom-gb", "0", "--max-procs", "5"]
    assert LAUNCHER.main(common + ["--phase", "1"]) == 0
    out = capsys.readouterr().out
    assert "arms: profit, learning_off" in out and "jobs: 160" in out and "80000 runs" in out
    assert LAUNCHER.main(common) == 0
    out = capsys.readouterr().out
    assert "all, phase 1 first" in out and "jobs: 320" in out and "phase 1 done after 244.4 h" in out
    assert LAUNCHER.main(common + ["--arms", "accuracy,profit_drift_off"]) == 0
    with pytest.raises(SystemExit):
        LAUNCHER.main(common + ["--phase", "1", "--arms", "profit"])
    with pytest.raises(SystemExit, match="unknown arm"):
        LAUNCHER.main(common + ["--arms", "profit,bogus"])
    assert not any(tmp_path.iterdir())


def test_runner_lists_one_phase(tmp_path, capsys):
    assert RUNNER.main(["--list-jobs", "--phase", "2", "--results-base", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 160 and all(":accuracy:" in l or ":profit_drift_off:" in l for l in lines)


def test_finish_refuses_while_any_job_is_missing(tmp_path):
    with pytest.raises(RuntimeError, match="missing job output"):
        RUNNER.finish(sm.SyntheticConfig(), tmp_path)


# ---- 6. recovery ----------------------------------------------------------------- #
def test_job_file_is_written_whole_and_damaged_files_do_not_count_as_done(tmp_path):
    cfg = sm.SyntheticConfig()
    job = sm.plan_jobs(cfg)[0]
    paths = RUNNER.Paths(tmp_path)
    RUNNER._write_json(paths.output(job), {"condition": "profit", "train": [], "test": []})
    assert paths.done(job) and not list(paths.parts.glob("*.partial"))
    for damaged in ("", '{"condition": "profit", "tra', "[1, 2]"):
        paths.output(job).write_text(damaged)
        assert not paths.done(job), damaged
    paths.output(job).unlink()
    assert not paths.done(job)


def test_a_damaged_job_file_is_rerun_and_replaced(tmp_path):
    base = tmp_path / "base"
    launcher_for(tmp_path, base).run()
    victim = sm.results_dir_for(base, tiny_config()) / "parts" / "condition_profit_0_20261001.json"
    good = victim.read_bytes()
    victim.write_bytes(good[: len(good) // 2])  # as if a crash had truncated it
    result = launcher_for(tmp_path, base).run()
    assert victim.read_bytes() == good and result["sweep_complete"]


def test_a_lock_from_before_the_last_boot_is_discarded(tmp_path):
    lock = tmp_path / "launcher.lock"
    lock.write_text("1")  # pid 1 always exists: acquire_lock alone would refuse
    with pytest.raises(LAUNCHER.LockHeld if hasattr(LAUNCHER, "LockHeld") else Exception):
        sys.modules["launch_first_learning_parallel"].acquire_lock(lock)
    assert not LAUNCHER.discard_lock_from_before_boot(lock, booted=lock.stat().st_mtime - 10)
    assert lock.exists()
    assert LAUNCHER.discard_lock_from_before_boot(lock, booted=time.time() + 10)
    assert not lock.exists()
    assert not LAUNCHER.discard_lock_from_before_boot(lock, booted=time.time())  # absent


def test_runner_writes_start_and_progress_lines_the_tools_can_parse(capsys):
    report = RUNNER.progress_printer("condition:profit:0:20261001", 500)
    report(1)
    report(2)
    out = capsys.readouterr().out
    times, rss = CAL.parse_progress(out)
    assert len(times) == 2 and rss > 0
    assert all(MON.PROGRESS_RE.match(line) for line in out.splitlines())
    source = (MB / "run_synthetic_market_experiment.py").read_text()
    assert "build_sweep_simulator(progress_printer(selected.id, selected.n_runs))" in source
    assert 'print(f"{START_TAG} {selected.id}' in source


# ---- 2. calibration and ETA ------------------------------------------------------ #
def test_seconds_per_run_uses_only_runs_inside_the_window():
    times = [100.0, 150.0, 200.0, 260.0, 300.0]
    assert CAL.seconds_per_run(times, 140, 310)["mean_s"] == pytest.approx(50.0)
    assert CAL.seconds_per_run(times, 140, 160) is None


FAKE_WORKER = """
import sys, time
job, n = sys.argv[1], 0
time.sleep(0.2)  # "network build"
while True:
    n += 1
    time.sleep({period})
    print(f"[progress] {{job}} run {{n}}/500 t={{time.time():.2f}} maxrss_gb=1.250", flush=True)
"""


def test_calibration_level_measures_rate_memory_and_throughput(tmp_path):
    worker = tmp_path / "w.py"
    worker.write_text(FAKE_WORKER.format(period=0.1))
    jobs = sm.run_order(sm.plan_jobs(sm.SyntheticConfig()))
    level = CAL.run_level(3, jobs, tmp_path, minutes=0.03, stagger_s=0.0, gb_per_proc=1.0,
                          headroom_gb=0.0, argv_for=lambda j, b: [sys.executable, str(worker), j.id],
                          mem_reader=lambda: 100.0, log=lambda m: None, poll_s=0.05)
    assert level["procs_run"] == 3 and level["complete"]
    assert 0.08 < level["seconds_per_run_mean"] < 0.3
    assert level["runs_per_hour"] == pytest.approx(
        sum(3600 / p["seconds_per_run"]["mean_s"] for p in level["per_process"]))
    assert level["peak_rss_gb_max"] >= 1.25
    assert [p["job"] for p in level["per_process"]] == [j.id for j in jobs[:3]]  # distinct jobs
    assert "|" in CAL.format_table([level])


def test_calibration_starts_fewer_processes_when_memory_runs_short(tmp_path):
    worker = tmp_path / "w.py"
    worker.write_text(FAKE_WORKER.format(period=0.05))
    readings = iter([30.0, 30.0, 30.0] + [3.0] * 10_000)  # room for two, then not
    level = CAL.run_level(4, sm.plan_jobs(sm.SyntheticConfig()), tmp_path, minutes=0.01,
                          stagger_s=0.0, gb_per_proc=5.0, headroom_gb=2.0,
                          argv_for=lambda j, b: [sys.executable, str(worker), j.id],
                          mem_reader=lambda: next(readings), log=lambda m: None, poll_s=0.02)
    assert level["procs_run"] == 2 and "memory-limited: started 2 of 4" in level["note"]


def calibration(levels):
    return {"config_hash": "a325e6b206", "environment": {"hostname": "ccx33"},
            "machine": {"total_gb": 32.0, "available_gb_at_start": 31.0, "logical_cpus": 8,
                        "headroom_gb": 3.2},
            "levels": [{"procs_asked": n, "procs_run": n, "complete": True,
                        "seconds_per_run_mean": s, "runs_per_hour": n * 3600 / s,
                        "peak_rss_gb_max": m, "first_run_done_after_s_max": s + 6.0, "note": None}
                       for n, s, m in levels]}


def test_eta_picks_the_fastest_count_that_fits_in_memory():
    start = ETA.dt.datetime(2026, 10, 12, 9, 0)
    # 8 processes would be fastest but need 8 x 4.6 GB > 27.8 GB
    lines = ETA.report(calibration([(1, 50.0, 4.0), (4, 60.0, 4.0), (8, 90.0, 4.0)]),
                       [], 0.266, start, budget=170)
    text = "\n".join(lines)
    assert "BEST: N = 4 processes, 240 runs/h" in text
    assert "| 8 | 90.0 | 320 | 4.00 | NO |" in text
    assert "--max-procs 4 --gb-per-proc 4.6" in text
    # phase 1: 160 jobs on 4 slots = 40 waves x 500 runs x 60 s, + 0.1 min build per wave
    assert "+333 h" in text and "+667 h" in text and "budget $170: EXCEEDED" in text
    assert ETA.fits(6, 4.0, 31.0, 3.2) and not ETA.fits(7, 4.0, 31.0, 3.2)


def test_eta_prefers_fewer_processes_within_two_percent_and_subtracts_done_jobs():
    cal = calibration([(4, 60.0, 3.0), (8, 118.0, 3.0)])  # 240 vs 244 runs/h
    best = ETA.choose([ETA.plan(lv, sm.run_order(sm.plan_jobs(sm.SyntheticConfig())), [], 0.266)
                       for lv in cal["levels"]])
    assert best["procs"] == 4
    jobs = sm.run_order(sm.plan_jobs(sm.SyntheticConfig()))
    full = ETA.plan(cal["levels"][0], jobs, [], 0.266)
    later = ETA.plan(cal["levels"][0], jobs, [j.id for j in jobs[:80]], 0.266)
    assert later["phase1_hours"] == pytest.approx(full["phase1_hours"] / 2, rel=0.01)
    assert full["phase1_hours"] < full["total_hours"]
    assert full["total_cost"] == pytest.approx(full["phase1_cost"] + full["phase2_cost"])


def test_eta_rejects_a_calibration_for_another_configuration():
    cal = calibration([(4, 60.0, 3.0)])
    cal["config_hash"] = "0000000000"
    with pytest.raises(SystemExit):
        ETA.report(cal, [], 0.266, ETA.dt.datetime(2026, 10, 12))


# ---- 3. cross-platform check ----------------------------------------------------- #
def test_noise_floors_are_the_pre_stated_values():
    _, seeds = XP.load_mac()
    floors = XP.noise_floors(seeds)
    assert round(floors[XP.SCORE], 2) == 3.22
    assert {p: round(floors[p], 2) for p in ("mbons", "kenyon_cells", "apl_neurons")} == {
        "mbons": 11.94, "kenyon_cells": 143.70, "apl_neurons": 5.02}
    plan = " ".join((REPO / "docs" / "cloud" / "ccx33-run-plan.md").read_text().split())
    for value in ("3.22 Hz", "11.94 Hz", "143.70 Hz", "5.02 Hz"):
        assert value in plan


def test_cross_platform_readings():
    mac, seeds = XP.load_mac()
    repro = json.loads((MB / "results" / "pool_identity_repro_check.json").read_text())
    assert XP.classify(repro, repro, mac, seeds)["reading"] == XP.IDENTICAL

    def shifted(payload, population, hz):
        out = json.loads(json.dumps(payload))
        out["rates_hz"][population][0] += hz
        return out

    small = shifted(mac, "kenyon_cells", 1.0)
    result = XP.classify(small, small, mac, seeds)
    assert result["reading"] == XP.WITHIN and result["beyond_floor"] == []
    big = shifted(mac, "apl_neurons", 50.0)
    result = XP.classify(big, big, mac, seeds)
    assert result["reading"] == XP.INCONSISTENT and result["beyond_floor"] == ["apl_neurons"]
    assert XP.classify(mac, small, mac, seeds)["reading"] == XP.NONDETERMINISTIC
    for reading in (XP.INCONSISTENT, XP.NONDETERMINISTIC):
        assert "do NOT start the sweep" in XP.ACTIONS[reading]


def test_cross_platform_dry_run_simulates_and_writes_nothing(tmp_path, capsys):
    before = sorted((MB / "results").iterdir())
    assert XP.main(["--dry-run"]) == 0
    assert "3.22 Hz" in capsys.readouterr().out
    assert sorted((MB / "results").iterdir()) == before
    assert "brian2" not in sys.modules


# ---- 5. monitor ------------------------------------------------------------------ #
def test_monitor_counts_jobs_failures_damage_rate_and_ignition_without_outcomes(tmp_path):
    cfg = sm.SyntheticConfig()
    jobs = sm.run_order(sm.plan_jobs(cfg))
    paths = RUNNER.Paths(sm.results_dir_for(tmp_path, cfg))
    now = 1_800_000_000.0
    ignited = {"ignited_any_trial": True}
    quiet = {"ignited_any_trial": False}
    row = {"ignition_yes": quiet, "ignition_no": quiet, "score_difference": 123.0}
    for j in jobs[:3]:  # finished, one with two ignited decisions
        rows = [dict(row, ignition_yes=ignited)] * 2 if j is jobs[0] else [row]
        RUNNER._write_json(paths.output(j), {"condition": j.condition, "train": rows, "test": [row]})
    paths.logs.mkdir(parents=True)
    for j in jobs[:3]:
        paths.log(j).write_text("".join(f"[progress] {j.id} run {n}/500 t={now - 3600 + n} "
                                        "maxrss_gb=3.900\n" for n in range(1, 501)))
    running = jobs[3]
    paths.log(running).write_text(
        "[start] x\n" + "".join(f"[progress] {running.id} run {n}/500 t={now - 3600 + n * 6} "
                                "maxrss_gb=4.100\n" for n in range(1, 101))
        + "[start] x\n" + f"[progress] {running.id} run 1/500 t={now - 60} maxrss_gb=4.000\n")
    paths.log(jobs[4]).write_text("Traceback (most recent call last):\nMemoryError\n")  # failed
    paths.output(jobs[5]).write_text('{"condition": "pro')  # damaged, not running
    paths.log(jobs[5]).write_text("[start] x\n")
    lines = MON.status(tmp_path, now=now, workers={running.id: {"pid": 1, "rss_gb": 3.95}},
                       meminfo={"MemTotal": 31.3, "MemAvailable": 12.0})
    text = "\n".join(lines)
    assert "jobs: 3 done / 1 running / 316 remaining of 320" in text
    assert "phase 1 (profit, learning_off): 3/160 done, 1 running" in text
    assert "runs: 1,500 in finished jobs + 1 in running jobs" in text
    assert f"running {running.id}: run 1/500" in text and "attempt 2" in text
    assert "FAILED or interrupted" in text and "MemoryError" in text
    assert f"DAMAGED job files (exist, not whole JSON; will be re-run): {jobs[5].id}" in text
    assert "2 decisions with an ignited framing in 1 of 3 finished jobs" in text
    assert "peak memory of any job so far: 4.10 GB" in text and "12.0 GB available" in text
    assert "runs/h" in text and "ETA at this rate" in text
    # blinding: nothing about scores, forecasts, outcomes or money
    lowered = text.lower()
    for banned in ("score", "brier", "p/l", "forecast", "outcome", "123"):
        assert banned not in lowered, banned


# ---- 4. backups ------------------------------------------------------------------ #
def test_backup_config_hash_is_the_sweep_hash():
    assert BACKUP.CONFIG_HASH == sm.SyntheticConfig().config_hash()
    assert BACKUP.SWEEP_REL.endswith(sm.results_dir_for(Path("x"), sm.SyntheticConfig()).name)


def test_backup_file_check(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"condition": "profit", "train": [], "test": []}))
    assert BACKUP.check_job_file(good) is None
    cases = {"empty.json": "", "cut.json": '{"condition": "pr', "other.json": '{"a": 1}'}
    for name, text in cases.items():
        (tmp_path / name).write_text(text)
        assert BACKUP.check_job_file(tmp_path / name) is not None, name
    assert "ceiling" in BACKUP.check_job_file(good, max_bytes=5)


def fake_server(root: Path) -> Path:
    sweep = root / BACKUP.SWEEP_REL
    (sweep / "parts").mkdir(parents=True)
    (sweep / "logs").mkdir()
    (sweep / "parts" / "a.json").write_text(json.dumps({"condition": "profit", "train": [], "test": []}))
    (sweep / "parts" / "b.json.partial").write_text("half")
    (sweep / "logs" / "a.log").write_text("[progress] ...\n")
    (sweep / "logs" / "launcher.lock").write_text("123")
    cal = root / BACKUP.EXTRA_REL[0]
    cal.mkdir(parents=True)
    (cal / "calibration_x.json").write_text("{}")
    (root / BACKUP.RESULTS_REL / "cross_platform_check_x.json").write_text("{}")
    (root / BACKUP.RESULTS_REL / "unrelated.json").write_text("{}")
    return sweep


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")
def test_backup_pull_copies_finished_files_only_and_never_deletes(tmp_path):
    server, dest = tmp_path / "server", tmp_path / "mac"
    sweep = fake_server(server)
    (dest / BACKUP.SWEEP_REL / "parts").mkdir(parents=True)
    (dest / BACKUP.SWEEP_REL / "parts" / "kept.json").write_text(
        json.dumps({"condition": "x", "train": [], "test": []}))
    log = []
    assert BACKUP.pull_cycle("", str(server), dest, log.append)
    got = dest / BACKUP.SWEEP_REL
    assert (got / "parts" / "a.json").read_bytes() == (sweep / "parts" / "a.json").read_bytes()
    assert (got / "parts" / "kept.json").exists()  # nothing deleted
    assert not (got / "parts" / "b.json.partial").exists() and not (got / "logs" / "launcher.lock").exists()
    assert (got / "logs" / "a.log").exists()
    assert (dest / BACKUP.EXTRA_REL[0] / "calibration_x.json").exists()
    assert (dest / BACKUP.RESULTS_REL / "cross_platform_check_x.json").exists()
    assert not (dest / BACKUP.RESULTS_REL / "unrelated.json").exists()
    assert "2 job files checked OK" in log[-1]
    (sweep / "parts" / "c.json").write_text("")  # a damaged file on the server is reported
    assert not BACKUP.pull_cycle("", str(server), dest, log.append)
    assert "FAILED the check" in log[-1] and "c.json: empty" in log[-1]


def test_backup_push_commits_checked_files_only(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "test")
    sweep = fake_server(repo)
    (sweep / "parts" / "bad.json").write_text('{"cond')
    log = []
    assert not BACKUP.push_cycle(repo, log.append, push=False)  # bad file -> not all good
    committed = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=repo,
                               capture_output=True, text=True).stdout.split()
    assert f"{BACKUP.SWEEP_REL}/parts/a.json" in committed
    assert f"{BACKUP.SWEEP_REL}/parts/bad.json" not in committed
    assert not any(p.endswith((".partial", ".lock")) for p in committed)
    assert any("NOT committing bad.json" in m for m in log)
    assert BACKUP.BRANCH == "results-backup/a325e6b206"


def test_backup_loop_survives_a_failing_cycle():
    calls, log = [], []

    def cycle():
        calls.append(1)
        raise OSError("ssh: connect to host flyshi: Connection refused")
    assert BACKUP.loop(cycle, every_hours=0, once=True, log=log.append) == 1
    assert "Connection refused" in log[0]


# ---- docs ------------------------------------------------------------------------ #
def test_spec_pre_states_the_two_phase_order_and_blinding():
    spec = " ".join((REPO / "docs" / "design" / "synthetic-market-experiment.md").read_text().split())
    rev = spec[spec.index("REVISION 2026-10-11"):spec.index("## Results")]
    for needle in ("**Phase 2 runs regardless of phase 1 results.**",
                   "**Phase 1 results are not analysed until phase 2 is complete.**",
                   "**`a325e6b206`**", "**160 jobs, 80,000 runs**",
                   "Why not read the gate early, although its arms are independent",
                   "**before** any phase 1 result is analysed", "`monitor_sweep.py` shows only these"):
        assert needle in rev, needle
    plan = " ".join((REPO / "docs" / "cloud" / "ccx33-run-plan.md").read_text().split())
    for needle in ("`SERVER_NONDETERMINISTIC`", "`CONSISTENT_WITHIN_NOISE`", "`INCONSISTENT`",
                   "**Do not start the sweep.**", "Automatic-Reboot", "**The job restarts from market 0.**",
                   "$0.266/h", "backup_results.py pull"):
        assert needle in plan, needle
