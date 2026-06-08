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

    def predict_scoreline(self, home, away, neutral=False, max_goals=10, covariates=None,
                          host_factor=None):
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
        # Venue environment -> per-side home terms (home_term, away_term).
        #   * host_factor set (T5): the 2026 hosts actually play a HOME game. A
        #     PREDICTION-time scalar `host_factor` (= k from config) on the ALREADY-
        #     FITTED home_adv — adds NO fitted parameter, never touches the
        #     likelihood/identifiability. Home carries host_factor*home_adv; the
        #     opponent stays at the away rate (away_term=0). UNCHANGED.
        #   * neutral (CALIBRATION FIX): a truly-neutral game has NO host, so it
        #     should score at the AVERAGE environment, not the away rate. Add
        #     k_neutral*home_adv to BOTH sides (split the home edge evenly). This
        #     raises E[total] to ~2*exp(mu + k*home_adv) and fixes the −0.34 g/game
        #     neutral under-prediction; the boost is symmetric so 1X2 ~unchanged.
        #     k_neutral = self._cfg["neutral_home_adv_fraction"] (self._cfg IS the
        #     `model` block — see __init__ and the widening read below — so the key
        #     is read WITHOUT a leading "model").
        #   * ordinary home/away: home carries the full fitted home_adv; the away
        #     side has no home term. UNCHANGED.
        # A fixture is EITHER host-home OR neutral OR ordinary, so there is no
        # conflict; the fix applies ONLY to the neutral branch (host_factor=None and
        # neutral=True). host_factor=None + neutral=False stays byte-identical.
        if host_factor is not None:
            home_term, away_term = host_factor * home_adv, 0.0
        elif neutral:
            k_neutral = self._cfg["neutral_home_adv_fraction"]
            home_term = away_term = k_neutral * home_adv
        else:
            home_term, away_term = home_adv, 0.0
        # log lambda_home = mu + home_term + att[home] - def[away] + home_off
        # log lambda_away = mu + away_term + att[away] - def[home] + away_off
        lh = np.exp(mu + home_term + att[hi] - defe[ai] + home_off)  # (S,)
        la = np.exp(mu + away_term + att[ai] - defe[hi] + away_off)  # (S,)
        grids = np.empty((S, n, n))
        if self.likelihood == "dixon_coles":
            rho = self._post("rho")
            for s in range(S):
                g = poisson.pmf(xs, lh[s])[:, None] * poisson.pmf(xs, la[s])[None, :]
                for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
                    g[x, y] *= dc_tau_np(x, y, float(lh[s]), float(la[s]), float(rho[s]))
                g = np.clip(g, 0.0, None)            # tau<0 guard: no negative prob
                grids[s] = self._renorm_draw(g)      # DC quasi-likelihood -> renorm
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
                grids[s] = self._renorm_draw(g)      # proper joint pmf -> renorm tail only
        grid = grids.mean(0)                         # average across draws (param uncertainty)
        prov = (home in self.provisional_teams) or (away in self.provisional_teams)
        if self._cfg["widening"]["mechanism"] == "c" and prov:
            grid = inflate_predictive(
                grid, is_provisional=True, strength=self._cfg["widening"]["strength"]
            )
        return grid / grid.sum()

    def predict_1x2(self, home, away, neutral=False, max_goals=10, covariates=None,
                    host_factor=None):
        g = self.predict_scoreline(home, away, neutral, max_goals, covariates,
                                   host_factor)                                  # g[h, a]
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
