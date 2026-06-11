<script lang="ts">
  // Bracket-tree view (spec §3 "bracket tree" progressive item): a R32 → R16 → QF → SF
  // → Final column layout. Each match is a slot pair (home / away); each slot shows its
  // PROBABLE OCCUPANTS (top few, each `team prob±se` via Estimate) or a CoverageGap.
  //
  // The occupants are ALREADY computed in the bundle (schedule.json's knockout rows):
  //   • a group-position / best-third feeder (1A / 2B / 3rd-…) carries a concrete
  //     occupant list (the group's placers) — we render the top few as Estimates.
  //   • a winner/loser feeder (W74 / L101) resolves only from a DEEPER match, so the
  //     bundle emits a {coverage_gap} — we render a CoverageGap (never a fabricated %).
  //
  // No naked numbers: every occupant prob renders via <Estimate> (data-uncertainty) and a
  // gapped occupant-list renders <CoverageGap>. The load-bearing guard
  // (tests/no-naked-number.test.ts) covers this component.
  import type { KoRow, Occupant } from '../lib/types';
  import { isGap } from '../lib/guards';
  import Estimate from './Estimate.svelte';
  import CoverageGap from './CoverageGap.svelte';

  let { knockout, occupantCap = 4 }: { knockout: KoRow[]; occupantCap?: number } = $props();

  // The canonical knockout ladder, shallow → deep (mirrors sim/bracket.py's `_ROUND` codes).
  // The 3rd-place consolation sits OFF the championship winner-DAG, so it trails the Final.
  const ROUND_ORDER = ['R32', 'R16', 'QF', 'SF', 'Final', '3rd-place'];
  const rank = (stage: string | null) => {
    const i = ROUND_ORDER.indexOf(stage ?? '');
    return i === -1 ? ROUND_ORDER.length : i; // an unknown/null stage trails known rounds
  };
  // Human label per round code (the codes are an internal contract, not a reader-facing label).
  const ROUND_LABEL: Record<string, string> = {
    R32: 'Round of 32', R16: 'Round of 16', QF: 'Quarter-finals',
    SF: 'Semi-finals', Final: 'Final', '3rd-place': 'Third place',
  };
  const labelOf = (stage: string | null) => (stage && ROUND_LABEL[stage]) || stage || 'TBD round';

  // Group the KO rows into ordered columns, one per round PRESENT in the data. Stable: rows
  // within a round keep ascending match order so the tree reads top→bottom consistently.
  type Column = { code: string; label: string; rows: KoRow[] };
  const columns = $derived.by<Column[]>(() => {
    const byRound = new Map<string, KoRow[]>();
    for (const r of knockout) {
      const code = r.stage ?? '__tbd__';
      (byRound.get(code) ?? byRound.set(code, []).get(code)!).push(r);
    }
    return [...byRound.entries()]
      .map(([code, rows]) => ({
        code,
        label: labelOf(rows[0].stage),
        rows: [...rows].sort((a, b) => a.match - b.match),
      }))
      .sort((a, b) => rank(a.code === '__tbd__' ? null : a.code) - rank(b.code === '__tbd__' ? null : b.code));
  });

  // The top-few occupants for a slot, capped — the spec's "probable occupants (top few)".
  const topFew = (occ: Occupant[]) => occ.slice(0, occupantCap);

  // ── MODAL-PATH bolding (Item B): chain-consistent argmax over the bracket ─────────
  // Bold the argmax advancing team at each node, with CHAIN CONSISTENCY — the bolded team at
  // round n must be the bolded WINNER of round n−1. The occupant lists are per-slot MARGINALS
  // (group placers / best-thirds), so a naive per-slot argmax can violate the chain (a slot's
  // top occupant need not be fed by the bolded winner of the feeding match). We run a FORWARD
  // PASS over TEAM IDENTITY — the occupant `team` name is the stable cross-round identity; the
  // `W{n}` feeder ref tells us WHICH match feeds the slot:
  //
  //   • Entry round (no resolvable feeders): bold each slot's top occupant (per-slot argmax).
  //   • Later node: the two feeding bolded entries are match n−1's bolded winners. Among THIS
  //     slot's listed occupants that match a feeding bolded team (by name), bold the highest-
  //     prob one.
  //   • If NEITHER feeding bolded team appears in this slot's (truncated top-few) occupants,
  //     bold NOTHING and BREAK the chain visibly (data-chain-break) — no fake continuation.
  //
  // A slot "winner" (used to feed deeper nodes) is the bolded occupant of whichever side of the
  // match has the higher bolded prob — i.e. the modal team to advance OUT of that match.
  //
  // NOTE — joint vs marginal (binding honesty constraint): no joint path probability is
  // readable from the bundle (the occupants are marginals; the serializer emits no modal-path
  // joint). We therefore NEVER multiply marginals into a fake joint — the caption omits the
  // number and honestly states the joint is "far lower".

  // Resolve a feeder ref (e.g. "W73") to the match number it advances from, or null.
  const feederMatch = (ref: string): number | null => {
    const m = /^W(\d+)$/.exec(ref ?? '');
    return m ? Number(m[1]) : null;
  };
  // The top occupant among a list restricted to an allowed set of team names (forward pass),
  // or the unrestricted top if `allowed` is null (entry round). Returns the team name or null.
  const argmaxOccupant = (occ: Occupant[], allowed: Set<string> | null): string | null => {
    let best: Occupant | null = null;
    for (const o of topFew(occ)) {
      if (allowed && !allowed.has(o.team)) continue;
      if (!best || o.prob > best.prob) best = o;
    }
    return best ? best.team : null;
  };

  type SlotModal = { bolded: string | null; chainBreak: boolean };
  type MatchModal = { home: SlotModal; away: SlotModal; winner: string | null };

  // Forward pass: process matches in round order (shallow → deep) so a deeper node always sees
  // its feeders' results. Keyed by match number; each entry holds per-side bold + the match's
  // advancing (modal) winner that feeds the next round.
  const modal = $derived.by<Map<number, MatchModal>>(() => {
    const out = new Map<number, MatchModal>();
    // The match's advancing winner = the bolded team on the side with the higher bolded prob.
    const slotProb = (occ: Occupant[] | null, team: string | null): number => {
      if (!occ || !team) return -1;
      const hit = topFew(occ).find((o) => o.team === team);
      return hit ? hit.prob : -1;
    };
    for (const col of columns) {
      for (const k of col.rows) {
        const sides = [
          ['home', k.home_ref, k.home_occupants] as const,
          ['away', k.away_ref, k.away_occupants] as const,
        ];
        const slot: Record<'home' | 'away', SlotModal> = {
          home: { bolded: null, chainBreak: false },
          away: { bolded: null, chainBreak: false },
        };
        for (const [side, ref, occ] of sides) {
          if (isGap(occ) || occ.length === 0) continue; // gapped slot: no bold, no break
          const fm = feederMatch(ref);
          if (fm === null) {
            // Entry-round slot (group-placer / best-third feeder): unrestricted argmax.
            slot[side] = { bolded: argmaxOccupant(occ, null), chainBreak: false };
          } else {
            // Deeper node: restrict to the feeding match's bolded WINNER (chain consistency).
            const feeder = out.get(fm);
            const allowed = new Set<string>();
            if (feeder?.winner) allowed.add(feeder.winner);
            const bolded = argmaxOccupant(occ, allowed);
            // BREAK the chain visibly if the feeding bolded winner isn't in this top-few list.
            slot[side] = { bolded, chainBreak: bolded === null };
          }
        }
        const hp = slotProb(isGap(k.home_occupants) ? null : k.home_occupants, slot.home.bolded);
        const ap = slotProb(isGap(k.away_occupants) ? null : k.away_occupants, slot.away.bolded);
        const winner = hp < 0 && ap < 0 ? null : hp >= ap ? slot.home.bolded : slot.away.bolded;
        out.set(k.match, { home: slot.home, away: slot.away, winner });
      }
    }
    return out;
  });

  const slotModal = (match: number, side: 'home' | 'away'): SlotModal =>
    modal.get(match)?.[side] ?? { bolded: null, chainBreak: false };
