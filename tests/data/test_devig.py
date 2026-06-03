import numpy as np
from wcmodel.data.devig import multiplicative, power, shin

ODDS = [2.0, 4.0, 4.0]   # 3-way book with overround


def test_all_methods_return_probabilities_summing_to_one():
    for fn in (multiplicative, power, shin):
        p = fn(ODDS)
        assert abs(sum(p) - 1.0) < 1e-9 and all(x > 0 for x in p)


def test_multiplicative_matches_closed_form():
    inv = np.array([1/o for o in ODDS]); expected = inv / inv.sum()
    assert np.allclose(multiplicative(ODDS), expected)


def test_shin_shrinks_longshot_relative_to_multiplicative():
    pm, ps = multiplicative(ODDS), shin(ODDS)
    assert ps[-1] < pm[-1] + 1e-9
