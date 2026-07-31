"""OA Plan 2 V6: the stacking arm S — an ordered-logit blender over the
[DC, odds, elo-ordlogit] 1X2 forecasts.

The arm is 1X2-only STRUCTURALLY: its inputs are three 1X2 vectors (reduced
to one latent location each — the mean cumulative logit) and its output is a
proportional-odds 1X2, so no scoreline/grid surface exists to leak a second
map. It trains on the SAME dev-ledger OOF rows the (w, de-vig) selection
consumes, under the SAME frozen monthly fold structure (finding 9): fold t is
scored with parameters fitted on folds < t (leakage sentinel below), and the
FINAL parameters (the deployment head, hashed into the V8 lock via the
selection trace) are fitted on all dev months. Rows without admissible odds
are excluded — the odds feature does not exist for them; a missing DC or
elo-ordlogit base row is a pipeline BUG and errors (V7's exact-cardinality
stance). The de-vig feeding the odds feature goes through the OA gate: the
set is exactly {shin, multiplicative}, 'basic' is a label, 'power' can enter
nothing (finding 13).
"""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

import numpy as np
import pytest
from scipy.special import expit

from wcmodel.eval import arms as arms_mod
from wcmodel.eval.arms import (
    STACK_FEATURE_ORDER,
    StackFold,
    StackingFit,
    StackParams,
    oof_stacking,
    predict_stacked,
)
from wcmodel.eval.ledger import LedgerWriter
from wcmodel.model.calibration import rps

UTC = timezone.utc


def _dev_row(fixture, day, arm, probs, *, hash_="b" * 64):
    y, m, d = (int(part) for part in day.split("-"))
    return {
        "fixture_id": fixture,
        "pool": "dev",
        "date": day,
        "home": f"H-{fixture}",
        "away": f"A-{fixture}",
        "kickoff_utc": datetime(y, m, d, 18, 0, tzinfo=UTC),
        "t_issue": datetime(y, m, d, 9, 0, tzinfo=UTC),
        "training_cutoff": datetime(y, m, d, 9, 0, tzinfo=UTC),
        "arm": arm,
        "p_home": probs[0],
        "p_draw": probs[1],
        "p_away": probs[2],
        "issued_git": "deadbee",
        "odds_snapshot_hash": hash_,
    }


def _write_ledger(path, rows):
    with LedgerWriter(path) as writer:
        for row in rows:
            writer.append(row)
    return path


def _manifest(ids):
    return {"rule": "synthetic", "fixtures": [{"match_id": i} for i in ids]}


def _base_rows(fixture, day, dc, odds, elo, *, method="shin"):
    """One fixture's three base-arm rows. Only the odds row carries a
    snapshot hash — the DC and elo arms are odds-free by construction."""
    return [
        _dev_row(fixture, day, "dev_dc", dc, hash_=None),
        _dev_row(fixture, day, f"dev_odds_{method}", odds),
        _dev_row(fixture, day, "dev_elo_ordlogit", elo, hash_=None),
    ]


def _world(eta):
    """A fixed proportional-odds world (c1=-0.6, c2=0.6): the 1X2 vector at
    latent location eta, keyed (home, draw, away)."""
    p_away = float(expit(-0.6 - eta))
    p_away_draw = float(expit(0.6 - eta))
    return (1.0 - p_away_draw, p_away_draw - p_away, p_away)


_LABELS = ("home", "draw", "away")


def _informative_ledger(rng, months, per_month, *, invert_months=()):
    """Synthetic dev rows where the ODDS arm is the truth-generating forecast
    and DC / elo-ordlogit are exchangeable noise (independent latent draws).
    In ``invert_months`` the odds arm's forecast is MIRRORED (home<->away) —
    anti-predictive on purpose, for the fold-isolation sentinel."""
    rows, outcomes, ids = [], {}, []
    for month in months:
        for k in range(per_month):
            fixture = f"dev-{month}-{k:03d}"
            truth = _world(rng.normal(0.0, 1.6))
            outcome = _LABELS[int(rng.choice(3, p=truth))]
            odds = truth[::-1] if month in invert_months else truth
            dc = _world(rng.normal(0.0, 1.6))
            elo = _world(rng.normal(0.0, 1.6))
            day = f"{month}-{3 + (k % 25):02d}"
            rows += _base_rows(fixture, day, dc, odds, elo)
            outcomes[fixture] = outcome
            ids.append(fixture)
    return rows, outcomes, ids


def _probs_dict(triple):
    return dict(zip(_LABELS, triple))


# ------------------------------------------------------------- fit + recover


