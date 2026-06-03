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
- **StatsBomb xG point-in-time (versioned).** Open Data is static and versioned, so
  for covered matches xG is point-in-time (not revision-contaminated); coverage-gated;
  never imputed. _Pinned release `source_version` filled in Task 9._
- **Tier bands from point-in-time computed-Elo.** Strength band is the computed-Elo
  percentile as-of the match cutoff (never as-of-today; bands may shift across the
  window). Uses computed-Elo, not the revised FIFA ranking.
- **COVID tag.** 2020–21 internationals (config `covid.start`/`covid.end`) are tagged
  COVID-distorted (empty-stadium era); tagged, not blended.
- **`current_only` policy scope.** The `current_only` (revision-contaminated) policy
  applies **only** to deferred optional sources (market values / rosters); the Phase 1
  clean core has no active `current_only` source.
