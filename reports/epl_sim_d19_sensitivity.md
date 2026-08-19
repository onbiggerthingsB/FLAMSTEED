# D19 sensitivity — mean-field ADVI against a NUTS reference

One cutoff: **2025/26 MW0** (cutoff `2025-08-15`), a settled season, so the two arms can also be scored against the table that actually happened.

- production arm: `advi`, 1000 draws — the frozen config, unchanged
- reference arm: `nuts`, 1000 draws (2 chains) — selected through the config, no `src/` change
- both books simulated through the same engine and ranker at N = 20,000, seed 20260611, S = the arm's own draw count

Monte-Carlo error is not model error. A probability difference smaller than a couple of the standard errors printed beside it has not been shown to be a difference. Positional thresholds are not claims about qualification for any competition, and nothing here is a betting signal.

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

Every figure carries its cluster-by-particle Monte-Carlo standard error. `Δ` is reference minus production.

### champion

| club | mean-field | ± | NUTS | ± | Δ |
|---|---|---|---|---|---|
| man_city | 0.3645 | 0.0076 | 0.3994 | 0.0074 | +0.0348 |
| arsenal | 0.2933 | 0.0070 | 0.2695 | 0.0060 | -0.0238 |
| liverpool | 0.2895 | 0.0070 | 0.2862 | 0.0066 | -0.0033 |
| newcastle | 0.0234 | 0.0018 | 0.0186 | 0.0014 | -0.0048 |
| chelsea | 0.0141 | 0.0013 | 0.0152 | 0.0012 | +0.0011 |
| aston_villa | 0.0054 | 0.0007 | 0.0044 | 0.0006 | -0.0010 |
| sunderland | 0.0021 | 0.0009 | 0.0021 | 0.0012 | +0.0000 |
| brighton | 0.0021 | 0.0004 | 0.0010 | 0.0002 | -0.0010 |
| brentford | 0.0019 | 0.0004 | 0.0009 | 0.0002 | -0.0009 |
| nottm_forest | 0.0008 | 0.0002 | 0.0002 | 0.0001 | -0.0006 |
| bournemouth | 0.0006 | 0.0002 | 0.0004 | 0.0001 | -0.0002 |
| tottenham | 0.0006 | 0.0002 | 0.0001 | 0.0001 | -0.0004 |
| crystal_palace | 0.0006 | 0.0002 | 0.0009 | 0.0002 | +0.0003 |
| man_united | 0.0003 | 0.0001 | 0.0004 | 0.0002 | +0.0001 |
| fulham | 0.0003 | 0.0001 | 0.0003 | 0.0001 | +0.0000 |
| everton | 0.0001 | 0.0001 | 0.0001 | 0.0001 | -0.0000 |
| west_ham | 0.0001 | 0.0000 | 0.0001 | 0.0000 | +0.0000 |
| leeds | 0.0001 | 0.0000 | 0.0001 | 0.0000 | +0.0000 |
| burnley | 0.0001 | 0.0000 | 0.0000 | 0.0000 | -0.0001 |
| wolves | 0.0000 | 0.0000 | 0.0000 | 0.0000 | +0.0000 |

### top4

| club | mean-field | ± | NUTS | ± | Δ |
|---|---|---|---|---|---|
| man_city | 0.9261 | 0.0038 | 0.9489 | 0.0027 | +0.0228 |
| arsenal | 0.9083 | 0.0038 | 0.9151 | 0.0034 | +0.0068 |
| liverpool | 0.9040 | 0.0041 | 0.9154 | 0.0035 | +0.0114 |
| newcastle | 0.3587 | 0.0075 | 0.3520 | 0.0075 | -0.0067 |
| chelsea | 0.3095 | 0.0072 | 0.3133 | 0.0070 | +0.0037 |
| aston_villa | 0.1680 | 0.0055 | 0.1660 | 0.0052 | -0.0020 |
| brighton | 0.0801 | 0.0036 | 0.0767 | 0.0034 | -0.0034 |
| brentford | 0.0789 | 0.0039 | 0.0696 | 0.0031 | -0.0093 |
| crystal_palace | 0.0527 | 0.0028 | 0.0430 | 0.0023 | -0.0096 |
| nottm_forest | 0.0394 | 0.0026 | 0.0348 | 0.0020 | -0.0046 |
| bournemouth | 0.0366 | 0.0024 | 0.0356 | 0.0023 | -0.0010 |
| fulham | 0.0324 | 0.0021 | 0.0295 | 0.0017 | -0.0029 |
| tottenham | 0.0323 | 0.0021 | 0.0379 | 0.0023 | +0.0056 |
| man_united | 0.0265 | 0.0019 | 0.0242 | 0.0017 | -0.0023 |
| everton | 0.0173 | 0.0013 | 0.0141 | 0.0013 | -0.0032 |
| sunderland | 0.0146 | 0.0026 | 0.0136 | 0.0026 | -0.0009 |
| west_ham | 0.0063 | 0.0008 | 0.0048 | 0.0006 | -0.0015 |
| leeds | 0.0039 | 0.0008 | 0.0021 | 0.0005 | -0.0017 |
| wolves | 0.0033 | 0.0005 | 0.0022 | 0.0004 | -0.0010 |
| burnley | 0.0011 | 0.0004 | 0.0011 | 0.0003 | +0.0000 |

