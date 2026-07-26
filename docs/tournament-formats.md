# Tournament Formats — the `format:` block (Phase 2A)

**Status:** written at the end of Phase-2A Task 6 (branch `feat/phase2a-tournament-format`).
**Scope:** how a tournament yaml declares its own shape, what the sim/ops pipeline does with
it, the market semantics shared by every edition, the AFC Asian Cup 2027 operating
procedure, and the modeling approximations made — stated honestly, with their tests.

The design invariant of the whole phase: **a document WITHOUT a `format:` block is the
frozen WC-2026 path, byte-identical to the published pipeline** — proven by the golden-hash
oracle `tests/sim/test_wc_golden.py` (seeded real-bracket sim, hashes committed at
`tests/golden/wc2026_sim_golden.json`), not merely by green suites.

---

## 1. The `format:` block

Optional top-level key of a tournament yaml (`config/tournament_ac2027.yaml` carries one;
`config/tournament_2026.yaml` does not and never will). When present, ALL keys are
required — `format: null`, a non-mapping, or a partial block raises at load
(`wcmodel.data.tournament.tournament_format`): a half-specified edition must fail loud,
never silently inherit half of the World Cup's shape.

| key | type | WC-2026 default (no block) | AC-2027 value |
|---|---|---|---|
| `n_groups` | int | 12 | 6 |
| `teams_per_group` | int | 4 | 4 (only 4 is supported — 6-games-per-group math) |
| `per_group_advance` | int | 2 | 2 |
| `best_thirds` | int | 8 | 4 |
| `third_place_match` | bool | true | false (regs Arts. 9.6–9.12: 15 KO matches, no 3rd-place playoff) |
| `tiebreak_order` | str | `fifa_2026` | `afc_2027` (registry key in `sim/groups.py`) |
| `assignment_table` | str | `third_place_assignment.json` | `third_place_assignment_ac2027.json` (file name under `config/`, traversal-guarded) |
| `competition_name` | str | `FIFA World Cup` | `AFC Asian Cup` (the `tournament` tag on every ingested row) |
| `source_tag` | str | `wc2026_schedule` | `ac2027_schedule` (store `source`/`source_version` on schedule rows) |
| `hosts` | map | `{Mexico: MX, United States: US, Canada: CA}` | `{Saudi Arabia: SA}` (team → ISO code of its venues) |
| `ko_host_advantage` | bool | false | true (see §4) |

Structural validation (`validate_tournament`, formatted branch): group count/size and
distinct-teams checks derived from the block; fixture SPLIT check — group fixtures (no
`match` key) must number `n_groups*6`, knockout fixtures (`match` present) must number
`(advancers-1) + third_place_match` where `advancers = n_groups*per_group_advance +
best_thirds` (AC: 16-1+0 = 15). The legacy WC branch runs verbatim for blockless
documents.

What the block drives downstream:

* **bracket** (`sim/bracket.py`) — slot grammar is edition-agnostic (`\d[A-Z]` seeds,
  `3rd-[A-Z]{2,}` third slots, `W\d+`/`L\d+` refs); round labels are a CLOSED vocabulary
  including the official AFC plural spellings (`Quarter-Finals`, `Semi-Finals`);
  unresolved `3rd-*` refs raise.
* **group ranking** (`sim/groups.py`) — `rank_group(order=...)` registry; `afc_2027` adds
  the regs Art. 7.3.2.7 penalties criterion (see §4), fed by each group's final-matchday
  pairings, which the sim reads as the LAST TWO fixtures of the group's schedule-ordered
  fixture list.
* **thirds** (`sim/thirds.py`) — `rank_thirds(best_n=...)` + the edition's published
  C(n_groups, best_n) assignment table, verified by `scripts/verify_thirds_table.py`
  (coverage, bijection, eligibility, match numbers pinned to `_meta`).
* **hosts** — `host_home_factor(..., hosts=...)` / `host_factor_map` read the block's
  hosts, so a non-WC edition never inherits the World Cup's hosts; `ingest` derives the
  `neutral` flag from the same map.
* **cache** (`sim/cache.py`) — `fmt` enters the content key ONLY when not `None`
  (absent ≠ null: pre-phase keys are preserved bit-for-bit).
* **ingest/ops** — provenance tags (§3) and the daily loop's `--tournament` flag.

## 2. Market semantics (both formats)

