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

from wcmodel.eval.elo_ordlogit import (
    _INIT, OrdLogitParams, fit_ordlogit, predict_1x2)
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


def _separated_by_edge(n: int = 64, seed: int = 0) -> pd.DataFrame:
    """The same ratings, but outcomes made perfectly monotone in the Elo edge:
    the bottom third of the edge ranking loses, the top third wins.

    Complete separation on the load-bearing slope — the b_elo analogue of the
    separated host sub-sample ``_HFA_PRIOR_SD`` exists for.
    """
    df = _synthetic(n=n, seed=seed, hfa_rows=0)
    order = np.argsort((df["elo_h"] - df["elo_a"]).to_numpy())
    third = n // 3
    label = np.empty(n, dtype=object)
    label[order[:third]] = "away"
    label[order[third:2 * third]] = "draw"
    label[order[2 * third:]] = "home"
    return df.assign(outcome=label)


def _flat_edge(n: int = 400, seed: int = 0,
               jitter: float = 0.5) -> pd.DataFrame:
    """Every rating within ``jitter`` Elo of the 1500 default — the shape a
    rating join produces when almost nothing matched (see the constant-edge
    test below for why that lookup lands there)."""
    rng = np.random.default_rng(seed)
    df = _synthetic(n=n, seed=seed)
    return df.assign(elo_h=1500.0 + rng.uniform(-jitter, jitter, n),
                     elo_a=1500.0 + rng.uniform(-jitter, jitter, n))


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


def test_rejects_a_two_level_hfa_column_that_omits_zero():
    # The other half of the test above: it pins that n_hfa_minority reads 0
    # when nothing identified b_hfa, and this pins that it cannot read 0 when
    # something did. np.count_nonzero is not a level counter, so a {1,2}
    # coding — two levels, 120 of 400 rows at the minority one — reported
    # n_hfa_minority=0, i.e. "the column was constant", about a real 120-row
    # estimate of b_hfa=0.794, while the two levels forecast materially
    # differently (P(home) 0.389 at hfa=1 vs 0.584 at hfa=2). A false 0 is
    # worse than no field at all: it reassures in exactly the case that owed a
    # warning. Refuse the coding rather than count around it.
    df = _synthetic(n=400, hfa_rows=120)
    df["hfa"] += 1.0
    with pytest.raises(ValueError, match=r"hfa value\(s\)"):
        fit_ordlogit(df)


@pytest.mark.parametrize("hfa_rows", [1, 2, 3])
def test_rejects_an_hfa_column_carried_in_rating_points(hfa_rows):
    # The prior is the only thing between this arm and a separated host
    # sub-sample, and its analytic guard |b_hfa| <= sd**2 * sum(hfa) is a
    # statement about the INDICATOR: the bound grows with sum(hfa) while the
    # latent shift is b_hfa * hfa, so a column carried in rating points (the
    # elo_1x2_baseline convention, 60.0/0.0) buys 60x the shift per unit of
    # bound and the guard stops binding. Measured on the sparse grid above:
    # worst latent home-advantage shift +6.90, against 0.416 for the indicator
    # control on the identical seeds — P(home)=0.9985, smallest class 2.1e-4,
    # i.e. log loss 8.5, exactly the blow-up the prior exists to prevent —
    # while the nominal bound there is 0.25*180 = 45, non-binding by two orders
    # of magnitude. Nothing else would catch the mis-pass: 60.0 is an ordinary
    # finite float in a column of ordinary finite floats.
    for seed in range(10):
        df = _synthetic(n=64, seed=seed, hfa_rows=hfa_rows)
        df["hfa"] *= 60.0
        with pytest.raises(ValueError, match=r"hfa value\(s\)"):
            fit_ordlogit(df)


