<script lang="ts">
  import type { OneXTwo } from '../lib/types';
  import { pct } from '../lib/format';
  // model = the model 1X2; line = the de-vigged sharp line (optional; ghosted markers).
  let { model, line = null }: { model: OneXTwo; line?: OneXTwo | null } = $props();
  const seg = $derived([
    { k: 'home', v: model.home, c: 'var(--accent)' },
    { k: 'draw', v: model.draw, c: 'var(--muted)' },
    { k: 'away', v: model.away, c: 'var(--good)' },
  ]);
</script>
<div class="winbar" data-uncertainty="distribution" role="img" aria-label="win/draw/loss distribution">
  {#each seg as s}
    <span class="s" style="flex:{s.v}; background:{s.c}" title="{s.k} {pct(s.v)}"></span>
  {/each}
  {#if line}
    {#each [line.home, line.home + line.draw] as edge}
      <span class="ghost" style="left:{edge * 100}%" title="sharp line"></span>
    {/each}
  {/if}
</div>
<div class="legend muted">
  <span>H {pct(model.home)}</span><span>D {pct(model.draw)}</span><span>A {pct(model.away)}</span>
  {#if line}<span class="ln">line: H {pct(line.home)} · D {pct(line.draw)} · A {pct(line.away)}</span>{/if}
</div>
<style>
  .winbar { position: relative; display: flex; height: 20px; border-radius: 6px; overflow: hidden; }
  .s { display: block; }
  .ghost { position: absolute; top: -2px; bottom: -2px; width: 2px; background: #fff; opacity: 0.55; }
  .legend { display: flex; gap: 10px; font-size: 0.8em; margin-top: 4px; }
  .ln { margin-left: auto; }
</style>
