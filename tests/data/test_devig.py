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


def test_shin_strictly_shrinks_longshot_on_overround_book():
    # real overround book: favourite, mid, longshot (1/1.5+1/3.5+1/7 ≈ 1.095 > 1)
    book = [1.5, 3.5, 7.0]
    pm, ps = multiplicative(book), shin(book)
    assert abs(sum(ps) - 1.0) < 1e-9
    assert ps[-1] < pm[-1]            # STRICT: Shin reduces the longshot (fav-longshot correction)
    assert ps[0] > pm[0]             # ...and inflates the favourite


def test_shin_reduces_to_multiplicative_on_fair_book():
    import numpy as np
    fair = [2.0, 4.0, 4.0]           # zero overround -> z->0 limit
    assert np.allclose(shin(fair), multiplicative(fair))


def test_two_outcome_book_all_methods_valid():
    for fn in (multiplicative, power, shin):
        p = fn([1.5, 2.5])           # overround two-way
        assert abs(sum(p) - 1.0) < 1e-9 and all(x > 0 for x in p)


def test_power_normalizes_overround_book():
    p = power([1.5, 3.5, 7.0])
    assert abs(sum(p) - 1.0) < 1e-9 and all(x > 0 for x in p)
