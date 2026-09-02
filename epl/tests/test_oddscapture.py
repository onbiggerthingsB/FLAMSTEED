"""The Tuesday-and-Friday capture.

Every test here runs against an INJECTED fetcher and a `tmp_path` directory:
this suite never touches the network and never writes to the real snapshot
directory, so it is CI-safe on a machine that has neither.

The one test that reads the real directory is skip-guarded, and it asserts the
fact §0.3 rests on rather than a count that grows every week.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from epl import oddscapture as oc, paths

SNAPSHOT_DIR = oc.SNAPSHOT_DIR


def _csv(rows: int = 4, *, columns: tuple[str, ...] | None = None,
         div: str = "E0") -> bytes:
    cols = columns or ("Div", "Date", "HomeTeam", "AwayTeam",
                       "AvgH", "AvgD", "AvgA")
    head = ",".join(cols)
    body = []
    for i in range(rows):
        cells = []
        for c in cols:
            if c == "Div":
                cells.append(div if i % 2 == 0 else "E1")
            elif c == "Date":
                cells.append("29/08/2026")
            elif c in ("HomeTeam", "AwayTeam"):
                cells.append(f"{c.lower()}{i}")
            else:
                cells.append("2.10")
        body.append(",".join(cells))
    # padded to clear the MIN_BYTES floor the way a real feed's width does
    pad = "\n".join(body[-1] for _ in range(20))
    return ("\n".join([head, *body, pad]) + "\n").encode("utf-8")


def _fetcher(blob: bytes):
    return lambda url: blob


# --------------------------------------------------------------------------
# 1. the cadence
# --------------------------------------------------------------------------
def test_the_cadence_is_tuesday_and_friday_and_not_friday_alone():
    """Friday alone silently drops every midweek round: the source publishes
    one file for the week and overwrites it in place."""
    assert oc.CAPTURE_DAYS == (1, 4)
    assert oc.CAPTURE_DAY_NAMES == ("Tuesday", "Friday")
    assert oc.is_capture_day("2026-08-25") is True         # a Tuesday
    assert oc.is_capture_day("2026-08-28") is True         # a Friday
    for other in ("2026-08-24", "2026-08-26", "2026-08-27",
                  "2026-08-29", "2026-08-30"):
        assert oc.is_capture_day(other) is False, other


def test_the_next_capture_day_is_strictly_after_today():
    assert str(oc.next_capture_day("2026-08-25").date()) == "2026-08-28"
    assert str(oc.next_capture_day("2026-08-28").date()) == "2026-09-01"
    assert str(oc.next_capture_day("2026-08-30").date()) == "2026-09-01"


def test_cadence_and_filename_use_utc_not_the_input_offset():
    instant = "2026-08-25T00:30:00+09:00"  # Monday 15:30 UTC
    assert oc.is_capture_day(instant) is False
    assert oc.snapshot_name(instant) == "fixtures_2026-08-24T153000Z.csv"
    assert oc.next_capture_at(instant).isoformat() == "2026-08-25T06:00:00+00:00"


def test_the_module_header_says_when_and_wires_no_cron():
    """§: the operator runs it. A scheduler committed by a harness is a
    standing side effect nobody reviewed."""
    text = Path(oc.__file__).read_text()
    assert "No cron is wired here" in text
    assert "Tuesday" in text and "Friday" in text
    for forbidden in ("crontab", "schedule.every", "APScheduler"):
        assert forbidden not in text


def test_the_default_archive_is_not_doubled():
    assert oc.SNAPSHOT_DIR == paths.DATA_DIR / "odds_snapshots"
    assert oc.PROVENANCE_PATH == oc.SNAPSHOT_DIR / "provenance.jsonl"
    assert oc.PROVENANCE_HEAD_PATH == (
        oc.SNAPSHOT_DIR / "provenance.head.json")


# --------------------------------------------------------------------------
# 2. the filename carries the instant the season file never will
# --------------------------------------------------------------------------
def test_the_filename_is_the_publication_bound_the_season_file_lacks():
    name = oc.snapshot_name("2026-08-28T06:00:00Z")
    assert name == "fixtures_2026-08-28T060000Z.csv"
    # naive timestamps are read as UTC rather than as local time
    assert oc.snapshot_name("2026-08-28T06:00:00") == name


def test_the_snapshot_names_sort_in_capture_order(tmp_path):
    names = [oc.snapshot_name(f"2026-08-{d:02d}T06:00:00Z")
             for d in (28, 25, 21)]
    assert sorted(names) == [
        "fixtures_2026-08-21T060000Z.csv",
        "fixtures_2026-08-25T060000Z.csv",
        "fixtures_2026-08-28T060000Z.csv"]


# --------------------------------------------------------------------------
# 3. capture, hash, store
# --------------------------------------------------------------------------
def test_a_capture_stores_the_bytes_the_hash_and_the_provenance(tmp_path):
    blob = _csv()
    snap = oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                      when="2026-08-28T06:00:00Z")
    assert snap.written is True
    assert snap.path.read_bytes() == blob
    assert snap.sha256 == oc.sha256_bytes(blob)
    assert snap.n_bytes == len(blob)
    assert snap.n_epl_rows == 2 and snap.n_rows == 24

    record = oc.read_provenance(tmp_path / "provenance.jsonl")
    assert len(record) == 1
    assert record[0]["sha256"] == snap.sha256
    assert record[0]["day_name"] == "Friday"
    assert record[0]["capture_day"] is True
    assert record[0]["closing_columns"] == []


def test_the_same_bytes_are_two_availability_observations(tmp_path):
    """Same value observed Friday is evidence it remained available Friday."""
    blob = _csv()
    first = oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                       when="2026-08-25T06:00:00Z")
    again = oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                       when="2026-08-28T06:00:00Z")
    assert first.written is True and again.written is False
    assert again.observation_recorded is True
    assert again.path == first.path
    assert again.duplicate_of == first.path.name
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 1
    records = oc.read_provenance(tmp_path / "provenance.jsonl")
    assert len(records) == 2
    assert records[0]["sha256"] == records[1]["sha256"]
    assert records[1]["duplicate_of"] == first.path.name

    # A changed publication is a third observation, with no duplicate link.
    moved = oc.capture(fetcher=_fetcher(_csv(rows=6)), directory=tmp_path,
                       when="2026-09-01T06:00:00Z")
    assert moved.written is True
    assert moved.duplicate_of is None
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 2


def test_force_is_compatible_but_no_longer_needed_for_a_repeat(tmp_path):
    blob = _csv()
    oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
               when="2026-08-25T06:00:00Z")
    dup = oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                     when="2026-08-28T06:00:00Z", force=True)
    assert dup.written is False and dup.observation_recorded is True
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 1
    assert oc.read_provenance(tmp_path / "provenance.jsonl")[1][
        "force_requested"] is True


def test_same_second_captures_never_overwrite(tmp_path):
    first_blob = _csv(rows=4)
    second_blob = _csv(rows=6)
    when = "2026-08-28T06:00:00Z"
    first = oc.capture(fetcher=_fetcher(first_blob), directory=tmp_path,
                       when=when)
    second = oc.capture(fetcher=_fetcher(second_blob), directory=tmp_path,
                        when=when)
    assert first.path.name == "fixtures_2026-08-28T060000Z.csv"
    assert second.path.name == (
        "fixtures_2026-08-28T060000Z_"
        f"{oc.sha256_bytes(second_blob)[:12]}.csv")
    assert first.path.read_bytes() == first_blob
    assert second.path.read_bytes() == second_blob
    assert oc.latest_snapshot(tmp_path) == second.path


def test_publish_collision_never_deletes_the_external_artifact(
        tmp_path, monkeypatch):
    external = b"external process won the filename race"
    collided: list[Path] = []

    def collide(target, blob):
        target.write_bytes(external)
        collided.append(target)
        raise oc.CaptureError("refusing to overwrite existing snapshot")

    monkeypatch.setattr(oc, "_publish_new_file", collide)
    with pytest.raises(oc.CaptureError, match="refusing to overwrite"):
        oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
                   when="2026-08-28T06:00:00Z")
    assert collided and collided[0].read_bytes() == external
    assert (tmp_path / "provenance.jsonl").read_text() == ""
    assert not (tmp_path / "provenance.head.json").exists()


def test_same_bytes_same_second_are_distinct_observations(tmp_path):
    blob = _csv()
    when = "2026-08-28T06:00:00Z"
    first = oc.capture(fetcher=_fetcher(blob), directory=tmp_path, when=when)
    second = oc.capture(fetcher=_fetcher(blob), directory=tmp_path, when=when)
    assert first.path == second.path
    assert first.written is True and second.written is False
    records = oc.read_provenance(tmp_path / "provenance.jsonl")
    assert len(records) == 2
    assert records[0]["observation_id"] != records[1]["observation_id"]
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 1


def test_a_prospective_duplicate_observation_id_is_refused_before_append(
        tmp_path, monkeypatch):
    blob = _csv()
    oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
               when="2026-08-28T06:00:00Z")
    ledger = tmp_path / "provenance.jsonl"
    existing = oc.read_provenance(ledger)[0]["observation_id"]
    monkeypatch.setattr(oc, "_observation_id",
                        lambda fetched_at, digest, previous: existing)
    with pytest.raises(oc.CaptureError, match="duplicate append"):
        oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                   when="2026-08-28T06:00:00Z")
    assert len(oc.read_provenance(ledger)) == 1
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 1


# --------------------------------------------------------------------------
# 4. the refusals
# --------------------------------------------------------------------------
def test_an_error_page_is_refused_rather_than_stored(tmp_path):
    """Storing it would put a hole in the archive that looks like a capture."""
    with pytest.raises(oc.CaptureError) as exc:
        oc.capture(fetcher=_fetcher(b"<html>404</html>"), directory=tmp_path)
    assert "error page" in str(exc.value)
    assert list(tmp_path.glob("fixtures_*.csv")) == []


def test_a_feed_that_drops_the_ruled_column_is_a_refusal(tmp_path):
    """§0.3 rules Avg-at-the-open BECAUSE it is the one column present in every
    season read and in the live feed. A feed that stops publishing it needs a
    ruling, not a silent capture."""
    blob = _csv(columns=("Div", "Date", "HomeTeam", "AwayTeam",
                         "B365H", "B365D", "B365A"))
    with pytest.raises(oc.CaptureError) as exc:
        oc.capture(fetcher=_fetcher(blob), directory=tmp_path)
    assert "AvgH" in str(exc.value)
    assert list(tmp_path.glob("fixtures_*.csv")) == []


def test_a_valid_cross_division_file_with_zero_epl_rows_is_refused(tmp_path):
    blob = _csv(div="EC")
    with pytest.raises(oc.CaptureError) as exc:
        oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                   when="2026-08-28T06:00:00Z")
    assert "zero Div=E0 rows" in str(exc.value)
    assert list(tmp_path.glob("fixtures_*.csv")) == []
    assert not (tmp_path / "provenance.jsonl").exists()


def test_a_fetcher_that_returns_text_is_a_refusal(tmp_path):
    """A snapshot is the file's own bytes; anything decoded and re-encoded is a
    copy of it, and its hash would not be the source's hash."""
    with pytest.raises(oc.CaptureError) as exc:
        oc.capture(fetcher=lambda url: _csv().decode(), directory=tmp_path)
    assert "not bytes" in str(exc.value)


