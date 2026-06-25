"""Favorite-band reliability diagnostic (J/G/K Phase 1, READ-ONLY).

Measures whether the FROZEN production model is over-confident on favorites /
under-predicts draws, bucketed by favorite probability, on leakage-safe held-out
data — over two populations:

  * historical pool: WC-2022 + Euro-2024 + pre-2026 international windows, each
    scored by a model fit at a cutoff strictly before the window;
  * 2026 group stage: each matchday D scored by a model fit at cutoff D (training
    on results strictly < D — i.e. through D-1, mirroring the live daily snapshot
    that produced the forecasts actually shown).

Writes reports/favorite_band_calibration_<date>.{md,json}. NO model change, NO
bundle regen. Run:

    PYTHONPATH=src .venv/bin/python scripts/diagnose_favorite_band.py

Leakage guard (re-asserted per fixture inside calibration.score_fixtures): the
fit's training window is strictly < cutoff; every held-out match is dated on/after
the cutoff day. A held-out match therefore never appears in its own training set.
"""
from __future__ import annotations

import argparse
import glob
import json
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

import wcmodel.model.cache as _model_cache
from wcmodel.config import load_config
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.results import load_results
from wcmodel.data.store import BitemporalStore
from wcmodel.data.tournament import host_home_factor
from wcmodel.live.manual_results import (
    _load_draw,
    _venue_country_map,
    ingest_manual_rows,
    validate_manual_csv,
)
from wcmodel.model.calibration import favorite_band_reliability, score_fixtures

REPORTS_DIR = Path("reports")

# Historical pool: (cutoff, window_end, label). The fit trains on results strictly
# < cutoff; the held-out scoring set is valid-played matches in [cutoff, window_end].
HISTORICAL_SEGMENTS = [
    ("2022-11-20", "2022-12-18", "WC2022"),       # World Cup 2022 finals
    ("2024-06-14", "2024-07-14", "Euro2024"),     # Euro 2024 finals
    ("2025-01-01", "2025-06-30", "intl_2025H1"),  # rolling internationals
    ("2025-07-01", "2025-12-31", "intl_2025H2"),
    ("2026-01-01", "2026-06-10", "intl_2026_preWC"),
]

# 2026 group window (matchday cutoffs derived from played results in the store).
WC2026_GROUP_START = "2026-06-11"
WC2026_GROUP_END = "2026-06-28"


def _all_played(store) -> pd.DataFrame:
    """Every valid-played result, read as-of a far-future cutoff (all settled)."""
    res = store.read("results", cutoff="2027-01-01T00:00:00Z").copy()
    res["date"] = pd.to_datetime(res["date"])
    if getattr(res["date"].dt, "tz", None) is not None:
        res["date"] = res["date"].dt.tz_convert("UTC").dt.tz_localize(None)
    return valid_played_results(res)


def _heldout(played: pd.DataFrame, cutoff: str, window_end: str) -> pd.DataFrame:
    """Valid-played matches in [cutoff_day, window_end_day] — the held-out set for
    a model fit at ``cutoff`` (which trains strictly < cutoff)."""
    c = pd.Timestamp(cutoff).normalize()
    hi = pd.Timestamp(window_end).normalize()
    mask = (played["date"] >= c) & (played["date"] <= hi)
    return played.loc[mask].reset_index(drop=True)


def _apply_host_factor(heldout: pd.DataFrame, venue_country: dict, cfg: dict) -> pd.DataFrame:
    """Add the production-faithful ``host_factor`` + ``neutral`` columns to a 2026
    held-out frame, EXACTLY mirroring dashboard/build.py:573-575: host_factor =
    host_home_factor(home, away, venue_city, venue_country, cfg) (host_k iff the
    HOME team is a 2026 host at a venue in its own country, else None); neutral =
    (host_factor is None). This overrides the raw data ``neutral`` flag so the
    diagnostic scores a host home game at host_k*home_adv (not 1.0*home_adv) and a
    host-listed-away game as neutral — the way the frozen model actually forecast."""
    df = heldout.copy()
    has_city = "city" in df.columns
    hf = [
        host_home_factor(r["home_team"], r["away_team"],
                         (r["city"] if has_city else None), venue_country, cfg)
        for _, r in df.iterrows()
    ]
    df["host_factor"] = hf
    df["neutral"] = [x is None for x in hf]
    return df


def score_population(store, segments, *, label: str, config: dict | None = None,
                     apply_host: bool = False) -> dict:
    """Fit the production model at each segment cutoff, score its held-out window,
    accumulate favorite-band rows across segments, and aggregate.

    ``apply_host`` (2026 population only): recompute each fixture's host_factor +
    neutral from the 2026 draw so host home games are scored as production did."""
    cfg = config or load_config()
    inf = cfg["model"]["inference"]
    played = _all_played(store)
    venue_country = _venue_country_map(_load_draw()) if apply_host else {}
    rows: list = []
    n_heldout = 0
    for cutoff, window_end, _seg in segments:
        ho = _heldout(played, cutoff, window_end)
        if ho.empty:
            continue
        if apply_host:
            ho = _apply_host_factor(ho, venue_country, cfg)
        n_heldout += len(ho)
        post, _meta = _model_cache.cached_fit(
            cutoff=pd.Timestamp(cutoff), store=store, backend="advi",
            draws=int(inf["draws"]), seed=int(cfg["seed"]),
            advi_iters=int(inf["advi_iters"]), cache_dir="data/cache", config=cfg,
        )
        rows.extend(score_fixtures(post, ho, cutoff=cutoff))
    return {"label": label, "n_scored": len(rows), "n_heldout": n_heldout,
            "n_skipped": n_heldout - len(rows), "bands": favorite_band_reliability(rows)}


