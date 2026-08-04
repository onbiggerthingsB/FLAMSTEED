"""The OA alias map and its EVIDENCE RULE (OA Plan 2 v2, V0 / finding 14).

An alias is a claim about what the Odds API actually calls a team. Seeding one
from memory is how a phantom spelling ("Korea Republic") enters the matcher and
silently widens what counts as coverage, so the rule is: an alias enters
``config/oa_aliases.yaml`` ONLY when an ARCHIVED raw response contains that
exact spelling, and the record names the archive digest that proves it. The
tests below pin the rule (structure + the seeded content) and, wherever the
gitignored archive is present locally, re-verify the cited bytes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from wcmodel.eval.aliases import (
    AliasError,
    AmbiguousFixtureMatch,
    ALIAS_PATH,
    canonical,
    load_alias_records,
    load_aliases,
    resolve_event,
    verify_alias_evidence,
)

_ROOT = Path(__file__).resolve().parents[2]
_ARCHIVE = _ROOT / "data" / "odds_raw"

_needs_archive = pytest.mark.skipif(
    not _ARCHIVE.exists(),
    reason=f"{_ARCHIVE} absent (gitignored paid-evidence store) — restore it to "
           "re-arm the alias evidence check",
)


def _write(tmp_path: Path, records) -> Path:
    path = tmp_path / "oa_aliases.yaml"
    path.write_text(yaml.safe_dump({"aliases": records}, sort_keys=False))
    return path


def _record(**over) -> dict:
    base = {"api_name": "USA", "store_name": "United States",
            "evidence_sha256": "a" * 64, "note": "seeded by test"}
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# The committed map: exactly one alias, and it is the hash-justified one.       #
# --------------------------------------------------------------------------- #
def test_committed_map_holds_exactly_the_evidenced_aliases():
    # Every entry must trace to archived paid bytes. Two exist: USA (OA-0a
    # probe, wc2022 R16 listing) and Bosnia & Herzegovina (G-A acquisition,
    # wc2026 discovery listing — the four event=n rows of the 217-fixture
    # run). Anything else is an unevidenced claim about the API's vocabulary
    # until its own archived bytes say so.
    assert load_aliases() == {
        "usa": "United States",
        "bosnia & herzegovina": "Bosnia and Herzegovina",
    }


def test_korea_republic_is_not_seeded():
    # The archived wc2022 R16 listing spells it "South Korea" — the store
    # spelling verbatim. "Korea Republic" appears in NO archived response, so
    # seeding it would be exactly the unevidenced alias finding 14 refused.
    records = load_alias_records()
    spellings = {r["api_name"].casefold() for r in records}
    assert "korea republic" not in spellings


def test_every_committed_record_cites_a_full_digest():
    for record in load_alias_records():
        digest = record["evidence_sha256"]
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")


@_needs_archive
def test_committed_evidence_survives_reverification():
    # The load-bearing check: the cited archived bytes must ACTUALLY contain
    # the API spelling claimed. A record citing a digest whose payload never
    # says "USA" is an alias with a footnote, not an alias with evidence.
    assert verify_alias_evidence(raw_dir=_ARCHIVE) == []


@_needs_archive
def test_evidence_verification_is_not_vacuous():
    # Prove the checker can FAIL: a fabricated spelling against a real
    # archived digest must be reported, or the check above proves nothing.
    real = load_alias_records()[0]["evidence_sha256"]
    bad = [_record(api_name="Korea Republic", store_name="South Korea",
                   evidence_sha256=real)]
    problems = verify_alias_evidence(records=bad, raw_dir=_ARCHIVE)
    assert len(problems) == 1 and "Korea Republic" in problems[0]


@_needs_archive
def test_missing_archive_entry_is_reported_not_silently_passed():
    problems = verify_alias_evidence(records=[_record()], raw_dir=_ARCHIVE)
    assert len(problems) == 1 and "not in the archive" in problems[0]


# --------------------------------------------------------------------------- #
# Loader validation — a hand-edited map must fail loudly, never half-load.      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("record,fragment", [
    ({"store_name": "United States", "evidence_sha256": "a" * 64}, "api_name"),
    ({"api_name": "USA", "evidence_sha256": "a" * 64}, "store_name"),
    ({"api_name": "USA", "store_name": "United States"}, "evidence_sha256"),
    (_record(evidence_sha256="deadbeef"), "sha256"),
    (_record(api_name="  "), "empty"),
    (_record(api_name="United States"), "aliases itself"),
])
def test_malformed_record_refused(tmp_path, record, fragment):
    with pytest.raises(AliasError) as exc:
        load_aliases(_write(tmp_path, [record]))
    assert fragment in str(exc.value)


def test_duplicate_api_name_refused(tmp_path):
    # Case-insensitive: "USA" and "usa" are ONE key in the matcher, so two
    # records would silently make the file's last line win.
    path = _write(tmp_path, [_record(), _record(api_name="usa",
                                                store_name="United States A")])
    with pytest.raises(AliasError) as exc:
        load_aliases(path)
    assert "duplicate" in str(exc.value)


def test_alias_chain_refused(tmp_path):
    # A -> B and B -> C is a two-step rewrite whose result depends on
    # iteration order. One hop only.
    path = _write(tmp_path, [
        _record(api_name="USA", store_name="United States"),
        _record(api_name="United States", store_name="US of A"),
    ])
    with pytest.raises(AliasError) as exc:
        load_aliases(path)
    assert "chain" in str(exc.value)


def test_empty_map_is_legal(tmp_path):
    # Before any evidence exists the map is EMPTY, not absent: an empty file
    # must load as "no aliases", never as a crash that tempts a seed.
    path = tmp_path / "oa_aliases.yaml"
    path.write_text("aliases: []\n")
    assert load_aliases(path) == {}


# --------------------------------------------------------------------------- #
# canonical() + resolve_event() — aliasing, then the ambiguity refusal.         #
# --------------------------------------------------------------------------- #
def test_canonical_maps_api_spelling_to_store_spelling():
    aliases = {"usa": "United States"}
    assert canonical("USA", aliases) == "United States"
    assert canonical(" usa ", aliases) == "United States"
    assert canonical("Netherlands", aliases) == "Netherlands"


def _event(eid, home, away):
    return {"event_id": eid, "home": home, "away": away,
            "commence_time": "2022-12-03T19:00:00Z"}


def test_resolve_event_matches_through_the_alias():
    events = [_event("e1", "Netherlands", "USA")]
    got, flipped = resolve_event(events, "Netherlands", "United States",
                                 {"usa": "United States"})
    assert got["event_id"] == "e1" and flipped is False


def test_resolve_event_matches_flipped_orientation_and_reports_it():
    events = [_event("e1", "USA", "Netherlands")]
    got, flipped = resolve_event(events, "Netherlands", "United States",
                                 {"usa": "United States"})
    assert got["event_id"] == "e1" and flipped is True


def test_resolve_event_returns_none_when_absent():
    events = [_event("e1", "Brazil", "South Korea")]
    assert resolve_event(events, "Netherlands", "United States",
                         {"usa": "United States"}) == (None, None)


def test_ambiguous_match_is_an_error_never_a_pick():
    # THE V0 rule: two distinct events matching the same pair after aliasing
    # is a per-fixture ERROR. Picking the first would buy a snapshot for a
    # fixture nobody chose — and read as coverage.
    events = [_event("e1", "Netherlands", "USA"),
              _event("e2", "Netherlands", "United States")]
    with pytest.raises(AmbiguousFixtureMatch) as exc:
        resolve_event(events, "Netherlands", "United States",
                      {"usa": "United States"})
    assert "e1" in str(exc.value) and "e2" in str(exc.value)


def test_ambiguity_counts_events_not_orientations():
    # One event whose two sides collapse to the same canonical name matches
    # "straight" and "flipped" both — one EVENT, so not ambiguous.
    events = [_event("e1", "USA", "United States")]
    got, _ = resolve_event(events, "United States", "United States",
                           {"usa": "United States"})
    assert got["event_id"] == "e1"


def test_alias_is_only_applied_to_the_api_side(tmp_path):
    # The map rewrites what the API says into the STORE's vocabulary; it must
    # never rewrite the store-side fixture we are looking for (that would make
    # the alias bidirectional and match a genuinely different team).
    events = [_event("e1", "Netherlands", "United States")]
    got, _ = resolve_event(events, "Netherlands", "United States", {})
    assert got["event_id"] == "e1"
    assert resolve_event(events, "Netherlands", "USA", {}) == (None, None)


def test_alias_path_points_at_the_committed_config():
    assert ALIAS_PATH == _ROOT / "config" / "oa_aliases.yaml"
    assert json.loads(json.dumps(load_aliases()))       # plain-JSON shaped
