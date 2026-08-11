"""How many fixtures does a DEFENSIBLE confirmatory test need?

The development gate (mean <= -0.002 AND support >= 0.80) is an ENTRY criterion,
not a confirmatory rule (oa_analysis_spec.md:20, oa_prereg.md:148). A confirmatory
rule needs a stated error rate. Under the sealed block bootstrap, a one-sided test
at level alpha is exactly "support >= 1 - alpha".

This asks: at each alpha, how many fixtures are needed for 80% power against the
development effect delta = 0.0102?
"""
import sys
import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")  # oa_verdict lives here
from oa_confirmatory_power import support_vec, empirical_diffs, AC2027_BLOCKS
from wcmodel.eval.power import GATE_FLOOR

TARGET_POWER = 0.80


def design(n_venues):
    """n_venues copies of a 24-team group stage: 36 fixtures / 14 matchdays each."""
    return AC2027_BLOCKS * n_venues, [f"v{i}" for i in range(n_venues)
                                      for _ in AC2027_BLOCKS]


def power_at(block_sizes, pools, emp, delta, bar, n_sims, n_boot, seed):
    rng = np.random.default_rng(seed)
    centred = emp - emp.mean()
    n = int(np.sum(block_sizes))
    hits = 0
    for _ in range(n_sims):
        draw = rng.choice(centred, size=n, replace=True) - delta
        if draw.mean() > GATE_FLOOR:
            continue
        sums, sizes, pob, pos = [], [], [], 0
        for bsz, pl in zip(block_sizes, pools):
            sums.append(draw[pos:pos + bsz].sum()); sizes.append(bsz)
            pob.append(pl); pos += bsz
        sup, _ = support_vec(sums, sizes, pob, n_boot, rng)
        if sup >= bar:
            hits += 1
    return hits / n_sims


if __name__ == "__main__":
    emp = empirical_diffs()
    delta = -emp.mean()
    sd = emp.std(ddof=1)
    print(f"empirical: n=217 mean={emp.mean():.6f} sd={sd:.6f}  delta={delta:.6f}\n")

    # Normal approximation first — cheap, and it tells us where to simulate.
    from scipy.stats import norm
    print("Normal approximation, n for 80% power (one-sided):")
    print(f"  {'alpha':>7} {'support bar':>12} {'n needed':>9} {'~group stages':>14}")
    for alpha in (0.01, 0.05, 0.10, 0.20):
        z = norm.ppf(1 - alpha) + norm.ppf(TARGET_POWER)
        n_req = (sd * z / delta) ** 2
        print(f"  {alpha:7.2f} {1-alpha:12.2f} {n_req:9.0f} {n_req/36:14.1f}")

    # Confirm with the real block bootstrap at the two candidate bars.
    print(f"\nSimulated (block bootstrap, 1000 sims x 1500 boot), power at delta={delta:.4f}:")
    print(f"  {'venues':>7} {'n':>5} {'bar 0.95':>9} {'bar 0.90':>9} {'bar 0.80':>9}")
    for v in (1, 2, 3, 6, 8):
        bs, pl = design(v)
        row = [power_at(bs, pl, emp, delta, bar, 1000, 1500, 424242 + v)
               for bar in (0.95, 0.90, 0.80)]
        print(f"  {v:7d} {36*v:5d} {row[0]:9.3f} {row[1]:9.3f} {row[2]:9.3f}")
