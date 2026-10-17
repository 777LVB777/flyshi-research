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

import gzip
import hashlib
import http.client
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from flyshi_research.simulator import Market

# ---- endpoints (condition 1) ------------------------------------------------------- #
GAMMA_MARKETS = "GET https://gamma-api.polymarket.com/markets/keyset"
CLOB_PRICES_HISTORY = "GET https://clob.polymarket.com/prices-history"
ALLOWED_ENDPOINTS = (GAMMA_MARKETS, CLOB_PRICES_HISTORY)

#: the configured rate may use at most this fraction of the published limit
RATE_FRACTION = 0.25
#: default pre-set rate: one request every 2 s (0.5 req/s)
DEFAULT_REQUESTS_PER_SECOND = 0.5
#: retries after a TRANSIENT failure (so up to MAX_RETRIES + 1 attempts), with
#: exponential backoff 2, 4, 8, 16, 32 s: HTTP 429/500/502/503/504, a truncated or
#: non-JSON 200 body, http.client.IncompleteRead, connection resets and remote
#: disconnects, timeouts, and other socket/URL errors
MAX_RETRIES = 5
MAX_RETRIES_429 = MAX_RETRIES  # former name
TRANSIENT_STATUSES = (429, 500, 502, 503, 504)
#: per socket operation (connect, each read)
REQUEST_TIMEOUT_S = 30.0
#: the whole request, body included: a slow trickle can never hang a request forever
REQUEST_DEADLINE_S = 120.0
READ_CHUNK_BYTES = 64 * 1024
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

# ---- split and sample (FINAL 2026-10-16, phase2-design.md 10.11) ------------------- #
#: training: resolved (closed) before SPLIT_CUTOFF; test: SPLIT_CUTOFF + SPLIT_GAP <= t_d < TEST_DECISION_END
SPLIT_CUTOFF = datetime(2026, 3, 1, tzinfo=timezone.utc)
SPLIT_GAP = DEFAULT_SPLIT_GAP
TEST_DECISION_END = datetime(2026, 9, 1, tzinfo=timezone.utc)
#: each pool is fetched in order of sha256(SAMPLE_ORDER_SEED|market id)
SAMPLE_ORDER_SEED = "flyshi-phase2-sample-20261016"
#: Design A: 40 disjoint chains x (70 training + 180 test)
POOL_NEED = {"train": 2_800, "test": 7_200}
#: usable markets fetched beyond the need, in percent (FINAL 2026-10-16)
POOL_RESERVE_PERCENT = 15


class NetworkRefused(RuntimeError):
    """A request was refused before any transport ran."""


# ---- terms re-check before any request (Section 1, condition 8) -------------------- #
#: SHA-256 of the plain-text export of the Terms of Use (effective 2026-08-11), recorded
#: 2026-10-11 and re-confirmed identical 2026-10-12 (phase2-design.md, Section 1)
RECORDED_TERMS_SHA256 = "0506de1ebf824b1827dfef90828f0e78f45d9defa63241ac91f1ed2c0ee2847d"
TERMS_EXPORT_URL = "https://docs.google.com/document/d/1N4aYlRcqaWCeKMID7vUSWJ1UPMvw_v6SP4cOFN8ZxR4/export?format=txt"
TERMS_MAX_AGE = timedelta(hours=24)


def record_terms_check(text_path: Path, out_path: Path, now: datetime) -> dict:
    """Hash a locally saved copy of the terms and record whether it matches."""
    digest = hashlib.sha256(Path(text_path).read_bytes()).hexdigest()
    record = {"checked_utc": now.astimezone(timezone.utc).isoformat(), "sha256": digest,
              "recorded_sha256": RECORDED_TERMS_SHA256, "matches": digest == RECORDED_TERMS_SHA256,
              "source": TERMS_EXPORT_URL}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(record, indent=1, sort_keys=True))
    return record


def require_fresh_terms_check(path: Path, now: datetime) -> dict:
    """Refuse unless a matching terms check was recorded within TERMS_MAX_AGE."""
    if not Path(path).exists():
        raise NetworkRefused(f"no terms check recorded at {path} (run the 'terms' step first)")
    record = json.loads(Path(path).read_text())
    if not record.get("matches") or record.get("recorded_sha256") != RECORDED_TERMS_SHA256:
        raise NetworkRefused("the terms changed since 2026-10-11: stop; the owner must review them")
    age = now - datetime.fromisoformat(record["checked_utc"])
    if not timedelta(0) <= age <= TERMS_MAX_AGE:
        raise NetworkRefused(f"the terms check is {age} old; re-check (at most {TERMS_MAX_AGE})")
    return record


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


class TransientNetworkError(Exception):
    """A network failure worth retrying, with how many body bytes had arrived."""

    def __init__(self, kind: str, bytes_received: int = 0, detail: str = "") -> None:
        super().__init__(f"{kind} after {bytes_received} bytes{': ' + detail if detail else ''}")
        self.kind, self.bytes_received, self.detail = kind, bytes_received, detail


class RetriesExhausted(RuntimeError):
    """Every attempt at one URL failed with a transient error."""

    def __init__(self, url: str, attempts: int, last_error: str) -> None:
        super().__init__(f"all {attempts} attempts failed for {url} (last error: {last_error})")
        self.url, self.attempts, self.last_error = url, attempts, last_error


