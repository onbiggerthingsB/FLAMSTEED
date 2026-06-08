"""+EV totals picks: compare the model's O/U prob to the RAW soft-book odds.

``edge = model_prob * soft_book_odds - 1`` is expected profit per unit staked at the actual offered
price (vig included — +EV value betting must overcome the vig, not remove it). A pick is placed only
when the edge, AFTER an uncertainty shrink, clears ``edge_threshold``; the stake reuses the project's
¼-Kelly × uncertainty-shrink (``backtest.staking.stake_fraction``). The model NEVER sees the odds.

Signature note (verified against ``backtest/staking.py``):
    ``stake_fraction(*, prob, decimal_odds, edge, se, kelly_fraction, edge_threshold)``
``kelly_fraction`` and ``edge_threshold`` are REQUIRED kwargs (no defaults); there is NO ``commission``
kwarg (commission is applied later, at settlement, by ``staking.settle_bet`` — not here). The bettable
decision is made HERE on the uncertainty-shrunk edge vs ``edge_threshold``; ``stake_fraction`` is then
called purely to SIZE the bet (¼-Kelly × shrink), so it is passed ``edge_threshold=0.0`` to avoid a
second, redundant gate on a DIFFERENT threshold (the staking trigger ``backtest.edge_threshold``).
``totals_edges`` stays pure/testable by taking the already-resolved ``kelly_fraction`` as an argument
(the harness/runner reads it from ``cfg["backtest"]``).
"""
from __future__ import annotations

from wcmodel.backtest.staking import stake_fraction, uncertainty_shrink


def totals_edges(model_probs: dict, book_totals: dict, *, edge_threshold: float,
                 se: float = 0.0, kelly_fraction: float = 0.25) -> list[dict]:
    """Return the +EV totals picks across all (line, side) the book offers AND the model prices.

    ``model_probs``: ``{line: {"over","under"}}``; ``book_totals``: ``{line: {"over_odds","under_odds"}}``.
    ``se`` is the model's predictive standard error for the prob (drives the shrink); pass 0.0 to
    disable shrink. A pick carries the model prob, raw odds, raw edge, and the staked fraction.

    A side is BET only when the uncertainty-shrunk edge ``edge * shrink(se)`` clears ``edge_threshold``
    (a confident thin edge can clear; a noisy thin edge is suppressed). ``stake_fraction`` then sizes
    the ¼-Kelly × shrink stake; ``kelly_fraction`` is the project's ¼-Kelly fraction (cfg.backtest).
    """
    picks: list[dict] = []
    shrink = uncertainty_shrink(se=se)
    for line, book in book_totals.items():
        mp = model_probs.get(line)
        if mp is None:
            continue
        for side in ("over", "under"):
            odds = book.get(f"{side}_odds")
            p = mp.get(side)
            if odds is None or p is None or not (odds > 1.0):
                continue
            edge = p * odds - 1.0
            # The bettable decision: the edge AFTER the uncertainty shrink must clear the totals
            # +EV threshold. ``stake_fraction`` then sizes the ¼-Kelly × shrink stake (its own gate
            # is neutralized with edge_threshold=0.0 so it never re-filters on a different threshold).
            effective_edge = edge * shrink
            if effective_edge < edge_threshold:
                continue
            stake = stake_fraction(prob=p, decimal_odds=odds, edge=edge, se=se,
                                   kelly_fraction=kelly_fraction, edge_threshold=0.0)
            if stake > 0.0:
                picks.append({"line": float(line), "side": side, "model_prob": float(p),
                              "odds": float(odds), "edge": float(edge), "stake": float(stake)})
    return picks
