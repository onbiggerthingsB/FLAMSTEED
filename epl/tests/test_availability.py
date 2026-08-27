"""The availability capture: A11's first use, and the fourth bitemporal ledger.

Every test here runs against an INJECTED fetcher, a synthetic payload and a
`tmp_path` tree: this suite never touches the network, never reads `data/`, and
never writes the real tracked manifest. It reads exactly one tracked file — the
2026/27 season manifest, which is in git — because the club-key mapping is the
one thing that must be checked against the season the capture belongs to.

The synthetic payload's twenty team spellings are the ones the live feed
actually prints ("Spurs", "Nott'm Forest", "Man Utd"): the mapping contract is
that those resolve through `epl.teams` into the season manifest's club keys, so
a test using tidier names would test nothing.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from epl import availability as av

# --------------------------------------------------------------------------
# synthetic payloads
# --------------------------------------------------------------------------

#: (id, name) exactly as the live bootstrap feed spells them for 2026/27.
FPL_TEAMS = (
    (1, "Arsenal"), (2, "Aston Villa"), (3, "Bournemouth"), (4, "Brentford"),
    (5, "Brighton"), (6, "Chelsea"), (7, "Coventry City"), (8, "Crystal Palace"),
    (9, "Everton"), (10, "Fulham"), (11, "Hull City"), (12, "Ipswich Town"),
    (13, "Leeds"), (14, "Liverpool"), (15, "Man City"), (16, "Man Utd"),
    (17, "Newcastle"), (18, "Nott'm Forest"), (19, "Spurs"), (20, "Sunderland"),
)


def _team_rows(names=FPL_TEAMS) -> list[dict]:
    return [{"id": i, "name": n, "short_name": n[:3].upper(), "code": i}
            for i, n in names]


def _player(pid: int, *, team: int = 1, web_name: str | None = None,
            status: str = "a", chance_this=None, chance_next=None,
            news: str = "", news_added=None, now_cost: int = 50,
            **extra) -> dict:
    row = {
        "id": pid,
        "web_name": web_name if web_name is not None else f"Player{pid}",
        "team": team,
        "status": status,
        "chance_of_playing_this_round": chance_this,
        "chance_of_playing_next_round": chance_next,
        "news": news,
        "news_added": news_added,
        "now_cost": now_cost,
        "element_type": 3,
        "team_code": team,
    }
    row.update(extra)
    return row


def _payload(players=None, *, teams=None, **extra) -> dict:
    payload = {
        "elements": list(players) if players is not None
        else [_player(1), _player(2, team=2), _player(3, team=19)],
        "teams": _team_rows() if teams is None else teams,
        "events": [],
        "element_types": [],
        "total_players": 12345,
    }
    payload.update(extra)
    return payload


def _blob(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _fetcher(payload_or_blob):
    blob = (payload_or_blob if isinstance(payload_or_blob, bytes)
            else _blob(payload_or_blob))
    return lambda url: blob


def _where(tmp_path: Path) -> dict:
    return {
        "raw_dir": tmp_path / "raw",
        "ledger_path": tmp_path / "availability_ledger.jsonl",
        "manifest_path": tmp_path / "availability_manifest.jsonl",
    }


def _pull(tmp_path: Path, payload, when: str, **kw):
    return av.pull(fetcher=_fetcher(payload), now=when, **_where(tmp_path), **kw)


def _rows(tmp_path: Path) -> list[dict]:
    return av.read_ledger(_where(tmp_path)["ledger_path"])


def _manifest(tmp_path: Path) -> list[dict]:
    return av.read_manifest(_where(tmp_path)["manifest_path"])


# --------------------------------------------------------------------------
# 1. the delta ledger
# --------------------------------------------------------------------------
def test_the_first_snapshot_appends_every_player(tmp_path):
    """Delta encoding has to start somewhere: with no prior state, every
    player's state is new, so the first snapshot appends all of them."""
    players = [_player(i, team=(i % 20) + 1) for i in range(1, 41)]
    report = _pull(tmp_path, _payload(players), "2026-08-27T09:00:00Z")

    assert report.first_snapshot is True
    assert report.written is True
    assert len(report.rows) == 40
    assert len(_rows(tmp_path)) == 40
    assert {r["player_id"] for r in _rows(tmp_path)} == set(range(1, 41))


def test_a_second_snapshot_that_changed_nothing_appends_nothing(tmp_path):
    """The whole point of delta encoding: a daily capture of a quiet week must
    not append 600 identical rows a day. Nothing changed, so nothing is a row —
    but the snapshot itself is still stored and still attested."""
    payload = _payload()
    _pull(tmp_path, payload, "2026-08-27T09:00:00Z")
    before = list(_rows(tmp_path))

    report = _pull(tmp_path, payload, "2026-08-28T09:00:00Z")

    assert report.first_snapshot is False
    assert report.rows == ()
    assert _rows(tmp_path) == before
    assert len(_manifest(tmp_path)) == 2, (
        "the snapshot is still a snapshot: a quiet day is attested by a "
        "manifest line even though it moves no ledger row")
    assert _manifest(tmp_path)[-1]["n_rows_appended"] == 0


