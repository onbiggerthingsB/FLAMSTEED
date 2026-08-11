"""Calibrate BOTH constants on the real design, then power the COMPLETE rule.

Three drafts failed today because a property of the whole rule was asserted after
computing a part. So nothing here reports power for the gate alone: every power
number below is P(CONFIRMED) = P(floor AND support-bar AND no-veto).

Outputs, in order:
  A. support bar b* with P(gate | true effect 0) = 0.05 on the real design
  B. heterogeneity critical value q* with P(veto | gate passed, homogeneous) = 0.10
  C. P(CONFIRMED) across K under those calibrated constants -> n*
  D. sensitivity: does the calibrated veto still fire on a genuine reversal?
"""
import sys
import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")  # oa_verdict lives here
from oa_confirmatory_power import empirical_diffs, support_vec, AC2027_BLOCKS
from wcmodel.eval.power import GATE_FLOOR

EMP = empirical_diffs()
DELTA = -EMP.mean()
CENTRED = EMP - EMP.mean()
NBOOT = 800


def _blocks(v):
    s, sz, pos = [], [], 0
    for b in AC2027_BLOCKS:
        s.append(v[pos:pos + b].sum()); sz.append(b); pos += b
    return s, sz


def one(rng, deltas, want_pools):
    """Draw a programme; return (mean, pooled_support, Q, any_positive_pool)."""
    pools = [rng.choice(CENTRED, size=36, replace=True) + d for d in deltas]
    flat = np.concatenate(pools)
    S, Z, P = [], [], []
    for i, v in enumerate(pools):
        s, z = _blocks(v); S += s; Z += z; P += [f"v{i}"] * len(s)
    sup, _ = support_vec(S, Z, P, NBOOT, rng)
    if not want_pools:
        return flat.mean(), sup, None, None
    th, se = [], []
    for i, v in enumerate(pools):
        s, z = _blocks(v)
        _, m = support_vec(s, z, [f"v{i}"] * len(s), NBOOT, rng)
        th.append(v.mean()); se.append(m.std(ddof=1))
    th = np.array(th); se = np.array(se); w = 1.0 / se ** 2
    tbar = (w * th).sum() / w.sum()
    Q = float((w * (th - tbar) ** 2).sum())
    return flat.mean(), sup, Q, bool((th > 0).any())


def calibrate_bar(K, n_sims, seed):
    """b* such that P(mean<=floor AND support>=b*) = 0.05 when the truth is 0."""
    rng = np.random.default_rng(seed)
    sups = []
    for _ in range(n_sims):
        m, s, _, _ = one(rng, [0.0] * K, False)
        sups.append(s if m <= GATE_FLOOR else -1.0)
    sups = np.array(sups)
    # the 95th percentile of the (floor-censored) support distribution
    return float(np.quantile(sups, 0.95))


def calibrate_q(K, bar, n_sims, seed, target=0.10):
    """q* such that P(Q>=q* | gate passed) = target under HOMOGENEOUS truth."""
    rng = np.random.default_rng(seed)
    qs = []
    for _ in range(n_sims):
        m, s, Q, anypos = one(rng, [-DELTA] * K, True)
        if m <= GATE_FLOOR and s >= bar:
            qs.append(Q if anypos else -1.0)
    if not qs:
        return float("inf"), 0
    return float(np.quantile(np.array(qs), 1 - target)), len(qs)


def confirmed_power(K, bar, qstar, deltas, n_sims, seed):
    rng = np.random.default_rng(seed)
    hits = fires = gates = 0
    for _ in range(n_sims):
        m, s, Q, anypos = one(rng, deltas, True)
        if m > GATE_FLOOR or s < bar:
            continue
        gates += 1
        veto = (Q >= qstar) and anypos
        fires += veto
        hits += (not veto)
    return hits / n_sims, gates / n_sims, fires / max(gates, 1)


if __name__ == "__main__":
    print(f"delta={DELTA:.6f}  floor={GATE_FLOOR}  B={NBOOT}\n")

    print("A. Support bar calibrated for 5% type-I on the real design")
    bars = {}
    for K in (8, 10, 12):
        b = calibrate_bar(K, 4000, 1000 + K)
        bars[K] = b
        print(f"   K={K:2d} (n={36*K:3d})  b* = {b:.4f}   (nominal 0.95)")

    print("\nB. Heterogeneity critical value for a 10% veto rate on noise")
    qs = {}
    for K in (8, 10, 12):
        q, ng = calibrate_q(K, bars[K], 3000, 2000 + K)
        qs[K] = q
        print(f"   K={K:2d}  q* = {q:7.3f}  (chi2(K-1) nominal 10% = "
              f"{__import__('scipy.stats', fromlist=['chi2']).chi2.ppf(0.90, K-1):.3f})"
              f"   [{ng} gate-passing sims]")

    print("\nC. P(CONFIRMED) — the COMPLETE rule, homogeneous truth at delta")
    print(f"   {'K':>3} {'n':>5} {'gate':>7} {'veto|gate':>10} {'CONFIRMED':>10}")
    for K in (8, 10, 12):
        p, g, f = confirmed_power(K, bars[K], qs[K], [-DELTA] * K, 3000, 3000 + K)
        print(f"   {K:3d} {36*K:5d} {g:7.3f} {f:10.3f} {p:10.3f}")

    print("\nD. Does the calibrated veto still catch a genuine reversal?")
    print(f"   {'K':>3} {'scenario':>26} {'veto fires':>11}")
    for K in (8, 12):
        for lab, ds in (("one pool +1x", [-DELTA]*(K-1) + [+DELTA]),
                        ("one pool +3x", [-DELTA]*(K-1) + [+3*DELTA])):
            _, _, f = confirmed_power(K, bars[K], qs[K], ds, 2000, 4000 + K)
            print(f"   {K:3d} {lab:>26} {f:11.3f}")
