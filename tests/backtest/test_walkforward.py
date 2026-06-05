import numpy as np
import pandas as pd
import pytest

from wcmodel.backtest.walkforward import (
    EloMemo, build_cutoff_grid, walkforward, Metrics, _sample_is_synthetic,
)
from wcmodel.backtest.odds_ingest import synthetic_odds_sample, _SYNTHETIC_KEY


def test_elo_memo_matches_features_build_elo(small_store, cfg):
    """The memoised per-cutoff Elo must equal a from-scratch compute_elo_history on
    the SAME leakage-safe < cutoff slice (correctness preserved while skipping the
    O(N) recompute when the < cutoff result set is unchanged)."""
    from wcmodel.data.features import valid_played_results
    from wcmodel.data import tiers
    from wcmodel.data.elo import compute_elo_history

    cutoff = pd.Timestamp("2024-06-01")
    memo = EloMemo(small_store, config=cfg)
    got = memo.elo_as_of(cutoff)

    # Reference: replicate features.build's < cutoff_day, valid-played, K-wired input.
    res = small_store.read("results", cutoff=cutoff)
    res["date"] = pd.to_datetime(res["date"])
    res = res.loc[res["date"] < cutoff.normalize()].copy()
    res = valid_played_results(res)
    res["match_type"] = res["tournament"].map(tiers.match_type)
    ref = compute_elo_history(res[["match_id", "date", "home_team", "away_team",
                                   "home_score", "away_score", "neutral", "match_type"]],
                              config=cfg)
    # FIX 3 (strengthened): the WHOLE compute_elo_history frame must be byte-
    # identical between the memo and a from-scratch compute — same rows, same
    # rating_pre AND rating_post, not just the latest rating_pre per team. A
    # latest-rating_pre-only check could pass even if the memo silently dropped
    # or reordered interior rows or staled rating_post; .equals() locks it fully.
    assert got.reset_index(drop=True).equals(ref.reset_index(drop=True))


def test_elo_memo_is_cached_across_repeat_cutoffs(small_store, cfg):
    memo = EloMemo(small_store, config=cfg)
    a = memo.elo_as_of(pd.Timestamp("2024-06-01"))
    hits_before = memo.hits
    b = memo.elo_as_of(pd.Timestamp("2024-06-01"))     # identical < cutoff set -> cache hit
    assert memo.hits == hits_before + 1
    assert a.equals(b)


def _synthetic_run_inputs(small_store):
    """Build a one-event synthetic odds sample + the realised result that settles it,
    using teams + a date that exist in small_store (so the as-of-cutoff fit resolves).
    The settle result is a Brazil home win, and a model that likes Brazil at a juicy
    entry price gives a positive-edge bet. CLEARLY NON-REAL (synthetic harness)."""
    s = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00),      # generous entry on Brazil
        close=(2.10, 3.50, 3.40),      # close drifts shorter on Brazil -> +CLV
        bookmaker="pinnacle", seed=0,
    )
    results_for_settle = pd.DataFrame([{
        "home_team": "Brazil", "away_team": "Croatia",
        "date": pd.Timestamp("2024-06-30"), "home_score": 2, "away_score": 0,
        "tournament": "FIFA World Cup",
    }])
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-30"])})
    return [s], results_for_settle, matches


def test_walkforward_runs_and_taints_synthetic(small_store):
    samples, rfs, matches = _synthetic_run_inputs(small_store)
    m = walkforward(small_store, samples, results_for_settle=rfs, matches=matches,
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # The whole Metrics is tainted non-real (D1): no number here is ever an edge claim.
    assert m.is_synthetic is True and m.summary["is_synthetic"] is True
    # CLV + ROI summaries exist and the bet (if placed) recorded its tier + baselines.
    assert "clv_beat_close_rate" in m.summary and "roi_roi" in m.summary
    for b in m.bets:
        assert set(b["model"]) == {"home", "draw", "away"}
        assert "rps_market" in b and "rps_elo" in b
        # D1 rider: EVERY emitted per-bet record carries the SYNTHETIC marker.
        assert b["synthetic"] is True


def test_walkforward_cache_round_trips(tmp_path, small_store):
    samples, rfs, matches = _synthetic_run_inputs(small_store)
    kw = dict(results_for_settle=rfs, matches=matches,
              fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0},
              cache_dir=str(tmp_path))
    a = walkforward(small_store, samples, **kw)
    b = walkforward(small_store, samples, **kw)     # second call hits the content cache
    assert a.summary == b.summary
    assert (tmp_path).glob("walkforward-*.json")    # a cache artifact was written


