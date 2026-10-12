"""Polymarket loader CLI for the Phase 2 replay (DRAFT). Network is OFF by default.

Spec: docs/design/phase2-design.md, Sections 1 and 10. Library:
flyshi_research.realdata.polymarket.

Steps (run in order; each writes under --data-dir, which is git-ignored because raw
data is never redistributed):

  select   fetch closed-market metadata (Gamma /markets/keyset), select, freeze the
           list with SHA-256                                        [network]
  history  fetch each frozen market's price history ending at its decision time
           (CLOB /prices-history)                                   [network]
  build    features strictly before the decision time, train/test split, and the
           Market file the synthetic runner consumes                 [no network]
  check    print the policy status for both endpoints               [no network]

A network step refuses unless BOTH --allow-network is given AND --permission names
a recorded permission file that covers that exact endpoint, with a published rate
limit the pre-set rate stays under (at most 25% of it).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

from flyshi_research.realdata import polymarket as pm

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "data" / "polymarket"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("check", "select", "history", "build"))
    p.add_argument("--allow-network", action="store_true",
                   help="Permit requests (also needs --permission covering the endpoint).")
    p.add_argument("--permission", type=Path, help="Recorded permission file (JSON).")
    p.add_argument("--rate", type=float, default=pm.DEFAULT_REQUESTS_PER_SECOND,
                   help="Pre-set requests per second (default 0.5).")
    p.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p.add_argument("--min-volume", type=float, default=pm.MIN_FINAL_VOLUME_USDC)
    p.add_argument("--max-pages", type=int, default=None, help="Stop metadata paging early (testing).")
    p.add_argument("--cutoff", help="build: training markets resolved before this UTC date (YYYY-MM-DD).")
    p.add_argument("--gap-days", type=float, default=pm.DEFAULT_SPLIT_GAP.days)
    return p


def policy(args) -> pm.NetworkPolicy:
    perm = pm.Permission.load(args.permission) if args.permission else None
    return pm.NetworkPolicy(allow_network=args.allow_network, permission=perm, requests_per_second=args.rate)


def client(args, transport=None) -> pm.PolymarketClient:
    d = args.data_dir
    return pm.PolymarketClient(policy(args), transport, d / "request_log.jsonl", raw_dir=d / "raw")


def main(argv=None, transport=None) -> int:
    args = parser().parse_args(argv)
    d = args.data_dir
    frozen_path = d / "frozen_market_list.json"
    if args.step == "check":
        pol = policy(args)
        for ep in pm.ALLOWED_ENDPOINTS:
            try:
                pol.check(ep)
                print(f"ALLOWED  {ep}")
            except pm.NetworkRefused as why:
                print(f"REFUSED  {ep}: {why}")
        return 0
    try:
        if args.step == "select":
            c = client(args, transport)
            c.policy.check(pm.GAMMA_MARKETS)  # refuse before creating anything
            sel = pm.select_markets(pm.fetch_closed_markets(c, args.max_pages), args.min_volume)
            digest = pm.freeze_selection(sel, frozen_path)
            print(json.dumps({"frozen_sha256": digest, "counts": sel.counts,
                              "volume_sensitivity": sel.volume_sensitivity, "requests": c.requests}, indent=1))
            return 0
        if args.step == "history":
            c = client(args, transport)
            c.policy.check(pm.CLOB_PRICES_HISTORY)
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
