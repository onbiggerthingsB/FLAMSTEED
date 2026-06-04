"""Phase-2 sizing diagnostic: which WC-2026 field teams trip the Elo
`provisional` flag's *volatility arm* (vs the few-games / debutant arm).

WHY THIS EXISTS (sizing, not modelling). Phase 1's `compute_elo_history`
(`src/wcmodel/data/elo.py`) flags a team `provisional=True` on EITHER of two
arms (RIDER 1):

  - **few-games arm** — fewer than `provisional_games` (5) prior matches
    (debutant / very thin history), or
  - **volatility arm** — population std of the team's last `volatility_window`
    (10) PRIOR rating deltas exceeds `provisional_volatility_threshold` (16.5):
    a long-but-erratic minor nation is low-information too.

A later Phase-2 task ("provisional-widening") spends effort widening the
scoreline-model prior for provisional teams. How much that matters for the
ACTUAL 48-team WC-2026 field depends on how many of those teams trip the
*volatility* arm specifically (the few-games arm is essentially irrelevant for a
WC field — every qualified nation has played far more than 5 matches). This
module produces that count. It is analysis-only: it computes nothing the model
consumes and writes no store state.

CAUSAL / NO-LEAKAGE. The metric is read entirely from matches **strictly before
`cutoff`** (`date < cutoff.normalize()`), reusing the SAME point-in-time Elo
(`compute_elo_history`) and the SAME `tiers.match_type` K-wiring that
`features.build` uses, so the K per competition is realistic rather than all-
"other". Only PLAYED matches enter (NaN-score WC-2026 fixtures on the live
martj42 feed are dropped) — an unplayed fixture has no rating delta.

WINDOW CONVENTION — a deliberate, documented subtlety vs `elo._provisional`.
`elo._provisional(team)` is evaluated **for each match** against that team's
deltas *strictly prior to that match* (the per-team delta list is appended only
AFTER the row is emitted). At a team's FINAL pre-cutoff match, that prior window
therefore EXCLUDES the final match's own delta.

This diagnostic instead measures each team's volatility from the last
`volatility_window` deltas **inclusive of its final pre-cutoff result** — i.e.
`recent_volatility` is the team's most up-to-date volatility *state as of its
last played match before the cutoff*, the quantity the Phase-2 prior should
react to when it next predicts that team. Equivalently: it is the value
`elo._provisional` WOULD use to flag that team's *next* (hypothetical) match.
The two windows differ by exactly one element (the inclusion of the final
delta); for `volatility_window=10` this is at most a one-of-ten shift and the
flag is a strict `> threshold` in both. We use the inclusive "current state"
window deliberately because that is what sizes prior-widening effort; the
one-element difference from the live per-match flag is noted here so no reader
mistakes this for a reimplementation of `_provisional`.

The threshold/window/few-games count are all read from
`load_config()["elo"]` — never hard-coded — so this stays pinned to the same
config the live Elo uses.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.data.elo import compute_elo_history
from wcmodel.data import tiers
from wcmodel.data.store import BitemporalStore


def count_volatility_arm(store: BitemporalStore, cutoff, field_teams: list[str]) -> pd.DataFrame:
    cfg = load_config()["elo"]
    win = int(cfg["volatility_window"]); thr = float(cfg["provisional_volatility_threshold"])
    n_few = int(cfg["provisional_games"])
    cutoff = pd.Timestamp(cutoff)
    res = store.read("results", cutoff=cutoff)
    res["date"] = pd.to_datetime(res["date"])
    res = res.loc[res["date"] < cutoff.normalize()].copy()
    res["match_type"] = res["tournament"].map(tiers.match_type)
    res = res.loc[res["home_score"].notna() & res["away_score"].notna()]
    elo = compute_elo_history(res[["match_id", "date", "home_team", "away_team",
                                   "home_score", "away_score", "neutral", "match_type"]])
    elo = elo.sort_values("date", kind="mergesort")
    rows = []
    for team in field_teams:
        t = elo[elo["team"] == team]
        games = len(t)
        if games == 0:
            rows.append(dict(team=team, games=0, recent_volatility=np.nan,
                             volatility_flag=False, few_games_flag=True)); continue
        deltas = (t["rating_post"] - t["rating_pre"]).to_numpy()
        window = deltas[-win:] if len(deltas) >= 1 else deltas
        vol = float(np.std(window)) if len(window) else np.nan
        few = games < n_few
        rows.append(dict(team=team, games=games, recent_volatility=vol,
                         volatility_flag=(not few) and (vol > thr), few_games_flag=few))
    return pd.DataFrame(rows)
