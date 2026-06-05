import numpy as np
import pandas as pd

from wcmodel.backtest.odds_ingest import OUTCOMES, _SYNTHETIC_KEY, synthetic_odds_sample
from wcmodel.live.decide import decide_live, LiveDecision


def _synth_sample():
    # CLEARLY NON-REAL synthetic event: generous Brazil entry, close drifts shorter
    # on Brazil (=> +CLV if Brazil is staked). Teams + a date that exist in small_store.
    return synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
        bookmaker="pinnacle", seed=0,
    )


def _snap(ts: str, prices, *, home="Brazil", away="Croatia",
          commence="2024-06-30T19:00:00Z", bookmaker="pinnacle") -> dict:
    """One CLEARLY-NON-REAL Odds-API snapshot ({timestamp, data:[...]}) at ``ts``.

    Same nested shape ``synthetic_odds_sample`` builds (synthetic marker on the
    nested snapshot too), so ``entry_close_prices`` propagates the non-real taint.
    """
    h, d, a = prices
    return {
        _SYNTHETIC_KEY: True,
        "timestamp": ts, "previous_timestamp": ts, "next_timestamp": ts,
        "data": [{
            "id": f"SYNTHETIC_{home}_{away}", "sport_key": "soccer_fifa_world_cup",
            "commence_time": commence, "home_team": home, "away_team": away,
            "bookmakers": [{
                "key": bookmaker, "last_update": ts,
                "markets": [{
                    "key": "h2h", "last_update": ts,
                    "outcomes": [
                        {"name": home, "price": h},
                        {"name": "Draw", "price": d},
                        {"name": away, "price": a},
                    ],
                }],
            }],
        }],
    }


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


def test_decide_live_never_prices_from_a_post_cutoff_snapshot(small_store, cfg):
    # ODDS-SIDE LEAKAGE GUARD. The entry that drives edge/staked-side/stake MUST be
    # the decision-time price (the latest snapshot <= cutoff), NEVER a > cutoff
    # (future / post-decision) price. Three snapshots for the book:
    #   T_old  = kickoff-9h  (price OLD, <= cutoff) — an earlier, superseded line
    #   T_A    = kickoff-6h  (price A,   <= cutoff) — THE decision-time price (latest <= cutoff)
    #   T_post = kickoff-1h  (price B,   >  cutoff) — a future price; must be unusable
    # cutoff = kickoff-3h. The decision must price/stake from A, never B (and never OLD,
    # which is not the latest <= cutoff). The close (latest <= kickoff = B) is recorded
    # for CLV but must not drive the decision.
    commence = "2024-06-30T19:00:00Z"
    kickoff = pd.Timestamp(commence)
    cutoff = (kickoff - pd.Timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_old = (kickoff - pd.Timedelta(hours=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_a = (kickoff - pd.Timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_post = (kickoff - pd.Timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    price_old = (4.00, 3.40, 2.10)
    price_a = (2.50, 3.40, 3.00)     # the decision-time (<= cutoff) entry
    price_b = (1.50, 4.00, 5.00)     # the post-cutoff future price — must NEVER be priced from
    a_map = dict(zip(OUTCOMES, price_a))
    b_map = dict(zip(OUTCOMES, price_b))

    sample = {
        _SYNTHETIC_KEY: True,
        "s_old": _snap(t_old, price_old, commence=commence),
        "s_a": _snap(t_a, price_a, commence=commence),
        "s_post": _snap(t_post, price_b, commence=commence),
    }
    d = decide_live(small_store, sample, cutoff=cutoff, config=cfg,
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})

    # The logged ENTRY is the decision-time price A (latest <= cutoff), never the
    # post-cutoff B (and never the older OLD line).
    assert d.entry_odds == a_map
    assert d.entry_odds != b_map
    # The edge/stake were priced off A: the de-vigged market_entry matches A's de-vig,
    # not B's. (Compare against the canonical de-vig of A and B.)
    from wcmodel.backtest.baselines import market_fair_1x2
    bt = cfg["backtest"]
    assert d.market_entry == market_fair_1x2(a_map, method=bt["devig_method"])
    assert d.market_entry != market_fair_1x2(b_map, method=bt["devig_method"])
    # The CLOSE (latest <= kickoff = the post-cutoff B) is still recorded for CLV ONLY —
    # it is a different price from the entry and did NOT drive the decision.
    assert d.close_odds == b_map
    assert d.close_odds != d.entry_odds


def test_decide_live_no_pre_cutoff_price_is_a_non_bet(small_store, cfg):
    # If the ONLY snapshots are > cutoff (no decision-time price exists for the book),
    # the decision is a COUNTED NON-BET (stake 0, a clear reason) — NOT a crash, and
    # NOT a future-priced bet off a post-cutoff snapshot.
    commence = "2024-06-30T19:00:00Z"
    kickoff = pd.Timestamp(commence)
    cutoff = (kickoff - pd.Timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Both snapshots are AFTER the cutoff (kickoff-2h and kickoff-1h > kickoff-5h).
    t1 = (kickoff - pd.Timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t2 = (kickoff - pd.Timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sample = {
        _SYNTHETIC_KEY: True,
        "s1": _snap(t1, (2.50, 3.40, 3.00), commence=commence),
        "s2": _snap(t2, (2.10, 3.50, 3.40), commence=commence),
    }
    d = decide_live(small_store, sample, cutoff=cutoff, config=cfg,
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert isinstance(d, LiveDecision)
    assert d.staked == ""           # no side staked
    assert d.stake == 0.0           # counted non-bet, not a future-priced bet
    assert d.non_bet_reason == "no_odds"
