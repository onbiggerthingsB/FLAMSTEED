"""The engine: one simulated season per particle, and a run you can reproduce.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_leaguesim.py -q

WHAT A RUN IS
-------------
A run is ``n_sims`` simulated seasons. Simulated season ``i`` is drawn under
**one** joint posterior particle, ``i mod S`` (plan v2 D1, D14): the same ``att``,
``def``, ``mu``, ``home_adv`` and ``rho`` price every remaining fixture of that
season, so the cross-fixture correlation a joint posterior carries reaches the
title and relegation tails instead of being averaged away one match at a time.
Stratifying rather than sampling the particle means every draw is used exactly
``n_sims / S`` times: no particle is over- or under-represented by chance, and
the outer (posterior) leg of the Monte-Carlo error is as small as it can be for
that many seasons.

The engine is vectorised across seasons, not across fixtures: for each fixture
it draws one uniform per season and inverts that season's particle's cumulative
scoreline distribution (:mod:`epl.particles` builds those). The scalar
alternative, ``wcmodel.sim.scoreline.sample_score``, is 41-52 us per call — a
measured bottleneck at 380 fixtures x 20,000 seasons, which is why the
vectorised form is the design and not an optimisation (plan v2 D13).

THE RNG CONTRACT (plan v2 D14) — the part that is easy to get quietly wrong
--------------------------------------------------------------------------
Every stream is keyed by ``(chunk_index, fixture_ordinal)`` through
``SeedSequence(seed, spawn_key=(chunk, fixture))``, and the only thing ever
drawn from it is ``Generator.random()`` — uniform doubles. All sampling is
inverse-CDF in this file, so a run depends on the bit generator (pinned to
``PCG64``) and on nothing else about numpy's distribution code.

Three properties follow, and each is asserted in the tests rather than assumed:

* **A played fixture owns a stream it never consumes.** Pinning a result cannot
  shift any other fixture's draws, so the leakage canary (plan v2 T6) is a
  bit-identical comparison and not a statistical one.
* **Fixture order does not matter.** ``fixture_ordinal`` is the rank of the
  fixture id among all 380 of the season's fixtures, fixed by
  :class:`epl.season.Season` at load; it does not move when a fixture is played,
  postponed or re-scheduled.
* **A run is exactly the concatenation of its chunks.** Executing the chunks
  serially, one at a time, or across processes gives byte-identical output.

The chunk size is therefore part of the run's DEFINITION, not an execution
detail: it is in the envelope, and two runs at different chunk sizes are two
different (equally valid) runs, the way two seeds are. What is invariant is the
execution mode.

WHAT COMES OUT, AND WHAT IT IS ALLOWED TO CLAIM
----------------------------------------------
Two products, kept apart (plan v2 D9). The **consequence state** — P(champion),
P(top 4), P(top 5), P(top 7), P(relegated) — is exact under the Handbook ladder
except for the tie mass the rulebook does not resolve, which is reported beside
it. The **display matrix** is 20x20, doubly stochastic, and uses the fractional
shared-slot convention for everything the ladder leaves level. Positions are
positions: "top 4" is a table position and never a claim about qualification for
any competition.

Every headline carries a Monte-Carlo error computed **cluster-by-particle**
(plan v2 D15) — ``sqrt(sum_s (m_s - p)^2 / (S(S-1)))`` over the per-particle
means — because sims sharing a particle are not independent and the binomial
``sqrt(p(1-p)/N)`` the World Cup sim reports would understate the real
uncertainty by an order of magnitude when the posterior draw is what decides the
title. The variance is split into an outer (posterior) and an inner (match
randomness) part, which sum back to the cluster variance exactly.

WHAT IS NOT MODELLED, AND IS SAID SO
------------------------------------
Strengths are frozen at the cutoff: no within-season drift, no injuries, no
January transfers (plan v2 D2, D19-ii). The posterior is mean-field ADVI and is
probably under-dispersed (D19-i). Neither is a defect of this file; both are
written into ``limitations.md`` beside every issuance so no number is quoted
without them.

USING IT
--------
    book = ParticleBook.from_posterior(post)
    run  = simulate("dc_native", state, book, 20_000, seed=20260611)
    write_outputs(run, "data/epl/sim/issuances/2026_27/2026-08-21")

A note on the signature: plan v2 T5 writes ``simulate(arm: ScorelineProvider,
..., book_or_provider, ...)``, which cannot be read literally — the third
parameter is the provider (or the book to build the DC-native one from), and the
first is the arm's NAME, which the envelope and the output filenames need. That
is what is implemented; the arm name is checked against the provider's own
``name`` so the label cannot drift from the thing that produced the numbers.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.metadata as _md
import json
import platform as _platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import repeat
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from epl import freeze, particles, paths, season as season_mod, table as table_mod

__all__ = [
    "AGG_BLOCK", "CUT_LINE_QUANTILES", "DEFAULT_BOUNDARIES", "DEFAULT_CHUNK_SIZE",
    "DEFAULT_RULE_ID", "ENVELOPE_FIELDS", "MARKETS", "NON_REPRODUCIBLE_FIELDS",
    "OUTPUT_SCHEMA_VERSION", "SCHEMA_VERSION", "STREAM_MAPPING", "ChunkRows",
    "DCNativeProvider", "FixturePlan", "ProviderError", "RetainedRows",
    "ScorelineProvider", "SimError", "SimPlan", "SimRun", "canonical_json",
    "cluster_se", "cut_lines", "envelope", "limitations_markdown",
    "market_slices", "particle_index", "resolve_provider", "simulate",
    "simulate_chunk", "streams", "sum_by_particle", "variance_components",
    "write_outputs",
]

#: Bumped when the meaning of a persisted field changes.
SCHEMA_VERSION = "epl-leaguesim-1"
OUTPUT_SCHEMA_VERSION = "epl-simoutput-1"

#: How ``(chunk, fixture)`` becomes a stream. Recorded in the envelope so a
#: future change to the mapping cannot be mistaken for a change in the model.
STREAM_MAPPING = "SeedSequence(seed, spawn_key=(chunk_index, fixture_ordinal))/v1"

#: Plan v2 D14. Part of the run definition, not an execution knob.
DEFAULT_CHUNK_SIZE = 2000

#: Sims per pass of the aggregation loop. A CONSTANT, deliberately independent of
#: ``chunk_size``: it fixes the order the per-particle sums accumulate in, so
#: serial, chunked and parallel runs agree bit for bit and not merely closely.
AGG_BLOCK = 2048

#: The 2026/27 ladder, mirrored from ``epl/season/2026_27/manifest.json``. A test
#: asserts the two are equal, so the season snapshot stays the source of truth
#: and this is only a default for callers that have no manifest (the archive).
DEFAULT_BOUNDARIES = ((1, 2), (4, 5), (5, 6), (6, 7), (7, 8), (17, 18))
DEFAULT_RULE_ID = (
    "PL-2026-27:C4-C7+C17;material={1|2,4|5,5|6,6|7,7|8,17|18};"
    "h2h_away=original_set;unresolved=fractional;v1")

#: The published consequence markets (plan v2 D9). Positional thresholds only —
#: no competition is named here or anywhere downstream.
MARKETS = ("champion", "top4", "top5", "top7", "relegated")

#: Quantiles reported for each cut line. ``method="lower"`` throughout, so every
#: number quoted is a points total some simulated season actually reached.
CUT_LINE_QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)

#: Envelope keys, frozen. `test_envelope_has_every_required_field` asserts the
#: built envelope carries exactly these, so a field cannot be dropped in a
#: refactor without a test failing.
ENVELOPE_FIELDS = (
    "anchor_spec", "arm", "arviz_version", "bridge_hash", "chunk_size", "cutoff",
    "effective_posterior_hash", "epl_tree_sha256", "fixtures_base_sha256",
    "frozen_config_sha256", "git_commit", "git_dirty",
    "kickoff_amendments_sha256", "manifest_sha256", "material_boundaries",
    "max_goals", "n_particles", "n_played", "n_sims", "n_unplayed",
    "n_unresolved", "numpy_version", "observed_by", "output_schema_version",
    "platform", "points_adjustments_applied", "points_adjustments_sha256",
    "provider_hash", "pymc_version", "python_version", "results_lag",
    "results_snapshot_sha256", "results_sources", "rng_algorithm",
    "schema_version", "scipy_version", "season", "seed", "stream_mapping",
    "tiebreak_rule_id", "uv_lock_sha256", "wall_seconds", "widening_mode",
)

#: The only envelope fields that legitimately differ between two runs of the
#: same specification. :meth:`SimRun.digest` drops them.
NON_REPRODUCIBLE_FIELDS = ("wall_seconds",)


class SimError(RuntimeError):
    """Anything the engine refuses to run."""


class ProviderError(SimError):
    """A scoreline provider returned something the engine will not accept."""


# ==========================================================================
# the RNG contract
# ==========================================================================

def streams(seed: int, chunk: int, fixture_ordinal: int) -> np.random.Generator:
    """The generator for one ``(chunk, fixture)`` cell.

    Independent of every other cell and of the order cells are visited in, which
    is what lets a played fixture hold a stream it never draws from and lets the
    chunks be computed in any order or in any process.
    """
    seq = np.random.SeedSequence(int(seed),
                                 spawn_key=(int(chunk), int(fixture_ordinal)))
    return np.random.Generator(np.random.PCG64(seq))


def particle_index(n_sims: int, n_particles: int) -> np.ndarray:
    """``int16[n_sims]``: which posterior draw prices each simulated season.

    ``i mod S`` — stratified, not sampled (plan v2 D14, Codex P1-6). Every draw
    is used ``floor`` or ``ceil`` of ``n_sims / S`` times and never a random
    number of times, so the outer Monte-Carlo leg carries no needless variance.
    """
    if n_sims <= 0 or n_particles <= 0:
        raise SimError("n_sims and n_particles must both be positive")
    if n_particles > np.iinfo(np.int16).max:
        raise SimError("particle ids are int16; more than 32767 draws is out of contract")
    return (np.arange(n_sims, dtype=np.int64) % n_particles).astype(np.int16)


def sum_by_particle(values: np.ndarray, lo: int, n_particles: int) -> np.ndarray:
    """Sum ``values[i]`` into bucket ``(lo + i) % n_particles``.

    The straightforward form is ``np.add.at``, which is slow enough to dominate
    the aggregation pass. Because the particle assignment is the cyclic ``i mod
    S``, rows that share a particle are exactly ``S`` apart, so padding to a
    multiple of ``S`` and reshaping turns the whole scatter into one strided sum.
    The tests pin it against the slow form, offset included.
    """
    values = np.asarray(values, float)
    n = values.shape[0]
    tail = values.shape[1:]
    flat = values.reshape(n, -1)
    pad = (-n) % n_particles
    if pad:
        flat = np.concatenate(
            [flat, np.zeros((pad, flat.shape[1]), float)], axis=0)
    grouped = flat.reshape(-1, n_particles, flat.shape[1]).sum(axis=0)
    return np.roll(grouped, lo % n_particles, axis=0).reshape((n_particles,) + tail)


# ==========================================================================
# Monte-Carlo error, cluster-by-particle (plan v2 D15)
# ==========================================================================

def cluster_se(values, particle) -> float:
    """``sqrt(sum_s (m_s - p)^2 / (S(S-1)))`` for one scalar quantity.

    `values` is one number per simulated season and `particle` says which
    posterior draw priced it. Seasons sharing a particle are NOT independent, so
    the binomial standard error is not the right one; this is the standard
    cluster-robust form with the particle as the cluster.
    """
    values = np.asarray(values, float).ravel()
    particle = np.asarray(particle, np.int64).ravel()
    if values.shape != particle.shape:
        raise SimError("values and particle must line up one-to-one")
    counts = np.bincount(particle)
    sums = np.bincount(particle, weights=values)
    present = counts > 0
    n_clusters = int(present.sum())
    if n_clusters < 2:
        return 0.0
    means = sums[present] / counts[present]
    overall = float(values.mean())
    return float(np.sqrt(((means - overall) ** 2).sum()
                         / (n_clusters * (n_clusters - 1))))


def variance_components(values, particle) -> dict:
    """Split the Monte-Carlo variance of the mean into outer and inner legs.

    outer = ``(B - W/k)/S`` (posterior sampling), inner = ``W/N`` (match
    randomness), with ``B`` the between-particle variance of the cluster means,
    ``W`` the mean within-particle variance and ``k = N/S``. They sum to the
    cluster variance identically — that is the point of writing them this way,
    and it is what makes "we need more particles" and "we need more seasons"
    separable questions (plan v2 D15: convergence is two-dimensional).

    `outer` can come out slightly negative when the true between-particle
    variance is zero; it is reported raw rather than clipped, because a clipped
    variance component silently breaks the identity above.
    """
    values = np.asarray(values, float).ravel()
    particle = np.asarray(particle, np.int64).ravel()
    counts = np.bincount(particle)
    sums = np.bincount(particle, weights=values)
    sq = np.bincount(particle, weights=values ** 2)
    stats = _cluster_stats(sums[:, None], sq[:, None], counts.astype(float),
                           values.size)
    return {name: float(np.asarray(stats[name]).ravel()[0])
            for name in ("mean", "se", "outer", "inner", "between", "within")}


def _cluster_stats(psum, psq, pcount, n_total) -> dict:
    """Cluster statistics for a whole array of cells at once.

    `psum` and `psq` are ``[S, *cells]`` sums and sums of squares by particle,
    `pcount` is ``[S]``. Everything downstream (matrix cells, markets, points)
    goes through this one function so the decomposition cannot drift between
    surfaces.
    """
    psum = np.asarray(psum, float)
    psq = np.asarray(psq, float)
    pcount = np.asarray(pcount, float)
    cells = psum.shape[1:]
    present = pcount > 0
    n_clusters = int(present.sum())
    mean = psum.sum(axis=0) / n_total
    zeros = np.zeros(cells)
    if n_clusters < 2:
        return {"mean": mean, "se": zeros.copy(), "outer": zeros.copy(),
                "inner": zeros.copy(), "between": zeros.copy(),
                "within": zeros.copy(), "n_clusters": n_clusters,
                "within_defined": False}

    counts = pcount[present].reshape((n_clusters,) + (1,) * len(cells))
    means = psum[present] / counts
    between = ((means - mean) ** 2).sum(axis=0) / (n_clusters - 1)

    within_defined = bool(np.all(pcount[present] >= 2))
    if within_defined:
        ss = np.clip(psq[present] - counts * means ** 2, 0.0, None)
        within = (ss / (counts - 1)).mean(axis=0)
    else:
        within = zeros.copy()

    k = n_total / n_clusters
    return {
        "mean": mean,
        "se": np.sqrt(between / n_clusters),
        "outer": (between - within / k) / n_clusters,
        "inner": within / n_total,
        "between": between,
        "within": within,
        "n_clusters": n_clusters,
        "within_defined": within_defined,
    }


# ==========================================================================
# cut lines
# ==========================================================================

def market_slices(n_clubs: int) -> dict[str, tuple[int, int]]:
    """Half-open 0-based position ranges for each consequence market."""
    if n_clubs < 8:
        raise SimError(f"the consequence markets need at least 8 positions, got {n_clubs}")
    return {"champion": (0, 1), "top4": (0, 4), "top5": (0, 5), "top7": (0, 7),
            "relegated": (n_clubs - 3, n_clubs)}


def cut_lines(points, quantiles=CUT_LINE_QUANTILES) -> dict[str, dict[str, int]]:
    """Points needed to finish 1st / 4th / 5th / 17th / 18th, as distributions.

    Sorting each season's points descending gives the points AT each rung
    directly: the ladder is points-first, so the club finishing r-th always holds
    the r-th largest points total whatever broke the tie below it.
    """
    pts = np.asarray(points)
    if pts.ndim != 2:
        raise SimError(f"points must be [N, clubs], got {pts.shape}")
    ranked = -np.sort(-pts, axis=1)
    out: dict[str, dict[str, int]] = {}
    for key, position in (("champion", 1), ("pos4", 4), ("pos5", 5),
                          ("pos17", 17), ("pos18", 18)):
        if position > pts.shape[1]:
            continue
        column = ranked[:, position - 1]
        out[key] = {f"q{int(round(q * 100)):02d}":
                    int(np.quantile(column, q, method="lower"))
                    for q in quantiles}
    return out


# ==========================================================================
# the plan: one immutable description of what a run is
# ==========================================================================

@dataclass(frozen=True)
class FixturePlan:
    """One fixture as the engine sees it. Kickoffs are deliberately absent."""

    fixture_id: str
    ordinal: int
    home_key: str
    away_key: str
    home_idx: int
    away_idx: int
    result: tuple[int, int] | None


@dataclass(frozen=True, eq=False)
class SimPlan:
    """Everything a chunk needs, and nothing that could differ between chunks."""

    season: str
    season_code: str
    cutoff: str
    observed_by: str
    clubs: tuple[str, ...]
    fixtures: tuple[FixturePlan, ...]
    adjustments: np.ndarray
    boundaries: tuple
    rule_id: str
    n_sims: int
    n_particles: int
    seed: int
    chunk_size: int
    n_unresolved: int
    results_lag: bool

    home_idx: np.ndarray = field(init=False, repr=False)
    away_idx: np.ndarray = field(init=False, repr=False)
    unplayed_positions: tuple[int, ...] = field(init=False, repr=False)
    unplayed_index: np.ndarray = field(init=False, repr=False)
    fixtures_per_club: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        set_ = object.__setattr__
        set_(self, "home_idx", np.array([f.home_idx for f in self.fixtures], np.int64))
        set_(self, "away_idx", np.array([f.away_idx for f in self.fixtures], np.int64))
        positions = tuple(i for i, f in enumerate(self.fixtures) if f.result is None)
        set_(self, "unplayed_positions", positions)
        set_(self, "unplayed_index", np.array(positions, np.int64))
        counts = np.zeros(len(self.clubs), np.int64)
        np.add.at(counts, self.home_idx, 1)
        np.add.at(counts, self.away_idx, 1)
        set_(self, "fixtures_per_club", counts)

    # ---- construction ---------------------------------------------------
    @classmethod
    def from_state(cls, state, *, n_sims: int, n_particles: int, seed: int,
                   chunk_size: int = DEFAULT_CHUNK_SIZE, boundaries=None,
                   rule_id: str | None = None) -> "SimPlan":
        """Freeze a `SeasonState` into a plan.

        "Played" comes from the results ledger the state resolved and from
        nowhere else — no kickoff date is read here, which is why moving every
        kickoff in the season leaves the numbers byte-identical (plan v2 D3).
        """
        if n_sims <= 0:
            raise SimError("n_sims must be positive")
        if chunk_size <= 0:
            raise SimError("chunk_size must be positive")
        boundaries = tuple((int(a), int(b)) for a, b in
                           (DEFAULT_BOUNDARIES if boundaries is None else boundaries))
        rule_id = DEFAULT_RULE_ID if rule_id is None else rule_id
        table_mod.check_rule_id(rule_id, boundaries)

        all_ids = tuple(sorted(state.fixtures))
        played, unplayed = set(state.played), set(state.unplayed)
        if played & unplayed:
            raise SimError("a fixture is both played and unplayed in this state")
        if played | unplayed != set(all_ids):
            raise SimError(
                "the state's played and unplayed sets do not cover its fixtures")

        club_index = {club: i for i, club in enumerate(state.clubs)}
        rows = []
        for ordinal, fid in enumerate(all_ids):
            fixture = state.fixtures[fid]
            result = state.played.get(fid)
            if result is not None:
                result = (int(result[0]), int(result[1]))
                if min(result) < 0:
                    raise SimError(f"{fid}: negative goals in the results ledger")
            rows.append(FixturePlan(
                fixture_id=fid, ordinal=ordinal,
                home_key=fixture.home_key, away_key=fixture.away_key,
                home_idx=club_index[fixture.home_key],
                away_idx=club_index[fixture.away_key],
                result=result))

        adjustments = np.zeros(len(state.clubs), np.int16)
        for club, delta in (state.adjustments_known or {}).items():
            adjustments[club_index[club]] = int(delta)

        return cls(
            season=state.season, season_code=state.season_code,
            cutoff=str(state.cutoff), observed_by=str(state.observed_by),
            clubs=tuple(state.clubs), fixtures=tuple(rows),
            adjustments=adjustments, boundaries=boundaries, rule_id=rule_id,
            n_sims=int(n_sims), n_particles=int(n_particles), seed=int(seed),
            chunk_size=int(chunk_size), n_unresolved=len(state.unresolved),
            results_lag=bool(state.results_lag))

    # ---- chunking -------------------------------------------------------
    @property
    def n_chunks(self) -> int:
        return -(-self.n_sims // self.chunk_size)

    def chunk_bounds(self, chunk_index: int) -> tuple[int, int]:
        if not 0 <= chunk_index < self.n_chunks:
            raise SimError(f"chunk {chunk_index} is outside 0..{self.n_chunks - 1}")
        lo = chunk_index * self.chunk_size
        return lo, min(lo + self.chunk_size, self.n_sims)

    # ---- lookups --------------------------------------------------------
    def position_of(self, fixture_id: str) -> int:
        for i, fixture in enumerate(self.fixtures):
            if fixture.fixture_id == fixture_id:
                return i
        raise SimError(f"no fixture {fixture_id!r} in this plan")

    @property
    def n_played(self) -> int:
        return len(self.fixtures) - len(self.unplayed_positions)

    def results_snapshot(self) -> list[list]:
        return [[f.fixture_id, f.result[0], f.result[1]]
                for f in self.fixtures if f.result is not None]


# ==========================================================================
# the arm: how a fixture becomes a scoreline
# ==========================================================================

@runtime_checkable
class ScorelineProvider(Protocol):
    """What an arm has to supply (plan v2 T5/T7).

    ``sample`` is handed one fixture, the particle each season in the chunk is
    priced under, and ``u[3, C]`` uniforms. The slots are a fixed convention so
    the arms share random numbers (plan v2 D18, common random numbers):

        ``u[0]``  the scoreline draw (DC-native) or the outcome draw (bridges)
        ``u[1]``  the mechanism-(c) widening Bernoulli (plan v2 D12)
        ``u[2]``  the bridge's scoreline draw, unused by the DC-native arm

    Plan v2 places this protocol in ``epl/bridge.py``; that module is a later
    task, so it lives here — where the engine that consumes it lives — and
    ``epl.bridge`` will import it rather than declaring a second copy.
    """

    name: str
    n_particles: int

    def sample(self, fixture: FixturePlan, particle_idx: np.ndarray,
               u: np.ndarray) -> tuple[np.ndarray, np.ndarray]: ...

    def content_hash(self) -> str: ...


class DCNativeProvider:
    """The model arm: scorelines straight from the fitted Dixon-Coles grids.

    Per fixture, per simulated season: pick that season's particle's cumulative
    distribution over the 121 scorelines and invert it against ``u[0]``. When
    production would widen the fixture — a provisional club is involved — the
    ``u[1]`` coin sends a share ``alpha`` of the seasons to the max-entropy
    component instead, which is exactly the mixture whose marginal is the
    published production grid (plan v2 D12; the parity is pinned in
    ``epl/tests/test_particles.py``).
    """

    name = "dc_native"

    def __init__(self, book: particles.ParticleBook):
        self.book = book
        self._cdfs: dict[str, particles.FixtureCDF] = {}

    # The CDF cache is derived and large (S x 121 doubles per fixture); it is
    # rebuilt in a worker rather than shipped to it.
    def __getstate__(self) -> dict:
        return {"book": self.book}

    def __setstate__(self, state: dict) -> None:
        self.book = state["book"]
        self._cdfs = {}

    @property
    def n_particles(self) -> int:
        return self.book.n_particles

    def cdf_for(self, fixture: FixturePlan) -> particles.FixtureCDF:
        got = self._cdfs.get(fixture.fixture_id)
        if got is None:
            got = particles.fixture_cdfs(self.book, fixture.home_key, fixture.away_key)
            self._cdfs[fixture.fixture_id] = got
        return got

    def sample(self, fixture, particle_idx, u):
        cdfs = self.cdf_for(fixture)
        rows = cdfs.cdf[particle_idx]            # fancy indexing already copies
        if cdfs.provisional and cdfs.q_cdf is not None:
            widened = u[1] < self.book.alpha
            if widened.any():
                rows[widened] = cdfs.q_cdf
        flat = (rows < u[0][:, None]).sum(axis=1)
        side = self.book.max_goals + 1
        return (flat // side).astype(np.int8), (flat % side).astype(np.int8)

    def content_hash(self) -> str:
        return self.book.content_hash()

    def describe(self) -> dict:
        return {"widening_mode": f"per_fixture_bernoulli@alpha={self.book.alpha:g}",
                "max_goals": int(self.book.max_goals),
                "effective_posterior_hash": self.book.content_hash()}


def resolve_provider(arm: str, book_or_provider) -> ScorelineProvider:
    """A `ParticleBook` becomes the DC-native arm; anything else must be a provider."""
    if isinstance(book_or_provider, particles.ParticleBook):
        if arm != DCNativeProvider.name:
            raise SimError(
                f"a ParticleBook builds the {DCNativeProvider.name!r} arm; "
                f"{arm!r} would label the run as something it is not")
        return DCNativeProvider(book_or_provider)

    provider = book_or_provider
    for attribute in ("sample", "content_hash", "n_particles"):
        if not hasattr(provider, attribute):
            raise ProviderError(
                f"{type(provider).__name__} is not a ScorelineProvider: no {attribute}")
    declared = getattr(provider, "name", None)
    if declared is not None and declared != arm:
        raise SimError(
            f"the run is labelled {arm!r} but the provider calls itself {declared!r}")
    return provider


# ==========================================================================
# one chunk
# ==========================================================================

@dataclass(eq=False)
class ChunkRows:
    """The raw per-season record for one chunk. Concatenating them IS the run."""

    lo: int
    hi: int
    particle: np.ndarray
    scorelines: np.ndarray            # int8[c, unplayed, 2]
    points: np.ndarray
    gd: np.ndarray
    gf: np.ndarray
    block_start: np.ndarray
    block_span: np.ndarray
    resolution_code: np.ndarray
    order: np.ndarray


def simulate_chunk(provider, plan: SimPlan, chunk_index: int) -> ChunkRows:
    """Simulate the seasons in one chunk. Pure in its arguments; process-safe.

    A played fixture is written straight in and its stream is not even created —
    the point of keying streams by ``(chunk, fixture)`` is that this cannot shift
    anything else, and the tests compare byte for byte to prove it.
    """
    lo, hi = plan.chunk_bounds(chunk_index)
    size = hi - lo
    pidx = (np.arange(lo, hi, dtype=np.int64) % plan.n_particles).astype(np.int16)

    scorelines = np.zeros((size, len(plan.fixtures), 2), np.int8)
    max_goals = getattr(getattr(provider, "book", None), "max_goals", None)

    for position, fixture in enumerate(plan.fixtures):
        if fixture.result is not None:
            scorelines[:, position, 0] = fixture.result[0]
            scorelines[:, position, 1] = fixture.result[1]
            continue
        uniforms = streams(plan.seed, chunk_index, fixture.ordinal).random((3, size))
        home_goals, away_goals = provider.sample(fixture, pidx, uniforms)
        home_goals = np.asarray(home_goals)
        away_goals = np.asarray(away_goals)
        if home_goals.shape != (size,) or away_goals.shape != (size,):
            raise ProviderError(
                f"{provider.name} returned {home_goals.shape}/{away_goals.shape} "
                f"for {fixture.fixture_id}, expected ({size},) twice")
        if home_goals.min() < 0 or away_goals.min() < 0:
            raise ProviderError(f"{provider.name} returned negative goals")
        # Fail closed rather than let an out-of-range goal count wrap silently
        # into the int8 store (where it would resurface as "negative goals" two
        # steps later, in a message that points at the wrong thing).
        ceiling = 126 if max_goals is None else max_goals
        if home_goals.max() > ceiling or away_goals.max() > ceiling:
            raise ProviderError(
                f"{provider.name} returned a scoreline past the {ceiling}-goal limit")
        scorelines[:, position, 0] = home_goals
        scorelines[:, position, 1] = away_goals

    totals = table_mod.accumulate(scorelines, plan.home_idx, plan.away_idx,
                                  n_clubs=len(plan.clubs),
                                  adjustments=plan.adjustments)
    table_mod.check_identities(totals)
    ranking = table_mod.rank(totals, scorelines, plan.home_idx, plan.away_idx,
                             plan.boundaries, plan.rule_id)

    return ChunkRows(
        lo=lo, hi=hi, particle=pidx,
        scorelines=np.ascontiguousarray(scorelines[:, plan.unplayed_index, :]),
        points=totals.pts, gd=totals.gd, gf=totals.gf,
        block_start=ranking.block_start, block_span=ranking.block_span,
        resolution_code=ranking.resolution_code, order=ranking.order)


# ==========================================================================
# the retained rows (plan v2 D20)
# ==========================================================================

@dataclass(eq=False)
class RetainedRows:
    """Per-season rows kept so leverage and the change ledger need no rerun.

    Plan v2 D20 fixes the set: the particle each season used, the scoreline of
    every UNPLAYED fixture (a pinned one is a constant of the state and is not
    stored 20,000 times), points/GD/GF, and the tie-block record. `order` is
    kept as well — it costs 20 bytes a season and makes the rows re-rankable
    without recomputing the ladder.
    """

    particle: np.ndarray
    scorelines: np.ndarray
    fixture_ordinals: np.ndarray
    points: np.ndarray
    gd: np.ndarray
    gf: np.ndarray
    block_start: np.ndarray
    block_span: np.ndarray
    resolution_code: np.ndarray
    order: np.ndarray

    _FIELDS = ("particle", "scorelines", "fixture_ordinals", "points", "gd",
               "gf", "block_start", "block_span", "resolution_code", "order")

    @classmethod
    def concatenate(cls, chunks: list[ChunkRows], plan: SimPlan) -> "RetainedRows":
        chunks = sorted(chunks, key=lambda c: c.lo)
        expected = [plan.chunk_bounds(i) for i in range(plan.n_chunks)]
        if [(c.lo, c.hi) for c in chunks] != expected:
            raise SimError("the chunks do not tile the run exactly once")
        stack = lambda name: np.concatenate(  # noqa: E731
            [getattr(c, name) for c in chunks], axis=0)
        ordinals = np.array([plan.fixtures[p].ordinal
                             for p in plan.unplayed_positions], np.int32)
        return cls(
            particle=stack("particle"), scorelines=stack("scorelines"),
            fixture_ordinals=ordinals, points=stack("points"), gd=stack("gd"),
            gf=stack("gf"), block_start=stack("block_start"),
            block_span=stack("block_span"),
            resolution_code=stack("resolution_code"), order=stack("order"))

    def arrays(self) -> dict[str, np.ndarray]:
        return {name: getattr(self, name) for name in self._FIELDS}


# ==========================================================================
# the run
# ==========================================================================

@dataclass(eq=False)
class SimRun:
    """One arm, one cutoff, one seed — with everything needed to check it."""

    arm: str
    plan: SimPlan
    matrix: np.ndarray
    matrix_se: np.ndarray
    shared_mass: np.ndarray
    unresolved_playoff_mass: np.ndarray
    unresolved_multiway_mass: np.ndarray
    consequences: dict
    points_summary: dict
    cut_lines: dict
    tie_diagnostics: dict
    mc: dict
    retained_rows: RetainedRows
    envelope: dict

    @property
    def clubs(self) -> tuple[str, ...]:
        return self.plan.clubs

    @property
    def n_sims(self) -> int:
        return self.plan.n_sims

    @property
    def n_particles(self) -> int:
        return self.plan.n_particles

    def full_scorelines(self) -> np.ndarray:
        """``int8[N, 380, 2]`` — retained rows put back beside the pinned results."""
        out = np.zeros((self.n_sims, len(self.plan.fixtures), 2), np.int8)
        for position, fixture in enumerate(self.plan.fixtures):
            if fixture.result is not None:
                out[:, position, 0] = fixture.result[0]
                out[:, position, 1] = fixture.result[1]
        out[:, self.plan.unplayed_index, :] = self.retained_rows.scorelines
        return out

    def to_json(self) -> dict:
        clubs = self.clubs
        by_club = lambda m: {c: [float(x) for x in m[i]]  # noqa: E731
                             for i, c in enumerate(clubs)}
        return {
            "arm": self.arm,
            "schema_version": SCHEMA_VERSION,
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "season": self.plan.season,
            "cutoff": self.plan.cutoff,
            "clubs": list(clubs),
            "positions": list(range(1, len(clubs) + 1)),
            "n_sims": self.n_sims,
            "n_particles": self.n_particles,
            "products": {
                "consequence_state": (
                    "P(champion), P(top 4), P(top 5), P(top 7), P(relegated) per "
                    "club. Exact under the tiebreak ladder except for the "
                    "unresolved mass reported beside each figure. Positional "
                    "thresholds only: a position is not a claim about "
                    "qualification for any competition."),
                "display_matrix": (
                    "20x20 P(club finishes in position). Clubs the ladder leaves "
                    "level share their positions fractionally (1/k each over the "
                    "block's span); that share is reported separately as "
                    "shared_mass, unresolved_playoff_mass and "
                    "unresolved_multiway_mass. Rows and columns each sum to 1."),
                "uncertainty": (
                    "Every standard error is cluster-by-particle over the "
                    "posterior draws, split into an outer (posterior) and inner "
                    "(match randomness) component. It is Monte-Carlo error "
                    "only, and it is conditional on the approximate posterior "
                    "and on strengths staying fixed for the rest of the season."),
            },
            "matrix": by_club(self.matrix),
            "matrix_se": by_club(self.matrix_se),
            "shared_mass": by_club(self.shared_mass),
            "unresolved_playoff_mass": by_club(self.unresolved_playoff_mass),
            "unresolved_multiway_mass": by_club(self.unresolved_multiway_mass),
            "consequences": self.consequences,
            "points_summary": self.points_summary,
            "cut_lines": self.cut_lines,
            "tie_diagnostics": self.tie_diagnostics,
            "mc": self.mc,
            "envelope": self.envelope,
        }

    def digest(self) -> str:
        """sha256 over everything a rerun must reproduce (wall time excluded)."""
        payload = self.to_json()
        env = {k: v for k, v in payload["envelope"].items()
               if k not in NON_REPRODUCIBLE_FIELDS}
        payload["envelope"] = env
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ==========================================================================
# the engine
# ==========================================================================

def simulate(arm: str, state, book_or_provider, n_sims: int, seed: int,
             chunk_size: int = DEFAULT_CHUNK_SIZE, *, boundaries=None,
             rule_id: str | None = None, season=None, n_particles: int | None = None,
             executor=None) -> SimRun:
    """Run one arm at one cutoff.

    `arm` names the arm ("dc_native", "dc_wdl_bridge", "elo_wdl_bridge");
    `book_or_provider` is a :class:`epl.particles.ParticleBook` (which builds the
    DC-native arm) or any :class:`ScorelineProvider`. `season` is optional and
    only enriches the provenance envelope with the season snapshot's file
    hashes; the numbers do not depend on it.

    Pass `executor` (anything with ``Executor.map``) to compute the chunks in
    parallel. The result is byte-identical to the serial one — the chunks are
    the run's definition, not a scheduling artefact.
    """
    started = time.perf_counter()
    provider = resolve_provider(arm, book_or_provider)

    declared = int(n_particles if n_particles is not None else provider.n_particles)
    book = getattr(provider, "book", None)
    if book is not None and declared != book.n_particles:
        raise SimError(
            f"the run says {declared} particles but the book carries {book.n_particles}")

    plan = SimPlan.from_state(state, n_sims=n_sims, n_particles=declared, seed=seed,
                              chunk_size=chunk_size, boundaries=boundaries,
                              rule_id=rule_id)

    if executor is None:
        chunks = [simulate_chunk(provider, plan, i) for i in range(plan.n_chunks)]
    else:
        chunks = list(executor.map(simulate_chunk, repeat(provider), repeat(plan),
                                   range(plan.n_chunks)))
    rows = RetainedRows.concatenate(chunks, plan)

    aggregate = _aggregate(rows, plan)
    _check_pinned(rows, plan)

    env = envelope(arm=arm, plan=plan, provider=provider, season=season,
                   wall_seconds=time.perf_counter() - started)
    return SimRun(arm=arm, plan=plan, retained_rows=rows, envelope=env, **aggregate)


def _check_pinned(rows: RetainedRows, plan: SimPlan) -> None:
    """Nothing retained may belong to a played fixture (plan v2 D10)."""
    retained = set(rows.fixture_ordinals.tolist())
    pinned = {f.ordinal for f in plan.fixtures if f.result is not None}
    if retained & pinned:
        raise SimError("a played fixture's scorelines were simulated")
    if len(retained) + len(pinned) != len(plan.fixtures):
        raise SimError("the retained and pinned fixtures do not cover the season")


def _aggregate(rows: RetainedRows, plan: SimPlan) -> dict:
    """Turn the raw per-season rows into the published surfaces."""
    n_sims, n_clubs = plan.n_sims, len(plan.clubs)
    if np.any(plan.fixtures_per_club != 2 * (n_clubs - 1)):
        raise SimError("some club does not play a complete double round-robin")

    ranking = table_mod.Ranking(
        block_start=rows.block_start, block_span=rows.block_span,
        resolution_code=rows.resolution_code, order=rows.order,
        boundaries=plan.boundaries, rule_id=plan.rule_id)
    mass = table_mod.position_mass_sums(ranking)
    matrix = mass.matrix / n_sims
    table_mod.check_doubly_stochastic(matrix)

    slices = market_slices(n_clubs)
    n_markets = len(MARKETS)

    psum_m = np.zeros((plan.n_particles, n_clubs, n_clubs))
    psq_m = np.zeros_like(psum_m)
    psum_k = np.zeros((plan.n_particles, n_clubs, n_markets))
    psq_k = np.zeros_like(psum_k)
    psum_p = np.zeros((plan.n_particles, n_clubs))
    psq_p = np.zeros_like(psum_p)
    pcount = np.zeros(plan.n_particles)

    for lo in range(0, n_sims, AGG_BLOCK):
        hi = min(lo + AGG_BLOCK, n_sims)
        block = table_mod.Ranking(
            block_start=rows.block_start[lo:hi], block_span=rows.block_span[lo:hi],
            resolution_code=rows.resolution_code[lo:hi], order=rows.order[lo:hi],
            boundaries=plan.boundaries, rule_id=plan.rule_id)
        cells = table_mod.position_mass(block)
        markets = np.stack([cells[:, :, a:b].sum(axis=2)
                            for a, b in (slices[m] for m in MARKETS)], axis=2)
        pts = rows.points[lo:hi].astype(float)

        psum_m += sum_by_particle(cells, lo, plan.n_particles)
        psq_m += sum_by_particle(cells ** 2, lo, plan.n_particles)
        psum_k += sum_by_particle(markets, lo, plan.n_particles)
        psq_k += sum_by_particle(markets ** 2, lo, plan.n_particles)
        psum_p += sum_by_particle(pts, lo, plan.n_particles)
        psq_p += sum_by_particle(pts ** 2, lo, plan.n_particles)
        pcount += sum_by_particle(np.ones((hi - lo, 1)), lo, plan.n_particles)[:, 0]

    stats_matrix = _cluster_stats(psum_m, psq_m, pcount, n_sims)
    stats_market = _cluster_stats(psum_k, psq_k, pcount, n_sims)
    stats_points = _cluster_stats(psum_p, psq_p, pcount, n_sims)

    drift = float(np.abs(stats_matrix["mean"] - matrix).max())
    if drift > 1e-9:
        raise SimError(
            f"the two accumulation paths disagree by {drift:.3g}; one of them is wrong")

    unresolved = (mass.unresolved_playoff + mass.unresolved_multiway) / n_sims
    consequences: dict[str, dict] = {}
    for i, club in enumerate(plan.clubs):
        cell = {}
        for j, market in enumerate(MARKETS):
            a, b = slices[market]
            cell[market] = {
                "p": float(matrix[i, a:b].sum()),
                "se": float(stats_market["se"][i, j]),
                "unresolved": float(unresolved[i, a:b].sum()),
                "outer": float(stats_market["outer"][i, j]),
                "inner": float(stats_market["inner"][i, j]),
            }
        consequences[club] = cell

    identity = float(np.abs(stats_market["outer"] + stats_market["inner"]
                            - stats_market["se"] ** 2).max())
    counts = np.bincount(rows.particle, minlength=plan.n_particles)
    mc = {
        "cluster": float(stats_market["se"].mean()),
        "outer": float(stats_market["outer"].mean()),
        "inner": float(stats_market["inner"].mean()),
        "cluster_se_max": float(stats_market["se"].max()),
        "matrix_cluster_se_max": float(stats_matrix["se"].max()),
        "identity_max_abs_error": identity,
        "n_particles": int(plan.n_particles),
        "sims_per_particle_min": int(counts.min()),
        "sims_per_particle_max": int(counts.max()),
        "within_particle_variance_defined": bool(stats_market["within_defined"]),
        "note": ("cluster-by-particle standard errors (plan v2 D15); outer is the "
                 "posterior-sampling leg and inner the match-randomness leg, and "
                 "they sum to the cluster variance. Monte-Carlo error only — it "
                 "says nothing about model error."),
    }

    return {
        "matrix": matrix,
        "matrix_se": stats_matrix["se"],
        "shared_mass": mass.shared / n_sims,
        "unresolved_playoff_mass": mass.unresolved_playoff / n_sims,
        "unresolved_multiway_mass": mass.unresolved_multiway / n_sims,
        "consequences": consequences,
        "points_summary": _points_summary(rows.points, stats_points, plan),
        "cut_lines": cut_lines(rows.points),
        "tie_diagnostics": _tie_diagnostics(rows, plan, mass),
        "mc": mc,
    }


def _points_summary(points, stats, plan: SimPlan) -> dict:
    quantiles = (0.05, 0.25, 0.50, 0.75, 0.95)
    out = {}
    for i, club in enumerate(plan.clubs):
        column = points[:, i]
        out[club] = {
            "mean": float(column.mean()),
            "se": float(stats["se"][i]),
            "sd": float(column.std(ddof=1)) if column.size > 1 else 0.0,
            **{f"q{int(round(q * 100)):02d}":
               int(np.quantile(column, q, method="lower")) for q in quantiles},
            "adjustment": int(plan.adjustments[i]),
        }
    return out


def _tie_diagnostics(rows: RetainedRows, plan: SimPlan, mass) -> dict:
    """How often the ladder had to go past goals scored, and where.

    The per-boundary breakdown is the direct test of "do scorelines matter at
    table level" (plan v2 §5 metric 6): a boundary decided on points needs no
    scoreline model at all, one decided on goal difference or head-to-head does.
    """
    n_sims = plan.n_sims
    club_seasons = n_sims * len(plan.clubs)
    codes = np.bincount(rows.resolution_code.ravel(),
                        minlength=len(table_mod.RESOLUTION_NAMES))

    order = rows.order.astype(np.int64)
    at_rung = lambda arr: np.take_along_axis(arr, order, axis=1)  # noqa: E731
    pts, gd, gf = at_rung(rows.points), at_rung(rows.gd), at_rung(rows.gf)
    code_at_rung = at_rung(rows.resolution_code)

    boundaries = {}
    for lo, hi in plan.boundaries:
        if hi > len(plan.clubs):
            continue
        a, b = lo - 1, hi - 1
        decider = np.where(
            pts[:, a] != pts[:, b], table_mod.UNIQUE,
            np.where(gd[:, a] != gd[:, b], table_mod.GD,
                     np.where(gf[:, a] != gf[:, b], table_mod.GF,
                              code_at_rung[:, a])))
        counts = np.bincount(decider.astype(np.int64),
                             minlength=len(table_mod.RESOLUTION_NAMES))
        boundaries[f"{lo}|{hi}"] = {
            name: float(counts[code] / n_sims)
            for code, name in enumerate(table_mod.RESOLUTION_NAMES)}

    return {
        "resolution_code_share": {
            name: float(codes[code] / club_seasons)
            for code, name in enumerate(table_mod.RESOLUTION_NAMES)},
        "shared_position_rate": float((rows.block_span > 1).mean()),
        "unresolved_playoff_mass": float(mass.unresolved_playoff.sum() / n_sims),
        "unresolved_multiway_mass": float(mass.unresolved_multiway.sum() / n_sims),
        "boundary_deciders": boundaries,
        "note": ("boundary_deciders gives, per material boundary, the share of "
                 "simulated seasons in which that boundary was settled by each "
                 "rung of the ladder. UNRESOLVED_* is mass the rulebook does not "
                 "decide and this engine allocates fractionally."),
    }


# ==========================================================================
# provenance (plan v2 D14)
# ==========================================================================

def envelope(*, arm: str, plan: SimPlan, provider, season=None,
             wall_seconds: float | None = None) -> dict:
    """Everything needed to say what produced a number, and to produce it again."""
    book = getattr(provider, "book", None)
    described = provider.describe() if hasattr(provider, "describe") else {}
    files = _season_file_hashes(plan.season, season)
    git = _git_state()

    env = {
        "schema_version": SCHEMA_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "arm": arm,
        # environment
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "epl_tree_sha256": git["epl_tree_sha256"],
        "python_version": _platform.python_version(),
        "numpy_version": np.__version__,
        "scipy_version": _package_version("scipy"),
        "pymc_version": _package_version("pymc"),
        "arviz_version": _package_version("arviz"),
        "platform": _platform.platform(),
        "uv_lock_sha256": _sha256_file(paths.REPO_ROOT / "uv.lock"),
        # the draw
        "rng_algorithm": f"PCG64@numpy-{np.__version__}",
        "stream_mapping": STREAM_MAPPING,
        "seed": int(plan.seed),
        "n_sims": int(plan.n_sims),
        "n_particles": int(plan.n_particles),
        "chunk_size": int(plan.chunk_size),
        # the model
        "effective_posterior_hash": (None if book is None else book.content_hash()),
        "provider_hash": provider.content_hash(),
        "bridge_hash": getattr(provider, "bridge_hash", None),
        "frozen_config_sha256": _sha256_file(freeze.FROZEN_PATH),
        "anchor_spec": _anchor_spec(),
        "max_goals": described.get("max_goals",
                                   None if book is None else int(book.max_goals)),
        "widening_mode": described.get("widening_mode", "none"),
        # the season snapshot
        "season": plan.season,
        "cutoff": plan.cutoff,
        "observed_by": plan.observed_by,
        "manifest_sha256": files["manifest"],
        "fixtures_base_sha256": files["fixtures"],
        "kickoff_amendments_sha256": files["amendments"],
        "results_snapshot_sha256": _sha256_json(plan.results_snapshot()),
        "results_sources": files["results_sources"],
        "points_adjustments_sha256": _sha256_json(
            {club: int(plan.adjustments[i]) for i, club in enumerate(plan.clubs)
             if plan.adjustments[i]}),
        "points_adjustments_applied": {
            club: int(plan.adjustments[i]) for i, club in enumerate(plan.clubs)
            if plan.adjustments[i]},
        "n_played": plan.n_played,
        "n_unplayed": len(plan.unplayed_positions),
        "n_unresolved": int(plan.n_unresolved),
        "results_lag": bool(plan.results_lag),
        # the ladder
        "tiebreak_rule_id": plan.rule_id,
        "material_boundaries": [list(b) for b in plan.boundaries],
        # the run
        "wall_seconds": (None if wall_seconds is None
                         else round(float(wall_seconds), 3)),
    }
    missing = set(ENVELOPE_FIELDS) ^ set(env)
    if missing:
        raise SimError(f"envelope field set drifted from ENVELOPE_FIELDS: {sorted(missing)}")
    return env


@lru_cache(maxsize=1)
def _anchor_spec() -> str | None:
    try:
        return freeze.load_frozen()["anchor_spec"]
    except Exception:                                   # pragma: no cover
        return None


def _package_version(name: str) -> str | None:
    try:
        return _md.version(name)
    except Exception:                                   # pragma: no cover
        module = sys.modules.get(name)
        return getattr(module, "__version__", None)


def _sha256_file(path) -> str | None:
    path = Path(path)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_json(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _season_file_hashes(season_name: str, season=None) -> dict:
    """Hashes of the season snapshot's files, and where the results came from.

    Hashes the vendored fixture file itself rather than quoting the manifest's
    pinned digest: the envelope should record what was on disk, not what a
    manifest says should have been.
    """
    out = {"manifest": None, "fixtures": None, "amendments": None,
           "results_sources": None}
    try:
        manifest = (season.manifest if season is not None
                    else season_mod.load_manifest(season_name))
        directory = (season_mod.SEASON_ROOT
                     / season_mod.season_dir_name(season_name))
        out["manifest"] = _sha256_file(directory / "manifest.json")
        out["fixtures"] = _sha256_file(directory / manifest.fixtures_filename)
        out["amendments"] = _sha256_file(directory / season_mod.AMENDMENTS_FILENAME)
    except Exception:
        pass
    if season is not None:
        out["results_sources"] = sorted(
            {str(row.get("source")) for row in season.results
             if row.get("source") is not None})
    return out


@lru_cache(maxsize=1)
def _git_state() -> dict:
    """Commit, dirty flag, and a content hash of `epl/` when the tree is dirty.

    Cached for the life of the process on purpose: the code that produced a run
    is the code imported at start-up, so re-reading a file that changed halfway
    through would make the envelope describe something that never ran.
    """
    out = {"commit": None, "dirty": None, "epl_tree_sha256": None}
    try:
        def git(*args):
            return subprocess.run(("git",) + args, cwd=paths.REPO_ROOT,
                                  capture_output=True, text=True, timeout=60)

        head = git("rev-parse", "HEAD")
        status = git("status", "--porcelain")
    except Exception:                                   # pragma: no cover
        return out
    if head.returncode == 0:
        out["commit"] = head.stdout.strip() or None
    if status.returncode == 0:
        out["dirty"] = bool(status.stdout.strip())
        if out["dirty"]:
            out["epl_tree_sha256"] = _epl_tree_sha256()
    return out


def _epl_tree_sha256() -> str:
    root = paths.REPO_ROOT / "epl"
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update((_sha256_file(path) or "").encode("utf-8"))
    return digest.hexdigest()


# ==========================================================================
# writing it down
# ==========================================================================

def canonical_json(obj) -> str:
    """Sorted keys, no incidental whitespace, no NaN. Byte-stable across runs."""
    return json.dumps(_plain(obj), sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _plain(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return [_plain(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = sorted(obj) if isinstance(obj, (set, frozenset)) else obj
        return [_plain(x) for x in items]
    if isinstance(obj, (bool, int, float, str)) or obj is None:
        return obj
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def write_outputs(run: SimRun, directory) -> dict[str, Path]:
    """Write the issuance: output json, envelope, retained rows, limitations."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = {
        "output": directory / f"output_{run.arm}.json",
        "envelope": directory / "envelope.json",
        "rows": directory / f"rows_{run.arm}.npz",
        "limitations": directory / "limitations.md",
    }
    written["output"].write_text(canonical_json(run.to_json()) + "\n")
    written["envelope"].write_text(canonical_json(run.envelope) + "\n")
    np.savez_compressed(written["rows"], **run.retained_rows.arrays())
    written["limitations"].write_text(limitations_markdown(run))
    return written


