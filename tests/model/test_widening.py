"""Tests for provisional-widening: (a) likelihood down-weight + (c) predictive
inflation, both selected by ``config["model"]["widening"]`` (mechanism/strength).

(c) is MEAN-PRESERVING. It takes the 2D scoreline pmf grid for a fixture and
widens it by mixing toward an independent product of overdispersed
negative-binomial marginals whose means EXACTLY match the grid's marginal means.
Because the reference marginals share the grid's expected home/away goals, the
convex mix leaves both marginal means unchanged (to finite-grid truncation
tolerance) while raising variance/entropy. The headline property test
(``test_inflate_preserves_marginal_means``) pins this — it is exactly what the
old uniform-over-bins mixture VIOLATED (uniform pulls the predicted scoreline
toward the grid centre, biasing the betting edge by an arbitrary ``max_goals``).
"""
import numpy as np
import pytest

from wcmodel.model.panel import build_design
from wcmodel.model.widening import inflate_predictive, likelihood_weight


# ---------- shared fixtures ----------


def _design_with_provisional():
    """3-team / 3-match DesignData; match 0 has a provisional home team, match 1
    a provisional away team, match 2 no provisional team. Weights distinct so
    scaling is visible per row."""
    import pandas as pd

    mp = pd.DataFrame(
        {
            "match_id": ["m0", "m1", "m2"],
            "date": pd.Timestamp("2020-01-01"),
            "home_team": ["A", "B", "C"],
            "away_team": ["B", "C", "A"],
            "home_goals": [1, 2, 0],
            "away_goals": [0, 1, 0],
            "neutral": False,
            "match_type": "friendly",
            "weight": [1.0, 2.0, 4.0],
            "home_provisional": [True, False, False],
            "away_provisional": [False, True, False],
        }
    )
    return build_design(mp)


def _poisson_grid(mh: float, ma: float, n: int = 11) -> np.ndarray:
    """Independent Poisson(mh) (x) Poisson(ma) joint scoreline pmf on a 0..n-1
    grid, renormalized on the finite support. Concentrated, non-symmetric when
    mh != ma — a realistic predictive scoreline grid."""
    from scipy.stats import poisson

    support = np.arange(n)
    ph = poisson.pmf(support, mh)
    pa = poisson.pmf(support, ma)
    grid = np.outer(ph, pa)
    return grid / grid.sum()


def _marginal_means(grid: np.ndarray) -> tuple[float, float]:
    h = np.arange(grid.shape[0])
    a = np.arange(grid.shape[1])
    return float((grid.sum(axis=1) * h).sum()), float((grid.sum(axis=0) * a).sum())


def _marginal_vars(grid: np.ndarray) -> tuple[float, float]:
    h = np.arange(grid.shape[0])
    a = np.arange(grid.shape[1])
    mh, ma = _marginal_means(grid)
    vh = float((grid.sum(axis=1) * (h - mh) ** 2).sum())
    va = float((grid.sum(axis=0) * (a - ma) ** 2).sum())
    return vh, va


# ---------- mechanism (a): likelihood down-weight ----------


def test_likelihood_weight_a_scales_provisional_matches():
    """(a): a match involving ANY provisional team has its weight * strength;
    matches with no provisional team are untouched."""
    d = _design_with_provisional()
    w = likelihood_weight(d, mechanism="a", strength=0.5)
    # m0 (prov home) and m1 (prov away) scaled; m2 (no prov) unchanged.
    assert w[0] == pytest.approx(1.0 * 0.5)
    assert w[1] == pytest.approx(2.0 * 0.5)
    assert w[2] == pytest.approx(4.0)


def test_likelihood_weight_a_does_not_mutate_input():
    """(a) returns a NEW array; d.weight is not mutated in place."""
    d = _design_with_provisional()
    before = d.weight.copy()
    w = likelihood_weight(d, mechanism="a", strength=0.5)
    assert np.array_equal(d.weight, before)  # input preserved
    assert w is not d.weight


def test_likelihood_weight_a_rejects_out_of_range_strength():
    """(a) strength is a multiplier and MUST lie in [0, 1]. A value <0 would flip
    sign and >1 would UP-weight provisional matches (the opposite of widening) —
    both are config errors -> ValueError (Codex finding 5)."""
    d = _design_with_provisional()
    with pytest.raises(ValueError):
        likelihood_weight(d, mechanism="a", strength=-0.1)
    with pytest.raises(ValueError):
        likelihood_weight(d, mechanism="a", strength=1.5)
    # Boundaries are allowed (0 = drop, 1 = no-op).
    likelihood_weight(d, mechanism="a", strength=0.0)
    likelihood_weight(d, mechanism="a", strength=1.0)


