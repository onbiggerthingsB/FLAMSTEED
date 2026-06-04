"""Phase-3 T8 — MC-convergence + degenerate-input tests for ``simulate_tournament``.

These are BEHAVIOURAL teeth for the full MC loop (Tasks 0-7), built on the
``tiny_bracket()`` (1 group of 4 -> a single Final) and HAND-ROLLED toy posteriors
(the ``_toy_posterior`` pattern from ``test_sim_cache.py``) so every test runs in
milliseconds with EXACT control over team strengths — control a real ADVI fit cannot
guarantee (it can't be asked for a perfectly-dominant or perfectly-equal field).

Three degenerate inputs pin the loop's end-to-end semantics where the answer is
known a priori:

  * a DOMINANT team wins almost surely  (P(champion) -> 1);
  * an EQUAL-STRENGTH field is symmetric within Monte-Carlo SE  (each P(champion)
    ~ 1/4), and the FIFA tiebreak random tail VISIBLY fires (equal strengths => far
    more all-level groups than a separated field => the seeded drawing-of-lots tail
    decides placings on a non-trivial fraction of sims);
  * an ELIMINATED team (bottom-2 of a fully-played group, via the per-cutoff
    conditioning in ``run.simulate``) has P(advance_from_group) == 0 BY CONSTRUCTION.

Plus an MC-convergence check: on a NON-degenerate field the market probabilities at
N and 4N (same seed) agree within a documented multiple of the binomial SE(N). All
runs are seeded => these are DETERMINISTIC comparisons (fixed under the seed), not
flaky probabilistic ones; the tolerance multiples are chosen to hold under the fixed
seed and are documented inline. A market that blew past its band would indicate a
real bug (a too-good or wrong result), not a tolerance to loosen.
"""
import numpy as np
import pandas as pd
import xarray as xr

from wcmodel.model.posterior import Posterior
from wcmodel.sim.tournament import simulate_tournament

from tests.sim.conftest import tiny_bracket

# tiny_bracket()'s four group-A teams, in the order build_bracket lays out the group.
_TEAMS = ["Brazil", "Argentina", "Croatia", "France"]


def _toy_posterior(att, deff, *, mu=0.1, home_adv=0.2, rho=-0.05,
                   teams=_TEAMS, likelihood="dixon_coles"):
    """A minimal REAL ``Posterior`` over ``teams`` with FULLY CONTROLLED, per-team
    att/def point values (NO randomness, NO ADVI). Every parameter is a single fixed
    draw (``chain=draw=1``), so ``RateBook`` reads EXACTLY the strengths we set and the
    only stochasticity in the sim is the scoreline / tiebreak sampling — which is what
    these degenerate tests want to isolate.

    ``att``/``deff`` are per-team sequences aligned to ``teams``: a team's expected
    goal rate rises with its own ``att`` and with its opponent's (low) ``def`` exactly
    as ``RateBook.rates`` rebuilds ``log λ = μ + att[scorer] - def[conceder]`` (home_adv
    is off under the sim's neutral-ground default). Mirrors the ``_toy_posterior`` shape
    in ``test_sim_cache.py`` (att/def/mu/home_adv + rho), but with chosen — not seeded —
    values so the field is deterministic by design."""
    att = np.asarray(att, dtype=float)
    deff = np.asarray(deff, dtype=float)
    n = len(teams)
    assert att.shape == (n,) and deff.shape == (n,)
    ds = xr.Dataset(
        {
            "att": (("chain", "draw", "team"), att.reshape(1, 1, n)),
            "def": (("chain", "draw", "team"), deff.reshape(1, 1, n)),
            "mu": (("chain", "draw"), np.full((1, 1), mu)),
            "home_adv": (("chain", "draw"), np.full((1, 1), home_adv)),
            "rho": (("chain", "draw"), np.full((1, 1), rho)),
        },
        coords={"team": list(teams)},
    )
    idata = xr.DataTree.from_dict({"posterior": ds})
    return Posterior(idata, list(teams), likelihood, provisional_teams=set())


