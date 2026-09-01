# Forward EPL betting evidence plane — preregistration

**Written:** 2026-08-31 · **Branch:** `main` · **HEAD when written:** `5a04a7b`

**Status when written: PREREGISTERED ONLY.** No betting-evaluation harness,
forward decision ledger, closing-price ledger, or result exists under this
design. No fit was run to write this document. This document creates no betting
authority, places no bet, changes no published forecast, and changes no file
under `src/` or `scripts/`.

This is the law for one question:

> When the frozen EPL model is sealed before a price is observed, and a
> one-unit bet is selected mechanically at a real price available to the owner,
> does that price later carry positive margin-adjusted economic value against
> the de-vigged Pinnacle close?

The answer is about a forward evidence plane, not a backtest. Results determine
the secondary paper P&L, but they do not determine the primary estimand. The
primary evidence is whether the selected entry prices beat a later, sharper
market after its margin is removed.

---

## 0. Decisions fixed here

| item | frozen decision |
|---|---|
| competition | English Premier League, full-time 90-minute 1X2 only |
| primary model | the published `dc_native` law and cadence named by the hash-freeze manifest; parameters may update only by that already-published law |
| model clock | forecast bundle sealed at least 30 minutes before the entry target and before any entry quote is observed |
| entry target | scheduled kickoff minus 48 hours |
| valid entry window | first complete eligible quote at or after the target, no later than target plus 10 minutes |
| entry price | best net decimal price for one outcome across the pre-frozen owner-accessible book manifest |
| selection threshold | maximum model-implied expected ROI at the entry price at least **+2.00%** |
| selections | at most one outcome per fixture, deterministic tie-break |
| stake | exactly one notional unit per selected fixture; zero on every non-bet |
| close | latest complete Pinnacle 1X2 quote from kickoff minus 10 minutes through kickoff minus 1 minute; no fallback bookmaker |
| close de-vig | proportional normalization of the three reciprocal closing odds |
| primary statistic | mean margin-adjusted economic CLV over selected, non-void bets |
| inference | 10,000 percentile bootstrap draws over EPL `(season, ISO kickoff week)` blocks, seed `20260831` |
| fixed horizon | 156 consecutive weeks, set mechanically from the hash-freeze date; no extension for sample size |
| adoption floor | `N >= 500`, mean economic CLV `>= +0.0100`, and 95% week-block lower bound `> 0`, all required |
| meaning of PASS | continue shadow collection and permit a separately preregistered tiny-stake validation; never proof of profit or authority to scale |

No threshold, market, time window, book subset, de-vig rule, model arm, or
stake may be selected after a forward row exists.

---

## 1. Population and fixed horizon

### 1.1 Fixture universe

The universe is every EPL league fixture first published by the frozen official
schedule source with its then-scheduled kickoff inside the run horizon. Cups,
friendlies, playoffs, outrights, totals, handicaps, correct-score markets and
in-play prices are out of scope.

Each official fixture enters an append-only census once, carrying its stable
source identifier, the first observed home and away clubs, the first observed
kickoff, the observation timestamp and the raw schedule digest. Later schedule
or venue changes append revision events; they never rewrite or remove the census
row. A fixture remains in the denominator after postponement, abandonment,
source outage, missing odds, or a model failure.

### 1.2 Horizon

The hash-freeze manifest computes:

```
H0 = the first Monday 00:00:00 UTC at least 7 full days after the freeze commit
H1 = H0 + 156 weeks
H2 = H1 + 60 days
```

The 156-week span is fixed independently of prices, selections, closes and
results. The run accepts no new fixture whose first-published scheduled kickoff
is outside `[H0, H1)`. Collection needed for a fixture at the start of the
horizon may begin at its entry target after the freeze and before `H0`.

At `H1`, no new entry decision is allowed. The period through `H2` exists only
to resolve already-admitted postponements, voids, closes and results. Any
selected bet whose **primary** status — stood or void, actual kickoff and valid
close — remains unresolved at `H2` is recorded as unresolved and makes the run
DATA-INCOMPLETE. A missing result on an otherwise closed primary row leaves
secondary P&L missing but does not erase its economic CLV. The horizon is never
extended because `N` is low or the point estimate is inconvenient. Reaching 500
bets early does not stop the run.

### 1.3 Schedule changes and voids

