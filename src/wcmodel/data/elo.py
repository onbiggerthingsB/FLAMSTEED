"""In-house computed Elo (point-in-time) + the 1X2 naive baseline.

ONE source of truth for ratings. `compute_elo_history` produces the ratings used
BOTH as a model feature (the point-in-time `rating_pre`) AND, via
`elo_1x2_baseline`, as the Phase-4 naive baseline. There is deliberately no
second, divergent Elo (the coherence requirement).

Point-in-time discipline: `rating_pre` is each team's rating *as of kickoff*
(knowable before the match) — that is the leakage-safe feature. `rating_post` is
the rating *after* the update and must never be used as a same-match feature.

Debutant handling: a team's first appearance starts at the SAME `initial_rating`
as everyone else (we do NOT fake a low point estimate). Its first
`provisional_games` matches are flagged `provisional=True` as a low-information
marker; the Phase-2 prior — not a rigged rating — handles the uncertainty.

`match_type` is an INPUT column on `matches` (used only to look up the K
importance multiplier). This module does not import the Task-6 tier taxonomy; an
unrecognised `match_type` falls back to the `other` multiplier. The real
results -> match_type wiring lands in Task 11.

Formulas are PINNED in ASSUMPTIONS.md; parameters are read from
`load_config()["elo"]` / `["baseline"]`.
"""
from __future__ import annotations

import pandas as pd

from wcmodel.config import load_config


def _mov_index(margin: int) -> float:
    """World Football Elo goal-difference (margin-of-victory) multiplier G.

    1 for a one-goal margin (or draw), 1.5 for a two-goal margin, then
    (11 + margin) / 8 for larger margins.
    """
    if margin <= 1:
        return 1.0
    if margin == 2:
        return 1.5
    return (11 + margin) / 8.0


def compute_elo_history(matches: pd.DataFrame) -> pd.DataFrame:
    """Deterministic, point-in-time Elo over a results frame.

    Input columns: `match_id`, `date`, `home_team`, `away_team`, `home_score`,
    `away_score`, `neutral`, `match_type`. Matches are processed in chronological
    order (stable mergesort on `date`, so equal-date order is preserved).

    Returns two rows per match (home and away perspective) with columns
    `{match_id, date, team, opponent, is_home, neutral, rating_pre,
    rating_post, provisional}`. `rating_pre` is the pre-match rating (the
    feature); `provisional` reflects whether the team had played fewer than
    `provisional_games` matches *before* this one. `neutral` is carried through
    (an input column, knowable at kickoff) so a row maps straight into
    `elo_1x2_baseline` without re-joining the source frame.
    """
    cfg = load_config()["elo"]
    initial_rating = cfg["initial_rating"]
    home_advantage = cfg["home_advantage"]
    k_base = cfg["k_base"]
    k_by_match_type = cfg["k_by_match_type"]
    provisional_games = cfg["provisional_games"]

    ordered = matches.sort_values("date", kind="mergesort")

    ratings: dict[str, float] = {}
    games_played: dict[str, int] = {}
    rows: list[dict] = []

    for m in ordered.itertuples(index=False):
        home, away = m.home_team, m.away_team
        hs, as_ = m.home_score, m.away_score

        home_pre = ratings.get(home, initial_rating)
        away_pre = ratings.get(away, initial_rating)

        ha = 0.0 if m.neutral else home_advantage
        dr = home_pre - away_pre + ha
        e_home = 1.0 / (1.0 + 10.0 ** (-dr / 400.0))
        e_away = 1.0 - e_home

        w_home = 1.0 if hs > as_ else 0.5 if hs == as_ else 0.0
        w_away = 1.0 - w_home

        g = _mov_index(abs(hs - as_))
        k = k_base * k_by_match_type.get(m.match_type, k_by_match_type["other"])

        home_post = home_pre + k * g * (w_home - e_home)
        away_post = away_pre + k * g * (w_away - e_away)

        # Provisional reflects games played BEFORE this match (evaluate first).
        home_provisional = games_played.get(home, 0) < provisional_games
        away_provisional = games_played.get(away, 0) < provisional_games

        rows.append({"match_id": m.match_id, "date": m.date, "team": home,
                     "opponent": away, "is_home": True, "neutral": m.neutral,
                     "rating_pre": home_pre, "rating_post": home_post,
                     "provisional": home_provisional})
        rows.append({"match_id": m.match_id, "date": m.date, "team": away,
                     "opponent": home, "is_home": False, "neutral": m.neutral,
                     "rating_pre": away_pre, "rating_post": away_post,
                     "provisional": away_provisional})

        ratings[home] = home_post
        ratings[away] = away_post
        games_played[home] = games_played.get(home, 0) + 1
        games_played[away] = games_played.get(away, 0) + 1

    return pd.DataFrame(
        rows,
        columns=["match_id", "date", "team", "opponent", "is_home", "neutral",
                 "rating_pre", "rating_post", "provisional"],
    )


def elo_1x2_baseline(rating_home: float, rating_away: float,
                     neutral: bool) -> dict[str, float]:
    """Naive Elo -> 1X2 probabilities (the Phase-4 baseline).

    Documented mapping from the SAME computed ratings as the feature:
    the win expectancy `E` sets the home/away split, and the draw mass shrinks
    as the match gets more lopsided (peaks at `draw_base` for an even match).
    Probabilities are clipped to >= 0 and renormalised to sum to 1.
    """
    cfg = load_config()
    home_advantage = cfg["elo"]["home_advantage"]
    draw_base = cfg["baseline"]["draw_base"]

    ha = 0.0 if neutral else home_advantage
    dr = rating_home - rating_away + ha
    e = 1.0 / (1.0 + 10.0 ** (-dr / 400.0))

    p_draw = draw_base * (1.0 - abs(2.0 * e - 1.0))
    p_home = e - p_draw / 2.0
    p_away = (1.0 - e) - p_draw / 2.0

    p_home, p_draw, p_away = (max(p, 0.0) for p in (p_home, p_draw, p_away))
    total = p_home + p_draw + p_away
    return {"home": p_home / total, "draw": p_draw / total, "away": p_away / total}
