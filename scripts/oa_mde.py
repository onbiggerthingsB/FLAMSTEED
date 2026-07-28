#!/usr/bin/env python
"""OA MDE analysis (prereg input; spec OA-5 / finding 7). Reads the July
B-lever per-match JSONs (EXISTING results — no new scoring), builds the
empirical noise model from the k=0.5 vs k=0.6 paired diffs, and reports gate
power across candidate effects. Deterministic (seed 0)."""
import json
from pathlib import Path

import numpy as np

from wcmodel.eval.power import simulate_power

A = json.load(open("reports/bk_levers/bk_rps_k0.5.json"))
B = json.load(open("reports/bk_levers/bk_rps_k0.6.json"))
keys = sorted(set(A) & set(B))
assert len(keys) == 185, f"expected the 185-pool, got {len(keys)}"
noise = np.array([A[k]["rps"] - B[k]["rps"] for k in keys])
pool = np.array([k.split("|")[0] for k in keys])
day = np.array([k.split("|")[1] for k in keys])

rows = []
for delta in (0.000, 0.001, 0.002, 0.003, 0.004, 0.006, 0.010):
    p = simulate_power(noise, pool, day, delta=delta, floor=0.002,
                       support_req=0.8, n_sims=400, n_boot=1000, seed=0)
    rows.append((delta, p))
    print(f"delta={delta:.3f}  power={p:.2f}")

out = Path("reports/oa_mde.md")
lines = ["# OA MDE analysis (2026-07-28, seed 0)", "",
         f"n=185; noise model: empirical k0.5-k0.6 paired diffs "
         f"(sd={noise.std():.5f}); gate: mean<=-0.002 AND support>=0.80 "
         "(block bootstrap, pool x matchday).", "",
         "| true delta | power |", "|---|---|"]
lines += [f"| {d:.3f} | {p:.2f} |" for d, p in rows]
lines += ["", "Reading: the smallest delta with power >= 0.8 is the MDE. "
          "If the literature-plausible 0.002-0.004 band sits below it, the "
          "development verdict is DIRECTIONAL-ONLY and the prereg must say "
          "so (spec: 'inconclusive' is a permitted outcome)."]
out.write_text("\n".join(lines) + "\n")
print(f"wrote {out}")
