"""Integration capstone: fit(features, cutoff) -> Posterior + predict_*.

Wires the leakage-safe per-cutoff feature panel through the match-level design,
the (a)/(c) widening switch, the PyMC scoreline model, and inference into a
Posterior whose predict_scoreline/predict_1x2 build the scoreline grid MANUALLY
from the posterior parameters (the likelihood is a Potential -> no observed RV to
sample_posterior_predictive from). ADVI is used so these stay fast; they are
still real end-to-end fits, so marked slow.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from wcmodel.config import load_config
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.model.scoreline import fit


def _provisional_contrast_store(tmp_path):
    """Store with ONE team SETTLED at the cutoff but provisional early in its
    history, and ANOTHER team GENUINELY provisional at the cutoff.

    * ``Settled`` plays 12 even 1-1 draws vs ``Foil``. Its first
      ``provisional_games`` (5) matches are flagged provisional by Phase-1 Elo's
      few-games arm (so it HAS historical provisional rows -> the old
      "ever-provisional" set picks it up), but by its 12th match it is long
      settled with near-zero recent rating volatility -> NOT provisional as of
      the cutoff.
    * ``Prov`` plays only 2 matches -> still inside the few-games arm at the
      cutoff -> genuinely provisional for the next (prediction) match.
    * ``Foil`` plays many matches and ends low-volatility -> not provisional.

    The as-of-cutoff provisional set is therefore exactly ``{"Prov"}``, while the
    buggy ever-provisional set is ``{"Settled", "Prov", "Foil"}``.
    """
    rows = []
    d0 = pd.Timestamp("2020-01-01")
    n = 0
    for _ in range(12):  # Settled: converges to ~0 deltas, low recent volatility
        rows.append((str((d0 + pd.Timedelta(days=n)).date()), "Settled", "Foil",
                     1, 1, "Friendly", "London", "England", False))
        n += 1
    for _ in range(2):   # Prov: few-games arm -> provisional at cutoff
        rows.append((str((d0 + pd.Timedelta(days=n)).date()), "Prov", "Foil",
                     2, 0, "Friendly", "London", "England", False))
        n += 1
    raw = pd.DataFrame(rows, columns=["date", "home_team", "away_team",
                                      "home_score", "away_score", "tournament",
                                      "city", "country", "neutral"])
    store = BitemporalStore(root=tmp_path)
    store.write("results", normalize_results(raw), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    return store


@pytest.mark.slow
def test_provisional_set_is_as_of_cutoff_not_ever_provisional(tmp_path):
    """FIX 7a: the prediction-time provisional set is the AS-OF-CUTOFF status,
    not "ever provisional". A team settled at the cutoff (but provisional in its
    first few games) must be EXCLUDED; a team genuinely provisional at the cutoff
    must be INCLUDED. The old code (ever-provisional, read off per-match panel
    flags) wrongly widened the settled team forever."""
    store = _provisional_contrast_store(tmp_path)
    post = fit("2024-06-01", store, backend="advi", draws=40, seed=0, advi_iters=300)
    # Sanity: the panel really did flag the settled team provisional early (so
    # this is a genuine ever-vs-as-of distinction, not a vacuous pass).
    from wcmodel.data import features
    from wcmodel.model.panel import to_match_panel
    mp = to_match_panel(features.build("2024-06-01", store, load_config()))
    ever = set(mp.loc[mp["home_provisional"], "home_team"]) | set(
        mp.loc[mp["away_provisional"], "away_team"])
    assert "Settled" in ever, "fixture must flag Settled provisional in early rows"
    # The fix: as-of-cutoff set excludes the now-settled team, includes the
    # genuinely-provisional one.
    assert "Settled" not in post.provisional_teams
    assert "Prov" in post.provisional_teams
    assert "Foil" not in post.provisional_teams


@pytest.mark.slow
def test_fit_config_is_authoritative_for_widening_and_priors(tmp_path):
    """FIX 7b: a config passed to fit(config=cfg) is authoritative for BOTH the
    predict-time widening mechanism (threaded into Posterior) AND the model
    priors (threaded into build_model -> _priors). Mechanism "a" widens in the
    likelihood, so predict_scoreline must NOT call inflate_predictive; the
    default "c" does."""
    store = _provisional_contrast_store(tmp_path)

    cfg_a = copy.deepcopy(load_config())
    cfg_a["model"]["widening"]["mechanism"] = "a"
    cfg_a["model"]["widening"]["strength"] = 0.5
    cfg_a["model"]["prior"]["sigma_att"] = 0.123   # custom prior must reach _priors

    post_a = fit("2024-06-01", store, config=cfg_a, backend="advi", draws=40,
                 seed=0, advi_iters=300)
    # Config threaded into Posterior: its widening mechanism is "a", not the
    # global "c".
    assert post_a._cfg["widening"]["mechanism"] == "a"

    # Under mechanism "a", predict_scoreline must NOT call inflate_predictive
    # (widening already happened in the likelihood). Spy on it.
    import wcmodel.model.posterior as posterior_mod
    calls = {"n": 0}
    orig = posterior_mod.inflate_predictive

    def _spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    posterior_mod.inflate_predictive = _spy
    try:
        post_a.predict_scoreline("Prov", "Foil", neutral=True, max_goals=6)
    finally:
        posterior_mod.inflate_predictive = orig
    assert calls["n"] == 0, "mechanism 'a' must not widen at predict time"

    # Contrast: default "c" DOES call inflate_predictive for a provisional team.
    post_c = fit("2024-06-01", store, backend="advi", draws=40, seed=0, advi_iters=300)
    assert post_c._cfg["widening"]["mechanism"] == "c"
    calls_c = {"n": 0}

    def _spy_c(*a, **k):
        calls_c["n"] += 1
        return orig(*a, **k)

    posterior_mod.inflate_predictive = _spy_c
    try:
        post_c.predict_scoreline("Prov", "Foil", neutral=True, max_goals=6)
    finally:
        posterior_mod.inflate_predictive = orig
    assert calls_c["n"] == 1, "mechanism 'c' must widen a provisional team at predict time"

    # The custom prior reached _priors: the built model's att_raw prior sigma
    # hyperprior (sigma_att HalfNormal scale) reflects the passed sigma_att.
    from wcmodel.data import features
    from wcmodel.model.panel import build_design, to_match_panel
    from wcmodel.model.scoreline import build_model
    d = build_design(to_match_panel(features.build("2024-06-01", store, cfg_a)))
    model = build_model(d, config=cfg_a)
    sigma_att_rv = next(v for v in model.free_RVs if v.name == "sigma_att")
    # HalfNormal sigma is the 2nd positional param of its distribution.
    scale = float(sigma_att_rv.owner.inputs[3].eval())
    assert np.isclose(scale, 0.123), f"custom sigma_att did not reach _priors (got {scale})"


@pytest.mark.slow
def test_fit_then_predict_scoreline_is_a_normalised_grid(small_store):
    post = fit("2024-06-01", small_store, backend="advi", draws=150, seed=0, advi_iters=3000)
    grid = post.predict_scoreline("Brazil", "Argentina", neutral=False, max_goals=6)
    assert grid.shape == (7, 7)
    assert np.isclose(grid.sum(), 1.0, atol=1e-6)
    assert (grid >= 0).all()                      # no negative probabilities
    p = post.predict_1x2("Brazil", "Argentina", neutral=False, max_goals=6)
    assert np.isclose(p["home"] + p["draw"] + p["away"], 1.0, atol=1e-9)


@pytest.mark.slow
def test_predict_unknown_team_raises(small_store):
    post = fit("2024-06-01", small_store, backend="advi", draws=80, seed=0, advi_iters=2000)
    with pytest.raises(KeyError):
        post.predict_scoreline("Atlantis", "Brazil", neutral=True)


@pytest.mark.slow
def test_bivariate_poisson_fit_predicts_normalised(small_store):
    post = fit("2024-06-01", small_store, likelihood="bivariate_poisson",
               backend="advi", draws=120, seed=0, advi_iters=2500)
    g = post.predict_scoreline("Brazil", "Croatia", neutral=True, max_goals=6)
    assert np.isclose(g.sum(), 1.0, atol=1e-6) and (g >= 0).all()
