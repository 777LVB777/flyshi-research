"""Polymarket historical loader for the Phase 2 replay (DRAFT design).

Spec: docs/design/phase2-design.md, Section 10 (decisions of 2026-10-12) and the
binding conditions in Section 1. Pure Python; importing it makes no network request.

Network safety (Section 1, conditions 1-6):

* Off by default. A request is made only when BOTH ``allow_network`` is true (the
  CLI's ``--allow-network``) AND a recorded permission file lists that exact
  endpoint. Without both, :class:`NetworkPolicy` refuses before any transport runs.
* Only two endpoints exist in code (condition 1): Gamma ``GET /markets/keyset`` and
  CLOB ``GET /prices-history``. A permission file cannot add others.
* GET only, https only, no redirects, no cookies, no authentication, key or wallet.
* A pre-set request rate, at most ``RATE_FRACTION`` of the published limit recorded
  in the permission file, with a JSON-lines request log of every request.
* Raw responses are stored privately (never redistributed; condition 6).

Pipeline (each step a pure function, tested on recorded fake responses):
``fetch_closed_markets`` -> ``select_markets`` (binary, resolved, one per event,
final-volume threshold, decision time drawn) -> ``freeze_selection`` (SHA-256) ->
``fetch_price_history`` (window ending at the decision time) -> ``decision_features``
(strictly before the decision time) -> ``split_train_test`` -> ``write_market_file``
(the ``simulator.Market`` fields the synthetic runner consumes).
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from flyshi_research.simulator import Market

# ---- endpoints (condition 1) ------------------------------------------------------- #
GAMMA_MARKETS = "GET https://gamma-api.polymarket.com/markets/keyset"
CLOB_PRICES_HISTORY = "GET https://clob.polymarket.com/prices-history"
ALLOWED_ENDPOINTS = (GAMMA_MARKETS, CLOB_PRICES_HISTORY)

#: the configured rate may use at most this fraction of the published limit
RATE_FRACTION = 0.25
#: default pre-set rate: one request every 2 s (0.5 req/s)
DEFAULT_REQUESTS_PER_SECOND = 0.5
MAX_RETRIES_429 = 5
GAMMA_PAGE_LIMIT = 100  # the documented maximum for /markets/keyset

# ---- pre-stated selection and feature parameters (PROPOSED 2026-10-12) ------------- #
#: final traded volume (USDC, Gamma ``volumeNum``) a market needs to be selected.
#: SELECTION ONLY, never an input (decision 3).
MIN_FINAL_VOLUME_USDC = 10_000.0
#: counts also reported at these thresholds (counts only; selection uses the one above)
VOLUME_SENSITIVITY_USDC = (1_000.0, 100_000.0)
#: decision time: seeded uniform draw over the scheduled life, minus these margins
DECISION_MARGIN = timedelta(hours=24)
DECISION_TIME_SEED = "flyshi-phase2-td-20261012"
EVENT_CHOICE_SEED = "flyshi-phase2-event-20261012"
#: recent_change window, and the largest allowed age of the price at t_d
RECENT_CHANGE_WINDOW = timedelta(hours=24)
MAX_PRICE_STALENESS = timedelta(hours=24)
#: price-history request: this much history before t_d, at this resolution (minutes)
HISTORY_LOOKBACK = timedelta(days=3)
HISTORY_FIDELITY_MIN = 60
#: train/test split: training markets resolved before the cutoff; test markets
#: decided at least this long after it
DEFAULT_SPLIT_GAP = timedelta(days=7)
#: held at the encoder midpoint (decisions 1 and 3)
SIGNAL_MIDPOINT = 0.5
LIQUIDITY_MIDPOINT = 0.5
MARKET_FILE_FORMAT = "flyshi.simulator.Market/v1"


class NetworkRefused(RuntimeError):
    """A request was refused before any transport ran."""


# --------------------------------------------------------------------------- #
# permission and policy
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EndpointPermission:
    endpoint: str
    basis: str
    published_requests: float
    published_per_seconds: float
    limit_source: str

    @property
    def published_rate(self) -> float:
        return self.published_requests / self.published_per_seconds


@dataclass(frozen=True)
class Permission:
    recorded_on: str
    recorded_by: str
    endpoints: Tuple[EndpointPermission, ...]

    @classmethod
    def load(cls, path: Path) -> "Permission":
        d = json.loads(Path(path).read_text())
        eps = []
        for e in d["endpoints"]:
            lim = e["published_limit"]
            eps.append(EndpointPermission(e["endpoint"], e["basis"], float(lim["requests"]),
                                          float(lim["per_seconds"]), lim["source"]))
        if not d.get("recorded_on") or not d.get("recorded_by"):
            raise ValueError("permission file must record recorded_on and recorded_by")
        return cls(d["recorded_on"], d["recorded_by"], tuple(eps))

    def covers(self, endpoint: str) -> Optional[EndpointPermission]:
        return next((e for e in self.endpoints if e.endpoint == endpoint), None)


@dataclass(frozen=True)
class NetworkPolicy:
    """Refuses every request unless network is allowed AND the endpoint is permitted."""

    allow_network: bool = False
    permission: Optional[Permission] = None
    requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND

    def check(self, endpoint: str) -> EndpointPermission:
        if endpoint not in ALLOWED_ENDPOINTS:
            raise NetworkRefused(f"{endpoint!r} is not one of the allowed endpoints {ALLOWED_ENDPOINTS}")
        if not self.allow_network:
            raise NetworkRefused("network is disabled (pass --allow-network)")
        if self.permission is None:
            raise NetworkRefused("no permission file recorded")
        grant = self.permission.covers(endpoint)
        if grant is None:
            raise NetworkRefused(f"the permission file does not cover {endpoint!r}")
        if not 0 < self.requests_per_second <= RATE_FRACTION * grant.published_rate:
            raise NetworkRefused(
                f"rate {self.requests_per_second:g}/s exceeds {RATE_FRACTION:g} x the published "
                f"limit {grant.published_rate:g}/s for {endpoint!r}")
        return grant


# --------------------------------------------------------------------------- #
# transport and client
# --------------------------------------------------------------------------- #
#: transport(url, headers) -> (status, body bytes, response headers)
Transport = Callable[[str, Mapping[str, str]], Tuple[int, bytes, Mapping[str, str]]]
REQUEST_HEADERS = {"User-Agent": "flyshi-research/0.1 (non-commercial research; read-only)",
                   "Accept": "application/json"}
_FORBIDDEN_HEADERS = ("authorization", "cookie", "poly_address", "poly_signature", "poly_api_key",
                      "poly_passphrase", "poly_timestamp", "x-api-key")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise NetworkRefused(f"redirect to {newurl!r} refused")


def urllib_transport(timeout_s: float = 30.0) -> Transport:
    """The real transport: https GET, no redirects, no cookie jar, no proxy auth."""
    opener = urllib.request.build_opener(_NoRedirect())

    def get(url: str, headers: Mapping[str, str]):
        req = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            with opener.open(req, timeout=timeout_s) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as err:
            return err.code, err.read(), dict(err.headers or {})

    return get


class PolymarketClient:
    """Read-only GET client. Every request passes the policy, the rate limit and the log."""

    def __init__(self, policy: NetworkPolicy, transport: Optional[Transport], log_path: Path,
                 raw_dir: Optional[Path] = None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 wallclock: Callable[[], float] = time.time) -> None:
        self.policy, self.log_path, self.raw_dir = policy, Path(log_path), raw_dir
        self.clock, self.sleep, self.wallclock = clock, sleep, wallclock
        self._transport = transport
        self._last: Optional[float] = None
        self.requests = 0

    def get(self, endpoint: str, params: Mapping[str, object]) -> object:
        self.policy.check(endpoint)  # refuses before anything else happens
        if self._transport is None:
            self._transport = urllib_transport()
        base = endpoint.split(" ", 1)[1]
        url = base + ("?" + urllib.parse.urlencode(sorted((k, str(v)) for k, v in params.items()))
                      if params else "")
        if not url.startswith("https://"):
            raise NetworkRefused("https only")
        if any(h.lower() in _FORBIDDEN_HEADERS for h in REQUEST_HEADERS):
            raise NetworkRefused("authentication headers are never sent")
        for attempt in range(MAX_RETRIES_429 + 1):
            self._throttle()
            status, body, _ = self._transport(url, REQUEST_HEADERS)
            self.requests += 1
            self._log(endpoint, url, status, body, attempt)
            if status == 429 and attempt < MAX_RETRIES_429:
                self.sleep(min(60.0, 2.0 ** (attempt + 1)))
                continue
            if status != 200:
                raise RuntimeError(f"HTTP {status} for {url}")
            if self.raw_dir is not None:
                self._store_raw(url, body)
            return json.loads(body)
        raise RuntimeError(f"rate limited after {MAX_RETRIES_429} retries: {url}")

    def _throttle(self) -> None:
        interval = 1.0 / self.policy.requests_per_second
        if self._last is not None:
            wait = self._last + interval - self.clock()
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()

    def _log(self, endpoint: str, url: str, status: int, body: bytes, attempt: int) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"utc": datetime.fromtimestamp(self.wallclock(), timezone.utc).isoformat(),
                 "endpoint": endpoint, "url": url, "status": status, "bytes": len(body),
                 "sha256": hashlib.sha256(body).hexdigest(), "attempt": attempt}
        with open(self.log_path, "a") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    def _store_raw(self, url: str, body: bytes) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        (self.raw_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")).write_bytes(body)


# --------------------------------------------------------------------------- #
# metadata fetch and selection
# --------------------------------------------------------------------------- #
def fetch_closed_markets(client: PolymarketClient, max_pages: Optional[int] = None) -> List[dict]:
    """Every closed market, archived included, by keyset paging (no volume filter, so
    the excluded markets can be counted)."""
    markets: List[dict] = []
    cursor: Optional[str] = None
    pages = 0
    while max_pages is None or pages < max_pages:
        params: Dict[str, object] = {"closed": "true", "limit": GAMMA_PAGE_LIMIT}
        if cursor:
            params["after_cursor"] = cursor
        page = client.get(GAMMA_MARKETS, params)
        markets.extend(page.get("markets") or [])
        pages += 1
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return markets


def parse_time(value: Optional[str]) -> Optional[datetime]:
    """Gamma timestamps: ISO 8601 ('...Z' or '+00:00') or '2024-01-01 12:00:00+00'."""
    if not value:
        return None
    v = str(value).strip().replace(" ", "T")
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    elif len(v) >= 3 and v[-3] in "+-" and v[-2:].isdigit():
        v = v + ":00"
    t = datetime.fromisoformat(v)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _json_list(value) -> Optional[list]:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    try:
        out = json.loads(value)
    except (TypeError, ValueError):
        return None
    return out if isinstance(out, list) else None


def _unit(seed: str, key: str) -> float:
    digest = hashlib.sha256(f"{seed}|{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def decision_time(market_id: str, start: datetime, end: datetime) -> Optional[datetime]:
    """Seeded uniform draw over [start + 24 h, end - 24 h] of the SCHEDULED life.
    Uses only the market ID and the listed dates: never the outcome, the price or the
    actual close time. None if the window is empty."""
    lo, hi = start + DECISION_MARGIN, end - DECISION_MARGIN
    if hi <= lo:
        return None
    seconds = math.floor(_unit(DECISION_TIME_SEED, market_id) * (hi - lo).total_seconds())
    return lo + timedelta(seconds=seconds)


@dataclass(frozen=True)
class SelectedMarket:
    market_id: str
    event_id: str
    yes_token_id: str
    question: str
    start: str
    end: str
    closed_time: str
    decision_time: str
    final_volume: float
    archived: bool


@dataclass
class Selection:
    params: dict
    markets: List[SelectedMarket]
    outcomes: Dict[str, int]  # kept apart from the frozen list; joined only at build time
    counts: Dict[str, int] = field(default_factory=dict)
    volume_sensitivity: Dict[str, int] = field(default_factory=dict)


def _resolution(prices: Optional[list]) -> Optional[str]:
    """'yes', 'no', 'void' (50/50) or None (anything else)."""
    if not prices or len(prices) != 2:
        return None
    try:
        a, b = (float(x) for x in prices)
    except (TypeError, ValueError):
        return None
    if (a, b) == (1.0, 0.0):
        return "yes"
    if (a, b) == (0.0, 1.0):
        return "no"
    if (a, b) == (0.5, 0.5):
        return "void"
    return None


def selection_params(min_volume: float = MIN_FINAL_VOLUME_USDC) -> dict:
    return {"min_final_volume_usdc": min_volume, "decision_margin_hours": DECISION_MARGIN.total_seconds() / 3600,
            "decision_time_seed": DECISION_TIME_SEED, "event_choice_seed": EVENT_CHOICE_SEED,
            "binary": "outcomes exactly ['Yes','No'] with two CLOB token IDs",
            "resolved": "closed and outcomePrices exactly (1,0) or (0,1); (0.5,0.5) counted as void",
            "one_per_event": "lowest sha256(event_choice_seed|market_id) within the event"}


def select_markets(raw: Iterable[Mapping], min_volume: float = MIN_FINAL_VOLUME_USDC) -> Selection:
    """Resolved binary markets, final volume >= ``min_volume``, one market per event.
    Every exclusion is counted; archived markets are included and counted."""
    counts: Dict[str, int] = {k: 0 for k in (
        "raw", "duplicate_id", "not_closed", "not_binary", "missing_token_ids", "void_50_50",
        "unresolved_or_ambiguous", "missing_dates", "below_min_volume", "no_decision_window",
        "closed_before_decision", "eligible_before_event_choice", "dropped_one_per_event", "selected", "archived_selected")}
    seen, eligible = set(), []
    volumes: List[float] = []
    outcomes: Dict[str, int] = {}
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
        names = _json_list(m.get("outcomes"))
        if not names or [str(n).lower() for n in names] != ["yes", "no"]:
            counts["not_binary"] += 1
            continue
        tokens = _json_list(m.get("clobTokenIds"))
        if not tokens or len(tokens) != 2:
            counts["missing_token_ids"] += 1
            continue
        res = _resolution(_json_list(m.get("outcomePrices")))
        if res == "void":
            counts["void_50_50"] += 1
            continue
        if res is None:
            counts["unresolved_or_ambiguous"] += 1
            continue
        start = parse_time(m.get("startDate") or m.get("createdAt"))
        end = parse_time(m.get("endDate"))
        closed = parse_time(m.get("closedTime"))
        if start is None or end is None or closed is None:
            counts["missing_dates"] += 1
            continue
        volume = float(m.get("volumeNum") or 0.0)
        volumes.append(volume)
        if volume < min_volume:
            counts["below_min_volume"] += 1
            continue
        td = decision_time(mid, start, end)
        if td is None:
            counts["no_decision_window"] += 1
            continue
        if closed <= td:  # not open at t_d, so not available to a trader then (counted)
            counts["closed_before_decision"] += 1
            continue
        events = m.get("events") or []
        event_id = str(events[0].get("id")) if events and events[0].get("id") is not None else f"market:{mid}"
        eligible.append(SelectedMarket(
            market_id=mid, event_id=event_id, yes_token_id=str(tokens[0]), question=str(m.get("question") or ""),
            start=start.isoformat(), end=end.isoformat(), closed_time=closed.isoformat(),
            decision_time=td.isoformat(), final_volume=volume, archived=bool(m.get("archived"))))
        outcomes[mid] = 1 if res == "yes" else 0
    counts["eligible_before_event_choice"] = len(eligible)
    chosen: Dict[str, SelectedMarket] = {}
    for s in eligible:  # outcome-blind and price-blind choice
        cur = chosen.get(s.event_id)
        if cur is None or _unit(EVENT_CHOICE_SEED, s.market_id) < _unit(EVENT_CHOICE_SEED, cur.market_id):
            chosen[s.event_id] = s
    selected = sorted(chosen.values(), key=lambda s: s.market_id)
    counts["dropped_one_per_event"] = len(eligible) - len(selected)
    counts["selected"] = len(selected)
    counts["archived_selected"] = sum(s.archived for s in selected)
    sens = {f">={v:g}": sum(x >= v for x in volumes) for v in (*VOLUME_SENSITIVITY_USDC, min_volume)}
    return Selection(selection_params(min_volume), selected,
                     {s.market_id: outcomes[s.market_id] for s in selected}, counts, sens)


# --------------------------------------------------------------------------- #
# freezing
# --------------------------------------------------------------------------- #
def _frozen_payload(sel: Selection) -> dict:
    return {"params": sel.params, "markets": [asdict(m) for m in sel.markets], "counts": sel.counts,
            "volume_sensitivity": sel.volume_sensitivity}


def frozen_hash(payload: Mapping) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def freeze_selection(sel: Selection, path: Path) -> str:
    """Write the market list (no outcomes, no prices) and its SHA-256; refuse to
    overwrite a different frozen list."""
    payload = _frozen_payload(sel)
    digest = frozen_hash(payload)
    path = Path(path)
    sha = path.with_name(path.name + ".sha256")
    if path.exists():
        if frozen_hash(json.loads(path.read_text())) != digest:
            raise RuntimeError(f"{path} already holds a different frozen list")
        return digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=1))
    sha.write_text(digest + "\n")
    # outcomes are stored apart, so the frozen list itself never carries them
    path.with_name(path.name + ".outcomes.json").write_text(json.dumps(sel.outcomes, sort_keys=True))
    return digest


def load_frozen(path: Path) -> Tuple[List[SelectedMarket], str]:
    path = Path(path)
    payload = json.loads(path.read_text())
    digest = frozen_hash(payload)
    recorded = path.with_name(path.name + ".sha256").read_text().strip()
    if digest != recorded:
        raise RuntimeError(f"frozen list hash mismatch: {digest} != recorded {recorded}")
    return [SelectedMarket(**m) for m in payload["markets"]], digest


# --------------------------------------------------------------------------- #
# price history and features (strictly before the decision time)
# --------------------------------------------------------------------------- #
def history_request(m: SelectedMarket) -> dict:
    """The request window ends AT t_d, so nothing after t_d is ever downloaded."""
    td = parse_time(m.decision_time)
    return {"market": m.yes_token_id, "startTs": int((td - HISTORY_LOOKBACK).timestamp()),
            "endTs": int(td.timestamp()), "fidelity": HISTORY_FIDELITY_MIN}


def fetch_price_history(client: PolymarketClient, m: SelectedMarket) -> List[Tuple[int, float]]:
    resp = client.get(CLOB_PRICES_HISTORY, history_request(m))
    return [(int(pt["t"]), float(pt["p"])) for pt in (resp.get("history") or [])]


def strictly_before(history: Sequence[Tuple[int, float]], cutoff: datetime) -> List[Tuple[int, float]]:
    """The look-ahead guard: keep only points timestamped strictly before ``cutoff``."""
    limit = cutoff.timestamp()
    return sorted((t, p) for t, p in history if t < limit)


@dataclass(frozen=True)
class Features:
    price: float
    recent_change: float
    time_to_resolution: float
    price_time: int


def decision_features(history: Sequence[Tuple[int, float]], td: datetime,
                      scheduled_end: datetime) -> Tuple[Optional[Features], Optional[str]]:
    """price, recent_change and time_to_resolution at ``td`` from data strictly before
    ``td``. Returns (None, reason) when the market must be excluded."""
    past = strictly_before(history, td)  # every feature below sees only ``past``
    if not past:
        return None, "no_price_before_decision"
    t_last, price = past[-1]
    if td.timestamp() - t_last > MAX_PRICE_STALENESS.total_seconds():
        return None, "stale_price"
    earlier = [pt for pt in past if pt[0] <= (td - RECENT_CHANGE_WINDOW).timestamp()]
    if not earlier:
        return None, "no_price_before_window"
    change = max(-1.0, min(1.0, price - earlier[-1][1]))
    ttr = (scheduled_end - td).total_seconds() / 86400.0
    return Features(price=price, recent_change=change, time_to_resolution=ttr, price_time=t_last), None


# --------------------------------------------------------------------------- #
# split and output
# --------------------------------------------------------------------------- #
@dataclass
class BuiltMarket:
    market: SelectedMarket
    features: Features
    outcome: int


def build_markets(frozen: Sequence[SelectedMarket], histories: Mapping[str, Sequence[Tuple[int, float]]],
                  outcomes: Mapping[str, int]) -> Tuple[List[BuiltMarket], Dict[str, int]]:
    counts: Dict[str, int] = {"frozen": len(frozen), "closed_before_decision": 0, "no_history_fetched": 0,
                              "no_price_before_decision": 0, "stale_price": 0, "no_price_before_window": 0,
                              "built": 0}
    built = []
    for m in frozen:
        td = parse_time(m.decision_time)
        if parse_time(m.closed_time) <= td:  # not open at t_d: unavailable to a trader then
            counts["closed_before_decision"] += 1
            continue
        if m.market_id not in histories:
            counts["no_history_fetched"] += 1
            continue
        f, why = decision_features(histories[m.market_id], td, parse_time(m.end))
        if f is None:
            counts[why] += 1
            continue
        built.append(BuiltMarket(m, f, int(outcomes[m.market_id])))
    counts["built"] = len(built)
    return built, counts


def split_train_test(built: Sequence[BuiltMarket], cutoff: datetime,
                     gap: timedelta = DEFAULT_SPLIT_GAP) -> Tuple[List[BuiltMarket], List[BuiltMarket], Dict[str, int]]:
    """Training: resolved before ``cutoff``, in resolution order. Test: decided at or
    after ``cutoff + gap``, in decision-time order. Everything else is counted."""
    train = sorted((b for b in built if parse_time(b.market.closed_time) < cutoff),
                   key=lambda b: (parse_time(b.market.closed_time), b.market.market_id))
    test = sorted((b for b in built if parse_time(b.market.decision_time) >= cutoff + gap),
                  key=lambda b: (parse_time(b.market.decision_time), b.market.market_id))
    straddling = len(built) - len(train) - len(test)
    return train, test, {"train": len(train), "test": len(test), "straddling_excluded": straddling}


def _record(b: BuiltMarket, sequence: int) -> dict:
    return {"latent_probability": None, "quote": b.features.price, "outcome": b.outcome,
            "signal": SIGNAL_MIDPOINT, "recent_change": b.features.recent_change,
            "time_to_resolution": b.features.time_to_resolution, "liquidity": LIQUIDITY_MIDPOINT,
            "sequence": sequence,
            "meta": {"market_id": b.market.market_id, "event_id": b.market.event_id,
                     "decision_time": b.market.decision_time, "price_time_unix": b.features.price_time,
                     "closed_time": b.market.closed_time}}


def write_market_file(path: Path, train: Sequence[BuiltMarket], test: Sequence[BuiltMarket],
                      frozen_sha256: str, cutoff: datetime, gap: timedelta, counts: Mapping) -> None:
    payload = {"format": MARKET_FILE_FORMAT, "venue": "polymarket", "frozen_list_sha256": frozen_sha256,
               "split": {"cutoff": cutoff.isoformat(), "gap_days": gap.total_seconds() / 86400},
               "counts": dict(counts),
               "train": [_record(b, i) for i, b in enumerate(train)],
               "test": [_record(b, i) for i, b in enumerate(test)]}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, sort_keys=True, indent=1))


def load_market_file(path: Path) -> Tuple[List[Market], List[Market]]:
    """The synthetic runner's input type. ``latent_probability`` is unknown for real
    markets and is NaN; nothing in the runner reads it."""
    payload = json.loads(Path(path).read_text())
    if payload.get("format") != MARKET_FILE_FORMAT:
        raise ValueError(f"not a {MARKET_FILE_FORMAT} file")

    def to_market(r: Mapping) -> Market:
        return Market(latent_probability=math.nan, quote=float(r["quote"]), outcome=int(r["outcome"]),
                      signal=float(r["signal"]), recent_change=float(r["recent_change"]),
                      time_to_resolution=float(r["time_to_resolution"]), liquidity=float(r["liquidity"]),
                      sequence=int(r["sequence"]))

    return [to_market(r) for r in payload["train"]], [to_market(r) for r in payload["test"]]
