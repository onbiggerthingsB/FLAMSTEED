<script lang="ts">
  // Reason-aware coverage badge. The data layer tags every gap with a `reason`; we map it to
  // terse, honest copy (coverageCopy) — time-resolving gaps say WHEN they fill, structural
  // gaps say WHY. "insufficient coverage" is reserved for the genuine history shortage only.
  // The raw reason always rides in the `title` so nothing is hidden, even for an unmapped
  // reason (which falls back to a neutral "data unavailable"). `data-coverage-gap` is the
  // LOAD-BEARING marker the no-naked-number guard keys on — it MUST stay on the rendered node.
  import { coverageCopy } from '../lib/coverageCopy';
  let { reason = '' }: { reason?: string } = $props();
  const copy = $derived(coverageCopy(reason));
</script>
<span class="gap" data-coverage-gap data-coverage-kind={copy.kind} title={reason}>{copy.text}</span>
<style>
  .gap { color: var(--muted); font-style: italic; font-size: 0.9em; }
</style>
