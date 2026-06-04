# Phase-3 progression — pipeline SMOKE snapshot (synthetic fixture)

> **READ THIS FIRST.** This is a **pipeline SMOKE snapshot on a synthetic toy
> fixture** — **NOT an edge, probability, or forecast claim about any real team.**
> It proves the full Monte-Carlo path (`simulate_tournament`: per-sim posterior draw
> → group sim → FIFA ranking → knockout propagation → per-market aggregation + SE)
> runs end-to-end and returns coherent, sane shapes. The "teams" are the four
> `tiny_bracket` labels (Brazil/Argentina/Croatia/France) over a **hand-built toy
> posterior with made-up strengths** — there is no ADVI fit and no market data behind
> these numbers, so the ordering is an artifact of the chosen toy `att/def`, not a
> real-world assessment. **The only honest verdict of edge is the Phase-4
> out-of-sample walk-forward (RPS / CLV), which does not exist yet.** Per the project
> rule, a too-good result here would be a **suspected bug**, never a win.

## Setup (fully reproducible)

- **Bracket:** `tests/sim/conftest.py::tiny_bracket()` — 1 group of 4 → a single
  Final between the group winner (`1A`) and runner-up (`2A`), built through the real
  `wcmodel.sim.bracket.build_bracket`.
- **Posterior:** a synthetic toy `Posterior` (the `_toy_posterior` pattern from
  `tests/sim/test_convergence.py`) with **fixed, made-up** per-team strengths
  `att = [0.6, 0.3, 0.0, -0.3]`, `def = [0.5, 0.2, -0.1, -0.4]` (aligned to
  Brazil/Argentina/Croatia/France), `mu = 0.1`, `home_adv = 0.2` (off under the sim's
  neutral default), Dixon-Coles likelihood, `rho = -0.05`. A single fixed draw — no
  ADVI, no real data.
- **Sim knobs:** `N = 20000` sims, `seed = 0`, `max_goals = 12`, `et_scale = 0.3333`
  (ET ≈ 30/90), `pen_home_prob = 0.5` (no-tilt shootout) — the production defaults
  from `config/config.yaml` `sim:`.
- **Reproduce:**
  ```python
  from tests.sim.test_convergence import _toy_posterior, _run
  res = _run(_toy_posterior([0.6, 0.3, 0.0, -0.3], [0.5, 0.2, -0.1, -0.4]),
             n_sims=20000, seed=0)
  res.progression, res.se, res.random_tail_rate
  ```

## Progression matrix (probability)

Every cell is a probability in `[0, 1]`; **MC standard error accompanies every number**
in the SE table below (`SE = sqrt(p·(1−p)/N)`).

| team | win_group | advance | reach_r16 | reach_qf | reach_sf | reach_final | champion | first | second | third | out |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Brazil    | 0.6774 | 0.9242 | 0.9242 | 0.9242 | 0.9242 | 0.9242 | 0.6888 | 0.6774 | 0.2468 | 0.0642 | 0.0116 |
| Argentina | 0.2440 | 0.7124 | 0.7124 | 0.7124 | 0.7124 | 0.7124 | 0.2505 | 0.2440 | 0.4684 | 0.2203 | 0.0673 |
| Croatia   | 0.0668 | 0.2844 | 0.2844 | 0.2844 | 0.2844 | 0.2844 | 0.0546 | 0.0668 | 0.2176 | 0.4668 | 0.2488 |
| France    | 0.0118 | 0.0790 | 0.0790 | 0.0790 | 0.0790 | 0.0790 | 0.0061 | 0.0118 | 0.0672 | 0.2487 | 0.6723 |

(`advance` = `advance_from_group`.)

## Monte-Carlo standard error (`sqrt(p·(1−p)/N)`, N = 20000)

| team | win_group | advance | reach_r16 | reach_qf | reach_sf | reach_final | champion | first | second | third | out |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Brazil    | 0.0033 | 0.0019 | 0.0019 | 0.0019 | 0.0019 | 0.0019 | 0.0033 | 0.0033 | 0.0030 | 0.0017 | 0.0008 |
| Argentina | 0.0030 | 0.0032 | 0.0032 | 0.0032 | 0.0032 | 0.0032 | 0.0031 | 0.0030 | 0.0035 | 0.0029 | 0.0018 |
| Croatia   | 0.0018 | 0.0032 | 0.0032 | 0.0032 | 0.0032 | 0.0032 | 0.0016 | 0.0018 | 0.0029 | 0.0035 | 0.0031 |
| France    | 0.0008 | 0.0019 | 0.0019 | 0.0019 | 0.0019 | 0.0019 | 0.0006 | 0.0008 | 0.0018 | 0.0031 | 0.0033 |

- **`random_tail_rate` = 0.0162** — the FIFA tiebreak random tail fired in ≈1.6% of
  the 20000 sims (small, as expected on a SEPARATED field: distinct strengths mean
  groups usually split on points/GD/GF before the seeded drawing-of-lots tail is
  needed). It is a diagnostic, not a probability.
- **`n_sims` = 20000.**

## Coherence checks (hold on these numbers)

- **Reach ladder monotone:** `champion ≤ reach_final ≤ reach_sf ≤ reach_qf ≤
  advance_from_group` for every team (by construction — cumulative depth thresholds).
- **`reach_r16 = reach_qf = reach_sf = reach_final = advance_from_group` here is
  EXPECTED, not a bug:** `tiny_bracket` has only a Final (no distinct R16/QF/SF
  rounds), so a team that advances from the group reaches the Final's depth (0), which
  clears every earlier-round threshold — all reach rungs collapse onto "advanced to
  the Final". On the real 12-group/104-fixture bracket these rungs separate.
- **`win_group ≡ first`** (identical columns — both are group placing 0).
- **Per-group placing partitions:** `first + second + third + out = 1` per team
  (every sim places every group team exactly once).
- **`champion` sums to 1.0** across the four teams (every sim crowns exactly one
  champion in the single Final).

The headline ordering (Brazil > Argentina > Croatia > France) simply reflects the
chosen toy `att/def` ranking — it is a smoke artifact of the synthetic input, **not**
a real-world claim. The real edge assessment is **Phase 4**.
