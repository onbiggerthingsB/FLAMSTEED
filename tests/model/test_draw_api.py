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


# --------------------------------------------------------------- golden pins


#: sha256 of ``production_grid(...).tobytes()`` for each golden case below,
#: computed ONCE from the deterministic compact ADVI fit (seed 0, draws 40,
#: advi_iters 300 on the ``_RAW_RESULTS`` panel, cutoff 2024-06-01; the
#: covariate case is the same fit with ``covariates=("rest_days",)``).
#:
#: REGENERATION NOTE (B2-4): these literals pin the map's NUMBERS, not just
#: path parity — ``predict_scoreline`` DELEGATES to ``production_grid``, so
#: the bitwise parity test above is tautological against a refactor that
#: drifts both paths together; this golden set is what catches that. They are
#: environment-pinned (a legitimate BLAS/pymc/numpy upgrade may shift the
#: ADVI draws): after verifying the change is an environment change and NOT a
#: semantic drift of the map (diff the grids, not just the hashes), re-run
#: ``pytest tests/model/test_draw_api.py -k golden`` and copy the "got"
#: values from the assertion diff over these literals — the single dict
#: compare prints every case.
_GOLDEN_GRID_SHA256 = {
    "ordinary":
        "177ecbb07b1b8038c8c8b7daff887c9595cd9794d61312a863183e0373532e63",
    "neutral":
        "4c4a465613ee4f03efbdf664f6b71dabeb1f0a463aa6a5efd97b10d59c54d87c",
    "host":
        "28852e06c4aa73c3b2e6cb80479c83ae462c61be5fecacd93b365371e419b432",
    "provisional":
        "51f2b20179930aafe901363669e1e738147e3d0acdc4cab6ccd52fa72f8c0c5f",
    "covariate":
        "b7ca9390c254d8b6a2bb4bcc7030413b16172cb41d1895f9fba4f353b406ff11",
}


@pytest.fixture(scope="module")
def real_covariate_posterior(tmp_path_factory):
    """A second compact ADVI fit with the rest_days covariate ENABLED — the
    production default is covariate-free, so the covariate leg of the map
    can only be pinned non-vacuously on this fit."""
    return fit_compact_real_posterior(
        tmp_path_factory.mktemp("draw_api_cov_store"),
        covariates=("rest_days",))


@pytest.mark.slow
def test_golden_grids_pin_the_production_map_numbers(real_posterior,
                                                     real_covariate_posterior):
    """[LOAD-BEARING, B2-4] Golden real-Posterior grids. The parity test
    above proves predict == production_grid, but since predict DELEGATES to
    production_grid that cannot catch a refactor drifting BOTH paths
    together. These sha256 literals pin the actual grid bytes for every
    production fixture-context case — ordinary, neutral, host, provisional
    (widening fired) and covariate (offsets fired) — against the
    deterministic compact fit, so any semantic drift of the map fails
    loudly even when parity still holds."""
    import hashlib

    post = real_posterior
    cov_post = real_covariate_posterior
    settled = [t for t in post.teams if t not in post.provisional_teams]
    home, away = settled[0], settled[1]
    prov = sorted(post.provisional_teams)[0]

    # the covariate fit sees the same panel: same teams, same provisional set
    assert cov_post.teams == post.teams
    assert cov_post.provisional_teams == post.provisional_teams
    assert sorted(cov_post.covariate_transforms) == ["rest_days"]
    assert post.covariate_transforms == {}

    cov_ctx = FixtureCtx(home=home, away=away,
                         covariates={"rest_days": 3.0, "rest_days__away": 9.0})
    cases = {
        "ordinary": (post, FixtureCtx(home=home, away=away)),
        "neutral": (post, FixtureCtx(home=home, away=away, neutral=True)),
        # 1.4 == the calibrated production host_k, hardcoded so the golden
        # inputs are self-contained (a config change must not move them).
        "host": (post, FixtureCtx(home=home, away=away, host_factor=1.4)),
        "provisional": (post, FixtureCtx(home=home, away=prov, neutral=True)),
        "covariate": (cov_post, cov_ctx),
    }
    grids = {}
    for label, (p, ctx) in cases.items():
        g = production_grid(p, ctx)
        assert g.dtype == np.float64 and g.shape == (11, 11), label
        grids[label] = g

    # non-vacuity: five genuinely different grids (each context leg fired)...
    got = {label: hashlib.sha256(g.tobytes()).hexdigest()
           for label, g in grids.items()}
    assert len(set(got.values())) == len(got)
    # ...and the covariate offsets moved the grid on ITS OWN fit's baseline.
    assert not np.array_equal(
        grids["covariate"],
        production_grid(cov_post, FixtureCtx(home=home, away=away)))

    assert got == _GOLDEN_GRID_SHA256


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
    """Yield ``(enclosing_function_name, callee_name, ast.Call)`` for calls
    to any of ``names`` (bare name or attribute access)."""
    class _V(ast.NodeVisitor):
        def __init__(self):
            self.stack: list[str] = []
            self.found: list[tuple[str, str, ast.Call]] = []

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
                                   callee, node))
            self.generic_visit(node)

    v = _V()
    v.visit(tree)
    return v.found


