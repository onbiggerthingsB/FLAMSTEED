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
    "CONDITIONAL_ARMS", "DEFAULT_N_SIMS", "NULLS", "REFUSAL_KINDS",
    "SANITY_CUTOFFS",
    "SCHEMA_VERSION", "SEASONS", "SEED", "SMOKE_CUTOFFS", "SMOKE_SEASONS",
    "ArchiveRunner", "ArmResult", "CutoffResult", "Realised", "RetroError",
    "UnrecordedHarness", "cutoff_schedule", "harness_hashes",
    "realised_positions", "recorded_harness_versions", "report",
    "check_marker_legality", "requested_cells", "run_retro", "score_retro",
    "weekly_cutoffs",
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

#: Amendment A4 (i): the CLOSED set of reasons a cell can be missing on
#: purpose. A refusal is a fact the RUNNER knows and the scorer does not, so
#: the runner writes it in a typed field and `score_retro` believes nothing
#: else — a row with `not_applicable` text and no `refusal_kind` is a hole.
#: Adding a fifth kind is an amendment, not a code change.
REFUSAL_KINDS = ("excluded_mass_ceiling",     # D11's 2e-2 hard ceiling (A1)
                 "unverified_adjustment",     # a deduction the ledger has not
                                              # checked against the league record
                 "arm_not_defined",           # no such arm here by rule
                 "runner_error")              # anything else — marked, then RAISED

#: Which arms the harness defines CONDITIONALLY, and are therefore the only
#: arms an `arm_not_defined` marker can legally name (Codex review of b5aa609).
#:
#: The kind was validated as a MEMBER of `REFUSAL_KINDS` and never as a claim
#: that could be false. "No such arm here by rule" is a statement about a RULE,
#: and there is exactly one rule of that shape in this harness: `ppg_pointmass`
#: needs `bridge.PPG_MIN_ROUNDS` complete rounds and does not exist before them
#: (prereg §4). Every other arm is defined at every cutoff — `flat` is a
#: constant matrix, and the three simulated arms are the retrospective's whole
#: question — so a marker saying `flat` is "not defined at MW10" is not a
#: refusal, it is a false statement that CLOSES the completeness accounting and
#: certifies a run that lost the comparison it exists to make.
#:
#: The other three kinds are not restricted, and must not be:
#: `unverified_adjustment` and `runner_error` are facts about a season or a
#: failure that can reach any arm, and `excluded_mass_ceiling` is raised at the
#: cell boundary and marked for every arm requested there, nulls included.
CONDITIONAL_ARMS = ("ppg_pointmass",)

#: A4 (iv): the harness pairs this project has recorded, stated in amendment
#: A4 and held against this file by `epl/tests/test_simretro.py`. The list is a
#: DATA file rather than a module constant for one reason: appending a version
#: to `epl/simretro.py` would change this file's own SHA-256 and invalidate the
#: entry being appended.
RETRO_HARNESS_VERSIONS_PATH = Path(__file__).resolve().with_name(
    "retro_harness_versions.json")


class RetroError(RuntimeError):
    """The retrospective refuses to produce or score a number."""


class UnrecordedHarness(RetroError):
    """The running harness pair is not one the ledger records (prereg §12)."""


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
    """Every arm at one (season, cutoff), plus what produced them.

    `refusals` maps an arm the runner DECLINED to a
    ``(refusal_kind, reason)`` pair from :data:`REFUSAL_KINDS`. A4 (i): an arm
    that is neither in `arms` nor in `refusals` was LOST, not refused, and
    `run_retro` writes nothing for it — the accounting then sees an
    undocumented hole, which is the truth. Under v2.1 the caller manufactured a
    marker for any absent arm, so an accidentally dropped `flat` was
    indistinguishable from a null that is undefined by rule.
    """

    clubs: tuple[str, ...]
    arms: dict[str, ArmResult]
    provenance: dict = field(default_factory=dict)
    refusals: dict[str, tuple[str, str]] = field(default_factory=dict)


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
        refusals: dict[str, tuple[str, str]] = {}
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
                # A4 (i): the runner SAYS it declined, and why. `ppg_pointmass`
                # is undefined before three complete rounds (prereg §4), which
                # is a fact this object knows and the scorer cannot infer.
                refusals[null] = (
                    "arm_not_defined",
                    f"{null} is not defined at {cutoff_label}: it needs "
                    f"{bridge_mod.PPG_MIN_ROUNDS} complete rounds and the "
                    f"table has fewer")
                continue
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
                            provenance=provenance, refusals=refusals)

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


def harness_hashes() -> tuple[str, str]:
    """``(sha256 of epl/simretro.py, sha256 of epl/simmetrics.py)``, right now."""
    here = Path(__file__).resolve()
    return (_sha256_file(here), _sha256_file(here.with_name("simmetrics.py")))


