"""Provisional-widening: treat a Phase-1 ``provisional`` team as less reliable.

Two mechanisms ship behind ONE config switch
(``config["model"]["widening"]["mechanism"]`` in ``{"a", "c"}`` plus
``["strength"]``). The Phase-4 lockbox picks the winner — NEITHER is tuned or
selected in Phase 2; both are kept deliberately SIMPLE (Task-0 sizing: only 1 of
48 field teams, Sweden, trips the volatility arm, so this affects very few
predictions).

* (a) likelihood down-weight  — :func:`likelihood_weight`. Any match involving a
  provisional team has its likelihood weight scaled by ``strength`` (in [0, 1]),
  so the fit trusts those matches less -> wider posterior. DISCARDS information.

* (c) predictive-entropy inflation (the design lean) — :func:`inflate_predictive`.
  Weights are left UNTOUCHED (so under 'c' :func:`likelihood_weight` is the
  identity); at PREDICT time a provisional team's predictive scoreline grid is
  made WIDER / less confident (strictly higher entropy), KEEPING the data. (c) is
  EXACTLY MEAN-PRESERVING to machine precision (see the function docstring) — it
  does not move the predicted scoreline, the betting edge.

The two functions are config-driven by ``mechanism`` / ``strength``; wiring them
into the fit/predict path is Task 7.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from wcmodel.model.panel import DesignData


def likelihood_weight(d: DesignData, *, mechanism: str, strength: float) -> np.ndarray:
    """Mechanism (a): per-match likelihood weight with provisional down-weighting.

    Returns a COPY of ``d.weight`` (never mutates the input). Under mechanism
    "a", every match in which the home OR away team is provisional has its weight
    multiplied by ``strength`` (which MUST lie in [0, 1] — a multiplier <0 would
    flip the weight's sign and >1 would UP-weight provisional matches, the
    opposite of widening; either is a config error and raises ``ValueError``).
    Under "c" the weights are returned unchanged — (c) acts at predict time
    (:func:`inflate_predictive`), not in the likelihood, so its ``strength`` (a
    mix weight) is validated there, not here. Any other mechanism is a config
    error and raises ``ValueError``.
    """
    w = d.weight.copy()
    if mechanism == "a":
        if not (0.0 <= strength <= 1.0):
            raise ValueError(
                f"widening (a) strength must be in [0, 1] (a multiplier); "
                f"got {strength!r}"
            )
        prov_match = d.home_provisional | d.away_provisional
        w[prov_match] = w[prov_match] * strength
    elif mechanism != "c":
        raise ValueError(
            f"unknown widening mechanism {mechanism!r}; choose from {{'a', 'c'}}"
        )
    return w


# Edge guard: a marginal mean within this of the support edge (0 or K) has no
# interior max-entropy (exp-tilted) solution — the tilt would need theta -> -+inf
# — and there is essentially nothing to widen on that axis (mass already pinned
# at an edge). In that case the grid is returned unchanged.
_MEAN_EDGE_EPS = 1e-9

# brentq bracket on the tilt parameter theta. mean(theta) for q(k) ∝ exp(theta*k)
# on {0..K} is strictly increasing, -> 0 as theta -> -inf and -> K as theta ->
# +inf, so for any interior target mean in (0, K) the root lies inside a wide
# finite bracket. +-700 keeps exp(theta*k) representable for the k=0..K integer
# support after the overflow-safe max-shift below.
_THETA_BRACKET = 700.0


def _max_entropy_pmf(n_bins: int, mean: float) -> np.ndarray:
    """Max-entropy pmf on the support ``{0, 1, ..., n_bins-1}`` whose mean equals
    ``mean`` EXACTLY (to root-solver precision).

    The maximum-entropy distribution on a bounded integer support subject to a
    fixed mean is the exponential-tilted (Boltzmann) family ``q(k) ∝ exp(theta*k)``.
    Its mean ``sum_k k*q(k)`` is strictly increasing in ``theta`` (it is the mean
    of a one-parameter exponential family, whose derivative in ``theta`` is the
    variance > 0), ranging over the open interval ``(0, K)`` as ``theta`` sweeps
    ``(-inf, +inf)``, where ``K = n_bins - 1``. So for any interior target
    ``mean in (0, K)`` there is a UNIQUE ``theta``; we find it by a 1-D bracketed
    root solve (``brentq``). The returned pmf therefore has mean exactly ``mean``
    on the FINITE support — no truncation/renormalization bias, for ANY grid size
    (contrast the old negative-binomial reference, whose infinite-support mean was
    only approximately preserved once truncated and renormalized on the grid).
    """
    K = n_bins - 1
    ks = np.arange(n_bins)

    def mean_minus_target(theta: float) -> float:
        z = theta * ks
        w = np.exp(z - z.max())  # overflow-safe: shift by max before exp
        p = w / w.sum()
        return float((ks * p).sum() - mean)

    theta = brentq(mean_minus_target, -_THETA_BRACKET, _THETA_BRACKET)
    z = theta * ks
    w = np.exp(z - z.max())
    return w / w.sum()


def inflate_predictive(
    grid: np.ndarray, *, is_provisional: bool, strength: float
) -> np.ndarray:
    """Mechanism (c): EXACTLY MEAN-PRESERVING widening of a provisional team's
    PREDICTIVE scoreline grid.

    ``grid`` is a 2D array of shape ``(n_home, n_away)``: a normalized JOINT
    scoreline pmf where ``grid[h, a] = P(home = h, away = a)``. For a provisional
    team we make the predictive WIDER / less confident WITHOUT moving the
    predicted scoreline, by mixing the grid toward an independent product of
    MAX-ENTROPY (exponential-tilted) marginals whose means are SOLVED to EQUAL
    the grid's marginal means::

        alpha  = min(strength, 0.99)
        mh, ma = E[home goals], E[away goals]   # the grid's marginal means
        qh = max-entropy pmf on 0..n_home-1 with E[k] == mh  (theta solved by brentq)
        qa = max-entropy pmf on 0..n_away-1 with E[k] == ma
        q  = outer(qh, qa)                       # independent -> marginals (mh, ma)
        out = (1 - alpha) * grid + alpha * q ;   return out / out.sum()

    EXACTLY mean-preserving, to machine precision, for ANY grid size. Each
    reference marginal's tilt parameter ``theta`` is found by a 1-D root solve so
    that the FINITE-support mean equals the grid mean exactly (``E[qh] == mh``,
    ``E[qa] == ma``); the convex mix therefore has marginal means
    ``(1-alpha)*mh + alpha*mh = mh`` (and ``ma``), independent of the goal-grid
    bound. This fixes the residual truncation bias of the earlier
    negative-binomial reference, whose infinite-support mean was only
    APPROXIMATELY preserved once truncated and renormalized on the finite grid
    (error exceeding 1e-2 at small grids / high strength — e.g. mean 2.5 on a
    max_goals=6 grid drifted by ~0.03–0.07). A betting edge IS the predicted
    mean, so mean-preservation here is load-bearing and must be exact.

    Widening is in the ENTROPY sense, and it is GUARANTEED: the max-entropy
    distribution at a given mean is, by construction, the highest-entropy
    distribution with that mean on the bounded support, so mixing any
    non-max-entropy predictive toward it strictly INCREASES Shannon entropy (the
    "less-confident" invariant). For a concentrated predictive it also increases
    variance, though entropy — not variance — is the always-true guarantee.

    A non-provisional team (or ``strength <= 0``) is a no-op: the input grid is
    returned unchanged. If a marginal mean sits at the support edge (~0, all mass
    at 0 goals; or ~K, the largest representable score) there is no interior
    max-entropy solution and nothing to widen on that axis, so the grid is
    returned unchanged.

    PHASE-4-TUNABLE. The dispersion/magnitude (here ``alpha = strength``, the mix
    weight) and the (a)-vs-(c) selection are calibration-harness knobs. This is a
    valid DEFAULT FORM, NOT a frozen choice; only the EXACT mean-preservation (and
    entropy-increase) invariant is fixed.
    """
    if not is_provisional or strength <= 0:
        return grid
    alpha = min(float(strength), 0.99)

    n_home, n_away = grid.shape
    home_support = np.arange(n_home)
    away_support = np.arange(n_away)
    mh = float((grid.sum(axis=1) * home_support).sum())
    ma = float((grid.sum(axis=0) * away_support).sum())

    # A marginal mean at the support edge (0 or K) has no interior exp-tilt
    # solution and no spread to add on that axis; leave the grid untouched.
    if (
        mh <= _MEAN_EDGE_EPS
        or mh >= (n_home - 1) - _MEAN_EDGE_EPS
        or ma <= _MEAN_EDGE_EPS
        or ma >= (n_away - 1) - _MEAN_EDGE_EPS
    ):
        return grid

    qh = _max_entropy_pmf(n_home, mh)
    qa = _max_entropy_pmf(n_away, ma)
    q = np.outer(qh, qa)

    out = (1 - alpha) * grid + alpha * q
    return out / out.sum()
