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

import pandas as pd
import pytest

from wcmodel.config import load_config
from wcmodel.data import features
from wcmodel.data.features import _build_cache_key, build, build_cached
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.data.cache import content_key
from wcmodel.model.cache import _cache_key_params, _feature_hash, cached_fit


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


def test_cache_key_tracks_strength_prior_enabled(small_store, tmp_path):
    """Task 4 Step 4: ``model.strength_prior`` is part of the posterior cache key,
    so toggling ``enabled`` (which changes the att/def prior MEAN -> a different
    posterior) yields a DIFFERENT key — never a stale serve of the wrong-anchor
    fit. ``_cache_key_params`` hashes ``cfg["model"]`` whole, and ``strength_prior``
    lives under ``model``, so the toggle rides into the key directly.

    Uses ``_cache_key_params`` + ``content_key`` directly (no fit). ``_feature_hash``
    and ``_git_commit`` are stubbed constant so the ONLY difference between the two
    keys is ``strength_prior.enabled`` — proving THAT is what moves the key (the
    elo_z VALUES additionally ride via the panel's feature_hash in production, but
    here we isolate the config toggle)."""
    base_cfg = load_config()
    cfg_off = copy.deepcopy(base_cfg)
    cfg_off["model"]["strength_prior"]["enabled"] = False
    cfg_on = copy.deepcopy(base_cfg)
    cfg_on["model"]["strength_prior"]["enabled"] = True

    kw = dict(cutoff="2024-06-01", store=small_store, backend="advi", draws=80,
              seed=0, advi_iters=2000, likelihood="dixon_coles", tune=1000)

    with mock.patch("wcmodel.model.cache._feature_hash", return_value="ff" * 8), \
         mock.patch("wcmodel.model.cache._git_commit", return_value="deadbeef"):
        key_off = content_key("posterior", _cache_key_params(**{**kw, "cfg": cfg_off}))
        key_on = content_key("posterior", _cache_key_params(**{**kw, "cfg": cfg_on}))

    assert key_off != key_on, (
        "strength_prior.enabled does not change the posterior cache key -> a fit "
        "with the anchor ON could be served from an OFF (or wrong-k) cache entry"
    )


def test_cache_key_tier_weights_off_states_match_baseline(small_store, tmp_path):
    """P2c: the OFF states of ``model.likelihood_tier_weights`` must NOT invalidate
    an existing cached posterior. Three configs must share ONE key:
      * the block ABSENT entirely (the pre-P2c baseline),
      * an explicit ALL-1.0 block, and
      * an all-1.0 block listing only SOME tiers (still all 1.0).
    So w=1.0 in the sweep is a cache HIT of the existing production posterior.

    ``_cache_key_params`` hashes ``cfg["model"]`` whole, so a NAIVE add of an
    all-1.0 block WOULD change the key. The key builder NORMALIZES the tier-weight
    block — dropping it when absent/all-1.0 — so the off states are key-identical
    to the baseline. Stubs hold feature_hash/git constant to isolate the model
    block's contribution."""
    base_cfg = load_config()
    cfg_absent = copy.deepcopy(base_cfg)
    cfg_absent["model"].pop("likelihood_tier_weights", None)
    cfg_ones = copy.deepcopy(cfg_absent)
    cfg_ones["model"]["likelihood_tier_weights"] = {
        "friendly": 1.0, "wc_qualifier": 1.0, "wc_finals": 1.0,
        "continental_championship": 1.0, "continental_qualifier": 1.0,
        "nations_league": 1.0, "other": 1.0,
    }
    cfg_ones_partial = copy.deepcopy(cfg_absent)
    cfg_ones_partial["model"]["likelihood_tier_weights"] = {"friendly": 1.0}

    kw = dict(cutoff="2024-06-01", store=small_store, backend="advi", draws=80,
              seed=0, advi_iters=2000, likelihood="dixon_coles", tune=1000)

    with mock.patch("wcmodel.model.cache._feature_hash", return_value="ff" * 8), \
         mock.patch("wcmodel.model.cache._git_commit", return_value="deadbeef"):
        k_absent = content_key("posterior", _cache_key_params(**{**kw, "cfg": cfg_absent}))
        k_ones = content_key("posterior", _cache_key_params(**{**kw, "cfg": cfg_ones}))
        k_ones_partial = content_key(
            "posterior", _cache_key_params(**{**kw, "cfg": cfg_ones_partial}))

    assert k_absent == k_ones, (
        "an explicit all-1.0 tier-weight block changed the cache key -> it would "
        "force a needless refit and orphan the existing production posterior")
    assert k_absent == k_ones_partial, "a partial all-1.0 block also must not move the key"


