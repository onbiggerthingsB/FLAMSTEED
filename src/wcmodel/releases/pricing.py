"""Price release fixtures off the (cached) posterior — ONE call per fixture.

`neutral=True` already applies the identical environment term to both sides
(posterior.py: home_term = away_term = k_neutral*home_adv), so the grid is
order-consistent by construction; the dashboard prices with a single call and
so do we. Home fixtures (qualifiers) carry the fitted home advantage.
Orientation per Posterior.predict_1x2: home=tril, draw=trace, away=triu.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wcmodel.model.draw_api import PRODUCTION_MAX_GOALS

_TOTAL_LINES = (1.5, 2.5, 3.5)


def known_team_set(post) -> set[str]:
    idx = getattr(post, "_idx", None)
    if not isinstance(idx, dict):
        raise TypeError("posterior object has no team index dict `_idx`")
    return set(idx)


def price_fixtures(post, fixtures: pd.DataFrame,
                   max_goals: int = PRODUCTION_MAX_GOALS) -> list[dict]:
    out = []
    for _, r in fixtures.iterrows():
        g = np.asarray(post.predict_scoreline(
            r["home"], r["away"], neutral=bool(r["neutral"]), max_goals=max_goals))
        n = g.shape[0]
        goals = np.add.outer(np.arange(n), np.arange(n))
        totals = {f"over_{str(line).replace('.', '_')}": float(g[goals > line].sum())
                  for line in _TOTAL_LINES}
        hi, ai = np.unravel_index(int(g.argmax()), g.shape)
        out.append({
            "date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
            "home": str(r["home"]), "away": str(r["away"]),
            "neutral": bool(r["neutral"]),
            "one_x_two": {
                "home": float(np.tril(g, -1).sum()),
                "draw": float(np.trace(g)),
                "away": float(np.triu(g, 1).sum()),
            },
            "totals": totals,
            "modal_score": f"{hi}-{ai}",
            "modal_score_p": float(g[hi, ai]),
        })
    return out
