"""Upstream martj42 now ships placeholder SCHEDULE rows for not-yet-determined
knockout fixtures (e.g. the final: date+city set, teams NaN, scores NaN).
normalize_results must DROP them loudly instead of crashing the match-id
hasher (observed live 2026-07-14: commit a77ed04's 3rd-place + final rows)."""
import numpy as np
import pandas as pd
import pytest

from wcmodel.data.sources.results import normalize_results


def _raw(rows):
    return pd.DataFrame(rows, columns=[
        "date", "home_team", "away_team", "home_score", "away_score",
        "tournament", "city", "country", "neutral"])


def test_nan_team_placeholder_rows_are_dropped_not_fatal():
    raw = _raw([
        ("2026-07-11", "Norway", "England", 1, 2, "FIFA World Cup",
         "Boston", "United States", True),
        ("2026-07-18", np.nan, np.nan, np.nan, np.nan, "FIFA World Cup",
         "Miami Gardens", "United States", True),
        ("2026-07-19", np.nan, np.nan, np.nan, np.nan, "FIFA World Cup",
         "East Rutherford", "United States", True),
    ])
    out = normalize_results(raw)          # must not raise
    assert len(out) == 1                  # placeholders dropped
    assert out.iloc[0]["home_team"] == "Norway"
    assert out["match_id"].is_unique


def test_one_sided_nan_team_also_dropped():
    raw = _raw([
        ("2026-07-11", "Norway", np.nan, np.nan, np.nan, "FIFA World Cup",
         "Boston", "United States", True),
        ("2026-07-11", "Argentina", "Switzerland", 3, 1, "FIFA World Cup",
         "Dallas", "United States", True),
    ])
    out = normalize_results(raw)
    assert list(out["home_team"]) == ["Argentina"]


def test_all_real_rows_unchanged_by_guard():
    raw = _raw([
        ("2026-07-11", "Norway", "England", 1, 2, "FIFA World Cup",
         "Boston", "United States", True),
        ("2026-07-11", "Argentina", "Switzerland", 3, 1, "FIFA World Cup",
         "Dallas", "United States", True),
    ])
    out = normalize_results(raw)
    assert len(out) == 2 and out["match_id"].is_unique
