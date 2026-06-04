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


def dc_tau_np(x, y, lh, la, rho):
    if x == 0 and y == 0:
        return 1.0 - lh * la * rho
    if x == 0 and y == 1:
        return 1.0 + la * rho
    if x == 1 and y == 0:
        return 1.0 + lh * rho
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


def dc_loglik_pt(x, y, lh, la, rho):
    tau = pt.switch(
        pt.eq(x, 0) & pt.eq(y, 0),
        1.0 - lh * la * rho,
        pt.switch(
            pt.eq(x, 0) & pt.eq(y, 1),
            1.0 + la * rho,
            pt.switch(
                pt.eq(x, 1) & pt.eq(y, 0),
                1.0 + lh * rho,
                pt.switch(pt.eq(x, 1) & pt.eq(y, 1), 1.0 - rho, 1.0),
            ),
        ),
    )
    return _pois_logpmf_pt(x, lh) + _pois_logpmf_pt(y, la) + pt.log(tau)


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
    xk = x[:, None]
    yk = y[:, None]
    k = ks[None, :]  # (n, kmax+1)
    valid = k <= pt.minimum(xk, yk)
    log_term = (
        pt.gammaln(xk + 1)
        - pt.gammaln(k + 1)
        - pt.gammaln(xk - k + 1)
        + pt.gammaln(yk + 1)
        - pt.gammaln(k + 1)
        - pt.gammaln(yk - k + 1)
        + pt.gammaln(k + 1)
        + k * (pt.log(l3) - pt.log(l1) - pt.log(l2))
    )
    log_term = pt.switch(valid, log_term, -np.inf)
    return base + pt.logsumexp(log_term, axis=1)
