import pandas as pd
from wcmodel.data import features
from wcmodel.model.panel import to_match_panel

def test_two_rows_per_match_collapse_to_one(small_store):
    feats = features.build("2024-06-01", small_store)
    mp = to_match_panel(feats)
    assert mp["match_id"].is_unique
    assert len(mp) == feats["match_id"].nunique()
    cols = {"match_id", "date", "home_team", "away_team", "home_goals",
            "away_goals", "neutral", "match_type", "weight",
            "home_provisional", "away_provisional"}
    assert cols <= set(mp.columns)
    assert mp["home_goals"].notna().all() and (mp["home_goals"] % 1 == 0).all()

def test_weight_is_home_row_decay_weight(small_store):
    feats = features.build("2024-06-01", small_store)
    mp = to_match_panel(feats)
    home_rows = feats[feats["is_home"]].set_index("match_id")["decay_weight"]
    merged = mp.set_index("match_id")["weight"]
    assert (merged.sort_index() == home_rows.sort_index()).all()
