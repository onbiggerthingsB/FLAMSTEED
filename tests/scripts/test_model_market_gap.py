"""Orchestration + report-assembly tests for ``scripts/model_market_gap.py``.

The script is THIN: two heavy step functions (``run_part_a`` — the n=22 paired
model-vs-market gap on the CURRENT config; ``run_part_b`` — the n~2111 stratified
weakness map vs realized results) + a PURE ``assemble_report`` + an argparse
``main``. These tests pin the ORCHESTRATION (``--part A|B|all`` runs exactly the
selected part; B never touches the odds cache; A never queries the Part-B set)
and the REPORT ASSEMBLY (canned result dicts -> the markdown carries the ranked
slice table, the limitation note, the G1 recommendation line, and the SUSPECT
tripwire) — WITHOUT ever running a real fit or reading the odds cache (every
heavy step is a monkeypatched recorder). A source-level grep test pins the
zero-Odds-API-credit invariant (no live-fetch surface).

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``) so
it imports identically to how it runs.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "model_market_gap.py"


def _load():
    spec = importlib.util.spec_from_file_location("model_market_gap", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


# --------------------------------------------------------------------------- #
# Canned result dicts — the SHAPE assemble_report consumes (never a real fit).
# --------------------------------------------------------------------------- #
def _canned_part_a(delta=0.012, lo=0.004, hi=0.020):
    """A Part-A aggregate where the market beats the model (positive delta) by
    default — the expected, non-tripwire case."""
    return {
        "n": 22,
        "aggregate": {"delta": delta, "lo95": lo, "hi95": hi,
                      "rps_model": 0.20 + delta, "rps_ref": 0.20},
        "clusters": [
            {"name": "wc2022", "cutoff": "2022-11-20T00:00:00Z", "n": 7,
             "delta": 0.010, "lo95": -0.002, "hi95": 0.022,
             "posterior_key": "posterior-aaa.nc"},
            {"name": "euro2024", "cutoff": "2024-06-14T00:00:00Z", "n": 5,
             "delta": 0.014, "lo95": 0.001, "hi95": 0.027,
             "posterior_key": "posterior-bbb.nc"},
        ],
        "per_match": [
            {"home": "Argentina", "away": "Saudi Arabia", "date": "2022-11-22",
             "outcome": "A", "rps_model": 0.9, "rps_market": 0.7},
        ],
    }


def _canned_part_b():
    return {
        "n": 2111,
        "posterior_src": "REUSED posterior-a7f06f23227f3a56.nc (config-matched k=0.6)",
        "aggregate": {"rps_model": 0.331, "rps_elo": 0.340,
                      "delta": -0.009, "lo95": -0.013, "hi95": -0.005},
        "slices": [
            {"slice": "tier=friendly", "n": 600, "rps_model": 0.36, "rps_elo": 0.34,
             "delta": 0.020, "lo95": 0.010, "hi95": 0.030},
            {"slice": "confed_pair=cross-confed", "n": 400, "rps_model": 0.30,
             "rps_elo": 0.31, "delta": -0.010, "lo95": -0.020, "hi95": 0.000},
        ],
        "reliability_fav": [
            {"bin": "0.5-0.6", "n": 100, "p_mean": 0.55, "freq": 0.52},
        ],
        "reliability_draw": [
            {"bin": "0.2-0.3", "n": 300, "p_mean": 0.25, "freq": 0.27},
        ],
    }


# --------------------------------------------------------------------------- #
# Orchestration: --part selects exactly the requested part.
# --------------------------------------------------------------------------- #
def _record_parts(mod, monkeypatch, calls, *, a_ret=None, b_ret=None):
    def part_a(*a, **k):
        calls.append("A")
        return a_ret if a_ret is not None else _canned_part_a()

    def part_b(*a, **k):
        calls.append("B")
        return b_ret if b_ret is not None else _canned_part_b()

    monkeypatch.setattr(mod, "run_part_a", part_a)
    monkeypatch.setattr(mod, "run_part_b", part_b)


def test_part_b_only_runs_b_not_a(mod, monkeypatch, tmp_path):
    """``--part B`` runs Part B and NEVER Part A (so it never touches the odds cache)."""
    calls: list[str] = []
    _record_parts(mod, monkeypatch, calls)
    out = tmp_path / "r.md"
    rc = mod.main(["--part", "B", "--out", str(out)])
    assert rc == 0
    assert calls == ["B"]
    assert "A" not in calls
    assert out.exists()


def test_part_a_only_runs_a_not_b(mod, monkeypatch, tmp_path):
    """``--part A`` runs Part A and NEVER queries the Part-B (n~2111) set."""
    calls: list[str] = []
    _record_parts(mod, monkeypatch, calls)
    out = tmp_path / "r.md"
    rc = mod.main(["--part", "A", "--out", str(out)])
    assert rc == 0
    assert calls == ["A"]
    assert "B" not in calls


def test_part_all_runs_both(mod, monkeypatch, tmp_path):
    calls: list[str] = []
    _record_parts(mod, monkeypatch, calls)
    out = tmp_path / "r.md"
    rc = mod.main(["--part", "all", "--out", str(out)])
    assert rc == 0
    assert set(calls) == {"A", "B"}


# --------------------------------------------------------------------------- #
# No live-fetch surface (zero Odds-API credits).
# --------------------------------------------------------------------------- #
def test_no_live_fetch_surface():
    src = _MODULE_PATH.read_text()
    assert "fetch_live_odds" not in src
    assert "odds_live" not in src
    assert "THE_ODDS_API_KEY" not in src
    assert "httpx.get" not in src
    # The script must not import a live-odds fetcher or the env-key loader.
    assert "_load_env_key" not in src


# --------------------------------------------------------------------------- #
# Report assembly (pure).
# --------------------------------------------------------------------------- #
def test_report_has_ranked_table_limitation_and_recommendation(mod):
    md = mod.assemble_report(_canned_part_a(), _canned_part_b(), today="2026-06-10")
    # Part B ranked slice table: worst slice (largest positive delta) first.
    assert "tier=friendly" in md
    assert "confed_pair=cross-confed" in md
    i_worst = md.index("tier=friendly")
    i_best = md.index("confed_pair=cross-confed")
    assert i_worst < i_best  # ranked worst-first (delta descending)
    # The coverage-limitation note is present.
    assert "limitation" in md.lower()
    assert "22" in md  # the n=22 thinness is stated
    # A G1 recommendation line is present.
    assert "recommend" in md.lower() or "G1" in md
    # Reliability tables labelled.
    assert "reliab" in md.lower()


def test_report_recommendation_tracks_thresholds(mod):
    """Gap >= ~0.01 -> Phase-3 priority; small gap (< ~0.005) -> Phase 2 only."""
    big = mod.assemble_report(_canned_part_a(delta=0.012, lo=0.004, hi=0.020),
                              _canned_part_b(), today="2026-06-10")
    assert "Phase 3" in big or "phase 3" in big.lower()
    small = mod.assemble_report(_canned_part_a(delta=0.002, lo=-0.001, hi=0.005),
                                _canned_part_b(), today="2026-06-10")
    assert "Phase 2" in small or "phase 2" in small.lower()


def test_report_tripwire_flips_suspect_label(mod):
    """A negative aggregate market gap (model 'beats' the de-vigged sharp close)
    is too-good -> the report carries the SUSPECT label + the audit block."""
    suspect = mod.assemble_report(
        _canned_part_a(delta=-0.008, lo=-0.015, hi=-0.001),
        _canned_part_b(), today="2026-06-10")
    assert "SUSPECT" in suspect
    assert "selection" in suspect.lower()  # the selection-bias audit is named
    # The non-tripwire (positive-gap) case does NOT raise the SUSPECT flag.
    ok = mod.assemble_report(_canned_part_a(delta=0.012), _canned_part_b(),
                             today="2026-06-10")
    assert "SUSPECT" not in ok


def test_report_writes_file(mod, monkeypatch, tmp_path):
    """``main`` writes the assembled markdown to ``--out``."""
    calls: list[str] = []
    _record_parts(mod, monkeypatch, calls)
    out = tmp_path / "headroom.md"
    rc = mod.main(["--part", "all", "--out", str(out)])
    assert rc == 0
    text = out.read_text()
    assert "tier=friendly" in text
    assert "limitation" in text.lower()
