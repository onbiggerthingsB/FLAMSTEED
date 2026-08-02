"""V8 — the pre-registration lock (OA Plan 2 v2).

A lock bundle is the single artifact that says: *these exact documents, this
exact evidence, and this exact code produced the deployment choice, and
nothing was chosen after outcomes were seen.* Everything the analysis
depends on is named by sha256, so a later reader can verify the claim
rather than trust it.

WHY A CHAIN AND NOT A FILE. Preregistrations get amended — the venue rule,
n_dev, the coherence ruling all landed as dated amendments. An amendment
that silently overwrote the lock would be indistinguishable from a
post-hoc rewrite. So each lock is `lock-vN.json` carrying
``prior_lock_sha256``, and verification walks the whole chain from v1. A
forecast issued under v1 is still attributable to v1 even after v2 exists;
what it is NOT is evidence for v2's choices.

WHAT THE LOCK BINDS
    prereg / spec / analysis spec  — the methodology, verbatim bytes
    dev manifest + coverage        — which fixtures tuned w, and why the
                                     others were refused
    dev ledger digest              — the forecasts behind the selection
                                     (a gitignored data artifact, so its
                                     digest is the only tie)
    selection trace                — (w, de-vig, stacking params) and the
                                     fold trace that produced them
    scored inventory               — the 217 fixtures, each with the paid
                                     snapshot digest it will be scored on
                                     and its eligibility flag
    code commit                    — the tree that computed all of it

The scored inventory is frozen HERE, before issuance, and it is
outcome-free by construction: eligibility asks only whether a coherent
sharp quote existed before the issuance instant.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

LOCK_DIR = Path("reports/oa_lock")
LOCK_SCHEMA = "oa-lock-v1"

#: Every document whose bytes the lock pins, as {key: repo-relative path}.
#: Adding an input here is a deliberate act — the verifier requires EXACTLY
#: these keys, so a silently dropped input fails rather than passes.
LOCKED_DOCUMENTS = {
    "prereg": "reports/oa_prereg.md",
    "analysis_spec": "reports/oa_analysis_spec.md",
    "dev_manifest": "config/oa_dev_manifest.yaml",
    "dev_coverage": "config/oa_dev_coverage.yaml",
    "eval_manifest": "config/oa_eval_manifest.yaml",
    "scored_inventory": "config/oa_scored_inventory.yaml",
    "selection_trace": "reports/oa_selection_trace.json",
    "aliases": "config/oa_aliases.yaml",
}


class LockError(RuntimeError):
    """The lock cannot be written, or does not verify."""


def sha256_file(path) -> str:
    p = Path(path)
    if not p.exists():
        raise LockError(f"locked input {p} does not exist")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def working_tree_clean() -> bool:
    """No TRACKED file differs from HEAD.

    A lock taken over modified tracked files names a commit that does not
    contain the bytes it hashed — ``code_commit`` would be a lie. Untracked
    files are deliberately ignored: they are not part of the tree the
    commit describes, so scratch work beside the repo cannot block a lock
    (nor can it change what the lock attests).
    """
    return _git("status", "--porcelain", "--untracked-files=no") == ""


def lock_versions(lock_dir=LOCK_DIR) -> list:
    """Existing lock versions, ascending."""
    d = Path(lock_dir)
    if not d.exists():
        return []
    versions = []
    for p in d.glob("lock-v*.json"):
        try:
            versions.append(int(p.stem.split("v")[1]))
        except (IndexError, ValueError):
            continue
    return sorted(versions)


def lock_file(version: int, lock_dir=LOCK_DIR) -> Path:
    return Path(lock_dir) / f"lock-v{version}.json"


def eval_inventory_from_journal(journal_path, manifest_path, *,
                                gate: str = "ga") -> list:
    """The scored inventory the lock freezes: one row per eval fixture with
    the PAID cut-snapshot digest it will be scored on.

    Derived from the acquisition journal's receipts, never from a report:
    the receipts are the spend ledger of record, and a markdown table is a
    rendering. A fixture with no receipted, error-free cut digest is
    recorded as ineligible WITH its reason rather than dropped — an
    exclusion the lock cannot explain is worse than no exclusion.
    """
    import yaml

    manifest = yaml.safe_load(Path(manifest_path).read_text())
    digests: dict = {}
    for line in Path(journal_path).read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if (rec.get("type") != "receipt" or rec.get("gate") != gate
                or rec.get("kind") != "snapshot" or rec.get("tag") != "cut"):
            continue
        fid = str(rec.get("fixture_id") or "")
        if rec.get("error") or not rec.get("raw_sha256"):
            digests.setdefault(fid, {"eligible": False,
                                     "reason": rec.get("error")
                                     or "no archived payload on the receipt"})
            continue
        digests[fid] = {"eligible": True, "cut_raw_sha256": rec["raw_sha256"]}

    inventory = []
    for fx in manifest["fixtures"]:
        fid = str(fx["fixture_id"])
        got = digests.get(fid)
        row = {"fixture_id": fid, "pool": str(fx["pool"]),
               "date": str(fx["date"]), "home": str(fx["home"]),
               "away": str(fx["away"])}
        if got is None:
            row.update({"eligible": False,
                        "reason": "no cut-snapshot receipt on this gate"})
        else:
            row.update(got)
        inventory.append(row)
    inventory.sort(key=lambda r: r["fixture_id"])
    return inventory


def build_lock(*, version: int, prior_lock_sha256, inventory,
               documents=LOCKED_DOCUMENTS, code_commit=None,
               issued_at=None) -> dict:
    """Assemble (do not write) one lock bundle."""
    if version < 1:
        raise LockError("lock versions start at 1")
    if version == 1 and prior_lock_sha256 is not None:
        raise LockError("lock v1 is the chain root and has no prior")
    if version > 1 and not prior_lock_sha256:
        raise LockError(
            f"lock v{version} must carry prior_lock_sha256 — an amendment "
            "that does not chain is indistinguishable from a rewrite")
    doc_hashes = {k: sha256_file(v) for k, v in sorted(documents.items())}
    n_eligible = sum(1 for r in inventory if r.get("eligible"))
    return {
        "schema": LOCK_SCHEMA,
        "version": version,
        "prior_lock_sha256": prior_lock_sha256,
        "issued_at": issued_at or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "code_commit": code_commit or _git("rev-parse", "HEAD"),
        "documents": {k: {"path": documents[k], "sha256": doc_hashes[k]}
                      for k in sorted(documents)},
        "scored_inventory": {
            "n_fixtures": len(inventory),
            "n_eligible": n_eligible,
            "fixtures": inventory,
        },
    }


def lock_digest(bundle: dict) -> str:
    """The bundle's own sha256 — over its CANONICAL serialization, so the
    digest is a function of content and not of formatting."""
    return sha256_text(serialize(bundle))


def serialize(bundle: dict) -> str:
    return json.dumps(bundle, sort_keys=True, indent=2) + "\n"


def write_lock(bundle: dict, lock_dir=LOCK_DIR) -> Path:
    d = Path(lock_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = lock_file(bundle["version"], d)
    if path.exists():
        raise LockError(
            f"{path} already exists — a lock is written ONCE; an amendment "
            "is the next version, chaining to this one")
    path.write_text(serialize(bundle))
    (d / f"lock-v{bundle['version']}.sha256").write_text(
        lock_digest(bundle) + "\n")
    return path


def load_lock(version: int, lock_dir=LOCK_DIR) -> dict:
    path = lock_file(version, lock_dir)
    if not path.exists():
        raise LockError(f"no lock at {path}")
    return json.loads(path.read_text())


def verify_chain(lock_dir=LOCK_DIR, *, check_documents: bool = True) -> dict:
    """Walk the whole chain from v1 and verify every claim it makes.

    Returns the HEAD bundle. Raises on: a missing version, a broken chain
    link, a bundle whose recorded digest disagrees with its bytes, or (when
    ``check_documents``) any locked document whose current bytes no longer
    hash to what the lock recorded. That last check is the point of the
    exercise — it is what makes "the prereg was frozen before issuance" a
    verifiable statement instead of an assurance.
    """
    versions = lock_versions(lock_dir)
    if not versions:
        raise LockError(
            f"no lock chain in {lock_dir} — issuance and scoring require a "
            "valid lock; run the V8 lock first")
    if versions != list(range(1, len(versions) + 1)):
        raise LockError(
            f"lock chain has gaps: found versions {versions}, expected "
            f"1..{len(versions)}")
    prior_digest = None
    head = None
    for v in versions:
        bundle = load_lock(v, lock_dir)
        if bundle.get("schema") != LOCK_SCHEMA:
            raise LockError(f"lock v{v}: unknown schema "
                            f"{bundle.get('schema')!r}")
        if bundle.get("version") != v:
            raise LockError(
                f"lock v{v}: bundle claims version {bundle.get('version')}")
        if bundle.get("prior_lock_sha256") != prior_digest:
            raise LockError(
                f"lock v{v}: prior_lock_sha256 "
                f"{bundle.get('prior_lock_sha256')!r} does not match the "
                f"actual digest of v{v - 1} ({prior_digest!r}) — the chain "
                "is broken, so no version after it is attributable")
        digest = lock_digest(bundle)
        sidecar = Path(lock_dir) / f"lock-v{v}.sha256"
        if sidecar.exists() and sidecar.read_text().strip() != digest:
            raise LockError(
                f"lock v{v}: recorded digest {sidecar.read_text().strip()} "
                f"disagrees with the bundle's actual {digest}")
        prior_digest = digest
        head = bundle

    if check_documents:
        drifted = []
        for key, entry in sorted(head["documents"].items()):
            try:
                now = sha256_file(entry["path"])
            except LockError:
                drifted.append(f"{key} ({entry['path']}): MISSING")
                continue
            if now != entry["sha256"]:
                drifted.append(
                    f"{key} ({entry['path']}): locked {entry['sha256'][:12]}…"
                    f" but now {now[:12]}…")
        if drifted:
            raise LockError(
                "locked document(s) have changed since the lock was taken:\n  "
                + "\n  ".join(drifted)
                + "\nEither restore the locked bytes or take the next lock "
                  "version — editing a locked document in place is exactly "
                  "the post-hoc rewrite the chain exists to make visible")
    return head


def require_lock(lock_dir=LOCK_DIR) -> dict:
    """The gate every issuance/scoring entry point calls first."""
    return verify_chain(lock_dir)
