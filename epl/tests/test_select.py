"""Selection: the window guard, the shared fit, and the adoption arithmetic.

THE TWO LOAD-BEARING PROPERTIES.

1. **The shared fit is not a shortcut that changes the answer.** ``run_sweep``
   fits once per cutoff and prices every predict-time variant off that one
   posterior. If the sharing perturbed a forecast, every within-pass comparison
   would be measuring the sharing as well as the lever. So a real sweep pass's
   control variant is compared with ``np.array_equal`` against the bare
   ``dcfit.fit_epl`` + ``Posterior.predict_1x2`` path — the same path that
   produced ``reports/epl_walkforward.md``.

2. **The tuning window cannot be widened by accident.** ``run_sweep`` refuses
   the confirmatory window without ``second_look=True`` and the holdout without
   ``holdout=True``, and it asserts on the frame it actually built rather than
   on a flag the caller passed.

The adoption rule is EXECUTED by :func:`epl.select.adopt`, so it is tested as
code: every condition is shown to be able to reject on its own, which is what
stops a rule from being a decoration on a decision already made.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from epl import anchor as anchor_mod, baseline, dcfit, fit as epl_fit
from epl import freeze, improve, paths, score as score_mod, select, windows
from epl.improve import Improvements, OFF
from epl.schema import sort_for_walk_forward

CUTOFF = "2017-01-07"          # a TUNING-window date, as everywhere in epl/tests


@pytest.fixture(scope="module")
def played() -> pd.DataFrame:
    m = baseline.load_matches()
    return sort_for_walk_forward(m.loc[m["played"]])


# ==========================================================================
# the window guard
# ==========================================================================
def test_the_confirm_window_needs_second_look_declared(played):
    with pytest.raises(ValueError, match="SECOND LOOK"):
        select.run_sweep(OFF, window="confirm", matches=played, limit=1,
                         verbose=False)


def test_the_holdout_needs_holdout_declared(played):
    with pytest.raises(ValueError, match="fresh holdout"):
        select.run_sweep(OFF, window="holdout", matches=played, limit=1,
                         verbose=False)


def test_a_fit_arm_may_not_carry_predict_gates(played):
    with pytest.raises(ValueError, match="predict-time gates"):
        select.run_sweep(Improvements(home_term_blend=0.5), matches=played,
                         limit=1, verbose=False)


def test_the_tuning_frame_is_asserted_not_assumed(monkeypatch, played):
    """The guard reads the frame, so a mis-sliced window fails loudly."""
    monkeypatch.setattr(improve, "_WINDOWS",
                        dict(improve._WINDOWS, tune=windows.SCORE_SEASONS))
    with pytest.raises(ValueError, match="non-tuning season"):
        select.run_sweep(OFF, window="tune", matches=played, limit=1,
                         verbose=False)


# ==========================================================================
# the fit arm
# ==========================================================================
def test_fit_arm_strips_predict_gates_and_keeps_fit_gates():
    v = Improvements(decay_half_life_days=180.0, congestion=True,
                     refit_cadence_weeks=2, break_widen_strength=0.35,
                     break_widen_january=True, home_term_blend=1.0,
                     home_term_half_life_days=90.0)
    arm = select.fit_arm(v)
    assert arm.decay_half_life_days == 180.0
    assert arm.congestion is True
    assert arm.refit_cadence_weeks == 2
    assert not (arm.i2 or arm.i3)
    assert select.fit_arm(arm) == arm                       # idempotent
    for over in select.PREDICT_GRID:                        # the grid shares it
        assert select.fit_arm(select.compose(arm, over)) == arm


def test_variants_sharing_an_arm_produce_the_same_model_config():
    """The justification for sharing a fit, checked rather than asserted."""
    arm = Improvements(decay_half_life_days=180.0)
    a = improve.wcmodel_config(select.compose(arm, {"home_term_blend": 1.0}))
    b = improve.wcmodel_config(
        select.compose(arm, {"break_widen_strength": 0.2}))
    a.pop("epl_improvements")
    b.pop("epl_improvements")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_the_arm_of_an_i1a_or_i4_variant_is_not_the_off_arm():
    """The converse: a fit-touching gate may NOT ride on another arm's fit."""
    for v in (Improvements(decay_half_life_days=180.0),
              Improvements(congestion=True)):
        assert select.fit_arm(v) != OFF
        assert v.touches_the_fit()


