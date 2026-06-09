"""Task 3 [LOAD-BEARING]: the Elo-anchored att/def prior MEAN, gated.

`_priors(d, p, strength=)` sets the att_raw/def_raw prior MEAN to `k·elo_z` when
`strength_prior.enabled` is True (a strong team -> high att AND high def, both
+k·elo_z); when off the mean is the scalar 0.0 EXACTLY as today (byte-identical).

Step 1/2 assert the RV's mu input directly (fast, decisive). Step 5 proves the
off path is byte-identical to elo_z=zeros via a seeded prior-predictive draw of
`att` (the BEHAVIORAL contract: off ignores elo_z entirely; on discriminates).
"""
import numpy as np
import pandas as pd
import pymc as pm

from wcmodel.model.panel import build_design
from wcmodel.model.scoreline import _priors


def _d(elo_z):
    # full match-panel schema build_design consumes (see panel.to_match_panel)
    mp = pd.DataFrame({"match_id": [1], "date": pd.to_datetime(["2025-06-10"]),
                       "home_team": ["A"], "away_team": ["B"],
                       "home_goals": [1], "away_goals": [0],
                       "neutral": [False], "match_type": ["friendly"],
                       "weight": [1.0], "home_provisional": [False],
                       "away_provisional": [False]})
    return build_design(mp, elo_z=np.array(elo_z))


PRIOR = {"sigma_att": 0.5, "sigma_def": 0.5, "mu_loc": 0.0, "mu_scale": 1.0,
         "home_loc": 0.25, "home_scale": 0.25}


def _normal_mu_input(rv):
    """The Normal ``mu`` argument fed to ``att_raw`` / ``def_raw``.

    DEVIATION (documented in the plan): the plan's literal ``inputs[3]`` index is
    BRITTLE — on the pinned PyMC 6.0.1 that input is the ``sigma`` draw, and the
    ``mu`` argument is a different node. So instead of a fixed index we locate the
    constant ``mu`` robustly: it is the RV node input that is a non-random,
    deterministically-evaluable constant whose value is NOT the sigma (a positive
    HalfNormal scalar draw). Concretely the mu is the constant carrying either the
    scalar ``0.0`` (off) or the per-team mean vector ``k·elo_z`` (on). We scan the
    inputs, eval the constant-foldable ones, and return the one matching the mean's
    expected SHAPE (scalar for off, length-n_teams for on). The prior-predictive
    behavioral tests below are the version-robust backstop for the same contract.
    """
    candidates = []
    for inp in rv.owner.inputs:
        try:
            val = np.asarray(inp.eval())
        except Exception:
            continue
        if not np.issubdtype(val.dtype, np.number):
            continue                                # skip the RNG / non-numeric inputs
        candidates.append(val)
    return candidates


def test_anchor_off_is_zero_mean():
    with pm.Model():
        _priors(_d([2.0, -2.0]), PRIOR,
                strength={"enabled": False, "k_att": 0.3, "k_def": 0.3})
        att_raw = pm.model.modelcontext(None)["att_raw"]
        # off path: mu arg is the SCALAR 0.0 (today's behavior) -> NOT a per-team
        # vector. Among the RV's constant inputs the scalar 0.0 is present (the mu),
        # and NO per-team k·elo_z vector ([0.6, -0.6]) appears anywhere — the off
        # path never reads elo_z.
        consts = _normal_mu_input(att_raw)
        # off path: mu is the scalar 0.0 (PyMC may wrap it as a size-1 broadcast
        # constant); a 0-d or size-1 all-zero constant is present.
        has_zero_mu = any(c.size == 1 and float(c.reshape(-1)[0]) == 0.0
                          for c in consts)
        assert has_zero_mu, "off path mu must be the scalar 0.0"
        anchored = 0.3 * np.array([2.0, -2.0])
        leaked = any(c.shape == (2,) and np.allclose(c, anchored) for c in consts)
        assert not leaked, "off path must NOT carry the k·elo_z anchor vector"


def test_anchor_on_sets_mean_to_k_elo_z():
    with pm.Model():
        _priors(_d([2.0, -2.0]), PRIOR,
                strength={"enabled": True, "k_att": 0.3, "k_def": 0.3})
        att_raw = pm.model.modelcontext(None)["att_raw"]
        def_raw = pm.model.modelcontext(None)["def_raw"]
        anchored = 0.3 * np.array([2.0, -2.0])      # k_att * elo_z = k_def * elo_z
        # strong team -> high att AND high def, both +k·elo_z: the per-team mean
        # vector [0.6, -0.6] is present among each RV's inputs (the mu argument).
        att_has = any(c.shape == (2,) and np.allclose(c, anchored)
                      for c in _normal_mu_input(att_raw))
        def_has = any(c.shape == (2,) and np.allclose(c, anchored)
                      for c in _normal_mu_input(def_raw))
        assert att_has, "att_raw mu must be k_att·elo_z"
        assert def_has, "def_raw mu must be k_def·elo_z"


def _att_prior_mean(elo_z, strength, seed=0):
    """Seeded prior-predictive MEAN of the deterministic ``att`` per team — the
    version-robust behavioral probe of the prior. (att = att_raw - mean(att_raw),
    so the elo_z anchor survives the soft sum-to-zero because elo_z is mean~0.)
    """
    with pm.Model():
        _priors(_d(elo_z), PRIOR, strength=strength)
        idata = pm.sample_prior_predictive(
            draws=400, var_names=["att"], random_seed=seed
        )
    return idata.prior["att"].mean(dim=("chain", "draw")).values


def test_off_path_is_byte_identical_to_elo_z_zeros():
    """BYTE-IDENTICAL-WHEN-OFF PROOF. With enabled=False and a NON-trivial elo_z,
    the seeded prior-predictive ``att`` is IDENTICAL to the same fit with
    elo_z=zeros — the off path never reads elo_z (its mean is the scalar 0.0). If
    the off path leaked elo_z into the mean, these two draws would differ.
    """
    a_nontrivial = _att_prior_mean(
        [2.0, -2.0], {"enabled": False, "k_att": 0.3, "k_def": 0.3}, seed=7)
    a_zeros = _att_prior_mean(
        [0.0, 0.0], {"enabled": False, "k_att": 0.3, "k_def": 0.3}, seed=7)
    assert np.array_equal(a_nontrivial, a_zeros), (
        "off path leaked elo_z: prior-predictive att differs from elo_z=zeros"
    )


def test_on_path_discriminates():
    """BEHAVIORAL contract for ON: anchored -> team-A (high elo_z) att-mean >
    team-B (low elo_z); off -> equal-ish (same RV graph regardless of elo_z)."""
    on = _att_prior_mean(
        [2.0, -2.0], {"enabled": True, "k_att": 0.3, "k_def": 0.3}, seed=11)
    assert on[0] > on[1], "anchored att must discriminate A (strong) > B (weak)"
    off = _att_prior_mean(
        [2.0, -2.0], {"enabled": False, "k_att": 0.3, "k_def": 0.3}, seed=11)
    # off: mean is 0 for both -> the gap is ~0 (sampling noise only), and the ON
    # gap is much larger than the OFF gap.
    assert (on[0] - on[1]) > abs(off[0] - off[1])
