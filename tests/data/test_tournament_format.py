import copy
import pytest

from wcmodel.data.tournament import (HOST_COUNTRY_BY_TEAM, load_tournament,
                                     tournament_format, validate_tournament)

_REAL = "config/tournament_2026.yaml"

AC_FORMAT = {"n_groups": 6, "teams_per_group": 4, "per_group_advance": 2,
             "best_thirds": 4, "third_place_match": False,
             "tiebreak_order": "afc_2027",
             "assignment_table": "third_place_assignment_ac2027.json",
             "competition_name": "AFC Asian Cup", "source_tag": "ac2027_schedule",
             "hosts": {"Saudi Arabia": "SA"}, "ko_host_advantage": True}


def _ac_min():
    """Minimal valid AC-2027-shaped dict: 36 group fixtures + 15 KO (no 3rd-place)."""
    letters = "ABCDEF"
    groups = [{"name": g, "teams": [f"Team{g}{i}" for i in range(4)]}
              for g in letters]
    teams = [t for g in groups for t in g["teams"]]
    fixtures = []
    for g in letters:
        t = [f"Team{g}{i}" for i in range(4)]
        for a, b in [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]:
            fixtures.append({"home": t[a], "away": t[b], "date": "2027-01-08",
                             "group": g, "round": "Matchday", "venue": "Riyadh"})
    ko = ([(49, "1A", "3rd-CDE", "Round of 16"), (50, "1B", "3rd-ADF", "Round of 16"),
           (51, "1C", "3rd-ABF", "Round of 16"), (52, "1D", "3rd-ABC", "Round of 16"),
           (53, "2A", "2C", "Round of 16"), (54, "1E", "2D", "Round of 16"),
           (55, "1F", "2B", "Round of 16"), (56, "2E", "2F", "Round of 16"),
           (57, "W49", "W53", "Quarter-final"), (58, "W50", "W54", "Quarter-final"),
           (59, "W51", "W55", "Quarter-final"), (60, "W52", "W56", "Quarter-final"),
           (61, "W57", "W58", "Semi-final"), (62, "W59", "W60", "Semi-final"),
           (63, "W61", "W62", "Final")])
    for m, h, a, r in ko:
        fixtures.append({"match": m, "home": h, "away": a, "round": r,
                         "date": "2027-01-25", "venue": "Riyadh"})
    return {"format": dict(AC_FORMAT), "teams": teams, "groups": groups,
            "fixtures": fixtures,
            "bracket": {"paths": [{"name": "left"}, {"name": "right"}]},
            "venues": [{"name": "X", "city": "Riyadh", "country": "SA"}]}


def test_no_format_block_yields_wc2026_defaults():
    fmt = tournament_format({"teams": []})
    assert fmt["n_groups"] == 12 and fmt["best_thirds"] == 8
    assert fmt["third_place_match"] is True and fmt["ko_host_advantage"] is False
    assert fmt["hosts"] == HOST_COUNTRY_BY_TEAM and fmt["hosts"] is not HOST_COUNTRY_BY_TEAM
    assert fmt["source_tag"] == "wc2026_schedule"


def test_real_wc_draw_loads_unchanged():
    t = load_tournament(_REAL)
    assert tournament_format(t)["n_groups"] == 12


def test_format_null_rejected():
    with pytest.raises(ValueError, match="format must be a mapping"):
        tournament_format({"format": None})


def test_format_missing_key_rejected():
    d = _ac_min()
    del d["format"]["third_place_match"]
    with pytest.raises(ValueError, match="format block missing"):
        validate_tournament(d)


def test_ac_shape_validates_15_ko_no_third_place():
    out = validate_tournament(_ac_min())
    assert tournament_format(out)["third_place_match"] is False


def test_ac_wrong_ko_count_rejected():
    d = _ac_min()
    d["fixtures"] = d["fixtures"][:-1]          # drop the Final -> 14 KO
    with pytest.raises(ValueError, match="knockout fixture count"):
        validate_tournament(d)


def test_legacy_valid_min_still_accepted():
    """The pre-format minimal WC structure (104 fixtures, no match keys) must
    keep validating exactly as before — the split check is format-gated."""
    from tests.data.test_tournament import _valid_min
    validate_tournament(_valid_min())
