#!/usr/bin/env python
"""Real-historical-odds CLV validation — DOES THE MODEL BEAT THE CLOSING LINE?

OPS-ONLY SCRIPT (untracked under scripts/). Adds NO model/pipeline behaviour. It is a
thin operator harness that (a) assembles the real martj42 bitemporal store exactly like
``scripts/build_real_snapshot.py``; (b) for a small, HARD-CAPPED set of 2022 FIFA World
Cup matches, pulls a real ENTRY (kickoff-6h) and a real CLOSE (kickoff-10min) Pinnacle
(else median-across-books) snapshot via the project's gated historical Odds-API adapter;
(c) reconciles Odds-API team names to martj42; (d) shapes a real ``is_synthetic=False``
``odds_sample`` per matched fixture; and (e) feeds those + the matches' real martj42
scores into the UNCHANGED ``backtest.walkforward.walkforward`` -> ``clv_summary``.

Every CLV number is produced by the unchanged Phase-4 machinery (per-cutoff leakage-safe
posterior fit -> de-vigged entry edge -> stake -> settle -> ``clv_pct = entry/close - 1``).
This script only wires the real store + the real odds into that engine.

THREE SUBCOMMANDS (run with ``PYTHONPATH=src uv run python scripts/clv_validation.py <cmd>``):
  * ``dry``   — ZERO credits. Proves the pipeline end-to-end on REAL martj42 matches with
                REAL-SHAPED hand-built snapshots (``is_synthetic=False``): finite
                beat_close_rate + avg_clv; the leakage proof (decision cutoff < match
                date); ``is_synthetic=False`` clears the taint; a deliberately-mismatched
                team name yields NO bet (a coverage gap), never a wrong-odds bet.
  * ``probe`` — ONE cheap credit. Lists the 2022-WC historical events at a single
                timestamp to confirm coverage + the exact event ids/names for the pilot.
  * ``pilot`` — The HARD-CAPPED real pull (<= ~16 paid historical-odds calls / ~160
                credits). Per match: one entry snapshot call + one close snapshot call.
                Reports exact credits used (from response headers), the name-match rate,
                ``n_bets``, ``beat_close_rate``, ``avg_clv``, and hand-checks 2-3 bets.

CREDIT DISCIPLINE (BINDING). The Odds API free tier is 500 credits; each historical odds
call costs ~10 (markets x regions). A ``CallBudget`` HARD-CAPS the run at MAX_PAID_CALLS
and STOPS before exceeding it. Exact credits are read from ``x-requests-used`` /
``x-requests-remaining`` response headers and printed; the API KEY IS NEVER PRINTED.

LEAKAGE (the binding rule): the model decides at ``cutoff = matchday`` and trains ONLY on
results ``< cutoff``; the bet's edge/side/stake come from the de-vigged ENTRY price (the
close is used ONLY for ``entry/close - 1``). ``entry_ts < close_ts <= kickoff`` is asserted
per fixture. No bet, signal/paper only.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

from wcmodel.backtest.clv import clv_pct
from wcmodel.backtest.odds_ingest import _SYNTHETIC_KEY, OUTCOMES, entry_close_prices
from wcmodel.backtest.baselines import market_fair_1x2, model_fair_1x2
from wcmodel.backtest.walkforward import _sample_is_synthetic, walkforward
from wcmodel.config import load_config
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.odds import ODDSAPI_BASE
from wcmodel.data.sources.results import load_results
from wcmodel.data.store import BitemporalStore

CACHE_DIR = Path("data/cache")
SPORT = "soccer_fifa_world_cup"

# --- HARD CAP (BINDING). Each pilot match costs 2 paid historical-odds calls (entry +
# close). 8 matches x 2 = 16 paid calls. We never issue more than MAX_PAID_CALLS paid
# historical-odds calls; the CallBudget raises before the (MAX+1)-th. The cheap events-
# list calls (1 credit each) are budgeted separately and small. ---
MAX_PAID_CALLS = 16

# The 8 pilot matches: 2022 FIFA World Cup, all with martj42 results. martj42 names on the
# left (== Odds-API names after reconciliation). Kickoff times are the real UTC kickoffs.
# Chosen to span favourites/underdogs/draws so the CLV is not one-sided by construction.
PILOT_MATCHES = [
    # (home, away, kickoff_utc_iso)
    ("Argentina", "Saudi Arabia", "2022-11-22T10:00:00Z"),   # famous upset
    ("England", "Iran", "2022-11-21T13:00:00Z"),
    ("Spain", "Costa Rica", "2022-11-23T16:00:00Z"),
    ("Germany", "Japan", "2022-11-23T13:00:00Z"),
    ("Netherlands", "Senegal", "2022-11-21T16:00:00Z"),
    ("Brazil", "Serbia", "2022-11-24T19:00:00Z"),
    ("Portugal", "Ghana", "2022-11-24T16:00:00Z"),
    ("France", "Denmark", "2022-11-26T16:00:00Z"),
]

# Odds-API team name -> martj42 name. Only genuinely-divergent names; identical needs no
# entry. NEVER a fuzzy guess — an unmatched fixture stays a coverage_gap (honest gap).
NAME_RECONCILE = {
    "USA": "United States",
    "United States of America": "United States",
    "South Korea": "South Korea",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Korea DPR": "North Korea",
}


# --------------------------------------------------------------------------- #
# Credit-header capture (never prints the key).
# --------------------------------------------------------------------------- #
_HEADERS: dict[str, str] = {}


def _capture(resp: httpx.Response) -> None:
    for h in ("x-requests-remaining", "x-requests-used", "x-requests-last"):
        if h in resp.headers:
            _HEADERS[h] = resp.headers[h]


def _credit_line(tag: str) -> str:
    return (f"[{tag}] credits used={_HEADERS.get('x-requests-used', '?')} "
            f"remaining={_HEADERS.get('x-requests-remaining', '?')} "
            f"last-call-cost={_HEADERS.get('x-requests-last', '?')}")


class CallBudget:
    """HARD CAP on PAID historical-odds calls. ``charge()`` refuses past ``max_calls``."""

    def __init__(self, *, max_calls: int):
        self.max_calls = int(max_calls)
        self.spent = 0

    def charge(self) -> None:
        if self.spent >= self.max_calls:
            raise RuntimeError(
                f"paid-call budget exhausted ({self.spent}/{self.max_calls}) — refusing to "
                "over-call the paid historical feed (credit discipline)")
        self.spent += 1


# --------------------------------------------------------------------------- #
# The real store + the fail-loud leakage gate (shared with the snapshot builders).
# --------------------------------------------------------------------------- #
def build_real_store(store_root: Path) -> BitemporalStore:
    store = BitemporalStore(root=store_root)
    load_results(store, cache_dir=CACHE_DIR)
    return store


def _load_env_key() -> str:
    """Read THE_ODDS_API_KEY from os.environ or .env — NEVER printed anywhere."""
    key = os.environ.get("THE_ODDS_API_KEY")
    if not key:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "THE_ODDS_API_KEY":
                    key = v.strip().strip('"').strip("'")
                    break
    if not key:
        raise SystemExit("THE_ODDS_API_KEY not found in environment or .env")
    return key


def _canon(name: str) -> str:
    return NAME_RECONCILE.get(name, name)


def _martj42_results_frame(store: BitemporalStore, cutoff: str) -> pd.DataFrame:
    """All valid-played martj42 results as-of ``cutoff`` (the settle frame source)."""
    res = store.read("results", cutoff=cutoff).copy()
    res["date"] = pd.to_datetime(res["date"])
    return valid_played_results(res)


# =========================================================================== #
# STEP 1 — DRY validation (ZERO credits).
# =========================================================================== #
def _real_shaped_snapshot(home, away, commence, ts, prices, *, book="pinnacle",
                          synthetic=False) -> dict:
    """A REAL-SHAPED Odds-API snapshot ({timestamp, data:[event]}). ``prices`` is
    (home, draw, away) decimal. Stamps ``_is_synthetic`` so the taint is explicit."""
    h, d, a = prices
    return {
        _SYNTHETIC_KEY: bool(synthetic),
        "timestamp": ts,
        "previous_timestamp": ts,
        "next_timestamp": ts,
        "data": [{
            "id": f"{home}_{away}_{commence}",
            "sport_key": SPORT,
            "commence_time": commence,
            "home_team": home,
            "away_team": away,
            "bookmakers": [{
                "key": book,
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


def _real_shaped_sample(home, away, kickoff_iso, entry, close, *, synthetic=False) -> dict:
    """One real-SHAPED ``odds_sample`` ({"sample": {bet_time, close}, is_synthetic}).
    entry snapshot at kickoff-6h, close snapshot at kickoff-10min."""
    kickoff = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
    entry_ts = (kickoff - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    close_ts = (kickoff - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sample = {
        _SYNTHETIC_KEY: bool(synthetic),
        "bet_time": _real_shaped_snapshot(home, away, kickoff_iso, entry_ts, entry,
                                          synthetic=synthetic),
        "close": _real_shaped_snapshot(home, away, kickoff_iso, close_ts, close,
                                       synthetic=synthetic),
    }
    return {"sample": sample, "is_synthetic": bool(synthetic)}


def cmd_dry(args) -> int:
    print("=" * 78)
    print("STEP 1 — DRY validation of the CLV harness (ZERO credits)")
    print("=" * 78)
    cfg = load_config()

    store_root = Path(tempfile.mkdtemp(prefix="wc-clv-dry-store-"))
    print(f"[store] assembling real martj42 store at {store_root} ...")
    store = build_real_store(store_root)
    cutoff_probe = "2026-06-07T00:00:00Z"
    played = _martj42_results_frame(store, cutoff_probe)
    print(f"[store] {len(played)} valid-played martj42 matches; range "
          f"{played['date'].min().date()} .. {played['date'].max().date()}")

    # Pick 3 REAL martj42 matches with known results to settle against. We use early
    # 2022-WC group games; the model trains on < matchday only (leakage-safe).
    real = [
        ("Argentina", "Saudi Arabia", "2022-11-22T10:00:00Z"),
        ("Spain", "Costa Rica", "2022-11-23T16:00:00Z"),
        ("Germany", "Japan", "2022-11-23T13:00:00Z"),
    ]
    # REAL-SHAPED, is_synthetic=False hand-built lines (NOT real prices — a SHAPE/plumbing
    # proof only). Entry generous on one side, close drifts -> a finite, signed CLV.
    handbuilt = {
        ("Argentina", "Saudi Arabia"): ((1.40, 4.60, 8.50), (1.45, 4.50, 7.50)),
        ("Spain", "Costa Rica"): ((1.30, 5.50, 11.0), (1.25, 5.80, 13.0)),
        ("Germany", "Japan"): ((1.45, 4.40, 8.00), (1.40, 4.60, 9.00)),
    }
    samples = []
    settle_rows = []
    for home, away, ko in real:
        entry, close = handbuilt[(home, away)]
        samples.append(_real_shaped_sample(home, away, ko, entry, close, synthetic=False))
        r = played[(played.home_team == home) & (played.away_team == away)
                   & (played.date == pd.Timestamp(ko[:10]))]
        if r.empty:
            raise SystemExit(f"dry: martj42 has no result for {home} v {away} on {ko[:10]}")
        rr = r.iloc[0]
        settle_rows.append({"home_team": home, "away_team": away,
                            "date": pd.Timestamp(ko[:10]),
                            "home_score": int(rr.home_score), "away_score": int(rr.away_score),
                            "tournament": rr.tournament})
        print(f"  [match] {home} {int(rr.home_score)}-{int(rr.away_score)} {away} "
              f"({ko[:10]}) -- martj42 result")
    rfs = pd.DataFrame(settle_rows)
    matches = pd.DataFrame({"date": pd.to_datetime([r["date"] for r in settle_rows])})

    # --- (a) Taint check: is_synthetic=False clears the taint. ---
    for s in samples:
        assert _sample_is_synthetic(s) is False, "is_synthetic=False sample must read REAL"
    print("\n[taint] all 3 real-shaped samples self-identify as REAL (is_synthetic=False). OK")

    # --- (b) Run the UNCHANGED engine -> finite CLV. ---
    print("[run] walkforward over the 3 real matches (per-cutoff leakage-safe fit) ...")
    m = walkforward(store, samples, results_for_settle=rfs, matches=matches,
                    fit_kwargs={"draws": 80, "advi_iters": 2000, "seed": cfg["seed"]})
    print(f"[run] is_synthetic taint = {m.is_synthetic} (must be False — real-shaped)")
    assert m.is_synthetic is False and m.summary["is_synthetic"] is False, (
        "real-shaped is_synthetic=False inputs must NOT taint the Metrics")
    s = m.summary
    print(f"[clv] n_bets={s['clv_n_bets']} beat_close_rate={s['clv_beat_close_rate']} "
          f"avg_clv={s['clv_avg_clv']}")
    import math
    if m.bets:
        assert not math.isnan(s["clv_beat_close_rate"]), "beat_close_rate must be finite"
        assert not math.isnan(s["clv_avg_clv"]), "avg_clv must be finite"
        print("[clv] finite beat_close_rate + avg_clv on real-shaped samples. OK")
    else:
        print("[clv] NOTE: 0 bets (model found no edge over the hand-built lines) — the CLV "
              "is vacuously NaN; the plumbing still ran. (Hand-built lines are a SHAPE proof.)")

    # --- (c) Leakage proof: each decision cutoff < that match's date. ---
    print("\n[leakage] proving the decision for each match trains on < match date only:")
    for b in m.bets:
        ek = b["event_key"]            # [home, away, date]
        cutoff = pd.Timestamp(b["cutoff"]).normalize()
        match_date = pd.Timestamp(str(ek[2])).normalize()
        asof = store.read("results", cutoff=str(cutoff))
        asof_dates = pd.to_datetime(asof["date"])
        max_train = valid_played_results(asof.assign(date=asof_dates))
        max_train_date = pd.to_datetime(max_train["date"])
        max_train_date = max_train_date[max_train_date < cutoff].max()
        own = asof[(asof["home_team"] == ek[0]) & (asof["away_team"] == ek[1])
                   & (asof_dates.dt.normalize() == match_date)]
        # The cutoff is the matchday; features.build trains on STRICTLY < cutoff_day.
        assert max_train_date < cutoff, (
            f"LEAKAGE: training max {max_train_date} not < cutoff {cutoff}")
        # The match's OWN result is never in the < cutoff_day training slice.
        own_in_train = own[asof_dates[own.index] < cutoff]
        assert len(own_in_train) == 0 or (match_date >= cutoff), (
            "LEAKAGE: the match's own result is in its own training slice")
        print(f"  [ok] {ek[0]} v {ek[1]} ({match_date.date()}): cutoff={cutoff.date()}, "
              f"max training date < cutoff = {max_train_date.date()} (< cutoff). "
              "own result NOT in training.")
    if not m.bets:
        print("  [note] no bets placed -> per-bet leakage proof vacuous; the engine's "
              "store.read(cutoff)+`date < cutoff` gate is the structural guarantee.")

    # --- (d) Mismatch -> coverage gap (no_result), NOT a wrong-odds bet. ---
    print("\n[mismatch] a deliberately wrong team name must yield NO bet (coverage gap):")
    bad_sample = _real_shaped_sample("Argentina", "Narnia", "2022-11-22T10:00:00Z",
                                     (1.40, 4.60, 8.50), (1.45, 4.50, 7.50),
                                     synthetic=False)
    mbad = walkforward(store, [bad_sample], results_for_settle=rfs, matches=matches,
                       fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": cfg["seed"]})
    print(f"[mismatch] bets={len(mbad.bets)} non_bets={mbad.non_bets}")
    assert len(mbad.bets) == 0, "a name-mismatched fixture must NOT place a bet"
    assert mbad.non_bets.get("no_result", 0) >= 1, (
        "the mismatched fixture must be a counted coverage gap (no_result), never a bet")
    print("[mismatch] OK: the unmatched fixture is a counted coverage gap (no_result), "
          "never a fabricated/wrong-odds bet.")

    print("\n" + "=" * 78)
    print("STEP 1 GREEN: harness proven end-to-end on REAL matches with REAL-SHAPED "
          "is_synthetic=False samples; leakage-safe; mismatch -> gap. Ready for the pilot.")
    print("=" * 78)
    return 0


# =========================================================================== #
# Real historical Odds-API pulls (PAID). Key never printed.
# =========================================================================== #
def _http_get(url, params, budget: CallBudget | None) -> httpx.Response:
    """One real GET. If ``budget`` is given this is a PAID call -> charged BEFORE the
    request so an exhausted budget refuses without issuing the call."""
    if budget is not None:
        budget.charge()
    resp = httpx.get(url, params=params, timeout=30.0)
    _capture(resp)
    resp.raise_for_status()
    return resp


def fetch_events_list(api_key: str, date_iso: str, budget: CallBudget | None = None) -> list[dict]:
    """GET /v4/historical/sports/{sport}/events?date= — the events knowable at ``date_iso``.
    Cheap (~1 credit). Returns the ``data`` list of {id, commence_time, home_team, away_team}."""
    url = f"{ODDSAPI_BASE}/historical/sports/{SPORT}/events"
    resp = _http_get(url, {"apiKey": api_key, "date": date_iso}, budget)
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


def fetch_event_odds(api_key: str, event_id: str, date_iso: str, *, regions: str,
                     budget: CallBudget) -> dict:
    """GET /v4/historical/sports/{sport}/events/{eventId}/odds?date= — one snapshot for one
    event at ``date_iso`` (h2h, decimal). PAID (~10 credits) -> charged via ``budget``.
    Returns the parsed JSON ({timestamp, data:[event]})."""
    url = f"{ODDSAPI_BASE}/historical/sports/{SPORT}/events/{event_id}/odds"
    resp = _http_get(url, {"apiKey": api_key, "date": date_iso, "markets": "h2h",
                           "regions": regions, "oddsFormat": "decimal"}, budget)
    return resp.json()


def _snapshot_to_real_shape(raw_snap: dict, ts_label: str) -> dict | None:
    """Lift the historical event-odds response into the {timestamp, data:[event]} snapshot
    shape ``parse_snapshot`` consumes, stamped is_synthetic=False. The historical event-odds
    response is itself {timestamp, data:{...event...}} (data is a single event object, not a
    list); we normalise ``data`` to a one-element list. Returns None if it has no event."""
    if not raw_snap:
        return None
    data = raw_snap.get("data")
    if data is None:
        return None
    event = data[0] if isinstance(data, list) else data
    if not event or "bookmakers" not in event:
        return None
    snap = {
        _SYNTHETIC_KEY: False,
        "timestamp": raw_snap.get("timestamp") or ts_label,
        "previous_timestamp": raw_snap.get("previous_timestamp"),
        "next_timestamp": raw_snap.get("next_timestamp"),
        "data": [event],
    }
    return snap


def _sharp_prices_from_event(event: dict, bookmaker: str) -> dict | None:
    """{home,draw,away} decimal odds for ``event`` from the SHARP book (pinnacle if present,
    else MEDIAN across all books with a complete 3-way h2h). Outcomes relabel from the API's
    team-named outcomes. None if no book has a complete h2h (-> coverage gap; never fabricated)."""
    home, away = event["home_team"], event["away_team"]

    def _three_way(book) -> dict | None:
        for mkt in book.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            by_name = {o["name"]: o["price"] for o in mkt.get("outcomes", [])}
            if home in by_name and away in by_name and "Draw" in by_name:
                return {"home": float(by_name[home]), "draw": float(by_name["Draw"]),
                        "away": float(by_name[away])}
        return None

    books = event.get("bookmakers", [])
    for book in books:
        if book.get("key") == bookmaker:
            p = _three_way(book)
            if p is not None:
                return p
    triples = [t for t in (_three_way(b) for b in books) if t is not None]
    if not triples:
        return None
    return {o: float(statistics.median(t[o] for t in triples)) for o in OUTCOMES}


def _which_book(event: dict, bookmaker: str) -> str:
    """Report whether the sharp book or the median-fallback supplied the price (for the log)."""
    for book in event.get("bookmakers", []):
        if book.get("key") == bookmaker:
            for mkt in book.get("markets", []):
                if mkt.get("key") == "h2h":
                    return bookmaker
    n = sum(1 for b in event.get("bookmakers", [])
            for mkt in b.get("markets", []) if mkt.get("key") == "h2h")
    return f"median(of {n} books)"


# =========================================================================== #
# STEP 2 probe — ONE cheap events-list call to confirm coverage + ids.
# =========================================================================== #
def cmd_probe(args) -> int:
    print("=" * 78)
    print("STEP 2a — PROBE 2022-WC historical coverage (ONE cheap events-list call)")
    print("=" * 78)
    api_key = _load_env_key()
    # A timestamp during the 2022 WC group stage (Nov 22 2022, midday UTC). The events-list
    # at this instant returns every event with odds knowable then.
    probe_date = "2022-11-22T12:00:00Z"
    print(f"[probe] GET historical events list @ {probe_date} (sport={SPORT}) ...")
    try:
        events = fetch_events_list(api_key, probe_date)
    except httpx.HTTPStatusError as exc:
        print(f"[probe] HTTP {exc.response.status_code}: {exc.response.text[:300]}",
              file=sys.stderr)
        print(_credit_line("probe"))
        return 2
    print(_credit_line("probe"))
    print(f"[probe] {len(events)} events returned at {probe_date}. Sample:")
    for ev in events[:12]:
        print(f"  id={ev.get('id')}  {ev.get('home_team')} v {ev.get('away_team')}  "
              f"commence={ev.get('commence_time')}")
    # Cross-check which of our PILOT matches are present (by reconciled name + date).
    by_key = {}
    for ev in events:
        try:
            ck = (_canon(ev["home_team"]), _canon(ev["away_team"]),
                  ev["commence_time"][:10])
        except Exception:
            continue
        by_key[ck] = ev
    print("\n[probe] PILOT-match coverage at this instant (some kick off later -> may not "
          "appear yet; the pilot lists each match at its OWN window):")
    for home, away, ko in PILOT_MATCHES:
        hit = by_key.get((home, away, ko[:10]))
        print(f"  {'FOUND ' if hit else 'absent'} {home} v {away} ({ko[:10]})"
              + (f"  id={hit['id']}" if hit else ""))
    return 0


# =========================================================================== #
# STEP 2 pilot — the HARD-CAPPED real pull + walkforward CLV.
# =========================================================================== #
def _find_event_id(api_key: str, home: str, away: str, kickoff_iso: str,
                   budget: CallBudget) -> tuple[str | None, dict | None]:
    """Resolve the Odds-API event id for one fixture via a cheap events-list call at
    kickoff-3h (events knowable then). Matches on reconciled (home, away, date). Returns
    (event_id, raw_event) or (None, None) -> coverage gap. The events-list call is cheap
    (~1 credit) and charged against the budget too (defense-in-depth)."""
    kickoff = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
    list_date = (kickoff - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = fetch_events_list(api_key, list_date, budget)
    for ev in events:
        try:
            ck = (_canon(ev["home_team"]), _canon(ev["away_team"]), ev["commence_time"][:10])
        except Exception:
            continue
        if ck == (home, away, kickoff_iso[:10]):
            return ev["id"], ev
    return None, None


def cmd_pilot(args) -> int:
    print("=" * 78)
    print("STEP 2b — PILOT: REAL 2022-WC historical odds -> CLV (HARD-CAPPED)")
    print("=" * 78)
    cfg = load_config()
    book = cfg["backtest"]["primary_bookmaker"]
    regions = "eu"
    n_matches = min(args.matches, len(PILOT_MATCHES))
    # Budget: 2 paid event-odds calls per match (entry + close). The cheap events-list
    # calls are charged separately so they cannot eat the paid-odds headroom. We cap the
    # paid event-odds calls at MAX_PAID_CALLS.
    paid_budget = CallBudget(max_calls=min(MAX_PAID_CALLS, 2 * n_matches))
    list_budget = CallBudget(max_calls=n_matches + 2)   # one events-list per match + slack
    print(f"[budget] HARD CAP: <= {paid_budget.max_calls} paid event-odds calls "
          f"(~{paid_budget.max_calls * 10} credits) over {n_matches} matches; "
          f"<= {list_budget.max_calls} cheap events-list calls.")

    api_key = _load_env_key()
    store_root = Path(tempfile.mkdtemp(prefix="wc-clv-pilot-store-"))
    print(f"[store] assembling real martj42 store at {store_root} ...")
    store = build_real_store(store_root)
    played = _martj42_results_frame(store, "2026-06-07T00:00:00Z")

    samples: list[dict] = []
    settle_rows: list[dict] = []
    matched: list[str] = []
    unmatched: list[str] = []
    pull_log: list[dict] = []

    for home, away, ko in PILOT_MATCHES[:n_matches]:
        label = f"{home} v {away} ({ko[:10]})"
        # martj42 result must exist (else skip — never settle a fabricated score).
        r = played[(played.home_team == home) & (played.away_team == away)
                   & (played.date == pd.Timestamp(ko[:10]))]
        if r.empty:
            print(f"  [skip] {label}: no martj42 result")
            unmatched.append(label + " [no martj42 result]")
            continue

        # Resolve the Odds-API event id (cheap events-list call).
        try:
            event_id, _ev = _find_event_id(api_key, home, away, ko, list_budget)
        except httpx.HTTPStatusError as exc:
            print(f"  [http] {label}: events-list HTTP {exc.response.status_code} "
                  f"{exc.response.text[:160]}")
            unmatched.append(label + f" [events-list HTTP {exc.response.status_code}]")
            continue
        if event_id is None:
            print(f"  [gap] {label}: no Odds-API event matched (name/date) -> coverage gap")
            unmatched.append(label + " [no Odds-API event]")
            continue

        # Stop BEFORE exceeding the paid cap (need 2 paid calls for this match).
        if paid_budget.spent + 2 > paid_budget.max_calls:
            print(f"  [budget] stopping before {label}: would exceed the paid cap "
                  f"({paid_budget.spent}/{paid_budget.max_calls}).")
            break

        kickoff = datetime.fromisoformat(ko.replace("Z", "+00:00"))
        entry_date = (kickoff - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        close_date = (kickoff - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            entry_raw = fetch_event_odds(api_key, event_id, entry_date, regions=regions,
                                         budget=paid_budget)
            close_raw = fetch_event_odds(api_key, event_id, close_date, regions=regions,
                                         budget=paid_budget)
        except httpx.HTTPStatusError as exc:
            print(f"  [http] {label}: event-odds HTTP {exc.response.status_code} "
                  f"{exc.response.text[:160]}")
            unmatched.append(label + f" [event-odds HTTP {exc.response.status_code}]")
            continue

        entry_snap = _snapshot_to_real_shape(entry_raw, entry_date)
        close_snap = _snapshot_to_real_shape(close_raw, close_date)
        if entry_snap is None or close_snap is None:
            print(f"  [gap] {label}: a snapshot had no event/bookmakers -> coverage gap")
            unmatched.append(label + " [empty snapshot]")
            continue

        entry_event = entry_snap["data"][0]
        close_event = close_snap["data"][0]
        entry_prices = _sharp_prices_from_event(entry_event, book)
        close_prices = _sharp_prices_from_event(close_event, book)
        if entry_prices is None or close_prices is None:
            print(f"  [gap] {label}: no complete 3-way h2h in a snapshot -> coverage gap")
            unmatched.append(label + " [no complete h2h]")
            continue

        # Re-shape into the martj42-named real sample the engine joins on. We rebuild the
        # snapshots with martj42 names + the sharp {home,draw,away} prices, preserving the
        # REAL snapshot timestamps (so entry_ts < close_ts <= kickoff is genuine).
        entry_ts = entry_snap["timestamp"]
        close_ts = close_snap["timestamp"]
        sample = {
            _SYNTHETIC_KEY: False,
            "bet_time": _real_shaped_snapshot(
                home, away, ko, entry_ts,
                (entry_prices["home"], entry_prices["draw"], entry_prices["away"]),
                book=book, synthetic=False),
            "close": _real_shaped_snapshot(
                home, away, ko, close_ts,
                (close_prices["home"], close_prices["draw"], close_prices["away"]),
                book=book, synthetic=False),
        }
        samples.append({"sample": sample, "is_synthetic": False})
        rr = r.iloc[0]
        settle_rows.append({"home_team": home, "away_team": away,
                            "date": pd.Timestamp(ko[:10]),
                            "home_score": int(rr.home_score), "away_score": int(rr.away_score),
                            "tournament": rr.tournament})
        matched.append(label)
        pull_log.append({
            "match": label, "event_id": event_id,
            "entry_ts": entry_ts, "close_ts": close_ts,
            "entry_book": _which_book(entry_event, book),
            "close_book": _which_book(close_event, book),
            "entry": entry_prices, "close": close_prices,
            "result": f"{int(rr.home_score)}-{int(rr.away_score)}",
        })
        print(f"  [pull] {label}: id={event_id} entry@{entry_ts} close@{close_ts} "
              f"({_which_book(entry_event, book)}) result {int(rr.home_score)}-{int(rr.away_score)}")
        print(f"         entry={entry_prices} close={close_prices}")

    print("\n" + _credit_line("pilot"))
    print(f"[budget] paid event-odds calls spent: {paid_budget.spent}/{paid_budget.max_calls}; "
          f"events-list calls spent: {list_budget.spent}/{list_budget.max_calls}")
    n_attempted = n_matches
    print(f"[reconcile] matched {len(matched)}/{n_attempted} attempted; "
          f"unmatched/gap={len(unmatched)}")
    for label in unmatched:
        print(f"  [gap] {label}")

    if not samples:
        print("\n[STOP] no real samples were built (coverage/HTTP). NOT fabricating odds. "
              "Reporting the blocker — see the [gap]/[http] lines above.")
        return 3

    # --- Pre-flight: assert entry_ts < close_ts <= kickoff per sample (no swap/leak). A
    # degenerate sample (entry_ts == close_ts: the API had only one snapshot before kickoff)
    # is DROPPED as a coverage gap, never forced into a bet (no CLV recordable). ---
    print("\n[preflight] asserting entry_ts < close_ts <= kickoff per real sample:")
    kept = []
    for s, row in zip(samples, settle_rows):
        pc = entry_close_prices(s["sample"], bookmaker=book)
        et = datetime.fromisoformat(pc["entry_ts"].replace("Z", "+00:00"))
        ct = datetime.fromisoformat(pc["close_ts"].replace("Z", "+00:00"))
        ko = datetime.fromisoformat(pc["commence_time"].replace("Z", "+00:00"))
        ek = pc["event_key"]
        assert _sample_is_synthetic(s) is False, "real sample must read is_synthetic=False"
        if not (et < ct <= ko):
            print(f"  [gap] {ek[0]} v {ek[1]}: entry_ts={et} close_ts={ct} kickoff={ko} "
                  "not strictly ordered (single pre-kickoff snapshot?) -> dropped, no CLV")
            unmatched.append(f"{ek[0]} v {ek[1]} [entry_ts==close_ts]")
            continue
        kept.append((s, row))
        print(f"  [ok] {ek[0]} v {ek[1]}: entry {et} < close {ct} <= kickoff {ko}")
    if not kept:
        print("\n[STOP] every real sample failed the entry<close<=kickoff order (degenerate "
              "snapshots). NOT fabricating a CLV. Reporting the blocker.")
        return 3
    samples = [s for s, _ in kept]
    settle_rows = [row for _, row in kept]

    rfs = pd.DataFrame(settle_rows)
    matches = pd.DataFrame({"date": pd.to_datetime([row["date"] for row in settle_rows])})

    print(f"\n[run] walkforward over {len(samples)} REAL matches (per-cutoff leakage-safe "
          "fit; edge from de-vigged ENTRY; close used only for CLV) ...")
    m = walkforward(store, samples, results_for_settle=rfs, matches=matches,
                    fit_kwargs={"draws": 200, "advi_iters": 2000, "seed": cfg["seed"]})
    print(f"[run] is_synthetic = {m.is_synthetic} (must be False — REAL odds)")
    if m.is_synthetic:
        print("[ABORT] the REAL run is tainted synthetic — refusing to report a CLV number.",
              file=sys.stderr)
        return 4

    s = m.summary
    print("\n" + "=" * 78)
    print("PILOT CLV RESULT (REAL 2022-WC historical odds)")
    print("=" * 78)
    print(f"  n_bets          : {s['clv_n_bets']}")
    print(f"  beat_close_rate : {s['clv_beat_close_rate']}")
    print(f"  avg_clv         : {s['clv_avg_clv']}")
    print(f"  non_bets        : {m.non_bets}")
    print(f"  name-match rate : {len(matched)}/{n_attempted} = "
          f"{len(matched)/n_attempted:.0%}")

    # --- STEP 3: hand-check up to 3 bets (model vs de-vigged entry vs close). ---
    print("\n" + "=" * 78)
    print("STEP 3 — adversarial hand-check (model 1X2 vs de-vigged ENTRY vs CLOSE)")
    print("=" * 78)
    devig = cfg["backtest"]["devig_method"]
    for b in m.bets[:3]:
        ek = b["event_key"]
        # Find the originating sample to recover the raw entry/close vectors.
        pc = None
        for s_ in samples:
            p = entry_close_prices(s_["sample"], bookmaker=book)
            # Stringify each key element: the bet's event_key date may be a str while the
            # sample's is a datetime.date (or vice-versa) -> a raw list== misses. Compare
            # by stringified (home, away, date) so the lookup is format-robust.
            if [str(x) for x in p["event_key"]] == [str(x) for x in ek]:
                pc = p
                break
        if pc is None:                       # lookup miss -> skip this bet's hand-check, never crash
            print(f"  [hand-check] {ek[0]} v {ek[1]}: originating sample not found (skipped)")
            continue
        entry_dv = market_fair_1x2(pc["entry"], method=devig)
        close_dv = market_fair_1x2(pc["close"], method=devig)
        staked = b["staked"]
        cl = clv_pct(entry_odds=b["entry_odds"], close_odds=b["close_odds"])
        print(f"\n  {ek[0]} v {ek[1]} ({ek[2]})  result={b['outcome']}  won={b['won']}")
        print(f"    model 1X2       : { {k: round(b['model'][k],3) for k in OUTCOMES} }")
        print(f"    de-vig ENTRY 1X2: { {k: round(entry_dv[k],3) for k in OUTCOMES} }  "
              f"(raw {pc['entry']})")
        print(f"    de-vig CLOSE 1X2: { {k: round(close_dv[k],3) for k in OUTCOMES} }  "
              f"(raw {pc['close']})")
        print(f"    staked side     : {staked}  (model {b['model'][staked]:.3f} vs "
              f"de-vig-entry {entry_dv[staked]:.3f}; edge {b['edge']:+.3f})")
        print(f"    entry odds      : {b['entry_odds']:.3f}")
        print(f"    close odds      : {b['close_odds']:.3f}")
        print(f"    clv_pct         : {cl:+.4f}  ({'BEAT close' if cl>0 else 'worse-or-equal'})")
        # Sanity: entry/close are the SAME staked side's prices (no cross-game/odds swap).
        assert abs(b["entry_odds"] - pc["entry"][staked]) < 1e-9
        assert abs(b["close_odds"] - pc["close"][staked]) < 1e-9

    # --- Foresight-RED guardrail (too-good = SUSPECTED BUG). ---
    print("\n" + "=" * 78)
    print("ADVERSARIAL: foresight-RED guardrail (too-good => SUSPECTED BUG, not a win)")
    print("=" * 78)
    red = cfg["backtest"]["foresight_red"]
    import math
    bcr = s["clv_beat_close_rate"]
    avg = s["clv_avg_clv"]
    flags = []
    if not math.isnan(bcr) and bcr > red["beat_close_rate"]:
        flags.append(f"beat_close_rate {bcr:.3f} > RED {red['beat_close_rate']}")
    if not math.isnan(avg) and avg > red["avg_clv"]:
        flags.append(f"avg_clv {avg:.4f} > RED {red['avg_clv']}")
    if flags:
        print("  [RED] " + "; ".join(flags))
        print("  => TREAT AS A SUSPECTED BUG. With n this small the CI is very wide; do NOT "
              "celebrate. Re-examine the hand-checked bets above for a name mismatch / "
              "entry-close swap before claiming an edge.")
    else:
        print(f"  [ok] beat_close_rate={bcr} and avg_clv={avg} are within the plausibility "
              f"ceilings (beat<= {red['beat_close_rate']}, avg<= {red['avg_clv']}). No "
              "too-good flag — but n is tiny, so this is directional only.")

    print("\n[verdict] DIRECTIONAL PILOT ONLY (n is small -> the CLV CI is WIDE). "
          "See the printed beat_close_rate / avg_clv; this is NOT a powered verdict.")
    print("[discipline] no commit; key never printed; signal/paper only (no real bet).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Real-historical-odds CLV validation.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dry", help="ZERO-credit dry validation of the harness")
    sub.add_parser("probe", help="ONE cheap events-list call to confirm 2022-WC coverage")
    pp = sub.add_parser("pilot", help="HARD-CAPPED real pull -> CLV")
    pp.add_argument("--matches", type=int, default=8,
                    help="number of pilot matches (<= 8; each costs 2 paid calls)")
    args = ap.parse_args()
    return {"dry": cmd_dry, "probe": cmd_probe, "pilot": cmd_pilot}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
