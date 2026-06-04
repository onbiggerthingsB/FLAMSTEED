"""Group standings + FIFA 2026 tiebreakers.

Correct FIFA 2026 precedence (source: FIFA 2026 World Cup regulations, as summarized
in Wikipedia "2026 FIFA World Cup" -> "Tie-breaking criteria for group stage ranking",
ref [161]). Teams are ranked first by total POINTS in all group matches. Teams level on
points are separated, IN ORDER:
  (a) head-to-head points     -- in the matches played BETWEEN the tied teams only;
  (b) head-to-head goal difference -- among those same matches;
  (c) head-to-head goals scored    -- among those same matches;
  REAPPLY (a)-(c) to any teams STILL level after a-c, recomputed on the smaller
      subset's mutual matches (a 3-way tie can collapse to a 2-way one whose single
      mutual match then separates them). If still undecided:
  (d) all-group goal difference;
  (e) all-group goals scored;
  (f) fair-play conduct score (card deductions);
  (g) better position in the most recent FIFA Men's World Ranking;
  (h) better in progressively older FIFA Rankings.

Criteria (f) and (g)-(h) are NOT modelled here: we do not simulate cards (f), and the
FIFA-Ranking tiebreak (g)-(h) is a deterministic criterion that would require
point-in-time, leakage-safe ranking data (deferred). For the rare tail where teams
remain level through (e), we substitute a SEEDED random draw (the caller-seeded
``rng``) and flag it via ``random_used``. Replacing the (g)-(h) stand-in with exact
point-in-time FIFA-Ranking lookups is a possible future enhancement.

All head-to-head tables are recomputed per call from the passed ``results`` -- nothing
is precomputed or shared, so each simulated set of scorelines gets its own mini-tables."""
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


def _split_runs(seq, key):
    """Yield maximal runs of consecutive ``seq`` entries that share ``key`` value.
    ``seq`` must already be sorted by ``key``. Each yielded run is a list."""
    i = 0
    while i < len(seq):
        j = i
        while j < len(seq) and key(seq[j]) == key(seq[i]):
            j += 1
        yield seq[i:j]
        i = j


def rank_group(teams, results, *, rng, _return_random_used=False):
    """Rank ``teams`` 1st..4th by the FIFA 2026 group tiebreaker order (see the module
    docstring for the full, source-cited criteria a-h).

    Precedence applied here:
      1. cluster by total POINTS;
      2. within a points-tied cluster, rank by head-to-head (a) points -> (b) GD ->
         (c) GF, recomputed from THIS call's mutual matches; any sub-cluster still
         level on (a)-(c) is REFINED by reapplying (a)-(c) to just that sub-cluster's
         own mutual matches (recursive -- the smaller subset can separate them);
      3. any sub-cluster still level after head-to-head is ranked by all-group
         (d) GD -> (e) GF;
      4. any sub-cluster still level after (e) is ordered by a SEEDED random draw,
         standing in for the criteria we do not model -- (f) fair-play conduct (we do
         not simulate cards) and (g)-(h) FIFA World Ranking (would need point-in-time,
         leakage-safe ranking data; deferred).

    ``rng`` is the caller-seeded numpy Generator; it is consulted ONLY for step 4 (a
    total tie through criterion (e)). Pass ``_return_random_used=True`` to also get a
    bool flag recording whether the random tail fired (for downstream logging)."""
    tbl = group_table(teams, results)
    random_used = False

    def _order_within_points_cluster(cluster):
        """Order a points-tied ``cluster`` by head-to-head (a-c, recursively reapplied)
        -> all-group GD/GF (d-e) -> seeded random tail (f/g-h stand-in). Mutates the
        enclosing ``random_used`` when the random tail fires."""
        nonlocal random_used
        if len(cluster) == 1:
            return list(cluster)

        # (a)-(c): head-to-head mini-table over the cluster's own mutual matches.
        h2h = _h2h(cluster, results)

        def key_h2h(t):
            return (h2h[t]["points"], h2h[t]["gd"], h2h[t]["gf"])

        ordered = sorted(cluster, key=key_h2h, reverse=True)
        out = []
        for run in _split_runs(ordered, key_h2h):
            if len(run) == 1:
                out.append(run[0])
            elif len(run) < len(cluster):
                # Genuine sub-cluster (smaller than what we started with): REAPPLY
                # a-c on this subset's own mutual matches -- the recursive refinement.
                out.extend(_order_within_points_cluster(run))
            else:
                # No progress from a-c (run is the whole cluster -> reapplying would
                # recurse forever). Fall through to all-group GD/GF, then random.
                out.extend(_break_by_all_group_then_random(run))
        return out

    def _break_by_all_group_then_random(group):
        """(d) all-group GD -> (e) all-group GF -> (f/g-h) seeded random stand-in."""
        nonlocal random_used

        def key_all_group(t):
            return (tbl[t]["gd"], tbl[t]["gf"])

        ordered = sorted(group, key=key_all_group, reverse=True)
        out = []
        for run in _split_runs(ordered, key_all_group):
            if len(run) == 1:
                out.append(run[0])
            else:
                # Level through (e): seeded random draw stands in for (f) fair-play
                # and (g)-(h) FIFA World Ranking, which we do not model.
                random_used = True
                perm = rng.permutation(len(run))
                out.extend(run[p] for p in perm)
        return out

    def key_points(t):
        return tbl[t]["points"]

    order = sorted(teams, key=key_points, reverse=True)
    final = []
    for cluster in _split_runs(order, key_points):
        final.extend(_order_within_points_cluster(cluster))
    return (final, random_used) if _return_random_used else final
