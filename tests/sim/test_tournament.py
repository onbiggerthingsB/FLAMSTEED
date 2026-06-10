import numpy as np
from wcmodel.sim.tournament import simulate_tournament

from tests.sim.conftest import tiny_bracket


def test_progression_probs_are_coherent(small_store):
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=120, seed=0, advi_iters=2500)
    res = simulate_tournament(post, bracket=tiny_bracket(), n_sims=2000, seed=0,
                              max_goals=8, et_scale=0.333, pen_home_prob=0.5)
    probs = res.progression          # DataFrame: index=team, cols=stages
    assert np.isclose(probs["champion"].sum(), 1.0, atol=1e-9)
    assert (probs["champion"] <= probs["reach_final"] + 1e-12).all()
    assert (probs["reach_final"] <= probs["reach_sf"] + 1e-12).all()
    assert (res.se["champion"] >= 0).all()


def test_seeded_determinism(small_store):
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=80, seed=0, advi_iters=2000)
    a = simulate_tournament(post, bracket=tiny_bracket(), n_sims=500, seed=0, max_goals=8,
                            et_scale=0.333, pen_home_prob=0.5)
    b = simulate_tournament(post, bracket=tiny_bracket(), n_sims=500, seed=0, max_goals=8,
                            et_scale=0.333, pen_home_prob=0.5)
    assert a.progression.equals(b.progression)


import pytest
import wcmodel.sim.tournament as _tour
from wcmodel.sim.tournament import _FixtureSampler, _Cfg


def _capture_sample_score(monkeypatch):
    calls = []
    def fake(lh, la, *, rng, likelihood, rho=None, l3=None, max_goals=12, fatten_alpha=0.0):
        # fatten_alpha mirrors the 4b sample_score signature; these ET-scaling tests use
        # no tail_fatten override, so it must arrive as the byte-identical default 0.0.
        calls.append({"lh": lh, "la": la, "rho": rho, "l3": l3, "fatten_alpha": fatten_alpha})
        return (0, 0)
    monkeypatch.setattr(_tour, "sample_score", fake)
    return calls


class _StubRB:
    def __init__(self, likelihood, lh, la, *, l3=None, rho=None):
        self.likelihood = likelihood
        self.n_draws = 1
        self._lh, self._la = lh, la
        if l3 is not None:
            self.l3 = np.array([l3])
        if rho is not None:
            self.rho = np.array([rho])
    # Accept the T5 host_factor kwarg to mirror the real RateBook.rates signature
    # (a host's home game carries k*home_adv); this stub is rate-fixed so it ignores it.
    def rates(self, home, away, neutral, draw, host_factor=None):
        return self._lh, self._la


def test_bp_extra_time_scales_shared_l3(monkeypatch):
    """Codex T5 bug-guard: under bivariate-Poisson, extra time (30/90 of a match)
    scales ALL THREE Poisson rates by et_scale -- lh, la, AND the shared l3 (W3).
    Leaving l3 unscaled makes ET too high-scoring / too correlated."""
    LH, LA, L3, ET = 1.6, 1.1, 0.4, 1.0 / 3.0
    calls = _capture_sample_score(monkeypatch)
    cfg = _Cfg(max_goals=8, et_scale=ET, pen_home_prob=0.5)
    fs = _FixtureSampler(_StubRB("bivariate_poisson", LH, LA, l3=L3), draw=0, cfg=cfg)
    sample = fs.knockout_sampler("X", "Y", neutral=True)

    sample("regulation", rng=None)
    assert calls[-1]["rho"] is None
    assert calls[-1]["lh"] == pytest.approx(LH)
    assert calls[-1]["la"] == pytest.approx(LA)
    assert calls[-1]["l3"] == pytest.approx(L3)

    sample("extra_time", rng=None)
    assert calls[-1]["lh"] == pytest.approx(LH * ET)
    assert calls[-1]["la"] == pytest.approx(LA * ET)
    assert calls[-1]["l3"] == pytest.approx(L3 * ET)   # THE FIX (bug left this at L3)
    # No tail_fatten override here -> the sampler passes the byte-identical default 0.0.
    assert calls[-1]["fatten_alpha"] == 0.0


