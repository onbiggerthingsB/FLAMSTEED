"""Power/MDE machinery for the OA prereg gate (spec OA-5, finding 7).

Block bootstrap: blocks are (pool, matchday) groups, resampled with
replacement WITHIN pool strata — matches within a matchday share shocks and
must move together (finding 8). support = fraction of bootstrap means < 0.
"""
from __future__ import annotations

import numpy as np


def _blocks(pool: np.ndarray, day: np.ndarray) -> dict:
    """Map each pool -> list of index-arrays, one per (pool, day) block."""
    out: dict = {}
    for p in np.unique(pool):
        m = pool == p
        idx = np.flatnonzero(m)
        days = day[m]
        out[p] = [idx[days == d] for d in np.unique(days)]
    return out


def block_bootstrap_support(diffs, pool, day, *, n_boot: int, seed: int) -> float:
    diffs = np.asarray(diffs, dtype=float)
    pool = np.asarray(pool)
    day = np.asarray(day)
    rng = np.random.default_rng(seed)
    blocks = _blocks(pool, day)
    means = np.empty(n_boot)
    for b in range(n_boot):
        take = []
        for p, blist in blocks.items():
            k = len(blist)
            for j in rng.integers(0, k, size=k):
                take.append(blist[j])
        means[b] = diffs[np.concatenate(take)].mean()
    return float((means < 0.0).mean())


def simulate_power(noise, pool, day, *, delta: float, floor: float,
                   support_req: float, n_sims: int, n_boot: int,
                   seed: int) -> float:
    """P(gate passes | true per-match effect = -delta), noise resampled from
    the centered empirical paired-difference distribution."""
    noise = np.asarray(noise, dtype=float)
    noise = noise - noise.mean()
    rng = np.random.default_rng(seed)
    n = len(noise)
    passes = 0
    for s in range(n_sims):
        d = -delta + rng.choice(noise, size=n, replace=True)
        if d.mean() > -floor:
            continue
        sup = block_bootstrap_support(d, pool, day, n_boot=n_boot,
                                      seed=seed * 100_003 + s)
        if sup >= support_req:
            passes += 1
    return passes / n_sims
