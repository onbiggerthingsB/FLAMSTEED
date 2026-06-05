"""Live result-ingest (Phase-5 §2.2) — write a FINISHED fixture's ACTUAL score into
``results`` POINT_IN_TIME, ``observed_at = now``.

As a fixture finishes we record its real result over the existing NaN-score schedule
row (``ingest_wc_group_fixtures`` wrote the schedule; this writes the result). The
store is bitemporal POINT_IN_TIME, so the result becomes visible only AT/after its
``observed_at`` (the final whistle) — a ``read(now)`` before the whistle never sees
it. Knockouts (post-L3) carry the shootout ``winner_override`` so the sim's D3 fix
(Task 7) can resolve a level pinned KO to the ACTUAL winner.

LEAKAGE-SAFE (binding). This only EVER fills the ACTUAL played result (an unplayed /
NaN-score "result" is refused), and ``observed_at`` must be >= the match date (a
result cannot be known before it is played). The downstream ``< cutoff`` discipline
(``features.build`` / ``sim/run._played_as_of``) is untouched — a result dated/observed
on day D is not conditioned on until a cutoff strictly after D.

The row is shaped + ``match_id``-stamped by the SAME ``normalize_results`` the martj42
adapter uses, so a live result keys identically to a historical one (the
``(date, home, away, city)`` identity). A nullable ``winner_override`` column is
carried through (NaN for group fixtures; the shootout winner for a penalty-decided KO).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy

#: Source tag for live-ingested results (distinct from the martj42 historical pull).
LIVE_RESULT_SOURCE = "wc2026_live"


def ingest_live_result(store: BitemporalStore, *, home_team: str, away_team: str,
                       date: str | pd.Timestamp, home_score, away_score,
                       tournament: str, neutral: bool, city: str, country: str,
                       observed_at: str | pd.Timestamp,
                       winner_override: str | None = None) -> int:
    """Write ONE finished fixture's ACTUAL result into ``results`` POINT_IN_TIME.

    Returns the number of rows written (1). Refuses an unplayed (NaN) score and an
    ``observed_at`` earlier than the match date (a result cannot be known before it
    is played). ``winner_override`` is the penalty-shootout winner for a level KO
    (else ``None`` -> NaN); it rides on a nullable column the sim's D3 fix reads.
    """
    # REFUSE an unplayed result: this writer records ACTUAL played results only.
    def _is_nan(x) -> bool:
        try:
            return x is None or (isinstance(x, float) and math.isnan(x)) or pd.isna(x)
        except (TypeError, ValueError):
            return False
    if _is_nan(home_score) or _is_nan(away_score):
        raise ValueError(
            "ingest_live_result refuses an unplayed (NaN-score) fixture — it records "
            "ACTUAL played results only (the schedule row already exists)"
        )

    match_date = pd.Timestamp(date).normalize()
    observed = pd.Timestamp(observed_at)
    # Normalize the final-whistle stamp to tz-NAIVE UTC — the store's stored
    # timestamps (and every downstream `cutoff.tz_convert("UTC").tz_localize(None)`
    # consumer: features.build, sim/run, walkforward, calibration) are tz-naive
    # UTC. Writing a tz-AWARE observed_at instead makes the bitemporal POINT_IN_TIME
    # read session-timezone-dependent (DuckDB compares a TIMESTAMPTZ column against a
    # naive `TIMESTAMP 'cutoff'` literal via the local session tz), which would let a
    # pre-whistle read see the result. Collapsing to naive UTC makes the leakage-safe
    # `observed_at <= cutoff` boundary exact and tz-agnostic.
    obs_utc = observed.tz_convert("UTC").tz_localize(None) if observed.tz is not None else observed
    # A result cannot be 'known' before it is played: observed_at >= the match date.
    if obs_utc.normalize() < match_date:
        raise ValueError(
            f"observed_at {obs_utc.date()} is before the match date {match_date.date()}: "
            "a played result cannot be observed before kickoff (leakage-safe PIT)"
        )

    raw = pd.DataFrame([{
        "date": match_date,
        "home_team": home_team,
        "away_team": away_team,
        "home_score": int(home_score),
        "away_score": int(away_score),
        "tournament": tournament,
        "neutral": bool(neutral),
        "city": city,
        "country": country,
    }])
    out = normalize_results(raw)                       # match_id + valid_as_of==observed_at==date
    # POINT_IN_TIME observed-at = the final whistle `now`, as tz-NAIVE UTC (overrides
    # the date-stamp normalize_results sets), so the result is visible only AT/after
    # the whistle and the boundary is tz-agnostic (see obs_utc note above).
    out["observed_at"] = obs_utc
    # Carry the nullable shootout-winner override (NaN for group fixtures).
    out["winner_override"] = winner_override if winner_override is not None else np.nan

    store.write(
        "results",
        out,
        policy=Policy.POINT_IN_TIME,
        keys=["match_id"],
        source=LIVE_RESULT_SOURCE,
        source_version=LIVE_RESULT_SOURCE,
    )
    return len(out)
