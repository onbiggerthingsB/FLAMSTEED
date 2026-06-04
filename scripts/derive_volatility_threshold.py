"""One-off empirical derivation of the Elo `provisional_volatility_threshold`.

Fetches the REAL martj42 international-results history (CC0, via the existing
`sources/results` adapter + content-addressed cache), computes the point-in-time
Elo history (`compute_elo_history`), and reports the empirical distribution of
the *rolling population stddev of the last `volatility_window` rating deltas* —
the exact quantity the `provisional` volatility branch thresholds on.

This is analysis-only: it does NOT modify config. Run with `PYTHONPATH=src`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.elo import compute_elo_history
from wcmodel.data.sources.results import fetch_results, normalize_results

CACHE_DIR = "data/cache"


def main() -> None:
    cfg = load_config()["elo"]
    window = int(cfg["volatility_window"])

    raw = fetch_results(CACHE_DIR)
    norm = normalize_results(raw)
    # Map martj42 raw `tournament` -> the Elo K `match_type` (same wiring as
    # features.build), so K is realistic per competition instead of all-"other".
    norm = norm.copy()
    norm["match_type"] = norm["tournament"].map(tiers.match_type)
    # Drop UNPLAYED fixtures (NaN scores) — the live martj42 feed carries
    # scheduled-but-not-yet-played WC-2026 rows with NaN home/away_score. They
    # have no result, hence no rating delta; including them would inject NaN
    # ratings that poison the whole downstream chain. The Elo history (and the
    # volatility metric) is defined only over PLAYED matches.
    n_before = len(norm)
    norm = norm.dropna(subset=["home_score", "away_score"]).copy()
    n_unplayed = n_before - len(norm)
    matches = norm[["match_id", "date", "home_team", "away_team",
                    "home_score", "away_score", "neutral", "match_type"]]
    print(f"dropped {n_unplayed} unplayed (NaN-score) fixtures")
    print(f"martj42 rows: {len(matches):,}  "
          f"date range: {matches['date'].min().date()} .. "
          f"{matches['date'].max().date()}")
    mt = matches["match_type"].value_counts()
    print("match_type counts:")
    for k, v in mt.items():
        print(f"  {k:28s} {v:,}")

    hist = compute_elo_history(matches)
    hist = hist.copy()
    hist["delta"] = hist["rating_post"] - hist["rating_pre"]

    # Replicate the EXACT causal metric the flag uses: at each team-match, the
    # population stddev of the team's last `window` PRIOR deltas (strictly before
    # the current match). `compute_elo_history` returns rows in chronological
    # match order (stable mergesort on date), and appends two rows per match in
    # that order, so a per-team cumulative scan over the returned frame reproduces
    # the same ordering the flag's internal `deltas[team]` list saw.
    vols: list[float] = []  # the metric value AT each team-match (>=1 prior delta)
    by_team: dict[str, list[float]] = {}
    flagged = 0
    total_states = 0  # team-matches where the volatility branch is evaluable (has priors)
    for team, d in zip(hist["team"].to_numpy(), hist["delta"].to_numpy()):
        prior = by_team.get(team)
        if prior:  # at least one PRIOR delta -> metric is defined
            v = float(np.std(prior[-window:]))
            vols.append(v)
            total_states += 1
        by_team.setdefault(team, []).append(float(d))

    arr = np.array(vols)
    print(f"\nEvaluable team-match volatility states (>=1 prior delta): {len(arr):,}")
    pcts = {
        "median(p50)": 50, "p75": 75, "p85": 85, "p90": 90,
        "p95": 95, "p99": 99,
    }
    print("\nEmpirical distribution of rolling stddev-of-last-%d-deltas "
          "(rating pts):" % window)
    rows = []
    for label, p in pcts.items():
        val = float(np.percentile(arr, p))
        rows.append((label, p, val))
        print(f"  {label:12s} = {val:7.3f}")
    print(f"  {'max':12s} = {float(arr.max()):7.3f}")
    print(f"  {'mean':12s} = {float(arr.mean()):7.3f}")

    # Fraction of evaluable states flagged at a few candidate thresholds.
    print("\nFraction of evaluable team-match states flagged provisional "
          "(volatility branch) at candidate thresholds T:")
    for T in [20, 25, 30, 35, 40, 45, 50, 60]:
        frac = float((arr > T).mean())
        print(f"  T={T:>3} -> {frac*100:6.2f}%  flagged")

    # Also report the metric's own ceiling: a fully-saturated window of ±max
    # single-match deltas would have stddev ~ that delta magnitude. Show the
    # observed top of the distribution to anchor "tail".
    p975 = float(np.percentile(arr, 97.5))
    print(f"\np97.5 = {p975:.3f}  (extra anchor for the tail)")


if __name__ == "__main__":
    main()
