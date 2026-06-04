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
    def fake(lh, la, *, rng, likelihood, rho=None, l3=None, max_goals=12):
        calls.append({"lh": lh, "la": la, "rho": rho, "l3": l3})
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
    def rates(self, home, away, neutral, draw):
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

    def rates(self, home, away, neutral, draw):
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


def test_played_knockout_level_score_rejected():
    """A decided knockout must have a winner — a level pinned KO score is malformed
    and must raise (regulation/ET/penalties can't be reconstructed from a draw)."""
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    played = {
        "groups": _DET_GROUP,
        "knockout_results": {("Brazil", "Argentina", _FINAL_DATE): (1, 1)},  # level: invalid
        "match_dates": {104: _FINAL_DATE},
    }
    with pytest.raises(ValueError, match="level"):
        simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg, played=played,
                     depths=_match_depths(br))


def test_played_none_simulates_every_fixture():
    """Back-compat: played=None (the T5 default) samples every fixture, so the RNG
    IS consumed — a NoDrawRNG must raise, confirming nothing is silently pinned."""
    br = tiny_bracket()
    cfg = _Cfg(max_goals=8, et_scale=0.3333, pen_home_prob=0.5)
    with pytest.raises(AssertionError, match="drawn"):
        simulate_one(br, _DetRB(), draw=0, rng=_NoDrawRNG(), cfg=cfg, played=None,
                     depths=_match_depths(br))