def test_cache_key_tracks_nondefault_tier_weights(small_store, tmp_path):
    """P2c complement: a NON-default tier-weight block (a value != 1.0) DOES change
    the key — it changes the likelihood weights -> a different posterior, never a
    stale serve. Two different non-default blocks also differ from each other."""
    base_cfg = load_config()
    cfg_off = copy.deepcopy(base_cfg)
    cfg_off["model"].pop("likelihood_tier_weights", None)
    cfg_half = copy.deepcopy(cfg_off)
    cfg_half["model"]["likelihood_tier_weights"] = {"friendly": 0.5}
    cfg_quarter = copy.deepcopy(cfg_off)
    cfg_quarter["model"]["likelihood_tier_weights"] = {"friendly": 0.25}

    kw = dict(cutoff="2024-06-01", store=small_store, backend="advi", draws=80,
              seed=0, advi_iters=2000, likelihood="dixon_coles", tune=1000)

    with mock.patch("wcmodel.model.cache._feature_hash", return_value="ff" * 8), \
         mock.patch("wcmodel.model.cache._git_commit", return_value="deadbeef"):
        k_off = content_key("posterior", _cache_key_params(**{**kw, "cfg": cfg_off}))
        k_half = content_key("posterior", _cache_key_params(**{**kw, "cfg": cfg_half}))
        k_quarter = content_key("posterior", _cache_key_params(**{**kw, "cfg": cfg_quarter}))

    assert k_off != k_half, (
        "a non-default tier-weight block does not change the key -> a down-weighted "
        "fit could be served from the baseline cache entry")
    assert k_half != k_quarter, "two distinct non-default tier blocks must yield distinct keys"


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


def test_feature_hash_is_row_order_invariant(small_store):
    """The posterior cache key embeds ``_feature_hash``; it must depend ONLY on the
    < cutoff panel CONTENT, never on the incidental read/build row order.

    This test BITES (the prior version passed with OR without the stabilizer
    because the fixture's panel order is already stable): we DIRECTLY feed the
    SAME panel back in two DIFFERENT shuffled row orders by patching
    ``features.build`` (the function ``_feature_hash`` routes through), and assert
    the hash is identical. Without ``_feature_hash``'s ``sort_values("match_id")``
    stabilizer this MUST fail — proven RED by deleting that line — so it pins the
    fix it exists to protect. ``cache_dir`` is None so ``build_cached`` calls
    ``build`` directly (no parquet round-trip that would re-canonicalize order)."""
    cfg = load_config()
    cutoff = "2025-03-01"
    panel = build(cutoff, small_store, cfg)
    assert "match_id" in panel.columns and len(panel) > 2

    def _hash_with_shuffle(k):
        shuffled = panel.sample(frac=1, random_state=k).reset_index(drop=True)
        with mock.patch("wcmodel.data.features.build", return_value=shuffled):
            return _feature_hash(cutoff, small_store, cfg)

    # Two DIFFERENT shuffles of the IDENTICAL panel content must hash identically.
    assert _hash_with_shuffle(1) == _hash_with_shuffle(7), (
        "_feature_hash must be invariant to panel row order (sort-by-match_id)")


def test_build_cache_key_is_read_order_invariant(small_store):
    """``_build_cache_key`` must depend ONLY on the < cutoff result CONTENT, never
    on the store's incidental ``store.read`` row order.

    ``store.read`` resolves the point-in-time slice through a DuckDB window whose
    OUTPUT order is process-unstable, so the key MUST sort by ``match_id`` before
    hashing. We patch ``store.read`` to return the SAME rows shuffled two ways and
    assert the key matches — removing the ``sort_values("match_id")`` in
    ``_build_cache_key`` makes this FAIL."""
    cfg = load_config()
    cutoff = "2025-03-01"
    real = small_store.read("results", cutoff=cutoff)
    assert len(real) > 2

    real_read = small_store.read

    def _key_with_shuffle(k):
        shuffled = real.sample(frac=1, random_state=k).reset_index(drop=True)

        def _fake_read(name, *, cutoff):
            if name == "results":
                return shuffled.copy()
            return real_read(name, cutoff=cutoff)

        with mock.patch.object(small_store, "read", side_effect=_fake_read):
            return _build_cache_key(cutoff, small_store, cfg)

    assert _key_with_shuffle(2) == _key_with_shuffle(9), (
        "_build_cache_key must be invariant to store.read row order")