def recorded_harness_versions() -> tuple[dict, ...]:
    """Every harness pair this project has RECORDED, oldest first.

    A4 (iv). Prereg §12 and amendments A2-N1 and A2-N2 all say a run whose
    harness hashes match none of the recorded pairs refuses.
    :func:`producer_identity` hashed both files and folded the digest into the
    key — which makes rows from different harnesses non-interchangeable, and is
    worth having — but it never COMPARED them to the recorded pairs, so a fresh
    ledger under an arbitrarily modified harness ran to completion and reported
    nothing unusual. This is the list that sentence is about, and
    `epl/tests/test_simretro.py` fails if it and amendment A4 diverge.
    """
    data = json.loads(RETRO_HARNESS_VERSIONS_PATH.read_text(encoding="utf-8"))
    versions = tuple(data["versions"])
    for entry in versions:
        for key in ("version", "simretro_sha256", "simmetrics_sha256"):
            if not entry.get(key):
                raise RetroError(
                    f"{RETRO_HARNESS_VERSIONS_PATH} has an entry missing {key!r}")
    # Codex review of cdd8879: A VERSION KEY IS UNIQUE. The equality check
    # between this file and amendment A4 collapses both sides into a
    # version-keyed dictionary, and a dictionary silently keeps the last of any
    # duplicate — so a rogue second `v3` pair, inserted before the legitimate
    # one and matching a mutated harness, was overwritten out of the comparison
    # while `run_retro`'s membership test accepted it. The list is what
    # authorises a harness to produce a citable number; a version that names two
    # different harnesses authorises whichever one the reader did not check.
    seen: dict[str, int] = {}
    for entry in versions:
        seen[entry["version"]] = seen.get(entry["version"], 0) + 1
    duplicated = sorted(v for v, n in seen.items() if n > 1)
    if duplicated:
        raise RetroError(
            f"{RETRO_HARNESS_VERSIONS_PATH} records version(s) {duplicated} "
            "more than once. A version key names ONE harness pair: two entries "
            "under one name means the list authorises a pair that is not the "
            "one the amendment ledger states, and the equality check between "
            "the two keeps only the last of them. Give the new pair its own "
            "version, in this file and in amendment A4.")
    return versions


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


def check_marker_legality(kind: str, arm: str, *, where: str) -> None:
    """Refuse a typed marker whose KIND cannot be true of that ARM.

    Codex review of b5aa609. `_refusal_row` validated `kind` against
    :data:`REFUSAL_KINDS` and stopped there — membership, never truth. So a
    runner could label the always-defined `flat` at MW10 `arm_not_defined`, the
    scorer would count it as documented, the completeness identity would close
    and the run would be certified as beating the flat null everywhere while
    the flat null was missing from a cutoff. The one kind that asserts a RULE
    is held against the rules this harness actually has
    (:data:`CONDITIONAL_ARMS`); the other three are facts about a season or a
    failure and can name any arm.

    Raised on the way IN (a runner writing the marker) and on the way OUT (a
    persisted ledger being scored), because a ledger can arrive from a run this
    process did not make.
    """
    if kind == "arm_not_defined" and arm not in CONDITIONAL_ARMS:
        raise RetroError(
            f"{where} `arm_not_defined` for {arm!r}, which this harness defines "
            f"at every cutoff. That kind means 'no such arm here by rule' and "
            f"the only arm(s) with such a rule are {list(CONDITIONAL_ARMS)} "
            f"({bridge_mod.PPG_MIN_ROUNDS} complete rounds, prereg §4). A "
            "marker of this kind for an always-defined arm is not a documented "
            "refusal: it closes the completeness accounting over a cell that "
            "was simply lost, and certifies a comparison that was never made.")


