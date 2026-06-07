"""Tests for provisional-widening: (a) likelihood down-weight + (c) predictive
inflation, both selected by ``config["model"]["widening"]`` (mechanism/strength).

(c) is EXACTLY MEAN-PRESERVING (to machine precision, for ANY grid size). It
takes the 2D scoreline pmf grid for a fixture and widens it by mixing toward an
independent product of MAX-ENTROPY (exponential-tilted) marginals whose means
are SOLVED (1-D root find) to EQUAL the grid's marginal means exactly. Because
each reference marginal has mean exactly equal to the grid's expected home/away
goals, the convex mix ``(1-alpha)*grid + alpha*q`` has marginal means
``(1-alpha)*m + alpha*m = m`` — preserved to machine precision, INDEPENDENT of
the goal-grid bound. (The earlier negative-binomial reference was only
APPROXIMATELY mean-preserving: renormalizing the NB on the finite grid truncates
its tail and shifts its mean, so the mix's mean drifted — by >1e-2 at small
grids / high strength, e.g. mean 2.5 on a max_goals=6 grid at strength 0.99.)
The headline property test (``test_inflate_preserves_marginal_means_exactly``)
pins this to atol 1e-6 across means / strengths / grid sizes — the regime the
NB version FAILED. Widening is in the ENTROPY sense: the max-entropy reference
at a fixed mean is the highest-entropy distribution with that mean on the
bounded support, so mixing toward it strictly INCREASES Shannon entropy (the
"less-confident" invariant) and, for a concentrated predictive, variance too.
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


def _entropy(p: np.ndarray) -> float:
    """Shannon entropy (nats) of a (flattened) pmf; 0*log0 := 0."""
    p = p.ravel()
    nz = p[p > 0]
    return float(-(nz * np.log(nz)).sum())


def _marginal_entropies(grid: np.ndarray) -> tuple[float, float]:
    return _entropy(grid.sum(axis=1)), _entropy(grid.sum(axis=0))


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


# ---------- mechanism (c): EXACTLY mean-preserving predictive widening ----------


@pytest.mark.parametrize("mh,ma", [(1.6, 0.9), (2.5, 1.8)])
@pytest.mark.parametrize("strength", [0.2, 0.5, 0.99])
@pytest.mark.parametrize("max_goals", [6, 10])
def test_inflate_preserves_marginal_means_exactly(mh, ma, strength, max_goals):
    """THE HEADLINE PROPERTY: widening a provisional team's predictive scoreline
    grid leaves BOTH marginal means (E[home goals], E[away goals]) unchanged to
    MACHINE PRECISION (atol 1e-6), independent of grid size. The predicted
    scoreline drives the betting edge, so this must be EXACT — not merely close.

    Pinned across a lower- and higher-mean grid, across strength in
    {0.2, 0.5, 0.99}, and on BOTH a small (max_goals=6) and a larger
    (max_goals=10) grid. This is precisely the regime the negative-binomial
    reference FAILED: at mean 2.5 on the max_goals=6 grid with strength 0.99, NB
    renormalization truncates the tail and shifts the mix mean by far more than
    1e-6 (~0.03–0.07). The max-entropy reference solves its mean to EQUAL the
    grid mean, so the convex mix's mean is exact for any bound."""
    grid = _poisson_grid(mh, ma, n=max_goals + 1)  # support 0..max_goals
    mh0, ma0 = _marginal_means(grid)
    wide = inflate_predictive(grid, is_provisional=True, strength=strength)
    mh1, ma1 = _marginal_means(wide)
    assert mh1 == pytest.approx(mh0, abs=1e-6)
    assert ma1 == pytest.approx(ma0, abs=1e-6)


