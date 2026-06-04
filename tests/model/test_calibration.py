"""Phase-2 calibration harness tests — RPS vs the Elo baseline + PPC.

IN-SAMPLE sanity (Phase 2), NOT the betting bar. The matches available at a
cutoff are exactly the ones the model was FIT on, so any same-cutoff RPS is
in-sample. The real out-of-sample RPS/CLV is the Phase-4 walk-forward backtest.
Per the project rule, a too-good in-sample result (model RPS << Elo) is a
SUSPECTED OVERFIT/bug to surface, not a win.

RPS literal note (see calibration.rps docstring): the standard 3-outcome ranked
probability score of {"home":.5,"draw":.3,"away":.2} with outcome "away" is
0.445, NOT the 0.2725 in the task draft. Arithmetic (ordered home,draw,away):
observed=away -> cumulative observed [0,0,1]; cumulative predicted [.5,.8,1.0];
RPS = (1/(r-1)) * sum_{i=1..r-1}(CP_i-CO_i)^2 = (1/2)*[(.5-0)^2+(.8-0)^2]
    = (1/2)*(0.25+0.64) = (1/2)*0.89 = 0.445.
No standard RPS variant (with/without the 1/(r-1) factor, either cumulation
direction) yields 0.2725, so the literal is corrected to the verified 0.445.
"""
import numpy as np
import pytest

from wcmodel.model.calibration import (
    posterior_predictive_checks,
    rps,
    vs_elo_baseline,
)


def test_rps_known_values():
    assert rps({"home": 1, "draw": 0, "away": 0}, "home") == 0.0
    # standard 3-outcome ranked probability score (corrected literal: 0.445).
    assert round(rps({"home": .5, "draw": .3, "away": .2}, "away"), 4) == 0.445


def test_rps_is_in_zero_one():
    for p, o in [({"home": .4, "draw": .3, "away": .3}, "draw"),
                 ({"home": .8, "draw": .1, "away": .1}, "home")]:
        assert 0.0 <= rps(p, o) <= 1.0


@pytest.mark.slow
def test_vs_elo_baseline_returns_both_scores(small_store):
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=150, seed=0, advi_iters=3000)
    rep = vs_elo_baseline(post, small_store, cutoff="2024-06-01")
    assert {"model_rps", "elo_rps", "n_matches", "in_sample"} <= set(rep)
    assert rep["n_matches"] >= 1
    assert rep["in_sample"] is True            # this harness is in-sample (sanity, not the betting bar)
    assert 0.0 <= rep["model_rps"] <= 1.0 and 0.0 <= rep["elo_rps"] <= 1.0
