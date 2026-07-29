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
(OA finding 13) — the parser accepts both shapes.

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
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

from wcmodel.data.store import BitemporalStore, Policy

ODDSAPI_BASE = "https://api.the-odds-api.com/v4"

#: Default raw-response archive: content-addressed ``<sha256>.json`` under the
#: gitignored ``/data/`` tree, anchored at the repo root (like every other
#: repo-root path in ``src/wcmodel/``) because no consumer of this adapter owns
#: the cwd. Every PAID historical response is persisted here by default so its
#: hash can be cited by the forecast ledger (``odds_snapshot_hash``) and the
#: exact bytes re-audited without spending a second credit.
_REPO_ROOT = Path(__file__).resolve().parents[4]
ODDS_RAW_DIR = _REPO_ROOT / "data" / "odds_raw"

# Keys identifying which top-level entries of the fixture/sample are snapshots.
_SNAPSHOT_REQUIRED = ("timestamp", "data")


def _parse_ts(ts: str) -> datetime:
    """Parse an Odds API ISO-8601 timestamp (trailing 'Z') to an aware datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _event_list(data) -> list[dict]:
    """Normalize a snapshot's ``data`` payload to a list of events.

    The multi-event routes return a LIST of events; the per-event historical
    route (``/historical/sports/{sport}/events/{id}/odds``) wraps ONE bare
    event DICT (OA finding 13). Both are real recorded response shapes.
    """
    if isinstance(data, dict):
        return [data]
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
    for event in _event_list(snapshot.get("data")):
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


def admissible_quote(snapshot_ts: datetime, last_update: datetime,
                     t_issue: datetime, *, buffer_minutes: int = 30) -> bool:
    """A quote is usable at issuance only if BOTH its snapshot and the
    bookmaker's own last_update predate t_issue minus the safety buffer
    (STRICT <, finding 2)."""
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
    contexts): BOTH the snapshot ``timestamp`` AND the bookmaker's own
    ``last_update`` must strictly predate ``commence_time``. An at/after-kickoff
    stamp on either leg is an in-play price, never a closing quote (OA F2).
    Where a source omits ``last_update`` the snapshot timestamp stands in. For
    the bundled fixture this resolves to the ``close`` snapshot.

    Returns ``{bookmaker, snapshot_ts, outcomes: {name: price, ...}}``.
    """
    snapshots = [
        v for v in sample.values()
        if isinstance(v, dict) and all(k in v for k in _SNAPSHOT_REQUIRED)
    ]

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
                _parse_ts(r["bookmaker_last_update"] or snap["timestamp"]),
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
    return {
        "bookmaker": bookmaker,
        "snapshot_ts": chosen["timestamp"],
        "outcomes": outcomes,
    }


def _persist_raw(content: bytes, raw_dir: Path | str | None) -> str:
    """sha256 the raw response bytes; persist them content-addressed.

    Written as ``<raw_dir>/<sha256>.json`` (skipped when the file already
    exists — same bytes, same name), so a paid response is never lost and the
    hash the ledger cites always resolves to the exact bytes it was computed
    from. ``raw_dir=None`` disables persistence (hash still returned).
    """
    digest = hashlib.sha256(content).hexdigest()
    if raw_dir is not None:
        directory = Path(raw_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest}.json"
        if not path.exists():
            path.write_bytes(content)
    return digest


def fetch_historical(
    event_id: str,
    ts: str,
    api_key: str | None,
    *,
    market: str = "h2h",
    regions: str = "eu",
    sport_key: str | None = None,
    raw_dir: Path | str | None = ODDS_RAW_DIR,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Pull a real historical snapshot from The Odds API (network, PAID).

    GATED: raises without an ``api_key`` (Phase-0 decision 1) and then without
    an explicit ``sport_key`` — the generic ``soccer`` key this function used
    to hardcode is INVALID on The Odds API, so refusing beats spending a credit
    on a guaranteed miss (OA F13). Callers take the per-competition key from
    config ``odds.sport_keys`` (config-driven so the OA-0a probe can correct a
    wrong key without a code change).

    The raw response bytes are sha256-hashed and persisted content-addressed
    under ``raw_dir`` (default ``data/odds_raw/<sha256>.json``; ``None``
    disables), and the hash is attached to the returned snapshot as
    ``raw_sha256`` — the provenance link the forecast ledger's
    ``odds_snapshot_hash`` cites. ``transport`` injects an
    ``httpx.MockTransport`` in tests; ``None`` uses the real network.
    """
    if api_key is None:
        raise RuntimeError(
            "Odds API pull gated: no api_key — see Phase-0 decision 1"
        )
    if sport_key is None:
        raise ValueError(
            "sport_key required: the generic 'soccer' key is invalid on The "
            "Odds API — pass the per-competition key from config "
            "odds.sport_keys (OA F13)"
        )
    # Documented historical endpoint:
    #   GET /v4/historical/sports/{sport}/events/{eventId}/odds
    #   ?apiKey=&date=&markets=&regions=&oddsFormat=decimal
    url = f"{ODDSAPI_BASE}/historical/sports/{sport_key}/events/{event_id}/odds"
    with httpx.Client(transport=transport, timeout=30.0) as client:
        resp = client.get(
            url,
            params={
                "apiKey": api_key,
                "date": ts,
                "markets": market,
                "regions": regions,
                "oddsFormat": "decimal",
            },
        )
    resp.raise_for_status()
    digest = _persist_raw(resp.content, raw_dir)
    payload = resp.json()
    if isinstance(payload, dict):
        payload["raw_sha256"] = digest
    return payload


def fetch_historical_events(
    sport_key: str,
    ts: str,
    api_key: str | None,
    *,
    raw_dir: Path | str | None = ODDS_RAW_DIR,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Discover the events visible at historical time ``ts`` (network, PAID).

    GATED like :func:`fetch_historical`: raises without an ``api_key``, and
    tests drive it only through an injected ``httpx.MockTransport``. Hits the
    documented discovery endpoint
    ``GET /v4/historical/sports/{sport}/events?date=…`` and returns one row per
    event: ``{event_id, commence_time, home, away}`` (team names ``None`` where
    the API has not yet named a knockout pairing). The raw response is
    persisted content-addressed under ``raw_dir`` like the snapshot route.
    """
    if api_key is None:
        raise RuntimeError(
            "Odds API pull gated: no api_key — see Phase-0 decision 1"
        )
    url = f"{ODDSAPI_BASE}/historical/sports/{sport_key}/events"
    with httpx.Client(transport=transport, timeout=30.0) as client:
        resp = client.get(url, params={"apiKey": api_key, "date": ts})
    resp.raise_for_status()
    _persist_raw(resp.content, raw_dir)
    payload = resp.json()
    data = payload.get("data") if isinstance(payload, dict) else payload
    return [
        {
            "event_id": event["id"],
            "commence_time": event["commence_time"],
            "home": event.get("home_team"),
            "away": event.get("away_team"),
        }
        for event in _event_list(data)
    ]


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
