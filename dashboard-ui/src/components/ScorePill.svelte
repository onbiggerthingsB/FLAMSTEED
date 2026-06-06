<script lang="ts">
  import type { MostLikely } from '../lib/types';
  import { pct } from '../lib/format';
  // The most-likely scoreline + its probability, rendered as ONE distribution readout.
  // The scoreline DISTRIBUTION is the uncertainty (the adjacent WinBar + the on-demand
  // ScorelineGrid carry it), so the probability is marked data-uncertainty="distribution"
  // — NOT an Estimate with a missing scalar SE ("±?"), which would misread KNOWN
  // uncertainty as unknown. Spec §4: the unit is "1–0 · 12%" (no ±).
  let { ml }: { ml: MostLikely } = $props();
</script>

<span class="scorepill" data-uncertainty="distribution">
  <strong class="score">{ml.home_goals}–{ml.away_goals}</strong>
  <span class="prob">· {pct(ml.prob)}</span>
</span>

<style>
  .scorepill { display: inline-flex; align-items: baseline; gap: 6px; }
  .score { font-size: 1.15em; }
  .prob { color: var(--muted); font-variant-numeric: tabular-nums; }
</style>
