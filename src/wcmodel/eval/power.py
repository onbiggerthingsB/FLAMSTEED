"""Power/MDE machinery for the OA prereg gate (spec OA-5, finding 7).

Block bootstrap: blocks are (pool, matchday) groups, resampled with
replacement WITHIN pool strata — matches within a matchday share shocks and
must move together (finding 8). support = fraction of bootstrap means < 0.

The same blocks govern panel GENERATION (plan V7 / finding 12): drawing each
simulated panel i.i.d. from single matches breaks the within-matchday shock
and understates the dispersion of the panel MEAN, which is what the floor half
of the gate tests — so an i.i.d.-generated MDE is optimistic on any panel with
positive within-block correlation. ``generation="block"`` resamples whole
(pool, matchday) blocks instead; :func:`within_block_correlation` measures the
correlation and :func:`generation_for_correlation` applies the pre-committed
0.05 threshold that decides which generation the lock re-states the MDE under.
The decision rule itself lives here too (:data:`GATE_FLOOR`,
:data:`GATE_SUPPORT_REQ`, :func:`gate_pass`) so the simulator, the MDE runner
and the scored-pool scorer cannot drift apart from the analysis spec
(``reports/oa_analysis_spec.md``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

#: Pre-registered adoption gate, on the canonical RPS scale: the arm's mean
#: paired diff must sit at or below this floor (negative = arm beats
#: incumbent), and at least this fraction of block-bootstrap means must be
#: below zero. Both comparisons are INCLUSIVE at the constant.
GATE_FLOOR = -0.002
GATE_SUPPORT_REQ = 0.80

#: "Materially positive" within-block correlation, pre-committed: strictly
#: above this, the MDE is re-stated under block panel generation.
BLOCK_CORR_THRESHOLD = 0.05

#: How a simulated panel is drawn from the centered noise model.
PANEL_GENERATIONS = ("iid", "block")


def _check_lengths(diffs, pool, day) -> None:
    """pool/day index the same panel as diffs; a mismatch would silently drop
    or double-count observations inside every bootstrap mean."""
    if not (len(diffs) == len(pool) == len(day)):
        raise ValueError(f"length mismatch: values={len(diffs)}, "
                         f"pool={len(pool)}, day={len(day)}")


def floor_pass(mean_diff, *, floor: float = GATE_FLOOR) -> bool:
    """Floor half of the gate: mean paired diff at or below ``floor``."""
    return bool(float(mean_diff) <= floor)


def support_pass(support, *, support_req: float = GATE_SUPPORT_REQ) -> bool:
    """Support half of the gate: block-bootstrap support at or above the
    requirement."""
    return bool(float(support) >= support_req)


def gate_pass(mean_diff, support, *, floor: float = GATE_FLOOR,
              support_req: float = GATE_SUPPORT_REQ) -> bool:
    """The two-part adoption gate, one implementation for every caller."""
    return (floor_pass(mean_diff, floor=floor)
            and support_pass(support, support_req=support_req))


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


def within_block_correlation(diffs, pool, day) -> float:
    """Mean PAIRWISE within-(pool, matchday) correlation of the paired diffs.

    Every ordered within-block pair contributes equally (so a block of size m
    carries m(m-1) of them), centered on the GRAND mean and scaled by the
    panel variance about it — the intraclass reading of "do matches on the
    same matchday move together", which is the dependence the panel generation
    has to reproduce. Centering within blocks instead would define the
    quantity away: it is exactly the block-to-block common shock that inflates
    the variance of the panel mean.

    A panel with no within-block pair at all (every match on its own matchday)
    raises rather than returning nan: nan compares False against the
    threshold, which would silently select the optimistic i.i.d. branch.
    """
    diffs = np.asarray(diffs, dtype=float)
    pool = np.asarray(pool)
    day = np.asarray(day)
    _check_lengths(diffs, pool, day)
    centered = diffs - diffs.mean()
    var = float((centered ** 2).mean())
    cross, pairs = 0.0, 0
    for blist in _blocks(pool, day).values():
        for idx in blist:
            m = len(idx)
            if m < 2:
                continue
            s = float(centered[idx].sum())
            # sum over ordered pairs i != j == (sum)^2 - sum of squares
            cross += s * s - float((centered[idx] ** 2).sum())
            pairs += m * (m - 1)
    if pairs == 0:
        raise ValueError(
            "no within-block pair: every (pool, matchday) block holds a "
            "single match, so within-block correlation is undefined")
    if var == 0.0:
        raise ValueError("zero-variance panel: correlation is undefined")
    return float(cross / (pairs * var))


def generation_for_correlation(correlation,
                               *, threshold: float = BLOCK_CORR_THRESHOLD
                               ) -> str:
    """Which panel generation the pre-committed rule requires: block when the
    within-block correlation EXCEEDS the threshold (strictly), else iid."""
    return "block" if float(correlation) > threshold else "iid"


def draw_panel(noise, pool, day, *, delta: float, generation: str, rng):
    """One simulated panel under a true per-match effect of ``-delta``.

    Returns ``(diffs, pool, day)`` — the labels come back because block
    generation builds its OWN block structure, which the support stage must
    then bootstrap.

    * ``iid`` — resample single matches from the whole centered noise vector
      and keep the observed panel's labels. Independence across matches is
      assumed, so the panel mean is as tight as the noise model allows.
    * ``block`` — resample whole (pool, matchday) blocks with replacement
      WITHIN each pool, the same unit and stratification the support
      bootstrap uses. Each pool keeps its own block COUNT (hence its exact row
      count when blocks are equal-sized; a panel with ragged blocks varies in
      length draw to draw — the standard non-overlapping block bootstrap
      trade-off, taken deliberately over reshaping blocks to a fixed size,
      which would break the verbatim-block copy that carries the shock).
    """
    noise = np.asarray(noise, dtype=float)
    pool = np.asarray(pool)
    day = np.asarray(day)
    _check_lengths(noise, pool, day)
    if generation == "iid":
        return (-delta + rng.choice(noise, size=len(noise), replace=True),
                pool, day)
    if generation != "block":
        raise ValueError(f"unknown panel generation {generation!r}: "
                         f"expected one of {PANEL_GENERATIONS}")
    values, out_pool, out_day = [], [], []
    for p, blist in _blocks(pool, day).items():
        k = len(blist)
        for slot, pick in enumerate(rng.integers(0, k, size=k)):
            idx = blist[pick]
            values.append(noise[idx])
            out_pool += [p] * len(idx)
            out_day += [slot] * len(idx)
    return (-delta + np.concatenate(values), np.array(out_pool),
            np.array(out_day))


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
                          seed: int, generation: str = "iid") -> PowerDetail:
    """P(gate passes | true per-match effect = -delta), noise resampled from
    the centered empirical paired-difference distribution.

    ``floor`` is the POSITIVE magnitude of the gate's floor (0.002 for the
    pre-registered -0.002). ``generation`` selects how each panel is drawn —
    see :func:`draw_panel`; it is validated up front, because a floor no panel
    can clear would otherwise skip every check inside the loop.
    """
    noise = np.asarray(noise, dtype=float)
    pool = np.asarray(pool)
    day = np.asarray(day)
    _check_lengths(noise, pool, day)
    if generation not in PANEL_GENERATIONS:
        raise ValueError(f"unknown panel generation {generation!r}: "
                         f"expected one of {PANEL_GENERATIONS}")
    noise = noise - noise.mean()
    rng = np.random.default_rng(seed)
    # spawned children are independent of default_rng(seed) itself, so a
    # simulation's bootstrap never reuses the stream that drew its own panel
    boot_seeds = np.random.SeedSequence(seed).spawn(n_sims)
    cleared = 0
    passes = 0
    sups = []
    for s in range(n_sims):
        d, d_pool, d_day = draw_panel(noise, pool, day, delta=delta,
                                      generation=generation, rng=rng)
        if not floor_pass(d.mean(), floor=-floor):
            continue
        cleared += 1
        sup = block_bootstrap_support(d, d_pool, d_day, n_boot=n_boot,
                                      seed=boot_seeds[s])
        sups.append(sup)
        if support_pass(sup, support_req=support_req):
            passes += 1
    return PowerDetail(power=passes / n_sims, floor_pass=cleared,
                       support_reject=cleared - passes,
                       min_support=float(min(sups)) if sups else float("nan"))


def simulate_power(noise, pool, day, *, delta: float, floor: float,
                   support_req: float, n_sims: int, n_boot: int,
                   seed: int, generation: str = "iid") -> float:
    return simulate_power_detail(noise, pool, day, delta=delta, floor=floor,
                                 support_req=support_req, n_sims=n_sims,
                                 n_boot=n_boot, seed=seed,
                                 generation=generation).power


def mde(rows: Sequence[tuple[float, float]], *,
        target: float = 0.80) -> float | None:
    """Smallest delta whose simulated power reaches target; None if none does."""
    for d, p in sorted(rows):
        if p >= target:
            return d
    return None
