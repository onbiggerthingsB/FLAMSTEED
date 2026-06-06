<script lang="ts">
  import type { ScheduleData, GroupRow } from '../lib/types';
  import { isGap } from '../lib/guards';
  import { formatDate } from '../lib/format';
  import Estimate from '../components/Estimate.svelte';
  import EdgeChip from '../components/EdgeChip.svelte';
  import CoverageGap from '../components/CoverageGap.svelte';
  import WinBar from '../components/WinBar.svelte';

  let { data }: { data: ScheduleData } = $props();
  const STAGES = ['group', 'knockout'] as const;
  let stage = $state<'group' | 'knockout'>('group');

  // The most-likely score is a label; its probability is the estimate. Keep the
  // two separate so the score text never poses as a bare probability.
  function scoreText(r: GroupRow): string {
    if (isGap(r.forecast_summary)) return '';
    const m = r.forecast_summary.most_likely;
    return `${m.home_goals}–${m.away_goals}`;
  }
</script>

<div class="nav">
  {#each STAGES as s}
    <button class:active={stage === s} onclick={() => (stage = s)}>{s}</button>
  {/each}
</div>

{#if stage === 'group'}
  <ul class="rows">
    {#each data.group as r (r.match_id)}
      <li class="card row" data-row="group" data-status={r.status}>
        <span class="teams">{r.home} <span class="muted">v</span> {r.away}</span>
        <span class="date muted">{formatDate(r.date)}</span>
        {#if isGap(r.forecast_summary)}
          <CoverageGap reason={r.forecast_summary.reason} />
        {:else}
          <!-- Most-likely score carries its probability (no naked score, no naked %). -->
          <span class="score">
            <strong>{scoreText(r)}</strong>
            <span class="ml"
              ><Estimate
                value={r.forecast_summary.most_likely.prob}
                se={null}
                label={`${r.match_id}-most-likely`}
              /></span
            >
          </span>
          <!-- The 1X2 distribution IS the uncertainty; WinBar wraps it in a marked region. -->
          <span class="dist"><WinBar model={r.forecast_summary.one_x_two} /></span>
        {/if}
        {#if isGap(r.edge)}
          <CoverageGap reason={r.edge.reason} />
        {:else}
          <EdgeChip edge={r.edge.edge} isSynthetic={r.edge.is_synthetic} />
        {/if}
        <a class="more" href={`#/match/${encodeURIComponent(r.match_id)}`}>detail →</a>
      </li>
    {/each}
  </ul>
{:else}
  <ul class="rows">
    {#each data.knockout as k (k.match)}
      <li class="card row" data-row="ko">
        <span class="teams">{k.stage} · {k.home_ref} v {k.away_ref}</span>
        {#each [['home', k.home_occupants] as const, ['away', k.away_occupants] as const] as [side, occ]}
          <div class="occ">
            <span class="muted side">{side}:</span>
            {#if isGap(occ)}
              <CoverageGap reason={occ.reason} />
            {:else}
              {#each occ.slice(0, 4) as o (o.team)}
                <span class="oc"
                  >{o.team} <Estimate value={o.prob} se={o.se} label={`${k.match}-${o.team}`} /></span
                >
              {/each}
            {/if}
          </div>
        {/each}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .nav { display: flex; gap: 8px; margin-bottom: 12px; }
  .nav button { background: var(--card); color: var(--ink); border: 1px solid var(--line); border-radius: 999px; padding: 4px 14px; cursor: pointer; }
  .nav .active { border-color: var(--accent); color: var(--accent); }
  .rows { list-style: none; padding: 0; display: grid; gap: 10px; }
  .row { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
  .row[data-status="played"] { opacity: 0.6; }
  .teams { font-weight: 600; min-width: 220px; }
  .score { display: inline-flex; align-items: baseline; gap: 6px; }
  .score strong { font-size: 1.15em; }
  .dist { min-width: 200px; flex: 1; }
  .more { margin-left: auto; color: var(--accent); text-decoration: none; }
  .occ { display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; width: 100%; }
  .oc { font-size: 0.9em; }
</style>
