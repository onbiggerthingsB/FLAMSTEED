<!-- T5 PLACEHOLDER — the real Track record surface is built in T9. -->
<script lang="ts">
  import type { TrackData } from '../lib/types';
  import { isGap } from '../lib/guards';
  let { data }: { data: TrackData } = $props();
</script>

<h2>Track record</h2>
<p class="muted">
  Placeholder surface — real Track record lands in T9
  ({isGap(data) ? 'coverage gap' : `${data.n_bets} bets loaded`}).
</p>
