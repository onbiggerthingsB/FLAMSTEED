"""Content-addressed posterior cache (spec 4.4).

A fit is reused ONLY when EVERY input that determines the posterior is identical;
any change -> cache miss (never serve a stale posterior). These tests prove the
HIT path skips resampling, reconstructs the full Posterior from the meta JSON
(teams / likelihood / provisional_teams) WITHOUT recomputing features/Elo, and
yields bit-identical predictions; and that changing any keyed input
(draws / seed / likelihood / a widening config value) misses.

Marked slow: the first call samples once (ADVI). Run them, but they can be
deselected with -m 'not slow'.
"""
import copy

import pytest

from wcmodel.config import load_config
from wcmodel.model.cache import cached_fit


@pytest.mark.slow
def test_second_call_hits_cache_and_skips_resample(small_store, tmp_path):
    kw = dict(cutoff="2024-06-01", store=small_store, backend="advi",
              draws=80, seed=0, advi_iters=2000, cache_dir=tmp_path)
    p1, meta1 = cached_fit(**kw)
    p2, meta2 = cached_fit(**kw)
    assert meta1["cache_hit"] is False and meta2["cache_hit"] is True
    # Identical predictions from the cached netCDF.
    a = p1.predict_1x2("Brazil", "Argentina"); b = p2.predict_1x2("Brazil", "Argentina")
    assert abs(a["home"] - b["home"]) < 1e-9
    # provisional_teams + teams survived the round-trip.
    assert p2.provisional_teams == p1.provisional_teams
    assert p2.teams == p1.teams and p2.likelihood == p1.likelihood


@pytest.mark.slow
def test_config_change_misses_cache(small_store, tmp_path):
    base = dict(cutoff="2024-06-01", store=small_store, backend="advi",
                draws=80, seed=0, advi_iters=2000, cache_dir=tmp_path)
    _, m1 = cached_fit(**base)
    _, m2 = cached_fit(**{**base, "draws": 81})        # different draws -> miss
    _, m3 = cached_fit(**{**base, "seed": 1})          # different seed -> miss
    assert m1["cache_hit"] is False
    assert m2["cache_hit"] is False and m3["cache_hit"] is False
    assert m1["key"] != m2["key"] != m3["key"] and m1["key"] != m3["key"]


@pytest.mark.slow
def test_likelihood_and_widening_config_change_miss(small_store, tmp_path):
    """A changed likelihood OR a changed model-config block (widening strength)
    must yield a different key -> miss. Stale-posterior protection: the key
    includes the likelihood and the full model block, so a config edit can never
    silently reuse a posterior fit under different settings."""
    base = dict(cutoff="2024-06-01", store=small_store, backend="advi",
                draws=80, seed=0, advi_iters=2000, cache_dir=tmp_path)
    _, m1 = cached_fit(**base)
    # Different likelihood -> miss (and is fit under the new likelihood).
    _, m_lik = cached_fit(**{**base, "likelihood": "bivariate_poisson"})
    # A widening-strength edit in the model config -> different key -> miss.
    cfg = copy.deepcopy(load_config())
    cfg["model"]["widening"]["strength"] = 0.9
    _, m_cfg = cached_fit(**{**base, "config": cfg})
    assert m1["cache_hit"] is False
    assert m_lik["cache_hit"] is False and m_lik["key"] != m1["key"]
    assert m_cfg["cache_hit"] is False and m_cfg["key"] != m1["key"]
