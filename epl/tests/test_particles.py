"""The effective posterior, the per-fixture grids and the widening branch (plan v2 T4).

Every test here is a PARITY test against the production predict path, because
that is the whole point of the module: the simulator must sample from the same
per-fixture law the forecast publishes, not from a nearly-identical one. The
oracles are `wcmodel.model.draw_api` (rates, mean grid, production grid) and
`epl.dcfit`'s own `ColdStartPosterior.predict_scoreline` — never a re-derivation
of the arithmetic in this file.

Three defects are pinned here on purpose:

* P0-2 — `wcmodel.sim.scoreline.RateBook` reads `posterior.idata.posterior`
  directly and therefore CANNOT see a `ColdStartPosterior`'s extension rows; a
  promoted club raises `IndexError` in the WC sampler. Asserted as a live
  positive control, so the reason `ParticleBook` exists stays visible.
* D11 — the goal grid is truncated at the PRODUCTION 10, not the WC sim's 12,
  and the truncated tail mass is measured rather than assumed negligible.
* D12 — mechanism-(c) widening is a per-fixture Bernoulli mixture whose marginal
  is EXACTLY the production grid. The tests read that marginal off the CDF
  arrays the sampler will actually consume, and the positive control shows the
  alpha branch is load-bearing (drop it and parity breaks by ~1e-2).

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_particles.py -q
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from epl import anchor as anchor_mod, dcfit, freeze, particles
from wcmodel.model import draw_api
from wcmodel.model.draw_api import PRODUCTION_MAX_GOALS, FixtureCtx
from wcmodel.model.posterior import Posterior
from wcmodel.sim.scoreline import RateBook

#: Small enough to keep the suite quick, large enough that a mean over
#: particles is not a single draw in disguise.
S = 64

TEAMS = tuple(f"club_{i:02d}" for i in range(20))
PROMOTED = "coventry"


# ---------------------------------------------------------------------------
# synthetic posteriors — the shape of a real fit, none of the ADVI cost
# ---------------------------------------------------------------------------

def _idata(teams, n_draws=S, seed=0, mu_loc=0.1, rho_scale=0.02):
    """A toy `idata` carrying every parameter the DC predict path reads."""
    rng = np.random.default_rng(seed)
    n = len(teams)
    ds = xr.Dataset({
        "att": (("chain", "draw", "team"), rng.normal(0, .3, (1, n_draws, n))),
        "def": (("chain", "draw", "team"), rng.normal(0, .3, (1, n_draws, n))),
        "mu": (("chain", "draw"), rng.normal(mu_loc, .05, (1, n_draws))),
        "home_adv": (("chain", "draw"), rng.normal(0.25, .05, (1, n_draws))),
        "rho": (("chain", "draw"), rng.normal(0.0, rho_scale, (1, n_draws))),
        "sigma_att": (("chain", "draw"), np.abs(rng.normal(.4, .05, (1, n_draws)))),
        "sigma_def": (("chain", "draw"), np.abs(rng.normal(.4, .05, (1, n_draws)))),
    })
    # `att`/`def` are centred, as the model's soft sum-to-zero makes them.
    for name in ("att", "def"):
        ds[name] = ds[name] - ds[name].mean("team")

    class _IData:
        posterior = ds

    return _IData()


def _posterior(teams=TEAMS, provisional=(), likelihood="dixon_coles",
               cfg=None, covariate_transforms=None, **kw):
    return Posterior(_idata(teams, **kw), list(teams), likelihood,
                     provisional_teams=provisional,
                     config=cfg or freeze.frozen_wcmodel_config(),
                     covariate_transforms=covariate_transforms)


def _cold_start_posterior(**kw):
    """A `ColdStartPosterior` built exactly the way `epl.dcfit.fit_epl` builds one.

    The rating spread is league-shaped on purpose (sd ~ 87 Elo points, the
    promoted club seeded at the division mean - 75, per the frozen protocol), so
    the promoted club's prior draws land where a real one's do. A toy spread
    would push its z to -3 and the resulting goal rates past the 10-goal grid,
    which would test the truncation gate rather than the cold-start path.
    """
    cfg = freeze.frozen_wcmodel_config()
    base = _posterior(TEAMS, cfg=cfg, **kw)
    ratings = {t: 1450.0 + 15.0 * i for i, t in enumerate(TEAMS)}
    r = np.array(list(ratings.values()), float)
    mean, sd = float(r.mean()), float(r.std())
    state = anchor_mod.AnchorState(
        cutoff=pd.Timestamp("2026-08-21"),
        ratings=dict(ratings, **{PROMOTED: mean - 75.0}),
        teams=tuple(TEAMS), mean=mean, sd=sd)
    assert -1.2 < state.z(PROMOTED) < -0.5, "the promoted seed is league-shaped"
    extra = {PROMOTED: dcfit._prior_draws(state, PROMOTED, cfg, base, int(cfg["seed"]))}
    return dcfit.ColdStartPosterior(base, extra)


# ---------------------------------------------------------------------------
# 1. the effective posterior — cold-start rows included (D11 / P0-2)
# ---------------------------------------------------------------------------

def test_from_cold_start_posterior_includes_promoted_rows():
    post = _cold_start_posterior()
    book = particles.ParticleBook.from_posterior(post)

    assert book.att.shape == (21, S), "the promoted club's att row must be there"
    assert book.defe.shape == (21, S)
    assert book.mu.shape == (S,) and book.home_adv.shape == (S,)
    assert book.rho.shape == (S,)
    assert book.sigma_att.shape == (S,) and book.sigma_def.shape == (S,)
    assert book.teams[-1] == PROMOTED and book.idx[PROMOTED] == 20
    assert book.cold_start == {PROMOTED}
    assert PROMOTED in book.provisional          # cold start IS low information

    # ...and the promoted club is priceable: a full, proper per-particle law.
    fc = particles.fixture_cdfs(book, PROMOTED, TEAMS[0])
    assert fc.cdf.shape == (S, (PRODUCTION_MAX_GOALS + 1) ** 2)
    assert np.isfinite(fc.cdf).all()
    assert np.allclose(fc.cdf[:, -1], 1.0, atol=0.0)
    assert np.all(np.diff(fc.cdf, axis=1) >= -1e-15)          # monotone
    assert np.allclose(fc.one_x_two.sum(axis=1), 1.0, atol=1e-12)

    # POSITIVE CONTROL — this is the defect ParticleBook exists to fix. The WC
    # sampler reads idata directly, so it never sees the extension rows.
    rb = RateBook(post)
    assert rb.att.shape == (20, S), "RateBook is blind to the cold-start rows"
    with pytest.raises(IndexError):
        rb.rates(PROMOTED, TEAMS[0], False, 0)


# ---------------------------------------------------------------------------
# 2. the rate leg — bitwise, not approximately (D11)
# ---------------------------------------------------------------------------

def test_rates_bitwise_equal_per_draw_rates():
    post = _cold_start_posterior()
    book = particles.ParticleBook.from_posterior(post)

    pairs = ((TEAMS[0], TEAMS[1]), (TEAMS[5], TEAMS[9]),
             (PROMOTED, TEAMS[3]), (TEAMS[7], PROMOTED))
    for h, a in pairs:
        lh, la = book.rates(h, a)
        rh, ra = draw_api.per_draw_rates(post, FixtureCtx(home=h, away=a))
        assert lh.tobytes() == rh.tobytes(), f"home rate drifted on {h}-{a}"
        assert la.tobytes() == ra.tobytes(), f"away rate drifted on {h}-{a}"

    # CANARY — the comparison above is not comparing two constants.
    lh, la = book.rates(TEAMS[0], TEAMS[1])
    assert lh.shape == (S,) and np.all(lh > 0.0)
    assert not np.array_equal(lh, la)
    assert not np.array_equal(lh, book.rates(TEAMS[2], TEAMS[1])[0])


# ---------------------------------------------------------------------------
# 3. the grid leg — the vectorised build reproduces the per-draw loop (D13)
# ---------------------------------------------------------------------------

def test_mean_grid_allclose_mean_grid_over_draws_1e_12():
    post = _cold_start_posterior()
    book = particles.ParticleBook.from_posterior(post)
    h, a = TEAMS[2], TEAMS[8]
    lh, la = book.rates(h, a)

    G, excluded = particles.fixture_grids(lh, la, book.rho, book.max_goals)
    assert G.shape == (S, 11, 11)
    assert excluded.shape == (S,)
    assert np.allclose(G.sum(axis=(1, 2)), 1.0, atol=1e-12)   # per-particle renorm

    gbar = particles.mean_grid(G)
    ref = draw_api.mean_grid_over_draws(
        lh, la, likelihood="dixon_coles", rho=book.rho,
        max_goals=PRODUCTION_MAX_GOALS)
    assert gbar.shape == (11, 11)
    assert np.max(np.abs(gbar - ref)) < 1e-12

    # POSITIVE CONTROL — the per-draw Dixon-Coles correction is really applied.
    # Build the same grids at rho = 0 and the parity above fails by orders of
    # magnitude, so a silent independent-Poisson grid could not pass.
    flat, _ = particles.fixture_grids(lh, la, np.zeros_like(book.rho),
                                      book.max_goals)
    assert np.max(np.abs(particles.mean_grid(flat) - ref)) > 1e-6


# ---------------------------------------------------------------------------
# 4. the widening branch — exact per-fixture marginal parity (D12)
# ---------------------------------------------------------------------------

def test_widened_mixture_equals_production_grid_1e_12():
    post = _cold_start_posterior()
    book = particles.ParticleBook.from_posterior(post)
    alpha = book.alpha
    assert alpha == 0.5, "the frozen mechanism-(c) strength"

    # provisional fixture: (1-a) * gbar + a * q IS the production grid
    h, a = PROMOTED, TEAMS[3]
    G, _ = particles.fixture_grids(*book.rates(h, a), book.rho, book.max_goals)
    gbar = particles.mean_grid(G)
    q = particles.widening_component(gbar, alpha)
    assert q.shape == gbar.shape
    assert q.sum() == pytest.approx(1.0, abs=1e-12)
    assert np.all(q >= 0.0)

    prod = draw_api.production_grid(post, FixtureCtx(home=h, away=a))
    mix = (1.0 - alpha) * gbar + alpha * q
    assert np.max(np.abs(mix - prod)) < 1e-12

    # POSITIVE CONTROL — the branch is load-bearing: the un-widened mean grid is
    # NOT the production grid for a provisional fixture.
    assert np.max(np.abs(gbar - prod)) > 1e-4

    # non-provisional fixture: production is the mean grid, no branch at all
    h2, a2 = TEAMS[0], TEAMS[1]
    G2, _ = particles.fixture_grids(*book.rates(h2, a2), book.rho, book.max_goals)
    gbar2 = particles.mean_grid(G2)
    prod2 = draw_api.production_grid(post, FixtureCtx(home=h2, away=a2))
    assert np.max(np.abs(gbar2 - prod2)) < 1e-12
    assert particles.fixture_cdfs(book, h2, a2).q_cdf is None


def test_mixture_of_sampled_cdfs_reproduces_dcfit_pricing_exactly():
    """The parity that matters: read off the CDF arrays the sampler consumes.

    `FixtureCDF` is what `epl.leaguesim` will inverse-CDF against, so the
    per-fixture marginal is reconstructed from `cdf`/`q_cdf` themselves —
    not from the intermediate grids — and compared to what `epl.dcfit`'s
    posterior prices today.
    """
    post = _cold_start_posterior()
    book = particles.ParticleBook.from_posterior(post)

    for h, a in ((PROMOTED, TEAMS[0]), (TEAMS[4], PROMOTED), (TEAMS[1], TEAMS[2])):
        fc = particles.fixture_cdfs(book, h, a)
        per_particle = np.diff(fc.cdf, axis=1, prepend=0.0)      # (S, n^2)
        assert np.all(per_particle >= -1e-15)
        marginal = per_particle.mean(axis=0)
        if fc.q_cdf is not None:
            q = np.diff(fc.q_cdf, prepend=0.0)
            marginal = (1.0 - book.alpha) * marginal + book.alpha * q
        assert fc.provisional == (h == PROMOTED or a == PROMOTED)
        assert (fc.q_cdf is not None) == fc.provisional

        prod = post.predict_scoreline(h, a).reshape(-1)
        assert np.max(np.abs(marginal - prod)) < 1e-12, f"{h}-{a} marginal drifted"

        p = post.predict_1x2(h, a)
        n = PRODUCTION_MAX_GOALS + 1
        g = marginal.reshape(n, n)
        assert np.tril(g, -1).sum() == pytest.approx(p["home"], abs=1e-12)
        assert np.trace(g) == pytest.approx(p["draw"], abs=1e-12)
        assert np.triu(g, 1).sum() == pytest.approx(p["away"], abs=1e-12)

        # the per-particle 1X2 legs average to the un-widened mean grid's 1X2
        m = per_particle.mean(axis=0).reshape(n, n)
        assert np.allclose(
            fc.one_x_two.mean(axis=0),
            [np.tril(m, -1).sum(), np.trace(m), np.triu(m, 1).sum()],
            atol=1e-12)

    # POSITIVE CONTROL — without the alpha branch a provisional fixture's
    # sampled marginal is NOT what production issues.
    fc = particles.fixture_cdfs(book, PROMOTED, TEAMS[0])
    unwidened = np.diff(fc.cdf, axis=1, prepend=0.0).mean(axis=0)
    prod = post.predict_scoreline(PROMOTED, TEAMS[0]).reshape(-1)
    assert np.max(np.abs(unwidened - prod)) > 1e-4


# ---------------------------------------------------------------------------
# 5. truncation — production 10, and the excluded tail is measured (D11)
# ---------------------------------------------------------------------------

def test_max_goals_is_production_10_not_sim_12():
    cfg = freeze.frozen_wcmodel_config()
    assert cfg["sim"]["max_goals"] == 12, "the WC sim's truncation, for contrast"
    assert PRODUCTION_MAX_GOALS == 10

    book = particles.ParticleBook.from_posterior(_cold_start_posterior())
    assert book.max_goals == PRODUCTION_MAX_GOALS
    assert book.max_goals != cfg["sim"]["max_goals"]

    fc = particles.fixture_cdfs(book, TEAMS[0], TEAMS[1])
    assert fc.cdf.shape[1] == 11 * 11
    G, _ = particles.fixture_grids(*book.rates(TEAMS[0], TEAMS[1]),
                                   book.rho, book.max_goals)
    assert G.shape[1:] == (11, 11)


def test_excluded_mass_is_flagged_at_5e_3_and_stops_only_above_2e_2():
    """D11 v1.0.1 — the owner ruling of 2026-08-19.

    Recorded in `reports/epl_sim_amendments.md` entry A1, before this guard was
    touched. The 5e-3 number is KEPT, but its meaning changes from hard-stop to
    FLAG: the fixture's excluded-mass statistics are recorded and reported and
    the run completes, because production truncates at the same 10 goals and
    discards the same tail silently. A particle-mean above 2e-2 — pre-stated in
    A1 as 4x the worst fixture observed at the 2026-08-21 opener — still fails
    the run closed, because that is a mis-scaled rate rather than a cold-start
    tail.

    This test replaces `test_excluded_mass_logged_and_fails_above_5e_3`, which
    asserted the old semantics (stop at 5e-3).
    """
    assert particles.FLAG_EXCLUDED_MASS == 5e-3
    assert particles.HARD_STOP_EXCLUDED_MASS == 2e-2
    assert particles.MAX_EXCLUDED_MASS == particles.FLAG_EXCLUDED_MASS, \
        "the old name is kept as an alias for the flag threshold"

    book = particles.ParticleBook.from_posterior(_cold_start_posterior())
    fc = particles.fixture_cdfs(book, TEAMS[0], TEAMS[1])
    # measured, not assumed: a real (tiny) tail mass is recorded, not a zero.
    assert 0.0 < fc.excluded_mean < particles.FLAG_EXCLUDED_MASS
    assert fc.excluded["flagged"] is False
    assert fc.excluded["mean"] == fc.excluded_mean
    for key in ("mean", "median", "worst"):
        assert np.isfinite(fc.excluded[key]), key
    assert fc.excluded["n_over_1pct"] == 0

    # BETWEEN the two thresholds: recorded, reported, NOT raised. The law it
    # hands the engine is still a proper one.
    warm = particles.ParticleBook.from_posterior(_cold_start_posterior(mu_loc=1.0))
    lh, la = warm.rates(TEAMS[0], TEAMS[1])
    _, excluded = particles.fixture_grids(lh, la, warm.rho, warm.max_goals)
    assert particles.FLAG_EXCLUDED_MASS < excluded.mean() \
        < particles.HARD_STOP_EXCLUDED_MASS
    flagged = particles.fixture_cdfs(warm, TEAMS[0], TEAMS[1])
    assert flagged.excluded["flagged"] is True
    assert flagged.excluded["mean"] == pytest.approx(float(excluded.mean()))
    assert flagged.excluded["median"] == pytest.approx(float(np.median(excluded)))
    assert flagged.excluded["worst"] == pytest.approx(float(excluded.max()))
    assert flagged.excluded["n_over_1pct"] == int((excluded > 0.01).sum()) > 0
    assert flagged.cdf.shape == (warm.n_particles, warm.n_scorelines)
    assert np.allclose(flagged.cdf[:, -1], 1.0)

    # ABOVE the pre-stated ceiling — a mis-scaled rate, which is the failure
    # mode the ceiling exists for — still fails CLOSED.
    hot = particles.ParticleBook.from_posterior(_cold_start_posterior(mu_loc=2.4))
    lh, la = hot.rates(TEAMS[0], TEAMS[1])
    _, excluded = particles.fixture_grids(lh, la, hot.rho, hot.max_goals)
    assert excluded.mean() > particles.HARD_STOP_EXCLUDED_MASS
    with pytest.raises(particles.ExcludedMassTooLarge):
        particles.fixture_cdfs(hot, TEAMS[0], TEAMS[1])


# ---------------------------------------------------------------------------
# 6. what this module refuses (v1 scope)
# ---------------------------------------------------------------------------

def test_bivariate_or_covariates_fail_closed():
    # a bivariate-Poisson posterior is out of v1 scope
    with pytest.raises(particles.UnsupportedPosterior):
        particles.ParticleBook.from_posterior(
            _posterior(likelihood="bivariate_poisson"))

    # covariates enabled in the config
    cfg = freeze.frozen_wcmodel_config()
    cfg["model"]["covariates"]["enabled"] = ["rest_days"]
    with pytest.raises(particles.UnsupportedPosterior):
        particles.ParticleBook.from_posterior(_posterior(cfg=cfg))

    # ...or a persisted covariate transform, even with an empty enabled list
    with pytest.raises(particles.UnsupportedPosterior):
        particles.ParticleBook.from_posterior(
            _posterior(covariate_transforms={"rest_days": object()}))

    # POSITIVE CONTROL — the same posterior with neither is accepted.
    assert particles.ParticleBook.from_posterior(_posterior()).likelihood \
        == "dixon_coles"


# ---------------------------------------------------------------------------
# 7. the bundle — persisted, hashed, cold rows intact (D14)
# ---------------------------------------------------------------------------

def test_save_load_roundtrip_hash_stable_and_cold_rows_survive(tmp_path):
    post = _cold_start_posterior()
    book = particles.ParticleBook.from_posterior(post)
    path = tmp_path / "particles.npz"
    book.save(path)
    assert path.exists() and path.with_suffix(".json").exists()

    back = particles.ParticleBook.load(path)
    assert back.content_hash() == book.content_hash()
    assert back.teams == book.teams and back.idx == book.idx
    assert back.att.shape == (21, S)
    for name in ("att", "defe", "mu", "home_adv", "rho", "sigma_att", "sigma_def"):
        assert np.array_equal(getattr(back, name), getattr(book, name)), name
    assert back.cold_start == {PROMOTED} and PROMOTED in back.provisional
    assert back.provisional == book.provisional
    assert (back.likelihood, back.alpha, back.max_goals, back.cfg_hash) == \
        (book.likelihood, book.alpha, book.max_goals, book.cfg_hash)

    # the reloaded book prices the promoted club identically, widening included
    a1 = particles.fixture_cdfs(book, PROMOTED, TEAMS[0])
    a2 = particles.fixture_cdfs(back, PROMOTED, TEAMS[0])
    assert np.array_equal(a1.cdf, a2.cdf)
    assert np.array_equal(a1.q_cdf, a2.q_cdf)
    assert a1.excluded_mean == a2.excluded_mean

    # POSITIVE CONTROL — the hash is over the arrays, so one nudged particle
    # (and, separately, one changed flag) changes it.
    tampered = particles.ParticleBook.load(path)
    tampered.att[0, 0] += 1e-12
    assert tampered.content_hash() != book.content_hash()
    relabelled = particles.ParticleBook.load(path)
    relabelled.provisional = frozenset()
    assert relabelled.content_hash() != book.content_hash()


# ---------------------------------------------------------------------------
# 8. acceptance — 380 fixtures at S = 1,000 (plan v2 T4)
# ---------------------------------------------------------------------------

def test_build_380_fixture_cdfs_at_s1000_under_3s():
    book = particles.ParticleBook.from_posterior(_cold_start_posterior(n_draws=1000))
    assert book.mu.shape == (1000,)
    fixtures = [(TEAMS[i], TEAMS[j]) for i in range(20) for j in range(20) if i != j]
    assert len(fixtures) == 380

    t0 = time.perf_counter()
    cdfs = [particles.fixture_cdfs(book, h, a) for h, a in fixtures]
    seconds = time.perf_counter() - t0
    assert len(cdfs) == 380
    assert all(c.cdf.shape == (1000, 121) for c in cdfs)
    assert seconds < 3.0, f"380 FixtureCDFs took {seconds:.2f}s"
    print(f"\n380 FixtureCDFs at S=1000: {seconds:.2f}s")
