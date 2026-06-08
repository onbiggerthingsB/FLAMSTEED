import pytest
from wcmodel.markets.totals_edge import totals_edges


def test_totals_edges_flags_positive_ev_only():
    model = {2.5: {"over": 0.60, "under": 0.40}}
    book = {2.5: {"over_odds": 2.00, "under_odds": 1.80}}
    # over: 0.60*2.00 - 1 = +0.20 (bet); under: 0.40*1.80 - 1 = -0.28 (no bet)
    picks = totals_edges(model, book, edge_threshold=0.03, se=0.0)
    assert len(picks) == 1
    p = picks[0]
    assert (p["line"], p["side"]) == (2.5, "over")
    assert p["edge"] == pytest.approx(0.20)
    assert p["stake"] > 0.0


def test_totals_edges_respects_threshold_and_missing_lines():
    model = {2.5: {"over": 0.52, "under": 0.48}, 1.5: {"over": 0.7, "under": 0.3}}
    book = {2.5: {"over_odds": 2.00, "under_odds": 1.90}}   # 1.5 has no book line
    # over 2.5: 0.52*2.00-1 = +0.04 > 0.03 -> bet; under 2.5: 0.48*1.90-1=-0.088 -> no; 1.5: no book -> skip
    picks = totals_edges(model, book, edge_threshold=0.03, se=0.0)
    assert [(p["line"], p["side"]) for p in picks] == [(2.5, "over")]


def test_totals_edges_uncertainty_shrink_can_suppress_a_thin_edge():
    model = {2.5: {"over": 0.52, "under": 0.48}}
    book = {2.5: {"over_odds": 2.00, "under_odds": 1.90}}   # raw over edge +0.04
    # a large se shrinks the effective edge below threshold -> no bet
    picks = totals_edges(model, book, edge_threshold=0.03, se=0.20)
    assert picks == []
