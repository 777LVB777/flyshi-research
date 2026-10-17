"""Does Gamma /markets/keyset?closed=true leave out archived markets? ONE read-only request.

Context: phase2-design.md 10.10. The full closed=true listing (snapshot
20261016T213329Z) holds 4,227,473 markets and none with archived=true, while the
numeric IDs up to 5,787,701 leave 1,560,228 gaps, including 99,823 of the IDs below
100,000. The Gamma docs (read 2026-10-16) list no ``archived`` query parameter for
/markets/keyset or /markets, and do not say whether archived markets are returned.

The request is an identifier lookup on the SAME permitted endpoint:

    GET https://gamma-api.polymarket.com/markets/keyset?closed=any&id=1&id=2&...&limit=100

with the 98 lowest IDs ABSENT from the snapshot plus two PRESENT IDs (12, 17) as
controls. ``closed=any`` is documented for identifier lookups (at most 100 IDs).
It passes every gate of the loader: --allow-network, the Gamma permission file, a
terms check within 24 h, the rate cap and the request log. The raw response is
stored privately under data/polymarket/raw/. Only id, closed, archived and active
are printed; no price or outcome field is read. (The client retries only on a
transient failure, each attempt logged.)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("load_polymarket", HERE / "load_polymarket.py")
lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lp)
pm = lp.pm

CONTROL_IDS = ("12", "17")  # present in the closed=true snapshot
#: the 98 lowest numeric IDs absent from metadata_closed_markets_20261016T213329Z.json
PROBE_IDS = tuple(str(i) for i in (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33,
    34, 35, 37, 38, 39, 41, 45, 49, 50, 51, 52, 53, 54, 55, 58, 60, 61, 62, 68, 79, 80, 81, 82, 83, 84, 85,
    88, 89, 90, 91, 94, 95, 104, 106, 112, 113, 116, 117, 118, 121, 122, 123, 124, 125, 126, 127, 128, 129,
    130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150,
    151))
PARAMS = {"closed": "any", "id": [*PROBE_IDS, *CONTROL_IDS], "limit": 100}
FIELDS = ("id", "closed", "archived", "active")


def verdict(rows) -> str:
    by_id = {str(r.get("id")): r for r in rows}
    if not all(c in by_id for c in CONTROL_IDS):
        return ("INCONCLUSIVE: a control market present in the listing was not returned, so the "
                "lookup itself did not work as expected. Do not retry blindly; inspect the request log.")
    probes = [by_id[i] for i in PROBE_IDS if i in by_id]
    if any(r.get("archived") for r in probes):
        return ("LISTING EXCLUDES ARCHIVED: markets absent from closed=true are returned by ID with "
                "archived=true. Safeguard 12 is not met by the listing; archived markets need their own "
                "retrieval (owner decision).")
    if any(r.get("closed") for r in probes):
        return ("LISTING MISSED CLOSED, NON-ARCHIVED MARKETS: returned by ID with closed=true and "
                "archived=false, yet absent from the listing. Investigate the paging before freezing.")
    if probes:
        return "PROBES RETURNED AS OPEN (closed=false): not archived and not in the closed universe."
    return ("NOT SERVED EVEN BY ID: none of the 98 absent IDs exists on /markets/keyset (controls returned). "
            "The closed=true listing is complete for what this endpoint serves. Whether archived markets "
            "exist elsewhere is not settled by this endpoint.")


def main(argv=None, transport=None, now=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--allow-network", action="store_true")
    p.add_argument("--permission", type=Path)
    p.add_argument("--rate", type=float, default=pm.DEFAULT_REQUESTS_PER_SECOND)
    p.add_argument("--data-dir", type=Path, default=lp.DATA_DIR)
    args = p.parse_args(argv)
    now = now or datetime.now(timezone.utc)
    try:
        c = lp.network_client(args, pm.GAMMA_MARKETS, now, transport)
        page = c.get(pm.GAMMA_MARKETS, PARAMS)
    except pm.NetworkRefused as why:
        print(f"REFUSED: {why}", file=sys.stderr)
        return 2
    except pm.RetriesExhausted as failed:
        print(f"STOPPED: {failed}", file=sys.stderr)
        return 4
    rows = [{k: m.get(k) for k in FIELDS} for m in (page.get("markets") or [])]
    result = {"checked_utc": now.isoformat(), "requests": c.requests, "params": PARAMS,
              "returned": rows, "next_cursor_present": bool(page.get("next_cursor")), "verdict": verdict(rows)}
    out = args.data_dir / f"archived_check_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({**result, "saved": str(out)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
