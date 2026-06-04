import numpy as np
from wcmodel.sim.tournament import simulate_tournament

from tests.sim.conftest import tiny_bracket


def test_progression_probs_are_coherent(small_store):
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=120, seed=0, advi_iters=2500)
    res = simulate_tournament(post, bracket=tiny_bracket(), n_sims=2000, seed=0,
                              max_goals=8, et_scale=0.333, pen_home_prob=0.5)
    probs = res.progression          # DataFrame: index=team, cols=stages
    assert np.isclose(probs["champion"].sum(), 1.0, atol=1e-9)
    assert (probs["champion"] <= probs["reach_final"] + 1e-12).all()
    assert (probs["reach_final"] <= probs["reach_sf"] + 1e-12).all()
    assert (res.se["champion"] >= 0).all()


def test_seeded_determinism(small_store):
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=80, seed=0, advi_iters=2000)
    a = simulate_tournament(post, bracket=tiny_bracket(), n_sims=500, seed=0, max_goals=8,
                            et_scale=0.333, pen_home_prob=0.5)
    b = simulate_tournament(post, bracket=tiny_bracket(), n_sims=500, seed=0, max_goals=8,
                            et_scale=0.333, pen_home_prob=0.5)
    assert a.progression.equals(b.progression)
