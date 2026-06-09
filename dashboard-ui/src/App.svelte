<script lang="ts">
  import { onMount } from 'svelte';
  import { loadBundle, loadValueBundle, type Bundle } from './lib/bundle';
  import type { ValueBundle } from './lib/types';
  import { parseHash, type Route } from './lib/router';
  import HonestyBar from './components/HonestyBar.svelte';
  import ValueBets from './surfaces/ValueBets.svelte';
  import Schedule from './surfaces/Schedule.svelte';
  import Tournament from './surfaces/Tournament.svelte';
  import Track from './surfaces/Track.svelte';
  import MatchDetail from './surfaces/MatchDetail.svelte';

  const BASE = `${import.meta.env.BASE_URL}bundle`;
  let bundle = $state<Bundle | null>(null);
  let value = $state<ValueBundle | null>(null);
  let valueError = $state<string | null>(null);
  let error = $state<string | null>(null);
  let route = $state<Route>(parseHash(location.hash));

  // The forecast (model) surfaces are SECONDARY. A match-detail hash still belongs to the
  // Forecast group, so it lights the Forecast nav as active.
  const isForecast = $derived(
    route.name === 'schedule' || route.name === 'tournament' || route.name === 'match',
  );

  onMount(() => {
    const onHash = () => (route = parseHash(location.hash));
    window.addEventListener('hashchange', onHash);
    // Fire-and-forget the loads; the cleanup must return synchronously so Svelte
    // can register the hashchange listener teardown. The value bundle is the PRIMARY
    // artifact; the model bundle is loaded for the SECONDARY Forecast/Track surfaces.
    // They are independent artifacts read side by side — a missing value bundle must not
    // take down the model surfaces, and vice versa.
    void (async () => {
      try { value = await loadValueBundle(`${BASE}/value.json`); } catch (e) { valueError = (e as Error).message; }
    })();
    void (async () => {
      try { bundle = await loadBundle(BASE); } catch (e) { error = (e as Error).message; }
    })();
    return () => window.removeEventListener('hashchange', onHash);
  });
</script>

{#if bundle}
  <HonestyBar provenance={bundle.meta.provenance} />
{/if}
<nav aria-label="surfaces">
  <a href="#/" aria-current={route.name === 'value' ? 'page' : undefined}>Value Bets</a><a
    href="#/track"
    aria-current={route.name === 'track' ? 'page' : undefined}>Track Record</a><a
    href="#/schedule"
    class="secondary"
    aria-current={isForecast ? 'page' : undefined}>Forecast</a>
  <span class="forecast-note muted">independent forecast — does NOT beat the market</span>
</nav>
<main>
  {#if route.name === 'value'}
    {#if value}
      <ValueBets bundle={value} />
    {:else if valueError}
      <p class="err">Could not load value bundle: {valueError}</p>
    {:else}
      <p class="muted load">Loading value scan…</p>
    {/if}
  {:else if route.name === 'track'}
    {#if bundle}
      <Track data={bundle.track.data} />
    {:else if error}
      <p class="err">Could not load bundle: {error}</p>
    {:else}
      <p class="muted load">Loading…</p>
    {/if}
  {:else if bundle}
    <!-- SECONDARY "Forecast" group: the model surfaces, labeled as not a market edge. -->
    <p class="forecast-label muted" data-forecast-label>
      Independent forecast — does NOT beat the market; kept for interest only.
    </p>
    {#if route.name === 'schedule'}
      <Schedule data={bundle.schedule.data} />
    {:else if route.name === 'tournament'}
      <Tournament
        data={bundle.tournament.data}
        markets={bundle.meta.data.markets}
        knockout={bundle.schedule.data.knockout}
      />
    {:else if route.name === 'match'}
      <MatchDetail baseUrl={BASE} matchId={route.id} />
    {/if}
  {:else if error}
    <p class="err">Could not load bundle: {error}</p>
  {:else}
    <p class="muted load">Loading snapshot…</p>
  {/if}
</main>

<style>
  nav {
    display: flex; gap: var(--space-5); align-items: baseline; padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--line); max-width: 1100px; margin: 0 auto; width: 100%;
  }
  nav a {
    color: var(--muted); text-decoration: none; font-size: var(--fs-sm); font-weight: 500;
    padding: var(--space-1) 0; border-bottom: 2px solid transparent; transition: color 0.12s ease;
  }
  nav a:hover { color: var(--ink); }
  nav a[aria-current="page"] { color: var(--ink); border-bottom-color: var(--accent); }
  /* The Forecast group is visibly demoted: dimmer, with an inline "not a market edge" note. */
  nav a.secondary { color: var(--muted); opacity: 0.85; }
  .forecast-note { font-size: 0.72em; font-style: italic; }
  .forecast-label { margin: 0 0 var(--space-4); font-size: var(--fs-sm); font-style: italic; }
  main { padding: var(--space-5); max-width: 1100px; margin: 0 auto; }
  .err { color: var(--warn); padding: var(--space-5); } .load { padding: var(--space-5); }
</style>