def test_a_closing_column_in_the_live_feed_is_recorded_not_swallowed(tmp_path):
    """The capture stores what the feed sends. It does not filter the closing
    columns out — §0.3's refusal lives in `epl.mktprior`'s reader, where the
    anchor actually reads — but it RECORDS that they appeared, because a feed
    that starts publishing closes is a fact the next reader should meet on the
    record rather than discover."""
    blob = _csv(columns=("Div", "Date", "HomeTeam", "AwayTeam",
                         "AvgH", "AvgD", "AvgA", "AvgCH", "AvgCD", "AvgCA"))
    snap = oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                      when="2026-08-28T06:00:00Z")
    assert snap.written is True
    record = oc.read_provenance(tmp_path / "provenance.jsonl")[0]
    assert record["closing_columns"] == ["AvgCH", "AvgCD", "AvgCA"]

    # and the anchor's own reader still refuses them by shape
    from epl import mktprior as mp
    with pytest.raises(mp.ClosingOddsRead):
        mp.assert_opening_columns(("AvgCH", "AvgCD", "AvgCA"))


def test_a_corrupt_provenance_line_is_a_typed_refusal(tmp_path):
    (tmp_path / "provenance.jsonl").write_text('{"ok": 1}\nnot json\n')
    with pytest.raises(oc.CaptureError) as exc:
        oc.read_provenance(tmp_path / "provenance.jsonl")
    assert "line 2" in str(exc.value)


