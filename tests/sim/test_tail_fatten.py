"""Phase-4b sim-only tail-fatten override tests.

The override is a SIM-ONLY, predict/sample-time grid reshape (the `host_factor`
class of change) — NO model/config field, NO posterior, NO refit. Three contracts:

  1. ``fatten_grid`` is the audited mean-preserving construction (mechanism-c
     ``inflate_predictive`` forced provisional): mean preserved to 1e-9, tails
     monotone in alpha, alpha==0 == identity.
  2. ``bucket_alpha`` maps a signed Elo gap to its |gap| bucket's alpha — monotone
     in |gap|, sign-symmetric, respects the cap.
  3. OFF-STATE BYTE-IDENTICAL (house pattern): a tiny-bracket sim with
     ``tail_fatten=None`` (and with an all-zero alpha callable) is BIT-identical to
     the pre-change sim path at the same seed; a positive alpha DOES change the
     sampled outcomes (the override is non-vacuous).

The off-state test reuses the ``_toy_posterior`` + ``tiny_bracket()`` precedent
from ``tests/sim/test_host_sensitivity.py`` so it runs in milliseconds.
"""
from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from wcmodel.backtest import tails as tailmod
from wcmodel.model.posterior import Posterior
from wcmodel.sim.scoreline import bucket_alpha, fatten_grid
from wcmodel.sim.tournament import simulate_tournament

from tests.sim.conftest import _TINY_TEAMS, tiny_bracket


# --------------------------------------------------------------------------- #
# 1. fatten_grid — mean-preserving, tails monotone, alpha==0 identity.
# --------------------------------------------------------------------------- #
def _peaked_grid(n=8, lh=1.3, la=1.1):
    """A peaked independent-Poisson grid (the shape the sim samples)."""
    from scipy.stats import poisson
    xs = np.arange(n)
    g = poisson.pmf(xs, lh)[:, None] * poisson.pmf(xs, la)[None, :]
    return g / g.sum()


def test_fatten_grid_alpha_zero_is_identity():
    g = _peaked_grid()
    out = fatten_grid(g, 0.0)
    assert np.allclose(out, g, atol=0, rtol=0)


def test_fatten_grid_mean_preserving():
    g = _peaked_grid()
    h = np.arange(g.shape[0])
    a = np.arange(g.shape[1])
    mh0 = (g.sum(axis=1) * h).sum()
    ma0 = (g.sum(axis=0) * a).sum()
    for alpha in (0.2, 0.5):
        out = fatten_grid(g, alpha)
        mh = (out.sum(axis=1) * h).sum()
        ma = (out.sum(axis=0) * a).sum()
        assert mh == pytest.approx(mh0, abs=1e-9)
        assert ma == pytest.approx(ma0, abs=1e-9)
        assert out.sum() == pytest.approx(1.0, abs=1e-12)


def test_fatten_grid_tails_monotone_in_alpha():
    g = _peaked_grid()
    prev_total = tailmod.total_ge(g, k=5)
    prev_gd = tailmod.abs_gd_ge(g, k=3)
    for alpha in (0.1, 0.3, 0.6):
        out = fatten_grid(g, alpha)
        t = tailmod.total_ge(out, k=5)
        d = tailmod.abs_gd_ge(out, k=3)
        assert t >= prev_total - 1e-12
        assert d >= prev_gd - 1e-12
        prev_total, prev_gd = t, d
    # Strictly fatter at the largest alpha than the unperturbed grid.
    assert tailmod.total_ge(fatten_grid(g, 0.6), k=5) > tailmod.total_ge(g, k=5)


def test_fatten_grid_out_of_range_raises():
    g = _peaked_grid()
    with pytest.raises(ValueError):
        fatten_grid(g, -0.1)
    with pytest.raises(ValueError):
        fatten_grid(g, 1.5)


# --------------------------------------------------------------------------- #
# 2. bucket_alpha — gap -> |gap| bucket alpha.
# --------------------------------------------------------------------------- #
def test_bucket_alpha_monotone_and_sign_symmetric():
    # edges (interior quartile cuts) and a monotone alpha-per-bucket vector.
    edges = [100.0, 250.0, 450.0]          # 4 buckets: [0,100),[100,250),[250,450),[450,inf)
    alpha_by_bucket = [0.0, 0.1, 0.3, 0.5]
    # Monotone non-decreasing in |gap|.
    a0 = bucket_alpha(50.0, alpha_by_bucket, edges)
    a1 = bucket_alpha(150.0, alpha_by_bucket, edges)
    a2 = bucket_alpha(300.0, alpha_by_bucket, edges)
    a3 = bucket_alpha(900.0, alpha_by_bucket, edges)
    assert (a0, a1, a2, a3) == (0.0, 0.1, 0.3, 0.5)
    # Sign-symmetric: |gap| is what matters.
    assert bucket_alpha(-300.0, alpha_by_bucket, edges) == bucket_alpha(300.0, alpha_by_bucket, edges)


# --------------------------------------------------------------------------- #
# 3. Off-state byte-identical (house pattern) + non-vacuity.
# --------------------------------------------------------------------------- #
_TEAMS = list(_TINY_TEAMS)


def _toy_posterior(*, mu=0.1, home_adv=0.5, rho=-0.05, teams=_TEAMS):
    """Minimal REAL Posterior with FIXED att/def (mirrors test_host_sensitivity)."""
    n = len(teams)
    ds = xr.Dataset(
        {
            "att": (("chain", "draw", "team"), np.zeros((1, 1, n))),
            "def": (("chain", "draw", "team"), np.zeros((1, 1, n))),
            "mu": (("chain", "draw"), np.full((1, 1), mu)),
            "home_adv": (("chain", "draw"), np.full((1, 1), home_adv)),
            "rho": (("chain", "draw"), np.full((1, 1), rho)),
        },
        coords={"team": list(teams)},
    )
    idata = xr.DataTree.from_dict({"posterior": ds})
    return Posterior(idata, list(teams), "dixon_coles", provisional_teams=set())


def _run(tail_fatten):
    post = _toy_posterior()
    return simulate_tournament(
        post, bracket=tiny_bracket(), n_sims=2000, seed=0,
        max_goals=12, et_scale=0.3333, pen_home_prob=0.5,
        tail_fatten=tail_fatten,
    )


def test_off_state_none_byte_identical():
    """tail_fatten=None must be BIT-identical to the pre-change neutral sim."""
    base = simulate_tournament(
        _toy_posterior(), bracket=tiny_bracket(), n_sims=2000, seed=0,
        max_goals=12, et_scale=0.3333, pen_home_prob=0.5,
    )
    with_none = _run(None)
    assert base.progression.equals(with_none.progression)
    assert base.se.equals(with_none.se)


def test_off_state_zero_alpha_byte_identical():
    """A tail_fatten callable that returns 0.0 everywhere == None (bit-identical)."""
    base = _run(None)
    zero = _run(lambda home, away: 0.0)
    assert base.progression.equals(zero.progression)


def test_positive_alpha_changes_outcomes():
    """A positive alpha reshapes the sampled scorelines -> the progression MOVES
    (the override is non-vacuous). Same seed, only the grid reshape differs."""
    base = _run(None)
    fat = _run(lambda home, away: 0.5)
    # At least one team's advance_from_group probability changes.
    assert not base.progression["advance_from_group"].equals(
        fat.progression["advance_from_group"]
    )