def test_one_changed_field_appends_exactly_one_row(tmp_path):
    """A status change for one player is one row, not a re-statement of the
    squad."""
    _pull(tmp_path, _payload(), "2026-08-27T09:00:00Z")

    hurt = [
        _player(1),
        _player(2, team=2, status="d", chance_this=75, chance_next=75,
                news="Thigh injury - 75% chance of playing",
                news_added="2026-08-27T17:00:08.846118Z"),
        _player(3, team=19),
    ]
    report = _pull(tmp_path, _payload(hurt), "2026-08-28T09:00:00Z")

    assert len(report.rows) == 1
    row = report.rows[0]
    assert row["player_id"] == 2
    assert row["status"] == "d"
    assert row["chance_this"] == 75
    assert row["chance_next"] == 75
    assert row["news"] == "Thigh injury - 75% chance of playing"
    assert row["news_added"] == "2026-08-27T17:00:08.846118Z", (
        "news_added is the SOURCE's clock and is stored verbatim — parsing and "
        "reprinting it would make our formatting the record")
    assert row["observed_at"] == "2026-08-28T09:00:00Z", (
        "observed_at is OUR pull clock, and it is the snapshot's, not the "
        "source's")
    assert len(_rows(tmp_path)) == 4


def test_a_correction_is_a_new_row_and_edits_nothing(tmp_path):
    """The source restates a player as fit after flagging him. That is a third
    row, and the first two still say what they said: nothing edits."""
    _pull(tmp_path, _payload([_player(1)]), "2026-08-27T09:00:00Z")
    _pull(tmp_path, _payload([
        _player(1, status="d", chance_this=25, news="Knock - 25% chance",
                news_added="2026-08-28T10:00:00.000000Z")]),
        "2026-08-28T09:00:00Z")
    _pull(tmp_path, _payload([
        _player(1, status="a", chance_this=100, news="",
                news_added="2026-08-29T10:00:00.000000Z")]),
        "2026-08-29T09:00:00Z")

    rows = _rows(tmp_path)
    assert len(rows) == 3
    assert [r["status"] for r in rows] == ["a", "d", "a"]
    assert [r["chance_this"] for r in rows] == [None, 25, 100]
    assert rows[1]["news"] == "Knock - 25% chance", (
        "the superseded row is untouched — a correction is an append")


def test_a_transfer_changes_team_key_and_that_is_a_tracked_change(tmp_path):
    """Club membership is in the row, so it is tracked: a January move is a
    row, not a silent rewrite of who the player has always played for."""
    _pull(tmp_path, _payload([_player(1, team=1)]), "2026-08-27T09:00:00Z")
    report = _pull(tmp_path, _payload([_player(1, team=15)]),
                   "2026-08-28T09:00:00Z")

    assert len(report.rows) == 1
    assert [r["team_key"] for r in _rows(tmp_path)] == ["arsenal", "man_city"]


def test_a_player_who_vanishes_and_returns_unchanged_appends_nothing(tmp_path):
    """The delta is measured against the player's LAST KNOWN state, not against
    whoever happened to be in the previous payload. A player who drops out of
    the feed for a week (a loan listing being rebuilt, a squad-number reshuffle)
    and comes back saying exactly what he said before has changed nothing, and
    a row saying otherwise would be an event the source never reported.

    This is also the case that separates a correct re-derivation from a
    plausible one, so `verify` must agree with `pull` about it.
    """
    _pull(tmp_path, _payload([_player(1), _player(2, team=2)]),
          "2026-08-27T09:00:00Z")
    _pull(tmp_path, _payload([_player(1)]), "2026-08-28T09:00:00Z")
    report = _pull(tmp_path, _payload([_player(1), _player(2, team=2)]),
                   "2026-08-29T09:00:00Z")

    assert report.rows == ()
    assert len(_rows(tmp_path)) == 2
    assert av.verify(**_where(tmp_path)).ok is True, (
        "re-derivation forgot the vanished player's state and the ledger it "
        "rebuilt is not the ledger the pulls wrote")


def test_verify_catches_a_raw_snapshot_no_manifest_line_attests(tmp_path):
    """A crash between writing the bytes and appending the line leaves an
    orphan: a snapshot in the archive that nothing says was ever pulled. It is
    invisible to every check that starts from the manifest, so one check has to
    start from the other end."""
    where = _where(tmp_path)
    _pull(tmp_path, _payload(), "2026-08-27T09:00:00Z")
    (where["raw_dir"] / "bootstrap_20260828T090000Z.json.gz").write_bytes(
        gzip.compress(_blob(_payload()), mtime=0))

    out = av.verify(**where)
    assert out.ok is False
    assert any("bootstrap_20260828T090000Z" in p and "no manifest line" in p
               for p in out.problems)


def test_the_ledger_row_carries_exactly_the_ruled_fields(tmp_path):
    """A11's row: the five availability fields plus who, where and the two
    clocks, with the snapshot digest that ties the row to bytes on disk."""
    report = _pull(tmp_path, _payload([_player(1, web_name="Bruno G.")]),
                   "2026-08-27T09:00:00Z")
    row = report.rows[0]

    assert set(row) == {
        "player_id", "web_name", "team_key", "status", "chance_this",
        "chance_next", "news", "news_added", "observed_at", "snapshot_sha256"}
    assert row["snapshot_sha256"] == report.snapshot.sha256
    assert row["web_name"] == "Bruno G."
    assert row["team_key"] == "arsenal"


