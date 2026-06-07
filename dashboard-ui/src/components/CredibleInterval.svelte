<script lang="ts">
  import { ciText } from '../lib/format';
  // value/ci are typed non-null per the serializer contract, but FIX B makes the render
  // FAIL-SAFE: a null/NaN strength value (or a missing/degenerate ci) must NOT crash the
  // whole MatchDetail surface (value.toFixed on null → blank error page). Mirror Estimate:
  // degrade to "—" inside data-estimate (no naked number, no throw). The UI must not DEPEND
  // on the producer always emitting a finite value + a well-formed [lo, hi].
  let { value, ci, label = '' }: { value: number; ci: [number, number]; label?: string } = $props();
  const ok = $derived(
    typeof value === 'number' &&
      Number.isFinite(value) &&
      Array.isArray(ci) &&
      ci.length === 2 &&
      Number.isFinite(ci[0]) &&
      Number.isFinite(ci[1]) &&
      ci[0] <= ci[1], // a reversed [hi, lo] interval is corrupt → degrade to "—"
  );
</script>

{#if ok}
  <span class="ci" data-estimate data-label={label}>
    <span class="val">{value.toFixed(2)}</span>
    <span class="unc" data-uncertainty>{ciText(ci)}</span>
  </span>
{:else}
  <!-- null/non-finite value or missing/degenerate ci → an honest em-dash, never a crash. -->
  <span class="ci" data-estimate data-label={label}>—</span>
{/if}

<style>
  .ci { display: inline-flex; align-items: baseline; gap: 6px; }
  .unc { color: var(--muted); font-size: 0.85em; }
</style>
