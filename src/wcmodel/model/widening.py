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
  MEAN-PRESERVING IN EXPECTED GOALS to machine precision (see the function
  docstring) — no central bias in (E[home], E[away]) — but it DOES reshape the
  scoreline distribution and therefore DOES change the 1X2 probabilities: that
  less-confident 1X2 shift is the INTENDED effect for a provisional team, not a
  bug. "Mean-preserving" here means expected goals, NOT the 1X2 fair-price edge.

The two functions are config-driven by ``mechanism`` / ``strength``; wiring them
into the fit/predict path is Task 7.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from wcmodel.data.tiers import MATCH_TYPES
from wcmodel.model.panel import DesignData


def tier_weighted_weight(
    weight: np.ndarray,
    match_type: np.ndarray,
    tier_w: dict | None,
) -> np.ndarray:
    """P2c: multiply the per-match likelihood weight by a per-TIER importance
    weight — ``w_out[i] = weight[i] * tier_w.get(match_type[i], 1.0)``.

    The likelihood weight is otherwise time-decay only (× the optional
    mechanism-(a) provisional down-weight); this layers a tier-importance scale
    on top so a noisy tier (e.g. friendlies) can be trusted less as a strength
    measurement WITHOUT touching the rest of the panel. A tier ABSENT from
    ``tier_w`` keeps multiplier 1.0 (unchanged).

    OFF state is byte-identical, BOTH ways: ``tier_w is None`` (the block absent
    from config) AND a block of all 1.0s return a COPY of ``weight`` that is
    array-equal to the input — so the produced weight (and every object derived
    from it) is bit-for-bit the pre-P2c result.

    Validation is STRICT and fails LOUD (never a silent no-op):
      * every key in ``tier_w`` MUST be a member of the closed tier universe
        (``tiers.MATCH_TYPES``); an unknown name (e.g. a typo) raises
        ``ValueError`` naming the bad key — a typo'd tier would otherwise never
        match a row and silently skip the intended re-weighting.
      * every value MUST be a finite, NON-NEGATIVE float; a negative multiplier
        would flip the likelihood's sign on those rows, so it raises ``ValueError``
        (matching mechanism-(a)'s fail-loud convention for ``likelihood_weight``).

    Returns a NEW array (never mutates ``weight``).
    """
    w = np.asarray(weight, dtype=float).copy()
    if not tier_w:
        return w  # absent / empty block -> byte-identical off path
    unknown = set(tier_w) - set(MATCH_TYPES)
    if unknown:
        raise ValueError(
            f"likelihood_tier_weights has unknown tier name(s) {sorted(unknown)}; "
            f"valid tiers are {sorted(MATCH_TYPES)}"
        )
    for tier, val in tier_w.items():
        fv = float(val)
        if not np.isfinite(fv) or fv < 0.0:
            raise ValueError(
                f"likelihood_tier_weights[{tier!r}] must be a finite, non-negative "
                f"multiplier; got {val!r}"
            )
    # Vectorized per-row multiplier (default 1.0 for any tier not in the block).
    mult = np.array(
        [float(tier_w.get(t, 1.0)) for t in match_type], dtype=float
    )
    return w * mult


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
    """Mechanism (c): widening of a provisional team's PREDICTIVE scoreline grid
    that is MEAN-PRESERVING IN EXPECTED GOALS (to machine precision).

    ``grid`` is a 2D array of shape ``(n_home, n_away)``: a normalized JOINT
    scoreline pmf where ``grid[h, a] = P(home = h, away = a)``. For a provisional
    team we make the predictive WIDER / less confident — strictly higher entropy —
    by mixing the grid toward an independent product of MAX-ENTROPY
    (exponential-tilted) marginals whose means are SOLVED to EQUAL the grid's
    marginal means::

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
    max_goals=6 grid drifted by ~0.03–0.07).

    WHAT IS (and is NOT) preserved — read this carefully. (c) is mean-preserving
    in the marginal EXPECTED GOALS ``(E[home], E[away])`` ONLY: it introduces NO
    CENTRAL BIAS in the predicted goal counts (unlike the rejected uniform-mixture
    widening, which shifted the mean toward the grid centre). It does NOT preserve
    the 1X2 (home/draw/away) fair-price edge: ``predict_1x2`` integrates this
    widened grid, and reshaping the scoreline distribution — even at a fixed
    marginal mean — REDISTRIBUTES mass across the home-win / draw / away-win
    regions, so the 1X2 probabilities DO change. That 1X2 change is the INTENDED
    less-confident effect for a provisional team (the whole point of widening),
    NOT a bug — do not read "mean-preserving" as "edge-preserving".

    Widening is in the ENTROPY sense, and it is GUARANTEED: the max-entropy
    distribution at a given mean is, by construction, the highest-entropy
    distribution with that mean on the bounded support, so mixing any
    non-max-entropy predictive toward it strictly INCREASES Shannon entropy (the
    "less-confident" invariant). For a concentrated predictive it also increases
    variance, though entropy — not variance — is the always-true guarantee.

    A non-provisional team (or in-range ``strength == 0.0``) is a no-op: the input
    grid is returned unchanged. An OUT-OF-RANGE ``strength`` (``<0`` or ``>1``)
    raises ``ValueError`` — fail loud, never a silent no-op/clip. If a marginal
    mean sits at the support edge (~0, all mass at 0 goals; or ~K, the largest
    representable score) there is no interior max-entropy solution and nothing to
    widen on that axis, so the grid is returned unchanged.

    A NON-FINITE input ``grid`` (any NaN/inf cell), a grid that does NOT sum to a
    POSITIVE finite total (e.g. all-zeros — the upstream goal-rate overflow that
    underflowed a per-draw scoreline pmf, before its ``0/0 = NaN`` renorm), or a
    non-finite marginal mean derived from it, is a BROKEN predictive and raises
    ``ValueError("non-finite predictive grid")``. This is a DELIBERATE fail-safe:
    the edge-guard below tests the means with ``<=`` / ``>=``, which NaN silently
    fails (and an all-zeros grid has finite means 0 that would trip the legitimate
    zero-mean no-op), so a broken grid would otherwise sail through into ``brentq``
    and crash cryptically — or silently no-op and propagate a degenerate forecast.
    Surfacing it LOUD and TYPED lets the ablation gate catch it and REJECT the
    candidate honestly (a fabricated/unmeasurable result is forbidden). A VALID pmf
    with all mass on 0-0 (``grid[0,0]==1``, sum 1, mean 0) is NOT broken — it sums to
    a positive total and legitimately trips the zero-mean no-op below, unchanged.

    PHASE-4-TUNABLE. The dispersion/magnitude (here ``alpha = strength``, the mix
    weight) and the (a)-vs-(c) selection are calibration-harness knobs. This is a
    valid DEFAULT FORM, NOT a frozen choice; only the EXACT mean-preservation (and
    entropy-increase) invariant is fixed.
    """
    # Fail loud on an out-of-range strength (a Phase-4 tuning DOF). Validate
    # BEFORE the no-op short-circuits so a bad config can never silently no-op
    # (strength<0) or be silently clipped (strength>1) — it must raise regardless
    # of the provisional flag, mirroring mechanism (a)'s likelihood_weight.
    if not (0.0 <= strength <= 1.0):
        raise ValueError(f"widening strength must be in [0,1], got {strength}")
    # In-range no-ops: a non-provisional team, or strength == 0.0 (zero widening
    # requested), returns the grid unchanged.
    if not is_provisional or strength == 0.0:
        return grid
    # Numerical cap: only bites for strength in (0.99, 1.0]. A full-replacement
    # (alpha == 1.0) would discard the model's predictive entirely (a degenerate
    # mix); cap at 0.99 so a sliver of the model grid always remains. This is a
    # NUMERICAL SAFEGUARD within the valid range, NOT input validation (that is
    # the [0,1] check above).
    alpha = min(float(strength), 0.99)

    n_home, n_away = grid.shape
    home_support = np.arange(n_home)
    away_support = np.arange(n_away)
    # FAIL-SAFE (defense-in-depth, NaN-blind edge-guard fix). A NON-FINITE input
    # grid (e.g. an upstream lambda overflow that underflowed the per-draw scoreline
    # pmf to all-zeros -> 0/0 = NaN; see predict_scoreline) yields NaN marginal
    # means, and the edge-guard below compares mh/ma with `<=` / `>=` — comparisons
    # that NaN SILENTLY FAILS (every comparison is False), so NaN sails past the
    # guard into `_max_entropy_pmf` -> `brentq` and dies with a cryptic
    # "function value at x=-700.0 is NaN" deep in scipy. A non-finite predictive is
    # a BROKEN forecast, not something to "widen" — surface it LOUD and TYPED so the
    # caller (the ablation gate) can catch it and REJECT honestly, never silently
    # widen-nothing-and-return-a-NaN-grid. Mirrors this file's fail-loud convention.
    grid_total = grid.sum()
    if not np.all(np.isfinite(grid)) or not (np.isfinite(grid_total) and grid_total > 0.0):
        raise ValueError("non-finite predictive grid")
    mh = float((grid.sum(axis=1) * home_support).sum())
    ma = float((grid.sum(axis=0) * away_support).sum())
    # A non-finite marginal mean (NaN/inf) likewise cannot drive the exp-tilt solve;
    # the finite-grid check above already rules this out, but assert it explicitly so
    # the brentq target is GUARANTEED finite at the call site (no NaN reaches scipy).
    if not (np.isfinite(mh) and np.isfinite(ma)):
        raise ValueError("non-finite predictive grid")

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
