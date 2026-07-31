"""Odds-free Elo ordered-logit head (spec OA-4) — the cheap comparison arm.

A proportional-odds model on ONE latent scale built from the Elo edge:

    eta = b_elo * (elo_h - elo_a) / 400 + b_hfa * hfa
    P(away)         = sigmoid(c1 - eta)
    P(away or draw) = sigmoid(c2 - eta)

with two thresholds ``c1 < c2`` cutting that scale into away / draw / home.
The ordering constraint is structural, not a hope about the optimizer:
``c2 = c1 + exp(s)``, so the free vector is ``(c1, s, b_elo, b_hfa)`` and no
parameterisation of it can put negative mass on the draw.

What this ADDS over ``elo.elo_1x2_baseline``, which stays untouched: the
baseline HARD-CODES its mapping (a fixed logistic on the rating gap plus a
``draw_base`` bump that shrinks with lopsidedness) and its home advantage
(``config['elo']['home_advantage']``, in rating points). Here every one of
those is FITTED — the slope on the Elo edge, the draw width, and the latent
home-advantage shift — so the arm answers "how much 1X2 accuracy is in the
Elo edge alone, optimally mapped" rather than "how good is one hand-written
mapping". Two separate heads, deliberately: the baseline's pinned numbers are
load-bearing for existing reports.

``hfa`` is an indicator on the LATENT scale (1.0 when the home team actually
has home advantage, 0.0 at a neutral venue) — NOT the rating-point constant
the baseline adds. That domain is CHECKED and not merely documented, on both
sides (see ``_HFA_LEVELS``): both safety mechanisms below read the coding
rather than the value, so a rating-point column would silently disarm them
while looking like ordinary finite floats. ``elo_h`` / ``elo_a`` are the
``rating_pre`` column of ``wcmodel.data.elo.compute_elo_history``; keeping the
caller responsible for that join is what keeps this module point-in-time.

``b_hfa`` alone is fitted under a weakly-informative Gaussian prior rather
than by pure MLE, because the pools this arm exists to score put home
advantage on 1-3 of 64 fixtures (only the host plays at home) and that
sub-sample is routinely separated — see ``_HFA_PRIOR_SD``. The fit reports
``n_hfa_minority`` so a caller can tell an estimate from a prior.

Scope: this module fits and predicts. Fitting on real store data and scoring
any arm on a pool is Plan 2, AFTER the prereg locks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, log_expit

_REQUIRED = ("elo_h", "elo_a", "hfa", "outcome")

# The three columns that must be numbers: isna() is False for +-inf, so the
# null guard alone would pass an infinite rating into the optimizer.
_NUMERIC = ("elo_h", "elo_a", "hfa")

# The ONLY admissible hfa values. Checked rather than assumed because both of
# this module's safety mechanisms are statements about this coding, not about
# the numbers: ``n_hfa_minority`` counts the smaller LEVEL, and the b_hfa
# prior's bound tracks the latent shift only while hfa is 0/1 (_HFA_PRIOR_SD).
# The live mis-pass is a column in rating points — the elo_1x2_baseline
# convention, a perfectly ordinary finite float that every other guard passes.
_HFA_LEVELS = (0.0, 1.0)

# The ORDINAL direction of the latent scale (increasing eta favours the home
# team). Same three labels as the canonical ``calibration._OUTCOMES``, whose
# order is the RPS cumulation order — the two must not be confused.
_LATENT_ORDER = ("away", "draw", "home")

_ELO_SCALE = 400.0                       # the Elo convention, as in elo.py

# Seed-free deterministic init, in the (c1, s, b_elo, b_hfa) order: thresholds
# at 0 and 1, a unit slope on the Elo edge, no home advantage.
_INIT = np.array([0.0, 0.0, 1.0, 0.0])

# Only ``s`` is bounded, and only to keep exp(s) inside float range: at s=-30
# the draw band is 9e-14 wide (log-computable) and at s=+30 it is wider than
# any reachable eta. Unbounded, a line search that overshoots to s>709 would
# overflow exp() mid-fit. The interior is where every real optimum lives, so
# the bounds never bind on data with all three outcomes present. ``b_hfa`` is
# left unbounded on purpose — its problem is identification, not range, and a
# FIXED bound cannot express that (see _HFA_PRIOR_SD).
_BOUNDS = [(None, None), (-30.0, 30.0), (None, None), (None, None)]

# Prior SD on ``b_hfa``, in latent units. WHY b_hfa needs one and the other
# three do not: it multiplies a binary indicator whose minority level is 1-3
# rows out of 64 in an international pool (only the host plays at home), and
# such a sub-sample is frequently perfectly separated — every host row a home
# win. The MLE then diverges while L-BFGS-B still reports SUCCESS at whatever
# value its stopping rule reached (measured: b_hfa=+15.7 off ONE row, P(home)
# =0.9999998), so the arm's score would measure the fitter rather than the
# information in the Elo edge. A constant hfa column is the same defect in
# another shape: it identifies only (c1 - b_hfa), and the unpenalised fit
# picks an arbitrary point of that ridge, then predicts a different
# distribution for a venue type it never observed.
#
# Why a prior and not a bound: the safe magnitude depends on how many rows
# carry the indicator, which a constant cannot know. Stationarity of the
# penalised objective gives |b_hfa| <= sd**2 * sum(hfa) — the fit can never
# buy more home advantage than the rows paying for it, and the cap relaxes as
# those rows accumulate. That bound is about the 0/1 CODING, not about b_hfa:
# what reaches the forecast is b_hfa * hfa, so off the indicator scale the
# cap stops tracking the thing it constrains (measured on rating points:
# latent shift +6.90 against a nominal bound of 45). Hence _HFA_LEVELS, which
# makes the coding a checked precondition of this whole argument. Why Gaussian
# and not a heavy tail: a Cauchy penalty's gradient is bounded, so it stops
# resisting exactly where separation pushes hardest; a quadratic does not.
#
# Scale: 0.5 latent units is ~133 Elo points at a typical b_elo=1.5, against a
# real home advantage of 60-100 Elo (0.22-0.37 here) — weakly informative by
# construction. It costs 0.9% of b_hfa at n=8,000 where the data identify the
# term (1.4318 unpenalised -> 1.4193), and pins the constant-column case at 0.
_HFA_PRIOR_SD = 0.5


@dataclass(frozen=True)
class OrdLogitParams:
    """A fitted proportional-odds head. ``s`` is the LOG width of the draw
    band; read ``c2`` for the upper threshold itself.

    ``n_hfa_minority`` is the rows at the smaller level of the ``hfa``
    indicator in the fit frame — the sample that identifies ``b_hfa``, and the
    number a caller needs to tell a fitted home advantage from a prior one. 0
    means the column was constant and ``b_hfa`` is the prior's 0, not an
    estimate — a two-level column can never report 0, because the ``{0,1}``
    coding this counts levels of is checked, not assumed (``_HFA_LEVELS``). It
    defaults to 0 so hand-built params (a known truth in a test, a
    re-parameterisation) stay constructible from the four coefficients.
    """
    c1: float
    s: float
    b_elo: float
    b_hfa: float
    n_hfa_minority: int = 0

    @property
    def c2(self) -> float:
        return self.c1 + math.exp(self.s)


def _check_hfa(hfa: np.ndarray | float) -> None:
    """Reject anything outside ``_HFA_LEVELS`` — column or scalar, so the fit
    frame and a single prediction go through the same domain."""
    values = np.atleast_1d(np.asarray(hfa, dtype=float))
    bad = np.unique(values[~np.isin(values, _HFA_LEVELS)])
    if bad.size:
        raise ValueError(
            f"hfa value(s) {bad[:5].tolist()}{' ...' if bad.size > 5 else ''} "
            "outside {0.0, 1.0}: hfa is the at-home INDICATOR on the latent "
            "scale, not the rating-point home advantage of elo_1x2_baseline")


def _design(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Validate and unpack to (elo edge / 400, hfa, class index)."""
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing column(s) {missing}; need {list(_REQUIRED)}")
    frame = df[list(_REQUIRED)]
    if frame.isna().any().any():
        bad = frame[frame.isna().any(axis=1)]
        raise ValueError(f"null value(s) in the fit frame:\n{bad}")
    finite = np.isfinite(frame[list(_NUMERIC)].to_numpy(float))
    if not finite.all():
        raise ValueError("non-finite value(s) in the fit frame:\n"
                         f"{frame[~finite.all(axis=1)]}")
    hfa = frame["hfa"].to_numpy(float)
    _check_hfa(hfa)
    outcome = frame["outcome"].astype(str)
    unknown = sorted(set(outcome) - set(_LATENT_ORDER))
    if unknown:
        raise ValueError(f"unknown outcome label(s) {unknown}; "
                         f"choose from {list(_LATENT_ORDER)}")
    y = outcome.map({o: i for i, o in enumerate(_LATENT_ORDER)}).to_numpy(int)
    # An absent class is not merely imprecise: its threshold runs to the bound
    # and the optimizer reports SUCCESS on a degenerate answer. Refuse instead.
    absent = [o for i, o in enumerate(_LATENT_ORDER) if not (y == i).any()]
    if absent:
        raise ValueError(f"no {absent} outcome in the fit frame — an absent "
                         "class leaves its threshold unidentified")
    edge = (frame["elo_h"].to_numpy(float)
            - frame["elo_a"].to_numpy(float)) / _ELO_SCALE
    return edge, hfa, y


