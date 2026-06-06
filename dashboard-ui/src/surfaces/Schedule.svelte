<!-- T5 PLACEHOLDER — the real Schedule landing surface is built in T6. -->
<script lang="ts">
  import type { ScheduleData } from '../lib/types';
  let { data }: { data: ScheduleData } = $props();
</script>

<h2>Schedule</h2>
<p class="muted">
  Placeholder surface — real Schedule landing lands in T6
  ({data.group.length} group fixtures, {data.knockout.length} knockout slots loaded).
</p>
