"""Phase-3 T6 — THE tournament-layer leakage GATE (cross-model adversarial review).

Mirrors the Phase-2 model gate (``tests/model/test_leakage_model.py``): a seeded
before/after invariance assertion (the canary) PLUS explicit NON-VACUITY proofs
(teeth) showing the assertion would actually CATCH a leak — so the canary's
``equals`` is never trivially green.

Project rule (binding): NO data leakage / look-ahead. ``simulate(cutoff, ...)`` may
condition only on results KNOWN at the cutoff (``date < cutoff``, played). A result
dated AFTER the cutoff must not touch the as-of-cutoff progression probabilities.
Because the sim is seeded, a leakage-free run is BIT-IDENTICAL across a mutation of a
post-cutoff result; any change is a real leak.
"""
import numpy as np
import pandas as pd
import pytest

from wcmodel.data.tournament import load_tournament
from wcmodel.sim.bracket import build_bracket
from wcmodel.sim.run import SimConfig

# --- Synthetic tournament over PANEL teams (the canary posterior only covers the
# ~14-team mutable_store panel, so RateBook(posterior) would KeyError on the real
# 48-team bracket). A SINGLE group of 4 -> one Final (1A vs 2A), built through the
# REAL build_bracket so the Bracket dataclass is genuine, not a hand-rolled stand-in.
#
# The (Mexico, Malta) group fixture is dated 2024-06-05 — the EXACT store row that
# mutate_future_result(after="2024-06-01") flips — so:
#   * at cutoff 2024-06-01 that fixture is NOT played-as-of-cutoff (date >= cutoff),
#     so it is SIMULATED in both before/after runs => the mutation cannot touch
#     progression (the canary's bit-identical guarantee);
#   * at a LATER cutoff (2024-06-10) it IS played-as-of-cutoff (date < cutoff), so
#     it gets FIXED to the actual score => progression DIFFERS from the all-simulated
#     baseline (the teeth: a leak that admitted the > cutoff row at 2024-06-01 WOULD
#     move progression, so the canary's equals assertion is non-vacuous).
# Every OTHER group fixture is dated < 2024-06-01 with NaN scores (unplayed in the
# store), so only the 2024-06-05 fixture is ever a candidate for fixing.
_PANEL_TEAMS = ["Brazil", "Argentina", "Mexico", "Malta"]

# (home, away) -> fixture date. The (Mexico, Malta) pair carries 2024-06-05 (the
# mutated store row's exact date); the rest are pre-cutoff sentinels.
_FIXTURE_DATES = {
    ("Brazil", "Argentina"): "2024-05-01",
    ("Mexico", "Malta"): "2024-06-05",       # the mutated store row's exact date
    ("Brazil", "Mexico"): "2024-05-02",
    ("Argentina", "Malta"): "2024-05-03",
    ("Brazil", "Malta"): "2024-05-04",
    ("Argentina", "Mexico"): "2024-05-05",
}


def _synthetic_tournament() -> dict:
    """A 1-group-of-4 -> Final tournament dict over PANEL teams, with each group
    fixture carrying its date (the bracket DROPS dates, so simulate() must read the
    fixture->date map from this dict). The (Mexico, Malta) fixture is dated
    2024-06-05 to coincide with the mutated store row."""
    fixtures = [
        {"home": h, "away": a, "date": _FIXTURE_DATES[(h, a)], "round": "Matchday 1"}
        for (h, a) in _FIXTURE_DATES
    ]
    fixtures.append({"match": 104, "home": "1A", "away": "2A", "round": "Final"})
    return {"groups": [{"name": "A", "teams": list(_PANEL_TEAMS)}], "fixtures": fixtures}


