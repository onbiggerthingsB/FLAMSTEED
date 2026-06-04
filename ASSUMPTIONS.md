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
  - Margin-of-victory index = **World Football Elo goal-difference scheme**:
    `G = 1` for a goal margin ≤ 1, `1.5` for a margin of 2, else `(11 + margin)/8`.
  - Expectancy/update: `dr = home_pre − away_pre + ha`; `E = 1/(1 + 10^(−dr/400))`;
    `rating_post = rating_pre + K·G·(W − E)` with `W ∈ {1, 0.5, 0}` (win/draw/loss).
  - `provisional_games = 5` (see debutant note below).
  - **Point-in-time.** `rating_pre` (the pre-match rating, knowable at kickoff) is the
    leakage-safe feature; `rating_post` is the post-update rating and is never a
    same-match feature.
- **Debutant / new-team handling (pinned, Task 5 — per user decision).** Debutants start
  at the **same** `initial_rating` (1500), **not** a faked-low point estimate. Their first
  `provisional_games = 5` matches are flagged `provisional = True` as a pure
  low-information marker. The minnow uncertainty is carried by the **Phase-2 prior**, not
  by rigging the rating. (The earlier `initial_rating_debutant: 1300` line was removed.)
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
- **`current_only` policy scope.** The `current_only` (revision-contaminated) policy
  applies **only** to deferred optional sources (market values / rosters); the Phase 1
  clean core has no active `current_only` source.
