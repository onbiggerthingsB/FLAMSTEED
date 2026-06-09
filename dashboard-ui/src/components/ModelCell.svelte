<script lang="ts">
  import { pct } from '../lib/format';
  import type { ModelSecondOpinion } from '../lib/modelSecondOpinion';

  let { opinion }: { opinion: ModelSecondOpinion } = $props();

  // The model's probability for the SAME outcome the value pick names — display-only
  // CONTEXT, never the edge. We surface it as a DERIVED, market-comparison datum (the same
  // conscious exemption the de-vigged sharp-fair-prob cell uses): it lives inside
  // data-derived="model" so the no-naked-number guard exempts the "%" explicitly, never by
  // accident, and so it can never be mistaken for a primary forecast posterior driving a bet.
  const label = $derived(
    opinion.agrees === null
      ? 'no model view for this pick'
      : opinion.agrees
        ? 'agrees (model rates it ≥ market)'
        : 'disagrees (model rates it below market)',
  );
</script>

<span class="model" data-derived="model" data-agree={opinion.agrees === null ? 'none' : opinion.agrees ? 'agree' : 'disagree'}>
  {#if opinion.prob === null}
    <span class="prob muted">—</span>
    <span class="tag none">{label}</span>
  {:else}
    <span class="prob">{pct(opinion.prob, 1)}</span>
    <span class="tag" class:agree={opinion.agrees} class:disagree={!opinion.agrees}>{label}</span>
  {/if}
</span>

<style>
  .model { display: inline-flex; align-items: baseline; gap: 8px; white-space: nowrap; }
  .prob { font-variant-numeric: tabular-nums; }
  .tag { font-size: 0.82em; border-radius: 999px; padding: 1px 8px; border: 1px solid var(--line); }
  .tag.agree { color: var(--good); border-color: color-mix(in srgb, var(--good) 40%, transparent); }
  .tag.disagree { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 40%, transparent); }
  .tag.none { color: var(--muted); }
</style>
