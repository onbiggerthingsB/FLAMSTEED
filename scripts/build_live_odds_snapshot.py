#!/usr/bin/env python
"""Build a REAL WC-2026 dashboard snapshot LIT WITH REAL MARKET ODDS — the funded
real-feed flip (Phase-5 §2.1 / the deliberately-deferred ASSUMPTIONS checklist item).

OPS-ONLY SCRIPT. This file adds NO model/pipeline behaviour. It is a thin operator
harness that (1) assembles the real martj42 bitemporal store EXACTLY like
``scripts/build_real_snapshot.py``; (2) performs the ONE funded, gated live-odds pull via
the project's ``wcmodel.live.odds_live.fetch_live_odds(dry_run=False)``; (3) reconciles the
Odds-API team names to the verified ``config/tournament_2026.yaml`` draw and shapes ONE
decision-time (entry-only) ``is_synthetic=False`` live sample per matched future fixture; and
(4) calls the unchanged, already-leakage-gated orchestrator ``dashboard.build.build_snapshot``
with those real samples as ``items=``. Every number in the bundle is produced by the unchanged
pipeline (posterior fit -> MC sim -> scan/decide -> schedule/why assembly). This script only
wires the real store + the real odds into that orchestrator and prints the resulting bundle.

LEAKAGE (the binding rule), proven at run time:
  * CUTOFF = the CURRENT UTC INSTANT at fetch time (NOT the hardcoded 2026-06-07). The model
    trains on results ``< cutoff``; the odds ``entry_ts = cutoff``; each fixture
    ``commence > cutoff`` (future). So ``entry_ts <= cutoff < commence`` holds by construction.
  * ``verify_cutoff_gate`` (mirrored from build_real_snapshot.py) re-reads the store at the
    cutoff and FAILS LOUD if any TRAINING row is dated ``>= cutoff``.
  * Per real sample we ASSERT ``entry_ts <= cutoff < commence`` and DROP (-> coverage_gap) any
    fixture that violates it. A post-kickoff price is never used.
  * Real samples are stamped ``is_synthetic=False`` (the canonical ``_is_synthetic`` key) on
    BOTH the wrapper AND every nested snapshot so ``_bundle_is_synthetic`` flips the bundle to
    REAL. ``cfg["dashboard"]["dry_run"]`` is set False IN-MEMORY for this funded build only
    (the committed YAML default stays True — this is the gated flip).

SIGNAL-ONLY stays True (``live.signal_only`` untouched): there is NO bet path; this only
produces signals + the dashboard. We fetch ONLY the ``h2h`` (1X2) market — the per-fixture
edge feed; NOT the outright market (the dashboard renders no champion edge).

RUN: ``PYTHONPATH=src uv run python scripts/build_live_odds_snapshot.py``
(Expect minutes: a 48-team posterior fit + a 20k-sim Monte-Carlo tournament. Reuses the
content-addressed posterior cache if warm.)
"""
from __future__ import annotations

import os
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from wcmodel.backtest.odds_ingest import _SYNTHETIC_KEY, _parse_ts
from wcmodel.config import load_config
from wcmodel.dashboard.build import _bundle_is_synthetic, build_snapshot
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.results import load_results
from wcmodel.data.store import BitemporalStore
from wcmodel.live.odds_live import fetch_live_odds, wrap_live_response

CACHE_DIR = Path("data/cache")
PUBLIC_BUNDLE = Path("dashboard-ui/public/bundle")

# Odds-API team name -> tournament_2026.yaml name. Only the genuinely-divergent names are
# listed; an identical name needs no entry. NEVER a fuzzy guess — an unmatched fixture stays a
# coverage_gap (honest). Extend ONLY with a name verified against the YAML team list.
NAME_RECONCILE = {
    "USA": "United States",
    "United States of America": "United States",
    "South Korea": "South Korea",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Iran": "Iran",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Turkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Ivory Coast": "Ivory Coast",
    "DR Congo": "DR Congo",
    "Congo DR": "DR Congo",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Curacao": "Curaçao",
}


