import numpy as np
import pytest
from wcmodel.backtest.totals_backtest import (
    score_totals_row, _settle_total, calibration_table, totals_verdict,
)


class _StubPost:
    """A posterior whose grid is a fixed pmf (no fit) — isolates the harness logic from ADVI."""
    def __init__(self, grid): self._g = np.asarray(grid, float)
    def predict_scoreline(self, home, away, neutral=False, max_goals=10, covariates=None,
                          host_factor=None):
        return self._g


def test_settle_total_over_under():
    assert _settle_total(2.5, "over", home_goals=2, away_goals=1) is True    # total 3 > 2.5
    assert _settle_total(2.5, "under", home_goals=2, away_goals=1) is False
    assert _settle_total(2.5, "under", home_goals=1, away_goals=0) is True   # total 1 < 2.5


def test_score_totals_row_settles_and_clv():
    # grid heavily favors >2.5 goals; book offers a generous Over price -> +EV Over bet that WINS.
    g = np.zeros((6, 6)); g[3, 1] = 1.0                                      # total 4, certain
    row = {"home": "A", "away": "B", "neutral": True, "home_goals": 3, "away_goals": 1,
           "entry": {2.5: {"over_odds": 2.10, "under_odds": 1.75}},
           "close": {2.5: {"over_odds": 1.90, "under_odds": 1.95}}}          # over shortened -> +CLV
    res = score_totals_row(_StubPost(g), row, lines=[2.5], edge_threshold=0.03, se=0.0)
    assert len(res["bets"]) == 1
    b = res["bets"][0]
    assert (b["line"], b["side"]) == (2.5, "over")
    assert b["won"] is True
    assert b["clv"] > 0.0                                                     # 2.10 entry vs 1.90 close
    assert b["pnl"] > 0.0                                                     # winning bet, positive pnl


def test_score_totals_row_plumbs_kelly_fraction():
    # The stake is kelly_fraction × full-Kelly × shrink, so halving kelly_fraction halves the
    # stake. This pins that score_totals_row actually THREADS kelly_fraction to totals_edges
    # (it is no longer silently stuck at the 0.25 default).
    g = np.zeros((6, 6)); g[3, 1] = 0.7; g[1, 1] = 0.3      # spread mass -> odds-dependent stake
    row = {"home": "A", "away": "B", "neutral": True, "home_goals": 3, "away_goals": 1,
           "entry": {2.5: {"over_odds": 2.10, "under_odds": 1.75}},
           "close": {2.5: {"over_odds": 1.90, "under_odds": 1.95}}}
    quarter = score_totals_row(_StubPost(g), row, lines=[2.5], edge_threshold=0.03, se=0.0,
                               kelly_fraction=0.25)["bets"][0]["stake"]
    eighth = score_totals_row(_StubPost(g), row, lines=[2.5], edge_threshold=0.03, se=0.0,
                              kelly_fraction=0.125)["bets"][0]["stake"]
    assert eighth == pytest.approx(quarter / 2.0)


def test_score_totals_row_defaults_to_quarter_kelly():
    # Default kelly_fraction is the project ¼-Kelly (0.25) when the caller does not pass one.
    g = np.zeros((6, 6)); g[3, 1] = 0.7; g[1, 1] = 0.3
    row = {"home": "A", "away": "B", "neutral": True, "home_goals": 3, "away_goals": 1,
           "entry": {2.5: {"over_odds": 2.10, "under_odds": 1.75}},
           "close": {2.5: {"over_odds": 1.90, "under_odds": 1.95}}}
    default = score_totals_row(_StubPost(g), row, lines=[2.5], edge_threshold=0.03, se=0.0)
    explicit = score_totals_row(_StubPost(g), row, lines=[2.5], edge_threshold=0.03, se=0.0,
                                kelly_fraction=0.25)
    assert default["bets"][0]["stake"] == explicit["bets"][0]["stake"]


def test_score_totals_row_close_present_is_not_masked_as_gap():
    # A pick whose close line IS present must compute a CLV (clv is not None). The gap sentinel is
    # a MISSING close price (None), not a falsy-but-present one — so the guard is `is not None`,
    # not truthiness. Here the close over_odds is present (1.90) -> clv computed.
    g = np.zeros((6, 6)); g[3, 1] = 0.7; g[1, 1] = 0.3
    row = {"home": "A", "away": "B", "neutral": True, "home_goals": 3, "away_goals": 1,
           "entry": {2.5: {"over_odds": 2.10, "under_odds": 1.75}},
           "close": {2.5: {"over_odds": 1.90, "under_odds": 1.95}}}
    b = score_totals_row(_StubPost(g), row, lines=[2.5], edge_threshold=0.03, se=0.0)["bets"][0]
    assert b["clv"] is not None


def test_score_totals_row_missing_close_line_is_clv_none():
    # No close line for the bet -> clv is None (recorded coverage gap, not a crash).
    g = np.zeros((6, 6)); g[3, 1] = 0.7; g[1, 1] = 0.3
    row = {"home": "A", "away": "B", "neutral": True, "home_goals": 3, "away_goals": 1,
           "entry": {2.5: {"over_odds": 2.10, "under_odds": 1.75}}, "close": {}}
    b = score_totals_row(_StubPost(g), row, lines=[2.5], edge_threshold=0.03, se=0.0)["bets"][0]
    assert b["clv"] is None


def test_calibration_table_bins_predicted_vs_realized():
    # 4 fixtures at line 2.5; model P(over) vs whether over actually hit.
    rows = [
        {"line": 2.5, "p_over": 0.9, "over_hit": True},
        {"line": 2.5, "p_over": 0.8, "over_hit": True},
        {"line": 2.5, "p_over": 0.2, "over_hit": False},
        {"line": 2.5, "p_over": 0.1, "over_hit": False},
    ]
    tab = calibration_table(rows, bins=[0.0, 0.5, 1.0])
    # high-prob bin (>0.5): 2 fixtures, both hit -> observed 1.0; mean predicted ~0.85
    hi = tab[(0.5, 1.0)]
    assert hi["n"] == 2 and hi["observed"] == 1.0 and 0.8 <= hi["predicted"] <= 0.9


def test_totals_verdict_rejects_no_edge_and_nan():
    assert totals_verdict({"n_bets": 0, "roi": float("nan"), "avg_clv": float("nan")},
                          paired_p=float("nan")) == "reject"
    assert totals_verdict({"n_bets": 20, "roi": -0.05, "avg_clv": -0.01},
                          paired_p=0.5) == "reject"           # negative CLV -> reject


def test_totals_verdict_accepts_positive_clv_and_roi_and_sig():
    assert totals_verdict({"n_bets": 40, "roi": 0.03, "avg_clv": 0.012},
                          paired_p=0.01) == "accept"
