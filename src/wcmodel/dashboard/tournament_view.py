"""Tournament (team-centric) artifact: per-team progression probabilities each paired with
its Monte-Carlo SE (Direct from SimResult), and future-KO slot occupants DERIVED from the
group-placing markets + the bracket slot definitions (spec §10 Derived). No fabrication:
an occupant only appears if it has a real placing probability."""
from __future__ import annotations

from wcmodel.dashboard.schema import no_impute

# Markets exposed per team (every one is a probability -> must carry its SE companion).
_MARKET_COLS = ["win_group", "advance_from_group", "reach_r16", "reach_qf", "reach_sf",
                "reach_final", "champion", "first", "second", "third", "out"]


def team_progression(simresult) -> dict:
    """``team -> {market: {"value": p, "se": mc_se}}`` for every market present in the
    SimResult, NULL-safe. Each probability travels with its binomial Monte-Carlo SE."""
    prog, se = simresult.progression, simresult.se
    out: dict = {}
    for team in prog.index:
        node: dict = {}
        for m in _MARKET_COLS:
            if m in prog.columns:
                node[m] = {"value": no_impute(prog.at[team, m]),
                           "se": no_impute(se.at[team, m])}
        out[team] = node
    return out


def ko_slot_occupants(*, slot_source: str, placing: dict) -> list[dict]:
    """Probable occupants of a knockout slot, DERIVED from the group-placing markets.

    ``slot_source`` is a bracket slot ref like ``"1A"`` (winner of group A), ``"2B"``
    (runner-up of B), or a third-place slot handled by the caller. ``placing`` is
    ``team -> {"first": p, "second": p, "third": p}`` for the relevant group. Returns the
    teams that can fill the slot, each with their real probability, most-likely first.
    Nothing is invented — a team with no placing probability does not appear."""
    pos = {"1": "first", "2": "second", "3": "third"}[slot_source[0]]
    occ = []
    for team, pm in placing.items():
        p = no_impute(pm.get(pos))
        if p is not None and p > 0.0:
            occ.append({"team": team, "prob": p})
    occ.sort(key=lambda o: o["prob"], reverse=True)
    return occ