def test_inflate_increases_entropy():
    """THE GUARANTEED WIDENING INVARIANT: mixing toward the max-entropy reference
    at the grid's mean strictly INCREASES Shannon entropy — per marginal AND
    jointly. (Max-entropy at a fixed mean on bounded support is the highest-
    entropy distribution with that mean, so a convex mix toward it lifts entropy
    for any non-max-entropy input.)"""
    grid = _poisson_grid(1.6, 0.9, n=11)
    hh0, ha0 = _marginal_entropies(grid)
    j0 = _entropy(grid)
    wide = inflate_predictive(grid, is_provisional=True, strength=0.5)
    hh1, ha1 = _marginal_entropies(wide)
    j1 = _entropy(wide)
    assert hh1 > hh0
    assert ha1 > ha0
    assert j1 > j0


def test_inflate_increases_variance_on_concentrated_grid():
    """Wider = less confident: on a CONCENTRATED predictive (independent Poisson
    grid), the marginal variance of home (and away) goals strictly increases
    after widening, at the SAME (exactly preserved) mean. (Variance increase
    holds for concentrated inputs; entropy increase is the always-guaranteed
    invariant — see ``test_inflate_increases_entropy``.)"""
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


def test_inflate_noop_when_strength_zero():
    """strength == 0.0 is a valid in-range no-op (zero widening requested) — it
    must NOT raise, and the grid is returned unchanged."""
    grid = _poisson_grid(1.6, 0.9, n=11)
    assert np.array_equal(
        inflate_predictive(grid, is_provisional=True, strength=0.0), grid
    )


def test_inflate_rejects_out_of_range_strength():
    """FIX B (fail loud): (c) ``strength`` is a Phase-4 tuning DOF and MUST lie
    in [0, 1] — a value <0 or >1 is a config error and raises ``ValueError``
    (mirroring mechanism (a)'s ``likelihood_weight`` validation), NOT a silent
    no-op (negative) / silent clip (>1). The in-range boundaries are valid:
    0.0 = no-op, 1.0 = full widening (the internal ``min(strength, 0.99)``
    numerical cap still applies WITHIN range).
    """
    grid = _poisson_grid(1.6, 0.9, n=11)
    with pytest.raises(ValueError):
        inflate_predictive(grid, is_provisional=True, strength=-0.1)
    with pytest.raises(ValueError):
        inflate_predictive(grid, is_provisional=True, strength=1.5)
    # Boundaries are allowed (0.0 = no-op, 1.0 = full widening within the cap).
    inflate_predictive(grid, is_provisional=True, strength=0.0)
    inflate_predictive(grid, is_provisional=True, strength=1.0)


def test_inflate_out_of_range_strength_raises_even_when_not_provisional():
    """An out-of-range ``strength`` is a CONFIG error — it must fail loud
    regardless of the provisional flag, so a bad Phase-4 strength can never hide
    behind a non-provisional team. (Validate strength BEFORE the provisional
    short-circuit.)"""
    grid = _poisson_grid(1.6, 0.9, n=11)
    with pytest.raises(ValueError):
        inflate_predictive(grid, is_provisional=False, strength=1.5)
    with pytest.raises(ValueError):
        inflate_predictive(grid, is_provisional=False, strength=-0.1)


def test_inflate_rejects_non_finite_grid_loud_and_typed():
    """FAIL-SAFE (defense-in-depth): a NON-FINITE input grid is a BROKEN predictive
    (e.g. an upstream goal-rate overflow that underflowed a per-draw scoreline pmf to
    all-zeros -> 0/0 = NaN) and must FAIL LOUD + TYPED — ``ValueError("non-finite
    predictive grid")`` — NOT silently widen-nothing and return a NaN grid.

    RED before the fix: the NaN-blind edge-guard (``mh <= eps`` etc.) lets a NaN
    marginal mean through (NaN fails every comparison) into ``_max_entropy_pmf`` ->
    ``brentq``, which dies with a cryptic 'function value at x=-700.0 is NaN'. GREEN:
    the explicit finiteness check raises the typed error the ablation gate catches."""
    grid = _poisson_grid(1.6, 0.9, n=11)
    # A single NaN cell makes the marginal means NaN -> must raise (not crash in scipy).
    bad = grid.copy()
    bad[3, 4] = np.nan
    with pytest.raises(ValueError, match="non-finite predictive grid"):
        inflate_predictive(bad, is_provisional=True, strength=0.5)
    # An all-zeros grid (the 0/0 underflow signature) -> NaN means -> typed raise.
    allzero = np.zeros((11, 11))
    with pytest.raises(ValueError, match="non-finite predictive grid"):
        inflate_predictive(allzero, is_provisional=True, strength=0.5)
    # An inf cell is likewise non-finite -> typed raise.
    infgrid = grid.copy()
    infgrid[0, 0] = np.inf
    with pytest.raises(ValueError, match="non-finite predictive grid"):
        inflate_predictive(infgrid, is_provisional=True, strength=0.5)