# --------------------------------------------------------------------------
# 2. raw bytes and the tracked manifest
# --------------------------------------------------------------------------
def test_the_raw_payload_is_stored_verbatim_and_hashed(tmp_path):
    """A11 (b): the bytes are the record. Gunzipping the stored snapshot must
    return exactly what the source served, and the digest is of THOSE bytes,
    not of the gzip container."""
    payload = _payload()
    blob = _blob(payload)
    report = _pull(tmp_path, blob, "2026-08-27T09:00:00Z")

    assert report.snapshot.raw_path.name == "bootstrap_20260827T090000Z.json.gz"
    assert gzip.decompress(report.snapshot.raw_path.read_bytes()) == blob
    assert report.snapshot.sha256 == av.sha256_bytes(blob)
    assert report.snapshot.n_bytes == len(blob)


def test_the_manifest_line_attests_without_redistributing(tmp_path):
    """The tracked line carries digest, byte count, player count and the
    source's own high-water clock — enough to prove what was pulled, and none
    of the pulled data."""
    players = [_player(1), _player(2, team=2, status="i",
                                   news="Groin injury",
                                   news_added="2026-08-26T22:00:07.797766Z")]
    report = _pull(tmp_path, _payload(players), "2026-08-27T09:00:00Z")
    line = _manifest(tmp_path)[-1]

    assert line["stamp"] == "20260827T090000Z"
    assert line["observed_at"] == "2026-08-27T09:00:00Z"
    assert line["sha256"] == report.snapshot.sha256
    assert line["n_bytes"] == report.snapshot.n_bytes
    assert line["n_players"] == 2
    assert line["max_news_added"] == "2026-08-26T22:00:07.797766Z"
    assert line["n_rows_appended"] == 2
    assert line["clock_regression"] is False
    assert set(line) == {
        "stamp", "observed_at", "season", "sha256", "n_bytes", "n_players",
        "max_news_added", "n_rows_appended", "clock_regression", "raw", "url"}
    assert "Groin injury" not in json.dumps(line), (
        "the manifest is attestation, not redistribution: it carries digests "
        "and counts and the source's clock, never a byte of source text")


def test_a_dry_run_computes_everything_and_writes_nothing(tmp_path):
    where = _where(tmp_path)
    report = _pull(tmp_path, _payload(), "2026-08-27T09:00:00Z", dry_run=True)

    assert report.dry_run is True
    assert report.written is False
    assert len(report.rows) == 3, "it still says what it WOULD have appended"
    assert not where["ledger_path"].exists()
    assert not where["manifest_path"].exists()
    assert not where["raw_dir"].exists() or not list(where["raw_dir"].glob("*.gz"))


def test_the_same_snapshot_pulled_twice_at_one_stamp_is_a_no_op(tmp_path):
    """Same stamp, same bytes: the snapshot is already attested. Recording it
    twice would make the count of manifest lines a lie about the count of
    pulls that saw something."""
    payload = _payload()
    _pull(tmp_path, payload, "2026-08-27T09:00:00Z")
    report = _pull(tmp_path, payload, "2026-08-27T09:00:00Z")

    assert report.written is False
    assert len(_manifest(tmp_path)) == 1
    assert len(_rows(tmp_path)) == 3


# --------------------------------------------------------------------------
# 3. the typed refusals
# --------------------------------------------------------------------------
def test_a_missing_asserted_field_is_a_typed_refusal_not_a_silent_narrow(tmp_path):
    """If the feed stops publishing chance_of_playing_next_round, the capture
    must STOP. Quietly writing nulls would fill the ledger with 'we know he is
    fine' rows that mean 'we stopped being told'."""
    broken = _player(2, team=2)
    del broken["chance_of_playing_next_round"]

    with pytest.raises(av.AvailabilitySchemaDrift) as exc:
        _pull(tmp_path, _payload([_player(1), broken]), "2026-08-27T09:00:00Z")

    assert "chance_of_playing_next_round" in str(exc.value)
    assert not _where(tmp_path)["ledger_path"].exists()
    assert not _where(tmp_path)["manifest_path"].exists()


def test_a_missing_top_level_key_is_schema_drift(tmp_path):
    payload = _payload()
    del payload["teams"]
    with pytest.raises(av.AvailabilitySchemaDrift) as exc:
        _pull(tmp_path, payload, "2026-08-27T09:00:00Z")
    assert "teams" in str(exc.value)


def test_a_missing_price_field_is_schema_drift(tmp_path):
    """A11 pre-states the roster and price data the same payload carries, so
    now_cost is asserted too — its disappearance is a ruling, not a shrug."""
    broken = _player(1)
    del broken["now_cost"]
    with pytest.raises(av.AvailabilitySchemaDrift) as exc:
        _pull(tmp_path, _payload([broken]), "2026-08-27T09:00:00Z")
    assert "now_cost" in str(exc.value)


def test_added_fields_are_tolerated_because_raw_keeps_everything(tmp_path):
    """The feed grows a column most months. Additions are not drift: the raw
    snapshot keeps them whether the ledger reads them or not."""
    payload = _payload([_player(1, some_new_2027_metric=4.2)],
                       new_top_level_section=[{"x": 1}])
    report = _pull(tmp_path, payload, "2026-08-27T09:00:00Z")

    assert len(report.rows) == 1
    stored = json.loads(gzip.decompress(report.snapshot.raw_path.read_bytes()))
    assert stored["elements"][0]["some_new_2027_metric"] == 4.2
    assert stored["new_top_level_section"] == [{"x": 1}]


