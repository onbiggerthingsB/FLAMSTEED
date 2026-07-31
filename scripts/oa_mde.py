#!/usr/bin/env python
"""OA MDE analysis (prereg input; spec OA-5 / finding 7). Reads the July
B-lever per-match JSONs (EXISTING results — no new scoring), builds the
empirical noise model from the k=0.5 vs k=0.6 paired diffs, and reports gate
power across candidate effects. MDE = floor + z*sd(noise)/sqrt(n), so every
headline number is a joint property of n AND the chosen contrast — each other
arm scored on the same 185 pool is re-run as a sensitivity block.
Deterministic (seed 0)."""
# No `from __future__ import annotations`: this module is loaded by PATH in
# tests (scripts/ is not on sys.path), and stringified annotations make
# @dataclass resolve them through sys.modules, which a path-load leaves empty.
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wcmodel.eval.power import mde, simulate_power_detail

LEVERS = Path("reports/bk_levers")   # cwd-relative: run from the repo root
OUT = Path("reports/oa_mde.md")

DELTAS = (0.000, 0.001, 0.002, 0.003, 0.004, 0.006, 0.010)
FLOOR, SUPPORT_REQ = 0.002, 0.8
N_SIMS, N_BOOT, SEED = 400, 1000, 0
TARGET = 0.80                  # power a delta needs to count as detectable
BAND = (0.002, 0.004)          # literature-plausible per-match RPS gain
BASE = "k0.6"                  # incumbent; every contrast is arm minus k0.6
HEADLINE = "k0.5"              # shipped noise model (plan Task 1)
# every other arm scored on this same 185 pool (reports/bk_levers_2026-07-02.md)
ALTS = ("k0.0", "k0.4", "k0.7", "k0.8", "nuts_k0.6")


@dataclass(frozen=True)
class Contrast:
    """One noise model — an arm's paired per-match diffs vs the incumbent, and
    what the gate can detect under it. The count fields are grid-wide:
    floor_pass/support_reject summed and min_support minimised over DELTAS."""
    label: str
    sd: float
    mde_value: float | None
    power_null: float
    power_max: float
    floor_pass: int
    support_reject: int
    min_support: float


def _load(arm: str) -> dict:
    with open(LEVERS / f"bk_rps_{arm}.json") as fh:
        return json.load(fh)


def paired_diffs(arm: dict, base: dict):
    """Per-match (arm - base) RPS diffs plus the pool/matchday block labels."""
    keys = sorted(set(arm) & set(base))
    assert len(keys) == 185, f"expected the 185-pool, got {len(keys)}"
    diffs = np.array([arm[k]["rps"] - base[k]["rps"] for k in keys])
    pool = np.array([k.split("|")[0] for k in keys])
    day = np.array([k.split("|")[1] for k in keys])
    # key schema is pool|date|home|away; a pool/day swap would stratify by matchday
    # and block by pool — inverting the estimator with both arrays still length 185,
    # so no length check downstream can catch it.
    assert set(pool) == {"wc2022", "euro2024", "wc2026"}, (
        f"unexpected pool labels {sorted(set(pool))} — expected key schema "
        "pool|date|home|away")
    return diffs, pool, day


def run_grid(noise, pool, day, *, label: str):
    """The delta grid under one noise model. Returns (rows, Contrast)."""
    rows, details = [], []
    for delta in DELTAS:
        det = simulate_power_detail(noise, pool, day, delta=delta, floor=FLOOR,
                                    support_req=SUPPORT_REQ, n_sims=N_SIMS,
                                    n_boot=N_BOOT, seed=SEED)
        rows.append((delta, det.power))
        details.append(det)
        # 3dp, not 2: a contrast can peak at 0.7975 — which a 2dp print rounds
        # to the 0.80 TARGET while mde() correctly returns None.
        print(f"[{label}] delta={delta:.3f}  power={det.power:.3f}  "
              f"floor_pass={det.floor_pass}  support_reject={det.support_reject}"
              f"  min_support={det.min_support:.3f}", flush=True)
    return rows, Contrast(
        label=label, sd=float(noise.std()), mde_value=mde(rows, target=TARGET),
        power_null=dict(rows)[DELTAS[0]], power_max=max(p for _, p in rows),
        floor_pass=sum(d.floor_pass for d in details),
        support_reject=sum(d.support_reject for d in details),
        min_support=float(np.nanmin([d.min_support for d in details])))


