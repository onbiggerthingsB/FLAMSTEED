"""Model-neutral arms: an empirical scoreline bridge, an Elo head, two nulls.

Plan v2 T7, and the module that makes plan v2 §0 honest. The v1 claim that a
league-table simulator is "the one surface where the Bayesian machinery is
structurally necessary" was WITHDRAWN: any outcome model plus a scoreline layer
produces a full table, tiebreaks and leverage. This module is that scoreline
layer, and the comparators built on it.

THREE ARMS, ONE ENGINE, ONE RANKER (plan v2 D18)

    dc_native        the model: scorelines straight from the fitted grids
                     (:class:`epl.leaguesim.DCNativeProvider`)
    dc_wdl_bridge    the model's 1X2 only, with the scoreline supplied by the
                     bridge (:class:`DCWDLProvider`)
    elo_wdl_bridge   frozen Elo at the cutoff through an ordered-logit head,
                     with the same bridge (:class:`EloOutcomeProvider`)

The first contrast measures whether native scoreline structure buys anything at
table level; the second measures the outcome model. That is only a measurement
if the arms differ in ONE place, so everything else is shared by construction:
the same season snapshot, the same accumulator, the same Handbook ladder, the
same keyed RNG streams, and — this is the load-bearing one — the same uniforms
in the same slots.

COMMON RANDOM NUMBERS. The engine hands every provider ``u[3, C]`` with a fixed
meaning (:class:`epl.leaguesim.ScorelineProvider`): ``u[0]`` decides the
scoreline (native) or the outcome (bridges), ``u[1]`` is the mechanism-(c)
widening coin, ``u[2]`` is the bridge's scoreline draw. Both bridge arms invert
their 1X2 through the SAME function (:func:`_draw_outcome`) and then call the
same bridge with ``u[2]``, so two arms that agree on a fixture's 1X2 produce the
same scoreline for that fixture in every simulated season — not merely the same
distribution. Paired differences between arms are then differences in the
models, not in the noise.

POINT-IN-TIME. The bridge is an empirical conditional and the Elo head is a
fitted head, which makes both exactly the kind of object that leaks when the
cutoff filter lives in the caller. Both filters live HERE, day-floored
(``date < cutoff.normalize()``) to mirror ``wcmodel.data.features.build``, and
both are attacked by a test that moves a result across the cutoff and demands
the estimate not notice (`epl/tests/test_bridge.py`).

WHAT THE BRIDGE IS, AND IS NOT. ``P(hg, ag | outcome)`` estimated over all valid
played matches before the cutoff — one league-wide conditional, not a
fixture-specific one. It carries no information about which teams are playing
beyond the outcome it is handed. That is the point: it is the cheapest possible
scoreline layer, so if the native-scoreline arm cannot beat it at table level,
the honest product is the cheaper arm and the retrospective says so.

NO BETTING CONTENT. Nothing here reads a price. The Elo arm is a comparator for
accuracy, and the two nulls are floors for the same, nothing else.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from epl import ordlogit, particles, score as score_mod, table as table_mod
from epl.leaguesim import ScorelineProvider, canonical_json

__all__ = [
    "BridgeError", "DCWDLProvider", "DEFAULT_N_PARTICLES", "EloOutcomeProvider",
    "EmpiricalBridge", "MAX_EXCLUDED_SHARE", "MIN_ROWS_PER_OUTCOME",
    "PPG_MIN_ROUNDS", "ScorelineProvider", "flat_matrix", "ppg_pointmass",
]

#: Probability column order, everywhere in this package: home, draw, away.
OUTCOMES = ordlogit.OUTCOMES

#: Below this many pre-cutoff matches in an outcome class the conditional is
#: mostly the accident of which scorelines happened to occur, so `fit` refuses
#: rather than emitting a confident-looking table built on a handful of rows.
#: Real use is never near it: the earliest retrospective cutoff has five full
#: seasons of archive behind it (~1,900 matches, ~470 in the thinnest class).
MIN_ROWS_PER_OUTCOME = 30

#: Share of pre-cutoff matches allowed to fall outside the [0, max_goals]^2
#: grid. Numerically the same 5e-3 as `epl.particles.FLAG_EXCLUDED_MASS`, and
#: for the same reason — past this the sampled law is not the law the rows
#: describe — but it is a HARD refusal and is NOT covered by the D11 v1.0.1
#: amendment: that ruling is about a model tail production also discards, while
#: this is about rows the bridge was fitted on and cannot represent. The
#: 2014/15-2025/26 archive has none.
MAX_EXCLUDED_SHARE = 5e-3

#: How many complete rounds the PPG null needs before it will extrapolate.
#: Undefined at the opener (Codex A4); three is the plan's floor (§5).
PPG_MIN_ROUNDS = 3

#: Particle count the Elo arm declares. It has no posterior, so this is only the
#: stratification grid the engine assigns seasons to (`i mod S`); it is set to
#: the DC arms' S so all three arms give a season the same particle id, which is
#: what lets the cluster-by-particle MC estimator be read across arms. For this
#: arm that estimator is measuring sampling noise and nothing else, because the
#: particle does not enter the law — and its near-zero outer component beside
#: the DC arms' is a fact worth reading, not an artefact to hide.
DEFAULT_N_PARTICLES = 1_000

_BRIDGE_SCHEMA = "epl-empirical-bridge-1"
_ELO_ARM_SCHEMA = "epl-elo-wdl-bridge-1"
_DCWDL_ARM_SCHEMA = "epl-dc-wdl-bridge-1"


class BridgeError(RuntimeError):
    """A bridge, an arm or a null refusing to produce a number it cannot stand behind."""


# ==========================================================================
# the shared inversion — why the arms can be compared at all
# ==========================================================================

def _draw_outcome(probs: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Inverse-CDF one 1X2 draw per simulated season, in :data:`OUTCOMES` order.

    `probs` is ``(C, 3)`` (one row per season) or ``(1, 3)`` (the same law for
    all of them); `u` is ``(C,)``. BOTH bridge arms call this and nothing else,
    which is what makes the common-random-numbers property structural: given
    equal probability rows and equal uniforms the two arms cannot disagree,
    because there is only one implementation to disagree with.

    The rule is ``|{i : cdf[i] <= u}|`` — the smallest ``i`` with ``cdf[i] > u``.
    The last cumulative entry is pinned to exactly 1.0 and ``Generator.random()``
    never returns 1.0, so the index is always in range, and a zero-probability
    class can never be selected however the float arithmetic rounds.
    """
    p = np.atleast_2d(np.asarray(probs, dtype=float))
    if p.shape[1] != 3:
        raise BridgeError(f"1X2 probabilities must be (n, 3); got {p.shape}")
    if not np.isfinite(p).all() or (p < -1e-12).any():
        raise BridgeError("non-finite or negative 1X2 probability")
    total = p.sum(axis=1)
    if not np.allclose(total, 1.0, atol=1e-9):
        raise BridgeError(
            f"1X2 probabilities do not sum to 1 (worst |sum-1| = "
            f"{float(np.max(np.abs(total - 1.0))):.3g})")
    u = np.asarray(u, dtype=float)
    if u.ndim != 1:
        raise BridgeError(f"uniforms must be 1-D; got {u.shape}")
    if u.size and (u.min() < 0.0 or u.max() >= 1.0):
        raise BridgeError("uniforms must lie in [0, 1)")
    cdf = np.cumsum(p, axis=1)
    cdf[:, -1] = 1.0
    return (cdf <= u[:, None]).sum(axis=1)


