# ASSUMPTIONS

Every modeling assumption, logged as it is made. North-star appendix entries are
carried first; the Phase 1 section holds stubs whose concrete values are filled
by the tasks noted (Elo hyperparameters → Task 5; StatsBomb release → Task 9).

## North-star seed entries

1. **Data-revision caveat** — bitemporal store; if snapshots unobtainable, backtest features are revision-contaminated and overstate edge; live forward-test is the trustworthy number.
2. **Config-count pre-registration** — the number of configurations tried is logged before looking at the lockbox.
3. **Permutation-null spec** — ≥100 shuffles, RPS/log-loss vs market+base-rate, judged by percentile.
4. **Foresight RED thresholds** — explicit in config; gross-leak alarm only.
5. **Global-operation rule** — no statistic fit across data the prediction shouldn't see, even when raw rows pass the cutoff check.
6. **Reproducibility caveat** — bit-reproducible for data+sim; reproducible-on-fixed-hardware for inference.
7. **Benchmark de-vig chosen by data** — best-calibrated de-vig of the close is canonical; Shin is the prior.
8. **Fair-price definition + wide-spread non-bet** — Betfair VWAP-near-close canonical; wide spread → non-bet.
9. **Fair-play / lots tiebreaker** — not cleanly modelable; treated as a documented near-random secondary tiebreaker (it rarely binds; we won't fake precision).
10. **Match-universe coverage caveat** — historical-odds coverage by team tier is mapped; backtest selection bias vs the minnow deployment distribution is documented.

## Phase 1

- **Elo hyperparameters (pinned, Task 5).** Implemented in `src/wcmodel/data/elo.py`
  (`compute_elo_history`), parameters read from `config.yaml` `elo:`. Pinned values:
  - `initial_rating = 1500` — every team's starting rating (debutants included).
  - `home_advantage = 100` rating points, added to the home side's rating in the
    expectancy unless the match is `neutral` (then 0).
  - `k_base = 40`, scaled by an importance multiplier `k_by_match_type`:
    `wc_finals 1.0`, `continental_championship 0.9`, `wc_qualifier 0.8`,
    `continental_qualifier 0.8`, `nations_league 0.7`, `friendly 0.4`, `other 0.5`.
    An unrecognised `match_type` falls back to the `other` multiplier (the
    results→match_type tier wiring is Task 6 / Task 11; this module only reads the
    `match_type` input column and does not import the Task-6 tiers).
    **Effective K** (= `k_base · multiplier`): **WC finals = 40**, WC qualifier = 32,
    continental championship = 36, continental qualifier = 32, Nations League = 28,
    **friendly = 16**, other = 20.
    - **K is PROVISIONAL, NOT frozen — a pre-counted Phase-4 tuning config.**
      Canonical World Football Elo uses **K = 60** for WC finals; we currently run
      **K = 40** (`k_base 40 × wc_finals 1.0`) as a provisional default — neither a
      blessed choice nor to be flipped to 60 on intuition. **K ∈ {40, ~50, 60} is one
      of the pre-registered Phase-4 configs**, chosen by out-of-sample RPS on the
      locked-box (north-star §4.6), under the same pre-counted discipline as the
      de-vig method and the Dixon-Coles-vs-bivariate-Poisson selection. The
      provisional volatility threshold **T (currently the empirical p95 = 16.5)** is
      likewise a pre-counted tuning config, calibrated **jointly** with K and the
      prior strength — none of the three is frozen separately.
      **Rationale (record):** we went Bayesian precisely so the *prior* handles
      low-information shrinkage. A low K already over-smooths Elo; stacking model-side
      shrinkage on top risks **double-damping** and staleness to genuine form changes.
      So K, the volatility threshold, and prior strength must be calibrated *together*
      on the lockbox — not frozen on intuition. K = 40 stands only until that
      calibration; this entry tags it provisional, it does not bless it.
  - Margin-of-victory index = **World Football Elo goal-difference scheme**:
    `G = 1` for a goal margin ≤ 1, `1.5` for a margin of 2, else `(11 + margin)/8`.
    `G` at margins **1/2/3/5/7 = 1.0 / 1.5 / 1.75 / 2.0 / 2.25**. The resulting
    **max single-match update magnitude** `K·G·|W−E|` (taking `|W−E| → ~0.95` for a
    big upset) at those margins is, for **WC finals** (K = 40):
    **38 / 57 / 66.5 / 76 / 85.5** pts, and for **friendlies** (K = 16):
    **15.2 / 22.8 / 26.6 / 30.4 / 34.2** pts. The absolute per-update ceiling
    (`|W−E| → 1`, margin 7, G = 2.25) is **≈ 90** at WC and **≈ 36** at a friendly.
  - Expectancy/update: `dr = home_pre − away_pre + ha`; `E = 1/(1 + 10^(−dr/400))`;
    `rating_post = rating_pre + K·G·(W − E)` with `W ∈ {1, 0.5, 0}` (win/draw/loss).
  - `provisional_games = 5` (see debutant / data-driven-provisional note below).
  - `provisional_volatility_threshold = 16.5` rating-pts and `volatility_window = 10`
    (the recent-volatility branch of `provisional` — **empirically derived from the
    real Elo-delta distribution**, see the data-driven note below).
  - **Point-in-time.** `rating_pre` (the pre-match rating, knowable at kickoff) is the
    leakage-safe feature; `rating_post` is the post-update rating and is never a
    same-match feature.
- **Debutant / new-team handling (pinned, Task 5 — per user decision).** Debutants start
  at the **same** `initial_rating` (1500), **not** a faked-low point estimate. Their first
  `provisional_games = 5` matches are flagged `provisional = True` as a pure
  low-information marker. The minnow uncertainty is carried by the **Phase-2 prior**, not
  by rigging the rating. (The earlier `initial_rating_debutant: 1300` line was removed.)
- **Data-driven `provisional` — count OR recent volatility (pinned, RIDER 1).** `provisional`
  is no longer just a debutant counter: it is True if **`rated_match_count < provisional_games`
  (=5)** OR **`recent_rating_volatility > provisional_volatility_threshold` (=16.5 rating-pts)**.
  This catches the case a pure count misses: a **minor nation with a long but sparse/erratic
  history** has the same low-information problem as a debutant yet would escape a count-only
  flag.
  - **The metric is a WINDOWED STDDEV, not a single delta.** `recent_rating_volatility` is the
    **population std of the team's last `volatility_window` (=10) rating deltas**
    (`rating_post − rating_pre`), computed **causally from matches strictly BEFORE the current
    one** (the per-team delta list is appended only *after* each row's flag is emitted) — so it
    is point-in-time, never peeks at the current or any future match. The threshold is therefore
    on a **stddev-of-10-deltas**, NOT on a single-match update. (The prior config's "a single
    international Elo delta is bounded ~±80, so std tops out ~80" framing was the **wrong scale
    entirely** — it reasoned about single-update magnitude, but the flag thresholds a *window
    stddev* whose empirical max is only ~30; see below.)
  - **Threshold rationale — EMPIRICALLY DERIVED from the real martj42 distribution (not
    test-fit).** The prior value `40.0` was reverse-engineered to make a *synthetic* test
    fixture (alternating 8-0/0-8 thrashings vs perpetually-fresh opponents, window-std ≈ 51)
    fire. That fixture does not occur in real football, so **`40.0` flagged 0.00% of real
    team-match states — a decorative flag, the exact failure RIDER 1 exists to prevent.** We
    re-derived the threshold by computing the windowed-stddev metric across **ALL teams over the
    whole martj42 history** (the CC0 international-results feed via `sources/results`; 49,296
    *played* matches 1872–2026 after dropping unplayed/NaN-score WC-2026 fixtures; **98,256
    evaluable team-match states** with ≥1 prior delta) using `compute_elo_history`. The
    **empirical distribution of the rolling stddev-of-last-10-deltas (rating pts)** is:

    | metric | median (p50) | p75 | p85 | p90 | p95 | p99 | max |
    |---|---|---|---|---|---|---|---|
    | stddev-of-10-deltas | 10.2 | 12.5 | 13.9 | 14.9 | **16.5** | 19.4 | 30.0 |

    (Stable across full-window-only and the modern 1990+ subset: p95 ≈ 16.4 in all three.) The
    distribution **saturates far below the single-update ceiling** (~90 at WC, see the K·G
    figures above) because a real 10-match window mixes low-K friendlies/qualifiers (K = 16–32),
    near-1 goal-difference multipliers, and small `|W−E|` vs well-estimated opponents — the
    pathological all-max-thrashing window never materialises.
  - **Chosen point on the distribution: p95 → `T = 16.5` rating-pts.** We flag the **most-volatile
    ~5% tail** of team-match observations as low-information. At `T = 16.5` exactly **4.9%** of the
    98,256 evaluable states are flagged. **Physical interpretation:** *a team whose recent
    per-match rating swings have a stddev > 16.5 points — vs a typical settled team at the
    ~10-point median — is treated as low-information (provisionally rated).* The cut sits well
    above the median (10.2) and p75 (12.5) of settled teams, so well-estimated sides are **not**
    flagged (a steadily-favoured strong side that wins 2-0 every match has window-std ≈ 2; 16
    draws → ≈ 0), while a genuinely erratic side that alternates wins and losses by two goals
    (window-std ≈ 25, in the p99.9–max tail) **is** flagged. The value **changed from 40 → 16.5**
    (a corrected *scale*, not a tweak). `volatility_window` is unchanged at 10. The derivation is
    reproducible via `scripts/derive_volatility_threshold.py`.
  - **Confirm propagation — Phase-2 prior MUST widen for `provisional` teams (a Phase-2
    acceptance criterion).** `features.build` **emits the `provisional` column** (it carries
    straight from `compute_elo_history` through the panel; guarded by
    `test_build_emits_provisional_column`). The flag is only meaningful if **Phase 2 widens its
    prior for `provisional` teams** — otherwise the flag is decorative. This is a binding
    Phase-2 acceptance criterion, recorded here so it cannot be silently dropped.
- **Elo-baseline coherence (single Elo, pinned, Task 5).** There is exactly ONE Elo:
  `compute_elo_history` produces the ratings used BOTH as the model feature AND as the
  Phase-4 naive baseline — there is no second, divergent Elo. The baseline
  (`elo_1x2_baseline`) consumes those same ratings via the pinned mapping
  (`draw_base = 0.28` from `config.yaml` `baseline:`):
  `ha = 0` if neutral else `home_advantage`; `dr = rating_home − rating_away + ha`;
  `E = 1/(1 + 10^(−dr/400))`; `p_draw = draw_base · (1 − |2E − 1|)`;
  `p_home = E − p_draw/2`; `p_away = (1 − E) − p_draw/2`; each clipped to ≥ 0 and
  renormalised to sum 1. Draw mass peaks at `draw_base` for an even match and shrinks as
  the tie expectancy gets lopsided.
- **StatsBomb xG point-in-time (versioned, pinned, Task 9).** Open Data is static and
  **append-mostly** (new competitions added over time; data for an already-covered match
  is stable), so for COVERED matches xG is **point-in-time, not revision-contaminated**:
  `valid_as_of == observed_at == match_date`, store policy POINT_IN_TIME (like results).
  The client exposes no per-pull git tag, so the release marker is the installed client
  version + pull date — `config.yaml` `statsbomb.open_data_version = "statsbombpy-1.18.0@2026-06-03"`
  — i.e. point-in-time "as close as release versioning allows".
  - **Coverage-gated, never imputed (pinned).** xG is NULL-safe. `normalize_match_xg`
    (`src/wcmodel/data/sources/statsbomb.py`) emits one row per `(match_id, team)` that
    has xG (aggregating shot `shot_statsbomb_xg`), each flagged `xg_covered = True`; a
    match-team with no shot data produces **no row** (absent / NULL) — never a fabricated
    `xg = 0`. The team-level gap is enumerated by `enumerate_coverage`
    (`src/wcmodel/data/coverage.py`); `write_coverage_report` writes the covered set, the
    uncovered **gap set**, and a CSV to `reports/phase1_statsbomb_coverage.md`.
  - **Network boundary / offline tests.** Only the thin `fetch_competitions` /
    `fetch_matches` / `fetch_shots` wrappers touch the network (`statsbombpy` → GitHub);
    `normalize_match_xg` and `enumerate_coverage` are pure and tested **offline** against
    `fixtures/statsbomb_*.json`.
  - **Coverage reality (Task 9 live pull, corrected).** Selecting on
    `competition_international == True` (the dedicated international-competition flag — NOT
    the stale `country_name == "International"` filter, which silently drops the continental
    cups StatsBomb files under their confederation), StatsBomb's *free* international
    men's-senior xG footprint is the **8 FIFA World Cup finals editions** (1958, 1962, 1970,
    1974, 1986, 1990, 2018, 2022) **plus UEFA Euro 2020 & 2024, Copa America 2024, and the
    African Cup of Nations 2023** — i.e. **12 men's-senior competition-seasons covering ~78
    distinct national teams**. There are **NO qualifiers, NO friendlies, and no Nations
    League** in the free Open Data. So the qualifier/friendly tail is absent (NULL, never
    imputed), **but** the continental-cup participants — a meaningful slice of mid/lower-tier
    sides (e.g. the full AFCON-2023 and Copa-2024 fields) — **ARE** covered. Practically, xG
    is still NULL across the entire (qualifier/friendly/Nations-League-heavy) backtest window
    yet available for finals + continental-cup matches. This compounds the post-2026-01-20
    FBref/Opta xG collapse (SOURCES.md) and still reinforces north-star seed #10 (minnow edge
    validated by live forward-test, not the backtest, since the deployment distribution is
    qualifier/Nations-League-heavy). The report is regenerated by
    `scripts/gen_statsbomb_coverage.py` (committed for reproducibility, so the filter cannot
    silently drift again). The **48-team WC-2026 intersection is GATED** on the user-provided
    `config/tournament_2026.yaml` draw file; the final 48-team gap analysis is produced in
    Task 13 once that file lands.
