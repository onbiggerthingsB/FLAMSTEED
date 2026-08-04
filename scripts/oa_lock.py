#!/usr/bin/env python
"""V8 — take or verify the pre-registration lock (OA Plan 2 v2).

``--verify`` (default) walks the chain and checks every hash. ``--take``
writes the next lock version; it refuses over a dirty tracked tree, because
a lock whose ``code_commit`` does not contain the bytes it hashed attests
to nothing.

Taking a lock is the programme's point of no return: after it, the prereg
is frozen, and any change to a locked document must arrive as a NEW chained
version that is visible as such. That is the intent — the chain does not
prevent amendment, it prevents an amendment from being mistaken for what
was preregistered all along.
"""
# No `from __future__ import annotations`: loaded by PATH in tests.
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wcmodel.eval.lock import (                       # noqa: E402
    LOCK_DIR,
    LockError,
    build_lock,
    eval_inventory_from_journal,
    lock_digest,
    lock_versions,
    load_lock,
    verify_chain,
    working_tree_clean,
    write_lock,
)

JOURNAL_DEFAULT = "data/oa_acquisition_journal.jsonl"
EVAL_MANIFEST_DEFAULT = "config/oa_eval_manifest.yaml"


#: Measured 2026-08-02 on the V5 dev ledger and the 217-fixture eval design
#: (see the lock-v2 commit). Recorded so the lock fixes what a null result
#: can be said to exclude, rather than leaving it to be argued afterwards.
POWER_BLOCK = {
    "r_dev": -0.1168,
    "generation": "iid",
    "noise_sd": 0.06324,
    "n_dev": 259,
    "n_primary_design": 217,
    "mde_at_80pct_power": 0.008,
    "observed_dev_effect": -0.00504,
    "note": ("the observed development effect (0.005) is SMALLER than the "
             "MDE (0.008): power at that effect size is roughly 0.6, so a "
             "non-adoption on this design is weak evidence of no effect"),
}


def _power_block() -> dict:
    return dict(POWER_BLOCK)


#: The fitted posteriors every forecast is priced from. Gitignored, far too
#: large to track, and covered by no document hash — so before this block the
#: lock attested to the code and the inputs but not to the model states that
#: actually produced the numbers (Codex MAJOR 6).
CACHE_DIR = Path("data/cache/oa_dev")


def _cache_attestation(cache_dir: Path = CACHE_DIR) -> dict:
    """One digest over the whole posterior cache: sorted name + content hash.

    LIMITS, stated rather than implied. ``verify_chain`` does NOT re-check
    this: the cache legitimately GROWS as later work adds fits, so enforcing
    it would make every subsequent lock unverifiable. What it gives you is a
    fixed record of the cache as it stood when this version was taken — so a
    posterior swapped AFTER the fact is provable by re-hashing and comparing
    against the lock that preceded it. That is attestation, not enforcement,
    and the difference matters.
    """
    if not cache_dir.exists():
        return {}
    import hashlib
    files = sorted(p for p in cache_dir.iterdir() if p.is_file())
    digest, total = hashlib.sha256(), 0
    for path in files:
        raw = path.read_bytes()
        total += len(raw)
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(raw).digest())
    return {"posterior_cache_sha256": digest.hexdigest(),
            "posterior_cache_files": len(files),
            "posterior_cache_bytes": total,
            "posterior_cache_dir": str(cache_dir),
            "posterior_cache_note": ("attested at lock time, NOT re-verified "
                                     "by verify_chain — the cache grows with "
                                     "later fits")}


def _evidence() -> dict:
    """Digests of gitignored data artifacts no document hash covers.

    ``scored_ledger`` is the V9 issuance the verdict is computed FROM. Without
    its digest here, a published verdict names no particular ledger bytes:
    re-running the issuance and re-reading the verdict would be
    indistinguishable from reading the original. Recording it makes the
    verdict attributable to one issuance rather than to a filename.
    """
    out = {}
    for key, path in (("dev_ledger", "data/oa_dev_ledger.parquet"),
                      ("scored_ledger", "data/oa_scored_ledger.parquet"),
                      ("acquisition_journal",
                       "data/oa_acquisition_journal.jsonl")):
        p = Path(path)
        if p.exists():
            import hashlib
            out[f"{key}_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    out.update(_cache_attestation())
    return out


def _report(head) -> str:
    inv = head["scored_inventory"]
    lines = [
        f"lock v{head['version']}  (schema {head['schema']})",
        f"  taken            {head['issued_at']}",
        f"  code commit      {head['code_commit']}",
        f"  chains to        {head['prior_lock_sha256'] or '— (chain root)'}",
        f"  scored inventory {inv['n_eligible']}/{inv['n_fixtures']} eligible",
        "  documents:",
    ]
    for key, entry in sorted(head["documents"].items()):
        lines.append(f"    {key:18s} {entry['sha256'][:16]}…  {entry['path']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--take", action="store_true",
                    help="write the NEXT lock version (the point of no "
                         "return; refuses over a dirty tracked tree)")
    ap.add_argument("--lock-dir", default=str(LOCK_DIR))
    ap.add_argument("--journal", default=JOURNAL_DEFAULT)
    ap.add_argument("--eval-manifest", default=EVAL_MANIFEST_DEFAULT)
    args = ap.parse_args(argv)

    if not args.take:
        try:
            head = verify_chain(args.lock_dir)
        except LockError as exc:
            print(f"LOCK INVALID: {exc}", file=sys.stderr)
            return 1
        print("LOCK VALID\n" + _report(head))
        return 0

    if not working_tree_clean():
        print("ABORT: tracked files differ from HEAD — commit first, or the "
              "lock's code_commit would name a tree that does not contain "
              "the bytes it hashed", file=sys.stderr)
        return 1
    existing = lock_versions(args.lock_dir)
    version = (existing[-1] + 1) if existing else 1
    prior = lock_digest(load_lock(existing[-1], args.lock_dir)) \
        if existing else None
    try:
        inventory = eval_inventory_from_journal(
            args.journal, args.eval_manifest)
        bundle = build_lock(version=version, prior_lock_sha256=prior,
                            inventory=inventory,
                            power=_power_block(), evidence=_evidence())
        path = write_lock(bundle, args.lock_dir)
    except LockError as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {path}\n" + _report(bundle))
    print(f"\nlock digest: {lock_digest(bundle)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
