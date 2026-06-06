<script lang="ts">
  let ready = $state(true);
</script>

<main>
  {#if ready}
    <h1 data-testid="app-title">WC-2026 Forecast Dashboard</h1>
  {/if}
</main>
