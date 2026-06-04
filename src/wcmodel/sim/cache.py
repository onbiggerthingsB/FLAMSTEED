"""Content-addressed Monte-Carlo SIM cache (Phase-3 T7).

A full-posterior MC run (``simulate_tournament``: ``n_sims`` x the full bracket,
drawing a posterior sample + sampling every fixture per sim) is expensive, and a
walk-forward backtest re-runs it at many cutoffs, so each run is cached on disk.

The cache is CONTENT-ADDRESSED: the key is a hash of EVERYTHING that determines
the output progression/SE tables, computed via ``wcmodel.data.cache.content_key``
(the same helper Phase-1/2 use). A change to ANY component -> a different key ->
a MISS. The key therefore NEVER serves a stale result.

LESSON FROM P2-T8 (a real cross-model catch, applied here). A stale serve — the
cache returning a result computed for the WRONG cutoff / posterior / bracket — is
THE bug to avoid, and it comes from an INCOMPLETE key. So the key is keyed on the
ACTUAL CONTENT that drove the run, never on a config field that can drift:

  * ``posterior_hash`` — a hash of the posterior's actual parameter VALUES (the
    ``idata.posterior`` group: ``att/def/mu/home_adv`` (+ ``rho`` or ``log_lambda3``),
    i.e. EXACTLY what ``RateBook`` reads to drive the sim) PLUS ``teams`` (the team
    index ``RateBook`` builds) and ``likelihood`` (DC vs bivariate-Poisson — a
    different sampler). A perturbed posterior -> a different hash -> a miss. (NOT a
    posterior identity/object id, NOT a config proxy — the values themselves.)
  * ``bracket_hash`` — a deterministic hash of the bracket STRUCTURE (groups,
    group_fixtures, third_place_slots, knockout_feeders, match_round). A different
    bracket -> a different hash -> a miss.
  * ``cutoff`` — which fixtures are played-as-of-cutoff (i.e. which conditioning).
  * ``n_sims, seed`` — the seeded MC sample (same seed -> bit-identical run).
  * ``max_goals, et_scale, pen_home_prob`` — the sim knobs that shape the per-sim
    scoreline / extra-time / penalty draws (all change the output distribution; the
    plan lists et_scale + pen_home_prob explicitly, and max_goals is included for the
    same stale-serve reason — it changes the sampled grid, so it MUST be in the key).
  * ``played_hash`` — a deterministic hash of the per-cutoff conditioning map
    (``{"groups", "knockout_results", "match_dates"}``) actually passed to the sim.
    The cutoff is in the key, but the played set is what the cutoff RESOLVES to, and
    the same posterior can be simulated with different conditioning; hashing the
    actual played content makes a hit impossible to serve for the wrong conditioning.
  * ``git`` — the code that builds the bracket / runs the sim / aggregates markets.

On a MISS we ``simulate_tournament`` and persist three files keyed by the content
hash (so a HIT reconstructs the full ``SimResult`` from disk WITHOUT re-simulating):

  * ``sim-<key>.progression.parquet`` — the team-indexed progression table.
  * ``sim-<key>.se.parquet``          — the team-indexed SE table.
  * ``sim-<key>.meta.json``           — the full keyed params PLUS the scalars
    (``random_tail_rate``, ``n_sims``) and the column/index ordering, so the loaded
    DataFrames are BYTE-IDENTICAL (``.equals``) to the cold compute.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.data.cache import _git_commit, content_key
from wcmodel.sim.tournament import SimResult, simulate_tournament


def _posterior_hash(posterior) -> str:
    """Stable 16-hex hash of the posterior CONTENT that drives the sim.

    Hashes the actual parameter VALUES ``RateBook`` reads — every variable in the
    ``idata.posterior`` group (``att/def/mu/home_adv`` + ``rho`` or ``log_lambda3``)
    — plus the team index and likelihood. Variables are folded in NAME-sorted order
    with their name + shape + raw bytes, so the digest is deterministic and a change
    to any draw (a perturbed posterior) yields a different hash -> a cache miss.
    """
    h = hashlib.sha256()
    h.update(repr(list(posterior.teams)).encode())
    h.update(str(posterior.likelihood).encode())
    post = posterior.idata.posterior
    for name in sorted(post.data_vars):
        arr = np.ascontiguousarray(post[name].values)
        h.update(name.encode())
        h.update(str(arr.shape).encode())
        # float64 raw bytes are exact; a single changed draw flips the digest.
        h.update(arr.tobytes())
    return h.hexdigest()[:16]


def _bracket_hash(bracket) -> str:
    """Stable 16-hex hash of the bracket STRUCTURE.

    Serializes every structural field to a canonical, sorted JSON blob (frozensets
    -> sorted lists; tuple feeders -> lists) so the digest is order-independent and
    deterministic. A different group composition / fixture pairing / feeder graph /
    round map -> a different blob -> a different hash -> a cache miss.
    """
    payload = {
        "groups": {g: list(teams) for g, teams in sorted(bracket.groups.items())},
        "group_fixtures": {
            g: [list(p) for p in fixtures]
            for g, fixtures in sorted(bracket.group_fixtures.items())
        },
        "third_place_slots": {
            str(m): sorted(slots) for m, slots in sorted(bracket.third_place_slots.items())
        },
        "knockout_feeders": {
            str(m): list(refs) for m, refs in sorted(bracket.knockout_feeders.items())
        },
        "match_round": {str(m): r for m, r in sorted(bracket.match_round.items())},
    }
    blob = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _played_hash(played) -> str:
    """Stable 16-hex hash of the per-cutoff conditioning map (or ``"none"``).

    The played dict keys are tuples (``(home, away)`` / ``(home, away, date)``) and
    contain ``pd.Timestamp`` values, neither JSON-native, so we canonicalize every
    entry to sorted ``(repr(key), value)`` lists before hashing. ``played=None`` (the
    T5 all-simulated default) hashes to the literal ``"none"`` so it is stable and
    distinct from any non-empty conditioning.
    """
    if not played:
        return "none"
    canon = {
        "groups": sorted((repr(k), list(v)) for k, v in played.get("groups", {}).items()),
        "knockout_results": sorted(
            (repr(k), list(v)) for k, v in played.get("knockout_results", {}).items()
        ),
        "match_dates": sorted(
            (str(m), str(d)) for m, d in played.get("match_dates", {}).items()
        ),
    }
    blob = json.dumps(canon, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _read_table(path: Path, columns: list[str]) -> pd.DataFrame:
    """Reload a persisted progression/SE table BYTE-IDENTICAL to the cold compute.

    The table was written with a ``team`` column (reset index); restore it as the
    named index and re-impose the canonical column order so the reconstructed frame
    ``.equals`` the original (which checks index name, column order, and dtype)."""
    df = pd.read_parquet(path)
    df = df.set_index("team")
    df.index.name = "team"
    return df[columns]


def cached_sim(*, cutoff, posterior, bracket, n_sims, seed, max_goals, et_scale,
               pen_home_prob, cache_dir, played=None):
    """Run ``simulate_tournament`` through the content-addressed sim cache.

    Returns ``(SimResult, {"cache_hit": bool, "key": str})``. On a HIT the
    ``SimResult`` is rebuilt from the persisted parquet tables + meta JSON with NO
    re-simulation (the load-bearing property: a hit must not recompute); on a MISS
    we simulate, persist, and return ``cache_hit=False``.

    The key (see module docstring) is the ACTUAL posterior content-hash + bracket
    structure-hash + cutoff + n_sims + seed + max_goals + et_scale + pen_home_prob +
    the played-conditioning hash + git. Any change -> a different key -> a miss
    (never a stale serve)."""
    params = {
        "cutoff": str(pd.Timestamp(cutoff)),
        "posterior_hash": _posterior_hash(posterior),
        "bracket_hash": _bracket_hash(bracket),
        "n_sims": int(n_sims),
        "seed": int(seed),
        "max_goals": int(max_goals),
        "et_scale": float(et_scale),
        "pen_home_prob": float(pen_home_prob),
        "played_hash": _played_hash(played),
        "git": _git_commit(),
    }
    key = content_key("sim", params)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prog_path = cache_dir / f"sim-{key}.progression.parquet"
    se_path = cache_dir / f"sim-{key}.se.parquet"
    meta_path = cache_dir / f"sim-{key}.meta.json"

    if prog_path.exists() and se_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        cols = meta["columns"]
        res = SimResult(
            progression=_read_table(prog_path, cols),
            se=_read_table(se_path, cols),
            random_tail_rate=meta["random_tail_rate"],
            n_sims=meta["n_sims"],
        )
        return res, {"cache_hit": True, "key": key}

    res = simulate_tournament(
        posterior, bracket=bracket, n_sims=n_sims, seed=seed, max_goals=max_goals,
        et_scale=et_scale, pen_home_prob=pen_home_prob, played=played,
    )
    # Persist the tables with the team index as a column (reset_index) so the parquet
    # round-trip is lossless and the reload re-imposes the exact index + column order.
    res.progression.reset_index().to_parquet(prog_path, index=False)
    res.se.reset_index().to_parquet(se_path, index=False)
    meta_path.write_text(json.dumps(
        {**params, "key": key, "columns": list(res.progression.columns),
         "random_tail_rate": res.random_tail_rate, "n_sims": res.n_sims},
        indent=2, default=str,
    ))
    return res, {"cache_hit": False, "key": key}
