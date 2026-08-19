"""Leakage, parity and coherence checks for the league-table simulator (plan v2 T6).

Three things can be wrong with a season forecast while every unit test in
`epl/tests/test_leaguesim.py` still passes, and this module is the answer to
each of them.

LEAKAGE. The engine decides what is "played" from a results ledger, and a ledger
is a mutable thing. If a result the cutoff cannot see ever reached the numbers,
every score this project publishes would be a fiction, and the failure is silent:
the run still completes, the matrix still sums to one. :func:`leakage_canary`
therefore rewrites one post-cutoff result and demands the whole run come back
BYTE-identical — matrix, retained rows, envelope, digest. That negative control
is worthless on its own (a canary that mutated nothing, or a builder that
quietly dropped the mutation, would pass it), so the same call carries two
positive controls: the SAME mutation at a later cutoff must move the numbers, and
a PRE-cutoff mutation at the SAME cutoff must move them too. Only the three
together are evidence. This is the `epl.walkforward.point_in_time_canary`
pattern aimed at the simulator instead of the fit — that canary covers the fit
(anchor, panel, posterior), this one covers the conditioning, so the two are
complementary and neither subsumes the other.

CUTOFF-SEMANTICS DRIFT. "Played" is defined twice in this codebase: here, from
the results ledger, and in `wcmodel.data.features.build`, from a day-floored
`date < cutoff` filter over the bitemporal store. Two implementations of one
rule drift. :func:`played_set_parity` asserts they agree on the real archive, by
match id. The day-floor predicate is MIRRORED here (:func:`played_as_of`) rather
than imported from `wcmodel.sim.run._played_as_of` — that function is private,
and a mirror checked against the public `features.build` output at real cutoffs
is worth more than a private import that would make the check circular.

COHERENCE. A display matrix whose columns do not sum to one is not a badly
calibrated forecast, it is an inadmissible one (plan v2 D10). :func:`coherence`
checks the whole D10 list and NAMES every violation instead of raising on the
first, so one call tells the operator everything that is wrong.

None of this replaces the guards inside the engine — `epl.table` raises on a
broken identity while the run is still in flight. These are the checks that need
two runs, an external oracle, or the real archive, which is why they live outside
the hot path and are runnable on their own:

    PYTHONPATH=src:. .venv/bin/python -m epl.simcanary

runs the plan's acceptance set (leakage + coherence + played-set parity on the
archive at 2024/25 MW10 and 2025/26 MW0) and prints the report as canonical JSON.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import sys
from typing import Callable

import numpy as np
import pandas as pd

from epl import baseline, freeze, leaguesim, particles, paths
from epl import season as season_mod
from epl import table as table_mod
from wcmodel.data import features as wc_features
from wcmodel.data.features import valid_played_results
from wcmodel.data.store import BitemporalStore
from wcmodel.model import draw_api

__all__ = [
    "ACCEPTANCE_CUTOFFS", "CanaryError", "archive_state_builder", "check_run",
    "coherence", "leakage_canary", "ledger_state_builder", "marginal_parity",
    "played_as_of", "played_set_parity", "run_acceptance",
]


class CanaryError(RuntimeError):
    """A check refused to run — usually because it would have been vacuous."""


#: Coherence tolerance. The literature's admissibility condition for a position
#: matrix is exact; 1e-8 is the floating-point allowance around it (plan v2 D10).
DEFAULT_TOL = 1e-8

#: How many cluster standard errors a simulated marginal may sit from the
#: published one before the parity fails (plan v2 D12).
DEFAULT_N_SIGMA = 4.0

#: Scoreline cells rarer than this many expected hits are not compared: at N
#: sims a cell with an expected count of 2 has no usable standard error, and
#: comparing it would be a coin flip rather than a test.
DEFAULT_MIN_EXPECTED = 25.0

#: A cutoff after every result any archive season can hold. Used only to ask a
#: builder "what does the record eventually contain?", so the canary can pick a
#: result that is genuinely in the future at the cutoff under test.
FAR_FUTURE = "2999-01-01"

#: The plan's acceptance set (§6 T6): `{label: (season, cutoff)}`. The cutoffs
#: are §5's schedule resolved against this archive — MW0 is the season's first
#: weekly walk-forward cutoff, MW10 the earliest weekly cutoff with >= 100 of
#: the season's fixtures behind it.
ACCEPTANCE_CUTOFFS = {
    "2024/25 MW10": ("2024/25", "2024-11-23"),
    "2025/26 MW0": ("2025/26", "2025-08-15"),
}


# ==========================================================================
# 1. the played set, as the fit's own layer defines it
# ==========================================================================

def played_as_of(store, cutoff) -> pd.DataFrame:
    """Results knowable at `cutoff`, by the feature layer's exact rule.

    A line-for-line mirror of the predicate `wcmodel.data.features.build`
    applies (and of `wcmodel.sim.run._played_as_of`, which is private and so is
    not imported):

      1. `store.read("results", cutoff)` — the bitemporal as-of read;
      2. coerce a tz-aware cutoff to tz-naive UTC, then DAY-FLOOR it: a match
         on day D is not knowable until D+1, so a same-day match never leaks;
      3. coerce the result dates symmetrically and keep `date < cutoff_day` —
         this strict, day-floored filter is the leakage-critical line;
      4. `valid_played_results` — the shared definition of a played match.

    A mirror is only as good as the check on it, which is why
    :func:`played_set_parity` compares this against `features.build`'s actual
    output rather than trusting the two to have stayed in step.
    """
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tz is not None:
        cutoff = cutoff.tz_convert("UTC").tz_localize(None)
    cutoff_day = cutoff.normalize()

    results = store.read("results", cutoff=cutoff)
    results["date"] = pd.to_datetime(results["date"])
    if getattr(results["date"].dt, "tz", None) is not None:
        results["date"] = results["date"].dt.tz_convert("UTC").dt.tz_localize(None)
    results = results.loc[results["date"] < cutoff_day].copy()
    results = valid_played_results(results)
    results["date"] = results["date"].dt.normalize()
    return results


def played_set_parity(store, cutoff, state, matches=None, *, config=None,
                      cache_dir=None, panel=None) -> dict:
    """The simulator's played set IS the row set the fit consumes. Asserted.

    `state` is a :class:`epl.season.SeasonState` for an ARCHIVE season, so its
    fixtures can be mapped back to the archive's `match_id`s; a live season has
    no archive rows and the comparison would be vacuously true, which raises.

    `cache_dir` routes the panel through `features.build_cached` (what
    `epl.dcfit` itself uses). The default is the uncached `features.build`: a
    parity check should recompute rather than compare against something a
    previous run left on disk. `panel` hands in a panel the caller already built
    AT THIS CUTOFF — the build costs ~45 s on this archive, and a caller
    checking several states against one cutoff should not pay it twice.
    """
    matches = baseline.load_matches() if matches is None else matches
    frame = matches.loc[matches["season"] == state.season]
    if frame.empty:
        raise CanaryError(
            f"{state.season} has no rows in the archive, so there is no panel to "
            "compare the simulator's played set against. This parity is for the "
            "archive seasons; a live season is covered by the leakage canary.")

    code = state.season_code
    wanted = {str(row.match_id): season_mod.fixture_id(code, row.home_key, row.away_key)
              for row in frame.itertuples()}
    unknown = set(wanted.values()) - set(state.fixtures)
    if unknown:
        raise CanaryError(
            f"{state.season}: {len(unknown)} archive fixture(s) are not in the "
            f"state's fixture set, e.g. {sorted(unknown)[:3]}")

    if panel is None:
        cfg = freeze.frozen_wcmodel_config() if config is None else config
        panel = (wc_features.build(cutoff, store, cfg) if cache_dir is None
                 else wc_features.build_cached(cutoff, store, cfg,
                                               cache_dir=cache_dir))
    panel_ids = {str(m) for m in panel["match_id"]}
    mirror_ids = {str(m) for m in played_as_of(store, cutoff)["match_id"]}

    panel_fixtures = {wanted[m] for m in panel_ids & set(wanted)}
    sim_played = set(state.played)
    only_in_sim = sorted(sim_played - panel_fixtures)
    only_in_panel = sorted(panel_fixtures - sim_played)
    mirror_equals_panel = mirror_ids == panel_ids

    return {
        "season": state.season,
        "cutoff": str(pd.Timestamp(cutoff)),
        "n_played": len(sim_played),
        "n_panel_rows_this_season": len(panel_fixtures),
        "n_panel_rows_all_seasons": len(panel_ids),
        "mirror_equals_panel": bool(mirror_equals_panel),
        "only_in_sim": only_in_sim,
        "only_in_panel": only_in_panel,
        "PASS": bool(mirror_equals_panel and not only_in_sim and not only_in_panel),
    }


# ==========================================================================
# 2. season-state builders (what the leakage canary mutates through)
# ==========================================================================

#: A builder is `(cutoff, mutations | None) -> SeasonState`, where `mutations`
#: maps `fixture_id -> (hg, ag)`. Everything else about the season is held
#: fixed, so a difference between two states is exactly the mutation.
StateBuilder = Callable[..., season_mod.SeasonState]


def archive_state_builder(matches: pd.DataFrame, season: str, *,
                          root=season_mod.SEASON_ROOT,
                          require_verified_adjustments: bool = True) -> StateBuilder:
    """A :data:`StateBuilder` over one completed archive season."""
    matches = matches.reset_index(drop=True)
    frame = matches.loc[matches["season"] == season]
    if frame.empty:
        raise CanaryError(f"no archive rows for {season}")
    code = str(frame["season_code"].iloc[0])
    row_of = {season_mod.fixture_id(code, row.home_key, row.away_key): row.Index
              for row in frame.itertuples()}

    def build(cutoff, mutations: dict | None = None) -> season_mod.SeasonState:
        used = matches
        if mutations:
            used = matches.copy()
            for fid, (hg, ag) in mutations.items():
                if fid not in row_of:
                    raise CanaryError(f"{season}: no archive fixture {fid!r} to mutate")
                used.loc[row_of[fid], "fthg"] = int(hg)
                used.loc[row_of[fid], "ftag"] = int(ag)
        return season_mod.archive_season_state(
            used, season, cutoff, root=root,
            require_verified_adjustments=require_verified_adjustments)

    return build


def ledger_state_builder(season_obj: season_mod.Season, *, observed_by=None,
                         require_verified_adjustments: bool = False) -> StateBuilder:
    """A :data:`StateBuilder` over a live season's results ledger."""
    def build(cutoff, mutations: dict | None = None) -> season_mod.SeasonState:
        obj = season_obj
        if mutations:
            rows = [dict(row) for row in season_obj.results]
            missing = set(mutations) - {row["fixture_id"] for row in rows}
            if missing:
                raise CanaryError(
                    f"{season_obj.season}: no ledger row for {sorted(missing)}")
            for row in rows:
                new = mutations.get(row["fixture_id"])
                if new is not None:
                    row["hg"], row["ag"] = int(new[0]), int(new[1])
            obj = dataclasses.replace(season_obj, results=tuple(rows))
        return obj.at(cutoff, observed_by,
                      require_verified_adjustments=require_verified_adjustments)

    return build


