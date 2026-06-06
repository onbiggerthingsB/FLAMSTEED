"""HIGH-1 / HIGH-2 (C5 FOCAL Codex): xG and rest_days in the match-detail "why" must be
FIXTURE-IDENTITY-matched — a FUTURE WC-2026 fixture (uncovered by StatsBomb, not played
as-of cutoff) must show an explicit ``coverage_gap`` for ``why["xg"]`` and ``why["rest_days"]``,
NEVER a stale prior-match number.

THE FABRICATION (before the fix). ``_xg_node`` filtered ``xg_read`` by TEAM only and emitted
the team's LAST historical xg; ``_rest_days`` filtered ``features`` by TEAM only and emitted
the last historical rest_days. But the xg store is per ``(match_id, team)`` (StatsBomb is
HISTORICAL — a future WC-2026 fixture is never covered) and ``features.build(cutoff)`` DROPS
future/unplayed rows, so a future fixture has NO row of its own in either frame. Emitting a
DIFFERENT match's value onto a future fixture is fabrication — exactly what these tests forbid.

THE FIX. xG is a coverage_gap UNLESS the xg read has a row for THIS exact fixture's identity
(team == home AND opponent == away AND match_date == date, or the symmetric); rest_days is
emitted ONLY if THIS fixture (by (home_team, away_team, date) identity) is a played row in the
features frame. For a future fixture both ALWAYS gap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wcmodel.dashboard.build import _fixture_why


class _FakePost:
    """A minimal posterior the team-strength "why" can index (att/def draws per team)."""
    _idx = {"Brazil": 0, "Mexico": 1}

    def _post(self, name):
        rng = np.random.default_rng(0)
        return np.vstack([rng.normal(0.3, 0.1, 200), rng.normal(-0.1, 0.1, 200)])


# A FUTURE WC-2026 group fixture: Brazil vs Mexico on 2026-06-20. Neither team's row for THIS
# fixture exists in the as-of reads (StatsBomb is historical; features drop the unplayed row).
_HOME, _AWAY, _FDATE = "Brazil", "Mexico", "2026-06-20"

# An xg read that DOES carry STALE prior-match xg rows for BOTH teams (different matches), to
# prove the fix matches on fixture IDENTITY, not team-last. Columns mirror normalize_match_xg:
# (match_id, match_date, team, opponent, is_home, xg).
_STALE_XG = pd.DataFrame([
    {"match_id": "old1", "match_date": pd.Timestamp("2022-12-09"),
     "team": "Brazil", "opponent": "Croatia", "is_home": False, "xg": 1.7},
    {"match_id": "old2", "match_date": pd.Timestamp("2022-11-26"),
     "team": "Mexico", "opponent": "Argentina", "is_home": True, "xg": 0.9},
])

# A features frame that DOES carry STALE prior-match rest_days rows for BOTH teams (a played
# row each, a DIFFERENT fixture), to prove rest gaps on the future fixture despite team history.
_STALE_FEATURES = pd.DataFrame([
    {"match_id": "old1", "date": pd.Timestamp("2022-12-09"), "team": "Brazil",
     "home_team": "Croatia", "away_team": "Brazil", "rest_days": 4.0},
    {"match_id": "old2", "date": pd.Timestamp("2022-11-26"), "team": "Mexico",
     "home_team": "Mexico", "away_team": "Argentina", "rest_days": 6.0},
])


def _why_future():
    return _fixture_why(_FakePost(), home=_HOME, away=_AWAY, date=_FDATE,
                        xg_read=_STALE_XG, features=_STALE_FEATURES, results=None)


def test_xg_gaps_for_a_future_fixture_never_a_stale_team_last_number():
    why = _why_future()
    for side in ("home", "away"):
        node = why["xg"][side]
        assert node.get("coverage_gap") is True, (
            f"xg[{side}] fabricated a value for a FUTURE/uncovered fixture: {node!r} — it must "
            "be a coverage_gap (StatsBomb never covers a future WC-2026 fixture)"
        )
        assert node.get("value") is None
    # Belt-and-braces: the stale numbers (1.7 / 0.9) must NOT have leaked through.
    assert why["xg"]["home"].get("value") != 1.7
    assert why["xg"]["away"].get("value") != 0.9


def test_rest_days_gaps_for_a_future_unplayed_fixture_never_stale():
    why = _why_future()
    for side in ("home", "away"):
        node = why["rest_days"][side]
        assert node.get("coverage_gap") is True, (
            f"rest_days[{side}] fabricated a value for a FUTURE/unplayed fixture: {node!r} — "
            "features.build(cutoff) drops the unplayed row, so rest_days is a coverage_gap"
        )
        assert node.get("value") is None
    # The stale numbers (4.0 / 6.0) must NOT have leaked through.
    assert why["rest_days"]["home"].get("value") != 4.0
    assert why["rest_days"]["away"].get("value") != 6.0


def test_xg_is_emitted_when_the_fixture_identity_IS_covered():
    """Positive case: when the xg read DOES carry a row for THIS exact fixture identity
    (team=home, opponent=away, match_date=date), the value is emitted (no over-gapping)."""
    covered_xg = pd.concat([_STALE_XG, pd.DataFrame([
        {"match_id": "thisfix", "match_date": pd.Timestamp(_FDATE),
         "team": _HOME, "opponent": _AWAY, "is_home": True, "xg": 2.3},
        {"match_id": "thisfix", "match_date": pd.Timestamp(_FDATE),
         "team": _AWAY, "opponent": _HOME, "is_home": False, "xg": 0.8},
    ])], ignore_index=True)
    why = _fixture_why(_FakePost(), home=_HOME, away=_AWAY, date=_FDATE,
                       xg_read=covered_xg, features=_STALE_FEATURES, results=None)
    assert why["xg"]["home"] == {"value": 2.3}
    assert why["xg"]["away"] == {"value": 0.8}


def test_rest_days_is_emitted_when_the_fixture_identity_IS_a_played_row():
    """Positive case: when the features frame DOES carry a played row for THIS exact fixture
    identity ((home_team, away_team, date)), rest_days is emitted (no over-gapping)."""
    played_feats = pd.concat([_STALE_FEATURES, pd.DataFrame([
        {"match_id": "thisfix", "date": pd.Timestamp(_FDATE), "team": _HOME,
         "home_team": _HOME, "away_team": _AWAY, "rest_days": 3.0},
        {"match_id": "thisfix", "date": pd.Timestamp(_FDATE), "team": _AWAY,
         "home_team": _HOME, "away_team": _AWAY, "rest_days": 5.0},
    ])], ignore_index=True)
    why = _fixture_why(_FakePost(), home=_HOME, away=_AWAY, date=_FDATE,
                       xg_read=_STALE_XG, features=played_feats, results=None)
    assert why["rest_days"]["home"] == {"value": 3.0}
    assert why["rest_days"]["away"] == {"value": 5.0}
