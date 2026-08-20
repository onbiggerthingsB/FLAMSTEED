"""Tests for the baseline: the metric conventions, the maths, and the cutoff.

The three things worth testing here, in order of how much damage they would do
undetected:

1. THE CUTOFF. A forecast that has seen its own match scores beautifully and
   means nothing. `test_leakage_*` rewrites the future and asserts the past
   does not move — the only test of point-in-time discipline that a careful
   implementation cannot pass by accident.
2. THE RPS CONVENTION. A silent factor of two would put every forecaster near
   0.4 and make a tie with Elo look like a rout. Pinned against hand-computed
   values AND against the World Cup model's own implementation.
3. THE DE-VIG. If the odds columns were scrambled or the normalisation wrong,
   the "market" bar would be fiction. Pinned against `wcmodel.data.devig`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from epl import baseline, devig, elo as elo_mod, ordlogit, score as score_mod, walk


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
def _toy(n_seasons: int = 3, seed: int = 7) -> pd.DataFrame:
    """A synthetic league: 20 clubs, full double round-robin, one match a day.

    Real strengths are fixed and results are sampled from them, so Elo has
    something to find; the bottom three clubs are relegated each season and
    replaced by weaker ones, which exercises the promotion/relegation path.
    """
    rng = np.random.default_rng(seed)
    strength = {f"c{i:02d}": rng.normal(0, 0.4) for i in range(20)}
    rows = []
    day = pd.Timestamp("2000-08-01")
    for s in range(n_seasons):
        clubs = sorted(strength)
        for h in clubs:
            for a in clubs:
                if h == a:
                    continue
                lam_h = np.exp(0.25 + strength[h] - strength[a])
                lam_a = np.exp(strength[a] - strength[h])
                gh, ga = rng.poisson(lam_h), rng.poisson(lam_a)
                rows.append({
                    "match_id": f"{s}-{h}-{a}", "season": f"S{s}",
                    "date": day, "kickoff": pd.NaT,
                    "home_key": h, "away_key": a,
                    "fthg": int(gh), "ftag": int(ga), "played": True,
                    "ftr": "H" if gh > ga else ("A" if gh < ga else "D"),
                    "odds_h": np.nan, "odds_d": np.nan, "odds_a": np.nan,
                })
                day += pd.Timedelta(days=1)
        worst = sorted(strength, key=strength.get)[:3]
        for club in worst:
            del strength[club]
            strength[f"n{s}{club}"] = rng.normal(-0.5, 0.3)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def real() -> pd.DataFrame:
    return baseline.load_matches()


# --------------------------------------------------------------------------
# 1. the cutoff
# --------------------------------------------------------------------------
def test_blocks_partition_and_are_ordered(real):
    blocks = walk.blocks(real)
    assert sum(len(b) for b in blocks) == len(real)
    assert np.array_equal(np.concatenate(blocks), np.arange(len(real)))
    keys = walk.cutoff_keys(real).to_numpy()
    for b in blocks:                       # one key per block, strictly rising
        assert len(set(keys[b])) == 1
    firsts = [keys[b[0]] for b in blocks]
    assert all(a < b for a, b in zip(firsts, firsts[1:]))


def test_cutoff_key_refuses_a_half_timed_day(real):
    """The one configuration where a single cutoff key cannot express the rule."""
    df = real.head(400).copy()
    df.loc[df.index[0], "kickoff"] = df.loc[df.index[0], "date"] + pd.Timedelta(hours=15)
    with pytest.raises(ValueError, match="both timed and untimed"):
        walk.cutoff_keys(df)


def test_leakage_elo_ratings_do_not_move_when_the_future_is_rewritten(real):
    """Overwrite every result after a cutoff; earlier PRE ratings must be identical.

    This is the load-bearing test in the file. It is not a check that the code
    is careful — it is a check that the code CANNOT be careless, because a walk
    that consulted a later row would move these numbers.
    """
    df = real.copy()
    cut = pd.Timestamp("2021-01-01")
    tampered = df.copy()
    future = tampered["date"] >= cut
    assert future.sum() > 1000
    # Every future match becomes a 9-0 home win: maximal, systematic distortion.
    tampered.loc[future, ["fthg", "ftag"]] = [9, 0]
    tampered.loc[future, "ftr"] = "H"

    base, _ = elo_mod.compute_elo_history(df, elo_mod.EloConfig())
    tamp, _ = elo_mod.compute_elo_history(tampered, elo_mod.EloConfig())
    before = base["date"] < cut
    for col in ("elo_home_pre", "elo_away_pre", "elo_diff_pre"):
        np.testing.assert_array_equal(base.loc[before, col].to_numpy(),
                                      tamp.loc[before, col].to_numpy())
    # Positive control: the test would be vacuous if nothing moved at all.
    assert not np.allclose(base.loc[~before, "elo_diff_pre"],
                           tamp.loc[~before, "elo_diff_pre"])


def test_leakage_forecasts_do_not_move_when_the_future_is_rewritten(real):
    """The same attack through the whole stack — ratings, head, base rate."""
    df = real[real["season"].isin(baseline.TUNE_SEASONS)].copy()
    cut = pd.Timestamp("2017-01-01")
    tampered = df.copy()
    future = tampered["date"] >= cut
    tampered.loc[future, ["fthg", "ftag"]] = [0, 4]
    tampered.loc[future, "ftr"] = "A"

    seasons = [s for s in baseline.TUNE_SEASONS if s != "2014/15"]
    a = baseline.evaluate(df, elo_mod.EloConfig(), seasons, require_odds=False)
    b = baseline.evaluate(tampered, elo_mod.EloConfig(), seasons,
                          require_odds=False)
    keep = a.frame["date"] < cut
    assert keep.sum() > 200
    cols = [f"{m}_{o}" for m in ("elo", "base") for o in score_mod.OUTCOMES]
    np.testing.assert_array_equal(a.frame.loc[keep, cols].to_numpy(),
                                  b.frame.loc[keep, cols].to_numpy())
    assert not np.allclose(a.frame.loc[~keep, cols].to_numpy(),
                           b.frame.loc[~keep, cols].to_numpy())


def test_head_is_never_fitted_on_its_own_block(real):
    """The head's fit sample must end exactly where its block begins."""
    df = real[real["season"].isin(baseline.TUNE_SEASONS)].copy()
    history, _ = elo_mod.compute_elo_history(df, elo_mod.EloConfig())
    want = np.ones(len(history), dtype=bool)
    _, log = baseline.walk_forward_head(history, want)
    assert log
    for entry in log:
        assert entry["n"] == entry["block_start_row"]


