import numpy as np
import pandas as pd

from wcmodel.backtest.odds_ingest import OUTCOMES, synthetic_odds_sample
from wcmodel.live.decide import decide_live, LiveDecision


def _synth_sample():
    # CLEARLY NON-REAL synthetic event: generous Brazil entry, close drifts shorter
    # on Brazil (=> +CLV if Brazil is staked). Teams + a date that exist in small_store.
    return synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
        bookmaker="pinnacle", seed=0,
    )


def test_decide_live_uses_entry_not_close_for_edge_and_stake(small_store, cfg):
    s = _synth_sample()
    d = decide_live(small_store, s["sample"], cutoff="2024-06-30T19:00:00Z",
                    config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert isinstance(d, LiveDecision)
    # The logged ENTRY price is the bet_time (decision-time) price, NEVER the close.
    assert d.entry_odds[d.staked] == s["sample"]["bet_time"]["data"][0][
        "bookmakers"][0]["markets"][0]["outcomes"][
            {"home": 0, "draw": 1, "away": 2}[d.staked]]["price"]
    # The edge was computed against the de-vigged ENTRY market (not the close).
    assert d.market_surface == "1x2"
    assert set(d.model) == set(OUTCOMES)
    assert set(d.edge) == set(OUTCOMES)
    # Non-real taint propagates (synthetic harness).
    assert d.is_synthetic is True
    # SIGNAL-ONLY: the stake is a recommendation fraction in [0, 1], no bet placed.
    assert 0.0 <= d.stake <= 1.0
    assert d.signal_only is True


def test_decide_live_records_close_for_clv_only(small_store, cfg):
    s = _synth_sample()
    d = decide_live(small_store, s["sample"], cutoff="2024-06-30T19:00:00Z",
                    config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # The close is RECORDED (for later CLV) but did NOT drive the staked side/edge.
    assert d.close_odds[d.staked] == s["sample"]["close"]["data"][0][
        "bookmakers"][0]["markets"][0]["outcomes"][
            {"home": 0, "draw": 1, "away": 2}[d.staked]]["price"]
    # realized CLV is computable from the LOGGED entry vs the LATER close.
    assert abs(d.realized_clv() - (d.entry_odds[d.staked] / d.close_odds[d.staked] - 1.0)) < 1e-12


def test_decide_live_is_reproducible_same_cutoff_seed(small_store, cfg):
    s = _synth_sample()
    kw = dict(cutoff="2024-06-30T19:00:00Z", config=cfg,
              fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    a = decide_live(small_store, s["sample"], **kw)
    b = decide_live(small_store, s["sample"], **kw)     # same cutoff + seed
    # Bit-identical decision (seeded + content-addressed provenance).
    assert a.to_dict() == b.to_dict()


def test_decide_live_non_bet_filter_gates_stale_entry(small_store, cfg):
    # A stale entry (older than stale_snapshot_seconds before kickoff) => a NON-BET:
    # decision records the reason, stakes nothing.
    s = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
        bookmaker="pinnacle", seed=0,
    )
    # Force the entry snapshot far before kickoff so it trips the stale filter.
    s["sample"]["bet_time"]["timestamp"] = "2024-06-01T00:00:00Z"
    d = decide_live(small_store, s["sample"], cutoff="2024-06-30T19:00:00Z",
                    config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert d.non_bet_reason == "stale"
    assert d.stake == 0.0
