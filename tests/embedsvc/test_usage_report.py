"""Monthly publisher usage aggregation and durable report artifacts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


_MOD = Path(__file__).resolve().parents[2] / "scripts" / "publisher_usage_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("publisher_usage_report", str(_MOD))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_summarize_and_write(tmp_path: Path):
    module = _load()
    meter = tmp_path / "meter.jsonl"
    rows = (
        [{"day": "2027-01-05", "pid": "gulfnews", "path_class": "bundle"}] * 3
        + [{"day": "2027-01-06", "pid": "gulfnews", "path_class": "fixture"}]
        + [{"day": "2027-01-06", "pid": "diaspo", "path_class": "token"}]
        + [{"day": "2027-02-01", "pid": "gulfnews", "path_class": "bundle"}]
    )
    meter.write_text("\n".join(json.dumps(row) for row in rows) + "\nnot json\n")
    summary = module.summarize(meter, "2027-01")
    assert summary["gulfnews"] == {
        "token": 0,
        "bundle": 3,
        "fixture": 1,
        "days_active": 2,
    }
    assert summary["diaspo"]["token"] == 1
    assert summary["_meta"]["skipped_lines"] == 1
    output = module.write_report(summary, "2027-01", tmp_path)
    assert output == tmp_path / "usage-2027-01.md"
    assert output.exists()
    assert "gulfnews" in (tmp_path / "usage-2027-01.csv").read_text()
    assert "Skipped malformed lines: 1" in output.read_text()


def test_wrong_shape_and_unknown_path_class_are_counted_as_malformed(tmp_path: Path):
    module = _load()
    meter = tmp_path / "meter.jsonl"
    meter.write_text(
        json.dumps({"day": "2027-01-01", "pid": "p", "path_class": "unknown"})
        + "\n"
        + json.dumps(["not", "an", "object"])
        + "\n"
    )
    assert module.summarize(meter, "2027-01") == {"_meta": {"skipped_lines": 2}}


def test_status_page_never_uses_markup_interpolation():
    html = Path("src/wcmodel/embedsvc/status.html").read_text()
    assert "innerHTML" not in html
    assert "document.createElement" in html
    assert "textContent" in html
