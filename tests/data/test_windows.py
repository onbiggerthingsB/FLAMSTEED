from wcmodel.data.windows import feature_window, backtest_window
import pandas as pd


def test_feature_window_is_bounded(matches_df):
    fw = feature_window(matches_df, cutoff="2025-01-01", years=4)
    assert (pd.to_datetime(fw["date"]) >= pd.Timestamp("2021-01-01")).all()
    assert (pd.to_datetime(fw["date"]) < pd.Timestamp("2025-01-01")).all()


def test_backtest_window_is_not_cropped_to_feature_years(matches_df):
    bw = backtest_window(matches_df, odds_start="2020-06-06")
    assert pd.to_datetime(bw["date"]).min() <= pd.Timestamp("2021-01-01")   # keeps pre-feature-window history
    assert (pd.to_datetime(bw["date"]) >= pd.Timestamp("2020-06-06")).all()