def test_tuner_refuses_a_scoring_season(real):
    with pytest.raises(ValueError, match="scoring season"):
        baseline.tune(real, grid=[elo_mod.EloConfig()], verbose=False)


# --------------------------------------------------------------------------
# 2. the metric conventions
# --------------------------------------------------------------------------
def test_rps_matches_hand_computation():
    # p = (0.6, 0.3, 0.1), realised HOME.
    # cumulative predicted (0.6, 0.9); observed (1, 1)
    # -> ((0.4)^2 + (0.1)^2) / 2 = (0.16 + 0.01)/2 = 0.085
    p = np.array([[0.6, 0.3, 0.1]])
    assert score_mod.rps(p, np.array([0])) == pytest.approx(0.085)
    # realised DRAW: cumulative observed (0, 1) -> (0.36 + 0.01)/2 = 0.185
    assert score_mod.rps(p, np.array([1])) == pytest.approx(0.185)
    # realised AWAY: cumulative observed (0, 0) -> (0.36 + 0.81)/2 = 0.585
    assert score_mod.rps(p, np.array([2])) == pytest.approx(0.585)


def test_rps_is_the_halved_convention():
    """A uniform forecast scores 5/18 on home or away and 1/9 on a draw.

    Under the OTHER published convention (no ``1/(r-1)`` factor) these are 5/9
    and 2/9 — exactly twice. The bar this probe is measured against is quoted
    on the halved one, so this test is what stops a factor of two from turning
    a tie with Elo into an apparent rout.
    """
    p = np.full((3, 3), 1 / 3)
    got = score_mod.rps(p, np.array([0, 1, 2]))
    assert got == pytest.approx([5 / 18, 1 / 9, 5 / 18])
    # Weighted by the league's own outcome frequencies, a uniform forecast
    # lands near the published base-rate bar (~0.234) — the cross-check that
    # this is the scale the bar is quoted on.
    assert 0.20 < float(np.average(got, weights=[0.44, 0.24, 0.32])) < 0.26
    # Bounds: a perfect forecast scores 0, the worst possible scores 1.
    assert score_mod.rps(np.array([[1.0, 0, 0]]), np.array([0])) == pytest.approx(0)
    assert score_mod.rps(np.array([[1.0, 0, 0]]), np.array([2])) == pytest.approx(1)


