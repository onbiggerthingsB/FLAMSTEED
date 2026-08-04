"""The Odds API adapter (historical odds snapshots).

We benchmark closing-line value (CLV) against the **Pinnacle closing** line, so
we need (a) a bet-time snapshot and (b) a near-kickoff "close" snapshot — i.e. a
short time series per event. The Odds API *historical* endpoints return one
snapshot per call:

    {"timestamp", "previous_timestamp", "next_timestamp",
     "data": ... {"id", "sport_key", "commence_time", "home_team", "away_team",
                  "bookmakers": [ {"key", "last_update",
                                   "markets": [ {"key": "h2h", "last_update",
                                                 "outcomes": [ {"name", "price"} ]} ]} ]} ...}

where ``data`` is a LIST of events on the multi-event routes but ONE bare event
object on the per-event route ``/historical/sports/{sport}/events/{id}/odds``
(OA finding 13) — the parser accepts both shapes via :func:`event_list`, the
ONE dict/list normalizer (``backtest.odds_ingest``, ``scripts/clv_validation.py``
and the ``live`` decide/validation/scan modules import it rather than keeping
private copies).

Store policy for odds is **POINT_IN_TIME** (timestamped): we record what the
market said at a moment, and that fact never gets revised, so
`valid_as_of == observed_at == snapshot timestamp` (north-star §4.2).

Gating: the live historical pull is **paid** and pricing is being verified
separately, so `fetch_historical` / `fetch_historical_events` *raise* without an
`api_key` and are exercised by tests only through injected ``httpx.MockTransport``
(Phase-0 decision 1 — zero live calls). The parse/extract/load functions are
pure and work entirely off a hand-built fixture — no network.

Betfair traded-volume / market depth is NOT in this feed and is deliberately
NOT fabricated here (deferred).
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

from wcmodel.data.store import BitemporalStore, Policy


def _silence_httpx_request_logging() -> None:
    """httpx's own logger prints the FULL request line — query string, so the
    API key — at INFO on EVERY call, success and failure alike. The redaction
    helpers cover exceptions; this covers the 200s. Called by both paid
    fetchers before any network touch (idempotent; WARNING keeps real
    transport warnings visible)."""
    logging.getLogger("httpx").setLevel(logging.WARNING)

ODDSAPI_BASE = "https://api.the-odds-api.com/v4"

#: Default raw-response archive: content-addressed ``<sha256>.json`` under the
#: gitignored ``/data/`` tree, anchored at the repo root (like every other
#: repo-root path in ``src/wcmodel/``) because no consumer of this adapter owns
#: the cwd. Every PAID historical response is persisted here by default so its
#: hash can be cited by the forecast ledger (``odds_snapshot_hash``) and the
#: exact bytes re-audited without spending a second credit.
_REPO_ROOT = Path(__file__).resolve().parents[4]
ODDS_RAW_DIR = _REPO_ROOT / "data" / "odds_raw"

#: Sentinel for "caller said nothing about raw_dir". The default must resolve
#: AGAINST the transport — an injected (mock/dry-run) transport serves
#: fabricated bytes that must never land in the real repo archive, while a
#: real network response is paid evidence and must — and a plain parameter
#: default cannot see the transport.
_RAW_DIR_UNSET = object()

# Keys identifying which top-level entries of the fixture/sample are snapshots.
_SNAPSHOT_REQUIRED = ("timestamp", "data")


def _require_sport_key(sport_key) -> None:
    """ONE validator for both paid endpoints (Codex finding 6): a None,
    non-string, or blank/whitespace ``sport_key`` must refuse BEFORE any
    logger/client/transport work — ``""`` builds the malformed route
    ``/historical/sports//events``, a PAID request to an endpoint that can
    only answer with a billed error. The generic ``soccer`` key this adapter
    once hardcoded is equally invalid (OA F13): callers take the
    per-competition key from config ``odds.sport_keys``."""
    if not isinstance(sport_key, str) or not sport_key.strip():
        raise ValueError(
            f"sport_key required: got {sport_key!r} — pass the non-blank "
            "per-competition key from config odds.sport_keys (the generic "
            "'soccer' key is invalid on The Odds API, OA F13)"
        )


def _parse_ts(ts: str) -> datetime:
    """Parse an Odds API ISO-8601 timestamp (trailing 'Z') to an aware datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def event_list(data) -> list[dict]:
    """Normalize a snapshot's ``data`` payload to a list of events.

    The multi-event routes return a LIST of events; the per-event historical
    route (``/historical/sports/{sport}/events/{id}/odds``) wraps ONE bare
    event DICT (OA finding 13). Both are real recorded response shapes.

    EXPORTED as the ONE normalizer for this dual shape: every consumer that
    reads a raw snapshot's ``data`` directly (``backtest.odds_ingest``,
    ``scripts/clv_validation.py``, ``live.decide`` / ``live.validation`` /
    ``live.scan``) goes through here — a private shape assumption per module
    is how the dict shape got missed on two of the first three paths, then
    again on the live ones. (``clv_validation``'s later ``["data"][0]`` reads
    consume its OWN ``_snapshot_to_real_shape`` output, list-shaped by
    construction — not the raw payload.)

    An EMPTY payload — ``{}``, ``[]``, ``None`` — is ZERO events: ``{}`` is
    not an event, and a truthy ``[{}]`` would turn the previously-silent
    empty case into ``KeyError('id')`` in every consumer (matching how
    ``clv_validation``'s real-shape builder already treats falsy ``data``).
    """
    if isinstance(data, dict):
        return [data] if data else []
    return list(data or [])


