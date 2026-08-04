"""Tests for the V8 pre-registration lock.

The lock's whole value is that it turns "nothing was chosen after outcomes
were seen" from an assurance into a checkable statement. So the tests are
mostly about REFUSAL: a mutated document, a broken chain link, a forged
digest, a missing version — each must be caught, because a lock that
verifies a tampered state is worse than no lock at all.
"""
import json
from pathlib import Path

import pytest

from wcmodel.eval.lock import (
    LOCK_SCHEMA,
    LockError,
    build_lock,
    eval_inventory_from_journal,
    lock_digest,
    lock_versions,
    load_lock,
    require_lock,
    serialize,
    verify_chain,
    write_lock,
)


@pytest.fixture
def docs(tmp_path, monkeypatch):
    """Stand-in files for EVERY locked key.

    The verifier now requires exactly ``LOCKED_DOCUMENTS`` (B4), so the
    tests patch that constant to this stand-in mapping rather than
    exercising a subset — which is the very shape the fix rejects.
    """
    import wcmodel.eval.lock as lock_mod

    mapping = {}
    for name in lock_mod.LOCKED_DOCUMENTS:
        p = tmp_path / f"{name}.txt"
        p.write_text(f"contents of {name}\n")
        mapping[name] = str(p)
    monkeypatch.setattr(lock_mod, "LOCKED_DOCUMENTS", mapping)
    return mapping


def _inventory(n=3, eligible=True):
    return [{"fixture_id": f"f{i}", "pool": "wc2022", "date": "2022-11-21",
             "home": "A", "away": "B", "eligible": eligible,
             **({"cut_raw_sha256": f"d{i}"} if eligible
                else {"reason": "no quote"})}
            for i in range(n)]


def _write_v1(tmp_path, docs, **kw):
    bundle = build_lock(version=1, prior_lock_sha256=None,
                        inventory=_inventory(), documents=docs,
                        code_commit="abc123", issued_at="2026-08-02T00:00:00Z",
                        **kw)
    write_lock(bundle, tmp_path / "lock")
    return bundle


# ------------------------------------------------------------- happy path
def test_v1_writes_and_verifies(tmp_path, docs):
    bundle = _write_v1(tmp_path, docs)
    assert bundle["schema"] == LOCK_SCHEMA and bundle["version"] == 1
    head = verify_chain(tmp_path / "lock")
    assert head["version"] == 1
    assert head["scored_inventory"]["n_eligible"] == 3


def test_digest_is_content_not_formatting(tmp_path, docs):
    bundle = _write_v1(tmp_path, docs)
    reordered = json.loads(json.dumps(dict(reversed(list(bundle.items())))))
    assert lock_digest(reordered) == lock_digest(bundle)


def test_sidecar_records_the_bundle_digest(tmp_path, docs):
    bundle = _write_v1(tmp_path, docs)
    sidecar = (tmp_path / "lock" / "lock-v1.sha256").read_text().strip()
    assert sidecar == lock_digest(bundle)


def test_a_lock_is_written_once(tmp_path, docs):
    _write_v1(tmp_path, docs)
    again = build_lock(version=1, prior_lock_sha256=None,
                       inventory=_inventory(), documents=docs,
                       code_commit="abc123",
                       issued_at="2026-08-02T00:00:00Z")
    with pytest.raises(LockError, match="written ONCE"):
        write_lock(again, tmp_path / "lock")


# ----------------------------------------------------------- the refusals
def test_mutating_a_locked_document_is_caught(tmp_path, docs):
    _write_v1(tmp_path, docs)
    Path(docs["prereg"]).write_text("the prereg, quietly edited\n")
    with pytest.raises(LockError, match="have changed since the lock"):
        verify_chain(tmp_path / "lock")


def test_deleting_a_locked_document_is_caught(tmp_path, docs):
    _write_v1(tmp_path, docs)
    Path(docs["selection_trace"]).unlink()
    with pytest.raises(LockError, match="MISSING"):
        verify_chain(tmp_path / "lock")


def test_tampering_with_the_bundle_is_caught_by_its_sidecar(tmp_path, docs):
    _write_v1(tmp_path, docs)
    path = tmp_path / "lock" / "lock-v1.json"
    bundle = json.loads(path.read_text())
    bundle["code_commit"] = "deadbeef"          # rewrite history
    path.write_text(serialize(bundle))
    with pytest.raises(LockError, match="disagrees with the bundle"):
        verify_chain(tmp_path / "lock")


def test_no_chain_at_all_refuses(tmp_path):
    with pytest.raises(LockError, match="no lock chain"):
        require_lock(tmp_path / "lock")


def test_a_gap_in_the_chain_refuses(tmp_path, docs):
    v1 = _write_v1(tmp_path, docs)
    v3 = build_lock(version=3, prior_lock_sha256=lock_digest(v1),
                    inventory=_inventory(), documents=docs,
                    code_commit="abc123", issued_at="2026-08-02T00:00:00Z")
    write_lock(v3, tmp_path / "lock")
    with pytest.raises(LockError, match="gaps"):
        verify_chain(tmp_path / "lock")


