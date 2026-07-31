"""OA Plan 2 V6: the E' per-draw blend + the frozen (w, de-vig) selection.

The blend is the PRODUCTION map with per-draw blended rates::

    lam_blend_d = (1 - w) * lam_model_d + w * lam_book

rho_d untouched, per-draw correction + renorm, mean over draws, widening —
never a second almost-right copy of the path (finding 3 closed by V2; V6
enters at the rate leg exactly as draw_api documents). The endpoint pins are
the whole point of the design: ``w=0`` must be BITWISE the incumbent
``production_grid`` on a REAL fitted Posterior (per-draw identity => identical
mean grid), and ``w=1`` must reproduce the de-vigged 1X2 within 1e-6 BY V2's
solve definition (constant book rates broadcast across the fixture's own rho
draws). There is deliberately NO monotonicity-in-w assertion — finding 15
ruled it unsound; continuity/normalization/determinism stand in for it.

``select_w`` is the FROZEN selection procedure (finding 9): monthly
chronological folds, burn-in first 2 months, fold t scored with the candidate
chosen on folds < t, objective mean canonical RPS, odds-absent rows excluded,
grid 0.00..1.00 step 0.05, tie -> smaller w. It consumes ONLY dev-ledger rows
(runtime dev-manifest membership check, scored-pool rows refused) — tested
here entirely on synthetic dev ledgers with a planted optimum and a leakage
sentinel proving fold t never sees fold t.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import arviz as az
import numpy as np
import pytest

from wcmodel.eval.blend import (
    BLEND_ARM_PREFIX,
    FOLD_SPEC,
    SELECTION_BURN_IN_MONTHS,
    W_GRID,
    blend_arm,
    blend_grid,
    blend_one_x_two,
    parse_blend_arm,
    select_w,
    write_selection_trace,
)
from wcmodel.eval.implied import (
    OA_DEVIG_METHODS,
    RESIDUAL_TOL,
    oa_devig,
    solve_implied_rates,
)
from wcmodel.eval.ledger import LedgerWriter
from wcmodel.model.calibration import rps
from wcmodel.model.draw_api import (
    PRODUCTION_MAX_GOALS,
    FixtureCtx,
    finalize_grid,
    grid_one_x_two,
    mean_grid_over_draws,
    production_grid,
)
from wcmodel.model.posterior import Posterior

from tests.model.conftest import fit_compact_real_posterior

UTC = timezone.utc


@pytest.fixture(scope="module")
def real_posterior(tmp_path_factory):
    """ONE real ADVI-fitted Posterior shared by this module's endpoint tests."""
    return fit_compact_real_posterior(tmp_path_factory.mktemp("blend_store"))


def _stub_posterior(likelihood="dixon_coles"):
    """Tiny hand-built Posterior (NO sampling) for guard-branch unit tests —
    the endpoint tests all run on the REAL fit (the test_implied pattern)."""
    params = {
        "att": np.zeros((1, 2, 2)),
        "def": np.zeros((1, 2, 2)),
        "mu": np.full((1, 2), 0.1),
        "home_adv": np.full((1, 2), 0.2),
        "rho": np.full((1, 2), -0.05),
    }
    return Posterior(az.from_dict({"posterior": params}), ["A", "B"],
                     likelihood, provisional_teams=set())


def _settled_pair(post):
    settled = [t for t in post.teams if t not in post.provisional_teams]
    assert len(settled) >= 2
    return settled[0], settled[1]


def _book_grid(post, lam_book, *, provisional):
    """V2's solve definition of the book map, finalized: constant rates
    broadcast across the fixture posterior's OWN rho draws, per-draw tau +
    renorm, mean, then the production widening/renorm leg."""
    rho = post._post("rho")
    S = rho.shape[-1]
    grid = mean_grid_over_draws(
        np.full(S, lam_book[0]), np.full(S, lam_book[1]),
        likelihood="dixon_coles", rho=rho, max_goals=PRODUCTION_MAX_GOALS)
    return finalize_grid(grid, post, provisional=provisional)


# ------------------------------------------------------------- endpoints


