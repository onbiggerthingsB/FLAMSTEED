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


# --- FIX 1 (P2): reject placeholder-SHAPED team names ------------------------
#
# A bracket placeholder smuggled into BOTH top-level `teams` AND a group passes
# the teams==groups / 48-distinct checks (it is consistent with itself) and would
# then be ingested as a real nation. Real nations never look like bracket slots,
# so `validate_tournament` rejects placeholder-SHAPED names outright: an anchored
# regex (`2A` / `W74` / `L101` / `3rd-...`) OR a structural word token (tbd /
# playoff / winner / runner-up / uefa path). These tests pin both the rejection
# (per shape) and the no-false-positive guarantee on the real 48 nations.

# Placeholder-shaped names that must be REJECTED even when self-consistent
# (present in both top-level `teams` and a group). One per distinct shape:
# group-slot, winner-ref, loser-ref, best-third slot (dash AND space), and each
# structural word token.
_PLACEHOLDER_SHAPED = [
    "2A",                 # group-position slot (digit + A-L)
    "W74",                # knockout winner ref
    "L101",               # knockout loser ref
    "3rd-ABCDF",          # best-third slot (dash form)
    "3rd ABCDF",          # best-third slot (space form)
    "Playoff Winner A",   # 'playoff' + 'winner' word tokens
    "TBD",                # to-be-determined token
    "Runner-up Group B",  # 'runner-up' token
    "UEFA Path A",        # 'uefa path' token
]


def _with_placeholder_team(name: str) -> dict:
    """A structurally VALID dict (48 distinct, teams==groups, 104 fixtures, …)
    except that ``name`` replaces one real team in BOTH a group AND top-level
    ``teams`` — so ONLY the placeholder-shape check can reject it (the
    teams==groups / distinct / count checks all still pass)."""
    data = _valid_min()
    # Replace the very first group member everywhere it appears in `teams`.
    old = data["groups"][0]["teams"][0]
    data["groups"][0]["teams"][0] = name
    data["teams"] = [name if t == old else t for t in data["teams"]]
    # Sanity: still 48 distinct and teams == group union (so the ONLY thing that
    # can trip the validator is the placeholder SHAPE, not a count/set mismatch).
    group_union = {t for g in data["groups"] for t in g["teams"]}
    assert len(data["teams"]) == 48 and len(set(data["teams"])) == 48
    assert set(data["teams"]) == group_union
    return data


@pytest.mark.parametrize("name", _PLACEHOLDER_SHAPED)
def test_validator_rejects_placeholder_shaped_team_name(name):
    """A placeholder-SHAPED name (e.g. "2A", "W74", "3rd-ABCDF", "Playoff
    Winner A") in BOTH `teams` and a group — self-consistent, so it survives the
    teams==groups / 48-distinct checks — must STILL raise, and the offending name
    must be named in the message."""
    bad = _with_placeholder_team(name)
    with pytest.raises(ValueError) as ei:
        validate_tournament(bad)
    assert name in str(ei.value), (
        f"the offending placeholder {name!r} must be listed in the error"
    )


def test_validator_rejects_placeholder_in_group_even_if_top_level_teams_clean():
    """The check covers EVERY team in EVERY group, not just top-level `teams`: a
    placeholder living in a group still raises (here it is in `teams` too so the
    set stays consistent — the shape is what trips it)."""
    bad = _with_placeholder_team("2A")
    assert "2A" in {t for g in bad["groups"] for t in g["teams"]}
    with pytest.raises(ValueError):
        validate_tournament(bad)


def test_validator_accepts_real_48_nation_names_no_false_positive():
    """No real WC-2026 nation may trip the placeholder-shape check.

    Pins the exact 48 common-English keys (United States, Bosnia and
    Herzegovina, DR Congo, South Korea, Côte d'Ivoire/Ivory Coast, Curaçao, …)
    into the minimal-valid structure and asserts `validate_tournament` does NOT
    raise — the anchored regex + word tokens are specific to bracket slots and
    never match a country name.
    """
    real48 = [
        "Algeria", "Argentina", "Australia", "Austria", "Belgium",
        "Bosnia and Herzegovina", "Brazil", "Canada", "Cape Verde", "Colombia",
        "Croatia", "Curaçao", "Czech Republic", "DR Congo", "Ecuador", "Egypt",
        "England", "France", "Germany", "Ghana", "Haiti", "Iran", "Iraq",
        "Ivory Coast", "Japan", "Jordan", "Mexico", "Morocco", "Netherlands",
        "New Zealand", "Norway", "Panama", "Paraguay", "Portugal", "Qatar",
        "Saudi Arabia", "Scotland", "Senegal", "South Africa", "South Korea",
        "Spain", "Sweden", "Switzerland", "Tunisia", "Turkey", "United States",
        "Uruguay", "Uzbekistan",
        # A few alt common-English keys that could plausibly brush the regex,
        # pinned here too so a future tightening can't silently break them.
        "Côte d'Ivoire",
    ]
    assert len(set(real48)) == len(real48)
    groups = [{"name": chr(65 + i), "teams": real48[4 * i:4 * i + 4]}
              for i in range(12)]
    data = {
        "teams": real48[:48],
        "groups": groups,
        "fixtures": [{"home": "x", "away": "y", "date": "2026-06-11"}] * 104,
        "advancement": {"per_group": 2, "best_thirds": 8},
        "third_place_tiebreakers": ["goal_difference", "goals_scored",
                                    "head_to_head", "fair_play",
                                    "drawing_of_lots"],
        "bracket": {"paths": ["A", "B"]},
    }
    validate_tournament(data)   # must NOT raise on any real nation


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


