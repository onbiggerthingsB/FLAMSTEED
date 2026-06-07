import numpy as np
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
