"""Tier taxonomy — per-match stratification tags for Phase-4 reporting (spec §6).

Four PURE functions, each a small lookup/classification with no I/O beyond a
module-level read of the bundled confederation reference table:

  - ``confederation(team)``    static team -> confederation map (CSV), else "Unknown".
  - ``strength_band(rank)``    integer Elo *rank* -> coarse strength band.
  - ``match_type(tournament)`` martj42 raw ``tournament`` string -> normalised label.
  - ``is_covid(date)``         True iff ``date`` falls inside the configured window.

Deliberate boundaries (coherence / no-leakage):
  - This module does NOT import ``elo`` or ``store``. ``strength_band`` takes an
    ALREADY-computed integer rank; the point-in-time Elo rank that feeds it is
    produced later (Task 11). Here it is purely a rank -> band mapping.
  - ``confederation`` NEVER guesses: an unmapped team returns "Unknown" so the
    gap is visible (to be reconciled against the live results feed in Task 11)
    rather than silently mis-attributed.
  - ``match_type`` normalises martj42's free-text ``tournament`` strings; an
    unrecognised competition falls back to "other" (never a wrong guess).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from wcmodel.config import load_config

_REF_PATH = Path(__file__).resolve().parent / "ref" / "confederations.csv"

#: Returned by ``confederation`` for any team absent from the reference table.
UNKNOWN_CONFEDERATION = "Unknown"

#: The CLOSED universe of labels ``match_type`` can emit (its docstring's list).
#: A single source of truth so any consumer that keys on a tier (e.g. the P2c
#: ``model.likelihood_tier_weights`` block) can validate its keys against the
#: SAME set the panel is tagged with — an unknown tier name then fails loud
#: instead of silently never matching a row. Keep in lockstep with ``match_type``.
MATCH_TYPES = frozenset({
    "wc_finals",
    "wc_qualifier",
    "continental_championship",
    "continental_qualifier",
    "nations_league",
    "friendly",
    "other",
})


@lru_cache(maxsize=1)
def _confederation_map() -> dict[str, str]:
    """team -> confederation, loaded once and cached for the process lifetime."""
    df = pd.read_csv(_REF_PATH)
    return dict(zip(df["team"], df["confederation"]))


def confederation(team: str) -> str:
    """Return the FIFA confederation for ``team`` (martj42 common-English name).

    Returns ``"Unknown"`` for any team not present in the reference table — we
    do NOT guess. Misses are a flagged gap to reconcile in Task 11, never a
    silent mis-attribution.
    """
    return _confederation_map().get(team, UNKNOWN_CONFEDERATION)


def strength_band(rank: int) -> str:
    """Map a precomputed integer Elo *rank* (1 = best) to a coarse band.

    Boundaries (inclusive): 1-10 Elite, 11-25 Strong, 26-50 Mid, 51-100 Weak,
    101+ Minnow. The rank itself is computed point-in-time elsewhere (Task 11);
    this is a pure rank -> band lookup.
    """
    if rank <= 10:
        return "Elite"
    if rank <= 25:
        return "Strong"
    if rank <= 50:
        return "Mid"
    if rank <= 100:
        return "Weak"
    return "Minnow"


def match_type(tournament: str) -> str:
    """Normalise a martj42 raw ``tournament`` string to a stratification label.

    Labels: ``wc_finals``, ``wc_qualifier``, ``continental_championship``,
    ``continental_qualifier``, ``nations_league``, ``friendly``, ``other``.
    Substring/pattern rules with an explicit "other" fallback (never a guess).
    Qualifiers are matched before their parent championship so that, e.g.,
    "UEFA Euro qualification" -> ``continental_qualifier`` (not championship).
    """
    t = (tournament or "").strip()
    tl = t.lower()
    is_qual = "qualif" in tl  # "qualification" / "qualifier"

    if "fifa world cup" in tl:
        return "wc_qualifier" if is_qual else "wc_finals"
    if "nations league" in tl:
        return "nations_league"
    if tl == "friendly":
        return "friendly"

    # Continental championships and their qualifiers (substring match on the
    # championship name; qualifier flag decides which label).
    continental = (
        "uefa euro",
        "copa américa",
        "copa america",
        "african cup of nations",
        "afc asian cup",
        "gold cup",
    )
    if any(name in tl for name in continental):
        return "continental_qualifier" if is_qual else "continental_championship"

    return "other"


def is_covid(date: str | pd.Timestamp) -> bool:
    """True iff ``date`` is within the configured COVID window (inclusive).

    Window bounds are read from ``load_config()["covid"]`` (``start`` / ``end``).
    """
    cfg = load_config()["covid"]
    start = pd.Timestamp(cfg["start"])
    end = pd.Timestamp(cfg["end"])
    d = pd.Timestamp(date)
    return start <= d <= end