# ==========================================================================
# 3. the leakage canary
# ==========================================================================

def _numbers_digest(run: leaguesim.SimRun) -> str:
    """sha256 over every NUMBER a run produced — no provenance, no wall time.

    Deliberately wider than `SimRun.digest`: it includes the retained rows and
    the reconstructed full scoreline block, so "nothing moved" means nothing
    moved anywhere, not merely that the published summary happened to round the
    same way.
    """
    digest = hashlib.sha256()
    for array in (run.matrix, run.matrix_se, run.shared_mass,
                  run.unresolved_playoff_mass, run.unresolved_multiway_mass,
                  run.retained_rows.particle, run.retained_rows.scorelines,
                  run.retained_rows.fixture_ordinals, run.retained_rows.points,
                  run.retained_rows.gd, run.retained_rows.gf,
                  run.retained_rows.block_start, run.retained_rows.block_span,
                  run.retained_rows.resolution_code, run.retained_rows.order,
                  run.full_scorelines()):
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _flip(result: tuple[int, int]) -> tuple[int, int]:
    """A scoreline that differs from `result` in goals AND in outcome."""
    hg, ag = int(result[0]), int(result[1])
    return (0, 9) if hg >= ag else (9, 0)


def leakage_canary(season_state_builder: StateBuilder, book, cutoff, seed, *,
                   later=None, target=None, arm: str = "dc_native",
                   n_sims: int = 96, chunk_size: int = 48) -> dict:
    """Rewrite one post-cutoff result and demand the run comes back identical.

    Returns the plan's two flags plus the evidence behind them:

    ``negative_identical``
        the post-cutoff mutation left every number byte-identical at `cutoff`;
    ``positive_changed``
        the SAME mutation moved the numbers at `later`, so it was real;
    ``pre_cutoff_changed``
        mutating a result the cutoff CAN see moved the numbers at `cutoff`, so
        the run is sensitive to exactly the results it is entitled to see. At an
        opener nothing is visible yet, so this control does not exist: it comes
        back ``None`` with ``pre_cutoff_control_available`` False, and ``PASS``
        rests on the other two. The canary is still not vacuous there — the
        `later` control is what proves the mutation was real.

    ``PASS`` is every control that exists. `later` defaults to the day after the
    mutated fixture's known kickoff — a kickoff is used HERE only to choose a
    second cutoff, never to decide whether anything is played (plan v2 D3).
    """
    clean_state = season_state_builder(cutoff, None)
    full_state = season_state_builder(FAR_FUTURE, None)

    candidates = sorted(set(full_state.played) - set(clean_state.played))
    if not candidates:
        raise CanaryError(
            f"nothing in the record is dated after {cutoff}: there is no "
            "post-cutoff result to mutate, so this canary would assert nothing. "
            "Run it at an earlier cutoff.")
    if target is None:
        target = candidates[len(candidates) // 2]
    elif target not in candidates:
        raise CanaryError(f"{target!r} is not a post-cutoff result at {cutoff}")

    # The pre-cutoff control needs a result the cutoff CAN see. At an opener
    # there is none, and the honest answer is to say so rather than to invent
    # one or to fail a check the season cannot support.
    visible = sorted(clean_state.played)
    pre_target = visible[len(visible) // 2] if visible else None
    pre_mutation = None if pre_target is None else _flip(clean_state.played[pre_target])

    mutation = _flip(full_state.played[target])

    if later is None:
        kickoff = full_state.kickoffs_known[target][0]
        later = str((pd.Timestamp(kickoff) + pd.Timedelta(days=1)).date())

    # Each state is built and IMMEDIATELY run. That ordering is deliberate:
    # if anything the builder touches is shared with the engine — an ungated
    # results cache, a module-level map — the run that follows the build is the
    # one that sees it, and the canary catches the leak. Building all five
    # states first and running them afterwards would hide exactly that bug.
    def _pair(at, mutations):
        state = season_state_builder(at, mutations)
        return state, leaguesim.simulate(arm, state, book, n_sims, seed, chunk_size)

    clean_state, clean_run = _pair(cutoff, None)
    dirty_state, dirty_run = _pair(cutoff, {target: mutation})
    clean_later, clean_late = _pair(later, None)
    dirty_later, dirty_late = _pair(later, {target: mutation})

    if target not in clean_later.played:
        raise CanaryError(
            f"{target} is still unplayed at {later}, so the positive control "
            "would prove nothing. Pass an explicit `later`.")
    if dirty_later.played.get(target) != mutation:
        raise CanaryError(
            f"the mutation did not land: {target} is "
            f"{dirty_later.played.get(target)} at {later}, not {mutation}")

    states_identical = clean_state.played == dirty_state.played

    negative_identical = _numbers_digest(clean_run) == _numbers_digest(dirty_run)
    negative_digest_identical = clean_run.digest() == dirty_run.digest()
    positive_changed = _numbers_digest(clean_late) != _numbers_digest(dirty_late)

    pre_cutoff_changed = None
    pre_matrix_gap = None
    if pre_target is not None:
        _pre_state, pre_run = _pair(cutoff, {pre_target: pre_mutation})
        pre_cutoff_changed = bool(
            _numbers_digest(clean_run) != _numbers_digest(pre_run))
        pre_matrix_gap = float(np.abs(clean_run.matrix - pre_run.matrix).max())

    return {
        "cutoff": str(pd.Timestamp(cutoff)),
        "later": str(later),
        "season": clean_state.season,
        "arm": arm,
        "n_sims": int(n_sims),
        "seed": int(seed),
        "target": target,
        "mutation": list(mutation),
        "true_result": list(full_state.played[target]),
        "pre_cutoff_target": pre_target,
        "pre_cutoff_mutation": None if pre_mutation is None else list(pre_mutation),
        "pre_cutoff_control_available": pre_target is not None,
        "n_mutated": 1,
        "n_post_cutoff_candidates": len(candidates),
        "n_played_at_cutoff": len(clean_state.played),
        "n_played_at_later": len(clean_later.played),
        "states_identical_at_cutoff": bool(states_identical),
        "negative_identical": bool(negative_identical),
        "negative_digest_identical": bool(negative_digest_identical),
        "positive_changed": bool(positive_changed),
        "pre_cutoff_changed": pre_cutoff_changed,
        "max_abs_matrix_diff_negative": float(
            np.abs(clean_run.matrix - dirty_run.matrix).max()),
        "max_abs_matrix_diff_positive": float(
            np.abs(clean_late.matrix - dirty_late.matrix).max()),
        "max_abs_matrix_diff_pre_cutoff": pre_matrix_gap,
        "PASS": bool(states_identical and negative_identical
                     and negative_digest_identical and positive_changed
                     and (pre_cutoff_changed is not False)),
    }


# ==========================================================================
# 4. marginal parity with what production issues (plan v2 D12)
# ==========================================================================

def _cluster_se_columns(values: np.ndarray, n_particles: int) -> np.ndarray:
    """Cluster-by-particle SE for every column of `values[N, K]`.

    Relies on the engine's own stratification contract — season ``i`` is priced
    by particle ``i mod S`` (plan v2 D14), which the caller asserts before
    calling — so the scatter is `leaguesim.sum_by_particle`'s strided sum rather
    than one `bincount` per column.
    """
    n_sims = values.shape[0]
    counts = np.full(n_particles, n_sims // n_particles, dtype=float)
    counts[:n_sims % n_particles] += 1
    means = leaguesim.sum_by_particle(values, 0, n_particles) / counts[:, None]
    overall = values.mean(axis=0)
    return np.sqrt(((means - overall) ** 2).sum(axis=0)
                   / (n_particles * (n_particles - 1)))


def _reference_grid(book: particles.ParticleBook, post, home: str,
                    away: str) -> np.ndarray:
    """The grid production would publish for this fixture.

    With a real `Posterior`, that is `draw_api.production_grid` itself. With
    `post=None` (a synthetic book) it is the book's own mechanism-(c) mixture
    `(1-a)*gbar + a*q`, whose bitwise equality with `production_grid` is pinned
    separately in `epl/tests/test_particles.py` — so the reference is still the
    published law, and what is under test here is whether the SAMPLER reproduces
    it.
    """
    if post is not None:
        return np.asarray(draw_api.production_grid(
            post, draw_api.FixtureCtx(home=home, away=away),
            max_goals=draw_api.PRODUCTION_MAX_GOALS), float)

    lh, la = book.rates(home, away)
    grids, _excluded = particles.fixture_grids(lh, la, book.rho, book.max_goals)
    gbar = particles.mean_grid(grids)
    if not book.is_provisional(home, away):
        return gbar
    q = particles.widening_component(gbar, book.alpha)
    if q is None:
        return gbar
    return (1.0 - book.alpha) * gbar + book.alpha * q


def marginal_parity(book, post, run: leaguesim.SimRun, fixtures=None, *,
                    n_sigma: float = DEFAULT_N_SIGMA,
                    min_expected_count: float = DEFAULT_MIN_EXPECTED) -> dict:
    """Simulated per-fixture marginals must BE the published per-fixture forecast.

    For each fixture the simulated 1X2 frequencies and the simulated scoreline
    frequencies are compared against :func:`_reference_grid` at `n_sigma`
    cluster-by-particle standard errors (plan v2 D12/D15). Scoreline cells with
    fewer than `min_expected_count` expected hits are skipped — at those
    frequencies the estimator has no usable standard error, and comparing them
    would add noise rather than evidence.

    The standard error used is `max(cluster SE, binomial SE)`. The cluster form
    is the right estimator (seasons sharing a particle are not independent) but
    it collapses to zero for a cell every particle agrees on; the binomial form
    is the floor that stops a degenerate estimate from failing the check for the
    wrong reason.
    """
    plan = run.plan
    n_sims, n_particles = plan.n_sims, plan.n_particles
    if n_sims % n_particles:
        raise CanaryError(
            f"marginal parity needs N ({n_sims}) to be a multiple of S "
            f"({n_particles}): otherwise some particles price one more season "
            "than others, and the simulated marginal is then an unbiased "
            "estimate of a weighted mean, not of the particle-mean grid "
            "production publishes.")
    if not np.array_equal(run.retained_rows.particle,
                          leaguesim.particle_index(n_sims, n_particles)):
        raise CanaryError("the run's particle assignment is not the stratified i mod S")

    column_of = {int(o): j for j, o
                 in enumerate(run.retained_rows.fixture_ordinals.tolist())}
    fixtures = ([plan.fixtures[p].fixture_id for p in plan.unplayed_positions]
                if fixtures is None else list(fixtures))

    side = int(book.max_goals) + 1
    labels = ["1x2 home", "1x2 draw", "1x2 away"] + [
        f"cell {h}-{a}" for h in range(side) for a in range(side)]
    failures: list[str] = []
    worst = 0.0
    n_cells = 0
    n_provisional = 0
    per_fixture = []

    for fid in fixtures:
        fixture = plan.fixtures[plan.position_of(fid)]
        if fixture.result is not None:
            raise CanaryError(f"{fid} is played: it has no simulated marginal")

        reference = _reference_grid(book, post, fixture.home_key, fixture.away_key)
        if reference.shape != (side, side):
            raise CanaryError(
                f"{fid}: reference grid is {reference.shape}, expected "
                f"{(side, side)} — the book and the reference disagree on max_goals")
        provisional = book.is_provisional(fixture.home_key, fixture.away_key)
        n_provisional += int(provisional)

        scores = run.retained_rows.scorelines[:, column_of[fixture.ordinal], :]
        scores = scores.astype(np.int64)
        onehot = np.zeros((n_sims, side * side))
        onehot[np.arange(n_sims), scores[:, 0] * side + scores[:, 1]] = 1.0
        outcome = np.stack([(scores[:, 0] > scores[:, 1]).astype(float),
                            (scores[:, 0] == scores[:, 1]).astype(float),
                            (scores[:, 0] < scores[:, 1]).astype(float)], axis=1)
        block = np.concatenate([outcome, onehot], axis=1)

        empirical = block.mean(axis=0)
        ref_1x2 = draw_api.grid_one_x_two(reference)
        ref = np.concatenate([
            np.array([ref_1x2["home"], ref_1x2["draw"], ref_1x2["away"]]),
            reference.reshape(-1)])
        se = np.maximum(_cluster_se_columns(block, n_particles),
                        np.sqrt(np.clip(ref * (1.0 - ref), 0.0, None) / n_sims))

        compared = np.zeros(block.shape[1], bool)
        compared[:3] = True
        compared[3:] = (ref[3:] * n_sims) >= min_expected_count
        gap = np.abs(empirical - ref)
        deviation = np.where(se > 0, gap / np.where(se > 0, se, 1.0),
                             np.where(gap > 0, np.inf, 0.0))

        n_cells += int(compared.sum())
        fixture_worst = float(np.max(deviation[compared], initial=0.0))
        worst = max(worst, fixture_worst)
        for k in np.flatnonzero(compared & (deviation > n_sigma)):
            failures.append(
                f"{fid} | {labels[k]} | simulated {empirical[k]:.5f} vs published "
                f"{ref[k]:.5f} = {deviation[k]:.2f} SE")
        per_fixture.append({
            "fixture_id": fid,
            "provisional": bool(provisional),
            "n_compared": int(compared.sum()),
            "max_sigma": fixture_worst,
        })

    return {
        "n_fixtures": len(fixtures),
        "n_provisional": int(n_provisional),
        "n_cells_compared": int(n_cells),
        "n_sigma": float(n_sigma),
        "min_expected_count": float(min_expected_count),
        "reference": "production_grid" if post is not None else "book_mixture",
        "max_sigma": float(worst),
        "per_fixture": per_fixture,
        "failures": failures,
        "PASS": not failures,
    }


# ==========================================================================
# 5. coherence (plan v2 D10)
# ==========================================================================

def coherence(run: leaguesim.SimRun, *, tol: float = DEFAULT_TOL) -> dict:
    """Every D10 identity, checked and NAMED rather than raised on the first.

    An operator debugging a broken run wants the whole list; the engine already
    fails fast while the run is in flight.
    """
    plan = run.plan
    failures: list[str] = []
    matrix = np.asarray(run.matrix, float)
    n_clubs = len(plan.clubs)

    # --- the display matrix is a doubly stochastic 20x20 -------------------
    row_error = float(np.abs(matrix.sum(axis=1) - 1.0).max())
    col_error = float(np.abs(matrix.sum(axis=0) - 1.0).max())
    negative = bool(np.any(matrix < -tol))
    matrix_rows_ok = row_error <= tol and not negative
    matrix_cols_ok = col_error <= tol
    if row_error > tol:
        failures.append(f"club rows do not sum to 1 (worst {row_error:.3e})")
    if negative:
        failures.append("negative mass in the position matrix")
    if col_error > tol:
        failures.append(f"position columns do not sum to 1 (worst {col_error:.3e})")

    # --- every consequence market IS its column sum ------------------------
    slices = leaguesim.market_slices(n_clubs)
    markets_ok = True
    market_error = 0.0
    market_totals: dict[str, float] = {}
    for market in leaguesim.MARKETS:
        lo, hi = slices[market]
        total = 0.0
        for i, club in enumerate(plan.clubs):
            published = float(run.consequences[club][market]["p"])
            expected = float(matrix[i, lo:hi].sum())
            market_error = max(market_error, abs(published - expected))
            if abs(published - expected) > tol:
                markets_ok = False
                failures.append(
                    f"{club} {market}: published {published:.9f} != column sum "
                    f"{expected:.9f}")
            total += published
        market_totals[market] = total
        if abs(total - (hi - lo)) > tol * n_clubs:
            markets_ok = False
            failures.append(
                f"{market} sums to {total:.9f} across clubs, not {hi - lo}")

    # --- the convention-allocated mass is a SUBSET of the matrix -----------
    mass = (np.asarray(run.shared_mass, float)
            + np.asarray(run.unresolved_playoff_mass, float)
            + np.asarray(run.unresolved_multiway_mass, float))
    mass_ok = bool(np.all(mass >= -tol) and np.all(mass <= matrix + tol))
    if not mass_ok:
        failures.append(
            "the convention-allocated mass (shared + unresolved) is not a "
            "subset of the display matrix")

    # --- every club plays a complete double round-robin ---------------------
    double_round_robin_ok = bool(
        np.all(plan.fixtures_per_club == 2 * (n_clubs - 1)))
    if not double_round_robin_ok:
        bad = [plan.clubs[i] for i in np.flatnonzero(
            plan.fixtures_per_club != 2 * (n_clubs - 1))]
        failures.append(f"{bad} do not play a complete double round-robin")

    # --- played fixtures are pinned, not simulated -------------------------
    retained = set(run.retained_rows.fixture_ordinals.tolist())
    pinned = {f.ordinal for f in plan.fixtures if f.result is not None}
    unplayed = {f.ordinal for f in plan.fixtures if f.result is None}
    pinned_ok = not (retained & pinned) and retained == unplayed
    if retained & pinned:
        failures.append(
            f"{len(retained & pinned)} played fixture(s) carry simulated "
            "scorelines: a pinned result was drawn instead of fixed")
    elif retained != unplayed:
        failures.append(
            "the retained and pinned fixtures do not partition the season")

    full = run.full_scorelines()
    for position, fixture in enumerate(plan.fixtures):
        if fixture.result is None:
            continue
        column = full[:, position, :]
        if not (np.all(column[:, 0] == fixture.result[0])
                and np.all(column[:, 1] == fixture.result[1])):
            pinned_ok = False
            failures.append(
                f"{fixture.fixture_id} is played {fixture.result} but the run "
                "does not carry that scoreline in every simulated season")

    # --- the per-season table identities (D10) -----------------------------
    totals = table_mod.accumulate(full, plan.home_idx, plan.away_idx,
                                  n_clubs=n_clubs, adjustments=plan.adjustments)
    rows = run.retained_rows
    identities_ok = True
    try:
        table_mod.check_identities(totals)
    except table_mod.IdentityViolation as exc:
        identities_ok = False
        failures.append(f"table identity: {exc}")
    # the same identities, applied to the rows the run actually PUBLISHES
    if not np.all(rows.gd.astype(np.int64).sum(axis=1) == 0):
        identities_ok = False
        failures.append("the retained goal differences do not sum to zero")
    if not np.array_equal(rows.gf.astype(np.int64).sum(axis=1),
                          totals.ga.astype(np.int64).sum(axis=1)):
        identities_ok = False
        failures.append("the retained goals for do not equal the goals against")

    retained_totals_ok = True
    for name, attribute, array in (("points", "pts", rows.points),
                                   ("goal difference", "gd", rows.gd),
                                   ("goals for", "gf", rows.gf)):
        if not np.array_equal(getattr(totals, attribute), array):
            retained_totals_ok = False
            failures.append(
                f"the retained {name} rows are not what the run's scorelines imply")

    return {
        "arm": run.arm,
        "season": plan.season,
        "cutoff": plan.cutoff,
        "n_sims": plan.n_sims,
        "matrix_row_max_error": row_error,
        "matrix_col_max_error": col_error,
        "market_max_error": float(market_error),
        "market_totals": market_totals,
        "matrix_rows_ok": bool(matrix_rows_ok),
        "matrix_cols_ok": bool(matrix_cols_ok),
        "markets_ok": bool(markets_ok),
        "mass_ok": bool(mass_ok),
        "double_round_robin_ok": bool(double_round_robin_ok),
        "pinned_ok": bool(pinned_ok),
        "identities_ok": bool(identities_ok),
        "retained_totals_ok": bool(retained_totals_ok),
        "failures": failures,
        "PASS": not failures,
    }


def check_run(run: leaguesim.SimRun, *, book=None, post=None, fixtures=None,
              tol: float = DEFAULT_TOL) -> dict:
    """Coherence, plus marginal parity when the arm carries a particle book."""
    report = {"coherence": coherence(run, tol=tol), "marginal_parity": None}
    if book is not None:
        report["marginal_parity"] = marginal_parity(book, post, run, fixtures)
    report["PASS"] = bool(report["coherence"]["PASS"]
                          and (report["marginal_parity"] is None
                               or report["marginal_parity"]["PASS"]))
    return report


# ==========================================================================
# 6. the runnable acceptance set
# ==========================================================================

def _synthetic_book(clubs, n_particles: int = 16) -> particles.ParticleBook:
    """A league-shaped book, so the acceptance run needs no fit.

    The canary and the parity below test the CONDITIONING and the row set, not
    the model: what the strengths are cannot change whether a post-cutoff result
    leaked, and a synthetic book keeps the acceptance run to seconds.
    """
    clubs = tuple(clubs)
    n_teams = len(clubs)
    att = np.repeat(np.linspace(-0.20, 0.20, n_teams)[:, None], n_particles, axis=1)
    defe = att.copy()
    for s in range(n_particles):
        att[s % n_teams, s] += 0.25
    return particles.ParticleBook(
        teams=clubs, idx={c: i for i, c in enumerate(clubs)},
        att=att, defe=defe, mu=np.zeros(n_particles),
        home_adv=np.full(n_particles, 0.25), rho=np.full(n_particles, -0.03),
        sigma_att=np.full(n_particles, 0.4), sigma_def=np.full(n_particles, 0.4),
        provisional=frozenset(), cold_start=frozenset(),
        likelihood="dixon_coles", alpha=0.0,
        max_goals=particles.PRODUCTION_MAX_GOALS, cfg_hash="simcanary-acceptance")


def run_acceptance(cutoffs: dict | None = None, *, matches=None, store=None,
                   n_sims: int = 96, seed: int = 20260611,
                   skip_panel: bool = False) -> dict:
    """The plan's T6 acceptance: leakage + coherence + played-set parity."""
    cutoffs = ACCEPTANCE_CUTOFFS if cutoffs is None else cutoffs
    matches = baseline.load_matches() if matches is None else matches
    store = BitemporalStore(paths.STORE_DIR) if store is None else store

    out: dict[str, dict] = {}
    for label, (season, cutoff) in cutoffs.items():
        builder = archive_state_builder(matches, season)
        state = builder(cutoff, None)
        book = _synthetic_book(state.clubs)
        chunk = max(1, n_sims // 2)
        entry = {
            "leakage": leakage_canary(builder, book, cutoff, seed,
                                      n_sims=n_sims, chunk_size=chunk),
            "coherence": coherence(leaguesim.simulate(
                "dc_native", state, book, n_sims, seed, chunk)),
            "played_set_parity": (
                None if skip_panel
                else played_set_parity(store, cutoff, state, matches)),
        }
        entry["PASS"] = bool(
            entry["leakage"]["PASS"] and entry["coherence"]["PASS"]
            and (entry["played_set_parity"] is None
                 or entry["played_set_parity"]["PASS"]))
        out[label] = entry

    return {"checks": out, "PASS": all(v["PASS"] for v in out.values())}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m epl.simcanary",
        description="Leakage, parity and coherence checks for the table simulator.")
    parser.add_argument("--n-sims", type=int, default=96)
    parser.add_argument("--seed", type=int, default=20260611)
    parser.add_argument("--skip-panel", action="store_true",
                        help="skip the features.build parity (~45s a cutoff)")
    args = parser.parse_args(argv)

    report = run_acceptance(n_sims=args.n_sims, seed=args.seed,
                            skip_panel=args.skip_panel)
    print(leaguesim.canonical_json(report))
    return 0 if report["PASS"] else 1


if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(main())