def test_dc_extra_time_scales_rates_not_rho(monkeypatch):
    """DC ET guard: lh/la scale by et_scale, but rho is a low-score dependence
    parameter (tau correction), NOT a goal rate -> it must NOT be scaled."""
    LH, LA, RHO, ET = 1.6, 1.1, -0.05, 1.0 / 3.0
    calls = _capture_sample_score(monkeypatch)
    cfg = _Cfg(max_goals=8, et_scale=ET, pen_home_prob=0.5)
    fs = _FixtureSampler(_StubRB("dixon_coles", LH, LA, rho=RHO), draw=0, cfg=cfg)
    sample = fs.knockout_sampler("X", "Y", neutral=True)

    sample("extra_time", rng=None)
    assert calls[-1]["lh"] == pytest.approx(LH * ET)
    assert calls[-1]["la"] == pytest.approx(LA * ET)
    assert calls[-1]["rho"] == pytest.approx(RHO)   # unscaled
    # No tail_fatten override here -> the sampler passes the byte-identical default 0.0.
    assert calls[-1]["fatten_alpha"] == 0.0


# --- Task 6: per-cutoff conditioning mechanics in simulate_one (fast, no ADVI). ---
# The ADVI leakage gate (test_leakage_sim.py) exercises the GROUP-fixing path
# end-to-end; these deterministic unit tests additionally pin down the KNOCKOUT
# fixing + the RNG-free contract that makes the canary's bit-identical invariance
# hold. _DetRB returns fixed rates so any sampled fixture is deterministic, but a
# FIXED fixture must not sample at all.
import pandas as pd
from wcmodel.sim.tournament import simulate_one, _match_depths
from tests.sim.conftest import tiny_bracket


class _DetRB:
    """Deterministic stub RateBook (one draw, fixed rates)."""
    likelihood = "dixon_coles"
    n_draws = 1
    rho = np.array([0.0])

    def rates(self, home, away, neutral, draw, host_factor=None):
        return 1.4, 1.0


class _NoDrawRNG:
    """RNG that raises on ANY consumption — proves a fully-pinned sim draws nothing
    (the mechanical basis of the canary's bit-identical invariance: fixing a fixture
    consumes no RNG, so two runs pinning the identical set stay in lockstep)."""
    def integers(self, *a, **k): raise AssertionError("integers drawn on a pinned sim")
    def random(self, *a, **k): raise AssertionError("random drawn on a pinned sim")
    def choice(self, *a, **k): raise AssertionError("choice drawn on a pinned sim")
    def poisson(self, *a, **k): raise AssertionError("poisson drawn on a pinned sim")
    def permutation(self, n): raise AssertionError("permutation drawn (unexpected tie)")


# Distinct, tie-free group standings (Brazil 9 > Argentina 6 > Croatia 3 > France 0)
# so rank_group never hits its seeded random tail — group order is fully determined
# by the pinned scores alone (no RNG). 1A=Brazil, 2A=Argentina feed the Final (104).
_DET_GROUP = {
    ("Brazil", "Argentina"): (2, 0), ("Croatia", "France"): (1, 0),
    ("Brazil", "Croatia"): (2, 0), ("Argentina", "France"): (1, 0),
    ("Brazil", "France"): (2, 0), ("Argentina", "Croatia"): (1, 0),
}
_FINAL_DATE = pd.Timestamp("2026-07-19")


def test_played_fully_pins_sim_consumes_no_rng():
    """A sim with EVERY fixture pinned (all 6 group fixtures + the Final) must draw
    NO random numbers: fixed fixtures bypass sample_score AND resolve_tie. This is
    the RNG-free contract underpinning the leakage canary's bit-identical runs."""
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    played = {
        "groups": _DET_GROUP,
        "knockout_results": {("Brazil", "Argentina", _FINAL_DATE): (1, 2)},  # Argentina win
        "match_dates": {104: _FINAL_DATE},
    }
    out = simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg, played=played,
                       depths=_match_depths(br))
    assert out["groups"] == {"Brazil": 0, "Argentina": 1, "Croatia": 2, "France": 3}
    assert out["champion"] == "Argentina"        # the ACTUAL pinned Final winner


def test_played_knockout_fix_is_load_bearing():
    """Flipping the pinned Final score flips the champion — proving the in-loop KO
    fix actually READS the played result (not an incidental sampled outcome)."""
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    base = dict(groups=_DET_GROUP, match_dates={104: _FINAL_DATE})
    arg = simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg,
                       played={**base, "knockout_results": {("Brazil", "Argentina", _FINAL_DATE): (1, 2)}},
                       depths=_match_depths(br))
    bra = simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg,
                       played={**base, "knockout_results": {("Brazil", "Argentina", _FINAL_DATE): (3, 0)}},
                       depths=_match_depths(br))
    assert arg["champion"] == "Argentina"
    assert bra["champion"] == "Brazil"


