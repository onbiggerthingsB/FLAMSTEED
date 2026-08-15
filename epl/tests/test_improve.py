"""The gates, and the one property that makes them usable: OFF is INERT.

THE CENTRAL TEST IS NOT A UNIT TEST. ``test_off_end_to_end_is_bit_identical``
runs two REAL Dixon-Coles fits at a tuning-window cutoff — one through
``epl.dcfit.fit_epl`` + ``Posterior.predict_1x2`` (the path that produced
``reports/epl_walkforward.md``) and one through ``epl.improve.fit_improved`` with
every gate off — and demands ``np.array_equal`` on the 1X2 probabilities. Not
``allclose``. A gate that perturbs the control arm by 1e-12 is still a gate that
perturbs the control arm, and every A/B measured afterwards would carry it.

Everything else here checks a gate does what its docstring says when it IS on,
because an inert gate and a broken gate are indistinguishable from the OFF test
alone.
"""

from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from epl import baseline, dcfit, freeze, improve, paths, walkforward, windows
from epl import anchor as anchor_mod, fit as epl_fit
from epl.improve import Improvements, OFF
from epl.schema import sort_for_walk_forward

#: A TUNING-window cutoff. Every fit in this file runs here: the OFF-identity
#: property is a property of the code, not of a season, so there is no reason to
#: demonstrate it on a scored window and every reason not to.
TUNE_CUTOFF = "2017-01-07"


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def matches():
    return baseline.load_matches()


@pytest.fixture(scope="module")
def played(matches):
    return sort_for_walk_forward(matches.loc[matches["played"]])


@pytest.fixture(scope="module")
def fit_env(played):
    anchor = anchor_mod.Anchor(played, freeze.frozen_elo_config())
    store = epl_fit.build_store(played)
    return anchor, store


# ==========================================================================
# 1. OFF is inert
# ==========================================================================
def test_off_config_is_byte_identical():
    """The gated config, with nothing on, IS the frozen config."""
    frozen = freeze.frozen_wcmodel_config()
    gated = improve.wcmodel_config(OFF)
    assert json.dumps(gated, sort_keys=True, default=str) == \
        json.dumps(frozen, sort_keys=True, default=str)
    assert "epl_improvements" not in gated


def test_off_leaves_no_token_in_the_cache_keyed_blocks():
    """A token in ``elo``/``windows`` would silently invalidate the panel cache."""
    on = improve.wcmodel_config(Improvements(home_term_blend=0.5))
    frozen = freeze.frozen_wcmodel_config()
    assert on["elo"] == frozen["elo"]
    assert on["windows"] == frozen["windows"]
    assert on["epl_improvements"]["spec"].startswith("epl.improve/")


def test_off_cadence_is_the_preregistered_one():
    assert improve.cadence_weeks(OFF) == walkforward.CADENCE_WEEKS == 1
    assert improve.cadence_weeks(Improvements(refit_cadence_weeks=4)) == 4


def test_off_cutoff_schedule_is_identical(played):
    a = walkforward.matchweek_cutoffs(
        played, score_seasons=windows.TUNE_SCORED,
        cadence=improve.cadence_weeks(OFF))
    b = walkforward.matchweek_cutoffs(played, score_seasons=windows.TUNE_SCORED)
    assert [c.key for c in a] == [c.key for c in b]
    assert [c.match_ids for c in a] == [c.match_ids for c in b]


class _SpyPosterior:
    """Records exactly how the Forecaster called through to the posterior."""

    def __init__(self):
        self.calls = []
        self.provisional_teams = {"prov_club"}
        self._cfg = {"widening": {"mechanism": "c", "strength": 0.5}}

    def predict_1x2(self, home, away, neutral=False, covariates=None):
        self.calls.append({"home": home, "away": away, "neutral": neutral,
                           "covariates": covariates,
                           "strength": self._cfg["widening"]["strength"],
                           "provisional": set(self.provisional_teams)})
        return {"home": 0.5, "draw": 0.3, "away": 0.2}