def test_inflate_noop_when_marginal_mean_near_zero():
    """No-op guard: a marginal mean at the support edge (~0, all mass at 0 goals)
    has no interior max-entropy solution and nothing to widen, so the grid is
    returned unchanged. A degenerate 0-0 grid (both marginal means 0) trips this."""
    grid = np.zeros((11, 11))
    grid[0, 0] = 1.0  # all mass on 0-0: both marginal means are exactly 0
    out = inflate_predictive(grid, is_provisional=True, strength=0.5)
    assert np.array_equal(out, grid)


def test_inflate_strength_scales_widening():
    """Larger strength => larger entropy increase (more weight on the max-entropy
    reference), while BOTH marginal means stay put (to machine precision) either
    way."""
    grid = _poisson_grid(1.6, 0.9, n=11)
    mh0, ma0 = _marginal_means(grid)
    hh0, ha0 = _marginal_entropies(grid)
    small = inflate_predictive(grid, is_provisional=True, strength=0.2)
    large = inflate_predictive(grid, is_provisional=True, strength=0.8)
    hh_small, ha_small = _marginal_entropies(small)
    hh_large, ha_large = _marginal_entropies(large)
    assert hh_large > hh_small > hh0
    assert ha_large > ha_small > ha0
    # Mean preserved regardless of strength.
    for w in (small, large):
        mh1, ma1 = _marginal_means(w)
        assert mh1 == pytest.approx(mh0, abs=1e-6)
        assert ma1 == pytest.approx(ma0, abs=1e-6)


# ---------- predict-path surfaces the bad-config ValueError ----------


def test_predict_scoreline_surfaces_bad_widening_strength():
    """FIX B (quick check): a bad (c) ``strength`` in config must surface as a
    ``ValueError`` — it must NOT silently no-op. The fail-loud now fires at
    Posterior CONSTRUCTION (convergence-review blocker 2: validated once in
    ``__init__`` so it is independent of provisional status / which fixture /
    whether predict is ever called), which is strictly earlier than — and
    therefore subsumes — the old predict-time surfacing. Builds a tiny hand-made
    posterior (no sampling) with mechanism 'c' + an out-of-range strength and a
    provisional home team, then asserts construction raises.
    """
    import arviz as az
    import copy

    from wcmodel.config import load_config
    from wcmodel.model.posterior import Posterior

    teams = ["A", "B"]
    n_teams = len(teams)
    # Minimal posterior with the params predict_scoreline reads (dixon_coles):
    # team-indexed att/def with dims (chain, draw, team); scalar mu/home_adv/rho.
    posterior = {
        "att": np.zeros((1, 2, n_teams)),
        "def": np.zeros((1, 2, n_teams)),
        "mu": np.full((1, 2), 0.0),
        "home_adv": np.full((1, 2), 0.2),
        "rho": np.zeros((1, 2)),
    }
    # arviz 1.1.0: from_dict takes a nested {group: {var: array}} dict (the
    # `posterior=` kwarg form is older-arviz only — see inference.py provenance).
    idata = az.from_dict({"posterior": posterior})

    cfg = copy.deepcopy(load_config())
    cfg["model"]["widening"]["mechanism"] = "c"
    cfg["model"]["widening"]["strength"] = 1.5  # OUT OF RANGE -> must raise
    with pytest.raises(ValueError):
        Posterior(idata, teams, "dixon_coles",
                  provisional_teams={"A"}, config=cfg)


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
