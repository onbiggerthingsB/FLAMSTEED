"""Derived match features: rest days, travel distance, altitude.

These features are **POINT_IN_TIME by construction** — they are computed purely
from the immutable fixture schedule + static venue coordinates, so they contain
no future leakage. A team's rest before a match depends only on *prior* fixtures
(the first match has NaN rest), travel distance depends only on the *previous*
venue, and altitude is a fixed property of the venue. None of these can ever be
revised after the fact, so `valid_as_of == observed_at == match date` (north-star
§4.2). No network, no store dependency here — pure functions over DataFrames.
"""
from __future__ import annotations

import math

import pandas as pd

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points in kilometres.

    Uses the haversine formula with Earth radius 6371 km. London -> Paris is
    ~343 km (sanity check). Returns 0.0 for identical points.
    """
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def rest_days(schedule: pd.DataFrame) -> pd.DataFrame:
    """Per-team days of rest since that team's previous fixture.

    `schedule` must have `team` and `date` columns. Within each team (sorted by
    date), `rest_days` is the gap in whole days to the previous fixture; the
    team's first match has NaN (no prior fixture — no leakage from the future).
    Returns the input frame (original row order preserved) with a `rest_days`
    column added.
    """
    df = schedule.copy()
    dates = pd.to_datetime(df["date"])
    # Sort within team by date, diff to the prior fixture, restore input order.
    order = dates.sort_values(kind="mergesort").index
    order = df.loc[order].sort_values("team", kind="mergesort").index
    prev = dates.loc[order].groupby(df.loc[order, "team"], sort=False).diff()
    df["rest_days"] = (prev.dt.total_seconds() / 86400.0).reindex(df.index)
    return df


def travel_distance(prev_venue, venue, venues_df: pd.DataFrame) -> float:
    """Haversine km between the previous venue and the current venue.

    NaN if `prev_venue` is missing (first match — no prior location) or either
    venue is unknown in `venues_df` (which must have `venue,lat,lon` columns).
    """
    if prev_venue is None or (isinstance(prev_venue, float) and math.isnan(prev_venue)):
        return float("nan")
    idx = venues_df.set_index("venue")
    if prev_venue not in idx.index or venue not in idx.index:
        return float("nan")
    a, b = idx.loc[prev_venue], idx.loc[venue]
    return haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])


def altitude(venue, venues_df: pd.DataFrame) -> float:
    """Altitude in metres for `venue`; NaN if unknown.

    `venues_df` must have `venue` and `altitude_m` columns.
    """
    idx = venues_df.set_index("venue")
    if venue not in idx.index:
        return float("nan")
    return float(idx.loc[venue, "altitude_m"])
