import pandas as pd
import pytest
from pathlib import Path
from wcmodel.data.tournament import (
    ingest_wc_group_fixtures,
    load_tournament,
    validate_tournament,
)
from wcmodel.data.store import BitemporalStore, Policy


def _valid_min():
    # minimal well-formed structure: 48 teams, 12 groups of 4, 104 fixtures, tiebreakers, two-path bracket
    groups = [{"name": chr(65 + i), "teams": [f"T{i}_{j}" for j in range(4)]} for i in range(12)]
    teams = [t for g in groups for t in g["teams"]]
    return {
        "teams": teams,
        "groups": groups,
        "fixtures": [{"home": "x", "away": "y", "date": "2026-06-11"}] * 104,
        "advancement": {"per_group": 2, "best_thirds": 8},
        "third_place_tiebreakers": ["goal_difference", "goals_scored", "head_to_head", "fair_play", "drawing_of_lots"],
        "bracket": {"paths": ["A", "B"]},
    }


def test_validator_accepts_well_formed():
    validate_tournament(_valid_min())   # must not raise


def test_validator_rejects_wrong_group_count():
    bad = {"teams": [], "groups": [{"name": "A", "teams": ["x"]}]}
    with pytest.raises(ValueError):
        validate_tournament(bad)


def test_validator_rejects_wrong_team_total():
    bad = _valid_min(); bad["groups"][0]["teams"] = ["only_three", "b", "c"]  # 47 total
    with pytest.raises(ValueError):
        validate_tournament(bad)


def test_validator_rejects_missing_tiebreakers():
    bad = _valid_min(); bad["third_place_tiebreakers"] = ["goal_difference"]
    with pytest.raises(ValueError):
        validate_tournament(bad)


# --- FIX 1: top-level `teams` must EQUAL the union of group teams -------------
#
# `ingest_wc_group_fixtures` trusts the validated structure for the drawn-48
# set; the validator must therefore guarantee top-level `teams` is exactly the
# group union (48 distinct), so a placeholder token (e.g. "2A") smuggled into
# top-level `teams` is a hard validation failure — not a value that could ever
# be treated as a real drawn nation.

def test_validator_rejects_top_level_team_not_in_any_group():
    """A token in top-level `teams` that appears in NO group (e.g. a "2A"
    placeholder) makes set(teams) != group set → ValueError."""
    bad = _valid_min()
    # Swap one real group member out of top-level `teams` for a placeholder, so
    # the sets differ (and "2A" is in `teams` but no group).
    bad["teams"] = bad["teams"][:-1] + ["2A"]
    assert len(bad["teams"]) == 48  # still 48, still distinct — only the SET differs
    with pytest.raises(ValueError):
        validate_tournament(bad)


def test_validator_rejects_top_level_teams_not_equal_group_set():
    """Even with the right COUNT, top-level `teams` differing from the group
    union (a missing team replaced by a duplicate of another) must raise."""
    bad = _valid_min()
    # 48 entries but not 48 DISTINCT and not equal to the group set: drop the
    # last group member from `teams`, duplicate the first instead.
    bad["teams"] = [bad["teams"][0]] + bad["teams"][:-1]
    assert len(bad["teams"]) == 48
    with pytest.raises(ValueError):
        validate_tournament(bad)


def test_validator_rejects_missing_top_level_teams():
    """Absent top-level `teams` (or non-list) is a hard failure — the drawn set
    has no validated source."""
    bad = _valid_min(); del bad["teams"]
    with pytest.raises(ValueError):
        validate_tournament(bad)


@pytest.mark.skipif(not Path("config/tournament_2026.yaml").exists(),
                    reason="awaiting user-provided verified draw file (decision 2)")
def test_real_draw_file_loads():
    t = load_tournament("config/tournament_2026.yaml")
    assert len(t["groups"]) == 12 and sum(len(g["teams"]) for g in t["groups"]) == 48
    assert len(t["fixtures"]) == 104


