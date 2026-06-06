"""Per-fixture forecast artifacts (scoreline shortlist + full grid + 1X2) and the
schedule assembly over the tournament fixtures. All numbers are Direct outputs of the
scoreline Posterior (spec §10)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def scoreline_shortlist(grid: np.ndarray, *, top: int = 6) -> list[dict]:
    """Top-N most-likely scorelines from the joint grid[h, a], each with its probability."""
    flat = [
        {"home_goals": int(h), "away_goals": int(a), "prob": float(grid[h, a])}
        for h in range(grid.shape[0]) for a in range(grid.shape[1])
    ]
    flat.sort(key=lambda s: s["prob"], reverse=True)
    return flat[:top]


def fixture_forecast(posterior, *, home: str, away: str, neutral: bool,
                     max_goals: int = 10, top: int = 6) -> dict:
    """The forecast for one fixture: most-likely score (with its prob), the shortlist, the
    full joint grid, and the 1X2 split — the score never appears without its probability."""
    grid = posterior.predict_scoreline(home, away, neutral, max_goals)
    shortlist = scoreline_shortlist(grid, top=top)
    return {
        "home": home, "away": away,
        "most_likely": shortlist[0],
        "shortlist": shortlist,
        "grid": [[float(grid[h, a]) for a in range(grid.shape[1])]
                 for h in range(grid.shape[0])],
        "one_x_two": posterior.predict_1x2(home, away, neutral, max_goals),
    }


def build_schedule(fixtures: list[dict], *, cutoff: str) -> list[dict]:
    """Time-ordered schedule rows for every group fixture. Each row is identity + date +
    stage + played/upcoming status (vs the cutoff). The per-row forecast/edge is attached
    by the orchestrator (build.py); KO slots are added by tournament_view.build_tournament."""
    # Fixtures carry date-only strings (tz-naive); the cutoff may be tz-aware
    # (e.g. "...Z"). Compare on calendar date with tz dropped to avoid a tz-naive
    # vs tz-aware TypeError. tz_localize(None) is a no-op on already-naive cutoffs.
    cut = pd.Timestamp(cutoff)
    if cut.tz is not None:
        cut = cut.tz_localize(None)
    cut = cut.normalize()
    rows = []
    for fx in sorted(fixtures, key=lambda f: (str(f["date"]), f.get("home", ""))):
        d = pd.Timestamp(str(fx["date"]))
        rows.append({
            "home": fx["home"], "away": fx["away"], "date": str(fx["date"]),
            "group": fx.get("group"), "stage": "group",
            "status": "played" if d < cut else "upcoming",
        })
    return rows
