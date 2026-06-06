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


def test_decide_live_skips_snapshot_missing_the_book_uses_earlier_priced_one(small_store, cfg):
    # BOOK-AWARE DECISION-TIME ENTRY. The decision-time entry is the latest snapshot
    # <= cutoff THAT CONTAINS the configured book — NOT merely the latest <= cutoff
    # snapshot (which might carry only some OTHER book). Two <= cutoff snapshots:
    #   T_A    = kickoff-6h  has `pinnacle` (price A)            — the valid book price
    #   T_late = kickoff-4h  has ONLY `betfair`, NO `pinnacle`   — still <= cutoff
    # cutoff = kickoff-3h (so BOTH are <= cutoff; T_late is the latest <= cutoff).
    # The decision must price/stake from A (latest <= cutoff snapshot that HAS pinnacle),
    # NOT crash on T_late's missing pinnacle and NOT let T_late block A.
    commence = "2024-06-30T19:00:00Z"
    kickoff = pd.Timestamp(commence)
    cutoff = (kickoff - pd.Timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_a = (kickoff - pd.Timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_late = (kickoff - pd.Timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_close = (kickoff - pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    price_a = (2.50, 3.40, 3.00)     # the pinnacle decision-time entry (latest <= cutoff WITH pinnacle)
    price_late = (1.50, 4.00, 5.00)  # betfair-only later snapshot; lacks pinnacle entirely
    price_close = (2.10, 3.50, 3.40)  # pinnacle close (latest <= kickoff; CLV only)
    a_map = dict(zip(OUTCOMES, price_a))

    sample = {
        _SYNTHETIC_KEY: True,
        "s_a": _snap(t_a, price_a, commence=commence, bookmaker="pinnacle"),
        # Latest <= cutoff snapshot, but it only carries betfair — pinnacle is absent.
        # The buggy _decision_time_entry picks THIS (latest <= cutoff) and crashes on
        # the missing pinnacle; the fix skips it and falls back to the pinnacle s_a.
        "s_late": _snap(t_late, price_late, commence=commence, bookmaker="betfair"),
        # A pinnacle CLOSE (latest <= kickoff, > cutoff): the kickoff-based
        # entry_close_prices close leg, recorded for CLV only — never the entry.
        "s_close": _snap(t_close, price_close, commence=commence, bookmaker="pinnacle"),
    }
    d = decide_live(small_store, sample, cutoff=cutoff, config=cfg,
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})

    # The logged ENTRY is the pinnacle price A (latest <= cutoff WITH the book), never
    # a crash and never blocked by the later book-less snapshot.
    assert d.entry_odds == a_map
    # The edge/stake were priced off A's de-vig (the snapshot that HAS pinnacle).
    from wcmodel.backtest.baselines import market_fair_1x2
    bt = cfg["backtest"]
    assert d.market_entry == market_fair_1x2(a_map, method=bt["devig_method"])


def test_decide_live_missing_earliest_book_never_prices_from_close(small_store, cfg):
    # FOCAL CONSTRUCTED MISS (the close-as-entry leak). When the EARLIEST <= kickoff
    # snapshot LACKS the configured book but LATER (mid + close) snapshots HAVE it,
    # `entry_close_prices` raises on its earliest-entry leg (book absent from the
    # earliest <= kickoff snapshot) and `decide_live` falls back to close_ts=None.
    # A close_ts=None makes the close EXCLUSION in `_decision_time_entry` inert (no
    # snapshot timestamp equals None), so with `cutoff >= close_ts` the CLOSE snapshot
    # becomes the latest <= cutoff book-present candidate and is (wrongly) selected as
    # the entry — pricing edge/staked-side/stake off POST-DECISION info (a leak).
    #
    # The FIX derives close_ts BOOK-AWARE and INDEPENDENTLY of the crashing earliest leg
    # (latest <= kickoff snapshot WITH the book), so the close is ALWAYS excluded from the
    # entry candidates. The logged entry must be the MID (latest <= cutoff WITH the book,
    # close-excluded), NEVER the close.
    commence = "2024-06-30T19:00:00Z"
    kickoff = pd.Timestamp(commence)
    # cutoff is AFTER the close timestamp (the trap: cutoff >= close_ts) so the close,
    # if not excluded, is the latest <= cutoff book-present snapshot.
    t_early = (kickoff - pd.Timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")  # betfair-only, EARLIEST <= KO
    t_mid = (kickoff - pd.Timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")     # pinnacle, the decision-time price
    t_close = (kickoff - pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")  # pinnacle, the CLOSE (post-decision)
    cutoff = (kickoff - pd.Timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")   # cutoff >= close_ts
    price_early = (9.99, 9.99, 9.99)  # betfair-only earliest snapshot (no pinnacle)
    price_mid = (2.30, 3.45, 3.20)    # pinnacle decision-time entry (the MID)
    price_close = (2.10, 3.50, 3.40)  # pinnacle CLOSE — must NEVER become the entry
    mid_map = dict(zip(OUTCOMES, price_mid))
    close_map = dict(zip(OUTCOMES, price_close))

    sample = {
        _SYNTHETIC_KEY: True,
        # EARLIEST <= kickoff snapshot carries ONLY betfair — pinnacle absent here makes
        # entry_close_prices' earliest-entry leg raise (the trigger for the close_ts=None fallback).
        "early": _snap(t_early, price_early, commence=commence, bookmaker="betfair"),
        "mid": _snap(t_mid, price_mid, commence=commence, bookmaker="pinnacle"),
        "close": _snap(t_close, price_close, commence=commence, bookmaker="pinnacle"),
    }
    d = decide_live(small_store, sample, cutoff=cutoff, config=cfg,
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})

    # The logged ENTRY is the MID (decision-time <= cutoff, book-aware, close-excluded),
    # NEVER the close. (RED before the fix: the close was selected as the entry.)
    assert d.entry_odds == mid_map
    assert d.entry_odds != close_map
    # The edge/stake were priced off the MID's de-vig, not the close's.
    from wcmodel.backtest.baselines import market_fair_1x2
    bt = cfg["backtest"]
    assert d.market_entry == market_fair_1x2(mid_map, method=bt["devig_method"])
    assert d.market_entry != market_fair_1x2(close_map, method=bt["devig_method"])
    # The CLOSE is still recorded (book-aware close snapshot) for later realized CLV ONLY,
    # and is a DIFFERENT price from the entry.
    assert d.close_odds == close_map
    assert d.close_odds != d.entry_odds


def test_decide_live_post_kickoff_non_close_refresh_is_a_non_bet(small_store, cfg):
    # FOCAL OPERATIONAL-LEAKAGE GATE (the post-kickoff-entry leak). `non_bet_snapshot`
    # only rejected entries OLDER than stale_seconds; an entry snapshot AT/AFTER kickoff
    # (age <= 0, an IN-GAME / post-kickoff price) passed as bettable. Because the
    # book-aware CLOSE is the LATEST snapshot <= kickoff, ANY snapshot AFTER the close is
    # > kickoff (post-kickoff). `_decision_time_entry` excludes only the close by ts (NOT
    # post-kickoff snapshots), so with a post-kickoff non-close refresh in the sample and
    # cutoff > that refresh, that in-game snapshot becomes the latest non-close <= cutoff
    # and would drive market_entry/edge/staked-side/stake — a leak (a bet priced off
    # post-kickoff, in-game information).
    #
    # Three snapshots for the book:
    #   T_mid   = kickoff-3h   (price MID, < commence)        — a legitimate pre-match price
    #   T_close = kickoff-5min (price CLOSE, <= kickoff)      — the book-aware close (CLV only)
    #   T_post  = kickoff+30min(price POST, > commence)       — an IN-GAME refresh; never an entry
    # cutoff = kickoff+1h (> T_post), so the post-kickoff snapshot is the latest non-close
    # <= cutoff. RED before the fix: it drives market_entry/stake (entry_ts > commence).
    # GREEN after: non_bet_reason == "post_kickoff", nothing staked, POST never drives the
    # market_entry/stake.
    commence = "2024-06-30T19:00:00Z"
    kickoff = pd.Timestamp(commence)
    t_mid = (kickoff - pd.Timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_close = (kickoff - pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_post = (kickoff + pd.Timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff = (kickoff + pd.Timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    price_mid = (2.50, 3.40, 3.00)    # a legitimate pre-match price
    price_close = (2.10, 3.50, 3.40)  # the book-aware close (CLV only)
    price_post = (1.20, 6.00, 9.00)   # an IN-GAME (post-kickoff) price — must NEVER be the entry
    post_map = dict(zip(OUTCOMES, price_post))

    sample = {
        _SYNTHETIC_KEY: True,
        "mid": _snap(t_mid, price_mid, commence=commence, bookmaker="pinnacle"),
        "close": _snap(t_close, price_close, commence=commence, bookmaker="pinnacle"),
        # The post-kickoff (in-game) refresh: > commence, > the close, <= cutoff. Pre-fix
        # the buggy path selects THIS as the latest non-close <= cutoff entry.
        "post": _snap(t_post, price_post, commence=commence, bookmaker="pinnacle"),
    }
    d = decide_live(small_store, sample, cutoff=cutoff, config=cfg,
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})

    # The post-kickoff snapshot is the latest non-close <= cutoff snapshot, so the entry
    # selector logs it as the decision-time entry — but it is a post-kickoff price, so the
    # decision is a COUNTED NON-BET, never a bet priced off in-game info.
    assert d.non_bet_reason == "post_kickoff"
    # Hardening: the selector DID pick the post-kickoff snapshot as the (rejected) entry —
    # this pins that the test exercises the post-kickoff path (the in-game snapshot was
    # selected as the latest non-close <= cutoff entry, then REJECTED by the guard), not a
    # no_odds/other non-bet that would pass vacuously.
    assert d.entry_ts == t_post
    assert d.entry_odds == post_map
    assert d.staked == ""             # no side staked off the in-game price
    assert d.stake == 0.0
    # The post-kickoff (in-game) price NEVER drove the market_entry/edge/stake.
    assert d.market_entry == {}
    assert d.edge == {}
    from wcmodel.backtest.baselines import market_fair_1x2
    bt = cfg["backtest"]
    assert d.market_entry != market_fair_1x2(post_map, method=bt["devig_method"])


def test_decide_live_no_book_price_before_cutoff_is_a_non_bet(small_store, cfg):
    # If NO snapshot <= cutoff contains the configured book (every <= cutoff snapshot
    # carries only some OTHER book), there is no decision-time price for the book =>
    # a COUNTED NON-BET (stake 0, reason "no_odds") — NEVER a crash and NEVER a price
    # off a snapshot that lacks the book.
    commence = "2024-06-30T19:00:00Z"
    kickoff = pd.Timestamp(commence)
    cutoff = (kickoff - pd.Timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t1 = (kickoff - pd.Timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t2 = (kickoff - pd.Timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # The configured book (pinnacle) is absent from EVERY pre-kickoff snapshot here
    # (the earliest <= kickoff snapshot is betfair-only, so even entry_close_prices'
    # book-keyed entry/close legs cannot resolve). decide_live must treat the book's
    # total absence as a counted no_odds non-bet (with NO close recorded) — NEVER a crash.
    # Event identity is still derived book-independently so the non-bet logs its event key.
    t_betfair_close = (kickoff - pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sample = {
        _SYNTHETIC_KEY: True,
        "s1": _snap(t1, (2.50, 3.40, 3.00), commence=commence, bookmaker="betfair"),
        "s2": _snap(t2, (2.10, 3.50, 3.40), commence=commence, bookmaker="betfair"),
        "s3": _snap(t_betfair_close, (2.10, 3.50, 3.40), commence=commence, bookmaker="betfair"),
    }
    d = decide_live(small_store, sample, cutoff=cutoff, config=cfg,
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert isinstance(d, LiveDecision)
    assert d.staked == ""           # no side staked
    assert d.stake == 0.0           # counted non-bet, not a price off a book-less snapshot
    assert d.entry_odds == {}       # no decision-time book price was logged
    assert d.close_odds == {}       # no book close to record for CLV (book absent entirely)
    # Event identity is still present (derived book-independently), so the non-bet is logged.
    assert d.event_key[0] == "Brazil" and d.event_key[1] == "Croatia"
    assert d.non_bet_reason == "no_odds"


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
