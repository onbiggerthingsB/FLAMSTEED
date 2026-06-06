<script lang="ts">
  let { reason = '' }: { reason?: string } = $props();
</script>
<span class="gap" data-coverage-gap title={reason}>insufficient coverage</span>
<style>
  .gap { color: var(--muted); font-style: italic; font-size: 0.9em; }
</style>
