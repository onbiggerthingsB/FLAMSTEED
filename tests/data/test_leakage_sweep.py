"""End-to-end leakage sweep — the Phase-1 capstone (north-star §2: "treat
too-good as a bug").

These four tests are the operational form of the leakage-safety invariant that
the whole data layer is built around. The headline is the **future-result
canary** (:func:`test_future_result_change_does_not_leak_into_earlier_cutoff`):
mutating a match that sits AFTER a cutoff must NOT change a single feature value
built at that earlier cutoff. If it does, ``build`` is peeking at the future and
that is a genuine leak — the test must NOT be weakened.

The other three assert the supporting guarantees: more history can only ADD
matches (monotonicity), no built row is dated on/after its cutoff (the strict
``date < cutoff`` filter), and the Elo feature is the PRE-match rating only
(``rating_post`` must never reach the panel).
"""
import pandas as pd

from wcmodel.data.features import build


def test_match_count_monotonic_in_cutoff(small_store):
    early = build(cutoff="2023-01-01", store=small_store)
    late = build(cutoff="2025-06-01", store=small_store)
    assert len(late) >= len(early)


def test_no_row_dated_on_or_after_cutoff(small_store):
    for c in ["2022-01-01", "2024-01-01", "2025-06-01"]:
        df = build(cutoff=c, store=small_store)
        assert (pd.to_datetime(df["date"]) < pd.Timestamp(c)).all()


def test_elo_feature_is_pre_match_never_post(small_store):
    df = build(cutoff="2025-06-01", store=small_store)
    # elo_pre must be the pre-match rating; assert it is present and finite.
    assert "elo_pre" in df.columns and df["elo_pre"].notna().all()
    assert "rating_post" not in df.columns  # post-match rating must NOT be a feature


def test_future_result_change_does_not_leak_into_earlier_cutoff(mutable_store):
    f_before = build(cutoff="2024-06-01", store=mutable_store)
    mutable_store.mutate_future_result(after="2024-06-01")  # change a match AFTER the cutoff
    f_after = build(cutoff="2024-06-01", store=mutable_store)
    pd.testing.assert_frame_equal(
        f_before.reset_index(drop=True), f_after.reset_index(drop=True))