# --------------------------------------------------------------------------- #
# FIX 1 (CRITICAL) — edge / staked-side / stake must be decided against the
# de-vigged ENTRY price, NEVER the close. The close is kickoff−1min — info from
# AFTER the entry decision; letting it drive the bet is future-line leakage.
# --------------------------------------------------------------------------- #
def _edge_run(small_store, *, close):
    """One-event run whose CLOSE we can vary while the ENTRY is fixed.

    Entry is a flat-ish 1X2 line; the model's own preference (not the close)
    must pick the staked side. We vary only ``close`` between runs.
    """
    s = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.60, 3.40, 2.90),      # FIXED entry (the price we transact at)
        close=close,                   # VARIED close (post-decision info)
        bookmaker="pinnacle", seed=0,
    )
    rfs = pd.DataFrame([{
        "home_team": "Brazil", "away_team": "Croatia",
        "date": pd.Timestamp("2024-06-30"), "home_score": 2, "away_score": 0,
        "tournament": "FIFA World Cup",
    }])
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-30"])})
    return walkforward(small_store, [s], results_for_settle=rfs, matches=matches,
                       fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})


def test_walkforward_edge_invariant_to_close_mutation(small_store):
    """THE leakage canary (FIX 1). Mutating ONLY the close must leave the bet
    decision — staked side, edge, stake — byte-identical; only CLV-derived fields
    (close_odds) may move. Before the fix, edge = model − devig(close), so a close
    that strongly favours a different outcome flips the staked side and the stake
    => the decision leaks the future line. After the fix, edge = model −
    devig(ENTRY), so the close cannot touch the decision."""
    # Close A: short home (de-vig favours home). Close B: short away (favours away).
    # If the close drives the decision these two runs disagree on the staked side.
    a = _edge_run(small_store, close=(1.50, 4.50, 7.00))   # home-skewed close
    b = _edge_run(small_store, close=(7.00, 4.50, 1.50))   # away-skewed close
    assert a.bets, "fixture must place a bet for the canary to bite"
    assert len(a.bets) == len(b.bets) == 1
    ba, bb = a.bets[0], b.bets[0]
    # The decision (side, edge, stake) is invariant to the close.
    assert ba["staked"] == bb["staked"]
    assert ba["edge"] == pytest.approx(bb["edge"])
    assert ba["stake"] == pytest.approx(bb["stake"])
    # And the edge is genuinely the model-vs-ENTRY edge (entry is identical),
    # not the model-vs-close edge (close differs wildly between the two runs).
    from wcmodel.backtest.baselines import market_fair_1x2
    from wcmodel.config import load_config
    devig_method = load_config()["backtest"]["devig_method"]
    entry = {"home": 2.60, "draw": 3.40, "away": 2.90}
    mkt_entry = market_fair_1x2(entry, method=devig_method)
    # edge recorded == model[staked] − devig(entry)[staked]
    assert ba["edge"] == pytest.approx(ba["model"][ba["staked"]] - mkt_entry[ba["staked"]])
    # Only the close-derived field differs (proof the close still flows to CLV).
    assert ba["close_odds"] != bb["close_odds"]


