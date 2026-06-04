"""Phase-3 sim tests: load the real verified WC-2026 bracket + reuse Phase-1/2 fixtures."""
from pathlib import Path

import pytest

from tests.data.conftest import (  # noqa: F401
    small_store,      # reused by the scoreline RateBook test
    mutable_store,    # the future-result canary store (T6 leakage gate)
)
from wcmodel.data.tournament import load_tournament
from wcmodel.sim.bracket import build_bracket

# The verified draw lives at the repo root; resolve it relative to THIS file so
# the fixture is invocation-directory independent. `load_tournament(path)`
# requires an explicit path (the module ships no draw — Phase-0 decision 2).
_REAL_DRAW = Path(__file__).resolve().parents[2] / "config" / "tournament_2026.yaml"


@pytest.fixture(scope="session")
def wc2026() -> dict:
    return load_tournament(_REAL_DRAW)   # the verified config/tournament_2026.yaml


# Four real teams that ALL exist in the small_store posterior (so RateBook.rates
# resolves every fixture) — Brazil/Argentina/Croatia/France are the core panel
# teams in tests/data/conftest.py. Kept tiny so the MC loop runs in milliseconds.
_TINY_TEAMS = ["Brazil", "Argentina", "Croatia", "France"]


def tiny_bracket():
    """A minimal but REAL Bracket: 1 group of 4 -> a single Final between the
    group winner (``1A``) and runner-up (``2A``).

    Built through the production ``build_bracket`` from a synthetic tournament
    dict so the returned object is the genuine ``Bracket`` dataclass with the
    exact attribute shapes the loop consumes (groups, group_fixtures,
    third_place_slots, knockout_feeders, match_round) — not a hand-rolled stand-in
    that could drift from the real structure. The 6 round-robin group fixtures
    carry NO ``match`` field (the group-fixture discriminator); the single Final
    carries ``match: 104`` and the placeholder feeders ``1A``/``2A`` (group A
    winner / runner-up), exercising the full group-sim -> rank_group -> knockout
    -> champion path. No ``3rd-*`` slot (no best-thirds in a 1-group bracket) and
    no distinct SF/QF/R16 round: the depth-from-final ladder must still emit a
    coherent ``reach_sf`` (a finalist sits at depth 0, below the SF depth-1
    threshold, so reach_sf == reach_final here)."""
    a, b, c, d = _TINY_TEAMS
    group_fixtures = [
        (a, b), (c, d), (a, c), (b, d), (a, d), (b, c),   # 6 round-robin pairs
    ]
    tournament = {
        "groups": [{"name": "A", "teams": list(_TINY_TEAMS)}],
        "fixtures": [
            # Group fixtures: NO `match` key -> build_bracket routes to group_fixtures.
            *[{"home": h, "away": aw, "round": "Matchday 1"} for h, aw in group_fixtures],
            # The Final: `match` key + placeholder feeders -> knockout_feeders[104].
            {"match": 104, "home": "1A", "away": "2A", "round": "Final"},
        ],
    }
    return build_bracket(tournament)
