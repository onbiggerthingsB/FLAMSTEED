# D19 sensitivity — mean-field ADVI against a NUTS reference

One cutoff: **2025/26 MW0** (cutoff `2025-08-15`), a settled season, so the two arms can also be scored against the table that actually happened.

- production arm: `advi`, 1000 draws — the frozen config, unchanged
- reference arm: `nuts`, 1000 draws (2 chains) — selected through the config, no `src/` change
- both books simulated through the same engine and ranker at N = 20,000, seed 20260611, S = the arm's own draw count

Monte-Carlo error is not model error. A probability difference smaller than a couple of the standard errors printed beside it has not been shown to be a difference. Positional thresholds are not claims about qualification for any competition, and nothing here is a betting signal.

**2026-08-19 revision (Codex review of `3844b59`).** Every number below is the 2026-08-19 run's, re-rendered from that run's saved dump with `--from-json`: no fit was re-run, and no probability, ratio, points spread, TRPS figure or hash has moved. What changed is how they are read. (i) The NUTS column now carries an **ESS-adjusted** Monte-Carlo standard error beside the cluster one (§2, §4) — the cluster form counts 1,000 posterior draws as 1,000 independent clusters, which is right for mean-field ADVI and wrong for a Markov chain. (ii) A difference between the two arms now carries the error **of the difference** rather than of one column beside it; the conclusion's Manchester City figure was previously quoted at 4.6 standard errors, which divided the gap by the production arm's error alone. (iii) §5 now states which parameter blocks the reference arm's recorded convergence check actually covered — five, not including `sigma_att`/`sigma_def`, the two blocks carrying the largest ratios in §1. The check has since been widened to cover all seven; a re-run would report them, and this run did not. (iv) The conclusion is stated as **indicative** rather than supported, for the reason (iii) gives.

**2026-08-20 revision (Codex review of `89f4c13`).** Every number below is still the 2026-08-19 run's: no fit was re-run and no probability, ratio, points spread, TRPS figure, standard error or hash has moved. Three sentences that describe those numbers have changed, and the generator that writes them changed with them, so a regeneration reproduces this text rather than the withdrawn one. (i) The **ESS-adjusted** column is now labelled a **heuristic** bound rather than "the honest column to read it by", and both reasons it is not a corrected standard error are printed beside it: the ESS is a marginal-parameter quantity while the column is a functional of the whole posterior, and the factor scales an error that also carries independent match-simulation noise no ESS deficit inflates. (ii) The `Δ ±` sentence no longer calls the independent-sum form *conservative rather than exact*: the covariance it ignores is not computed here and its sign is not established, so the direction is stated as unknown — the same discipline A2-N4 applies to the TRPS diagonal SE. (iii) §2 now states that **both arms carry S = 1000**, and the run refuses to report two arms at different draw counts (`check_arms_share_S`); each arm was previously checked only against its own config, which two different configs can both satisfy. §5's "which blocks the check covered" sentence is also now driven by the blocks the check actually read rather than by the list it was asked for.

## 1. Posterior dispersion — richer / mean-field

A ratio above 1 means mean-field was tighter than the reference: the under-dispersion D19 names. `n` is how many quantities the ratio is taken over (one per club for the team effects, one for a scalar).

| parameter | n | mean | median | min | max | mean-field sd | reference sd |
|---|---|---|---|---|---|---|---|
| `att` | 35 | 0.947 | 0.955 | 0.876 | 1.080 | 0.2034 | 0.1944 |
| `def` | 35 | 0.929 | 0.925 | 0.835 | 1.023 | 0.1924 | 0.1803 |
| `home_adv` | 1 | 1.324 | 1.324 | 1.324 | 1.324 | 0.0394 | 0.0522 |
| `mu` | 1 | 2.210 | 2.210 | 2.210 | 2.210 | 0.0299 | 0.0660 |
| `rho` | 1 | 1.005 | 1.005 | 1.005 | 1.005 | 0.0512 | 0.0515 |
| `sigma_att` | 1 | 1.323 | 1.323 | 1.323 | 1.323 | 0.0447 | 0.0591 |
| `sigma_def` | 1 | 1.254 | 1.254 | 1.254 | 1.254 | 0.0461 | 0.0579 |

