"""Structural checks on a parsed season. Report failures; never drop them.

A season that fails a check stays in the output with its failure recorded in the
manifest. Dropping it would be the worst outcome: the model would train on a
silently smaller sample and every downstream RPS would be computed against a
denominator nobody chose.

The fixture-level checks are stronger than a bare row count on purpose. 380 rows
is satisfied by a file that duplicates one fixture and omits another; requiring
every ordered (home, away) pair exactly once, and 19 home + 19 away per club, is
not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from epl import schema


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def to_json(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class SeasonReport:
    season: str
    season_code: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def to_json(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [c.to_json() for c in self.checks],
        }


def season_window(season_code: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Plausible date range for a season code.

    Generous by design: 1 July of the start year to 31 August of the following
    year. It has to admit 2019/20, which COVID stretched from 2019-08-09 to
    2020-07-26. The check is a guard against gross corruption (a 1970 epoch date,
    a fixture filed under the wrong season), not a tight schedule assertion.
    """
    start_year = 2000 + int(season_code[:2])
    return (
        pd.Timestamp(year=start_year, month=7, day=1),
        pd.Timestamp(year=start_year + 1, month=8, day=31),
    )


def validate_season(frame: pd.DataFrame, season_code: str, season: str) -> SeasonReport:
    """Run every structural check against one season's rows."""
    report = SeasonReport(season=season, season_code=season_code)
    add = report.checks.append
    n = len(frame)

    # --- completeness -----------------------------------------------------
    unplayed = int((~frame["played"]).sum())
    add(Check(
        "all_fixtures_played",
        unplayed == 0,
        "every fixture has a result" if unplayed == 0
        else f"{unplayed} fixture(s) have no result — season is in progress or truncated",
    ))

    add(Check(
        "match_count_380",
        n == schema.MATCHES_PER_SEASON,
        f"{n} matches" if n == schema.MATCHES_PER_SEASON
        else f"expected {schema.MATCHES_PER_SEASON}, found {n}",
    ))

    # --- teams ------------------------------------------------------------
    if frame[["home_key", "away_key"]].isna().any().any():
        add(Check("teams_resolved", False,
                  f"{int(frame['home_key'].isna().sum() + frame['away_key'].isna().sum())} "
                  f"unresolved club name(s) — see the name-mapping report"))
        return report
    add(Check("teams_resolved", True, "every club name resolved to a stable key"))

    club_keys = pd.unique(pd.concat([frame["home_key"], frame["away_key"]]))
    add(Check(
        "distinct_teams_20",
        len(club_keys) == schema.TEAMS_PER_SEASON,
        f"{len(club_keys)} clubs" if len(club_keys) == schema.TEAMS_PER_SEASON
        else f"expected {schema.TEAMS_PER_SEASON}, found {len(club_keys)}: {sorted(club_keys)}",
    ))

    home_counts = frame["home_key"].value_counts()
    away_counts = frame["away_key"].value_counts()
    expected_each = schema.TEAMS_PER_SEASON - 1  # 19
    off = {
        club: (int(home_counts.get(club, 0)), int(away_counts.get(club, 0)))
        for club in club_keys
        if home_counts.get(club, 0) != expected_each
        or away_counts.get(club, 0) != expected_each
    }
    add(Check(
        "double_round_robin",
        not off,
        f"every club plays {expected_each} home and {expected_each} away" if not off
        else f"club(s) with wrong home/away counts (club: home, away): {off}",
    ))

    pairs = frame[["home_key", "away_key"]]
    dup_pairs = pairs[pairs.duplicated(keep=False)]
    add(Check(
        "unique_fixtures",
        dup_pairs.empty,
        "each ordered (home, away) pair occurs once" if dup_pairs.empty
        else f"{len(dup_pairs)} row(s) in repeated fixtures: "
             f"{dup_pairs.drop_duplicates().to_dict('records')[:10]}",
    ))

    key = frame[["date", "home_key", "away_key"]]
    dup_key = key[key.duplicated(keep=False)]
    add(Check(
        "no_duplicate_date_home_away",
        dup_key.empty,
        "no duplicate (date, home, away)" if dup_key.empty
        else f"{len(dup_key)} duplicated row(s): {dup_key.astype(str).to_dict('records')[:10]}",
    ))

    self_play = frame[frame["home_key"] == frame["away_key"]]
    add(Check(
        "no_self_fixtures",
        self_play.empty,
        "no club plays itself" if self_play.empty
        else f"{len(self_play)} self-fixture(s)",
    ))

    # --- goals ------------------------------------------------------------
    played = frame[frame["played"]]
    bad_goals = played[(played["fthg"] < 0) | (played["ftag"] < 0)]
    missing_goals = int(frame["fthg"].isna().sum() + frame["ftag"].isna().sum())
    goals_ok = bad_goals.empty and missing_goals == 2 * unplayed
    add(Check(
        "goals_non_negative_integers",
        goals_ok,
        "all goals are non-negative integers" if goals_ok
        else f"{len(bad_goals)} negative, {missing_goals} missing "
             f"(expected {2 * unplayed} missing from unplayed fixtures)",
    ))

    # --- results agree with goals ----------------------------------------
    if played["ftr"].notna().any():
        implied = played.apply(
            lambda r: "H" if r["fthg"] > r["ftag"] else ("A" if r["fthg"] < r["ftag"] else "D"),
            axis=1,
        )
        mismatch = played[played["ftr"] != implied]
        add(Check(
            "ftr_matches_goals",
            mismatch.empty,
            "FTR agrees with the scoreline in every row" if mismatch.empty
            else f"{len(mismatch)} row(s) where FTR contradicts FTHG/FTAG: "
                 f"{mismatch[['date', 'home_key', 'away_key', 'fthg', 'ftag', 'ftr']].astype(str).to_dict('records')[:10]}",
        ))

    # --- dates ------------------------------------------------------------
    lo, hi = season_window(season_code)
    outside = frame[(frame["date"] < lo) | (frame["date"] > hi)]
    add(Check(
        "dates_within_season",
        outside.empty,
        f"all dates within {lo:%Y-%m-%d}..{hi:%Y-%m-%d}" if outside.empty
        else f"{len(outside)} date(s) outside the season window: "
             f"{sorted(outside['date'].dt.strftime('%Y-%m-%d').unique())[:10]}",
    ))

    return report
