"""Backtest-layer leakage canary (Phase-4 Task 6) — the load-bearing gate, WITH
NON-VACUITY TEETH on BOTH leak surfaces (score-mode AND count-mode).

The canary runs the REAL ``walkforward`` over a synthetic event whose decision
cutoff precedes a POST-cutoff perturbation, and asserts the run is BIT-IDENTICAL
across that perturbation. A leakage-free engine reads only ``< cutoff`` data for
every feature/refit and uses the realised result ONLY to settle the bet AFTER the
decision, so the run cannot move.

TWO perturbation modes, mirroring the Phase-2 model canary (score-mode +
count-mode, both with teeth):

  * SCORE-MODE (``test_backtest_invariant_to_post_cutoff_result``) — mutate a
    POST-cutoff result's SCORE; the bet team (Mexico) is the team whose result is
    mutated, so a same-team Elo/future-form leak would move *the bet team's*
    rating -> the ledger. Teeth: ``test_canary_has_teeth_*``.

  * COUNT-MODE (``test_backtest_invariant_to_post_cutoff_row_count``) — ADD a
    POST-cutoff ROW (written observed-as-of ``< cutoff`` so the bitemporal
    ``read(cutoff)`` RETURNS it) for a bet team sitting at the few-games
    provisional BOUNDARY. A score mutation cannot perturb a game COUNT, so the
    score-mode canary is BLIND to a count-mode leak (a ``> cutoff`` row whose mere
    PRESENCE inflates ``count_volatility_arm``'s game count, flips the bet team's
    provisional flag, and moves its widening/price/ledger). Teeth:
    ``test_count_mode_canary_has_teeth`` (row visible to ``read(cutoff)``; a count
    leak WOULD flip provisional + move the bet).

FRESH FITS ACROSS BEFORE/AFTER (un-masks the PRIMARY surface; closes the focal
Codex finding). The before/after runs MUST NOT share a posterior cache: the
posterior cache key (``model.cache._cache_key_params``) is ``< cutoff``-only (its
``_feature_hash`` hashes ``features.build(cutoff, ...)``, which already excludes
``> cutoff`` rows), so a SECOND run reusing the FIRST run's ``cache_dir`` HITS the
first posterior and a fit-level leak (``features.build`` / ``count_volatility_arm``
reading ``> cutoff``) is NEVER recomputed -> the canary's ``before == after`` is
TRIVIALLY true and VACUOUS for the fit/posterior surface (only the un-cached Elo
baseline had teeth). Every ``run()`` here therefore gets a UNIQUE fresh
``cache_dir`` (``_FreshFitCache``) so the second run RE-FITS;
``test_second_run_refits_no_posterior_cache_hit`` proves the re-fit by
instrumenting ``cached_fit`` (no cache hit), and
``test_fit_leak_masked_by_shared_cache_caught_by_fresh_fits`` is the RED-on-
injected-FIT-leak proof: a real ``count_volatility_arm`` ``>= cutoff`` leak is
MASKED under a shared cache (the canary passes, vacuously) but CAUGHT under fresh
fits (the canary RAISES) — so the fresh-fit fix is LOAD-BEARING for the fit
surface, not cosmetic.
"""
import copy
import itertools

import pandas as pd

from wcmodel.backtest.baselines import elo_baseline_1x2
from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.backtest.validation import assert_leakage_invariant
from wcmodel.backtest.walkforward import walkforward
from wcmodel.config import load_config
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy

# The mutable_store rewrites the EARLIEST post-2024-06-01 result, which is the
# 2024-06-05 Mexico fixture. Bet MEXICO so the mutated row belongs to a BET team:
# a same-team Elo/form leak that read it would move this run's ledger (non-vacuity).
_BET_HOME, _BET_AWAY = "Mexico", "Croatia"
_DECISION_CUTOFF = pd.Timestamp("2024-05-20")   # the synthetic event's matchday

# Shared sampler knobs for the canary's tiny ADVI refit (seeded => a leakage-free
# fit is bit-identical across before/after, so `before == after` holds exactly).
_FIT = {"draws": 60, "advi_iters": 1500, "seed": 0}