def test_off_forecaster_makes_the_bare_call():
    """With the gates off, the Forecaster IS ``post.predict_1x2(h, a, False)``."""
    post = _SpyPosterior()
    fc = improve.Forecaster(post, OFF, TUNE_CUTOFF)
    fc.predict_1x2("ars", "che", date="2017-01-07")
    assert post.calls == [{"home": "ars", "away": "che", "neutral": False,
                           "covariates": None, "strength": 0.5,
                           "provisional": {"prov_club"}}]


@pytest.mark.slow
def test_off_end_to_end_is_bit_identical(played, fit_env):
    """THE test. Two real fits, identical probabilities, ``array_equal``."""
    anchor, store = fit_env
    frozen = freeze.frozen_wcmodel_config()
    fixtures = epl_fit.next_matchweek(played, TUNE_CUTOFF, 10)
    pairs = list(zip(fixtures["home_key"].astype(str),
                     fixtures["away_key"].astype(str)))

    with epl_fit.config_read_once(frozen):
        base_post, _ = dcfit.fit_epl(TUNE_CUTOFF, store, anchor, frozen,
                                     matches=played,
                                     feature_cache_dir=paths.FIT_CACHE_DIR)
        a = np.array([[base_post.predict_1x2(h, w)[k] for k in
                       ("home", "draw", "away")] for h, w in pairs])

        gated_cfg = improve.wcmodel_config(OFF)
        fc, _ = improve.fit_improved(TUNE_CUTOFF, store, anchor, gated_cfg, OFF,
                                     matches=played,
                                     feature_cache_dir=paths.FIT_CACHE_DIR)
        b = np.array([[fc.predict_1x2(h, w, date=TUNE_CUTOFF)[k] for k in
                       ("home", "draw", "away")] for h, w in pairs])

    assert np.array_equal(a, b), (
        "the OFF path moved the forecast; max |diff| = "
        f"{np.max(np.abs(a - b))}")


# ==========================================================================
# 2. validation
# ==========================================================================
@pytest.mark.parametrize("kwargs", [
    {"decay_half_life_days": 0.0},
    {"decay_half_life_days": -30.0},
    {"refit_cadence_weeks": 0},
    {"break_widen_strength": 1.5},
    {"break_widen_strength": -0.1},
    {"break_widen_half_life_matches": 0.0},
    {"home_term_blend": 1.2},
    {"home_term_half_life_days": 0.0},
])
def test_bad_parameters_raise(kwargs):
    with pytest.raises(ValueError):
        Improvements(**kwargs)


def test_enabled_and_spec_round_trip():
    imp = Improvements(decay_half_life_days=180.0, refit_cadence_weeks=2,
                       break_widen_strength=0.25, break_widen_january=True,
                       home_term_blend=0.5, congestion=True)
    assert imp.enabled == ("i1a", "i1b", "i2", "i3", "i4")
    assert not imp.is_off()
    assert Improvements.from_dict(imp.as_dict()) == imp
    assert "decay=180d" in imp.spec and "congestion" in imp.spec
    assert OFF.spec == "off" and OFF.enabled == ()
    assert OFF.is_off()


# ==========================================================================
# 3. I1a / I1b — recency and cadence
# ==========================================================================
def test_decay_gate_writes_the_half_life_and_flips_the_panel_key(fit_env):
    """The half-life reaches the panel, and the panel cache knows it changed."""
    from wcmodel.data.features import _build_cache_key

    _, store = fit_env
    off = improve.wcmodel_config(OFF)
    on = improve.wcmodel_config(Improvements(decay_half_life_days=180.0))
    assert off["windows"]["decay_half_life_days"] == 365.0
    assert on["windows"]["decay_half_life_days"] == 180.0
    assert _build_cache_key(TUNE_CUTOFF, store, off) != \
        _build_cache_key(TUNE_CUTOFF, store, on)