def test_stacker_loads_on_the_informative_arm_and_is_deterministic(tmp_path):
    """[LOAD-BEARING] With the odds arm generating the outcomes and the other
    two arms pure noise, the fitted head must (a) put clearly more weight on
    the odds feature, (b) score OOF close to the informative arm and clearly
    better than the noise arms, and (c) be bitwise reproducible — no RNG
    anywhere in the fit."""
    rng = np.random.default_rng(7)
    months = [f"2023-{m:02d}" for m in range(1, 7)]
    rows, outcomes, ids = _informative_ledger(rng, months, 50)
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)

    fit = oof_stacking(path, outcomes=outcomes, manifest=_manifest(ids),
                       devig_method="shin")
    assert isinstance(fit, StackingFit)
    assert fit.devig_method == "shin"
    assert fit.n_fixtures == 300
    assert fit.n_excluded_no_odds == 0
    assert fit.params.b_odds > fit.params.b_dc + 0.4
    assert fit.params.b_odds > fit.params.b_elo + 0.4
    assert [f.month for f in fit.folds] == months[2:]

    # Pooled per-fixture RPS of each BASE arm over the same fold-scored
    # fixtures (months 3+), from the same construction.
    scored = {f for f in ids if f[4:11] >= months[2]}
    arm_rows = {}
    for row in rows:
        arm_rows.setdefault(row["arm"], {})[row["fixture_id"]] = (
            row["p_home"], row["p_draw"], row["p_away"])

    def arm_rps(arm):
        return float(np.mean([
            rps(_probs_dict(arm_rows[arm][f]), outcomes[f]) for f in scored]))

    assert fit.oof_rps < arm_rps("dev_dc") - 0.02
    assert fit.oof_rps < arm_rps("dev_elo_ordlogit") - 0.02
    assert fit.oof_rps < arm_rps("dev_odds_shin") + 0.01

    again = oof_stacking(path, outcomes=outcomes, manifest=_manifest(ids),
                         devig_method="shin")
    assert again.params == fit.params
    assert again.folds == fit.folds
    assert again.oof_rps == fit.oof_rps


def test_fold_fit_never_sees_its_own_month(tmp_path):
    """[LOAD-BEARING leakage sentinel] The ledger ends at March, so a fold
    fit that leaked its own month would be fitting on EXACTLY the final fit's
    rows — the two parameter sets would coincide. March is built
    anti-predictive (mirrored odds forecasts) and 2x heavier than Jan+Feb, so
    the honest fold-March head (fitted on Jan+Feb only) keeps a strongly
    positive b_odds while the final head (fitted on everything) is dragged
    far down. The recorded gap IS the proof of isolation."""
    rng = np.random.default_rng(11)
    rows, outcomes, ids = _informative_ledger(
        rng, ["2023-01", "2023-02"], 60)
    march_rows, march_outcomes, march_ids = _informative_ledger(
        rng, ["2023-03"], 240, invert_months=("2023-03",))
    rows += march_rows
    outcomes.update(march_outcomes)
    ids += march_ids

    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)
    fit = oof_stacking(path, outcomes=outcomes, manifest=_manifest(ids),
                       devig_method="shin")
    assert [f.month for f in fit.folds] == ["2023-03"]
    fold = fit.folds[0]
    assert fold.n_train_fixtures == 120
    assert fold.params.b_odds > 0.5
    assert fold.params.b_odds - fit.params.b_odds > 0.5
    assert fold.params != fit.params


# ----------------------------------------------------------- diet + refusals


def test_oof_stacking_excludes_odds_absent_and_errors_on_missing_base(tmp_path):
    """No odds row -> the odds feature does not exist -> the fixture is
    EXCLUDED and counted. A missing DC or elo-ordlogit row for a fixture the
    ledger knows is a pipeline BUG (those arms need no odds) -> error. An
    odds row with a null snapshot hash is incoherent -> error."""
    rng = np.random.default_rng(3)
    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = _informative_ledger(rng, months, 20)

    uncovered = [
        _dev_row("dev-none-1", "2023-01-05", "dev_dc", _world(0.3), hash_=None),
        _dev_row("dev-none-1", "2023-01-05", "dev_elo_ordlogit",
                 _world(-0.2), hash_=None),
    ]
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows + uncovered)
    fit = oof_stacking(
        path, outcomes={**outcomes, "dev-none-1": "home"},
        manifest=_manifest(ids + ["dev-none-1"]), devig_method="shin")
    assert fit.n_fixtures == 60
    assert fit.n_excluded_no_odds == 1

    missing_dc = [r for r in rows
                  if not (r["fixture_id"] == ids[0] and r["arm"] == "dev_dc")]
    path = _write_ledger(tmp_path / "missing_dc.parquet", missing_dc)
    with pytest.raises(ValueError, match="dev_dc"):
        oof_stacking(path, outcomes=outcomes, manifest=_manifest(ids),
                     devig_method="shin")

    null_hash = [dict(r) for r in rows]
    for r in null_hash:
        if r["fixture_id"] == ids[0] and r["arm"] == "dev_odds_shin":
            r["odds_snapshot_hash"] = None
    path = _write_ledger(tmp_path / "null_hash.parquet", null_hash)
    with pytest.raises(ValueError, match="hash"):
        oof_stacking(path, outcomes=outcomes, manifest=_manifest(ids),
                     devig_method="shin")


