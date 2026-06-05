"""Backtest-layer leakage canary (Phase-4 Task 6) — the load-bearing gate, WITH
NON-VACUITY TEETH.

The canary runs the REAL ``walkforward`` over a synthetic event whose decision
cutoff (the 2024-05-20 matchday) precedes a POST-cutoff result, mutates that
post-cutoff result, and asserts the run is BIT-IDENTICAL across the mutation. A
leakage-free engine reads only ``< cutoff`` data for every feature/refit and uses
the realised result ONLY to settle the bet AFTER the decision, so the run cannot
move.

CRITICAL non-vacuity design (closes the focal-Codex finding): the canary BETS the
SAME TEAM whose post-cutoff result the mutation flips (Mexico). The mutated row is
Mexico's 2024-06-05 fixture, so an Elo / future-form feature that leaked
``>= cutoff`` results would move *the bet team's* rating -> the ledger. Betting a
team DISJOINT from the mutated row (the original Brazil/Croatia draft) would have
made the Elo invariance hold VACUOUSLY — a same-team future-result leak would
never be exercised. ``test_canary_has_teeth_*`` proves both halves: (a) the
mutation fires, and (b) a deliberately-leaky same-team Elo WOULD move the recorded
elo baseline for the bet pair, so the invariance above is a real guarantee.

The canary forces a FRESH posterior fit per run (a test-local ``cache_dir``) so a
stale ``data/cache`` HIT — whose key omits the uncommitted working tree — can
never mask a fit-level leak.
"""
import copy

import pandas as pd

from wcmodel.backtest.baselines import elo_baseline_1x2
from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.backtest.validation import assert_leakage_invariant
from wcmodel.backtest.walkforward import walkforward
from wcmodel.config import load_config

# The mutable_store rewrites the EARLIEST post-2024-06-01 result, which is the
# 2024-06-05 Mexico fixture. Bet MEXICO so the mutated row belongs to a BET team:
# a same-team Elo/form leak that read it would move this run's ledger (non-vacuity).
_BET_HOME, _BET_AWAY = "Mexico", "Croatia"
_DECISION_CUTOFF = pd.Timestamp("2024-05-20")   # the synthetic event's matchday


def _inputs():
    """A synthetic Mexico-vs-Croatia event whose decision cutoff (its 2024-05-20
    matchday) precedes the POST-cutoff result the mutable_store rewrites (Mexico's
    2024-06-05 fixture). The fit + Elo at the cutoff read only ``< cutoff`` data,
    so mutating that post-cutoff Mexico result must NOT move the run."""
    s = synthetic_odds_sample(
        home=_BET_HOME, away=_BET_AWAY, commence="2024-05-20T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
        bookmaker="pinnacle", seed=0,
    )
    results_for_settle = pd.DataFrame([{
        "home_team": _BET_HOME, "away_team": _BET_AWAY,
        "date": pd.Timestamp("2024-05-20"), "home_score": 2, "away_score": 0,
        "tournament": "FIFA World Cup",
    }])
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-05-20"])})
    return [s], results_for_settle, matches


def test_backtest_invariant_to_post_cutoff_result(mutable_store):
    samples, rfs, matches = _inputs()
    # FRESH fit cache (under the store's tmp root) so each run RE-FITS — a stale
    # data/cache HIT (whose key omits the uncommitted working tree) cannot mask a
    # fit-level leak. Seeded => a leakage-free fit is bit-identical across runs.
    fit_cache = str(mutable_store.root / "fitcache")

    def run():
        return walkforward(mutable_store, copy.deepcopy(samples),
                           results_for_settle=rfs.copy(), matches=matches,
                           fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                       "cache_dir": fit_cache})

    # mutate_future_result rewrites the EARLIEST post-2024-06-01 result — the
    # 2024-06-05 Mexico pivot — dated AFTER the 2024-05-20 decision cutoff. A
    # leakage-free run is bit-identical across it; if it is NOT, the backtest is
    # peeking past the cutoff (a real leak) and assert_leakage_invariant raises.
    assert_leakage_invariant(run, lambda: mutable_store.mutate_future_result("2024-06-01"),
                             seed=0)


