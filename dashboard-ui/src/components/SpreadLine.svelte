<script lang="ts">
  import type { CoverPair } from '../lib/types';
  import { pct } from '../lib/format';
  // The ±1.5 goal-line cover pair, rendered as ONE line under the win-bar:
  //   "{home} −1.5 · {p}%   ·   {away} +1.5 · {q}%"
  // It is a DERIVED readout of the scoreline DISTRIBUTION (P(home covers −1.5) = Σ grid over
  // h−a>=2; away is the complement) — NOT a posterior estimate with its own ± companion. The
  // scoreline distribution IS the uncertainty (exactly like WinBar / ScorePill / the 1X2),
  // so the whole line lives inside data-uncertainty="distribution" and every % is a readout of
  // that distribution, never a naked number. The does-NOT-beat-the-market banner already
  // covers the model-probability framing for the surface; the inline "model" label names it
  // here too. Same rounding as the scoreline percentages (pct(), 0 dp).
  let { cover, home, away }: { cover: CoverPair; home: string; away: string } = $props();
  const MINUS = '−'; // U+2212 (the project's minus, matching format.ts), not a hyphen
</script>

<!-- ONE line, under the outcome bar. The distribution marker exempts the two %s from the
     no-naked-number guard (the distribution carries the uncertainty), the same way the WinBar
     legend %s are exempt. -->
<div class="spread" data-uncertainty="distribution" data-spread>
  <span class="lbl muted">model ±1.5:</span>
  <span class="side"
    >{home} {MINUS}1.5 <span class="p">· {pct(cover.home)}</span></span
  >
  <span class="sep muted">·</span>
  <span class="side"
    >{away} +1.5 <span class="p">· {pct(cover.away)}</span></span
  >
</div>

<style>
  /* Quiet, one-line, under the win-bar — never louder than the 1X2 split it complements. */
  .spread {
    display: inline-flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 0.82em;
    font-variant-numeric: tabular-nums;
  }
  .lbl { font-size: 0.95em; letter-spacing: 0.02em; }
  .side { white-space: nowrap; }
  .p { color: var(--muted); }
  .sep { opacity: 0.6; }
</style>
