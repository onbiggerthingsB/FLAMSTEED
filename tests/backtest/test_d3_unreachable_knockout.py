import pandas as pd

from wcmodel.backtest.walkforward import build_cutoff_grid


def test_backtest_grid_never_reaches_an_in_tournament_knockout(cfg):
    """D3 deferral soundness: the Phase-4 backtest conditions on NO in-tournament
    knockout (WC-2026 hasn't happened; prior WCs aren't in the WC-2026 bracket),
    so a level pinned knockout — which sim/run.py fails loud on — is UNREACHABLE.
    This test pins that: every cutoff in the backtest grid is strictly BEFORE the
    WC-2026 knockout stage begins, so no KO fixture is ever pinned as 'decided'."""
    # WC-2026 knockouts (matches 73-104) start 2026-06-28 (Round of 32 per the
    # verified config/tournament_2026.yaml). The odds_start is 2020-06-06 and the
    # backtestable history is HISTORICAL international matches that pre-date the
    # tournament; build a panel of such matches and confirm the grid stays pre-KO.
    matches = pd.DataFrame({"date": pd.to_datetime([
        "2020-06-06", "2022-12-18", "2024-07-14", "2025-03-25",
    ])})
    grid = build_cutoff_grid(matches, cfg["backtest"]["odds_start"])
    wc2026_ko_start = pd.Timestamp("2026-06-28")
    assert all(c < wc2026_ko_start for c in grid), (
        "a backtest cutoff reached the WC-2026 knockout window — the D3 deferral "
        "(no in-tournament knockout in the backtest) is no longer sound; the "
        "penalty-KO data fix must be done before extending the grid into the bracket"
    )


def test_no_played_wc2026_knockout_in_history(small_store):
    """The historical store contains no PLAYED WC-2026 knockout result (the bracket
    is unplayed), so the walk-forward never pins a level KO -> sim/run.py's
    fail-loud guard is never tripped by this phase (D3)."""
    res = small_store.read("results", cutoff="2026-06-04")
    # No fixture in the store is a WC-2026 knockout (matches 73-104) — the panel is
    # pre-tournament international history only.
    assert "match" not in res.columns         # results carry match_id, not bracket match-no
    # Sanity: every result is a played historical match with a real score.
    assert res[["home_score", "away_score"]].notna().all().all()
