<script lang="ts">
  import { pct } from '../lib/format';
  import type { ModelSecondOpinion } from '../lib/modelSecondOpinion';

  let { opinion }: { opinion: ModelSecondOpinion } = $props();

  // The model's probability for the SAME outcome the value pick names — display-only
  // CONTEXT, never the edge. We surface it as a DERIVED, market-comparison datum (the same
  // conscious exemption the de-vigged sharp-fair-prob cell uses): it lives inside
  // data-derived="model" so the no-naked-number guard exempts the "%" explicitly, never by
  // accident, and so it can never be mistaken for a primary forecast posterior driving a bet.
  //
  // EMPHASIS (display-only — the agree/disagree computation is unchanged):
  //   • AGREE  — DE-EMPHASIZED. Our model systematically over-rates underdogs, so it "agrees"
  //              with almost any underdog value pick. That makes agreement weak, near-noise
  //              evidence — so we render it QUIETLY (muted prob · "in line"), with NO loud
  //              "agrees" badge.
  //   • DISAGREE — PROMINENT. When the model rates the pick BELOW the market, that is the
  //              genuinely useful signal: a real caution flag. It gets an amber ⚠ badge that
  //              stands out from the muted agree rows.
  //   • null   — no joinable model view → quiet "—".
  const probText = $derived(opinion.prob === null ? '—' : pct(opinion.prob, 1));
</script>

<span
  class="model"
  data-derived="model"
  data-agree={opinion.agrees === null ? 'none' : opinion.agrees ? 'agree' : 'disagree'}
>
  {#if opinion.prob === null}
    <span class="prob muted">—</span>
    <span class="note muted">no model view for this pick</span>
  {:else if opinion.agrees}
    <!-- AGREE: quiet. Weak evidence (model over-rates underdogs), so no celebratory badge. -->
    <span class="prob muted">model {probText}</span>
    <span class="note muted">· in line</span>
  {:else}
    <!-- DISAGREE: the real signal — a prominent amber caution that stands out. -->
    <span class="caution" data-caution title="Our model rates this pick BELOW the market.">
      <span class="warn-glyph" aria-hidden="true">⚠</span>
      <span class="caution-prob">model {probText}</span>
      <span class="caution-txt">caution: below the market</span>
    </span>
  {/if}
</span>

<style>
  .model { display: inline-flex; align-items: baseline; gap: 6px; white-space: nowrap; }
  .prob { font-variant-numeric: tabular-nums; }
  /* AGREE / null: quiet, recedes — weak signal, not worth the reader's attention. */
  .muted { color: var(--muted); }
  .note { font-size: 0.82em; }

  /* DISAGREE: prominent amber caution badge — the signal we actually want surfaced. */
  .caution {
    display: inline-flex; align-items: baseline; gap: 6px; white-space: nowrap;
    color: var(--warn); font-weight: 600;
    background: color-mix(in srgb, var(--warn) 14%, transparent);
    border: 1px solid color-mix(in srgb, var(--warn) 45%, transparent);
    border-radius: 999px; padding: 1px 10px;
  }
  .warn-glyph { font-weight: 700; }
  .caution-prob { font-variant-numeric: tabular-nums; }
  .caution-txt { font-size: 0.82em; }
</style>
