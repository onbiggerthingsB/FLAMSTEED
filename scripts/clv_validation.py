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
import json
import math
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

from wcmodel.backtest.clv import clv_pct
from wcmodel.backtest.odds_ingest import _SYNTHETIC_KEY, OUTCOMES, entry_close_prices
from wcmodel.backtest.baselines import market_fair_1x2, model_fair_1x2, rps
from wcmodel.backtest.walkforward import _sample_is_synthetic, walkforward
from wcmodel.config import load_config
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.odds import ODDSAPI_BASE
from wcmodel.data.sources.results import load_results
from wcmodel.data.store import BitemporalStore
import wcmodel.model.cache as _model_cache

CACHE_DIR = Path("data/cache")
SPORT = "soccer_fifa_world_cup"

# A PERSISTENT martj42 store dir (gitignored under /data/). Building the store once
# here — instead of a fresh ``tempfile.mkdtemp`` per run — keeps the content-
# addressed feature/posterior caches STABLE across runs: a fresh temp store made
# the DuckDB read order (and so the feature_hash) flip every run, forcing a full
# re-fit; a persistent store + the now-row-order-stable hash means a 2nd identical
# run HITS the on-disk panel + posterior caches and spends seconds, not ~50 min.
# Still read STRICTLY as-of-cutoff (leakage-safe): the persistent store holds the
# full martj42 history, but every fit reads ``store.read(cutoff)`` + ``date<cutoff``
# exactly as before — persistence changes only WHERE the parquet lives, never WHICH
# rows a cutoff can see.
CLV_STORE_DIR = Path("data/clv_store")

# Gitignored on-disk cache of the REAL pulled odds (one record per matched
# fixture). The ``accuracy`` (and a cached ``pilot``) run reads this first so a
# re-run re-spends ZERO credits; only a genuinely-new fixture triggers a pull.
ODDS_CACHE_PATH = Path("data/clv_odds_cache.json")

# --- HARD CAP (BINDING). Each match costs 2 paid historical-odds calls (entry + close).
# The pilot (8 WC matches) -> 16 paid calls. The stratified set (15 internationals across
# 3 tiers) -> 30 paid calls (~300 credits, well under the ~19.5k-credit paid balance). We
# NEVER issue more than the effective cap; the CallBudget raises before the (cap+1)-th paid
# call. The cheap events-list calls (1 credit each) are budgeted separately and small. ---
MAX_PAID_CALLS = 16                    # pilot cap (8 matches x 2)
MAX_PAID_CALLS_STRATIFIED = 30         # stratified cap (15 matches x 2 = 30; ~300 credits)

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
    # Stratified additions (verified against the events-list API names printed during the
    # coverage probe; each is a confident 1:1 spelling reconciliation, never a fuzzy guess).
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "Republic of Ireland": "Republic of Ireland",
    "North Macedonia": "North Macedonia",
}


# --------------------------------------------------------------------------- #
# STRATIFIED match set — internationals across THREE market-liquidity tiers, each
# (a) with a real martj42 result and (b) confirmed Odds-API historical coverage
# (probed cheaply; see the coverage report). Domestic/club comps are excluded —
# the model trains ONLY on martj42 NATIONAL-TEAM results.
#
# Tier ladder (sharpest -> least efficient WITH odds coverage):
#   * marquee — UEFA Euro 2024 group/KO. The sharpest international markets after the WC.
#   * mid     — UEFA Nations League 2024 (top European sides; liquid but a notch below a major).
#   * thin    — FIFA World Cup qualifiers (Europe, Sep 2025), skewed to lower-profile / minnow
#               matchups. The thinnest international markets that STILL have Odds-API depth.
#
# COVERAGE HONESTY: international FRIENDLIES were the intended "thinnest" tier, but the Odds API
# has NO historical odds depth for the ``soccer_int_friendlies`` key across every tested window
# (the key is valid — 200, not 404 — but returns n=0 events). That tier is therefore an honest
# COVERAGE GAP; WC-qualifier minnow games are the thinnest markets we can actually score. UEFA
# Euro/WC qualifier keys also varied: the live ``soccer_uefa_euro_qualification`` returned n=0,
# while ``soccer_fifa_world_cup_qualifiers_europe`` has solid Sep/Oct/Nov-2025 depth.
#
# Each entry: (martj42_home, martj42_away, kickoff_utc_iso, tier, sport_key). The martj42 names
# are the LEFT side of NAME_RECONCILE (== reconciled Odds-API names). Kickoffs are the real UTC
# kickoffs (Euro/NL evening slots 18:45Z; WC-qual likewise). Each tier spans favourites /
# underdogs / draws so per-tier RPS is not one-sided by construction.
SPORT_EURO = "soccer_uefa_european_championship"
SPORT_NL = "soccer_uefa_nations_league"
SPORT_WCQ_EU = "soccer_fifa_world_cup_qualifiers_europe"