def _wc2026_segments(played: pd.DataFrame) -> list:
    """One per-matchday segment over the 2026 group window: cutoff D scores the
    matches dated D (model trained on < D). Derived from played 2026 results."""
    lo, hi = pd.Timestamp(WC2026_GROUP_START), pd.Timestamp(WC2026_GROUP_END)
    days = sorted({d.normalize() for d in played["date"]
                   if lo <= d.normalize() <= hi})
    return [(d.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d"), f"WC2026-{d.strftime('%Y-%m-%d')}")
            for d in days]


def _overlay_manual_2026(store) -> int:
    """Ingest the manual dayN.csv 2026 group results into the store (the pinned
    martj42 commit predates the group stage). Each match is observed at end of its
    own match day (D 23:00Z) so the per-matchday walk-forward sees prior days'
    results but never the matchday being scored. Returns rows ingested."""
    rows = []
    for f in sorted(glob.glob("day*.csv")):
        rows.extend(validate_manual_csv(f))
    by_date: dict = defaultdict(list)
    for r in rows:
        by_date[pd.Timestamp(r.date).normalize()].append(r)
    n = 0
    for d, drows in sorted(by_date.items()):
        observed = (d + pd.Timedelta(hours=23)).tz_localize("UTC")
        n += ingest_manual_rows(store, drows, observed_at=observed)
    return n


def _fmt(x, nd=3):
    return "--" if x is None else f"{x:.{nd}f}"


def render_markdown(populations: list) -> str:
    lines = [f"# Favorite-band reliability — {date.today().isoformat()}", "",
             "Read-only diagnostic of the FROZEN model. Predicted vs realized by "
             "favorite-probability band, on leakage-safe held-out data.", ""]
    for pop in populations:
        lines.append(f"## {pop['label']}  (n_scored={pop['n_scored']})")
        lines.append("")
        lines.append("| band | n | pred favwin | real favwin | pred draw | "
                     "real draw | mean RPS | pred P(m>=3) | real P(m>=3) | flag |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for label in ["0.55-0.65", "0.65-0.75", "0.75-0.85", "0.85+", "all"]:
            b = pop["bands"][label]
            flag = "MISCALIBRATED" if b.get("miscalibrated") else ""
            lines.append(
                f"| {label} | {b['n']} | {_fmt(b['pred_fav_win'])} | "
                f"{_fmt(b['real_fav_win'])} | {_fmt(b['pred_draw'])} | "
                f"{_fmt(b['real_draw'])} | {_fmt(b['mean_rps'])} | "
                f"{_fmt(b.get('pred_marg_ge3'))} | {_fmt(b.get('real_marg_ge3'))} | {flag} |")
        lines.append("")
    lines.append("## Phase-2 gate verdict")
    lines.append("")
    lines.append("- Historical pool miscalibrated bands → systematic bias (proceed to a lever).")
    lines.append("- Only 2026 diverges, historical clean → 2026 small-sample noise (lean no change).")
    lines.append("- Neither miscalibrated → ship nothing.")
    lines.append("")
    lines.append("_Verdict to be filled in after reading the tables._")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=str, default=None,
                    help="output stem (default reports/favorite_band_calibration_<date>)")
    ap.add_argument("--skip-2026", action="store_true",
                    help="historical pool only (skip the 2026 group population)")
    args = ap.parse_args(argv)

    cfg = load_config()
    # Assemble the real store from the pinned martj42 commit (historical pool),
    # then overlay the manual 2026 group results (the pin predates the group stage).
    store_root = Path(tempfile.mkdtemp(prefix="wc-favband-store-"))
    store = BitemporalStore(root=store_root)
    load_results(store, cache_dir=cfg["paths"]["cache"])
    print(f"[store] assembled martj42 store at {store_root}")

    pops = [score_population(store, HISTORICAL_SEGMENTS, label="historical_pool", config=cfg)]

    if not args.skip_2026:
        n_manual = _overlay_manual_2026(store)
        print(f"[store] overlaid {n_manual} manual 2026 group result(s)")
        wc26 = _wc2026_segments(_all_played(store))
        if wc26:
            pops.append(score_population(store, wc26, label="wc2026_group",
                                         config=cfg, apply_host=True))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = args.out or str(REPORTS_DIR / f"favorite_band_calibration_{date.today().isoformat()}")
    Path(stem + ".json").write_text(json.dumps(pops, indent=2))
    Path(stem + ".md").write_text(render_markdown(pops))
    print(f"[favorite-band] wrote {stem}.md and {stem}.json")
    for pop in pops:
        print(f"  {pop['label']}: n_scored={pop['n_scored']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
