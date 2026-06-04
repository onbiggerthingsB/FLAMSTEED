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


def test_composite_key_collision_both_rows_survive_with_distinct_ids():
    """STANDING guard for the 1974-double-header case (systematic, not one-off).

    Two REAL rows can share the full composite key (date|home|away|city) yet be
    distinct matches (e.g. Tahiti vs New Caledonia, 1974-02-17, Papeete — two
    matches, different scores). The disambiguation must REWRITE the match_id (it
    must NOT drop a row): both rows survive, the count is preserved, and the
    final match_id is unique.
    """
    raw = pd.DataFrame([
        # date, home, away, hs, as, tournament, neutral, city, country
        ("1974-02-17", "Tahiti", "New Caledonia", 4, 2, "Friendly", False,
         "Papeete", "Tahiti"),
        ("1974-02-17", "Tahiti", "New Caledonia", 1, 0, "Friendly", False,
         "Papeete", "Tahiti"),  # SAME composite key, DIFFERENT score
    ], columns=["date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "neutral", "city", "country"])

    out = normalize_results(raw)

    # Disambiguation rewrites match_id — it must NOT drop a row (count preserved).
    assert len(out) == len(raw) == 2
    # Both genuine matches survive with DISTINCT ids, and the id is unique.
    assert out["match_id"].nunique() == 2
    assert out["match_id"].is_unique
