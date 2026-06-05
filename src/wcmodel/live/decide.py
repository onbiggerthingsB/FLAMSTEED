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
from wcmodel.backtest.odds_ingest import OUTCOMES, entry_close_prices, non_bet_snapshot
from wcmodel.backtest.staking import stake_fraction
from wcmodel.backtest.clv import clv_pct


@dataclass
class LiveDecision:
    """One live signal at ``cutoff = now``. SIGNAL-ONLY: ``stake`` is a recommended
    bankroll fraction, not a placed bet. ``entry_odds`` is the price AT decision time
    (the logged transacted price); ``close_odds`` is recorded for later CLV ONLY.
    ``is_synthetic`` taints the whole decision if the odds were non-real."""

    cutoff: str
    event_key: list                         # [home, away, commence_date-iso]
    market_surface: str                     # "1x2" (PRIMARY) | "progression" (SECONDARY)
    staked: str                             # the staked outcome (OUTCOMES) or "" if a non-bet
    model: dict = field(default_factory=dict)        # {home, draw, away} model fair probs
    market_entry: dict = field(default_factory=dict) # de-vigged ENTRY (the edge driver)
    edge: dict = field(default_factory=dict)          # {o: model[o] - market_entry[o]}
    entry_odds: dict = field(default_factory=dict)    # {home, draw, away} ENTRY decimal odds (logged)
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
            "entry_odds": self.entry_odds, "close_odds": self.close_odds,
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

    pc = entry_close_prices(sample, bookmaker=live["bookmaker"])
    ekey = pc["event_key"]
    home, away = ekey[0], ekey[1]
    is_synth = bool(pc["is_synthetic"])

    base = LiveDecision(
        cutoff=str(cutoff), event_key=[ekey[0], ekey[1], str(ekey[2])],
        market_surface="1x2", staked="", entry_odds=dict(pc["entry"]),
        close_odds=dict(pc["close"]), is_synthetic=is_synth,
        signal_only=bool(live["signal_only"]),
    )

    # Non-bet snapshot filters (sign-flip / stale) on the ENTRY — logged, stakes nothing.
    reason = non_bet_snapshot(pc["entry"], entry_ts=pc["entry_ts"],
                              commence=pc["commence_time"], max_spread=bt["max_spread"],
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

    # FOCAL: edge + staked side + stake decided against the de-vigged ENTRY, NEVER the
    # close (== walkforward FIX-1). The close is recorded above for CLV only.
    market_entry = market_fair_1x2(pc["entry"], method=bt["devig_method"])
    edge = edge_vector(model, market_entry)
    staked = max(OUTCOMES, key=lambda o: edge[o])
    p_model = model[staked]
    se = float(np.sqrt(p_model * (1 - p_model) / max(draws, 1)))
    f = stake_fraction(prob=p_model, decimal_odds=pc["entry"][staked], edge=edge[staked],
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
