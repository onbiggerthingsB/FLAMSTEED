"""The Bayesian model's strength anchor, made league-shaped. FIXES 1 AND 2.

WHAT THE ANCHOR IS. ``wcmodel``'s scoreline model does not learn each club's
attack and defence from a flat prior. With ``model.strength_prior.enabled`` the
per-team prior MEANS are ``k_att * elo_z[i]`` and ``k_def * elo_z[i]``, where
``elo_z`` is the club's point-in-time Elo rating, z-scored across the fitted
teams (``wcmodel.model.scoreline._priors``). So the rating system the anchor is
built from is a load-bearing part of the architecture, not a preprocessing
detail: it sets where every club's posterior starts, and it is the ONLY channel
through which a club with little match history gets any strength at all.

WHAT WAS WRONG WITH IT ON EPL DATA, and what this module does about it.

**Fix 1 — the K factor.** ``wcmodel.data.features.build`` tags every match with
``wcmodel.data.tiers.match_type(tournament)``. That taxonomy is a taxonomy of
INTERNATIONAL competitions — World Cup finals, continental qualifiers,
friendlies — and "Premier League" is not in it, so every EPL match falls to the
``other`` bucket and inherits ``k_base * k_by_match_type["other"]`` from the
international configuration. The K a domestic league wants is not the K a
national-team ladder wants (clubs play 38 times a season against a closed pool;
nations play a handful against an open one), and arriving at a number by
falling off the end of a lookup table is not calibration even when the number
turns out to be reasonable.

**Fix 2 — the promoted-club prior.** ``wcmodel.data.elo.compute_elo_history``
has no concept of a season boundary, because international football has none.
Every club it has never seen starts at ``initial_rating``; every club it has
seen keeps its rating forever. On a domestic league that is wrong twice over: a
promoted club enters at the archive-wide mean when it belongs near the
relegation zone, and a club returning after years in the second tier resumes at
a rating earned before evidence the archive does not contain. This package's
own Elo (:mod:`epl.elo`) implements both rules — a promoted seed at
``division_mean + promoted_offset`` and an optional summer carryover — and its
tuning found the promoted seed worth ~0.0030 RPS, the largest single
configuration effect measured on this data.

THE FIX, IN ONE SENTENCE: the model's anchor is computed by
:func:`epl.elo.compute_elo_history` under the frozen configuration — the SAME
function, the SAME parameters and the SAME rating table as the Elo baseline the
model is being compared against — instead of by ``wcmodel``'s
international-shaped Elo.

WHY THAT IS THE CONSERVATIVE CHOICE, not a thumb on the scale. The comparison
this probe exists to make is "does the Dixon-Coles architecture beat walk-
forward Elo". If the model's anchor ran a DIFFERENT rating system from the
baseline, a win could be the likelihood or it could be the anchor, and nothing
in the result would separate them. Giving both forecasters the identical rating
input removes that confound in the direction that makes the model's job HARDER:
the baseline's rating is now exactly the model's starting point, so the model
has to add something beyond it. The likelihood, the priors, the design, the
weighting, the inference backend and the posterior are imported unmodified from
``src/wcmodel``; nothing under ``src/`` or ``scripts/`` is written.

WHAT IS STILL ``wcmodel``'S ELO. The config block this module builds
(:func:`wcmodel_config`) still drives ``wcmodel``'s own Elo recompute inside
``features.build`` and ``count_volatility_arm``. After this change the panel's
``elo_pre`` column feeds nothing the model reads — ``to_match_panel`` drops it —
so its only live consumer is the provisional/volatility arm that decides which
clubs get predict-time widening. The K is set there too, so that arm is
evaluated at league scale rather than at ``k_base = 40``; see
:func:`wcmodel_config` for the one place the two rating systems still differ
(``wcmodel``'s Elo carries an unconditional margin-of-victory multiplier).

POINT-IN-TIME. A snapshot is the rating table as it stands when a cutoff block
OPENS — after any season re-seeding, before any of that block's results. It is
therefore a function of strictly earlier matches only, which is the same
guarantee ``epl.walk`` gives the baseline, enforced by the same code.
"""

from __future__ import annotations

