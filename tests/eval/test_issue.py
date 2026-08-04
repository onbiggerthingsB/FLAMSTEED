"""Tests for V9's exit discipline — scripts/oa_issue.py main().

A partial issuance must NOT look like a clean one to a caller (F3): the
shard runner backgrounds N workers and the merge step branches on their
exit statuses, so a worker that skipped fixtures but exited 0 would hand
the contrast a ledger silently missing rows — exactly the failure the
scored inventory exists to make impossible. These tests drive the REAL
``main()`` and the REAL ``run_issue()`` per-fixture loop (only the store,
the posterior fit and the Elo panel are stubbed), with a fixture whose
team is absent from the as-of-cutoff panel — a genuine cannot-price path —
and pin the contract: errors -> exit 1 + the INCOMPLETE line on stderr;
no errors -> exit 0.
"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from wcmodel.eval.ledger import load_ledger

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def issue():
    sys.path.insert(0, str(_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "oa_issue", _ROOT / "scripts" / "oa_issue.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["oa_issue"] = mod
    spec.loader.exec_module(mod)
    return mod


_INVENTORY = (
    {"fixture_id": "f1", "pool": "P", "date": "2024-09-05",
     "home": "A", "away": "B", "eligible": False},
    {"fixture_id": "f2", "pool": "P", "date": "2024-09-05",
     "home": "C", "away": "D", "eligible": False},
)


def _drive(issue, tmp_path, monkeypatch, *, elos):
    """Run main() over a two-fixture locked population.

    ``elos`` is the as-of-cutoff panel's rating dict: a fixture whose team
    is absent from it cannot price and must land in ``errors`` — the same
    per-fixture refusal the production loop takes.
    """
    head = {"version": 7, "code_commit": "f" * 40,
            "scored_inventory": {"fixtures": [dict(r) for r in _INVENTORY]}}
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({"fixtures": [
        {"fixture_id": "f1", "kickoff_utc": "2024-09-05T19:00:00Z"},
        {"fixture_id": "f2", "kickoff_utc": "2024-09-05T19:00:00Z"},
    ]}))
    store = tmp_path / "store"
    store.mkdir()
    pd.DataFrame({"match_id": ["f1", "f2"],
                  "neutral": [False, True]}).to_parquet(
        store / "results.parquet")

    cfg = {"model": {"inference": {"backend": "advi", "draws": 8,
                                   "advi_iters": 10},
                     "covariates": {"enabled": []}},
           "seed": 0}
    choices = {"devig_method": "multiplicative", "w": 0.40,
               "other_devig": "shin", "other_w": 0.30, "stack": None}
    free_arms = {issue.DC_ARM: {"home": .5, "draw": .3, "away": .2},
                 issue.ELO_ARM: {"home": .4, "draw": .3, "away": .3}}

    monkeypatch.setattr(issue, "require_lock", lambda: head)
    monkeypatch.setattr(issue, "locked_choices", lambda: choices)
    monkeypatch.setattr(issue, "load_config", lambda: cfg)
    monkeypatch.setattr(issue, "load_aliases", lambda: {})
    # the heavy externals only — the per-fixture loop stays real
    monkeypatch.setattr(issue, "BitemporalStore", lambda p: None)
    monkeypatch.setattr(issue, "build_cached", lambda *a, **k: None)
    monkeypatch.setattr("wcmodel.model.cache.cached_fit",
                        lambda **k: (None, None))
    monkeypatch.setattr(issue, "match_level_panel", lambda panel: None)
    monkeypatch.setattr(issue, "fit_ordlogit", lambda panel: None)
    monkeypatch.setattr(issue, "latest_elo", lambda panel: dict(elos))
    monkeypatch.setattr(issue, "price_fixture", lambda **kw: dict(free_arms))

    ledger = tmp_path / "ledger.parquet"
    out = tmp_path / "report.md"
    rc = issue.main([
        "--manifest", str(manifest), "--store", str(store),
        "--cache-dir", str(tmp_path / "cache"),
        "--raw-dir", str(tmp_path / "raw"),
        "--ledger", str(ledger), "--out", str(out)])
    return rc, ledger, out


def test_a_fixture_that_cannot_price_exits_1_with_incomplete_on_stderr(
        issue, tmp_path, monkeypatch, capsys):
    """The F3 contract: one unpriced fixture makes the whole run report
    INCOMPLETE on stderr and exit 1, while the partial evidence (the other
    fixture's rows, the error table in the report) still lands on disk."""
    rc, ledger, out = _drive(issue, tmp_path, monkeypatch,
                             elos={"A": 1600.0, "B": 1500.0})  # C, D absent
    assert rc == 1
    err = capsys.readouterr().err
    assert "INCOMPLETE: 1 fixture(s) did not price" in err
    assert "must not be merged as final" in err
    # partial evidence is preserved, flagged — not discarded
    frame = load_ledger(ledger)
    assert set(frame["fixture_id"]) == {"f1"}
    assert len(frame) == len(issue.ISSUED_ARMS)
    assert "| f2 | team absent" in out.read_text()


def test_a_run_with_every_fixture_priced_exits_0(issue, tmp_path, monkeypatch,
                                                 capsys):
    """The contrast that keeps the previous test meaningful: the exit code
    is driven by the error set, not always-1 or always-0."""
    rc, ledger, _ = _drive(issue, tmp_path, monkeypatch,
                           elos={"A": 1600.0, "B": 1500.0,
                                 "C": 1550.0, "D": 1450.0})
    assert rc == 0
    assert "INCOMPLETE" not in capsys.readouterr().err
    assert set(load_ledger(ledger)["fixture_id"]) == {"f1", "f2"}
