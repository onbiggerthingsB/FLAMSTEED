"""Dashboard-layer test fixtures.

The leakage / reproducibility canaries (``test_leakage_dashboard.py``) need a seeded
``BitemporalStore`` to fit+simulate over. Rather than invent a new data shape, we REUSE the
Phase-1/2/3/5 ``small_store`` panel (the same compact, leakage-safe Brazil/Argentina/.../
Malta panel every other leakage test fits against) — re-exported here so it is visible from
``tests/dashboard/`` (a conftest's fixtures only reach its own subtree, and ``small_store``
lives under ``tests/data/``). This mirrors how ``tests/sim/conftest.py`` and
``tests/live/conftest.py`` already import it.

``synthetic_tournament`` is the SAME minimal 1-group-of-4 -> single-Final bracket the
Phase-3 sim leakage gate (``tests/sim/test_leakage_sim.py``) uses, over the PANEL teams the
``small_store`` posterior actually covers. The real verified 48-team ``tournament_2026.yaml``
would ``KeyError`` in ``RateBook(posterior)`` because the compact panel posterior does not
cover all 48 teams — so the canaries thread this synthetic bracket through
``build_snapshot(..., tournament=...)`` (production passes nothing and gets the real draw).
"""
from __future__ import annotations

import pytest

from wcmodel.config import load_config
from tests.data.conftest import (  # noqa: F401  (re-exported so tests/dashboard/ sees them)
    small_store,
    mutable_store,
)


@pytest.fixture
def cfg() -> dict:
    """The project config dict (same fixture as tests/backtest|live/conftest.py), exposed
    here so the C5 full-bundle e2e (which threads ``config=cfg`` into ``build_snapshot`` /
    the scanner) reuses the SAME resolved config every other layer fits against."""
    return load_config()

# PANEL teams every fixture lives in the small_store posterior, so RateBook(posterior)
# resolves every group fixture. Mirrors tests/sim/test_leakage_sim.py's _PANEL_TEAMS.
_PANEL_TEAMS = ["Brazil", "Argentina", "Mexico", "Malta"]

# (home, away) -> group fixture date. The bracket DROPS fixture dates, so simulate() reads
# the fixture->date map from the tournament dict itself; every date is a pre-2026 sentinel
# < the canary cutoff so none of these group fixtures is ever "played as of" the cutoff (the
# bundle is an all-simulated read at the cutoff). Same construction as the sim leakage gate.
_FIXTURE_DATES = {
    ("Brazil", "Argentina"): "2024-05-01",
    ("Mexico", "Malta"): "2024-05-06",
    ("Brazil", "Mexico"): "2024-05-02",
    ("Argentina", "Malta"): "2024-05-03",
    ("Brazil", "Malta"): "2024-05-04",
    ("Argentina", "Mexico"): "2024-05-05",
}


@pytest.fixture
def synthetic_tournament() -> dict:
    """A 1-group-of-4 -> single-Final tournament dict over PANEL teams (the build_snapshot
    ``tournament=`` passthrough), so the snapshot's full group-sim -> rank_group -> knockout
    -> champion path runs over the compact ``small_store`` posterior without a KeyError.

    Group fixtures carry NO ``match`` key (the group-fixture discriminator) + their date; the
    single Final carries ``match: 104`` with placeholder feeders ``1A``/``2A`` — exactly the
    Phase-3 ``tiny_bracket`` / sim-leakage shape, built straight as the dict ``SimConfig``
    accepts (validation is bypassed for a tournament DICT, the documented test escape hatch)."""
    fixtures = [
        {"home": h, "away": a, "date": _FIXTURE_DATES[(h, a)], "round": "Matchday 1"}
        for (h, a) in _FIXTURE_DATES
    ]
    fixtures.append({"match": 104, "home": "1A", "away": "2A", "round": "Final"})
    return {"groups": [{"name": "A", "teams": list(_PANEL_TEAMS)}], "fixtures": fixtures}