The entry target uses the kickoff as known when the model bundle is sealed,
called `kickoff_as_known`. If that kickoff changes before the entry target, the
old attempt records `schedule_changed_pre_entry`; a new model bundle may be
sealed against the revised schedule before its new entry target. It may not
reuse a model or price observed in the wrong order.

If the kickoff changes after a valid entry decision, the frozen entry book's
ordinary published cash-bet rules decide whether the wager would stand or be
void. A void is recorded with stake returned, is not a primary bet, and is never
silently dropped. If the wager stands, the Pinnacle close is taken at the actual
kickoff under §3.3.

---

## 2. The two-clock information barrier

### 2.1 Model first

For fixture `i`, let `T_entry(i) = kickoff_as_known(i) - 48 hours`. The model
record is eligible only if all of the following hold:

1. `model_issued_at <= T_entry - 30 minutes`;
2. the forecast's own `cutoff` and `observed_by` are both no later than
   `model_issued_at`;
3. the forecast bundle, model-law digest, realised configuration digest and
   exact `{home, draw, away}` probabilities are hashed and appended before the
   first entry-source request for that fixture;
4. all three probabilities are finite, non-negative and sum to 1 within
   `1e-9`; and
5. the forecast is the primary arm named by the freeze manifest. A shadow arm
   cannot be substituted because its number looks better.

The evidence-plane process that reads prices may read this sealed model record.
The model process may not read an entry quote, a close, an outcome, a market
movement, or any evidence-plane aggregate. A future model-law change does not
enter this run: it requires a new preregistration and a new forward clock.

### 2.2 Entry second

Only after the model record is durably sealed may the entry collector request
prices. It takes the first complete eligible snapshot whose provider timestamp
and local observation timestamp are both in:

```
[T_entry, T_entry + 10 minutes]
```

A quote from before the target, after the window, or observed before the model
seal is not repaired by relabelling its timestamp. It is a recorded failure.
If a provider supplies publication time and local observation time, both are
stored; selection binds on the later of the two.

### 2.3 Close last

The close is never available to selection. It is the latest complete Pinnacle
snapshot with provider timestamp in:

```
[actual kickoff - 10 minutes, actual kickoff - 1 minute]
```

No post-kickoff quote is admissible. No consensus, average, median bookmaker,
Betfair midpoint, entry book, or archived season-file close may substitute for
a missing Pinnacle close. The same frozen provider may recover the timestamped
historical Pinnacle response after kickoff; the raw response and retrieval clock
must be retained. If it still cannot be recovered, the selected row is
`close_missing` and the run cannot PASS.

### 2.4 Leakage canary

Before hash freeze, the adversarial audit must mutate every close and every
result while holding model and entry events fixed. Model eligibility, selected
book, selected outcome, selected price and stake must remain byte-identical.
A positive control that mutates an entry quote enough to cross the +2% threshold
must change the selection. Zero movement on the positive control is a vacuous
canary and refuses the freeze.

---

## 3. Market and price requirements

### 3.1 The entry-book manifest

Before the first forward model record, the freeze commit pins an ordered
`ENTRY_BOOKS` manifest. Each entry states:

- canonical book identifier and quote source;
- evidence that the owner can legally and practically access that account or
  exchange in the relevant jurisdiction;
- whether the quote is an authenticated account/bet-slip quote or API quote;
- commission rate and its exact calculation, if an exchange;
- minimum accepted cash stake and how one notional unit maps to it; and
- the book's postponement, abandonment and void rule in force at freeze.

Public comparison-site or consensus odds are not purchasable entry evidence.
Promotional boosts, free bets, deposit bonuses, personalized offers and prices
whose conditions cannot be repeated are excluded. A quote is eligible only if
the market is open and the book or exchange indicates that at least one unit can
be accepted at that price. For an exchange, available unmatched volume at the
price must be at least one unit.

The manifest is ordered before the run and cannot gain a book mid-run. Loss of
access is recorded as `book_unavailable`; it does not license a replacement.

During BUILT, UNFROZEN the manifest may be empty or schema-only and every book
test must be synthetic. The implementer may not infer or invent which accounts,
books, jurisdictions, limits or commissions the owner has. Before HASH-FROZEN,
the **owner supplies** the real accessible-book entries and attests their access
facts; the freeze refuses an empty manifest or an entry without that owner
attestation. Only that owner-supplied, frozen list may enter the forward run.

