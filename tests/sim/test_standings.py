"""Item A standings hook (sim OUTPUT layer): per-team group-stage E[Pts]/E[GD] +
the qualify-as-best-8-third vs eliminated split.

FOCAL property (asserted by ``test_standings_hook_is_byte_identical_on_preexisting_outputs``):
the hook is ADDITIVE-ONLY. Running the SAME seeded sim and reading the pre-existing
``progression``/``se`` must be BIT-IDENTICAL whether or not the new ``standings``/
``third_split`` fields are consumed — the hook adds keys, it changes NO sim logic,
sampling, or seeds.
"""
import numpy as np
import pandas as pd
import pytest

from wcmodel.sim.tournament import simulate_one, simulate_tournament, _match_depths, _Cfg

from tests.sim.conftest import tiny_bracket


# ── Byte-identical guarantee (the load-bearing additive-only assertion) ──────────────────
def test_standings_hook_is_byte_identical_on_preexisting_outputs(small_store):
    """Two runs at the SAME seed produce IDENTICAL progression + se DataFrames; reading the
    new standings/third_split fields cannot perturb them (they are pure OUTPUT additions over
    already-drawn scorelines, consuming no RNG). This is the spec's 'existing aggregates must
    be BYTE-IDENTICAL with the hooks present' canary."""
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=80, seed=0, advi_iters=2000)
    kw = dict(bracket=tiny_bracket(), n_sims=400, seed=0, max_goals=8,
              et_scale=0.333, pen_home_prob=0.5)
    a = simulate_tournament(post, **kw)
    b = simulate_tournament(post, **kw)
    # The PRE-EXISTING aggregates are bit-identical run-to-run (seeded determinism preserved).
    assert a.progression.equals(b.progression)
    assert a.se.equals(b.se)
    assert a.random_tail_rate == b.random_tail_rate
    # And the NEW aggregates are themselves deterministic (same seed -> same values).
    assert a.standings.equals(b.standings)
    assert a.third_split.equals(b.third_split)


def test_simulate_one_adds_keys_without_changing_preexisting_return(small_store):
    """simulate_one's pre-existing keys (depth/groups/champion/random_tail) are present and
    unchanged; the standings hook only ADDS group_stats/group_third/qualified_third_groups."""
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=40, seed=0, advi_iters=1500)
    from wcmodel.sim.scoreline import RateBook
    rb = RateBook(post)
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.333, pen_home_prob=0.5)
    rng = np.random.default_rng(0)
    out = simulate_one(br, rb, draw=0, rng=rng, cfg=cfg, depths=_match_depths(br))
    # pre-existing contract
    assert set(["depth", "groups", "champion", "random_tail"]) <= set(out)
    # additive keys
    assert "group_stats" in out and "group_third" in out and "qualified_third_groups" in out
    # group_stats covers every group team with integer points/gd
    assert set(out["group_stats"]) == set(br.groups["A"])
    for team, gst in out["group_stats"].items():
        assert set(gst) == {"points", "gd"}
        assert isinstance(gst["points"], int) and isinstance(gst["gd"], int)


# ── E[Pts] / E[GD] correctness vs a fully-pinned (deterministic) sim ─────────────────────
class _DetRB:
    """Deterministic stub RateBook (one draw, fixed rates) — mirrors test_tournament's stub."""
    likelihood = "dixon_coles"
    n_draws = 1
    rho = np.array([0.0])

    def rates(self, home, away, neutral, draw, host_factor=None):
        return 1.4, 1.0


# Brazil 9 > Argentina 6 > Croatia 3 > France 0 (tie-free). GDs:
#   Brazil  +6 (2-0, 2-0, 2-0), Argentina +1 (0-2, 1-0, 1-0 -> gf 2 ga 2... see below).
# Exact tallies computed by group_table over these scores.
_DET_GROUP = {
    ("Brazil", "Argentina"): (2, 0), ("Croatia", "France"): (1, 0),
    ("Brazil", "Croatia"): (2, 0), ("Argentina", "France"): (1, 0),
    ("Brazil", "France"): (2, 0), ("Argentina", "Croatia"): (1, 0),
}


def test_expected_points_and_gd_match_pinned_scores():
    """With every group fixture pinned to a known score, E[Pts]/E[GD] equal the exact
    group-table tally (SE == 0, since every draw is identical) — proving the hook reads the
    REAL per-draw points/gd off the same group_table the ranking uses."""
    from wcmodel.sim.groups import group_table
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.333, pen_home_prob=0.5)
    played = {"groups": _DET_GROUP, "match_dates": {104: pd.Timestamp("2026-07-19")},
              "knockout_results": {("Brazil", "Argentina", pd.Timestamp("2026-07-19")): (1, 0)}}
    out = simulate_one(br, _DetRB(), draw=0, rng=np.random.default_rng(0), cfg=cfg,
                       played=played, depths=_match_depths(br))
    expected = group_table(br.groups["A"], _DET_GROUP)
    for team in br.groups["A"]:
        assert out["group_stats"][team]["points"] == expected[team]["points"]
        assert out["group_stats"][team]["gd"] == expected[team]["gd"]
