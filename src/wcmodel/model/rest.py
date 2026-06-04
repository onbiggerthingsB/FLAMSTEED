"""Predict-time rest_days, leakage-safe.

rest_days for a fixture = days since the team's most recent PLAYED match that
EXISTS at the cutoff. If the team has no such prior match (e.g. its previous
fixture is itself unplayed/future at the cutoff), rest is NULL (NaN) — the
NULL-safe model handles it. NEVER computed from unplayed/future fixtures.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def predict_rest_days(team, fixture_date, cutoff, played_schedule: pd.DataFrame):
    fixture_date = pd.Timestamp(fixture_date); cutoff = pd.Timestamp(cutoff)
    if cutoff.tz is not None:                      # tz-safe (mirror features.build)
        cutoff = cutoff.tz_convert("UTC").tz_localize(None)
    s = played_schedule.copy()
    dates = pd.to_datetime(s["date"])
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_convert("UTC").dt.tz_localize(None)
    prior = s[(s["team"] == team) & (dates < cutoff.normalize()) & (dates < fixture_date)]
    if prior.empty:
        return np.nan
    last = pd.to_datetime(prior["date"]).max()
    return int((fixture_date - last).days)
