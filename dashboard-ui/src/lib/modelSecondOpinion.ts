// Model "second opinion" join (DISPLAY-ONLY context — NOT the betting edge).
//
// The +EV value board is market-vs-market: a soft book beating the de-vigged sharp
// (Pinnacle) line. Our scoreline MODEL has NO proven betting edge, so it MUST NOT drive
// the edge or the bettable decision. This helper is a pure read-side join used only to
// SHOW, next to each value pick, what our independent forecast thinks of that same
// outcome — and whether it agrees or disagrees with the de-vigged market.
//
// It touches nothing in the scanner / edge path. It is a one-way lookup from a value bet
// into the already-loaded forecast (schedule) bundle.

import type { ValueBet, ScheduleData, GroupRow } from './types';
import { isGap } from './guards';

// The forecast bundle (from the model) and the value bundle (from the odds API) both name
// teams off the same tournament source — but two teams render with different surface forms
// on the odds wire than in the model bundle. We join on EXACT team name first; this tiny,
// explicit alias map only reconciles the KNOWN odds-API ↔ model display divergences so
// those fixtures join too. It is NOT fuzzy matching: only these exact tokens are aliased,
// so it can never mis-join two genuinely different teams.
const TEAM_ALIASES: Record<string, string> = {
  // odds-API form            -> model (schedule) form
  'Bosnia & Herzegovina': 'Bosnia and Herzegovina',
  USA: 'United States',
};

function canon(team: string): string {
  const t = team.trim();
  return TEAM_ALIASES[t] ?? t;
}

// Parse the value bet's "Home v Away" event label into its two team names. The scanner
// emits exactly " v " as the separator. Returns null if the label is not in that shape.
export function parseEvent(event: string): { home: string; away: string } | null {
  const parts = event.split(' v ');
  if (parts.length !== 2) return null;
  const home = parts[0].trim();
  const away = parts[1].trim();
  if (!home || !away) return null;
  return { home, away };
}

// A flat fixture -> 1X2 index built once from the schedule bundle. Keyed by the canonical
// "home|away" pair so the value bet can be matched by exact (home, away) team names.
export type ForecastIndex = Map<string, { home: number; draw: number; away: number }>;

export function buildForecastIndex(schedule: ScheduleData | null | undefined): ForecastIndex {
  const idx: ForecastIndex = new Map();
  if (!schedule) return idx;
  for (const row of schedule.group as GroupRow[]) {
    // forecast_summary is Maybe<…>: a coverage gap (or missing) has no 1X2 to join.
    if (isGap(row.forecast_summary)) continue;
    const oxt = row.forecast_summary.one_x_two;
    if (!oxt) continue;
    idx.set(`${canon(row.home)}|${canon(row.away)}`, {
      home: oxt.home,
      draw: oxt.draw,
      away: oxt.away,
    });
  }
  return idx;
}

// The model's take on a single value-bet outcome (display-only).
//   prob    — the model's probability for the SAME outcome the value pick names, or null
//             when the model has no joinable view (no matching fixture, or a market —
//             e.g. totals — whose model probability is not exposed in the viewer).
//   agrees  — true  iff prob >= sharpFairProb (model rates it >= market)
//             false iff prob <  sharpFairProb (model rates it below market)
//             null  when prob is null (no model view → render "—")
export interface ModelSecondOpinion {
  prob: number | null;
  agrees: boolean | null;
}

// Resolve OUR model's probability for the exact outcome a value bet names, then compare it
// to the de-vigged sharp fair prob to decide agree/disagree. DISPLAY-ONLY: callers must
// NOT feed this back into edge / bettable / ordering — it never participates in the
// decision, only the presentation.
export function modelSecondOpinion(bet: ValueBet, idx: ForecastIndex): ModelSecondOpinion {
  const prob = modelProbForBet(bet, idx);
  if (prob === null) return { prob: null, agrees: null };
  // Tie (model_prob === sharpFairProb) counts as agreement: model rates it >= market.
  return { prob, agrees: prob >= bet.sharpFairProb };
}

function modelProbForBet(bet: ValueBet, idx: ForecastIndex): number | null {
  // Only h2h (1X2) is joinable from the viewer-loaded forecast bundle. The model scoreline
  // GRID needed for totals P(over/under) lives only in the per-fixture detail files, which
  // the value surface does not load — so totals return null ("—"). Totals are a minority of
  // picks; the spec is explicit not to block on them.
  if (bet.market !== 'h2h') return null;

  const teams = parseEvent(bet.event);
  if (!teams) return null;
  const oxt = idx.get(`${canon(teams.home)}|${canon(teams.away)}`);
  if (!oxt) return null;

  const side = canon(bet.side);
  if (side === 'Draw') return oxt.draw;
  if (side === canon(teams.home)) return oxt.home;
  if (side === canon(teams.away)) return oxt.away;
  // Side is neither team nor "Draw" — no honest mapping; show "—".
  return null;
}
