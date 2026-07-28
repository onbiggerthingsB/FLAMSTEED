#!/usr/bin/env python
"""OA MDE analysis (prereg input; spec OA-5 / finding 7). Reads the July
B-lever per-match JSONs (EXISTING results — no new scoring), builds the
empirical noise model from the k=0.5 vs k=0.6 paired diffs, and reports gate
power across candidate effects. Deterministic (seed 0)."""
import json
from pathlib import Path

import numpy as np

from wcmodel.eval.power import mde, simulate_power_detail

A = json.load(open("reports/bk_levers/bk_rps_k0.5.json"))
B = json.load(open("reports/bk_levers/bk_rps_k0.6.json"))
keys = sorted(set(A) & set(B))
assert len(keys) == 185, f"expected the 185-pool, got {len(keys)}"
noise = np.array([A[k]["rps"] - B[k]["rps"] for k in keys])
pool = np.array([k.split("|")[0] for k in keys])
day = np.array([k.split("|")[1] for k in keys])
# key schema is pool|date|home|away; a pool/day swap would stratify by matchday
# and block by pool — inverting the estimator with both arrays still length 185,
# so no length check downstream can catch it.
assert set(pool) == {"wc2022", "euro2024", "wc2026"}, (
    f"unexpected pool labels {sorted(set(pool))} — expected key schema "
    "pool|date|home|away")

FLOOR, SUPPORT_REQ = 0.002, 0.8
TARGET = 0.80                  # power a delta needs to count as detectable
BAND = (0.002, 0.004)          # literature-plausible per-match RPS gain

rows, details = [], []
for delta in (0.000, 0.001, 0.002, 0.003, 0.004, 0.006, 0.010):
    det = simulate_power_detail(noise, pool, day, delta=delta, floor=FLOOR,
                                support_req=SUPPORT_REQ, n_sims=400,
                                n_boot=1000, seed=0)
    rows.append((delta, det.power))
    details.append(det)
    print(f"delta={delta:.3f}  power={det.power:.2f}  "
          f"floor_pass={det.floor_pass}  support_reject={det.support_reject}  "
          f"min_support={det.min_support:.3f}")

m = mde(rows, target=TARGET)
by_delta = dict(rows)
assert set(BAND) <= set(by_delta), "band endpoints must be in the delta grid"
floor_pass = sum(d.floor_pass for d in details)
support_reject = sum(d.support_reject for d in details)
min_support = float(np.nanmin([d.min_support for d in details]))

lo, hi = BAND
if m is None:
    reading = (f"no delta in the grid reaches power {TARGET:.2f}, so the pool "
               "cannot resolve the literature-plausible band at all — the "
               "prereg verdict for any outcome is DIRECTIONAL-ONLY.")
elif m > hi:
    reading = (f"the MDE ({m:.3f}) sits ABOVE the literature-plausible "
               f"{lo:.3f}-{hi:.3f} band, so the whole band is undetectable at "
               "n=185: the development verdict is DIRECTIONAL-ONLY and the "
               "prereg must say so.")
elif m <= lo:
    reading = (f"the MDE ({m:.3f}) sits at or BELOW the literature-plausible "
               f"{lo:.3f}-{hi:.3f} band, so the whole band is detectable at "
               "n=185 and a gate FAIL is genuine evidence against it.")
else:
    reading = (f"the MDE ({m:.3f}) sits INSIDE the literature-plausible "
               f"{lo:.3f}-{hi:.3f} band, not below it, so the pool resolves the "
               f"top of the band but not the bottom: power is "
               f"{by_delta[hi]:.2f} at delta={hi:.3f}, {by_delta[m]:.2f} at "
               f"{m:.3f}, and {by_delta[lo]:.2f} at {lo:.3f} — a coin flip. "
               "Pre-committed consequence: a gate FAIL is evidence against "
               f"effects >= ~{hi:.3f} but NOT against a true {lo:.3f} effect, "
               "so a FAIL is DIRECTIONAL-ONLY / inconclusive rather than 'no "
               "effect' (spec: 'inconclusive' is a permitted outcome).")

out = Path("reports/oa_mde.md")
lines = ["# OA MDE analysis (2026-07-28, seed 0)", "",
         f"n=185; noise model: empirical k0.5-k0.6 paired diffs "
         f"(sd={noise.std():.5f}); gate: mean<=-0.002 AND support>=0.80 "
         "(block bootstrap, pool x matchday) — at this n the floor is the "
         "binding half, so the table below is the power of the floor alone "
         "(see 'Binding constraint').", "",
         "| true delta | power |", "|---|---|"]
lines += [f"| {d:.3f} | {p:.2f} |" for d, p in rows]
lines += ["", f"MDE (smallest delta with power >= {TARGET:.2f}): "
          + ("none in this grid" if m is None else f"{m:.3f}") + ".", "",
          "Common random numbers: every row above is simulated from the same "
          "seed, and each simulation draws its panel BEFORE the floor is "
          "tested, so simulation s at one delta is simulation s at any other "
          "delta shifted by the delta difference — same resampled noise, same "
          "bootstrap block draws. Floor-passing and support are therefore both "
          "nested across the grid, and the curve is monotone BY CONSTRUCTION. "
          "That is deliberate variance reduction (delta-to-delta comparisons "
          "carry no Monte-Carlo noise), but it makes the monotonicity "
          "arithmetic rather than a check: it would come out just as smooth if "
          "the machinery were wrong. Task 7's prereg must not cite the shape "
          "of this curve as evidence the machinery works — that evidence is "
          "tests/eval/test_power.py.", "",
          f"Binding constraint: the mean<=-{FLOOR:.3f} floor, NOT the support "
          f"requirement. Across every delta above, {floor_pass} simulated "
          f"panels cleared the floor and {support_reject} of them were then "
          f"rejected by support>={SUPPORT_REQ:.2f}; the smallest support among "
          f"floor-passers was {min_support:.3f}, so support_req would have to "
          f"exceed {min_support:.3f} before it rejected a single one. "
          "support>=0.80 only asks that the panel mean sit ~0.84 bootstrap "
          "standard errors below zero, which at n=185 the floor already "
          "implies with room to spare. Every power number in the table is "
          "therefore the power of the floor alone, and Task 7's prereg must "
          "state that at this n the support requirement is a sign/robustness "
          "check, not a second binding hurdle.", "",
          f"Reading: the smallest delta with power >= {TARGET:.2f} is the MDE. "
          "Here " + reading]
out.write_text("\n".join(lines) + "\n")
print(f"wrote {out}")
