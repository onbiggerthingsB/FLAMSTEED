import numpy as np
import pytest
from wcmodel.config import load_config
from wcmodel.markets.derived import totals_probs


def test_config_has_markets_totals_block_with_defaults():
    m = load_config()["markets"]["totals"]
    assert m["lines"] == [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]
    assert m["edge_threshold"] == 0.03          # min +EV after uncertainty shrink to place a bet
    assert isinstance(m["soft_books"], list) and m["soft_books"]   # the betting venue(s)
    assert m["sharp_book"] == "pinnacle"         # reference only (never bet, never fed to the model)


def test_totals_probs_on_a_known_grid():
    # 3x3 grid: P(0,0)=0.5, P(1,0)=0.2, P(0,1)=0.2, P(1,1)=0.1 (sums to 1).
    g = np.zeros((3, 3))
    g[0, 0], g[1, 0], g[0, 1], g[1, 1] = 0.5, 0.2, 0.2, 0.1
    out = totals_probs(g, lines=[0.5, 1.5, 2.5])
    # P(total > 0.5) = 1 - P(0,0) = 0.5
    assert out[0.5]["over"] == pytest.approx(0.5)
    # P(total > 1.5) = P(1,1) only (total 2) = 0.1
    assert out[1.5]["over"] == pytest.approx(0.1)
    # P(total > 2.5) = 0 (max total here is 2)
    assert out[2.5]["over"] == pytest.approx(0.0)
    # over + under == 1 exactly, every line
    for L, s in out.items():
        assert s["over"] + s["under"] == pytest.approx(1.0)


def test_totals_probs_rejects_degenerate_grid():
    with pytest.raises(ValueError):
        totals_probs(np.zeros((3, 3)), lines=[2.5])          # sums to 0
    with pytest.raises(ValueError):
        totals_probs(np.full((3, 3), np.nan), lines=[2.5])   # non-finite


def test_totals_probs_rejects_negative_pmf():
    # a cell < 0 is not a valid pmf -> raise rather than price off it
    g = np.zeros((3, 3)); g[0, 0] = 1.2; g[1, 1] = -0.2
    with pytest.raises(ValueError):
        totals_probs(g, lines=[1.5])


def test_totals_probs_raises_on_line_at_or_above_grid_bound():
    # A 6x6 grid represents totals 0..10; the max representable total is (n-1)*2 = 10.
    # A line AT/ABOVE the bound has zero representable over-cells -> it would silently return
    # over=0.0 (a WRONG price), so it must RAISE (coverage/config error, never a fabricated price).
    g = np.zeros((6, 6)); g[2, 2] = 1.0
    with pytest.raises(ValueError):
        totals_probs(g, lines=[10.0])          # line == (n-1)*2 bound
    with pytest.raises(ValueError):
        totals_probs(g, lines=[2.5, 12.5])     # one in-grid line, one above the bound
    # a line just BELOW the bound is fine (still representable: total 10 > 9.5)
    out = totals_probs(g, lines=[9.5])
    assert 0.0 <= out[9.5]["over"] <= 1.0
