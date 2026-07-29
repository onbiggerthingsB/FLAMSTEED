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


def _malformed_synthetic_item(liquidity: float = 50.0) -> dict:
    # A SYNTHETIC fixture (the non-real marker rides on the wrapper AND every nested
    # snapshot) that is also MALFORMED — its snapshots carry an EMPTY `data` list, so
    # `decide_live`'s `_event_meta`/`_decision_time_entry` RAISES (IndexError on
    # `snaps[0]["data"][0]`). The synthetic taint must still be detected per-sample
    # BEFORE the guarded `decide_live`, so even an all-malformed synthetic batch reads
    # non-real (rider #1 money-safety).
    s = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40), bookmaker="pinnacle", seed=0)
    sample = s["sample"]
    for snap in sample.values():
        if isinstance(snap, dict) and "data" in snap:
            snap["data"] = []          # malformed: decide_live raises, marker preserved
    return {"sample": sample, "liquidity": liquidity}


def test_scan_all_malformed_synthetic_run_is_still_tainted_non_real(small_store, cfg):
    # MONEY-SAFETY (Codex HIGH, rider #1): a batch whose fixtures are SYNTHETIC but
    # MALFORMED (decide_live raises on each) used to return is_synthetic=False with NO
    # dry-run banner — a synthetic/dry-run scan could be mistaken for real. The
    # synthetic taint is now detected per-sample BEFORE the guarded decide_live, so
    # even an all-malformed synthetic batch taints the whole run non-real.
    batch = [_malformed_synthetic_item(50.0), _malformed_synthetic_item(75.0)]
    ranked = scan(small_store, batch, cutoff="2024-06-30T19:00:00Z", config=cfg,
                  fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # Every fixture was caught by the batch guard (malformed) — yet the run is tainted.
    assert ranked.non_bets.get("malformed", 0) == 2
    assert ranked.opportunities == []
    # The whole artifact reads NON-REAL even though no decide_live ever succeeded.
    assert ranked.is_synthetic is True
    # And the written report LEADS with the unmissable DRY-RUN / NOT-REAL banner.
    report = render_scan_report(ranked)
    assert report.startswith("# DRY-RUN")
    assert "NOT AN EDGE CLAIM" in report


def test_scan_batch_guard_records_exception_detail(small_store, cfg):
    # DIAGNOSTICS (both reviews): the broad batch guard must RECORD the actual
    # exception so a SYSTEMIC bug (every fixture dying on the same error) is visible
    # rather than masquerading as generic "malformed" input. A malformed fixture with
    # NO snapshots -> decide_live raises ValueError("decide_live: sample has no
    # snapshots"); the sidecar list must capture that repr + the offending event id.
    bad = {"sample": {"garbage": 1, "event_id": "SYNTHETIC_bad_evt"}, "liquidity": 50.0}
    items = _two_synth_events()
    batch = [items[0], bad, items[1]]
    ranked = scan(small_store, batch, cutoff="2024-06-30T19:00:00Z", config=cfg,
                  fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # The malformed counter is intact (the run did not abort).
    assert ranked.non_bets.get("malformed", 0) >= 1
    # AND the new sidecar list captured the real error (visible, not opaque).
    detail = ranked.errors
    assert isinstance(detail, list) and len(detail) >= 1
    blob = repr(detail)
    assert "ValueError" in blob and "no snapshots" in blob
    # The offending event identifier is recorded so a systemic failure is locatable.
    assert "SYNTHETIC_bad_evt" in blob
    # The sidecar is serialised deterministically in the structured artifact.
    assert ranked.to_dict()["errors"] == detail


def test_event_id_reads_dict_shaped_data():
    # The defensive locator guarded on list-shaped ``data`` only, so a snapshot
    # in the per-event historical shape (data = ONE bare event dict, OA F13)
    # silently degraded to event=None — a systemic Plan-2 failure would lose
    # its event ids exactly when the sidecar is needed to locate it.
    from wcmodel.live.scan import _event_id
    item = {"sample": {"snap": {
        "timestamp": "2026-06-11T18:55:00Z",
        "data": {"id": "evt_dict_shape", "commence_time": "2026-06-11T19:00:00Z",
                 "home_team": "X", "away_team": "Y", "bookmakers": []},
    }}, "liquidity": 50.0}
    assert _event_id(item) == "evt_dict_shape"


def test_scan_is_reproducible_and_tie_break_deterministic(small_store, cfg):
    # REPRODUCIBILITY + STABLE TIE-BREAK (in-house review, now committed). Two scan
    # calls with the SAME seed/inputs -> identical Ranked.to_dict() AND identical
    # report; two opportunities with the SAME edge*liquidity rank_key preserve a
    # deterministic order (stable sort on input order).
    items = _two_synth_events()
    fk = {"draws": 60, "advi_iters": 1500, "seed": 0}
    a = scan(small_store, items, cutoff="2024-06-30T19:00:00Z", config=cfg, fit_kwargs=fk)
    b = scan(small_store, items, cutoff="2024-06-30T19:00:00Z", config=cfg, fit_kwargs=fk)
    assert a.to_dict() == b.to_dict()
    assert render_scan_report(a) == render_scan_report(b)
    # Stable tie-break: two opportunities with IDENTICAL edge*liquidity keep input order.
    tie = [
        {"event_key": ("A", "B", "2024"), "edge": 0.04, "liquidity": 50.0},
        {"event_key": ("C", "D", "2024"), "edge": 0.02, "liquidity": 100.0},
    ]
    assert rank_key(tie[0]) == rank_key(tie[1])      # same score -> a true tie
    ordered = sorted(tie, key=rank_key, reverse=True)
    assert [o["event_key"] for o in ordered] == [("A", "B", "2024"), ("C", "D", "2024")]