- `att`: tightest relative to the reference at **cardiff** (ratio 1.080), widest at **wolves** (0.876).
- `def`: tightest relative to the reference at **sunderland** (ratio 1.023), widest at **leeds** (0.835).

## 2. Consequence probabilities, side by side

Every figure carries its cluster-by-particle Monte-Carlo standard error. `Δ` is reference minus production, and `Δ ±` is the error on that DIFFERENCE rather than on either column beside it: `sqrt(se_mean-field² + se_NUTS²)`.

**Both arms carry S = 1000 posterior draws.** That is what makes the comparison one between two posterior APPROXIMATIONS: at two different draw counts a difference in Monte-Carlo error between the arms would be a difference in S wearing the costume of a difference in posterior, and no column here separates the two. The run refuses to report unequal arms (`check_arms_share_S`).

**`NUTS ± (ESS-adj)`** is the NUTS column's error scaled by **1.620**, and it is a **HEURISTIC** bound rather than a corrected standard error. A cluster-by-particle error counts the S posterior draws as S INDEPENDENT clusters, which is right for mean-field ADVI — i.i.d. draws from one approximation — and wrong for NUTS, whose draws are a Markov chain, so the unadjusted NUTS `±` is a lower bound on that arm's Monte-Carlo error and SOME inflation is warranted. The rule is `SE_adjusted = SE_cluster * sqrt(S / ESS_bulk_min) = sqrt(1000 / 381) = 1.620`, taking the SMALLEST bulk ESS over the parameter blocks the reference arm's convergence check covered. What is NOT established is that this is the right inflation, for two reasons, and neither is quantified here:

- the ESS is a MARGINAL-parameter one and the column is a FUNCTIONAL of the whole posterior: the bulk ESS of the worst-mixed parameter block need not bound the effective sample size of a champion or relegation probability, which can mix better or worse than any single block;
- the factor multiplies the WHOLE cluster standard error, and that error contains independent match-simulation noise as well as posterior-draw noise; no ESS deficit inflates the match-simulation part, so the scaling over-corrects it;

so the adjusted column is a plausible order of magnitude for the understatement and is not an error anything in this run computed.

Both arms were simulated at the same seed and the same N, so their Monte-Carlo errors are coupled rather than independent. `Δ ±` ignores that covariance, and the sign of the covariance is not computed here. Common random numbers usually couple two arms positively, in which case the independent-sum form overstates the error of the difference — but that is an expectation about this kind of coupling and not a measurement of this one, so **the direction of `Δ ±` is not known**.

### champion

