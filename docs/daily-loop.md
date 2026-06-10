# Daily forecast loop — `scripts/daily_update.py`

One idempotent command that refreshes the production WC-2026 forecast from the
freshest ingested results. **Zero Odds-API credits** — the value scan
(`scripts/scan_value.py`) is a separate, manual command and this loop never
touches odds.

```
PYTHONPATH=src .venv/bin/python scripts/daily_update.py [--cutoff 2026-06-12T00:00:00Z] [--latest] [--manual-results day1.csv] [--dry-run]
```

> Run it as a **script** (`PYTHONPATH=src .venv/bin/python …`), **never** `uv run`
> — `uv run` breaks the editable install. (Recovery if you ever do:
> `uv pip install -e . >/dev/null 2>&1`.)

## Post-matchday recipe (one command)

After a matchday, the freshest results land in the martj42 feed. To pick them up
and rebuild in **one command**, add `--latest`:

```
PYTHONPATH=src .venv/bin/python scripts/daily_update.py --latest
```

`--latest` resolves the newest martj42 `master` commit via **one** call to the
free GitHub commits API
(`api.github.com/repos/martj42/international_results/commits/master`) and ingests
**that** sha instead of the source pin. This automates the manual pin-bump that
was previously a hand step (the P0 Task-1 bump,
`api.github.com/.../commits/master` → edit `MARTJ42_COMMIT`). It is the **free**
GitHub API, **not** the Odds API — zero Odds-API credits, as always.