def _refusal_row(*, season, cutoff_label, cutoff, arm, n_sims, seed,
                 kind: str, reason: str) -> dict:
    """A TYPED claim on a key the runner refused, so a resume stays cheap.

    ``ppg_pointmass`` is undefined before three complete rounds, so at MW0 there
    is nothing to write. Without this marker the key would stay missing, and
    every resumed run would pay for the whole cutoff's fit again just to
    rediscover that. `score_retro` skips them when SCORING — they are
    bookkeeping, not forecasts — and reads them for one other thing: they are
    the only evidence the completeness accounting has that a cell is missing on
    purpose rather than lost. So `run_retro` returns them beside the forecasts,
    and a caller that wants forecasts alone filters on `refusal_kind`.

    A4 (i): `refusal_kind` is the load-bearing field and it comes from the
    runner. `not_applicable` is kept beside it, carrying the same text, only so
    that every existing reader that skips on that key — `score_retro`,
    `epl.retro_addendum` — keeps skipping these rows; it is no longer what
    makes a refusal documented, because a v1 ledger has that key and no type.
    """
    if kind not in REFUSAL_KINDS:
        raise RetroError(
            f"{kind!r} is not one of the four refusal kinds A4 fixed "
            f"({', '.join(REFUSAL_KINDS)}); adding a fifth is an amendment")
    check_marker_legality(kind, arm, where="the runner declared")
    producer = producer_identity()
    key = run_key(season, cutoff_label, cutoff, arm, n_sims, seed, producer)
    return {
        "schema_version": SCHEMA_VERSION,
        "producer": producer,
        "run_key": key,
        "envelope_hash": _sha256_json({"run_key": key, "refusal_kind": kind,
                                       "reason": reason}),
        "season": season, "cutoff_label": cutoff_label,
        "cutoff": str(pd.Timestamp(cutoff).normalize().date()),
        "arm": arm, "is_null": bool(arm in NULLS),
        "n_sims": int(n_sims), "seed": int(seed),
        "refusal_kind": kind,
        "reason": reason,
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


def _grid(seasons: Sequence[str] | None, cutoffs: Sequence[str] | None,
          arms: Sequence[str] | None = None, nulls: Sequence[str] | None = None,
          *, smoke: bool) -> tuple[tuple[str, ...], ...]:
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
    arms = tuple(ARMS if arms is None else arms)
    nulls = tuple(NULLS if nulls is None else nulls)
    unknown = [c for c in cutoffs if c not in CUTOFF_LABELS]
    if unknown:
        raise RetroError(f"cutoff label(s) {unknown} are not in the fixed schedule")
    return seasons, cutoffs, arms, nulls


def requested_cells(seasons: Sequence[str] | None = None,
                    cutoffs: Sequence[str] | None = None,
                    arms: Sequence[str] | None = None,
                    nulls: Sequence[str] | None = None, *,
                    smoke: bool = False) -> tuple[tuple[str, str, str], ...]:
    """The (season, cutoff, ARM) triples a :func:`run_retro` call would fill.

    Pass it to :func:`score_retro` as `expected_triples`. A2 (b) defines
    `n_expected` as *the requested cells*, which is a fact about the REQUEST and
    cannot be recovered from the answer: a grid read off the rows that came back
    is satisfied by whatever came back. This is the canonical way to state it,
    computed by the same normalisation :func:`run_retro` applies to the same
    arguments, so the two cannot drift apart.

    A4 (ii) moves the unit from the cell to the TRIPLE. A cell is "present" as
    soon as one arm in it scored; the thing that actually gets lost is an arm,
    and until the unit of the identity is the arm the identity cannot see the
    loss. A2 (b) chose the cell because the refusals it had in mind were
    whole-cell refusals — which are now typed and counted too.

    The whole preregistered schedule is
    ``requested_cells(cutoffs=CUTOFF_LABELS)`` (7 x 6 x 5 = 210 triples); the
    comparison grid alone is ``requested_cells()`` (7 x 5 x 5 = 175).
    """
    seasons, cutoffs, arms, nulls = _grid(seasons, cutoffs, arms, nulls,
                                          smoke=smoke)
    return tuple((season, label, arm)
                 for season in seasons for label in cutoffs
                 for arm in (*arms, *nulls))


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
              allow_legacy_rows: bool = False,
              allow_unrecorded_harness: bool = False,
              verbose: bool = True) -> list[dict]:
    """Run every (season, cutoff, arm) that the ledger does not already hold.

    Append-only and resumable, on the same reasoning as
    ``epl.walkforward.run_walk``: every forecast is a pure function of (season,
    cutoff, arm, n_sims, seed) and the frozen configuration, so a resumed run is
    the same run. Returns the rows for the REQUESTED keys, old and new, in
    request order, INCLUDING the TYPED refusal markers for keys the runner
    refused. Those markers used to be filtered out here, which made
    `score_retro`'s documented-refusal term structurally zero on this path —
    a cell refused on purpose was then indistinguishable from a cell that was
    lost, and the completeness accounting could not close on a correct run.
    The grid the call requests is :func:`requested_cells` with the same
    arguments; pass it to :func:`score_retro` as `expected_triples`.

    Amendment A4 adds four guards, each of which refuses something this
    function used to do silently:

    (i) **Refusals are typed and they come from the runner.** A whole-cell
    failure — season construction, the fit, the simulation — is caught AT THE
    CELL BOUNDARY and a marker of the matching kind is written for every
    requested arm of that cell before anything propagates.
    `excluded_mass_ceiling`, `unverified_adjustment` and `arm_not_defined` are
    expected: the marker is written and the run continues. `runner_error` is
    not: the marker is written **and the exception is re-raised**, so an
    unexplained failure still stops the run. An arm the runner neither returned
    nor refused gets NOTHING — this function no longer writes the alibi.

    (iii) **A producer-less row refuses the run** unless `allow_legacy_rows`;
    an absent `producer` is precisely the v1 schema, and it was the one shape
    the foreign-producer guard exempted.

    (iv) **An unrecorded harness pair refuses the run before any fit** unless
    `allow_unrecorded_harness`. Development and the test suite necessarily run
    under unrecorded hashes and pass it explicitly; it is stamped on every row
    the run writes and printed in the report, and a run that used it is not a
    citable run.

    `runner` is the seam: the default :class:`ArchiveRunner` fits and simulates,
    and a test can substitute a callable with the same keyword signature to
    exercise the ledger without a fit.
    """
    seasons, cutoffs, arms, nulls = _grid(seasons, cutoffs, arms, nulls,
                                          smoke=smoke)

    # A4 (iv), before anything else: prereg §12's invalidation condition, in
    # code rather than in prose. `producer_identity` hashes both harness files
    # into every key and every row, which makes rows from different harnesses
    # non-interchangeable — but it never compared them to the recorded list.
    pair = harness_hashes()
    recorded = recorded_harness_versions()
    unrecorded = pair not in {(v["simretro_sha256"], v["simmetrics_sha256"])
                              for v in recorded}
    if unrecorded and not allow_unrecorded_harness:
        raise UnrecordedHarness(
            f"this harness pair (epl/simretro.py {pair[0][:12]}…, "
            f"epl/simmetrics.py {pair[1][:12]}…) is not one of the "
            f"{len(recorded)} pairs recorded in {RETRO_HARNESS_VERSIONS_PATH.name} "
            f"({', '.join(v['version'] for v in recorded)}). Prereg §12 makes a "
            "run under an unrecorded harness invalid. Record the pair in that "
            "file and in amendment A4, or pass allow_unrecorded_harness=True — "
            "which is recorded on every row this run writes, printed in the "
            "report, and makes the run uncitable.")

    ledger_path = Path(ledger_path or (Path("data/epl/sim") / "retro_ledger.jsonl"))
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    have = {row["run_key"]: row for row in _read_ledger(ledger_path)}

    # A2 (a): refuse a ledger written by another producer, before any fit. The
    # key already makes a foreign row unable to satisfy a request; this stops
    # the run from silently APPENDING to someone else's file and leaving a
    # ledger nobody can describe. The override is explicit and is recorded.
    me = producer_identity()
    foreign = sorted(key for key, row in have.items()
                     if row.get("producer") is not None
                     and row.get("producer") != me)
    legacy = sorted(key for key, row in have.items()
                    if row.get("producer") is None)
    if foreign and not allow_foreign_producer:
        raise RetroError(
            f"{ledger_path} holds {len(foreign)} row(s) written by a different "
            f"producer than this one ({me[:12]}); the first are {foreign[:3]}. "
            "A ledger that mixes producers is one whose rows were computed by "
            "different code and cannot be compared. Re-run into a fresh ledger, "
            "or pass allow_foreign_producer=True to append deliberately — which "
            "is recorded on every row this run writes.")
    if legacy and not allow_legacy_rows:
        raise RetroError(
            f"{ledger_path} holds {len(legacy)} row(s) with no producer at all; "
            f"the first are {legacy[:3]}. That is the v1 schema, and it is the "
            "one shape the foreign-producer guard used to exempt — so a v1 "
            "ledger was appended to silently by a later harness, and the file "
            "ended up holding two producers' rows with nothing recording it. "
            "Re-run into a fresh ledger, or pass allow_legacy_rows=True to "
            "append deliberately — which is recorded on every row this run "
            "writes and printed in the report.")

    need_archive = schedules is None or realised is None or runner is None
    if need_archive and matches is None:
        matches = baseline.load_matches()
    if runner is None:
        runner = ArchiveRunner(matches,
                               require_verified_adjustments=require_verified_adjustments,
                               verbose=verbose)

    def _append(fh, row: dict) -> None:
        if row["run_key"] in have:
            return
        if allow_foreign_producer and foreign:
            row["allow_foreign_producer"] = True
        if allow_legacy_rows and legacy:
            row["allow_legacy_rows"] = True
        if allow_unrecorded_harness and unrecorded:
            row["allow_unrecorded_harness"] = True
        _seal_overrides(row)
        fh.write(json.dumps(row, default=str) + "\n")
        have[row["run_key"]] = row

    def _refuse(season: str, triples, kind: str, reason: str) -> None:
        """Write one typed marker per (label, cutoff, arm) that has no row."""
        with ledger_path.open("a") as fh:
            for label, cutoff, arm in triples:
                _append(fh, _refusal_row(
                    season=season, cutoff_label=label, cutoff=cutoff, arm=arm,
                    n_sims=n_sims, seed=seed, kind=kind, reason=reason))

    def _todo(season: str, label: str, cutoff) -> list[str]:
        return [a for a in (*arms, *nulls)
                if run_key(season, label, cutoff, a, n_sims, seed, me) not in have]

    wanted: list[str] = []
    for season in seasons:
        # The schedule has to resolve first: a marker's key is built from the
        # cutoff DATE, so a failure to resolve the schedule itself has no key
        # to be written under and propagates unmarked. Everything downstream of
        # it — the realised table, the fit, the simulation — is marked.
        schedule = ((schedules or {}).get(season)
                    or cutoff_schedule(matches, season))
        try:
            outcome = ((realised or {}).get(season)
                       or realised_positions(
                           matches, season,
                           require_verified=require_verified_adjustments))
            season_refusal = None
        except Exception as exc:                          # noqa: BLE001 — typed below
            outcome = None
            season_refusal = (_refusal_kind(exc), _refusal_reason(exc))
            # A4 (i): every requested arm of every cutoff of this season is
            # named in the ledger before anything propagates. R1's 2023/24 —
            # `UnverifiedAdjustment`, all six cutoffs — is this case exactly,
            # and it was documented in PROSE by a human because nothing wrote
            # a marker.
            _refuse(season, [(label, schedule[label], arm)
                             for label in cutoffs
                             for arm in _todo(season, label, schedule[label])],
                    *season_refusal)
            if verbose:
                print(f"[retro] {season} refused ({season_refusal[0]})", flush=True)
            if season_refusal[0] == "runner_error":
                raise

        for label in cutoffs:
            cutoff = schedule[label]
            todo = _todo(season, label, cutoff)
            if todo and season_refusal is None:
                if verbose:
                    print(f"[retro] {season} {label} ({pd.Timestamp(cutoff).date()}) "
                          f"-> {len(todo)} arm(s)", flush=True)
                try:
                    result = runner(season=season, cutoff_label=label,
                                    cutoff=cutoff,
                                    arms=tuple(a for a in arms if a in todo),
                                    nulls=tuple(n for n in nulls if n in todo),
                                    n_sims=n_sims, seed=seed)
                    _check_clubs(result, season, label)
                except Exception as exc:                  # noqa: BLE001 — typed here
                    kind = _refusal_kind(exc)
                    _refuse(season, [(label, cutoff, arm) for arm in todo],
                            kind, _refusal_reason(exc))
                    if kind == "runner_error":
                        raise
                    if verbose:
                        print(f"[retro] {season} {label} refused ({kind})",
                              flush=True)
                    result = None

                if result is not None:
                    with ledger_path.open("a") as fh:
                        for arm in todo:
                            got = result.arms.get(arm)
                            if got is not None:
                                _append(fh, _row(
                                    season=season, cutoff_label=label,
                                    cutoff=cutoff, arm=arm, result=got,
                                    clubs=result.clubs, realised=outcome,
                                    seed=seed, provenance=result.provenance,
                                    smoke=smoke))
                                continue
                            told = (result.refusals or {}).get(arm)
                            if told is None:
                                # A4 (i): the runner was not asked whether it
                                # refused and its silence is not an answer. An
                                # arm it simply lost leaves its key unclaimed,
                                # and the accounting reports an undocumented
                                # hole — which is what happened.
                                continue
                            kind, reason = told
                            _append(fh, _refusal_row(
                                season=season, cutoff_label=label, cutoff=cutoff,
                                arm=arm, n_sims=n_sims, seed=seed,
                                kind=kind, reason=reason))

            for arm in (*arms, *nulls):
                key = run_key(season, label, cutoff, arm, n_sims, seed, me)
                if key in have:
                    wanted.append(key)

    return [have[key] for key in wanted]