def test_decay_gate_actually_reweights_the_training_panel(fit_env):
    """Halving the half-life must down-weight old matches, not just the config."""
    from wcmodel.data import features as wc_features
    from wcmodel.model.panel import to_match_panel

    _, store = fit_env
    out = {}
    for imp in (OFF, Improvements(decay_half_life_days=120.0)):
        cfg = improve.wcmodel_config(imp)
        with epl_fit.config_read_once(cfg):
            mp = to_match_panel(wc_features.build_cached(
                TUNE_CUTOFF, store, cfg, cache_dir=paths.FIT_CACHE_DIR))
        out[imp.spec] = mp.sort_values("match_id")["weight"].to_numpy()
    fast = out["epl.improve/decay=120d"]
    slow = out["off"]
    assert (fast <= slow + 1e-12).all(), "a shorter half-life cannot up-weight"
    assert fast.mean() < slow.mean() * 0.75


def test_cadence_gate_groups_matchweeks(played):
    one = walkforward.matchweek_cutoffs(played, windows.TUNE_SCORED, cadence=1)
    four = walkforward.matchweek_cutoffs(played, windows.TUNE_SCORED, cadence=4)
    assert len(four) < len(one)
    # every fixture is still priced exactly once, by construction of the schedule
    assert sorted(m for c in four for m in c.match_ids) == \
        sorted(m for c in one for m in c.match_ids)


# ==========================================================================
# 4. I2 — the break clock and the widening composition
# ==========================================================================
def _toy_matches() -> pd.DataFrame:
    rows = []
    for season, start in (("2016/17", "2016-08-13"), ("2017/18", "2017-08-12")):
        d = pd.Timestamp(start)
        for i in range(20):                      # 20 rounds, fortnightly: the
            day = d + pd.Timedelta(weeks=i * 2)  # season spans August to May
            rows.append({"season": season, "date": day, "kickoff": day,
                         "home_key": "a", "away_key": "b", "fthg": 1,
                         "ftag": 0, "played": True,
                         "match_id": f"{season}-{i}"})
    return pd.DataFrame(rows)


def test_break_clock_resets_at_a_season_opening():
    m = _toy_matches()
    clock = improve.BreakClock(m, january=False)
    assert clock.matches_since_break("a", "2016-08-13") == 0     # opening day
    assert clock.matches_since_break("a", "2016-08-14") == 1
    assert clock.matches_since_break("a", "2016-09-24") == 3
    assert clock.matches_since_break("a", "2017-05-01") == 19    # late season
    assert clock.matches_since_break("a", "2017-08-12") == 0     # new season
    assert clock.matches_since_break("a", "2017-08-13") == 1


def test_break_clock_resets_again_in_february_when_asked():
    m = _toy_matches()
    no_jan = improve.BreakClock(m, january=False)
    with_jan = improve.BreakClock(m, january=True)
    cutoff = "2017-03-01"
    assert no_jan.matches_since_break("a", cutoff) > \
        with_jan.matches_since_break("a", cutoff)


def test_break_strength_decays_and_is_zero_when_off():
    m = _toy_matches()
    clock = improve.BreakClock(m, january=False)
    imp = Improvements(break_widen_strength=0.4,
                       break_widen_half_life_matches=3.0)
    assert clock.matches_since_break("a", "2016-09-24") == 3
    assert clock.strength("a", "2016-08-13", imp) == pytest.approx(0.4)
    assert clock.strength("a", "2016-09-24", imp) == pytest.approx(0.2)
    assert clock.strength("a", "2016-08-13", OFF) == 0.0


def test_unknown_club_reads_zero_matches_since_its_break():
    """A promoted club has no history, which is the maximally uncertain state."""
    clock = improve.BreakClock(_toy_matches(), january=False)
    assert clock.matches_since_break("never_seen", "2017-01-01") == 0


