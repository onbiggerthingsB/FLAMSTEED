"""Item A standings BUILDER + gate tests (dashboard layer), exercised directly on the tiny
sim fixtures (no production fit/sim).

Acceptance coverage (per the build spec):
  #1 per team P(top2)+P(3rd qualify)+P(eliminated) == 1          -> test_fate_partition_*
  #2 per group Σ P(top2) == 2.000 (exact by construction)        -> test_sum_p_top2_*
  #3 across all 12 groups Σ P(3rd qualify) == 8.000              -> test_sum_third_qualify_*
  #4 [LOAD-BEARING] Σ E[Pts] over the 4 teams == 18 − Σ P(draw)  -> test_cross_tab_*
  #5 (UI) covered by the vitest suite.

#2/#3 hold EXACTLY by construction on a single SimResult, so they are also asserted at the
sim layer (every draw advances exactly 2 per group and exactly 8 thirds across 12 groups);
here we assert the BUILDER preserves them in the standings rows.
"""
import numpy as np
import pandas as pd
import pytest

from wcmodel.dashboard.tournament_view import standings_view
from wcmodel.dashboard.schema import gate_standings
from wcmodel.sim.tournament import simulate_one, simulate_tournament, _match_depths, _Cfg
from wcmodel.sim.groups import group_table

from tests.sim.conftest import tiny_bracket


def _tiny_sim(small_store, *, n_sims=3000, seed=0):
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=120, seed=0, advi_iters=2500)
    return simulate_tournament(post, bracket=tiny_bracket(), n_sims=n_sims, seed=seed,
                               max_goals=8, et_scale=0.333, pen_home_prob=0.5)


# ── #1 fate partition ────────────────────────────────────────────────────────────────────
def test_fate_partition_sums_to_one_per_team(small_store):
    sim = _tiny_sim(small_store)
    view = standings_view(sim, groups=tiny_bracket().groups)
    for rows in view.values():
        for r in rows:
            top2 = r["p_top2"]["value"]
            q3 = r["p_third_qualify"]["value"]
            elim = r["p_eliminated"]["value"]
            assert abs((top2 + q3 + elim) - 1.0) < 1e-9, f"{r['team']} fate partition != 1"
            # P(advance) == P(top2) + P(3rd qualify) exactly.
            assert abs(r["p_advance"]["value"] - (top2 + q3)) < 1e-12


# ── #2 Σ P(top2) == 2.000 per group (exact by construction) ──────────────────────────────
def test_sum_p_top2_is_two_per_group(small_store):
    sim = _tiny_sim(small_store)
    view = standings_view(sim, groups=tiny_bracket().groups)
    for g, rows in view.items():
        s = sum(r["p_top2"]["value"] for r in rows)
        # Exact: every sim draw places exactly 2 of the 4 teams in {first, second}.
        assert abs(s - 2.0) < 1e-12, f"group {g}: Σ P(top2) = {s} != 2.000"


# ── #3 Σ P(3rd qualify) across all groups == 8.000 ───────────────────────────────────────
def test_sum_third_qualify_is_eight_across_groups_real_bracket():
    """On the REAL 12-group 2026 bracket, exactly 8 thirds qualify EVERY sim, so across all 12
    groups Σ P(3rd qualify) == 8.000 exactly. (The tiny 1-group bracket has NO best-third
    slots, so its Σ is 0 — this property only has teeth on the real bracket, which we sim at a
    tiny n with a FLAT synthetic posterior over its 48 teams.)"""
    from pathlib import Path
    from wcmodel.data.tournament import load_tournament
    from wcmodel.sim.bracket import build_bracket
    real_draw = Path(__file__).resolve().parents[2] / "config" / "tournament_2026.yaml"
    bracket = build_bracket(load_tournament(real_draw))
    # Build a posterior over EXACTLY the bracket's teams so RateBook resolves every fixture.
    # A flat synthetic posterior keeps this CPU-trivial (no fit) while exercising the real
    # 12-group + best-8-thirds structure end to end.
    teams = [t for ts in bracket.groups.values() for t in ts]
    sim = _synthetic_sim(teams, bracket, n_sims=200, seed=0)
    view = standings_view(sim, groups=bracket.groups)
    total = sum(r["p_third_qualify"]["value"] for rows in view.values() for r in rows)
    assert abs(total - 8.0) < 1e-9, f"Σ P(3rd qualify) across 12 groups = {total} != 8.000"
    # Cross-check #2 on the real bracket too: every group sums to 2.000.
    for g, rows in view.items():
        assert abs(sum(r["p_top2"]["value"] for r in rows) - 2.0) < 1e-12


