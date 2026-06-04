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
    - **Divergence from standard World Football Elo K = 60 — flagged, NOT changed.**
      The canonical World Football Elo uses **K = 60** for World Cup finals; WE run
      **K = 40** for WC finals (`k_base 40 × wc_finals 1.0`). This is a deliberate,
      documented divergence (a flatter, less twitchy update than the public WFE),
      recorded here so it is not mistaken for the standard. This entry does **not**
      change K — it only reports the effective values.
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