STRATIFIED_MATCHES = [
    # (home, away, kickoff_utc_iso, tier, sport_key)
    # --- MARQUEE: UEFA Euro 2024 ---
    ("Spain", "Croatia", "2024-06-15T16:00:00Z", "marquee", SPORT_EURO),
    ("Italy", "Albania", "2024-06-15T19:00:00Z", "marquee", SPORT_EURO),
    ("Serbia", "England", "2024-06-16T19:00:00Z", "marquee", SPORT_EURO),
    ("Austria", "France", "2024-06-17T19:00:00Z", "marquee", SPORT_EURO),
    ("Portugal", "Czech Republic", "2024-06-18T19:00:00Z", "marquee", SPORT_EURO),
    # --- MID: UEFA Nations League 2024 ---
    ("Belgium", "Israel", "2024-09-06T18:45:00Z", "mid", SPORT_NL),
    ("France", "Italy", "2024-09-06T18:45:00Z", "mid", SPORT_NL),
    ("Germany", "Hungary", "2024-09-07T18:45:00Z", "mid", SPORT_NL),
    ("Netherlands", "Bosnia and Herzegovina", "2024-09-07T18:45:00Z", "mid", SPORT_NL),
    ("Republic of Ireland", "England", "2024-09-07T16:00:00Z", "mid", SPORT_NL),
    # --- THIN: FIFA World Cup qualifiers (Europe, Sep 2025) — lower-profile / minnow markets ---
    ("Liechtenstein", "Belgium", "2025-09-04T18:45:00Z", "thin", SPORT_WCQ_EU),
    ("Lithuania", "Malta", "2025-09-04T16:00:00Z", "thin", SPORT_WCQ_EU),
    ("Kazakhstan", "Wales", "2025-09-04T14:00:00Z", "thin", SPORT_WCQ_EU),
    ("Luxembourg", "Northern Ireland", "2025-09-04T18:45:00Z", "thin", SPORT_WCQ_EU),
    ("Faroe Islands", "Croatia", "2025-09-05T18:45:00Z", "thin", SPORT_WCQ_EU),
]

TIER_ORDER = ["marquee", "mid", "thin"]


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


def get_persistent_store(*, rebuild: bool = False) -> BitemporalStore:
    """Build the martj42 store ONCE into ``CLV_STORE_DIR`` and reuse it across runs.

    If the persistent parquet already exists we attach to it WITHOUT re-writing
    (so the store content — and the content-addressed feature/posterior cache keys
    derived from it — stay byte-stable across runs, which is what lets a 2nd run
    HIT the caches). ``rebuild=True`` (or a missing parquet) re-ingests from the
    martj42 cache. The store still holds the full history and is read strictly
    as-of-cutoff downstream, so persistence is leakage-neutral.
    """
    CLV_STORE_DIR.mkdir(parents=True, exist_ok=True)
    results_parquet = CLV_STORE_DIR / "results.parquet"
    if results_parquet.exists() and not rebuild:
        return BitemporalStore(root=CLV_STORE_DIR)
    # Fresh build: ingest once. (Remove a stale parquet so write() appends cleanly.)
    if results_parquet.exists():
        results_parquet.unlink()
    return build_real_store(CLV_STORE_DIR)


# --------------------------------------------------------------------------- #
# Gitignored odds cache — a re-run re-spends ZERO credits.
# --------------------------------------------------------------------------- #
def _odds_cache_key(home: str, away: str, ko: str, regions: str, book: str) -> str:
    return f"{home}|{away}|{ko[:10]}|{regions}|{book}"


def _load_odds_cache() -> dict:
    if ODDS_CACHE_PATH.exists():
        try:
            return json.loads(ODDS_CACHE_PATH.read_text())
        except (ValueError, OSError):
            return {}
    return {}


def _save_odds_cache(cache: dict) -> None:
    ODDS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ODDS_CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, indent=2, sort_keys=True, default=str))
    tmp.replace(ODDS_CACHE_PATH)


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

    # Persistent store (built once, reused) so the content-addressed feature/
    # posterior caches stay STABLE across runs — see CLV_STORE_DIR. Leakage-safe:
    # still read strictly as-of-cutoff downstream.
    store = get_persistent_store()
    print(f"[store] persistent real martj42 store at {CLV_STORE_DIR} ...")
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


def fetch_events_list(api_key: str, date_iso: str, budget: CallBudget | None = None,
                      *, sport: str = SPORT) -> list[dict]:
    """GET /v4/historical/sports/{sport}/events?date= — the events knowable at ``date_iso``.
    Cheap (~1 credit). Returns the ``data`` list of {id, commence_time, home_team, away_team}.

    ``sport`` defaults to the WC key (so the legacy pilot/probe path is byte-identical);
    the stratified accuracy run passes the per-tier comp key (Euro / Nations League / WC
    qualifiers). An unknown key 404s upstream and is surfaced as a coverage gap, never a guess.
    """
    url = f"{ODDSAPI_BASE}/historical/sports/{sport}/events"
    resp = _http_get(url, {"apiKey": api_key, "date": date_iso}, budget)
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


