// The uncertainty grammar. LOAD-BEARING: the project's "no naked numbers" rule
// lives here. A probability is ALWAYS formatted WITH its uncertainty — there is
// no input to pctPlusMinus that yields a bare number with no ± or —.

export function pct(p: number | null | undefined, dp = 0): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return '—';
  return `${(p * 100).toFixed(dp)}%`;
}

// The no-naked-number primitive: an estimate ALWAYS carries its SE (in percentage points).
// value present but se null -> "±?" (explicit unknown), never a silent bare number.
export function pctPlusMinus(value: number | null | undefined, se: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const v = `${Math.round(value * 100)}%`;
  if (se === null || se === undefined || !Number.isFinite(se)) return `${v} ±?`;
  // An SE is a magnitude: abs() guards against a malformed negative-SE token (±-0.3) without crashing the display.
  const pts = Math.abs(se) * 100;
  const dp = pts > 0 && pts < 1 ? 1 : 0;
  return `${v} ±${pts.toFixed(dp)}`;
}

// A non-probability estimate (E[Pts], E[GD]) ALWAYS carries its SE — same no-naked-number
// rule as pctPlusMinus, but the value is a plain number (points / goal difference), NOT a
// percentage. `signedValue` renders E[GD] with an explicit + / − sign (a goal difference is
// signed); E[Pts] is unsigned. value null -> "—" (a null, never a bare number). se null ->
// "±?" (explicit unknown), never a silent bare number.
export function numPlusMinus(
  value: number | null | undefined,
  se: number | null | undefined,
  { dp = 1, signedValue = false }: { dp?: number; signedValue?: boolean } = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const sign = signedValue ? (value < 0 ? '−' : '+') : '';
  const v = `${sign}${Math.abs(value).toFixed(dp)}`;
  if (se === null || se === undefined || !Number.isFinite(se)) return `${v} ±?`;
  return `${v} ±${Math.abs(se).toFixed(dp)}`;
}

const MINUS = '−'; // U+2212, not hyphen
function signed(x: number, dp = 2): string {
  const s = (Math.abs(x) * 100).toFixed(dp === 2 ? 1 : dp);
  return x < 0 ? `${MINUS}${s}` : `+${s}`;
}

export function ciText(ci: [number, number]): string {
  const f = (x: number) => (x < 0 ? MINUS : '') + Math.abs(x).toFixed(2);
  return `[${f(ci[0])}, ${f(ci[1])}] (94% HDI)`;
}

export function edgeChip(edge: number | null | undefined): string {
  if (edge === null || edge === undefined || !Number.isFinite(edge) || edge === 0) return 'no edge';
  return `${edge > 0 ? '▲' : '▼'} ${signed(edge)}%`;
}

export function formatDate(d: string): string { return d.split(' ')[0]; }

// ── Value-scanner formatters ────────────────────────────────────────────────────
// Decimal odds: a market datum, shown to 2dp (never a probability — no ± companion).
export function decimalOdds(o: number | null | undefined): string {
  if (o === null || o === undefined || !Number.isFinite(o)) return '—';
  return o.toFixed(2);
}

// Freshness: how stale a line quote is, as a human age. Edges evaporate in minutes, so
// the viewer surfaces the quote's age (from the API last_update vs the scan timestamp).
// Returns "—" when either timestamp is missing/malformed (never a fabricated age).
export function freshness(lastUpdate: string | null | undefined, scanTs: string): string {
  if (!lastUpdate) return '—';
  const lu = Date.parse(lastUpdate);
  const now = Date.parse(scanTs);
  if (!Number.isFinite(lu) || !Number.isFinite(now)) return '—';
  const sec = Math.max(0, Math.round((now - lu) / 1000));
  if (sec < 90) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 90) return `${min}m ago`;
  const hr = Math.round(min / 60);
  return `${hr}h ago`;
}

// ¼-Kelly suggested stake as a fraction of bankroll — a SUGGESTION signal, never an
// instruction and never auto-acted. Derived; renders inside data-derived.
export function stakeSignal(frac: number | null | undefined): string {
  if (frac === null || frac === undefined || !Number.isFinite(frac) || frac <= 0) return '—';
  return `${(frac * 100).toFixed(2)}% of bankroll`;
}
