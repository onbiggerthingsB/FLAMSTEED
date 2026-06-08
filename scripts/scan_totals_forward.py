#!/usr/bin/env python
"""FORWARD totals (O/U goals) +EV paper-test for the WC-2026 model.

THE FORWARD EDGE TEST. The historical totals backtest is impossible (soft-book
historical totals odds do not exist in the feed). But the CURRENT totals lines DO
exist — a probe confirmed all 72 upcoming WC-2026 group fixtures carry totals from
betmgm / williamhill / betrivers. So this is the LIVE edge: fit the production
posterior at a cutoff strictly BEFORE every fixture, pull the CURRENT soft-book
totals lines ONCE, price the model's O/U probabilities off the leakage-safe
scoreline grid (the grid NEVER sees odds), and paper-log each +EV pick. It is
SIGNAL-ONLY: no bet, no broker, no order path — the ledger is paper, append-only,
gitignored. Realized CLV / ROI are settled LATER (close + result do not exist yet),
so this is the OPENING signal, NOT a verdict.

REUSE (no new model/edge math): the merged engine + the existing helpers ONLY.
  * ``model.cache.cached_fit``            — the content-addressed production posterior.
  * ``scripts.build_real_snapshot``       — the real martj42 store assembly + leakage gate.
  * ``data.tournament.host_home_factor``  — the dashboard's per-fixture host_factor rule.
  * ``dashboard.fixtures.fixture_forecast`` is the dashboard's predict path; here we call
    ``posterior.predict_scoreline`` directly with the SAME (neutral, host_factor) it uses,
    so the grid is identical to the dashboard's — but we keep the full grid for totals.
  * ``markets.derived.totals_probs``      — O/U probs off the grid (market-prior-free).
  * ``markets.totals_edge.totals_edges``  — +EV picks vs the RAW soft-book odds.
  * ``data.sources.odds.parse_totals_snapshot`` — per-book, per-line over/under decimals.
  * ``live.odds_live.fetch_live_odds``    — ONE live pull on the regular /odds route.
  * ``backtest.odds_ingest.event_key``    — the (home, away, UTC-commence-date) join identity.

HARD INVARIANTS (verified + reported):
  * MARKET-PRIOR-FREE: the model grid never sees odds; odds enter only at ``totals_edges``.
  * LEAKAGE: cutoff=now < every fixture's commence (asserted per matched fixture); the
    posterior is trained on ``< cutoff`` only (asserted: max training date < cutoff). No
    result / close is used (none exist for upcoming fixtures).
  * NO FABRICATION: an unmatched fixture / a missing line is a COVERAGE GAP — never a guess.
  * SIGNAL-ONLY: no bet/broker/order path; the ledger is paper, ``is_synthetic=False`` (the
    odds ARE real, current, entry-time) but ``stake`` is a FRACTION, never a wager.
  * CREDITS hard-capped (``--max-calls``, default 4); the API key is NEVER printed (it is
    read via the same .env loader clv_validation uses and only ever handed to httpx).

RUN: ``uv run python scripts/scan_totals_forward.py``
(The fit is bounded: a cache HIT at the production cutoff is instant; a MISS is ONE
~20-min ADVI fit, then cached for reuse. The live pull is ONE call, ~hundreds of credits
for the full WC-2026 board.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd
import yaml

import wcmodel.live.odds_live as odds_live
from wcmodel.backtest.odds_ingest import event_key
from wcmodel.config import load_config
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.odds import parse_totals_snapshot
from wcmodel.data.sources.results import load_results
from wcmodel.data.store import BitemporalStore
from wcmodel.data.tournament import host_home_factor
from wcmodel.live.odds_live import CallBudget, fetch_live_odds
from wcmodel.markets.derived import totals_probs
from wcmodel.markets.totals_edge import totals_edges
from wcmodel.model import cache as model_cache

# The production posterior cutoff — IDENTICAL to scripts/build_real_snapshot.py, so a
# previously built real snapshot's posterior is reused from the content-addressed cache.
CUTOFF = "2026-06-07T00:00:00Z"
CACHE_DIR = Path("data/cache")                 # canonical martj42 source + posterior cache
TOURNAMENT_YAML = Path("config/tournament_2026.yaml")
LEDGER_PATH = Path("reports/totals_paper_ledger.jsonl")  # gitignored, append-only, PAPER

# Captured Odds-API credit headers (key NEVER stored/printed). Populated by the httpx hook
# below so the ONE audited fetch_live_odds call surfaces its credit cost.
_HEADERS: dict[str, str] = {}

# Odds-API <-> martj42 / YAML name reconciliation. Seeded from clv_validation's verified
# NAME_RECONCILE (each entry a confident 1:1 spelling fix, never a fuzzy guess) and EXTENDED
# only with confident WC-2026 spellings. An odds event whose names do not reconcile to a YAML
# fixture is a COVERAGE GAP — never matched to the wrong fixture.
NAME_RECONCILE = {
    "USA": "United States",
    "United States of America": "United States",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Turkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Korea DPR": "North Korea",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}


def _canon(name: str) -> str:
    """Reconcile an Odds-API team name to the martj42 / YAML common-English key."""
    return NAME_RECONCILE.get(name, name)


def _load_env_key() -> str:
    """Read THE_ODDS_API_KEY from os.environ or .env — NEVER printed anywhere.

    Identical loader to clv_validation._load_env_key (one source of truth would be ideal,
    but clv_validation is a script not a package; this is the same six lines)."""
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


def _install_credit_capture():
    """Wrap ``odds_live.httpx.get`` so the audited fetch_live_odds call's response headers
    (``x-requests-used`` / ``x-requests-remaining`` / ``x-requests-last``) are captured —
    WITHOUT changing the audited route logic and WITHOUT ever touching the api key. The key
    rides inside ``params`` (httpx URL-encodes it for the request only); we read headers, the
    key is never logged. Returns the original ``get`` so the caller can restore it."""
    orig_get = odds_live.httpx.get

    def _get(url, *args, **kwargs):
        resp = orig_get(url, *args, **kwargs)
        for h in ("x-requests-remaining", "x-requests-used", "x-requests-last"):
            if h in resp.headers:
                _HEADERS[h] = resp.headers[h]
        return resp

    odds_live.httpx.get = _get
    return orig_get


def _credit_line() -> str:
    return (f"credits used={_HEADERS.get('x-requests-used', '?')} "
            f"remaining={_HEADERS.get('x-requests-remaining', '?')} "
            f"last-call-cost={_HEADERS.get('x-requests-last', '?')}")


def build_real_store():
    """Assemble the real martj42 bitemporal store the SAME way build_real_snapshot.py does:
    the canonical ``data.sources.results.load_results`` write path (fetch-from-cache ->
    normalize -> attach shootouts -> POINT_IN_TIME write keyed on match_id), in a fresh
    isolated dir. (``scripts`` is not an importable package, so this inlines the identical
    six lines build_real_snapshot.build_real_store / clv_validation.build_real_store use.)"""
    store_root = Path(tempfile.mkdtemp(prefix="wc-totals-fwd-store-"))
    store = BitemporalStore(root=store_root)
    load_results(store, cache_dir=CACHE_DIR)
    return store


def _commence_utc_date(event: dict):
    """The Odds-API event's UTC commence DATE (day) — the same identity ``event_key`` uses."""
    return event_key({"home_team": event["home_team"], "away_team": event["away_team"],
                      "commence_time": event["commence_time"]})[2]