# --------------------------------------------------------------------------- #
# FIX 2 — the sweep must actually walk the per-matchday cutoff grid (one refit
# per matchday/cutoff, reused for every fixture at that cutoff) and odds_start
# must bound which fixtures are swept, not merely feed the cache key.
# --------------------------------------------------------------------------- #
def _multi_matchday_inputs(small_store):
    """Two fixtures on matchday-1 (same cutoff) + one on matchday-2 => 2 distinct
    cutoffs. A correct per-matchday sweep refits ONCE per cutoff (2 fits), not
    once per fixture (3 fits)."""
    md1a = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-20T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40), bookmaker="pinnacle")
    md1b = synthetic_odds_sample(
        home="Argentina", away="Croatia", commence="2024-06-20T16:00:00Z",
        entry=(2.20, 3.30, 3.40), close=(2.00, 3.40, 3.90), bookmaker="pinnacle")
    md2 = synthetic_odds_sample(
        home="Brazil", away="Argentina", commence="2024-06-25T19:00:00Z",
        entry=(2.60, 3.30, 2.80), close=(2.40, 3.35, 3.00), bookmaker="pinnacle")
    rfs = pd.DataFrame([
        {"home_team": "Brazil", "away_team": "Croatia",
         "date": pd.Timestamp("2024-06-20"), "home_score": 2, "away_score": 0,
         "tournament": "FIFA World Cup"},
        {"home_team": "Argentina", "away_team": "Croatia",
         "date": pd.Timestamp("2024-06-20"), "home_score": 1, "away_score": 1,
         "tournament": "FIFA World Cup"},
        {"home_team": "Brazil", "away_team": "Argentina",
         "date": pd.Timestamp("2024-06-25"), "home_score": 2, "away_score": 1,
         "tournament": "FIFA World Cup"},
    ])
    matches = pd.DataFrame({"date": pd.to_datetime(
        ["2024-06-20", "2024-06-20", "2024-06-25"])})
    return [md1a, md1b, md2], rfs, matches


def test_walkforward_refit_cadence_is_per_matchday(small_store, monkeypatch):
    """FIX 2: the posterior is refit ONCE per matchday/cutoff, reused for all
    fixtures at that cutoff — N distinct cutoffs => N fits, NOT one-per-fixture.
    We count the distinct cutoffs that reach cached_fit: 3 fixtures over 2
    matchdays must yield exactly 2 distinct refit cutoffs."""
    import wcmodel.model.cache as model_cache

    seen_cutoffs = []
    real_fit = model_cache.cached_fit

    def _spy(*args, **kwargs):
        seen_cutoffs.append(pd.Timestamp(kwargs["cutoff"]).normalize())
        return real_fit(*args, **kwargs)

    monkeypatch.setattr(model_cache, "cached_fit", _spy)

    samples, rfs, matches = _multi_matchday_inputs(small_store)
    m = walkforward(small_store, samples, results_for_settle=rfs, matches=matches,
                    fit_kwargs={"draws": 40, "advi_iters": 800, "seed": 0})
    distinct = sorted(set(seen_cutoffs))
    assert distinct == [pd.Timestamp("2024-06-20"), pd.Timestamp("2024-06-25")]
    # Per-matchday cadence: 2 distinct cutoffs, not 3 (one-per-fixture).
    assert len(distinct) == 2 and len(seen_cutoffs) == 2


def test_walkforward_odds_start_bounds_swept_fixtures(small_store):
    """FIX 2: ``odds_start`` (via the cutoff grid) must actually filter which
    fixtures are swept — a fixture whose matchday is BEFORE odds_start is not
    decided at any grid cutoff, so it is excluded from the run (not silently
    bet anyway). With odds_start set after the early fixture, only the late one
    is eligible."""
    samples, rfs, matches = _multi_matchday_inputs(small_store)
    from wcmodel.config import load_config
    cfg = load_config()
    # Move odds_start to AFTER matchday-1 (2024-06-20) but on/before matchday-2.
    cfg = {**cfg, "backtest": {**cfg["backtest"], "odds_start": "2024-06-22"}}
    m = walkforward(small_store, samples, results_for_settle=rfs, matches=matches,
                    config=cfg, fit_kwargs={"draws": 40, "advi_iters": 800, "seed": 0})
    swept_dates = {pd.Timestamp(b["cutoff"]).normalize() for b in m.bets}
    swept_dates |= {pd.Timestamp("2024-06-20")} if m.non_bets.get("out_of_window") else set()
    # The matchday-1 (06-20) fixtures are out of window; only 06-25 is in window.
    assert all(d >= pd.Timestamp("2024-06-22") for d in
               {pd.Timestamp(b["cutoff"]).normalize() for b in m.bets})
    # The two early fixtures are counted out-of-window, not bet.
    assert m.non_bets.get("out_of_window", 0) == 2


