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

- **Elo hyperparameters (pinned).** K-factor (`k_base` × `k_by_match_type`),
  home-advantage, margin-of-victory adjustment (`mov_index`), initial rating, and
  debutant/new-team handling. Low-information debutant Elo is expected (the minnow
  problem — handled by the Phase 2 prior, not faked precision). _Concrete values
  and formulas filled in Task 5._
- **Elo-baseline coherence (single Elo).** The same computed Elo is the Phase 4
  naive-Elo baseline via a documented standard logistic mapping; no second
  divergent Elo. _Mapping (incl. `draw_base`) filled in Task 5._
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
