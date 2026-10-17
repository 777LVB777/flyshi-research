#!/usr/bin/env python3
"""Unattended autopilot for the CCX33 server: finish Phase 1, run Phase 2, publish, notify.

Runs on the server as the systemd service ``flyshi-autopilot`` (docs/cloud/autopilot.md).
Standard library only. A resumable state machine: the state is one JSON file, every
step is idempotent, and the service can be killed and restarted at any point.

  SETUP           the publish clone (deploy key, origin = the configured push URL) exists
  PHASE1_RUNNING  watch the synthetic sweep's phase 1 (160 jobs, config a325e6b206);
                  restart its launcher if it is gone (job-granular, as the run plan says)
  PHASE1_COMMIT   finish_day.py's steps, run here; commit and push exactly what its
                  printed git commands add; check the pushed files on GitHub
  PHASE1_VERDICT  the main tree is moved to the tag phase2-frozen (checked against GitHub);
                  --finish-phase1 there; commit and push verdict_phase1.json
  PHASE2_DECISION the preregistration's rule for whether Phase 2 runs: one marker line.
                  No rule, or an unclear one: wait and notify; never guess
  PHASE2_INPUTS   the tag still matches GitHub and the main tree; market file SHA-256;
                  the owner's drive sign-off; drive_check.py exits 0
  PHASE2_PREPARE  run_real_market_experiment.py --prepare (chains, frozen comparator)
  PHASE2_RUNNING  launch_real_market_parallel.py --max-procs 4 --gb-per-proc 3.6; watch;
                  budget stop at the configured spend
  PHASE2_PUBLISH  the verdict (--finish), then commit and push verdict.json + hashes.json
  FINAL_VERIFY    every file the autopilot pushed matches its SHA-256 on GitHub
  DONE            "SAFE TO DELETE THE SERVER" has been sent

Blinding: job files are counted, hashed and parsed only to see that they are whole
(their keys, never their values). The only result value read is "readings.overall"
of the two verdict files, which the preregistered verdict code writes.

Never: deletes the server, calls the Hetzner API, force-pushes, commits under data/,
or sends anything but status lines to ntfy.

    python3 autopilot.py run --config ~/.config/flyshi-autopilot/config.json
    python3 autopilot.py status --config ...
    python3 autopilot.py resume --config ...       # after a HALTED notification, once fixed
    python3 autopilot.py notify-test --config ...
    python3 autopilot.py --simulate                 # fake jobs + local bare repo; touches nothing real
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
CONFIG_HASH = "a325e6b206"
SWEEP_REL = f"repro/mushroom_body/results/synthetic_market_{CONFIG_HASH}"
PREREG_REL = "docs/design/phase2-preregistration.md"
SIGNOFF_REL = "docs/records/phase2_build_signoff.md"
PHASE2_PUBLIC_REL = "repro/real_market/results"
RULE_RE = re.compile(r"^<!--\s*autopilot-phase2-rule:\s*(\S+)\s*-->\s*$", re.M)
RULES = ("run-regardless", "do-not-run")
PUSH_URL_RE = re.compile(r"^(git@[\w.-]+:|ssh://git@[\w.-]+/)777LVB777/flyshi-research(\.git)?$")
TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
FAILED_RE = re.compile(r"\[launcher\] FAILED (\S+) \(exit (-?\d+)\)")
OOM_RE = re.compile(r"Killed process \d+")
MARKET_RE = re.compile(r"^markets_([0-9a-f]{12})_cutoff_")
STATES = ("SETUP", "PHASE1_RUNNING", "PHASE1_COMMIT", "PHASE1_VERDICT", "PHASE2_DECISION", "PHASE2_INPUTS",
          "PHASE2_PREPARE", "PHASE2_RUNNING", "PHASE2_PUBLISH", "FINAL_VERIFY", "DONE")

DEFAULTS = {
    "ntfy_server": "https://ntfy.sh",
    "main_tree": "~/flyshi-research",
    "state_dir": "~/flyshi-autopilot",
    "publish_clone": "~/flyshi-autopilot/publish",
    "push_url": "git@github-flyshi:777LVB777/flyshi-research.git",
    "branch": "main",
    "python": ".venv-shiu/bin/python",  # relative to the main tree
    "phase1_tmux_session": "setup",
    "frozen_tag": "phase2-frozen",  # Phase 2 (and --finish-phase1) run exactly this tag's commit
    "ssh_alias": "flyshi",  # only for the copy command in the SAFE notification
    "mac_data_dir": "~/Projects/flyshi-research/data/polymarket/",
    "market_file": "data/polymarket/markets_f3d41123e20e_cutoff_2026-03-01.json",
    "fill_plan": "data/polymarket/fill_plan_f3d41123e20e.json",
    "market_sha256": "0777ae92f0dd6b950e1a0e3495c72c3a89280b421265f2a53cdac3c3b9e2c686",
    "drive_signoff_sha256": "",
    "max_procs": 4,
    "gb_per_proc": 3.6,
    "price_per_hour": 0.266,
    "spend_warn_usd": 85.0,
    "spend_stop_usd": 95.0,
    "stall_hours": 12.0,
    "disk_min_free_fraction": 0.10,
    "alive_every_hours": 24.0,
    "poll_seconds": 300,
    "max_relaunches": 3,
    "max_step_errors": 3,
}
REQUIRED = ("ntfy_topic", "git_user_name", "git_user_email")
PATH_KEYS = ("main_tree", "state_dir", "publish_clone")

#: data guard for Phase 2 commits: any of these keys, a list longer than MAX_LIST or a
#: mapping with more than MAX_KEYS entries is treated as per-market records
FORBIDDEN_KEYS = {"market_id", "market_ids", "training_ids", "ids", "quote", "quotes", "outcome", "outcomes",
                  "price", "prices", "history", "histories", "recent_change", "decision_time",
                  "price_time_unix", "train", "test", "rows", "chains", "question", "event_id"}
MAX_LIST, MAX_KEYS = 50, 200
PRIVATE_NAME_RE = re.compile(r"(^|/)(markets_.*_cutoff_.*\.json|histories_.*|.*\.outcomes\.json|fill_plan_.*\.json"
                             r"|frozen_market_list\.json|manifest\.json|chains\.json|comparator\.json"
                             r"|metadata_.*\.json|request_log\.jsonl)$")
MANIFEST_HASH_KEYS = ("market_file_sha256", "fill_plan_sha256", "frozen_sha256", "chains_sha256",
                      "comparator_sha256", "locked_config_hash", "prepared_utc", "prestated", "design")


class StepWait(Exception):
    """Not an error: a condition the owner must meet. Re-checked every tick."""


class StepHalt(Exception):
    """Stop until the owner runs ``autopilot.py resume``."""


class CommandFailed(Exception):
    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


# ---- small helpers ------------------------------------------------------------------ #
def utc(t: Optional[float] = None) -> str:
    return datetime.fromtimestamp(time.time() if t is None else t, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_atomic(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(value, fh, indent=1, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def whole_json(path: Path, keys: Sequence[str] = ()) -> bool:
    """True if the file is a whole JSON object with these keys. Values are never read."""
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return False
    return isinstance(value, dict) and set(keys) <= set(value)


def copy_identical(src: Path, dst: Path) -> None:
    """Copy, or nothing if an identical file is there; never overwrite a different one."""
    if dst.exists():
        if sha256_file(dst) != sha256_file(src):
            raise StepHalt(f"{dst.name} already exists in the publish clone with different content")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def per_market_problems(value, where: str = "$") -> List[str]:
    """Why a JSON value looks like it holds per-market records (empty if it does not)."""
    out: List[str] = []
    if isinstance(value, dict):
        if len(value) > MAX_KEYS:
            out.append(f"{where}: {len(value)} keys")
        for k, v in value.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                out.append(f"{where}: key {k!r}")
            out += per_market_problems(v, f"{where}.{k}")
    elif isinstance(value, list):
        if len(value) > MAX_LIST:
            out.append(f"{where}: list of {len(value)}")
        for i, v in enumerate(value[:MAX_LIST + 1]):
            out += per_market_problems(v, f"{where}[{i}]")
    return out


def staged_problems(root: Path, staged: Iterable[str], allowed: Sequence[str], per_market: bool) -> List[str]:
    """The commit guard. Every commit: nothing under data/, no private file name, nothing
    outside the step's own paths. Phase 2 commits: JSON only, and no per-market records."""
    problems = []
    for rel in staged:
        if rel == "data" or rel.startswith("data/"):
            problems.append(f"{rel}: under data/")
            continue
        if PRIVATE_NAME_RE.search(rel):
            problems.append(f"{rel}: a private data file name")
            continue
        if not any(rel == a or rel.startswith(a.rstrip("/") + "/") for a in allowed):
            problems.append(f"{rel}: outside this step's paths")
            continue
        if per_market:
            if not rel.endswith(".json"):
                problems.append(f"{rel}: not JSON")
                continue
            try:
                value = json.loads((root / rel).read_bytes())
            except (OSError, ValueError):
                problems.append(f"{rel}: not readable JSON")
                continue
            found = per_market_problems(value)
            if found:
                problems.append(f"{rel}: per-market records ({found[0]})")
    return problems


