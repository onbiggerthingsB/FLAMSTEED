import copy

from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.data.store import BitemporalStore
from wcmodel.live.clv_tracker import DRY_RUN_BANNER, PaperClvTracker, clv_report
from wcmodel.live.decide import decide_live
from wcmodel.live.ingest_live import ingest_live_result
from wcmodel.live.odds_live import live_snapshot_from_fixture
from wcmodel.live.scan import scan
from wcmodel.live.tournament import _settle
from wcmodel.live.validation import assert_entry_logged_at_decision_time


def _anchor_off(cfg: dict) -> dict:
    """Return a deep copy of ``cfg`` with the Elo strength anchor
    (``model.strength_prior``) forced OFF.

    The wrong-score settle-flip proof below checks the ingest->settle->log CHAIN (a wrong
    ingested score flips the settled P&L sign), orthogonal to the Elo strength anchor. It
    pins which side the decision stakes (``d.staked == "away"``). Pin the anchor OFF so the
    tiny coarse synthetic ``decide_live`` fit keeps ``home_adv`` well-identified (positive);
    on a degenerate anchored fit ``home_adv`` can go negative, flipping the priced side
    (here home<->away) and breaking the pinned-side precondition. The anchor's own behavior
    is validated at production fidelity + in ``tests/model``."""
    c = copy.deepcopy(cfg)
    c["model"]["strength_prior"]["enabled"] = False
    return c


def _settle_ingested(rstore: BitemporalStore, *, cutoff: str) -> str:
    """Read the played result POINT_IN_TIME and settle it to a 1X2 outcome via the
    SHARED ``tournament._settle`` (== walkforward ``_settle_outcome``) — the SAME rule
    the backtest engine uses. The outcome is derived from the INGESTED score, so a
    different ingested score yields a different settled outcome (genuine ingest->settle)."""
    settled = rstore.read("results", cutoff=cutoff)
    row = settled.iloc[0]
    return _settle(int(row["home_score"]), int(row["away_score"]))