- **xG is sparse prior-enrichment, NOT a model driver (pinned, Codex P3 / RIDER 3).** State
  plainly: **this is an Elo-anchored model with sparse xG enrichment, NOT an xG-driven
  model.** The Elo feature (`elo_pre`) is present on every row; xG is an *optional*
  prior-enrichment feature available only on the handful of covered (major-tournament /
  continental-cup) matches. Consequence for honesty: **the backtest CANNOT evaluate xG at
  all** — xG is NULL across the *entire* qualifier/friendly/Nations-League backtest window
  (the deployment distribution), and is present only on finals + continental-cup matches that
  do not appear in the backtest universe. The NULL-safe-not-imputed rule (above) therefore
  stays correct precisely *because* xG is enrichment, not a driver: a backtest row with no xG
  is the norm, contributes `0.0` (not `NaN`) to `revision_contaminated_exposure`, and is
  handled by the Phase-2 shrinkage prior. Any xG signal is validated by the live
  forward-test, never claimed from the backtest.
- **Time-decay & feature window (pinned, Task 11/12).** `config.yaml` `windows:` pins the
  two feature-recency parameters consumed by `features.build` (north-star §4.3):
  - `feature_years = 4` — the model/feature window. A built row carries
    `in_feature_window = (cutoff − date).days ≤ feature_years·365`; rows older than the
    window are flagged out (a feature, not a hard crop).
  - `decay_half_life_days = 365` — exponential time-decay half-life. Each row carries
    `decay_weight = 0.5 ** (age_days / decay_half_life_days)` (a match exactly one half-life
    old weighs 0.5). `age_days = (cutoff − date).days`, always ≥ 0 by the strict `date <
    cutoff` filter — no future row is ever weighted.
  - The **backtest** window is *separate* and is **NOT cropped** to `feature_years` (it keeps
    pre-window history from `odds_start`) — see `windows.py` / Task 12.
- **Cutoff resolution — date-only match knowability vs intraday odds (pinned, Fix 1).**
  Match results (martj42) are stored at **date resolution** (midnight). A match on date `D`
  is therefore **not knowable until `D+1 00:00`** — its real kickoff can fall *after* an
  intraday bet-time cutoff on `D`, so a same-day result must never feed a feature panel cut
  at a `D`-daytime cutoff. `features.build` enforces this by **flooring the cutoff to its
  day** (`cutoff_day = pd.Timestamp(cutoff).normalize()`) and filtering the results panel to
  `date < cutoff_day`; the day-floored slice feeds **both** the Elo recompute **and** the
  emitted rows, so a same-day match enters neither (e.g. `build(cutoff="2024-06-20 12:00")`
  excludes a match dated `2024-06-20` but still includes `2024-06-19`). This day-normalization
  is a **features-layer convention for date-only match knowability ONLY**. It is deliberately
  **NOT** applied to `store.read` (which compares at true `observed_at`/`valid_as_of`
  resolution) nor to any **intraday-timestamped source**: The Odds API snapshots carry real
  intraday `bet_time`/`close` timestamps and are read at **TRUE resolution** — day-normalizing
  them would misalign entry-vs-close and corrupt CLV. (`sources/odds.py` timestamp handling is
  untouched.)
  Cutoffs are interpreted in **UTC** for the day-flooring step. A **tz-aware** cutoff (e.g. an
  Odds API `Z`/UTC timestamp) is first converted to UTC and made tz-naive
  (`cutoff = cutoff.tz_convert("UTC").tz_localize(None)`) **before** `cutoff.normalize()`, so it
  aligns with the tz-naive date-only (midnight) match dates — otherwise the
  tz-aware-vs-tz-naive comparison raises in pandas. The same-day-excluded / prior-day-included
  semantics are **unchanged** by this coercion (e.g. `build(cutoff="2024-06-20T12:00:00Z")`
  behaves like the tz-naive noon cutoff: excludes `2024-06-20`, includes `2024-06-19`). The
  intraday **odds-store read** at tz-aware intraday cutoffs is a separate, Phase-4 concern and is
  out of scope for this features-layer day-flooring.
- **Played filter — unplayed/NaN-score fixtures are excluded from features and Elo
  regardless of date (pinned, #4 gate).** An UNPLAYED fixture (null `home_score` or
  `away_score`) is a *schedule* entry, not a *result*: it has no outcome, hence no rating
  delta and no label. `features.build` drops every such row **immediately after** the
  `date < cutoff_day` filter and **before** `compute_elo_history` — so it enters neither the
  emitted panel nor the Elo input — **even when its date is before the cutoff.** This makes
  two classes of row leakage-safe at the cutoff boundary: (1) an **in-progress** tournament
  fixture (kickoff on day `D-2` but still scoreless at a day-`D` cutoff), which `date <
  cutoff_day` alone would admit as an as-of feature carrying a NaN label; and (2) the
  **future-dated, not-yet-played WC-2026 group rows** ingested into `results`
  (`ingest_wc_group_fixtures`, NaN scores) — excluded by date at a pre-WC cutoff, and
  *additionally* excluded by THIS filter at a mid-tournament cutoff where their date has
  passed but they have no result. The **TBD-knockout** rows never reach the store at all (only
  the 72 group fixtures are ingested; the 32 knockout fixtures stay as bracket *structure
  placeholders* — `2A`/`W74`/`3rd-ABCDF` — in `config/tournament_2026.yaml` for Phase 3), so
  no placeholder token can appear in any team column. Dropping unplayed rows before the Elo
  recompute also prevents a NaN score from poisoning the per-cutoff ratings. (Existing
  scored-fixture tests are unaffected; the WC in-progress leakage test proves the boundary.)
- **No imputation — every missing feature is NULL (pinned, Task 11).** `build` NEVER fills a
  missing feature with `0` / mean / forward-fill / anything. Concretely: an uncovered match
  (no StatsBomb xG) → `xg_for`/`xg_against = NaN`, `xg_covered = False`; a city absent from
  the venue table (sparse historical city→coord coverage) → `travel_km`/`altitude_m` (and the
  climate placeholders) `= NaN`; a team's first fixture in the slice → `rest_days = NaN`.
  Absence of a whole source is a NULL-safe no-op, not contamination (it contributes `0.0`, not
  `NaN`, to `revision_contaminated_exposure`). (The xG-specific form of this rule is also
  recorded under the StatsBomb entry above; stated here as the panel-wide invariant.)
- **Tier bands from point-in-time computed-Elo.** Strength band is the computed-Elo
  percentile as-of the match cutoff (never as-of-today; bands may shift across the
  window). Uses computed-Elo, not the revised FIFA ranking.
- **COVID tag.** 2020–21 internationals (config `covid.start`/`covid.end`) are tagged
  COVID-distorted (empty-stadium era); tagged, not blended.
- **Friendlies are a separately-reportable tier (pinned, Codex P3).** Friendlies are
  **never weighted equal to competitive matches.** Two mechanisms enforce this: (1) the Elo
  K-importance multiplier already down-weights them (`k_by_match_type.friendly = 0.4`, the
  lowest band — see the Elo entry), and (2) **Phase-4 reporting stratifies on match type**,
  so friendly performance is reported as its own tier and never folded into a blended
  competitive headline. The down-weighting alone is not the whole guarantee — the
  separately-reportable-tier assumption must be stated explicitly (it is a §6 tier tag and a
  Phase-4 reporting contract, not just a K-factor).
- **`current_only` policy scope.** The `current_only` (revision-contaminated) policy
  applies **only** to deferred optional sources (market values / rosters); the Phase 1
  clean core has no active `current_only` source.
- **`read(cutoff)` boundary guarantee — POINT_IN_TIME vs CURRENT_ONLY (pinned, Codex P2).**
  The exclusive-of-the-future cutoff boundary is the **POINT_IN_TIME** guarantee: `store.read`
  returns, per logical key, only the latest row with `observed_at <= cutoff` **AND**
  `valid_as_of <= cutoff` (look-ahead impossible by construction), flagged
  `revision_contaminated = False`. **CURRENT_ONLY deliberately returns the latest snapshot
  per key regardless of `cutoff`** (the spec §4.2 contaminated fallback: only the current
  revised state is obtainable), with every row flagged `revision_contaminated = True` so
  Phase 4 can compute a per-bet contamination exposure — i.e. `observed_at > cutoff` is
  *expected*, not a bug, under this policy. **No clean-core Phase-1 source uses
  CURRENT_ONLY** (it is reserved for the deferred optional sources above), so the practical
  leakage surface of the contaminated fallback is **zero**.

## Phase 2 — Bayesian scoreline model

Every load-bearing decision in the Phase-2 scoreline model (`src/wcmodel/model/`),
plus the follow-ups deferred to Phase 4. Implemented on branch
`phase2-scoreline-model`; spec
`docs/superpowers/specs/2026-06-03-phase2-bayesian-scoreline-design.md`.

