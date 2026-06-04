"""Scoreline log-likelihoods. NumPy reference (`*_np`, used in tests + the
NumPy predictive path) and PyTensor versions (`dc_loglik_pt`, `bp_loglik_pt`,
vectorised over matches) used inside the PyMC `Potential`.

Dixon-Coles: independent Poisson(home; lh), Poisson(away; la) with the low-score
dependence correction tau(x,y; rho). Bivariate-Poisson (Karlis-Ntzoufris):
X = W1+W3, Y = W2+W3, Wi~Poisson(li); closed-form joint pmf with the
min(x,y) convolution sum.
"""
from __future__ import annotations

import numpy as np
import pytensor.tensor as pt
from scipy.special import gammaln


# ---- NumPy reference ----
def _pois_logpmf_np(k, lam):
    return k * np.log(lam) - lam - gammaln(k + 1.0)


# CONTRACT (NaN trap): caller must constrain `rho` so ALL FOUR tau cells stay
# strictly positive: for rho>0 the binding cells are tau(0,0)=1-lh*la*rho>0 and
# tau(1,1)=1-rho>0; for rho<0 they are tau(0,1)=1+lh*rho>0 and tau(1,0)=1+la*rho>0.
# Otherwise log(tau) is NaN/-inf and breaks NUTS.
def dc_tau_np(x, y, lh, la, rho):
    # Canonical Dixon & Coles (1997) tau: x=home~Pois(lh), y=away~Pois(la).
    # The (0,1) cell uses the HOME rate lh; the (1,0) cell uses the AWAY rate la.
    # This convention is mass-neutral (the four perturbations cancel exactly).
    if x == 0 and y == 0:
        return 1.0 - lh * la * rho
    if x == 0 and y == 1:
        return 1.0 + lh * rho
    if x == 1 and y == 0:
        return 1.0 + la * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def dc_loglik_np(x, y, lh, la, rho):
    return (
        _pois_logpmf_np(x, lh)
        + _pois_logpmf_np(y, la)
        + np.log(dc_tau_np(x, y, lh, la, rho))
    )


def bp_loglik_np(x, y, l1, l2, l3):
    # log P(X=x,Y=y) = -(l1+l2+l3) + x*log l1 + y*log l2 - log x! - log y!
    #                  + log sum_{k=0}^{min(x,y)} C(x,k)C(y,k) k! (l3/(l1 l2))^k
    m = min(int(x), int(y))
    if l3 == 0.0:
        s = 0.0  # log(1)
    else:
        ks = np.arange(m + 1)
        log_terms = (
            gammaln(x + 1)
            - gammaln(ks + 1)
            - gammaln(x - ks + 1)
            + gammaln(y + 1)
            - gammaln(ks + 1)
            - gammaln(y - ks + 1)
            + gammaln(ks + 1)
            + ks * (np.log(l3) - np.log(l1) - np.log(l2))
        )
        s = np.logaddexp.reduce(log_terms)
    return (
        -(l1 + l2 + l3)
        + x * np.log(l1)
        + y * np.log(l2)
        - gammaln(x + 1)
        - gammaln(y + 1)
        + s
    )


# ---- PyTensor (vectorised over matches; goals are observed constants) ----
def _pois_logpmf_pt(k, lam):
    return k * pt.log(lam) - lam - pt.gammaln(k + 1.0)


# CONTRACT (NaN trap): caller must constrain `rho` so ALL FOUR tau cells stay
# strictly positive: for rho>0 the binding cells are tau(0,0)=1-lh*la*rho>0 and
# tau(1,1)=1-rho>0; for rho<0 they are tau(0,1)=1+lh*rho>0 and tau(1,0)=1+la*rho>0.
# Otherwise log(tau) is NaN/-inf and breaks NUTS.
def dc_loglik_pt(x, y, lh, la, rho):
    # Canonical Dixon-Coles tau (see dc_tau_np): (0,1) uses HOME rate lh,
    # (1,0) uses AWAY rate la. Mass-neutral by construction.
    tau = pt.switch(
        pt.eq(x, 0) & pt.eq(y, 0),
        1.0 - lh * la * rho,
        pt.switch(
            pt.eq(x, 0) & pt.eq(y, 1),
            1.0 + lh * rho,
            pt.switch(
                pt.eq(x, 1) & pt.eq(y, 0),
                1.0 + la * rho,
                pt.switch(pt.eq(x, 1) & pt.eq(y, 1), 1.0 - rho, 1.0),
            ),
        ),
    )
    return _pois_logpmf_pt(x, lh) + _pois_logpmf_pt(y, la) + pt.log(tau)


# CONTRACT (NaN trap): requires `l3 > 0` when `kmax > 0` -- the k=0 term computes
# 0*log(l3), and l3=0 yields NaN in the vectorized graph. For the independent
# (l3=0) case pass kmax=0. The model uses a strictly-positive prior on l3.
def bp_loglik_pt(x, y, l1, l2, l3, kmax: int):
    # x, y are observed int arrays; kmax = max(min(x,y)) precomputed in the design.
    base = (
        -(l1 + l2 + l3)
        + x * pt.log(l1)
        + y * pt.log(l2)
        - pt.gammaln(x + 1)
        - pt.gammaln(y + 1)
    )
    if kmax == 0:
        return base
    ks = pt.arange(kmax + 1)  # (kmax+1,)
    xk = x[:, None]  # (n, 1)
    yk = y[:, None]  # (n, 1)
    k = ks[None, :]  # (1, kmax+1)
    valid = k <= pt.minimum(xk, yk)  # (n, kmax+1)
    # The per-match rate term log(l3/(l1*l2)) must broadcast against k over the
    # MATCH axis, giving entry [i, j] = j * rate_i. `shape_padright` appends a
    # trailing axis: a per-match (n,) rate (what the model supplies) becomes
    # (n, 1) so `k * rate` is (n, kmax+1); a scalar rate becomes (1, 1) and still
    # broadcasts as a scalar. (BUG: a bare (n,) rate term either ERRORS for
    # n != kmax+1 or silently contracts the wrong axis when n == kmax+1.) The
    # gammaln terms already broadcast: xk/yk are (n,1), k is (1, kmax+1).
    rate = pt.shape_padright(pt.log(l3) - pt.log(l1) - pt.log(l2))  # (n, 1)
    log_term = (
        pt.gammaln(xk + 1)
        - pt.gammaln(k + 1)
        - pt.gammaln(xk - k + 1)
        + pt.gammaln(yk + 1)
        - pt.gammaln(k + 1)
        - pt.gammaln(yk - k + 1)
        + pt.gammaln(k + 1)
        + k * rate
    )
    log_term = pt.switch(valid, log_term, -np.inf)
    return base + pt.logsumexp(log_term, axis=1)
