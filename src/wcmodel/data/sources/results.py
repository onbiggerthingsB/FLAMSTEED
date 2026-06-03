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
import pandas as pd

from wcmodel.data.cache import cached_pull
from wcmodel.data.store import BitemporalStore, Policy

# Pinned to a specific commit (never `master`) so a re-pull is reproducible.
MARTJ42_COMMIT = "dad6874bb720e23cccdf696f057aa64fa5471445"
MARTJ42_RAW_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    f"{MARTJ42_COMMIT}/results.csv"
)

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
    (ordered by score, content-stable) to the hash input only where it repeats.
    This guarantees `match_id.is_unique` while leaving every non-colliding row's
    id identical to the bare formula.
    """
    df = raw.copy()
    # Hash on the original (string) date so the id is stable regardless of how
    # the parsed timestamp later renders.
    base = (df["date"].astype(str) + "|" + df["home_team"].astype(str) + "|"
            + df["away_team"].astype(str) + "|" + df["city"].astype(str))
    # Deterministic, input-order-independent disambiguation for collisions:
    # rank tied rows by their result so the same CSV always maps a given match
    # to the same suffix. Non-colliding rows (the vast majority) get occ == 0.
    order = df.sort_values(["home_score", "away_score"], kind="mergesort").index
    occ = pd.Series(0, index=df.index)
    occ.loc[order] = df.loc[order].groupby(base.loc[order], sort=False).cumcount()
    keyed = base.where(occ == 0, base + "|" + occ.astype(str))
    df["match_id"] = keyed.map(_sha1)
    df["date"] = pd.to_datetime(df["date"])
    df["valid_as_of"] = df["date"]
    df["observed_at"] = df["date"]
    return df[["match_id", "date", "valid_as_of", "observed_at", *_CARRY]]


def fetch_results(cache_dir: str | Path) -> pd.DataFrame:
    """Pull the real martj42 CSV (network). Cached by content key + commit."""
    def _fetch() -> pd.DataFrame:
        resp = httpx.get(MARTJ42_RAW_URL, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        from io import StringIO
        return pd.read_csv(StringIO(resp.text))

    return cached_pull(
        "martj42_results",
        {"commit": MARTJ42_COMMIT},
        _fetch,
        cache_dir=cache_dir,
    )


def load_results(store: BitemporalStore, cache_dir: str | Path) -> None:
    """Fetch -> normalize -> write to the bitemporal store."""
    df = normalize_results(fetch_results(cache_dir))
    store.write(
        "results",
        df,
        policy=Policy.POINT_IN_TIME,
        keys=["match_id"],
        source="martj42",
        source_version=MARTJ42_COMMIT,
    )
