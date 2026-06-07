<script lang="ts">
  import { pct } from '../lib/format';
  import CoverageGap from './CoverageGap.svelte';
  let { grid, home, away }: { grid: number[][]; home: string; away: string } = $props();
  // FIX C (crash-safety): grid is typed non-optional and rendered unconditionally in
  // MatchDetail. An empty / non-rectangular / all-zero grid used to yield Math.max(...[]) =
  // -Infinity (or max 0) → NaN% / ÷0 cell backgrounds with no fallback. Validate the grid
  // is a non-empty rectangular array of finite numbers whose max is a POSITIVE finite
  // number; otherwise degrade to a CoverageGap. Never NaN%, never ÷0.
  const valid = $derived(
    Array.isArray(grid) &&
      grid.length > 0 &&
      grid.every((row) => Array.isArray(row) && row.length > 0) &&
      grid.every((row) => row.length === grid[0].length) && // rectangular — a ragged grid is corrupt
      grid.flat().every((p) => Number.isFinite(p)),
  );
  const max = $derived(valid ? Math.max(...grid.flat()) : 0);
  const renderable = $derived(valid && Number.isFinite(max) && max > 0);
  // ratio clamped to [0,1] so even a stray out-of-range cell can never paint NaN%/negative.
  const ratio = (p: number) => Math.min(1, Math.max(0, p / max));
  // FIX G (a11y): a screen-reader summary so the grid is not hover/title-only. Locate the
  // most-likely cell (argmax over the grid) and name the distribution + that cell. The %
  // lives in an aria-label INSIDE the data-uncertainty="distribution" wrap, so the
  // no-naked-number guard exempts it (the distribution IS the uncertainty), never naked.
  const peak = $derived.by(() => {
    if (!renderable) return { h: 0, a: 0, p: 0 };
    let h = 0, a = 0, p = -1;
    grid.forEach((row, hi) =>
      row.forEach((v, ai) => {
        if (v > p) { p = v; h = hi; a = ai; }
      }),
    );
    return { h, a, p };
  });
  const summary = $derived(
    renderable
      ? `Scoreline probability distribution for ${home} vs ${away}; most likely ${home} ${peak.h}–${peak.a} ${away} at ${pct(peak.p, 1)}.`
      : '',
  );
</script>
{#if renderable}
  <div class="wrap" data-uncertainty="distribution" role="img" aria-label={summary}>
    <div class="axis muted" aria-hidden="true">{away} goals →, {home} goals ↓</div>
    <table>
      <tbody>
        {#each grid as row, h}
          <tr>
            {#each row as p, a}
              <td title="{home} {h}–{a} {away}: {pct(p, 1)}"
                  style="background: color-mix(in srgb, var(--accent) {Math.round(ratio(p) * 100)}%, transparent)"></td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{:else}
  <CoverageGap reason="scoreline grid unavailable" />
{/if}
<style>
  .wrap { overflow: auto; }
  table { border-collapse: collapse; }
  td { width: 18px; height: 18px; border: 1px solid var(--bg); }
  .axis { font-size: 0.8em; margin-bottom: 4px; }
</style>