def build_real_store(store_root: Path) -> BitemporalStore:
    """Assemble the real martj42 bitemporal store via the canonical load path (unchanged)."""
    store = BitemporalStore(root=store_root)
    load_results(store, cache_dir=CACHE_DIR)
    return store


def verify_cutoff_gate(store: BitemporalStore, cutoff: str) -> pd.Timestamp:
    """LEAKAGE GUARD (fail-loud), mirrored from build_real_snapshot.py but at the real ``now``.

    Re-read the store at ``cutoff`` and assert NO post-cutoff result leaked into training.
    Returns the cutoff day (tz-naive normalized) for downstream assertions."""
    asof = store.read("results", cutoff=cutoff)
    dates = pd.to_datetime(asof["date"])
    cut_day = pd.Timestamp(cutoff).tz_convert("UTC").tz_localize(None).normalize()
    leaked = asof[dates >= cut_day]
    played = valid_played_results(asof)
    played_max = pd.to_datetime(played["date"]).max()
    print(f"[leakage] read(results, cutoff={cutoff}): {len(asof)} rows; "
          f"max date = {dates.max()}; max VALID-PLAYED date = {played_max}")
    if len(leaked) > 0:
        print(f"[leakage] ABORT: {len(leaked)} row(s) dated >= cutoff leaked into the as-of "
              f"read — refusing to build a contaminated snapshot:", file=sys.stderr)
        print(leaked[["date", "home_team", "away_team", "home_score", "away_score"]]
              .head(20).to_string(), file=sys.stderr)
        raise SystemExit(1)
    if played_max >= cut_day:
        print(f"[leakage] ABORT: max valid-played date {played_max} is not strictly before "
              f"the cutoff {cut_day}.", file=sys.stderr)
        raise SystemExit(1)
    print("[leakage] OK: every training row is strictly before the cutoff.")
    return cut_day


def _load_env_key() -> str:
    """Read THE_ODDS_API_KEY from os.environ or a local .env — NEVER printed anywhere."""
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


# Captures the LAST live HTTP response headers (rate-limit credits) WITHOUT exposing the key:
# the gated adapter ``fetch_live_odds`` returns only the parsed JSON, so we attach a one-shot
# httpx event hook to read ``x-requests-remaining`` / ``x-requests-used`` off the response.
_LAST_HEADERS: dict[str, str] = {}


def _capture_headers(response: httpx.Response) -> None:
    for h in ("x-requests-remaining", "x-requests-used", "x-requests-last"):
        if h in response.headers:
            _LAST_HEADERS[h] = response.headers[h]


def fetch_real_h2h(api_key: str, cfg: dict) -> list[dict]:
    """The ONE funded, gated live pull (h2h only). Routes the spend THROUGH the project's
    ``fetch_live_odds(dry_run=False)`` (the L1 spend gate). An httpx event hook captures the
    rate-limit headers off the live response so we can report exact credits spent."""
    live = cfg["live"]
    # Wrap httpx.get so the gated adapter's call still goes through, but its Response runs our
    # header-capture hook. We do NOT change the adapter; we only observe its response headers.
    orig_get = httpx.get

    def _get_with_hook(*args, **kwargs):
        resp = orig_get(*args, **kwargs)
        _capture_headers(resp)
        return resp

    httpx.get = _get_with_hook  # type: ignore[assignment]
    try:
        events = fetch_live_odds(
            api_key=api_key,
            sport="soccer_fifa_world_cup",
            regions="us,uk,eu",
            market="h2h",
            dry_run=False,  # REQUIRED: the L1 spend gate; the user authorized this single flip.
        )
    finally:
        httpx.get = orig_get  # type: ignore[assignment]
    return events


def _canon(name: str) -> str:
    """Reconcile an Odds-API team name to the tournament name (identity if no mapping)."""
    return NAME_RECONCILE.get(name, name)