def test_widening_composition_is_exact_on_a_real_grid():
    """Two mixes in sequence == one mix at ``1 - (1-s1)(1-s2)``, to float."""
    from wcmodel.model.widening import inflate_predictive

    rng = np.random.default_rng(7)
    g = rng.random((9, 9)) ** 3
    g /= g.sum()
    s1, s2 = 0.3, 0.45
    seq = inflate_predictive(inflate_predictive(g, is_provisional=True,
                                                strength=s1),
                             is_provisional=True, strength=s2)
    one = inflate_predictive(g, is_provisional=True,
                             strength=improve.combine_widening(s1, s2))
    assert np.allclose(seq, one, atol=1e-12, rtol=0)
    assert improve.combine_widening(0.0, 0.0) == 0.0
    assert improve.combine_widening(0.5, 0.0) == pytest.approx(0.5)


def test_widening_rejects_a_weight_outside_the_unit_interval():
    with pytest.raises(ValueError):
        improve.combine_widening(1.4)


def test_forecaster_forces_one_inflation_at_the_combined_strength():
    post = _SpyPosterior()
    clock = improve.BreakClock(_toy_matches(), january=False)
    imp = Improvements(break_widen_strength=0.4,
                       break_widen_half_life_matches=3.0)
    fc = improve.Forecaster(post, imp, "2016-08-13", clock=clock)
    fc.predict_1x2("prov_club", "b")
    call = post.calls[-1]
    # prov_club is base-provisional (0.5) AND at k=0 (0.4) -> 1-(0.5)(0.6)=0.7
    assert call["strength"] == pytest.approx(0.7)
    assert call["provisional"] == {"prov_club", "b"}
    # and the posterior is restored afterwards
    assert post._cfg["widening"]["strength"] == 0.5
    assert post.provisional_teams == {"prov_club"}


def test_forecaster_refuses_i2_under_mechanism_a():
    post = _SpyPosterior()
    post._cfg["widening"]["mechanism"] = "a"
    with pytest.raises(ValueError, match="mechanism"):
        improve.Forecaster(post, Improvements(break_widen_strength=0.3),
                           "2016-08-13", clock=improve.BreakClock(_toy_matches()))


def test_forecaster_does_not_mutate_the_shared_config():
    """The strength swap must not reach the config other fits are reading."""
    shared = {"widening": {"mechanism": "c", "strength": 0.5}}
    post = _SpyPosterior()
    post._cfg = shared
    fc = improve.Forecaster(post, Improvements(break_widen_strength=0.4),
                            "2016-08-13",
                            clock=improve.BreakClock(_toy_matches()))
    fc.predict_1x2("a", "b")
    assert shared["widening"]["strength"] == 0.5
    assert fc.post._cfg is not shared


# ==========================================================================
# 5. I3 — the home term
# ==========================================================================
def test_home_term_recovers_a_planted_home_edge():
    n = 400
    rng = np.random.default_rng(3)
    true = 0.25
    lam_h = np.exp(0.15 + true)
    lam_a = np.exp(0.15)
    m = pd.DataFrame({
        "date": pd.date_range("2015-01-01", periods=n, freq="3D"),
        "fthg": rng.poisson(lam_h, n), "ftag": rng.poisson(lam_a, n)})
    got = improve.home_term(m, "2019-01-01", half_life_days=100_000.0)
    assert got == pytest.approx(true, abs=0.05)


def test_home_term_uses_only_pre_cutoff_matches():
    m = pd.DataFrame({"date": pd.to_datetime(["2018-01-01", "2018-06-01"]),
                      "fthg": [3, 0], "ftag": [1, 9]})
    early = improve.home_term(m, "2018-03-01", 365.0)
    both = improve.home_term(m, "2018-12-01", 365.0)
    assert early == pytest.approx(np.log(3.0) - np.log(1.0))
    assert both < early


def test_home_term_shift_is_zero_when_the_gate_is_off(played):
    assert improve.home_term_shift(played, "2018-01-06", OFF, 365.0) == 0.0


def test_home_term_shift_sees_the_closed_doors_season(played):
    """2020/21 was played behind closed doors; a fast window must notice.

    This reads a SCORING season's dates, which is legitimate: it asserts the
    estimator's behaviour on a documented, published fact about the league (the
    38% home-win rate of 2020/21), not a model score. No forecast is produced
    and nothing is tuned here.
    """
    imp = Improvements(home_term_blend=1.0, home_term_half_life_days=90.0)
    mid = improve.home_term_shift(played, "2021-03-01", imp, 365.0)
    assert mid < 0.0, "a fast window should read a LOWER home edge in 2020/21"


