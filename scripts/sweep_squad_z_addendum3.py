#!/usr/bin/env python
"""PREREG ADDENDUM 3 — the single post-group-stage k_squad re-evaluation.

TIMING-DEVIATION NOTE (leads every output of this run). Addendum 3 registered
ONE look "after the FINAL group-stage match and before the Round of 32". This
run executes 2026-07-01, with the R32 7 games in — a documented deviation from
the registered TIMING, ruled on by the user (2026-07-01: run now, document).
The ANALYSIS is untainted by construction: every arm refits at the frozen
cutoff 2026-06-11T00:00:00Z (no 2026 result trains any arm) and the evaluation
pool is WC-2022 + Euro-2024 + the 72 GROUP-STAGE matches only (R32 results are
excluded by the eval window). Adoption, if gated in, applies from the R16.

Protocol is otherwise sweep_squad_z.py VERBATIM (same arms, gates, bootstrap):
  arms k_squad in {0,0.2,0.4,0.6} at k_elo=0.6, + the k_elo 0->0.6 yardstick;
  pooled paired bootstrap vs k_squad=0; ADOPT >=75% AND G2 AND sanity;
  <60% CLOSED; 60-75% user call (default no). 15 cells (3 cutoffs x 5).

DEVIATION FROM sweep_squad_z.fit_and_score_cell (this module only, NOT
sweep_squad_z.py): that function scores every held-out row via
``model_fair_1x2(post, home, away, neutral=...)``, which has no host_factor
parameter. The wc2026 pool has 3 host-home group fixtures (a 2026 co-host
playing at home, in-country) that PRODUCTION prices with
``host_factor=host_home_factor(...)`` per ``wcmodel.dashboard.build`` (see
``fixture_forecast(..., neutral=(host_factor is None), host_factor=host_factor)``
there). ``Posterior.predict_1x2`` already accepts ``host_factor`` and reduces
the scoreline grid to 1X2 by summing home/draw/away triangles internally
(``src/wcmodel/model/posterior.py``), so ``fit_and_score_cell_hf`` below is
``fit_and_score_cell`` with ONLY the scoring line changed: when a held-out row
carries a non-null ``host_factor``, price it via
``posterior.predict_1x2(home, away, neutral=False, host_factor=hf)`` instead of
``model_fair_1x2``; every other row (host_factor is None) is priced exactly as
before. RPS, the has_squad=0 slice, max_favorite, and the leakage line are
unchanged.

Usage: PYTHONPATH=src .venv/bin/python scripts/sweep_squad_z_addendum3.py \
           [--n-boot 2000] [--ks 0.0,0.2,0.4,0.6]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sweep_squad_z import (  # noqa: E402
    HELDOUT, K_ELO, K_ELO_YARDSTICK, K_SQUAD_GRID,
    _config_for_cell, _pool_cells, _print_table, _sign_split, _yardstick,
    fit_and_score_cell,
)
from wcmodel.backtest.baselines import OUTCOMES, rps  # noqa: E402
from wcmodel.backtest.squad_sweep import (  # noqa: E402
    MAX_FAVORITE_CEILING, SUPPORT_ADOPT, SUPPORT_NOLIFT, evaluate_gates,
)
from wcmodel.config import load_config  # noqa: E402
from wcmodel.data.sources.squad_anchor import load_squad_anchor  # noqa: E402
from wcmodel.data.store import BitemporalStore  # noqa: E402
import wcmodel.model.cache as _model_cache  # noqa: E402

STORE_DIR = Path("data/stores/martj42_36675ba")   # built by review-v2 Task 0
REPORT_DIR = Path("reports/p3sweep")

#: The Addendum-3 third pool: ALL 72 group games. Frozen fit cutoff 2026-06-11
#: (matches ON June 11 are legitimately held-out: training is date < cutoff day).
#: Window is INCLUSIVE of 2026-06-11 (sweep_squad_z's `date > lo` would drop
#: day-1 games) and ends 2026-06-27 (last group day) so R32 games are excluded.
WC2026 = {
    "tag": "wc2026",
    "cutoff": "2026-06-11T00:00:00Z",
    "lo": "2026-06-11", "hi": "2026-06-27",
    "label_substr": "fifa world cup",
}


def wc2026_heldout(store) -> pd.DataFrame:
    asof = store.read("results", cutoff="2026-07-01T00:00:00Z")
    asof = asof.copy()
    asof["date"] = pd.to_datetime(asof["date"])
    tl = asof["tournament"].str.lower()
    finals = tl.str.contains(WC2026["label_substr"]) & ~tl.str.contains("qualif")
    ho = asof[finals & (asof["date"] >= WC2026["lo"]) & (asof["date"] <= WC2026["hi"])]
    ho = ho.dropna(subset=["home_score", "away_score"]).reset_index(drop=True)
    assert len(ho) == 72, f"Addendum-3 pool must be ALL 72 group games, got {len(ho)}"
    return ho


def host_factor_map_2026(cfg) -> dict:
    """{(home, away): k*home_adv-multiplier-k} for the 3 host-home group fixtures,
    exactly as dashboard/build.py prices them (host_home_factor)."""
    from wcmodel.data.tournament import host_home_factor, load_tournament
    t = load_tournament(Path("config") / "tournament_2026.yaml")
    venue_country = {v["city"]: v.get("country") for v in t.get("venues", [])}
    out = {}
    for fx in t["fixtures"]:
        if fx.get("match") is not None:
            continue
        hf = host_home_factor(fx["home"], fx["away"], fx.get("venue"),
                              venue_country, cfg)
        if hf is not None:
            out[(fx["home"], fx["away"])] = hf
    return out


def _result_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def fit_and_score_cell_hf(*, cutoff: str, tag: str, k_squad: float, base_cfg: dict,
                          store, heldout: pd.DataFrame, k_elo: float = K_ELO) -> dict:
    """``sweep_squad_z.fit_and_score_cell`` with ONE change: a held-out row that
    carries a non-null ``host_factor`` column value is priced via
    ``posterior.predict_1x2(home, away, neutral=False, host_factor=hf)`` (the
    production path for a 2026 host's in-country home group game — see the
    module docstring) instead of ``model_fair_1x2``. Rows with ``host_factor``
    None/absent are priced exactly as ``fit_and_score_cell`` does. RPS, the
    has_squad=0 slice, max_favorite, and the leakage line are all unchanged."""
    cfg = _config_for_cell(base_cfg, tag, k_squad, k_elo)
    inf = cfg["model"]["inference"]
    post, meta = _model_cache.cached_fit(
        cutoff=pd.Timestamp(cutoff), store=store, backend="advi",
        draws=int(inf["draws"]), seed=int(cfg["seed"]),
        advi_iters=int(inf["advi_iters"]), cache_dir=Path("data/cache"), config=cfg,
    )
    anchor = load_squad_anchor(tag)
    known = set(post.teams)
    has_hf_col = "host_factor" in heldout.columns
    overall: list[float] = []
    slice_rps: list[float] = []
    max_favorite = 0.0
    for _, row in heldout.iterrows():
        home, away = str(row["home_team"]), str(row["away_team"])
        if home not in known or away not in known:
            continue
        hf = row["host_factor"] if has_hf_col else None
        hf = None if (hf is None or (isinstance(hf, float) and np.isnan(hf))) else float(hf)
        neutral = False if hf is not None else bool(row["neutral"])
        outcome = _result_outcome(int(row["home_score"]), int(row["away_score"]))
        try:
            p = post.predict_1x2(home, away, neutral, host_factor=hf)
            probs = {o: float(p[o]) for o in OUTCOMES}
        except KeyError:
            continue
        r = rps(probs, outcome)
        overall.append(r)
        max_favorite = max(max_favorite, max(probs.values()))
        if anchor.has_squad.get(home, 0) == 0 or anchor.has_squad.get(away, 0) == 0:
            slice_rps.append(r)
    asof = store.read("results", cutoff=cutoff)
    max_train = pd.to_datetime(asof["date"])
    max_train = max_train[max_train < pd.Timestamp(cutoff[:10])].max()
    return {
        "overall_rps": overall, "slice_rps": slice_rps,
        "n_overall": len(overall), "n_slice": len(slice_rps),
        "n_train": int(len(asof)), "max_train_date": str(max_train.date()),
        "cache_hit": bool(meta["cache_hit"]),
        "max_favorite": float(max_favorite) if overall else float("nan"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--ks", type=str, default=None)
    args = ap.parse_args(argv)
    ks = ([float(x) for x in args.ks.split(",")] if args.ks else list(K_SQUAD_GRID))

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"addendum3_{ts}.md"
    lines: list[str] = []

    def emit(s=""):
        print(s, flush=True)
        lines.append(s)

    emit("# PREREG ADDENDUM 3 — post-group-stage k_squad re-evaluation")
    emit()
    emit("## TIMING-DEVIATION NOTE (read first)")
    emit(__doc__.split("Protocol is otherwise")[0].strip())
    emit()

    base_cfg = load_config()
    seed = int(base_cfg["seed"])
    store = BitemporalStore(root=STORE_DIR)
    hf2026 = host_factor_map_2026(base_cfg)
    emit(f"[2026] host-home fixtures priced with host_factor: {sorted(hf2026)}")

    per_tag_cells: dict[str, list[dict]] = {}
    per_tag_yard: dict[str, list[float]] = {}
    per_tag_k0: dict[str, list[float]] = {}

    specs = list(HELDOUT) + [WC2026]
    for spec in specs:
        tag = spec["tag"]
        if tag == "wc2026":
            heldout = wc2026_heldout(store)
            # Price 2026 host-home rows as production does: host_factor overrides
            # the neutral flag for exactly those 3 fixtures (build.py semantics).
            heldout = heldout.copy()
            heldout["host_factor"] = [
                hf2026.get((h, a)) for h, a in zip(heldout["home_team"],
                                                   heldout["away_team"])
            ]
            score_fn = fit_and_score_cell_hf
        else:
            from sweep_squad_z import _heldout_tournament_frame
            heldout = _heldout_tournament_frame(store, spec)
            heldout = heldout.copy()
            heldout["host_factor"] = None
            score_fn = fit_and_score_cell
        emit(f"\n[{tag}] cutoff {spec['cutoff'][:10]} -> {len(heldout)} held-out matches")
        cells = []
        for k in ks:
            res = score_fn(cutoff=spec["cutoff"], tag=tag, k_squad=k,
                           base_cfg=base_cfg, store=store, heldout=heldout)
            cells.append({"k": k, **res})
            o = np.mean(res["overall_rps"]) if res["overall_rps"] else float("nan")
            emit(f"  [k={k:.2f}] {'HIT' if res['cache_hit'] else 'fit'} "
                 f"RPS={o:.5f} n={res['n_overall']} max_fav={res['max_favorite']:.3f} "
                 f"(train max {res['max_train_date']} < {spec['cutoff'][:10]})")
        per_tag_cells[tag] = cells
        per_tag_k0[tag] = next(c["overall_rps"] for c in cells if abs(c["k"]) < 1e-9)
        yres = score_fn(cutoff=spec["cutoff"], tag=tag, k_squad=0.0,
                        base_cfg=base_cfg, store=store, heldout=heldout,
                        k_elo=K_ELO_YARDSTICK)
        per_tag_yard[tag] = yres["overall_rps"]
        _print_table(tag, cells)

    pooled = _pool_cells(per_tag_cells, ks)
    n_pool = pooled[0]["n_overall"] if pooled else 0
    emit(f"\n[POOLED] {'+'.join(per_tag_cells)} -> {n_pool} held-out matches "
         f"(prereg expectation ~185).")
    _print_table("POOLED", pooled)

    v = evaluate_gates(pooled, seed=seed, n_boot=args.n_boot)
    od, sd = v["overall_delta_vs0"], v["slice_delta_vs0"]
    emit(f"\n[POOLED] knee k_squad={v['knee_k']:.2f}  SUPPORT={v['support']:.1f}%")
    emit(f"  paired dRPS vs k=0 = {od['delta']:+.5f} "
         f"CI95({od['lo95']:+.5f},{od['hi95']:+.5f})")
    emit(f"  G2 slice non-regression = {'PASS' if v['g2_pass'] else 'FAIL'} "
         f"[slice d={sd['delta']:+.5f} CI({sd['lo95']:+.5f},{sd['hi95']:+.5f})]")
    emit(f"  sanity(no >{MAX_FAVORITE_CEILING:.2f} favourite) = "
         f"{'PASS' if v['sanity_pass'] else 'FAIL'} [max_fav={v['max_favorite']:.3f}]")
    split = _sign_split(per_tag_cells, v["knee_k"], seed=seed, n_boot=args.n_boot)
    for tag, s in split.items():
        emit(f"  sign[{tag}]: d={s['delta']:+.5f} support={s['support']:.1f}% -> {s['sign']}")
    y = _yardstick(per_tag_yard, per_tag_k0, seed=seed, n_boot=args.n_boot)
    emit(f"  YARDSTICK k_elo 0->0.6: d={y['delta']:+.5f} support={y['support']:.1f}% "
         f"n={y['n']} (context only)")

    support, knee = v["support"], v["knee_k"]
    if support >= SUPPORT_ADOPT and v["g2_pass"] and v["sanity_pass"]:
        verdict = (f"P3SWEEP VERDICT: ADOPT k_squad={knee:.2f} FOR KNOCKOUTS "
                   f"(R16 onward per deviation ruling) support={support:.1f}%")
    elif support < SUPPORT_NOLIFT:
        verdict = (f"P3SWEEP VERDICT: NO-LIFT — CLOSED this World Cup "
                   f"(support={support:.1f}% < {SUPPORT_NOLIFT:.0f}%)")
    else:
        verdict = (f"P3SWEEP VERDICT: MORNING-CALL (support={support:.1f}% in "
                   f"[{SUPPORT_NOLIFT:.0f},{SUPPORT_ADOPT:.0f}); default no-adopt)")
    emit("\n" + "=" * 78)
    emit(verdict)
    emit("=" * 78)
    report_path.write_text("\n".join(lines) + "\n")
    print(f"[report] {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
