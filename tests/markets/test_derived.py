from wcmodel.config import load_config


def test_config_has_markets_totals_block_with_defaults():
    m = load_config()["markets"]["totals"]
    assert m["lines"] == [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]
    assert m["edge_threshold"] == 0.03          # min +EV after uncertainty shrink to place a bet
    assert isinstance(m["soft_books"], list) and m["soft_books"]   # the betting venue(s)
    assert m["sharp_book"] == "pinnacle"         # reference only (never bet, never fed to the model)