def test_rps_agrees_with_the_world_cup_model(real):
    """Same convention as `wcmodel.model.calibration.rps`, on real forecasts."""
    from wcmodel.model.calibration import rps as wc_rps

    rng = np.random.default_rng(0)
    p = rng.dirichlet([3, 2, 2], size=300)
    y = rng.integers(0, 3, size=300)
    mine = score_mod.rps(p, y)
    theirs = np.array([
        wc_rps(dict(zip(score_mod.OUTCOMES, row)), score_mod.OUTCOMES[k])
        for row, k in zip(p, y)])
    np.testing.assert_allclose(mine, theirs, atol=1e-12)


def test_rps_cumulation_order_is_load_bearing():
    """Handing the columns in (home, away, draw) order is a real hazard, and it
    produces a materially different score rather than an error — which is why
    the order is a module constant that every producer writes into."""
    p = np.array([[0.6, 0.3, 0.1]])
    assert score_mod.rps(p, np.array([0])) == pytest.approx(0.085)
    assert score_mod.rps(p[:, [0, 2, 1]], np.array([0])) == pytest.approx(0.125)


def test_log_loss_and_accuracy():
    p = np.array([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]])
    y = np.array([0, 1])
    np.testing.assert_allclose(score_mod.log_loss(p, y),
                               [-np.log(0.5), -np.log(0.3)])
    np.testing.assert_allclose(score_mod.hit(p, y), [1.0, 0.0])


def test_metrics_refuse_unnormalised_probabilities():
    with pytest.raises(ValueError, match="sum to 1"):
        score_mod.rps(np.array([[0.5, 0.3, 0.1]]), np.array([0]))


def test_paired_gap_refuses_different_match_sets():
    with pytest.raises(ValueError, match="SAME matches"):
        score_mod.paired_gap("a", np.zeros(10), "b", np.zeros(9))


def test_block_bootstrap_widens_with_correlated_blocks():
    """A block bootstrap must be wider than an iid one when blocks carry the
    signal; if it is not, the blocking is not doing anything."""
    rng = np.random.default_rng(3)
    block_effect = rng.normal(0, 0.05, size=60)
    d = np.repeat(block_effect, 20) + rng.normal(0, 0.005, size=1200)
    labels = np.repeat(np.arange(60), 20).astype(object)
    lo_b, hi_b, nb = score_mod.block_bootstrap_ci(d, labels, n_boot=2000)
    lo_i, hi_i, ni = score_mod.block_bootstrap_ci(d, np.arange(1200).astype(object),
                                                  n_boot=2000)
    assert nb == 60 and ni == 1200
    assert (hi_b - lo_b) > 3 * (hi_i - lo_i)


