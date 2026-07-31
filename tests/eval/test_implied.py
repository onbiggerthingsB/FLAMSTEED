"""OA Plan 2 V2: implied-rate solve through the REAL finalized production map,
plus the OA de-vig set (Codex findings 13 & 15, B2-1 ruling).

The solve inverts the SAME map production forecasts come from, END TO END:
``(lam_h, lam_a)`` such that ``finalize(mean_d grid(lam_h, lam_a, rho_d))
-> 1X2`` equals the de-vigged book vector — rho draws from the fixture's OWN
posterior, and the finalization leg (mechanism-'c' widening for a provisional
fixture, final renorm always) INCLUDED (B2-1: inverting the unwidened map
while the blend widens broke the w=1 endpoint by ~0.029 on provisional
fixtures). Acceptance is residual < 1e-6 in every component AND two
well-separated starts agreeing; every failure mode returns None (fail closed
— the fixture is odds-uncovered; no symmetric-split fallback ever).

The infeasibility test uses a CERTIFIED infeasible vector: the bounded map's
draw-probability maximum is MEASURED here (fine grid + multi-start scipy
maximization, B2-5), through the same map the solver inverts, and the target
is placed strictly above it — finding 15 killed the guessed ``p_draw=0.9``
fixture precisely because 0.9 IS feasible at the low corner of the rate box.

De-vig: the OA-choosable set is EXACTLY {shin, multiplicative}; "basic" is a
reporting LABEL for multiplicative; "power" (a Phase-4 backtest method) can
enter neither selection nor the Holm family (finding 13).
"""
from __future__ import annotations

import arviz as az
import numpy as np
import pytest

from wcmodel.data import devig as _devig
from wcmodel.eval import implied
from wcmodel.eval.implied import (
    OA_DEVIG_LABELS,
    OA_DEVIG_METHODS,
    RATE_BOUNDS,
    RESIDUAL_TOL,
    oa_devig,
    solve_implied_rates,
)
from wcmodel.model.draw_api import (
    PRODUCTION_MAX_GOALS,
    FixtureCtx,
    finalize_grid,
    grid_one_x_two,
    mean_grid_over_draws,
)
from wcmodel.model.posterior import Posterior

from tests.model.conftest import fit_compact_real_posterior


@pytest.fixture(scope="module")
def real_posterior(tmp_path_factory):
    """ONE real ADVI-fitted Posterior shared by this module's solver tests."""
    return fit_compact_real_posterior(tmp_path_factory.mktemp("implied_store"))


def _settled_ctx(post) -> FixtureCtx:
    """A fixture context between two settled teams (widening never fires)."""
    settled = [t for t in post.teams if t not in post.provisional_teams]
    assert len(settled) >= 2
    return FixtureCtx(home=settled[0], away=settled[1], neutral=True)


def _provisional_ctx(post) -> FixtureCtx:
    """A fixture context with one provisional team (widening fires)."""
    settled = [t for t in post.teams if t not in post.provisional_teams]
    prov = sorted(post.provisional_teams)[0]
    return FixtureCtx(home=settled[0], away=prov, neutral=True)


def _map_1x2(post, ctx, lam_h: float, lam_a: float) -> dict:
    """The EXACT map the solver inverts: constant rates broadcast across the
    posterior's rho draws, averaged per-draw grids, the production
    finalization leg (widening iff the fixture is provisional, renorm always),
    1X2 projection."""
    rho = post._post("rho")
    grid = mean_grid_over_draws(
        np.full(rho.shape[-1], lam_h), np.full(rho.shape[-1], lam_a),
        likelihood="dixon_coles", rho=rho, max_goals=PRODUCTION_MAX_GOALS)
    provisional = (ctx.home in post.provisional_teams) \
        or (ctx.away in post.provisional_teams)
    return grid_one_x_two(finalize_grid(grid, post, provisional=provisional))


def _stub_posterior(likelihood="dixon_coles"):
    """Tiny hand-built Posterior (NO sampling) for guard-branch unit tests —
    the acceptance-path tests below all run on the REAL fit."""
    params = {
        "att": np.zeros((1, 2, 2)),
        "def": np.zeros((1, 2, 2)),
        "mu": np.full((1, 2), 0.1),
        "home_adv": np.full((1, 2), 0.2),
        "rho": np.full((1, 2), -0.05),
    }
    return Posterior(az.from_dict({"posterior": params}), ["A", "B"],
                     likelihood, provisional_teams=set())


