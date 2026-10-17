#!/usr/bin/env python3
"""Run Phase 2: the synthetic sweep's circuit on real Polymarket markets (Design A).

Pre-stated in docs/design/phase2-preregistration.md (2026-10-16). Steps:

  --prepare      chains (40 x 70 training + 180 test, from the fill plan's hash
                 order) and the frozen comparator (training markets only), with a
                 manifest of SHA-256s. Written BEFORE any job runs.   [no simulation]
  --drive-check  real markets' encoder drive against the validated synthetic range;
                 the owner signs off before any run.                 [no simulation]
  --dry-run      the plan.                                            [no simulation]
  --list-jobs    120 jobs: 40 chains x (profit, learning_off, null_permuted).
  --job ID       one (chain, arm) job: 500 runs. IMPORTS BRIAN2 AND SIMULATES.
  --finish       the pre-stated verdict from the 120 job files.       [no simulation]

Everything is written under --run-dir, inside the git-ignored data/ directory: job
files hold outcomes and prices, and the chains hold market IDs (condition 6). A job
refuses to run unless the manifest's hashes match the market file, chains and
comparator on disk, so the comparator is frozen before any test market is scored.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))  # sibling runners; none imports Brian2 at module level

from flyshi_research.evaluation import isotonic_comparator as ic  # noqa: E402
from flyshi_research.learning import real_market as rm  # noqa: E402
from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from run_left_only_pool_diagnostic import IDS_PATH, kc_side_map  # noqa: E402
from run_synthetic_market_experiment import (  # noqa: E402
    START_TAG,
    Paths,
    _write_json,
    build_sweep_simulator,
    progress_printer,
    read_output,
)

DATA_DIR = REPO / "data" / "polymarket"
MANIFEST = "manifest.json"
CHAINS = "chains.json"
COMPARATOR = "comparator.json"


def default_run_dir(market_file: Path) -> Path:
    return DATA_DIR / f"phase2_{rm.file_sha256(market_file)[:12]}"


def prepare(market_file: Path, fill_plan: Path, run_dir: Path, now: datetime) -> dict:
    """Chains and the frozen comparator, plus the manifest. Refuses to overwrite."""
    run_dir = Path(run_dir)
    if (run_dir / MANIFEST).exists():
        raise SystemExit(f"{run_dir / MANIFEST} exists: a prepared run is never overwritten")
    train, test, header = rm.load_market_file(market_file)
    plan = json.loads(Path(fill_plan).read_text())
    if plan.get("frozen_sha256") != header["frozen_list_sha256"]:
        raise SystemExit("the fill plan and the market file come from different frozen lists")
    chains = rm.chains_from_market_file(plan, train, test)
    ids = sorted(train)
    comparator = ic.fit_comparator(ids, [train[i].market.quote for i in ids],
                                   [train[i].market.outcome for i in ids])
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / CHAINS, chains)
    _write_json(run_dir / COMPARATOR, {**comparator.to_dict(), "training_ids": ids})
    manifest = {
        "prepared_utc": now.isoformat(), "prestated": "docs/design/phase2-preregistration.md",
        "market_file": str(market_file), "market_file_sha256": rm.file_sha256(market_file),
        "fill_plan_sha256": rm.file_sha256(fill_plan), "frozen_sha256": header["frozen_list_sha256"],
        "chains_sha256": rm.file_sha256(run_dir / CHAINS),
        "comparator_sha256": rm.file_sha256(run_dir / COMPARATOR),
        "locked_config_hash": rm.locked_config().config_hash(),
        "design": {"n_chains": rm.N_CHAINS, "train_per_chain": rm.TRAIN_PER_CHAIN,
                   "test_per_chain": rm.TEST_PER_CHAIN, "arms": list(rm.ARMS),
                   "simulation_seed_base": rm.SIMULATION_SEED_BASE,
                   "null_permutation_seed": rm.NULL_PERMUTATION_SEED, "bootstrap_seed": rm.BOOTSTRAP_SEED},
    }
    _write_json(run_dir / MANIFEST, manifest)
    return {"run_dir": str(run_dir), "chain_counts": chains["counts"], "comparator": ic.describe(comparator),
            **{k: manifest[k] for k in ("chains_sha256", "comparator_sha256", "locked_config_hash")}}


def load_prepared(run_dir: Path) -> tuple:
    """(manifest, chains, comparator, training IDs, train, test); refuses on any hash mismatch."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / MANIFEST).read_text())
    market_file = Path(manifest["market_file"])
    for key, path in (("market_file_sha256", market_file), ("chains_sha256", run_dir / CHAINS),
                      ("comparator_sha256", run_dir / COMPARATOR)):
        if rm.file_sha256(path) != manifest[key]:
            raise SystemExit(f"{path} does not match the manifest ({key}); refusing")
    if manifest["locked_config_hash"] != rm.locked_config().config_hash():
        raise SystemExit("the locked configuration changed since preparation; refusing")
    raw = json.loads((run_dir / COMPARATOR).read_text())
    training_ids = raw.pop("training_ids")
    comparator = ic.FrozenComparator.from_dict(raw)
    train, test, _ = rm.load_market_file(market_file)
    return manifest, json.loads((run_dir / CHAINS).read_text()), comparator, training_ids, train, test


