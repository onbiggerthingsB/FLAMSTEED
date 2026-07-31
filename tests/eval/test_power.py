import numpy as np
import pytest

from wcmodel.eval.power import (BLOCK_CORR_THRESHOLD, GATE_FLOOR,
                                GATE_SUPPORT_REQ, block_bootstrap_support,
                                draw_panel, floor_pass, gate_pass,
                                generation_for_correlation, mde, simulate_power,
                                simulate_power_detail, support_pass,
                                within_block_correlation)


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
        within_block_correlation(diffs[:-1], pool, day)
    with pytest.raises(ValueError, match="length"):
        draw_panel(diffs[:-1], pool, day, delta=0.0, generation="block",
                   rng=np.random.default_rng(0))
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


# ------------------------------------------------- V7: block panel generation


def test_block_generation_flips_the_power_verdict_on_a_correlated_panel():
    # THE discriminating case (plan V7 / finding 12). iid generation draws
    # single matches, which destroys the common (pool, matchday) shock and so
    # shrinks the dispersion of the panel MEAN — the exact quantity the floor
    # half of the gate tests. Block generation resamples whole matchdays and
    # keeps it. On a shocked panel the difference is big enough to move the
    # SAME delta across the 0.80 power target, i.e. to flip the MDE verdict
    # the prereg reports. Every other test in this file uses i.i.d. panels,
    # where the two generations are the same thing.
    pool, day, noise = _correlated_panel(n_days=12, per_day=10, shock_sd=0.02,
                                         idio_sd=0.004, seed=11)
    delta = 0.0035
    kw = dict(delta=delta, floor=-GATE_FLOOR, support_req=GATE_SUPPORT_REQ,
              n_sims=200, n_boot=100, seed=0)
    p_iid = simulate_power(noise, pool, day, generation="iid", **kw)
    p_block = simulate_power(noise, pool, day, generation="block", **kw)
    assert p_iid >= 0.80 > p_block
    # ... stated in the MDE vocabulary the report actually prints
    assert mde([(delta, p_iid)]) == delta
    assert mde([(delta, p_block)]) is None


def test_block_generation_resamples_whole_blocks_within_pool():
    pool, day, noise = _correlated_panel(n_days=4, per_day=3, seed=2)
    d, out_pool, out_day = draw_panel(noise, pool, day, delta=0.0,
                                      generation="block",
                                      rng=np.random.default_rng(0))
    pools = np.unique(pool)
    assert len(d) == len(noise)
    for p in pools:
        # each pool keeps its own share of the panel and its own block count:
        # resampling is stratified WITHIN pool, exactly as the support stage is
        assert (out_pool == p).sum() == (pool == p).sum()
        assert (len(np.unique(out_day[out_pool == p]))
                == len(np.unique(day[pool == p])))
    for p in pools:
        originals = {tuple(noise[(pool == p) & (day == dd)])
                     for dd in np.unique(day[pool == p])}
        for dd in np.unique(out_day[out_pool == p]):
            # verbatim block copies, not per-match draws reassembled into
            # blocks — that distinction IS the within-block correlation
            assert tuple(d[(out_pool == p) & (out_day == dd)]) in originals
    assert not np.array_equal(d, noise)          # drawn with replacement


def test_iid_generation_is_the_default_and_leaves_the_panel_labels_alone():
    # iid generation is what every shipped MDE number (reports/oa_mde.md) was
    # produced under, so adding the parameter must not move it.
    pool, day, noise = _correlated_panel(n_days=6, per_day=3, seed=3)
    d, out_pool, out_day = draw_panel(noise, pool, day, delta=0.001,
                                      generation="iid",
                                      rng=np.random.default_rng(0))
    assert np.array_equal(out_pool, pool) and np.array_equal(out_day, day)
    assert len(d) == len(noise)
    kw = dict(delta=0.004, floor=0.002, support_req=0.8, n_sims=30, n_boot=50,
              seed=0)
    assert (simulate_power(noise, pool, day, **kw)
            == simulate_power(noise, pool, day, generation="iid", **kw) > 0.0)


def test_unknown_generation_is_refused():
    # a typo must not silently fall back to the optimistic (iid) branch
    pool, day, noise = _correlated_panel(n_days=3, per_day=2, seed=4)
    with pytest.raises(ValueError, match="generation"):
        draw_panel(noise, pool, day, delta=0.0, generation="bootstrap",
                   rng=np.random.default_rng(0))
    # refused UP FRONT: a floor no panel can clear means the loop body — and
    # any check inside it — never runs
    with pytest.raises(ValueError, match="generation"):
        simulate_power(noise, pool, day, delta=0.0, floor=1.0, support_req=0.8,
                       n_sims=3, n_boot=10, seed=0, generation="blocks")


# ------------------------------------------------ V7: the pre-committed gate


def test_gate_constants_are_the_preregistered_ones():
    # the prereg's numbers, in code, so the scorer (V10) and the MDE runner
    # cannot drift apart from the analysis spec
    assert GATE_FLOOR == -0.002
    assert GATE_SUPPORT_REQ == 0.80
    assert BLOCK_CORR_THRESHOLD == 0.05


