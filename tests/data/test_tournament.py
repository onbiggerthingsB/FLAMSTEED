import pytest
from pathlib import Path
from wcmodel.data.tournament import validate_tournament, load_tournament


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


@pytest.mark.skipif(not Path("config/tournament_2026.yaml").exists(),
                    reason="awaiting user-provided verified draw file (decision 2)")
def test_real_draw_file_loads():
    t = load_tournament("config/tournament_2026.yaml")
    assert len(t["groups"]) == 12 and sum(len(g["teams"]) for g in t["groups"]) == 48
    assert len(t["fixtures"]) == 104