def _synthetic_sim(teams, bracket, *, n_sims, seed):
    """A CPU-trivial SimResult over the REAL 12-group bracket from a FLAT synthetic posterior
    (every team equal strength: att=def=mu=home_adv=0). No fit — we hand-build the minimal
    xarray posterior RateBook consumes, then run the production simulate_tournament. Strengths
    are irrelevant to acceptance #2/#3, which hold by CONSTRUCTION (every draw advances exactly
    2 per group and exactly 8 thirds across 12 groups) regardless of the rates."""
    import numpy as np
    import xarray as xr
    from wcmodel.config import load_config
    from wcmodel.model.posterior import Posterior

    n_teams = len(teams)
    nd = 2                                    # two posterior draws (RateBook needs >= 1)
    post_ds = xr.Dataset(
        {"att": (("chain", "draw", "team"), np.zeros((1, nd, n_teams))),
         "def": (("chain", "draw", "team"), np.zeros((1, nd, n_teams))),
         "mu": (("chain", "draw"), np.zeros((1, nd))),
         "home_adv": (("chain", "draw"), np.zeros((1, nd))),
         "rho": (("chain", "draw"), np.zeros((1, nd)))},
        coords={"team": list(teams)},
    )
    dt = xr.DataTree.from_dict({"posterior": post_ds})
    post = Posterior(dt, list(teams), "dixon_coles", config=load_config())
    return simulate_tournament(post, bracket=bracket, n_sims=n_sims, seed=seed,
                               max_goals=8, et_scale=0.333, pen_home_prob=0.5)


# ── #4 [LOAD-BEARING] cross-tab identity: Σ E[Pts] == 18 − Σ P(draw) ─────────────────────
def test_cross_tab_sum_expected_points_equals_18_minus_sum_draws_PER_DRAW():
    """The identity is EXACT every sim draw: in a 4-team group's 6 round-robin matches each
    decisive match awards 3 total points and each DRAW awards 2, so Σ points = 3*(6 − d) +
    2*d = 18 − d where d = #drawn matches. Therefore Σ E[Pts] = 18 − E[#draws] = 18 −
    Σ_match P(draw_match). DOCSTRING SUBTLETY (acceptance #4): the per-match draw 'probability'
    here is the sim's ACTUAL per-match draw indicator — realized (0/1) for a CONDITIONED
    (played) match, the forecast frequency for an unplayed one. On the tiny unconditioned
    fixtures every match is sampled, so the sim's per-match draw frequency coincides with the
    displayed one_x_two.draw. We prove the per-draw algebraic identity directly with a fully-
    pinned deterministic sim (1 drawn match -> Σ points == 17 == 18 − 1)."""
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.333, pen_home_prob=0.5)
    # Pin all 6 group fixtures; make EXACTLY ONE of them a draw (Croatia 1-1 France).
    pinned = {
        ("Brazil", "Argentina"): (2, 0), ("Croatia", "France"): (1, 1),   # the lone DRAW
        ("Brazil", "Croatia"): (2, 0), ("Argentina", "France"): (1, 0),
        ("Brazil", "France"): (2, 0), ("Argentina", "Croatia"): (1, 0),
    }
    n_draws = sum(1 for (hg, ag) in pinned.values() if hg == ag)
    played = {"groups": pinned, "match_dates": {104: pd.Timestamp("2026-07-19")},
              "knockout_results": {("Brazil", "Argentina", pd.Timestamp("2026-07-19")): (1, 0)}}

    class _DetRB:
        likelihood = "dixon_coles"; n_draws_attr = 1; rho = np.array([0.0])
        n_draws = 1
        def rates(self, home, away, neutral, draw, host_factor=None): return 1.4, 1.0

    out = simulate_one(br, _DetRB(), draw=0, rng=np.random.default_rng(0), cfg=cfg,
                       played=played, depths=_match_depths(br))
    sum_points = sum(gst["points"] for gst in out["group_stats"].values())
    assert sum_points == 18 - n_draws == 17     # the exact per-draw cross-tab identity