# --------------------------------------------------------------------------- #
# FIX 3 — EloMemo current rating must be rating_post of the last played match
# (not the one-match-stale rating_pre), and elo_as_of must be copy-safe.
# --------------------------------------------------------------------------- #
def test_elo_memo_current_rating_is_rating_post(small_store, cfg):
    """FIX 3: a team's as-of-cutoff CURRENT rating (for a FUTURE prediction) is
    its latest rating_post — the rating AFTER its last pre-cutoff match — NOT the
    rating_pre of that match, which is one match stale. Mirrors the proven
    leakage-safe semantics in model.calibration._leakage_safe_elo."""
    cutoff = pd.Timestamp("2024-06-01")
    memo = EloMemo(small_store, config=cfg)
    elo = memo.elo_as_of(cutoff)
    ratings = memo.latest_ratings(cutoff)
    # Reference: latest rating_post per team (the calibration.py rule).
    ref = (elo.sort_values("date", kind="mergesort")
              .groupby("team", sort=False)["rating_post"].last().to_dict())
    assert ratings == ref
    # And it must NOT equal the (stale) latest rating_pre for at least one team
    # that has played (rating_post != rating_pre whenever a match moved the rating).
    stale = (elo.sort_values("date", kind="mergesort")
                .groupby("team", sort=False)["rating_pre"].last().to_dict())
    assert any(abs(ratings[t] - stale[t]) > 1e-9 for t in ratings), (
        "expected at least one team whose rating moved, so post != stale pre")


def test_elo_as_of_returns_copy_not_cached_reference(small_store, cfg):
    """FIX 3 (copy-safety): elo_as_of must hand back a COPY so a caller mutating
    the returned frame cannot corrupt the memo's cached frame (and poison every
    later cutoff that shares the < cutoff result set)."""
    cutoff = pd.Timestamp("2024-06-01")
    memo = EloMemo(small_store, config=cfg)
    a = memo.elo_as_of(cutoff)
    a.loc[a.index[0], "rating_pre"] = -999999.0     # caller corrupts its copy
    b = memo.elo_as_of(cutoff)                       # cache hit
    assert (b["rating_pre"] != -999999.0).all(), "cache frame was mutated by caller"


# --------------------------------------------------------------------------- #
# FIX 4 — cache key completeness + value-identical HIT (incl. empty bets) + a
# true no-recompute HIT + per-component MISS.
# --------------------------------------------------------------------------- #
def _cache_kw(tmp_path, *, edge_threshold=None, devig_method=None,
              kelly_fraction=None, draws=60, seed=0, odds_start=None):
    from wcmodel.config import load_config
    cfg = load_config()
    bt = dict(cfg["backtest"])
    if edge_threshold is not None:
        bt["edge_threshold"] = edge_threshold
    if devig_method is not None:
        bt["devig_method"] = devig_method
    if kelly_fraction is not None:
        bt["kelly_fraction"] = kelly_fraction
    if odds_start is not None:
        bt["odds_start"] = odds_start
    cfg = {**cfg, "backtest": bt}
    return dict(config=cfg,
                fit_kwargs={"draws": draws, "advi_iters": 1500, "seed": seed},
                cache_dir=str(tmp_path))