# ==========================================================================
# the bridge
# ==========================================================================

@dataclass(frozen=True, eq=False)
class EmpiricalBridge:
    """``P(hg, ag | outcome)`` on ``[0, max_goals]^2``, estimated point-in-time.

    Three conditional pmfs — one per outcome class — over the same flat
    scoreline index the particle grids use (``h * (max_goals + 1) + a``). Each
    is supported only on the scorelines that realise its outcome, so a sampled
    scoreline always agrees with the outcome it was drawn for; the arms cannot
    quietly produce a draw for a fixture the outcome model called a home win.

    Estimated, never smoothed: this is the empirical conditional the plan names
    (D18), and a prior on it would be another modelling choice to defend in a
    comparator whose whole job is to be the cheap thing.
    """

    counts: np.ndarray                 #: (3, n^2) int64 — the raw evidence
    max_goals: int
    cutoff: str                        #: ISO day; part of the identity
    n_rows: int                        #: valid pre-cutoff matches read
    n_excluded: int                    #: of those, the ones off the grid

    pmf: np.ndarray = field(init=False, repr=False)
    cdf: np.ndarray = field(init=False, repr=False)
    hash: str = field(init=False)

    def __post_init__(self) -> None:
        counts = np.asarray(self.counts, dtype=np.int64)
        side = int(self.max_goals) + 1
        if counts.shape != (3, side * side):
            raise BridgeError(
                f"counts are {counts.shape}, expected {(3, side * side)} for "
                f"max_goals={self.max_goals}")
        totals = counts.sum(axis=1)
        thin = [OUTCOMES[i] for i, n in enumerate(totals) if n < MIN_ROWS_PER_OUTCOME]
        if thin:
            raise BridgeError(
                f"outcome class(es) {thin} have fewer than {MIN_ROWS_PER_OUTCOME} "
                f"pre-cutoff matches ({dict(zip(OUTCOMES, totals.tolist()))} at "
                f"cutoff {self.cutoff}): the conditional would be the accident of "
                "which scorelines happened, not an estimate of anything")
        pmf = counts / totals[:, None]
        cdf = np.cumsum(pmf, axis=1)
        cdf[:, -1] = 1.0

        set_ = object.__setattr__
        set_(self, "counts", counts)
        set_(self, "pmf", pmf)
        set_(self, "cdf", cdf)
        set_(self, "hash", _sha256_json({
            "schema": _BRIDGE_SCHEMA,
            "cutoff": self.cutoff,
            "max_goals": int(self.max_goals),
            "counts": counts.tolist(),
        }))

    # ---- point-in-time --------------------------------------------------
    def refuse_if_after(self, forecast_cutoff, what: str) -> None:
        """Refuse a bridge estimated LATER than the forecast it would price.

        The conditional is fitted on matches strictly before its own cutoff, so
        a bridge at a later cutoff has read scorelines the forecast cannot see —
        every one of them, in the window between the two dates. That is a leak
        of exactly the kind the whole cutoff apparatus exists to prevent, and it
        is silent: the run completes, the matrix sums to one, and the arm quietly
        knows more about how goals were distributed than its own cutoff allows.

        Day-floored on both sides, matching the `date < cutoff.normalize()` rule
        the fit uses. EQUAL cutoffs are fine and are the normal case: the same
        day-floor means the same evidence.
        """
        mine = pd.Timestamp(self.cutoff).normalize()
        theirs = pd.Timestamp(forecast_cutoff).normalize()
        if mine > theirs:
            raise BridgeError(
                f"the bridge was estimated at {mine.date()} and {what} is "
                f"{theirs.date()}: the bridge has read every scoreline between "
                "those two dates and the forecast cannot see one of them. A "
                "later bridge is a leak, not a refinement — refit it at the "
                "forecast's own cutoff.")

    # ---- construction ---------------------------------------------------
    @classmethod
    def fit(cls, rows, cutoff, *,
            max_goals: int = particles.PRODUCTION_MAX_GOALS) -> "EmpiricalBridge":
        """Estimate the conditional from every valid played match before `cutoff`.

        `rows` is a frame (or a sequence of mappings) carrying a date column
        (``date`` or the ledger's ``date_played``) and goals (``fthg``/``ftag``
        or the ledger's ``hg``/``ag``), so both the archive and a live results
        ledger go in unchanged.

        THE CUTOFF IS AN ARGUMENT, NOT A PROMISE. The caller does not get to
        pre-filter and be trusted: the day-floored ``date < cutoff.normalize()``
        filter is applied here, and the cutoff is part of the content hash, so
        two issuances at different cutoffs can never be mistaken for one bridge
        in an envelope.

        The outcome class is read off the SCORELINE, not off a label. Where a
        label is present it is checked against the goals and a disagreement is
        fatal — a flipped orientation is exactly the bug that would otherwise
        show up as a mysteriously good away record.
        """
        frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
        if frame.empty:
            raise BridgeError("no rows to estimate a bridge from")

        date = _column(frame, ("date", "date_played"), "a date")
        home = _column(frame, ("fthg", "hg", "home_goals"), "home goals")
        away = _column(frame, ("ftag", "ag", "away_goals"), "away goals")

        keep = np.ones(len(frame), bool)
        if "played" in frame.columns:
            keep &= frame["played"].to_numpy(bool)

        day = pd.Timestamp(cutoff).normalize()
        keep &= pd.to_datetime(date).to_numpy() < day.to_datetime64()
        if not keep.any():
            raise BridgeError(f"no played match before {day.date()} to estimate from")

        hg = pd.to_numeric(home[keep], errors="coerce").to_numpy(float)
        ag = pd.to_numeric(away[keep], errors="coerce").to_numpy(float)
        valid = (np.isfinite(hg) & np.isfinite(ag) & (hg >= 0) & (ag >= 0)
                 & (hg == np.floor(hg)) & (ag == np.floor(ag)))
        if not valid.all():
            raise BridgeError(
                f"{int((~valid).sum())} pre-cutoff row(s) carry a score that is "
                "not a valid goal count (finite, non-negative, integral)")
        hg = hg.astype(np.int64)
        ag = ag.astype(np.int64)

        outcome = np.where(hg > ag, 0, np.where(hg == ag, 1, 2))
        if "ftr" in frame.columns:
            labelled = score_mod.outcome_codes(frame["ftr"].to_numpy()[keep])
            wrong = int((labelled != outcome).sum())
            if wrong:
                raise BridgeError(
                    f"{wrong} pre-cutoff row(s) carry an `ftr` label that "
                    "contradicts the scoreline — the join is oriented wrongly, "
                    "or the labels are not this frame's")

        side = int(max_goals) + 1
        on_grid = (hg <= max_goals) & (ag <= max_goals)
        n_excluded = int((~on_grid).sum())
        n_rows = int(on_grid.size)
        if n_excluded > MAX_EXCLUDED_SHARE * n_rows:
            raise BridgeError(
                f"{n_excluded}/{n_rows} pre-cutoff matches fall outside the "
                f"{max_goals}-goal grid, over the {MAX_EXCLUDED_SHARE:g} share "
                "limit: the bridge would not be the law of the rows it read")

        counts = np.zeros((3, side * side), np.int64)
        np.add.at(counts, (outcome[on_grid], hg[on_grid] * side + ag[on_grid]), 1)
        return cls(counts=counts, max_goals=int(max_goals),
                   cutoff=day.date().isoformat(), n_rows=n_rows,
                   n_excluded=n_excluded)

    # ---- use -------------------------------------------------------------
    @property
    def n_by_outcome(self) -> np.ndarray:
        """Pre-cutoff matches behind each conditional, in :data:`OUTCOMES` order."""
        return self.counts.sum(axis=1)

    def content_hash(self) -> str:
        return self.hash

    def sample(self, outcome, u) -> tuple[np.ndarray, np.ndarray]:
        """One scoreline per row, drawn from that row's outcome's conditional.

        Inverse-CDF, same rule as :func:`_draw_outcome`: ``|{i : cdf[i] <= u}|``.
        The ``<=`` matters here in a way it does not for a continuous grid — an
        empirical pmf has many exactly-zero cells and therefore many exactly-tied
        cumulative entries, and this is the side of the tie that cannot land on
        one of them.
        """
        outcome = np.asarray(outcome, dtype=np.int64)
        u = np.asarray(u, dtype=float)
        if outcome.shape != u.shape or outcome.ndim != 1:
            raise BridgeError(
                f"outcome {outcome.shape} and uniforms {u.shape} must be the "
                "same 1-D shape")
        if outcome.size and (outcome.min() < 0 or outcome.max() > 2):
            raise BridgeError("outcome codes must be 0=home, 1=draw, 2=away")
        if u.size and (u.min() < 0.0 or u.max() >= 1.0):
            raise BridgeError("uniforms must lie in [0, 1)")

        flat = np.empty(outcome.shape, np.int64)
        for code in range(3):
            rows = outcome == code
            if rows.any():
                flat[rows] = np.searchsorted(self.cdf[code], u[rows], side="right")
        side = self.max_goals + 1
        return (flat // side).astype(np.int8), (flat % side).astype(np.int8)

    def describe(self) -> dict:
        return {"bridge_hash": self.hash, "bridge_cutoff": self.cutoff,
                "bridge_rows": int(self.n_rows),
                "bridge_rows_by_outcome": self.n_by_outcome.tolist(),
                "bridge_excluded_rows": int(self.n_excluded),
                "max_goals": int(self.max_goals)}


def _column(frame: pd.DataFrame, names: Sequence[str], what: str) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    raise BridgeError(
        f"no {what} column: expected one of {list(names)}, got "
        f"{list(frame.columns)[:12]}")


# ==========================================================================
# arm (b): the model's 1X2, the bridge's scoreline
# ==========================================================================

class DCWDLProvider:
    """The DC model reduced to its 1X2, with the bridge supplying the scoreline.

    Per fixture, per simulated season: take that season's particle's 1X2 from
    the same ``FixtureCDF`` the native arm samples from, apply the SAME
    mechanism-(c) widening branch (plan v2 D12) with the same ``u[1]`` coin, draw
    the outcome with ``u[0]``, and hand it to the bridge with ``u[2]``.

    Because 1X2 is a function of the scoreline, this arm's per-fixture outcome
    marginal is *exactly* the native arm's — mixture and all. That equality is
    the point: it is what makes the paired difference between the two arms a
    measurement of scoreline structure alone, and it is asserted directly in
    `epl/tests/test_bridge.py`.
    """

    name = "dc_wdl_bridge"

    def __init__(self, book: particles.ParticleBook, bridge: EmpiricalBridge,
                 *, cutoff=None):
        if int(book.max_goals) != int(bridge.max_goals):
            raise BridgeError(
                f"the book truncates at {book.max_goals} goals and the bridge at "
                f"{bridge.max_goals}: the two arms would not be sampling the same "
                "scoreline space")
        # This arm's own cutoff lives in the book's fit, which the book does not
        # carry, so the forecast cutoff is passed in. When it is given the
        # point-in-time check is enforced here; when it is not, `simulate`
        # enforces the same rule against the plan's cutoff, which no run can
        # avoid going through.
        if cutoff is not None:
            bridge.refuse_if_after(cutoff, "this arm's forecast cutoff")
        self.cutoff = None if cutoff is None else str(
            pd.Timestamp(cutoff).normalize().date())
        self.book = book
        self.bridge = bridge
        self._laws: dict[str, tuple[np.ndarray, np.ndarray | None]] = {}
        self._excluded: dict[str, dict] = {}

    # The per-fixture laws are derived and are rebuilt in a worker rather than
    # pickled to it, exactly as the native arm's CDF cache is.
    def __getstate__(self) -> dict:
        return {"book": self.book, "bridge": self.bridge, "cutoff": self.cutoff}

    def __setstate__(self, state: dict) -> None:
        self.book = state["book"]
        self.bridge = state["bridge"]
        self.cutoff = state.get("cutoff")
        self._laws = {}
        self._excluded = {}

    @property
    def n_particles(self) -> int:
        return self.book.n_particles

    @property
    def bridge_hash(self) -> str:
        return self.bridge.hash

    def laws_for(self, fixture) -> tuple[np.ndarray, np.ndarray | None]:
        """``(one_x_two[S, 3], widening 1X2 or None)`` for one fixture."""
        got = self._laws.get(fixture.fixture_id)
        if got is None:
            cdfs = particles.fixture_cdfs(self.book, fixture.home_key,
                                          fixture.away_key)
            widened = None
            if cdfs.provisional and cdfs.q_cdf is not None:
                # Recover q's pmf from its cumulative form and reduce it to 1X2
                # through the same indicator matrix the per-particle laws used.
                q = np.diff(cdfs.q_cdf, prepend=0.0)
                widened = q @ particles._outcome_matrix(self.book.max_goals + 1)
            got = (cdfs.one_x_two, widened)
            self._laws[fixture.fixture_id] = got
            self._excluded[fixture.fixture_id] = dict(cdfs.excluded)
        return got

    def excluded_mass_for(self, fixture) -> dict:
        """This fixture's D11 v1.0.1 truncation record (owner ruling A1).

        This arm reduces the same truncated grids the native arm samples, so it
        carries the same tail and reports it the same way. Before the amendment
        it also failed closed on the same fixture — see the dated correction in
        `reports/epl_sim_first_issuance.md`.
        """
        self.laws_for(fixture)
        return dict(self._excluded[fixture.fixture_id])

    def sample(self, fixture, particle_idx, u):
        one_x_two, widened = self.laws_for(fixture)
        probs = one_x_two[np.asarray(particle_idx, np.int64)]   # fancy index copies
        if widened is not None:
            coin = np.asarray(u[1]) < self.book.alpha
            if coin.any():
                probs[coin] = widened
        return self.bridge.sample(_draw_outcome(probs, np.asarray(u[0])),
                                  np.asarray(u[2]))

    def content_hash(self) -> str:
        return _sha256_json({"schema": _DCWDL_ARM_SCHEMA,
                             "book": self.book.content_hash(),
                             "bridge": self.bridge.hash})

    def describe(self) -> dict:
        return {
            # The branch is the same Bernoulli as the native arm's, applied to
            # the outcome law rather than to the scoreline law; naming it that
            # way keeps the envelope honest about where it acted.
            "widening_mode": f"per_fixture_bernoulli_1x2@alpha={self.book.alpha:g}",
            "max_goals": int(self.book.max_goals),
            "effective_posterior_hash": self.book.content_hash(),
            **self.bridge.describe(),
        }


# ==========================================================================
# arm (c): frozen Elo through an ordered logit, the same bridge
# ==========================================================================

class EloOutcomeProvider:
    """Static Elo ratings at the cutoff -> ordered logit -> outcome -> bridge.

    STATIC, deliberately (plan v2 D18). The ratings are the table standing at
    the cutoff and do not move as the simulated season is played out, so a
    fixture's law is the same in every simulated season and cannot depend on
    which particle priced it. A pathwise-updating Elo is a named v1.1
    sensitivity (§6, R8), not this arm — and the coin-flip-tiebreak Elo of plan
    v1 is deleted outright, being a straw man rather than a comparator.

    The head is :mod:`epl.ordlogit`, fitted on matches strictly before the
    cutoff — the same three-parameter proportional-odds model the probe's Elo
    baseline reports, so this arm IS that baseline, extended to a season.
    """

    name = "elo_wdl_bridge"

    def __init__(self, *, probs, fixture_ids: Sequence[str],
                 bridge: EmpiricalBridge, params: ordlogit.OrdLogitParams | None,
                 cutoff, n_fit_rows: int,
                 n_particles: int = DEFAULT_N_PARTICLES,
                 ratings: dict[str, float] | None = None):
        probs = np.atleast_2d(np.asarray(probs, dtype=float))
        fixture_ids = tuple(str(f) for f in fixture_ids)
        if probs.shape != (len(fixture_ids), 3):
            raise BridgeError(
                f"probabilities are {probs.shape}, expected "
                f"{(len(fixture_ids), 3)} — one row per fixture in "
                f"{OUTCOMES} order")
        if len(set(fixture_ids)) != len(fixture_ids):
            raise BridgeError("duplicate fixture id in the Elo arm's fixtures")
        # Reject a malformed row here rather than at the first sample: a
        # provider that cannot price its fixtures should not reach the engine.
        _draw_outcome(probs, np.zeros(len(fixture_ids)))

        self.probs = probs
        self.fixture_ids = fixture_ids
        self.bridge = bridge
        self.params = params
        self.cutoff = str(pd.Timestamp(cutoff).normalize().date())
        # This arm carries its own cutoff — the anchor's — so the point-in-time
        # check is unconditional here.
        bridge.refuse_if_after(self.cutoff, "the Elo arm's own cutoff")
        self.n_fit_rows = int(n_fit_rows)
        self.n_particles = int(n_particles)
        self.ratings = dict(ratings or {})
        self._index = {fid: i for i, fid in enumerate(fixture_ids)}

    # ---- construction ---------------------------------------------------
    @classmethod
    def fit(cls, anchor_state, history, fixtures: Iterable[Any],
            bridge: EmpiricalBridge, *, cutoff=None,
            n_particles: int = DEFAULT_N_PARTICLES,
            min_fit: int = ordlogit.MIN_FIT_MATCHES) -> "EloOutcomeProvider":
        """Fit the head on pre-cutoff history and price every fixture with it.

        `anchor_state` is an :class:`epl.anchor.AnchorState` (or the
        :class:`epl.liveanchor.LiveAnchor` equivalent) — a rating table plus the
        cutoff it stands at. `history` is ``Anchor.history``'s frame, carrying
        ``date``, ``elo_diff_pre`` and ``ftr``. `fixtures` is anything with
        ``fixture_id``/``home_key``/``away_key``, which both
        :class:`epl.season.Fixture` and :class:`epl.leaguesim.FixturePlan` are.

        The cutoff defaults to the anchor state's own, which is the property
        that stops the ratings and the head drifting apart: one object, one
        moment. The filter is day-floored ``date < cutoff.normalize()``, the
        model layer's rule, so this arm sees exactly what the DC arms' fit saw.
        """
        cutoff = anchor_state.cutoff if cutoff is None else cutoff
        day = pd.Timestamp(cutoff).normalize()

        frame = history if isinstance(history, pd.DataFrame) else pd.DataFrame(
            list(history))
        for column in ("date", "elo_diff_pre", "ftr"):
            if column not in frame.columns:
                raise BridgeError(
                    f"history needs a {column!r} column; got "
                    f"{list(frame.columns)[:12]}")
        before = pd.to_datetime(frame["date"]).to_numpy() < day.to_datetime64()
        n_fit_rows = int(before.sum())
        if n_fit_rows < min_fit:
            raise BridgeError(
                f"only {n_fit_rows} match(es) before {day.date()}, under the "
                f"{min_fit}-match floor: an ordered logit fitted on fewer rows "
                "reports its prior's pull on its init, not an estimate")

        params = ordlogit.fit(
            frame["elo_diff_pre"].to_numpy(float)[before],
            score_mod.outcome_codes(frame["ftr"].to_numpy()[before]))

        ratings = anchor_state.ratings
        fixtures = list(fixtures)
        clubs = ({f.home_key for f in fixtures} | {f.away_key for f in fixtures})
        missing = sorted(clubs - set(ratings))
        if missing:
            raise BridgeError(
                f"club(s) {missing} have no rating at {day.date()}: the Elo arm "
                "cannot price a fixture it has no rating for, and a default "
                "would be a modelling choice smuggled in as a fallback")

        edge = np.array([ratings[f.home_key] - ratings[f.away_key]
                         for f in fixtures], dtype=float)
        return cls(probs=ordlogit.predict(params, edge),
                   fixture_ids=[f.fixture_id for f in fixtures],
                   bridge=bridge, params=params, cutoff=day,
                   n_fit_rows=n_fit_rows, n_particles=n_particles,
                   ratings={club: float(ratings[club]) for club in sorted(clubs)})

    # ---- use -------------------------------------------------------------
    @property
    def bridge_hash(self) -> str:
        return self.bridge.hash

    def probs_for(self, fixture_id: str) -> np.ndarray:
        position = self._index.get(str(fixture_id))
        if position is None:
            raise BridgeError(
                f"the Elo arm never priced {fixture_id!r}: it was fitted over a "
                f"different fixture set ({len(self.fixture_ids)} fixtures), and "
                "pricing one it has not seen would be inventing a forecast")
        return self.probs[position]

    def sample(self, fixture, particle_idx, u):
        # `particle_idx` is deliberately unread: the ratings are static, so the
        # posterior draw a season was assigned does not enter this arm's law.
        probs = self.probs_for(fixture.fixture_id)[None, :]
        return self.bridge.sample(_draw_outcome(probs, np.asarray(u[0])),
                                  np.asarray(u[2]))

    def content_hash(self) -> str:
        return _sha256_json({
            "schema": _ELO_ARM_SCHEMA,
            "cutoff": self.cutoff,
            "n_fit_rows": self.n_fit_rows,
            "params": None if self.params is None else self.params.as_dict(),
            "bridge": self.bridge.hash,
            "fixtures": {fid: self.probs[i].tolist()
                         for i, fid in enumerate(self.fixture_ids)},
        })

    def describe(self) -> dict:
        # `elo_cutoff` is REPORTED, not implied. This arm carries two fitted
        # objects with two cutoffs — the empirical bridge's and the ordered
        # logit's — and only the bridge's reached `describe()`, so the engine's
        # point-in-time backstop compared the forecast against one of them and
        # was blind to the other. An Elo head fitted through 2023-12 behind an
        # older bridge simulated a 2022-06 state without complaint.
        return {"widening_mode": "none",
                "max_goals": int(self.bridge.max_goals),
                "elo_head": None if self.params is None else self.params.as_dict(),
                "elo_fit_rows": self.n_fit_rows,
                "elo_cutoff": self.cutoff,
                **self.bridge.describe()}


# ==========================================================================
# the nulls (plan v2 §5)
# ==========================================================================

def flat_matrix(n_clubs: int = 20) -> np.ndarray:
    """The zero-cost null: every club equally likely to finish anywhere.

    Doubly stochastic by construction, so it is an admissible forecast and TRPS
    scores it honestly. `dc_native` beating this at every (season, cutoff) is a
    hard sanity check of the retrospective, not a result (plan v2 §5).
    """
    if n_clubs <= 0:
        raise BridgeError("a league has at least one club")
    return np.full((n_clubs, n_clubs), 1.0 / n_clubs)


def ppg_pointmass(state, *, min_rounds: int = PPG_MIN_ROUNDS) -> np.ndarray | None:
    """Points-per-game extrapolation as a point mass, or None if too early.

    The floor a league-table forecast has to clear: assume every club keeps its
    current rate exactly, project the final table, and put all the probability
    on that one ordering. Undefined before `min_rounds` complete rounds — at the
    opener there is no rate to extrapolate (Codex A4), and after one round it is
    a rate estimated from one match.

    Points adjustments are added ONCE (they are not a rate); the goal columns
    are extrapolated the same way as the points. Exact ties get the ranker's
    fractional convention (plan v2 D8) so the result is still doubly stochastic,
    but the Handbook's head-to-head ladder is deliberately NOT run: a projected
    table has no scorelines to run it on, and inventing some would make the null
    a model.
    """
    clubs = list(state.clubs)
    table = state.table_so_far
    played = np.array([table[club].played for club in clubs], dtype=float)
    if played.min() < min_rounds:
        return None

    remaining = 38.0 - played
    match_points = np.array([3 * table[club].w + table[club].d for club in clubs],
                            dtype=float)
    adjustment = np.array([table[club].adjustment for club in clubs], dtype=float)
    gd = np.array([table[club].gd for club in clubs], dtype=float)
    gf = np.array([table[club].gf for club in clubs], dtype=float)

    scale = 1.0 + remaining / played
    projected_points = match_points * scale + adjustment
    projected_gd = gd * scale
    projected_gf = gf * scale

    return _pointmass_matrix(projected_points, projected_gd, projected_gf)


def _pointmass_matrix(points, gd, gf) -> np.ndarray:
    """C.4 -> C.5 -> C.6 on one projected table, ties shared fractionally.

    The run-finding and mass-spreading come from :mod:`epl.table` rather than
    being written out again here. They are private there, and reached across on
    purpose: a null whose tie convention drifted from the ranker's would make a
    difference in TRPS that was about the convention rather than the forecast.
    """
    keys = [np.asarray(k, float)[None, :] for k in (points, gd, gf)]
    order = np.lexsort((-keys[2], -keys[1], -keys[0]), axis=-1)
    sorted_keys = [np.take_along_axis(k, order, axis=1) for k in keys]
    start, span = table_mod._blocks(sorted_keys)

    n_clubs = keys[0].shape[1]
    out_start = np.zeros((1, n_clubs), np.uint8)
    out_span = np.zeros((1, n_clubs), np.uint8)
    np.put_along_axis(out_start, order, (start + 1).astype(np.uint8), axis=1)
    np.put_along_axis(out_span, order, span.astype(np.uint8), axis=1)
    matrix = table_mod._mass_chunk(out_start, out_span, n_clubs)[0]
    table_mod.check_doubly_stochastic(matrix)
    return matrix


# ==========================================================================
# helpers
# ==========================================================================

def _sha256_json(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()
