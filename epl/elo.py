"""Walk-forward Elo for a league — ratings that never see their own match.

Plain Elo, the textbook update, run match by match through :mod:`epl.walk`'s
cutoff so a match's rating is a function of strictly earlier matches only.
No margin of victory in the default configuration: the published bar this probe
is measured against (walk-forward Elo ~0.203 RPS on EPL) is plain Elo, and a
baseline that quietly includes a goal-difference multiplier would be a
different, stronger baseline wearing the same name. The multiplier is
implemented and switchable (:attr:`EloConfig.mov`) so it can be reported as a
sensitivity, never as the headline.

THE UPDATE.  With ``d = R_home + home_advantage - R_away``::

    E_home = 1 / (1 + 10 ** (-d / 400))
    S_home = 1.0 win / 0.5 draw / 0.0 loss
    R_home += K * (S_home - E_home)
    R_away -= K * (S_home - E_home)

Zero-sum, so total rating is conserved inside a season and moves only at a
season boundary, where the division's membership changes.

WHAT A LEAGUE NEEDS THAT AN INTERNATIONAL LADDER DOES NOT
---------------------------------------------------------
The World Cup model seeds every team at ``initial_rating`` 1500 and leaves the
ladder open. A domestic division is a closed 20-club pool with three clubs
swapped out every summer, so two extra rules are unavoidable, and both are
CHOICES that a later revision may want to revisit.

1. PROMOTED CLUBS ARE SEEDED BELOW THE DIVISION MEAN, at
   ``division_mean + promoted_offset`` with ``promoted_offset < 0`` — see
   :attr:`EloConfig.promoted_offset`. Seeding them AT the mean would assert
   that a club arriving from the second tier is an average Premier League club,
   which is false in a way the table settles every year: promoted clubs are
   over-represented in the relegation places, and the three clubs they replace
   were by construction the division's worst. The offset's magnitude is tuned
   on the earliest seasons only (:mod:`epl.baseline`) and then frozen.

   A club returning after a spell in the second tier gets the same seed as any
   other promotion — its old top-flight rating is NOT restored. That rating is
   at least a season stale, and the Championship season that earned the club
   its promotion is not in this dataset, so "remembered" would mean
   "remembered from before the evidence we do not have". Stated as a choice
   because the alternative (shrink the remembered rating toward the seed) is
   defensible too and is the obvious thing to try next.

2. RATINGS CARRY OVER BETWEEN SEASONS ONLY PARTLY, regressed toward the
   division mean by ``1 - carryover`` — see :attr:`EloConfig.carryover`.
   Squads turn over in the summer, so a June rating is a noisier estimate of
   August strength than of May strength. ``carryover = 1.0`` (no regression) is
   inside the tuning grid, so the data is allowed to say this rule is not
   needed.

The two rules interact in a way worth stating because it keeps the scale
honest: the 17 continuing clubs are, by construction, better than the 20 that
started the season (the 3 relegated were the worst), so re-seeding 3 clubs at
``mean + offset`` roughly cancels that upward drift when ``offset`` is near
minus the relegated clubs' shortfall. The league mean is reported per season
(:func:`compute_elo_history` -> ``season_start_ratings``) so any residual drift
is visible rather than silent. Drift is harmless to the forecast either way —
the head downstream reads only rating DIFFERENCES — but a mean sliding by
hundreds of points would mean the seeding rule was mis-specified.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

from epl import walk
from epl.schema import sort_for_walk_forward

__all__ = ["EloConfig", "DEFAULT_CONFIG", "compute_elo_history", "expected_score"]

_ELO_SCALE = 400.0

#: Realised score for the home team, by the source's FTR label.
_HOME_SCORE = {"H": 1.0, "D": 0.5, "A": 0.0}


@dataclass(frozen=True)
class EloConfig:
    """A frozen Elo specification. Every field is a modelling choice.

    ``k``
        Update gain in rating points. Large K tracks form and amplifies noise;
        small K is stable and slow. Tuned on the earliest seasons only.
    ``home_advantage``
        Rating points added to the home side when forming the EXPECTED score in
        the update. This is the update-side home advantage only: the 1X2 head
        downstream absorbs any constant shift into its own thresholds (every
        league match has a home team, so the indicator is constant), which is
        why this parameter changes forecasts through the ratings it produces
        rather than directly. Tuned on the earliest seasons only.
    ``initial_rating``
        Rating for every club in the first season of the archive. Arbitrary and
        harmless: only differences are used downstream, and the first season is
        burn-in that is never scored.
    ``promoted_offset``
        Rating points BELOW the completed season's 20-club division mean at
        which a promoted club enters. Negative by intent — see the module
        docstring. Tuned on the earliest seasons only.
    ``carryover``
        Fraction of a continuing club's deviation from the division mean that
        survives the summer: ``R <- mean + carryover * (R - mean)``. 1.0 keeps
        the rating intact. Tuned on the earliest seasons only.
    ``mov``
        Enable the goal-difference multiplier. OFF in the default config: the
        published ~0.203 bar is plain Elo. Sensitivity only.
    ``mov_shape`` / ``mov_base`` / ``mov_autocorr``
        Multiplier constants, in the widely used form
        ``((|gd| + 1) ** mov_shape) / (mov_base + mov_autocorr * d_winner)``
        where ``d_winner`` is the winner's pre-match rating edge. Inert while
        ``mov`` is False.
    """

    k: float = 20.0
    home_advantage: float = 60.0
    initial_rating: float = 1500.0
    promoted_offset: float = -150.0
    carryover: float = 1.0
    mov: bool = False
    mov_shape: float = 0.8
    mov_base: float = 7.5
    mov_autocorr: float = 0.006

    def __post_init__(self) -> None:
        if not (self.k > 0):
            raise ValueError(f"k must be positive; got {self.k}")
        if not (0.0 <= self.carryover <= 1.0):
            raise ValueError(
                f"carryover is the surviving FRACTION of a club's deviation "
                f"from the division mean and must lie in [0, 1]; got "
                f"{self.carryover}")
        if self.promoted_offset > 0:
            raise ValueError(
                f"promoted_offset={self.promoted_offset} would seed promoted "
                "clubs ABOVE the division mean, asserting that arriving from "
                "the second tier is evidence of strength; pass a negative "
                "offset (or exactly 0 to seed at the mean, deliberately)")

    def as_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}

    def replace(self, **kw: Any) -> "EloConfig":
        return replace(self, **kw)


#: Placeholder only. The configuration actually used for scoring is SELECTED on
#: the earliest seasons by `epl.baseline.tune` and frozen there; nothing should
#: score a later season with these numbers by default.
DEFAULT_CONFIG = EloConfig()


def expected_score(rating_home: float, rating_away: float,
                   home_advantage: float) -> float:
    """Elo's expected home score in [0, 1] — the logistic on the rating edge."""
    d = (float(rating_home) + float(home_advantage) - float(rating_away))
    return 1.0 / (1.0 + 10.0 ** (-d / _ELO_SCALE))