def _cfg(**kw) -> SimConfig:
    """TEST helper: a SimConfig over the tiny synthetic tournament (PANEL teams), so
    RateBook(posterior) resolves every fixture. The real 48-team bracket would
    KeyError on the canary's 14-team posterior."""
    base = dict(
        tournament=_synthetic_tournament(),
        n_sims=200, seed=0, max_goals=8, et_scale=0.3333, pen_home_prob=0.5,
    )
    base.update(kw)
    return SimConfig(**base)


def test_progression_invariant_to_post_cutoff_result(mutable_store):
    """Tournament-layer leakage canary: a result dated AFTER the cutoff must not
    change the as-of-cutoff progression probabilities. Seeded, so a leakage-free
    sim is bit-identical across the mutation."""
    from wcmodel.model.scoreline import fit
    from wcmodel.sim.run import simulate
    kw = dict(n_sims=800, seed=0)
    before = simulate("2024-06-01", fit("2024-06-01", mutable_store, backend="advi",
                      draws=80, seed=0, advi_iters=2000), mutable_store, _cfg(**kw))
    mutable_store.mutate_future_result(after="2024-06-01")
    after = simulate("2024-06-01", fit("2024-06-01", mutable_store, backend="advi",
                     draws=80, seed=0, advi_iters=2000), mutable_store, _cfg(**kw))
    assert before.progression.equals(after.progression)   # no leak


def test_per_cutoff_conditioning_is_load_bearing(mutable_store):
    """NON-VACUITY proof (teeth) for the canary above — mirrors the Phase-2 gate's
    ``test_full_posterior_invariance_is_non_vacuous`` /
    ``test_provisional_set_leak_would_be_caught``.

    The canary asserts ``before.progression.equals(after.progression)``. That is a
    meaningful leakage GATE only if conditioning on the 2024-06-05 result WOULD move
    progression — otherwise the equality is trivially green (nothing ever depends on
    that row). Here we prove the per-cutoff conditioning is LOAD-BEARING:

      * BASELINE: simulate at cutoff 2024-06-01. The 2024-06-05 Mexico-Malta fixture
        is dated >= cutoff, so it is NOT played-as-of-cutoff and is SIMULATED. This is
        exactly the canary's all-simulated run.
      * CONDITIONED: simulate at cutoff 2024-06-10, AFTER the 2024-06-05 fixture. Now
        that fixture IS played-as-of-cutoff (date < cutoff) and gets FIXED to the
        actual store score (Mexico 1, Malta 0). Mexico's / Malta's forward
        probabilities move because their match is pinned to a real result instead of
        sampled.

    Conclusion (asserted): the two progressions DIFFER. So conditioning on the
    2024-06-05 row genuinely changes progression — which means a leak that admitted
    that > cutoff row into the played set at cutoff 2024-06-01 WOULD change the
    canary's progression and break its ``equals`` assertion. The canary therefore has
    TEETH (non-vacuous). If this test ever fails (baseline == conditioned), the
    conditioning is not load-bearing and the canary's equality would be vacuous.

    We ALSO assert the store row is exactly Mexico 1 - Malta 0 at 2024-06-05 so the
    conditioning is pinned to a known, score-bearing fact (not an accidental NaN)."""
    from wcmodel.model.scoreline import fit
    from wcmodel.sim.run import simulate

    # The 2024-06-05 Mexico-Malta row IS the played fact the conditioning pins to.
    played = mutable_store.read("results", cutoff="2024-06-10")
    mm = played[(played["home_team"] == "Mexico") & (played["away_team"] == "Malta")
                & (pd.to_datetime(played["date"]) == pd.Timestamp("2024-06-05"))]
    assert len(mm) == 1, "expected exactly one 2024-06-05 Mexico-Malta store row"
    assert (int(mm.iloc[0]["home_score"]), int(mm.iloc[0]["away_score"])) == (1, 0), (
        "conditioning must pin to the known 2024-06-05 Mexico 1 - Malta 0 result"
    )

    post = fit("2024-06-10", mutable_store, backend="advi", draws=80, seed=0,
               advi_iters=2000)
    kw = dict(n_sims=800, seed=0)
    # Baseline: nothing played-as-of-cutoff is the 2024-06-05 fixture -> all simulated.
    baseline = simulate("2024-06-01", post, mutable_store, _cfg(**kw))
    # Conditioned: the 2024-06-05 fixture IS played-as-of 2024-06-10 -> FIXED.
    conditioned = simulate("2024-06-10", post, mutable_store, _cfg(**kw))

    assert not baseline.progression.equals(conditioned.progression), (
        "per-cutoff conditioning is NOT load-bearing: fixing the 2024-06-05 result "
        "did not change progression — the canary's equals assertion would be vacuous"
    )


