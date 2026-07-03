#!/usr/bin/env python
"""Lever-B k re-sweep runner (prereg docs/superpowers/specs/2026-07-02-bk-levers-prereg.md).
Fits k_att=k_def=k arms at 3 cutoffs, scores per-match held-out 1X2 RPS on the
review-v2 185-pool windows, writes bk_rps_k<k>.json per arm. Also supports the
Lever-K NUTS arm via --backend nuts (k fixed at the production 0.6).

Usage: PYTHONPATH=src .venv/bin/python bk_sweep.py --ks 0.0,0.4,0.5,0.6,0.7,0.8 <outdir>
       PYTHONPATH=src .venv/bin/python bk_sweep.py --backend nuts --ks 0.6 <outdir>
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.data.store import BitemporalStore
from wcmodel.data.tournament import host_home_factor, load_tournament
from wcmodel.model.cache import cached_fit

STORE = Path("data/stores/martj42_36675ba")
WINDOWS = [("wc2022", "2022-11-20T00:00:00Z", "2022-11-20", "2022-12-18", False),
           ("euro2024", "2024-06-14T00:00:00Z", "2024-06-14", "2024-07-14", False),
           ("wc2026", "2026-06-11T00:00:00Z", "2026-06-11", "2026-06-27", True)]
LABELS = {"wc2022": "fifa world cup", "euro2024": "uefa euro",
          "wc2026": "fifa world cup"}


def grid_to_1x2(grid):
    g = np.asarray(grid, dtype=float); g = g / g.sum()
    return {"home": float(np.tril(g, -1).sum()), "draw": float(np.trace(g)),
            "away": float(np.triu(g, 1).sum())}


def rps_1x2(p, outcome):
    cum_p = np.cumsum([p["home"], p["draw"], p["away"]])
    cum_o = np.cumsum([outcome == "home", outcome == "draw", outcome == "away"])
    return float(np.sum((cum_p[:2] - cum_o[:2]) ** 2) / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--ks", default="0.0,0.4,0.5,0.6,0.7,0.8")
    ap.add_argument("--backend", default=None)
    args = ap.parse_args()
    out = Path(args.outdir)
    ks = [float(x) for x in args.ks.split(",")]

    base = load_config()
    inf = base["model"]["inference"]
    backend = args.backend or inf["backend"]
    store = BitemporalStore(root=STORE)
    t26 = load_tournament(Path("config") / "tournament_2026.yaml")
    vc = {v["city"]: v.get("country") for v in t26.get("venues", [])}
    hf_map = {}
    for f in t26["fixtures"]:
        if f.get("match") is None:
            hf = host_home_factor(f["home"], f["away"], f.get("venue"), vc, base)
            if hf is not None:
                hf_map[(f["home"], f["away"])] = hf

    print(f"[prereg] arms k={ks} backend={backend}; production strength_prior:",
          base["model"].get("strength_prior"), flush=True)

    for k in ks:
        cfg = copy.deepcopy(base)
        sp = cfg["model"].setdefault("strength_prior", {})
        sp["k_att"] = float(k)
        sp["k_def"] = float(k)
        per_match = {}
        for tag, cutoff, lo, hi, inclusive in WINDOWS:
            asof = store.read("results", cutoff="2026-07-01T00:00:00Z").copy()
            asof["date"] = pd.to_datetime(asof["date"])
            tl = asof["tournament"].str.lower()
            sel = tl.str.contains(LABELS[tag]) & ~tl.str.contains("qualif")
            sel &= (asof["date"] >= lo) if inclusive else (asof["date"] > lo)
            sel &= asof["date"] <= hi
            ho = asof[sel].dropna(subset=["home_score", "away_score"])
            post, meta = cached_fit(cutoff=pd.Timestamp(cutoff), store=store,
                                    backend=backend, draws=inf["draws"],
                                    seed=int(cfg["seed"]),
                                    advi_iters=inf["advi_iters"],
                                    cache_dir="data/cache", config=cfg)
            print(f"[k={k} {tag}] {'HIT' if meta['cache_hit'] else 'FIT'} "
                  f"n={len(ho)} key={meta['key']}", flush=True)
            known = set(post.teams)
            for _, m in ho.iterrows():
                h, a = str(m["home_team"]), str(m["away_team"])
                if h not in known or a not in known:
                    continue
                if tag == "wc2026":
                    hf = hf_map.get((h, a)); neutral = hf is None
                else:
                    hf, neutral = None, bool(m["neutral"])
                grid = post.predict_scoreline(h, a, neutral=neutral, max_goals=8,
                                              host_factor=hf)
                p = grid_to_1x2(grid)
                o = ("home" if m["home_score"] > m["away_score"] else
                     "away" if m["home_score"] < m["away_score"] else "draw")
                per_match[f"{tag}|{m['date'].date()}|{h}|{a}"] = {
                    "rps": rps_1x2(p, o), "p_fav": max(p["home"], p["away"])}
        suffix = f"k{k}" if backend == inf["backend"] else f"{backend}_k{k}"
        (out / f"bk_rps_{suffix}.json").write_text(json.dumps(per_match, indent=1))
        print(f"[k={k}] wrote {len(per_match)} matches -> bk_rps_{suffix}.json",
              flush=True)


if __name__ == "__main__":
    main()