def test_read_provenance_rehashes_every_snapshot(tmp_path):
    snap = oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
                      when="2026-08-28T06:00:00Z")
    snap.path.write_bytes(snap.path.read_bytes() + b"tampered")
    with pytest.raises(oc.CaptureError) as exc:
        oc.read_provenance(tmp_path / "provenance.jsonl")
    assert "hash is" in str(exc.value)


def test_directory_only_provenance_read_uses_that_archives_ledger(tmp_path):
    oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
               when="2026-08-28T06:00:00Z")
    records = oc.read_provenance(directory=tmp_path)
    assert len(records) == 1
    assert records[0]["path"] == "fixtures_2026-08-28T060000Z.csv"


def test_provenance_read_refuses_a_ledger_outside_the_locked_archive(tmp_path):
    with pytest.raises(oc.CaptureError, match="one archive lock"):
        oc.read_provenance(tmp_path / "other" / "provenance.jsonl",
                           directory=tmp_path)


def test_read_provenance_refuses_a_symlinked_snapshot(tmp_path):
    blob = _csv()
    snap = oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                      when="2026-08-28T06:00:00Z")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.csv"
    outside.write_bytes(blob)
    snap.path.unlink()
    snap.path.symlink_to(outside)
    with pytest.raises(oc.CaptureError, match="non-regular"):
        oc.read_provenance(tmp_path / "provenance.jsonl")


