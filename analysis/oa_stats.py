#!/usr/bin/env python
"""Two-group block bootstrap for the post-hoc dev-slate tests.

This is the SECOND repair of this file. The first attempt claimed to fix a
fixture-level bootstrap and did not actually implement the design it claimed;
a Codex verification pass caught three things, all fixed here.

1. JOINT, NOT INDEPENDENT, BLOCK RESAMPLING.
   The previous version resampled the two groups independently even when
   their rows shared a ``(pool, matchday)`` block — 7 such blocks in H1, 21
   in H2. Fixtures on the same matchday share a fitted posterior, a market
   state and a day; resampling the groups apart destroys that common shock
   and the cross-group covariance, so the difference of means no longer has
   the sampling law the report claims. Blocks are now drawn WHOLE, carrying
   whichever groups' rows they contain.

2. STRATIFIED WITHIN POOL.
   ``_blocks`` keyed on ``(pool, date)`` and then threw the keys away,
   pooling every block into one urn. The repository's own primitive
   (``wcmodel.eval.power.block_bootstrap_support``) resamples within pool
   strata. Now so does this.

3. REAL DUALITY BETWEEN THE INTERVAL AND THE TEST.
   The previous version reported a two-sided 95% interval (2.5% per tail)
   beside a one-sided 5% test and called that "one alpha". They are different
   bars, which is how H2 came to be described as excluding zero when a
   higher-precision run put the bound on the other side. The interval is now
   two-sided at ``1 - 2*alpha`` — 90% for alpha=0.05 — which is exactly dual
   to the one-sided test, so "p <= alpha" and "the interval excludes zero"
   cannot disagree.

``alternative`` is explicit. Exploratory questions with no pre-committed
direction must pass ``two_sided``; reading a one-sided tail off whichever way
the estimate happens to point is not a test.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: The single significance level. The interval derives from it, not beside it.
ALPHA = 0.05
REQUIRED = ("pool", "date", "delta")


@dataclass(frozen=True)
class GroupGap:
    gap: float
    ci_low: float
    ci_high: float
    p: float
    alternative: str
    n_a: int
    n_b: int
    n_blocks: int
    n_shared_blocks: int
    alpha: float

    @property
    def significant(self) -> bool:
        return self.p <= self.alpha

    @property
    def ci_excludes_zero(self) -> bool:
        return self.ci_low > 0 or self.ci_high < 0


def _check(frame: pd.DataFrame, name: str) -> None:
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f"{name} lacks {missing} — the block bootstrap needs "
                         "pool and date, and a frame that dropped them cannot "
                         "be blocked")
    if frame.empty:
        raise ValueError(f"{name} is empty")


def _joint_blocks(frame_a, frame_b):
    """(pool -> list of blocks), each block = (a_values, b_values).

    A block is one (pool, matchday). It carries BOTH groups' rows for that
    matchday, so drawing it keeps them together and preserves the shared
    shock in the difference.
    """
    a = frame_a.assign(_g="a")
    b = frame_b.assign(_g="b")
    both = pd.concat([a, b], ignore_index=True)
    strata: dict = {}
    shared = 0
    for (pool, date), grp in both.groupby(["pool", "date"], observed=True):
        av = grp.loc[grp["_g"] == "a", "delta"].to_numpy()
        bv = grp.loc[grp["_g"] == "b", "delta"].to_numpy()
        if len(av) and len(bv):
            shared += 1
        strata.setdefault(pool, []).append((av, bv))
    return strata, shared


def _replicate(strata, rng) -> float:
    """One joint block-bootstrap draw of mean(a) - mean(b).

    Blocks are drawn with replacement WITHIN each pool, matching the
    repository's stratified primitive. Returns NaN when a draw happens to
    contain no rows for one group — those replicates carry no information
    about a difference and are dropped rather than silently treated as zero.
    """
    a_parts, b_parts = [], []
    for blocks in strata.values():
        idx = rng.integers(0, len(blocks), size=len(blocks))
        for i in idx:
            av, bv = blocks[i]
            if len(av):
                a_parts.append(av)
            if len(bv):
                b_parts.append(bv)
    if not a_parts or not b_parts:
        return float("nan")
    return float(np.concatenate(a_parts).mean()
                 - np.concatenate(b_parts).mean())


def two_group_gap(frame_a, frame_b, *, n_boot: int = 10000,
                  seed: int = 20260611, alpha: float = ALPHA,
                  alternative: str = "less") -> GroupGap:
    """Block-bootstrap ``mean(a) - mean(b)`` with joint, pool-stratified blocks.

    ``alternative``: ``less`` / ``greater`` for a pre-committed direction,
    ``two_sided`` for exploratory comparisons where the direction was not
    fixed in advance.
    """
    if alternative not in ("less", "greater", "two_sided"):
        raise ValueError(f"alternative must be less/greater/two_sided, "
                         f"got {alternative!r}")
    _check(frame_a, "frame_a")
    _check(frame_b, "frame_b")

    strata, shared = _joint_blocks(frame_a, frame_b)
    rng = np.random.default_rng(seed)
    reps = np.array([_replicate(strata, rng) for _ in range(n_boot)])
    reps = reps[~np.isnan(reps)]
    if reps.size < n_boot // 2:
        raise ValueError("more than half the bootstrap replicates were "
                         "uninformative — the groups share too few blocks "
                         "for this design")

    gap = float(frame_a["delta"].mean() - frame_b["delta"].mean())
    centred = reps - reps.mean()

    # PIVOTAL (basic) interval, not percentile. A percentile interval and a
    # null-centred p are only APPROXIMATELY dual — they agree when the
    # bootstrap distribution is symmetric and drift apart when it is not,
    # which is how a "significant" result can carry an interval containing
    # zero. The pivotal form gap - q(centred) makes the duality exact:
    # for `less`, p <= alpha  <=>  gap <= q_alpha(centred)  <=>  ci_high < 0.
    tail = 100 * (alpha if alternative != "two_sided" else alpha / 2)
    c_lo, c_hi = np.percentile(centred, [tail, 100 - tail])
    lo, hi = gap - c_hi, gap - c_lo

    if alternative == "less":
        p = float((centred <= gap).mean())
    elif alternative == "greater":
        p = float((centred >= gap).mean())
    else:
        p = float((np.abs(centred) >= abs(gap)).mean())

    return GroupGap(gap=gap, ci_low=float(lo), ci_high=float(hi), p=p,
                    alternative=alternative, n_a=len(frame_a),
                    n_b=len(frame_b),
                    n_blocks=sum(len(v) for v in strata.values()),
                    n_shared_blocks=shared, alpha=alpha)


def block_ci(frame, *, n_boot: int = 10000, seed: int = 20260611,
             alpha: float = ALPHA) -> tuple:
    """(mean, lo, hi) for one group, pool-stratified block resampling."""
    _check(frame, "frame")
    strata: dict = {}
    for (pool, date), grp in frame.groupby(["pool", "date"], observed=True):
        strata.setdefault(pool, []).append(grp["delta"].to_numpy())
    rng = np.random.default_rng(seed)
    reps = []
    for _ in range(n_boot):
        parts = []
        for blocks in strata.values():
            idx = rng.integers(0, len(blocks), size=len(blocks))
            parts.extend(blocks[i] for i in idx)
        reps.append(np.concatenate(parts).mean())
    lo, hi = np.percentile(reps, [100 * alpha, 100 * (1 - alpha)])
    return float(frame["delta"].mean()), float(lo), float(hi)