def _default_is_the_constant_by_name(module_path: Path, func: str,
                                     param: str = "max_goals") -> bool:
    """True iff ``func``'s ``param`` default is spelled PRODUCTION_MAX_GOALS
    in the source — a literal ``10`` passes the VALUE check in (b) while
    silently detaching from the frozen constant (B2-6)."""
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == func:
            args = node.args
            all_args = args.posonlyargs + args.args + args.kwonlyargs
            defaults = ([None] * (len(args.posonlyargs) + len(args.args)
                                  - len(args.defaults))
                        + list(args.defaults) + list(args.kw_defaults))
            for arg, default in zip(all_args, defaults):
                if arg.arg != param:
                    continue
                return (isinstance(default, ast.Name)
                        and default.id == "PRODUCTION_MAX_GOALS") or \
                       (isinstance(default, ast.Attribute)
                        and default.attr == "PRODUCTION_MAX_GOALS")
    raise AssertionError(f"{func} not found in {module_path}")


def test_production_max_goals_is_frozen_and_every_caller_is_pinned():
    """[LOAD-BEARING] ONE frozen truncation constant, every caller pinned.

    (a) ``PRODUCTION_MAX_GOALS`` == 10 — the value the production forecast
        path has always issued at (the ``predict_scoreline``/``predict_1x2``
        defaults, the dashboard ``fixture_forecast`` default, the releases
        ``price_fixtures`` default). Changing it is a prereg amendment.
    (b) Those production defaults all EQUAL the constant (inspected, so a
        drift in any one of them fails here, not in a scored run) — and the
        dashboard/releases defaults are spelled AS the constant in source
        (B2-6): a literal ``10`` equals the value today but silently detaches
        the caller the day the constant is ever amended.
    (c) AST scan of ``src/wcmodel`` + ``scripts``: every call site of
        ``production_grid`` / ``solve_implied_rates`` / ``blend_grid`` /
        ``blend_one_x_two`` (the blend surface rides the same freeze — B2-6)
        either omits ``max_goals`` or passes the constant BY NAME. The
        sanctioned pass-throughs are EXACTLY ``Posterior.predict_scoreline``
        (legacy diagnostic harnesses keep their explicit-truncation API) and
        ``blend_one_x_two`` forwarding to ``blend_grid`` — each forwarding
        its own ``max_goals`` parameter whose default is pinned in (b); the
        scan counts them exactly so no new caller can ride either exemption.
    """
    from wcmodel.dashboard.fixtures import fixture_forecast
    from wcmodel.eval.blend import blend_grid, blend_one_x_two
    from wcmodel.eval.implied import solve_implied_rates
    from wcmodel.releases.pricing import price_fixtures

    # (a) the frozen production value.
    assert PRODUCTION_MAX_GOALS == 10

    # (b) every production-path signature default IS the frozen value.
    def default_of(func, param="max_goals"):
        return inspect.signature(func).parameters[param].default

    assert default_of(production_grid) == PRODUCTION_MAX_GOALS
    assert default_of(solve_implied_rates) == PRODUCTION_MAX_GOALS
    assert default_of(blend_grid) == PRODUCTION_MAX_GOALS
    assert default_of(blend_one_x_two) == PRODUCTION_MAX_GOALS
    assert default_of(Posterior.predict_scoreline) == PRODUCTION_MAX_GOALS
    assert default_of(Posterior.predict_1x2) == PRODUCTION_MAX_GOALS
    assert default_of(fixture_forecast) == PRODUCTION_MAX_GOALS
    assert default_of(price_fixtures) == PRODUCTION_MAX_GOALS
    # max_goals is KEYWORD-ONLY on the OA surface, so the AST scan below
    # cannot be bypassed positionally.
    for func in (production_grid, solve_implied_rates, blend_grid,
                 blend_one_x_two):
        assert inspect.signature(func).parameters["max_goals"].kind \
            is inspect.Parameter.KEYWORD_ONLY, func

    repo = Path(wcmodel.__file__).resolve().parents[2]
    # (b, continued) the dashboard/releases defaults are the constant BY
    # NAME in source, not a detached literal 10 (B2-6).
    for module, func in (
        (repo / "src/wcmodel/dashboard/fixtures.py", "fixture_forecast"),
        (repo / "src/wcmodel/releases/pricing.py", "price_fixtures"),
    ):
        assert _default_is_the_constant_by_name(module, func), (
            f"{module.name}:{func} defaults max_goals to a literal instead "
            "of PRODUCTION_MAX_GOALS (B2-6)")

    # (c) scan every call site.
    files = sorted((repo / "src" / "wcmodel").rglob("*.py"))
    files += sorted((repo / "scripts").glob("*.py"))
    # Positional-arity ceiling per callee: max_goals is keyword-only on all
    # four, so this only guards against a future signature loosening.
    max_positional = {"production_grid": 2, "solve_implied_rates": 3,
                      "blend_grid": 4, "blend_one_x_two": 4}
    names = frozenset(max_positional)
    sanctioned = {
        ("posterior.py", "predict_scoreline", "production_grid"),
        ("blend.py", "blend_one_x_two", "blend_grid"),
    }

    violations: list[str] = []
    pass_throughs: list[tuple[str, str, str]] = []
    n_calls = 0
    for path in files:
        tree = ast.parse(path.read_text(), filename=str(path))
        for func_name, callee, call in _oa_calls(tree, names):
            n_calls += 1
            where = f"{path.relative_to(repo)}:{call.lineno} (in {func_name})"
            if len(call.args) > max_positional[callee]:
                violations.append(f"{where}: positional max_goals")
            for kw in call.keywords:
                if kw.arg != "max_goals":
                    continue
                v = kw.value
                if (isinstance(v, ast.Name) and v.id == "PRODUCTION_MAX_GOALS") \
                        or (isinstance(v, ast.Attribute)
                            and v.attr == "PRODUCTION_MAX_GOALS"):
                    continue           # the frozen constant, by name
                if ((path.name, func_name, callee) in sanctioned
                        and isinstance(v, ast.Name) and v.id == "max_goals"):
                    pass_throughs.append((path.name, func_name, callee))
                    continue
                violations.append(f"{where}: max_goals={ast.dump(v)}")

    assert n_calls >= 2, "scan found no OA-map call sites — the pin is vacuous"
    assert violations == [], (
        "callers overriding the frozen production max_goals:\n"
        + "\n".join(violations))
    assert sorted(pass_throughs) == sorted(sanctioned), (
        "exactly the two sanctioned pass-throughs expected once each, got "
        f"{pass_throughs}")


def test_draw_api_module_exposes_the_frozen_constant_once():
    """The constant lives in draw_api and is IMPORTED everywhere else — the
    posterior module's name must be the SAME object, not a re-definition."""
    from wcmodel.model import posterior as posterior_mod
    assert posterior_mod.PRODUCTION_MAX_GOALS is draw_api.PRODUCTION_MAX_GOALS
