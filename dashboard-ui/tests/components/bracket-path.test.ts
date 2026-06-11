// Item B — bracket MODAL-PATH bolding (chain-consistent argmax).
//
// SPEC (binding): bold the argmax advancing team at each node, with CHAIN CONSISTENCY —
// the bolded team at round n must be the bolded WINNER of round n−1. A naive per-slot argmax
// can violate the chain (the slot's top occupant at round n need not be fed by round n−1's
// bolded winner). We implement a FORWARD PASS over team identity (the occupant `team` name is
// the stable cross-round identity; the `W{n}` feeder ref tells us WHICH match feeds the slot):
//
//   • Entry round (shallowest present): bold each slot's top occupant (per-slot argmax).
//   • Later node: the two feeding bolded entries are match n−1's bolded winners. Among THIS
//     slot's occupants that match a feeding bolded team (by name), bold the highest-prob one.
//   • If NEITHER feeding bolded team appears in this slot's listed (truncated top-few)
//     occupants, bold NOTHING at that node and BREAK the chain visibly — no fake continuation.
//
// The bolded occupant carries data-modal="1" (and the slot bolds its team via .modal-team).
// A single verbatim caption is present. No joint path probability is readable from the bundle
// (occupant lists are MARGINALS), so the caption omits the number — never a multiplied fake.

import { render } from '@testing-library/svelte';
import BracketTree from '../../src/components/BracketTree.svelte';
import type { KoRow } from '../../src/lib/types';

const occ = (team: string, prob: number, se = 0.003) => ({ team, prob, se });

// VERBATIM caption (the user spec pins this string exactly).
const CAPTION =
  'bold = most likely team at each step; the joint probability of this exact path is far lower.';

// Helper: the set of bolded team names within a given round column.
function boldedTeamsInRound(container: HTMLElement, round: string): string[] {
  const col = container.querySelector(`[data-round="${round}"]`);
  if (!col) return [];
  return Array.from(col.querySelectorAll('[data-modal="1"] .team')).map(
    (n) => (n.textContent ?? '').trim(),
  );
}

// Helper: bolded team in a specific match's specific side, or null if none bolded there.
function boldedInSlot(container: HTMLElement, match: number, side: 'home' | 'away'): string | null {
  const matchEl = container.querySelector(`[data-match="${match}"]`);
  if (!matchEl) return null;
  const slot = matchEl.querySelector(`[data-bracket-slot="${side}"]`);
  if (!slot) return null;
  const bold = slot.querySelector('[data-modal="1"] .team');
  return bold ? (bold.textContent ?? '').trim() : null;
}

