<script lang="ts">
  import { pctPlusMinus } from '../lib/format';
  let { value, se, label = '' }: { value: number | null; se: number | null; label?: string } = $props();
  const text = $derived(pctPlusMinus(value, se));
  // split "29% ±0.3" into estimate + uncertainty so the ± lives in its own marked node.
  const parts = $derived(text.split(' ±'));
</script>

<span class="estimate" data-estimate data-label={label}>
  <span class="val">{parts[0]}</span>{#if parts.length > 1}<span class="unc" data-uncertainty>±{parts[1]}</span>{/if}
</span>

<style>
  .estimate { display: inline-flex; align-items: baseline; gap: 4px; }
  .val { font-variant-numeric: tabular-nums; }
  .unc { color: var(--muted); font-size: 0.85em; }
</style>