class _FreshFitCache:
    """Hands out a UNIQUE posterior ``cache_dir`` per ``run()`` invocation.

    The before/after runs MUST NOT share a posterior cache: the cache key is
    ``< cutoff``-only, so the second run would HIT the first's posterior and a
    fit-level leak would never be recomputed (the masked PRIMARY surface). A fresh
    dir per run forces a RE-FIT, so a fit/posterior leak surfaces in
    ``before != after``. (Seeded => the leakage-free re-fit is still bit-identical.)
    """

    def __init__(self, root):
        self._root = str(root)
        self._counter = itertools.count()

    def next(self) -> str:
        return f"{self._root}/fitcache_{next(self._counter)}"


def _fit_kwargs(cache_dir: str) -> dict:
    return {**_FIT, "cache_dir": cache_dir}


def _anchor_off_cfg() -> dict:
    """A config with the Elo strength anchor (``model.strength_prior``) pinned OFF.

    These synthetic canaries test the leak-DETECTION machinery (the walk-forward
    before/after over the provisional/count widening surface). Pin the Elo strength
    anchor OFF so it can't mask the synthetic provisional-leak signal — the anchor
    is a SEPARATE prior whose att/def prior MEAN it dominates (k=0.6), which swamps
    mechanism-(c)'s provisional-widening price influence and suppresses the synthetic
    +EV bet at the boundary cutoff (so before == after == [] vacuously, and the
    detector can't trip). The anchor's OWN point-in-time leakage-safety is proven by
    ``tests/model/test_fit_strength_leakage.py`` (a > cutoff row never moves ``att``);
    the anchor is byte-identical when off; and the fit-DATA (score-mode) leak surface
    keeps its teeth with the anchor ON. So pinning it off here is a TEST-ONLY
    calibration choice on the SECONDARY count-detection surface, not a model change.
    """
    cfg = copy.deepcopy(load_config())
    cfg["model"]["strength_prior"]["enabled"] = False
    return cfg


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
    # FRESH fit cache PER RUN (under the store's tmp root) so each run RE-FITS — a
    # second run sharing the first's cache_dir would HIT the first posterior (the
    # key is < cutoff-only) and a fit-level leak would be MASKED. A unique dir per
    # run forces the re-fit; seeded => a leakage-free fit is bit-identical.
    caches = _FreshFitCache(mutable_store.root)

    def run():
        return walkforward(mutable_store, copy.deepcopy(samples),
                           results_for_settle=rfs.copy(), matches=matches,
                           fit_kwargs=_fit_kwargs(caches.next()))

    # mutate_future_result rewrites the EARLIEST post-2024-06-01 result — the
    # 2024-06-05 Mexico pivot — dated AFTER the 2024-05-20 decision cutoff. A
    # leakage-free run is bit-identical across it; if it is NOT, the backtest is
    # peeking past the cutoff (a real leak) and assert_leakage_invariant raises.
    assert_leakage_invariant(run, lambda: mutable_store.mutate_future_result("2024-06-01"),
                             seed=0)


def test_canary_has_teeth_mutation_fires_and_leak_would_move(mutable_store):
    """SCORE-MODE NON-VACUITY (the teeth). Prove the invariance above is a REAL
    guarantee:
    (0) the leakage-free run actually places a bet, so ``before.bets == after.bets``
        is not the trivially-true ``[] == []``;
    (a) the mutation actually changes the underlying results parquet; AND
    (b) a deliberately-LEAKY same-team Elo (one that read the POST-cutoff result)
        WOULD move the recorded elo baseline for the BET pair — so the canary can
        distinguish a leak from a non-leak."""
    cfg = load_config()
    samples, rfs, matches = _inputs()
    caches = _FreshFitCache(mutable_store.root)

    # (0) the leakage-free run is NON-EMPTY: it stakes exactly one bet on the bet
    #     pair. (If it bet nothing, before.bets == after.bets would be vacuously
    #     [] == [] and the invariance would prove nothing.)
    honest = walkforward(mutable_store, copy.deepcopy(samples),
                         results_for_settle=rfs.copy(), matches=matches,
                         fit_kwargs=_fit_kwargs(caches.next()))
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


# ---------------------------------------------------------------------------
# GAP 1 — fresh fits un-mask the fit/posterior surface (the PRIMARY surface).
# ---------------------------------------------------------------------------

