"""The server autopilot, on FAKES only: fake job folders, a fake clock, fake verdicts
and a local bare repository standing in for GitHub. No ssh, no network, no ntfy, no
Hetzner, no real result file and no project script is involved."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "cloud" / "autopilot" / "autopilot.py"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _load():
    spec = importlib.util.spec_from_file_location("autopilot_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


AP = _load()


def quiet(_message):
    pass


def git(world: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(world / "github.git"), *args], capture_output=True, text=True,
                          check=True).stdout


def notes(world: Path) -> str:
    path = world / "notifications.txt"
    return path.read_text() if path.exists() else ""


# ---- whole runs ---------------------------------------------------------------- #
def test_simulation_waits_for_the_rule_then_runs_phase_2_and_ends_safe(tmp_path):
    world = tmp_path / "w"
    state = AP.simulate(world, "later", echo=quiet)
    assert state["state"] == "DONE" and not state["halt"]
    text = notes(world)
    order = ["Phase 1 done", "Phase 1 pushed", "Phase 1 verdict", "Waiting (PHASE2_DECISION)", "Phase 2 will run",
             "Phase 2 started", "Phase 2 done", "Phase 2 verdict", "SAFE TO DELETE THE SERVER"]
    positions = [text.index(t) for t in order]
    assert positions == sorted(positions)
    assert text.count("SAFE TO DELETE THE SERVER") == 1
    last = text.strip().splitlines()[-1]
    assert "SAFE TO DELETE THE SERVER" in last
    assert f"scp -r flyshi:" in last and f"phase2_{state_market(world)[:12]}" in last  # the copy reminder
    assert "committed AFTER the Phase 1 verdict" in text  # the rule was added after the notification
    # the phase 1 launcher died once: crash noticed, launcher restarted, no job lost
    assert "Job crashed" in text and "exited -9" in text and "Phase 1 launcher restarted" in text

    files = git(world, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert not [f for f in files if f.startswith("data/")]
    assert {f"{AP.SWEEP_REL}/parts/{n}" for n in AP.SIM_P1} <= set(files)
    assert f"{AP.SWEEP_REL}/verdict_phase1.json" in files
    out = f"{AP.PHASE2_PUBLIC_REL}/phase2_{state_market(world)[:12]}"
    assert {f for f in files if f.startswith(AP.PHASE2_PUBLIC_REL)} == {f"{out}/verdict.json", f"{out}/hashes.json"}
    # every tick was a restart, yet each step committed exactly once
    subjects = git(world, "log", "--format=%s", "main").splitlines()
    for start in ("Synthetic sweep phase 1 results", "Synthetic sweep phase 1 verdict", "Phase 2 verdict and hashes"):
        assert sum(s.startswith(start) for s in subjects) == 1
    hashes = json.loads(git(world, "show", f"main:{out}/hashes.json"))
    assert set(hashes["job_files_sha256"]) == set(AP.SIM_P2) and hashes["market_file_sha256"] == state_market(world)


def state_market(world: Path) -> str:
    return AP.world_config(world)["market_sha256"]


def test_without_a_rule_it_waits_and_never_starts_phase_2(tmp_path):
    world = tmp_path / "w"
    state = AP.simulate(world, "none", echo=quiet)
    assert state["state"] == "PHASE2_DECISION" and "states no rule" in state["wait"]
    assert not state["phase2"].get("started_at")
    assert not json.loads((world / "sim.json").read_text())["phase2"]["running"]
    assert "SAFE TO DELETE" not in notes(world)


def test_do_not_run_rule_skips_phase_2_and_still_verifies_the_push(tmp_path):
    world = tmp_path / "w"
    state = AP.simulate(world, "do-not-run", echo=quiet)
    assert state["state"] == "DONE"
    text = notes(world)
    assert "Phase 2 not run" in text and "committed before the Phase 1 verdict" in text
    assert "Phase 2 started" not in text and "SAFE TO DELETE THE SERVER" in text
    assert "scp" not in text  # nothing private to copy when Phase 2 never ran


def test_budget_stop_starts_no_new_job_and_never_says_safe(tmp_path):
    world = tmp_path / "w"
    state = AP.simulate(world, "run-regardless", echo=quiet, overrides={"price_per_hour": 50.0})
    assert state["halt"] and "budget stop" in state["halt"]["reason"]
    assert state["state"] == "PHASE2_RUNNING"
    text = notes(world)
    assert "Phase 2 spend" in text and "Phase 2 budget stop" in text and "SAFE TO DELETE" not in text
    run_dir = world / "main/data/polymarket" / f"phase2_{state_market(world)[:12]}"
    assert (run_dir / "STOP_LAUNCHING").exists()
    assert len(list((run_dir / "parts").glob("*.json"))) < len(AP.SIM_P2)  # no job started after the stop


def test_wrong_market_file_or_missing_sign_off_waits_before_phase_2(tmp_path):
    state = AP.simulate(tmp_path / "a", "run-regardless", echo=quiet, max_ticks=30,
                        overrides={"market_sha256": "0" * 64, "drive_signoff_sha256": "0" * 64})
    assert state["state"] == "PHASE2_INPUTS" and "expected SHA-256" in state["wait"]
    state = AP.simulate(tmp_path / "b", "run-regardless", echo=quiet, max_ticks=30,
                        overrides={"drive_signoff_sha256": ""})
    assert state["state"] == "PHASE2_INPUTS" and "not signed off" in state["wait"]
    for w in ("a", "b"):
        assert "Phase 2 started" not in notes(tmp_path / w)


def test_the_committed_sign_off_record_counts_as_the_drive_sign_off(tmp_path):
    world = tmp_path / "w"
    world.mkdir()
    AP.make_world(world, "run-regardless")
    cfg = AP.world_config(world, {"drive_signoff_sha256": ""})
    ap = AP.Autopilot(cfg, AP.SimEnv(cfg, world))
    digest = cfg["market_sha256"]
    record = cfg["main_tree"] / AP.SIGNOFF_REL
    record.parent.mkdir(parents=True)
    record.write_text(f"# sign-off\n- sha256: {digest}\n- Signed off by the owner\n")
    assert ap.drive_signed_off(digest)
    record.write_text(f"# sign-off\n- sha256: {'1' * 64}\n- Signed off by the owner\n")
    assert not ap.drive_signed_off(digest)
    record.write_text(f"# draft\n- sha256: {digest}\n")
    assert not ap.drive_signed_off(digest)


def test_without_the_frozen_tag_nothing_after_the_phase_1_push_runs(tmp_path):
    world = tmp_path / "w"
    state = AP.simulate(world, "run-regardless", echo=quiet, max_ticks=30, overrides={"frozen_tag": "no-such-tag"})
    assert state["state"] == "PHASE1_VERDICT" and "is not on GitHub" in state["wait"]
    assert "Phase 1 pushed" in notes(world) and "Phase 2 started" not in notes(world)


def _tick_until_halt(cfg, world, ticks=10):
    for _ in range(ticks):
        ap = AP.Autopilot(cfg, AP.SimEnv(cfg, world))
        ap.tick()
        if ap.s["halt"] or ap.s["state"] == "DONE":
            return ap.s
        AP.SimEnv(cfg, world).advance(1.0)
    return ap.s


@pytest.mark.parametrize("change", ["moved", "deleted"])
def test_phase_2_refuses_to_start_if_the_tag_moved_or_vanished_on_github(tmp_path, change):
    world = tmp_path / "w"
    state = AP.simulate(world, "run-regardless", echo=quiet, stop_at="PHASE2_INPUTS")
    assert state["state"] == "PHASE2_INPUTS" and state["phase2"]["code_sha"]
    bare, seed = world / "github.git", world / "seed"
    if change == "moved":
        AP._sim_git("pull", "-q", str(bare), "main", cwd=seed)
        (seed / "later.txt").write_text("a later change\n")
        AP._sim_git("add", "later.txt", cwd=seed)
        AP._sim_git("commit", "-q", "-m", "later", cwd=seed)
        AP._sim_git("tag", "-f", "-a", "phase2-frozen", "-m", "moved", cwd=seed)
        AP._sim_git("push", "-q", "--force", str(bare), "refs/tags/phase2-frozen", cwd=seed)
    else:
        AP._sim_git("tag", "-d", "phase2-frozen", cwd=bare)
    cfg = AP.world_config(world)
    s = _tick_until_halt(cfg, world)
    assert s["halt"] and ("differs from the pinned commit" if change == "moved" else "missing") in s["halt"]["reason"]
    assert not s["phase2"].get("launches") and "Phase 2 started" not in notes(world)


def test_final_check_catches_a_file_changed_on_github(tmp_path):
    world = tmp_path / "w"
    assert AP.simulate(world, "do-not-run", echo=quiet)["state"] == "DONE"
    seed = world / "seed"
    AP._sim_git("pull", "-q", str(world / "github.git"), "main", cwd=seed)
    victim = seed / AP.SWEEP_REL / "parts" / AP.SIM_P1[0]
    victim.write_text('{"tampered": true}\n')
    AP._sim_git("commit", "-q", "-am", "tamper", cwd=seed)
    AP._sim_git("push", "-q", str(world / "github.git"), "main", cwd=seed)
    cfg = AP.world_config(world)
    state_path = cfg["state_dir"] / "state.json"
    s = json.loads(state_path.read_text())
    s["state"], s["notified"] = "FINAL_VERIFY", {}
    state_path.write_text(json.dumps(s))
    ap = AP.Autopilot(cfg, AP.SimEnv(cfg, world))
    ap.tick()
    assert ap.s["halt"] and "changed on GitHub" in ap.s["halt"]["reason"] and ap.s["state"] == "FINAL_VERIFY"


# ---- the commit guard ------------------------------------------------------------ #
def test_data_guard_rejects_data_private_names_per_market_records_and_stray_paths(tmp_path):
    files = {
        "a/ok.json": {"gate": {"lower": 0.1}, "limitations": ["x"] * 4, "readings": {"overall": "y"}},
        "a/ids.json": {"summary": {"market_id": "123"}},
        "a/long.json": {"values": list(range(500))},
        "a/wide.json": {str(i): 1 for i in range(1000)},
        "a/rows.json": {"test": [{}]},
        "a/notes.txt": "text",
        "b/ok.json": {},
    }
    for rel, value in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(value if isinstance(value, str) else json.dumps(value))
    staged = [*files, "data/polymarket/x.json", "a/markets_f3d41123e20e_cutoff_2026-03-01.json",
              "a/fill_plan_f3d41123e20e.json", "a/manifest.json"]
    problems = AP.staged_problems(tmp_path, staged, ["a"], per_market=True)
    flagged = {p.split(":")[0] for p in problems}
    assert "a/ok.json" not in flagged
    assert flagged == set(staged) - {"a/ok.json"}
    # phase 1 commits: synthetic job files with rows are allowed, data/ never
    assert AP.staged_problems(tmp_path, ["a/rows.json"], ["a"], per_market=False) == []
    assert AP.staged_problems(tmp_path, ["data/x.json"], ["data"], per_market=False)


def test_a_guarded_commit_is_aborted_unstaged_and_never_pushed(tmp_path):
    world = tmp_path / "w"
    world.mkdir()
    AP.make_world(world, "run-regardless")
    cfg = AP.world_config(world)
    ap = AP.Autopilot(cfg, AP.SimEnv(cfg, world))
    ap.step_setup()
    rel = f"{AP.PHASE2_PUBLIC_REL}/phase2_x"
    (cfg["publish_clone"] / rel).mkdir(parents=True)
    (cfg["publish_clone"] / rel / "verdict.json").write_text(json.dumps({"outcomes": [0, 1]}))
    with pytest.raises(AP.StepHalt, match="data guard"):
        ap.commit_and_push([rel], "should never land", per_market=True)
    staged = subprocess.run(["git", "-C", str(cfg["publish_clone"]), "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, check=True).stdout
    assert staged == ""
    assert "should never land" not in git(world, "log", "--format=%s", "main")


# ---- small pieces ------------------------------------------------------------------ #
def test_rule_marker_must_be_its_own_line():
    assert AP.RULE_RE.findall("x\n<!-- autopilot-phase2-rule: run-regardless -->\ny") == ["run-regardless"]
    assert AP.RULE_RE.findall("prose about autopilot-phase2-rule: run-regardless") == []
    both = "<!-- autopilot-phase2-rule: run-regardless -->\n<!-- autopilot-phase2-rule: do-not-run -->\n"
    assert len(set(AP.RULE_RE.findall(both))) == 2  # ambiguous: the step waits


def test_config_needs_a_long_topic_and_this_repository(tmp_path):
    path = tmp_path / "config.json"
    base = {"git_user_name": "a", "git_user_email": "a@example.invalid"}
    for bad in ({**base, "ntfy_topic": "short"},
                {**base, "ntfy_topic": "x" * 40, "push_url": "git@github.com:someone/else.git"},
                {"ntfy_topic": "x" * 40}):
        path.write_text(json.dumps(bad))
        with pytest.raises(SystemExit):
            AP.load_config(path)
    path.write_text(json.dumps({**base, "ntfy_topic": "x" * 40}))
    cfg = AP.load_config(path)
    assert cfg["max_procs"] == 4 and cfg["gb_per_proc"] == 3.6
    assert (cfg["stall_hours"], cfg["spend_warn_usd"], cfg["spend_stop_usd"]) == (12.0, 85.0, 95.0)
    assert cfg["frozen_tag"] == "phase2-frozen"


def test_simulation_refuses_a_folder_that_is_not_empty(tmp_path):
    (tmp_path / "x").write_text("keep")
    with pytest.raises(SystemExit):
        AP.simulate(tmp_path, echo=quiet)
    assert (tmp_path / "x").read_text() == "keep"
