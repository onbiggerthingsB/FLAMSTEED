"""OA Plan 2 V2: the per-draw production map API (Codex finding 3).

``draw_api.production_grid`` must BE the production predict path — ONE shared
implementation of per-draw rates -> per-draw dependence correction -> per-draw
renormalization -> mean over draws -> widening. Finding 3 was exactly the
drift risk this closes: a second almost-right copy of the map (rho applied to
the averaged grid instead of per draw, widening skipped, an unfrozen goal
truncation) would let the OA blend/solve measure a DIFFERENT model than the
one production issues.

Three pins live here:

* BITWISE parity with ``Posterior.predict_scoreline`` on a REAL (ADVI-fitted)
  Posterior for every production fixture context — ordinary, neutral,
  host-home, provisional (the widening branch, proven non-vacuous) — plus the
  1X2 projection.
* PER-DRAW semantics: the mean is over per-draw tau-corrected, per-draw
  renormalized grids; collapsing the draws to mean rates/rho first is NOT the
  map.
* ``PRODUCTION_MAX_GOALS`` frozen at the production value in ONE constant,
  with every caller pinned to it (signature defaults by inspection + an AST
  scan of every ``production_grid``/``solve_implied_rates`` call site under
  ``src/`` and ``scripts/``).
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import poisson

import wcmodel
from wcmodel.config import load_config
from wcmodel.model import draw_api
from wcmodel.model.draw_api import (
    PRODUCTION_MAX_GOALS,
    FixtureCtx,
    grid_one_x_two,
    mean_grid_over_draws,
    per_draw_rates,
    production_grid,
)
from wcmodel.model.likelihoods import dc_tau_np
from wcmodel.model.posterior import Posterior

from tests.model.conftest import fit_compact_real_posterior


@pytest.fixture(scope="module")
def real_posterior(tmp_path_factory):
    """ONE real ADVI-fitted Posterior shared by this module's parity tests."""
    return fit_compact_real_posterior(tmp_path_factory.mktemp("draw_api_store"))


# ---------------------------------------------------------------- parity


@pytest.mark.slow
def test_production_grid_is_bitwise_the_predict_path_on_a_real_posterior(real_posterior):
    """[LOAD-BEARING] ``production_grid`` == ``predict_scoreline`` BITWISE
    (``np.array_equal``, not allclose) on a REAL fitted Posterior, for every
    production fixture context: ordinary home/away, neutral, host-home (the
    calibrated ``host_k``), and a provisional fixture (mechanism-'c' widening
    fires). The 1X2 projection (``grid_one_x_two``) must equal ``predict_1x2``
    exactly too — it is the production scoring map's last step, and the
    implied-rate solve inverts through it."""
    post = real_posterior
    assert post.likelihood == "dixon_coles"          # the production likelihood
    prov_teams = sorted(post.provisional_teams)
    assert prov_teams, "compact panel must yield a provisional team (few-games arm)"
    prov = prov_teams[0]
    settled = [t for t in post.teams if t not in post.provisional_teams]
    assert len(settled) >= 2, "need two non-provisional teams for the plain contexts"
    home, away = settled[0], settled[1]
    host_k = load_config()["model"]["covariates"]["host_k"]  # the calibrated 1.4

    cases = [
        ("ordinary", home, away, dict(neutral=False, host_factor=None)),
        ("neutral", home, away, dict(neutral=True, host_factor=None)),
        ("host-home", home, away, dict(neutral=False, host_factor=host_k)),
        ("provisional", home, prov, dict(neutral=True, host_factor=None)),
    ]
    for label, h, a, kw in cases:
        via_predict = post.predict_scoreline(
            h, a, neutral=kw["neutral"], host_factor=kw["host_factor"])
        via_api = production_grid(
            post, FixtureCtx(home=h, away=a, neutral=kw["neutral"],
                             host_factor=kw["host_factor"]))
        assert via_api.shape == (PRODUCTION_MAX_GOALS + 1,) * 2, label
        assert np.array_equal(via_api, via_predict), f"{label}: grid parity broken"
        assert post.predict_1x2(
            h, a, neutral=kw["neutral"], host_factor=kw["host_factor"]
        ) == grid_one_x_two(via_api), f"{label}: 1X2 projection parity broken"


