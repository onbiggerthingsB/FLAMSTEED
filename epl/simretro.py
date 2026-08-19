"""The preregistered retrospective: schedule, arms, ledger, scores, report.

Plan v2 §5 fixes what this module does before it produces a number: which
seasons, which cutoffs, which arms, which metrics, and how the comparison is
made. T8 ships the HARNESS and one smoke run; the seven-season run is v1.1 R1,
triggered within seven days of the opener and before any public accuracy claim.
Building it in this order is deliberate — a harness written after the first
result is a harness written by the result.

What is fixed here
------------------
**Seasons** 2019/20-2025/26. 2025/26 is admissible because no market column is
involved: the reason ``epl.windows`` excludes it is odds-coverage bias, which
this question does not touch, so ``allow_excluded=True`` is passed explicitly
and recorded rather than defaulted.

**Cutoffs** ``MW0`` is the season's first weekly walk-forward cutoff — the
opener, zero results. ``MWk`` for k in {3, 6, 10, 19} is the EARLIEST weekly
cutoff with at least 10k of the season's fixtures dated before it. ``MW28`` is
computed by the same rule but is a degenerate-case sanity check only and is
excluded from the comparisons: by late March the table has converged and TRPS
is on its way to zero for every arm, so a difference there measures the
calendar rather than the forecast. The weekly grid comes from
``epl.walkforward.matchweek_cutoffs`` so the feature-panel cache hits where it
exists. Note the count is over fixture DATES: it selects which cutoff to stand
at, and is not — anywhere — how the simulator decides a fixture is played.

**Arms** ``dc_native`` (the model), ``dc_wdl_bridge`` (the model's 1X2 through
the empirical scoreline bridge) and ``elo_wdl_bridge`` (frozen Elo through an
ordered-logit head through the same bridge), all through ONE engine and ONE
ranker so the arms differ in exactly one place. Nulls: the flat matrix at every
cutoff, and the points-per-game point mass from MW3 (undefined at the opener).

**Comparison** paired differences per cutoff index across seasons with a
season-block bootstrap, 10,000 resamples, percentile CI. Seven blocks: the
intervals will be wide, and this is a DIAGNOSTIC WITH NO PASS RULE. Shipping
does not depend on it. Two things are hard checks: ``dc_native`` beats the flat
null at every (season, cutoff) — a violation is STOP-and-inspect, not a
finding — and no matrix may violate the coherence conditions.

**Never averaged across cutoffs.** A forecast at the opener and one at
matchweek 19 answer different questions. Every aggregate in :func:`score_retro`
carries its cutoff label and the report prints one line per (cutoff, season,
arm); there is no cross-cutoff headline, by construction.

The ledger
----------
:func:`run_retro` appends one JSONL row per (season, cutoff, arm) and skips a
row it already has, so a crash costs the forecast in flight and nothing else.
The row keeps the position matrix, the consequence markets, the tie
diagnostics, an EXACT histogram of the simulated points and the provenance hash
of the run that produced it — enough for :func:`score_retro` to compute every
metric from the ledger alone, without a rerun and without the multi-gigabyte
retained rows.

    PYTHONPATH=src:. .venv/bin/python -m epl.simretro --smoke
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd

from epl import baseline, bridge as bridge_mod, freeze, leaguesim, particles
from epl import score as score_mod, season as season_mod, simmetrics
from epl import table as table_mod, walkforward

__all__ = [
    "ARMS", "COMPARISON_CUTOFFS", "CUTOFF_LABELS", "DEFAULT_COMPARISONS",
    "DEFAULT_N_SIMS", "NULLS", "SANITY_CUTOFFS", "SCHEMA_VERSION", "SEASONS",
    "SEED", "SMOKE_CUTOFFS", "SMOKE_SEASONS", "ArchiveRunner", "ArmResult",
    "CutoffResult", "Realised", "RetroError", "cutoff_schedule",
    "realised_positions", "report", "requested_cells", "run_retro",
    "score_retro", "weekly_cutoffs",
]

SCHEMA_VERSION = "epl-simretro-1"

#: Plan v2 §5. 2025/26 included; `epl.windows`' exclusion is about odds
#: coverage and does not bear on a market-free question.
SEASONS = ("2019/20", "2020/21", "2021/22", "2022/23", "2023/24", "2024/25",
           "2025/26")

CUTOFF_LABELS = ("MW0", "MW3", "MW6", "MW10", "MW19", "MW28")
COMPARISON_CUTOFFS = ("MW0", "MW3", "MW6", "MW10", "MW19")
SANITY_CUTOFFS = ("MW28",)

ARMS = ("dc_native", "dc_wdl_bridge", "elo_wdl_bridge")
NULLS = ("flat", "ppg_pointmass")

DEFAULT_COMPARISONS = (("dc_native", "dc_wdl_bridge"),
                       ("dc_native", "elo_wdl_bridge"))

DEFAULT_N_SIMS = 20_000
SEED = 20260611
N_BOOT = 10_000

#: The T8 smoke run: one season, two cutoffs, every arm and both nulls.
SMOKE_SEASONS = ("2025/26",)
SMOKE_CUTOFFS = ("MW0", "MW10")

#: Fields that measure the clock rather than the result. They are KEPT in the
#: ledger row — how long a fit took is worth recording — and dropped before the
#: provenance hash, so two identical runs on different days agree.
_VOLATILE = ("wall_seconds", "fit_seconds", "seconds")


class RetroError(RuntimeError):
    """The retrospective refuses to produce or score a number."""


# ==========================================================================
# 1. the cutoff schedule (plan v2 §5)
# ==========================================================================

def weekly_cutoffs(matches: pd.DataFrame, season: str) -> list[pd.Timestamp]:
    """The season's weekly walk-forward cutoffs, in order.

    ``allow_excluded=True`` is passed on purpose and stated in this module's
    docstring: 2025/26 is in ``epl.windows.EXCLUDED_SEASONS`` because of odds
    coverage, and no odds enter a league-table score.
    """
    cuts = walkforward.matchweek_cutoffs(matches, score_seasons=(season,),
                                         cadence=1, allow_excluded=True)
    if not cuts:
        raise RetroError(f"no weekly cutoffs for {season}: is it in the archive?")
    return [c.cutoff for c in cuts]


def cutoff_schedule(matches: pd.DataFrame, season: str,
                    labels: Sequence[str] = CUTOFF_LABELS) -> dict[str, pd.Timestamp]:
    """MW0 and each MWk, by the rule — not by a remembered list of dates.

    MW0 is the season's first weekly cutoff. MWk is the earliest weekly cutoff
    with >= 10k of the season's fixtures dated before it. The count is over
    fixture dates because it chooses where to STAND; what is played at that
    cutoff is decided by the results ledger, in :mod:`epl.season`.
    """
    weekly = weekly_cutoffs(matches, season)
    dates = pd.to_datetime(
        matches.loc[(matches["season"] == season) & matches["played"], "date"]
    ).dt.normalize().to_numpy()

    out: dict[str, pd.Timestamp] = {}
    for label in labels:
        if label == "MW0":
            out[label] = weekly[0]
            continue
        if not label.startswith("MW"):
            raise RetroError(f"unknown cutoff label {label!r}")
        need = 10 * int(label[2:])
        chosen = next((c for c in weekly
                       if int((dates < c.to_datetime64()).sum()) >= need), None)
        if chosen is None:
            raise RetroError(
                f"{season} never reaches {need} fixtures before a weekly cutoff; "
                f"{label} is not defined on this archive")
        out[label] = chosen
    return out


# ==========================================================================
# 2. the realised outcome
# ==========================================================================

@dataclass(frozen=True)
class Realised:
    """How a completed season actually finished, through the sim's own ranker."""

    season: str
    position: dict[str, int]
    span: dict[str, int]
    points: dict[str, int]
    adjustments: dict[str, int]
    n_shared: int

    @property
    def clubs(self) -> tuple[str, ...]:
        return tuple(sorted(self.position))

    def position_vector(self, clubs: Sequence[str]) -> np.ndarray:
        missing = [c for c in clubs if c not in self.position]
        if missing:
            raise RetroError(f"the realised table has no position for {missing}")
        return np.array([self.position[c] for c in clubs], dtype=np.int64)

    def points_vector(self, clubs: Sequence[str]) -> np.ndarray:
        return np.array([self.points[c] for c in clubs], dtype=np.int64)


