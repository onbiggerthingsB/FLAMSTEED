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


def test_collision_disambiguation_is_input_order_independent():
    """FIX 3 regression: full distinguishing tuple -> order-independent match_id.

    Two rows sharing the FULL composite key (date|home|away|city) AND tying on
    (home_score, away_score) but differing in `tournament` previously got an
    occurrence index ordered by score ALONE — so the tie was broken by input
    row order, making the base-hash (occ==0 vs occ==1) assignment depend on
    which row came first. Extending the deterministic sort key to the full
    distinguishing tuple (..., tournament, neutral) makes the SET of emitted
    match_ids identical regardless of feed order.
    """
    rows = [
        # date, home, away, hs, as, tournament, neutral, city, country
        ("2024-06-19", "Brazil", "Argentina", 1, 1, "Friendly", False,
         "London", "England"),
        ("2024-06-19", "Brazil", "Argentina", 1, 1, "FIFA World Cup", False,
         "London", "England"),  # SAME key + SAME score, DIFFERENT tournament
    ]
    cols = ["date", "home_team", "away_team", "home_score", "away_score",
            "tournament", "neutral", "city", "country"]

    forward = normalize_results(pd.DataFrame(rows, columns=cols))
    reversed_ = normalize_results(pd.DataFrame(rows[::-1], columns=cols))

    # Both orders keep two distinct, unique ids...
    assert forward["match_id"].is_unique and reversed_["match_id"].is_unique
    assert forward["match_id"].nunique() == reversed_["match_id"].nunique() == 2
    # ...and crucially the SAME SET of ids regardless of input order (the id for a
    # given (tournament) row is stable, not assigned by feed position).
    assert set(forward["match_id"]) == set(reversed_["match_id"])
    # Tighter: the id attached to each tournament is identical across orders.
    fwd_by_tourn = dict(zip(forward["tournament"], forward["match_id"]))
    rev_by_tourn = dict(zip(reversed_["tournament"], reversed_["match_id"]))
    assert fwd_by_tourn == rev_by_tourn
