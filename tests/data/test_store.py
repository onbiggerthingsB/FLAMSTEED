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
