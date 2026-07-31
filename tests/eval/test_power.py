import numpy as np
import pytest

from wcmodel.eval.power import (block_bootstrap_support, mde, simulate_power,
                                simulate_power_detail)


def _fake_panel(n=120, pools=("a", "b", "c"), seed=0):
    rng = np.random.default_rng(seed)
    pool = np.repeat(pools, n // len(pools))
    # ~4 matches per matchday block
    day = np.concatenate([np.repeat(np.arange(n // len(pools) // 4 + 1), 4)[: n // len(pools)]
                          for _ in pools])
    return pool, day, rng


def _correlated_panel(pools=("a", "b", "c"), n_days=10, per_day=6,
                      shock_sd=0.05, idio_sd=0.005, panel_mean=-0.005, seed=0):
    """Panel where every (pool, day) block shares one common shock — the
    structure the block bootstrap exists to respect. The realized panel mean is
    pinned so the block-vs-iid comparison is not a lottery on the shock draw."""
    rng = np.random.default_rng(seed)
    pool, day, diffs = [], [], []
    for p in pools:
        for d in range(n_days):
            shock = rng.normal(0.0, shock_sd)
            pool += [p] * per_day
            day += [d] * per_day
            diffs.append(shock + rng.normal(0.0, idio_sd, size=per_day))
    diffs = np.concatenate(diffs)
    return np.array(pool), np.array(day), diffs - diffs.mean() + panel_mean


def test_support_near_half_under_null():
    # Support is p-value-like: on any SINGLE null panel it is ~Uniform(0,1)
    # (measured sd 0.289), because the bootstrap centres on that panel's
    # sample mean. So a one-panel band passes or fails on the data seed alone
    # (seed 0 gives 0.175 — a 0.93-sigma sample mean, entirely ordinary).
    # Averaging over independent null panels is the seed-free statement of the
    # same property: no systematic drift toward "improved".
    sups = []
    for panel_seed in range(30):
        pool, day, rng = _fake_panel(seed=panel_seed)
        diffs = rng.normal(0.0, 0.05, size=len(pool))      # zero true effect
        sups.append(block_bootstrap_support(diffs, pool, day,
                                            n_boot=2000, seed=0))
    s = float(np.mean(sups))
    assert 0.30 < s < 0.70


def test_support_high_under_large_effect():
    pool, day, rng = _fake_panel(seed=1)
    diffs = rng.normal(-0.02, 0.05, size=len(pool))        # big improvement
    s = block_bootstrap_support(diffs, pool, day, n_boot=2000, seed=0)
    assert s > 0.95


def test_power_monotone_in_effect():
    pool, day, rng = _fake_panel(seed=2)
    noise = rng.normal(0.0, 0.05, size=len(pool))
    p_small = simulate_power(noise, pool, day, delta=0.001, floor=0.002,
                             support_req=0.8, n_sims=200, n_boot=500, seed=0)
    p_large = simulate_power(noise, pool, day, delta=0.010, floor=0.002,
                             support_req=0.8, n_sims=200, n_boot=500, seed=0)
    assert p_large > p_small
    assert p_large > 0.9


def test_power_at_the_floor_is_a_coin_flip():
    # The MDE is set by the DISPERSION of the simulated panel mean, not by the
    # floor: with the true effect EQUAL to the floor, half the panels miss the
    # floor on noise alone, so power(delta == floor) must be ~0.5. support_req=0
    # isolates the floor half of the gate. A panel draw that is a permutation
    # rather than a resample makes d.mean() exactly -delta and collapses this
    # curve to a step, while every other test in this file still passes.
    pool, day, rng = _fake_panel(seed=6)
    noise = rng.normal(0.0, 0.0133, size=len(pool))
    p = simulate_power(noise, pool, day, delta=0.002, floor=0.002,
                       support_req=0.0, n_sims=400, n_boot=1, seed=0)
    assert 0.40 < p < 0.60


def test_effect_is_measured_from_the_centered_noise():
    # delta means "true effect", which holds only because simulate_power
    # subtracts the noise sample's own mean: the empirical k0.5-k0.6 diffs
    # carry mean -0.000502 (0.51 iid se, 25% of the 0.002 floor) in the
    # power-inflating direction, so an uncentered noise model would smuggle
    # that head start into every delta — including delta=0, where the reported
    # number IS the gate's simulated false-positive rate under a true null.
    pool, day, rng = _fake_panel(seed=4)
    noise = rng.normal(-0.004, 0.010, size=len(pool))   # deliberately off-centre
    p_null = simulate_power(noise, pool, day, delta=0.0, floor=0.002,
                            support_req=0.8, n_sims=200, n_boot=200, seed=0)
    assert p_null < 0.10


def test_support_requirement_is_inclusive_at_its_boundary():
    # support is a discrete k/n_boot fraction, so a simulation landing EXACTLY
    # on support_req is reachable, and ">=80% support" is the pre-registered
    # spec constant — the boundary case counts as a pass. Re-running with
    # support_req set to a support value the run actually achieves (its
    # observed minimum) must therefore leave power untouched; a strict > would
    # reject that simulation. Derived at runtime, not hardcoded, so the test
    # pins the comparison rather than one numpy version's draws.
    pool, day, rng = _fake_panel(seed=5)
    noise = rng.normal(0.0, 0.05, size=len(pool))
    kw = dict(delta=0.006, floor=0.002, n_sims=40, n_boot=200, seed=0)
    loose = simulate_power_detail(noise, pool, day, support_req=0.0, **kw)
    assert 0.0 < loose.min_support < 1.0     # interior: strictly achievable
    at_boundary = simulate_power_detail(noise, pool, day,
                                        support_req=loose.min_support, **kw)
    assert at_boundary.power == loose.power > 0.0
    assert at_boundary.support_reject == 0


def test_blocks_widen_support_on_correlated_panel():
    # On block-correlated data, ignoring the (pool, day) blocks understates the
    # spread of the bootstrap mean and so overstates support — by enough to
    # flip the >=0.80 gate verdict. The tests above cannot see this: their
    # panels are i.i.d., where block structure is a no-op.
    pool, day, diffs = _correlated_panel()
    s_block = block_bootstrap_support(diffs, pool, day, n_boot=2000, seed=0)
    # same estimator with every observation in its own block == iid bootstrap
    s_iid = block_bootstrap_support(diffs, pool, np.arange(len(diffs)),
                                    n_boot=2000, seed=0)
    assert s_iid - s_block > 0.10
    assert s_block < 0.80 <= s_iid


def test_resampling_is_stratified_within_pool():
    # Blocks are resampled WITHIN pool, so every resample carries each pool's
    # exact share of the panel. With constant-per-pool diffs that pins every
    # bootstrap mean at (-1.0 + 0.6 + 0.6)/3 > 0, i.e. support exactly 0.
    # Blocking by day across pools instead would let pool a's solo day-2/day-3
    # blocks crowd out b and c and drive support far above 0.
    pool = np.array(["a"] * 16 + ["b"] * 16 + ["c"] * 16)
    day = np.array([0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3]  # a: 4 x 4
                   + [0] * 8 + [1] * 8                               # b: 2 x 8
                   + [0] * 8 + [1] * 8)                              # c: 2 x 8
    diffs = np.where(pool == "a", -1.0, 0.6)
    s = block_bootstrap_support(diffs, pool, day, n_boot=200, seed=0)
    assert s == 0.0


def test_length_mismatch_is_rejected():
    pool, day, rng = _fake_panel()
    diffs = rng.normal(0.0, 0.05, size=len(pool))
    with pytest.raises(ValueError, match="length"):
        block_bootstrap_support(diffs[:-1], pool, day, n_boot=10, seed=0)
    with pytest.raises(ValueError, match="length"):
        simulate_power(np.concatenate([diffs, diffs]), pool, day, delta=0.001,
                       floor=0.002, support_req=0.8, n_sims=2, n_boot=10,
                       seed=0)
    # a floor no panel can clear: with every sim skipped before the bootstrap,
    # simulate_power's OWN guard is the only thing left to catch the mismatch
    with pytest.raises(ValueError, match="length"):
        simulate_power(np.concatenate([diffs, diffs]), pool, day, delta=0.0,
                       floor=1.0, support_req=0.8, n_sims=3, n_boot=10, seed=0)


def test_detail_reports_which_half_of_the_gate_binds():
    pool, day, rng = _fake_panel(seed=3)
    noise = rng.normal(0.0, 0.05, size=len(pool))
    kw = dict(delta=0.010, floor=0.002, n_sims=50, n_boot=200, seed=0)
    loose = simulate_power_detail(noise, pool, day, support_req=0.0, **kw)
    strict = simulate_power_detail(noise, pool, day, support_req=1.01, **kw)
    assert loose.floor_pass == strict.floor_pass > 0
    assert loose.support_reject == 0                        # floor alone binds
    assert strict.support_reject == strict.floor_pass       # support binds
    assert loose.power == loose.floor_pass / 50
    assert strict.power == 0.0
    assert 0.0 <= loose.min_support <= 1.0
    assert loose.power == simulate_power(noise, pool, day, support_req=0.0,
                                         **kw)
    empty = simulate_power_detail(noise, pool, day, support_req=0.8, delta=0.0,
                                  floor=1.0, n_sims=5, n_boot=50, seed=0)
    assert empty.floor_pass == 0 and np.isnan(empty.min_support)


def test_mde_is_smallest_delta_reaching_target_power():
    rows = [(0.000, 0.03), (0.002, 0.51), (0.003, 0.83), (0.004, 0.98)]
    assert mde(rows) == 0.003
    assert mde(rows, target=0.99) is None