import copy
import inspect
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd

from epl import elo as epl_elo, walk
from epl.schema import sort_for_walk_forward
from epl.season import SeasonError

__all__ = ["Anchor", "AnchorState", "anchor_state_at", "wcmodel_config",
           "mean_mov_multiplier", "TOURNAMENT_LABEL", "MATCH_TYPE"]

#: The ``tournament`` string every EPL row carries into the store.
TOURNAMENT_LABEL = "Premier League"

#: What ``wcmodel.data.tiers.match_type`` maps that string to. Not a guess —
#: asserted in :func:`wcmodel_config` against the live taxonomy, so a future
#: edit that adds a "Premier League" entry (or renames ``other``) fails loudly
#: instead of silently re-scaling K.
MATCH_TYPE = "other"


@dataclass(frozen=True)
class AnchorState:
    """The rating table standing at one cutoff, plus its z-scoring reference.

    ``ratings`` is every club the archive has seeded by this point, including
    clubs that have not yet played a match in the league (a promoted club is
    seeded when its season opens). ``mean`` / ``sd`` are computed over the
    FITTED teams only — the set the model's prior means were built for — so a
    cold-start club is placed on that scale rather than moving it.
    """

    cutoff: pd.Timestamp
    ratings: dict[str, float]
    teams: tuple[str, ...]
    mean: float
    sd: float

    def z(self, club: str) -> float:
        """z-score for any club with a rating, fitted or not."""
        if club not in self.ratings:
            raise KeyError(
                f"club {club!r} has no rating at {self.cutoff.date()}; it is "
                "not in the league this season, so nothing can price it")
        if self.sd <= 0.0 or not np.isfinite(self.sd):
            return 0.0
        return float((self.ratings[club] - self.mean) / self.sd)

    def elo_z(self, teams: Sequence[str] | None = None) -> np.ndarray:
        """The anchor array, aligned to ``teams`` (default: the fitted teams).

        Mirrors ``wcmodel.model.strength.team_elo_z``'s contract exactly — same
        shape, same population (ddof=0) z-scoring, same "no dispersion -> all
        zeros" degenerate case — so it is a drop-in for the array
        ``scoreline.fit`` would otherwise build. What differs is the RATING it
        z-scores, which is the whole point.
        """
        want = tuple(teams) if teams is not None else self.teams
        return np.array([self.z(t) for t in want], dtype=float)


