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
    # Canonical Dixon-Coles (1997) tau: with x=home~Pois(lh), y=away~Pois(la),
    # the (0,1) cell uses the HOME rate lh and the (1,0) cell uses the AWAY
    # rate la. (A swapped convention is NOT mass-neutral; see the mass-neutral
    # test below.)
    lh, la, rho = 1.2, 0.8, 0.1
    assert dc_tau_np(0, 0, lh, la, rho) == 1 - lh * la * rho
    assert dc_tau_np(0, 1, lh, la, rho) == 1 + lh * rho
    assert dc_tau_np(1, 0, lh, la, rho) == 1 + la * rho
    assert dc_tau_np(1, 1, lh, la, rho) == 1 - rho
    assert dc_tau_np(3, 2, lh, la, rho) == 1.0  # untouched


def test_dc_matches_independent_poisson_rho_zero_grid():
    """ALL (x,y) on a grid: DC with rho=0 == independent Poisson logpmf sum."""
    lh, la = 1.7, 1.1
    for x in range(8):
        for y in range(8):
            expect = poisson.logpmf(x, lh) + poisson.logpmf(y, la)
            assert np.isclose(dc_loglik_np(x, y, lh, la, rho=0.0), expect)


def test_dc_is_mass_neutral():
    """Canonical Dixon-Coles tau is mass-neutral BY CONSTRUCTION: the four
    low-score cell perturbations cancel exactly
    (-lh*la + lh*rho*la + la*rho*lh - rho ... net 0 against the Poisson
    weights), so sum_{x,y} tau(x,y)*Pois(x;lh)*Pois(y;la) == 1 for ANY
    (lh, la, rho) -- including lh != la and rho != 0.

    This is the correctness check that BUG 1 (the swapped (0,1)/(1,0) cells)
    stays fixed: the swapped convention instead sums to
    1 + rho*(lh - la)**2 * e**(-(lh + la)), so it FAILS this test whenever
    lh != la and rho != 0.
    """
    grid = range(0, 40)  # wide enough that truncation error << tolerance

    def dc_grid_sum(lh, la, rho):
        return sum(
            np.exp(dc_loglik_np(x, y, lh, la, rho)) for x in grid for y in grid
        )

    # rho == 0 -> reduces to independent Poisson -> proper pmf.
    assert np.isclose(dc_grid_sum(1.3, 0.9, 0.0), 1.0, atol=1e-6)
    # lh == la, rho != 0 -> mass-neutral.
    assert np.isclose(dc_grid_sum(1.1, 1.1, 0.08), 1.0, atol=1e-6)
    # General cases: lh != la AND rho != 0 -> still exactly mass-neutral.
    assert np.isclose(dc_grid_sum(1.3, 0.9, 0.08), 1.0, atol=1e-6)
    assert np.isclose(dc_grid_sum(2.0, 0.5, 0.15), 1.0, atol=1e-6)


# ---------------------------------------------------------------------------
# Tau-floor soft barrier (Codex T4 NaN trap)
# ---------------------------------------------------------------------------
# The Dixon-Coles tau(0,0)=1-lh*la*rho can go <= 0 when the (UNBOUNDED) rates
# lh,la=exp(...) take a tail draw large enough that lh*la*rho >= 1, even with
# |rho| bounded. log(tau<=0) is NaN and breaks NUTS. The likelihood floors tau
# at a tiny positive epsilon inside the log: a no-op in the valid region
# (tau >> eps), but it converts the pathological tau<=0 tail from a NaN crash
# into a large-but-FINITE penalty -- a soft barrier that repels the sampler.
def test_dc_loglik_finite_when_tau_would_be_nonpositive():
    # lh=la=3.0, rho=0.15 -> tau(0,0)=1-9*0.15=-0.35 (the pathological condition
    # genuinely exists for these unbounded-rate-tail values).
    assert dc_tau_np(0, 0, 3.0, 3.0, 0.15) < 0
    # With the floor, dc_loglik_np is FINITE (penalized), not NaN.
    val = dc_loglik_np(0, 0, 3.0, 3.0, 0.15)
    assert np.isfinite(val)