### relegated

| club | mean-field | ± | NUTS | ± | Δ |
|---|---|---|---|---|---|
| burnley | 0.6464 | 0.0093 | 0.6570 | 0.0090 | +0.0105 |
| sunderland | 0.6464 | 0.0115 | 0.6375 | 0.0112 | -0.0089 |
| leeds | 0.5998 | 0.0101 | 0.6336 | 0.0095 | +0.0337 |
| wolves | 0.2841 | 0.0075 | 0.2781 | 0.0067 | -0.0060 |
| west_ham | 0.2419 | 0.0069 | 0.2366 | 0.0064 | -0.0052 |
| everton | 0.1024 | 0.0042 | 0.1078 | 0.0042 | +0.0053 |
| man_united | 0.0850 | 0.0042 | 0.0769 | 0.0034 | -0.0082 |
| fulham | 0.0776 | 0.0038 | 0.0722 | 0.0035 | -0.0054 |
| bournemouth | 0.0680 | 0.0034 | 0.0726 | 0.0035 | +0.0047 |
| nottm_forest | 0.0635 | 0.0033 | 0.0566 | 0.0028 | -0.0069 |
| tottenham | 0.0609 | 0.0032 | 0.0579 | 0.0030 | -0.0030 |
| crystal_palace | 0.0421 | 0.0028 | 0.0447 | 0.0026 | +0.0026 |
| brentford | 0.0350 | 0.0024 | 0.0288 | 0.0019 | -0.0062 |
| brighton | 0.0313 | 0.0022 | 0.0266 | 0.0017 | -0.0047 |
| aston_villa | 0.0100 | 0.0011 | 0.0085 | 0.0010 | -0.0015 |
| chelsea | 0.0034 | 0.0005 | 0.0023 | 0.0004 | -0.0011 |
| newcastle | 0.0021 | 0.0004 | 0.0022 | 0.0004 | +0.0001 |
| man_city | 0.0000 | 0.0000 | 0.0000 | 0.0000 | +0.0000 |
| liverpool | 0.0000 | 0.0000 | 0.0000 | 0.0000 | +0.0000 |
| arsenal | 0.0000 | 0.0000 | 0.0000 | 0.0000 | +0.0000 |

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

| arm | E[relegations among promoted] | MC SE (upper bound) |
|---|---|---|
| mean-field ADVI | 1.893 | 0.031 |
| NUTS | 1.928 | 0.030 |

Promoted into 2025/26: `burnley`, `leeds`, `sunderland`.

## 5. Score against the realised table, and what each fit cost

| arm | TRPS | fit wall (s) | sim wall (s) | draws |
|---|---|---|---|---|
| mean-field ADVI | 0.1356 | 7.5 | 1.6 | 1000 |
| NUTS | 0.1359 | 20.4 | 1.5 | 1000 |

Reference-arm convergence: worst r-hat 1.0200, smallest bulk ESS 381 over 5 parameter blocks — **flagged**: att, def. A reference that has not mixed is not a reference, and the ratios above inherit that doubt.

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
1.32x/1.25x tighter. Those gaps are large and real, but a global scoring-level
term shifts every club together rather than reordering them, and the net effect
on the object actually published runs the *other* way: the simulated
points-total spread is about 4% narrower under NUTS (mean ratio 0.960, range
0.932–0.996; mean sd 9.90 points against 9.51). The consequence probabilities
move by at most 0.035 — Manchester City's title figure 0.3645 +/- 0.0076 to
0.3994 +/- 0.0074, roughly 4.6 Monte-Carlo standard errors, and Leeds relegation
0.5998 to 0.6336 — while most clubs move inside two standard errors; E[relegations
among the three promoted clubs] is 1.893 against 1.928. TRPS on the realised
2025/26 table is 0.13557 for mean-field against 0.13593 for NUTS, the production
arm marginally *better* by 0.00036 on one season at one cutoff with no interval,
which is a coin flip and is not a win for either arm. The cost is 7.5 s against
20.4 s per fit, so nothing here is decided by runtime. Two caveats stop this
being a clean bill of health. The NUTS reference did not fully mix — worst r-hat
1.020 on the raw team effects and smallest bulk ESS 381 over 1,000 draws at
3,000 tuning steps — so its own standard deviations carry noise; re-running it at
1,000 tuning steps moved the reported ratios by roughly 1–7% (`att` 0.936 to
0.947, `mu` 2.07 to 2.21, `home_adv` 1.24 to 1.32), which is the size of the
reference-arm wobble and is smaller than the `mu` finding but comparable to the
`att`/`def` ones. And this is ONE cutoff on ONE season, the opener, where every
fixture is unplayed and the fit has no in-season evidence at all (no club is
cold-start or provisional here, so the widening branch is inert and plays no
part in either arm). The
narrow claim D19 asked for is supported at this cutoff: moving to a richer
posterior does not widen the published table intervals and does not improve the
score, so mean-field is not buying its speed with visibly false confidence about
the table. The broader claim — that this holds mid-season, or across seasons — is
untested here, and no public uncertainty language should lean on it.

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
  --report-out reports/epl_sim_d19_sensitivity.md --conclusion-file <file>
```

The two fits are seeded and deterministic: a re-run reproduces both TRPS figures and both digests exactly. `--from-json` rewrites this report from the dump without paying for the fits again.

