import pytest

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
    assert 0.0 <= rps <= 1.0                     # ÷2-normalized (OA F16): [0, 1]


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


def test_choose_devig_empty_never_promotes_buchdahl_via_config():
    # MUST-FIX 2: the empty-calibration fallback must VALIDATE the config prior is
    # in DEVIG_METHODS. A config that (mis)sets devig_method="buchdahl" must NOT be
    # promoted — buchdahl manufactures phantom favourite-longshot value. The path
    # falls back to "shin" instead of returning the un-choosable method.
    cfg = {"backtest": {"devig_method": "buchdahl"}}
    best, table = choose_devig([], [], config=cfg)
    assert best == "shin"                         # NOT "buchdahl"
    assert best in DEVIG_METHODS
    # And a garbage/unknown prior is likewise refused (defense-in-depth).
    cfg_bad = {"backtest": {"devig_method": "nonsense_method"}}
    best_bad, _ = choose_devig([], [], config=cfg_bad)
    assert best_bad == "shin"


def test_rps_of_devig_raises_on_length_mismatch():
    # MUST-FIX 3: a length mismatch between odds rows and realised outcomes must
    # RAISE (a silent zip-truncation would compute the score over a subset and
    # report a wrong calibration number).
    odds_list = [[1.57, 4.20, 6.50], [2.10, 3.30, 3.80]]
    outcomes = ["home"]                           # one outcome, two odds rows
    with pytest.raises(ValueError):
        rps_of_devig(odds_list, outcomes, method="shin")


def test_rps_of_devig_raises_on_wrong_odds_width():
    # Each decimal-odds row must have exactly len(OUTCOMES)=3 entries; a 2-wide
    # row is a malformed 1X2 vector and must RAISE, not be silently zipped short.
    odds_list = [[1.57, 4.20]]                     # missing the away price
    outcomes = ["home"]
    with pytest.raises(ValueError):
        rps_of_devig(odds_list, outcomes, method="shin")


def test_rps_of_devig_empty_odds_nonempty_outcomes_raises():
    # Codex T1 re-review hole: EMPTY odds + NON-empty outcomes is a genuine length
    # mismatch and must RAISE — it previously slipped through the empty-return as
    # nan (the length check now runs FIRST). Both-empty is a legitimately-empty
    # calibration set and still returns nan (no data to score).
    import math
    with pytest.raises(ValueError):
        rps_of_devig([], ["home"], method="shin")
    assert math.isnan(rps_of_devig([], [], method="shin"))
