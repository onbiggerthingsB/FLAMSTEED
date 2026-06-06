import pandas as pd
import pytest
from wcmodel.data.store import BitemporalStore, Policy


def _df(rows):
    return pd.DataFrame(rows)


def test_point_in_time_never_returns_future_observations(tmp_path):
    store = BitemporalStore(root=tmp_path)
    store.write("elo", _df([
        {"team": "BRA", "valid_as_of": "2025-01-01", "observed_at": "2025-01-01", "rating": 2000.0},
        {"team": "BRA", "valid_as_of": "2025-06-01", "observed_at": "2025-06-01", "rating": 2050.0},
    ]), policy=Policy.POINT_IN_TIME, keys=["team"])
    out = store.read("elo", cutoff="2025-03-01")
    assert list(out["rating"]) == [2000.0]
    assert (out["observed_at"] <= pd.Timestamp("2025-03-01")).all()


def test_point_in_time_returns_latest_observation_at_or_before_cutoff(tmp_path):
    store = BitemporalStore(root=tmp_path)
    store.write("elo", _df([
        {"team": "BRA", "valid_as_of": "2025-01-01", "observed_at": "2025-01-01", "rating": 2000.0},
        {"team": "BRA", "valid_as_of": "2025-06-01", "observed_at": "2025-06-01", "rating": 2050.0},
    ]), policy=Policy.POINT_IN_TIME, keys=["team"])
    out = store.read("elo", cutoff="2025-07-01")
    assert list(out["rating"]) == [2050.0]


def test_current_only_serves_snapshot_but_flags_contaminated(tmp_path):
    store = BitemporalStore(root=tmp_path)
    store.write("mktval", _df([
        {"team": "BRA", "valid_as_of": "2026-06-01", "observed_at": "2026-06-01", "value_eur": 1.2e9},
    ]), policy=Policy.CURRENT_ONLY, keys=["team"])
    out = store.read("mktval", cutoff="2025-03-01")
    assert list(out["value_eur"]) == [1.2e9]
    assert out["revision_contaminated"].all()


def test_point_in_time_does_not_set_contamination_flag(tmp_path):
    store = BitemporalStore(root=tmp_path)
    store.write("elo", _df([
        {"team": "BRA", "valid_as_of": "2025-01-01", "observed_at": "2025-01-01", "rating": 2000.0},
    ]), policy=Policy.POINT_IN_TIME, keys=["team"])
    out = store.read("elo", cutoff="2025-07-01")
    assert not out["revision_contaminated"].any()


def test_exact_tie_resolves_to_latest_ingested_deterministically(tmp_path):
    """MIGRATION-RISK GUARD (Phase-5 T7, Codex finding). Re-running an ingest over a
    pre-D3 store appends a same-(match_id) row with the SAME ``observed_at`` AND
    ``valid_as_of`` as the original, now carrying ``winner_override``. The read
    tie-break orders only by ``(observed_at DESC, valid_as_of DESC)``, so on an EXACT
    tie the winner was nondeterministic (DuckDB scan order) — an old no-override row
    could shadow the new one. The store must resolve an exact tie to the LATEST-ingested
    row DETERMINISTICALLY (repeatable across reads). RED before the tertiary tie-break."""
    store = BitemporalStore(root=tmp_path)
    same = {"valid_as_of": "2026-06-28", "observed_at": "2026-06-28"}
    # Original pre-D3 row: NO winner_override (the column did not yet exist conceptually).
    store.write("results", _df([
        {"match_id": "k1", **same, "winner_override": None},
    ]), policy=Policy.POINT_IN_TIME, keys=["match_id"])
    # Re-pull appends the SAME key/time row, now carrying the recorded shootout winner.
    store.write("results", _df([
        {"match_id": "k1", **same, "winner_override": "Brazil"},
    ]), policy=Policy.POINT_IN_TIME, keys=["match_id"])

    # Latest-ingested-wins must hold, and hold IDENTICALLY across repeated reads.
    seen = set()
    for _ in range(8):
        out = store.read("results", cutoff="2026-07-01")
        assert len(out) == 1
        seen.add(out["winner_override"].iloc[0])
    assert seen == {"Brazil"}, (
        f"exact-tie read is nondeterministic / shadows the new row: saw {seen} "
        "(expected the later-ingested winner_override='Brazil' every time)"
    )


def _write_pre_d3_parquet(store, name, rows, *, policy, keys):
    """Write a GENUINELY-OLD (pre-D3) parquet DIRECTLY to the store's parquet path,
    bypassing ``store.write()``. Carries exactly the bookkeeping columns the OLD
    ``write()`` produced — ``_policy``/``_keys``/``source``/``source_version`` and
    tz-naive ``valid_as_of``/``observed_at`` — but deliberately NO ``_ingest_seq``
    (that column did not exist before the D3 tie-break fix). This is the only faithful
    way to exercise the old-store read path: routing through the new ``store.write()``
    would always add ``_ingest_seq`` and so could never reproduce the regression."""
    df = pd.DataFrame(rows)
    for c in ("valid_as_of", "observed_at"):
        df[c] = pd.to_datetime(df[c])  # tz-naive, exactly as the old writer stored them
    df["_policy"] = policy.value
    df["_keys"] = ",".join(keys)
    df["source"] = name
    df["source_version"] = None
    assert "_ingest_seq" not in df.columns
    df.to_parquet(store._path(name), index=False)
    # Sanity: the on-disk file truly has no _ingest_seq (the pre-D3 shape).
    assert "_ingest_seq" not in pd.read_parquet(store._path(name)).columns


