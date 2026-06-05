"""Content-addressed walk-forward cache (spec §3).

A full walk-forward run is expensive (many per-cutoff refits) and must NEVER be
stale-served, so it is cached on disk keyed by EVERYTHING that determines the
``Metrics``: the store content-hash, the odds content-hash, the FULL DOF config
block (the 9 pre-registered DOF + the trigger/commission), the cutoff grid, the
``odds_start``, and git (HEAD + a hash of the uncommitted tracked diff — the
Phase-3 ``cached_sim`` discipline). Any change -> a different key -> a MISS. The
key is built from the SAME ``content_key`` the Phase-1/2/3 caches use.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from wcmodel.data.cache import _git_commit, content_key


def _git_diff_hash() -> str:
    """Hash of the uncommitted tracked diff (so an uncommitted code edit also misses).

    Mirrors the Phase-3 ``cache.py`` guard: a brand-new UNTRACKED file is not in
    the diff, so commit or clear the cache when iterating on new files.
    """
    try:
        diff = subprocess.check_output(["git", "diff", "HEAD"], text=True)
    except Exception:
        diff = ""
    return hashlib.sha256(diff.encode()).hexdigest()[:16]


def store_hash(store, cutoff) -> str:
    """Stable hash of the leakage-safe results the run can see (as-of the LAST cutoff).

    Uses the bitemporal ``read`` so it captures exactly the rows the engine may
    consume; a new/revised result before the cutoff changes the hash -> a miss.
    """
    res = store.read("results", cutoff=cutoff)
    blob = pd.util.hash_pandas_object(
        res[["match_id", "date", "home_team", "away_team",
             "home_score", "away_score", "neutral"]].sort_values("match_id"),
        index=False,
    ).values.tobytes()
    return hashlib.sha256(blob).hexdigest()[:16]


def odds_hash(odds_samples: list[dict]) -> str:
    """Stable hash of the odds inputs (the per-event snapshot samples).

    Serialised deterministically (sorted keys) so two identical odds inputs hash
    identically and any price/timestamp change misses.
    """
    blob = json.dumps(odds_samples, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def walkforward_key(*, store, odds_samples, dof_config, cutoff_grid, odds_start,
                    last_cutoff) -> str:
    """The exhaustive content key for one walk-forward run."""
    params = {
        "store_hash": store_hash(store, last_cutoff),
        "odds_hash": odds_hash(odds_samples),
        "dof": dof_config,
        "cutoff_grid": [str(pd.Timestamp(c)) for c in cutoff_grid],
        "odds_start": str(pd.Timestamp(odds_start)),
        "git": _git_commit(),
        "git_diff": _git_diff_hash(),
    }
    return content_key("walkforward", params)


def cached_walkforward(*, key: str, compute, cache_dir) -> tuple[dict, dict]:
    """Serve a walk-forward ``Metrics`` dict from disk or compute+persist it.

    ``compute`` is a zero-arg callable returning the metrics dict. Returns
    ``(metrics, {"cache_hit": bool, "key": key})``. Persists the metrics JSON
    keyed by the content hash.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"walkforward-{key}.json"
    if path.exists():
        return json.loads(path.read_text()), {"cache_hit": True, "key": key}
    metrics = compute()
    path.write_text(json.dumps(metrics, indent=2, default=str))
    return metrics, {"cache_hit": False, "key": key}
