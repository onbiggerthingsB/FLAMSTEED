<!-- T5 PLACEHOLDER — the real Tournament progression surface is built in T8. -->
<script lang="ts">
  import type { TournamentData } from '../lib/types';
  let { data, markets }: { data: TournamentData; markets: string[] } = $props();
</script>

<h2>Tournament</h2>
<p class="muted">
  Placeholder surface — real Tournament progression lands in T8
  ({Object.keys(data).length} teams across {markets.length} markets loaded).
</p>
