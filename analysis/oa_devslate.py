#!/usr/bin/env python
"""Dev-slate population and 90-minute settlement — the corrected version.

WHY THIS EXISTS
---------------
The first cut of the H1/H2 tests settled dev-slate fixtures from the store's
FINAL score and excluded rows carrying a ``winner_override``. Both were wrong,
and a Codex review caught them:

1. ``winner_override`` is set only for PENALTY shootouts. A shootout happens
   only from a level score, so those 15 fixtures had the one 90' outcome that
   is known with certainty — a draw — and they were the fixtures dropped.
   Worse, dropping them is selection ON THE OUTCOME.
2. A knockout tie decided by an extra-time GOAL carries no override, so it
   sailed through and was scored on its ET-inclusive final. Four such matches
   were mis-labelled (Egypt-Morocco 2022-01-30, Netherlands-Croatia
   2023-06-14, Ivory Coast-Mali 2024-02-03, Argentina-Colombia 2024-07-14).
   The claim that this "only adds noise" was false: Ivory Coast-Mali moved
   book-minus-model from -0.088 to -0.014.

THE FIX: EXCLUDE BY STAGE, NEVER BY RESULT
------------------------------------------
A fixture is admitted only if extra time was STRUCTURALLY IMPOSSIBLE — group
or league phase. That is knowable before kickoff and conditions on nothing
that happened, which is exactly what the previous filter got wrong.

Knockout rounds are excluded wholesale rather than looked up. We hold no
verified 90' table for AFCON, Copa América or the Nations League finals
(``config/regulation_time_results.yaml`` covers only wc2022/euro2024/wc2026),
and the repo's standing rule is that a knockout fixture absent from such a
table is EXCLUDED, never inferred. Admitting only the shootouts back would
re-introduce outcome selection by another route — it would condition the
sample on "this one was a draw" and inflate the draw rate.

The boundaries below are the published competition formats, read off the
fixture calendar (each edition shows a clear multi-day gap between the last
group matchday and the first knockout round).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from wcmodel.data.tiers import confederation                  # noqa: E402
from wcmodel.eval.ledger import load_ledger                   # noqa: E402
from wcmodel.model.calibration import outcome_1x2, rps        # noqa: E402

DEV_LEDGER = _ROOT / "data" / "oa_dev_ledger.parquet"
STORE = _ROOT / "data" / "stores" / "full_final" / "results.parquet"
MODEL_ARM, BOOK_ARM = "dev_dc", "dev_odds_multiplicative"
OUTCOMES = ("home", "draw", "away")

#: First knockout date per edition, inclusive. A fixture on or after this date
#: within that edition could have gone past 90' and is excluded.
#: An edition absent from this map has NO knockout phase in the slate window.
KNOCKOUT_FROM = {
    ("African Cup of Nations", 2022): "2022-01-23",   # R16 after 01-20 groups
    ("African Cup of Nations", 2024): "2024-01-27",   # R16 after 01-24 groups
    # AFCON 2025 in-slate window (12-21..12-31) is group stage only; the
    # knockout rounds fall in January 2026, outside the acquisition window.
    ("Copa América", 2024): "2024-07-04",             # QF after 07-02 groups
}

#: Editions that are knockout IN THEIR ENTIRETY. The Nations League finals
#: (2023) and the 2025 quarter-finals + finals are single-elimination, so
#: every fixture in those windows could reach extra time.
ALL_KNOCKOUT_EDITIONS = {
    ("UEFA Nations League", 2023),
    ("UEFA Nations League", 2025),
}


class DevSlateError(RuntimeError):
    """The dev-slate population cannot be built as specified."""


def is_knockout(tournament: str, date: str) -> bool:
    """True if this fixture could have gone past 90 minutes.

    Determined by competition and calendar position only — never by score,
    by ``winner_override``, or by anything else the match produced.
    """
    year = int(str(date)[:4])
    key = (str(tournament), year)
    if key in ALL_KNOCKOUT_EDITIONS:
        return True
    cut = KNOCKOUT_FROM.get(key)
    return bool(cut and str(date) >= cut)


def build(*, dev_ledger=DEV_LEDGER, store=STORE) -> tuple[pd.DataFrame, dict]:
    """Return (frame, provenance) for fixtures where 90' == full time.

    ``frame`` carries one paired row per fixture; ``provenance`` records how
    many fixtures were dropped and why, so a shrinking population can never
    pass unnoticed.
    """
    ledger = load_ledger(dev_ledger)
    wide = ledger.pivot_table(
        index=["fixture_id", "pool", "date", "home", "away"], columns="arm",
        values=["p_home", "p_draw", "p_away"], aggfunc="first")

    results = pd.read_parquet(store)
    results["date"] = pd.to_datetime(results["date"]).dt.date.astype(str)
    by_key = {(str(r.date), str(r.home_team), str(r.away_team)):
              (r.home_score, r.away_score, r.tournament)
              for r in results.itertuples(index=False)}

    rows = []
    counts = {"total": 0, "knockout_excluded": 0, "no_store_row": 0,
              "no_odds_comparator": 0}
    for (fid, pool, date, home, away) in wide.index:
        counts["total"] += 1
        got = by_key.get((str(date), str(home), str(away)))
        if got is None:
            counts["no_store_row"] += 1
            continue
        home_goals, away_goals, tournament = got
        if is_knockout(tournament, date):
            counts["knockout_excluded"] += 1
            continue
        try:
            model = {k: float(wide.loc[(fid, pool, date, home, away),
                                       (f"p_{k}", MODEL_ARM)])
                     for k in OUTCOMES}
            book = {k: float(wide.loc[(fid, pool, date, home, away),
                                      (f"p_{k}", BOOK_ARM)])
                    for k in OUTCOMES}
        except KeyError:
            counts["no_odds_comparator"] += 1
            continue
        if any(np.isnan(v) for v in (*model.values(), *book.values())):
            counts["no_odds_comparator"] += 1
            continue

        actual = outcome_1x2(int(home_goals), int(away_goals))
        fav = max(book, key=book.get)
        rows.append({
            "fixture_id": fid, "pool": pool, "date": str(date),
            "home": home, "away": away, "tournament": tournament,
            "outcome": actual,
            "rps_model": rps(model, actual), "rps_book": rps(book, actual),
            "core": (confederation(home) in ("UEFA", "CONMEBOL")
                     and confederation(away) in ("UEFA", "CONMEBOL")),
            "fav_p_book": book[fav],
            "disagree": model[fav] - book[fav],
        })

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise DevSlateError("no admissible dev-slate fixtures — refusing to "
                            "report statistics on an empty population")
    # delta < 0 means the BOOK scored better (lower RPS wins)
    frame["delta"] = frame["rps_book"] - frame["rps_model"]
    frame["absdis"] = frame["disagree"].abs()
    counts["admitted"] = len(frame)
    return frame, counts
