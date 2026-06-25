"""Smoke test for the favorite-band diagnostic CLI core (scripts/diagnose_favorite_band.py).

Loads the script as a module (scripts/ is not a package), exercises score_population
on small_store over one tiny segment with a fast (50-iter) ADVI fit, and checks the
report shape + the markdown renderer. Does NOT exercise main()'s real-store assembly.
"""
import importlib.util
from pathlib import Path

import pytest

from wcmodel.config import load_config

_SPEC = importlib.util.spec_from_file_location(
    "diagnose_favorite_band",
    Path(__file__).resolve().parents[2] / "scripts" / "diagnose_favorite_band.py")
dfb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dfb)


def test_score_population_returns_bucketed_report(small_store):
    # Fast ADVI fit (50 iters) — this is a plumbing smoke test, not an accuracy test.
    cfg = load_config()
    cfg["model"]["inference"]["advi_iters"] = 50
    segments = [("2025-03-01", "2027-01-01", "smoke")]   # (cutoff, window_end, label)
    report = dfb.score_population(small_store, segments, label="smoke", config=cfg)
    assert "bands" in report and "all" in report["bands"]
    assert "n_scored" in report
    # Null-safe even if the tiny store scores zero favorites.
    assert report["bands"]["all"]["n"] >= 0


def test_render_markdown_has_band_rows():
    fake = {
        "label": "demo", "n_scored": 3,
        "bands": {
            "0.55-0.65": {"n": 0, "pred_fav_win": None, "real_fav_win": None,
                          "pred_draw": None, "real_draw": None, "mean_rps": None,
                          "miscalibrated": None, "pred_marg_ge3": None,
                          "real_marg_ge3": None},
            "0.65-0.75": {"n": 0, "pred_fav_win": None, "real_fav_win": None,
                          "pred_draw": None, "real_draw": None, "mean_rps": None,
                          "miscalibrated": None, "pred_marg_ge3": None,
                          "real_marg_ge3": None},
            "0.75-0.85": {"n": 0, "pred_fav_win": None, "real_fav_win": None,
                          "pred_draw": None, "real_draw": None, "mean_rps": None,
                          "miscalibrated": None, "pred_marg_ge3": None,
                          "real_marg_ge3": None},
            "0.85+": {"n": 0, "pred_fav_win": None, "real_fav_win": None,
                      "pred_draw": None, "real_draw": None, "mean_rps": None,
                      "miscalibrated": None, "pred_marg_ge3": None,
                      "real_marg_ge3": None},
            "all": {"n": 3, "pred_fav_win": 0.7, "real_fav_win": 0.55,
                    "pred_draw": 0.2, "real_draw": 0.33, "mean_rps": 0.2,
                    "miscalibrated": True, "pred_marg_ge3": 0.15,
                    "real_marg_ge3": 0.1},
        },
    }
    md = dfb.render_markdown([fake])
    assert "demo" in md and "0.55-0.65" in md and "MISCALIBRATED" in md.upper()