def finish(run_dir: Path) -> dict:
    _, chains, comparator, training_ids, train, test = load_prepared(run_dir)
    paths = Paths(Path(run_dir))
    outputs = {}
    for job in rm.plan_jobs(chains["n_chains"]):
        value = read_output(paths.output(job))
        if value is None:
            raise SystemExit(f"missing job output {job.id}")
        outputs[(job.chain, job.condition)] = value
    verdict = rm.evaluate(outputs, chains, comparator, {i: m.final_volume for i, m in test.items()},
                          training_ids)
    _write_json(Path(run_dir) / "verdict.json", verdict)
    return verdict


def plan_lines(cfg: sm.SyntheticConfig) -> list:
    jobs = rm.plan_jobs()
    return [
        "Phase 2 real-market experiment: PLAN (dry run; nothing is simulated)",
        f"  locked configuration: the synthetic sweep's, hash {cfg.config_hash()} (mitigation {cfg.mitigation};"
        f" encoder {sm.option_b_variant(cfg)} Option B, left-only pools)",
        f"  inputs held at the midpoint: signal 0.5, liquidity 0.5 (90 Hz in both framings)",
        f"  chains: {rm.N_CHAINS} x ({rm.TRAIN_PER_CHAIN} training, then {rm.TEST_PER_CHAIN} test)",
        f"  arms: {', '.join(rm.ARMS)}",
        f"  jobs: {len(jobs)}; runs: {sum(j.n_runs for j in jobs)}",
        "  comparator: isotonic price, pseudo-count 20, 5-fold raw-vs-calibrated guard, training only",
    ]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--market-file", type=Path, help="The build step's output (--prepare, --drive-check).")
    p.add_argument("--fill-plan", type=Path, help="The history step's fill plan (--prepare).")
    p.add_argument("--run-dir", type=Path, help="Default: data/polymarket/phase2_<market file sha12>.")
    p.add_argument("--ids", type=Path, default=IDS_PATH)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--drive-check", action="store_true")
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--list-jobs", action="store_true")
    group.add_argument("--job")
    group.add_argument("--finish", action="store_true")
    return p


def main(argv=None, now=None) -> int:
    args = parser().parse_args(argv)
    now = now or datetime.now(timezone.utc)
    cfg = rm.locked_config()
    if args.dry_run:
        print("\n".join(plan_lines(cfg)))
        return 0
    if args.drive_check:
        if not args.market_file:
            raise SystemExit("--drive-check needs --market-file")
        train, test, _ = rm.load_market_file(args.market_file)
        report = rm.drive_check([m.market for m in train.values()], [m.market for m in test.values()], cfg)
        print(json.dumps(report, indent=1))
        return 0
    if args.prepare:
        if not (args.market_file and args.fill_plan):
            raise SystemExit("--prepare needs --market-file and --fill-plan")
        run_dir = args.run_dir or default_run_dir(args.market_file)
        print(json.dumps(prepare(args.market_file, args.fill_plan, run_dir, now), indent=1))
        return 0
    if not args.run_dir:
        raise SystemExit("--run-dir is required (the directory --prepare wrote)")
    paths = Paths(args.run_dir)
    if args.list_jobs:
        for job in rm.plan_jobs():
            print(f"{job.id:28s} {job.n_runs:4d} runs  {'done' if paths.done(job) else 'todo'}")
        return 0
    if args.finish:
        print(json.dumps(finish(args.run_dir), indent=1))
        return 0
    job = next((j for j in rm.plan_jobs() if j.id == args.job), None)
    if job is None:
        raise SystemExit("--job with a valid job ID is required; use --list-jobs")
    if paths.done(job):
        print(f"{job.id}: already done")
        return 0
    _, chains, _, _, train, test = load_prepared(args.run_dir)  # refuses on any hash mismatch
    tr, te = rm.chain_markets(chains, job.chain, train, test)
    # Lazy import: this is the only branch that loads Brian2 and the connectome.
    print(f"{START_TAG} {job.id} t={time.time():.2f} pid={os.getpid()}", flush=True)
    kc_sides = kc_side_map(args.ids)
    sim = build_sweep_simulator(progress_printer(job.id, job.n_runs))
    sm.setup_encoder(sim, cfg, kc_sides)  # left-only guard before any presentation
    output = rm.run_chain(sim, cfg, job.chain, tr, te, job.condition, kc_sides=kc_sides)
    _write_json(paths.output(job), output)
    print(f"{job.id}: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