def test_likelihood_weight_c_is_identity():
    """(c) leaves weights untouched — it acts at PREDICT time, not in the
    likelihood. So likelihood_weight under 'c' == d.weight exactly."""
    d = _design_with_provisional()
    w = likelihood_weight(d, mechanism="c", strength=0.5)
    assert np.array_equal(w, d.weight)


def test_likelihood_weight_unknown_mechanism_raises():
    """An unknown mechanism is a config error -> ValueError naming the bad key."""
    d = _design_with_provisional()
    with pytest.raises(ValueError) as exc:
        likelihood_weight(d, mechanism="b", strength=0.5)
    assert "b" in str(exc.value)


# ---------- mechanism (c): mean-preserving predictive widening ----------


def test_inflate_preserves_marginal_means():
    """THE HEADLINE PROPERTY (what uniform-mixture VIOLATED): widening a
    provisional team's predictive scoreline grid leaves BOTH marginal means
    (E[home goals], E[away goals]) unchanged. The predicted scoreline — which
    drives the betting edge — must not move."""
    grid = _poisson_grid(1.6, 0.9, n=11)  # non-symmetric, concentrated
    mh0, ma0 = _marginal_means(grid)
    wide = inflate_predictive(grid, is_provisional=True, strength=0.5)
    mh1, ma1 = _marginal_means(wide)
    assert mh1 == pytest.approx(mh0, abs=1e-2)
    assert ma1 == pytest.approx(ma0, abs=1e-2)


def test_inflate_increases_variance():
    """Wider = less confident: the marginal variance of home (and away) goals
    strictly increases after widening, at the SAME mean."""
    grid = _poisson_grid(1.6, 0.9, n=11)
    vh0, va0 = _marginal_vars(grid)
    wide = inflate_predictive(grid, is_provisional=True, strength=0.5)
    vh1, va1 = _marginal_vars(wide)
    assert vh1 > vh0
    assert va1 > va0


def test_inflate_normalized():
    """The widened grid is still a valid joint pmf (sums to 1)."""
    grid = _poisson_grid(1.6, 0.9, n=11)
    wide = inflate_predictive(grid, is_provisional=True, strength=0.5)
    assert wide.sum() == pytest.approx(1.0)


def test_inflate_noop_when_not_provisional():
    """No-op control: a non-provisional team's predictive grid is returned
    unchanged."""
    grid = _poisson_grid(1.6, 0.9, n=11)
    out = inflate_predictive(grid, is_provisional=False, strength=0.5)
    assert np.array_equal(out, grid)


def test_inflate_noop_when_strength_nonpositive():
    """strength <= 0 is also a no-op (no widening requested)."""
    grid = _poisson_grid(1.6, 0.9, n=11)
    assert np.array_equal(
        inflate_predictive(grid, is_provisional=True, strength=0.0), grid
    )
    assert np.array_equal(
        inflate_predictive(grid, is_provisional=True, strength=-0.3), grid
    )


def test_inflate_strength_scales_widening():
    """Larger strength => larger variance increase (more weight on the
    overdispersed reference), while the mean stays put either way."""
    grid = _poisson_grid(1.6, 0.9, n=11)
    vh0, va0 = _marginal_vars(grid)
    small = inflate_predictive(grid, is_provisional=True, strength=0.2)
    large = inflate_predictive(grid, is_provisional=True, strength=0.8)
    vh_small, va_small = _marginal_vars(small)
    vh_large, va_large = _marginal_vars(large)
    assert vh_large > vh_small > vh0
    assert va_large > va_small > va0


# ---------- both mechanisms reachable via the config switch ----------


def test_config_widening_keys_present_and_drive_both_mechanisms():
    """The two functions are config-driven by mechanism/strength: feeding the
    live config['model']['widening'] block into each entry point routes to the
    right behaviour ('a' scales, 'c' is likelihood-identity)."""
    from wcmodel.config import load_config

    wd = load_config()["model"]["widening"]
    assert set(wd) >= {"mechanism", "strength"}
    d = _design_with_provisional()
    # Drive (a) from a config-shaped dict.
    wa = likelihood_weight(d, mechanism="a", strength=wd["strength"])
    assert wa[0] == pytest.approx(d.weight[0] * wd["strength"])
    # Drive (c) from a config-shaped dict (likelihood side is identity).
    wc = likelihood_weight(d, mechanism="c", strength=wd["strength"])
    assert np.array_equal(wc, d.weight)
