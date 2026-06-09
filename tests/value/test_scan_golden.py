import json
from pathlib import Path
from wcmodel.value.scanner import scan
from wcmodel.value.types import ValueConfig
from wcmodel.config import load_config

NOW = "2026-06-08T23:10:00Z"   # must match the fixture's fresh last_update window

def test_scan_golden():
    events = json.loads(Path("tests/value/fixtures/wc_odds_snapshot.json").read_text())
    res = scan(events, cfg=ValueConfig.from_config(load_config()), now=NOW)
    # exactly one bettable spot, the engineered DR Congo soft +EV
    assert len(res["bettable"]) == 1
    b = res["bettable"][0]
    assert b["soft_book"] == "betmgm" and b["bettable"] is True and b["flags"] == []
    assert round(b["edge"], 4) == 0.0604     # fill from the authored prices
    # the pinnacle-less event is a coverage gap, never an edge
    assert any("no sharp" in g["reason"].lower() for g in res["coverage_gaps"])
    # no bettable spot is ever too-good / stale / non-soft
    assert all(x["edge"] <= 0.10 for x in res["bettable"])