def realised_positions(matches: pd.DataFrame, season: str, *,
                       require_verified: bool = True,
                       adjustments: dict[str, int] | None = None,
                       boundaries=None, rule_id: str | None = None) -> Realised:
    """Final positions and points, from the archive's 380 results.

    The adjustments are the ledger's FINAL state, not a point-in-time snapshot:
    a season is scored against the table it actually finished with. By default
    an unverified row REFUSES — the retrospective must not credit or debit a
    season against a deduction nobody has checked against the league's published
    record (plan v2 D16). Pass `adjustments` to override the ledger entirely;
    that is for tests and for the "what would it be without" control, never for
    a published number.

    A shared finishing position is reported (`n_shared`) rather than silently
    ordered: both clubs take the shared rank, per plan v2 §5.
    """
    boundaries = leaguesim.DEFAULT_BOUNDARIES if boundaries is None else boundaries
    rule_id = leaguesim.DEFAULT_RULE_ID if rule_id is None else rule_id

    frame = matches[(matches["season"] == season) & matches["played"]]
    if frame.empty:
        raise RetroError(f"no played archive rows for {season}")
    results = {(str(r.home_key), str(r.away_key)): (int(r.fthg), int(r.ftag))
               for r in frame.itertuples()}
    if len(results) != len(frame):
        raise RetroError(
            f"{season}: {len(frame)} rows collapse to {len(results)} ordered "
            "pairs — the archive holds a duplicate fixture")

    if adjustments is None:
        rows = season_mod.load_adjustments()
        # the FINAL state: every row this season ever produced is known by now
        adjustments = season_mod.adjustments_at(
            rows, season, pd.Timestamp.max.normalize(),
            require_verified=require_verified)

    placed = table_mod.official_positions_for_realised(
        results, adjustments, boundaries=boundaries, rule_id=rule_id)

    points: dict[str, int] = {club: int(adjustments.get(club, 0))
                              for club, _, _ in placed}
    for (home, away), (hg, ag) in results.items():
        if hg > ag:
            points[home] += 3
        elif hg == ag:
            points[home] += 1
            points[away] += 1
        else:
            points[away] += 3

    return Realised(
        season=season,
        position={club: int(pos) for club, pos, _ in placed},
        span={club: int(span) for club, _, span in placed},
        points=points,
        adjustments=dict(sorted(adjustments.items())),
        n_shared=sum(1 for _, _, span in placed if span > 1),
    )


# ==========================================================================
# 3. what one arm at one cutoff reduces to
# ==========================================================================

@dataclass(frozen=True, eq=False)
class ArmResult:
    """One arm at one cutoff, cut down to what the ledger keeps.

    The engine's retained rows are 20-30 MB per arm per cutoff and belong in
    ``data/epl/sim/``; the ledger keeps the position matrix, the markets, the
    tie diagnostics and an EXACT integer histogram of the simulated points.
    Every metric in plan v2 §5 is computable from that, so `score_retro` never
    needs a rerun.
    """

    matrix: np.ndarray
    matrix_se: np.ndarray | None
    consequences: dict | None
    points: np.ndarray | None
    tie_diagnostics: dict | None
    mc: dict | None
    n_sims: int
    n_particles: int
    digest: str | None
    envelope: dict | None
    is_null: bool = False
    run: Any = None

    @classmethod
    def from_run(cls, run) -> "ArmResult":
        return cls(
            matrix=np.asarray(run.matrix, float),
            matrix_se=np.asarray(run.matrix_se, float),
            consequences=run.consequences,
            points=np.asarray(run.retained_rows.points),
            tie_diagnostics=run.tie_diagnostics,
            mc=run.mc,
            n_sims=int(run.n_sims),
            n_particles=int(run.n_particles),
            digest=run.digest(),
            envelope=run.envelope,
            is_null=False,
            run=run,
        )

    @classmethod
    def from_null(cls, matrix, *, n_sims: int, note: str = "") -> "ArmResult":
        """A null is a matrix and nothing else — no sims, so no Monte-Carlo error."""
        return cls(
            matrix=np.asarray(matrix, float), matrix_se=None, consequences=None,
            points=None, tie_diagnostics=None, mc=None, n_sims=int(n_sims),
            n_particles=0, digest=None,
            envelope={"null": True, "note": note}, is_null=True, run=None)


