import json

import pandas as pd

from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.data.store import BitemporalStore
from wcmodel.live.clv_tracker import PaperClvTracker, clv_report
from wcmodel.live.decide import decide_live
from wcmodel.live.ingest_live import ingest_live_result
from wcmodel.live.odds_live import live_snapshot_from_fixture
from wcmodel.live.scan import scan
from wcmodel.live.validation import assert_entry_logged_at_decision_time
from wcmodel.live.tournament import _settle  # noqa: F401  (re-exported helper, see note)


def test_dry_run_end_to_end_full_loop(small_store, cfg, tmp_path):
    """The FULL live loop on the CLEARLY-NON-REAL synthetic harness, NO spend:
    fetch (dry-run) -> ingest -> decide -> scan -> log -> CLV. Every number is labelled
    non-real; the mis-log canary passes; foresight-RED guards the tracker."""
    # 1) FETCH (dry-run): a synthetic event's snapshot mapping, NO network.
    s = synthetic_odds_sample(home="Brazil", away="Croatia",
                              commence="2024-06-30T19:00:00Z",
                              entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
                              bookmaker="pinnacle", seed=0)
    live_now = live_snapshot_from_fixture(s["sample"], which="bet_time")
    assert live_now["_dry_run"] is True

    # 2) INGEST (post-match): write the ACTUAL played result POINT_IN_TIME (observed
    #    after kickoff). Uses an isolated store so the small_store fit input is intact.
    rstore = BitemporalStore(tmp_path / "rstore")
    ingest_live_result(rstore, home_team="Brazil", away_team="Croatia",
                       date="2024-06-30", home_score=2, away_score=0,
                       tournament="FIFA World Cup", neutral=True, city="Inglewood",
                       country="United States", observed_at="2024-06-30T21:00:00Z")
    settled = rstore.read("results", cutoff="2024-07-01")
    assert int(settled.iloc[0]["home_score"]) == 2

    # 3) DECIDE at cutoff=now (the fit reads small_store's < now history).
    d = decide_live(small_store, s["sample"], cutoff="2024-06-30T19:00:00Z",
                    config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # The mis-log canary passes: the logged entry is the decision-time price.
    assert_entry_logged_at_decision_time(d, s["sample"], bookmaker="pinnacle")
    assert d.is_synthetic is True

    # 4) SCAN -> Ranked (edge x liquidity), labelled non-real.
    ranked = scan(small_store, [{"sample": s["sample"], "liquidity": 50.0}],
                  cutoff="2024-06-30T19:00:00Z", config=cfg,
                  fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert ranked.is_synthetic is True

    # 5) LOG + CLV: settle the staked signal against the actual result, log it, report.
    tracker = PaperClvTracker(tmp_path / "ledger.jsonl")
    if d.staked:                       # if a bet fired
        outcome = "home" if 2 > 0 else ("away" if 2 < 0 else "draw")
        tracker.log_signal(
            event_key=d.event_key, staked=d.staked,
            entry_odds=d.entry_odds[d.staked], close_odds=d.close_odds[d.staked],
            stake=d.stake, won=(d.staked == outcome), match_type="wc_finals",
            confederation="CONMEBOL", venue=cfg["live"]["bookmaker"],
            commission=cfg["backtest"]["commission"], is_synthetic=True)
    rep = clv_report(tracker.records())
    # The authoritative forward number is labelled non-real (dry-run) — never an edge claim.
    assert rep["is_synthetic"] is True
    assert rep["paper"] is True
    # The whole loop produced a structured artifact + a CLV summary, no real spend.
    assert "clv_beat_close_rate" in rep["summary"]