def _sharp_prices(event: dict, bookmaker: str) -> dict | None:
    """De-vig-INPUT decimal odds {home, draw, away} for the event from a SHARP book.

    Prefer the configured sharp book (``pinnacle``) if present; else the MEDIAN decimal price
    across ALL books carrying a complete h2h (3-way) market. Outcomes are relabeled from the
    API's team-named outcomes to {home, draw, away}. Returns None if no book has a complete
    h2h market (-> the fixture stays a coverage_gap; never a fabricated price)."""
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
    # 1) Prefer the configured sharp book.
    for book in books:
        if book.get("key") == bookmaker:
            p = _three_way(book)
            if p is not None:
                return p
    # 2) Else median across every book with a complete 3-way h2h.
    triples = [t for t in (_three_way(b) for b in books) if t is not None]
    if not triples:
        return None
    return {o: float(statistics.median(t[o] for t in triples)) for o in ("home", "draw", "away")}


def _entry_snapshot(home: str, away: str, commence: str, prices: dict, entry_ts: str,
                    book_key: str) -> dict:
    """One REAL decision-time (entry-only) snapshot in the Odds-API ``{timestamp,data}`` shape
    the pipeline consumes. The sharp prices are exposed UNDER the configured book key (so the
    single-book decide path reads them) with the API team-named outcomes. Stamped
    ``is_synthetic=False`` on the snapshot (the canonical key) so it reads REAL by construction.
    There is NO close snapshot — an unplayed future fixture has no close yet; the edge + ghost
    line come from the de-vigged ENTRY (CLV is correctly N/A until kickoff)."""
    return {
        _SYNTHETIC_KEY: False,
        "timestamp": entry_ts,
        "previous_timestamp": entry_ts,
        "next_timestamp": entry_ts,
        "data": [{
            "id": f"REAL_{home}_{away}_{commence}",
            "sport_key": "soccer_fifa_world_cup",
            "commence_time": commence,
            "home_team": home,
            "away_team": away,
            "bookmakers": [{
                "key": book_key,
                "last_update": entry_ts,
                "markets": [{
                    "key": "h2h",
                    "last_update": entry_ts,
                    "outcomes": [
                        {"name": home, "price": prices["home"]},
                        {"name": "Draw", "price": prices["draw"]},
                        {"name": away, "price": prices["away"]},
                    ],
                }],
            }],
        }],
    }


def build_real_samples(events: list[dict], cfg: dict, cutoff: str, cut_day: pd.Timestamp):
    """Reconcile API events to the verified draw and shape ONE entry-only real sample per
    matched FUTURE group fixture. Returns (items, match_report)."""
    import yaml

    tour = yaml.safe_load((Path("config") / "tournament_2026.yaml").read_text())
    group_fixtures = [f for f in tour["fixtures"] if f.get("match") is None]
    book = cfg["live"]["bookmaker"]
    cutoff_dt = _parse_ts(cutoff)

    # Index API events by the reconciled (home, away, UTC-commence-date) — the edges_by_event key.
    api_by_key: dict[tuple, dict] = {}
    for ev in events:
        try:
            commence = ev["commence_time"]
            ckey = (_canon(ev["home_team"]), _canon(ev["away_team"]),
                    str(_parse_ts(commence).astimezone(timezone.utc).date()))
        except Exception:
            continue
        api_by_key.setdefault(ckey, ev)

    items: list[dict] = []
    matched: list[str] = []
    unmatched: list[str] = []
    dropped: list[str] = []

    from wcmodel.dashboard.build import _fixture_utc_commence_date

    for fx in group_fixtures:
        home, away = fx["home"], fx["away"]
        utc_date = _fixture_utc_commence_date(fx["date"], fx.get("time"))
        fkey = (home, away, utc_date)
        ev = api_by_key.get(fkey)
        label = f"{home} vs {away} ({utc_date})"
        if ev is None:
            unmatched.append(label)
            continue
        # Build the de-vig-input sharp prices (pinnacle if present, else median across books).
        # The sample carries the API's ORIGINAL team names (so its outcomes match its own
        # home/away). We re-key by the RECONCILED names so the dashboard edge join lands on the
        # tournament fixture; outcomes still relabel home/draw/away correctly regardless of name.
        prices = _sharp_prices(ev, book)
        if prices is None:
            unmatched.append(label + " [no complete h2h book]")
            continue
        commence = ev["commence_time"]
        # LEAKAGE: entry_ts = cutoff (now); assert entry_ts <= cutoff < commence. Drop (-> gap)
        # any fixture whose kickoff is not strictly in the future (never a post-kickoff price).
        commence_dt = _parse_ts(commence)
        if not (cutoff_dt < commence_dt):
            dropped.append(label + f" [commence {commence} not > cutoff]")
            continue
        # Use the RECONCILED tournament names in the sample so event_key matches the fixture.
        snap = _entry_snapshot(home, away, commence, prices, cutoff, book)
        sample = {_SYNTHETIC_KEY: False, "bet_time": snap}
        items.append({"sample": sample, "liquidity": 1.0, "is_synthetic": False})
        matched.append(label)

    report = {"matched": matched, "unmatched": unmatched, "dropped": dropped,
              "n_group_fixtures": len(group_fixtures), "n_api_events": len(events)}
    return items, report


