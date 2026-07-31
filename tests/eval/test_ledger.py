from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from wcmodel.data.sources.odds import admissible_quote
from wcmodel.eval import ledger as ledger_mod
from wcmodel.eval.ledger import (
    LEDGER_DTYPES, LedgerWriter, load_ledger, lock_path)

UTC = timezone.utc

SRC = Path(__file__).resolve().parents[2] / "src"


def _row(**over):
    # The default fixture is itself a UTC-rollover case (19:00 UTC-6 on local
    # matchday 2026-06-12 kicks off 2026-06-13T01:00Z): date is the
    # venue-LOCAL matchday, and every test that uses the default row rides on
    # that convention being the accepted one.
    row = {
        "fixture_id": "wc2026-0001",
        "pool": "wc2026",
        "date": "2026-06-12",
        "home": "Mexico",
        "away": "Poland",
        "kickoff_utc": datetime(2026, 6, 13, 1, 0, tzinfo=UTC),
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
    assert str(df["kickoff_utc"].dt.tz) == "UTC"
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
    w.flush()


def test_duplicate_arm_fixture_rejected_same_writer(tmp_path):
    w = LedgerWriter(tmp_path / "ledger.parquet")
    w.append(_row())
    with pytest.raises(ValueError, match="duplicate"):
        w.append(_row(p_home=0.6, p_draw=0.2, p_away=0.2))
    # a DIFFERENT arm on the same fixture is the normal case, not a duplicate
    w.append(_row(arm="elo_ordlogit"))
    w.flush()


def test_duplicate_arm_fixture_rejected_across_writers(tmp_path):
    """Every arm appends to ONE ledger over many sessions; a second run that
    re-issues a fixture must not silently double-weight it in the contrast —
    and the later session's flush must PRESERVE the earlier one's rows rather
    than rewriting the shared ledger down to what this process happens to
    hold."""
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
    w2 = LedgerWriter(path)
    with pytest.raises(ValueError, match="duplicate"):
        w2.append(_row())
    w2.append(_row(arm="elo_ordlogit", p_home=0.4, p_draw=0.3, p_away=0.3))
    w2.flush()

    df = load_ledger(path).set_index("arm")
    assert sorted(df.index) == ["elo_ordlogit", "incumbent"]
    assert df.loc["incumbent", "p_home"] == 0.5
    assert df.loc["incumbent", "issued_git"] == "deadbee"
    assert df.loc["elo_ordlogit", "p_home"] == 0.4


def test_a_flush_does_not_erase_rows_another_open_writer_flushed(tmp_path):
    """The multi-arm / multi-session case this module exists for: two writers
    open on the same ledger. Whoever flushes second must not silently drop the
    first one's rows — a vanished (arm, fixture) shrinks the paired contrast
    asymmetrically with no error to notice (OA F9)."""
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row(odds_snapshot_hash=None))
    a, b = LedgerWriter(path), LedgerWriter(path)
    a.append(_row(arm="eprime", p_home=0.45, p_draw=0.3, p_away=0.25))
    b.append(_row(arm="elo_ordlogit", p_home=0.4, p_draw=0.3, p_away=0.3))
    a.flush()
    b.flush()

    df = load_ledger(path)
    assert dict(df.dtypes.astype(str)) == dict(LEDGER_DTYPES)
    df = df.set_index("arm")
    assert sorted(df.index) == ["elo_ordlogit", "eprime", "incumbent"]
    assert df.loc["eprime", "p_home"] == 0.45
    # a re-read row survives the merge unchanged, nullable hash included
    assert pd.isna(df.loc["incumbent", "odds_snapshot_hash"])
    assert df.loc["incumbent", "t_issue"] == pd.Timestamp("2026-06-12 09:00", tz="UTC")


