#!/usr/bin/env python3
"""Copy finished sweep results off the server, every few hours, unattended.

Two modes. Both only ever ADD files: nothing is deleted at either end, a file is
never overwritten by a damaged copy, and a failed cycle is logged and retried at
the next one. Safe to leave running in tmux (Ctrl-C stops it between steps).

pull (RECOMMENDED; runs on the Mac, the server holds no credentials):

    caffeinate -i python3 scripts/cloud/backup_results.py pull --every-hours 3

  rsyncs the sweep's job files, logs, calibration and cross-platform files from
  ``flyshi`` (the ssh alias of server-setup.md) into ~/flyshi-backups/, outside the
  git working tree, so nothing half-finished can be committed by accident.
  ``*.partial`` files (a write in progress) are never copied. After each cycle,
  every job file is checked: non-empty, below the size ceiling, whole JSON.
  The Mac must be awake (caffeinate) and online; missed cycles catch up.

push (alternative; runs on the server, needs a GitHub deploy key with write access):

    python3 scripts/cloud/backup_results.py push --every-hours 3

  commits new, checked job files to the server clone and pushes them to the
  branch results-backup/<config hash>, never to main. Files failing the check
  are not committed and are reported. Create the deploy key yourself and delete
  it from GitHub when the run is over (server-setup.md, "Never give an AI agent").

Standard library only: runs with any python3 on the Mac or the server.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[2]
CONFIG_HASH = "a325e6b206"  # synthetic-market sweep, design (b'); tests pin it to the config
RESULTS_REL = "repro/mushroom_body/results"
SWEEP_REL = f"{RESULTS_REL}/synthetic_market_{CONFIG_HASH}"
EXTRA_REL = (f"{RESULTS_REL}/server_calibration",)
EXTRA_GLOB = "cross_platform_check_*.json"
MAX_JOB_FILE_BYTES = 5 * 1024 ** 2  # expected about 0.5 MB per job (cost-estimate.md)
DEFAULT_DEST = Path.home() / "flyshi-backups"
BRANCH = f"results-backup/{CONFIG_HASH}"


def check_job_file(path: Path, max_bytes: int = MAX_JOB_FILE_BYTES) -> Optional[str]:
    """None if the job file is fine, else the reason it is not."""
    try:
        size = path.stat().st_size
    except OSError as error:
        return f"unreadable ({error})"
    if size == 0:
        return "empty"
    if size > max_bytes:
        return f"{size:,} bytes exceeds the {max_bytes:,}-byte ceiling"
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        return f"not whole JSON ({error.__class__.__name__})"
    if not isinstance(value, dict) or not {"condition", "train", "test"} <= set(value):
        return "JSON without the job fields condition/train/test"
    return None


def check_tree(sweep_dir: Path) -> Tuple[List[Path], List[Tuple[Path, str]]]:
    good, bad = [], []
    for path in sorted((sweep_dir / "parts").glob("*.json")):
        reason = check_job_file(path)
        (bad.append((path, reason)) if reason else good.append(path))
    return good, bad


def run(cmd: Sequence[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, timeout=3600)


# ---- pull (Mac) ------------------------------------------------------------------ #
def rsync_commands(remote: str, remote_repo: str, dest: Path, make_dirs: bool = True) -> List[List[str]]:
    """One rsync per source; never --delete; partial files excluded. ``remote`` may be
    empty for a local source (tests). ``make_dirs=False`` only builds the commands and
    creates nothing (a dry run)."""
    prefix = f"{remote}:" if remote else ""
    cmds = []
    for rel in (SWEEP_REL, *EXTRA_REL):
        target = dest / rel
        if make_dirs:
            target.parent.mkdir(parents=True, exist_ok=True)
        cmds.append(["rsync", "-a", "--exclude", "*.partial", "--exclude", "launcher.lock",
                     f"{prefix}{remote_repo}/{rel}", str(target.parent) + "/"])
    if make_dirs:
        (dest / RESULTS_REL).mkdir(parents=True, exist_ok=True)
    cmds.append(["rsync", "-a", "--include", EXTRA_GLOB, "--exclude", "*",
                 f"{prefix}{remote_repo}/{RESULTS_REL}/", str(dest / RESULTS_REL) + "/"])
    return cmds


def pull_cycle(remote: str, remote_repo: str, dest: Path, log: Callable[[str], None]) -> bool:
    ok = True
    for cmd in rsync_commands(remote, remote_repo, dest):
        result = run(cmd)
        # 23 = some files could not be transferred (e.g. the source does not exist yet)
        if result.returncode not in (0, 23):
            ok = False
            log(f"rsync failed (exit {result.returncode}): {result.stderr.strip()[:300]}")
    good, bad = check_tree(dest / SWEEP_REL)
    log(f"pull: {len(good)} job files checked OK in {dest / SWEEP_REL}"
        + (f"; {len(bad)} FAILED the check: " + "; ".join(f"{p.name}: {r}" for p, r in bad) if bad else ""))
    return ok and not bad


# ---- push (server) --------------------------------------------------------------- #
def push_cycle(repo: Path, log: Callable[[str], None], remote_name: str = "origin",
               branch: str = BRANCH, push: bool = True) -> bool:
    good, bad = check_tree(repo / SWEEP_REL)
    for path, reason in bad:
        log(f"push: NOT committing {path.name}: {reason}")
    rels = [str(p.relative_to(repo)) for p in good]
    rels += [str(p.relative_to(repo)) for p in sorted((repo / SWEEP_REL / "logs").glob("*.log"))]
    for extra in EXTRA_REL:
        rels += [str(p.relative_to(repo)) for p in sorted((repo / extra).glob("*.json"))]
    rels += [str(p.relative_to(repo)) for p in sorted((repo / RESULTS_REL).glob(EXTRA_GLOB))]
    if rels:
        result = run(["git", "add", "--", *rels], cwd=repo)
        if result.returncode:
            log(f"push: git add failed: {result.stderr.strip()[:300]}")
            return False
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=repo).stdout.split()
    if staged:
        message = (f"Results backup ({CONFIG_HASH}): {len(good)} job files on the server, "
                   f"{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
        result = run(["git", "commit", "-q", "-m", message], cwd=repo)
        if result.returncode:
            log(f"push: git commit failed (is user.name/user.email set?): {result.stderr.strip()[:300]}")
            return False
        log(f"push: committed {len(staged)} changed file(s)")
    else:
        log("push: nothing new to commit")
    if not push:
        return not bad
    result = run(["git", "push", "-q", remote_name, f"HEAD:refs/heads/{branch}"], cwd=repo)
    if result.returncode:
        log(f"push: git push failed: {result.stderr.strip()[:300]}")
        return False
    log(f"push: pushed to {remote_name} {branch}")
    return not bad


# ---- loop ------------------------------------------------------------------------ #
def loop(cycle: Callable[[], bool], every_hours: float, once: bool,
         log: Callable[[str], None]) -> int:
    while True:
        try:
            ok = cycle()
        except Exception as error:  # an unattended loop must survive one bad cycle
            ok = False
            log(f"cycle raised {error.__class__.__name__}: {error}")
        if once:
            return 0 if ok else 1
        log(f"next cycle in {every_hours:g} h")
        time.sleep(every_hours * 3600)


def make_log(path: Optional[Path]) -> Callable[[str], None]:
    def log(message: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
        print(line, flush=True)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as fh:
                fh.write(line + "\n")
    return log


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    pull = sub.add_parser("pull", help="On the Mac: rsync results from the server (recommended).")
    pull.add_argument("--remote", default="flyshi", help="ssh host alias (default flyshi).")
    pull.add_argument("--remote-repo", default="flyshi-research",
                      help="Clone path on the server, relative to its home (default flyshi-research).")
    pull.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    push = sub.add_parser("push", help="On the server: commit and push results to a backup branch.")
    push.add_argument("--repo", type=Path, default=REPO)
    push.add_argument("--remote-name", default="origin")
    for sp in (pull, push):
        sp.add_argument("--every-hours", type=float, default=3.0)
        sp.add_argument("--once", action="store_true", help="One cycle, then exit (0 = all good).")
    args = p.parse_args(argv)
    if args.mode == "pull":
        log = make_log(args.dest / "backup.log")
        return loop(lambda: pull_cycle(args.remote, args.remote_repo, args.dest, log),
                    args.every_hours, args.once, log)
    log = make_log(args.repo / SWEEP_REL / "backup.log")
    return loop(lambda: push_cycle(args.repo, log, args.remote_name), args.every_hours, args.once, log)


if __name__ == "__main__":
    sys.exit(main())
