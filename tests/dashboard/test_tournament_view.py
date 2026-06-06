import pandas as pd
from wcmodel.dashboard.tournament_view import team_progression, ko_slot_occupants
from wcmodel.dashboard.schema import validate_progression_coherence


def _simresult():
    cols = ["win_group", "advance_from_group", "reach_qf", "reach_sf", "reach_final",
            "champion", "first", "second", "third", "out"]
    prog = pd.DataFrame(
        [[0.55, 0.70, 0.45, 0.30, 0.18, 0.10, 0.55, 0.15, 0.05, 0.25]],
        index=["Brazil"], columns=cols)
    se = prog * 0.0 + 0.002
    class _SR:
        progression = prog
    sr = _SR(); sr.se = se; sr.n_sims = 20000
    return sr


def test_team_progression_pairs_every_prob_with_its_mc_se_and_is_coherent():
    rows = team_progression(_simresult())
    brazil = rows["Brazil"]
    assert brazil["champion"] == {"value": 0.10, "se": 0.002}
    validate_progression_coherence({k: v["value"] for k, v in brazil.items()
                                    if isinstance(v, dict) and "value" in v})


def test_ko_occupants_gap_when_a_qualifying_occupant_has_no_se_companion():
    """FIX D: a qualifying occupant (prob > 0) with NO finite se companion makes the WHOLE
    occupant-list GAP — no naked occupant prob is ever emitted. The back-compat RAW-FLOAT
    placing shape (no se) is exactly that path: it now gaps rather than emit nakedly. (The
    REAL production placing is always {value, se}, so this never fires on production data;
    it's a fail-safe so the gate never sees a naked occupant prob.)"""
    placing = {"Brazil": {"first": 0.55, "second": 0.15}, "Mexico": {"first": 0.30}}
    occ = ko_slot_occupants(slot_source="1A", placing=placing)
    assert isinstance(occ, dict) and occ.get("coverage_gap") is True   # gapped, not a naked list


def test_ko_occupants_consume_value_se_nodes_and_carry_se():
    # the REAL team_progression shape: {first: {value, se}}
    placing = {"Brazil": {"first": {"value": 0.55, "se": 0.003}},
               "Mexico": {"first": {"value": 0.30, "se": 0.004}},
               "Croatia": {"first": {"value": 0.0, "se": 0.0}},      # 0 prob -> excluded
               "Japan": {}}                                          # no placing -> excluded
    occ = ko_slot_occupants(slot_source="1A", placing=placing)
    assert occ[0] == {"team": "Brazil", "prob": 0.55, "se": 0.003}   # value extracted, se carried, most-likely first
    assert {"team": "Mexico", "prob": 0.30, "se": 0.004} in occ
    assert all(o["team"] not in ("Croatia", "Japan") for o in occ)   # 0-prob + missing excluded