#: The three flags that record a run made under an explicit override. Named
#: once so the seal below and the report cannot drift from each other.
OVERRIDE_FLAGS = ("allow_foreign_producer", "allow_legacy_rows",
                  "allow_unrecorded_harness")


def _seal_overrides(row: dict) -> dict:
    """Fold the override flags into the row's ``envelope_hash``.

    Codex review of b5aa609 (3). The flags are set AFTER `_row` and
    `_refusal_row` have hashed the envelope, so override provenance — the
    record that a run appended to a foreign or v1 ledger, or ran under a
    harness pair prereg §12 makes invalid — could be added to or removed from
    any row without invalidating a single hash. That provenance is the reason
    the overrides are allowed to exist at all: they are explicit, recorded on
    every row, and printed in the report, and "recorded" has to mean something
    a later edit cannot quietly undo.

    The seal is applied only when a flag is actually set, so an ordinary row's
    hash is exactly what it was; and it is deterministic, so the same run
    resumed writes the same hash.
    """
    overrides = {name: True for name in OVERRIDE_FLAGS if row.get(name)}
    if overrides:
        row["envelope_hash"] = _sha256_json(
            {"envelope_hash": row["envelope_hash"], "overrides": overrides})
    return row


def _refusal_kind(exc: BaseException) -> str:
    """Which of A4's four kinds an exception is, by type and nothing else."""
    if isinstance(exc, particles.ExcludedMassTooLarge):
        return "excluded_mass_ceiling"
    if isinstance(exc, season_mod.UnverifiedAdjustment):
        return "unverified_adjustment"
    return "runner_error"


