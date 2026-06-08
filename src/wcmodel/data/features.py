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

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.cache import _git_commit
from wcmodel.data.elo import compute_elo_history
from wcmodel.data.sources.derived import altitude, rest_days, travel_distance
from wcmodel.data.store import BitemporalStore

# Manual invalidation lever for the content-addressed feature-panel cache. The
# panel-cache key (``_build_cache_key``) hashes the ``< cutoff`` inputs + config,
# NOT the code that turns them into the panel — so a change to ``build`` /
# ``compute_elo_history`` / the join logic that alters the panel's CONTENT or
# SCHEMA (without changing the elo/windows config or the ``< cutoff`` data) would
# otherwise serve a STALE cached panel. ``_git_commit()`` is folded into the key
# too, but it does NOT cover uncommitted working-tree edits, so BUMP this constant
# whenever ``build``'s output schema/semantics change to force a clean miss.
PANEL_SCHEMA_VERSION = "1"


def valid_played_results(results: pd.DataFrame) -> pd.DataFrame:
    """Coerce scores to numeric and keep only PLAYED matches with VALID goal
    counts: finite, non-negative, integral, non-null.

    This is THE SINGLE DEFINITION of a "valid played match" shared by
    :func:`build`, :func:`wcmodel.model.volatility_diagnostic.count_volatility_arm`,
    and the calibration Elo baseline (``calibration._leakage_safe_elo``) — so the
    model fit, the provisional set, and the baseline all consume the IDENTICAL row
    set (no inconsistency, no cache-key gap).

    Both score columns are first coerced with ``pd.to_numeric(errors="coerce")``,
    so a non-numeric/garbage score (e.g. a stray string from a malformed feed)
    becomes NaN. Each coerced score is then required to be a VALID goal count —
    FINITE, NON-NEGATIVE and INTEGRAL — forcing anything else (``inf`` / ``-1`` /
    ``1.5``, all of which ``to_numeric`` would otherwise let through) to NaN as
    well. The final ``notna()`` filter drops every such row, so an invalid score
    can never reach Elo (where a non-numeric would raise and an ``inf`` would
    NaN/inf-poison every downstream rating) or the panel. Real integer scores,
    including 0 (a 0-0 is a played match), are unaffected; the martj42 feed is
    already clean integers, so this is a no-op there and a guard everywhere else.

    Returns a COPY; the input frame is never mutated.
    """
    out = results.copy()
    for _c in ("home_score", "away_score"):
        s = pd.to_numeric(out[_c], errors="coerce")
        # inf / -1 / 1.5 -> NaN (then dropped below). `s == s.round()` is False
        # for non-integral AND for NaN/inf, so the mask keeps only finite,
        # non-negative, whole-number scores.
        out[_c] = s.where(np.isfinite(s) & (s >= 0) & (s == s.round()))
    return out.loc[
        out["home_score"].notna() & out["away_score"].notna()].copy()


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
    #     Score VALIDITY hygiene + the played notna() filter are the SHARED
    #     `valid_played_results` helper (the single definition of a "valid played
    #     match"): it coerces both scores to numeric, forces each to be FINITE /
    #     NON-NEGATIVE / INTEGRAL (so `inf`/`-1`/`1.5` -> NaN), then drops every
    #     null-score row — so an invalid score never reaches Elo or the panel.
    #     count_volatility_arm and the calibration Elo baseline call the SAME
    #     helper, so the model fit, the provisional set, and the baseline all
    #     consume the identical row set. (No-op on the already-clean martj42 feed.)
    results = valid_played_results(results)

    # 2) Per-match match_type tag (drives the Elo K multiplier AND is a tier).
    results["match_type"] = results["tournament"].map(tiers.match_type)

    if results.empty:
        return _empty_frame()

    # 2b) Point-in-time Elo: recompute on THIS < cutoff slice every call. We do
    #     NOT precompute across the full panel and slice by row — a row's Elo
    #     must reflect only pre-cutoff information. O(N) per cutoff by design
    #     (correctness over speed); Phase-4 may memoise/incrementalise this.
    #     The resolved `cfg` is threaded so the Elo K/T params come from the
    #     PASSED config (not global disk) — a custom cfg["elo"] (a lockbox K/T
    #     sweep) thus actually drives elo_pre + the provisional flags, matching
    #     the posterior cache key (closes the Task-0 stale-serve finding). Only
    #     the K/T PARAMS change; the `< cutoff` data window is untouched above,
    #     so per-cutoff leakage-safety is preserved exactly.
    elo = compute_elo_history(
        results[["match_id", "date", "home_team", "away_team",
                 "home_score", "away_score", "neutral", "match_type"]],
        config=cfg,
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


def _build_cache_key(cutoff, store: BitemporalStore, cfg: dict) -> str:
    """Content key for the per-cutoff feature panel — cheap, leakage-safe.

    The panel ``build`` emits is fully determined by (a) the ``< cutoff`` valid-
    played results (every column ``compute_elo_history`` + the venue/travel/rest
    joins consume), (b) the presence/content of the optional ``xg`` / ``venues``
    tables as-of the cutoff, and (c) the ``elo`` + ``windows`` config blocks (they
    drive ratings, the provisional flags, decay weights, and the feature window).
    Hashing exactly those — and NOTHING that peeks past the cutoff — gives a key
    that is STABLE across runs (sorted by ``match_id`` so DuckDB's read order is
    irrelevant) yet flips whenever any < cutoff input changes (so a cached panel
    is never stale).

    Crucially this recomputes the cheap ``< cutoff`` slice (a store read + a
    valid-played filter + a hash) but does NOT run the O(N) Elo loop — so the key
    is microseconds, not the 5-minute panel build. Leakage-safety is identical to
    ``build``: the same ``store.read(cutoff)`` + ``date < cutoff_day`` +
    valid-played gate; no post-cutoff row is ever read.
    """
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tz is not None:
        cutoff = cutoff.tz_convert("UTC").tz_localize(None)
    cutoff_day = cutoff.normalize()

    results = store.read("results", cutoff=cutoff)
    results["date"] = pd.to_datetime(results["date"])
    if getattr(results["date"].dt, "tz", None) is not None:
        results["date"] = results["date"].dt.tz_convert("UTC").dt.tz_localize(None)
    results = results.loc[results["date"] < cutoff_day].copy()
    results = valid_played_results(results)
    results["match_type"] = results["tournament"].map(tiers.match_type)

    # The columns that actually determine the panel: the Elo inputs PLUS `city`
    # (drives travel/venue joins). Sorted by match_id so the DuckDB read order
    # (non-deterministic across processes) cannot change the hash.
    key_cols = ["match_id", "date", "home_team", "away_team", "home_score",
                "away_score", "neutral", "match_type", "city"]
    key_cols = [c for c in key_cols if c in results.columns]
    slim = results[key_cols].sort_values("match_id", kind="mergesort").reset_index(drop=True)
    res_blob = pd.util.hash_pandas_object(slim, index=False).values.tobytes()
    res_hash = hashlib.sha256(res_blob).hexdigest()[:16]

    # Optional sources (NULL-safe in build): fold a cheap presence+content hash so
    # a newly-loaded xg/venues table (which would change the panel) misses. Most
    # CLV/backtest stores carry neither, so this is typically two "none" tokens.
    # CRITICAL: ``store.read`` returns rows in a process-unstable DuckDB order, so
    # the hash MUST be made row-order-independent — sort BOTH columns (axis=1) AND
    # rows by their full content before hashing — else the key would flip every
    # call and the panel cache would MISS every time (the same bug the result-hash
    # and the Elo total-order fix address).
    def _opt_hash(name: str) -> str:
        tbl = _try_read(store, name, cutoff)
        if tbl is None or tbl.empty:
            return "none"
        try:
            sorted_tbl = tbl.sort_index(axis=1)
            sorted_tbl = sorted_tbl.sort_values(
                list(sorted_tbl.columns), kind="mergesort").reset_index(drop=True)
            blob = pd.util.hash_pandas_object(sorted_tbl, index=False).values.tobytes()
            return hashlib.sha256(blob).hexdigest()[:16]
        except Exception:
            # CONTENT-BEARING fallback (never a row-count-only token): a bare
            # ``present:{len}`` collided two DISTINCT same-length tables onto one
            # key -> a stale-serve risk. Serialize the table to parquet and digest
            # the bytes so the fallback still depends on CONTENT. The parquet byte-
            # stream can carry the (process-unstable) read order, so a benign extra
            # MISS is possible — acceptable, and strictly safer than a false HIT.
            return "blob:" + hashlib.sha256(tbl.to_parquet(index=False)).hexdigest()[:16]

    payload = {
        # The as-of CUTOFF itself (tz-coerced to the SAME tz-naive-UTC form
        # ``build`` consumes above) — BLOCKING fix. ``build`` derives
        # ``age_days = (cutoff - date)`` -> ``decay_weight`` / ``in_feature_window``
        # from this exact value, so two DIFFERENT-day cutoffs that happen to share
        # the same ``< cutoff_day`` result set produce DIFFERENT panels (different
        # decay weights). Omitting the cutoff collided them, serving the earlier
        # cutoff's wrongly-weighted panel for the later one (a mild look-ahead).
        "cutoff": str(cutoff),
        "results": res_hash,
        "n_results": int(len(slim)),
        "xg": _opt_hash("xg"),
        "venues": _opt_hash("venues"),
        "elo": cfg["elo"],
        "windows": cfg["windows"],
        # Code-version tokens (mirror the posterior key): a change to ``build`` /
        # ``compute_elo_history`` / the joins that alters panel CONTENT — but not
        # the elo/windows config or the ``< cutoff`` data — would otherwise serve a
        # STALE cached panel. ``_git_commit`` ignores uncommitted edits, so
        # ``PANEL_SCHEMA_VERSION`` is the manual invalidation lever (bump it on any
        # schema/semantics change to ``build``).
        "schema_version": PANEL_SCHEMA_VERSION,
        "git": _git_commit(),
        # The covariate-missing-indicator + travel/altitude joins read `city`;
        # `model.covariates` does not change the panel columns build emits (it is
        # consumed downstream in fit), so it is intentionally NOT keyed here.
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def build_cached(cutoff, store: BitemporalStore, config: dict | None = None, *,
                 cache_dir: str | Path | None = None) -> pd.DataFrame:
    """``build`` through a content-addressed on-disk panel cache (the speed fix).

    ``build`` recomputes the per-cutoff Elo over the WHOLE ``< cutoff`` history on
    every call — measured at ~5 minutes over the full ~46k-match martj42 panel.
    The walk-forward / CLV backtests refit at several cutoffs and RE-run end-to-end
    often, so that O(N) recompute dominates wall-clock and is paid AGAIN on every
    identical re-run (the posterior cache never helped, because computing its key
    via ``_feature_hash`` itself calls ``build``). This wrapper persists the built
    panel as a parquet keyed by ``_build_cache_key`` (the < cutoff result-set +
    elo/windows config), so a HIT reads the panel from disk in milliseconds with
    NO Elo recompute.

    Correctness is IDENTICAL to ``build``: the cached panel was produced by ``build``
    on exactly this < cutoff slice + config; any change to either flips the key ->
    a miss -> a fresh ``build``. Leakage-safety is unchanged — the key is computed
    from the same ``< cutoff`` gate and the panel itself is ``build``'s leakage-safe
    output. ``cache_dir=None`` (the default when no dir is threaded) bypasses the
    cache entirely and just calls ``build`` — so existing callers are unaffected.
    """
    cfg = config or load_config()
    if cache_dir is None:
        return build(cutoff, store, cfg)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _build_cache_key(cutoff, store, cfg)
    path = cache_dir / f"featpanel-{key}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    panel = build(cutoff, store, cfg)
    # Persist atomically (temp + rename) so a crashed write never leaves a
    # truncated parquet a later run would read as a valid (corrupt) HIT.
    tmp = cache_dir / f"featpanel-{key}.parquet.tmp"
    panel.to_parquet(tmp, index=False)
    tmp.replace(path)
    return panel


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