def test_read_on_pre_d3_parquet_without_ingest_seq_succeeds(tmp_path):
    """BACKWARD-COMPAT GUARD (Phase-5, Codex finding). The D3 tie-break fix made
    ``read()`` unconditionally ``ORDER BY ... _ingest_seq DESC`` + ``SELECT * EXCLUDE
    (rn, _ingest_seq)``. On an EXISTING pre-D3 parquet (Phases 1-4 on-disk stores) that
    has NO ``_ingest_seq`` column, that raised a DuckDB Binder Error 'Referenced column
    "_ingest_seq" not found' — breaking reads on real existing data. ``write()`` already
    back-filled ``_ingest_seq`` for a prior frame lacking it; ``read()`` must do the same
    in-memory. RED before the fix (Binder Error); GREEN after, returning the correct
    latest-by-(observed_at, valid_as_of) row per key."""
    store = BitemporalStore(root=tmp_path)
    _write_pre_d3_parquet(store, "elo", [
        {"team": "BRA", "valid_as_of": "2025-01-01", "observed_at": "2025-01-01", "rating": 2000.0},
        {"team": "BRA", "valid_as_of": "2025-06-01", "observed_at": "2025-06-01", "rating": 2050.0},
        {"team": "ARG", "valid_as_of": "2025-02-01", "observed_at": "2025-02-01", "rating": 1990.0},
    ], policy=Policy.POINT_IN_TIME, keys=["team"])

    out = store.read("elo", cutoff="2025-07-01")
    got = dict(zip(out["team"], out["rating"]))
    assert got == {"BRA": 2050.0, "ARG": 1990.0}

    # Cutoff still bites on the old store: only observations at/before cutoff are returned.
    out_early = store.read("elo", cutoff="2025-03-01")
    got_early = dict(zip(out_early["team"], out_early["rating"]))
    assert got_early == {"BRA": 2000.0, "ARG": 1990.0}


def test_read_on_pre_d3_parquet_returns_no_bookkeeping_columns(tmp_path):
    """Output-shape parity: a read of an old (pre-D3) parquet must return the SAME column
    set as a read of a normally-written store — no ``_ingest_seq`` (the in-memory back-fill
    is EXCLUDEd), and no ``rn``/``_policy``/``_keys`` leaking through."""
    store = BitemporalStore(root=tmp_path)
    _write_pre_d3_parquet(store, "elo", [
        {"team": "BRA", "valid_as_of": "2025-01-01", "observed_at": "2025-01-01", "rating": 2000.0},
    ], policy=Policy.POINT_IN_TIME, keys=["team"])
    old_out = store.read("elo", cutoff="2025-07-01")

    # Reference: a normally-written store with the same logical columns.
    ref = BitemporalStore(root=tmp_path / "ref")
    ref.write("elo", _df([
        {"team": "BRA", "valid_as_of": "2025-01-01", "observed_at": "2025-01-01", "rating": 2000.0},
    ]), policy=Policy.POINT_IN_TIME, keys=["team"])
    ref_out = ref.read("elo", cutoff="2025-07-01")

    assert set(old_out.columns) == set(ref_out.columns)
    for leaked in ("_ingest_seq", "rn", "_policy", "_keys"):
        assert leaked not in old_out.columns


def test_read_on_pre_d3_parquet_resolves_exact_tie_deterministically(tmp_path):
    """The in-memory back-fill assigns ascending ``_ingest_seq`` by file-row order, so even
    on an OLD store an exact (same key, same ``observed_at`` AND ``valid_as_of``) tie now
    resolves deterministically to the LATER file row, identically across repeated reads."""
    store = BitemporalStore(root=tmp_path)
    same = {"valid_as_of": "2026-06-28", "observed_at": "2026-06-28"}
    _write_pre_d3_parquet(store, "results", [
        {"match_id": "k1", **same, "winner_override": None},      # earlier file row
        {"match_id": "k1", **same, "winner_override": "Brazil"},  # later file row → must win
    ], policy=Policy.POINT_IN_TIME, keys=["match_id"])

    seen = set()
    for _ in range(8):
        out = store.read("results", cutoff="2026-07-01")
        assert len(out) == 1
        seen.add(out["winner_override"].iloc[0])
    assert seen == {"Brazil"}, (
        f"old-store exact-tie read is nondeterministic: saw {seen} "
        "(expected the later file row winner_override='Brazil' every time)"
    )