class MetadataPageFailed(RetriesExhausted):
    """A Gamma metadata page failed every attempt; names the cursor to resume from."""

    def __init__(self, cursor: Optional[str], saved_pages: int, cause: RetriesExhausted) -> None:
        where = f"after cursor {cursor!r}" if cursor else "1 (no cursor)"
        RuntimeError.__init__(
            self, f"Gamma metadata page {where} failed all {cause.attempts} attempts "
                  f"(last error: {cause.last_error}). Nothing was saved for this page; the "
                  f"{saved_pages} saved page(s) are kept. Re-run the same command to resume from this cursor.")
        self.url, self.attempts, self.last_error = cause.url, cause.attempts, cause.last_error
        self.cursor, self.saved_pages = cursor, saved_pages


def _classify(exc: BaseException) -> Tuple[str, int]:
    """(error kind, bytes received) for a transient exception raised by a transport."""
    if isinstance(exc, TransientNetworkError):
        return exc.kind, exc.bytes_received
    if isinstance(exc, http.client.IncompleteRead):
        return "IncompleteRead", len(exc.partial or b"")
    if isinstance(exc, urllib.error.URLError) and not isinstance(exc, urllib.error.HTTPError):
        return f"URLError({type(exc.reason).__name__})", 0
    return type(exc).__name__, 0


#: exceptions a transport may raise that are retried (NetworkRefused is never among them)
TRANSIENT_EXCEPTIONS = (TransientNetworkError, http.client.HTTPException, OSError)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise NetworkRefused(f"redirect to {newurl!r} refused")


