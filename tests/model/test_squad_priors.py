"""P3 v0 [LOAD-BEARING]: the squad-strength anchor term in the att/def prior MEAN.

Extends the Elo anchor (``test_strength_priors.py``). The full anchor mean is the
brief's:

    anchor_mean[t] = k_elo·elo_z[t]  +  k_squad·squad_z[t]·has_squad[t]

In code, ``_priors`` reads ``d.elo_z`` (== ``k_elo·elo_z`` term, with k from
``strength.k_att``/``k_def``) and ADDITIVELY adds ``strength.k_squad`` ·
``d.squad_z`` · ``d.has_squad``. The mask is binding: an uncovered team
(``has_squad==0``) gets ZERO squad contribution at ANY ``k_squad`` — its prior
mean is UNCHANGED from the pure-Elo anchor.

BYTE-IDENTICAL-OFF (the load-bearing invariant): with ``k_squad == 0.0`` (the
default) every produced prior object is byte-identical to the k_squad-ABSENT code
path. We prove this two ways:
  * the RV ``mu`` input vector at k_squad=0.0 equals the elo-only anchor vector
    exactly (the squad term is identically 0), AND
  * a seeded prior-predictive ``att`` draw at k_squad=0.0 is array-equal to the
    same draw with the squad block ABSENT and with squad_z=None.
"""
import numpy as np
import pandas as pd
import pymc as pm

from wcmodel.model.panel import build_design
from wcmodel.model.scoreline import _priors


def _d(elo_z, squad_z=None, has_squad=None):
    # full match-panel schema build_design consumes (see panel.to_match_panel).
    # 3 teams so we can have one covered (has_squad=1) and one uncovered (=0).
    mp = pd.DataFrame({"match_id": [1, 2], "date": pd.to_datetime(["2025-06-10", "2025-06-11"]),
                       "home_team": ["A", "B"], "away_team": ["B", "C"],
                       "home_goals": [1, 0], "away_goals": [0, 2],
                       "neutral": [False, False], "match_type": ["friendly", "friendly"],
                       "weight": [1.0, 1.0], "home_provisional": [False, False],
                       "away_provisional": [False, False]})
    return build_design(mp, elo_z=np.array(elo_z, dtype=float),
                        squad_z=None if squad_z is None else np.array(squad_z, dtype=float),
                        has_squad=None if has_squad is None else np.array(has_squad, dtype=float))


PRIOR = {"sigma_att": 0.5, "sigma_def": 0.5, "mu_loc": 0.0, "mu_scale": 1.0,
         "home_loc": 0.25, "home_scale": 0.25}


def _const_inputs(rv):
    """Every constant-foldable numeric input array of an RV (the mu candidates)."""
    out = []
    for inp in rv.owner.inputs:
        try:
            val = np.asarray(inp.eval())
        except Exception:
            continue
        if not np.issubdtype(val.dtype, np.number):
            continue
        out.append(val)
    return out


# --------------------------------------------------------------------------- #
# build_design carries squad_z / has_squad aligned to teams.                   #
# --------------------------------------------------------------------------- #
def test_design_carries_squad_z_and_has_squad_aligned():
    d = _d([0.5, 0.0, -0.5], squad_z=[1.0, -1.0, 0.0], has_squad=[1.0, 1.0, 0.0])
    assert d.teams == ["A", "B", "C"]
    assert d.squad_z is not None and d.squad_z.shape == (3,)
    assert d.has_squad is not None and d.has_squad.shape == (3,)
    assert d.squad_z[0] == 1.0 and d.has_squad[2] == 0.0


def test_design_squad_fields_default_to_zeros_and_ones_absent():
    # squad_z absent -> zeros; has_squad absent -> all-ones (no mask => every team
    # would carry its squad_z, but squad_z is zeros so the term is still 0).
    d = _d([0.5, 0.0, -0.5])
    assert d.squad_z is not None and np.allclose(d.squad_z, 0.0)
    assert d.has_squad is not None and np.allclose(d.has_squad, 1.0)


# --------------------------------------------------------------------------- #
# The additive squad term + the binding mask.                                  #
# --------------------------------------------------------------------------- #
def test_squad_term_adds_to_elo_anchor_for_covered_teams():
    elo_z = [0.5, 0.0, -0.5]
    squad_z = [1.0, -1.0, 0.5]
    has_squad = [1.0, 1.0, 0.0]          # C uncovered
    k_elo, k_squad = 0.6, 0.4
    with pm.Model():
        _priors(_d(elo_z, squad_z, has_squad), PRIOR,
                strength={"enabled": True, "k_att": k_elo, "k_def": k_elo,
                          "k_squad": k_squad})
        att_raw = pm.model.modelcontext(None)["att_raw"]
        # Expected per-team mean: k_elo*elo_z + k_squad*squad_z*has_squad.
        expected = (k_elo * np.array(elo_z)
                    + k_squad * np.array(squad_z) * np.array(has_squad))
        present = any(c.shape == (3,) and np.allclose(c, expected)
                      for c in _const_inputs(att_raw))
        assert present, "att_raw mu must be k_elo*elo_z + k_squad*squad_z*has_squad"


