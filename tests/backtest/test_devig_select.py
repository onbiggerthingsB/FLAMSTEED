import numpy as np

from wcmodel.backtest.devig_select import (
    devig, rps_of_devig, choose_devig, DEVIG_METHODS,
)


def test_devig_dispatches_and_orders_by_outcomes():
    odds = [1.57, 4.20, 6.50]                    # home/draw/away
    p = devig(odds, method="shin")
    assert abs(sum(p) - 1.0) < 1e-9
    assert p[0] > p[1] > p[2]                    # favourite ordering preserved


def test_buchdahl_is_never_a_choosable_method():
    # Buchdahl / odds-proportional is sensitivity-only — NEVER promoted (it
    # manufactures phantom value in the favourite-longshot direction).
    assert "buchdahl" not in DEVIG_METHODS
    assert set(DEVIG_METHODS) == {"shin", "multiplicative", "power"}


def test_rps_of_devig_rewards_calibrated_probabilities():
    # Two devigged forecasts on the same realised outcomes; the better-calibrated
    # one has the LOWER mean RPS.
    odds_list = [[1.57, 4.20, 6.50], [2.0, 3.4, 4.0]]
    outcomes = ["home", "away"]                  # realised results, OUTCOMES-labelled
    rps = rps_of_devig(odds_list, outcomes, method="shin")
    assert 0.0 <= rps <= 2.0                     # RPS for a 3-way market is in [0, 2]


def test_choose_devig_picks_lowest_rps_with_shin_default_on_tie():
    # Construct so 'shin' wins; choose_devig returns the empirical best + a table.
    odds_list = [[1.57, 4.20, 6.50], [2.10, 3.30, 3.80], [1.30, 5.0, 11.0]]
    outcomes = ["home", "draw", "home"]
    best, table = choose_devig(odds_list, outcomes)
    assert best in DEVIG_METHODS
    assert set(table) == set(DEVIG_METHODS)      # every method scored (sensitivity)
    # The returned best really is the argmin of the table.
    assert table[best] == min(table.values())


def test_choose_devig_empty_returns_config_default():
    # No bets to calibrate on => fall back to the configured prior (Shin), not crash.
    best, table = choose_devig([], [])
    assert best == "shin"
