<script lang="ts">
  import { ciText } from '../lib/format';
  let { value, ci, label = '' }: { value: number; ci: [number, number]; label?: string } = $props();
</script>

<span class="ci" data-estimate data-label={label}>
  <span class="val">{value.toFixed(2)}</span>
  <span class="unc" data-uncertainty>{ciText(ci)}</span>
</span>

<style>
  .ci { display: inline-flex; align-items: baseline; gap: 6px; }
  .unc { color: var(--muted); font-size: 0.85em; }
</style>