def test_dc_loglik_pt_finite_when_tau_would_be_nonpositive():
    """PyTensor mirror: the graph the PyMC Potential evaluates must also stay
    finite (not NaN) on the tau<=0 tail, or NUTS crashes instead of being
    repelled."""
    x = pt.lvector("x")
    y = pt.lvector("y")
    lh = pt.dvector("lh")
    la = pt.dvector("la")
    rho = pt.dscalar("rho")
    f = pytensor.function([x, y, lh, la, rho], dc_loglik_pt(x, y, lh, la, rho))
    got = f(
        np.array([0], dtype=np.int64),
        np.array([0], dtype=np.int64),
        np.array([3.0]),
        np.array([3.0]),
        0.15,
    )
    assert np.isfinite(got).all()


def test_dc_loglik_np_floor_is_noop_in_valid_region():
    """The floor must NOT perturb the valid-region likelihood: where
    tau >= _TAU_FLOOR -- which realistic rates always satisfy, tau being O(1),
    far above the 1e-12 floor -- max() picks tau unchanged, so realistic-rate
    values are identical to the unfloored Poisson+log(tau) (matched against
    scipy). NB the floor is a no-op only for tau >= _TAU_FLOOR, NOT for all
    tau>0: a tau in (0, 1e-12) WOULD be floored, but that never occurs for
    realistic O(1) rates. Guards against the floor distorting the calibrated region."""
    for x, y, lh, la, rho in [(0, 0, 1.3, 0.9, 0.08), (2, 1, 1.7, 1.1, 0.1)]:
        tau = dc_tau_np(x, y, lh, la, rho)
        assert tau > 0  # valid region: floor is inert here
        expect = poisson.logpmf(x, lh) + poisson.logpmf(y, la) + np.log(tau)
        assert np.isclose(dc_loglik_np(x, y, lh, la, rho), expect, atol=1e-15)


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


def test_bp_loglik_pt_n_not_equal_kmax_plus_one():
    """BUG 2 regression: the per-match rate term log(l3/(l1*l2)) must broadcast
    against the k-axis, NOT the match-axis. The PyMC model passes PER-MATCH rate
    vectors l1,l2,l3 of shape (n,) (one rate per match from the linear
    predictor). The old `... + k * (log l3 - log l1 - log l2)` multiplied a
    (1, kmax+1) k-grid by an (n,) rate: it ERRORS when n != kmax+1, and silently
    contracts the wrong axis when n == kmax+1.

    Uses n=5 matches and kmax=3 (so n != kmax+1 and n > 1). kmax stays
    >= max(min(x,y)) (the design contract); min(x,y) mixes == kmax (full
    k-range), < kmax (exercise the -inf mask), and == 0 (k=0 term only).
    """
    xs = np.array([0, 1, 5, 3, 2], dtype=np.int64)  # n = 5
    ys = np.array([4, 0, 3, 1, 2], dtype=np.int64)
    # min(x,y) = [0, 0, 3, 1, 2]; max = 3 == kmax (no truncation); mixes 0, <kmax, ==kmax
    # Per-match rate VECTORS (n,), as the model supplies -- this is what makes
    # the broadcast bug surface (scalar rates would mask it).
    l1 = np.array([1.2, 0.8, 1.5, 1.0, 1.3])
    l2 = np.array([1.0, 1.1, 0.9, 1.2, 0.7])
    l3 = np.array([0.5, 0.4, 0.6, 0.3, 0.5])
    kmax = 3  # n (5) != kmax+1 (4)
    assert len(xs) != kmax + 1 and len(xs) > 1
    assert int(np.minimum(xs, ys).max()) == kmax  # contract: kmax >= max(min(x,y))

    x = pt.lvector("x")
    y = pt.lvector("y")
    L1 = pt.dvector("L1")
    L2 = pt.dvector("L2")
    L3 = pt.dvector("L3")
    f = pytensor.function([x, y, L1, L2, L3], bp_loglik_pt(x, y, L1, L2, L3, kmax))
    got = f(xs, ys, l1, l2, l3)
    expect = np.array(
        [bp_loglik_np(a, b, c, d, e) for a, b, c, d, e in zip(xs, ys, l1, l2, l3)]
    )
    assert np.allclose(got, expect, atol=1e-6)


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
