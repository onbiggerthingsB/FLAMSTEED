# EPL table simulator — T9: the CLI, the first 2026/27 issuance, and the gate

**Task:** plan v2 §6 T9 (`docs/superpowers/plans/2026-08-18-epl-table-simulator-v2.md`).
**Branch:** `epl-probe` · **Commits:** `d6a1a91`, `32578e7` · **Date:** 2026-08-19
**Season opens:** 2026-08-21 · **Cutoff run:** 2026-08-21 (zero results, all 20 clubs
from the transition).

**Status: STOP for owner review. The published arm did not run.**

The `dc_native` arm — the arm plan v2 T9 says to publish — **fails closed** at this
cutoff on the D11 excluded-mass guard. One fixture of 380 trips it. This is the
frozen design refusing to publish, not a defect in T9's code, and unblocking it
requires an owner decision that changes a preregistered number. Details in §2.

Everything else T9 asks for is built, tested and demonstrated on the real season:
the CLI's four verbs, the eleven-criterion acceptance gate, and a complete
end-to-end issuance at the real cutoff on the `elo_wdl_bridge` arm, which passes
ten of eleven criteria with the eleventh correctly recorded as not applicable.

---

## Correction (added 2026-08-19, after the owner ruling; nothing above is rewritten)

**The STOP note above understates the blast radius.** It says the `dc_native` arm
fails closed. Two of the three arms do.

`epl.bridge.DCWDLProvider.laws_for` builds its per-particle 1X2 by calling
`epl.particles.fixture_cdfs` on the same book and the same fixture — that is the
whole point of the arm, since its outcome marginal is *exactly* the native arm's.
So the D11 guard trips on `2627:man_city:coventry` for `dc_wdl_bridge` as well,
for the same reason and with the same number. Before the amendment recorded in
`reports/epl_sim_amendments.md`, **only `elo_wdl_bridge` could run at this
cutoff**, because it is the one arm that never touches the particle grids.

That does not change any measurement in §2, the gate record in §3, or the
demonstration issuance in §4: `elo_wdl_bridge` is what was run, and it is what
§4 reports. It changes §5's framing — the decision the owner was asked for
gates both model-side arms, not one — and it means the arm-vs-arm contrast in §4
("the DC arm carries a joint posterior draw per season and should be visibly
less concentrated") was doubly unavailable.

The owner's ruling of 2026-08-19 (D11 v1.0.1) is recorded in
`reports/epl_sim_amendments.md`, entry A1.

---

## 1. What shipped

`epl/simcli.py` (+ `epl/tests/test_simcli.py`, 18 tests). Four verbs:

| Verb | What it does |
|---|---|
| `forecast` | fit → `ParticleBook` → one run per arm → issuance directory → gate |
| `ingest-results` | append to the season results ledger from openfootball or by hand |
| `retro` | delegates to `epl.simretro`'s smoke run |
| `check` | re-runs a written issuance from its own bundle and demands the same numbers |

The forecast path is the live one plan v2 D4/D5/D11 specifies:

- the archive handed to `LiveAnchor` **excludes** the target season, so the anchor
  cannot re-seed from "the rows present";
- the fit store is archive **plus** the season's results ledger (empty at this
  cutoff, so archive-only here);
- `cold_start` is **manifest minus the fitted teams** — the feature panel is built
  first, through the same cached call the fit itself makes, because
  `dcfit.cold_start_clubs` reads played history at or *after* the cutoff and
  therefore returns `[]` at an opener. At 2026-08-21 that yields
  `cold_start = ['coventry']`, `promoted_seed = 1519.61`, 35 fitted teams,
  4,560 training matches, fit 7.1 s.

Artifacts per issuance (`data/epl/sim/issuances/<season>/<cutoff>/`, gitignored):
`output_<arm>.json`, `rows_<arm>.npz`, `envelope.json`, `limitations.md`,
`particles.npz`, `fit.json`, `acceptance.json`, `issuance.json`, `summary.md`.

### Two defects the first live run exposed

Both were found by the gate, not by reading code, and both are fixed in `32578e7`:

1. **The gate re-ran the wrong arm.** `acceptance_gate` fell back to the particle
   book when handed no provider, so re-running a bridge arm asked a `ParticleBook`
   to build `elo_wdl_bridge`; `resolve_provider` refused. `forecast` now passes the
   published arm's own provider. The fallback still exists and still fails loudly —
   a gate that silently re-ran `dc_native` and reported the agreement as the bridge
   arm's would be worse than one that errors.
