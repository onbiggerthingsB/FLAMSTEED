import numpy as np

from wcmodel.backtest.staking import (
    kelly_fraction_bet, uncertainty_shrink, stake_fraction, settle_bet,
    bankroll_path, roi_metrics, bootstrap_ci,
)


def test_kelly_fraction_matches_closed_form():
    # Full-Kelly for a back bet: f* = (b*p - q) / b, b = decimal_odds - 1.
    # odds 2.5 (b=1.5), p=0.5 -> f* = (1.5*0.5 - 0.5)/1.5 = 0.1667
    f = kelly_fraction_bet(prob=0.5, decimal_odds=2.5)
    assert abs(f - (1.5 * 0.5 - 0.5) / 1.5) < 1e-12


def test_kelly_is_zero_when_no_positive_expectation():
    # p below the breakeven 1/odds -> Kelly <= 0 -> clamp to 0 (no bet).
    assert kelly_fraction_bet(prob=0.30, decimal_odds=2.5) == 0.0


def test_uncertainty_shrink_scales_down_with_se():
    # Higher posterior SE on the price => more shrink (smaller multiplier in (0,1]).
    s_low = uncertainty_shrink(se=0.0)
    s_high = uncertainty_shrink(se=0.10)
    assert s_low == 1.0                          # no uncertainty -> no shrink
    assert 0.0 < s_high < 1.0 and s_high < s_low


def test_stake_fraction_applies_quarter_kelly_and_shrink_and_threshold():
    # edge below threshold => no stake.
    assert stake_fraction(prob=0.55, decimal_odds=2.5, edge=0.01, se=0.0,
                          kelly_fraction=0.25, edge_threshold=0.02) == 0.0
    # edge above threshold => quarter-Kelly * shrink.
    full = kelly_fraction_bet(prob=0.55, decimal_odds=2.5)
    s = stake_fraction(prob=0.55, decimal_odds=2.5, edge=0.05, se=0.0,
                       kelly_fraction=0.25, edge_threshold=0.02)
    assert abs(s - 0.25 * full * 1.0) < 1e-12


def test_settle_bet_pinnacle_has_no_commission():
    # Win at 2.5 on a 1.0-unit stake => profit = stake*(odds-1) = 1.5, no commission.
    assert abs(settle_bet(stake=1.0, decimal_odds=2.5, won=True, venue="pinnacle",
                          commission={"pinnacle": 0.0, "betfair": 0.02}) - 1.5) < 1e-12
    # Loss => -stake.
    assert settle_bet(stake=1.0, decimal_odds=2.5, won=False, venue="pinnacle",
                      commission={"pinnacle": 0.0, "betfair": 0.02}) == -1.0


def test_settle_bet_betfair_takes_commission_on_net_winnings():
    # Win at 2.5: gross profit 1.5, Betfair takes 2% of NET winnings => 1.5*0.98 = 1.47.
    assert abs(settle_bet(stake=1.0, decimal_odds=2.5, won=True, venue="betfair",
                          commission={"pinnacle": 0.0, "betfair": 0.02}) - 1.47) < 1e-12
    # Loss => commission does not apply to losses.
    assert settle_bet(stake=1.0, decimal_odds=2.5, won=False, venue="betfair",
                      commission={"pinnacle": 0.0, "betfair": 0.02}) == -1.0


def test_bankroll_path_and_roi_metrics():
    # Two bets: +1.5 then -1.0 on 1.0-unit stakes, starting bankroll 10.
    pnls = [1.5, -1.0]
    stakes = [1.0, 1.0]
    path = bankroll_path(pnls, start=10.0)
    assert path == [10.0, 11.5, 10.5]
    m = roi_metrics(pnls=pnls, stakes=stakes, start=10.0)
    assert abs(m["roi"] - (0.5 / 2.0)) < 1e-12          # net 0.5 over 2.0 turnover
    assert abs(m["turnover"] - 2.0) < 1e-12
    assert abs(m["hit_rate"] - 0.5) < 1e-12
    # max drawdown: peak 11.5 -> trough 10.5 => 1.0 absolute, ~0.087 fractional.
    assert abs(m["max_drawdown"] - 1.0) < 1e-12
    assert abs(m["max_drawdown_frac"] - (1.0 / 11.5)) < 1e-12


def test_bootstrap_ci_is_seeded_and_brackets_point_estimate():
    pnls = [1.5, -1.0, 0.8, -0.5, 1.2, -1.0]
    stakes = [1.0] * 6
    lo, hi = bootstrap_ci(pnls=pnls, stakes=stakes, start=10.0,
                          metric="roi", resamples=500, seed=20260611)
    point = roi_metrics(pnls=pnls, stakes=stakes, start=10.0)["roi"]
    assert lo <= point <= hi
    # seeded -> identical across calls.
    lo2, hi2 = bootstrap_ci(pnls=pnls, stakes=stakes, start=10.0,
                            metric="roi", resamples=500, seed=20260611)
    assert (lo, hi) == (lo2, hi2)


def test_bootstrap_ci_refuses_order_dependent_and_unknown_metrics():
    # Quality-review finding: drawdown is PATH-ORDER-DEPENDENT, but the bootstrap
    # resamples bet indices (destroys temporal order) -> a CI on it is meaningless
    # (a reshuffle front-loading losses drove the probe to a 110% upper bound). It
    # must RAISE, not return a bogus number. An unknown metric also raises (rather
    # than KeyError-ing mid-resample). Order-independent roi still works.
    import pytest
    pnls = [1.5, -1.0, 0.8, -0.5]
    stakes = [1.0] * 4
    for bad in ("max_drawdown", "max_drawdown_frac", "not_a_metric"):
        with pytest.raises(ValueError):
            bootstrap_ci(pnls=pnls, stakes=stakes, start=10.0, metric=bad,
                         resamples=50, seed=0)
    lo, hi = bootstrap_ci(pnls=pnls, stakes=stakes, start=10.0, metric="roi",
                          resamples=50, seed=0)
    assert lo <= hi
