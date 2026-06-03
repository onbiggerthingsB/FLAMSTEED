from __future__ import annotations
from enum import Enum
from pathlib import Path
import duckdb
import pandas as pd


class Policy(str, Enum):
    POINT_IN_TIME = "point_in_time"
    CURRENT_ONLY = "current_only"


_TIME_COLS = ("valid_as_of", "observed_at")


class BitemporalStore:
    """Append-only bitemporal store. read(cutoff) is leakage-safe for
    point_in_time sources by construction (north-star §4.2)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / f"{name}.parquet"

    def write(self, name: str, df: pd.DataFrame, *, policy: Policy, keys: list[str],
              source: str | None = None, source_version: str | None = None) -> None:
        df = df.copy()
        for c in _TIME_COLS:
            df[c] = pd.to_datetime(df[c])
        df["_policy"] = policy.value
        df["_keys"] = ",".join(keys)
        df["source"] = source or name
        df["source_version"] = source_version
        path = self._path(name)
        if path.exists():
            df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
        df.to_parquet(path, index=False)

    def read(self, name: str, *, cutoff: str | pd.Timestamp) -> pd.DataFrame:
        cutoff = pd.Timestamp(cutoff)
        raw = pd.read_parquet(self._path(name))
        policy = Policy(raw["_policy"].iloc[0])
        keys = raw["_keys"].iloc[0].split(",")
        con = duckdb.connect()
        con.register("t", raw)
        key_list = ", ".join(keys)
        if policy is Policy.POINT_IN_TIME:
            q = f"""
              SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (
                  PARTITION BY {key_list} ORDER BY observed_at DESC, valid_as_of DESC) rn
                FROM t
                WHERE observed_at <= TIMESTAMP '{cutoff}' AND valid_as_of <= TIMESTAMP '{cutoff}'
              ) WHERE rn = 1
            """
            out = con.execute(q).df()
            out["revision_contaminated"] = False
        else:
            q = f"""
              SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (
                  PARTITION BY {key_list} ORDER BY observed_at DESC) rn FROM t
              ) WHERE rn = 1
            """
            out = con.execute(q).df()
            out["revision_contaminated"] = True
        con.close()
        return out.drop(columns=["_policy", "_keys"])