# ------------------------------------------------------------- OA de-vig set


def test_oa_devig_set_is_exactly_shin_and_multiplicative():
    """Finding 13: the OA-choosable set is EXACTLY {shin, multiplicative} —
    no third method, and both members produce genuine distributions."""
    assert OA_DEVIG_METHODS == ("shin", "multiplicative")
    odds = [2.05, 3.30, 3.90]
    for method in OA_DEVIG_METHODS:
        p = oa_devig(odds, method=method)
        assert len(p) == 3 and all(q > 0 for q in p)
        assert abs(sum(p) - 1.0) < 1e-12


def test_basic_is_the_reporting_label_for_multiplicative():
    """'basic' names no distinct algorithm (finding 13): it resolves to
    multiplicative EXACTLY (same output as the underlying devig function) and
    is a LABEL, not a third member of the OA set."""
    odds = [1.85, 3.60, 4.40]
    assert oa_devig(odds, method="basic") == oa_devig(odds, method="multiplicative")
    assert oa_devig(odds, method="basic") == _devig.multiplicative(odds)
    assert "basic" not in OA_DEVIG_METHODS
    assert OA_DEVIG_LABELS == {"basic": "multiplicative"}


def test_power_cannot_enter_the_oa_devig_set():
    """'power' exists in the Phase-4 backtest trio but is NOT OA-choosable: it
    must be refused on input, absent from the frozen set, and unreachable via
    the label map — so it can enter neither the de-vig selection nor the Holm
    family (finding 13)."""
    odds = [2.00, 3.40, 4.00]
    for bad in ("power", "buchdahl", "odds_proportional", "", "shin "):
        with pytest.raises(ValueError, match="OA"):
            oa_devig(odds, method=bad)
    assert "power" not in OA_DEVIG_METHODS
    assert "power" not in OA_DEVIG_LABELS          # no label resolves FROM it
    assert "power" not in OA_DEVIG_LABELS.values()  # ...or TO it


# ------------------------------------------------------------ solve: accepts


@pytest.mark.slow
def test_solve_roundtrip_recovers_planted_rates(real_posterior):
    """A target GENERATED by the map at known rates must be solved back to
    those rates: residual < 1e-6 through the same averaged map, and the
    recovered pair sits on the planted one (unique interior root)."""
    post = real_posterior
    ctx = _settled_ctx(post)
    planted = (1.6, 0.9)
    p = _map_1x2(post, ctx, *planted)
    target = (p["home"], p["draw"], p["away"])

    got = solve_implied_rates(post, ctx, target)
    assert got is not None
    lam_h, lam_a = got
    assert lam_h == pytest.approx(planted[0], abs=1e-3)
    assert lam_a == pytest.approx(planted[1], abs=1e-3)
    back = _map_1x2(post, ctx, lam_h, lam_a)
    for i, k in enumerate(("home", "draw", "away")):
        assert abs(back[k] - target[i]) < RESIDUAL_TOL


@pytest.mark.slow
def test_solve_matches_devig_vector_through_finalized_map(real_posterior):
    """[LOAD-BEARING] The V2 statement of the coherence invariant: a de-vigged
    book vector (BOTH OA methods) solves to rates whose finalized
    mean-over-draws grid reproduces that exact vector to < 1e-6 through the
    production 1X2 projection — the definition V6's w=1 endpoint leans on."""
    post = real_posterior
    ctx = _settled_ctx(post)
    odds = [2.05, 3.30, 3.90]
    for method in OA_DEVIG_METHODS:
        target = oa_devig(odds, method=method)
        got = solve_implied_rates(post, ctx, target)
        assert got is not None, method
        lam_h, lam_a = got
        assert RATE_BOUNDS[0] <= lam_h <= RATE_BOUNDS[1]
        assert RATE_BOUNDS[0] <= lam_a <= RATE_BOUNDS[1]
        back = _map_1x2(post, ctx, lam_h, lam_a)
        for i, k in enumerate(("home", "draw", "away")):
            assert abs(back[k] - target[i]) < RESIDUAL_TOL, (method, k)