# --------------------------------------------------------------------------
# 3. the de-vig
# --------------------------------------------------------------------------
def test_devig_agrees_with_the_world_cup_model(real):
    """Both methods, on the real closing prices, to 1e-12."""
    from wcmodel.data import devig as wc_devig

    prices = real[["odds_h", "odds_d", "odds_a"]].dropna().to_numpy(float)[:500]
    np.testing.assert_allclose(
        devig.proportional(prices),
        np.array([wc_devig.multiplicative(list(r)) for r in prices]), atol=1e-12)
    np.testing.assert_allclose(
        devig.shin(prices),
        np.array([wc_devig.shin(list(r)) for r in prices]), atol=1e-9)


def test_devig_removes_the_overround_and_keeps_the_order(real):
    prices = real[["odds_h", "odds_d", "odds_a"]].dropna().to_numpy(float)
    for method in (devig.proportional, devig.shin):
        p = method(prices)
        np.testing.assert_allclose(p.sum(axis=1), 1.0, atol=1e-12)
        assert (p > 0).all()
        # De-vigging must not reorder the outcomes: it removes a margin, it
        # does not form a view.
        assert (np.argsort(np.argsort(-p, axis=1), axis=1)
                == np.argsort(np.argsort(prices, axis=1), axis=1)).all()


def test_shin_shrinks_longshots_relative_to_proportional():
    prices = np.array([[1.30, 5.50, 12.0]])
    prop = devig.proportional(prices)[0]
    sh = devig.shin(prices)[0]
    assert sh[2] < prop[2] and sh[0] > prop[0]


def test_devig_refuses_a_corrupt_book():
    with pytest.raises(ValueError, match="exceed 1.0"):
        devig.proportional(np.array([[0.9, 5.0, 5.0]]))
    with pytest.raises(ValueError, match="below 1"):
        devig.proportional(np.array([[4.0, 4.0, 4.0]]))


# --------------------------------------------------------------------------
# 4. the Elo itself
# --------------------------------------------------------------------------
def test_expected_score_and_one_update_by_hand():
    cfg = elo_mod.EloConfig(k=20.0, home_advantage=100.0)
    # Equal ratings, +100 home advantage -> E = 1/(1+10^-0.25) = 0.640065...
    e = elo_mod.expected_score(1500.0, 1500.0, cfg.home_advantage)
    assert e == pytest.approx(1 / (1 + 10 ** -0.25))
    df = pd.DataFrame([{
        "match_id": "m", "season": "S0", "date": pd.Timestamp("2020-01-01"),
        "kickoff": pd.NaT, "home_key": "h", "away_key": "a",
        "fthg": 1, "ftag": 0, "ftr": "H", "played": True}])
    hist, _ = elo_mod.compute_elo_history(df, cfg)
    delta = 20.0 * (1.0 - e)
    assert hist.loc[0, "elo_home_post"] == pytest.approx(1500 + delta)
    assert hist.loc[0, "elo_away_post"] == pytest.approx(1500 - delta)


def test_elo_is_zero_sum_within_a_season():
    """Total rating is conserved: every point one club gains, another loses.

    Checked over all 20 clubs' FINAL ratings, not over one match — a
    per-match check would pass even if the two sides were updated with
    different gains.
    """
    df = _toy(n_seasons=1)
    hist, _ = elo_mod.compute_elo_history(df, elo_mod.EloConfig())
    final: dict[str, float] = {}
    for _, row in hist.iterrows():           # chronological, so the last wins
        final[row["home_key"]] = row["elo_home_post"]
        final[row["away_key"]] = row["elo_away_post"]
    assert len(final) == 20
    assert sum(final.values()) == pytest.approx(20 * 1500.0, abs=1e-8)


def test_promoted_clubs_are_seeded_below_the_division_mean():
    df = _toy(n_seasons=3)
    cfg = elo_mod.EloConfig(promoted_offset=-150.0)
    hist, starts = elo_mod.compute_elo_history(df, cfg)
    later = [s for s in starts if not s["first_season"]]
    assert later and all(len(s["promoted"]) == 3 for s in later)
    for s in later:
        assert s["promoted_seed"] == pytest.approx(s["division_mean"] - 150.0)
    # And the promoted flag reaches the history rows.
    assert hist["home_promoted"].sum() > 0