def read_overall(path: Path) -> str:
    """The verdict line, as the preregistered verdict code worded it."""
    return str(json.loads(path.read_text())["readings"]["overall"])


# ---- configuration --------------------------------------------------------------- #
def load_config(path: Path, simulated: bool = False) -> dict:
    raw = json.loads(Path(path).expanduser().read_text())
    cfg = {**DEFAULTS, **raw}
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        raise SystemExit(f"config {path}: missing {', '.join(missing)}")
    if not simulated:
        if not TOPIC_RE.match(cfg["ntfy_topic"]):
            raise SystemExit("config: ntfy_topic must be 32-64 random letters, digits, '-' or '_'")
        if not PUSH_URL_RE.match(cfg["push_url"]):
            raise SystemExit("config: push_url must be an ssh URL of 777LVB777/flyshi-research")
    for k in PATH_KEYS:
        cfg[k] = Path(str(cfg[k])).expanduser()
    return cfg


# ---- git ------------------------------------------------------------------------- #
class Git:
    def __init__(self, repo: Optional[Path], cfg: dict) -> None:
        self.repo = repo
        self.ident = ["-c", f"user.name={cfg['git_user_name']}", "-c", f"user.email={cfg['git_user_email']}"]
        self.env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}

    def run(self, *args: str, check: bool = True, binary: bool = False) -> subprocess.CompletedProcess:
        cmd = ["git", *(["-C", str(self.repo)] if self.repo else []), *self.ident, *args]
        r = subprocess.run(cmd, capture_output=True, text=not binary, env=self.env, timeout=900)
        if check and r.returncode != 0:
            err = r.stderr if not binary else r.stderr.decode(errors="replace")
            raise CommandFailed(f"git {args[0]} exited {r.returncode}", err)
        return r

    def __call__(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    def blob(self, ref: str, path: str) -> bytes:
        return self.run("cat-file", "blob", f"{ref}:{path}", binary=True).stdout


# ---- the real server ---------------------------------------------------------------- #
class RealEnv:
    """Everything that touches the machine, the project's scripts or the network."""

    simulated = False

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.main: Path = cfg["main_tree"]
        self.clone: Path = cfg["publish_clone"]
        self.logs = cfg["state_dir"] / "logs"

    # time, log, notifications
    def now(self) -> float:
        return time.time()

    def log(self, message: str) -> None:
        print(f"{utc()} {message}", flush=True)  # systemd appends stdout to the log file

    def send(self, title: str, message: str, priority: str) -> bool:
        url = f"{self.cfg['ntfy_server'].rstrip('/')}/{self.cfg['ntfy_topic']}"
        req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST",
                                     headers={"Title": title.encode("ascii", "replace").decode(),
                                              "Priority": priority, "Tags": "fly"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return 200 <= resp.status < 300
        except OSError as error:
            self.log(f"ntfy send failed ({error.__class__.__name__}); kept for the next tick")
            return False

    # processes
    def _python(self) -> str:
        return str(self.main / self.cfg["python"])

    def _proc_env(self, tree: Path) -> dict:
        return {**os.environ, "PYTHONPATH": str(tree / "src"), "OMP_NUM_THREADS": "1"}

    def _run_logged(self, cmd: List[str], tree: Path, log_name: str, stdout=subprocess.DEVNULL,
                    timeout: int = 6 * 3600) -> int:
        """Run a project command in ``tree``. stderr (and stdout if given a file) go to a
        private log under state_dir/logs, never to ntfy."""
        self.logs.mkdir(parents=True, exist_ok=True)
        log_path = self.logs / f"{log_name}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.log"
        with open(log_path, "w") as err:
            r = subprocess.run(cmd, cwd=tree, env=self._proc_env(tree), stdout=stdout if stdout is not None else err,
                               stderr=err, stdin=subprocess.DEVNULL, timeout=timeout)
        self.log(f"{log_name}: exit {r.returncode} (log {log_path})")
        return r.returncode

    def _project(self, tree: Path, *args: str) -> subprocess.CompletedProcess:
        cmd = [self._python(), str(HERE / "project_steps.py"), "--tree", str(tree), *args]
        r = subprocess.run(cmd, cwd=tree, env=self._proc_env(tree), capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=3 * 3600)
        if r.stderr:
            self.logs.mkdir(parents=True, exist_ok=True)
            with open(self.logs / f"project_{args[0]}.log", "a") as fh:
                fh.write(f"--- {utc()}\n{r.stderr}")
        if r.returncode != 0:
            raise CommandFailed(f"project step {args[0]} exited {r.returncode}", r.stderr[-3000:])
        return r

    def _pgrep(self, name: str) -> List[int]:
        r = subprocess.run(["pgrep", "-f", name], capture_output=True, text=True)
        return [int(x) for x in r.stdout.split() if int(x) != os.getpid()]

    @staticmethod
    def _lock_alive(lock: Path) -> bool:
        try:
            pid = int(lock.read_text().strip())
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except (OSError, ValueError):
            return False

    # phase 1
    def phase1_parts(self) -> Path:
        return self.main / SWEEP_REL / "parts"

    def phase1_job_names(self) -> List[str]:
        return json.loads(self._project(self.clone, "phase1-jobs").stdout)

    def launcher_state(self, phase: str, run_dir: Optional[Path] = None) -> dict:
        if phase == "phase1":
            base, launcher, worker = self.main / SWEEP_REL, "launch_synthetic_market_parallel.py", \
                "run_synthetic_market_experiment.py"
        else:
            base, launcher, worker = run_dir, "launch_real_market_parallel.py", "run_real_market_experiment.py"
        parts = base / "parts"
        return {"alive": self._lock_alive(base / "logs" / "launcher.lock") or bool(self._pgrep(launcher)),
                "workers": len(self._pgrep(worker)),
                "partial": len(list(parts.glob("*.partial"))) if parts.is_dir() else 0}

    def start_launcher(self, phase: str, run_dir: Optional[Path] = None) -> None:
        mb = self.main / "repro" / "mushroom_body"
        common = ["--max-procs", str(self.cfg["max_procs"]), "--gb-per-proc", str(self.cfg["gb_per_proc"])]
        if phase == "phase1":
            cmd = [self._python(), str(mb / "launch_synthetic_market_parallel.py"), *common, "--phase", "1"]
            log_path = self.logs / "phase1_launcher.log"
        else:
            cmd = [self._python(), str(mb / "launch_real_market_parallel.py"), "--run-dir", str(run_dir), *common,
                   "--stop-file", str(run_dir / "STOP_LAUNCHING")]
            log_path = run_dir / "logs" / "autopilot_launcher.log"  # private: under data/
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as fh:
            fh.write(f"--- autopilot start {utc()}: {' '.join(cmd)}\n")
            fh.flush()
            # its own session: a restart of the autopilot service does not stop it
            subprocess.Popen(cmd, cwd=self.main, env=self._proc_env(self.main), stdout=fh,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)

    def launcher_failures(self, phase: str, run_dir: Optional[Path] = None) -> List[str]:
        texts = []
        if phase == "phase1":
            r = subprocess.run(["tmux", "capture-pane", "-p", "-J", "-S", "-50000", "-t",
                                self.cfg["phase1_tmux_session"]], capture_output=True, text=True)
            texts.append(r.stdout if r.returncode == 0 else "")
            paths = [self.logs / "phase1_launcher.log"]
        else:
            paths = [run_dir / "logs" / "autopilot_launcher.log"]
        for p in paths:
            try:
                texts.append(p.read_text(errors="replace"))
            except OSError:
                pass
        return [m.group(0) for t in texts for m in FAILED_RE.finditer(t)]

    def oom_kills(self, since: float) -> int:
        try:
            r = subprocess.run(["journalctl", "-k", "--since", f"@{int(since)}", "--no-pager", "-q", "-o", "cat"],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return 0
        return len(OOM_RE.findall(r.stdout)) if r.returncode == 0 else 0

    def disk_free_fraction(self) -> float:
        du = shutil.disk_usage(self.main)
        return du.free / du.total

    def finish_day(self) -> dict:
        return json.loads(self._project(self.clone, "finish-day", "--source", str(self.main)).stdout)

    def finish_phase1(self) -> int:
        cmd = [self._python(), str(self.main / "repro/mushroom_body/run_synthetic_market_experiment.py"),
               "--finish-phase1"]
        return self._run_logged(cmd, self.main, "finish_phase1")  # stdout (the verdict JSON) discarded

    # phase 2
    def phase2_job_names(self, run_dir: Path) -> List[str]:
        return json.loads(self._project(self.main, "phase2-jobs", "--run-dir", str(run_dir)).stdout)

    def drive_check(self, market: Path, report: Path) -> int:
        cmd = [self._python(), str(self.main / "repro/polymarket/drive_check.py"), "--market-file", str(market),
               "--data-dir", str(market.parent)]
        with open(report, "w") as out:  # private: under data/
            return self._run_logged(cmd, self.main, "drive_check", stdout=out)

    def prepare(self, market: Path, fill_plan: Path, run_dir: Path) -> int:
        cmd = [self._python(), str(self.main / "repro/mushroom_body/run_real_market_experiment.py"), "--prepare",
               "--market-file", str(market), "--fill-plan", str(fill_plan), "--run-dir", str(run_dir)]
        return self._run_logged(cmd, self.main, "prepare")

    def finish_phase2(self, run_dir: Path) -> int:
        cmd = [self._python(), str(self.main / "repro/mushroom_body/run_real_market_experiment.py"), "--finish",
               "--run-dir", str(run_dir)]
        return self._run_logged(cmd, self.main, "finish_phase2")  # stdout (the verdict JSON) discarded


# ---- the state machine --------------------------------------------------------------- #
def new_state(now: float) -> dict:
    return {"version": 1, "state": "SETUP", "wait": None, "halt": None, "errors": 0, "notified": {},
            "seen_failures": [], "phase1": {}, "phase2": {}, "commits": {}, "pushed": {}, "outbox": [],
            "last_alive": None, "journal_since": now, "created": now}


class Autopilot:
    def __init__(self, cfg: dict, env) -> None:
        self.cfg, self.env = cfg, env
        self.main: Path = cfg["main_tree"]
        self.clone: Path = cfg["publish_clone"]
        self.state_path: Path = cfg["state_dir"] / "state.json"
        self.s = json.loads(self.state_path.read_text()) if self.state_path.exists() else new_state(env.now())
        self.branch = cfg["branch"]

    # -- bookkeeping
    def save(self) -> None:
        write_json_atomic(self.state_path, self.s)

    def git(self, repo: Optional[Path]) -> Git:
        return Git(repo, self.cfg)

    def notify(self, title: str, message: str, priority: str = "default", key: Optional[str] = None) -> None:
        if key is not None:
            if key in self.s["notified"]:
                return
            self.s["notified"][key] = self.env.now()
        self.env.log(f"notify [{priority}] {title}: {message}")
        self.s["outbox"].append({"title": title, "message": message, "priority": priority})
        self.flush_outbox()
        self.save()

    def flush_outbox(self) -> None:
        while self.s["outbox"]:
            item = self.s["outbox"][0]
            if not self.env.send(item["title"], item["message"], item["priority"]):
                return
            self.s["outbox"].pop(0)

    def halt(self, state: str, reason: str) -> None:
        self.s["halt"] = {"state": state, "reason": reason, "t": self.env.now()}
        self.notify(f"HALTED in {state}", f"{reason}. Fix it, then run: python3 autopilot.py resume", "urgent")

    # -- phase 2 paths
    def market(self) -> Path:
        return self.main / self.cfg["market_file"]

    def run_dir(self) -> Path:
        return self.market().parent / f"phase2_{self.cfg['market_sha256'][:12]}"

    def phase2_inputs(self) -> Dict[str, Path]:
        market = self.market()
        m = MARKET_RE.match(market.name)
        if not m:
            raise StepHalt(f"market_file {market.name} is not named markets_<frozen12>_cutoff_<date>.json")
        d = market.parent
        return {market.name: market, Path(self.cfg["fill_plan"]).name: self.main / self.cfg["fill_plan"],
                "frozen_market_list.json": d / "frozen_market_list.json",
                "frozen_market_list.json.sha256": d / "frozen_market_list.json.sha256",
                f"histories_{m.group(1)}.jsonl": d / f"histories_{m.group(1)}.jsonl"}

    # -- the loop body
    def tick(self) -> None:
        self.flush_outbox()
        try:
            self.watchdogs()
        except Exception as error:  # a watchdog must never stop the machine
            self.env.log(f"watchdog error: {error!r}")
        state = self.s["state"]
        if self.s["halt"] or state == "DONE":
            self.save()
            return
        try:
            nxt = getattr(self, "step_" + state.lower())()
        except StepWait as wait:
            reason = str(wait)
            if self.s["wait"] != reason:
                self.s["wait"] = reason
                self.notify(f"Waiting ({state})", reason, "high")
            self.save()
            return
        except StepHalt as stop:
            self.halt(state, str(stop))
            return
        except Exception as error:
            self.s["errors"] += 1
            self.env.log(f"error in {state} ({self.s['errors']}): {traceback.format_exc()}"
                         + (f"\ndetail: {error.detail}" if isinstance(error, CommandFailed) else ""))
            brief = f"{type(error).__name__}: {str(error)[:200]}"
            if self.s["errors"] >= self.cfg["max_step_errors"]:
                self.halt(state, f"failed {self.s['errors']} times, last {brief}; details in the server log")
            elif self.s["errors"] == 1:
                self.notify(f"Error in {state}", f"{brief}; retrying at the next check", "high")
            self.save()
            return
        self.s["wait"], self.s["errors"] = None, 0
        if nxt and nxt != state:
            self.env.log(f"state {state} -> {nxt}")
            self.s["state"] = nxt
        self.save()

    def status_line(self) -> str:
        p1, p2 = self.s["phase1"], self.s["phase2"]
        parts = [f"state {self.s['state']}"]
        if p1.get("jobs"):
            parts.append(f"phase 1 jobs {p1.get('done', 0)}/{len(p1['jobs'])}")
        if p2.get("jobs"):
            parts.append(f"phase 2 jobs {p2.get('done', 0)}/{len(p2['jobs'])}")
        if p2.get("started_at"):
            parts.append(f"est. Phase 2 spend ${self.spend():.2f}")
        if self.s["wait"]:
            parts.append("WAITING: " + self.s["wait"][:120])
        if self.s["halt"]:
            parts.append("HALTED: " + self.s["halt"]["reason"][:120])
        return "; ".join(parts)

    def spend(self) -> float:
        p2 = self.s["phase2"]
        end = p2.get("ended_at") or self.env.now()
        return max(0.0, end - p2["started_at"]) / 3600.0 * self.cfg["price_per_hour"]

    # -- watchdogs: notify only, except the budget stop
    def watchdogs(self) -> None:
        now, cfg, state = self.env.now(), self.cfg, self.s["state"]
        free = self.env.disk_free_fraction()
        if free < cfg["disk_min_free_fraction"]:
            self.notify("Disk low", f"{free:.0%} of the server disk is free", "high", key="disk")
        elif free > cfg["disk_min_free_fraction"] + 0.02:
            self.s["notified"].pop("disk", None)
        kills = self.env.oom_kills(self.s["journal_since"])
        self.s["journal_since"] = now
        if kills:
            self.notify("Out of memory", f"the kernel killed {kills} process(es) for lack of memory", "high")
        if state in ("PHASE1_RUNNING", "PHASE2_RUNNING"):
            phase = "phase1" if state == "PHASE1_RUNNING" else "phase2"
            p = self.s[phase]
            seen: Dict[str, int] = {}
            for line in self.env.launcher_failures(phase, self.run_dir()):
                seen[line] = seen.get(line, 0) + 1  # the n-th time this line appears is a new failure
                key = f"{phase}:{seen[line]}:{line}"
                if key not in self.s["seen_failures"]:
                    self.s["seen_failures"].append(key)
                    m = FAILED_RE.search(line)
                    self.notify("Job crashed", f"{phase.replace('phase', 'Phase ')} job {m.group(1)} exited "
                                f"{m.group(2)}" + (" (killed: likely out of memory)" if m.group(2) == "-9" else ""),
                                "high")
            last = max(p.get("last_done_at") or 0, p.get("watch_started") or 0)
            if p.get("jobs") and last and now - last > cfg["stall_hours"] * 3600:
                self.notify("No job finished", f"{phase.replace('phase', 'Phase ')}: no job finished for "
                            f"{(now - last) / 3600:.0f} h ({p.get('done', 0)}/{len(p['jobs'])} done)", "high",
                            key=f"stall:{phase}:{last}")
        p2 = self.s["phase2"]
        if p2.get("started_at") and not p2.get("ended_at"):
            spend = self.spend()
            if spend > cfg["spend_warn_usd"]:
                self.notify("Phase 2 spend", f"estimated Phase 2 spend ${spend:.2f} passed "
                            f"${cfg['spend_warn_usd']:.0f}", "high", key="spend_warn")
            if spend > cfg["spend_stop_usd"]:
                stop = self.run_dir() / "STOP_LAUNCHING"
                if not stop.exists():
                    stop.write_text(f"budget stop by the autopilot at {utc(now)}: ${spend:.2f}\n")
                self.notify("Phase 2 budget stop", f"estimated spend ${spend:.2f} passed "
                            f"${cfg['spend_stop_usd']:.0f}: no new job is started; running jobs finish",
                            "urgent", key="spend_stop")
        if self.s["last_alive"] is None or now - self.s["last_alive"] >= cfg["alive_every_hours"] * 3600:
            self.s["last_alive"] = now
            self.notify("Still alive", self.status_line(), "low")

    # -- git steps shared by the commit states
    def sync_clone(self) -> None:
        g = self.git(self.clone)
        g("reset", "-q")  # unstage anything a step left staged before a restart; files stay
        g("fetch", "-q", "origin")
        if g("rev-list", f"origin/{self.branch}..HEAD"):
            g("rebase", "-q", f"origin/{self.branch}")
        else:
            g("merge", "-q", "--ff-only", f"origin/{self.branch}")

    def commit_and_push(self, paths: List[str], message: str, per_market: bool) -> str:
        g = self.git(self.clone)
        g("add", "--", *paths)  # never -f: ignored files stay out
        staged = [x for x in g("diff", "--cached", "--name-only").splitlines() if x]
        problems = staged_problems(self.clone, staged, paths, per_market)
        if problems:
            g("reset", "-q")
            raise StepHalt("commit aborted by the data guard: " + "; ".join(problems[:3]))
        if staged:
            g("commit", "-q", "-m", message)
        for attempt in range(4):
            g("fetch", "-q", "origin")
            if not g("rev-list", f"origin/{self.branch}..HEAD"):
                break  # everything is on GitHub
            if attempt == 3:
                raise StepHalt("the push to GitHub was rejected three times")
            if g.run("push", "-q", "origin", f"HEAD:refs/heads/{self.branch}", check=False).returncode == 0:
                continue  # the next fetch confirms it landed
            g("rebase", "-q", f"origin/{self.branch}")  # someone pushed meanwhile; never force
        sha = g("log", "-1", "--format=%H", "--", *paths)
        if not sha:
            raise StepHalt("nothing was committed for " + ", ".join(paths))
        return sha

    def verify_pushed(self, sha: str, paths: List[str], sources: Dict[str, Path],
                      require: Sequence[str] = ()) -> None:
        """The pushed commit is on GitHub's branch and each of its files there has the
        SHA-256 of the local source file (the original, not only the copy)."""
        g = self.git(self.clone)
        g("fetch", "-q", "origin")
        ref = f"origin/{self.branch}"
        if g.run("merge-base", "--is-ancestor", sha, ref, check=False).returncode != 0:
            raise StepHalt(f"commit {sha[:7]} is not on GitHub's {self.branch}")
        files = [x for x in g("diff-tree", "--no-commit-id", "--name-only", "-r", sha).splitlines() if x]
        on_remote = set(g("ls-tree", "-r", "--name-only", ref, "--", *paths).splitlines())
        missing = [r for r in require if r not in on_remote]
        if missing:
            raise StepHalt(f"{len(missing)} expected file(s) not on GitHub, e.g. {missing[0]}")
        bad = []
        for rel in sorted(set(files) | set(require)):
            local = sources.get(rel, self.main / rel)
            if not local.exists():
                local = self.clone / rel
            digest = sha256_bytes(g.blob(ref, rel))
            if digest != sha256_file(local):
                bad.append(rel)
            else:
                self.s["pushed"][rel] = digest
        if bad:
            raise StepHalt(f"{len(bad)} file(s) on GitHub differ from the local SHA-256, e.g. {bad[0]}")
        self.save()

    def remote_tag_commit(self) -> Optional[str]:
        """The commit the frozen tag points to on GitHub (peeled), or None if absent."""
        tag = f"refs/tags/{self.cfg['frozen_tag']}"
        out = self.git(self.clone)("ls-remote", "origin", tag, tag + "^{}")
        refs = dict(reversed(line.split("\t")) for line in out.splitlines() if "\t" in line)
        return refs.get(tag + "^{}") or refs.get(tag)

    def pin_frozen_tag(self) -> str:
        """Fetch the frozen tag into the publish clone, check it equals GitHub's, and move
        the main tree to it. Done once; the commit is recorded as Phase 2's code."""
        tag = self.cfg["frozen_tag"]
        remote = self.remote_tag_commit()
        if not remote:
            raise StepWait(f"the git tag {tag} is not on GitHub; create and push it (guide step 2). Phase 1's "
                           "verdict and Phase 2 run exactly that commit")
        p2 = self.s["phase2"]
        if p2.get("code_sha") and p2["code_sha"] != remote:
            raise StepHalt(f"the tag {tag} on GitHub moved from {p2['code_sha'][:7]} to {remote[:7]}; "
                           "Phase 2 is not started on a moved tag")
        g = self.git(self.clone)
        g("fetch", "-q", "--force", "origin", f"+refs/tags/{tag}:refs/tags/{tag}")
        if g("rev-parse", f"{tag}^{{commit}}") != remote:
            raise StepHalt(f"the tag {tag} fetched from GitHub does not match GitHub's listing")
        self.update_main_tree(remote, f"+refs/tags/{tag}:refs/tags/{tag}")
        p2["code_sha"] = remote
        self.save()
        return remote

    def verify_frozen_tag(self) -> None:
        """Before Phase 2 starts: the tag still exists on GitHub, still points to the
        pinned commit, and the main tree is checked out at exactly that commit."""
        tag, pinned = self.cfg["frozen_tag"], self.s["phase2"].get("code_sha")
        remote = self.remote_tag_commit()
        if not remote:
            raise StepHalt(f"the git tag {tag} is missing on GitHub; Phase 2 is not started")
        if remote != pinned:
            raise StepHalt(f"the git tag {tag} on GitHub ({remote[:7]}) differs from the pinned commit "
                           f"({(pinned or 'none')[:7]}); Phase 2 is not started")
        if self.git(self.main)("rev-parse", "HEAD") != pinned:
            raise StepHalt(f"the main tree is not at the pinned commit {pinned[:7]}; Phase 2 is not started")

    def update_main_tree(self, sha: str, refspec: str) -> None:
        """Move the main tree (venv, connectome data, the sweep's files) to ``sha``,
        fetched from the publish clone. Refuses if a tracked file was changed or an
        untracked file would be replaced by different content."""
        g = self.git(self.main)
        if g("rev-parse", "HEAD") == sha:
            return
        if g("status", "--porcelain", "--untracked-files=no"):
            raise StepHalt("the main tree has changes to tracked files; it was not updated")
        g("fetch", "-q", "--force", str(self.clone), refspec)
        g("cat-file", "-e", f"{sha}^{{commit}}")
        for rel in [x for x in g("diff", "--name-only", "HEAD", sha).splitlines() if x]:
            f = self.main / rel
            tracked = g.run("ls-files", "--error-unmatch", "--", rel, check=False).returncode == 0
            if f.exists() and not tracked:
                try:
                    blob = g.blob(sha, rel)
                except CommandFailed:
                    continue
                if sha256_bytes(blob) != sha256_file(f):
                    raise StepHalt(f"untracked {rel} in the main tree differs from commit {sha[:7]}")
        g("-c", "advice.detachedHead=false", "checkout", "-q", "-f", "--detach", sha)
        self.env.log(f"main tree now at {sha[:7]}")

    # -- the steps; each returns the next state (None: stay)
    def step_setup(self) -> str:
        if not (self.clone / ".git").exists():
            self.clone.parent.mkdir(parents=True, exist_ok=True)
            self.git(None)("clone", "-q", "--branch", self.branch, self.cfg["push_url"], str(self.clone))
        g = self.git(self.clone)
        if g("remote", "get-url", "origin") != self.cfg["push_url"]:
            raise StepHalt("the publish clone's origin is not the configured push_url")
        if g("rev-parse", "--abbrev-ref", "HEAD") != self.branch:
            g("checkout", "-q", self.branch)
        self.notify("Autopilot started", self.status_line(), key="started")
        return "PHASE1_RUNNING"

    def _watch(self, phase: str, parts: Path, keys: Sequence[str]) -> Optional[bool]:
        """Count whole job files, restart a launcher that is gone. True once every job is
        done and the launcher has exited."""
        p = self.s[phase]
        p.setdefault("watch_started", self.env.now())
        done_files = [parts / n for n in p["jobs"] if whole_json(parts / n, keys)]
        if len(done_files) > p.get("done", 0):
            p["relaunches_since_progress"] = 0
        p["done"] = len(done_files)
        if done_files:
            p["last_done_at"] = max(f.stat().st_mtime for f in done_files)
        total = len(p["jobs"])
        run_dir = self.run_dir() if phase == "phase2" else None
        st = self.env.launcher_state(phase, run_dir)
        if st["alive"]:
            return False
        if p["done"] == total:
            return st["workers"] == 0 and st["partial"] == 0
        name = phase.replace("phase", "Phase ")
        if phase == "phase2" and (run_dir / "STOP_LAUNCHING").exists():
            raise StepHalt(f"budget stop: {p['done']}/{total} Phase 2 jobs done and the launcher has exited; "
                           "no verdict (it needs all 120). To continue, raise spend_stop_usd in the config and "
                           "delete STOP_LAUNCHING in the run directory")
        if st["workers"]:
            raise StepWait(f"{name} launcher is not running but worker processes are; not restarting it")
        if p.get("relaunches_since_progress", 0) >= self.cfg["max_relaunches"]:
            raise StepHalt(f"{name} launcher stopped {self.cfg['max_relaunches']} times without a job finishing")
        first = phase == "phase2" and not p.get("launches")
        p["relaunches_since_progress"] = p.get("relaunches_since_progress", 0) + (0 if first else 1)
        p["launches"] = p.get("launches", 0) + 1
        if first:
            p["started_at"] = self.env.now()  # the spend clock; saved before the launch
        self.save()
        self.env.start_launcher(phase, run_dir)
        if first:
            self.notify("Phase 2 started", f"{total} jobs, {self.cfg['max_procs']} processes, code "
                        f"{self.cfg['frozen_tag']} = {p.get('code_sha', '')[:7]}", "high", key="p2started")
        else:
            self.notify(f"{name} launcher restarted", f"it was not running with {p['done']}/{total} done "
                        f"(restart {p['relaunches_since_progress']} without progress)", "high")
        return False

    def step_phase1_running(self) -> Optional[str]:
        p = self.s["phase1"]
        if not p.get("jobs"):
            p["jobs"] = self.env.phase1_job_names()
        if not self._watch("phase1", self.env.phase1_parts(), ("condition", "train", "test")):
            return None
        self.notify("Phase 1 done", f"{p['done']}/{len(p['jobs'])} job files; verifying, committing and pushing",
                    "high", key="p1done")
        return "PHASE1_COMMIT"

    def step_phase1_commit(self) -> str:
        self.sync_clone()
        res = self.env.finish_day()
        if res["rc"] != 0:
            raise StepHalt("finish_day's checks failed (details in the server log); nothing was committed")
        paths = [x for x in res["add_paths"] if (self.clone / x).exists()]
        sha = self.commit_and_push(paths, res["message"], per_market=False)
        names = [f"{SWEEP_REL}/parts/{n}" for n in self.s["phase1"]["jobs"]]
        self.verify_pushed(sha, paths, {}, require=names)
        self.s["commits"]["phase1_results"] = sha
        self.notify("Phase 1 pushed", f"{len(names)} job files committed and verified on GitHub ({sha[:7]})",
                    key="p1pushed")
        return "PHASE1_VERDICT"

    def step_phase1_verdict(self) -> str:
        # The main tree moves once, to the frozen tag. (Moving it to the results commit
        # first and then to the tag would make git delete the now-tracked job files.)
        self.pin_frozen_tag()
        rel = f"{SWEEP_REL}/verdict_phase1.json"
        src = self.main / rel
        if not src.exists():
            if self.env.finish_phase1() != 0 or not src.exists():
                raise StepHalt("--finish-phase1 failed (details in the server log)")
        self.sync_clone()
        copy_identical(src, self.clone / rel)
        sha = self.commit_and_push([rel], f"Synthetic sweep phase 1 verdict ({CONFIG_HASH}): verdict_phase1.json "
                                   "from run_synthetic_market_experiment.py --finish-phase1", per_market=False)
        self.verify_pushed(sha, [rel], {rel: src}, require=[rel])
        self.s["commits"]["phase1_verdict"] = sha
        self.notify("Phase 1 verdict", read_overall(src), "high", key="p1verdict")
        return "PHASE2_DECISION"

    def step_phase2_decision(self) -> str:
        self.sync_clone()
        found = RULE_RE.findall((self.clone / PREREG_REL).read_text())
        if not found:
            raise StepWait(f"Phase 1 is finished and pushed. {PREREG_REL} states no rule for whether Phase 2 "
                           "runs given the Phase 1 verdict, so the autopilot is waiting. To decide, add the "
                           "line <!-- autopilot-phase2-rule: run-regardless --> or <!-- autopilot-phase2-rule: "
                           "do-not-run --> with a dated note and push it to main. Checked every few minutes.")
        if len(set(found)) != 1 or found[0] not in RULES:
            raise StepWait(f"{PREREG_REL} has more than one, or an unknown, autopilot-phase2-rule line; "
                           "keep exactly one: run-regardless or do-not-run")
        rule = found[0]
        g = self.git(self.clone)
        rule_commit = g("log", "-1", "--format=%H", "-Gautopilot-phase2-rule", "HEAD", "--", PREREG_REL)
        before = bool(rule_commit) and g.run("merge-base", "--is-ancestor", rule_commit,
                                             self.s["commits"]["phase1_verdict"], check=False).returncode == 0
        when = "before" if before else "AFTER"
        self.s["phase2"]["rule"] = rule
        if rule == "do-not-run":
            self.notify("Phase 2 not run", f"the preregistration's rule is do-not-run (committed {when} the "
                        "Phase 1 verdict)", "high", key="p2rule")
            return "FINAL_VERIFY"
        self.notify("Phase 2 will run", f"rule run-regardless (committed {when} the Phase 1 verdict); "
                    "checking its inputs", "high", key="p2rule")
        return "PHASE2_INPUTS"

    def step_phase2_inputs(self) -> str:
        p2 = self.s["phase2"]
        if not p2.get("code_sha"):
            self.pin_frozen_tag()
        self.verify_frozen_tag()
        inputs = self.phase2_inputs()
        missing = [name for name, path in inputs.items() if not path.exists()]
        if missing:
            raise StepWait("Phase 2 inputs missing on the server: " + ", ".join(missing)
                           + f" (copy them into {self.market().parent}; guide step 2)")
        digest = sha256_file(self.market())
        if digest != self.cfg["market_sha256"]:
            raise StepWait("the market file on the server does not have the expected SHA-256; copy it again")
        if not self.drive_signed_off(digest):
            raise StepWait(f"the drive check is not signed off for this market file: no {SIGNOFF_REL} naming "
                           "its SHA-256 with 'Signed off by', and no drive_signoff_sha256 in the config")
        if not p2.get("drive_check_passed"):
            report = self.market().parent / f"drive_check_autopilot_{digest[:12]}.txt"
            if self.env.drive_check(self.market(), report) != 0:
                raise StepHalt(f"drive_check.py did not pass (report on the server: {report}); Phase 2 not started")
            p2["drive_check_passed"] = True
        return "PHASE2_PREPARE"

    def copy_command(self) -> str:
        """One scp command, run on the Mac, that copies the private Phase 2 run directory."""
        run_dir = self.run_dir()
        try:
            remote = str(run_dir.relative_to(Path.home()))
        except ValueError:
            remote = str(run_dir)
        return f"scp -r {self.cfg['ssh_alias']}:{remote} {self.cfg['mac_data_dir']}"

    def drive_signed_off(self, digest: str) -> bool:
        """The owner's sign-off (preregistration Section 10, step 3): the committed record
        in the pinned code names this file's SHA-256 and a signer, or the config does."""
        if self.cfg.get("drive_signoff_sha256") == digest:
            return True
        record = self.main / SIGNOFF_REL
        try:
            text = record.read_text()
        except OSError:
            return False
        return re.search(rf"^- sha256: {digest}\s*$", text, re.M) is not None and "Signed off by" in text

    def step_phase2_prepare(self) -> str:
        run_dir = self.run_dir()
        manifest = run_dir / "manifest.json"
        if not manifest.exists():
            if self.env.prepare(self.market(), self.main / self.cfg["fill_plan"], run_dir) != 0 \
                    or not manifest.exists():
                raise StepHalt("--prepare failed (details in the server log)")
        if json.loads(manifest.read_text()).get("market_file_sha256") != self.cfg["market_sha256"]:
            raise StepHalt(f"{run_dir.name} was prepared from a different market file")
        return "PHASE2_RUNNING"

    def step_phase2_running(self) -> Optional[str]:
        p2 = self.s["phase2"]
        if not p2.get("launches"):
            self.verify_frozen_tag()  # refuse to start on a missing or moved tag
        if not p2.get("jobs"):
            p2["jobs"] = self.env.phase2_job_names(self.run_dir())
        if not self._watch("phase2", self.run_dir() / "parts", ("train", "test")):
            return None
        p2["ended_at"] = p2.get("ended_at") or self.env.now()
        self.notify("Phase 2 done", f"{p2['done']}/{len(p2['jobs'])} jobs; est. spend ${self.spend():.2f}; "
                    "computing the verdict", "high", key="p2done")
        return "PHASE2_PUBLISH"

    def step_phase2_publish(self) -> str:
        p2, run_dir = self.s["phase2"], self.run_dir()
        verdict = run_dir / "verdict.json"
        if not verdict.exists():
            if self.env.finish_phase2(run_dir) != 0 or not verdict.exists():
                raise StepHalt("--finish failed (details in the server log); nothing was published")
        self.sync_clone()
        out_rel = f"{PHASE2_PUBLIC_REL}/phase2_{self.cfg['market_sha256'][:12]}"
        out = self.clone / out_rel
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        parts = run_dir / "parts"
        hashes = {
            "note": "hashes and aggregates only; job files, chains, comparator and market data stay private",
            "market_file_sha256": self.cfg["market_sha256"],
            "manifest_sha256": sha256_file(manifest_path),
            "manifest": {k: manifest[k] for k in MANIFEST_HASH_KEYS if k in manifest},
            "job_files_sha256": {n: sha256_file(parts / n) for n in p2["jobs"]},
            "verdict_sha256": sha256_file(verdict),
            "code_commit": p2.get("code_sha"),
            "estimated_spend_usd": round(self.spend(), 2),
        }
        copy_identical(verdict, out / "verdict.json")
        hashes_path = out / "hashes.json"
        if not hashes_path.exists():
            write_json_atomic(hashes_path, hashes)
        elif json.loads(hashes_path.read_text()) != json.loads(json.dumps(hashes)):
            raise StepHalt("hashes.json in the publish clone differs from the one computed now")
        sha = self.commit_and_push([out_rel], f"Phase 2 verdict and hashes (market file "
                                   f"{self.cfg['market_sha256'][:12]}): aggregates only", per_market=True)
        self.verify_pushed(sha, [out_rel], {f"{out_rel}/verdict.json": verdict},
                           require=[f"{out_rel}/verdict.json", f"{out_rel}/hashes.json"])
        self.s["commits"]["phase2_verdict"] = sha
        self.notify("Phase 2 verdict", read_overall(verdict), "high", key="p2verdict")
        return "FINAL_VERIFY"

    def step_final_verify(self) -> str:
        g = self.git(self.clone)
        g("fetch", "-q", "origin")
        ref = f"origin/{self.branch}"
        bad = []
        for rel, digest in sorted(self.s["pushed"].items()):
            try:
                ok = sha256_bytes(g.blob(ref, rel)) == digest
            except CommandFailed:
                ok = False
            if not ok:
                bad.append(rel)
        if bad or not self.s["pushed"]:
            raise StepHalt(f"{len(bad)} pushed file(s) are missing or changed on GitHub, e.g. "
                           f"{bad[0] if bad else '(none recorded)'}")
        message = f"{len(self.s['pushed'])} pushed files verified on GitHub ({g('rev-parse', ref)[:7]})."
        if self.s["phase2"].get("launches"):
            message += (" The private Phase 2 job files exist only on the server. Before deleting it, copy them "
                        "on the Mac with: " + self.copy_command())
        self.notify("SAFE TO DELETE THE SERVER", message, "urgent", key="safe")
        return "DONE"


# ---- simulation: fake jobs, a local bare repository, a fake clock ------------------- #
SIM_P1 = [f"condition_{arm}_0_2026100{i}.json" for arm in ("profit", "learning_off") for i in range(1, 5)]
SIM_P2 = [f"{arm}_chain_{c:02d}.json" for arm in ("profit", "learning_off", "null_permuted") for c in range(2)]


class SimEnv(RealEnv):
    """RealEnv with every project script, process and network call replaced by a fake
    inside the simulation folder. Git is real, against a local bare repository."""

    simulated = True

    def __init__(self, cfg: dict, world: Path) -> None:
        super().__init__(cfg)
        self.world = world
        self.sim_path = world / "sim.json"

    def _w(self) -> dict:
        return json.loads(self.sim_path.read_text())

    def _save(self, w: dict) -> None:
        write_json_atomic(self.sim_path, w)

    def now(self) -> float:
        return self._w()["now"]

    def log(self, message: str) -> None:
        with open(self.world / "autopilot.log", "a") as fh:
            fh.write(f"{utc(self.now())} {message}\n")

    def send(self, title: str, message: str, priority: str) -> bool:
        with open(self.world / "notifications.txt", "a") as fh:
            fh.write(f"{utc(self.now())} [{priority}] {title}: {message}\n")
        return True

    def phase1_job_names(self) -> List[str]:
        return list(SIM_P1)

    def phase2_job_names(self, run_dir: Path) -> List[str]:
        return list(SIM_P2)

    def launcher_state(self, phase: str, run_dir: Optional[Path] = None) -> dict:
        return {"alive": self._w()[phase]["running"], "workers": 0, "partial": 0}

    def start_launcher(self, phase: str, run_dir: Optional[Path] = None) -> None:
        w = self._w()
        w[phase]["running"] = True
        self._save(w)

    def launcher_failures(self, phase: str, run_dir: Optional[Path] = None) -> List[str]:
        return list(self._w()[phase].get("failures", []))

    def oom_kills(self, since: float) -> int:
        return 0

    def finish_day(self) -> dict:
        src, dst = self.main / SWEEP_REL, self.clone / SWEEP_REL
        rc = 0
        for f in sorted(src.glob("parts/*.json")) + sorted(src.glob("logs/*.log")):
            target = dst / f.relative_to(src)
            if target.exists() and sha256_file(target) != sha256_file(f):
                rc = 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
        return {"rc": rc, "add_paths": [SWEEP_REL], "message": f"Synthetic sweep phase 1 results ({CONFIG_HASH}): "
                f"{len(SIM_P1)} job files, verified against the server's SHA-256 [SIMULATED]"}

    def finish_phase1(self) -> int:
        write_json_atomic(self.main / SWEEP_REL / "verdict_phase1.json",
                          {"evaluation": "SIMULATED", "readings": {"overall": "SIMULATED phase 1 verdict"}})
        return 0

    def drive_check(self, market: Path, report: Path) -> int:
        report.write_text("SIMULATED drive check: ALL CHECKS PASSED\n")
        return 0

    def prepare(self, market: Path, fill_plan: Path, run_dir: Path) -> int:
        write_json_atomic(run_dir / "manifest.json", {"market_file_sha256": sha256_file(market),
                                                      "chains_sha256": "0" * 64, "locked_config_hash": CONFIG_HASH})
        return 0

    def finish_phase2(self, run_dir: Path) -> int:
        write_json_atomic(run_dir / "verdict.json", {
            "prestated": "SIMULATED", "success": False, "gate_passes": False, "n_test_markets": 6,
            "readings": {"overall": "SIMULATED: does not pass"}})
        return 0

    # the fake launchers: called by the simulation loop between ticks, never by the autopilot
    def advance(self, hours: float) -> None:
        w = self._w()
        w["now"] += hours * 3600
        for phase, names, parts in (("phase1", SIM_P1, self.main / SWEEP_REL / "parts"),
                                    ("phase2", SIM_P2, self.cfg["main_tree"] / "data/polymarket" /
                                     f"phase2_{self.cfg['market_sha256'][:12]}" / "parts")):
            ph = w[phase]
            if not ph["running"]:
                continue
            ph["ticks"] = ph.get("ticks", 0) + 1
            if phase == "phase1" and ph["ticks"] == 2 and not ph.get("crashed"):
                ph["crashed"], ph["running"] = True, False  # a launcher that dies once
                ph["failures"] = ["[launcher] FAILED condition:profit:0:20261003 (exit -9)"]
                continue
            todo = [n for n in names if not (parts / n).exists()]
            stop = (parts.parent / "STOP_LAUNCHING").exists()
            for n in ([] if stop else todo[:2]):
                parts.mkdir(parents=True, exist_ok=True)
                write_json_atomic(parts / n, {"condition": n, "train": [{}] * 3, "test": [{}] * 3})
            if stop or len(todo) <= 2:
                ph["running"] = False
        self._save(w)


def _sim_git(*args: str, cwd: Optional[Path] = None) -> str:
    r = subprocess.run(["git", *(["-C", str(cwd)] if cwd else []), "-c", "user.name=Simulation",
                        "-c", "user.email=sim@example.invalid", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"simulation setup: git {args[0]} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def make_world(world: Path, rule: str) -> dict:
    """A fake GitHub (bare repo), a fake server main tree with 2 of 8 phase 1 jobs done,
    fake Phase 2 inputs, and a config pointing only inside ``world``."""
    bare, seed, main = world / "github.git", world / "seed", world / "main"
    _sim_git("init", "-q", "--bare", str(bare))
    _sim_git("symbolic-ref", "HEAD", "refs/heads/main", cwd=bare)
    _sim_git("init", "-q", str(seed))
    _sim_git("checkout", "-q", "-b", "main", cwd=seed)
    prereg = "# Phase 2 preregistration (SIMULATED)\n"
    if rule in RULES:
        prereg += f"\n<!-- autopilot-phase2-rule: {rule} -->\n"
    (seed / "docs/design").mkdir(parents=True)
    (seed / PREREG_REL).write_text(prereg)
    (seed / ".gitignore").write_text("/data/\n")
    _sim_git("add", "-A", cwd=seed)
    _sim_git("commit", "-q", "-m", "simulated repository", cwd=seed)
    _sim_git("tag", "-a", "phase2-frozen", "-m", "simulated frozen Phase 2 code", cwd=seed)
    _sim_git("push", "-q", str(bare), "main", "refs/tags/phase2-frozen", cwd=seed)
    _sim_git("clone", "-q", str(bare), str(main))
    parts = main / SWEEP_REL / "parts"
    parts.mkdir(parents=True)
    (main / SWEEP_REL / "logs").mkdir()
    (main / SWEEP_REL / "logs" / "condition_profit_0_20261001.log").write_text("[progress] fake\n")
    for n in SIM_P1[:2]:
        write_json_atomic(parts / n, {"condition": n, "train": [{}] * 3, "test": [{}] * 3})
    data = main / "data" / "polymarket"
    data.mkdir(parents=True)
    market = data / "markets_f3d41123e20e_cutoff_2026-03-01.json"
    market.write_text('{"format": "SIMULATED market file"}\n')
    for name in ("fill_plan_f3d41123e20e.json", "frozen_market_list.json", "frozen_market_list.json.sha256",
                 "histories_f3d41123e20e.jsonl"):
        (data / name).write_text("SIMULATED\n")
    write_json_atomic(world / "sim.json", {"now": 1_800_000_000.0, "phase1": {"running": True},
                                           "phase2": {"running": False}})
    return world_config(world)


def world_config(world: Path, overrides: Optional[dict] = None) -> dict:
    """The simulation's config: every path inside ``world``, the fake GitHub as push URL."""
    digest = sha256_file(world / "main/data/polymarket/markets_f3d41123e20e_cutoff_2026-03-01.json")
    return {**DEFAULTS, "ntfy_topic": "simulated-topic-never-used-0123456789",
            "git_user_name": "Simulation", "git_user_email": "sim@example.invalid",
            "main_tree": world / "main", "state_dir": world / "state", "publish_clone": world / "publish",
            "push_url": str(world / "github.git"), "market_sha256": digest, "drive_signoff_sha256": digest,
            **(overrides or {})}


def simulate(world: Path, rule: str = "later", max_ticks: int = 200, hours_per_tick: float = 1.0,
             echo=print, overrides: Optional[dict] = None, stop_at: Optional[str] = None) -> dict:
    """Run the whole machine on fakes. A fresh Autopilot is built from the state file at
    every tick, so every tick is also a restart. Returns the final state."""
    world = world.resolve()
    if world.exists() and any(world.iterdir()):
        raise SystemExit(f"{world} is not empty; the simulation needs a new folder")
    world.mkdir(parents=True, exist_ok=True)
    make_world(world, rule)
    cfg = world_config(world, overrides)
    added = False
    state: dict = {}
    for _ in range(max_ticks):
        ap = Autopilot(cfg, SimEnv(cfg, world))
        ap.tick()
        state = ap.s
        if state["state"] == "DONE" or state["halt"] or state["state"] == stop_at:
            break
        if rule == "later" and state["state"] == "PHASE2_DECISION" and state["wait"] and not added:
            seed = world / "seed"  # the owner records the rule after being notified
            _sim_git("pull", "-q", str(world / "github.git"), "main", cwd=seed)
            with open(seed / PREREG_REL, "a") as fh:
                fh.write("\n<!-- autopilot-phase2-rule: run-regardless -->\n")
            _sim_git("commit", "-q", "-am", "record the Phase 2 rule", cwd=seed)
            _sim_git("push", "-q", str(world / "github.git"), "main", cwd=seed)
            added = True
        if rule == "none" and state["wait"] and state["state"] == "PHASE2_DECISION":
            break
        SimEnv(cfg, world).advance(hours_per_tick)
    echo(f"simulation folder: {world}")
    echo(f"final state: {state.get('state')}" + (f"; HALTED: {state['halt']['reason']}" if state.get("halt") else "")
         + (f"; WAITING: {state['wait'][:100]}" if state.get("wait") else ""))
    echo("notifications:")
    echo((world / "notifications.txt").read_text() if (world / "notifications.txt").exists() else "(none)")
    files = _sim_git("ls-tree", "-r", "--name-only", "main", cwd=world / "github.git").splitlines()
    echo(f"files on the fake GitHub: {len(files)}; under data/: {sum(f.startswith('data/') for f in files)}")
    return state


# ---- command line --------------------------------------------------------------------- #
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", nargs="?", choices=("run", "status", "resume", "notify-test"))
    p.add_argument("--config", type=Path, default=Path("~/.config/flyshi-autopilot/config.json"))
    p.add_argument("--once", action="store_true", help="run: one tick, then exit.")
    p.add_argument("--simulate", action="store_true", help="Run everything on fakes in a new temporary folder.")
    p.add_argument("--sim-rule", default="later", choices=("later", "run-regardless", "do-not-run", "none"),
                   help="Simulation: the prereg rule. 'later' = none at first, added after the notification.")
    p.add_argument("--sim-dir", type=Path, help="Simulation folder (new or empty; default: a temporary one).")
    args = p.parse_args(argv)

    if args.simulate:
        world = args.sim_dir or Path(tempfile.mkdtemp(prefix="flyshi-autopilot-sim-"))
        state = simulate(world, args.sim_rule)
        expected = "PHASE2_DECISION" if args.sim_rule == "none" else "DONE"
        ok = state.get("state") == expected and not state.get("halt")
        print("SIMULATION OK" if ok else "SIMULATION FAILED")
        return 0 if ok else 1
    if not args.command:
        p.error("give a command (run, status, resume, notify-test) or --simulate")

    cfg = load_config(args.config)
    env = RealEnv(cfg)
    cfg["state_dir"].mkdir(parents=True, exist_ok=True)
    if args.command == "notify-test":
        ok = env.send("Test", "flyshi autopilot: notifications work", "default")
        print("sent" if ok else "FAILED")
        return 0 if ok else 1
    if args.command == "status":
        print(Autopilot(cfg, env).status_line())
        return 0
    if args.command == "resume":
        import fcntl
        with open(cfg["state_dir"] / "autopilot.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)  # waits for the running tick to end
            ap = Autopilot(cfg, env)
            ap.s["halt"], ap.s["wait"], ap.s["errors"] = None, None, 0
            for phase in ("phase1", "phase2"):
                ap.s[phase]["relaunches_since_progress"] = 0
            ap.save()
        print(f"resumed: {ap.status_line()}")
        return 0

    import fcntl
    lock = open(cfg["state_dir"] / "autopilot.lock", "w")
    env.log(f"autopilot starting (pid {os.getpid()})")
    while True:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            Autopilot(load_config(args.config), env).tick()  # the config is re-read every tick
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
        if args.once:
            return 0
        time.sleep(cfg["poll_seconds"])


if __name__ == "__main__":
    sys.exit(main())
