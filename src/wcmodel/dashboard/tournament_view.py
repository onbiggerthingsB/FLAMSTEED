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


def ko_slot_occupants(*, slot_source: str, placing: dict):
    """Probable occupants of a knockout slot, DERIVED from the group-placing markets.

    ``slot_source`` is a bracket slot ref like ``"1A"`` (winner of group A), ``"2B"``
    (runner-up of B), or a third-place slot handled by the caller. ``placing`` is
    ``team -> {pos: ...}`` for the relevant group, where each position is EITHER the real
    ``team_progression`` node shape ``{"value": p, "se": se}`` OR a raw float (back-compat).
    Returns the teams that can fill the slot, each as ``{team, prob, se}`` most-likely first.
    Nothing is invented — a team with no placing probability > 0 does not appear; nothing is
    imputed.

    NO NAKED OCCUPANT PROB (FIX D). Each emitted occupant MUST carry a finite ``se`` companion
    (``team_progression`` always pairs every placing market's value with its binomial MC SE,
    so this holds on real data). If a qualifying occupant has a probability but NO finite se
    (the only path: a back-compat raw-float placing, or an upstream NaN SE), the WHOLE
    occupant-list GAPS (``coverage_gap``) rather than emit a naked prob — the gate
    (``gate_schedule._check_occupants``) would otherwise STOP the build, so we gap honestly
    instead of false-raising on a missing companion."""
    from wcmodel.dashboard.schema import coverage_gap

    pos = {"1": "first", "2": "second", "3": "third"}[slot_source[0]]
    occ = []
    for team, pm in placing.items():
        cell = pm.get(pos)
        if isinstance(cell, dict):                  # the real {value, se} node
            p = no_impute(cell.get("value"))
            se = no_impute(cell.get("se"))
        else:                                       # backward-compat: a raw float
            p = no_impute(cell)
            se = None
        if p is not None and p > 0.0:
            if se is None:
                # A qualifying occupant with no finite SE companion -> gap the whole list
                # (no naked occupant prob), never emit it.
                return coverage_gap(f"slot {slot_source}: occupant {team} has no se companion")
            occ.append({"team": team, "prob": p, "se": se})
    occ.sort(key=lambda o: o["prob"], reverse=True)
    return occ
