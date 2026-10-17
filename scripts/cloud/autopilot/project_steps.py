#!/usr/bin/env python3
"""Project-side steps of the autopilot, run as a subprocess with the model venv.

The autopilot itself is standard library only. These steps need the project's code,
so the autopilot runs them with ``.venv-shiu/bin/python`` and ``PYTHONPATH=<tree>/src``,
which makes them use the code of ``--tree`` rather than the editable install's.

  phase1-jobs                  the 160 phase 1 job file names (JSON list)
  finish-day --source DIR      finish_day.py's steps on this machine: DIR is the server
                               clone where the sweep ran, so (a) checks it locally,
                               (b) has nothing to pull (it re-checks the files in place),
                               (c) verifies, (d) copies into --tree. Prints JSON: its exit
                               code and the git add paths and commit message it prints.
  phase2-jobs --run-dir DIR    the 120 Phase 2 job file names (JSON list)

Reads no result field: finish_day checks keys, identity fields and row counts only.
finish_day's own lines (including its SAFE line, which the autopilot ignores: the
server is still needed for Phase 2) go to stderr, which the autopilot logs.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
import sys
from pathlib import Path


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tree", type=Path, required=True, help="The checkout whose code is used.")
    sub = p.add_subparsers(dest="step", required=True)
    sub.add_parser("phase1-jobs")
    fd_p = sub.add_parser("finish-day")
    fd_p.add_argument("--source", type=Path, required=True)
    p2 = sub.add_parser("phase2-jobs")
    p2.add_argument("--run-dir", type=Path, required=True)
    args = p.parse_args(argv)
    tree = args.tree.resolve()
    mb = tree / "repro" / "mushroom_body"
    sys.path.insert(0, str(mb))

    if args.step == "phase1-jobs":
        fd = load(mb / "finish_day.py", "autopilot_finish_day")
        print(json.dumps([fd.file_name(j) for j in fd.phase1_jobs()]))
        return 0

    if args.step == "finish-day":
        fd = load(mb / "finish_day.py", "autopilot_finish_day")
        source = args.source.resolve()

        def log(message: str) -> None:
            print(message, file=sys.stderr, flush=True)

        def pull() -> bool:  # (b): the files are already here; check them where they are
            good, bad = fd.BACKUP.check_tree(source / fd.BACKUP.SWEEP_REL)
            for path, reason in bad:
                log(f"    {path.name}: {reason}")
            return not bad

        rc = fd.run("", str(source), source, tree, False, log=log, pull=pull)
        add_line, commit_line = fd.git_commands(tree, len(fd.phase1_jobs()))
        add = shlex.split(add_line)
        commit = shlex.split(commit_line)
        print(json.dumps({"rc": rc, "add_paths": add[add.index("--") + 1:],
                          "message": commit[commit.index("-m") + 1]}))
        return 0

    from flyshi_research.learning import real_market as rm
    import run_real_market_experiment as runner

    paths = runner.Paths(args.run_dir)
    print(json.dumps([paths.output(j).name for j in rm.plan_jobs()]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