@dataclass(frozen=True, eq=False)
class CutoffResult:
    """Every arm at one (season, cutoff), plus what produced them."""

    clubs: tuple[str, ...]
    arms: dict[str, ArmResult]
    provenance: dict = field(default_factory=dict)


# ==========================================================================
# 4. the runner that actually fits and simulates
# ==========================================================================

class ArchiveRunner:
    """One fit, three arms and two nulls at one archive cutoff.

    All three arms go through ``leaguesim.simulate`` and ``epl.table``'s ranker,
    so the only thing that differs between them is how a fixture becomes a
    scoreline. The fit runs under ``epl.fit.config_read_once`` exactly as
    ``epl.walkforward`` runs it — verified inert per fit, and the only sanctioned
    monkey-patch in this package.
    """

    def __init__(self, matches: pd.DataFrame | None = None, *,
                 store=None, anchor=None, config: dict | None = None,
                 chunk_size: int = leaguesim.DEFAULT_CHUNK_SIZE,
                 require_verified_adjustments: bool = True,
                 verbose: bool = True):
        from epl import anchor as anchor_mod, fit as epl_fit, freeze
        from epl.schema import sort_for_walk_forward

        self.matches = baseline.load_matches() if matches is None else matches
        self.played = sort_for_walk_forward(self.matches.loc[self.matches["played"]])
        self.config = freeze.frozen_wcmodel_config() if config is None else config
        self.store = epl_fit.build_store(self.played) if store is None else store
        self.anchor = (anchor_mod.Anchor(self.played, freeze.frozen_elo_config())
                       if anchor is None else anchor)
        self.chunk_size = int(chunk_size)
        self.require_verified_adjustments = bool(require_verified_adjustments)
        self.verbose = bool(verbose)
        self._epl_fit = epl_fit

    # ---- the fit --------------------------------------------------------
    def _fit(self, cutoff):
        from epl import dcfit, paths

        with self._epl_fit.config_read_once(self.config):
            post, info = dcfit.fit_epl(cutoff, self.store, self.anchor, self.config,
                                       matches=self.played,
                                       feature_cache_dir=paths.FIT_CACHE_DIR)
        return post, info

    # ---- one cutoff -----------------------------------------------------
    def __call__(self, *, season: str, cutoff_label: str, cutoff,
                 arms: Sequence[str], nulls: Sequence[str], n_sims: int,
                 seed: int) -> CutoffResult:
        started = time.perf_counter()
        cutoff = pd.Timestamp(cutoff).normalize()
        state = season_mod.archive_season_state(
            self.matches, season, cutoff,
            require_verified_adjustments=self.require_verified_adjustments)

        post, info = self._fit(cutoff)
        book = particles.ParticleBook.from_posterior(post)
        missing = [c for c in state.clubs if c not in book.idx]
        if missing:
            raise RetroError(
                f"{season} {cutoff_label}: the posterior cannot price {missing}")

        bridge = None
        if {"dc_wdl_bridge", "elo_wdl_bridge"} & set(arms):
            bridge = bridge_mod.EmpiricalBridge.fit(self.played, cutoff)

        out: dict[str, ArmResult] = {}
        for arm in arms:
            provider = self._provider(arm, book, bridge, state, cutoff)
            run = leaguesim.simulate(arm, state, provider, n_sims, seed,
                                     chunk_size=self.chunk_size,
                                     n_particles=book.n_particles)
            table_mod.check_doubly_stochastic(run.matrix)
            out[arm] = ArmResult.from_run(run)
            if self.verbose:
                print(f"[retro] {season} {cutoff_label} {arm} "
                      f"{run.envelope.get('wall_seconds', 0):.1f}s", flush=True)

        for null in nulls:
            matrix = self._null(null, state)
            if matrix is None:
                continue                     # ppg is undefined before MW3
            table_mod.check_doubly_stochastic(matrix)
            out[null] = ArmResult.from_null(matrix, n_sims=n_sims, note=null)

        provenance = {
            "cold_start_teams": list(info.cold_start_teams),
            "provisional_teams": list(info.provisional_teams),
            "n_training_matches": int(info.n_training_matches),
            "anchor_spec": info.anchor_spec,
            "fit_seconds": float(info.seconds),
            "effective_posterior_hash": book.content_hash(),
            "bridge_hash": None if bridge is None else bridge.content_hash(),
            "n_played": len(state.played),
            "n_unresolved": len(state.unresolved),
            "adjustments_known": dict(state.adjustments_known),
            "wall_seconds": round(time.perf_counter() - started, 2),
        }
        return CutoffResult(clubs=tuple(state.clubs), arms=out,
                            provenance=provenance)

    # ---- the arms -------------------------------------------------------
    def _provider(self, arm: str, book, bridge, state, cutoff):
        if arm == "dc_native":
            return book
        if arm == "dc_wdl_bridge":
            return bridge_mod.DCWDLProvider(book, bridge)
        if arm == "elo_wdl_bridge":
            anchor_state = self.anchor.state(cutoff, list(state.clubs))
            return bridge_mod.EloOutcomeProvider.fit(
                anchor_state, self.anchor.history,
                [state.fixtures[fid] for fid in sorted(state.fixtures)],
                bridge, n_particles=book.n_particles)
        raise RetroError(f"unknown arm {arm!r}")

    @staticmethod
    def _null(name: str, state):
        if name == "flat":
            return bridge_mod.flat_matrix(len(state.clubs))
        if name == "ppg_pointmass":
            return bridge_mod.ppg_pointmass(state)
        raise RetroError(f"unknown null {name!r}")


# ==========================================================================
# 5. the ledger
# ==========================================================================

def _canonical(obj) -> str:
    return leaguesim.canonical_json(obj)