class Anchor:
    """Point-in-time club ratings for the model, from :mod:`epl.elo`.

    Built ONCE over the whole archive and then queried per cutoff. The walk is
    ~20 ms, and building it once rather than per fit means every cutoff reads
    the same rating trajectory — a per-cutoff rebuild would be identical by
    construction but would invite a future edit that made it not.
    """

    def __init__(self, matches: pd.DataFrame, config: epl_elo.EloConfig):
        played = sort_for_walk_forward(matches.loc[matches["played"]])
        history, season_starts, snapshots = epl_elo.compute_elo_history(
            played, config, capture_snapshots=True)
        self.config = config
        self.history = history
        self.season_starts = season_starts
        self._snapshots = snapshots
        self._keys = np.array([s["key"] for s in snapshots])
        # The invariant that makes this trustworthy: the rating a snapshot
        # hands out for a club MUST equal the `elo_*_pre` the baseline used to
        # price that club's match in that same block. If those two ever
        # disagree, the model and the baseline are running different ratings
        # and every comparison downstream is confounded. Checked here, on real
        # data, at construction — not asserted in a docstring.
        self._verify_snapshots()

    def _verify_snapshots(self) -> None:
        block = self.history["block"].to_numpy()
        home = self.history["home_key"].to_numpy()
        away = self.history["away_key"].to_numpy()
        pre_h = self.history["elo_home_pre"].to_numpy(float)
        pre_a = self.history["elo_away_pre"].to_numpy(float)
        by_block = {s["block"]: s["ratings"] for s in self._snapshots}
        for i in range(len(self.history)):
            snap = by_block[int(block[i])]
            if snap[home[i]] != pre_h[i] or snap[away[i]] != pre_a[i]:
                raise AssertionError(
                    f"snapshot disagrees with the baseline's pre-match rating "
                    f"at row {i} ({home[i]} vs {away[i]}): the model's anchor "
                    "and the Elo baseline would be running different ratings")

    def state(self, cutoff, teams: Sequence[str]) -> AnchorState:
        """Ratings as of ``cutoff``, with the z-scale set by ``teams``.

        ``cutoff`` is resolved to the FIRST cutoff block at or after it — the
        block a fit at that moment would be used to price — and that block's
        opening rating table is returned. A cutoff past the last block returns
        the final table.

        RESOLUTION, and a small asymmetry worth naming. ``wcmodel``'s feature
        layer filters ``date < cutoff.normalize()``, so a model fit is
        DAY-resolution: a cutoff of 2018-01-06 sees nothing from 2018-01-06,
        not even a 12:30 kickoff, and this function passed that midnight
        returns the ratings standing before the whole matchday. This package's
        Elo baseline is KICKOFF-resolution and would price a 17:30 match with
        the 12:30 result already in. The difference is not a leak in either
        direction — the model sees strictly LESS — but it does mean the
        model's anchor is a little staler within a matchday than its
        comparator's, and staler still between refits. Passing an exact
        kickoff key resolves to that kickoff's block, which is how the
        invariant against the baseline is checked.
        """
        cutoff = pd.Timestamp(cutoff)
        pos = int(np.searchsorted(self._keys, cutoff.to_datetime64(),
                                  side="left"))
        if pos >= len(self._snapshots):
            ratings = self._final_ratings()
        else:
            ratings = dict(self._snapshots[pos]["ratings"])
        missing = [t for t in teams if t not in ratings]
        if missing:
            raise KeyError(
                f"fitted team(s) {sorted(missing)} have no rating at "
                f"{cutoff.date()}, which cannot happen: a club is in the "
                "model's team index only because it has a pre-cutoff match, "
                "and a played match implies a rating")
        r = np.array([ratings[t] for t in teams], dtype=float)
        sd = float(np.std(r)) if r.size else 0.0
        return AnchorState(cutoff=cutoff, ratings=ratings, teams=tuple(teams),
                           mean=float(np.mean(r)) if r.size else 0.0, sd=sd)

    def _final_ratings(self) -> dict[str, float]:
        last = self.history.iloc[-1]
        ratings = dict(self._snapshots[-1]["ratings"])
        block = int(last["block"])
        rows = self.history.index[self.history["block"] == block]
        for i in rows:
            ratings[self.history.at[i, "home_key"]] = float(
                self.history.at[i, "elo_home_post"])
            ratings[self.history.at[i, "away_key"]] = float(
                self.history.at[i, "elo_away_post"])
        return ratings

    def promoted_seed(self, season: str) -> float:
        """The rating a club promoted into ``season`` is seeded at."""
        for rec in self.season_starts:
            if rec["season"] == season:
                seed = rec["promoted_seed"]
                return float(rec["division_mean"] if seed is None else seed)
        raise KeyError(f"no season-start record for {season!r}")


# --------------------------------------------------------------------------
# the wcmodel config block (FIX 1, at its remaining live consumer)
# --------------------------------------------------------------------------
def mean_mov_multiplier(matches: pd.DataFrame) -> float:
    """Mean of ``wcmodel``'s goal-difference multiplier over these matches.

    ``wcmodel.data.elo`` multiplies every update by the World Football Elo
    margin index ``G`` — 1.0 for a draw or a one-goal win, 1.5 for two,
    ``(11+m)/8`` beyond — with no switch to turn it off. This package's Elo has
    the multiplier OFF in the frozen configuration, because the published bar
    it reproduces is plain Elo. So the two rating systems cannot be made
    identical by choosing K: at equal nominal K, ``wcmodel``'s updates are this
    factor larger on average. The number is reported rather than compensated
    for, because the only ``wcmodel`` Elo still live after this module is the
    provisional/volatility arm, where a 26% scale difference changes which
    clubs get widened and nothing else.
    """
    gd = (matches["fthg"].to_numpy(int) - matches["ftag"].to_numpy(int))
    m = np.abs(gd)
    g = np.where(m <= 1, 1.0, np.where(m == 2, 1.5, (11.0 + m) / 8.0))
    return float(g.mean())


