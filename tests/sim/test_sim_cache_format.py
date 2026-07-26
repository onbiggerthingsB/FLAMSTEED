"""Cache key: fmt=None == pre-change key; fmt dict changes it; miss passes fmt.

Two load-bearing contracts for the Phase-2A cache wiring (F6):

  * **Key**: with ``fmt=None`` the assembled params dict contains NO ``"fmt"``
    key AT ALL (absent, not ``null``) — so every WC-2026 key computed before this
    change is reproduced byte-for-byte and no cached run is invalidated. With a
    fmt dict the key gains exactly that one entry, and the resulting key differs.
    The same absent-vs-present discipline governs ``ko_host_factor``.
  * **Miss path**: the cold branch forwards ``fmt`` into ``simulate_tournament``.
    Wiring only the key would be the WORST failure mode — a fmt-specific result
    stored under a fmt-specific key but computed with WC-2026 semantics.
"""
from __future__ import annotations

import pytest

from wcmodel.sim import cache as sim_cache

from tests.sim.conftest import tiny_bracket
from tests.sim.test_sim_cache import _toy_posterior


def _base(tmp_path, **over):
    kw = dict(cutoff="2027-01-07T00:00:00Z", posterior=_toy_posterior(),
              bracket=tiny_bracket(), n_sims=20, seed=1, max_goals=8,
              et_scale=0.3333, pen_home_prob=0.5, cache_dir=tmp_path)
    kw.update(over)
    return kw


def _param_recorder(monkeypatch):
    """Record every params dict handed to ``content_key`` (both calls are kind
    ``"sim"``, so they are collected in a LIST rather than keyed by kind)."""
    seen = []
    real = sim_cache.content_key

    def rec(kind, params):
        seen.append(dict(params))
        return real(kind, params)

    monkeypatch.setattr(sim_cache, "content_key", rec)
    return seen


def test_key_params_without_fmt_identical_to_legacy(tmp_path, monkeypatch):
    seen = _param_recorder(monkeypatch)

    _, meta_none = sim_cache.cached_sim(**_base(tmp_path))
    _, meta_fmt = sim_cache.cached_sim(**_base(tmp_path), fmt={"best_thirds": 4})

    params_none, params_fmt = seen
    # CONTRACT: fmt=None -> the key is the PRE-CHANGE key (no 'fmt' entry at all).
    assert "fmt" not in params_none
    assert "ko_host_factor" not in params_none
    # ... and a fmt dict adds exactly that one entry, nothing else.
    assert params_fmt == {**params_none, "fmt": {"best_thirds": 4}}
    assert meta_none["key"] != meta_fmt["key"]


def test_ko_host_factor_absent_from_key_unless_set(tmp_path, monkeypatch):
    """``ko_host_factor`` is output-affecting whenever the KO host policy is on,
    so it must be in the key — under the SAME absent-when-None discipline."""
    seen = _param_recorder(monkeypatch)

    _, meta_none = sim_cache.cached_sim(**_base(tmp_path))
    _, meta_k = sim_cache.cached_sim(**_base(tmp_path), ko_host_factor=0.6)

    params_none, params_k = seen
    assert "ko_host_factor" not in params_none
    assert params_k == {**params_none, "ko_host_factor": 0.6}
    assert meta_none["key"] != meta_k["key"]


def test_cold_sim_receives_fmt(tmp_path, monkeypatch):
    seen = {}

    def fake_sim(posterior, **kw):
        seen.update(kw)
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(sim_cache, "simulate_tournament", fake_sim)
    with pytest.raises(RuntimeError):
        sim_cache.cached_sim(**_base(tmp_path / "cold"), fmt={"best_thirds": 4},
                             ko_host_factor=0.6)
    assert seen["fmt"] == {"best_thirds": 4}
    assert seen["ko_host_factor"] == 0.6