> **The source pin remains the reproducibility anchor.** `--latest` is a
> *runtime* override threaded through the fetch path (URL + cache key + the
> store's `source_version`); it **never** edits `MARTJ42_COMMIT` in
> `src/wcmodel/data/sources/results.py`. Default (no flag) ingest is unchanged
> and byte-identical. To make a fresh sha the permanent, reproducible anchor,
> bump the pin in source and commit it.

> **Failure mode — fails loud, never silently stale.** If the GitHub API call
> errors (network down, rate-limited, unexpected shape), `--latest` **aborts**
> before any expensive step with a non-zero exit and a clear message. It will
> **never** silently fall back to the stale pin while claiming freshness. The
> manual fallback when the API is unavailable: re-run **without** `--latest` (to
> rebuild on the current pin), or bump `MARTJ42_COMMIT` by hand and re-run pinned.

> If `--latest` resolves a sha **equal to** the current pin (no new data since
> the last bump), the run **still proceeds** (idempotent) and notes it.

## Manual matchday-1 fallback (`--manual-results`) — independent of upstream timing

martj42 publishes the **previous** calendar day's matches once per morning
(~06:00–08:00 UTC). Measured median post-match → committed lag is **≈ 31 h
(~1.3 days)**, and it goes **multi-day to weeks** when the maintainer batches a
window into a single commit. So an evening matchday-1 final is **not** in upstream
until the next morning at the earliest. When you can't wait, **hand-enter the
score** and condition the bundle yourself.

### The exact two-command flow (the acceptance flow)

1. **Write the CSV** (`day1.csv`). Header + one row per played match — see
   `docs/manual_results_example.csv`:

   ```csv
   date,home_team,away_team,home_score,away_score,shootout_winner
   2026-06-11,Mexico,South Africa,3,1,
   ```

2. **Run the loop** (auto-cutoff; the manual rows condition the sim):

   ```
   PYTHONPATH=src .venv/bin/python scripts/daily_update.py --manual-results day1.csv
   ```

   → conditioned bundle staged in **~25 min** (production 48-team posterior fit +
   20k sim). Composes with `--latest`: `--manual-results day1.csv --latest`
   resolves the freshest pin, assembles martj42, **then** adds your manual rows.

   **Validate first without ingesting:** add `--dry-run` to check the CSV (it
   prints the parsed rows, the file sha256, and the implied cutoff) and exit.

### The CSV contract (STRICT, fail-loud, NEVER fuzzy)

- **Columns:** `date,home_team,away_team,home_score,away_score` (+ optional
  `shootout_winner`). A wrong/extra/missing column rejects the file.
- **Team names** must **exactly** match `config/tournament_2026.yaml` (the drawn-48
  martj42 keys). A typo/unknown name is **rejected** — never auto-corrected.
- **`(home,away,date)`** must equal a **real scheduled fixture** (group fixtures
  carry concrete nations; matched by the exact triple). A flipped home/away or a
  wrong date rejects.
- **Scores** must be finite, non-negative, integral (no `1.5`, no `-1`, no truncation).
- **A level KNOCKOUT score requires `shootout_winner`** ∈ {the two teams in that
  row}. A level **group** score is a legal draw and must leave `shootout_winner`
  empty; a `shootout_winner` on a non-level or group score rejects.

The **whole file is validated before any row is written** — a bad file aborts with
a clear message and a non-zero exit, never a partial ingest.

### How the manual rows reach the sim (and why the cutoff matters)

Each validated row is written through the **existing** leakage-safe
`ingest_live.ingest_live_result` POINT_IN_TIME path **after** the martj42 assembly,
with `valid_as_of` = the match date and **`observed_at` = now** (the real
hand-entered-result vector). It keys on the **same** `match_id` as the upstream
schedule/result row, so `read(cutoff)` sees it and the sim conditions on it.

> **The load-bearing cutoff rule.** Both the training panel (`features.build`) and
> the sim conditioning (`sim.run._played_as_of`) filter results with the **strict,
> day-floored** predicate `date < cutoff_day` (where `cutoff_day = cutoff.normalize()`).
> A match played **today** (`date = today 00:00`) is **not** `< today 00:00`, so it is
> **excluded** at the default cutoff `today 00:00 UTC` — **and even at `cutoff = now`**
> (e.g. today 21:00 UTC, whose `cutoff_day` is still today 00:00). To condition a
> day-`D` match, `cutoff_day` must be **strictly after `D`** (i.e. `cutoff ≥ D+1
> 00:00 UTC`).
>
> So `--manual-results` **auto-implies `cutoff = (max manual-row date) + 1 day` at
> `00:00:00Z`** when you don't pass `--cutoff` — making today's finals condition. If
> you pass an explicit `--cutoff` that is **not** strictly after a manual row's date,
> the run **fails loud** (that result could never condition — an operator error, not a
> silent no-op). At the implied `D+1` cutoff the day-`D` match is unambiguously in the
> past: it informs **both** the fit (Elo update) and the sim conditioning, leakage-safe.

> **Re-run / cache note.** The fit is cutoff-keyed. A same-day rerun with the **same**
> manual rows reuses the cached posterior **only if** the `< cutoff` training-panel
> hash is unchanged. Today's hand-entered match (date `D < D+1 = cutoff_day`) **does**
> enter the `< cutoff` panel at the implied cutoff, so adding/changing a manual row
> legitimately re-fits; re-running with an identical CSV is a cache hit.

### Reconciliation when martj42 catches up

When the next-morning martj42 pull carries the same match, both rows share the same
`match_id`. The store's deterministic tie-break is `observed_at DESC, valid_as_of
DESC, _ingest_seq DESC`. The manual row's `observed_at` is your (earlier) entry time;
the upstream row, re-pulled **later**, has a later `observed_at` → **the
later-observed upstream value wins** at read. Once upstream carries the match, simply
**drop that row from the CSV** (or run pure `--latest`) — upstream is the source of
record. The **provenance** line + run-log record `manual_rows: N` and
`manual_file_sha256` so any hand-entered run is auditable.

## What it does

A thin operator harness over the unchanged, already-leakage-gated pipeline. Each
step prints a `[step]` line; the order is fixed:

1. **ingest** — assemble a fresh `BitemporalStore` from the martj42 cache via the
   canonical `load_results` (POINT_IN_TIME write keyed `match_id`). Cached fetch +
   keyed writes ⇒ re-ingest is duplicate-free. By default the **source-pinned**
   commit is used; with `--latest` the runtime-resolved sha is threaded into the
   fetch (URL + cache key + store `source_version`) instead. With
   `--manual-results <csv>`, the validated hand-entered rows are written —
   **after** the martj42 assembly — through the leakage-safe
   `ingest_live.ingest_live_result` path (`observed_at = now`), so the sim
   conditions on them (see the manual-fallback section above).
2. **gate** — re-read the store at the cutoff and fail loud (`SystemExit`) if any
   row is dated on/after the cutoff, or the max valid-played date is not strictly
   before it. This is the same leakage guard as `build_real_snapshot`, run
   **before** the expensive fit/sim so a contaminated build is aborted early.
3. **snapshot** — `build_snapshot(cutoff, …, tournament=None, items=[])` over the
   verified `config/tournament_2026.yaml` 48-team draw. Internally composes
   panel → posterior fit → 20k-sim Monte-Carlo → gated bundle write, all through
   the content-addressed caches.
4. **stage** — `node dashboard-ui/scripts/copy-bundle.mjs` copies the newest
   bundle dir into the viewer's `public/bundle/` (it picks newest by mtime).
5. **provenance** — read back `<bundle>/meta.json`, print
   `as_of / posterior_key / git / n_sims / martj42_commit (source) / manual_rows /
   manual_file_sha256`, and append one JSON line to `logs/daily_update.jsonl`. The
   line records the martj42 `commit` ingested and its `commit_source` (`pinned` or
   `latest-resolved`), plus `manual_rows` (count of hand-entered results) and
   `manual_file_sha256` (the CSV fingerprint) — provenance honesty, so the log never
   claims freshness it didn't fetch and a hand-entered run is auditable.

`--cutoff` defaults to **today 00:00 UTC** (`YYYY-MM-DDT00:00:00Z`); with
`--manual-results` and no `--cutoff` it instead auto-implies `(max manual date)+1
day` so today's finals condition (see the manual-fallback section).
`--latest` resolves and ingests the newest martj42 `master` commit (see the
post-matchday recipe above) instead of the source pin; the default is the pin
(byte-identical).
`--manual-results <csv>` ingests hand-entered played fixtures (the matchday-1
fallback); composes with `--latest`/`--cutoff`.
`--dry-run` prints the resolved plan (cutoff, store path, out_root, steps,
commit, and — with `--manual-results` — the parsed rows + file sha256) and exits 0
— **no network, no fit, no writes**. `--dry-run --latest` prints that it *would*
resolve the latest commit but makes **no** API call; `--dry-run --manual-results`
validates the CSV and prints what would be ingested without ingesting.

## Idempotence / cache behavior

Designed for `nohup` and safe to re-run **any number of times the same day**:

- the martj42 pull is content-addressed by pinned commit ⇒ a cached no-op;
- keyed POINT_IN_TIME store writes are duplicate-free;
- the posterior fit and the 20k sim hit their content-addressed caches on the
  same `cutoff` + seed, so the bundle is rewritten **byte-identical**;
- staging just re-copies the (identical) newest bundle.

So a same-day re-run does no new compute beyond cache-key checks. A **new** day
(new cutoff) or a **new** ingest (new results) legitimately re-fits.

## `nohup` usage

```
mkdir -p logs
nohup env PYTHONPATH=src .venv/bin/python scripts/daily_update.py \
  > logs/daily_update_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
# then tail the log:
tail -f logs/daily_update_*.log
```

Expect: ingest counts → `[gate] OK` → fit (fresh on a new cutoff) → sim → bundle
path → `[stage] staged …` → the `[provenance]` summary line.

## The provenance line to check

After a run, the last useful line is:

```
[provenance] as_of=<cutoff> posterior_key=<hash> git=<sha> n_sims=20000 martj42_commit=<sha> (pinned|latest-resolved) manual_rows=<N> manual_file_sha256=<hash|None>
```

and one JSON line is appended to `logs/daily_update.jsonl`:

```json
{"ts": "...", "cutoff": "...", "bundle": "...", "posterior_key": "...", "git": "...", "n_sims": 20000, "duration_s": ..., "commit": "<martj42 sha>", "commit_source": "pinned|latest-resolved", "manual_rows": 0, "manual_file_sha256": null}
```

Confirm `cutoff` is the as-of you intended, `git` is your branch HEAD,
`posterior_key` changed iff the inputs (cutoff/results/config) changed, and
`commit` / `commit_source` match what you intended (the pin, or a fresher sha
under `--latest`).

## Scheduling — examples only, **NOT installed** (the user decides)

The loop is safe under a scheduler, but **nothing here installs one**. Pick one
if and when you want it.

### crontab (06:30 local, daily)

```cron
30 6 * * * cd ~/worldcup && PYTHONPATH=src .venv/bin/python scripts/daily_update.py >> logs/cron.out 2>&1
```

### launchd (macOS) — `~/Library/LaunchAgents/com.worldcup.daily-update.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.worldcup.daily-update</string>
  <key>WorkingDirectory</key><string>~/worldcup</string>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONPATH</key><string>src</string></dict>
  <key>ProgramArguments</key>
  <array>
    <string>~/worldcup/.venv/bin/python</string>
    <string>scripts/daily_update.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>~/worldcup/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>~/worldcup/logs/launchd.err</string>
</dict>
</plist>
```

To install (only if you choose to):
`launchctl load ~/Library/LaunchAgents/com.worldcup.daily-update.plist`.

> Both examples are recipes, **not** installed by this repo. Scheduling is a
> deliberate user decision (mission Phase 0 §2 / spec §6 out-of-scope).