### 3.2 A complete quote

Entry and close snapshots concern the ordinary full-time 1X2 market including
stoppage time and excluding extra time and penalties. A complete quote has home,
draw and away prices from the same bookmaker and snapshot, each finite decimal
odds strictly greater than 1. For both entry and close, the reciprocal sum must
be at most `1.20` and must satisfy `reciprocal_sum + 1e-9 >= 1.0`. A named
single-book triple below `1.0` by more than the `1e-9` arithmetic tolerance is
an underround and refuses as malformed; it is not treated as an arbitrage or a
special opportunity.

Raw vendor bytes, fixture identity, bookmaker, market key, provider timestamp,
local observation timestamp, raw odds strings, parsed decimal odds, market
status, available stake and SHA-256 are retained. Home/away mapping is exact and
registry-based; fuzzy matching is forbidden. The entry record retains the quote
and eligibility/refusal result for **every** book in the frozen manifest, not
only the winning book. Otherwise “best available” could not be reproduced and a
failed high price could be silently omitted.

### 3.3 Net entry payout and sharp closing probability

For a bookmaker, net entry decimal odds equal the displayed cash decimal odds.
For an exchange with commission `c` on winnings:

```
O_entry_net = 1 + (O_entry_raw - 1) * (1 - c)
```

Pinnacle is the only primary closing book. Given its raw closing odds
`O_close,H`, `O_close,D`, `O_close,A`, proportional de-vigging is:

```
r_j       = 1 / O_close,j
q_close,j = r_j / (r_H + r_D + r_A)
```

The closing margin is therefore removed. Entry margin is not “corrected” away:
the actual net payout is the economic offer the owner could have taken.

---

## 4. Selection and flat stakes

### 4.1 Candidate edge

For each eligible outcome `j` at each eligible entry book `b`:

```
edge(i,j,b) = p_model(i,j) * O_entry_net(i,j,b) - 1
```

This uses the model probability sealed before price observation and the actual
net price after bookmaker margin or exchange commission. No close, result,
market consensus, later line movement, manual opinion, injury news read after
the model seal, or bookmaker limit may change the number except that a price
unable to accept one unit is ineligible.

### 4.2 One mechanical decision per fixture

Among all eligible `(outcome, book)` pairs, select the pair with maximum `edge`.
Exact numerical ties are broken first by outcome order `home`, `draw`, `away`,
then by the pre-frozen `ENTRY_BOOKS` order. There is no operator choice.

- If the maximum edge is at least `+0.0200`, record `bet_intent` for that pair.
- If valid model and entry data exist but the maximum is below `+0.0200`, record
  the valid non-bet `no_edge`.
- If model, clock, identity or price requirements fail, record a typed failure.

There is at most one bet intent per fixture. There is no threshold grid, odds
bin exclusion, favorite/underdog rule, promoted-club override or “top pick”
quota. A fixture with no edge still occupies its census row.

### 4.3 Stakes and settlement

Every bet intent carries exactly `stake_units = 1.0`; every non-bet, failure or
void carries `0.0`. There is no Kelly sizing, confidence sizing, compounding,
chasing, parlaying, cash-out, or stake change by price, edge, team, book or
recent performance.

The run is shadow evidence: the unit is notional and this document does not
authorize a real transaction. Hypothetical secondary P&L is:

```
win  : +(O_entry_net - 1)
loss : -1
void : 0
```

Settlement uses the frozen entry book's ordinary rule and an independently
provenanced final result. P&L never enters the primary decision.

---

## 5. Primary estimand and inference

### 5.1 Margin-adjusted economic CLV

For selected, non-void bet `i` on outcome `s(i)`:

```
economic_clv_i = q_close(i, s(i)) * O_entry_net(i, s(i)) - 1
```

The primary estimand is the unweighted mean over all primary bets:

```
mu_eclv = sum(economic_clv_i) / N
```

Each selected bet receives equal weight because each stake is one unit.
`+0.0100` means the entry bets carried one cent of close-implied expected value
per unit staked after the closing margin was removed. This is not the existing
raw price-ratio statistic `entry_odds / close_odds - 1`; that statistic remains
a secondary diagnostic under §6.