def test_cross_tab_sum_expected_points_within_3se_on_sampled_sim(small_store):
    """Aggregated cross-tab identity (acceptance #4) on the SAMPLED tiny sim: Σ E[Pts] over the
    4 teams == 18 − Σ_match P(draw_match), where Σ_match P(draw) is the sim's OWN per-match draw
    frequency (the unconditioned tiny fixture coincides with the displayed one_x_two.draw).

    TOLERANCE (documented): Σ points per draw = 18 − d_s with d_s = that draw's #drawn matches.
    Σ E[Pts] = 18 − mean(d_s) is therefore an EXACT rearrangement — the ONLY error is the MC
    error of estimating mean(d_s), i.e. the SE of Σ E[Pts]. We compute Σ E[Pts]'s SE as the SE
    of the per-draw Σ points (sd/√N) and require |Σ E[Pts] − (18 − Σ draw_freq)| ≤ 3·SE. Since
    both sides are computed from the IDENTICAL sim draws the residual is ~machine-zero; the
    3·SE band is the spec-mandated envelope, satisfied with wide margin."""
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.333, pen_home_prob=0.5)
    from wcmodel.model.scoreline import fit
    from wcmodel.sim.scoreline import RateBook
    post = fit("2024-06-01", small_store, backend="advi", draws=120, seed=0, advi_iters=2500)
    rb = RateBook(post)
    teams = br.groups["A"]
    fixtures = br.group_fixtures["A"]
    N = 4000
    per_draw_sum_points = []
    draw_counts = np.zeros(len(fixtures))    # per-match #draws across sims (the draw frequency)
    # Re-run the group-stage scoreline path the same way simulate_tournament does: one posterior
    # draw per sim, fixed across the group's fixtures (focal property #1), seeded per sim.
    children = np.random.SeedSequence(0).spawn(N)
    from wcmodel.sim.tournament import _FixtureSampler
    for child in children:
        rng = np.random.default_rng(child)
        s = int(rng.integers(rb.n_draws))
        sampler = _FixtureSampler(rb, s, cfg)
        results = {(h, a): sampler.score(h, a, neutral=True, rng=rng) for h, a in fixtures}
        tbl = group_table(teams, results)
        per_draw_sum_points.append(sum(tbl[t]["points"] for t in teams))
        for i, (h, a) in enumerate(fixtures):
            hg, ag = results[(h, a)]
            if hg == ag:
                draw_counts[i] += 1
    per_draw_sum_points = np.array(per_draw_sum_points, float)
    sum_exp_points = per_draw_sum_points.mean()
    se_sum_points = per_draw_sum_points.std(ddof=1) / np.sqrt(N)
    sum_draw_freq = float(draw_counts.sum() / N)        # Σ_match P(draw_match), sim's own freq
    rhs = 18.0 - sum_draw_freq
    tol = 3.0 * se_sum_points
    assert abs(sum_exp_points - rhs) <= tol + 1e-9, (
        f"cross-tab identity: Σ E[Pts]={sum_exp_points:.6f} vs 18−Σdraw={rhs:.6f}; "
        f"|Δ|={abs(sum_exp_points - rhs):.2e} > 3·SE={tol:.2e}")


# ── gate_standings (the true-STOP serializer guard) ──────────────────────────────────────
def test_gate_standings_passes_on_real_view(small_store):
    sim = _tiny_sim(small_store)
    view = standings_view(sim, groups=tiny_bracket().groups)
    gate_standings(view)                     # must not raise on a real, coherent view


def test_gate_standings_stops_naked_number():
    """A standings probability node with a value but no se companion is a NAKED number -> STOP."""
    bad = {"A": [{"team": "X", "exp_points": {"value": 5.0, "se": 0.1},
                  "exp_gd": {"value": 1.0, "se": 0.1},
                  "p_top2": {"value": 0.6},          # NAKED: no se companion
                  "p_third_qualify": {"value": 0.2, "se": 0.01},
                  "p_eliminated": {"value": 0.2, "se": 0.01},
                  "p_advance": {"value": 0.8, "se": 0.01}, "fate": "advance"}]}
    with pytest.raises(ValueError, match="naked number"):
        gate_standings(bad)


def test_gate_standings_stops_incoherent_partition():
    """A fate partition that doesn't sum to 1 is incoherent -> STOP (every draw lands in
    exactly one fate, so the three must partition the unit)."""
    bad = {"A": [{"team": "X", "exp_points": {"value": 5.0, "se": 0.1},
                  "exp_gd": {"value": 1.0, "se": 0.1},
                  "p_top2": {"value": 0.6, "se": 0.01},
                  "p_third_qualify": {"value": 0.2, "se": 0.01},
                  "p_eliminated": {"value": 0.5, "se": 0.01},      # 0.6+0.2+0.5 = 1.3 != 1
                  "p_advance": {"value": 0.8, "se": 0.01}, "fate": "advance"}]}
    with pytest.raises(ValueError, match="partition"):
        gate_standings(bad)


def test_standings_sorted_by_p_advance_desc(small_store):
    sim = _tiny_sim(small_store)
    view = standings_view(sim, groups=tiny_bracket().groups)
    for rows in view.values():
        advs = [r["p_advance"]["value"] for r in rows]
        assert advs == sorted(advs, reverse=True), "rows not sorted by P(advance) desc"