def test_second_run_refits_no_posterior_cache_hit(mutable_store, monkeypatch):
    """GAP-1 FIX PROOF: with a fresh ``cache_dir`` per ``run()``, the SECOND run
    RE-FITS (no posterior cache hit), so a fit-level leak can surface.

    Instruments ``walkforward``'s ``cached_fit`` reference and records the
    ``cache_hit`` of every fit. The first run misses (fits fresh); after the
    post-cutoff mutation the second run — given a UNIQUE fresh dir — misses AGAIN
    (re-fits). If instead the two runs shared a dir, the second would HIT (the key
    is < cutoff-only) and the fit-level leak surface would be masked. This is the
    instrumentation the GAP-1 fix turns on."""
    import wcmodel.model.cache as model_cache

    samples, rfs, matches = _inputs()
    caches = _FreshFitCache(mutable_store.root)

    real_cached_fit = model_cache.cached_fit
    hits: list[bool] = []

    def spy(**kwargs):
        post, meta = real_cached_fit(**kwargs)
        hits.append(bool(meta["cache_hit"]))
        return post, meta

    # walkforward calls cached_fit via `import wcmodel.model.cache as _model_cache`,
    # so patch the attribute on that module.
    monkeypatch.setattr(model_cache, "cached_fit", spy)

    def run():
        return walkforward(mutable_store, copy.deepcopy(samples),
                           results_for_settle=rfs.copy(), matches=matches,
                           fit_kwargs=_fit_kwargs(caches.next()))

    hits.clear()
    run()
    assert hits == [False], f"first run must MISS (fit fresh); got {hits}"

    mutable_store.mutate_future_result("2024-06-01")
    hits.clear()
    run()
    # The crux of the GAP-1 fix: a UNIQUE fresh dir means the second run does NOT
    # hit the first run's posterior — it RE-FITS — so a fit-level leak that reads
    # the mutated > cutoff row WOULD be recomputed (and caught by before != after).
    assert hits == [False], (
        "second run HIT the posterior cache -> it reused the first run's fit, so a "
        "fit/posterior leak would be MASKED. The canary must force a fresh fit per "
        f"run; got cache_hits={hits}"
    )


# ---------------------------------------------------------------------------
# COUNT-MODE canary (GAP 2) — the few-games provisional boundary store.
# ---------------------------------------------------------------------------

# A bet team ("Edge") parked EXACTLY at the few-games provisional boundary: it has
# EXACTLY `provisional_games - 1` (= 4) played matches < the cutoff, all vs "Foe",
# so it is few-games-provisional at the cutoff. "Foe" plays "Punch" too so the
# scoreline model is identified (Foe/Punch are NOT at the boundary). All neutral
# so the home-advantage term is out of the picture. The cutoff (the bet's matchday)
# is 2024-05-20, comfortably after `backtest.odds_start` (2020-06-06) so it lands
# in the swept grid.
_COUNT_CUTOFF = pd.Timestamp("2024-05-20")
_COUNT_BET_HOME, _COUNT_BET_AWAY = "Edge", "Foe"

_COUNT_BASE_ROWS = [
    # date, home, away, hs, as, tournament, city, country, neutral
    ("2024-01-02", "Edge", "Foe", 2, 1, "Friendly", "London", "England", True),
    ("2024-01-04", "Foe", "Edge", 0, 1, "Friendly", "London", "England", True),
    ("2024-01-06", "Edge", "Foe", 1, 1, "Friendly", "London", "England", True),
    ("2024-01-08", "Foe", "Edge", 2, 0, "Friendly", "London", "England", True),  # Edge: 4 < cutoff games
    # Foe's other fixtures (so Foe — and the model — is identified; Edge plays ONLY Foe).
    ("2024-01-03", "Foe", "Punch", 2, 1, "Friendly", "London", "England", True),
    ("2024-01-05", "Punch", "Foe", 0, 0, "Friendly", "London", "England", True),
    ("2024-01-07", "Foe", "Punch", 3, 1, "Friendly", "London", "England", True),
    ("2024-01-09", "Punch", "Foe", 1, 2, "Friendly", "London", "England", True),
]

