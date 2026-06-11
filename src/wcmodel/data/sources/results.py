"""martj42/international_results adapter.

International match results are immutable: a result, once played, never gets
revised. So `valid_as_of == observed_at == match date` and the store policy is
POINT_IN_TIME (north-star §4.2). We keep `tournament` raw here — mapping it to
match-type tiers is Task 6.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from wcmodel.data.cache import cached_pull
from wcmodel.data.store import BitemporalStore, Policy

# Pinned to a specific commit (never `master`) so a re-pull is reproducible.
# Bumped 2026-06-09 (GitHub API: latest master = 6b6f8e9f, committed 2026-06-09T07:12Z)
# to ingest results through today before WC-2026 kickoff (Phase 0 §1).
#
# This pin is the REPRODUCIBILITY ANCHOR: every default fetch uses it. The fetch
# path also accepts an OPTIONAL ``commit=`` runtime override (e.g. the operator's
# ``daily_update.py --latest`` resolving the freshest master sha via the GitHub
# commits API). The override is threaded per-call into both the raw URL and the
# cache key — it NEVER mutates this constant at runtime, so the default path stays
# byte-identical and a re-pull at the pin remains reproducible.
MARTJ42_COMMIT = "6b6f8e9f321414957cc17861d8c2dbf25c4437b0"


def _martj42_raw_url(filename: str, commit: str) -> str:
    """The martj42 raw-content URL for ``filename`` at a specific ``commit``."""
    return (
        "https://raw.githubusercontent.com/martj42/international_results/"
        f"{commit}/{filename}"
    )


MARTJ42_RAW_URL = _martj42_raw_url("results.csv", MARTJ42_COMMIT)
# martj42 ships shootout winners in a SEPARATE file (the same pinned commit). The
# main results.csv stores only the regulation/ET score and DROPS the shootout winner,
# which is exactly why sim.tournament.simulate_one fails loud on a level pinned KO
# (Phase-4 D3 deferral). Ingesting this resolves D3 (Phase-5 L3, before R32).
MARTJ42_SHOOTOUTS_URL = _martj42_raw_url("shootouts.csv", MARTJ42_COMMIT)

_CARRY = ["home_team", "away_team", "home_score", "away_score",
          "tournament", "neutral", "city", "country"]


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def normalize_results(raw: pd.DataFrame) -> pd.DataFrame:
    """Pure transform: raw martj42 rows -> store-ready frame.

    No store/network dependency. Adds a deterministic `match_id`, parses `date`
    to datetime, and sets `valid_as_of == observed_at == date`.

    `match_id = sha1(f"{date}|{home_team}|{away_team}|{city}")`. `city` keeps
    multi-match days unique for the overwhelming majority of rows, but the real
    martj42 data has a genuine same-day/same-venue double-header (Tahiti vs New
    Caledonia, 1974-02-17, Papeete — two matches, different scores). Those rows
    collide on the base key, so we append a deterministic occurrence index
    (ordered by the full distinguishing tuple, content-stable) to the hash input
    only where it repeats. This guarantees `match_id.is_unique` while leaving
    every non-colliding row's id identical to the bare formula.
    """
    df = raw.copy()
    # Hash on the original (string) date so the id is stable regardless of how
    # the parsed timestamp later renders.
    base = (df["date"].astype(str) + "|" + df["home_team"].astype(str) + "|"
            + df["away_team"].astype(str) + "|" + df["city"].astype(str))
    # Deterministic, input-order-INDEPENDENT disambiguation for collisions. We
    # rank tied rows by their FULL distinguishing tuple — not score alone — so
    # the occurrence index (and thus which colliding row keeps the bare hash vs
    # gets a suffix) is fixed by content, never by feed position. Score alone was
    # insufficient: two rows tying on (date|home|away|city) AND on score but
    # differing in tournament/neutral got an input-order-dependent assignment.
    # A stable mergesort over the full tuple makes the id set identical for any
    # row ordering. Non-colliding rows (the vast majority) get occ == 0.
    order = df.sort_values(
        ["home_score", "away_score", "tournament", "neutral"],
        kind="mergesort").index
    occ = pd.Series(0, index=df.index)
    occ.loc[order] = df.loc[order].groupby(base.loc[order], sort=False).cumcount()
    keyed = base.where(occ == 0, base + "|" + occ.astype(str))
    df["match_id"] = keyed.map(_sha1)
    df["date"] = pd.to_datetime(df["date"])
    df["valid_as_of"] = df["date"]
    df["observed_at"] = df["date"]
    out = df[["match_id", "date", "valid_as_of", "observed_at", *_CARRY]]
    # Standing guard (systematic, not the 1974-double-header one-off): the
    # disambiguation REWRITES match_id for composite-key collisions, so it must
    # be row-PRESERVING (out count == in count — never drops a genuine match)
    # and the final id must be unique. A regression that silently dropped or
    # mis-suffixed a colliding row would trip here, not in some later join.
    # These are explicit raises, NOT asserts: `python -O` strips `assert`, which
    # would silently disable this integrity guard in optimized runs.
    if len(out) != len(raw):
        raise ValueError(
            f"normalize_results dropped rows: in={len(raw)}, out={len(out)}")
    if not out["match_id"].is_unique:
        raise ValueError(
            "normalize_results produced duplicate match_id after disambiguation")
    return out


def join_shootout_winners(results: pd.DataFrame,
                          shootouts: pd.DataFrame) -> pd.DataFrame:
    """Attach the penalty-shootout winner to results via a nullable ``winner_override``.

    Pure transform. ``shootouts`` is martj42's separate ``shootouts.csv`` (cols
    ``date, home_team, away_team, winner``); we LEFT-join it onto ``results`` by the
    ``(date, home_team, away_team)`` triple (the same identity the sim matches KO
    results on) and expose the winner as a nullable ``winner_override`` column (NaN
    for every non-shootout match). Row-PRESERVING (a left join never drops/adds a
    result row); a result with no shootout entry simply gets ``winner_override = NaN``.

    This supplies ONLY the ACTUAL played KO winner — it is leakage-safe (the
    ``< cutoff`` discipline downstream is untouched) and resolves the D3 fail-loud:
    ``sim.tournament.simulate_one`` reads this winner to resolve a level pinned KO
    instead of raising.
    """
    res = results.copy()
    if shootouts is None or shootouts.empty:
        res["winner_override"] = np.nan
        return res
    sh = shootouts.copy()
    sh["date"] = pd.to_datetime(sh["date"])
    res["date"] = pd.to_datetime(res["date"])
    sh = sh[["date", "home_team", "away_team", "winner"]].rename(
        columns={"winner": "winner_override"})
    # Drop duplicate shootout rows on the triple (defensive — keep the first) so the
    # left join can never multiply result rows.
    sh = sh.drop_duplicates(subset=["date", "home_team", "away_team"], keep="first")
    n_before = len(res)
    out = res.merge(sh, on=["date", "home_team", "away_team"], how="left")
    if len(out) != n_before:
        raise ValueError(
            f"join_shootout_winners changed the row count ({n_before} -> {len(out)}) "
            "— the shootout join must be row-preserving (one winner per result row)"
        )
    return out


def fetch_results(cache_dir: str | Path, *, commit: str | None = None) -> pd.DataFrame:
    """Pull the real martj42 CSV (network). Cached by content key + commit.

    ``commit`` is an optional RUNTIME override of the pinned ``MARTJ42_COMMIT``
    (default ``None`` -> the pin, byte-identical). It is threaded into both the
    raw URL and the cache key, so an override pulls (and caches) a distinct sha
    without mutating the module constant."""
    commit = commit or MARTJ42_COMMIT
    url = _martj42_raw_url("results.csv", commit)

    def _fetch() -> pd.DataFrame:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        from io import StringIO
        return pd.read_csv(StringIO(resp.text))

    return cached_pull(
        "martj42_results",
        {"commit": commit},
        _fetch,
        cache_dir=cache_dir,
    )


def fetch_shootouts(cache_dir: str | Path, *, commit: str | None = None) -> pd.DataFrame:
    """Pull martj42's separate shootouts.csv (network). Cached by content key + commit.

    ``commit`` is the same optional RUNTIME override as ``fetch_results`` (default
    ``None`` -> the pinned ``MARTJ42_COMMIT``)."""
    commit = commit or MARTJ42_COMMIT
    url = _martj42_raw_url("shootouts.csv", commit)

    def _fetch() -> pd.DataFrame:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        from io import StringIO
        return pd.read_csv(StringIO(resp.text))

    return cached_pull(
        "martj42_shootouts",
        {"commit": commit},
        _fetch,
        cache_dir=cache_dir,
    )


def load_results(store: BitemporalStore, cache_dir: str | Path,
                 *, commit: str | None = None) -> None:
    """Fetch -> normalize -> attach shootout winners -> write to the bitemporal store.

    ``commit`` is an optional RUNTIME override of the pinned ``MARTJ42_COMMIT``
    (default ``None`` -> the pin; the store ``source_version`` records whichever
    sha was actually fetched). It flows verbatim into ``fetch_results`` /
    ``fetch_shootouts`` so both files come from the SAME commit."""
    commit = commit or MARTJ42_COMMIT
    normalized = normalize_results(fetch_results(cache_dir, commit=commit))
    shootouts = fetch_shootouts(cache_dir, commit=commit)
    df = join_shootout_winners(normalized, shootouts)
    store.write(
        "results",
        df,
        policy=Policy.POINT_IN_TIME,
        keys=["match_id"],
        source="martj42",
        source_version=commit,
    )
