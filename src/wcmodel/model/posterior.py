"""Posterior product: per-fixture scoreline distributions for Phase 3.

Holds the InferenceData + team index. ``predict_scoreline`` builds the
posterior-MEAN scoreline pmf over a ``(max_goals+1)^2`` grid (averaged across
draws -> parameter uncertainty integrated in). Mechanism-(c) widening
(mean-preserving) is applied to the averaged grid for a provisional team. The
likelihood is a ``pm.Potential``, so there is NO observed RV to
``sample_posterior_predictive`` from -- the grid is built MANUALLY from the
posterior ``att``/``def``/``mu``/``home_adv`` (+ ``rho`` for Dixon-Coles or
``log_lambda3`` for bivariate-Poisson).

The grid construction itself — per-draw rates -> per-draw dependence
correction -> per-draw renorm -> mean over draws -> widening — lives in
``wcmodel.model.draw_api`` (OA Plan 2 V2 / Codex finding 3): ``predict_*``
DELEGATE to ``production_grid``/``grid_one_x_two`` so the OA arms (implied
solver, E' blend, scored issuance) and the production forecast path share ONE
implementation, with bitwise parity pinned on a real fitted Posterior. The
DC-quasi-likelihood renorm and bivariate-Poisson proper-joint contracts moved
to ``draw_api`` with the loop they govern; what stays here is what needs the
instance — the posterior reads, the covariate offsets, and construction-time
validation.
"""
from __future__ import annotations

import arviz as az
import numpy as np

from wcmodel.config import load_config
from wcmodel.model.draw_api import (
    PRODUCTION_MAX_GOALS,
    FixtureCtx,
    _renorm_draw as _renorm_draw_impl,
    grid_one_x_two,
    production_grid,
)
# Side-wiring taxonomy: which side(s) a covariate modifies. Imported from panel
# (numpy/pandas-only, no import cycle) so predict reuses the SAME classification
# the fit-time _cov_offset uses — a per-team covariate reads the home value on the
# home rate and "<name>__away" on the away rate; a per-match covariate applies the
# single value to BOTH rates. (scoreline.py keeps its own copy of these for the
# build path; importing from scoreline here would cycle via Posterior.)
from wcmodel.model.panel import _PER_MATCH_COVS, _PER_TEAM_COVS


