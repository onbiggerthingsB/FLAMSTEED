"""Phase-3 T7 — content-addressed SIM cache (``wcmodel.sim.cache.cached_sim``).

A full-posterior MC run is expensive (N sims x full bracket), so a run is cached
on disk and reused ONLY when EVERY input that determines the output is identical.
The key is CONTENT-ADDRESSED (reusing ``wcmodel.data.cache.content_key``): the
ACTUAL posterior content-hash (parameter values + teams + likelihood), the ACTUAL
bracket-structure hash (groups + fixtures + feeders + rounds), the cutoff, n_sims,
seed, max_goals, et_scale, pen_home_prob, the played-conditioning hash, and git.
A change to ANY component -> a different key -> a MISS (never a stale serve — the
P2-T8 lesson: a stale serve returning a cached result for the WRONG
cutoff/posterior/bracket is THE bug to avoid).

These tests prove:
  * cold = MISS (computes), warm = HIT (no recompute — asserted via a SENTINEL:
    ``simulate_tournament`` is monkeypatched to raise on a hit);
  * changing EACH key component (cutoff, seed, n_sims, max_goals, et_scale,
    pen_home_prob, a perturbed posterior, a different bracket) MISSES;
  * a HIT returns results BYTE-IDENTICAL to the cold compute.

Uses a tiny stub RateBook-shaped posterior + ``tiny_bracket()`` so no ADVI is
needed — these run in milliseconds.
"""
import numpy as np
import xarray as xr

import wcmodel.sim.cache as sim_cache
from wcmodel.model.posterior import Posterior
from wcmodel.sim.cache import cached_sim

from tests.sim.conftest import tiny_bracket

_TEAMS = ["Brazil", "Argentina", "Croatia", "France"]


def _toy_posterior(seed=0, *, teams=_TEAMS, likelihood="dixon_coles"):
    """A minimal but REAL ``Posterior`` over the tiny-bracket teams with random
    (seeded) parameter draws — enough for ``RateBook`` to resolve every fixture.
    No ADVI: we hand-build the ``idata.posterior`` xarray group directly."""
    rng = np.random.default_rng(seed)
    n_teams, n_chain, n_draw = len(teams), 1, 8
    ds = xr.Dataset(
        {
            "att": (("chain", "draw", "team"),
                    rng.normal(0, 0.3, (n_chain, n_draw, n_teams))),
            "def": (("chain", "draw", "team"),
                    rng.normal(0, 0.3, (n_chain, n_draw, n_teams))),
            "mu": (("chain", "draw"), rng.normal(0.1, 0.05, (n_chain, n_draw))),
            "home_adv": (("chain", "draw"), rng.normal(0.2, 0.05, (n_chain, n_draw))),
            "rho": (("chain", "draw"), rng.normal(-0.05, 0.01, (n_chain, n_draw))),
        },
        coords={"team": list(teams)},
    )
    idata = xr.DataTree.from_dict({"posterior": ds})
    return Posterior(idata, teams, likelihood, provisional_teams=set())


def _base_kwargs(tmp_path, **over):
    kw = dict(
        cutoff="2024-06-01",
        posterior=_toy_posterior(),
        bracket=tiny_bracket(),
        n_sims=300,
        seed=0,
        max_goals=8,
        et_scale=0.3333,
        pen_home_prob=0.5,
        cache_dir=tmp_path,
        played=None,
    )
    kw.update(over)
    return kw


# ---------------------------------------------------------------------------
# Cold = miss, warm = hit (the SENTINEL proves a hit does NOT recompute).
# ---------------------------------------------------------------------------
def test_cold_miss_warm_hit(tmp_path):
    res1, m1 = cached_sim(**_base_kwargs(tmp_path))
    res2, m2 = cached_sim(**_base_kwargs(tmp_path))
    assert m1["cache_hit"] is False, "first call must MISS (cold)"
    assert m2["cache_hit"] is True, "second call must HIT (warm)"
    assert m1["key"] == m2["key"]


def test_hit_does_not_recompute(tmp_path, monkeypatch):
    """SENTINEL: after a cold miss populates the cache, a warm call must NOT call
    ``simulate_tournament`` — we monkeypatch it to raise, so any recompute fails
    loudly. A clean hit proves the load path is real (the load-bearing property)."""
    cached_sim(**_base_kwargs(tmp_path))             # populate the cache

    def _boom(*a, **k):
        raise AssertionError("simulate_tournament was called on a cache HIT")

    monkeypatch.setattr(sim_cache, "simulate_tournament", _boom)
    res, meta = cached_sim(**_base_kwargs(tmp_path))  # must hit -> no recompute
    assert meta["cache_hit"] is True
    # And it still returns a usable SimResult (loaded from disk, not recomputed).
    assert "champion" in res.progression.columns


