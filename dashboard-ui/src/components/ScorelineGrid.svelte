<script lang="ts">
  import { pct } from '../lib/format';
  let { grid, home, away }: { grid: number[][]; home: string; away: string } = $props();
  const max = $derived(Math.max(...grid.flat()));
</script>
<div class="wrap" data-uncertainty="distribution">
  <div class="axis muted">{away} goals →, {home} goals ↓</div>
  <table>
    <tbody>
      {#each grid as row, h}
        <tr>
          {#each row as p, a}
            <td title="{home} {h}–{a} {away}: {pct(p, 1)}"
                style="background: color-mix(in srgb, var(--accent) {Math.round((p / max) * 100)}%, transparent)"></td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>
<style>
  .wrap { overflow: auto; }
  table { border-collapse: collapse; }
  td { width: 18px; height: 18px; border: 1px solid var(--bg); }
  .axis { font-size: 0.8em; margin-bottom: 4px; }
</style>