def wcmodel_config(base: dict, config: epl_elo.EloConfig,
                   anchor_spec: str) -> dict:
    """A deep copy of the shipped config with the EPL ``elo`` block written in.

    Threaded into ``features.build`` / ``count_volatility_arm`` through their
    existing ``config=`` parameter — the documented seam for exactly this ("a
    custom ``cfg['elo']`` thus actually drives ``elo_pre`` + the provisional
    flags"). Nothing under ``src/`` is touched.

    ``anchor_spec`` is a short token describing WHICH anchor the fit used. It
    is stored inside the ``elo`` block for one reason: ``wcmodel``'s posterior
    cache key hashes ``cfg["elo"]`` wholesale, and the anchor is NOT otherwise
    in that key (the cached panel hash covers goals and teams, not ratings). A
    cache that could not tell two anchors apart would serve one fit's posterior
    for another's — silently, and in the direction that hides a bug. The token
    makes the key honest. ``wcmodel``'s Elo reads named keys and ignores extra
    ones, so it changes no computation.
    """
    live_type = _match_type(TOURNAMENT_LABEL)
    if live_type != MATCH_TYPE:
        raise AssertionError(
            f"wcmodel.data.tiers.match_type({TOURNAMENT_LABEL!r}) is now "
            f"{live_type!r}, not {MATCH_TYPE!r}: the K this config sets would "
            "no longer be the K an EPL match receives")
    cfg = copy.deepcopy(base)
    mult = float(cfg["elo"]["k_by_match_type"][MATCH_TYPE])
    if mult <= 0:
        raise ValueError(f"k_by_match_type[{MATCH_TYPE!r}] is {mult}")
    cfg["elo"]["k_base"] = float(config.k) / mult
    cfg["elo"]["home_advantage"] = float(config.home_advantage)
    cfg["elo"]["initial_rating"] = float(config.initial_rating)
    cfg["elo"]["epl_anchor_spec"] = anchor_spec
    return cfg


def _match_type(tournament: str) -> str:
    from wcmodel.data import tiers as wc_tiers
    return wc_tiers.match_type(tournament)


def anchor_state_at(anchor, cutoff, teams: Sequence[str],
                    observed_by=None) -> AnchorState:
    """``anchor.state``, with the knowledge bound given to anchors that HAVE one.

    A6 (c): ``observed_by`` bounds the whole forecast, the DC fit's Elo
    covariates included. Two anchors reach this function and only one of them
    has a known-at dimension:

    * :class:`epl.liveanchor.LiveAnchor` replays a bitemporal results ledger, so
      a result filed after ``observed_by`` must not reach the ratings. Dropping
      the bound here is the leak all five final-state reviews report as their
      P0: the state saw no results and the anchor saw one.
    * :class:`epl.anchor.Anchor` is the archive's own snapshot table. A completed
      season is a closed record with nothing a later observation could reveal,
      so it takes no such argument and needs none.

    Which of the two we hold is read off the SIGNATURE, not guessed from the
    type and not discovered by catching :class:`TypeError` — a ``TypeError``
    raised deep inside a replay would otherwise be swallowed and silently
    downgraded into an unbounded call, which is the failure this exists to stop.
    An object that is neither is REFUSED: an anchor that cannot state the
    knowledge bound it was built under is not trusted to have respected one.
    """
    if observed_by is None:
        return anchor.state(cutoff, teams)
    state = getattr(anchor, "state", None)
    if state is None:
        raise SeasonError(f"{type(anchor).__name__} is not an anchor: it has no state()")
    if "observed_by" in inspect.signature(state).parameters:
        return state(cutoff, teams, observed_by=observed_by)
    if isinstance(anchor, Anchor):
        # The archive branch: no known-at dimension, so the bound is satisfied
        # by construction rather than ignored.
        return state(cutoff, teams)
    raise SeasonError(
        f"{type(anchor).__name__}.state() takes no knowledge bound, and this "
        f"forecast declares observed_by={observed_by}. An anchor that cannot "
        "state the bound it was built under is refused rather than re-entered "
        "without one (amendment A6 (c)).")
