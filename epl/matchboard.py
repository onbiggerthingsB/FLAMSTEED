"""A7 — the per-fixture matchboard: the forecast the record already named.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_matchboard.py -q

WHY THIS FILE EXISTS
--------------------
On PASS the acceptance gate's ``marginal_parity`` criterion prints *"simulated
per-fixture marginals ARE the published per-fixture forecast"*, and the shipped
opener carries that sentence in its own ``summary.md``. Until this module there
was no published per-fixture forecast: an issuance published a 20x20 position
matrix and an envelope, and the per-fixture law the criterion compared against
was production's own grid, computed at check time and never written down for a
reader. Amendment A7 (``reports/epl_sim_amendments.md``) rules that the sentence
is made true rather than withdrawn, and this is the file that makes it true.

DERIVED FROM THE RETAINED ROWS, AND FROM NOTHING ELSE
----------------------------------------------------
The matchboard is computed from ``rows_<arm>.npz`` of the SAME bundle: the
scoreline of every unplayed fixture in every one of the run's simulated seasons.
It is never re-priced — not from the particles, not from a fresh grid, not from
``draw_api.production_grid``. That is not a convenience. The 38 of 380 opener
fixtures that carried provisional widening exist in the retained rows and in no
grid a later reader can rebuild, so a re-priced matchboard would publish a
different law from the one the run issued, and it would do it invisibly because
the two laws agree almost everywhere.

``dc_native`` ONLY (A6 (d), restated by A7 (a)). A bridge arm inverts ``u[0]``
against a three-cell H/D/A CDF and then draws its SCORELINE from the bridge's
league-wide conditional (``epl/bridge.py:454``, ``:607``). Its 1X2 is that
fixture's own law; its scorelines are a league-wide conditional wearing that
fixture's name, and every margin field here is computed from scorelines. A
surface with three meaningful columns and four decorative ones is worse than no
surface, so the bridge arms get no matchboard at all rather than a partial one.

THE WORLD CUP SEMANTICS, PINNED HERE BECAUSE THE CODE IS GONE
-------------------------------------------------------------
``scripts/live_scorecard_final.py`` imports ``score_fixtures``, ``grid_to_1x2``
and ``grid_margin_stats`` from ``wcmodel.model.calibration``; none of them is in
that module at HEAD, so "match the World Cup" cannot be answered by running the
World Cup's code. A7 pins the semantics from the generator as git records it at
``f374841`` and from the published ``reports/live_scorecard_final.json``:

* **margin is UNSIGNED**: ``|home_goals - away_goals|``. A draw is 0. It names
  no side and is NOT the winner's margin signed by who won — all 24 drawn rows
  of the published 104 carry ``realized_margin == 0`` and none is negative.
* **e_margin = E|home - away|**. In the World Cup an exact grid sum
  ``sum_ij |i-j| p[i,j]``; here the mean of ``|hg - ag|`` over that fixture's
  retained scorelines — the same functional, estimated from the rows rather than
  integrated over a grid, which is why this one carries a Monte-Carlo error and
  the World Cup's did not.
* **p_marg_ge_k = P(|home - away| >= k)** for k = 2, 3, 4. The three events are
  NESTED, so the chain is monotone BY CONSTRUCTION on any one sample: a
  violation is a defect in this file and never a sampling accident.
* **realized_margin = |hg - ag|** belongs to the scorecard ledger, not here.

EVERY STANDARD ERROR CLUSTERS BY PARTICLE (plan v2 D15), through
:func:`epl.leaguesim.cluster_se` and no local re-derivation of it. The opener's
rows are 1,000 posterior draws used exactly 20 times each; a binomial error over
20,000 seasons would treat correlated draws as independent coins and understate
the real uncertainty by an order of magnitude. A binomial SE here is a FAIL of
the derivation, not a rounding difference.

THE CLOSED SET OF FOUR (A7 (f)). ``e_margin`` and ``p_marg_ge2/3/4`` are
published as World-Cup-parity fields under the owner's 2026-08-22 instruction
and for no other reason, and they are a closed set: a fifth quantity is a new
amendment. Not permitted here, on the render, on the scorecard ledger or on
anything derived from them — prices or returns of any kind, total-goals or
threshold fields, both-teams-to-score, a correct-score list, and no benchmark
comparison column.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from epl import leaguesim
from epl import season as season_mod

#: The one arm that gets a matchboard (A7 (a), on A6 (d)'s reasoning).
ARM = "dc_native"

SCHEMA_VERSION = "epl-matchboard-1"
JSON_FILENAME = f"matchboard_{ARM}.json"
MD_FILENAME = "matchboard.md"

#: The ordered outcomes the ranked probability score runs over. ORDER IS PART OF
#: THE SCORE: a draw is the MIDDLE outcome, and swapping draw and away gives a
#: different (and wrong) number for the same forecast.
OUTCOMES = ("home", "draw", "away")

#: A7 (f): a CLOSED set of four margin quantities — ``e_margin`` and these three.
MARGIN_THRESHOLDS = (2, 3, 4)

#: Every floating-point quantity a row carries, which is what
#: ``matchboard_reproduces`` compares to 1e-12. A7's prose says "eleven"; the
#: field table it is written beside names fourteen, and this file implements the
#: table — see the dated deviation note under A7 in the amendment ledger.
ROW_FLOAT_FIELDS = (
    "probs.home", "probs.draw", "probs.away",
    "probs_se.home", "probs_se.draw", "probs_se.away",
    "e_margin", "e_margin_se",
    "p_marg_ge2", "p_marg_ge3", "p_marg_ge4",
    "p_marg_ge2_se", "p_marg_ge3_se", "p_marg_ge4_se",
)

#: Every field a row carries, in A7 (a)'s own table order.
ROW_FIELDS = (
    "fixture_id", "fixture_ordinal", "date", "home", "away",
    "probs", "probs_se", "e_margin", "e_margin_se",
    "p_marg_ge2", "p_marg_ge3", "p_marg_ge4",
    "p_marg_ge2_se", "p_marg_ge3_se", "p_marg_ge4_se",
    "n_sims", "n_particles",
)

#: A7 (a), *in these terms and not softer ones*.
NO_CLAIM = ("these numbers carry no accuracy claim; the claim is earned by the "
            "live scored record or not at all")

SE_METHOD = ("Every ± on this page is a Monte-Carlo standard error computed "
             "cluster-by-particle (plan v2 D15), `sqrt(sum_s (m_s - p)^2 / "
             "(S(S-1)))` over the per-particle means. It is Monte-Carlo error "
             "and nothing else: it says nothing about model error.")

#: A7 (d) — TWO KINDS OF PROVENANCE, NEVER COLLAPSED. Which of these a rendered
#: matchboard carries is decided by the record it was derived from, not by the
#: writer's confidence.
LAW_ANCHORED_NOTE = (
    "**The law is anchored before kickoff.** The hashes that identify what this "
    "surface was priced under were written into a TRACKED file, and committed, "
    "before the cutoff — which is checkable rather than asserted, because the "
    "file is in this repository's history. Each is listed below with the file, "
    "the commit that introduced it and when that commit was authored.")
LAW_UNANCHORED_NOTE = (
    "**The law is NOT shown to be anchored before kickoff.** The hashes that "
    "identify what this surface was priced under were not found in a tracked "
    "file committed at or before the cutoff, so nothing here is claimed about "
    "when they were first written down. That is a statement about this "
    "repository's history and not about the forecast.")

ROWS_ANCHORED_NOTE = (
    "**The rows are anchored.** The record pins `sidecar_digests` over "
    "`rows_dc_native.npz`, so the bytes this surface was derived from are the "
    "bytes the issuance recorded.")
ROWS_REPRODUCTION_NOTE = (
    "**The rows are not anchored — their provenance is reproduction.** No hash "
    "recorded before kickoff covers `rows_dc_native.npz`: `data/` is gitignored, "
    "so the bundle is not in the repository's history, and this record predates "
    "`sidecar_digests`. What the rows have instead is re-derivation — "
    "`retained_rows_reproduce` re-runs the arm and compares all ten arrays "
    "element for element. That is a real guarantee and a weaker one than "
    "anchoring, and it is written in those words rather than in one.")

#: The uniform baseline of A7 (e), pre-stated as arithmetic this file
#: reproduces rather than defines: 5/18 for a home or away result, 1/9 for a
#: draw. :func:`rps` on `(1/3, 1/3, 1/3)` returns the same numbers, and the
#: tests hold the two against each other.
UNIFORM_RPS = {"home": 5.0 / 18.0, "draw": 1.0 / 9.0, "away": 5.0 / 18.0}

#: A7 (c): a DERIVED artifact lives outside every bundle directory and is named
#: so that `check` can refuse a bundle that contains one.
_DERIVED_RE = re.compile(r"^epl_matchboard_.+_derived\.(?:json|md)$")


class MatchboardError(RuntimeError):
    """Anything the matchboard refuses to derive, render or score."""


# ==========================================================================
# 1. the derivation
# ==========================================================================

def fixture_facts(state) -> tuple[tuple[str, ...], dict[str, dict]]:
    """The ordinal basis and the three facts a matchboard row prints.

    The basis is the season's SORTED fixture ids — the same tuple
    :class:`epl.leaguesim.SimPlan` enumerates to assign ``ordinal``
    (``epl/leaguesim.py:610``), so index equals ordinal by construction rather
    than by coincidence.

    ``date`` is the kickoff DAY as the season knew it at ``observed_by``, after
    the kickoff amendments — ``state.kickoffs_known``, not the fixture's base
    date. A surface that printed the base date would name a day the league had
    already moved.
    """
    ids = tuple(sorted(state.fixtures))
    facts = {}
    for fid, fixture in state.fixtures.items():
        known = state.kickoffs_known.get(fid)
        if known is None:
            raise MatchboardError(
                f"{fid}: the season state knows no kickoff for this fixture")
        facts[fid] = {"home": fixture.home_key, "away": fixture.away_key,
                      "date": known[0].isoformat()}
    return ids, facts


def derive_rows(arrays: Mapping[str, Any], *, fixture_ids: Sequence[str],
                facts: Mapping[str, Mapping[str, str]]) -> list[dict]:
    """One row per retained (i.e. unplayed) fixture, in ``fixture_ordinal`` order.

    ``arrays`` is the ``rows_<arm>.npz`` mapping: ``scorelines`` ``[N, F, 2]``,
    ``particle`` ``[N]`` and ``fixture_ordinals`` ``[F]``.

    THE COLUMN CONTRACT (``epl/leaguesim.py:37``), which is the one thing here
    that is easy to get quietly wrong: ``fixture_ordinals[j]`` is a RANK among
    the season's 380 sorted ids, not a position in this file. At a cutoff with
    played fixtures the retained columns are a SUBSET, so reading column ``j``
    as ``fixture_ids[j]`` resolves the wrong club pair and the wrong date for
    every column after the first played one, and produces a perfectly plausible
    surface while doing it.
    """
    scorelines = np.asarray(arrays["scorelines"])
    particle = np.asarray(arrays["particle"]).ravel()
    ordinals = np.asarray(arrays["fixture_ordinals"]).ravel()

    if scorelines.ndim != 3 or scorelines.shape[2] != 2:
        raise MatchboardError(
            f"scorelines must be [n_sims, n_fixtures, 2], got {scorelines.shape}")
    if scorelines.shape[0] != particle.size:
        raise MatchboardError(
            f"{particle.size} particle labels for {scorelines.shape[0]} seasons")
    if scorelines.shape[1] != ordinals.size:
        raise MatchboardError(
            f"{ordinals.size} fixture ordinals for {scorelines.shape[1]} columns")

    n_sims = int(particle.size)
    n_particles = int(np.unique(particle).size)
    # A repeated ordinal is a corrupt rows file, and the row COUNT cannot see
    # it: 380 columns with one ordinal twice and another missing still prices
    # 380 fixtures. Two rows for one fixture is the visible half of that; the
    # half that matters is the fixture the run priced and the board never
    # mentions.
    values, counts = np.unique(ordinals, return_counts=True)
    repeated = values[counts > 1]
    if repeated.size:
        named = [f"{int(o)} ({fixture_ids[int(o)]})"
                 if 0 <= int(o) < len(fixture_ids) else str(int(o))
                 for o in repeated]
        raise MatchboardError(
            f"the rows repeat fixture ordinal(s) {', '.join(named)}: one column "
            "per unplayed fixture is the npz contract, and a repeat means some "
            "fixture the run priced has no row at all")
    order = np.argsort(ordinals, kind="stable")

    rows: list[dict] = []
    for column in order:
        ordinal = int(ordinals[column])
        if not 0 <= ordinal < len(fixture_ids):
            raise MatchboardError(
                f"fixture ordinal {ordinal} is not a rank among this season's "
                f"{len(fixture_ids)} sorted fixture ids")
        fid = fixture_ids[ordinal]
        fact = facts.get(fid)
        if fact is None:
            raise MatchboardError(
                f"{fid}: the season carries no club keys or kickoff for the "
                "fixture this column prices")

        home_goals = scorelines[:, column, 0].astype(np.int64)
        away_goals = scorelines[:, column, 1].astype(np.int64)
        # UNSIGNED, and a draw is 0 (A7 (a)). Signed would average a symmetric
        # fixture to nothing and report the tails on one side only.
        margin = np.abs(home_goals - away_goals).astype(float)

        indicators = {"home": (home_goals > away_goals).astype(float),
                      "draw": (home_goals == away_goals).astype(float),
                      "away": (home_goals < away_goals).astype(float)}
        row = {
            "fixture_id": fid,
            "fixture_ordinal": ordinal,
            "date": str(fact["date"]),
            "home": str(fact["home"]),
            "away": str(fact["away"]),
            "probs": {k: float(v.mean()) for k, v in indicators.items()},
            "probs_se": {k: leaguesim.cluster_se(v, particle)
                         for k, v in indicators.items()},
            "e_margin": float(margin.mean()),
            "e_margin_se": leaguesim.cluster_se(margin, particle),
            "n_sims": n_sims,
            "n_particles": n_particles,
        }
        for k in MARGIN_THRESHOLDS:
            tail = (margin >= k).astype(float)
            row[f"p_marg_ge{k}"] = float(tail.mean())
            row[f"p_marg_ge{k}_se"] = leaguesim.cluster_se(tail, particle)
        rows.append({name: row[name] for name in ROW_FIELDS})
    return rows


def derive(directory, *, record: dict | None = None, state=None,
           season_root=None) -> dict:
    """The whole matchboard document for a bundle: header block plus rows.

    Reads FOUR things out of the bundle and nothing from anywhere else: the
    record (``issuance.json``), the arm's envelope (``output_dc_native.json``),
    the retained rows (``rows_dc_native.npz``), and — when the issuance ran a
    gate — the provisional-widening count the acceptance report already
    measured, which the render is required to state.

    ``state`` is accepted so ``check`` does not rebuild a season snapshot it has
    already built; passing a DIFFERENT state than the record names would be
    deriving one run's matchboard against another run's schedule, so the cutoff
    and ``observed_by`` are held against the record either way.
    """
    directory = Path(directory)
    if record is None:
        record = json.loads((directory / "issuance.json").read_text())

    if ARM not in (record.get("arms") or []):
        raise MatchboardError(
            f"{directory}: this issuance carries no {ARM!r} arm, and A7 (a) "
            "gives a matchboard to no other arm")

    payload = json.loads((directory / f"output_{ARM}.json").read_text())
    envelope = payload.get("envelope") or {}

    if state is None:
        season_obj = season_mod.Season.load(
            record["season"],
            root=season_mod.SEASON_ROOT if season_root is None else season_root)
        state = season_obj.at(record["cutoff"], record["observed_by"])
    if str(state.cutoff) != str(record["cutoff"]) or \
            str(state.observed_by) != str(record["observed_by"]):
        raise MatchboardError(
            f"the season state is at ({state.cutoff}, {state.observed_by}) and "
            f"the record at ({record['cutoff']}, {record['observed_by']}); a "
            "matchboard of one run against another run's schedule is not that "
            "run's matchboard")

    with np.load(directory / f"rows_{ARM}.npz") as handle:
        arrays = {name: handle[name]
                  for name in ("scorelines", "particle", "fixture_ordinals")}

    ids, facts = fixture_facts(state)
    rows = derive_rows(arrays, fixture_ids=ids, facts=facts)

    # A7 (a): a matchboard that prices a different number of fixtures than the
    # run had is not the run's matchboard.
    if len(rows) != int(record["n_unplayed"]):
        raise MatchboardError(
            f"the matchboard prices {len(rows)} fixtures and the record reports "
            f"n_unplayed = {record['n_unplayed']}")
    n_sims = int(arrays["particle"].size)
    if n_sims != int(record["n_sims"]):
        raise MatchboardError(
            f"the rows carry {n_sims} seasons and the record reports "
            f"n_sims = {record['n_sims']}")
    n_particles = int(np.unique(arrays["particle"]).size)
    if n_particles != int(record["n_particles"]):
        raise MatchboardError(
            f"the rows carry {n_particles} distinct particles and the record "
            f"reports n_particles = {record['n_particles']}")

    return {
        "schema_version": SCHEMA_VERSION,
        "season": record["season"],
        "arm": ARM,
        "cutoff": str(record["cutoff"]),
        "observed_by": str(record["observed_by"]),
        "seed": int(record["seed"]),
        "chunk_size": int(record["chunk_size"]),
        "n_sims": n_sims,
        "n_particles": n_particles,
        "n_fixtures": len(rows),
        "source_rows": f"rows_{ARM}.npz",
        "effective_posterior_hash": record["effective_posterior_hash"],
        # the record's `digests[ARM]`: WHICH RUN these rows came out of
        "run_digest": (record.get("digests") or {}).get(ARM),
        # the three the envelope already carries, and which anchor the names and
        # the dates this surface prints
        "manifest_sha256": envelope.get("manifest_sha256"),
        "fixtures_base_sha256": envelope.get("fixtures_base_sha256"),
        "kickoff_amendments_sha256": envelope.get("kickoff_amendments_sha256"),
        # what the render is required to state (A7 (a))
        "max_goals": envelope.get("max_goals"),
        "n_provisional": _provisional_count(directory),
        "rows_provenance": _rows_provenance(directory, record),
        "rows": rows,
    }


def _rows_provenance(directory: Path, record: Mapping[str, Any]) -> str:
    """A7 (d): ``anchored`` only when the record's pin over the rows is TRUE.

    PRESENCE WAS NOT ENOUGH (Codex r7 #5). A record carrying sixty-four zeros
    where ``rows_dc_native.npz``'s digest belongs produced a document — and a
    rendered page — saying *the bytes this surface was derived from are the
    bytes the issuance recorded*, which was a claim about a hash nobody had
    recomputed. A7 (d)'s whole point is that the two kinds of provenance are
    never collapsed, and an anchored word earned by an unchecked hash collapses
    them by other means.

    A mismatch REFUSES the derivation rather than downgrading it to
    ``reproduction``. The weaker word would be a second false claim: a bundle
    whose rows are not the rows its record pins is not a bundle whose halves
    came from one run, and it is not a source for anything.
    """
    pinned = ((record.get("sidecar_digests") or {}).get(ARM) or {}).get("rows")
    if not pinned:
        return "reproduction"
    rows = Path(directory) / f"rows_{ARM}.npz"
    actual = leaguesim.sha256_file(rows)
    if actual != pinned:
        raise MatchboardError(
            f"{rows}: the record pins {pinned} over this file and it hashes to "
            f"{actual}. A bundle that disagrees with its own record is not a "
            "source: the derivation is refused rather than published under a "
            "provenance word neither half of the bundle supports")
    return "anchored"


def _provisional_count(directory: Path) -> int | None:
    """How many fixtures carried provisional widening, from the gate's own count.

    ``None`` when the issuance ran no gate: the render then says the count is
    unavailable rather than printing a zero it did not measure — a zero nobody
    counted is the worst of the three answers.
    """
    path = directory / "acceptance.json"
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    detail = ((report.get("criteria") or {}).get("marginal_parity") or {}
              ).get("detail") or {}
    count = detail.get("n_provisional")
    return None if count is None else int(count)


# ==========================================================================
# 2. the derived artifact (A7 (c))
# ==========================================================================

def derived_filename(season: str, cutoff, suffix: str) -> str:
    return (f"epl_matchboard_{season_mod.season_dir_name(season)}_"
            f"{pd.Timestamp(cutoff).date().isoformat()}_derived.{suffix}")


def is_derived_name(name: str) -> bool:
    return bool(_DERIVED_RE.match(str(name)))


def derived_artifacts_in(directory) -> list[str]:
    """Every file ANYWHERE under `directory` named like a derived artifact.

    A7 (c): a derived artifact is written OUTSIDE every bundle directory, and
    `check` FAILs a bundle that contains one — so a derivation can never drift
    into a bundle and be mistaken for a sidecar the record anchors.

    RECURSIVE (Codex r7 #5). The scan read only a directory's immediate
    children, and "contains" is not "lists": one `mkdir` was enough to make a
    derivation inside a bundle invisible to the refusal that exists to find it.
    Paths are returned relative to `directory`, so the FAIL names where the file
    actually is.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(p.relative_to(directory).as_posix()
                  for p in directory.rglob("*")
                  if p.is_file() and is_derived_name(p.name))


def as_derived(document: Mapping[str, Any], *, source_bundle: str,
               derived_at: str, recorded_hashes: Mapping[str, Any]) -> dict:
    """Stamp a document as a labelled derivation rather than part of a record.

    Carries the four things A7 (c) requires: ``derived``, the source bundle
    path, when it was derived, and the source bundle's RECORDED hashes — copied
    from its record, not recomputed here, because a hash this file computes
    today is not a hash that record made yesterday.
    """
    return {**dict(document), "derived": True,
            "source_bundle": str(source_bundle),
            "derived_at": str(derived_at),
            "source_recorded_hashes": json.loads(
                leaguesim.canonical_json(recorded_hashes))}


# ==========================================================================
# 3. the render
# ==========================================================================

def render_markdown(document: Mapping[str, Any]) -> str:
    """``matchboard.md`` — the same numbers, in the house voice.

    Probabilities are never naked: every quantity in the table carries its
    Monte-Carlo error, and the method is stated under it. An interval whose
    method is not stated is a decoration (A2-N4), and a probability with no
    error beside it is worse.
    """
    rows = list(document.get("rows") or [])
    derived = bool(document.get("derived"))
    season = document.get("season")
    cutoff = document.get("cutoff")

    lines: list[str] = []
    if derived:
        lines += [
            f"**Derived after the fact from the preserved bundle at "
            f"`{document.get('source_bundle')}` on "
            f"{document.get('derived_at')}. It is NOT part of that bundle's "
            f"record**: nothing was written into the bundle, no hash in its "
            f"record covers this file, and the issuance was not re-run.",
            ""]
    lines += [f"# Matchboard — {season}, cutoff {cutoff} "
              f"(`{document.get('arm')}`)",
              "",
              f"One row per unplayed fixture: **{len(rows)}** of them, priced "
              f"from **{document.get('n_sims')}** simulated seasons drawn under "
              f"**{document.get('n_particles')}** joint posterior particles.",
              ""]

    lines += ["## What this is not", "",
              f"On the record, and in these terms rather than softer ones: "
              f"**{NO_CLAIM}**. Nothing on this page has been scored against a "
              "live result. The preregistered walk-forward record is what "
              "licenses publishing a forecast; it does not license believing "
              "one.",
              "",
              f"**The law is one arm's.** Every number here comes from the "
              f"`{document.get('arm')}` arm and from its retained simulated "
              "scorelines. It is not an average over the arms and it is not a "
              "consensus of anything.",
              ""]

    max_goals = document.get("max_goals")
    provisional = document.get("n_provisional")
    truncation = (
        f"**Scorelines are truncated.** Every fixture is priced on a grid "
        f"truncated at {max_goals} goals per side under D11 v1.0.1 (amendment "
        f"A1), and the mass beyond that grid is DISCARDED rather than "
        f"redistributed. Production truncates at the same {max_goals} goals and "
        f"discards the same tail; `excluded_mass_{document.get('arm')}.json` "
        f"beside this file measures what it came to, per fixture.")
    if provisional is None:
        widening = (
            "**Provisional widening: not measured for this issuance.** It ran "
            "no acceptance gate, so no count of provisionally widened fixtures "
            "was taken, and none is asserted here.")
    else:
        widening = (
            f"**{provisional} of the {len(rows)} fixtures carried provisional "
            f"widening.** Those fixtures were priced through the model's "
            f"existing uncertainty machinery for clubs the posterior has little "
            f"or no top-flight history for. The widening is in these rows and "
            f"in no grid a later reader can rebuild, which is why this surface "
            f"is derived from the rows and never re-priced.")
    lines += ["## What priced it", "", truncation, "", widening, "", SE_METHOD,
              ""]

    lines += ["## Provenance", "",
              f"- season / cutoff / observed by: `{season}` / `{cutoff}` / "
              f"`{document.get('observed_by')}`",
              f"- seed / chunk size: `{document.get('seed')}` / "
              f"`{document.get('chunk_size')}`",
              f"- effective posterior: `{document.get('effective_posterior_hash')}`",
              f"- run digest (`digests[\"{document.get('arm')}\"]`): "
              f"`{document.get('run_digest')}`",
              f"- rows read: `{document.get('source_rows')}`",
              f"- manifest / fixtures / kickoff amendments: "
              f"`{document.get('manifest_sha256')}` / "
              f"`{document.get('fixtures_base_sha256')}` / "
              f"`{document.get('kickoff_amendments_sha256')}`",
              ""]
    # A7 (d) — TWO KINDS, NEVER COLLAPSED. The LAW and the ROWS get separate
    # paragraphs and separate words, because part of a derivation's provenance
    # can be anchored while the other part is only reproducible, and one word
    # covering both would be the ledger manufacturing an anchor for a file the
    # record explicitly reports as unanchored.
    #
    # A bundle sidecar makes no law claim at all: it was written by the run that
    # issued it and has no git history to appeal to, and silence is better than
    # a sentence nobody checked.
    anchor = document.get("law_anchor")
    if anchor is not None:
        lines += [LAW_ANCHORED_NOTE if anchor.get("pre_kickoff")
                  else LAW_UNANCHORED_NOTE, ""]
        for entry in anchor.get("hashes") or []:
            lines.append(
                f"- `{entry.get('name')}` = `{entry.get('hash')}` — "
                + (f"`{entry['file']}`, commit `{entry['commit']}`, authored "
                   f"{entry['committed_at']}" if entry.get("commit")
                   else "not found in any tracked file"))
        lines += ["",
                  f"...against a cutoff of `{anchor.get('cutoff')}`.", ""]

    lines += [ROWS_ANCHORED_NOTE if document.get("rows_provenance") == "anchored"
              else ROWS_REPRODUCTION_NOTE, ""]

    lines += ["## The rows", "",
              "`margin` is UNSIGNED — `|home goals − away goals|`, so a draw is "
              "0 and the quantity names no side. `E margin` is the mean of that "
              "over this fixture's simulated scorelines; `P(margin k+)` is the "
              "fraction of them at or beyond `k`. The three tail events are "
              "nested, so the chain is monotone by construction.",
              "",
              "| Fixture | Date | Home | Away | P(home) | P(draw) | P(away) | "
              "E margin | P(margin 2+) | P(margin 3+) | P(margin 4+) |",
              "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: "
              "| ---: | ---: |"]
    for row in rows:
        cells = [f"`{row['fixture_id']}`", str(row["date"]), str(row["home"]),
                 str(row["away"])]
        cells += [_pm(row["probs"][k], row["probs_se"][k]) for k in OUTCOMES]
        cells.append(_pm(row["e_margin"], row["e_margin_se"]))
        cells += [_pm(row[f"p_marg_ge{k}"], row[f"p_marg_ge{k}_se"])
                  for k in MARGIN_THRESHOLDS]
        lines.append("| " + " | ".join(cells) + " |")

    lines += ["",
              f"Machine-readable beside this file: `{JSON_FILENAME}`, "
              f"schema `{SCHEMA_VERSION}`.",
              ""]
    return "\n".join(lines)


def _pm(value: float, se: float) -> str:
    return f"{float(value):.4f} ± {float(se):.4f}"


def write(document: Mapping[str, Any], directory, *,
          json_name: str = JSON_FILENAME,
          md_name: str = MD_FILENAME) -> tuple[Path, Path]:
    """Write the two files and return their paths, JSON first."""
    directory = Path(directory)
    json_path = directory / json_name
    md_path = directory / md_name
    json_path.write_text(leaguesim.canonical_json(document) + "\n")
    md_path.write_text(render_markdown(document))
    return json_path, md_path


# ==========================================================================
# 4. the scorecard ledger (A7 (e))
# ==========================================================================

def rps(probs: Mapping[str, float], outcome: str) -> float:
    """``RPS = (1/(r-1)) sum_{i=1..r-1} (CP_i - CO_i)^2``, r = 3.

    Over the ORDERED outcomes ``(home, draw, away)``. This project's own
    literal, and the ordering is load-bearing: the draw is the middle outcome,
    so a home forecast that misses by predicting a draw is penalised less than
    one that misses by predicting an away win.
    """
    if outcome not in OUTCOMES:
        raise MatchboardError(f"{outcome!r} is not one of {OUTCOMES}")
    predicted = [float(probs[k]) for k in OUTCOMES]
    observed = [1.0 if k == outcome else 0.0 for k in OUTCOMES]
    cum_p = cum_o = total = 0.0
    for i in range(len(OUTCOMES) - 1):
        cum_p += predicted[i]
        cum_o += observed[i]
        total += (cum_p - cum_o) ** 2
    return total / (len(OUTCOMES) - 1)


def uniform_rps(outcome: str) -> float:
    """The baseline column, pre-stated by A7 (e) as exact arithmetic."""
    if outcome not in OUTCOMES:
        raise MatchboardError(f"{outcome!r} is not one of {OUTCOMES}")
    return UNIFORM_RPS[outcome]


def law_provenance(document: Mapping[str, Any]) -> str | None:
    """What a scorecard row may say about the LAW that priced its forecast.

    ``None`` when no anchor was computed — a bundle sidecar has no git history
    to appeal to, and inventing a verdict for it would be the collapse A7 (d)
    forbids.
    """
    anchor = document.get("law_anchor")
    if anchor is None:
        return None
    return "anchored-pre-kickoff" if anchor.get("pre_kickoff") \
        else "not-shown-anchored"


def outcome_of(home_goals: int, away_goals: int) -> str:
    if int(home_goals) > int(away_goals):
        return "home"
    if int(home_goals) < int(away_goals):
        return "away"
    return "draw"


def season_ledger(board: Mapping[str, Any], *, season=None,
                  season_root=None) -> season_mod.LedgerView:
    """The season's results ledger, resolved by the SEASON'S OWN machinery.

    :func:`epl.season.current_ledger_view` — the same
    :func:`epl.season.resolve_ledger` the league table reads through, with no
    bounds, which is what the ledger says right now. Bitemporal resolution and
    the conflict rules that go with it (a score withdrawn by a later
    ``abandoned`` is not a result; a postponement corrected by the replayed
    match is) live there and are not restated here: two implementations of
    "what was played" is exactly the shape of defect this project spent A6 on.
    """
    if season is None:
        season = season_mod.Season.load(
            board["season"],
            root=season_mod.SEASON_ROOT if season_root is None else season_root)
    return season_mod.current_ledger_view(season)


def _goals(result: Mapping[str, Any], key: str, fid: str) -> int:
    """One goal count, through :func:`epl.season.goal_count` and never around it.

    That function is THE definition in this codebase — finite, non-negative,
    integral, and a coercion nowhere — so a scorecard applies it rather than
    spelling a second, weaker one. `int(result["home_goals"])` was the weaker
    one: it accepted `-7` and rounded `1.9` to `1`.
    """
    try:
        return season_mod.goal_count(result.get(key), f"{fid} {key}")
    except season_mod.SeasonError as exc:
        # the label already opens with the fixture id; prefixing again would
        # print it twice
        raise MatchboardError(str(exc)) from exc


def score(board: Mapping[str, Any], results: Iterable[Mapping[str, Any]], *,
          ledger: season_mod.LedgerView | None = None,
          season_root=None) -> list[dict]:
    """Scorecard rows for results that have entered the season ledger.

    `board` is a :func:`derive` document — it is what carries the provenance
    each ledger row must cite, which is why the whole document is the argument
    and not a bare list of rows.

    **THE SEASON LEDGER IS THE SOURCE OF TRUTH** (Codex r7 #4). A results file
    handed to this function is a REQUEST to score rows the ledger already
    carries, never a way for a result to enter the record: each row must name a
    fixture the resolved ledger reports as played, with the scoreline the ledger
    resolved to. Before this rule, a fabricated `99-(-7)` for a fixture nine
    months away scored cleanly against an EMPTY ledger, twice, and produced
    scorecard rows indistinguishable from real ones. The resolution is
    :func:`season_ledger`'s and the conflict rules are
    :func:`epl.season.resolve_ledger`'s; `ledger` overrides the lookup for
    callers holding a view already (and for tests of a synthetic season).

    **No pass rule, and no benchmark column.** This ledger reports; it decides
    nothing, triggers nothing and gates nothing (A7 (e), (f)).

    **A row is admissible only if the forecast preceded the kickoff**, and this
    refuses rather than drops: the issuance's ``cutoff`` AND ``observed_by``
    must both be at or before the fixture's kickoff day as the season knew it.
    The comparison is made at DAY granularity, which is what the matchboard row
    records, and a ledger that silently omitted the row it could not justify
    would be a ledger nobody can audit.
    """
    by_id = {row["fixture_id"]: row for row in (board.get("rows") or [])}
    cutoff = pd.Timestamp(board["cutoff"])
    observed_by = pd.Timestamp(board["observed_by"])
    if ledger is None:
        ledger = season_ledger(board, season_root=season_root)
    played = ledger.played_rows
    statuses = ledger.statuses

    out: list[dict] = []
    for result in results:
        fid = result.get("fixture_id")
        row = by_id.get(fid)
        if row is None:
            raise MatchboardError(
                f"{fid!r} is not on this matchboard: a result cannot be scored "
                "against a forecast that never priced it")
        kickoff = pd.Timestamp(row["date"])
        for name, stamp in (("cutoff", cutoff), ("observed_by", observed_by)):
            if stamp > kickoff:
                raise MatchboardError(
                    f"{fid}: the issuance's {name} ({stamp}) is after the "
                    f"kickoff the season knew ({row['date']}); the forecast did "
                    "not precede the match and the row is not admissible")
        # A7 (e): the ledger is append-only and each row records the matchweek
        # and the ingest that supplied the result. A row filed with neither
        # cannot do what a per-matchweek append-only ledger is for, so it is
        # refused at the door rather than written with two nulls in it.
        #
        # EMPTY IS ABSENT. `""` is what a hand-written results file carries when
        # a column was left blank, and a row stamped with two empty strings
        # answers "which matchweek, which ingest" exactly as poorly as two
        # nulls do.
        for required in ("matchweek", "ingest"):
            value = result.get(required)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise MatchboardError(
                    f"{fid}: this result records no {required!r}, and an "
                    "append-only ledger row that cannot say which matchweek it "
                    "belongs to or which ingest supplied it is not auditable")
        home_goals = _goals(result, "home_goals", fid)
        away_goals = _goals(result, "away_goals", fid)
        # ...and THEN the ledger, which is what decides whether this match was
        # played at all and what its score was.
        entry = played.get(fid)
        if entry is None:
            status = statuses.get(fid)
            raise MatchboardError(
                f"{fid}: the season's results ledger resolves no result for "
                f"this fixture"
                + (f" — its winning ledger row is {status!r}" if status else "")
                + ". The ledger is the source of truth for what was played, and "
                "a scorecard row is a reading of it rather than a second door a "
                "result can come through")
        ledger_home = _goals({"hg": entry.get("hg")}, "hg", fid)
        ledger_away = _goals({"ag": entry.get("ag")}, "ag", fid)
        if (ledger_home, ledger_away) != (home_goals, away_goals):
            raise MatchboardError(
                f"{fid}: this result scores {home_goals}-{away_goals} and the "
                f"season's results ledger resolves to "
                f"{ledger_home}-{ledger_away}. The ledger is the source of "
                "truth, and a scorecard row that disagrees with it is refused "
                "rather than filed beside it")
        outcome = outcome_of(home_goals, away_goals)
        out.append({
            "fixture_id": fid,
            "date": row["date"],
            "home": row["home"],
            "away": row["away"],
            "probs": dict(row["probs"]),
            "e_margin": row["e_margin"],
            "p_marg_ge2": row["p_marg_ge2"],
            "p_marg_ge3": row["p_marg_ge3"],
            "p_marg_ge4": row["p_marg_ge4"],
            "season": board["season"],
            "cutoff": str(board["cutoff"]),
            "observed_by": str(board["observed_by"]),
            "run_digest": board.get("run_digest"),
            # A7 (d): a row citing the MW0 derivation says BOTH kinds of
            # provenance in the words that are true of each, and does not call
            # the rows anchored.
            "rows_provenance": board.get("rows_provenance"),
            "law_provenance": law_provenance(board),
            "source_bundle": board.get("source_bundle"),
            "outcome": outcome,
            "realized_margin": abs(home_goals - away_goals),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "matchweek": result.get("matchweek"),
            "ingest": result.get("ingest"),
            "rps": rps(row["probs"], outcome),
            "rps_uniform": uniform_rps(outcome),
        })
    return out


__all__ = [
    "ARM", "SCHEMA_VERSION", "JSON_FILENAME", "MD_FILENAME", "OUTCOMES",
    "MARGIN_THRESHOLDS", "ROW_FIELDS", "ROW_FLOAT_FIELDS", "NO_CLAIM",
    "SE_METHOD", "ROWS_ANCHORED_NOTE", "ROWS_REPRODUCTION_NOTE",
    "LAW_ANCHORED_NOTE", "LAW_UNANCHORED_NOTE", "UNIFORM_RPS",
    "MatchboardError", "fixture_facts", "derive_rows", "derive",
    "derived_filename", "is_derived_name", "derived_artifacts_in", "as_derived",
    "render_markdown", "write", "rps", "uniform_rps", "outcome_of",
    "law_provenance", "season_ledger", "score",
]
