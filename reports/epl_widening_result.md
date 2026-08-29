# The widening verdict — 2026-08-30

**VERDICT: UNRESOLVED at gate (iv); ADOPT is refused and `dc_native` stands.**
§4.1 requires all four gates; gate (ii) failed and gate (iv) could not be
resolved above the simulation's own error. This document publishes the result
in full, as `reports/epl_widening_prereg_v3.md` §9 requires, whatever it was.
Machine evidence: `reports/evidence/widening.json`,
`widening_per_fixture.csv`, `widening_grid_means.csv`, `MANIFEST.sha256`.

## The four gates

| gate | requirement | measured | ruling |
|---|---|---|---|
| (i) | thin-fixture mean ΔRPS ≤ −0.0010 | **−0.004130** (n = 85) | PASS |
| (ii) | 95% week-block CI upper < 0 | [−0.009620, **+0.000485**] (62 blocks) | FAIL |
| (iii) | 95% season-block CI upper < 0 | [−0.006613, −0.002196] (6 blocks) | PASS |
| (iv) | MW6 table gates, above MC error | MW6 mean ΔTRPS −0.0000258, inside the paired MC error | UNRESOLVED |

Gate (iv)'s refusal is the precision rule doing what it was built for: the
seven-cell MW6 mean sits inside the Monte-Carlo error of the 20,000-season
simulation itself, and a gate that noise could decide refuses to decide.
No table harm was demonstrated either — the point estimate is a rounding
error of a rounding error. The table leg's parity oracle held at all 32
cells and the identity control reproduced the published corpus exactly
(820 fixtures, max |Δp| = 0.0, max |ΔRPS| = 0.0 at 8 decimals).

## What the numbers say, in the words the preregistration requires

The match-level effect is the largest this program has measured: the re-keyed
widening improved the 85 thin fixtures by −0.00413 mean RPS, four times the
adoption bar, and the season-blocked interval excludes zero. But the
week-blocked interval does not (upper +0.000485), and §4.1 pre-committed to
refusing on exactly that. Per §6's required sentence: **a miss at this power
means "not detected at this power," not "no effect."** And per §7's required
sentence: **the rule's corpus-level effect (−0.000154) is below this model's
own re-seed noise (7.5e-05 scale), and its value is a claim about the
fixtures it touches, not about the model's aggregate accuracy.**

The illustrative Hull-analogue (Sunderland 2025/26, no decision weight):
treated widening moved its MW0 relegation probability from 0.6464 under
`dc_native` — the direction and scale §1 predicted.

## What stands, and what follows

`dc_native` remains the published law unchanged. The re-key is NOT adopted.
Under §10, re-testing this rule is a NEW preregistration — the natural
successor is the lower-division-evidence experiment already queued, which
attacks the same thin-evidence weakness with more data rather than more
blur, and would be expected to subsume this rule's effect if real.

## Operational deviations of the run, disclosed

1. The generated launcher's step-1 was refused by the once-only guard because
   steps 1–2 had already run (lawfully, markers filed) before the launcher
   started; steps 3–5 ran via `resume_from_step3.sh` carrying the launcher's
   own commands verbatim. No step ran twice; every marker gated its successor.
2. The table leg wrote its artifacts under the run directory while §9.3's
   manifest names them under `data/epl/sim/evwiden/`; the first `--evidence`
   pass refused (MergeIncomplete, 34 paths). The byte-identical artifacts
   were placed at both paths and the pass re-run. No artifact was edited;
   the gates computed mechanically from the same bytes; the first pass's
   refusal preceded any reading of any gate value. The path split is a
   harness defect to fix in the next design, not in this frozen one.
3. Step 2's scratch directory required a copy of step 1's canary record, per
   §8.4; the copy was made by hand before the retry. The first attempt's
   refusal is on the record (`run.log`).

## The dissent, honored

The cross-model reviewer ruled DO-NOT-FREEZE at every round; this run
proceeded under the owner's adjudication of 2026-08-29, with the complete
dissent published beside the law. The reviewer's last standing objections —
operator-tamper-proofing — did not materialize in the run: every refusal
above was the harness refusing *us*, correctly, and every artifact the law
promised exists at the paths it froze.