describe('Item B — modal-path bolding (chain consistency)', () => {
  // A CLEAN chain: R32 winners feed R16 which feeds the QF, and the bolded team at each
  // deeper node IS one of the two feeding bolded winners. The forward pass must bold the
  // consistent occupant (NOT a naive per-slot argmax that would violate the chain).
  //
  // R32: m73 home top = Argentina(.51); m74 home top = Spain(.60).
  // R16: m89 fed by W73 (Argentina) + W74 (Spain). Naive argmax of m89 home would pick
  //      Brazil(.55) — but Brazil is NOT a feeding bolded winner. Chain-consistent pick is
  //      Argentina(.40) (the only feeding bolded team present) → proves we don't take .55.
  const cleanChain: KoRow[] = [
    // m73 home (Argentina .51) is the match's modal winner — higher than away top (Japan .45).
    { match: 73, stage: 'R32', status: 'upcoming', home_ref: '1A', away_ref: '2B',
      home_occupants: [occ('Argentina', 0.51), occ('Mexico', 0.30), occ('Malta', 0.19)],
      away_occupants: [occ('Japan', 0.45), occ('Croatia', 0.40)] },
    // m74 home (Spain .60) is the match's modal winner — higher than away top (Germany .52).
    { match: 74, stage: 'R32', status: 'upcoming', home_ref: '1C', away_ref: '2D',
      home_occupants: [occ('Spain', 0.60), occ('Portugal', 0.40)],
      away_occupants: [occ('Germany', 0.52), occ('Italy', 0.48)] },
    // R16 m89: home slot fed by W73 (→ Argentina), away slot fed by W74 (→ Spain). The home
    // slot's naive top is Brazil(.55) — a chain VIOLATOR (Brazil is not the W73 winner) — so
    // the forward pass must instead bold the W73 winner present in the list: Argentina(.40).
    { match: 89, stage: 'R16', status: 'upcoming', home_ref: 'W73', away_ref: 'W74',
      home_occupants: [occ('Brazil', 0.55), occ('Argentina', 0.40)],
      away_occupants: [occ('Germany', 0.60), occ('Spain', 0.40)] },
  ];

  test('entry round (R32) bolds each slot top occupant (per-slot argmax)', () => {
    const { container } = render(BracketTree, { knockout: cleanChain });
    expect(boldedInSlot(container, 73, 'home')).toBe('Argentina');
    expect(boldedInSlot(container, 73, 'away')).toBe('Japan');
    expect(boldedInSlot(container, 74, 'home')).toBe('Spain');
    expect(boldedInSlot(container, 74, 'away')).toBe('Germany');
  });

  test('deeper node bolds the chain-consistent occupant, NOT the naive per-slot argmax', () => {
    const { container } = render(BracketTree, { knockout: cleanChain });
    // m89 home: naive argmax = Brazil(.55), but Brazil is NOT the W73 bolded winner.
    // The feeding bolded winner of the home slot is Argentina (W73), so the forward pass
    // bolds Argentina(.40) — never Brazil(.55), which would violate the chain.
    expect(boldedInSlot(container, 89, 'home')).toBe('Argentina');
    expect(boldedInSlot(container, 89, 'home')).not.toBe('Brazil');
  });

  test('every bolded deeper team is a feeding bolded winner (chain consistency invariant)', () => {
    const { container } = render(BracketTree, { knockout: cleanChain });
    const r32Bold = new Set([
      ...boldedTeamsInRound(container, 'R32'),
    ]);
    // Every team bolded at R16 must have been bolded at R32 (fed by a bolded winner).
    for (const t of boldedTeamsInRound(container, 'R16')) {
      expect(r32Bold.has(t), `R16 bolded "${t}" was not a bolded R32 winner`).toBe(true);
    }
  });

  test('exactly one occupant is bolded per resolvable slot (argmax, not multi-bold)', () => {
    const { container } = render(BracketTree, { knockout: cleanChain });
    // Each occupant list that renders should bold at most one team.
    container.querySelectorAll('[data-bracket-slot]').forEach((slot) => {
      const bolds = slot.querySelectorAll('[data-modal="1"]');
      expect(bolds.length).toBeLessThanOrEqual(1);
    });
  });

  // DELIBERATE VIOLATION case: a deeper slot whose occupant list (truncated top-few) does NOT
  // contain EITHER feeding bolded winner. The forward pass must BREAK the chain visibly: bold
  // NOTHING at that node (no fake continuation), and the slot is flagged data-chain-break.
  const brokenChain: KoRow[] = [
    { match: 73, stage: 'R32', status: 'upcoming', home_ref: '1A', away_ref: '2B',
      home_occupants: [occ('Argentina', 0.51), occ('Mexico', 0.30)],
      away_occupants: [occ('Croatia', 0.55), occ('Japan', 0.45)] },
    { match: 74, stage: 'R32', status: 'upcoming', home_ref: '1C', away_ref: '2D',
      home_occupants: [occ('Spain', 0.60), occ('Portugal', 0.40)],
      away_occupants: [occ('Germany', 0.52), occ('Italy', 0.48)] },
    // m89 fed by W73 (Argentina) + W74 (Spain) — but NEITHER appears in the home occupant
    // top-few (only Brazil/France listed). The chain BREAKS: bold nothing in m89 home.
    { match: 89, stage: 'R16', status: 'upcoming', home_ref: 'W73', away_ref: 'W74',
      home_occupants: [occ('Brazil', 0.70), occ('France', 0.30)],
      away_occupants: [occ('Spain', 0.50), occ('Argentina', 0.50)] },
  ];

  test('chain break: a node with NO feeding bolded winner present bolds nothing (no fake continuation)', () => {
    const { container } = render(BracketTree, { knockout: brokenChain });
    // m89 home lists only Brazil/France; neither is a feeding bolded winner → no bold.
    expect(boldedInSlot(container, 89, 'home')).toBeNull();
    // And it must NOT silently bold the naive top (Brazil) — that would be a fake continuation.
    const matchEl = container.querySelector('[data-match="89"]')!;
    const homeSlot = matchEl.querySelector('[data-bracket-slot="home"]')!;
    expect(homeSlot.textContent).toContain('Brazil');
    expect(homeSlot.querySelector('[data-modal="1"]')).toBeNull();
  });

  test('chain break is flagged visibly (data-chain-break) so the reader sees the discontinuity', () => {
    const { container } = render(BracketTree, { knockout: brokenChain });
    const matchEl = container.querySelector('[data-match="89"]')!;
    const homeSlot = matchEl.querySelector('[data-bracket-slot="home"]')!;
    expect(homeSlot.matches('[data-chain-break]')).toBe(true);
  });

  test('a gapped slot is not bolded and does not break a chain spuriously', () => {
    const gapped: KoRow[] = [
      { match: 73, stage: 'R32', status: 'upcoming', home_ref: '1A', away_ref: '2B',
        home_occupants: [occ('Argentina', 0.51), occ('Mexico', 0.30)],
        away_occupants: { coverage_gap: true, reason: 'x' } },
    ];
    const { container } = render(BracketTree, { knockout: gapped });
    // The home slot bolds its top; the gapped away slot has no bold and no chain-break flag.
    expect(boldedInSlot(container, 73, 'home')).toBe('Argentina');
    const awaySlot = container.querySelector('[data-match="73"] [data-bracket-slot="away"]')!;
    expect(awaySlot.querySelector('[data-modal="1"]')).toBeNull();
    expect(awaySlot.matches('[data-chain-break]')).toBe(false);
  });

  // ── CAPTION (verbatim, present) ──────────────────────────────────────────────────
  test('the verbatim modal-path caption is present', () => {
    const { container } = render(BracketTree, { knockout: cleanChain });
    const cap = container.querySelector('[data-modal-caption]');
    expect(cap).not.toBeNull();
    expect((cap!.textContent ?? '').trim()).toBe(CAPTION);
  });

  test('the caption carries NO numeric joint (occupant lists are marginals; no real joint exists)', () => {
    const { container } = render(BracketTree, { knockout: cleanChain });
    const cap = container.querySelector('[data-modal-caption]')!;
    // No digit at all in the caption — we never multiply marginals into a fake joint.
    expect(/\d/.test(cap.textContent ?? '')).toBe(false);
  });

  test('the entry round picks the global top even when listed out of order', () => {
    const unordered: KoRow[] = [
      { match: 73, stage: 'R32', status: 'upcoming', home_ref: '1A', away_ref: '2B',
        // NOT sorted: the top prob (Mexico .60) is second in the list.
        home_occupants: [occ('Argentina', 0.25), occ('Mexico', 0.60), occ('Malta', 0.15)],
        away_occupants: { coverage_gap: true, reason: 'x' } },
    ];
    const { container } = render(BracketTree, { knockout: unordered });
    expect(boldedInSlot(container, 73, 'home')).toBe('Mexico');
  });
});