def _log_probs(theta, edge: np.ndarray, hfa: np.ndarray) -> np.ndarray:
    """Rows of log P in ``_LATENT_ORDER``, computed so no category underflows.

    ``sigmoid(z2) - sigmoid(z1)`` loses the draw entirely once both thresholds
    saturate (and can even go negative); the identity
    ``sigmoid(a) - sigmoid(b) = sigmoid(a) * sigmoid(-b) * (1 - e^-(a-b))``
    for ``a > b`` keeps every factor in a stable range, and ``a - b`` is
    exactly ``exp(s)``.
    """
    c1, s, b_elo, b_hfa = theta
    gap = np.exp(s)
    z1 = c1 - (b_elo * edge + b_hfa * hfa)
    z2 = z1 + gap
    log_draw = log_expit(z2) + log_expit(-z1) + np.log(-np.expm1(-gap))
    return np.stack([log_expit(z1), log_draw, log_expit(-z2)])


def _objective(theta, edge: np.ndarray, hfa: np.ndarray,
               y: np.ndarray) -> float:
    """Mean negative log-likelihood plus the ``b_hfa`` prior.

    MEAN, not sum: L-BFGS-B differentiates numerically by default, and the
    forward-difference error scales with |f| while its gradient tolerance does
    not — an n-scaled objective would stop the fit on rounding noise.

    The prior term is divided by ``n`` for the same reason and for a
    statistical one: on the SUM scale it is then ONE fixed Gaussian, so it
    dominates the 1-3 rows that a tournament pool gives ``b_hfa`` and washes
    out as real rows accumulate. Left on the mean scale it would instead be an
    n-strong prior that never stops shrinking (see _HFA_PRIOR_SD).
    """
    log_p = _log_probs(theta, edge, hfa)
    nll = -float(log_p[y, np.arange(y.size)].mean())
    return nll + float(theta[3]) ** 2 / (2.0 * _HFA_PRIOR_SD ** 2 * y.size)