def parse_snapshot(snapshot: dict) -> list[dict]:
    """Flatten ONE Odds API snapshot into per-outcome rows. Pure; no network.

    Iterates events -> bookmakers -> markets where ``key == "h2h"`` -> outcomes,
    emitting one dict per outcome. ``data`` may be a list of events OR one bare
    event dict (the per-event historical route). ``snapshot_ts`` is the
    snapshot's own ``timestamp`` (the observation time); the bookmaker's and
    market's own ``last_update`` stamps are RETAINED per row (``None`` where a
    source omits them) so admissibility can check the quote's true age, not
    just when we happened to observe it (OA F2/F13).
    """
    snapshot_ts = snapshot["timestamp"]
    rows: list[dict] = []
    for event in event_list(snapshot.get("data")):
        event_id = event["id"]
        commence_time = event["commence_time"]
        for book in event.get("bookmakers", []):
            bookmaker = book["key"]
            for market in book.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    rows.append({
                        "event_id": event_id,
                        "bookmaker": bookmaker,
                        "outcome": outcome["name"],
                        "price": outcome["price"],
                        "snapshot_ts": snapshot_ts,
                        "commence_time": commence_time,
                        "bookmaker_last_update": book.get("last_update"),
                        "market_last_update": market.get("last_update"),
                    })
    return rows


def parse_totals_snapshot(event: dict) -> dict:
    """Parse ONE Odds-API event's ``totals`` market into per-book, per-line over/under decimals.

    Returns ``{"home_team","away_team","commence_time","books": {book: {line: {over_odds, under_odds}}}}``.
    A line is emitted ONLY when BOTH Over and Under are present (a half-priced line is dropped — never
    a one-sided bet). Non-``totals`` markets are ignored. Pure; no network.
    """
    books: dict[str, dict[float, dict[str, float]]] = {}
    for book in event.get("bookmakers", []) or []:
        bkey = book.get("key")
        per_line: dict[float, dict[str, float]] = {}
        for market in book.get("markets", []) or []:
            if market.get("key") != "totals":
                continue
            for o in market.get("outcomes", []) or []:
                pt = o.get("point")
                name = (o.get("name") or "").lower()
                price = o.get("price")
                if pt is None or price is None or name not in ("over", "under"):
                    continue
                per_line.setdefault(float(pt), {})[f"{name}_odds"] = float(price)
        # keep only complete (both-sided) lines
        complete = {L: v for L, v in per_line.items() if "over_odds" in v and "under_odds" in v}
        if complete:
            books[bkey] = complete
    return {"home_team": event.get("home_team"), "away_team": event.get("away_team"),
            "commence_time": event.get("commence_time"), "books": books}