def test_hit_results_are_byte_identical(tmp_path):
    """A HIT reproduces the cold-compute output EXACTLY: progression, se,
    random_tail_rate, and n_sims all match (loaded from the persisted tables)."""
    cold, _ = cached_sim(**_base_kwargs(tmp_path))
    warm, meta = cached_sim(**_base_kwargs(tmp_path))
    assert meta["cache_hit"] is True
    assert warm.progression.equals(cold.progression)
    assert warm.se.equals(cold.se)
    assert warm.random_tail_rate == cold.random_tail_rate
    assert warm.n_sims == cold.n_sims
    # Column order/index preserved on the round-trip.
    assert list(warm.progression.columns) == list(cold.progression.columns)
    assert list(warm.progression.index) == list(cold.progression.index)


# ---------------------------------------------------------------------------
# Changing EACH key component MISSES (never a stale serve).
# ---------------------------------------------------------------------------
def test_different_cutoff_misses(tmp_path):
    _, m1 = cached_sim(**_base_kwargs(tmp_path))
    _, m2 = cached_sim(**_base_kwargs(tmp_path, cutoff="2024-07-01"))
    assert m1["cache_hit"] is False and m2["cache_hit"] is False
    assert m1["key"] != m2["key"]


def test_different_seed_misses(tmp_path):
    _, m1 = cached_sim(**_base_kwargs(tmp_path))
    _, m2 = cached_sim(**_base_kwargs(tmp_path, seed=1))
    assert m2["cache_hit"] is False and m1["key"] != m2["key"]


def test_different_n_sims_misses(tmp_path):
    _, m1 = cached_sim(**_base_kwargs(tmp_path))
    _, m2 = cached_sim(**_base_kwargs(tmp_path, n_sims=301))
    assert m2["cache_hit"] is False and m1["key"] != m2["key"]


def test_different_max_goals_misses(tmp_path):
    _, m1 = cached_sim(**_base_kwargs(tmp_path))
    _, m2 = cached_sim(**_base_kwargs(tmp_path, max_goals=9))
    assert m2["cache_hit"] is False and m1["key"] != m2["key"]


def test_different_et_scale_misses(tmp_path):
    _, m1 = cached_sim(**_base_kwargs(tmp_path))
    _, m2 = cached_sim(**_base_kwargs(tmp_path, et_scale=0.4))
    assert m2["cache_hit"] is False and m1["key"] != m2["key"]


def test_different_pen_home_prob_misses(tmp_path):
    _, m1 = cached_sim(**_base_kwargs(tmp_path))
    _, m2 = cached_sim(**_base_kwargs(tmp_path, pen_home_prob=0.6))
    assert m2["cache_hit"] is False and m1["key"] != m2["key"]


def test_perturbed_posterior_misses(tmp_path):
    """A DIFFERENT posterior (different parameter draws) MUST miss — the key is
    keyed on the actual posterior CONTENT, not an identity/config proxy. This is
    the P2-T8 stale-serve guard at the sim layer."""
    _, m1 = cached_sim(**_base_kwargs(tmp_path))
    _, m2 = cached_sim(**_base_kwargs(tmp_path, posterior=_toy_posterior(seed=99)))
    assert m2["cache_hit"] is False and m1["key"] != m2["key"]


def test_different_bracket_misses(tmp_path):
    """A DIFFERENT bracket structure MUST miss. We reorder the group so the team
    list (and hence the bracket content) differs — the bracket hash must change."""
    from wcmodel.sim.bracket import build_bracket

    a, b, c, d = _TEAMS
    # Same 4 teams but a DIFFERENT group ordering + fixture pairing -> a genuinely
    # different bracket structure (different rank slots feed the Final).
    fixtures = [(b, a), (d, c), (b, c), (a, d), (b, d), (a, c)]
    alt_tour = {
        "groups": [{"name": "A", "teams": [b, a, d, c]}],
        "fixtures": [
            *[{"home": h, "away": aw, "round": "Matchday 1"} for h, aw in fixtures],
            {"match": 104, "home": "1A", "away": "2A", "round": "Final"},
        ],
    }
    alt_bracket = build_bracket(alt_tour)
    _, m1 = cached_sim(**_base_kwargs(tmp_path))
    _, m2 = cached_sim(**_base_kwargs(tmp_path, bracket=alt_bracket))
    assert m2["cache_hit"] is False and m1["key"] != m2["key"]


