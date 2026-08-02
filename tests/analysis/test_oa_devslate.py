"""Tests for the corrected dev-slate population and settlement.

These exist because the first version had none. Two defects shipped as a
result — outcome-based exclusion of shootouts, and extra-time-inclusive
scoring of knockout ties — and both produced published numbers before a
review caught them. Each test below pins one of those failures.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "analysis"))
sys.path.insert(0, str(_ROOT / "src"))

from oa_devslate import build, is_knockout                    # noqa: E402


# ------------------------------------------------- stage classification
@pytest.mark.parametrize("tournament,date,expected", [
    # AFCON 2022: groups end 01-20, R16 opens 01-23
    ("African Cup of Nations", "2022-01-20", False),
    ("African Cup of Nations", "2022-01-23", True),
    ("African Cup of Nations", "2022-02-06", True),      # the final
    # AFCON 2024: groups end 01-24, R16 opens 01-27
    ("African Cup of Nations", "2024-01-24", False),
    ("African Cup of Nations", "2024-01-27", True),
    # AFCON 2025 in-window is group stage only
    ("African Cup of Nations", "2025-12-31", False),
    # Copa America 2024: groups end 07-02, QF open 07-04
    ("Copa América", "2024-07-02", False),
    ("Copa América", "2024-07-05", True),
    # Nations League league phases carry no knockout
    ("UEFA Nations League", "2022-09-27", False),
    ("UEFA Nations League", "2024-11-19", False),
    # ...but the 2023 finals and 2025 QF/finals are knockout throughout
    ("UEFA Nations League", "2023-06-14", True),
    ("UEFA Nations League", "2025-03-20", True),
    # qualification is a league
    ("FIFA World Cup qualification", "2025-09-09", False),
])
def test_stage_classification(tournament, date, expected):
    assert is_knockout(tournament, date) is expected


def test_classification_never_consults_the_result():
    """The rule must be decidable before kickoff. Same fixture slot, any
    score: the answer cannot move, because the signature has nowhere to put
    one."""
    import inspect
    params = set(inspect.signature(is_knockout).parameters)
    assert params == {"tournament", "date"}


# --------------------------------------------------------- the population
@pytest.fixture(scope="module")
def built():
    return build()


def test_no_knockout_fixture_survives(built):
    """The whole point: every admitted fixture had extra time structurally
    unavailable, so its full-time score IS its 90-minute score."""
    frame, _ = built
    leaked = [(r.tournament, r.date) for r in frame.itertuples(index=False)
              if is_knockout(r.tournament, r.date)]
    assert not leaked, f"knockout fixtures leaked into the population: {leaked}"


@pytest.mark.parametrize("home,away,date", [
    ("Egypt", "Morocco", "2022-01-30"),          # 1-1 at 90, 2-1 in ET
    ("Netherlands", "Croatia", "2023-06-14"),    # 2-2 at 90, 4-2 in ET
    ("Ivory Coast", "Mali", "2024-02-03"),       # 1-1 at 90, 2-1 in ET
    ("Argentina", "Colombia", "2024-07-14"),     # 0-0 at 90, 1-0 in ET
])
def test_the_four_mis_scored_extra_time_fixtures_are_gone(built, home, away,
                                                          date):
    """Golden cases. Each was previously scored on its ET-inclusive final,
    turning a 90-minute DRAW into a home or away win. All four are knockout
    ties and must now be excluded by stage."""
    frame, _ = built
    hit = frame[(frame.home == home) & (frame.away == away)
                & (frame.date == date)]
    assert hit.empty, f"{home} v {away} {date} was decided in extra time"


def test_population_is_reported_not_silently_shrunk(built):
    """A shrinking sample must be visible. The counts have to add up."""
    frame, counts = built
    assert counts["admitted"] == len(frame)
    assert counts["total"] == (counts["admitted"] + counts["knockout_excluded"]
                               + counts["no_store_row"]
                               + counts["no_odds_comparator"])
    assert counts["knockout_excluded"] > 0, "the exclusion must be non-vacuous"


def test_delta_sign_convention(built):
    """delta = RPS(book) - RPS(model); negative means the market scored
    better. Every downstream conclusion depends on this orientation."""
    frame, _ = built
    row = frame.iloc[0]
    assert row["delta"] == pytest.approx(row["rps_book"] - row["rps_model"])


def test_both_confederation_groups_are_populated(built):
    """The H1 split needs both sides; a one-sided population would make the
    test vacuous rather than negative."""
    frame, _ = built
    assert frame["core"].sum() > 20
    assert (~frame["core"]).sum() > 20