def urllib_transport(timeout_s: float = REQUEST_TIMEOUT_S, deadline_s: float = REQUEST_DEADLINE_S,
                     opener=None, clock: Callable[[], float] = time.monotonic) -> Transport:
    """The real transport: https GET, no redirects, no cookie jar, no proxy auth.

    ``timeout_s`` bounds each socket operation; ``deadline_s`` bounds the whole request,
    checked between body chunks. Every network failure is raised as
    TransientNetworkError with the bytes received so far; a refused redirect is not."""
    opener = opener or urllib.request.build_opener(_NoRedirect())

    def get(url: str, headers: Mapping[str, str]):
        req = urllib.request.Request(url, headers=dict(headers), method="GET")
        start, received, chunks = clock(), 0, []
        try:
            with opener.open(req, timeout=timeout_s) as resp:
                while True:
                    if clock() - start > deadline_s:
                        raise TransientNetworkError("TimeoutError", received, f"request deadline {deadline_s:g} s")
                    chunk = resp.read(READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    received += len(chunk)
                return resp.status, b"".join(chunks), dict(resp.headers)
        except urllib.error.HTTPError as err:
            try:
                body = err.read()
            except (http.client.HTTPException, OSError):
                body = b""
            return err.code, body, dict(err.headers or {})
        except http.client.IncompleteRead as exc:
            raise TransientNetworkError("IncompleteRead", received + len(exc.partial or b"")) from exc
        except (http.client.HTTPException, OSError) as exc:
            kind, _ = _classify(exc)
            raise TransientNetworkError(kind, received, str(exc)[:200]) from exc

    return get


class PolymarketClient:
    """Read-only GET client. Every request passes the policy, the rate limit and the log."""

    def __init__(self, policy: NetworkPolicy, transport: Optional[Transport], log_path: Path,
                 raw_dir: Optional[Path] = None, clock: Optional[Callable[[], float]] = None,
                 sleep: Optional[Callable[[float], None]] = None,
                 wallclock: Optional[Callable[[], float]] = None) -> None:
        self.policy, self.log_path, self.raw_dir = policy, Path(log_path), raw_dir
        # resolved when the client is built (not when the class is defined)
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.wallclock = wallclock or time.time
        self._transport = transport
        self._last: Optional[float] = None
        self.requests = 0

    def get(self, endpoint: str, params: Mapping[str, object]) -> object:
        self.policy.check(endpoint)  # refuses before anything else happens
        if self._transport is None:
            self._transport = urllib_transport()
        base = endpoint.split(" ", 1)[1]
        pairs = [(k, str(x)) for k, v in sorted(params.items())
                 for x in (v if isinstance(v, (list, tuple)) else (v,))]  # a list repeats its key
        url = base + ("?" + urllib.parse.urlencode(pairs) if pairs else "")
        if not url.startswith("https://"):
            raise NetworkRefused("https only")
        if any(h.lower() in _FORBIDDEN_HEADERS for h in REQUEST_HEADERS):
            raise NetworkRefused("authentication headers are never sent")
        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            status: Optional[int] = None
            body = b""
            error: Optional[str] = None
            try:
                status, body, _ = self._transport(url, REQUEST_HEADERS)
            except NetworkRefused:
                raise
            except TRANSIENT_EXCEPTIONS as exc:
                error, received = _classify(exc)
            else:
                received = len(body)
                if status == 200:
                    try:
                        value = json.loads(body)  # a truncated or non-JSON body is transient
                    except ValueError as exc:
                        error = type(exc).__name__
                elif status in TRANSIENT_STATUSES:
                    error = f"HTTP {status}"
            self.requests += 1
            self._log(endpoint, url, status, body, attempt, error=error, bytes_received=received)
            if error is None:
                if status != 200:
                    raise RuntimeError(f"HTTP {status} for {url}")
                if self.raw_dir is not None:  # only a page that parsed is ever saved
                    self._store_raw(url, body)
                return value
            last_error = f"{error} ({received} bytes)"
            if attempt < MAX_RETRIES:
                self.sleep(min(60.0, 2.0 ** (attempt + 1)))
        raise RetriesExhausted(url, MAX_RETRIES + 1, last_error)

    def _throttle(self) -> None:
        interval = 1.0 / self.policy.requests_per_second
        if self._last is not None:
            wait = self._last + interval - self.clock()
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()

    def _log(self, endpoint: str, url: str, status: Optional[int], body: bytes, attempt: int,
             error: Optional[str] = None, bytes_received: Optional[int] = None) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"utc": datetime.fromtimestamp(self.wallclock(), timezone.utc).isoformat(),
                 "endpoint": endpoint, "url": url, "status": status,
                 "bytes": len(body) if bytes_received is None else bytes_received,
                 "sha256": hashlib.sha256(body).hexdigest() if body else None, "attempt": attempt,
                 "error": error, "result": "ok" if error is None else
                 ("retry" if attempt < MAX_RETRIES else "gave_up")}
        with open(self.log_path, "a") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    def _store_raw(self, url: str, body: bytes) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        (self.raw_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json.gz")).write_bytes(gzip.compress(body))


# --------------------------------------------------------------------------- #
# metadata fetch and selection
# --------------------------------------------------------------------------- #
def fetch_closed_markets(client: PolymarketClient, max_pages: Optional[int] = None,
                         transform: Optional[Callable[[Mapping], dict]] = None,
                         progress_path: Optional[Path] = None,
                         extra_params: Optional[Mapping[str, object]] = None) -> List[dict]:
    """Every closed market, archived included, by keyset paging (no volume filter, so
    the excluded markets can be counted).

    ``transform`` reduces each market as it arrives (the CLI keeps only the snapshot
    fields, so memory stays small). With ``progress_path`` every page is appended as
    one JSON line with the cursor that follows it, and a re-run resumes after the
    last saved page instead of starting again."""
    markets: List[dict] = []
    cursor: Optional[str] = None
    pages = 0
    if progress_path is not None and Path(progress_path).exists():
        for entry in _read_progress(Path(progress_path)):
            markets.extend(entry["markets"])
            cursor = entry["next_cursor"]
            pages += 1
        if pages and not cursor:
            return markets  # finished earlier
    while max_pages is None or pages < max_pages:
        params: Dict[str, object] = {"closed": "true", "limit": GAMMA_PAGE_LIMIT, **(extra_params or {})}
        if cursor:
            params["after_cursor"] = cursor
        try:
            page = client.get(GAMMA_MARKETS, params)
        except RetriesExhausted as failed:  # nothing is saved for this page
            raise MetadataPageFailed(cursor, pages, failed) from failed
        batch = [transform(m) if transform else m for m in (page.get("markets") or [])]
        next_cursor = page.get("next_cursor")
        if progress_path is not None:
            _append_progress(Path(progress_path), {"next_cursor": next_cursor, "markets": batch})
        markets.extend(batch)
        pages += 1
        cursor = next_cursor
        if not cursor:
            break
    return markets


def _append_progress(path: Path, entry: Mapping) -> None:
    """One whole line per page, flushed and fsynced before the next request."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(entry) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _read_progress(path: Path) -> List[dict]:
    """Saved pages. A torn LAST line (the process was killed mid-write) is dropped and
    the file truncated to the last whole page; a bad line anywhere else is an error."""
    text = path.read_text()
    lines = text.split("\n")
    entries, good_chars = [], 0
    for i, line in enumerate(lines):
        if not line:
            good_chars += 1 if i < len(lines) - 1 else 0
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            if any(rest.strip() for rest in lines[i + 1:]):
                raise RuntimeError(f"{path}: line {i + 1} is damaged but later pages exist; inspect it")
            with open(path, "r+") as fh:
                fh.truncate(good_chars)
            break
        good_chars += len(line) + 1
    return entries


def parse_time(value: Optional[str]) -> Optional[datetime]:
    """Gamma timestamps: ISO 8601 ('...Z' or '+00:00') or '2024-01-01 12:00:00+00'."""
    if not value:
        return None
    v = str(value).strip().replace(" ", "T")
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    elif len(v) >= 3 and v[-3] in "+-" and v[-2:].isdigit():
        v = v + ":00"
    if "." in v:  # real Gamma createdAt has 1-3 fractional digits; pad to 6
        head, _, rest = v.partition(".")
        digits = len(rest) - len(rest.lstrip("0123456789"))
        v = head + "." + rest[:digits].ljust(6, "0")[:6] + rest[digits:]
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


#: numeric market IDs below this are remembered in a bitmap (at most 32 MB); others in a set
ID_BITMAP_LIMIT = 1 << 28


class _SeenIds:
    """Exact membership for market IDs: canonical numeric IDs in a bitmap, others in a set."""

    def __init__(self) -> None:
        self.bits = bytearray()
        self.other: set = set()

    def add(self, mid: str) -> bool:
        """True if ``mid`` was already seen."""
        if mid.isascii() and mid.isdigit() and (mid == "0" or mid[0] != "0") and len(mid) < 10 \
                and int(mid) < ID_BITMAP_LIMIT:
            i = int(mid)
            byte, bit = i >> 3, 1 << (i & 7)
            if byte >= len(self.bits):
                self.bits.extend(bytes(max(byte + 1 - len(self.bits), len(self.bits))))
            if self.bits[byte] & bit:
                return True
            self.bits[byte] |= bit
            return False
        if mid in self.other:
            return True
        self.other.add(mid)
        return False


#: tolerance used ONLY to name an exclusion reason (never to accept a market)
NEAR_SETTLED_TOLERANCE = 0.02


def _resolution(prices: Optional[list]) -> str:
    """'yes', 'no' or 'void' (50/50) for an EXACT recorded settlement; otherwise the
    reason it is not one:

    * 'near_0_1_not_exact': within NEAR_SETTLED_TOLERANCE of a 0/1 pair but not exact,
      e.g. ['0.9999999999…', '0.0000000000…'] in 2020-21 AMM-era markets, whose
      outcomePrices is the pool's last price, not a settlement record;
    * 'interior_final_price': further from 0/1 than that;
    * 'malformed_prices': missing, not two numbers.

    Only an exact pair is accepted, so a stale pool price is never taken as an outcome.
    The reason is symmetric in the two sides, so counting it reveals no outcome."""
    if not prices or len(prices) != 2:
        return "malformed_prices"
    try:
        a, b = (float(x) for x in prices)
    except (TypeError, ValueError):
        return "malformed_prices"
    if (a, b) == (1.0, 0.0):
        return "yes"
    if (a, b) == (0.0, 1.0):
        return "no"
    if (a, b) == (0.5, 0.5):
        return "void"
    distance = min(max(abs(a - 1.0), abs(b)), max(abs(a), abs(b - 1.0)))
    return "near_0_1_not_exact" if distance <= NEAR_SETTLED_TOLERANCE else "interior_final_price"


def selection_params(min_volume: float = MIN_FINAL_VOLUME_USDC) -> dict:
    return {"min_final_volume_usdc": min_volume, "decision_margin_hours": DECISION_MARGIN.total_seconds() / 3600,
            "decision_time_seed": DECISION_TIME_SEED, "event_choice_seed": EVENT_CHOICE_SEED,
            "binary": "outcomes exactly ['Yes','No'] with two CLOB token IDs; two named outcomes counted apart",
            "resolved": ("closed and outcomePrices exactly (1,0) or (0,1); (0.5,0.5) counted as void; "
                         "near-0/1 (AMM-era pool prices) and interior final prices counted, never accepted"),
            "one_per_event": "lowest sha256(event_choice_seed|market_id) within the event"}


def select_markets(raw: Iterable[Mapping], min_volume: float = MIN_FINAL_VOLUME_USDC) -> Selection:
    """Resolved binary markets, final volume >= ``min_volume``, one market per event.
    Every exclusion is counted; archived markets are included and counted.

    One pass over ``raw``, which may be a stream (``iter_snapshot``). Memory is
    compact: seen IDs in ``_SeenIds``, volume-sensitivity counters instead of a list
    of volumes, and only the current choice per event (lowest ``_unit``; the earlier
    market wins a tie), never every eligible market."""
    counts: Dict[str, int] = {k: 0 for k in (
        "raw", "duplicate_id", "not_closed", "multi_outcome", "two_named_outcomes_not_yes_no",
        "missing_token_ids", "void_50_50", "near_0_1_not_exact", "interior_final_price", "malformed_prices",
        "missing_dates", "below_min_volume", "no_decision_window",
        "closed_before_decision", "eligible_before_event_choice", "dropped_one_per_event", "selected", "archived_selected")}
    seen = _SeenIds()
    sens_at = {f">={v:g}": v for v in (*VOLUME_SENSITIVITY_USDC, min_volume)}
    sens = {k: 0 for k in sens_at}
    chosen: Dict[str, Tuple[float, SelectedMarket, int]] = {}  # event -> (unit, market, outcome)
    for m in raw:
        counts["raw"] += 1
        mid = str(m.get("id"))
        if seen.add(mid):
            counts["duplicate_id"] += 1
            continue
        if not m.get("closed"):
            counts["not_closed"] += 1
            continue
        names = _json_list(m.get("outcomes"))
        if not names or len(names) != 2:
            counts["multi_outcome"] += 1
            continue
        if [str(n).strip().lower() for n in names] != ["yes", "no"]:
            counts["two_named_outcomes_not_yes_no"] += 1  # e.g. two team or candidate names
            continue
        tokens = _json_list(m.get("clobTokenIds"))
        if not tokens or len(tokens) != 2:
            counts["missing_token_ids"] += 1
            continue
        res = _resolution(_json_list(m.get("outcomePrices")))
        if res == "void":
            counts["void_50_50"] += 1
            continue
        if res not in ("yes", "no"):
            counts[res] += 1
            continue
        start = parse_time(m.get("startDate") or m.get("createdAt"))
        end = parse_time(m.get("endDate"))
        closed = parse_time(m.get("closedTime"))
        if start is None or end is None or closed is None:
            counts["missing_dates"] += 1
            continue
        volume = float(m.get("volumeNum") or 0.0)
        for k, v in sens_at.items():
            sens[k] += volume >= v
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
        counts["eligible_before_event_choice"] += 1
        unit = _unit(EVENT_CHOICE_SEED, mid)  # outcome-blind and price-blind choice
        cur = chosen.get(event_id)
        if cur is None or unit < cur[0]:
            chosen[event_id] = (unit, SelectedMarket(
                market_id=mid, event_id=event_id, yes_token_id=str(tokens[0]),
                question=str(m.get("question") or ""), start=start.isoformat(), end=end.isoformat(),
                closed_time=closed.isoformat(), decision_time=td.isoformat(), final_volume=volume,
                archived=bool(m.get("archived"))), 1 if res == "yes" else 0)
    picks = sorted(chosen.values(), key=lambda c: c[1].market_id)
    selected = [c[1] for c in picks]
    counts["dropped_one_per_event"] = counts["eligible_before_event_choice"] - len(selected)
    counts["selected"] = len(selected)
    counts["archived_selected"] = sum(s.archived for s in selected)
    return Selection(selection_params(min_volume), selected, {c[1].market_id: c[2] for c in picks}, counts, sens)


# --------------------------------------------------------------------------- #
# metadata snapshot and blinded count report
# --------------------------------------------------------------------------- #
#: the only Gamma fields kept in the private metadata snapshot (selection needs them)
SNAPSHOT_FIELDS = ("id", "question", "closed", "archived", "outcomes", "outcomePrices", "clobTokenIds",
                   "volumeNum", "startDate", "createdAt", "endDate", "closedTime", "umaResolutionStatus",
                   "umaResolutionStatuses", "marketMakerAddress", "fpmmLive", "enableOrderBook")
COUNT_THRESHOLDS_USDC = (*VOLUME_SENSITIVITY_USDC[:1], MIN_FINAL_VOLUME_USDC, *VOLUME_SENSITIVITY_USDC[1:])


def compact_market(m: Mapping) -> dict:
    out = {k: m.get(k) for k in SNAPSHOT_FIELDS}
    out["events"] = [{"id": e.get("id")} for e in (m.get("events") or []) if isinstance(e, Mapping)]
    return out


def write_snapshot(markets: Sequence[Mapping], path: Path) -> str:
    """Private metadata snapshot (compact fields only) plus its SHA-256."""
    payload = [compact_market(m) for m in markets]
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    Path(path).with_name(Path(path).name + ".sha256").write_text(digest + "\n")
    return digest


def read_snapshot(path: Path) -> List[dict]:
    text = Path(path).read_text()
    recorded = Path(path).with_name(Path(path).name + ".sha256").read_text().strip()
    if hashlib.sha256(text.encode()).hexdigest() != recorded:
        raise RuntimeError(f"metadata snapshot hash mismatch: {path}")
    return json.loads(text)


def _uma_resolved(m: Mapping) -> bool:
    statuses = _json_list(m.get("umaResolutionStatuses")) or []
    return m.get("umaResolutionStatus") == "resolved" or "resolved" in [str(x) for x in statuses]


def _year_counts(raw: Sequence[Mapping]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for m in raw:
        t = parse_time(m.get("createdAt") or m.get("startDate"))
        k = t.strftime("%Y") if t else "unknown"
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def count_report(raw: Sequence[Mapping], thresholds: Sequence[float] = COUNT_THRESHOLDS_USDC,
                 main: float = MIN_FINAL_VOLUME_USDC) -> dict:
    """Counts only. Reports NO outcome and NO price: no YES/NO split, no price field,
    and nothing that changes when outcomes or prices change (tested)."""
    sels = {v: select_markets(raw, v) for v in thresholds}
    s = sels[main]

    def months(key: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for m in s.markets:
            k = parse_time(getattr(m, key)).strftime("%Y-%m")
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items()))

    return {
        "note": "counts only; no outcome or price is reported",
        "raw_markets": s.counts["raw"],
        "archived_in_raw": sum(bool(m.get("archived")) for m in raw),
        "resolved_binary_markets": s.counts["raw"] - sum(s.counts[k] for k in (
            "duplicate_id", "not_closed", "multi_outcome", "two_named_outcomes_not_yes_no", "missing_token_ids",
            "void_50_50", "near_0_1_not_exact", "interior_final_price", "malformed_prices")),
        "era_and_status_in_raw": {
            "amm_market_maker_address_present": sum(bool(m.get("marketMakerAddress")) for m in raw),
            "uma_resolution_status_resolved": sum(_uma_resolved(m) for m in raw),
            "created_year": _year_counts(raw)},
        f"exclusions_by_reason_at_{main:g}": {k: v for k, v in s.counts.items() if k not in (
            "raw", "eligible_before_event_choice", "selected", "archived_selected")},
        "one_per_event": {f">={v:g}": {"eligible_before_event_choice": sels[v].counts["eligible_before_event_choice"],
                                       "dropped_one_per_event": sels[v].counts["dropped_one_per_event"],
                                       "selected": sels[v].counts["selected"]} for v in thresholds},
        "qualifying_one_per_event": {f">={v:g}": sels[v].counts["selected"] for v in thresholds},
        f"selected_at_{main:g}_by_close_month": months("closed_time"),
        f"selected_at_{main:g}_by_decision_month": months("decision_time"),
        f"archived_selected_at_{main:g}": s.counts["archived_selected"],
    }


# --------------------------------------------------------------------------- #
# streaming count report (a multi-GB snapshot, never loaded whole)
# --------------------------------------------------------------------------- #
SNAPSHOT_READ_CHARS = 8 * 1024 * 1024
#: no single market comes near this; a longer undecodable run means a damaged file
MAX_RECORD_CHARS = 64 * 1024 * 1024


def verify_snapshot_sha256(path: Path, chunk_bytes: int = SNAPSHOT_READ_CHARS) -> str:
    """The snapshot's SHA-256, hashed in chunks; refuses unless it matches the recorded one."""
    path = Path(path)
    recorded = path.with_name(path.name + ".sha256").read_text().strip()
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_bytes), b""):
            h.update(chunk)
    if h.hexdigest() != recorded:
        raise RuntimeError(f"metadata snapshot hash mismatch: {path}")
    return recorded


