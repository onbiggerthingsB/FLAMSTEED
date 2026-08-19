# EPL table simulator — amendments to the preregistered design

Every change to a preregistered decision of the EPL table simulator is recorded
here, **before** the code that implements it is written, with the observation
that prompted it, the ruling in full, the rationale, and any number the ruling
pre-states. An amendment recorded after a result exists is not an amendment; it
is a rationalisation, and this file exists so the distinction is checkable from
the git history rather than taken on trust.

Format per entry: **observation → ruling → rationale → what is pre-stated**.

---

## A1 — D11 v1.0.1 (2026-08-19)

**Decision amended:** D11, the per-fixture truncation guard.
**Status of the amendment when written:** the guard is unchanged in code; no
`dc_native` issuance of any kind exists.

### The observation

At the first attempted 2026/27 issuance — cutoff 2026-08-21, the season opener,
zero results, 20 clubs from the transition — the `dc_native` arm failed closed on
D11's excluded-mass guard. Recorded in full in
[`reports/epl_sim_first_issuance.md`](epl_sim_first_issuance.md) §2; the numbers
that matter here:

| | |
|---|---|
| Fixtures over the 5e-3 gate | **1 of 380** — `2627:man_city:coventry`, particle-mean **0.005365** against the 0.005 limit (7.3% over) |
| Next worst three | `arsenal:coventry` 0.003934, `liverpool:coventry` 0.003426, `man_city:hull` 0.003284 |
| Mean over all 380 fixtures | 1.55e-4 · 90th percentile 3.46e-4 |
| Median **particle** for the failing fixture | 1.9e-4 — four orders of magnitude under the gate |
| Concentration | the worst 10 particles of 1,000 contribute 42.6% of the mean; 88 particles exceed 1%, 22 exceed 5% |
| Worst particle (s=953) | λ_home = 10.25, λ_away = 0.90 → P(home > 10 goals) = 0.448 |

The failure is deterministic: the same stop on every attempt, at the same fit and
the same seeded cold-start draws.

Its cause is a cold start, not a mis-scale. Coventry has no match anywhere in the
2014/15–2025/26 archive, so its attack and defence come from prior draws at the
fitted hyperparameters (D17), sd ≈ 0.30/0.34, range −1.16 to +1.24. A handful of
draws put Coventry's defence near −1.1; against Man City's attack (mean +0.77)
that gives λ_home > 10, and those individual particles lose 25–45% of their mass
past the truncation. Every fixture near the top of the list involves a promoted
club.

Sensitivity, diagnostic only and with nothing changed: at `max_goals` 11 the
worst fixture is 0.002814 and no fixture is over the gate; at 12, 0.001480; at
14, 0.000404; at 16, 0.000103.

### The ruling (owner, 2026-08-19)

D11 v1.0.1 — *report-and-record with a pre-stated hard ceiling*:

**(a)** `PRODUCTION_MAX_GOALS` stays **10**, for parity with the issued
per-fixture forecasts. Cold start stays exactly as D17 froze it. The 5e-3 number
is **kept**, but its meaning changes from hard-stop to **flag**: every fixture
whose particle-mean excluded mass exceeds 5e-3 is recorded in the envelope
(fixture id, particle-mean, median particle, worst particle, count of particles
over 1%) and listed by id in `limitations.md` under a section **"Truncation-flagged
fixtures"**, together with the sentence that production truncates at the same 10
goals and discards the same tail silently.

**(b)** The per-fixture excluded mass for **all** fixtures is recorded in the
envelope — max, mean, 90th percentile, and the full per-fixture vector in the
retained npz or a sidecar — not only for the flagged ones.

**(c)** A **hard stop remains**: a particle-mean excluded mass above **2e-2** on
any fixture fails the run closed with `ExcludedMassTooLarge`, exactly as before.

**(d)** Nothing else in D11 changes: the grid is still built through the `_post()`
accessor, the likelihood is still Dixon-Coles only, covariates stay off, and the
`effective_posterior_hash` is unchanged in meaning and construction.

### The rationale

Production already discards this tail, silently, for this same fixture: the
per-fixture forecast this project publishes truncates and renormalises at exactly
the same 10 goals. D11's gate is what surfaced it. The guard was the first thing
to look at, and what it found is a real property of the published law rather than
a defect introduced by the simulator.

The amendment makes the simulator **more** visible about that tail than
production is, not less: production reports nothing, and after this amendment the
simulator reports the excluded mass for every fixture and names the ones over the
old threshold in the issuance's own limitations note.

The tail is a cold-start artefact of one club with zero archive rows. It is
expected to collapse once Coventry has fitted rows — a forecast, and recorded
here as one so it can be checked later rather than assumed now.

### What is pre-stated

**2e-2 is pre-stated here, in this entry, before any run under the amended rule
and before any `dc_native` number exists.** It is 4× the worst fixture observed
at the opener (0.005365). It still catches the failure mode the original guard
was built for: a mis-scaled rate — λ around 20 — excludes roughly half the mass
and would trip it by more than an order of magnitude.

The flag threshold stays at its preregistered value of 5e-3. Neither number was
chosen after seeing a result under the amended rule, because no such result
exists.

### Recording note

This entry is recorded **before the guard was changed and before any `dc_native`
issuance existed; the commit that changes the guard follows this one.**