@pytest.mark.slow
def test_w0_is_bitwise_the_incumbent_production_grid(real_posterior):
    """[LOAD-BEARING] At w=0 the per-draw blended rates ARE the model's
    per-draw rates ((1-0)*lam + 0*book is an IEEE identity for finite positive
    rates), so the blend must be BITWISE the incumbent production grid — for
    every production fixture context, on a REAL Posterior, for any book rates.
    """
    post = real_posterior
    home, away = _settled_pair(post)
    prov = sorted(post.provisional_teams)[0]
    contexts = [
        FixtureCtx(home=home, away=away),
        FixtureCtx(home=home, away=away, neutral=True),
        FixtureCtx(home=home, away=away, host_factor=1.4),
        FixtureCtx(home=home, away=prov, neutral=True),   # widening branch
    ]
    for ctx in contexts:
        incumbent = production_grid(post, ctx)
        blended = blend_grid(post, ctx, (1.7, 1.1), 0.0)
        assert np.array_equal(blended, incumbent), ctx
        assert blend_one_x_two(post, ctx, (1.7, 1.1), 0.0) \
            == grid_one_x_two(incumbent), ctx


@pytest.mark.slow
def test_w1_reproduces_the_devigged_vector_within_1e6(real_posterior):
    """[LOAD-BEARING] At w=1 the blended rates are the book rates broadcast
    across the posterior's draws — EXACTLY the map V2's solver inverted — so
    for a non-provisional fixture the blend's 1X2 reproduces the de-vigged
    vector within 1e-6 (the solver's own residual tolerance), for BOTH OA
    de-vig methods. The grid itself must be BITWISE the finalized solve map.
    """
    post = real_posterior
    home, away = _settled_pair(post)
    ctx = FixtureCtx(home=home, away=away, neutral=True)
    odds = [2.05, 3.30, 3.90]
    for method in OA_DEVIG_METHODS:
        target = oa_devig(odds, method=method)
        lam_book = solve_implied_rates(post, target)
        assert lam_book is not None, method
        blended = blend_grid(post, ctx, lam_book, 1.0)
        assert np.array_equal(
            blended, _book_grid(post, lam_book, provisional=False)), method
        p = grid_one_x_two(blended)
        for i, k in enumerate(("home", "draw", "away")):
            assert abs(p[k] - target[i]) < RESIDUAL_TOL, (method, k)


@pytest.mark.slow
def test_w1_provisional_fixture_widens_on_top_of_the_book_map(real_posterior):
    """Widening is NOT part of the w=1 endpoint claim: it is a per-team
    predictive reshaping the production path applies downstream of the rates,
    identically for every w (the implied.py contract). For a provisional
    fixture the w=1 blend must be BITWISE the finalized (widened) book map —
    and therefore deliberately NOT the raw de-vig vector."""
    post = real_posterior
    home, _ = _settled_pair(post)
    prov = sorted(post.provisional_teams)[0]
    ctx = FixtureCtx(home=home, away=prov, neutral=True)
    target = oa_devig([2.05, 3.30, 3.90], method="shin")
    lam_book = solve_implied_rates(post, target)
    assert lam_book is not None

    blended = blend_grid(post, ctx, lam_book, 1.0)
    widened = _book_grid(post, lam_book, provisional=True)
    unwidened = _book_grid(post, lam_book, provisional=False)
    assert np.array_equal(blended, widened)
    assert not np.array_equal(widened, unwidened), (
        "provisional fixture did not widen — the case is vacuous")


# ---------------------------------------- continuity / normalization / determinism


