#!/usr/bin/env python3
"""Phase 2 drive check on the built market file (phase2-preregistration.md, Section 10, step 3).

No network, no simulation, nothing written. Every check prints one PASS/FAIL line
with counts and dates only: never an outcome, a price, a feature value or a market ID.

  file        SHA-256 (hash only), format, header, the frozen list's hash
  structure   every record's keys and types; signal and liquidity at the midpoint
  counts      train/test sizes against the pool targets; the build's own counts
  ids         unique market and event IDs; no market in both splits
  times       the split rule and ordering; closed after the decision time; the price
              point strictly before the decision time and at most 24 h old
  frozen      decision time redrawn from its seed; dates, volume and time to
              resolution as in the frozen list
  fill plan   every built market is usable in its pool; the chains assemble
  look-ahead  price, recent change and price time re-derived from the stored
              histories using only points strictly before the decision time
  drive       the preregistered total-drive check (``real_market.drive_check``):
              encoder drive in kHz against the synthetic sweep's validated range.
              Drive is computed from the price and recent-change features, so its
              figures are aggregates of them; --no-drive skips this section.

Exit status 0 only if every check passes. The drive flags do not set it: the owner
signs off on the drive report before any job runs.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

from flyshi_research.learning import real_market as rm
from flyshi_research.realdata import polymarket as pm

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "data" / "polymarket"

TOP_KEYS = {"format", "venue", "frozen_list_sha256", "split", "counts", "train", "test"}
RECORD_KEYS = {"latent_probability", "quote", "outcome", "signal", "recent_change", "time_to_resolution",
               "liquidity", "sequence", "meta"}
META_KEYS = {"market_id", "event_id", "decision_time", "price_time_unix", "closed_time", "final_volume"}


class Report:
    def __init__(self) -> None:
        self.failed: list = []

    def check(self, name: str, ok: bool, detail: object = "") -> bool:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail != "" else ""), flush=True)
        if not ok:
            self.failed.append(name)
        return ok


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _time(value):
    try:
        t = pm.parse_time(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return t if t is not None and t.utcoffset() is not None else None


def record_problems(r) -> list:
    """Names of what is wrong with one record, never its values."""
    if not isinstance(r, dict) or set(r) != RECORD_KEYS:
        return ["record_keys"]
    meta = r["meta"]
    if not isinstance(meta, dict) or set(meta) != META_KEYS:
        return ["meta_keys"]
    bad = []
    if r["latent_probability"] is not None:
        bad.append("latent_probability_not_null")
    if not (_finite(r["quote"]) and 0.0 <= r["quote"] <= 1.0):
        bad.append("quote_not_in_0_1")
    if not (type(r["outcome"]) is int and r["outcome"] in (0, 1)):
        bad.append("outcome_not_0_or_1")
    if not (_finite(r["recent_change"]) and -1.0 <= r["recent_change"] <= 1.0):
        bad.append("recent_change_not_in_-1_1")
    if not (_finite(r["time_to_resolution"]) and r["time_to_resolution"] > 0):
        bad.append("time_to_resolution_not_positive")
    if r["signal"] != pm.SIGNAL_MIDPOINT:
        bad.append("signal_not_midpoint")
    if r["liquidity"] != pm.LIQUIDITY_MIDPOINT:
        bad.append("liquidity_not_midpoint")
    if type(r["sequence"]) is not int:
        bad.append("sequence_not_int")
    if not (isinstance(meta["market_id"], str) and meta["market_id"]):
        bad.append("market_id")
    if not (isinstance(meta["event_id"], str) and meta["event_id"]):
        bad.append("event_id")
    if _time(meta["decision_time"]) is None:
        bad.append("decision_time_unparseable")
    if _time(meta["closed_time"]) is None:
        bad.append("closed_time_unparseable")
    if type(meta["price_time_unix"]) is not int:
        bad.append("price_time_unix_not_int")
    if not (_finite(meta["final_volume"]) and meta["final_volume"] >= pm.MIN_FINAL_VOLUME_USDC):
        bad.append("final_volume_below_minimum")
    return bad


def check_file(rep: Report, payload, path: Path, frozen_digest: str) -> bool:
    if not rep.check("top-level keys", isinstance(payload, dict) and set(payload) == TOP_KEYS,
                     "" if isinstance(payload, dict) and set(payload) == TOP_KEYS else "unexpected keys"):
        return False
    rep.check("format", payload["format"] == pm.MARKET_FILE_FORMAT)
    rep.check("venue", payload["venue"] == "polymarket")
    rep.check("frozen list hash in header = frozen list on disk", payload["frozen_list_sha256"] == frozen_digest,
              frozen_digest[:12])
    rep.check("file name names the frozen list and the cutoff",
              path.name == f"markets_{frozen_digest[:12]}_cutoff_{pm.SPLIT_CUTOFF:%Y-%m-%d}.json")
    split = {"cutoff": pm.SPLIT_CUTOFF.isoformat(), "gap_days": pm.SPLIT_GAP.total_seconds() / 86400}
    rep.check("split header = pre-stated cutoff and gap", payload["split"] == split, split)
    ok = isinstance(payload["train"], list) and isinstance(payload["test"], list)
    return rep.check("train and test are lists", ok)


def check_structure(rep: Report, payload) -> bool:
    problems = Counter()
    for split in ("train", "test"):
        for i, r in enumerate(payload[split]):
            problems.update(f"{split}:{p}" for p in record_problems(r))
            if isinstance(r, dict) and r.get("sequence") != i:
                problems[f"{split}:sequence_not_index"] += 1
    return rep.check("record structure and types", not problems, dict(problems) or "all records")


def check_counts(rep: Report, payload) -> None:
    n = {s: len(payload[s]) for s in ("train", "test")}
    targets = pm.pool_targets()
    rep.check("train count = pool target", n["train"] == targets["train"], f"{n['train']:,} (target {targets['train']:,})")
    rep.check("test count = pool target", n["test"] == targets["test"], f"{n['test']:,} (target {targets['test']:,})")
    need = {"train": rm.N_CHAINS * rm.TRAIN_PER_CHAIN, "test": rm.N_CHAINS * rm.TEST_PER_CHAIN}
    rep.check("enough for 40 chains", all(n[s] >= need[s] for s in n), f"need {need}")
    c = payload["counts"]
    print(f"INFO  build counts in header: {json.dumps(c, sort_keys=True)}")
    rep.check("header counts = record counts", c.get("train") == n["train"] and c.get("test") == n["test"])
    rep.check("closed_before_decision = 0", c.get("closed_before_decision") == 0)
    excluded = sum(c.get(k, 0) for k in ("closed_before_decision", "no_history_fetched",
                                         "no_price_before_decision", "stale_price", "no_price_before_window"))
    rep.check("header: frozen - exclusions = built", c.get("frozen", 0) - excluded == c.get("built"))
    rep.check("header: built = train + test + excluded by split",
              c.get("built") == n["train"] + n["test"] + c.get("straddling_excluded", 0)
              + c.get("after_test_window_excluded", 0))
    rep.check("built = 11,500 = train + test", c.get("built") == n["train"] + n["test"] == 11_500)


def check_ids(rep: Report, payload) -> None:
    ids = {s: [r["meta"]["market_id"] for r in payload[s]] for s in ("train", "test")}
    rep.check("market IDs unique within each split", all(len(set(v)) == len(v) for v in ids.values()))
    rep.check("no market in both splits", not set(ids["train"]) & set(ids["test"]))
    events = [r["meta"]["event_id"] for s in ("train", "test") for r in payload[s]]
    rep.check("one market per event", len(set(events)) == len(events),
              f"{len(events) - len(set(events))} repeated")


def _span(times) -> str:
    if not times:
        return "none"
    return f"{min(times):%Y-%m-%d} .. {max(times):%Y-%m-%d}"


def check_times(rep: Report, payload) -> None:
    cutoff, gap, test_end = pm.SPLIT_CUTOFF, pm.SPLIT_GAP, pm.TEST_DECISION_END
    stale = pm.MAX_PRICE_STALENESS.total_seconds()
    for split in ("train", "test"):
        recs = payload[split]
        td = [_time(r["meta"]["decision_time"]) for r in recs]
        closed = [_time(r["meta"]["closed_time"]) for r in recs]
        ids = [r["meta"]["market_id"] for r in recs]
        price_t = [r["meta"]["price_time_unix"] for r in recs]
        print(f"INFO  {split}: decision times {_span(td)}; close times {_span(closed)}")
        if split == "train":
            rep.check("train: resolved before the cutoff", sum(c >= cutoff for c in closed) == 0,
                      f"{sum(c >= cutoff for c in closed)} violations")
            keys = list(zip(closed, ids))
        else:
            out = sum(not (cutoff + gap <= t < test_end) for t in td)
            rep.check("test: decided in [cutoff + 7 d, 2026-09-01)", out == 0, f"{out} violations")
            keys = list(zip(td, ids))
        rep.check(f"{split}: in pre-stated order ({'close' if split == 'train' else 'decision'} time, ID)",
                  keys == sorted(keys))
        n = sum(c <= t for c, t in zip(closed, td))
        rep.check(f"{split}: closed after the decision time", n == 0, f"{n} violations")
        n = sum(p >= t.timestamp() for p, t in zip(price_t, td))
        rep.check(f"{split}: price point strictly before the decision time", n == 0, f"{n} violations")
        n = sum(t.timestamp() - p > stale for p, t in zip(price_t, td))
        rep.check(f"{split}: price point at most 24 h before the decision time", n == 0, f"{n} violations")


def check_frozen(rep: Report, payload, frozen: dict) -> None:
    bad = Counter()
    for split in ("train", "test"):
        for r in payload[split]:
            meta = r["meta"]
            m = frozen.get(meta["market_id"])
            if m is None:
                bad["not_in_frozen_list"] += 1
                continue
            start, end, td = pm.parse_time(m.start), pm.parse_time(m.end), _time(meta["decision_time"])
            if pm.decision_time(m.market_id, start, end) != td or m.decision_time != meta["decision_time"]:
                bad["decision_time_not_the_seeded_draw"] += 1
            if not (start + pm.DECISION_MARGIN <= td <= end - pm.DECISION_MARGIN):
                bad["decision_time_outside_scheduled_window"] += 1
            if m.closed_time != meta["closed_time"]:
                bad["closed_time"] += 1
            if m.event_id != meta["event_id"]:
                bad["event_id"] += 1
            if m.final_volume != meta["final_volume"]:
                bad["final_volume"] += 1
            if (end - td).total_seconds() / 86400.0 != r["time_to_resolution"]:
                bad["time_to_resolution"] += 1
    rep.check("records agree with the frozen list", not bad, dict(bad) or "decision times, dates, volume, time to resolution")


def check_fill_plan(rep: Report, payload, plan: dict, frozen_digest: str, path: Path) -> None:
    rep.check("fill plan is for this frozen list", plan.get("frozen_sha256") == frozen_digest)
    for split in ("train", "test"):
        usable = set(map(str, plan["pools"][split]["usable_ids"]))
        n = sum(r["meta"]["market_id"] not in usable for r in payload[split])
        rep.check(f"{split}: every market usable in the fill plan's {split} pool", n == 0, f"{n} not usable")
    train, test, _ = rm.load_market_file(path)
    try:
        chains = rm.chains_from_market_file(plan, train, test)
    except ValueError as why:
        rep.check("chains assemble (not written)", False, str(why))
        return
    rep.check("chains assemble (not written)", True, json.dumps(chains["counts"], sort_keys=True))


def check_look_ahead(rep: Report, payload, histories: dict, frozen: dict) -> None:
    """Re-derive each record's price, price time and recent change from its stored
    history, independently of ``decision_features``, using only points strictly before
    the decision time. Compares for equality; prints counts only."""
    window = pm.RECENT_CHANGE_WINDOW.total_seconds()
    bad, later_markets, later_points = Counter(), 0, 0
    for split in ("train", "test"):
        for r in payload[split]:
            meta = r["meta"]
            hist = histories.get(meta["market_id"])
            if hist is None:
                bad["no_stored_history"] += 1
                continue
            limit = _time(meta["decision_time"]).timestamp()
            past = sorted((t, p) for t, p in hist if t < limit)
            n_later = sum(1 for t, _ in hist if t >= limit)
            later_markets += n_later > 0
            later_points += n_later
            if not past:
                bad["no_point_before_decision"] += 1
                continue
            t_last, price = past[-1]
            earlier = [pt for pt in past if pt[0] <= limit - window]
            if t_last != meta["price_time_unix"]:
                bad["price_time"] += 1
            if price != r["quote"]:
                bad["price"] += 1
            if not earlier or max(-1.0, min(1.0, price - earlier[-1][1])) != r["recent_change"]:
                bad["recent_change"] += 1
            m = frozen.get(meta["market_id"])
            if m is None:
                bad["not_in_frozen_list"] += 1
                continue
            f, why = pm.decision_features(hist, _time(meta["decision_time"]), pm.parse_time(m.end))
            if f is None or (f.price, f.recent_change, f.time_to_resolution, f.price_time) != (
                    r["quote"], r["recent_change"], r["time_to_resolution"], meta["price_time_unix"]):
                bad["differs_from_decision_features"] += 1
    print(f"INFO  stored histories with points at or after the decision time (dropped by the guard):"
          f" {later_markets:,} markets, {later_points:,} points")
    rep.check("look-ahead: features come only from points before the decision time", not bad,
              dict(bad) or "price, price time and recent change re-derived for every market")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--market-file", type=Path, required=True, help="The build step's output.")
    p.add_argument("--data-dir", type=Path, default=DATA_DIR,
                   help="Holds the frozen list, the fill plan and the histories (default %(default)s).")
    p.add_argument("--no-drive", action="store_true", help="Skip the drive section (structure checks only).")
    args = p.parse_args(argv)
    path = args.market_file
    digest = rm.file_sha256(path)
    print(f"market file {path}")
    print(f"sha256 {digest}", flush=True)

    rep = Report()
    frozen_list, frozen_digest = pm.load_frozen(args.data_dir / "frozen_market_list.json")  # verifies its hash
    frozen = {m.market_id: m for m in frozen_list}
    try:
        payload = json.loads(path.read_bytes())
    except ValueError:
        rep.check("file parses as JSON", False)
        return 1
    if not (check_file(rep, payload, path, frozen_digest) and check_structure(rep, payload)):
        print(f"STOPPED: the later checks need valid records ({len(rep.failed)} failed)")
        return 1
    check_counts(rep, payload)
    check_ids(rep, payload)
    check_times(rep, payload)
    check_frozen(rep, payload, frozen)
    check_fill_plan(rep, payload, json.loads((args.data_dir / f"fill_plan_{frozen_digest[:12]}.json").read_text()),
                    frozen_digest, path)
    histories = {e["market_id"]: [tuple(x) for x in e["history"]]
                 for e in pm._read_progress(args.data_dir / f"histories_{frozen_digest[:12]}.jsonl")}
    check_look_ahead(rep, payload, histories, frozen)

    if not args.no_drive:
        print("\nDRIVE (preregistered; the owner signs off before any job runs)", flush=True)
        train, test, _ = rm.load_market_file(path)
        report = rm.drive_check([m.market for m in train.values()], [m.market for m in test.values()],
                                rm.locked_config())
        print(json.dumps(report, indent=1))

    rep.check("market file unchanged during the check", rm.file_sha256(path) == digest)
    print(f"\n{'ALL CHECKS PASSED' if not rep.failed else f'{len(rep.failed)} CHECK(S) FAILED: ' + '; '.join(rep.failed)}")
    print(f"sha256 {digest}  {path.name}")
    return 0 if not rep.failed else 1


if __name__ == "__main__":
    sys.exit(main())