def test_walkforward_cache_value_identical_hit(tmp_path, small_store):
    """FIX 4: a cold run and a warm (cache-HIT) reload must produce a
    VALUE-IDENTICAL Metrics — every summary field, the full bet ledger, the
    non-bet tallies — not merely a written artifact."""
    samples, rfs, matches = _synthetic_run_inputs(small_store)
    kw = dict(results_for_settle=rfs, matches=matches, **_cache_kw(tmp_path))
    cold = walkforward(small_store, samples, **kw)
    warm = walkforward(small_store, samples, **kw)
    assert cold.to_dict() == warm.to_dict()


def test_walkforward_cache_round_trip_empty_bets(tmp_path, small_store):
    """FIX 4: with an edge_threshold so high NO bet qualifies, the summary holds
    NaN aggregates. A cold Metrics vs a cache-HIT reload must STILL compare equal
    (NaN-safe), proving the empty-bets path round-trips cleanly."""
    samples, rfs, matches = _synthetic_run_inputs(small_store)
    kw = dict(results_for_settle=rfs, matches=matches,
              **_cache_kw(tmp_path, edge_threshold=10.0))   # impossible edge
    cold = walkforward(small_store, samples, **kw)
    warm = walkforward(small_store, samples, **kw)
    assert not cold.bets, "edge_threshold=10 must qualify zero bets"
    assert cold.to_dict() == warm.to_dict()


def test_walkforward_cache_hit_does_not_recompute(tmp_path, small_store, monkeypatch):
    """FIX 4: a warm call must be served from disk WITHOUT recomputing. We
    monkeypatch the inner compute (cached_fit) to raise on any warm invocation;
    if the run still returns, the HIT genuinely skipped compute."""
    import wcmodel.model.cache as model_cache
    samples, rfs, matches = _synthetic_run_inputs(small_store)
    kw = dict(results_for_settle=rfs, matches=matches, **_cache_kw(tmp_path))
    walkforward(small_store, samples, **kw)          # cold: populates the cache

    def _boom(*a, **k):
        raise AssertionError("cache HIT must not recompute (cached_fit called)")

    monkeypatch.setattr(model_cache, "cached_fit", _boom)
    warm = walkforward(small_store, samples, **kw)   # must be served from disk
    assert "roi_roi" in warm.summary


@pytest.mark.parametrize("mutate", [
    "edge_threshold", "devig_method", "kelly_fraction", "draws", "seed",
    "odds_start", "store", "odds",
])
def test_walkforward_cache_misses_on_each_key_component(tmp_path, small_store, mutate):
    """FIX 4: changing ANY determining input must MISS (a new artifact appears).
    Covers a staking DOF, the de-vig method, the fit draws, the seed, the cutoff
    grid driver (odds_start), the settled-results identity (store), and the odds.
    A miss == a second distinct cache file on disk."""
    samples, rfs, matches = _synthetic_run_inputs(small_store)
    base = dict(results_for_settle=rfs, matches=matches, **_cache_kw(tmp_path))
    walkforward(small_store, samples, **base)
    n0 = len(list(tmp_path.glob("walkforward-*.json")))

    if mutate == "edge_threshold":
        kw = dict(results_for_settle=rfs, matches=matches,
                  **_cache_kw(tmp_path, edge_threshold=0.03))
        walkforward(small_store, samples, **kw)
    elif mutate == "devig_method":
        kw = dict(results_for_settle=rfs, matches=matches,
                  **_cache_kw(tmp_path, devig_method="basic"))
        walkforward(small_store, samples, **kw)
    elif mutate == "kelly_fraction":
        kw = dict(results_for_settle=rfs, matches=matches,
                  **_cache_kw(tmp_path, kelly_fraction=0.5))
        walkforward(small_store, samples, **kw)
    elif mutate == "draws":
        kw = dict(results_for_settle=rfs, matches=matches,
                  **_cache_kw(tmp_path, draws=80))
        walkforward(small_store, samples, **kw)
    elif mutate == "seed":
        kw = dict(results_for_settle=rfs, matches=matches,
                  **_cache_kw(tmp_path, seed=7))
        walkforward(small_store, samples, **kw)
    elif mutate == "odds_start":
        kw = dict(results_for_settle=rfs, matches=matches,
                  **_cache_kw(tmp_path, odds_start="2020-07-01"))
        walkforward(small_store, samples, **kw)
    elif mutate == "store":
        # A revised settled result -> a different store_hash -> a miss.
        rfs2 = rfs.copy()
        rfs2.loc[0, "home_score"] = 5
        walkforward(small_store, samples, results_for_settle=rfs2, matches=matches,
                    **_cache_kw(tmp_path))
    elif mutate == "odds":
        s2 = synthetic_odds_sample(
            home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
            entry=(2.70, 3.40, 3.00), close=(2.10, 3.50, 3.40),  # entry nudged
            bookmaker="pinnacle", seed=0)
        walkforward(small_store, [s2], results_for_settle=rfs, matches=matches,
                    **_cache_kw(tmp_path))

    n1 = len(list(tmp_path.glob("walkforward-*.json")))
    assert n1 == n0 + 1, f"{mutate}: expected a cache MISS (new artifact), got {n0}->{n1}"


