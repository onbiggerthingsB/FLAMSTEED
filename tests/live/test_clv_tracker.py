import pytest

from wcmodel.backtest.validation import ForesightRedError
from wcmodel.live.clv_tracker import (
    PaperClvTracker, paper_pnl, clv_report,
)


def _ledger(tmp_path):
    return PaperClvTracker(tmp_path / "ledger.jsonl")


def test_log_signal_records_entry_close_clv_and_paper_pnl(tmp_path):
    t = _ledger(tmp_path)
    # A settled paper bet: staked home at entry 2.50, close 2.10 (+CLV), result home win.
    t.log_signal(event_key=["Brazil", "Croatia", "2024-06-30"], staked="home",
                 entry_odds=2.50, close_odds=2.10, stake=0.10, won=True,
                 match_type="wc_finals", confederation="CONMEBOL",
                 venue="pinnacle", commission={"pinnacle": 0.0, "betfair": 0.02},
                 is_synthetic=True)
    recs = t.records()
    assert len(recs) == 1
    r = recs[0]
    assert abs(r["clv_pct"] - (2.50 / 2.10 - 1.0)) < 1e-12
    assert r["beat_close"] is True
    # PAPER P&L: win at 2.50 on a 0.10 stake = 0.10*(2.5-1)=0.15 (pinnacle no commission).
    assert abs(r["paper_pnl"] - 0.15) < 1e-12
    assert r["paper"] is True and r["is_synthetic"] is True   # never a real bet/number


def test_tracker_is_append_only_refuses_rewrite(tmp_path):
    t = _ledger(tmp_path)
    kw = dict(event_key=["A", "B", "2024-06-30"], staked="home", entry_odds=2.0,
              close_odds=1.9, stake=0.1, won=True, match_type="wc_finals",
              confederation="UEFA", venue="pinnacle",
              commission={"pinnacle": 0.0, "betfair": 0.02}, is_synthetic=True)
    t.log_signal(**kw)
    # Re-logging the SAME signal (a silent re-price) is REFUSED (append-only).
    from wcmodel.live.validation import ImmutableLogError
    with pytest.raises(ImmutableLogError):
        t.log_signal(**{**kw, "entry_odds": 9.99})


def test_paper_pnl_betfair_commission_on_net_winnings():
    # Win at 2.5 on a 1.0 stake via betfair: gross 1.5, 2% commission => 1.47.
    assert abs(paper_pnl(stake=1.0, decimal_odds=2.5, won=True, venue="betfair",
                         commission={"pinnacle": 0.0, "betfair": 0.02}) - 1.47) < 1e-12
    # Loss => -stake (commission never on a loss).
    assert paper_pnl(stake=1.0, decimal_odds=2.5, won=False, venue="betfair",
                     commission={"pinnacle": 0.0, "betfair": 0.02}) == -1.0


def test_clv_report_leads_with_clv_stratified_and_labelled_non_real(tmp_path):
    t = _ledger(tmp_path)
    for i in range(3):
        t.log_signal(event_key=["T", f"O{i}", "2024-06-30"], staked="home",
                     entry_odds=2.10, close_odds=2.00, stake=0.1, won=(i % 2 == 0),
                     match_type="wc_finals", confederation="UEFA", venue="pinnacle",
                     commission={"pinnacle": 0.0, "betfair": 0.02}, is_synthetic=True)
    rep = clv_report(t.records())
    # CLV-first: the beat-close rate + avg CLV lead the summary.
    assert "clv_beat_close_rate" in rep["summary"] and "clv_avg_clv" in rep["summary"]
    # Stratified by tier.
    assert "wc_finals" in rep["by_match_type"]
    # The whole report is labelled non-real (dry-run).
    assert rep["is_synthetic"] is True


def test_clv_report_foresight_red_stops_on_too_good(tmp_path, cfg):
    t = _ledger(tmp_path)
    # Fabricate a suspiciously-good ledger: every bet beats the close by a huge margin.
    for i in range(5):
        t.log_signal(event_key=["T", f"O{i}", "2024-06-30"], staked="home",
                     entry_odds=3.0, close_odds=2.0, stake=0.1, won=True,
                     match_type="wc_finals", confederation="UEFA", venue="pinnacle",
                     commission={"pinnacle": 0.0, "betfair": 0.02}, is_synthetic=True)
    # avg CLV = 3/2-1 = 0.50 >> RED 0.02 => foresight-RED STOPs (a suspected bug).
    with pytest.raises(ForesightRedError):
        clv_report(t.records(), config=cfg, check_red=True)
