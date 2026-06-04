"""ScorelineModel interface + the two PyMC likelihoods.

Hierarchical attack/defense with SOFT sum-to-zero centering (att = att_raw -
mean(att_raw)); baseline mu; home_adv applied only on non-neutral matches; the
likelihood is TIME-DECAY-WEIGHTED via a Potential (weight = design.weight, which
already carries decay_weight; widening mechanism (a) multiplies into it). Elo is
NOT used here (independent prior): the model learns attack/defense from goals +
team indices + the decay weight only — it never reads elo_pre or any rating.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pymc as pm
import pytensor.tensor as pt

from wcmodel.config import load_config
from wcmodel.model.likelihoods import bp_loglik_pt, dc_loglik_pt
from wcmodel.model.panel import DesignData


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
    def build(self, d: DesignData, weight: np.ndarray) -> pm.Model: ...


class DixonColesModel(ScorelineModel):
    def build(self, d, weight):
        p = load_config()["model"]["prior"]
        with pm.Model() as m:
            att, defe, mu, home_adv = _priors(d, p)
            # rho CONTRACT (likelihoods.dc_loglik_pt): a tau cell <= 0 -> log(tau)
            # = NaN -> NUTS breaks. An UNBOUNDED Normal can draw a tail value that
            # makes a tau cell non-positive. International goal rates are ~<=2.5
            # each (lh*la <~ 6.25), so |rho| <= 0.15 keeps tau(0,0)=1-lh*la*rho>0
            # and the off-diagonals positive for all realistic rates. The bound is
            # a safe Phase-2 default (Phase-4 may tune); it is what makes the model
            # structurally unable to produce tau<=0.
            rho = pm.TruncatedNormal(
                "rho", mu=0.0, sigma=p["rho_scale"], lower=-0.15, upper=0.15
            )
            lh, la = _rates(d, att, defe, mu, home_adv)
            ll = dc_loglik_pt(d.home_goals, d.away_goals, lh, la, rho)
            pm.Potential("like", pt.sum(pt.as_tensor_variable(weight) * ll))
        return m


class BivariatePoissonModel(ScorelineModel):
    def build(self, d, weight):
        p = load_config()["model"]["prior"]
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
    d: DesignData, likelihood: str | None = None, weight: np.ndarray | None = None
) -> pm.Model:
    likelihood = likelihood or load_config()["model"]["likelihood"]
    w = d.weight if weight is None else weight
    return _REGISTRY[likelihood]().build(d, w)
