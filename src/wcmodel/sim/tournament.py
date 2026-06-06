"""Full-posterior Monte-Carlo tournament loop + progression aggregation (Phase-3 T5).

INTEGRATES Tasks 0-4: it draws ONE posterior sample per simulation, plays the group
stage (``sample_score`` at that draw's rates), ranks each group + the best-8 thirds
(FIFA 2026 tiebreakers), resolves the R32 feeder graph, and propagates knockout
winners (``resolve_tie``) through to the Final — recording, per team, the furthest
stage reached and a win-group flag. Counts/N over ``n_sims`` give the progression
probabilities; ``se = sqrt(p*(1-p)/N)`` is the per-market binomial Monte-Carlo SE.

THREE focal correctness properties (each load-bearing; cross-model adversarial review):

1. ONE posterior draw per sim, FIXED across every fixture. ``simulate_one`` is called
   with a single integer ``draw`` and passes that SAME ``draw`` to ``RateBook.rates``
   for every group fixture and every knockout phase. Drawing a fresh posterior sample
   per fixture would decorrelate the shared att/def/mu/home_adv across a sim's matches
   (a team would be strong in one match, weak in the next) — that is WRONG and would
   understate joint tail events. Cross-fixture correlation is preserved EXACTLY because
   the rates all read the same draw ``s`` (see ``_FixtureSampler`` and the single
   ``rng.integers(n_draws)`` per sim in ``simulate_tournament``).

2. The (c) provisional widening is NEVER applied in-sim. Uncertainty enters ONCE: via
   the posterior draw (RateBook) + the raw DC/BP scoreline sampling (``sample_score``).
   We deliberately do NOT call ``Posterior.predict_scoreline`` (which averages draws AND
   may inflate a provisional grid) — that would double-count uncertainty and destroy the
   per-sim shared-parameter correlation. ``RateBook`` exposes the RAW per-draw rates.

3. Seeded / fully reproducible. ``SeedSequence(seed).spawn(n_sims)`` gives each sim an
   independent, seed-derived child stream; per-sim ``rng = default_rng(child)``. No
   global/default RNG anywhere. Same ``seed`` -> bit-identical ``progression``.

The ``reach_X`` markets are CUMULATIVE by depth-from-final (Final = depth 0, SF = 1,
QF = 2, R16 = 3, anything deeper -> group-stage-exit boundary), so for ANY bracket
``champion <= reach_final <= reach_sf <= reach_qf <= reach_r16 <= advance`` holds BY
CONSTRUCTION (a team that reaches a later round trivially satisfies every earlier depth
threshold). Depths are read off the WINNER feeder DAG rooted at the Final, so the
loser-fed 3rd-place consolation match is correctly OFF the championship ladder.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from wcmodel.sim.groups import group_table, rank_group
from wcmodel.sim.knockout import resolve_tie
from wcmodel.sim.scoreline import RateBook, sample_score
from wcmodel.sim.thirds import assign_thirds_to_slots, rank_thirds

# Feeder-token grammar (mirrors bracket.py / config/tournament_2026.yaml):
#   "1A"/"2B"  -> group-position slot: digit (1=winner, 2=runner-up) + group letter
#   "3rd-ABCDF"-> best-third slot: the third assigned to this match (Annex C lookup)
#   "W74"      -> winner of match 74 ; "L101" -> loser of match 101 (3rd-place feeders)
_GROUP_SLOT = re.compile(r"^([12])([A-L])$")
_THIRD_SLOT = re.compile(r"^3rd-[A-L]+$")
_WL_REF = re.compile(r"^([WL])(\d+)$")

# Depth-from-final -> ladder semantic. Smaller depth = further in the tournament.
_DEPTH_FINAL = 0
_DEPTH_SF = 1
_DEPTH_QF = 2
_DEPTH_R16 = 3
# Sentinel for a team eliminated in the group stage (never entered any KO match):
# larger than any real KO depth so every reach_X threshold test is False for it.
_GROUP_EXIT = 1 << 30

# The market ladder, as (column -> depth threshold). A team scores 1 in column C iff its
# MIN participated KO depth <= threshold[C]. `advance_from_group` uses the bracket's
# deepest KO depth (set per-run), so it means "entered the knockouts at all". `win_group`
# and `champion` are handled separately (group placing / Final winner).
#
# MARKET NAMING (Phase-3 T7). The depth-from-final reach ladder is keyed internally by the
# advance-threshold name `advance_from_group` (the plan's resolved headline market; the old
# `advance` is renamed, NOT aliased — the public table exposes exactly `advance_from_group`).
_ADVANCE = "advance_from_group"
_REACH_LADDER = [
    ("reach_r16", _DEPTH_R16),
    ("reach_qf", _DEPTH_QF),
    ("reach_sf", _DEPTH_SF),
    ("reach_final", _DEPTH_FINAL),
]
# Per-group placing markets: a team's 0-based group finish bucketed to first/second/third/
# out (placing 0/1/2/>=3). They PARTITION every group team (first+second+third+out == 1 per
# team, since every sim places every group team exactly once). `win_group` IS `first` (both
# are placing==0) — emitted as IDENTICAL columns (computed once, copied), never two
# inconsistent counts. `out` is "did not finish top-3 in the group".
_GROUP_PLACE = ["first", "second", "third", "out"]
# Public column/market set, in emission order. The SIX resolved headline markets are
# `champion, reach_final, reach_sf, reach_qf, advance_from_group, win_group`; they are all
# present below alongside `reach_r16` (the deepest reach rung kept for the full ladder) and
# the four per-group placing markets. Coherence chain
# `champion <= reach_final <= reach_sf <= reach_qf <= advance_from_group` holds by
# construction (each reach column is a monotone threshold on the same MIN depth), and
# `win_group <= advance_from_group` because a group winner (placing 0) always advances.
_COLUMNS = (["win_group", _ADVANCE, "reach_r16", "reach_qf", "reach_sf", "reach_final",
             "champion"] + _GROUP_PLACE)


@dataclass(frozen=True)
class SimResult:
    """Aggregated MC output. ``progression``/``se`` are team-indexed DataFrames over the
    SAME market columns (``_COLUMNS``), one tidy team-indexed table each:

      * SIX headline markets — ``champion, reach_final, reach_sf, reach_qf,
        advance_from_group, win_group`` — plus ``reach_r16`` (the deepest reach rung,
        kept for the full ladder);
      * FOUR per-group placing markets — ``first, second, third, out`` — a partition of
        every team's group finish (``first+second+third+out == 1`` per team). ``win_group``
        and ``first`` are the SAME quantity (group placing == 0), emitted as identical
        columns.

    ``progression`` holds the probability in [0,1]; ``se`` the binomial Monte-Carlo SE
    ``sqrt(p(1-p)/N)`` for the same cell. ``random_tail_rate`` is the fraction of sims in
    which a group ranking's seeded random tail fired (a diagnostic, not a probability);
    ``n_sims`` is the sample size behind every probability + SE."""

    progression: pd.DataFrame      # index=team, cols=markets -> probability in [0,1]
    se: pd.DataFrame               # index=team, cols=markets -> binomial MC SE
    random_tail_rate: float        # fraction of sims where a rank_group random tail fired
    n_sims: int


@dataclass(frozen=True)
class _Cfg:
    """Sim knobs threaded through one run (all passed explicitly to ``simulate_one``)."""
    max_goals: int
    et_scale: float
    pen_home_prob: float
    neutral: bool = True   # WC-2026 group/KO matches are modelled on neutral ground


class _FixtureSampler:
    """Per-sim closure: every call reads the SAME posterior draw ``s`` from the shared
    ``RateBook``. This is the mechanical guarantee of focal property #1 — one draw, fixed
    across all fixtures in the sim. ``knockout_sampler`` returns the ``sample(phase, rng)``
    callable ``resolve_tie`` consumes: regulation rates, or rates*et_scale for extra time
    (the et_scale arithmetic lives HERE, per the knockout.py caller-applies contract)."""

    def __init__(self, ratebook: RateBook, draw: int, cfg: _Cfg):
        self._rb = ratebook
        self._draw = draw
        self._cfg = cfg

    def score(self, home, away, *, neutral, rng):
        # RAW per-draw rates (NO predict_scoreline averaging, NO (c) widening) at the one
        # fixed draw -> raw DC/BP pmf sample. Focal properties #1 and #2.
        lh, la = self._rb.rates(home, away, neutral, draw=self._draw)
        return self._sample_at(lh, la, rng)

    def knockout_sampler(self, home, away, *, neutral):
        lh, la = self._rb.rates(home, away, neutral, draw=self._draw)

        def sample(phase, rng):
            # ET = 30/90 of a regulation match -> scale ALL Poisson goal rates by et_scale.
            # _sample_at applies the scale uniformly (lh, la, AND the BP shared l3); the DC
            # rho is a low-score DEPENDENCE parameter, not a rate, so it is NOT scaled.
            scale = self._cfg.et_scale if phase == "extra_time" else 1.0
            return self._sample_at(lh, la, rng, rate_scale=scale)

        return sample

    def _sample_at(self, lh, la, rng, *, rate_scale=1.0):
        rb, s = self._rb, self._draw
        lh, la = lh * rate_scale, la * rate_scale
        if rb.likelihood == "dixon_coles":
            # rho: dependence parameter (tau correction on low-score cells), NOT a goal
            # rate -> unscaled by rate_scale.
            return sample_score(lh, la, rng=rng, likelihood=rb.likelihood,
                                rho=float(rb.rho[s]), max_goals=self._cfg.max_goals)
        # bivariate_poisson: l3 is the SHARED Poisson goal-rate (W3 ~ Pois(l3)); it scales
        # with lh/la so extra time is consistently 30/90 of a regulation match.
        return sample_score(lh, la, rng=rng, likelihood=rb.likelihood,
                            l3=float(rb.l3[s]) * rate_scale, max_goals=self._cfg.max_goals)


def _match_depths(bracket) -> dict:
    """Depth-from-final for every knockout match, read off the WINNER feeder DAG rooted at
    the Final (round == 'Final', depth 0). A match feeding match ``m`` (via ``W{m}``) sits
    one hop deeper. Matches NOT on the winner-DAG (the loser-fed 3rd-place consolation) get
    no depth -> excluded from the championship ladder. Pure structure (computed once per
    run from the immutable bracket); no RNG, no draw."""
    finals = [m for m, r in bracket.match_round.items() if r == "Final"]
    if len(finals) != 1:
        raise ValueError(f"bracket must have exactly one Final, found matches {finals}")
    final_no = finals[0]

    # consumer[p] = the match that consumes W{p} (p's winner advances INTO it).
    consumer = {}
    for m, (home_ref, away_ref) in bracket.knockout_feeders.items():
        for ref in (home_ref, away_ref):
            mt = _WL_REF.match(ref)
            if mt and mt.group(1) == "W":
                consumer[int(mt.group(2))] = m

    depth = {final_no: _DEPTH_FINAL}

    def _depth_of(m):
        if m in depth:
            return depth[m]
        if m not in consumer:
            return None                      # off the winner-DAG (e.g. the 3rd-place match)
        parent = _depth_of(consumer[m])
        if parent is None:
            return None
        depth[m] = parent + 1
        return depth[m]

    for m in bracket.knockout_feeders:
        _depth_of(m)
    return depth


def _resolve_feeder(ref, *, group_rankings, third_by_match, winners, losers, match_no):
    """Resolve one feeder token to a concrete team for ``match_no``.

    ``group_rankings``: {group_letter: [1st, 2nd, 3rd, 4th]} (this sim's rank_group output).
    ``third_by_match``: {match_no: group_letter} from assign_thirds_to_slots (or {} when the
    bracket has no best-third slots, e.g. tiny_bracket). ``winners``/``losers``: filled in
    match-number (topological) order as knockouts resolve."""
    mt = _GROUP_SLOT.match(ref)
    if mt:                                               # "1A"/"2B": placing 0 or 1
        return group_rankings[mt.group(2)][int(mt.group(1)) - 1]
    if _THIRD_SLOT.match(ref):                           # "3rd-ABCDF": Annex-C-assigned third
        return group_rankings[third_by_match[match_no]][2]
    mt = _WL_REF.match(ref)
    if mt:                                               # "W74"/"L101"
        src = int(mt.group(2))
        return (winners if mt.group(1) == "W" else losers)[src]
    raise ValueError(f"unrecognised feeder token {ref!r} for match {match_no}")


def simulate_one(bracket, ratebook, draw, rng, cfg, played=None, *, depths=None):
    """Simulate ONE tournament at a single fixed posterior ``draw``.

    Returns ``{"depth": {team: furthest_depth}, "groups": {team: placing}, "champion":
    team, "random_tail": bool}`` — ``furthest_depth`` is the team's MIN participated KO
    depth (smaller = further; ``_GROUP_EXIT`` if it never advanced), ``placing`` its 0-based
    group finish. Every fixture in this call uses the SAME ``draw`` (focal property #1) and
    the RAW per-draw rates (focal property #2).

    PER-CUTOFF CONDITIONING (Task 6). ``played`` pins the fixtures already DECIDED as of a
    cutoff, so they are NOT sampled (the as-of-cutoff state is FACT, not a draw). The match
    key everywhere is the EXACT ``(home_team, away_team, date)`` triple (the leakage-critical
    matching rule built in ``wcmodel.sim.run.simulate`` from ``date < cutoff`` played rows):

      * ``played["groups"]``  : ``{(home, away): (home_goals, away_goals)}`` — group teams
        are concrete in the bracket, so ``simulate`` resolves these by the exact triple and
        keys them by the (home, away) pair here. A group fixture present here uses its
        ACTUAL score instead of ``sample_score``.
      * ``played["knockout_results"]`` : ``{(home, away, date): (home_goals, away_goals)}``
        + ``played["match_dates"]`` : ``{match_no: date}``. Knockout feeders are PLACEHOLDERS
        in the bracket (``1A``/``W74``), so a played KO result can only be matched to a match
        once its feeders resolve to CONCRETE teams — which happens HERE, in-loop. After
        resolving match ``m``'s concrete ``home``/``away`` we look up
        ``(home, away, match_dates[m])``; if present the match is decided -> use the ACTUAL
        winner from that score, do NOT ``resolve_tie``. (KO fixture dates are not unique
        across matches, so date alone can't identify a match; the concrete team pair + date
        does. This is why KO matching is in-loop, not pre-resolved in ``simulate``.)

    ``simulate`` builds these from results KNOWN at the cutoff (``date < cutoff``, played).
    ``played=None`` (the T5 default) simulates every fixture. Determinism: fixing consumes
    NO RNG (no ``sample_score`` / ``resolve_tie`` call for a pinned fixture), so two runs that
    pin the IDENTICAL fixture set consume the per-sim RNG identically -> bit-identical
    progression (the leakage canary's invariance). A fixed knockout still records both
    participants' depths exactly as a sampled one would, so the reach ladder is unaffected by
    whether a match was pinned or sampled.

    ``depths`` is the pre-computed ``_match_depths(bracket)`` (pure structure). It is passed
    in so ``simulate_tournament`` computes it ONCE per run rather than per sim; if omitted
    (direct call) it is computed here. Behaviour is identical either way."""
    played = played or {}
    played_groups = played.get("groups", {})             # {(home, away): (hg, ag)}
    played_ko_results = played.get("knockout_results", {})  # {(home, away, date): (hg, ag)}
    ko_match_dates = played.get("match_dates", {})          # {match_no: date}
    # D3 (Phase-5 L3): the ACTUAL shootout winner for a level pinned KO, keyed by the
    # SAME (home, away, date) triple. Supplied by sim.run._build_played from the
    # results `winner_override` column (martj42 shootouts.csv). Empty -> a level KO
    # with no recorded winner still fails loud below (the guard is preserved).
    played_ko_winners = played.get("knockout_winners", {})  # {(home, away, date): winner}

    sampler = _FixtureSampler(ratebook, draw, cfg)
    random_tail = False

    # --- Group stage: play each group's fixtures, rank (FIFA 2026 tiebreakers), and
    # capture the 3rd-placer's (points, gd, gf) from the SAME scorelines (no re-sampling). ---
    group_rankings = {}            # {group: [1st, 2nd, 3rd, 4th]}
    thirds_stats = {}              # {group: {points, gd, gf}} for the 3rd-placer
    placing = {}                   # {team: 0-based group finish}
    # CANONICAL group iteration (Codex T7 stale-serve guard): walk groups in sorted-key
    # order, NOT dict-insertion order. This loop consumes the per-sim RNG (scoreline
    # sampling below + rank_group's seeded tail), so its order determines the seeded
    # result. cache.py::_bracket_hash canonicalizes the bracket by SORTING the group keys
    # (the key is independent of group insertion order), so the sim MUST consume RNG in
    # that same content-determined order — else two content-identical brackets with
    # different group insertion order would share a cache key yet produce different seeded
    # results (a stale serve). sorted() makes SimResult a pure function of bracket CONTENT.
    # (Within-group fixture order is left as-is: it IS content and _bracket_hash preserves
    # it, so a reorder there is a distinct key — see test_simresult_invariant_to_*.)
    for g in sorted(bracket.group_fixtures):
        fixtures = bracket.group_fixtures[g]
        teams = bracket.groups[g]
        # A fixture decided as-of-cutoff (in played_groups) uses its ACTUAL score and is
        # NOT sampled (consumes no RNG); every other fixture is sampled at this draw.
        results = {
            (home, away): (played_groups[(home, away)] if (home, away) in played_groups
                           else sampler.score(home, away, neutral=cfg.neutral, rng=rng))
            for home, away in fixtures
        }
        ranking, used = rank_group(teams, results, rng=rng, _return_random_used=True)
        random_tail = random_tail or used
        group_rankings[g] = ranking
        for pos, team in enumerate(ranking):
            placing[team] = pos
        if bracket.third_place_slots:    # only needed when the bracket has best-third slots
            tbl = group_table(teams, results)
            third = ranking[2]
            thirds_stats[g] = {k: tbl[third][k] for k in ("points", "gd", "gf")}

    # --- Best-8 thirds + R32 slot assignment (skipped entirely when the bracket has no
    # third slots, e.g. tiny_bracket -> no FIFA Annex-C lookup, no RNG touched there). ---
    third_by_match = {}
    if bracket.third_place_slots:
        third_by_match = assign_thirds_to_slots(rank_thirds(thirds_stats, rng=rng))

    # --- Knockouts: resolve every match in match-number (topological) order. Winner-fed
    # matches propagate champions toward the Final; the loser-fed 3rd-place match is
    # resolved for full-sim fidelity but is off the championship depth ladder (no depth). ---
    # `depths` is pure structure (the winner-feeder DAG); computed ONCE per run by
    # simulate_tournament and passed in, else (direct call) computed here.
    if depths is None:
        depths = _match_depths(bracket)
    winners, losers = {}, {}
    furthest = {}                  # {team: MIN participated KO depth}
    champion = None
    for m in sorted(bracket.knockout_feeders):
        home_ref, away_ref = bracket.knockout_feeders[m]
        home = _resolve_feeder(home_ref, group_rankings=group_rankings,
                               third_by_match=third_by_match, winners=winners,
                               losers=losers, match_no=m)
        away = _resolve_feeder(away_ref, group_rankings=group_rankings,
                               third_by_match=third_by_match, winners=winners,
                               losers=losers, match_no=m)
        # Decided as-of-cutoff? Match the now-CONCRETE (home, away) + this match's date
        # against the played KO results (exact triple). A knockout that finishes LEVEL
        # after regulation+ET is decided by a penalty shootout, but the martj42 results
        # adapter stores only the regulation/ET score and DROPS the shootout winner
        # (shootouts live in a separate file it does not ingest). So a level played KO
        # score is VALID data we cannot yet pin to its actual winner — not malformed
        # input — and we fail loud rather than guess/randomize a KNOWN outcome.
        ko_score = played_ko_results.get((home, away, ko_match_dates.get(m)))
        if ko_score is not None:
            hg, ag = ko_score
            if hg == ag:
                # D3 (Phase-5 L3): a level (penalty-decided) KO resolves to the ACTUAL
                # recorded shootout winner if we have it (martj42 shootouts.csv ->
                # winner_override -> knockout_winners). No RNG is drawn — the winner is
                # FACT, not a coin-flip. The guard is PRESERVED: a level KO with NO
                # recorded winner (genuinely-missing data) still fails loud.
                ko_winner = played_ko_winners.get((home, away, ko_match_dates.get(m)))
                if ko_winner is None:
                    raise ValueError(
                        f"pinned knockout fixture {home!r} vs {away!r} (match {m}) has a "
                        f"level score {hg}-{ag} — it was decided by a penalty shootout, "
                        f"but no shootout winner is recorded for it, so the actual winner "
                        f"cannot be pinned; conditioning on a penalty-decided knockout "
                        f"with no recorded winner is unsupported (resolution: ingest the "
                        f"shootout winner via results.winner_override)"
                    )
                if ko_winner not in (home, away):
                    raise ValueError(
                        f"recorded shootout winner {ko_winner!r} for match {m} is neither "
                        f"participant ({home!r}/{away!r}) — the winner_override is corrupt"
                    )
                w = ko_winner                            # ACTUAL recorded winner, no RNG
            else:
                w = home if hg > ag else away            # ACTUAL winner, no RNG drawn
        else:
            sample = sampler.knockout_sampler(home, away, neutral=cfg.neutral)
            w = resolve_tie(home, away, sample=sample, rng=rng, et_scale=cfg.et_scale,
                            pen_home_prob=cfg.pen_home_prob)
        winners[m] = w
        losers[m] = away if w == home else home

        d = depths.get(m)
        if d is not None:                    # on the championship DAG: record participation
            for team in (home, away):
                furthest[team] = min(furthest.get(team, _GROUP_EXIT), d)
            if d == _DEPTH_FINAL:
                champion = w

    return {"depth": furthest, "groups": placing, "champion": champion,
            "random_tail": random_tail}


def simulate_tournament(posterior, *, bracket, n_sims, seed, max_goals, et_scale,
                        pen_home_prob, played=None):
    """Run ``n_sims`` full-posterior MC tournaments over ``bracket`` -> ``SimResult``.

    Focal property #3 (seeded determinism): ``SeedSequence(seed).spawn(n_sims)`` derives
    one independent child stream per sim; ``rng = default_rng(child)`` is the ONLY RNG used
    inside a sim. No global/default RNG anywhere -> same ``seed`` gives a bit-identical
    ``progression``. ``simulate_one`` walks groups in CANONICAL ``sorted(group_fixtures)``
    order, so the per-sim RNG-consumption order — and hence the seeded ``SimResult`` — is a
    pure function of bracket CONTENT, INDEPENDENT of the ``groups`` dict insertion order.
    That makes the (insertion-order-independent) ``cache.py::_bracket_hash`` a SOUND cache
    key: two content-identical brackets ordered differently share a key AND produce the same
    result (Codex T7 stale-serve guard; ``test_simresult_invariant_to_group_insertion_order``).
    Focal property #1 (one draw per sim): ``s = rng.integers(n_draws)`` is drawn ONCE per sim
    and that SAME ``s`` is threaded to every fixture (group + knockout) via
    ``simulate_one(..., draw=s, ...)``.

    ``played`` (the Task-6 per-cutoff conditioning map: ``{"groups": {(h,a): (hg,ag)},
    "knockout_results": {(h,a,date): (hg,ag)}, "match_dates": {match_no: date}}``) is
    forwarded to ``simulate_one``, which pins those fixtures to their actual results instead
    of sampling them; ``played=None`` simulates every fixture. The same ``played`` set is
    pinned in every sim, so fixing consumes no RNG and a leakage-free run is bit-identical
    across runs that pin the identical set."""
    ratebook = RateBook(posterior)
    cfg = _Cfg(max_goals=max_goals, et_scale=et_scale, pen_home_prob=pen_home_prob)
    teams = list(posterior.teams)
    team_idx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)

    # Per-market integer counts (teams x markets), summed over sims; champion-summing to N
    # is guaranteed because each sim records exactly one Final winner.
    counts = {col: np.zeros(n_teams, dtype=np.int64) for col in _COLUMNS}
    random_tail_hits = 0

    # `_match_depths` is pure structure (the winner-feeder DAG) -> compute ONCE here and
    # reuse for the advance threshold AND every sim (passed into simulate_one), rather than
    # recomputing it inside the per-sim body (wasted work at N=20k; T5 quality review).
    depths = _match_depths(bracket)
    depths_on_dag = set(depths.values())                   # finite KO depths present
    # `advance_from_group` threshold = the bracket's deepest KO depth (entered the
    # knockouts at all).
    advance_depth = max(depths_on_dag) if depths_on_dag else _GROUP_EXIT

    children = np.random.SeedSequence(seed).spawn(n_sims)  # one seed-derived stream per sim
    for child in children:
        rng = np.random.default_rng(child)                 # the ONLY RNG inside the sim
        s = int(rng.integers(ratebook.n_draws))            # ONE posterior draw, fixed for the sim
        out = simulate_one(bracket, ratebook, draw=s, rng=rng, cfg=cfg, played=played,
                           depths=depths)
        random_tail_hits += int(out["random_tail"])

        # Per-group placing markets: bucket the 0-based group finish to first/second/third/
        # out (0/1/2/>=3). `win_group` is filled from the SAME placing==0 event as `first`
        # so the two are identical by construction (reconciled into one column after the
        # loop). Every group team is placed in exactly one bucket each sim.
        for team, placing in out["groups"].items():
            i = team_idx[team]
            if placing == 0:
                counts["first"][i] += 1
            elif placing == 1:
                counts["second"][i] += 1
            elif placing == 2:
                counts["third"][i] += 1
            else:
                counts["out"][i] += 1
        # Reach ladder (cumulative depth thresholds) + advance_from_group, from each team's
        # MIN participated KO depth.
        for team, d in out["depth"].items():
            i = team_idx[team]
            if d <= advance_depth:
                counts[_ADVANCE][i] += 1
            for col, thr in _REACH_LADDER:
                if d <= thr:
                    counts[col][i] += 1
        champ = out["champion"]
        if champ is not None:
            counts["champion"][team_idx[champ]] += 1

    # `win_group` IS the per-group `first` market (both are group placing == 0). Copy the
    # single counted array so the two columns are IDENTICAL by construction (design note 1:
    # never two inconsistent computations); `[:]` writes into the pre-allocated array.
    counts["win_group"][:] = counts["first"]

    n = float(n_sims)
    prob = pd.DataFrame({col: counts[col] / n for col in _COLUMNS}, index=teams)
    prob.index.name = "team"
    # Binomial Monte-Carlo standard error per market: sqrt(p*(1-p)/N).
    se = pd.DataFrame(
        {col: np.sqrt(prob[col].to_numpy() * (1.0 - prob[col].to_numpy()) / n)
         for col in _COLUMNS},
        index=teams,
    )
    se.index.name = "team"
    return SimResult(progression=prob[_COLUMNS], se=se[_COLUMNS],
                     random_tail_rate=random_tail_hits / n, n_sims=n_sims)
