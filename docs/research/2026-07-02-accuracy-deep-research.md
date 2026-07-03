# External deep-research: what improves international-tournament forecast accuracy (2026-07-02)

Multi-agent research run (`wf_ace751ad-6e0`): 5 search angles → 7 primary
sources deep-read → 30 claims extracted → 25 adversarially verified (3-vote;
23 confirmed, 2 refuted). Full artifact with per-claim votes/evidence in the
workflow transcript; this file is the distilled, actionable menu. NOTE the
coverage gap at the bottom — 12 fetch agents died on a usage-credit outage,
starving angles 4-6.

## The blunt headline (verified, multi-source)

**Bookmaker odds dominate.** Pure statistical models trail market accuracy by
~1.1-1.3pp average correct-1X2 probability (~0.002-0.004 RPS) on World Cup
matches (Groll/Schauberger/Tutz 2015: 40.2/40.3% vs 41.45%; Groll et al. 2019:
bookmaker RPS 0.188 vs 0.190 best-pure-statistical on 256 WC matches). The
ONLY published method that edges the market — Groll et al.'s hybrid random
forest, RPS 0.187 vs 0.188 — does it by INGESTING odds-derived abilities.
LASSO picks odds FIRST among ~18 covariates when available; odds absorb most
other information including the host effect.

## Ranked improvement menu (vs OUR system specifically)

1. **Market-odds blending** — highest expected gain, and unusually cheap for
   us: the odds plumbing (The Odds API fetch, de-vig, PIT snapshots) already
   exists in the value-scanner subsystem; it has just never fed the FORECAST.
   Two architectures, no published head-to-head (open question #1):
   (a) prior-level anchoring (shrink attack/defense priors toward odds-implied
   strengths — same pattern as our Elo anchor, k swept on held-out data);
   (b) post-hoc stacking (logistic blend of our 1X2 probs with de-vigged
   market probs, weight fit on held-out internationals).
   Expected order: closes most of the ~0.002-0.004 RPS model-vs-market gap.
2. **Transfermarkt log market-value differences as a covariate** — the
   dominant player-level feature in the Groll/Zeileis lineage (variable
   importance #1 in the EURO-2020/WC-2022 hybrid; ahead of CL/EL player
   counts and FIFA rank; GDP/population/age ~zero after regularization).
   Caveat: no paper ablates it AGAINST an Elo-anchored goal model — its
   marginal value over our anchor is genuinely unknown (open question #2).
   PIT source: archived pre-tournament Transfermarkt squad values.
3. **Stacking layer generally** (our DC probs + market probs [+ market value]
   into a light blender) — the design pattern behind the only measured
   over-market result. Deltas ~0.003-0.005 RPS, measured on CV not fresh
   holdouts — treat as upper bounds.

## Verified DON'T-DOs (saves future effort)

- **Rating-system swaps** (Bayesian BTD, pi-ratings, official FIFA rank,
  Glicko-class): marginal, stage-dependent, often qualitative-only on
  internationals; best-in-class in Lasek et al. 2013 was a goal-difference-
  aware Elo variant — which is what we already run, with a swept anchor.
- **Demographic covariates** (GDP, population): shrink to ~zero.
- **Chasing betting-ROI results as accuracy evidence**: the WC2014 "+33%"
  value-bet returns came from models LESS accurate than the market (n=64, no
  significance test) — price-inefficiency exploitation, not forecast skill.

## Method discipline (verified, and it validates ours)

Every published delta (0.002-0.005 RPS) sits near the noise floor of a
50-200-match holdout; flagship forecasts (Zeileis 2022) publish NO accuracy
metric at all. Pre-registered paired match-level tests — our house standard —
are a first-order requirement, not a nicety.

## Coverage gaps (starved by the credit outage — NOT evidence of absence)

Angles with no surviving verified claims: structural variants (time-decay
schedules, Koopman & Lit state-space dynamics, copula dependence,
zero-inflation), tournament effects (rest days, dead rubbers, knockout draw
rates, ET/pens modeling), and competition/ensembling evidence (Kaggle WC,
Machine Learning journal challenges). Also lost: Peeters 2018 (Transfermarkt
wisdom-of-crowds, IJoF) — directly relevant to item 2. Resumable from the
workflow's cached prefix (`resumeFromRunId: wf_ace751ad-6e0`).

## Open questions the internal program should answer

1. Prior-anchoring vs post-hoc stacking of market odds — no published
   head-to-head; we can measure it ourselves on the 185-pool.
2. Ablated delta of a market-value covariate ON TOP OF the Elo anchor.
3. The starved angles above, after a resume pass.
4. Does the hybrid-RF gain survive genuinely held-out tournaments?
