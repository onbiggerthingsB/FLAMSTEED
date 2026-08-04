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

from oa_devslate import (                                    # noqa: E402
    build, extra_time_possible, is_knockout,
)


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
    assert set(inspect.signature(is_knockout).parameters) == {
        "tournament", "date"}
    # extra_time_possible may see identities but never a score, an override,
    # or anything else produced by playing the match.
    assert set(inspect.signature(extra_time_possible).parameters) == {
        "tournament", "date", "home", "away"}


# --------------------------------------------------------- the population
@pytest.fixture(scope="module")
def built():
    return build()


def test_no_extra_time_possible_fixture_survives(built):
    """The invariant: every admitted fixture had extra time structurally
    unavailable, so its full-time score IS its 90-minute score. Note this is
    NOT "no knockout fixture" — rounds that go straight from 90' to penalties
    are safe, and excluding them cost 14 valid fixtures in the first repair."""
    frame, _ = built
    leaked = [(r.tournament, r.date, r.home, r.away)
              for r in frame.itertuples(index=False)
              if extra_time_possible(r.tournament, r.date, r.home, r.away)]
    assert not leaked, f"extra-time-capable fixtures leaked: {leaked}"


@pytest.mark.parametrize("home,away,date,present,why", [
    # Same competition, adjacent rounds, opposite answers. These pin the
    # REGULATION, not the classifier: reading them off one oracle is what
    # made the previous version of this test tautological.
    ("Argentina", "Colombia", "2024-07-14", False, "Copa final HAS extra time"),
    ("Canada", "Uruguay", "2024-07-13", True, "Copa 3rd place: 90'->pens"),
    ("Argentina", "Canada", "2024-07-09", True, "Copa SF: 90'->pens"),
    # Same DATE, opposite answers — proof that date alone is insufficient.
    ("Netherlands", "Italy", "2023-06-18", True, "NL 3rd place: no ET"),
    ("Croatia", "Spain", "2023-06-18", False, "NL final HAS extra time"),
    ("Germany", "France", "2025-06-08", True, "NL 3rd place: no ET"),
    ("Portugal", "Spain", "2025-06-08", False, "NL final HAS extra time"),
    # Two-legged tie: first leg cannot reach ET, second leg can.
    ("Netherlands", "Spain", "2025-03-20", True, "NL QF first leg: no ET"),
    ("Spain", "Netherlands", "2025-03-23", False, "NL QF second leg: ET"),
    # AFCON third place goes straight to penalties; the final does not.
    ("Cameroon", "Burkina Faso", "2022-02-05", True, "AFCON 3rd: 90'->pens"),
    ("Senegal", "Egypt", "2022-02-06", False, "AFCON final HAS extra time"),
])
def test_round_level_regulation_is_pinned(built, home, away, date, present,
                                          why):
    """Each case is a published-regulation fact, checked against the built
    population rather than against the classifier that produced it."""
    frame, _ = built
    hit = frame[(frame.home == home) & (frame.away == away)
                & (frame.date == date)]
    assert (not hit.empty) is present, f"{home} v {away} {date}: {why}"


def test_the_fourteen_safe_knockout_fixtures_are_admitted(built):
    """The first repair excluded ALL knockouts and lost 14 valid fixtures.
    They must be back, and they must be knockout — otherwise this passes
    vacuously by the exclusion being wrong in the other direction."""
    frame, _ = built
    safe_ko = [r for r in frame.itertuples(index=False)
               if is_knockout(r.tournament, r.date)]
    assert len(safe_ko) == 14


def test_an_unclassified_edition_fails_closed(built):
    """Fail-open was the original bug's shape. An edition we have not
    classified must raise, never be assumed regulation-only."""
    from oa_devslate import DevSlateError
    with pytest.raises(DevSlateError, match="unclassified edition"):
        is_knockout("UEFA Nations League", "2027-06-10")


@pytest.mark.parametrize("home,away,date", [
    ("Egypt", "Morocco", "2022-01-30"),          # 1-1 at 90, 2-1 in ET
    ("Netherlands", "Croatia", "2023-06-14"),    # 2-2 at 90, 4-2 in ET
    ("Ivory Coast", "Mali", "2024-02-03"),       # 1-1 at 90, 2-1 in ET
    ("Argentina", "Colombia", "2024-07-14"),     # 0-0 at 90, 1-0 in ET
])
def test_the_four_mis_scored_extra_time_fixtures_are_gone(built, home, away,
                                                          date):
    """Golden cases. Each was previously scored on its ET-inclusive final,
    turning a 90-minute DRAW into a home or away win. All four are
    extra-time-capable knockout ties and must be excluded."""
    frame, _ = built
    hit = frame[(frame.home == home) & (frame.away == away)
                & (frame.date == date)]
    assert hit.empty, f"{home} v {away} {date} was decided in extra time"


def test_population_is_reported_not_silently_shrunk(built):
    """A shrinking sample must be visible. The counts have to add up."""
    frame, counts = built
    assert counts["admitted"] == len(frame)
    assert counts["total"] == (counts["admitted"] + counts["extra_time_excluded"]
                               + counts["no_store_row"]
                               + counts["no_odds_comparator"])
    assert counts["extra_time_excluded"] > 0, "the exclusion must be non-vacuous"


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
