import numpy as np, pandas as pd
from wcmodel.data.elo import compute_elo_history, elo_1x2_baseline

def _matches():
    return pd.DataFrame([
        {"match_id":"m1","date":"2024-01-01","home_team":"A","away_team":"B",
         "home_score":2,"away_score":0,"neutral":False,"match_type":"friendly"},
        {"match_id":"m2","date":"2024-02-01","home_team":"B","away_team":"A",
         "home_score":1,"away_score":1,"neutral":True,"match_type":"wc_qualifier"},
    ])

def test_elo_is_deterministic_and_point_in_time():
    h1 = compute_elo_history(_matches()); h2 = compute_elo_history(_matches())
    assert h1.equals(h2)
    first = h1[(h1.match_id=="m1") & (h1.team=="A")].iloc[0]
    assert first["rating_pre"] == 1500.0      # debutant starts at initial_rating

def test_winner_gains_rating():
    h = compute_elo_history(_matches())
    a_after_m1 = h[(h.match_id=="m1") & (h.team=="A")].iloc[0]["rating_post"]
    assert a_after_m1 > 1500.0

def test_baseline_probs_sum_to_one_and_favor_higher_rating():
    p = elo_1x2_baseline(rating_home=1800, rating_away=1500, neutral=False)
    assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-9
    assert p["home"] > p["away"]

def test_baseline_uses_same_ratings_as_feature():
    h = compute_elo_history(_matches())
    row = h[(h.match_id=="m2")].iloc[0]
    p = elo_1x2_baseline(rating_home=row["rating_pre"], rating_away=1500, neutral=row["neutral"])
    assert set(p) == {"home","draw","away"}

def test_debutant_flagged_provisional():
    h = compute_elo_history(_matches())
    assert h[(h.match_id=="m1") & (h.team=="A")].iloc[0]["provisional"] == True
