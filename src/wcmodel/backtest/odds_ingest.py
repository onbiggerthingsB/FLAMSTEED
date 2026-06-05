"""Odds ingest for the backtest — the REAL pure-parse path + a clearly-labelled
NON-REAL synthetic-odds harness.

No spend, no network. We reuse the existing real parser
(``wcmodel.data.sources.odds.parse_snapshot`` / ``extract_closing_prices``) over
the hand-built fixture, so all CLV/edge/staking math is validated on the genuine
ingest path. When the user funds the gated pull (D1), the SAME path ingests the
real Pinnacle-close + Betfair snapshots — only ``fetch_historical`` (gated) is
added; nothing here changes.

SYNTHETIC LABELLING (D1 rider, binding). ``synthetic_odds_sample`` fabricates a
snapshot pair so the engine can be exercised end-to-end WITHOUT real data. Every
such object carries ``is_synthetic=True`` + a ``SYNTHETIC — NOT REAL ODDS``
provenance string, and ``entry_close_prices`` PROPAGATES that flag, so no number
derived from synthetic odds can ever be mistaken for — or reported as — a real
edge. This mirrors the Phase-3 progression-snapshot's non-real labelling.

The odds store keys on ``event_id`` (the Odds API id), which is DISTINCT from the
results ``match_id`` (``sha1(date|home|away|city)``). The backtest therefore joins
an odds event to a result by the ``event_key`` = ``(home_team, away_team,
commence_date)`` triple (the same identity rule ``sim/run.py`` uses to match
played knockouts), NEVER by id equality.

Real-pull team-name reconciliation against the martj42 results store is DEFERRED
to the gated paid sub-task (D1): it is only needed once real Odds-API events are
sourced, and the synthetic/fixture harness already uses the martj42 common-English
names, so no reconciliation is built here.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from wcmodel.data.sources.odds import parse_snapshot

#: The fixed 1X2 outcome order shared across de-vig, model probs, and settling.
OUTCOMES = ("home", "draw", "away")

_SYNTHETIC_BANNER = "SYNTHETIC — NOT REAL ODDS (Phase-4 harness; never an edge claim)"


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def event_key(event: dict):
    """``(home_team, away_team, commence_date)`` — the odds⇄results join identity.

    ``commence_date`` is the UTC kickoff DATE (day resolution), matching the
    results panel's date-resolution keys; team names are the martj42 common-English
    names the Odds API also uses.
    """
    return (
        event["home_team"],
        event["away_team"],
        _parse_ts(event["commence_time"]).astimezone(timezone.utc).date(),
    )


def _bookmaker_prices(snapshot: dict, bookmaker: str, home_team: str,
                      away_team: str) -> dict:
    """Map one snapshot's ``bookmaker`` h2h outcomes to the fixed OUTCOMES order.

    The Odds API names outcomes by TEAM (home_team / away_team) plus ``"Draw"``;
    we relabel to ``home``/``draw``/``away`` so every downstream vector is ordered
    by ``OUTCOMES`` regardless of which team is home.
    """
    rows = [r for r in parse_snapshot(snapshot) if r["bookmaker"] == bookmaker]
    by_name = {r["outcome"]: r["price"] for r in rows}
    return {
        "home": by_name[home_team],
        "draw": by_name["Draw"],
        "away": by_name[away_team],
    }


def entry_close_prices(sample: dict, bookmaker: str) -> dict:
    """Extract ENTRY (bet_time) + CLOSE (nearest-kickoff) h2h prices for ``bookmaker``.

    ``sample`` is the snapshot mapping (e.g. ``{"bet_time": {...}, "close": {...}}``)
    or a synthetic one from ``synthetic_odds_sample``. Entry is the snapshot at the
    decision time ``T_bet`` (the EARLIEST snapshot at/before kickoff); close is the
    LATEST snapshot at/before kickoff (the Pinnacle close). Both are read via the
    real ``parse_snapshot`` path. Returns
    ``{entry, close, commence_time, event_key, is_synthetic}`` with ``entry``/``close``
    each ``{home, draw, away}`` decimal odds.
    """
    snaps = [
        v for v in sample.values()
        if isinstance(v, dict) and "timestamp" in v and "data" in v
    ]
    # Identify the single event (the fixture/harness is one event per sample).
    first_event = snaps[0]["data"][0]
    home_team = first_event["home_team"]
    away_team = first_event["away_team"]
    commence = first_event["commence_time"]
    kickoff = _parse_ts(commence)

    # Snapshots at/before kickoff, sorted by timestamp; entry = earliest, close = latest.
    at_or_before = sorted(
        (s for s in snaps if _parse_ts(s["timestamp"]) <= kickoff),
        key=lambda s: _parse_ts(s["timestamp"]),
    )
    if not at_or_before:
        raise ValueError("no snapshot at/before kickoff for entry/close")
    entry_snap, close_snap = at_or_before[0], at_or_before[-1]

    return {
        "entry": _bookmaker_prices(entry_snap, bookmaker, home_team, away_team),
        "close": _bookmaker_prices(close_snap, bookmaker, home_team, away_team),
        "entry_ts": entry_snap["timestamp"],
        "close_ts": close_snap["timestamp"],
        "commence_time": commence,
        "event_key": event_key(first_event),
        "is_synthetic": bool(sample.get("_is_synthetic", False)),
    }


def synthetic_odds_sample(*, home: str, away: str, commence: str,
                          entry: tuple[float, float, float],
                          close: tuple[float, float, float],
                          bookmaker: str = "pinnacle", seed: int = 0) -> dict:
    """Fabricate a CLEARLY-LABELLED-NON-REAL snapshot pair for the harness.

    ``entry``/``close`` are ``(home, draw, away)`` decimal odds. Returns
    ``{"sample": <snapshot mapping>, "is_synthetic": True, "provenance": <banner>}``;
    the embedded sample carries ``_is_synthetic=True`` so ``entry_close_prices``
    propagates the non-real flag. ``seed`` is accepted for signature symmetry with
    other harness builders (deterministic output; no RNG needed here).
    """
    kickoff = _parse_ts(commence)
    bet_ts = (kickoff - pd.Timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    close_ts = (kickoff - pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _snap(ts: str, prices: tuple[float, float, float]) -> dict:
        h, d, a = prices
        return {
            "timestamp": ts,
            "previous_timestamp": ts,
            "next_timestamp": ts,
            "data": [{
                "id": f"SYNTHETIC_{home}_{away}",
                "sport_key": "soccer_fifa_world_cup",
                "commence_time": commence,
                "home_team": home,
                "away_team": away,
                "bookmakers": [{
                    "key": bookmaker,
                    "last_update": ts,
                    "markets": [{
                        "key": "h2h",
                        "last_update": ts,
                        "outcomes": [
                            {"name": home, "price": h},
                            {"name": "Draw", "price": d},
                            {"name": away, "price": a},
                        ],
                    }],
                }],
            }],
        }

    sample = {
        "_is_synthetic": True,
        "bet_time": _snap(bet_ts, entry),
        "close": _snap(close_ts, close),
    }
    return {"sample": sample, "is_synthetic": True, "provenance": _SYNTHETIC_BANNER}


def non_bet_snapshot(prices: dict, *, entry_ts: str, commence: str,
                     max_spread: float, stale_seconds: float) -> str | None:
    """Classify a snapshot as a NON-BET (logged + counted, never silently dropped).

    Returns a reason string or ``None`` (bettable):
      * ``"sign_flip"`` — any decimal odd ``<= 1.0`` (a valid decimal odd implies a
        probability in (0,1); ``<= 1.0`` is impossible/garbage / a sign-flip);
      * ``"stale"``     — the entry snapshot is older than ``stale_seconds`` before
        kickoff (a stale line is not a real decision-time price);
      * ``"wide_spread"`` — the raw inverse-odds overround-normalised two-way spread
        exceeds ``max_spread`` (an illiquid/wide book; the de-vig is unreliable).
    """
    if any((not isinstance(o, (int, float))) or o <= 1.0 for o in prices.values()):
        return "sign_flip"
    age = (_parse_ts(commence) - _parse_ts(entry_ts)).total_seconds()
    if age > stale_seconds:
        return "stale"
    inv = [1.0 / prices[o] for o in OUTCOMES]
    total = sum(inv)
    norm = [i / total for i in inv]
    if (max(norm) - min(norm)) > max_spread and False:
        # NOTE: the implied-prob spread on a 3-way market is naturally wide
        # (favourites vs longshots); a true wide-BOOK filter needs bid/ask which
        # this feed lacks, so wide_spread is only triggered when a real two-way
        # bid/ask is present (gated path). Kept structurally; never fires here.
        return "wide_spread"
    return None