def strictest_last_update(row: dict, snapshot_ts: str) -> datetime:
    """The strictest available evidence for a quote's age: the LATEST of the
    stamps the row actually carries — the bookmaker-level AND the h2h-market-
    level ``last_update`` (the market stamp is the age of the price itself).
    Only when a source omits BOTH does the snapshot timestamp stand in, which
    collapses admissibility leg 2 into leg 1 — the weakest position, taken
    last, never the default (OA F2).

    EXPORTED (like :func:`event_list`, and for the same reason): this is the
    binding stamp-resolution contract :func:`admissible_quote` requires of its
    callers, so the T5 ledger imports it rather than keeping a private copy —
    a private re-implementation is exactly where the ``or snapshot_ts``
    weakening crept in before."""
    stamps = [s for s in (row["bookmaker_last_update"],
                          row["market_last_update"]) if s]
    if not stamps:
        return _parse_ts(snapshot_ts)
    return max(_parse_ts(s) for s in stamps)


def admissible_quote(snapshot_ts: datetime, last_update: datetime,
                     t_issue: datetime, *, buffer_minutes: int = 30) -> bool:
    """A quote is usable at issuance only if BOTH its snapshot and the
    bookmaker's own last_update predate t_issue minus the safety buffer
    (STRICT <, finding 2).

    ``last_update=None`` is a CALLER error (it raises TypeError, loudly — the
    check precedes the comparison, so a failing snapshot leg cannot
    short-circuit an unresolved stamp into a quiet False): this
    helper never guesses a quote's age. A source that omits the stamp must be
    resolved BY THE CALLER to the strictest evidence it does have — the latest
    of the stamps present, the snapshot timestamp only when there is none
    (:func:`strictest_last_update`, the resolution
    :func:`extract_closing_prices` uses). An unconditional ``or snapshot_ts``
    fallback instead makes leg 2 vacuous exactly when stricter evidence is
    available — the T5 ledger must not copy that weakening.

    ``buffer_minutes`` must be >= 0 (Codex finding 7): the subtraction takes
    any integer, and a NEGATIVE buffer moves the cut AFTER ``t_issue`` —
    the safety window reverses and a quote stamped after issuance (an
    in-play price) reads admissible. Refused loudly, never computed.
    """
    if buffer_minutes < 0:
        raise ValueError(
            f"admissible_quote: buffer_minutes must be >= 0 (got "
            f"{buffer_minutes}) — a negative buffer moves the cut AFTER "
            "t_issue, reversing the safety window so post-issuance in-play "
            "quotes read admissible (Codex finding 7)"
        )
    if last_update is None:
        raise TypeError(
            "admissible_quote: last_update is None — resolve the missing "
            "stamp to the strictest evidence available BEFORE calling "
            "(strictest_last_update); this helper never guesses a quote's "
            "age (OA F2)"
        )
    cut = t_issue - timedelta(minutes=buffer_minutes)
    return snapshot_ts < cut and last_update < cut