def test_walkforward_cache_key_distinguishes_wrapper_taint(tmp_path, small_store):
    """T5 Codex residual: the run-level synthetic taint must be a KEYED determining
    input, so the cached ``is_synthetic`` flag can never be stale-served.

    ``odds_hash`` is computed over the INNER snapshot sample (the wrapper is
    stripped at the call site), but ``Metrics.is_synthetic`` is derived from the
    WRAPPER-level ``is_synthetic`` (or a nested ``_is_synthetic``). So two runs
    with the SAME inner snapshot but DIFFERENT wrapper-level taint used to share a
    cache key — a HIT could then serve a cached Metrics whose ``is_synthetic`` flag
    is WRONG (a synthetic-tainted result read as real, defeating rider #1 via the
    cache). Folding the resolved run-level taint into the key gives the two runs
    DIFFERENT keys -> a MISS -> the taint can never be stale-served.

    Build two runs identical in every input EXCEPT the wrapper-level taint:
      * ``tainted``: the bare inner snapshot wrapped with ``is_synthetic=True`` and
        NO nested ``_is_synthetic`` (taint comes ONLY from the wrapper);
      * ``real``: the bare inner snapshot passed directly (no taint anywhere).
    The inner snapshot is byte-identical between them, so ``odds_hash`` matches;
    only the wrapper-level taint — and hence ``Metrics.is_synthetic`` — differs.
    """
    # A bare, clean inner snapshot with NO synthetic marker anywhere (strip both
    # the wrapper flag AND the nested `_is_synthetic` so the only taint signal is
    # the wrapper we add below). This is the "real" inner sample.
    wrapped = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40), bookmaker="pinnacle")
    bare = wrapped["sample"]
    bare.pop("is_synthetic", None)
    bare.pop(_SYNTHETIC_KEY, None)
    for snap in bare.values():
        if isinstance(snap, dict):
            snap.pop(_SYNTHETIC_KEY, None)
    # Sanity: the bare inner sample now self-identifies as REAL (no taint signal).
    assert not _sample_is_synthetic(bare)

    # The tainted run wraps that SAME bare inner sample with a wrapper-only taint.
    tainted = {"sample": bare, "is_synthetic": True}
    assert _sample_is_synthetic(tainted)              # taint comes from the wrapper
    # Both runs strip to the identical inner sample -> identical odds_hash.
    assert tainted.get("sample", tainted) is bare

    rfs = pd.DataFrame([{
        "home_team": "Brazil", "away_team": "Croatia",
        "date": pd.Timestamp("2024-06-30"), "home_score": 2, "away_score": 0,
        "tournament": "FIFA World Cup"}])
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-30"])})
    kw = dict(results_for_settle=rfs, matches=matches,
              fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0},
              cache_dir=str(tmp_path))

    m_real = walkforward(small_store, [bare], **kw)
    n_after_real = len(list(tmp_path.glob("walkforward-*.json")))
    m_tainted = walkforward(small_store, [tainted], **kw)
    n_after_tainted = len(list(tmp_path.glob("walkforward-*.json")))

    # The resolved Metrics.is_synthetic genuinely DIFFERS between the two runs, so
    # the taint really is a determining input the cache key MUST reflect.
    assert m_real.is_synthetic is False
    assert m_tainted.is_synthetic is True
    assert m_real.summary["is_synthetic"] is False
    assert m_tainted.summary["is_synthetic"] is True

    # The cache must MISS across them (a second, distinct artifact) — before the
    # fix the two share a key (same inner odds_hash) and the tainted run would HIT
    # the real run's artifact, stale-serving is_synthetic=False as synthetic.
    assert n_after_tainted == n_after_real + 1, (
        "wrapper-level taint must change the cache key (a MISS); a shared key would "
        "stale-serve the wrong is_synthetic flag")


