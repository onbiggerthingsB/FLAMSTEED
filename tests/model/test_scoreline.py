"""Tests for the PyMC ScorelineModel (Dixon-Coles + bivariate-Poisson).

`_sim_design` is defined at module scope so later tasks can import a known-good
simulated DesignData with recoverable attack/defense strengths.
"""
import numpy as np
import pandas as pd
import pytest

from wcmodel.model.panel import build_design
from wcmodel.model.scoreline import build_model


def _sim_design(seed=0, n_teams=6, n_matches=600):
    rng = np.random.default_rng(seed)
    att = rng.normal(0, 0.4, n_teams)
    dfn = rng.normal(0, 0.4, n_teams)
    att -= att.mean()
    dfn -= dfn.mean()
    mu, home = 0.1, 0.3
    h = rng.integers(0, n_teams, n_matches)
    a = rng.integers(0, n_teams, n_matches)
    ok = h != a
    h, a = h[ok], a[ok]
    lh = np.exp(mu + home + att[h] - dfn[a])
    la = np.exp(mu + att[a] - dfn[h])
    hg = rng.poisson(lh)
    ag = rng.poisson(la)
    mp = pd.DataFrame(
        {
            "match_id": np.arange(len(h)).astype(str),
            "date": pd.Timestamp("2020-01-01"),
            "home_team": h.astype(str),
            "away_team": a.astype(str),
            "home_goals": hg,
            "away_goals": ag,
            "neutral": False,
            "match_type": "friendly",
            "weight": 1.0,
            "home_provisional": False,
            "away_provisional": False,
        }
    )
    return build_design(mp), att, dfn


def test_dixon_coles_model_has_expected_rvs():
    d, *_ = _sim_design()
    model = build_model(d, likelihood="dixon_coles")
    names = {v.name for v in model.free_RVs}
    assert {"att_raw", "def_raw", "mu", "home_adv", "rho"} <= names


def test_bivariate_poisson_model_has_expected_rvs():
    d, *_ = _sim_design()
    model = build_model(d, likelihood="bivariate_poisson")
    names = {v.name for v in model.free_RVs}
    assert {"att_raw", "def_raw", "mu", "home_adv", "log_lambda3"} <= names


@pytest.mark.slow
def test_recovers_attack_strength_ordering():
    import pymc as pm

    d, att, dfn = _sim_design()
    model = build_model(d, likelihood="dixon_coles")
    with model:
        idata = pm.sample(
            300, tune=300, chains=2, cores=1, random_seed=0, progressbar=False
        )
    est = idata.posterior["att"].mean(("chain", "draw")).values
    from scipy.stats import spearmanr

    assert spearmanr(est, att).correlation > 0.8


# ---- CRITICAL verification duties (load-bearing model) ----


def test_soft_sum_to_zero_centering():
    """att/def are Deterministics mean-centered to ~0 (soft sum-to-zero)."""
    import pymc as pm

    d, *_ = _sim_design()
    model = build_model(d, likelihood="dixon_coles")
    det_names = {v.name for v in model.deterministics}
    assert {"att", "def"} <= det_names
    # Draw from the prior: each posterior-predictive att/def sample sums to ~0.
    with model:
        prior = pm.sample_prior_predictive(draws=50, random_seed=0)
    att = prior.prior["att"].values  # (chain, draw, n_teams)
    defe = prior.prior["def"].values
    assert np.allclose(att.sum(axis=-1), 0.0, atol=1e-8)
    assert np.allclose(defe.sum(axis=-1), 0.0, atol=1e-8)


@pytest.mark.slow
def test_dixon_coles_no_nan_divergences():
    """rho contract: the bounded prior cannot make a tau cell <= 0, so NUTS
    sampling the DC model produces no NaN-logp divergences."""
    import pymc as pm

    d, *_ = _sim_design()
    model = build_model(d, likelihood="dixon_coles")
    with model:
        idata = pm.sample(
            200, tune=200, chains=2, cores=1, random_seed=0, progressbar=False
        )
    # Zero (or near-zero) divergences => no tau<=0 NaN traps were hit.
    assert int(idata.sample_stats.diverging.sum()) == 0


@pytest.mark.slow
def test_bivariate_poisson_builds_and_samples():
    """The BP likelihood builds + samples on the fixture without error/NaN."""
    import pymc as pm

    d, *_ = _sim_design()
    model = build_model(d, likelihood="bivariate_poisson")
    with model:
        idata = pm.sample(
            150, tune=150, chains=2, cores=1, random_seed=0, progressbar=False
        )
    assert int(idata.sample_stats.diverging.sum()) == 0
    assert np.isfinite(idata.posterior["att"].values).all()


def test_decay_weight_actually_used():
    """Potential multiplies per-match log-lik by the passed weight, so a model
    built with all-zero weights has a flat (prior-only) posterior on att while
    all-one weights does not. We verify by comparing the prior-vs-posterior
    spread: zero-weight posterior == prior; unit-weight posterior is tighter."""
    import pymc as pm

    d, att, _ = _sim_design()
    zero_w = np.zeros_like(d.weight)

    # Zero weights: the Potential contributes 0 -> posterior == prior. The att
    # Deterministic is att_raw - mean(att_raw); under the prior its per-team
    # std is governed only by sigma_att, NOT informed by goals.
    m0 = build_model(d, likelihood="dixon_coles", weight=zero_w)
    with m0:
        i0 = pm.sample(
            150, tune=150, chains=2, cores=1, random_seed=0, progressbar=False
        )
    # Unit weights: goals inform att -> posterior means should correlate with
    # the true att, which the prior-only (zero-weight) fit cannot do.
    m1 = build_model(d, likelihood="dixon_coles", weight=np.ones_like(d.weight))
    with m1:
        i1 = pm.sample(
            150, tune=150, chains=2, cores=1, random_seed=0, progressbar=False
        )
    from scipy.stats import spearmanr

    corr0 = abs(spearmanr(i0.posterior["att"].mean(("chain", "draw")).values, att).correlation)
    corr1 = abs(spearmanr(i1.posterior["att"].mean(("chain", "draw")).values, att).correlation)
    # Unit-weight fit learns the ordering; zero-weight fit (prior only) cannot.
    assert corr1 > 0.8
    assert corr1 > corr0
