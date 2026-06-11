<script lang="ts">
  import { onMount } from 'svelte';
  import type { ScheduleData, StandingsData } from '../lib/types';
  import { isGap } from '../lib/guards';
  import { formatDate } from '../lib/format';
  import Estimate from '../components/Estimate.svelte';
  import EdgeChip from '../components/EdgeChip.svelte';
  import CoverageGap from '../components/CoverageGap.svelte';
  import WinBar from '../components/WinBar.svelte';
  import ScorePill from '../components/ScorePill.svelte';
  import SpreadLine from '../components/SpreadLine.svelte';
  import Standings from './Standings.svelte';

  // `standings` is the predicted group standings (Item A). OPTIONAL: null on a pre-feature
  // bundle with no standings.json — the standings chip then renders a coverage gap, never a
  // crash. It rides ALONGSIDE the group/knockout fixture stages as a third chip.
  let { data, standings = null }: { data: ScheduleData; standings?: StandingsData | null } =
    $props();
  const STAGES = ['group', 'knockout', 'standings'] as const;
  let stage = $state<'group' | 'knockout' | 'standings'>('group');

  // Next-up anchor (spec D6): the FIRST group row still 'upcoming' is the next fixture.
  // Mark exactly that row [data-nextup] and scroll it into view on mount so the landing
  // opens on what matters now. All-played → no anchor (nextupId stays null).
  let listEl = $state<HTMLElement | null>(null);
  const nextupId = $derived(data.group.find((r) => r.status === 'upcoming')?.match_id ?? null);
  onMount(() => {
    // Guarded: jsdom (vitest) has no scrollIntoView. The marker is what the test asserts;
    // the scroll is a best-effort browser nicety, never load-bearing.
    const el = listEl?.querySelector('[data-nextup]');
    if (el instanceof HTMLElement && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'center' });
    }
  });
</script>

<div class="nav">
  {#each STAGES as s}
    <button class:active={stage === s} aria-pressed={stage === s} onclick={() => (stage = s)}>{s}</button>
  {/each}
</div>

{#if stage === 'group'}
  <ul class="rows" bind:this={listEl}>
    {#each data.group as r (r.match_id)}
      <li
        class="card row"
        class:nextup={r.match_id === nextupId}
        data-row="group"
        data-status={r.status}
        data-match-id={r.match_id}
        data-nextup={r.match_id === nextupId ? '' : undefined}
        aria-current={r.match_id === nextupId ? 'true' : undefined}
      >
        {#if r.match_id === nextupId}<span class="nextup-tag">next up</span>{/if}
        <span class="teams">{r.home} <span class="muted">v</span> {r.away}</span>
        <span class="date muted">{formatDate(r.date)}</span>
        {#if isGap(r.forecast_summary)}
          <CoverageGap reason={r.forecast_summary.reason} />
        {:else}
          <!-- Spec D3: LEAD with the differentiated signal — the 1X2 split as the PRIMARY
               forecast element, then the top-3 scoreline SHORTLIST ("predicted score =
               shortlist, never a lone score"). -->
          <!-- The 1X2 distribution IS the uncertainty; WinBar wraps it in a marked region.
               GHOST LINE: the de-vigged ENTRY market 1X2 (forecast_summary.market_1x2, a
               DERIVED comparison present only where a real edge carries it) is ghosted into
               the bar as the `line` prop — the sharp line vs the model, inside the marked
               distribution region (the no-naked-number guard exempts the line legend). -->
          <span class="dist"
            ><WinBar
              model={r.forecast_summary.one_x_two}
              line={r.forecast_summary.market_1x2 ?? null}
            />
            <!-- ±1.5 goal-line cover, ONE line UNDER the outcome bar. A DERIVED readout of the
                 scoreline distribution (model probability; the does-not-beat-the-market banner
                 covers the framing) — rendered only when the bundle carries the cover pair. -->
            {#if r.forecast_summary.cover}
              <SpreadLine cover={r.forecast_summary.cover} home={r.home} away={r.away} />
            {/if}</span>
          <!-- The top-3 shortlist, each a distribution-marked "h–a · p%" ScorePill. This
               replaces the single lone score: the predicted score is a shortlist. Every
               ScorePill prob stays inside data-uncertainty="distribution". -->
          <span class="shortlist">
            <span class="muted label">most likely:</span>
            {#each r.forecast_summary.shortlist as ml, i (`${ml.home_goals}-${ml.away_goals}-${i}`)}
              <ScorePill {ml} />
            {/each}
          </span>
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
{:else if stage === 'knockout'}
  <ul class="rows">
    {#each data.knockout as k (k.match)}
      <li class="card row" data-row="ko">
        <!-- stage may be null (serializer match_round.get() → None); render a placeholder,
             never a raw "null" or a dangling "· " separator. -->
        <span class="teams">{k.stage ?? 'TBD round'} · {k.home_ref} v {k.away_ref}</span>
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
{:else}
  <!-- Standings chip (Item A). On a pre-feature bundle (standings null) or an empty payload,
       degrade cleanly to a coverage gap — never a crash, never a blank surface. -->
  <div data-row="standings">
    {#if standings && Object.keys(standings).length > 0}
      <Standings data={standings} />
    {:else}
      <CoverageGap reason="standings not available in this bundle" />
    {/if}
  </div>
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
  /* The next-up fixture is the quiet anchor: one accent-tinted left edge, never loud. */
  .row.nextup { border-color: color-mix(in srgb, var(--accent) 45%, var(--line)); box-shadow: inset 3px 0 0 var(--accent); opacity: 1; }
  .nextup-tag {
    align-self: center; color: var(--accent); background: var(--accent-soft);
    border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
    border-radius: 999px; padding: 1px 9px; font-size: 0.72em; font-weight: 600;
    letter-spacing: 0.04em; text-transform: uppercase;
  }
  .teams { font-weight: 600; min-width: 200px; }
  /* The 1X2 split leads as the primary forecast element. */
  .dist { min-width: 200px; flex: 1; }
  /* The top-3 shortlist: a compact row of distribution-marked ScorePills. */
  .shortlist { display: inline-flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .shortlist .label { font-size: 0.8em; letter-spacing: 0.02em; }
  .more { margin-left: auto; color: var(--accent); text-decoration: none; font-size: 0.9em; }
  .more:hover { text-decoration: underline; }
  .occ { display: flex; gap: var(--space-3); align-items: baseline; flex-wrap: wrap; width: 100%; }
  .oc { font-size: 0.9em; }
</style>
