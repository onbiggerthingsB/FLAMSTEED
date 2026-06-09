"""PROOF-OF-CONCEPT +EV value scanner — soft books vs the SHARP (Pinnacle) line.

NO MODEL. This is pure market-vs-market: the legit retail +EV mechanism. For each
event's H2H market we de-vig Pinnacle (the sharp consensus = the best estimate of
true probability), then for every OTHER book check whether its offered price pays
MORE than Pinnacle's fair probability implies:

    edge = pinnacle_fair_prob * soft_book_decimal_odds - 1      ( > 0  => +EV )

A positive edge means the soft book is slow / off the sharp line in your favor at
the moment of the bet (positive expected CLV). We scan the World Cup PLUS a few
other live markets so you can see the real shape of the opportunity (honest
expectation: the WC is thin; value lives in less-efficient markets).

Discipline (same as the model work): any edge > TOO_GOOD is flagged as a SUSPECTED
ARTIFACT (stale/suspended line, low-limit book, mismatched outcome), NOT trusted.

SIGNAL-ONLY. No bet placed. Key NEVER printed. HARD credit cap.
Run: PYTHONPATH=src .venv/bin/python scripts/ev_scan_poc.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx

_spec = importlib.util.spec_from_file_location(
    "scan_totals_forward", str(Path("scripts/scan_totals_forward.py")))
_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scan)

from wcmodel.data.devig import shin
from wcmodel.live.odds_live import CallBudget, fetch_live_odds

BASE = "https://api.the-odds-api.com/v4"
REGIONS = "us,uk,eu"
SHARP = "pinnacle"
EDGE_MIN = 0.02            # report soft-beats-sharp edges >= 2%
TOO_GOOD = 0.10           # > 10% edge => SUSPECTED artifact (stale/suspended/mismatch), hand-check
MAX_ODDS_CALLS = 6        # HARD credit cap (each us,uk,eu h2h pull ~3 credits)
# Recreational ("soft") books — the bettable venues. Sharps excluded from the bet target.
SOFT = {"betmgm", "draftkings", "fanduel", "betrivers", "williamhill", "bovada",
        "betonlineag", "mybookieag", "betsson", "leovegas", "unibet_uk", "unibet_eu",
        "unibet_nl", "unibet_se", "nordicbet", "casumo", "coolbet", "grosvenor",
        "betvictor", "skybet", "ladbrokes_uk", "betway", "gtbets", "betanysports"}
OTHER_SHARP = {"betfair_ex_uk", "betfair_ex_eu", "smarkets", "matchbook", "onexbet"}
# Preference order for which live sports to spend the (capped) odds calls on.
PREFER = ["soccer_fifa_world_cup", "baseball_mlb", "soccer_usa_mls",
          "soccer_conmebol_copa_america", "soccer_brazil_campeonato",
          "tennis_atp_french_open", "tennis_wta_french_open", "basketball_nba",
          "icehockey_nhl", "soccer_uefa_nations_league", "cricket_ipl",
          "americanfootball_nfl", "soccer_england_efl_cup"]


def list_sports(key: str) -> list[dict]:
    r = httpx.get(f"{BASE}/sports/", params={"apiKey": key}, timeout=30.0)
    r.raise_for_status()
    return r.json()


def fair_from_pinnacle(ev: dict) -> dict[str, float] | None:
    """De-vig Pinnacle's H2H outcomes -> {outcome_name: fair_prob}. None if absent/partial."""
    for bk in ev.get("bookmakers", []):
        if bk.get("key") != SHARP:
            continue
        for mk in bk.get("markets", []):
            if mk.get("key") != "h2h":
                continue
            outs = mk.get("outcomes", [])
            if len(outs) < 2:
                return None
            names = [o["name"] for o in outs]
            odds = [float(o["price"]) for o in outs]
            fair = shin(odds)
            return dict(zip(names, fair))
    return None


def soft_prices(ev: dict) -> list[tuple[str, str, float]]:
    """Every (book, outcome_name, decimal_odds) from non-Pinnacle books' H2H."""
    out = []
    for bk in ev.get("bookmakers", []):
        bkey = bk.get("key")
        if bkey == SHARP:
            continue
        for mk in bk.get("markets", []):
            if mk.get("key") != "h2h":
                continue
            for o in mk.get("outcomes", []):
                out.append((bkey, o["name"], float(o["price"])))
    return out