- **Independent prior — Elo is NOT a prior or covariate in the model (pinned, spec §1.1).**
  The scoreline model learns each team's attack/defense (`att`/`def`) from **results**
  via a **hierarchical shrinkage prior** (per-team Normal around a shared hyper-mean with a
  learned scale), with a **soft sum-to-zero centering** on `att`/`def` for identifiability
  (a zero-sum soft constraint, not a hard pivot). Elo is **never** an anchor, mean, or
  covariate of that prior. Rationale: Elo is itself derived from results, so anchoring the
  prior to Elo *and* fitting the likelihood on results would use the same data twice
  (double-counting / the double-damping flagged in Phase 1). "We went Bayesian so the
  *prior* handles low-information shrinkage" — the hierarchical prior + provisional-widening
  does that job. **Computed-Elo stays the Phase-4 naive baseline** (`compute_elo_history` →
  `elo_1x2_baseline`), a separate independent estimate the model is scored against — there
  is exactly one Elo and it never enters the model.
- **Both likelihoods behind one `ScorelineModel` interface — DC-vs-BP is a pre-counted P4
  lockbox DOF (pinned, spec §1.2 / §7.4).** Phase 2 ships **both** the Dixon-Coles low-score
  correction (a `tau`-reweight of the four `{0,1}×{0,1}` cells of the independent-Poisson
  grid) **and** the bivariate-Poisson (a shared `λ3` covariance term), behind one
  `ScorelineModel` ABC (`scoreline.py`) with a common `fit`. Both are **scipy-verified**
  against their reference pmfs (`likelihoods.py`). Phase 2 does **NOT** pick the winner: the
  empirical Dixon-Coles-vs-bivariate-Poisson choice is a **pre-counted Phase-4 lockbox
  degree of freedom** (DOF #8 below), decided by out-of-sample calibration, under the same
  pre-registration discipline as the de-vig method and Elo K.
- **`_TAU_FLOOR` soft barrier for Dixon-Coles (pinned).** The DC `tau` correction can go
  `<= 0` for an extreme combination of unbounded Poisson rates × `rho`; we floor it at
  `_TAU_FLOOR = 1e-12` **inside the log** so NUTS receives a **finite penalty** (a soft
  barrier) rather than a `-inf`/NaN gradient — it is a **no-op for any realistic goal
  rate**, biting only in the pathological tail. The model additionally bounds `rho` with a
  **TruncatedNormal** prior so the posterior keeps `rho` small (DC is a low-score
  *correction*, not a free covariance). At **predict** time the DC grid is a QUASI-likelihood
  (the `tau`-reweight does not integrate to a proper joint pmf), so each per-draw grid is
  **renormalized**, and any residual `tau<0` cell is **clipped to 0** before renorm so no
  negative probability survives (`posterior.predict_scoreline`). Bivariate-Poisson uses the
  proper joint pmf, so its grid is just exponentiated + renormalized (finite-grid truncation
  only).
- **Provisional-widening — ship BOTH (a) and (c); mechanism AND strength are P4 DOF (pinned,
  spec §7.2; binding Phase-1 acceptance criterion).** A `provisional` team (low
  rated-match-count OR high recent Elo-delta volatility, from Phase 1) MUST carry **more
  predictive uncertainty**, else the flag is decorative. Phase 2 ships **both** arms behind
  `config.model.widening.mechanism`:
  - **(a) likelihood down-weight** — scales that team's match contributions in the
    likelihood (`likelihood_weight`), so the data pins its `att`/`def` less tightly.
  - **(c) predictive-variance inflation** — a widening of the averaged predictive grid
    (`widening.inflate_predictive`) that is **mean-preserving in EXPECTED GOALS** to machine
    precision: a **max-entropy exponentially-tilted** reference whose tilt is **solved so the
    widened grid's marginal means `(E[home], E[away])` equal the original grid's marginal
    means** (no central bias — unlike the rejected uniform-mixture, which shifted the mean).
    It **intentionally widens the scoreline distribution and therefore changes the 1X2
    (home/draw/away) probabilities** — `predict_1x2` integrates the widened grid, so
    reshaping the distribution at a fixed marginal mean redistributes 1X2 mass. That
    less-confident 1X2 shift is **the intended point of widening for a provisional team, NOT
    a bug** — "mean-preserving" means expected goals, **not** the 1X2 fair-price edge.
    Out-of-range `strength` (`<0`/`>1`) **raises** (fail loud, no silent no-op/clip), like
    mechanism (a). Verified mean-preserving (in expected goals) in the widening tests.
  - **Design leans (c)** (widens for the real reason — uncertainty — and keeps all the data),
    but **both the mechanism (a vs c) AND the strength are pre-counted Phase-4 lockbox DOF**
    (#3 and #4 below). The widening **strength is co-tuned with the decay half-life** (#5):
    both encode the *same* recency signal, so tuning them independently would double-count
    recency. **Sizing reality (T0 diagnostic, `reports/phase2_volatility_field_sizing.md`):**
    of the 48-team WC-2026 field, **only 1 (Sweden)** trips the volatility arm and **0** trip
    the few-games arm at the 2026-06-01 cutoff — so widening affects **few** predictions, and
    the (a)/(c) arms are deliberately kept minimal.
- **Inference — ADVI/Pathfinder walk-forward + NUTS final/periodic; periodic NUTS is an
  ADVI-falsely-tight check (pinned, spec §7.5).** `inference.py` exposes a NUTS backend (full
  posterior) and an ADVI backend (mean-field variational, fast) for the per-cutoff
  walk-forward refits. The periodic full-**NUTS** fit is an explicit **`advi_variance_check`**:
  **ADVI mean-field systematically UNDERESTIMATES posterior variance**, and we *depend on the
  posterior width* — it drives both the (c) predictive widening and the Phase-4 stake sizing
  — so a periodic NUTS fit checks that ADVI is not falsely tight. **Pathfinder is unavailable
  in the pinned `pymc 6.0.1`** → the Pathfinder path raises `NotImplementedError` (recorded
  so it is not mistaken for a bug); ADVI is the walk-forward backend until Pathfinder lands.
- **Per-cutoff fit + leakage discipline (pinned, spec §6; Task-9 canary).** `fit(cutoff)`
  consumes **only** `features.build(cutoff)` (the Phase-1 leakage-safe panel: matches strictly
  before the cutoff day, played-filtered) **plus** `count_volatility_arm(cutoff)` — **both read
  only matches `< cutoff`**. No other store table and no future row is read in the fit, so a
  fit at `cutoff` can never peek past it. Specifics:
  - The **provisional set for predict-time (c) widening is the AS-OF-CUTOFF status** (each
    team's would-be provisional flag at its *next* match, via `count_volatility_arm`), **NOT
    the per-match panel flags**. Panel flags are *pre-match* states, so a team provisional only
    in its early history would otherwise be flagged "ever provisional" and widened forever;
    the as-of-cutoff status widens only teams genuinely low-information **now**.
  - `rest_days` is a **predict-time** covariate computed from **only matches that exist at the
    cutoff** (`rest.predict_rest_days`): a team with no prior match in the `< cutoff` slice gets
    **NULL**, never a value inferred from an unplayed future fixture (mirrors the Phase-1
    no-imputation rule and the `rest_days` rider, spec §3/§7.1).
  - **Model-layer leakage canary (Task 9):** the per-cutoff fit is proven **bit-identical** under
    a future-result mutation — the posterior **and** the provisional set are invariant when a
    post-cutoff result is rewritten, in **both** widening modes, with the canary's **teeth
    demonstrated** (a deliberate leak would flip the posterior / the provisional-set membership).
    Plus `rest_days` tz-coercion + explicit played contract are covered.
- **Posterior cache — content-addressed, posterior-group-only (pinned, Task 8).**
  `cache.py` is content-addressed on a **complete** key: the feature-hash + the **full model
  config** (likelihood, prior, widening, inference knobs) + the **global elo block** + the
  **windows** + the inference seed + the git commit. It persists the **`posterior` group
  only** via the **NETCDF3** engine — `arviz 1.1.0` lacks `az.to_netcdf` and there is no
  `netcdf4` backend in the pinned env, so `sample_stats` and `observed_data` are **NOT
  cached**. Consequence (recorded so it cannot be silently violated): **any divergence or
  posterior-predictive check must use a FRESH fit, not the cache** — the cached object is
  posterior-only and carries no sampler stats. (See deferred follow-up (i) for the
  global-elo-vs-`cfg.elo` keying nuance.)
- **Calibration — IN-SAMPLE RPS vs Elo + PPC; out-of-sample is Phase 4 (pinned,
  `calibration.py`).** Phase 2's calibration is an **internal diagnostic, NOT the betting
  bar**: `vs_elo_baseline` scores the model's 1X2 RPS against the leakage-safe Elo baseline
  over the **fitted** matches (so it stamps `in_sample=True`), and `posterior_predictive_checks`
  compares the observed vs model-predicted draw-rate / home-win-rate / mean total goals on the
  fitted panel. **The betting bar (out-of-sample RPS / CLV) is Phase 4.** Per the project rule,
  a **too-good in-sample result (model RPS << Elo RPS) is a SUSPECTED OVERFIT / leakage bug to
  surface, never a win** — the only honest verdict of edge is the Phase-4 walk-forward. The
  Elo baseline in the harness recomputes from the **same `< cutoff` slice** the model fit used,
  so model and baseline are scored on identical information. (RPS literal note: the standard
  3-outcome RPS of `{.5,.3,.2}` with outcome `away` is **0.445**, not the `0.2725` in the task
  draft — the standard formula is the source of truth.)

### Deferred to Phase 4 (recorded explicitly)

- **(i) The `elo` config block is NOT config-threaded — `fit(config=...)` is authoritative for
  the model block + windows, but NOT for elo.** `compute_elo_history`
  (`src/wcmodel/data/elo.py`) and `count_volatility_arm`
  (`src/wcmodel/model/volatility_diagnostic.py`) both read the **GLOBAL** `load_config()["elo"]`
  internally — they take no `config` argument. So `fit(config=...)` controls the **model block**
  (priors / widening mechanism+strength / likelihood / inference knobs) and the **windows**, but
  the **elo block** (K, the volatility threshold `T`, the volatility window) is taken from disk
  regardless of the passed `cfg`. **Phase 4 must thread the elo config** through
  `compute_elo_history` + `count_volatility_arm` so the lockbox can tune **Elo K and the
  volatility threshold `T`** (which calibrate jointly with the prior strength — see the Phase-1
  Elo entry). **And then the posterior cache key must switch to `cfg["elo"]`**: today the cache
  deliberately keys `load_config()["elo"]` (the elo that *actually* determined the posterior,
  since elo is global), precisely because a caller passing a custom `cfg.elo` that diverges from
  disk must NOT be able to record an elo the computation never used (a stale-serve guard,
  `cache.py` lines ~147-169). Once elo is threaded, `cfg["elo"]` becomes the value actually used
  and the key should reference it.
- **(ii) The Phase-4 tuning DOF list (single-use lockbox; more knobs ⇒ more overfit risk).**
  Cross-reference the north-star spec §5.1 pre-registration table. The pre-counted degrees of
  freedom the Phase-4 lockbox calibration may tune are:
  1. **Elo K** (provisional 40; `{40, ~50, 60}` candidates — Phase-1 Elo entry).
  2. **Volatility threshold `T`** (provisional p95 = 16.5; calibrated jointly with K and prior
     strength).
  3. **Widening mechanism** — (a) likelihood down-weight vs (c) predictive-variance inflation.
  4. **Widening strength** — **co-tuned with the decay half-life** (#5; shared recency signal).
  5. **Decay half-life** (provisional 365 days; co-tuned with #4).
  6. **Prior strength** (the hierarchical shrinkage scale; calibrated jointly with K and `T`).
  7. **De-vig method** (best-calibrated de-vig of the close is canonical; Shin is the prior —
     north-star seed #7).
  8. **Dixon-Coles vs bivariate-Poisson** (the likelihood choice).
  9. **Kelly** (stake-sizing fraction — Phase 4 only).

  This is a **single-use lockbox** evaluated once on the locked-box out-of-sample data
  (north-star §4.6); the number of configurations tried is **pre-registered before looking**
  (north-star seed #2). Every added knob raises overfit risk, so the list is fixed here and
  not grown on intuition.

## Phase 3 — Monte Carlo simulation

Load-bearing decisions in the Phase-3 tournament simulator (`src/wcmodel/sim/`).
Implemented on branch `phase3-monte-carlo`.

- **Per-cutoff conditioning + leakage discipline (pinned, Task 6).** `simulate(cutoff, …)`
  (`src/wcmodel/sim/run.py`) runs the WC-2026 simulation CONDITIONED on the results known
  as of the cutoff: it FIXES every fixture played-as-of-cutoff (a group fixture to its
  ACTUAL score; a decided knockout to its ACTUAL winner) and simulates only the unplayed
  remainder via `simulate_tournament`. The played read uses the **EXACT** strict, day-floored,
  tz-coerced `date < cutoff` filter `wcmodel.data.features.build` applies (mirrored
  line-for-line in `_played_as_of`), so there is **no look-ahead** and no cutoff-semantics
  drift between the model-fit layer and the sim layer. Fixing consumes no RNG and the sim is
  seeded, so a leakage-free run is **bit-identical** under a mutation of any post-cutoff
  result (the `tests/sim/test_leakage_sim.py` canary).
- **KNOWN LIMITATION — a penalty-decided knockout cannot yet be pinned (pinned, Task 6 /
  Codex T6 finding).** A knockout that finishes LEVEL after regulation+ET is decided by a
  **penalty shootout**, but the martj42 results adapter (`src/wcmodel/data/sources/results.py`)
  stores only the regulation/ET score and **drops the shootout winner** (martj42 keeps
  shootouts in a separate file this adapter does not ingest). So such a fixture is stored as a
  level draw with **no recorded winner** — VALID data we cannot yet pin to its actual outcome,
  NOT malformed input. The sim therefore **FAILS LOUD** (`simulate_one` raises `ValueError`)
  on a level pinned knockout rather than guessing or randomizing a KNOWN outcome (a penalty
  coin-flip would randomize a known result — wrong for a model whose purpose is correct
  conditioning on known results). **Resolution path:** ingest the shootout winner (or add a
  winner-override column) in the **data layer** before mid-knockout-stage conditioning is used
  for serving/backtest (Phase 4/5). **Pre-knockout cutoffs — the current use — are unaffected**
  (no knockout has been played yet, so no level KO can enter the played set). It is not
  reachable today (no 2026 knockout results exist; there is no production caller of `simulate`
  yet), but it WOULD crash the first time a penalty-decided knockout enters the played set —
  hence the explicit fail-loud + this limitation note.
- **Binding principle — uncertainty enters the sim ONCE (pinned).** Per simulation the ONLY
  sources of randomness are (1) **one posterior draw**, fixed across EVERY fixture of that sim
  (`s = rng.integers(n_draws)` drawn once in `simulate_tournament`, threaded to every group and
  knockout fixture via `simulate_one(..., draw=s)`), which preserves the cross-fixture
  correlation of the shared `att/def/μ/home_adv` (a team strong in one match is strong in the
  next), and (2) the **raw DC/BP scoreline sampling** (`scoreline.sample_score` on the per-draw
  rates). The Phase-2 mechanism-(c) provisional widening is **NEVER** applied in-sim:
  `Posterior.predict_scoreline` / `inflate*` are not called by the sim (`RateBook` exposes the
  RAW per-draw rates). Re-widening per draw would **double-count** the parameter uncertainty
  already carried by the draw AND destroy the per-sim shared-parameter correlation — so it is
  deliberately excluded. (Focal properties #1/#2 in `tournament.py`.)
- **Extra-time 30/90 + penalty 0.50 defaults (pinned; P4-tunable).** Knockout ties resolve via
  extra time then a penalty shootout. Config: `sim.extra_time_scale = 0.3333` (ET ≈ 30/90 of a
  regulation match) and `sim.penalty_home_prob = 0.5` (a no-tilt shootout coin-flip). Under the
  **bivariate-Poisson** likelihood ALL THREE Poisson goal rates — `λ_home`, `λ_away`, AND the
  **shared** `λ₃` — scale by `et_scale` in extra time, so ET is consistently 30/90 of regulation
  (a BP scoreline is generative `X=W₁+W₃, Y=W₂+W₃`, so a partial-scale of `λ₃` is required or the
  shared-goal mass would be mis-weighted; Codex T5 finding). Under **Dixon-Coles** `λ_home`/
  `λ_away` scale but `ρ` does **not** — `ρ` is a low-score **dependence** (tau) parameter, not a
  goal rate. Both knobs are P4-tunable (calibration may revisit the 30/90 and the 0.50).
- **Third-place selection + FIFA Annex-C R32 assignment (pinned; focal Codex target).** When 12
  groups send their 8 best third-placers to the R32, the slot-eligibility sets are **READ from
  the verified `config/tournament_2026.yaml`** (the `3rd-<groups>` feeder tokens), never invented.
  Ranking the 12 thirds (`rank_thirds`: points → GD → GF) selects the best 8; the
  best-8-groups → R32-match mapping is a **LOOKUP** of FIFA's published combination table
  (`config/third_place_assignment.json`: all **495 = C(12,8)** combinations, externally
  validated for bijection + eligibility), because the perfect matching is non-unique across the
  495 cases so FIFA's official assignment is authoritative — there is **no invented mapping**.
  `rank_thirds` consumes RNG **only** on a genuine tie that straddles the **8/9 qualification
  boundary** (more groups share the 8th group's key than there are remaining slots); a tie wholly
  inside the top-8 changes no one's qualification and draws no RNG (Codex T3 RNG-locality).
- **Seeded FIFA tiebreak random tail + `random_tail_rate` (pinned).** After the deterministic
  FIFA tiebreak chain (points → head-to-head → all-group GD → all-group GF), any residual exact
  tie is broken by a **seeded random tail** standing in for FIFA's fair-play points + drawing of
  lots (we do not model fair-play conduct). It is seeded (per-sim child RNG), so it is fully
  reproducible. Its activation is **logged as `SimResult.random_tail_rate`** — the fraction of
  sims in which the tail fired — a **diagnostic, not a probability**: it is **visibly > 0** on a
  near-equal field (frequent all-level groups) and a **small fraction** on a separated field
  (groups usually split on GD/GF). Asserted in `tests/sim/test_convergence.py`
  (equal-strength field ⇒ tail fires on ≈3% of sims; non-degenerate field ⇒ < 5%).
- **N = 20 000 default, per-market binomial MC SE, and the market set (pinned).** `sim.n_sims =
  20000` is the default sample size (config-driven; raise for the final pre-tournament run).
  EVERY market reports a binomial Monte-Carlo standard error **`SE = sqrt(p·(1−p)/N)`** alongside
  the probability (the `SimResult.se` table, same shape as `progression`), so each number carries
  its own ± uncertainty. The market columns are: the SIX headline markets `champion`,
  `reach_final`, `reach_sf`, `reach_qf`, `advance_from_group`, `win_group`; plus `reach_r16` (the
  deepest reach rung kept for the full ladder); plus the FOUR per-group placing markets `first`,
  `second`, `third`, `out` (a partition of each team's group finish). The reach ladder is
  cumulative by depth-from-final, so `champion ≤ reach_final ≤ reach_sf ≤ reach_qf ≤
  advance_from_group` holds **by construction**, and `win_group ≡ first` (emitted as identical
  columns). Convergence is pinned by `tests/sim/test_convergence.py` (probs at N vs 4N agree
  within a documented multiple of `SE_N`).
- **Content-addressed sim cache key (pinned).** A full MC run is cached on disk
  (`wcmodel.sim.cache.cached_sim`) and reused **only** when EVERY output-determining input is
  identical. The key (via the shared `data.cache.content_key`) folds in: the **posterior
  content-hash** (the actual `idata.posterior` parameter VALUES `RateBook` reads + `teams` +
  `likelihood`, not an object identity / config proxy), the **bracket structure-hash** (groups,
  group_fixtures, third_place_slots, knockout_feeders, match_round; group keys canonicalized so
  the key is independent of group **insertion** order, while within-group fixture order is
  preserved as result-affecting content), the **cutoff**, **n_sims**, **seed**, **max_goals**,
  **et_scale**, **pen_home_prob**, the **played-conditioning hash** (the per-cutoff
  `{groups, knockout_results, match_dates}` map), and **git** (HEAD commit **plus** a hash of the
  uncommitted tracked `git diff HEAD`, so an uncommitted sim-code edit also misses — Codex T7
  finding 2; a brand-new UNTRACKED file is not in the diff, so commit or clear the cache when
  iterating). Any change → a different key → a **MISS**, never a stale serve (the P2-T8 lesson:
  an incomplete key returning a result for the WRONG cutoff/posterior/bracket is THE bug to
  avoid).

## Phase 4 — Backtest, CLV & Simulated ROI

- **Build-and-gate odds posture (D1).** The entire backtest/CLV/staking/validation
  machinery is built + fully tested NOW against the real pure-parse odds path
  (`wcmodel.data.sources.odds.parse_snapshot`/`extract_closing_prices`) over the
  hand-built fixture + a clearly-labelled-NON-REAL synthetic-odds harness
  (`wcmodel.backtest.odds_ingest.synthetic_odds_sample`, `is_synthetic=True` +
  `SYNTHETIC — NOT REAL ODDS` provenance, propagated into every `Metrics`). **No
  real odds spend and NO real CLV/ROI number is produced by this phase.** The real
  paid Odds API pull (`fetch_historical`, gated — raises without a key) is a single
  switch behind a SEPARATE explicit funding approval; until then no number off the
  harness is ever reported as an edge (mirrors the Phase-3 snapshot's non-real
  labelling).
- **CLV is the primary number; ROI is the goal; calibration (RPS) is diagnostic,
  never the target** (north-star §0, verbatim). The report leads with CLV
  (beat-the-close rate + avg CLV% = entry/close − 1 on transacted (raw decimal)
  prices — de-vig drives the EDGE, not CLV; `clv.py` compares the prices you
  actually transact at).
- **De-vig selection (lockbox DOF #7).** Shin is the prior/primary; multiplicative
  + power are sensitivity checks; **Buchdahl / odds-proportional is sensitivity-
  only and NEVER promoted** (it manufactures phantom favourite-longshot value) — it
  is not even a choosable method in `devig_select.DEVIG_METHODS`. The best-
  calibrated de-vig of the close is chosen EMPIRICALLY by RPS, not assumed. A
  negative/sign-flipped implied prob, a stale snapshot, or a wide bid-ask → non-bet
  (logged + counted, never silently dropped).
- **Staking (D5).** ¼-Kelly (lockbox DOF #9, `backtest.kelly_fraction=0.25`) ×
  posterior-uncertainty shrink (`1/(1+k·SE)` ∈ (0,1], only ever scales exposure
  DOWN); bet only when `edge > edge_threshold` (2 pp — the TRIGGER, not a DOF).
  Commission: Pinnacle close = margin-in-line, none separate; Betfair = 2% on NET
  winnings (losses unaffected). Outputs ROI / hit-rate / turnover / max drawdown /
  bankroll path, each with seeded bootstrap CIs.
- **Baselines — beat both or say so.** Market-only (the de-vigged close) + naive
  `elo_1x2_baseline` (the SAME computed ratings — the coherence requirement, no
  second divergent Elo), both through the identical settle/RPS path. The report
  asserts whether the model beats BOTH on RPS AND positive ROI.
- **The 9 pre-registered lockbox DOF (D4), pinned (the config budget the lockbox is
  judged against):** (1) Elo K, (2) Elo volatility threshold T, (3) widening
  mechanism a/c, (4) widening strength, (5) decay half-life, (6) prior
  σ_att/σ_def, (7) de-vig method, (8) likelihood DC/BP, (9) ¼-Kelly fraction. The
  edge threshold (2 pp) is the trigger, NOT a DOF. **Lockbox = the final 18% of
  odds-covered history BY DATE, frozen**; a lockbox ROI ≈ the tuned-window ROI ⇒
  the edge is real, a collapse ⇒ overfit. **Permutation null = 200 label shuffles**;
  the model's real RPS must sit at ~the 99th percentile of the null.
- **The single-use lockbox is a MECHANISM, not an adjective (Task 7).** A committed
  pre-registration registry (`config/lockbox.json`) is pinned FIRST — before any
  tuning/evaluation code — recording the held-out boundary as a FROZEN rule (final
  18% by date; `resolved_cutoff_date` written ONCE/immutably when the real universe
  is materialized, else `resolved: false`), the pre-registered config count = the 9
  DOF (listed), and a `used: false` flag. The `LockboxRegistry` harness
  (`backtest/lockbox.py`) flips `used → true` ON DISK on a real evaluation and
  PHYSICALLY REFUSES (`LockboxUsedError`) any second evaluation — even from a fresh
  process / re-loaded registry. Enforcement is persisted disk state, not a comment;
  a RED→GREEN proof shows an in-memory-only flag is caught. Test evals use an
  isolated temp registry so the committed real single-use shot is never burned.
- **Foresight-RED hard-STOP (the "too-good = bug" guardrail, ENFORCED as a test).**
  RED ceilings in `config.yaml` `backtest.foresight_red` (ROI > +10%, beat-close >
  58%, avg CLV > +2% — tight for 1X2-vs-sharp-close); any metric past RED ⇒
  `ForesightRedError` ⇒ STOP and investigate, never celebrate. Treat any too-good
  result as a suspected bug. RED is a COARSE backstop for GROSS leaks, NOT proof of
  cleanliness — a clean pass means nothing on its own; the permutation null (Task 7)
  and the leakage canary (Task 6) are the real catches.
- **Backtest-layer leakage canary (THE GATE, the focal Codex target).** A
  post-cutoff odds OR result mutation must not move any as-of-cutoff
  price/edge/stake/settled P&L; seeded ⇒ bit-identical across the mutation; with
  non-vacuity teeth (a leak WOULD move it). Mirrors the P2 model + P3 tournament
  canaries. Every per-cutoff read is the bitemporal `store.read(cutoff)` + strict
  `date < cutoff`; settle uses the realised result ONLY after the decision, never
  as a feature.
- **D6 must-do plumbing (done in Task 0).** `elo` config is threaded end-to-end
  (`compute_elo_history`, `elo_1x2_baseline`, `count_volatility_arm` all take an
  optional `config`) and the posterior cache key now folds `cfg["elo"]` (not the
  global `load_config()["elo"]`) — so a lockbox K/T sweep invalidates the cache
  correctly and cannot record an elo the computation never used (the P2-T8 stale-
  serve lesson). The per-cutoff Elo recompute is MEMOISED in the walk-forward
  engine (`walkforward.EloMemo`, the `features.build` Phase-4 hook at
  features.py:174) so the O(N)-per-cutoff Elo is not re-paid every fixture; the
  memoised Elo is byte-identical to `features.build`'s.
- **Penalty-decided-KO (D3) — DEFERRED, recorded as a Phase-5 precondition.** The
  data layer drops shootout winners, so `sim.tournament.simulate_one` fails loud on
  a level pinned knockout. The Phase-4 backtest conditions on NO in-tournament
  knockout (WC-2026 hasn't happened; prior WCs aren't in the WC-2026 bracket), so a
  level pinned KO is UNREACHABLE — pinned by
  `tests/backtest/test_d3_unreachable_knockout.py` (every backtest cutoff is
  strictly before the 2026-06-28 KO window; no played WC-2026 knockout is in the
  store). The fail-loud guard stays. **Resolution before Phase-5 live in-tournament
  betting: ingest the shootout winner / a winner-override column.**
- **Reproducibility / compute.** The whole run is content-addressed
  (`cached_walkforward`: store-hash, odds-hash, the full DOF config block, the
  cutoff grid, `odds_start`, git HEAD + uncommitted-diff hash) — no stale serve,
  the P1/P2/P3 cache discipline. Bootstrap + permutation seeds are pinned in config.
- **The backtest is a big-match, revision-contaminated UPPER BOUND.** The obtainable
  sharp-priced universe is skewed to well-covered big matches; the
  minnow/progression tail is thin or absent. Every metric is stratified by tier and
  a thin stratum is a COVERAGE GAP (n < 30), never averaged into a headline. The
  **Phase-5 live forward-test is authoritative** for the minnow/progression edge —
  exactly the markets the thesis targets.
- **Two surfaces (D2).** 1X2 (`h2h`, `predict_1x2`) is PRIMARY + authoritative.
  Tournament-progression/outright (`SimResult` columns: champion / advance_from_
  group / reach-*) is SECONDARY, coverage-gated exploratory — where outright keys
  are unverified/absent it is a coverage gap, not a number.

## Phase 5 — Live Forward-Test, Scanner & Realized-CLV Tracker

- **Build-and-gate live-feed posture (L1).** The entire live pipeline
  (fetch/ingest/decide/scan/clv-tracker) is built + fully tested NOW against the real
  pure-parse odds path (`wcmodel.data.sources.odds.parse_snapshot`) over the fixture +
  a clearly-labelled-NON-REAL synthetic harness (`backtest.odds_ingest.synthetic_odds_sample`,
  `is_synthetic=True`, propagated). **No real odds spend, no real bet, NO real CLV/ROI
  number is produced by this phase.** The live fetch route (`live.odds_live.fetch_live_odds`,
  the regular `GET /v4/sports/{sport}/odds`) is GATED behind an `api_key` (raises
  without it, like `fetch_historical`); flipping the real feed on is the ONE gated
  switch behind a SEPARATE explicit funding approval. `config.live.dry_run` defaults
  TRUE so a fresh run can never spend or imply a real bet.
- **Funding-flip runbook (the gated switch).** Before flipping `live.dry_run=false`:
  (1) verify pricing-fits-budget on a FREE Odds API account + the Phase-0 §8.9
  four-point checklist; (2) re-pick the sharp CLV benchmark — Pinnacle closed its
  public API in July 2025, so verify The Odds API still carries Pinnacle's close, else
  set `live.sharp_benchmark`/`live.bookmaker` to Betfair Exchange (the fetch is
  feed-agnostic; the fixture carries both keys); (3) confirm the call budget
  (`live.call_budget.max_calls_per_day`) ≥ cadence × event-count and ≤ the plan quota;
  (4) supply `--api-key` (LIVE runs are refused without one). The flip changes NO code
  — only the config flag + the key.
- **SIGNAL-ONLY / PAPER (L2).** The system emits ranked edge×liquidity SIGNALS + an
  append-only realized-CLV/ROI PAPER tracker; **it NEVER places a real bet** (no
  order/broker/exchange path exists in the codebase). Any real bet is the user's manual
  action (the money-action boundary). Project ROI stays "simulated / paper";
  `live.signal_only` is an asserted invariant.
- **The live loop IS the Phase-4 per-cutoff body at `cutoff = now`.** `live.decide.decide_live`
  REUSES `model_fair_1x2`/`market_fair_1x2`/`edge_vector`/`choose_devig`/`devig`/
  `non_bet_snapshot`/`stake_fraction`/`clv_pct` — it does NOT reimplement the decision.
  `read(now)`/`cached_fit(now)`/`simulate(now)` are leakage-safe by construction (≤ now;
  strict `date < cutoff`), already proven by the P1/P2/P3/P4 canaries — so the LIVE
  number is **point-in-time-correct, the AUTHORITATIVE forward number** the
  revision-contaminated backtest cannot be (L5, north-star §4.2).
- **The focal operational-leakage discipline (L5, the NEW risk class).** Live has no
  look-ahead by construction; the new risk is OPERATIONAL. The **entry price is logged
  AT decision time** (the latest snapshot ≤ `cutoff` with the book, close-excluded and
  strictly before kickoff — the price transactable when the decision fired),
  **NEVER retroactively re-priced from the close** (the kickoff−1 min line is
  info from AFTER the entry decision; logging it as the entry would fake the edge). The
  edge + staked side + stake are decided against the de-vigged ENTRY; the close is used
  ONLY for realized CLV (`entry/close − 1`). The **bet log is append-only / immutable**
  (`live.validation.AppendOnlyLedger` — a re-log of a logged signal raises
  `ImmutableLogError`). The **live mis-log canary** (`assert_entry_logged_at_decision_time`,
  the FOCAL Codex target) proves a mis-log (the close logged as the entry) is caught.
  Every live decision is reproducible (same cutoff+seed → identical decision; provenance
  auditable from the content-addressed cache key).
- **Decision-time / CLV semantics + a pre-funding live-timeline follow-up (the
  whole-phase convergence-review DESIGN-QUESTION).** `cutoff` is the EVALUATION HORIZON of
  a decision, not necessarily the wall-clock bet instant. The ENTRY is the latest
  `<= cutoff` snapshot with the book that is STRICTLY BEFORE kickoff (`entry_ts < commence`,
  enforced — an at/after-kickoff in-game snapshot is a `"post_kickoff"` non-bet, never the
  entry; `non_bet_snapshot` + the mis-log canary both pin this independently). The entry is
  therefore ALWAYS strictly before the book-aware CLOSE (`entry_ts < close_ts <= kickoff`),
  so `CLV = entry/close − 1` is honest: you bet earlier at a real transactable price, the
  line closes later, CLV measures the move. The convergence review asked whether a decision
  taken when the close is ALREADY observable (`cutoff >= close_ts`) and priced off an
  earlier mid is "backdating." **Resolution (reviewed + chosen):** it is NOT a leak under
  standard CLV methodology, and a hard `cutoff >= close_ts → non-bet` guard is NOT viable —
  `book_aware_close` bounds by kickoff, so in genuine live (`cutoff = now < kickoff`, the
  kickoff−Xmin closing line not yet observable) it returns the latest-so-far snapshot and
  `close_ts <= cutoff` ALWAYS, which would turn EVERY live decision into a non-bet. **PRE-FUNDING
  FOLLOW-UP (do before flipping `live.dry_run=false`):** separate an explicit `decision_ts`
  (bet-commit instant) from the `cutoff` evaluation horizon and require `decision_ts <
  close_ts`, with genuine-live passing `decision_ts = now` and the real close folded in
  post-kickoff by the T6 tracker — so the live path prices the genuinely-latest transactable
  snapshot at decision time instead of treating the latest-so-far as the close. This is a
  live-operation refinement (it only bites once the real feed is funded), NOT a
  backtest/dry-run leak: the dry-run machinery this phase delivers is honest as-is (entry
  strictly before close; in-game prices rejected).
- **Cadence + cost discipline (L4/L1).** Per-matchday + a pre-kickoff (~kickoff−1h)
  refresh for active fixtures, within a pinned call budget (`live.call_budget`);
  rate-limit + exponential backoff on a 429/5xx; the feed key gated; never a
  scraper-at-volume.
- **"Too-good = bug" live (L5).** `live.validation.check_live_foresight_red` REUSES the
  Phase-4 `check_foresight_red` on the realized-CLV tracker (same `backtest.foresight_red`
  ceilings: ROI > +10%, beat-close > 58%, avg CLV > +2%); a suspiciously-good live CLV
  ⇒ SUSPECTED feed/logging bug ⇒ STOP + inspect, never celebrate. Foresight-RED is a
  COARSE backstop, NOT proof of cleanliness — the mis-log canary is the real catch.
- **The scanner (`live.scan.scan(cutoff=now) → Ranked`).** Ranks live opportunities by
  EDGE × LIQUIDITY (the north-star headline deliverable). TWO surfaces: 1X2 (`h2h`,
  PRIMARY/authoritative) + tournament-progression/outright (`SimResult` columns,
  SECONDARY, COVERAGE-GATED — outright keys unverified, so a sub-threshold/absent-odds
  market is an explicit COVERAGE GAP, never a number). Output: a structured artifact + a
  written report (no UI); non-bet filters (sign-flip/stale/thin-liquidity) gate the
  ranking + are counted. Every dry-run artifact + report is labelled non-real.
- **D3 penalty-KO fix (L3) — DONE before R32.** `wcmodel.data.sources.results.join_shootout_winners`
  ingests martj42's SEPARATE `shootouts.csv` (same pinned commit `dad6874…`) → a
  nullable `winner_override` column joined on `(date, home_team, away_team)`;
  `sim.run._build_played` threads it into `played["knockout_winners"]`;
  `sim.tournament.simulate_one` resolves a level pinned KO to the ACTUAL recorded winner
  (no RNG drawn) instead of failing loud. **The guard is PRESERVED:** a level KO with NO
  recorded winner (genuinely-missing data) STILL fails loud. Leakage-safe — only the
  ACTUAL played winner; the `< cutoff` discipline is untouched. The Phase-4
  `tests/backtest/test_d3_unreachable_knockout.py` (the BACKTEST never reaches a KO)
  stays valid; the LIVE path conditions on KOs post-fix.
- **Dry-run end-to-end (the §4 gate).** `tests/live/test_dry_run_e2e.py` runs the FULL
  loop (fetch → ingest → decide → scan → log → CLV) on the synthetic harness, labelled
  non-real, with NO spend and NO bet — the mis-log canary passes in the loop and
  foresight-RED guards the tracker.

## Dashboard data layer

- **Read-only JSON snapshots over Phase 1–5 (the data layer, not a UI).** The
  `wcmodel.dashboard` package emits provenance-stamped, leakage-safe JSON bundles over the
  existing Phase 1–5 outputs; the frontend (Plan 2) RENDERS these and recomputes NOTHING.
  `build.py` only assembles, GATES, stamps, and writes — it never reads a raw result or
  recomputes a number. The thin runner (`dashboard.cli.build_arg_parser`,
  `wc-dashboard-build`) defaults to `--dry-run` with `--cutoff` defaulting to now at runtime.
- **The FULL bundle (one per-cutoff dir).** `build_snapshot(cutoff)` writes a directory of
  stamped JSON: `tournament.json` (`team_progression`), `schedule.json` (`{group, knockout}`
  rows — group rows carry a forecast summary + edge node, knockout rows carry the derived slot
  occupants), `track.json` (`track_record` when backtest records are supplied, else an honest
  `coverage_gap` — the build NEVER re-runs the walk-forward backtest), `meta.json` (markets +
  provenance note), and a `fixtures/<match_id>.json` per group fixture (the FULL gated
  `fixture_forecast` + the match-detail "why" + the edge node).
- **Per-surface honesty semantics (the no-naked-numbers rule, per surface).** Each surface
  carries its uncertainty in the shape native to that surface, never a bare point estimate:
  team-PROGRESSION cells are `{value, se}`; SCORELINE is the full score-grid distribution (the
  distribution IS the uncertainty — no separate companion); the 1X2 split is likewise a full
  distribution (distribution-is-uncertainty); TEAM-STRENGTH ("why") is `{value, ci}` with `ci`
  the 94% HDI of the posterior; EDGES are DERIVED from the model-vs-market overlay (decision
  fields), never asserted; xG is COVERAGE-GATED (never imputed — absent StatsBomb coverage is
  an explicit `coverage_gap`, and a WC-2026 future fixture is therefore always an honest xG
  gap). A `coverage_gap` node is EXEMPT from the uncertainty-companion check (a gap is an
  explicit absence, not a naked number) — that exemption is what lets a thin/absent market
  pass the gate as a gap rather than RAISE.
- **The artifact-glob contract (bundle = stamped JSON only).** The bundle dir contains ONLY
  the stamped JSON artifacts (top-level `*.json` + the `fixtures/` dir). Model fit caches live
  OUTSIDE the bundle dir (default `paths.cache`, the shared project cache; never under
  `out_root`, never inside the per-cutoff dir), so a frontend globbing the bundle's `*.json`
  never trips over a cache file, and the whole `out_root` tree a production run reuses holds
  only bundle dirs.
- **The spec §10 provenance map is ENFORCED, never trusted to hold upstream.** `schema.py`
  carries the serializer-side rules (no-naked-numbers — every probability node needs an
  uncertainty companion; coherence — the progression ladder must be monotone; coverage-gap —
  a thin/absent market is an explicit gap, never a number; no-impute) and `build.py` is the
  one place every artifact passes through before disk: `gate_artifact` is a true STOP (a
  naked/incoherent team-progression table RAISES before any write, so a violating artifact is
  never persisted), provenance is stamped on EVERY file, `json.dumps(allow_nan=False)` fails
  loud on a residual NaN rather than emitting an invalid token, and tuple event-keys are
  stringified (`(home, away, date) → "home|away|date"`).
- **COMPLETE gate coverage — EVERY surface is a true STOP, not just the grid + tournament
  table (convergence Codex + multi-agent Workflow).** The earlier gates covered only the
  per-fixture scoreline grid (`gate_fixture_forecast`) and the team-progression table
  (`gate_artifact`); the homepage (`schedule.json`), the track record (`track.json`), the
  fixture-forecast HEADLINE, and the scoreline SHORTLIST escaped the no-naked-number STOP.
  These are now ALL gated before their `_write` (VALIDATION/HARDENING only — the approved
  DESIGN semantics are unchanged: the 1X2 split stays "distribution IS the uncertainty" with
  NO per-outcome CI, and edges stay a DERIVED comparison with NO uncertainty companion):
  - `gate_fixture_forecast` now value-checks the headline `most_likely.prob` (finite in
    [0,1]), the full `one_x_two` triple (each finite in [0,1] AND summing to ~1 — a coherent
    all-three distribution), and every `shortlist` entry's `prob` (finite in [0,1]). NOTE: a
    NaN headline would otherwise be MASKED — `_write`'s `sanitize_nans` turns NaN→None BEFORE
    `allow_nan=False`, so the gate is the only real STOP.
  - `gate_schedule(payload)` (the HOMEPAGE, previously written with NO gate) STOPs on each
    GROUP row's `forecast_summary` (headline + 1X2, shared helpers with the fixture gate so
    the two agree), each row's `edge` node (finite-sanity only — `edge`/`stake_signal` finite,
    `entry_odds` a finite decimal-odds number > 1.0 — NO uncertainty companion, edges are
    derived comparisons by design), and each KO row's `home_occupants`/`away_occupants` (each
    occupant carries `{team, prob, se}` with prob finite in [0,1] and a finite `se` — no naked
    occupant prob). `team_progression` always pairs every placing market's value with its
    binomial MC SE, so `ko_slot_occupants` always carries `se` on real data; if a qualifying
    occupant ever lacked a finite SE companion, `ko_slot_occupants` GAPS the whole
    occupant-list (`coverage_gap`) rather than emit a naked prob — the gate never false-raises
    on valid production output.
  - `gate_track` now BOUNDS the headline metrics in addition to finiteness — the "too-good is
    a suspected bug" law made structural: `beat_close_rate` in [0,1], each `rps.{model,
    market,elo}` (when not None) finite and >= 0, `n_bets`/`n` >= 0, a reliability bin's
    `forecast_mean`/`empirical` (when not None) in [0,1]. A `beat_close_rate` of 1.4 or a
    negative RPS now STOPS the build. coverage_gap/None stay exempt (an honest absence is
    never bound-checked). The build takes the metrics branch ONLY when there are ACTUAL
    records (`backtest_records and (bets or preds)`) — a truthy-but-empty records dict yields
    an honest `coverage_gap` track, never a `clv_summary([])` NaN the gate would raise on.
  - **Preds-only / Metrics-shaped records are handled (convergence Codex round-2 FIX E).** The
    build reads `bets`/`preds` via defensive `.get` (NEVER hard-index — a real
    `walkforward.Metrics.to_dict()` has no `preds` key, so `["preds"]` would `KeyError`). A
    preds-only track (forecasts made, no bet cleared the edge threshold) is legitimate:
    `track_record` GAPS the CLV block (`beat_close_rate`/`avg_clv` = None, `n_bets` = 0) instead
    of `clv_summary([])`'s NaN, while RPS/reliability stay populated from the preds; gate_track
    passes (None is exempt). A no-records dict still gaps the whole track.
- **NON-REAL / synthetic posture (`is_synthetic` taint + DRY-RUN banner).** v1 is synthetic
  only; the `is_synthetic` taint propagates into the provenance envelope and the DRY-RUN
  banner (`DRY_RUN_BANNER`) marks every synthetic snapshot as unmistakably non-real (no real
  odds sourced, no bet placed, no real CLV/ROI claim).
- **The fail-safe NON-REAL taint (the bundle reads REAL only when EVERY item is EXPLICITLY
  real).** `is_synth = cfg["dashboard"]["dry_run"] OR _bundle_is_synthetic(items) OR
  ranked.is_synthetic`. The bundle is synthetic UNLESS `items` is non-empty AND EVERY item is
  EXPLICITLY real, where an item is "explicitly real" iff it is a dict, carries NO positive
  synthetic flag, carries an EXPLICIT `is_synthetic is False` marker (item/wrapper level OR in
  its `sample`, under either the canonical `_is_synthetic` key or the `is_synthetic` alias),
  AND the canonical `walkforward._sample_is_synthetic` sees no synthetic flag in the sample.
  Anything else (missing/None/ambiguous marker, non-dict, a positive taint anywhere) → NON-REAL
  (fail-safe). An UNMARKED item that never proves itself real now reads NON-REAL (convergence
  Codex FIX A — previously a producer-side `any(_item_synth(...))` only flagged
  POSITIVELY-synthetic items, so an unmarked item slipped through as REAL and could drop the
  banner). `dry_run` taints the WHOLE bundle, a MIXED batch taints the whole bundle, and
  `items` None/empty is synthetic-by-default. So a snapshot reads as REAL only when dry-run is
  off AND every item is explicitly real. In v1 (`dashboard.dry_run=true`) the bundle is
  therefore ALWAYS NON-REAL, consistent with the embedded paper track (`track_record`
  hardcodes `is_synthetic=True`).
- **PRE-FUNDING CHECKLIST — stamp real odds samples `is_synthetic=False`.** Because the taint
  is now fail-safe (NON-REAL unless EXPLICITLY real), the real-feed flip MUST stamp each real
  odds sample `is_synthetic=False` (item/wrapper level OR in its `sample`) — else
  `_bundle_is_synthetic` keeps the WHOLE bundle stamped NON-REAL (the safe default) and the
  real banner is never shown. This is an addition to the funding-flip runbook below: an
  unstamped real feed fails SAFE to NON-REAL, never UNSAFE to a real-looking banner on
  unverified data.
- **Clean-rebuild dir (byte-reproducibility + the glob contract, convergence Codex FIX B).**
  A rebuild into an existing per-cutoff bundle dir REMOVES the dir's contents first
  (`shutil.rmtree(bundle, ignore_errors=True)` then recreate), scoped EXACTLY to the
  per-cutoff `bundle` dir (never `out_root` or above). A bare `mkdir(exist_ok=True)` overwrites
  named files but leaves ORPHANED top-level/`fixtures/*.json` from a prior/different build — a
  stale-provenance file the frontend would render AND a byte-reproducibility/§10 violation. So
  the bundle dir holds ONLY this build's stamped JSON (the glob contract), and a rebuild is
  byte-identical with no surviving orphan. **The `rmtree` is PROVABLY scoped (convergence Codex
  round-2 FIX B).** Because the dir name derives from a raw `--cutoff` (operator input) and the
  op is destructive, `_safe_bundle_dir` validates BEFORE any delete (and before the heavy fit):
  it REJECTS a name carrying a path separator / `..` / an absolute path, then asserts the
  RESOLVED bundle path is a DIRECT child strictly under `out_root` (`resolve().relative_to` +
  `parent == out_root`). A traversal cutoff (`"../evil"`, `"/etc/x"`, `"2026/06/12"`) raises
  `ValueError` and deletes nothing out-of-tree.
- **The UTC-date edge key (match the scan `event_key`, not the local date).** The edge lookup
  key is `(home, away, UTC-commence-date-str)` — the fixture's UTC COMMENCE DATE reconstructed
  from its local `date` + local `time`-with-offset (`_fixture_utc_commence_date`), NOT the raw
  local `date`. The scan/odds path keys `edges_by_event` on the stringified UTC commence date
  (`odds_ingest.event_key` → `astimezone(utc).date()`, stringified by `decide_live`), so the
  dashboard MUST derive the key the same way. A negative-UTC-offset evening kickoff's local
  date is ONE DAY before the UTC date (e.g. `'2026-06-11' + '20:00 UTC-6'` → UTC
  `'2026-06-12'`); keying on the local date made every such fixture's edge silently miss into a
  `coverage_gap` — 28 of the 72 WC-2026 group fixtures cross the UTC boundary. The synthetic
  harness (fixtures with no `time`) is unaffected: the local `date` is treated as already-UTC.
- **Leakage-safe BY CONSTRUCTION.** A snapshot IS a `read(cutoff)`: the heavy compute is
  delegated to the already-leakage-gated producers (`cached_fit`/`simulate` read ONLY
  `store.read(cutoff)`, the strict `date < cutoff` set), so a result observed AFTER the cutoff
  cannot touch the as-of-cutoff bundle. The dashboard leakage canary
  (`tests/dashboard/test_leakage_dashboard.py`) ISOLATES the `observed_at` gate — a result
  observed after the cutoff cannot change the as-of-cutoff bundle (the dashboard-layer analog
  of the P2–P5 canaries), with a positive control proving the canary is non-vacuous.
  DEFENSE-IN-DEPTH (convergence Codex FIX F): `_recent_form` additionally filters the emitted
  form-match DATES to `date <= cutoff` (tz-safe, on the calendar day) BEFORE the `tail(n)`, so
  a future-dated row that somehow slipped the store's observed_at/valid_as_of gate (e.g. a
  live-ingest row with `valid_as_of <= cutoff` but a later calendar date) can never surface as
  "recent form"; if the filter empties the set it is an honest `coverage_gap`.
- **xG coverage-gated; reliability + KO occupants DERIVED from real outputs.** xG is NEVER
  imputed — absent coverage is an explicit coverage gap. The reliability diagram and the
  knockout-bracket occupants are DERIVED from the real Phase 1–5 model/sim outputs, not
  fabricated.
- **The gated CLI (`wc-dashboard-build`, dry-run default; `--no-dry-run` REFUSES).** The
  console script (`pyproject` `[project.scripts]` → `wcmodel.dashboard.cli:main`) defaults to
  `--dry-run`: it builds a NON-REAL synthetic demo bundle (a self-contained synthetic harness —
  no test code imported) and prints the bundle path. `main(["--no-dry-run"])` REFUSES — it
  prints a clear "the real feed is GATED behind the funded pre-flip checklist; not available in
  v1" to stderr and `SystemExit(2)`; it can NEVER reach a real feed by accident. The tested
  library entry point `run_build_dry(...)` FORCES `dashboard.dry_run=True` on a DEEP COPY of
  the caller's config (the caller's dict is never mutated), so the dry-run builder can never
  emit a real-looking bundle even if handed a config whose `dry_run` is somehow False.
- **The real-feed flip is GATED.** Flipping `--no-dry-run` (the real feed) is GATED behind
  the pre-funding `decision_ts` follow-up + funding-flip runbook already documented in the
  Phase 5 section above — v1 ships synthetic only; no number in a dashboard snapshot is a
  real CLV/ROI claim.

## Dashboard frontend viewer (Plan 2)

- **A dependency-light Svelte + Vite + TypeScript STATIC viewer (`dashboard-ui/`).** No UI kit,
  no CSS framework, no state library — plain Svelte 5 components, a hash router, and a small
  set of CSS tokens (`src/app.css`). It renders the Plan-1 JSON bundles and **recomputes
  NOTHING**: there is no model in the browser, so the viewer is **leakage-safe by
  construction** (a snapshot is already a leakage-gated `read(cutoff)` from the data layer
  above; the UI only displays it). `src/lib/types.ts` mirrors the bundle envelope contract;
  the serializer (`wcmodel.dashboard`) remains ground truth.
- **The uncertainty-grammar markers (the no-naked-numbers rule made STRUCTURAL in the UI).**
  Every probability-shaped token (`45%`, `6.9%`) renders inside ONE of three conscious markers,
  or the render guard fails:
  - `data-estimate` + `data-uncertainty` — a point estimate carrying its `±` companion
    (`Estimate` / `CredibleInterval`); the companion lives in its own marked node.
  - `data-uncertainty="distribution"` — the distribution IS the uncertainty (`WinBar` /
    `ScorelineGrid` / `ScorePill`'s "1–0 · 12%"); no separate `±` companion, by approved design.
  - `data-coverage-gap` — an honest absence ("insufficient coverage"), never a number.
- **The reviewed `data-derived` exemption (NON-FORECAST numbers ONLY).** `data-derived` is a
  consciously-reviewed exemption for DERIVED signals (the EdgeChip's edge %, the ¼-Kelly stake
  signal, entry odds) and BACKWARD-LOOKING track performance (beat-close rate, CLV, RPS,
  reliability) — these are not posteriors, so they carry no `±` by design. It MUST NEVER wrap a
  forward-looking forecast probability; the guard cannot infer semantics from markup, so every
  new `data-derived` use is a manual review checkpoint, not a free pass.
- **The no-naked-number render guard + the NON-REAL e2e (the load-bearing tests).**
  `tests/no-naked-number.test.ts` walks the rendered DOM of EVERY surface and asserts no `%`
  (visible text OR `title`/`aria-label` attribute) escapes the marker set; its non-vacuity
  block proves it has teeth (the SAME function must catch a deliberately-naked `<span>45%</span>`
  and a `data-estimate` with no `±` companion). The Playwright `tests/e2e/smoke.spec.ts`
  enforces the honesty posture: the `DRY-RUN · SYNTHETIC ODDS · NOT REAL` banner is visible on
  load AND persists across drill-down, there is NO bet/stake/buy/order affordance anywhere
  (the stake is a read-only SIGNAL, not a control), and the real-edge match detail drill-down
  renders the edge + stake without any commerce-shaped control.
- **Data flow (`copy-bundle.mjs` → `public/bundle/`).** `dev`/`build`/`e2e` first run
  `scripts/copy-bundle.mjs`, which copies the NEWEST live `data/dashboard/<cutoff>/` dir
  (selected by directory `mtime`, robust to a future non-ISO dir name) into `public/bundle/`,
  falling back to the committed synthetic fixture (`tests/fixtures/bundle/`) so the app, unit
  tests, and e2e always have data offline. Requires Node ≥ 20.11 (`import.meta.dirname`; pinned
  in `package.json` `engines`).
- **v1 scope = four surfaces.** Schedule (landing, with a next-up anchor onto the first
  `upcoming` group fixture per spec D6), Match-detail (fetched on drill-down), Tournament
  progression (the coherence ladder, readable column labels), and Track record. The
  bracket-tree visualization, the ghosted sharp-line in the win-bar (needs a Plan-1 data-layer
  follow-up to emit the de-vigged market 1X2), and the real-feed flip (gated on the
  funding-flip checklist) are PROGRESSIVE / out of scope per spec §7. The viewer is
  feed-agnostic: flipping to a real feed is a data-layer change, not a UI change.
- **Convergence-review hardening (fail-safe honesty + crash-safety — the viewer does not trust
  the producer).** Mirrors Plan 1's fail-safe taint discipline at the render layer:
  - **The NON-REAL banner is gated on `provenance.is_synthetic`, NOT banner-presence.** A
    synthetic bundle with a missing/empty `banner` STILL renders the DRY-RUN chip (with a
    hardcoded `DRY-RUN · SYNTHETIC ODDS · NOT REAL` fallback); the on-screen claim is sourced
    from the producer's banner when present. A synthetic bundle can never silently read as REAL.
  - **Value components degrade, never crash.** `CredibleInterval` renders `—` for a
    null/non-finite value or a missing/degenerate CI (it never crashes the match-detail
    surface, mirroring `Estimate`). `ScorelineGrid` degrades to a `CoverageGap` for an empty /
    non-rectangular / all-zero grid — never `NaN%` / divide-by-zero — and clamps each cell's
    intensity ratio to [0,1]. `WinBar` clamps each segment's visual flex to `max(0, v)`; this is
    a **render-only** clamp that never recomputes/normalizes the probabilities (a model recompute
    is forbidden in a read-only viewer — the data layer already gates sum≈1 + [0,1]).
  - **The no-naked-number guard now covers the composed `App` shell + `HonestyBar`** (not just
    the four surfaces in isolation), with a non-vacuity proof that a hypothetical `%` in the
    honesty bar (text OR `title`) would be caught — closing the bar's blind spot. The NON-REAL
    e2e visits **all routes** (Schedule, match detail, Tournament, Track), asserting the banner
    persists and there is no bet affordance on each.
  - **Type fidelity to the serializer's conditional emission.** `TournamentData`'s inner market
    map is `Partial` (the serializer emits a market node only `if m in prog.columns`) and
    `KoRow.stage` is `string | null` (serializer `match_round.get()` may be `None`); the
    surfaces read these null-safely (Schedule renders a `TBD round` placeholder for a null
    stage). The dead `oddsToImplied` (`1/odds`) helper was removed — a latent recompute foothold
    with no use in a read-only viewer.

## Match-context covariates + host advantage (model extension, M-T0–M-T8)

A leakage-safe, ablation-gated mechanism to add match-context covariates (`rest_days`,
`travel_km`, `altitude_m`) and a host-nation home factor to the Dixon-Coles scoreline model.
**Shipped DORMANT: `model.covariates.enabled: []` is BYTE-IDENTICAL to the pre-covariate
baseline** (no covariate ⇒ no offset term ⇒ identical log-rates; proven by
`test_predict_covariates_none_is_byte_identical_to_baseline`). Nothing is live in the forecast.

- **The transform is the leakage gate.** `CovariateTransform` (`model/covariates.py`)
  standardizes each covariate on the `< cutoff` TRAINING rows only (mean/sd from observed rows,
  ddof=1), masks a missing value's CONTRIBUTION to exactly 0 (NEVER imputes a fabricated value),
  forces finiteness, and clamps the standardized `z` to ±10σ (a sanity bound against
  exp-overflow on a degenerate covariate, NOT imputation). The SAME fitted transform is used at
  fit AND predict — one source of truth, so the covariate is fit/predict-consistent and
  point-in-time safe. The M-T6 leakage canary proves a post-cutoff covariate revision cannot
  move an as-of-cutoff forecast (non-vacuous: positive control + revert-proof + a
  broken-gate-fails teeth proof).
- **β prior:** each standardized coefficient is `Normal(0, beta_scale=0.25)` — tight by design
  (an effect on the log-goal-rate larger than ~0.25/σ is implausible). Per-team covariates
  (`rest_days`, `travel_km`) shift the POSSESSING team's rate; per-match (`altitude_m`) shifts
  both sides symmetrically.
- **Host advantage:** `host_factor = host_k · home_adv` (`host_k=0.5` default) is applied to
  6 of the 9 in-country host group games (USA/Mexico/Canada). **Scope caveat (convergence
  review):** host detection keys on the HOME slot only, so the 3 games where a host plays at home
  as the schedule AWAY team (Czech Republic v Mexico @ Mexico City, Turkey v USA @ LA,
  Switzerland v Canada @ Vancouver) are currently modeled NEUTRAL — crediting the away-side host
  needs the host term to attach to the away rate, folded into the Phase-5 `k`-tuning follow-up.
  It REUSES the
  already-fitted `home_adv` — **no new fitted DOF**, never touches the likelihood/identifiability.
  Bounds: `host_k=0` ⇒ hosts neutral like everyone else; `host_k=1` ⇒ hosts get the full
  estimated home advantage. Raising `k` monotonically lifts the three hosts' win prob in their
  home games and (via the sim) their advance/progression odds. **The empirical `k` sensitivity
  table + data-driven `k` tuning is DEFERRED to Phase 5** (tune `k` from real 2026 host results
  as they arrive), per the covariate design spec; until then `k=0.5` is a documented assumption,
  NOT a fitted value.
- **Pre-enable requirement (convergence review) — the Monte-Carlo sim is covariate-blind.**
  `sim/scoreline.py::RateBook.rates` threads ONLY `host_factor`, never the covariate offset (the
  whole `sim/` tree has zero covariate references). With `enabled: []` this is a no-op (sim and
  cards are both baseline), but the moment ANY covariate is enabled the dashboard per-fixture
  cards (which DO apply covariates via `fixtures.fixture_forecast`) would DISAGREE with the
  champion/advance progression numbers (which come from the sim). So a covariate must NOT leave
  `enabled: []` until the sim threads the same per-fixture covariate offset. A tripwire test
  (`test_covariates_stay_disabled_until_the_sim_threads_them`) pins the shipped default to `[]`;
  the ablation is unaffected (it scores via `predict_1x2`, never the sim). The previously-dead
  `hosts` config field is now guarded by `test_config_hosts_field_matches_the_host_country_constant`
  (config↔constant agreement) so it can no longer silently drift from the code.

### rest_days ablation verdict (M-T8): UNVALIDATED → keep `enabled: []`

The real paired-RPS ablation (`scripts/run_real_ablation.py`, candidate `enabled=["rest_days"]`
vs baseline `[]`, real martj42 store, walk-forward cutoffs) was run. **It is NOT shipped.**
Honest status:

- **First run crashed — no verdict.** At `advi_iters=1500` the candidate's mean-field ADVI
  DIVERGED on the larger (later-cutoff) windows — ELBO blew up to 17k/120k/85k vs baseline's
  stable ~7k — driving `β_rest_days` to a runaway value ⇒ `exp(log-rate)` overflow ⇒ the
  truncated Poisson scoreline grid underflowed to all-zeros ⇒ `g/g.sum()=0/0=NaN` ⇒ the
  NaN-blind max-entropy widening edge-guard fed a NaN to `brentq` ⇒ crash. **Root cause =
  under-converged ADVI (the config default is 30000 iters; the run used 1500), NOT a real
  rest_days instability and NOT an unbounded prior** (the β prior is already tight; at a
  converged cutoff β stays sane).
- **Interim signal (the one cutoff we could afford to refit — `2024-06-01`, seed 0):** the
  candidate converges fine — ELBO 9,581 ≈ baseline — and **`β_rest_days = −0.20 ± 0.61`**
  (small, credibly spanning 0; a sign that rest_days carries little independent signal once team
  strength is in the model). One cutoff/seed is NOT a verdict, but it points to ~no lift.
- **Fail-safes added (defense-in-depth, TDD; commits `54bb8a3` + `baead55`) so the harness is
  now honest-by-construction:** (1) `inflate_predictive` raises a typed `ValueError` on a
  non-finite grid instead of NaN-crashing `brentq`; (2) `predict_scoreline` guards a degenerate
  (non-finite / sum≈0) draw grid AT SOURCE and explicitly does NOT clamp λ to fabricate a fake
  forecast; (3) the ablation wraps both arms' predicts — a candidate that produces a non-finite
  forecast on any common-eval fixture is recorded as a PAIRED NaN (kept paired, counted via
  `n_unstable`, NEVER dropped) ⇒ the existing NaN→REJECT path fires with a loud per-cutoff log.
  So an unstable candidate REJECTS honestly; it can never crash the run, fabricate a forecast, or
  be scored on surviving fixtures (no survivorship bias).
- **Why not shipped now:** (a) a clean RPS verdict needs well-converged fits (~30k iters ⇒
  multi-hour/overnight compute), deferred as a documented follow-up; (b) **the ship decision is
  CLV-gated regardless** — with no funded odds feed CLV is `None`, so the formal accept gate
  (`mean_d>0` AND `paired_p<0.05` AND CLV-not-worse) CANNOT clear on RPS alone; (c) the interim β
  already hints ~0 signal. Conservative, honest outcome: **`rest_days` stays `enabled: []`**
  ("tested, not validated, not shipped"). The converged re-run + the funded-CLV gate are the
  gated follow-ups. `scripts/run_real_ablation.py` is the committed, crash-safe recipe
  (`advi_iters` set to the converged config default with the wall-clock caveat inline);
  re-running it once the odds feed is funded yields the RPS + CLV verdict.

## Totals (O/U goals) +EV edge (markets/totals, T0–T8)

A SECOND betting surface read off the SAME scoreline grid the 1X2 model already produces: the
model's Over/Under-total-goals fair prices are compared to soft-book totals odds to find +EV bets,
validated on a leakage-safe paper-CLV backtest. The model NEVER ingests the odds. Status: BUILT +
unit-tested; the real-data verdict run is GATED (the calibration-trust gate + plan T8 Step 5) and
has NOT been run — so this is "wired, not yet validated, not bet."

### Market-prior-free framing (the binding invariant)

- The odds are NEVER fed into the fit. `cached_fit` reads ONLY the martj42 store as-of cutoff;
  `markets/derived.totals_probs(grid, lines)` takes ONLY the normalized scoreline grid (`g[h,a]`
  from `posterior.predict_scoreline`) — no model, no odds — so `P(over L)=Σ g[h,a]` over `h+a>L`
  and `over+under==1` exactly. Odds enter at EXACTLY ONE place, `markets/totals_edge.totals_edges`,
  AFTER the grid is computed (the model is compared to the market, never primed by it).

### The +EV edge metric + threshold

- `edge = model_prob * soft_book_odds - 1` — expected profit per unit at the RAW offered price
  (vig included: +EV value betting must overcome the vig, not de-vig it away).
- A side is BET only when the UNCERTAINTY-SHRUNK edge `edge * shrink(se)` clears
  `markets.totals.edge_threshold` (default 0.03). The stake is the project's ¼-Kelly ×
  uncertainty-shrink (`backtest.staking.stake_fraction`, `kelly_fraction` from `cfg.backtest`).
- DEVIATION from the plan's draft code (noted honestly): the plan gated on the RAW edge and relied
  on `stake_fraction` to suppress a thin noisy edge, but the real `stake_fraction` SCALES the stake
  by the shrink (never zeroes a positive Kelly) and REQUIRES `kelly_fraction`/`edge_threshold`
  kwargs. So the bettable decision is made on the shrunk edge vs the threshold (the plan's stated
  intent — "the edge AFTER the shrink clears edge_threshold"), and `stake_fraction` is called only
  to SIZE the bet (passed `edge_threshold=0.0` so it never re-gates on the DIFFERENT staking
  trigger `backtest.edge_threshold`). The T3 shrink-suppression test pins this.

### Calibration gate dependency (why the verdict is held)

- The edge is only as trustworthy as the goal distribution. `backtest.totals_backtest.
calibration_table` bins model `P(over)` vs the realized over-rate over ALL scorable fixture/lines
  (NOT only bet ones — unbiased by the bet filter); under-confidence shows as `predicted` pulled
  toward 0.5 vs a more extreme `observed`. If the overnight production calibration run finds the
  goal distribution under-confident, the sharpening (raise `prior.sigma_att/def` / lower
  `widening.strength`) + re-validation come FIRST. The verdict run (plan T8 Step 5) is HELD on this.

### CLV-is-the-gate accept + the single-use lockbox

- `totals_verdict(agg, paired_p)` accepts iff `avg_clv>0` AND `roi>=0` AND a one-sided sign-flip
  permutation `paired_p<0.05` on the per-bet CLV; ANY NaN/None -> REJECT (fail-safe), mirroring
  the 1X2 ablation discipline. CLV (entry vs the soft-book CLOSE on the bet line) is the leading
  indicator; the realized total only SETTLES the bet (never informs the pick — pinned by the
  leakage canary `test_totals_leakage.py`, which is non-vacuous: a real bet is asserted placed).
- The final accept is computed ONCE on the held-out lockbox slice via
  `LockboxRegistry.evaluate_on_lockbox`. The ops runner uses a TEMP COPY of `config/lockbox.json`
  by default — an ops re-run NEVER burns the committed single shot (`--use-real-lockbox` is the
  deliberate one-time burn, only after the calibration gate clears).

### Soft-book-limits caveat

- The edge is priced vs soft books (`markets.totals.soft_books`: bet365/draftkings/fanduel) — the
  venues we'd actually transact. Pinnacle is the SHARP reference ONLY (printed for context, NEVER
  fed to the model, NEVER bet). Soft books limit/ban consistent +EV winners, so a backtested
  soft-book edge can be unrealizable at scale; this is a known caveat, not modeled here (signal-only).

### Totals-only (BTTS / correct-score deferred)

- `markets/derived.py` ships ONLY `totals_probs` (the package is built general but only totals is
  wired now). BTTS, correct-score, and other grid-derived markets are deferred — adding them is a
  new `derived.py` function + a new edge calculator, no change to the fit or the leakage/lockbox
  machinery.
