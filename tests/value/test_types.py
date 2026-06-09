from wcmodel.value.types import ValueBet, ValueConfig
from wcmodel.config import load_config

def test_valueconfig_from_config():
    c = ValueConfig.from_config(load_config())
    assert c.sharp_book == "pinnacle" and c.edge_min == 0.02 and c.too_good == 0.10
    assert "betmgm" in c.soft_books and "pinnacle" not in c.soft_books

def test_valuebet_to_dict_roundtrip():
    b = ValueBet(event="A v B", commence_time="2026-06-15T18:00:00Z", market="h2h",
                 line=None, side="A", sharp_book="pinnacle", sharp_fair_prob=0.40,
                 soft_book="betmgm", soft_odds=2.70, edge=0.08, suggested_stake=0.012,
                 book_tier="soft", last_update="2026-06-08T23:00:00Z",
                 flags=[], bettable=True)
    d = b.to_dict()
    assert d["edge"] == 0.08 and d["bettable"] is True and d["flags"] == []
    assert d["market"] == "h2h" and d["line"] is None