def test_uncovered_team_prior_unchanged_at_any_k_squad():
    """The mask is binding: team C (has_squad=0) gets the SAME prior mean at
    k_squad=0 and k_squad=10 — its squad contribution is identically zero."""
    elo_z = [0.5, 0.0, -0.5]
    squad_z = [1.0, -1.0, 9.9]           # C has a wild squad_z, but it's masked off
    has_squad = [1.0, 1.0, 0.0]
    k_elo = 0.6

    def _mean_C(k_squad):
        with pm.Model():
            _priors(_d(elo_z, squad_z, has_squad), PRIOR,
                    strength={"enabled": True, "k_att": k_elo, "k_def": k_elo,
                              "k_squad": k_squad})
            att_raw = pm.model.modelcontext(None)["att_raw"]
            for c in _const_inputs(att_raw):
                if c.shape == (3,):
                    return float(c[2])
        return None

    assert abs(_mean_C(0.0) - _mean_C(10.0)) < 1e-12, (
        "uncovered team C's prior mean moved with k_squad — mask not applied")
    # And it equals the pure-Elo value k_elo*elo_z[C].
    assert abs(_mean_C(0.0) - (k_elo * elo_z[2])) < 1e-12


# --------------------------------------------------------------------------- #
# BYTE-IDENTICAL-OFF at k_squad=0.0.                                            #
# --------------------------------------------------------------------------- #
def test_k_squad_zero_mean_equals_elo_only_anchor_vector():
    """At k_squad=0.0 the att_raw mu vector EQUALS the elo-only anchor vector
    (the squad term is identically 0) — byte-identical to the k_squad-absent path."""
    elo_z = [0.5, 0.0, -0.5]
    squad_z = [1.0, -1.0, 0.5]
    has_squad = [1.0, 1.0, 1.0]
    k_elo = 0.6
    with pm.Model():
        _priors(_d(elo_z, squad_z, has_squad), PRIOR,
                strength={"enabled": True, "k_att": k_elo, "k_def": k_elo,
                          "k_squad": 0.0})
        att_raw = pm.model.modelcontext(None)["att_raw"]
        elo_only = k_elo * np.array(elo_z)
        present = any(c.shape == (3,) and np.allclose(c, elo_only)
                      for c in _const_inputs(att_raw))
        assert present, "k_squad=0.0 mu must equal the elo-only anchor exactly"


def _att_prior_mean(elo_z, squad_z, has_squad, strength, seed=0):
    """Seeded prior-predictive MEAN of deterministic ``att`` (version-robust probe)."""
    with pm.Model():
        _priors(_d(elo_z, squad_z, has_squad), PRIOR, strength=strength)
        idata = pm.sample_prior_predictive(draws=300, var_names=["att"],
                                           random_seed=seed)
    return idata.prior["att"].mean(dim=("chain", "draw")).values


def test_k_squad_zero_is_byte_identical_to_squad_absent():
    """BYTE-IDENTICAL-OFF PROOF. With a NON-trivial squad_z, the seeded
    prior-predictive ``att`` at k_squad=0.0 is IDENTICAL to (a) the same fit with
    the squad block carrying NO k_squad key (legacy elo-only strength dict) and
    (b) the same fit with squad_z=None. If k_squad=0 leaked the squad term these
    would differ."""
    elo_z = [0.5, 0.0, -0.5]
    squad_z = [1.0, -1.0, 0.5]
    has_squad = [1.0, 1.0, 1.0]
    k_elo = 0.6
    a_k0 = _att_prior_mean(elo_z, squad_z, has_squad,
                           {"enabled": True, "k_att": k_elo, "k_def": k_elo,
                            "k_squad": 0.0}, seed=7)
    a_legacy = _att_prior_mean(elo_z, squad_z, has_squad,
                               {"enabled": True, "k_att": k_elo, "k_def": k_elo},
                               seed=7)
    a_none = _att_prior_mean(elo_z, None, None,
                             {"enabled": True, "k_att": k_elo, "k_def": k_elo,
                              "k_squad": 0.0}, seed=7)
    assert np.array_equal(a_k0, a_legacy), (
        "k_squad=0.0 differs from the k_squad-absent (legacy) strength dict")
    assert np.array_equal(a_k0, a_none), (
        "k_squad=0.0 differs from squad_z=None — squad term not truly off")


def test_on_path_discriminates_on_squad():
    """BEHAVIORAL: with elo_z FLAT (no Elo signal) and only squad_z carrying the
    strength, a k_squad>0 anchor makes the high-squad_z team's att-mean exceed the
    low-squad_z team's — the squad term alone discriminates."""
    elo_z = [0.0, 0.0, 0.0]              # flat -> elo term contributes nothing
    squad_z = [1.5, -1.5, 0.0]
    has_squad = [1.0, 1.0, 1.0]
    on = _att_prior_mean(elo_z, squad_z, has_squad,
                         {"enabled": True, "k_att": 0.6, "k_def": 0.6,
                          "k_squad": 0.5}, seed=11)
    assert on[0] > on[1], "k_squad>0 must discriminate high-squad_z A > low-squad_z B"
    off = _att_prior_mean(elo_z, squad_z, has_squad,
                          {"enabled": True, "k_att": 0.6, "k_def": 0.6,
                           "k_squad": 0.0}, seed=11)
    assert (on[0] - on[1]) > abs(off[0] - off[1])
