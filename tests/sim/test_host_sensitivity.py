"""T5 host-advantage SENSITIVITY artifact (the documented k-sweep table).

The host factor ``k`` (config ``model.covariates.host_k``) is an ASSUMPTION, not a
fitted number — it scales the ALREADY-FITTED ``home_adv`` for a 2026 host's home game
(``k*home_adv``). No new parameter is estimated. This module prints the hosts'
champion / advance probabilities under ``k in {0, 0.5, 0.7, 1.0}`` and asserts the
k-sweep is correctly WIRED (a larger k strictly raises the host's forward probability)
so the published sensitivity table is reproducible from the sim.

It is deliberately FAST: a hand-rolled toy ``Posterior`` over the ``tiny_bracket()``
(1 group of 4 -> a single Final), the same ``_toy_posterior`` pattern the convergence
tests use, with ``home_adv`` set to a fixed, clearly-positive value so the k-effect is
visible at a small ``n_sims``. A full ADVI fit + 48-team sim is unnecessary to exercise
the wiring — the point is the k-sweep plumbing, not a production probability.
"""
import numpy as np
import pytest
import xarray as xr

from wcmodel.model.posterior import Posterior
from wcmodel.sim.tournament import simulate_tournament

from tests.sim.conftest import _TINY_TEAMS, tiny_bracket

# tiny_bracket()'s four group-A teams, in build_bracket's group order (the bracket
# hardcodes these names, so the toy posterior MUST be over the SAME set). We treat the
# FIRST team as the stand-in "host" — its 3 HOME group fixtures carry k*home_adv. The
# host-detection rule (host nation + in-country venue) is unit-tested separately in
# tests/model/test_covariates.py::test_host_home_factor_detection; HERE we exercise only
# the k-sweep WIRING through the sim, so any team can play the host role.
_TEAMS = list(_TINY_TEAMS)
_HOST = _TEAMS[0]

# The host's 3 HOME group fixtures in tiny_bracket()'s round-robin: (a,b), (a,c), (a,d).
# Only the fixtures where the host is the HOME team are host-home (host advantage accrues
# to the home side only) — matching host_factor_map's group-fixture detection.
_HOST_HOME_FIXTURES = [(_HOST, _TEAMS[1]), (_HOST, _TEAMS[2]), (_HOST, _TEAMS[3])]

# The documented sensitivity grid. k=0 is neutral (today's WC default); k=1 is full
# home advantage; 0.5 is the config default; 0.7 a mid-high sensitivity point.
_K_GRID = [0.0, 0.5, 0.7, 1.0]


def _toy_posterior(att, deff, *, mu=0.1, home_adv=0.5, rho=-0.05, teams=_TEAMS):
    """A minimal REAL Posterior with FIXED per-team att/def + a clearly-positive
    ``home_adv`` (so k*home_adv is visible). One fixed draw (chain=draw=1) -> the only
    stochasticity is scoreline/tiebreak sampling. Mirrors test_convergence._toy_posterior."""
    att = np.asarray(att, dtype=float)
    deff = np.asarray(deff, dtype=float)
    n = len(teams)
    ds = xr.Dataset(
        {
            "att": (("chain", "draw", "team"), att.reshape(1, 1, n)),
            "def": (("chain", "draw", "team"), deff.reshape(1, 1, n)),
            "mu": (("chain", "draw"), np.full((1, 1), mu)),
            "home_adv": (("chain", "draw"), np.full((1, 1), home_adv)),
            "rho": (("chain", "draw"), np.full((1, 1), rho)),
        },
        coords={"team": list(teams)},
    )
    idata = xr.DataTree.from_dict({"posterior": ds})
    return Posterior(idata, list(teams), "dixon_coles", provisional_teams=set())


def _sweep_host_probs(*, n_sims=4000, seed=0):
    """Run the tiny-bracket sim under each k in _K_GRID and return
    ``{k: {"champion": p, "advance_from_group": p}}`` for the host team.

    The field is EQUAL-strength (every att/def identical), so any lift in the host's
    forward probability as k rises is attributable PURELY to k*home_adv on its home
    group games — the cleanest possible read on the k-sweep wiring."""
    post = _toy_posterior(att=[0.0, 0.0, 0.0, 0.0], deff=[0.0, 0.0, 0.0, 0.0])
    table = {}
    for k in _K_GRID:
        # host_factors: the host's 3 home group fixtures carry k; k=0 == neutral.
        host_factors = {pair: k for pair in _HOST_HOME_FIXTURES}
        res = simulate_tournament(
            post, bracket=tiny_bracket(), n_sims=n_sims, seed=seed,
            max_goals=12, et_scale=0.3333, pen_home_prob=0.5,
            host_factors=host_factors,
        )
        table[k] = {
            "champion": float(res.progression.loc[_HOST, "champion"]),
            "advance_from_group": float(res.progression.loc[_HOST, "advance_from_group"]),
        }
    return table


def test_host_k_sensitivity_table_is_monotone_and_documented(capsys):
    """The documented host k-sweep: print the host's champion/advance probabilities for
    k in {0, 0.5, 0.7, 1.0}, and assert the sweep is correctly WIRED — a larger k (more
    home advantage) strictly raises BOTH the host's advance and champion probability, and
    k=0 is the neutral baseline. No number here is fitted: k is an assumption on the
    already-fitted home_adv (no new DOF). Run with ``-s`` to see the table."""
    table = _sweep_host_probs()

    # Print the sensitivity table (visible under pytest -s) — the documented artifact.
    print(f"\nHost ({_HOST}) probability sensitivity to host factor k "
          f"(k=0 neutral, k=1 full home_adv); equal-strength field, tiny bracket:")
    print(f"  {'k':>4}  {'advance':>9}  {'champion':>9}")
    for k in _K_GRID:
        row = table[k]
        print(f"  {k:>4.2f}  {row['advance_from_group']:>9.4f}  {row['champion']:>9.4f}")

    advance = [table[k]["advance_from_group"] for k in _K_GRID]
    champion = [table[k]["champion"] for k in _K_GRID]

    # MONOTONE wiring: each step up in k must not lower the host's forward probability,
    # and the endpoints must strictly separate (the k-effect is real, not noise). With an
    # equal-strength field + a fixed seed these are deterministic comparisons.
    for lo, hi in zip(advance, advance[1:]):
        assert lo <= hi + 1e-12                       # advance non-decreasing in k
    for lo, hi in zip(champion, champion[1:]):
        assert lo <= hi + 1e-12                       # champion non-decreasing in k
    assert advance[0] < advance[-1]                   # k=0 (neutral) < k=1 (full): real lift
    assert champion[0] < champion[-1]
    # k=0 is the neutral baseline: with an equal-strength 4-team field the host's
    # neutral champion prob sits near 1/4 (within a generous band for n_sims).
    assert 0.15 < champion[0] < 0.35

    # The captured output carries the printed table (so the artifact is in the test log).
    out = capsys.readouterr().out
    assert "host factor k" in out and f"{_K_GRID[-1]:.2f}" in out
