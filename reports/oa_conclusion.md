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

> **On these 217 fixtures, market-priced forecasts scored about 0.010 RPS
> better than our model.**

What it does NOT say is that zero model is optimal. ADOPT compared a
95%-market blend against the incumbent; it never compared the blend against
pure market. That contrast, run separately, gives pure market ahead of E′ by
only 0.00018 with an interval straddling zero — i.e. *no detectable
difference between 95% and 100% market*, which is a much weaker statement
than "stop using the model".

The arm gradient is consistent with this: arms move in proportion to how
much bookmaker they carry — E′ −0.01018 and E′-other-devig −0.01013 together,
stacking −0.00584 less, the two Elo arms at −0.00021 and −0.00061. That is
the pattern the mechanism predicts.

It is NOT, as an earlier draft claimed, a proof that no scoring bug exists.
The arms are nested and correlated, not independent negative controls, and a
defect specific to outcomes or odds could move the market-heavy contrasts
while leaving the Elo arms near zero. Near-zero Elo arms are reassuring, not
a scoring-integrity test.

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

- It **wins 42% of individual fixtures** and loses the aggregate through a
  **fat tail of catastrophic misses** — Cameroon v Brazil, Ghana v Panama,
  Qatar v Senegal. The ten worst fixtures account for roughly 88% of the net
  deficit.
- Reliability looks broadly similar to the market's, but that comparison is
  **not load-bearing**: the table's shared `n` column was the model's count
  applied to both sides, the bands pool all three outcome classes, and it
  carries no intervals. It cannot separate calibration from sharpness, so
  "not broadly miscalibrated" is withdrawn as a claim.

"Normal, then occasionally very wrong" also flatters it. The median
`book − model` is −0.00882 and the model loses 58% of fixtures. It is
modestly behind most of the time and catastrophically behind occasionally.

## Two explanations, both tested, both honestly reported

The diagnostic produced two candidate stories. Both were re-tested on the
development slate, restricted to the **219 fixtures where extra time was
structurally impossible** — group and league matches, plus the knockout
rounds that go straight from 90 minutes to penalties (AFCON third place,
Copa América quarter-finals through third place, Nations League first legs
and third-place matches). 40 extra-time-capable fixtures are excluded; we
hold no verified 90' table for them.

*A note on provenance, since it cuts against me.* An earlier run of these
tests excluded shootouts — selection on the outcome, and they were the
fixtures whose 90' result was certain — and scored knockout ties on
extra-time-inclusive finals, mislabelling four matches. It also resampled
individual fixtures rather than (pool, matchday) blocks. A second review
then found that the first repair still mis-specified the design: it excluded
ALL knockouts (losing 14 fixtures whose rounds have no extra time by
regulation), resampled the two groups independently even when they shared a
matchday, and paired a one-sided test with a two-sided interval. Both sets of
numbers are withdrawn; what follows is the third and current computation. And while the predicted directions were written down before
computing, the repository cannot PROVE it: hypothesis code and results landed
in single commits. Treat both as replication attempts, not auditable
preregistrations.

**Confederation — DOES NOT REPLICATE.** The eval pool suggested the model
was level with the market between UEFA/CONMEBOL teams (+0.0003) and lost
everywhere else (−0.0182), which reads as thin rating history. On the
corrected dev slate the pattern **inverted**: gap **+0.0131**, block CI
[+0.0015, +0.0246], one-sided p **0.97** against the predicted direction. H1 predicted a negative gap and got a positive one.

"Refuted" was too strong and is withdrawn — refuting a hypothesis needs an
equivalence or reverse-rejection rule, and none was set. What is supported is
the narrow claim that H1 does not replicate. The reverse effect is *not*
claimed either: its direction was not predicted in advance, so reading
significance off it would be the same post-hoc move H1 existed to test. Nor
can non-replication identify a cause, so "small-cell noise plus confounding"
is likewise withdrawn as an explanation.

*This mattered.* The modelling change it pointed at — P2c tier weights —
would have been built on a lead that does not exist.

**Disagreement — REPLICATED, STILL NOT CERTIFIED.** When the model departs
sharply from the market in *either* direction, it loses. On the corrected
population the U-shape holds: much-lower −0.0179, agree +0.0023, much-higher
−0.0281. The gap is **−0.0253**, block CI [−0.0452, −0.0043], one-sided
p **0.024**.