def test_build_cached_matches_build_and_hits_on_second_call(small_store, tmp_path):
    """``features.build_cached`` (the panel-cache speed fix) must (a) return a panel
    CONTENT-identical to a fresh ``features.build``, and (b) read from disk on the
    2nd call (a HIT) instead of recomputing the per-cutoff Elo."""
    cfg = load_config()
    cutoff = "2025-03-01"
    direct = features.build(cutoff, small_store, cfg)
    miss = features.build_cached(cutoff, small_store, cfg, cache_dir=tmp_path)
    # Exactly one panel parquet was written (the key is stable).
    files = list(tmp_path.glob("featpanel-*.parquet"))
    assert len(files) == 1
    # A 2nd call returns the SAME panel from disk.
    hit = features.build_cached(cutoff, small_store, cfg, cache_dir=tmp_path)
    assert len(list(tmp_path.glob("featpanel-*.parquet"))) == 1   # no new file
    # Content-identical to the fresh build (sorted + dtype-robust compare).
    def _canon(df):
        return df.sort_values("match_id").reset_index(drop=True) if "match_id" in df else df
    a, b, c = _canon(direct), _canon(miss), _canon(hit)
    assert list(a.columns) == list(b.columns) == list(c.columns)
    assert a.shape == b.shape == c.shape
    assert (a["match_id"].values == c["match_id"].values).all()
    # VALUE equality on the columns the model actually consumes (via
    # ``to_match_panel``): elo_pre / decay_weight(->weight) / provisional /
    # neutral / home_score / away_score / match_type, plus the date the decay is
    # derived from. A bare column/shape/match_id check (the pre-fix assertion) let
    # a value-CORRUPTING serialization change through; this catches it.
    model_cols = ["match_id", "date", "elo_pre", "decay_weight", "provisional",
                  "neutral", "home_score", "away_score", "match_type"]
    pd.testing.assert_frame_equal(a[model_cols], b[model_cols], check_dtype=False)
    pd.testing.assert_frame_equal(a[model_cols], c[model_cols], check_dtype=False)


def test_panel_cache_key_folds_cutoff_no_cross_day_collision(small_store, tmp_path):
    """BLOCKING regression: ``_build_cache_key`` MUST fold the as-of ``cutoff`` so
    two DIFFERENT-day cutoffs that share the SAME ``< cutoff_day`` result set do
    NOT collide on the key.

    ``build`` derives ``age_days = (cutoff - date)`` -> ``decay_weight`` /
    ``in_feature_window`` from the cutoff itself, NOT from the ``< cutoff_day``
    slice. On ``small_store`` cutoffs 2024-06-10 (A) and 2024-06-19 (B) straddle a
    rest-day gap — no match is played between them (the prior match is 2024-06-05,
    the next is 2024-06-20) — so both see the IDENTICAL ``< cutoff_day`` results,
    but ``build`` assigns DIFFERENT decay weights (9 days apart). The pre-fix key
    omitted the cutoff, so A and B collided and ``build_cached(B)`` served A's
    wrongly-weighted panel — a mild look-ahead (the model fits on the wrong
    weighting). Asserts (a) the keys differ, and (b) ``build_cached(B)``'s
    ``decay_weight`` equals ``build(B)``'s (NOT ``build(A)``'s)."""
    cfg = load_config()
    A, B = "2024-06-10", "2024-06-19"

    # (precondition) A and B genuinely share the < cutoff_day result set — no
    # match played in the [A, B) gap, so only the cutoff (decay) differs.
    from wcmodel.data.features import valid_played_results
    res = small_store.read("results", cutoff=B)
    res["date"] = pd.to_datetime(res["date"])
    played = valid_played_results(res)
    in_gap = played[(played["date"] >= pd.Timestamp(A))
                    & (played["date"] < pd.Timestamp(B))]
    assert in_gap.empty, "fixture changed: a match now falls in the [A,B) gap"

    # (a) The keys must DIFFER now that the cutoff is folded in.
    kA = _build_cache_key(A, small_store, cfg)
    kB = _build_cache_key(B, small_store, cfg)
    assert kA != kB, "cross-day cutoffs sharing a < cutoff_day slice must NOT collide"

    # (b) build_cached(B) must serve B's panel (B's decay weights), not A's. Seed
    #     the cache with A FIRST (the collision would have it served for B).
    def _canon(df):
        return df.sort_values("match_id").reset_index(drop=True)
    pA = _canon(build_cached(A, small_store, cfg, cache_dir=tmp_path))
    pB_cached = _canon(build_cached(B, small_store, cfg, cache_dir=tmp_path))
    pB_fresh = _canon(build(B, small_store, cfg))
    pd.testing.assert_series_equal(pB_cached["decay_weight"], pB_fresh["decay_weight"])
    assert not pB_cached["decay_weight"].equals(pA["decay_weight"]), (
        "build_cached(B) served A's decay weights — the collision fired")


def test_panel_cache_key_folds_schema_version(small_store):
    """Important: bumping ``PANEL_SCHEMA_VERSION`` must change the panel-cache key.

    The key hashes the ``< cutoff`` inputs + config but NOT the code that builds
    the panel, so a future ``build`` change that alters panel CONTENT (with no
    elo/windows/data change and no commit) would serve a STALE panel.
    ``PANEL_SCHEMA_VERSION`` is the manual invalidation lever — flipping it must
    flip the key so a maintainer can force a clean miss."""
    cfg = load_config()
    cutoff = "2025-03-01"
    k0 = _build_cache_key(cutoff, small_store, cfg)
    orig = features.PANEL_SCHEMA_VERSION
    try:
        features.PANEL_SCHEMA_VERSION = orig + "-bumped"
        k1 = _build_cache_key(cutoff, small_store, cfg)
    finally:
        features.PANEL_SCHEMA_VERSION = orig
    assert k0 != k1, "a PANEL_SCHEMA_VERSION bump must invalidate the panel cache"


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
