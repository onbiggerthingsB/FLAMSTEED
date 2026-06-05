import copy

import pandas as pd

from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.live.decide import decide_live


def _synth_sample():
    return synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
        bookmaker="pinnacle", seed=0,
    )


def test_live_decision_invariant_to_post_cutoff_result(mutable_store, cfg):
    """read(now) is leakage-safe: a post-cutoff result mutation must NOT move the
    as-of-now decision (the fit reads only < now data). Seeded => bit-identical."""
    s = _synth_sample()
    kw = dict(cutoff="2024-06-01T12:00:00Z", config=cfg,
              fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    before = decide_live(mutable_store, copy.deepcopy(s["sample"]), **kw)
    # Mutate the EARLIEST post-2024-06-01 result (dated AFTER the 2024-06-01 cutoff).
    mutable_store.mutate_future_result("2024-06-01")
    after = decide_live(mutable_store, copy.deepcopy(s["sample"]), **kw)
    assert before.to_dict() == after.to_dict(), (
        "LIVE LEAKAGE: a post-cutoff result moved the as-of-now decision -> read(now) "
        "is peeking past now. STOP and investigate."
    )


def test_live_leakage_canary_has_teeth(mutable_store):
    """NON-VACUITY: the mutation actually changes the store, so the invariance above
    is a real guarantee, not vacuously true."""
    before = mutable_store.read("results", cutoff="2025-01-01")
    mutable_store.mutate_future_result("2024-06-01")
    after = mutable_store.read("results", cutoff="2025-01-01")
    merged = before.merge(after, on="match_id", suffixes=("_b", "_a"))
    changed = (merged["home_score_b"] != merged["home_score_a"]).any()
    assert changed, "mutation did not change any result -> the leakage canary would be vacuous"