@pytest.mark.slow
def test_provisional_parity_case_actually_widens(real_posterior):
    """NON-VACUITY guard for the provisional parity case: the production grid
    for a provisional fixture must DIFFER from the un-widened averaged grid —
    otherwise the 'provisional' parity row above silently degenerates into a
    fourth copy of the plain path (e.g. if the fit config's widening mechanism
    drifted off 'c' or strength to 0, the widening branch would never run)."""
    post = real_posterior
    assert post._cfg["widening"]["mechanism"] == "c"
    assert post._cfg["widening"]["strength"] > 0.0
    prov = sorted(post.provisional_teams)[0]
    home = [t for t in post.teams if t not in post.provisional_teams][0]
    ctx = FixtureCtx(home=home, away=prov, neutral=True)

    lh, la = per_draw_rates(post, ctx)
    mean = mean_grid_over_draws(lh, la, likelihood="dixon_coles",
                                rho=post._post("rho"),
                                max_goals=PRODUCTION_MAX_GOALS)
    unwidened = mean / mean.sum()
    widened = production_grid(post, ctx)
    assert not np.array_equal(widened, unwidened), (
        "provisional fixture did not widen — the parity case is vacuous")


# ---------------------------------------------------------- per-draw semantics


def _ref_dc_draw_grid(lh: float, la: float, rho: float, n: int) -> np.ndarray:
    """ONE draw's reference DC grid, built independently from the rate
    definitions (the ``test_fit_predict._expected_dc_grid`` arithmetic):
    independent-Poisson outer product, tau on the four low-score cells,
    clip, renormalize."""
    xs = np.arange(n)
    g = poisson.pmf(xs, lh)[:, None] * poisson.pmf(xs, la)[None, :]
    for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
        g[x, y] *= dc_tau_np(x, y, float(lh), float(la), float(rho))
    g = np.clip(g, 0.0, None)
    return g / g.sum()


def test_mean_grid_applies_rho_per_draw_before_averaging():
    """[LOAD-BEARING] The map is mean-over-draws of PER-DRAW corrected,
    PER-DRAW renormalized grids — bitwise equal to averaging independently
    built reference grids. Collapsing draws to their mean rates/rho FIRST (the
    finding-3 failure mode: 'per-draw rho' replaced by a single rho on the
    averaged grid) is measurably NOT the same map."""
    lh = np.array([1.4, 0.9])
    la = np.array([1.1, 1.3])
    rho = np.array([-0.12, 0.08])
    n = PRODUCTION_MAX_GOALS + 1

    got = mean_grid_over_draws(lh, la, likelihood="dixon_coles", rho=rho,
                               max_goals=PRODUCTION_MAX_GOALS)
    ref = np.stack([
        _ref_dc_draw_grid(lh[s], la[s], rho[s], n) for s in range(2)
    ]).mean(0)
    assert np.array_equal(got, ref)

    collapsed = _ref_dc_draw_grid(float(lh.mean()), float(la.mean()),
                                  float(rho.mean()), n)
    assert float(np.max(np.abs(got - collapsed))) > 1e-6, (
        "collapsed-draw grid indistinguishable — the per-draw test is vacuous")


def test_mean_grid_refuses_missing_or_unknown_correction():
    """Fail LOUD, never guess: the DC branch requires per-draw rho, the BP
    branch per-draw lambda3, and an unknown likelihood is refused — a silent
    independent-Poisson fallback would be exactly the incoherent map finding
    15 rejected."""
    lh = la = np.array([1.0, 1.0])
    with pytest.raises(ValueError, match="rho"):
        mean_grid_over_draws(lh, la, likelihood="dixon_coles",
                             max_goals=PRODUCTION_MAX_GOALS)
    with pytest.raises(ValueError, match="lambda3|l3"):
        mean_grid_over_draws(lh, la, likelihood="bivariate_poisson",
                             max_goals=PRODUCTION_MAX_GOALS)
    with pytest.raises(ValueError, match="likelihood"):
        mean_grid_over_draws(lh, la, likelihood="skellam", rho=np.zeros(2),
                             max_goals=PRODUCTION_MAX_GOALS)


def test_fixture_ctx_is_frozen_with_predict_default_semantics():
    """``FixtureCtx`` defaults mirror the ``predict_scoreline`` keyword surface
    (neutral=False, covariates=None, host_factor=None) and the ctx is frozen —
    a mutated context between rate build and finalization would silently
    decouple the two legs of the shared path."""
    ctx = FixtureCtx(home="A", away="B")
    assert ctx.neutral is False
    assert ctx.covariates is None
    assert ctx.host_factor is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.neutral = True


# ------------------------------------------------------- frozen max_goals pin


def _oa_calls(tree: ast.AST, names: frozenset[str]):
    """Yield ``(enclosing_function_name, ast.Call)`` for calls to any of
    ``names`` (bare name or attribute access)."""
    class _V(ast.NodeVisitor):
        def __init__(self):
            self.stack: list[str] = []
            self.found: list[tuple[str, ast.Call]] = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            f = node.func
            callee = f.id if isinstance(f, ast.Name) else (
                f.attr if isinstance(f, ast.Attribute) else None)
            if callee in names:
                self.found.append((self.stack[-1] if self.stack else "<module>",
                                   node))
            self.generic_visit(node)

    v = _V()
    v.visit(tree)
    return v.found


