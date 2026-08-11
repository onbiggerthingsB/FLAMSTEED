"""Design a multiplicity-controlled sign-flip veto, and check it still WORKS.

The sealed veto fires iff any pool has mean > 0 AND opposite_support >= 0.60
(oa_analysis_spec.md:203-227). At K=3 pools it fires on 13% of numeric passes;
at K=8, 62%; at K=10, 73% — because with enough pools one is noisy-positive by
chance. It is a family of K tests with no multiplicity control.

PROPOSED: keep every other property (mean > 0 strict, PASS-only downgrade,
zero-block pools skipped) and replace the fixed 0.60 with a Bonferroni bound on
the per-pool opposite-direction p-value at family-wise veto rate alpha_v:

    fire iff  mean_pool > 0  AND  (1 - opposite_support) <= alpha_v / K
    i.e.      opposite_support >= 1 - alpha_v / K

TWO THINGS MUST BOTH HOLD, and a rule that only does the first is useless:
  (1) it must stop firing on NOISE (restore power under homogeneity);
  (2) it must still FIRE on a genuinely reversed pool (do its actual job).
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


def _pool_blocks(v):
    s, sz, pos = [], [], 0
    for b in AC2027_BLOCKS:
        s.append(v[pos:pos + b].sum()); sz.append(b); pos += b
    return s, sz


def trial(rng, deltas, bar, n_boot, alpha_v):
    """One simulated programme. deltas: per-pool TRUE mean effect (signed).

    Returns (numeric_gate_passed, veto_sealed, veto_bonferroni).
    """
    K = len(deltas)
    pools = [rng.choice(CENTRED, size=36, replace=True) + d for d in deltas]
    flat = np.concatenate(pools)
    if flat.mean() > GATE_FLOOR:
        return False, False, False

    sums, sizes, pob = [], [], []
    for i, v in enumerate(pools):
        s, sz = _pool_blocks(v)
        sums += s; sizes += sz; pob += [f"v{i}"] * len(s)
    sup, _ = support_vec(sums, sizes, pob, n_boot, rng)
    if sup < bar:
        return False, False, False

    sealed = bonf = False
    thresh = 1.0 - alpha_v / K
    for i, v in enumerate(pools):
        if v.mean() <= 0:
            continue
        s, sz = _pool_blocks(v)
        _, means = support_vec(s, sz, [f"v{i}"] * len(s), n_boot, rng)
        opp = float((means > 0).mean())
        if opp >= 0.60:
            sealed = True
        if opp >= thresh:
            bonf = True
    return True, sealed, bonf


def run(deltas, bar=0.95, alpha_v=0.10, n_sims=2000, n_boot=800, seed=11):
    rng = np.random.default_rng(seed)
    g = s_conf = b_conf = s_veto = b_veto = 0
    for _ in range(n_sims):
        ok, sv, bv = trial(rng, deltas, bar, n_boot, alpha_v)
        if not ok:
            continue
        g += 1
        s_veto += sv; b_veto += bv
        s_conf += (not sv); b_conf += (not bv)
    return dict(gate=g / n_sims, sealed_confirm=s_conf / n_sims,
                bonf_confirm=b_conf / n_sims,
                sealed_vetorate=s_veto / max(g, 1),
                bonf_vetorate=b_veto / max(g, 1))


if __name__ == "__main__":
    print(f"delta_dev = {DELTA:.6f}\n")

    print("(1) HOMOGENEOUS truth — every pool really is -delta. The veto SHOULD")
    print("    almost never fire; firing here is pure noise and costs power.")
    print(f"    {'K':>3} {'n':>5} {'gate':>7} {'sealed veto':>12} {'bonf veto':>10}"
          f" {'sealed CONF':>12} {'bonf CONF':>10}")
    for K in (3, 5, 8, 10):
        r = run([-DELTA] * K, alpha_v=0.10)
        print(f"    {K:3d} {36*K:5d} {r['gate']:7.3f} {r['sealed_vetorate']:12.3f}"
              f" {r['bonf_vetorate']:10.3f} {r['sealed_confirm']:12.3f}"
              f" {r['bonf_confirm']:10.3f}")

    print("\n(2) ONE POOL GENUINELY REVERSED — K-1 pools at -delta, one at +delta.")
    print("    The veto MUST fire. A rule that only restores power is useless.")
    print(f"    {'K':>3} {'sealed fires':>13} {'bonf fires':>11}")
    for K in (3, 5, 8):
        r = run([-DELTA] * (K - 1) + [+DELTA], alpha_v=0.10)
        print(f"    {K:3d} {r['sealed_vetorate']:13.3f} {r['bonf_vetorate']:11.3f}")

    print("\n(2b) ONE POOL STRONGLY REVERSED (+3x delta) — must fire near-certainly.")
    print(f"    {'K':>3} {'sealed fires':>13} {'bonf fires':>11}")
    for K in (3, 8):
        r = run([-DELTA] * (K - 1) + [+3 * DELTA], alpha_v=0.10)
        print(f"    {K:3d} {r['sealed_vetorate']:13.3f} {r['bonf_vetorate']:11.3f}")

    print("\n(3) alpha_v sensitivity at K=8, homogeneous truth:")
    print(f"    {'alpha_v':>8} {'bonf veto rate':>15} {'CONFIRMED power':>16}")
    for av in (0.05, 0.10, 0.20, 0.40):
        r = run([-DELTA] * 8, alpha_v=av)
        print(f"    {av:8.2f} {r['bonf_vetorate']:15.3f} {r['bonf_confirm']:16.3f}")
