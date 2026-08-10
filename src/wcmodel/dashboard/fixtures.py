"""Per-fixture forecast artifacts (scoreline shortlist + full grid + 1X2) and the
schedule assembly over the tournament fixtures. All numbers are Direct outputs of the
scoreline Posterior (spec §10)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from wcmodel.dashboard.spread import cover_line
from wcmodel.model.draw_api import PRODUCTION_MAX_GOALS
from wcmodel.model.markets import project_all


def scoreline_shortlist(grid: np.ndarray, *, top: int = 6) -> list[dict]:
    """Top-N most-likely scorelines from the joint grid[h, a], each with its probability."""
    flat = [
        {"home_goals": int(h), "away_goals": int(a), "prob": float(grid[h, a])}
        for h in range(grid.shape[0]) for a in range(grid.shape[1])
    ]
    flat.sort(key=lambda s: s["prob"], reverse=True)
    return flat[:top]


def fixture_forecast(posterior, *, home: str, away: str, neutral: bool,
                     max_goals: int = PRODUCTION_MAX_GOALS, top: int = 6,
                     host_factor: float | None = None) -> dict:
    """The forecast for one fixture: most-likely score (with its prob), the shortlist, the
    full joint grid, and the 1X2 split — the score never appears without its probability.

    ``host_factor`` (T5) is the prediction-time multiplier on the fitted ``home_adv`` for a
    2026 host's HOME game (``k*home_adv``); ``None`` (the default) keeps the existing
    ``neutral`` behaviour byte-identical. When set, it overrides the ``neutral`` flag's
    home term inside :meth:`Posterior.predict_scoreline` (the host plays at home)."""
    grid = posterior.predict_scoreline(home, away, neutral, max_goals, host_factor=host_factor)
    shortlist = scoreline_shortlist(grid, top=top)
    return {
        "home": home, "away": away,
        "most_likely": shortlist[0],
        "shortlist": shortlist,
        "grid": [[float(grid[h, a]) for a in range(grid.shape[1])]
                 for h in range(grid.shape[0])],
        "one_x_two": posterior.predict_1x2(home, away, neutral, max_goals,
                                           host_factor=host_factor),
        # ±1.5 goal-line cover pair (spec §10: DERIVED from the SAME scoreline grid — no model,
        # no odds). P(home covers −1.5) = Σ grid[h,a] over h−a>=2; P(away covers +1.5) is its
        # complement (half line, no push). cover_line reads the identical orientation
        # predict_1x2 uses, so home-cover ⊂ home-win by construction.
        "cover": cover_line(grid),
        # The ordinary football markets (spec §10: DERIVED from THIS grid — no model, no
        # odds, nothing fitted). Projected from ``grid`` itself rather than recomputed, so
        # the block cannot describe a different fixture than the one published above; the
        # 1X2 it carries is pinned equal to ``one_x_two`` by test.
        #
        # These are additional VIEWS of the same forecast, not additional accuracy. An
        # "over 1.5" number is right more often than a 1X2 number because the event is
        # more likely — each market is scored on its own record and never pooled.
        "markets": project_all(grid),
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