@pytest.mark.slow
def test_blend_is_continuous_normalized_and_deterministic_in_w(real_posterior):
    """Finding 15's replacement for the unsound monotonicity assertion:

    * continuity — across the whole selection grid, adjacent evaluations move
      each 1X2 component by at most L*dw (L=2.0: the averaged map's rate
      sensitivity |dp/dlam| stays well under 1 on the rate box interior and
      the model-book rate gap here is ~O(1), so |dp/dw| < ~1.2; 2.0 is that
      with margin), and a 1e-3 step moves it by at most L*1e-3 — no hidden
      branch (e.g. a special-cased endpoint) can jump.
    * normalization — every blended grid is a distribution.
    * determinism — repeated evaluation is bitwise identical (no RNG).
    """
    post = real_posterior
    home, away = _settled_pair(post)
    ctx = FixtureCtx(home=home, away=away, neutral=True)
    target = oa_devig([2.05, 3.30, 3.90], method="shin")
    lam_book = solve_implied_rates(post, target)
    assert lam_book is not None

    L = 2.0
    probs = []
    for w in W_GRID:
        grid = blend_grid(post, ctx, lam_book, w)
        assert np.array_equal(grid, blend_grid(post, ctx, lam_book, w)), w
        assert float(grid.min()) >= 0.0, w
        assert abs(float(grid.sum()) - 1.0) < 1e-12, w
        p = blend_one_x_two(post, ctx, lam_book, w)
        assert abs(sum(p.values()) - 1.0) < 1e-12, w
        probs.append(p)
    for a, b, w in zip(probs, probs[1:], W_GRID[1:]):
        step = max(abs(b[k] - a[k]) for k in ("home", "draw", "away"))
        assert step <= L * 0.05, (w, step)
    fine_a = blend_one_x_two(post, ctx, lam_book, 0.5)
    fine_b = blend_one_x_two(post, ctx, lam_book, 0.501)
    assert max(abs(fine_b[k] - fine_a[k])
               for k in ("home", "draw", "away")) <= L * 1e-3


# ------------------------------------------------------------------- guards


