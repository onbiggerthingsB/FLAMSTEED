"""C5 end-to-end: the FULL dashboard bundle (schedule + fixtures/<id> + tournament +
track + meta) is emitted, GATED per-surface, STAMPED on every file, and NON-REAL-tainted
when the live items are synthetic. track.json is an honest coverage-gap when no backtest
records are supplied (the build NEVER re-runs the heavy walk-forward backtest)."""
import json

import pytest

from wcmodel.dashboard.build import build_snapshot
from wcmodel.backtest.odds_ingest import synthetic_odds_sample


@pytest.mark.slow
def test_full_bundle_emitted_gated_and_stamped(small_store, synthetic_tournament, tmp_path, cfg):
    s = synthetic_odds_sample(home="Brazil", away="Mexico", commence="2026-06-12T19:00:00Z",
                              entry=(2.5, 3.4, 3.0), close=(2.1, 3.5, 3.4), seed=0)
    b = build_snapshot("2026-06-12T12:00:00Z", store=small_store,
                       items=[{"sample": s["sample"], "liquidity": 50.0}],
                       config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                               "cache_dir": str(tmp_path / "fc")},
                       tournament=synthetic_tournament, out_root=tmp_path / "out")
    names = {p.name for p in b.glob("*.json")}
    assert {"schedule.json", "tournament.json", "track.json", "meta.json"} <= names
    assert (b / "fixtures").is_dir() and any((b / "fixtures").glob("*.json"))
    for p in b.rglob("*.json"):                       # every file stamped + NON-REAL (synthetic items)
        env = json.loads(p.read_text())
        assert env["provenance"]["is_synthetic"] is True and env["provenance"]["banner"]
        assert "data" in env
    # track is an honest coverage-gap when no backtest records supplied
    track = json.loads((b / "track.json").read_text())["data"]
    assert track.get("coverage_gap") is True
