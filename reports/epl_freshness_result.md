# The matchday-freshness sweep — result (2026-08-26)

**WEEKLY STANDS.** The preregistered estimand — the mean paired RPS change from
moving each stale fixture's fit to its own matchday, over all 1,699 stale
fixtures of the pinned corpus — came out at **−0.000216**, 95% season-block
bootstrap CI **[−0.000463, +0.000024]**. The adoption rule
(reports/epl_freshness_prereg.md §4: Δ ≤ −0.00030 AND the CI's upper bound
below zero, both required) is not met on either leg. The live cadence stays
weekly, exactly as CADENCE_WEEKS = 1 has said since the walk.

Freshness is real and small. The staleness strata are monotone in the right
direction — one-day staleness costs nothing (+0.000015), two days −0.000166,
three or more −0.000289 — and every one of those intervals crosses zero. The
prereg pre-banned a retreat to the 3+ stratum, and the numbers show why that
ban earned its place: the tempting stratum is as unresolved as the whole.

Two figures this run corrects for the record. The 0.00153 cross-sectional
"staleness penalty" that motivated the design was never reproducible from the
pinned corpus (prereg §1.4) and the paired measurement now puts the true
effect at roughly a seventh of it. The Elo-proxy scaling of I1b (~0.0004 at
this corpus's mean staleness) also overstated it, by less.

Mechanics, for whoever re-runs this: 527 fits (20 control + 507 matchday),
canary PASS (10 pre-cutoff forecasts bit-identical under a rewritten future;
positive control moved 0.81), control PASS at exact 8-decimal equality against
the corpus (no archive drift bit), four shards all exit 0, the merge's key set
exactly the 507 preregistered fit points, run start-to-finish 22 minutes warm.
Machine-readable result: reports/epl_freshness_result.json (schema
epl-freshness-1); the full per-fixture ledger stays local under
data/epl/fit/freshness/.

Nothing else changes. No model change, no decay change, and — per §4.5 —
adoption was never the harness's call: the rule reported, and the rule's own
terms answered.
