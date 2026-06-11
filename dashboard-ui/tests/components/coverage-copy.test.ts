// Coverage-copy mapping completeness (DRIFT GUARD) + classification.
//
// Asserts EVERY coverage-gap `reason` the data layer can emit maps to non-default copy, so a
// newly-added emitter without copy is caught here rather than silently rendering the neutral
// "data unavailable" fallback in production.
//
// The list below is MIRRORED from the data layer. It was enumerated by grepping
//   `coverage_gap(`  +  inline `{"coverage_gap": True, "reason": …}`
// across src/wcmodel/ at main e60ebce. If you add/rename a reason in the data layer, update
// this list (and src/lib/coverageCopy.ts). The two static-reason sets are also cross-checked
// against each other so neither drifts unnoticed.

import { describe, expect, test } from 'vitest';
import { coverageCopy, STATIC_REASONS } from '../../src/lib/coverageCopy';

// ── STATIC (non-parameterized) reasons emitted by the data + UI layers ──────────────────
//   reason string                                  source (file:line)
const DATA_LAYER_STATIC: ReadonlyArray<readonly [string, string]> = [
  ['no played history as-of cutoff',                'src/wcmodel/dashboard/build.py:290,295,305'],
  ['xg not StatsBomb-covered for this fixture',     'src/wcmodel/dashboard/why.py:37'],
  ['xg missing',                                    'src/wcmodel/dashboard/why.py:39'],
  ['rest_days unknown for an unplayed fixture',     'src/wcmodel/dashboard/build.py:352,359'],
  ['rest_days null as-of cutoff',                   'src/wcmodel/dashboard/build.py:361'],
  ['no live edge for this fixture as-of cutoff',    'src/wcmodel/dashboard/build.py:582'],
  ['no live edge for this fixture',                 'src/wcmodel/dashboard/build.py:608'],
  ['no forecast for this fixture',                  'src/wcmodel/dashboard/build.py:606'],
  ['no backtest records supplied',                  'src/wcmodel/dashboard/build.py:638'],
  // UI-introduced literals that flow through the SAME `reason` prop:
  ['scoreline grid unavailable',                    'dashboard-ui/src/components/ScorelineGrid.svelte:58'],
  ['no probable occupants',                         'dashboard-ui/src/components/BracketTree.svelte:75'],
];

// ── PARAMETERIZED reasons (data-layer f-strings) — concrete sample per template ─────────
//   sample reason                                          source (file:line)
const DATA_LAYER_PARAMETERIZED: ReadonlyArray<readonly [string, string]> = [
  ['feeder W74 resolves from a later match',                'src/wcmodel/dashboard/build.py:415'],
  ['no sharp (pinnacle) line',                              'src/wcmodel/value/scanner.py:103'],
  ['slot 1: occupant Brazil has no se companion',          'src/wcmodel/dashboard/tournament_view.py:63'],
];

describe('coverage-copy DRIFT GUARD — every emitted reason has a mapping', () => {
  test.each(DATA_LAYER_STATIC)('static reason "%s" (%s) maps to non-default copy', (reason) => {
    const copy = coverageCopy(reason);
    // Non-default: not the neutral fallback, and never an empty string.
    expect(copy.kind).not.toBe('unknown');
    expect(copy.text.trim().length).toBeGreaterThan(0);
    expect(copy.text).not.toBe('data unavailable');
  });

  test.each(DATA_LAYER_PARAMETERIZED)('parameterized reason "%s" (%s) maps to non-default copy', (reason) => {
    const copy = coverageCopy(reason);
    expect(copy.kind).not.toBe('unknown');
    expect(copy.text.trim().length).toBeGreaterThan(0);
    expect(copy.text).not.toBe('data unavailable');
  });

  test('the module STATIC_REASONS exactly covers the mirrored data-layer static list (no drift either way)', () => {
    const mirrored = new Set(DATA_LAYER_STATIC.map(([r]) => r));
    const inModule = new Set(STATIC_REASONS);
    // Every mirrored reason is in the module map…
    for (const r of mirrored) expect(inModule.has(r), `module missing copy for "${r}"`).toBe(true);
    // …and the module map has no static reason the data layer doesn't emit (stale entry).
    for (const r of inModule) expect(mirrored.has(r), `module has stale reason "${r}"`).toBe(true);
  });
});

describe('coverage-copy classification — the right kind + word discipline', () => {
  test('"insufficient" is used by EXACTLY the history reason, no other', () => {
    for (const [reason] of [...DATA_LAYER_STATIC, ...DATA_LAYER_PARAMETERIZED]) {
      const copy = coverageCopy(reason);
      if (reason === 'no played history as-of cutoff') {
        expect(copy.kind).toBe('insufficient');
        expect(copy.text).toMatch(/insufficient/i);
      } else {
        expect(copy.kind).not.toBe('insufficient');
        expect(copy.text).not.toMatch(/insufficient/i);
      }
    }
  });

  test('time-resolving copy says WHEN (mentions filling/pending), structural says WHY', () => {
    const timeResolving = [
      'rest_days unknown for an unplayed fixture',
      'rest_days null as-of cutoff',
      'no backtest records supplied',
      'feeder W74 resolves from a later match',
    ];
    for (const r of timeResolving) {
      const copy = coverageCopy(r);
      expect(copy.kind, r).toBe('time-resolving');
      expect(copy.text, r).toMatch(/pending|fills/i);
    }
    const structural = [
      'xg not StatsBomb-covered for this fixture',
      'xg missing',
      'no live edge for this fixture',
      'no sharp (pinnacle) line',
      'slot 1: occupant Brazil has no se companion',
    ];
    for (const r of structural) {
      expect(coverageCopy(r).kind, r).toBe('structural');
    }
  });

  test('the sharp-line copy preserves the book name from the reason string', () => {
    expect(coverageCopy('no sharp (pinnacle) line').text).toMatch(/pinnacle/);
    expect(coverageCopy('no sharp (betfair) line').text).toMatch(/betfair/);
  });

  test('null / undefined / empty reason -> neutral fallback (never crashes)', () => {
    for (const r of [null, undefined, '']) {
      const copy = coverageCopy(r);
      expect(copy.kind).toBe('unknown');
      expect(copy.text).toBe('data unavailable');
    }
  });
});