def test_gate_boundaries_are_inclusive_at_exactly_minus_0_002_and_0_80():
    # "mean <= -0.002 AND support >= 0.80": a result landing EXACTLY on either
    # constant passes. nextafter steps one ULP to the failing side, so only
    # the comparison operator itself can make these come out right.
    assert gate_pass(-0.002, 0.80) is True
    assert floor_pass(-0.002) is True
    assert support_pass(0.80) is True
    assert floor_pass(float(np.nextafter(-0.002, 0.0))) is False
    assert support_pass(float(np.nextafter(0.80, 0.0))) is False
    # both halves are required
    assert gate_pass(float(np.nextafter(-0.002, 0.0)), 1.0) is False
    assert gate_pass(-1.0, float(np.nextafter(0.80, 0.0))) is False
    assert gate_pass(-0.001, 0.99) is False
    assert gate_pass(-0.003, 0.79) is False


def test_a_panel_mean_of_exactly_minus_0_002_clears_the_floor():
    # the same boundary through the simulator's own floor test. A two-match
    # single-block panel with zero-variance noise puts d.mean() EXACTLY on
    # -0.002 (x + x then /2 is exact in binary FP — asserted below as the
    # premise, so a numpy that broke it fails loudly instead of passing
    # vacuously), so the whole run turns on <= versus <.
    pool, day, noise = np.array(["a", "a"]), np.array([0, 0]), np.zeros(2)
    d, _, _ = draw_panel(noise, pool, day, delta=0.002, generation="iid",
                         rng=np.random.default_rng(0))
    assert d.mean() == GATE_FLOOR
    kw = dict(floor=-GATE_FLOOR, support_req=GATE_SUPPORT_REQ, n_sims=20,
              n_boot=50, seed=0)
    at = simulate_power_detail(noise, pool, day, delta=0.002, **kw)
    assert at.floor_pass == 20 and at.power == 1.0
    inside = simulate_power_detail(noise, pool, day,
                                   delta=float(np.nextafter(0.002, 0.0)), **kw)
    assert inside.floor_pass == 0 and inside.power == 0.0


def test_a_support_of_exactly_0_80_passes_the_gate():
    # support is a k/n_boot fraction, so exactly 0.80 is REACHABLE and the
    # ">= 80%" rule must admit it. Rigged panel: one pool, two singleton
    # blocks (-1.0, +0.6), where only the {+0.6, +0.6} resample has a
    # non-negative mean, so support = 1 - k/n_boot. The seed that lands on
    # 80/100 is SEARCHED at runtime, not hardcoded, so this pins the
    # comparison rather than one numpy version's draws.
    pool, day = np.array(["a", "a"]), np.array([0, 1])
    diffs = np.array([-1.0, 0.6])
    for seed in range(2000):
        s = block_bootstrap_support(diffs, pool, day, n_boot=100, seed=seed)
        if s == GATE_SUPPORT_REQ:
            break
    else:
        pytest.fail("no seed in 2000 produced a support of exactly 0.80")
    assert s == 0.80
    assert gate_pass(-0.003, s) is True
    assert gate_pass(-0.003, s - 0.01) is False      # one bootstrap draw fewer


# ---------------------------------- V7: which generation the lock must re-run


def test_within_block_correlation_is_the_mean_pairwise_one():
    # hand-computable: grand mean 0, variance 1, four ordered within-block
    # pairs. Blocks whose members move together give +1, blocks whose members
    # move opposite give -1. An estimator that centred WITHIN blocks would
    # report the same number (0) for both panels.
    pool, day = np.array(["a"] * 4), np.array([0, 0, 1, 1])
    assert within_block_correlation(np.array([1.0, 1.0, -1.0, -1.0]),
                                    pool, day) == 1.0
    assert within_block_correlation(np.array([1.0, -1.0, 1.0, -1.0]),
                                    pool, day) == -1.0


def test_within_block_correlation_separates_shocked_from_iid_panels():
    pool, day, rng = _fake_panel(n=2400, seed=8)
    r_iid = within_block_correlation(rng.normal(0.0, 0.05, size=len(pool)),
                                     pool, day)
    assert abs(r_iid) < BLOCK_CORR_THRESHOLD
    assert generation_for_correlation(r_iid) == "iid"

    pool, day, shocked = _correlated_panel(shock_sd=0.02, idio_sd=0.004, seed=9)
    r_block = within_block_correlation(shocked, pool, day)
    assert r_block > 0.5
    assert generation_for_correlation(r_block) == "block"


def test_the_correlation_threshold_must_be_exceeded_strictly():
    # "materially positive" is pre-committed as r > 0.05; landing ON the
    # threshold is not exceeding it.
    assert generation_for_correlation(BLOCK_CORR_THRESHOLD) == "iid"
    assert generation_for_correlation(float(np.nextafter(0.05, 1.0))) == "block"
    assert generation_for_correlation(-0.9) == "iid"


def test_correlation_without_a_within_block_pair_is_an_error():
    # every match on its own matchday: there is no within-block pair to
    # correlate. A silent nan would compare False against the 0.05 threshold
    # and quietly select the optimistic (iid) branch.
    with pytest.raises(ValueError, match="within-block pair"):
        within_block_correlation(np.array([0.1, -0.2, 0.3]),
                                 np.array(["a", "a", "a"]),
                                 np.array([0, 1, 2]))
