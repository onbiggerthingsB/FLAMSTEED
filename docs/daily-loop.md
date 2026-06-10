# Daily forecast loop — `scripts/daily_update.py`

One idempotent command that refreshes the production WC-2026 forecast from the
freshest ingested results. **Zero Odds-API credits** — the value scan
(`scripts/scan_value.py`) is a separate, manual command and this loop never
touches odds.

```
PYTHONPATH=src .venv/bin/python scripts/daily_update.py [--cutoff 2026-06-12T00:00:00Z] [--dry-run]
```

> Run it as a **script** (`PYTHONPATH=src .venv/bin/python …`), **never** `uv run`
> — `uv run` breaks the editable install. (Recovery if you ever do:
> `uv pip install -e . >/dev/null 2>&1`.)

## What it does

A thin operator harness over the unchanged, already-leakage-gated pipeline. Each
step prints a `[step]` line; the order is fixed:

1. **ingest** — assemble a fresh `BitemporalStore` from the pinned-commit martj42
   cache via the canonical `load_results` (POINT_IN_TIME write keyed `match_id`).
   Cached fetch + keyed writes ⇒ re-ingest is duplicate-free.
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
   `as_of / posterior_key / git / n_sims`, and append one JSON line to
   `logs/daily_update.jsonl`.

`--cutoff` defaults to **today 00:00 UTC** (`YYYY-MM-DDT00:00:00Z`).
`--dry-run` prints the resolved plan (cutoff, store path, out_root, steps) and
exits 0 — **no network, no fit, no writes**.

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
[provenance] as_of=<cutoff> posterior_key=<hash> git=<sha> n_sims=20000
```

and one JSON line is appended to `logs/daily_update.jsonl`:

```json
{"ts": "...", "cutoff": "...", "bundle": "...", "posterior_key": "...", "git": "...", "n_sims": 20000, "duration_s": ...}
```

Confirm `cutoff` is the as-of you intended, `git` is your branch HEAD, and
`posterior_key` changed iff the inputs (cutoff/results/config) changed.

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