def fit_ordlogit(df: pd.DataFrame) -> OrdLogitParams:
    """MLE fit over a frame of ``elo_h, elo_a, hfa, outcome`` rows — penalised
    on ``b_hfa`` alone (see _HFA_PRIOR_SD), plain MLE in the other three.

    Deterministic: fixed init, no RNG anywhere, so the same frame always
    yields bitwise-identical parameters. Raises rather than returning a
    non-converged fit — a silently bad head would score as a real arm.
    """
    edge, hfa, y = _design(df)
    result = minimize(_objective, _INIT, args=(edge, hfa, y),
                      method="L-BFGS-B", bounds=_BOUNDS)
    if not result.success:
        raise RuntimeError(f"ordered-logit MLE did not converge: "
                           f"{result.message}")
    c1, s, b_elo, b_hfa = (float(v) for v in result.x)
    # A LEVEL count, not count_nonzero: the two must agree for the field to
    # mean what its docstring says, and only _check_hfa makes them agree.
    at_home = int(np.count_nonzero(hfa == 1.0))
    return OrdLogitParams(c1=c1, s=s, b_elo=b_elo, b_hfa=b_hfa,
                          n_hfa_minority=min(at_home, hfa.size - at_home))


def predict_1x2(params: OrdLogitParams, elo_h: float, elo_a: float,
                hfa: float) -> dict[str, float]:
    """1X2 probabilities under a fitted head, keyed the canonical way.

    The keys are exactly ``("home","draw","away")``, so the result drops
    straight into ``calibration.rps`` / ``log_loss`` without a second
    probability convention (finding 16).

    ``hfa`` is checked here too, not only at fit time: params fitted on the
    indicator are meaningless against a rating-point ``hfa``, and unchecked
    the mis-pass returns a point mass rather than an error.

    The ratings get the same treatment, for the same reason ``_design``
    checks them in the fit frame (``_NUMERIC``): the caller owns the
    ``rating_pre`` join, so a name that missed it arrives here as NaN. Both
    non-finite ends are silent downstream — NaN gives nan probabilities that
    a mean over fixtures SKIPS rather than raises on, and an infinity gives a
    point mass that passes the ledger's probability check intact.
    """
    _check_hfa(hfa)
    if not (math.isfinite(float(elo_h)) and math.isfinite(float(elo_a))):
        raise ValueError(
            f"non-finite rating(s) elo_h={elo_h!r}, elo_a={elo_a!r}: these "
            "are the rating_pre column of compute_elo_history, which never "
            "emits one — the caller's join is what puts a non-finite value "
            "here")
    gap = math.exp(params.s)
    eta = (params.b_elo * (float(elo_h) - float(elo_a)) / _ELO_SCALE
           + params.b_hfa * float(hfa))
    z1 = params.c1 - eta
    z2 = z1 + gap
    return {"home": float(expit(-z2)),
            # Same stable difference as the likelihood — see _log_probs.
            "draw": float(expit(z2) * expit(-z1) * -math.expm1(-gap)),
            "away": float(expit(z1))}