def main() -> int:
    ap = argparse.ArgumentParser(description="Forward totals +EV paper-test (signal-only).")
    ap.add_argument("--max-calls", type=int, default=4,
                    help="HARD cap on PAID live odds calls (default 4).")
    ap.add_argument("--too-good-edge", type=float, default=0.15,
                    help="Flag any totals edge above this as a SUSPECTED name/de-vig bug.")
    args = ap.parse_args()

    cfg = load_config()
    tot_cfg = cfg["markets"]["totals"]
    lines = [float(x) for x in tot_cfg["lines"]]
    soft_books = list(tot_cfg["soft_books"])
    edge_threshold = float(tot_cfg["edge_threshold"])
    kelly_fraction = float(cfg["backtest"]["kelly_fraction"])

    now = datetime.now(timezone.utc)
    print("=" * 80)
    print("FORWARD totals +EV paper-test — WC-2026 (SIGNAL-ONLY, no bet).")
    print(f"  cutoff(model/now-as-of) = {CUTOFF}   decision_ts = {now.isoformat()}")
    print(f"  lines = {lines}   edge_threshold = {edge_threshold}   "
          f"kelly_fraction = {kelly_fraction}")
    print(f"  soft_books = {soft_books}")
    print("=" * 80)

    # --- 1. MODEL: production posterior at the cutoff (cache HIT reuse, else ONE bounded fit).
    store = build_real_store()

    # LEAKAGE PROOF: max training date < cutoff (re-read the as-of store, like the snapshot
    # builder + clv_validation). The fit reads store.read(cutoff) then features.build restricts
    # to ``< cutoff`` — this asserts that gate held against the real store.
    asof = store.read("results", cutoff=CUTOFF)
    asof = asof.assign(date=pd.to_datetime(asof["date"]))
    cut_ts = pd.Timestamp(CUTOFF).tz_convert("UTC").tz_localize(None)
    played = valid_played_results(asof)
    max_train = pd.to_datetime(played["date"]).max()
    assert max_train < cut_ts, f"LEAKAGE: max training date {max_train} not < cutoff {cut_ts}"
    print(f"[leakage] read(results, cutoff={CUTOFF}): {len(asof)} rows; "
          f"max VALID-PLAYED training date = {max_train.date()} (< cutoff). "
          "No post-cutoff result in train.")

    print("[model] fitting/loading the production posterior via cached_fit "
          "(cache HIT = instant; MISS = ONE bounded ~20-min ADVI fit, then cached) ...")
    posterior, meta = model_cache.cached_fit(
        cutoff=CUTOFF, store=store, backend=cfg["model"]["inference"]["backend"],
        draws=cfg["model"]["inference"]["draws"], seed=cfg["seed"],
        advi_iters=cfg["model"]["inference"]["advi_iters"],
        cache_dir=CACHE_DIR, config=cfg,
    )
    print(f"[model] posterior ready: cache_hit={meta['cache_hit']} key={meta['key']}")

    # --- 2. ODDS: ONE live pull on the regular /odds route (HARD budget cap; key never printed).
    api_key = _load_env_key()
    budget = CallBudget(max_calls_per_day=args.max_calls)
    orig_get = _install_credit_capture()
    try:
        print(f"[odds] ONE live totals pull: sport={cfg['live']['sport_key']} "
              f"regions={cfg['live']['regions']} market=totals "
              f"(budget cap={args.max_calls} calls) ...")
        raw_events = fetch_live_odds(
            api_key=api_key, sport=cfg["live"]["sport_key"],
            regions=cfg["live"]["regions"], market="totals", dry_run=False,
            budget=budget,
            base_backoff=cfg["live"]["call_budget"]["rate_limit_backoff_seconds"],
            max_retries=cfg["live"]["call_budget"]["max_retries"],
        )
    finally:
        odds_live.httpx.get = orig_get               # restore the unwrapped httpx.get
        del api_key                                  # drop the key reference promptly
    print(f"[odds] pulled {len(raw_events)} live events; "
          f"PAID calls spent={budget.spent}/{args.max_calls}; {_credit_line()}")

    # Parse each event's totals into per-book over/under decimals (only complete both-sided
    # lines survive — a half-priced line is dropped, never a one-sided bet).
    parsed_events = [parse_totals_snapshot(ev) for ev in raw_events]

    # --- 3. MATCH each odds event to a WC-2026 GROUP fixture by (home, away, UTC-commence-date).
    tdict = yaml.safe_load(TOURNAMENT_YAML.read_text())
    venue_country = {v["city"]: v.get("country") for v in tdict.get("venues", [])}
    group_fixtures = [fx for fx in tdict["fixtures"] if fx.get("match") is None]

    # Index fixtures by (home, away, commence-UTC-date). The YAML carries a LOCAL date + a
    # local time-with-offset; reconstruct the UTC commence date EXACTLY as the dashboard's
    # _fixture_utc_commence_date / the scan event_key does (negative-offset evening kickoffs
    # cross the date line) so the odds-event UTC date matches.
    from wcmodel.dashboard.build import _fixture_utc_commence_date
    fx_by_key: dict[tuple, dict] = {}
    for fx in group_fixtures:
        utc_date = _fixture_utc_commence_date(fx["date"], fx.get("time"))
        fx_by_key[(fx["home"], fx["away"], utc_date)] = fx

    matched: list[tuple] = []          # (fixture, parsed_event)
    gaps: list[str] = []
    for ev_raw, ev in zip(raw_events, parsed_events):
        home = _canon(ev["home_team"])
        away = _canon(ev["away_team"])
        cdate = str(_commence_utc_date(ev_raw))
        fx = fx_by_key.get((home, away, cdate))
        if fx is None:
            gaps.append(f"{ev['home_team']} v {ev['away_team']} ({cdate}) "
                        "[no matching WC group fixture]")
            continue
        if not ev["books"]:
            gaps.append(f"{home} v {away} ({cdate}) [matched fixture, but no totals lines]")
            continue
        matched.append((fx, ev))

    print(f"[match] {len(matched)} matched / {len(parsed_events)} odds events "
          f"({len(gaps)} gapped); {len(group_fixtures)} WC group fixtures total.")
    for g in gaps:
        print(f"  [gap] {g}")

    # --- 4. Per matched UPCOMING fixture: predict the grid (dashboard path) -> totals_probs ->
    # totals_edges vs the BEST soft-book ENTRY price per (line, side).
    picks: list[dict] = []
    too_good: list[dict] = []
    scanned = 0
    for fx, ev in matched:
        home, away = fx["home"], fx["away"]
        commence = ev["commence_time"]
        # LEAKAGE (forward): every matched fixture must commence STRICTLY AFTER the cutoff.
        commence_ts = pd.Timestamp(commence)
        assert commence_ts > pd.Timestamp(CUTOFF), (
            f"LEAKAGE: {home} v {away} commences {commence} not after cutoff {CUTOFF}")

        # SAME predict path the dashboard uses: host_factor for a host's in-country home game,
        # neutral otherwise. The grid is MARKET-PRIOR-FREE (no odds in).
        host_factor = host_home_factor(home, away, fx.get("venue"), venue_country, cfg)
        try:
            grid = posterior.predict_scoreline(
                home, away, neutral=(host_factor is None), host_factor=host_factor)
        except KeyError as exc:
            gaps.append(f"{home} v {away} [team {exc} not in posterior — coverage gap]")
            continue
        scanned += 1
        model_probs = totals_probs(grid, lines=lines)

        # BEST soft-book price per (line, side): for each line, take the max over_odds and the
        # max under_odds ACROSS the configured soft books — that is the venue you'd bet, and
        # which book offered it. Only books in cfg.soft_books are eligible (sharp = never bet).
        best_by_line: dict[float, dict] = {}
        for bkey, per_line in ev["books"].items():
            if bkey not in soft_books:
                continue
            for L, od in per_line.items():
                slot = best_by_line.setdefault(float(L), {})
                for side in ("over", "under"):
                    price = od.get(f"{side}_odds")
                    if price is None:
                        continue
                    cur = slot.get(side)
                    if cur is None or price > cur["odds"]:
                        slot[side] = {"odds": float(price), "book": bkey}

        # Build the book_totals dict totals_edges consumes (best price per line/side) AND keep
        # the per-(line,side) winning book so the paper-log records the venue.
        book_totals: dict[float, dict] = {}
        book_for: dict[tuple, str] = {}
        for L, slot in best_by_line.items():
            node = {}
            for side in ("over", "under"):
                if side in slot:
                    node[f"{side}_odds"] = slot[side]["odds"]
                    book_for[(L, side)] = slot[side]["book"]
            # totals_edges only prices a side when its odds exist; a half-line node is harmless.
            book_totals[L] = node

        # se=0.0: forward signal carries no per-line predictive SE here (the shrink is inert),
        # so the bet decision is the raw +EV vs edge_threshold — the same gate the engine uses.
        edges = totals_edges(model_probs, book_totals, edge_threshold=edge_threshold,
                             se=0.0, kelly_fraction=kelly_fraction)

        for e in edges:
            L, side = e["line"], e["side"]
            book = book_for.get((L, side), "?")
            implied = 1.0 / e["odds"]
            rec = {
                "decision_ts": now.isoformat(),
                "fixture": f"{home} v {away}",
                "home": home, "away": away, "commence": commence,
                "line": L, "side": side,
                "model_prob": e["model_prob"], "market_implied": implied,
                "book": book, "entry_odds": e["odds"],
                "edge": e["edge"], "stake": e["stake"],
                "is_synthetic": False, "posterior_key": meta["key"],
            }
            picks.append(rec)
            if e["edge"] > args.too_good_edge:
                too_good.append(rec)

    # --- 5. PAPER-LOG each +EV pick to the gitignored append-only ledger. NO settle (forward).
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a") as fh:
        for rec in picks:
            fh.write(json.dumps(rec, default=str) + "\n")

    # --- 6. PRINT the opening paper-bet list + summary.
    print("\n" + "=" * 80)
    print(f"FORWARD +EV TOTALS PICKS (opening paper bets) — {len(picks)} pick(s):")
    print("=" * 80)
    if not picks:
        print("  (none cleared the edge threshold on this snapshot — a real, honest null "
              "result, not an error.)")
    for p in sorted(picks, key=lambda r: -r["edge"]):
        print(f"  {p['fixture']:<42} {p['side'].upper():<5} {p['line']:<4} "
              f"model={p['model_prob']:.3f} vs mkt-impl={p['market_implied']:.3f} "
              f"edge={p['edge']:+.3f} stake={p['stake']:.4f} @ {p['entry_odds']:.2f} "
              f"({p['book']})")

    lines_hit = sorted({p["line"] for p in picks})
    fixtures_hit = sorted({p["fixture"] for p in picks})
    books_hit = sorted({p["book"] for p in picks})
    total_stake = sum(p["stake"] for p in picks)
    print("\n--- SUMMARY ---")
    print(f"  #picks                 = {len(picks)}")
    print(f"  #fixtures scanned       = {scanned}  (matched & priced)")
    print(f"  #fixtures with a pick   = {len(fixtures_hit)}")
    print(f"  #odds events gapped     = {len(gaps)}")
    print(f"  match rate              = {len(matched)}/{len(parsed_events)} "
          f"odds events matched to a WC group fixture")
    print(f"  lines with a pick       = {lines_hit}")
    print(f"  soft books used         = {books_hit}")
    print(f"  total staked fraction   = {total_stake:.4f} (of bankroll, PAPER)")
    print(f"  credits                 = {_credit_line()} (PAID calls spent {budget.spent})")
    print(f"  posterior_key           = {meta['key']}  (cache_hit={meta['cache_hit']})")
    print(f"  ledger (gitignored)     = {LEDGER_PATH}")

    if too_good:
        print("\n  !! TOO-GOOD EDGE FLAG (> "
              f"{args.too_good_edge:.0%}): SUSPECTED name-mismatch / de-vig bug — "
              "HAND-CHECK before trusting:")
        for p in too_good:
            print(f"     {p['fixture']} {p['side'].upper()} {p['line']} "
                  f"edge={p['edge']:+.3f} model={p['model_prob']:.3f} @ {p['entry_odds']:.2f}")

    print("\nNOTE: this is the FORWARD SIGNAL (opening paper bets), validated by realized "
          "CLV / result LATER as games play — NOT yet a verdict. SIGNAL-ONLY: no bet placed; "
          "ledger is paper; key never printed.")
    return 0


if __name__ == "__main__":
    # Ensure the repo root is importable (so ``scripts.build_real_snapshot`` resolves) and
    # the working dir is the repo root (so relative config/data paths resolve).
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    os.chdir(repo_root)
    raise SystemExit(main())
