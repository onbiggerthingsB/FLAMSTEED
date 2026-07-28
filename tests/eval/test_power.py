import numpy as np
import pytest

from wcmodel.eval.power import block_bootstrap_support, simulate_power


def _fake_panel(n=120, pools=("a", "b", "c"), seed=0):
    rng = np.random.default_rng(seed)
    pool = np.repeat(pools, n // len(pools))
    # ~4 matches per matchday block
    day = np.concatenate([np.repeat(np.arange(n // len(pools) // 4 + 1), 4)[: n // len(pools)]
                          for _ in pools])
    return pool, day, rng


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
