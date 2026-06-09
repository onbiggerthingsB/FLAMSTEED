from wcmodel.value.scanner import classify_edge
from wcmodel.value.types import ValueConfig
from wcmodel.config import load_config
C = ValueConfig.from_config(load_config())
NOW = "2026-06-08T23:10:00Z"; FRESH = "2026-06-08T23:08:00Z"; STALE = "2026-06-08T22:00:00Z"

def base(**kw):
    d = dict(book="betmgm", edge=0.05, odds=2.7, last_update=FRESH, now=NOW,
             both_sides_book=False, cfg=C); d.update(kw); return d

def test_bettable_clean():
    assert classify_edge(**base()) == ([], True)
def test_too_good_excluded():
    f, b = classify_edge(**base(edge=0.20)); assert "too_good" in f and b is False
def test_below_min_excluded():
    f, b = classify_edge(**base(edge=0.01)); assert "below_min" in f and b is False
def test_other_sharp_not_bettable():
    f, b = classify_edge(**base(book="smarkets")); assert "non_soft" in f and b is False
def test_stale_excluded():
    f, b = classify_edge(**base(last_update=STALE)); assert "stale" in f and b is False
def test_longshot_flagged_not_bettable():
    f, b = classify_edge(**base(odds=9.0)); assert "fragile" in f and b is False
def test_both_sides_excluded():
    f, b = classify_edge(**base(both_sides_book=True)); assert "both_sides" in f and b is False
def test_missing_last_update_fails_open():
    # deliberate fail-open: age None (missing/unparseable last_update) is NOT
    # flagged stale; an otherwise-clean edge stays bettable.
    f, b = classify_edge(**base(last_update=None))
    assert "stale" not in f and f == [] and b is True
