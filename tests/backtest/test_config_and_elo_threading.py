import copy

import numpy as np
import pandas as pd

from wcmodel.config import load_config


def test_backtest_config_block_present_and_typed():
    bt = load_config()["backtest"]
    assert bt["odds_start"] == "2020-06-06"
    assert bt["edge_threshold"] == 0.02
    assert bt["kelly_fraction"] == 0.25
    assert bt["preregistered_config_count"] == 9
    assert bt["lockbox_fraction"] == 0.18
    assert bt["permutation_shuffles"] == 200
    assert bt["foresight_red"]["roi"] == 0.10
    assert bt["foresight_red"]["beat_close_rate"] == 0.58
    assert bt["foresight_red"]["avg_clv"] == 0.02
    assert bt["commission"]["pinnacle"] == 0.0 and bt["commission"]["betfair"] == 0.02
    assert bt["devig_method"] == "shin"


def _two_match_frame():
    # Two played matches, distinct dates, so a K change moves the post rating.
    return pd.DataFrame([
        {"match_id": "m1", "date": pd.Timestamp("2023-01-01"), "home_team": "A",
         "away_team": "B", "home_score": 3, "away_score": 0, "neutral": False,
         "match_type": "wc_finals"},
        {"match_id": "m2", "date": pd.Timestamp("2023-02-01"), "home_team": "A",
         "away_team": "B", "home_score": 1, "away_score": 0, "neutral": False,
         "match_type": "wc_finals"},
    ])


def test_compute_elo_history_threads_config_k():
    from wcmodel.data.elo import compute_elo_history
    frame = _two_match_frame()
    base = compute_elo_history(frame)                      # global config (k_base 40)
    cfg = copy.deepcopy(load_config())
    cfg["elo"]["k_base"] = 80.0                            # double K via THREADED config
    bumped = compute_elo_history(frame, config=cfg)
    # A's rating_pre at its SECOND match must differ once K doubles (config really threaded).
    a2_base = base[(base["team"] == "A") & (base["match_id"] == "m2")]["rating_pre"].iloc[0]
    a2_bump = bumped[(bumped["team"] == "A") & (bumped["match_id"] == "m2")]["rating_pre"].iloc[0]
    assert not np.isclose(a2_base, a2_bump)


def test_elo_1x2_baseline_threads_config_draw_base():
    from wcmodel.data.elo import elo_1x2_baseline
    base = elo_1x2_baseline(1600.0, 1500.0, neutral=True)
    cfg = copy.deepcopy(load_config())
    cfg["baseline"]["draw_base"] = 0.10                    # shrink draw mass via threaded config
    bumped = elo_1x2_baseline(1600.0, 1500.0, neutral=True, config=cfg)
    assert bumped["draw"] < base["draw"]


def test_count_volatility_arm_threads_config(small_store):
    from wcmodel.model.volatility_diagnostic import count_volatility_arm
    cfg = copy.deepcopy(load_config())
    cfg["elo"]["provisional_volatility_threshold"] = 0.0   # everything trips the volatility arm
    out = count_volatility_arm(small_store, "2024-06-01", ["Brazil", "France"], config=cfg)
    # With T=0 every team with >= provisional_games and any volatility trips the volatility arm.
    assert out["volatility_flag"].any()


def test_posterior_cache_key_uses_threaded_elo(tmp_path, small_store):
    """Stale-serve guard: a caller passing a custom cfg['elo'] must yield a DIFFERENT
    cache key (the key must reflect the elo that ACTUALLY determined the posterior —
    the threaded cfg, not the global disk value). RED before the D6 key switch."""
    from wcmodel.model.cache import _cache_key_params
    base_cfg = load_config()
    bumped_cfg = copy.deepcopy(base_cfg)
    bumped_cfg["elo"]["k_base"] = 999.0
    p_base = _cache_key_params(cutoff="2024-06-01", store=small_store, backend="advi",
                               draws=10, seed=0, advi_iters=50, likelihood="dixon_coles",
                               tune=10, cfg=base_cfg)
    p_bump = _cache_key_params(cutoff="2024-06-01", store=small_store, backend="advi",
                               draws=10, seed=0, advi_iters=50, likelihood="dixon_coles",
                               tune=10, cfg=bumped_cfg)
    assert p_base["elo"] != p_bump["elo"]
    assert p_base["elo"] == base_cfg["elo"]                # keyed from the PASSED cfg, not disk


def test_cached_fit_posterior_actually_uses_threaded_elo(tmp_path, small_store):
    """Stale-serve TEETH for the PROVISIONAL-SET channel specifically: a bumped
    cfg['elo'] must change the ACTUAL fit output (the provisional set, driven by
    scoreline.fit -> count_volatility_arm, and/or a prediction), not merely the
    cache key. Before the call-site threading this was False (key changed,
    computation did not) — the exact P2-T8 stale-serve class on the posterior
    cache key.

    SCOPE / what this test does NOT see: the scoreline model is Elo-independent,
    so a revert of the OTHER channel — features.build -> compute_elo_history(
    config=cfg) -> the panel's Elo feature column -> _feature_hash — would leave
    predictions AND the provisional set unchanged here, so this guard would still
    PASS while the feature-hash channel of the cache key silently stopped
    reflecting cfg['elo']. That feature-hash channel is covered directly by
    test_feature_hash_reflects_threaded_elo."""
    import copy
    from wcmodel.config import load_config
    from wcmodel.model.scoreline import fit
    base_cfg = load_config()
    bumped = copy.deepcopy(base_cfg)
    bumped["elo"]["k_base"] = 999.0
    bumped["elo"]["provisional_volatility_threshold"] = 0.0   # force a provisional-set change
    kw = dict(backend="advi", draws=60, seed=0, advi_iters=1500)
    p_base = fit("2024-06-01", small_store, config=base_cfg, **kw)
    p_bump = fit("2024-06-01", small_store, config=bumped, **kw)
    # The provisional set (driven by count_volatility_arm's elo config) must differ,
    # OR a representative prediction must differ — i.e. cfg['elo'] reaches the computation.
    differs = (p_base.provisional_teams != p_bump.provisional_teams) or (
        p_base.predict_1x2("Brazil", "Argentina") != p_bump.predict_1x2("Brazil", "Argentina")
    )
    assert differs, (
        "cfg['elo'] changed the cache key but NOT the actual fit -> stale serve. "
        "The fit-path call sites are not threading config into the Elo computation."
    )


def test_feature_hash_reflects_threaded_elo(small_store):
    """Teeth for the features.build -> compute_elo_history -> _feature_hash channel,
    which the prediction-based guard test CANNOT see (the scoreline model is
    Elo-independent, so a reverted features.build elo-threading leaves predictions +
    the provisional set unchanged, yet would make _feature_hash — part of the
    posterior cache key — stop reflecting cfg['elo']). A bumped cfg['elo'] must change
    the panel's Elo feature column, hence _feature_hash."""
    import copy
    from wcmodel.config import load_config
    from wcmodel.model.cache import _feature_hash
    base = load_config()
    bumped = copy.deepcopy(base)
    bumped["elo"]["k_base"] = 999.0
    h_base = _feature_hash("2024-06-01", small_store, base)
    h_bump = _feature_hash("2024-06-01", small_store, bumped)
    assert h_base != h_bump, (
        "features.build is not threading cfg['elo'] into compute_elo_history -> the "
        "Elo feature column (hence _feature_hash, hence the cache key) is blind to a "
        "custom cfg['elo'] -> stale serve on the feature-hash channel."
    )