def test_blend_grid_refuses_bad_w_and_bad_book_rates():
    """w outside [0,1] (or non-finite, or a bool), and book rates that are
    non-positive, non-finite or not a pair, are caller bugs — ValueError,
    never a silent clamp."""
    post = _stub_posterior()
    ctx = FixtureCtx(home="A", away="B")
    for bad_w in (-0.01, 1.01, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            blend_grid(post, ctx, (1.2, 1.0), bad_w)
    for bad_book in ((0.0, 1.0), (-1.0, 1.0), (float("nan"), 1.0),
                     (1.0,), (1.0, 1.0, 1.0)):
        with pytest.raises(ValueError):
            blend_grid(post, ctx, bad_book, 0.5)


def test_blend_grid_refuses_non_dixon_coles_posterior():
    """The blend rides the PRODUCTION Dixon-Coles map (per-draw rho, the same
    stance as the solver): another likelihood is a prereg change, not a
    fallback."""
    post = _stub_posterior(likelihood="bivariate_poisson")
    with pytest.raises(ValueError, match="[Dd]ixon"):
        blend_grid(post, FixtureCtx(home="A", away="B"), (1.2, 1.0), 0.5)


# ------------------------------------------------------- frozen selection spec


def test_selection_spec_is_frozen():
    """The fold spec is a pre-registered quantity (finding 9): grid, burn-in
    and the spec text are pinned VERBATIM — editing any of them is a prereg
    amendment, not a refactor."""
    assert W_GRID == tuple(round(i * 0.05, 2) for i in range(21))
    assert W_GRID[0] == 0.0 and W_GRID[-1] == 1.0 and len(W_GRID) == 21
    assert SELECTION_BURN_IN_MONTHS == 2
    assert FOLD_SPEC == (
        "monthly chronological folds over the dev slate; burn-in = first 2 "
        "months (training-only); fold t is scored with the (w, de-vig) pair "
        "chosen by mean canonical RPS on folds < t; rows without admissible "
        "odds are excluded from selection; grid w in {0.00, 0.05, ..., 1.00}; "
        "ties break to the smaller w, then the lexicographically smaller "
        "de-vig method; the final (w, de-vig) is the argmin over ALL dev "
        "months")


def test_blend_surface_pins_the_frozen_production_truncation():
    """The V2 freeze extends to the blend surface: ``max_goals`` defaults to
    the ONE frozen constant and is keyword-only, so the AST-scan discipline
    of test_draw_api cannot be bypassed positionally through E' either."""
    import inspect

    for func in (blend_grid, blend_one_x_two):
        param = inspect.signature(func).parameters["max_goals"]
        assert param.default == PRODUCTION_MAX_GOALS
        assert param.kind is inspect.Parameter.KEYWORD_ONLY


def test_blend_arm_names_round_trip_and_refuse_foreign_shapes():
    """The arm-name convention is the V5<->V6 interface: every (method, w) on
    the frozen grid round-trips; a label ('basic'), a non-OA method (finding
    13: 'power' can enter nothing), or an off-grid w is refused; a non-blend
    arm parses as None (it is somebody else's row, not an error)."""
    for method in OA_DEVIG_METHODS:
        for w in W_GRID:
            arm = blend_arm(method, w)
            assert arm.startswith(BLEND_ARM_PREFIX)
            assert parse_blend_arm(arm) == (method, w)
    assert parse_blend_arm("dev_dc") is None
    assert parse_blend_arm("incumbent") is None
    with pytest.raises(ValueError):
        blend_arm("basic", 0.5)          # reporting label, never an arm name
    with pytest.raises(ValueError):
        blend_arm("power", 0.5)
    with pytest.raises(ValueError):
        blend_arm("shin", 0.33)          # off-grid
    with pytest.raises(ValueError):
        parse_blend_arm("dev_blend_power_w0.10")
    with pytest.raises(ValueError):
        parse_blend_arm("dev_blend_shin_w0.33")
    with pytest.raises(ValueError):
        parse_blend_arm("dev_blend_shin")


# ----------------------------------------------------- synthetic dev ledgers


def _dev_row(fixture, day, arm, probs, *, hash_="b" * 64, pool="dev"):
    y, m, d = (int(part) for part in day.split("-"))
    return {
        "fixture_id": fixture,
        "pool": pool,
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


def _sharpened(outcome, q):
    """A forecast at quality q in (0,1): uniform pulled toward the truth.
    Canonical RPS is strictly decreasing in q, so candidate orderings by q
    ARE orderings by mean RPS — the planted optimum is exact, not sampled."""
    idx = {"home": 0, "draw": 1, "away": 2}[outcome]
    p = [(1.0 - q) / 3.0] * 3
    p[idx] += q
    return tuple(p)


def _blend_rows(fixture, day, outcome, quality, *, hash_="b" * 64):
    """The full 42-arm blend block for one fixture: every OA method x every
    grid w, forecast quality given by ``quality(method, w)``."""
    return [
        _dev_row(fixture, day, blend_arm(method, w),
                 _sharpened(outcome, quality(method, w)), hash_=hash_)
        for method in OA_DEVIG_METHODS for w in W_GRID
    ]


def _manifest(ids):
    return {"rule": "synthetic", "fixtures": [{"match_id": i} for i in ids]}


_OUTCOME_CYCLE = ("home", "away", "draw")


def _month_fixtures(months, per_month, quality, *, prefix="dev", hash_="b" * 64):
    """rows, outcomes, ids for ``per_month`` fixtures on the 3rd/10th/... of
    each month, outcomes cycling so no single label dominates."""
    rows, outcomes, ids = [], {}, []
    for mi, month in enumerate(months):
        for k in range(per_month):
            fixture = f"{prefix}-{mi}{k}"
            outcome = _OUTCOME_CYCLE[(mi + k) % 3]
            day = f"{month}-{3 + 7 * k:02d}"
            rows += _blend_rows(fixture, day, outcome, quality, hash_=hash_)
            outcomes[fixture] = outcome
            ids.append(fixture)
    return rows, outcomes, ids


def test_select_w_recovers_a_planted_optimum(tmp_path):
    """[LOAD-BEARING] A (shin, 0.30) optimum planted across every month must
    come back exactly, with the walk-forward folds (months 3+) each choosing
    it on their prior months, and the grid table carrying every candidate."""
    def quality(method, w):
        return 0.85 - abs(w - 0.30) - (0.10 if method == "multiplicative" else 0.0)

    months = ["2023-01", "2023-02", "2023-03", "2023-04"]
    rows, outcomes, ids = _month_fixtures(months, 2, quality)
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)

    sel = select_w(path, outcomes=outcomes, manifest=_manifest(ids))
    assert sel.w == 0.30
    assert sel.devig_method == "shin"
    assert sel.months == tuple(months)
    assert [f.month for f in sel.folds] == ["2023-03", "2023-04"]
    for fold in sel.folds:
        assert (fold.devig_method, fold.w) == ("shin", 0.30)
        assert fold.n_fold_fixtures == 2
    assert sel.folds[0].n_train_fixtures == 4
    assert sel.folds[1].n_train_fixtures == 6
    assert sel.n_fixtures == 8
    assert sel.n_excluded_no_odds == 0
    assert len(sel.grid_mean_rps) == len(OA_DEVIG_METHODS) * len(W_GRID)
    table = {(m, w): r for m, w, r in sel.grid_mean_rps}
    assert min(table, key=lambda c: (table[c], c[1], c[0])) == ("shin", 0.30)


def _expected_argmin(fixtures):
    """The frozen argmin ((mean canonical RPS, w, method) tie order),
    recomputed INDEPENDENTLY from a list of (outcome, quality_fn) fixtures —
    the certification half of the sentinel tests below."""
    means = {}
    for method in OA_DEVIG_METHODS:
        for w in W_GRID:
            means[(method, w)] = float(np.mean([
                rps(dict(zip(("home", "draw", "away"),
                             _sharpened(outcome, quality(method, w)))),
                    outcome)
                for outcome, quality in fixtures]))
    return min(means, key=lambda c: (means[c], c[1], c[0]))


def test_select_w_fold_never_sees_its_own_month(tmp_path):
    """[LOAD-BEARING leakage sentinel] Fold 2023-03's candidate is chosen on
    Jan+Feb ONLY. The March data invert the optimum so hard that the FULL-set
    argmin flips to w=0.90 — both argmins are certified in-test by an
    independent recomputation over every candidate — so an implementation
    that let fold t see fold t (or that ignored the fold structure entirely)
    would choose 0.90 for the March fold. It must choose 0.10, while the
    FINAL selection (argmin over ALL months — the deployment choice) is
    0.90."""
    def quality(method, w):
        if method != "shin":
            return 0.05
        return {0.10: 0.80}.get(w, 0.40)

    def march_quality(method, w):
        if method != "shin":
            return 0.05
        return {0.10: 0.05, 0.90: 0.95}.get(w, 0.40)

    months = ["2023-01", "2023-02"]
    rows, outcomes, ids = _month_fixtures(months, 2, quality)
    march_rows, march_outcomes, march_ids = _month_fixtures(
        ["2023-03"], 3, march_quality, prefix="mar")
    rows += march_rows
    outcomes.update(march_outcomes)
    ids += march_ids

    early = [(outcomes[f], quality) for f in ids if not f.startswith("mar")]
    march = [(outcomes[f], march_quality) for f in ids if f.startswith("mar")]
    assert _expected_argmin(early) == ("shin", 0.10)
    assert _expected_argmin(early + march) == ("shin", 0.90)

    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)
    sel = select_w(path, outcomes=outcomes, manifest=_manifest(ids))
    assert [f.month for f in sel.folds] == ["2023-03"]
    assert sel.folds[0].w == 0.10          # chosen on Jan+Feb only
    assert sel.w == 0.90                   # final = argmin over ALL months


