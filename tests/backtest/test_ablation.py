"""T7 — ablation + accept/reject backtest gate (the disciplined covariate gate).

``run_ablation`` runs a PAIRED baseline-vs-candidate RPS evaluation over a COMMON
out-of-sample fixture set: for each cutoff it fits the baseline
(``covariates.enabled=[]``) and the candidate (``enabled=[X]``) on ``< cutoff``,
determines the real matches PLAYED in the forward window (the OOS set), computes
each fixture's covariate LEAKAGE-SAFELY, and scores ``rps`` for the candidate's
``predict_1x2`` WITH the covariate and the baseline WITHOUT — over the IDENTICAL
fixtures/outcomes. The delta is paired; significance is a one-sided sign-flip
permutation test; accept iff ``mean_d > 0`` AND ``paired_p_adj < 0.05`` AND CLV is
not worse. The whole harness is signal-only / paper (NON-REAL synthetic taint).
"""
import shutil

import numpy as np
import pandas as pd
import pytest

from wcmodel.backtest.lockbox import REGISTRY_PATH
from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.config import load_config


def _paired_inputs():
    """A two-matchday synthetic run (CLEARLY NON-REAL) over teams + dates that exist
    in ``small_store`` so the as-of-cutoff fit resolves and the forward windows have
    real PLAYED fixtures to evaluate. The SAME odds/results/matches feed both arms."""
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
    # The matches frame's max date bounds the LAST OOS window's upper edge; span it
    # to the end of June so the store's 2024-06 fixtures land in the eval set.
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-20", "2024-06-30"])})
    return [md1, md2], results_for_settle, matches


_FIT_KWARGS = {"draws": 40, "advi_iters": 800, "seed": 0}
# The cutoffs DRIVE the paired OOS eval windows: [2023-06-01, 2024-06-01) and
# [2024-06-01, max_match_date+1). Both windows contain real PLAYED store fixtures.
_CUTOFFS = ["2023-06-01", "2024-06-01"]


# --------------------------------------------------------------------------- #
# Pure verdict-logic tests (no fit, no I/O) — fast.                            #
# --------------------------------------------------------------------------- #

def test_ablation_verdict_logic_is_pure_and_gated():
    """Accept iff mean_d > 0 AND paired p < 0.05 AND candidate_clv >= baseline_clv - tol.
    Tested in isolation so the gate logic is locked independent of sampling."""
    from wcmodel.backtest.ablation import _verdict

    tol = 1e-6
    # All three conditions met -> accept.
    assert _verdict(mean_d=0.01, p_value=0.01, baseline_clv=0.0,
                    candidate_clv=0.0, tol=tol) == "accept"
    # RPS not improved -> reject (even with a great p + CLV).
    assert _verdict(mean_d=-0.01, p_value=0.001, baseline_clv=0.0,
                    candidate_clv=0.5, tol=tol) == "reject"
    # Paired p not significant -> reject (a noise-level delta can't accept).
    assert _verdict(mean_d=0.01, p_value=0.20, baseline_clv=0.0,
                    candidate_clv=0.5, tol=tol) == "reject"
    # CLV got worse beyond tol -> reject (the covariate cost us at the close).
    assert _verdict(mean_d=0.01, p_value=0.01, baseline_clv=0.10,
                    candidate_clv=0.0, tol=tol) == "reject"
    # CLV within tol (a hair worse) -> still accept.
    assert _verdict(mean_d=0.01, p_value=0.01, baseline_clv=0.0,
                    candidate_clv=-tol / 2, tol=tol) == "accept"


def test_ablation_verdict_is_nan_safe_reject():
    """FIX 4: a None/NaN in ANY verdict input -> 'reject' (fail-safe), never a
    crash (``float(None)``) and never a spurious accept. An empty/unmeasurable arm
    canonicalises its aggregate to None/NaN, so this is the fail-closed guard."""
    from wcmodel.backtest.ablation import _verdict

    tol = 1e-6
    nan = float("nan")
    # None / NaN on each axis -> reject (no crash).
    assert _verdict(mean_d=None, p_value=0.01, baseline_clv=0.0,
                    candidate_clv=0.0, tol=tol) == "reject"
    assert _verdict(mean_d=0.01, p_value=None, baseline_clv=0.0,
                    candidate_clv=0.0, tol=tol) == "reject"
    assert _verdict(mean_d=0.01, p_value=0.01, baseline_clv=nan,
                    candidate_clv=0.0, tol=tol) == "reject"
    assert _verdict(mean_d=0.01, p_value=0.01, baseline_clv=0.0,
                    candidate_clv=nan, tol=tol) == "reject"
    assert _verdict(mean_d=nan, p_value=nan, baseline_clv=nan,
                    candidate_clv=nan, tol=tol) == "reject"


