"""Integration capstone: fit(features, cutoff) -> Posterior + predict_*.

Wires the leakage-safe per-cutoff feature panel through the match-level design,
the (a)/(c) widening switch, the PyMC scoreline model, and inference into a
Posterior whose predict_scoreline/predict_1x2 build the scoreline grid MANUALLY
from the posterior parameters (the likelihood is a Potential -> no observed RV to
sample_posterior_predictive from). ADVI is used so these stay fast; they are
still real end-to-end fits, so marked slow.
"""
import numpy as np
import pytest

from wcmodel.model.scoreline import fit


@pytest.mark.slow
def test_fit_then_predict_scoreline_is_a_normalised_grid(small_store):
    post = fit("2024-06-01", small_store, backend="advi", draws=150, seed=0, advi_iters=3000)
    grid = post.predict_scoreline("Brazil", "Argentina", neutral=False, max_goals=6)
    assert grid.shape == (7, 7)
    assert np.isclose(grid.sum(), 1.0, atol=1e-6)
    assert (grid >= 0).all()                      # no negative probabilities
    p = post.predict_1x2("Brazil", "Argentina", neutral=False, max_goals=6)
    assert np.isclose(p["home"] + p["draw"] + p["away"], 1.0, atol=1e-9)


@pytest.mark.slow
def test_predict_unknown_team_raises(small_store):
    post = fit("2024-06-01", small_store, backend="advi", draws=80, seed=0, advi_iters=2000)
    with pytest.raises(KeyError):
        post.predict_scoreline("Atlantis", "Brazil", neutral=True)


@pytest.mark.slow
def test_bivariate_poisson_fit_predicts_normalised(small_store):
    post = fit("2024-06-01", small_store, likelihood="bivariate_poisson",
               backend="advi", draws=120, seed=0, advi_iters=2500)
    g = post.predict_scoreline("Brazil", "Croatia", neutral=True, max_goals=6)
    assert np.isclose(g.sum(), 1.0, atol=1e-6) and (g >= 0).all()
