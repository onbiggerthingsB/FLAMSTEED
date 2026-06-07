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
