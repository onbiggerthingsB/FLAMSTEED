"""Publisher bundle projection, integrity scans, and atomic replacement."""

import importlib.util
import json
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parents[2] / "scripts" / "build_publisher_bundle.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_publisher_bundle", str(_MOD))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mk(root, *, dirty_banner=True):
    (root / "fixtures").mkdir(parents=True)
    (root / "meta.json").write_text(
        json.dumps(
            {
                "provenance": {
                    "as_of": "2027-01-07T00:00:00Z",
                    "is_synthetic": True,
                    "banner": (
                        "DRY-RUN · SYNTHETIC ODDS · NOT REAL — no bet was placed"
                        if dirty_banner
                        else "clean"
                    ),
                },
                "data": {"markets": ["champion"]},
            }
        )
    )
    (root / "schedule.json").write_text(
        json.dumps(
            {
                "data": {
                    "group": [
                        {
                            "home": "A",
                            "away": "B",
                            "edge": {"staked": 1},
                            "forecast_summary": {
                                "one_x_two": {"home": 0.5},
                                "market_1x2": {"home": 0.48},
                            },
                        }
                    ],
                    "knockout": [],
                }
            }
        )
    )
    (root / "tournament.json").write_text(
        json.dumps({"data": {"A": {"champion": {"value": 1}}}})
    )
    (root / "track.json").write_text(json.dumps({"data": {"avg_clv": 0.1}}))
    (root / "value.json").write_text(json.dumps({"data": {"bettable": []}}))
    (root / "fixtures" / "A__B__2027-01-08.json").write_text(
        json.dumps(
            {
                "provenance": {
                    "is_synthetic": True,
                    "banner": "SYNTHETIC ODDS — no bet was placed",
                },
                "data": {
                    "forecast": {"one_x_two": {"home": 0.5}},
                    "edge": {"kelly": 0.1},
                }
            }
        )
    )


def test_clean_wire_format_end_to_end(tmp_path):
    module = _load()
    src, out = tmp_path / "src", tmp_path / "out"
    _mk(src)
    manifest = module.build_publisher_bundle(src, out, tournament="ac2027")
    from wcmodel.releases.projection import scan_betting_keys, scan_betting_strings

    for file_path in out.rglob("*.json"):
        data = json.loads(file_path.read_text())
        assert scan_betting_keys(data) == set(), file_path
        assert scan_betting_strings(data) == [], file_path
        if file_path.name != "publisher_manifest.json":
            provenance = data.get("provenance", {})
            assert "is_synthetic" not in provenance
    assert not (out / "track.json").exists()
    assert not (out / "value.json").exists()
    assert set(manifest["files"]) == {
        "meta.json",
        "schedule.json",
        "tournament.json",
        "fixtures/A__B__2027-01-08.json",
    }


def test_build_is_atomic_on_failure(tmp_path, monkeypatch):
    """A failing scan must leave the PREVIOUS live bundle untouched."""
    module = _load()
    src, out = tmp_path / "src", tmp_path / "out"
    _mk(src)
    module.build_publisher_bundle(src, out, tournament="ac2027")
    before = (out / "meta.json").read_text()
    monkeypatch.setattr(module, "normalize_publisher_provenance", lambda data: data)
    with pytest.raises(ValueError, match="wire scan"):
        module.build_publisher_bundle(src, out, tournament="ac2027")
    assert (out / "meta.json").read_text() == before
    assert not list(out.parent.glob("*.tmp-*"))


def test_stale_fixture_removed_by_swap(tmp_path):
    module = _load()
    src, out = tmp_path / "src", tmp_path / "out"
    _mk(src)
    module.build_publisher_bundle(src, out, tournament="ac2027")
    (src / "fixtures" / "A__B__2027-01-08.json").unlink()
    manifest = module.build_publisher_bundle(src, out, tournament="ac2027")
    assert not (out / "fixtures" / "A__B__2027-01-08.json").exists()
    assert "fixtures/A__B__2027-01-08.json" not in manifest["files"]


def test_missing_meta_fails_without_touching_live_bundle(tmp_path):
    module = _load()
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    out.mkdir()
    (out / "sentinel").write_text("live")
    with pytest.raises(ValueError, match="meta.json"):
        module.build_publisher_bundle(src, out, tournament="ac2027")
    assert (out / "sentinel").read_text() == "live"