def test_canary_has_teeth_mutation_fires_and_leak_would_move(mutable_store):
    """NON-VACUITY (the teeth). Prove the invariance above is a REAL guarantee:
    (0) the leakage-free run actually places a bet, so ``before.bets == after.bets``
        is not the trivially-true ``[] == []``;
    (a) the mutation actually changes the underlying results parquet; AND
    (b) a deliberately-LEAKY same-team Elo (one that read the POST-cutoff result)
        WOULD move the recorded elo baseline for the BET pair — so the canary can
        distinguish a leak from a non-leak."""
    cfg = load_config()
    samples, rfs, matches = _inputs()
    fit_cache = str(mutable_store.root / "fitcache")

    # (0) the leakage-free run is NON-EMPTY: it stakes exactly one bet on the bet
    #     pair. (If it bet nothing, before.bets == after.bets would be vacuously
    #     [] == [] and the invariance would prove nothing.)
    honest = walkforward(mutable_store, copy.deepcopy(samples),
                         results_for_settle=rfs.copy(), matches=matches,
                         fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                     "cache_dir": fit_cache})
    assert len(honest.bets) == 1, "leakage-free run must place a bet (else canary is vacuous)"
    assert list(honest.bets[0]["event_key"][:2]) == [_BET_HOME, _BET_AWAY]

    # (a) the mutation changes the underlying results parquet (the 2024-06-05
    #     Mexico pivot), and it changes the BET HOME team's row specifically.
    before = mutable_store.read("results", cutoff="2025-01-01")
    mutable_store.mutate_future_result("2024-06-01")
    after = mutable_store.read("results", cutoff="2025-01-01")
    merged = before.merge(after, on="match_id", suffixes=("_b", "_a"))
    changed = merged[merged["home_score_b"] != merged["home_score_a"]]
    assert not changed.empty, "mutation did not change any result -> canary would be vacuous"
    assert (changed["home_team_a"] == _BET_HOME).any(), (
        "mutation did not touch the BET team's future result -> a same-team Elo "
        "leak would not be exercised, making the invariance vacuous"
    )

    # (b) a LEAKY same-team Elo (reading ALL results, NOT just < cutoff) WOULD move
    #     the bet team's rating, hence the recorded elo baseline for the bet pair
    #     (bets[*]["elo"]) and the summary's mean_rps_elo. `before`/`after` already
    #     captured the un-mutated / mutated FULL result sets above, so compute the
    #     leaky (cutoff-ignoring) Elo over each and assert it differs on the bet
    #     pair — the concrete >= cutoff leak the < cutoff guard prevents, and which
    #     this canary therefore guards against. This is what gives the bit-identity
    #     above its teeth.
    def _leaky_ratings_from_frame(res):
        from wcmodel.data import tiers
        from wcmodel.data.elo import compute_elo_history
        from wcmodel.data.features import valid_played_results
        res = res.copy()
        res["date"] = pd.to_datetime(res["date"])
        res = valid_played_results(res)
        res["match_type"] = res["tournament"].map(tiers.match_type)
        elo = compute_elo_history(
            res[["match_id", "date", "home_team", "away_team",
                 "home_score", "away_score", "neutral", "match_type"]],
            config=cfg,
        )
        return (elo.sort_values("date", kind="mergesort")
                   .groupby("team", sort=False)["rating_post"].last().to_dict())

    r_before = _leaky_ratings_from_frame(before)
    r_after = _leaky_ratings_from_frame(after)
    assert r_before.get(_BET_HOME) != r_after.get(_BET_HOME), (
        "a leaky (>= cutoff) Elo did NOT move the bet team's rating -> the mutated "
        "row is not Elo-relevant for the bet team, so the canary lacks teeth"
    )
    elo_before = elo_baseline_1x2(rating_home=r_before.get(_BET_HOME),
                                  rating_away=r_before.get(_BET_AWAY),
                                  neutral=True, config=cfg)
    elo_after = elo_baseline_1x2(rating_home=r_after.get(_BET_HOME),
                                 rating_away=r_after.get(_BET_AWAY),
                                 neutral=True, config=cfg)
    assert elo_before != elo_after, (
        "a LEAKY same-team Elo baseline for the bet pair WOULD move under the "
        "mutation -> the leakage-free run's bit-identity is a real guarantee, not "
        "vacuously true"
    )
