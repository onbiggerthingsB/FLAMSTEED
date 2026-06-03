import json

import pandas as pd

from wcmodel.data.sources.statsbomb import normalize_match_xg


def _raw():
    return json.load(open("fixtures/statsbomb_matches_sample.json"))


def test_xg_is_point_in_time_versioned():
    raw = _raw()
    out = normalize_match_xg(raw, source_version="v-pinned")
    assert (out["valid_as_of"] == out["observed_at"]).all()
    assert (out["source_version"] == "v-pinned").all()
    assert out["xg_covered"].all()


def test_valid_as_of_equals_match_date():
    out = normalize_match_xg(_raw(), source_version="v-pinned")
    assert (out["valid_as_of"] == out["match_date"]).all()
    assert (out["observed_at"] == out["match_date"]).all()


def test_one_row_per_match_team_with_aggregated_xg():
    out = normalize_match_xg(_raw(), source_version="v-pinned")
    # Two matches x two teams each = four match-team xG rows.
    assert len(out) == 4
    assert (out.groupby(["match_id", "team"]).size() == 1).all()
    # Brazil's shot xG in match 3857289 sums to 0.76+0.33+0.18+0.29 = 1.56.
    bra = out[(out.match_id == 3857289) & (out.team == "Brazil")].iloc[0]
    assert bra["xg"] == 0.76 + 0.33 + 0.18 + 0.29


def test_xg_never_imputed_uncovered_match_is_absent_not_zero():
    # A covered match with NO shot data for a team must NOT manufacture xG=0;
    # the row is dropped (absent / NULL), never imputed.
    raw = _raw()
    raw.append({
        "match_id": 9999999,
        "match_date": "2022-12-10",
        "home_team": {"home_team_name": "Morocco"},
        "away_team": {"away_team_name": "Portugal"},
        "shots": [],  # no shot-level xG available
    })
    out = normalize_match_xg(raw, source_version="v-pinned")
    assert 9999999 not in set(out["match_id"])  # absent, not xg=0
    assert out["xg"].notna().all()  # nothing imputed


def test_normalize_is_pure_no_network(monkeypatch):
    import wcmodel.data.sources.statsbomb as m
    # Guard: the pure transform must never reach into the network client.
    monkeypatch.setattr(
        m, "sb",
        type("Blocked", (), {"__getattr__": staticmethod(
            lambda name: (_ for _ in ()).throw(AssertionError("no network")))})(),
    )
    normalize_match_xg(_raw(), source_version="v-pinned")
