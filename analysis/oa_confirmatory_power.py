"""Decision spike: is the AC2027 confirmatory test capable of concluding anything?

Computes power for the SEALED gate (mean <= -0.002 AND support >= 0.80) under the
real block structure, for AC2027 alone and for a pooled AC2027 + AFCON design.

The bootstrap here is a vectorised re-expression of
``wcmodel.eval.power.block_bootstrap_support``; it is validated against the shipped
function before any result is reported. A power number computed with a different
resampling scheme than the one that will decide the test would be worthless.
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")  # oa_verdict lives here
from wcmodel.eval.power import block_bootstrap_support, GATE_FLOOR, GATE_SUPPORT_REQ

RNG_MASTER = 20260809

# AC2027 group stage: 36 matches over 14 matchdays (from config/tournament_ac2027.yaml)
AC2027_BLOCKS = [1, 3, 3, 2, 3, 3, 2, 3, 2, 2, 4, 2, 2, 4]


def support_vec(block_sums, block_sizes, pool_of_block, n_boot, rng):
    """Vectorised block bootstrap: resample blocks WITH replacement within each pool.

    Returns P(bootstrap mean < 0) — the same quantity block_bootstrap_support
    returns, computed without the per-draw Python loop.
    """
    block_sums = np.asarray(block_sums, float)
    block_sizes = np.asarray(block_sizes, float)
    pool_of_block = np.asarray(pool_of_block)
    tot_s = np.zeros(n_boot)
    tot_n = np.zeros(n_boot)
    for p in np.unique(pool_of_block):
        idx = np.flatnonzero(pool_of_block == p)
        k = idx.size
        pick = rng.integers(0, k, size=(n_boot, k))
        chosen = idx[pick]
        tot_s += block_sums[chosen].sum(axis=1)
        tot_n += block_sizes[chosen].sum(axis=1)
    return float(np.mean((tot_s / tot_n) < 0.0)), (tot_s / tot_n)


def validate():
    """The vectorised bootstrap must agree with the shipped one.

    Validated at SEVERAL support levels, deliberately including mid-range ones.
    A case where both sides return 1.000 agrees trivially and proves nothing —
    the first version of this check did exactly that and was worthless.
    """
    ok = True
    for tag, shift in (("low", +0.030), ("mid", +0.004), ("high", -0.030)):
        rng = np.random.default_rng(7)
        n = 40
        diffs = rng.normal(0.0, 0.07, n)
        diffs = diffs - diffs.mean() - shift        # exact sample mean = -shift
        pool = np.array(["a"] * 20 + ["b"] * 20)
        day = np.array([f"d{i//4}" for i in range(20)] * 2)
        ref = block_bootstrap_support(diffs, pool, day, n_boot=20000, seed=11)

        sums, sizes, pob = [], [], []
        for p in np.unique(pool):
            m = pool == p
            idx = np.flatnonzero(m)
            for d in np.unique(day[m]):
                sel = idx[day[m] == d]
                sums.append(diffs[sel].sum()); sizes.append(sel.size); pob.append(p)
        got, _ = support_vec(sums, sizes, pob, 20000, np.random.default_rng(11))
        good = abs(ref - got) < 0.02
        informative = 0.02 < ref < 0.98
        ok &= good
        print(f"  {tag:5} shipped={ref:.4f}  vectorised={got:.4f}  "
              f"|diff|={abs(ref-got):.4f}  {'OK' if good else 'MISMATCH'}"
              f"{'' if informative else '  (degenerate — proves nothing)'}")
    assert ok, "vectorised bootstrap disagrees — do not trust any result below"
    return True


def empirical_diffs():
    """The 217 real paired diffs from the SEALED ledger."""
    df = pd.read_parquet("data/oa_scored_ledger.parquet")
    import oa_verdict as V
    frame = df
    outcomes = V.load_outcomes(frame)
    diffs, pool, day, _ = V.paired_diffs(frame, "Eprime", outcomes)
    return np.asarray(diffs, float)


def power(block_sizes, pool_labels, emp, delta, n_sims, n_boot, bar, seed):
    """P(gate passes) when the true mean effect is -delta.

    Fixtures are drawn iid from the empirical diff distribution (the panel
    generation the lock fixes: generation='iid' at r_dev=-0.1168), then shifted
    so the population mean is exactly -delta.
    """
    rng = np.random.default_rng(seed)
    centred = emp - emp.mean()
    n = int(np.sum(block_sizes))
    passes = 0
    for s in range(n_sims):
        draw = rng.choice(centred, size=n, replace=True) - delta
        # accumulate per block
        sums, sizes, pob = [], [], []
        pos = 0
        for bsz, pl in zip(block_sizes, pool_labels):
            sums.append(draw[pos:pos + bsz].sum()); sizes.append(bsz); pob.append(pl)
            pos += bsz
        if draw.mean() > GATE_FLOOR:      # floor half of the gate
            continue
        sup, _ = support_vec(sums, sizes, pob, n_boot, rng)
        if sup >= bar:
            passes += 1
    return passes / n_sims


if __name__ == "__main__":
    print("Validating the bootstrap re-expression...")
    validate()

    emp = empirical_diffs()
    print(f"\nSealed ledger: n={emp.size}  mean={emp.mean():.6f}  "
          f"sd={emp.std(ddof=1):.6f}")
    delta_dev = -emp.mean()

    designs = {
        "AC2027 alone (n=36, 1 pool, 14 blocks)":
            (AC2027_BLOCKS, ["ac2027"] * 14),
        "AC2027 + AFCON pooled (n=72, 2 pools, 28 blocks)":
            (AC2027_BLOCKS * 2, ["ac2027"] * 14 + ["afcon"] * 14),
        "AC2027 + AFCON + a third (n=108, 3 pools)":
            (AC2027_BLOCKS * 3,
             ["ac2027"] * 14 + ["afcon"] * 14 + ["third"] * 14),
    }

    N_SIMS, N_BOOT = 2000, 2000
    print(f"\n{N_SIMS} sims x {N_BOOT} bootstrap draws, gate = "
          f"mean<={GATE_FLOOR} AND support>=bar\n")

    # AC2027 alone, swept across support bars — this resolves which bar each of
    # the reviewer's five numbers belongs to, which is where I mis-transcribed.
    bs, pl = designs["AC2027 alone (n=36, 1 pool, 14 blocks)"]
    print("AC2027 alone (n=36), by support bar:")
    print(f"  {'bar':>6} {'null FPR':>9} {'power@dev':>10}")
    for bar in (0.70, 0.80, 0.90, 0.95, 0.975):
        f = power(bs, pl, emp, 0.0, N_SIMS, N_BOOT, bar, RNG_MASTER)
        p = power(bs, pl, emp, delta_dev, N_SIMS, N_BOOT, bar, RNG_MASTER + 1)
        star = "   <-- SEALED BAR" if abs(bar - GATE_SUPPORT_REQ) < 1e-9 else ""
        print(f"  {bar:6.3f} {f:9.3f} {p:10.3f}{star}")

    print(f"\nAt the SEALED bar {GATE_SUPPORT_REQ}, by design:")
    print(f"{'design':52} {'null FPR':>9} {'power@dev':>10} {'power@.02':>10}")
    print("-" * 84)
    for name, (bs, pl) in designs.items():
        fpr = power(bs, pl, emp, 0.0, N_SIMS, N_BOOT, GATE_SUPPORT_REQ, RNG_MASTER)
        pw = power(bs, pl, emp, delta_dev, N_SIMS, N_BOOT, GATE_SUPPORT_REQ,
                   RNG_MASTER + 1)
        pw2 = power(bs, pl, emp, 0.020, N_SIMS, N_BOOT, GATE_SUPPORT_REQ,
                    RNG_MASTER + 2)
        print(f"{name:52} {fpr:9.3f} {pw:10.3f} {pw2:10.3f}")

    print(f"\n(dev effect delta = {delta_dev:.6f})")
