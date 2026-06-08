#!/usr/bin/env python
"""T8 — RUN the REAL rest_days RPS ablation over the martj42 historical store.

OPS-ONLY SCRIPT. Adds NO model behaviour — it assembles the real bitemporal store
the SAME way ``scripts/build_real_snapshot.py`` does (``data.sources.results.load_results``
from the pinned martj42 commit) and calls the unchanged T7 ``run_ablation`` over a real
walk-forward cutoff schedule.

PRIMARY METRIC = paired out-of-sample RPS (needs NO odds): for each cutoff the baseline
(``covariates.enabled=[]``) and the candidate (``enabled=["rest_days"]``) are fit on the
``< cutoff`` data and scored over the IDENTICAL real fixtures PLAYED in the forward window,
the candidate WITH the leakage-safe per-fixture rest_days, the baseline WITHOUT. The delta
is paired; significance is the one-sided sign-flip permutation p (+ Bonferroni). The verdict
is mean_d>0 AND paired_p<0.05 AND CLV-not-worse.

CLV is the SECONDARY guard and needs the gated real feed which we do NOT have. We therefore
run CLV on the CLEARLY-NON-REAL synthetic odds harness (a couple of labelled-synthetic
snapshots over real store fixtures). That taints the whole report ``is_synthetic=True`` — by
design: the decision in THIS run is RPS + the paired permutation p, NOT CLV. No bet, no spend.

RUN: ``PYTHONPATH=src uv run python scripts/run_real_ablation.py``
(Expect MANY HOURS / overnight at the converged ``advi_iters=30000``: 2 ADVI fits per cutoff
for the paired RPS eval + 2 walk-forward arms. See the FIT_KWARGS note on the wall-clock /
why 1500 iters under-converged. Currently a DEFERRED follow-up — rest_days stays enabled:[].)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

from wcmodel.backtest.ablation import run_ablation
from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.config import load_config
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.results import load_results
from wcmodel.data.store import BitemporalStore

CACHE_DIR = Path("data/cache")

# Walk-forward cutoff schedule: semi-annual decision dates across the recent feature
# window. Each consecutive pair drives a half-open OOS eval window; the last runs to
# the max played match date + 1 day. Spans 2022-06 .. 2025-12 (real fixtures in every
# window — ~1000 played internationals/year over this span).
CUTOFFS = [
    "2022-06-01", "2022-12-01",
    "2023-06-01", "2023-12-01",
    "2024-06-01", "2024-12-01",
    "2025-06-01", "2025-12-01",
]

# Sampler knobs for the per-cutoff fits. ADVI iters set to the config DEFAULT (30000):
# a first run at advi_iters=1500 DIVERGED on the larger later-cutoff windows (mean-field
# ADVI is stochastic; under-converged it let beta_rest_days run away -> exp(rate) overflow
# -> a degenerate scoreline grid). That was under-converged ADVI, NOT a rest_days
# instability (see ASSUMPTIONS.md "rest_days ablation verdict (M-T8)"). The ablation is now
# crash-safe regardless (an unstable candidate REJECTS, never crashes/fabricates), but a
# MEANINGFUL verdict needs converged fits. WALL-CLOCK CAVEAT: 30000 iters is ~20x the 1500
# run (which already took ~1h40m for the 5-cutoff/2-arm schedule) -> expect MANY HOURS /
# overnight for the full 8-cutoff schedule. Seed fixed for reproducibility.
FIT_KWARGS = {"backend": "advi", "draws": 200, "advi_iters": 30000, "seed": 0}


def build_real_store(store_root: Path) -> BitemporalStore:
    """Assemble the real martj42 store via the canonical load path (same as the snapshot
    builder). Fetches+caches the pinned-commit results CSV on first run, then writes it
    POINT_IN_TIME keyed on match_id so the bitemporal cutoff gate applies."""
    store = BitemporalStore(root=store_root)
    load_results(store, cache_dir=CACHE_DIR)
    return store


def synthetic_clv_feed():
    """A SMALL clearly-NON-REAL synthetic odds feed for the CLV secondary guard only.

    Two labelled-synthetic 1X2 snapshots over real store fixtures (so the walkforward CLV
    arm has something to settle); this taints the report is_synthetic=True by design — CLV
    is NOT the gate in this run. Returns (odds_samples, results_for_settle, matches)."""
    md1 = synthetic_odds_sample(
        home="Brazil", away="Argentina", commence="2024-06-25T19:00:00Z",
        entry=(2.60, 3.30, 2.80), close=(2.40, 3.35, 3.00),
        bookmaker="pinnacle", seed=0,
    )
    md2 = synthetic_odds_sample(
        home="France", away="Germany", commence="2024-06-20T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
        bookmaker="pinnacle", seed=0,
    )
    rfs = pd.DataFrame([
        {"home_team": "Brazil", "away_team": "Argentina",
         "date": pd.Timestamp("2024-06-25"), "home_score": 2, "away_score": 1,
         "tournament": "Friendly"},
        {"home_team": "France", "away_team": "Germany",
         "date": pd.Timestamp("2024-06-20"), "home_score": 1, "away_score": 0,
         "tournament": "Friendly"},
    ])
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-20", "2024-06-25"])})
    return [md1, md2], rfs, matches


def main() -> int:
    cfg = load_config()
    store_root = Path(tempfile.mkdtemp(prefix="wc-real-ablation-store-"))
    print(f"[store] assembling real martj42 store at {store_root} ...", flush=True)
    store = build_real_store(store_root)

    res = store.read("results", cutoff="2026-06-07T00:00:00Z").copy()
    res["date"] = pd.to_datetime(res["date"])
    played = valid_played_results(res)
    print(f"[store] {len(played)} valid-played matches; "
          f"date range {played['date'].min().date()} .. {played['date'].max().date()}",
          flush=True)

    odds_samples, rfs, matches = synthetic_clv_feed()

    print(f"[ablation] running rest_days RPS ablation over {len(CUTOFFS)} cutoffs:\n"
          f"           {CUTOFFS}\n"
          f"           fit_kwargs={FIT_KWARGS}\n"
          f"           (PRIMARY=paired OOS RPS; CLV on synthetic harness, NOT the gate)",
          flush=True)

    rep = run_ablation(
        store, odds_samples, candidates=["rest_days"], cutoffs=CUTOFFS,
        config=cfg, seed=0,
        results_for_settle=rfs, matches=matches, fit_kwargs=FIT_KWARGS,
        cache_dir=str(CACHE_DIR),
    )

    r = rep["rest_days"]
    meta = rep["_meta"]
    print("\n=========== REAL rest_days ABLATION RESULT ===========")
    print(f"  n_eval (paired OOS fixtures): {r['n_eval']}")
    print(f"  baseline_rps : {r['baseline_rps']:.6f}")
    print(f"  candidate_rps: {r['candidate_rps']:.6f}")
    print(f"  mean_d (delta = base - cand, +=cand better): {r['mean_d']:.6f}")
    print(f"  paired_p (sign-flip permutation): {r['paired_p']}")
    print(f"  paired_p_adj (Bonferroni): {r['paired_p_adj']}")
    print(f"  null_p (sanity field, NOT gate): {r['null_p']}")
    print(f"  baseline_clv (synthetic, NOT gate): {r['baseline_clv']}")
    print(f"  candidate_clv (synthetic, NOT gate): {r['candidate_clv']}")
    print(f"  VERDICT: {r['verdict'].upper()}")
    print(f"  is_synthetic (CLV harness taint): {meta['is_synthetic']}")
    print(f"  accepted set: {meta['accepted']}")
    print("======================================================\n")

    out = Path("reports/ablation_rest_days_real.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, default=str))
    print(f"[done] full report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