def _flush_at_the_same_instant(writers, monkeypatch) -> list[str]:
    """Flush every writer with all of them inside one another's
    read -> replace window, and return one message per failed flush.

    The injected delay widens that window, it does not create it: re-reading
    on flush only protects a writer that STARTED after the other finished.
    Messages, not exception objects — a stored traceback keeps a losing
    writer (and its stranded buffer) alive in a cycle until an arbitrary
    later gc pass, surfacing its warning under whatever test ran then.
    """
    real_write_atomic = ledger_mod._write_atomic

    def slow_write_atomic(df, dest):
        time.sleep(0.25)
        real_write_atomic(df, dest)

    monkeypatch.setattr(ledger_mod, "_write_atomic", slow_write_atomic)
    errors: list[str] = []

    def _flush(writer):
        try:
            writer.flush()
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=_flush, args=(w,)) for w in writers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(t.is_alive() for t in threads), "flush deadlocked"
    return errors


def test_simultaneous_flushes_serialize_instead_of_clobbering(tmp_path, monkeypatch):
    """The same invariant when the flushes OVERLAP rather than follow one
    another: two writers inside the read->replace window both read the same
    table, and the later ``os.replace`` deletes the earlier arm's rows."""
    path = tmp_path / "ledger.parquet"
    a, b = LedgerWriter(path), LedgerWriter(path)
    a.append(_row(arm="eprime", p_home=0.45, p_draw=0.3, p_away=0.25))
    b.append(_row(arm="incumbent"))

    assert _flush_at_the_same_instant((a, b), monkeypatch) == []
    assert sorted(load_ledger(path)["arm"]) == ["eprime", "incumbent"]


# The losing flush strands its buffer, which is the warned-about behaviour
# pinned by test_unflushed_rows_warn_at_interpreter_exit.
@pytest.mark.filterwarnings(
    "ignore::wcmodel.eval.ledger.UnflushedLedgerWarning")
def test_simultaneous_flushes_of_one_pair_raise_not_overwrite(tmp_path, monkeypatch):
    """The same-arm half: re-issuing a fixture must stay a loud duplicate even
    when the two flushes overlap. Exactly one row lands and exactly one caller
    is told — silently keeping the later forecast would double-count a fixture
    the analysis believes was issued once."""
    path = tmp_path / "ledger.parquet"
    a, b = LedgerWriter(path), LedgerWriter(path)
    a.append(_row(arm="eprime", p_home=0.45, p_draw=0.3, p_away=0.25))
    b.append(_row(arm="eprime", p_home=0.1, p_draw=0.1, p_away=0.8))

    errors = _flush_at_the_same_instant((a, b), monkeypatch)
    assert len(errors) == 1, errors
    assert "duplicate" in errors[0]
    # whichever writer won the lock, its row is intact and it is the only one
    assert load_ledger(path)["p_home"].tolist() in ([0.45], [0.1])


_RACE_SCRIPT = """
import datetime, pathlib, sys, time
from wcmodel.eval.ledger import LedgerWriter

path, arm = sys.argv[1], sys.argv[2]
barrier, n = pathlib.Path(sys.argv[3]), int(sys.argv[4])
stamp = datetime.datetime(2026, 6, 12, 9, 0, tzinfo=datetime.timezone.utc)
kick = datetime.datetime(2026, 6, 13, 1, 0, tzinfo=datetime.timezone.utc)
w = LedgerWriter(path)
for i in range(n):
    w.append(dict(
        fixture_id="wc2026-%04d" % i, pool="wc2026", date="2026-06-12",
        home="Mexico", away="Poland", kickoff_utc=kick,
        t_issue=stamp, training_cutoff=stamp,
        arm=arm, p_home=0.5, p_draw=0.25, p_away=0.25,
        issued_git="deadbee", odds_snapshot_hash=None))
(barrier / (arm + ".ready")).touch()
deadline = time.monotonic() + 60
while len(list(barrier.glob("*.ready"))) < 2:
    if time.monotonic() > deadline:
        raise SystemExit("barrier timeout")
    time.sleep(0.002)
w.flush()
print("flushed ok")
"""


