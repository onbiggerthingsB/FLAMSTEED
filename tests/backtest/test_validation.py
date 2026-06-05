import pytest

from wcmodel.backtest.validation import (
    ForesightRedError, check_foresight_red, leaked_feature_metrics,
)


def test_check_foresight_red_passes_plausible_metrics(cfg):
    ok = {"roi_roi": 0.03, "clv_beat_close_rate": 0.55, "clv_avg_clv": 0.01}
    # Plausible big-match upper-bound numbers -> no STOP.
    check_foresight_red(ok, config=cfg)            # must not raise


def test_check_foresight_red_stops_on_implausible_roi(cfg):
    leaked = {"roi_roi": 0.45, "clv_beat_close_rate": 0.55, "clv_avg_clv": 0.01}
    with pytest.raises(ForesightRedError) as ei:
        check_foresight_red(leaked, config=cfg)
    assert "roi" in str(ei.value).lower()          # names the tripped metric


def test_check_foresight_red_stops_on_implausible_beat_close(cfg):
    leaked = {"roi_roi": 0.02, "clv_beat_close_rate": 0.80, "clv_avg_clv": 0.01}
    with pytest.raises(ForesightRedError):
        check_foresight_red(leaked, config=cfg)


def test_check_foresight_red_stops_on_implausible_avg_clv(cfg):
    # roi (0.02 < 0.10) and beat-close (0.55 < 0.58) are both plausible; ONLY the
    # avg CLV (0.06 > 0.02) crosses RED -> pins the avg_clv ceiling in isolation.
    leaked = {"roi_roi": 0.02, "clv_beat_close_rate": 0.55, "clv_avg_clv": 0.06}
    with pytest.raises(ForesightRedError) as ei:
        check_foresight_red(leaked, config=cfg)
    assert "clv" in str(ei.value).lower()          # names the tripped metric


def test_leaked_feature_trips_red(small_store, cfg):
    """A synthetic LEAKED feature (the model is fed the realised outcome) must
    produce an implausibly good metric that trips foresight-RED -> STOP."""
    metrics = leaked_feature_metrics(seed=0)       # deliberately leaky -> ~perfect
    with pytest.raises(ForesightRedError):
        check_foresight_red(metrics, config=cfg)