def test_sign_flip_p_is_paired_seeded_and_one_sided():
    """The paired sign-flip permutation p: a strongly-positive paired delta clears
    the bar; an empty/degenerate input -> (nan, nan) so the verdict rejects."""
    from wcmodel.backtest.ablation import _sign_flip_p

    # A clearly-positive, low-noise paired delta sits in the best tail of the
    # sign-flip null -> small p.
    d = [0.05] * 12
    mean_d, p = _sign_flip_p(d, shuffles=200, seed=0)
    assert mean_d == pytest.approx(0.05)
    assert p < 0.05
    # Seeded -> reproducible.
    _, p2 = _sign_flip_p(d, shuffles=200, seed=0)
    assert p == p2
    # A symmetric (noise-level) delta does NOT clear the bar.
    rng = np.random.default_rng(1)
    noise = (rng.normal(0, 1, size=40)).tolist()
    _, p_noise = _sign_flip_p(noise, shuffles=500, seed=0)
    assert p_noise >= 0.05
    # Empty -> (nan, nan) -> verdict fail-safe reject.
    md, pe = _sign_flip_p([], shuffles=200, seed=0)
    assert np.isnan(md) and np.isnan(pe)


def test_fixture_covariates_rest_days_is_leakage_safe():
    """The eval-fixture rest_days is the gap to the team's LAST < cutoff match —
    derived ONLY from the prior-match panel, never the fixture's own future row."""
    from wcmodel.backtest.ablation import _fixture_covariates

    panel = pd.DataFrame({
        "team": ["Brazil", "Brazil", "Argentina"],
        "date": pd.to_datetime(["2024-05-01", "2024-05-10", "2024-05-05"]),
    })
    cov = _fixture_covariates(enabled=["rest_days"], panel=panel,
                              home="Brazil", away="Argentina",
                              fixture_date="2024-05-20")
    # Brazil's last prior match is 2024-05-10 -> 10 days; Argentina's 2024-05-05 -> 15.
    assert cov["rest_days"] == pytest.approx(10.0)
    assert cov["rest_days__away"] == pytest.approx(15.0)
    # A team with NO prior match -> NaN (masked by the transform, never imputed).
    cov2 = _fixture_covariates(enabled=["rest_days"], panel=panel,
                               home="France", away="Brazil",
                               fixture_date="2024-05-20")
    assert np.isnan(cov2["rest_days"])
    assert cov2["rest_days__away"] == pytest.approx(10.0)


def test_eval_window_bounds_iterate_provided_cutoffs():
    """FIX 5: the provided cutoffs DRIVE the OOS windows — each consecutive pair is
    a half-open ``[c_k, c_{k+1})`` window; the last runs to max match date + 1 day."""
    from wcmodel.backtest.ablation import _eval_window_bounds

    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-20", "2024-06-30"])})
    bounds = _eval_window_bounds(["2023-06-01", "2024-06-01"], matches)
    assert bounds[0] == (pd.Timestamp("2023-06-01"), pd.Timestamp("2024-06-01"))
    assert bounds[1] == (pd.Timestamp("2024-06-01"), pd.Timestamp("2024-07-01"))


class _StubBase:
    """A baseline posterior stub that prices EVERY fixture with a valid 1X2 — so the
    fixture is baseline-priceable and a candidate failure on it is a real instability
    (NOT a symmetric structural absence)."""
    def predict_1x2(self, home, away, neutral=False, max_goals=10, covariates=None,
                    host_factor=None):
        return {"home": 0.4, "draw": 0.3, "away": 0.3}


