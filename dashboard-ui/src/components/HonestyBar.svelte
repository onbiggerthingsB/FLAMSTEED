<script lang="ts">
  import type { Provenance } from '../lib/types';
  let { provenance }: { provenance: Provenance } = $props();
</script>
<header class="bar">
  <span class="asof">as of <strong>{provenance.as_of}</strong></span>
  <span class="ver muted">model {provenance.git} · {provenance.posterior_key.slice(0, 8)} · {provenance.n_sims.toLocaleString()} sims</span>
  {#if provenance.banner}
    <span class="dryrun" title={provenance.banner}>DRY-RUN · SYNTHETIC ODDS · NOT REAL</span>
  {/if}
</header>
<style>
  /* Persistent honesty bar: as-of + version always visible at the very top. */
  .bar {
    display: flex; gap: var(--space-4); align-items: center; flex-wrap: wrap;
    padding: var(--space-2) var(--space-5); background: var(--card);
    border-bottom: 1px solid var(--line); font-size: var(--fs-sm);
    max-width: 1100px; margin: 0 auto; width: 100%;
  }
  .asof strong { font-weight: 650; }
  .ver { font-variant-numeric: tabular-nums; }
  .dryrun {
    margin-left: auto; color: #1b1d22; background: var(--warn);
    padding: 2px 10px; border-radius: 999px; font-weight: 700;
    font-size: 0.78em; letter-spacing: 0.03em;
  }
</style>
