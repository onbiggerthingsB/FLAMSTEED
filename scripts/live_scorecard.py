#!/usr/bin/env python
"""Live-2026 calibration scorecard (review-v2 Track 3a).

HONESTY RULE (leads the report): n=79 live matches -> wide CIs. This scorecard
INFORMS the adoption meeting; it never auto-triggers a model change. The
favorite-overconfidence question was CLOSED 2026-06-25 on n=1473 held-out
matches; this extends the evidence, it does not reopen that decision.

PIT discipline: each match dated D is priced by a posterior fit at cutoff
D 00:00Z (training strictly < day D — the daily loop's own semantics). One
production-fidelity fit per distinct match day (~20); the content-addressed
cache turns re-runs into HITs. Store: pure martj42@36675ba (single source —
NO duplicate rows, unaffected by review-v2 finding C2).

Usage: PYTHONPATH=src .venv/bin/python scripts/live_scorecard.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.backtest.baselines import elo_baseline_1x2
from wcmodel.config import load_config
from wcmodel.data.store import BitemporalStore
from wcmodel.data.tournament import host_home_factor, load_tournament
from wcmodel.model.cache import cached_fit
from wcmodel.model.calibration import (_leakage_safe_elo,
                                       favorite_band_reliability, rps,
                                       score_fixtures)

STORE_DIR = Path("data/stores/martj42_36675ba")
OUT_MD = Path("reports/live_scorecard_2026-07-01.md")
OUT_JSON = Path("reports/live_scorecard_2026-07-01.json")


def live_matches(store) -> pd.DataFrame:
    asof = store.read("results", cutoff="2026-07-01T00:00:00Z").copy()
    asof["date"] = pd.to_datetime(asof["date"])
    tl = asof["tournament"].str.lower()
    m = asof[tl.str.contains("fifa world cup") & ~tl.str.contains("qualif")]
    m = m[(m["date"] >= "2026-06-11") & (m["date"] <= "2026-06-30")]
    m = m.dropna(subset=["home_score", "away_score"]).reset_index(drop=True)
    assert len(m) == 79, f"expected 79 scored matches, got {len(m)}"
    return m


def main() -> int:
    cfg = load_config()
    inf = cfg["model"]["inference"]
    store = BitemporalStore(root=STORE_DIR)
    matches = live_matches(store)

    # Host-home pricing map, exactly as production (dashboard/build.py). Keyed
    # by unordered pair so the 3 orientation-reversed store rows still price as
    # host games (finding C1: martj42 may list the fixture reversed).
    t = load_tournament(Path("config") / "tournament_2026.yaml")
    venue_country = {v["city"]: v.get("country") for v in t.get("venues", [])}
    hf_map = {}
    for fx in t["fixtures"]:
        if fx.get("match") is None:
            hf = host_home_factor(fx["home"], fx["away"], fx.get("venue"),
                                  venue_country, cfg)
            if hf is not None:
                hf_map[frozenset((fx["home"], fx["away"]))] = (fx["home"], hf)

    all_rows, elo_rps, model_rps = [], [], []
    fits_missed = 0
    for day, dm in matches.groupby(matches["date"].dt.normalize()):
        cutoff = day.strftime("%Y-%m-%dT00:00:00Z")
        post, meta = cached_fit(cutoff=pd.Timestamp(cutoff), store=store,
                                backend=inf["backend"], draws=inf["draws"],
                                seed=int(cfg["seed"]),
                                advi_iters=inf["advi_iters"],
                                cache_dir="data/cache", config=cfg)
        fits_missed += 0 if meta["cache_hit"] else 1
        print(f"[{day.date()}] {'HIT' if meta['cache_hit'] else 'FIT'} "
              f"{len(dm)} matches", flush=True)
        ho = dm.copy()
        # A host game gets host_factor iff the STORE's home_team IS the host
        # (a reversed row where the host is listed away prices neutral — the
        # conservative production-consistent choice; 0-1 such rows exist).
        hfs, neutrals = [], []
        for h, a in zip(ho["home_team"], ho["away_team"]):
            ent = hf_map.get(frozenset((h, a)))
            if ent is not None and ent[0] == h:
                hfs.append(ent[1]); neutrals.append(False)
            else:
                hfs.append(None); neutrals.append(True)
        ho["host_factor"] = hfs
        ho["neutral"] = neutrals
        rows = score_fixtures(post, ho, cutoff=cutoff)
        ho_stage = "R32" if day >= pd.Timestamp("2026-06-28") else "group"
        by_pair = {(str(r2["home_team"]), str(r2["away_team"])): r2
                   for _, r2 in ho.iterrows()}
        for r in rows:
            src = by_pair[(r["home"], r["away"])]
            r["date"] = str(day.date())
            r["stage"] = ho_stage
            r["total_goals"] = int(src["home_score"]) + int(src["away_score"])
            model_rps.append(rps(r["probs"], r["outcome"]))
            all_rows.append(r)
        elo = _leakage_safe_elo(store, cutoff, config=cfg)
        for _, m2 in ho.iterrows():
            h, a = str(m2["home_team"]), str(m2["away_team"])
            if h in elo and a in elo:
                probs = elo_baseline_1x2(rating_home=elo[h], rating_away=elo[a],
                                         neutral=bool(m2["neutral"]), config=cfg)
                out = ("home" if m2["home_score"] > m2["away_score"] else
                       "away" if m2["home_score"] < m2["away_score"] else "draw")
                elo_rps.append(rps(probs, out))

    bands = favorite_band_reliability(all_rows)
    n = len(all_rows)
    draw_pred = float(np.mean([r["probs"]["draw"] for r in all_rows]))
    draw_real = float(np.mean([r["outcome"] == "draw" for r in all_rows]))
    tails = {k: {"pred": float(np.mean([r[k] for r in all_rows])),
                 "real": float(np.mean([r["realized_margin"] >= g
                                        for r in all_rows]))}
             for k, g in [("p_marg_ge2", 2), ("p_marg_ge3", 3),
                          ("p_marg_ge4", 4)]}
    r32 = [r for r in all_rows if r["stage"] == "R32"]

    def fmt_bands(b):
        hdr = ("| band | n | pred fav-win | real fav-win | ±SE | pred draw "
               "| real draw | RPS |\n|---|---|---|---|---|---|---|---|")
        rows_ = []
        for label, m3 in b.items():
            if not m3 or not m3.get("n"):
                continue
            se = m3.get("real_fav_win_se")
            rows_.append(
                f"| {label} | {m3['n']} | {m3['pred_fav_win']:.3f} "
                f"| {m3['real_fav_win']:.3f} | {se if se is None else f'{se:.3f}'} "
                f"| {m3['pred_draw']:.3f} | {m3['real_draw']:.3f} "
                f"| {m3['mean_rps']:.4f} |")
        return hdr + "\n" + "\n".join(rows_)

    md = [
        "# Live-2026 calibration scorecard (as of 2026-07-01)",
        "",
        "**HONESTY RULE:** n=79 -> wide CIs. This scorecard INFORMS the",
        "adoption meeting; it never auto-triggers a model change (the",
        "2026-06-25 lesson: 72-game live variance is not a bias signal).",
        "",
        f"- matches scored: {n} (72 group + 7 R32); fresh fits this run: "
        f"{fits_missed}",
        f"- model mean RPS: {np.mean(model_rps):.5f} | naive-Elo baseline: "
        f"{np.mean(elo_rps):.5f} (lower better; n_elo={len(elo_rps)})",
        f"- draw rate: predicted {draw_pred:.3f} vs realized {draw_real:.3f}",
        "",
        "## Favorite-band reliability (live)", fmt_bands(bands), "",
        "## Blowout tails (the P4 question, on live data)",
        "| tail | predicted | realized |", "|---|---|---|",
        *[f"| margin>={k[-1]} | {v['pred']:.3f} | {v['real']:.3f} |"
          for k, v in tails.items()],
        "",
        f"## R32 subtable (n={len(r32)})",
        (f"- mean RPS: "
         f"{np.mean([rps(r['probs'], r['outcome']) for r in r32]):.5f}"
         if r32 else "- (none)"),
    ]
    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_MD.write_text("\n".join(md) + "\n")
    OUT_JSON.write_text(json.dumps({"rows": all_rows, "bands": bands,
                                    "tails": tails}, default=str, indent=1))
    print(f"[report] {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