def iter_snapshot(path: Path, chunk_chars: int = SNAPSHOT_READ_CHARS) -> Iterator[dict]:
    """The markets of a snapshot (one JSON array of objects) one at a time, in file
    order, holding about one chunk of text. Same values as ``json.loads``."""
    decoder = json.JSONDecoder()
    buf, pos, eof, state = "", 0, False, "start"  # start -> first -> (sep <-> value) -> end
    with open(path, encoding="utf-8") as fh:
        while True:
            while pos < len(buf) and buf[pos] in " \t\r\n":
                pos += 1
            if pos < len(buf) and state in ("first", "value") and not (state == "first" and buf[pos] == "]"):
                try:
                    obj, end = decoder.raw_decode(buf, pos)
                except json.JSONDecodeError:
                    if eof or len(buf) - pos > MAX_RECORD_CHARS:
                        raise
                    obj = None  # an object cut by the chunk boundary: read more
                if obj is not None:
                    if not isinstance(obj, dict):
                        raise ValueError(f"{path}: snapshot element at char {pos} is not an object")
                    yield obj
                    pos, state = end, "sep"
                    continue
            elif pos < len(buf):
                c = buf[pos]
                pos += 1
                if state == "start" and c == "[":
                    state = "first"
                elif state in ("first", "sep") and c == "]":
                    state = "end"
                elif state == "sep" and c == ",":
                    state = "value"
                else:
                    raise ValueError(f"{path}: unexpected {c!r} in state {state!r}")
                continue
            if eof:
                break
            chunk = fh.read(chunk_chars)
            buf, pos, eof = buf[pos:] + chunk, 0, not chunk
    if state != "end" or buf[pos:].strip():
        raise ValueError(f"{path}: snapshot is truncated or has trailing data (state {state!r})")


