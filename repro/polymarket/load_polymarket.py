"""Polymarket loader CLI for the Phase 2 replay (DRAFT). Network is OFF by default.

Spec: docs/design/phase2-design.md, Sections 1 and 10. Library:
flyshi_research.realdata.polymarket.

Steps (each writes under --data-dir, which is git-ignored because raw data is never
redistributed):

  check    print the policy and terms-check status for both endpoints  [no network]
  terms    hash a locally saved copy of the Terms of Use and record whether it
           matches the recorded SHA-256 (--terms-file)               [no network]
  select   fetch closed-market metadata (Gamma /markets/keyset)     [network]
             --count-only     save a private metadata snapshot and print the
                              blinded count report; freeze nothing
             (default)        select and freeze the market list with SHA-256
             --from-metadata  select and freeze from a saved snapshot [no network]
  history  fetch each frozen market's price history ending at its decision time
           (CLOB /prices-history)                                    [network]
  build    features strictly before the decision time, train/test split, and the
           Market file the synthetic runner consumes                 [no network]

A network step refuses unless ALL of: --allow-network; --permission naming a recorded
permission file that covers that exact endpoint, with our rate at most 25% of the
published limit; and a matching terms check recorded within the last 24 h.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flyshi_research.realdata import polymarket as pm

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "data" / "polymarket"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("check", "terms", "select", "history", "build"))
    p.add_argument("--allow-network", action="store_true",
                   help="Permit requests (also needs --permission covering the endpoint).")
    p.add_argument("--permission", type=Path, help="Recorded permission file (JSON).")
    p.add_argument("--rate", type=float, default=pm.DEFAULT_REQUESTS_PER_SECOND,
                   help="Pre-set requests per second (default 0.5).")
    p.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p.add_argument("--terms-file", type=Path, help="terms: a locally saved plain-text copy of the terms.")
    p.add_argument("--count-only", action="store_true",
                   help="select: snapshot + blinded count report only; freeze nothing.")
    p.add_argument("--from-metadata", type=Path, help="select: freeze from a saved snapshot (no network).")
    p.add_argument("--min-volume", type=float, default=pm.MIN_FINAL_VOLUME_USDC)
    p.add_argument("--max-pages", type=int, default=None, help="Stop metadata paging early (trial run).")
    p.add_argument("--trial-end-date-min", metavar="YYYY-MM-DD",
                   help="Trial only (needs --count-only and --max-pages): look at markets whose scheduled end"
                        " is on or after this date (Gamma end_date_min). Never used for the real count; it"
                        " writes no progress file, so the full run is unaffected.")
    p.add_argument("--cutoff", help="build: training markets resolved before this UTC date (YYYY-MM-DD).")
    p.add_argument("--gap-days", type=float, default=pm.DEFAULT_SPLIT_GAP.days)
    return p


def policy(args) -> pm.NetworkPolicy:
    perm = pm.Permission.load(args.permission) if args.permission else None
    return pm.NetworkPolicy(allow_network=args.allow_network, permission=perm, requests_per_second=args.rate)


def client(args, transport=None) -> pm.PolymarketClient:
    d = args.data_dir
    return pm.PolymarketClient(policy(args), transport, d / "request_log.jsonl", raw_dir=d / "raw")


def network_client(args, endpoint: str, now: datetime, transport=None) -> pm.PolymarketClient:
    """Every gate, in order, before anything is created or requested."""
    c = client(args, transport)
    c.policy.check(endpoint)
    pm.require_fresh_terms_check(args.data_dir / "terms_check.json", now)
    return c


def main(argv=None, transport=None, now=None) -> int:
    args = parser().parse_args(argv)
    now = now or datetime.now(timezone.utc)
    d = args.data_dir
    frozen_path = d / "frozen_market_list.json"
    terms_path = d / "terms_check.json"
    if args.step == "check":
        pol = policy(args)
        for ep in pm.ALLOWED_ENDPOINTS:
            try:
                pol.check(ep)
                print(f"ALLOWED  {ep}")
            except pm.NetworkRefused as why:
                print(f"REFUSED  {ep}: {why}")
        try:
            rec = pm.require_fresh_terms_check(terms_path, now)
            print(f"TERMS    match, checked {rec['checked_utc']}")
        except pm.NetworkRefused as why:
            print(f"TERMS    {why}")
        return 0
    if args.step == "terms":
        if not args.terms_file:
            raise SystemExit("terms needs --terms-file (a saved copy of the plain-text export)")
        rec = pm.record_terms_check(args.terms_file, terms_path, now)
        print(json.dumps(rec, indent=1))
        if not rec["matches"]:
            print("TERMS CHANGED since 2026-10-11: stop; the owner must review them before any request.",
                  file=sys.stderr)
            return 3
        return 0
    if args.step == "select" and args.from_metadata:
        raw = pm.read_snapshot(args.from_metadata)
        sel = pm.select_markets(raw, args.min_volume)
        digest = pm.freeze_selection(sel, frozen_path)
        print(json.dumps({"frozen_sha256": digest, "from_snapshot": str(args.from_metadata),
                          **pm.count_report(raw)}, indent=1))
        return 0
    try:
        if args.step == "select":
            c = network_client(args, pm.GAMMA_MARKETS, now, transport)
            stamp = now.strftime("%Y%m%dT%H%M%SZ")
            if args.trial_end_date_min:
                if not (args.count_only and args.max_pages):
                    raise SystemExit("--trial-end-date-min is for trials only: add --count-only and --max-pages")
                raw = pm.fetch_closed_markets(c, args.max_pages, transform=pm.compact_market,
                                              extra_params={"end_date_min": args.trial_end_date_min + "T00:00:00Z"})
                snap = d / f"trial_metadata_end_date_min_{args.trial_end_date_min}_{stamp}.json"
            else:
                progress = d / "metadata_progress.jsonl"  # resumable: a re-run continues from here
                raw = pm.fetch_closed_markets(c, args.max_pages, transform=pm.compact_market,
                                              progress_path=progress)
                snap = d / f"metadata_closed_markets_{stamp}.json"
                if args.max_pages is None:
                    progress.rename(d / f"metadata_progress_{stamp}_complete.jsonl")
            snap_sha = pm.write_snapshot(raw, snap)
            report = {"partial_trial_run": args.max_pages is not None,
                      "trial_filter_end_date_min": args.trial_end_date_min, "requests": c.requests,
                      "snapshot": str(snap), "snapshot_sha256": snap_sha, **pm.count_report(raw)}
            if not args.count_only:
                report["frozen_sha256"] = pm.freeze_selection(pm.select_markets(raw, args.min_volume), frozen_path)
            print(json.dumps(report, indent=1))
            return 0
        if args.step == "history":
            c = network_client(args, pm.CLOB_PRICES_HISTORY, now, transport)
            frozen, digest = pm.load_frozen(frozen_path)
            hist_path = d / f"histories_{digest[:12]}.json"
            have = json.loads(hist_path.read_text()) if hist_path.exists() else {}
            for m in frozen:
                if m.market_id not in have:  # restartable
                    have[m.market_id] = pm.fetch_price_history(c, m)
                    hist_path.write_text(json.dumps(have))
            print(f"histories for {len(have)}/{len(frozen)} markets in {hist_path} ({c.requests} requests)")
            return 0
    except pm.NetworkRefused as why:
        print(f"REFUSED: {why}", file=sys.stderr)
        return 2
    # build: no network
    if not args.cutoff:
        raise SystemExit("build needs --cutoff YYYY-MM-DD")
    frozen, digest = pm.load_frozen(frozen_path)
    outcomes = json.loads(frozen_path.with_name(frozen_path.name + ".outcomes.json").read_text())
    hist = json.loads((d / f"histories_{digest[:12]}.json").read_text())
    built, counts = pm.build_markets(frozen, {k: [tuple(x) for x in v] for k, v in hist.items()}, outcomes)
    cutoff = pm.parse_time(args.cutoff + "T00:00:00Z")
    gap = timedelta(days=args.gap_days)
    train, test, split = pm.split_train_test(built, cutoff, gap)
    out = d / f"markets_{digest[:12]}_cutoff_{args.cutoff}.json"
    pm.write_market_file(out, train, test, digest, cutoff, gap, {**counts, **split})
    print(json.dumps({"output": str(out), **counts, **split}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
