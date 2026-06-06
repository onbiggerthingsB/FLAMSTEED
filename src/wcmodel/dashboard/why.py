"""The match-detail "why": team-strength posterior (attack/defense mean + 94% HDI, Direct
from the Posterior draws), xG coverage-gated (Direct but only where covered), and helpers
the orchestrator fills with rest days (Phase-1 feature) and recent form (raw result history,
Derived)."""
from __future__ import annotations

import numpy as np

from wcmodel.dashboard.schema import coverage_gap, no_impute


def _hdi(draws: np.ndarray, prob: float = 0.94) -> list[float]:
    """94% highest-density interval from 1-D posterior draws (sorted-window method)."""
    x = np.sort(np.asarray(draws, float))
    n = x.size
    k = max(1, int(np.floor(prob * n)))
    widths = x[k - 1:] - x[: n - k + 1]
    i = int(np.argmin(widths))
    return [float(x[i]), float(x[i + k - 1])]


def team_strength(posterior, team: str, prob: float = 0.94) -> dict:
    """Attack/defense posterior strength for a team: mean + 94% HDI (value travels with its
    interval — never a naked point estimate)."""
    i = posterior._idx[team]
    att = posterior._post("att")[i]
    deff = posterior._post("def")[i]
    return {
        "attack": {"value": float(att.mean()), "ci": _hdi(att, prob)},
        "defense": {"value": float(deff.mean()), "ci": _hdi(deff, prob)},
    }


def xg_or_gap(*, xg, covered: bool) -> dict:
    """xG only where StatsBomb-covered; otherwise an explicit coverage gap, NEVER imputed."""
    if not covered:
        return coverage_gap("xg not StatsBomb-covered for this fixture")
    v = no_impute(xg)
    return {"value": v} if v is not None else coverage_gap("xg missing")