@pytest.mark.parametrize("elo_h, elo_a", [(1500.0, 1500.0), (1234.5, 1134.5)])
def test_rejects_a_constant_elo_edge(elo_h, elo_a):
    # A constant edge leaves the arm's LOAD-BEARING slope unidentified: the
    # likelihood is exactly flat in b_elo, so the _ELO_PRIOR term decides and
    # the fit reports success at the prior's 0. Measured on THIS frame at HEAD
    # with the guard bypassed: b_elo = 1.4176e-04 (1500/1500) and -1.8571e-04
    # (1234.5/1134.5), result.success True, no exception and no warning, and
    # the head then priced a +400-Elo mismatch at {'home': 0.352, 'draw':
    # 0.372, 'away': 0.276} — well-formed probabilities carrying ZERO rating
    # information, which would score as a real arm with elo_edge_sd = 0.0 as
    # the only tell. (Pre-prior, the same defect leaked the init 1.0 instead —
    # the prior changed the failure's shape, not the need for this guard.)
    #
    # Reachable through this repo's own rating-lookup idiom, not a hypothetical:
    # `ratings.get(team, initial_rating)` at elo.py:130-131,
    # walkforward.py:397-398 and calibration.py:199-200 all fall back to the
    # shared initial rating for an unseen team, and this module hands the
    # rating_pre join to the CALLER on purpose (to stay point-in-time). A team-
    # name join that misses entirely therefore puts every row at the same
    # default and every edge at 0. The second case pins that the guard is about
    # VARIATION, not about zero: a constant NON-zero gap is equally unidentified
    # (it is absorbed by c1) and must not slip past a `(edge == 0).all()` check.
    df = _synthetic(n=400)
    df["elo_h"] = elo_h
    df["elo_a"] = elo_a
    with pytest.raises(ValueError, match="Elo edge is constant"):
        fit_ordlogit(df)


@pytest.mark.parametrize("n", [24, 48, 64, 129])
def test_a_separated_elo_edge_cannot_emit_a_point_forecast(n):
    # The b_elo half of the separation hazard _HFA_PRIOR_SD documents but only
    # ever applied to b_hfa. On a frame whose outcomes are monotone in the Elo
    # edge the MLE diverges while L-BFGS-B still reports SUCCESS: measured over
    # this exact grid, worst |b_elo| = 30,708 with c1 = -5,698 (n=48 seed 2),
    # where predict_1x2 returned the EXACT point mass {'home': 1.0, 'draw':
    # 0.0, 'away': 0.0}. That output passes ledger._check_probs (sums to 1, all
    # in [0,1]) and calibration.log_loss scores it at 34.5 via its 1e-15 clip
    # — i.e. it enters the Plan-2 contrast as a legitimate forecast, with the
    # clip hiding how impossible it is. Bounds are the worst over this whole
    # 40-fit grid with the b_elo prior in place: |b_elo| 13.20, smallest class
    # 7.5e-6 at the +200 fixture (log loss 11.8 — bad, but a real distribution
    # scored as itself rather than as the clip).
    for seed in range(10):
        fitted = fit_ordlogit(_separated_by_edge(n=n, seed=seed))
        probs = predict_1x2(fitted, 1800.0, 1600.0, 0.0)
        why = f"n={n} seed={seed}: b_elo={fitted.b_elo!r} {probs}"
        assert abs(fitted.b_elo) < 25.0, why
        assert min(probs.values()) > 1e-6, why


@pytest.mark.parametrize("jitter", [0.5, 2.0, 5.0])
def test_a_near_constant_elo_edge_cannot_emit_a_point_forecast(jitter):
    # The constant-edge guard above is a cliff, but the defect degrades
    # CONTINUOUSLY: at a few Elo points of spread the objective is not flat, so
    # the fit is a real MLE — of noise. Nothing identifies the slope, so it runs
    # to whatever magnitude the residual wiggle supports, and that magnitude is
    # then applied to REAL edges at predict time. Measured over this grid
    # without the prior: worst |b_elo| = 167.6, and predicting an ordinary
    # +200-Elo fixture off such a fit returned a smallest class of 1.7e-37 (log
    # loss 84.6, or 34.5 once log_loss clips it). Worst with the prior: |b_elo|
    # 1.57 and smallest class 0.161. Note the fitted frames are IDENTICAL in
    # every column but the ratings — only the edge information was destroyed.
    for seed in range(5):
        fitted = fit_ordlogit(_flat_edge(seed=seed, jitter=jitter))
        probs = predict_1x2(fitted, 1800.0, 1600.0, 0.0)
        why = f"jitter={jitter} seed={seed}: b_elo={fitted.b_elo!r} {probs}"
        assert abs(fitted.b_elo) < 5.0, why
        assert min(probs.values()) > 0.05, why


def test_the_fitted_slope_survives_its_own_prior(fitted):
    # The other side of the two tests above: the prior that caps a separated
    # fit must be invisible where the data identify the slope, or the arm would
    # measure the penalty instead of the Elo edge. Recovery already pins b_elo
    # within 10% of 1.5 at n=8,000; this pins the tighter statement that the
    # penalty is what moved it by almost nothing — 1.5020 unpenalised ->
    # 1.5018 penalised, 0.018%. On the 64-fixture frames this arm is actually
    # scored on, the worst shrink over 12 seeds is 2.96% (a prior SD of 1.0
    # would cost 20.8% there, which is why the scale is 3.0).
    assert fitted.b_elo == pytest.approx(1.5020455, rel=1e-3)


