"""Phase-5 live tests: reuse the Phase-1/2/3/4 fixtures + load the live config."""
from pathlib import Path

import pytest

from tests.data.conftest import (  # noqa: F401
    small_store,      # compact leakage-safe panel (Brazil/Argentina/Croatia/France + ladder)
    mutable_store,    # MutableStore.mutate_future_result(after) — the canary store
    matches_df,       # tiny date-spanning panel
)
from wcmodel.config import load_config

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "oddsapi_historical_sample.json"


@pytest.fixture(scope="session")
def odds_fixture_path() -> Path:
    """The hand-built REAL-PARSE Odds API fixture (Brazil vs Croatia; pinnacle + betfair)."""
    return _FIXTURE


@pytest.fixture
def cfg() -> dict:
    return load_config()