`N` counts only mechanically selected, non-void bets with valid model, entry and
Pinnacle-close records. A selected bet with an unresolved missing close is not
dropped into a favorable complete case: it remains visible and makes the run
DATA-INCOMPLETE under §8.

### 5.2 Week-block bootstrap

Every primary bet receives block `season | ISO-year-Wweek` from its actual
kickoff. The bootstrap sampling frame is the fixed set of blocks containing at
least one primary bet. Weeks with fixtures but zero bets remain in the fixture
census and the selection-rate denominator, but they do not enter an estimator
whose population is selected bets. For each of 10,000 draws using NumPy's
`PCG64` generator at seed `20260831`:

1. sample the fixed number of populated blocks with replacement;
2. carry every primary bet belonging to each sampled block, with multiplicity;
3. recompute the ratio `sum(economic_clv) / sum(n_bets)`; and
4. assert that the denominator is positive; a zero denominator is an
   implementation error because every sampled block is populated.

The 95% interval is `numpy.quantile(draw_means, [0.025, 0.975])` using NumPy's
default linear interpolation. The code, NumPy version, block inventory, seed and
resulting bootstrap digest are frozen or reported. There is no IID interval in
the adoption rule. Season-block and heteroskedasticity-robust intervals may be
reported as diagnostics only.

### 5.3 No interim decision

During RUNNING, operational dashboards may show fixture counts, source health,
clock failures, book availability, bet-intent count and unresolved rows. They
may not show aggregate economic CLV, beat-close rate, P&L, outcome-stratified
performance, or any proxy that reveals the sign of the primary result. There is
one computation for decision after the horizon closes. Safety or integrity may
stop a run early; performance may not.

---

## 6. Secondaries and multiplicity

There is one primary estimand, one primary model, one market, one horizon, one
selection threshold and one adoption decision. Therefore no multiplicity
adjustment is applied to the primary 95% interval.

The following are reported but **never decide** this run:

- raw price-ratio CLV, `O_entry_net / O_close_raw - 1`;
- proportion of selected bets with strictly positive raw price-ratio CLV;
- Shin-de-vigged economic CLV as a sensitivity to proportional de-vigging;
- notional flat-stake P&L, ROI and drawdown after results arrive;
- selection rate and failure rate over the complete fixture census;
- model-implied edge at entry versus realised economic CLV;
- RPS of the sealed model and de-vigged close against results; and
- descriptive slices by season, outcome, entry book, promoted-club involvement,
  entry-odds bands `[1,2)`, `[2,4)`, `[4,+inf)`, and model age
  `[0,24h)`, `[24h,72h)`, `[72h,+inf)`.

Secondary intervals are labelled exploratory. They carry no PASS labels and no
subgroup is allowed to rescue a failed primary. If any slice motivates a rule,
that rule requires a new forward preregistration; the already-observed slice
cannot be its confirmatory sample. Totals, handicaps and correct-score markets
are separate families and cannot be added here as extra chances to pass.

---

## 7. Evidence contract and schema

### 7.1 Append-only source ledgers

The build must create five append-only event streams, with canonical JSON and a
hash chain within each stream:

1. `fixture_census` — initial official fixture and every schedule revision;
2. `model_seals` — model clocks, probabilities, law/config and bundle digests;
3. `entry_decisions` — every valid non-bet, bet intent and pre-decision failure;
4. `closing_events` — valid closes, recoveries, voids and close failures; and
5. `settlements` — result provenance and secondary paper settlement.

The source streams are the record. A final one-row-per-fixture evidence table is
derived only after close; it never replaces or rewrites an event. The natural
idempotency key is `(fixture_id, stage, attempt_clock)`. An identical replay is
a no-op; a substantive conflict under the same key refuses the whole append and
names both records.

### 7.2 Canonical evidence-table fields

Every universe fixture appears once in the derived table. Nullable fields remain
present as null; absence is not represented by dropping the row.

