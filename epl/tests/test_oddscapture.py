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

from epl import oddscapture as oc

SNAPSHOT_DIR = Path("data/epl/odds_snapshots")


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


def test_the_module_header_says_when_and_wires_no_cron():
    """§: the operator runs it. A scheduler committed by a harness is a
    standing side effect nobody reviewed."""
    text = Path(oc.__file__).read_text()
    assert "No cron is wired here" in text
    assert "Tuesday" in text and "Friday" in text
    for forbidden in ("crontab", "schedule.every", "APScheduler"):
        assert forbidden not in text


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


def test_the_same_bytes_are_not_stored_twice(tmp_path):
    """The source overwrites ONE file in place, so two runs between two
    publications see the same bytes. A directory of duplicates would make the
    count of captures a lie about the count of publications."""
    blob = _csv()
    first = oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                       when="2026-08-25T06:00:00Z")
    again = oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                       when="2026-08-28T06:00:00Z")
    assert first.written is True and again.written is False
    assert again.path == first.path                # points at what is on disk
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 1
    assert len(oc.read_provenance(tmp_path / "provenance.jsonl")) == 1

    # ...and it is a refusal to WRITE, not a failure: a new publication lands
    moved = oc.capture(fetcher=_fetcher(_csv(rows=6)), directory=tmp_path,
                       when="2026-09-01T06:00:00Z")
    assert moved.written is True
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 2


def test_force_stores_a_duplicate_when_the_operator_asks(tmp_path):
    blob = _csv()
    oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
               when="2026-08-25T06:00:00Z")
    dup = oc.capture(fetcher=_fetcher(blob), directory=tmp_path,
                     when="2026-08-28T06:00:00Z", force=True)
    assert dup.written is True
    assert len(list(tmp_path.glob("fixtures_*.csv"))) == 2


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


# --------------------------------------------------------------------------
# 5. the CLI, and the real directory
# --------------------------------------------------------------------------
def test_status_fetches_nothing(tmp_path, capsys):
    assert oc.main(["--status", "--dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["cadence"] == ["Tuesday", "Friday"]
    assert out["n_captures"] == 0
    assert "no cron is wired here" in out["note"]


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
