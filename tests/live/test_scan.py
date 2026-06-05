import pandas as pd

from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.live.scan import scan, Ranked, rank_key, render_scan_report


def _two_synth_events():
    # Two CLEARLY NON-REAL synthetic 1X2 events with different edges + liquidity.
    big = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40), bookmaker="pinnacle", seed=0)
    small = synthetic_odds_sample(
        home="France", away="Argentina", commence="2024-06-30T19:00:00Z",
        entry=(2.20, 3.30, 3.40), close=(2.15, 3.35, 3.45), bookmaker="pinnacle", seed=0)
    return [
        {"sample": big["sample"], "liquidity": 100.0},
        {"sample": small["sample"], "liquidity": 5.0},
    ]


def test_rank_key_is_edge_times_liquidity():
    # The ranking score is edge x liquidity (higher = better opportunity).
    assert rank_key({"edge": 0.05, "liquidity": 100.0}) == 0.05 * 100.0
    assert rank_key({"edge": 0.05, "liquidity": 5.0}) == 0.05 * 5.0


def test_scan_ranks_by_edge_times_liquidity_and_taints_synthetic(small_store, cfg):
    items = _two_synth_events()
    ranked = scan(small_store, items, cutoff="2024-06-30T19:00:00Z", config=cfg,
                  fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert isinstance(ranked, Ranked)
    # Both surfaces present in the structured artifact.
    assert ranked.primary_surface == "1x2"
    # The 1X2 opportunities are sorted by edge x liquidity descending.
    scores = [rank_key(o) for o in ranked.opportunities]
    assert scores == sorted(scores, reverse=True)
    # Non-real taint propagates to the whole artifact (dry-run / synthetic).
    assert ranked.is_synthetic is True


def test_scan_coverage_gaps_a_below_threshold_progression_market(small_store, cfg):
    # The progression/outright surface is SECONDARY + coverage-gated: with no outright
    # odds supplied (the common dry-run case), it renders as a COVERAGE GAP, never a number.
    items = _two_synth_events()
    ranked = scan(small_store, items, cutoff="2024-06-30T19:00:00Z", config=cfg,
                  fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert ranked.progression_surface["coverage_gap"] is True
    assert "insufficient" in ranked.progression_surface["render"].lower()
    # No CLV/edge number leaks from a coverage-gapped surface.
    assert "edge" not in ranked.progression_surface


def test_scan_non_bet_filter_excludes_stale_from_ranking(small_store, cfg):
    items = _two_synth_events()
    items[0]["sample"]["bet_time"]["timestamp"] = "2024-06-01T00:00:00Z"  # stale entry
    ranked = scan(small_store, items, cutoff="2024-06-30T19:00:00Z", config=cfg,
                  fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # The stale event is counted as a non-bet, not ranked as an opportunity.
    assert ranked.non_bets.get("stale", 0) >= 1
    keys = [tuple(o["event_key"]) for o in ranked.opportunities]
    assert ("Brazil", "Croatia", "2024-06-30") not in keys


def test_scan_batch_guard_one_malformed_fixture_is_counted_not_a_crash(small_store, cfg):
    # BATCH GUARD (T3's deferred concern, now T5's job): the scanner iterates many
    # fixtures; a single malformed / odds-less / decide_live-raising item must be a
    # COUNTED non-bet (caught, reason recorded, skipped), NEVER a run-aborting crash —
    # the live analog of the Phase-4 walkforward Stage-1 guarded batch loop.
    items = _two_synth_events()
    # Inject a malformed fixture between the two good ones: a sample with NO snapshots
    # (decide_live -> ValueError "sample has no snapshots"). The run must complete, the
    # bad one is counted, and the good ones still rank.
    bad = {"sample": {"garbage": 1}, "liquidity": 50.0}
    batch = [items[0], bad, items[1]]
    ranked = scan(small_store, batch, cutoff="2024-06-30T19:00:00Z", config=cfg,
                  fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # The malformed fixture is a COUNTED non-bet (the run did not abort).
    assert ranked.non_bets.get("malformed", 0) >= 1
    # The good fixtures still produced ranked opportunities (the run completed).
    assert len(ranked.opportunities) >= 1
    scores = [rank_key(o) for o in ranked.opportunities]
    assert scores == sorted(scores, reverse=True)
    # The malformed fixture never leaked into the ranking.
    keys = [tuple(o["event_key"]) for o in ranked.opportunities]
    assert all(len(k) == 3 for k in keys)


def test_render_scan_report_leads_non_real_and_is_text(small_store, cfg):
    items = _two_synth_events()
    ranked = scan(small_store, items, cutoff="2024-06-30T19:00:00Z", config=cfg,
                  fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    report = render_scan_report(ranked)
    # A written report (no UI), leading with the unmissable non-real banner.
    assert isinstance(report, str)
    assert "DRY-RUN" in report and "NOT AN EDGE CLAIM" in report
    assert "edge" in report.lower() and "liquidity" in report.lower()