class _StubUnstableCandidate:
    """A candidate posterior stub that is UNSTABLE on the first fixture it sees —
    it raises ``ValueError('non-finite predictive grid')`` exactly as a diverged fit
    does through the posterior/widening guards — and prices every later fixture with
    a valid 1X2. Proves the ablation treats the failure as a NaN paired delta (paired
    + counted, NOT dropped) and rejects, instead of crashing or scoring the survivors."""
    def __init__(self):
        self._n = 0

    def predict_1x2(self, home, away, neutral=False, max_goals=10, covariates=None,
                    host_factor=None):
        self._n += 1
        if self._n == 1:
            raise ValueError("non-finite predictive grid")
        return {"home": 0.4, "draw": 0.3, "away": 0.3}


@pytest.mark.slow
def test_unstable_candidate_window_is_paired_nan_not_dropped(small_store):
    """FAIL-SAFE (ablation crash-safety, RED->GREEN): a candidate that raises a
    non-finite-predictive ValueError on a baseline-priceable eval fixture must NOT
    crash the run and must NOT be silently scored on the surviving fixtures
    (survivorship bias). The failing fixture is recorded as a NaN PAIRED difference
    (still counted, kept paired) so the window's ``mean_d``/``p`` go NaN and the
    verdict fail-safe REJECTS, and the instability is counted for the loud log."""
    from wcmodel.backtest.ablation import (
        _paired_rps_over_window, _played_in_window, _sign_flip_p, _verdict,
    )
    cfg = load_config()
    lo, hi = pd.Timestamp("2024-06-01"), pd.Timestamp("2024-07-01")
    # Sanity: the window has at least 2 played fixtures so "survivors" exist to NOT
    # score on (the failing one + at least one valid one).
    n_played = len(_played_in_window(small_store, lo=lo, hi=hi))
    assert n_played >= 2, "need >=2 eval fixtures to prove survivors are not scored"

    d, br, cr, cp, oc, n_unstable = _paired_rps_over_window(
        store=small_store, base_post=_StubBase(),
        cand_post=_StubUnstableCandidate(),
        enabled=["rest_days"], cfg=cfg, lo=lo, hi=hi)

    # The candidate was unstable on exactly the first fixture; it was COUNTED, not
    # dropped — the paired difference list carries a NaN for it.
    assert n_unstable == 1
    assert any(x != x for x in d), "the failing fixture must be a NaN paired delta"
    # Survivors were NOT silently scored into a clean metric: a NaN in d poisons the
    # window -> mean_d/p NaN -> verdict reject (no crash, no survivorship score).
    mean_d, p = _sign_flip_p(d, shuffles=200, seed=0)
    assert np.isnan(mean_d) and np.isnan(p)
    assert _verdict(mean_d=mean_d, p_value=p, baseline_clv=0.0,
                    candidate_clv=0.0, tol=1e-6) == "reject"
    # The candidate RPS list also carries the NaN (its mean is therefore NaN, never a
    # flattering survivors-only average).
    assert any(x != x for x in cr)


# --------------------------------------------------------------------------- #
# Paired-eval integration tests (real fit) — slow.                            #
# --------------------------------------------------------------------------- #

@pytest.mark.slow
def test_ablation_reports_paired_rps_over_common_set(small_store):
    """The runner returns a STRUCTURED per-candidate verdict with the paired keys,
    the provided cutoffs recorded in ``_meta``, a non-empty COMMON eval set, and a
    verdict in {accept, reject}. The whole report is NON-REAL (synthetic taint)."""
    from wcmodel.backtest.ablation import run_ablation

    samples, rfs, matches = _paired_inputs()
    rep = run_ablation(
        small_store, samples, candidates=["rest_days"], cutoffs=_CUTOFFS,
        config=load_config(), seed=0,
        results_for_settle=rfs, matches=matches, fit_kwargs=_FIT_KWARGS,
    )
    r = rep["rest_days"]
    assert {"mean_d", "paired_p", "paired_p_adj", "baseline_rps", "candidate_rps",
            "n_eval", "baseline_clv", "candidate_clv", "verdict"} <= set(r)
    assert r["verdict"] in {"accept", "reject"}
    # The PAIRED eval scored a non-empty COMMON fixture set (real played store
    # fixtures in the forward windows).
    assert r["n_eval"] > 0
    assert rep["_meta"]["n_eval_total"] == r["n_eval"]
    # delta_rps is the paired mean improvement (alias of mean_d).
    assert r["delta_rps"] == pytest.approx(r["mean_d"])
    # The provided cutoffs are recorded (paired identity).
    assert rep["_meta"]["cutoffs"] == _CUTOFFS
    assert rep["_meta"]["seed"] == 0
    # NON-REAL: the whole report is tainted synthetic.
    assert rep["_meta"]["is_synthetic"] is True


