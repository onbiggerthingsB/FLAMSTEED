<script lang="ts">
  import { onMount } from 'svelte';
  import { loadBundle, type Bundle } from './lib/bundle';
  import { parseHash, type Route } from './lib/router';
  import HonestyBar from './components/HonestyBar.svelte';
  import Schedule from './surfaces/Schedule.svelte';
  import Tournament from './surfaces/Tournament.svelte';
  import Track from './surfaces/Track.svelte';
  import MatchDetail from './surfaces/MatchDetail.svelte';

  const BASE = `${import.meta.env.BASE_URL}bundle`;
  let bundle = $state<Bundle | null>(null);
  let error = $state<string | null>(null);
  let route = $state<Route>(parseHash(location.hash));

  onMount(() => {
    const onHash = () => (route = parseHash(location.hash));
    window.addEventListener('hashchange', onHash);
    // Fire-and-forget the load; the cleanup must return synchronously so Svelte
    // can register the hashchange listener teardown.
    void (async () => {
      try { bundle = await loadBundle(BASE); } catch (e) { error = (e as Error).message; }
    })();
    return () => window.removeEventListener('hashchange', onHash);
  });
</script>

{#if error}
  <p class="err">Could not load bundle: {error}</p>
{:else if !bundle}
  <p class="muted load">Loading snapshot…</p>
{:else}
  <HonestyBar provenance={bundle.meta.provenance} />
  <nav aria-label="surfaces">
    <a href="#/">Schedule</a><a href="#/tournament">Tournament</a><a href="#/track">Track record</a>
  </nav>
  <main>
    {#if route.name === 'schedule'}
      <Schedule data={bundle.schedule.data} />
    {:else if route.name === 'tournament'}
      <Tournament data={bundle.tournament.data} markets={bundle.meta.data.markets} />
    {:else if route.name === 'track'}
      <Track data={bundle.track.data} />
    {:else if route.name === 'match'}
      <MatchDetail baseUrl={BASE} matchId={route.id} />
    {/if}
  </main>
{/if}

<style>
  nav { display: flex; gap: 16px; padding: 10px 16px; border-bottom: 1px solid var(--line); }
  nav a { color: var(--accent); text-decoration: none; }
  main { padding: 16px; max-width: 1100px; margin: 0 auto; }
  .err { color: var(--warn); padding: 16px; } .load { padding: 16px; }
</style>
