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
  const dirs = readdirSync(live).filter((d) => statSync(join(live, d)).isDirectory()).sort();
  if (dirs.length) source = join(live, dirs[dirs.length - 1]);
}
if (!source) source = existsSync(fixture) ? fixture : null;
if (!source) { console.warn('no bundle found (live or fixture)'); process.exit(0); }

rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
cpSync(source, dest, { recursive: true });
console.log(`copied bundle ${source} -> public/bundle/`);
