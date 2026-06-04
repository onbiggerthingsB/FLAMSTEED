"""Group standings + FIFA 2026 tiebreakers. Order: points, goal difference, goals
scored, then the HEAD-TO-HEAD mini-table among the still-tied teams (their points
-> GD -> GF, recomputed from THIS call's own results), then a SEEDED random draw
standing in for the unmodellable fair-play/lots tail. The head-to-head table is
recomputed per call from the passed results -- nothing precomputed or shared."""
from __future__ import annotations

import numpy as np


def group_table(teams, results):
    """Per-team {points, gf, ga, gd} accumulated over ``results`` (a dict
    ``{(home, away): (home_goals, away_goals)}``). Pure: no IO, no global state."""
    tbl = {t: {"points": 0, "gf": 0, "ga": 0} for t in teams}
    for (h, a), (hg, ag) in results.items():
        tbl[h]["gf"] += hg
        tbl[h]["ga"] += ag
        tbl[a]["gf"] += ag
        tbl[a]["ga"] += hg
        if hg > ag:
            tbl[h]["points"] += 3
        elif hg < ag:
            tbl[a]["points"] += 3
        else:
            tbl[h]["points"] += 1
            tbl[a]["points"] += 1
    for t in teams:
        tbl[t]["gd"] = tbl[t]["gf"] - tbl[t]["ga"]
    return tbl


def _h2h(tied, results):
    """Head-to-head mini-table among the ``tied`` teams, recomputed FROM THIS
    CALL's ``results`` (only the fixtures between tied teams). Never precomputed
    or shared -- each sim has its own scorelines."""
    sub = {(h, a): s for (h, a), s in results.items() if h in tied and a in tied}
    return group_table(list(tied), sub)


def rank_group(teams, results, *, rng, _return_random_used=False):
    """Rank ``teams`` 1st..4th by FIFA 2026 order: points -> GD -> GF -> head-to-head
    mini-table -> seeded random draw. ``rng`` is the caller-seeded numpy Generator;
    it is consulted ONLY to break a total tie (teams level on every criterion incl.
    head-to-head). Pass ``_return_random_used=True`` to also get a bool flag recording
    whether the random tail fired (for downstream logging)."""
    tbl = group_table(teams, results)
    random_used = False

    def key_overall(t):
        return (tbl[t]["points"], tbl[t]["gd"], tbl[t]["gf"])

    order = sorted(teams, key=key_overall, reverse=True)
    final, i = [], 0
    while i < len(order):
        j = i
        while j < len(order) and key_overall(order[j]) == key_overall(order[i]):
            j += 1
        cluster = order[i:j]
        if len(cluster) == 1:
            final.append(cluster[0])
        else:
            h2h = _h2h(cluster, results)

            def key_h2h(t):
                return (h2h[t]["points"], h2h[t]["gd"], h2h[t]["gf"])

            sub = sorted(cluster, key=key_h2h, reverse=True)
            k = 0
            while k < len(sub):
                l = k
                while l < len(sub) and key_h2h(sub[l]) == key_h2h(sub[k]):
                    l += 1
                if l - k > 1:
                    random_used = True
                    tie = sub[k:l]
                    perm = rng.permutation(len(tie))
                    sub[k:l] = [tie[p] for p in perm]
                k = l
            final.extend(sub)
        i = j
    return (final, random_used) if _return_random_used else final