The sim's 11 public market columns are unchanged: `win_group, advance_from_group,
reach_r16, reach_qf, reach_sf, reach_final, champion, first, second, third, out`.

`reach_r16` means **"reached the Round of 16"** — in every format. The reach ladder is
cumulative over knockout depth; an R32 loser in the 2026 World Cup does NOT get
`reach_r16` (it reached only the R32). In a 4-round bracket (AC-2027: R16 → QF → SF →
Final) the R16 **is** the knockout entry round, so `reach_r16` coincides exactly with
`advance_from_group` — values AND standard errors are identical arrays, pinned by
`tests/sim/test_ac2027_e2e.py::test_advance_equals_reach_r16_values_and_ses`. In the
5-round WC-2026 bracket the two differ (you can advance and then lose the R32).
There is deliberately no `reach_r32` column for AC (no such round exists); the coherence
ladder (`dashboard/schema.py`) applies unchanged.

## 3. AFC Asian Cup 2027 — operating procedure

The real draw lives at `config/tournament_ac2027.yaml` (May-9-2026 final draw; group E
completed by Yemen's June-4 playoff win; fixtures/venues from the official Match Schedule
PDF archived at `docs/superpowers/research/AC27F_MatchSchedule_5june26.pdf`). Team names
are martj42 store keys — reconciliation (5 mapped, 19 identical):

| AFC official | martj42 store key |
|---|---|
| DPR Korea | North Korea |
| Islamic Republic of Iran | Iran |
| Kyrgyz Republic | Kyrgyzstan |
| China PR | China |
| Korea Republic | South Korea |

**Window:** group stage 2027-01-07 → 2027-01-20; R16 Jan 22–25 (matches 37–44); QF Jan
28–29 (45–48); SF Feb 1–2 (49–50); Final Feb 5 (51). 51 matches total.

**Daily loop** (mirrors `docs/daily-loop.md`, one flag added):

```bash
# nightly, during the tournament window
PYTHONPATH=src .venv/bin/python scripts/daily_update.py \
    --tournament config/tournament_ac2027.yaml --latest

# matchday fallback when martj42 lags — CSV validated against the AC draw
PYTHONPATH=src .venv/bin/python scripts/daily_update.py \
    --tournament config/tournament_ac2027.yaml \
    --manual-results dayN_ac.csv
```

`--tournament` threads the yaml into (a) manual-CSV validation (`validate_manual_csv
(tournament_path=...)` — drawn-team set, fixture index, hosts/neutral flags and the
`AFC Asian Cup` row tag all come from the AC draw + its format), and (b)
`build_snapshot(tournament=...)` → the sim (format-driven shape end-to-end). Default
(no flag) is the WC-2026 draw — the pre-phase call shape, byte-identical.

Schedule ingest (`ingest_wc_group_fixtures` — name kept, behavior format-driven) writes
the 36 group fixtures as UNPLAYED PIT rows tagged `tournament="AFC Asian Cup"`,
`source=source_version="ac2027_schedule"`; the WC path keeps stamping today's literals
(`FIFA World Cup` / `wc2026_schedule`), asserted in
`tests/data/test_tournament_format.py`.

## 4. Modeling approximations (honest register)

These are deliberate simplifications, each seeded/deterministic per draw and each with a
stand-in rationale — not hidden behavior:

* **Penalties criterion (AFC group tiebreak, regs Art. 7.3.2.7)** — when exactly two
  teams remain tied after all-group GD/GF AND met on the final matchday (in a single
  round-robin such a pair necessarily drew that game), the criterion is a **seeded 50/50
  coin flip** (`rng.permutation(2)`), consistent with `pen_home_prob=0.5` for KO
  shootouts: a penalty shootout between near-equal sides ≈ coin flip. Not modeled:
  team-specific shootout skill.
* **KO host advantage (`ko_host_advantage: true`)** — once knockout participants are
  concrete, a tie with EXACTLY ONE host participant applies the same `host_k`-derived
  factor used for group games (`_ko_host_side` in `sim/tournament.py`; both/neither host
  ⇒ neutral). Not modeled: a knockout-specific host effect size (no data to fit one).
* **Fair-play / cards and drawing-of-lots tails** (regs 7.3.2.8–7.3.2.9, ops-manual
  Appendix 2 1.1.4–1.1.5) — the existing **seeded random tail** stands in, exactly as it
  does for the FIFA fair-play/lots criteria; `random_tail_rate` reports how often any
  random tail fired.
* **Third-placed comparison** — points → GD → GF per ops-manual Appendix 2 1.1.1–1.1.3
  modeled exactly; the cards/lots tail is the seeded stand-in above.
* **Kickoff times** — the AC schedule wall chart publishes dates only; fixtures carry
  dates, so `date < cutoff_day` conditioning is day-floored exactly as for the WC.

Rules provenance: `config/afc2027_rules_extract.md` (verbatim regs Art. 7.3 +
Arts. 9.2–9.12, pages 25–29; ops manual Appendix 2, pages 104–106).

## 5. Deliberate non-goals

* **Analysis scripts stay WC-specific** — `scripts/live_scorecard_final.py` and the other
  retrospective/diagnostic scripts hardcode the 2026 edition; generalizing them bought
  nothing for the AC loop and risked the frozen path. Same for the Phase-1 release
  generator (WC-2026 archive).
* **No market renames** (`reach_r16` keeps its name in both formats — §2).
* **No model changes** — the posterior, covariates and calibration are untouched; only
  the tournament SHAPE became configurable.
* **Widget/entitlements/hosting/UI polish** — Plan 2B.
