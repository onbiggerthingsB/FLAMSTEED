"""League-table accumulation and the Premier League ranker (plan v2 T3, D7-D10).

Two jobs, kept apart on purpose.

`accumulate` turns an ``int8[N, F, 2]`` block of simulated scorelines into
points/GD/GF/GA/W/D/L for every club in every simulated season. It is fully
vectorised over sims: `wcmodel.sim.groups.group_table` is the scalar oracle the
tests check it against, never a component of the hot path.

`rank` applies the Handbook ladder to those totals:

    C.4   points
    C.5   goal difference
    C.6   goals scored
    C.7   clubs still level SHARE the position

...unless the shared block is *material* — it straddles one of the versioned
boundaries ``{1|2, 4|5, 5|6, 6|7, 7|8, 17|18}`` — in which case C.17 runs:

    C.17.1  head-to-head points among the block's clubs
    C.17.2  goals scored as the VISITING club in the ORIGINAL block's
            head-to-head matches (the literal reading; the alternative is to
            re-apply it among the still-tied subset only, which is the UEFA
            convention and is NOT what the Handbook text says — the choice is
            versioned as ``h2h_away=original_set`` in the rule id and the ranker
            refuses a rule id that claims anything else)
    C.17.3  exactly two clubs still level -> a play-off, which has no model here

The gate is evaluated ONCE, on the block as C.4-C.6 left it, which is the literal
scope of the Handbook text ("...the following procedure will be adopted" applies
to the tied clubs). So a material block of 17-19 that C.17 splits into a decided
17th and a still-level 18th/19th reports that residual as unresolved rather than
as a plain shared position, even though nothing hangs on 18 versus 19. The
alternative — re-testing materiality on each residual sub-block — changes only
the resolution code and which mass bucket the pair lands in, never the fractional
numbers or any consequence market. It is flagged as an open reading, not settled
here.

Three or more clubs still level after C.17.2 is a case the Handbook does not
cover at all. Both that case and C.17.3 are resolved by *fractional allocation*
(plan v2 D8): a block of k clubs spanning k positions takes 1/k of each. That is
the Rao-Blackwellised form of a coin flip — same expectation, zero added
variance — and it is why **the ranker consumes no randomness whatsoever**, which
the tests assert directly. The mass that rests on the convention is not hidden:
`position_mass_sums` returns it separately as `shared`, `unresolved_playoff` and
`unresolved_multiway`, so a headline can always be quoted with the share of it
that the rulebook does not actually decide.

Positions are 1-based everywhere in the outputs (`block_start` = 1 is the
champion); array axes are 0-based. The display matrix is indexed
``[sim, club, position]`` and every row and every column sums to one — the
admissibility condition a positional forecast has to meet before it can be
scored at all (plan v2 D10).

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_table.py -q
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

# --------------------------------------------------------------------------
# resolution codes — how a club's final position came to be decided
# --------------------------------------------------------------------------

UNIQUE = 0                 #: alone on points (C.4)
GD = 1                     #: level on points, separated by goal difference (C.5)
GF = 2                     #: level on points and GD, separated by goals scored (C.6)
SHARED_NONMATERIAL = 3     #: still level, nothing rests on the order (C.7)
H2H_PTS = 4                #: material tie broken by head-to-head points (C.17.1)
H2H_AWAY = 5               #: material tie broken by head-to-head away goals (C.17.2)
UNRESOLVED_PLAYOFF = 6     #: two clubs still level -> play-off (C.17.3), no model
UNRESOLVED_MULTIWAY = 7    #: three or more still level -> no rule exists

RESOLUTION_NAMES = (
    "UNIQUE", "GD", "GF", "SHARED_NONMATERIAL",
    "H2H_PTS", "H2H_AWAY", "UNRESOLVED_PLAYOFF", "UNRESOLVED_MULTIWAY",
)

#: Codes whose position rests on a convention rather than on the rulebook.
UNRESOLVED_CODES = (UNRESOLVED_PLAYOFF, UNRESOLVED_MULTIWAY)


class TableError(RuntimeError):
    """Anything the accumulator or the ranker refuses to do."""


class RuleIdMismatch(TableError):
    """The tiebreak rule id does not describe the ladder it was handed."""


class IdentityViolation(TableError):
    """A league table that cannot exist (plan v2 D10)."""


class CoherenceViolation(TableError):
    """A position matrix that is not doubly stochastic (plan v2 D10)."""


# --------------------------------------------------------------------------
# the accumulator
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Totals:
    """Per-club season totals across N simulated seasons, all ``int16[N, C]``.

    `adjustments` (``int16[C]``) are the points deductions already folded into
    `pts`; `fixtures_per_club` (``int16[C]``) is how many fixtures each club
    actually appears in, which is what makes ``w + d + l`` a real identity
    rather than a hard-coded 38.
    """

    pts: np.ndarray
    gd: np.ndarray
    gf: np.ndarray
    ga: np.ndarray
    w: np.ndarray
    d: np.ndarray
    l: np.ndarray                                            # noqa: E741
    adjustments: np.ndarray
    fixtures_per_club: np.ndarray

    @property
    def n_sims(self) -> int:
        return int(self.pts.shape[0])

    @property
    def n_clubs(self) -> int:
        return int(self.pts.shape[1])


def accumulate(scorelines, home_idx, away_idx, n_clubs: int = 20,
               adjustments=None) -> Totals:
    """Season totals for every club in every simulated season.

    `scorelines` is ``int[N, F, 2]`` (home goals, away goals); `home_idx` and
    `away_idx` are ``int[F]`` club indices. Pinned (already played) fixtures are
    ordinary rows here — the engine writes the real result into them, so this
    function never needs to know which is which.
    """
    sl = np.asarray(scorelines)
    if sl.ndim != 3 or sl.shape[2] != 2:
        raise TableError(f"scorelines must be [N, F, 2], got {sl.shape}")
    home_idx = np.asarray(home_idx, np.int64)
    away_idx = np.asarray(away_idx, np.int64)
    if home_idx.shape != away_idx.shape or home_idx.ndim != 1:
        raise TableError("home_idx and away_idx must be matching 1-D arrays")
    if home_idx.size != sl.shape[1]:
        raise TableError(
            f"{home_idx.size} fixtures but scorelines carry {sl.shape[1]}")
    if home_idx.size and (home_idx.max() >= n_clubs or away_idx.max() >= n_clubs
                          or home_idx.min() < 0 or away_idx.min() < 0):
        raise TableError(f"club indices outside [0, {n_clubs})")
    if np.any(home_idx == away_idx):
        raise TableError("a fixture cannot have the same club at both ends")
    if np.any(sl < 0):
        raise TableError("negative goals")

    n_sims = int(sl.shape[0])
    hg = sl[:, :, 0].astype(np.int16, copy=False)
    ag = sl[:, :, 1].astype(np.int16, copy=False)

    if adjustments is None:
        adj = np.zeros(n_clubs, np.int16)
    else:
        adj = np.asarray(adjustments, np.int16)
        if adj.shape != (n_clubs,):
            raise TableError(f"adjustments must be [{n_clubs}], got {adj.shape}")

    shape = (n_sims, n_clubs)
    gf = np.zeros(shape, np.int32)
    ga = np.zeros(shape, np.int32)
    w = np.zeros(shape, np.int32)
    d = np.zeros(shape, np.int32)
    played = np.zeros(n_clubs, np.int32)

    for club in range(n_clubs):
        at_home = np.flatnonzero(home_idx == club)
        away = np.flatnonzero(away_idx == club)
        played[club] = at_home.size + away.size

        hg_h, ag_h = hg[:, at_home], ag[:, at_home]
        hg_a, ag_a = hg[:, away], ag[:, away]

        gf[:, club] = hg_h.sum(axis=1) + ag_a.sum(axis=1)
        ga[:, club] = ag_h.sum(axis=1) + hg_a.sum(axis=1)
        w[:, club] = (hg_h > ag_h).sum(axis=1) + (ag_a > hg_a).sum(axis=1)
        d[:, club] = (hg_h == ag_h).sum(axis=1) + (ag_a == hg_a).sum(axis=1)

    losses = played[None, :] - w - d
    pts = 3 * w + d + adj[None, :].astype(np.int32)

    return Totals(
        pts=pts.astype(np.int16), gd=(gf - ga).astype(np.int16),
        gf=gf.astype(np.int16), ga=ga.astype(np.int16),
        w=w.astype(np.int16), d=d.astype(np.int16), l=losses.astype(np.int16),
        adjustments=adj.astype(np.int16),
        fixtures_per_club=played.astype(np.int16),
    )


def check_identities(totals: Totals) -> None:
    """Raise `IdentityViolation` on any table that could not have happened.

    This is the table half of the D10 guard list; the engine calls it once per
    run, and it is written to fail loudly rather than to be reassuring.
    """
    t = totals
    if not np.all(t.w + t.d + t.l == t.fixtures_per_club[None, :]):
        raise IdentityViolation("W + D + L does not equal matches played")
    if not np.array_equal(t.gd, t.gf - t.ga):
        raise IdentityViolation("GD does not equal GF - GA")
    if not np.array_equal(t.pts, (3 * t.w.astype(np.int32) + t.d
                                  + t.adjustments[None, :]).astype(np.int16)):
        raise IdentityViolation("points do not equal 3W + D + adjustment")
    if not np.all(t.gd.astype(np.int64).sum(axis=1) == 0):
        raise IdentityViolation("goal differences do not sum to zero")
    if not np.array_equal(t.gf.astype(np.int64).sum(axis=1),
                          t.ga.astype(np.int64).sum(axis=1)):
        raise IdentityViolation("goals for do not equal goals against")
    if not np.array_equal(t.w.astype(np.int64).sum(axis=1),
                          t.l.astype(np.int64).sum(axis=1)):
        raise IdentityViolation("wins do not equal losses")


# --------------------------------------------------------------------------
# the materiality gate and the rule id that versions it
# --------------------------------------------------------------------------

_MATERIAL_RE = re.compile(r"material=\{([^}]*)\}")
_H2H_AWAY_RE = re.compile(r"h2h_away=([A-Za-z_]+)")

#: The only C.17.2 reading this module implements (plan v2 Q2).
H2H_AWAY_READING = "original_set"


def parse_material_boundaries(rule_id: str) -> tuple[tuple[int, int], ...]:
    """Pull the ``material={a|b,...}`` clause out of a tiebreak rule id."""
    found = _MATERIAL_RE.search(rule_id)
    if not found:
        raise RuleIdMismatch(f"rule id carries no material= clause: {rule_id!r}")
    out = []
    for token in found.group(1).split(","):
        token = token.strip()
        if not token:
            continue
        parts = token.split("|")
        if len(parts) != 2:
            raise RuleIdMismatch(f"unreadable boundary {token!r} in {rule_id!r}")
        out.append((int(parts[0]), int(parts[1])))
    return tuple(out)


def check_rule_id(rule_id: str, boundaries) -> None:
    """Refuse a rule id that does not describe the ladder actually being run.

    The rule id travels with every output; if it can drift away from the code
    it is decoration. So it is parsed and checked, not merely recorded.
    """
    declared = parse_material_boundaries(rule_id)
    given = tuple((int(a), int(b)) for a, b in boundaries)
    if declared != given:
        raise RuleIdMismatch(
            f"rule id declares material boundaries {declared} but the ranker "
            f"was given {given}")
    reading = _H2H_AWAY_RE.search(rule_id)
    if reading is None or reading.group(1) != H2H_AWAY_READING:
        raise RuleIdMismatch(
            f"this ranker implements h2h_away={H2H_AWAY_READING}; rule id says "
            f"{reading.group(1) if reading else 'nothing'}")


def is_material(start, span, boundaries):
    """Does a tie-block at 1-based `start` spanning `span` positions matter?

    A block is material when it *contains both sides* of a versioned boundary:
    a block of {17, 18} decides who is relegated, a block of {18, 19} decides
    nothing. Singletons are never ties. Accepts scalars or arrays.
    """
    start = np.asarray(start)
    span = np.asarray(span)
    end = start + span - 1
    out = np.zeros(np.broadcast(start, span).shape, bool)
    for lo, hi in boundaries:
        out |= (start <= lo) & (end >= hi)
    out &= span >= 2
    return out if out.ndim else bool(out)


# --------------------------------------------------------------------------
# C.17 — the head-to-head ladder (pure, scalar, and rarely reached)
# --------------------------------------------------------------------------

def h2h_ladder(clubs, scorelines_among):
    """Order a material tie-block by C.17.1 then C.17.2.

    `clubs` is the block in its pre-C.17 order (used to break nothing — it only
    fixes a deterministic order inside a sub-block that stays level).
    `scorelines_among` maps ``(home, away) -> (home_goals, away_goals)`` for the
    **original block's** head-to-head matches, and that whole set is what C.17.2
    counts away goals over: the still-tied subset is never re-scoped. That is
    the literal reading of "Head-to-Head Matches" and it is versioned in the
    rule id as ``h2h_away=original_set``.

    Returns the sub-blocks best-first as ``[(clubs, resolution_code), ...]``,
    where a sub-block of two or more clubs carries `UNRESOLVED_PLAYOFF` or
    `UNRESOLVED_MULTIWAY` — nothing in the rulebook separates them.
    """
    clubs = list(clubs)
    members = set(clubs)
    if len(members) != len(clubs):
        raise TableError(f"duplicate club in a tie-block: {clubs}")

    pts = dict.fromkeys(clubs, 0)
    away_goals = dict.fromkeys(clubs, 0)
    for (home, away), (hg, ag) in scorelines_among.items():
        if home not in members or away not in members:
            raise TableError(
                f"({home!r}, {away!r}) is not a head-to-head match of {clubs}")
        hg, ag = int(hg), int(ag)
        if hg > ag:
            pts[home] += 3
        elif hg < ag:
            pts[away] += 3
        else:
            pts[home] += 1
            pts[away] += 1
        away_goals[away] += ag                       # C.17.2, visiting club only

    out: list[tuple[tuple, int]] = []
    for run in _runs(sorted(clubs, key=lambda c: -pts[c]), pts):
        if len(run) == 1:
            out.append((tuple(run), H2H_PTS))
            continue
        for sub in _runs(sorted(run, key=lambda c: -away_goals[c]), away_goals):
            if len(sub) == 1:
                out.append((tuple(sub), H2H_AWAY))
            elif len(sub) == 2:
                out.append((tuple(sub), UNRESOLVED_PLAYOFF))
            else:
                out.append((tuple(sub), UNRESOLVED_MULTIWAY))
    return out


def _runs(ordered, key_map):
    """Maximal runs of `ordered` sharing a value in `key_map` (input is sorted;
    Python's sort is stable, so the run order is the caller's order)."""
    runs, current = [], []
    for item in ordered:
        if current and key_map[item] != key_map[current[0]]:
            runs.append(current)
            current = []
        current.append(item)
    if current:
        runs.append(current)
    return runs


# --------------------------------------------------------------------------
# the ranker
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Ranking:
    """Where every club finished, and what decided it.

    All arrays are ``[N, C]``. `block_start` is the 1-based position of the top
    of the club's block and `block_span` its size — a club alone on its rung has
    span 1 and `block_start` IS its position; a block of k clubs occupies
    positions ``block_start .. block_start + k - 1`` and shares them.
    `order` is the ladder sequence (``order[n, r]`` = the club at 0-based rung
    r); inside a shared block its sequence carries no meaning and is only the
    deterministic club-index order.
    """

    block_start: np.ndarray            # uint8[N, C]
    block_span: np.ndarray             # uint8[N, C]
    resolution_code: np.ndarray        # uint8[N, C]
    order: np.ndarray                  # int8[N, C]
    boundaries: tuple
    rule_id: str

    @property
    def n_sims(self) -> int:
        return int(self.block_start.shape[0])

    @property
    def n_clubs(self) -> int:
        return int(self.block_start.shape[1])


def rank(totals: Totals, scorelines, home_idx, away_idx, boundaries,
         rule_id: str) -> Ranking:
    """Apply the Handbook ladder to `totals`, one ranking per simulated season.

    Stages C.4-C.6 and the materiality gate are vectorised over all N seasons at
    once. Only the material tie-blocks fall through to the scalar C.17 path, and
    in a real season those are close to nonexistent — which is the whole reason
    the head-to-head sub-tables can be recomputed honestly per season instead of
    being approximated away.
    """
    check_rule_id(rule_id, boundaries)
    boundaries = tuple((int(a), int(b)) for a, b in boundaries)

    pts, gd, gf = totals.pts, totals.gd, totals.gf
    n_sims, n_clubs = pts.shape
    if n_clubs > 127:
        raise TableError("order is int8; more than 127 clubs is out of contract")

    sl = np.asarray(scorelines)
    home_idx = np.asarray(home_idx, np.int64)
    away_idx = np.asarray(away_idx, np.int64)
    if sl.ndim != 3 or sl.shape[2] != 2:
        raise TableError(f"scorelines must be [N, F, 2], got {sl.shape}")
    if sl.shape[0] != n_sims:
        raise TableError(
            f"totals hold {n_sims} seasons, scorelines {sl.shape[0]}")
    if home_idx.shape != away_idx.shape or home_idx.size != sl.shape[1]:
        raise TableError(
            f"{home_idx.size} home / {away_idx.size} away indices but "
            f"{sl.shape[1]} fixtures of scorelines")

    # C.4 -> C.5 -> C.6. lexsort's last key is the primary one; it is stable, so
    # clubs that are level in every criterion stay in club-index order and no
    # tie is ever broken by accident.
    order = np.lexsort((-gf, -gd, -pts), axis=-1)
    s_pts = np.take_along_axis(pts, order, axis=1)
    s_gd = np.take_along_axis(gd, order, axis=1)
    s_gf = np.take_along_axis(gf, order, axis=1)

    start1, span1 = _blocks([s_pts])
    start2, span2 = _blocks([s_pts, s_gd])
    start3, span3 = _blocks([s_pts, s_gd, s_gf])

    # what separated each club, in ladder space
    code = np.full((n_sims, n_clubs), SHARED_NONMATERIAL, np.uint8)
    alone = span3 == 1
    code[alone & (span1 == 1)] = UNIQUE
    code[alone & (span1 > 1) & (span2 == 1)] = GD
    code[alone & (span2 > 1)] = GF

    block_start_rank = start3
    block_span_rank = span3
    material = is_material(block_start_rank + 1, block_span_rank, boundaries)

    # scatter ladder-space results back to club-space. Zeros, not `empty`: the
    # scatter is a total permutation, and if a refactor ever broke that, an
    # impossible position 0 is a visible bug where uninitialised memory is not.
    out_start = np.zeros((n_sims, n_clubs), np.uint8)
    out_span = np.zeros((n_sims, n_clubs), np.uint8)
    out_code = np.zeros((n_sims, n_clubs), np.uint8)
    np.put_along_axis(out_start, order, (block_start_rank + 1).astype(np.uint8), axis=1)
    np.put_along_axis(out_span, order, block_span_rank.astype(np.uint8), axis=1)
    np.put_along_axis(out_code, order, code, axis=1)

    # C.17, only where a shared block actually decides something
    new_block = np.zeros((n_sims, n_clubs), bool)
    new_block[:, 0] = True
    new_block[:, 1:] = block_start_rank[:, 1:] != block_start_rank[:, :-1]
    sims, rungs = np.nonzero(material & new_block)
    if sims.size:
        lookup = _fixture_lookup(home_idx, away_idx)
        for sim, rung in zip(sims.tolist(), rungs.tolist()):
            span = int(block_span_rank[sim, rung])
            members = [int(c) for c in order[sim, rung:rung + span]]
            among = {}
            for home in members:
                for away in members:
                    if home == away:
                        continue
                    fixture = lookup.get((home, away))
                    if fixture is None:
                        continue           # not played twice yet: use what exists
                    among[(home, away)] = (int(sl[sim, fixture, 0]),
                                           int(sl[sim, fixture, 1]))
            position = rung
            for sub, sub_code in h2h_ladder(members, among):
                for club in sub:
                    out_start[sim, club] = position + 1
                    out_span[sim, club] = len(sub)
                    out_code[sim, club] = sub_code
                order[sim, position:position + len(sub)] = sub
                position += len(sub)

    return Ranking(block_start=out_start, block_span=out_span,
                   resolution_code=out_code, order=order.astype(np.int8),
                   boundaries=boundaries, rule_id=rule_id)


def _blocks(keys):
    """Start rung and length of the run each rung belongs to, per row.

    `keys` are already-sorted ``[N, C]`` arrays; rungs are in one run when they
    agree on every key.
    """
    n_sims, n_clubs = keys[0].shape
    same = np.ones((n_sims, n_clubs - 1), bool)
    for key in keys:
        same &= key[:, 1:] == key[:, :-1]

    rungs = np.arange(n_clubs)
    first = np.ones((n_sims, n_clubs), bool)
    first[:, 1:] = ~same
    start = np.maximum.accumulate(np.where(first, rungs, 0), axis=1)

    last = np.ones((n_sims, n_clubs), bool)
    last[:, :-1] = ~same
    end = np.minimum.accumulate(
        np.where(last, rungs, n_clubs - 1)[:, ::-1], axis=1)[:, ::-1]
    return start, end - start + 1


def _fixture_lookup(home_idx, away_idx) -> dict[tuple[int, int], int]:
    return {(int(h), int(a)): f
            for f, (h, a) in enumerate(zip(home_idx.tolist(), away_idx.tolist()))}


# --------------------------------------------------------------------------
# the display matrix (plan v2 D9)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PositionMass:
    """20x20 sums over simulated seasons, indexed ``[club, position]``.

    `matrix` is the whole display matrix; `shared`, `unresolved_playoff` and
    `unresolved_multiway` are the parts of it that a convention put there rather
    than the rulebook (plan v2 D8). Divide by `n_sims` for probabilities.
    """

    matrix: np.ndarray
    shared: np.ndarray
    unresolved_playoff: np.ndarray
    unresolved_multiway: np.ndarray
    n_sims: int

    @property
    def unresolved(self) -> np.ndarray:
        return self.unresolved_playoff + self.unresolved_multiway

    @property
    def matrix_prob(self) -> np.ndarray:
        return self.matrix / self.n_sims


def position_mass(ranking: Ranking) -> np.ndarray:
    """The per-season display matrix, ``float64[N, C, C]`` as ``[sim, club, pos]``.

    Materialising this costs ``N * C * C * 8`` bytes; the engine accumulates
    straight into 20x20 sums with `position_mass_sums` instead and only uses
    this for tests and small runs.
    """
    return _mass_chunk(ranking.block_start, ranking.block_span,
                       ranking.n_clubs)


def position_mass_sums(ranking: Ranking, chunk_size: int = 2048) -> PositionMass:
    """Accumulate the display matrix and its convention-driven parts."""
    n_clubs = ranking.n_clubs
    total = np.zeros((n_clubs, n_clubs))
    shared = np.zeros((n_clubs, n_clubs))
    playoff = np.zeros((n_clubs, n_clubs))
    multiway = np.zeros((n_clubs, n_clubs))

    for lo in range(0, ranking.n_sims, chunk_size):
        hi = min(lo + chunk_size, ranking.n_sims)
        start = ranking.block_start[lo:hi]
        span = ranking.block_span[lo:hi]
        code = ranking.resolution_code[lo:hi]
        mass = _mass_chunk(start, span, n_clubs)
        total += mass.sum(axis=0)
        shared += np.where((code == SHARED_NONMATERIAL)[..., None], mass, 0.0
                           ).sum(axis=0)
        playoff += np.where((code == UNRESOLVED_PLAYOFF)[..., None], mass, 0.0
                            ).sum(axis=0)
        multiway += np.where((code == UNRESOLVED_MULTIWAY)[..., None], mass, 0.0
                             ).sum(axis=0)

    return PositionMass(matrix=total, shared=shared, unresolved_playoff=playoff,
                        unresolved_multiway=multiway, n_sims=ranking.n_sims)


def _mass_chunk(block_start, block_span, n_clubs: int) -> np.ndarray:
    lo = block_start.astype(np.int64) - 1
    span = block_span.astype(np.int64)
    positions = np.arange(n_clubs)
    inside = ((positions[None, None, :] >= lo[..., None])
              & (positions[None, None, :] < (lo + span)[..., None]))
    return inside / span[..., None]


def check_doubly_stochastic(matrix, tol: float = 1e-8) -> None:
    """Every club finishes somewhere; every position is taken by someone.

    A matrix that fails this is not a badly calibrated forecast, it is an
    inadmissible one — nothing downstream may score it (plan v2 D10).
    """
    matrix = np.asarray(matrix, float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise CoherenceViolation(f"position matrix must be square, got {matrix.shape}")
    rows = matrix.sum(axis=1)
    cols = matrix.sum(axis=0)
    if not np.all(np.abs(rows - 1.0) <= tol):
        raise CoherenceViolation(
            f"club rows do not sum to 1 (worst {np.abs(rows - 1.0).max():.3e})")
    if not np.all(np.abs(cols - 1.0) <= tol):
        raise CoherenceViolation(
            f"position columns do not sum to 1 (worst {np.abs(cols - 1.0).max():.3e})")
    if np.any(matrix < -tol):
        raise CoherenceViolation("negative mass in the position matrix")


# --------------------------------------------------------------------------
# the realised table
# --------------------------------------------------------------------------

def official_positions_for_realised(results, adjustments, *, boundaries,
                                    rule_id: str):
    """Final positions of a completed season, through the ranker the sim uses.

    `results` maps ``(home_club, away_club) -> (home_goals, away_goals)`` and
    `adjustments` maps ``club -> points delta`` (the final state of the ledger,
    per plan v2 D16 — the point-in-time state is the caller's business).

    Returns ``[(club, position, span), ...]`` best-first; `span` > 1 is a shared
    finishing position and is reported rather than silently ordered.
    """
    clubs = sorted({club for pair in results for club in pair}
                   | set(adjustments or {}))
    if not clubs:
        raise TableError("no clubs in the realised season")
    index = {club: i for i, club in enumerate(clubs)}

    pairs = sorted(results)
    home_idx = np.array([index[h] for h, _ in pairs], np.int64)
    away_idx = np.array([index[a] for _, a in pairs], np.int64)
    scorelines = np.array([[results[p][0], results[p][1]] for p in pairs],
                          np.int16)[None, :, :]

    adj = np.zeros(len(clubs), np.int16)
    for club, delta in (adjustments or {}).items():
        adj[index[club]] = int(delta)

    totals = accumulate(scorelines, home_idx, away_idx, n_clubs=len(clubs),
                        adjustments=adj)
    ranking = rank(totals, scorelines, home_idx, away_idx, boundaries, rule_id)

    placed = [(clubs[int(club)], int(ranking.block_start[0, club]),
               int(ranking.block_span[0, club]))
              for club in ranking.order[0].tolist()]
    return placed


__all__ = [
    "GD", "GF", "H2H_AWAY", "H2H_AWAY_READING", "H2H_PTS", "PositionMass",
    "Ranking", "RESOLUTION_NAMES", "SHARED_NONMATERIAL", "TableError", "Totals",
    "UNIQUE", "UNRESOLVED_CODES", "UNRESOLVED_MULTIWAY", "UNRESOLVED_PLAYOFF",
    "CoherenceViolation", "IdentityViolation", "RuleIdMismatch", "accumulate",
    "check_doubly_stochastic", "check_identities", "check_rule_id", "h2h_ladder",
    "is_material", "official_positions_for_realised", "parse_material_boundaries",
    "position_mass", "position_mass_sums", "rank",
]
