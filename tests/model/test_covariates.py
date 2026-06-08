import numpy as np
import pytensor
import pytest
from wcmodel.config import load_config
from wcmodel.model.scoreline import DesignData, DixonColesModel
from wcmodel.data.tournament import HOST_COUNTRY_BY_TEAM


def test_config_has_covariate_block_with_defaults():
    cov = load_config()["model"]["covariates"]
    assert cov["enabled"] == []                      # OFF by default: baseline is unchanged
    assert cov["beta_scale"] == 0.25                 # tight regularizing prior on each coefficient
    assert cov["host_k"] == 0.5                       # host magnitude default (Q2)
    assert cov["missing_indicator_for"] == ["travel_km", "altitude_m"]  # Q1


def test_config_hosts_field_matches_the_host_country_constant():
    # CONVERGENCE-REVIEW GUARD (dead-config drift): host detection in
    # data/tournament.py keys on the HOST_COUNTRY_BY_TEAM constant, NOT on the
    # config `hosts` list (only host_k is read from config). Pin the two together so
    # the config field is load-bearing — a future edit that drifts the config from
    # the code constant fails CI — rather than silently inert.
    cfg_hosts = set(load_config()["model"]["covariates"]["hosts"])
    assert cfg_hosts == set(HOST_COUNTRY_BY_TEAM), (
        "config covariates.hosts must match HOST_COUNTRY_BY_TEAM keys "
        f"(config={sorted(cfg_hosts)}, constant={sorted(HOST_COUNTRY_BY_TEAM)})"
    )


def test_covariates_stay_disabled_until_the_sim_threads_them():
    # CONVERGENCE-REVIEW TRIPWIRE (sim covariate-blindness): the Monte-Carlo sim
    # (sim/scoreline.py::RateBook.rates) threads ONLY host_factor, never the
    # covariate offset (the whole sim/ tree has zero covariate references). So
    # enabling ANY covariate would make the dashboard per-fixture cards (which DO
    # apply covariates via fixtures.fixture_forecast) DISAGREE with the champion/
    # advance progression numbers (from the sim). The SHIPPED default must stay
    # enabled:[] until the sim threads covariates (see ASSUMPTIONS "pre-enable
    # requirement"). NOTE: the ablation sets enabled per-arm at runtime via
    # _arm_config and scores via predict_1x2 (NOT the sim), so it is unaffected by
    # this guard. Do NOT delete this test to enable a covariate — thread the sim first.
    assert load_config()["model"]["covariates"]["enabled"] == []


def test_designdata_accepts_optional_covariates_defaulting_empty():
    # Construct a COMPLETE DesignData: every original field stays required —
    # cov/cov_mask are the only new (defaulted) fields, so omitting them must
    # still yield empty dicts without weakening the production dataclass.
    d = DesignData(
        home_idx=np.array([0]), away_idx=np.array([1]),
        home_goals=np.array([1]), away_goals=np.array([0]),
        neutral=np.array([False]), n_teams=2,
        teams=["A", "B"], weight=np.array([1.0]),
        home_provisional=np.array([False]), away_provisional=np.array([False]),
    )
    assert d.cov == {}                               # no covariates -> exactly today's model
    assert d.cov_mask == {}


from wcmodel.model.covariates import CovariateTransform


def test_transform_standardizes_on_observed_and_masks_missing_to_zero():
    train = np.array([2.0, 4.0, 6.0, np.nan])        # mean_obs=4; ddof=1 (sample std) -> sd=2.0
    t = CovariateTransform.fit("rest_days", train)
    assert abs(t.mean - 4.0) < 1e-9 and abs(t.sd - 2.0) < 1e-9
    z, mask = t.apply(np.array([4.0, 6.0, np.nan]))
    assert np.allclose(z, [0.0, 1.0, 0.0])           # 4->0, 6->+1, NaN-> masked 0 (NOT imputed to a value)
    assert np.allclose(mask, [1.0, 1.0, 0.0])


