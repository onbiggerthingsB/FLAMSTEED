"""Posterior product: per-fixture scoreline distributions for Phase 3.

Holds the InferenceData + team index. ``predict_scoreline`` builds the
posterior-MEAN scoreline pmf over a ``(max_goals+1)^2`` grid (averaged across
draws -> parameter uncertainty integrated in). Mechanism-(c) widening
(mean-preserving) is applied to the averaged grid for a provisional team. The
likelihood is a ``pm.Potential``, so there is NO observed RV to
``sample_posterior_predictive`` from -- the grid is built MANUALLY from the
posterior ``att``/``def``/``mu``/``home_adv`` (+ ``rho`` for Dixon-Coles or
``log_lambda3`` for bivariate-Poisson).

Two correctness contracts from the cross-model review live here:

* Dixon-Coles is a QUASI-likelihood (the tau correction does not integrate to a
  proper joint pmf), so the per-draw grid MUST be renormalized; a ``tau<0`` cell
  (extreme posterior ``rho`` against unbounded rates) is CLIPPED to 0 first so no
  negative probability survives.
* bivariate-Poisson uses the PROPER joint pmf ``exp(bp_loglik_np)`` -- its joint
  inherently carries the correct marginal means ``l1+l3, l2+l3``, so the grid is
  just exponentiated + renormalized (the finite-grid truncation is the only
  reason the sum differs from 1 before renorm).
"""
from __future__ import annotations

import arviz as az
import numpy as np
from scipy.stats import poisson

from wcmodel.config import load_config
from wcmodel.model.likelihoods import bp_loglik_np, dc_tau_np
# Side-wiring taxonomy: which side(s) a covariate modifies. Imported from panel
# (numpy/pandas-only, no import cycle) so predict reuses the SAME classification
# the fit-time _cov_offset uses — a per-team covariate reads the home value on the
# home rate and "<name>__away" on the away rate; a per-match covariate applies the
# single value to BOTH rates. (scoreline.py keeps its own copy of these for the
# build path; importing from scoreline here would cycle via Posterior.)
from wcmodel.model.panel import _PER_MATCH_COVS, _PER_TEAM_COVS
from wcmodel.model.widening import inflate_predictive


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
        time: for each persisted covariate transform whose value is supplied for
        THIS fixture, add ``beta * z * mask (+ miss * (1 - mask))`` to the correct
        side's log-rate exponent. The transform is the PERSISTED training one (NOT
        re-fit on predict data — re-fitting would leak / mis-scale), and the betas
        are READ from idata via ``_post`` (the SAME params the model fitted, never
        re-estimated). Side wiring: a per-team covariate's supplied value moves the
        HOME rate (``name``) and its ``"<name>__away"`` value moves the AWAY rate;
        a per-match covariate's single value moves BOTH rates.

        A covariate NOT supplied (key absent), or supplied as None/NaN, is a TRUE
        zero shift: apply() masks a non-finite value to 0.0, and a masked side
        contributes EXACTLY nothing — NOT even the ``beta_<name>_miss`` intercept.
        (At predict time we are forecasting a specific future fixture; a covariate
        the caller does not have must leave the forecast at baseline, so a missing
        fixture covariate never moves it — the plan's focal "missing → true
        zero-shift".) The miss intercept therefore only ever rides an OBSERVED
        value's term, where ``(1 - mask) == 0``, so it contributes 0 there too and
        the term reduces to ``beta * z``. Returns ``(0.0, 0.0)`` when no covariate
        is enabled OR none is supplied, keeping ``covariates`` defaulting to None
        byte-identical to the baseline prediction.
        """
        home_off = 0.0
        away_off = 0.0
        if not covariates or not self.covariate_transforms:
            return home_off, away_off

        def _term(name, raw_value):
            # Standardize this fixture's raw value with the PERSISTED transform;
            # apply() returns (z, mask) as length-1 float arrays. A None/NaN value
            # -> mask 0.0 -> EXACT zero contribution (no shift, never imputed, and
            # no miss intercept either — a missing fixture covariate cannot move the
            # forecast). Only an OBSERVED value adds beta * z (+ miss * (1-mask),
            # which is 0 when observed); so the miss term never fires at predict.
            v = np.nan if raw_value is None else raw_value
            t = self.covariate_transforms[name]
            z, mask = t.apply(np.array([v], dtype=float))   # (1,), (1,)
            if mask[0] == 0.0:                               # missing -> true zero shift
                return 0.0
            beta = self._post(f"beta_{name}")               # (S,), read from idata
            term = beta * z[0] * mask[0]                     # (S,); observed
            miss_name = f"beta_{name}_miss"
            if miss_name in self.idata.posterior:            # 0 when observed, kept for parity
                term = term + self._post(miss_name) * (1.0 - mask[0])
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

    def predict_scoreline(self, home, away, neutral=False, max_goals=10, covariates=None):
        hi, ai = self._idx[home], self._idx[away]      # KeyError if unknown team
        att = self._post("att")
        defe = self._post("def")
        mu = self._post("mu")
        home_adv = self._post("home_adv")
        S = mu.shape[-1]
        n = max_goals + 1
        xs = np.arange(n)
        # Per-fixture covariate offsets via the PERSISTED transform + idata betas.
        # (0.0, 0.0) when covariates is None/empty -> exponents byte-identical to
        # the baseline (no covariate shift), so the default path is unchanged.
        home_off, away_off = self._covariate_offsets(covariates)
        # log lambda_home = mu + home_adv*(non-neutral) + att[home] - def[away] + home_off
        # log lambda_away = mu + att[away] - def[home] + away_off   (no home term)
        lh = np.exp(mu + (0.0 if neutral else home_adv) + att[hi] - defe[ai] + home_off)  # (S,)
        la = np.exp(mu + att[ai] - defe[hi] + away_off)                                   # (S,)
        grids = np.empty((S, n, n))
        if self.likelihood == "dixon_coles":
            rho = self._post("rho")
            for s in range(S):
                g = poisson.pmf(xs, lh[s])[:, None] * poisson.pmf(xs, la[s])[None, :]
                for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
                    g[x, y] *= dc_tau_np(x, y, float(lh[s]), float(la[s]), float(rho[s]))
                g = np.clip(g, 0.0, None)            # tau<0 guard: no negative prob
                grids[s] = g / g.sum()               # DC quasi-likelihood -> renorm
        else:  # bivariate_poisson
            l3 = np.exp(self._post("log_lambda3"))
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
                grids[s] = g / g.sum()               # proper joint pmf -> renorm tail only
        grid = grids.mean(0)                         # average across draws (param uncertainty)
        prov = (home in self.provisional_teams) or (away in self.provisional_teams)
        if self._cfg["widening"]["mechanism"] == "c" and prov:
            grid = inflate_predictive(
                grid, is_provisional=True, strength=self._cfg["widening"]["strength"]
            )
        return grid / grid.sum()

    def predict_1x2(self, home, away, neutral=False, max_goals=10, covariates=None):
        g = self.predict_scoreline(home, away, neutral, max_goals, covariates)   # g[h, a]
        return {
            "home": float(np.tril(g, -1).sum()),   # home goals > away goals (lower triangle)
            "draw": float(np.trace(g)),            # home goals == away goals (diagonal)
            "away": float(np.triu(g, 1).sum()),    # away goals > home goals (upper triangle)
        }

    def diagnostics(self):
        s = az.summary(self.idata, var_names=["mu", "home_adv"])
        return {
            "max_rhat": float(s["r_hat"].max()),
            "min_ess_bulk": float(s["ess_bulk"].min()),
        }
