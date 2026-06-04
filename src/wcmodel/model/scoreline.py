"""ScorelineModel interface + the two PyMC likelihoods.

Hierarchical attack/defense with SOFT sum-to-zero centering (att = att_raw -
mean(att_raw)); baseline mu; home_adv applied only on non-neutral matches; the
likelihood is TIME-DECAY-WEIGHTED via a Potential (weight = design.weight, which
carries the Phase-1 decay_weight). This file is mechanism-AGNOSTIC: it consumes
whatever `weight` array it is given. Widening is applied in a LATER task —
mechanism (a) (likelihood down-weight) would multiply into this weight, while the
Phase-2 default mechanism (c) (predictive-variance inflation) leaves weight =
decay only and acts at predict time. Elo is NOT used here (independent prior):
the model learns attack/defense from goals + team indices + the decay weight
only — it never reads elo_pre or any rating.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pymc as pm
import pytensor.tensor as pt

from wcmodel.config import load_config
from wcmodel.data import features
from wcmodel.model.inference import sample
from wcmodel.model.likelihoods import bp_loglik_pt, dc_loglik_pt
from wcmodel.model.panel import DesignData, build_design, to_match_panel
from wcmodel.model.posterior import Posterior
from wcmodel.model.volatility_diagnostic import count_volatility_arm
from wcmodel.model.widening import likelihood_weight


def _rates(d: DesignData, att, defe, mu, home_adv):
    # log lambda_home = mu + home_adv*(non-neutral) + att[home] - def[away]
    # log lambda_away = mu + att[away] - def[home]   (no home term)
    neutral = d.neutral.astype(float)
    log_lh = mu + home_adv * (1.0 - neutral) + att[d.home_idx] - defe[d.away_idx]
    log_la = mu + att[d.away_idx] - defe[d.home_idx]
    return pt.exp(log_lh), pt.exp(log_la)


def _priors(d: DesignData, p):
    sigma_att = pm.HalfNormal("sigma_att", sigma=p["sigma_att"])
    sigma_def = pm.HalfNormal("sigma_def", sigma=p["sigma_def"])
    att_raw = pm.Normal("att_raw", 0.0, sigma_att, shape=d.n_teams)
    def_raw = pm.Normal("def_raw", 0.0, sigma_def, shape=d.n_teams)
    att = pm.Deterministic("att", att_raw - pt.mean(att_raw))  # soft sum-to-zero
    defe = pm.Deterministic("def", def_raw - pt.mean(def_raw))
    mu = pm.Normal("mu", p["mu_loc"], p["mu_scale"])
    home_adv = pm.Normal("home_adv", p["home_loc"], p["home_scale"])
    return att, defe, mu, home_adv


class ScorelineModel(ABC):
    @abstractmethod
    def build(self, d: DesignData, weight: np.ndarray, config: dict | None = None) -> pm.Model: ...


class DixonColesModel(ScorelineModel):
    def build(self, d, weight, config=None):
        p = (config or load_config())["model"]["prior"]
        with pm.Model() as m:
            att, defe, mu, home_adv = _priors(d, p)
            # rho CONTRACT (likelihoods.dc_loglik_pt): a tau cell <= 0 -> log(tau)
            # = NaN. This TruncatedNormal keeps |rho| small (<=0.15) so that for
            # realistic international goal rates (~<=2.5 each, lh*la <~ 6.25)
            # tau(0,0)=1-lh*la*rho stays positive. But the rates lh,la=exp(...) are
            # UNBOUNDED: a tail draw with lh*la*|rho| >= 1 can still push tau(0,0)<=0,
            # so the bound makes that RARE, not impossible. The actual structural NaN
            # guard for the unbounded-rate tail is the `_TAU_FLOOR` soft barrier in
            # dc_loglik_pt (a tau<=0 draw yields a finite penalty -> NUTS is repelled,
            # not crashed). The bound stays as a good weakly-informative prior (safe
            # Phase-2 default; Phase-4 may tune) that keeps the floor essentially never
            # active on realistic rates.
            rho = pm.TruncatedNormal(
                "rho", mu=0.0, sigma=p["rho_scale"], lower=-0.15, upper=0.15
            )
            lh, la = _rates(d, att, defe, mu, home_adv)
            ll = dc_loglik_pt(d.home_goals, d.away_goals, lh, la, rho)
            pm.Potential("like", pt.sum(pt.as_tensor_variable(weight) * ll))
        return m


class BivariatePoissonModel(ScorelineModel):
    def build(self, d, weight, config=None):
        p = (config or load_config())["model"]["prior"]
        # kmax = max over matches of min(home,away) goals (the convolution depth).
        # bp_loglik_pt handles kmax==0 as the independent case.
        kmax = int(np.minimum(d.home_goals, d.away_goals).max()) if len(d.home_goals) else 0
        with pm.Model() as m:
            att, defe, mu, home_adv = _priors(d, p)
            # l3 CONTRACT (likelihoods.bp_loglik_pt): l3 must be > 0 when kmax>0
            # (the k=0 term computes 0*log(l3); l3=0 yields NaN in the vectorized
            # graph). Parameterise l3 = exp(log_l3) so l3>0 ALWAYS. Centered at
            # log(0.1): a small covariance default, consistent with rho_scale.
            log_l3 = pm.Normal("log_lambda3", np.log(0.1), p["rho_scale"])
            l3 = pt.exp(log_l3)
            lh, la = _rates(d, att, defe, mu, home_adv)
            ll = bp_loglik_pt(d.home_goals, d.away_goals, lh, la, l3, kmax)
            pm.Potential("like", pt.sum(pt.as_tensor_variable(weight) * ll))
        return m


_REGISTRY = {
    "dixon_coles": DixonColesModel,
    "bivariate_poisson": BivariatePoissonModel,
}


def build_model(
    d: DesignData,
    likelihood: str | None = None,
    weight: np.ndarray | None = None,
    config: dict | None = None,
) -> pm.Model:
    likelihood = likelihood or (config or load_config())["model"]["likelihood"]
    if likelihood not in _REGISTRY:
        raise ValueError(f"unknown likelihood {likelihood!r}; choose from {sorted(_REGISTRY)}")
    w = d.weight if weight is None else weight
    return _REGISTRY[likelihood]().build(d, w, config)


def fit(
    cutoff,
    store,
    *,
    likelihood: str | None = None,
    backend: str | None = None,
    draws: int | None = None,
    tune: int | None = None,
    seed: int | None = None,
    advi_iters: int | None = None,
    config: dict | None = None,
) -> Posterior:
    """Fit the scoreline model on the leakage-safe per-cutoff panel -> Posterior.

    Consumes ONLY ``features.build(cutoff, store, cfg)`` -- the Phase-1
    leakage-safe panel (matches strictly before the cutoff day, played-filtered).
    No future data and no other store table is read here, so a fit at ``cutoff``
    can never peek past it (Phase-2 Task 9 adds a model-layer leakage canary on
    top of this). The match-level design feeds the (a)/(c) widening switch and the
    PyMC scoreline model; ``sample`` (ADVI by default) produces the posterior. The
    provisional-team set (for mechanism-(c) predict-time widening) is the
    AS-OF-CUTOFF status -- each team's would-be provisional flag at its NEXT match
    -- via the Task-0 ``count_volatility_arm`` (volatility OR few-games arm), NOT
    the per-match panel flags. Those panel flags are PRE-MATCH states, so a team
    provisional only in its first few (historical) matches would otherwise be
    flagged "ever provisional" and widened at predict time forever; the
    as-of-cutoff status widens only teams genuinely low-information NOW.
    ``count_volatility_arm`` reads only matches strictly before the cutoff (the
    same leakage-safe slice ``features.build`` uses), so this stays leakage-safe;
    the duplicate sub-cutoff Elo recompute is acceptable for Phase 2.

    All sampler knobs default to ``config["model"]`` (or the global config) and
    can be overridden per-call; ``seed`` falls back to the global ``config["seed"]``.
    """
    cfg = config or load_config()
    likelihood = likelihood or cfg["model"]["likelihood"]
    inf = cfg["model"]["inference"]
    backend = backend or inf["backend"]
    draws = draws or inf["draws"]
    tune = tune or inf["tune"]
    advi_iters = advi_iters or inf["advi_iters"]
    seed = cfg["seed"] if seed is None else seed
    feats = features.build(cutoff, store, cfg)            # leakage-safe panel ONLY
    mp = to_match_panel(feats)
    d = build_design(mp)
    w = likelihood_weight(
        d,
        mechanism=cfg["model"]["widening"]["mechanism"],
        strength=cfg["model"]["widening"]["strength"],
    )
    model = build_model(d, likelihood=likelihood, weight=w, config=cfg)
    idata = sample(
        model, backend=backend, draws=draws, tune=tune, seed=seed, advi_iters=advi_iters
    )
    # Provisional set is the AS-OF-CUTOFF status (each team's would-be flag at its
    # NEXT match), NOT the per-match panel flags (which are pre-match states, so a
    # team provisional only in its early history would be widened forever).
    # count_volatility_arm reads only matches strictly before the cutoff -> the
    # same leakage-safe slice features.build uses; a team is provisional-for-
    # prediction iff its volatility OR few-games arm trips.
    arm = count_volatility_arm(store, cutoff, d.teams)
    prov = set(arm.loc[arm["volatility_flag"] | arm["few_games_flag"], "team"])
    return Posterior(idata, d.teams, likelihood, provisional_teams=prov, config=cfg)
