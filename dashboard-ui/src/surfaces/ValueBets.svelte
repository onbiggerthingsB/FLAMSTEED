<!--
  PRIMARY surface — "Value Bets". Market-vs-market only: where a SOFT book offers a
  better price than the de-vigged SHARP (Pinnacle) line. SIGNAL-ONLY: this surface
  shows signals, it NEVER places a bet (there is no bet/stake/order affordance — the
  ¼-Kelly stake is a read-only SUGGESTION). The honest test is CLV, not any single
  result (see Track Record).

  No naked numbers: edge / sharp-fair-prob / ¼-Kelly stake are DERIVED signals (not
  forecast posteriors) and render inside [data-derived] — the same conscious exemption
  the EdgeChip / Track stats use. Decimal odds are plain market data (no %), so they are
  not subject to the ±-companion rule.
-->
<script lang="ts">
  import type { ValueBundle, ScheduleData } from '../lib/types';
  import { stakeSignal, decimalOdds, freshness, pct, formatDate } from '../lib/format';
  import { buildForecastIndex, modelSecondOpinion } from '../lib/modelSecondOpinion';
  import EdgeChip from '../components/EdgeChip.svelte';
  import CoverageGap from '../components/CoverageGap.svelte';
  import ModelCell from '../components/ModelCell.svelte';

  // `forecast` is the OPTIONAL model (schedule) data — passed in for the display-only
  // "model second opinion" column. It is read-only CONTEXT: it joins each value pick to
  // OUR independent forecast's take on that same outcome, and NEVER touches the edge or the
  // bettable list (those come straight off the value bundle). A missing forecast bundle
  // simply yields "—" in the Model column; it can never change which spots are bettable.
  let { bundle, forecast = null }: { bundle: ValueBundle; forecast?: ScheduleData | null } = $props();
  const p = $derived(bundle.provenance);
  const d = $derived(bundle.data);
  const forecastIndex = $derived(buildForecastIndex(forecast));
</script>

<!-- The NOT-REAL banner, made prominent at the top of the primary surface. -->
<div class="banner" role="note">
  <strong class="tag">SIGNAL-ONLY</strong>
  <span class="txt">{p.banner}</span>
</div>

<p class="lede muted">
  Signals, not guarantees. The real test is CLV, not any single result. Soft books limit winners.
</p>

<!-- Scan provenance: when, sharp source, regions, credits. No % anywhere here. -->
<p class="scanmeta muted" data-scanmeta>
  last scanned <strong>{p.scanTs}</strong>
  · sharp <strong>{p.sharpBook}</strong>
  · regions {p.regions}
  · {p.creditsUsed} credits used ({p.creditsRemaining} remaining)
</p>