def test_read_provenance_refuses_an_orphan_snapshot(tmp_path):
    orphan = tmp_path / oc.snapshot_name("2026-08-28T06:00:00Z")
    orphan.write_bytes(_csv())
    with pytest.raises(oc.CaptureError) as exc:
        oc.read_provenance(tmp_path / "provenance.jsonl")
    assert "has no provenance" in str(exc.value)


def test_a_valid_orphan_requires_explicit_degraded_adoption(tmp_path):
    when = "2026-08-28T06:00:00Z"
    orphan = tmp_path / oc.snapshot_name(when)
    orphan.write_bytes(_csv())
    adopted = oc.adopt_orphan(
        orphan, observed_at=when,
        reason="recovered after a process kill before the ledger append")
    assert adopted.written is False
    assert adopted.observation_recorded is True
    assert adopted.recovered_orphan is True
    record = oc.read_provenance(tmp_path / "provenance.jsonl")[0]
    assert record["recovered_orphan"] is True
    assert record["url"] is None
    assert record["source_provenance"] == "unknown_preledger_artifact"
    assert "process kill" in record["adoption_reason"]


def test_a_zero_epl_orphan_cannot_be_adopted_as_healthy(tmp_path):
    when = "2026-08-26T05:39:48Z"
    orphan = tmp_path / oc.snapshot_name(when)
    orphan.write_bytes(_csv(div="EC"))
    with pytest.raises(oc.CaptureError, match="zero Div=E0 rows"):
        oc.adopt_orphan(orphan, observed_at=when,
                        reason="legacy pre-ledger artifact")
    assert not (tmp_path / "provenance.jsonl").exists()


def test_read_provenance_refuses_a_missing_snapshot(tmp_path):
    snap = oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
                      when="2026-08-28T06:00:00Z")
    snap.path.unlink()
    with pytest.raises(oc.CaptureError) as exc:
        oc.read_provenance(tmp_path / "provenance.jsonl")
    assert "names missing" in str(exc.value)


def test_the_provenance_chain_detects_metadata_tampering(tmp_path):
    oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
               when="2026-08-28T06:00:00Z")
    ledger = tmp_path / "provenance.jsonl"
    record = json.loads(ledger.read_text())
    record["url"] = "https://attacker.invalid/fixtures.csv"
    ledger.write_text(json.dumps(record) + "\n")
    with pytest.raises(oc.CaptureError) as exc:
        oc.read_provenance(ledger)
    assert "record hash is invalid" in str(exc.value)