| group | required fields |
|---|---|
| identity | `schema_version`, `run_id`, `fixture_id`, `season`, `home`, `away`, `competition`, `market` |
| schedule | `first_kickoff_utc`, `kickoff_as_known_utc`, `actual_kickoff_utc`, `schedule_observed_at`, `schedule_digest`, `week_block`, `revision_count` |
| model | `model_arm`, `model_law_digest`, `config_digest`, `source_bundle`, `bundle_sha256`, `cutoff`, `observed_by`, `model_issued_at`, `p_home`, `p_draw`, `p_away`, `model_age_hours` |
| entry | `entry_target`, `entry_observed_at`, `entry_provider_at`, `entry_quote_set`, `entry_quote_set_sha256`, `entry_books_seen`, `entry_candidate_count`, `entry_book`, `entry_market_status`, `entry_odds_raw`, `entry_odds_net`, `entry_overround`, `entry_available_stake`, `entry_commission`, `entry_raw_sha256` |
| decision | `decision_status`, `reason`, `selected_outcome`, `model_edge`, `selection_threshold`, `stake_units`, `selection_rule_version` |
| close | `close_observed_at`, `close_provider_at`, `close_book`, `close_odds_raw`, `close_overround`, `q_close_home`, `q_close_draw`, `q_close_away`, `close_raw_sha256`, `close_status` |
| primary | `economic_clv`, `primary_eligible`, `primary_exclusion_reason` |
| settlement | `result_status`, `outcome`, `settlement_status`, `pnl_units`, `result_source`, `result_sha256` |
| provenance | `entry_books_manifest_sha256`, `harness_manifest_sha256`, `created_at`, `event_chain_heads` |

Odds triples are objects with exactly `home`, `draw`, `away`. UTC timestamps are
RFC 3339 with explicit `Z`. Raw price strings are retained beside full-precision
parsed decimals; no rounding occurs before selection or scoring.

`entry_quote_set` is an array in the frozen `ENTRY_BOOKS` order. It contains one
object per manifest book with exactly `book`, `provider_at`, `observed_at`,
`market_status`, `odds_raw`, `odds_net`, `overround`, `available_stake`,
`commission`, `raw_sha256`, `eligible` and `reason`. A source failure therefore
occupies its book's slot with null prices and a typed reason; it is not absence
from the array. `entry_quote_set_sha256` is the SHA-256 of that array's canonical
JSON bytes.

### 7.3 Closed reason vocabulary

`decision_status` is exactly one of `bet_intent`, `non_bet`, `failure`, `void`.
A valid non-bet has reason `no_edge`. Typed failure/void reasons are the closed
set:

```
fixture_unmapped
model_missing
model_late
model_invalid
model_arm_mismatch
schedule_changed_pre_entry
entry_source_unreachable
entry_quote_missing
entry_quote_stale
entry_market_suspended
entry_market_incomplete
entry_market_malformed
entry_price_not_purchasable
book_unavailable
close_source_unreachable
close_quote_missing
close_quote_stale
close_market_incomplete
close_market_malformed
entry_book_void
fixture_abandoned
fixture_unresolved_at_H2
result_missing
row_conflict
```

A new reason changes the schema and requires a preregistered amendment before it
is used. Free-text detail may accompany a reason but cannot replace it.
`result_missing` affects only settlement secondaries when model, entry, stand/
void status and close are otherwise valid; it never removes an observed primary
economic-CLV row and by itself cannot prevent PASS.

---

## 8. Validity and failure semantics

### 8.1 Run-level validity gates

A numerical PASS is unavailable unless all of the following hold:

1. the fixed horizon completed and the run reached CLOSED without performance
   peeking or a hash violation;
2. every official fixture admitted under §1 has exactly one final derived row;
3. at least 95% of non-void universe fixtures have a valid model-plus-entry
   decision, whether `bet_intent` or `no_edge`;
4. every non-void `bet_intent` has a valid Pinnacle close — zero unresolved
   selected closes;
5. all model-before-entry and entry-before-close clock inequalities hold;
6. no unresolved primary fixture, team, outcome, bookmaker or duplicate-key
   conflict exists; and
7. the preregistration, model law, realised config, entry-book manifest, schema,
   harness and analysis code match the hash-freeze manifest byte for byte.

The 95% decision-coverage requirement prevents a thin surviving subset from
masquerading as the designed strategy. The zero-missing-selected-close rule
prevents later close availability from selecting the primary sample. A source
outage is not evidence against the model, but neither is it permission to delete
the affected fixture.

### 8.2 Outcomes on failure

- **INVALIDATED** — clocks, code/config hashes, model arm, selection rule or
  outcome independence were violated. No primary claim is made.
