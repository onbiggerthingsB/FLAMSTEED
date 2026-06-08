#!/usr/bin/env python
"""Totals (O/U goals) +EV edge backtest — REAL martj42 results vs REAL historical totals odds.

OPS-ONLY SCRIPT (signal-only; NO bet path). A thin operator harness that:
  1. Assembles the real bitemporal martj42 store (canonical ``load_results`` -> POINT_IN_TIME).
  2. For a curated set of internationals (each with a real martj42 result AND confirmed Odds-API
     historical coverage — reusing ``clv_validation.STRATIFIED_MATCHES``), pulls the ``totals``
     market at an ENTRY (kickoff-6h) and CLOSE (kickoff-10m) snapshot from the soft book(s) we
     transact against AND the sharp reference (Pinnacle — printed only, NEVER fed to the model).
  3. Per matchday cutoff, fits the leakage-safe posterior (``cached_fit``: trained on < cutoff),
     reads the scoreline grid (``predict_scoreline``), derives ``totals_probs``, and places +EV
     picks (``totals_edges``) vs the RAW ENTRY soft-book odds — the model NEVER sees the odds.
  4. Settles each pick against the realized total goals, records ROI (staked) + CLV (entry vs the
     soft-book close on the bet line), bins a calibration table (model P(over) vs realized
     over-rate, UNBIASED over all scorable fixture/lines), and a sign-flip permutation ``paired_p``
     on the per-bet CLV.
  5. Computes ``totals_verdict`` once on the held-out lockbox slice via
     ``LockboxRegistry.evaluate_on_lockbox`` (a TEMP COPY of the registry by default — the committed
     ``config/lockbox.json`` single shot is NEVER burned by an ops re-run).

GATES / SAFETY (the binding rules):
  * SIGNAL-ONLY. There is no broker/exchange/order path here. This prints signals + a paper verdict.
  * MARKET-PRIOR-FREE. The odds are compared to the model, never fed into the fit (``cached_fit``
    reads ONLY the martj42 store as-of cutoff; ``totals_edges`` is the ONLY place odds enter, after
    the grid is already computed).
  * LEAKAGE-SAFE. The fit reads ``store.read(cutoff)`` + ``date < cutoff_day``; the pick is a
    function of model + ENTRY odds only (the close/result settle, never inform — pinned by
    ``tests/backtest/test_totals_leakage.py``).
  * NO FABRICATION. A missing/half-priced totals line is a coverage gap (``parse_totals_snapshot``
    drops it); a degenerate grid raises (``totals_probs``). No price is ever guessed.
  * CREDIT DISCIPLINE. ``--pull`` is OFF by default (ZERO paid calls). When ON, a hard ``CallBudget``
    refuses past the cap; pulled odds are cached to a gitignored file so a re-run re-spends nothing.
  * THE_ODDS_API_KEY is read from os.environ / .env and is NEVER printed.

HOLD (plan T8 Step 5): the real-data verdict run is GATED on the production calibration verdict
clearing first. This script is the runner; running it for real is a SEPARATE, deliberate action.

RUN (dry, zero credits — prints the plan + the curated set, no network):
    PYTHONPATH=src uv run python scripts/run_totals_backtest.py --fast
RUN (real pull, hard-capped — only after the calibration gate clears):
    PYTHONPATH=src uv run python scripts/run_totals_backtest.py --pull
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

# Path bootstrap: put the repo root on sys.path so ``from scripts.clv_validation import ...``
# resolves under the documented ``PYTHONPATH=src`` invocation (scripts/ is not a package).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import wcmodel.model.cache as _model_cache
from wcmodel.config import load_config
from wcmodel.backtest.lockbox import REGISTRY_PATH, LockboxRegistry
from wcmodel.backtest.totals_backtest import (
    aggregate_totals,
    calibration_table,
    score_totals_row,
    totals_verdict,
)
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.odds import parse_totals_snapshot
from wcmodel.data.sources.results import load_results
from wcmodel.data.store import BitemporalStore

# Reuse the curated, coverage-confirmed match set + the credit-disciplined fetch plumbing from
# the 1X2 CLV validator (same store, same name reconciliation, same hard cap). Importing keeps
# ONE source of truth for the fixtures and the paid-call discipline.
from scripts.clv_validation import (  # noqa: E402  (path bootstrap above)
    CACHE_DIR,
    CallBudget,
    STRATIFIED_MATCHES,
    _canon,
    _http_get,
    _load_env_key,
    _martj42_results_frame,
    fetch_events_list,
)
from wcmodel.data.sources.odds import ODDSAPI_BASE  # noqa: E402


def fetch_event_totals_odds(api_key: str, event_id: str, date_iso: str, *, regions: str,
                            budget: CallBudget, sport: str) -> dict:
    """GET one historical snapshot for one event with ``markets=totals`` (decimal). PAID
    (~credits) -> charged via ``budget`` (the same hard cap as the 1X2 validator). Mirrors
    ``clv_validation.fetch_event_odds`` but for the totals market (h2h would carry no O/U)."""
    url = f"{ODDSAPI_BASE}/historical/sports/{sport}/events/{event_id}/odds"
    resp = _http_get(url, {"apiKey": api_key, "date": date_iso, "markets": "totals",
                           "regions": regions, "oddsFormat": "decimal"}, budget)
    return resp.json()

# Persistent store + gitignored totals-odds cache (a re-run re-spends ZERO credits).
TOTALS_STORE_DIR = Path("data/totals_store")
TOTALS_ODDS_CACHE_PATH = Path("data/totals_odds_cache.json")

# HARD CAP. Each match costs 2 paid calls (entry + close). The curated set is 15 internationals
# -> 30 paid calls. We never issue more; CallBudget raises before the (cap+1)-th paid call.
MAX_PAID_CALLS = 2 * len(STRATIFIED_MATCHES)


# --------------------------------------------------------------------------- #
# Per-fixture venue fidelity (LOCAL to the totals runner — does NOT touch the shared
# STRATIFIED_MATCHES tuple arity, so the clv_validation `accuracy` subcommand is untouched).
#
# The totals edge is the model price vs the soft-book price, so the model price must use the REAL
# venue: forcing neutral=True everywhere zeros the fitted ``home_adv`` even for genuine HOST games
# (e.g. Germany v Hungary, Kazakhstan v Wales, Liechtenstein v Belgium, Faroe Islands v Croatia —
# the listed home side hosts the tie), mis-specifying the model price the edge is compared against.
#
# Basis for the curated set (clv_validation.STRATIFIED_MATCHES):
#   * marquee = UEFA Euro 2024 GROUP games, all played on NEUTRAL German grounds; the listed home
#     team is NOT the tournament host (Germany), so these are genuinely neutral -> neutral=True.
#   * mid = UEFA Nations League 2024 and thin = FIFA WCQ (Europe) — both played at the listed home
#     team's own ground (a genuine host) -> neutral=False (the fitted home_adv applies).
# Any per-fixture exception (a host playing at a neutral site, a relocation) goes in _VENUE_OVERRIDES.
_VENUE_OVERRIDES: dict[tuple[str, str, str], bool] = {
    # (home, away, kickoff_iso): neutral — add genuine exceptions here (none in the current set).
}
_NEUTRAL_GROUND_TIERS = frozenset({"marquee"})   # Euro 2024 group games on neutral German grounds


def _fixture_neutral(home: str, away: str, ko: str, tier: str, sport: str) -> bool:
    """Real venue for one curated fixture: True iff played on a neutral ground (no home_adv).

    Looks up an explicit per-fixture override first, else falls back to the tier basis above
    (marquee Euro-2024 group games = neutral; Nations League / WCQ = the listed home team hosts).
    """
    override = _VENUE_OVERRIDES.get((home, away, ko))
    if override is not None:
        return override
    return tier in _NEUTRAL_GROUND_TIERS


# --------------------------------------------------------------------------- #
# Store assembly (persistent; leakage-neutral — read strictly as-of cutoff).
# --------------------------------------------------------------------------- #
def get_persistent_store(*, rebuild: bool = False) -> BitemporalStore:
    TOTALS_STORE_DIR.mkdir(parents=True, exist_ok=True)
    results_parquet = TOTALS_STORE_DIR / "results.parquet"
    if results_parquet.exists() and not rebuild:
        return BitemporalStore(root=TOTALS_STORE_DIR)
    if results_parquet.exists():
        results_parquet.unlink()
    store = BitemporalStore(root=TOTALS_STORE_DIR)
    load_results(store, cache_dir=CACHE_DIR)
    return store


# --------------------------------------------------------------------------- #
# Gitignored totals-odds cache.
# --------------------------------------------------------------------------- #
def _odds_cache_key(home: str, away: str, ko: str, regions: str) -> str:
    return f"totals|{home}|{away}|{ko[:10]}|{regions}"


def _load_odds_cache() -> dict:
    if TOTALS_ODDS_CACHE_PATH.exists():
        try:
            return json.loads(TOTALS_ODDS_CACHE_PATH.read_text())
        except (ValueError, OSError):
            return {}
    return {}


def _save_odds_cache(cache: dict) -> None:
    TOTALS_ODDS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOTALS_ODDS_CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, indent=2, sort_keys=True, default=str))
    tmp.replace(TOTALS_ODDS_CACHE_PATH)


# --------------------------------------------------------------------------- #
# Totals snapshot -> the {line: {over_odds, under_odds}} the harness consumes.
# --------------------------------------------------------------------------- #
def _totals_lines_for_books(raw_snap: dict, books: list[str]) -> dict:
    """Merge the first available soft book's totals lines (per ``parse_totals_snapshot``).

    Returns ``{line: {over_odds, under_odds}}`` from the FIRST of ``books`` that prices a
    complete (both-sided) line. A line is taken from a SINGLE book (we transact one price), never
    averaged across books (that would be a fabricated price). Empty if no soft book covers it.
    """
    data = raw_snap.get("data") if raw_snap else None
    if not data:
        return {}
    event = data[0] if isinstance(data, list) else data
    parsed = parse_totals_snapshot(event)
    per_book = parsed.get("books", {})
    out: dict[float, dict] = {}
    for bk in books:
        for line, sides in per_book.get(bk, {}).items():
            out.setdefault(line, sides)   # first book wins; never blend prices
    return out


def _sharp_totals_lines(raw_snap: dict, sharp_book: str) -> dict:
    """The sharp reference book's totals lines (printed for context; NEVER fed to the model)."""
    return _totals_lines_for_books(raw_snap, [sharp_book])