def test_unchained_legacy_provenance_is_explicitly_refused(tmp_path):
    oc.capture(fetcher=_fetcher(_csv(rows=4)), directory=tmp_path,
               when="2026-08-25T06:00:00Z")
    oc.capture(fetcher=_fetcher(_csv(rows=6)), directory=tmp_path,
               when="2026-08-28T06:00:00Z")
    ledger = tmp_path / "provenance.jsonl"
    legacy = []
    for line in ledger.read_text().splitlines():
        record = json.loads(line)
        for key in ("schema_version", "prev_record_sha256",
                    "record_sha256", "observation_id"):
            record.pop(key, None)
        legacy.append(record)
    legacy[0]["url"] = "tampered legacy metadata"
    ledger.write_text("".join(json.dumps(r) + "\n" for r in legacy))
    with pytest.raises(oc.CaptureError, match="unchained legacy provenance"):
        oc.read_provenance(ledger)


def test_external_head_detects_lost_duplicate_tail_observation(tmp_path):
    blob = _csv()
    oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
               when="2026-08-25T06:00:00Z")
    oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
               when="2026-08-28T06:00:00Z")
    ledger = tmp_path / "provenance.jsonl"
    lines = ledger.read_text().splitlines()
    assert len(lines) == 2
    ledger.write_text(lines[0] + "\n")
    with pytest.raises(oc.CaptureError, match="disagrees with the provenance"):
        oc.read_provenance(ledger)


def test_nonempty_ledger_without_external_head_is_refused(tmp_path):
    oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
               when="2026-08-28T06:00:00Z")
    (tmp_path / "provenance.head.json").unlink()
    with pytest.raises(oc.CaptureError, match="durable head"):
        oc.read_provenance(tmp_path / "provenance.jsonl")


def test_a_failed_ledger_append_rolls_back_the_snapshot(
        tmp_path, monkeypatch):
    def fail_append(path, record):
        raise OSError("disk full")

    monkeypatch.setattr(oc, "_append_provenance", fail_append)
    with pytest.raises(oc.CaptureError, match="could not commit provenance"):
        oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
                   when="2026-08-28T06:00:00Z")
    assert list(tmp_path.glob("fixtures_*.csv")) == []
    assert (tmp_path / "provenance.jsonl").read_text() == ""


def test_a_failed_head_update_preserves_uncertain_ledger_and_snapshot(
        tmp_path, monkeypatch):
    monkeypatch.setattr(
        oc, "_write_head",
        lambda path, payload: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(oc.CaptureError, match="manual reconciliation"):
        oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
                   when="2026-08-28T06:00:00Z")
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 1
    assert len((tmp_path / "provenance.jsonl").read_text().splitlines()) == 1
    assert not (tmp_path / "provenance.head.json").exists()
    with pytest.raises(oc.CaptureError, match="durable head"):
        oc.read_provenance(directory=tmp_path)


def test_a_readable_head_does_not_hide_a_reported_durability_failure(
        tmp_path, monkeypatch):
    real_write_head = oc._write_head

    def publish_then_report_failure(path, payload):
        real_write_head(path, payload)
        raise OSError("injected post-replace fsync uncertainty")

    monkeypatch.setattr(oc, "_write_head", publish_then_report_failure)
    with pytest.raises(oc.CaptureError, match="durability is uncertain"):
        oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
                   when="2026-08-28T06:00:00Z")
    # The bytes are internally consistent, but the call still refused to claim
    # durability. An operator can now reconcile rather than trust a swallowed
    # fsync error.
    assert len(oc.read_provenance(directory=tmp_path)) == 1
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 1


def test_failed_append_never_truncates_a_concurrent_writers_tail(
        tmp_path, monkeypatch):
    ledger = tmp_path / "provenance.jsonl"
    ledger.touch()
    external = b'{"external_writer":true}\n'
    real_write = oc.os.write

    def write_then_interleave(fd, raw):
        written = real_write(fd, raw)
        with ledger.open("ab", buffering=0) as other:
            other.write(external)
        # Simulate the caller being unable to certify its otherwise-complete
        # write. The old implementation truncated both rows to the old offset.
        return written - 1

    monkeypatch.setattr(oc.os, "write", write_then_interleave)
    with pytest.raises(oc.CaptureError, match="uncertain tail was preserved"):
        oc._append_provenance(ledger, {"ours": True})
    raw = ledger.read_bytes()
    assert b'"ours":true' in raw
    assert raw.endswith(external)


