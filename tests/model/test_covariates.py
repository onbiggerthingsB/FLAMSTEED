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
