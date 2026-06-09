"""DECISIVE sharp-line check for the post-fix totals forward scan (read-only, ONE capped call).

The forward scan showed a wall of +EV totals picks vs the SOFT books. The open question the
diagnostic could not close from disk: could all the soft books be JOINTLY soft, leaving the
model right? This script settles it. It makes ONE live totals pull (cap=1 call) on the SAME
us,uk,eu route the scan uses, then for EVERY matched WC group fixture at the 2.5 line compares
the MARKET-PRIOR-FREE model P(under 2.5) against:
  * the SHARP book (Pinnacle) de-vigged P(under), if Pinnacle posts WC totals; and
  * the de-vigged ALL-BOOK CONSENSUS P(under) (median across every book with a 2.5 line).

If the model disagrees with the sharp/consensus by ~0.1-0.17 in BOTH directions (and the
regression slope of model-on-market > 1), the model is the over-dispersed OUTLIER -> the edges
are model error, not money. If instead the model AGREES with the sharp/consensus (small gap,
slope ~1) while disagreeing only with the soft best price, some edges could be real.

SIGNAL-ONLY. No bet. The model grid NEVER sees odds. Key never printed. Cap=1 paid call.
Run: PYTHONPATH=src .venv/bin/python scripts/sharp_totals_check.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# Reuse the scan's verified script-level helpers + constants (one source of truth, no drift).
_spec = importlib.util.spec_from_file_location(
    "scan_totals_forward", str(Path("scripts/scan_totals_forward.py")))
_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scan)

from wcmodel.config import load_config
from wcmodel.data.devig import shin
from wcmodel.data.sources.odds import parse_totals_snapshot
from wcmodel.data.store import BitemporalStore
from wcmodel.data.sources.results import load_results
from wcmodel.data.tournament import host_home_factor
from wcmodel.dashboard.build import _fixture_utc_commence_date
from wcmodel.live.odds_live import CallBudget, fetch_live_odds
from wcmodel.markets.derived import totals_probs
from wcmodel.model import cache as model_cache

CUTOFF = _scan.CUTOFF
CACHE_DIR = _scan.CACHE_DIR
TOURNAMENT_YAML = _scan.TOURNAMENT_YAML
LINE = 2.5
# Fixtures the diagnostic flagged, spanning BOTH gap directions, for the detail table.
DETAIL = {
    "Portugal v DR Congo", "Ecuador v Curaçao", "France v Iraq", "Saudi Arabia v Uruguay",
    "Iran v New Zealand", "Jordan v Algeria", "Germany v Curaçao", "DR Congo v Uzbekistan",
}


def _e_total(grid: np.ndarray) -> float:
    g = np.asarray(grid, dtype=float)
    idx = np.add.outer(np.arange(g.shape[0]), np.arange(g.shape[1]))
    return float((idx * g).sum())


def _devig_p_under(od: dict) -> float | None:
    """De-vig (Shin) a single book's 2.5 over/under pair -> P(under). None if one-sided."""
    over, under = od.get("over_odds"), od.get("under_odds")
    if over is None or under is None:
        return None
    p_over, p_under = shin([float(over), float(under)])
    return float(p_under)


