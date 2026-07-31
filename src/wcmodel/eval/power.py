"""Power/MDE machinery for the OA prereg gate (spec OA-5, finding 7).

Block bootstrap: blocks are (pool, matchday) groups, resampled with
replacement WITHIN pool strata — matches within a matchday share shocks and
must move together (finding 8). support = fraction of bootstrap means < 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


def _check_lengths(diffs, pool, day) -> None:
    """pool/day index the same panel as diffs; a mismatch would silently drop
    or double-count observations inside every bootstrap mean."""
    if not (len(diffs) == len(pool) == len(day)):
        raise ValueError(f"length mismatch: values={len(diffs)}, "
                         f"pool={len(pool)}, day={len(day)}")


def _blocks(pool: np.ndarray, day: np.ndarray) -> dict:
    """Map each pool -> list of index-arrays, one per (pool, day) block."""
    out: dict = {}
    for p in np.unique(pool):
        m = pool == p
        idx = np.flatnonzero(m)
        days = day[m]
        out[p] = [idx[days == d] for d in np.unique(days)]
    return out


def block_bootstrap_support(diffs, pool, day, *, n_boot: int,
                            seed: int | np.random.SeedSequence) -> float:
    diffs = np.asarray(diffs, dtype=float)
    pool = np.asarray(pool)
    day = np.asarray(day)
    _check_lengths(diffs, pool, day)
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


@dataclass(frozen=True)
class PowerDetail:
    """power plus the diagnostics that say WHICH half of the two-part gate is
    binding: floor_pass counts sims clearing mean <= -floor, support_reject
    counts how many of those the support requirement then rejected, and
    min_support is the smallest support among floor-passers (nan if none)."""
    power: float
    floor_pass: int
    support_reject: int
    min_support: float


def simulate_power_detail(noise, pool, day, *, delta: float, floor: float,
                          support_req: float, n_sims: int, n_boot: int,
                          seed: int) -> PowerDetail:
    """P(gate passes | true per-match effect = -delta), noise resampled from
    the centered empirical paired-difference distribution."""
    noise = np.asarray(noise, dtype=float)
    _check_lengths(noise, pool, day)
    noise = noise - noise.mean()
    rng = np.random.default_rng(seed)
    # spawned children are independent of default_rng(seed) itself, so a
    # simulation's bootstrap never reuses the stream that drew its own panel
    boot_seeds = np.random.SeedSequence(seed).spawn(n_sims)
    n = len(noise)
    floor_pass = 0
    passes = 0
    sups = []
    for s in range(n_sims):
        d = -delta + rng.choice(noise, size=n, replace=True)
        if d.mean() > -floor:
            continue
        floor_pass += 1
        sup = block_bootstrap_support(d, pool, day, n_boot=n_boot,
                                      seed=boot_seeds[s])
        sups.append(sup)
        if sup >= support_req:
            passes += 1
    return PowerDetail(power=passes / n_sims, floor_pass=floor_pass,
                       support_reject=floor_pass - passes,
                       min_support=float(min(sups)) if sups else float("nan"))


def simulate_power(noise, pool, day, *, delta: float, floor: float,
                   support_req: float, n_sims: int, n_boot: int,
                   seed: int) -> float:
    return simulate_power_detail(noise, pool, day, delta=delta, floor=floor,
                                 support_req=support_req, n_sims=n_sims,
                                 n_boot=n_boot, seed=seed).power


def mde(rows: Sequence[tuple[float, float]], *,
        target: float = 0.80) -> float | None:
    """Smallest delta whose simulated power reaches target; None if none does."""
    for d, p in sorted(rows):
        if p >= target:
            return d
    return None