@pytest.mark.slow
def test_solve_inverts_the_widened_map_for_a_provisional_fixture(real_posterior):
    """[LOAD-BEARING, B2-1 ruling] For a PROVISIONAL fixture the solver must
    invert the FINALIZED (widened) map — the map the E' blend actually
    evaluates at w=1 — so the solved rates reproduce the de-vigged vector
    through the widened map to < 1e-6. Solving through the unwidened map and
    widening afterwards missed the target by ~0.029 (the reviewer's measured
    error), which broke the w=1 coherence endpoint for every provisional
    fixture. Non-vacuity is asserted twice: the widened and unwidened maps
    genuinely differ at the solved rates, and the provisional-ctx solve lands
    on a DIFFERENT rate pair than the settled-ctx solve (the solver really
    compensates for widening)."""
    post = real_posterior
    ctx = _provisional_ctx(post)
    target = oa_devig([2.05, 3.30, 3.90], method="shin")

    got = solve_implied_rates(post, ctx, target)
    assert got is not None
    lam_h, lam_a = got
    back = _map_1x2(post, ctx, lam_h, lam_a)
    for i, k in enumerate(("home", "draw", "away")):
        assert abs(back[k] - target[i]) < RESIDUAL_TOL, k

    # the widening branch actually fired at these rates...
    settled_view = _map_1x2(post, _settled_ctx(post), lam_h, lam_a)
    assert any(abs(settled_view[k] - back[k]) > 1e-3
               for k in ("home", "draw", "away"))
    # ...and the solver compensated for it: a settled-ctx solve of the SAME
    # target lands elsewhere.
    plain = solve_implied_rates(post, _settled_ctx(post), target)
    assert plain is not None
    assert max(abs(plain[0] - lam_h), abs(plain[1] - lam_a)) > 1e-3


# ------------------------------------------------------------- solve: refuses


def test_solver_acceptance_constants_are_pinned():
    """[B2-5] The acceptance boundaries are pre-registered quantities: the
    residual tolerance and the two-start agreement tolerance are pinned as
    LITERALS — moving either loosens (or silently retargets) the coherence
    invariant and is a prereg amendment, not a refactor."""
    assert RESIDUAL_TOL == 1e-6
    assert implied._AGREEMENT_TOL == 1e-4


@pytest.mark.slow
def test_solve_returns_none_on_certified_infeasible_vector(real_posterior):
    """[LOAD-BEARING, findings 15 & B2-5] Infeasibility is CERTIFIED, not
    guessed, and the certification is a genuine MAXIMIZATION, not a sparse
    scan: the bounded map's draw-probability maximum is established by (a) a
    fine grid over the rate box and (b) scipy L-BFGS-B maximization from
    MULTIPLE well-separated starts (one start genuinely converges to a
    different, far lower stationary point at the high-rate corner — that is
    why multiple starts are load-bearing). Both agree the max sits at the
    low-rate corner; the independent Codex review search found 0.9070050416
    at (0.05, 0.05) on its own fit of this same panel, corroborated here to
    1e-4 (cross-environment ADVI jitter). The target's draw probability is
    then placed strictly ABOVE the measured max. The old guessed fixture
    (p_draw=0.9) is BELOW it, i.e. feasible — which is precisely why the
    guess was rejected."""
    from scipy.optimize import minimize

    post = real_posterior
    ctx = _settled_ctx(post)
    lo, hi = RATE_BOUNDS

    def draw_prob(x):
        return _map_1x2(post, ctx, float(x[0]), float(x[1]))["draw"]

    # (a) fine grid: dense near the low-rate corner (where the max lives),
    # coarser across the rest of the box.
    axis = np.concatenate([np.linspace(lo, 0.3, 26), np.linspace(0.35, hi, 40)])
    grid_vals = {(a, b): draw_prob((a, b)) for a in axis for b in axis}
    grid_max = max(grid_vals.values())
    grid_argmax = max(grid_vals, key=grid_vals.get)
    assert grid_argmax == (lo, lo), (
        f"fine-grid draw-prob maximum expected at the low-rate corner, got "
        f"{grid_argmax} — the corner certification does not hold for this map")

    # (b) scipy maximization from multiple well-separated starts.
    starts = [(lo, lo), (0.1, 0.2), (0.5, 0.5), (1.0, 1.0), (2.0, 3.0),
              (7.0, 7.0)]
    best_val, best_x = -np.inf, None
    for x0 in starts:
        res = minimize(lambda x: -draw_prob(x), x0, method="L-BFGS-B",
                       bounds=[(lo, hi), (lo, hi)])
        assert res.success, x0
        if -res.fun > best_val:
            best_val, best_x = -float(res.fun), np.asarray(res.x)
    assert np.allclose(best_x, (lo, lo), atol=1e-6), (
        f"scipy maximizer landed at {best_x}, not the low-rate corner")
    measured_max = max(best_val, grid_max)
    assert best_val >= grid_max - 1e-12      # the scan never beats the optimizer
    assert measured_max == pytest.approx(0.9070050416, abs=1e-4)
    # The finding-15 point, demonstrated: 0.9 is NOT above the map's maximum.
    assert measured_max > 0.9

    p_draw = min(measured_max + 0.02, 0.98)
    assert p_draw > measured_max            # certified: strictly unreachable
    rest = (1.0 - p_draw) / 2.0
    assert solve_implied_rates(post, ctx, (rest, p_draw, rest)) is None


