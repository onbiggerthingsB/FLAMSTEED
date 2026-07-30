from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from wcmodel.data.sources.odds import admissible_quote
from wcmodel.eval.ledger import LEDGER_DTYPES, LedgerWriter, load_ledger

UTC = timezone.utc


def _row(**over):
    row = {
        "fixture_id": "wc2026-0001",
        "pool": "wc2026",
        "date": "2026-06-12",
        "home": "Mexico",
        "away": "Poland",
        "t_issue": datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
        "training_cutoff": datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
        "arm": "incumbent",
        "p_home": 0.5,
        "p_draw": 0.25,
        "p_away": 0.25,
        "issued_git": "deadbee",
        "odds_snapshot_hash": "a" * 64,
    }
    row.update(over)
    return row


def test_round_trip_preserves_dtypes_tz_and_nullable_hash(tmp_path):
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
        w.append(_row(arm="elo_ordlogit", odds_snapshot_hash=None,
                      p_home=0.4, p_draw=0.3, p_away=0.3))
    df = load_ledger(path)

    assert dict(df.dtypes.astype(str)) == dict(LEDGER_DTYPES)
    assert list(df.columns) == list(LEDGER_DTYPES)
    # tz survives the parquet round-trip as UTC, not as a naive local stamp.
    assert str(df["t_issue"].dt.tz) == "UTC"
    assert str(df["training_cutoff"].dt.tz) == "UTC"
    assert df["t_issue"].tolist() == [pd.Timestamp("2026-06-12 09:00", tz="UTC")] * 2
    assert df["p_home"].tolist() == [0.5, 0.4]
    assert df["odds_snapshot_hash"].tolist()[0] == "a" * 64
    assert df["odds_snapshot_hash"].isna().tolist() == [False, True]


def test_stored_t_issue_drives_the_T3_admissibility_helper(tmp_path):
    """The ledger's t_issue is the SAME object T3's odds gate consumes — a
    naive or non-UTC stamp here would raise inside admissible_quote at the
    comparison, not at write time (spec F2)."""
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
    t_issue = load_ledger(path)["t_issue"][0].to_pydatetime()

    early = t_issue - timedelta(minutes=31)
    late = t_issue - timedelta(minutes=29)
    assert admissible_quote(early, early, t_issue) is True
    assert admissible_quote(late, late, t_issue) is False


@pytest.mark.parametrize("probs", [
    (0.5, 0.25, 0.24),          # sums to 0.99
    (0.5, 0.25, 0.26),          # sums to 1.01
    (0.5, 0.25, 0.25 + 1e-6),   # inside float noise but outside 1e-9
    (1.2, 0.25, -0.45),         # sums to 1.0 via a NEGATIVE leg
    (0.5, 0.25, float("nan")),
])
def test_probabilities_must_be_a_valid_distribution(tmp_path, probs):
    w = LedgerWriter(tmp_path / "ledger.parquet")
    with pytest.raises(ValueError):
        w.append(_row(p_home=probs[0], p_draw=probs[1], p_away=probs[2]))


def test_probability_sum_tolerance_is_1e_9(tmp_path):
    w = LedgerWriter(tmp_path / "ledger.parquet")
    w.append(_row(p_home=0.5 + 5e-10, p_draw=0.25, p_away=0.25))


def test_duplicate_arm_fixture_rejected_same_writer(tmp_path):
    w = LedgerWriter(tmp_path / "ledger.parquet")
    w.append(_row())
    with pytest.raises(ValueError, match="duplicate"):
        w.append(_row(p_home=0.6, p_draw=0.2, p_away=0.2))
    # a DIFFERENT arm on the same fixture is the normal case, not a duplicate
    w.append(_row(arm="elo_ordlogit"))


def test_duplicate_arm_fixture_rejected_across_writers(tmp_path):
    """Every arm appends to ONE ledger over many sessions; a second run that
    re-issues a fixture must not silently double-weight it in the contrast."""
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
    w2 = LedgerWriter(path)
    with pytest.raises(ValueError, match="duplicate"):
        w2.append(_row())


