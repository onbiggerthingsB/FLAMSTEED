"""Track-record artifact: realized CLV (beat-close + avg CLV%), ROI, and RPS vs the
market & Elo baselines (Direct from the backtest), plus a DERIVED reliability diagram
(binned forecast-vs-outcome). Paper/synthetic in v1."""
from __future__ import annotations

import numpy as np

from wcmodel.backtest.clv import clv_summary
from wcmodel.dashboard.schema import no_impute


def reliability_bins(preds: list[dict], *, n_bins: int = 10) -> list[dict]:
    """Bin (forecast p, hit 0/1) records into a reliability diagram: per bin, the mean
    forecast vs the empirical hit rate. Derived from the backtest's per-bet records."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for lo, hi in zip(edges, edges[1:]):
        members = [r for r in preds if lo <= r["p"] < hi or (hi == 1.0 and r["p"] == 1.0)]
        n = len(members)
        out.append({
            "bin_lo": float(lo), "bin_hi": float(hi), "n": n,
            "forecast_mean": float(np.mean([r["p"] for r in members])) if n else None,
            "empirical": float(np.mean([r["hit"] for r in members])) if n else None,
        })
    return out


def track_record(*, bets: list[dict], preds: list[dict]) -> dict:
    """CLV-first track record + RPS vs baselines + reliability bins. Paper/synthetic (v1).

    FIX E: a preds-only track (forecasts made, but no bet cleared the edge threshold) is
    LEGITIMATE — GAP the CLV block (None metrics, n_bets 0) rather than ``clv_summary([])``'s
    NaN, which ``gate_track`` would raise on. rps/reliability stay None-safe when preds is empty.
    """
    summary = (clv_summary(bets) if bets
               else {"n_bets": 0, "beat_close_rate": None, "avg_clv": None})
    rps_model = [r["rps_model"] for r in preds if "rps_model" in r]
    rps_market = [r["rps_market"] for r in preds if "rps_market" in r]
    rps_elo = [r["rps_elo"] for r in preds if "rps_elo" in r]
    return {
        **summary,
        "rps": {
            "model": no_impute(np.mean(rps_model)) if rps_model else None,
            "market": no_impute(np.mean(rps_market)) if rps_market else None,
            "elo": no_impute(np.mean(rps_elo)) if rps_elo else None,
        },
        "reliability": reliability_bins(preds),
        "is_synthetic": True,
    }
