"""The Odds API adapter (historical odds snapshots).

We benchmark closing-line value (CLV) against the **Pinnacle closing** line, so
we need (a) a bet-time snapshot and (b) a near-kickoff "close" snapshot — i.e. a
short time series per event. The Odds API *historical* endpoint returns one
snapshot per call:

    {"timestamp", "previous_timestamp", "next_timestamp",
     "data": [ {"id", "sport_key", "commence_time", "home_team", "away_team",
                "bookmakers": [ {"key", "last_update",
                                 "markets": [ {"key": "h2h",
                                               "outcomes": [ {"name", "price"} ]} ]} ]} ]}

Store policy for odds is **POINT_IN_TIME** (timestamped): we record what the
market said at a moment, and that fact never gets revised, so
`valid_as_of == observed_at == snapshot timestamp` (north-star §4.2).

Gating: the live historical pull is **paid** and pricing is being verified
separately, so `fetch_historical` *raises* without an `api_key` and is never
exercised by tests (Phase-0 decision 1). The parse/extract/load functions are
pure and work entirely off a hand-built fixture — no network.

Betfair traded-volume / market depth is NOT in this feed and is deliberately
NOT fabricated here (deferred).
"""
from __future__ import annotations

from datetime import datetime

import httpx
import pandas as pd

from wcmodel.data.store import BitemporalStore, Policy

ODDSAPI_BASE = "https://api.the-odds-api.com/v4"

# Keys identifying which top-level entries of the fixture/sample are snapshots.
_SNAPSHOT_REQUIRED = ("timestamp", "data")


def _parse_ts(ts: str) -> datetime:
    """Parse an Odds API ISO-8601 timestamp (trailing 'Z') to an aware datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def parse_snapshot(snapshot: dict) -> list[dict]:
    """Flatten ONE Odds API snapshot into per-outcome rows. Pure; no network.

    Iterates events -> bookmakers -> markets where ``key == "h2h"`` -> outcomes,
    emitting one dict per outcome. ``snapshot_ts`` is the snapshot's own
    ``timestamp`` (the observation time), not a bookmaker's ``last_update``.
    """
    snapshot_ts = snapshot["timestamp"]
    rows: list[dict] = []
    for event in snapshot.get("data", []):
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
                    })
    return rows


def extract_closing_prices(sample: dict, bookmaker: str) -> dict:
    """Pick the closing snapshot (latest timestamp <= commence_time) and return
    that bookmaker's h2h prices. Pure; no network.

    ``sample`` is a mapping whose values are full snapshots (e.g. ``bet_time``,
    ``close``). Among snapshots whose ``timestamp`` is at or before kickoff, we
    take the latest — the line nearest the close. For the bundled fixture this
    resolves to the ``close`` snapshot.

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
        # Closing line: nearest kickoff without crossing it.
        if any(_parse_ts(r["commence_time"]) < ts for r in rows):
            continue
        if chosen_ts is None or ts > chosen_ts:
            chosen, chosen_ts = snap, ts

    if chosen is None:
        raise ValueError(
            f"no closing snapshot for bookmaker={bookmaker!r} at/before kickoff"
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


def fetch_historical(
    event_id: str,
    ts: str,
    api_key: str | None,
    *,
    market: str = "h2h",
    regions: str = "eu",
) -> dict:
    """Pull a real historical snapshot from The Odds API (network, PAID).

    GATED: pricing is being verified separately and no key is available, so this
    raises without an ``api_key`` and is never called by tests. When a key is
    supplied it hits the documented historical endpoint and returns the parsed
    JSON snapshot.
    """
    if api_key is None:
        raise RuntimeError(
            "Odds API pull gated: no api_key — see Phase-0 decision 1"
        )
    # Documented historical endpoint:
    #   GET /v4/historical/sports/{sport}/events/{eventId}/odds
    #   ?apiKey=&date=&markets=&regions=&oddsFormat=decimal
    url = f"{ODDSAPI_BASE}/historical/sports/soccer/events/{event_id}/odds"
    resp = httpx.get(
        url,
        params={
            "apiKey": api_key,
            "date": ts,
            "markets": market,
            "regions": regions,
            "oddsFormat": "decimal",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def load_odds_snapshots(store: BitemporalStore, sample: dict) -> None:
    """Parse every snapshot in ``sample`` and append to the bitemporal store.

    Odds are POINT_IN_TIME: ``valid_as_of == observed_at == snapshot_ts`` (the
    moment the market was observed). Pure parse path — no network.
    """
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
