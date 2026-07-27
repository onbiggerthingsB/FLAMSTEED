<script lang="ts">
  import type { ScheduleData } from '../lib/types';
  import { isGap } from '../lib/guards';
  import { formatDate } from '../lib/format';
  import Estimate from '../components/Estimate.svelte';
  import CoverageGap from '../components/CoverageGap.svelte';
  import WinBar from '../components/WinBar.svelte';
  import ScorePill from '../components/ScorePill.svelte';
  import SpreadLine from '../components/SpreadLine.svelte';

  let {
    data,
    allowDetail,
    onSelectMatch,
  }: {
    data: ScheduleData;
    allowDetail: boolean;
    onSelectMatch: (matchId: string) => void;
  } = $props();
  const STAGES = ['group', 'knockout'] as const;
  let stage = $state<'group' | 'knockout'>('group');
  const nextupId = $derived(data.group.find((row) => row.status === 'upcoming')?.match_id ?? null);
</script>

<div class="nav">
  {#each STAGES as nextStage}
    <button
      type="button"
      class:active={stage === nextStage}
      aria-pressed={stage === nextStage}
      onclick={() => (stage = nextStage)}
    >
      {nextStage}
    </button>
  {/each}
</div>

{#if stage === 'group'}
  <ul class="rows">
    {#each data.group as row (row.match_id)}
      <li
        class="card row"
        class:nextup={row.match_id === nextupId}
        data-row="group"
        data-status={row.status}
        data-match-id={row.match_id}
        data-nextup={row.match_id === nextupId ? '' : undefined}
        aria-current={row.match_id === nextupId ? 'true' : undefined}
      >
        {#if row.match_id === nextupId}<span class="nextup-tag">next up</span>{/if}
        <span class="teams">{row.home} <span class="muted">v</span> {row.away}</span>
        <span class="date muted">{formatDate(row.date)}</span>
        {#if isGap(row.forecast_summary)}
          <CoverageGap reason={row.forecast_summary.reason} />
        {:else}
          <span class="dist">
            <WinBar model={row.forecast_summary.one_x_two} line={null} />
            {#if row.forecast_summary.cover}
              <SpreadLine
                cover={row.forecast_summary.cover}
                home={row.home}
                away={row.away}
              />
            {/if}
          </span>
          <span class="shortlist">
            <span class="muted label">most likely:</span>
            {#each row.forecast_summary.shortlist as ml, index (`${ml.home_goals}-${ml.away_goals}-${index}`)}
              <ScorePill {ml} />
            {/each}
          </span>
        {/if}
        {#if allowDetail}
          <button
            type="button"
            class="more"
            data-match-id={row.match_id}
            onclick={() => onSelectMatch(row.match_id)}
          >
            detail →
          </button>
        {/if}
      </li>
    {/each}
  </ul>
{:else}
  <ul class="rows">
    {#each data.knockout as row (row.match)}
      <li class="card row" data-row="ko">
        <span class="teams">{row.stage ?? 'TBD round'} · {row.home_ref} v {row.away_ref}</span>
        {#each [['home', row.home_occupants] as const, ['away', row.away_occupants] as const] as [side, occupants]}
          <div class="occ">
            <span class="muted side">{side}:</span>
            {#if isGap(occupants)}
              <CoverageGap reason={occupants.reason} />
            {:else}
              {#each occupants.slice(0, 4) as occupant (occupant.team)}
                <span class="oc">
                  {occupant.team}
                  <Estimate
                    value={occupant.prob}
                    se={occupant.se}
                    label={`${row.match}-${occupant.team}`}
                  />
                </span>
              {/each}
            {/if}
          </div>
        {/each}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .nav { display: flex; gap: 8px; margin-bottom: var(--space-4); }
  .nav button {
    background: transparent; color: var(--muted); border: 1px solid var(--line);
    border-radius: 999px; padding: 5px 16px; cursor: pointer; font: inherit;
    transition: color 0.12s ease, border-color 0.12s ease;
  }
  .nav button:hover { color: var(--ink); }
  .nav .active { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
  .rows { list-style: none; padding: 0; margin: 0; display: grid; gap: var(--space-3); }
  .row { display: flex; gap: var(--space-4); align-items: center; flex-wrap: wrap; }
  .row[data-status="played"] { opacity: 0.55; }
  .row.nextup {
    border-color: color-mix(in srgb, var(--accent) 45%, var(--line));
    box-shadow: inset 3px 0 0 var(--accent); opacity: 1;
  }
  .nextup-tag {
    align-self: center; color: var(--accent); background: var(--accent-soft);
    border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
    border-radius: 999px; padding: 1px 9px; font-size: 0.72em; font-weight: 600;
    letter-spacing: 0.04em; text-transform: uppercase;
  }
  .teams { font-weight: 600; min-width: 200px; }
  .dist { min-width: 200px; flex: 1; }
  .shortlist { display: inline-flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .shortlist .label { font-size: 0.8em; letter-spacing: 0.02em; }
  .more {
    margin-left: auto; padding: 0; border: 0; background: transparent;
    color: var(--accent); cursor: pointer; font: inherit; font-size: 0.9em;
  }
  .more:hover { text-decoration: underline; }
  .occ { display: flex; gap: var(--space-3); align-items: baseline; flex-wrap: wrap; width: 100%; }
  .oc { font-size: 0.9em; }
</style>
