"""Format-generalization tests for the bracket parser (Task 1).

``test_bracket.py`` pins the WC-2026 behaviour and must stay green untouched;
this file pins the generalizations that let a non-WC edition (AFC Asian Cup
2027: 6 groups, best-4 thirds, no third-place match) parse through the same
code path:

* third-slot grammar ``3rd-([A-Z]{2,})`` — 5 letters (WC) *and* 3 letters (AC);
* a ``3rd-``-prefixed ref that does NOT match is a LOUD failure, never a
  silently-dropped slot (a dropped slot yields a structurally wrong bracket);
* the explicit ``group`` key on a group fixture is preferred over the
  team->group lookup (both YAMLs carry it; WC's 72 agree with the lookup);
* an unrecognised round label names itself and its match instead of raising a
  bare ``KeyError``;
* the official AFC plural round labels are accepted — an ENUMERATED, CLOSED
  vocabulary, no fuzzy matching.
"""
import pytest

from wcmodel.sim.bracket import build_bracket


def _mini() -> dict:
    """Smallest bracket-shaped dict. Fixture index map (tests index it directly):
    0, 1 = group fixtures (no ``match``); 2 = match 1; 3 = match 2."""
    return {
        "groups": [{"name": "A", "teams": ["A1", "A2"]},
                   {"name": "B", "teams": ["B1", "B2"]}],
        "fixtures": [
            {"home": "A1", "away": "A2", "group": "A", "round": "Matchday 1"},
            {"home": "B1", "away": "B2", "group": "B", "round": "Matchday 1"},
            {"match": 1, "home": "1A", "away": "2B", "round": "Semi-final"},
            {"match": 2, "home": "W1", "away": "1B", "round": "Final"},
        ],
    }


# --- third-slot grammar ------------------------------------------------------

def test_third_slot_accepts_three_letter_ac_style_ref():
    t = _mini()
    t["fixtures"][2]["away"] = "3rd-CDE"
    b = build_bracket(t)
    assert b.third_place_slots == {1: frozenset("CDE")}


def test_third_slot_still_accepts_five_letter_wc_style_ref():
    t = _mini()
    t["fixtures"][2]["away"] = "3rd-ABCDF"
    b = build_bracket(t)
    assert b.third_place_slots == {1: frozenset("ABCDF")}


def test_third_slot_accepts_letters_beyond_L():
    """WC-2026 groups stop at L; the grammar must not hard-code that ceiling."""
    t = _mini()
    t["fixtures"][2]["away"] = "3rd-MNZ"
    b = build_bracket(t)
    assert b.third_place_slots == {1: frozenset("MNZ")}


@pytest.mark.parametrize("bad", ["3rd-A", "3rd-", "3rd-abc", "3rd-A1C"])
def test_malformed_third_ref_raises_loudly(bad):
    """A ``3rd-`` ref that does not parse must NOT be silently dropped."""
    t = _mini()
    t["fixtures"][2]["away"] = bad
    with pytest.raises(ValueError, match="unresolved third-place slot"):
        build_bracket(t)


def test_malformed_third_ref_error_names_ref_and_match():
    t = _mini()
    t["fixtures"][3]["home"] = "3rd-Q"
    with pytest.raises(ValueError) as exc:
        build_bracket(t)
    assert "3rd-Q" in str(exc.value) and "2" in str(exc.value)


def test_non_third_refs_are_untouched():
    """``W``/``L``/``1A`` feeder refs must not trip the third-slot check."""
    t = _mini()
    t["fixtures"][3]["home"], t["fixtures"][3]["away"] = "L1", "W1"
    b = build_bracket(t)
    assert b.third_place_slots == {} and b.knockout_feeders[2] == ("L1", "W1")


# --- group-key preference ----------------------------------------------------

def test_group_key_preferred_over_team_lookup():
    """The declared ``group`` key wins, so a group fixture parses even when its
    teams are not resolvable through the group->teams map."""
    t = _mini()
    t["fixtures"][0]["home"] = "NotInAnyGroup"
    b = build_bracket(t)
    assert b.group_fixtures["A"] == [("NotInAnyGroup", "A2")]


def test_group_key_absent_falls_back_to_team_lookup():
    t = _mini()
    del t["fixtures"][0]["group"]
    b = build_bracket(t)
    assert b.group_fixtures["A"] == [("A1", "A2")]


# --- round labels ------------------------------------------------------------

def test_unknown_round_raises_named_error():
    t = _mini()
    t["fixtures"][2]["round"] = "Play-off"
    with pytest.raises(ValueError, match="unknown round"):
        build_bracket(t)


def test_unknown_round_error_names_label_and_match():
    t = _mini()
    t["fixtures"][3]["round"] = "Repechage"
    with pytest.raises(ValueError) as exc:
        build_bracket(t)
    assert "Repechage" in str(exc.value) and "2" in str(exc.value)


def test_afc_plural_round_labels_accepted():
    t = _mini()
    t["fixtures"][2]["round"] = "Round of 16"
    t["fixtures"][3]["round"] = "Quarter-Finals"
    b = build_bracket(t)
    assert b.match_round[2] == "QF"


def test_afc_lowercase_plural_round_labels_accepted():
    t = _mini()
    t["fixtures"][2]["round"] = "Semi-finals"
    t["fixtures"][3]["round"] = "Quarter-finals"
    b = build_bracket(t)
    assert b.match_round[1] == "SF" and b.match_round[2] == "QF"


def test_singular_wc_round_labels_still_accepted():
    t = _mini()
    t["fixtures"][2]["round"] = "Quarter-final"
    t["fixtures"][3]["round"] = "Semi-final"
    b = build_bracket(t)
    assert b.match_round[1] == "QF" and b.match_round[2] == "SF"
