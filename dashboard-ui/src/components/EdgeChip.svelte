<script lang="ts">
  import { edgeChip } from '../lib/format';
  let { edge, isSynthetic = false }: { edge: number | null; isSynthetic?: boolean } = $props();
  const label = $derived(edgeChip(edge));
  const positive = $derived(edge !== null && edge > 0);
</script>
<span class="chip" class:pos={positive} class:none={label === 'no edge'} title={isSynthetic ? 'NON-REAL (synthetic odds)' : ''}>
  {label}{#if isSynthetic && label !== 'no edge'}<span class="nr"> · NON-REAL</span>{/if}
</span>
<style>
  .chip { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.82em; border: 1px solid var(--line); }
  .pos { color: var(--good); border-color: color-mix(in srgb, var(--good) 40%, transparent); }
  .none { color: var(--muted); }
  .nr { color: var(--warn); }
</style>