</script>

<section class="bracket" aria-label="Knockout bracket tree">
  {#if columns.length === 0}
    <p class="muted empty">No knockout fixtures in this snapshot yet.</p>
  {:else}
    <div class="cols" role="list">
      {#each columns as col (col.code)}
        <div class="col" data-round={col.code === '__tbd__' ? '' : col.code} role="listitem">
          <h3 class="round">{col.label}</h3>
          <div class="slots">
            {#each col.rows as k (k.match)}
              <div class="match card" data-bracket-match data-match={k.match}>
                {#each [['home', k.home_ref, k.home_occupants] as const, ['away', k.away_ref, k.away_occupants] as const] as [side, ref, occ]}
                  {@const sm = slotModal(k.match, side)}
                  <div
                    class="slot"
                    data-bracket-slot={side}
                    data-chain-break={sm.chainBreak ? '' : undefined}
                  >
                    <span class="ref muted" title={`feeder ${ref}`}>{ref}</span>
                    {#if isGap(occ)}
                      <CoverageGap reason={occ.reason} />
                    {:else if occ.length === 0}
                      <CoverageGap reason="no probable occupants" />
                    {:else}
                      <ul class="occs">
                        {#each topFew(occ) as o (o.team)}
                          {@const isModal = o.team === sm.bolded}
                          <li class="occ" class:modal={isModal} data-modal={isModal ? '1' : undefined}>
                            <span class="team" class:modal-team={isModal}>{o.team}</span>
                            <Estimate value={o.prob} se={o.se} label={`m${k.match}-${side}-${o.team}`} />
                          </li>
                        {/each}
                      </ul>
                    {/if}
                  </div>
                {/each}
              </div>
            {/each}
          </div>
        </div>
      {/each}
    </div>
  {/if}
  <p class="muted note">
    Each slot shows its probable occupants — group placers (1A/2B/3rd-…) with their
    Monte-Carlo probability ± SE, or a coverage gap for a winner/loser feeder (W74/L101)
    that only resolves from a deeper match. No occupant is fabricated.
  </p>
  <!-- MODAL-PATH caption (Item B). VERBATIM per spec; carries NO number because the occupant
       lists are MARGINALS and the bundle exposes no joint path probability — multiplying
       marginals would be a false joint, so we state it honestly in words only. -->
  <p class="muted caption" data-modal-caption>
    bold = most likely team at each step; the joint probability of this exact path is far lower.
  </p>
</section>

<style>
  .bracket { width: 100%; }
  .cols {
    display: flex; gap: var(--space-5); align-items: flex-start;
    overflow-x: auto; padding-bottom: var(--space-3);
  }
  .col { display: flex; flex-direction: column; gap: var(--space-3); min-width: 200px; flex: 0 0 auto; }
  .round {
    margin: 0 0 var(--space-1); font-size: var(--fs-sm); font-weight: 600;
    color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em;
  }
  .slots { display: flex; flex-direction: column; gap: var(--space-4); justify-content: space-around; flex: 1; }
  .match { padding: var(--space-3); display: grid; gap: var(--space-2); }
  .slot { display: flex; flex-direction: column; gap: 2px; }
  .slot + .slot { border-top: 1px dashed color-mix(in srgb, var(--line) 70%, transparent); padding-top: var(--space-2); }
  .ref { font-size: 0.72em; font-weight: 600; letter-spacing: 0.03em; }
  .occs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 1px; }
  .occ { display: flex; align-items: baseline; gap: var(--space-2); justify-content: space-between; font-size: 0.9em; }
  .team { font-weight: 500; }
  /* MODAL-PATH bolding (Item B): the chain-consistent argmax team at each node reads bold. */
  .occ.modal { font-weight: 700; }
  .team.modal-team { font-weight: 700; }
  /* A chain BREAK (no feeding bolded winner present in this slot's top-few) is shown honestly:
     a dotted left rule marks the discontinuity so the reader sees the path did not continue. */
  .slot[data-chain-break] { border-left: 2px dotted color-mix(in srgb, var(--muted) 60%, transparent); padding-left: var(--space-2); }
  .note { margin-top: var(--space-4); font-size: var(--fs-sm); }
  .caption { margin-top: var(--space-2); font-size: var(--fs-sm); font-style: italic; }
  .empty { padding: var(--space-4) 0; }
</style>
