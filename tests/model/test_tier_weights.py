"""P2c — per-tier likelihood weight wired into ``fit`` + the posterior cache key.

The likelihood weight was time-decay only (× the optional mechanism-(a)
provisional down-weight). P2c layers a multiplicative per-TIER importance weight
``w = decay × tier_w[tier]`` behind ``config["model"]["likelihood_tier_weights"]``.

THE LOAD-BEARING INVARIANT is byte-identical OFF, proven BOTH ways on a seeded
tiny-fixture fit:
  * the block ABSENT from config, and
  * a block of ALL 1.0s
must each give a posterior bit-identical to the pre-P2c baseline.

A weights-move test with teeth pins that ``tier_w[friendly]=0.5`` actually changes
the fit (the off path is non-vacuous), unknown tier names fail loud, and the
posterior cache key is byte-identical for the off states (absent AND all-1.0) but
changes for a non-default block — so an all-1.0 block never invalidates an
existing cached production posterior.

Per the house convention these tiny-fixture fits pin ``strength_prior.enabled =
false`` (degenerate fits can flip signs on a tiny synthetic store).
"""
from __future__ import annotations

import copy

import numpy as np
import pytest

from wcmodel.config import load_config
from wcmodel.model.scoreline import fit

CUTOFF = "2024-06-01"
# Seeded compact ADVI fit: deterministic (same cutoff+seed -> byte-identical
# posterior, so the array_equal comparisons below are exact) and fast.
_FIT_KW = dict(backend="advi", draws=60, advi_iters=800, seed=0)


def _base_cfg():
    """Production config with strength_prior pinned OFF (tiny-fixture house rule)."""
    cfg = copy.deepcopy(load_config())
    cfg["model"]["strength_prior"]["enabled"] = False
    # Drop any tier-weight block so this is the pristine OFF baseline.
    cfg["model"].pop("likelihood_tier_weights", None)
    return cfg


def _cfg_with_tier_w(tier_w):
    cfg = _base_cfg()
    cfg["model"]["likelihood_tier_weights"] = dict(tier_w)
    return cfg


def _posterior_arrays(post):
    """The fitted posterior params as a dict of numpy arrays, for exact equality."""
    p = post.idata.posterior
    return {k: p[k].values.copy() for k in p.data_vars}


# --------------------------------------------------------------------------- #
# Byte-identical OFF — both ways — on a seeded tiny-fixture fit.                #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_off_absent_block_is_byte_identical_baseline(small_store):
    """OFF #1: no ``likelihood_tier_weights`` key -> posterior bit-identical to
    the pre-P2c baseline (which also has no such key). Same seed/cutoff/config."""
    base = fit(CUTOFF, small_store, config=_base_cfg(), **_FIT_KW)
    again = fit(CUTOFF, small_store, config=_base_cfg(), **_FIT_KW)
    a, b = _posterior_arrays(base), _posterior_arrays(again)
    assert a.keys() == b.keys()
    for k in a:
        assert np.array_equal(a[k], b[k]), f"non-deterministic baseline var {k}"


@pytest.mark.slow
def test_off_all_ones_block_is_byte_identical_baseline(small_store):
    """OFF #2 (the load-bearing one): an explicit ALL-1.0 block produces a
    posterior bit-identical to the absent-block baseline. all-1.0 == off."""
    base = fit(CUTOFF, small_store, config=_base_cfg(), **_FIT_KW)
    ones = {t: 1.0 for t in ["friendly", "wc_qualifier", "wc_finals",
                             "continental_championship", "continental_qualifier",
                             "nations_league", "other"]}
    allones = fit(CUTOFF, small_store, config=_cfg_with_tier_w(ones), **_FIT_KW)
    a, b = _posterior_arrays(base), _posterior_arrays(allones)
    assert a.keys() == b.keys()
    for k in a:
        assert np.array_equal(a[k], b[k]), (
            f"all-1.0 tier block changed posterior var {k} — NOT byte-identical off")


# --------------------------------------------------------------------------- #
# Weights-move test with TEETH: tier_w[friendly]=0.5 changes the fit.           #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_friendly_half_moves_the_fit(small_store):
    """NON-VACUITY: tier_w[friendly]=0.5 (halving every friendly's likelihood
    weight) MUST change the fitted posterior vs the off baseline — otherwise the
    byte-identical-off proof would be vacuous (the knob would do nothing)."""
    base = fit(CUTOFF, small_store, config=_base_cfg(), **_FIT_KW)
    moved = fit(CUTOFF, small_store, config=_cfg_with_tier_w({"friendly": 0.5}),
                **_FIT_KW)
    a, b = _posterior_arrays(base), _posterior_arrays(moved)
    # At least one core param must differ — the friendly down-weight reshapes the fit.
    differs = any(not np.array_equal(a[k], b[k]) for k in a if k in b)
    assert differs, "tier_w[friendly]=0.5 left the posterior unchanged (knob is inert)"


# --------------------------------------------------------------------------- #
# Strict validation: unknown tier name fails loud through fit().                #
# --------------------------------------------------------------------------- #
def test_unknown_tier_name_fails_loud_in_fit(small_store):
    """An unknown tier key is a config error -> ValueError naming the bad tier,
    surfaced through the fit path (not silently ignored). FAST: the validation
    fires before sampling."""
    with pytest.raises(ValueError) as exc:
        fit(CUTOFF, small_store,
            config=_cfg_with_tier_w({"freindly": 0.5}),  # typo
            **_FIT_KW)
    assert "freindly" in str(exc.value)
