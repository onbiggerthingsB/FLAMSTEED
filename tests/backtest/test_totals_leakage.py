import numpy as np
from wcmodel.backtest.totals_backtest import score_totals_row


class _StubPost:
    def __init__(self, grid): self._g = np.asarray(grid, float)
    def predict_scoreline(self, home, away, neutral=False, max_goals=10, covariates=None,
                          host_factor=None):
        return self._g


def test_pick_is_invariant_to_close_and_result():
    g = np.zeros((6, 6)); g[3, 1] = 1.0
    base = {"home": "A", "away": "B", "neutral": True, "home_goals": 3, "away_goals": 1,
            "entry": {2.5: {"over_odds": 2.10, "under_odds": 1.75}},
            "close": {2.5: {"over_odds": 1.90, "under_odds": 1.95}}}
    picks_base = [(b["line"], b["side"], round(b["stake"], 9))
                  for b in score_totals_row(_StubPost(g), base, lines=[2.5],
                                             edge_threshold=0.03, se=0.0)["bets"]]
    # mutate the CLOSE odds and the RESULT — the PICK (line/side/stake) must be identical;
    # only settlement (won/clv) may differ. The pick is a function of model+ENTRY only.
    moved = {**base, "home_goals": 0, "away_goals": 0,
             "close": {2.5: {"over_odds": 5.0, "under_odds": 1.1}}}
    picks_moved = [(b["line"], b["side"], round(b["stake"], 9))
                   for b in score_totals_row(_StubPost(g), moved, lines=[2.5],
                                              edge_threshold=0.03, se=0.0)["bets"]]
    assert picks_base == picks_moved        # pick uses ONLY model + entry; close/result never leak in
    assert len(picks_base) == 1   # the invariance is over a REAL placed bet (non-vacuous)