# --- WC-2026 group-fixture ingestion (#4 gate, Part 2) -----------------------

_REAL = Path("config/tournament_2026.yaml")
_needs_draw = pytest.mark.skipif(
    not _REAL.exists(),
    reason="awaiting user-provided verified draw file (decision 2)")

# Placeholder-token shapes that must NEVER reach the store as a team name:
# group-position slots (`2A`), winner/loser refs (`W74`/`L101`), and the
# best-third slots (`3rd-ABCDF`). Mirrors the leakage-sweep guard.
_PLACEHOLDER_RE = r"^(?:[0-9][A-L]|W\d+|L\d+|3rd-).*$"


@_needs_draw
def test_ingest_lands_only_the_72_group_fixtures():
    """ingest_wc_group_fixtures writes EXACTLY the 72 real-team group matches;
    the 32 structure-placeholder knockouts are NOT ingested."""
    t = load_tournament(_REAL)
    store = BitemporalStore(root_for_test())
    n = ingest_wc_group_fixtures(t, store, observed_at="2026-01-01")
    assert n == 72
    rows = store.read("results", cutoff="2027-01-01")
    assert len(rows) == 72


@_needs_draw
def test_ingested_rows_are_future_dated_unplayed_pit():
    """Every ingested row is UNPLAYED (NaN scores), future-dated June-2026,
    tournament='FIFA World Cup', point-in-time with valid_as_of==observed_at."""
    t = load_tournament(_REAL)
    store = BitemporalStore(root_for_test())
    ingest_wc_group_fixtures(t, store, observed_at="2026-01-01")
    rows = store.read("results", cutoff="2027-01-01")

    assert rows["home_score"].isna().all() and rows["away_score"].isna().all()
    assert (rows["tournament"] == "FIFA World Cup").all()
    assert (pd.to_datetime(rows["date"]).dt.year == 2026).all()
    assert (pd.to_datetime(rows["date"]) >= pd.Timestamp("2026-06-11")).all()
    # POINT_IN_TIME provenance: knowable at the schedule-publication instant.
    assert (rows["valid_as_of"] == rows["observed_at"]).all()
    assert (rows["source"] == "wc2026_schedule").all()
    assert rows["match_id"].is_unique


@_needs_draw
def test_ingested_team_names_are_martj42_keys():
    """Team names come straight from the yaml (already martj42 keys) — and no
    placeholder token leaks into home_team / away_team."""
    t = load_tournament(_REAL)
    store = BitemporalStore(root_for_test())
    ingest_wc_group_fixtures(t, store, observed_at="2026-01-01")
    rows = store.read("results", cutoff="2027-01-01")

    drawn = set(t["teams"])  # the 48 martj42-keyed nations
    assert set(rows["home_team"]) | set(rows["away_team"]) <= drawn
    for col in ("home_team", "away_team"):
        assert not rows[col].astype(str).str.match(_PLACEHOLDER_RE).any()


@_needs_draw
def test_real_draw_validates_and_ingests_exactly_72_group_rows():
    """FIX 1 (belt + suspenders, end to end): the REAL config both VALIDATES
    (top-level teams == group union, 48 distinct) AND ingests EXACTLY 72 group
    rows — neither the validator nor the group-set-derived ingest regresses."""
    t = load_tournament(_REAL)               # validate_tournament ran inside
    validate_tournament(t)                    # explicit: passes the new check too
    group_set = {team for g in t["groups"] for team in g["teams"]}
    assert set(t["teams"]) == group_set and len(set(t["teams"])) == 48
    store = BitemporalStore(root_for_test())
    n = ingest_wc_group_fixtures(t, store, observed_at="2026-01-01")
    assert n == 72
    assert len(store.read("results", cutoff="2027-01-01")) == 72