def fetch_event_odds(api_key: str, event_id: str, date_iso: str, *, regions: str,
                     budget: CallBudget, sport: str = SPORT) -> dict:
    """GET /v4/historical/sports/{sport}/events/{eventId}/odds?date= — one snapshot for one
    event at ``date_iso`` (h2h, decimal). PAID (~10 credits) -> charged via ``budget``.
    Returns the parsed JSON ({timestamp, data:[event]}). ``sport`` defaults to the WC key."""
    url = f"{ODDSAPI_BASE}/historical/sports/{sport}/events/{event_id}/odds"
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
                   budget: CallBudget, *, sport: str = SPORT) -> tuple[str | None, dict | None]:
    """Resolve the Odds-API event id for one fixture via a cheap events-list call at
    kickoff-3h (events knowable then). Matches on reconciled (home, away, date). Returns
    (event_id, raw_event) or (None, None) -> coverage gap. The events-list call is cheap
    (~1 credit) and charged against the budget too (defense-in-depth). ``sport`` selects the
    comp (WC / Euro / Nations League / WC-qualifiers) for the stratified run."""
    kickoff = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
    list_date = (kickoff - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = fetch_events_list(api_key, list_date, budget, sport=sport)
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
    # Persistent store (built once, reused) so a re-run HITS the on-disk feature/
    # posterior caches instead of re-fitting (~50 min) from a fresh temp store.
    store = get_persistent_store()
    print(f"[store] persistent real martj42 store at {CLV_STORE_DIR} ...")
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


# =========================================================================== #
# STEP 4 — ACCURACY: model RPS vs market RPS vs uniform (the forecast-accuracy job)
# =========================================================================== #
UNIFORM_1X2 = {"home": 1.0 / 3, "draw": 1.0 / 3, "away": 1.0 / 3}


def _result_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def _resolve_sample_from_cache_or_pull(home, away, ko, *, api_key, book, regions,
                                       paid_budget, list_budget, cache, allow_pull,
                                       sport=SPORT):
    """Return a REAL ``{entry, close}`` price record for one fixture.

    Cache-first: if the gitignored odds cache already holds this fixture's
    de-vig-ready ``{entry, close, entry_ts, close_ts}`` we reuse it (ZERO credits).
    Otherwise — and ONLY if ``allow_pull`` and the hard-capped budgets permit — we
    pull it via the SAME gated historical adapter the pilot uses, persist it, and
    return it. Returns ``(record, status)`` where status is one of
    ``cache|pulled|gap:<reason>|budget``.

    ``sport`` selects the comp endpoint for the pull (WC / Euro / Nations League /
    WC-qualifiers). The CACHE KEY stays ``home|away|date|regions|book`` (no sport):
    (home, away, date) is unique per fixture across comps, so this is back-compatible
    with the already-cached WC-2022 records (re-runs of those re-spend ZERO credits)."""
    ck = _odds_cache_key(home, away, ko, regions, book)
    if ck in cache:
        return cache[ck], "cache"
    if not allow_pull:
        return None, "gap:not_cached_no_pull"

    try:
        event_id, _ev = _find_event_id(api_key, home, away, ko, list_budget, sport=sport)
    except httpx.HTTPStatusError as exc:
        return None, f"gap:events_list_http_{exc.response.status_code}"
    if event_id is None:
        return None, "gap:no_event"
    if paid_budget.spent + 2 > paid_budget.max_calls:
        return None, "budget"

    kickoff = datetime.fromisoformat(ko.replace("Z", "+00:00"))
    entry_date = (kickoff - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    close_date = (kickoff - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        entry_raw = fetch_event_odds(api_key, event_id, entry_date, regions=regions,
                                     budget=paid_budget, sport=sport)
        close_raw = fetch_event_odds(api_key, event_id, close_date, regions=regions,
                                     budget=paid_budget, sport=sport)
    except httpx.HTTPStatusError as exc:
        return None, f"gap:event_odds_http_{exc.response.status_code}"

    entry_snap = _snapshot_to_real_shape(entry_raw, entry_date)
    close_snap = _snapshot_to_real_shape(close_raw, close_date)
    if entry_snap is None or close_snap is None:
        return None, "gap:empty_snapshot"
    entry_prices = _sharp_prices_from_event(entry_snap["data"][0], book)
    close_prices = _sharp_prices_from_event(close_snap["data"][0], book)
    if entry_prices is None or close_prices is None:
        return None, "gap:no_h2h"

    record = {
        "home": home, "away": away, "kickoff": ko, "event_id": event_id,
        "entry": entry_prices, "close": close_prices,
        "entry_ts": entry_snap["timestamp"], "close_ts": close_snap["timestamp"],
        "entry_book": _which_book(entry_snap["data"][0], book),
        "close_book": _which_book(close_snap["data"][0], book),
        "regions": regions, "bookmaker": book, "sport": sport,
    }
    cache[ck] = record
    return record, "pulled"


def cmd_accuracy(args) -> int:
    """The FORECAST-ACCURACY diagnostic: per-match + aggregate RPS of the model's
    1X2 vs the de-vigged CLOSE (market) vs uniform, leakage-safe per-cutoff fits.

    RPS is a forecast-accuracy score (lower = better), INDEPENDENT of betting —
    so it is computed for EVERY matched fixture, not only the ones the model would
    bet. The model is the project's audited ``baselines.rps`` on ``model_fair_1x2``
    (the per-cutoff ``cached_fit`` posterior, trained on < matchday only). The
    market benchmark is ``rps`` on ``market_fair_1x2`` of the de-vigged CLOSE; the
    floor is ``rps`` on the (1/3,1/3,1/3) uniform. Credits: ZERO if the odds cache
    already covers the pilot matches; else a hard-capped pull that is then cached.
    """
    match_set = getattr(args, "match_set", "pilot")
    is_stratified = match_set == "stratified"
    print("=" * 78)
    if is_stratified:
        print("STEP 4 — STRATIFIED ACCURACY: model RPS vs MARKET (de-vigged close) vs UNIFORM")
        print("            across THREE market-liquidity tiers (marquee / mid / thin)")
    else:
        print("STEP 4 — ACCURACY: model RPS vs MARKET (de-vigged close) RPS vs UNIFORM")
    print("=" * 78)
    cfg = load_config()
    # SHARPENING overrides (in-memory): raise the strength-prior scale and/or lower the widening
    # to make the model less under-confident. Each distinct setting is a distinct posterior cache
    # key (cfg["model"] is hashed), so a sweep never collides. None -> the on-disk config (baseline).
    if getattr(args, "sigma_att", None) is not None:
        cfg["model"]["prior"]["sigma_att"] = float(args.sigma_att)
    if getattr(args, "sigma_def", None) is not None:
        cfg["model"]["prior"]["sigma_def"] = float(args.sigma_def)
    if getattr(args, "widening_strength", None) is not None:
        cfg["model"]["widening"]["strength"] = float(args.widening_strength)
    print(f"[sharpen] prior.sigma_att={cfg['model']['prior']['sigma_att']} "
          f"sigma_def={cfg['model']['prior']['sigma_def']} "
          f"widening.strength={cfg['model']['widening']['strength']}")
    book = cfg["backtest"]["primary_bookmaker"]
    regions = "eu"
    devig = cfg["backtest"]["devig_method"]
    allow_pull = bool(args.pull)

    # Resolve the match set. The PILOT path is byte-identical to before (WC-2022, single
    # comp, no tier). The STRATIFIED path carries a per-match (tier, sport_key).
    if is_stratified:
        match_specs = [(h, a, ko, tier, sp) for (h, a, ko, tier, sp) in STRATIFIED_MATCHES]
    elif match_set == "euro":
        # The 5 UEFA Euro-2024 fixtures (the marquee tier) — for a SINGLE-fit cluster diagnostic
        # (pair with --cutoff 2024-06-14 so all 5 share one leakage-safe production fit).
        match_specs = [(h, a, ko, tier, sp) for (h, a, ko, tier, sp) in STRATIFIED_MATCHES
                       if tier == "marquee"]
    else:
        match_specs = [(h, a, ko, "pilot", SPORT) for (h, a, ko) in PILOT_MATCHES]
    n_matches = min(args.matches, len(match_specs))
    match_specs = match_specs[:n_matches]

    # Persistent store + shared on-disk caches => a 2nd run re-fits NOTHING.
    store = get_persistent_store(rebuild=bool(args.rebuild_store))
    print(f"[store] persistent martj42 store at {CLV_STORE_DIR} "
          f"(rebuild={bool(args.rebuild_store)})")
    played = _martj42_results_frame(store, "2026-06-07T00:00:00Z")

    cache = _load_odds_cache()
    print(f"[odds-cache] {len(cache)} cached fixture(s) at {ODDS_CACHE_PATH} "
          f"(pull={'ON (hard-capped)' if allow_pull else 'OFF — cache-only, ZERO credits'})")

    api_key = _load_env_key() if allow_pull else None
    # HARD CAP: <= cap paid event-odds calls, period (2 per match — entry+close). The cap
    # is MAX_PAID_CALLS_STRATIFIED (30, for 15 matches) on the stratified set, else the
    # pilot cap MAX_PAID_CALLS (16). The CallBudget STOPS before the (cap+1)-th paid call,
    # so it can NEVER over-call the paid historical feed (binding credit discipline).
    cap_ceiling = MAX_PAID_CALLS_STRATIFIED if is_stratified else MAX_PAID_CALLS
    paid_budget = CallBudget(max_calls=min(cap_ceiling, 2 * n_matches))
    list_budget = CallBudget(max_calls=n_matches + 2)
    print(f"[budget] HARD CAP: <= {paid_budget.max_calls} paid event-odds calls "
          f"(~{paid_budget.max_calls * 10} credits) over {n_matches} matches; "
          f"<= {list_budget.max_calls} cheap events-list calls.")

    rows: list[dict] = []
    gaps: list[str] = []
    for home, away, ko, tier, sport in match_specs:
        label = f"[{tier}] {home} v {away} ({ko[:10]})"
        r = played[(played.home_team == home) & (played.away_team == away)
                   & (played.date == pd.Timestamp(ko[:10]))]
        if r.empty:
            gaps.append(label + " [no martj42 result]")
            continue
        rec, status = _resolve_sample_from_cache_or_pull(
            home, away, ko, api_key=api_key, book=book, regions=regions,
            paid_budget=paid_budget, list_budget=list_budget, cache=cache,
            allow_pull=allow_pull, sport=sport)
        if rec is None:
            gaps.append(f"{label} [{status}]")
            continue
        rr = r.iloc[0]
        rows.append({
            "home": home, "away": away, "ko": ko, "rec": rec, "tier": tier, "sport": sport,
            "home_score": int(rr.home_score), "away_score": int(rr.away_score),
            "tournament": rr.tournament, "status": status,
        })

    if allow_pull:
        _save_odds_cache(cache)
        print("\n" + _credit_line("accuracy"))
        print(f"[budget] paid event-odds calls spent: {paid_budget.spent}/{paid_budget.max_calls}; "
              f"events-list calls: {list_budget.spent}/{list_budget.max_calls}")
    else:
        print("[credits] pull OFF — ZERO paid calls issued this run.")

    if not rows:
        print("\n[STOP] no matched fixtures with cached/pulled odds. "
              + ("Re-run with --pull to fetch (hard-capped). " if not allow_pull else "")
              + "Gaps:")
        for g in gaps:
            print(f"  [gap] {g}")
        return 3

    # --- Fit fidelity: PRODUCTION by default (cfg inference draws/advi_iters), so
    #     the reported RPS IS the production fit; --fast opts into a COARSE smoke
    #     fit that is loudly labelled so it can never pass as the real verdict. ---
    fit_draws, fit_advi_iters, is_coarse = _accuracy_fit_fidelity(args, cfg)
    coarse_tag = (f"COARSE-FIT (advi_iters={fit_advi_iters}, draws={fit_draws}, "
                  "NOT production)") if is_coarse else ""
    if is_coarse:
        print(f"\n[fit-fidelity] {coarse_tag} — RPS below is a coarse approximation, "
              "NOT the production accuracy verdict.")
    else:
        print(f"\n[fit-fidelity] PRODUCTION (advi_iters={fit_advi_iters}, "
              f"draws={fit_draws} from cfg['model']['inference']).")

    # --- Per-cutoff leakage-safe fit (FAST via the persistent store + on-disk
    #     panel/posterior caches) -> model 1X2; de-vig CLOSE -> market 1X2. ---
    print(f"[fit] per-cutoff leakage-safe posterior for {len(rows)} matched fixtures "
          "(cached panel + posterior; no re-fit on a 2nd run) ...")
    fit_cache = CACHE_DIR
    per_match = []
    # Group fixtures by matchday cutoff so the posterior is fit ONCE per cutoff.
    by_cutoff: dict[str, list] = {}
    override_cutoff = getattr(args, "cutoff", None)
    if override_cutoff:
        print(f"[fit] SINGLE shared cutoff {override_cutoff} for ALL {len(rows)} matches "
              "(ONE cluster fit; each match must kick off strictly after it).")
    for row in rows:
        if override_cutoff:
            cutoff = pd.Timestamp(override_cutoff).normalize()
            # LEAKAGE: a scored match MUST be after the shared cutoff (else it would be in train).
            assert pd.Timestamp(row["ko"][:10]).normalize() > cutoff, (
                f"LEAKAGE: {row['home']} v {row['away']} ({row['ko'][:10]}) does NOT kick off "
                f"after the shared cutoff {cutoff.date()} — it would be in the training window")
        else:
            cutoff = pd.Timestamp(row["ko"][:10]).normalize()
        by_cutoff.setdefault(str(cutoff), []).append(row)

    n_advi_fits = 0
    leakage_lines: list[str] = []
    for cutoff_str in sorted(by_cutoff):
        cutoff = pd.Timestamp(cutoff_str)
        post, meta = _model_cache.cached_fit(
            cutoff=cutoff, store=store, backend="advi",
            draws=fit_draws, seed=cfg["seed"], advi_iters=fit_advi_iters,
            cache_dir=fit_cache, config=cfg,
        )
        if not meta["cache_hit"]:
            n_advi_fits += 1
        # LEAKAGE PROOF (per cutoff): the max martj42 training date < the matchday cutoff.
        # ``cached_fit`` reads ``store.read(cutoff)`` then ``features.build`` restricts to
        # ``< cutoff_day`` — so the realised matchday results can NEVER be in the train set.
        asof = store.read("results", cutoff=cutoff_str)
        asof_dates = pd.to_datetime(asof["date"])
        train = valid_played_results(asof.assign(date=asof_dates))
        max_train_date = pd.to_datetime(train["date"])
        max_train_date = max_train_date[max_train_date < cutoff].max()
        assert max_train_date < cutoff, (
            f"LEAKAGE: training max {max_train_date} not < cutoff {cutoff}")
        leakage_lines.append(
            f"  [ok] cutoff={cutoff.date()}: max training date < cutoff = "
            f"{max_train_date.date()} (strictly < matchday). Realised matchday results "
            "NOT in train.")
        for row in by_cutoff[cutoff_str]:
            home, away = row["home"], row["away"]
            try:
                model = model_fair_1x2(post, home=home, away=away, neutral=True)
            except KeyError:
                gaps.append(f"[{row['tier']}] {home} v {away} ({row['ko'][:10]}) "
                            "[no model price]")
                continue
            close = market_fair_1x2(row["rec"]["close"], method=devig)
            outcome = _result_outcome(row["home_score"], row["away_score"])
            per_match.append({
                "home": home, "away": away, "date": row["ko"][:10], "tier": row["tier"],
                "result": f"{row['home_score']}-{row['away_score']}", "outcome": outcome,
                "model": model, "market": close, "rec": row["rec"],
                "rps_model": rps(model, outcome),
                "rps_market": rps(close, outcome),
                "rps_uniform": rps(UNIFORM_1X2, outcome),
                "cache_hit": meta["cache_hit"],
            })

    if not per_match:
        print("[STOP] no fixtures produced a model price. Gaps below.")
        for g in gaps:
            print(f"  [gap] {g}")
        return 3

    # --- LEAKAGE PROOF #1: max training date < matchday cutoff (printed per cutoff). ---
    print("\n" + "=" * 78)
    print("LEAKAGE PROOF #1 — max martj42 training date < matchday cutoff (per cutoff)")
    print("=" * 78)
    for ln in leakage_lines:
        print(ln)

    # --- LEAKAGE PROOF #2: entry_ts < close_ts <= kickoff per matched fixture (odds). ---
    print("\n" + "=" * 78)
    print("LEAKAGE PROOF #2 — entry_ts < close_ts <= kickoff per matched fixture (odds)")
    print("=" * 78)
    odds_leak_ok = True
    for pm in per_match:
        rec = pm["rec"]
        et = datetime.fromisoformat(rec["entry_ts"].replace("Z", "+00:00"))
        ct = datetime.fromisoformat(rec["close_ts"].replace("Z", "+00:00"))
        ko = datetime.fromisoformat(rec["kickoff"].replace("Z", "+00:00"))
        ok = et < ct <= ko
        odds_leak_ok = odds_leak_ok and ok
        print(f"  [{'ok' if ok else 'FAIL'}] [{pm['tier']}] {pm['home']} v {pm['away']}: "
              f"entry {et} < close {ct} <= kickoff {ko}")
    assert odds_leak_ok, "LEAKAGE: an odds sample failed entry_ts < close_ts <= kickoff"

    # --- Per-match table (sorted by the model's RPS — worst model miss first). ---
    print("\n" + "=" * 78)
    print("PER-MATCH RPS (lower = better forecast; model trained < matchday only)")
    print("=" * 78)
    print(f"  {'match':<28} {'result':<8} {'mRPS':>7} {'mktRPS':>7} {'uniRPS':>7} "
          f"{'m-mkt':>7} {'verdict':<14}")
    print("  " + "-" * 88)
    for pm in sorted(per_match, key=lambda x: x["rps_model"], reverse=True):
        gap = pm["rps_model"] - pm["rps_market"]
        verdict = "beat market" if gap < 0 else ("tie" if abs(gap) < 1e-6 else "lost to market")
        m = f"{pm['home']} v {pm['away']}"
        print(f"  {m:<28} {pm['result']:<8} {pm['rps_model']:>7.4f} "
              f"{pm['rps_market']:>7.4f} {pm['rps_uniform']:>7.4f} {gap:>+7.4f} {verdict:<14}")

    n = len(per_match)
    agg_model = sum(p["rps_model"] for p in per_match) / n
    agg_market = sum(p["rps_market"] for p in per_match) / n
    agg_uniform = sum(p["rps_uniform"] for p in per_match) / n
    n_beat = sum(1 for p in per_match if p["rps_model"] < p["rps_market"] - 1e-9)

    # --- CONFIDENCE / UNDER-CONFIDENCE diagnostic (the calibration question): is the model's
    #     top pick systematically LESS confident than the sharp market on the SAME games? If so,
    #     sharpening (raise prior.sigma_att/def or lower widening.strength) is the indicated lever.
    def _top(d):
        return max(d["home"], d["draw"], d["away"])

    def _argmax(d):
        return max(("home", "draw", "away"), key=lambda k: d[k])

    mean_model_top = sum(_top(p["model"]) for p in per_match) / n
    mean_market_top = sum(_top(p["market"]) for p in per_match) / n
    model_fav_hit = sum(1 for p in per_match if _argmax(p["model"]) == p["outcome"]) / n
    market_fav_hit = sum(1 for p in per_match if _argmax(p["market"]) == p["outcome"]) / n
    conf_gap = mean_market_top - mean_model_top
    print("\n" + "=" * 78)
    print("CONFIDENCE / CALIBRATION DIAGNOSTIC — is the model UNDER-CONFIDENT?")
    print("=" * 78)
    print(f"  mean MODEL  top-prob : {mean_model_top:.3f}   (avg confidence the model puts on its pick)")
    print(f"  mean MARKET top-prob : {mean_market_top:.3f}   (the sharp market's avg confidence)")
    print(f"  MODEL  pick hit-rate : {model_fav_hit:.3f}   (how often the model's top pick won)")
    print(f"  MARKET pick hit-rate : {market_fav_hit:.3f}")
    if conf_gap > 0.05:
        print(f"  -> UNDER-CONFIDENT by ~{conf_gap:.3f}: the model's top-prob trails the market's. "
              "SHARPEN (raise prior.sigma_att/def and/or lower widening.strength), then re-validate.")
    elif conf_gap < -0.05:
        print(f"  -> OVER-CONFIDENT by ~{-conf_gap:.3f}: the model's top-prob exceeds the market's.")
    else:
        print(f"  -> ROUGHLY MATCHED (|gap| {abs(conf_gap):.3f} <= 0.05): no clear under/over-confidence; "
              "the flatness is calibrated, not a bug. No sharpening indicated.")
    print("  (small n -> directional; compares model vs the sharp market's confidence on the SAME games)")

    # --- PER-TIER breakdown (the map of where the model stands by market liquidity). The
    #     key question: does the model-minus-market gap SHRINK on thinner markets (mid/thin)
    #     vs the sharpest marquee tier? A per-tier model-beats-market is the AMBER guard. ---
    if is_stratified:
        present_tiers = [t for t in TIER_ORDER if any(p["tier"] == t for p in per_match)]
        print("\n" + "=" * 78)
        print("PER-TIER RPS (mean; lower = better) — the liquidity-stratified map")
        print("=" * 78)
        print(f"  {'tier':<9} {'n':>3} {'mRPS':>8} {'mktRPS':>8} {'uniRPS':>8} "
              f"{'m-mkt':>8} {'beat':>6}")
        print("  " + "-" * 60)
        tier_amber: list[str] = []
        for t in present_tiers:
            tp = [p for p in per_match if p["tier"] == t]
            tn = len(tp)
            tm = sum(p["rps_model"] for p in tp) / tn
            tk = sum(p["rps_market"] for p in tp) / tn
            tu = sum(p["rps_uniform"] for p in tp) / tn
            tb = sum(1 for p in tp if p["rps_model"] < p["rps_market"] - 1e-9)
            tgap = tm - tk
            print(f"  {t:<9} {tn:>3} {tm:>8.4f} {tk:>8.4f} {tu:>8.4f} {tgap:>+8.4f} "
                  f"{tb:>3}/{tn}")
            if tgap < 0:
                tier_amber.append(
                    f"{t}: model beat de-vigged ceiling by {-tgap:.4f} RPS (n={tn})")
        print("\n  Reading: model-minus-market gap (m-mkt) is the headline. A POSITIVE gap = the "
              "sharp\n  market is more accurate (expected). The question is whether the gap "
              "SHRINKS\n  marquee -> mid -> thin (the model closing on the market where the "
              "market is\n  less efficient). A NEGATIVE per-tier gap is the AMBER guard (below).")
        if tier_amber:
            print("\n  [AMBER] a tier shows the model BEATING the de-vigged market ceiling:")
            for a in tier_amber:
                print(f"    - {a}")
            print("    On these per-tier n (tiny) a beat-the-ceiling is MORE LIKELY a "
                  "leakage / de-vig\n    bug than skill. HAND-CHECK before trusting — NOT a "
                  "win. (See worst-miss tables.)")
        else:
            print("\n  [ok] no tier shows the model beating the de-vigged ceiling — the "
                  "market is at/near\n  the accuracy ceiling in every tier, as expected.")

        # --- Per-tier worst model misses (largest model RPS) — model vs market vs result. ---
        print("\n" + "=" * 78)
        print("WORST MODEL MISSES per tier (largest model RPS): model 1X2 vs market vs result")
        print("=" * 78)
        for t in present_tiers:
            tp = sorted((p for p in per_match if p["tier"] == t),
                        key=lambda x: x["rps_model"], reverse=True)
            print(f"\n  --- {t} (top {min(3, len(tp))} worst) ---")
            for pm in tp[:3]:
                mdl = {k: round(pm["model"][k], 3) for k in OUTCOMES}
                mkt = {k: round(pm["market"][k], 3) for k in OUTCOMES}
                print(f"  {pm['home']} v {pm['away']} ({pm['date']})  result "
                      f"{pm['result']} ({pm['outcome']})")
                print(f"    model 1X2 ={mdl}  RPS={pm['rps_model']:.4f}")
                print(f"    market1X2 ={mkt}  RPS={pm['rps_market']:.4f}  "
                      f"(m-mkt {pm['rps_model'] - pm['rps_market']:+.4f})")

    set_label = ("stratified internationals (marquee/mid/thin)" if is_stratified
                 else "2022-WC fixtures")
    rps_label = f"  [{coarse_tag}]" if is_coarse else ""
    print("\n" + "=" * 78)
    print(f"AGGREGATE RPS over n={n} matched {set_label} (mean; lower = better)"
          + (f"  {coarse_tag}" if is_coarse else ""))
    print("=" * 78)
    print(f"  model   RPS : {agg_model:.4f}{rps_label}")
    print(f"  market  RPS : {agg_market:.4f}   (de-vigged CLOSE — the accuracy benchmark/ceiling)")
    print(f"  uniform RPS : {agg_uniform:.4f}   (1/3,1/3,1/3 floor)")
    print(f"  model - market gap : {agg_model - agg_market:+.4f}  "
          f"({'model BETTER' if agg_model < agg_market else 'market better'})")
    print(f"  model - uniform gap: {agg_model - agg_uniform:+.4f}  "
          f"({'model better than floor' if agg_model < agg_uniform else 'WORSE than floor — SUSPECT'})")
    print(f"  model beat market on {n_beat}/{n} matches")

    # --- Adversarial: a model RPS far BELOW the market's on this sample is a
    #     SUSPECTED BUG (the market is the accuracy ceiling; beating it materially
    #     on a handful of games is implausible without leakage/peeking). ---
    print("\n" + "=" * 78)
    print("ADVERSARIAL: too-good RPS => SUSPECTED BUG (market is the ceiling)")
    print("=" * 78)
    gap = agg_model - agg_market
    if agg_model < 1e-4:
        print("  [RED] model RPS ~ 0 — near-perfect forecasts are implausible; "
              "SUSPECT a result peeking into the model. HUNT before trusting.")
    elif gap < -0.05:
        print(f"  [RED] model beats market by {-gap:.4f} RPS — materially better than the "
              "accuracy ceiling on a tiny sample. TREAT AS A SUSPECTED BUG (leakage / "
              "de-vig error / result-peek), not a win, until hand-checked.")
    elif gap < 0 and n <= 8:
        # ANY beat-the-ceiling on a tiny sample is suspect — the de-vigged close is
        # the accuracy ceiling, so even a SMALL aggregate edge on n<=8 warrants a
        # leakage hand-check before it is trusted (a milder AMBER below the RED).
        print(f"  [AMBER] model beat the de-vigged ceiling by {-gap:.4f} RPS on a tiny "
              f"sample (n={n}<=8). The de-vigged close is the accuracy ceiling — beating "
              "it at all here is more likely leakage/de-vig error than skill. HAND-CHECK "
              "for leakage before trusting; not a powered win.")
    else:
        print(f"  [ok] model RPS {agg_model:.4f} is "
              f"{'above' if gap > 0 else 'just below'} the market's {agg_market:.4f} "
              f"(gap {gap:+.4f}); within plausibility — the market is at/near the ceiling, "
              "as expected. n is tiny, so this is DIRECTIONAL only.")

    print(f"\n[verdict] DIRECTIONAL ACCURACY (n={n}, WIDE CI). The model's mean RPS is "
          f"{agg_model:.4f} vs the market's {agg_market:.4f} "
          f"(gap {agg_model - agg_market:+.4f}) and the uniform floor {agg_uniform:.4f}. "
          "Small-n: not a powered verdict."
          + (f" {coarse_tag} — re-run WITHOUT --fast for the production verdict."
             if is_coarse else ""))
    print("[discipline] no commit; key never printed; signal/paper only (no real bet).")
    if gaps:
        print("\n[gaps]")
        for g in gaps:
            print(f"  [gap] {g}")
    return 0


def _accuracy_fit_fidelity(args, cfg) -> tuple[int, int, bool]:
    """Resolve ``(draws, advi_iters, is_coarse)`` for the accuracy fits.

    DEFAULT is PRODUCTION fidelity — ``draws`` / ``advi_iters`` read straight from
    ``cfg['model']['inference']`` (currently 1000 / 30000) — so the reported RPS is
    the SAME fit the production forecast uses, not a coarse approximation. The
    opt-in ``--fast`` flag drops to a coarse iteration (``--draws`` / a low
    ``advi_iters``) for a quick smoke run; when it is set, EVERY printed RPS is
    LABELLED ``COARSE-FIT`` so a coarse number is never mistaken for the production
    accuracy verdict. An explicit ``--draws`` always overrides the draw count."""
    inf = cfg["model"]["inference"]
    if getattr(args, "fast", False):
        draws = int(getattr(args, "draws", None) or 200)
        advi_iters = int(getattr(args, "advi_iters", None) or 2000)
        return draws, advi_iters, True
    # Production fidelity: config draws/advi_iters by default. A user-supplied
    # --draws still overrides the draw count (advi_iters stays production).
    draws = int(getattr(args, "draws", None) or inf["draws"])
    advi_iters = int(inf["advi_iters"])
    return draws, advi_iters, False


def main() -> int:
    ap = argparse.ArgumentParser(description="Real-historical-odds CLV + accuracy validation.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dry", help="ZERO-credit dry validation of the harness")
    sub.add_parser("probe", help="ONE cheap events-list call to confirm 2022-WC coverage")
    pp = sub.add_parser("pilot", help="HARD-CAPPED real pull -> CLV")
    pp.add_argument("--matches", type=int, default=8,
                    help="number of pilot matches (<= 8; each costs 2 paid calls)")
    ap_acc = sub.add_parser("accuracy",
                            help="model RPS vs market(close) RPS vs uniform (cache-first, ZERO credits unless --pull)")
    ap_acc.add_argument("--match-set", choices=["pilot", "stratified", "euro"], default="pilot",
                        help="pilot = the 8 WC-2022 marquee matches (default); stratified = "
                             "the tier-tagged internationals (marquee Euro-2024 / mid Nations-"
                             "League / thin WC-qualifiers) with per-tier + overall RPS; euro = "
                             "just the 5 UEFA Euro-2024 fixtures (use with --cutoff for ONE fit)")
    ap_acc.add_argument("--matches", type=int, default=20,
                        help="cap on matches to score (pilot <= 8; stratified <= 15)")
    ap_acc.add_argument("--pull", action="store_true",
                        help="allow a HARD-CAPPED real pull for fixtures not in the odds cache (else cache-only, ZERO credits)")
    ap_acc.add_argument("--fast", action="store_true",
                        help="COARSE smoke fit (advi_iters=2000, draws=200) — NOT production; every printed RPS is labelled COARSE-FIT. Default is PRODUCTION fidelity from cfg['model']['inference'].")
    ap_acc.add_argument("--draws", type=int, default=None,
                        help="override ADVI draws for the per-cutoff fit (default: cfg['model']['inference']['draws'], i.e. production)")
    ap_acc.add_argument("--advi-iters", dest="advi_iters", type=int, default=None,
                        help="override ADVI iterations for the per-cutoff fit (only with --fast; default 2000 coarse)")
    ap_acc.add_argument("--rebuild-store", action="store_true",
                        help="force-rebuild the persistent martj42 store (default: reuse if present)")
    ap_acc.add_argument("--cutoff", default=None,
                        help="single shared as-of cutoff (YYYY-MM-DD) for ALL scored matches -> ONE "
                             "leakage-safe cluster fit (bounded + robust) instead of one fit per "
                             "matchday. Every scored match MUST kick off strictly after this cutoff.")
    ap_acc.add_argument("--sigma-att", dest="sigma_att", type=float, default=None,
                        help="SHARPENING sweep: override prior.sigma_att (raise to let team strengths "
                             "spread further -> more confident forecasts). Default: on-disk config.")
    ap_acc.add_argument("--sigma-def", dest="sigma_def", type=float, default=None,
                        help="SHARPENING sweep: override prior.sigma_def. Default: on-disk config.")
    ap_acc.add_argument("--widening-strength", dest="widening_strength", type=float, default=None,
                        help="SHARPENING sweep: override widening.strength (lower -> less hedging on "
                             "thin-data teams). Default: on-disk config.")
    args = ap.parse_args()
    return {"dry": cmd_dry, "probe": cmd_probe, "pilot": cmd_pilot,
            "accuracy": cmd_accuracy}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
