import pytest
from wcmodel.model.scoreline import fit


@pytest.mark.slow
def test_fit_invariant_to_future_result_mutation(mutable_store):
    """Model leakage canary: a result dated AFTER the cutoff must not change the
    per-cutoff fit. fit() consumes only features.build(cutoff) + the as-of-cutoff
    provisional set, both < cutoff. ADVI is seeded, so a leakage-free fit is
    bit-stable across the future-result mutation; any change is a real leak."""
    kw = dict(backend="advi", draws=120, seed=0, advi_iters=3000)
    before = fit("2024-06-01", mutable_store, **kw).predict_1x2("Brazil", "Argentina")
    mutable_store.mutate_future_result(after="2024-06-01")
    after = fit("2024-06-01", mutable_store, **kw).predict_1x2("Brazil", "Argentina")
    assert abs(before["home"] - after["home"]) < 1e-9, "future result leaked into the fit"
    assert abs(before["draw"] - after["draw"]) < 1e-9
    assert abs(before["away"] - after["away"]) < 1e-9
