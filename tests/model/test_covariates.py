import numpy as np
from wcmodel.config import load_config
from wcmodel.model.scoreline import DesignData


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
    train = np.array([2.0, 4.0, 6.0, np.nan])        # mean_obs=4, sd_obs=2 (ddof=0 over observed)
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
