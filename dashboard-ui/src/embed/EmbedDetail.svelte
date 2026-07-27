<script lang="ts">
  import type { EmbedClient } from './client';
  import type { Envelope, FixtureDetail, Strength } from '../lib/types';
  import { isGap } from '../lib/guards';
  import { formatDate } from '../lib/format';
  import WinBar from '../components/WinBar.svelte';
  import ScorelineGrid from '../components/ScorelineGrid.svelte';
  import ScorePill from '../components/ScorePill.svelte';
  import SpreadLine from '../components/SpreadLine.svelte';
  import CredibleInterval from '../components/CredibleInterval.svelte';
  import CoverageGap from '../components/CoverageGap.svelte';

  let {
    client,
    tournament,
    matchId,
    onBack,
  }: {
    client: EmbedClient;
    tournament: string;
    matchId: string;
    onBack: () => void;
  } = $props();
  let env = $state<Envelope<FixtureDetail> | null>(null);
  let error = $state<string | null>(null);

  $effect(() => {
    const requestedMatch = matchId;
    const requestedTournament = tournament;
    let cancelled = false;
    env = null;
    error = null;
    client
      .getJson<Envelope<FixtureDetail>>(
        `/v1/bundle/${requestedTournament}/fixtures/${encodeURIComponent(requestedMatch)}.json`,
      )
      .then((next) => {
        if (!cancelled) env = next;
      })
      .catch((caught: unknown) => {
        if (!cancelled) error = caught instanceof Error ? caught.message : 'request failed';
      });
    return () => {
      cancelled = true;
    };
  });
</script>

{#if error}
  <p class="err">Could not load fixture: {error}</p>
{:else if !env}
  <p class="muted">Loading…</p>
{:else}
  {@const detail = env.data}
  <button type="button" class="back" data-embed-back onclick={onBack}>← schedule</button>
  <h2>
    {detail.home} <span class="muted">v</span> {detail.away}
    <span class="muted date">· {formatDate(detail.date)}</span>
  </h2>

  <section class="card">
    <h3>Most likely score</h3>
    <p class="ml"><ScorePill ml={detail.forecast.most_likely} /></p>
    <div class="shortlist muted">
      {#each detail.forecast.shortlist as score}<ScorePill ml={score} />{/each}
    </div>
    <WinBar model={detail.forecast.one_x_two} line={null} />
    {#if detail.forecast.cover}
      <SpreadLine
        cover={detail.forecast.cover}
        home={detail.home}
        away={detail.away}
      />
    {/if}
    <ScorelineGrid
      grid={detail.forecast.grid}
      home={detail.home}
      away={detail.away}
    />
  </section>

  <section class="card why">
    <h3>Why</h3>
    {#each [['home', detail.home, detail.why.team_strength.home] as const, ['away', detail.away, detail.why.team_strength.away] as const] as [side, name, rawStrength]}
      {@const strength = rawStrength as Strength}
      <div class="ts">
        <span class="name">{name}</span>
        attack
        <CredibleInterval
          value={strength.attack.value}
          ci={strength.attack.ci}
          label={`${side}-att`}
        />
        defense
        <CredibleInterval
          value={strength.defense.value}
          ci={strength.defense.ci}
          label={`${side}-def`}
        />
      </div>
    {/each}
    <div class="row2">
      <div>
        xG (home):
        {#if isGap(detail.why.xg.home)}
          <CoverageGap reason={detail.why.xg.home.reason} />
        {:else}
          {detail.why.xg.home.value}
        {/if}
      </div>
      <div>
        xG (away):
        {#if isGap(detail.why.xg.away)}
          <CoverageGap reason={detail.why.xg.away.reason} />
        {:else}
          {detail.why.xg.away.value}
        {/if}
      </div>
      <div>
        rest (home):
        {#if isGap(detail.why.rest_days.home)}
          <CoverageGap reason={detail.why.rest_days.home.reason} />
        {:else}
          {detail.why.rest_days.home.value}d
        {/if}
      </div>
      <div>
        rest (away):
        {#if isGap(detail.why.rest_days.away)}
          <CoverageGap reason={detail.why.rest_days.away.reason} />
        {:else}
          {detail.why.rest_days.away.value}d
        {/if}
      </div>
    </div>
    <div class="form">
      <h4 class="muted">recent results — raw match history (data, not a forecast)</h4>
      {#each [[detail.home, detail.why.recent_form.home] as const, [detail.away, detail.why.recent_form.away] as const] as [name, recent]}
        <div class="form-side">
          <span class="name muted">{name}</span>
          {#if isGap(recent)}
            <CoverageGap reason={recent.reason} />
          {:else}
            <ul>
              {#each recent.matches as match}
                <li class="muted">
                  {formatDate(match.date)} · {match.home_team} {match.home_score}–{match.away_score}
                  {match.away_team}
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {/each}
    </div>
  </section>
{/if}

<style>
  .back {
    padding: 0; border: 0; background: transparent; color: var(--accent);
    cursor: pointer; font: inherit;
  }
  .back:hover { text-decoration: underline; }
  h2 .date { font-weight: 400; }
  section { margin: 14px 0; }
  .ml { font-size: 1.6em; }
  .shortlist { display: flex; gap: 16px; margin: 6px 0 12px; font-size: 0.85em; flex-wrap: wrap; }
  .ts { display: flex; gap: 12px; align-items: baseline; margin: 6px 0; flex-wrap: wrap; }
  .ts .name { font-weight: 600; min-width: 90px; }
  .row2 { display: flex; gap: 24px; margin: 10px 0; flex-wrap: wrap; }
  .form-side { margin: 6px 0; }
  .form ul { margin: 4px 0; padding-left: 18px; }
</style>