def main() -> int:
    key = _scan._load_env_key()
    budget = CallBudget(max_calls_per_day=MAX_ODDS_CALLS)
    _scan._install_credit_capture()
    try:
        sports = list_sports(key)  # FREE (does not count against quota)
        active = [s for s in sports if s.get("active") and not s.get("has_outrights")]
        print("=" * 90)
        print("PROOF-OF-CONCEPT +EV SCAN — soft books vs SHARP (Pinnacle) de-vigged line. NO MODEL.")
        print(f"  regions={REGIONS}  edge_min={EDGE_MIN:.0%}  too_good_flag>{TOO_GOOD:.0%}  "
              f"odds-call cap={MAX_ODDS_CALLS}")
        print("=" * 90)
        akeys = {s["key"] for s in active}
        print(f"[discover] {len(active)} active non-outright sports. Examples: "
              f"{sorted(akeys)[:18]}")
        targets = [k for k in PREFER if k in akeys][:MAX_ODDS_CALLS]
        # backfill with any other active soccer if we have call budget left
        if len(targets) < MAX_ODDS_CALLS:
            extra = [s["key"] for s in active
                     if s["key"].startswith("soccer_") and s["key"] not in targets]
            targets += extra[: MAX_ODDS_CALLS - len(targets)]
        print(f"[targets] scanning ({len(targets)}): {targets}\n")

        all_rows = []
        for sport in targets:
            try:
                events = fetch_live_odds(
                    api_key=key, sport=sport, regions=REGIONS, market="h2h",
                    dry_run=False, budget=budget, base_backoff=2.0, max_retries=3)
            except Exception as exc:  # noqa: BLE001
                print(f"[{sport}] pull failed/blocked: {type(exc).__name__} {exc}")
                continue
            n_pinn = 0
            rows = []
            for ev in events:
                fair = fair_from_pinnacle(ev)
                if not fair:
                    continue
                n_pinn += 1
                # best soft price per outcome -> edge vs pinnacle fair
                best = {}
                for bkey, name, price in soft_prices(ev):
                    if name not in fair:
                        continue
                    edge = fair[name] * price - 1.0
                    cur = best.get(name)
                    if cur is None or edge > cur[0]:
                        best[name] = (edge, bkey, price)
                for name, (edge, bkey, price) in best.items():
                    if edge >= EDGE_MIN:
                        rows.append({
                            "sport": sport, "match": f"{ev.get('home_team','?')} v {ev.get('away_team','?')}",
                            "pick": name, "book": bkey, "price": price,
                            "fair": fair[name], "edge": edge,
                            "soft": bkey in SOFT, "commence": ev.get("commence_time")})
            rows.sort(key=lambda r: -r["edge"])
            all_rows += rows
            print(f"[{sport}] {len(events)} events, {n_pinn} with Pinnacle; "
                  f"{len(rows)} outcomes with edge>={EDGE_MIN:.0%} "
                  f"({sum(1 for r in rows if r['soft'])} at SOFT books). "
                  f"calls spent={budget.spent}/{MAX_ODDS_CALLS}")
            for r in rows[:8]:
                flag = "  <-- TOO-GOOD (artifact?)" if r["edge"] > TOO_GOOD else ""
                tag = "soft" if r["soft"] else "other"
                print(f"    {r['match']:<40} {r['pick']:<22} +{r['edge']*100:4.1f}%  "
                      f"@ {r['price']:.2f} {r['book']}({tag}) fair={r['fair']:.3f}{flag}")
    finally:
        _scan.odds_live.httpx.get = _scan.odds_live.httpx.get  # noop; capture wrapper already local
        del key

    soft_rows = [r for r in all_rows if r["soft"]]
    realistic = [r for r in soft_rows if EDGE_MIN <= r["edge"] <= TOO_GOOD]
    toogood = [r for r in soft_rows if r["edge"] > TOO_GOOD]
    print("\n" + "=" * 90)
    print("[SUMMARY]")
    print(f"  {_scan._credit_line()}")
    print(f"  total soft-book +EV outcomes (edge>={EDGE_MIN:.0%}) = {len(soft_rows)}")
    print(f"    realistic ({EDGE_MIN:.0%}-{TOO_GOOD:.0%})  = {len(realistic)}   "
          f"<- the honest, bettable spots")
    print(f"    too-good (>{TOO_GOOD:.0%}, artifact-suspect) = {len(toogood)}   "
          f"<- almost always stale/suspended/mismatch, NOT free money")
    wc = [r for r in realistic if r["sport"] == "soccer_fifa_world_cup"]
    print(f"  of the realistic spots, World Cup = {len(wc)}  (expected: thin — WC is efficiently priced)")
    if realistic:
        print("  TOP realistic soft-book +EV spots:")
        for r in sorted(realistic, key=lambda r: -r["edge"])[:10]:
            print(f"    {r['sport']:<28} {r['match']:<34} {r['pick']:<20} "
                  f"+{r['edge']*100:4.1f}% @ {r['price']:.2f} {r['book']}")
    print("=" * 90)
    print("SIGNAL-ONLY. No bet placed. Edges are point-in-time; soft books move/limit fast.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