def test_transform_degenerate_sd_is_safe():
    t = CovariateTransform.fit("x", np.array([3.0, 3.0, 3.0]))   # sd=0
    z, mask = t.apply(np.array([3.0, np.nan]))
    assert np.allclose(z, [0.0, 0.0]) and np.allclose(mask, [1.0, 0.0])   # zero-variance -> no signal, no div0


def test_transform_all_missing_yields_all_masked():
    t = CovariateTransform.fit("x", np.array([np.nan, np.nan]))
    z, mask = t.apply(np.array([np.nan, 1.0]))
    assert np.allclose(mask, [0.0, 0.0])             # never observed in train -> never trusted at predict
    assert np.all(np.isfinite(z))                    # z must be finite, not inf/nan...
    assert np.all(z == 0.0)                          # ...and an exact zero contribution


def test_transform_single_observed_has_no_signal_and_is_finite():
    t = CovariateTransform.fit("x", np.array([7.0]))     # one observed row -> no spread
    assert t.sd == 0.0
    z, mask = t.apply(np.array([7.0, np.nan]))
    assert np.allclose(mask, [1.0, 0.0])             # the lone row is "observed" but...
    assert np.all(np.isfinite(z)) and np.all(z == 0.0)   # ...sd=0 -> zero signal, no NaN


def test_apply_is_always_finite_and_bounded():
    # 1) Overflowing-but-finite train input: mean/sd overflow to inf -> NO SIGNAL.
    t = CovariateTransform.fit("x", np.array([1e200, -1e200, 3e200]))
    z, mask = t.apply(np.array([1e200, -1e200, 3e200]))
    assert np.all(np.isfinite(z)) and np.all(np.abs(z) <= 10.0)   # never inf/nan, bounded
    assert np.all(mask == 0.0)                                    # untrustworthy -> masked

    # 2) Near-constant train (tiny positive sd) -> enormous z would overflow exp(rate);
    #    the 10-sigma clamp keeps apply() finite + bounded instead of blowing up.
    t2 = CovariateTransform.fit("x", np.array([5.0, 5.0 + 1e-13, 5.0]))
    z2, _ = t2.apply(np.array([5.0]))
    assert np.all(np.isfinite(z2)) and np.all(np.abs(z2) <= 10.0)


# ---- T2: masked covariate terms in the scoreline log-rate ----
#
# Both DesignData below pass EVERY required field (home_idx/away_idx/home_goals/
# away_goals/neutral/n_teams/teams/weight/home_provisional/away_provisional) —
# the frozen dataclass has no defaults for those — plus cov/cov_mask. The plan's
# snippets predate that signature; these constructors are the adapted form.


def test_rates_add_rest_term_to_attacking_rate():
    # Two matches; team0 has +1 sd rest at home in match0. With an enabled
    # rest_days covariate a beta coefficient is added to the model.
    d = DesignData(
        home_idx=np.array([0, 1]), away_idx=np.array([1, 0]),
        home_goals=np.array([1, 0]), away_goals=np.array([0, 1]),
        neutral=np.array([False, False]), n_teams=2,
        teams=["A", "B"], weight=np.ones(2),
        home_provisional=np.zeros(2, bool), away_provisional=np.zeros(2, bool),
        cov={"rest_days": np.array([1.0, 0.0]),
             "rest_days__away": np.array([0.0, 1.0])},
        cov_mask={"rest_days": np.array([1.0, 1.0]),
                  "rest_days__away": np.array([1.0, 1.0])},
    )
    cfg = load_config()
    cfg["model"]["covariates"]["enabled"] = ["rest_days"]
    m = DixonColesModel().build(d, weight=np.ones(2), config=cfg)
    names = {v.name for v in m.free_RVs}
    assert "beta_rest_days" in names   # a coefficient was added for the enabled covariate