<section>
  <h3>Bettable spots <span class="muted">· {d.bettable.length}</span></h3>
  {#if d.bettable.length === 0}
    <p class="empty muted">No bettable +EV spots in this scan — the World Cup is the most
      efficiently-priced market on earth; thin by design.</p>
  {:else}
    <table class="bets" data-table="bettable">
      <thead>
        <tr>
          <th>event</th><th>market</th><th>pick</th><th>edge</th><th>book</th>
          <th>odds</th><th>fair</th>
          <!-- Model = our independent forecast's take, shown as CONTEXT next to the pick.
               It is NOT the edge and does NOT decide the bet (the model does not beat the
               market). The honest label below explains the emphasis: agreement is weak
               (the model over-rates underdogs, so it "agrees" with most picks), while a ⚠
               disagreement (model rates the pick below the market) is the real caution. -->
          <th data-col="model">model<span class="model-note muted">our forecast — context, NOT the edge. Our model over-rates underdogs, so it "agrees" with most picks (weak signal). A ⚠ disagreement (model rates the pick below the market) is the real caution.</span></th>
          <th>¼-Kelly stake</th><th>freshness</th><th>kickoff</th>
        </tr>
      </thead>
      <tbody>
        {#each d.bettable as b (`${b.event}-${b.market}-${b.side}-${b.softBook}`)}
          <tr data-bet>
            <td class="ev">{b.event}</td>
            <td>{b.market}{#if b.line !== null} {b.line}{/if}</td>
            <td class="pick">{b.side}</td>
            <!-- edge is a DERIVED signal — EdgeChip wraps it in data-derived="edge". -->
            <td><EdgeChip edge={b.edge} isSynthetic={p.isSynthetic} /></td>
            <td>{b.softBook}</td>
            <!-- decimal odds: market data, not a probability (no ± rule). -->
            <td class="num">{decimalOdds(b.softOdds)}</td>
            <!-- sharp fair prob is a DERIVED de-vigged market datum, not a posterior. -->
            <td class="num" data-derived="fair">{pct(b.sharpFairProb, 1)}</td>
            <!-- MODEL SECOND OPINION (display-only): our forecast's prob for this same
                 outcome + agree/disagree vs the sharp fair prob. Derived CONTEXT, never the
                 edge — computed off the value bet + forecast index, fed nowhere else. -->
            <td data-cell="model"><ModelCell opinion={modelSecondOpinion(b, forecastIndex)} /></td>
            <!-- ¼-Kelly is a read-only SUGGESTION signal (derived), never an instruction. -->
            <td class="num" data-derived="stake">{stakeSignal(b.suggestedStake)}</td>
            <td class="num">{freshness(b.lastUpdate, p.scanTs)}</td>
            <td class="num">{formatDate(b.commenceTime)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<!-- "Filtered (and why)": every rejected spot is still serialized, tagged with the guard
     flags that excluded it — so the board shows what we filtered and WHY (honest, not hidden). -->
{#if d.filtered.length > 0}
  <details class="filtered">
    <summary>Filtered (and why) <span class="muted">· {d.filtered.length}</span></summary>
    <table class="bets" data-table="filtered">
      <thead>
        <tr>
          <th>event</th><th>market</th><th>pick</th><th>edge</th><th>book</th>
          <th>odds</th><th>why filtered</th>
        </tr>
      </thead>
      <tbody>
        {#each d.filtered as b (`${b.event}-${b.market}-${b.side}-${b.softBook}`)}
          <tr data-filtered>
            <td class="ev">{b.event}</td>
            <td>{b.market}{#if b.line !== null} {b.line}{/if}</td>
            <td class="pick">{b.side}</td>
            <td><EdgeChip edge={b.edge} isSynthetic={p.isSynthetic} /></td>
            <td>{b.softBook}</td>
            <td class="num">{decimalOdds(b.softOdds)}</td>
            <td class="flags">
              {#each b.flags as f}<span class="flag">{f}</span>{/each}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </details>
{/if}

<!-- Coverage gaps: events/markets with no sharp (Pinnacle) line. No sharp truth ⇒ no
     claim — never fabricated into an edge. Rendered as honest "insufficient coverage". -->
{#if d.coverageGaps.length > 0}
  <section class="gaps">
    <h3>Coverage gaps <span class="muted">· {d.coverageGaps.length}</span></h3>
    <ul>
      {#each d.coverageGaps as g (`${g.event}-${g.market}-${g.line}`)}
        <li>
          <span class="ev">{g.event}</span>
          <span class="muted">· {g.market}{#if g.line !== null} {g.line}{/if} ·</span>
          <CoverageGap reason={g.reason} />
        </li>
      {/each}
    </ul>
  </section>
{/if}

<style>
  .banner {
    display: flex; gap: var(--space-3); align-items: baseline; flex-wrap: wrap;
    background: color-mix(in srgb, var(--warn) 14%, var(--card));
    border: 1px solid color-mix(in srgb, var(--warn) 45%, var(--line));
    border-radius: var(--radius); padding: var(--space-3) var(--space-4);
    margin-bottom: var(--space-3);
  }
  .banner .tag {
    color: #1b1d22; background: var(--warn); padding: 2px 10px; border-radius: 999px;
    font-size: 0.78em; font-weight: 700; letter-spacing: 0.03em; white-space: nowrap;
  }
  .banner .txt { font-size: var(--fs-sm); }
  .lede { margin: 0 0 var(--space-2); font-size: var(--fs-sm); }
  .scanmeta { margin: 0 0 var(--space-5); font-size: var(--fs-sm); font-variant-numeric: tabular-nums; }
  h3 { margin: var(--space-4) 0 var(--space-3); }
  .empty { font-size: var(--fs-sm); }
  table.bets { border-collapse: collapse; width: 100%; font-size: var(--fs-sm); }
  .bets th, .bets td {
    padding: 6px 12px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: baseline;
  }
  .bets th { color: var(--muted); font-weight: 600; }
  .bets th[data-col="model"] { display: flex; flex-direction: column; gap: 2px; }
  .model-note { font-size: 0.72em; font-style: italic; font-weight: 400; max-width: 36ch; white-space: normal; line-height: 1.35; }
  .bets .num { text-align: right; font-variant-numeric: tabular-nums; }
  .bets .ev { font-weight: 600; }
  .bets .pick { color: var(--accent); }
  .filtered { margin-top: var(--space-5); }
  .filtered summary { cursor: pointer; color: var(--muted); font-weight: 600; }
  .flags { display: flex; gap: 6px; flex-wrap: wrap; }
  .flag {
    color: var(--warn); border: 1px solid color-mix(in srgb, var(--warn) 40%, transparent);
    border-radius: 999px; padding: 1px 8px; font-size: 0.85em;
  }
  .gaps { margin-top: var(--space-5); }
  .gaps ul { list-style: none; padding: 0; margin: 0; display: grid; gap: var(--space-2); }
  .gaps li { font-size: var(--fs-sm); }
  .gaps .ev { font-weight: 600; }
</style>