def _sha256_json(obj) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def producer_identity(config_hash: str | None = None) -> str:
    """Who is answering — the harness itself, not the question it answers.

    A digest over the harness schema version, the SHA-256 of `epl/simretro.py`
    and `epl/simmetrics.py` as they stand at run time, the metrics schema
    version, and the frozen configuration's identity.

    A2 (a): the v1 key was the question and nothing else, so a ledger written by
    one producer and resumed by another passed its own resume test — the rows it
    kept were stale, the rows it appended were fresh, the file marked neither and
    nothing stopped. The `envelope_hash` that would have caught it is on every
    row and was never consulted at resume time. Putting the producer IN the key
    makes the mix impossible by construction rather than detectable in principle.
    """
    return _sha256_json({
        "schema": SCHEMA_VERSION,
        "metrics_schema": simmetrics.SCHEMA_VERSION,
        "simretro_sha256": _sha256_file(Path(__file__).resolve()),
        "simmetrics_sha256": _sha256_file(
            Path(__file__).resolve().with_name("simmetrics.py")),
        "config": config_hash or _sha256_json(freeze.frozen_wcmodel_config()),
    })


def run_key(season: str, cutoff_label: str, cutoff, arm: str, n_sims: int,
            seed: int, producer: str | None = None) -> str:
    """What identifies a REQUEST **and who answered it**.

    The question — season, cutoff, arm, simulation count, seed — plus the first
    twelve hex of :func:`producer_identity`. The answer's own fingerprint still
    travels beside it as `envelope_hash`; the producer segment is what stops a
    row made by a different harness from satisfying this request at all.
    """
    day = pd.Timestamp(cutoff).normalize().date()
    who = (producer or producer_identity())[:12]
    return (f"{season}|{cutoff_label}|{day}|{arm}|n{int(n_sims)}|s{int(seed)}"
            f"|p{who}")


def _stable(mapping) -> dict:
    """A dict with the clock-measuring fields removed, for hashing."""
    return {k: v for k, v in (mapping or {}).items() if k not in _VOLATILE}


def _not_applicable_row(*, season, cutoff_label, cutoff, arm, n_sims, seed,
                        reason: str) -> dict:
    """A claim on a key the runner declined to fill, so a resume stays cheap.

    ``ppg_pointmass`` is undefined before three complete rounds, so at MW0 there
    is nothing to write. Without this marker the key would stay missing, and
    every resumed run would pay for the whole cutoff's fit again just to
    rediscover that. `score_retro` skips them when SCORING — they are
    bookkeeping, not forecasts — and reads them for one other thing: they are
    the only evidence the completeness accounting has that a cell is missing on
    purpose rather than lost. So `run_retro` returns them beside the forecasts,
    and a caller that wants forecasts alone filters on `not_applicable`.
    """
    producer = producer_identity()
    key = run_key(season, cutoff_label, cutoff, arm, n_sims, seed, producer)
    return {
        "schema_version": SCHEMA_VERSION,
        "producer": producer,
        "run_key": key,
        "envelope_hash": _sha256_json({"run_key": key, "not_applicable": reason}),
        "season": season, "cutoff_label": cutoff_label,
        "cutoff": str(pd.Timestamp(cutoff).normalize().date()),
        "arm": arm, "is_null": True, "n_sims": int(n_sims), "seed": int(seed),
        "not_applicable": reason,
    }


def _row(*, season, cutoff_label, cutoff, arm, result: ArmResult, clubs,
         realised: Realised, seed, provenance, smoke) -> dict:
    producer = producer_identity()
    key = run_key(season, cutoff_label, cutoff, arm, result.n_sims, seed, producer)

    row = {
        "schema_version": SCHEMA_VERSION,
        "metrics_schema_version": simmetrics.SCHEMA_VERSION,
        "producer": producer,
        "run_key": key,
        "envelope_hash": _sha256_json({"run_key": key,
                                       "envelope": _stable(result.envelope),
                                       "provenance": _stable(provenance)}),
        "digest": result.digest,
        "season": season,
        "cutoff_label": cutoff_label,
        "cutoff": str(pd.Timestamp(cutoff).normalize().date()),
        "arm": arm,
        "is_null": bool(result.is_null),
        "smoke": bool(smoke),
        "n_sims": int(result.n_sims),
        "n_particles": int(result.n_particles),
        "seed": int(seed),
        "clubs": list(clubs),
        "matrix": [[float(v) for v in row_] for row_ in np.asarray(result.matrix)],
        "matrix_se": (None if result.matrix_se is None else
                      [[float(v) for v in r] for r in np.asarray(result.matrix_se)]),
        "consequences": result.consequences,
        "points_hist": (None if result.points is None
                        else simmetrics.points_histogram(result.points)),
        "tie_diagnostics": result.tie_diagnostics,
        "mc": result.mc,
        "realised": {
            "position": dict(realised.position),
            "span": dict(realised.span),
            "points": dict(realised.points),
            "adjustments": dict(realised.adjustments),
            "n_shared": int(realised.n_shared),
        },
        "provenance": provenance,
    }
    return row