# --------------------------------------------------------------------------- #
# Fit fidelity (PRODUCTION by default; --fast = loudly-labelled coarse smoke).
# --------------------------------------------------------------------------- #
def _fit_fidelity(args, cfg) -> tuple[int, int, bool]:
    inf = cfg["model"]["inference"]
    if getattr(args, "fast", False):
        draws = int(getattr(args, "draws", None) or 200)
        advi_iters = int(getattr(args, "advi_iters", None) or 2000)
        return draws, advi_iters, True
    return int(inf["draws"]), int(inf["advi_iters"]), False


# --------------------------------------------------------------------------- #
# Sign-flip permutation null on the per-bet CLV (the local null the plan allows: the
# report module's permutation_null is 1X2-RPS-specific, so a CLV sign-flip is used here).
# --------------------------------------------------------------------------- #
def _sign_flip_paired_p(clvs: list[float], *, shuffles: int, seed: int) -> float:
    """One-sided sign-flip p for mean(CLV) > 0: under H0 each bet's CLV sign is a fair coin, so
    we flip signs ``shuffles`` times and report P(shuffled mean >= observed mean). Fewer than 2
    non-zero CLVs -> NaN (nothing to test)."""
    vals = np.asarray([c for c in clvs if c is not None], dtype=float)
    if vals.size < 2:
        return float("nan")
    observed = float(vals.mean())
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(shuffles):
        signs = rng.choice((-1.0, 1.0), size=vals.size)
        if float((vals * signs).mean()) >= observed:
            ge += 1
    return (ge + 1) / (shuffles + 1)   # add-one smoothing (never a 0 p)