def extract_closing_prices(sample: dict, bookmaker: str) -> dict:
    """Pick the closing snapshot (latest timestamp strictly before kickoff) and
    return that bookmaker's h2h prices. Pure; no network.

    ``sample`` is a mapping whose values are full snapshots (e.g. ``bet_time``,
    ``close``). Among snapshots admissible for that bookmaker we take the
    latest — the line nearest the close. Admissibility is the STRICT
    :func:`admissible_quote` rule at the kickoff cut (buffer 0 — kickoff IS the
    cut for a closing line; the 30-minute issuance buffer belongs to ``t_issue``
    contexts): BOTH the snapshot ``timestamp`` AND the quote's own
    ``last_update`` must strictly predate ``commence_time``. An at/after-kickoff
    stamp on either leg is an in-play price, never a closing quote (OA F2).
    The ``last_update`` leg is the STRICTEST available evidence — the latest of
    the bookmaker-level and h2h-market-level stamps the row carries; only where
    a source omits both does the snapshot timestamp stand in
    (:func:`strictest_last_update`).

    SINGLE-EVENT-ONLY: the return shape (one flat outcomes map, one kickoff
    cut) cannot describe more than one event — outcome names would collide
    across events and one kicked-off fixture would veto the bookmaker's whole
    snapshot — and the identity is enforced BOTH within each snapshot AND
    across the sample: a sample of single-event snapshots for two DIFFERENT
    fixtures is the same defect one level up (latest-timestamp-wins would
    silently attach another match's closing line to this fixture), so either
    shape is REFUSED loudly. Split multi-event responses per event and
    assemble samples per fixture (the per-event historical route returns one
    event per call). For the bundled fixture this resolves to the ``close``
    snapshot.

    Returns ``{event_id, bookmaker, snapshot_ts, outcomes: {name: price, ...}}``
    — ``event_id`` names the fixture the line belongs to, so a caller can
    assert it got the event it asked about.
    """
    snapshots = [
        v for v in sample.values()
        if isinstance(v, dict) and all(k in v for k in _SNAPSHOT_REQUIRED)
    ]

    event_ids: set[str] = set()
    for snap in snapshots:
        events = event_list(snap.get("data"))
        if len(events) > 1:
            raise ValueError(
                f"extract_closing_prices is single-event-only: a snapshot "
                f"holds {len(events)} events, and one flat outcomes map "
                "cannot describe more (names collide across events; one "
                "kicked-off fixture would veto them all). Split the snapshot "
                "per event first (OA F13)."
            )
        event_ids.update(e["id"] for e in events)
    if len(event_ids) > 1:
        raise ValueError(
            f"extract_closing_prices is single-event-only: the sample's "
            f"snapshots span {len(event_ids)} distinct events "
            f"({sorted(event_ids)}) — latest-timestamp-wins would silently "
            "attach another fixture's closing line to this one. Assemble the "
            "sample per fixture (OA F13)."
        )

    chosen: dict | None = None
    chosen_ts: datetime | None = None
    for snap in snapshots:
        rows = [r for r in parse_snapshot(snap) if r["bookmaker"] == bookmaker]
        if not rows:
            continue
        ts = _parse_ts(snap["timestamp"])
        if not all(
            admissible_quote(
                ts,
                strictest_last_update(r, snap["timestamp"]),
                _parse_ts(r["commence_time"]),
                buffer_minutes=0,
            )
            for r in rows
        ):
            continue
        if chosen_ts is None or ts > chosen_ts:
            chosen, chosen_ts = snap, ts

    if chosen is None:
        raise ValueError(
            f"no admissible closing snapshot for bookmaker={bookmaker!r} "
            "strictly before kickoff (OA F2)"
        )

    outcomes = {
        r["outcome"]: r["price"]
        for r in parse_snapshot(chosen)
        if r["bookmaker"] == bookmaker
    }
    # A chosen snapshot has >=1 event, and the guard capped the union at 1.
    (event_id,) = event_ids
    return {
        "event_id": event_id,
        "bookmaker": bookmaker,
        "snapshot_ts": chosen["timestamp"],
        "outcomes": outcomes,
    }


