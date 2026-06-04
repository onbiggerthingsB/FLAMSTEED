"""Phase-3 T7 — the resolved OUTPUT MARKET set + per-market Monte-Carlo SE.

``simulate_tournament`` emits, per team, the six headline markets
(``champion, reach_final, reach_sf, reach_qf, advance_from_group, win_group``)
PLUS the per-group placing markets (``first, second, third, out``) — each with
its binomial MC standard error ``sqrt(p(1-p)/N)``. These tests pin the public
column set and the coherence relations that must hold BY CONSTRUCTION:

  * the six headline markets are present (with SE on every column);
  * ``win_group <= advance_from_group`` per team (a group winner always advances);
  * the ladder ``champion <= reach_final <= reach_sf <= reach_qf <=
    advance_from_group`` per team;
  * the per-group markets are a proper partition: ``first + second + third + out
    == 1`` per team (every sim places every group team exactly once);
  * ``win_group`` and the per-group ``first`` are the SAME quantity (placing==0).

Uses the fast ``tiny_bracket()`` (1 group of 4 -> a single Final) + the
``small_store`` ADVI posterior, so the whole MC loop runs in seconds.
"""
import numpy as np

from wcmodel.sim.tournament import simulate_tournament

from tests.sim.conftest import tiny_bracket

_HEADLINE = ["champion", "reach_final", "reach_sf", "reach_qf",
             "advance_from_group", "win_group"]
_PER_GROUP = ["first", "second", "third", "out"]


def _fit_and_sim(small_store, *, n_sims=2000, seed=0):
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=120, seed=0,
               advi_iters=2500)
    return simulate_tournament(post, bracket=tiny_bracket(), n_sims=n_sims, seed=seed,
                               max_goals=8, et_scale=0.333, pen_home_prob=0.5)


def test_six_headline_markets_present_with_se(small_store):
    """The six resolved headline markets exist in BOTH progression and se, and
    every one carries a non-negative MC standard error."""
    res = _fit_and_sim(small_store)
    for col in _HEADLINE:
        assert col in res.progression.columns, f"missing headline market {col!r}"
        assert col in res.se.columns, f"missing SE for headline market {col!r}"
        assert (res.se[col] >= 0).all(), f"negative SE on {col!r}"


def test_per_group_markets_present_with_se(small_store):
    """The per-group placing markets (first/second/third/out) exist for every
    team with a non-negative MC SE."""
    res = _fit_and_sim(small_store)
    for col in _PER_GROUP:
        assert col in res.progression.columns, f"missing per-group market {col!r}"
        assert col in res.se.columns, f"missing SE for per-group market {col!r}"
        assert (res.se[col] >= 0).all(), f"negative SE on {col!r}"


def test_win_group_le_advance_per_team(small_store):
    """A group winner always advances out of the group, so win_group probability
    can never exceed advance_from_group, per team."""
    res = _fit_and_sim(small_store)
    p = res.progression
    assert (p["win_group"] <= p["advance_from_group"] + 1e-12).all()


def test_reach_ladder_is_monotone_per_team(small_store):
    """champion <= reach_final <= reach_sf <= reach_qf <= advance_from_group per
    team (cumulative depth thresholds — holds by construction)."""
    res = _fit_and_sim(small_store)
    p = res.progression
    assert (p["champion"] <= p["reach_final"] + 1e-12).all()
    assert (p["reach_final"] <= p["reach_sf"] + 1e-12).all()
    assert (p["reach_sf"] <= p["reach_qf"] + 1e-12).all()
    assert (p["reach_qf"] <= p["advance_from_group"] + 1e-12).all()


def test_per_group_markets_partition_to_one(small_store):
    """first + second + third + out == 1 for every team that plays in a group:
    every sim places every group team in exactly one of the four buckets (a
    coherent partition). Teams in the posterior but NOT in the bracket's groups
    (the small_store panel has 14 teams; tiny_bracket uses 4) get 0 in all four
    buckets — they never played a group fixture — so the partition is a per-GROUP
    -team property, asserted exactly on the bracketed teams."""
    res = _fit_and_sim(small_store)
    p = res.progression
    group_teams = list(tiny_bracket().groups["A"])
    total = p.loc[group_teams, ["first", "second", "third", "out"]].sum(axis=1)
    assert np.allclose(total.to_numpy(), 1.0, atol=1e-9), (
        f"per-group placing markets must sum to 1 per group team, got {total.to_dict()}"
    )
    # Non-bracketed teams never played a group fixture -> all four buckets are 0.
    others = [t for t in p.index if t not in group_teams]
    assert (p.loc[others, ["first", "second", "third", "out"]].to_numpy() == 0).all(), (
        "teams not in any bracket group must have 0 in every per-group placing market"
    )


def test_win_group_equals_first(small_store):
    """win_group and the per-group `first` are the SAME quantity (group placing
    == 0) — they must be IDENTICAL, not two inconsistent computations."""
    res = _fit_and_sim(small_store)
    p = res.progression
    assert np.array_equal(p["win_group"].to_numpy(), p["first"].to_numpy()), (
        "win_group must equal the per-group `first` market (both are placing==0)"
    )
    # SE too (same count -> same binomial SE).
    assert np.array_equal(res.se["win_group"].to_numpy(), res.se["first"].to_numpy())


def test_advance_from_group_is_the_advance_column(small_store):
    """The public headline name is `advance_from_group` (the plan's market name).
    The legacy internal `advance` name must NOT leak into the public table."""
    res = _fit_and_sim(small_store)
    assert "advance_from_group" in res.progression.columns
    assert "advance" not in res.progression.columns, (
        "the public market is `advance_from_group`, not the legacy `advance`"
    )