def test_home_shifted_posterior_moves_only_home_adv():
    """Built on a real ``Posterior`` so the ``_post`` chain is the real one."""
    import arviz as az
    from wcmodel.model.posterior import Posterior

    idata = az.from_dict({"posterior": {
        "home_adv": np.array([[0.2, 0.3, 0.4]]),
        "mu": np.array([[0.1, 0.15, 0.2]])}})
    base = dcfit.ColdStartPosterior(
        Posterior(idata, ["a", "b"], "dixon_coles",
                  config=freeze.frozen_wcmodel_config()), {})
    shifted = improve.HomeShiftedPosterior(base, 0.05)
    assert np.allclose(shifted._post("home_adv"), [0.25, 0.35, 0.45])
    assert np.allclose(shifted._post("mu"), base._post("mu"))
    assert np.array_equal(improve.HomeShiftedPosterior(base, 0.0)._post("home_adv"),
                          base._post("home_adv"))
    assert shifted.teams == base.teams
    assert shifted.idata is base.idata


# ==========================================================================
# 6. I4 — congestion
# ==========================================================================
def test_congestion_gate_enables_exactly_rest_days():
    cfg = improve.wcmodel_config(Improvements(congestion=True))
    assert cfg["model"]["covariates"]["enabled"] == ["rest_days"]
    assert improve.wcmodel_config(OFF)["model"]["covariates"]["enabled"] == []


def test_dcfit_still_refuses_a_covariate_with_no_epl_analogue(fit_env, played):
    anchor, store = fit_env
    cfg = freeze.frozen_wcmodel_config()
    cfg["model"]["covariates"]["enabled"] = ["travel_km"]
    with pytest.raises(NotImplementedError, match="travel_km"):
        dcfit.fit_epl(TUNE_CUTOFF, store, anchor, cfg, matches=played)


def test_rest_schedule_matches_the_hand_computation(played):
    rest = improve.RestSchedule(played)
    cutoff = pd.Timestamp("2017-01-07")
    d = pd.to_datetime(played["date"]).dt.normalize()
    club = str(played["home_key"].iloc[0])
    prior = d.loc[((played["home_key"] == club) | (played["away_key"] == club))
                  & (d < cutoff)]
    want = int((cutoff - prior.max()).days)
    got = rest.covariates(club, "opponent_that_does_not_exist", cutoff, cutoff)
    assert got["rest_days"] == want
    assert np.isnan(got["rest_days__away"])


def test_rest_schedule_cannot_see_past_the_cutoff(played):
    """Rewrite every post-cutoff date; the pre-cutoff answer must not move.

    The corruption keeps the rewritten matches in the FUTURE (it shifts them
    further out) — moving them before the cutoff would fabricate pre-cutoff
    evidence and test nothing. The positive control at a later cutoff proves the
    rewrite really landed, so a canary that changed nothing cannot pass.
    """
    cutoff = pd.Timestamp("2017-01-07")
    club = str(played["home_key"].iloc[0])
    dirty_frame = played.copy()
    after = pd.to_datetime(dirty_frame["date"]) >= cutoff
    dirty_frame.loc[after, "date"] = (
        pd.to_datetime(dirty_frame.loc[after, "date"]) + pd.Timedelta(days=37))
    clean, dirty = improve.RestSchedule(played), improve.RestSchedule(dirty_frame)

    assert clean.covariates(club, "x", cutoff, cutoff)["rest_days"] == \
        dirty.covariates(club, "x", cutoff, cutoff)["rest_days"]
    later = pd.Timestamp("2017-06-01")
    assert clean.covariates(club, "x", later, later)["rest_days"] != \
        dirty.covariates(club, "x", later, later)["rest_days"], \
        "positive control: the rewrite must be visible AFTER the cutoff"


