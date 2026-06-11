"""Altitude (acclimatized-altitude) covariate leakage canary — P2a, mirrors the
rest_days canary (``tests/model/test_covariate_leakage.py``).

``accl_alt`` is a STATIC venue property minus a static national constant: for a match it
is ``CITY_ELEVATION_M[city] − accustomed_alt(team)``, read straight off the match row's
own ``city`` (known pre-kickoff, never revised). It must inherit the bitemporal store's
leakage-safety end to end: a covariate row observed/stamped AFTER the cutoff must NOT
change an as-of-cutoff forecast, and the standardization transform must be fit on
``< cutoff`` rows ONLY. The canary is NON-VACUOUS — a positive control + a revert-proof
give it teeth, so a green result is a real guarantee, not a panel that can never move.

THE LEAK VECTOR. ``accl_alt`` for a row is a function of its ``city`` + ``team``. We
inject ONE NEW high-altitude home match for an accustomed nation (Bolivia at La Paz vs a
lowland visitor) dated strictly between two existing in-panel dates. IF it reached the
``< cutoff`` panel it would add a (home-gap ≈ 0, away-gap ≈ 3640) training PAIR — moving
the POOLED standardization mean/sd AND the fitted ``beta_accl_alt`` (the pooled-fit case,
see ``scoreline._POOLED_FIT_COVS``), hence the as-of-cutoff forecast. The row is stamped
POST-cutoff (``observed_at = valid_as_of > cutoff``) so ``store.read(cutoff)`` excludes
it. A leakage-safe forecast is therefore BYTE-IDENTICAL across the injection; if it moves,
the covariate path peeked past the cutoff.

NON-VACUITY. The SAME injected row, stamped PRE-cutoff, IS returned by ``read(cutoff)``
and DOES move the panel ``accl_alt`` column, the transform mean, and the forecast — and a
revert-proof (``enabled=[]`` vs ``enabled=["accl_alt"]``) proves the term is genuinely
live. This module builds its OWN multi-altitude store (the shared ``small_store`` has a
single altitude venue → a degenerate single-row transform), keyed by ``accl_gap`` off the
results ``city`` (no venues-coord dependency).

Tiny-fixture pattern: ``strength_prior.enabled=false`` is pinned (degenerate coarse fits
can flip the anchor's sign).
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from wcmodel.config import load_config
from wcmodel.data import features
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.model.panel import to_match_panel
from wcmodel.model.scoreline import fit

CUTOFF = "2024-06-01"

# Seeded compact ADVI fit: deterministic (same cutoff+seed -> byte-identical forecast, so
# the `==` comparisons below are exact) and fast.
_FIT_KW = dict(backend="advi", draws=60, advi_iters=800, seed=0)

# Compact multi-altitude < cutoff panel: CONMEBOL home games at altitude + lowland games,
# so the pooled accl_alt training column has variance (sd > 0) and a real beta is fitted.
_BASE_ROWS = [
    # date, home, away, hs, as, tournament, city, country, neutral
    ("2023-03-01", "Bolivia", "Brazil", 2, 1, "FIFA World Cup qualification", "La Paz", "Bolivia", False),
    ("2023-04-01", "Ecuador", "Argentina", 1, 1, "FIFA World Cup qualification", "Quito", "Ecuador", False),
    ("2023-05-01", "Colombia", "Uruguay", 2, 0, "FIFA World Cup qualification", "Bogotá", "Colombia", False),
    ("2023-06-10", "Bolivia", "Argentina", 0, 3, "FIFA World Cup qualification", "La Paz", "Bolivia", False),
    ("2023-07-01", "Brazil", "Argentina", 1, 0, "Friendly", "Miami (Miami Gardens)", "United States", True),
    ("2023-08-01", "Argentina", "Brazil", 2, 1, "Friendly", "Seattle", "United States", True),
    ("2023-09-01", "Ecuador", "Colombia", 1, 1, "FIFA World Cup qualification", "Quito", "Ecuador", False),
    ("2024-01-15", "Uruguay", "Bolivia", 3, 0, "FIFA World Cup qualification", "Seattle", "Uruguay", False),
    ("2023-11-01", "Colombia", "Brazil", 2, 1, "FIFA World Cup qualification", "Bogotá", "Colombia", False),
    ("2023-12-01", "Argentina", "Uruguay", 1, 0, "Friendly", "Miami (Miami Gardens)", "United States", True),
]

# The injected accl_alt-moving row: a NEW Bolivia HOME match at La Paz (a high-altitude
# acclimatized-home game) vs a lowland visitor, dated 2023-12-15 — strictly before the
# cutoff yet not in the base panel. If admitted it adds a (home-gap ≈ 0, away-gap ≈ 3640)
# training PAIR, moving the pooled transform + the fitted beta.
_INJECT = normalize_results(pd.DataFrame(
    [("2023-12-15", "Bolivia", "Germany", 3, 0, "FIFA World Cup qualification", "La Paz", "Bolivia", False)],
    columns=["date", "home_team", "away_team", "home_score", "away_score",
             "tournament", "city", "country", "neutral"],
))


def _cfg(enabled):
    cfg = copy.deepcopy(load_config())
    cfg["model"]["covariates"]["enabled"] = list(enabled)
    # Tiny-fixture pattern: pin the anchor off (degenerate coarse fits flip signs).
    cfg["model"]["strength_prior"] = {"enabled": False, "source": "elo",
                                      "k_att": 0.0, "k_def": 0.0}
    return cfg


def _make_store(tmp_path, subdir="store"):
    root = tmp_path / subdir
    root.mkdir(parents=True, exist_ok=True)
    store = BitemporalStore(root=root)
    results = normalize_results(pd.DataFrame(
        _BASE_ROWS, columns=["date", "home_team", "away_team", "home_score",
                             "away_score", "tournament", "city", "country", "neutral"]))
    store.write("results", results, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    return store


def _write_injected(store, *, observed_at):
    """Append the accl_alt-moving Bolivia/La-Paz row with the given bitemporal stamp.
    ``observed_at = valid_as_of`` so a POST-cutoff stamp is hidden by ``read(cutoff)``
    (leak gate) and a PRE-cutoff stamp is visible (teeth)."""
    row = _INJECT.copy()
    row["observed_at"] = pd.Timestamp(observed_at)
    row["valid_as_of"] = pd.Timestamp(observed_at)
    store.write("results", row, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")


def _accl_panel_stats(store, cutoff, cfg):
    """The < cutoff panel's accl_alt training stats — row count + the POOLED (home+away)
    nanmean (the pooled fit's actual standardizer) — the quantities the injected row would
    move IF it leaked into the panel."""
    mp = to_match_panel(features.build(cutoff, store, cfg))
    home = mp["accl_alt"].to_numpy()
    away = mp["accl_alt__away"].to_numpy()
    pooled = np.concatenate([home, away])
    return len(mp), float(np.nanmean(pooled))


# --------------------------------------------------------------------------- #
# (0) The leak vector is real — non-vacuity for the negative gate (FAST, no fit) #
# --------------------------------------------------------------------------- #
def test_accl_alt_leak_vector_is_non_vacuous(tmp_path):
    """TEETH for the negative gate (panel-level, fast): the injected row is excluded by
    ``read(cutoff)`` when stamped POST-cutoff (panel unchanged), but WOULD move the
    accl_alt panel if admitted — proven by writing the SAME row PRE-cutoff and watching
    the pooled training mean change."""
    cfg = _cfg(["accl_alt"])
    store = _make_store(tmp_path, "base")
    base_rows, base_mean = _accl_panel_stats(store, CUTOFF, cfg)

    # POST-cutoff stamp: read(cutoff) must EXCLUDE it -> panel unchanged.
    _write_injected(store, observed_at="2024-09-01")
    vis = store.read("results", cutoff=CUTOFF)
    assert not (pd.to_datetime(vis["date"]) == pd.Timestamp("2023-12-15")).any(), (
        "the POST-cutoff-stamped row must NOT be visible to read(cutoff)"
    )
    post_rows, post_mean = _accl_panel_stats(store, CUTOFF, cfg)
    assert (post_rows, post_mean) == (base_rows, base_mean), (
        "POST-cutoff row changed the accl_alt panel — store gating failed"
    )

    # PRE-cutoff stamp on the SAME row, fresh store: read(cutoff) INCLUDES it -> panel MOVES.
    leaky = _make_store(tmp_path, "leaky")
    _write_injected(leaky, observed_at="2023-12-16")
    vis2 = leaky.read("results", cutoff=CUTOFF)
    assert (pd.to_datetime(vis2["date"]) == pd.Timestamp("2023-12-15")).any(), (
        "the PRE-cutoff-stamped row must BE visible to read(cutoff)"
    )
    leak_rows, leak_mean = _accl_panel_stats(leaky, CUTOFF, cfg)
    assert leak_rows == base_rows + 1, "the leaked row adds a training row"
    assert leak_mean != base_mean, "the leaked row moves the pooled transform mean"
    # The crux: invariant under POST, MOVED under PRE — the negative gate has teeth.
    assert (post_rows, post_mean) == (base_rows, base_mean)
    assert (leak_rows, leak_mean) != (base_rows, base_mean)


# --------------------------------------------------------------------------- #
# (1) THE NEGATIVE GATE — post-cutoff covariate must NOT move the forecast      #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_post_cutoff_accl_alt_does_not_leak_into_as_of_forecast(tmp_path):
    """NEGATIVE (the leak gate). Fit + predict an as-of-cutoff forecast with accl_alt IN
    THE MODEL. Inject a POST-cutoff Bolivia/La-Paz row that WOULD change accl_alt IF it
    leaked. Re-fit at the SAME cutoff. The forecast must be BYTE-IDENTICAL and the
    persisted transform mean/sd unchanged — the post-cutoff covariate did NOT leak."""
    cfg = _cfg(["accl_alt"])
    store = _make_store(tmp_path, "neg")
    f1 = fit(CUTOFF, store, config=cfg, **_FIT_KW)
    p1 = f1.predict_1x2("Bolivia", "Brazil", neutral=True)
    mean1 = f1.covariate_transforms["accl_alt"].mean
    sd1 = f1.covariate_transforms["accl_alt"].sd
    assert sd1 > 0.0, "fixture must give accl_alt real signal for a meaningful gate"

    _write_injected(store, observed_at="2024-09-01")     # POST-cutoff
    f2 = fit(CUTOFF, store, config=cfg, **_FIT_KW)
    p2 = f2.predict_1x2("Bolivia", "Brazil", neutral=True)

    assert p2 == p1, "post-cutoff accl_alt leaked into the as-of-cutoff forecast"
    assert f2.covariate_transforms["accl_alt"].mean == mean1
    assert f2.covariate_transforms["accl_alt"].sd == sd1


# --------------------------------------------------------------------------- #
# (2) POSITIVE CONTROL + REVERT-PROOF — the covariate term is genuinely live    #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_accl_alt_positive_control_and_revert_proof(tmp_path):
    """NON-VACUITY. Two complementary proofs:

      POSITIVE CONTROL — inject the SAME La-Paz row PRE-cutoff so it IS in the < cutoff
      panel. It adds a (low home-gap, high away-gap) pair, moving the fitted transform +
      beta, so the forecast must DIFFER from the no-injection accl_alt forecast.

      REVERT-PROOF — the SAME baseline fixture predicted with ``enabled=[]`` (the
      covariate DROPPED) must DIFFER from the ``enabled=["accl_alt"]`` forecast — the
      beta_accl_alt term is live, not a no-op the negative gate trivially preserves.
    """
    cfg_on = _cfg(["accl_alt"])
    store = _make_store(tmp_path, "pos")
    base = fit(CUTOFF, store, config=cfg_on, **_FIT_KW)
    p_on = base.predict_1x2("Bolivia", "Brazil", neutral=True)

    # REVERT-PROOF: dropping the covariate (enabled=[]) changes the forecast.
    cfg_off = _cfg([])
    off = fit(CUTOFF, _make_store(tmp_path, "off"), config=cfg_off, **_FIT_KW)
    assert off.covariate_transforms == {}, "enabled=[] must fit no transform"
    assert "beta_accl_alt" not in off.idata.posterior, "enabled=[] must add no beta"
    p_off = off.predict_1x2("Bolivia", "Brazil", neutral=True)
    assert p_off != p_on, "covariate term is inert (revert-proof failed)"

    # POSITIVE CONTROL: a pre-cutoff accl_alt change DOES move the forecast.
    leaky = _make_store(tmp_path, "pos_leaky")
    _write_injected(leaky, observed_at="2023-12-16")     # PRE-cutoff -> in the panel
    moved = fit(CUTOFF, leaky, config=cfg_on, **_FIT_KW)
    p_moved = moved.predict_1x2("Bolivia", "Brazil", neutral=True)
    assert p_moved != p_on, "positive control failed: a pre-cutoff accl_alt change did NOT move the forecast"
    assert moved.covariate_transforms["accl_alt"].mean != \
        base.covariate_transforms["accl_alt"].mean


# --------------------------------------------------------------------------- #
# (3) THE TRANSFORM IS FIT ON < cutoff ROWS ONLY                                #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_accl_alt_transform_fit_on_pre_cutoff_only(tmp_path):
    """The standardization transform's ``mean`` is computed from ``< cutoff`` rows only.

      (a) HAND-COMPUTED: the persisted ``mean`` equals the nanmean of the POOLED (home +
          away) accl_alt training columns from ``features.build(cutoff)`` (the pooled-fit
          standardizer for accl_alt — see scoreline._POOLED_FIT_COVS).
      (b) POST-CUTOFF-INVARIANT: injecting a post-cutoff row does NOT change the persisted
          mean/sd (excluded from the training panel by the bitemporal read).
    """
    cfg = _cfg(["accl_alt"])
    store = _make_store(tmp_path, "fit")
    post = fit(CUTOFF, store, config=cfg, **_FIT_KW)
    t = post.covariate_transforms["accl_alt"]

    # (a) Persisted mean == nanmean over the POOLED < cutoff training columns.
    mp = to_match_panel(features.build(CUTOFF, store, cfg))
    pooled = np.concatenate([mp["accl_alt"].to_numpy(), mp["accl_alt__away"].to_numpy()])
    expected_mean = float(np.nanmean(pooled))
    assert t.mean == expected_mean, (
        "transform mean is not the < cutoff POOLED training nanmean — it may be reading "
        "rows past the cutoff (or not pooling as accl_alt requires)"
    )

    # (b) A post-cutoff row leaves the persisted transform untouched.
    _write_injected(store, observed_at="2024-09-01")
    post2 = fit(CUTOFF, store, config=cfg, **_FIT_KW)
    t2 = post2.covariate_transforms["accl_alt"]
    assert (t2.mean, t2.sd) == (t.mean, t.sd), (
        "post-cutoff row changed the standardization transform — it must be fit on "
        "< cutoff rows only"
    )
