import json
from types import SimpleNamespace

import pandas as pd
import pytest

from wcmodel.backtest.odds_ingest import (
    _SYNTHETIC_KEY, _parse_ts, entry_close_prices, synthetic_odds_sample,
)
from wcmodel.backtest.validation import ForesightRedError
from wcmodel.live.decide import _decision_time_entry, decide_live
from wcmodel.live.validation import (
    AppendOnlyLedger, ImmutableLogError, assert_entry_logged_at_decision_time,
    MisLogError, check_live_foresight_red, assert_live_reproducible,
)


def _synth_sample():
    return synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
        bookmaker="pinnacle", seed=0,
    )


def _multi_snapshot_sample():
    """A 3-snapshot sample (early/mid/close) where the EARLIEST-<=-kickoff price (2.50)
    and the LATEST-<=-cutoff decision-time price (mid, 2.30) DIVERGE — the case that
    distinguishes the decision-time entry from the (cutoff-unaware) kickoff entry."""
    commence = "2024-06-30T19:00:00Z"
    ko = _parse_ts(commence)

    def _snap(ts, h, d, a):
        return {
            _SYNTHETIC_KEY: True, "timestamp": ts,
            "previous_timestamp": ts, "next_timestamp": ts,
            "data": [{
                "id": "X", "sport_key": "soccer_fifa_world_cup",
                "commence_time": commence, "home_team": "Brazil", "away_team": "Croatia",
                "bookmakers": [{"key": "pinnacle", "last_update": ts, "markets": [{
                    "key": "h2h", "last_update": ts,
                    "outcomes": [{"name": "Brazil", "price": h}, {"name": "Draw", "price": d},
                                 {"name": "Croatia", "price": a}],
                }]}],
            }],
        }

    t_early = (ko - pd.Timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_mid = (ko - pd.Timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_close = (ko - pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sample = {
        _SYNTHETIC_KEY: True,
        "early": _snap(t_early, 2.50, 3.40, 3.00),
        "mid": _snap(t_mid, 2.30, 3.45, 3.20),
        "close": _snap(t_close, 2.10, 3.50, 3.40),
    }
    return sample, t_mid


def _missing_earliest_book_sample():
    """The FOCAL constructed-miss sample: the EARLIEST <= kickoff snapshot LACKS the
    configured book (betfair-only) while LATER mid + close snapshots HAVE it (pinnacle).
    On this sample `entry_close_prices` raises on its earliest-entry leg, so a canary
    that re-derives its close_ts via that path gets close_ts=None and (mirroring the
    decide_live bug) would select the close as the entry. Returns (sample, cutoff, mid,
    close) with cutoff >= close_ts (so an un-excluded close is the latest <= cutoff
    book-present snapshot)."""
    commence = "2024-06-30T19:00:00Z"
    ko = _parse_ts(commence)

    def _snap(ts, h, d, a, *, bookmaker):
        return {
            _SYNTHETIC_KEY: True, "timestamp": ts,
            "previous_timestamp": ts, "next_timestamp": ts,
            "data": [{
                "id": "X", "sport_key": "soccer_fifa_world_cup",
                "commence_time": commence, "home_team": "Brazil", "away_team": "Croatia",
                "bookmakers": [{"key": bookmaker, "last_update": ts, "markets": [{
                    "key": "h2h", "last_update": ts,
                    "outcomes": [{"name": "Brazil", "price": h}, {"name": "Draw", "price": d},
                                 {"name": "Croatia", "price": a}],
                }]}],
            }],
        }

    t_early = (ko - pd.Timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")  # betfair-only, EARLIEST <= KO
    t_mid = (ko - pd.Timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")     # pinnacle, decision-time
    t_close = (ko - pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")  # pinnacle, the CLOSE
    cutoff = (ko - pd.Timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")   # cutoff >= close_ts
    mid = {"home": 2.30, "draw": 3.45, "away": 3.20}
    close = {"home": 2.10, "draw": 3.50, "away": 3.40}
    sample = {
        _SYNTHETIC_KEY: True,
        "early": _snap(t_early, 9.99, 9.99, 9.99, bookmaker="betfair"),
        "mid": _snap(t_mid, mid["home"], mid["draw"], mid["away"], bookmaker="pinnacle"),
        "close": _snap(t_close, close["home"], close["draw"], close["away"], bookmaker="pinnacle"),
    }
    return sample, cutoff, mid, close


def test_mislog_canary_passes_a_correctly_logged_entry(small_store, cfg):
    s = _synth_sample()
    d = decide_live(small_store, s["sample"], cutoff="2024-06-30T19:00:00Z",
                    config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # The logged entry == the bet_time (decision-time) snapshot prices; NOT the close.
    assert_entry_logged_at_decision_time(d, s["sample"], bookmaker="pinnacle")  # must not raise


def test_mislog_canary_CATCHES_a_close_logged_as_entry(small_store, cfg):
    """TEETH: a decision whose entry_odds were (wrongly) set to the CLOSE prices is a
    mis-log — the canary MUST raise. This is the focal live-leakage gate."""
    s = _synth_sample()
    d = decide_live(small_store, s["sample"], cutoff="2024-06-30T19:00:00Z",
                    config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # Sabotage: overwrite the logged entry with the CLOSE prices (the mis-log).
    d.entry_odds = dict(d.close_odds)
    with pytest.raises(MisLogError, match="(?i)entry.*close|close.*entry|mis-log"):
        assert_entry_logged_at_decision_time(d, s["sample"], bookmaker="pinnacle")


def test_mislog_canary_catches_close_as_entry_in_missing_earliest_book_case():
    """TEETH for the FOCAL constructed miss. On the missing-earliest-book sample
    (earliest <= KO lacks pinnacle; mid + close have it), a canary that re-derives its
    close reference through `entry_close_prices`' earliest-entry leg gets close_ts=None
    and (mirroring the decide_live bug) reproduces the SAME close-as-entry selection — so
    it would PASS a sabotaged decision whose logged entry IS the close. A mirror cannot
    catch a bug in the function it mirrors.

    The FIX makes the canary INDEPENDENTLY pin the entry: it derives the close snapshot
    BOOK-AWARE (latest <= kickoff WITH the book, independent of the crashing earliest leg)
    and asserts the logged entry is <= cutoff AND strictly NOT the close snapshot. So even
    when `_decision_time_entry` regresses to select the close (close_ts=None), the canary
    RAISES MisLogError on a decision whose logged entry == the close prices.
    """
    sample, cutoff, _mid, close = _missing_earliest_book_sample()
    # Sabotage: a decision whose logged ENTRY is the CLOSE prices (the focal mis-log) in
    # exactly the case the old mirror-canary would have let through.
    d = SimpleNamespace(cutoff=cutoff, entry_odds=dict(close), close_odds=dict(close))
    with pytest.raises(MisLogError, match="(?i)entry.*close|close.*entry|mis-log|decision.time|cutoff"):
        assert_entry_logged_at_decision_time(d, sample, bookmaker="pinnacle")


def test_mislog_canary_passes_the_latest_le_cutoff_entry_multi_snapshot():
    """The canary mirrors decide_live's REAL contract (latest <= cutoff snapshot WITH
    the book, close-excluded) via the SAME _decision_time_entry path — NOT the
    cutoff-unaware earliest-<=-kickoff price. On a 3-snapshot sample at a late cutoff,
    a correctly-logged decision-time (mid) entry must PASS (no false positive)."""
    sample, cutoff = _multi_snapshot_sample()
    pc = entry_close_prices(sample, bookmaker="pinnacle")
    entry, _ = _decision_time_entry(sample, bookmaker="pinnacle", cutoff=cutoff,
                                    close_ts=pc["close_ts"])
    assert entry["home"] == 2.30 and pc["entry"]["home"] == 2.50  # mid != earliest-<=-KO
    d = SimpleNamespace(cutoff=cutoff, entry_odds=dict(entry), close_odds=dict(pc["close"]))
    assert_entry_logged_at_decision_time(d, sample, bookmaker="pinnacle")  # must NOT raise


def test_mislog_canary_CATCHES_a_stale_pre_cutoff_entry_multi_snapshot():
    """TEETH (the closed miss): logging the STALE earliest-<=-kickoff price (2.50, a
    12h-old line) as the entry at a late cutoff — when the transactable decision-time
    price was the later 'mid' (2.30) — is a mis-log. The canary MUST raise. A
    cutoff-unaware canary (referencing entry_close_prices['entry']) would MISS this."""
    sample, cutoff = _multi_snapshot_sample()
    pc = entry_close_prices(sample, bookmaker="pinnacle")
    stale = pc["entry"]  # earliest-<=-kickoff (2.50) — NOT the decision-time price
    d = SimpleNamespace(cutoff=cutoff, entry_odds=dict(stale), close_odds=dict(pc["close"]))
    with pytest.raises(MisLogError, match="(?i)decision.time|cutoff|stale|mis-log"):
        assert_entry_logged_at_decision_time(d, sample, bookmaker="pinnacle")


def test_append_only_ledger_refuses_rewrite(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = AppendOnlyLedger(path)
    rec = {"event_key": ["Brazil", "Croatia", "2024-06-30"], "staked": "home",
           "entry_odds": 2.5, "close_odds": 2.1}
    ledger.append(rec)
    # A second append of a record with the SAME key is REFUSED (a silent re-price/
    # re-write of an already-logged signal). The log is append-only / immutable.
    with pytest.raises(ImmutableLogError, match="(?i)already logged|immutable|append-only"):
        ledger.append({**rec, "entry_odds": 9.99})    # attempt to re-price the entry
    # The on-disk record is unchanged (the original entry survives).
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["entry_odds"] == 2.5


def test_append_only_ledger_appends_distinct_keys(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "ledger.jsonl")
    ledger.append({"event_key": ["A", "B", "2024-06-30"], "staked": "home"})
    ledger.append({"event_key": ["C", "D", "2024-06-30"], "staked": "away"})
    assert len(ledger.records()) == 2


def test_append_only_immutability_is_disk_persisted_not_in_memory(tmp_path):
    """The immutability guard is enforced by the PERSISTED on-disk records, not an
    in-memory flag: a FRESH ledger object (a new 'process', no shared in-memory state)
    pointed at the same path reloads its keys from disk and STILL refuses the re-write.
    A sabotaged in-memory-only guard (that started with an empty key set) would let the
    re-write through — this test catches that (mirrors the Phase-4 lockbox disk proof)."""
    path = tmp_path / "ledger.jsonl"
    rec = {"event_key": ["Brazil", "Croatia", "2024-06-30"], "staked": "home",
           "entry_odds": 2.5}
    AppendOnlyLedger(path).append(rec)            # ledger A logs the signal, then is dropped
    fresh = AppendOnlyLedger(path)                 # a new instance — keys come ONLY from disk
    assert fresh._keys, "fresh ledger did not reload keys from disk — guard is in-memory-only"
    with pytest.raises(ImmutableLogError, match="(?i)already logged|immutable|append-only"):
        fresh.append({**rec, "entry_odds": 9.99})
    lines = path.read_text().strip().splitlines()  # disk record unchanged
    assert len(lines) == 1 and json.loads(lines[0])["entry_odds"] == 2.5


def test_check_live_foresight_red_stops_on_too_good(cfg):
    # A too-good live CLV (avg 0.06 > RED 0.02) trips foresight-RED => STOP, not celebrate.
    with pytest.raises(ForesightRedError):
        check_live_foresight_red({"clv_avg_clv": 0.06, "clv_beat_close_rate": 0.55,
                                  "roi_roi": 0.0}, config=cfg)


def test_assert_live_reproducible_passes_identical_decisions(small_store, cfg):
    s = _synth_sample()
    kw = dict(cutoff="2024-06-30T19:00:00Z", config=cfg,
              fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert_live_reproducible(lambda: decide_live(small_store, s["sample"], **kw))  # must not raise
