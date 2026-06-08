"""REGRESSION (Codex): the sim's T5 host_factors MUST derive from the CALLER's config
(the cfg threaded into ``build_snapshot``/``SimConfig.from_config``), NOT the disk default.

THE BUG this guards. ``sim/run.py::simulate`` built ``host_factors = host_factor_map(
tournament, load_config())`` — the DISK config (``host_k`` default 0.5), ignoring the
caller's cfg. But ``dashboard/build.py`` renders its per-fixture forecasts with the CALLER
cfg's ``host_k`` (via ``host_home_factor(..., cfg)``). So a ``build_snapshot(config=cfg)``
with an overridden ``host_k`` (e.g. 0.7) rendered the dashboard fixture forecasts at 0.7
while the SIM progression — and the sim-cache key — used 0.5. Two failures:
  * dashboard and sim DISAGREE on host_k for the same call (the dashboard's host-home
    fixture forecast is computed at a k the sim never used); and
  * the host_k SENSITIVITY SWEEP (T8: k in {0, 0.5, 0.7, 1.0}) couldn't move the sim —
    every k re-derived the same disk 0.5 host map, so the sim (and its cache key) was
    byte-identical across k.

THE FIX. ``SimConfig`` now carries the caller's ``config`` (``from_config`` captures it),
and ``simulate`` derives ``host_factors = host_factor_map(tournament, config.config)`` from
THAT cfg — the SINGLE SOURCE shared with the dashboard's per-fixture ``host_home_factor``.

WHAT THIS MODULE ASSERTS (all over the SAME synthetic 1-group tournament whose Mexico-Malta
fixture is host-home — Mexico is a 2026 host, the fixture's venue is in MX — so a non-zero
``host_k`` lifts Mexico's forward probability):

  1. ``test_caller_host_k_reaches_the_sim``: ``simulate()`` driven by
     ``SimConfig.from_config(cfg(host_k=0.0))`` vs ``cfg(host_k=1.0)`` yields a DIFFERENT
     Mexico progression — i.e. the OVERRIDDEN k (not the disk 0.5) flows to the sim. RED
     before the fix (the sim ignored the override -> identical progression).
  2. ``test_dashboard_and_sim_agree_on_host_k``: the sim's single source
     ``host_factor_map(tournament, caller_cfg)`` and the dashboard's per-fixture
     ``host_home_factor(home, away, venue, venue_country, caller_cfg)`` produce the SAME
     ``k`` for the host-home fixture, and it EQUALS the caller's overridden ``host_k`` (not
     the disk default) — dashboard and sim read the identical k for one ``config=`` call.
  3. ``test_distinct_host_k_distinct_cache_key``: two ``host_factors`` maps differing only
     in ``k`` hash to DIFFERENT sim-cache keys, and a host_k=1.0 cached run does NOT
     stale-serve a host_k=0.0 result (no stale serve across host_k). RED before the fix
     (the sim always built the same disk-0.5 map -> same key -> a stale serve).
"""
import copy

import pytest

from wcmodel.config import load_config
from wcmodel.data.tournament import host_factor_map, host_home_factor
from wcmodel.sim.run import SimConfig, simulate

# Reuse the leakage-sim panel scaffolding: a 1-group-of-4 -> Final tournament over the
# ~14-team mutable_store panel (so RateBook(posterior) resolves every fixture). The
# (Mexico, Malta) fixture is dated 2024-06-05 (a FUTURE fixture at cutoff 2024-06-01, so
# it is SIMULATED, not fixed) — the host-home fixture whose k-effect we read.
from tests.sim.test_leakage_sim import _FIXTURE_DATES, _PANEL_TEAMS

# A venue IN MEXICO so host_factor_map / host_home_factor flag the Mexico-home fixture as
# host-home (Mexico is a 2026 host; HOST_COUNTRY_BY_TEAM["Mexico"] == "MX"). Every other
# fixture's venue is None/elsewhere -> neutral, so ONLY Mexico-Malta carries host_factor.
_HOST_VENUE_CITY = "Guadalajara"
_HOST_FIXTURE = ("Mexico", "Malta")           # Mexico is HOME -> host advantage accrues here


