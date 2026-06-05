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
from unittest import mock

import pytest

from wcmodel.config import load_config
from wcmodel.model.cache import cached_fit


class _FakePosterior:
    """Minimal stand-in for the meta-JSON write on a MISS (no real fit)."""

    def __init__(self):
        self.teams = ["Brazil", "Argentina"]
        self.likelihood = "dixon_coles"
        self.provisional_teams = set()


def test_cache_key_uses_passed_config_elo_not_global(small_store, tmp_path):
    """D6 (Phase-4 Task 0): the key must reference the ACTUAL elo config the
    posterior was computed under -- the PASSED ``cfg["elo"]`` -- NOT the global
    ``load_config()["elo"]``.

    WHY (inverted from the pre-D6 contract): ``compute_elo_history`` /
    ``count_volatility_arm`` are now config-threaded (Phase-4 Task 0), so a
    caller-supplied ``config`` actually drives the posterior's elo-dependent
    inputs (the panel's ``provisional`` flags + the prediction provisional set).
    The value that determines the posterior is therefore ``cfg["elo"]``, and the
    key must track THAT -- so a custom ``cfg.elo`` (a lockbox K/T sweep)
    invalidates the cache correctly and can never record an elo the computation
    did not use.

    The fit / netCDF write / feature hash are stubbed so this is FAST and
    isolates the elo-param contribution to the key (no sampling, and the
    feature_hash is held constant so the only thing under test is the explicit
    ``elo`` key param). The GLOBAL ``load_config`` is held FIXED across both
    calls; only the PASSED config's elo differs -> a different key.
    """
    base_cfg = load_config()
    cfg_lo = copy.deepcopy(base_cfg)
    cfg_lo["elo"]["provisional_volatility_threshold"] = 10.0
    cfg_hi = copy.deepcopy(base_cfg)
    cfg_hi["elo"]["provisional_volatility_threshold"] = 25.0

    kw = dict(cutoff="2024-06-01", store=small_store, backend="advi",
              draws=80, seed=0, advi_iters=2000, cache_dir=tmp_path)

    with mock.patch("wcmodel.model.cache._feature_hash", return_value="ff" * 8), \
         mock.patch("wcmodel.model.cache._git_commit", return_value="deadbeef"), \
         mock.patch("wcmodel.model.cache._posterior_to_netcdf"), \
         mock.patch("wcmodel.model.cache.fit", return_value=_FakePosterior()), \
         mock.patch("wcmodel.model.cache.load_config", return_value=copy.deepcopy(base_cfg)):
        _, m_lo = cached_fit(**{**kw, "config": cfg_lo})
        _, m_hi = cached_fit(**{**kw, "config": cfg_hi})

    # A DIFFERENT passed-config elo -> a DIFFERENT key (the key tracks the elo
    # that actually drove the posterior). This is the inverted D6 contract.
    assert m_lo["key"] != m_hi["key"]


def test_cache_key_tracks_passed_config_elo_block(small_store, tmp_path):
    """D6 complement: a passed ``config`` whose ONLY difference is its ``elo``
    block DOES change the key -- because elo is now keyed from the PASSED config
    (Phase-4 Task 0; ``compute_elo_history``/``count_volatility_arm`` are
    config-threaded), so a custom ``cfg.elo`` correctly invalidates the cache.

    The global ``load_config`` is held FIXED across both calls; only the passed
    config's elo differs. Same stubs as above so the feature_hash cannot smuggle
    the elo difference into the key -- the change rides ONLY the explicit ``elo``
    key param now sourced from the passed cfg.
    """
    base_cfg = load_config()
    cfg_a = copy.deepcopy(base_cfg)
    cfg_b = copy.deepcopy(base_cfg)
    cfg_b["elo"]["provisional_volatility_threshold"] = 99.0  # only the elo block differs

    kw = dict(cutoff="2024-06-01", store=small_store, backend="advi",
              draws=80, seed=0, advi_iters=2000, cache_dir=tmp_path)

    with mock.patch("wcmodel.model.cache._feature_hash", return_value="ff" * 8), \
         mock.patch("wcmodel.model.cache._git_commit", return_value="deadbeef"), \
         mock.patch("wcmodel.model.cache._posterior_to_netcdf"), \
         mock.patch("wcmodel.model.cache.fit", return_value=_FakePosterior()), \
         mock.patch("wcmodel.model.cache.load_config", return_value=copy.deepcopy(base_cfg)):
        _, m_a = cached_fit(**{**kw, "config": cfg_a})
        _, m_b = cached_fit(**{**kw, "config": cfg_b})

    # Passed-config elo NOW enters the key (D6: elo keyed from the passed cfg).
    assert m_a["key"] != m_b["key"]


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
