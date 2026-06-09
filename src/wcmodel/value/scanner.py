from __future__ import annotations
from wcmodel.data.devig import shin

def _market_outcomes(book: dict, market: str, line: float | None) -> dict[str, float] | None:
    """{outcome_name: decimal_odds} for one book's market (totals filtered to `line`)."""
    for mk in book.get("markets", []) or []:
        if mk.get("key") != market:
            continue
        outs = {}
        for o in mk.get("outcomes", []) or []:
            if market == "totals" and line is not None and float(o.get("point", "nan")) != line:
                continue
            outs[o["name"]] = float(o["price"])
        return outs or None
    return None

def sharp_fair_probs(event: dict, *, market: str, line: float | None, sharp: str) -> dict[str, float] | None:
    """De-vig the sharp book's market (Shin) -> {outcome_name: fair_prob}. None if absent/partial."""
    for bk in event.get("bookmakers", []) or []:
        if bk.get("key") != sharp:
            continue
        outs = _market_outcomes(bk, market, line)
        if not outs or len(outs) < 2:
            return None
        names = list(outs); fair = shin([outs[n] for n in names])
        return dict(zip(names, fair))
    return None

def _kelly_stake(*, edge: float, odds: float, fraction: float) -> float:
    if edge <= 0 or odds <= 1.0:
        return 0.0
    return fraction * edge / (odds - 1.0)
