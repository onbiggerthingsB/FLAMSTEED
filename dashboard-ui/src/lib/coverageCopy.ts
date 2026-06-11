// Reason-aware copy for the CoverageGap badge.
//
// The data layer emits a `reason` string with every `coverage_gap` node (canonical
// constructor `dashboard/schema.py:coverage_gap`). CoverageGap.svelte historically printed
// the single literal "insufficient coverage" for EVERY reason — misleading, because almost
// none of the gaps are a history shortage. This module maps each emitted reason to terse,
// honest badge copy classified from the EMITTING CONDITION in the data layer:
//
//   • TIME-RESOLVING  — fills on its own as the tournament progresses or the next scan runs.
//                       Copy says WHEN it resolves.
//   • STRUCTURAL      — never fills without a system change (unfunded feed, historical-only
//                       source, data-integrity gap). Copy says WHY.
//   • "insufficient"  — RESERVED, exclusively, for the genuine history condition
//                       ("no played history as-of cutoff"), which currently never fires
//                       (every WC-2026 team has hundreds of played internationals as-of
//                       cutoff — see reports/coverage_audit_2026-06-11.md).
//
// ── Reason inventory (mirrored from the data layer; keep in sync if the emitters change) ──
// Enumerated by grepping `coverage_gap(` + inline `{"coverage_gap": True, "reason": …}` over
// src/wcmodel/. file:line + emitting condition + classification:
//
//   "no played history as-of cutoff"                  src/wcmodel/dashboard/build.py:290,295,305
//        _recent_form: team has 0 valid-played matches <= cutoff. HISTORY — never fires today.
//   "xg not StatsBomb-covered for this fixture"        src/wcmodel/dashboard/why.py:37
//        xG read has no row for this (team,opp,date). STRUCTURAL (StatsBomb is historical /
//        per match_id — a future fixture is never covered).
//   "xg missing"                                       src/wcmodel/dashboard/why.py:39
//        covered but xG value null. STRUCTURAL.
//   "rest_days unknown for an unplayed fixture"        src/wcmodel/dashboard/build.py:352,359
//        features frame has no PLAYED row for this fixture. TIME-RESOLVING — fills once the
//        team has played a prior tournament match (features.build then carries the row).
//   "rest_days null as-of cutoff"                      src/wcmodel/dashboard/build.py:361
//        played row exists but rest_days null. TIME-RESOLVING (next feature build / next match).
//   "no live edge for this fixture as-of cutoff"       src/wcmodel/dashboard/build.py:582
//        no edge node for the event key. STRUCTURAL while the live-odds feed is unfunded.
//   "no live edge for this fixture"                    src/wcmodel/dashboard/build.py:608
//        schedule row with no forecaster attach. STRUCTURAL while unfunded.
//   "no forecast for this fixture"                     src/wcmodel/dashboard/build.py:606
//        forecaster skipped this fixture. STRUCTURAL.
//   "feeder {ref} resolves from a later match"         src/wcmodel/dashboard/build.py:415
//        KO winner/loser feeder (W74/L101) not yet resolved. TIME-RESOLVING — fills as the
//        bracket plays out. (parameterized by `ref`)
//   "slot {slot_source}: occupant {team} has no se companion"
//                                                      src/wcmodel/dashboard/tournament_view.py:63
//        an occupant prob with no finite SE companion. STRUCTURAL (data-integrity gap, not
//        a wait). (parameterized by slot/team)
//   "no backtest records supplied"                     src/wcmodel/dashboard/build.py:638
//        track build got no bet/pred rows. TIME-RESOLVING — fills as bets settle post-kickoff.
//   "no sharp ({sharp_book}) line"                     src/wcmodel/value/scanner.py:103
//        no sharp (Pinnacle) line for the event/market/line. STRUCTURAL while the sharp-odds
//        feed is unfunded (a scan with no funded feed never clears it). (parameterized by book)
//
// UI-introduced reasons (not from the data layer, but flow through the same `reason` prop):
//   "scoreline grid unavailable"   src/components/ScorelineGrid.svelte:58  STRUCTURAL (degenerate grid)
//   "no probable occupants"        src/components/BracketTree.svelte:75    STRUCTURAL (no eligible occupant)

