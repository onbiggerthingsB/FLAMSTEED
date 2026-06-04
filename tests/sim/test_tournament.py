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