def main() -> int:
    cfg = load_config()
    out_root = Path(cfg["dashboard"]["output_dir"])

    # CUTOFF = the CURRENT UTC INSTANT (the real "now" at fetch time).
    now = datetime.now(timezone.utc)
    cutoff = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[cutoff] now (UTC) = {cutoff}")

    # --- The real store + the fail-loud leakage gate (BEFORE any spend/fit). ---
    store_root = Path(tempfile.mkdtemp(prefix="wc-live-odds-store-"))
    print(f"[store] assembling real martj42 store at {store_root} ...")
    store = build_real_store(store_root)
    cut_day = verify_cutoff_gate(store, cutoff)

    # --- The ONE funded, gated live pull (h2h only). ---
    api_key = _load_env_key()
    print("[fetch] funded live pull: GET /v4/sports/soccer_fifa_world_cup/odds (h2h, "
          "regions=us,uk,eu, dry_run=False) ...")
    events = fetch_real_h2h(api_key, cfg)
    print(f"[fetch] received {len(events)} live events; credits "
          f"used={_LAST_HEADERS.get('x-requests-used','?')} "
          f"remaining={_LAST_HEADERS.get('x-requests-remaining','?')} "
          f"last-call-cost={_LAST_HEADERS.get('x-requests-last','?')}")

    # --- Reconcile + shape entry-only real samples (is_synthetic=False). ---
    items, report = build_real_samples(events, cfg, cutoff, cut_day)
    print(f"[reconcile] matched {len(report['matched'])}/{report['n_group_fixtures']} "
          f"group fixtures; unmatched={len(report['unmatched'])}; dropped={len(report['dropped'])}")
    for label in report["matched"]:
        print(f"  [matched] {label}")
    for label in report["unmatched"]:
        print(f"  [unmatched] {label}")
    for label in report["dropped"]:
        print(f"  [dropped] {label}")

    # Fail-safe self-check: the items must read REAL (else the whole bundle stays NON-REAL).
    bundle_synth = _bundle_is_synthetic(items)
    print(f"[taint] _bundle_is_synthetic(items) = {bundle_synth} (must be False for a REAL bundle)")
    if items and bundle_synth:
        raise SystemExit("real items did not clear the synthetic taint — refusing to build")

    # --- The funded flip: dashboard.dry_run=False IN-MEMORY ONLY for this build. ---
    cfg["dashboard"]["dry_run"] = False

    print(f"[build] build_snapshot(cutoff={cutoff}, items=<{len(items)} real samples>) — "
          "this takes minutes (48-team posterior fit + 20k-sim MC) ...")
    bundle = build_snapshot(
        cutoff,
        store=store,
        config=cfg,
        tournament=None,            # -> config/tournament_2026.yaml (the verified 48-team draw)
        items=items,                # REAL entry-only samples -> REAL model-vs-market edges
        backtest_records=None,      # -> track.json is an honest coverage_gap
        out_root=out_root,
    )
    print(f"[done] bundle written to: {bundle}")
    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