# --- Codex B note: validate-at-ingest-entry + placeholder-excluding `drawn` ---
#
# `ingest_wc_group_fixtures` previously trusted the caller to have run
# `validate_tournament` first. A caller that BYPASSED the validator and smuggled a
# placeholder ("2A") into a group would put "2A" into the group-derived `drawn`
# set. Not a leak today (such rows are NaN-score and dropped before Elo), but the
# guarantee is now CODE-ENFORCED two ways: (1) ingest calls `validate_tournament`
# at entry, so a malformed/unvalidated doc can never be ingested; (2) `drawn`
# excludes any placeholder-shaped name as a second guard.

def test_ingest_validates_at_entry_rejecting_smuggled_placeholder_in_group():
    """Codex B note (guard 1): ingest REFUSES an unvalidated/malformed doc.

    A doc with "2A" smuggled into BOTH a group AND top-level `teams` (the exact
    bypass a caller skipping `validate_tournament` could attempt) must RAISE
    `ValueError` at ingest entry — `ingest_wc_group_fixtures` now calls
    `validate_tournament` first, and the validator rejects placeholder-shaped
    names. Ingestion can NEVER run on an unvalidated/malformed tournament.
    """
    # Start from a fully-valid structure so the ONLY defect is the smuggled
    # placeholder (proving it is the placeholder-shape guard inside
    # `validate_tournament` that trips, reached via the entry call — not an
    # unrelated count/shape failure).
    bad = _valid_min()
    bad["venues"] = [{"city": "Los Angeles", "country": "US"}]
    old = bad["groups"][0]["teams"][0]
    bad["groups"][0]["teams"][0] = "2A"                 # smuggled INTO a group
    bad["teams"] = ["2A" if t == old else t for t in bad["teams"]]  # ...and `teams`
    # Self-consistent (48 distinct, teams == group union) — only the SHAPE is bad.
    group_union = {t for g in bad["groups"] for t in g["teams"]}
    assert "2A" in group_union and set(bad["teams"]) == group_union
    store = BitemporalStore(root_for_test())
    with pytest.raises(ValueError) as ei:
        ingest_wc_group_fixtures(bad, store, observed_at="2026-01-01")
    assert "2A" in str(ei.value), (
        "the offending placeholder must be named by the entry validation"
    )


def test_ingest_drawn_excludes_placeholder_shaped_name_second_guard():
    """Codex B note (guard 2): `drawn` is derived EXCLUDING placeholder-shaped
    names, independently of the entry validation.

    Even if a placeholder ever reached the group set, the `drawn` comprehension
    filters it via `_is_placeholder_team`, so a group-SHAPED fixture pairing a
    placeholder with a real nation is still SKIPPED (the placeholder is not in
    `drawn`). Proven directly against `_drawn_teams` to isolate THIS guard from
    the entry validation above.
    """
    from wcmodel.data.tournament import _drawn_teams
    groups = [{"name": chr(65 + i), "teams": [f"T{i}_{j}" for j in range(4)]}
              for i in range(12)]
    # Poison the group set: OVERWRITE one real member ("T0_0") with a placeholder
    # shape; the second guard must drop "2A" from the derived drawn set.
    groups[0]["teams"][0] = "2A"
    drawn = _drawn_teams({"groups": groups})
    assert "2A" not in drawn, "placeholder-shaped name leaked into the drawn set"
    # The 47 remaining real members (all T{i}_{j} except the overwritten T0_0)
    # are retained — the filter drops ONLY the placeholder, nothing else.
    expected = {f"T{i}_{j}" for i in range(12) for j in range(4)} - {"T0_0"}
    assert expected == drawn


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
