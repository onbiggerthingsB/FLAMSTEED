"""P3 v0 — pure squad_z functions (join + aggregation + mask + z-score).

Fixtures only: NO data/, NO network, NO store. These pin the four pure pieces the
build script composes (spec §4/§8):

- ``match_squad_to_elo``: EXACT club match + explicit alias map; unknown club ->
  unmatched (logged, never imputed); a near-miss spelling with NO alias entry does
  NOT fuzzy-match.
- ``top18_mean``: >18 matched -> mean of the top 18 by Elo; <=18 -> mean of all;
  empty -> NaN.
- ``compute_has_squad``: >= MIN_MATCHED matched -> 1; fewer -> 0.
- ``zscore_covered``: zero-mean/unit-std across the covered set; an uncovered team
  -> 0.0; a degenerate (sigma=0) covered set -> all-zeros (no div-by-zero),
  mirroring ``strength.team_elo_z``.
"""
from __future__ import annotations

import math

import numpy as np

from wcmodel.data.sources.squad_z import (
    MIN_MATCHED,
    compute_has_squad,
    match_squad_to_elo,
    top18_mean,
    zscore_covered,
)


# --------------------------------------------------------------------------- #
# match_squad_to_elo — EXACT + alias, NEVER fuzzy.                              #
# --------------------------------------------------------------------------- #
def _elo_table():
    # clubelo `Club` -> Elo (the snapshot, as a dict for the pure fn).
    return {"Arsenal": 2000.0, "Inter": 1900.0, "Man City": 1970.0, "Paris SG": 1960.0}


def _aliases():
    return {"Internazionale": "Inter", "Manchester City": "Man City",
            "Paris Saint-Germain": "Paris SG"}


def test_exact_match_hits():
    clubs = ["Arsenal"]
    matched, gaps = match_squad_to_elo(clubs, _elo_table(), _aliases())
    assert matched == [2000.0]
    assert gaps == []


def test_alias_mapped_club_hits():
    # The squad spelling differs from the clubelo `Club`; the alias map bridges it.
    clubs = ["Internazionale", "Manchester City", "Paris Saint-Germain"]
    matched, gaps = match_squad_to_elo(clubs, _elo_table(), _aliases())
    assert sorted(matched) == [1900.0, 1960.0, 1970.0]
    assert gaps == []


def test_whitespace_is_stripped_before_exact_match():
    clubs = ["  Arsenal  "]
    matched, gaps = match_squad_to_elo(clubs, _elo_table(), _aliases())
    assert matched == [2000.0]
    assert gaps == []


def test_unknown_club_is_unmatched_never_imputed():
    clubs = ["Al-Hilal"]  # not in the table, not in aliases
    matched, gaps = match_squad_to_elo(clubs, _elo_table(), _aliases())
    assert matched == []          # nothing imputed
    assert gaps == ["Al-Hilal"]   # logged as a coverage gap


def test_join_is_never_fuzzy():
    # A near-miss spelling with NO alias entry must NOT match (no casefold / no
    # token overlap / no Levenshtein).
    clubs = ["arsenal", "Arsenal FC", "Inter Milan"]  # none exactly equal a `Club`
    matched, gaps = match_squad_to_elo(clubs, _elo_table(), _aliases())
    assert matched == []
    assert sorted(gaps) == ["Arsenal FC", "Inter Milan", "arsenal"]


def test_empty_club_string_is_a_gap_not_a_match():
    # The coverage-gap sentinel row carries an empty club.
    clubs = [""]
    matched, gaps = match_squad_to_elo(clubs, _elo_table(), _aliases())
    assert matched == []
    assert gaps == [""]


# --------------------------------------------------------------------------- #
# top18_mean.                                                                   #
# --------------------------------------------------------------------------- #
def test_top18_mean_of_top_18_when_more_than_18():
    # 20 values 1..20; the top 18 are 3..20, mean = (3+20)/2 = 11.5.
    vals = [float(i) for i in range(1, 21)]
    assert top18_mean(vals) == 11.5


def test_top18_mean_of_all_when_18_or_fewer():
    vals = [10.0, 20.0, 30.0]
    assert top18_mean(vals) == 20.0


def test_top18_mean_exactly_18():
    vals = [float(i) for i in range(1, 19)]  # 1..18, mean 9.5
    assert top18_mean(vals) == 9.5


def test_top18_mean_empty_is_nan():
    assert math.isnan(top18_mean([]))


# --------------------------------------------------------------------------- #
# compute_has_squad.                                                           #
# --------------------------------------------------------------------------- #
def test_has_squad_at_threshold():
    assert compute_has_squad(MIN_MATCHED) == 1


def test_has_squad_above_threshold():
    assert compute_has_squad(MIN_MATCHED + 5) == 1


def test_has_squad_below_threshold():
    assert compute_has_squad(MIN_MATCHED - 1) == 0


def test_has_squad_zero_matched():
    assert compute_has_squad(0) == 0


def test_min_matched_is_eleven():
    # v0 contract: a full XI's worth of club-Elo signal.
    assert MIN_MATCHED == 13   # PRE-REGISTERED (2026-06-11): ceil(0.70*18); never tuned vs sweep RPS


