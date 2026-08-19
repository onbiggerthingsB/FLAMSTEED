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

import dataclasses
import time

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from scipy.stats import chi2

from epl import anchor as anchor_mod, dcfit, freeze, particles
from wcmodel.model import draw_api
from wcmodel.model.draw_api import PRODUCTION_MAX_GOALS, FixtureCtx
from wcmodel.model.posterior import Posterior
from wcmodel.sim.scoreline import RateBook, sample_score

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

    G, excluded, _ = particles.fixture_grids(lh, la, book.rho, book.max_goals)
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
    flat, _, _ = particles.fixture_grids(lh, la, np.zeros_like(book.rho),
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
    G, _, _ = particles.fixture_grids(*book.rates(h, a), book.rho, book.max_goals)
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
    G2, _, _ = particles.fixture_grids(*book.rates(h2, a2), book.rho, book.max_goals)
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
    G, _, _ = particles.fixture_grids(*book.rates(TEAMS[0], TEAMS[1]),
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
    _, excluded, _ = particles.fixture_grids(lh, la, warm.rho, warm.max_goals)
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
    _, excluded, _ = particles.fixture_grids(lh, la, hot.rho, hot.max_goals)
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


# ---------------------------------------------------------------------------
# 8. D13 — the grid is the LAW the scalar sampler draws from
# ---------------------------------------------------------------------------
#
# `fixture_grids` exists because `wcmodel.sim.scoreline.sample_score` costs
# 41-52 us a call and a season is 380 fixtures x 20,000 simulated seasons (plan
# v2 D13). The parity tests above pin the ARITHMETIC to 1e-12 against
# `draw_api`'s per-draw loop. This one pins the DISTRIBUTION against the scalar
# sampler the vectorised form replaced: 200,000 draws, the same rates, the same
# 10-goal truncation, and a chi-squared test that the draws could have come from
# our grid. An arithmetic parity test cannot catch a sampler that indexes the
# flat grid transposed; a distributional one can.

def _chi_squared_p(observed, pmf, *, min_expected: float = 5.0) -> float:
    """Pearson goodness of fit, cells with expected < 5 pooled into one tail.

    Pooling is not a convenience: a chi-squared over 121 cells of which 80 have
    an expected count below 1 is not chi-squared distributed, and a test whose
    null distribution is wrong is a test that reports whatever it likes.
    """
    observed = np.asarray(observed, dtype=float)
    expected = np.asarray(pmf, dtype=float) * observed.sum()
    keep = expected >= min_expected
    obs = list(observed[keep])
    exp = list(expected[keep])
    tail = float(expected[~keep].sum())
    if tail > 0.0:
        obs.append(float(observed[~keep].sum()))
        exp.append(tail)
    obs, exp = np.array(obs), np.array(exp)
    stat = float((((obs - exp) ** 2) / exp).sum())
    return float(chi2.sf(stat, df=obs.size - 1))


def test_grid_is_the_law_the_scalar_sampler_draws_from_chi_squared():
    lam_home, lam_away, rho = 1.62, 1.14, -0.03
    grid, _, _ = particles.fixture_grids([lam_home], [lam_away], [rho],
                                      PRODUCTION_MAX_GOALS)
    pmf = grid[0].ravel()
    side = PRODUCTION_MAX_GOALS + 1

    rng = np.random.default_rng(20260819)
    n_draws = 200_000
    flat = np.empty(n_draws, np.int64)
    for i in range(n_draws):
        x, y = sample_score(lam_home, lam_away, rng=rng, likelihood="dixon_coles",
                            rho=rho, max_goals=PRODUCTION_MAX_GOALS)
        flat[i] = x * side + y
    observed = np.bincount(flat, minlength=side * side).astype(float)
    assert observed.sum() == n_draws

    p_value = _chi_squared_p(observed, pmf)
    assert p_value > 1e-3, (
        f"the vectorised grid and `sample_score` disagree at the same rates "
        f"(chi-squared p = {p_value:.3g})")

    # POSITIVE CONTROL — the same draws against a grid built at a deliberately
    # wrong rate MUST fail. Without this the test above passes for a grid that
    # is merely a valid distribution over 121 cells.
    wrong, _, _ = particles.fixture_grids([lam_home * 1.15], [lam_away], [rho],
                                       PRODUCTION_MAX_GOALS)
    p_wrong = _chi_squared_p(observed, wrong[0].ravel())
    assert p_wrong < 1e-3, (
        f"a 15% rate error must be detectable at N={n_draws} "
        f"(chi-squared p = {p_wrong:.3g}); the test is not measuring anything")

    # ...and so must a grid with the two sides swapped, which is the indexing
    # bug an arithmetic parity test cannot see.
    swapped, _, _ = particles.fixture_grids([lam_away], [lam_home], [rho],
                                         PRODUCTION_MAX_GOALS)
    assert _chi_squared_p(observed, swapped[0].ravel()) < 1e-3


# ---------------------------------------------------------------------------
# round 2 — the truncation record, the truncation itself, and the bundle
# ---------------------------------------------------------------------------

def test_excluded_mass_is_the_unclipped_poisson_tail_not_the_post_clip_sum():
    """The gated number is measured BEFORE the tau clip, and that matters.

    The Dixon-Coles tau is a quasi-likelihood correction and can drive a cell
    negative — `tau(0,0) = 1 - lh*la*rho` goes negative as soon as
    `lh*la*rho > 1`. Clipping puts that mass back, which RAISES the grid sum and
    so LOWERS `1 - sum`: v1 measured there, and the clip could therefore mask
    part of the truncation tail it was supposed to report. Here the clip is
    larger than the tail itself and the v1 quantity comes out NEGATIVE.

    The unclipped tail is asserted against the closed form
    `1 - P(H<=max)*P(A<=max)` AND against the pre-clip grid sum, which are equal
    because the four tau perturbations cancel identically in aggregate.
    """
    from scipy.stats import poisson

    lh, la, rho = 3.0, 3.0, 0.2                      # lh*la*rho = 1.8 > 1
    _grids, excluded, after_clip = particles.fixture_grids(
        [lh], [la], [rho], PRODUCTION_MAX_GOALS)

    xs = np.arange(PRODUCTION_MAX_GOALS + 1)
    tail = 1.0 - poisson.pmf(xs, lh).sum() * poisson.pmf(xs, la).sum()
    assert excluded[0] == pytest.approx(tail, rel=1e-12)

    # the clip fired, hard: the v1 quantity is not merely smaller, it is negative
    assert after_clip[0] < 0.0 < excluded[0]
    assert excluded[0] - after_clip[0] == pytest.approx(
        (rho * lh * la - 1.0) * np.exp(-lh - la), rel=1e-9), (
        "the gap is exactly the mass the clip put back into the (0,0) cell")

    # and the tau perturbations cancel: the pre-clip grid sum's complement IS
    # the Poisson product tail, which is why the closed form is usable at all.
    from wcmodel.model.likelihoods import dc_tau_np
    g = np.outer(poisson.pmf(xs, lh), poisson.pmf(xs, la))
    for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
        g[x, y] *= float(dc_tau_np(x, y, np.array([lh]), np.array([la]),
                                   np.array([rho]))[0])
    assert 1.0 - g.sum() == pytest.approx(tail, abs=1e-14)

    # POSITIVE CONTROL: with no clip to fire the two measurements agree, so the
    # gap above is the clip and not a second definition of the tail.
    _g2, exc2, post2 = particles.fixture_grids([1.4], [1.1], [0.0],
                                               PRODUCTION_MAX_GOALS)
    assert exc2[0] == pytest.approx(post2[0], abs=1e-15)
    assert exc2[0] > 0.0


def test_excluded_mass_stats_records_both_measurements():
    excluded = np.array([0.01, 0.02, 0.03, 0.30])
    after = excluded - 0.005
    stats = particles.excluded_mass_stats(excluded, after)
    assert stats["mean"] == pytest.approx(0.09)
    assert stats["mean_after_clip"] == pytest.approx(0.085)
    assert stats["worst"] == pytest.approx(0.30)
    assert stats["worst_after_clip"] == pytest.approx(0.295)
    assert "mean_after_clip" not in particles.excluded_mass_stats(excluded)

    # THE FLAG READS THE UNCLIPPED MEAN, DISCRIMINATINGLY. Above, 0.09 and
    # 0.085 both clear the 5e-3 threshold, so the assertion `flagged is True`
    # held whichever of the two the flag read — it could not tell them apart.
    # Here the threshold sits BETWEEN them, so computing `flagged` from
    # `after_clip` flips this assertion.
    split = np.array([0.012, 0.0])
    split_after = np.array([0.012, -0.010])
    straddle = particles.excluded_mass_stats(split, split_after)
    assert straddle["mean_after_clip"] < particles.FLAG_EXCLUDED_MASS \
        < straddle["mean"], "the two measurements must straddle the threshold"
    assert straddle["flagged"] is True
    # POSITIVE CONTROL: with both measurements under the threshold it is False,
    # so `flagged` is reading a number and not pinned True.
    assert particles.excluded_mass_stats(
        np.array([0.001, 0.0]), np.array([0.001, -0.010]))["flagged"] is False
    assert particles.excluded_mass_stats(excluded)["flagged"] is True


def test_fixture_cdfs_gates_on_the_unclipped_tail_not_the_post_clip_sum():
    """D11's hard stop reads `excluded`, and the two really can disagree.

    Clipping the negative Dixon-Coles cells can only RAISE a grid's sum, so
    `1 - sum` after the clip can only be SMALLER: measuring there lets the clip
    mask part of a truncation problem. Every end-to-end threshold test so far
    used fixtures where the clip did not fire at all, so swapping `excluded` for
    `excluded_after_clip` in the gate left them all green — the central
    invariant of the amendment had no test that could see it.

    This book is built so the ceiling sits BETWEEN the two measurements. One
    particle carries a real 8.3% truncation tail with no clip; the other has
    `lh*la*rho = 3.8 > 1`, so `tau(0,0)` is negative and the clip puts back more
    mass than that particle's whole tail. Mean unclipped 0.0417 is over the 2e-2
    ceiling; mean post-clip 0.0161 is under it.
    """
    lh_over_la = np.log(np.array([6.0, 2.0]))          # exp(mu) IS the rate here
    book = particles.ParticleBook(
        teams=("h", "a"), idx={"h": 0, "a": 1},
        att=np.zeros((2, 2)), defe=np.zeros((2, 2)),
        mu=lh_over_la, home_adv=np.zeros(2), rho=np.array([0.0, 0.95]),
        sigma_att=np.full(2, 0.4), sigma_def=np.full(2, 0.4),
        provisional=frozenset(), cold_start=frozenset(),
        likelihood="dixon_coles", alpha=0.1,
        max_goals=PRODUCTION_MAX_GOALS, cfg_hash="test")

    lh, la = book.rates("h", "a")
    _grids, excluded, after_clip = particles.fixture_grids(
        lh, la, book.rho, book.max_goals)
    assert after_clip.mean() < particles.HARD_STOP_EXCLUDED_MASS < excluded.mean(), (
        "the fixture must straddle the ceiling, or this test proves nothing")

    with pytest.raises(particles.ExcludedMassTooLarge):
        particles.fixture_cdfs(book, "h", "a")

    # POSITIVE CONTROL: drop the hot particle's rate and BOTH measurements fall
    # under the ceiling — the same clip, the same rho, no refusal. So the
    # refusal above is the tail crossing the line, not the clip firing.
    cool = dataclasses.replace(book, mu=np.log(np.array([2.5, 2.0])))
    _g, exc2, post2 = particles.fixture_grids(*cool.rates("h", "a"), cool.rho,
                                              cool.max_goals)
    assert post2.mean() < exc2.mean() < particles.HARD_STOP_EXCLUDED_MASS
    assert particles.fixture_cdfs(cool, "h", "a").excluded_mean == pytest.approx(
        float(exc2.mean()))


def test_max_goals_override_needs_allow_nonproduction():
    """The truncation is the published law's, not a keyword default.

    A book at 11 or 12 goals samples a different per-fixture law from the one
    the forecast issues and its D11 excluded-mass record gates a different
    quantity. The sensitivity sweep is entitled to build one; it has to say so.
    """
    post = _cold_start_posterior()
    for other in (11, 12, 9):
        with pytest.raises(particles.UnsupportedPosterior, match="max_goals"):
            particles.ParticleBook.from_posterior(post, max_goals=other)

    # explicit, deliberate, and it really does build a different grid
    diag = particles.ParticleBook.from_posterior(post, max_goals=12,
                                                 allow_nonproduction=True)
    assert diag.max_goals == 12
    assert diag.n_scorelines == 169

    # POSITIVE CONTROL: the production value needs no flag, and passing the flag
    # does not change what the default builds.
    plain = particles.ParticleBook.from_posterior(post)
    flagged = particles.ParticleBook.from_posterior(
        post, max_goals=PRODUCTION_MAX_GOALS, allow_nonproduction=True)
    assert plain.max_goals == PRODUCTION_MAX_GOALS == flagged.max_goals
    assert plain.content_hash() == flagged.content_hash() != diag.content_hash()


def test_load_refuses_a_corrupted_bundle(tmp_path):
    """A bundle that cannot answer for its own contents is refused, every way.

    The recorded `content_hash` covers the metadata and every array byte. It was
    optional — `if recorded is not None` — so a bundle whose json had lost it
    loaded silently, and a forecast issued from it would quote an
    `effective_posterior_hash` that nothing on disk backs.
    """
    import json as _json

    book = particles.ParticleBook.from_posterior(_cold_start_posterior())
    path = tmp_path / "particles.npz"
    book.save(path)
    meta_path = path.with_suffix(".json")
    good_npz = path.read_bytes()
    good_meta = meta_path.read_text()

    # POSITIVE CONTROL: untouched, it loads and hashes to the same thing.
    assert particles.ParticleBook.load(path).content_hash() == book.content_hash()

    # (a) one flipped byte deep inside the arrays
    flipped = bytearray(good_npz)
    i = len(flipped) - 64
    flipped[i] ^= 0x01
    path.write_bytes(bytes(flipped))
    with pytest.raises(particles.ParticleError):
        particles.ParticleBook.load(path)

    # (b) a truncated (half-written) npz
    path.write_bytes(good_npz[: len(good_npz) // 2])
    with pytest.raises(particles.ParticleError):
        particles.ParticleBook.load(path)

    # (c) the recorded hash removed — refused, not trusted
    path.write_bytes(good_npz)
    meta = _json.loads(good_meta)
    meta.pop("content_hash")
    meta_path.write_text(_json.dumps(meta))
    with pytest.raises(particles.ParticleError, match="content_hash"):
        particles.ParticleBook.load(path)

    # (d) metadata edited to disagree with the arrays it describes
    meta = _json.loads(good_meta)
    meta["alpha"] = float(meta["alpha"]) + 0.25
    meta_path.write_text(_json.dumps(meta))
    with pytest.raises(particles.ParticleError, match="content hash"):
        particles.ParticleBook.load(path)

    # ... and restoring the json restores the load, so (c)/(d) are the json.
    meta_path.write_text(good_meta)
    assert particles.ParticleBook.load(path).content_hash() == book.content_hash()

    # (e) VALID JSON THAT IS NOT A SIDECAR. `[1, 2]` and `"x"` parse, and then
    #     `meta.get` raised `AttributeError` — outside the `ParticleError`
    #     contract this method advertises, so a caller catching "this bundle is
    #     unusable" did not catch it.
    for not_an_object in ("[1, 2]", '"particles"', "null", "3"):
        meta_path.write_text(not_an_object)
        with pytest.raises(particles.ParticleError):
            particles.ParticleBook.load(path)

    # (f) A STRUCTURALLY MALFORMED ARRAY. It survives construction and fails
    #     when `content_hash` walks it, which was OUTSIDE the try block.
    meta_path.write_text(good_meta)
    with np.load(path) as npz:
        arrays = {k: npz[k] for k in npz.files}
    arrays["rho"] = np.array(["not", "a", "number"])
    np.savez(path, **arrays)
    with pytest.raises(particles.ParticleError):
        particles.ParticleBook.load(path)


def test_load_enforces_the_production_gate_the_save_side_enforces(tmp_path):
    """The 10-goal gate survives being written to disk and read back.

    `from_posterior` refuses any other `max_goals` without an explicit
    `allow_nonproduction`, and that gate used to stop at the file: a 12-goal
    diagnostic book — exactly what the D19 sensitivity sweep builds — round-
    tripped through `save`/`load` and came back as an ordinary production book.
    It samples a different per-fixture law from the one the forecast publishes
    and its D11 excluded-mass record gates a different quantity, with nothing on
    the way in to say so.
    """
    post = _cold_start_posterior()
    diag = particles.ParticleBook.from_posterior(post, max_goals=12,
                                                 allow_nonproduction=True)
    path = tmp_path / "diag.npz"
    diag.save(path)

    with pytest.raises(particles.UnsupportedPosterior, match="max_goals"):
        particles.ParticleBook.load(path)

    back = particles.ParticleBook.load(path, allow_nonproduction=True)
    assert back.max_goals == 12
    assert back.content_hash() == diag.content_hash()

    # POSITIVE CONTROL, both directions: a production book needs no flag, and
    # passing the flag does not change what comes back.
    plain_path = tmp_path / "plain.npz"
    plain = particles.ParticleBook.from_posterior(post)
    plain.save(plain_path)
    assert particles.ParticleBook.load(plain_path).content_hash() \
        == particles.ParticleBook.load(
            plain_path, allow_nonproduction=True).content_hash() \
        == plain.content_hash() != diag.content_hash()
