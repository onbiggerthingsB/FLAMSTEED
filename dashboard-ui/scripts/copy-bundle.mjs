// Populate public/bundle/ for dev/preview/e2e: prefer the newest live data/dashboard/<cutoff>/,
// else fall back to the committed synthetic fixture bundle (so the app + e2e always have data).
// ALSO populate public/bundle/value.json — the PRIMARY +EV value bundle — preferring the newest
// live value scan (data/dashboard/value/<scan_ts>.json), else the committed fixture value bundle.
// The model bundle and the value bundle are INDEPENDENT artifacts read side by side; the cheap
// value scan never triggers a model fit/sim, so each is sourced separately here.
import { existsSync, mkdirSync, readdirSync, rmSync, cpSync, copyFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
const root = resolve(import.meta.dirname, '..');
const live = resolve(root, '..', 'data', 'dashboard');
const fixture = join(root, 'tests', 'fixtures', 'bundle');
const dest = join(root, 'public', 'bundle');

let source = null;
if (existsSync(live)) {
  // Pick the NEWEST live bundle dir by mtime, not lexical order: the dir names are ISO
  // cutoffs today (so lexical == chronological), but mtime is robust if a future
  // non-ISO dir name is ever introduced — a freshly-written bundle always wins.
  // Exclude the `value/` subdir — it holds value-scan JSON files, not a model bundle dir.
  const dirs = readdirSync(live)
    .filter((d) => d !== 'value')
    .map((d) => ({ name: d, path: join(live, d) }))
    .filter((d) => statSync(d.path).isDirectory())
    .sort((a, b) => statSync(a.path).mtimeMs - statSync(b.path).mtimeMs);
  if (dirs.length) source = dirs[dirs.length - 1].path;
}
if (!source) source = existsSync(fixture) ? fixture : null;
if (!source) { console.warn('no bundle found (live or fixture)'); process.exit(0); }

rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
cpSync(source, dest, { recursive: true });
console.log(`copied bundle ${source} -> public/bundle/`);

// Value bundle: newest live value scan, else the committed fixture value bundle.
const liveValue = join(live, 'value');
let valueSource = null;
if (existsSync(liveValue)) {
  const files = readdirSync(liveValue)
    .filter((f) => f.endsWith('.json'))
    .map((f) => ({ name: f, path: join(liveValue, f) }))
    .filter((f) => statSync(f.path).isFile())
    .sort((a, b) => statSync(a.path).mtimeMs - statSync(b.path).mtimeMs);
  if (files.length) valueSource = files[files.length - 1].path;
}
if (!valueSource) {
  const fixtureValue = join(fixture, 'value.json');
  valueSource = existsSync(fixtureValue) ? fixtureValue : null;
}
if (valueSource) {
  copyFileSync(valueSource, join(dest, 'value.json'));
  console.log(`copied value bundle ${valueSource} -> public/bundle/value.json`);
} else {
  console.warn('no value bundle found (live or fixture) — Value Bets surface will 404');
}