# ---- T2 hardening (Codex): the rest term is NON-VACUOUS ----
#
# The existence check above proves only that a beta_rest_days RV exists — it does
# NOT prove the covariate actually reaches the rate / the likelihood. These two
# tests pin that: we compile the `like` POTENTIAL tensor on its own (a function of
# the model's free RVs) and evaluate it at two beta values while holding att/def/
# mu/home_adv/rho FIXED at identical values. Because the `like` Potential is built
# only from the rate→likelihood path, the beta_rest_days PRIOR (a separate logp
# term) is NOT inside it — so any change in `like` must come from the covariate
# entering the LIKELIHOOD, not from the prior. mask==1 -> `like` MUST change;
# mask==0 (missing) -> `like` MUST be invariant (exactly zero contribution).


def _build_rest_model(mask_val):
    # One std-unit of HOME rest in match0, zero away contribution, so a non-zero
    # beta moves the home attacking rate (hence the DC likelihood) in match0.
    # mask_val toggles observed (1.0) vs missing (0.0) for the rest_days arrays.
    d = DesignData(
        home_idx=np.array([0, 1]), away_idx=np.array([1, 0]),
        home_goals=np.array([3, 0]), away_goals=np.array([0, 1]),
        neutral=np.array([False, False]), n_teams=2,
        teams=["A", "B"], weight=np.ones(2),
        home_provisional=np.zeros(2, bool), away_provisional=np.zeros(2, bool),
        cov={"rest_days": np.array([1.5, 0.0]),
             "rest_days__away": np.array([0.0, 0.0])},
        cov_mask={"rest_days": np.array([mask_val, mask_val]),
                  "rest_days__away": np.array([mask_val, mask_val])},
    )
    cfg = load_config()
    cfg["model"]["covariates"]["enabled"] = ["rest_days"]
    return DixonColesModel().build(d, weight=np.ones(2), config=cfg)


def _like_evaluator(m):
    """Return a fn(beta) -> float value of ONLY the `like` Potential, with every
    other RV held at a fixed reference point. Isolates the likelihood from the
    beta prior: the prior is a separate logp term, never part of this tensor."""
    like = m["like"]
    rvs = {v.name: v for v in m.free_RVs}
    fn = pytensor.function(list(rvs.values()), like, on_unused_input="ignore")
    order = list(rvs.keys())

    def at(beta):
        fixed = dict(
            sigma_att=np.array(1.0), sigma_def=np.array(1.0),
            att_raw=np.array([0.1, -0.1]), def_raw=np.array([0.05, -0.05]),
            mu=np.array(0.0), home_adv=np.array(0.2),
            beta_rest_days=np.array(float(beta)), rho=np.array(0.0),
        )
        return float(fn(*[fixed[k] for k in order]))

    return at


def test_rest_term_enters_the_likelihood_when_observed():
    # mask==1: the covariate is observed, so changing beta_rest_days (holding all
    # other RVs fixed) MUST change the `like` Potential — proving the term reaches
    # the LIKELIHOOD, not just the prior. Fast: graph eval, no NUTS.
    at = _like_evaluator(_build_rest_model(mask_val=1.0))
    base, moved = at(0.0), at(0.5)
    assert abs(moved - base) > 1e-6   # the covariate term enters the rate/likelihood


def test_rest_term_is_exactly_zero_in_the_likelihood_when_missing():
    # mask==0: identical setup but the rest_days rows are MISSING. The `like`
    # Potential MUST be invariant to beta_rest_days — masked rows contribute
    # EXACTLY zero to the likelihood (no imputation), the complement of the
    # observed case above.
    at = _like_evaluator(_build_rest_model(mask_val=0.0))
    assert at(0.5) == at(0.0)   # missing -> exactly zero contribution, bit-for-bit


# ---- T2 hardening (Codex): taxonomy + per-team both-sides guards ----


def _designdata_with_cov(cov, cov_mask):
    return DesignData(
        home_idx=np.array([0, 1]), away_idx=np.array([1, 0]),
        home_goals=np.array([1, 0]), away_goals=np.array([0, 1]),
        neutral=np.array([False, False]), n_teams=2,
        teams=["A", "B"], weight=np.ones(2),
        home_provisional=np.zeros(2, bool), away_provisional=np.zeros(2, bool),
        cov=cov, cov_mask=cov_mask,
    )