@pytest.mark.parametrize("replace_inode", [False, True])
def test_failed_commit_never_unlinks_a_post_publish_replacement(
        tmp_path, monkeypatch, replace_inode):
    """Rollback owns both an inode and its bytes, not a pathname forever."""
    when = "2026-08-28T06:00:00Z"
    target = tmp_path / oc.snapshot_name(when)
    replacement = b"external process replaced the published pathname"

    def replace_then_fail(path, record, *, n_records):
        assert target.exists()
        if replace_inode:
            target.unlink()
        target.write_bytes(replacement)
        raise oc.CaptureError("injected provenance failure")

    monkeypatch.setattr(oc, "_commit_provenance", replace_then_fail)
    with pytest.raises(oc.CaptureError, match="rollback refused"):
        oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path, when=when)
    assert target.read_bytes() == replacement
    safety_copies = list(tmp_path.glob(".oddscapture-rollback-*.tmp"))
    assert len(safety_copies) == 1
    assert safety_copies[0].read_bytes() == replacement


def test_post_link_directory_fsync_failure_rolls_back_owned_artifact(
        tmp_path, monkeypatch):
    real_fsync = oc._fsync_directory
    failed = False

    def fail_once_after_link(directory):
        nonlocal failed
        if not failed and list(Path(directory).glob("fixtures_*.csv")):
            failed = True
            raise OSError("injected directory fsync failure")
        return real_fsync(directory)

    monkeypatch.setattr(oc, "_fsync_directory", fail_once_after_link)
    with pytest.raises(oc.CaptureError, match="cannot publish snapshot"):
        oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
                   when="2026-08-28T06:00:00Z")
    assert failed is True
    assert not list(tmp_path.glob("fixtures_*.csv"))
    assert not list(tmp_path.glob(".oddscapture-rollback-*.tmp"))
    assert (tmp_path / "provenance.jsonl").read_text() == ""