def test_different_played_misses(tmp_path):
    """A different per-cutoff conditioning set (played) changes the output, so it
    MUST be in the key -> a miss. (Two distinct cutoffs can share n_sims/seed/etc.
    but condition on different played fixtures; the played hash distinguishes them
    so a hit can never serve the wrong conditioning.)"""
    played = {
        "groups": {("Brazil", "Argentina"): (2, 0)},
        "knockout_results": {},
        "match_dates": {},
    }
    _, m1 = cached_sim(**_base_kwargs(tmp_path))
    _, m2 = cached_sim(**_base_kwargs(tmp_path, played=played))
    assert m2["cache_hit"] is False and m1["key"] != m2["key"]


def test_perturbed_posterior_changes_results(tmp_path):
    """Sanity teeth for the stale-serve guard: a perturbed posterior doesn't just
    change the KEY, it changes the RESULTS — so serving the cached result for the
    wrong posterior would be a real, observable corruption (proving the miss matters)."""
    base, _ = cached_sim(**_base_kwargs(tmp_path))
    other, _ = cached_sim(**_base_kwargs(tmp_path, posterior=_toy_posterior(seed=99)))
    assert not base.progression.equals(other.progression), (
        "perturbed posterior produced identical progression — the cache-miss "
        "guard would be vacuous"
    )


# ---------------------------------------------------------------------------
# Integration: simulate(...) routes through the cache when SimConfig.cache_dir is set.
# (Fast: a synthetic 1-group-of-4 tournament over the toy-posterior teams, no ADVI —
# the store is read only for the played-as-of-cutoff conditioning, which is empty here
# because every group fixture is dated >= the cutoff or absent from the store.)
# ---------------------------------------------------------------------------
def _synthetic_tournament():
    a, b, c, d = _TEAMS
    pairs = [(a, b), (c, d), (a, c), (b, d), (a, d), (b, c)]
    return {
        "groups": [{"name": "A", "teams": list(_TEAMS)}],
        "fixtures": [
            *[{"home": h, "away": aw, "date": "2030-01-01", "round": "Matchday 1"}
              for h, aw in pairs],
            {"match": 104, "home": "1A", "away": "2A", "round": "Final"},
        ],
    }


def test_simulate_run_path_uses_cache(tmp_path, small_store, monkeypatch):
    """simulate(...) with SimConfig.cache_dir set MISSES cold then HITS warm, and the
    warm run returns results identical to the cold one — and a SENTINEL proves the warm
    run does NOT re-simulate (the run-layer wiring honours the cache)."""
    from wcmodel.sim.run import SimConfig, simulate

    cfg = SimConfig(
        tournament=_synthetic_tournament(),
        n_sims=200, seed=0, max_goals=8, et_scale=0.3333, pen_home_prob=0.5,
        cache_dir=tmp_path,
    )
    post = _toy_posterior()
    cold = simulate("2024-06-01", post, small_store, cfg)   # cold: computes + persists

    # Warm call must hit -> simulate_tournament (imported INTO the cache module) must
    # not be called. Patch it on the cache module to raise if a recompute happens.
    def _boom(*a, **k):
        raise AssertionError("simulate_tournament called on a run-path cache HIT")

    monkeypatch.setattr(sim_cache, "simulate_tournament", _boom)
    warm = simulate("2024-06-01", post, small_store, cfg)   # warm: loads from disk
    assert warm.progression.equals(cold.progression)
    assert warm.se.equals(cold.se)
    assert warm.n_sims == cold.n_sims


def test_simulate_run_path_uncached_by_default(tmp_path, small_store):
    """Default (no cache_dir) writes NOTHING to disk — the uncached path is unchanged
    by T7 (no accidental cache coupling for callers that did not opt in)."""
    from wcmodel.sim.run import SimConfig, simulate

    cfg = SimConfig(
        tournament=_synthetic_tournament(),
        n_sims=120, seed=0, max_goals=8, et_scale=0.3333, pen_home_prob=0.5,
    )
    simulate("2024-06-01", _toy_posterior(), small_store, cfg)
    assert list(tmp_path.glob("sim-*")) == [], "uncached run must not write cache files"
