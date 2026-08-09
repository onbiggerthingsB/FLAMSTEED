"""Market projections of a scoreline grid.

The model already produces ONE object per fixture: a joint distribution over
scorelines. Every betting-style market is a different *view* of that same
object — over/under is a sum along anti-diagonals, both-teams-to-score is the
complement of the first row and column, double chance is two 1X2 legs added
together. Nothing here fits anything, learns anything, or adds information.

That matters for how the outputs may be described. Broader market coverage is
NOT higher accuracy: an "over 1.5 goals" forecast is right more often than a
1X2 forecast because the event is more likely, not because the model got
better. Each market must therefore be reported with its own record, never
pooled into a single headline hit rate — pooling is precisely how a 55%
forecaster advertises 83%.

The 1X2 projection DELEGATES to ``draw_api.grid_one_x_two``. There is one
home/away convention in this codebase and this module does not get a second
one; a transposed copy would produce entirely plausible, entirely wrong
numbers, which is the failure mode these projections are most exposed to.

Grid convention (inherited, pinned by tests): ``grid[h, a]`` is the
probability of the home side scoring ``h`` and the away side ``a``.
"""
from __future__ import annotations

import numpy as np

from wcmodel.model.draw_api import grid_one_x_two

#: Goal lines quoted by default. Half-integers only, so each resolves cleanly
#: with no push; integer lines are supported on request and report the push.
DEFAULT_LINES = (0.5, 1.5, 2.5, 3.5, 4.5)

#: A projection may not silently differ from a distribution by more than this.
TOLERANCE = 1e-6


class MarketError(ValueError):
    """The grid cannot support the requested projection."""


def _checked(grid) -> np.ndarray:
    """Return ``grid`` as an array, or refuse it.

    An unnormalised or negative grid still projects — it just returns numbers
    that look like probabilities and are not. Every public function in this
    module goes through here first.
    """
    arr = np.asarray(grid, dtype=float)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        raise MarketError(
            f"scoreline grid must be square (home x away); got {arr.shape}")
    if np.any(arr < -TOLERANCE):
        raise MarketError("scoreline grid has negative cells — it is not a "
                          "probability distribution")
    total = arr.sum()
    if abs(total - 1.0) > 1e-4:
        raise MarketError(
            f"scoreline grid must sum to 1, got {total:.6f} — projecting an "
            "unnormalised grid yields plausible-looking numbers that are "
            "wrong")
    return arr


def _totals(arr: np.ndarray) -> np.ndarray:
    """Total-goals value for every cell."""
    h, a = np.indices(arr.shape)
    return h + a


def one_x_two(grid) -> dict:
    """Home / draw / away. Delegates to the production projection."""
    return grid_one_x_two(_checked(grid))


def double_chance(grid) -> dict:
    """The three two-way combinations, summed from the 1X2 legs."""
    r = one_x_two(grid)
    return {
        "home_or_draw": float(r["home"] + r["draw"]),
        "home_or_away": float(r["home"] + r["away"]),
        "draw_or_away": float(r["draw"] + r["away"]),
    }


def over_under(grid, line: float) -> dict:
    """Total goals over / under ``line``, with the push stated explicitly.

    A half-integer line cannot push. An INTEGER line pushes when the total
    lands exactly on it, and folding that mass into either side would both
    misprice the market and break the sum — so it is returned as its own
    number rather than absorbed.
    """
    arr = _checked(grid)
    if line < 0:
        raise MarketError(f"goal line must be non-negative; got {line}")
    max_total = int(_totals(arr).max())
    if line > max_total:
        raise MarketError(
            f"line {line} is beyond the grid's truncation (max representable "
            f"total is {max_total} goals) — the grid cannot answer this and "
            "reporting 0% would be a fabricated certainty")
    tot = _totals(arr)
    push = float(arr[tot == line].sum()) if float(line).is_integer() else 0.0
    return {
        "over": float(arr[tot > line].sum()),
        "under": float(arr[tot < line].sum()),
        "push": push,
    }


def both_teams_to_score(grid) -> dict:
    """Yes when both sides score — the grid minus its first row and column."""
    arr = _checked(grid)
    yes = float(arr[1:, 1:].sum())
    return {"yes": yes, "no": float(1.0 - yes)}


def clean_sheet(grid) -> dict:
    """Per side. The HOME side keeps a clean sheet when the AWAY side fails to
    score — i.e. the first *column*. Getting this backwards is the single
    easiest transposition to ship, so the tests pin both sides separately."""
    arr = _checked(grid)
    return {
        "home": float(arr[:, 0].sum()),
        "away": float(arr[0, :].sum()),
    }


def correct_score(grid, top_n: int = 5) -> list:
    """The ``top_n`` most likely exact scorelines, most likely first.

    Ties break on (-probability, home, away) so a rerun on identical inputs
    cannot reorder a published shortlist.
    """
    arr = _checked(grid)
    if top_n < 1:
        raise MarketError(f"top_n must be at least 1; got {top_n}")
    cells = [(int(h), int(a), float(arr[h, a]))
             for h in range(arr.shape[0]) for a in range(arr.shape[1])]
    cells.sort(key=lambda c: (-c[2], c[0], c[1]))
    return [{"home": h, "away": a, "prob": p} for h, a, p in cells[:top_n]]


def project_all(grid, lines=DEFAULT_LINES, top_n: int = 5) -> dict:
    """Every market, JSON-safe, from one grid.

    Lines beyond the grid's truncation are omitted rather than reported as
    zero — a market the grid cannot answer is absent, not certain.
    """
    arr = _checked(grid)
    max_total = int(_totals(arr).max())
    return {
        "one_x_two": one_x_two(arr),
        "double_chance": double_chance(arr),
        "over_under": {f"{line}": over_under(arr, line)
                       for line in lines if line <= max_total},
        "both_teams_to_score": both_teams_to_score(arr),
        "clean_sheet": clean_sheet(arr),
        "correct_score": correct_score(arr, top_n=top_n),
    }