- **DATA-INCOMPLETE** — the law was respected but the census, decision coverage,
  close completeness or final resolution gate failed. Numerical diagnostics are
  published with the failure; there is no PASS.
- **INSUFFICIENT** — the run is valid and complete but `N < 500`. The horizon is
  not extended and there is no PASS.
- **NO PASS** — the run is valid, complete and sufficiently large, but either
  the point bar or interval bar fails.
- **PASS** — every validity gate and every numerical gate in §9 passes.

All five outcomes publish. None is silently rerun on the same forward period.

---

## 9. Adoption rule and its deliberately narrow meaning

### 9.1 The rule

> Declare **PASS** if and only if the run is VALID and COMPLETE under §8 and all
> three numerical conditions hold:
>
> 1. **`N >= 500`** primary bets;
> 2. **mean margin-adjusted economic CLV `>= +0.0100`**; and
> 3. the **95% `(season, ISO week)` block-bootstrap lower bound is strictly
>    greater than `0`**.
>
> Otherwise there is no PASS.

All three are required; none is sufficient. Equality at zero on the interval
fails. A raw odds-ratio CLV pass, profitable P&L, a favorable season, a promoted
club slice, or an alternative de-vig does not substitute for any condition.

### 9.2 What PASS authorizes

PASS means only that this frozen, mechanically selected shadow strategy showed
forward evidence of acquiring economically better-than-close prices at the
pre-stated scale. It authorizes:

1. continued shadow collection; and
2. drafting a **new preregistration** for a tiny-stake execution validation with
   an explicit currency unit, total-loss cap, slippage rule, rejected-bet record,
   account/limit evidence and stop authority.

PASS does **not** establish positive future profit, stable model edge, executable
size, account longevity, independence of bets, immunity to limits, or a right to
increase stakes. It does not authorize automated betting or even the first real
bet under this document. A tiny-stake run is a validation of execution and
price acceptance, not a scale-up.

NO PASS, INSUFFICIENT, DATA-INCOMPLETE or INVALIDATED means the model has not
earned authority to bet from this evidence plane.

---

## 10. Lifecycle: the only permitted order

| state | what may happen | what may not happen |
|---|---|---|
| **PREREGISTERED** | commit this document alone; discuss design | write a forward row, inspect a result under this rule, run a fit for it |
| **BUILT, UNFROZEN** | implement under `epl/`; test with synthetic and clearly historical fixtures | collect an admissible forward entry, alter this document silently |
| **ADVERSARIAL AUDIT** | attack clocks, identity, missingness, selection, hashes and append semantics; publish every finding | waive a failed canary or use a live result to tune a constant |
| **AUDITED** | close or explicitly refute every blocking finding | begin collection before the freeze commit |
| **HASH-FROZEN** | commit the complete manifest in §11 and mechanically set `H0/H1/H2` | change a hashed byte or book list without invalidating the run |
| **RUNNING** | append census/model/entry/close/settlement events; show operational health only | show performance, change selection, stop for a bad number |
| **CLOSED** | stop new decisions at `H1`; resolve admitted rows through `H2`; run the frozen analysis once | add fixtures, repair by deleting rows, choose a favorable subset |
| **PUBLISHED** | publish PASS, NO PASS, INSUFFICIENT, DATA-INCOMPLETE or INVALIDATED with evidence | suppress an unfavorable outcome or rerun this period as new evidence |

State transitions are forward-only. A post-freeze substantive change creates a
new run with a new preregistration or a dated amendment committed before its new
forward horizon. It cannot inherit already-observed rows as confirmatory data.

---

## 11. Required adversarial audit and hash freeze

### 11.1 Minimum audit

Before freeze, an independent adversarial review must demonstrate at least:

- close/result mutation leaves decisions byte-identical and the entry positive
  control moves a decision;
- every clock boundary accepts exact equality only where this document allows it
  and refuses one-microsecond violations;
- a missing book in an early snapshot cannot make a later close become entry;
- home/away swaps, fuzzy aliases, duplicate fixtures and cross-market joins
  refuse rather than guess;
- a source outage, suspended market, malformed triple, zero-edge fixture and
  missing close each produce the exact typed row this document requires;
- exact replay is a no-op and a substantive same-key conflict refuses atomically;
- no failure/non-bet path can omit the fixture from the final census;
- exchange commission is applied once, bookmaker commission zero times, and
  proportional de-vig sums to one;
