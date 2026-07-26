"""Parse the verified tournament dict into a simulation-ready Bracket: groups,
group fixtures, the best-third slots (+ eligible group sets), and the knockout
feeder graph (match -> its two feeder refs). Pure structure — no Elo, no
posterior, no sim. The bracket is the SINGLE source of truth (Phase-1 verified);
nothing here re-derives FIFA linkage.

Discriminator (confirmed against config/tournament_2026.yaml via load_tournament):
the 72 group fixtures carry NO ``match`` field and real team names; the 32
knockout fixtures carry ``match`` in 73..104 and PLACEHOLDER refs (``1X``/``2X``
group-position slots, ``3rd-XXXXX`` best-third slots, ``W{n}`` winner-of-match
refs). Splitting on ``fx.get("match") is None`` therefore cleanly separates the
two — see ``test_bracket`` for the 72 / 73..104 assertions on the real data.

The shape constants are NOT baked in here: the slot grammar, round vocabulary
and group keys are edition-agnostic so a non-WC format (AFC Asian Cup 2027: 6
groups, 4 best-third-fed R16 slots, no third-place match) parses through the
same code — see ``test_bracket_format``. Malformed refs and unknown round
labels raise instead of silently shrinking the bracket.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# CLOSED vocabulary — every accepted label is enumerated, no fuzzy matching.
# The plural spellings are the official AFC schedule's labels; casing varies
# between AFC publications, so both are listed explicitly.
_ROUND = {"Round of 32": "R32", "Round of 16": "R16", "Quarter-final": "QF",
          "Semi-final": "SF", "Match for third place": "3rd-place", "Final": "Final",
          "Quarter-Finals": "QF", "Semi-Finals": "SF",
          "Quarter-finals": "QF", "Semi-finals": "SF"}

# Best-third slot ref: "3rd-" + the eligible group letters. WC-2026 publishes
# 5-letter sets (A..L); AFC Asian Cup 2027 publishes 3-letter sets (A..F). The
# grammar is length- and ceiling-agnostic; a "3rd-" ref that fails it is a
# config bug and raises rather than silently vanishing from the bracket.
_THIRD_SLOT_PREFIX = "3rd-"
_THIRD_SLOT_RE = re.compile(r"3rd-([A-Z]{2,})")


@dataclass(frozen=True)
class Bracket:
    # Counts below are the WC-2026 shape; the format block drives them per edition.
    groups: dict                 # {"A": [t1,t2,t3,t4], ...}  (WC: 12 groups)
    group_fixtures: dict         # {"A": [(home,away), ...6], ...}
    third_place_slots: dict      # {match_no: frozenset("ABCDF"), ...}  (WC: 8 slots)
    knockout_feeders: dict       # {match_no: (feeder_home, feeder_away)}  (WC: 73..104)
    match_round: dict            # {match_no: "R32"|"R16"|"QF"|"SF"|"3rd-place"|"Final"}


def build_bracket(tournament: dict) -> Bracket:
    groups = {g["name"]: list(g["teams"]) for g in tournament["groups"]}
    team_to_group = {t: g for g, ts in groups.items() for t in ts}
    group_fixtures = {g: [] for g in groups}
    third_slots, feeders, rounds = {}, {}, {}
    for fx in tournament["fixtures"]:
        m = fx.get("match")
        if m is None:                                   # group fixture (real teams)
            # Prefer the fixture's declared group over the team lookup: both
            # YAMLs carry it (WC-2026's 72 agree with the lookup exactly), and
            # it keeps parsing independent of the group->teams map.
            g = fx.get("group") or team_to_group[fx["home"]]
            group_fixtures[g].append((fx["home"], fx["away"]))
        else:                                           # knockout fixture (placeholders)
            label = fx.get("round")
            code = _ROUND.get(label)                     # no _ROUND value is None
            if code is None:
                raise ValueError(
                    f"match {m}: unknown round label {label!r}; "
                    f"known labels: {sorted(_ROUND)}")
            rounds[m] = code
            feeders[m] = (fx["home"], fx["away"])
            for ref in (fx["home"], fx["away"]):
                if not ref.startswith(_THIRD_SLOT_PREFIX):
                    continue                            # 1A/2B/W{n}/L{n} feeder
                mt = _THIRD_SLOT_RE.fullmatch(ref)
                if mt is None:                          # never drop it silently
                    raise ValueError(
                        f"match {m}: unresolved third-place slot ref {ref!r} — "
                        f"expected '{_THIRD_SLOT_PREFIX}' + two or more uppercase "
                        f"group letters (e.g. '3rd-ABCDF')")
                third_slots[m] = frozenset(mt.group(1))
    return Bracket(groups, group_fixtures, third_slots, feeders, rounds)