def _fmt_mde(m: float | None) -> str:
    return "none in this grid" if m is None else f"{m:.3f}"


def _reading(headline: Contrast, by_delta: dict) -> str:
    lo, hi = BAND
    cond = (f"n=185 AND sd(noise)={headline.sd:.5f} (the {headline.label}-vs-"
            f"{BASE} contrast)")
    m = headline.mde_value
    if m is None:
        return (f"no delta in the grid reaches power {TARGET:.2f} under {cond}, "
                "so this noise model cannot resolve the literature-plausible "
                f"{lo:.3f}-{hi:.3f} band at all — the prereg verdict for any "
                "outcome is DIRECTIONAL-ONLY.")
    if m > hi:
        return (f"the MDE ({m:.3f}) sits ABOVE the literature-plausible "
                f"{lo:.3f}-{hi:.3f} band, so the whole band is undetectable "
                f"under {cond}: the development verdict is DIRECTIONAL-ONLY and "
                "the prereg must say so.")
    if m <= lo:
        return (f"the MDE ({m:.3f}) sits at or BELOW the literature-plausible "
                f"{lo:.3f}-{hi:.3f} band, so the whole band is detectable under "
                f"{cond} and a gate FAIL is genuine evidence against it.")
    return (f"the MDE ({m:.3f}) sits INSIDE the literature-plausible "
            f"{lo:.3f}-{hi:.3f} band, not below it, so the pool resolves the "
            f"top of the band but not the bottom: power is {by_delta[hi]:.2f} "
            f"at delta={hi:.3f}, {by_delta[m]:.2f} at {m:.3f}, and "
            f"{by_delta[lo]:.2f} at {lo:.3f} — a coin flip. Pre-committed "
            f"consequence, CONDITIONAL on {cond}: a gate FAIL is evidence "
            f"against effects >= ~{hi:.3f} but NOT against a true {lo:.3f} "
            "effect, so a FAIL is DIRECTIONAL-ONLY / inconclusive rather than "
            "'no effect' (spec: 'inconclusive' is a permitted outcome). Every "
            "number in this paragraph moves with sd(noise), so Task 7's prereg "
            "must carry the conditioning and not just the numbers — see "
            "'Noise-model sensitivity' for what they become under the other "
            "arms measured on this same pool.")


