import numpy as np
import pytest

from wcmodel.model.scoreline import fit


@pytest.mark.slow
def test_fit_invariant_to_future_result_mutation(mutable_store):
    """Model leakage GATE: a result dated AFTER the cutoff must not change ANY
    part of the per-cutoff fit. ``fit()`` consumes only ``features.build(cutoff)``
    + the as-of-cutoff provisional set (``count_volatility_arm``), both reading
    strictly < cutoff. ADVI is seeded, so a leakage-free fit is BIT-STABLE across
    the future-result mutation; any change is a real leak.

    WHY FULL-POSTERIOR INVARIANCE IS THE RIGHT GATE (Codex T9). The previous
    canary asserted only that ``predict_1x2("Brazil","Argentina")`` was invariant.
    That is a coverage hole: the mutated match is Mexico v Malta, so a leak
    localized to Mexico/Malta strengths — or a leak into ``provisional_teams`` via
    ``count_volatility_arm`` (which a Brazil-Argentina 1X2 cannot see) — would slip
    through. A leakage gate must catch ANY leak into the fit, not one fixture pair.
    Under a SEEDED fit the entire posterior is a deterministic function of the
    < cutoff panel + provisional set; therefore ANY > cutoff data reaching the fit
    would perturb SOME posterior variable (a team strength, a global param, or the
    provisional set) away from bit-identical. So we assert invariance of the WHOLE
    object: every posterior ``data_var`` elementwise, the provisional set, and the
    predicted 1X2 for BOTH a far pair AND the most-likely-affected (mutated) pair.
    """
    kw = dict(backend="advi", draws=120, seed=0, advi_iters=3000)
    before = fit("2024-06-01", mutable_store, **kw)
    mutable_store.mutate_future_result(after="2024-06-01")  # asserts the score changed
    after = fit("2024-06-01", mutable_store, **kw)

    # (1) Provisional set invariant — catches a leak via count_volatility_arm
    # (the as-of-cutoff volatility/few-games arm) into the predict-time widening
    # set, which no single 1X2 prediction would necessarily reveal.
    assert before.provisional_teams == after.provisional_teams, (
        "future result leaked into the provisional set (count_volatility_arm)"
    )

    # (2) EVERY posterior data variable bit-identical (att, def, mu, home_adv,
    # rho or log_lambda3, and the raw/sigma hyperparams). Iterating all data_vars
    # — not a hand-picked subset — catches a leak into ANY team's strength or any
    # global parameter, not just one fixture pair. Same var set in both fits is
    # itself part of the contract (a leak cannot add/drop a variable either).
    before_vars = set(before.idata.posterior.data_vars)
    after_vars = set(after.idata.posterior.data_vars)
    assert before_vars == after_vars, "posterior variable set changed under mutation"
    for name in before_vars:
        b = before.idata.posterior[name].values
        a = after.idata.posterior[name].values
        assert b.shape == a.shape, f"posterior var {name!r} changed shape under mutation"
        assert np.array_equal(b, a), (
            f"future result leaked into posterior var {name!r}: "
            f"max|Δ|={np.abs(b - a).max():.3e}"
        )

    # (3) predict_1x2 bit-identical (< 1e-9) for BOTH a FAR pair (Brazil v
    # Argentina) AND the MUTATED match's teams (Mexico v Malta — the most-likely-
    # affected pair, so a leak localized to the mutated teams is caught here).
    for home, away in (("Brazil", "Argentina"), ("Mexico", "Malta")):
        b1x2 = before.predict_1x2(home, away)
        a1x2 = after.predict_1x2(home, away)
        for outcome in ("home", "draw", "away"):
            assert abs(b1x2[outcome] - a1x2[outcome]) < 1e-9, (
                f"future result leaked into predict_1x2({home!r},{away!r})[{outcome!r}]"
            )


@pytest.mark.slow
def test_full_posterior_invariance_is_non_vacuous(mutable_store):
    """Non-vacuity guard for the gate above. The full-posterior/provisional/1X2
    invariance is only a meaningful leakage GATE if a leak would actually MOVE
    those quantities — i.e. the test is not trivially green because nothing in
    this panel can ever move. Here we fit the SAME cutoff over two stores whose
    < cutoff (in-panel, played) data DIFFER on a full-panel match, and assert the
    posterior + provisional set + 1X2 genuinely change. If this fails, the
    invariance assertions in the gate above are vacuous and must be revisited.

    Concretely: ``mutate_future_result(after=D)`` rewrites the EARLIEST result
    dated after ``D``. With ``D="2020-01-01"`` that earliest match is well BEFORE
    the 2024-06-01 fit cutoff, so the rewritten row is IN-panel for the fit and
    must perturb the seeded posterior — unlike the gate above, where the mutated
    match is dated AFTER the cutoff and therefore excluded."""
    kw = dict(backend="advi", draws=120, seed=0, advi_iters=3000)
    base = fit("2024-06-01", mutable_store, **kw)
    # Mutate an EARLY (in-panel, < cutoff) match so the fit's own input changes.
    mutable_store.mutate_future_result(after="2020-01-01")
    perturbed = fit("2024-06-01", mutable_store, **kw)

    # SOME posterior variable must move (the panel genuinely changed). att/def are
    # team strengths and are the most direct carrier of an in-panel score change.
    moved = any(
        not np.array_equal(
            base.idata.posterior[name].values, perturbed.idata.posterior[name].values
        )
        for name in base.idata.posterior.data_vars
    )
    assert moved, (
        "non-vacuity FAILED: a full-panel (< cutoff) score change moved NO "
        "posterior variable — the invariance gate would be vacuous"
    )