def test_undeclared_covariate_raises_not_silently_per_match():
    # FIX 1: an enabled covariate present in d.cov but absent from BOTH
    # _PER_TEAM_COVS and _PER_MATCH_COVS must FAIL LOUD — never silently fall into
    # the per-match (symmetric) branch as if it were declared.
    d = _designdata_with_cov(
        cov={"mystery_feature": np.array([1.0, 0.0])},
        cov_mask={"mystery_feature": np.array([1.0, 1.0])},
    )
    cfg = load_config()
    cfg["model"]["covariates"]["enabled"] = ["mystery_feature"]
    with pytest.raises(ValueError, match="unknown covariate 'mystery_feature'"):
        DixonColesModel().build(d, weight=np.ones(2), config=cfg)


def test_per_team_covariate_missing_away_side_raises_early():
    # FIX 3: a per-team covariate must supply BOTH the home array/mask and the
    # '__away' array/mask. A caller that omits the away side fails clearly at
    # build time, not with a deep KeyError later inside _cov_offset.
    d = _designdata_with_cov(
        cov={"rest_days": np.array([1.0, 0.0])},          # no rest_days__away
        cov_mask={"rest_days": np.array([1.0, 1.0])},
    )
    cfg = load_config()
    cfg["model"]["covariates"]["enabled"] = ["rest_days"]
    with pytest.raises(ValueError, match="missing its '__away'"):
        DixonColesModel().build(d, weight=np.ones(2), config=cfg)


def test_enabled_empty_adds_no_covariate_params():
    d = DesignData(
        home_idx=np.array([0]), away_idx=np.array([1]),
        home_goals=np.array([1]), away_goals=np.array([0]),
        neutral=np.array([False]), n_teams=2,
        teams=["A", "B"], weight=np.ones(1),
        home_provisional=np.zeros(1, bool), away_provisional=np.zeros(1, bool),
    )
    m = DixonColesModel().build(d, weight=np.ones(1), config=load_config())
    assert not any(v.name.startswith("beta_") for v in m.free_RVs)   # baseline unchanged


# ---- T3: fit() builds + persists the transform; threads cov into the design ----
#
# NOTE (real signature): the plan snippet calls fit(small_features, cutoff=...);
# the SHIPPED fit is fit(cutoff, store, *, backend, draws, seed, advi_iters,
# config) and reads features.build(cutoff, store, cfg) internally. The small_store
# fixture's features panel carries a rest_days column, so we enable rest_days and
# pass the store. ADVI keeps it fast; still a real end-to-end fit -> slow.


def test_panel_carries_per_team_covariate_home_and_away_columns(small_store):
    # to_match_panel must carry rest_days (home team's value) and rest_days__away
    # (the away team's OWN value) onto each match row. Fast: no sampling.
    from wcmodel.data import features
    from wcmodel.model.panel import to_match_panel
    mp = to_match_panel(features.build("2024-06-01", small_store, load_config()))
    assert "rest_days" in mp.columns and "rest_days__away" in mp.columns
    # Per-match altitude is identical on both rows -> carried once, no __away.
    assert "altitude_m" in mp.columns and "altitude_m__away" not in mp.columns


@pytest.mark.slow
def test_fit_persists_covariate_transforms_and_uses_them(small_store):
    import copy
    cfg = copy.deepcopy(load_config())
    cfg["model"]["covariates"]["enabled"] = ["rest_days"]    # enable rest_days
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, config=cfg, backend="advi",
               draws=40, advi_iters=500, seed=0)
    assert "rest_days" in post.covariate_transforms          # transform persisted
    assert "beta_rest_days" in post.idata.posterior          # coefficient fitted


@pytest.mark.slow
def test_fit_with_no_covariates_persists_empty_transforms(small_store):
    # enabled == [] (the default): no transform fitted, no beta RV -> the baseline.
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=40,
               advi_iters=500, seed=0)
    assert post.covariate_transforms == {}                   # nothing fitted
    assert "beta_rest_days" not in post.idata.posterior      # no covariate coefficient