def test_training_cutoff_after_t_issue_rejected(tmp_path):
    """The information-set rule (spec F2): a fit may not see the future."""
    w = LedgerWriter(tmp_path / "ledger.parquet")
    with pytest.raises(ValueError, match="training_cutoff"):
        w.append(_row(training_cutoff=datetime(2026, 6, 12, 9, 0, 1, tzinfo=UTC)))
    # equal is the default and must pass; earlier is fine too
    w.append(_row())
    w.append(_row(arm="elo_ordlogit",
                  training_cutoff=datetime(2026, 6, 11, 9, 0, tzinfo=UTC)))


def test_naive_timestamps_rejected(tmp_path):
    w = LedgerWriter(tmp_path / "ledger.parquet")
    with pytest.raises(ValueError, match="tz-aware"):
        w.append(_row(t_issue=datetime(2026, 6, 12, 9, 0)))
    with pytest.raises(ValueError, match="tz-aware"):
        w.append(_row(training_cutoff=datetime(2026, 6, 12, 9, 0)))


@pytest.mark.parametrize("bad", [
    datetime(2026, 6, 12, 10, 0, tzinfo=UTC),      # wrong hour
    datetime(2026, 6, 12, 9, 30, tzinfo=UTC),      # wrong minute
    datetime(2026, 6, 12, 9, 0, 1, tzinfo=UTC),    # wrong second
    datetime(2026, 6, 11, 9, 0, tzinfo=UTC),       # right clock, wrong matchday
])
def test_t_issue_must_be_0900_utc_on_the_fixture_date(tmp_path, bad):
    """The prereg default IS the estimand: a drifted config must fail loudly
    rather than quietly re-define what is being measured (spec F2/F9)."""
    w = LedgerWriter(tmp_path / "ledger.parquet")
    with pytest.raises(ValueError, match="t_issue"):
        w.append(_row(t_issue=bad, training_cutoff=bad))


def test_t_issue_accepts_an_equivalent_offset_and_normalizes_to_utc(tmp_path):
    """Same INSTANT, different wall clock: 11:00+02:00 is 09:00 UTC."""
    path = tmp_path / "ledger.parquet"
    plus_two = timezone(timedelta(hours=2))
    with LedgerWriter(path) as w:
        w.append(_row(t_issue=datetime(2026, 6, 12, 11, 0, tzinfo=plus_two)))
    assert load_ledger(path)["t_issue"][0] == pd.Timestamp("2026-06-12 09:00", tz="UTC")


def test_date_accepts_date_objects_and_pads(tmp_path):
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row(date=date(2026, 6, 12)))
    assert load_ledger(path)["date"].tolist() == ["2026-06-12"]


def test_missing_and_unknown_keys_rejected(tmp_path):
    w = LedgerWriter(tmp_path / "ledger.parquet")
    partial = _row()
    partial.pop("issued_git")
    with pytest.raises(ValueError, match="issued_git"):
        w.append(partial)
    with pytest.raises(ValueError, match="unknown"):
        w.append(_row(p_over=0.5))


def test_null_identity_fields_rejected(tmp_path):
    w = LedgerWriter(tmp_path / "ledger.parquet")
    for col in ("fixture_id", "pool", "home", "away", "arm", "issued_git"):
        with pytest.raises(ValueError, match=col):
            w.append(_row(**{col: None}))


def test_load_ledger_revalidates_a_tampered_file(tmp_path):
    """The parquet is the shared artifact; a hand-edited or foreign-written
    file must not enter a contrast just because it parses."""
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
    df = load_ledger(path)
    df.loc[0, "p_away"] = 0.30
    df.to_parquet(path, engine="pyarrow", index=False)
    with pytest.raises(ValueError, match="sum"):
        load_ledger(path)


def test_load_ledger_rejects_missing_columns(tmp_path):
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
    load_ledger(path).drop(columns=["issued_git"]).to_parquet(
        path, engine="pyarrow", index=False)
    with pytest.raises(ValueError, match="issued_git"):
        load_ledger(path)


def test_flush_is_atomic_on_a_rejected_row(tmp_path):
    """A rejected append leaves neither the buffer nor the file changed."""
    path = tmp_path / "ledger.parquet"
    w = LedgerWriter(path)
    w.append(_row())
    with pytest.raises(ValueError):
        w.append(_row(arm="bad", p_home=0.9, p_draw=0.9, p_away=0.9))
    w.flush()
    assert load_ledger(path)["arm"].tolist() == ["incumbent"]
