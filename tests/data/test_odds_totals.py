from wcmodel.data.sources.odds import parse_totals_snapshot

# One Odds-API event with a `totals` market from two bookmakers.
_EVENT = {
    "home_team": "Spain", "away_team": "Croatia", "commence_time": "2024-06-15T16:00:00Z",
    "bookmakers": [
        {"key": "pinnacle", "markets": [{"key": "totals", "outcomes": [
            {"name": "Over", "point": 2.5, "price": 1.95},
            {"name": "Under", "point": 2.5, "price": 1.95}]}]},
        {"key": "bet365", "markets": [{"key": "totals", "outcomes": [
            {"name": "Over", "point": 2.5, "price": 2.05},
            {"name": "Under", "point": 2.5, "price": 1.80}]}]},
    ],
}


def test_parse_totals_snapshot_groups_by_book_and_line():
    out = parse_totals_snapshot(_EVENT)
    assert out["home_team"] == "Spain" and out["away_team"] == "Croatia"
    assert out["books"]["bet365"][2.5] == {"over_odds": 2.05, "under_odds": 1.80}
    assert out["books"]["pinnacle"][2.5] == {"over_odds": 1.95, "under_odds": 1.95}


def test_parse_totals_snapshot_ignores_non_totals_and_partial_lines():
    ev = {"home_team": "A", "away_team": "B", "commence_time": "2024-01-01T00:00:00Z",
          "bookmakers": [{"key": "bet365", "markets": [
              {"key": "h2h", "outcomes": [{"name": "A", "price": 1.5}]},          # not totals -> ignored
              {"key": "totals", "outcomes": [{"name": "Over", "point": 3.5, "price": 2.0}]}]}]}  # no Under
    out = parse_totals_snapshot(ev)
    assert 3.5 not in out["books"].get("bet365", {})    # incomplete line dropped, never half-priced
