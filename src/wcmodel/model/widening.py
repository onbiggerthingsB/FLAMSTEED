"""Provisional-widening: treat a Phase-1 ``provisional`` team as less reliable.

Two mechanisms ship behind ONE config switch
(``config["model"]["widening"]["mechanism"]`` in ``{"a", "c"}`` plus
``["strength"]``). The Phase-4 lockbox picks the winner — NEITHER is tuned or
selected in Phase 2; both are kept deliberately SIMPLE (Task-0 sizing: only 1 of
48 field teams, Sweden, trips the volatility arm, so this affects very few
predictions).

* (a) likelihood down-weight  — :func:`likelihood_weight`. Any match involving a
  provisional team has its likelihood weight scaled by ``strength`` (<1), so the
  fit trusts those matches less -> wider posterior. DISCARDS information.

* (c) predictive-variance inflation (the design lean) — :func:`inflate_predictive`.
  Weights are left UNTOUCHED (so under 'c' :func:`likelihood_weight` is the
  identity); at PREDICT time a provisional team's predictive scoreline
  distribution is made WIDER / less confident, KEEPING the data.

The two functions are config-driven by ``mechanism`` / ``strength``; wiring them
into the fit/predict path is Task 7.
"""
from __future__ import annotations

import numpy as np

from wcmodel.model.panel import DesignData


def likelihood_weight(d: DesignData, *, mechanism: str, strength: float) -> np.ndarray:
    """Mechanism (a): per-match likelihood weight with provisional down-weighting.

    Returns a COPY of ``d.weight`` (never mutates the input). Under mechanism
    "a", every match in which the home OR away team is provisional has its weight
    multiplied by ``strength``. Under "c" the weights are returned unchanged —
    (c) acts at predict time (:func:`inflate_predictive`), not in the likelihood.
    Any other mechanism is a config error and raises ``ValueError``.
    """
    w = d.weight.copy()
    if mechanism == "a":
        prov_match = d.home_provisional | d.away_provisional
        w[prov_match] = w[prov_match] * strength
    elif mechanism != "c":
        raise ValueError(
            f"unknown widening mechanism {mechanism!r}; choose from {{'a', 'c'}}"
        )
    return w


def inflate_predictive(
    pmf_draws: np.ndarray, *, is_provisional: bool, strength: float
) -> np.ndarray:
    """Mechanism (c): widen a provisional team's PREDICTIVE scoreline pmf.

    ``pmf_draws`` is shape ``(n_draws, n_bins)``; each row is a normalized pmf
    over scoreline bins. For a provisional team we make the predictive WIDER /
    less confident — i.e. HIGHER-ENTROPY / more spread over the outcomes (we are
    less sure what the score will be) — by mixing each row toward the uniform pmf::

        wide = (1 - alpha) * pmf_draws + alpha * uniform,   alpha = min(strength, 0.99)

    The result is still row-normalized (a convex combination of pmfs), and for a
    non-uniform row its Shannon entropy strictly increases. A non-provisional
    team (or ``strength <= 0``) is a no-op: the input is returned unchanged.

    KNOWN LIMITATION — NOT MEAN-PRESERVING (Phase-4-tunable modeling choice).
    --------------------------------------------------------------------------
    Mixing toward uniform-OVER-SCORELINES does NOT preserve the predictive's
    expected scoreline: it pulls E[bin] toward the grid CENTRE (inflating
    high-score mass). For a BETTING model the predicted MEAN drives the edge, so
    a mean-distorting widening is a real weakness of THIS (c)-form. The choice of
    (c)-form — uniform-mixture here vs. a mean-PRESERVING overdispersion (e.g.
    tempering/flattening that keeps E[bin] fixed, or widening a count
    distribution's dispersion rather than its location) — is a Phase-4-tunable
    modeling decision to be revisited in the calibration harness, ALONGSIDE the
    (a)-vs-(c) selection and the ``strength`` knob. ``test_widening.py`` measures
    this mean-shift explicitly so the limitation is characterized, not hidden.

    (Aside on the metric: this WIDENS the predictive — higher entropy — but it
    LOWERS the variance ACROSS posterior draws by ``(1 - alpha)**2`` because the
    added uniform term is a constant per draw. Across-draw variance is PARAMETER
    uncertainty, not predictive spread; entropy/spread-over-outcomes is the
    correct target here. See the test module's header note.)
    """
    if not is_provisional or strength <= 0:
        return pmf_draws
    alpha = min(float(strength), 0.99)
    n_bins = pmf_draws.shape[1]
    uniform = np.full((1, n_bins), 1.0 / n_bins)
    return (1 - alpha) * pmf_draws + alpha * uniform
