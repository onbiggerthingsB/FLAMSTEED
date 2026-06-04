"""Per-cutoff Monte-Carlo entry point (Phase-3 Task 6) — THE tournament-layer
leakage gate.

``simulate(cutoff, posterior, store, config)`` runs the WC-2026 simulation
CONDITIONED on the results KNOWN at ``cutoff``: it FIXES every fixture already
decided (group fixtures to their actual score, decided knockouts to their actual
winner) and simulates only the unplayed remainder via ``simulate_tournament``.
Eliminated teams (lost a known knockout, or can't-advance out of a finished group)
get 0 forward probability BY CONSTRUCTION — their fixed results flow through the
group ranking / knockout propagation exactly as a sampled result would.

LEAKAGE DISCIPLINE (binding project rule; cross-model adversarial review). The
conditioning reads ONLY results knowable at the cutoff. The played set is the
``store.read("results", cutoff)`` rows filtered to *valid played matches with*
``date < cutoff`` — the EXACT strict, day-floored, tz-coerced filter
``wcmodel.data.features.build`` uses (mirrored line-for-line in ``_played_as_of``
below; see that function's comment for the leakage-critical line). A result dated
on/after the cutoff is therefore NEVER fixed, so it cannot touch the as-of-cutoff
progression — the invariance the leakage canary (``tests/sim/test_leakage_sim.py``)
asserts. Because the sim is seeded and fixing consumes no RNG, a leakage-free run
is bit-identical across a mutation of any post-cutoff result.

FIXTURE <-> RESULT MATCHING (leakage-critical rule). A bracket fixture is matched to
a played result by the EXACT ``(home_team, away_team, date)`` triple. The bracket
DROPS fixture dates (``Bracket.group_fixtures`` is just ``{group: [(home,away),...]}``),
so ``simulate`` keeps a fixture->date map read from the tournament dict itself. Group
fixtures carry concrete teams, so they are matched here and keyed by ``(home, away)``.
Knockout fixtures carry PLACEHOLDER feeders (``1A``/``W74``), so a played KO result can
only be matched once feeders resolve to concrete teams INSIDE the sim — ``simulate``
passes the raw KO results (keyed by the concrete triple) + the ``{match_no: date}`` map
to ``simulate_one``, which does the in-loop concrete-team match (see ``simulate_one``).
For an ingested WC-2026 result the fixture's date is exact, so the triple is unique; the
exact-date match also disambiguates the multiple historical friendlies a team-pair has.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from wcmodel.config import load_config
from wcmodel.data.features import valid_played_results
from wcmodel.data.tournament import load_tournament
from wcmodel.sim.bracket import build_bracket
from wcmodel.sim.tournament import simulate_tournament


@dataclass(frozen=True)
class SimConfig:
    """Knobs for one per-cutoff simulation run.

    ``tournament`` is either a parsed tournament dict OR a path to a draw YAML
    (default: the verified ``config/tournament_2026.yaml`` via ``load_tournament``).
    ``n_sims`` / ``seed`` / ``max_goals`` / ``et_scale`` / ``pen_home_prob`` are the
    MC params; the production values come from the project ``config/config.yaml``
    ``sim:`` section — use :meth:`from_config` to load them."""

    # SOURCE OF TRUTH: :meth:`from_config` (the ``config.yaml`` ``sim:`` section) is the
    # production source for these knobs; the literal field defaults below are a fallback
    # for direct construction and MUST be kept in sync with that section.
    tournament: dict | str | Path | None = None
    n_sims: int = 20000
    seed: int = 0
    max_goals: int = 12
    et_scale: float = 0.3333
    pen_home_prob: float = 0.5

    @classmethod
    def from_config(cls, config: dict | None = None, *, tournament=None, seed=None,
                    n_sims=None) -> "SimConfig":
        """Build a SimConfig from the project config ``sim:`` section (production
        params). ``tournament`` defaults to ``config/tournament_2026.yaml``; ``seed``
        falls back to the global ``config["seed"]``."""
        cfg = config or load_config()
        sim = cfg["sim"]
        return cls(
            tournament=tournament,
            n_sims=n_sims if n_sims is not None else int(sim["n_sims"]),
            seed=cfg["seed"] if seed is None else seed,
            max_goals=int(sim["max_goals"]),
            et_scale=float(sim["extra_time_scale"]),
            pen_home_prob=float(sim["penalty_home_prob"]),
        )


def _load_tournament(spec, repo_root: Path) -> dict:
    """Resolve a SimConfig.tournament spec to a parsed, validated tournament dict.

    ``None`` -> the verified ``config/tournament_2026.yaml``; a dict -> used as-is; a
    path -> loaded + validated via ``load_tournament``. NOTE: only the YAML path runs
    ``validate_tournament`` — passing a tournament DICT BYPASSES validation (an
    intentional test escape hatch for minimal synthetic brackets)."""
    if spec is None:
        return load_tournament(repo_root / "config" / "tournament_2026.yaml")
    if isinstance(spec, (str, Path)):
        return load_tournament(spec)
    return spec


def _fixture_dates(tournament: dict) -> tuple[dict, dict]:
    """Read the fixture->date maps the bracket drops, straight from the tournament
    dict, so a fixture can be matched to a played result by its exact date.

    Returns ``(group_dates, ko_dates)``:
      * ``group_dates`` : ``{(home, away): pd.Timestamp}`` for group fixtures (concrete
        teams — the same ``match`` is None discriminator ``build_bracket`` uses);
      * ``ko_dates``    : ``{match_no: pd.Timestamp}`` for knockout fixtures (placeholder
        feeders; the concrete-team match happens in-sim, but the date is fixed here).
    Dates are normalized (day-floored) to match the played set's day-resolution keys."""
    group_dates, ko_dates = {}, {}
    for fx in tournament["fixtures"]:
        m = fx.get("match")
        if m is None:
            # A group fixture MUST carry a date — it is the only key for matching its
            # concrete teams to a played result (the validated draw always has one).
            # Guard symmetrically with the KO branch: a dateless group fixture cannot be
            # matched and the docstring promises a date, so fail loud naming the fixture.
            if fx.get("date") is None:
                raise ValueError(
                    f"group fixture {fx.get('home')!r} vs {fx.get('away')!r} has no "
                    f"date — a group fixture's date is its only key for matching a "
                    f"played result (the validated draw always carries one)"
                )
            group_dates[(fx["home"], fx["away"])] = pd.Timestamp(fx["date"]).normalize()
        elif fx.get("date") is not None:
            # KO date drives the in-loop KO-result match. A KO fixture with no date
            # (e.g. a minimal synthetic bracket) simply can't be matched to a played
            # result -> it is always simulated, which is correct (nothing to fix).
            ko_dates[m] = pd.Timestamp(fx["date"]).normalize()
    return group_dates, ko_dates