def test_select_w_excludes_odds_absent_fixtures(tmp_path):
    """Odds-absent rows carry no signal about w and are EXCLUDED. The null-
    hash fixtures here are built so that INCLUDING them would flip the argmin
    to w=0.90 — the guard must drop them regardless of row content (a real
    V9-style incumbent copy could never flip anything, so a copy-shaped test
    would be vacuous), and count them."""
    def covered_quality(method, w):
        return 0.80 - abs(w - 0.20)

    def absent_quality(method, w):
        return 0.95 if w == 0.90 else 0.05

    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = _month_fixtures(months, 2, covered_quality)
    absent_rows, absent_outcomes, absent_ids = _month_fixtures(
        months, 3, absent_quality, prefix="abs", hash_=None)
    rows += absent_rows
    outcomes.update(absent_outcomes)
    ids += absent_ids

    # Certified flip: had the null-hash fixtures been scored, the argmin
    # would move to (shin-or-mult, 0.90) — so the 0.20 below can only come
    # from the exclusion actually happening.
    covered = [(outcomes[f], covered_quality) for f in ids
               if not f.startswith("abs")]
    absent = [(outcomes[f], absent_quality) for f in ids
              if f.startswith("abs")]
    assert _expected_argmin(covered)[1] == 0.20
    assert _expected_argmin(covered + absent)[1] == 0.90

    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)
    sel = select_w(path, outcomes=outcomes, manifest=_manifest(ids))
    assert sel.w == 0.20
    assert sel.n_fixtures == 6
    assert sel.n_excluded_no_odds == 9