def test_a_club_outside_the_season_manifest_refuses_rather_than_slugs(tmp_path):
    """Burnley resolves perfectly well through `epl.teams` — and is not in
    2026/27. A capture that accepted it would file rows against a club the
    season does not contain."""
    teams = [(i, n) for i, n in FPL_TEAMS if i != 1]
    teams.insert(0, (1, "Burnley"))

    with pytest.raises(av.TeamUnmapped) as exc:
        _pull(tmp_path, _payload(teams=_team_rows(tuple(teams))),
              "2026-08-27T09:00:00Z")
    assert "burnley" in str(exc.value).lower()


def test_an_unresolvable_club_spelling_refuses_rather_than_slugs(tmp_path):
    teams = [(i, n) for i, n in FPL_TEAMS if i != 1]
    teams.insert(0, (1, "Wanderers Athletic"))

    with pytest.raises(av.TeamUnmapped) as exc:
        _pull(tmp_path, _payload(teams=_team_rows(tuple(teams))),
              "2026-08-27T09:00:00Z")
    assert "Wanderers Athletic" in str(exc.value)


def test_a_player_on_a_team_id_the_payload_never_declared_refuses(tmp_path):
    with pytest.raises(av.TeamUnmapped) as exc:
        _pull(tmp_path, _payload([_player(1, team=77)]), "2026-08-27T09:00:00Z")
    assert "77" in str(exc.value)


def test_a_backwards_source_clock_refuses_and_writes_nothing(tmp_path):
    """A snapshot whose high-water news_added is EARLIER than the last one's is
    the source restating history. Refuse and surface: the alternative is a
    ledger that silently disagrees with the archive it was derived from."""
    fresh = _payload([_player(1, status="i", news="Out",
                              news_added="2026-08-26T22:00:07.797766Z")])
    _pull(tmp_path, fresh, "2026-08-27T09:00:00Z")

    stale = _payload([_player(1, status="i", news="Out",
                              news_added="2026-08-20T10:00:00.000000Z")])
    with pytest.raises(av.ClockRegression) as exc:
        _pull(tmp_path, stale, "2026-08-28T09:00:00Z")

    assert "2026-08-26T22:00:07.797766Z" in str(exc.value)
    assert "2026-08-20T10:00:00.000000Z" in str(exc.value)
    assert len(_manifest(tmp_path)) == 1, "nothing was written"
    assert len(list(_where(tmp_path)["raw_dir"].glob("*.gz"))) == 1


def test_a_restatement_can_be_accepted_but_only_on_the_record(tmp_path):
    """The escape hatch is a reviewable mark in the tracked manifest, never a
    silent acceptance — the season doctrine's rule for rewriting history."""
    _pull(tmp_path, _payload([_player(1, status="i", news="Out",
                                      news_added="2026-08-26T22:00:07.797766Z")]),
          "2026-08-27T09:00:00Z")
    report = _pull(tmp_path, _payload([_player(1, status="i", news="Out",
                                               news_added="2026-08-20T10:00:00.000000Z")]),
                   "2026-08-28T09:00:00Z", accept_restatement=True)

    assert report.written is True
    assert _manifest(tmp_path)[-1]["clock_regression"] is True
    assert av.verify(**_where(tmp_path)).ok is True, (
        "a marked restatement is not a verification failure — an unmarked one is")


def test_a_pull_clock_that_walked_backwards_refuses_too(tmp_path):
    """The other clock can regress as well. An NTP correction or a container
    with a bad clock produces a pull stamped BEFORE the last one, and the delta
    it appends would be a change dated earlier than the state it changed from —
    two readers ("last row in the file" and "latest row by observed_at") would
    then give different answers about who is fit."""
    _pull(tmp_path, _payload([_player(1)]), "2026-08-28T09:00:00Z")

    with pytest.raises(av.ClockRegression) as exc:
        _pull(tmp_path, _payload([_player(1, status="i", news="Out")]),
              "2026-08-27T09:00:00Z")

    assert "observed_at" in str(exc.value)
    assert len(_manifest(tmp_path)) == 1
    assert len(_rows(tmp_path)) == 1


def test_a_second_line_for_one_stamp_with_other_bytes_is_a_manifest_conflict(tmp_path):
    """Two different payloads cannot both be what the source served at one
    instant. Overwriting the line would destroy the attestation."""
    _pull(tmp_path, _payload([_player(1)]), "2026-08-27T09:00:00Z")

    with pytest.raises(av.ManifestConflict) as exc:
        _pull(tmp_path, _payload([_player(1), _player(2, team=2)]),
              "2026-08-27T09:00:00Z")

    assert "20260827T090000Z" in str(exc.value)
    assert len(_manifest(tmp_path)) == 1
    assert len(_rows(tmp_path)) == 1


def test_a_fetcher_that_fails_is_a_typed_unreachable(tmp_path):
    def boom(url):
        raise OSError("connection reset by peer")

    with pytest.raises(av.SourceUnreachable) as exc:
        av.pull(fetcher=boom, now="2026-08-27T09:00:00Z", **_where(tmp_path))
    assert "connection reset" in str(exc.value)


def test_bytes_that_are_not_json_are_unreachable_not_drift(tmp_path):
    """An HTML error page is the source being unavailable in substance. It is
    not a schema change, and calling it one would send the operator hunting for
    a renamed field that never moved."""
    with pytest.raises(av.SourceUnreachable) as exc:
        _pull(tmp_path, b"<html><title>503</title></html>",
              "2026-08-27T09:00:00Z")
    assert "JSON" in str(exc.value)


