import math

import pytest

from wcmodel.dashboard.track import reliability_bins, track_record


def test_reliability_bins_compare_forecast_to_outcome():
    # Both near-0.65 forecasts must land in the SAME 10-bin cell [0.6, 0.7). Probe the
    # bin with a mid-bin value (0.65), not the 0.6 edge: np.linspace(0,1,11) makes that
    # edge 0.6000000000000001, so an on-edge probe would select the neighbouring bin.
    preds = [{"p": 0.61, "hit": 1}, {"p": 0.63, "hit": 0}, {"p": 0.10, "hit": 0}]
    bins = reliability_bins(preds, n_bins=10)
    b6 = [b for b in bins if b["bin_lo"] <= 0.65 < b["bin_hi"]][0]
    assert b6["n"] == 2 and abs(b6["empirical"] - 0.5) < 1e-9
    assert b6["forecast_mean"] > 0.0


def test_track_record_leads_with_clv_and_carries_rps_vs_baselines():
    bets = [{"entry_odds": 2.5, "close_odds": 2.1, "won": True, "stake": 1.0},
            {"entry_odds": 3.0, "close_odds": 3.4, "won": False, "stake": 1.0}]
    preds = [{"p": 0.6, "hit": 1, "rps_model": 0.10, "rps_market": 0.12, "rps_elo": 0.15}]
    tr = track_record(bets=bets, preds=preds)
    assert "beat_close_rate" in tr and "avg_clv" in tr
    assert tr["rps"]["model"] <= tr["rps"]["elo"]
    assert tr["is_synthetic"] is True


def test_track_record_preds_only_gaps_clv_not_nan():
    """FIX E: predictions made but NO bet cleared the edge threshold is LEGITIMATE — the track
    must show RPS/reliability and GAP the CLV block (beat_close_rate/avg_clv None, n_bets 0),
    NEVER a NaN (which gate_track would raise on, crashing the build). RED before (track_record
    calls clv_summary([]) -> NaN beat_close_rate); GREEN after (None)."""
    preds = [{"p": 0.6, "hit": 1, "rps_model": 0.10, "rps_market": 0.12, "rps_elo": 0.15}]
    tr = track_record(bets=[], preds=preds)
    assert tr["n_bets"] == 0
    assert tr["beat_close_rate"] is None and tr["avg_clv"] is None
    assert not (isinstance(tr["beat_close_rate"], float) and math.isnan(tr["beat_close_rate"]))
    assert tr["rps"]["model"] == pytest.approx(0.10)   # rps still populated from preds


@pytest.mark.slow
def test_preds_only_records_build_gaps_clv_no_crash(small_store, synthetic_tournament, tmp_path):
    """FIX E (E2 wiring): a records dict with ONLY ``preds`` (no ``"bets"`` key — the shape of a
    real ``walkforward.Metrics.to_dict()`` missing preds, or a no-bet-cleared run) must NOT
    KeyError, and must produce a GATED track with the CLV block gapped (beat_close_rate None,
    n_bets 0) and RPS populated — never a NaN/crash. RED before (hard-index ``["bets"]`` ->
    KeyError, or clv_summary([]) -> NaN -> gate_track raises); GREEN after (defensive .get +
    CLV-gap)."""
    import json
    from wcmodel.dashboard.build import build_snapshot
    preds = [{"p": 0.6, "hit": 1, "rps_model": 0.10, "rps_market": 0.12, "rps_elo": 0.15}]
    b = build_snapshot("2026-06-12T12:00:00Z", store=small_store, items=[],
                       fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                   "cache_dir": str(tmp_path / "fc")},
                       out_root=tmp_path / "out", tournament=synthetic_tournament,
                       backtest_records={"preds": preds})   # NO "bets" key (Metrics-shaped)
    track = json.loads((b / "track.json").read_text())["data"]
    assert track.get("coverage_gap") is not True          # a real (gated) track, not a gap
    assert track["beat_close_rate"] is None and track["n_bets"] == 0
    assert track["rps"]["model"] is not None              # rps populated from preds


def test_empty_backtest_records_build_emits_a_coverage_gap_track(
        small_store, synthetic_tournament, tmp_path):
    """FIX E: a TRUTHY-but-EMPTY backtest_records dict (empty bets/preds) must NOT take the
    metrics branch — ``clv_summary([])`` returns NaN, which ``gate_track`` would then raise on.
    The build must emit an honest ``coverage_gap`` track instead (no NaN). RED before (the
    truthy dict takes the metrics branch -> NaN track -> gate_track raises); GREEN after (an
    empty records dict -> coverage_gap track)."""
    from wcmodel.dashboard.build import build_snapshot
    b = build_snapshot("2026-06-12T12:00:00Z", store=small_store, items=[],
                       fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                   "cache_dir": str(tmp_path / "fc")},
                       out_root=tmp_path / "out", tournament=synthetic_tournament,
                       backtest_records={"bets": [], "preds": []})   # truthy but EMPTY
    import json
    track = json.loads((b / "track.json").read_text())["data"]
    assert track.get("coverage_gap") is True, (
        "an empty backtest_records dict must emit a coverage_gap track, not a NaN metrics track")
