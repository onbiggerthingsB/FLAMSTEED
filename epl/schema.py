"""Column contract for the tidy match table, and the point-in-time ordering rule.

Downstream code should import the column names from here rather than spelling
them as string literals, so a schema change breaks loudly at import instead of
quietly producing an all-NaN feature.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# --- identity -------------------------------------------------------------
ID_COLUMNS = ["match_id", "season", "season_code"]

# --- when -----------------------------------------------------------------
# `date` is always populated. `time` is UK local kickoff as printed by the
# source, and is absent for seasons before 2019/20. `kickoff` combines them and
# is NaT wherever `time` is missing.
TIME_COLUMNS = ["date", "time", "kickoff"]

# --- who ------------------------------------------------------------------
# `*_raw` preserves the source spelling verbatim so the mapping stays auditable;
# `*_team` is the canonical display name; `*_key` is the stable join key.
TEAM_COLUMNS = [
    "home_team_raw", "away_team_raw",
    "home_team", "away_team",
    "home_key", "away_key",
]

# --- what happened --------------------------------------------------------
# NOT knowable before kickoff. Any feature derived from these for match M must
# come from matches strictly earlier than M under ORDERING_RULE.
RESULT_COLUMNS = ["fthg", "ftag", "ftr", "played"]

# --- benchmark only -------------------------------------------------------
# BENCHMARK ONLY. These exist to answer "did we beat the market?" and for no
# other purpose. They are never displayed publicly and never turned into a
# betting signal. `odds_*` is the preferred triple: Pinnacle closing
# (PSCH/PSCD/PSCA) where available, else Pinnacle opening (PSH/PSD/PSA), with
# `odds_source` recording which. `odds_overround` is sum(1/odds) — roughly
# 1.02-1.06 for Pinnacle. Every selected price must be finite and greater than
# 1.0. A zero-vig book at exactly 1.0 is valid; only a gross underround below
# that boundary (allowing the fixed floating-point tolerance below) is
# unusable, in which case the parser may try only the already-declared
# closing-to-opening fallback.
MIN_USABLE_OVERROUND = 1.0
ODDS_OVERROUND_ATOL = 1e-9
ODDS_COLUMNS = [
    "psch", "pscd", "psca",
    "psh", "psd", "psa",
    "odds_h", "odds_d", "odds_a",
    "odds_source", "odds_overround",
]

COLUMNS = ID_COLUMNS + TIME_COLUMNS + TEAM_COLUMNS + RESULT_COLUMNS + ODDS_COLUMNS

#: Number of matches in a completed double round-robin among 20 clubs.
#: THE E0 CONSTANTS. Kept spelled this way, and kept at these values, because
#: every existing caller reads them and the Premier League ingest's behaviour is
#: not allowed to move. A second division reads `division_shape` instead.
TEAMS_PER_SEASON = 20
MATCHES_PER_SEASON = TEAMS_PER_SEASON * (TEAMS_PER_SEASON - 1)  # 380

#: football-data.co.uk's division code for the Premier League. Every ingest
#: entry point defaults to it, so a caller that names no division gets exactly
#: the behaviour it got before divisions existed.
DEFAULT_DIVISION = "E0"


@dataclass(frozen=True)
class DivisionShape:
    """How big one completed season of a division is.

    The three numbers are not independent — `matches` and `opponents` follow
    from `teams` in a double round-robin — but they are stored rather than
    derived so a division with a different format could be registered without
    the validator quietly computing the wrong expectation for it. `__post_init__`
    checks the arithmetic for the round-robin case we do have.
    """

    division: str
    label: str
    teams: int
    matches: int
    opponents: int

    def __post_init__(self) -> None:
        if self.matches != self.teams * (self.teams - 1):
            raise ValueError(
                f"{self.division}: {self.matches} matches is not a double "
                f"round-robin among {self.teams} clubs"
            )
        if self.opponents != self.teams - 1:
            raise ValueError(
                f"{self.division}: {self.opponents} opponents is not "
                f"{self.teams} - 1"
            )


#: The divisions this ingest knows how to validate. A division that is not here
#: has no asserted shape, and `division_shape` refuses rather than guessing one:
#: a guessed 380 against a 552-match file would report a complete season as
#: broken, and a guessed 552 against E0 would do the reverse.
DIVISIONS: dict[str, DivisionShape] = {
    "E0": DivisionShape("E0", "Premier League", 20, 380, 19),
    "E1": DivisionShape("E1", "EFL Championship", 24, 552, 23),
}

assert DIVISIONS["E0"].teams == TEAMS_PER_SEASON
assert DIVISIONS["E0"].matches == MATCHES_PER_SEASON


def division_shape(division: str = DEFAULT_DIVISION) -> DivisionShape:
    """`'E1'` -> the 24/552/23 shape. Raises for a division with no shape."""
    try:
        return DIVISIONS[division]
    except KeyError as exc:
        raise KeyError(
            f"no season shape registered for division {division!r}; known "
            f"divisions are {sorted(DIVISIONS)}. Register its shape in "
            f"epl.schema.DIVISIONS rather than letting a validator assume one."
        ) from exc

ORDERING_RULE = """\
A forecast for match M may use only matches strictly earlier than M:

    kickoff known for both  ->  earlier iff kickoff < M.kickoff
    kickoff missing (pre-2019/20 seasons, no Time column)
                            ->  earlier iff date < M.date

The second clause is deliberately strict. Same-day matches with no kickoff time
are NOT ordered among themselves, so none of them may inform any other: treating
them as ordered by row position would let a 15:00 result inform a 12:30 kickoff
whenever the file happens to list them that way. Same-day exclusion costs a
little information and buys the guarantee that the cutoff cannot be wrong.
"""


def sort_for_walk_forward(df: pd.DataFrame) -> pd.DataFrame:
    """Return `df` in deterministic chronological order.

    Sorts by date, then kickoff time where known (rows without a time sort
    first within their day), then home_key to break remaining ties. The result
    is stable across runs and machines, which matters because a walk-forward
    backtest that reorders between runs is not reproducible.

    Ordering is NOT the same as the cutoff rule: see `ORDERING_RULE`. Sorting
    puts same-day untimed matches in some order, but they must still not inform
    one another.
    """
    out = df.copy()
    out["_time_sort"] = out["kickoff"].astype("datetime64[ns]")
    out = out.sort_values(
        ["date", "_time_sort", "home_key", "away_key"],
        na_position="first",
        kind="mergesort",  # stable
    )
    return out.drop(columns="_time_sort").reset_index(drop=True)
