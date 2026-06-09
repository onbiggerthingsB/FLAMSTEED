from wcmodel.live.clv_tracker import PaperClvTracker, clv_report
import importlib.util
spec = importlib.util.spec_from_file_location("scan_value", "scripts/scan_value.py")
sv = importlib.util.module_from_spec(spec); spec.loader.exec_module(sv)


def test_settle_records_realized_clv(tmp_path):
    t = PaperClvTracker(tmp_path / "clv.jsonl")
    sv.settle_one(t, event_key=["A v B", "2026-06-15"], staked="A", entry_odds=2.70,
                  close_odds=2.40, stake=0.01, won=True, match_type="wc_finals")
    recs = t.records()
    assert len(recs) == 1 and recs[0]["beat_close"] is True       # 2.70 entry beat 2.40 close
    # clv_report runs without error; the beat-close rate lives under summary as
    # clv_beat_close_rate (clv_report prefixes clv_summary's keys with "clv_").
    assert clv_report(recs)["summary"]["clv_beat_close_rate"] >= 0.0