def test_dry_run_end_to_end_full_loop(small_store, cfg, tmp_path):
    """The FULL live loop on the CLEARLY-NON-REAL synthetic harness, NO spend, GENUINELY
    CHAINED: the dry-run FETCH output is what DECIDE/SCAN price from, the INGESTED result
    is what SETTLE derives the P&L from (via ``_settle``), and the synthetic taint is
    PROPAGATED end-to-end into the ledger. Every number is labelled non-real; the mis-log
    canary passes; foresight-RED guards the tracker. A break at ANY stage fails the test
    (the chain is load-bearing, not decorative)."""
    # 1) FETCH (dry-run): a synthetic event's ACCUMULATED snapshot mapping (the early
    #    decision-time line + the kickoff close), NO network. This is the fetch OUTPUT
    #    the decision/scan CONSUME — not the raw sample (so the fetch->decide chain is real).
    s = synthetic_odds_sample(home="Brazil", away="Croatia",
                              commence="2024-06-30T19:00:00Z",
                              entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
                              bookmaker="pinnacle", seed=0)
    live_now = live_snapshot_from_fixture(s["sample"], which="all")
    assert live_now["_dry_run"] is True

    # 2) INGEST (post-match): write the ACTUAL played result POINT_IN_TIME (observed
    #    after kickoff) into an ISOLATED store so the small_store fit input is intact.
    rstore = BitemporalStore(tmp_path / "rstore")
    ingest_live_result(rstore, home_team="Brazil", away_team="Croatia",
                       date="2024-06-30", home_score=2, away_score=0,
                       tournament="FIFA World Cup", neutral=True, city="Inglewood",
                       country="United States", observed_at="2024-06-30T21:00:00Z")
    # SETTLE the bet from the INGESTED result (not a hard-coded score) via the shared
    # `_settle`: Brazil 2-0 -> "home". A different ingested score would settle differently.
    settled_outcome = _settle_ingested(rstore, cutoff="2024-07-01")
    assert settled_outcome == "home"

    # 3) DECIDE at cutoff=now, PRICING FROM THE FETCH OUTPUT (`live_now`) — proving the
    #    fetch->decide chain (the decision's entry is the FETCHED decision-time snapshot).
    d = decide_live(small_store, live_now, cutoff="2024-06-30T19:00:00Z",
                    config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # The mis-log canary passes ON THE FETCH OUTPUT decide priced from: the logged entry
    # is the decision-time snapshot, never the close (identity-pinned).
    assert_entry_logged_at_decision_time(d, live_now, bookmaker="pinnacle")
    assert d.is_synthetic is True
    assert d.staked != ""                          # the chain fired a real signal

    # 4) SCAN -> Ranked (edge x liquidity) ALSO consuming the FETCH OUTPUT, labelled non-real.
    ranked = scan(small_store, [{"sample": live_now, "liquidity": 50.0}],
                  cutoff="2024-06-30T19:00:00Z", config=cfg,
                  fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert ranked.is_synthetic is True

    # 5) LOG + CLV: settle the staked signal against the INGESTED result and log it.
    #    `won` is derived from the SETTLED outcome (ingest->settle->log), and the logged
    #    `is_synthetic` is PROPAGATED from the loop (the fetch/decide/scan taint), NOT
    #    hard-coded — so a broken taint or a wrong ingested score would change what is
    #    logged and trip the assertions below.
    loop_synthetic = bool(
        live_now.get("_is_synthetic", False) and d.is_synthetic and ranked.is_synthetic)
    tracker = PaperClvTracker(tmp_path / "ledger.jsonl")
    assert d.staked                                # a bet fired (chain is exercised)
    won = (d.staked == settled_outcome)            # ingest->settle->won, not hard-coded 2>0
    tracker.log_signal(
        event_key=d.event_key, staked=d.staked,
        entry_odds=d.entry_odds[d.staked], close_odds=d.close_odds[d.staked],
        stake=d.stake, won=won, match_type="wc_finals",
        confederation="CONMEBOL", venue=cfg["live"]["bookmaker"],
        commission=cfg["backtest"]["commission"], is_synthetic=loop_synthetic)

    # The logged record reflects the SETTLED P&L (a wrong ingested score -> a wrong `won`
    # -> a different paper_pnl) and the PROPAGATED taint (a broken taint -> is_synthetic
    # False here).
    logged = tracker.records()[0]
    assert logged["won"] is won
    assert logged["is_synthetic"] is True          # propagated, not hard-coded
    expected_pnl = (d.stake * (d.entry_odds[d.staked] - 1.0)) if won else -d.stake
    assert abs(logged["paper_pnl"] - expected_pnl) < 1e-9

    rep = clv_report(tracker.records())
    # The authoritative forward number is labelled non-real (dry-run) — never an edge claim.
    assert rep["is_synthetic"] is True
    assert rep["paper"] is True
    # FIX 4: the dry-run realized-CLV report carries an unmistakable NOT-REAL banner.
    assert rep["banner"] == DRY_RUN_BANNER
    # The whole loop produced a structured artifact + a CLV summary, no real spend.
    assert "clv_beat_close_rate" in rep["summary"]


def test_dry_run_e2e_is_a_genuine_chain_wrong_ingested_score_flips_settled_pnl(
        small_store, cfg, tmp_path):
    """PROOF the e2e is a GENUINE ingest->settle->log chain (not a facade): the SAME
    decision settled against TWO different ingested scores yields DIFFERENT settled P&L.
    If settlement were hard-coded (the old `2 > 0`), the wrong score could not change it."""
    s = synthetic_odds_sample(home="Brazil", away="Croatia",
                              commence="2024-06-30T19:00:00Z",
                              entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
                              bookmaker="pinnacle", seed=0)
    live_now = live_snapshot_from_fixture(s["sample"], which="all")
    d = decide_live(small_store, live_now, cutoff="2024-06-30T19:00:00Z",
                    config=_anchor_off(cfg),
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert d.staked, "the chain must fire a bet for the settle proof to be meaningful"

    def _settled_pnl(home_score: int, away_score: int, tag: str) -> float:
        rstore = BitemporalStore(tmp_path / f"rstore_{tag}")
        ingest_live_result(rstore, home_team="Brazil", away_team="Croatia",
                           date="2024-06-30", home_score=home_score, away_score=away_score,
                           tournament="FIFA World Cup", neutral=True, city="Inglewood",
                           country="United States", observed_at="2024-06-30T21:00:00Z")
        outcome = _settle_ingested(rstore, cutoff="2024-07-01")
        won = (d.staked == outcome)
        tracker = PaperClvTracker(tmp_path / f"ledger_{tag}.jsonl")
        tracker.log_signal(
            event_key=d.event_key, staked=d.staked,
            entry_odds=d.entry_odds[d.staked], close_odds=d.close_odds[d.staked],
            stake=d.stake, won=won, match_type="wc_finals", confederation="CONMEBOL",
            venue=cfg["live"]["bookmaker"], commission=cfg["backtest"]["commission"],
            is_synthetic=True)
        return tracker.records()[0]["paper_pnl"]

    # The TRUE score (Brazil 2-0 -> "home") and a DELIBERATELY-WRONG score that settles
    # to the staked side. The staked side here is "away" (the decision priced it), so a
    # 0-2 result ("away") makes the SAME bet a winner — flipping the settled P&L sign.
    assert d.staked == "away"                      # pin the staked side this seed produces
    pnl_true = _settled_pnl(2, 0, "true")          # Brazil win -> away bet LOSES -> -stake
    pnl_wrong = _settled_pnl(0, 2, "wrong")        # Croatia win -> away bet WINS -> +profit
    # The settled P&L genuinely depends on the INGESTED score (ingest->settle is wired).
    assert pnl_true != pnl_wrong
    assert pnl_true < 0 < pnl_wrong