def _run(posterior, *, n_sims, seed=0):
    """Run ``simulate_tournament`` on ``tiny_bracket()`` with the production-default
    sim knobs (max_goals=12, et_scale=1/3, pen_home_prob=0.5)."""
    return simulate_tournament(
        posterior, bracket=tiny_bracket(), n_sims=n_sims, seed=seed,
        max_goals=12, et_scale=0.3333, pen_home_prob=0.5,
    )


# ---------------------------------------------------------------------------
# Degenerate 1 — a DOMINANT team wins almost surely.
# ---------------------------------------------------------------------------
def test_dominant_team_wins_almost_surely():
    """One overwhelmingly strong team (huge attack + miserly defence) against three
    weak ones => it tops its group and wins the single Final almost every sim. Asserts
    P(champion) > 0.99 and P(reach_final) ~ 1 for that team.

    Why ~1 and not exactly 1: the Final is still a sampled scoreline, so even a vastly
    superior team can (astronomically rarely) lose; with these strengths the per-match
    upset prob is ~1e-7, far below the 0.99 floor at N=4000."""
    # Brazil: strong attack (+1.6), elite defence (def +2.0 => opponents' rate ~ e^-2).
    # The other three: weak attack (-0.5), porous defence (-0.5).
    att = [1.6, -0.5, -0.5, -0.5]
    deff = [2.0, -0.5, -0.5, -0.5]
    res = _run(_toy_posterior(att, deff), n_sims=4000)

    champ = res.progression["champion"]
    assert champ["Brazil"] > 0.99, f"dominant team champion prob too low: {champ['Brazil']}"
    assert res.progression.loc["Brazil", "reach_final"] > 0.99
    # Sanity: the three weak teams share the residual (<1% total) — none is a co-favourite.
    assert champ.drop("Brazil").sum() < 0.01
    # Coherence still holds at the extreme: champion <= reach_final <= advance.
    assert champ["Brazil"] <= res.progression.loc["Brazil", "reach_final"] + 1e-12
    assert (res.progression.loc["Brazil", "reach_final"]
            <= res.progression.loc["Brazil", "advance_from_group"] + 1e-12)


# ---------------------------------------------------------------------------
# Degenerate 2 — EQUAL strengths are symmetric within MC SE, and the random tail fires.
# ---------------------------------------------------------------------------
def test_equal_strengths_are_symmetric_within_mc_se():
    """Four IDENTICAL teams => by symmetry each should win the tournament with prob
    1/4. The four observed champion probs must agree within a few x the binomial MC SE.

    Tolerance (documented): we assert the four champion probs are mutually within
    ``4 * SE`` where ``SE = sqrt(p(1-p)/N)`` at ``p = 1/4`` — i.e. each is within 4 SE of
    the 1/4 ideal, so any pair is within 8 SE; we use the tighter per-arm ``|p - 1/4| <
    4*SE`` form. At N=20000, SE ~ 0.00306, so 4*SE ~ 0.0122. The seed is fixed, so this
    is a deterministic check, not a flaky one; 4 SE is a comfortable, non-vacuous band
    (the observed max deviation is well inside it — see the assert message) chosen so a
    genuinely ASYMMETRIC loop (a real bug favouring one slot) would blow past it."""
    att = [0.2, 0.2, 0.2, 0.2]
    deff = [0.1, 0.1, 0.1, 0.1]
    n_sims = 20000
    res = _run(_toy_posterior(att, deff), n_sims=n_sims)

    champ = res.progression["champion"]
    se = np.sqrt(0.25 * 0.75 / n_sims)           # binomial SE at the p=1/4 ideal
    dev = (champ - 0.25).abs()
    assert (dev < 4 * se).all(), (
        f"equal-strength champion probs not symmetric within 4*SE ({4*se:.4f}); "
        f"probs={champ.to_dict()}, max|p-1/4|={dev.max():.4f}"
    )
    # The four champion probs sum to 1 (every sim crowns exactly one champion).
    assert abs(champ.sum() - 1.0) < 1e-12

    # The FIFA tiebreak random tail must be VISIBLY active: equal strengths => far more
    # all-equal group standings (points AND head-to-head AND GD AND GF all level) than a
    # separated field => the seeded drawing-of-lots tail fires on a non-trivial fraction
    # of sims. Observed at this seed: ``random_tail_rate ~ 0.031`` (~3% of sims) — note
    # it is NOT near 1, because the per-match Poisson scoreline noise still usually
    # separates teams on GD/GF; a full all-level group (where the tail is forced) is the
    # minority. We assert ``> 0.01`` — comfortably below the observed 0.031, but a hard
    # line above 0: a loop that NEVER fired the tail (a broken tiebreak) would give
    # exactly 0.0 and fail. This is the converse of ``test_mc_convergence_n_vs_4n``,
    # which asserts a SEPARATED field fires the tail RARELY.
    assert res.random_tail_rate > 0.01, (
        f"equal-strength field should visibly trigger the random tiebreak tail; "
        f"random_tail_rate={res.random_tail_rate}"
    )