def test_production_max_goals_is_frozen_and_every_caller_is_pinned():
    """[LOAD-BEARING] ONE frozen truncation constant, every caller pinned.

    (a) ``PRODUCTION_MAX_GOALS`` == 10 — the value the production forecast
        path has always issued at (the ``predict_scoreline``/``predict_1x2``
        defaults, the dashboard ``fixture_forecast`` default, the releases
        ``price_fixtures`` default). Changing it is a prereg amendment.
    (b) Those production defaults all EQUAL the constant (inspected, so a
        drift in any one of them fails here, not in a scored run).
    (c) AST scan of ``src/wcmodel`` + ``scripts``: every call site of
        ``production_grid`` / ``solve_implied_rates`` either omits
        ``max_goals`` or passes the constant BY NAME. The single sanctioned
        pass-through is ``Posterior.predict_scoreline`` forwarding its own
        ``max_goals`` parameter (whose default is pinned in (b)) so legacy
        diagnostic harnesses keep their explicit-truncation API; the scan
        counts it to exactly one so no new caller can ride the exemption.
    """
    from wcmodel.dashboard.fixtures import fixture_forecast
    from wcmodel.eval.implied import solve_implied_rates
    from wcmodel.releases.pricing import price_fixtures

    # (a) the frozen production value.
    assert PRODUCTION_MAX_GOALS == 10

    # (b) every production-path signature default IS the frozen value.
    def default_of(func, param="max_goals"):
        return inspect.signature(func).parameters[param].default

    assert default_of(production_grid) == PRODUCTION_MAX_GOALS
    assert default_of(solve_implied_rates) == PRODUCTION_MAX_GOALS
    assert default_of(Posterior.predict_scoreline) == PRODUCTION_MAX_GOALS
    assert default_of(Posterior.predict_1x2) == PRODUCTION_MAX_GOALS
    assert default_of(fixture_forecast) == PRODUCTION_MAX_GOALS
    assert default_of(price_fixtures) == PRODUCTION_MAX_GOALS
    # max_goals is KEYWORD-ONLY on the OA surface, so the AST scan below
    # cannot be bypassed positionally.
    assert inspect.signature(production_grid).parameters["max_goals"].kind \
        is inspect.Parameter.KEYWORD_ONLY
    assert inspect.signature(solve_implied_rates).parameters["max_goals"].kind \
        is inspect.Parameter.KEYWORD_ONLY

    # (c) scan every call site.
    repo = Path(wcmodel.__file__).resolve().parents[2]
    files = sorted((repo / "src" / "wcmodel").rglob("*.py"))
    files += sorted((repo / "scripts").glob("*.py"))
    names = frozenset({"production_grid", "solve_implied_rates"})

    violations: list[str] = []
    pass_throughs: list[str] = []
    n_calls = 0
    for path in files:
        tree = ast.parse(path.read_text(), filename=str(path))
        for func_name, call in _oa_calls(tree, names):
            n_calls += 1
            where = f"{path.relative_to(repo)}:{call.lineno} (in {func_name})"
            if len(call.args) > 2:
                violations.append(f"{where}: positional max_goals")
            for kw in call.keywords:
                if kw.arg != "max_goals":
                    continue
                v = kw.value
                if (isinstance(v, ast.Name) and v.id == "PRODUCTION_MAX_GOALS") \
                        or (isinstance(v, ast.Attribute)
                            and v.attr == "PRODUCTION_MAX_GOALS"):
                    continue           # the frozen constant, by name
                if (path.name == "posterior.py"
                        and func_name == "predict_scoreline"
                        and isinstance(v, ast.Name) and v.id == "max_goals"):
                    pass_throughs.append(where)   # the ONE sanctioned forward
                    continue
                violations.append(f"{where}: max_goals={ast.dump(v)}")

    assert n_calls >= 1, "scan found no OA-map call sites — the pin is vacuous"
    assert violations == [], (
        "callers overriding the frozen production max_goals:\n"
        + "\n".join(violations))
    assert len(pass_throughs) == 1, (
        "exactly one sanctioned predict_scoreline pass-through expected, got "
        f"{pass_throughs}")


def test_draw_api_module_exposes_the_frozen_constant_once():
    """The constant lives in draw_api and is IMPORTED everywhere else — the
    posterior module's name must be the SAME object, not a re-definition."""
    from wcmodel.model import posterior as posterior_mod
    assert posterior_mod.PRODUCTION_MAX_GOALS is draw_api.PRODUCTION_MAX_GOALS