def _refusal_reason(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


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
        "trps_se_method": ("TRPS MC SE (diagonal approx.): the delta method on "
                           "the cluster-by-particle per-cell SE, keeping only "
                           "the diagonal of the quadratic form. The cross-cell "
                           "covariance is omitted, and because the TRPS "
                           "gradient changes sign within a club's row the "
                           "omitted terms can raise or lower the variance, so "
                           "the direction of the approximation is not known "
                           "(amendment A2-N4)"),
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
                expected_triples: Sequence[tuple[str, str, str]] | None = None,
                ) -> dict:
    """Every metric in plan v2 §5, per (season, cutoff, arm), plus the pairings.

    `expected_triples` is the (season, cutoff, ARM) grid the run was ASKED
    for — :func:`requested_cells` states it. A2 (b) named the unit the cell;
    A4 (ii) makes it the triple, because a cell counts as present as soon as
    one arm in it scored and the thing that gets lost is an arm.

    **An unstated request is not a licence to certify.** v2.1 answered one with
    `None` — *not evaluated* — which is not the same as complete and not the
    same as incomplete. A4 (ii) retires that branch: with no grid supplied this
    scores against the WHOLE preregistered schedule, every season, every cutoff
    label, every arm and null. That is the most demanding grid available, so an
    unstated request can only ever report more missing, never fewer, and a
    casual `score_retro(rows)` on a partial ledger reads incomplete — correctly,
    loudly, and with the fix being to state the grid.

    The identity is over SETS of triples, not counts: the scored triples united
    with the typed refusals must BE the expected set, and no triple may appear
    in both halves — with `n_scored > 0` and zero violations, all required for
    `complete`. Counts cancel and sets do not: a triple carrying both a score
    and a refusal is counted twice by ``n_scored + n_typed_refusals``, paying
    for exactly one undocumented hole elsewhere.

    Only a TYPED marker counts as a refusal (A4 (i)): a row carrying
    `not_applicable` text and no `refusal_kind` is a hole, which is what a v1
    ledger's markers are — and the kind must be one that can be TRUE of the arm
    it names (:func:`check_marker_legality`), or the ledger is refused outright.

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
    #
    # A4 (i): ONLY A TYPED MARKER COUNTS. `not_applicable` text with no
    # `refusal_kind` is a hole: v1 wrote exactly that shape, and under v2.1 so
    # did this module's own caller, for any arm the runner failed to return —
    # including the required `dc_native` and the always-defined `flat`.
    #
    # Codex b5aa609 (2): AND THE KIND MUST BE TRUE OF THE ARM. Membership in
    # `REFUSAL_KINDS` was the whole check, so `flat` at MW10 labelled
    # `arm_not_defined` — of a null that is a constant matrix and is defined
    # everywhere — was counted as documented, closed the identity, and
    # certified a run that had lost the comparison. A ledger can arrive from a
    # run this process did not make, so the rule is applied here as well as at
    # the marker's writing.
    for row in ledger:
        if row.get("refusal_kind") in REFUSAL_KINDS:
            check_marker_legality(row["refusal_kind"], row["arm"],
                                  where=(f"{row['season']} "
                                         f"{row['cutoff_label']} carries"))
    documented = {
        (row["season"], row["cutoff_label"], row["arm"]):
            row.get("reason") or row.get("not_applicable") or ""
        for row in ledger if row.get("refusal_kind") in REFUSAL_KINDS}
    # A4 (i) again: `runner_error` is the one kind that is written AND re-raised,
    # so a ledger that holds one is a ledger whose run did not finish. On resume
    # the key is occupied and the cell is never retried, so the marker's only
    # remaining job is to keep saying so — see the STOP flag below.
    runner_errors = sorted(
        (row["season"], row["cutoff_label"], row["arm"]) for row in ledger
        if row.get("refusal_kind") == "runner_error")
    by_cell: dict[tuple[str, str], set[str]] = {}
    for row in scored:
        by_cell.setdefault((row["season"], row["cutoff_label"]), set()).add(
            row["arm"])
    scored_triples = {(row["season"], row["cutoff_label"], row["arm"])
                      for row in scored}

    # A4 (ii): the grid is the SCHEDULE, on every path. Deriving it from the
    # rows just handed in makes the identity self-satisfying — every row present
    # is a cell expected, so it holds by construction and any subset "closes".
    # Scored through that path the real R1 ledger reported n_expected=34,
    # n_checked=34, n_missing=0, complete=True on a run eight cells short of its
    # preregistered 42. v2.1 answered `None`; A4 answers with the whole
    # preregistered schedule, which cannot flatter a partial ledger.
    if expected_triples is not None:
        expected = {(str(s), str(c), str(a)) for s, c, a in expected_triples}
        expected_source = "supplied by the caller"
    else:
        expected = set(requested_cells(cutoffs=CUTOFF_LABELS))
        expected_source = (
            "NOT SUPPLIED — scored against the whole preregistered schedule "
            f"({len(SEASONS)} seasons x {len(CUTOFF_LABELS)} cutoffs x "
            f"{len(ARMS) + len(NULLS)} arms), which is the most demanding grid "
            "available, so an unstated request can only report MORE missing "
            "and never fewer; pass `expected_triples` (see `requested_cells`) "
            "to be held against what this run actually asked for")

    missing = []
    for season, label, arm in sorted(expected - scored_triples):
        reason = documented.get((season, label, arm))
        missing.append({
            "season": season, "cutoff_label": label, "arm": arm,
            "reason": reason if reason is not None else "absent from the ledger",
            "documented": reason is not None,
        })
    n_scored = len(expected & scored_triples)
    typed_refusals = {t for t in expected if t in documented}
    n_typed_refusals = len(typed_refusals)
    undocumented = [m for m in missing if not m["documented"]]

    # A4 (ii)'s identity, over triples — AND OVER SETS, not counts (Codex
    # review of b5aa609). `n_scored + n_typed_refusals == n_expected` is an
    # accounting identity in cardinality only, and cardinality cancels: a
    # triple carrying BOTH a score and a refusal marker is counted twice, which
    # pays for exactly one undocumented hole somewhere else. Two scored rows
    # plus one refusal that overlaps one of them, against three expected
    # triples, gave 2 + 1 == 3 — identity_holds, complete, and
    # dc_native_beats_flat_everywhere — over a grid with a cell missing. The
    # question is which triples are covered, so that is what is asked: the
    # union must BE the expected set, and no triple may be in both halves.
    n_expected = len(expected)
    scored_in_grid = expected & scored_triples
    overlapping = sorted(scored_in_grid & typed_refusals)
    covered = scored_in_grid | typed_refusals
    identity = covered == expected and not overlapping
    complete = bool(identity and n_scored > 0 and not violations)
    foreign_overrides = sum(1 for r in ledger if r.get("allow_foreign_producer"))
    legacy_overrides = sum(1 for r in ledger if r.get("allow_legacy_rows"))
    unrecorded_overrides = sum(1 for r in ledger
                               if r.get("allow_unrecorded_harness"))

    return {
        "schema_version": SCHEMA_VERSION,
        "metrics_schema_version": simmetrics.SCHEMA_VERSION,
        "trps_reference": simmetrics.TRPS_REFERENCE,
        "n_rows": len(scored),
        "rows": scored,
        "by_cutoff": by_cutoff,
        "comparisons": paired,
        "sanity": {
            "n_expected": int(n_expected),
            "n_expected_source": expected_source,
            "n_scored": int(n_scored),
            "n_cells_compared": int(checked),
            "n_missing": len(missing),
            "missing": missing,
            "n_typed_refusals": int(n_typed_refusals),
            "n_overlapping": len(overlapping),
            "overlapping": [{"season": s, "cutoff_label": c, "arm": a}
                            for s, c, a in overlapping],
            "n_runner_errors": len(runner_errors),
            "runner_errors": [{"season": s, "cutoff_label": c, "arm": a}
                              for s, c, a in runner_errors],
            "identity_holds": bool(identity),
            "complete": complete,
            "n_foreign_producer_overrides": int(foreign_overrides),
            "n_legacy_row_overrides": int(legacy_overrides),
            "n_unrecorded_harness_overrides": int(unrecorded_overrides),
            "dc_native_beats_flat_everywhere": bool(
                checked and not violations and complete),
            "violations": violations,
            # `runner_errors` is here (Codex review of 7b9d7d1, item 2): the
            # marker is written and the exception re-raised, so the run that
            # wrote it stopped — but `run_retro` skips occupied keys on resume,
            # so the next run never retries that cell and the marker becomes a
            # documented refusal that closes the accounting. An unexplained
            # failure stays stop-worthy for as long as it stays in the ledger,
            # whatever the completeness verdict says.
            "STOP_AND_INSPECT": bool(violations or undocumented or overlapping
                                     or runner_errors or not identity),
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
_COLUMNS = ("cutoff", "season", "arm", "TRPS",
            "TRPS MC SE (diagonal approx.)", "flat TRPS", "wTRPS",
            "Brier champ", "Brier top4", "Brier releg", "champ -ln p",
            "pts CRPS", "pts MAE", "cov50", "cov90",
            "mean cell SE", "max cell SE")


#: How many missing triples the report prints in full. Under A4 (ii) an
#: unstated grid is the whole 210-triple schedule, so a casual scoring of a
#: partial ledger names hundreds of holes; the count is always exact and the
#: list is truncated so the sanity block stays readable.
_MISSING_SHOWN = 20


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
        "was not, and TRPS carried no Monte-Carlo error at all. "
        "`TRPS MC SE (diagonal approx.)` is that error: the delta method "
        "applied to the run's own per-cell cluster-by-particle SE, keeping only "
        "the diagonal of the quadratic form. The cross-cell covariance is "
        "omitted, and because the TRPS gradient changes sign within a club's "
        "row the omitted terms can raise or lower the variance, so the "
        "direction of the approximation is not known (amendment A2-N4). It is "
        "`n/a` for the nulls, which record no per-cell error. All of it is "
        "Monte-Carlo error only.",
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
    lines += ["", "## Sanity", "",
              f"- dc_native beats the flat null at every EXPECTED "
              f"(season, cutoff): **{sanity['dc_native_beats_flat_everywhere']}** "
              f"— {sanity['n_scored']} scored + "
              f"{sanity['n_typed_refusals']} typed refusal(s) against "
              f"{sanity['n_expected']} expected (season, cutoff, arm) triples "
              f"({sanity['n_expected_source']}); "
              f"{sanity['n_cells_compared']} cell(s) had both required arms; "
              f"the accounting closes: **{sanity['complete']}**"]
    if sanity["n_missing"]:
        shown = sanity["missing"][:_MISSING_SHOWN]
        rest = sanity["n_missing"] - len(shown)
        lines.append(f"- {sanity['n_missing']} missing triple(s): "
                     + json.dumps(shown)
                     + (f" … and {rest} more" if rest else ""))
    if sanity["n_foreign_producer_overrides"]:
        lines.append(
            f"- **{sanity['n_foreign_producer_overrides']} row(s) were appended "
            "under an explicit foreign-producer override**: this ledger mixes "
            "rows computed by different harness code, on purpose and on record.")
    if sanity["n_legacy_row_overrides"]:
        lines.append(
            f"- **{sanity['n_legacy_row_overrides']} row(s) were appended under "
            "an explicit legacy-rows override**: this ledger already held rows "
            "with no producer at all — the v1 schema — and was appended to "
            "anyway, on purpose and on record.")
    if sanity["n_unrecorded_harness_overrides"]:
        lines.append(
            f"- **{sanity['n_unrecorded_harness_overrides']} row(s) were "
            "produced under an UNRECORDED harness pair**, by explicit override. "
            "Prereg §12 makes such a run invalid: this is **not a citable run**.")
    if sanity["n_overlapping"]:
        lines.append(
            f"- **{sanity['n_overlapping']} triple(s) carry BOTH a score and a "
            "typed refusal**, which is a contradiction: "
            + json.dumps(sanity["overlapping"]))
    if sanity["n_runner_errors"]:
        lines.append(
            f"- **{sanity['n_runner_errors']} `runner_error` marker(s) are in "
            "this ledger**: the run that wrote one did not finish, and a "
            "resumed run skips the occupied key rather than retrying it. The "
            "failure is unexplained until someone explains it: "
            + json.dumps(sanity["runner_errors"]))
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
    ap.add_argument("--allow-legacy-rows", action="store_true",
                    help="append to a ledger that holds producer-less (v1) "
                         "rows; recorded on every row and printed (A4 (iii))")
    ap.add_argument("--allow-unrecorded-harness", action="store_true",
                    help="run under a harness pair the ledger does not record; "
                         "recorded on every row and printed, and the run is "
                         "NOT citable (A4 (iv))")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if not args.smoke:
        raise SystemExit(
            "the full seven-season retrospective is v1.1 R1 (plan v2 §6); "
            "T8 ships the harness and --smoke")

    # The grid is stated by the caller, from the same normalisation the run
    # used, so `score_retro` closes its accounting against what was ASKED for.
    triples = requested_cells(smoke=True)
    rows = run_retro(smoke=True, n_sims=args.n_sims, seed=args.seed,
                     ledger_path=args.ledger, verbose=True,
                     allow_legacy_rows=args.allow_legacy_rows,
                     allow_unrecorded_harness=args.allow_unrecorded_harness)
    scores = score_retro(rows, expected_triples=triples)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report(scores))
    print(f"[retro] {len(rows)} rows -> {out}")
    print(f"[retro] dc_native beats flat everywhere: "
          f"{scores['sanity']['dc_native_beats_flat_everywhere']} "
          f"({scores['sanity']['n_scored']} scored + "
          f"{scores['sanity']['n_typed_refusals']} typed refusal(s) "
          f"of {scores['sanity']['n_expected']} requested triples; "
          f"the accounting closes: {scores['sanity']['complete']})")


if __name__ == "__main__":       # pragma: no cover
    _cli()