- at most one outcome and exactly one unit are selected per fixture;
- all zero-bet active weeks survive in the evidence universe and selection-rate
  denominator, while the bootstrap inventory contains exactly the populated
  primary-bet weeks;
- interim surfaces contain no primary or proxy performance number; and
- the full result can be reproduced from source ledgers and raw-response hashes
  without reading an untracked mutable file.

Audit findings are published with disposition `CLOSED`, `REFUTED` with evidence,
or `BLOCKING`. Any `BLOCKING` finding prevents hash freeze.

### 11.2 Freeze manifest

The freeze commit records path, byte count, line count where meaningful and
SHA-256 for:

- this preregistration;
- every harness, schema, analysis and bootstrap file;
- the primary model-law and realised-config artifacts;
- the ordered entry-book/access/commission/void manifest;
- bookmaker, team, fixture and outcome registries;
- quote-source and schedule-source parsers;
- the closed reason vocabulary and evidence schema;
- synthetic audit fixtures and their expected outputs;
- the audit report and finding ledger;
- Python, NumPy and relevant dependency versions; and
- the empty/genesis event-ledger state, run id, `H0`, `H1`, `H2`, seed and all
  constants in §0.

At every append and at analysis, the harness verifies the manifest. If any
hashed byte differs, the output is INVALIDATED, not “close enough.” Raw forward
responses are content-hashed at capture and may remain private; their digest,
timestamps, source and byte count must be present in the evidence record.

---

## 12. Scope and lock boundary

This document preregisters measurement only. It does not modify `dc_native`,
fit a model, change the EPL ingestion schema, wire E1 data, alter the simulator,
publish odds, or place a bet.

The intended harness belongs under `epl/` with its own data/evidence paths. If
the future build genuinely requires any change under `src/` or `scripts/`, those
paths are covered by the existing OA lock and the change must arrive in a new
chained lock version before HASH-FROZEN. This document supplies no exception.

The next legal action is **build**, followed by **adversarial audit**, then
**hash freeze**, then and only then the first forward row. The result publishes
either way.

---

## Clarification 1 — the thirty minutes bind issuance, not the durable seal (2026-09-01)

**Status:** clarification of this document against itself, written before hash
freeze, before any forward row, and with `epl/beteval.py` still
`BUILT_UNFROZEN`. No rule changes. No reason is added to §7.3. §2.1(1), §2.1(3),
§2.2 and §8.1(5) stand exactly as written.

### What was found

An independent full-system review on 2026-08-31 flagged that
`epl/beteval.py` enforced a rule this document's operative sections do not
state. Two places:

```
epl/beteval.py:340    if sealed > seal_deadline:
epl/beteval.py:341        raise ClockError("model seal must be durable no later than target minus 30m")
epl/beteval.py:368    if clocks["model_sealed_at"] > clocks["entry_target"] - 30 * 60:
epl/beteval.py:369        raise ClockError("model seal must be durable no later than target minus 30m")
```

Both require the DURABLE SEAL to have completed by `T_entry - 30m`. §2 requires
no such thing. §2.1(1) bounds `model_issued_at` at `T_entry - 30 minutes`;
§2.1(3) bounds the seal — "hashed and appended" — by ORDER, before the first
entry-source request for that fixture; §2.2 forbids the collector from
requesting a price until that seal is durable. The seal has an upper bound in
this document, and it is `first_entry_request_at`, not a deadline.

The reviewer read §2 correctly and the implementer read §0 correctly, which is
the actual finding. §0's row —

| model clock | forecast bundle sealed at least 30 minutes before the entry target and before any entry quote is observed |

— compresses two clocks into one word. "Sealed" there means the bundle is
FIXED, which is §2.1(1)'s bound on `model_issued_at`; the second clause is
§2.1(3)/§2.2's ordering bound on the durable append. Read as one sentence about
one clock, it says the append must beat `T_entry - 30m`, and that is what got
built.

### The clarification

**§0's `model clock` row is to be read as, and is hereby restated as:** *the
forecast bundle is issued at least 30 minutes before the entry target (§2.1(1)),
and its durable seal is appended before the first entry-source request and
therefore before any entry quote is observed (§2.1(3), §2.2).*