# --------------------------------------------------------------------------- #
# Pull (or read-from-cache) the entry/close totals lines for one fixture.
# --------------------------------------------------------------------------- #
def _resolve_totals_row(home, away, ko, *, api_key, regions, soft_books, sharp_book,
                        paid_budget, list_budget, cache, allow_pull, sport):
    """Return a totals ``row`` dict for ``score_totals_row`` + the sharp-line context, or
    ``(None, reason)`` (coverage gap). Reads the gitignored cache first; only a new fixture
    triggers a (hard-capped) pull. Pure-cache path when ``allow_pull`` is False."""
    key = _odds_cache_key(home, away, ko, regions)
    rec = cache.get(key)
    if rec is None:
        if not allow_pull:
            return None, "no cached odds (re-run with --pull, hard-capped)"
        if paid_budget.spent + 2 > paid_budget.max_calls:
            return None, "paid cap would be exceeded"
        try:
            events = fetch_events_list(api_key, ko, list_budget, sport=sport)
        except httpx.HTTPStatusError as exc:
            return None, f"events-list HTTP {exc.response.status_code}"
        event_id = None
        for ev in events or []:
            if (_canon(ev.get("home_team", "")) == home
                    and _canon(ev.get("away_team", "")) == away):
                event_id = ev.get("id")
                break
        if event_id is None:
            return None, "no Odds-API event matched (name/date)"
        kickoff = datetime.fromisoformat(ko.replace("Z", "+00:00"))
        entry_date = (kickoff - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        close_date = (kickoff - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            entry_raw = fetch_event_totals_odds(api_key, event_id, entry_date, regions=regions,
                                                budget=paid_budget, sport=sport)
            close_raw = fetch_event_totals_odds(api_key, event_id, close_date, regions=regions,
                                                budget=paid_budget, sport=sport)
        except httpx.HTTPStatusError as exc:
            return None, f"event-odds HTTP {exc.response.status_code}"
        rec = {
            "entry": _totals_lines_for_books(entry_raw, soft_books),
            "close": _totals_lines_for_books(close_raw, soft_books),
            "entry_sharp": _sharp_totals_lines(entry_raw, sharp_book),
            "close_sharp": _sharp_totals_lines(close_raw, sharp_book),
            "event_id": event_id,
        }
        cache[key] = rec
    entry = {float(k): v for k, v in (rec.get("entry") or {}).items()}
    close = {float(k): v for k, v in (rec.get("close") or {}).items()}
    if not entry:
        return None, "no soft-book totals lines (coverage gap; never fabricated)"
    return rec, (entry, close)


def cmd_run(args) -> int:
    cfg = load_config()
    totals_cfg = cfg["markets"]["totals"]
    lines = list(totals_cfg["lines"])
    edge_threshold = float(totals_cfg["edge_threshold"])
    soft_books = list(totals_cfg["soft_books"])
    sharp_book = totals_cfg["sharp_book"]
    regions = cfg["live"].get("regions", "eu")
    allow_pull = bool(args.pull)

    print("=" * 78)
    print("TOTALS (O/U goals) +EV EDGE BACKTEST — signal-only; market-prior-free; leakage-safe")
    print("=" * 78)
    print(f"[cfg] lines={lines} edge_threshold={edge_threshold} soft_books={soft_books} "
          f"sharp_book={sharp_book} (sharp = reference ONLY, never fed to the model)")
    print(f"[safety] live.signal_only={cfg['live']['signal_only']} live.dry_run={cfg['live']['dry_run']} "
          "-> NO bet path; this prints signals + a paper verdict only.")
    _venue_flags = [_fixture_neutral(h, a, ko, tier, sp)
                    for h, a, ko, tier, sp in STRATIFIED_MATCHES]
    _n_neutral = sum(1 for f in _venue_flags if f)
    _n_host = len(_venue_flags) - _n_neutral
    print(f"[venue] per-fixture REAL venue: {_n_neutral} neutral-ground (Euro-2024 group), "
          f"{_n_host} genuine HOST (NL/WCQ at the home ground) -> host games keep the fitted "
          "home_adv (NOT forced neutral). The totals edge is priced vs the correctly-specified "
          "model. (assumption documented in ASSUMPTIONS.md > Totals; overrides in _VENUE_OVERRIDES)")
    if not cfg["live"]["signal_only"]:
        print("[ABORT] live.signal_only is False — refusing to run a totals signal without the "
              "signal-only invariant.", file=sys.stderr)
        return 2

    store = get_persistent_store(rebuild=bool(args.rebuild_store))
    cache = _load_odds_cache()
    api_key = _load_env_key() if allow_pull else None
    paid_budget = CallBudget(max_calls=MAX_PAID_CALLS)
    list_budget = CallBudget(max_calls=len(STRATIFIED_MATCHES))

    fit_draws, fit_advi_iters, is_coarse = _fit_fidelity(args, cfg)
    if is_coarse:
        print(f"\n[fit-fidelity] COARSE-FIT (advi_iters={fit_advi_iters}, draws={fit_draws}, "
              "NOT production) — the verdict below is a coarse approximation, re-run WITHOUT "
              "--fast for the production verdict.")
    else:
        print(f"\n[fit-fidelity] PRODUCTION (advi_iters={fit_advi_iters}, draws={fit_draws}).")

    # Resolve the curated fixtures -> totals rows (cache-first; hard-capped pull).
    rows: list[dict] = []
    gaps: list[str] = []
    for home, away, ko, tier, sport in STRATIFIED_MATCHES:
        label = f"[{tier}] {home} v {away} ({ko[:10]})"
        results = _martj42_results_frame(store, cutoff=ko)
        rr = results[(results["home_team"] == home) & (results["away_team"] == away)]
        if rr.empty:
            gaps.append(label + " [no martj42 result]")
            continue
        rr0 = rr.iloc[0]
        rec, payload = _resolve_totals_row(
            home, away, ko, api_key=api_key, regions=regions, soft_books=soft_books,
            sharp_book=sharp_book, paid_budget=paid_budget, list_budget=list_budget,
            cache=cache, allow_pull=allow_pull, sport=sport)
        if rec is None:
            gaps.append(label + f" [{payload}]")
            continue
        entry, close = payload
        rows.append({
            "home": home, "away": away,
            "neutral": _fixture_neutral(home, away, ko, tier, sport),
            "tier": tier, "ko": ko,
            "home_goals": int(rr0.home_score), "away_goals": int(rr0.away_score),
            "entry": entry, "close": close,
            "entry_sharp": rec.get("entry_sharp", {}), "close_sharp": rec.get("close_sharp", {}),
        })

    if allow_pull:
        _save_odds_cache(cache)
        print(f"[budget] paid event-odds calls spent: {paid_budget.spent}/{paid_budget.max_calls}; "
              f"events-list calls: {list_budget.spent}/{list_budget.max_calls}")
    else:
        print("[credits] pull OFF — ZERO paid calls issued this run.")

    if not rows:
        print("\n[STOP] no fixtures with cached/pulled soft-book totals lines."
              + (" Re-run with --pull (hard-capped) to fetch." if not allow_pull else ""))
        for g in gaps:
            print(f"  [gap] {g}")
        return 3

    # Per-cutoff leakage-safe fit -> grid -> totals_probs -> +EV picks vs ENTRY -> settle + CLV.
    by_cutoff: dict[str, list] = {}
    for row in rows:
        cutoff = str(pd.Timestamp(row["ko"][:10]).normalize())
        by_cutoff.setdefault(cutoff, []).append(row)

    scored: list[dict] = []
    calib_rows: list[dict] = []          # ALL scorable fixture/lines (unbiased calibration)
    leakage_lines: list[str] = []
    for cutoff_str in sorted(by_cutoff):
        cutoff = pd.Timestamp(cutoff_str)
        post, meta = _model_cache.cached_fit(
            cutoff=cutoff, store=store, backend="advi", draws=fit_draws,
            seed=cfg["seed"], advi_iters=fit_advi_iters, cache_dir=CACHE_DIR, config=cfg)
        # LEAKAGE PROOF: max martj42 training date < the matchday cutoff.
        asof = store.read("results", cutoff=cutoff_str)
        train = valid_played_results(asof.assign(date=pd.to_datetime(asof["date"])))
        max_train = pd.to_datetime(train["date"])
        max_train = max_train[max_train < cutoff].max()
        assert max_train < cutoff, f"LEAKAGE: training max {max_train} not < cutoff {cutoff}"
        leakage_lines.append(f"  [ok] cutoff={cutoff.date()}: max training date < cutoff = "
                             f"{max_train.date()} (realised matchday NOT in train).")
        for row in by_cutoff[cutoff_str]:
            try:
                res = score_totals_row(post, row, lines=lines, edge_threshold=edge_threshold, se=0.0)
            except KeyError:
                gaps.append(f"[{row['tier']}] {row['home']} v {row['away']} [no model price]")
                continue
            scored.append(res)
            # Unbiased calibration: every line the model + book BOTH price (not only bet ones).
            from wcmodel.markets.derived import totals_probs as _tp
            mp = _tp(post.predict_scoreline(row["home"], row["away"], neutral=row["neutral"]),
                     lines=lines)
            total = row["home_goals"] + row["away_goals"]
            for L in lines:
                if L in row["entry"]:
                    calib_rows.append({"line": L, "p_over": mp[L]["over"], "over_hit": total > L})

    # Aggregate + calibration + sign-flip CLV null + verdict.
    agg = aggregate_totals(scored)
    calib = calibration_table(calib_rows)
    all_bets = [b for r in scored for b in r["bets"]]
    clvs = [b["clv"] for b in all_bets if b["clv"] is not None]
    paired_p = _sign_flip_paired_p(
        clvs, shuffles=int(cfg["backtest"]["permutation_shuffles"]), seed=int(cfg["seed"]))

    print("\n" + "=" * 78)
    print("LEAKAGE PROOF — max martj42 training date < matchday cutoff (per cutoff)")
    print("=" * 78)
    for ln in leakage_lines:
        print(ln)

    print("\n" + "=" * 78)
    print("TOTALS EDGE — per-line + overall ROI + CLV")
    print("=" * 78)
    ov = agg["overall"]
    for L in sorted(agg["by_line"]):
        s = agg["by_line"][L]
        print(f"  line {L}: n_bets={s['n_bets']} roi={s['roi']:.4f} "
              f"beat_close={s['beat_close_rate']:.3f} avg_clv={s['avg_clv']:.4f}")
    print(f"  OVERALL: n_bets={ov['n_bets']} roi={ov['roi']:.4f} "
          f"beat_close={ov['beat_close_rate']:.3f} avg_clv={ov['avg_clv']:.4f} paired_p={paired_p:.4f}")

    print("\n" + "=" * 78)
    print("CALIBRATION — model P(over) vs realized over-rate (UNBIASED: all scorable lines)")
    print("=" * 78)
    for (lo, hi), c in sorted(calib.items()):
        print(f"  P(over) in [{lo:.1f},{hi:.1f}): n={c['n']} predicted={c['predicted']:.3f} "
              f"observed={c['observed']:.3f}")

    # Lockbox-gated verdict on the held-out slice. By DEFAULT use a TEMP COPY of the committed
    # registry so an ops re-run NEVER burns config/lockbox.json's single shot; --use-real-lockbox
    # is the deliberate, one-time burn (only after the calibration gate clears, plan T8 Step 5).
    if args.use_real_lockbox:
        registry_path = REGISTRY_PATH
        print("\n[lockbox] using the REAL committed registry — this BURNS the single shot.")
    else:
        tmp = Path(tempfile.mkdtemp(prefix="totals-lockbox-")) / "lockbox.json"
        shutil.copy(REGISTRY_PATH, tmp)
        registry_path = tmp
        print(f"\n[lockbox] using a TEMP COPY ({tmp}) — the committed registry is NOT burned.")

    def _eval_fn() -> dict:
        # The single permitted lockbox evaluation returns the held-out totals verdict.
        return {"verdict": totals_verdict(ov, paired_p=paired_p), "agg": ov, "paired_p": paired_p}

    registry = LockboxRegistry.load(path=registry_path)
    lockbox_result = registry.evaluate_on_lockbox(_eval_fn)

    print("\n" + "=" * 78)
    print(f"VERDICT (lockbox-gated): {lockbox_result['verdict'].upper()}")
    print("=" * 78)
    print("  accept iff avg_clv>0 AND roi>=0 AND sign-flip paired_p<0.05 (NaN/None -> reject). "
          "If REJECT: 'tested, no soft-book totals edge, not bet.'")
    for g in gaps:
        print(f"  [gap] {g}")
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Totals (O/U goals) +EV edge backtest (signal-only, leakage-safe, gated).")
    ap.add_argument("--pull", action="store_true",
                    help="allow REAL hard-capped historical-odds pulls (default OFF: zero credits)")
    ap.add_argument("--fast", action="store_true",
                    help="coarse smoke fit (loudly labelled NOT production); default = production")
    ap.add_argument("--draws", type=int, default=None, help="override per-cutoff fit draws")
    ap.add_argument("--advi-iters", dest="advi_iters", type=int, default=None,
                    help="override ADVI iterations (only meaningful with --fast)")
    ap.add_argument("--rebuild-store", action="store_true",
                    help="re-ingest the martj42 store from cache (default: reuse persistent store)")
    ap.add_argument("--use-real-lockbox", action="store_true",
                    help="BURN the committed single-use lockbox (deliberate; default = temp copy)")
    return ap


def main(argv=None) -> int:
    args = _build_argparser().parse_args(argv)
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
