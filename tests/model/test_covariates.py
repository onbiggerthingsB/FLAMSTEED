import numpy as np
import pytensor
import pytest
from wcmodel.config import load_config
from wcmodel.model.scoreline import DesignData, DixonColesModel


def test_config_has_covariate_block_with_defaults():
    cov = load_config()["model"]["covariates"]
    assert cov["enabled"] == []                      # OFF by default: baseline is unchanged
    assert cov["beta_scale"] == 0.25                 # tight regularizing prior on each coefficient
    assert cov["host_k"] == 0.5                       # host magnitude default (Q2)
    assert cov["missing_indicator_for"] == ["travel_km", "altitude_m"]  # Q1


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
