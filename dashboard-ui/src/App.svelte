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
    <a href="#/" aria-current={route.name === 'schedule' ? 'page' : undefined}>Schedule</a><a
      href="#/tournament"
      aria-current={route.name === 'tournament' ? 'page' : undefined}>Tournament</a><a
      href="#/track"
      aria-current={route.name === 'track' ? 'page' : undefined}>Track record</a>
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
  nav {
    display: flex; gap: var(--space-5); padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--line); max-width: 1100px; margin: 0 auto; width: 100%;
  }
  nav a {
    color: var(--muted); text-decoration: none; font-size: var(--fs-sm); font-weight: 500;
    padding: var(--space-1) 0; border-bottom: 2px solid transparent; transition: color 0.12s ease;
  }
  nav a:hover { color: var(--ink); }
  nav a[aria-current="page"] { color: var(--ink); border-bottom-color: var(--accent); }
  main { padding: var(--space-5); max-width: 1100px; margin: 0 auto; }
  .err { color: var(--warn); padding: var(--space-5); } .load { padding: var(--space-5); }
</style>
