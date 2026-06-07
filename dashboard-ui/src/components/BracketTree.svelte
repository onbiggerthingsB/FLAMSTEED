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
                  <div class="slot" data-bracket-slot={side}>
                    <span class="ref muted" title={`feeder ${ref}`}>{ref}</span>
                    {#if isGap(occ)}
                      <CoverageGap reason={occ.reason} />
                    {:else if occ.length === 0}
                      <CoverageGap reason="no probable occupants" />
                    {:else}
                      <ul class="occs">
                        {#each topFew(occ) as o (o.team)}
                          <li class="occ">
                            <span class="team">{o.team}</span>
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
  .note { margin-top: var(--space-4); font-size: var(--fs-sm); }
  .empty { padding: var(--space-4) 0; }
</style>
