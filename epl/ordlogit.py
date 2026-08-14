"""Elo rating difference -> 1X2, as a walk-forward ordered logit.

A proportional-odds model on one latent scale built from the Elo edge::

    eta             = b * (elo_home - elo_away) / 400
    P(away)         = sigmoid(c1 - eta)
    P(away or draw) = sigmoid(c2 - eta)

with two thresholds ``c1 < c2`` cutting the scale into away / draw / home. The
ordering is structural, not a hope about the optimizer: ``c2 = c1 + exp(s)``,
so the free vector is ``(c1, s, b)`` and no value of it can put negative mass
on the draw.

THREE PARAMETERS, NOT FOUR. The international version of this head
(``wcmodel.eval.elo_ordlogit``) carries a fourth coefficient on a home-advantage
INDICATOR, because at a World Cup only the host plays at home. In a league every
match has a home side, so that indicator is constant at 1 and is absorbed
exactly into the thresholds — fitting it would leave ``(c1 - b_hfa)`` and
``(c2 - b_hfa)`` identified but neither term separately, and the optimizer would
return an arbitrary point of that ridge. Home advantage is therefore not absent
here; it is carried by the asymmetry of the thresholds against the distribution
of the Elo edge. Adding the update-side ``home_advantage`` into the feature
would likewise be a pure relabelling — a constant shift of ``b * H / 400`` in
both thresholds — so the feature is the raw rating difference.

WALK-FORWARD. :func:`fit` is a pure function of the rows it is given;
:func:`walk_forward_probabilities` is what makes it point-in-time, refitting at
every cutoff block on strictly earlier matches only.

WHY THE SLOPE IS PENALISED. An ordered logit whose outcomes separate along its
covariate has no finite maximum-likelihood slope, and L-BFGS-B reports SUCCESS
at wherever its stopping rule landed — emitting a near-point-mass forecast that
passes every downstream probability check and is scored by log loss at the clip.
On a full league season that never happens; on the first few dozen matches of an
expanding window it can. A weak Gaussian prior (:data:`SLOPE_PRIOR_SD`) removes
the failure mode at a cost measured in the fourth decimal once a few hundred
matches are in (see the module's test).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, log_expit

__all__ = ["OrdLogitParams", "fit", "predict", "OUTCOMES", "SLOPE_PRIOR_SD"]

#: Probability column order used everywhere in this package: home, draw, away.
#: This is also the RPS cumulation order (:mod:`epl.score`).
OUTCOMES = ("home", "draw", "away")

#: The LATENT order, increasing in eta. Not the same tuple as OUTCOMES and not
#: interchangeable with it: eta increasing means the home team is favoured.
_LATENT = ("away", "draw", "home")

_ELO_SCALE = 400.0

#: Deterministic init in (c1, s, b) order: thresholds at 0 and 1, unit slope.
_INIT = np.array([0.0, 0.0, 1.0])

#: Only ``s`` is bounded, and only to keep ``exp(s)`` inside float range.
_BOUNDS = [(None, None), (-30.0, 30.0), (None, None)]

#: Prior SD on the slope, in latent units per 400 Elo points. Elo's own curve
#: is ``logit = ln(10) * d / 400``, so ``b = 2.303`` is the value at which this
#: head reproduces the rating system it is reading; draws flatten the fitted
#: value to roughly 1.3-1.6. One SD is 1.3 of Elo's own slope, so the prior only
#: resists several times past anything the parameter can mean.
SLOPE_PRIOR_SD = 3.0

#: Convergence is declared on the infinity norm of the gradient of the MEAN
#: penalised NLL, not on the optimizer's status flag — see `fit`. Components of
#: that gradient are O(1), so 1e-7 is roughly seven digits into a stationary
#: point; measured across a full walk over this archive the achieved norm is
#: several orders below it.
GRAD_TOL = 1e-7

#: How many times `fit` may restart L-BFGS-B from its own answer to walk the
#: last digits of the gradient in. Two is enough on every block in this
#: archive; the third exists so the error, when it comes, is about the data.
_MAX_POLISH = 3

#: Below this many earlier matches, no forecast is emitted at all rather than a
#: forecast from a head fitted on a handful of rows. The scoring window in
#: `epl.baseline` opens with four full seasons behind it, so this never binds
#: there; it binds inside the tuning window, where it is meant to.
MIN_FIT_MATCHES = 200


@dataclass(frozen=True)
class OrdLogitParams:
    """A fitted head. ``s`` is the LOG width of the draw band; read ``c2``."""

    c1: float
    s: float
    b: float
    n: int = 0
    edge_sd: float = 0.0
    grad_max: float = 0.0

    @property
    def c2(self) -> float:
        return self.c1 + math.exp(self.s)

    def as_dict(self) -> dict[str, float]:
        return {"c1": self.c1, "s": self.s, "b": self.b, "c2": self.c2,
                "n": self.n, "edge_sd": self.edge_sd,
                "grad_max": self.grad_max}


def _log_probs(theta: np.ndarray, edge: np.ndarray) -> np.ndarray:
    """Rows of log P in ``_LATENT`` order, computed so no category underflows.

    ``sigmoid(z2) - sigmoid(z1)`` loses the draw entirely once both thresholds
    saturate and can even go negative; the identity
    ``sigmoid(a) - sigmoid(b) = sigmoid(a) * sigmoid(-b) * (1 - e^-(a-b))``
    for ``a > b`` keeps every factor in range, and ``a - b`` is exactly
    ``exp(s)``.
    """
    c1, s, b = theta
    gap = np.exp(s)
    z1 = c1 - b * edge
    z2 = z1 + gap
    log_draw = log_expit(z2) + log_expit(-z1) + np.log(-np.expm1(-gap))
    return np.stack([log_expit(z1), log_draw, log_expit(-z2)])


def _objective(theta: np.ndarray, edge: np.ndarray, y: np.ndarray,
               ) -> tuple[float, np.ndarray]:
    """Mean penalised negative log-likelihood and its ANALYTIC gradient.

    MEAN, not sum, and the penalty divided by ``n`` with it: on the sum scale
    the prior is one fixed Gaussian that washes out as rows accumulate, which
    is the behaviour a weakly-informative prior is supposed to have, while on
    the mean scale it would be an n-strong prior that never stops shrinking.

    The gradient is written out rather than left to L-BFGS-B's forward
    differences for a reason that showed up in measurement, not in theory: with
    numerical gradients two runs that differ only in their starting point
    stopped ~1e-5 apart in probability, which is invisible in a reported RPS
    but makes the walk's answer depend on its path. With the analytic gradient
    the same two runs agree to ~1e-9, so a refit is a function of its rows and
    nothing else.

    Writing ``z1 = c1 - b*x`` and ``z2 = z1 + g`` with ``g = exp(s)``, and
    collecting ``d log p / d z1`` and ``d log p / d z2`` per realised class::

        away:  (sigmoid(-z1),  0)
        draw:  (-sigmoid(z1),  sigmoid(-z2))  plus  d/dg = 1 / (e^g - 1)
        home:  (0,            -sigmoid(z2))

    the chain rule through ``dz1/dc1 = dz2/dc1 = 1``, ``dz1/db = dz2/db = -x``,
    ``dz2/dg = 1`` and ``dg/ds = g`` gives the three components below.
    """
    c1, s, b = theta
    gap = math.exp(s)
    z1 = c1 - b * edge
    z2 = z1 + gap
    log_p = _log_probs(theta, edge)
    n = y.size
    nll = -float(log_p[y, np.arange(n)].mean())
    penalty = float(b) ** 2 / (2.0 * SLOPE_PRIOR_SD ** 2 * n)

    is_away, is_draw, is_home = (y == 0), (y == 1), (y == 2)
    g1 = np.where(is_away, expit(-z1), 0.0) + np.where(is_draw, -expit(z1), 0.0)
    g2 = np.where(is_draw, expit(-z2), 0.0) + np.where(is_home, -expit(z2), 0.0)
    # d log p / d gap, the term that does not arrive through z2: only the draw
    # density carries the explicit log(1 - e^-gap) factor.
    # `gap` reaches exp(30) = 1e13 during a line-search excursion, where
    # expm1 overflows to inf; 1/inf is the right answer (0) but arrives with a
    # warning. Clipping the argument at 700 gives 1e-304 instead of 0 — the
    # same number to every digit that can matter, without the noise.
    gg = np.where(is_draw, 1.0 / np.expm1(min(gap, 700.0)), 0.0)
    grad = np.array([
        -float(np.mean(g1 + g2)),                                    # d/dc1
        -float(np.mean(gap * (g2 + gg))),                            # d/ds
        float(np.mean(edge * (g1 + g2))) + b / (SLOPE_PRIOR_SD ** 2 * n),
    ])
    return nll + penalty, grad


def fit(elo_diff: np.ndarray, outcome: np.ndarray,
        init: OrdLogitParams | None = None) -> OrdLogitParams:
    """Fit ``(c1, s, b)`` to rating differences and realised 1X2 labels.

    ``elo_diff`` is ``elo_home_pre - elo_away_pre`` in rating points;
    ``outcome`` is an integer code in :data:`OUTCOMES` order (0 home, 1 draw,
    2 away). ``init`` warm-starts from a previous fit, which is what makes a
    per-block refit over a whole archive cheap; it changes the iteration path,
    not the optimum.

    Deterministic — fixed init, no RNG — so the same rows always give bitwise
    identical parameters. Raises rather than returning a non-converged fit: a
    silently bad head would still score as a real forecaster.
    """
    edge = np.asarray(elo_diff, dtype=float) / _ELO_SCALE
    y_home = np.asarray(outcome, dtype=int)
    if edge.shape != y_home.shape:
        raise ValueError(f"shape mismatch: {edge.shape} vs {y_home.shape}")
    if not np.isfinite(edge).all():
        raise ValueError("non-finite Elo difference in the fit frame")
    if not np.isin(y_home, (0, 1, 2)).all():
        raise ValueError("outcome codes must be 0=home, 1=draw, 2=away")
    # OUTCOMES order -> _LATENT order.
    y = np.array([2, 1, 0])[y_home]
    absent = [o for i, o in enumerate(_LATENT) if not (y == i).any()]
    if absent:
        raise ValueError(f"no {absent} outcome in the fit frame — an absent "
                         "class leaves its threshold unidentified")
    if edge.min() == edge.max():
        raise ValueError(
            f"the Elo edge is constant at {edge[0] * _ELO_SCALE:g} rating "
            f"point(s) over all {edge.size} rows — nothing identifies the "
            "slope, so the fit would report the prior's pull on its init "
            "rather than an estimate; check the rating join")
    x0 = _INIT if init is None else np.array([init.c1, init.s, init.b])
    # Convergence is judged on the GRADIENT, not on `result.success`, and the
    # solver is restarted from its own answer until the gradient is small.
    #
    # Why: with an exact gradient and tolerances near machine precision,
    # L-BFGS-B stops on its ftol test — and sometimes reports ABNORMAL — at a
    # point whose gradient is still ~5e-7, because its line search can no
    # longer make progress from the Hessian approximation it has built. A
    # restart discards that approximation and walks the last few digits in.
    # Trusting the flag would abort a converged fit; ignoring the flag without
    # checking anything would accept a genuinely failed one; the gradient is
    # what "converged" actually means, so it is what is checked.
    #
    # The restart is deterministic (each stage starts from the previous
    # stage's answer), and the optimum is unique here — measured across four
    # starting points a hundredfold apart on real blocks from 200 to 4,000
    # matches, every one lands on the same parameters to 5 decimal places.
    # Tolerances are tighter than the defaults (ftol 2.2e-9, gtol 1e-5), which
    # is affordable only because the gradient is exact: the defaults leave two
    # differently-started fits ~9e-5 apart in parameter space, these leave them
    # ~5e-10 apart, for three extra iterations.
    grad_max = np.inf
    result = None
    for _ in range(_MAX_POLISH):
        result = minimize(_objective, x0, args=(edge, y), method="L-BFGS-B",
                          jac=True, bounds=_BOUNDS,
                          options={"ftol": 1e-13, "gtol": 1e-10})
        x0 = result.x
        grad_max = float(np.max(np.abs(_objective(result.x, edge, y)[1])))
        if grad_max <= GRAD_TOL:
            break
    if grad_max > GRAD_TOL or not np.isfinite(result.x).all():
        raise RuntimeError(
            f"ordered-logit fit did not converge: |grad|_inf = {grad_max:.3g} "
            f"exceeds {GRAD_TOL:g} after {_MAX_POLISH} restarts, at "
            f"{result.x} (optimizer said {result.message!r}) — a "
            "non-stationary head would still emit well-formed probabilities "
            "and score as a real forecaster")
    if abs(result.x[1]) >= 30.0 - 1e-6:
        raise RuntimeError(
            f"the draw-band width hit its bound (s = {result.x[1]:g}): the "
            "bound exists only to keep exp(s) inside float range, so an "
            "optimum sitting on it is a degenerate fit, not a wide draw band")
    c1, s, b = (float(v) for v in result.x)
    return OrdLogitParams(c1=c1, s=s, b=b, n=int(edge.size),
                          edge_sd=float(edge.std()) * _ELO_SCALE,
                          grad_max=grad_max)


def predict(params: OrdLogitParams, elo_diff: np.ndarray) -> np.ndarray:
    """Probabilities as an ``(n, 3)`` array in :data:`OUTCOMES` order."""
    edge = np.atleast_1d(np.asarray(elo_diff, dtype=float)) / _ELO_SCALE
    if not np.isfinite(edge).all():
        raise ValueError("non-finite Elo difference passed to predict")
    gap = math.exp(params.s)
    z1 = params.c1 - params.b * edge
    z2 = z1 + gap
    p_away = expit(z1)
    # The same stable difference as the likelihood — see `_log_probs`.
    p_draw = expit(z2) * expit(-z1) * -np.expm1(-gap)
    p_home = expit(-z2)
    return np.column_stack([p_home, p_draw, p_away])