# ---- T4: predict consumes per-fixture covariates via the PERSISTED transform ----
#
# NOTE (real signature): the plan snippet calls fit(small_features, cutoff=...);
# the SHIPPED fit is fit(cutoff, store, *, backend, draws, seed, advi_iters,
# config) (mirrored from T3). predict recomputes lh/la from the stacked posterior
# and must add the SAME masked, standardized covariate offset using the PERSISTED
# training transform + the betas READ from idata + this fixture's raw covariate
# values (passed by the caller) — an as-of-cutoff forecast that reflects the
# covariates with NO refit.


@pytest.mark.slow
def test_predict_uses_rest_covariate_monotonically(small_store):
    # Supplying covariates must CHANGE the forecast (non-vacuity) and keep it a
    # proper 1X2 distribution that sums to 1 (integration). Whatever the SIGN of
    # the fitted beta, a different per-fixture rest profile must move the forecast.
    import copy
    cfg = copy.deepcopy(load_config())
    cfg["model"]["covariates"]["enabled"] = ["rest_days"]
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, config=cfg, backend="advi",
               draws=60, advi_iters=800, seed=0)
    teams = list(post._idx)[:2]
    base = post.predict_1x2(teams[0], teams[1], neutral=True)            # no covariates supplied
    rested = post.predict_1x2(teams[0], teams[1], neutral=True,
                              covariates={"rest_days": 9.0, "rest_days__away": 2.0})
    assert abs(rested["home"] - base["home"]) > 1e-6                     # non-vacuity: forecast moved
    assert abs(rested["home"] + rested["draw"] + rested["away"] - 1.0) < 1e-6  # proper distribution


@pytest.mark.slow
def test_predict_covariates_none_is_byte_identical_to_baseline(small_store):
    # covariates=None (the default) must be byte-identical to today's prediction,
    # even when the model carries fitted betas — a covariate is only ever applied
    # when the caller supplies a value for THIS fixture.
    import copy
    cfg = copy.deepcopy(load_config())
    cfg["model"]["covariates"]["enabled"] = ["rest_days"]
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, config=cfg, backend="advi",
               draws=60, advi_iters=800, seed=0)
    teams = list(post._idx)[:2]
    g_default = post.predict_scoreline(teams[0], teams[1], neutral=True)
    g_none = post.predict_scoreline(teams[0], teams[1], neutral=True, covariates=None)
    g_empty = post.predict_scoreline(teams[0], teams[1], neutral=True, covariates={})
    assert np.array_equal(g_default, g_none)                            # None == default
    assert np.array_equal(g_default, g_empty)                          # empty dict == no shift


@pytest.mark.slow
def test_predict_missing_no_indicator_covariate_is_exact_zero_shift(small_store):
    # A NO-miss-indicator covariate (rest_days is NOT in missing_indicator_for):
    # a supplied-but-None covariate value masks to 0 -> EXACTLY no shift, because
    # the term reduces to beta * z * 0 == 0 and there is no beta_rest_days_miss to
    # fire. So a supplied-missing rest_days is byte-identical to supplying nothing.
    # This is the complement of the miss-indicator case below: no indicator -> the
    # only possible contribution is the masked beta*z term, which a missing value
    # zeroes exactly. (Mirrors fit: rest_days has no miss term, so a masked row
    # contributes exactly zero at fit too.)
    import copy
    cfg = copy.deepcopy(load_config())
    cfg["model"]["covariates"]["enabled"] = ["rest_days"]
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, config=cfg, backend="advi",
               draws=60, advi_iters=800, seed=0)
    assert "beta_rest_days_miss" not in post.idata.posterior           # NO miss intercept fitted
    teams = list(post._idx)[:2]
    g_base = post.predict_scoreline(teams[0], teams[1], neutral=True)
    g_none = post.predict_scoreline(teams[0], teams[1], neutral=True,
                                    covariates={"rest_days": None, "rest_days__away": None})
    g_nan = post.predict_scoreline(teams[0], teams[1], neutral=True,
                                   covariates={"rest_days": np.nan, "rest_days__away": np.nan})
    assert np.array_equal(g_base, g_none)                              # None -> exactly zero shift
    assert np.array_equal(g_base, g_nan)                               # NaN  -> exactly zero shift
    # predict_1x2 form too: supplied-missing == covariates=None for a no-indicator cov.
    p_base = post.predict_1x2(teams[0], teams[1], neutral=True, covariates=None)
    p_none = post.predict_1x2(teams[0], teams[1], neutral=True,
                              covariates={"rest_days": None, "rest_days__away": None})
    assert p_base == p_none


