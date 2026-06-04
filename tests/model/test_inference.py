"""Tests for the inference backend dispatch + the ADVI-falsely-tight check.

API NOTE (arviz 1.1.0): this arviz major migrated InferenceData -> xarray
DataTree. The constructed-idata tests therefore build groups via
``az.from_dict({"posterior": {...}})`` (the ``az.InferenceData(posterior=...)``
ctor in older arviz no longer accepts that kwarg), and ``advi_variance_check``
reads bounds off the ``ci_bound`` ("lower"/"upper") coordinate that arviz
1.1.0's ``az.hdi`` returns. See src/wcmodel/model/inference.py for the
provenance of each adaptation.
"""
import arviz as az
import numpy as np
import pytest

from tests.model.test_scoreline import _sim_design
from wcmodel.model.inference import advi_variance_check, sample
from wcmodel.model.scoreline import build_model


@pytest.mark.slow
def test_seeded_advi_is_reproducible():
    """Two ADVI fits with the same seed are bit-identical (hard project
    invariant). Not a degenerate match: the fixture below also checks the fit
    moved off the prior (att varies across teams)."""
    d, *_ = _sim_design(n_matches=200)
    m = build_model(d, "dixon_coles")
    a = sample(m, backend="advi", draws=100, seed=7, advi_iters=2000)
    b = sample(m, backend="advi", draws=100, seed=7, advi_iters=2000)
    va = a.posterior["mu"].mean().item()
    vb = b.posterior["mu"].mean().item()
    assert np.isclose(va, vb, atol=1e-6)
    # Guard against a degenerate "both return the prior mean" pass: a genuine
    # ADVI fit learns team-specific attack strengths, so att has spread > 0.
    att = a.posterior["att"].mean(("chain", "draw")).values
    assert float(att.std()) > 0.01


@pytest.mark.slow
def test_nuts_and_advi_both_return_idata():
    d, *_ = _sim_design(n_matches=200)
    m = build_model(d, "dixon_coles")
    for backend in ("advi", "nuts"):
        idata = sample(m, backend=backend, draws=80, tune=80, seed=0, advi_iters=2000)
        assert "mu" in idata.posterior


def test_unknown_backend_raises_valueerror():
    """Cheap fast guard (no sampling): an unknown backend is rejected by name."""
    d, *_ = _sim_design(n_matches=40)
    m = build_model(d, "dixon_coles")
    with pytest.raises(ValueError, match="unknown backend"):
        sample(m, backend="nope", draws=10, seed=0)


def test_pathfinder_backend_raises_notimplemented():
    """pathfinder is NOT available in pymc 6.0.1 (pm.fit methods are advi /
    fullrank_advi / svgd / asvgd; no pymc_experimental/nutpie installed). The
    branch must fail loud + actionable, never crash cryptically."""
    d, *_ = _sim_design(n_matches=40)
    m = build_model(d, "dixon_coles")
    with pytest.raises(NotImplementedError, match="pathfinder"):
        sample(m, backend="pathfinder", draws=10, seed=0)


def _idata(var, sigma, n=2000, seed=0):
    """A 1-param posterior-only idata-like object (arviz 1.1.0 DataTree)."""
    rng = np.random.default_rng(seed)
    return az.from_dict({"posterior": {var: rng.normal(0.0, sigma, (1, n))}})


def test_advi_variance_check_flags_false_tightness():
    """tight (0.3 sigma) vs wide (1.0 sigma): ADVI HDI width ~= 0.3x NUTS,
    which is below the (1 - rel_tol) = 0.5 threshold -> flagged True."""
    tight = _idata("att", 0.3)
    wide = _idata("att", 1.0)
    rep = advi_variance_check(tight, wide, params=["att"], rel_tol=0.5)
    assert rep["att"]["flagged"] is True
    assert rep["att"]["ratio"] < 0.5


def test_advi_variance_check_does_not_flag_equal_widths():
    """Proves the check is not always-true: two same-sigma posteriors have
    ratio ~= 1.0 (well above 0.5) -> flagged False."""
    a = _idata("att", 0.7, seed=1)
    b = _idata("att", 0.7, seed=2)
    rep = advi_variance_check(a, b, params=["att"], rel_tol=0.5)
    assert rep["att"]["flagged"] is False
    assert rep["att"]["ratio"] > 0.8
