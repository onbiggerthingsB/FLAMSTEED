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
                            inventory=inventory)
        path = write_lock(bundle, args.lock_dir)
    except LockError as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {path}\n" + _report(bundle))
    print(f"\nlock digest: {lock_digest(bundle)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
