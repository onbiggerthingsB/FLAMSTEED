"""The explicit season transition, and the Elo walk through a season in progress.

WHAT THIS MODULE EXISTS FOR (plan v2 D5; Codex P0-1, adjudicated ADOPT).
:class:`epl.anchor.Anchor` is the model's strength anchor and it is built from
an ARCHIVE — a run of completed seasons. Two of its properties are correct there
and wrong for the season that opens on Friday.

1. **Past the last archived match it stops re-seeding.** ``Anchor.state`` falls
   through to ``_final_ratings()``, the post-2025/26 rating table with no season
   boundary applied. Measured on this archive under the frozen configuration:
   Coventry raises ``KeyError`` (it has never appeared), Hull carries 1398.9 —
   the rating it stopped playing at in 2016/17 — and Ipswich 1411.1 from its
   relegated season, where the frozen protocol seeds every promoted club at
   ``division_mean + promoted_offset`` = 1594.6 − 75 = 1519.6. Two of the three
   promoted clubs would enter the model's prior 110–120 Elo points below where
   the protocol puts them, and the third could not be priced at all.

2. **Its club set comes from the rows.** ``epl.elo._open_season`` is invoked by
   ``compute_elo_history`` with ``clubs = set(home[seasons == season]) |
   set(away[...])`` (elo.py:265). For a completed season that is exactly the
   twenty; for a season one matchday old it is however many clubs have kicked
   off. Feed a plain ``Anchor`` the archive plus Friday's Arsenal–Coventry and
   it re-seeds Coventry, treats Arsenal as the only continuing club, and never
   re-seeds Hull or Ipswich at all — the boundary rule fires once and is gone.
   So the live season needs a MANIFEST-driven walk throughout, not a single
   correction applied before matchday one.

WHAT THIS MODULE DOES ABOUT IT. :func:`open_target_season` applies
``_open_season`` explicitly — same function, same frozen parameters, same
``division_mean`` over the twenty clubs that completed the previous season —
with the club set taken from the season manifest rather than from whatever rows
happen to exist. :class:`LiveAnchor` then walks the results ledger forward from
that opening table with the same update the archive walk uses, and duck-types
``Anchor.state(cutoff, teams)`` so ``epl.dcfit.fit_epl`` consumes it unchanged.

THE DUPLICATED LOOP, AND THE PARITY THAT LICENSES IT. :func:`replay` is a second
implementation of the inner loop of ``epl.elo.compute_elo_history``: price a
whole block off the table standing when it opens, then apply that block's
updates. Duplicating it is a real cost — two loops can drift — and it is paid
for one reason: ``compute_elo_history`` walks a frame, and the live season is
not a frame of the same kind (its results arrive from a bitemporal ledger, its
club set comes from a manifest, and it must be queryable at an arbitrary cutoff
without rebuilding). What makes the duplication safe is not care but a test:
``test_explicit_replay_of_2025_26_matches_anchor_snapshots_bitwise`` opens
2025/26 explicitly from the 2024/25 finals and replays the season, and every
block's opening table must equal the archived ``Anchor`` snapshot to the last
bit. The update itself is not re-derived here — :func:`epl.elo.expected_score`
and ``epl.elo._mov_multiplier`` are called, so there is one implementation of
the arithmetic even though there are two loops around it.

POINT-IN-TIME. A live result is visible at cutoff C iff it was PLAYED before C's
day and was OBSERVED by C — the same bitemporal rule ``epl.season`` applies
(``_visible_results``), and the same day-flooring ``wcmodel.data.features.build``
applies, so the anchor never sees a match the fit cannot. Blocks in the live
walk are DAYS, because a results ledger carries no kickoff times, where the
archive walk blocks by kickoff. That coarsening changes no rating: a club's Elo
moves only in its own matches and no club plays twice in a day, so both clubs of
a 17:30 match have the same pre-rating whether or not the 12:30 match has been
applied. Asserted, not argued:
``test_live_anchor_replaying_2025_26_matches_archive_state_at_every_cutoff``.

WHAT IS NOT HERE. Nothing decides which fixtures are played — that is the
results ledger's job (:mod:`epl.season`), and "played" is never inferred from a
kickoff date. Nothing under ``src/`` or ``scripts/`` is written or patched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from epl import elo as epl_elo, walk
from epl.anchor import Anchor, AnchorState
from epl.schema import sort_for_walk_forward
from epl.season import Manifest, SeasonError, fixture_id
from epl.season import season_code as _season_code

__all__ = [
    "TransitionError", "LiveRow", "ReplayResult", "normalise_rows",
    "visible_rows", "replay", "open_target_season", "LiveAnchor",
]

#: Columns of ``Anchor.history``, in order. :meth:`LiveAnchor.history_frame`
#: must extend that frame, not a frame that merely resembles it, because the
#: ordered-logit head reads it positionally-by-name.
HISTORY_COLUMNS = (
    "match_id", "season", "season_index", "block", "date", "home_key",
    "away_key", "elo_home_pre", "elo_away_pre", "elo_diff_pre",
    "elo_home_post", "elo_away_post", "home_promoted", "away_promoted", "ftr",
)

class TransitionError(SeasonError):
    """A season transition or live walk that cannot be trusted to be right.

    Subclasses :class:`epl.season.SeasonError` so the whole season layer fails
    with one exception type: a caller that means "the snapshot is unusable"
    catches one thing.
    """


# ==========================================================================
# 1. live rows: the results ledger, made walkable
# ==========================================================================
@dataclass(frozen=True)
class LiveRow:
    """One played fixture of the target season, as the anchor needs it.

    ``key`` is the block key: the day the match was played, at midnight. See
    the module docstring for why day-resolution is exact here.
    """

    fixture_id: str
    home_key: str
    away_key: str
    date_played: pd.Timestamp
    observed_at: pd.Timestamp
    hg: int
    ag: int

    @property
    def ftr(self) -> str:
        return "H" if self.hg > self.ag else "A" if self.ag > self.hg else "D"

    @property
    def key(self) -> pd.Timestamp:
        return self.date_played


def _timestamp(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tz is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _goals(row: dict, side: str, fid: str) -> int:
    if side not in row or row[side] is None:
        raise TransitionError(f"{fid}: results row has no {side!r}")
    value = row[side]
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        raise TransitionError(f"{fid}: {side}={value!r} is not a goal count")
    if not np.isfinite(as_float) or as_float < 0 or not as_float.is_integer():
        raise TransitionError(
            f"{fid}: {side}={value!r} is not a valid goal count (finite, "
            f"non-negative, integral)")
    return int(as_float)


def normalise_rows(rows: Iterable[Any], manifest: Manifest) -> tuple[LiveRow, ...]:
    """Results-ledger rows -> :class:`LiveRow`, failing closed on anything odd.

    Accepts the ledger's own shape (``{fixture_id, date_played, hg, ag, source,
    observed_at, note}``, plan v2 D4) or ready-made :class:`LiveRow` objects.
    Rows carrying a ``status`` (``postponed`` / ``abandoned``) have no scoreline
    and are dropped: they are a fixture state, not a result.

    Everything is checked rather than assumed, because this ledger is
    hand-maintained during the season and a bad row here silently mis-rates a
    club for weeks: the season code must be the manifest's, both clubs must be
    in the manifest's twenty, the score must be a valid goal count, and
    ``observed_at`` must be present — a row with no known-at stamp would be
    visible at every cutoff, which is precisely the leak the ledger exists to
    prevent.
    """
    clubs = set(manifest.clubs)
    out: list[LiveRow] = []
    for raw in rows:
        if isinstance(raw, LiveRow):
            unknown = {raw.home_key, raw.away_key} - clubs
            if unknown:
                raise TransitionError(
                    f"{raw.fixture_id}: club(s) {sorted(unknown)} are not in the "
                    f"{manifest.season} manifest")
            out.append(raw)
            continue
        row = dict(raw)
        if row.get("status") is not None:
            continue
        fid = row.get("fixture_id")
        home, away = row.get("home_key"), row.get("away_key")
        if home is None or away is None:
            if not fid:
                raise TransitionError(
                    f"results row {row!r} has neither fixture_id nor "
                    "home_key/away_key")
            parts = str(fid).split(":")
            if len(parts) != 3:
                raise TransitionError(f"malformed fixture_id {fid!r}")
            code, home, away = parts
            if code != manifest.season_code:
                raise TransitionError(
                    f"{fid}: season code {code!r} is not {manifest.season} "
                    f"({manifest.season_code!r})")
        fid = fid or fixture_id(manifest.season_code, home, away)
        unknown = {home, away} - clubs
        if unknown:
            raise TransitionError(
                f"{fid}: club(s) {sorted(unknown)} are not in the {manifest.season} "
                f"manifest, so the season it describes is not the season being walked")
        if row.get("date_played") is None:
            raise TransitionError(f"{fid}: results row has no date_played")
        if row.get("observed_at") is None:
            raise TransitionError(
                f"{fid}: results row has no observed_at. A row with no known-at "
                "stamp is visible at every cutoff, which is the leak the ledger "
                "exists to prevent")
        out.append(LiveRow(
            fixture_id=str(fid), home_key=str(home), away_key=str(away),
            date_played=_timestamp(row["date_played"]).normalize(),
            observed_at=_timestamp(row["observed_at"]),
            hg=_goals(row, "hg", str(fid)), ag=_goals(row, "ag", str(fid))))
    return tuple(out)


def visible_rows(rows: Sequence[LiveRow], cutoff=None,
                 observed_by=None) -> tuple[LiveRow, ...]:
    """The rows a forecast at ``cutoff`` may see, in walk order.

    Bitemporal, mirroring ``epl.season._visible_results``: a row is visible iff
    it was played strictly before the cutoff DAY and was observed by
    ``observed_by`` (default: the cutoff). Where several rows describe one
    fixture — a correction is appended, never edited in place — the latest
    observation wins, ties broken by ledger order.

    ``cutoff=None`` drops the date bound only; the known-at bound still applies.
    """
    day = None if cutoff is None else _timestamp(cutoff).normalize()
    if observed_by is not None:
        obs = _timestamp(observed_by)
    elif cutoff is not None:
        obs = _timestamp(cutoff)
    else:
        obs = pd.Timestamp.max

    latest: dict[str, tuple[pd.Timestamp, int, LiveRow]] = {}
    for order, row in enumerate(rows):
        if row.observed_at > obs:
            continue
        if day is not None and row.date_played >= day:
            continue
        stamp = (row.observed_at, order)
        if row.fixture_id not in latest or stamp > latest[row.fixture_id][:2]:
            latest[row.fixture_id] = (row.observed_at, order, row)
    return tuple(sorted((v[2] for v in latest.values()),
                        key=lambda r: (r.key, r.fixture_id)))


def rows_to_frame(rows: Sequence[LiveRow], season: str) -> pd.DataFrame:
    """Live rows as a walk-forward frame (:func:`replay`'s input shape)."""
    return sort_for_walk_forward(pd.DataFrame({
        "match_id": [r.fixture_id for r in rows],
        "season": [season] * len(rows),
        "date": [r.date_played for r in rows],
        "kickoff": [pd.NaT] * len(rows),
        "home_key": [r.home_key for r in rows],
        "away_key": [r.away_key for r in rows],
        "fthg": [r.hg for r in rows],
        "ftag": [r.ag for r in rows],
        "ftr": [r.ftr for r in rows],
        "played": [True] * len(rows),
    }))


# ==========================================================================
# 2. the walk — `compute_elo_history`'s inner loop, over an arbitrary frame
# ==========================================================================
@dataclass
class ReplayResult:
    """What one replay did.

    ``ratings`` is the table AFTER the last block (the same dict object that was
    passed in — the walk mutates in place, as ``compute_elo_history`` does).
    ``snapshots`` holds one record per block with the table as it stood when
    that block OPENED, which is the only state a forecast for a match in that
    block may use. ``history`` is one row per match in ``Anchor.history``'s
    shape.
    """

    ratings: dict[str, float]
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    history: pd.DataFrame = field(default_factory=pd.DataFrame)


def replay(ratings: dict[str, float], frame: pd.DataFrame,
           config: epl_elo.EloConfig, *, promoted: Iterable[str] = (),
           season_index: int = 0, block_offset: int = 0) -> ReplayResult:
    """Walk ``frame`` block by block from ``ratings``, and report every step.

    Step for step this is the loop inside ``epl.elo.compute_elo_history``: the
    whole block is priced off the table standing when it opens, and only then
    does the block's own result update anything, so simultaneous matches cannot
    inform one another. The arithmetic is not re-derived — ``expected_score``
    and ``_mov_multiplier`` are imported — and the pre-ratings are held in a
    float64 array exactly as they are there, so the two loops agree to the last
    bit rather than to a tolerance. That equality is a test, not a claim:
    :mod:`epl.tests.test_liveanchor`.

    ``frame`` must already be in chronological order and must carry
    ``home_key``, ``away_key``, ``ftr``, ``fthg``, ``ftag``, ``date`` and
    ``kickoff``; blocks come from :mod:`epl.walk`, the single implementation of
    the cutoff, so a live walk and an archive walk group by the same rule.
    """
    cfg = config
    fresh = set(promoted)
    if frame is None or len(frame) == 0:
        return ReplayResult(ratings=ratings, snapshots=[],
                            history=pd.DataFrame(columns=list(HISTORY_COLUMNS)))

    block_ids = walk.block_index(frame)
    keys = walk.cutoff_keys(frame).to_numpy()
    home = frame["home_key"].to_numpy()
    away = frame["away_key"].to_numpy()
    ftr = frame["ftr"].astype(str).to_numpy()
    fthg = frame["fthg"].to_numpy(int)
    ftag = frame["ftag"].to_numpy(int)
    dates = pd.to_datetime(frame["date"]).to_numpy()
    match_id = (frame["match_id"].astype(str).to_numpy() if "match_id" in frame
                else np.array([f"{h}:{a}" for h, a in zip(home, away)]))
    season_col = (frame["season"].astype(str).to_numpy() if "season" in frame
                  else np.array([""] * len(frame)))

    n = len(frame)
    elo_h_pre = np.empty(n)
    elo_a_pre = np.empty(n)
    elo_h_post = np.empty(n)
    elo_a_post = np.empty(n)
    snapshots: list[dict[str, Any]] = []

    for rows in walk.groups(block_ids):
        snapshots.append({
            "block": int(block_ids[rows[0]]) + int(block_offset),
            "key": keys[rows[0]],
            "season": str(season_col[rows[0]]),
            "season_index": int(season_index),
            "row": int(rows[0]),
            "ratings": dict(ratings),
        })

        # --- price the whole block off the table standing right now ---------
        seen: set[str] = set()
        for i in rows:
            missing = sorted({home[i], away[i]} - set(ratings))
            if missing:
                raise TransitionError(
                    f"club(s) {missing} have no rating when {home[i]} v {away[i]} "
                    f"opens. A club plays only if the season transition seeded "
                    f"it: either the manifest is wrong or the walk started from "
                    f"the wrong table")
            if home[i] in seen or away[i] in seen:
                raise TransitionError(
                    f"club {home[i] if home[i] in seen else away[i]!r} appears "
                    "twice in one block, so its two matches would be priced off "
                    "the same ratings and update out of order")
            seen.update((home[i], away[i]))
            elo_h_pre[i] = ratings[home[i]]
            elo_a_pre[i] = ratings[away[i]]

        # --- then, and only then, learn from it ------------------------------
        for i in rows:
            e_home = epl_elo.expected_score(elo_h_pre[i], elo_a_pre[i],
                                            cfg.home_advantage)
            s_home = epl_elo._HOME_SCORE[ftr[i]]
            edge = elo_h_pre[i] + cfg.home_advantage - elo_a_pre[i]
            gd = int(fthg[i]) - int(ftag[i])
            mult = epl_elo._mov_multiplier(cfg, gd, edge if gd > 0 else -edge)
            delta = cfg.k * mult * (s_home - e_home)
            ratings[home[i]] = elo_h_pre[i] + delta
            ratings[away[i]] = elo_a_pre[i] - delta
            elo_h_post[i] = ratings[home[i]]
            elo_a_post[i] = ratings[away[i]]

    history = pd.DataFrame({
        "match_id": match_id,
        "season": season_col,
        "season_index": np.full(n, int(season_index), dtype=int),
        "block": block_ids + int(block_offset),
        "date": dates,
        "home_key": home,
        "away_key": away,
        "elo_home_pre": elo_h_pre,
        "elo_away_pre": elo_a_pre,
        "elo_diff_pre": elo_h_pre - elo_a_pre,
        "elo_home_post": elo_h_post,
        "elo_away_post": elo_a_post,
        "home_promoted": np.array([h in fresh for h in home]),
        "away_promoted": np.array([a in fresh for a in away]),
        "ftr": ftr,
    })[list(HISTORY_COLUMNS)]
    return ReplayResult(ratings=ratings, snapshots=snapshots, history=history)


# ==========================================================================
# 3. the transition
# ==========================================================================
def _season_clubs(history: pd.DataFrame, season: str) -> set[str]:
    rows = history.loc[history["season"].astype(str) == season]
    return set(rows["home_key"].astype(str)) | set(rows["away_key"].astype(str))


def _open_target(anchor: Anchor, manifest: Manifest,
                 config: epl_elo.EloConfig,
                 ) -> tuple[dict[str, float], dict[str, Any]]:
    """The opening table and the season-start record. See :func:`open_target_season`."""
    history = anchor.history
    if history.empty:
        raise TransitionError("the archive anchor has no history to transition from")
    last_season = str(history["season"].astype(str).iloc[-1])
    if last_season != manifest.prev_season:
        raise TransitionError(
            f"the archive ends in {last_season} but the {manifest.season} manifest "
            f"transitions from {manifest.prev_season}. Re-ingest the archive or fix "
            "the manifest — a transition from the wrong season silently mis-seeds "
            "every promoted club")

    prev_clubs = _season_clubs(history, last_season)
    if prev_clubs != set(manifest.prev_season_clubs):
        raise TransitionError(
            f"{last_season} in the archive holds {sorted(prev_clubs)}, the manifest "
            f"says {sorted(manifest.prev_season_clubs)}: the division mean would be "
            "taken over the wrong twenty")
    expected = len(prev_clubs) * (len(prev_clubs) - 1)
    n_last = int((history["season"].astype(str) == last_season).sum())
    if n_last != expected:
        raise TransitionError(
            f"{last_season} has {n_last} matches in the archive, not {expected}: "
            "the season is incomplete, and a transition out of an unfinished "
            "season would carry a half-formed division mean into the next one")

    ever_seen = (set(history["home_key"].astype(str))
                 | set(history["away_key"].astype(str)))
    ratings = anchor._final_ratings()
    record = epl_elo._open_season(config, ratings, prev_clubs,
                                  set(manifest.clubs), manifest.season,
                                  ever_seen)
    missing = sorted(set(manifest.clubs) - set(ratings))
    if missing:                      # unreachable by construction; asserted anyway
        raise TransitionError(f"transition left {missing} unrated")
    return ratings, record


def open_target_season(anchor: Anchor, manifest: Manifest,
                       config: epl_elo.EloConfig) -> dict[str, float]:
    """The target season's OPENING rating table, seeded from the manifest.

    Runs ``epl.elo._open_season`` — the one implementation of the frozen
    season-boundary rules — against the archive's final table, with
    ``prev_clubs`` the twenty clubs that completed the last archived season,
    ``clubs`` the twenty in the manifest (NOT whichever clubs happen to have
    played already), and ``ever_seen`` every club the archive contains. So the
    three promoted clubs enter at ``division_mean + promoted_offset`` whether or
    not they have ever appeared before, the seventeen continuing clubs are
    regressed by ``1 - carryover``, and clubs that were relegated keep their
    ratings in the table but out of the league.

    The three guards above it are not decoration. A manifest that transitions
    from a season the archive does not end in, disagrees with the archive about
    who was in it, or points at an unfinished season would each produce a
    plausible-looking table with the wrong division mean, and nothing
    downstream would notice.
    """
    return _open_target(anchor, manifest, config)[0]


# ==========================================================================
# 4. the live anchor
# ==========================================================================
class LiveAnchor:
    """``Anchor`` for a season in progress: explicit transition + live walk.

    Duck-types :meth:`epl.anchor.Anchor.state`, which is the whole interface
    ``epl.dcfit.fit_epl`` uses (dcfit.py:261), so a fit takes this object in
    place of an ``Anchor`` and changes nothing else.

    ``archive_matches`` is the completed-season archive; it must NOT contain the
    target season, because a plain ``Anchor`` over it would re-seed from the
    rows present and undo the point of this class. ``live_results_rows`` is the
    target season's results ledger (:mod:`epl.season`, plan v2 D4) — the only
    source of "played", never the calendar.
    """

    def __init__(self, archive_matches: pd.DataFrame,
                 live_results_rows: Iterable[Any], manifest: Manifest,
                 config: epl_elo.EloConfig):
        frame = archive_matches
        if "played" in frame.columns:
            frame = frame.loc[frame["played"]]
        frame = sort_for_walk_forward(frame)
        intruders = int((frame["season"].astype(str) == manifest.season).sum())
        if intruders:
            raise TransitionError(
                f"{intruders} {manifest.season} row(s) are in the archive handed to "
                "LiveAnchor. The target season must come from the results ledger "
                "only: an Anchor built over it would re-seed from the rows present, "
                "which is the bug this class exists to fix")
        if _season_code(manifest.season) != manifest.season_code:
            raise TransitionError(
                f"manifest season_code {manifest.season_code!r} does not match "
                f"{manifest.season}")

        self.config = config
        self.manifest = manifest
        self.archive = Anchor(frame, config)
        self.rows = normalise_rows(live_results_rows, manifest)
        self._opening, self.open_record = _open_target(self.archive, manifest,
                                                       config)
        self._archive_keys = self.archive._keys
        self._season_index = int(self.archive.history["season_index"].max()) + 1
        self._block_offset = int(self.archive.history["block"].max()) + 1
        self._cache: dict[tuple[Any, Any], ReplayResult] = {}

    # --- the transition ---------------------------------------------------
    def opening_table(self) -> dict[str, float]:
        """The target season's rating table before any of it has been played."""
        return dict(self._opening)

    @property
    def promoted_seed(self) -> float:
        """``division_mean + promoted_offset`` for the target season."""
        seed = self.open_record["promoted_seed"]
        return float(self.open_record["division_mean"] if seed is None else seed)

    def cold_start_for(self, fitted_teams: Iterable[str]) -> list[str]:
        """Manifest clubs the fit has no match for — ``fit_epl``'s ``cold_start``.

        ``epl.dcfit.cold_start_clubs`` cannot answer this for the target season:
        it derives the season from PLAYED history at or after the cutoff
        (dcfit.py:183-191), and at the opener there is none, so it returns ``[]``
        and the promoted club is never added. The manifest knows who is in the
        league without waiting for a result.
        """
        return sorted(set(self.manifest.clubs) - set(fitted_teams))

    # --- the walk ---------------------------------------------------------
    def _replay_at(self, cutoff, observed_by=None) -> ReplayResult:
        # The cache key must be the RESOLVED (day, observed_by) pair, not the
        # arguments: two intraday cutoffs on the same day share a day but not
        # necessarily a known-at bound, and serving one's walk for the other
        # would show a result before it was observed.
        day = None if cutoff is None else _timestamp(cutoff).normalize()
        if observed_by is not None:
            obs = _timestamp(observed_by)
        elif cutoff is not None:
            obs = _timestamp(cutoff)
        else:
            obs = pd.Timestamp.max
        key = (day, obs)
        if key not in self._cache:
            rows = visible_rows(self.rows, day, obs)
            self._cache[key] = replay(
                dict(self._opening), rows_to_frame(rows, self.manifest.season),
                self.config, promoted=self.open_record["promoted"],
                season_index=self._season_index,
                block_offset=self._block_offset)
        return self._cache[key]

    def ratings_at(self, cutoff, observed_by=None) -> dict[str, float]:
        """The target season's rating table as it stands at ``cutoff``."""
        return dict(self._replay_at(cutoff, observed_by).ratings)

    def state(self, cutoff, teams: Sequence[str],
              observed_by=None) -> AnchorState:
        """Ratings as of ``cutoff``, with the z-scale set by ``teams``.

        Delegates to the archive ``Anchor`` for any cutoff that still resolves
        to an archived block — the archive's own snapshots are authoritative
        there, and re-deriving them would be a second answer to a question that
        already has one. Past the last archived block it returns the transitioned
        table advanced through every live result visible at the cutoff.

        The z-scale is computed over ``teams`` (the FITTED teams), exactly as
        ``Anchor.state`` does, so a cold-start club is placed on that scale
        rather than moving it.

        ``observed_by`` bounds the LIVE ledger only, and has no effect on the
        delegated branch: the archive is a completed record with no known-at
        dimension, so there is nothing there a later observation could reveal.
        """
        cutoff = pd.Timestamp(cutoff)
        pos = int(np.searchsorted(self._archive_keys, cutoff.to_datetime64(),
                                  side="left"))
        if pos < len(self._archive_keys):
            return self.archive.state(cutoff, teams)

        ratings = self._replay_at(cutoff, observed_by).ratings
        missing = [t for t in teams if t not in ratings]
        if missing:
            raise KeyError(
                f"fitted team(s) {sorted(missing)} have no rating at "
                f"{cutoff.date()}: they are neither in the {self.manifest.season} "
                "manifest nor anywhere in the archive the transition opened from")
        r = np.array([ratings[t] for t in teams], dtype=float)
        sd = float(np.std(r)) if r.size else 0.0
        return AnchorState(cutoff=cutoff, ratings=dict(ratings),
                           teams=tuple(teams),
                           mean=float(np.mean(r)) if r.size else 0.0, sd=sd)

    def history_frame(self, cutoff=None, observed_by=None) -> pd.DataFrame:
        """Archive history plus the live rows, in ``Anchor.history``'s shape.

        What the ordered-logit head consumes: ``elo_diff_pre`` and ``ftr`` per
        match, in ``block`` order, where a row's pre-ratings are a function of
        strictly earlier blocks only. Live blocks continue the archive's
        numbering so "strictly earlier" keeps meaning what it means.
        """
        res = self._replay_at(cutoff, observed_by)
        if res.history.empty:
            return self.archive.history.copy()
        return pd.concat([self.archive.history, res.history], ignore_index=True)
