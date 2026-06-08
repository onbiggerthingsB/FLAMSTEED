import numpy as np
import pytest
from wcmodel.sim.scoreline import RateBook, sample_score


def _stub_posterior(mu=0.10, home_adv=0.30, k_neutral=0.5):
    """Hand-built Posterior (NO sampling) carrying exactly what RateBook reads:
    idata.posterior att/def/mu/home_adv/rho, teams, likelihood, and the `model`
    config block (self._cfg) holding neutral_home_adv_fraction. Lets the neutral
    rate test be deterministic and fast (no fit)."""
    import arviz as az

    from wcmodel.config import load_config
    from wcmodel.model.posterior import Posterior
    posterior = {
        "att": np.zeros((1, 2, 2)),
        "def": np.zeros((1, 2, 2)),
        "mu": np.full((1, 2), mu),
        "home_adv": np.full((1, 2), home_adv),
        "rho": np.zeros((1, 2)),
    }
    idata = az.from_dict({"posterior": posterior})
    cfg = load_config()
    cfg["model"]["neutral_home_adv_fraction"] = k_neutral
    return Posterior(idata, ["A", "B"], "dixon_coles", provisional_teams=set(),
                     config=cfg)


def test_ratebook_neutral_uses_average_environment():
    """[LOAD-BEARING] RateBook.rates(neutral=True) must MIRROR predict_scoreline:
    apply k_neutral*home_adv to BOTH sides (the average environment), NOT zero the
    home term. So the sim's per-draw neutral rates equal exp(mu + k*home_adv) on each
    side — no card-vs-progression divergence. host_factor and non-neutral branches
    stay UNCHANGED."""
    mu, ha, k = 0.10, 0.30, 0.5
    post = _stub_posterior(mu=mu, home_adv=ha, k_neutral=k)
    rb = RateBook(post)
    # NEUTRAL (FIX): both sides at mu + k*home_adv.
    lh_n, la_n = rb.rates("A", "B", neutral=True, draw=0)
    assert lh_n == pytest.approx(np.exp(mu + k * ha))
    assert la_n == pytest.approx(np.exp(mu + k * ha))      # away side gets the term too
    # It is STRICTLY above the buggy away-rate (exp(mu)) on both sides.
    assert lh_n > np.exp(mu) + 1e-9 and la_n > np.exp(mu) + 1e-9
    # NON-NEUTRAL: UNCHANGED — home carries full home_adv, away has no home term.
    lh_f, la_f = rb.rates("A", "B", neutral=False, draw=0)
    assert lh_f == pytest.approx(np.exp(mu + ha))
    assert la_f == pytest.approx(np.exp(mu))
    # HOST_FACTOR set: UNCHANGED — home = host_factor*home_adv, away has no home term.
    lh_h, la_h = rb.rates("A", "B", neutral=True, draw=0, host_factor=0.5)
    assert lh_h == pytest.approx(np.exp(mu + 0.5 * ha))
    assert la_h == pytest.approx(np.exp(mu))


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
    # builder too. k=1.0 reproduces the full (neutral=False) HOME rate exactly; k=0.0 the
    # bare-away home rate (no home term); k=0.5 sits strictly between — monotone in k.
    # The host_factor path puts the term on the HOME side only, so the away rate is
    # identical across all host_factor values.
    #
    # NB after the neutral-venue calibration fix, neutral=True is the AVERAGE-environment
    # path (k_neutral*home_adv on BOTH sides), so it is NO LONGER equal to host_factor=0.0
    # (bare away). With k_neutral=0.5 it instead coincides with host_factor=0.5 on the home
    # side, but unlike the host path it ALSO lifts the away rate. We assert these explicitly.
    from wcmodel.config import load_config
    from wcmodel.model.scoreline import fit
    k_neutral = load_config()["model"]["neutral_home_adv_fraction"]
    post = fit("2024-06-01", small_store, backend="advi", draws=100, seed=0, advi_iters=2000)
    rb = RateBook(post)
    lh_full, la_full = rb.rates("Brazil", "Argentina", neutral=False, draw=0)
    lh_neut, la_neut = rb.rates("Brazil", "Argentina", neutral=True, draw=0)
    lh_k1, la_k1 = rb.rates("Brazil", "Argentina", neutral=True, draw=0, host_factor=1.0)
    lh_k0, la_k0 = rb.rates("Brazil", "Argentina", neutral=True, draw=0, host_factor=0.0)
    lh_half, la_half = rb.rates("Brazil", "Argentina", neutral=True, draw=0, host_factor=0.5)
    assert lh_k1 == pytest.approx(lh_full)            # k=1 == full home_adv (HOME side)
    assert lh_k0 < lh_full                            # k=0 == bare away (no home term)
    assert lh_k0 <= lh_half <= lh_full + 1e-12        # monotone in host_factor k
    # The away rate is invariant across the HOST path (host term is home-side only).
    assert la_full == la_half == la_k1 == la_k0
    # The NEUTRAL fix: average environment on both sides -> home rate matches
    # host_factor=k_neutral, but the away rate is lifted ABOVE the bare-away host path.
    assert lh_neut == pytest.approx(rb.rates("Brazil", "Argentina", neutral=True,
                                             draw=0, host_factor=k_neutral)[0])
    assert lh_neut > lh_k0 + 1e-12                    # neutral now scores above bare-away home
    assert la_neut > la_full + 1e-12                  # neutral lifts the away rate too (the fix)


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