@pytest.mark.slow
def test_predict_supplied_missing_miss_indicator_covariate_fires_beta_miss(small_store):
    # FIT/PREDICT CONSISTENCY: a miss-indicator covariate (travel_km IS in
    # missing_indicator_for, so beta_travel_km_miss is fitted) treats a SUPPLIED
    # missing value (NaN / absent) EXACTLY as fit treated a missing-feature match:
    # the per-side term is beta*z*mask + beta_miss*(1-mask), so mask==0 -> the
    # term is beta_miss (NOT zero). Therefore a supplied-missing travel_km MUST
    # MOVE the forecast away from covariates=None (which short-circuits to baseline,
    # adding nothing on either side). This assertion is RED before the fit/predict
    # fix (predict used to early-return 0 for a masked value, dropping beta_miss) —
    # the non-vacuity guard that proves the bug is actually corrected.
    import copy
    cfg = copy.deepcopy(load_config())
    cfg["model"]["covariates"]["enabled"] = ["travel_km"]
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, config=cfg, backend="advi",
               draws=60, advi_iters=800, seed=0)
    assert "beta_travel_km_miss" in post.idata.posterior              # miss intercept WAS fitted
    teams = list(post._idx)[:2]
    g_base = post.predict_scoreline(teams[0], teams[1], neutral=True)  # covariates=None -> baseline
    # SUPPLIED-MISSING on BOTH sides: beta_travel_km_miss fires on home AND away,
    # so the grid must differ from baseline (the miss term is a real, non-zero shift).
    g_nan = post.predict_scoreline(teams[0], teams[1], neutral=True,
                                   covariates={"travel_km": float("nan"),
                                               "travel_km__away": float("nan")})
    assert not np.array_equal(g_base, g_nan)                           # miss term fires -> moved (RED pre-fix)
    p_nan = post.predict_1x2(teams[0], teams[1], neutral=True,
                             covariates={"travel_km": float("nan"),
                                         "travel_km__away": float("nan")})
    assert abs(p_nan["home"] + p_nan["draw"] + p_nan["away"] - 1.0) < 1e-9  # still a proper distribution
    # An OBSERVED travel value ALSO moves the forecast (term reduces to beta*z, the
    # (1-mask)==0 branch zeroes the miss term) — mirrors fit's formula for observed.
    g_obs = post.predict_scoreline(teams[0], teams[1], neutral=True,
                                    covariates={"travel_km": 5000.0})
    assert not np.array_equal(g_base, g_obs)                           # observed value shifts the forecast


# ---- T5: host advantage = k * home_adv for the 2026 hosts' home games ----
#
# host_factor is a PREDICTION-time scalar on the ALREADY-FITTED home_adv: it adds NO
# new fitted parameter (no new RV, no likelihood/identifiability change). The 2026
# hosts (USA/Mexico/Canada) actually play at home, but the dashboard/sim build every
# WC fixture neutral=True, zeroing the fitted home_adv. T5 lets a host's home game
# carry k*home_adv (k from config, default 0.5). host_factor=None (the default) is
# byte-identical to today's predict; the home term is host_factor*home_adv when
# host_factor is not None, else (0 if neutral else home_adv). It COMPOSES with the
# T4 covariate offsets (both add to the home log-rate exponent).


