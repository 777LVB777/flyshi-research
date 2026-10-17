"""Polymarket loader: network refusal, rate and log, selection, freezing, look-ahead guard,
split and output format.

Only RECORDED FAKE responses (tests/fixtures/polymarket, hand-written to the documented
schema) are used, through an injected fake transport. No test makes a network request:
the real transport is never constructed (``_no_real_transport`` makes sure of it).
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from flyshi_research.realdata import polymarket as pm
from flyshi_research.simulator import Market

REAL_URLLIB_TRANSPORT = pm.urllib_transport  # kept before the autouse fixture replaces it

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures" / "polymarket"
CLI = REPO / "repro" / "polymarket" / "load_polymarket.py"


@pytest.fixture(autouse=True)
def _no_real_transport(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to build the real network transport")
    monkeypatch.setattr(pm, "urllib_transport", refuse)


class FakeServer:
    """Serves the recorded fake responses; records every call."""

    def __init__(self, status_sequence=None):
        self.calls = []
        self.status_sequence = list(status_sequence or [])

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        if self.status_sequence:
            status = self.status_sequence.pop(0)
            if status != 200:
                return status, b'{"error":"rate limited"}', {}
        parsed = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(parsed.query))
        if parsed.netloc == "gamma-api.polymarket.com" and parsed.path == "/markets/keyset":
            name = "gamma_markets_keyset_page2.json" if q.get("after_cursor") == "FAKECURSOR1" \
                else "gamma_markets_keyset_page1.json"
        elif parsed.netloc == "clob.polymarket.com" and parsed.path == "/prices-history":
            name = f"clob_prices_history_{q['market']}.json"
        else:
            return 404, b"{}", {}
        return 200, (FIX / name).read_bytes(), {}


def permission(tmp_path, endpoints=pm.ALLOWED_ENDPOINTS, requests=100, per_seconds=10):
    path = tmp_path / "permission.json"
    path.write_text(json.dumps({
        "recorded_on": "2026-10-12", "recorded_by": "test",
        "endpoints": [{"endpoint": e, "basis": "TEST ONLY",
                       "published_limit": {"requests": requests, "per_seconds": per_seconds, "source": "test"}}
                      for e in endpoints]}))
    return pm.Permission.load(path)


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def client(tmp_path, server, allow=True, perm="all", rate=0.5, clock=None):
    p = permission(tmp_path) if perm == "all" else perm
    clock = clock or FakeClock()
    pol = pm.NetworkPolicy(allow_network=allow, permission=p, requests_per_second=rate)
    return pm.PolymarketClient(pol, server, tmp_path / "log.jsonl", raw_dir=tmp_path / "raw",
                               clock=clock.now, sleep=clock.sleep, wallclock=lambda: 1.76e9)


# ---- network refusal ------------------------------------------------------------------- #
def test_network_is_refused_without_the_flag_even_with_a_permission(tmp_path):
    server = FakeServer()
    c = client(tmp_path, server, allow=False)
    with pytest.raises(pm.NetworkRefused, match="network is disabled"):
        c.get(pm.GAMMA_MARKETS, {"closed": "true"})
    assert server.calls == [] and not (tmp_path / "log.jsonl").exists()


def test_network_is_refused_with_the_flag_but_no_or_partial_permission(tmp_path):
    server = FakeServer()
    with pytest.raises(pm.NetworkRefused, match="no permission file"):
        client(tmp_path, server, perm=None).get(pm.GAMMA_MARKETS, {})
    gamma_only = permission(tmp_path, endpoints=(pm.GAMMA_MARKETS,))
    c = client(tmp_path, server, perm=gamma_only)
    with pytest.raises(pm.NetworkRefused, match="does not cover"):
        c.get(pm.CLOB_PRICES_HISTORY, {"market": "1"})
    assert server.calls == []


def test_only_the_two_coded_endpoints_exist_and_a_permission_cannot_add_more(tmp_path):
    extra = ("GET https://data-api.polymarket.com/trades", "GET https://clob.polymarket.com/book",
             "POST https://clob.polymarket.com/batch-prices-history", "GET https://gamma-api.polymarket.com/markets")
    server = FakeServer()
    c = client(tmp_path, server, perm=permission(tmp_path, endpoints=pm.ALLOWED_ENDPOINTS + extra))
    for ep in extra:
        with pytest.raises(pm.NetworkRefused, match="not one of the allowed endpoints"):
            c.get(ep, {})
    assert pm.ALLOWED_ENDPOINTS == ("GET https://gamma-api.polymarket.com/markets/keyset",
                                    "GET https://clob.polymarket.com/prices-history")
    assert server.calls == []


def test_rate_must_stay_under_a_quarter_of_the_published_limit(tmp_path):
    p = permission(tmp_path, requests=10, per_seconds=10)  # 1 req/s published -> at most 0.25 req/s
    with pytest.raises(pm.NetworkRefused, match="exceeds"):
        client(tmp_path, FakeServer(), perm=p, rate=0.5).get(pm.GAMMA_MARKETS, {})
    client(tmp_path, FakeServer(), perm=p, rate=0.25).get(pm.GAMMA_MARKETS, {})


def test_requests_are_read_only_unauthenticated_throttled_and_logged(tmp_path):
    server, clock = FakeServer(), FakeClock()
    c = client(tmp_path, server, rate=0.5, clock=clock)
    pages = pm.fetch_closed_markets(c)
    assert len(pages) == 13 and len(server.calls) == 2
    for url, headers in server.calls:
        assert url.startswith("https://gamma-api.polymarket.com/markets/keyset?")
        assert not {h.lower() for h in headers} & {"authorization", "cookie", "x-api-key", "poly_api_key"}
    assert clock.slept == [pytest.approx(2.0)]  # 0.5 req/s: second request waits 2 s
    log = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert [e["status"] for e in log] == [200, 200] and all(len(e["sha256"]) == 64 for e in log)
    assert len(list((tmp_path / "raw").iterdir())) == 2  # stored privately
    assert not hasattr(c, "post") and not hasattr(c, "put") and not hasattr(c, "delete")


def test_429_backs_off_and_is_logged(tmp_path):
    server, clock = FakeServer(status_sequence=[429, 429, 200]), FakeClock()
    c = client(tmp_path, server, clock=clock)
    c.get(pm.GAMMA_MARKETS, {"closed": "true"})
    log = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert [e["status"] for e in log] == [429, 429, 200] and 2.0 in clock.slept and 4.0 in clock.slept


def test_redirects_are_refused():
    handler = pm._NoRedirect()
    with pytest.raises(pm.NetworkRefused, match="redirect"):
        handler.redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example/")


# ---- selection and freezing ------------------------------------------------------------ #
def _raw():
    return (json.loads((FIX / "gamma_markets_keyset_page1.json").read_text())["markets"]
            + json.loads((FIX / "gamma_markets_keyset_page2.json").read_text())["markets"])


def test_selection_counts_every_exclusion_and_keeps_one_market_per_event():
    sel = pm.select_markets(_raw())
    c = sel.counts
    assert c["raw"] == 13 and c["duplicate_id"] == 1 and c["not_closed"] == 1 and c["multi_outcome"] == 1
    assert c["missing_token_ids"] == 1 and c["void_50_50"] == 1 and c["interior_final_price"] == 1
    assert c["below_min_volume"] == 1 and c["no_decision_window"] == 1 and c["closed_before_decision"] == 1
    assert c["eligible_before_event_choice"] == 4 and c["dropped_one_per_event"] == 1
    assert c["selected"] == 3 and c["archived_selected"] == 1
    ids = {m.market_id for m in sel.markets}
    assert {"106", "110"} <= ids and len(ids & {"101", "102"}) == 1
    # counted at the volume step, i.e. among markets that passed every earlier filter
    assert sel.volume_sensitivity == {">=1000": 7, ">=100000": 0, ">=10000": 6}
    assert {m.event_id for m in sel.markets if m.market_id == "110"} == {"market:110"}


def test_selection_and_decision_times_are_blind_to_outcome_and_price():
    raw = _raw()
    flipped = json.loads(json.dumps(raw))
    for m in flipped:
        if m["outcomePrices"] in ('["1", "0"]', '["0", "1"]'):
            m["outcomePrices"] = '["0", "1"]' if m["outcomePrices"] == '["1", "0"]' else '["1", "0"]'
        m["lastTradePrice"] = 0.123
    a, b = pm.select_markets(raw), pm.select_markets(flipped)
    assert a.markets == b.markets and a.counts == b.counts
    assert all(a.outcomes[k] != b.outcomes[k] for k in a.outcomes)


def test_decision_time_is_inside_the_scheduled_life_with_margins():
    for m in pm.select_markets(_raw()).markets:
        td, start, end = (pm.parse_time(x) for x in (m.decision_time, m.start, m.end))
        assert start + timedelta(hours=24) <= td <= end - timedelta(hours=24)
        assert td < pm.parse_time(m.closed_time)


def test_freeze_writes_a_hash_without_outcomes_and_refuses_a_different_list(tmp_path):
    sel = pm.select_markets(_raw())
    path = tmp_path / "frozen.json"
    digest = pm.freeze_selection(sel, path)
    assert (tmp_path / "frozen.json.sha256").read_text().strip() == digest
    frozen_fields = {k for m in json.loads(path.read_text())["markets"] for k in m}
    assert frozen_fields == set(pm.SelectedMarket.__dataclass_fields__) and "outcome" not in frozen_fields
    frozen, d2 = pm.load_frozen(path)
    assert d2 == digest and frozen == sel.markets
    assert pm.freeze_selection(sel, path) == digest  # same list: fine (restart)
    other = pm.select_markets(_raw(), min_volume=1_000.0)
    with pytest.raises(RuntimeError, match="different frozen list"):
        pm.freeze_selection(other, path)
    payload = json.loads(path.read_text())
    payload["markets"][0]["decision_time"] = "2099-01-01T00:00:00+00:00"
    path.write_text(json.dumps(payload))
    with pytest.raises(RuntimeError, match="hash mismatch"):
        pm.load_frozen(path)


# ---- look-ahead guard ---------------------------------------------------------------- #
TD = datetime(2025, 3, 10, 12, 0, tzinfo=timezone.utc)
END = datetime(2025, 4, 1, tzinfo=timezone.utc)


def _history(rng, n=200):
    t0 = int((TD - timedelta(days=5)).timestamp())
    return sorted((t0 + rng.randrange(0, 10 * 86400), round(rng.random(), 4)) for _ in range(n))


def test_no_feature_uses_data_at_or_after_the_decision_time():
    """Fails if any feature reads a point timestamped at or after t_d: every such point is
    replaced, removed or added in bulk, and the features must not change."""
    rng = random.Random(20261012)
    cut = int(TD.timestamp())
    checked = 0
    for _ in range(300):
        h = _history(rng)
        base, why = pm.decision_features(h, TD, END)
        past = [pt for pt in h if pt[0] < cut]
        variants = [
            past,                                                         # everything at/after t_d removed
            past + [(t, 1.0 - p) for t, p in h if t >= cut],              # every later price inverted
            past + [(cut, 0.999), (cut + 1, 0.001), (cut + 86400, 0.5)],  # points exactly at and after t_d
        ]
        for v in variants:
            assert pm.decision_features(v, TD, END) == (base, why)
        checked += base is not None
    assert checked > 100  # the property was exercised on markets that produced features


def test_a_point_exactly_at_the_decision_time_is_not_used():
    cut = int(TD.timestamp())
    h = [(cut - 2 * 86400, 0.40), (cut - 3600, 0.50), (cut, 0.99)]
    f, why = pm.decision_features(h, TD, END)
    assert why is None and f.price == 0.50 and f.price_time == cut - 3600
    assert f.recent_change == pytest.approx(0.10)
    assert f.time_to_resolution == pytest.approx((END - TD).total_seconds() / 86400)


def test_stale_and_too_young_histories_are_excluded_with_a_reason():
    cut = int(TD.timestamp())
    assert pm.decision_features([], TD, END) == (None, "no_price_before_decision")
    assert pm.decision_features([(cut - 3 * 86400, 0.5)], TD, END) == (None, "stale_price")
    assert pm.decision_features([(cut - 3600, 0.5)], TD, END) == (None, "no_price_before_window")


def test_history_requests_end_at_the_decision_time(tmp_path):
    server = FakeServer()
    c = client(tmp_path, server)
    for m in pm.select_markets(_raw()).markets:
        pm.fetch_price_history(c, m)
    for url, _ in server.calls:
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        m = next(x for x in pm.select_markets(_raw()).markets if x.yes_token_id == q["market"])
        assert int(q["endTs"]) == int(pm.parse_time(m.decision_time).timestamp())
        assert int(q["startTs"]) < int(q["endTs"])


# ---- split and output -------------------------------------------------------------- #
def _end_to_end(tmp_path, cutoff="2025-06-01"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    server = FakeServer()
    c = client(tmp_path, server)
    sel = pm.select_markets(pm.fetch_closed_markets(c))
    digest = pm.freeze_selection(sel, tmp_path / "frozen.json")
    frozen, _ = pm.load_frozen(tmp_path / "frozen.json")
    hist = {m.market_id: pm.fetch_price_history(c, m) for m in frozen}
    built, counts = pm.build_markets(frozen, hist, sel.outcomes)
    cut = pm.parse_time(cutoff + "T00:00:00Z")
    train, test, split = pm.split_train_test(built, cut)
    out = tmp_path / "markets.json"
    pm.write_market_file(out, train, test, digest, cut, pm.DEFAULT_SPLIT_GAP, {**counts, **split})
    return out, train, test, split, counts


def test_split_trains_only_on_markets_resolved_before_the_cutoff_with_a_gap(tmp_path):
    _, train, test, split, counts = _end_to_end(tmp_path)
    cut = pm.parse_time("2025-06-01T00:00:00Z")
    assert counts["built"] == 3 and split == {"train": 2, "test": 1, "straddling_excluded": 0}
    assert all(pm.parse_time(b.market.closed_time) < cut for b in train)
    assert all(pm.parse_time(b.market.decision_time) >= cut + timedelta(days=7) for b in test)
    assert [b.market.closed_time for b in train] == sorted(b.market.closed_time for b in train)
    _, train2, test2, split2, _ = _end_to_end(tmp_path / "late", cutoff="2025-04-20")
    assert split2["straddling_excluded"] == 1  # 106 resolves after, but is decided before cutoff + gap


def test_output_is_the_market_type_the_synthetic_runner_consumes(tmp_path):
    from flyshi_research.learning import synthetic_market as sm
    out, train, test, _, _ = _end_to_end(tmp_path)
    tr, te = pm.load_market_file(out)
    assert all(isinstance(m, Market) for m in tr + te)
    assert [m.sequence for m in tr] == list(range(len(tr))) and [m.sequence for m in te] == [0]
    for m in tr + te:
        assert m.signal == 0.5 and m.liquidity == 0.5 and math.isnan(m.latent_probability)
        assert 0.0 <= m.quote <= 1.0 and -1.0 <= m.recent_change <= 1.0 and m.time_to_resolution > 0
        assert m.outcome in (0, 1)
    assert sm.feature_matrix(tr + te).shape == (3, 5)
    payload = json.loads(out.read_text())
    assert payload["format"] == pm.MARKET_FILE_FORMAT and len(payload["frozen_list_sha256"]) == 64


# ---- CLI refuses by default ------------------------------------------------------------ #
def _cli():
    spec = importlib.util.spec_from_file_location("load_polymarket_cli_test", CLI)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cli_network_steps_refuse_without_flag_and_permission(tmp_path, capsys):
    cli, server = _cli(), FakeServer()
    assert cli.main(["select", "--data-dir", str(tmp_path)], transport=server) == 2
    assert cli.main(["select", "--allow-network", "--data-dir", str(tmp_path)], transport=server) == 2
    assert server.calls == [] and not (tmp_path / "frozen_market_list.json").exists()
    assert "REFUSED" in capsys.readouterr().err
    cli.main(["check"])
    assert capsys.readouterr().out.count("REFUSED") == 2


NOW = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)


def _fake_terms(tmp_path, monkeypatch, text=b"FAKE TERMS TEXT"):
    f = tmp_path / "terms.txt"
    f.write_bytes(text)
    import hashlib
    monkeypatch.setattr(pm, "RECORDED_TERMS_SHA256", hashlib.sha256(b"FAKE TERMS TEXT").hexdigest())
    return f


def _perm_file(tmp_path, endpoints=pm.ALLOWED_ENDPOINTS):
    permission(tmp_path, endpoints=endpoints)  # writes tmp_path/permission.json
    p = tmp_path / "perm.json"
    (tmp_path / "permission.json").rename(p)
    return p


def test_cli_runs_end_to_end_on_the_fake_server_when_both_are_given(tmp_path, capsys, monkeypatch):
    cli, server = _cli(), FakeServer()
    p = _perm_file(tmp_path)
    terms = _fake_terms(tmp_path, monkeypatch)
    args = ["--allow-network", "--permission", str(p), "--data-dir", str(tmp_path / "d")]
    assert cli.main(["terms", "--terms-file", str(terms), "--data-dir", str(tmp_path / "d")], now=NOW) == 0
    assert cli.main(["select", *args], transport=server, now=NOW) == 0
    split = ["--cutoff", "2025-06-01"]
    # the fixtures cannot reach Design A's targets: every pool market is fetched, and exit 5 says so
    assert cli.main(["history", *args, *split], transport=server, now=NOW) == 5
    plan = json.loads(next((tmp_path / "d").glob("fill_plan_*.json")).read_text())
    assert plan["pools"]["train"]["considered"] == plan["pools"]["train"]["pool_size"] == 2
    assert plan["pools"]["test"]["considered"] == plan["pools"]["test"]["pool_size"] == 1
    assert cli.main(["build", "--data-dir", str(tmp_path / "d"), *split]) == 0
    out = next((tmp_path / "d").glob("markets_*_cutoff_2025-06-01.json"))
    tr, te = pm.load_market_file(out)
    assert (len(tr), len(te)) == (2, 1)


# ---- terms gate, count-only report, permission file (2026-10-12) ---------------------- #
def test_network_steps_refuse_without_a_fresh_matching_terms_check(tmp_path, monkeypatch, capsys):
    cli, server = _cli(), FakeServer()
    p = _perm_file(tmp_path)
    d = tmp_path / "d"
    args = ["select", "--count-only", "--allow-network", "--permission", str(p), "--data-dir", str(d)]
    assert cli.main(args, transport=server, now=NOW) == 2  # no terms check at all
    changed = _fake_terms(tmp_path, monkeypatch, text=b"CHANGED TERMS")
    assert cli.main(["terms", "--terms-file", str(changed), "--data-dir", str(d)], now=NOW) == 3
    assert cli.main(args, transport=server, now=NOW) == 2  # recorded, but not matching
    same = _fake_terms(tmp_path, monkeypatch)
    assert cli.main(["terms", "--terms-file", str(same), "--data-dir", str(d)], now=NOW) == 0
    assert cli.main(args, transport=server, now=NOW + timedelta(hours=25)) == 2  # stale
    assert server.calls == []
    assert "terms" in capsys.readouterr().err.lower()
    assert cli.main(args, transport=server, now=NOW + timedelta(hours=1)) == 0
    assert len(server.calls) == 2


def test_count_only_snapshots_and_reports_but_freezes_nothing(tmp_path, monkeypatch, capsys):
    cli, server = _cli(), FakeServer()
    p, d = _perm_file(tmp_path), tmp_path / "d"
    terms = _fake_terms(tmp_path, monkeypatch)
    cli.main(["terms", "--terms-file", str(terms), "--data-dir", str(d)], now=NOW)
    capsys.readouterr()
    assert cli.main(["select", "--count-only", "--allow-network", "--permission", str(p), "--data-dir", str(d)],
                    transport=server, now=NOW) == 0
    report = json.loads(capsys.readouterr().out)
    assert not (d / "frozen_market_list.json").exists() and not list(d.glob("*.outcomes.json"))
    assert report["qualifying_one_per_event"] == {">=1000": 4, ">=10000": 3, ">=100000": 0}
    assert report["resolved_binary_markets"] == 7 and report["raw_markets"] == 13
    assert report["exclusions_by_reason_at_10000"]["void_50_50"] == 1
    assert sum(report["selected_at_10000_by_close_month"].values()) == 3
    assert all(c.startswith("https://gamma-api.polymarket.com/") for c, _ in server.calls)
    snap = pm.read_snapshot(Path(report["snapshot"]))
    assert len(snap) == 13 and set(snap[0]) == set(pm.SNAPSHOT_FIELDS) | {"events"}
    # later: freeze offline from the snapshot, no request at all
    n = len(server.calls)
    assert cli.main(["select", "--from-metadata", report["snapshot"], "--data-dir", str(d)], now=NOW) == 0
    assert (d / "frozen_market_list.json").exists() and len(server.calls) == n


def test_count_report_carries_no_outcome_or_price_information():
    raw = _raw()
    altered = json.loads(json.dumps(raw))
    for m in altered:
        if m["outcomePrices"] in ('["1", "0"]', '["0", "1"]'):
            m["outcomePrices"] = '["0", "1"]' if m["outcomePrices"] == '["1", "0"]' else '["1", "0"]'
        m.update(lastTradePrice=0.77, bestBid=0.7, bestAsk=0.8, oneDayPriceChange=0.1)
    a, b = pm.count_report(raw), pm.count_report(altered)
    assert a == b

    def keys(x):
        return set(x) | {k for v in x.values() if isinstance(v, dict) for k in keys(v)} if isinstance(x, dict) else set()

    named_reasons = {"interior_final_price", "malformed_prices"}  # resolution-state reasons, not prices
    for k in keys(a):
        assert "price" not in k.lower() or k in named_reasons, k
        assert k.lower() not in ("yes", "no", "outcome", "outcomes", "brier", "pnl"), k


def _real_page(name="gamma_markets_keyset_realformat_page1.json"):
    return json.loads((FIX / name).read_text())


def test_real_format_page_is_parsed_with_named_reasons():
    """Mirrors the REAL Gamma format seen in the 2026-10-12 trial (values made up)."""
    page = _real_page()
    assert set(page) == {"$schema", "markets", "next_cursor"}
    c = pm.select_markets(page["markets"]).counts
    assert c["raw"] == 12
    assert c["multi_outcome"] == 2 and c["two_named_outcomes_not_yes_no"] == 2
    assert c["near_0_1_not_exact"] == 2 and c["interior_final_price"] == 1  # AMM-era: never accepted
    assert c["missing_token_ids"] == 1 and c["missing_dates"] == 1
    assert c["selected"] == 2  # the two exact-settlement markets
    assert sum(v for k, v in c.items() if k not in (
        "raw", "eligible_before_event_choice", "selected", "archived_selected", "dropped_one_per_event")) \
        + c["eligible_before_event_choice"] == c["raw"]


def test_near_settled_amm_prices_are_never_taken_as_outcomes():
    assert pm._resolution(["0.9999999999999999999999999999999999", "0.0000000000000000000000000000000001"]) \
        == "near_0_1_not_exact"
    assert pm._resolution(["0.0000000000000000000000000000000001", "0.9999999999999999999999999999999999"]) \
        == "near_0_1_not_exact"  # symmetric: the reason does not reveal the side
    assert pm._resolution(["0.6125", "0.3875"]) == "interior_final_price"
    assert pm._resolution(["1", "0"]) == "yes" and pm._resolution(["0", "1"]) == "no"
    assert pm._resolution(["0.5", "0.5"]) == "void" and pm._resolution(None) == "malformed_prices"


def test_real_timestamp_formats_parse():
    for v, iso in (("2020-10-21T15:04:05.123Z", "2020-10-21T15:04:05.123000+00:00"),
                   ("2020-10-21T15:04:05.12Z", "2020-10-21T15:04:05.120000+00:00"),
                   ("2020-10-21T15:04:05.1Z", "2020-10-21T15:04:05.100000+00:00"),
                   ("2020-10-21T15:04:05Z", "2020-10-21T15:04:05+00:00"),
                   ("2021-01-06 17:30:00+00", "2021-01-06T17:30:00+00:00")):
        assert pm.parse_time(v).isoformat() == iso
    assert pm.parse_time(None) is None


def test_count_report_on_the_real_format_is_blind_to_outcomes_and_prices():
    raw = _real_page()["markets"]
    altered = json.loads(json.dumps(raw))
    for m in altered:
        prices = json.loads(m["outcomePrices"])
        if prices in (["1", "0"], ["0", "1"]):
            m["outcomePrices"] = json.dumps(prices[::-1])
        elif len(prices) == 2:  # move non-exact prices within their reason category, and swap sides
            r = pm._resolution(prices)
            new = ["0.99999999", "0.00000001"] if r == "near_0_1_not_exact" else ["0.41", "0.59"]
            m["outcomePrices"] = json.dumps(new)
    assert pm.count_report(raw) == pm.count_report(altered)
    rep = pm.count_report(raw)
    assert rep["era_and_status_in_raw"]["amm_market_maker_address_present"] == 8
    assert rep["era_and_status_in_raw"]["uma_resolution_status_resolved"] == 2


def test_the_recorded_permission_file_covers_gamma_only_at_a_safe_rate():
    path = REPO / "repro" / "polymarket" / "permissions" / "gamma_markets_keyset_20261012.json"
    perm = pm.Permission.load(path)
    assert [e.endpoint for e in perm.endpoints] == [pm.GAMMA_MARKETS]
    assert perm.endpoints[0].published_rate == 30.0  # /markets 300 req / 10 s
    raw = json.loads(path.read_text())
    assert "Roni" in raw["endpoints"][0]["basis"] and "NOT a definitive" in raw["endpoints"][0]["basis"]
    ours = raw["endpoints"][0]["our_rate_requests_per_second"]
    pm.NetworkPolicy(True, perm, ours).check(pm.GAMMA_MARKETS)
    with pytest.raises(pm.NetworkRefused, match="does not cover"):
        pm.NetworkPolicy(True, perm, ours).check(pm.CLOB_PRICES_HISTORY)


def test_metadata_fetch_resumes_after_an_interruption(tmp_path):
    progress = tmp_path / "progress.jsonl"

    class Dies(FakeServer):
        def __call__(self, url, headers):
            if "after_cursor" in url:
                raise ConnectionError("simulated interruption")
            return super().__call__(url, headers)

    with pytest.raises(pm.MetadataPageFailed, match="after cursor 'FAKECURSOR1'"):
        pm.fetch_closed_markets(client(tmp_path, Dies()), transform=pm.compact_market, progress_path=progress)
    assert len(progress.read_text().splitlines()) == 1  # page 1 saved
    for sub in ("b", "c", "e"):
        (tmp_path / sub).mkdir()
    server = FakeServer()
    resumed = pm.fetch_closed_markets(client(tmp_path / "b", server), transform=pm.compact_market,
                                      progress_path=progress)
    assert len(server.calls) == 1 and "after_cursor=FAKECURSOR1" in server.calls[0][0]
    whole = pm.fetch_closed_markets(client(tmp_path / "c", FakeServer()), transform=pm.compact_market)
    assert resumed == whole and pm.count_report(resumed) == pm.count_report(_raw())
    again = FakeServer()
    assert pm.fetch_closed_markets(client(tmp_path / "e", again), progress_path=progress) == whole
    assert again.calls == []  # a finished progress file needs no request



# ---- transient network failures (2026-10-12) ------------------------------------------ #
import http.client  # noqa: E402
import socket  # noqa: E402
import urllib.error  # noqa: E402

PAGE1 = (FIX / "gamma_markets_keyset_page1.json").read_bytes()


class Flaky:
    """Fails ``n`` times in the given way, then serves the recorded fake page."""

    def __init__(self, failure, n=1):
        self.failure, self.n, self.calls = failure, n, 0

    def __call__(self, url, headers):
        self.calls += 1
        if self.calls <= self.n:
            f = self.failure
            if isinstance(f, BaseException):
                raise f
            return f  # a (status, body, headers) tuple
        return 200, PAGE1, {}


FAILURES = {
    "truncated_body": ((200, PAGE1[: len(PAGE1) // 2], {}), "JSONDecodeError", len(PAGE1) // 2),
    "non_json_body": ((200, b"<html>502 Bad Gateway</html>", {}), "JSONDecodeError", 28),
    "IncompleteRead": (http.client.IncompleteRead(b"x" * 404009, 1000), "IncompleteRead", 404009),
    "ConnectionResetError": (ConnectionResetError(54, "Connection reset by peer"), "ConnectionResetError", 0),
    "RemoteDisconnected": (http.client.RemoteDisconnected("Remote end closed connection"), "RemoteDisconnected", 0),
    "socket.timeout": (socket.timeout("timed out"), "TimeoutError", 0),
    "TimeoutError": (TimeoutError("timed out"), "TimeoutError", 0),
    "URLError": (urllib.error.URLError(ConnectionRefusedError(61, "refused")), "URLError(ConnectionRefusedError)", 0),
    "transport_error": (pm.TransientNetworkError("IncompleteRead", 404009), "IncompleteRead", 404009),
    "HTTP 503": ((503, b"busy", {}), "HTTP 503", 4),
}


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_each_transient_failure_is_retried_logged_and_then_succeeds(tmp_path, name):
    failure, kind, nbytes = FAILURES[name]
    server, clock = Flaky(failure, n=2), FakeClock()
    c = client(tmp_path, server, clock=clock)
    page = c.get(pm.GAMMA_MARKETS, {"closed": "true"})
    assert len(page["markets"]) == 6 and server.calls == 3
    log = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert [e["result"] for e in log] == ["retry", "retry", "ok"]
    assert [e["error"] for e in log[:2]] == [kind, kind] and [e["bytes"] for e in log[:2]] == [nbytes, nbytes]
    assert 2.0 in clock.slept and 4.0 in clock.slept  # the existing backoff
    assert len(list((tmp_path / "raw").iterdir())) == 1  # only the page that parsed is saved


def test_a_page_failing_every_attempt_stops_naming_its_cursor_and_saves_nothing(tmp_path):
    progress = tmp_path / "progress.jsonl"

    class FailsPage2(FakeServer):
        def __call__(self, url, headers):
            if "after_cursor=FAKECURSOR1" in url:
                raise http.client.IncompleteRead(b"y" * 1234, 10)
            return super().__call__(url, headers)

    server, clock = FailsPage2(), FakeClock()
    with pytest.raises(pm.MetadataPageFailed) as failed:
        pm.fetch_closed_markets(client(tmp_path, server, clock=clock), transform=pm.compact_market,
                                progress_path=progress)
    msg = str(failed.value)
    assert "after cursor 'FAKECURSOR1'" in msg and "all 6 attempts" in msg and "IncompleteRead (1234 bytes)" in msg
    assert failed.value.cursor == "FAKECURSOR1" and failed.value.saved_pages == 1
    assert len(server.calls) == 1  # the fake records only the request it answered
    assert len(progress.read_text().splitlines()) == 1  # page 1 only; the failed page left no trace
    log = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert [e["result"] for e in log] == ["ok"] + ["retry"] * 5 + ["gave_up"]
    assert clock.slept.count(2.0) and 32.0 in clock.slept
    # resume continues from the last saved page with a working server: one request, page 2
    (tmp_path / "r").mkdir()
    server2 = FakeServer()
    resumed = pm.fetch_closed_markets(client(tmp_path / "r", server2), transform=pm.compact_market,
                                      progress_path=progress)
    assert len(server2.calls) == 1 and "after_cursor=FAKECURSOR1" in server2.calls[0][0]
    assert pm.count_report(resumed) == pm.count_report(_raw())


def test_cli_stops_with_a_clear_message_naming_the_cursor(tmp_path, monkeypatch, capsys):
    cli = _cli()
    p, d = _perm_file(tmp_path), tmp_path / "d"
    terms = _fake_terms(tmp_path, monkeypatch)
    cli.main(["terms", "--terms-file", str(terms), "--data-dir", str(d)], now=NOW)

    class FailsPage2(FakeServer):
        def __call__(self, url, headers):
            if "after_cursor" in url:
                raise ConnectionResetError(54, "reset")
            return super().__call__(url, headers)

    monkeypatch.setattr(pm.time, "sleep", lambda s: None)
    args = ["select", "--count-only", "--allow-network", "--permission", str(p), "--data-dir", str(d)]
    assert cli.main(args, transport=FailsPage2(), now=NOW) == 4
    err = capsys.readouterr().err
    assert "STOPPED" in err and "after cursor 'FAKECURSOR1'" in err and "Re-run the same command" in err
    assert not list(d.glob("metadata_closed_markets_*.json"))  # no snapshot from a failed run
    assert cli.main(args, transport=FakeServer(), now=NOW) == 0  # resumes and finishes


def test_a_torn_last_progress_line_is_dropped_on_resume(tmp_path):
    progress = tmp_path / "progress.jsonl"
    whole = json.dumps({"next_cursor": "FAKECURSOR1", "markets": [{"id": "1"}]})
    progress.write_text(whole + "\n" + '{"next_cursor": "X", "markets": [{"id": "2"')  # killed mid-write
    entries = pm._read_progress(progress)
    assert [e["next_cursor"] for e in entries] == ["FAKECURSOR1"]
    assert progress.read_text() == whole + "\n"
    progress.write_text('{"broken\n' + whole + "\n")
    with pytest.raises(RuntimeError, match="damaged but later pages exist"):
        pm._read_progress(progress)


class _FakeResp:
    def __init__(self, chunks, status=200, error_after=None):
        self.chunks, self.status, self.headers, self.error_after = list(chunks), status, {}, error_after

    def read(self, n=-1):
        if self.error_after is not None and not self.chunks:
            raise self.error_after
        return self.chunks.pop(0) if self.chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeOpener:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.timeouts = resp, exc, []

    def open(self, req, timeout=None):
        self.timeouts.append(timeout)
        if self.exc:
            raise self.exc
        return self.resp


def test_real_transport_has_a_socket_timeout_and_a_whole_request_deadline():
    t = [0.0]

    def clock():
        t[0] += 50.0  # each chunk takes 50 s: a slow trickle
        return t[0]

    opener = _FakeOpener(_FakeResp([b"a" * 100] * 10))
    get = REAL_URLLIB_TRANSPORT(timeout_s=30.0, deadline_s=120.0, opener=opener, clock=clock)
    with pytest.raises(pm.TransientNetworkError) as e:
        get("https://gamma-api.polymarket.com/markets/keyset", {})
    # two 100-byte chunks arrive inside the 120 s deadline; the third check trips it
    assert e.value.kind == "TimeoutError" and e.value.bytes_received == 200 and opener.timeouts == [30.0]
    assert pm.REQUEST_TIMEOUT_S == 30.0 and pm.REQUEST_DEADLINE_S == 120.0


def test_real_transport_turns_read_failures_into_retryable_errors_with_bytes():
    resp = _FakeResp([b"z" * 65536], error_after=http.client.IncompleteRead(b"z" * 100, 5))
    with pytest.raises(pm.TransientNetworkError) as e:
        REAL_URLLIB_TRANSPORT(opener=_FakeOpener(resp))("https://x.test/", {})
    assert e.value.kind == "IncompleteRead" and e.value.bytes_received == 65536 + 100
    for exc, kind in ((ConnectionResetError(54, "reset"), "ConnectionResetError"),
                      (http.client.RemoteDisconnected("closed"), "RemoteDisconnected"),
                      (socket.timeout("timed out"), "TimeoutError"),
                      (urllib.error.URLError(socket.gaierror(8, "nodename")), "URLError(gaierror)")):
        with pytest.raises(pm.TransientNetworkError) as e:
            REAL_URLLIB_TRANSPORT(opener=_FakeOpener(exc=exc))("https://x.test/", {})
        assert e.value.kind == kind


def test_refused_redirects_and_permanent_http_errors_are_not_retried(tmp_path):
    server = Flaky(pm.NetworkRefused("redirect to 'https://elsewhere.example/' refused"), n=10)
    with pytest.raises(pm.NetworkRefused):
        client(tmp_path, server).get(pm.GAMMA_MARKETS, {})
    assert server.calls == 1
    server = Flaky((404, b"not found", {}), n=10)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        client(tmp_path / "x", server).get(pm.GAMMA_MARKETS, {}) if (tmp_path / "x").mkdir() is None else None
    assert server.calls == 1


# ---- streaming count report (offline, for a snapshot too big to load) ------------------- #
def _streamed(raw):
    acc = pm.StreamingCountReport()
    for m in raw:
        acc.add(m)
    return acc.report()


def _same(a, b):
    """Equal, and with the same key order (the printed report is identical)."""
    return json.dumps(a) == json.dumps(b)


def _synthetic_raw(n=4000, seed=7):
    """Fixture markets as templates, with shuffled IDs (duplicates, leading zeros,
    non-numeric, huge), shared events and volumes on and around every threshold."""
    rng = random.Random(seed)
    templates = _raw() + _real_page()["markets"]
    ids = [str(i) for i in range(1, 2500)] + ["007", "7", "abc", "None", "99999999999", "1e3", "٣"]
    vols = [999.99, 1000, 1000.01, 9999, 10000, 100000, 99999.9, 0, None, "12345.5"]
    out = []
    for _ in range(n):
        m = json.loads(json.dumps(rng.choice(templates)))
        m["id"] = rng.choice(ids) if rng.random() < 0.97 else None
        r = rng.random()
        m["events"] = [] if r < 0.1 else [{"id": None}] if r < 0.15 else [{"id": str(rng.randrange(400))}]
        m["volumeNum"] = rng.choice(vols) if rng.random() < 0.3 else 10 ** rng.uniform(2, 5.5)
        m["archived"] = rng.random() < 0.3
        if rng.random() < 0.02:
            m["endDate"] = None
        out.append(m)
    return out


@pytest.mark.parametrize("raw", [_raw(), _real_page()["markets"], _raw() + _real_page()["markets"],
                                 _synthetic_raw(), _synthetic_raw(seed=11)],
                         ids=["fixture", "realformat", "both", "synthetic7", "synthetic11"])
def test_streaming_count_report_is_exactly_the_in_memory_one(raw):
    assert _same(_streamed(raw), pm.count_report(raw))


def test_streaming_report_from_a_snapshot_matches_read_snapshot_at_every_chunk_size(tmp_path):
    snap = tmp_path / "snap.json"
    pm.write_snapshot(_synthetic_raw(), snap)
    whole = pm.read_snapshot(snap)
    expected = pm.count_report(whole)
    for chunk in (1, 7, 333, 1 << 20):
        assert list(pm.iter_snapshot(snap, chunk)) == whole
        digest, rep = pm.count_report_from_snapshot(snap, chunk_chars=chunk)
        assert _same(rep, expected) and digest == snap.with_name("snap.json.sha256").read_text().strip()
    # the synthetic set exercises every path it should
    c = pm.select_markets(whole).counts
    assert c["duplicate_id"] > 0 and c["dropped_one_per_event"] > 0 and c["missing_dates"] > 0
    assert expected["qualifying_one_per_event"][">=100000"] > 0


def test_streaming_snapshot_is_refused_on_a_hash_mismatch_before_any_parsing(tmp_path, monkeypatch):
    snap = tmp_path / "snap.json"
    pm.write_snapshot(_raw(), snap)
    snap.write_text(snap.read_text().replace('"closed":true', '"closed":false', 1))
    monkeypatch.setattr(pm, "iter_snapshot", lambda *a, **k: pytest.fail("parsed before the hash check"))
    with pytest.raises(RuntimeError, match="hash mismatch"):
        pm.count_report_from_snapshot(snap)


@pytest.mark.parametrize("text", ['[{"id":"1"},{"id":"2"}', '[{"id":"1"},{"id":"2', '[{"id":"1"}]x',
                                  '[{"id":"1"},]', '[1]', '{"id":"1"}', ''])
def test_a_truncated_or_malformed_snapshot_is_an_error(tmp_path, text):
    p = tmp_path / "s.json"
    p.write_text(text)
    with pytest.raises(ValueError):
        list(pm.iter_snapshot(p, 3))


def test_empty_snapshot_streams_nothing(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(" [ ] \n")
    assert list(pm.iter_snapshot(p, 2)) == []
    assert _same(_streamed([]), pm.count_report([]))


def test_cli_streams_the_count_offline_and_freezes_nothing(tmp_path, capsys):
    d = tmp_path / "d"
    snap = d / "metadata_closed_markets_X.json"
    raw = _synthetic_raw(seed=3)
    pm.write_snapshot(raw, snap)
    assert _cli().main(["select", "--count-only", "--from-metadata", str(snap), "--data-dir", str(d)],
                       now=NOW) == 0
    out = json.loads(capsys.readouterr().out)
    assert out.pop("offline_from_snapshot") is True and out.pop("snapshot") == str(snap)
    assert out.pop("snapshot_sha256") == (d / "metadata_closed_markets_X.json.sha256").read_text().strip()
    assert out == pm.count_report(pm.read_snapshot(snap))
    assert not (d / "frozen_market_list.json").exists() and not list(d.glob("*.outcomes.json"))
    assert not (d / "request_log.jsonl").exists()


# ---- streamed freeze (select from a snapshot without loading it) ------------------------ #
def _select_markets_reference(raw, min_volume=pm.MIN_FINAL_VOLUME_USDC):
    """VERBATIM copy of select_markets as committed in ffae1f5 (in memory: every ID in
    a set, every volume in a list, every eligible market kept). The compact one-pass
    version must give exactly this."""
    counts = {k: 0 for k in (
        "raw", "duplicate_id", "not_closed", "multi_outcome", "two_named_outcomes_not_yes_no",
        "missing_token_ids", "void_50_50", "near_0_1_not_exact", "interior_final_price", "malformed_prices",
        "missing_dates", "below_min_volume", "no_decision_window",
        "closed_before_decision", "eligible_before_event_choice", "dropped_one_per_event", "selected", "archived_selected")}
    seen, eligible = set(), []
    volumes = []
    outcomes = {}
    for m in raw:
        counts["raw"] += 1
        mid = str(m.get("id"))
        if mid in seen:
            counts["duplicate_id"] += 1
            continue
        seen.add(mid)
        if not m.get("closed"):
            counts["not_closed"] += 1
            continue
        names = pm._json_list(m.get("outcomes"))
        if not names or len(names) != 2:
            counts["multi_outcome"] += 1
            continue
        if [str(n).strip().lower() for n in names] != ["yes", "no"]:
            counts["two_named_outcomes_not_yes_no"] += 1
            continue
        tokens = pm._json_list(m.get("clobTokenIds"))
        if not tokens or len(tokens) != 2:
            counts["missing_token_ids"] += 1
            continue
        res = pm._resolution(pm._json_list(m.get("outcomePrices")))
        if res == "void":
            counts["void_50_50"] += 1
            continue
        if res not in ("yes", "no"):
            counts[res] += 1
            continue
        start = pm.parse_time(m.get("startDate") or m.get("createdAt"))
        end = pm.parse_time(m.get("endDate"))
        closed = pm.parse_time(m.get("closedTime"))
        if start is None or end is None or closed is None:
            counts["missing_dates"] += 1
            continue
        volume = float(m.get("volumeNum") or 0.0)
        volumes.append(volume)
        if volume < min_volume:
            counts["below_min_volume"] += 1
            continue
        td = pm.decision_time(mid, start, end)
        if td is None:
            counts["no_decision_window"] += 1
            continue
        if closed <= td:
            counts["closed_before_decision"] += 1
            continue
        events = m.get("events") or []
        event_id = str(events[0].get("id")) if events and events[0].get("id") is not None else f"market:{mid}"
        eligible.append(pm.SelectedMarket(
            market_id=mid, event_id=event_id, yes_token_id=str(tokens[0]), question=str(m.get("question") or ""),
            start=start.isoformat(), end=end.isoformat(), closed_time=closed.isoformat(),
            decision_time=td.isoformat(), final_volume=volume, archived=bool(m.get("archived"))))
        outcomes[mid] = 1 if res == "yes" else 0
    counts["eligible_before_event_choice"] = len(eligible)
    chosen = {}
    for s in eligible:
        cur = chosen.get(s.event_id)
        if cur is None or pm._unit(pm.EVENT_CHOICE_SEED, s.market_id) < pm._unit(pm.EVENT_CHOICE_SEED, cur.market_id):
            chosen[s.event_id] = s
    selected = sorted(chosen.values(), key=lambda s: s.market_id)
    counts["dropped_one_per_event"] = len(eligible) - len(selected)
    counts["selected"] = len(selected)
    counts["archived_selected"] = sum(s.archived for s in selected)
    sens = {f">={v:g}": sum(x >= v for x in volumes) for v in (*pm.VOLUME_SENSITIVITY_USDC, min_volume)}
    return pm.Selection(pm.selection_params(min_volume), selected,
                        {s.market_id: outcomes[s.market_id] for s in selected}, counts, sens)


def _same_selection(a, b):
    return (a.params == b.params and a.markets == b.markets and _same(a.outcomes, b.outcomes)
            and _same(a.counts, b.counts) and _same(a.volume_sensitivity, b.volume_sensitivity)
            and pm.frozen_hash(pm._frozen_payload(a)) == pm.frozen_hash(pm._frozen_payload(b)))


@pytest.mark.parametrize("min_volume", [1000.0, 10000.0, 12345.5, 100000.0, 0.0])
@pytest.mark.parametrize("raw", [_raw(), _real_page()["markets"], _synthetic_raw(), _synthetic_raw(seed=11)],
                         ids=["fixture", "realformat", "synthetic7", "synthetic11"])
def test_compact_select_markets_is_exactly_the_in_memory_reference(raw, min_volume):
    new = pm.select_markets(iter(raw), min_volume)  # a one-shot stream is enough
    assert _same_selection(new, _select_markets_reference(raw, min_volume))


def test_select_from_snapshot_streams_one_pass_and_matches_the_in_memory_freeze(tmp_path):
    snap = tmp_path / "snap.json"
    pm.write_snapshot(_synthetic_raw(seed=5), snap)
    whole = pm.read_snapshot(snap)
    ref = _select_markets_reference(whole)
    for chunk in (1, 97, 1 << 20):
        digest, sel, report = pm.select_from_snapshot(snap, chunk_chars=chunk)
        assert _same_selection(sel, ref) and _same(report, pm.count_report(whole))
        assert digest == (tmp_path / "snap.json.sha256").read_text().strip()
    assert sel.counts["selected"] > 50 and sel.counts["dropped_one_per_event"] > 0


def test_cli_freeze_from_snapshot_is_streamed_and_freezes_the_same_list(tmp_path, capsys, monkeypatch):
    d = tmp_path / "d"
    snap = d / "metadata_closed_markets_X.json"
    pm.write_snapshot(_synthetic_raw(seed=5), snap)
    whole = pm.read_snapshot(snap)
    expected = pm.freeze_selection(_select_markets_reference(whole), tmp_path / "ref" / "frozen.json")
    monkeypatch.setattr(pm, "read_snapshot", lambda *a, **k: pytest.fail("the freeze path loaded the snapshot"))
    assert _cli().main(["select", "--from-metadata", str(snap), "--data-dir", str(d)], now=NOW) == 0
    out = json.loads(capsys.readouterr().out)
    assert out.pop("frozen_sha256") == expected and out.pop("from_snapshot") == str(snap)
    assert out.pop("snapshot_sha256") == (d / "metadata_closed_markets_X.json.sha256").read_text().strip()
    assert out == pm.count_report(whole)
    frozen, digest = pm.load_frozen(d / "frozen_market_list.json")
    assert digest == expected
    assert (d / "frozen_market_list.json.outcomes.json").read_text() == \
        (tmp_path / "ref" / "frozen.json.outcomes.json").read_text()
    assert not (d / "request_log.jsonl").exists()


def test_cli_freeze_refuses_a_snapshot_with_a_bad_hash_and_writes_nothing(tmp_path, capsys):
    d = tmp_path / "d"
    snap = d / "s.json"
    pm.write_snapshot(_raw(), snap)
    snap.write_text(snap.read_text().replace('"closed":true', '"closed":false', 1))
    with pytest.raises(RuntimeError, match="hash mismatch"):
        _cli().main(["select", "--from-metadata", str(snap), "--data-dir", str(d)], now=NOW)
    assert not (d / "frozen_market_list.json").exists() and not list(d.glob("*.outcomes.json"))


# ---- pool order and fill (FINAL 2026-10-16): blind to outcomes and prices --------------- #
def test_final_split_and_sample_parameters_are_pinned():
    assert pm.SPLIT_CUTOFF == datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert pm.SPLIT_GAP == timedelta(days=7)
    assert pm.TEST_DECISION_END == datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert pm.SAMPLE_ORDER_SEED == "flyshi-phase2-sample-20261016"
    assert pm.POOL_NEED == {"train": 2800, "test": 7200}  # 40 chains x 70 and x 180
    assert pm.pool_targets() == {"train": 3220, "test": 8280}  # +15%, integer arithmetic
    assert pm.pool_targets({"x": 7}, 15) == {"x": 9}  # rounded up


def _sm(i, closed, td, **kw):
    """A frozen market with the given close and decision times (UTC ISO strings)."""
    base = dict(market_id=str(i), event_id=f"e{i}", yes_token_id=f"tok{i}", question=f"q{i}",
                start="2025-01-01T00:00:00+00:00", end="2027-01-01T00:00:00+00:00", closed_time=closed,
                decision_time=td, final_volume=20000.0, archived=False)
    return pm.SelectedMarket(**{**base, **kw})


def _frozen_world(n=600, seed=1):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        td = pm.SPLIT_CUTOFF + timedelta(days=rng.uniform(-300, 250))
        closed = td + timedelta(days=rng.uniform(0.01, 60))
        out.append(_sm(1000 + i, closed.isoformat(), td.isoformat()))
    return out


def _fake_history(m, price=0.42, kind=None):
    """Hourly points over [t_d - 3 d, t_d); some markets get an unusable history."""
    td = int(pm.parse_time(m.decision_time).timestamp())
    kind = kind or ("ok", "ok", "ok", "none", "stale", "short")[int(m.market_id) % 6]
    if kind == "none":
        return []
    if kind == "stale":
        return [(td - 30 * 3600 - h * 3600, price) for h in range(10)]
    if kind == "short":
        return [(td - h * 3600, price) for h in range(1, 10)]
    return [(td - h * 3600, price) for h in range(1, 72)]


def test_pool_of_is_the_split_rule_of_split_train_test():
    frozen = _frozen_world()
    built = [pm.BuiltMarket(m, pm.Features(0.5, 0.0, 1.0, 0), 0) for m in frozen]
    train, test, counts = pm.split_train_test(built, pm.SPLIT_CUTOFF, pm.SPLIT_GAP, pm.TEST_DECISION_END)
    pools = {m.market_id: pm.pool_of(m) for m in frozen}
    assert {b.market.market_id for b in train} == {k for k, v in pools.items() if v == "train"}
    assert {b.market.market_id for b in test} == {k for k, v in pools.items() if v == "test"}
    assert counts["straddling_excluded"] == sum(v == "straddling" for v in pools.values()) > 0
    assert counts["after_test_window_excluded"] == sum(v == "after_test_window" for v in pools.values()) > 0
    # without test_end the split is unchanged from before (no new count)
    assert set(pm.split_train_test(built, pm.SPLIT_CUTOFF)[2]) == {"train", "test", "straddling_excluded"}


def test_boundaries_of_the_pools():
    c, g, e = pm.SPLIT_CUTOFF, pm.SPLIT_GAP, pm.TEST_DECISION_END
    iso = lambda t: t.isoformat()
    second = timedelta(seconds=1)
    assert pm.pool_of(_sm(1, iso(c - second), iso(c - 2 * second))) == "train"
    assert pm.pool_of(_sm(2, iso(c), iso(c - second))) == "straddling"  # resolved AT the cutoff
    assert pm.pool_of(_sm(3, iso(c + g + 9 * second), iso(c + g - second))) == "straddling"
    assert pm.pool_of(_sm(4, iso(c + g + 9 * second), iso(c + g))) == "test"
    assert pm.pool_of(_sm(5, iso(e + 9 * second), iso(e - second))) == "test"
    assert pm.pool_of(_sm(6, iso(e + 9 * second), iso(e))) == "after_test_window"


def test_pool_order_is_the_seeded_hash_of_the_id_and_nothing_else():
    import hashlib
    frozen = _frozen_world()
    pools, counts = pm.pool_order(frozen)
    for p in pm.POOLS:
        ids = [m.market_id for m in pools[p]]
        assert ids == sorted(ids, key=lambda i: hashlib.sha256(f"flyshi-phase2-sample-20261016|{i}".encode()).digest())
    assert sum(counts.values()) == len(frozen)
    # input order, question, token, volume, event and archived flag change nothing
    rng = random.Random(3)
    other = [pm.SelectedMarket(**{**m.__dict__, "question": "x", "yes_token_id": "y", "event_id": "z",
                                  "final_volume": rng.random() * 1e6, "archived": True})
             for m in rng.sample(frozen, len(frozen))]
    pools2, _ = pm.pool_order(other)
    assert all([m.market_id for m in pools[p]] == [m.market_id for m in pools2[p]] for p in pm.POOLS)
    # a different seed gives a different order
    assert [m.market_id for m in pm.pool_order(frozen, seed="other")[0]["test"]] != \
        [m.market_id for m in pools["test"]]


def test_history_exclusion_matches_decision_features_on_random_histories():
    rng = random.Random(9)
    td = datetime(2026, 5, 1, 12, tzinfo=timezone.utc)
    for _ in range(500):
        t0 = int(td.timestamp())
        hist = [(t0 + rng.randint(-4 * 86400, 86400), rng.random()) for _ in range(rng.randint(0, 6))]
        features, why = pm.decision_features(hist, td, td + timedelta(days=30))
        assert pm.history_exclusion([t for t, _ in hist], td) == why


def test_fill_stops_at_the_target_walks_in_order_and_resumes_without_refetching():
    frozen = _frozen_world()
    calls = []

    def fetch(m):
        calls.append(m.market_id)
        return _fake_history(m)

    targets = {"train": 40, "test": 55}
    plan = pm.fill_pools(frozen, fetch, targets=targets)
    pools, _ = pm.pool_order(frozen)
    for p in pm.POOLS:
        x = plan["pools"][p]
        assert x["reached"] and x["usable"] == targets[p] == len(x["usable_ids"])
        walked = [m.market_id for m in pools[p]][:x["considered"]]
        assert x["usable_ids"] == [i for i in walked if pm.history_exclusion(
            [t for t, _ in _fake_history(next(m for m in frozen if m.market_id == i))],
            pm.parse_time(next(m for m in frozen if m.market_id == i).decision_time)) is None]
        assert pm.history_exclusion([t for t, _ in _fake_history(pools[p][x["considered"] - 1])],
                                    pm.parse_time(pools[p][x["considered"] - 1].decision_time)) is None  # stops on a usable one
        assert set(x["excluded_by_reason"]) <= {"no_price_before_decision", "stale_price", "no_price_before_window"}
        assert x["considered"] == x["usable"] + sum(x["excluded_by_reason"].values())
    assert calls == [m.market_id for p in pm.POOLS for m in pools[p][:plan["pools"][p]["considered"]]]
    # resume after an interruption: what was fetched is reused, the rest continues in order
    half = calls[: len(calls) // 2]
    have = {i: _fake_history(next(m for m in frozen if m.market_id == i)) for i in half}
    calls.clear()
    again = pm.fill_pools(frozen, fetch, have, targets=targets)
    assert calls and not set(calls) & set(half)
    for p in pm.POOLS:
        again["pools"][p].pop("fetched_now"), plan["pools"][p].pop("fetched_now")
    assert again == plan


def test_fill_reports_a_pool_that_runs_out():
    frozen = _frozen_world(60)
    plan = pm.fill_pools(frozen, _fake_history, targets={"train": 1000, "test": 1000})
    for p in pm.POOLS:
        x = plan["pools"][p]
        assert not x["reached"] and x["considered"] == x["pool_size"] > 0


def test_fill_is_blind_to_prices_and_outcomes():
    """Every price value changed, and every outcome flipped before selection: the
    same markets are fetched, in the same order, and the same ones are usable."""
    frozen = _frozen_world()
    targets = {"train": 30, "test": 45}
    base = pm.fill_pools(frozen, _fake_history, targets=targets)
    rng = random.Random(5)
    repriced = pm.fill_pools(frozen, lambda m: [(t, rng.random()) for t, _ in _fake_history(m)], targets=targets)
    assert repriced == base
    import inspect
    assert not any("outcome" in name for name in inspect.signature(pm.fill_pools).parameters)
    raw = _synthetic_raw(seed=5)
    flipped = json.loads(json.dumps(raw))
    for m in flipped:
        if m["outcomePrices"] in ('["1", "0"]', '["0", "1"]'):
            m["outcomePrices"] = '["0", "1"]' if m["outcomePrices"] == '["1", "0"]' else '["1", "0"]'
    a, b = pm.select_markets(raw), pm.select_markets(flipped)
    assert a.outcomes != b.outcomes
    kw = dict(targets={"train": 5, "test": 5}, cutoff=pm.parse_time("2025-04-01T00:00:00Z"), test_end=None)
    assert pm.fill_pools(a.markets, _fake_history, **kw) == pm.fill_pools(b.markets, _fake_history, **kw)


def test_list_query_parameters_repeat_their_key_and_scalar_urls_are_unchanged(tmp_path):
    server = FakeServer()
    c = client(tmp_path, server)
    c.get(pm.GAMMA_MARKETS, {"closed": "true", "limit": 100})
    c.get(pm.GAMMA_MARKETS, {"closed": "any", "id": ["12", "1", "17"], "limit": 100})
    assert server.calls[0][0] == "https://gamma-api.polymarket.com/markets/keyset?closed=true&limit=100"
    assert server.calls[1][0] == ("https://gamma-api.polymarket.com/markets/keyset"
                                  "?closed=any&id=12&id=1&id=17&limit=100")


def test_history_exclusion_ignores_a_point_exactly_at_the_decision_time():
    td = datetime(2026, 5, 1, 12, tzinfo=timezone.utc)
    t0 = int(td.timestamp())
    assert pm.history_exclusion([t0], td) == "no_price_before_decision"
    assert pm.history_exclusion([t0, t0 - 30 * 3600], td) == "stale_price"
    assert pm.history_exclusion([t0 - 3600, t0 - 24 * 3600], td) is None
    assert pm.history_exclusion([t0 - 3600, t0 - 24 * 3600 + 1], td) == "no_price_before_window"


# ---- archived check (one Gamma identifier lookup; never sent by a test) ----------------- #
def _archived_cli():
    spec = importlib.util.spec_from_file_location("archived_check_test", REPO / "repro" / "polymarket" / "archived_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LookupServer:
    def __init__(self, markets):
        self.markets, self.calls = markets, []

    def __call__(self, url, headers):
        self.calls.append(url)
        return 200, json.dumps({"markets": self.markets, "next_cursor": None}).encode(), {}


def _market(i, closed=True, archived=False):
    return {"id": str(i), "closed": closed, "archived": archived, "active": True,
            "outcomePrices": '["1", "0"]', "lastTradePrice": 0.99, "question": "SECRET"}


def test_archived_check_is_one_gated_identifier_lookup_and_prints_no_price(tmp_path, monkeypatch, capsys):
    ac = _archived_cli()
    assert len(ac.PROBE_IDS) == 98 and len(set(ac.PROBE_IDS) | set(ac.CONTROL_IDS)) == 100
    d = tmp_path / "d"
    server = LookupServer([_market(12), _market(17), _market(3, archived=True)])
    assert ac.main(["--data-dir", str(d)], transport=server) == 2  # no flag, no permission
    p = _perm_file(tmp_path, endpoints=(pm.GAMMA_MARKETS,))
    args = ["--allow-network", "--permission", str(p), "--data-dir", str(d)]
    assert ac.main(args, transport=server, now=NOW) == 2  # no terms check yet
    assert server.calls == []
    terms = _fake_terms(tmp_path, monkeypatch)
    _cli().main(["terms", "--terms-file", str(terms), "--data-dir", str(d)], now=NOW)
    capsys.readouterr()
    assert ac.main(args, transport=server, now=NOW) == 0
    assert len(server.calls) == 1
    url = server.calls[0]
    assert url.startswith("https://gamma-api.polymarket.com/markets/keyset?closed=any&id=1&id=2&")
    assert url.endswith("&id=151&id=12&id=17&limit=100")
    out = capsys.readouterr().out
    assert "LISTING EXCLUDES ARCHIVED" in out
    assert "price" not in out.lower() and "SECRET" not in out
    assert json.loads((d / "request_log.jsonl").read_text().splitlines()[-1])["url"] == url


@pytest.mark.parametrize("markets,expect", [
    ([_market(12), _market(17)], "NOT SERVED EVEN BY ID"),
    ([_market(12), _market(17), _market(5)], "LISTING MISSED CLOSED"),
    ([_market(12), _market(17), _market(5, closed=False)], "PROBES RETURNED AS OPEN"),
    ([_market(5, archived=True)], "INCONCLUSIVE"),
])
def test_archived_check_verdicts(markets, expect):
    assert _archived_cli().verdict(markets).startswith(expect)


def test_the_recorded_clob_permission_covers_prices_history_only_at_a_safe_rate():
    path = REPO / "repro" / "polymarket" / "permissions" / "clob_prices_history_20261016.json"
    perm = pm.Permission.load(path)
    assert [e.endpoint for e in perm.endpoints] == [pm.CLOB_PRICES_HISTORY]
    assert perm.endpoints[0].published_rate == 100.0  # /prices-history 1,000 req / 10 s
    raw = json.loads(path.read_text())
    basis = raw["endpoints"][0]["basis"]
    assert "Roni" in basis and "2026-10-15" in basis and "NOT a formal written confirmation" in basis
    assert "1a238b502342564ff0afb087a725aad2bf16e5fa5978d19bcf414ea81d2a84a5" in raw["endpoints"][0]["published_limit"]["source"]
    ours = raw["endpoints"][0]["our_rate_requests_per_second"]
    assert ours <= pm.RATE_FRACTION * perm.endpoints[0].published_rate
    pm.NetworkPolicy(True, perm, ours).check(pm.CLOB_PRICES_HISTORY)
    with pytest.raises(pm.NetworkRefused, match="does not cover"):
        pm.NetworkPolicy(True, perm, ours).check(pm.GAMMA_MARKETS)
    with pytest.raises(pm.NetworkRefused, match="exceeds"):
        pm.NetworkPolicy(True, perm, 26.0).check(pm.CLOB_PRICES_HISTORY)