def _write_all(fd: int, data: bytes) -> None:
    """``os.write`` until every byte lands: a single call may return short
    (signals, pipes-adjacent filesystems), and a short archive write is a
    torn file with a content-addressed name."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def fsync_dir(directory: Path | str) -> None:
    """fsync a DIRECTORY: after a rename or file creation the new directory
    entry is metadata, and fsync'ing the file alone leaves an entry that can
    vanish on power loss — durable bytes nobody can find by name. Loud on
    failure (OSError propagates): callers treat broken provenance storage as
    fatal, never as a note."""
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _persist_raw(content: bytes, raw_dir: Path | str | None) -> str:
    """sha256 the raw response bytes; persist them content-addressed, DURABLY.

    Written as ``<raw_dir>/<sha256>.json``, so a paid response is never lost
    and the hash the ledger cites always resolves to the exact bytes it was
    computed from. That invariant is VERIFIED, not assumed: existence alone
    is no proof — an interrupted earlier write can leave a file NAMED
    ``<sha256>.json`` holding other bytes, and a skip-on-existence dedupe
    would trust the torn file forever. A file already holding the same bytes
    is left alone; anything else is (re)written via a same-directory tmp file
    + ``os.replace``, so the content-addressed name only ever holds complete
    content (pid-suffixed tmp so concurrent processes archiving the same
    response cannot interleave).

    Durability ordering (plan2 batch-1, finding 3): the tmp file is fsync'd
    BEFORE the rename — renaming unfsync'd bytes can survive power loss as a
    correct name holding a torn file, which a durable RECEIPT then cites
    forever — and the directory is fsync'd AFTER, so the rename itself cannot
    vanish out from under that receipt. Short writes are completed, never
    truncated (:func:`_write_all`). ``raw_dir=None`` disables persistence
    (hash still returned).
    """
    digest = hashlib.sha256(content).hexdigest()
    if raw_dir is not None:
        directory = Path(raw_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest}.json"
        if not (path.exists() and path.read_bytes() == content):
            tmp = directory / f"{digest}.json.{os.getpid()}.tmp"
            try:
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                             0o644)
                try:
                    _write_all(fd, content)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.replace(tmp, path)
                fsync_dir(directory)
            finally:
                tmp.unlink(missing_ok=True)
    return digest


def _resolve_raw_dir(raw_dir, transport: httpx.BaseTransport | None):
    """Resolve the ``raw_dir`` default AGAINST the transport. An injected
    transport serves mocked/dry-run bytes — a fabricated payload must never
    land in the real repo archive just because a test or dry-run forgot
    ``raw_dir=tmp_path``. Only a real network response (``transport=None``)
    is paid evidence that defaults into ``ODDS_RAW_DIR``. An EXPLICIT
    ``raw_dir`` (incl. ``None`` = disable) is always honored as given."""
    if raw_dir is _RAW_DIR_UNSET:
        return None if transport is not None else ODDS_RAW_DIR
    return raw_dir


def _raise_for_status_redacted(resp: httpx.Response, api_key: str,
                               raw_sha256: str | None = None) -> None:
    """``raise_for_status`` that cannot leak the key. httpx's HTTPStatusError
    message embeds the full request URL, and this API carries
    ``apiKey=<secret>`` in the query string — error strings from here get
    written into committed reports and session logs (the OA-0a probe's
    failure handler), which would exfiltrate the key through our own error
    handling. Before the message can exist, the response's request is
    re-pointed at the query-stripped URL (so ``exc.request.url`` /
    ``resp.url`` hold nothing to resurrect either), the key is belt-and-braces
    scrubbed from the final message, and the raise chains ``from None`` so no
    context exception carries the live URL into a rendered traceback.

    ``raw_sha256`` is the digest of the ALREADY-ARCHIVED paid error body,
    attached to the raised exception as an attribute (plan2 batch-1, finding
    7): a failure receipt records WHERE the paid evidence lives from it —
    a digest embedded only in the message is provenance a machine cannot
    cite.

    RESPONSE path only: a failure BELOW the HTTP layer never reaches here —
    :func:`_get_redacted` scrubs that leg (and carries no digest: no response
    bytes ever existed)."""
    if resp.is_success:
        return
    resp.request = httpx.Request(
        resp.request.method, resp.request.url.copy_with(query=None)
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # Belt-and-braces on top of the query-strip; guarded because
        # str.replace("", "***") would mangle the message char-by-char and
        # the None-gate upstream does not exclude an empty key.
        message = str(exc).replace(api_key, "***") if api_key else str(exc)
        redacted = httpx.HTTPStatusError(
            message, request=exc.request, response=resp)
        redacted.raw_sha256 = raw_sha256
        raise redacted from None


def _payload_error(message: str, raw_sha256: str | None) -> ValueError:
    """A malformed-200 refusal that carries its archive digest structurally
    (plan2 batch-1, finding 7) — the message already names the hash for the
    human; the attribute names it for the failure receipt."""
    err = ValueError(message)
    err.raw_sha256 = raw_sha256
    return err


def _decode_json(resp: httpx.Response, digest: str | None):
    """``resp.json()`` whose failure is a response-backed finding: a PAID 200
    with an undecodable body must still cite the archived bytes."""
    try:
        return resp.json()
    except ValueError:
        raise _payload_error(
            "unparseable JSON body on a PAID response — archived as "
            f"raw_sha256={digest} for audit", digest) from None


def _get_redacted(
    client: httpx.Client, url: str, params: dict, api_key: str
) -> httpx.Response:
    """``client.get`` whose TRANSPORT-level failures cannot leak the key.

    :func:`_raise_for_status_redacted` covers only the response path: a
    failure below the HTTP layer (read timeout, connection refused — against
    a paid API at least as likely as a 401/429) escapes ``client.get`` as an
    ``httpx.RequestError`` with the UNMODIFIED request attached by httpx's
    ``request_context``, so ``exc.request.url`` carried ``apiKey=<secret>``
    into the same committed-report failure handlers (the OA-0a probe). The
    re-raise keeps the exception TYPE (callers still catch ``ReadTimeout``
    etc.) but re-points the request at ``url`` — query-less by construction,
    since ``params`` ride separately — scrubs the key from the message
    belt-and-braces, and chains ``from None`` so the original exception
    (whose attached request still holds the live URL) never enters a
    rendered traceback."""
    try:
        return client.get(url, params=params)
    except httpx.RequestError as exc:
        message = str(exc).replace(api_key, "***") if api_key else str(exc)
        raise type(exc)(
            message, request=httpx.Request("GET", url)
        ) from None


def fetch_historical(
    event_id: str,
    ts: str,
    api_key: str | None,
    *,
    market: str = "h2h",
    regions: str = "eu",
    sport_key: str | None = None,
    raw_dir: Path | str | None = _RAW_DIR_UNSET,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Pull a real historical snapshot from The Odds API (network, PAID).

    GATED: raises without an ``api_key`` (Phase-0 decision 1) and then on any
    non-string or blank ``sport_key`` (:func:`_require_sport_key`) — the
    generic ``soccer`` key this function used to hardcode is INVALID on The
    Odds API, and a blank key builds a malformed paid route, so refusing
    beats spending a credit on a guaranteed miss (OA F13, Codex finding 6).
    Callers take the per-competition key from config ``odds.sport_keys``
    (config-driven so the OA-0a probe can correct a wrong key without a code
    change).

    The raw response bytes are sha256-hashed and persisted content-addressed
    under ``raw_dir`` BEFORE the HTTP status gate — a paid non-2xx body is
    still a paid response, and it is the evidence a quota/key failure gets
    audited from. The hash is attached to the returned snapshot as
    ``raw_sha256`` — the provenance link the forecast ledger's
    ``odds_snapshot_hash`` cites. When ``raw_dir`` is not given, the
    ``data/odds_raw/<sha256>.json`` default engages ONLY for real-network
    calls: with an injected ``transport`` (mocks, dry-runs) nothing is
    persisted unless the caller names a directory explicitly
    (:func:`_resolve_raw_dir`); ``None`` always disables. HTTP errors raise
    with the query string (which carries the key) stripped from message and
    attached request (:func:`_raise_for_status_redacted`); transport-level
    failures (timeout, connection) re-raise the same way via
    :func:`_get_redacted`.
    """
    if api_key is None:
        raise RuntimeError(
            "Odds API pull gated: no api_key — see Phase-0 decision 1"
        )
    _require_sport_key(sport_key)
    raw_dir = _resolve_raw_dir(raw_dir, transport)
    # Documented historical endpoint:
    #   GET /v4/historical/sports/{sport}/events/{eventId}/odds
    #   ?apiKey=&date=&markets=&regions=&oddsFormat=decimal
    url = f"{ODDSAPI_BASE}/historical/sports/{sport_key}/events/{event_id}/odds"
    _silence_httpx_request_logging()
    with httpx.Client(transport=transport, timeout=30.0) as client:
        resp = _get_redacted(
            client,
            url,
            {
                "apiKey": api_key,
                "date": ts,
                "markets": market,
                "regions": regions,
                "oddsFormat": "decimal",
            },
            api_key,
        )
    digest = _persist_raw(resp.content, raw_dir)
    _raise_for_status_redacted(resp, api_key, raw_sha256=digest)
    payload = _decode_json(resp, digest)
    # Mirror of the discovery guard below: a 200 whose shape is not the
    # documented {timestamp, previous_timestamp?, next_timestamp?, data}
    # wrapper must not pass as a snapshot — on a PAID call it would either
    # masquerade as coverage or (non-dict) return with NO raw_sha256, so the
    # T5 ledger would record None provenance for money spent.
    if not isinstance(payload, dict) or "timestamp" not in payload \
            or "data" not in payload:
        keys = sorted(payload) if isinstance(payload, dict) \
            else type(payload).__name__
        raise _payload_error(
            "unrecognized snapshot payload: expected a dict with 'timestamp' "
            f"and 'data', got {keys} — a changed shape on a PAID call must "
            f"not read as a snapshot; archived as raw_sha256={digest} for "
            "audit", digest)
    payload["raw_sha256"] = digest
    return payload


