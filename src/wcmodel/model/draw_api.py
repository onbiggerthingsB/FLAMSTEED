"""Per-draw production scoreline map API (OA Plan 2 v2, V2 / Codex finding 3).

ONE implementation of the production predictive path lives HERE and nowhere
else::

    per-draw rates (fixture context: neutral / host_factor / covariates)
      -> per-draw dependence correction (Dixon-Coles tau at the per-draw rho,
         or the bivariate-Poisson joint at the per-draw lambda3)
      -> per-draw renormalization
      -> mean over draws (parameter uncertainty integrated in)
      -> provisional widening (mechanism 'c') + final normalization

``Posterior.predict_scoreline`` DELEGATES to :func:`production_grid`, so the
dashboard/releases forecast path and every OA consumer (the implied-rate
solver, the E' per-draw blend, scored issuance) evaluate the SAME map.
Finding 3 was exactly the drift risk this closes: a second, almost-right copy
of the map — rho applied once to the averaged grid instead of per draw,
widening skipped, an unfrozen goal truncation — would make the OA arms
measure a DIFFERENT model than the one production issues. The legs are also
exposed separately (:func:`per_draw_rates`, :func:`mean_grid_over_draws`,
:func:`finalize_grid`, :func:`grid_one_x_two`) because the blend and the
solver enter the path at the RATE level while keeping everything downstream
identical; parity with ``predict_scoreline`` is pinned BITWISE on a real
fitted Posterior (tests/model/test_draw_api.py).

Correctness contracts inherited from the cross-model review (moved here WITH
the per-draw loop they govern; ``posterior.py`` keeps the construction-time
ones):

* Dixon-Coles is a QUASI-likelihood (the tau correction does not integrate to
  a proper joint pmf), so the per-draw grid MUST be renormalized; a ``tau<0``
  cell (extreme posterior ``rho`` against unbounded rates) is CLIPPED to 0
  first so no negative probability survives.
* bivariate-Poisson uses the PROPER joint pmf ``exp(bp_loglik_np)`` — its
  joint inherently carries the correct marginal means ``l1+l3, l2+l3``, so
  the grid is just exponentiated + renormalized (the finite-grid truncation
  is the only reason the sum differs from 1 before renorm).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from scipy.stats import poisson

from wcmodel.model.likelihoods import bp_loglik_np, dc_tau_np
from wcmodel.model.widening import inflate_predictive

#: The FROZEN production goal-grid truncation: every grid is
#: ``(max_goals+1)^2``. 10 is the value the production forecast path has
#: always issued at — the ``predict_scoreline``/``predict_1x2`` default, the
#: dashboard ``fixture_forecast`` default and the releases ``price_fixtures``
#: default — so the OA map inherits it VERBATIM rather than re-choosing it
#: (finding 3: an unfrozen truncation was one of the ways the blend interface
#: drifted off the production map). tests/model/test_draw_api.py pins this
#: constant AND every caller; changing the truncation anywhere is a prereg
#: amendment, not a refactor.
PRODUCTION_MAX_GOALS = 10


@dataclass(frozen=True)
class FixtureCtx:
    """The fixture context the production per-draw rates depend on.

    EXACTLY the ``predict_scoreline`` keyword surface, semantics preserved
    verbatim — including precedence: ``host_factor`` set wins over
    ``neutral`` (a fixture is EITHER host-home OR neutral OR ordinary; the
    2026 host-home path passes ``host_factor`` and the orchestrator sets
    ``neutral`` complementarily). ``covariates`` is the per-fixture raw
    covariate mapping ``Posterior._covariate_offsets`` consumes (``None`` =
    the baseline no-covariate path, byte-identical exponents). Frozen so the
    context cannot drift between the rate leg and the finalization leg of the
    shared path.
    """

    home: str
    away: str
    neutral: bool = False
    covariates: Mapping | None = None
    host_factor: float | None = None


def per_draw_rates(posterior, fixture_ctx: FixtureCtx):
    """Per-draw goal rates ``(lam_home, lam_away)``, each shape ``(S,)``.

    The EXACT rate leg of the production path (moved verbatim from
    ``predict_scoreline``): posterior ``att``/``def``/``mu``/``home_adv``
    draws, the fixture's covariate offsets via the PERSISTED training
    transforms + idata betas, and the venue-environment home terms::

        log lam_home = mu + home_term + att[home] - def[away] + home_off
        log lam_away = mu + away_term + att[away] - def[home] + away_off

    Venue environment -> per-side home terms (home_term, away_term):

    * ``host_factor`` set (T5): the 2026 hosts actually play a HOME game. A
      PREDICTION-time scalar (= k from config) on the ALREADY-FITTED
      ``home_adv`` — adds NO fitted parameter, never touches the
      likelihood/identifiability. Home carries ``host_factor*home_adv``; the
      opponent stays at the away rate (``away_term=0``).
    * ``neutral`` (CALIBRATION FIX): a truly-neutral game has NO host, so it
      scores at the AVERAGE environment, not the away rate: add
      ``k_neutral*home_adv`` to BOTH sides (splits the home edge evenly;
      fixes the −0.34 g/game neutral under-prediction, symmetric so 1X2
      ~unchanged). ``k_neutral = cfg["neutral_home_adv_fraction"]``.
    * ordinary home/away: home carries the full fitted ``home_adv``; the away
      side has no home term.

    A fixture is EITHER host-home OR neutral OR ordinary, so there is no
    conflict; ``host_factor=None + neutral=False`` is the plain-home path.
    Unknown teams raise ``KeyError`` (the predict contract).
    """
    hi, ai = posterior._idx[fixture_ctx.home], posterior._idx[fixture_ctx.away]
    att = posterior._post("att")
    defe = posterior._post("def")
    mu = posterior._post("mu")
    home_adv = posterior._post("home_adv")
    # Per-fixture covariate offsets via the PERSISTED transform + idata betas.
    # (0.0, 0.0) when covariates is None/empty -> exponents byte-identical to
    # the baseline (no covariate shift), so the default path is unchanged.
    home_off, away_off = posterior._covariate_offsets(fixture_ctx.covariates)
    if fixture_ctx.host_factor is not None:
        home_term, away_term = fixture_ctx.host_factor * home_adv, 0.0
    elif fixture_ctx.neutral:
        k_neutral = posterior._cfg["neutral_home_adv_fraction"]
        home_term = away_term = k_neutral * home_adv
    else:
        home_term, away_term = home_adv, 0.0
    lh = np.exp(mu + home_term + att[hi] - defe[ai] + home_off)  # (S,)
    la = np.exp(mu + away_term + att[ai] - defe[hi] + away_off)  # (S,)
    return lh, la


def _renorm_draw(g: np.ndarray) -> np.ndarray:
    """Renormalize ONE per-draw scoreline grid, failing LOUD on a degenerate one.

    FAIL-SAFE (defense-in-depth). A diverged/under-converged fit can push a
    covariate offset (e.g. a large ``beta_rest_days`` on a clamped ``z``) so
    far that ``lambda = exp(...)`` OVERFLOWS to ``inf`` -> the truncated
    ``poisson.pmf(0..max_goals, lambda)`` underflows to all-zeros (or carries a
    NaN), so ``g.sum()`` is ``0`` or non-finite and ``g / g.sum()`` is the
    ``0/0 = NaN`` grid behind the original crash (the ``:196`` divide warning).
    Such a draw's forecast is UNUSABLE: detect it and raise the SAME typed error
    ``inflate_predictive`` raises, so the per-draw instability surfaces HONESTLY
    at its source instead of (a) silently averaging a NaN into the mean grid and
    crashing later in ``brentq``, or (b) being papered over by clamping lambda to
    fabricate an all-(max,max) "forecast" that hides the divergence. The caller
    (the ablation gate) catches the ValueError and REJECTs the unstable candidate.
    """
    total = g.sum()
    if not np.isfinite(total) or total <= 0.0 or not np.all(np.isfinite(g)):
        raise ValueError("non-finite predictive grid")
    return g / total


def mean_grid_over_draws(lh, la, *, likelihood: str, rho=None, l3=None,
                         max_goals: int):
    """Mean over draws of per-draw corrected, per-draw renormalized grids.

    ``lh``/``la`` are per-draw rate arrays of shape ``(S,)`` — the production
    path passes :func:`per_draw_rates` output; the implied solver broadcasts a
    constant candidate rate across the fixture posterior's draws; the E' blend
    passes per-draw blended rates. The dependence correction is applied PER
    DRAW at that draw's own ``rho[s]`` (Dixon-Coles) or ``l3[s]``
    (bivariate-Poisson), each draw renormalized, THEN averaged — never a
    single correction on the averaged grid (finding 3). The loop is the
    production arithmetic verbatim; parity with ``predict_scoreline`` is
    pinned bitwise.

    The required correction array is validated LOUDLY: a missing ``rho``/
    ``l3`` (or an unknown likelihood) raises rather than silently pricing an
    independent-Poisson grid — exactly the incoherent stand-in map finding 15
    rejected.
    """
    if likelihood == "dixon_coles":
        if rho is None:
            raise ValueError(
                "dixon_coles mean grid requires the per-draw rho array — a "
                "silent independent-Poisson fallback is a different map "
                "(finding 15)")
    elif likelihood == "bivariate_poisson":
        if l3 is None:
            raise ValueError(
                "bivariate_poisson mean grid requires the per-draw lambda3 "
                "array")
    else:
        raise ValueError(
            f"unknown likelihood {likelihood!r}; choose from "
            "{'dixon_coles', 'bivariate_poisson'}")

    S = lh.shape[-1]
    n = max_goals + 1
    xs = np.arange(n)
    grids = np.empty((S, n, n))
    if likelihood == "dixon_coles":
        for s in range(S):
            g = poisson.pmf(xs, lh[s])[:, None] * poisson.pmf(xs, la[s])[None, :]
            for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
                g[x, y] *= dc_tau_np(x, y, float(lh[s]), float(la[s]), float(rho[s]))
            g = np.clip(g, 0.0, None)            # tau<0 guard: no negative prob
            grids[s] = _renorm_draw(g)           # DC quasi-likelihood -> renorm
    else:  # bivariate_poisson
        for s in range(S):
            g = np.array(
                [
                    [
                        np.exp(bp_loglik_np(x, y, float(lh[s]), float(la[s]), float(l3[s])))
                        for y in range(n)
                    ]
                    for x in range(n)
                ]
            )
            grids[s] = _renorm_draw(g)           # proper joint pmf -> renorm tail only
    return grids.mean(0)                         # average across draws (param uncertainty)


def finalize_grid(grid: np.ndarray, posterior, *, provisional: bool) -> np.ndarray:
    """Widening + final normalization — the LAST leg of the production map.

    Mechanism-'c' widening fires ONLY for a provisional fixture (the predict
    semantics, verbatim); the trailing renormalization runs UNCONDITIONALLY —
    it is part of the map, so a consumer that skipped it would already be off
    the production path.
    """
    if posterior._cfg["widening"]["mechanism"] == "c" and provisional:
        grid = inflate_predictive(
            grid, is_provisional=True,
            strength=posterior._cfg["widening"]["strength"]
        )
    return grid / grid.sum()


def production_grid(posterior, fixture_ctx: FixtureCtx, *,
                    max_goals: int = PRODUCTION_MAX_GOALS) -> np.ndarray:
    """THE production per-fixture scoreline map, end to end.

    Bitwise-equal to ``Posterior.predict_scoreline`` — which DELEGATES here,
    so there is one implementation to drift, not two; the parity is still
    pinned on a real fitted Posterior (neutral / host-home / provisional) so
    any future fork of the paths fails loudly. ``max_goals`` is KEYWORD-ONLY
    and defaults to the frozen production truncation; the caller-pinning test
    refuses any call site that overrides it with anything but the constant
    itself.
    """
    lh, la = per_draw_rates(posterior, fixture_ctx)
    if posterior.likelihood == "dixon_coles":
        grid = mean_grid_over_draws(
            lh, la, likelihood="dixon_coles", rho=posterior._post("rho"),
            max_goals=max_goals)
    else:  # bivariate_poisson (the only other fitted likelihood)
        grid = mean_grid_over_draws(
            lh, la, likelihood="bivariate_poisson",
            l3=np.exp(posterior._post("log_lambda3")), max_goals=max_goals)
    provisional = (fixture_ctx.home in posterior.provisional_teams) \
        or (fixture_ctx.away in posterior.provisional_teams)
    return finalize_grid(grid, posterior, provisional=provisional)


def grid_one_x_two(grid: np.ndarray) -> dict:
    """The 1X2 projection of a scoreline grid — the production scoring map's
    last step (``predict_1x2`` delegates here; the implied-rate solver inverts
    through it)."""
    return {
        "home": float(np.tril(grid, -1).sum()),   # home goals > away goals (lower triangle)
        "draw": float(np.trace(grid)),            # home goals == away goals (diagonal)
        "away": float(np.triu(grid, 1).sum()),    # away goals > home goals (upper triangle)
    }