class StreamingCountReport:
    """``count_report`` one market at a time, for a snapshot too big to load.

    Same filters, in the same order, as ``select_markets``; the threshold-independent
    ones run once per market. One per event: at the main threshold only the current
    best (lowest ``_unit``) per event is kept, as (unit, close month, decision month,
    archived); at the other thresholds the report needs only how many events have an
    eligible market, so only the event IDs are kept. Duplicate IDs: ``_SeenIds``."""

    _SHARED = ("raw", "duplicate_id", "not_closed", "multi_outcome", "two_named_outcomes_not_yes_no",
               "missing_token_ids", "void_50_50", "near_0_1_not_exact", "interior_final_price",
               "malformed_prices", "missing_dates")

    def __init__(self, thresholds: Sequence[float] = COUNT_THRESHOLDS_USDC,
                 main: float = MIN_FINAL_VOLUME_USDC) -> None:
        if main not in thresholds:
            raise ValueError("the main threshold must be one of the thresholds")
        self.thresholds, self.main = tuple(thresholds), main
        self.shared: Dict[str, int] = {k: 0 for k in self._SHARED}
        self.per = {v: {"below_min_volume": 0, "no_decision_window": 0, "closed_before_decision": 0,
                        "eligible_before_event_choice": 0} for v in self.thresholds}
        self.best: Dict[str, Tuple[float, str, str, bool]] = {}  # main threshold
        self.events = {v: set() for v in self.thresholds if v != main}  # the others
        self.seen = _SeenIds()
        self.archived_in_raw = self.amm = self.uma = 0
        self.years: Dict[str, int] = {}
        self._month: Dict[Tuple[int, int], str] = {}

    def _ym(self, t: datetime) -> str:
        k = (t.year, t.month)
        if k not in self._month:
            self._month[k] = t.strftime("%Y-%m")
        return self._month[k]

    def add(self, m: Mapping) -> None:
        c = self.shared
        c["raw"] += 1
        self.archived_in_raw += bool(m.get("archived"))
        self.amm += bool(m.get("marketMakerAddress"))
        self.uma += _uma_resolved(m)
        t = parse_time(m.get("createdAt") or m.get("startDate"))
        y = t.strftime("%Y") if t else "unknown"
        self.years[y] = self.years.get(y, 0) + 1
        mid = str(m.get("id"))
        if self.seen.add(mid):
            c["duplicate_id"] += 1
            return
        if not m.get("closed"):
            c["not_closed"] += 1
            return
        names = _json_list(m.get("outcomes"))
        if not names or len(names) != 2:
            c["multi_outcome"] += 1
            return
        if [str(n).strip().lower() for n in names] != ["yes", "no"]:
            c["two_named_outcomes_not_yes_no"] += 1
            return
        tokens = _json_list(m.get("clobTokenIds"))
        if not tokens or len(tokens) != 2:
            c["missing_token_ids"] += 1
            return
        res = _resolution(_json_list(m.get("outcomePrices")))
        if res == "void":
            c["void_50_50"] += 1
            return
        if res not in ("yes", "no"):
            c[res] += 1
            return
        start = parse_time(m.get("startDate") or m.get("createdAt"))
        end = parse_time(m.get("endDate"))
        closed = parse_time(m.get("closedTime"))
        if start is None or end is None or closed is None:
            c["missing_dates"] += 1
            return
        volume = float(m.get("volumeNum") or 0.0)
        drawn, td, unit, event_id = False, None, 0.0, ""
        for v in self.thresholds:
            p = self.per[v]
            if volume < v:
                p["below_min_volume"] += 1
                continue
            if not drawn:
                drawn, td = True, decision_time(mid, start, end)
                if td is not None and closed > td:
                    events = m.get("events") or []
                    event_id = str(events[0].get("id")) if events and events[0].get("id") is not None \
                        else f"market:{mid}"
                    unit = _unit(EVENT_CHOICE_SEED, mid)
            if td is None:
                p["no_decision_window"] += 1
                continue
            if closed <= td:
                p["closed_before_decision"] += 1
                continue
            p["eligible_before_event_choice"] += 1
            if v == self.main:
                cur = self.best.get(event_id)
                if cur is None or unit < cur[0]:  # strict: the earlier market wins a tie, as in select_markets
                    self.best[event_id] = (unit, self._ym(closed), self._ym(td), bool(m.get("archived")))
            else:
                self.events[v].add(event_id)

    def counts(self, v: float) -> Dict[str, int]:
        """``select_markets(raw, v).counts``, same keys in the same order (``archived_selected``
        is tracked at the main threshold only; elsewhere it is 0)."""
        p = self.per[v]
        n = len(self.best) if v == self.main else len(self.events[v])
        out = dict(self.shared)
        out.update(below_min_volume=p["below_min_volume"], no_decision_window=p["no_decision_window"],
                   closed_before_decision=p["closed_before_decision"],
                   eligible_before_event_choice=p["eligible_before_event_choice"],
                   dropped_one_per_event=p["eligible_before_event_choice"] - n, selected=n,
                   archived_selected=sum(b[3] for b in self.best.values()) if v == self.main else 0)
        return out

    def report(self) -> dict:
        """Exactly ``count_report`` (same keys, order and values). No outcome, no price."""
        main, thresholds = self.main, self.thresholds
        sc = {v: self.counts(v) for v in thresholds}
        s = sc[main]

        def months(i: int) -> Dict[str, int]:
            out: Dict[str, int] = {}
            for b in self.best.values():
                out[b[i]] = out.get(b[i], 0) + 1
            return dict(sorted(out.items()))

        return {
            "note": "counts only; no outcome or price is reported",
            "raw_markets": s["raw"],
            "archived_in_raw": self.archived_in_raw,
            "resolved_binary_markets": s["raw"] - sum(s[k] for k in (
                "duplicate_id", "not_closed", "multi_outcome", "two_named_outcomes_not_yes_no", "missing_token_ids",
                "void_50_50", "near_0_1_not_exact", "interior_final_price", "malformed_prices")),
            "era_and_status_in_raw": {
                "amm_market_maker_address_present": self.amm,
                "uma_resolution_status_resolved": self.uma,
                "created_year": dict(sorted(self.years.items()))},
            f"exclusions_by_reason_at_{main:g}": {k: v for k, v in s.items() if k not in (
                "raw", "eligible_before_event_choice", "selected", "archived_selected")},
            "one_per_event": {f">={v:g}": {"eligible_before_event_choice": sc[v]["eligible_before_event_choice"],
                                           "dropped_one_per_event": sc[v]["dropped_one_per_event"],
                                           "selected": sc[v]["selected"]} for v in thresholds},
            "qualifying_one_per_event": {f">={v:g}": sc[v]["selected"] for v in thresholds},
            f"selected_at_{main:g}_by_close_month": months(1),
            f"selected_at_{main:g}_by_decision_month": months(2),
            f"archived_selected_at_{main:g}": s["archived_selected"],
        }


