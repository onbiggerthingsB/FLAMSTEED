"""Scoreline log-likelihood tests.

The NumPy `*_np` functions are the correctness anchor: verified against
`scipy.stats.poisson` and (for bivariate-Poisson) against the requirement that
the joint pmf sums to 1 over a goal grid. The PyTensor `*_pt` versions are what
the PyMC `Potential` actually evaluates, so they are cross-checked elementwise
against the verified NumPy reference.
"""
import numpy as np
import pytensor
import pytensor.tensor as pt
from scipy.stats import poisson

from wcmodel.model.likelihoods import (
    bp_loglik_np,
    bp_loglik_pt,
    dc_loglik_np,
    dc_loglik_pt,
    dc_tau_np,
)


# ---------------------------------------------------------------------------
# Dixon-Coles NumPy reference
# ---------------------------------------------------------------------------
def test_dc_reduces_to_independent_poisson_when_rho_zero():
    x, y, lh, la = 2, 1, 1.3, 0.9
    expect = poisson.logpmf(x, lh) + poisson.logpmf(y, la)
    assert np.isclose(dc_loglik_np(x, y, lh, la, rho=0.0), expect)


def test_dc_tau_adjusts_only_low_scores():
    lh, la, rho = 1.2, 0.8, 0.1
    assert dc_tau_np(0, 0, lh, la, rho) == 1 - lh * la * rho
    assert dc_tau_np(0, 1, lh, la, rho) == 1 + la * rho
    assert dc_tau_np(1, 0, lh, la, rho) == 1 + lh * rho
    assert dc_tau_np(1, 1, lh, la, rho) == 1 - rho
    assert dc_tau_np(3, 2, lh, la, rho) == 1.0  # untouched


def test_dc_matches_independent_poisson_rho_zero_grid():
    """ALL (x,y) on a grid: DC with rho=0 == independent Poisson logpmf sum."""
    lh, la = 1.7, 1.1
    for x in range(8):
        for y in range(8):
            expect = poisson.logpmf(x, lh) + poisson.logpmf(y, la)
            assert np.isclose(dc_loglik_np(x, y, lh, la, rho=0.0), expect)


def test_dc_normalizes_to_one_when_correction_is_mass_neutral():
    """The raw Dixon-Coles tau-correction is a QUASI-likelihood, not a
    normalized pmf: the original Dixon & Coles (1997) tau re-weights the four
    low-score cells without preserving total mass. The net mass shift is exactly

        rho * (lh - la)**2 * e**(-(lh + la)),

    so exp(dc_loglik) sums to 1 over the goal grid in (and only in) the two
    cases where that shift vanishes -- rho == 0, or lh == la. Downstream
    *predictive* code MUST renormalize DC over the score grid; the likelihood
    used for estimation is the unnormalized form (this is standard DC practice).
    This test pins both special cases AND the closed-form deviation in the
    general case so the un-normalization is a documented, asserted property
    rather than a silent surprise.
    """
    grid = range(0, 40)  # wide enough that truncation error << tolerance

    def dc_grid_sum(lh, la, rho):
        return sum(
            np.exp(dc_loglik_np(x, y, lh, la, rho)) for x in grid for y in grid
        )

    # rho == 0 -> reduces to independent Poisson -> proper pmf.
    assert np.isclose(dc_grid_sum(1.3, 0.9, 0.0), 1.0, atol=1e-9)
    # lh == la -> (lh - la)**2 == 0 -> mass-neutral even with rho != 0.
    assert np.isclose(dc_grid_sum(1.1, 1.1, 0.08), 1.0, atol=1e-9)
    # General case: total mass deviates from 1 by EXACTLY the closed-form shift.
    lh, la, rho = 1.3, 0.9, 0.08
    expected_dev = rho * (lh - la) ** 2 * np.exp(-(lh + la))
    assert np.isclose(dc_grid_sum(lh, la, rho) - 1.0, expected_dev, atol=1e-9)


# ---------------------------------------------------------------------------
# Bivariate-Poisson NumPy reference
# ---------------------------------------------------------------------------
def test_bp_reduces_to_independent_when_lambda3_zero():
    x, y, l1, l2 = 2, 1, 1.3, 0.9
    expect = poisson.logpmf(x, l1) + poisson.logpmf(y, l2)
    assert np.isclose(bp_loglik_np(x, y, l1, l2, l3=0.0), expect)


def test_bp_matches_independent_poisson_lambda3_zero_grid():
    """ALL (x,y) on a grid: BP with l3=0 == independent Poisson logpmf sum."""
    l1, l2 = 1.4, 1.0
    for x in range(8):
        for y in range(8):
            expect = poisson.logpmf(x, l1) + poisson.logpmf(y, l2)
            assert np.isclose(bp_loglik_np(x, y, l1, l2, l3=0.0), expect)


def test_bp_pmf_sums_to_one_with_lambda3():
    """The bivariate-Poisson closed form must integrate to 1 over a goal grid.

    If this fails, the convolution sum is wrong — STOP and report.
    """
    l1, l2, l3 = 1.2, 1.0, 0.5
    grid = range(0, 16)
    total = sum(
        np.exp(bp_loglik_np(x, y, l1, l2, l3)) for x in grid for y in grid
    )
    assert np.isclose(total, 1.0, atol=1e-9)


def test_bp_induces_positive_correlation():
    rng = np.random.default_rng(0)
    l1, l2, l3 = 1.2, 1.0, 0.5
    w1 = rng.poisson(l1, 200000)
    w2 = rng.poisson(l2, 200000)
    w3 = rng.poisson(l3, 200000)
    x, y = w1 + w3, w2 + w3
    assert np.corrcoef(x, y)[0, 1] > 0.05


