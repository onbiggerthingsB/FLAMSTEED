"""P3 v0 — club-Elo squad-strength anchor: the pure join/aggregation functions.

These are the leakage-free, network-free, store-free pieces the offline build
script (``scripts/build_squad_z.py``) composes to turn hand-curated squad lists +
point-in-time clubelo.com snapshots into a per-team ``squad_z`` (spec
``docs/superpowers/specs/2026-06-10-p3v0-squad-anchor-design.md`` §3-§5).

Invariants (binding):
- The join is **EXACT** club-name match + an explicit alias map. NEVER fuzzy
  (no casefold, no Levenshtein, no token overlap). An unmatched club is logged as
  a coverage gap and **never imputed**.
- An uncovered team (``has_squad=0``) gets ``squad_z = 0.0`` and is excluded from
  the z-score moments, so it keeps the pure-Elo anchor downstream (spec §5: a
  missing squad_z is NOT missing-at-random — coverage correlates with strength).
- The z-score mirrors ``model.strength.team_elo_z``: a degenerate (sigma=0) or
  empty covered set returns all-zeros (no div-by-zero), and NaN never leaks.

This module adds NO data source and runs NO I/O; it operates on plain
dicts/lists handed in by the orchestrator.
"""
from __future__ import annotations

import math

import numpy as np

# PRE-REGISTERED mask threshold (user, 2026-06-11, locked BEFORE any sweep number
# existed): squad_z only where >=70% of the top-18 slots are club-Elo-matched ->
# ceil(0.70 * TOP_N) = 13. This threshold is NEVER tuned against sweep RPS.
# (Supersedes the v0 placeholder MIN_MATCHED=11.)
MIN_MATCHED: int = 13

# Top-N clubs averaged per squad (spec §4.2: "top-18 by match if more").
TOP_N: int = 18


def match_squad_to_elo(
    clubs: list[str],
    elo_by_club: dict[str, float],
    aliases: dict[str, str],
) -> tuple[list[float], list[str]]:
    """EXACT (alias-bridged) club -> club-Elo. Returns (matched_elos, gap_clubs).

    For each squad ``club`` (as published): strip surrounding whitespace, then map
    through ``aliases`` if present (the alias map translates the squad spelling to
    the clubelo ``Club`` spelling). If the resulting key EXACTLY equals a clubelo
    ``Club``, take that Elo; else the club is a coverage gap. NEVER fuzzy; an empty
    string is always a gap (the coverage-gap sentinel row).
    """
    matched: list[float] = []
    gaps: list[str] = []
    for raw in clubs:
        club = (raw or "").strip()
        if club == "":
            gaps.append(raw)
            continue
        key = aliases.get(club, club)
        if key in elo_by_club:
            matched.append(float(elo_by_club[key]))
        else:
            gaps.append(raw)
    return matched, gaps


def top18_mean(elos: list[float]) -> float:
    """Mean of the top-``TOP_N`` Elos (descending). <=TOP_N -> mean of all; [] -> NaN."""
    if not elos:
        return float("nan")
    top = sorted(elos, reverse=True)[:TOP_N]
    return float(sum(top) / len(top))


def compute_has_squad(n_matched: int) -> int:
    """1 iff the team has >= MIN_MATCHED matched players, else 0 (spec §4.3)."""
    return 1 if n_matched >= MIN_MATCHED else 0


def zscore_covered(
    club_elo_mean: dict[str, float],
    has_squad: dict[str, int],
) -> dict[str, float]:
    """Z-score ``club_elo_mean`` across the COVERED teams only (spec §4.4).

    mu, sigma are the mean + POPULATION std over teams with ``has_squad==1`` and a
    finite mean. An uncovered team (or one with a NaN mean) -> 0.0 and is excluded
    from the moments. A degenerate (sigma==0) or empty covered set -> all-zeros
    (mirrors ``strength.team_elo_z``; no div-by-zero, no NaN leak).
    """
    covered_means = [
        club_elo_mean[t]
        for t in club_elo_mean
        if has_squad.get(t, 0) == 1 and math.isfinite(club_elo_mean.get(t, float("nan")))
    ]
    out: dict[str, float] = {t: 0.0 for t in club_elo_mean}
    if not covered_means:
        return out
    arr = np.array(covered_means, dtype=float)
    sd = float(np.std(arr))  # population std (ddof=0), like team_elo_z's nanstd
    if not math.isfinite(sd) or sd == 0.0:
        return out
    mu = float(np.mean(arr))
    for t in club_elo_mean:
        m = club_elo_mean.get(t, float("nan"))
        if has_squad.get(t, 0) == 1 and math.isfinite(m):
            out[t] = (m - mu) / sd
        else:
            out[t] = 0.0
    return out
