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

from wcmodel.value.types import ValueBet

def _book_last_update(event: dict, book: str) -> str | None:
    for bk in event.get("bookmakers", []) or []:
        if bk.get("key") == book:
            return bk.get("last_update")
    return None

def _lines_for(event: dict, market: str) -> list[float | None]:
    if market != "totals":
        return [None]
    pts = set()
    for bk in event.get("bookmakers", []) or []:
        for mk in bk.get("markets", []) or []:
            if mk.get("key") == "totals":
                for o in mk.get("outcomes", []) or []:
                    if "point" in o:
                        pts.add(float(o["point"]))
    return sorted(pts) if pts else []

def scan(events: list[dict], *, cfg, now: str) -> dict:
    bettable, filtered, gaps = [], [], []
    for ev in events:
        name = f"{ev.get('home_team','?')} v {ev.get('away_team','?')}"
        commence = ev.get("commence_time")
        for market in cfg.markets:
            for line in _lines_for(ev, market):
                fair = sharp_fair_probs(ev, market=market, line=line, sharp=cfg.sharp_book)
                if fair is None:
                    gaps.append({"event": name, "market": market, "line": line,
                                 "reason": f"no sharp ({cfg.sharp_book}) line"})
                    continue
                # per-book edges; track which books are +EV on EVERY outcome (stale de-vig)
                per_book: dict[str, list[tuple[str, float, float]]] = {}
                for bk in ev.get("bookmakers", []) or []:
                    bkey = bk.get("key")
                    if bkey == cfg.sharp_book:
                        continue
                    outs = _market_outcomes(bk, market, line)
                    if not outs:
                        continue
                    for nm, odds in outs.items():
                        if nm not in fair:
                            continue
                        per_book.setdefault(bkey, []).append((nm, odds, fair[nm] * odds - 1.0))
                both_sides = {bk for bk, rows in per_book.items()
                              if len(rows) >= 2 and all(e > 0 for *_, e in rows)}
                for bkey, rows in per_book.items():
                    lu = _book_last_update(ev, bkey)
                    for nm, odds, edge in rows:
                        if edge <= 0:
                            continue
                        flags, ok = classify_edge(book=bkey, edge=edge, odds=odds, last_update=lu,
                                                  now=now, both_sides_book=bkey in both_sides, cfg=cfg)
                        vb = ValueBet(event=name, commence_time=commence, market=market, line=line,
                                      side=nm, sharp_book=cfg.sharp_book, sharp_fair_prob=fair[nm],
                                      soft_book=bkey, soft_odds=odds, edge=edge,
                                      suggested_stake=_kelly_stake(edge=edge, odds=odds, fraction=cfg.kelly_fraction) if ok else 0.0,
                                      book_tier="soft" if bkey in cfg.soft_books else "other_sharp",
                                      last_update=lu, flags=flags, bettable=ok).to_dict()
                        (bettable if ok else filtered).append(vb)
    bettable.sort(key=lambda x: -x["edge"])
    filtered.sort(key=lambda x: -x["edge"])
    return {"bettable": bettable, "filtered": filtered, "coverage_gaps": gaps}