@pytest.mark.parametrize("hfa", [60.0, 2.0, 0.5, -1.0, float("nan")])
def test_predict_rejects_a_non_indicator_hfa(hfa):
    # Guarding only the fit frame leaves the mis-pass live at the point of use:
    # predict_1x2 accepted hfa=60 against indicator-fitted params and returned
    # {"home": 1.0, "draw": 4.7e-37, "away": 9.2e-38} — a point mass on the
    # home team, no error and no warning, log loss 85 if the away team wins.
    # Same domain, same guard, both sides of the contract.
    with pytest.raises(ValueError, match=r"hfa value\(s\)"):
        predict_1x2(_known(), 1700.0, 1600.0, hfa)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("side", ["elo_h", "elo_a"])
def test_predict_rejects_a_non_finite_rating(side, bad):
    # The same argument as the hfa guard above, applied to the other two
    # arguments _design already checks in the fit frame (_NUMERIC). The module
    # hands the rating_pre join to the CALLER to stay point-in-time, so a
    # left-merge miss on a team name arrives here as NaN — and NaN is the
    # quiet one: predict_1x2 returned {"home": nan, "draw": nan, "away": nan},
    # rps() and log_loss() both returned nan, and Series.mean() skips NaN by
    # default, so the fixture is DROPPED from that arm's mean RPS instead of
    # raising. Differential fixture-dropping is what a paired contrast cannot
    # survive. An infinite rating is worse: it returned {"home": 1.0, "draw":
    # 0.0, "away": 0.0}, which sums to 1 with every value in [0,1] and so
    # PASSES ledger._check_probs as a legitimate point mass — log loss 34.5
    # when the away team wins, and no error anywhere along the way.
    ratings = {"elo_h": 1700.0, "elo_a": 1600.0, side: bad}
    with pytest.raises(ValueError, match=r"non-finite rating\(s\)"):
        predict_1x2(_known(), ratings["elo_h"], ratings["elo_a"], 1.0)


def test_reports_the_rows_that_identify_home_advantage(fitted):
    # b_hfa is only ever as good as the smaller hfa level, and a caller cannot
    # otherwise tell an estimate from a prior: the same +0.4 means one thing
    # off 4,000 rows and another off 3.
    df = _synthetic()
    at_home = int((df["hfa"] == 1.0).sum())
    assert fitted.n_hfa_minority == min(at_home, len(df) - at_home)
    sparse = fit_ordlogit(_synthetic(n=64, seed=0, hfa_rows=3))
    assert sparse.n_hfa_minority == 3


def test_reports_the_spread_that_identifies_the_elo_slope(fitted):
    # The b_elo counterpart of n_hfa_minority, and needed for the same reason:
    # a slope is only ever as good as the variation that identified it, and
    # b_elo=1.2 means one thing off 253 Elo points of spread and another off
    # 0.4. fit_ordlogit refuses a spread of exactly 0 (see the constant-edge
    # test), so a FITTED head can never report 0.0 here — which is what makes
    # the hand-built default unambiguous.
    df = _synthetic()
    assert fitted.elo_edge_sd == pytest.approx(
        float((df["elo_h"] - df["elo_a"]).to_numpy().std()))
    assert fitted.elo_edge_sd == pytest.approx(252.67, abs=0.01)
    assert _known().elo_edge_sd == 0.0


def test_the_preregistered_init_is_the_planned_vector():
    # The plan names this exact vector as part of the estimator's definition
    # ("seed-free deterministic init [0.0, 0.0, 1.0, 0.0]", Task 6), and
    # reproducibility of a PRE-REGISTERED estimator is what the whole program
    # is buying: an init moved to speed convergence is a different estimator
    # reporting under the same name. Nothing else pins it — mutating the
    # literal to [0.0, 0.0, 3.0, 0.0] left every other test in this file green
    # (re-verified at HEAD: 1 failed, 70 passed). Since the b_elo prior landed,
    # a degenerate fit reports the prior's 0 rather than this init (see the
    # constant-edge test) — the init still defines the estimator, it just no
    # longer leaks into degenerate fits.
    assert tuple(_INIT) == (0.0, 0.0, 1.0, 0.0)


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
