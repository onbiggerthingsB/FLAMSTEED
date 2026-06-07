<!--
  T9 Track record surface — BACKWARD-LOOKING PERFORMANCE STATS, not forecasts.
  CLV (beat-close rate + avg CLV%) is the spec's primary number; RPS vs the
  market/elo baselines is the calibration diagnostic. The "no naked numbers / ±
  companion" rule is for FORECASTS — these performance metrics are rendered
  plainly and clearly, labeled. A null metric or an empty (n=0) reliability bin
  renders "—", never a fabricated number/point. When no backtest records were
  supplied the whole surface is an honest coverage gap.
-->
<script lang="ts">
  import type { TrackData } from '../lib/types';
  import { isGap } from '../lib/guards';
  import { pct } from '../lib/format';
  import CoverageGap from '../components/CoverageGap.svelte';

  let { data }: { data: TrackData } = $props();
</script>

{#if isGap(data)}
  <div class="card">
    <h3>Track record</h3>
    <CoverageGap reason={data.reason} />
  </div>
{:else}
  <div class="card">
    <h3>
      Track record
      <span class="muted">· {data.n_bets} bets {#if data.is_synthetic}· NON-REAL{/if}</span>
    </h3>
    <p class="muted note">Backward-looking performance — not a forecast.</p>

    <!-- Backward-looking performance stats (CLV / RPS / reliability) — NOT forecasts.
         They are consciously exempt from the ±-companion rule, so the whole metrics
         region carries data-derived: the no-naked-number guard exempts these % readouts
         EXPLICITLY (never by accident) while still catching a stray naked forecast. -->
    <div data-derived="performance">
    <!-- CLV first: the spec's primary number. -->
    <ul class="metrics">
      <li>beat-close rate: <strong>{pct(data.beat_close_rate)}</strong></li>
      <li>avg CLV: <strong>{data.avg_clv === null ? '—' : pct(data.avg_clv, 1)}</strong></li>
    </ul>

    <h4>RPS vs baselines (lower is better)</h4>
    <ul class="metrics">
      <li>model: <strong>{data.rps.model ?? '—'}</strong></li>
      <li>market: {data.rps.market ?? '—'}</li>
      <li>elo: {data.rps.elo ?? '—'}</li>
    </ul>

    <h4>Reliability</h4>
    <table class="rel">
      <thead><tr><th>bin</th><th>n</th><th>forecast</th><th>empirical</th></tr></thead>
      <tbody>
        {#each data.reliability as b}
          <tr>
            <td>{pct(b.bin_lo)}–{pct(b.bin_hi)}</td>
            <td>{b.n}</td>
            <td>{b.forecast_mean === null ? '—' : pct(b.forecast_mean)}</td>
            <td>{b.empirical === null ? '—' : pct(b.empirical)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    </div>
  </div>
{/if}

<style>
  .note { margin: 0 0 12px; font-size: 0.85em; }
  .metrics { list-style: none; padding: 0; display: flex; gap: 24px; flex-wrap: wrap; }
  .rel { border-collapse: collapse; }
  .rel th, .rel td { padding: 4px 12px; text-align: right; border-bottom: 1px solid var(--line); }
</style>
