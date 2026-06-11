"""Tournament (team-centric) artifact: per-team progression probabilities each paired with
its Monte-Carlo SE (Direct from SimResult), and future-KO slot occupants DERIVED from the
group-placing markets + the bracket slot definitions (spec §10 Derived). No fabrication:
an occupant only appears if it has a real placing probability.

Item A (standings): the predicted GROUP STANDINGS view — per group, per team, the group-stage
E[Pts]/E[GD] (Direct mean + MC-SE from the new SimResult.standings hook) and the qualification
fate split P(top2) = first+second, P(3rd qualify), P(eliminated) (Derived from the placing
markets + the SimResult.third_split hook). Every probability carries its SE companion; rows are
sorted by P(advance) = P(top2) + P(3rd qualify); each row's most-likely FATE is a colour summary
over the ALWAYS-VISIBLE numbers (the numbers are the claim, the colour is a hint)."""
from __future__ import annotations

import math

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


# ── Item A: predicted GROUP STANDINGS ────────────────────────────────────────────────────
# A team's qualification fate is a 3-way partition of every sim draw:
#   advance        = finished top-2 in the group          (P = first + second)
#   possible_third = finished 3rd AND made the best-8      (P = third_qualify)
#   eliminated     = finished 3rd-but-out, OR finished 4th (P = third_eliminated + out)
# These three PARTITION the unit (acceptance #1: P(top2)+P(3rd qualify)+P(eliminated)==1).
_FATES = ("advance", "possible_third", "eliminated")


def _binomial_se(p: float | None, n_sims: int) -> float | None:
    """MC SE sqrt(p(1-p)/N) for a COMBINED binomial proportion (e.g. P(top2) = first+second
    is itself a 0/1 'finished top 2' event per draw, so its SE is the binomial SE of the
    combined p — NOT the quadrature of the component SEs). None-safe: a null p -> null se."""
    if p is None or not isinstance(n_sims, int) or n_sims <= 0:
        return None
    return math.sqrt(max(p * (1.0 - p), 0.0) / n_sims)


def _node(value, se) -> dict:
    """A {value, se} envelope, NULL-safe (no_impute turns NaN/None -> null). Pairs every
    emitted number with its uncertainty companion (the no-naked-numbers grammar)."""
    return {"value": no_impute(value), "se": no_impute(se)}


def standings_view(simresult, *, groups: dict) -> dict:
    """Predicted group standings: ``{group_letter: [team_row, ...sorted by P(advance) desc]}``.

    ``groups`` is the bracket's ``{letter: [team, ...]}`` map (the SAME source of truth the
    sim ranked). Each ``team_row``:

      ``{"team", "exp_points": {value,se}, "exp_gd": {value,se},
         "p_top2": {value,se}, "p_third_qualify": {value,se}, "p_eliminated": {value,se},
         "p_advance": {value,se}, "fate": "advance"|"possible_third"|"eliminated"}``

    Direct: ``exp_points``/``exp_gd`` are the SimResult.standings mean + MC-SE-of-the-mean.
    Derived: ``p_top2`` = first+second, ``p_third_qualify``/``p_eliminated`` from the
    third_split hook + the ``out`` placing market — each a COMBINED binomial proportion, so
    its SE is the binomial MC SE of the combined p (computed here from n_sims), never a
    fabricated companion. ``fate`` is the argmax of the three partition probabilities — a
    COLOUR summary; the probabilities stay the claim. Rows are sorted by P(advance) =
    P(top2) + P(3rd qualify), descending.

    No fabrication: a team absent from the progression/standings tables (its group not
    simulated) is skipped. A team with a present placing market but a missing standings row
    still gets NULL-safe ``exp_*`` nodes (value=None) — never an imputed number."""
    prog, se = simresult.progression, simresult.se
    n_sims = getattr(simresult, "n_sims", 0)
    standings = getattr(simresult, "standings", None)
    third_split = getattr(simresult, "third_split", None)

    def _placing(team, market):
        return float(prog.at[team, market]) if (team in prog.index
                                                and market in prog.columns) else None

    def _exp(team, stat):
        # {value, se} from the standings hook; NULL-safe if the hook/team is absent.
        if standings is None or team not in standings.index:
            return _node(None, None)
        return _node(standings.at[team, (stat, "value")], standings.at[team, (stat, "se")])

    out: dict = {}
    for g in sorted(groups):
        rows = []
        for team in groups[g]:
            if team not in prog.index:
                continue                                   # group not simulated -> skip
            first = _placing(team, "first")
            second = _placing(team, "second")
            out_p = _placing(team, "out")
            # P(top2): first + second (mutually exclusive per draw -> a single binomial event).
            p_top2 = None if (first is None or second is None) else first + second
            # third_qualify / third_eliminated from the split hook (Derived); the eliminated
            # bucket folds in the `out` (4th-place) placing market.
            tq = (float(third_split.at[team, ("third_qualify", "value")])
                  if (third_split is not None and team in third_split.index) else None)
            te = (float(third_split.at[team, ("third_eliminated", "value")])
                  if (third_split is not None and team in third_split.index) else None)
            p_elim = None if (te is None or out_p is None) else te + out_p
            p_adv = None if (p_top2 is None or tq is None) else p_top2 + tq
            # Most-likely FATE = argmax of the 3-way partition (a colour summary). When a
            # component is null the fate is omitted (None) rather than guessed.
            parts = {"advance": p_top2, "possible_third": tq, "eliminated": p_elim}
            fate = (max(_FATES, key=lambda f: (parts[f] is not None, parts[f] or -1.0))
                    if all(parts[f] is not None for f in _FATES) else None)
            rows.append({
                "team": team,
                "exp_points": _exp(team, "exp_points"),
                "exp_gd": _exp(team, "exp_gd"),
                "p_top2": _node(p_top2, _binomial_se(p_top2, n_sims)),
                "p_third_qualify": _node(tq, _binomial_se(tq, n_sims)),
                "p_eliminated": _node(p_elim, _binomial_se(p_elim, n_sims)),
                "p_advance": _node(p_adv, _binomial_se(p_adv, n_sims)),
                "fate": fate,
            })
        # Sort by P(advance) desc (None last). Stable on ties -> bracket team order preserved.
        rows.sort(key=lambda r: (r["p_advance"]["value"] is not None,
                                 r["p_advance"]["value"] or -1.0), reverse=True)
        out[g] = rows
    return out
