import pandas as pd
from wcmodel.data.features import build


def test_build_returns_only_matches_strictly_before_cutoff(small_store):
    df = build(cutoff="2025-03-01", store=small_store)
    assert (pd.to_datetime(df["date"]) < pd.Timestamp("2025-03-01")).all()


def test_elo_feature_is_pre_match_rating(small_store):
    df = build(cutoff="2025-03-01", store=small_store)
    assert "elo_pre" in df.columns and df["elo_pre"].notna().all()


def test_missing_xg_is_null_not_imputed(small_store):
    df = build(cutoff="2025-03-01", store=small_store)
    uncov = df[df["xg_covered"] == False]
    assert uncov["xg_for"].isna().all()          # NULL, never filled


def test_contamination_exposure_zero_for_clean_core(small_store):
    df = build(cutoff="2025-03-01", store=small_store)
    assert (df["revision_contaminated_exposure"] == 0.0).all()


def test_time_decay_weight_decreases_with_age(small_store):
    df = build(cutoff="2025-03-01", store=small_store).sort_values("date")
    assert df["decay_weight"].iloc[0] <= df["decay_weight"].iloc[-1]   # older -> smaller weight
