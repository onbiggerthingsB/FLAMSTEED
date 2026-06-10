"""Orchestration + report-assembly tests for ``scripts/sweep_tier_weights.py`` (P2c gate).

The script is THIN: a pure non-friendly slice selector, a per-arm config builder, a pure
paired-row builder, a pure ``_verdict`` (the machine-readable ``P2C VERDICT:`` line), and a
pure ``assemble_report``. These tests pin the PURE pieces WITHOUT running a real fit, plus a
``main`` orchestration test with MONKEYPATCHED recorders (no store, no fit, no sampling) that
proves the grid is swept, the arms are paired, and the verdict + report are produced. A
source-level grep pins the zero-Odds-API-credit invariant.

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "sweep_tier_weights.py"


def _load():
    spec = importlib.util.spec_from_file_location("sweep_tier_weights", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


# --------------------------------------------------------------------------- #
# Zero Odds-API credits (source grep).                                          #
# --------------------------------------------------------------------------- #
def test_no_live_fetch_surface():
    src = _MODULE_PATH.read_text()
    assert "fetch_live_odds" not in src
    assert "odds_live" not in src
    assert "THE_ODDS_API_KEY" not in src
    assert "httpx.get" not in src
    assert "_load_env_key" not in src


# --------------------------------------------------------------------------- #
# The locked grid + DEFERRED δ_f note.                                          #
# --------------------------------------------------------------------------- #
def test_locked_friendly_grid(mod):
    # Exactly the brief's grid; 1.0 present (the paired reference / cache-hit arm).
    assert set(mod.FRIENDLY_GRID) == {0.4, 0.6, 0.8, 1.0}
    assert 1.0 in mod.FRIENDLY_GRID


def test_friendly_intercept_is_deferred(mod):
    # The optional δ_f friendly-intercept is explicitly OUT OF SCOPE / deferred.
    src = _MODULE_PATH.read_text()
    assert "DEFERRED" in src and "δ_f" in src


# --------------------------------------------------------------------------- #
# Non-friendly slice selector (pure) — the GATE slice.                          #
# --------------------------------------------------------------------------- #
def test_non_friendly_slice_selector(mod):
    assert mod.is_non_friendly("wc_qualifier")
    assert mod.is_non_friendly("wc_finals")
    assert mod.is_non_friendly("continental_championship")
    assert mod.is_non_friendly("nations_league")
    assert mod.is_non_friendly("other")
    assert not mod.is_non_friendly("friendly")   # friendlies EXCLUDED from the gate


# --------------------------------------------------------------------------- #
# Per-arm config builder (pure): only friendly moves; 1.0 = off block.          #
# --------------------------------------------------------------------------- #
def test_config_for_arm_sets_only_friendly(mod):
    from wcmodel.config import load_config

    base = load_config()
    cfg = mod._config_for_arm(base, 0.4)
    tw = cfg["model"]["likelihood_tier_weights"]
    assert tw == {"friendly": 0.4}               # ONLY friendly is set
    # The base config is not mutated (deepcopy).
    assert "likelihood_tier_weights" not in base["model"] or \
        base["model"].get("likelihood_tier_weights") != {"friendly": 0.4}
    # w=1.0 arm: the off-state block (canonicalizes to absent in the cache key).
    cfg1 = mod._config_for_arm(base, 1.0)
    assert cfg1["model"]["likelihood_tier_weights"] == {"friendly": 1.0}


# --------------------------------------------------------------------------- #
# Paired-row builder (pure): pairs on match_id, gate-filters friendlies.        #
# --------------------------------------------------------------------------- #
def _scored(match_id, fair, outcome, non_friendly):
    return {"match_id": match_id, "fair": fair, "outcome": outcome,
            "non_friendly": non_friendly, "rps": 0.0}


def test_paired_rows_pairs_on_id_and_filters_friendlies(mod):
    base = [
        _scored("m1", (0.6, 0.2, 0.2), "home", True),
        _scored("m2", (0.3, 0.4, 0.3), "draw", False),   # a friendly
        _scored("m3", (0.2, 0.2, 0.6), "away", True),
    ]
    cand = [
        _scored("m1", (0.7, 0.15, 0.15), "home", True),
        _scored("m2", (0.3, 0.4, 0.3), "draw", False),   # friendly -> excluded from gate
        _scored("m3", (0.25, 0.2, 0.55), "away", True),
        _scored("m4", (0.5, 0.3, 0.2), "home", True),    # only in cand -> unpaired -> dropped
    ]
    rows = mod._paired_rows(cand, base, non_friendly_only=True)
    # m1 + m3 pair (non-friendly + present in both); m2 friendly-excluded; m4 unpaired.
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["p_model"] == (0.7, 0.15, 0.15)   # candidate
    assert r0["p_ref"] == (0.6, 0.2, 0.2)       # baseline
    assert r0["outcome"] == "H"
    # Without the gate filter, the friendly m2 is also paired.
    rows_all = mod._paired_rows(cand, base, non_friendly_only=False)
    assert len(rows_all) == 3


# --------------------------------------------------------------------------- #
# Verdict logic (pure) — the machine-readable P2C VERDICT line.                 #
# --------------------------------------------------------------------------- #
def _arms(best_w, best_rps, best_paired, *, base_rps=0.330):
    """A grid of arm rows: w=1.0 baseline (paired=None) + three candidates, only
    ``best_w`` carrying the supplied (rps, paired) so it is the chosen best."""
    arms = [{"friendly_w": 1.0, "rps_nonfriendly": base_rps, "n_nonfriendly": 100,
             "rps_all": base_rps, "n_all": 150, "paired": None}]
    for w in (0.8, 0.6, 0.4):
        if w == best_w:
            arms.append({"friendly_w": w, "rps_nonfriendly": best_rps, "n_nonfriendly": 100,
                         "rps_all": best_rps, "n_all": 150, "paired": best_paired})
        else:
            arms.append({"friendly_w": w, "rps_nonfriendly": base_rps + 0.01,
                         "n_nonfriendly": 100, "rps_all": base_rps + 0.01, "n_all": 150,
                         "paired": {"delta": +0.01, "lo95": -0.001, "hi95": +0.02}})
    return arms


def test_verdict_adopt_when_strictly_beats_beyond_ci(mod):
    # best arm: Δ<0 AND hi95<0 -> the entire CI below zero -> ADOPT.
    arms = _arms(0.6, 0.320, {"delta": -0.010, "lo95": -0.018, "hi95": -0.002})
    v, notes = mod._verdict(arms)
    assert v.startswith("P2C VERDICT: ADOPT tier_w[friendly]=0.6")
    assert "0.320" in v and "-0.01" in v          # rps + paired delta surfaced
    assert "REFIT" in notes                        # the production-refit caveat


def test_verdict_no_lift_when_ci_includes_zero(mod):
    # Δ<0 but hi95>0 -> the CI straddles zero -> NOT strict -> NO-LIFT.
    arms = _arms(0.6, 0.328, {"delta": -0.002, "lo95": -0.010, "hi95": +0.006})
    v, _ = mod._verdict(arms)
    assert v.startswith("P2C VERDICT: NO-LIFT")


def test_verdict_no_lift_when_no_improvement(mod):
    # best candidate is WORSE than 1.0 (Δ>0) -> NO-LIFT.
    arms = _arms(0.6, 0.335, {"delta": +0.005, "lo95": -0.001, "hi95": +0.011})
    v, _ = mod._verdict(arms)
    assert v.startswith("P2C VERDICT: NO-LIFT")


def test_verdict_too_good_flags_audit(mod):
    # An absurd improvement (Δ < -0.02) still ADOPTs but flags a leakage audit.
    arms = _arms(0.4, 0.300, {"delta": -0.030, "lo95": -0.040, "hi95": -0.020})
    v, notes = mod._verdict(arms)
    assert v.startswith("P2C VERDICT: ADOPT")
    assert "TOO-GOOD" in notes


def test_verdict_no_lift_when_unscorable(mod):
    # No scorable candidate -> NO-LIFT (insufficient data), never a crash.
    arms = [{"friendly_w": 1.0, "rps_nonfriendly": float("nan"), "n_nonfriendly": 0,
             "rps_all": float("nan"), "n_all": 0, "paired": None}]
    v, _ = mod._verdict(arms)
    assert v.startswith("P2C VERDICT: NO-LIFT")


# --------------------------------------------------------------------------- #
# Report assembler (pure).                                                      #
# --------------------------------------------------------------------------- #
def test_report_has_table_slice_and_verdict(mod):
    arms = _arms(0.6, 0.320, {"delta": -0.010, "lo95": -0.018, "hi95": -0.002})
    part = {
        "arms": arms, "n_nonfriendly": 100, "n_all": 150,
        "verdict": "P2C VERDICT: ADOPT tier_w[friendly]=0.6 (...)",
        "notes": "0.6 beats 1.0.",
    }
    md = mod.assemble_report(part, cutoff="2024-06-01T00:00:00Z", today="2026-06-10")
    assert "Held-out RPS Sweep" in md
    assert "non-friendly RPS" in md           # primary metric header
    assert "all-matches RPS" in md            # secondary diagnostic header
    assert "paired Δ vs 1.0" in md            # the paired column
    assert "P2C VERDICT: ADOPT" in md         # the verdict line
    assert "DEFERRED" in md                   # δ_f deferral noted in the report body


# --------------------------------------------------------------------------- #
# main() orchestration — MONKEYPATCHED recorders (no store, no fit).            #
# --------------------------------------------------------------------------- #
def test_main_sweeps_grid_and_writes_report(mod, monkeypatch, tmp_path):
    """End-to-end orchestration with EVERYTHING heavy stubbed: a fake store, a fake
    held-out frame, and a fake fit that returns a recorder posterior whose 1X2
    forecast depends on the friendly weight (so a candidate can beat the baseline).
    Proves: every grid point is fit (recorded), arms are paired + scored, and the
    machine-readable verdict + report are produced. NO real fit, NO sampling."""
    import pandas as pd

    # Fake held-out frame: 1 friendly + 2 non-friendly, all priceable.
    heldout = pd.DataFrame([
        {"match_id": "f1", "home_team": "A", "away_team": "B", "home_score": 1,
         "away_score": 0, "neutral": False, "date": pd.Timestamp("2024-07-01"),
         "match_type": "friendly"},
        {"match_id": "q1", "home_team": "A", "away_team": "B", "home_score": 1,
         "away_score": 0, "neutral": False, "date": pd.Timestamp("2024-07-02"),
         "match_type": "wc_qualifier"},
        {"match_id": "q2", "home_team": "A", "away_team": "B", "home_score": 2,
         "away_score": 0, "neutral": True, "date": pd.Timestamp("2024-07-03"),
         "match_type": "continental_championship"},
    ])

    class _RecorderPost:
        """Posterior stub: a confident-home forecast that gets MORE confident (lower
        RPS on home/away wins) as the friendly weight shrinks — so 0.4 beats 1.0."""
        teams = ["A", "B"]

        def __init__(self, friendly_w):
            self.friendly_w = friendly_w

        def predict_1x2(self, home, away, neutral=False):
            # sharper as w decreases: home prob 0.5 + 0.4*(1-w)
            ph = 0.5 + 0.4 * (1.0 - self.friendly_w)
            rest = (1.0 - ph) / 2.0
            return {"home": ph, "draw": rest, "away": rest}

    fits = []

    def _fake_fit_arm(store, cutoff, cfg_arm):
        w = cfg_arm["model"]["likelihood_tier_weights"]["friendly"]
        fits.append(w)
        return _RecorderPost(w), (w == 1.0)   # w=1.0 is the "cache hit" arm

    monkeypatch.setattr(mod, "get_persistent_store", lambda: object())
    monkeypatch.setattr(mod, "_assert_no_leak", lambda store, cutoff: pd.Timestamp("2024-05-31"))
    monkeypatch.setattr(mod, "_heldout_frame", lambda store, cutoff: heldout)
    monkeypatch.setattr(mod, "_fit_arm", _fake_fit_arm)

    out = tmp_path / "tier_weights.md"
    rc = mod.main(["--cutoff", "2024-06-01T00:00:00Z", "--out", str(out)])
    assert rc == 0
    # EVERY grid point was fit (sweep recorder).
    assert sorted(fits) == sorted(mod.FRIENDLY_GRID)
    # The report exists and carries the machine-readable verdict line.
    text = out.read_text()
    assert "P2C VERDICT:" in text
    # Sharper-as-w-shrinks design -> 0.4 is the best arm and strictly beats 1.0.
    assert "P2C VERDICT: ADOPT tier_w[friendly]=0.4" in text
