"""Team-level features.build panel -> match-level design rows + team index.

features.build emits TWO rows per match (home + away perspective). The scoreline
model is match-level (home/away goals jointly), so we collapse to one row per
match_id off the is_home==True row (which already carries home_team/away_team/
home_score/away_score/neutral/match_type/date/decay_weight) and graft the
per-team provisional flags from both perspectives. No score is imputed — the
Phase-1 played filter guarantees integer goals.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

def to_match_panel(features_df: pd.DataFrame) -> pd.DataFrame:
    if features_df.empty:
        return pd.DataFrame(columns=[
            "match_id", "date", "home_team", "away_team", "home_goals",
            "away_goals", "neutral", "match_type", "weight",
            "home_provisional", "away_provisional"])
    home = features_df[features_df["is_home"]].copy()
    base = home[["match_id", "date", "home_team", "away_team", "home_score",
                 "away_score", "neutral", "match_type", "decay_weight"]].rename(
        columns={"home_score": "home_goals", "away_score": "away_goals",
                 "decay_weight": "weight"})
    prov = features_df[["match_id", "team", "is_home", "provisional"]]
    hp = prov[prov["is_home"]].set_index("match_id")["provisional"].rename("home_provisional")
    ap = prov[~prov["is_home"]].set_index("match_id")["provisional"].rename("away_provisional")
    out = base.merge(hp, on="match_id").merge(ap, on="match_id")
    out["home_goals"] = out["home_goals"].astype(int)
    out["away_goals"] = out["away_goals"].astype(int)
    if len(out) != home["match_id"].nunique():
        raise ValueError(
            f"to_match_panel row count {len(out)} != distinct home matches "
            f"{home['match_id'].nunique()} — malformed upstream panel "
            "(a match missing its away row, or duplicate is_home rows)")
    return out.reset_index(drop=True)


@dataclass(frozen=True)
class DesignData:
    """Team-indexed numpy arrays for the scoreline likelihood.

    teams is the sorted unique team universe; home_idx/away_idx index into it.
    All arrays are length-n (one entry per match) and aligned to match_panel row
    order, so home_idx[i]/away_idx[i] et al. all describe match_panel row i.

    cov / cov_mask are OPTIONAL pre-match covariates (T0 scaffold): name ->
    standardized per-row value (already masked to 0 where absent), and name ->
    1.0-where-observed mask. Both default empty, so the model is byte-identical
    to today's baseline when model.covariates.enabled == [] (no covariate terms).
    They are the ONLY defaulted fields — every other field stays required, so a
    mis-shaped DesignData can't be built by accident; build_design supplies them
    all by keyword.
    """
    home_idx: np.ndarray
    away_idx: np.ndarray
    home_goals: np.ndarray
    away_goals: np.ndarray
    neutral: np.ndarray
    n_teams: int
    teams: list[str]
    weight: np.ndarray
    home_provisional: np.ndarray
    away_provisional: np.ndarray
    cov: dict[str, np.ndarray] = field(default_factory=dict)        # name -> standardized per-row value (already masked to 0 where absent)
    cov_mask: dict[str, np.ndarray] = field(default_factory=dict)   # name -> 1.0 where observed, else 0.0

def build_design(match_panel: pd.DataFrame) -> DesignData:
    teams = sorted(set(match_panel["home_team"]) | set(match_panel["away_team"]))
    idx = {t: i for i, t in enumerate(teams)}
    return DesignData(
        teams=teams, n_teams=len(teams),
        home_idx=match_panel["home_team"].map(idx).to_numpy(dtype=np.int64),
        away_idx=match_panel["away_team"].map(idx).to_numpy(dtype=np.int64),
        home_goals=match_panel["home_goals"].to_numpy(dtype=np.int64),
        away_goals=match_panel["away_goals"].to_numpy(dtype=np.int64),
        neutral=match_panel["neutral"].to_numpy(dtype=bool),
        weight=match_panel["weight"].to_numpy(dtype=float),
        home_provisional=match_panel["home_provisional"].to_numpy(dtype=bool),
        away_provisional=match_panel["away_provisional"].to_numpy(dtype=bool),
    )
