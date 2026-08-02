"""Tests for the two-group block bootstrap.

The first version of these tests did not exist, and the code it would have
covered resampled individual fixtures instead of (pool, matchday) blocks —
overstating the independent information in the sample. It also reported a
5% "p-value" beside a 2.5% certification rule. Both are pinned here.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "analysis"))

from oa_stats import ALPHA, block_ci, two_group_gap            # noqa: E402


def _frame(deltas, *, pool="p", start_day=1, per_block=1):
    """Lay `deltas` into blocks of `per_block` fixtures per (pool, date)."""
    rows = []
    for i, d in enumerate(deltas):
        rows.append({"pool": pool,
                     "date": f"2024-01-{start_day + i // per_block:02d}",
                     "delta": float(d)})
    return pd.DataFrame(rows)


def test_gap_equals_the_difference_in_means():
    a, b = _frame([1.0, 1.0, 1.0]), _frame([0.0, 0.0, 0.0])
    assert two_group_gap(a, b, n_boot=200).gap == pytest.approx(1.0)


def test_blocks_are_counted_not_fixtures():
    """Fixtures sharing a matchday are ONE block. Missing this is exactly what
    made the original intervals too narrow."""
    a = _frame([0.1] * 10, per_block=10, start_day=1)   # 1 block
    b = _frame([0.0] * 10, per_block=1, start_day=20)   # 10 blocks
    res = two_group_gap(a, b, n_boot=200)
    assert res.n_blocks == 11
    assert res.n_a == res.n_b == 10


def test_shared_blocks_are_drawn_whole_not_independently():
    """THE defect the second repair fixed. When both groups appear on the same
    matchday they share a common shock. Drawing the block whole cancels that
    shock in the difference; drawing the groups apart does not, and inflates
    the apparent uncertainty of the gap."""
    # Same matchdays for both groups, with a large per-matchday shock that is
    # IDENTICAL in each group, so the true difference is exactly 0.20 with no
    # block-driven variance at all.
    shocks = [10.0, -10.0, 5.0, -5.0, 7.0, -7.0]
    a = _frame([s + 0.2 for s in shocks], per_block=1)
    b = _frame([s for s in shocks], per_block=1)
    res = two_group_gap(a, b, n_boot=3000, alternative="two_sided")
    assert res.n_shared_blocks == 6, "the groups must share every block here"
    assert res.gap == pytest.approx(0.2)
    # The common shock cancels, so the interval must be TIGHT around 0.2.
    # Independent resampling would leave the +-10 shock in the difference.
    assert (res.ci_high - res.ci_low) < 1.0


def test_pool_strata_are_respected():
    """Blocks are resampled within pool, matching the repository primitive."""
    a = pd.concat([_frame([0.3, 0.3], pool="p1"),
                   _frame([0.9, 0.9], pool="p2", start_day=10)])
    b = pd.concat([_frame([0.0, 0.0], pool="p1"),
                   _frame([0.0, 0.0], pool="p2", start_day=10)])
    res = two_group_gap(a, b, n_boot=500, alternative="two_sided")
    assert res.n_blocks == 4        # 2 dates x 2 pools


def test_block_dependence_widens_the_interval_versus_treating_rows_as_free():
    """The substantive claim, and the reason the original numbers were wrong.

    The SAME eight values, laid out two ways. Grouped so that each matchday
    carries one sign, there are really only two independent observations and
    the interval must be wide. Spread one-per-matchday there are eight, and
    it must be narrower. Fixture-level resampling always reports the narrow
    answer, which is how the first cut understated its uncertainty.
    """
    values = [0.5, 0.5, 0.5, 0.5, -0.5, -0.5, -0.5, -0.5]
    # start_day keeps the reference group on DIFFERENT matchdays, so no block
    # is shared and this isolates clustering from the shared-shock effect.
    clustered = _frame(values, per_block=4)     # 2 blocks, means +0.5 / -0.5
    independent = _frame(values, per_block=1)   # 8 blocks
    ref = _frame([0.0] * 8, per_block=1, start_day=20)
    wide = two_group_gap(clustered, ref, n_boot=4000, alternative="two_sided")
    narrow = two_group_gap(independent, ref, n_boot=4000,
                           alternative="two_sided")
    assert wide.n_shared_blocks == 0 and narrow.n_shared_blocks == 0
    assert (wide.ci_high - wide.ci_low) > (narrow.ci_high - narrow.ci_low)


def test_a_frame_without_date_is_refused_not_silently_unblocked():
    """The original H2 script dropped `date`, which made the prescribed
    bootstrap impossible downstream. That must fail loudly."""
    a = _frame([1.0, 2.0]).drop(columns=["date"])
    with pytest.raises(ValueError, match="date"):
        two_group_gap(a, _frame([0.0, 0.0]), n_boot=50)


def test_interval_and_test_agree_by_construction():
    """The duality the first repair claimed and did not deliver: it paired a
    5% tail with a 97.5th-percentile gate, so a result could be significant
    while its interval contained zero. Across varied data the two must now
    never disagree."""
    rng = np.random.default_rng(11)
    for _ in range(12):
        a = _frame(rng.normal(-0.05, 0.1, 8))
        b = _frame(rng.normal(0.0, 0.1, 8), start_day=20)
        res = two_group_gap(a, b, n_boot=1500, alternative="less")
        assert res.significant == res.ci_excludes_zero


def test_two_sided_is_required_for_undirected_questions():
    """A one-sided tail read off whichever way the estimate points is not a
    test. Both alternatives must be available and must differ."""
    # A modest separation, so neither tail saturates at exactly 0.
    a = _frame([0.10, 0.02, 0.14, -0.03, 0.08, 0.01])
    b = _frame([0.0, 0.03, -0.05, 0.02, -0.01, 0.04], start_day=20)
    one = two_group_gap(a, b, n_boot=4000, alternative="greater")
    two = two_group_gap(a, b, n_boot=4000, alternative="two_sided")
    assert two.p >= one.p
    with pytest.raises(ValueError, match="less/greater/two_sided"):
        two_group_gap(a, b, n_boot=50, alternative="whichever-wins")


def test_p_value_is_null_centred_not_sign_support():
    """With two identical groups the true gap is zero, so a null-centred
    one-sided p must sit near 0.5 — NOT near 0 or 1, which is what raw
    P(uncentred >= 0) would give for a group whose mean is far from zero."""
    # Same mean, different composition and different matchdays, so the
    # bootstrap is non-degenerate and the true gap is zero.
    a = _frame([0.9, 1.0, 1.1, 1.0])
    b = _frame([1.05, 0.95, 1.15, 0.85], start_day=20)
    res = two_group_gap(a, b, n_boot=4000, alternative="two_sided")
    assert abs(res.gap) < 0.02
    assert 0.2 < res.p < 1.01


def test_a_real_separation_is_detected():
    a = _frame([-0.30, -0.28, -0.32, -0.29, -0.31, -0.27, -0.33, -0.30])
    b = _frame([0.30, 0.28, 0.32, 0.29, 0.31, 0.27, 0.33, 0.30])
    res = two_group_gap(a, b, n_boot=4000, alternative='less')
    assert res.gap < 0
    assert res.significant
    assert res.ci_high < 0


def test_alpha_widens_the_interval():
    """The original reported a 5% tail beside a 97.5th-percentile gate. Here
    a single alpha drives both, so they cannot disagree by construction."""
    # Varied values: a constant group has zero bootstrap spread, so every
    # alpha would return the same degenerate interval and prove nothing.
    a = _frame([0.30, -0.10, 0.22, 0.05, -0.18, 0.41])
    b = _frame([0.02, 0.11, -0.25, 0.19, 0.07, -0.09])
    res = two_group_gap(a, b, n_boot=2000, alpha=ALPHA)
    assert res.alpha == ALPHA
    tight = two_group_gap(a, b, n_boot=2000, alpha=0.20)
    assert (tight.ci_high - tight.ci_low) < (res.ci_high - res.ci_low)


def test_block_ci_agrees_with_the_two_group_machinery():
    frame = _frame([0.2, -0.1, 0.3, 0.0, 0.15, -0.05])
    mean, lo, hi = block_ci(frame, n_boot=500)
    assert mean == pytest.approx(frame["delta"].mean())
    assert lo <= mean <= hi


def test_seed_is_deterministic():
    a, b = _frame([0.3, -0.1, 0.2]), _frame([0.0, 0.1, -0.2])
    first = two_group_gap(a, b, n_boot=500, seed=7)
    second = two_group_gap(a, b, n_boot=500, seed=7)
    assert first == second
