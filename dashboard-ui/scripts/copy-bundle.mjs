// Populate public/bundle/ for dev/preview/e2e: prefer the newest live data/dashboard/<cutoff>/,
// else fall back to the committed synthetic fixture bundle (so the app + e2e always have data).
import { existsSync, mkdirSync, readdirSync, rmSync, cpSync, statSync } from 'node:fs';
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
  const dirs = readdirSync(live)
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