def _read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _grid(seasons: Sequence[str] | None, cutoffs: Sequence[str] | None, *,
          smoke: bool) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What a request resolves to — ONE definition, used by both callers.

    :func:`run_retro` and :func:`requested_cells` must not be able to disagree
    about what was asked for. The completeness identity in :func:`score_retro`
    is an identity between the grid REQUESTED and the rows that came back; if
    the two sides are normalised by two copies of this logic they can drift,
    and an identity that closes against a drifted grid is the same bug in a new
    place.
    """
    if smoke:
        seasons = SMOKE_SEASONS if seasons is None else seasons
        cutoffs = SMOKE_CUTOFFS if cutoffs is None else cutoffs
    seasons = tuple(SEASONS if seasons is None else seasons)
    cutoffs = tuple(COMPARISON_CUTOFFS if cutoffs is None else cutoffs)
    unknown = [c for c in cutoffs if c not in CUTOFF_LABELS]
    if unknown:
        raise RetroError(f"cutoff label(s) {unknown} are not in the fixed schedule")
    return seasons, cutoffs


def requested_cells(seasons: Sequence[str] | None = None,
                    cutoffs: Sequence[str] | None = None, *,
                    smoke: bool = False) -> tuple[tuple[str, str], ...]:
    """The (season, cutoff) grid a :func:`run_retro` call would be asked to fill.

    Pass it to :func:`score_retro` as `expected_cells`. A2 (b) defines
    `n_expected` as *the requested cells*, which is a fact about the REQUEST and
    cannot be recovered from the answer: a grid read off the rows that came back
    is satisfied by whatever came back. This is the canonical way to state it,
    computed by the same normalisation :func:`run_retro` applies to the same
    arguments, so the two cannot drift apart.

    The whole preregistered grid is ``requested_cells(cutoffs=CUTOFF_LABELS)``
    (42 cells); the comparison grid alone is ``requested_cells()`` (35).
    """
    seasons, cutoffs = _grid(seasons, cutoffs, smoke=smoke)
    return tuple((season, label) for season in seasons for label in cutoffs)


def run_retro(seasons: Sequence[str] | None = None,
              cutoffs: Sequence[str] | None = None,
              arms: Sequence[str] = ARMS,
              nulls: Sequence[str] = NULLS,
              n_sims: int = DEFAULT_N_SIMS,
              seed: int = SEED,
              *,
              smoke: bool = False,
              ledger_path: Path | str | None = None,
              matches: pd.DataFrame | None = None,
              runner: Callable[..., CutoffResult] | None = None,
              schedules: dict[str, dict[str, pd.Timestamp]] | None = None,
              realised: dict[str, Realised] | None = None,
              require_verified_adjustments: bool = True,
              allow_foreign_producer: bool = False,
              verbose: bool = True) -> list[dict]:
    """Run every (season, cutoff, arm) that the ledger does not already hold.

    Append-only and resumable, on the same reasoning as
    ``epl.walkforward.run_walk``: every forecast is a pure function of (season,
    cutoff, arm, n_sims, seed) and the frozen configuration, so a resumed run is
    the same run. Returns the rows for the REQUESTED keys, old and new, in
    request order, INCLUDING the `not_applicable` markers for keys the runner
    declined. Those markers used to be filtered out here, which made
    `score_retro`'s `n_documented_refusals` structurally zero on this path —
    a cell refused on purpose was then indistinguishable from a cell that was
    lost, and the completeness accounting could not close on a correct run.
    The grid the call requests is :func:`requested_cells` with the same
    arguments; pass it to :func:`score_retro` as `expected_cells`.

    `runner` is the seam: the default :class:`ArchiveRunner` fits and simulates,
    and a test can substitute a callable with the same keyword signature to
    exercise the ledger without a fit.
    """
    seasons, cutoffs = _grid(seasons, cutoffs, smoke=smoke)
    arms, nulls = tuple(arms), tuple(nulls)

    ledger_path = Path(ledger_path or (Path("data/epl/sim") / "retro_ledger.jsonl"))
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    have = {row["run_key"]: row for row in _read_ledger(ledger_path)}

    # A2 (a): refuse a ledger written by another producer, before any fit. The
    # key already makes a foreign row unable to satisfy a request; this stops
    # the run from silently APPENDING to someone else's file and leaving a
    # ledger nobody can describe. The override is explicit and is recorded.
    me = producer_identity()
    foreign = sorted(key for key, row in have.items()
                     if row.get("producer") not in (None, me))
    if foreign and not allow_foreign_producer:
        raise RetroError(
            f"{ledger_path} holds {len(foreign)} row(s) written by a different "
            f"producer than this one ({me[:12]}); the first are {foreign[:3]}. "
            "A ledger that mixes producers is one whose rows were computed by "
            "different code and cannot be compared. Re-run into a fresh ledger, "
            "or pass allow_foreign_producer=True to append deliberately — which "
            "is recorded on every row this run writes.")

    need_archive = schedules is None or realised is None or runner is None
    if need_archive and matches is None:
        matches = baseline.load_matches()
    if runner is None:
        runner = ArchiveRunner(matches,
                               require_verified_adjustments=require_verified_adjustments,
                               verbose=verbose)

    wanted: list[str] = []
    for season in seasons:
        schedule = ((schedules or {}).get(season)
                    or cutoff_schedule(matches, season))
        outcome = ((realised or {}).get(season)
                   or realised_positions(
                       matches, season,
                       require_verified=require_verified_adjustments))
        for label in cutoffs:
            cutoff = schedule[label]
            todo = [a for a in (*arms, *nulls)
                    if run_key(season, label, cutoff, a, n_sims, seed, me)
                    not in have]
            if todo:
                if verbose:
                    print(f"[retro] {season} {label} ({pd.Timestamp(cutoff).date()}) "
                          f"-> {len(todo)} arm(s)", flush=True)
                result = runner(season=season, cutoff_label=label, cutoff=cutoff,
                                arms=tuple(a for a in arms if a in todo),
                                nulls=tuple(n for n in nulls if n in todo),
                                n_sims=n_sims, seed=seed)
                _check_clubs(result, season, label)
                with ledger_path.open("a") as fh:
                    for arm in todo:
                        got = result.arms.get(arm)
                        if got is None:
                            # a null the runner declined — claim the key anyway
                            row = _not_applicable_row(
                                season=season, cutoff_label=label, cutoff=cutoff,
                                arm=arm, n_sims=n_sims, seed=seed,
                                reason=f"{arm} is not defined at {label}")
                        else:
                            row = _row(season=season, cutoff_label=label,
                                       cutoff=cutoff, arm=arm, result=got,
                                       clubs=result.clubs, realised=outcome,
                                       seed=seed, provenance=result.provenance,
                                       smoke=smoke)
                        if row["run_key"] in have:
                            continue
                        if allow_foreign_producer and foreign:
                            row["allow_foreign_producer"] = True
                        fh.write(json.dumps(row, default=str) + "\n")
                        have[row["run_key"]] = row

            for arm in (*arms, *nulls):
                key = run_key(season, label, cutoff, arm, n_sims, seed, me)
                if key in have:
                    wanted.append(key)

    return [have[key] for key in wanted]


def _check_clubs(result: CutoffResult, season: str, label: str) -> None:
    n = len(result.clubs)
    for arm, got in result.arms.items():
        matrix = np.asarray(got.matrix, float)
        if matrix.shape != (n, n):
            raise RetroError(
                f"{season} {label} {arm}: matrix is {matrix.shape}, expected "
                f"({n}, {n})")
        table_mod.check_doubly_stochastic(matrix)


# ==========================================================================
# 6. scoring
# ==========================================================================

def _score_one(row: dict) -> dict:
    clubs = list(row["clubs"])
    # A2 (d): both margins, on the way OUT of the ledger. This is the path that
    # turns a stored row into a published number, and it checked row sums only.
    matrix = simmetrics.scored_matrix(row["matrix"], len(clubs))
    row_error, col_error = simmetrics.matrix_margin_errors(matrix)
    realised = row["realised"]
    positions = np.array([int(realised["position"][c]) for c in clubs], np.int64)

    out = {
        "season": row["season"],
        "cutoff_label": row["cutoff_label"],
        "cutoff": row["cutoff"],
        "arm": row["arm"],
        "is_null": bool(row.get("is_null", False)),
        "seed": int(row["seed"]),
        "n_sims": int(row["n_sims"]),
        "run_key": row["run_key"],
        "envelope_hash": row["envelope_hash"],
        "n_shared_realised": int(realised.get("n_shared", 0)),
        "trps": simmetrics.trps(matrix, positions),
        # A2 (c) recorded a TRPS Monte-Carlo error as an open item and put it
        # out of scope for v2; it is supplied here, by the delta method on the
        # run's own per-cell cluster SE, and the deviation from that
        # pre-statement is recorded as a dated note under A2.
        "trps_se": simmetrics.trps_se(matrix, positions, row.get("matrix_se")),
        "trps_se_method": ("delta method on the cluster-by-particle per-cell SE, "
                           "cells treated as independent (conservative: a club's "
                           "row sums to 1, so the neglected covariances are "
                           "predominantly negative)"),
        "matrix_row_max_error": row_error,
        "matrix_col_max_error": col_error,
        "wtrps": simmetrics.wtrps(matrix, positions,
                                  simmetrics.consequence_weights(len(clubs))),
        "flat_trps": simmetrics.flat_trps(positions),
        "briers": simmetrics.consequence_briers(matrix, positions),
        "mc": row.get("mc"),
        "boundary_deciders": (row.get("tie_diagnostics") or {}).get(
            "boundary_deciders"),
    }
    out["beats_flat"] = bool(out["trps"] < out["flat_trps"])

    champion = [c for c in clubs if int(realised["position"][c]) == 1]
    p_champion = float(np.mean([matrix[clubs.index(c), 0] for c in champion]))
    out["champion_logloss"] = simmetrics.champion_logloss_floored(
        p_champion, row["n_sims"])
    out["champion_shared"] = len(champion) > 1

    hist = row.get("points_hist")
    if hist is None:
        out["points"] = None
    else:
        rows = simmetrics.points_from_histogram(hist)
        truth = np.array([int(realised["points"][c]) for c in clubs], np.int64)
        crps = simmetrics.points_crps(rows, truth)
        out["points"] = {
            "crps": float(crps.mean()),
            "crps_per_club": {c: float(v) for c, v in zip(clubs, crps)},
            "mae": simmetrics.points_mae(rows, truth),
            **simmetrics.interval_coverage(rows, truth),
        }
    return out


def score_retro(ledger, *, n_boot: int = N_BOOT,
                comparisons: Sequence[tuple[str, str]] = DEFAULT_COMPARISONS,
                expected_cells: Sequence[tuple[str, str]] | None = None,
                ) -> dict:
    """Every metric in plan v2 §5, per (season, cutoff, arm), plus the pairings.

    `expected_cells` is the (season, cutoff) grid the run was ASKED for —
    :func:`requested_cells` states it. Without it the completeness identity of
    amendment A2 (b) cannot be evaluated, and the sanity block says so rather
    than deriving a grid from the rows it was handed: `n_expected` is `None`,
    `complete` is `None`, `dc_native_beats_flat_everywhere` is `False` and
    `STOP_AND_INSPECT` is `True`.

    Aggregation happens WITHIN a cutoff label and never across labels — an
    opener forecast and a matchweek-19 forecast are different questions and a
    pooled TRPS would describe neither. The paired differences are bootstrapped
    with seasons as blocks; with seven blocks the intervals are wide, which is
    why plan v2 §5 calls this a diagnostic with no pass rule.
    """
    rows = [r for r in ledger if not r.get("not_applicable")]
    if not rows:
        raise RetroError("an empty ledger cannot be scored")
    scored = [_score_one(row) for row in rows]

    by_cutoff: dict[str, dict[str, dict]] = {}
    for row in scored:
        cell = by_cutoff.setdefault(row["cutoff_label"], {}).setdefault(
            row["arm"], {"cutoff_label": row["cutoff_label"], "arm": row["arm"],
                         "seasons": [], "trps": [], "wtrps": [], "flat_trps": []})
        cell["seasons"].append(row["season"])
        for name in ("trps", "wtrps", "flat_trps"):
            cell[name].append(row[name])
    for per_arm in by_cutoff.values():
        for cell in per_arm.values():
            cell["n_seasons"] = len(set(cell["seasons"]))
            cell["n_forecasts"] = len(cell["trps"])
            for name in ("trps", "wtrps", "flat_trps"):
                cell[f"{name}_mean"] = float(np.mean(cell[name]))

    # paired differences, per cutoff index, blocked by season
    occasion = lambda r: (r["season"], r["cutoff_label"], r["cutoff"],  # noqa: E731
                          r["seed"], r["n_sims"])
    index: dict[tuple, dict[str, dict]] = {}
    for row in scored:
        index.setdefault(occasion(row), {})[row["arm"]] = row

    paired: dict[str, dict[str, dict]] = {}
    for label in sorted(by_cutoff):
        here = {k: v for k, v in index.items() if k[1] == label}
        for a, b in comparisons:
            both = [(k, v) for k, v in sorted(here.items()) if a in v and b in v]
            if not both:
                continue
            diffs = np.array([v[a]["trps"] - v[b]["trps"] for _, v in both])
            blocks = [k[0] for k, _ in both]
            cell = {"a": a, "b": b, "n": int(diffs.size),
                    "mean": float(diffs.mean()),
                    "sd": float(diffs.std(ddof=1)) if diffs.size > 1 else 0.0,
                    "metric": "trps"}
            lo, hi, n_blocks = score_mod.block_bootstrap_ci(
                diffs, blocks, n_boot=int(n_boot))
            cell["ci95"] = [lo, hi]
            cell["n_blocks"] = int(n_blocks)
            paired.setdefault(label, {})[f"{a}-{b}"] = cell

    violations = [
        {"season": k[0], "cutoff_label": k[1],
         "dc_native": v["dc_native"]["trps"], "flat": v["flat"]["trps"]}
        for k, v in sorted(index.items())
        if "dc_native" in v and "flat" in v
        and not v["dc_native"]["trps"] < v["flat"]["trps"]]
    checked = sum(1 for v in index.values() if "dc_native" in v and "flat" in v)

    # A2 (b): completeness, not just non-emptiness. `bool(checked and not
    # violations)` reported True on ANY non-empty subset — one surviving cell of
    # a preregistered twenty-eight — because a missing cell is not a violation,
    # it is simply not counted. The flag now requires the accounting to close.
    documented = {}
    for row in ledger:
        if row.get("not_applicable"):
            documented[(row["season"], row["cutoff_label"], row["arm"])] = \
                row["not_applicable"]
    by_cell: dict[tuple[str, str], set[str]] = {}
    for row in scored:
        by_cell.setdefault((row["season"], row["cutoff_label"]), set()).add(
            row["arm"])
    # v2.1: and the grid has to be STATED. Deriving it from the rows just
    # handed in makes the identity self-satisfying — every row present is a cell
    # expected, so `n_checked == n_expected` holds by construction and any
    # subset "closes". Scored through that path the real R1 ledger reported
    # n_expected=34, n_checked=34, complete=True, STOP_AND_INSPECT=False on a
    # run eight cells short of its preregistered 42. The derived cells are still
    # worth reporting — an arm missing INSIDE a cell that IS present is a hole
    # this can see without knowing the grid — but the identity is not evaluated
    # and the flag cannot be True. :func:`requested_cells` states the grid.
    stated = expected_cells is not None
    if stated:
        cells = {(str(s), str(c)) for s, c in expected_cells}
        expected_source = "supplied by the caller"
    else:
        cells = set(by_cell) | {(s, c) for s, c, _a in documented}
        expected_source = ("NOT SUPPLIED — the caller did not state the "
                           "requested grid, so the completeness identity was "
                           "not evaluated and no cell absent from these rows "
                           "can have been noticed; pass `expected_cells` "
                           "(see `requested_cells`) to evaluate it")
    missing = []
    for season, label in sorted(cells):
        present = by_cell.get((season, label), set())
        for arm in ("dc_native", "flat"):
            if arm in present:
                continue
            reason = documented.get((season, label, arm))
            missing.append({
                "season": season, "cutoff_label": label, "arm": arm,
                "reason": reason or "absent from the ledger",
                "documented": reason is not None,
            })
    documented_refusals = len({(m["season"], m["cutoff_label"]) for m in missing
                               if m["documented"]})
    undocumented = [m for m in missing if not m["documented"]]
    # A2 (b)'s identity, evaluated only when there is a request to evaluate it
    # against. `None` is "not evaluated" and is deliberately not `False`: a
    # caller who states no grid has not been told its run is incomplete, it has
    # been told nothing, and the flag below fails closed on that.
    n_expected = len(cells) if stated else None
    complete = (bool(checked + documented_refusals == n_expected
                     and not undocumented) if stated else None)
    overrides = sum(1 for r in ledger if r.get("allow_foreign_producer"))

    return {
        "schema_version": SCHEMA_VERSION,
        "metrics_schema_version": simmetrics.SCHEMA_VERSION,
        "trps_reference": simmetrics.TRPS_REFERENCE,
        "n_rows": len(scored),
        "rows": scored,
        "by_cutoff": by_cutoff,
        "comparisons": paired,
        "sanity": {
            "n_expected": None if n_expected is None else int(n_expected),
            "n_expected_source": expected_source,
            "n_checked": int(checked),
            "n_missing": len(missing),
            "missing": missing,
            "n_documented_refusals": int(documented_refusals),
            "complete": complete,
            "n_foreign_producer_overrides": int(overrides),
            "dc_native_beats_flat_everywhere": bool(
                checked and not violations and complete is True),
            "violations": violations,
            "STOP_AND_INSPECT": bool(violations or undocumented or not stated),
        },
        "never_averaged_across_cutoffs": True,
        "note": ("TRPS is primary and unweighted; wTRPS on the published "
                 "consequence boundaries is secondary; the champion log loss is "
                 "a floored diagnostic. Paired differences are a diagnostic with "
                 "no pass rule (plan v2 §5). Nothing here is a betting signal, "
                 "and a position is not a claim about qualification for any "
                 "competition."),
    }


# ==========================================================================
# 7. the report
# ==========================================================================

#: A2 (c): `MC SE` was `stats_market["se"].mean()` — the MEAN cluster-by-particle
#: error over the club x consequence cells — printed at the right-hand end of a
#: row whose leading number is TRPS and described in the legend as the position
#: matrix's error. It was neither. It is now named for what it is, its maximum
#: is printed beside it, and TRPS carries its own SE.
_COLUMNS = ("cutoff", "season", "arm", "TRPS", "TRPS SE", "flat TRPS", "wTRPS",
            "Brier champ", "Brier top4", "Brier releg", "champ -ln p",
            "pts CRPS", "pts MAE", "cov50", "cov90",
            "mean cell SE", "max cell SE")


def _fmt(value, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def report(scores: dict) -> str:
    """A markdown table per cutoff, one line per (season, arm). Never pooled."""
    lines: list[str] = [
        "# EPL league-table retrospective",
        "",
        f"Metrics: {scores['metrics_schema_version']} · "
        f"harness: {scores['schema_version']}",
        f"Primary score: TRPS (unweighted, 1/(20·19)) — {scores['trps_reference']}.",
        "",
        "Scores are reported per (season, cutoff) and are NEVER averaged across "
        "cutoffs: the opener and matchweek 19 are different questions. "
        "Monte-Carlo error is cluster-by-particle and says nothing about model "
        "error. Positional thresholds are not claims about qualification for "
        "any competition.",
        "",
        "**The error columns.** `mean cell SE` and `max cell SE` are the mean "
        "and the maximum cluster-by-particle Monte-Carlo error over the club x "
        "consequence cells. Neither is an error on TRPS, and neither is the "
        "position matrix's own error (that quantity is `matrix_cluster_se_max` "
        "in the same `mc` block). Under harness v1 the first of them was printed "
        "as `MC SE` beside TRPS and described as the matrix's error, which it "
        "was not, and TRPS carried no Monte-Carlo error at all. `TRPS SE` is "
        "that error: the delta method applied to the run's own per-cell "
        "cluster-by-particle SE, treating a club's cells as independent. They "
        "are not — a club's row sums to 1, so the neglected covariances are "
        "predominantly negative — which makes the reported figure conservative "
        "rather than exact. It is `n/a` for the nulls, which record no per-cell "
        "error. All of it is Monte-Carlo error only.",
        "",
        "| " + " | ".join(_COLUMNS) + " |",
        "|" + "|".join(["---"] * len(_COLUMNS)) + "|",
    ]

    order = {label: i for i, label in enumerate(CUTOFF_LABELS)}
    for row in sorted(scores["rows"],
                      key=lambda r: (order.get(r["cutoff_label"], 99), r["season"],
                                     r["arm"])):
        points = row.get("points") or {}
        mc = row.get("mc") or {}
        lines.append("| " + " | ".join([
            row["cutoff_label"], row["season"], row["arm"],
            _fmt(row["trps"]), _fmt(row.get("trps_se"), 5),
            _fmt(row["flat_trps"]), _fmt(row["wtrps"]),
            _fmt(row["briers"]["champion"], 4),
            _fmt(row["briers"]["top4"], 4),
            _fmt(row["briers"]["relegated"], 4),
            _fmt(row["champion_logloss"]["value"], 3),
            _fmt(points.get("crps"), 2), _fmt(points.get("mae"), 2),
            _fmt(points.get("coverage50"), 2), _fmt(points.get("coverage90"), 2),
            _fmt(mc.get("cluster"), 5), _fmt(mc.get("cluster_se_max"), 5),
        ]) + " |")

    lines += ["", "## Paired differences (TRPS), per cutoff", "",
              "Season-block bootstrap, percentile CI. **Diagnostic, no pass "
              "rule** — shipping does not depend on these intervals.", "",
              "| cutoff | pair | n | mean | CI95 low | CI95 high | blocks |",
              "|---|---|---|---|---|---|---|"]
    for label in sorted(scores["comparisons"], key=lambda l: order.get(l, 99)):
        for name, cell in sorted(scores["comparisons"][label].items()):
            lines.append(
                f"| {label} | {name} | {cell['n']} | {_fmt(cell['mean'], 5)} | "
                f"{_fmt(cell['ci95'][0], 5)} | {_fmt(cell['ci95'][1], 5)} | "
                f"{cell['n_blocks']} |")

    sanity = scores["sanity"]
    expected = ("a grid that was not stated" if sanity["n_expected"] is None
                else f"{sanity['n_expected']} expected")
    closes = ("**NOT EVALUATED** — the requested grid was not stated, so a cell "
              "absent from these rows cannot have been noticed"
              if sanity["complete"] is None else f"**{sanity['complete']}**")
    lines += ["", "## Sanity", "",
              f"- dc_native beats the flat null at every EXPECTED "
              f"(season, cutoff): **{sanity['dc_native_beats_flat_everywhere']}** "
              f"— {sanity['n_checked']} checked + "
              f"{sanity['n_documented_refusals']} documented refusal(s) against "
              f"{expected} ({sanity['n_expected_source']}); "
              f"the accounting closes: {closes}"]
    if sanity["n_missing"]:
        lines.append("- missing cells: " + json.dumps(sanity["missing"]))
    if sanity["n_foreign_producer_overrides"]:
        lines.append(
            f"- **{sanity['n_foreign_producer_overrides']} row(s) were appended "
            "under an explicit foreign-producer override**: this ledger mixes "
            "rows computed by different harness code, on purpose and on record.")
    if sanity["STOP_AND_INSPECT"]:
        lines.append("- **STOP AND INSPECT** — violations: "
                     + json.dumps(sanity["violations"]))
    zero_hits = sum(r["champion_logloss"]["zero_hits"] for r in scores["rows"])
    lines.append(f"- champion log-loss zero hits (floored at 0.5/N): {zero_hits}")
    shared = sum(r["n_shared_realised"] for r in scores["rows"])
    lines.append(f"- shared realised positions across scored seasons: {shared}")
    lines += ["", scores["note"], ""]
    return "\n".join(lines)


# ==========================================================================
# 8. CLI
# ==========================================================================

def _cli(argv: Iterable[str] | None = None) -> None:
    """Run the smoke retrospective and write its markdown table."""
    import argparse

    ap = argparse.ArgumentParser(description=_cli.__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="one season, two cutoffs (the T8 acceptance run)")
    ap.add_argument("--n-sims", type=int, default=DEFAULT_N_SIMS)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--ledger", default="data/epl/sim/retro_smoke.jsonl")
    ap.add_argument("--out", default="data/epl/sim/retro_smoke.md")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if not args.smoke:
        raise SystemExit(
            "the full seven-season retrospective is v1.1 R1 (plan v2 §6); "
            "T8 ships the harness and --smoke")

    # The grid is stated by the caller, from the same normalisation the run
    # used, so `score_retro` closes its accounting against what was ASKED for.
    cells = requested_cells(smoke=True)
    rows = run_retro(smoke=True, n_sims=args.n_sims, seed=args.seed,
                     ledger_path=args.ledger, verbose=True)
    scores = score_retro(rows, expected_cells=cells)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report(scores))
    print(f"[retro] {len(rows)} rows -> {out}")
    print(f"[retro] dc_native beats flat everywhere: "
          f"{scores['sanity']['dc_native_beats_flat_everywhere']} "
          f"({scores['sanity']['n_checked']} checked + "
          f"{scores['sanity']['n_documented_refusals']} documented refusal(s) "
          f"of {scores['sanity']['n_expected']} requested cells; "
          f"the accounting closes: {scores['sanity']['complete']})")


if __name__ == "__main__":       # pragma: no cover
    _cli()