2. **Per-fixture parity is a DC-native question.** `marginal_parity` compares
   simulated frequencies against the DC production grid; a bridge arm samples an
   outcome model plus the empirical scoreline bridge, a different law by design
   (D18). The criterion is now `SKIPPED` for any arm but `dc_native`, with the
   reason recorded. `SKIPPED` still does not pass the gate.

### One correction to the plan's shorthand

T9 lists "serial and chunked runs reproduce (T5)". That cannot mean *two different
chunk sizes agree*: streams are keyed by `(chunk_index, fixture_ordinal)` (D14), so
chunk size is part of a run's specification and two chunk sizes are two runs — as
T5's own test has it (N=4,000, chunk 1,000, serial vs 2 processes). `check_reproducibility`
therefore compares the **same specification computed three ways** — in-process,
chunk by chunk by hand, and across two processes — plus a seed control that must
move the digest. A dedicated test pins the chunk size as part of the specification
so this reading cannot quietly drift back.

---

## 2. Why `dc_native` did not run — the D11 excluded-mass guard

```
STOP: ExcludedMassTooLarge: man_city v coventry: the 10-goal truncation excludes a
particle-mean 0.00536 of the probability mass, over the 0.005 limit.
```

Deterministic: the same STOP on every attempt, at the same fit (ADVI average loss
1,534.1) and the same seeded cold-start draws.

### The measurement

