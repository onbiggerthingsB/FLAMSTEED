"""Review-v2 Fix 1 (finding C1): orientation-tolerant fixture<->result matching.

martj42 recorded three real 2026 matchday-3 games with home/away REVERSED
relative to config/tournament_2026.yaml (A: Czech Republic-Mexico,
B: Switzerland-Canada, D: Turkey-United States). The exact (home, away, date)
triple match in run._build_played / simulate_one therefore silently FAILED to
condition them — the sim re-sampled decided games every draw (the live
Canada-0.714 symptom). These tests pin the fix: a played result recorded in
EITHER orientation conditions its fixture, with the score (not the recorded
winner name) flipped to the fixture's orientation.
"""
import numpy as np
import pandas as pd

from tests.sim.conftest import tiny_bracket
from tests.sim.test_tournament import _inv_posterior
from wcmodel.sim.run import _build_played
from wcmodel.sim.tournament import simulate_tournament

_DATE = pd.Timestamp("2026-07-10")

# tiny_bracket group fixtures (yaml orientation), scores chosen so the group is
# FULLY DETERMINISTIC (no points/GD/GF tie anywhere): Croatia 9, France 6,
# Brazil 3, Argentina 0.
_GROUP_RESULTS = {
    ("Brazil", "Argentina"): (1, 0),
    ("Croatia", "France"): (1, 0),
    ("Brazil", "Croatia"): (0, 1),
    ("Argentina", "France"): (0, 1),
    ("Brazil", "France"): (0, 2),
    ("Argentina", "Croatia"): (0, 3),
}


class _StubStore:
    """Minimal store: read() returns pre-cutoff played rows, one REVERSED."""

    def __init__(self, rows):
        self._df = pd.DataFrame(rows)

    def read(self, name, cutoff):
        return self._df.copy()


def test_build_played_conditions_reversed_group_fixture():
    """A store row recorded (away, home) still pins the (home, away) fixture,
    with the score flipped to the fixture's orientation."""
    rows = [
        # yaml fixture is (Croatia, France) — store has it REVERSED, France won 2-1
        # in store orientation, i.e. Croatia 1 - 2 France in fixture orientation.
        {"home_team": "France", "away_team": "Croatia", "home_score": 2,
         "away_score": 1, "date": pd.Timestamp("2026-06-20")},
        # control: normal orientation row must keep working unchanged.
        {"home_team": "Brazil", "away_team": "Argentina", "home_score": 1,
         "away_score": 0, "date": pd.Timestamp("2026-06-20")},
    ]
    group_dates = {("Croatia", "France"): pd.Timestamp("2026-06-20"),
                   ("Brazil", "Argentina"): pd.Timestamp("2026-06-20")}
    played = _build_played(_StubStore(rows), "2026-07-01T00:00:00Z",
                           group_dates, {})
    assert played["groups"][("Brazil", "Argentina")] == (1, 0)      # control
    assert played["groups"][("Croatia", "France")] == (1, 2)        # flipped


def test_exact_orientation_wins_over_reversed():
    """If BOTH orientations exist (a duplicated match), the exact-orientation
    row is authoritative — the reversed twin must not overwrite it."""
    rows = [
        {"home_team": "Croatia", "away_team": "France", "home_score": 1,
         "away_score": 2, "date": pd.Timestamp("2026-06-20")},
        {"home_team": "France", "away_team": "Croatia", "home_score": 2,
         "away_score": 1, "date": pd.Timestamp("2026-06-20")},
    ]
    group_dates = {("Croatia", "France"): pd.Timestamp("2026-06-20")}
    played = _build_played(_StubStore(rows), "2026-07-01T00:00:00Z",
                           group_dates, {})
    assert played["groups"][("Croatia", "France")] == (1, 2)


def _played(ko_results, ko_winners=None):
    return {
        "groups": dict(_GROUP_RESULTS),
        "knockout_results": ko_results,
        "knockout_winners": ko_winners or {},
        "match_dates": {104: _DATE},
    }


def _run(played, n_sims=400, seed=0):
    return simulate_tournament(_inv_posterior(), bracket=tiny_bracket(),
                               n_sims=n_sims, seed=seed, max_goals=8,
                               et_scale=0.3333, pen_home_prob=0.5,
                               played=played)


def test_reversed_pinned_knockout_binds_every_draw():
    """THE C1 repro: the Final is drawn (Croatia home, France away) — 1A v 2A of
    a deterministic group — but the played result is recorded REVERSED
    (France, Croatia, date): 0-1, i.e. Croatia won. Pre-fix the exact-triple
    lookup misses and the Final is SAMPLED (champion(Croatia) < 1); post-fix
    the reversed row binds in EVERY draw."""
    res = _run(_played({("France", "Croatia", _DATE): (0, 1)}))
    assert res.progression.loc["Croatia", "champion"] == 1.0
    assert res.progression.loc["France", "champion"] == 0.0


def test_exact_orientation_pinned_knockout_still_binds():
    """Regression guard: the normal-orientation pinned KO keeps working."""
    res = _run(_played({("Croatia", "France", _DATE): (1, 0)}))
    assert res.progression.loc["Croatia", "champion"] == 1.0


def test_reversed_level_ko_resolves_via_winner_override():
    """A penalty-decided KO recorded in reversed orientation: the level score
    flips harmlessly (1-1) and the winner_override — keyed by the STORE's
    orientation triple, holding a team NAME — must still resolve it."""
    res = _run(_played({("France", "Croatia", _DATE): (1, 1)},
                       {("France", "Croatia", _DATE): "Croatia"}))
    assert res.progression.loc["Croatia", "champion"] == 1.0
    assert res.progression.loc["France", "champion"] == 0.0