def test_two_processes_flushing_at_once_keep_both_arms(tmp_path):
    """Plan 2's actual shape: one arm per process, one shared ledger, both
    matchday jobs firing off the same cron. Neither may exit 0 having quietly
    dropped the other's slate — an absent (arm, fixture) is indistinguishable
    from an arm that never issued (OA F9), so a clobbered flush shrinks the
    paired contrast with nothing to notice."""
    path = tmp_path / "ledger.parquet"
    barrier = tmp_path / "barrier"
    barrier.mkdir()
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _RACE_SCRIPT, str(path), arm, str(barrier), "60"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "PYTHONPATH": str(SRC)})
        for arm in ("eprime", "incumbent")]
    results = [proc.communicate(timeout=180) for proc in procs]
    for proc, (out, err) in zip(procs, results):
        assert proc.returncode == 0, err
        assert "flushed ok" in out, err

    counts = load_ledger(path)["arm"].value_counts().to_dict()
    assert counts == {"eprime": 60, "incumbent": 60}


def test_repeated_flushes_accumulate_rather_than_re_append(tmp_path):
    """An arm flushing per matchday: each flush adds only what was buffered
    since the last one, and a flush with nothing buffered is a no-op."""
    path = tmp_path / "ledger.parquet"
    w = LedgerWriter(path)
    w.append(_row())
    w.flush()
    w.append(_row(arm="eprime", p_home=0.45, p_draw=0.3, p_away=0.25))
    w.flush()
    w.flush()
    assert load_ledger(path)["arm"].tolist() == ["incumbent", "eprime"]


# The rejected flush deliberately strands b's buffer — that warning IS the
# behaviour pinned by test_unflushed_rows_warn_at_interpreter_exit.
@pytest.mark.filterwarnings(
    "ignore::wcmodel.eval.ledger.UnflushedLedgerWarning")
def test_flush_rejects_a_pair_another_writer_wrote_after_this_one_opened(tmp_path):
    """Duplicate detection must see rows that landed AFTER construction —
    otherwise the second flush would overwrite, not double-count, and the
    losing forecast would disappear without a word."""
    path = tmp_path / "ledger.parquet"
    a, b = LedgerWriter(path), LedgerWriter(path)
    a.append(_row(arm="eprime", p_home=0.45, p_draw=0.3, p_away=0.25))
    b.append(_row(arm="eprime", p_home=0.1, p_draw=0.1, p_away=0.8))
    a.flush()
    with pytest.raises(ValueError, match="duplicate"):
        b.flush()
    assert load_ledger(path)["p_home"].tolist() == [0.45]


def test_training_cutoff_after_t_issue_rejected(tmp_path):
    """The information-set rule (spec F2): a fit may not see the future."""
    w = LedgerWriter(tmp_path / "ledger.parquet")
    with pytest.raises(ValueError, match="training_cutoff"):
        w.append(_row(training_cutoff=datetime(2026, 6, 12, 9, 0, 1, tzinfo=UTC)))
    # equal is the default and must pass; earlier is fine too
    w.append(_row())
    w.append(_row(arm="elo_ordlogit",
                  training_cutoff=datetime(2026, 6, 11, 9, 0, tzinfo=UTC)))
    w.flush()


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