def test_uncertain_rollback_reports_and_preserves_its_safety_quarantine(
        tmp_path, monkeypatch):
    real_fsync = oc._fsync_directory

    def fail_publication_and_rollback(directory):
        directory = Path(directory)
        if (list(directory.glob("fixtures_*.csv"))
                or list(directory.glob(".oddscapture-rollback-*.tmp"))):
            raise OSError("injected persistent directory fsync failure")
        return real_fsync(directory)

    blob = _csv()
    monkeypatch.setattr(oc, "_fsync_directory",
                        fail_publication_and_rollback)
    with pytest.raises(oc.CaptureError, match="safety quarantine"):
        oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                   when="2026-08-28T06:00:00Z")
    assert not list(tmp_path.glob("fixtures_*.csv"))
    quarantined = list(tmp_path.glob(".oddscapture-rollback-*.tmp"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == blob
    assert (tmp_path / "provenance.jsonl").read_text() == ""
    with pytest.raises(oc.CaptureError, match="safety quarantine"):
        oc.read_provenance(directory=tmp_path)


# --------------------------------------------------------------------------
# 5. the CLI, and the real directory
# --------------------------------------------------------------------------
def test_status_fetches_nothing(tmp_path, capsys):
    assert oc.main(["--status", "--dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["cadence"] == ["Tuesday", "Friday"]
    assert out["n_captures"] == 0
    assert out["missed_slots"] == []
    assert out["n_missed_slots"] == 0
    assert out["archive_verified"] is True
    assert out["scheduler_wired"] is False
    assert "no cron is wired here" in out["note"]


def test_status_exposes_due_today_without_claiming_a_scheduler(tmp_path):
    before = oc.capture_status(when="2026-08-25T06:00:00Z",
                               directory=tmp_path)
    assert before["capture_due_today"] is True
    assert before["scheduler_wired"] is False
    oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
               when="2026-08-25T06:00:00Z")
    after = oc.capture_status(when="2026-08-25T07:00:00Z",
                              directory=tmp_path)
    assert after["archive_verified"] is True
    assert after["capture_due_today"] is False
    assert after["n_observations"] == after["n_snapshot_files"] == 1


def test_status_names_a_missed_latest_slot(tmp_path):
    oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
               when="2026-08-25T06:00:00Z")
    status = oc.capture_status(when="2026-08-30T07:00:00Z",
                               directory=tmp_path)
    assert status["latest_scheduled_slot"] == "2026-08-28T06:00:00+00:00"
    assert status["latest_slot_observed"] is False
    assert status["missed_latest_slot"] is True
    assert status["next_capture_at"] == "2026-09-01T06:00:00+00:00"


def test_pre_0600_capture_does_not_satisfy_the_0600_slot(tmp_path):
    oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
               when="2026-08-25T00:01:00Z")
    status = oc.capture_status(when="2026-08-25T07:00:00Z",
                               directory=tmp_path)
    assert status["capture_due_today"] is True
    assert status["latest_slot_observed"] is False
    assert status["missed_latest_slot"] is True
    assert status["n_pre_slot_observations"] == 1


def test_status_as_of_never_uses_a_future_receipt(tmp_path):
    older = oc.capture(fetcher=_fetcher(_csv(rows=4)), directory=tmp_path,
                       when="2026-08-21T06:00:00Z")
    oc.capture(fetcher=_fetcher(_csv(rows=6)), directory=tmp_path,
               when="2026-08-25T23:00:00Z")

    status = oc.capture_status(when="2026-08-25T07:00:00Z",
                               directory=tmp_path)
    assert status["capture_due_today"] is True
    assert status["latest_slot_observed"] is False
    assert status["missed_latest_slot"] is True
    assert status["latest"]["path"] == older.path.name
    assert status["n_observations"] == 1
    assert status["n_future_observations"] == 1


def test_adopting_an_older_orphan_does_not_make_it_latest(tmp_path):
    newer = oc.capture(fetcher=_fetcher(_csv(rows=6)), directory=tmp_path,
                       when="2026-09-01T06:00:00Z")
    older_when = "2026-08-28T06:00:00Z"
    older = tmp_path / oc.snapshot_name(older_when)
    older.write_bytes(_csv(rows=4))
    oc.adopt_orphan(
        older, observed_at=older_when,
        reason="recovered older crash artifact after newer capture")
    assert oc.latest_snapshot(tmp_path) == newer.path
    status = oc.capture_status(when="2026-09-02T07:00:00Z",
                               directory=tmp_path)
    assert status["latest"]["path"] == newer.path.name


# --- the slot behind a LATER capture (A17) --------------------------------
# `missed_latest_slot` asks about ONE slot, the newest. So the archive kept a
# hole and the report lost it the instant the NEXT slot was captured.

def test_a_later_capture_does_not_forgive_an_earlier_missed_slot(tmp_path):
    """A17: the cadence is a SEQUENCE, not a head.

    Two Fridays on file with the Tuesday between them never taken.
    `missed_latest_slot` goes False the instant the second Friday lands — the
    archive keeps the hole and the report used to lose it. `missed_slots` is
    what keeps naming it."""
    oc.capture(fetcher=_fetcher(_csv(rows=4)), directory=tmp_path,
               when="2026-08-21T06:05:00Z")                 # a Friday
    oc.capture(fetcher=_fetcher(_csv(rows=6)), directory=tmp_path,
               when="2026-08-28T06:04:00Z")                 # the next Friday
    status = oc.capture_status(when="2026-08-28T07:00:00Z", directory=tmp_path)
    assert status["latest_scheduled_slot"] == "2026-08-28T06:00:00+00:00"
    assert status["latest_slot_observed"] is True
    assert status["missed_latest_slot"] is False
    assert status["missed_slots"] == ["2026-08-25T06:00:00+00:00"]
    assert status["n_missed_slots"] == 1
    assert status["n_observations"] == 2


def test_every_hole_is_named_oldest_first_not_only_the_newest(tmp_path):
    """Two slots skipped in a row, then a capture: both are named, in order.
    The refusal that reads this list has to be able to name each of them."""
    oc.capture(fetcher=_fetcher(_csv(rows=4)), directory=tmp_path,
               when="2026-08-21T06:05:00Z")                 # a Friday
    oc.capture(fetcher=_fetcher(_csv(rows=6)), directory=tmp_path,
               when="2026-09-01T06:02:00Z")                 # the Tuesday after next
    status = oc.capture_status(when="2026-09-01T07:00:00Z", directory=tmp_path)
    assert status["missed_latest_slot"] is False
    assert status["missed_slots"] == ["2026-08-25T06:00:00+00:00",
                                      "2026-08-28T06:00:00+00:00"]
    assert status["n_missed_slots"] == 2


def test_the_sequence_starts_where_the_archive_did_and_not_before(tmp_path):
    """A14's `archive_started` bound, asked per SLOT: an archive that began on
    a Friday is not behind on the Tuesday before it. Without this the first run
    on a fresh machine would report a hole for every slot since the epoch."""
    oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
               when="2026-08-21T06:05:00Z")                 # a Friday, 06:05
    status = oc.capture_status(when="2026-08-21T07:00:00Z", directory=tmp_path)
    assert status["latest_scheduled_slot"] == "2026-08-21T06:00:00+00:00"
    assert status["missed_slots"] == []
    assert status["n_missed_slots"] == 0