@pytest.mark.slow
def test_congestion_gate_produces_a_beta_and_moves_the_forecast(played, fit_env):
    """The gate has to reach the model, not just the config dict."""
    anchor, store = fit_env
    imp = Improvements(congestion=True)
    cfg = improve.wcmodel_config(imp)
    rest = improve.RestSchedule(played)
    with epl_fit.config_read_once(cfg):
        fc, _ = improve.fit_improved(TUNE_CUTOFF, store, anchor, cfg, imp,
                                     matches=played, rest=rest,
                                     feature_cache_dir=paths.FIT_CACHE_DIR)
    assert "rest_days" in fc.post.covariate_transforms
    assert "beta_rest_days" in fc.post.idata.posterior
    h, a = str(played["home_key"].iloc[0]), str(played["away_key"].iloc[0])
    if h in fc.post._idx and a in fc.post._idx:
        with_cov = fc.predict_1x2(h, a, date=TUNE_CUTOFF)
        without = fc.post.predict_1x2(h, a, neutral=False)
        assert any(abs(with_cov[k] - without[k]) > 0 for k in with_cov)


# ==========================================================================
# 7. the window guard
# ==========================================================================
def test_the_confirmatory_window_needs_an_explicit_second_look():
    with pytest.raises(ValueError, match="SECOND LOOK"):
        improve._resolve_seasons("confirm", second_look=False, holdout=False)
    assert improve._resolve_seasons("confirm", True, False) == \
        windows.SCORE_SEASONS


def test_the_holdout_needs_an_explicit_flag():
    with pytest.raises(ValueError, match="holdout"):
        improve._resolve_seasons("holdout", second_look=False, holdout=False)
    assert improve._resolve_seasons("holdout", False, True) == \
        windows.EXCLUDED_SEASONS


def test_the_tuning_window_is_the_default():
    assert improve._resolve_seasons("tune", False, False) == windows.TUNE_SCORED
    with pytest.raises(ValueError):
        improve._resolve_seasons("nonsense", False, False)


def test_i5_record_is_a_verdict_not_a_todo():
    assert improve.I5_FEASIBILITY["verdict"] == "FEASIBLE, NOT ADOPTED"
    assert improve.I5_FEASIBILITY["licence"] == "CC0"
    assert sum(improve.I5_FEASIBILITY["date_precision"].values()) == \
        improve.I5_FEASIBILITY["spells_since_2014_06_01"]
    assert "P286" in improve.I5_WIKIDATA_QUERY


def test_the_excluded_season_guard_still_defaults_to_closed(played):
    """``allow_excluded`` must be opt-in: the default schedule still refuses."""
    with pytest.raises(ValueError, match="excluded season"):
        walkforward.matchweek_cutoffs(played, windows.EXCLUDED_SEASONS)
    cuts = walkforward.matchweek_cutoffs(played, windows.EXCLUDED_SEASONS,
                                         allow_excluded=True)
    assert sum(len(c.match_ids) for c in cuts) == 380


def test_i3_without_a_match_frame_raises(fit_env):
    anchor, store = fit_env
    imp = Improvements(home_term_blend=0.5)
    with pytest.raises(ValueError, match="matches="):
        improve.fit_improved(TUNE_CUTOFF, store, anchor,
                             improve.wcmodel_config(imp), imp, matches=None)


def test_i4_without_a_fixture_date_raises():
    post = _SpyPosterior()
    fc = improve.Forecaster(post, Improvements(congestion=True), TUNE_CUTOFF,
                            rest=improve.RestSchedule(_toy_matches()))
    with pytest.raises(ValueError, match="DATE"):
        fc.predict_1x2("a", "b", date=None)


def test_missing_helpers_are_refused_up_front():
    with pytest.raises(ValueError, match="BreakClock"):
        improve.Forecaster(_SpyPosterior(),
                           Improvements(break_widen_strength=0.2), TUNE_CUTOFF)
    with pytest.raises(ValueError, match="RestSchedule"):
        improve.Forecaster(_SpyPosterior(), Improvements(congestion=True),
                           TUNE_CUTOFF)
