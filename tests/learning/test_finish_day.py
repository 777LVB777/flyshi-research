"""Finish-day script for the synthetic sweep's phase 1, on FAKE servers only: a local
directory stands in for ``ssh flyshi`` (remote ''), so no ssh, no rsync to a real
host, no Hetzner and no real result file is involved."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from flyshi_research.learning import synthetic_market as sm  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "repro" / "mushroom_body" / "finish_day.py"


def _load():
    spec = importlib.util.spec_from_file_location("finish_day_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


FD = _load()
needs_rsync = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")


def _job_value(job, cfg):
    # rows are opaque placeholders: the script must never open them
    return {"condition": job.condition, "strength": job.strength, "market_seed": job.market_seed,
            "drift_rate": 0.0, "mbon_ids": [], "mbon_labels": [], "calibrator": {},
            "train": [{"x": i} for i in range(cfg.train_count)], "test": [{"x": i} for i in range(cfg.test_count)]}


def fake_server(root: Path, skip=0) -> Path:
    cfg = sm.SyntheticConfig()
    sweep = root / FD.BACKUP.SWEEP_REL
    (sweep / "parts").mkdir(parents=True)
    (sweep / "logs").mkdir()
    for job in FD.phase1_jobs(cfg)[skip:]:
        (sweep / "parts" / FD.file_name(job)).write_text(json.dumps(_job_value(job, cfg)))
        (sweep / "logs" / (job.id.replace(":", "_") + ".log")).write_text("[progress] ...\n")
    (root / FD.BACKUP.EXTRA_REL[0]).mkdir(parents=True)
    (root / FD.BACKUP.EXTRA_REL[0] / "calibration_x.json").write_text("{}")
    return sweep


def _run(tmp_path, dry_run, **kw):
    server, dest, repo = tmp_path / "server", tmp_path / "backups", tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    lines = []
    code = FD.run("", str(server), dest, repo, dry_run, log=lines.append, **kw)
    return code, "\n".join(lines), dest, repo


def test_there_are_160_phase1_jobs():
    jobs = FD.phase1_jobs()
    assert len(jobs) == 160 and {j.condition for j in jobs} == {"profit", "learning_off"}
    assert FD.file_name(jobs[0]) == jobs[0].id.replace(":", "_") + ".json"


def test_dry_run_checks_but_pulls_copies_and_clears_nothing(tmp_path):
    fake_server(tmp_path / "server")
    code, out, dest, repo = _run(tmp_path, dry_run=True)
    assert "phase 1 job files on the server: 160/160" in out
    assert "DRY RUN: would run" in out
    rsyncs = [line for line in out.splitlines() if line.strip().startswith("rsync ")]
    assert len(rsyncs) == 3 and not any("--delete" in line for line in rsyncs)
    assert "SAFE TO DELETE" not in out.replace("no SAFE line", "")
    assert not dest.exists() and list(repo.iterdir()) == []
    assert FD.finish_phase1_command() in out


@needs_rsync
def test_full_run_pulls_verifies_copies_and_says_safe_only_when_everything_passes(tmp_path):
    fake_server(tmp_path / "server")
    code, out, dest, repo = _run(tmp_path, dry_run=False)
    assert code == 0, out
    assert "all 160 verified" in out and "SAFE TO DELETE THE SERVER" in out
    parts = repo / FD.BACKUP.SWEEP_REL / "parts"
    assert len(list(parts.glob("*.json"))) == 160
    assert (repo / FD.BACKUP.EXTRA_REL[0] / "calibration_x.json").exists()
    assert "git -C" in out and " add -- " in out and "commit -m" in out
    assert out.index("SAFE TO DELETE") < out.index("--finish-phase1")  # (e) before (f)
    assert (tmp_path / "server" / FD.BACKUP.SWEEP_REL / "parts").exists()  # nothing deleted on the server


@needs_rsync
def test_a_missing_job_or_a_live_launcher_is_not_safe_and_nothing_is_copied(tmp_path):
    fake_server(tmp_path / "server", skip=1)
    code, out, dest, repo = _run(tmp_path, dry_run=False)
    assert code == 1 and "NOT SAFE TO DELETE THE SERVER" in out and "1 of 160 phase 1 job files missing" in out
    assert "NOT copying" in out and list(repo.iterdir()) == []
    shutil.rmtree(tmp_path / "server"), shutil.rmtree(dest)  # test cleanup of fakes only
    sweep = fake_server(tmp_path / "server")
    (sweep / "logs" / "launcher.lock").write_text(str(os.getpid()))  # a live pid
    code, out, _, _ = _run(tmp_path, dry_run=False)
    assert code == 1 and "the launcher has not exited" in out and "SAFE TO DELETE THE SERVER:" not in out


def test_a_backup_that_differs_from_the_server_fails_the_checksum(tmp_path):
    sweep = fake_server(tmp_path / "server")
    dest = tmp_path / "backups"
    shutil.copytree(tmp_path / "server" / "repro", dest / "repro")
    victim = dest / FD.BACKUP.SWEEP_REL / "parts" / FD.file_name(FD.phase1_jobs()[7])
    victim.write_text(victim.read_text().replace('"drift_rate": 0.0', '"drift_rate": 0.00'))
    code, out, _, repo = _run(tmp_path, dry_run=False, pull=lambda: True)
    assert code == 1 and "SHA-256 differs from the server's" in out and victim.name in out
    assert list(repo.iterdir()) == []


def test_a_different_file_already_in_the_repository_is_never_overwritten(tmp_path):
    fake_server(tmp_path / "server")
    dest = tmp_path / "backups"
    shutil.copytree(tmp_path / "server" / "repro", dest / "repro")
    repo = tmp_path / "repo"
    target = repo / FD.BACKUP.SWEEP_REL / "parts" / FD.file_name(FD.phase1_jobs()[0])
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    code, out, _, _ = _run(tmp_path, dry_run=False, pull=lambda: True)
    assert code == 1 and "not overwritten" in out and target.read_text() == "{}"


def test_structure_check_counts_rows_and_never_opens_one():
    cfg = sm.SyntheticConfig()
    job = FD.phase1_jobs(cfg)[0]
    opened = []

    class Row(dict):
        def __getitem__(self, k):
            opened.append(k)
            return super().__getitem__(k)

        def get(self, k, d=None):
            opened.append(k)
            return super().get(k, d)

        def keys(self):
            opened.append("keys")
            return super().keys()

    value = _job_value(job, cfg)
    value["train"] = [Row(score=1, action="YES", outcome=1) for _ in range(cfg.train_count)]
    value["test"] = [Row(score=1, action="YES", outcome=1) for _ in range(cfg.test_count)]
    assert FD.structure_problems(value, job, cfg) == [] and opened == []
    value["test"] = value["test"][:-1]
    assert FD.structure_problems(value, job, cfg) == [f"expected {cfg.test_count} test rows"]
    wrong = dict(_job_value(job, cfg), condition="accuracy")
    assert "condition" in FD.structure_problems(wrong, job, cfg)[0]


def test_the_script_never_deletes_and_never_touches_hetzner():
    import ast
    source = SCRIPT.read_text()
    text = source.replace(ast.get_docstring(ast.parse(source)), "")  # the code, not the promise
    for banned in ("unlink", "rmtree", "os.remove", "shutil.move", "rm -", "hcloud", "api.hetzner", "kill "):
        assert banned not in text, banned
    assert '"--delete"' not in text and "--delete " not in text
    # blinding: no result field is ever read
    for field in ('["score', "['score", '["action', '["outcome', '["calibrated', "pnl"):
        assert field not in text, field