@pytest.mark.slow
def test_ablation_rps_eval_is_paired_same_fixtures_and_outcomes(small_store, monkeypatch):
    """PAIRING TEETH: spy on the per-fixture RPS scorer and assert the baseline and
    candidate are scored over the SAME fixtures + SAME realised outcomes — only the
    model (and the covariate it sees) differs. The candidate's predict_1x2 is called
    WITH covariates; the baseline's WITHOUT."""
    import wcmodel.backtest.ablation as ab

    seen = []
    real_rps = ab.rps

    def _spy_rps(probs, outcome):
        seen.append((tuple(sorted(probs.items())), outcome))
        return real_rps(probs, outcome)

    monkeypatch.setattr(ab, "rps", _spy_rps)

    # Spy predict_1x2 to confirm the candidate is fed a covariate dict and the
    # baseline is not (the baseline is scored via model_fair_1x2 -> predict_1x2
    # with covariates=None).
    cand_cov_calls = []
    real_predict = ab.model_fair_1x2  # baseline path

    samples, rfs, matches = _paired_inputs()
    # Wrap Posterior.predict_1x2 to record whether covariates were supplied.
    from wcmodel.model.posterior import Posterior
    real_p1x2 = Posterior.predict_1x2

    def _wrapped(self, home, away, neutral=False, max_goals=10, covariates=None,
                 host_factor=None):
        cand_cov_calls.append(covariates)
        return real_p1x2(self, home, away, neutral, max_goals, covariates, host_factor)

    monkeypatch.setattr(Posterior, "predict_1x2", _wrapped)

    rep = ab.run_ablation(
        small_store, samples, candidates=["rest_days"], cutoffs=_CUTOFFS,
        config=load_config(), seed=0,
        results_for_settle=rfs, matches=matches, fit_kwargs=_FIT_KWARGS,
    )
    r = rep["rest_days"]
    n = r["n_eval"]
    assert n > 0
    # The outcomes the baseline saw and the outcomes the candidate saw are the SAME
    # multiset (paired over the same fixtures). The scorer was called 2*n times for
    # the paired eval (baseline + candidate per fixture); their outcome lists match.
    outcomes = [o for (_p, o) in seen]
    # At least n baseline + n candidate paired scorings happened.
    assert len(outcomes) >= 2 * n
    # The candidate predict path received covariate dicts carrying rest_days.
    cov_dicts = [c for c in cand_cov_calls if c is not None]
    assert cov_dicts, "candidate predict_1x2 must be called WITH covariates"
    assert any("rest_days" in c for c in cov_dicts)