def count_report_from_snapshot(path: Path, progress: Optional[Callable[[int], None]] = None,
                               every: int = 250_000, chunk_chars: int = SNAPSHOT_READ_CHARS) -> Tuple[str, dict]:
    """(SHA-256, ``count_report``) for a saved snapshot, streamed. The hash is checked
    over the whole file BEFORE any market is parsed."""
    digest = verify_snapshot_sha256(path)
    acc = StreamingCountReport()
    for i, m in enumerate(iter_snapshot(path, chunk_chars), 1):
        acc.add(m)
        if progress is not None and i % every == 0:
            progress(i)
    return digest, acc.report()


def select_from_snapshot(path: Path, min_volume: float = MIN_FINAL_VOLUME_USDC,
                         progress: Optional[Callable[[int], None]] = None, every: int = 250_000,
                         chunk_chars: int = SNAPSHOT_READ_CHARS) -> Tuple[str, Selection, dict]:
    """(SHA-256, ``select_markets``, ``count_report``) for a saved snapshot, in ONE
    streamed pass after the hash is checked over the whole file. Nothing is written."""
    digest = verify_snapshot_sha256(path)
    acc = StreamingCountReport()

    def markets() -> Iterator[dict]:
        for i, m in enumerate(iter_snapshot(path, chunk_chars), 1):
            acc.add(m)
            yield m
            if progress is not None and i % every == 0:
                progress(i)

    sel = select_markets(markets(), min_volume)
    return digest, sel, acc.report()


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
# sample order and fill (FINAL 2026-10-16): blind to outcomes and prices
# --------------------------------------------------------------------------- #
POOLS = ("train", "test")