def assemble_report(rows, contrasts, *, headline: Contrast) -> str:
    """Pure: markdown for one headline grid plus its noise-model sensitivity."""
    by_delta = dict(rows)
    assert set(BAND) <= set(by_delta), "band endpoints must be in the delta grid"
    others = [c for c in contrasts if c.label != headline.label]
    binders = [c for c in others if c.support_reject > 0]
    dead = [c for c in others if c.mde_value is None]
    order = sorted(contrasts, key=lambda c: c.sd)
    rank = [c.label for c in order].index(headline.label) + 1
    widest = order[-1]

    if headline.support_reject == 0:
        binding = ("the floor is the binding half, so the table below is the "
                   "power of the floor alone (see 'Binding constraint')")
    else:
        binding = (f"BOTH halves of the gate bind — support>={SUPPORT_REQ:.2f} "
                   f"rejected {headline.support_reject} floor-passers (see "
                   "'Binding constraint')")

    lines = [
        "# OA MDE analysis (2026-07-28, seed 0)", "",
        f"n=185; noise model: empirical {headline.label}-{BASE} paired diffs "
        f"(sd={headline.sd:.5f}); gate: mean<=-{FLOOR:.3f} AND "
        f"support>={SUPPORT_REQ:.2f} (block bootstrap, pool x matchday).", "",
        f"SCOPE: every number below is a joint property of n=185 AND "
        f"sd(noise)={headline.sd:.5f}, NOT of n alone. MDE = floor + "
        "z*sd(noise)/sqrt(n), and sd(noise) here is a CHOSEN arm contrast "
        "rather than a measured constant of the pool, so the MDE, the "
        "false-positive rate, and which half of the gate binds all move when "
        "the contrast changes — 'Noise-model sensitivity' below re-runs the "
        f"whole grid under the other arms on this pool and shows them moving. "
        f"Under the shipped contrast {binding}.", "",
        "| true delta | power |", "|---|---|"]
    lines += [f"| {d:.3f} | {p:.2f} |" for d, p in rows]
    lines += [
        "", f"MDE (smallest delta with power >= {TARGET:.2f}): "
        f"{_fmt_mde(headline.mde_value)}.", "",
        "Common random numbers: every row above is simulated from the same "
        "seed, and each simulation draws its panel BEFORE the floor is tested, "
        "so simulation s at one delta is simulation s at any other delta "
        "shifted by the delta difference — same resampled noise, same bootstrap "
        "block draws. Floor-passing and support are therefore both nested "
        "across the grid, and the curve is monotone BY CONSTRUCTION. That is "
        "deliberate variance reduction (delta-to-delta comparisons carry no "
        "Monte-Carlo noise), but it makes the monotonicity arithmetic rather "
        "than a check: it would come out just as smooth if the machinery were "
        "wrong. Task 7's prereg must not cite the shape of this curve as "
        "evidence the machinery works — that evidence is "
        "tests/eval/test_power.py.", ""]

    # The whole paragraph — not just the SCOPE summary — must agree with which
    # half of the gate binds under THE HEADLINE; the floor-only wording below
    # is provably false the moment headline.support_reject > 0 (review round 5).
    if headline.support_reject == 0:
        if binders:
            # the TIGHTEST binder, not the widest: it bounds how little extra
            # dispersion it takes before support starts rejecting, and it does
            # not depend on the order ALTS happens to list the arms in.
            b = min(binders, key=lambda c: c.sd)
            caveat = (
                f"That is conditional on the noise model, not on n: on the more "
                f"dispersed {b.label}-vs-{BASE} contrast (sd={b.sd:.5f}, only "
                f"{b.sd / headline.sd:.1f}x the headline) measured on this SAME 185 "
                f"pool, support>={SUPPORT_REQ:.2f} DOES reject {b.support_reject} "
                f"floor-passers (min support {b.min_support:.3f}) — and it is the "
                f"tightest of {len(binders)} alternative contrasts that bind.")
        else:
            caveat = ("No alternative contrast on this pool makes support bind "
                      "either, but that is still a statement about the arms on "
                      "disk, not about n=185.")
        binding_para = (
            f"Binding constraint: the mean<=-{FLOOR:.3f} floor, NOT the support "
            f"requirement. Across every delta above, {headline.floor_pass} "
            f"simulated panels cleared the floor and {headline.support_reject} of "
            f"them were then rejected by support>={SUPPORT_REQ:.2f}; the smallest "
            f"support among floor-passers was {headline.min_support:.3f}, so "
            f"support_req would have to exceed {headline.min_support:.3f} before it "
            f"rejected a single one. support>={SUPPORT_REQ:.2f} only asks that the "
            "panel mean sit ~0.84 bootstrap standard errors below zero, which at "
            "this n and this dispersion the floor already implies with room to "
            "spare. Every power number in the table is therefore the power of the "
            f"floor alone. {caveat} Task 7's prereg must state the conditioned "
            f"form — at n=185 AND sd(noise)={headline.sd:.5f} the support "
            "requirement is a sign/robustness check rather than a second binding "
            "hurdle — not the unconditional claim.")
    else:
        binding_para = (
            f"Binding constraint: BOTH halves of the gate bind at this "
            f"configuration. Across every delta above, {headline.floor_pass} "
            f"simulated panels cleared the floor and support>={SUPPORT_REQ:.2f} "
            f"then rejected {headline.support_reject} of them (smallest support "
            f"among floor-passers {headline.min_support:.3f}, below the "
            "requirement). The power table is therefore the power of the JOINT "
            "gate, not of the floor alone. Task 7's prereg must state the "
            f"conditioned form — at n=185 AND sd(noise)={headline.sd:.5f} the "
            "support requirement IS a second binding hurdle — not the "
            "floor-only claim.")
    lines += [
        binding_para, "",
        f"Reading: the smallest delta with power >= {TARGET:.2f} is the MDE. "
        "Here " + _reading(headline, by_delta), "",
        "## Noise-model sensitivity", "",
        "Each row re-runs the WHOLE grid above with only the contrast swapped: "
        "identical 185 matches, identical block structure, same "
        f"floor/support_req/seed {SEED}/n_sims {N_SIMS}/n_boot {N_BOOT}. Every "
        "arm was scored in the July B/K sweep "
        "(reports/bk_levers_2026-07-02.md) — no new scoring was run here.", "",
        f"| contrast (vs {BASE}) | sd(noise) | MDE | power(0.000) | floor_pass "
        "| support_reject | min_support |", "|---|---|---|---|---|---|---|"]
    for c in order:
        tag = " (headline)" if c.label == headline.label else ""
        lines.append(f"| {c.label}{tag} | {c.sd:.5f} | {_fmt_mde(c.mde_value)} "
                     f"| {c.power_null:.2f} | {c.floor_pass} | "
                     f"{c.support_reject} | {c.min_support:.3f} |")

    # same config as the incumbent, only the inference backend differs, so its
    # dispersion is a floor on what ANY real arm change can look like
    nuts = next((c for c in others if c.label.startswith("nuts")), None)
    jitter = ""
    if nuts is not None:
        jitter = (
            f" Decisively, {nuts.label} vs {BASE} is the SAME configuration "
            f"with k fixed at {BASE[1:]}, differing only in inference backend "
            "(reports/bk_levers/bk_sweep.py) — pure sampler jitter — and it is "
            f"already {nuts.sd / headline.sd:.1f}x more dispersed than the "
            "headline noise model. No real arm change (least of all a "
            "prediction-time market blend, which moves forecasts far more than "
            "a 0.1 k-nudge) can plausibly be as tight, so read the headline MDE "
            "as a LOWER BOUND on the detectable effect rather than an estimate "
            "of it.")
    dead_txt = ""
    if dead:
        # peak power at 4dp: it is a multiple of 1/N_SIMS so this is exact, and
        # a peak of 0.7975 rounds at 2dp to the very TARGET it fell short of.
        dead_txt = (
            " Under " + ", ".join(f"{c.label} (sd={c.sd:.5f}, peak power "
                                  f"{c.power_max:.4f})" for c in dead)
            + f" no delta in the grid reaches power {TARGET:.2f} at all: that "
            "contrast cannot resolve the band, flipping the Reading above from "
            "a straddle to no resolution.")
    lines += [
        "", "The shipped choice is not neutral: by dispersion it ranks "
        f"{rank} of {len(contrasts)} (1 = tightest), and the widest contrast "
        f"({widest.label}) is {widest.sd / headline.sd:.1f}x more dispersed."
        + dead_txt + jitter]
    return "\n".join(lines) + "\n"


def main() -> int:
    base = _load(BASE)
    rows, headline = run_grid(*paired_diffs(_load(HEADLINE), base),
                              label=HEADLINE)
    contrasts = [headline]
    for arm in ALTS:
        contrasts.append(run_grid(*paired_diffs(_load(arm), base), label=arm)[1])
    OUT.write_text(assemble_report(rows, contrasts, headline=headline))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
