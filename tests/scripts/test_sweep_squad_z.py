"""Orchestration tests for ``scripts/sweep_squad_z.py`` (P3 v0 sweep harness).

The sweep is THIN: named step functions (so tests can monkeypatch the heavy fit +
score with recorders) + an argparse ``main`` that walks the PRE-REGISTERED grid
and prints the machine-readable verdict. These tests pin the ORCHESTRATION — the
locked grid, the two cutoffs/tags, the gate wiring, the verdict line, the
zero-credits invariant — WITHOUT running a real fit/sim/network call.

Loaded by PATH (the scan-script house pattern: ``scripts/`` is not on sys.path).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "sweep_squad_z.py"


def _load():
    spec = importlib.util.spec_from_file_location("sweep_squad_z", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


# --------------------------------------------------------------------------- #
# Locked pre-registration constants.                                           #
# --------------------------------------------------------------------------- #
def test_grid_and_cutoffs_are_pre_registered(mod):
    assert mod.K_SQUAD_GRID == [0.0, 0.2, 0.4, 0.6]
    assert mod.K_ELO == 0.6
    # Two held-out tournaments at the prereg cutoffs / tags.
    tags = {h["tag"]: h for h in mod.HELDOUT}
    assert tags["wc2022"]["cutoff"].startswith("2022-11-20")
    assert tags["euro2024"]["cutoff"].startswith("2024-06-14")
    assert tags["wc2022"]["squad_snapshot"] == "clubelo_20221120.csv"
    assert tags["euro2024"]["squad_snapshot"] == "clubelo_20240614.csv"


def test_min_matched_is_referenced_not_tuned(mod):
    # The harness must NOT define/override MIN_MATCHED — it inherits the pinned
    # value from the data layer (never tuned against sweep RPS, prereg §6).
    from wcmodel.data.sources.squad_z import MIN_MATCHED
    assert MIN_MATCHED == 13


# --------------------------------------------------------------------------- #
# Orchestration: the grid is walked for BOTH cutoffs with recorders.           #
# --------------------------------------------------------------------------- #
def _stub_store_and_heldout(mod, monkeypatch):
    """Stub the heavy store build + held-out frame so the orchestration test runs
    with NO real store / NO network."""
    import pandas as pd
    monkeypatch.setattr(mod, "step_store", lambda: "STUB_STORE")
    monkeypatch.setattr(mod, "step_heldout",
                        lambda store, spec: pd.DataFrame({"_": [0]}))


def _recorders(mod, monkeypatch, calls):
    """Replace the heavy per-cell fit+score with a recorder returning synthetic
    per-match RPS arrays, so no fit/sim/network runs. The k=0.4 cell is made the
    clear knee that beats k=0 and improves the slice -> a deterministic ADOPT."""
    _stub_store_and_heldout(mod, monkeypatch)
    rng = np.random.default_rng(0)
    base_overall = rng.uniform(0.2, 0.6, 120)
    base_slice = rng.uniform(0.2, 0.6, 30)

    def fake_fit_and_score(*, cutoff, tag, k_squad, **kwargs):
        calls.append({"cutoff": cutoff, "tag": tag, "k_squad": k_squad})
        # Make k=0.4 the knee (lowest overall), and improve the slice with k.
        bump = {0.0: 0.0, 0.2: -0.01, 0.4: -0.03, 0.6: -0.02}[round(k_squad, 2)]
        sbump = {0.0: 0.0, 0.2: -0.003, 0.4: -0.006, 0.6: -0.004}[round(k_squad, 2)]
        return {
            "overall_rps": list(base_overall + bump),
            "slice_rps": list(base_slice + sbump),
            "n_overall": len(base_overall),
            "n_slice": len(base_slice),
            "n_train": 1000,
            "max_train_date": cutoff[:10],
            "cache_hit": False,
        }

    monkeypatch.setattr(mod, "fit_and_score_cell", fake_fit_and_score)


def test_walks_full_grid_for_both_cutoffs(mod, monkeypatch, capsys):
    calls: list = []
    _recorders(mod, monkeypatch, calls)
    rc = mod.main([])
    assert rc == 0
    # 4 k * 2 cutoffs = 8 cells.
    assert len(calls) == 8
    ks = sorted({c["k_squad"] for c in calls})
    assert ks == [0.0, 0.2, 0.4, 0.6]
    tags = {c["tag"] for c in calls}
    assert tags == {"wc2022", "euro2024"}
    out = capsys.readouterr().out
    assert "P3SWEEP VERDICT:" in out


def test_verdict_line_is_machine_readable_adopt(mod, monkeypatch, capsys):
    calls: list = []
    _recorders(mod, monkeypatch, calls)
    mod.main([])
    out = capsys.readouterr().out
    verdict_line = next(l for l in out.splitlines() if l.startswith("P3SWEEP VERDICT:"))
    assert "ADOPT k_squad=0.4" in verdict_line


def test_no_lift_verdict_when_anchor_hurts(mod, monkeypatch, capsys):
    calls: list = []
    _stub_store_and_heldout(mod, monkeypatch)
    rng = np.random.default_rng(1)
    base_overall = rng.uniform(0.2, 0.6, 120)
    base_slice = rng.uniform(0.2, 0.6, 30)

    def fake(*, cutoff, tag, k_squad, **kwargs):
        # every k>0 is WORSE -> knee is k=0 -> NO-LIFT.
        bump = {0.0: 0.0, 0.2: 0.02, 0.4: 0.03, 0.6: 0.04}[round(k_squad, 2)]
        return {"overall_rps": list(base_overall + bump),
                "slice_rps": list(base_slice + bump),
                "n_overall": len(base_overall), "n_slice": len(base_slice),
                "n_train": 1000, "max_train_date": cutoff[:10], "cache_hit": False}

    monkeypatch.setattr(mod, "fit_and_score_cell", fake)
    mod.main([])
    out = capsys.readouterr().out
    verdict_line = next(l for l in out.splitlines() if l.startswith("P3SWEEP VERDICT:"))
    assert "NO-LIFT" in verdict_line


def test_single_cutoff_flag_restricts_grid(mod, monkeypatch, capsys):
    calls: list = []
    _recorders(mod, monkeypatch, calls)
    rc = mod.main(["--only", "wc2022"])
    assert rc == 0
    assert {c["tag"] for c in calls} == {"wc2022"}
    assert len(calls) == 4


# --------------------------------------------------------------------------- #
# Zero-credits / offline invariant (the daily_update / sweep_altitude precedent).
# --------------------------------------------------------------------------- #
def test_no_odds_api_surface():
    src = _MODULE_PATH.read_text()
    assert "odds_live" not in src
    assert "THE_ODDS_API_KEY" not in src
    assert "fetch_live_odds" not in src