| club | mean-field | ± | NUTS | ± | NUTS ± (ESS-adj) | Δ | Δ ± |
|---|---|---|---|---|---|---|---|
| man_city | 0.3645 | 0.0076 | 0.3994 | 0.0074 | 0.0120 | +0.0348 | 0.0106 |
| arsenal | 0.2933 | 0.0070 | 0.2695 | 0.0060 | 0.0098 | -0.0238 | 0.0092 |
| liverpool | 0.2895 | 0.0070 | 0.2862 | 0.0066 | 0.0107 | -0.0033 | 0.0096 |
| newcastle | 0.0234 | 0.0018 | 0.0186 | 0.0014 | 0.0023 | -0.0048 | 0.0023 |
| chelsea | 0.0141 | 0.0013 | 0.0152 | 0.0012 | 0.0019 | +0.0011 | 0.0017 |
| aston_villa | 0.0054 | 0.0007 | 0.0044 | 0.0006 | 0.0010 | -0.0010 | 0.0009 |
| sunderland | 0.0021 | 0.0009 | 0.0021 | 0.0012 | 0.0019 | +0.0000 | 0.0014 |
| brighton | 0.0021 | 0.0004 | 0.0010 | 0.0002 | 0.0004 | -0.0010 | 0.0005 |
| brentford | 0.0019 | 0.0004 | 0.0009 | 0.0002 | 0.0004 | -0.0009 | 0.0005 |
| nottm_forest | 0.0008 | 0.0002 | 0.0002 | 0.0001 | 0.0002 | -0.0006 | 0.0003 |
| bournemouth | 0.0006 | 0.0002 | 0.0004 | 0.0001 | 0.0002 | -0.0002 | 0.0002 |
| tottenham | 0.0006 | 0.0002 | 0.0001 | 0.0001 | 0.0001 | -0.0004 | 0.0002 |
| crystal_palace | 0.0006 | 0.0002 | 0.0009 | 0.0002 | 0.0004 | +0.0003 | 0.0003 |
| man_united | 0.0003 | 0.0001 | 0.0004 | 0.0002 | 0.0003 | +0.0001 | 0.0002 |
| fulham | 0.0003 | 0.0001 | 0.0003 | 0.0001 | 0.0002 | +0.0000 | 0.0002 |
| everton | 0.0001 | 0.0001 | 0.0001 | 0.0001 | 0.0001 | -0.0000 | 0.0001 |
| west_ham | 0.0001 | 0.0000 | 0.0001 | 0.0000 | 0.0001 | +0.0000 | 0.0001 |
| leeds | 0.0001 | 0.0000 | 0.0001 | 0.0000 | 0.0001 | +0.0000 | 0.0001 |
| burnley | 0.0001 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.0001 | 0.0000 |
| wolves | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | +0.0000 | 0.0000 |

### top4

| club | mean-field | ± | NUTS | ± | NUTS ± (ESS-adj) | Δ | Δ ± |
|---|---|---|---|---|---|---|---|
| man_city | 0.9261 | 0.0038 | 0.9489 | 0.0027 | 0.0044 | +0.0228 | 0.0047 |
| arsenal | 0.9083 | 0.0038 | 0.9151 | 0.0034 | 0.0054 | +0.0068 | 0.0051 |
| liverpool | 0.9040 | 0.0041 | 0.9154 | 0.0035 | 0.0057 | +0.0114 | 0.0054 |
| newcastle | 0.3587 | 0.0075 | 0.3520 | 0.0075 | 0.0122 | -0.0067 | 0.0106 |
| chelsea | 0.3095 | 0.0072 | 0.3133 | 0.0070 | 0.0113 | +0.0037 | 0.0100 |
| aston_villa | 0.1680 | 0.0055 | 0.1660 | 0.0052 | 0.0085 | -0.0020 | 0.0076 |
| brighton | 0.0801 | 0.0036 | 0.0767 | 0.0034 | 0.0056 | -0.0034 | 0.0050 |
| brentford | 0.0789 | 0.0039 | 0.0696 | 0.0031 | 0.0051 | -0.0093 | 0.0050 |
| crystal_palace | 0.0527 | 0.0028 | 0.0430 | 0.0023 | 0.0037 | -0.0096 | 0.0036 |
| nottm_forest | 0.0394 | 0.0026 | 0.0348 | 0.0020 | 0.0032 | -0.0046 | 0.0033 |
| bournemouth | 0.0366 | 0.0024 | 0.0356 | 0.0023 | 0.0038 | -0.0010 | 0.0034 |
| fulham | 0.0324 | 0.0021 | 0.0295 | 0.0017 | 0.0028 | -0.0029 | 0.0027 |
| tottenham | 0.0323 | 0.0021 | 0.0379 | 0.0023 | 0.0038 | +0.0056 | 0.0031 |
| man_united | 0.0265 | 0.0019 | 0.0242 | 0.0017 | 0.0027 | -0.0023 | 0.0025 |
| everton | 0.0173 | 0.0013 | 0.0141 | 0.0013 | 0.0022 | -0.0032 | 0.0019 |
| sunderland | 0.0146 | 0.0026 | 0.0136 | 0.0026 | 0.0042 | -0.0009 | 0.0037 |
| west_ham | 0.0063 | 0.0008 | 0.0048 | 0.0006 | 0.0010 | -0.0015 | 0.0010 |
| leeds | 0.0039 | 0.0008 | 0.0021 | 0.0005 | 0.0008 | -0.0017 | 0.0009 |
| wolves | 0.0033 | 0.0005 | 0.0022 | 0.0004 | 0.0007 | -0.0010 | 0.0006 |
| burnley | 0.0011 | 0.0004 | 0.0011 | 0.0003 | 0.0005 | +0.0000 | 0.0005 |

