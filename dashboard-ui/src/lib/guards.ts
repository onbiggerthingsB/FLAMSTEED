import type { Gap } from './types';
export function isGap(x: unknown): x is Gap {
  if (x === null || x === undefined) return true;            // missing data -> render as a gap
  return typeof x === 'object' && (x as Record<string, unknown>).coverage_gap === true;
}