export type CoverageKind = 'time-resolving' | 'structural' | 'insufficient' | 'unknown';

export interface CoverageCopy {
  /** Terse badge text (a few words — these render in a small italic span). */
  text: string;
  /** Classification, for styling / tests / a11y. */
  kind: CoverageKind;
}

// Exact-match copy for the static (non-parameterized) reason strings.
const STATIC: Record<string, CoverageCopy> = {
  // HISTORY — the ONLY reason that earns the word "insufficient" (never fires today).
  'no played history as-of cutoff': {
    text: 'insufficient coverage — no played history as-of cutoff',
    kind: 'insufficient',
  },

  // STRUCTURAL — say WHY.
  'xg not StatsBomb-covered for this fixture': {
    text: 'xG feed not covered for internationals',
    kind: 'structural',
  },
  'xg missing': {
    text: 'xG value missing for this fixture',
    kind: 'structural',
  },
  'no live edge for this fixture as-of cutoff': {
    text: 'no live edge — odds feed not funded',
    kind: 'structural',
  },
  'no live edge for this fixture': {
    text: 'no live edge — odds feed not funded',
    kind: 'structural',
  },
  'no forecast for this fixture': {
    text: 'no forecast for this fixture',
    kind: 'structural',
  },
  'scoreline grid unavailable': {
    text: 'scoreline grid unavailable',
    kind: 'structural',
  },
  'no probable occupants': {
    text: 'no probable occupants yet',
    kind: 'structural',
  },

  // TIME-RESOLVING — say WHEN it fills.
  'rest_days unknown for an unplayed fixture': {
    text: 'rest days pending — fills after first match',
    kind: 'time-resolving',
  },
  'rest_days null as-of cutoff': {
    text: 'rest days pending — fills after next match',
    kind: 'time-resolving',
  },
  'no backtest records supplied': {
    text: 'track record pending — fills as bets settle',
    kind: 'time-resolving',
  },
};

// Parameterized reasons (data-layer f-strings) matched by pattern. Ordered; first hit wins.
const PATTERNS: Array<{ re: RegExp; copy: (m: RegExpMatchArray) => CoverageCopy }> = [
  {
    // "feeder {ref} resolves from a later match"  (TIME-RESOLVING)
    re: /^feeder\s+(\S+)\s+resolves from a later match$/,
    copy: () => ({ text: 'occupant pending — fills as bracket resolves', kind: 'time-resolving' }),
  },
  {
    // "no sharp ({sharp_book}) line"  (STRUCTURAL while the sharp-odds feed is unfunded)
    re: /^no sharp \(([^)]+)\) line$/,
    copy: (m) => ({ text: `no sharp (${m[1]}) line — feed not funded`, kind: 'structural' }),
  },
  {
    // "slot {slot_source}: occupant {team} has no se companion"  (STRUCTURAL data-integrity)
    re: /^slot\s+.+:\s+occupant\s+.+\s+has no se companion$/,
    copy: () => ({ text: 'occupant uncertainty unavailable', kind: 'structural' }),
  },
];

// Neutral fallback for any reason not enumerated above — NEVER crash. The badge stays a
// coverage marker; the raw reason rides in the title/tooltip so nothing is hidden.
const DEFAULT: CoverageCopy = { text: 'data unavailable', kind: 'unknown' };

/**
 * Map a coverage-gap `reason` to terse, classified badge copy. Falls back to a neutral
 * "data unavailable" (kind: 'unknown') for any unrecognized reason — the caller surfaces
 * the raw reason in the title attribute so an unmapped reason is visible, never swallowed.
 */
export function coverageCopy(reason: string | null | undefined): CoverageCopy {
  if (!reason) return DEFAULT;
  const exact = STATIC[reason];
  if (exact) return exact;
  for (const { re, copy } of PATTERNS) {
    const m = reason.match(re);
    if (m) return copy(m);
  }
  return DEFAULT;
}

/**
 * Every static (non-parameterized) reason the data + UI layers can emit. Mirrored from the
 * inventory comment above; the drift guard test asserts each maps to non-default copy.
 * Parameterized reasons are covered by `coverageCopy` pattern tests separately.
 */
export const STATIC_REASONS: readonly string[] = Object.freeze(Object.keys(STATIC));