def test_the_predict_grid_gives_every_dial_a_shape():
    """B1 needs at least three points per dial plus the zero point."""
    variants = [select.compose(OFF, o) for o in select.PREDICT_GRID]
    assert sum(1 for v in variants if v.is_off()) == 1, "exactly one control"
    assert len({v.home_term_blend for v in variants if v.i3}) >= 2
    assert len({v.break_widen_strength for v in variants if v.i2}) >= 3
    assert len({v.spec for v in variants}) == len(variants), "no duplicates"


# ==========================================================================
# the shared posterior view
# ==========================================================================
def test_the_shared_view_changes_no_forecast(played):
    """A real fit, priced through the base and through the view."""
    cfg = freeze.frozen_wcmodel_config()
    anc = anchor_mod.Anchor(played, freeze.frozen_elo_config())
    store = epl_fit.build_store(played)
    with epl_fit.config_read_once(cfg):
        post, _ = dcfit.fit_epl(pd.Timestamp(CUTOFF), store, anc, cfg,
                                matches=played,
                                feature_cache_dir=paths.FIT_CACHE_DIR)
    pairs = [(h, a) for h, a in zip(played["home_key"].astype(str),
                                    played["away_key"].astype(str))
             if h in post._idx and a in post._idx][:8]
    select._assert_view_is_inert(post, pairs)             # raises if it moved

    view = select._SharedView(post)
    view._cfg = dict(view._cfg)          # a variant rebinding its own namespace
    assert post._cfg is not view._cfg
    assert post.idata is view.idata      # ...over the SAME fitted arrays


def test_the_view_check_is_not_vacuous(played, monkeypatch):
    """A view that DID move the forecast must be caught."""
    class Broken(select._SharedView):
        def predict_1x2(self, home, away, **kw):
            p = super().predict_1x2(home, away, **kw)
            return {k: v for k, v in zip(p, (0.5, 0.3, 0.2))}

    cfg = freeze.frozen_wcmodel_config()
    anc = anchor_mod.Anchor(played, freeze.frozen_elo_config())
    store = epl_fit.build_store(played)
    with epl_fit.config_read_once(cfg):
        post, _ = dcfit.fit_epl(pd.Timestamp(CUTOFF), store, anc, cfg,
                                matches=played,
                                feature_cache_dir=paths.FIT_CACHE_DIR)
    pairs = [(h, a) for h, a in zip(played["home_key"].astype(str),
                                    played["away_key"].astype(str))
             if h in post._idx and a in post._idx][:4]
    monkeypatch.setattr(select, "_SharedView", Broken)
    with pytest.raises(AssertionError, match="changed the forecast"):
        select._assert_view_is_inert(post, pairs)


def test_two_i2_variants_cannot_leak_into_each_other(played):
    """I2 swaps the widening strength on its posterior; views keep that local."""
    cfg = freeze.frozen_wcmodel_config()
    anc = anchor_mod.Anchor(played, freeze.frozen_elo_config())
    store = epl_fit.build_store(played)
    with epl_fit.config_read_once(cfg):
        post, _ = dcfit.fit_epl(pd.Timestamp(CUTOFF), store, anc, cfg,
                                matches=played,
                                feature_cache_dir=paths.FIT_CACHE_DIR)
    base_strength = post._cfg["widening"]["strength"]
    clock = improve.BreakClock(played, january=False)
    weak = Improvements(break_widen_strength=0.10)
    strong = Improvements(break_widen_strength=0.35)
    h, a = next((h, a) for h, a in zip(played["home_key"].astype(str),
                                       played["away_key"].astype(str))
                if h in post._idx and a in post._idx)

    outs = []
    for imp in (weak, strong, weak):
        fc = improve.Forecaster(select._SharedView(post), imp,
                                pd.Timestamp(CUTOFF), clock=clock)
        outs.append([fc.predict_1x2(h, a)[k] for k in score_mod.OUTCOMES])
    assert outs[0] == outs[2], "the strong variant contaminated the weak one"
    assert post._cfg["widening"]["strength"] == base_strength


# ==========================================================================
# the adoption rule, executed
# ==========================================================================
def _cmp(delta=-0.002, ll=-0.004, seasons=4, sd=0.01, n=1520):
    return {"challenger": "x", "delta": delta, "delta_log_loss": ll,
            "seasons_improved": seasons, "paired_sd": sd,
            "mde80": select.tuning_mde(sd, n), "ci95_week": [-0.003, -0.001]}


