import json

import pandas as pd

import pytest

from wcmodel.backtest.odds_ingest import (
    OUTCOMES, book_aware_close, event_key, entry_close_prices,
    synthetic_odds_sample, non_bet_snapshot, _SYNTHETIC_KEY,
)


def _sample(path):
    return json.load(open(path))


def test_outcomes_order_is_fixed():
    assert OUTCOMES == ("home", "draw", "away")


def test_event_key_is_home_away_commence_date():
    ev = {"home_team": "Brazil", "away_team": "Croatia",
          "commence_time": "2026-06-11T19:00:00Z"}
    assert event_key(ev) == ("Brazil", "Croatia", pd.Timestamp("2026-06-11").date())


def test_entry_close_prices_uses_real_parse_path(odds_fixture_path):
    sample = _sample(odds_fixture_path)
    pc = entry_close_prices(sample, bookmaker="pinnacle")
    # entry = bet_time snapshot, close = nearest-kickoff snapshot — both via the
    # real extract_closing_prices/parse_snapshot path (no network, no spend).
    assert pc["is_synthetic"] is False
    assert pc["entry"]["home"] == 1.62 and pc["entry"]["away"] == 6.10   # bet_time pinnacle
    assert pc["close"]["home"] == 1.57 and pc["close"]["away"] == 6.50   # close pinnacle
    assert pc["commence_time"] == "2026-06-11T19:00:00Z"
    # Prices are ordered consistently with OUTCOMES.
    assert set(pc["entry"]) == set(OUTCOMES)


def test_synthetic_sample_is_labelled_non_real():
    s = synthetic_odds_sample(home="X", away="Y", commence="2024-06-20T19:00:00Z",
                              entry=(2.0, 3.4, 4.0), close=(1.9, 3.5, 4.3),
                              bookmaker="pinnacle", seed=0)
    # The harness MUST self-label as non-real (D1 rider) at every surface.
    assert s["is_synthetic"] is True
    assert "SYNTHETIC" in s["provenance"]
    # It still flows through the SAME real parse path: entry/close extract cleanly.
    pc = entry_close_prices(s["sample"], bookmaker="pinnacle")
    assert pc["is_synthetic"] is True            # provenance propagates
    assert pc["entry"]["home"] == 2.0 and pc["close"]["away"] == 4.3


def test_synthetic_marker_key_is_single_source_of_truth():
    # MUST-FIX 1(a): the marker key is ONE module constant shared by writer+reader,
    # so the writer's stamp and the reader's lookup can never drift to two literals.
    assert _SYNTHETIC_KEY == "_is_synthetic"


def test_synthetic_marker_rides_on_nested_snapshots_not_only_the_wrapper():
    # MUST-FIX 1(b): every nested snapshot the harness builds carries the marker —
    # the flag travels WITH the snapshot, not only on the outer wrapper, so a
    # snapshot lifted out of the wrapper still self-identifies as synthetic.
    s = synthetic_odds_sample(home="X", away="Y", commence="2024-06-20T19:00:00Z",
                              entry=(2.0, 3.4, 4.0), close=(1.9, 3.5, 4.3))
    sample = s["sample"]
    snaps = [v for v in sample.values()
             if isinstance(v, dict) and "timestamp" in v and "data" in v]
    assert snaps, "harness must build at least one nested snapshot"
    for snap in snaps:
        assert snap.get(_SYNTHETIC_KEY) is True   # marker is on the snapshot itself


def test_entry_close_is_synthetic_contract_true_and_false(odds_fixture_path):
    # MUST-FIX 1: pin the is_synthetic contract at the entry_close_prices boundary.
    # A real (non-synthetic) fixture sample => False; a synthetic harness sample => True.
    real = _sample(odds_fixture_path)
    assert entry_close_prices(real, bookmaker="pinnacle")["is_synthetic"] is False
    syn = synthetic_odds_sample(home="X", away="Y", commence="2024-06-20T19:00:00Z",
                                entry=(2.0, 3.4, 4.0), close=(1.9, 3.5, 4.3))
    assert entry_close_prices(syn["sample"], bookmaker="pinnacle")["is_synthetic"] is True


