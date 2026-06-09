from wcmodel.config import load_config

def test_value_block_defaults():
    v = load_config()["value"]
    assert v["sports"] == ["soccer_fifa_world_cup"]
    assert v["markets"] == ["h2h", "totals"]
    assert v["sharp_book"] == "pinnacle"
    assert v["edge_min"] == 0.02
    assert v["too_good"] == 0.10
    assert v["longshot_odds"] == 8.0
    assert v["stale_seconds"] == 900
    assert v["kelly_fraction"] == 0.25
    assert v["max_calls_per_scan"] == 2
    assert "pinnacle" not in v["soft_books"]      # the sharp is never a soft (bettable) book
    assert v["ledger_path"] == "reports/value_paper_ledger.jsonl"
