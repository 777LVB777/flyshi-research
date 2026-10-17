#!/usr/bin/env python3
"""Finish day for the synthetic sweep's phase 1: confirm, pull, verify, copy, decide.

Run on the Mac, from the repository, after the server's launcher has printed
"every selected job is done (160)":

    .venv/bin/python repro/mushroom_body/finish_day.py            # the real thing
    .venv/bin/python repro/mushroom_body/finish_day.py --dry-run  # checks only; pulls and copies nothing

Steps, in order:

  (a) via ``ssh flyshi``, read-only: all 160 phase 1 job files exist on the server,
      no write is in progress (no ``*.partial``), and the launcher has exited (no
      live lock, no launcher or worker process). Also records each file's SHA-256.
  (b) pull everything with ``scripts/cloud/backup_results.py`` (rsync, never
      ``--delete``) into ~/flyshi-backups/.
  (c) verify every phase 1 job file in the backup: whole JSON, the expected job
      fields, identity fields matching the file name, 70 training and 180 test
      rows, the count, and a SHA-256 equal to the server's.
  (d) copy the results into the repository (never overwriting a different file),
      check the copies' SHA-256 again, and print the exact git commands to commit.
  (e) print "SAFE TO DELETE THE SERVER" only if every check passed; otherwise list
      what failed.
  (f) print the ``--finish-phase1`` command to run afterwards.

What it never does: delete anything (here or on the server), touch Hetzner (no
``hcloud``, no API), start or stop a process on the server, or read a result field.
Blinding (synthetic-market-experiment.md, Section 7): before step (f) nothing reads
a score, action, forecast, outcome, reward or P/L. The checks look only at the
top-level keys, the identity fields (condition, strength, market seed) and the
NUMBER of rows; a row is never opened. Checksums are of the raw bytes.

``--dry-run`` runs the read-only checks (a) and (c) and prints what (b) and (d)
would do, without pulling or copying, and never prints the SAFE line.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

from flyshi_research.learning import synthetic_market as sm  # noqa: E402

_spec = importlib.util.spec_from_file_location("backup_results", REPO / "scripts" / "cloud" / "backup_results.py")
BACKUP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BACKUP)

#: every key a run_dataset job file has (synthetic_market.run_dataset)
JOB_KEYS = ("condition", "strength", "market_seed", "drift_rate", "mbon_ids", "mbon_labels", "train", "test",
            "calibrator")

#: runs on the server through ``ssh flyshi python3 - <sweep dir>``: standard library,
#: read-only, hashes raw bytes, opens no JSON
REMOTE_STATUS = r'''
import hashlib, json, os, subprocess, sys
from pathlib import Path
sweep = Path(sys.argv[1]).expanduser()
parts = sweep / "parts"
files = {}
for p in sorted(parts.glob("*.json")) if parts.is_dir() else []:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    files[p.name] = {"sha256": h.hexdigest(), "bytes": p.stat().st_size}
partial = sorted(p.name for p in parts.glob("*.partial")) if parts.is_dir() else []
lock = sweep / "logs" / "launcher.lock"
state = {"exists": lock.exists(), "pid": None, "alive": False}
if lock.exists():
    try:
        state["pid"] = int(lock.read_text().strip())
        os.kill(state["pid"], 0)
        state["alive"] = True
    except (ValueError, OSError) as e:
        state["alive"] = isinstance(e, PermissionError)
procs = []
# the names are in this source, never on a command line, so pgrep cannot match this check itself
for name in ("launch_synthetic_market" + "_parallel.py", "run_synthetic_market" + "_experiment.py"):
    r = subprocess.run(["pgrep", "-f", name], capture_output=True, text=True)
    procs += [f"{name} pid {pid}" for pid in r.stdout.split() if int(pid) not in (os.getpid(), os.getppid())]
print(json.dumps({"sweep_dir_exists": sweep.is_dir(), "files": files, "partial": partial,
                  "lock": state, "processes": procs}))
'''


def phase1_jobs(cfg: Optional[sm.SyntheticConfig] = None) -> List[sm.Job]:
    cfg = cfg or sm.SyntheticConfig()
    return [j for j in sm.plan_jobs(cfg, sm.PHASE1_ARMS) if j.kind == "condition"]


def file_name(job: sm.Job) -> str:
    return job.id.replace(":", "_") + ".json"


def remote_status(remote: str, remote_repo: str, runner: Callable = subprocess.run) -> dict:
    """Step (a)'s one read-only remote call. ``remote`` '' runs it locally (tests)."""
    sweep = f"{remote_repo}/{BACKUP.SWEEP_REL}"
    cmd = ["ssh", "-o", "BatchMode=yes", remote, "python3", "-", sweep] if remote else [sys.executable, "-", sweep]
    result = runner(cmd, input=REMOTE_STATUS, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"remote status failed (exit {result.returncode}): {result.stderr.strip()[:300]}")
    return json.loads(result.stdout)


