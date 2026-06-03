from wcmodel.data.sources.results import normalize_results
import pandas as pd


def test_normalize_sets_valid_and_observed_to_match_date():
    raw = pd.read_csv("fixtures/results_sample.csv")
    out = normalize_results(raw)
    assert (out["valid_as_of"] == out["observed_at"]).all()
    assert {"match_id", "date", "home_team", "away_team", "home_score", "away_score",
            "tournament", "neutral"} <= set(out.columns)


def test_match_id_is_stable_hash():
    raw = pd.read_csv("fixtures/results_sample.csv")
    a = normalize_results(raw)["match_id"]
    b = normalize_results(raw)["match_id"]
    assert a.equals(b) and a.is_unique
