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
  .bar { display: flex; gap: 16px; align-items: center; padding: 8px 16px; background: var(--card); border-bottom: 1px solid var(--line); font-size: 0.85em; }
  .dryrun { margin-left: auto; color: #1b1d22; background: var(--warn); padding: 2px 10px; border-radius: 999px; font-weight: 600; }
</style>
