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
    (``{"groups", "knockout_results", "knockout_winners", "match_dates"}``) actually
    passed to the sim. The cutoff is in the key, but the played set is what the cutoff
    RESOLVES to, and the same posterior can be simulated with different conditioning;
    hashing the actual played content makes a hit impossible to serve for the wrong
    conditioning. ``knockout_winners`` (the recorded shootout winner) is in the payload
    because D3 made it DETERMINE a level pinned KO's champion (Phase-5 T7 stale-serve
    fix): two played maps differing only by the recorded winner MUST get different keys.
  * ``git`` — the HEAD commit of the code that builds the bracket / runs the sim /
    aggregates markets, PLUS ``git_worktree`` (a hash of the uncommitted tracked diff,
    or ``"clean"``). See the GIT-KEY POLICY below.

GIT-KEY POLICY (Codex T7 finding 2). Cache validity assumes COMMITTED code. The shared
``content_key`` git component (``_git_commit``) is the HEAD COMMIT ONLY — a project-wide
Phase-1/2 convention we do NOT change here. On its own that cannot distinguish a clean
tree from one with uncommitted edits to the sim/aggregation code, so a HIT during active
development could serve a result computed by SINCE-EDITED code. To close that locally
WITHOUT touching the shared helper, the sim key ALSO includes ``_git_worktree_hash()`` (a
hash of ``git diff HEAD``), so any uncommitted change to TRACKED sim code yields a
different key -> a MISS. Caveat: a brand-new UNTRACKED file is not in ``git diff HEAD``;
when iterating on sim code prefer to commit, or clear the cache, rather than rely on the
dirty-flag for untracked additions.

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
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.data.cache import _git_commit, content_key
from wcmodel.sim.tournament import SimResult, simulate_tournament


