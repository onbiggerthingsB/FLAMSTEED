import numpy as np
import pytest
from wcmodel.sim.scoreline import RateBook, sample_score


def test_ratebook_exposes_per_draw_rates(small_store):
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=100, seed=0, advi_iters=2000)
    rb = RateBook(post)
    assert rb.n_draws == 100
    lh, la = rb.rates("Brazil", "Argentina", neutral=False, draw=0)
    assert lh > 0 and la > 0
    lh_n, _ = rb.rates("Brazil", "Argentina", neutral=True, draw=0)
    assert lh_n <= lh + 1e-9                      # neutral removes home advantage (home_adv>=0 typ.)
    with pytest.raises(KeyError):
        rb.rates("Atlantis", "Brazil", neutral=True, draw=0)


def test_ratebook_host_factor_scales_home_advantage(small_store):
    # T5: host_factor is a prediction-time scalar on the fitted home_adv in the SIM rate
    # builder too. k=1.0 reproduces the full (neutral=False) home rate exactly, k=0.0 the
    # neutral home rate exactly, and k=0.5 sits strictly between — monotonic in k. host_adv
    # enters the home rate only, so the away rate is identical across all of these.
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=100, seed=0, advi_iters=2000)
    rb = RateBook(post)
    lh_full, la_full = rb.rates("Brazil", "Argentina", neutral=False, draw=0)
    lh_neut, la_neut = rb.rates("Brazil", "Argentina", neutral=True, draw=0)
    lh_k1, la_k1 = rb.rates("Brazil", "Argentina", neutral=True, draw=0, host_factor=1.0)
    lh_k0, _ = rb.rates("Brazil", "Argentina", neutral=True, draw=0, host_factor=0.0)
    lh_half, la_half = rb.rates("Brazil", "Argentina", neutral=True, draw=0, host_factor=0.5)
    assert lh_k1 == pytest.approx(lh_full)            # k=1 == full home_adv
    assert lh_k0 == pytest.approx(lh_neut)            # k=0 == neutral
    assert lh_neut <= lh_half <= lh_full + 1e-12      # monotone in k (home_adv >= 0 typ.)
    assert lh_neut < lh_full                          # non-vacuity: home_adv actually fitted > 0
    assert la_full == la_half == la_k1                # away rate carries NO home term


def test_sample_score_dc_seeded_nonneg_ints():
    r1 = np.random.default_rng(3); r2 = np.random.default_rng(3)
    x, y = sample_score(1.4, 1.1, rng=r1, likelihood="dixon_coles", rho=-0.05, max_goals=12)
    x2, y2 = sample_score(1.4, 1.1, rng=r2, likelihood="dixon_coles", rho=-0.05, max_goals=12)
    assert (x, y) == (x2, y2)                      # seeded reproducible
    assert isinstance(x, (int, np.integer)) and x >= 0 and y >= 0


def test_sample_score_bp_generative_seeded():
    r1 = np.random.default_rng(3); r2 = np.random.default_rng(3)
    assert sample_score(1.4, 1.1, rng=r1, likelihood="bivariate_poisson", l3=0.1) == \
           sample_score(1.4, 1.1, rng=r2, likelihood="bivariate_poisson", l3=0.1)


def test_bp_l3_induces_positive_goal_correlation():
    rng = np.random.default_rng(0)
    xs, ys = zip(*[sample_score(1.3, 1.0, rng=rng, likelihood="bivariate_poisson", l3=0.6)
                   for _ in range(20000)])
    assert np.corrcoef(xs, ys)[0, 1] > 0.05        # shared l3 -> positive correlation