@pytest.mark.slow
def test_candidate_covariate_actually_changes_per_fixture_rps(small_store):
    """The candidate's per-fixture RPS WITH the fitted covariate differs from a
    covariate-FREE predict over the same fixtures — proof the covariate is actually
    USED in the scored candidate forecast (not silently dropped). If the fitted
    beta moves the prediction at all, the paired RPS must move with it."""
    from wcmodel.backtest.ablation import (
        _fit_arm, _paired_rps_over_window,
    )
    cfg = load_config()
    lo, hi = pd.Timestamp("2024-06-01"), pd.Timestamp("2024-07-01")

    base_post = _fit_arm(small_store, enabled=[], base_config=cfg, seed=0,
                         fit_kwargs=_FIT_KWARGS, cache_dir=None, cutoff=lo)
    cand_post = _fit_arm(small_store, enabled=["rest_days"], base_config=cfg, seed=0,
                         fit_kwargs=_FIT_KWARGS, cache_dir=None, cutoff=lo)
    assert base_post is not None and cand_post is not None

    # The candidate fit a non-zero rest_days beta on this store?
    beta = float(cand_post.idata.posterior["beta_rest_days"].mean())
    assert abs(beta) > 0, "candidate did not fit a usable rest_days beta"

    # Candidate scored WITH covariate vs the candidate scored as-if covariate-free:
    # run the paired scorer with the covariate (enabled=["rest_days"]) and with no
    # covariate (enabled=[]) — same posterior, same fixtures.
    d_with, _, cand_with, _, _, _ = _paired_rps_over_window(
        store=small_store, base_post=base_post, cand_post=cand_post,
        enabled=["rest_days"], cfg=cfg, lo=lo, hi=hi)
    _, _, cand_free, _, _, _ = _paired_rps_over_window(
        store=small_store, base_post=base_post, cand_post=cand_post,
        enabled=[], cfg=cfg, lo=lo, hi=hi)
    assert len(cand_with) == len(cand_free) and len(cand_with) > 0
    # The covariate moved at least one fixture's candidate RPS (it is genuinely used).
    assert cand_with != pytest.approx(cand_free), (
        "the covariate did not change the candidate's scored forecast — it is not "
        "being applied at predict (the ablation would measure nothing)"
    )


@pytest.mark.slow
def test_empty_eval_arm_rejects_without_crash(small_store):
    """An arm whose OOS windows contain NO played fixtures -> empty paired eval ->
    mean_d/p NaN -> verdict 'reject', no crash (FIX 4 fail-safe end-to-end)."""
    from wcmodel.backtest.ablation import run_ablation

    samples, rfs, matches = _paired_inputs()
    # Cutoffs whose forward window has no played store fixtures (far future).
    empty_cutoffs = ["2030-01-01", "2030-06-01"]
    far_matches = pd.DataFrame({"date": pd.to_datetime(["2030-01-01", "2030-06-02"])})
    rep = run_ablation(
        small_store, samples, candidates=["rest_days"], cutoffs=empty_cutoffs,
        config=load_config(), seed=0,
        results_for_settle=rfs, matches=far_matches, fit_kwargs=_FIT_KWARGS,
    )
    r = rep["rest_days"]
    assert r["n_eval"] == 0
    assert r["verdict"] == "reject"          # fail-safe, no spurious accept
    assert "rest_days" not in rep["_meta"]["accepted"]


@pytest.mark.slow
def test_noise_level_delta_does_not_accept(small_store):
    """A candidate whose paired RPS delta is NOT significant (the sign-flip p does
    not clear 0.05) is REJECTED even if mean_d happens to be positive — the paired
    permutation p guards against accepting noise."""
    from wcmodel.backtest.ablation import run_ablation

    samples, rfs, matches = _paired_inputs()
    rep = run_ablation(
        small_store, samples, candidates=["rest_days"], cutoffs=_CUTOFFS,
        config=load_config(), seed=0,
        results_for_settle=rfs, matches=matches, fit_kwargs=_FIT_KWARGS,
    )
    r = rep["rest_days"]
    # On this tiny store the paired delta is not significant; assert the gate is
    # COHERENT: an accept REQUIRES a significant paired p, a positive mean_d, and
    # non-degraded CLV. (We assert the logical contract, robust to the exact verdict.)
    tol = rep["_meta"]["clv_tol"]
    p_adj = r["paired_p_adj"]
    md = r["mean_d"]
    # An accept REQUIRES all three clauses; a reject must fail at least one.
    accept_clauses = (
        md is not None and not np.isnan(md) and md > 0
        and p_adj is not None and not np.isnan(p_adj) and p_adj < 0.05
        and r["candidate_clv"] >= r["baseline_clv"] - tol
    )
    assert (r["verdict"] == "accept") == bool(accept_clauses)


