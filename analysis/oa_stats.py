#!/usr/bin/env python
"""Two-group block bootstrap for the post-hoc dev-slate tests.

WHY NOT JUST RESAMPLE FIXTURES
------------------------------
The first cut resampled individual fixtures. The programme's own tested
primitive (`wcmodel.eval.power.block_bootstrap_support`, used correctly by
V10) resamples ``(pool, matchday)`` BLOCKS, because fixtures sharing a
competition and a matchday are not independent — they share a fitted
posterior, a market state, and a day. Resampling fixtures pretends to more
independent information than exists and produces intervals that are too
narrow in one direction and mis-centred in the other.

The per-fixture PAIRING is preserved either way: each fixture is reduced to a
single paired delta (book minus model) before any resampling happens. What
the fixture bootstrap broke was between-fixture dependence, not the pairing.

WHY IT LIVES HERE AND NOT IN src/
---------------------------------
``CODE_PATHS = ("src", "scripts")`` is what the OA lock attests to. This is
post-hoc analysis machinery that must never price a forecast, so putting it
in ``src/`` would both invalidate the lock and imply the attested pipeline
had changed. It is tested (``tests/analysis/test_oa_stats.py``) — the point
of the earlier failure was untested ad-hoc code, not its directory.

ONE DECISION RULE, NOT TWO
--------------------------
The first cut reported ``mean(boot >= 0)`` as a "one-sided p" while
certifying on the 97.5th percentile — a 5% bar and a 2.5% bar in the same
report. Here the rule is stated once, in ``ALPHA``, and both the interval and
the test are derived from it. The p-value is NULL-CENTRED: the bootstrap
distribution is recentred on zero before the tail is read, because
``P(uncentred estimate >= 0)`` is bootstrap sign support, not a p-value.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: The single, explicit significance level. Everything below derives from it.
ALPHA = 0.05


@dataclass(frozen=True)
class GroupGap:
    """Difference in mean delta between two groups, with block inference."""
    gap: float
    ci_low: float
    ci_high: float
    p_one_sided: float
    n_a: int
    n_b: int
    blocks_a: int
    blocks_b: int
    alpha: float

    @property
    def significant(self) -> bool:
        """One-sided at ``alpha`` in the DIRECTION THE GAP POINTS.

        A single rule, applied to the null-centred tail. The interval is
        reported alongside for magnitude, never as a second, stricter gate.
        """
        return self.p_one_sided <= self.alpha


def _blocks(frame: pd.DataFrame) -> dict:
    """Map (pool, date) -> the delta values in that block."""
    out: dict = {}
    for key, grp in frame.groupby(["pool", "date"], observed=True):
        out[key] = grp["delta"].to_numpy()
    return out


def _resample(blocks: list, rng) -> float:
    """Mean of one block-bootstrap replicate: draw whole blocks with
    replacement, then pool their fixtures."""
    picked = rng.integers(0, len(blocks), size=len(blocks))
    drawn = np.concatenate([blocks[i] for i in picked])
    return float(drawn.mean())


def two_group_gap(frame_a: pd.DataFrame, frame_b: pd.DataFrame, *,
                  n_boot: int = 10000, seed: int = 20260611,
                  alpha: float = ALPHA) -> GroupGap:
    """Block-bootstrap the difference ``mean(a) - mean(b)``.

    Both frames need ``pool``, ``date`` and ``delta``. Blocks are resampled
    independently within each group, which is the correct null for "these two
    groups have the same mean delta".
    """
    for name, frame in (("a", frame_a), ("b", frame_b)):
        missing = {"pool", "date", "delta"} - set(frame.columns)
        if missing:
            raise ValueError(f"frame_{name} lacks {sorted(missing)} — the "
                             "block bootstrap needs pool and date, and a "
                             "frame that dropped them cannot be blocked")
        if frame.empty:
            raise ValueError(f"frame_{name} is empty")

    blocks_a = list(_blocks(frame_a).values())
    blocks_b = list(_blocks(frame_b).values())
    rng = np.random.default_rng(seed)
    reps = np.array([_resample(blocks_a, rng) - _resample(blocks_b, rng)
                     for _ in range(n_boot)])

    gap = float(frame_a["delta"].mean() - frame_b["delta"].mean())
    lo, hi = np.percentile(reps, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    # NULL-CENTRED tail: recentre the replicate distribution on zero, then ask
    # how often it reaches at least as far as the observed gap, in the
    # direction the gap points. This is a p-value; P(uncentred >= 0) is not.
    centred = reps - reps.mean()
    p = (float((centred <= gap).mean()) if gap < 0
         else float((centred >= gap).mean()))
    return GroupGap(gap=gap, ci_low=float(lo), ci_high=float(hi),
                    p_one_sided=p, n_a=len(frame_a), n_b=len(frame_b),
                    blocks_a=len(blocks_a), blocks_b=len(blocks_b),
                    alpha=alpha)


def block_ci(frame: pd.DataFrame, *, n_boot: int = 10000,
             seed: int = 20260611, alpha: float = ALPHA) -> tuple:
    """(mean, lo, hi) for one group's mean delta, blocked the same way."""
    blocks = list(_blocks(frame).values())
    rng = np.random.default_rng(seed)
    reps = np.array([_resample(blocks, rng) for _ in range(n_boot)])
    lo, hi = np.percentile(reps, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(frame["delta"].mean()), float(lo), float(hi)
