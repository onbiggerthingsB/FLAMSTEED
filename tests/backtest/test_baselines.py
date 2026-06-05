import numpy as np

from wcmodel.backtest.baselines import (
    edge_vector, model_fair_1x2, market_fair_1x2, elo_baseline_1x2, rps,
)
from wcmodel.backtest.odds_ingest import OUTCOMES


def test_edge_is_model_minus_devigged_market_per_outcome():
    model = {"home": 0.55, "draw": 0.25, "away": 0.20}
    market = {"home": 0.50, "draw": 0.27, "away": 0.23}
    e = edge_vector(model, market)
    assert abs(e["home"] - 0.05) < 1e-12
    assert abs(e["away"] - (-0.03)) < 1e-12
    assert set(e) == set(OUTCOMES)


def test_market_fair_devigs_the_close():
    # market-only baseline = the de-vigged close (Shin), ordered by OUTCOMES.
    close = {"home": 1.57, "draw": 4.20, "away": 6.50}
    m = market_fair_1x2(close, method="shin")
    assert abs(sum(m.values()) - 1.0) < 1e-9
    assert m["home"] > m["draw"] > m["away"]


def test_elo_baseline_uses_computed_ratings(small_store, cfg):
    from wcmodel.model.volatility_diagnostic import count_volatility_arm  # noqa: F401
    # Pull the as-of-cutoff ratings the SAME way the engine will (Task 5 helper),
    # but here just check elo_baseline_1x2 maps ratings -> a valid 1X2 dict.
    p = elo_baseline_1x2(rating_home=1600.0, rating_away=1500.0, neutral=True, config=cfg)
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert set(p) == set(OUTCOMES)


def test_model_fair_1x2_reads_predict_1x2(small_store):
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=60, seed=0, advi_iters=1500)
    p = model_fair_1x2(post, home="Brazil", away="Argentina", neutral=True)
    assert set(p) == set(OUTCOMES)
    assert abs(sum(p.values()) - 1.0) < 1e-6


def test_rps_matches_manual_three_way():
    # Perfect forecast -> RPS 0; flat forecast on a home win -> known value.
    assert rps({"home": 1.0, "draw": 0.0, "away": 0.0}, "home") == 0.0
    flat = rps({"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}, "home")
    # cumulative: (1/3-1)^2 + (2/3-1)^2 = 4/9 + 1/9 = 5/9
    assert abs(flat - 5 / 9) < 1e-12


def test_baselines_rps_equals_devig_select_rps():
    # DRY lock: the public dict-keyed ``rps`` and the private list-indexed
    # ``devig_select._rps`` are KEPT separate (consolidating would close a
    # baselines<->devig_select import cycle) but MUST stay numerically identical.
    # If either drifts, this fails — the public copy can never silently diverge.
    from wcmodel.backtest.devig_select import _rps as devig_rps

    rng = np.random.default_rng(0)
    for _ in range(200):
        v = rng.dirichlet([1.0, 1.0, 1.0])  # a valid 1X2 distribution
        probs_dict = dict(zip(OUTCOMES, v))
        probs_list = [v[i] for i in range(len(OUTCOMES))]
        for outcome in OUTCOMES:
            assert abs(rps(probs_dict, outcome) - devig_rps(probs_list, outcome)) < 1e-15