# --------------------------------------------------------------------------- #
# zscore_covered.                                                              #
# --------------------------------------------------------------------------- #
def test_zscore_zero_mean_unit_std_across_covered():
    means = {"A": 10.0, "B": 20.0, "C": 30.0}
    has = {"A": 1, "B": 1, "C": 1}
    z = zscore_covered(means, has)
    # population std of [10,20,30] = sqrt(200/3) ~ 8.165
    assert abs(z["A"] - (-1.2247448714)) < 1e-6
    assert abs(z["B"]) < 1e-12
    assert abs(z["C"] - (1.2247448714)) < 1e-6


def test_zscore_uncovered_team_is_zero_and_excluded_from_moments():
    # The uncovered team must NOT shift mu/sigma and must get squad_z = 0.0.
    means = {"A": 10.0, "B": 20.0, "C": 30.0, "WEAK": 1000.0}
    has = {"A": 1, "B": 1, "C": 1, "WEAK": 0}
    z = zscore_covered(means, has)
    assert z["WEAK"] == 0.0
    # The covered three are z-scored among themselves (WEAK's 1000 excluded).
    assert abs(z["B"]) < 1e-12
    assert abs(z["A"] - (-1.2247448714)) < 1e-6


def test_zscore_degenerate_sigma_zero_is_all_zeros():
    means = {"A": 50.0, "B": 50.0, "C": 50.0}
    has = {"A": 1, "B": 1, "C": 1}
    z = zscore_covered(means, has)
    assert all(v == 0.0 for v in z.values())


def test_zscore_empty_covered_set_is_all_zeros():
    means = {"A": 10.0, "B": 20.0}
    has = {"A": 0, "B": 0}
    z = zscore_covered(means, has)
    assert z == {"A": 0.0, "B": 0.0}


def test_zscore_nan_mean_treated_as_uncovered():
    # A covered-flag team whose mean is NaN (no matched players) -> 0.0, no NaN leak.
    means = {"A": 10.0, "B": 20.0, "C": 30.0, "X": float("nan")}
    has = {"A": 1, "B": 1, "C": 1, "X": 1}
    z = zscore_covered(means, has)
    assert z["X"] == 0.0
    assert not any(math.isnan(v) for v in z.values())


# --------------------------------------------------------------------------- #
# Snapshot CONTENT tests — check (a) resolution (2026-06-11).                  #
#                                                                              #
# The clubelo `/D` endpoint returns ratings ENTERING day D — matches strictly  #
# before D — i.e. exactly this repo's `read(cutoff=D)` convention. Verified    #
# empirically by the D-1 re-pull (prereg addendum): every D-1 vs D diff was a  #
# real club match played ON D-1 (exact zero-sum Elo-exchange pairs; changed    #
# validity windows close at D-1 and open at D). These tests pin the structural #
# no-look-ahead property of the COMMITTED snapshot files themselves, so a      #
# future re-pull or edit cannot silently smuggle post-tournament-start info    #
# into the sweep's validation anchors.                                         #
# --------------------------------------------------------------------------- #
import csv as _csv
import io as _io
from pathlib import Path as _Path

_SQUADS_DIR = _Path(__file__).resolve().parents[2] / "config" / "squads"

#: (snapshot file, API endpoint date D, the tournament's FIRST match day).
#: WC-2022 / Euro-2024: D == opening day (ratings entering it: matches < D).
#: WC-2026: D = 2026-06-10, strictly before the 2026-06-11 opener.
_SNAPSHOT_BOUNDS = [
    ("clubelo_20221120.csv", "2022-11-20", "2022-11-20"),
    ("clubelo_20240614.csv", "2024-06-14", "2024-06-14"),
    ("clubelo_20260610.csv", "2026-06-10", "2026-06-11"),
]


def _snapshot_rows(name: str) -> list[dict]:
    text = (_SQUADS_DIR / name).read_text()
    data = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    return list(_csv.DictReader(_io.StringIO(data)))


def test_snapshots_contain_no_post_endpoint_rating_window():
    """No rating window in any committed snapshot opens AFTER its endpoint date D:
    a `From > D` row would mean a match on/after D (i.e. tournament-time info)
    contributed to the rating — look-ahead for the held-out evaluation."""
    for name, endpoint, _start in _SNAPSHOT_BOUNDS:
        rows = _snapshot_rows(name)
        assert len(rows) > 500, f"{name}: implausibly few rows ({len(rows)})"
        bad = [r["Club"] for r in rows if r["From"] > endpoint]
        assert not bad, (
            f"{name}: {len(bad)} rating window(s) open after {endpoint} "
            f"(post-endpoint info): {bad[:5]}")


def test_snapshot_endpoints_never_exceed_tournament_start():
    """The endpoint date D never exceeds the tournament's first match day, so
    (with matches-strictly-before-D semantics) no tournament match can be in
    the ratings. ISO strings compare lexicographically."""
    for name, endpoint, start in _SNAPSHOT_BOUNDS:
        assert endpoint <= start, f"{name}: endpoint {endpoint} > first match day {start}"


def test_snapshot_provenance_headers_name_their_endpoint():
    """Each snapshot's provenance header names the exact /D endpoint it claims —
    the date in the filename, the header, and the bound table must agree."""
    for name, endpoint, _start in _SNAPSHOT_BOUNDS:
        head = "\n".join(l for l in (_SQUADS_DIR / name).read_text().splitlines()
                         if l.startswith("#"))
        assert f"api.clubelo.com/{endpoint}" in head, (
            f"{name}: provenance header does not name the {endpoint} endpoint")
        assert endpoint.replace("-", "") in name, (
            f"{name}: filename does not carry the endpoint date {endpoint}")