| | |
|---|---|
| Fixtures over the 5e-3 gate | **1 of 380** (`2627:man_city:coventry`, 0.005365 — 7.3% over) |
| Next worst | `arsenal:coventry` 0.003934, `liverpool:coventry` 0.003426, `man_city:hull` 0.003284 |
| Mean excluded mass, all 380 | 1.55e-4 · 90th pct 3.46e-4 |
| Median **particle** for the failing fixture | 1.9e-4 — about **26×**, 1.4 orders of magnitude, under the gate |
| | *(2026-08-19 correction: this row previously said "four orders of magnitude under the gate". `5e-3 / 1.9e-4 = 26.3158`, which is 1.42 orders. The point stands — the failing fixture's typical particle is nowhere near the gate and a handful of extreme particles carry the mean — and it was overstated by two and a half orders. Recorded in amendment A1-C1; no excluded-mass number changes.)* |
| Worst 10 particles of 1,000 | contribute **42.6%** of the mean; 88 particles exceed 1%, 22 exceed 5% |
| Worst particle (s=953) | λ_home = 10.25, λ_away = 0.90 → P(home > 10 goals) = 0.448 |

Cause: Coventry has **no match anywhere in the 2014/15–2025/26 archive**, so its
att/def come from `ColdStartPosterior` prior draws (D17) with sd ≈ 0.30/0.34 —
range −1.16 to +1.24. A handful of draws put Coventry's defence near −1.1, which
against Man City's attack (mean +0.77) gives λ_home > 10, and those particles
individually lose 25–45% of their mass past the truncation. It is a pure tail
effect of the cold-start prior, not a systematic mis-scale. Every fixture near the
top of the list involves a promoted club.

### What the guard is actually telling us

`PRODUCTION_MAX_GOALS = 10`, and `draw_api.production_grid` truncates and
renormalises at exactly the same 10. So the per-fixture forecast this project
already publishes for Man City v Coventry **also discards that 0.54%** — silently.
D11's gate is what surfaces it, and D11 chose to fail the table run rather than
let the sim quietly discard a tail that production quietly discards.

### Sensitivity (diagnostic only — nothing was changed)

| `max_goals` | mean excluded, worst fixture | fixtures over the gate |
|---:|---:|---:|
| **10 (frozen)** | **0.005365** | **1** |
| 11 | 0.002814 | 0 |
| 12 | 0.001480 | 0 |
| 14 | 0.000404 | 0 |
| 16 | 0.000103 | 0 |

### Why I did not unblock it

Three obvious workarounds are all preregistered decisions, not implementation
details, and each is the owner's call:

- **Raise the 5e-3 threshold.** That is D11's number. Raising it to clear a 7%
  overshoot is choosing the answer first.
- **Raise `max_goals` to 11 or 12.** D11 explicitly rejects the WC sim's 12 —
  "so simulated marginals match what production issues". Changing it here breaks
  parity with the published per-fixture forecast, which is the whole point of the
  `marginal_parity` criterion.
- **Reseed or shrink the cold-start draws.** D17 freezes cold start's mechanism
  and rejects refitted hyperpriors for v1 (that is v1.1 R10).

A fourth option exists and is arguably the cleanest: **keep max_goals = 10 and
renormalise, but record the excluded mass per fixture in the envelope** — i.e.
treat the guard as a reporting requirement rather than a hard stop, on the grounds
that production already does exactly this. That is still a change to D11 and still
the owner's call.

**Owner decision needed before any `dc_native` issuance exists.** Note the guard
is a property of *this* cutoff: once Coventry has played a few matches the prior
draws are replaced by fitted ones and the tail collapses. It may resolve itself by
MW3–MW6 without any decision at all — but that is a forecast, not a plan.

---

## 3. The acceptance gate — T9's eleven criteria, criterion by criterion

Run at `2026/27` cutoff `2026-08-21`, N = 20,000, S = 1,000, seed 20260611, on the
`elo_wdl_bridge` arm (see §4 for why that arm). Full record:
`data/epl/sim/issuances_partial/2026_27/2026-08-21/acceptance.json`.

| # | Criterion (T9 wording) | Gate name | Result | Evidence |
|---|---|---|---|---|
| 1 | 20 clubs / 380 fixtures validate | `clubs_and_fixtures` | **PASS** | 20 clubs = manifest clubs; 380 fixtures; complete double round-robin; every club 38 matches, 19 at home; played ∪ unplayed covers the fixture set |
| 2 | every promoted club completes a season | `promoted_complete` | **PASS** | Coventry / Hull / Ipswich each 38 fixtures, 19 home, matrix rows sum to 1 ± 1e-8, no negative mass. Diagnostic: **1.401 expected relegations** among the three promoted — inside R3's 0.9–2.0 sanity band |
| 3 | fixture-level simulated marginals match production within MC error | `marginal_parity` | **SKIPPED** | Not defined for a bridge arm (D18). It is the criterion the blocked `dc_native` run would have supplied; **still outstanding** |
| 4 | tiebreak oracle suite passes (T3) | `tiebreak_oracle` | **PASS** | `pytest epl/tests/test_table.py -q` as a subprocess, returncode 0 |
| 5 | played fixtures + known adjustments reconstruct the cutoff table | `cutoff_table` | **PASS** | Opener is degenerate (0 played), so a witness was run: 2025/26 at 2026-01-01, **186 played**, 516 points, zero mismatches. `non_degenerate_anywhere = true` |
| 6 | matrix and threshold counts agree | `matrix_and_markets` | **PASS** | Rows/cols max error 2.22e-16; every consequence market equals its column sum to **0.0**; all D10 per-sim identities hold |
| 7 | serial and chunked runs reproduce | `serial_equals_chunked` | **PASS** | N=20,000, chunk 2,000, 10 chunks: deterministic ✓, chunk concatenation ✓, 2-process parallel ✓, seed control moved the digest ✓ |
| 8 | MC uncertainty beside every headline | `mc_uncertainty` | **PASS** | Every club × market carries finite `p`/`se`/`outer`/`inner`; worst market SE **0.00366**; outer/inner identity error 3.4e-21 |
| 9 | limitations explicit | `limitations` | **PASS** | All five sections present; the run's own unresolved masses, played/unplayed counts and rule id found in the text |
| 10 | `git diff --stat -- src scripts` empty | `src_scripts_untouched` | **PASS** | empty against `main` |
| 11 | LOCK VALID after commit | `lock_valid` | **PASS** | `scripts/oa_lock.py` first line `LOCK VALID` |

**Gate verdict: NOT PASSED — 0 failed, 1 skipped.** A skipped criterion does not
pass the gate; an unrun check is not a passing check.

### Reproducibility, independently verified

Rebuilding the issuance from scratch — new fit, new bridge, new provider — gives
the recorded number digest bit for bit:

```
recorded    26e48f521c77c21a67c3843fc49d4037e78e9b962c455db6e70a621e938ba101
recomputed  26e48f521c77c21a67c3843fc49d4037e78e9b962c455db6e70a621e938ba101
effective posterior hash ✓   bridge hash ✓
```

The `check` verb refuses this issuance by design — `published arm 'elo_wdl_bridge'
cannot be rebuilt from the bundle alone: only the DC-native arm is fully described
by the particle book`. That is a real gap in `check` for bridge arms; it needs the
archive and the bridge, not just `particles.npz`. Recorded, not fixed (out of T9's
scope).

---

## 4. The demonstration issuance (NOT the forecast)

To exercise the pipeline end to end on real 2026/27 data with `dc_native` blocked,
one arm was run at the real cutoff. It is written to
`data/epl/sim/issuances_partial/` — a deliberately non-canonical path — and every
artifact labels its arm.

**This is not the 2026/27 forecast.** It is the `elo_wdl_bridge` comparator: static
frozen-Elo ratings at the cutoff, an ordered-logit head fitted on pre-cutoff
history, and the empirical P(scoreline | outcome) bridge. It carries no parameter
uncertainty by construction (outer MC variance 2.2e-9 vs inner 3.8e-6), so its
tails are narrower than the model's would be. Nothing here has been scored against
the preregistered retrospective.

Reported only so the owner can see the surface — arm run in 0.8 s, whole issuance
16.5 s:

`±` is one cluster-by-particle Monte-Carlo standard error (plan v2 D15), in
percentage points for probabilities and in points for E[points]. It is
Monte-Carlo error only and says nothing about model error.

**2026-08-20 correction note (Codex review of ce82484 #2).** The sentence above
was ADDED to this report after it was issued — the `±` column existed and was
unlabelled — and was not marked as a post-issuance edit at the time, unlike the
dated arithmetic corrections elsewhere in this file. No number in the table
below changed: the edit names what the existing column already was. Recorded so
that the rule holds without exception — every edit to an issued report is dated
in the report itself.

| Club | P(champion) | P(top 4) | E[points] |
|---|---:|---:|---:|
| arsenal | 58.3% ± 0.35 | 98.6% ± 0.08 | 80.9 ± 0.05 |
| man_city | 36.1% ± 0.34 | 97.1% ± 0.12 | 77.9 ± 0.05 |
| liverpool | 2.0% ± 0.10 | 53.3% ± 0.35 | 63.9 ± 0.05 |
| man_united | 1.9% ± 0.09 | 49.8% ± 0.35 | 63.5 ± 0.05 |

| Club | P(relegated) | E[points] |
|---|---:|---:|
| tottenham | 53.8% ± 0.37 | 37.8 ± 0.05 |
| coventry | 47.4% ± 0.36 | 38.9 ± 0.05 |
| hull | 46.6% ± 0.36 | 39.1 ± 0.05 |
| ipswich | 46.1% ± 0.36 | 39.1 ± 0.05 |

Two things an owner should look at rather than take on trust:

- **Tottenham at 53.8% relegation, above all three promoted clubs.** That is the
  frozen Elo table talking, through a head with no parameter uncertainty. It may
  be right; it is certainly the sharpest claim on the page and it comes from the
  comparator arm, not the model.
- **Concentration at the top** (58/36 between two clubs) is what a static-strength,
  no-parameter-uncertainty arm does. The DC arm carries a joint posterior draw per
  season (D1) and should be visibly less concentrated. That contrast is one of the
  things the blocked run would have shown.

Tie diagnostics at the relegation boundary (the direct "do scorelines matter" test,
D18/§5.6): 17|18 decided **81.8%** on points alone, **17.2%** on goal difference,
**0.96%** on goals scored, 0.07% on head-to-head points, 0.005% on head-to-head
away goals, 0.01% unresolved play-off, **0.0%** three-or-more-way. At the title:
95.6% unique, 4.2% GD, 0.18% GF.

Positional thresholds only. No competition is named anywhere. No betting content,
no odds, no market comparison.

---

## 5. What the owner is being asked to decide

1. **The D11 excluded-mass guard at this cutoff** (§2). Four options, all of them
   amendments to a preregistered decision. Until one is chosen there is no
   `dc_native` issuance and `marginal_parity` stays unverified on the real season.
2. Whether to re-attempt at a later cutoff instead (MW3–MW6), on the expectation
   that Coventry's fitted parameters replace the prior draws and the tail collapses.
3. Whether the demonstration issuance in `data/epl/sim/issuances_partial/` should
   be kept, deleted, or promoted — my recommendation is **kept and not published**.

Nothing has been published anywhere. `docs/obligations.md` is untouched. Both
commits verified: `LOCK VALID`, `git diff --stat main -- src scripts` empty,
`pytest epl/tests -q` 322 passed.