def fetch_historical_events(
    sport_key: str,
    ts: str,
    api_key: str | None,
    *,
    raw_dir: Path | str | None = _RAW_DIR_UNSET,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Discover the events visible at historical time ``ts`` (network, PAID).

    GATED like :func:`fetch_historical`: raises without an ``api_key`` and on
    a non-string/blank ``sport_key`` (:func:`_require_sport_key`, Codex
    finding 6), and tests drive it only through an injected
    ``httpx.MockTransport``. Hits the documented discovery endpoint
    ``GET /v4/historical/sports/{sport}/events?date=…`` and returns a
    RESPONSE envelope ``{"raw_sha256", "events"}`` — ONE paid response, ONE
    archived hash, carried at response level (Codex finding 4): hanging the
    hash on per-event rows lost it on exactly the empty/miss branches a
    coverage dispute audits ("event found: n" could cite no provenance at
    all, because there was no row to carry it). ``events`` holds one row per
    event: ``{event_id, commence_time, home, away}`` (team names ``None``
    where the API has not yet named a knockout pairing). The raw response is
    persisted content-addressed under ``raw_dir`` BEFORE the status gate,
    with the same transport-aware default and key-redacting error handling
    as the snapshot route.

    A dict payload WITHOUT a ``data`` key is REFUSED loudly (ValueError citing
    the archived hash): on a paid discovery call an unexpected/changed
    response shape must not read as a genuine "no events at this timestamp" —
    the probe would bill credits and report zero coverage as truth.
    ``{"data": []}`` remains the API's real empty answer (``events: []`` with
    the archived hash still on the envelope).
    """
    if api_key is None:
        raise RuntimeError(
            "Odds API pull gated: no api_key — see Phase-0 decision 1"
        )
    _require_sport_key(sport_key)
    raw_dir = _resolve_raw_dir(raw_dir, transport)
    url = f"{ODDSAPI_BASE}/historical/sports/{sport_key}/events"
    _silence_httpx_request_logging()
    with httpx.Client(transport=transport, timeout=30.0) as client:
        resp = _get_redacted(client, url, {"apiKey": api_key, "date": ts}, api_key)
    digest = _persist_raw(resp.content, raw_dir)
    _raise_for_status_redacted(resp, api_key, raw_sha256=digest)
    payload = _decode_json(resp, digest)
    if isinstance(payload, dict):
        if "data" not in payload:
            raise _payload_error(
                "unrecognized discovery payload: a dict without a 'data' key "
                f"(keys={sorted(payload)}) cannot be read as 'no events at "
                "this timestamp' on a PAID call — archived as "
                f"raw_sha256={digest} for audit", digest)
        data = payload["data"]
    else:
        data = payload
    return {
        "raw_sha256": digest,
        "events": [
            {
                "event_id": event["id"],
                "commence_time": event["commence_time"],
                "home": event.get("home_team"),
                "away": event.get("away_team"),
            }
            for event in event_list(data)
        ],
    }


def load_odds_snapshots(store: BitemporalStore, sample: dict) -> None:
    """Parse every snapshot in ``sample`` and append to the bitemporal store.

    Odds are POINT_IN_TIME: ``valid_as_of == observed_at == snapshot_ts`` (the
    moment the market was observed). Pure parse path — no network.

    DEFENSE-IN-DEPTH (betting-safety): this REFUSES to persist a synthetic sample
    as real. If the sample wrapper OR any of its snapshots carries the synthetic
    marker (``odds_ingest._SYNTHETIC_KEY``), it raises — a fabricated price can
    never enter the real odds store (``source=the_odds_api``) even if it leaks out
    of the harness wrapper. This is additive: real samples carry no marker and are
    unaffected.
    """
    # Function-local import: ``odds_ingest`` imports ``parse_snapshot`` from this
    # module, so importing it at top level would be circular. ONE source of truth
    # for the marker key (defined in ``odds_ingest``).
    from wcmodel.backtest.odds_ingest import _SYNTHETIC_KEY

    if sample.get(_SYNTHETIC_KEY) or any(
        isinstance(v, dict) and v.get(_SYNTHETIC_KEY) for v in sample.values()
    ):
        raise ValueError(
            "refusing to store synthetic odds as real (source=the_odds_api) — "
            "synthetic harness output must never enter the real odds store"
        )

    rows: list[dict] = []
    for value in sample.values():
        if isinstance(value, dict) and all(k in value for k in _SNAPSHOT_REQUIRED):
            rows.extend(parse_snapshot(value))
    if not rows:
        return
    df = pd.DataFrame(rows)
    df["valid_as_of"] = df["snapshot_ts"]
    df["observed_at"] = df["snapshot_ts"]
    store.write(
        "odds",
        df,
        policy=Policy.POINT_IN_TIME,
        keys=["event_id", "bookmaker", "outcome"],
        source="the_odds_api",
    )