def test_select_w_tie_breaks_to_smaller_w_then_method(tmp_path):
    """Ties are structural, not hypothetical (at w=0 both methods' blends are
    the SAME incumbent row). Identical best forecasts at w in {0.40, 0.60} for
    both methods must resolve to (multiplicative, 0.40): smaller w first —
    less market dependence — then the lexicographically smaller method."""
    def quality(method, w):
        return 0.80 if w in (0.40, 0.60) else 0.30

    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = _month_fixtures(months, 2, quality)
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)
    sel = select_w(path, outcomes=outcomes, manifest=_manifest(ids))
    assert sel.w == 0.40
    assert sel.devig_method == "multiplicative"


def test_select_w_refuses_foreign_rows(tmp_path):
    """The dev-only diet is enforced at runtime, not assumed: a fixture
    outside the dev manifest, an arm without the dev_ prefix, and a row
    stamped with a scored pool's name are each refused loudly."""
    def quality(method, w):
        return 0.5

    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = _month_fixtures(months, 1, quality)

    path = _write_ledger(tmp_path / "not_in_manifest.parquet", rows)
    with pytest.raises(ValueError, match="manifest"):
        select_w(path, outcomes=outcomes, manifest=_manifest(ids[:-1]))

    foreign_arm = rows + [_dev_row(ids[0], "2023-01-03", "incumbent",
                                   (0.4, 0.3, 0.3))]
    path = _write_ledger(tmp_path / "foreign_arm.parquet", foreign_arm)
    with pytest.raises(ValueError, match="dev_"):
        select_w(path, outcomes=outcomes, manifest=_manifest(ids))

    scored = rows + [_dev_row("wc-1", "2023-01-03", "dev_dc", (0.4, 0.3, 0.3),
                              pool="wc2026")]
    path = _write_ledger(tmp_path / "scored_pool.parquet", scored)
    with pytest.raises(ValueError, match="scored pool"):
        select_w(path, outcomes=outcomes,
                 manifest=_manifest(ids + ["wc-1"]))


def test_select_w_errors_on_malformed_blend_blocks(tmp_path):
    """A PARTIAL per-fixture grid, a mixed null/non-null hash block, and a
    malformed dev_blend_* arm are pipeline bugs — errors, never silent drops
    (the V7 exact-cardinality stance): a fixture missing one candidate would
    make the grid means incomparable across candidates."""
    def quality(method, w):
        return 0.5

    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = _month_fixtures(months, 1, quality)

    partial = [r for r in rows
               if not (r["fixture_id"] == ids[0]
                       and r["arm"] == blend_arm("shin", 0.55))]
    path = _write_ledger(tmp_path / "partial.parquet", partial)
    with pytest.raises(ValueError, match="candidate|partial|missing"):
        select_w(path, outcomes=outcomes, manifest=_manifest(ids))

    mixed = [dict(r) for r in rows]
    for r in mixed:
        if r["fixture_id"] == ids[0] and r["arm"] == blend_arm("shin", 0.55):
            r["odds_snapshot_hash"] = None
    path = _write_ledger(tmp_path / "mixed.parquet", mixed)
    with pytest.raises(ValueError, match="hash"):
        select_w(path, outcomes=outcomes, manifest=_manifest(ids))

    off_grid = rows + [_dev_row(ids[0], "2023-01-03", "dev_blend_shin_w0.33",
                                (0.4, 0.3, 0.3))]
    path = _write_ledger(tmp_path / "off_grid.parquet", off_grid)
    with pytest.raises(ValueError, match="grid"):
        select_w(path, outcomes=outcomes, manifest=_manifest(ids))

    bad_method = rows + [_dev_row(ids[0], "2023-01-03",
                                  "dev_blend_power_w0.10", (0.4, 0.3, 0.3))]
    path = _write_ledger(tmp_path / "bad_method.parquet", bad_method)
    with pytest.raises(ValueError, match="OA|power"):
        select_w(path, outcomes=outcomes, manifest=_manifest(ids))


