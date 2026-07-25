# scripts/build_archive.py
"""Assemble the public point-in-time forecast archive.

Content-level projection (NOT a path denylist): every JSON is parsed and every
key in BETTING_FIELD_DENYLIST is removed recursively; track.json (CLV/ROI
territory wholesale) never ships. Selection is EXPLICIT via --include: dev/test
bundles are excluded because they are never listed, not because a heuristic
guessed. index.html states the is_synthetic scope: it taints the ORIGINAL
bundle's odds overlay, never the forecast probabilities — and the odds fields
are stripped from this archive anyway.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/build_archive.py \
      --src data/dashboard --out archive_site/ \
      --include 2026-06-10T000000Z --include 2026-06-12T000000Z \
      --releases releases/
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
from pathlib import Path

from wcmodel.releases import BETTING_FIELD_DENYLIST

_EXCLUDE_FILES = {"track.json"}
_RESERVED_NAMES = {"releases", "manifest.json", "index.html"}
HASH_SEMANTICS = ("sha256 of archived (projected) file bytes — "
                  "not source-bundle bytes")
TAINT_SCOPE = ("is_synthetic marks the ODDS OVERLAY of the original dashboard "
               "bundle (synthetic odds, no bets); the forecast probabilities "
               "archived here are real model output. Betting/edge fields have "
               "been removed from this archive.")


def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       text=True, timeout=5).strip()
    except Exception:
        return "unknown"


def _keys_of(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys_of(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys_of(v)


def _assert_under(out_root: Path, dest: Path) -> Path:
    """Belt-and-braces: every write destination must resolve under out_root."""
    try:
        dest.resolve().relative_to(out_root.resolve())
    except ValueError:
        raise ValueError(f"write destination escapes out_root: {dest}")
    return dest


def strip_betting(obj):
    if isinstance(obj, dict):
        return {k: strip_betting(v) for k, v in obj.items()
                if k not in BETTING_FIELD_DENYLIST}
    if isinstance(obj, list):
        return [strip_betting(v) for v in obj]
    return obj


def assemble_archive(src_root: Path, out_root: Path, include: list[str],
                     releases_dir: Path | None = None) -> dict:
    src_root, out_root = Path(src_root), Path(out_root)
    if not include:
        raise ValueError("no bundles selected — pass explicit --include names")
    for n in include:
        if "/" in n or "\\" in n or ".." in n:
            raise ValueError(f"invalid bundle name (path traversal): {n!r}")
        if n in _RESERVED_NAMES:
            raise ValueError(f"reserved name — cannot include {n!r}")
    missing = [n for n in include if not (src_root / n).is_dir()]
    if missing:
        raise ValueError(f"included bundle(s) not found under {src_root}: {missing}")

    manifest = {"generated_from_git": _git_rev(), "taint_scope": TAINT_SCOPE,
                "hash_semantics": HASH_SEMANTICS, "bundles": {}, "releases": []}
    synthetic_flags = {}
    for name in include:
        b = src_root / name
        if not (b / "meta.json").exists():
            raise ValueError(f"bundle {name} has no meta.json — refusing to archive")
        meta = json.loads((b / "meta.json").read_text())
        prov = meta.get("provenance")
        if not isinstance(prov, dict) or "is_synthetic" not in prov:
            raise ValueError(f"bundle {name} has no provenance (is_synthetic) — "
                             "refusing to archive")
        synthetic_flags[name] = bool(prov["is_synthetic"])
        # Non-JSON files are not expected in a bundle and are NEVER projected;
        # refuse loudly rather than silently skipping an unvetted leak vector.
        stray = sorted(str(f.relative_to(b)) for f in b.rglob("*")
                       if f.is_file() and f.suffix != ".json")
        if stray:
            raise ValueError(
                f"bundle {name} contains non-JSON file(s) {stray} — "
                "not expected, refusing to archive")
        files = {}
        for f in sorted(b.rglob("*.json")):
            rel = f.relative_to(b)
            if rel.name in _EXCLUDE_FILES:
                continue
            data = strip_betting(json.loads(f.read_text()))
            dest = _assert_under(out_root, out_root / name / rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(data, indent=1)
            dest.write_text(text)
            files[str(rel)] = hashlib.sha256(text.encode()).hexdigest()
        manifest["bundles"][name] = files

    if releases_dir is not None:
        for rj in sorted(Path(releases_dir).glob("*/release.json")):
            try:
                rdata = json.loads(rj.read_text())
            except json.JSONDecodeError as e:
                raise ValueError(f"corrupt release {rj}: {e}") from e
            found = set(_keys_of(rdata)) & BETTING_FIELD_DENYLIST
            if found:
                # Do NOT silently strip: releases are gated at build time
                # (wcmodel.releases.build); a betting key HERE means that gate
                # was bypassed — suspected bug, refuse loudly.
                raise ValueError(
                    f"release {rj} contains betting key(s) {sorted(found)} — "
                    "upstream gate bypassed, suspected bug; refusing to link")
            rel_path = Path("releases") / rj.parent.name / rj.name
            dest = _assert_under(out_root, out_root / rel_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(rdata, indent=1)
            dest.write_text(text)
            manifest["releases"].append(
                {"path": str(rel_path),
                 "sha256": hashlib.sha256(text.encode()).hexdigest()})

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=1))
    items = "".join(
        f"<li><a href='{html.escape(c, quote=True)}/meta.json'>{html.escape(c)}"
        f"</a> — is_synthetic={str(synthetic_flags[c]).lower()}</li>"
        for c in include)
    rel_items = "".join(
        f"<li><a href='{html.escape(e['path'], quote=True)}'>"
        f"{html.escape(e['path'])}</a></li>" for e in manifest["releases"])
    (out_root / "index.html").write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Point-in-time forecast archive</title></head><body>"
        "<h1>Point-in-time forecast archive</h1>"
        "<p>Each bundle is the forecast as it stood at that cutoff — data "
        f"strictly before the timestamp. Note on flags: {TAINT_SCOPE} "
        f"Integrity: manifest.json ({HASH_SEMANTICS}, per file). "
        "Built from code rev "
        f"{manifest['generated_from_git']}.</p>"
        f"<ul>{items}</ul>"
        + (f"<h2>Forecast releases</h2><ul>{rel_items}</ul>" if rel_items else "")
        + "</body></html>")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="data/dashboard")
    ap.add_argument("--out", required=True)
    ap.add_argument("--include", action="append", default=[])
    ap.add_argument("--releases", default=None)
    args = ap.parse_args(argv)
    manifest = assemble_archive(
        Path(args.src), Path(args.out), include=args.include,
        releases_dir=Path(args.releases) if args.releases else None)
    n = sum(len(v) for v in manifest["bundles"].values())
    print(f"[archive] {len(manifest['bundles'])} bundles, {n} files, "
          f"{len(manifest['releases'])} releases -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