def test_solve_returns_none_when_a_start_fails_or_residual_unmet(monkeypatch):
    """Fail CLOSED on the solver's own terms: a start that does not converge,
    or converges to a residual >= 1e-6, yields None (never a best-effort
    rate pair). Injected via a least_squares stub — the real bounded map has
    no reachable non-convergent input to trigger this honestly."""
    post = _stub_posterior()
    ctx = FixtureCtx(home="A", away="B")
    target = (0.4, 0.3, 0.3)

    class _R:
        def __init__(self, success, x, fun):
            self.success, self.x, self.fun = success, np.array(x), np.array(fun)

    monkeypatch.setattr(
        implied, "least_squares",
        lambda *a, **k: _R(False, [1.0, 1.0], [0.0, 0.0, 0.0]))
    assert solve_implied_rates(post, ctx, target) is None

    monkeypatch.setattr(
        implied, "least_squares",
        lambda *a, **k: _R(True, [1.0, 1.0], [5e-4, -5e-4, 0.0]))
    assert solve_implied_rates(post, ctx, target) is None


def test_solve_returns_none_when_two_starts_disagree(monkeypatch):
    """Two-start agreement is a hard acceptance leg: two 'successful'
    tiny-residual solutions that do not coincide (an ambiguous inversion)
    yield None. Injected — the guard exists exactly for map pathologies the
    healthy test posterior cannot exhibit."""
    post = _stub_posterior()
    answers = iter(([0.9, 0.9], [2.1, 2.1]))

    class _R:
        def __init__(self, x):
            self.success, self.x, self.fun = True, np.array(x), np.zeros(3)

    monkeypatch.setattr(
        implied, "least_squares", lambda *a, **k: _R(next(answers)))
    assert solve_implied_rates(post, FixtureCtx(home="A", away="B"),
                               (0.4, 0.3, 0.3)) is None


def test_solve_refuses_non_dixon_coles_posterior():
    """The solve inverts the PRODUCTION Dixon-Coles map (per-draw rho). A
    posterior fitted under another likelihood carries no rho draws — refusing
    loudly beats silently inverting a different map (extending the solve is a
    prereg change, not a fallback)."""
    post = _stub_posterior(likelihood="bivariate_poisson")
    with pytest.raises(ValueError, match="[Dd]ixon"):
        solve_implied_rates(post, FixtureCtx(home="A", away="B"),
                            (0.4, 0.3, 0.3))


def test_solve_refuses_unknown_teams():
    """An unknown team is the predict contract's KeyError, never a silent
    'not provisional' guess — guessing would invert the unwidened map for a
    fixture whose blend might widen (exactly the B2-1 incoherence)."""
    post = _stub_posterior()
    with pytest.raises(KeyError):
        solve_implied_rates(post, FixtureCtx(home="A", away="Nowhere"),
                            (0.4, 0.3, 0.3))


def test_solve_raises_on_malformed_target():
    """A malformed target is a CALLER bug, not infeasibility: ValueError, not
    None — None must stay reserved for 'well-posed but unreachable', because
    V3/V4 count None rows as odds-uncovered population (finding 10)."""
    post = _stub_posterior()
    ctx = FixtureCtx(home="A", away="B")
    for bad in (
        (0.5, 0.5),                    # wrong length
        (0.5, 0.4, 0.2),               # sum 1.1
        (0.7, 0.4, -0.1),              # negative component
        (float("nan"), 0.5, 0.5),      # non-finite
        (1.0, 0.0, 0.0),               # boundary components (not strict probs)
    ):
        with pytest.raises(ValueError):
            solve_implied_rates(post, ctx, bad)
