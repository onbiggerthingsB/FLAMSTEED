"""Parse the verified tournament dict into a simulation-ready Bracket: groups,
group fixtures, the eight R32 third-place slots (+ eligible group sets), and the
knockout feeder graph (match -> its two feeder refs). Pure structure — no Elo,
no posterior, no sim. The bracket is the SINGLE source of truth (Phase-1 verified);
nothing here re-derives FIFA linkage.

Discriminator (confirmed against config/tournament_2026.yaml via load_tournament):
the 72 group fixtures carry NO ``match`` field and real team names; the 32
knockout fixtures carry ``match`` in 73..104 and PLACEHOLDER refs (``1X``/``2X``
group-position slots, ``3rd-XXXXX`` best-third slots, ``W{n}`` winner-of-match
refs). Splitting on ``fx.get("match") is None`` therefore cleanly separates the
two — see ``test_bracket`` for the 72 / 73..104 assertions on the real data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ROUND = {"Round of 32": "R32", "Round of 16": "R16", "Quarter-final": "QF",
          "Semi-final": "SF", "Match for third place": "3rd-place", "Final": "Final"}


@dataclass(frozen=True)
class Bracket:
    groups: dict                 # {"A": [t1,t2,t3,t4], ...}  (12 groups)
    group_fixtures: dict         # {"A": [(home,away), ...6], ...}
    third_place_slots: dict      # {match_no: frozenset("ABCDF"), ...8 slots}
    knockout_feeders: dict       # {match_no: (feeder_home, feeder_away)}  73..104
    match_round: dict            # {match_no: "R32"|"R16"|"QF"|"SF"|"3rd-place"|"Final"}


def build_bracket(tournament: dict) -> Bracket:
    groups = {g["name"]: list(g["teams"]) for g in tournament["groups"]}
    team_to_group = {t: g for g, ts in groups.items() for t in ts}
    group_fixtures = {g: [] for g in groups}
    third_slots, feeders, rounds = {}, {}, {}
    for fx in tournament["fixtures"]:
        m = fx.get("match")
        if m is None:                                   # group fixture (real teams)
            g = team_to_group[fx["home"]]
            group_fixtures[g].append((fx["home"], fx["away"]))
        else:                                           # knockout fixture (placeholders)
            rounds[m] = _ROUND[fx["round"]]
            feeders[m] = (fx["home"], fx["away"])
            for ref in (fx["home"], fx["away"]):
                mt = re.fullmatch(r"3rd-([A-L]{5})", ref)
                if mt:
                    third_slots[m] = frozenset(mt.group(1))
    return Bracket(groups, group_fixtures, third_slots, feeders, rounds)