def test_select_w_requires_outcomes_and_enough_months(tmp_path):
    """A missing outcome for an included fixture is an ERROR (silent drops
    shrink the paired comparison asymmetrically); fewer than burn-in+1 months
    means no fold can be scored — refuse, never degrade."""
    def quality(method, w):
        return 0.5

    months = ["2023-01", "2023-02", "2023-03"]
    rows, outcomes, ids = _month_fixtures(months, 1, quality)
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)

    short = dict(outcomes)
    del short[ids[0]]
    with pytest.raises(ValueError, match="outcome"):
        select_w(path, outcomes=short, manifest=_manifest(ids))

    with pytest.raises(ValueError, match="outcome"):
        select_w(path, outcomes={**outcomes, ids[0]: "HOME"},
                 manifest=_manifest(ids))

    two_rows, two_outcomes, two_ids = _month_fixtures(
        ["2023-01", "2023-02"], 2, quality)
    path = _write_ledger(tmp_path / "two_months.parquet", two_rows)
    with pytest.raises(ValueError, match="month"):
        select_w(path, outcomes=two_outcomes, manifest=_manifest(two_ids))


# ------------------------------------------------------- selection trace


def test_write_selection_trace_is_complete_and_deterministic(tmp_path):
    """The trace is what the V8 lock HASHES: it must carry the selected
    (w, de-vig), the stacking params, the full fold trace, the frozen spec
    text and the grid table — and serializing the same selection twice must
    be byte-identical, or the lock hash would depend on the writing session.
    """
    def quality(method, w):
        return 0.85 - abs(w - 0.30) - (0.10 if method == "multiplicative" else 0.0)

    months = ["2023-01", "2023-02", "2023-03", "2023-04"]
    rows, outcomes, ids = _month_fixtures(months, 2, quality)
    path = _write_ledger(tmp_path / "dev_ledger.parquet", rows)
    sel = select_w(path, outcomes=outcomes, manifest=_manifest(ids))

    stacking = {
        "devig_method": "shin",
        "feature_order": ["dc", "odds", "elo_ordlogit"],
        "params": {"c1": -0.4, "s": 0.1, "b_dc": 0.5, "b_odds": 0.9,
                   "b_elo": 0.1},
        "oof_rps": 0.19,
    }
    p1 = write_selection_trace(tmp_path / "trace_a.json", sel,
                               stacking=stacking)
    p2 = write_selection_trace(tmp_path / "trace_b.json", sel,
                               stacking=stacking)
    assert p1.read_bytes() == p2.read_bytes()

    doc = json.loads(p1.read_text())
    assert doc["selected"] == {"w": 0.30, "devig_method": "shin"}
    assert doc["fold_spec"] == FOLD_SPEC
    assert doc["burn_in_months"] == SELECTION_BURN_IN_MONTHS
    assert doc["w_grid"] == [round(i * 0.05, 2) for i in range(21)]
    assert doc["devig_methods"] == list(OA_DEVIG_METHODS)
    assert doc["stacking"] == stacking
    assert [f["month"] for f in doc["folds"]] == ["2023-03", "2023-04"]
    assert {"w", "devig_method", "fold_rps", "n_train_fixtures",
            "n_fold_fixtures"} <= set(doc["folds"][0])
    assert len(doc["grid_mean_rps"]) == len(OA_DEVIG_METHODS) * len(W_GRID)
    assert doc["n_fixtures"] == 8
    assert doc["n_excluded_no_odds"] == 0
