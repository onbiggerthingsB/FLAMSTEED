<script lang="ts">
  import Tournament from '../surfaces/Tournament.svelte';
  import type {
    Envelope,
    MetaData,
    ScheduleData,
    TournamentData,
  } from '../lib/types';
  import type { EmbedClient, Tok } from './client';

  let {
    client,
    tournament,
    surface,
    theme = {},
  } = $props<{
    client: EmbedClient;
    tournament: string;
    surface: 'ladder' | 'schedule';
    theme?: Record<string, string>;
  }>();

  let meta = $state<Envelope<MetaData> | null>(null);
  let tournamentData = $state<Envelope<TournamentData> | null>(null);
  let schedule = $state<Envelope<ScheduleData> | null>(null);
  let entitlement = $state<Tok | null>(null);
  let error = $state(false);

  $effect(() => {
    let cancelled = false;
    error = false;
    Promise.all([
      client.getToken(),
      client.getJson(`/v1/bundle/${tournament}/meta.json`) as Promise<Envelope<MetaData>>,
      client.getJson(`/v1/bundle/${tournament}/tournament.json`) as Promise<Envelope<TournamentData>>,
      client.getJson(`/v1/bundle/${tournament}/schedule.json`) as Promise<Envelope<ScheduleData>>,
    ])
      .then(([token, nextMeta, nextTournament, nextSchedule]) => {
        if (cancelled) return;
        entitlement = token;
        meta = nextMeta;
        tournamentData = nextTournament;
        schedule = nextSchedule;
      })
      .catch(() => {
        if (!cancelled) error = true;
      });
    return () => {
      cancelled = true;
    };
  });

  function applyTheme(node: HTMLElement) {
    for (const [property, value] of Object.entries(theme as Record<string, string>)) {
      if (property.startsWith('--')) node.style.setProperty(property, value);
    }
  }
</script>

<div class="wc-embed" use:applyTheme data-tier={entitlement?.tier ?? 'loading'}>
  {#if error}
    <p class="wc-embed-err">forecast unavailable</p>
  {:else if meta && tournamentData && schedule}
    {#if surface === 'ladder'}
      <Tournament
        data={tournamentData.data}
        markets={meta.data.markets}
        knockout={schedule.data.knockout ?? []}
      />
    {:else}
      <p class="wc-embed-loading">schedule unavailable</p>
    {/if}
    <footer class="wc-embed-foot">
      Forecasts · as-of {meta.provenance?.as_of ?? 'unknown'} ·
      {meta.provenance?.banner ?? 'probabilities, not picks'}
    </footer>
  {:else}
    <p class="wc-embed-loading">loading forecasts…</p>
  {/if}
</div>
