import numpy as np

from wcmodel.backtest.clv import clv_pct, beat_close, clv_summary


def test_clv_pct_is_entry_over_close_minus_one():
    # You bet at 2.10 and the close drifts to 2.00 -> you beat the close by +5%.
    assert abs(clv_pct(entry_odds=2.10, close_odds=2.00) - 0.05) < 1e-12
    # You bet at 1.90 and the close is 2.00 -> negative CLV.
    assert clv_pct(entry_odds=1.90, close_odds=2.00) < 0


def test_beat_close_is_strict_positive_clv():
    assert beat_close(entry_odds=2.10, close_odds=2.00) is True
    assert beat_close(entry_odds=2.00, close_odds=2.00) is False   # equal is NOT a beat
    assert beat_close(entry_odds=1.90, close_odds=2.00) is False


def test_clv_summary_aggregates_rate_and_mean():
    bets = [
        {"entry_odds": 2.10, "close_odds": 2.00},   # +5%, beat
        {"entry_odds": 1.90, "close_odds": 2.00},   # -5%, not
        {"entry_odds": 3.10, "close_odds": 3.00},   # +3.33%, beat
    ]
    s = clv_summary(bets)
    assert s["n_bets"] == 3
    assert abs(s["beat_close_rate"] - 2 / 3) < 1e-12
    assert abs(s["avg_clv"] - np.mean([0.05, -0.05, 0.10 / 3])) < 1e-12


def test_clv_summary_empty_is_zero_count_nan_metrics():
    s = clv_summary([])
    assert s["n_bets"] == 0
    assert np.isnan(s["beat_close_rate"]) and np.isnan(s["avg_clv"])
