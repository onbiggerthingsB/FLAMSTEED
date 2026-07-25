"""Archive: recursive betting-strip, explicit selection, taint-scoped index,
release linkage. Loaded by PATH (house pattern)."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_archive.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_archive", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mk_bundle(root, cutoff):
    d = root / cutoff
    (d / "fixtures").mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps(
        {"provenance": {"as_of": cutoff, "is_synthetic": True}}))
    (d / "tournament.json").write_text(json.dumps({"data": {"Spain": {"champion": 0.15}}}))
    (d / "schedule.json").write_text(json.dumps(
        {"data": [{"home": "A", "away": "B",
                   "edge": {"entry_odds": 2.1, "staked": 5.0},
                   "forecast": {"one_x_two": {"home": 0.5}}}]}))
    (d / "track.json").write_text(json.dumps({"clv": 0.01, "roi": -0.02}))
    (d / "fixtures" / "m1.json").write_text(json.dumps(
        {"data": {"forecast": {"grid": [[1.0]]}, "edge": {"kelly": 0.1}}}))
    return d


def test_strip_betting_recursive():
    arch = _load()
    obj = {"a": {"edge": {"staked": 1}, "keep": 2}, "list": [{"odds": 3, "ok": 4}]}
    out = arch.strip_betting(obj)
    assert out == {"a": {"keep": 2}, "list": [{"ok": 4}]}


def test_assemble_projects_and_excludes_track(tmp_path):
    arch = _load()
    src, out = tmp_path / "src", tmp_path / "out"
    _mk_bundle(src, "2026-06-10T000000Z")
    manifest = arch.assemble_archive(src, out, include=["2026-06-10T000000Z"])
    sched = json.loads((out / "2026-06-10T000000Z" / "schedule.json").read_text())
    assert "edge" not in sched["data"][0] and "forecast" in sched["data"][0]
    fx = json.loads((out / "2026-06-10T000000Z" / "fixtures" / "m1.json").read_text())
    assert "edge" not in fx["data"]
    assert not (out / "2026-06-10T000000Z" / "track.json").exists()
    assert "track.json" not in manifest["bundles"]["2026-06-10T000000Z"]


def test_no_betting_key_anywhere_in_output(tmp_path):
    """The F1 scan: NO denylisted key survives anywhere in archived JSON."""
    arch = _load()
    from wcmodel.releases import BETTING_FIELD_DENYLIST
    src, out = tmp_path / "src", tmp_path / "out"
    _mk_bundle(src, "2026-06-10T000000Z")
    arch.assemble_archive(src, out, include=["2026-06-10T000000Z"])

    def keys_of(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys_of(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys_of(v)

    for f in out.rglob("*.json"):
        if f.name == "manifest.json":
            continue
        found = set(keys_of(json.loads(f.read_text()))) & BETTING_FIELD_DENYLIST
        assert not found, f"{f}: betting keys survived: {found}"


def test_explicit_selection_only(tmp_path):
    arch = _load()
    src, out = tmp_path / "src", tmp_path / "out"
    _mk_bundle(src, "2026-06-10T000000Z")
    _mk_bundle(src, "2026-06-06T193122Z")          # dev-harness bundle
    manifest = arch.assemble_archive(src, out, include=["2026-06-10T000000Z"])
    assert list(manifest["bundles"]) == ["2026-06-10T000000Z"]
    assert not (out / "2026-06-06T193122Z").exists()


def test_missing_included_bundle_fails(tmp_path):
    arch = _load()
    src = tmp_path / "src"
    _mk_bundle(src, "2026-06-10T000000Z")
    with pytest.raises(ValueError, match="not found"):
        arch.assemble_archive(src, tmp_path / "out", include=["2026-06-11T000000Z"])


def test_index_explains_taint_scope(tmp_path):
    arch = _load()
    src, out = tmp_path / "src", tmp_path / "out"
    _mk_bundle(src, "2026-06-10T000000Z")
    arch.assemble_archive(src, out, include=["2026-06-10T000000Z"])
    idx = (out / "index.html").read_text()
    assert "ODDS OVERLAY" in idx and "is_synthetic" in idx


def test_release_linkage(tmp_path):
    arch = _load()
    src, out, rel = tmp_path / "src", tmp_path / "out", tmp_path / "releases"
    _mk_bundle(src, "2026-06-10T000000Z")
    (rel / "2026-09-20").mkdir(parents=True)
    (rel / "2026-09-20" / "release.json").write_text(json.dumps({"rows": []}))
    manifest = arch.assemble_archive(src, out, include=["2026-06-10T000000Z"],
                                     releases_dir=rel)
    assert (out / "releases" / "2026-09-20" / "release.json").exists()
    assert "releases/2026-09-20/release.json" in manifest["releases"]
