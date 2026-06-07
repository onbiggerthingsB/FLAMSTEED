"""T7 — ablation + accept/reject backtest runner (the disciplined covariate gate).

``run_ablation`` runs a PAIRED baseline-vs-candidate walk-forward over the SAME
cutoffs/seed/windows/odds — the ONLY difference is ``model.covariates.enabled`` —
and reports, per candidate, a structured verdict: ``delta_rps`` (baseline minus
candidate mean RPS; positive = candidate better), the permutation-null ``null_p``,
``baseline_clv``/``candidate_clv``, and ``verdict ∈ {accept, reject}``.

Accept iff ``delta_rps > 0`` AND ``null_p < 0.05`` AND CLV is not worse — else
reject. The lockbox is read AT MOST ONCE (single-use, P4-T7 mechanism). The whole
harness is signal-only / paper: NO bet, NO spend. Everything synthetic is tainted
NON-REAL by ``walkforward`` so no number here is ever a real edge.
"""
import shutil

import pandas as pd
import pytest

from wcmodel.backtest.lockbox import REGISTRY_PATH
from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.config import load_config


def _paired_inputs():
    """A two-matchday synthetic run (CLEARLY NON-REAL) over teams + dates that exist
    in ``small_store`` so the as-of-cutoff fit resolves. The SAME odds/results/matches
    are reused for both the baseline and the candidate arm — the pairing fixture."""
    md1 = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-20T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
        bookmaker="pinnacle", seed=0,
    )
    md2 = synthetic_odds_sample(
        home="Brazil", away="Argentina", commence="2024-06-25T19:00:00Z",
        entry=(2.60, 3.30, 2.80), close=(2.40, 3.35, 3.00),
        bookmaker="pinnacle", seed=0,
    )
    results_for_settle = pd.DataFrame([
        {"home_team": "Brazil", "away_team": "Croatia",
         "date": pd.Timestamp("2024-06-20"), "home_score": 2, "away_score": 0,
         "tournament": "FIFA World Cup"},
        {"home_team": "Brazil", "away_team": "Argentina",
         "date": pd.Timestamp("2024-06-25"), "home_score": 2, "away_score": 1,
         "tournament": "FIFA World Cup"},
    ])
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-20", "2024-06-25"])})
    return [md1, md2], results_for_settle, matches


_FIT_KWARGS = {"draws": 40, "advi_iters": 800, "seed": 0}
_CUTOFFS = ["2023-06-01", "2024-06-01"]


@pytest.mark.slow
def test_ablation_reports_paired_rps_and_clv_per_covariate(small_store):
    """The runner returns a STRUCTURED per-covariate verdict with all keys, the
    cutoffs recorded in ``_meta`` are the ones passed (paired identity), and the
    verdict is one of {accept, reject}."""
    from wcmodel.backtest.ablation import run_ablation

    samples, rfs, matches = _paired_inputs()
    rep = run_ablation(
        small_store, samples, candidates=["rest_days"], cutoffs=_CUTOFFS,
        config=load_config(), seed=0,
        results_for_settle=rfs, matches=matches, fit_kwargs=_FIT_KWARGS,
    )
    r = rep["rest_days"]
    assert {"baseline_rps", "candidate_rps", "delta_rps", "null_p",
            "baseline_clv", "candidate_clv", "verdict"} <= set(r)
    assert r["verdict"] in {"accept", "reject"}
    # SAME cutoffs/seed for baseline and candidate (paired) — recorded in _meta.
    assert rep["_meta"]["cutoffs"] == _CUTOFFS
    assert rep["_meta"]["seed"] == 0
    # delta_rps is exactly baseline - candidate (positive = candidate better).
    assert r["delta_rps"] == pytest.approx(r["baseline_rps"] - r["candidate_rps"])
    # NON-REAL: the whole report is tainted synthetic (no number here is an edge).
    assert rep["_meta"]["is_synthetic"] is True


