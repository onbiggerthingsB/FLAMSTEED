import pandas as pd

from wcmodel.data.sources.results import join_shootout_winners


def test_join_shootout_winners_adds_winner_override_on_triple():
    # Normalized results (a level KO + a non-level group game).
    results = pd.DataFrame([
        {"match_id": "k1", "date": pd.Timestamp("2026-06-28"), "home_team": "Brazil",
         "away_team": "Argentina", "home_score": 1, "away_score": 1,
         "tournament": "FIFA World Cup", "neutral": True, "city": "East Rutherford",
         "country": "United States"},
        {"match_id": "g1", "date": pd.Timestamp("2026-06-11"), "home_team": "France",
         "away_team": "Mexico", "home_score": 2, "away_score": 0,
         "tournament": "FIFA World Cup", "neutral": True, "city": "Inglewood",
         "country": "United States"},
    ])
    # martj42 shootouts.csv shape: date, home_team, away_team, winner.
    shootouts = pd.DataFrame([
        {"date": pd.Timestamp("2026-06-28"), "home_team": "Brazil",
         "away_team": "Argentina", "winner": "Brazil"},
    ])
    out = join_shootout_winners(results, shootouts)
    # The level KO gets its ACTUAL shootout winner; the group game stays NaN.
    k1 = out[out["match_id"] == "k1"].iloc[0]
    assert k1["winner_override"] == "Brazil"
    g1 = out[out["match_id"] == "g1"].iloc[0]
    assert pd.isna(g1["winner_override"])
    # Row-preserving: no rows dropped/added by the join.
    assert len(out) == len(results)


def test_join_shootout_winners_no_shootouts_is_all_nan():
    results = pd.DataFrame([
        {"match_id": "g1", "date": pd.Timestamp("2026-06-11"), "home_team": "France",
         "away_team": "Mexico", "home_score": 2, "away_score": 0,
         "tournament": "FIFA World Cup", "neutral": True, "city": "Inglewood",
         "country": "United States"},
    ])
    out = join_shootout_winners(results, pd.DataFrame(
        columns=["date", "home_team", "away_team", "winner"]))
    assert "winner_override" in out.columns
    assert out["winner_override"].isna().all()


import pytest


def test_level_pinned_ko_resolves_to_recorded_winner():
    """D3: a level (penalty-decided) pinned KO with a RECORDED winner now resolves to
    the ACTUAL winner — simulate_one NO LONGER fails loud."""
    from tests.sim.test_tournament import (
        tiny_bracket as _tb, _DetRB, _NoDrawRNG, _Cfg, _DET_GROUP, _FINAL_DATE,
        _match_depths,
    )
    from wcmodel.sim.tournament import simulate_one
    br = _tb()
    cfg = _Cfg(max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    # Brazil vs Argentina level 1-1 after ET; the shootout winner (Brazil) is recorded.
    played = {
        "groups": _DET_GROUP,
        "knockout_results": {("Brazil", "Argentina", _FINAL_DATE): (1, 1)},
        "knockout_winners": {("Brazil", "Argentina", _FINAL_DATE): "Brazil"},
        "match_dates": {104: _FINAL_DATE},
    }
    # No RNG is drawn for a pinned KO (the winner is FACT) -> _NoDrawRNG must not raise.
    res = simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg, played=played,
                       depths=_match_depths(br))
    assert res["champion"] == "Brazil"            # the ACTUAL recorded winner


def test_level_pinned_ko_without_recorded_winner_still_fails_loud():
    """The guard is PRESERVED: a level pinned KO with NO recorded winner (genuinely
    missing data) STILL fails loud — the fix only resolves a KNOWN winner."""
    from tests.sim.test_tournament import (
        tiny_bracket as _tb, _DetRB, _NoDrawRNG, _Cfg, _DET_GROUP, _FINAL_DATE,
        _match_depths,
    )
    from wcmodel.sim.tournament import simulate_one
    br = _tb()
    cfg = _Cfg(max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    played = {
        "groups": _DET_GROUP,
        "knockout_results": {("Brazil", "Argentina", _FINAL_DATE): (1, 1)},
        # no "knockout_winners" -> a level KO with missing winner must still raise.
        "match_dates": {104: _FINAL_DATE},
    }
    with pytest.raises(ValueError, match=r"(?i)(shootout|penalty).*winner"):
        simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg, played=played,
                     depths=_match_depths(br))


def test_level_pinned_ko_with_corrupt_winner_fails_loud():
    """D3 corruption guard: a level pinned KO whose recorded ``knockout_winners`` entry
    names a team that is NEITHER participant (a corrupt ``winner_override``) must fail
    loud — the sim refuses to crown a non-participant rather than silently mis-resolve."""
    from tests.sim.test_tournament import (
        tiny_bracket as _tb, _DetRB, _NoDrawRNG, _Cfg, _DET_GROUP, _FINAL_DATE,
        _match_depths,
    )
    from wcmodel.sim.tournament import simulate_one
    br = _tb()
    cfg = _Cfg(max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    played = {
        "groups": _DET_GROUP,
        "knockout_results": {("Brazil", "Argentina", _FINAL_DATE): (1, 1)},
        # Corrupt: the recorded winner is a THIRD team, not Brazil or Argentina.
        "knockout_winners": {("Brazil", "Argentina", _FINAL_DATE): "Croatia"},
        "match_dates": {104: _FINAL_DATE},
    }
    with pytest.raises(ValueError, match=r"(?i)(corrupt|neither)"):
        simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg, played=played,
                     depths=_match_depths(br))