# --------------------------------------------------------------------------- #
# FIX 5 — synthetic taint must derive from the authoritative entry_close_prices
# flag, so an UNWRAPPED/nested synthetic sample still taints the Metrics.
# --------------------------------------------------------------------------- #
def test_walkforward_taints_unwrapped_synthetic_sample(small_store):
    """FIX 5: a BARE synthetic sample (the inner snapshot mapping, no wrapper
    carrying is_synthetic) still self-identifies via the nested _is_synthetic
    flag that entry_close_prices reads. The Metrics — and every bet — must be
    tainted synthetic, so a synthetic ROI can never read as real."""
    wrapped = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40), bookmaker="pinnacle")
    bare = wrapped["sample"]                          # strip the wrapper
    assert not bare.get("is_synthetic")              # wrapper flag is gone
    rfs = pd.DataFrame([{
        "home_team": "Brazil", "away_team": "Croatia",
        "date": pd.Timestamp("2024-06-30"), "home_score": 2, "away_score": 0,
        "tournament": "FIFA World Cup"}])
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-30"])})
    m = walkforward(small_store, [bare], results_for_settle=rfs, matches=matches,
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert m.is_synthetic is True and m.summary["is_synthetic"] is True
    assert m.bets, "the bare synthetic sample should still place a bet"
    for b in m.bets:
        assert b["synthetic"] is True


# --------------------------------------------------------------------------- #
# FIX 6 — an odds-less / malformed sample is a COUNTED non-bet, never a crash
# that aborts the whole run.
# --------------------------------------------------------------------------- #
def test_walkforward_counts_oddsless_fixture_not_crash(small_store):
    """FIX 6: a real fixture whose snapshot has NO quote for the primary
    bookmaker must be a counted non-bet (no_odds/no_bookmaker), processed via
    continue — NOT a ValueError that aborts the entire walk-forward. A good
    fixture in the SAME run must still settle, proving the run continued."""
    good = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-20T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40), bookmaker="pinnacle")
    # A sample whose only book is NOT the primary (pinnacle) -> _bookmaker_prices
    # raises ValueError inside entry_close_prices. Must be caught + counted.
    bad = synthetic_odds_sample(
        home="Brazil", away="Argentina", commence="2024-06-25T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40), bookmaker="someother")
    rfs = pd.DataFrame([
        {"home_team": "Brazil", "away_team": "Croatia",
         "date": pd.Timestamp("2024-06-20"), "home_score": 2, "away_score": 0,
         "tournament": "FIFA World Cup"},
        {"home_team": "Brazil", "away_team": "Argentina",
         "date": pd.Timestamp("2024-06-25"), "home_score": 2, "away_score": 1,
         "tournament": "FIFA World Cup"},
    ])
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-20", "2024-06-25"])})
    # Must NOT raise.
    m = walkforward(small_store, [good, bad], results_for_settle=rfs, matches=matches,
                    fit_kwargs={"draws": 40, "advi_iters": 800, "seed": 0})
    # The odds-less fixture is counted, not crashed.
    assert (m.non_bets.get("no_odds", 0) + m.non_bets.get("no_bookmaker", 0)) >= 1
    # The good fixture still ran (a bet or a counted non-bet for it exists).
    assert m.bets or any(v for k, v in m.non_bets.items())
