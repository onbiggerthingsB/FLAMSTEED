"""Orchestration tests for ``scripts/daily_update.py`` (Phase 0 §2).

The daily loop is THIN: small named step functions (so tests can monkeypatch
them with recorders) + an argparse ``main``. These tests pin the ORCHESTRATION
— step order, cutoff threading, the gate aborting before the expensive steps,
the default cutoff, the run-log line schema, the ``--dry-run`` no-op — WITHOUT
ever running a real fit/sim/network call (every heavy step is a monkeypatched
recorder). A source-level grep test pins the zero-Odds-API-credit invariant.

The module is loaded by PATH (the scan-script pattern: ``scripts/`` is not a
package on ``sys.path``), so it imports identically to how it runs.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "daily_update.py"


def _load():
    """Import scripts/daily_update.py by path (scan-script house pattern)."""
    spec = importlib.util.spec_from_file_location("daily_update", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


def _recorders(mod, monkeypatch, calls):
    """Replace every heavy step with a recorder that appends (name, cutoff) to
    ``calls`` and returns a benign sentinel — so no network/fit/sim ever runs."""
    def rec(name, ret=None):
        def _f(*args, **kwargs):
            # cutoff is threaded positionally or by kw depending on the step.
            cutoff = kwargs.get("cutoff")
            if cutoff is None:
                for a in args:
                    if isinstance(a, str) and a.endswith("Z"):
                        cutoff = a
                        break
            calls.append((name, cutoff))
            return ret
        return _f

    monkeypatch.setattr(mod, "step_ingest", rec("ingest", ret="STORE"))
    monkeypatch.setattr(mod, "step_gate", rec("gate"))
    monkeypatch.setattr(mod, "step_snapshot", rec("snapshot", ret=Path("/tmp/bundle")))
    monkeypatch.setattr(mod, "step_stage", rec("stage"))
    monkeypatch.setattr(mod, "step_provenance", rec("provenance", ret={"ok": True}))


def test_dry_run_executes_nothing(mod, monkeypatch, capsys):
    calls: list = []
    _recorders(mod, monkeypatch, calls)
    rc = mod.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert calls == []  # NONE of the real steps ran
    # The plan is printed: the resolved cutoff + the step plan.
    assert "dry-run" in out.lower()
    assert "ingest" in out and "snapshot" in out and "stage" in out
    assert "T00:00:00Z" in out  # the resolved cutoff appears


def test_step_order_and_cutoff_threading(mod, monkeypatch):
    calls: list = []
    _recorders(mod, monkeypatch, calls)
    cut = "2026-06-12T00:00:00Z"
    rc = mod.main(["--cutoff", cut])
    assert rc == 0
    names = [c[0] for c in calls]
    assert names == ["ingest", "gate", "snapshot", "stage", "provenance"]
    # Every step that takes a cutoff received the SAME one.
    threaded = {c[0]: c[1] for c in calls if c[1] is not None}
    assert threaded.get("gate") == cut
    assert threaded.get("snapshot") == cut


def test_gate_aborts_before_expensive_steps(mod, monkeypatch, capsys):
    calls: list = []
    _recorders(mod, monkeypatch, calls)

    def boom(*a, **k):
        calls.append(("gate", None))
        raise SystemExit(2)

    monkeypatch.setattr(mod, "step_gate", boom)
    with pytest.raises(SystemExit) as ei:
        mod.main(["--cutoff", "2026-06-12T00:00:00Z"])
    assert ei.value.code == 2
    names = [c[0] for c in calls]
    assert "snapshot" not in names and "stage" not in names and "provenance" not in names


def test_default_cutoff_is_today_utc_midnight(mod, monkeypatch):
    calls: list = []
    _recorders(mod, monkeypatch, calls)
    monkeypatch.setattr(mod, "_today", lambda: "2026-06-09")
    rc = mod.main([])
    assert rc == 0
    cutoffs = {c[1] for c in calls if c[1] is not None}
    assert cutoffs == {"2026-06-09T00:00:00Z"}


def test_no_odds_api_surface():
    src = _MODULE_PATH.read_text()
    assert "odds_live" not in src
    assert "THE_ODDS_API_KEY" not in src
    assert "fetch_live_odds" not in src


def test_run_log_line_schema(mod, tmp_path):
    log_path = tmp_path / "daily_update.jsonl"
    meta = {
        "provenance": {
            "as_of": "2026-06-12T00:00:00Z",
            "posterior_key": "deadbeef",
            "git": "abc1234",
            "n_sims": 20000,
        }
    }
    bundle = tmp_path / "2026-06-12T000000Z"
    bundle.mkdir()
    (bundle / "meta.json").write_text(json.dumps(meta))

    rec = mod.step_provenance(bundle, log_path=log_path, duration_s=1.5)
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    for k in ("ts", "cutoff", "bundle", "posterior_key", "git", "n_sims", "duration_s"):
        assert k in row, f"missing {k} in run-log line"
    assert row["posterior_key"] == "deadbeef"
    assert row["n_sims"] == 20000
    assert row["cutoff"] == "2026-06-12T00:00:00Z"
    # The returned dict mirrors the appended line (caller can print a summary).
    assert rec["posterior_key"] == "deadbeef"