class Posterior:
    """Fitted scoreline posterior + per-fixture predictive scoreline grids."""

    def __init__(self, idata, teams, likelihood, provisional_teams=None,
                 config=None, covariate_transforms=None):
        self.idata = idata
        self.teams = list(teams)
        self._idx = {t: i for i, t in enumerate(self.teams)}
        self.likelihood = likelihood
        self.provisional_teams = set(provisional_teams or ())
        # The leakage-safe CovariateTransform fitted PER enabled covariate on the
        # < cutoff training rows (set by fit()). predict (T4) reuses these so the
        # exact same standardization is applied to a future fixture's covariate —
        # the single source of truth that keeps fit/predict consistent. Empty {}
        # when no covariate is enabled (the baseline path).
        self.covariate_transforms = dict(covariate_transforms or {})
        self._cfg = (config or load_config())["model"]
        # Fail loud on a bad widening config at CONSTRUCTION -- not at predict
        # time. predict_scoreline only routes through inflate_predictive (which
        # carries its own [0,1] guard) for mechanism 'c' AND a provisional
        # fixture, so a bad strength/mechanism on a non-provisional fixture (or
        # mechanism 'a', which widens in the likelihood) would otherwise silently
        # no-op. Validating here once makes ANY Posterior with a bad widening
        # config raise at the earliest point every construction path hits (fit,
        # cached_fit on a hit, direct construction), independent of provisional
        # status or whether predict is ever called. inflate_predictive keeps its
        # own validation as inner defense-in-depth.
        w = self._cfg["widening"]
        if w["mechanism"] not in ("a", "c"):
            raise ValueError(
                f"widening.mechanism must be 'a' or 'c', got {w['mechanism']!r}"
            )
        if not (0.0 <= w["strength"] <= 1.0):
            raise ValueError(
                f"widening.strength must be in [0,1], got {w['strength']}"
            )

    def _post(self, name):
        # stack chain+draw -> trailing sample axis S; a team-indexed param
        # (dims chain, draw, <team_dim>) becomes (n_teams, S) so param[i] is
        # (S,); a scalar param (dims chain, draw) becomes (S,). Verified against
        # the installed arviz: stack moves the new `s` dim LAST.
        return self.idata.posterior[name].stack(s=("chain", "draw")).values

    def _covariate_offsets(self, covariates):
        """Per-fixture covariate offsets (home_off, away_off), each shape (S,).

        Mirrors the FIT-time linear predictor (scoreline._cov_offset) at PREDICT
        time EXACTLY: for each persisted covariate transform whose value is supplied
        for THIS fixture, add ``beta * z * mask (+ beta_<name>_miss * (1 - mask))``
        to the correct side's log-rate exponent — the same per-term formula fit
        used. The transform is the PERSISTED training one (NOT re-fit on predict
        data — re-fitting would leak / mis-scale), and the betas are READ from idata
        via ``_post`` (the SAME params the model fitted, never re-estimated). Side
        wiring: a per-team covariate's supplied value moves the HOME rate (``name``)
        and its ``"<name>__away"`` value moves the AWAY rate; a per-match
        covariate's single value moves BOTH rates.

        A SUPPLIED-but-missing value (None / NaN) standardizes to ``z=0, mask=0``,
        so the masked ``beta * z * mask`` term is 0 and the behavior depends on
        whether the covariate carries a miss indicator (it is in
        ``missing_indicator_for``):
          * WITH a miss indicator (``travel_km``, ``altitude_m``): the supplied-
            missing value contributes ``beta_<name>_miss * (1 - 0) = beta_<name>_miss``
            — the SAME shift fit applied to a missing-feature match. This is the
            fit/predict consistency fix: a supplied-missing covariate is NOT a true
            zero shift when the model carries a miss intercept.
          * WITHOUT a miss indicator (``rest_days``): there is no ``beta_<name>_miss``
            RV, so the term reduces to ``beta * z * 0 = 0`` — an EXACT zero shift.
        An OBSERVED value gives ``beta * z + beta_miss * 0 = beta * z`` (the miss
        term's ``(1 - mask) == 0``). Returns ``(0.0, 0.0)`` when no covariate is
        enabled OR ``covariates`` is None/empty — that baseline escape hatch is
        SEPARATE from a supplied-but-missing value and stays byte-identical to the
        baseline prediction (the caller supplies nothing -> no term on either side).
        """
        home_off = 0.0
        away_off = 0.0
        if not covariates or not self.covariate_transforms:
            return home_off, away_off

        def _term(name, raw_value):
            # Standardize this fixture's raw value with the PERSISTED transform and
            # build the per-side term EXACTLY as fit-time _cov_offset does:
            #   beta * z * mask  (+ beta_<name>_miss * (1 - mask)  if the indicator exists)
            # apply() returns (z, mask) as length-1 float arrays. A None/NaN value
            # standardizes to z=0, mask=0, so the masked beta term is 0 either way;
            # the miss intercept (when the covariate is in missing_indicator_for)
            # rides (1 - mask) and therefore FIRES on a supplied-missing value — the
            # same shift fit applied to a missing-feature match. A covariate with NO
            # miss indicator falls back to beta * z * 0 == 0 (exact zero, unchanged).
            # An OBSERVED value gives beta * z + beta_miss * 0 == beta * z. This
            # mirrors fit so predict is consistent with how the betas were estimated.
            v = np.nan if raw_value is None else raw_value
            t = self.covariate_transforms[name]
            z, mask = t.apply(np.array([v], dtype=float))   # (1,), (1,); NaN -> z=0,mask=0
            beta = self._post(f"beta_{name}")               # (S,), read from idata
            term = beta * z[0] * mask[0]                     # (S,); 0 when missing
            miss_name = f"beta_{name}_miss"
            if miss_name in self.idata.posterior:            # only for missing_indicator_for covs
                term = term + self._post(miss_name) * (1.0 - mask[0])  # fires when mask==0
            return term

        for name in self.covariate_transforms:
            if name in _PER_TEAM_COVS:
                if name in covariates:
                    home_off = home_off + _term(name, covariates[name])
                away_key = f"{name}__away"
                if away_key in covariates:
                    away_off = away_off + _term(name, covariates[away_key])
            elif name in _PER_MATCH_COVS:
                if name in covariates:                       # single value -> both sides
                    shift = _term(name, covariates[name])
                    home_off = home_off + shift
                    away_off = away_off + shift
            # A persisted transform whose name is in neither side-set cannot occur:
            # _build_covariates only fits transforms for classified covariates.
        return home_off, away_off

    @staticmethod
    def _renorm_draw(g: np.ndarray) -> np.ndarray:
        """Renormalize ONE per-draw scoreline grid, failing LOUD on a degenerate
        one. Delegates to ``draw_api._renorm_draw`` — the fail-safe now lives
        with the per-draw loop it protects; this method survives because
        consumers (and the byte-identity test) pin it here."""
        return _renorm_draw_impl(g)

    def predict_scoreline(self, home, away, neutral=False,
                          max_goals=PRODUCTION_MAX_GOALS, covariates=None,
                          host_factor=None):
        """The production per-fixture scoreline grid.

        DELEGATES to ``draw_api.production_grid`` — ONE implementation of the
        per-draw-rates -> per-draw-correction -> mean -> widening path, shared
        with the OA map (finding 3); bitwise parity is pinned on a real fitted
        Posterior (tests/model/test_draw_api.py). The branch semantics
        (host_factor wins over neutral; neutral scores at the average
        environment; DC per-draw tau + renorm; mechanism-'c' widening for a
        provisional fixture) are documented on the draw_api legs. ``max_goals``
        stays overridable HERE — diagnostic harnesses price shallower grids —
        while the OA surface is pinned to the frozen production default by the
        caller-pinning test.
        """
        return production_grid(
            self,
            FixtureCtx(home=home, away=away, neutral=neutral,
                       covariates=covariates, host_factor=host_factor),
            max_goals=max_goals,
        )

    def predict_1x2(self, home, away, neutral=False,
                    max_goals=PRODUCTION_MAX_GOALS, covariates=None,
                    host_factor=None):
        g = self.predict_scoreline(home, away, neutral, max_goals, covariates,
                                   host_factor)                                  # g[h, a]
        return grid_one_x_two(g)

    def diagnostics(self):
        s = az.summary(self.idata, var_names=["mu", "home_adv"])
        return {
            "max_rhat": float(s["r_hat"].max()),
            "min_ess_bulk": float(s["ess_bulk"].min()),
        }
