"""Tests for provisional-widening: (a) likelihood down-weight + (c) predictive
inflation, both selected by ``config["model"]["widening"]`` (mechanism/strength).

NOTE ON THE (c) METRIC — deliberate divergence from the plan's draft test.
The Phase-2 plan's draft asserted that ``pmf_draws.var(axis=0).sum()`` (variance
ACROSS DRAWS, per bin) INCREASES under (c). That assertion is WRONG and we do
NOT reproduce it. (c) here is a uniform-mixture ``wide = (1-a)*draws + a*uniform``;
since ``a*uniform`` is the SAME constant added to every draw, the across-draw
variance scales by exactly ``(1-a)**2`` and therefore strictly DECREASES — you
cannot raise a sample's variance by adding a constant to every sample. That
quantity is *parameter* uncertainty (spread of the pmf across posterior draws),
not the *predictive* spread we want to inflate. The INTENT of (c) is "less sure
what the score will be" = a WIDER / HIGHER-ENTROPY predictive distribution OVER
THE SCORELINE OUTCOMES. So we test that correct property directly:
``test_inflate_increases_entropy`` (Shannon entropy per row strictly up), plus
normalization, a no-op control, and an explicit characterization of the known
mean-shift limitation (``test_inflate_shifts_mean_toward_grid_centre``).
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


def _entropy(pmf, axis=-1):
    """Shannon entropy (nats) of a (normalized) pmf along ``axis``; 0*log0:=0."""
    pmf = np.asarray(pmf, dtype=float)
    return -np.sum(np.where(pmf > 0, pmf * np.log(pmf), 0.0), axis=axis)


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


# ---------- mechanism (c): predictive-variance / entropy inflation ----------


def _base_draws():
    """(n_draws=4, n_bins=6) of non-uniform, normalized pmf rows (seeded)."""
    rng = np.random.default_rng(0)
    raw = rng.gamma(shape=2.0, size=(4, 6))
    return raw / raw.sum(axis=1, keepdims=True)


def test_inflate_increases_entropy():
    """THE CORRECT (c) PROPERTY: widening a provisional team's predictive makes
    it HIGHER-ENTROPY (wider over scoreline outcomes) row-by-row. Mixing a
    non-uniform pmf toward uniform strictly increases Shannon entropy."""
    base = _base_draws()
    wide = inflate_predictive(base, is_provisional=True, strength=0.5)
    h_base = _entropy(base)
    h_wide = _entropy(wide)
    assert np.all(h_wide > h_base)  # strictly higher entropy every row


def test_inflate_does_not_raise_across_draw_variance():
    """GUARD AGAINST THE PLAN'S WRONG METRIC. The plan asserted across-draw
    variance INCREASES; it does not. Mixing toward a constant scales across-draw
    variance by (1-a)**2, so it strictly DECREASES. We pin that here so nobody
    'fixes' (c) to satisfy the wrong assertion — entropy is the right target."""
    base = _base_draws()
    alpha = 0.5
    wide = inflate_predictive(base, is_provisional=True, strength=alpha)
    v_base = base.var(axis=0).sum()
    v_wide = wide.var(axis=0).sum()
    assert v_wide < v_base  # the plan's metric goes the WRONG way
    assert v_wide == pytest.approx((1 - alpha) ** 2 * v_base)


def test_inflate_rows_still_sum_to_one():
    """Normalization invariant: widened rows are still valid pmfs (sum to 1)."""
    base = _base_draws()
    wide = inflate_predictive(base, is_provisional=True, strength=0.5)
    assert np.allclose(wide.sum(axis=1), 1.0)


def test_inflate_noop_when_not_provisional():
    """No-op control: a non-provisional team's predictive is returned unchanged."""
    base = _base_draws()
    out = inflate_predictive(base, is_provisional=False, strength=0.5)
    assert np.array_equal(out, base)


def test_inflate_noop_when_strength_nonpositive():
    """strength <= 0 is also a no-op (no widening requested)."""
    base = _base_draws()
    assert np.array_equal(
        inflate_predictive(base, is_provisional=True, strength=0.0), base
    )
    assert np.array_equal(
        inflate_predictive(base, is_provisional=True, strength=-0.3), base
    )


def test_inflate_shifts_mean_toward_grid_centre():
    """CHARACTERIZES THE DOCUMENTED (c) LIMITATION: uniform-mixture is NOT
    mean-preserving. For a left-skewed pmf (mass on low bins), the expected bin
    index E[bin] is pulled UP toward the grid centre (n_bins-1)/2 by widening.
    This shifts the predicted scoreline — a known weakness for a betting model
    whose edge is driven by the predictive mean (Phase-4-tunable choice)."""
    # One sharply left-skewed pmf row: nearly all mass on bin 0.
    n_bins = 6
    base = np.array([[0.90, 0.06, 0.02, 0.01, 0.005, 0.005]])
    assert base.sum() == pytest.approx(1.0)
    bins = np.arange(n_bins)
    centre = (n_bins - 1) / 2.0  # 2.5

    wide = inflate_predictive(base, is_provisional=True, strength=0.5)
    mean_base = float((base[0] * bins).sum())
    mean_wide = float((wide[0] * bins).sum())

    # The mean is NOT preserved: it moves, and specifically toward the centre.
    assert mean_wide != pytest.approx(mean_base)
    assert mean_base < mean_wide <= centre


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