def test_wc2026_rollover_fixture_pins_local_matchday_not_utc_date(tmp_path):
    """The ledger date is the venue-LOCAL matchday of kickoff, NOT the UTC
    calendar date of the kickoff instant — and the two differ on 36 of the 104
    WC-2026 fixtures (evening Americas kickoffs roll past midnight UTC).

    Concrete case (config/tournament_2026.yaml): South Korea v Czech Republic,
    local 2026-06-11 20:00 UTC-6 = kickoff 2026-06-12T02:00Z. Local-matchday
    row: t_issue 2026-06-11T09:00Z, 17 h pre-kickoff — accepted. The UTC-date
    misjoin (the natural-looking join key, since The Odds API reports
    commence_time in UTC) lands t_issue at 2026-06-12T09:00Z — 7 h AFTER
    kickoff — with an odds cut of 08:30Z that is post-kickoff too, so
    admissible_quote alone happily admits an in-play price against it. Only
    the ledger's kickoff invariant can refuse that row."""
    kickoff = datetime(2026, 6, 12, 2, 0, tzinfo=UTC)
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row(
            fixture_id="wc2026-a1", date="2026-06-11",
            home="South Korea", away="Czech Republic", kickoff_utc=kickoff,
            t_issue=datetime(2026, 6, 11, 9, 0, tzinfo=UTC),
            training_cutoff=datetime(2026, 6, 11, 9, 0, tzinfo=UTC)))
    assert load_ledger(path)["kickoff_utc"][0] == pd.Timestamp(
        "2026-06-12 02:00", tz="UTC")

    misjoined_t_issue = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
    in_play = misjoined_t_issue - timedelta(minutes=31)  # 08:29Z, 6.5 h in-match
    assert in_play > kickoff
    assert admissible_quote(in_play, in_play, misjoined_t_issue) is True
    w2 = LedgerWriter(path)
    with pytest.raises(ValueError, match="strictly before kickoff_utc"):
        w2.append(_row(
            fixture_id="wc2026-a1", arm="eprime", date="2026-06-12",
            home="South Korea", away="Czech Republic", kickoff_utc=kickoff,
            t_issue=misjoined_t_issue, training_cutoff=misjoined_t_issue))


def test_t_issue_at_or_after_kickoff_rejected(tmp_path):
    """The pre-kickoff invariant is STRICT: issuing AT kickoff already scores
    an in-play information set (OA F2)."""
    w = LedgerWriter(tmp_path / "ledger.parquet")
    with pytest.raises(ValueError, match="strictly before kickoff_utc"):
        w.append(_row(kickoff_utc=datetime(2026, 6, 12, 9, 0, tzinfo=UTC)))
    # the boundary: any kickoff strictly after t_issue is admissible
    w.append(_row(kickoff_utc=datetime(2026, 6, 12, 9, 0, 1, tzinfo=UTC)))
    w.flush()


def test_kickoff_must_be_tz_aware_and_non_null(tmp_path):
    w = LedgerWriter(tmp_path / "ledger.parquet")
    with pytest.raises(ValueError, match="tz-aware"):
        w.append(_row(kickoff_utc=datetime(2026, 6, 13, 1, 0)))
    with pytest.raises(ValueError, match="must not be null"):
        w.append(_row(kickoff_utc=None))


def test_load_ledger_rejects_a_post_kickoff_t_issue(tmp_path):
    """The load-path twin: a foreign writer that joined on the UTC date wrote
    a post-kickoff t_issue; re-validation must refuse the file."""
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
    df = load_ledger(path)
    # default row's kickoff 2026-06-13T01:00Z pulled to 02:00Z on the 12th —
    # now 7 h before the stored t_issue 09:00Z, the misjoin's exact shape
    df["kickoff_utc"] = df["kickoff_utc"] - pd.Timedelta(hours=23)
    df.to_parquet(path, engine="pyarrow", index=False)
    with pytest.raises(ValueError, match="strictly before kickoff_utc"):
        load_ledger(path)


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


@pytest.mark.parametrize("mangle", ["string", "naive"])
@pytest.mark.parametrize("col", ["t_issue", "training_cutoff", "kickoff_utc"])
def test_load_ledger_rejects_stamp_columns_that_are_not_tz_aware(tmp_path, col, mangle):
    """The load-path twin of ``test_naive_timestamps_rejected``. A foreign
    writer in, say, Europe/Paris emitting naive wall-clock stamps must fail
    here too: coercing the column to UTC first would READ '09:00:00' as 09:00
    UTC, landing an instant two hours off its true value that then passes
    every remaining check, including the exact-09:00 rule (spec F2)."""
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
    df = load_ledger(path)
    naive = df[col].dt.tz_localize(None)
    df[col] = naive.astype(str) if mangle == "string" else naive
    df.to_parquet(path, engine="pyarrow", index=False)

    with pytest.raises(ValueError, match="tz-aware"):
        load_ledger(path)