### relegated

| club | mean-field | ± | NUTS | ± | NUTS ± (ESS-adj) | Δ | Δ ± |
|---|---|---|---|---|---|---|---|
| burnley | 0.6464 | 0.0093 | 0.6570 | 0.0090 | 0.0146 | +0.0105 | 0.0130 |
| sunderland | 0.6464 | 0.0115 | 0.6375 | 0.0112 | 0.0182 | -0.0089 | 0.0161 |
| leeds | 0.5998 | 0.0101 | 0.6336 | 0.0095 | 0.0155 | +0.0337 | 0.0139 |
| wolves | 0.2841 | 0.0075 | 0.2781 | 0.0067 | 0.0108 | -0.0060 | 0.0100 |
| west_ham | 0.2419 | 0.0069 | 0.2366 | 0.0064 | 0.0104 | -0.0052 | 0.0094 |
| everton | 0.1024 | 0.0042 | 0.1078 | 0.0042 | 0.0068 | +0.0053 | 0.0059 |
| man_united | 0.0850 | 0.0042 | 0.0769 | 0.0034 | 0.0055 | -0.0082 | 0.0054 |
| fulham | 0.0776 | 0.0038 | 0.0722 | 0.0035 | 0.0056 | -0.0054 | 0.0051 |
| bournemouth | 0.0680 | 0.0034 | 0.0726 | 0.0035 | 0.0057 | +0.0047 | 0.0049 |
| nottm_forest | 0.0635 | 0.0033 | 0.0566 | 0.0028 | 0.0045 | -0.0069 | 0.0043 |
| tottenham | 0.0609 | 0.0032 | 0.0579 | 0.0030 | 0.0049 | -0.0030 | 0.0044 |
| crystal_palace | 0.0421 | 0.0028 | 0.0447 | 0.0026 | 0.0041 | +0.0026 | 0.0038 |
| brentford | 0.0350 | 0.0024 | 0.0288 | 0.0019 | 0.0030 | -0.0062 | 0.0030 |
| brighton | 0.0313 | 0.0022 | 0.0266 | 0.0017 | 0.0028 | -0.0047 | 0.0028 |
| aston_villa | 0.0100 | 0.0011 | 0.0085 | 0.0010 | 0.0015 | -0.0015 | 0.0015 |
| chelsea | 0.0034 | 0.0005 | 0.0023 | 0.0004 | 0.0006 | -0.0011 | 0.0007 |
| newcastle | 0.0021 | 0.0004 | 0.0022 | 0.0004 | 0.0006 | +0.0001 | 0.0005 |
| man_city | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | +0.0000 | 0.0000 |
| liverpool | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | +0.0000 | 0.0000 |
| arsenal | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | +0.0000 | 0.0000 |

## 3. Points-total spread per club