That clears a 5% bar — and it is still **not a certification**, for a reason
worth stating plainly. The first run used an internally inconsistent rule (a
5% tail reported beside a 97.5th-percentile gate) under which H2 narrowly
missed. Correcting to a single one-sided α is the right construction and
would have been right from the start, but it was adopted *after* the
near-miss was visible. A rule that turns a miss into a pass once the data are
seen cannot certify anything. An independent reviewer, asked to argue both
sides, reached the same ruling.

The earlier claim that H2 "misses on power, not signal" is **withdrawn**:
plugging an observed effect into a power formula cannot establish that the
effect is real, and the ~811-fixture figure derived from it is withdrawn with
it. `oa_disagreement_test.md` now carries a sensitivity grid instead —
block-resampled, and labelled post-hoc, because those effect sizes were also
chosen with the estimate already known.

Both tails lose, and no asymmetry is detected on a two-sided test — the
question had no pre-committed direction, so a one-sided tail read off
whichever way the estimate pointed would not have been a test at all. That is **not** evidence of symmetry — the interval is
far too wide to exclude a meaningful bias, and bias and variance can coexist.
The honest statement is that this data cannot separate them, so "variance,
not bias, therefore shrinkage" is withdrawn as a conclusion.

## What this leaves

We do not currently have a validated direction for improving the model. That
is the honest state. The two leads this programme generated are one that
fails to replicate and one uncertified, and further slicing of the same 217 + 219 fixtures is
fishing, not analysis.

**H1 could not have answered its question with this sample**, whatever the
statistics. Confederation is nearly collinear with competition here: all 84
AFCON rows are non-core, every Nations League and World Cup qualification row
is core, and only Copa América contains both. No resampling separates a
confederation effect from a competition effect under that design. That is a
limit of the data, not of the estimator, and it should have been checked
before the test was run.

One untested idea is on the record precisely so it is not mistaken for a
finding: the deficit concentrates where the model disagrees with the market,
which suggests *conditional* shrinkage — trust the model when it agrees,
pull toward the market when it does not — rather than the blunt global
w=0.95. It was generated post-hoc from the same data that would test it.
**Do not build it without an independent test.**

## Cost

9,009 API credits (G-A eval 4,495; G-B development 4,514) against a ~20,000
monthly allowance. Two hypotheses tested — not resolved; one fails to
replicate and one remains uncertified — for the price of a few scripts, two
adversarial reviews and no additional credits.

The reviews were the best-value part. They found a settlement bug that turned
90-minute draws into wins, a bootstrap that ignored the dependence it claimed
to model, a decision rule that contradicted itself, and an over-exclusion that
discarded 14 valid fixtures. Every one of those was in hand-written analysis
code that bypassed tested primitives the locked pipeline already used
correctly. The headline result never moved.

## Why the negative result was worth buying

It closes a question that would otherwise have been answered by assertion:
whether the model has independent forecasting value against a liquid market.
The measured answer is a retrospective deficit against the market on
tournament 1X2, concentrated where the two disagree. It does NOT establish
that the model carries no incremental information: blend-versus-pure-market
was never a powered primary comparison, and none of this is confirmatory.
Any future accuracy claim now has a number to beat and a documented method
for beating it.

A future venue should preregister three contrasts, not one: blend vs
incumbent, pure market vs incumbent, and **blend vs pure market**. Only the
last one asks whether the model adds anything once the market is present,
and it is the question this programme could not answer.

A null is a real answer, which the prereg said in advance.

---

## Closure note — 2026-08-12

The confirmatory programme this document pointed forward to will not run.
The design work was completed first and published
(`reports/oa_confirmatory_design.md`): no confirmatory decision rule was ever
sealed; the sealed sign-flip veto makes an accumulating design self-defeating
(the probability of confirming a true effect *falls* as pools are added,
0.461 at K=3 to 0.263 at K=10); the calibrated repair needs roughly 400
covered fixtures across 8–12 pools over years during which the incumbent
could not honestly stay frozen; and the sealed venue supplied 36 fixtures at
0.284 power. The owner ruled closure on 2026-08-12; the ruling and its exact
form are sealed in the lock-v10 amendment of `reports/oa_prereg.md`.

Everything above this note stands as written. The development verdict is
unchanged — the market beat the model by ~0.010 mean RPS on the 217-fixture
eval, and that number remains the one any future accuracy claim has to beat,
under a preregistration written from scratch.