def test_played_knockout_penalty_decided_not_yet_pinnable():
    """A pinned knockout that is LEVEL after regulation+ET was decided by a penalty
    shootout, but the martj42 adapter drops the shootout winner — so the actual winner
    cannot be pinned. The sim FAILS LOUD (raises) rather than guessing/randomizing a
    known outcome, and the message names the real cause (shootout winner unrecorded)."""
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    played = {
        "groups": _DET_GROUP,
        # Level after reg+ET => penalty-decided; winner not recorded by the data source.
        "knockout_results": {("Brazil", "Argentina", _FINAL_DATE): (1, 1)},
        "match_dates": {104: _FINAL_DATE},
    }
    with pytest.raises(ValueError, match=r"(?i)(shootout|penalty).*winner") as exc:
        simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg, played=played,
                     depths=_match_depths(br))
    msg = str(exc.value)
    assert ("shootout" in msg or "penalty" in msg) and "winner" in msg


def test_played_none_simulates_every_fixture():
    """Back-compat: played=None (the T5 default) samples every fixture, so the RNG
    IS consumed — a NoDrawRNG must raise, confirming nothing is silently pinned."""
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    with pytest.raises(AssertionError, match="drawn"):
        simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg, played=None,
                     depths=_match_depths(br))


# --- Codex T7 (stale-serve guard): SimResult is a PURE FUNCTION of bracket CONTENT,
# independent of the `groups`/`group_fixtures` dict INSERTION order. ---
# `cache.py::_bracket_hash` canonicalizes the bracket by SORTING the group keys, so two
# content-identical brackets that differ only in group insertion order share a cache key.
# That is only SOUND if the sim itself is insertion-order-invariant; otherwise a cache hit
# could serve a seeded result the live sim would not produce. The sim walks each group in
# turn consuming the per-sim RNG (scoreline sampling + rank_group tail), so the consumption
# order — and hence the seeded result — must be a deterministic function of group CONTENT,
# i.e. the canonical sorted-by-group-key order the hash uses. These tests pin that.
import xarray as xr
from wcmodel.model.posterior import Posterior
from wcmodel.sim.bracket import build_bracket

_INV_TEAMS = ["Brazil", "Argentina", "Croatia", "France",
              "Spain", "England", "Germany", "Portugal"]


def _inv_posterior(seed=0):
    """A minimal but REAL Posterior over the 8 invariance-test teams (hand-built
    idata.posterior — no ADVI, runs in ms). Mirrors tests/sim/test_sim_cache.py."""
    rng = np.random.default_rng(seed)
    n_teams, n_chain, n_draw = len(_INV_TEAMS), 1, 8
    ds = xr.Dataset(
        {
            "att": (("chain", "draw", "team"),
                    rng.normal(0, 0.3, (n_chain, n_draw, n_teams))),
            "def": (("chain", "draw", "team"),
                    rng.normal(0, 0.3, (n_chain, n_draw, n_teams))),
            "mu": (("chain", "draw"), rng.normal(0.1, 0.05, (n_chain, n_draw))),
            "home_adv": (("chain", "draw"), rng.normal(0.2, 0.05, (n_chain, n_draw))),
            "rho": (("chain", "draw"), rng.normal(-0.05, 0.01, (n_chain, n_draw))),
        },
        coords={"team": list(_INV_TEAMS)},
    )
    idata = xr.DataTree.from_dict({"posterior": ds})
    return Posterior(idata, list(_INV_TEAMS), "dixon_coles", provisional_teams=set())


def _round_robin(teams):
    a, b, c, d = teams
    return [(a, b), (c, d), (a, c), (b, d), (a, d), (b, c)]


