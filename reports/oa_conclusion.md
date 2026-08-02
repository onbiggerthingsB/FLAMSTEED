# Odds-Anchored accuracy programme — what it found

Closed 2026-08-02 under lock-v6. This is the plain-language companion to
`oa_verdict.md` (the preregistered decision) and `oa_prereg.md` (what was
committed to in advance). Where they disagree with this document, they win.

## The question

Does anchoring our forecasts to betting-market odds make them more accurate?

## The answer

Yes — and that is worse news than it sounds.

The preregistered gate passed: mean ΔRPS **−0.01018** against a floor of
−0.002, support **0.995** against a requirement of 0.80, sign-flip veto not
fired, jackknife range [−0.01247, −0.00843] never crossing zero. On 217
fixtures across WC-2022, Euro-2024 and WC-2026.

The catch is what the winning arm *is*. The blend weight selected on
development data was **w = 0.95** — ninety-five percent bookmaker, five
percent us. And w=0.95 beat pure market (w=1.00) by 0.00002, which is noise.
So the honest reading of the verdict is not "our model improved". It is:

> **The market forecasts these matches better than our model, by about 0.010
> RPS, and the procedure's preferred way to close that gap is to stop using
> our model.**

The arm gradient says the same thing independently. Arms move in proportion
to how much bookmaker they carry: E′ −0.01018 and E′-other-devig −0.01013
(both book-dominated) together, stacking −0.00584 less, and the two Elo arms
at −0.00021 and −0.00061, essentially zero. A scoring bug would not have
spared the Elo arms.

## What we did NOT conclude

**This is not confirmatory evidence.** The lock was taken after every one of
these outcomes already existed, so no amount of hashing can attest that the
analysis was blind to them. That is Codex finding B1, and no code fixes it.
The retrospective result is a *development diagnostic*. The only confirmatory
route is the preregistered live venue test, and the ranked rule points at
AC2027 → AFCON 2027 → 2027 WCQ windows — none of which exist yet.

**We did not adopt anything.** No odds arm ships. The product's forecasts are
unchanged.

## Where the model actually loses

The aggregate number says a gap exists, not where. Cutting the same fixtures
(`oa_gap_diagnostic.md`) found the shape:

- The model is **not broadly miscalibrated**. Band by band it states nearly
  the same probabilities as the market and those probabilities happen nearly
  as often. It also **wins 42% of individual fixtures**.
- It loses the aggregate through a **fat tail of catastrophic misses** —
  Cameroon v Brazil, Ghana v Panama, Qatar v Senegal.

So the model is not quietly worse. It is normal, then occasionally very
wrong.

## Two explanations, both tested, both honestly reported

The diagnostic produced two candidate stories. Both were tested
out-of-sample on the 259-fixture development slate, with the predicted
direction committed in writing before computing.

**Confederation — REFUTED.** The eval pool suggested the model was level
with the market between UEFA/CONMEBOL teams (+0.0003) and lost everywhere
else (−0.0182), which reads as thin rating history. Out of sample the
pattern **inverted**: gap +0.0119, p 0.914 against prediction. Copa América
(+0.0200, the model *beats* the market) and CONMEBOL World Cup qualification
(−0.0380, its worst loss) are the same confederation pointing opposite ways.
The eval-pool split was small-cell noise plus favourite-strength
confounding.

*This mattered.* The modelling change it pointed at — P2c tier weights —
would have been built on a lead that does not exist.

**Disagreement — REPLICATED, UNCERTIFIED.** When the model departs sharply
from the market in *either* direction, it loses badly. Band by band, dev
against eval: much-lower −0.0168/−0.0205, agree +0.0025/−0.0036, much-higher
−0.0257/−0.0297. The shape held in independent data. It still does not clear
the pre-set bar (gap −0.0236, CI [−0.0577, +0.0103], p 0.082) and has not
been upgraded.

It misses on **power, not signal**: per-fixture SD is 0.127 in the extreme
bands against 0.019 when the two agree, ~7×. At that spread the effect needs
roughly 811 fixtures; we have 244.

Both tails lose about equally, with no detectable asymmetry. That is the
signature of **variance, not bias** — there is no directional error to
correct, so the indicated remedy is shrinkage.

## What this leaves

We do not currently have a validated direction for improving the model. That
is the honest state. The two leads this programme generated are one refuted
and one underpowered, and further slicing of the same 217 + 244 fixtures is
fishing, not analysis.

One untested idea is on the record precisely so it is not mistaken for a
finding: the deficit concentrates where the model disagrees with the market,
which suggests *conditional* shrinkage — trust the model when it agrees,
pull toward the market when it does not — rather than the blunt global
w=0.95. It was generated post-hoc from the same data that would test it.
**Do not build it without an independent test.**

## Cost

9,009 API credits (G-A eval 4,495; G-B development 4,514) against a ~20,000
monthly allowance. Two hypotheses tested and resolved for the price of two
scripts and no additional credits.

## Why the negative result was worth buying

It closes a question that would otherwise have been answered by assertion:
whether the model has independent forecasting value against a liquid market.
The measured answer is that it currently does not, at least on tournament
1X2, and that the gap runs through erratic disagreement rather than
systematic bias. Any future accuracy claim now has a number to beat and a
documented method for beating it.

A null is a real answer, which the prereg said in advance.
