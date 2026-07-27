"""Project a staged dashboard bundle into an atomic publisher bundle.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/build_publisher_bundle.py \
      --src data/dashboard/2027-01-07T000000Z \
      --out publisher_bundles/ac2027 --tournament ac2027
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

from wcmodel.releases.projection import (
    normalize_publisher_provenance,
    scan_betting_keys,
    scan_betting_strings,
    strip_betting,
)

_TOP = ("meta.json", "schedule.json", "tournament.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_publisher_bundle(
    src_root: Path, out_root: Path, *, tournament: str
) -> dict:
    """Build, validate, and swap a publisher bundle into place."""
    src_root, out_root = Path(src_root), Path(out_root)
    if not (src_root / "meta.json").is_file():
        raise ValueError(f"{src_root} has no meta.json — not a staged bundle")

    tmp = out_root.with_name(f"{out_root.name}.tmp-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        sources = [src_root / name for name in _TOP if (src_root / name).is_file()]
        fixture_dir = src_root / "fixtures"
        if fixture_dir.is_dir():
            sources.extend(sorted(fixture_dir.glob("*.json")))

        for source in sources:
            data = strip_betting(json.loads(source.read_text()))
            # Real staged bundles repeat provenance on schedule, tournament,
            # and fixture envelopes, so every publisher envelope must be
            # normalized before the wire scan (not only meta.json).
            if isinstance(data.get("provenance"), dict):
                data = normalize_publisher_provenance(data)
            destination = tmp / source.relative_to(src_root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(data, indent=1))

        files: dict[str, str] = {}
        for output in sorted(tmp.rglob("*.json")):
            data = json.loads(output.read_text())
            key_hits = scan_betting_keys(data)
            if key_hits:
                raise ValueError(
                    f"key scan found {sorted(key_hits)} in "
                    f"{output.relative_to(tmp)}"
                )
            string_hits = scan_betting_strings(data)
            if string_hits:
                raise ValueError(
                    f"wire scan found banned string(s) in "
                    f"{output.relative_to(tmp)}: {string_hits!r}"
                )
            files[str(output.relative_to(tmp))] = _sha256(output)

        expected = {
            str(source.relative_to(src_root))
            for source in sources
        }
        if set(files) != expected:
            raise ValueError(
                f"manifest check failed: expected {sorted(expected)}, "
                f"found {sorted(files)}"
            )

        manifest = {"tournament": tournament, "files": files}
        (tmp / "publisher_manifest.json").write_text(
            json.dumps(manifest, indent=1)
        )

        out_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(out_root, ignore_errors=True)
        os.replace(tmp, out_root)
        return manifest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--tournament", required=True)
    args = parser.parse_args(argv)
    manifest = build_publisher_bundle(
        Path(args.src), Path(args.out), tournament=args.tournament
    )
    print(
        f"[publisher-bundle] {len(manifest['files'])} files -> "
        f"{args.out} (scans clean)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