def test_bp_empirical_logpmf_matches_closed_form():
    """Monte-Carlo the (X,Y) distribution and compare empirical log-frequencies
    to the closed-form bp_loglik_np for the most common cells."""
    rng = np.random.default_rng(7)
    l1, l2, l3 = 1.2, 1.0, 0.5
    n = 4_000_000
    w1 = rng.poisson(l1, n)
    w2 = rng.poisson(l2, n)
    w3 = rng.poisson(l3, n)
    x, y = w1 + w3, w2 + w3
    for cx, cy in [(0, 0), (1, 0), (0, 1), (1, 1), (2, 1), (2, 2)]:
        emp = np.mean((x == cx) & (y == cy))
        closed = np.exp(bp_loglik_np(cx, cy, l1, l2, l3))
        assert np.isclose(emp, closed, atol=3e-3), (cx, cy, emp, closed)


# ---------------------------------------------------------------------------
# PyTensor versions cross-checked against the verified NumPy reference
# ---------------------------------------------------------------------------
def test_dc_loglik_pt_matches_np():
    x = pt.lvector("x")
    y = pt.lvector("y")
    lh = pt.dvector("lh")
    la = pt.dvector("la")
    rho = pt.dscalar("rho")
    f = pytensor.function([x, y, lh, la, rho], dc_loglik_pt(x, y, lh, la, rho))

    xs = np.array([0, 0, 1, 1, 2, 3, 0, 4], dtype=np.int64)
    ys = np.array([0, 1, 0, 1, 1, 2, 3, 0], dtype=np.int64)
    lhs = np.array([1.3, 1.0, 0.7, 2.1, 1.5, 1.1, 0.9, 1.8])
    las = np.array([0.9, 1.2, 1.0, 0.6, 1.3, 0.8, 1.4, 1.0])
    rho_val = 0.07

    got = f(xs, ys, lhs, las, rho_val)
    expect = np.array(
        [dc_loglik_np(a, b, c, d, rho_val) for a, b, c, d in zip(xs, ys, lhs, las)]
    )
    assert np.allclose(got, expect)


def test_dc_loglik_pt_rho_zero_matches_scipy():
    x = pt.lvector("x")
    y = pt.lvector("y")
    lh = pt.dvector("lh")
    la = pt.dvector("la")
    rho = pt.dscalar("rho")
    f = pytensor.function([x, y, lh, la, rho], dc_loglik_pt(x, y, lh, la, rho))
    xs = np.array([0, 1, 2, 3], dtype=np.int64)
    ys = np.array([0, 1, 1, 2], dtype=np.int64)
    lhs = np.array([1.3, 1.0, 1.5, 1.1])
    las = np.array([0.9, 1.2, 1.3, 0.8])
    got = f(xs, ys, lhs, las, 0.0)
    expect = poisson.logpmf(xs, lhs) + poisson.logpmf(ys, las)
    assert np.allclose(got, expect)


def test_bp_loglik_pt_matches_np():
    """bp_loglik_pt with kmax >= max(min(x,y)) must equal bp_loglik_np
    elementwise — the -inf masking + logsumexp handles k>min(x,y)."""
    xs = np.array([0, 1, 2, 3, 4, 2, 0, 5], dtype=np.int64)
    ys = np.array([0, 0, 1, 2, 1, 2, 3, 4], dtype=np.int64)
    l1, l2, l3 = 1.2, 1.0, 0.5
    kmax = int(np.minimum(xs, ys).max())  # = 4

    x = pt.lvector("x")
    y = pt.lvector("y")
    f = pytensor.function([x, y], bp_loglik_pt(x, y, l1, l2, l3, kmax))
    got = f(xs, ys)
    expect = np.array([bp_loglik_np(a, b, l1, l2, l3) for a, b in zip(xs, ys)])
    assert np.allclose(got, expect)


def test_bp_loglik_pt_kmax_larger_than_needed():
    """A kmax strictly larger than any min(x,y) still equals the NumPy ref:
    the extra k-terms are masked to -inf and must not leak into logsumexp."""
    xs = np.array([0, 1, 2, 1, 0], dtype=np.int64)
    ys = np.array([0, 1, 1, 0, 2], dtype=np.int64)
    l1, l2, l3 = 1.1, 0.9, 0.4
    kmax = 7  # >> max(min(x,y)) which is 1

    x = pt.lvector("x")
    y = pt.lvector("y")
    f = pytensor.function([x, y], bp_loglik_pt(x, y, l1, l2, l3, kmax))
    got = f(xs, ys)
    expect = np.array([bp_loglik_np(a, b, l1, l2, l3) for a, b in zip(xs, ys)])
    assert np.allclose(got, expect)


def test_bp_loglik_pt_lambda3_zero_matches_scipy():
    """l3=0 + kmax=0 path equals independent Poisson."""
    xs = np.array([0, 1, 2, 3, 4], dtype=np.int64)
    ys = np.array([0, 1, 1, 2, 0], dtype=np.int64)
    l1, l2 = 1.3, 0.9
    x = pt.lvector("x")
    y = pt.lvector("y")
    f = pytensor.function([x, y], bp_loglik_pt(x, y, l1, l2, 0.0, kmax=0))
    got = f(xs, ys)
    expect = poisson.logpmf(xs, l1) + poisson.logpmf(ys, l2)
    assert np.allclose(got, expect)