def _host_tournament() -> dict:
    """The leakage-sim synthetic tournament PLUS a ``venues`` block (Guadalajara, MX) and a
    ``venue`` on the Mexico-Malta fixture, so that fixture is host-home (host_factor_map
    flags it). All other group fixtures stay neutral (no in-country host venue)."""
    fixtures = [
        {"home": h, "away": a, "date": _FIXTURE_DATES[(h, a)], "round": "Matchday 1",
         "venue": _HOST_VENUE_CITY if (h, a) == _HOST_FIXTURE else None}
        for (h, a) in _FIXTURE_DATES
    ]
    fixtures.append({"match": 104, "home": "1A", "away": "2A", "round": "Final"})
    return {
        "groups": [{"name": "A", "teams": list(_PANEL_TEAMS)}],
        "fixtures": fixtures,
        "venues": [{"city": _HOST_VENUE_CITY, "country": "MX"}],
    }


def _cfg_with_host_k(k: float) -> dict:
    """A full project cfg with ``model.covariates.host_k`` OVERRIDDEN to ``k`` (a deep copy
    so the disk default is untouched). This is the 'caller cfg' the sim+dashboard share."""
    cfg = copy.deepcopy(load_config())
    cfg["model"]["covariates"]["host_k"] = float(k)
    return cfg


def _simconfig(cfg: dict, *, cache_dir=None) -> SimConfig:
    """A SimConfig built through ``from_config(cfg, ...)`` over the host tournament — so it
    CARRIES ``cfg`` (the fix) and ``simulate`` derives host_factors from THAT cfg, not disk.
    Tiny n_sims/max_goals keep the panel sim fast; seed fixed so comparisons are exact."""
    sc = SimConfig.from_config(cfg, tournament=_host_tournament(), n_sims=600, seed=0)
    # from_config doesn't expose max_goals/cache_dir; rebuild with the test's smaller cap
    # (speed) + the optional cache_dir, PRESERVING the carried cfg (the load-bearing field).
    return SimConfig(
        tournament=sc.tournament, n_sims=sc.n_sims, seed=sc.seed, max_goals=8,
        et_scale=sc.et_scale, pen_home_prob=sc.pen_home_prob,
        cache_dir=cache_dir, config=sc.config,
    )


def test_caller_host_k_reaches_the_sim(mutable_store):
    """RED→GREEN: the CALLER's overridden host_k flows to the sim's host_factors.

    Fit once, then ``simulate()`` the SAME posterior under ``host_k=0.0`` (neutral host)
    vs ``host_k=1.0`` (full home advantage on Mexico's host-home group games). With the fix,
    Mexico's host-home fixtures are sampled with ``k*home_adv``, so its forward probability
    DIFFERS between the two runs. Before the fix the sim re-derived the disk 0.5 map for
    BOTH runs -> identical progression (the override was ignored) -> this assertion was RED.
    """
    from wcmodel.model.scoreline import fit

    cutoff = "2024-06-01"                         # Mexico-Malta (2024-06-05) is FUTURE -> simulated
    post = fit(cutoff, mutable_store, backend="advi", draws=80, seed=0, advi_iters=2000)

    res_k0 = simulate(cutoff, post, mutable_store, _simconfig(_cfg_with_host_k(0.0)))
    res_k1 = simulate(cutoff, post, mutable_store, _simconfig(_cfg_with_host_k(1.0)))

    # The progression tables MUST differ — the only changed input is the caller's host_k,
    # which (post-fix) reaches the sim's host_factors for Mexico's host-home fixtures.
    assert not res_k0.progression.equals(res_k1.progression), (
        "caller host_k did NOT reach the sim: progression identical across host_k=0.0 vs "
        "1.0 — the sim is using the disk default, not the caller cfg (the Codex bug)"
    )
    # Direction sanity: more home advantage (k=1) does not LOWER Mexico's group-advance
    # probability vs the neutral k=0 baseline (it samples Mexico's home games stronger).
    adv0 = float(res_k0.progression.loc["Mexico", "advance_from_group"])
    adv1 = float(res_k1.progression.loc["Mexico", "advance_from_group"])
    assert adv1 >= adv0