def main() -> int:
    cfg = load_config()
    sharp_key = cfg["markets"]["totals"].get("sharp_book", "pinnacle")
    # Build the real martj42 bitemporal store the SAME way the scan / build_real_snapshot do.
    store = _scan.build_real_store()

    print("=" * 84)
    print("DECISIVE SHARP-LINE CHECK — model vs Pinnacle / all-book consensus (line 2.5)")
    print(f"  cutoff={CUTOFF}  sharp_book={sharp_key}")
    print("=" * 84)

    posterior, meta = model_cache.cached_fit(
        cutoff=CUTOFF, store=store, backend=cfg["model"]["inference"]["backend"],
        draws=cfg["model"]["inference"]["draws"], seed=cfg["seed"],
        advi_iters=cfg["model"]["inference"]["advi_iters"], cache_dir=CACHE_DIR, config=cfg)
    print(f"[model] posterior ready: cache_hit={meta['cache_hit']} key={meta['key']}")
    assert meta["cache_hit"], "expected a cache HIT (no re-fit) — abort if it would re-fit"

    api_key = _scan._load_env_key()
    budget = CallBudget(max_calls_per_day=1)
    orig_get = _scan._install_credit_capture()
    try:
        print(f"[odds] ONE live totals pull regions={cfg['live']['regions']} market=totals cap=1 ...")
        raw_events = fetch_live_odds(
            api_key=api_key, sport=cfg["live"]["sport_key"], regions=cfg["live"]["regions"],
            market="totals", dry_run=False, budget=budget,
            base_backoff=cfg["live"]["call_budget"]["rate_limit_backoff_seconds"],
            max_retries=cfg["live"]["call_budget"]["max_retries"])
    finally:
        _scan.odds_live.httpx.get = orig_get
        del api_key
    print(f"[odds] pulled {len(raw_events)} events; {_scan._credit_line()}")

    parsed = [parse_totals_snapshot(ev) for ev in raw_events]
    all_book_keys: set[str] = set()
    for ev in parsed:
        all_book_keys.update(ev["books"].keys())
    print(f"[odds] distinct books in pull ({len(all_book_keys)}): {sorted(all_book_keys)}")
    print(f"[odds] SHARP '{sharp_key}' present in pull: {sharp_key in all_book_keys}")

    tdict = yaml.safe_load(TOURNAMENT_YAML.read_text())
    venue_country = {v["city"]: v.get("country") for v in tdict.get("venues", [])}
    group_fixtures = [fx for fx in tdict["fixtures"] if fx.get("match") is None]
    fx_by_key = {(fx["home"], fx["away"], _fixture_utc_commence_date(fx["date"], fx.get("time"))): fx
                 for fx in group_fixtures}

    rows = []
    for ev_raw, ev in zip(raw_events, parsed):
        home, away = _scan._canon(ev["home_team"]), _scan._canon(ev["away_team"])
        cdate = str(_scan._commence_utc_date(ev_raw))
        fx = fx_by_key.get((home, away, cdate))
        if fx is None or not ev["books"]:
            continue
        host_factor = host_home_factor(fx["home"], fx["away"], fx.get("venue"), venue_country, cfg)
        try:
            grid = posterior.predict_scoreline(
                fx["home"], fx["away"], neutral=(host_factor is None), host_factor=host_factor)
        except KeyError:
            continue
        mp = totals_probs(grid, lines=[LINE])
        model_pu = float(mp[LINE]["under"])
        # De-vig every book that posts a 2.5 line; build consensus + sharp.
        devigs = {}
        for bkey, per_line in ev["books"].items():
            od = per_line.get(LINE)
            if od is None:
                continue
            pu = _devig_p_under(od)
            if pu is not None:
                devigs[bkey] = pu
        if not devigs:
            continue
        consensus = float(np.median(list(devigs.values())))
        sharp_pu = devigs.get(sharp_key)
        rows.append({
            "fixture": f"{fx['home']} v {fx['away']}", "model_pu": model_pu,
            "e_total": _e_total(grid), "consensus_pu": consensus,
            "sharp_pu": sharp_pu, "n_books": len(devigs)})

    if not rows:
        print("[result] NO matched fixtures with a 2.5 line — cannot run the check.")
        return 1
    df = pd.DataFrame(rows)
    df["gap_consensus"] = df["model_pu"] - df["consensus_pu"]
    has_sharp = df["sharp_pu"].notna()
    df["gap_sharp"] = df["model_pu"] - df["sharp_pu"]

    print(f"\n[detail] flagged fixtures (model P(under2.5) vs sharp / consensus):")
    print(f"  {'fixture':<34} {'model':>6} {'E[tot]':>6} {'cons':>6} {'sharp':>6} "
          f"{'gap_c':>7} {'gap_s':>7} {'nbk':>3}")
    for _, r in df[df["fixture"].isin(DETAIL)].sort_values("gap_consensus").iterrows():
        sp = f"{r['sharp_pu']:.3f}" if pd.notna(r["sharp_pu"]) else "  -  "
        gs = f"{r['gap_sharp']:+.3f}" if pd.notna(r["sharp_pu"]) else "   -   "
        print(f"  {r['fixture']:<34} {r['model_pu']:6.3f} {r['e_total']:6.2f} "
              f"{r['consensus_pu']:6.3f} {sp:>6} {r['gap_consensus']:+7.3f} {gs:>7} {int(r['n_books']):3d}")

    # Aggregate verdict.
    n = len(df)
    mean_gap_c = float(df["gap_consensus"].mean())
    mean_abs_gap_c = float(df["gap_consensus"].abs().mean())
    n_pos = int((df["gap_consensus"] > 0.02).sum())
    n_neg = int((df["gap_consensus"] < -0.02).sum())
    sd_model = float(df["model_pu"].std())
    sd_cons = float(df["consensus_pu"].std())
    # slope of model on consensus: >1 => model fans out wider than the market (over-dispersion).
    slope, intercept = np.polyfit(df["consensus_pu"], df["model_pu"], 1)
    corr = float(np.corrcoef(df["consensus_pu"], df["model_pu"])[0, 1])

    print(f"\n{'='*84}\n[VERDICT] model vs ALL-BOOK CONSENSUS across {n} matched fixtures (line 2.5):")
    print(f"  mean gap (model-consensus)   = {mean_gap_c:+.3f}   (level; ~0 => centered)")
    print(f"  mean |gap|                   = {mean_abs_gap_c:.3f}   (per-fixture disagreement size)")
    print(f"  bidirectional split          = {n_neg} model-lower / {n_pos} model-higher (|gap|>0.02)")
    print(f"  sd(model P-under) vs market  = {sd_model:.3f} vs {sd_cons:.3f}  "
          f"ratio={sd_model/sd_cons:.2f}x  (>1 => model over-dispersed)")
    print(f"  regression model ~ consensus : slope={slope:.2f} intercept={intercept:+.2f} corr={corr:.2f}")
    print(f"     slope>1 => model fans WIDER than the market (the over-dispersion signature)")
    if has_sharp.any():
        ds = df[has_sharp]
        print(f"  --- vs SHARP ({sharp_key}, n={len(ds)}) ---")
        print(f"  mean gap (model-sharp)       = {float(ds['gap_sharp'].mean()):+.3f}")
        print(f"  mean |gap| vs sharp          = {float(ds['gap_sharp'].abs().mean()):.3f}")
        print(f"  bidirectional vs sharp       = "
              f"{int((ds['gap_sharp']<-0.02).sum())} lower / {int((ds['gap_sharp']>0.02).sum())} higher")
    else:
        print(f"  --- SHARP '{sharp_key}' NOT in the live pull; consensus (all {len(all_book_keys)} "
              f"books) is the market reference ---")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