def _played_as_of(store, cutoff) -> pd.DataFrame:
    """Results KNOWN at ``cutoff`` — the leakage-safe played set the conditioning may
    use, filtered with the EXACT predicate ``wcmodel.data.features.build`` applies.

    Mirrors ``features.build`` line-for-line so the sim conditions on the IDENTICAL row
    set the model fit consumed (no cutoff-semantics drift between the two layers):

      1. ``store.read("results", cutoff)`` — the bitemporal as-of read;
      2. tz-coerce the cutoff to tz-naive UTC, then DAY-FLOOR it (a match on day D is
         not knowable until D+1, so a same-day match never leaks);
      3. tz-coerce the result dates symmetrically, then keep ``date < cutoff_day`` —
         THIS strict, day-floored filter is the leakage-critical line (== features.build
         line ``results.loc[results["date"] < cutoff_day]``);
      4. ``valid_played_results`` — drop unplayed/NaN/invalid-score rows (the single
         shared "valid played match" definition).

    A normalized ``date`` column (day-floored, tz-naive) is returned so callers match
    fixtures by the exact ``(home, away, date)`` triple against the same day-resolution.
    """
    cutoff = pd.Timestamp(cutoff)
    # tz-aware cutoff (e.g. an Odds API UTC `Z` timestamp) -> tz-naive UTC before
    # flooring (a tz-aware vs tz-naive comparison raises in pandas). Identical to
    # features.build's cutoff coercion; day-boundary semantics unchanged.
    if cutoff.tz is not None:
        cutoff = cutoff.tz_convert("UTC").tz_localize(None)
    cutoff_day = cutoff.normalize()

    results = store.read("results", cutoff=cutoff)
    results["date"] = pd.to_datetime(results["date"])
    # Symmetric tz-coercion of the result dates (features.build does the same): a
    # tz-aware source date would otherwise raise against the tz-naive cutoff_day.
    if getattr(results["date"].dt, "tz", None) is not None:
        results["date"] = results["date"].dt.tz_convert("UTC").dt.tz_localize(None)
    # LEAKAGE-CRITICAL: strict, day-floored cutoff filter (mirror of features.build).
    results = results.loc[results["date"] < cutoff_day].copy()
    # Valid played matches only (shared definition: finite/non-negative/integral, played).
    results = valid_played_results(results)
    # Day-floor the surviving dates so fixture-date matching is on the same resolution.
    results["date"] = results["date"].dt.normalize()
    return results


