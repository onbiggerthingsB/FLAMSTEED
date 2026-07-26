"""Operator-authored fixtures CSV -> validated frame.

Contract: required columns {date, home, away}; optional `neutral`
("",0,1,true,false only — anything else fails loud); EXTRA columns are allowed
and dropped (venue/notes convenience). Public artifacts must not render from a
malformed row, so everything else is fail-loud."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_REQUIRED = ["date", "home", "away"]
_TRUE, _FALSE = {"1", "true", "True"}, {"", "0", "false", "False"}


def load_fixtures(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in _REQUIRED:
        if col not in df.columns:
            raise ValueError(f"fixtures CSV missing required column: {col!r}")
    if "neutral" not in df.columns:
        df["neutral"] = ""
    df = df[["date", "home", "away", "neutral"]].copy()

    dates = pd.to_datetime(df["date"], errors="coerce")
    # A tz-aware column would otherwise survive to the PIT compare in build.py and
    # die there as a raw TypeError; fixtures dates are calendar days, never instants.
    if dates.dtype.kind != "M" or getattr(dates.dt, "tz", None) is not None:
        raise ValueError("tz-aware (or mixed-offset) date(s) in fixtures CSV; "
                         "use naive calendar dates, e.g. 2026-09-21")
    if dates.isna().any():
        raise ValueError(
            f"unparseable date(s) in fixtures CSV: {df.loc[dates.isna(), 'date'].tolist()}")
    df["date"] = dates

    for col in ("home", "away"):
        df[col] = df[col].str.strip()
        if (df[col] == "").any():
            raise ValueError(f"blank team name in column {col!r}")
    if (df["home"] == df["away"]).any():
        raise ValueError(
            f"home == away in fixture row(s): {df.index[df['home'] == df['away']].tolist()}")

    dup = df.duplicated(subset=["date", "home", "away"], keep=False)
    if dup.any():
        raise ValueError(
            f"duplicate fixture row(s): {df.loc[dup, ['date', 'home', 'away']].to_dict('records')}")

    raw = df["neutral"].astype(str).str.strip()
    bad = ~(raw.isin(_TRUE) | raw.isin(_FALSE))
    if bad.any():
        raise ValueError(f"invalid neutral value(s): {sorted(raw[bad].unique())} "
                         f"(allowed: 0/1/true/false/blank)")
    df["neutral"] = raw.isin(_TRUE)

    if df.empty:
        raise ValueError("fixtures CSV has no rows")
    return df.reset_index(drop=True)


def unknown_teams(fixtures: pd.DataFrame, known: set[str]) -> list[str]:
    """Fixture team names absent from `known` (the posterior's team index).
    Membership test — never exception-probing (a KeyError names only ONE team)."""
    teams = set(fixtures["home"]) | set(fixtures["away"])
    return sorted(teams - set(known))