def pool_of(m: SelectedMarket, cutoff: datetime = SPLIT_CUTOFF, gap: timedelta = SPLIT_GAP,
            test_end: Optional[datetime] = TEST_DECISION_END) -> str:
    """'train', 'test', 'straddling' or 'after_test_window', from the market's dates
    only; the same rule as ``split_train_test``."""
    if parse_time(m.closed_time) < cutoff:
        return "train"
    td = parse_time(m.decision_time)
    if td < cutoff + gap:
        return "straddling"
    return "after_test_window" if test_end is not None and td >= test_end else "test"


def sample_rank(market_id: str, seed: str = SAMPLE_ORDER_SEED) -> bytes:
    return hashlib.sha256(f"{seed}|{market_id}".encode()).digest()


def pool_order(frozen: Iterable[SelectedMarket], cutoff: datetime = SPLIT_CUTOFF, gap: timedelta = SPLIT_GAP,
               test_end: Optional[datetime] = TEST_DECISION_END,
               seed: str = SAMPLE_ORDER_SEED) -> Tuple[Dict[str, List[SelectedMarket]], Dict[str, int]]:
    """Each pool in fetch order (sha256(seed|market id), the full digest), plus the
    count of markets in every category. Uses market IDs and dates only."""
    pools: Dict[str, List[SelectedMarket]] = {p: [] for p in POOLS}
    counts = {k: 0 for k in (*POOLS, "straddling", "after_test_window")}
    for m in frozen:
        p = pool_of(m, cutoff, gap, test_end)
        counts[p] += 1
        if p in pools:
            pools[p].append(m)
    for p in POOLS:
        pools[p].sort(key=lambda m: (sample_rank(m.market_id, seed), m.market_id))
    return pools, counts


