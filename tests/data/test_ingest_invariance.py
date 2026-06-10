"""Bitemporal-invariance canary for the results refresh (Phase 0, §1).

Refreshing the martj42 feed = bumping the pinned commit and re-ingesting. The
binding leakage rule is that NEW, post-cutoff rows (later friendlies arriving
between the old and new pin) must NOT change what an OLD-cutoff read sees: the
store's ``observed_at <= cutoff AND valid_as_of <= cutoff`` gate has to hide
them. This test LOCKS that gate data-independently (two writes against one
store, one frame-identical read), so a regression in the store's as-of read
trips here rather than silently contaminating a production snapshot.

This is the data-side companion to ``build_real_snapshot.verify_cutoff_gate``:
that re-asserts the gate operationally at build time; this asserts the gate's
contract directly.
"""
import pandas as pd
from wcmodel.data.store import BitemporalStore, Policy

CUT = "2026-06-02T00:00:00Z"


def _row(date, home, away, mid):
    """Minimal store-ready results row (the schema ``store.write`` requires for a
    POINT_IN_TIME results write keyed on ``match_id``: a key, the bitemporal time
    columns, and the carried result columns)."""
    return pd.DataFrame({
        "match_id": [mid],
        "date": [pd.Timestamp(date)],
        "valid_as_of": [pd.Timestamp(date)],
        "observed_at": [pd.Timestamp(date)],
        "home_team": [home],
        "away_team": [away],
        "home_score": [1],
        "away_score": [0],
        "neutral": [False],
        "tournament": ["Friendly"],
        "city": ["X"],
        "country": ["X"],
    })


def test_new_later_rows_do_not_change_old_cutoff_read(tmp_path):
    store = BitemporalStore(root=tmp_path / "s")
    base = _row("2026-05-30", "A", "B", "m1")
    store.write("results", base, policy=Policy.POINT_IN_TIME, keys=["match_id"])
    before = (store.read("results", cutoff=CUT)
              .sort_values("match_id").reset_index(drop=True))

    # Simulate the refresh: a post-cutoff friendly arrives (valid+observed AFTER
    # the cutoff). Re-ingest writes it through the canonical POINT_IN_TIME path.
    later = _row("2026-06-08", "C", "D", "m2")
    store.write("results", later, policy=Policy.POINT_IN_TIME, keys=["match_id"])
    after = (store.read("results", cutoff=CUT)
             .sort_values("match_id").reset_index(drop=True))

    # The gate hides the new row: the old-cutoff read is frame-identical.
    pd.testing.assert_frame_equal(before, after)

    # …but a later cutoff DOES see it (the row is present, just gated, not lost).
    full = store.read("results", cutoff="2026-06-09T00:00:00Z")
    assert len(full) == len(before) + 1
