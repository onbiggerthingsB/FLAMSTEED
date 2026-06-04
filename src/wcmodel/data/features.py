"""Feature assembly — the per-cutoff integration heart (north-star §4.3, spec §5).

``build(cutoff, store)`` materialises ONE leakage-safe feature panel as of a
single ``cutoff``: every fitted statistic is computed strictly from the
``date < cutoff`` slice, every missing feature is NULL (never imputed), and each
row carries its point-in-time provenance (time-decay weight, feature-window
flag, revision-contamination exposure).

Per-cutoff discipline (non-negotiable)
--------------------------------------
Elo is recomputed by running :func:`compute_elo_history` on the ``< cutoff``
results EACH call — we deliberately do NOT precompute ratings across the full
panel and slice by row, because a row's Elo must reflect only what was knowable
before ``cutoff``. This is an O(N) recompute per cutoff (correctness over speed);
Phase-4 may memoise/incrementalise it — see the inline note at the recompute.

NULL-safe, no imputation
------------------------
Uncovered match (no StatsBomb xG) -> ``xg_for``/``xg_against`` = NaN with
``xg_covered = False``. Missing venue coords (sparse historical city->coord
coverage) -> ``travel_km``/``altitude_m``/climate = NaN. A missing feature is
NEVER filled with 0 / mean / anything.

Point-in-time
-------------
``elo_pre`` is the pre-match rating (the leakage-safe feature); ``rest_days``
uses only prior fixtures. No row uses its own match outcome as a feature — the
result is the label, carried as ``home_score`` / ``away_score`` for downstream
use only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.elo import compute_elo_history
from wcmodel.data.sources.derived import altitude, rest_days, travel_distance
from wcmodel.data.store import BitemporalStore


def _try_read(store: BitemporalStore, name: str, cutoff: pd.Timestamp):
    """Read a store table, returning ``None`` if that source isn't present.

    xG and venue coords are optional inputs (StatsBomb covers only a slice of
    matches; the city->coord table may not be loaded) — their absence is a
    NULL-safe no-op, not an error.
    """
    try:
        return store.read(name, cutoff=cutoff)
    except FileNotFoundError:
        return None


def build(cutoff, store: BitemporalStore, config: dict | None = None) -> pd.DataFrame:
    """Assemble the per-cutoff feature panel — one row per ``(match_id, team)``.

    Parameters
    ----------
    cutoff
        As-of date. Only matches with ``date < cutoff`` are used, and every
        fitted statistic is computed from that slice alone.
    store
        The bitemporal store to read ``results`` (and, if present, ``xg`` /
        ``venues``) from.
    config
        Optional pre-loaded config dict (defaults to :func:`load_config`).
    """
    cfg = config or load_config()
    cutoff = pd.Timestamp(cutoff)
    # A tz-AWARE cutoff (e.g. an Odds API `Z`/UTC timestamp) must be coerced to
    # tz-naive UTC before flooring: match dates are tz-naive date-only
    # (midnight), and a tz-aware-vs-tz-naive comparison raises in pandas.
    # Interpret the cutoff's instant in UTC, then drop the tz so it compares
    # cleanly against the tz-naive dates. Day-boundary semantics (same-day
    # excluded / prior-day included) are unchanged. (The intraday odds path is
    # separate and untouched — see ASSUMPTIONS.md "Cutoff resolution".)
    if cutoff.tz is not None:
        cutoff = cutoff.tz_convert("UTC").tz_localize(None)

    # 1) Results, strictly before the cutoff DAY. Match dates are date-resolution
    #    (stored at midnight), so a match on day D is not knowable until D+1 00:00
    #    — its real kickoff may fall after an intraday bet_time cutoff on D. We
    #    therefore floor the cutoff to its day and filter `date < cutoff_day`, so
    #    a same-day match never leaks (e.g. cutoff "2024-06-20 12:00" excludes a
    #    match dated 2024-06-20). This day-normalization is a FEATURES-LAYER
    #    convention for DATE-ONLY match knowability ONLY: the store's
    #    point-in-time read is left at true resolution, and intraday-timestamped
    #    sources (odds bet_time/close) are NEVER day-normalized — doing so would
    #    misalign entry-vs-close and corrupt CLV (see ASSUMPTIONS.md).
    cutoff_day = cutoff.normalize()
    results = store.read("results", cutoff=cutoff)
    results["date"] = pd.to_datetime(results["date"])
    # Symmetric tz-coercion: the cutoff side is already tz-naive UTC (above), so
    # the RESULT date side must be too. If a source emits a tz-AWARE date (e.g.
    # `2024-06-19T00:00:00Z`), the bare `< cutoff_day` filter — and the later
    # age-days calc — would raise a tz-aware-vs-tz-naive comparison error. Coerce
    # the instant to UTC then drop the tz so both sides compare cleanly; this
    # single naive `results["date"]` then feeds BOTH the day-floor filter and the
    # age/decay_weight calc (no tz-aware path remains downstream).
    if getattr(results["date"].dt, "tz", None) is not None:
        results["date"] = results["date"].dt.tz_convert("UTC").dt.tz_localize(None)
    results = results.loc[results["date"] < cutoff_day].copy()

    # 1b) PLAYED FILTER (leakage-critical). An UNPLAYED fixture — null
    #     home_score or away_score — is a SCHEDULE entry, not a RESULT: it has no
    #     outcome, hence no rating delta and no label. It must be excluded from
    #     BOTH the feature panel and the Elo input EVEN when its date is before
    #     the cutoff. Two cases this walls off at the cutoff boundary:
    #       - an in-progress tournament fixture (kickoff on day D-2 but no score
    #         yet at a day-D cutoff) — `date < cutoff_day` would otherwise admit
    #         it as an as-of feature with a NaN label;
    #       - a future-dated, not-yet-played WC-2026 group row ingested into the
    #         store (NaN scores) — date already excludes it at a pre-WC cutoff,
    #         and THIS filter additionally excludes it at a mid-tournament cutoff
    #         where its date has passed but it still has no result.
    #     Dropping it here (before compute_elo_history) also stops a NaN score
    #     from poisoning the Elo recompute. (See ASSUMPTIONS.md "Played filter".)
    #
    #     Score VALIDITY hygiene: coerce both score columns to numeric FIRST, so
    #     any non-numeric/garbage score (e.g. a stray string from a malformed
    #     feed) becomes NaN. Then require each coerced score to be a VALID goal
    #     count — FINITE, NON-NEGATIVE and INTEGRAL — forcing anything else
    #     (`inf`/`-1`/`1.5`, all of which `to_numeric` would otherwise let
    #     through) to NaN as well. The very next notna() filter then drops every
    #     such row, so an invalid score can never reach Elo (where a non-numeric
    #     would raise and an `inf` would NaN/inf-poison every downstream rating)
    #     or the panel. Real integer scores, including 0 (a 0-0 is a played
    #     match), are unaffected; the martj42 feed is already clean integers, so
    #     this is a no-op there and a guard everywhere else.
    for _c in ("home_score", "away_score"):
        s = pd.to_numeric(results[_c], errors="coerce")
        # inf / -1 / 1.5 -> NaN (then dropped below). `s == s.round()` is False
        # for non-integral AND for NaN/inf, so the mask keeps only finite,
        # non-negative, whole-number scores.
        s = s.where(np.isfinite(s) & (s >= 0) & (s == s.round()))
        results[_c] = s
    results = results.loc[
        results["home_score"].notna() & results["away_score"].notna()].copy()

    # 2) Per-match match_type tag (drives the Elo K multiplier AND is a tier).
    results["match_type"] = results["tournament"].map(tiers.match_type)

    if results.empty:
        return _empty_frame()

    # 2b) Point-in-time Elo: recompute on THIS < cutoff slice every call. We do
    #     NOT precompute across the full panel and slice by row — a row's Elo
    #     must reflect only pre-cutoff information. O(N) per cutoff by design
    #     (correctness over speed); Phase-4 may memoise/incrementalise this.
    elo = compute_elo_history(
        results[["match_id", "date", "home_team", "away_team",
                 "home_score", "away_score", "neutral", "match_type"]]
    )

    # One output row per (match_id, team), seeded from the Elo long frame (which
    # already carries opponent / is_home / neutral / provisional / rating_pre).
    df = elo.rename(columns={"rating_pre": "elo_pre"})[
        ["match_id", "date", "team", "opponent", "is_home", "neutral",
         "elo_pre", "provisional"]
    ].copy()
    df["date"] = pd.to_datetime(df["date"])

    # Carry per-match context (match_type, scores as the LABEL only, venue city).
    match_ctx = results[["match_id", "match_type", "home_team", "away_team",
                         "home_score", "away_score", "city",
                         "revision_contaminated"]].rename(
        columns={"revision_contaminated": "_rc_results"})
    df = df.merge(match_ctx, on="match_id", how="left")

    # Team-perspective label scores (home_score/away_score kept as the outcome
    # to predict — never used as a same-match feature).
    df["team_score"] = np.where(df["is_home"], df["home_score"], df["away_score"])
    df["opponent_score"] = np.where(df["is_home"], df["away_score"], df["home_score"])

    # 3) Tier tags per team.
    df["confederation"] = df["team"].map(tiers.confederation)
    df["covid"] = df["date"].map(tiers.is_covid)
    df["strength_band"] = _strength_bands(elo, df["team"])

    # 4) xG left-join — NULL-safe, NEVER imputed.
    df = _join_xg(df, _try_read(store, "xg", cutoff))

    # 5) Derived: rest_days (prior fixtures only) + venue-coord features.
    df = _join_rest_days(df)
    df = _join_venue_features(df, _try_read(store, "venues", cutoff), cfg)

    # 6) Point-in-time provenance columns.
    windows = cfg["windows"]
    half_life = float(windows["decay_half_life_days"])
    feature_years = float(windows["feature_years"])

    age_days = (cutoff - df["date"]).dt.days.astype(float)
    df["age_days"] = age_days
    df["decay_weight"] = 0.5 ** (age_days / half_life)
    df["in_feature_window"] = age_days <= feature_years * 365

    # revision_contaminated_exposure = max contamination flag across joined
    # sources. The clean core (results/elo/tiers/derived/StatsBomb-xG) is all
    # point-in-time, so this is 0.0; a current_only source (e.g. a future
    # market-value feed) would surface here as 1.0. Absence of a source (no xG
    # row) is NOT contamination -> contributes 0.0, not NaN.
    rc_cols = [c for c in ("_rc_results", "_rc_xg") if c in df.columns]
    exposure = pd.Series(0.0, index=df.index)
    for c in rc_cols:
        exposure = np.maximum(exposure, df[c].fillna(False).astype(float))
    df["revision_contaminated_exposure"] = exposure
    df = df.drop(columns=rc_cols)

    return df.reset_index(drop=True)


def _strength_bands(elo: pd.DataFrame, teams: pd.Series) -> pd.Series:
    """Point-in-time strength band per team.

    Ranks every team by its LATEST pre-match rating (``rating_pre``) in the
    ``< cutoff`` Elo history — the best as-of-cutoff strength estimate that does
    not peek past any match — then maps the integer rank (1 = best) through
    :func:`tiers.strength_band`. Mapped back onto each output row by team.
    """
    last = (elo.sort_values("date", kind="mergesort")
               .groupby("team", sort=False)["rating_pre"].last())
    rank = last.rank(method="first", ascending=False).astype(int)
    band = rank.map(tiers.strength_band)
    return teams.map(band)


def _join_xg(df: pd.DataFrame, xg: pd.DataFrame | None) -> pd.DataFrame:
    """Left-join StatsBomb xG -> xg_for / xg_against / xg_covered (NULL-safe).

    ``xg`` (if present) is one row per ``(match_id, team)`` with the team's
    summed ``xg``. ``xg_for`` is that team's xG; ``xg_against`` is the opponent's
    (same match, opponent team). A match-team with no StatsBomb row keeps NaN xG
    and ``xg_covered = False`` — coverage gap, never imputed.
    """
    if xg is None or xg.empty:
        df["xg_for"] = np.nan
        df["xg_against"] = np.nan
        df["xg_covered"] = False
        df["_rc_xg"] = 0.0
        return df

    rc_xg = xg[["match_id", "team", "revision_contaminated"]].rename(
        columns={"revision_contaminated": "_rc_xg"})
    xg_for = xg[["match_id", "team", "xg"]].rename(columns={"xg": "xg_for"})
    xg_against = xg[["match_id", "team", "xg"]].rename(
        columns={"team": "opponent", "xg": "xg_against"})

    df = df.merge(xg_for, on=["match_id", "team"], how="left")
    df = df.merge(xg_against, on=["match_id", "opponent"], how="left")
    df = df.merge(rc_xg, on=["match_id", "team"], how="left")
    # Coverage is presence of the team's own xG row (never fabricated).
    df["xg_covered"] = df["xg_for"].notna()
    df["_rc_xg"] = df["_rc_xg"].fillna(0.0)
    return df


def _join_rest_days(df: pd.DataFrame) -> pd.DataFrame:
    """Attach per-team rest_days from the < cutoff schedule (prior fixtures only).

    Built from the distinct ``(team, date)`` schedule so a team's rest reflects
    its own prior match only; each team's first fixture in the slice has NaN
    rest (no prior fixture — no future leakage).
    """
    sched = df[["team", "date"]].drop_duplicates().reset_index(drop=True)
    sched = rest_days(sched)
    return df.merge(sched, on=["team", "date"], how="left")


def _join_venue_features(df: pd.DataFrame, venues: pd.DataFrame | None,
                         cfg: dict) -> pd.DataFrame:
    """Attach travel_km / altitude_m (+ climate placeholders) — NaN where sparse.

    Venue coords are keyed by the results ``city``. Historical city->coord
    coverage is sparse, so a city absent from the venues table yields NaN for
    travel and altitude (NULL-safe, never imputed). Climate joins where venue
    coords exist; with no coords it is NaN. (Per-day climate values come from a
    network pull in a real run; ``build`` leaves them NaN unless a climate
    source is wired in, never imputing.)
    """
    if venues is None or venues.empty:
        df["travel_km"] = np.nan
        df["altitude_m"] = np.nan
        df["temperature_2m_mean"] = np.nan
        df["precipitation_sum"] = np.nan
        return df

    # derived.{travel_distance,altitude} key on a "venue" column.
    venues_df = venues.rename(columns={"city": "venue"})[
        ["venue", "lat", "lon", "altitude_m"]].copy()

    # Per-team previous venue (city) from the < cutoff schedule, for travel.
    sched = (df[["team", "date", "city"]].drop_duplicates()
               .sort_values(["team", "date"], kind="mergesort"))
    sched["prev_city"] = sched.groupby("team", sort=False)["city"].shift(1)
    prev = sched[["team", "date", "prev_city"]]
    d = df.merge(prev, on=["team", "date"], how="left")

    d["travel_km"] = [
        travel_distance(pc, c, venues_df)
        for pc, c in zip(d["prev_city"], d["city"])
    ]
    d["altitude_m"] = [altitude(c, venues_df) for c in d["city"]]

    # Climate: only knowable where the venue has coords; left NaN otherwise and
    # NaN here (no network in build) — never imputed.
    d["temperature_2m_mean"] = np.nan
    d["precipitation_sum"] = np.nan
    return d.drop(columns=["prev_city"])


def _empty_frame() -> pd.DataFrame:
    """Empty panel with the full feature schema (no < cutoff matches)."""
    cols = [
        "match_id", "date", "team", "opponent", "is_home", "neutral",
        "elo_pre", "provisional", "match_type", "home_team", "away_team",
        "home_score", "away_score", "city", "team_score", "opponent_score",
        "confederation", "covid", "strength_band", "xg_for", "xg_against",
        "xg_covered", "rest_days", "travel_km", "altitude_m",
        "temperature_2m_mean", "precipitation_sum", "age_days", "decay_weight",
        "in_feature_window", "revision_contaminated_exposure",
    ]
    return pd.DataFrame(columns=cols)