# The POST-cutoff Edge row the count-mode canary ADDS. Dated AFTER the cutoff, but
# written OBSERVED-as-of < cutoff so the bitemporal read(cutoff) RETURNS it: the
# SOLE thing excluding it from the count is count_volatility_arm's `date < cutoff`
# MATCH-DATE filter (NOT the store's observed_at masking — which would hide it for
# an unrelated reason and make the proof vacuous), mirroring the Phase-2 count-mode
# canary's `extra["observed_at"] = ...`.
_COUNT_EXTRA_DATE = pd.Timestamp("2024-06-05")        # > cutoff
_COUNT_EXTRA_OBSERVED = pd.Timestamp("2024-05-19")    # < cutoff (visible to read(cutoff))


def _count_boundary_store(tmp_path) -> BitemporalStore:
    """A store where the BET team sits at the few-games provisional boundary (4
    played < cutoff matches). POINT_IN_TIME results only; no xG/venues needed."""
    store = BitemporalStore(root=tmp_path / "count_boundary")
    res = normalize_results(pd.DataFrame(
        _COUNT_BASE_ROWS,
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "city", "country", "neutral"],
    ))
    store.write("results", res, policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source="martj42", source_version="test")
    return store


def _add_post_cutoff_row(store: BitemporalStore) -> None:
    """ADD a > cutoff Edge row written OBSERVED-as-of < cutoff (so read(cutoff)
    returns it; only the date<cutoff filter excludes it from the count)."""
    extra = normalize_results(pd.DataFrame(
        [(str(_COUNT_EXTRA_DATE.date()), "Edge", "Foe", 4, 0, "Friendly",
          "London", "England", True)],
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "city", "country", "neutral"],
    ))
    extra["observed_at"] = _COUNT_EXTRA_OBSERVED
    extra["valid_as_of"] = _COUNT_EXTRA_OBSERVED
    store.write("results", extra, policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source="martj42", source_version="test")


def _count_inputs(cutoff: pd.Timestamp = _COUNT_CUTOFF):
    """Synthetic Edge-vs-Foe event + settle frame + match panel, all at ``cutoff``
    (the bet's matchday)."""
    s = synthetic_odds_sample(
        home=_COUNT_BET_HOME, away=_COUNT_BET_AWAY,
        commence=f"{cutoff.date()}T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
        bookmaker="pinnacle", seed=0,
    )
    rfs = pd.DataFrame([{
        "home_team": _COUNT_BET_HOME, "away_team": _COUNT_BET_AWAY,
        "date": cutoff, "home_score": 2, "away_score": 0, "tournament": "Friendly",
    }])
    matches = pd.DataFrame({"date": pd.to_datetime([str(cutoff.date())])})
    return [s], rfs, matches


def _provisional_set(store, cutoff, teams) -> set:
    """The provisional set EXACTLY as ``scoreline.fit`` builds it:
    ``set(arm.loc[arm["volatility_flag"] | arm["few_games_flag"], "team"])`` over
    ``count_volatility_arm`` — the same OR-of-two-arms predicate that populates
    ``Posterior.provisional_teams`` (and thus drives mechanism-(c) widening)."""
    from wcmodel.model.volatility_diagnostic import count_volatility_arm
    arm = count_volatility_arm(store, cutoff=cutoff, field_teams=list(teams))
    return set(arm.loc[arm["volatility_flag"] | arm["few_games_flag"], "team"])


def test_backtest_invariant_to_post_cutoff_row_count(tmp_path):
    """COUNT-MODE leakage canary (closes the GAP-2 blind spot). The score-mode
    canary mutates a > cutoff SCORE, but the bet team is ALREADY few-games-
    provisional and a score change does not perturb the game COUNT — so a
    COUNT-mode leak (a > cutoff row whose PRESENCE inflates the count, flips the
    provisional flag, and moves the price) would pass the score-mode canary
    undetected. This canary perturbs the COUNT: it ADDS a > cutoff Edge row written
    observed-as-of < cutoff (so read(cutoff) RETURNS it; only the date<cutoff
    filter excludes it from the count) and asserts the run is BIT-IDENTICAL across
    that addition — with FRESH fits per run (GAP 1), so a count-mode FIT leak is
    not masked by a shared posterior cache."""
    store = _count_boundary_store(tmp_path)
    samples, rfs, matches = _count_inputs()
    caches = _FreshFitCache(tmp_path)
    # Anchor OFF (see _anchor_off_cfg): the Elo strength prior would swamp
    # mechanism-(c)'s provisional widening and suppress the synthetic boundary bet,
    # making this count-detection invariance vacuous (before == after == []).
    cfg = _anchor_off_cfg()

    def run():
        return walkforward(store, copy.deepcopy(samples),
                           results_for_settle=rfs.copy(), matches=matches,
                           config=cfg, fit_kwargs=_fit_kwargs(caches.next()))

    # The added row is dated AFTER the cutoff, so a leakage-free count_volatility_arm
    # (`date < cutoff`) excludes it -> Edge still counts 4 games -> still provisional
    # -> the run is bit-identical. If it is NOT, the count is leaking the > cutoff
    # row and assert_leakage_invariant raises (a real leak).
    assert_leakage_invariant(run, lambda: _add_post_cutoff_row(store), seed=0)