def test_carryover_regresses_toward_the_division_mean():
    df = _toy(n_seasons=2)
    full, _ = elo_mod.compute_elo_history(df, elo_mod.EloConfig(carryover=1.0))
    flat, _ = elo_mod.compute_elo_history(df, elo_mod.EloConfig(carryover=0.0))
    second = full["season"] == "S1"
    # carryover=0 wipes every continuing club to the division mean, so the
    # first block of season 2 has no spread at all.
    first_block = flat[second].iloc[:1]
    assert abs(first_block["elo_diff_pre"].iloc[0]) < 1e-9
    assert abs(full[second]["elo_diff_pre"].iloc[0]) > 1e-9


def test_elo_config_refuses_a_positive_promoted_offset():
    with pytest.raises(ValueError, match="ABOVE the division mean"):
        elo_mod.EloConfig(promoted_offset=25.0)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        elo_mod.EloConfig(carryover=1.5)


def test_elo_beats_the_base_rate_on_data_it_should(real):
    """A sanity floor: if walk-forward Elo cannot beat a constant on 1,140 real
    matches, something upstream is broken, not subtle."""
    df = real[real["season"].isin(baseline.TUNE_SEASONS)].copy()
    seasons = [s for s in baseline.TUNE_SEASONS if s != "2014/15"]
    ev = baseline.evaluate(df, elo_mod.EloConfig(), seasons, require_odds=False)
    assert ev.scores["elo"].rps < ev.scores["base"].rps - 0.01


# --------------------------------------------------------------------------
# 5. the ordered-logit head
# --------------------------------------------------------------------------
def test_ordlogit_recovers_known_parameters():
    truth = ordlogit.OrdLogitParams(c1=-0.35, s=np.log(0.75), b=1.5)
    rng = np.random.default_rng(11)
    edge = rng.normal(0, 150, size=40_000)
    p = ordlogit.predict(truth, edge)
    y = np.array([rng.choice(3, p=row) for row in p])
    got = ordlogit.fit(edge, y)
    assert got.c1 == pytest.approx(truth.c1, abs=0.05)
    assert got.b == pytest.approx(truth.b, abs=0.05)
    assert got.c2 == pytest.approx(truth.c2, abs=0.05)


def test_ordlogit_probabilities_are_a_proper_distribution():
    params = ordlogit.OrdLogitParams(c1=-0.3, s=-0.4, b=1.4)
    p = ordlogit.predict(params, np.linspace(-2000, 2000, 401))
    np.testing.assert_allclose(p.sum(axis=1), 1.0, atol=1e-12)
    assert (p > 0).all(), "the draw must never vanish, even far out in the tail"
    # Monotone in the edge: more rating advantage, more home probability.
    assert (np.diff(p[:, 0]) > 0).all() and (np.diff(p[:, 2]) < 0).all()


def test_ordlogit_prior_costs_little_where_the_data_identify_the_slope():
    """The slope penalty exists for the first few dozen matches of a walk. On a
    league-sized sample it must be invisible in the fourth decimal."""
    rng = np.random.default_rng(5)
    truth = ordlogit.OrdLogitParams(c1=-0.3, s=-0.3, b=1.5)
    edge = rng.normal(0, 150, size=4_000)
    y = np.array([rng.choice(3, p=row) for row in ordlogit.predict(truth, edge)])
    penalised = ordlogit.fit(edge, y)
    original = ordlogit.SLOPE_PRIOR_SD
    try:
        ordlogit.SLOPE_PRIOR_SD = 1e6          # effectively unpenalised
        plain = ordlogit.fit(edge, y)
    finally:
        ordlogit.SLOPE_PRIOR_SD = original
    assert abs(penalised.b - plain.b) / abs(plain.b) < 0.01