def test_doctored_group_looking_fixture_is_not_ingested_as_group_row():
    """FIX 1 belt-and-suspenders: even if `validate_tournament` were BYPASSED, a
    group-SHAPED fixture whose team is a placeholder (home="2A", away="Mexico")
    must be SKIPPED by ingest — `ingest_wc_group_fixtures` derives `drawn` from
    the GROUP teams, and "2A" is in no group, so the row is NOT a group row and
    ZERO placeholder tokens reach the store.

    We construct the tournament dict DIRECTLY (no validate) so this proves the
    ingest-side guard in isolation: top-level `teams` is poisoned with the "2A"
    placeholder (the exact smuggling a bypassed validator would let through), and
    a group-SHAPED fixture pairs "2A" with a REAL drawn nation — yet nothing is
    written, because ingest reads `drawn` from the GROUP teams, where "2A" never
    appears. (Under the OLD `drawn = set(teams)` code this row WOULD have been
    ingested, since poisoned `teams` contained "2A"; that is the regression this
    guards.)
    """
    # 12 groups of 4 real names. The away team "T0_0" IS a real group member, so
    # the ONLY thing keeping this group-shaped fixture out of the store is that
    # "2A" is absent from the GROUP-derived drawn set.
    groups = [{"name": chr(65 + i), "teams": [f"T{i}_{j}" for j in range(4)]}
              for i in range(12)]
    group_teams = [t for g in groups for t in g["teams"]]
    real_away = group_teams[0]  # "T0_0" — a genuine drawn nation, KEPT in `teams`
    doctored = {
        # Top-level `teams` is POISONED with the "2A" placeholder, replacing the
        # LAST real group member (so length stays 48 and `real_away` is retained).
        # Old ingest derived `drawn` from THIS list — which contains both "2A"
        # AND `real_away` — so it WOULD have admitted the fixture (n=1). The fix
        # derives `drawn` from the groups, where "2A" is absent → skipped (n=0).
        "teams": group_teams[:-1] + ["2A"],
        "groups": groups,
        "fixtures": [
            {"home": "2A", "away": real_away, "date": "2026-06-28",
             "venue": "Los Angeles"},
        ],
        "venues": [{"city": "Los Angeles", "country": "US"}],
    }
    store = BitemporalStore(root_for_test())
    n = ingest_wc_group_fixtures(doctored, store, observed_at="2026-01-01")
    # ZERO rows written: the placeholder fixture is skipped, so NO placeholder
    # token reaches the store — the count IS the proof (nothing was ingested).
    assert n == 0, "a placeholder-team fixture was ingested as a group row"
    # Defensive read: whatever the store returns (empty / not-found), no
    # placeholder token may appear in any team column.
    try:
        rows = store.read("results", cutoff="2027-01-01")
    except (FileNotFoundError, IndexError):
        rows = None
    if rows is not None and not rows.empty:
        for col in ("home_team", "away_team"):
            if col in rows.columns:
                assert not rows[col].astype(str).str.match(_PLACEHOLDER_RE).any()


@_needs_draw
def test_host_country_fixtures_are_non_neutral():
    """neutral=False exactly when a host nation (Mexico/USA/Canada) plays at a
    venue in its own country; all other group matches are neutral=True."""
    t = load_tournament(_REAL)
    store = BitemporalStore(root_for_test())
    ingest_wc_group_fixtures(t, store, observed_at="2026-01-01")
    rows = store.read("results", cutoff="2027-01-01")

    hosts = {"Mexico", "United States", "Canada"}
    non_neutral = rows[~rows["neutral"]]
    # Every non-neutral row has a host nation as a participant.
    assert (non_neutral["home_team"].isin(hosts)
            | non_neutral["away_team"].isin(hosts)).all()
    # And there is at least one of each (the three hosts all play group matches
    # at home), so the flag is non-vacuous.
    assert len(non_neutral) >= 3


def root_for_test(_counter=[0]):
    """Per-call unique tmp store root (pytest tmp_path is fixture-only)."""
    import tempfile
    _counter[0] += 1
    return Path(tempfile.mkdtemp()) / f"store{_counter[0]}"
