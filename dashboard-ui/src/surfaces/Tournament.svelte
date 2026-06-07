<script lang="ts">
  import type { TournamentData } from '../lib/types';
  import Estimate from '../components/Estimate.svelte';

  let { data, markets }: { data: TournamentData; markets: string[] } = $props();
  // The coherence ladder, ordered shallow → deep so the monotone chain reads
  // left → right: advance ≥ reach-r16 ≥ qf ≥ sf ≥ final ≥ champion.
  const LADDER = ['win_group', 'advance_from_group', 'reach_r16', 'reach_qf', 'reach_sf', 'reach_final', 'champion'];
  const cols = $derived(LADDER.filter((m) => markets.includes(m)));
  const teams = $derived(
    Object.keys(data).sort((a, b) => (data[b].champion?.value ?? 0) - (data[a].champion?.value ?? 0)),
  );
</script>

<table class="prog">
  <thead><tr><th>Team</th>{#each cols as c}<th>{c.replace(/_/g, ' ')}</th>{/each}</tr></thead>
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
  .prog th, .prog td { text-align: right; padding: 6px 10px; border-bottom: 1px solid var(--line); }
  .prog th:first-child, .team { text-align: left; font-weight: 600; }
  .note { margin-top: 10px; font-size: 0.85em; }
</style>