Two clocks, two different bounds, as §2 has said throughout.

### Why the operative rule is the safe one, and the stricter code is not safer

The threat §2 exists to close is a model number influenced by a price. Four
facts close it, and none of them is a seal deadline.

1. **The price does not exist yet.** The first eligible entry quote is at or
   after `T_entry` (§2.2). A model issued at or before `T_entry - 30m` cannot
   have read one.
2. **The numbers are fixed at issuance, not at the append.** §2.1(3) requires
   the seal to cover the forecast bundle, the model-law digest, the realised
   configuration digest and the exact `{home, draw, away}` triple. The append is
   a RECORDING step over values that were already determined; completing it
   later does not re-decide them.
3. **The append strictly precedes any observation.** §2.2 gates the collector on
   the seal, and the code enforces the strict inequality
   `model_sealed_at < first_entry_request_at` — equality is refused. The window
   between issuance and the append is a window in which no price has been
   requested at all.
4. **The leakage canary tests the barrier, not the buffer.** §2.4 mutates every
   close and every result while holding model and entry events fixed, and
   requires an entry mutation to move a selection. A seal completing at
   `T_entry - 29m` changes nothing that canary can see, because there is nothing
   to see.

So the deleted rule bought no information property. It bought thirty minutes of
operational slack for a durable write — a reliability margin — and it charged
for it in the one currency this design cannot spend.

**What it charged.** A run in which the model is issued at `T_entry - 90m` and
its seal lands at `T_entry - 12m`, with the first entry request at `T_entry`, is
leak-free under every clause of §2 and refused by the shipped code. In a harness
that refusal must become a typed pre-decision row, and the only reason in
§7.3's closed set that fits a model-clock violation is `model_late` — a row that
is not a `bet_intent` and not a `no_edge`, and therefore a row that counts
against §8.1(3)'s requirement that **at least 95% of non-void universe fixtures
have a valid model-plus-entry decision**. Enough of them and a valid,
uncontaminated forward run reports **DATA-INCOMPLETE** (§8.2) over an append
that finished eleven minutes late.

§8.1(3) exists to stop a thin surviving subset from masquerading as the designed
strategy. Spending it on clock arithmetic the design never fixed inverts it: it
would remove fixtures whose model and entry records are both valid, which is the
selection effect the gate is there to prevent.

**And the honest direction of the fix.** Both readings cannot be law. The choice
is between deleting a refusal from unfrozen code with no forward row behind it,
and widening this document to make the stricter reading binding — where §7.3 is
explicit that the vocabulary "requires a preregistered amendment before it is
used", and §11.2 hash-freezes the preregistration and the harness together.
Tightening a preregistration to match an accident of implementation, before the
audit that is supposed to check the implementation against it, is the wrong
order of operations even when the tighter rule is harmless. This one is not
harmless.

### What changes in code

`epl/beteval.py` loses exactly the two refusals quoted above. `seal_deadline` is
renamed `issue_deadline`, which is what it always was: the bound on
`model_issued_at` in §2.1(1). Every other clock check is untouched, including
`sealed < issued` ("durable model seal cannot precede model_issued_at") and
`model_sealed_at >= first_entry_request_at` ("model seal must precede first
entry-source request"), which is the barrier itself.

`validate_model_seal` deliberately bounds the seal only from below and its
docstring now says so, naming `validate_quote_clocks` as the function that holds
§2.1(3). **A harness that validates a seal and never validates that fixture's
quote clocks has not enforced §2.1(3)**, and §11.1's audit — whose second bullet
already requires that "every clock boundary accepts exact equality only where
this document allows it and refuses one-microsecond violations" — must
demonstrate that the built harness calls both for every census fixture.

`epl/tests/test_beteval.py` drops the assertion that a seal one microsecond
after `T_entry - 30m` refuses, and gains
`test_the_thirty_minutes_bind_issuance_and_the_seal_is_bound_by_ordering`, which
accepts a seal at `T_entry - 1μs` and refuses one at exactly
`first_entry_request_at`. The parametrised `model_sealed_at` boundary case is
kept and re-annotated: it now proves the ordering rule rather than a deadline.

Nothing under `src/` or `scripts/` is touched, and §12's lock boundary is not
approached. Suite green: `epl/tests/test_beteval.py`, 50 passed.
