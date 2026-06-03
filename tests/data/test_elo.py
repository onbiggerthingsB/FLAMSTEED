import numpy as np, pandas as pd
import pytest
from wcmodel.data.elo import compute_elo_history, elo_1x2_baseline, _mov_index

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

def test_rating_pre_chains_forward_from_prior_post():
    h = compute_elo_history(_matches())
    a_m1_post = h[(h.match_id=="m1") & (h.team=="A")].iloc[0]["rating_post"]
    a_m2_pre  = h[(h.match_id=="m2") & (h.team=="A")].iloc[0]["rating_pre"]
    assert a_m2_pre == a_m1_post   # no same-match leakage

def test_m1_exact_ratings():
    h = compute_elo_history(_matches())
    a = h[(h.match_id=="m1") & (h.team=="A")].iloc[0]["rating_post"]
    b = h[(h.match_id=="m1") & (h.team=="B")].iloc[0]["rating_post"]
    assert a == pytest.approx(1508.6384400047307)   # 2-0 friendly, non-neutral (ha=100), K=16, G=1.5
    assert b == pytest.approx(1491.3615599952693)

def test_mov_index_scheme():
    assert _mov_index(1) == 1.0
    assert _mov_index(2) == 1.5
    assert _mov_index(5) == 2.0   # (11+5)/8

def test_baseline_home_advantage_and_neutral_symmetry():
    assert elo_1x2_baseline(1500, 1500, neutral=False)["home"] > 0.5
    pn = elo_1x2_baseline(1500, 1500, neutral=True)
    assert pn["home"] == pytest.approx(pn["away"])   # symmetric when neutral + equal ratings

def test_baseline_draw_peaks_at_even_match():
    assert elo_1x2_baseline(1500, 1500, neutral=True)["draw"] == pytest.approx(0.28)
    assert elo_1x2_baseline(1900, 1500, neutral=True)["draw"] < 0.28
