import math
from wcmodel.value.scanner import sharp_fair_probs, _kelly_stake, _market_outcomes

def _event():
    return {"home_team": "A", "away_team": "B", "commence_time": "2026-06-15T18:00:00Z",
        "bookmakers": [
          {"key": "pinnacle", "last_update": "2026-06-08T23:00:00Z", "markets": [
            {"key": "h2h", "outcomes": [{"name":"A","price":2.10},{"name":"Draw","price":3.40},{"name":"B","price":3.60}]}]},
          {"key": "betmgm", "last_update": "2026-06-08T23:00:00Z", "markets": [
            {"key": "h2h", "outcomes": [{"name":"A","price":2.05},{"name":"Draw","price":3.30},{"name":"B","price":4.20}]}]}]}

def test_sharp_fair_probs_devig_sums_to_one():
    fair = sharp_fair_probs(_event(), market="h2h", line=None, sharp="pinnacle")
    assert fair is not None
    assert math.isclose(sum(fair.values()), 1.0, abs_tol=1e-9)
    assert 0.40 < fair["A"] < 0.50            # ~ de-vigged favorite

def test_sharp_absent_returns_none():
    ev = _event(); ev["bookmakers"] = [b for b in ev["bookmakers"] if b["key"] != "pinnacle"]
    assert sharp_fair_probs(ev, market="h2h", line=None, sharp="pinnacle") is None

def test_kelly_stake_is_quarter_kelly():
    # full kelly = edge/(odds-1); quarter = 0.25 * that
    assert math.isclose(_kelly_stake(edge=0.08, odds=2.70, fraction=0.25),
                        0.25 * 0.08 / 1.70, rel_tol=1e-9)
    assert _kelly_stake(edge=-0.01, odds=2.0, fraction=0.25) == 0.0     # never negative

def test_market_outcomes_totals_requires_line():
    # explicit line contract: collapsing all totals lines into one dict is a
    # footgun, so totals with line=None returns None rather than silently
    # keeping only the last Over/Under priced.
    book = {"markets": [{"key": "totals", "outcomes": [
        {"name": "Over", "price": 1.90, "point": 2.5},
        {"name": "Under", "price": 1.95, "point": 2.5},
        {"name": "Over", "price": 2.40, "point": 3.5},
        {"name": "Under", "price": 1.60, "point": 3.5}]}]}
    assert _market_outcomes(book, "totals", None) is None
    # a concrete line still resolves
    assert _market_outcomes(book, "totals", 2.5) == {"Over": 1.90, "Under": 1.95}
