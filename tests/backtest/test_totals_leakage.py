import numpy as np
from wcmodel.backtest.totals_backtest import score_totals_row


class _StubPost:
    def __init__(self, grid): self._g = np.asarray(grid, float)
    def predict_scoreline(self, home, away, neutral=False, max_goals=10, covariates=None,
                          host_factor=None):
        return self._g


def _nondegenerate_grid():
    """A spread-mass 6x6 pmf with ``p_over(2.5) ≈ 0.62`` (NOT a point mass).

    The spread mass makes the ¼-Kelly stake ODDS-DEPENDENT (a point-mass p_over=1.0 grid makes
    the Kelly fraction f*=1 regardless of price, so the stake is odds-INDEPENDENT and the canary
    would be blind to a close-for-entry substitution). With this grid the over-side stake is a
    strictly monotone function of the offered odds, so reading ``close`` instead of ``entry`` to
    PICK produces a DIFFERENT stake — the leak the canary must catch.
    """
    g = np.zeros((6, 6))
    mass = {(0, 0): 0.05, (1, 0): 0.06, (0, 1): 0.06, (1, 1): 0.09, (2, 0): 0.05, (0, 2): 0.05,
            (2, 1): 0.085, (1, 2): 0.085, (2, 2): 0.10, (3, 1): 0.065, (1, 3): 0.065,
            (3, 0): 0.03, (0, 3): 0.03, (3, 2): 0.045, (2, 3): 0.045, (3, 3): 0.025,
            (4, 1): 0.015, (1, 4): 0.015}
    for (h, a), v in mass.items():
        g[h, a] = v
    return g / g.sum()


def test_pick_is_invariant_to_close_and_result():
    # NON-degenerate grid: p_over(2.5) ≈ 0.62, so the ¼-Kelly stake is ODDS-DEPENDENT (a point-mass
    # grid makes the stake odds-INDEPENDENT, hiding a close-for-entry substitution leak).
    g = _nondegenerate_grid()
    # ENTRY over_odds=2.10 (the price the honest pick must use); the base CLOSE over_odds=1.90 is
    # DELIBERATELY DIFFERENT from entry, so a pick reading ``close`` would size off 1.90 (a different
    # Kelly stake) — and the moved close (5.0) would size off yet another stake. Honest pick reads
    # ENTRY only, so it is invariant to both.
    base = {"home": "A", "away": "B", "neutral": True, "home_goals": 3, "away_goals": 1,
            "entry": {2.5: {"over_odds": 2.10, "under_odds": 1.75}},
            "close": {2.5: {"over_odds": 1.90, "under_odds": 1.95}}}
    bets_base = score_totals_row(_StubPost(g), base, lines=[2.5],
                                 edge_threshold=0.03, se=0.0)["bets"]
    picks_base = [(b["line"], b["side"], round(b["stake"], 9)) for b in bets_base]
    # mutate the CLOSE odds and the RESULT — the PICK (line/side/stake) must be identical;
    # only settlement (won/clv) may differ. The pick is a function of model+ENTRY only.
    moved = {**base, "home_goals": 0, "away_goals": 0,
             "close": {2.5: {"over_odds": 5.0, "under_odds": 1.1}}}
    picks_moved = [(b["line"], b["side"], round(b["stake"], 9))
                   for b in score_totals_row(_StubPost(g), moved, lines=[2.5],
                                              edge_threshold=0.03, se=0.0)["bets"]]
    assert picks_base == picks_moved        # pick uses ONLY model + entry; close/result never leak in
    assert len(picks_base) == 1   # the invariance is over a REAL placed bet (non-vacuous)
    # DIRECT close-for-entry catch (grid-independent): the placed bet is priced at the ENTRY
    # over_odds (2.10), NEVER the close (1.90). A harness that read close to pick would carry 1.90.
    assert bets_base[0]["odds"] == 2.10
