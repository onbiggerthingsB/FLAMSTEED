<script lang="ts">
  import type { TournamentData } from '../lib/types';
  import Estimate from '../components/Estimate.svelte';

  let { data, markets }: { data: TournamentData; markets: string[] } = $props();
  // The coherence ladder, ordered shallow → deep so the monotone chain reads
  // left → right: advance ≥ reach-r16 ≥ qf ≥ sf ≥ final ≥ champion.
  const LADDER = ['win_group', 'advance_from_group', 'reach_r16', 'reach_qf', 'reach_sf', 'reach_final', 'champion'];
  // Readable column headers — the raw market keys are an internal contract, not a label
  // a reader should have to decode ("reach_qf" → "QF"). Unknown markets fall back to a
  // de-underscored, capitalised form so a future market never renders raw snake_case.
  const LABELS: Record<string, string> = {
    win_group: 'Win group',
    advance_from_group: 'Advance',
    reach_r16: 'R16',
    reach_qf: 'QF',
    reach_sf: 'SF',
    reach_final: 'Final',
    champion: 'Champion',
    first: 'First',
    second: 'Second',
    third: 'Third',
    out: 'Out',
  };
  const labelOf = (m: string) =>
    LABELS[m] ?? m.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
  const cols = $derived(LADDER.filter((m) => markets.includes(m)));
  const teams = $derived(
    Object.keys(data).sort((a, b) => (data[b].champion?.value ?? 0) - (data[a].champion?.value ?? 0)),
  );
</script>

<table class="prog">
  <thead><tr><th>Team</th>{#each cols as c}<th>{labelOf(c)}</th>{/each}</tr></thead>
  <tbody>
    {#each teams as t (t)}
      <tr data-team={t}>
        <td class="team">{t}</td>
        {#each cols as c}
          <td><Estimate value={data[t][c]?.value ?? null} se={data[t][c]?.se ?? null} label={`${t}-${c}`} /></td>
        {/each}
      </tr>
    {/each}
  </tbody>
</table>
<p class="muted note">Coherence chain preserved: advance ≥ reach-r16 ≥ … ≥ champion. Each cell is a Monte-Carlo estimate ± its SE.</p>

<style>
  .prog { width: 100%; border-collapse: collapse; }
  .prog th { text-align: right; padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--line); color: var(--muted); font-weight: 600; font-size: var(--fs-sm); }
  .prog td { text-align: right; padding: var(--space-2) var(--space-3); border-bottom: 1px solid color-mix(in srgb, var(--line) 60%, transparent); }
  .prog tbody tr { transition: background 0.1s ease; }
  .prog tbody tr:hover { background: var(--accent-soft); }
  .prog th:first-child, .team { text-align: left; font-weight: 600; }
  .note { margin-top: var(--space-3); font-size: var(--fs-sm); }
</style>
