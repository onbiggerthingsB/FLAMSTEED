"""Elo ordered-logit head — proportional-odds MLE (spec OA-4).

Every fit here is on SYNTHETIC data drawn from the model's own generative
process: no real-store fit and no pool scoring happens in this task (both are
Plan 2, after the prereg locks).
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from wcmodel.eval.elo_ordlogit import OrdLogitParams, fit_ordlogit, predict_1x2
from wcmodel.model.calibration import rps

# Truth for the recovery test. The tolerance is RELATIVE (10%), so the truth
# has to be far enough from zero that the band clears the estimator's own
# sampling error at n=8,000 — otherwise the test measures the outcome draw,
# not the estimator. Measured at these values: SE 0.034 (thresholds) / 0.042
# (slopes), so the band is 2.7-3.5 SE; 59 of 60 independent panel seeds pass
# all four, and the pinned seed lands inside 0.25 of the band. Class mix is
# football-plausible (46% home / 32% draw / 22% away).
TRUE = {"c1": -0.9, "c2": 0.9, "b_elo": 1.5, "b_hfa": 1.4}

# Elo edges out to +-1500, past the widest gap international football produces
# (top nation vs bottom nation is ~1000 on this scale).
EDGES = (-1500.0, -600.0, -150.0, 0.0, 150.0, 600.0, 1500.0)


def _synthetic(n: int = 8_000, seed: int = 7, hfa_rows: int | None = None,
               **overrides: float) -> pd.DataFrame:
    """Draw ``n`` matches from the proportional-odds model itself.

    ``hfa`` defaults to a balanced ~50/50 split — the shape of a CLUB league.
    ``hfa_rows=k`` puts home advantage on exactly ``k`` rows instead: ``k`` in
    1-3 out of 64 is the international-pool shape this head will actually be
    fitted on, and ``k`` of 0 or ``n`` makes the column constant.
    """
    true = {**TRUE, **overrides}
    rng = np.random.default_rng(seed)
    elo_h = rng.normal(1600.0, 180.0, n)
    elo_a = rng.normal(1600.0, 180.0, n)
    if hfa_rows is None:
        hfa = rng.integers(0, 2, n).astype(float)
    else:
        hfa = np.zeros(n)
        hfa[:hfa_rows] = 1.0
    eta = true["b_elo"] * (elo_h - elo_a) / 400.0 + true["b_hfa"] * hfa
    p_away = 1.0 / (1.0 + np.exp(-(true["c1"] - eta)))
    p_not_home = 1.0 / (1.0 + np.exp(-(true["c2"] - eta)))
    u = rng.random(n)
    outcome = np.where(u < p_away, "away",
                       np.where(u < p_not_home, "draw", "home"))
    return pd.DataFrame({"elo_h": elo_h, "elo_a": elo_a, "hfa": hfa,
                         "outcome": outcome})


def _known() -> OrdLogitParams:
    """The generating parameters as an ``OrdLogitParams`` — lets the shape
    tests run without paying for a fit."""
    return OrdLogitParams(c1=TRUE["c1"], s=math.log(TRUE["c2"] - TRUE["c1"]),
                          b_elo=TRUE["b_elo"], b_hfa=TRUE["b_hfa"])


@pytest.fixture(scope="module")
def fitted() -> OrdLogitParams:
    return fit_ordlogit(_synthetic())


def test_recovers_known_parameters_within_10_percent(fitted):
    got = {"c1": fitted.c1, "c2": fitted.c2,
           "b_elo": fitted.b_elo, "b_hfa": fitted.b_hfa}
    for name, truth in TRUE.items():
        assert got[name] == pytest.approx(truth, rel=0.10), \
            f"{name}: fitted {got[name]!r} vs true {truth!r}"


def test_thresholds_stay_ordered(fitted):
    # c2 = c1 + exp(s) makes c1 < c2 structural, not a hope about the optimizer:
    # a crossed pair would put negative mass on the draw.
    assert fitted.c2 > fitted.c1


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("hfa", [0.0, 1.0])
def test_predictions_are_a_proper_distribution(edge, hfa):
    probs = predict_1x2(_known(), 1600.0 + edge, 1600.0, hfa)
    assert set(probs) == {"home", "draw", "away"}
    assert sum(probs.values()) == pytest.approx(1.0, abs=1e-12)
    assert all(0.0 < p < 1.0 for p in probs.values()), probs


def test_fitted_predictions_are_a_proper_distribution(fitted):
    for edge in EDGES:
        probs = predict_1x2(fitted, 1600.0 + edge, 1600.0, 1.0)
        assert sum(probs.values()) == pytest.approx(1.0, abs=1e-12)
        assert all(0.0 < p < 1.0 for p in probs.values()), (edge, probs)


@pytest.mark.parametrize("edge", [-12_000.0, 12_000.0])
def test_draw_survives_the_saturated_tail(edge):
    # Far outside football's range, but this is the regime the stable draw
    # identity exists for: a zero-probability outcome is one log_loss cannot
    # score and the likelihood cannot fit through.
    probs = predict_1x2(_known(), 1600.0 + edge, 1600.0, 0.0)
    assert probs["draw"] > 0.0, probs
    assert sum(probs.values()) == pytest.approx(1.0, abs=1e-12)


def test_the_saturated_tail_really_breaks_the_naive_difference():
    # Non-vacuity for the test above. The breakage is ONE-SIDED: sigmoid
    # underflows gradually toward 0 (denormals keep the difference alive at a
    # huge HOME edge, ~6e-20 there), but saturates abruptly AT 1.0 — so a huge
    # AWAY edge is where `sigmoid(c2-eta) - sigmoid(c1-eta)` collapses to
    # exactly zero and the stable form is what keeps the draw alive.
    params = _known()
    eta = params.b_elo * -12_000.0 / 400.0
    assert float(expit(params.c2 - eta) - expit(params.c1 - eta)) == 0.0
    assert predict_1x2(params, 1600.0 - 12_000.0, 1600.0, 0.0)["draw"] > 0.0


def test_output_feeds_the_canonical_scorer(fitted):
    # The head emits the canonical ("home","draw","away") key set, so it drops
    # straight into calibration.rps — no second probability convention (F16).
    score = rps(predict_1x2(fitted, 1700.0, 1500.0, 1.0), "home")
    assert 0.0 <= score <= 1.0


def test_the_fit_optimises_the_distribution_predict_returns(fitted):
    # The likelihood and predict_1x2 are two separate expressions of the same
    # distribution. If they ever drift apart the head silently optimises one
    # thing and reports another, and nothing else in this file would notice:
    # recovery and monotonicity would both still pass. Stated without reaching
    # into the private likelihood — the fitted vector must be a local minimum
    # of the NLL computed from predict_1x2's own output. The b_hfa prior moves
    # the optimum by 0.0125 on this frame (4,000 rows identify the term), a
    # quarter of the step below, so the UNPENALISED NLL still rises both ways.
    df = _synthetic()
    rows = list(zip(df["elo_h"], df["elo_a"], df["hfa"], df["outcome"]))

    def mean_nll(params: OrdLogitParams) -> float:
        return -sum(math.log(predict_1x2(params, h, a, x)[y])
                    for h, a, x, y in rows) / len(rows)

    base = mean_nll(fitted)
    for field in ("c1", "s", "b_elo", "b_hfa"):
        for step in (0.05, -0.05):
            moved = replace(fitted, **{field: getattr(fitted, field) + step})
            assert mean_nll(moved) > base, f"{field} {step:+}"


@pytest.mark.parametrize("hfa", [0.0, 1.0])
def test_p_home_strictly_increases_with_the_elo_edge(hfa):
    params = _known()
    edges = np.arange(-1200.0, 1201.0, 25.0)
    home = [predict_1x2(params, 1600.0 + d, 1600.0, hfa)["home"] for d in edges]
    away = [predict_1x2(params, 1600.0 + d, 1600.0, hfa)["away"] for d in edges]
    assert all(b > a for a, b in zip(home, home[1:]))
    assert all(b < a for a, b in zip(away, away[1:]))


def test_fitted_p_home_strictly_increases_with_the_elo_edge(fitted):
    edges = np.arange(-1200.0, 1201.0, 25.0)
    home = [predict_1x2(fitted, 1600.0 + d, 1600.0, 0.0)["home"] for d in edges]
    assert all(b > a for a, b in zip(home, home[1:]))


def test_home_advantage_shifts_probability_toward_the_home_team():
    params = _known()
    neutral = predict_1x2(params, 1600.0, 1600.0, 0.0)
    at_home = predict_1x2(params, 1600.0, 1600.0, 1.0)
    assert at_home["home"] > neutral["home"]
    assert at_home["away"] < neutral["away"]


@pytest.mark.parametrize("hfa_rows", [1, 2, 3])
def test_a_sparse_hfa_column_cannot_emit_a_point_forecast(hfa_rows):
    # The shape every pool this arm exists to score actually has: 64 fixtures,
    # home advantage on 1-3 of them because only the host plays at home. That
    # sub-sample is frequently separated (every host row a home win), where the
    # UNPENALISED MLE for b_hfa diverges and L-BFGS-B still reports success —
    # measured on this generator at b_hfa=+15.68 (1 row, seed 0), P(home)=
    # 0.9999998, i.e. log loss 15.4 if the host then loses, against ~1.1 for a
    # sane forecast. One such fixture moves a 64-match pool's mean RPS by more
    # than the prereg's whole gate, so the arm's contrast would measure the
    # fitter, not the information. Bounds below are the worst over this entire
    # 30-fit grid with the prior in place: |b_hfa| 0.42, P(home) 0.57,
    # smallest class 0.104 (log loss 2.26).
    for seed in range(10):
        fitted = fit_ordlogit(_synthetic(n=64, seed=seed, hfa_rows=hfa_rows))
        probs = predict_1x2(fitted, 1700.0, 1600.0, 1.0)
        why = f"seed {seed}: b_hfa={fitted.b_hfa!r} {probs}"
        assert abs(fitted.b_hfa) < 1.0, why
        assert probs["home"] < 0.8, why
        assert min(probs.values()) > 0.02, why


@pytest.mark.parametrize("hfa_rows", [0, 400])
def test_a_constant_hfa_column_is_not_estimated(hfa_rows):
    # Neither constant column identifies b_hfa, and refusing them is wrong
    # both ways: an all-neutral pool legitimately wants b_hfa=0, and an
    # all-at-home pool identifies only (c1 - b_hfa), so an unpenalised fit
    # lands on an arbitrary point of that ridge (measured c1=-1.062 with
    # b_hfa=+1.062) and then invents a materially different distribution for
    # the neutral venue it never observed. Pin b_hfa at 0, let c1 carry the
    # shift, and report that nothing identified the term.
    fitted = fit_ordlogit(_synthetic(n=400, hfa_rows=hfa_rows))
    assert fitted.b_hfa == pytest.approx(0.0, abs=1e-3)
    assert fitted.n_hfa_minority == 0
    neutral = predict_1x2(fitted, 1650.0, 1600.0, 0.0)
    at_home = predict_1x2(fitted, 1650.0, 1600.0, 1.0)
    assert neutral == pytest.approx(at_home, abs=1e-3)


def test_reports_the_rows_that_identify_home_advantage(fitted):
    # b_hfa is only ever as good as the smaller hfa level, and a caller cannot
    # otherwise tell an estimate from a prior: the same +0.4 means one thing
    # off 4,000 rows and another off 3.
    df = _synthetic()
    at_home = int((df["hfa"] == 1.0).sum())
    assert fitted.n_hfa_minority == min(at_home, len(df) - at_home)
    sparse = fit_ordlogit(_synthetic(n=64, seed=0, hfa_rows=3))
    assert sparse.n_hfa_minority == 3


def test_fit_is_bitwise_deterministic():
    df = _synthetic()
    first = fit_ordlogit(df)
    second = fit_ordlogit(df.copy())
    assert first == second
    # Dataclass equality would accept -0.0 == 0.0 and would not catch a
    # last-bit drift that survives repr(); hex() is the exact bit pattern.
    for field in ("c1", "s", "b_elo", "b_hfa"):
        assert getattr(first, field).hex() == getattr(second, field).hex()


def test_rejects_missing_columns():
    df = _synthetic(n=300).drop(columns=["hfa"])
    # Pin the RENDERED prefix. The message tails with `need [...]`, which lists
    # every required column, so a bare "hfa" match passes whichever column the
    # guard actually named — including a guard that names all of them.
    with pytest.raises(ValueError, match=r"missing column\(s\) \['hfa'\]"):
        fit_ordlogit(df)


def test_rejects_unknown_outcome_label():
    df = _synthetic(n=300)
    df.loc[0, "outcome"] = "shootout"
    with pytest.raises(ValueError, match="shootout"):
        fit_ordlogit(df)


def test_rejects_nulls():
    df = _synthetic(n=300)
    df.loc[5, "elo_a"] = np.nan
    with pytest.raises(ValueError, match="null"):
        fit_ordlogit(df)


@pytest.mark.parametrize("value", [np.inf, -np.inf])
@pytest.mark.parametrize("column", ["elo_h", "elo_a", "hfa"])
def test_rejects_non_finite_values(column, value):
    # isna() is False for +-inf, so the null guard alone passes an infinite
    # rating through to a "did not converge" RuntimeError (a misdiagnosis: the
    # input was inadmissible, the fit was fine) behind a raw RuntimeWarning
    # out of the numerical differencer.
    df = _synthetic(n=300)
    df.loc[5, column] = value
    with pytest.raises(ValueError, match="non-finite"):
        fit_ordlogit(df)


def test_rejects_an_absent_outcome_class():
    # With no draws the fit is not merely imprecise: the threshold gap runs to
    # its bound and the optimizer reports success on a meaningless answer.
    df = _synthetic(n=2_000)
    df = df[df["outcome"] != "draw"].reset_index(drop=True)
    with pytest.raises(ValueError, match="draw"):
        fit_ordlogit(df)


def test_rejects_an_empty_frame():
    empty = pd.DataFrame({"elo_h": [], "elo_a": [], "hfa": [], "outcome": []})
    with pytest.raises(ValueError):
        fit_ordlogit(empty)
