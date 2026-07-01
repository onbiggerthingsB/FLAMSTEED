"""Review-v2 Fix 3 (Codex pass-4 finding): the sim cache's posterior hash must
cover ``neutral_home_adv_fraction``.

``RateBook`` (sim/scoreline.py) reads ``posterior._cfg["neutral_home_adv_fraction"]``
to build every neutral fixture's rates, so it is output-determining for the
sim — yet ``_posterior_hash`` hashed only the idata values + teams +
likelihood. Two posteriors identical in draws but differing in that tunable
shared a hash, so ``cached_sim`` could stale-serve a pre-change tournament
result after a config change. (It is the ONLY ``_cfg`` field the sim sampling
path consumes: widening applies to prediction grids, not RateBook sampling.)
"""
import copy

import numpy as np
import xarray as xr

from wcmodel.config import load_config
from wcmodel.model.posterior import Posterior
from wcmodel.sim.cache import _posterior_hash

_TEAMS = ["Brazil", "Argentina", "Croatia", "France"]


def _posterior(neutral_fraction: float) -> Posterior:
    rng = np.random.default_rng(7)
    n = len(_TEAMS)
    ds = xr.Dataset(
        {
            "att": (("chain", "draw", "team"), rng.normal(0, 0.3, (1, 6, n))),
            "def": (("chain", "draw", "team"), rng.normal(0, 0.3, (1, 6, n))),
            "mu": (("chain", "draw"), rng.normal(0.1, 0.05, (1, 6))),
            "home_adv": (("chain", "draw"), rng.normal(0.2, 0.05, (1, 6))),
            "rho": (("chain", "draw"), rng.normal(-0.05, 0.01, (1, 6))),
        },
        coords={"team": list(_TEAMS)},
    )
    idata = xr.DataTree.from_dict({"posterior": ds})
    cfg = copy.deepcopy(load_config())
    cfg["model"]["neutral_home_adv_fraction"] = neutral_fraction
    return Posterior(idata, list(_TEAMS), "dixon_coles",
                     provisional_teams=set(), config=cfg)


def test_neutral_fraction_changes_posterior_hash():
    """Same idata draws, different neutral_home_adv_fraction -> the sim rates
    differ, so the hash MUST differ (else cached_sim stale-serves)."""
    a = _posterior(0.5)
    b = _posterior(1.0)
    assert _posterior_hash(a) != _posterior_hash(b)


def test_identical_cfg_hash_is_stable():
    a = _posterior(0.5)
    b = _posterior(0.5)
    assert _posterior_hash(a) == _posterior_hash(b)
