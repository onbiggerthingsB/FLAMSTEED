<script lang="ts">
  import { numPlusMinus } from '../lib/format';
  // A NON-PROBABILITY estimate (E[Pts], E[GD]) that still obeys the no-naked-number rule:
  // the value is a plain number, but it ALWAYS carries its SE companion in a marked node.
  // `signedValue` renders an explicit +/− (for a goal difference); `dp` is decimal places.
  let {
    value,
    se,
    label = '',
    dp = 1,
    signedValue = false,
  }: {
    value: number | null;
    se: number | null;
    label?: string;
    dp?: number;
    signedValue?: boolean;
  } = $props();
  const text = $derived(numPlusMinus(value, se, { dp, signedValue }));
  // split "5.1 ±0.2" into estimate + uncertainty so the ± lives in its own marked node.
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