def test_a_broken_link_refuses(tmp_path, docs):
    _write_v1(tmp_path, docs)
    v2 = build_lock(version=2, prior_lock_sha256="0" * 64,   # wrong prior
                    inventory=_inventory(), documents=docs,
                    code_commit="abc123", issued_at="2026-08-02T00:00:00Z")
    write_lock(v2, tmp_path / "lock")
    with pytest.raises(LockError, match="chain is broken"):
        verify_chain(tmp_path / "lock")


def test_v1_may_not_claim_a_prior(docs):
    with pytest.raises(LockError, match="chain root"):
        build_lock(version=1, prior_lock_sha256="x" * 64,
                   inventory=_inventory(), documents=docs)


def test_an_amendment_must_chain(docs):
    with pytest.raises(LockError, match="does not chain"):
        build_lock(version=2, prior_lock_sha256=None,
                   inventory=_inventory(), documents=docs)


def test_a_missing_locked_input_refuses_at_build(tmp_path, docs):
    docs = {**docs, "ghost": str(tmp_path / "not-here.md")}
    with pytest.raises(LockError, match="does not exist"):
        build_lock(version=1, prior_lock_sha256=None,
                   inventory=_inventory(), documents=docs)


def test_a_bundle_may_not_choose_which_inputs_it_binds(tmp_path, docs):
    """B4: the verifier requires EXACTLY the declared set — a bundle that
    drops inputs (in the limit, all of them) must not verify."""
    bundle = build_lock(version=1, prior_lock_sha256=None,
                        inventory=_inventory(), documents=docs,
                        code_commit="abc123",
                        issued_at="2026-08-02T00:00:00Z")
    bundle["documents"] = {}                       # bind nothing at all
    path = tmp_path / "lock"
    path.mkdir()
    (path / "lock-v1.json").write_text(serialize(bundle))
    with pytest.raises(LockError, match="may not choose which inputs"):
        verify_chain(path)


# ------------------------------------------------------------- amendments
def test_a_correctly_chained_amendment_verifies(tmp_path, docs):
    v1 = _write_v1(tmp_path, docs)
    Path(docs["prereg"]).write_text("the prereg, amended in the open\n")
    v2 = build_lock(version=2, prior_lock_sha256=lock_digest(v1),
                    inventory=_inventory(), documents=docs,
                    code_commit="def456", issued_at="2026-08-03T00:00:00Z")
    write_lock(v2, tmp_path / "lock")
    head = verify_chain(tmp_path / "lock")
    assert head["version"] == 2
    assert lock_versions(tmp_path / "lock") == [1, 2]
    # v1 remains readable and still describes the ORIGINAL bytes: a forecast
    # issued under it stays attributable to it
    assert load_lock(1, tmp_path / "lock")["documents"]["prereg"]["sha256"] \
        != head["documents"]["prereg"]["sha256"]


# -------------------------------------------------- inventory from journal
def test_inventory_records_ineligibility_with_its_reason(tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text("\n".join(json.dumps(r) for r in [
        {"type": "receipt", "gate": "ga", "kind": "snapshot", "tag": "cut",
         "fixture_id": "f0", "raw_sha256": "a" * 64},
        {"type": "receipt", "gate": "ga", "kind": "snapshot", "tag": "cut",
         "fixture_id": "f1", "raw_sha256": None, "error": "404 not found"},
        # a T-24h receipt must NOT be mistaken for the cut
        {"type": "receipt", "gate": "ga", "kind": "snapshot", "tag": "T-24h",
         "fixture_id": "f2", "raw_sha256": "b" * 64},
    ]) + "\n")
    manifest = tmp_path / "m.yaml"
    manifest.write_text(
        "fixtures:\n"
        + "".join(f"- fixture_id: f{i}\n  pool: wc2022\n  date: '2022-11-21'\n"
                  f"  home: A\n  away: B\n" for i in range(3)))
    inv = eval_inventory_from_journal(journal, manifest)
    by_id = {r["fixture_id"]: r for r in inv}
    assert by_id["f0"]["eligible"] and by_id["f0"]["cut_raw_sha256"] == "a" * 64
    assert not by_id["f1"]["eligible"] and "404" in by_id["f1"]["reason"]
    # f2 has only a T-24h receipt -> no cut -> ineligible WITH a reason
    assert not by_id["f2"]["eligible"] and by_id["f2"]["reason"]


def test_inventory_covers_every_manifest_fixture(tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text("")
    manifest = tmp_path / "m.yaml"
    manifest.write_text(
        "fixtures:\n- fixture_id: f0\n  pool: wc2022\n  date: '2022-11-21'\n"
        "  home: A\n  away: B\n")
    inv = eval_inventory_from_journal(journal, manifest)
    assert len(inv) == 1 and inv[0]["eligible"] is False