def test_a_clean_winner_is_adopted():
    out = select.adopt(_cmp(), touches_the_fit=False, floor=0.0, shape_ok=True)
    assert out["ADOPT"] is True


@pytest.mark.parametrize("kw, flag", [
    (dict(delta=-0.0009), "A_beats_threshold"),               # A: below thr
    (dict(seasons=2), "B2_seasons"),                          # B2: unstable
    (dict(ll=+0.004), "B3_log_loss_agrees"),                  # B3: reversed
])
def test_each_condition_can_reject_on_its_own(kw, flag):
    out = select.adopt(_cmp(**kw), touches_the_fit=False, floor=0.0,
                       shape_ok=True)
    assert out[flag] is False and out["ADOPT"] is False


def test_curve_shape_can_reject_on_its_own():
    out = select.adopt(_cmp(), touches_the_fit=False, floor=0.0,
                       shape_ok=False, shape_note="isolated point")
    assert out["B1_curve_shape"] is False and out["ADOPT"] is False


def test_the_noise_floor_applies_only_to_fit_touching_gates():
    """A gain of 0.002 against a 0.001 seed floor is inside optimiser noise."""
    predict_side = select.adopt(_cmp(), touches_the_fit=False, floor=0.001,
                                shape_ok=True)
    fit_side = select.adopt(_cmp(), touches_the_fit=True, floor=0.001,
                            shape_ok=True)
    assert predict_side["ADOPT"] is True
    assert fit_side["B4_above_noise_floor"] is False
    assert fit_side["ADOPT"] is False
    assert select.adopt(_cmp(), touches_the_fit=True, floor=0.0001,
                        shape_ok=True)["ADOPT"] is True


def test_the_threshold_is_the_one_in_the_rule():
    assert select.ADOPTION_RULE["threshold"] == -0.0010
    just_short = select.adopt(_cmp(delta=-0.00099), touches_the_fit=False,
                              floor=0.0, shape_ok=True)
    exactly = select.adopt(_cmp(delta=-0.0010), touches_the_fit=False,
                           floor=0.0, shape_ok=True)
    assert just_short["ADOPT"] is False and exactly["ADOPT"] is True


def test_the_mde_constant_matches_the_walkforward_convention():
    """Both windows quote the 80%-power MDE on one convention."""
    sd, n = 0.039932, 2280
    assert select.tuning_mde(sd, n) == pytest.approx(0.00234, abs=5e-6)
    with pytest.raises(ValueError):
        select.tuning_mde(sd, n, power=0.9)


# ==========================================================================
# the comparison is paired on a shared index
# ==========================================================================
def test_compare_refuses_to_score_two_variants_on_different_fixtures(tmp_path):
    """A variant may never be scored on an easier subset than its incumbent."""
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    m = baseline.load_matches()
    played = sort_for_walk_forward(m.loc[m["played"]])
    tune = played.loc[played["season"] == "2016/17"].head(20)
    ids = tune["match_id"].astype(str).tolist()
    rows_a = {"key": "k", "season": "2016/17", "spec": "A",
              "match_ids": ids, "probs": [[0.4, 0.3, 0.3]] * len(ids)}
    rows_b = {"key": "k", "season": "2016/17", "spec": "B",
              "match_ids": ids[:10], "probs": [[0.4, 0.3, 0.3]] * 10}
    a.write_text(json.dumps(rows_a) + "\n")
    b.write_text(json.dumps(rows_b) + "\n")
    out = select.compare(a, b, matches=m, n_boot=200)
    assert out["n"] <= 10, "the comparison must fall back to the shared index"
    assert out["delta"] == pytest.approx(0.0, abs=1e-12)


def test_a_ledger_that_mixes_variants_is_refused(tmp_path):
    p = tmp_path / "mixed.jsonl"
    p.write_text(json.dumps({"key": "1", "season": "2016/17", "spec": "A",
                             "match_ids": [], "probs": []}) + "\n"
                 + json.dumps({"key": "2", "season": "2016/17", "spec": "B",
                               "match_ids": [], "probs": []}) + "\n")
    with pytest.raises(ValueError, match="mixes variants"):
        select._probs(p)