| club | mean-field sd | NUTS sd | ratio |
|---|---|---|---|
| arsenal | 8.91 | 8.50 | 0.954 |
| aston_villa | 9.69 | 9.32 | 0.962 |
| bournemouth | 9.75 | 9.66 | 0.991 |
| brentford | 10.06 | 9.38 | 0.932 |
| brighton | 9.93 | 9.37 | 0.943 |
| burnley | 10.12 | 9.88 | 0.976 |
| chelsea | 9.65 | 9.35 | 0.969 |
| crystal_palace | 9.60 | 9.27 | 0.966 |
| everton | 9.41 | 9.07 | 0.964 |
| fulham | 9.84 | 9.39 | 0.955 |
| leeds | 11.35 | 10.60 | 0.934 |
| liverpool | 8.96 | 8.50 | 0.949 |
| man_city | 8.91 | 8.45 | 0.948 |
| man_united | 9.74 | 9.28 | 0.954 |
| newcastle | 9.57 | 9.53 | 0.996 |
| nottm_forest | 9.82 | 9.24 | 0.942 |
| sunderland | 14.41 | 14.11 | 0.979 |
| tottenham | 9.46 | 9.41 | 0.994 |
| west_ham | 9.49 | 9.11 | 0.960 |
| wolves | 9.31 | 8.77 | 0.942 |

## 4. Promoted clubs and the drop

| arm | E[relegations among promoted] | MC SE (upper bound) | ESS-adjusted |
|---|---|---|---|
| mean-field ADVI | 1.893 | 0.031 | n/a |
| NUTS | 1.928 | 0.030 | 0.048 |

The MC SE is the SUM of the per-club relegation standard errors, deliberately an upper bound: the events are negatively correlated (three clubs go down, whoever they are) and the independent-sum form would claim a covariance this report does not compute. The NUTS row carries the same ESS adjustment as §2; `n/a` on the ADVI row is not a missing number — i.i.d. draws need no adjustment.

Promoted into 2025/26: `burnley`, `leeds`, `sunderland`.

## 5. Score against the realised table, and what each fit cost

| arm | TRPS | fit wall (s) | sim wall (s) | draws |
|---|---|---|---|---|
| mean-field ADVI | 0.1356 | 7.5 | 1.6 | 1000 |
| NUTS | 0.1359 | 20.4 | 1.5 | 1000 |

Reference-arm convergence: worst r-hat 1.0200, smallest bulk ESS 381 over 5 parameter block(s) (`att`, `def`, `home_adv`, `mu`, `rho`) — **flagged**: att, def. A reference that has not mixed is not a reference, and the ratios above inherit that doubt.

The check this run ran did **not** cover `sigma_att`, `sigma_def`, so the r-hat and ESS above say nothing about how the reference mixed on blocks §1 nevertheless reports ratios for. The check now covers every quantity the report puts a ratio beside, and a re-run reports all 7; these figures are the ones this run recorded and are not restated as if they were.

TRPS is the plan's primary league-table score (Ekstrom, Van Eetvelde, Ley & Brefeld, *Evaluating one-shot tournament predictions*, arXiv:1912.07364, eq. 2), unweighted at 1/(20·19), scored against the realised 2025/26 table through the sim's own ranker (0 shared finishing position(s)). ONE season and ONE cutoff: there is no interval on this difference and none is implied.

## 6. Conclusion

Mean-field ADVI is **not** visibly under-dispersed where a league table is most
sensitive to it, and where it *is* under-dispersed the published numbers barely
move. On the team effects the mean-field posterior is if anything slightly
**wider** than the NUTS reference — richer/mean-field 0.947 on `att` and 0.929
on `def`, averaged over 35 fitted clubs, with per-club ratios spanning
0.876–1.080 and 0.835–1.023 — so the club-strength spread that drives finishing
positions is not what mean-field is collapsing. What it *is* collapsing are the
terms common to every fixture: `mu` comes back 2.21x tighter than the reference
and `home_adv` 1.32x, with the hierarchical scales `sigma_att`/`sigma_def`
1.32x/1.25x tighter. Those gaps are large, but a global scoring-level term
shifts every club together rather than reordering them, and the net effect on
the object actually published runs the *other* way: the simulated points-total
spread is about 4% narrower under NUTS (mean ratio 0.960, range 0.932–0.996;
mean sd 9.90 points against 9.51). The consequence probabilities move by at most
0.035. Manchester City's title figure goes from 0.3645 +/- 0.0076 to
0.3994 +/- 0.0074, a difference of +0.0348 against a standard error **of that
difference** of 0.0106 — about **3.3** standard errors, and about **2.5** once
the NUTS error carries the ESS adjustment of §2. (An earlier version of this
paragraph read 4.6 standard errors; that divided the difference by the
production arm's error alone, which is the error of one column and not of the
gap between two.) Leeds relegation moves 0.5998 +/- 0.0101 to
0.6336 +/- 0.0095, +0.0337 against a difference standard error of 0.0139 — about
2.4, or 1.8 adjusted — while most clubs move inside two standard errors of the
difference; E[relegations among the three promoted clubs] is 1.893 against
1.928 +/- 0.030 (0.048 adjusted). TRPS on the realised 2025/26 table is 0.13557
for mean-field against 0.13593 for NUTS, the production arm marginally *better*
by 0.00036 on one season at one cutoff with no interval, which is a coin flip
and is not a win for either arm. The cost is 7.5 s against 20.4 s per fit, so
nothing here is decided by runtime.