def test_count_mode_canary_has_teeth(tmp_path):
    """COUNT-MODE NON-VACUITY (the teeth). Prove the count-mode invariance above is
    a REAL guarantee, mirroring the Phase-2 count-mode canary's cutoff-sweep teeth:

    (0) the leakage-free run actually places a bet on the bet pair (else
        ``before.bets == after.bets`` is vacuously ``[] == []``);
    (1) the bet team Edge sits EXACTLY at the few-games boundary (4 < cutoff games
        -> few-games-provisional, IN the provisional set), and the volatility arm
        is OFF, so membership is driven purely by the COUNT;
    (2) the ADDED > cutoff row is VISIBLE to ``read(cutoff)`` (so the date<cutoff
        filter is the SOLE exclusion — else the invariance is masked for the wrong
        reason and is vacuous), and the leakage-free count at the cutoff is STILL 4;
    (3) LEAK SIMULATION: at a cutoff AFTER the added row, Edge counts 5 games ->
        NOT provisional -> DROPS OUT of the set — exactly what a count leak admitting
        the > cutoff row at the cutoff would do; AND that flip MOVES the recorded bet
        (price/side/stake/ledger). So a count leak WOULD move ``before != after``
        and the canary WOULD catch it — proving the count-mode assertion non-vacuous.
    """
    teams = ["Edge", "Foe", "Punch"]
    store = _count_boundary_store(tmp_path)
    samples, rfs, matches = _count_inputs()
    caches = _FreshFitCache(tmp_path)
    # Anchor OFF (see _anchor_off_cfg): with the Elo strength prior ON it dominates
    # the att/def prior mean and swamps mechanism-(c)'s provisional widening, so the
    # synthetic +EV bet at the boundary cutoff is filtered (below_edge) and the count-
    # mode teeth (provisional flip MOVES the bet) become vacuous. The anchor's own
    # point-in-time leakage-safety is tests/model/test_fit_strength_leakage.py.
    cfg = _anchor_off_cfg()

    # (0) the leakage-free run stakes exactly one bet on the bet pair.
    honest = walkforward(store, copy.deepcopy(samples),
                         results_for_settle=rfs.copy(), matches=matches,
                         config=cfg, fit_kwargs=_fit_kwargs(caches.next()))
    assert len(honest.bets) == 1, "leakage-free run must place a bet (else canary is vacuous)"
    assert list(honest.bets[0]["event_key"][:2]) == [_COUNT_BET_HOME, _COUNT_BET_AWAY]

    # (1) Edge is at the few-games boundary: exactly 4 < cutoff games, few-games arm
    #     ON, volatility arm OFF -> membership is purely the COUNT.
    from wcmodel.model.volatility_diagnostic import count_volatility_arm
    arm = count_volatility_arm(store, cutoff=_COUNT_CUTOFF, field_teams=teams)
    edge = arm.set_index("team").loc["Edge"]
    assert int(edge["games"]) == 4, "Edge must have EXACTLY 4 < cutoff games (the boundary)"
    assert bool(edge["few_games_flag"]) is True, "Edge (4 games) must trip the few-games arm"
    assert bool(edge["volatility_flag"]) is False, (
        "Edge's volatility arm must be OFF so membership is driven purely by the COUNT"
    )
    prov_before = _provisional_set(store, _COUNT_CUTOFF, teams)
    assert "Edge" in prov_before, "Edge (4 games) must be IN the provisional set at the cutoff"

    # (2) ADD the > cutoff row and prove it is VISIBLE to read(cutoff) — so the
    #     date<cutoff filter is the SOLE exclusion (not the store's observed_at
    #     masking, which would make the invariance vacuous). The leakage-free count
    #     at the cutoff is STILL 4 (Edge still IN the set).
    _add_post_cutoff_row(store)
    visible = store.read("results", cutoff=_COUNT_CUTOFF)
    assert (pd.to_datetime(visible["date"]) == _COUNT_EXTRA_DATE).any(), (
        "the added > cutoff row must be VISIBLE in read(cutoff) so the date<cutoff "
        "filter is the sole exclusion — else this proof is vacuous"
    )
    arm_after = count_volatility_arm(store, cutoff=_COUNT_CUTOFF, field_teams=teams)
    assert int(arm_after.set_index("team").loc["Edge"]["games"]) == 4, (
        "count_volatility_arm's date<cutoff filter must STILL count exactly 4 games "
        "for Edge — the > cutoff row must NOT inflate the count"
    )
    prov_after = _provisional_set(store, _COUNT_CUTOFF, teams)
    assert prov_before == prov_after and "Edge" in prov_after, (
        "provisional set CHANGED when a > cutoff row was added at the fixed cutoff "
        "-> count_volatility_arm leaked the > cutoff row into the games-count"
    )

    # (3) LEAK SIMULATION (the teeth) — a cutoff AFTER the added row, where the row
    #     is legitimately in-window (Edge counts 5) -> NOT provisional -> OUT. This
    #     is exactly what a leak admitting the > cutoff row at the cutoff would do.
    cutoff_after_row = _COUNT_EXTRA_DATE + pd.Timedelta(days=1)   # 2024-06-06
    arm_leak = count_volatility_arm(store, cutoff=cutoff_after_row, field_teams=teams)
    edge_leak = arm_leak.set_index("team").loc["Edge"]
    assert int(edge_leak["games"]) == 5, "past the added row, Edge must count 5 games"
    assert bool(edge_leak["few_games_flag"]) is False, "Edge with 5 games must NOT trip few-games"
    assert bool(edge_leak["volatility_flag"]) is False, (
        "Edge's volatility arm stays OFF so the flip is purely the few-games boundary"
    )
    prov_leak = _provisional_set(store, cutoff_after_row, teams)
    assert "Edge" not in prov_leak, "Edge must DROP OUT once the 5th game is counted"

    # The flip MOVES the recorded bet. A walk-forward run at cutoff_after_row (Edge
    # NOT provisional) records a DIFFERENT model price/side/stake than the run at
    # the boundary cutoff (Edge provisional, mechanism-(c) widening applied). This
    # is the ledger movement a count leak admitting the row at the boundary cutoff
    # would produce — the concrete `before != after` the canary's invariance catches.
    samples_b, rfs_b, matches_b = _count_inputs(_COUNT_CUTOFF)
    samples_l, rfs_l, matches_l = _count_inputs(cutoff_after_row)
    teeth_caches = _FreshFitCache(tmp_path / "teeth")
    bet_provisional = walkforward(
        store, copy.deepcopy(samples_b), results_for_settle=rfs_b.copy(),
        matches=matches_b, config=cfg, fit_kwargs=_fit_kwargs(teeth_caches.next())).bets[0]
    bet_not_provisional = walkforward(
        store, copy.deepcopy(samples_l), results_for_settle=rfs_l.copy(),
        matches=matches_l, config=cfg, fit_kwargs=_fit_kwargs(teeth_caches.next())).bets[0]
    assert bet_provisional["model"] != bet_not_provisional["model"], (
        "the provisional flip did NOT move the model price -> mechanism-(c) widening "
        "has no effect here, so the count-mode invariance assertion is vacuous"
    )
    assert bet_provisional["stake"] != bet_not_provisional["stake"], (
        "the provisional flip did NOT move the recorded stake -> a count leak would "
        "not move the ledger and the canary's count-mode assertion lacks teeth"
    )