def limitations_markdown(run: SimRun) -> str:
    """The caveats, auto-filled with this run's own numbers.

    Written beside every issuance because the honest version of a league-table
    forecast is inseparable from what it does not model, and a template nobody
    fills in is worse than none.
    """
    env = run.envelope
    playoff = float(run.unresolved_playoff_mass.sum() / len(run.clubs))
    multiway = float(run.unresolved_multiway_mass.sum() / len(run.clubs))
    shared = run.tie_diagnostics["shared_position_rate"]
    worst = max((cell["se"] for club in run.consequences.values()
                 for cell in club.values()), default=0.0)
    generated = _dt.date.today().isoformat()

    return f"""# Limitations — {run.arm}, {run.plan.season} at {run.plan.cutoff}

Written automatically from the run itself ({generated}). Every number this
issuance publishes is subject to all of the following.

## What the forecast is conditional on

* **Strengths are frozen at the cutoff.** No within-season drift, no injuries,
  no manager change, no January transfer window. The forecast is conditional on
  current strengths remaining fixed for the rest of the season (plan v2 D2). The
  correlated within-season error this leaves out is named and unmodelled, not
  estimated.
* **An approximate posterior.** Parameter uncertainty comes from {env['n_particles']}
  mean-field ADVI draws, one joint draw per simulated season. Mean-field ADVI is
  very likely under-dispersed, so the tails here are **conditional on the
  approximate posterior** and are not called honest tails until a
  richer-inference sensitivity has been run (plan v2 D19).
* **Match randomness** is the Dixon-Coles scoreline law, truncated at
  {env['max_goals']} goals per side — the same truncation the published
  per-fixture forecast uses.

## What the rulebook does not decide

* Clubs level after goals scored share their positions fractionally. Mean shared
  positions per simulated season: **{shared * len(run.clubs):.3f}**.
* Mass resting on the play-off convention (two clubs level on a material
  boundary, no model for the play-off): **{playoff:.5f}** per club.
* Mass resting on the three-or-more-way convention, for which the Handbook has
  no rule at all: **{multiway:.5f}** per club.
* Tiebreak rule id: `{env['tiebreak_rule_id']}`.

## The state of the season

* Fixtures played and conditioned on: **{env['n_played']}**; simulated: **{env['n_unplayed']}**.
* Fixtures whose scheduled date has passed with no result recorded
  (simulated either way): **{env['n_unresolved']}**.
* Results lag flag: **{env['results_lag']}**.
* Points adjustments applied: **{env['points_adjustments_applied'] or 'none'}**.

## Monte-Carlo error

* {env['n_sims']} simulated seasons, {env['n_particles']} posterior draws, each used
  {run.mc['sims_per_particle_min']}-{run.mc['sims_per_particle_max']} times.
  Largest cluster-by-particle standard error on any published market:
  **{worst:.4f}**.
* Standard errors are Monte-Carlo only. They do not describe model error, and a
  tight standard error on a badly specified model is still a badly specified
  model.

## What these numbers are not

* "Top 4", "top 5" and "top 7" are **table positions**. They are not claims
  about qualification for any competition.
* There is no betting content here: no odds, no market comparison, no stake.
* The forecast has not been scored against a preregistered retrospective at the
  time of writing; until it has, treat it as a demonstration of the pipeline
  rather than as an accuracy claim.
"""
