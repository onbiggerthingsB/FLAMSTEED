"""Phase-3 sim tests: load the real verified WC-2026 bracket + reuse Phase-1/2 fixtures."""
from pathlib import Path

import pytest

from tests.data.conftest import small_store  # noqa: F401  (reused by scoreline RateBook test)
from wcmodel.data.tournament import load_tournament

# The verified draw lives at the repo root; resolve it relative to THIS file so
# the fixture is invocation-directory independent. `load_tournament(path)`
# requires an explicit path (the module ships no draw — Phase-0 decision 2).
_REAL_DRAW = Path(__file__).resolve().parents[2] / "config" / "tournament_2026.yaml"


@pytest.fixture(scope="session")
def wc2026() -> dict:
    return load_tournament(_REAL_DRAW)   # the verified config/tournament_2026.yaml