def test_oof_stacking_errors_when_a_covered_fixture_lacks_its_bases(tmp_path):
    """[LOAD-BEARING, B2-2] A covered fixture (rows with a non-null
    odds_snapshot_hash anywhere in the frame) must carry its stacking base
    block — silence would make the fixture VANISH from the stack. Two
    escapes are closed, both errors NAMING the fixture: (a) a covered
    fixture with none of the three base arms at all (e.g. only blend rows
    were archived); (b) a covered fixture whose odds row exists only under
    the OTHER de-vig method — previously counted as 'odds-absent', which a
    covered fixture never is."""
    rng = np.random.default_rng(21)
    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = _informative_ledger(rng, months, 12)

    lost = rows + [_dev_row("dev-lost", "2023-01-05", "dev_blend_shin_w0.10",
                            _world(0.2))]
    path = _write_ledger(tmp_path / "no_bases.parquet", lost)
    with pytest.raises(ValueError, match="dev-lost"):
        oof_stacking(path, outcomes={**outcomes, "dev-lost": "home"},
                     manifest=_manifest(ids + ["dev-lost"]),
                     devig_method="shin")

    other_method = rows + _base_rows("dev-other", "2023-01-06", _world(0.1),
                                     _world(0.4), _world(-0.2),
                                     method="multiplicative")
    path = _write_ledger(tmp_path / "other_method.parquet", other_method)
    with pytest.raises(ValueError, match="dev-other"):
        oof_stacking(path, outcomes={**outcomes, "dev-other": "away"},
                     manifest=_manifest(ids + ["dev-other"]),
                     devig_method="shin")


def test_oof_stacking_requires_outcomes_manifest_and_months(tmp_path):
    """Same dev-only diet as select_w: manifest membership at runtime, an
    outcome for every included fixture, and enough months for at least one
    scoreable fold."""
    rng = np.random.default_rng(5)
    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = _informative_ledger(rng, months, 12)
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)

    with pytest.raises(ValueError, match="manifest"):
        oof_stacking(path, outcomes=outcomes, manifest=_manifest(ids[:-1]),
                     devig_method="shin")

    short = dict(outcomes)
    del short[ids[0]]
    with pytest.raises(ValueError, match="outcome"):
        oof_stacking(path, outcomes=short, manifest=_manifest(ids),
                     devig_method="shin")

    rows2, outcomes2, ids2 = _informative_ledger(
        np.random.default_rng(6), ["2023-01", "2023-02"], 12)
    path2 = _write_ledger(tmp_path / "two_months.parquet", rows2)
    with pytest.raises(ValueError, match="month"):
        oof_stacking(path2, outcomes=outcomes2, manifest=_manifest(ids2),
                     devig_method="shin")


def test_oof_stacking_refuses_absent_outcome_class_in_training(tmp_path):
    """An absent outcome class leaves a threshold unidentified (the
    elo-ordlogit stance): a training slice with no draws must refuse rather
    than fit a degenerate head that scores as a real arm."""
    rng = np.random.default_rng(9)
    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = _informative_ledger(rng, months, 12)
    no_draws = {f: ("home" if o == "draw" else o) for f, o in outcomes.items()}
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)
    with pytest.raises(ValueError, match="draw"):
        oof_stacking(path, outcomes=no_draws, manifest=_manifest(ids),
                     devig_method="shin")


