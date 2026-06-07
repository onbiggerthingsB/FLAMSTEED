"""Covariate leakage canary (M-T6) — THE gate that proves the match-context
covariate change is leakage-safe.

The covariate path (``rest_days`` now IN THE MODEL) must inherit the bitemporal
store's leakage-safety end to end: a covariate value observed/stamped AFTER the
cutoff must NOT change an as-of-cutoff forecast, and the standardization
transform must be fit on ``< cutoff`` rows ONLY. The canary is NON-VACUOUS — a
positive control + a revert-proof prove it has teeth, so a green result is a real
guarantee and not a panel that simply can never move.

WHY THE FIT/PREDICT FORECAST IS THE RIGHT GATE. ``fit(cutoff, store)`` reads
ONLY ``features.build(cutoff, store)`` (the Phase-1 leakage-safe panel), then
``_build_covariates`` fits the standardization transform AND the model's
``beta_rest_days`` on that SAME ``< cutoff`` training panel. So a ``> cutoff``
covariate row that leaked into the panel would perturb BOTH the persisted
transform (its mean/sd) AND the fitted beta, hence the as-of-cutoff forecast.
Under a fixed seed + ADVI the whole forecast is a deterministic function of the
``< cutoff`` panel, so ``==`` on the 1X2 forecast is exact and ANY leak shows up.

THE LEAK VECTOR (``rest_days`` is gap-to-prior-fixture). ``rest_days`` for a match
is the day-gap to that team's PREVIOUS fixture within the ``< cutoff`` schedule
(``features._join_rest_days`` over the ``date < cutoff_day`` slice). We inject ONE
NEW Croatia match dated 2023-12-01 — strictly BETWEEN Croatia's existing
2023-06-10 and 2024-01-15 in-panel matches — so that IF it reached the panel it
would become the new "previous fixture" for the 2024-01-15 match and flip its
rest_days 219 -> 45 (and add a 43rd observed training row), moving the transform
mean and the fitted beta. The row is stamped POST-cutoff
(``observed_at = valid_as_of = 2024-09-01 > 2024-06-01``) so the bitemporal
``store.read(cutoff=2024-06-01)`` (``observed_at <= cutoff AND valid_as_of <=
cutoff``) excludes it. A leakage-safe forecast is therefore BYTE-IDENTICAL across
the injection; if it moves, the covariate path peeked past the cutoff.

NON-VACUITY (teeth). The SAME injected row, stamped PRE-cutoff instead, IS
returned by ``read(cutoff)`` and DOES move the panel rest_days, the transform
mean, and the forecast — proving the post-cutoff invariance is a real gate, not a
no-op (``test_covariate_leak_vector_is_non_vacuous``). And the positive control +
revert-proof below prove the covariate term is genuinely live: a pre-cutoff
rest_days difference moves the forecast, and dropping the covariate
(``enabled=[]``) changes the prediction.

These tests reuse the Phase-1/2 ``small_store`` fixture + its compact
``_RAW_RESULTS`` / ``_VENUES`` panel (``tests.data.conftest``) — the same machinery
the rest_days feature-leakage canary (P2-T9, ``test_leakage_model.py``) is built
on — and the same ``observed_at``/``valid_as_of`` post-cutoff write pattern that
canary's count-mode proof uses (``extra["observed_at"] = ...`` then
``store.write(... POINT_IN_TIME ...)``).
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from wcmodel.config import load_config
from wcmodel.data import features
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import Policy
from wcmodel.model.panel import to_match_panel
from wcmodel.model.scoreline import fit

# As-of cutoff every fit in this module is taken at. Croatia's in-panel matches
# straddling the injected 2023-12-01 row (2023-06-10 and 2024-01-15) are both
# strictly before it; the post-cutoff stamp (2024-09-01) sits after it.
CUTOFF = "2024-06-01"

# Seeded compact ADVI fit: deterministic (same cutoff+seed -> byte-identical
# forecast, so the `==` comparisons below are exact) and fast.
_FIT_KW = dict(backend="advi", draws=60, advi_iters=800, seed=0)

# The injected covariate-moving row: a NEW Croatia match dated BETWEEN Croatia's
# 2023-06-10 and 2024-01-15 in-panel fixtures. If it reached the < cutoff panel it
# would become the new predecessor of the 2024-01-15 match (rest_days 219 -> 45)
# and add a fresh observed training row — moving the transform AND the fitted beta.
_INJECT = normalize_results(pd.DataFrame(
    [("2023-12-01", "Croatia", "Italy", 1, 0, "Friendly", "London", "England", True)],
    columns=["date", "home_team", "away_team", "home_score", "away_score",
             "tournament", "city", "country", "neutral"],
))


def _cfg(enabled):
    cfg = copy.deepcopy(load_config())
    cfg["model"]["covariates"]["enabled"] = list(enabled)
    return cfg


def _write_injected(store, *, observed_at):
    """Append the covariate-moving Croatia row to ``store`` with the given bitemporal
    stamp. ``observed_at = valid_as_of`` so a POST-cutoff stamp is hidden by
    ``read(cutoff)`` (leak gate) and a PRE-cutoff stamp is visible (teeth)."""
    row = _INJECT.copy()
    row["observed_at"] = pd.Timestamp(observed_at)
    row["valid_as_of"] = pd.Timestamp(observed_at)
    store.write("results", row, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")


def _croatia_panel_rest(store, cutoff, cfg):
    """rest_days the < cutoff panel assigns to Croatia's 2024-01-15 match, plus the
    row count + the home-side training-column nanmean — the three quantities the
    injected row would move IF it leaked into the panel."""
    mp = to_match_panel(features.build(cutoff, store, cfg))
    cro = mp[(mp["home_team"] == "Croatia")
             & (mp["date"] == pd.Timestamp("2024-01-15"))]
    rest = float(cro["rest_days"].iloc[0]) if len(cro) else None
    return rest, len(mp), float(np.nanmean(mp["rest_days"].to_numpy()))


# --------------------------------------------------------------------------- #
# (0) The leak vector is real — non-vacuity for the negative gate (FAST, no fit) #
# --------------------------------------------------------------------------- #
def test_covariate_leak_vector_is_non_vacuous(small_store):
    """TEETH for the negative gate (panel-level, fast): the injected row is excluded
    by ``read(cutoff)`` when stamped POST-cutoff, but WOULD move the covariate panel
    if it were admitted. Proven by writing the SAME row PRE-cutoff and watching the
    panel change. If this ever passes vacuously (PRE == BASELINE) the fit-level
    negative gate below is meaningless and must be revisited.

    This isolates the store-gating contract decisively and without sampling, exactly
    mirroring the count-mode teeth in ``test_leakage_model.py``.
    """
    cfg = _cfg(["rest_days"])
    base_rest, base_rows, base_mean = _croatia_panel_rest(small_store, CUTOFF, cfg)
    assert base_rest == 219.0, "baseline: Croatia's 2024-01-15 predecessor is 2023-06-10"

    # POST-cutoff stamp: read(cutoff) must EXCLUDE it -> panel unchanged.
    _write_injected(small_store, observed_at="2024-09-01")
    vis = small_store.read("results", cutoff=CUTOFF)
    assert not (pd.to_datetime(vis["date"]) == pd.Timestamp("2023-12-01")).any(), (
        "the POST-cutoff-stamped row must NOT be visible to read(cutoff) — the "
        "bitemporal observed_at/valid_as_of <= cutoff masking is the gate"
    )
    post_rest, post_rows, post_mean = _croatia_panel_rest(small_store, CUTOFF, cfg)
    assert (post_rest, post_rows, post_mean) == (base_rest, base_rows, base_mean), (
        "POST-cutoff row changed the covariate panel — store gating failed"
    )

    # PRE-cutoff stamp on the SAME row: read(cutoff) INCLUDES it -> panel MOVES.
    # (Fresh store so the two stamps don't both land in one parquet.)
    leaky = _fresh_store_like(small_store)
    _write_injected(leaky, observed_at="2023-12-02")
    vis2 = leaky.read("results", cutoff=CUTOFF)
    assert (pd.to_datetime(vis2["date"]) == pd.Timestamp("2023-12-01")).any(), (
        "the PRE-cutoff-stamped row must BE visible to read(cutoff)"
    )
    leak_rest, leak_rows, leak_mean = _croatia_panel_rest(leaky, CUTOFF, cfg)
    assert leak_rest == 45.0, "leaked predecessor is 2023-12-01 -> rest_days 219 -> 45"
    assert leak_rows == base_rows + 1, "the leaked row adds a training row"
    assert leak_mean != base_mean, "the leaked row moves the transform's training mean"
    # The crux: invariant under the POST stamp, MOVED under the PRE stamp — so a
    # post-cutoff leak WOULD move the panel and the negative gate has teeth.
    assert (post_rest, post_mean) == (base_rest, base_mean)
    assert (leak_rest, leak_mean) != (base_rest, base_mean)


def _fresh_store_like(small_store):
    """A second small_store seeded identically, in a sibling tmp dir, so the PRE/POST
    injections are written to DISTINCT parquet files (never co-mingled)."""
    from wcmodel.data.store import BitemporalStore
    import tests.data.conftest as cf

    root = small_store.root.parent / "leaky_store"
    root.mkdir(exist_ok=True)
    store = BitemporalStore(root=root)
    results = normalize_results(cf._RAW_RESULTS)
    store.write("results", results, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    venues = cf._VENUES.copy()
    venues["valid_as_of"] = pd.Timestamp("1900-01-01")
    venues["observed_at"] = pd.Timestamp("1900-01-01")
    store.write("venues", venues, policy=Policy.POINT_IN_TIME,
                keys=["city"], source="venues_ref", source_version="test")
    return store


# --------------------------------------------------------------------------- #
# (1) THE NEGATIVE GATE — post-cutoff covariate must NOT move the forecast      #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_post_cutoff_covariate_does_not_leak_into_as_of_forecast(small_store):
    """NEGATIVE (the leak gate). Fit + predict an as-of-cutoff forecast ``f1`` with
    ``rest_days`` IN THE MODEL. Then inject a POST-cutoff Croatia row (``observed_at
    = valid_as_of > cutoff``) that WOULD change Croatia's rest_days IF it leaked.
    Re-fit at the SAME cutoff over the mutated store. The new forecast must be
    BYTE-IDENTICAL to ``f1`` — the post-cutoff covariate did NOT leak into the as-of
    forecast. This proves the covariate path inherits ``store.read(cutoff)``'s gating
    AND the ``< cutoff``-only transform.

    Non-vacuity for THIS gate is supplied by
    ``test_covariate_leak_vector_is_non_vacuous`` (the same row, stamped pre-cutoff,
    moves the panel) and by the positive control + revert-proof below.
    """
    cfg = _cfg(["rest_days"])
    f1 = fit(CUTOFF, small_store, config=cfg, **_FIT_KW)
    p1 = f1.predict_1x2("Brazil", "Argentina", neutral=True)
    mean1 = f1.covariate_transforms["rest_days"].mean
    sd1 = f1.covariate_transforms["rest_days"].sd

    # Inject the post-cutoff covariate revision and RE-FIT at the SAME cutoff.
    _write_injected(small_store, observed_at="2024-09-01")
    f2 = fit(CUTOFF, small_store, config=cfg, **_FIT_KW)
    p2 = f2.predict_1x2("Brazil", "Argentina", neutral=True)

    assert p2 == p1, "post-cutoff covariate leaked into the as-of-cutoff forecast"
    # The PERSISTED transform is also untouched (the < cutoff training panel is the
    # same), so the standardization itself never saw the post-cutoff row.
    assert f2.covariate_transforms["rest_days"].mean == mean1
    assert f2.covariate_transforms["rest_days"].sd == sd1


# --------------------------------------------------------------------------- #
# (2) POSITIVE CONTROL + REVERT-PROOF — the covariate term is genuinely live    #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_covariate_positive_control_and_revert_proof(small_store):
    """NON-VACUITY. The negative gate is only meaningful if the covariate actually
    moves the forecast when present BEFORE the cutoff. Two complementary proofs:

      POSITIVE CONTROL — inject the SAME Croatia row PRE-cutoff (``observed_at =
      valid_as_of < cutoff``) so it IS in the ``< cutoff`` panel. It shifts Croatia's
      rest_days (219 -> 45, +1 training row), moving the fitted transform and beta, so
      the forecast must DIFFER from the no-injection ``rest_days`` forecast. (If it
      did not, the covariate would be inert and the negative gate vacuous.)

      REVERT-PROOF — the SAME baseline fixture predicted with ``enabled=[]`` (the
      covariate DROPPED from the model) must DIFFER from the ``enabled=["rest_days"]``
      forecast. This proves the ``beta_rest_days`` term is live, not a no-op the
      negative gate trivially preserves.
    """
    cfg_on = _cfg(["rest_days"])
    base = fit(CUTOFF, small_store, config=cfg_on, **_FIT_KW)
    p_on = base.predict_1x2("Brazil", "Argentina", neutral=True)

    # REVERT-PROOF: dropping the covariate (enabled=[]) changes the forecast.
    cfg_off = _cfg([])
    off = fit(CUTOFF, small_store, config=cfg_off, **_FIT_KW)
    assert off.covariate_transforms == {}, "enabled=[] must fit no transform"
    assert "beta_rest_days" not in off.idata.posterior, "enabled=[] must add no beta"
    p_off = off.predict_1x2("Brazil", "Argentina", neutral=True)
    assert p_off != p_on, (
        "covariate term is inert (revert-proof failed): enabled=[] and "
        "enabled=['rest_days'] give the same forecast"
    )

    # POSITIVE CONTROL: a rest_days difference present BEFORE the cutoff DOES move
    # the forecast (the same row that the negative gate proves does NOT leak when
    # stamped post-cutoff).
    leaky = _fresh_store_like(small_store)
    _write_injected(leaky, observed_at="2023-12-02")    # PRE-cutoff -> in the panel
    moved = fit(CUTOFF, leaky, config=cfg_on, **_FIT_KW)
    p_moved = moved.predict_1x2("Brazil", "Argentina", neutral=True)
    assert p_moved != p_on, (
        "positive control failed: a pre-cutoff rest_days change did NOT move the "
        "forecast — the canary's negative gate would be vacuous"
    )
    # And the persisted transform itself moved (the < cutoff training panel changed).
    assert moved.covariate_transforms["rest_days"].mean != \
        base.covariate_transforms["rest_days"].mean


# --------------------------------------------------------------------------- #
# (3) THE TRANSFORM IS FIT ON < cutoff ROWS ONLY                                #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_transform_mean_is_computed_on_strictly_pre_cutoff_rows(small_store):
    """The standardization transform's ``mean`` is computed from ``< cutoff`` rows
    only. Two independent checks:

      (a) HAND-COMPUTED: the persisted ``mean`` equals the nanmean of the home-side
          ``rest_days`` training column from ``features.build(cutoff)`` (the
          ``date < cutoff_day`` panel) — i.e. exactly what ``_build_covariates`` /
          ``CovariateTransform.fit`` standardize on, no future rows.

      (b) POST-CUTOFF-INVARIANT: injecting a post-cutoff covariate row does NOT change
          the persisted ``mean``/``sd`` (it is excluded from the training panel by the
          bitemporal read), the complement of the positive control where a pre-cutoff
          row DOES move the mean.
    """
    cfg = _cfg(["rest_days"])
    post = fit(CUTOFF, small_store, config=cfg, **_FIT_KW)
    t = post.covariate_transforms["rest_days"]

    # (a) Persisted mean == nanmean over the < cutoff training column.
    mp = to_match_panel(features.build(CUTOFF, small_store, cfg))
    expected_mean = float(np.nanmean(mp["rest_days"].to_numpy()))
    assert t.mean == expected_mean, (
        "transform mean is not the < cutoff training-column nanmean — it may be "
        "reading rows past the cutoff"
    )

    # (b) A post-cutoff row leaves the persisted transform untouched.
    _write_injected(small_store, observed_at="2024-09-01")
    post2 = fit(CUTOFF, small_store, config=cfg, **_FIT_KW)
    t2 = post2.covariate_transforms["rest_days"]
    assert (t2.mean, t2.sd) == (t.mean, t.sd), (
        "post-cutoff row changed the standardization transform — it must be fit on "
        "< cutoff rows only"
    )