def _two_group_tournament(group_order):
    """A 2-group (4 teams each) -> single Final tournament dict, with the two groups
    emitted in ``group_order`` (a sequence of group dicts). The Final (match 104) pairs
    the two group winners (1A vs 1B), so BOTH groups feed the knockout — content is the
    SAME for any ordering; only the `groups` list (and hence dict insertion) order moves.
    Group fixtures carry NO ``match`` key (the group discriminator); the Final carries
    one + placeholder feeders."""
    fixtures = []
    for g in group_order:
        for h, aw in _round_robin(g["teams"]):
            fixtures.append({"home": h, "away": aw, "round": "Matchday 1"})
    fixtures.append({"match": 104, "home": "1A", "away": "1B", "round": "Final"})
    return {"groups": list(group_order), "fixtures": fixtures}


def test_simresult_invariant_to_group_insertion_order():
    """STALE-SERVE GUARD (Codex T7). Two brackets with IDENTICAL content but different
    group INSERTION order must produce a BYTE-IDENTICAL seeded SimResult — because
    `_bracket_hash` sorts the group keys (so they share a cache key), serving one for the
    other is only correct if the sim is insertion-order-invariant. RED on the old
    insertion-order group loop (the two orderings consume the per-sim RNG in different
    order -> different draws -> different progression); GREEN once the loop iterates groups
    in sorted-key order."""
    group_a = {"name": "A", "teams": _INV_TEAMS[:4]}
    group_b = {"name": "B", "teams": _INV_TEAMS[4:]}
    # SAME content, DIFFERENT group insertion order: A,B vs B,A.
    br_ab = build_bracket(_two_group_tournament([group_a, group_b]))
    br_ba = build_bracket(_two_group_tournament([group_b, group_a]))
    # Sanity: the two brackets are genuinely just a reordering — identical group CONTENT,
    # but a different `groups`/`group_fixtures` dict insertion order (the bug's trigger).
    assert dict(br_ab.groups) == dict(br_ba.groups)
    assert list(br_ab.groups) != list(br_ba.groups), "insertion order must differ"

    kw = dict(n_sims=400, seed=0, max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    res_ab = simulate_tournament(_inv_posterior(), bracket=br_ab, **kw)
    res_ba = simulate_tournament(_inv_posterior(), bracket=br_ba, **kw)
    assert res_ab.progression.equals(res_ba.progression), (
        "SimResult depends on group INSERTION order — a cache hit (keyed on the "
        "order-independent _bracket_hash) could serve a result the live sim would "
        "not produce (stale serve)"
    )
    assert res_ab.se.equals(res_ba.se)


def test_simresult_invariant_to_within_group_fixture_order():
    """Sister guard for the within-group level: `_bracket_hash` PRESERVES each group's
    fixture-list order (it does NOT sort the inner lists), and the sim samples each
    group's fixtures in list order — so a within-group fixture REORDERING is genuine
    new content that the hash distinguishes (a different key) and the sim must reflect.
    This documents the deliberate hash/sim contract: group keys canonicalized (sorted)
    in both; within-group fixture order PRESERVED in both. We assert the sim is NOT
    invariant to a within-group reorder (it is real content, correctly keyed)."""
    teams_a, teams_b = _INV_TEAMS[:4], _INV_TEAMS[4:]
    base = {"name": "A", "teams": teams_a}, {"name": "B", "teams": teams_b}
    br1 = build_bracket(_two_group_tournament(list(base)))

    # Reorder ONLY group A's within-group fixture list (same pairs, different order).
    rr_a = _round_robin(teams_a)
    rr_a_shuffled = [rr_a[3], rr_a[0], rr_a[5], rr_a[1], rr_a[4], rr_a[2]]
    fixtures = ([{"home": h, "away": aw, "round": "Matchday 1"} for h, aw in rr_a_shuffled]
                + [{"home": h, "away": aw, "round": "Matchday 1"}
                   for h, aw in _round_robin(teams_b)]
                + [{"match": 104, "home": "1A", "away": "1B", "round": "Final"}])
    br2 = build_bracket({"groups": list(base), "fixtures": fixtures})

    assert br1.group_fixtures["A"] != br2.group_fixtures["A"], "fixture order must differ"
    kw = dict(n_sims=400, seed=0, max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    res1 = simulate_tournament(_inv_posterior(), bracket=br1, **kw)
    res2 = simulate_tournament(_inv_posterior(), bracket=br2, **kw)
    # Within-group order IS content (hash preserves it -> distinct key): results differ.
    assert not res1.progression.equals(res2.progression), (
        "within-group fixture order is real content the hash distinguishes; the sim "
        "must reflect it (else the hash and sim would disagree one level down)"
    )