def check_remote(status: Mapping, expected: List[str]) -> List[str]:
    failures = []
    if not status["sweep_dir_exists"]:
        return ["(a) the sweep directory does not exist on the server"]
    missing = [n for n in expected if n not in status["files"]]
    if missing:
        failures.append(f"(a) {len(missing)} of {len(expected)} phase 1 job files missing on the server, "
                        f"e.g. {missing[:3]}")
    if status["partial"]:
        failures.append(f"(a) write in progress on the server: {status['partial'][:3]}")
    if status["lock"]["alive"]:
        failures.append(f"(a) the launcher lock is live (pid {status['lock']['pid']}): the launcher has not exited")
    if status["processes"]:
        failures.append(f"(a) sweep processes still running: {status['processes'][:4]}")
    return failures


def structure_problems(value: object, job: sm.Job, cfg: sm.SyntheticConfig) -> List[str]:
    """Keys, identity fields and row COUNTS only. Rows are counted with len() and never
    opened, so no score, action, forecast, outcome, reward or P/L is read."""
    if not isinstance(value, dict):
        return ["not a JSON object"]
    problems = [f"missing key {k!r}" for k in JOB_KEYS if k not in value]
    if problems:
        return problems
    if value["condition"] != job.condition:
        problems.append(f"condition {value['condition']!r} != {job.condition!r}")
    if value["strength"] != job.strength or value["market_seed"] != job.market_seed:
        problems.append("strength or market seed does not match the file name")
    if not isinstance(value["train"], list) or len(value["train"]) != cfg.train_count:
        problems.append(f"expected {cfg.train_count} training rows")
    if not isinstance(value["test"], list) or len(value["test"]) != cfg.test_count:
        problems.append(f"expected {cfg.test_count} test rows")
    return problems


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_local(parts: Path, jobs: List[sm.Job], server_files: Mapping[str, Mapping],
                 cfg: sm.SyntheticConfig, step: str = "(c)") -> List[str]:
    failures = []
    for job in jobs:
        path = parts / file_name(job)
        if not path.exists():
            failures.append(f"{step} {path.name}: missing")
            continue
        reason = BACKUP.check_job_file(path)
        if reason:
            failures.append(f"{step} {path.name}: {reason}")
            continue
        problems = structure_problems(json.loads(path.read_text()), job, cfg)
        if problems:
            failures.append(f"{step} {path.name}: {'; '.join(problems)}")
        server = server_files.get(path.name)
        if server is None or sha256_file(path) != server["sha256"]:
            failures.append(f"{step} {path.name}: SHA-256 differs from the server's")
    extra = sorted(p.name for p in parts.glob("*.json") if p.name not in {file_name(j) for j in jobs}) \
        if parts.is_dir() else []
    if extra and step == "(c)":
        print(f"note: {len(extra)} job file(s) besides phase 1 in the backup (not checked): {extra[:3]}")
    return failures


def copy_plan(dest: Path, repo: Path, jobs: List[sm.Job]) -> Tuple[List[Tuple[Path, Path]], List[str]]:
    """(copies to make, conflicts). An identical file already in place is skipped; a
    DIFFERENT file in place is a conflict and is never overwritten."""
    sources: List[Path] = [dest / BACKUP.SWEEP_REL / "parts" / file_name(j) for j in jobs]
    sources += sorted((dest / BACKUP.SWEEP_REL / "logs").glob("*.log"))
    for extra in BACKUP.EXTRA_REL:
        sources += sorted((dest / extra).glob("*.json"))
    sources += sorted((dest / BACKUP.RESULTS_REL).glob(BACKUP.EXTRA_GLOB))
    copies, conflicts = [], []
    for src in sources:
        if not src.exists():
            continue
        target = repo / src.relative_to(dest)
        if target.exists():
            if sha256_file(target) != sha256_file(src):
                conflicts.append(f"(d) {target.relative_to(repo)} already exists in the repository with "
                                 "different content; not overwritten")
            continue
        copies.append((src, target))
    return copies, conflicts