def test_missed_slots_never_drops_what_missed_latest_slot_already_said(tmp_path):
    """The new field is a SUPERSET of the old one, so no refusal is lost.

    The pre-06:00 receipt is the case that proves it: the archive has started,
    its 06:00 slot is unobserved, and the sequence begins at that slot."""
    oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
               when="2026-08-25T00:01:00Z")
    status = oc.capture_status(when="2026-08-25T07:00:00Z", directory=tmp_path)
    assert status["missed_latest_slot"] is True
    assert status["missed_slots"] == ["2026-08-25T06:00:00+00:00"]
    assert status["n_pre_slot_observations"] == 1


def test_the_superset_holds_when_the_archive_began_after_the_newest_slot(
        tmp_path):
    """The superset property at the branch that IMPLEMENTS it, not beside it.

    `test_missed_slots_never_drops_...` states the property on a pre-06:00
    receipt, for which the sequence already begins at the head, so the
    enumeration alone carries it. This is the other case: the archive's first
    receipt is OFF-CADENCE and lands after the newest slot, so `_cadence_start`
    returns a slot LATER than that slot and `_scheduled_slots` yields nothing
    at all. A14 still refuses on the head today, so the head is appended and
    the set must not say less than the head boolean does.

    Here the appended head is the whole set, because a non-empty enumeration
    always ends at the newest unobserved slot and so never reaches this
    branch; the sort is asserted as the field's oldest-first contract, which
    every reader of `missed_slots` — the refusal, the journal line, the
    printed line — is entitled to on any path that builds it."""
    oc.capture(fetcher=_fetcher(_csv()), directory=tmp_path,
               when="2026-08-29T10:00:00Z")           # a Saturday, off-cadence
    status = oc.capture_status(when="2026-08-29T11:00:00Z", directory=tmp_path)
    latest_slot = status["latest_scheduled_slot"]
    assert latest_slot == "2026-08-28T06:00:00+00:00"  # the Friday before it
    assert status["n_observations"] == 1               # the archive HAS begun
    assert status["n_off_cadence_observations"] == 1
    assert status["missed_latest_slot"] is True
    assert latest_slot in status["missed_slots"]       # the superset, at last
    assert status["missed_slots"] == [latest_slot]
    assert status["missed_slots"] == sorted(status["missed_slots"])
    assert status["n_missed_slots"] == 1


@pytest.mark.skipif(not SNAPSHOT_DIR.exists(), reason="no odds snapshots")
def test_the_real_snapshots_carry_the_ruled_column_and_no_pinnacle():
    """§0.3's live-feed half, asserted on the captures themselves."""
    files = sorted(SNAPSHOT_DIR.glob("fixtures_*.csv"))
    if not files:
        pytest.skip("no captured fixtures file")
    for path in files:
        header = path.read_text().splitlines()[0].lstrip("﻿").split(",")
        assert all(c in header for c in ("AvgH", "AvgD", "AvgA")), path.name
        assert not any(c in header for c in ("PSH", "PSD", "PSA")), (
            f"{path.name}: Pinnacle has reappeared in the live feed; §0.3's "
            "ruling that Avg is the only column present in every season read "
            "is worth re-checking")
