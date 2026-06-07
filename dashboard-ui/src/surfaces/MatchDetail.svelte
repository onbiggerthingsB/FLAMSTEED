<script lang="ts">
  import { onMount } from 'svelte';
  import type { FixtureDetail, Envelope, Strength } from '../lib/types';
  import { loadFixture } from '../lib/bundle';
  import { isGap } from '../lib/guards';
  import { pct, formatDate } from '../lib/format';
  import WinBar from '../components/WinBar.svelte';
  import ScorelineGrid from '../components/ScorelineGrid.svelte';
  import ScorePill from '../components/ScorePill.svelte';
  import CredibleInterval from '../components/CredibleInterval.svelte';
  import CoverageGap from '../components/CoverageGap.svelte';
  import EdgeChip from '../components/EdgeChip.svelte';

  let { baseUrl, matchId }: { baseUrl: string; matchId: string } = $props();
  let env = $state<Envelope<FixtureDetail> | null>(null);
  let error = $state<string | null>(null);
  onMount(async () => {
    try {
      env = await loadFixture(baseUrl, matchId);
    } catch (e) {
      error = (e as Error).message;
    }
  });
</script>

{#if error}<p class="err">Could not load fixture: {error}</p>
{:else if !env}<p class="muted">Loading…</p>
{:else}
  {@const d = env.data}
  <a href="#/" class="back">← schedule</a>
  <h2>{d.home} <span class="muted">v</span> {d.away} <span class="muted date">· {formatDate(d.date)}</span></h2>

  <section class="card">
    <h3>Most likely score</h3>
    <!-- The scoreline DISTRIBUTION is the uncertainty: ScorePill marks it
         data-uncertainty="distribution" ("1–0 · 15%"), never a bare pct() / "±?". -->
    <p class="ml"><ScorePill ml={d.forecast.most_likely} /></p>
    <div class="shortlist muted">
      {#each d.forecast.shortlist as s}<ScorePill ml={s} />{/each}
    </div>
    <WinBar model={d.forecast.one_x_two} />
    <ScorelineGrid grid={d.forecast.grid} home={d.home} away={d.away} />
  </section>

  <section class="card why">
    <h3>Why</h3>
    {#each [['home', d.home, d.why.team_strength.home] as const, ['away', d.away, d.why.team_strength.away] as const] as [side, name, s]}
      {@const st = s as Strength}
      <div class="ts">
        <span class="name">{name}</span>
        attack <CredibleInterval value={st.attack.value} ci={st.attack.ci} label={`${side}-att`} />
        defense <CredibleInterval value={st.defense.value} ci={st.defense.ci} label={`${side}-def`} />
      </div>
    {/each}
    <div class="row2">
      <div>xG (home): {#if isGap(d.why.xg.home)}<CoverageGap reason={d.why.xg.home.reason} />{:else}{d.why.xg.home.value}{/if}</div>
      <div>xG (away): {#if isGap(d.why.xg.away)}<CoverageGap reason={d.why.xg.away.reason} />{:else}{d.why.xg.away.value}{/if}</div>
      <div>rest (home): {#if isGap(d.why.rest_days.home)}<CoverageGap reason={d.why.rest_days.home.reason} />{:else}{d.why.rest_days.home.value}d{/if}</div>
      <div>rest (away): {#if isGap(d.why.rest_days.away)}<CoverageGap reason={d.why.rest_days.away.reason} />{:else}{d.why.rest_days.away.value}d{/if}</div>
    </div>
    <div class="form">
      <h4 class="muted">recent results — raw match history (data, not a forecast)</h4>
      {#each [[d.home, d.why.recent_form.home] as const, [d.away, d.why.recent_form.away] as const] as [name, f]}
        <div class="form-side">
          <span class="name muted">{name}</span>
          {#if isGap(f)}<CoverageGap reason={f.reason} />
          {:else}
            <ul>{#each f.matches as m}<li class="muted">{formatDate(m.date)} · {m.home_team} {m.home_score}–{m.away_score} {m.away_team}</li>{/each}</ul>
          {/if}
        </div>
      {/each}
    </div>
  </section>

  <section class="card" data-section="edge">
    <h3>Edge</h3>
    {#if isGap(d.edge)}<CoverageGap reason={d.edge.reason} />
    {:else}
      <p>
        side: <strong>{d.edge.staked}</strong>
        · <EdgeChip edge={d.edge.edge} isSynthetic={d.edge.is_synthetic} />
        <!-- stake_signal is a DERIVED ¼-Kelly signal and entry_odds is a market datum —
             neither is a posterior forecast, so both are consciously exempt from the
             ±-companion rule and live inside data-derived so the no-naked-number guard
             exempts them EXPLICITLY (never by accident). It is a read-only SIGNAL, not a
             control: there is no bet/stake/order affordance anywhere. -->
        · <span data-derived="stake">¼-Kelly stake signal {pct(d.edge.stake_signal, 1)} · entry odds {d.edge.entry_odds}</span>
      </p>
    {/if}
  </section>
{/if}

<style>
  .back { color: var(--accent); text-decoration: none; } h2 .date { font-weight: 400; }
  section { margin: 14px 0; } .ml { font-size: 1.6em; }
  .shortlist { display: flex; gap: 16px; margin: 6px 0 12px; font-size: 0.85em; flex-wrap: wrap; }
  .ts { display: flex; gap: 12px; align-items: baseline; margin: 6px 0; flex-wrap: wrap; } .ts .name { font-weight: 600; min-width: 90px; }
  .row2 { display: flex; gap: 24px; margin: 10px 0; flex-wrap: wrap; }
  .form-side { margin: 6px 0; } .form ul { margin: 4px 0; padding-left: 18px; }
</style>
