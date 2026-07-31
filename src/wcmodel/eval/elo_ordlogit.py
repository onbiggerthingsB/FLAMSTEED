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
the baseline adds. ``elo_h`` / ``elo_a`` are the pre-match ratings, i.e. the
``rating_pre`` column of ``wcmodel.data.elo.compute_elo_history``; keeping the
caller responsible for that join is what keeps this module point-in-time.

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
# the bounds never bind on data with all three outcomes present.
_BOUNDS = [(None, None), (-30.0, 30.0), (None, None), (None, None)]


@dataclass(frozen=True)
class OrdLogitParams:
    """A fitted proportional-odds head. ``s`` is the LOG width of the draw
    band; read ``c2`` for the upper threshold itself."""
    c1: float
    s: float
    b_elo: float
    b_hfa: float

    @property
    def c2(self) -> float:
        return self.c1 + math.exp(self.s)


def _design(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Validate and unpack to (elo edge / 400, hfa, class index)."""
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing column(s) {missing}; need {list(_REQUIRED)}")
    frame = df[list(_REQUIRED)]
    if frame.isna().any().any():
        bad = frame[frame.isna().any(axis=1)]
        raise ValueError(f"null value(s) in the fit frame:\n{bad}")
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
    return edge, frame["hfa"].to_numpy(float), y


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


def _mean_nll(theta, edge: np.ndarray, hfa: np.ndarray, y: np.ndarray) -> float:
    """MEAN, not sum: L-BFGS-B differentiates numerically by default, and the
    forward-difference error scales with |f| while its gradient tolerance does
    not — an n-scaled objective would stop the fit on rounding noise."""
    log_p = _log_probs(theta, edge, hfa)
    return -float(log_p[y, np.arange(y.size)].mean())


def fit_ordlogit(df: pd.DataFrame) -> OrdLogitParams:
    """MLE fit over a frame of ``elo_h, elo_a, hfa, outcome`` rows.

    Deterministic: fixed init, no RNG anywhere, so the same frame always
    yields bitwise-identical parameters. Raises rather than returning a
    non-converged fit — a silently bad head would score as a real arm.
    """
    edge, hfa, y = _design(df)
    result = minimize(_mean_nll, _INIT, args=(edge, hfa, y),
                      method="L-BFGS-B", bounds=_BOUNDS)
    if not result.success:
        raise RuntimeError(f"ordered-logit MLE did not converge: "
                           f"{result.message}")
    c1, s, b_elo, b_hfa = (float(v) for v in result.x)
    return OrdLogitParams(c1=c1, s=s, b_elo=b_elo, b_hfa=b_hfa)


def predict_1x2(params: OrdLogitParams, elo_h: float, elo_a: float,
                hfa: float) -> dict[str, float]:
    """1X2 probabilities under a fitted head, keyed the canonical way.

    The keys are exactly ``("home","draw","away")``, so the result drops
    straight into ``calibration.rps`` / ``log_loss`` without a second
    probability convention (finding 16).
    """
    gap = math.exp(params.s)
    eta = (params.b_elo * (float(elo_h) - float(elo_a)) / _ELO_SCALE
           + params.b_hfa * float(hfa))
    z1 = params.c1 - eta
    z2 = z1 + gap
    return {"home": float(expit(-z2)),
            # Same stable difference as the likelihood — see _log_probs.
            "draw": float(expit(z2) * expit(-z1) * -math.expm1(-gap)),
            "away": float(expit(z1))}
