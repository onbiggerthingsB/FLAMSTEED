"""Team-level features.build panel -> match-level design rows + team index.

features.build emits TWO rows per match (home + away perspective). The scoreline
model is match-level (home/away goals jointly), so we collapse to one row per
match_id off the is_home==True row (which already carries home_team/away_team/
home_score/away_score/neutral/match_type/date/decay_weight) and graft the
per-team provisional flags from both perspectives. No score is imputed — the
Phase-1 played filter guarantees integer goals.
"""
from __future__ import annotations
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
    return out.reset_index(drop=True)
