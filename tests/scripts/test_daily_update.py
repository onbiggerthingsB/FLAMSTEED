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


# --------------------------------------------------------------------------- #
# `--latest` flag: resolve the freshest martj42 master commit via ONE GitHub  #
# API call and thread it (as a runtime override) into the ingest fetch path.  #
# All monkeypatched — NO network, NO data/ dependency.                        #
# --------------------------------------------------------------------------- #
def _recorders_capturing_commit(mod, monkeypatch, calls):
    """Like ``_recorders`` but ``step_ingest`` also records the ``commit`` it was
    handed, and ``step_provenance`` records ``commit``/``commit_source``. Lets the
    --latest tests assert WHICH sha reached the fetch path and the run-log."""
    def rec(name, ret=None):
        def _f(*args, **kwargs):
            cutoff = kwargs.get("cutoff")
            if cutoff is None:
                for a in args:
                    if isinstance(a, str) and a.endswith("Z"):
                        cutoff = a
                        break
            calls.append((name, cutoff, dict(kwargs)))
            return ret
        return _f

    monkeypatch.setattr(mod, "step_ingest", rec("ingest", ret="STORE"))
    monkeypatch.setattr(mod, "step_gate", rec("gate"))
    monkeypatch.setattr(mod, "step_snapshot", rec("snapshot", ret=Path("/tmp/bundle")))
    monkeypatch.setattr(mod, "step_stage", rec("stage"))
    monkeypatch.setattr(mod, "step_provenance", rec("provenance", ret={"ok": True}))


def test_latest_resolves_and_threads_sha_into_ingest(mod, monkeypatch):
    calls: list = []
    _recorders_capturing_commit(mod, monkeypatch, calls)
    resolved = "abc1234abc1234abc1234abc1234abc1234abc1"
    seen = {}

    def fake_resolve():
        seen["called"] = True
        return resolved

    monkeypatch.setattr(mod, "resolve_latest_commit", fake_resolve)
    rc = mod.main(["--latest", "--cutoff", "2026-06-12T00:00:00Z"])
    assert rc == 0
    assert seen.get("called") is True  # the API resolver ran
    ingest = next(c for c in calls if c[0] == "ingest")
    assert ingest[2].get("commit") == resolved  # the resolved sha reached ingest
    # …and provenance recorded it as latest-resolved.
    prov = next(c for c in calls if c[0] == "provenance")
    assert prov[2].get("commit") == resolved
    assert prov[2].get("commit_source") == "latest-resolved"


def test_no_flag_threads_pinned_constant_into_ingest(mod, monkeypatch):
    """Back-compat: no --latest -> the pinned constant reaches ingest and the
    API resolver is NEVER called (default path is byte-identical)."""
    calls: list = []
    _recorders_capturing_commit(mod, monkeypatch, calls)

    def must_not_call():
        raise AssertionError("resolve_latest_commit must not run without --latest")

    monkeypatch.setattr(mod, "resolve_latest_commit", must_not_call)
    rc = mod.main(["--cutoff", "2026-06-12T00:00:00Z"])
    assert rc == 0
    ingest = next(c for c in calls if c[0] == "ingest")
    assert ingest[2].get("commit") == mod.PINNED_COMMIT
    prov = next(c for c in calls if c[0] == "provenance")
    assert prov[2].get("commit") == mod.PINNED_COMMIT
    assert prov[2].get("commit_source") == "pinned"


def test_latest_api_failure_aborts_before_expensive_steps(mod, monkeypatch, capsys):
    """An API error under --latest must abort with a non-zero exit BEFORE ingest/
    gate/snapshot — never silently fall back to the stale pin."""
    calls: list = []
    _recorders_capturing_commit(mod, monkeypatch, calls)

    def boom():
        raise RuntimeError("github api unreachable")

    monkeypatch.setattr(mod, "resolve_latest_commit", boom)
    with pytest.raises(SystemExit) as ei:
        mod.main(["--latest", "--cutoff", "2026-06-12T00:00:00Z"])
    assert ei.value.code != 0
    names = [c[0] for c in calls]
    assert names == []  # nothing expensive ran
    err = capsys.readouterr().err.lower()
    assert "abort" in err or "fail" in err  # a clear failure message, not a silent fallback


def test_dry_run_latest_makes_no_api_call(mod, monkeypatch, capsys):
    """``--dry-run --latest`` must NOT hit the API — it only prints that it WOULD
    resolve the latest commit."""
    calls: list = []
    _recorders_capturing_commit(mod, monkeypatch, calls)

    def must_not_call():
        raise AssertionError("resolve_latest_commit must not run under --dry-run")

    monkeypatch.setattr(mod, "resolve_latest_commit", must_not_call)
    rc = mod.main(["--dry-run", "--latest"])
    assert rc == 0
    assert calls == []  # no steps, no resolve
    out = capsys.readouterr().out.lower()
    assert "latest" in out and ("would" in out or "resolve" in out)


def test_run_log_line_carries_commit_and_source(mod, tmp_path):
    """The run-log JSONL line records {commit, commit_source} — provenance honesty."""
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
    log_path = tmp_path / "daily_update.jsonl"

    rec = mod.step_provenance(
        bundle, log_path=log_path, duration_s=1.5,
        commit="abc1234abc1234abc1234abc1234abc1234abc1",
        commit_source="latest-resolved",
    )
    row = json.loads(log_path.read_text().splitlines()[0])
    assert row["commit"] == "abc1234abc1234abc1234abc1234abc1234abc1"
    assert row["commit_source"] == "latest-resolved"
    assert rec["commit_source"] == "latest-resolved"
