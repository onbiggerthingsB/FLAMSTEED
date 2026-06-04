"""Predict-time rest_days, leakage-safe.

rest_days for a fixture = days since the team's most recent PLAYED match that
EXISTS at the cutoff. If the team has no such prior match (e.g. its previous
fixture is itself unplayed/future at the cutoff), rest is NULL (NaN) — the
NULL-safe model handles it. NEVER computed from unplayed/future fixtures.

PLAYED CONTRACT (caller's responsibility). ``played_schedule`` MUST contain
ONLY matches that have actually been PLAYED and that already EXIST at the
cutoff. This helper has NO score column and therefore CANNOT verify played-ness
itself — that is a caller contract, the same division of labor as Phase-1's
``derived.rest_days``, which runs over the already-played-filtered panel. The
helper's only leakage guard is the strict ``date < cutoff`` (and ``< fixture``)
filter; it cannot tell a played match from an unplayed fixture that merely
happens to be dated before the cutoff. Passing an unplayed row dated < cutoff
would (incorrectly) be treated as the team's most recent PLAYED match and used
as the predecessor. Callers MUST pre-filter to played matches.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def predict_rest_days(team, fixture_date, cutoff, played_schedule: pd.DataFrame):
    fixture_date = pd.Timestamp(fixture_date); cutoff = pd.Timestamp(cutoff)
    # tz-SAFE (mirror features.build / count_volatility_arm): coerce BOTH the
    # cutoff AND the fixture_date to tz-naive UTC, and coerce the schedule `date`
    # column the same way. A tz-aware-vs-tz-naive comparison/subtraction raises
    # in pandas, so all three must live on the same (tz-naive UTC) clock.
    if cutoff.tz is not None:
        cutoff = cutoff.tz_convert("UTC").tz_localize(None)
    if fixture_date.tz is not None:
        fixture_date = fixture_date.tz_convert("UTC").tz_localize(None)
    s = played_schedule.copy()
    dates = pd.to_datetime(s["date"])
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_convert("UTC").dt.tz_localize(None)
    mask = (s["team"] == team) & (dates < cutoff.normalize()) & (dates < fixture_date)
    if not mask.any():
        return np.nan
    # `last` MUST come from the tz-COERCED `dates` (not the original `s["date"]`
    # column), so it is always tz-naive and the final subtraction never mixes a
    # tz-aware `last` with the tz-naive `fixture_date`.
    last = dates[mask].max()
    return int((fixture_date - last).days)
