"""Raw football-data.co.uk CSV -> tidy match rows.

Three things here are easy to get wrong and expensive to get wrong quietly:

DATES. The source uses DD/MM/YY in older files and DD/MM/YYYY in newer ones,
sometimes both. Both are parsed explicitly; a value matching neither becomes NaT
and raises. It is never handed to a general-purpose date guesser, which would
silently read 01/02/2015 as January 2nd on a US-locale default and shift a third
of the season's fixtures.

GOALS. Coerced to numeric, then required to be finite, non-negative and
integral. Anything else becomes <NA> and is reported — never rounded into place.

ODDS. BENCHMARK ONLY (see `epl.schema.ODDS_COLUMNS`). Pinnacle closing
(PSCH/PSCD/PSCA) is preferred over Pinnacle opening (PSH/PSD/PSA). A row counts
as having odds only when all three prices are present and each exceeds 1.0;
partial or degenerate triples are treated as absent rather than half-used.

CLUB KEYS, for a division whose archive this ingest introduces. An unresolved
spelling leaves a NULL key, and a null key is not a missing value downstream —
it is a club. `epl.fit.to_store_frame` projects `home_key` straight into the
model's team identity without checking it, so every unregistered club in a file
would share one identity, accumulate one attack and one defence parameter, and
produce a fit that looks entirely healthy. `epl/fit.py` is protected and is not
edited here; instead `parse_season` REFUSES with `PhantomClub` for any division
other than E0, so the row never exists to be projected. E0 keeps its old
behaviour — report the issue, retain the row — because the daily live cycle
depends on an unmapped E0 name being a reported issue rather than an exception.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from epl import fetch, schema, teams

#: Source column names.
_SRC_DATE = "Date"
_SRC_TIME = "Time"
_SRC_HOME = "HomeTeam"
_SRC_AWAY = "AwayTeam"
_SRC_FTHG = "FTHG"
_SRC_FTAG = "FTAG"
_SRC_FTR = "FTR"

_CLOSING_ODDS = ("PSCH", "PSCD", "PSCA")
_OPENING_ODDS = ("PSH", "PSD", "PSA")

_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y")


class PhantomClub(ValueError):
    """A club key came out null, and a null key would become a club.

    Raised only for divisions this ingest introduces. It names the season, the
    date and the raw spelling, because the fix is a one-line registry entry and
    the message should be enough to write it.
    """


@dataclass
class ParseResult:
    """Tidy rows for one season, plus everything that went wrong producing them."""

    season_code: str
    season: str
    frame: pd.DataFrame
    division: str = schema.DEFAULT_DIVISION
    issues: list[str] = field(default_factory=list)
    #: raw spelling -> occurrence count, for the name-mapping report
    raw_team_counts: dict[str, int] = field(default_factory=dict)
    unknown_teams: list[str] = field(default_factory=list)
    dropped_blank_rows: int = 0


def parse_dates(values: pd.Series) -> pd.Series:
    """Parse DD/MM/YY and DD/MM/YYYY. Never guesses; never silently yields NaT.

    Each format is tried explicitly and the results combined, so a value is only
    NaT if it matches neither. Two-digit years map 14-26 -> 2014-2026 under
    pandas' pivot, which covers the whole ingest window.
    """
    text = values.astype("string").str.strip()
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    for fmt in _DATE_FORMATS:
        remaining = parsed.isna() & text.notna()
        if not remaining.any():
            break
        attempt = pd.to_datetime(text[remaining], format=fmt, errors="coerce")
        parsed.loc[remaining] = attempt
    return parsed


def _parse_times(frame: pd.DataFrame) -> pd.Series:
    """HH:MM strings where the source has a Time column, else all-NA.

    Absent for seasons before 2019/20, which is why `kickoff` is nullable and
    why `schema.ORDERING_RULE` falls back to date-only comparison.
    """
    if _SRC_TIME not in frame.columns:
        return pd.Series(pd.NA, index=frame.index, dtype="string")
    text = frame[_SRC_TIME].astype("string").str.strip()
    valid = text.str.fullmatch(r"\d{1,2}:\d{2}").fillna(False)
    return text.where(valid, pd.NA)


def _build_kickoff(date: pd.Series, time: pd.Series) -> pd.Series:
    """date + time as a naive UK-local timestamp; NaT where time is unknown.

    Built element-wise through plain Python strings rather than by adding two
    Series: pandas' string dtypes differ enough across versions that the
    concatenation form silently changes behaviour or raises.
    """
    has_time = time.notna().to_numpy()
    days = date.dt.strftime("%Y-%m-%d").to_numpy(dtype="object")
    times = time.to_numpy(dtype="object")
    combined = pd.Series(
        [f"{d} {t}" if ok else None for d, t, ok in zip(days, times, has_time)],
        index=date.index,
        dtype="object",
    )
    return pd.to_datetime(combined, format="%Y-%m-%d %H:%M", errors="coerce")


def _coerce_goals(values: pd.Series, label: str, issues: list[str]) -> pd.Series:
    """Nullable Int16 goals; anything not a non-negative integer becomes <NA>."""
    numeric = pd.to_numeric(values, errors="coerce")
    finite = numeric.notna() & np.isfinite(numeric.to_numpy(dtype="float64", na_value=np.nan))
    integral = finite & (numeric % 1 == 0)
    valid = integral & (numeric >= 0)

    bad = finite & ~valid
    if bad.any():
        offenders = numeric[bad].tolist()
        issues.append(
            f"{label}: {int(bad.sum())} value(s) not a non-negative integer "
            f"-> set to <NA>, rows retained: {offenders[:10]}"
        )
    return numeric.where(valid).astype("Int16")


def _odds_triple(frame: pd.DataFrame, cols: tuple[str, str, str]) -> pd.DataFrame:
    """Three decimal-odds columns as floats; invalid triples become all-NaN.

    A price at or below 1.0 is impossible for decimal odds (it implies a
    probability of 1 or more), so its presence means the cell is a placeholder
    rather than a quote. The whole triple is voided together — a de-vig needs
    all three or none.
    """
    if not all(c in frame.columns for c in cols):
        return pd.DataFrame(
            {c: np.full(len(frame), np.nan) for c in cols}, index=frame.index
        )
    out = frame[list(cols)].apply(pd.to_numeric, errors="coerce")
    usable = out.notna().all(axis=1) & (out > 1.0).all(axis=1)
    return out.where(usable, np.nan)


def blank_rows_issue(n: int) -> str:
    """The issue text for `n` fully blank trailing rows dropped from a file.

    THE VENDOR'S FORMATTING, NOT A DEFECT IN THE DATA. Every football-data
    season file ends with a line of bare commas; dropping it is this parser
    working, not this parser finding something wrong. The live E0 manifest's
    ONLY recorded issue, across twelve seasons, is this one line for 2014/15.

    It is a function rather than an inline f-string because `epl.build`'s strict
    gate has to recognise this exact issue and let it through, and the only way
    that recognition stays correct when the wording changes is for both sides to
    derive the string from here. Matching a prose fragment instead is how a gate
    quietly starts refusing — or quietly stops — after an unrelated edit.
    """
    return f"dropped {n} fully blank trailing row(s)"


def _match_id(
    season_code: str,
    date: pd.Timestamp,
    home_key: str,
    away_key: str,
    division: str = schema.DEFAULT_DIVISION,
) -> str:
    """Deterministic id: same inputs give the same id on any machine, any run.

    THE DIVISION IS IN THE PAYLOAD FOR EVERY DIVISION BUT E0, AND E0'S ABSENCE
    IS DELIBERATE. Without a division the two archives' ids live in one space
    keyed on (season, date, home, away), and the same two clubs meeting on the
    same date in two divisions would produce one id — which, in a table keyed on
    `match_id`, is one match. E0 ids are recorded in artifacts throughout the
    repository and may not move, so E0 keeps the original payload verbatim and
    every other division prefixes its code. The two id spaces are then disjoint
    up to a SHA-256 collision.
    """
    payload = f"{season_code}|{date:%Y-%m-%d}|{home_key}|{away_key}"
    if division != schema.DEFAULT_DIVISION:
        payload = f"{division}|{payload}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _refuse_phantom_clubs(
    season: str,
    division: str,
    dates: pd.Series,
    sides: tuple[tuple[str, list[str | None], pd.Series], ...],
) -> None:
    """Raise `PhantomClub` if any club key is null. Named, dated, quoted.

    Runs BEFORE the frame is assembled, so the offending row never reaches a
    projector that would turn its null key into a team identity.
    """
    offenders: list[str] = []
    for label, keys, raw_names in sides:
        for position, key in enumerate(keys):
            if key is None:
                offenders.append(
                    f"{dates.iloc[position]:%Y-%m-%d} {label}="
                    f"{raw_names.iloc[position]!r}"
                )
    if offenders:
        raise PhantomClub(
            f"{season} [{division}]: {len(offenders)} club key(s) did not "
            f"resolve, and a null club key is not a missing value — it becomes "
            f"a club. Refusing before the rows exist. Offending fixtures: "
            f"{offenders[:10]}"
            f"{' …' if len(offenders) > 10 else ''}. Register the spelling(s) in "
            f"epl/teams.py against the published census and re-run; do not drop "
            f"the season and do not null the club."
        )


def parse_season(
    season_code: str, division: str = schema.DEFAULT_DIVISION
) -> ParseResult:
    """Parse one cached season CSV into tidy rows."""
    schema.division_shape(division)
    season = fetch.season_label(season_code)
    issues: list[str] = []
    raw = pd.read_csv(io.StringIO(fetch.read_raw(season_code, division)))

    required = [_SRC_DATE, _SRC_HOME, _SRC_AWAY, _SRC_FTHG, _SRC_FTAG]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise ValueError(f"{season}: source CSV missing required columns {missing}")

    # football-data pads files with fully blank trailing rows. Drop only rows
    # with no date AND no teams; anything partially filled is a real problem and
    # must survive to be reported.
    blank = (
        raw[_SRC_DATE].isna() & raw[_SRC_HOME].isna() & raw[_SRC_AWAY].isna()
    )
    dropped_blank = int(blank.sum())
    raw = raw[~blank].reset_index(drop=True)

    date = parse_dates(raw[_SRC_DATE])
    if date.isna().any():
        offenders = raw.loc[date.isna(), _SRC_DATE].astype(str).unique().tolist()
        raise ValueError(
            f"{season}: {int(date.isna().sum())} date(s) matched neither "
            f"{_DATE_FORMATS[0]} nor {_DATE_FORMATS[1]}: {offenders[:10]}"
        )

    time = _parse_times(raw)
    kickoff = _build_kickoff(date, time)

    # --- teams ------------------------------------------------------------
    home_raw = raw[_SRC_HOME].map(teams.normalise_spelling)
    away_raw = raw[_SRC_AWAY].map(teams.normalise_spelling)
    raw_counts = pd.concat([home_raw, away_raw]).value_counts().to_dict()

    unknown: list[str] = []

    def _resolve(name: str) -> tuple[str | None, str | None]:
        try:
            return teams.resolve(name)
        except teams.UnknownTeamError:
            if name not in unknown:
                unknown.append(name)
            return None, None

    home_resolved = [_resolve(n) for n in home_raw]
    away_resolved = [_resolve(n) for n in away_raw]
    if unknown:
        issues.append(
            f"unregistered club spelling(s) {unknown} -> canonical name and key "
            f"left null; rows retained. Add them to epl/teams.py."
        )
    if division != schema.DEFAULT_DIVISION:
        _refuse_phantom_clubs(
            season,
            division,
            date,
            (
                ("home", [k for _, k in home_resolved], home_raw),
                ("away", [k for _, k in away_resolved], away_raw),
            ),
        )

    # --- results ----------------------------------------------------------
    fthg = _coerce_goals(raw[_SRC_FTHG], f"{season} FTHG", issues)
    ftag = _coerce_goals(raw[_SRC_FTAG], f"{season} FTAG", issues)
    played = fthg.notna() & ftag.notna()

    ftr = (
        raw[_SRC_FTR].astype("string").str.strip().str.upper()
        if _SRC_FTR in raw.columns
        else pd.Series(pd.NA, index=raw.index, dtype="string")
    )

    # --- odds (BENCHMARK ONLY) -------------------------------------------
    closing = _odds_triple(raw, _CLOSING_ODDS)
    opening = _odds_triple(raw, _OPENING_ODDS)
    has_closing = closing.notna().all(axis=1)
    has_opening = opening.notna().all(axis=1)

    odds = pd.DataFrame(
        {
            "odds_h": np.where(has_closing, closing[_CLOSING_ODDS[0]], opening[_OPENING_ODDS[0]]),
            "odds_d": np.where(has_closing, closing[_CLOSING_ODDS[1]], opening[_OPENING_ODDS[1]]),
            "odds_a": np.where(has_closing, closing[_CLOSING_ODDS[2]], opening[_OPENING_ODDS[2]]),
        },
        index=raw.index,
    )
    odds_source = pd.Series(pd.NA, index=raw.index, dtype="string")
    odds_source[has_opening] = "PS"
    odds_source[has_closing] = "PSC"
    overround = (1.0 / odds).sum(axis=1).where(odds.notna().all(axis=1))

    home_keys = [k for _, k in home_resolved]
    away_keys = [k for _, k in away_resolved]

    frame = pd.DataFrame(
        {
            "match_id": [
                _match_id(season_code, d, hk or "?", ak or "?", division)
                for d, hk, ak in zip(date, home_keys, away_keys)
            ],
            "season": season,
            "season_code": season_code,
            "date": date,
            "time": time,
            "kickoff": kickoff,
            "home_team_raw": home_raw.to_numpy(),
            "away_team_raw": away_raw.to_numpy(),
            "home_team": [n for n, _ in home_resolved],
            "away_team": [n for n, _ in away_resolved],
            "home_key": home_keys,
            "away_key": away_keys,
            "fthg": fthg,
            "ftag": ftag,
            "ftr": ftr,
            "played": played,
            "psch": closing[_CLOSING_ODDS[0]].to_numpy(),
            "pscd": closing[_CLOSING_ODDS[1]].to_numpy(),
            "psca": closing[_CLOSING_ODDS[2]].to_numpy(),
            "psh": opening[_OPENING_ODDS[0]].to_numpy(),
            "psd": opening[_OPENING_ODDS[1]].to_numpy(),
            "psa": opening[_OPENING_ODDS[2]].to_numpy(),
            "odds_h": odds["odds_h"].to_numpy(),
            "odds_d": odds["odds_d"].to_numpy(),
            "odds_a": odds["odds_a"].to_numpy(),
            "odds_source": odds_source,
            "odds_overround": overround.to_numpy(),
        }
    )
    frame = frame[schema.COLUMNS]

    if dropped_blank:
        issues.append(blank_rows_issue(dropped_blank))

    return ParseResult(
        season_code=season_code,
        season=season,
        division=division,
        frame=schema.sort_for_walk_forward(frame),
        issues=issues,
        raw_team_counts={str(k): int(v) for k, v in raw_counts.items()},
        unknown_teams=unknown,
        dropped_blank_rows=dropped_blank,
    )