def test_canary_mutation_actually_fires(mutable_store):
    """Guard that the canary isn't trivially comparing two identical stores: the
    SCORE of the 2024-06-05 row must genuinely change under mutate_future_result.
    (Mirrors mutate_future_result's own internal assertion, surfaced here so the
    canary's premise — that the stores DIFFER on the post-cutoff row — is explicit.)"""
    before = mutable_store.read("results", cutoff="2024-06-10")
    bm = before[(before["home_team"] == "Mexico") & (before["away_team"] == "Malta")
                & (pd.to_datetime(before["date"]) == pd.Timestamp("2024-06-05"))].iloc[0]
    before_score = (int(bm["home_score"]), int(bm["away_score"]))

    mutable_store.mutate_future_result(after="2024-06-01")

    after = mutable_store.read("results", cutoff="2024-06-10")
    am = after[(after["home_team"] == "Mexico") & (after["away_team"] == "Malta")
               & (pd.to_datetime(after["date"]) == pd.Timestamp("2024-06-05"))].iloc[0]
    after_score = (int(am["home_score"]), int(am["away_score"]))

    assert before_score != after_score, (
        "mutate_future_result did not change the 2024-06-05 score — the canary "
        "would be comparing two identical stores (trivially green)"
    )


def test_played_filter_is_strict_and_day_floored(mutable_store):
    """Direct, fast coverage of the leakage-critical line in
    ``wcmodel.sim.run._played_as_of`` — the strict, day-floored ``date < cutoff``
    filter mirrored from ``features.build``. This is the boundary the whole gate
    rests on, so we pin it without waiting on ADVI:

      * a match dated ON the cutoff day is EXCLUDED (strict ``<``, not ``<=``) — a
        same-day match is not knowable as-of an intraday cutoff;
      * a match dated strictly BEFORE the cutoff is INCLUDED;
      * the 2024-06-05 row is OUT at 2024-06-01 (the canary's premise) and IN at
        2024-06-10 (the teeth's premise) — the exact rows the gate depends on.
    """
    from wcmodel.sim.run import _played_as_of

    # 2024-06-05 Mexico-Malta: OUT strictly before, IN strictly after.
    p_before = _played_as_of(mutable_store, "2024-06-01")
    p_eq = _played_as_of(mutable_store, "2024-06-05")        # ON the day -> excluded (strict <)
    p_after = _played_as_of(mutable_store, "2024-06-10")

    def _has_mm(df):
        return bool(((df["home_team"] == "Mexico") & (df["away_team"] == "Malta")
                     & (df["date"] == pd.Timestamp("2024-06-05"))).any())

    assert not _has_mm(p_before), "2024-06-05 row must be EXCLUDED at cutoff 2024-06-01"
    assert not _has_mm(p_eq), (
        "2024-06-05 row must be EXCLUDED at cutoff 2024-06-05 (strict <, day-floored: "
        "a same-day match is not knowable as-of an intraday cutoff)"
    )
    assert _has_mm(p_after), "2024-06-05 row must be INCLUDED at cutoff 2024-06-10"
    # Every surviving row is strictly before the cutoff day (the leakage invariant).
    assert (p_after["date"] < pd.Timestamp("2024-06-10")).all()
