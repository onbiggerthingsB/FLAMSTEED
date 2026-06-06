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
        prior = pd.read_parquet(path) if path.exists() else None
        # ``_ingest_seq`` — a monotonic, write-time INGEST-ORDER column. It exists ONLY to
        # give the read tie-break a STABLE tertiary key so "latest-ingested-wins" is
        # well-defined when two same-key rows carry IDENTICAL ``observed_at`` AND
        # ``valid_as_of`` (the pre-D3-store re-pull case: a same-(match_id) row re-appended
        # with the same timestamps, now carrying ``winner_override``). Without it the read's
        # ``row_number()`` tie-break fell back to DuckDB scan order, so the winner of an
        # exact tie was nondeterministic and an old no-override row could shadow the new one.
        # The sequence increases ACROSS writes (each write's rows start above every prior
        # ``_ingest_seq``), so a later ingest always sorts after an earlier one. A pre-D3
        # store has no ``_ingest_seq`` column; we back-fill the prior rows by their existing
        # row order (older = lower) before appending, so the column is total + monotonic.
        if prior is not None:
            if "_ingest_seq" in prior.columns:
                start = int(prior["_ingest_seq"].max()) + 1
            else:
                prior = prior.copy()
                prior["_ingest_seq"] = range(len(prior))
                start = len(prior)
        else:
            start = 0
        df["_ingest_seq"] = range(start, start + len(df))
        if prior is not None:
            df = pd.concat([prior, df], ignore_index=True)
        df.to_parquet(path, index=False)

    def read(self, name: str, *, cutoff: str | pd.Timestamp) -> pd.DataFrame:
        """Read a source table as-of ``cutoff``, applying its stored policy.

        The cutoff boundary is **exclusive of the future** but its strength
        depends on the table's write-time policy (north-star §4.2):

        - **POINT_IN_TIME** — the leakage-safe guarantee. Returns, per logical
          key, only the latest row with ``observed_at <= cutoff`` AND
          ``valid_as_of <= cutoff`` (look-ahead is impossible by construction),
          flagged ``revision_contaminated = False``.
        - **CURRENT_ONLY** — **deliberately ignores ``cutoff``** and returns the
          latest snapshot per key regardless of when it was observed (the spec
          §4.2 contaminated fallback: only the current revised state is
          obtainable). Every row is flagged ``revision_contaminated = True`` so
          Phase 4 can compute a per-bet contamination exposure. This is NOT a
          point-in-time read — ``observed_at > cutoff`` is expected. **No
          clean-core Phase-1 source uses CURRENT_ONLY** (it is reserved for the
          deferred optional sources: market values / rosters), so the practical
          leakage surface of this fallback is zero.
        """
        cutoff = pd.Timestamp(cutoff)
        # Normalize a tz-AWARE cutoff to tz-NAIVE UTC before it reaches the DuckDB
        # `TIMESTAMP '{cutoff}'` literal. The stored `observed_at`/`valid_as_of`
        # columns are tz-naive UTC (every writer collapses to naive UTC), so an
        # aware cutoff's string form (e.g. `2026-06-12 01:00:00+08:00`) would have
        # its offset SILENTLY DROPPED by `TIMESTAMP '...'` and parse as the wrong
        # naive wall-clock — a +08:00 cutoff just before a 21:00Z whistle would
        # read as next-day 01:00 naive and LEAK the future result. Coercing the
        # instant to UTC then dropping the tz makes the `observed_at <= cutoff`
        # boundary exact and tz-agnostic for EVERY caller (defense-in-depth; the
        # feature/sim callers already normalize, this hardens the store itself).
        # Additive: a naive cutoff passes through unchanged, and an aware-UTC `Z`
        # cutoff is unchanged in effect.
        if cutoff.tz is not None:
            cutoff = cutoff.tz_convert("UTC").tz_localize(None)
        raw = pd.read_parquet(self._path(name))
        policy = Policy(raw["_policy"].iloc[0])
        keys = raw["_keys"].iloc[0].split(",")
        con = duckdb.connect()
        con.register("t", raw)
        key_list = ", ".join(keys)
        # ``_ingest_seq DESC`` is the STABLE tertiary tie-break (latest-ingested-wins):
        # it ONLY decides the order when the prior keys are EQUAL, so it changes no
        # currently-deterministic read — it just makes a previously-undefined exact tie
        # (same key, same ``observed_at`` AND ``valid_as_of``) resolve to the row written
        # LAST. It is a write-time bookkeeping column, EXCLUDEd from the returned frame.
        if policy is Policy.POINT_IN_TIME:
            q = f"""
              SELECT * EXCLUDE (rn, _ingest_seq) FROM (
                SELECT *, row_number() OVER (
                  PARTITION BY {key_list}
                  ORDER BY observed_at DESC, valid_as_of DESC, _ingest_seq DESC) rn
                FROM t
                WHERE observed_at <= TIMESTAMP '{cutoff}' AND valid_as_of <= TIMESTAMP '{cutoff}'
              ) WHERE rn = 1
            """
            out = con.execute(q).df()
            out["revision_contaminated"] = False
        else:
            q = f"""
              SELECT * EXCLUDE (rn, _ingest_seq) FROM (
                SELECT *, row_number() OVER (
                  PARTITION BY {key_list}
                  ORDER BY observed_at DESC, _ingest_seq DESC) rn FROM t
              ) WHERE rn = 1
            """
            out = con.execute(q).df()
            out["revision_contaminated"] = True
        con.close()
        return out.drop(columns=["_policy", "_keys"])