def test_load_ledger_accepts_a_stamp_column_in_an_equivalent_offset(tmp_path):
    """Symmetric with the write path: another OFFSET is the same instant and
    stays admissible — only an unanchored stamp is rejected."""
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
    df = load_ledger(path)
    df["t_issue"] = df["t_issue"].dt.tz_convert("Europe/Paris")
    df.to_parquet(path, engine="pyarrow", index=False)

    assert load_ledger(path)["t_issue"][0] == pd.Timestamp("2026-06-12 09:00", tz="UTC")


def test_load_ledger_rejects_missing_columns(tmp_path):
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())
    load_ledger(path).drop(columns=["issued_git"]).to_parquet(
        path, engine="pyarrow", index=False)
    with pytest.raises(ValueError, match="issued_git"):
        load_ledger(path)


def test_a_rejected_append_leaves_the_buffer_unchanged(tmp_path):
    """A rejected append contributes nothing to the eventual flush."""
    path = tmp_path / "ledger.parquet"
    w = LedgerWriter(path)
    w.append(_row())
    with pytest.raises(ValueError):
        w.append(_row(arm="bad", p_home=0.9, p_draw=0.9, p_away=0.9))
    w.flush()
    assert load_ledger(path)["arm"].tolist() == ["incumbent"]


@pytest.mark.filterwarnings(  # the torn flush strands w2's buffer, as designed
    "ignore::wcmodel.eval.ledger.UnflushedLedgerWarning")
def test_a_torn_flush_leaves_the_previous_sessions_rows_intact(tmp_path, monkeypatch):
    """flush rewrites the WHOLE accumulated table, so an in-place write that
    dies mid-parquet would destroy every prior session's forecasts, not just
    this one's. Same temp+rename contract as features._cached_panel and
    odds._persist_raw."""
    path = tmp_path / "ledger.parquet"
    with LedgerWriter(path) as w:
        w.append(_row())

    def _die_mid_write(self, dest, *args, **kwargs):
        Path(dest).write_bytes(b"PAR1-torn")
        raise OSError("no space left on device")

    w2 = LedgerWriter(path)
    w2.append(_row(arm="eprime", p_home=0.45, p_draw=0.3, p_away=0.25))
    monkeypatch.setattr(pd.DataFrame, "to_parquet", _die_mid_write)
    with pytest.raises(OSError):
        w2.flush()
    monkeypatch.undo()

    assert load_ledger(path)["arm"].tolist() == ["incumbent"]
    # the half-written tmp file is gone; the flush lock's sidecar is the only
    # other thing a ledger directory ever holds (it outlives the flush by
    # design — see lock_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        path.name, lock_path(path).name]


_EXIT_SCRIPT = """
import datetime
from wcmodel.eval.ledger import LedgerWriter
w = LedgerWriter({path!r})
w.append(dict(
    fixture_id="wc2026-0001", pool="wc2026", date="2026-06-12",
    home="Mexico", away="Poland",
    kickoff_utc=datetime.datetime(2026, 6, 13, 1, 0, tzinfo=datetime.timezone.utc),
    t_issue=datetime.datetime(2026, 6, 12, 9, 0, tzinfo=datetime.timezone.utc),
    training_cutoff=datetime.datetime(2026, 6, 12, 9, 0, tzinfo=datetime.timezone.utc),
    arm="incumbent", p_home=0.5, p_draw=0.25, p_away=0.25,
    issued_git="deadbee", odds_snapshot_hash=None))
{tail}
"""


@pytest.mark.parametrize("tail,warned", [("", True), ("w.flush()", False)])
def test_unflushed_rows_warn_at_interpreter_exit(tmp_path, tail, warned):
    """Rows only reach disk on flush, and an arm that dies mid-run must not
    look like an arm that simply never ran: in the contrast an absent
    (arm, fixture) is indistinguishable from a missing forecast (OA F9)."""
    path = tmp_path / "ledger.parquet"
    proc = subprocess.run(
        [sys.executable, "-c", _EXIT_SCRIPT.format(path=str(path), tail=tail)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(SRC)})
    assert proc.returncode == 0, proc.stderr
    assert ("never flushed" in proc.stderr) is warned, proc.stderr
    assert path.exists() is not warned