def test_dashboard_and_sim_agree_on_host_k():
    """The sim's SINGLE SOURCE (host_factor_map over the caller cfg) and the dashboard's
    per-fixture host_home_factor over the SAME caller cfg produce the SAME k for the
    host-home fixture — and it equals the caller's OVERRIDDEN host_k (not the disk 0.5).

    This is the dashboard/sim agreement the bug broke: build.py computes the per-fixture
    forecast at ``host_home_factor(..., cfg)`` while simulate() (pre-fix) used the disk map.
    Post-fix both read ``cfg["model"]["covariates"]["host_k"]``."""
    tournament = _host_tournament()
    venue_country = {v["city"]: v.get("country") for v in tournament["venues"]}
    home, away = _HOST_FIXTURE

    for k in (0.0, 0.7, 1.0):                     # incl. 0.7 != disk 0.5 (the bug's tell)
        cfg = _cfg_with_host_k(k)
        # SIM single source: the map simulate() now builds from the caller cfg.
        sim_map = host_factor_map(tournament, cfg)
        sim_k = sim_map[(home, away)]
        # DASHBOARD per-fixture: exactly the call build.py makes for this fixture.
        dash_k = host_home_factor(home, away, _HOST_VENUE_CITY, venue_country, cfg)
        assert sim_k == dash_k == k, (
            f"dashboard/sim disagree on host_k: sim_map={sim_k}, dashboard={dash_k}, "
            f"caller host_k={k} (must all be equal — both read the caller cfg)"
        )
    # And the disk default is NOT what they read when the caller overrides it: at k=0.7 the
    # shared k is 0.7, never the disk 0.5 (the precise failure mode of the bug).
    cfg07 = _cfg_with_host_k(0.7)
    assert host_factor_map(tournament, cfg07)[(home, away)] == 0.7
    assert load_config()["model"]["covariates"]["host_k"] != 0.7   # 0.7 is a genuine override


def test_distinct_host_k_distinct_cache_key(tmp_path, mutable_store):
    """No stale serve across host_k: two host_factors maps differing only in k hash to
    DIFFERENT sim-cache keys, AND a host_k=1.0 cached run does not return the host_k=0.0
    result. Pre-fix the sim always built the disk-0.5 map -> identical key -> a stale serve.
    """
    from wcmodel.model.scoreline import fit
    from wcmodel.sim.cache import _host_factors_hash

    # (a) the cache-key COMPONENT for the host map is k-sensitive: same fixture, different k
    # -> different hash (the guard that makes a different k MISS instead of stale-serving).
    h0 = _host_factors_hash({_HOST_FIXTURE: 0.0})
    h1 = _host_factors_hash({_HOST_FIXTURE: 1.0})
    assert h0 != h1, "host_factors_hash is not k-sensitive — a different k would stale-serve"

    # (b) END-TO-END through the cache_dir route: run host_k=0.0 (cold miss, persisted),
    # then host_k=1.0. The k=1.0 run MUST recompute (different host map the sim now derives
    # from the caller cfg) and NOT stale-serve the k=0.0 progression. Pre-fix both runs
    # built the disk-0.5 map -> same key -> the k=1.0 run would have served k=0.0's result.
    cutoff = "2024-06-01"
    post = fit(cutoff, mutable_store, backend="advi", draws=80, seed=0, advi_iters=2000)
    cache_dir = tmp_path / "simcache"

    res_k0 = simulate(cutoff, post, mutable_store,
                      _simconfig(_cfg_with_host_k(0.0), cache_dir=cache_dir))
    res_k1 = simulate(cutoff, post, mutable_store,
                      _simconfig(_cfg_with_host_k(1.0), cache_dir=cache_dir))
    assert not res_k0.progression.equals(res_k1.progression), (
        "host_k=1.0 stale-served the host_k=0.0 cached result — the sim cache key does not "
        "reflect the caller's host_k (the Codex bug: same disk map -> same key)"
    )