@pytest.mark.slow
def test_host_factor_applies_partial_home_advantage(small_store):
    # The plan's monotonicity gate: neutral (k=0) < host_factor=0.5 < full (k=1) for
    # the home-win prob. With home_adv fitted >= 0 (the home_loc=0.25 prior), a larger
    # multiplier on the home log-rate strictly raises the home-win mass. No covariate
    # is enabled here — this exercises ONLY the host_factor scalar on home_adv.
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=60,
               advi_iters=800, seed=0)
    a, b = list(post._idx)[:2]
    neutral = post.predict_1x2(a, b, neutral=True)["home"]          # k=0: no home term
    full = post.predict_1x2(a, b, neutral=False)["home"]            # k=1 equivalent: full home_adv
    half = post.predict_1x2(a, b, host_factor=0.5)["home"]          # k=0.5: half home_adv
    assert neutral < half < full                                   # 0 < 0.5*home_adv < full home_adv


@pytest.mark.slow
def test_host_factor_one_equals_non_neutral_and_zero_equals_neutral(small_store):
    # host_factor is EXACTLY a scalar on home_adv: k=1.0 reproduces the non-neutral
    # (full home_adv) grid byte-for-byte, and k=0.0 reproduces the neutral grid. This
    # pins host_factor to home_adv with no other moving part (the focal identifiability
    # claim: the only knob is k; home_adv is reused, never re-estimated).
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=60,
               advi_iters=800, seed=0)
    a, b = list(post._idx)[:2]
    g_full = post.predict_scoreline(a, b, neutral=False)
    g_k1 = post.predict_scoreline(a, b, host_factor=1.0)
    g_neutral = post.predict_scoreline(a, b, neutral=True)
    g_k0 = post.predict_scoreline(a, b, host_factor=0.0)
    assert np.array_equal(g_full, g_k1)                            # k=1 == full home_adv
    assert np.array_equal(g_neutral, g_k0)                         # k=0 == neutral


@pytest.mark.slow
def test_host_factor_none_is_byte_identical_to_baseline(small_store):
    # host_factor=None (the default) must be byte-identical to today's predict — the
    # neutral= path is unchanged when no host factor is supplied. This is the no-DOF /
    # no-regression guard: a non-host fixture (host_factor never set) is untouched.
    from wcmodel.model.scoreline import fit
    post = fit("2024-06-01", small_store, backend="advi", draws=60,
               advi_iters=800, seed=0)
    a, b = list(post._idx)[:2]
    g_default = post.predict_scoreline(a, b, neutral=True)
    g_none = post.predict_scoreline(a, b, neutral=True, host_factor=None)
    assert np.array_equal(g_default, g_none)                       # None == today's predict
    p_default = post.predict_1x2(a, b, neutral=True)
    p_none = post.predict_1x2(a, b, neutral=True, host_factor=None)
    assert p_default == p_none


def test_host_home_factor_detection(monkeypatch):
    # FAST host-home detection (no fit): the host-home test is HOME team is a host
    # nation AND the venue's country == that nation. A host playing AWAY, a host at
    # an OUT-OF-COUNTRY venue (USA playing in Mexico), and a non-host all stay neutral
    # (factor is None). Only a host at an in-country venue gets host_k.
    from wcmodel.data.tournament import host_home_factor
    cfg = load_config()
    venue_country = {"Mexico City": "MX", "Atlanta": "US", "Toronto": "CA"}
    k = cfg["model"]["covariates"]["host_k"]
    # Mexico (host) at a Mexican venue -> host-home: k.
    assert host_home_factor("Mexico", "South Africa", "Mexico City", venue_country, cfg) == k
    # USA (host) playing IN Mexico -> NOT host-home (venue country != USA): None.
    assert host_home_factor("United States", "Mexico", "Mexico City", venue_country, cfg) is None
    # Host as the AWAY team at its own venue -> NOT host-home (home team is not host): None.
    assert host_home_factor("South Africa", "Mexico", "Mexico City", venue_country, cfg) is None
    # USA (host) at a US venue -> host-home: k.
    assert host_home_factor("United States", "Brazil", "Atlanta", venue_country, cfg) == k
    # Non-host home team at any venue -> neutral: None.
    assert host_home_factor("Brazil", "Argentina", "Atlanta", venue_country, cfg) is None
    # Unknown venue (no country) -> None (cannot be in-country).
    assert host_home_factor("Mexico", "Brazil", "Nowhere", venue_country, cfg) is None