def test_ordlogit_refuses_an_unidentified_fit():
    y = np.array([0, 1, 2, 0, 1, 2])
    with pytest.raises(ValueError, match="constant"):
        ordlogit.fit(np.zeros(6), y)
    with pytest.raises(ValueError, match="absent class|no \\['draw'\\]"):
        ordlogit.fit(np.arange(6.0), np.array([0, 2, 0, 2, 0, 2]))


def test_the_optimum_does_not_depend_on_where_the_fit_started(real):
    """Four starting points a hundredfold apart, on REAL blocks, must agree.

    This is what licenses the walk to be read as "the head fitted on these
    rows" rather than "wherever the optimizer happened to stop": if the answer
    moved with the start, every reported number would carry an invisible
    dependence on the order the walk ran in.

    The tolerance is 1e-7 in probability — measured worst case here is 6e-9,
    and the gap this whole exercise is trying to resolve is 7e-3, five orders
    larger. With L-BFGS-B's default tolerances and no gradient the same four
    starts land ~1e-4 apart, which is why the fit is configured as it is.
    """
    history, _ = elo_mod.compute_elo_history(real, elo_mod.EloConfig())
    edge = history["elo_diff_pre"].to_numpy(float)
    y = score_mod.outcome_codes(history["ftr"].to_numpy())
    starts = [None,
              ordlogit.OrdLogitParams(c1=2.0, s=1.0, b=4.0),
              ordlogit.OrdLogitParams(c1=-3.0, s=-2.0, b=0.2),
              ordlogit.OrdLogitParams(c1=0.5, s=2.0, b=-1.0)]
    for cut in (300, 1520, 2500, 4560):
        fits = [ordlogit.fit(edge[:cut], y[:cut], init=s) for s in starts]
        probs = [ordlogit.predict(f, edge[:cut]) for f in fits]
        for p in probs[1:]:
            np.testing.assert_allclose(p, probs[0], atol=1e-7, rtol=0)
        assert all(f.grad_max <= ordlogit.GRAD_TOL for f in fits)


def test_the_fitted_slope_reproduces_elos_own_curve(real):
    """Elo's expected score is ``logit = ln(10) * d / 400``, so a head that has
    learned what the ratings mean should land near ``b = 2.303``. Landing far
    from it would say the rating scale and the head disagree — which is a
    symptom of a broken join, not a modelling choice."""
    history, _ = elo_mod.compute_elo_history(real, elo_mod.EloConfig())
    fitted = ordlogit.fit(history["elo_diff_pre"].to_numpy(float),
                          score_mod.outcome_codes(history["ftr"].to_numpy()))
    assert 1.8 < fitted.b < 2.8
    assert fitted.c1 < fitted.c2, "thresholds must stay ordered"


# --------------------------------------------------------------------------
# 6. end to end
# --------------------------------------------------------------------------
def test_evaluate_produces_a_complete_case_frame(real):
    df = real[real["season"].isin(["2014/15", "2015/16", "2016/17"])].copy()
    ev = baseline.evaluate(df, elo_mod.EloConfig(), ["2016/17"])
    assert len(ev.frame) == 380
    for name in ("elo", "base", "market", "market_shin"):
        cols = [f"{name}_{o}" for o in score_mod.OUTCOMES]
        assert ev.frame[cols].notna().all().all()
        np.testing.assert_allclose(ev.frame[cols].sum(axis=1), 1.0, atol=1e-9)
    assert ev.frame["block"].nunique() > 20


def test_toy_league_walk_is_reproducible():
    df = _toy(n_seasons=2)
    a, _ = elo_mod.compute_elo_history(df, elo_mod.EloConfig())
    b, _ = elo_mod.compute_elo_history(df.iloc[::-1].copy(), elo_mod.EloConfig())
    # Row order in must not change the answer: the walk sorts for itself.
    pd.testing.assert_frame_equal(a, b)
