# The EPL probe: a published null

**Branch** `epl-probe` · **2026-08-15** · 5 commits, `0aa6941` → `91ee8ee`

One page. The five detailed reports beside this one carry the workings; this is the
finding and what it costs.

---

## The question

FLAMSTEED's Bayesian Dixon-Coles scoreline model forecast all 104 matches of the
2026 World Cup. Two results discipline everything that follows, both published:

- Over the full 104-match replay the model **tied naive Elo** (RPS 0.15609 vs
  0.15565 — Elo marginally ahead).
- Against de-vigged market prices the **market beat the model** by ~0.010 mean RPS
  over 217 fixtures. That programme was closed 2026-08-12 with no confirmatory run.

Dixon & Coles (1997) was fitted to *English league* data, not international
football. So the probe asked one question: **does this architecture beat naive Elo
in its native habitat?**

## The bar, measured in-repo

2,870 EPL matches, our own computation, agreeing with published research:

| Forecaster | RPS |
|---|---|
| De-vigged Pinnacle close | 0.19432 |
| Walk-forward Elo + ordered logit | 0.20111 |
| Base rate | 0.23439 |

**The entire gap between naive Elo and the market is 0.0068.** That is the whole
field a model can compete for.

## The answer

**Run 1** — 2019/20–2024/25, n=2,280, 212 fits, zero unpriceable fixtures:

| | RPS |
|---|---|
| Dixon-Coles | 0.20194 |
| Elo | 0.20311 |

ΔRPS = **−0.00117**, 95% CI **[−0.00281, +0.00047]**. Crosses zero. The
preregistered rule FAILED. The sign nonetheless *flipped* versus the World Cup,
where DC was worse than Elo (+0.00044).

**Improvements** — four levers, config-gated, tuned on 2014/15–2018/19 only,
47 runs including 25+ multi-lever combinations:

| Lever | Best tuning effect | Verdict |
|---|---|---|
| Decay half-life (dynamic strength) | +0.000022 → +0.001774 | **Wrong sign, monotone** |
| Congestion / rest differential | +0.000102 | Wrong sign, inside ADVI noise |
| Faster-adapting home term | +0.000078 | Wrong sign, precisely measured |
| Transfer-window variance inflation | −0.000055 | Right sign, 5.5% of threshold |

**Nothing was adopted.** The final stack is byte-identical to the frozen config.

Best single lever −0.000055; **best combination anywhere in the grid −0.000065**.
Stacking bought 0.00001. Three-lever combinations were *worse* than control.
Interactions are real and negligible.

**Fresh holdout** — 2025/26, n=380, never scored before, touched once:

| | RPS |
|---|---|
| Dixon-Coles | 0.20945 |
| Elo | 0.20848 |

ΔRPS = **+0.00097** — the model is *worse* than Elo here. CI [−0.00264, +0.00447],
and the holdout was preregistered as **unable to resolve** an effect this size
(MDE ≈ 0.0057 against an effect of ~0.001–0.002).

## What it means

Run 1 says −0.0012. The fresh window says +0.0010. They **straddle zero**, both CIs
contain it, and every attempt to improve the model failed on data it had never seen.

**On the Premier League, the Bayesian Dixon-Coles architecture is indistinguishable
from a naive Elo rating.** Run 1's apparent edge is best read as noise.

Two consequences worth stating plainly:

1. **The literature's top lever did not survive contact.** Both research streams
   named time-varying team strength as the biggest available gain (~0.001).
   Shortening the model's memory made things monotonically *worse* here:
   270d +0.000022, 180d +0.000565, 120d +0.001774. Long memory is doing real work
   in this league.
2. **You cannot prove the effect either way at this sample size.** With the realised
   paired sd (0.0399), establishing an effect of 0.0012 at 80% power needs ~9,100
   matches — about 24 EPL seasons. Six exist.

## What was verified, and what was not

Verified independently, by a scorer written without reading `epl/score.py`:

- Run 1: RPS 0.20194, log loss 0.97548, n=2,280 — exact to 5 dp
- Holdout: RPS 0.20945, log loss 1.02873, n=380 — exact to 5 dp
- 2,280 of 2,280 and 380 of 380 matches forecast; **zero duplicates, zero drops**
- Base-rate anchor 0.23418 confirms the halved-RPS convention (an unhalved
  implementation would read ≈0.47)
- Frozen config byte-identical since `b416925`; zero files under `src/` or
  `scripts/`; lock chain VALID throughout

**NOT verified** — the adversarial verify agent died on an account spend limit:

- seeded-leak positive control on the improvement run
- window-contamination audit
- gates-off byte-identity check
- formal multiplicity analysis

Mitigating: **nothing was adopted**, so there is no selected winner that could be a
best-of-51 artefact. "51 specifications, none cleared the bar" is a more robust
claim than "one of 51 passed."

## Cost

One fit 57 s; the full 212-fit walk ~2.3 h. **Zero cash** — CC0 data
(football-data.co.uk), no odds purchases, no paid feeds. Odds appear only as an
internal benchmark and are never displayed.

Incidental finding, not acted on: ~90% of each fit is `wcmodel.data.tiers.is_covid`
re-parsing `config/config.yaml` — 8,038 parses per fit. Memoising it gives a 6.5 s
fit with a bit-identical panel and the identical content key. The fix is one line
inside the lock-attested `src/`, so it needs a new lock version.

## What was foreclosed, and why

Not attempted, for licence reasons rather than effort:

- **Match-level xG** — Sports Reference deleted advanced data from FBref in
  January 2026; Understat's `robots.txt` is `User-agent: *` / `Disallow: /`;
  StatsBomb's licence forbids commercially exploiting derived analysis.
- **Transfer values / player-level data** — Transfermarkt forbids automated access,
  and evidence that a transfer covariate improves prospective 1X2 scores is thin.

The lawful substitute is the variance inflation above: do not claim to know how a
squad changed, widen the uncertainty instead. It was the only lever with the right
sign, and it was still too small to adopt.
