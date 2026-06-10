"""Orchestration + report-assembly tests for ``scripts/diagnose_tails.py`` (P4a/4b).

The script is THIN: a 4a tail diagnostic (``run_4a`` — REUSES a cached posterior,
buckets the held-out set, predicted-vs-realized tail masses), a pure transform
sizer (``size_transform`` — the bucket-alpha rule from the 4a misfit), a sim-only
4b sensitivity runner (``run_4b`` — REUSES the cached production posterior, NO
refit, the tail_fatten override), a pure ``decision`` (the brief's 2xSE rule), and
a PURE ``assemble_report`` + an argparse ``main``.

These tests pin the PURE pieces (``size_transform`` monotonicity / no-misfit ->
near-zero alpha; ``decision`` NO-LIFT vs 4c-GO; ``assemble_report`` carries the 4a
table + transform + sim before/after table + EXACTLY ONE verdict) and the 4b
SENSITIVITY ORCHESTRATION (reuses the cached posterior, runs baseline + perturbed
once each with the SAME seed, threads the alpha-vector into SimConfig.tail_fatten)
— WITHOUT ever running a real fit or a real sim. A source grep pins the
zero-Odds-API-credit invariant.

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "diagnose_tails.py"


def _load():
    spec = importlib.util.spec_from_file_location("diagnose_tails", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


def _cfg():
    from wcmodel.config import load_config
    return load_config()


# --------------------------------------------------------------------------- #
# size_transform — the bucket-alpha sizing rule.
# --------------------------------------------------------------------------- #
def test_size_transform_monotone_in_gap_and_capped(mod):
    """A 4a table with worsening blowout under-prediction at higher |gap| -> alpha
    monotone non-decreasing in the bucket, capped at alpha_max."""
    # ratios realized/predicted by bucket: Q1 fine, Q4 badly under-predicted.
    table = {
        "buckets": ["Q1", "Q2", "Q3", "Q4"],
        "edges": [100.0, 250.0, 450.0],
        "ratio_by_bucket": [1.0, 1.3, 1.8, 2.6],   # blowout markets averaged
    }
    out = mod.size_transform(table)
    a = out["alpha_by_bucket"]
    assert a == sorted(a)                          # monotone non-decreasing
    assert all(0.0 <= x <= mod.ALPHA_MAX + 1e-12 for x in a)
    assert a[-1] == pytest.approx(mod.ALPHA_MAX)   # worst bucket hits the cap
    assert out["edges"] == table["edges"]


def test_size_transform_no_misfit_near_zero_alpha(mod):
    """If realized <= predicted everywhere (ratios <= 1), the transform is ~no-op
    (alpha 0 everywhere) — the honest NO-MISFIT path."""
    table = {
        "buckets": ["Q1", "Q2", "Q3", "Q4"],
        "edges": [100.0, 250.0, 450.0],
        "ratio_by_bucket": [0.9, 1.0, 0.95, 0.8],
    }
    out = mod.size_transform(table)
    assert all(x == pytest.approx(0.0) for x in out["alpha_by_bucket"])


# --------------------------------------------------------------------------- #
# decision — the brief's 2xSE rule.
# --------------------------------------------------------------------------- #
def test_decision_all_within_2se_is_no_lift(mod):
    deltas = {"champion": {"Spain": 0.001}, "advance_from_group": {"Mexico": 0.002},
              "third": {"Senegal": 0.003}}
    ses = {"champion": {"Spain": 0.003}, "advance_from_group": {"Mexico": 0.004},
           "third": {"Senegal": 0.005}}
    out = mod.decision(deltas, ses)
    assert out["verdict"] == "NO-LIFT"
    assert out["moved"] == []


def test_decision_one_market_beyond_2se_is_4c_go(mod):
    deltas = {"champion": {"Spain": 0.001}, "advance_from_group": {"Mexico": 0.02},
              "third": {"Senegal": 0.003}}
    ses = {"champion": {"Spain": 0.003}, "advance_from_group": {"Mexico": 0.004},
           "third": {"Senegal": 0.005}}
    out = mod.decision(deltas, ses)
    assert out["verdict"] == "4c-GO"
    # Mexico advance moved beyond 2*0.004 = 0.008 (delta 0.02) -> named.
    assert any("Mexico" in m or "advance" in m for m in out["moved"])


# --------------------------------------------------------------------------- #
# assemble_report — pure (canned dicts -> markdown).
# --------------------------------------------------------------------------- #
def _canned_4a():
    return {
        "n": 2100,
        "posterior_src": "REUSED posterior-5de423cf6c9a498f.nc (config-matched k=0.6 / 2024-06-01)",
        "cutoff": "2024-06-01T00:00:00Z",
        "max_train": "2024-05-31",
        "buckets": ["Q1", "Q2", "Q3", "Q4", "top-decile"],
        "edges": [100.0, 250.0, 450.0],
        "rows": [
            {"bucket": "Q4", "market": "total_ge5", "n": 528, "pred": 0.10, "real": 0.14,
             "real_lo": 0.11, "real_hi": 0.17, "gap": 0.04, "gap_lo": 0.01, "gap_hi": 0.07,
             "ratio": 1.4},
        ],
        "ratio_by_bucket": [1.0, 1.1, 1.3, 1.5],
        "gaps": [],
    }


def _canned_transform():
    return {"edges": [100.0, 250.0, 450.0], "alpha_by_bucket": [0.0, 0.1, 0.3, 0.5]}


def _canned_4b(verdict="NO-LIFT"):
    return {
        "cutoff": "2026-06-10T00:00:00Z",
        "posterior_src": "REUSED posterior-e45d051e8e68d492.nc (config-matched / 2026-06-10)",
        "n_sims": 20000,
        "seed": 20260611,
        "hosts": {
            "United States": {"champion": {"base": 0.05, "fat": 0.051, "se": 0.0015},
                              "advance_from_group": {"base": 0.80, "fat": 0.801, "se": 0.003}},
        },
        "board_base": [{"team": "Spain", "champion": 0.128, "se": 0.0024}],
        "board_fat": [{"team": "Spain", "champion": 0.129, "se": 0.0024}],
        "third_best8": [{"team": "Senegal", "base": 0.40, "fat": 0.402, "se": 0.0035}],
        "decision": {"verdict": verdict, "moved": []},
    }


def test_assemble_report_carries_all_sections_and_one_verdict(mod):
    md = mod.assemble_report(_canned_4a(), _canned_transform(), _canned_4b("NO-LIFT"),
                             today="2026-06-10")
    # 4a table present.
    assert "total_ge5" in md and "Q4" in md
    assert "2024-06-01" in md
    # Transform definition + the alpha-vector.
    assert "mean-preserving" in md.lower()
    assert "0.5" in md   # the worst-bucket alpha
    # 4b before/after sim table: hosts + board + third best-8 + SE.
    assert "United States" in md and "Senegal" in md and "Spain" in md
    assert "20,000" in md or "20000" in md
    # EXACTLY ONE verdict token.
    assert ("NO-LIFT" in md) ^ ("4c-GO" in md)
    assert "NO-LIFT" in md


def test_assemble_report_4c_go_verdict(mod):
    b = _canned_4b("4c-GO")
    b["decision"] = {"verdict": "4c-GO", "moved": ["advance_from_group: Mexico +2.0pp"]}
    md = mod.assemble_report(_canned_4a(), _canned_transform(), b, today="2026-06-10")
    assert ("NO-LIFT" in md) ^ ("4c-GO" in md)
    assert "4c-GO" in md
    assert "Mexico" in md


def test_assemble_report_4a_only(mod):
    """4a alone (no 4b yet) still assembles the diagnostic table + a 'pending' note."""
    md = mod.assemble_report(_canned_4a(), _canned_transform(), None, today="2026-06-10")
    assert "total_ge5" in md
    assert "4b" in md.lower()


# --------------------------------------------------------------------------- #
# run_4b — sim-only sensitivity orchestration (monkeypatched sim + posterior).
# --------------------------------------------------------------------------- #
def _stub_simresult(champ_spain, adv_us, third_sen):
    from wcmodel.sim.tournament import SimResult
    teams = ["United States", "Mexico", "Canada", "Spain", "Senegal"]
    cols = ["champion", "advance_from_group", "third"]
    prog = pd.DataFrame(
        {"champion": [0.05, 0.04, 0.02, champ_spain, 0.01],
         "advance_from_group": [adv_us, 0.70, 0.55, 0.95, 0.60],
         "third": [0.20, 0.22, 0.25, 0.10, third_sen]},
        index=teams,
    )[cols]
    se = pd.DataFrame(
        {"champion": [0.0015, 0.001, 0.001, 0.0024, 0.001],
         "advance_from_group": [0.003, 0.004, 0.005, 0.002, 0.004],
         "third": [0.003, 0.003, 0.003, 0.002, 0.0035]},
        index=teams,
    )[cols]
    return SimResult(progression=prog, se=se, random_tail_rate=0.0, n_sims=20000)


def test_run_4b_reuses_posterior_threads_tail_fatten_same_seed(mod, monkeypatch):
    seen = []

    def fake_find(cutoff, cfg):
        if cutoff == mod.SENSITIVITY_CUTOFFS[0]:
            return ("SENTINEL_POSTERIOR", "posterior-sentinel.nc", set())
        return None

    def fake_ratings(post, store, cutoff, cfg):
        # The per-fixture alpha closure is built from these point-in-time ratings.
        return {"United States": 1800.0, "Mexico": 1750.0, "Spain": 2000.0,
                "Canada": 1600.0, "Senegal": 1700.0}

    def fake_simulate(cutoff, posterior, store, simcfg):
        assert posterior == "SENTINEL_POSTERIOR"   # reused sentinel, never a fit
        seen.append({"seed": simcfg.seed, "tail_fatten": simcfg.tail_fatten})
        is_baseline = simcfg.tail_fatten is None
        # Distinct numbers baseline vs perturbed so deltas are non-trivial.
        return _stub_simresult(
            champ_spain=0.128 if is_baseline else 0.130,
            adv_us=0.80 if is_baseline else 0.802,
            third_sen=0.40 if is_baseline else 0.404,
        )

    monkeypatch.setattr(mod, "_find_cached_production_posterior", fake_find)
    monkeypatch.setattr(mod, "_ratings_for_fixtures", fake_ratings)
    monkeypatch.setattr(mod, "simulate", fake_simulate)

    cfg = _cfg()
    transform = {"edges": [100.0, 250.0, 450.0], "alpha_by_bucket": [0.0, 0.1, 0.3, 0.5]}
    out = mod.run_4b(store=object(), cfg=cfg,
                     alpha_by_bucket=transform["alpha_by_bucket"],
                     edges=transform["edges"])

    # Ran exactly twice: baseline (None) then perturbed (a callable), SAME seed.
    assert len(seen) == 2
    assert seen[0]["tail_fatten"] is None                  # baseline
    assert callable(seen[1]["tail_fatten"])                # perturbed: an alpha closure
    assert seen[0]["seed"] == seen[1]["seed"]              # paired comparison
    # Reused the sentinel posterior at the preferred cutoff (no fresh fit).
    assert "sentinel" in out["posterior_src"].lower()
    assert out["cutoff"] == mod.SENSITIVITY_CUTOFFS[0]
    # The perturbed alpha closure actually maps a |gap| to a positive alpha for a
    # mismatch (Spain 2000 vs Canada 1600 -> gap 400 -> bucket 2 -> alpha 0.3).
    alpha_fn = seen[1]["tail_fatten"]
    assert alpha_fn("Spain", "Canada") == pytest.approx(0.3)
    # Before/after carried for hosts + board + third best-8.
    assert out["hosts"]["United States"]["champion"]["base"] == 0.05
    assert out["third_best8"][0]["team"] in {"Senegal", "Spain", "Canada", "Mexico",
                                             "United States"}
    # A decision verdict is attached.
    assert out["decision"]["verdict"] in {"NO-LIFT", "4c-GO"}


def test_run_4b_no_cached_posterior_errors_without_fresh_fit(mod, monkeypatch):
    monkeypatch.setattr(mod, "_find_cached_production_posterior", lambda cutoff, cfg: None)
    with pytest.raises(RuntimeError, match="config-matched"):
        mod.run_4b(store=object(), cfg=_cfg(), alpha_by_bucket=[0.0, 0.1, 0.3, 0.5],
                   edges=[100.0, 250.0, 450.0])


# --------------------------------------------------------------------------- #
# Zero-Odds-API-credit invariant (source grep).
# --------------------------------------------------------------------------- #
def test_no_live_odds_fetch_in_source():
    src = _MODULE_PATH.read_text()
    for forbidden in ("fetch_live_odds", "odds_live", "import requests", "requests.get",
                      "CallBudget", "scan_value"):
        assert forbidden not in src, f"diagnose_tails must not reference {forbidden!r}"
