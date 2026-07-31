"""Odds-API -> store team-name aliases, and the fixture matcher that uses them.

The map (``config/oa_aliases.yaml``) is evidence-bound: every record cites the
sha256 of an archived raw response that contains the API spelling it claims
(OA Plan 2 v2, V0 / Codex finding 14). This module loads and VALIDATES that
file, and resolves a store-spelled fixture against a discovery listing —
refusing, never guessing, when more than one event matches.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

# aliases.py lives at src/wcmodel/eval/ -> the repo root (which holds config/)
# is parents[3]; the consumers are scripts and a WSGI app, none of which owns
# the cwd (same idiom as eval/regulation.py).
ALIAS_PATH = Path(__file__).resolve().parents[3] / "config" / "oa_aliases.yaml"

_REQUIRED = ("api_name", "store_name", "evidence_sha256")
_HEX = set("0123456789abcdef")


class AliasError(ValueError):
    """The alias file is malformed — refuse to half-load it."""


class AmbiguousFixtureMatch(ValueError):
    """Two or more distinct events match one fixture after aliasing.

    Never resolved by picking: the V0 rule makes this a per-fixture ERROR,
    because a pick buys a paid snapshot for a fixture nobody chose and then
    reports it as coverage."""


def _norm(name: str) -> str:
    """The matcher's key: casefolded and stripped. Whitespace and case are the
    only differences we absorb silently — anything else needs an evidenced
    alias."""
    return str(name).casefold().strip()


def _validate(record, path: Path) -> dict:
    if not isinstance(record, dict):
        raise AliasError(f"{path}: each alias must be a mapping; got {record!r}")
    for field in _REQUIRED:
        if field not in record:
            raise AliasError(f"{path}: alias record missing {field}: {record!r}")
        if not isinstance(record[field], str) or not record[field].strip():
            raise AliasError(
                f"{path}: {field} must be a non-empty string (empty/blank "
                f"names match nothing and hide the typo): {record!r}")
    digest = record["evidence_sha256"]
    if len(digest) != 64 or not set(digest) <= _HEX:
        raise AliasError(
            f"{path}: evidence_sha256 must be a FULL 64-hex sha256 — a "
            "truncated digest cannot be re-verified against the "
            f"content-addressed archive: {digest!r}")
    if _norm(record["api_name"]) == _norm(record["store_name"]):
        raise AliasError(
            f"{path}: {record['api_name']!r} aliases itself — a no-op record "
            "that reads like evidence of a real spelling difference")
    return record


def load_alias_records(path: Path = ALIAS_PATH) -> list:
    """The validated records, provenance included. ``load_aliases`` builds the
    matcher's dict from these; the evidence checker needs the digests."""
    doc = yaml.safe_load(path.read_text()) or {}
    records = doc.get("aliases")
    if records is None:
        raise AliasError(f"{path}: missing top-level 'aliases' key")
    if not isinstance(records, list):
        raise AliasError(f"{path}: 'aliases' must be a list; got {type(records)}")
    validated = [_validate(r, path) for r in records]
    seen = {}
    for record in validated:
        key = _norm(record["api_name"])
        if key in seen:
            raise AliasError(
                f"{path}: duplicate api_name {record['api_name']!r} (matching "
                "is case-insensitive, so two records silently let the last "
                "one win)")
        seen[key] = record["store_name"]
    # One hop only: A -> B and B -> C would make the result depend on how many
    # times the map is applied, which is not a property a frozen artifact may
    # have.
    for record in validated:
        if _norm(record["store_name"]) in seen:
            raise AliasError(
                f"{path}: alias chain {record['api_name']!r} -> "
                f"{record['store_name']!r} -> "
                f"{seen[_norm(record['store_name'])]!r}; aliases are one hop")
    return validated


def load_aliases(path: Path = ALIAS_PATH) -> dict:
    """``{normalized api spelling: store spelling}`` — the matcher's map."""
    return {_norm(r["api_name"]): r["store_name"]
            for r in load_alias_records(path)}


def verify_alias_evidence(records=None, *, raw_dir, path: Path = ALIAS_PATH):
    """Re-read the cited archived bytes; return a list of problem strings (empty
    == every alias is evidenced).

    THIS is the evidence rule made mechanical: a record whose archived payload
    never contains the claimed API spelling is an alias with a footnote, not an
    alias with evidence. The archive is gitignored, so callers skip this where
    it is absent — but never treat "absent" as "verified"."""
    records = load_alias_records(path) if records is None else records
    problems = []
    for record in records:
        digest = record["evidence_sha256"]
        blob = Path(raw_dir) / f"{digest}.json"
        if not blob.exists():
            problems.append(
                f"{record['api_name']!r}: cited evidence {digest} is not in "
                f"the archive {raw_dir}")
            continue
        # Substring over the RAW json text: the spelling may sit in any field
        # (home_team, away_team, an outcome name), and the point is only that
        # these exact bytes contain it. json.dumps of the parsed payload would
        # re-encode escapes; the stored text is what was archived.
        text = blob.read_text()
        needle = json.dumps(record["api_name"])[1:-1]   # json-escaped, unquoted
        if needle not in text:
            problems.append(
                f"{record['api_name']!r}: not present in the archived payload "
                f"{digest} it cites — unevidenced alias")
    return problems


def canonical(name: str, aliases: dict) -> str:
    """The store spelling of an API-side ``name``. Unaliased names pass through
    stripped (never casefolded: the output is a display/join value)."""
    key = _norm(name)
    return aliases.get(key, str(name).strip())


def resolve_event(events, home: str, away: str, aliases: dict):
    """Find the store-spelled fixture ``home`` v ``away`` among discovered
    ``events``.

    Returns ``(event, flipped)`` — ``flipped`` True when the listing carries the
    pair in the opposite orientation (neutral-venue sources disagree, so this is
    a match, but a reported one) — or ``(None, None)`` when absent. Raises
    ``AmbiguousFixtureMatch`` when two or more DISTINCT events match: one event
    matching both orientations (a degenerate same-name pair) is one match, not
    two.

    Aliases are applied to the EVENT side only: the map translates the API's
    vocabulary into the store's, and applying it to the fixture we are looking
    for would make it bidirectional and match a genuinely different team."""
    want = (_norm(home), _norm(away))
    matches = []
    for event in events:
        got = (_norm(canonical(event.get("home") or "", aliases)),
               _norm(canonical(event.get("away") or "", aliases)))
        if got == want:
            matches.append((event, False))
        elif got == (want[1], want[0]):
            matches.append((event, True))
    if not matches:
        return None, None
    ids = {event.get("event_id") or event.get("id") for event, _ in matches}
    if len(ids) > 1:
        raise AmbiguousFixtureMatch(
            f"{home} v {away}: {len(ids)} distinct events match after aliasing "
            f"({', '.join(sorted(str(i) for i in ids))}) — a per-fixture error, "
            "never a pick")
    return matches[0]
