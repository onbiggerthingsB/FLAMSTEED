# External deep-research: what improves international-tournament forecast accuracy (2026-07-02, v2)

Multi-agent research run (`wf_ace751ad-6e0`, completed in two passes — the
first starved by a credit outage, resumed from cache after top-up): 5 search
angles → **20 primary sources deep-read → 98 claims extracted → 25
adversarially verified (3-vote; 22 confirmed, 3 refuted) → 8 synthesized
findings.** Full artifact with per-claim votes in the workflow transcript.

## The blunt headline (verified, multi-source, now quantified tightly)

**De-vigged bookmaker odds are the effective accuracy ceiling.** Best
published statistical models roughly TIE them (±0.001-0.003 RPS/Brier), and
more often lose: Peeters 2018 (961 internationals — the largest sample in the
set): odds Brier 0.1556 vs best covariate model 0.1584 (p=0.0495), odds win
every Brier-decomposition component. Robberechts & Davis: 2018-WC
out-of-sample, bookmakers beat the deployed Elo+ODM logit (RPS 0.1976 vs
0.2072). The rare model-over-odds results are razor-thin and carry tuning
leakage.

## Ranked improvement menu (vs OUR system)

1. **Market-odds integration** — two concrete, replicable recipes:
   - **(a) Stacking** (Groll/Zeileis lineage): odds enter as a dominant
     covariate/input to a blender; LASSO picks odds FIRST of 18 covariates;
     odds subsume the host effect.
   - **(b) Likelihood-level anchoring** (Egidi, Pauli & Torelli): each team's
     Poisson goal rate = a convex combination of the historical-data rate and
     a bookmaker-implied rate (recovered by inverting 1X2 odds through the
     Skellam distribution), mixing weight learned with a Beta prior.
     **Directly transplantable to our PyMC Dixon-Coles** — this is the
     engineering blueprint for a prior/likelihood-level version of our Elo
     anchor, with odds instead of Elo. Caveat: validated on CLUB data;
     transfer to internationals is assumed, not measured (open question #1:
     (a) vs (b) has NO published head-to-head — we can be first).
   - Expected gain: closes most of the model→odds gap (~0.002-0.010
     RPS/Brier for unanchored models); does not exceed the market.
2. **Transfermarkt squad market value** — now with measured numbers: probit
   on log squad value beat an Elo probit **Brier 0.1578 vs 0.1613 on 592
   held-out non-friendly internationals** (Peeters; FIFA-rank probit 0.1645),
   with residual signal beyond odds. Two caveats that shrink it for us: the
   losing benchmark was a NAIVE Elo probit (not a tuned Elo-anchored DC), and
   Transfermarkt's valuation methodology changed post-2021 (effect sizes are
   2008-2014 vintage).
3. **Shin de-vig (cheap sub-lever)** — when consuming odds, Shin-style de-vig
   beats basic inverse-odds normalization by ~0.002-0.004 log-loss (5
   bookmakers tested; preprint-grade evidence, likely in-sample). One-day
   check of our existing de-vig module when the odds-blending work starts.
4. **Elo ordered-logit 1X2 head as an ensemble cross-check (cheap
   structural)** — on 2002-2014 WCs with IDENTICAL Elo inputs, a result-based
   ordered logit beat the goal-based bivariate Poisson's implied 1X2 (RPS
   0.1860 vs 0.1866, log-loss 0.9375 vs 1.0045). Candidate: average/cross-check
   our DC 1X2 with an Elo ordered logit — near-zero cost, uses data we have.
   (Context: our own pooled-185 RPS is 0.1896 — same ballpark, different pool.)

## Verified DON'T-DOs (now stronger than v1)

- **Rating-system swaps**: no alternative rating has demonstrated an edge over
  tuned goal-difference-aware Elo as a prior anchor on internationals.
- **Complexity for its own sake measurably HURTS on small samples**: Elo+ODM
  augmentation scored WORSE than Elo alone (RPS 0.1878 vs 0.1860); a
  16-feature RF *including odds* lost to a plain Elo ordered logit. The
  field's best group deployed their SECOND-simplest model for this reason.
- Demographics (GDP/population), betting-ROI-as-accuracy-evidence: unchanged
  from v1.

## The formerly-starved angles — now a real (negative) answer

The resume pass searched structural variants (time-decay schedules, copulas,
Koopman & Lit state-space dynamics, zero-inflation) and tournament effects
(rest days, dead rubbers, knockout draw shifts, ET/pens) properly this time:
**no claim on any of them survived adversarial verification** — the
literature simply lacks measured international-tournament evidence for these
levers. This is no longer a coverage gap; it is a finding: nobody has shown
these matter on internationals. They stay off the menu absent new evidence.

## Method discipline (reinforced)

Samples are 64-250 matches everywhere, essentially nothing is
significance-tested, and the 2018-WC out-of-sample run REVERSED the 2002-2014
backtest ordering — near-tied method rankings are unstable. Our prereg'd
paired-test discipline is the difference between measuring and guessing.

## Post-tournament experiment program (updated)

1. Odds integration head-to-head: Egidi-style likelihood anchoring vs
   stacking, on the 185-pool + full 2026 (~104 matches) — no published
   comparison exists; we'd be first.
2. Shin de-vig check inside our odds path (sub-experiment of #1).
3. Transfermarkt ablation ON TOP OF the tuned Elo anchor (answers whether
   Peeters' gain survives a real baseline + post-2021 TM data).
4. Elo ordered-logit ensemble cross-check (cheapest; can piggyback on #1's
   eval harness).