def git_commands(repo: Path, n_jobs: int) -> List[str]:
    paths = [BACKUP.SWEEP_REL, *BACKUP.EXTRA_REL]
    paths += [str(p.relative_to(repo)) for p in sorted((repo / BACKUP.RESULTS_REL).glob(BACKUP.EXTRA_GLOB))]
    return [f"git -C {repo} add -- " + " ".join(paths),
            f"git -C {repo} commit -m \"Synthetic sweep phase 1 results ({BACKUP.CONFIG_HASH}): {n_jobs} job "
            "files, verified against the server's SHA-256\""]


def finish_phase1_command() -> str:
    return ".venv/bin/python repro/mushroom_body/run_synthetic_market_experiment.py --finish-phase1"


def run(remote: str, remote_repo: str, dest: Path, repo: Path, dry_run: bool,
        log: Callable[[str], None] = print, runner: Callable = subprocess.run,
        pull: Optional[Callable[[], bool]] = None) -> int:
    cfg = sm.SyntheticConfig()
    jobs = phase1_jobs(cfg)
    names = [file_name(j) for j in jobs]
    failures: List[str] = []

    log(f"(a) server status ({remote or 'local'}:{remote_repo}), read-only")
    status = remote_status(remote, remote_repo, runner)
    present = sum(n in status["files"] for n in names)
    log(f"    phase 1 job files on the server: {present}/{len(names)}; partial writes: {len(status['partial'])}; "
        f"launcher lock live: {status['lock']['alive']}; sweep processes: {len(status['processes'])}")
    failures += check_remote(status, names)

    if dry_run:
        log("(b) DRY RUN: would run, never with --delete:")
        for cmd in BACKUP.rsync_commands(remote, remote_repo, dest, make_dirs=False):
            log("    " + " ".join(cmd))
    else:
        log(f"(b) pulling into {dest} with scripts/cloud/backup_results.py")
        ok = (pull or (lambda: BACKUP.pull_cycle(remote, remote_repo, dest, lambda m: log("    " + m))))()
        if not ok:
            failures.append("(b) the backup pull reported a failure (see above)")

    parts = dest / BACKUP.SWEEP_REL / "parts"
    log(f"(c) verifying {len(names)} phase 1 job files in {parts} (keys, identity, row counts, SHA-256)")
    local = verify_local(parts, jobs, status["files"], cfg)
    failures += local
    log(f"    all {len(names)} verified" if not local else f"    {len(local)} problem(s)")

    copies, conflicts = copy_plan(dest, repo, jobs)
    failures += conflicts
    if dry_run:
        log(f"(d) DRY RUN: would copy {len(copies)} file(s) into {repo}; {len(conflicts)} conflict(s)")
    elif failures:
        log("(d) NOT copying into the repository: an earlier check failed")
    else:
        for src, target in copies:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        failures += verify_local(repo / BACKUP.SWEEP_REL / "parts", jobs, status["files"], cfg, step="(d)")
        size = sum((repo / BACKUP.SWEEP_REL / "parts" / n).stat().st_size for n in names) / 1024 ** 2
        log(f"(d) copied {len(copies)} file(s) into the repository; phase 1 job files total {size:.1f} MB")
        if not failures:
            log("    commit them with:")
            for line in git_commands(repo, len(names)):
                log("      " + line)

    log("(e) verdict")
    if dry_run:
        log("    DRY RUN: no SAFE line is ever printed in a dry run")
        for f in failures:
            log("    would fail: " + f)
    elif failures:
        log("    NOT SAFE TO DELETE THE SERVER. Failed checks:")
        for f in failures:
            log("    - " + f)
    else:
        log("    SAFE TO DELETE THE SERVER: 160/160 phase 1 job files pulled, verified and copied; "
            "the launcher has exited. (Delete it yourself: server-setup.md, Step 12. This script never does.)")
    log("(f) afterwards, on the Mac, from the repository:")
    log("    " + finish_phase1_command())
    return 0 if not failures else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--remote", default="flyshi", help="ssh host alias (default flyshi).")
    p.add_argument("--remote-repo", default="flyshi-research",
                   help="Clone path on the server, relative to its home (default flyshi-research).")
    p.add_argument("--dest", type=Path, default=BACKUP.DEFAULT_DEST, help="Backup folder (default ~/flyshi-backups).")
    p.add_argument("--repo", type=Path, default=REPO)
    p.add_argument("--dry-run", action="store_true", help="Read-only checks; pull and copy nothing.")
    args = p.parse_args(argv)
    return run(args.remote, args.remote_repo, args.dest, args.repo, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
