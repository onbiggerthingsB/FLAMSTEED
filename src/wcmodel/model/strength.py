"""Per-team Elo strength as a leakage-safe, z-scored prior anchor for att/def.

`elo_z[i]` is team `teams[i]`'s most-recent pre-match Elo (`elo_pre`, point-in-time
< cutoff via the features panel), z-scored across `teams`. A team absent from the
panel (no pre-cutoff match) -> 0 (no-info, = today's shrink-to-mean behavior).
Elo is computed from RESULTS only (market-prior-free) and strictly before the
cutoff (leakage-safe) -- this module adds NO new data source.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

def team_elo_z(feats: pd.DataFrame, teams: list[str]) -> np.ndarray:
    latest = (feats.sort_values("date").groupby("team")["elo_pre"].last())
    r = np.array([latest.get(t, np.nan) for t in teams], dtype=float)
    sd = np.nanstd(r)
    if not np.isfinite(sd) or sd == 0.0:
        return np.zeros(len(teams), dtype=float)
    z = (r - np.nanmean(r)) / sd
    z[np.isnan(z)] = 0.0
    return z