def test_a_fetcher_returning_text_instead_of_bytes_refuses(tmp_path):
    with pytest.raises(av.SourceUnreachable) as exc:
        av.pull(fetcher=lambda url: json.dumps(_payload()),
                now="2026-08-27T09:00:00Z", **_where(tmp_path))
    assert "bytes" in str(exc.value)


def test_a_payload_that_is_not_the_seasons_twenty_clubs_refuses(tmp_path):
    """A structural floor that an error page or a pre-season stub can never
    clear: the bootstrap of a 20-club league carries 20 clubs."""
    with pytest.raises(av.AvailabilitySchemaDrift) as exc:
        _pull(tmp_path, _payload(teams=_team_rows(FPL_TEAMS[:19])),
              "2026-08-27T09:00:00Z")
    assert "19" in str(exc.value) and "20" in str(exc.value)


def test_an_empty_squad_list_refuses(tmp_path):
    with pytest.raises(av.AvailabilitySchemaDrift) as exc:
        _pull(tmp_path, _payload([]), "2026-08-27T09:00:00Z")
    assert "elements" in str(exc.value)


# --------------------------------------------------------------------------
# 4. verify()
# --------------------------------------------------------------------------
def test_verify_re_derives_the_ledger_from_the_raw_bytes(tmp_path):
    _pull(tmp_path, _payload([_player(1), _player(2, team=2)]),
          "2026-08-27T09:00:00Z")
    _pull(tmp_path, _payload([_player(1, status="i", news="Out",
                                      news_added="2026-08-28T08:00:00.000000Z"),
                              _player(2, team=2)]),
          "2026-08-28T09:00:00Z")

    report = av.verify(**_where(tmp_path))
    assert report.ok is True
    assert report.problems == ()
    assert report.n_snapshots == 2
    assert report.n_rows == 3 == report.n_rows_rederived


def test_verify_catches_a_tampered_ledger_row(tmp_path):
    """The ledger is derived, so a hand-edited row is not a correction — it is
    a divergence from the bytes, and re-derivation is what finds it."""
    where = _where(tmp_path)
    _pull(tmp_path, _payload([_player(1)]), "2026-08-27T09:00:00Z")

    rows = av.read_ledger(where["ledger_path"])
    rows[0]["status"] = "i"
    where["ledger_path"].write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8")

    report = av.verify(**where)
    assert report.ok is False
    assert any("ledger" in p for p in report.problems)


def test_verify_catches_a_tampered_raw_byte(tmp_path):
    """The manifest is the tracked truth about the untracked bytes. One flipped
    character in a gzipped snapshot breaks the digest, and that is the whole
    point of writing the digest down."""
    where = _where(tmp_path)
    report = _pull(tmp_path, _payload([_player(1, web_name="Saliba")]),
                   "2026-08-27T09:00:00Z")

    blob = gzip.decompress(report.snapshot.raw_path.read_bytes())
    report.snapshot.raw_path.write_bytes(
        gzip.compress(blob.replace(b"Saliba", b"Saliba!")))

    out = av.verify(**where)
    assert out.ok is False
    assert any("sha256" in p for p in out.problems)


def test_verify_catches_a_missing_raw_snapshot(tmp_path):
    where = _where(tmp_path)
    report = _pull(tmp_path, _payload(), "2026-08-27T09:00:00Z")
    report.snapshot.raw_path.unlink()

    out = av.verify(**where)
    assert out.ok is False
    assert any("missing" in p for p in out.problems)


def test_verify_catches_an_unmarked_clock_regression_across_snapshots(tmp_path):
    """The regression check lives in verify() too: a manifest whose lines walk
    backwards was assembled by something that skipped the pull-time refusal."""
    where = _where(tmp_path)
    _pull(tmp_path, _payload([_player(1, status="i", news="Out",
                                      news_added="2026-08-26T22:00:07.797766Z")]),
          "2026-08-27T09:00:00Z")
    _pull(tmp_path, _payload([_player(1, status="i", news="Out",
                                      news_added="2026-08-20T10:00:00.000000Z")]),
          "2026-08-28T09:00:00Z", accept_restatement=True)

    lines = av.read_manifest(where["manifest_path"])
    lines[-1]["clock_regression"] = False
    where["manifest_path"].write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in lines),
        encoding="utf-8")

    out = av.verify(**where)
    assert out.ok is False
    assert any("news_added" in p for p in out.problems)


def test_verify_catches_a_manifest_whose_pull_clock_walked_backwards(tmp_path):
    """`verify` re-asks what `pull` asked, on both clocks: a manifest assembled
    out of order was assembled by something that skipped the pull-time refusal."""
    where = _where(tmp_path)
    _pull(tmp_path, _payload([_player(1)]), "2026-08-27T09:00:00Z")
    _pull(tmp_path, _payload([_player(1, status="i", news="Out")]),
          "2026-08-28T09:00:00Z")

    lines = av.read_manifest(where["manifest_path"])
    lines.reverse()
    where["manifest_path"].write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in lines),
        encoding="utf-8")

    out = av.verify(**where)
    assert out.ok is False
    assert any("observed_at" in p for p in out.problems)


