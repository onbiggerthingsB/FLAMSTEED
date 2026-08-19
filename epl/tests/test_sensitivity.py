"""D19 — the sensitivity's arithmetic, and a real positive control on the swap.

Two things have to be true before the D19 report means anything.

1. The backend swap has to be REAL. ``richer_config`` only edits a dict; if the
   dict never reached a different sampler, or if both samplers produced the same
   dispersion, the report would compare a thing with itself and print ratios of
   1.000 that looked like a clean bill of health. The positive control here
   fits a deliberately CORRELATED two-dimensional Gaussian through the same
   ``wcmodel.model.inference.sample`` the EPL fit calls, once per backend, and
   asserts mean-field comes back visibly tighter. Mean-field VI factorises the
   posterior, so on a correlated target it underestimates the marginal
   variances — a textbook fact, and the reason D19 exists. Cheap: a 2-D model,
   a few hundred draws.

2. The comparison arithmetic has to be able to SAY so. Every ratio helper is
   paired with the input that must move it: identical posteriors give exactly
   1, a deliberately narrowed one gives more than 1, a degenerate denominator
   refuses rather than returning an infinity.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from epl import sensitivity


# ==========================================================================
# stubs — a posterior is anything with `_post`
# ==========================================================================
class _Post:
    def __init__(self, arrays: dict[str, np.ndarray]):
        self._arrays = arrays

    def _post(self, name):
        return self._arrays[name]


def _posterior(n_teams: int = 4, n_draws: int = 500, *, scale: float = 1.0,
               seed: int = 3) -> _Post:
    rng = np.random.default_rng(seed)
    return _Post({
        "att": scale * rng.standard_normal((n_teams, n_draws)),
        "def": scale * rng.standard_normal((n_teams, n_draws)),
        "home_adv": scale * rng.standard_normal(n_draws),
        "mu": scale * rng.standard_normal(n_draws),
        "rho": scale * rng.standard_normal(n_draws),
    })


# ==========================================================================
# 1. selecting the backend
# ==========================================================================
def test_richer_config_swaps_the_backend_without_touching_the_frozen_one():
    base = {"model": {"inference": {"backend": "advi", "draws": 1000,
                                    "tune": 1000, "advi_iters": 30000}}}
    snapshot = copy.deepcopy(base)

    cfg = sensitivity.richer_config(base, backend="nuts", draws=500, tune=1000)
    assert cfg["model"]["inference"]["backend"] == "nuts"
    assert cfg["model"]["inference"]["draws"] == 500
    # the advi_iters the production path uses survives untouched
    assert cfg["model"]["inference"]["advi_iters"] == 30000
    # ...and the config handed in is NOT mutated: production shares this object
    assert base == snapshot


def test_an_unreachable_backend_is_refused_rather_than_left_to_raise_later():
    base = {"model": {"inference": {"backend": "advi", "draws": 10, "tune": 10}}}
    for backend in ("fullrank_advi", "pathfinder", "svgd", ""):
        with pytest.raises(sensitivity.SensitivityError) as exc:
            sensitivity.richer_config(base, backend=backend)
        assert "dispatch" in str(exc.value)


def test_draw_count_knows_nuts_runs_two_chains():
    base = {"model": {"inference": {"backend": "advi", "draws": 1000,
                                    "tune": 1000}}}
    assert sensitivity.draw_count(base) == 1000
    assert sensitivity.draw_count(
        sensitivity.richer_config(base, backend="nuts", draws=500)) == 1000


# ==========================================================================
# 2. the arithmetic, and what must move it
# ==========================================================================
def test_posterior_sds_have_one_entry_per_club_and_one_per_scalar():
    sds = sensitivity.posterior_sds(_posterior(n_teams=6))
    assert sds["att"].shape == (6,)
    assert sds["def"].shape == (6,)
    for name in ("mu", "home_adv", "rho"):
        assert sds[name].shape == (1,)


def test_identical_posteriors_give_a_ratio_of_exactly_one():
    sds = sensitivity.posterior_sds(_posterior())
    ratios = sensitivity.sd_ratios(sds, sds)
    for name, cell in ratios.items():
        assert cell["mean"] == pytest.approx(1.0, abs=1e-12), name
        assert cell["min"] == pytest.approx(1.0, abs=1e-12), name
        assert cell["max"] == pytest.approx(1.0, abs=1e-12), name


def test_a_narrowed_mean_field_shows_up_as_a_ratio_above_one():
    """POSITIVE CONTROL for the ratio itself: halve the mean-field spread and
    the reported ratio must be 2, not 1."""
    reference = sensitivity.posterior_sds(_posterior(scale=1.0))
    tight = {k: v / 2.0 for k, v in reference.items()}
    ratios = sensitivity.sd_ratios(reference, tight,
                                   teams=("a", "b", "c", "d"))
    for name, cell in ratios.items():
        assert cell["mean"] == pytest.approx(2.0, abs=1e-9), name
    assert ratios["att"]["max_team"] in {"a", "b", "c", "d"}


def test_mismatched_shapes_and_degenerate_denominators_refuse():
    reference = sensitivity.posterior_sds(_posterior(n_teams=4))
    other = sensitivity.posterior_sds(_posterior(n_teams=5))
    with pytest.raises(sensitivity.SensitivityError) as exc:
        sensitivity.sd_ratios(reference, other)
    assert "same objects" in str(exc.value)

    degenerate = {k: np.zeros_like(v) for k, v in reference.items()}
    with pytest.raises(sensitivity.SensitivityError) as exc:
        sensitivity.sd_ratios(reference, degenerate)
    assert "denominator" in str(exc.value)


# ==========================================================================
# 3. reading a run
# ==========================================================================
class _Run:
    """The three things the sensitivity reads off a SimRun."""

    def __init__(self, clubs, probs, points):
        self.clubs = tuple(clubs)
        self.consequences = {
            club: {market: {"p": probs[market][i], "se": 0.001}
                   for market in ("champion", "top4", "relegated")}
            for i, club in enumerate(clubs)}
        self.retained_rows = type("R", (), {"points": np.asarray(points)})()


def _run(clubs=("a", "b", "c"), seed: int = 1) -> _Run:
    rng = np.random.default_rng(seed)
    n = len(clubs)
    probs = {"champion": np.full(n, 1.0 / n), "top4": np.ones(n),
             "relegated": np.array([0.6, 0.3, 0.1][:n])}
    return _Run(clubs, probs, rng.integers(20, 90, size=(400, n)))


def test_consequence_table_reads_p_and_se_for_every_club():
    table = sensitivity.consequence_table(_run())
    assert set(table) == {"champion", "top4", "relegated"}
    assert set(table["champion"]) == {"a", "b", "c"}
    value, se = table["champion"]["a"]
    assert value == pytest.approx(1 / 3)
    assert se == pytest.approx(0.001)

    with pytest.raises(sensitivity.SensitivityError):
        sensitivity.consequence_table(_run(), markets=("top9",))


def test_points_sds_are_the_spread_of_the_simulated_seasons():
    run = _run()
    sds = sensitivity.points_sds(run)
    assert set(sds) == {"a", "b", "c"}
    expected = float(np.asarray(run.retained_rows.points)[:, 0].std(ddof=1))
    assert sds["a"] == pytest.approx(expected)


def test_expected_relegations_sums_the_named_clubs_and_bounds_its_error():
    got = sensitivity.expected_relegations_among(_run(), ("a", "b"))
    assert got["expected"] == pytest.approx(0.9)
    assert got["se_upper_bound"] == pytest.approx(0.002)
    with pytest.raises(sensitivity.SensitivityError):
        sensitivity.expected_relegations_among(_run(), ("a", "zzz"))


# ==========================================================================
# 4. the report builder
# ==========================================================================
def _arm(name: str, backend: str, trps: float) -> sensitivity.Arm:
    run = _run()
    return sensitivity.Arm(
        name=name, backend=backend, n_draws=1000, fit_seconds=12.0,
        sim_seconds=9.0, sds=sensitivity.posterior_sds(_posterior()),
        consequences=sensitivity.consequence_table(run),
        points_sd=sensitivity.points_sds(run), trps=trps,
        promoted=sensitivity.expected_relegations_among(run, ("a", "b")))


def test_report_names_both_arms_every_market_and_the_honest_caveats():
    mean_field = _arm("mean-field ADVI", "advi", 0.1356)
    richer = _arm("NUTS", "nuts", 0.1361)
    ratios = sensitivity.sd_ratios(richer.sds, mean_field.sds,
                                   teams=("a", "b", "c", "d"))
    text = sensitivity.report_markdown(
        season="2025/26", cutoff="2025-08-15", cutoff_label="MW0",
        mean_field=mean_field, richer=richer, ratios=ratios, hyper_ratios={},
        clubs=("a", "b", "c"), realised={"n_shared": 0}, n_sims=20_000,
        seed=20260611, conclusion="Mean-field is not visibly under-dispersed here.")

    for needed in ("D19", "2025/26", "MW0", "advi", "nuts", "TRPS",
                   "champion", "top4", "relegated",
                   "Monte-Carlo error is not model error",
                   "not claims about qualification", "0.1356", "0.1361"):
        assert needed in text, needed
    # every parameter the book carries is named in the dispersion table
    for name in sensitivity.PARAMS:
        assert f"`{name}`" in text, name


# ==========================================================================
# 5. THE POSITIVE CONTROL — the two backends really do disperse differently
# ==========================================================================
@pytest.mark.slow
def test_mean_field_advi_is_measurably_tighter_than_nuts_on_a_correlated_target():
    """The swap is real, and it is the swap D19 is about.

    A two-dimensional Gaussian with correlation 0.95. Mean-field VI factorises
    the approximation, so it cannot represent that correlation and comes back
    with marginal standard deviations well below the truth; NUTS samples the
    joint and recovers them. If this ever stopped holding — a stack where both
    branches ran the same sampler, or a config that never reached
    ``sample`` — the D19 report's ratios would be meaningless, and this test is
    what would say so.
    """
    import pymc as pm
    from wcmodel.model.inference import sample

    rho, sd = 0.95, 1.0
    cov = np.array([[sd ** 2, rho * sd * sd], [rho * sd * sd, sd ** 2]])
    with pm.Model() as model:
        pm.MvNormal("theta", mu=np.zeros(2), cov=cov, shape=2)

    advi = sample(model, backend="advi", draws=500, seed=11, advi_iters=8000)
    nuts = sample(model, backend="nuts", draws=400, tune=400, seed=11)

    def marginal_sd(idata):
        arr = idata.posterior["theta"].stack(s=("chain", "draw")).values
        return np.asarray(arr, float).std(axis=1, ddof=1)

    advi_sd, nuts_sd = marginal_sd(advi), marginal_sd(nuts)
    ratio = nuts_sd / advi_sd
    assert (ratio > 1.5).all(), (
        f"mean-field {advi_sd} vs NUTS {nuts_sd} (ratio {ratio}): mean-field "
        "was not tighter, so the backend swap is not doing what D19 assumes")
    # ...and NUTS is near the truth, so the gap is ADVI being tight rather than
    # NUTS being loose
    assert np.allclose(nuts_sd, sd, rtol=0.25), nuts_sd


# ==========================================================================
# 6. the dump, and rebuilding the report from it without refitting
# ==========================================================================
def _payload() -> dict:
    mean_field = _arm("mean-field ADVI", "advi", 0.13557)
    richer = _arm("NUTS", "nuts", 0.13593)
    richer.provenance = {"convergence": {
        "available": True, "converged": False, "max_rhat": 1.0200,
        "min_ess": 380.9, "flagged": [{"param": "att", "rhat": 1.015}]}}
    ratios = sensitivity.sd_ratios(richer.sds, mean_field.sds,
                                   teams=("a", "b", "c", "d"))
    got = {"season": "2025/26", "cutoff": "2025-08-15", "cutoff_label": "MW0",
           "n_sims": 20_000, "seed": 20260611, "clubs": ["a", "b", "c"],
           "promoted": ["a"], "realised": {"n_shared": 0}, "ratios": ratios,
           "hyper_ratios": {},
           "arms": {"mean_field": mean_field, "richer": richer}}
    return sensitivity.payload_of(got)


def test_the_dump_is_plain_json_and_carries_what_the_report_needs():
    import json

    payload = _payload()
    json.dumps(payload)                      # no numpy, no tuples-as-keys
    for key in ("season", "cutoff", "cutoff_label", "n_sims", "seed", "clubs",
                "promoted", "realised", "ratios", "arms"):
        assert key in payload, key
    for arm in ("mean_field", "richer"):
        for key in ("name", "backend", "n_draws", "fit_seconds", "sim_seconds",
                    "trps", "points_sd", "promoted", "consequences"):
            assert key in payload["arms"][arm], (arm, key)


def test_the_report_rebuilds_from_the_dump_and_names_the_convergence_warning():
    payload = _payload()
    text = sensitivity.report_from_payload(
        payload, conclusion="The one paragraph a human wrote.")
    assert "The one paragraph a human wrote." in text
    assert "0.1356" in text and "0.1359" in text
    # the r-hat warning is carried into the report, not quietly dropped
    assert "r-hat" in text and "1.0200" in text
    assert "flagged" in text and "att" in text
    assert "not a reference" in text


def test_the_report_carries_provenance_and_a_reproduction_command():
    payload = _payload()
    payload["arms"]["mean_field"]["provenance"] = {
        "effective_posterior_hash": "aaa111", "numbers_digest": "bbb222",
        "n_teams": 35, "n_training_matches": 4180,
        "cold_start_teams": [], "provisional_teams": []}
    text = sensitivity.report_from_payload(payload, conclusion="x")
    assert "## 7. Provenance" in text
    assert "`aaa111`" in text and "`bbb222`" in text
    assert "4180" in text
    # the cutoff's cold-start / provisional state is stated, not assumed
    assert "Cold-start clubs at this cutoff: **none**" in text
    assert "provisional clubs: **none**" in text
    # and the report says how to reproduce itself
    assert "epl.sensitivity" in text and "--from-json" in text


def test_a_converged_reference_says_so_instead_of_warning():
    payload = _payload()
    payload["arms"]["richer"]["provenance"]["convergence"] = {
        "available": True, "converged": True, "max_rhat": 1.0007,
        "min_ess": 900.0, "flagged": []}
    text = sensitivity.report_from_payload(payload, conclusion="x")
    assert "nothing flagged above 1.01" in text
    assert "not a reference" not in text


def test_convergence_is_undefined_for_a_single_chain_rather_than_reassuring():
    class _Single:
        idata = None

    got = sensitivity.convergence(_Single())
    assert got["available"] is False
    assert "single chain" in got["reason"]
    # ...and it does NOT claim convergence
    assert "converged" not in got


def test_promoted_into_reads_the_archive_and_has_no_predecessor_at_the_start():
    frame = pd.DataFrame({
        "season": ["2023/24"] * 3 + ["2024/25"] * 3,
        "home_key": ["a", "b", "c", "a", "b", "z"]})
    assert sensitivity.promoted_into(frame, "2024/25") == ["z"]
    assert sensitivity.promoted_into(frame, "2023/24") == []
