from wcmodel.data.sources.derived import rest_days, haversine_km
import pandas as pd

def test_rest_days_per_team_from_schedule():
    sched = pd.DataFrame([
        {"team":"A","date":"2024-06-01"},{"team":"A","date":"2024-06-07"}])
    r = rest_days(sched)
    assert r.iloc[1]["rest_days"] == 6

def test_haversine_known_distance():
    d = haversine_km(51.5074,-0.1278, 48.8566, 2.3522)   # London -> Paris ~343 km
    assert 330 < d < 355

def test_first_match_has_na_rest_days():
    sched = pd.DataFrame([{"team":"A","date":"2024-06-01"}])
    r = rest_days(sched)
    assert pd.isna(r.iloc[0]["rest_days"])    # no prior fixture