def test_verify_on_an_empty_capture_is_vacuously_clean(tmp_path):
    out = av.verify(**_where(tmp_path))
    assert out.ok is True
    assert out.n_snapshots == 0


# --------------------------------------------------------------------------
# 5. status()
# --------------------------------------------------------------------------
def test_status_is_one_screen_of_what_the_operator_needs(tmp_path):
    _pull(tmp_path, _payload([_player(1), _player(2, team=2), _player(3, team=19)]),
          "2026-08-27T09:00:00Z")
    _pull(tmp_path, _payload([
        _player(1, status="i", chance_this=0, chance_next=0,
                news="Groin injury - Unknown return date",
                news_added="2026-08-28T08:00:00.000000Z"),
        _player(2, team=2, status="d", chance_this=75,
                news="Thigh injury - 75% chance of playing",
                news_added="2026-08-28T08:30:00.000000Z"),
        _player(3, team=19)]),
        "2026-08-28T09:00:00Z")

    report = av.status(**_where(tmp_path))
    assert report["n_snapshots"] == 2
    assert report["last_pull"]["stamp"] == "20260828T090000Z"
    assert report["n_players"] == 3
    assert report["n_flagged"] == 2
    assert report["n_changes_since_previous"] == 2
    assert {p["player_id"] for p in report["flagged"]} == {1, 2}

    text = av.render_status(report)
    assert "20260828T090000Z" in text
    assert "Groin injury - Unknown return date" in text
    assert text.count("\n") < 40, "one screen means one screen"


def test_status_before_any_pull_says_so_rather_than_crashing(tmp_path):
    report = av.status(**_where(tmp_path))
    assert report["n_snapshots"] == 0
    assert report["last_pull"] is None
    assert "no snapshots" in av.render_status(report).lower()