# ---------------------------------------------------------------------------
# Degenerate 3 — an ELIMINATED team has P(advance_from_group) == 0 by construction.
# ---------------------------------------------------------------------------
def _fully_played_group_store(tmp_path, scores, *, group_date="2026-06-10"):
    """A tmp ``BitemporalStore`` whose ``results`` table contains ALL SIX round-robin
    fixtures of the tiny_bracket group, every one dated ``group_date`` with the chosen
    ``scores`` — so as of a LATER cutoff the whole group is played-as-of-cutoff and the
    standings are DETERMINISTIC (no sampling). ``scores`` maps ``(home, away) -> (hg,
    ag)`` for the six pairs in tiny_bracket's fixture order."""
    from wcmodel.data.sources.results import normalize_results
    from wcmodel.data.store import BitemporalStore, Policy

    rows = [
        (group_date, h, a, hg, ag, "FIFA World Cup", "Dallas", "United States", True)
        for (h, a), (hg, ag) in scores.items()
    ]
    raw = pd.DataFrame(
        rows,
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "city", "country", "neutral"],
    )
    store = BitemporalStore(root=tmp_path)
    store.write("results", normalize_results(raw), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    return store


def _synthetic_tournament(group_date="2026-06-10"):
    """tiny_bracket's 1-group-of-4 -> Final as a tournament DICT (so ``run.simulate``
    can read the fixture->date map): the six group fixtures all carry ``group_date`` and
    the Final (match 104) feeds from 1A/2A. Fixture pairing matches tiny_bracket exactly
    so the played scores line up with the simulated bracket's group."""
    a, b, c, d = _TEAMS
    pairs = [(a, b), (c, d), (a, c), (b, d), (a, d), (b, c)]
    return {
        "groups": [{"name": "A", "teams": list(_TEAMS)}],
        "fixtures": [
            *[{"home": h, "away": aw, "date": group_date, "round": "Matchday 1"}
              for h, aw in pairs],
            {"match": 104, "home": "1A", "away": "2A", "round": "Final"},
        ],
    }


def test_eliminated_team_has_zero_advance(tmp_path):
    """A team that finishes BOTTOM-2 of a fully-played group cannot reach the top-2, so
    its ``advance_from_group`` (and every forward market) is EXACTLY 0 — not "small",
    zero — because the per-cutoff conditioning (``run.simulate``) PINS the whole group to
    its actual scores, making the standings deterministic.

    Construction: all six group fixtures are dated 2026-06-10 in the store and we
    simulate at cutoff 2026-07-01, so the entire group is played-as-of-cutoff. The chosen
    scores make Brazil & Argentina win everything and Croatia & France lose everything:

        Brazil  beats Argentina, Croatia, France  -> 9 pts (1st)
        Argentina beats Croatia, France           -> 6 pts (2nd)
        Croatia beats France                       -> 3 pts (3rd)
        France loses all three                     -> 0 pts (4th)

    => Croatia (3rd) and France (4th) are ELIMINATED. Both must have
    advance_from_group == 0 (they are bottom-2 in EVERY sim, since the group is fixed),
    and Brazil & Argentina must have advance_from_group == 1 (always top-2). Only the
    Final (1A vs 2A = Brazil vs Argentina) is still simulated — exercising the T6
    "eliminated teams get 0 forward prob" path end to end."""
    from wcmodel.sim.run import SimConfig, simulate

    a, b, c, d = _TEAMS                  # Brazil, Argentina, Croatia, France
    # tiny_bracket fixture order: (a,b)(c,d)(a,c)(b,d)(a,d)(b,c). Pick scores giving the
    # strict ordering Brazil > Argentina > Croatia > France (home score first).
    scores = {
        (a, b): (2, 0),   # Brazil   beats Argentina
        (c, d): (1, 0),   # Croatia  beats France
        (a, c): (3, 0),   # Brazil   beats Croatia
        (b, d): (2, 0),   # Argentina beats France
        (a, d): (4, 0),   # Brazil   beats France
        (b, c): (2, 0),   # Argentina beats Croatia
    }
    store = _fully_played_group_store(tmp_path, scores)
    cfg = SimConfig(
        tournament=_synthetic_tournament(), n_sims=500, seed=0,
        max_goals=12, et_scale=0.3333, pen_home_prob=0.5,
    )
    # A toy posterior is still required (RateBook resolves the simulated Final), but the
    # group standings are FIXED by the played scores, so the posterior cannot affect who
    # advances — only who wins the Brazil-Argentina Final.
    post = _toy_posterior([0.3, 0.2, 0.1, 0.0], [0.2, 0.1, 0.0, -0.1])
    res = simulate("2026-07-01", post, store, cfg)

    adv = res.progression["advance_from_group"]
    # The two ELIMINATED (bottom-2) teams advance with probability EXACTLY zero.
    assert adv["Croatia"] == 0.0, f"eliminated Croatia advanced: {adv['Croatia']}"
    assert adv["France"] == 0.0, f"eliminated France advanced: {adv['France']}"
    # ... and every forward market for them is 0 too (advance is the loosest threshold).
    for col in ("reach_r16", "reach_qf", "reach_sf", "reach_final", "champion"):
        assert res.progression.loc["Croatia", col] == 0.0
        assert res.progression.loc["France", col] == 0.0
    # The two SURVIVORS advance with probability EXACTLY one (always top-2; group fixed).
    assert adv["Brazil"] == 1.0 and adv["Argentina"] == 1.0
    # Their group placings are pinned too: Brazil 1st, Argentina 2nd in every sim.
    assert res.progression.loc["Brazil", "first"] == 1.0
    assert res.progression.loc["Argentina", "second"] == 1.0
    # The group is fully pinned (no sampled group fixture) => the FIFA random tail never
    # fires on this run (the only sampled match is the Final, which has no group tiebreak).
    assert res.random_tail_rate == 0.0


# ---------------------------------------------------------------------------
# MC convergence — N vs 4N agree within a documented SE band on every market.
# ---------------------------------------------------------------------------
def test_mc_convergence_n_vs_4n():
    """On a NON-degenerate field (4 teams, modestly different strengths) the per-market
    progression probabilities at N and 4N (SAME seed) agree within a documented multiple
    of the binomial Monte-Carlo SE(N). Everything is seeded, so this is a DETERMINISTIC
    comparison (a fixed pair of runs under the fixed seed), not a flaky probabilistic one.

    Tolerance (documented): for every team x market we require
        |p_N - p_4N| <= 3 * SE_N,   SE_N = sqrt(p_hat (1 - p_hat) / N)
    with ``p_hat`` the 4N estimate (the more accurate one) and ``N = 4000`` (so
    ``4N = 16000``). SE_N is the spread of the COARSER estimate; the finer 4N estimate is
    ~2x tighter, so under independent sampling |p_N - p_4N| ~ sqrt(SE_N^2 + SE_4N^2) ~
    1.12*SE_N in expectation. The observed worst-case ratio at this seed is ~1.48*SE_N
    (a single market's finite-sample draw, still well inside the band), so 3*SE_N is a
    comfortable, non-vacuous line with real headroom. A zero-variance market
    (p in {0,1}: e.g. a team that NEVER reaches a round in either run) has SE_N == 0 and
    must match EXACTLY (|p_N - p_4N| == 0) — the strongest possible agreement, asserted
    directly. The seed is fixed so the band is a hard line; a market that blew past 3*SE_N
    would signal a real bug (a non-converging / wrong aggregation), not a tolerance to
    loosen — investigate, do not widen.

    We also assert ``random_tail_rate`` is LOGGED and is a SMALL fraction on this
    non-degenerate field (distinct strengths => groups usually separate on
    points/GD/GF => the seeded tail rarely fires), the converse of the equal-strength
    case above."""
    # Modestly different strengths: a clear-ish but not degenerate ordering.
    att = [0.6, 0.3, 0.0, -0.3]
    deff = [0.5, 0.2, -0.1, -0.4]
    post = _toy_posterior(att, deff)

    n = 4000
    res_n = _run(post, n_sims=n)
    res_4n = _run(post, n_sims=4 * n)

    p_n = res_n.progression
    p_4n = res_4n.progression
    # Same teams x markets in both runs.
    assert list(p_n.index) == list(p_4n.index)
    assert list(p_n.columns) == list(p_4n.columns)

    se_n = np.sqrt(p_4n * (1.0 - p_4n) / n)      # SE of the COARSER (N) estimate, p_hat=4N
    diff = (p_n - p_4n).abs()
    band = 3.0 * se_n
    # Degenerate (p in {0,1}) cells have se_n == 0 -> must match EXACTLY; add a tiny eps
    # only so floating compare of two equal zeros is unambiguous.
    within = diff <= band + 1e-12
    if not within.all().all():
        # Pinpoint the worst offender for the failure message (do NOT loosen — investigate).
        flat = (diff - band).stack()
        worst = flat.idxmax()
        raise AssertionError(
            f"market {worst} diverged beyond 3*SE_N: |p_N - p_4N|={diff.loc[worst]:.5f}, "
            f"3*SE_N={band.loc[worst]:.5f}, p_4N={p_4n.loc[worst]:.5f}"
        )

    # Zero-variance markets (p_4N in {0,1} => SE_N == 0) must match to the bit: a
    # threshold of 3*SE_N == 0 already FORCES |p_N - p_4N| == 0 above, so this is an
    # explicit, separate restatement of that strongest-agreement property. We compare on
    # the raw numpy arrays (a boolean-DataFrame mask would inject NaN into the unmasked
    # cells and make ``== 0.0`` spuriously False); ``zero_var.any()`` may be empty for
    # this field (no degenerate market), in which case the assertion is trivially true.
    zero_var = se_n.to_numpy() == 0.0
    assert np.all(diff.to_numpy()[zero_var] == 0.0), (
        "a p in {0,1} market disagreed between N and 4N despite zero binomial variance"
    )

    # random_tail_rate is logged and small on a non-degenerate field (converse of equal).
    assert 0.0 <= res_4n.random_tail_rate < 0.05, (
        f"non-degenerate field should rarely fire the random tail; "
        f"random_tail_rate={res_4n.random_tail_rate}"
    )