def test_fit_leak_masked_by_shared_cache_caught_by_fresh_fits(tmp_path, monkeypatch):
    """GAP-1 RED-on-injected-FIT-LEAK proof: the fresh-fit fix is LOAD-BEARING.

    Injects a REAL fit-path leak — ``count_volatility_arm`` reading ``>= cutoff``
    rows (it feeds the posterior's ``provisional_teams``, hence the fit/predict
    price) — and proves:

      (RED-when-masked) under a SHARED posterior ``cache_dir`` the SECOND run HITS
        the first run's posterior (the key is < cutoff-only), so the leaked
        provisional flip is never recomputed and the count-mode canary PASSES
        VACUOUSLY (the masked PRIMARY surface — the focal Codex finding); AND
      (GREEN-when-fresh) under a UNIQUE fresh ``cache_dir`` per run the second run
        RE-FITS with the leaked provisional set, the bet price moves, and the SAME
        canary CORRECTLY RAISES ``BACKTEST LEAKAGE``.

    This injected leak is exercised by the COUNT perturbation (adding the > cutoff
    row): admitting that row flips Edge 4->5 games -> out of the provisional set ->
    moves the price. The contrast (masked vs caught) is the proof that forcing
    fresh fits is what gives the fit/posterior surface its teeth. The leak is
    reverted by ``monkeypatch`` teardown, restoring the clean engine."""
    import wcmodel.model.scoreline as scoreline
    import wcmodel.model.volatility_diagnostic as vol_diag

    real_arm = vol_diag.count_volatility_arm

    def leaky_count_volatility_arm(store, cutoff, field_teams, config=None):
        # THE INJECTED LEAK: ignore the as-of cutoff and count ALL rows the store
        # holds (including > cutoff rows visible via observed_at) -> Edge's count
        # inflates past the few-games boundary once the post-cutoff row is added.
        return real_arm(store, pd.Timestamp("2100-01-01"), field_teams, config=config)

    # `scoreline.fit` calls it as `count_volatility_arm(...)` (a name imported into
    # the scoreline module), so patch BOTH the source and the imported reference.
    monkeypatch.setattr(vol_diag, "count_volatility_arm", leaky_count_volatility_arm)
    monkeypatch.setattr(scoreline, "count_volatility_arm", leaky_count_volatility_arm)

    samples, rfs, matches = _count_inputs()
    # Anchor OFF (see _anchor_off_cfg): the injected count leak surfaces by flipping
    # Edge's provisional flag and MOVING the bet price. With the Elo strength prior ON
    # it dominates the att/def prior mean and swamps mechanism-(c)'s provisional
    # widening, so the leaked flip no longer moves the price enough to re-place/move
    # the bet -> the fresh-fit run would NOT raise (the load-bearing RED proof goes
    # vacuous). The anchor's own point-in-time leakage-safety is covered by
    # tests/model/test_fit_strength_leakage.py.
    cfg = _anchor_off_cfg()

    # (RED-when-masked) SHARED cache_dir: the second run HITS the first posterior,
    # so the leaked provisional flip is never recomputed -> the canary is VACUOUS
    # and PASSES even though the engine is (injected-)leaky.
    shared_store = _count_boundary_store(tmp_path / "shared")
    shared_dir = str(tmp_path / "shared_fitcache")

    def run_shared():
        return walkforward(shared_store, copy.deepcopy(samples),
                           results_for_settle=rfs.copy(), matches=matches,
                           config=cfg, fit_kwargs=_fit_kwargs(shared_dir))

    # Must NOT raise: the shared cache MASKS the injected fit leak (this is exactly
    # the vacuity the focal Codex finding flagged).
    assert_leakage_invariant(run_shared, lambda: _add_post_cutoff_row(shared_store), seed=0)

    # (GREEN-when-fresh) UNIQUE fresh cache_dir per run: the second run RE-FITS with
    # the leaked provisional set, the price moves, and the SAME canary CATCHES the
    # injected leak. This is the RED proof — the fresh-fit fix is load-bearing.
    fresh_store = _count_boundary_store(tmp_path / "fresh")
    caches = _FreshFitCache(tmp_path / "fresh_fitcache")

    def run_fresh():
        return walkforward(fresh_store, copy.deepcopy(samples),
                           results_for_settle=rfs.copy(), matches=matches,
                           config=cfg, fit_kwargs=_fit_kwargs(caches.next()))

    import pytest
    with pytest.raises(AssertionError, match="BACKTEST LEAKAGE"):
        assert_leakage_invariant(run_fresh, lambda: _add_post_cutoff_row(fresh_store), seed=0)