def _git_worktree_hash() -> str:
    """Short digest of the UNCOMMITTED working-tree state (tracked files), or
    ``"clean"`` / ``"nogit"``.

    GIT-KEY POLICY (Codex T7 finding 2). The shared ``content_key`` git component
    (``wcmodel.data.cache._git_commit``) is the HEAD COMMIT ONLY, so on its own a
    cache key cannot tell a committed tree from a working tree with uncommitted edits
    to the sim/aggregation code — during active development a ``cached_sim`` HIT could
    serve a result computed by SINCE-EDITED code. ``_git_commit`` is a project-wide
    convention shared by the Phase-1/2 caches; we do NOT change it. Instead this LOCAL
    sim-cache helper folds a hash of ``git diff HEAD`` (the full uncommitted tracked
    diff) into the sim key, so any uncommitted change to code the sim depends on yields
    a DIFFERENT key -> a MISS (never a stale serve from since-edited code). A clean tree
    hashes to the literal ``"clean"`` so a committed run's key is stable; ``"nogit"`` if
    git is unavailable. NB: this captures TRACKED edits (``git diff HEAD``); a brand-new
    UNTRACKED, unstaged file is not in the diff — commit/clear the cache when iterating.
    """
    try:
        diff = subprocess.check_output(
            ["git", "diff", "HEAD"], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        return "nogit"
    if not diff:
        return "clean"
    return hashlib.sha256(diff.encode()).hexdigest()[:16]


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
    # Review-v2 Fix 3 (Codex pass-4): ``RateBook`` reads
    # ``posterior._cfg["neutral_home_adv_fraction"]`` to build every neutral
    # fixture's rates, so it is output-determining for the sim and MUST be in
    # the key — two posteriors with identical draws but a different fraction
    # previously shared a hash, letting ``cached_sim`` stale-serve across a
    # config change of that tunable. It is the ONLY ``_cfg`` field the sim
    # sampling path consumes (widening acts on prediction grids, not RateBook).
    h.update(repr(float(posterior._cfg["neutral_home_adv_fraction"])).encode())
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
    -> sorted lists; tuple feeders -> lists) so the digest is deterministic. A
    different group composition / fixture pairing / feeder graph / round map -> a
    different blob -> a different hash -> a cache miss.

    HASH <-> SIM CONTRACT (Codex T7 stale-serve guard) — the two MUST agree on the
    canonical form, in BOTH directions, or a cache hit could serve a seeded result the
    live sim would not produce:

      * GROUP KEYS are canonicalized (``sorted(...items())`` on ``groups`` and
        ``group_fixtures``), so the key is INDEPENDENT of group dict-insertion order.
        ``simulate_one`` therefore walks groups in the SAME ``sorted(group_fixtures)``
        order (it consumes the per-sim RNG group-by-group), so two content-identical
        brackets whose groups are inserted in different order share a key AND produce
        the SAME seeded ``SimResult`` (proven by ``test_simresult_invariant_to_group_
        insertion_order``). Without that, sharing a key would be a stale serve.
      * WITHIN-GROUP FIXTURE ORDER is PRESERVED (the inner ``[list(p) for p in
        fixtures]`` is NOT sorted), because the sim samples each group's ``fixtures``
        list in list order and consumes RNG in that order — so within-group order IS
        result-affecting content. Preserving it here means a within-group reorder is a
        DIFFERENT blob -> a different key -> a miss (proven by
        ``test_simresult_invariant_to_within_group_fixture_order``, which asserts the
        sim is NOT invariant to such a reorder). Sorting the inner lists would
        reintroduce the same stale-serve bug one level down.
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

    D3 STALE-SERVE GUARD (Phase-5 T7, Codex finding). The D3 fix made
    ``knockout_winners`` (``{(home, away, date): winner}``, the recorded shootout
    winner) DETERMINE the champion of a level (penalty-decided) pinned KO in
    ``simulate_one`` — so it is output-affecting content and MUST be in the key.
    Omitting it let two played maps differing ONLY by the recorded shootout winner
    share a key, and the cached path stale-served the WRONG champion. It is folded in
    the SAME canonical, key-sorted form as ``knockout_results`` (``sorted`` on
    ``(repr(key), value)``), so the digest is insertion-order-independent — the same
    Phase-3 lesson (a dict hashed in insertion order is non-reproducible) — and a
    different recorded winner yields a different blob -> a different key -> a MISS.
    """
    if not played:
        return "none"
    canon = {
        "groups": sorted((repr(k), list(v)) for k, v in played.get("groups", {}).items()),
        "knockout_results": sorted(
            (repr(k), list(v)) for k, v in played.get("knockout_results", {}).items()
        ),
        "knockout_winners": sorted(
            (repr(k), str(w)) for k, w in played.get("knockout_winners", {}).items()
        ),
        "match_dates": sorted(
            (str(m), str(d)) for m, d in played.get("match_dates", {}).items()
        ),
    }
    blob = json.dumps(canon, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _host_factors_hash(host_factors) -> str:
    """Stable 16-hex hash of the T5 host-advantage map ``{(home, away): k}`` (or ``"none"``).

    STALE-SERVE GUARD: ``host_factors`` is OUTPUT-AFFECTING content — a host's home group
    game is sampled with ``k*home_adv`` instead of neutral, so two runs differing only in
    the host map (or in ``k``) must NOT share a cache key. The tuple keys are not
    JSON-native, so each entry is canonicalized to ``(repr(key), k)`` and key-sorted (the
    same insertion-order-independent form as ``_played_hash``), so a different host set or
    a different ``k`` yields a different digest -> a different key -> a MISS. ``None``/empty
    (the neutral default) hashes to ``"none"``, stable and distinct from any host map."""
    if not host_factors:
        return "none"
    canon = sorted((repr(k), float(v)) for k, v in host_factors.items())
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
               pen_home_prob, cache_dir, played=None, host_factors=None):
    """Run ``simulate_tournament`` through the content-addressed sim cache.

    Returns ``(SimResult, {"cache_hit": bool, "key": str})``. On a HIT the
    ``SimResult`` is rebuilt from the persisted parquet tables + meta JSON with NO
    re-simulation (the load-bearing property: a hit must not recompute); on a MISS
    we simulate, persist, and return ``cache_hit=False``.

    The key (see module docstring) is the ACTUAL posterior content-hash + bracket
    structure-hash + cutoff + n_sims + seed + max_goals + et_scale + pen_home_prob +
    the played-conditioning hash + git (HEAD commit + uncommitted-tracked-diff hash, per
    the GIT-KEY POLICY in the module docstring). Any change -> a different key -> a miss
    (never a stale serve). Cache validity assumes COMMITTED code; the ``git_worktree``
    component makes uncommitted TRACKED sim edits miss, but a new UNTRACKED file is not in
    ``git diff HEAD`` — commit or clear the cache when iterating on sim code."""
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
        # T5 host advantage is output-affecting (a host's home game samples with k*home_adv)
        # -> in the key so a different host map / k MISSES instead of stale-serving neutral.
        "host_factors_hash": _host_factors_hash(host_factors),
        "git": _git_commit(),
        # HEAD commit alone can't see uncommitted edits to the sim/aggregation code, so a
        # dirty working tree would otherwise HIT a result computed by since-edited code.
        # Fold a hash of the uncommitted tracked diff in -> uncommitted sim changes MISS.
        # (Sim-cache-local; the shared content_key/_git_commit convention is untouched.)
        "git_worktree": _git_worktree_hash(),
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
        host_factors=host_factors,
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