def _build_played(store, cutoff, group_dates: dict, ko_dates: dict) -> dict:
    """Assemble the per-cutoff conditioning map for ``simulate_one`` from the played
    set, matching fixtures by the EXACT ``(home, away, date)`` triple.

      * group fixtures (concrete teams) -> ``{"groups": {(home, away): (hg, ag)}}``,
        matched here against ``group_dates``;
      * every played result + its triple is also exposed as
        ``{"knockout_results": {(home, away, date): (hg, ag)}}`` (+ ``match_dates`` =
        ``ko_dates``) so ``simulate_one`` can match a KO result once its placeholder
        feeders resolve to concrete teams in-loop.

    Only fixtures whose exact ``(home, away, date)`` triple is in the played set are
    fixed; everything else is simulated. (A played row whose triple matches no bracket
    fixture — e.g. an unrelated friendly — simply never gets looked up, so it is inert.)
    """
    played = _played_as_of(store, cutoff)
    # Index played scores by the exact triple. Group fixtures are then matched by triple
    # and re-keyed to (home, away); knockouts keep the full triple for the in-loop match.
    by_triple = {
        (r.home_team, r.away_team, r.date): (int(r.home_score), int(r.away_score))
        for r in played.itertuples(index=False)
    }
    group_played = {
        (home, away): by_triple[(home, away, date)]
        for (home, away), date in group_dates.items()
        if (home, away, date) in by_triple
    }
    return {
        "groups": group_played,
        "knockout_results": by_triple,    # {(home, away, date): (hg, ag)}
        "match_dates": ko_dates,           # {match_no: date}
    }


def simulate(cutoff, posterior, store, config: SimConfig):
    """Run the per-cutoff conditioned WC-2026 simulation -> ``SimResult``.

    Builds the bracket from ``config.tournament``, reads the played-as-of-cutoff results
    (the leakage-safe ``date < cutoff`` set — see :func:`_played_as_of`), FIXES every
    fixture decided as of the cutoff (group fixtures by exact ``(home, away, date)``
    triple; decided knockouts in-loop once feeders are concrete), and simulates the
    unplayed remainder via :func:`wcmodel.sim.tournament.simulate_tournament`.

    Leakage-safe by construction: a result dated on/after ``cutoff`` is excluded by the
    strict cutoff filter, so it is never fixed and cannot change progression. Seeded +
    fixing-is-RNG-free -> bit-identical across a post-cutoff mutation (the canary)."""
    repo_root = Path(__file__).resolve().parents[3]
    tournament = _load_tournament(config.tournament, repo_root)
    bracket = build_bracket(tournament)
    group_dates, ko_dates = _fixture_dates(tournament)
    played = _build_played(store, cutoff, group_dates, ko_dates)
    return simulate_tournament(
        posterior,
        bracket=bracket,
        n_sims=config.n_sims,
        seed=config.seed,
        max_goals=config.max_goals,
        et_scale=config.et_scale,
        pen_home_prob=config.pen_home_prob,
        played=played,
    )
