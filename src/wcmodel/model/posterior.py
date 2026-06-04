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
from wcmodel.model.widening import inflate_predictive


class Posterior:
    """Fitted scoreline posterior + per-fixture predictive scoreline grids."""

    def __init__(self, idata, teams, likelihood, provisional_teams=None, config=None):
        self.idata = idata
        self.teams = list(teams)
        self._idx = {t: i for i, t in enumerate(self.teams)}
        self.likelihood = likelihood
        self.provisional_teams = set(provisional_teams or ())
        self._cfg = (config or load_config())["model"]

    def _post(self, name):
        # stack chain+draw -> trailing sample axis S; a team-indexed param
        # (dims chain, draw, <team_dim>) becomes (n_teams, S) so param[i] is
        # (S,); a scalar param (dims chain, draw) becomes (S,). Verified against
        # the installed arviz: stack moves the new `s` dim LAST.
        return self.idata.posterior[name].stack(s=("chain", "draw")).values

    def predict_scoreline(self, home, away, neutral=False, max_goals=10):
        hi, ai = self._idx[home], self._idx[away]      # KeyError if unknown team
        att = self._post("att")
        defe = self._post("def")
        mu = self._post("mu")
        home_adv = self._post("home_adv")
        S = mu.shape[-1]
        n = max_goals + 1
        xs = np.arange(n)
        # log lambda_home = mu + home_adv*(non-neutral) + att[home] - def[away]
        # log lambda_away = mu + att[away] - def[home]   (no home term)
        lh = np.exp(mu + (0.0 if neutral else home_adv) + att[hi] - defe[ai])  # (S,)
        la = np.exp(mu + att[ai] - defe[hi])                                   # (S,)
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

    def predict_1x2(self, home, away, neutral=False, max_goals=10):
        g = self.predict_scoreline(home, away, neutral, max_goals)   # g[h, a]
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