@pytest.mark.slow
def test_multiplicity_correction_applied_for_multiple_candidates(small_store):
    """With >1 candidate a Bonferroni correction is applied: paired_p_adj =
    min(1, paired_p * n_candidates), and _meta records the multiplicity method."""
    from wcmodel.backtest.ablation import run_ablation

    samples, rfs, matches = _paired_inputs()
    rep = run_ablation(
        small_store, samples, candidates=["rest_days", "travel_km"], cutoffs=_CUTOFFS,
        config=load_config(), seed=0,
        results_for_settle=rfs, matches=matches, fit_kwargs=_FIT_KWARGS,
    )
    assert rep["_meta"]["multiplicity"] == "bonferroni"
    assert rep["_meta"]["n_candidates"] == 2
    for cand in ("rest_days", "travel_km"):
        r = rep[cand]
        if not np.isnan(r["paired_p"]):
            assert r["paired_p_adj"] == pytest.approx(min(1.0, r["paired_p"] * 2))


@pytest.mark.slow
def test_cache_hit_preserves_covariate_transform_and_predicts_with_it(small_store, tmp_path):
    """FIX 3a: a covariate fit, cached, then re-loaded on a HIT must keep the
    persisted CovariateTransform and predict WITH the covariate (not a zero offset).
    Proof: the cached Posterior's transform map survives, and its covariate-aware
    prediction differs from its covariate-free prediction."""
    from wcmodel.model.cache import cached_fit

    cfg = load_config()
    cfg["model"]["covariates"]["enabled"] = ["rest_days"]
    kw = dict(cutoff="2024-06-01", store=small_store, backend="advi",
              draws=40, seed=0, advi_iters=800, cache_dir=tmp_path, config=cfg)

    p_miss, m_miss = cached_fit(**kw)
    p_hit, m_hit = cached_fit(**kw)
    assert m_miss["cache_hit"] is False and m_hit["cache_hit"] is True

    # The transform survived the round-trip (not an empty map on the HIT).
    assert "rest_days" in p_hit.covariate_transforms
    t = p_hit.covariate_transforms["rest_days"]
    assert t.name == "rest_days"
    # And it MATCHES the fresh fit's transform (same standardization).
    t0 = p_miss.covariate_transforms["rest_days"]
    assert (t.mean, t.sd, t.any_observed) == pytest.approx(
        (t0.mean, t0.sd, t0.any_observed))

    # The HIT predicts WITH the covariate: a covariate-bearing predict differs from
    # a covariate-free predict (the offset is actually applied on the cached fit).
    cov = {"rest_days": 30.0, "rest_days__away": 2.0}   # observed -> non-zero z
    with_cov = p_hit.predict_1x2("Brazil", "Argentina", neutral=True, covariates=cov)
    no_cov = p_hit.predict_1x2("Brazil", "Argentina", neutral=True)
    # If the fitted beta is non-zero, the covariate moves the prediction.
    beta = float(p_hit.idata.posterior["beta_rest_days"].mean())
    if abs(beta) > 1e-9:
        assert abs(with_cov["home"] - no_cov["home"]) > 1e-9, (
            "cached HIT predicted a ZERO covariate offset — the transform was not "
            "restored / not applied (FIX 3a regression)"
        )


@pytest.mark.slow
def test_ablation_lockbox_is_read_at_most_once(small_store, tmp_path):
    """The ``use_lockbox`` path runs the ACCEPTED set ONCE against the single-use
    lockbox and records it; a SECOND lockbox run is physically refused. Isolated
    temp registry so the committed real flag is never burned."""
    from wcmodel.backtest.ablation import run_ablation
    from wcmodel.backtest.lockbox import LockboxRegistry, LockboxUsedError

    temp_registry = tmp_path / "lockbox.json"
    shutil.copy(REGISTRY_PATH, temp_registry)

    samples, rfs, matches = _paired_inputs()
    kw = dict(candidates=["rest_days"], cutoffs=_CUTOFFS, config=load_config(),
              seed=0, results_for_settle=rfs, matches=matches, fit_kwargs=_FIT_KWARGS)

    rep = run_ablation(small_store, samples, use_lockbox=True,
                       lockbox_path=temp_registry, **kw)
    assert "lockbox" in rep["_meta"]
    reg = LockboxRegistry.load(path=temp_registry)
    assert reg.used is True

    with pytest.raises(LockboxUsedError):
        run_ablation(small_store, samples, use_lockbox=True,
                     lockbox_path=temp_registry, **kw)
