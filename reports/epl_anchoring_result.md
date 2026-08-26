# The market-prior experiment — result (2026-08-26)

**DC NATIVE STANDS.** The preregistered estimand — the mean paired RPS change
from rotating the fit's prior toward market-implied strength, at the
leave-one-season-out weight, over all 2,280 corpus fixtures — came out at
**−0.000193**, against a bar of −0.0010 with both intervals required to exclude
zero. Week-block CI **[−0.000831, +0.000432]**; season-block CI
**[−0.000838, +0.000836]**. All three legs miss. No arm ships.

The selection saturated, and §3.4's pre-ruled diagnostic ran: four of six folds
chose w = 1.0, the grid maximum. At full market direction the arm scored
0.20024 against native's 0.20003 — indistinguishable — while the same-timing
opening market itself scored 0.19457. The arm did not collapse onto the market
(correlation 0.956, mean probability gap 4.1pp): the prior pointed where the
market points, and the likelihood — 4,570 matches of results at a frozen prior
strength of k = 0.6 — pulled the posterior back to what results say. Mean
probability movement was 0.88pp against a seed-replica floor of 0.32pp. The
mechanism the preregistration permitted is too gentle for the information it
carries; the data swamps the prior.

Read together with the design's grounding, the honest chain is now complete:
the output blend reaches the market's accuracy but saturates at w = 1 and
defines no scoreline law — publishing it would be publishing the market; the
input rotation defines a full scoreline law but cannot move the posterior at
frozen k. The +0.0050 opening-odds prize is real and remains unclaimed. What
would claim it is a stronger coupling — a swept prior strength, or odds
entering the likelihood itself — and every such path re-opens settled
preregistrations (k = 0.6 among them) or builds new model machinery. That is a
future preregistration's decision, recorded here as the open door it is,
walked through by nobody today.

The run's own integrity: sanity control 20 dates / 681 probabilities at exact
8-decimal parity; both leakage canaries PASS with live positive controls
(results canary 0.81, odds canary 4.98, zero vacuous legs); harness freeze
verified in-run; 1,060 fits, four shards, key set exact; the featpanel race of
the first launch answered operationally by sequential sharding, with the
concurrency fix queued for the next lock version. Machine-readable verdict:
data/epl/fit/anchoring.json; the arm's 2,280 predictions retained at
data/epl/fit/dc_market_prior_predictions.parquet (sha da685cf4…) for any future
comparison. Per §5, nothing here compares any arm to any market as a claim.