def _mov_multiplier(cfg: EloConfig, goal_diff: int, edge_winner: float) -> float:
    """Goal-difference gain multiplier; 1.0 when the multiplier is disabled."""
    if not cfg.mov:
        return 1.0
    return ((abs(int(goal_diff)) + 1.0) ** cfg.mov_shape) / (
        cfg.mov_base + cfg.mov_autocorr * float(edge_winner))


def compute_elo_history(matches: pd.DataFrame, config: EloConfig | None = None,
                        ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Walk `matches` forward, returning per-match PRE ratings and post ratings.

    Returns ``(history, season_starts)``.

    ``history`` has one row per input match, in chronological order, carrying
    ``elo_home_pre`` / ``elo_away_pre`` — the ratings as of the last block that
    is strictly earlier than the match, i.e. the only ratings a forecast for it
    may use — plus the post-update ratings and bookkeeping columns
    (``block``, ``home_promoted`` / ``away_promoted``, ``season_index``).

    ``season_starts`` records, per season, the division mean carried in, the
    promoted clubs and their seed, and the resulting 20-club mean — the numbers
    that make the seeding rule auditable instead of merely documented.

    Point-in-time by construction: every match in a block is priced off the
    ratings standing when the block opens, and the whole block's updates are
    applied only after all of its matches have been priced. Matches that are
    simultaneous under the cutoff rule therefore cannot inform one another, and
    since no block in this archive contains a club twice (checked below), the
    order of updates inside a block is immaterial.
    """
    cfg = config or DEFAULT_CONFIG
    df = sort_for_walk_forward(matches)
    if not df["played"].all():
        raise ValueError(f"{int((~df['played']).sum())} unplayed match(es) in "
                         "the frame; an Elo walk needs results")

    block_ids = walk.block_index(df)
    seasons = df["season"].to_numpy()
    home = df["home_key"].to_numpy()
    away = df["away_key"].to_numpy()
    ftr = df["ftr"].astype(str).to_numpy()
    fthg = df["fthg"].to_numpy(int)
    ftag = df["ftag"].to_numpy(int)

    # Seasons must not interleave: the season-boundary rule fires on a change
    # of the season label while walking forward, so an archive whose seasons
    # overlap in time would re-seed mid-season.
    change = np.flatnonzero(seasons[1:] != seasons[:-1]) + 1
    order = [seasons[0], *seasons[change]]
    if len(set(order)) != len(order):
        raise ValueError(f"seasons interleave in chronological order: {order}")

    n = len(df)
    elo_h_pre = np.empty(n)
    elo_a_pre = np.empty(n)
    elo_h_post = np.empty(n)
    elo_a_post = np.empty(n)
    promoted_h = np.zeros(n, dtype=bool)
    promoted_a = np.zeros(n, dtype=bool)
    season_index = np.empty(n, dtype=int)

    ratings: dict[str, float] = {}
    fresh: set[str] = set()          # clubs seeded into the CURRENT season
    current_season: str | None = None
    prev_clubs: set[str] = set()
    season_starts: list[dict[str, Any]] = []
    season_no = -1

    for rows in walk.blocks(df):
        season = seasons[rows[0]]
        if season != current_season:
            if len(set(seasons[rows])) != 1:
                raise ValueError("a cutoff block spans two seasons")
            season_no += 1
            clubs = set(home[seasons == season]) | set(away[seasons == season])
            record = _open_season(cfg, ratings, prev_clubs, clubs, season)
            record["season_index"] = season_no
            season_starts.append(record)
            fresh = set(record["promoted"])
            prev_clubs = clubs
            current_season = season

        # --- price the whole block off the ratings standing right now -------
        seen: set[str] = set()
        for i in rows:
            if home[i] in seen or away[i] in seen:
                raise ValueError(
                    f"club {home[i] if home[i] in seen else away[i]!r} appears "
                    "twice in one cutoff block, so its two matches would be "
                    "priced off the same ratings and update out of order")
            seen.update((home[i], away[i]))
            elo_h_pre[i] = ratings[home[i]]
            elo_a_pre[i] = ratings[away[i]]
            promoted_h[i] = home[i] in fresh
            promoted_a[i] = away[i] in fresh
            season_index[i] = season_no

        # --- then, and only then, learn from it -----------------------------
        for i in rows:
            e_home = expected_score(elo_h_pre[i], elo_a_pre[i],
                                    cfg.home_advantage)
            s_home = _HOME_SCORE[ftr[i]]
            edge = elo_h_pre[i] + cfg.home_advantage - elo_a_pre[i]
            gd = int(fthg[i]) - int(ftag[i])
            # The multiplier reads the WINNER's edge, which is the losing
            # side's edge negated; a draw has no winner and no margin.
            mult = _mov_multiplier(cfg, gd, edge if gd > 0 else -edge)
            delta = cfg.k * mult * (s_home - e_home)
            ratings[home[i]] = elo_h_pre[i] + delta
            ratings[away[i]] = elo_a_pre[i] - delta
            elo_h_post[i] = ratings[home[i]]
            elo_a_post[i] = ratings[away[i]]

    history = pd.DataFrame({
        "match_id": df["match_id"].to_numpy(),
        "season": seasons,
        "season_index": season_index,
        "block": block_ids,
        "date": df["date"].to_numpy(),
        "home_key": home,
        "away_key": away,
        "elo_home_pre": elo_h_pre,
        "elo_away_pre": elo_a_pre,
        "elo_diff_pre": elo_h_pre - elo_a_pre,
        "elo_home_post": elo_h_post,
        "elo_away_post": elo_a_post,
        "home_promoted": promoted_h,
        "away_promoted": promoted_a,
        "ftr": ftr,
    })
    return history, season_starts


def _open_season(cfg: EloConfig, ratings: dict[str, float],
                 prev_clubs: set[str], clubs: set[str], season: str,
                 ) -> dict[str, Any]:
    """Apply the season-boundary rules in place; return what happened.

    First season: everyone starts at ``initial_rating``. Afterwards: the
    division mean is the mean over the 20 clubs that just COMPLETED a season
    (relegated clubs included — they are what made the mean what it is);
    continuing clubs regress toward it by ``1 - carryover``; promoted clubs are
    seeded at ``mean + promoted_offset`` with no memory of an earlier spell.
    """
    if not prev_clubs:
        for club in clubs:
            ratings[club] = cfg.initial_rating
        return {"season": season, "division_mean": cfg.initial_rating,
                "promoted": [], "promoted_seed": None,
                "continuing": len(clubs),
                "mean_after": cfg.initial_rating, "first_season": True}

    division_mean = float(np.mean([ratings[c] for c in sorted(prev_clubs)]))
    promoted = sorted(clubs - prev_clubs)
    seed = division_mean + cfg.promoted_offset
    for club in sorted(clubs & prev_clubs):
        ratings[club] = division_mean + cfg.carryover * (ratings[club]
                                                         - division_mean)
    for club in promoted:
        ratings[club] = seed
    return {
        "season": season,
        "division_mean": division_mean,
        "promoted": promoted,
        "promoted_seed": seed,
        "continuing": len(clubs & prev_clubs),
        "mean_after": float(np.mean([ratings[c] for c in sorted(clubs)])),
        "first_season": False,
    }
