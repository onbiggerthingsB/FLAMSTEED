"""Review-v2 Fix 2 (finding C2): duplicate-match dedup in valid_played_results.

The live store held 95 scored rows for 79 real 2026 matches: a manual
(wc2026_live) row and a martj42 row for the SAME match fork into different
match_ids when they disagree on home/away orientation (Turkey-United States)
or merely on the city string ('Foxborough' vs 'Boston (Foxborough)'). Nothing
downstream deduped, so 16 matches were double-counted in the Elo history and
the fit panel. valid_played_results — THE single shared "valid played match"
definition — now drops content-identical duplicates: same normalized date +
same unordered team pair + IDENTICAL team->goals map, keeping the wc2026_live
row when present. Same-pair/same-date rows with DIFFERENT scores (the real
1974 Tahiti v New Caledonia double-header) are two genuine matches and are
NEVER collapsed.
"""
import pandas as pd

from wcmodel.data.features import valid_played_results


def _row(home, away, hs, as_, date="2026-06-26", source=None, city=None):
    r = {"home_team": home, "away_team": away, "home_score": hs,
         "away_score": as_, "date": pd.Timestamp(date)}
    if source is not None:
        r["source"] = source
    if city is not None:
        r["city"] = city
    return r


def test_same_orientation_duplicate_collapses_to_manual_row():
    df = pd.DataFrame([
        _row("Norway", "France", 1, 4, source="martj42", city="Foxborough"),
        _row("Norway", "France", 1, 4, source="wc2026_live",
             city="Boston (Foxborough)"),
    ])
    out = valid_played_results(df)
    assert len(out) == 1
    assert out.iloc[0]["source"] == "wc2026_live"


def test_reversed_orientation_duplicate_collapses_to_manual_row():
    df = pd.DataFrame([
        _row("United States", "Turkey", 2, 3, date="2026-06-25",
             source="martj42"),
        _row("Turkey", "United States", 3, 2, date="2026-06-25",
             source="wc2026_live"),
    ])
    out = valid_played_results(df)
    assert len(out) == 1
    assert out.iloc[0]["home_team"] == "Turkey"      # manual row kept as-is
    assert (out.iloc[0]["home_score"], out.iloc[0]["away_score"]) == (3, 2)


def test_double_header_with_different_scores_is_kept_whole():
    """Two REAL matches, same pair + same day, different scores (the 1974
    Tahiti double-header case) — content differs, nothing is dropped."""
    df = pd.DataFrame([
        _row("Tahiti", "New Caledonia", 2, 1, date="1974-02-17"),
        _row("Tahiti", "New Caledonia", 0, 3, date="1974-02-17"),
    ])
    out = valid_played_results(df)
    assert len(out) == 2


def test_no_source_column_still_dedups_deterministically():
    df = pd.DataFrame([
        _row("Norway", "France", 1, 4),
        _row("France", "Norway", 4, 1),
    ])
    out = valid_played_results(df)
    assert len(out) == 1
    assert out.iloc[0]["home_team"] == "Norway"      # first occurrence kept


def test_distinct_matches_untouched_and_input_not_mutated():
    df = pd.DataFrame([
        _row("Norway", "France", 1, 4, date="2026-06-26"),
        _row("Norway", "France", 1, 4, date="2026-06-30"),   # different DAY
        _row("Senegal", "Iraq", 5, 0, date="2026-06-26"),
    ])
    snap = df.copy(deep=True)
    out = valid_played_results(df)
    assert len(out) == 3
    pd.testing.assert_frame_equal(df, snap)          # input never mutated


def test_invalid_scores_still_dropped_before_dedup():
    """The existing validity contract is unchanged: garbage scores drop."""
    df = pd.DataFrame([
        _row("Norway", "France", 1, 4),
        _row("Ghana", "Togo", float("inf"), 1),
        _row("Ghana", "Togo", -1, 1),
    ])
    out = valid_played_results(df)
    assert len(out) == 1 and out.iloc[0]["home_team"] == "Norway"
