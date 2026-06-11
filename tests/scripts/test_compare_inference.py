"""Orchestration + pure-helper tests for ``scripts/compare_inference.py`` (P5).

The harness is THIN over reused house machinery (the sweep_strength_k held-out
protocol, headroom.reliability_table / bootstrap_delta_ci). These tests pin the
PURE pieces — the held-out scoring + reliability extraction, the paired-bootstrap
ΔRPS re-pairing, the runtime projection, the pre-registered adoption GATES, the
machine-readable ``P5 VERDICT:`` grammar, and the report shape — WITHOUT a real
fit, plus a monkeypatched end-to-end ``main`` (recorders for cached_fit / store /
heldout) that proves the orchestration wires a single backend through to a verdict
with NO sampling, and a source grep pinning the zero-Odds-API-credit invariant.

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``); the
house pattern (see tests/scripts/test_sweep_altitude.py).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "compare_inference.py"


def _load():
    spec = importlib.util.spec_from_file_location("compare_inference", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


# --------------------------------------------------------------------------- #
# Zero Odds-API credits (source grep) — house invariant.                       #
# --------------------------------------------------------------------------- #
def test_no_live_odds_fetch_surface():
    src = _MODULE_PATH.read_text()
    assert "fetch_live_odds" not in src
    assert "fetch_event_odds" not in src
    assert "THE_ODDS_API_KEY" not in src
    assert "_load_env_key" not in src
    assert "httpx" not in src


# --------------------------------------------------------------------------- #
# A fake posterior whose predict_1x2 is deterministic per fixture.             #
# --------------------------------------------------------------------------- #
class _FakePost:
    """Deterministic 1X2 by team pair: a strong 'home' favourite unless the names
    encode a draw (team == 'Dx'). Lets score_backend run with no real model."""

    def __init__(self, teams):
        self.teams = list(teams)
        self.idata = None

    def predict_1x2(self, home, away, neutral=False, max_goals=10, covariates=None,
                    host_factor=None):
        if home.startswith("D") and away.startswith("D"):
            return {"home": 0.30, "draw": 0.40, "away": 0.30}
        return {"home": 0.60, "draw": 0.25, "away": 0.15}


def _heldout(rows):
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# score_backend — RPS + reliability extraction (pure, no fit).                 #
# --------------------------------------------------------------------------- #
def test_score_backend_priceable_set_and_reliability(mod):
    teams = ["A", "B", "Dx", "Dy"]
    elo = {t: 1500.0 for t in teams}
    heldout = _heldout([
        # A beats B (home win) -> favourite 'home' HIT.
        {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 0, "neutral": False},
        # Dx vs Dy draws -> favourite 'draw' HIT, draw HIT.
        {"home_team": "Dx", "away_team": "Dy", "home_score": 1, "away_score": 1, "neutral": True},
        # A team not in the posterior -> SKIPPED (priceable-set discipline).
        {"home_team": "A", "away_team": "Zz", "home_score": 1, "away_score": 0, "neutral": False},
    ])
    with mock.patch.object(mod, "elo_baseline_1x2",
                           return_value={"home": 0.34, "draw": 0.32, "away": 0.34}):
        sc = mod.score_backend(_FakePost(teams), heldout, elo, config={})
    assert sc["n"] == 2  # the Zz fixture is dropped (not in teams)
    assert len(sc["rows"]) == 2
    # FAVORITE reliability: A->home@0.60 (hit), Dx->draw@0.40 (hit) -> both hits.
    assert sc["fav_probs"] == [0.60, 0.40]
    assert sc["fav_hits"] == [True, True]
    # DRAW reliability: A match draw_prob 0.25 (no draw), Dx draw_prob 0.40 (draw).
    assert sc["draw_probs"] == [0.25, 0.40]
    assert sc["draw_hits"] == [False, True]
    # rows carry the headroom contract (ordered triples + H/D/A letter).
    assert sc["rows"][0]["outcome"] == "H" and sc["rows"][1]["outcome"] == "D"
    assert sc["rows"][0]["p_model"] == (0.60, 0.25, 0.15)


# --------------------------------------------------------------------------- #
# paired_delta_vs_baseline — re-pairing into bootstrap_delta_ci.               #
# --------------------------------------------------------------------------- #
def test_paired_delta_backend_minus_advi_sign(mod):
    """A backend that is UNIFORMLY better than advi on every fixture must yield a
    negative ΔRPS (rps_backend − rps_advi < 0) with the whole CI below 0."""
    # Backend nails the outcome (prob 0.98 on the realised home win); advi is flat.
    backend_rows = [{"p_model": (0.98, 0.01, 0.01), "outcome": "H"} for _ in range(40)]
    baseline_rows = [{"p_ref": (0.34, 0.33, 0.33), "outcome": "H"} for _ in range(40)]
    ci = mod.paired_delta_vs_baseline(backend_rows, baseline_rows, seed=0, n_boot=2000)
    assert ci["n"] == 40
    assert ci["delta"] < 0.0 and ci["hi95"] < 0.0     # backend strictly better
    assert mod.rps_lift_passes(ci) is True


def test_paired_delta_no_lift_when_equal(mod):
    """Identical forecasts -> ΔRPS ~ 0, CI spans 0 -> NO lift."""
    rows_a = [{"p_model": (0.5, 0.3, 0.2), "outcome": "H"} for _ in range(30)]
    rows_b = [{"p_ref": (0.5, 0.3, 0.2), "outcome": "H"} for _ in range(30)]
    ci = mod.paired_delta_vs_baseline(rows_a, rows_b, seed=1, n_boot=2000)
    assert abs(ci["delta"]) < 1e-9
    assert mod.rps_lift_passes(ci) is False


# --------------------------------------------------------------------------- #
# Runtime projection + gates.                                                   #
# --------------------------------------------------------------------------- #
def test_project_runtime_min_adds_sim_stage_remainder(mod):
    assert mod.project_runtime_min(6.0) == 6.0 + mod.SIM_STAGE_REMAINDER_MIN
    assert mod.project_runtime_min(40.0, remainder_min=10.0) == 50.0


def test_runtime_compatible_budget_edge(mod):
    assert mod.runtime_compatible(mod.NIGHTLY_BUDGET_MIN) is True   # exactly at budget = OK
    assert mod.runtime_compatible(mod.NIGHTLY_BUDGET_MIN + 0.1) is False


# --------------------------------------------------------------------------- #
# Verdict grammar — the four pre-registered forms (machine-readable).          #
# --------------------------------------------------------------------------- #
def test_verdict_adopt_when_lift_and_runtime_ok(mod):
    v = mod.verdict_line(backend="nuts", is_baseline=False,
                         delta_ci={"delta": -0.002, "lo95": -0.004, "hi95": -0.0008},
                         projected_min=21.0)
    assert v.startswith("P5 VERDICT: ADOPT nuts")


def test_verdict_deep_refit_only_when_lift_but_runtime_blown(mod):
    v = mod.verdict_line(backend="nuts", is_baseline=False,
                         delta_ci={"delta": -0.002, "lo95": -0.004, "hi95": -0.0008},
                         projected_min=180.0)
    assert v.startswith("P5 VERDICT: DEEP-REFIT-ONLY CANDIDATE")
    assert "nuts" in v


def test_verdict_no_adopt_when_no_lift(mod):
    v = mod.verdict_line(backend="fullrank_advi", is_baseline=False,
                         delta_ci={"delta": 0.001, "lo95": -0.001, "hi95": 0.003},
                         projected_min=21.0)
    assert v.startswith("P5 VERDICT: NO-ADOPT fullrank_advi")


def test_verdict_baseline_for_advi(mod):
    v = mod.verdict_line(backend="advi", is_baseline=True, delta_ci=None,
                         projected_min=21.0)
    assert v.startswith("P5 VERDICT: BASELINE advi")


def test_every_verdict_is_one_grammar_line(mod):
    """The controller greps a SINGLE line starting 'P5 VERDICT: '. Every form must
    be exactly one line with that prefix."""
    forms = [
        mod.verdict_line(backend="nuts", is_baseline=False,
                         delta_ci={"delta": -0.002, "lo95": -0.004, "hi95": -0.001},
                         projected_min=21.0),
        mod.verdict_line(backend="nuts", is_baseline=False,
                         delta_ci={"delta": -0.002, "lo95": -0.004, "hi95": -0.001},
                         projected_min=999.0),
        mod.verdict_line(backend="fullrank_advi", is_baseline=False,
                         delta_ci={"delta": 0.001, "lo95": -0.001, "hi95": 0.003},
                         projected_min=21.0),
        mod.verdict_line(backend="advi", is_baseline=True, delta_ci=None,
                         projected_min=21.0),
    ]
    for v in forms:
        assert "\n" not in v
        assert v.startswith("P5 VERDICT: ")


# --------------------------------------------------------------------------- #
# Report assembler — shape (pure).                                             #
# --------------------------------------------------------------------------- #
def test_assemble_report_has_all_sections(mod):
    fav = mod.reliability_table([0.6, 0.4], [True, True])
    draw = mod.reliability_table([0.25, 0.40], [False, True])
    part = {
        "backend": "nuts", "cutoff": "2024-06-01T00:00:00Z", "is_baseline": False,
        "model_rps": 0.330, "elo_rps": 0.340, "n": 2111, "fit_seconds": 1800.0,
        "projected_min": 45.0,
        "delta_ci": {"delta": -0.002, "lo95": -0.004, "hi95": -0.0008, "n": 2111},
        "nuts_diag": {"divergences": 0, "min_ess_bulk": 800.0, "max_rhat": 1.003,
                      "n_chains": 4, "n_draws": 1000},
        "fav_table": fav, "draw_table": draw,
        "verdict": "P5 VERDICT: ADOPT nuts (...)", "reablation": None,
    }
    md = mod.assemble_report(part)
    assert "P5 INFERENCE COMPARISON" in md
    assert "n=2111" in md                       # held-out count stated
    assert "elo_baseline_RPS" in md             # apples-to-apples Elo baseline
    assert "FAVORITE" in md and "DRAW" in md     # both reliability tables
    assert "divergences=0" in md                # NUTS diagnostics surfaced
    assert "max_rhat=1.003" in md
    assert "ΔRPS (backend − advi)" in md         # paired bootstrap line
    assert "projected full daily_update" in md  # runtime projection PRINTED
    assert "P5 VERDICT: ADOPT nuts" in md        # verdict verbatim


def test_assemble_report_includes_reablation_when_present(mod):
    part = {
        "backend": "nuts", "cutoff": "2024-06-01T00:00:00Z", "is_baseline": False,
        "model_rps": 0.330, "elo_rps": 0.340, "n": 2111, "fit_seconds": 100.0,
        "projected_min": 16.7, "delta_ci": None, "nuts_diag": None,
        "fav_table": mod.reliability_table([0.6], [True]),
        "draw_table": mod.reliability_table([0.2], [False]),
        "verdict": "P5 VERDICT: ADOPT nuts (...)",
        "reablation": {"on_rps": 0.330, "off_rps": 0.332, "mechanism": "c",
                       "strength": 0.5,
                       "delta_ci": {"delta": -0.002, "lo95": -0.004, "hi95": -0.0009, "n": 2111}},
    }
    md = mod.assemble_report(part)
    assert "WIDENING RE-ABLATION" in md
    assert "widening ON" in md and "widening OFF" in md
    assert "HELPS" in md  # hi95 < 0 -> the on-arm beats off


# --------------------------------------------------------------------------- #
# Orchestration — monkeypatched main (NO real fit, NO sampling).               #
# --------------------------------------------------------------------------- #
def test_main_orchestration_single_backend_no_real_fit(mod, tmp_path, capsys):
    """End-to-end ``main`` for ONE backend with cached_fit / store / heldout /
    elo monkeypatched. Proves the orchestration runs to a single P5 VERDICT line
    with NO sampling (house pattern: recorders, no real fits)."""
    teams = ["A", "B", "Dx", "Dy"]
    heldout = _heldout([
        {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 0, "neutral": False},
        {"home_team": "Dx", "away_team": "Dy", "home_score": 1, "away_score": 1, "neutral": True},
    ])

    fake_post = _FakePost(teams)

    def fake_cached_fit(**kwargs):
        # No sampling — return the fake posterior + a MISS so wall-clock is measured.
        return fake_post, {"cache_hit": False, "key": "fake"}

    with mock.patch.object(mod._model_cache, "cached_fit", side_effect=fake_cached_fit), \
         mock.patch.object(mod, "get_persistent_store", return_value=object()), \
         mock.patch.object(mod, "_assert_no_leak", return_value=pd.Timestamp("2024-05-30")), \
         mock.patch.object(mod, "_heldout_frame", return_value=heldout), \
         mock.patch.object(mod, "_elo_as_of_cutoff", return_value={t: 1500.0 for t in teams}), \
         mock.patch.object(mod, "elo_baseline_1x2",
                           return_value={"home": 0.34, "draw": 0.32, "away": 0.34}), \
         mock.patch.object(mod, "CACHE_DIR", tmp_path):
        rc = mod.main(["--backend", "advi", "--out", str(tmp_path / "report.txt")])

    assert rc == 0
    out = capsys.readouterr().out
    # Exactly one machine-readable verdict line; advi is the baseline.
    verdicts = [ln for ln in out.splitlines() if ln.startswith("P5 VERDICT: ")]
    assert len(verdicts) == 1
    assert verdicts[0].startswith("P5 VERDICT: BASELINE advi")
    # The advi run persisted its baseline rows for later backends.
    assert mod._baseline_path(tmp_path, "2024-06-01T00:00:00Z").exists()
    # The report file was written.
    assert (tmp_path / "report.txt").exists()


def test_main_nuts_scores_delta_against_persisted_baseline(mod, tmp_path, capsys):
    """A nuts run, with an advi baseline already on disk, must compute a paired
    ΔRPS against it and emit an ADOPT/NO-ADOPT/DEEP-REFIT verdict (NOT 'BASELINE').
    Proves the cross-backend ΔRPS path + the single-backend-per-invocation design.
    NO sampling (cached_fit faked)."""
    teams = ["A", "B"]
    heldout = _heldout([
        {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 0, "neutral": False},
    ] * 30)

    # Persist an advi baseline that is FLAT (poor) so nuts (sharp) beats it.
    import json
    bpath = mod._baseline_path(tmp_path, "2024-06-01T00:00:00Z")
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(json.dumps({"cutoff": "2024-06-01T00:00:00Z",
                                 "rows": [{"p_model": [0.34, 0.33, 0.33], "outcome": "H"}] * 30}))

    fake_post = _FakePost(teams)  # predicts home@0.60 -> sharper than flat baseline

    with mock.patch.object(mod._model_cache, "cached_fit",
                           side_effect=lambda **k: (fake_post, {"cache_hit": False, "key": "x"})), \
         mock.patch.object(mod, "get_persistent_store", return_value=object()), \
         mock.patch.object(mod, "_assert_no_leak", return_value=pd.Timestamp("2024-05-30")), \
         mock.patch.object(mod, "_heldout_frame", return_value=heldout), \
         mock.patch.object(mod, "_elo_as_of_cutoff", return_value={t: 1500.0 for t in teams}), \
         mock.patch.object(mod, "elo_baseline_1x2",
                           return_value={"home": 0.34, "draw": 0.32, "away": 0.34}), \
         mock.patch.object(mod, "CACHE_DIR", tmp_path):
        rc = mod.main(["--backend", "nuts"])

    assert rc == 0
    out = capsys.readouterr().out
    verdicts = [ln for ln in out.splitlines() if ln.startswith("P5 VERDICT: ")]
    assert len(verdicts) == 1
    # nuts scored against the persisted baseline -> NOT the baseline verdict.
    assert "BASELINE" not in verdicts[0]
    assert verdicts[0].split()[2] == "nuts" or "nuts" in verdicts[0]
    # NUTS diagnostics were attempted on the fresh fit (fake idata is None ->
    # nuts_diagnostics returns all-None, but the report still has the [nuts] block).
    assert "[nuts]" in out