Three things stop this being a clean bill of health, and together they are why
the finding is **indicative rather than supported**. The NUTS reference did not
fully mix: worst r-hat 1.020 on the raw team effects and smallest bulk ESS 381
over 1,000 draws at 3,000 tuning steps, so its own standard deviations carry
noise, and re-running it at 1,000 tuning steps moved the reported ratios by
roughly 1–7% (`att` 0.936 to 0.947, `mu` 2.07 to 2.21, `home_adv` 1.24 to 1.32)
— the size of the reference-arm wobble, smaller than the `mu` finding but
comparable to the `att`/`def` ones. That convergence check covered five
parameter blocks and did **not** cover `sigma_att` or `sigma_def`, which carry
ratios of 1.32x and 1.25x in §1, third and fourth
largest behind `mu` and `home_adv`: nothing in this run says whether the
reference had mixed on them. And this is ONE cutoff on ONE season, the opener,
where every fixture is unplayed and the fit has no in-season evidence at all (no
club is cold-start or provisional here, so the widening branch is inert and
plays no part in either arm).

What D19 asked for is therefore answered **provisionally** at this cutoff:
moving to a richer posterior did not widen the published table intervals and did
not improve the score, so on this evidence mean-field is not buying its speed
with visibly false confidence about the table — but the reference this is
measured against is itself unconverged on two of the seven blocks and unchecked
on two more, and a finding measured against a shaky reference is a reading, not
a result. It should not be treated as settled without a reference that mixes.
The broader claim — that this holds mid-season, or across seasons — is untested
here, and no public uncertainty language should lean on either.

## 7. Provenance

| arm | effective posterior hash | numbers digest | fitted teams | training matches |
|---|---|---|---|---|
| mean-field ADVI | `e636739448848ae452d43639eec4a2e0745ad585e111d9d90158e5729c8af55f` | `b0cbc2ecf47b33c1088de845b30edf328bb5dec12f4f6ae9678792a5772547b2` | 35 | 4180 |
| NUTS | `91f30b4886c25b7ce2b1137a46a72ada467be7a7323323d3a9f319af198c8152` | `88bbde39738e1ab9d388579613dbfa29361b7227c21e9ccd784cfb4daf0cb27c` | 35 | 4180 |

Cold-start clubs at this cutoff: **none**; provisional clubs: **none**. Both arms fit the same panel with the same team index, so the only difference between them is the sampler.

Reproduce with:

```
PYTHONPATH=src:. python -u -m epl.sensitivity \
  --season '2025/26' --cutoff-label MW0 --n-sims 20000 --seed 20260611 \
  --json-out data/epl/d19/d19_2025_26_MW0.json \
  --report-out reports/epl_sim_d19_sensitivity.md --conclusion-file <file> \
  --note-file <file>
```

The two fits are seeded and deterministic: a re-run reproduces both TRPS figures and both digests exactly. `--from-json` rewrites this report from the dump without paying for the fits again.

