<script lang="ts">
  import type { StandingsData, Fate } from '../lib/types';
  import Estimate from '../components/Estimate.svelte';
  import NumEstimate from '../components/NumEstimate.svelte';

  // The predicted group standings (Item A). Per group, per team: E[Pts], E[GD], P(top 2),
  // P(qualify as 3rd), P(eliminated). Rows arrive PRE-SORTED by P(advance) desc from the
  // builder. Each row is COLOURED by its most-likely fate — a summary hint; the always-
  // visible probabilities are the claim (no-naked-numbers: each carries its SE companion).
  let { data }: { data: StandingsData } = $props();

  // Stable group order (A, B, C …) regardless of the wire dict's key order.
  const groups = $derived(Object.keys(data).sort());

  // A readable label for the most-likely fate (the colour legend).
  const FATE_LABEL: Record<Fate, string> = {
    advance: 'Advancing',
    possible_third: 'Possible 3rd',
    eliminated: 'Eliminated',
  };
</script>

<div class="standings">
  {#each groups as g (g)}
    <section class="group" data-group={g}>
      <h3 class="group-title">Group {g}</h3>
      <table class="tbl">
        <thead>
          <tr>
            <th class="team-h">Team</th>
            <th>E[Pts]</th>
            <th>E[GD]</th>
            <th>P(top 2)</th>
            <th>P(3rd qual.)</th>
            <th>P(elim.)</th>
          </tr>
        </thead>
        <tbody>
          {#each data[g] as r (r.team)}
            <!-- fate is a COLOUR summary; the cells below carry the always-visible numbers. -->
            <tr data-team={r.team} data-fate={r.fate ?? 'unknown'}>
              <td class="team">
                {r.team}
                {#if r.fate}<span class="fate-tag" data-fate-tag={r.fate}>{FATE_LABEL[r.fate]}</span>{/if}
              </td>
              <td><NumEstimate value={r.exp_points.value} se={r.exp_points.se} label={`${r.team}-epts`} dp={1} /></td>
              <td><NumEstimate value={r.exp_gd.value} se={r.exp_gd.se} label={`${r.team}-egd`} dp={1} signedValue /></td>
              <td><Estimate value={r.p_top2.value} se={r.p_top2.se} label={`${r.team}-top2`} /></td>
              <td><Estimate value={r.p_third_qualify.value} se={r.p_third_qualify.se} label={`${r.team}-q3`} /></td>
              <td><Estimate value={r.p_eliminated.value} se={r.p_eliminated.se} label={`${r.team}-elim`} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/each}
</div>
<p class="muted note">
  Rows sorted by P(advance) = P(top 2) + P(qualify as 3rd). Row colour = most-likely fate; the
  probabilities (each ± its Monte-Carlo SE) are the claim. P(top 2) + P(3rd qual.) + P(elim.) = 1.
</p>

<style>
  .standings { display: grid; gap: var(--space-5); }
  .group-title { font-size: var(--fs-md, 1rem); font-weight: 600; margin: 0 0 var(--space-2); }
  .tbl { width: 100%; border-collapse: collapse; }
  .tbl th {
    text-align: right; padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--line);
    color: var(--muted); font-weight: 600; font-size: var(--fs-sm);
  }
  .tbl td {
    text-align: right; padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid color-mix(in srgb, var(--line) 60%, transparent);
  }
  .team-h, .team { text-align: left; font-weight: 600; }
  .team { display: flex; align-items: center; gap: var(--space-2); }
  /* Fate colouring — a LEFT-EDGE accent + a soft tint, never overriding the cell text. The
     numbers stay fully legible; the colour is a summary hint. */
  tr[data-fate='advance'] { box-shadow: inset 3px 0 0 var(--good); background: color-mix(in srgb, var(--good) 7%, transparent); }
  tr[data-fate='possible_third'] { box-shadow: inset 3px 0 0 var(--warn); background: color-mix(in srgb, var(--warn) 7%, transparent); }
  tr[data-fate='eliminated'] { box-shadow: inset 3px 0 0 var(--muted); opacity: 0.7; }
  .fate-tag {
    font-size: 0.68em; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
    border-radius: 999px; padding: 1px 8px; border: 1px solid transparent;
  }
  .fate-tag[data-fate-tag='advance'] { color: var(--good); border-color: color-mix(in srgb, var(--good) 35%, transparent); background: color-mix(in srgb, var(--good) 12%, transparent); }
  .fate-tag[data-fate-tag='possible_third'] { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 35%, transparent); background: color-mix(in srgb, var(--warn) 12%, transparent); }
  .fate-tag[data-fate-tag='eliminated'] { color: var(--muted); border-color: color-mix(in srgb, var(--muted) 35%, transparent); }
  .note { margin-top: var(--space-4); font-size: var(--fs-sm); }
</style>
