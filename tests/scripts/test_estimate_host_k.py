"""Orchestration + report-assembly tests for ``scripts/estimate_host_k.py``.

The script is THIN: a sample builder (``build_host_rows`` — finals-tier host
games + point-in-time Elo), a pure estimate step (``run_estimate`` — k_elo MLE +
bootstrap CI + the unit mapping + the verdict), a sim-only sensitivity runner
(``run_sensitivity`` — REUSES a cached posterior, NO refit), and a PURE
``assemble_report`` + an argparse ``main``.

These tests pin the REPORT ASSEMBLY (canned dicts -> the markdown carries the n +
per-tournament breakdown, the k ± CI line, the unit-mapping + net-edge-both-ways
block, the sensitivity table, and EXACTLY ONE of ADOPT / NO-CHANGE / SUSPECTED-
BUG) and the SENSITIVITY ORCHESTRATION (the runner threads the overridden host_k
into the SimConfig it passes, runs once per host_k, shapes the delta table) —
WITHOUT ever running a real fit or a real sim (the sim + posterior lookup are
monkeypatched). A source-level grep pins the zero-Odds-API-credit invariant.

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "estimate_host_k.py"


def _load():
    spec = importlib.util.spec_from_file_location("estimate_host_k", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


# --------------------------------------------------------------------------- #
# Canned dicts — the SHAPE assemble_report consumes (never a real fit/sim).
# --------------------------------------------------------------------------- #
def _canned_breakdown(n=873):
    return {
        "n": n,
        "hda": (0.597, 0.215, 0.188),
        "hda_counts": {"H": 521, "D": 188, "A": 164},
        "by_family": {"Copa América": 291, "AFCON": 162, "WC finals": 121,
                      "Gold Cup": 109, "Euro": 99, "AFC Asian Cup": 91},
        "by_tier": {"continental_championship": 752, "wc_finals": 121},
    }


def _canned_estimate(k=1.40, lo=1.10, hi=1.70):
    """An ADOPT case by default: the CI excludes 0.5."""
    cur = 0.5
    suspected = (k > 3.0 or k < -1.0)
    excludes = (lo > cur or hi < cur)
    if suspected:
        verdict, adopt = "SUSPECTED-BUG", None
    elif excludes:
        verdict, adopt = "ADOPT", round(k, 1)
    else:
        verdict, adopt = "NO-CHANGE", None
    return {
        "k_elo": k, "lo95": lo, "hi95": hi,
        "n": 873, "n_boot": 2000, "seed": 20260611,
        "home_advantage": 100.0, "draw_base": 0.28,
        "host_k_model": k, "current_host_k": cur,
        "ci_excludes_half": excludes,
        "verdict": verdict, "adopt_value": adopt,
    }


def _canned_sensitivity(old=0.5, new=1.4):
    def hosts(champ_us, adv_us):
        return {
            "United States": {"champion": champ_us, "champion_se": 0.003,
                              "advance": adv_us, "advance_se": 0.004},
            "Mexico": {"champion": 0.04, "champion_se": 0.002,
                       "advance": 0.70, "advance_se": 0.004},
            "Canada": {"champion": 0.02, "champion_se": 0.001,
                       "advance": 0.55, "advance_se": 0.005},
        }

    def board(top_champ):
        return [
            {"team": "Spain", "champion": 0.15, "champion_se": 0.003},
            {"team": "France", "champion": 0.13, "champion_se": 0.003},
            {"team": "United States", "champion": top_champ, "champion_se": 0.003},
        ]

    return {
        "cutoff": "2026-06-10T00:00:00Z",
        "posterior_src": "REUSED posterior-7df2414f5175cbcc.nc (config-matched / 2026-06-10)",
        "host_ks": [old, new],
        "n_sims": 20000,
        "per_k": {old: hosts(0.08, 0.80), new: hosts(0.11, 0.88)},
        "boards": {old: board(0.08), new: board(0.11)},
    }


# --------------------------------------------------------------------------- #
# No live-fetch surface (zero Odds-API credits).
# --------------------------------------------------------------------------- #
def test_no_live_fetch_surface():
    src = _MODULE_PATH.read_text()
    assert "fetch_live_odds" not in src
    assert "odds_live" not in src
    assert "THE_ODDS_API_KEY" not in src
    assert "httpx" not in src
    assert "_load_env_key" not in src


# --------------------------------------------------------------------------- #
# Report assembly (pure).
# --------------------------------------------------------------------------- #
def test_report_has_sample_breakdown_estimate_and_mapping(mod):
    md = mod.assemble_report(_canned_estimate(), _canned_breakdown(),
                             _canned_sensitivity(), today="2026-06-10")
    # n + per-tournament breakdown present.
    assert "873" in md
    assert "Copa América" in md and "AFCON" in md and "WC finals" in md
    # k +- CI line.
    assert "k_elo" in md
    assert "1.40" in md and "1.10" in md and "1.70" in md
    # Unit mapping (identity) + net-edge-both-ways block.
    assert "host_k_model = k_elo" in md
    assert "identity" in md.lower()
    assert "net edge" in md.lower() or "net-edge" in md.lower()
    # The (host_k - 0.5)*ha net-edge phrasing.
    assert "0.5" in md


def test_report_sensitivity_table_has_hosts_deltas_and_top8(mod):
    md = mod.assemble_report(_canned_estimate(), _canned_breakdown(),
                             _canned_sensitivity(), today="2026-06-10")
    # Host rows + both markets.
    assert "United States" in md and "Mexico" in md and "Canada" in md
    assert "champion" in md and "advance_from_group" in md
    # The top-8 champion board (old vs new) is present.
    assert "champion board" in md.lower()
    # The SE is carried (a +- appears in the table cells).
    assert "±" in md
    # The empirical host_k (1.4) and the current (0.5) both label columns.
    assert "1.4" in md


def test_report_verdict_is_exactly_one_label(mod):
    """ADOPT (CI excludes 0.5), NO-CHANGE (CI includes 0.5), SUSPECTED-BUG (k>3)
    — each renders EXACTLY ONE verdict, deterministically from the estimate dict."""
    # ADOPT: CI [1.10, 1.70] excludes 0.5.
    adopt = mod.assemble_report(_canned_estimate(k=1.4, lo=1.1, hi=1.7),
                                _canned_breakdown(), None, today="2026-06-10")
    assert "ADOPT" in adopt
    assert "NO-CHANGE" not in adopt
    assert "SUSPECTED" not in adopt
    assert "host_k = 1.4" in adopt

    # NO-CHANGE: CI [0.3, 0.9] includes 0.5.
    nochange = mod.assemble_report(_canned_estimate(k=0.6, lo=0.3, hi=0.9),
                                   _canned_breakdown(), None, today="2026-06-10")
    assert "NO-CHANGE" in nochange
    assert "ADOPT host_k" not in nochange  # the ADOPT recommendation heading is absent

    # SUSPECTED-BUG: k > 3 -> withhold ADOPT.
    bug = mod.assemble_report(_canned_estimate(k=4.5, lo=3.8, hi=5.2),
                              _canned_breakdown(), None, today="2026-06-10")
    assert "SUSPECTED" in bug
    assert "WITHHELD" in bug or "withheld" in bug.lower()
    assert "RECOMMENDATION: ADOPT" not in bug


# --------------------------------------------------------------------------- #
# run_estimate — the verdict logic is deterministic from rows + cfg.
# --------------------------------------------------------------------------- #
def _cfg():
    return {"seed": 20260611, "elo": {"home_advantage": 100.0},
            "baseline": {"draw_base": 0.28},
            "sim": {"n_sims": 20000, "max_goals": 12, "extra_time_scale": 0.3333,
                    "penalty_home_prob": 0.5},
            "model": {"covariates": {"host_k": 0.5}}}


def test_run_estimate_identity_mapping_and_verdict(mod):
    """run_estimate carries the identity mapping (host_k_model == k_elo) and a
    verdict; on synthetic-strong-host data it should ADOPT (CI excludes 0.5)."""
    # Synthesise a host-heavy sample directly via the estimator's own probs so the
    # MLE has a clear signal (k_true ~ 1.4); small n_boot keeps the test quick.
    import numpy as np

    from wcmodel.backtest.host_k import elo_host_probs
    rng = np.random.default_rng(1)
    rows = []
    for _ in range(1500):
        rh = 1500.0 + rng.normal(0, 120)
        ra = 1500.0 + rng.normal(0, 120)
        pH, pD, pA = elo_host_probs(rh, ra, 1.4, draw_base=0.28, home_advantage=100.0)
        o = rng.choice(["H", "D", "A"], p=[pH, pD, pA])
        rows.append({"rating_home": rh, "rating_away": ra, "outcome": str(o)})
    cfg = _cfg()
    # n_boot patched down for test speed (the production runner uses 2000).
    mod.N_BOOT = 80
    est = mod.run_estimate(rows, cfg)
    assert est["host_k_model"] == est["k_elo"]  # identity mapping
    assert est["verdict"] in ("ADOPT", "NO-CHANGE", "SUSPECTED-BUG")
    # A strong injected host edge (k_true=1.4) should land near 1.4 and ADOPT.
    assert 1.2 < est["k_elo"] < 1.6
    assert est["verdict"] == "ADOPT"
    assert est["adopt_value"] == round(est["k_elo"], 1)


# --------------------------------------------------------------------------- #
# Sensitivity-runner monkeypatch test — threads host_k into the SimConfig, runs
# once per host_k, shapes the delta table; NO real posterior / sim.
# --------------------------------------------------------------------------- #
def _stub_simresult(champ_us):
    """A tiny team-indexed SimResult-like object with progression + se frames."""
    from wcmodel.sim.tournament import SimResult
    teams = ["United States", "Mexico", "Canada", "Spain", "France"]
    cols = ["champion", "advance_from_group"]
    prog = pd.DataFrame(
        {"champion": [champ_us, 0.04, 0.02, 0.15, 0.13],
         "advance_from_group": [0.80, 0.70, 0.55, 0.95, 0.93]},
        index=teams,
    )[cols]
    se = pd.DataFrame(
        {"champion": [0.003, 0.002, 0.001, 0.003, 0.003],
         "advance_from_group": [0.004, 0.004, 0.005, 0.002, 0.002]},
        index=teams,
    )[cols]
    return SimResult(progression=prog, se=se, random_tail_rate=0.0, n_sims=20000)


def test_run_sensitivity_threads_host_k_and_runs_once_per_value(mod, monkeypatch):
    seen_host_ks: list[float] = []

    def fake_find(cutoff, cfg):
        # Match only the preferred (first) cutoff so the runner picks it.
        if cutoff == mod.SENSITIVITY_CUTOFFS[0]:
            return ("SENTINEL_POSTERIOR", "posterior-sentinel.nc", set())
        return None

    def fake_simulate(cutoff, posterior, store, simcfg):
        assert posterior == "SENTINEL_POSTERIOR"  # the reused sentinel, never a fit
        hk = simcfg.config["model"]["covariates"]["host_k"]
        seen_host_ks.append(float(hk))
        # Distinct champion by host_k so the delta is non-trivial.
        return _stub_simresult(0.08 if abs(hk - 0.5) < 1e-9 else 0.11)

    monkeypatch.setattr(mod, "_find_cached_production_posterior", fake_find)
    monkeypatch.setattr(mod, "simulate", fake_simulate)

    cfg = _cfg()
    out = mod.run_sensitivity(store=object(), cfg=cfg, host_ks=[0.5, 1.4])

    # Ran exactly once per host_k, threading the overridden value each time.
    assert seen_host_ks == [0.5, 1.4]
    # Reused the sentinel posterior at the preferred cutoff (no fresh fit).
    assert "sentinel" in out["posterior_src"].lower()
    assert out["cutoff"] == mod.SENSITIVITY_CUTOFFS[0]
    # Per-host champion deltas carried (new - old), with SE.
    us_old = out["per_k"][0.5]["United States"]["champion"]
    us_new = out["per_k"][1.4]["United States"]["champion"]
    assert us_old == 0.08 and us_new == 0.11
    assert out["per_k"][0.5]["United States"]["champion_se"] == 0.003
    # Top-8 board shaped from the stub at each host_k.
    assert out["boards"][0.5][0]["team"] in {"Spain", "France", "United States"}
    assert len(out["boards"][1.4]) >= 1


def test_run_sensitivity_no_cached_posterior_errors_without_fresh_fit(mod, monkeypatch):
    monkeypatch.setattr(mod, "_find_cached_production_posterior",
                        lambda cutoff, cfg: None)
    with pytest.raises(RuntimeError, match="config-matched"):
        mod.run_sensitivity(store=object(), cfg=_cfg(), host_ks=[0.5, 1.4])