def _historical_snap(ts: str, prices: tuple[float, float, float]) -> dict:
    """A per-event historical-route snapshot: ``data`` is ONE bare event DICT,
    not a list (OA F13) — the shape ``odds.fetch_historical`` returns per
    snapshot on ``/historical/sports/{sport}/events/{id}/odds``."""
    h, d, a = prices
    return {
        "timestamp": ts,
        "previous_timestamp": ts,
        "next_timestamp": ts,
        "data": {
            "id": "evt_BRA_CRO", "sport_key": "soccer_fifa_world_cup",
            "commence_time": "2026-06-11T19:00:00Z",
            "home_team": "Brazil", "away_team": "Croatia",
            "bookmakers": [{
                "key": "pinnacle", "last_update": ts,
                "markets": [{"key": "h2h", "last_update": ts,
                             "outcomes": [{"name": "Brazil", "price": h},
                                          {"name": "Draw", "price": d},
                                          {"name": "Croatia", "price": a}]}],
            }],
        },
    }


def test_entry_close_prices_accepts_dict_shaped_single_event_data():
    # The natural Plan-2 pipeline: fetch_historical (per-event route, ``data``
    # is ONE bare event dict) -> {"bet_time": ..., "close": ...} -> here. The
    # event-identity read must go through the SAME dict/list normalizer
    # parse_snapshot uses (odds.event_list), not assume ``data[0]``.
    sample = {
        "bet_time": _historical_snap("2026-06-11T13:00:00Z", (1.62, 4.1, 6.10)),
        "close": _historical_snap("2026-06-11T18:55:00Z", (1.57, 4.2, 6.50)),
    }
    pc = entry_close_prices(sample, bookmaker="pinnacle")
    assert pc["entry"] == {"home": 1.62, "draw": 4.1, "away": 6.10}
    assert pc["close"] == {"home": 1.57, "draw": 4.2, "away": 6.50}
    assert pc["event_key"] == ("Brazil", "Croatia",
                               pd.Timestamp("2026-06-11").date())
    assert pc["is_synthetic"] is False


def test_book_aware_close_accepts_dict_shaped_single_event_data():
    # Same dual-shape contract for the live decide path's close-exclusion leg.
    sample = {
        "bet_time": _historical_snap("2026-06-11T13:00:00Z", (1.62, 4.1, 6.10)),
        "close": _historical_snap("2026-06-11T18:55:00Z", (1.57, 4.2, 6.50)),
    }
    bac = book_aware_close(sample, bookmaker="pinnacle")
    assert bac == {"close": {"home": 1.57, "draw": 4.2, "away": 6.50},
                   "close_ts": "2026-06-11T18:55:00Z"}


def test_non_bet_snapshot_flags_sign_flip_wide_spread_and_stale():
    # A negative/<=1.0 decimal price (impossible/garbage) => non-bet.
    bad = {"home": 1.8, "draw": 0.9, "away": 4.0}
    assert non_bet_snapshot(bad, entry_ts="2024-06-20T18:55:00Z",
                            commence="2024-06-20T19:00:00Z", max_spread=0.05,
                            stale_seconds=86400) == "sign_flip"
    # A stale entry (older than stale_seconds before kickoff) => non-bet.
    ok = {"home": 1.8, "draw": 3.6, "away": 4.0}
    assert non_bet_snapshot(ok, entry_ts="2024-06-18T00:00:00Z",
                            commence="2024-06-20T19:00:00Z", max_spread=1.0,
                            stale_seconds=3600) == "stale"
    # A clean, timely snapshot => None (bettable).
    assert non_bet_snapshot(ok, entry_ts="2024-06-20T18:55:00Z",
                            commence="2024-06-20T19:00:00Z", max_spread=1.0,
                            stale_seconds=86400) is None
