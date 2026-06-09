"""Both-sides stale-line guard must require FULL market coverage.

A soft book that prices only a subset of a market's outcomes (e.g. 2 of a 3-way
h2h) is NOT a stale-de-vig signal: you can't arb a one-sided book against the
sharp fair. The guard should only fire when the book covers the entire market
width (len(rows) >= len(fair)) and is +EV on every leg.
"""
from wcmodel.value.scanner import scan
from wcmodel.value.types import ValueConfig
from wcmodel.config import load_config

NOW = "2026-06-08T23:10:00Z"
FRESH = "2026-06-08T23:08:00Z"
C = ValueConfig.from_config(load_config())


def _event_two_of_three():
    """Sharp prices a full 3-way h2h; soft (betmgm) prices only 2 of 3 legs,
    BOTH +EV vs the sharp fair. Those two legs must remain bettable (the
    book covers 2 < 3 outcomes, so it is NOT both-sides stale)."""
    return {
        "id": "evt_subset",
        "home_team": "A",
        "away_team": "B",
        "commence_time": "2026-06-15T18:00:00Z",
        "bookmakers": [
            {
                "key": "pinnacle",
                "last_update": FRESH,
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "A", "price": 2.10},
                        {"name": "Draw", "price": 3.40},
                        {"name": "B", "price": 3.60},
                    ]},
                ],
            },
            {
                "key": "betmgm",
                "last_update": FRESH,
                "markets": [
                    # only 2 of 3 legs priced, both +EV vs sharp fair
                    {"key": "h2h", "outcomes": [
                        {"name": "A", "price": 2.30},
                        {"name": "Draw", "price": 3.75},
                    ]},
                ],
            },
        ],
    }


def test_two_of_three_subset_not_flagged_both_sides():
    res = scan([_event_two_of_three()], cfg=C, now=NOW)
    sides = {b["side"] for b in res["bettable"]}
    assert sides == {"A", "Draw"}, res
    for b in res["bettable"]:
        assert "both_sides" not in b["flags"]
        assert b["bettable"] is True
    # neither leg landed in filtered for a both_sides reason
    for f in res["filtered"]:
        assert "both_sides" not in f["flags"], f


def test_full_three_way_stale_still_fires():
    """True positive: soft book +EV on ALL 3 legs (3 == len(fair)) IS stale."""
    ev = {
        "id": "evt_full3", "home_team": "A", "away_team": "B",
        "commence_time": "2026-06-15T18:00:00Z",
        "bookmakers": [
            {"key": "pinnacle", "last_update": FRESH, "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "A", "price": 2.10},
                    {"name": "Draw", "price": 3.40},
                    {"name": "B", "price": 3.60},
                ]}]},
            {"key": "betmgm", "last_update": FRESH, "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "A", "price": 2.30},
                    {"name": "Draw", "price": 3.75},
                    {"name": "B", "price": 4.10},
                ]}]},
        ],
    }
    res = scan([ev], cfg=C, now=NOW)
    assert res["bettable"] == []
    assert {f["side"] for f in res["filtered"]} == {"A", "Draw", "B"}
    for f in res["filtered"]:
        assert "both_sides" in f["flags"], f


def test_two_way_totals_stale_still_fires():
    """True positive: soft book +EV on BOTH Over/Under (2 == len(fair)) IS stale."""
    ev = {
        "id": "evt_tot2", "home_team": "A", "away_team": "B",
        "commence_time": "2026-06-15T18:00:00Z",
        "bookmakers": [
            {"key": "pinnacle", "last_update": FRESH, "markets": [
                {"key": "totals", "outcomes": [
                    {"name": "Over", "price": 1.95, "point": 2.5},
                    {"name": "Under", "price": 1.95, "point": 2.5},
                ]}]},
            {"key": "betmgm", "last_update": FRESH, "markets": [
                {"key": "totals", "outcomes": [
                    {"name": "Over", "price": 2.10, "point": 2.5},
                    {"name": "Under", "price": 2.10, "point": 2.5},
                ]}]},
        ],
    }
    res = scan([ev], cfg=C, now=NOW)
    assert res["bettable"] == []
    assert {f["side"] for f in res["filtered"]} == {"Over", "Under"}
    for f in res["filtered"]:
        assert "both_sides" in f["flags"], f
