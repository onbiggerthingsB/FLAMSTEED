"""Open-Meteo historical climate adapter (daily temperature / precipitation).

Open-Meteo's **historical** archive API (ERA5 reanalysis) is FREE and needs no
API key. We only ever query *past* dates, and a past date's reanalysis value is
fixed — it does not get revised — so weather pulled this way is
**POINT_IN_TIME**: `valid_as_of == observed_at == the match date` (north-star
§4.2). No future leakage: we never read a date later than the match.

Attribution: weather data by Open-Meteo.com, licensed CC BY 4.0.

Tests run OFFLINE and never call `fetch_climate`; only a real run touches the
network. Cached via `cached_pull` (content-addressed by lat/lon/date).
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd

from wcmodel.data.cache import cached_pull

OPENMETEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

# Daily variables we request (free, no key). Mean temperature + total precip.
_DAILY_VARS = "temperature_2m_mean,precipitation_sum"


def fetch_climate(lat: float, lon: float, date: str, cache_dir: str | Path) -> dict:
    """Pull daily mean temp + total precip for a single past `date` (network).

    `date` is an ISO date string (YYYY-MM-DD). Returns
    ``{"date", "lat", "lon", "temperature_2m_mean", "precipitation_sum"}`` for
    that day. Cached by content key (lat, lon, date) so a re-pull is a no-op —
    and since past reanalysis is immutable, the cached value is point_in_time.

    Not called in tests (offline). No API key required.
    """
    def _fetch() -> pd.DataFrame:
        resp = httpx.get(
            OPENMETEO_ARCHIVE,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": date,
                "end_date": date,
                "daily": _DAILY_VARS,
                "timezone": "UTC",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        return pd.DataFrame({
            "date": daily.get("time", [date]),
            "lat": lat,
            "lon": lon,
            "temperature_2m_mean": daily.get("temperature_2m_mean", [None]),
            "precipitation_sum": daily.get("precipitation_sum", [None]),
        })

    df = cached_pull(
        "openmeteo_climate",
        {"lat": lat, "lon": lon, "date": date},
        _fetch,
        cache_dir=cache_dir,
    )
    return df.iloc[0].to_dict()
