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

from datetime import datetime, timezone

def _age_seconds(last_update: str | None, now: str) -> float | None:
    if not last_update:
        return None
    try:
        lu = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
        n = datetime.fromisoformat(now.replace("Z", "+00:00"))
        return (n - lu).total_seconds()
    except ValueError:
        return None

def classify_edge(*, book: str, edge: float, odds: float, last_update: str | None, now: str,
                  both_sides_book: bool, cfg) -> tuple[list[str], bool]:
    flags: list[str] = []
    if book not in cfg.soft_books:
        flags.append("non_soft")
    if edge < cfg.edge_min:
        flags.append("below_min")
    if edge > cfg.too_good:
        flags.append("too_good")
    if odds > cfg.longshot_odds:
        flags.append("fragile")
    age = _age_seconds(last_update, now)
    if age is not None and age > cfg.stale_seconds:
        flags.append("stale")
    if both_sides_book:
        flags.append("both_sides")
    bettable = not flags          # bettable iff NO guard fired
    return flags, bettable
