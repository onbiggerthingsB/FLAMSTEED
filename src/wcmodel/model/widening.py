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

* (c) predictive-variance inflation (the design lean) — :func:`inflate_predictive`.
  Weights are left UNTOUCHED (so under 'c' :func:`likelihood_weight` is the
  identity); at PREDICT time a provisional team's predictive scoreline grid is
  made WIDER / less confident, KEEPING the data. (c) is MEAN-PRESERVING (see the
  function docstring) — it does not move the predicted scoreline.

The two functions are config-driven by ``mechanism`` / ``strength``; wiring them
into the fit/predict path is Task 7.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import nbinom

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


# Default overdispersion for the (c) reference marginals. With NB "size" r = mean
# (`_DISPERSION_SIZE_FACTOR` * mean), the NB variance is mean + mean^2/r = 2*mean
# at this default — twice the Poisson variance at the same mean: clearly
# overdispersed but not degenerate. PHASE-4-TUNABLE: this magnitude (and the
# a-vs-c choice and `strength`) are calibration-harness knobs, not frozen.
_DISPERSION_SIZE_FACTOR = 1.0

# Truncation guard: if a marginal mean is below this, there is essentially
# nothing to widen (mass already at 0) — return the grid unchanged.
_MEAN_FLOOR = 1e-9


def _nb_reference_pmf(mean: float, support_size: int) -> np.ndarray:
    """Negative-binomial pmf on ``0..support_size-1`` with mean EXACTLY ``mean``
    (in the infinite-support sense) and variance ``2*mean`` (twice Poisson),
    renormalized on the finite support.

    ``nbinom(n=r, p=r/(r+mu))`` has mean ``mu`` and variance ``mu + mu^2/r``;
    with ``r = mu`` the variance is ``2*mu``. Renormalizing on the finite grid
    introduces only the (negligible, when the grid covers the bulk) truncated
    tail mass, so the finite-support mean stays within the documented <1e-2
    tolerance of ``mean``.
    """
    r = _DISPERSION_SIZE_FACTOR * mean
    p = r / (r + mean)
    support = np.arange(support_size)
    pmf = nbinom.pmf(support, r, p)
    total = pmf.sum()
    if total <= 0:  # pragma: no cover - mean>0 guard upstream makes this unreachable
        return pmf
    return pmf / total


def inflate_predictive(
    grid: np.ndarray, *, is_provisional: bool, strength: float
) -> np.ndarray:
    """Mechanism (c): MEAN-PRESERVING widening of a provisional team's PREDICTIVE
    scoreline grid.

    ``grid`` is a 2D array of shape ``(n_home, n_away)``: a normalized JOINT
    scoreline pmf where ``grid[h, a] = P(home = h, away = a)``. For a provisional
    team we make the predictive WIDER / less confident WITHOUT moving the
    predicted scoreline, by mixing the grid toward an independent product of
    OVERDISPERSED negative-binomial marginals whose means EXACTLY match the
    grid's marginal means::

        alpha = min(strength, 0.99)
        mh, ma = E[home goals], E[away goals]   # the grid's marginal means
        qh = NB(mean=mh, var=2*mh) over 0..n_home-1   (renormalized on support)
        qa = NB(mean=ma, var=2*ma) over 0..n_away-1
        q  = outer(qh, qa)                       # independent -> marginals (mh, ma)
        out = (1 - alpha) * grid + alpha * q ;   return out / out.sum()

    Because ``E[qh] = mh`` and ``E[qa] = ma``, the convex mix has marginal means
    ``(1-alpha)*mh + alpha*mh = mh`` (and ``ma``) — EXACTLY preserved, modulo a
    documented <1e-2 finite-grid truncation error (the NB tail beyond the grid is
    renormalized away; keep the goal-grid bound large enough that this tail is
    negligible — at the default 0..10 grid the error is ~9e-3 for a mean-1.6
    marginal). Variance/entropy strictly increase because the NB reference is
    overdispersed (variance ``2*mu`` vs Poisson ``mu``) at the SAME mean. This is
    the property the previous uniform-over-bins mixture VIOLATED: uniform pulls
    E[scoreline] toward the grid centre and injects high-score mass that scales
    with the arbitrary goal-grid bound, biasing the betting edge.

    A non-provisional team (or ``strength <= 0``) is a no-op: the input grid is
    returned unchanged. If a marginal mean is ~0 (all mass already at 0 goals)
    there is nothing to widen on that axis, so the grid is returned unchanged.

    PHASE-4-TUNABLE. The overdispersion magnitude (``2x`` Poisson here), the
    (a)-vs-(c) selection, and ``strength`` are calibration-harness knobs. This is
    a valid DEFAULT FORM, NOT a frozen choice.
    """
    if not is_provisional or strength <= 0:
        return grid
    alpha = min(float(strength), 0.99)

    n_home, n_away = grid.shape
    home_support = np.arange(n_home)
    away_support = np.arange(n_away)
    mh = float((grid.sum(axis=1) * home_support).sum())
    ma = float((grid.sum(axis=0) * away_support).sum())

    # If either marginal mean is ~0, that axis has no spread to add; mixing a
    # degenerate NB would be a no-op at best, so leave the grid untouched.
    if mh <= _MEAN_FLOOR or ma <= _MEAN_FLOOR:
        return grid

    qh = _nb_reference_pmf(mh, n_home)
    qa = _nb_reference_pmf(ma, n_away)
    q = np.outer(qh, qa)

    out = (1 - alpha) * grid + alpha * q
    return out / out.sum()
