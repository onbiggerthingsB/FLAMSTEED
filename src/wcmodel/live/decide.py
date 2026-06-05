"""The live decision at ``cutoff = now`` (Phase-5 §2.3) — the Phase-4 per-cutoff
body, called ONCE.

This does NOT reimplement the per-cutoff decision. It calls the SAME merged Phase-4
functions ``walkforward._compute`` calls per fixture, with ``cutoff = now``:

  ``read(now)`` -> ``cached_fit(now)`` -> ``model_fair_1x2`` (1X2, the PRIMARY surface)
  + ``simulate(now)`` -> ``SimResult`` progression (SECONDARY, coverage-gated) ->
  ``entry_close_prices`` -> ``non_bet_snapshot`` -> ``market_fair_1x2(ENTRY)`` ->
  ``edge_vector(model, market_ENTRY)`` -> ``stake_fraction``.

FOCAL OPERATIONAL-LEAKAGE RULE (L5, §3, == walkforward.py FIX-1). The edge, the
staked side, and the stake are decided against the de-vigged ENTRY price — the
EARLIEST snapshot <= kickoff, the price available at the decision time ``now`` —
NEVER the CLOSE (the kickoff-1min line, information from AFTER the entry decision).
The close is RECORDED on the decision for later realized CLV (``entry/close - 1``)
and the close-market baseline ONLY. Logging the close as the entry would fake the
edge; the live mis-log canary (Task 4) proves a mis-log is caught.

SIGNAL-ONLY / PAPER (L2). ``LiveDecision.stake`` is a RECOMMENDATION fraction; no
bet is placed (no order/broker/exchange path). ``signal_only`` is stamped True.

REPRODUCIBLE. Same ``cutoff`` + ``seed`` -> identical ``LiveDecision`` (seeded
``cached_fit``; provenance auditable from the content-addressed cache key).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.backtest.baselines import edge_vector, market_fair_1x2, model_fair_1x2
from wcmodel.backtest.odds_ingest import (
    OUTCOMES, _SYNTHETIC_KEY, _bookmaker_prices, _parse_ts, _snapshot_has_book,
    book_aware_close, event_key, non_bet_snapshot,
)
from wcmodel.backtest.staking import stake_fraction
from wcmodel.backtest.clv import clv_pct


def _decision_time_entry(sample: dict, *, bookmaker: str, cutoff, close_ts: str | None):
    """The leakage-correct LIVE entry: the latest snapshot with ``timestamp <= cutoff``
    THAT CONTAINS ``bookmaker`` (the price transactable AT the decision time ``cutoff``).

    ODDS-SIDE LEAKAGE BOUNDARY (the T3 fix). ``entry_close_prices`` selects the entry
    by KICKOFF (earliest <= kickoff), which is NOT cutoff-aware — a snapshot AFTER
    ``cutoff`` (a future / post-decision price) could otherwise drive the edge/stake.
    Here we filter to snapshots whose ``timestamp <= cutoff`` BEFORE picking, so a
    ``> cutoff`` snapshot is STRUCTURALLY unusable. The kickoff CLOSE (``close_ts``) is
    EXCLUDED as an entry candidate — it is recorded for later CLV only and must never
    influence the decision (so even at ``cutoff >= kickoff`` the close cannot become the
    entry).

    BOOK-AWARE SELECTION (the T3 re-review fix). The decision-time price is the latest
    ``<= cutoff`` (close-excluded) snapshot THAT CONTAINS the configured book — NOT merely
    the latest ``<= cutoff`` snapshot. We iterate the candidates latest -> earliest and
    take the FIRST that has the book (book presence checked via ``_snapshot_has_book``,
    the SAME ``parse_snapshot`` rule ``_bookmaker_prices`` enforces). So a latest snapshot
    that lacks the book (e.g. only a different exchange refreshed) neither CRASHES
    ``_bookmaker_prices`` nor BLOCKS an earlier valid ``<= cutoff`` price for the book.

    Returns ``({home, draw, away} decimal odds, entry_ts)`` for the chosen decision-time
    snapshot, or ``(None, None)`` if NO ``<= cutoff`` (close-excluded) snapshot contains
    the book (a counted ``no_odds`` non-bet — never a crash, never a post-cutoff price).
    """
    ct = pd.Timestamp(cutoff)
    if ct.tzinfo is None:
        ct = ct.tz_localize("UTC")
    cutoff_dt = ct.to_pydatetime()
    # `close_ts` is None only when the configured book has no close snapshot at all (the
    # book is absent from the sample); then there is no close to exclude.
    close_dt = _parse_ts(close_ts) if close_ts is not None else None

    snaps = [
        v for v in sample.values()
        if isinstance(v, dict) and "timestamp" in v and "data" in v
    ]
    # Candidates: snapshots at/before the decision cutoff, EXCLUDING the kickoff close
    # snapshot (reserved for CLV). Sorted ascending; we scan from the latest backward.
    candidates = sorted(
        (s for s in snaps
         if _parse_ts(s["timestamp"]) <= cutoff_dt
         and _parse_ts(s["timestamp"]) != close_dt),
        key=lambda s: _parse_ts(s["timestamp"]),
    )
    # The entry is the LATEST candidate THAT CONTAINS the book: a latest snapshot missing
    # the book is skipped (not a crash) and does not block an earlier book-present price.
    for entry_snap in reversed(candidates):
        if not _snapshot_has_book(entry_snap, bookmaker):
            continue
        first_event = entry_snap["data"][0]
        prices = _bookmaker_prices(
            entry_snap, bookmaker, first_event["home_team"], first_event["away_team"]
        )
        return prices, entry_snap["timestamp"]
    # No <= cutoff snapshot contains the book -> a counted no_odds non-bet.
    return None, None


def _event_meta(sample: dict):
    """``(event_key, commence_time, is_synthetic)`` for the sample's single event, derived
    book-INDEPENDENTLY (the fixture/harness is one event per sample).

    Mirrors the event-identity derivation in ``entry_close_prices`` but takes NO bookmaker:
    so a sample whose configured book is absent can still be logged as a counted non-bet
    (with its event key + synthetic taint) instead of crashing before the decision is built.
    """
    snaps = [
        v for v in sample.values()
        if isinstance(v, dict) and "timestamp" in v and "data" in v
    ]
    if not snaps:
        raise ValueError("decide_live: sample has no snapshots")
    first_event = snaps[0]["data"][0]
    is_synth = bool(
        sample.get(_SYNTHETIC_KEY, False) or any(s.get(_SYNTHETIC_KEY) for s in snaps)
    )
    return event_key(first_event), first_event["commence_time"], is_synth


@dataclass
class LiveDecision:
    """One live signal at ``cutoff = now``. SIGNAL-ONLY: ``stake`` is a recommended
    bankroll fraction, not a placed bet. ``entry_odds`` is the price AT decision time
    (the logged transacted price) and ``entry_ts`` is the TIMESTAMP of that exact entry
    snapshot — the SNAPSHOT IDENTITY the mis-log canary pins on, so a close-as-entry
    mis-log is caught by identity even if the close and the decision-time price coincide
    in VALUE; ``close_odds`` is recorded for later CLV ONLY. ``is_synthetic`` taints the
    whole decision if the odds were non-real. ``entry_ts`` is ``None`` on a non-bet/no-odds
    path (no decision-time snapshot was selected)."""

    cutoff: str
    event_key: list                         # [home, away, commence_date-iso]
    market_surface: str                     # "1x2" (PRIMARY) | "progression" (SECONDARY)
    staked: str                             # the staked outcome (OUTCOMES) or "" if a non-bet
    model: dict = field(default_factory=dict)        # {home, draw, away} model fair probs
    market_entry: dict = field(default_factory=dict) # de-vigged ENTRY (the edge driver)
    edge: dict = field(default_factory=dict)          # {o: model[o] - market_entry[o]}
    entry_odds: dict = field(default_factory=dict)    # {home, draw, away} ENTRY decimal odds (logged)
    entry_ts: str | None = None             # the TIMESTAMP of the ENTRY snapshot (SNAPSHOT IDENTITY)
    close_odds: dict = field(default_factory=dict)    # {home, draw, away} CLOSE decimal odds (CLV only)
    stake: float = 0.0                      # RECOMMENDED bankroll fraction (signal, not a bet)
    non_bet_reason: str | None = None       # a filter reason if not bettable, else None
    is_synthetic: bool = False
    signal_only: bool = True                # L2: never a placed bet

    def realized_clv(self) -> float:
        """Realized CLV on the staked side: ``entry/close - 1`` (the logged entry vs
        the later close). NaN if no side was staked."""
        if not self.staked:
            return float("nan")
        return clv_pct(entry_odds=self.entry_odds[self.staked],
                       close_odds=self.close_odds[self.staked])

    def to_dict(self) -> dict:
        return {
            "cutoff": self.cutoff, "event_key": list(self.event_key),
            "market_surface": self.market_surface, "staked": self.staked,
            "model": self.model, "market_entry": self.market_entry, "edge": self.edge,
            "entry_odds": self.entry_odds, "entry_ts": self.entry_ts,
            "close_odds": self.close_odds,
            "stake": self.stake, "non_bet_reason": self.non_bet_reason,
            "is_synthetic": self.is_synthetic, "signal_only": self.signal_only,
        }


def decide_live(store, sample: dict, *, cutoff, config: dict | None = None,
                fit_kwargs: dict | None = None) -> LiveDecision:
    """Produce ONE live 1X2 signal at ``cutoff = now`` by calling the Phase-4 body.

    ``sample`` is the snapshot mapping (fixture / synthetic harness). ``cutoff`` is
    ``now`` (a tz-aware ISO ts is fine — the leakage-safe reads coerce it). Returns a
    ``LiveDecision`` whose ENTRY price drove the edge/stake and whose CLOSE is recorded
    for later CLV only.
    """
    cfg = config or load_config()
    bt = cfg["backtest"]
    live = cfg["live"]
    fit_kwargs = fit_kwargs or {}
    draws = fit_kwargs.get("draws", 200)

    # Event identity + the close (CLV only). The close is the BOOK-AWARE closing line —
    # the LATEST snapshot <= kickoff THAT CONTAINS the configured book — derived via
    # `book_aware_close`, INDEPENDENTLY of `entry_close_prices`' earliest-entry leg.
    #
    # WHY NOT `entry_close_prices` here (the FOCAL close-as-entry fix). Its earliest-entry
    # leg RAISES when the book is absent from the EARLIEST <= kickoff snapshot, even if
    # later (mid + close) snapshots DO have the book. Deriving `close_ts` through that
    # crashing path forced a `close_ts=None` fallback, which made the close EXCLUSION in
    # `_decision_time_entry` inert — so with `cutoff >= close_ts` the CLOSE snapshot became
    # the latest <= cutoff book-present candidate and was WRONGLY selected as the entry
    # (pricing edge/stake off post-decision info — a leak). `book_aware_close` finds the
    # close by scanning <= kickoff snapshots latest -> earliest for the book, so a
    # missing-earliest-book never makes `close_ts` None and the close is ALWAYS excluded
    # from the entry candidates. If NO <= kickoff snapshot has the book, the close is None
    # (the book-absent no-close case) and the (still-derived-below) decision-time entry is
    # itself empty -> a counted `no_odds` non-bet. Event metadata is derived
    # book-INDEPENDENTLY so the non-bet can still be logged with its event key.
    ekey, commence, is_synth = _event_meta(sample)
    home, away = ekey[0], ekey[1]
    bac = book_aware_close(sample, bookmaker=live["bookmaker"])
    if bac is not None:
        close_prices, close_ts = bac["close"], bac["close_ts"]
    else:
        close_prices, close_ts = {}, None

    # ODDS-SIDE LEAKAGE BOUNDARY. The ENTRY that drives edge/staked-side/stake is the
    # DECISION-TIME price (the latest snapshot <= cutoff THAT HAS the book), NOT the
    # kickoff-based entry `entry_close_prices` returns (it ignores `cutoff`) and NEVER a
    # > cutoff (future) snapshot. The CLOSE (latest <= kickoff) is recorded for later
    # realized CLV ONLY (T6); it never influences the decision. When there is no book
    # close, `close_ts` is None and the close exclusion in `_decision_time_entry` is inert
    # (no snapshot timestamp equals None), which is correct — there is nothing to exclude.
    entry_prices, entry_ts = _decision_time_entry(
        sample, bookmaker=live["bookmaker"], cutoff=cutoff, close_ts=close_ts,
    )

    base = LiveDecision(
        cutoff=str(cutoff), event_key=[ekey[0], ekey[1], str(ekey[2])],
        market_surface="1x2", staked="",
        entry_odds=dict(entry_prices) if entry_prices is not None else {},
        # SNAPSHOT IDENTITY: the timestamp of the EXACT decision-time snapshot
        # `_decision_time_entry` selected (None when there is no <= cutoff book price).
        # The mis-log canary pins on this ts so a close-as-entry mis-log is caught by
        # identity even when the close and the decision-time price coincide in value.
        entry_ts=entry_ts,
        close_odds=dict(close_prices), is_synthetic=is_synth,
        signal_only=bool(live["signal_only"]),
    )

    # No decision-time price (no snapshot <= cutoff for the book) => a COUNTED non-bet,
    # never a crash and never a future-priced bet off a post-cutoff snapshot.
    if entry_prices is None:
        base.non_bet_reason = "no_odds"
        return base

    # Non-bet snapshot filters (sign-flip / stale) on the DECISION-TIME ENTRY — logged,
    # stakes nothing.
    reason = non_bet_snapshot(entry_prices, entry_ts=entry_ts,
                              commence=commence, max_spread=bt["max_spread"],
                              stale_seconds=bt["stale_snapshot_seconds"])
    if reason is not None:
        base.non_bet_reason = reason
        return base

    # --- The Phase-4 per-cutoff body at cutoff = now. ---
    from wcmodel.model.cache import cached_fit

    try:
        post, _meta = cached_fit(
            cutoff=pd.Timestamp(cutoff), store=store,
            backend=fit_kwargs.get("backend", "advi"), draws=draws,
            seed=fit_kwargs.get("seed", cfg["seed"]),
            advi_iters=fit_kwargs.get("advi_iters", 2000),
            cache_dir=fit_kwargs.get("cache_dir", cfg["paths"]["cache"]),
            config=cfg,
        )
        model = model_fair_1x2(post, home=home, away=away, neutral=True)
    except KeyError:
        # A team absent from the as-of-now panel (no < now history) -> no model price.
        base.non_bet_reason = "no_model_price"
        return base

    # FOCAL: edge + staked side + stake decided against the de-vigged DECISION-TIME
    # ENTRY (<= cutoff), NEVER the close and NEVER a post-cutoff snapshot (== walkforward
    # FIX-1 + the T3 odds-boundary fix). The close is recorded above for CLV only.
    market_entry = market_fair_1x2(entry_prices, method=bt["devig_method"])
    edge = edge_vector(model, market_entry)
    staked = max(OUTCOMES, key=lambda o: edge[o])
    p_model = model[staked]
    se = float(np.sqrt(p_model * (1 - p_model) / max(draws, 1)))
    f = stake_fraction(prob=p_model, decimal_odds=entry_prices[staked], edge=edge[staked],
                       se=se, kelly_fraction=bt["kelly_fraction"],
                       edge_threshold=bt["edge_threshold"])

    base.model = model
    base.market_entry = market_entry
    base.edge = edge
    if f <= 0:
        base.non_bet_reason = "below_edge"
        return base
    base.staked = staked
    base.stake = float(f)
    return base