def test_stacking_devig_gate_is_the_oa_gate(tmp_path):
    """Finding 13 at the stacking arm's door: 'power' can enter nothing;
    'basic' is the reporting label for multiplicative and resolves to it —
    the fit consumes dev_odds_multiplicative rows and records the RESOLVED
    method."""
    rng = np.random.default_rng(13)
    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = [], {}, []
    for month in months:
        for k in range(12):
            fixture = f"dev-{month}-{k:03d}"
            truth = _world(rng.normal(0.0, 1.6))
            outcomes[fixture] = _LABELS[int(rng.choice(3, p=truth))]
            ids.append(fixture)
            rows += _base_rows(fixture, f"{month}-{3 + k:02d}", truth, truth,
                               truth, method="multiplicative")
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)

    with pytest.raises(ValueError, match="OA|power"):
        oof_stacking(path, outcomes=outcomes, manifest=_manifest(ids),
                     devig_method="power")

    fit = oof_stacking(path, outcomes=outcomes, manifest=_manifest(ids),
                       devig_method="basic")
    assert fit.devig_method == "multiplicative"
    assert fit.trace_payload()["devig_method"] == "multiplicative"


# ------------------------------------------------------------------ predict


def test_predict_stacked_contract_and_direction():
    """The head's output is a genuine 1X2 in the canonical keys; with a
    positive odds weight, a more home-leaning odds forecast moves the stacked
    forecast toward home. Boundary base probabilities (a point mass has an
    infinite cumulative logit) and wrong keys are refused."""
    params = StackParams(c1=-0.5, s=0.2, b_dc=0.3, b_odds=0.8, b_elo=0.1)
    flat = _probs_dict(_world(0.0))
    home_lean = _probs_dict(_world(1.5))

    base = {"dc": flat, "odds": flat, "elo_ordlogit": flat}
    p = predict_stacked(params, base)
    assert set(p) == {"home", "draw", "away"}
    assert all(0.0 < v < 1.0 for v in p.values())
    assert abs(sum(p.values()) - 1.0) < 1e-12

    leaning = predict_stacked(params, {**base, "odds": home_lean})
    assert leaning["home"] > p["home"]
    assert leaning["away"] < p["away"]

    with pytest.raises(ValueError):
        predict_stacked(params, {**base, "odds": {"home": 1.0, "draw": 0.0,
                                                  "away": 0.0}})
    with pytest.raises(ValueError):
        predict_stacked(params, {"dc": flat, "odds": flat})
    with pytest.raises(ValueError):
        predict_stacked(params, {**base, "market": flat})


def test_stacking_arm_is_structurally_1x2_only():
    """The 1X2-only property is STRUCTURAL: the module's public surface is
    exactly the ordered-logit head — nothing named for (or capable of
    emitting) a scoreline grid, so the arm cannot grow a second map without
    failing here first."""
    assert STACK_FEATURE_ORDER == ("dc", "odds", "elo_ordlogit")
    functions = {name for name, obj in inspect.getmembers(arms_mod,
                                                          inspect.isfunction)
                 if obj.__module__ == arms_mod.__name__
                 and not name.startswith("_")}
    assert functions == {"oof_stacking", "predict_stacked"}
    classes = {name for name, obj in inspect.getmembers(arms_mod,
                                                        inspect.isclass)
               if obj.__module__ == arms_mod.__name__
               and not name.startswith("_")}
    assert classes == {"StackParams", "StackFold", "StackingFit"}
    for name in functions | classes:
        assert "grid" not in name.lower()
        assert "scoreline" not in name.lower()


def test_trace_payload_is_json_ready_and_complete(tmp_path):
    """The payload rides inside the V6 selection trace the V8 lock hashes:
    it must serialize as-is and carry the deployment head (params), the
    feature order, the de-vig it consumed, and the full fold trace."""
    rng = np.random.default_rng(17)
    months = ["2023-01", "2023-02", "2023-03", "2023-04"]
    rows, outcomes, ids = _informative_ledger(rng, months, 20)
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)
    fit = oof_stacking(path, outcomes=outcomes, manifest=_manifest(ids),
                       devig_method="shin")

    payload = fit.trace_payload()
    assert json.dumps(payload, sort_keys=True)      # serializable as-is
    assert payload["devig_method"] == "shin"
    assert payload["feature_order"] == list(STACK_FEATURE_ORDER)
    assert set(payload["params"]) == {"c1", "s", "b_dc", "b_odds", "b_elo"}
    assert payload["n_fixtures"] == 80
    assert payload["n_excluded_no_odds"] == 0
    assert [f["month"] for f in payload["folds"]] == ["2023-03", "2023-04"]
    assert {"month", "n_train_fixtures", "n_fold_fixtures", "rps",
            "params"} <= set(payload["folds"][0])
    assert isinstance(payload["oof_rps"], float)
    assert isinstance(fit.folds[0], StackFold)