def pool_targets(need: Mapping[str, int] = POOL_NEED, reserve_percent: int = POOL_RESERVE_PERCENT) -> Dict[str, int]:
    """Need plus the reserve, rounded up (integer arithmetic, so 7,200 + 15% is 8,280)."""
    return {p: n + -(-n * reserve_percent // 100) for p, n in need.items()}


def history_exclusion(times: Iterable[int], td: datetime) -> Optional[str]:
    """Why a price history is unusable at ``td`` (the same reasons, in the same order,
    as ``decision_features``), or None. Takes the TIMESTAMPS only, so whether a market
    counts toward its pool can never depend on a price value."""
    limit = td.timestamp()
    past = [t for t in times if t < limit]
    if not past:
        return "no_price_before_decision"
    if limit - max(past) > MAX_PRICE_STALENESS.total_seconds():
        return "stale_price"
    if not any(t <= limit - RECENT_CHANGE_WINDOW.total_seconds() for t in past):
        return "no_price_before_window"
    return None


def fill_pools(frozen: Sequence[SelectedMarket], fetch: Callable[[SelectedMarket], Sequence[Tuple[int, float]]],
               have: Mapping[str, Sequence[Sequence[float]]] = (), targets: Optional[Mapping[str, int]] = None,
               cutoff: datetime = SPLIT_CUTOFF, gap: timedelta = SPLIT_GAP,
               test_end: Optional[datetime] = TEST_DECISION_END, seed: str = SAMPLE_ORDER_SEED) -> dict:
    """Walk each pool in ``pool_order`` and stop once ``targets[pool]`` markets have a
    usable history. Histories already in ``have`` are reused (restartable); others are
    fetched with ``fetch`` in order. Sees no outcome (the frozen list has none) and
    judges each history by its timestamps alone (``history_exclusion``).

    Returns the plan: per pool the target, the pool size, how many were considered
    and newly fetched, the exclusions by reason, whether the target was reached and the
    usable market IDs in order."""
    targets = dict(pool_targets() if targets is None else targets)
    have = dict(have or {})
    pools, categories = pool_order(frozen, cutoff, gap, test_end, seed)
    plan: dict = {"seed": seed, "cutoff": cutoff.isoformat(), "gap_days": gap.total_seconds() / 86400,
                  "test_end": test_end.isoformat() if test_end else None, "categories": categories, "pools": {}}
    for p in POOLS:
        usable: List[str] = []
        excluded: Dict[str, int] = {}
        considered = fetched = 0
        for m in pools[p]:
            if len(usable) >= targets[p]:
                break
            considered += 1
            if m.market_id in have:
                hist = have[m.market_id]
            else:
                hist = have[m.market_id] = fetch(m)
                fetched += 1
            why = history_exclusion((int(pt[0]) for pt in hist), parse_time(m.decision_time))
            if why is None:
                usable.append(m.market_id)
            else:
                excluded[why] = excluded.get(why, 0) + 1
        plan["pools"][p] = {"target": targets[p], "pool_size": len(pools[p]), "considered": considered,
                            "fetched_now": fetched, "usable": len(usable), "excluded_by_reason": excluded,
                            "reached": len(usable) >= targets[p], "usable_ids": usable}
    return plan


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


def split_train_test(built: Sequence[BuiltMarket], cutoff: datetime, gap: timedelta = DEFAULT_SPLIT_GAP,
                     test_end: Optional[datetime] = None) -> Tuple[List[BuiltMarket], List[BuiltMarket], Dict[str, int]]:
    """Training: resolved before ``cutoff``, in resolution order. Test: decided at or
    after ``cutoff + gap`` (and before ``test_end``, if given), in decision-time order.
    Everything else is counted."""
    train = sorted((b for b in built if parse_time(b.market.closed_time) < cutoff),
                   key=lambda b: (parse_time(b.market.closed_time), b.market.market_id))
    late = [b for b in built if test_end is not None and parse_time(b.market.decision_time) >= test_end]
    test = sorted((b for b in built if cutoff + gap <= parse_time(b.market.decision_time)
                   and (test_end is None or parse_time(b.market.decision_time) < test_end)),
                  key=lambda b: (parse_time(b.market.decision_time), b.market.market_id))
    straddling = len(built) - len(train) - len(test) - len(late)
    counts = {"train": len(train), "test": len(test), "straddling_excluded": straddling}
    if test_end is not None:
        counts["after_test_window_excluded"] = len(late)
    return train, test, counts


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