# --------------------------------------------------------------------------
# 6. the clock discipline
# --------------------------------------------------------------------------
def test_the_capture_reads_no_wall_clock_and_moving_the_clock_proves_it(monkeypatch, tmp_path):
    """`observed_at` is an INPUT: the CLI reads a clock, the library never does.
    The swap goes through `sys.modules` as well as the module attribute, so a
    function-local `import datetime` — which a module-attribute monkeypatch
    never sees — is intercepted too. Same cure as `epl.matchboard`'s: do not
    string-match today's date, MOVE the clock and require identical bytes.
    """
    import datetime as real_datetime
    import sys
    import time as real_time

    payload_a = _payload([_player(1), _player(2, team=2)])
    payload_b = _payload([_player(1, status="i", news="Out",
                                  news_added="2026-08-28T08:00:00.000000Z"),
                          _player(2, team=2)])

    a = tmp_path / "before"
    a.mkdir()
    _pull(a, payload_a, "2026-08-27T09:00:00Z")
    _pull(a, payload_b, "2026-08-28T09:00:00Z")
    ledger_before = _where(a)["ledger_path"].read_bytes()
    manifest_before = _where(a)["manifest_path"].read_bytes()

    class _FrozenTime:
        @staticmethod
        def time():
            return 0.0

        @staticmethod
        def monotonic():
            return 0.0

        @staticmethod
        def perf_counter():
            return 0.0

        @staticmethod
        def strftime(fmt, t=None):
            return "FROZEN"

        @staticmethod
        def gmtime(secs=None):
            return real_time.gmtime(0)

        @staticmethod
        def localtime(secs=None):
            return real_time.localtime(0)

    class _FrozenDatetime:
        timezone = real_datetime.timezone
        timedelta = real_datetime.timedelta

        class datetime(real_datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(1970, 1, 1)

            @classmethod
            def utcnow(cls):
                return cls(1970, 1, 1)

        class date(real_datetime.date):
            @classmethod
            def today(cls):
                return cls(1970, 1, 1)

    monkeypatch.setitem(sys.modules, "time", _FrozenTime)
    monkeypatch.setitem(sys.modules, "datetime", _FrozenDatetime)
    monkeypatch.setattr(av, "time", _FrozenTime, raising=False)
    monkeypatch.setattr(av, "datetime", _FrozenDatetime, raising=False)

    b = tmp_path / "after"
    b.mkdir()
    _pull(b, payload_a, "2026-08-27T09:00:00Z")
    _pull(b, payload_b, "2026-08-28T09:00:00Z")

    assert _where(b)["ledger_path"].read_bytes() == ledger_before, (
        "the ledger changed when the clock moved — something is stamping rows "
        "with the wall clock instead of the passed observed_at")
    assert _where(b)["manifest_path"].read_bytes() == manifest_before
    assert av.verify(**_where(b)).ok is True


def test_pull_will_not_invent_an_observed_at(tmp_path):
    """There is no default `now`. A capture whose pull clock came from
    somewhere unstated is a row nobody can reproduce."""
    with pytest.raises(TypeError):
        av.pull(fetcher=_fetcher(_payload()), **_where(tmp_path))


def test_a_naive_observed_at_is_read_as_utc_not_as_local_time(tmp_path):
    report = _pull(tmp_path, _payload(), "2026-08-27 09:00:00")
    assert report.snapshot.observed_at == "2026-08-27T09:00:00Z"


def test_a_non_utc_observed_at_is_converted_not_relabelled(tmp_path):
    report = _pull(tmp_path, _payload(),
                   pd.Timestamp("2026-08-27T11:00:00+02:00"))
    assert report.snapshot.observed_at == "2026-08-27T09:00:00Z"


# --------------------------------------------------------------------------
# 7. the command
# --------------------------------------------------------------------------
def _argv(tmp_path: Path, *args: str) -> list[str]:
    where = _where(tmp_path)
    return [*args,
            "--raw-dir", str(where["raw_dir"]),
            "--ledger", str(where["ledger_path"]),
            "--manifest", str(where["manifest_path"])]


def test_the_pull_command_writes_and_exits_zero(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(av, "_download", lambda url, **kw: _blob(_payload()))
    assert av.main(_argv(tmp_path, "pull")) == 0
    assert len(_manifest(tmp_path)) == 1
    assert "20260" in capsys.readouterr().out


def test_the_dry_run_command_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(av, "_download", lambda url, **kw: _blob(_payload()))
    assert av.main(_argv(tmp_path, "pull", "--dry-run")) == 0
    assert not _where(tmp_path)["manifest_path"].exists()


def test_a_refusal_stops_the_command_with_exit_two(monkeypatch, tmp_path, capsys):
    """The simcli convention: STOP on stderr, exit 2, no half-written state."""
    def boom(url, **kw):
        raise OSError("name or service not known")

    monkeypatch.setattr(av, "_download", boom)
    assert av.main(_argv(tmp_path, "pull")) == 2
    err = capsys.readouterr().err
    assert err.startswith("STOP: SourceUnreachable")


def test_the_verify_command_exits_two_when_the_archive_disagrees(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(av, "_download", lambda url, **kw: _blob(_payload()))
    assert av.main(_argv(tmp_path, "pull")) == 0

    path = _where(tmp_path)["ledger_path"]
    path.write_text(path.read_text(encoding="utf-8").replace('"a"', '"i"'),
                    encoding="utf-8")

    assert av.main(_argv(tmp_path, "verify")) == 2
    assert "STOP" in capsys.readouterr().err


def test_the_status_command_prints_and_exits_zero(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(av, "_download", lambda url, **kw: _blob(_payload()))
    av.main(_argv(tmp_path, "pull"))
    assert av.main(_argv(tmp_path, "status")) == 0
    assert "snapshots" in capsys.readouterr().out.lower()


# --------------------------------------------------------------------------
# 8. what this module is NOT
# --------------------------------------------------------------------------
def test_the_capture_is_standalone_and_wired_into_no_model():
    """A11: nothing enters a model without its own preregistration through the
    covariate gate. The cheapest way to keep that true is for the live cycle
    not to import this module at all."""
    source = Path(av.__file__).with_name("livecycle.py").read_text(encoding="utf-8")
    assert "availability" not in source

    text = Path(av.__file__).read_text(encoding="utf-8")
    for forbidden in ("import epl.leaguesim", "from epl import leaguesim",
                      "from epl import particles", "from epl import elo",
                      "from epl import fit", "from epl import mktprior"):
        assert forbidden not in text, (
            f"{forbidden!r} in the capture module: this is an input archive, "
            "not a model feature")


# --------------------------------------------------------------------------
# 9. the source's clock is not ours to control
# --------------------------------------------------------------------------
def test_a_source_clock_we_cannot_read_is_a_typed_refusal_not_a_traceback(tmp_path):
    """`news_added` is the SOURCE's clock, and its format is the source's to
    change. A value that is not a timestamp used to escape as pandas'
    `DateParseError`, which is not in the family — and `main()` turns an
    `AvailabilityError` into `STOP` + exit 2 and lets everything else
    traceback. So an unreadable stamp died without saying what it refused.

    It is drift: the field is still there and no longer carries what the
    capture asserted it carries. The message must name the player, because
    "one of six hundred rows" is not a lead.
    """
    with pytest.raises(av.AvailabilitySchemaDrift) as exc:
        _pull(tmp_path, _payload([_player(1, web_name="Bruno G.", status="d",
                                          news="Thigh injury",
                                          news_added="sometime last week")]),
              "2026-08-27T09:00:00Z")

    assert "sometime last week" in str(exc.value)
    assert "Bruno G." in str(exc.value)
    assert "news_added" in str(exc.value)
    assert not _where(tmp_path)["manifest_path"].exists(), "nothing was written"
    assert not _where(tmp_path)["ledger_path"].exists()


def test_a_source_stamp_without_a_zone_is_read_as_utc_like_our_own(tmp_path):
    """One row stamped without a zone next to six hundred stamped with one
    raised `TypeError: Cannot compare tz-naive and tz-aware timestamps` out of
    the high-water comparison — an untyped crash on a benign format wobble.

    The source's clock is read by the same rule as ours: no zone means UTC.
    That rule is a guess about someone else's clock, so it is bounded — the
    string stored in the ledger is still the source's own, byte for byte, and
    only the COMPARISON is normalised.
    """
    report = _pull(tmp_path, _payload([
        _player(1, status="i", news="Out",
                news_added="2026-08-26T22:00:07.797766Z"),
        _player(2, team=2, status="d", news="Knock",
                news_added="2026-08-27T10:00:00")]),
        "2026-08-27T11:00:00Z")

    assert report.snapshot.max_news_added == "2026-08-27T10:00:00", (
        "the later of the two is the naive one, read as UTC")
    stamps = {r["player_id"]: r["news_added"] for r in report.rows}
    assert stamps == {1: "2026-08-26T22:00:07.797766Z",
                      2: "2026-08-27T10:00:00"}, (
        "stored verbatim: normalising for comparison must not rewrite the row")
    assert av.verify(**_where(tmp_path)).ok is True


def test_a_manifest_high_water_we_cannot_read_refuses_typed(tmp_path):
    """The other side of the same parse: `pull` compares this snapshot's
    high-water clock against the LAST MANIFEST LINE's. A hand-edited line
    reaches the same parser, and it must refuse in the family rather than
    traceback through the comparison."""
    where = _where(tmp_path)
    _pull(tmp_path, _payload([_player(1, status="i", news="Out",
                                      news_added="2026-08-26T22:00:07.797766Z")]),
          "2026-08-27T09:00:00Z")

    lines = av.read_manifest(where["manifest_path"])
    lines[-1]["max_news_added"] = "last Tuesday"
    where["manifest_path"].write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in lines),
        encoding="utf-8")

    with pytest.raises(av.AvailabilityError) as exc:
        _pull(tmp_path, _payload([_player(1, status="i", news="Out still",
                                          news_added="2026-08-28T08:00:00.000000Z")]),
              "2026-08-28T09:00:00Z")
    assert "last Tuesday" in str(exc.value)


def test_an_unreadable_source_clock_stops_the_command_with_exit_two(
        monkeypatch, tmp_path, capsys):
    """What the typing is FOR: the operator gets one STOP line naming the
    player and the value, not a stack trace."""
    payload = _payload([_player(1, web_name="Bruno G.", status="d",
                                news="Thigh", news_added="sometime last week")])
    monkeypatch.setattr(av, "_download", lambda url, **kw: _blob(payload))

    assert av.main(_argv(tmp_path, "pull")) == 2
    err = capsys.readouterr().err
    assert err.startswith("STOP: AvailabilitySchemaDrift")
    assert "Bruno G." in err


def test_a_json_payload_that_is_not_an_object_is_drift(tmp_path):
    """A proxy that answers `[]` served JSON. It did not serve the feed."""
    with pytest.raises(av.AvailabilitySchemaDrift) as exc:
        _pull(tmp_path, b"[]", "2026-08-27T09:00:00Z")
    assert "list" in str(exc.value)


# --------------------------------------------------------------------------
# 10. where the three artifacts live — A11 (b), structurally
# --------------------------------------------------------------------------
def test_the_manifest_is_tracked_beside_the_seasons_other_ledgers():
    """A11 (b): attestation without redistribution. The manifest is the TRACKED
    half, so it lives in `epl/season/<season>/` with the results ledger, the
    kickoff amendments and the fixture corpus — the directory whose git history
    IS the known-at record."""
    path = av.default_manifest_path("2026/27")
    assert path.name == "availability_manifest.jsonl"
    assert path.parent.name == "2026_27"
    assert path.parent == Path(av.season_mod.SEASON_ROOT) / "2026_27"
    assert (path.parent / "results_ledger.jsonl").exists(), (
        "the tracked manifest belongs beside the other tracked ledgers")


def test_the_bytes_and_the_derived_ledger_live_under_gitignored_data():
    """The other half of A11 (b): no source byte is ever tracked. Both the raw
    snapshots and the derived ledger sit under `data/epl/`, which `epl.paths`
    documents as covered by the repo-root-anchored `/data/` rule.

    Asserted as a path relationship rather than by shelling out to
    `git check-ignore`: CI has no `data/` directory and this suite makes no git
    assumptions.
    """
    from epl import paths

    assert av.AVAILABILITY_DIR.parent == paths.DATA_DIR
    assert av.RAW_DIR.parent == av.AVAILABILITY_DIR
    assert av.LEDGER_PATH.parent == av.AVAILABILITY_DIR
    assert paths.DATA_DIR.name == "epl" and paths.DATA_DIR.parent.name == "data"
    assert "/data/" in Path(paths.REPO_ROOT, ".gitignore").read_text(
        encoding="utf-8"), "the anchored rule the layout depends on"


def test_verify_reports_an_unreadable_manifest_stamp_instead_of_dying_on_it(tmp_path):
    """`verify` returns a report rather than raising, because a checker that
    stops at the first problem cannot tell the operator how much of the archive
    is sound — and a corrupt tracked manifest is exactly when it gets run.

    A line whose own `observed_at` is not a timestamp used to escape through
    `_utc` and abandon every later line unchecked.
    """
    where = _where(tmp_path)
    _pull(tmp_path, _payload([_player(1)]), "2026-08-27T09:00:00Z")
    _pull(tmp_path, _payload([_player(1, status="i", news="Out")]),
          "2026-08-28T09:00:00Z")
    _pull(tmp_path, _payload([_player(1, status="a", news="")]),
          "2026-08-29T09:00:00Z")

    lines = av.read_manifest(where["manifest_path"])
    lines[0]["observed_at"] = "whenever"
    where["manifest_path"].write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in lines),
        encoding="utf-8")

    out = av.verify(**where)
    assert out.ok is False
    assert any("whenever" in p for p in out.problems)
    assert out.n_snapshots == 3, (
        "it read the whole manifest rather than stopping at the bad line")
    assert any("bootstrap_20260829T090000Z" in p or "ledger" in p
               for p in out.problems), (
        "the later lines were still checked, and the ledger no longer matches "
        "a re-derivation that could not replay the first snapshot")