@pytest.mark.slow
def test_ablation_is_paired_same_cutoffs_seed_odds_only_enabled_differs(
    small_store, monkeypatch
):
    """PAIRING TEETH: spy on ``walkforward`` and assert the baseline and candidate
    arms are invoked with byte-identical store / odds / results / matches / seed /
    cutoff-grid driver — the ONLY thing that differs between the two arms is
    ``config['model']['covariates']['enabled']`` ([] for baseline, [candidate]
    for candidate). The baseline must NOT be advantaged."""
    import wcmodel.backtest.ablation as ablation_mod

    calls = []
    real_wf = ablation_mod.walkforward

    def _spy(store, odds_samples, **kwargs):
        calls.append({
            "store": store,
            "odds_samples": odds_samples,
            "enabled": list(kwargs["config"]["model"]["covariates"]["enabled"]),
            "seed": kwargs["fit_kwargs"]["seed"],
            "odds_start": kwargs["config"]["backtest"]["odds_start"],
            "results_for_settle": kwargs["results_for_settle"],
            "matches": kwargs["matches"],
        })
        return real_wf(store, odds_samples, **kwargs)

    monkeypatch.setattr(ablation_mod, "walkforward", _spy)

    samples, rfs, matches = _paired_inputs()
    run_ablation = ablation_mod.run_ablation
    run_ablation(
        small_store, samples, candidates=["rest_days"], cutoffs=_CUTOFFS,
        config=load_config(), seed=0,
        results_for_settle=rfs, matches=matches, fit_kwargs=_FIT_KWARGS,
    )

    # Exactly two walkforward arms for one candidate: baseline + candidate.
    assert len(calls) == 2
    baseline = [c for c in calls if c["enabled"] == []]
    candidate = [c for c in calls if c["enabled"] == ["rest_days"]]
    assert len(baseline) == 1 and len(candidate) == 1
    b, c = baseline[0], candidate[0]
    # Identical EVERYTHING except `enabled`: same store object, same odds list,
    # same settle frame, same matches, same seed, same cutoff-grid driver.
    assert b["store"] is c["store"]
    assert b["odds_samples"] is c["odds_samples"]
    assert b["results_for_settle"] is c["results_for_settle"]
    assert b["matches"] is c["matches"]
    assert b["seed"] == c["seed"] == 0
    assert b["odds_start"] == c["odds_start"]


@pytest.mark.slow
def test_ablation_lockbox_is_read_at_most_once(small_store, tmp_path):
    """The ``use_lockbox`` path runs the ACCEPTED set ONCE against the held-out
    single-use lockbox and records it; a SECOND lockbox run is physically refused
    (LockboxUsedError) — the single shot is spent. Uses an ISOLATED temp registry
    so the committed real flag is never burned."""
    from wcmodel.backtest.ablation import run_ablation
    from wcmodel.backtest.lockbox import LockboxRegistry, LockboxUsedError

    temp_registry = tmp_path / "lockbox.json"
    shutil.copy(REGISTRY_PATH, temp_registry)

    samples, rfs, matches = _paired_inputs()
    kw = dict(candidates=["rest_days"], cutoffs=_CUTOFFS, config=load_config(),
              seed=0, results_for_settle=rfs, matches=matches, fit_kwargs=_FIT_KWARGS)

    rep = run_ablation(small_store, samples, use_lockbox=True,
                       lockbox_path=temp_registry, **kw)
    # The lockbox result is recorded and the on-disk single-use flag is now burned.
    assert "lockbox" in rep["_meta"]
    reg = LockboxRegistry.load(path=temp_registry)
    assert reg.used is True

    # A SECOND lockbox evaluation against the same (burned) registry is refused.
    with pytest.raises(LockboxUsedError):
        run_ablation(small_store, samples, use_lockbox=True,
                     lockbox_path=temp_registry, **kw)


def test_ablation_verdict_logic_is_pure_and_gated():
    """The accept/reject decision is a pure function of (delta_rps, null_p, clv) —
    accept iff delta_rps > 0 AND null_p < 0.05 AND candidate_clv >= baseline_clv - tol.
    Tested in isolation (no fit) so the gate logic is locked independent of sampling."""
    from wcmodel.backtest.ablation import _verdict

    tol = 1e-6
    # All three conditions met -> accept.
    assert _verdict(delta_rps=0.01, null_p=0.01, baseline_clv=0.0,
                    candidate_clv=0.0, tol=tol) == "accept"
    # RPS not improved -> reject (even with a great null + CLV).
    assert _verdict(delta_rps=-0.01, null_p=0.001, baseline_clv=0.0,
                    candidate_clv=0.5, tol=tol) == "reject"
    # Null not significant -> reject (a too-weak signal can't accept).
    assert _verdict(delta_rps=0.01, null_p=0.20, baseline_clv=0.0,
                    candidate_clv=0.5, tol=tol) == "reject"
    # CLV got worse beyond tol -> reject (the covariate cost us at the close).
    assert _verdict(delta_rps=0.01, null_p=0.01, baseline_clv=0.10,
                    candidate_clv=0.0, tol=tol) == "reject"
    # CLV within tol (a hair worse) -> still accept.
    assert _verdict(delta_rps=0.01, null_p=0.01, baseline_clv=0.0,
                    candidate_clv=-tol / 2, tol=tol) == "accept"
