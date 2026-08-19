"""The operator's front door: issue a forecast, ingest results, check a run.

Four verbs, and nothing clever behind any of them (plan v2 T9):

``forecast``
    One fit at one cutoff, one particle book, one run per arm through the same
    engine and the same ranker, written to
    ``data/epl/sim/issuances/<season>/<cutoff>/`` with its provenance envelope,
    its limitations note and its acceptance gate beside it.
``ingest-results``
    Append rows to the season's results ledger from openfootball or from a
    hand-entered file. Idempotent; a contradiction STOPs rather than resolving
    itself (plan v2 D4).
``retro``
    Delegates to :mod:`epl.simretro`'s smoke run — one entry point, one harness.
``check``
    Re-runs a written issuance from its own persisted bundle and demands the
    same numbers, then re-checks coherence and per-fixture marginal parity.

**The acceptance gate.** :func:`acceptance_gate` evaluates the eleven criteria
plan v2 T9 lists, one function each, and every one of them can fail: the tests
beside this module feed each check the input that must break it. A criterion
that could not be run comes back ``SKIPPED`` and the gate does NOT pass — an
unrun check is not a passing check.

Nothing here publishes anything. The issuance lands under ``data/epl/`` (which
is gitignored) and a human decides what, if anything, becomes public.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from epl import (bridge as bridge_mod, leaguesim, particles, paths,
                 season as season_mod, simcanary, table as table_mod)

# ==========================================================================
# constants
# ==========================================================================

#: The live season this CLI was built for. Any season with a snapshot works.
DEFAULT_SEASON = "2026/27"

#: The arm whose envelope, limitations note and gate the issuance publishes.
#: The retrospective may move this; until it has run, the model is the default
#: and the two bridge arms are carried beside it for comparison (plan v2 D18).
PUBLISHED_ARM = "dc_native"

ARMS = ("dc_native", "dc_wdl_bridge", "elo_wdl_bridge")

DEFAULT_N_SIMS = 20_000
DEFAULT_SEED = 20260611

#: Live issuances (plan v2 §4). Under `data/`, so gitignored like the rest.
ISSUANCE_ROOT = paths.DATA_DIR / "sim" / "issuances"

#: A store of its own, so a live run that appends the season's results to the
#: archive does not rewrite the retrospective's archive-only store on every
#: alternation. The feature-panel cache is content-addressed, so two stores with
#: identical content still share their cached panels.
LIVE_STORE_DIR = paths.FIT_DIR / "store_live"

#: The eleven acceptance criteria of plan v2 T9, in the order the summary
#: prints them. Frozen: a criterion cannot be dropped without a test failing.
GATE_CRITERIA = (
    "clubs_and_fixtures",        # 20 clubs / 380 fixtures validate
    "promoted_complete",         # every promoted club completes a season
    "marginal_parity",           # simulated marginals == the published forecast
    "tiebreak_oracle",           # the T3 ladder suite passes
    "cutoff_table",              # played + adjustments reconstruct the table
    "matrix_and_markets",        # matrix and threshold counts agree
    "serial_equals_chunked",     # serial and chunked runs reproduce
    "mc_uncertainty",            # MC uncertainty beside every headline
    "limitations",               # limitations explicit
    "src_scripts_untouched",     # git diff --stat -- src scripts empty
    "lock_valid",                # the preregistration lock chain still verifies
)

#: Section headings :func:`epl.leaguesim.limitations_markdown` must emit. The
#: check below refuses a note missing any of them, and the test deletes each in
#: turn to prove the refusal is real.
LIMITATIONS_SECTIONS = (
    "## What the forecast is conditional on",
    "## What the rulebook does not decide",
    "## The state of the season",
    "## Monte-Carlo error",
    "## What these numbers are not",
)

#: Phrases the note must carry whatever the numbers are.
LIMITATIONS_PHRASES = (
    "table positions",
    "no betting content",
    "Results lag flag",
    "Tiebreak rule id",
)

ISSUANCE_SCHEMA_VERSION = "epl-issuance-1"


class CliError(RuntimeError):
    """Anything the CLI refuses to do."""


# ==========================================================================
# 1. the fit
# ==========================================================================

@dataclass
class FitBundle:
    """What a forecast needs from the fit, and what it needs to say about it.

    ``post`` is the fitted :class:`epl.dcfit.ColdStartPosterior`; it may be
    ``None`` when the book was built some other way (a synthetic book in a
    test), in which case the per-fixture parity check falls back to the book's
    own published law rather than to ``draw_api.production_grid``.
    """

    book: particles.ParticleBook
    post: Any = None
    anchor: Any = None
    matches: pd.DataFrame | None = None
    info: dict = field(default_factory=dict)


def live_fit(season_obj: season_mod.Season, cutoff, *, matches=None, store=None,
             config=None, elo_config=None, store_root=None, observed_by=None,
             verbose: bool = True) -> FitBundle:
    """One fit for a season in progress, through the explicit transition.

    The three things that make this different from an archive fit, all of them
    plan v2 D5:

    1. the archive handed to :class:`epl.liveanchor.LiveAnchor` excludes the
       target season, so the anchor cannot re-seed from "the rows present";
    2. the store the panel is built from is archive **plus** the season's
       results ledger, so a mid-season fit trains on the season so far;
    3. ``cold_start`` is computed from the MANIFEST minus the fitted teams,
       because ``dcfit.cold_start_clubs`` reads played history at or after the
       cutoff and therefore returns ``[]`` at an opener.
    """
    from epl import baseline, dcfit, fit as epl_fit, freeze, liveanchor
    from epl.schema import sort_for_walk_forward

    started = time.perf_counter()
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    season = season_obj.season

    archive = played.loc[played["season"].astype(str) != season]
    cfg = freeze.frozen_wcmodel_config() if config is None else config
    elo_cfg = freeze.frozen_elo_config() if elo_config is None else elo_config

    anchor = liveanchor.LiveAnchor(archive, season_obj.results,
                                   season_obj.manifest, elo_cfg)
    live_rows = liveanchor.visible_rows(anchor.rows, cutoff, observed_by)
    frames = [archive]
    if live_rows:
        frames.append(liveanchor.rows_to_frame(live_rows, season))
    train = sort_for_walk_forward(pd.concat(frames, ignore_index=True))

    if store is None:
        store = epl_fit.build_store(train, root=store_root or LIVE_STORE_DIR)

    with epl_fit.config_read_once(cfg):
        teams = _fitted_teams(cutoff, store, cfg)
        cold = anchor.cold_start_for(teams)
        if verbose:
            print(f"[forecast] fitting at {cutoff}: {len(teams)} fitted teams, "
                  f"cold start {cold}", flush=True)
        post, info = dcfit.fit_epl(cutoff, store, anchor, cfg, matches=train,
                                   cold_start=cold,
                                   feature_cache_dir=paths.FIT_CACHE_DIR)

    book = particles.ParticleBook.from_posterior(post)
    return FitBundle(
        book=book, post=post, anchor=anchor, matches=played,
        info={
            "fit_seconds": float(info.seconds),
            "n_training_matches": int(info.n_training_matches),
            "n_teams": int(info.n_teams),
            "fitted_teams": list(info.teams),
            "cold_start_teams": list(info.cold_start_teams),
            "cold_start_z": {k: float(v) for k, v in info.cold_start_z.items()},
            "provisional_teams": list(info.provisional_teams),
            "anchor_spec": info.anchor_spec,
            "promoted_seed": float(anchor.promoted_seed),
            "n_live_rows_visible": len(live_rows),
            "effective_posterior_hash": book.content_hash(),
            "n_particles": int(book.n_particles),
            "wall_seconds": round(time.perf_counter() - started, 2),
        })


def _fitted_teams(cutoff, store, cfg) -> list[str]:
    """The team index ``fit_epl`` will build, computed before the fit runs.

    ``fit_epl`` takes ``cold_start`` as a list, and the list is "manifest minus
    fitted"; the fitted set is a property of the panel, so the panel is built
    first. It is the same cached call the fit itself makes, so the second build
    is a cache hit rather than a second Elo walk.
    """
    from wcmodel.data import features as wc_features
    from wcmodel.model.panel import to_match_panel

    feats = wc_features.build_cached(cutoff, store, cfg,
                                     cache_dir=paths.FIT_CACHE_DIR)
    mp = to_match_panel(feats)
    return sorted(set(mp["home_team"]) | set(mp["away_team"]))


# ==========================================================================
# 2. the forecast
# ==========================================================================

def issuance_dir(season: str, cutoff, root=None) -> Path:
    root = ISSUANCE_ROOT if root is None else Path(root)
    day = pd.Timestamp(cutoff).normalize().date().isoformat()
    return root / season_mod.season_dir_name(season) / day


def forecast(*, season: str = DEFAULT_SEASON, cutoff,
             arms: Sequence[str] = (PUBLISHED_ARM,),
             n_sims: int = DEFAULT_N_SIMS, seed: int = DEFAULT_SEED,
             chunk_size: int = leaguesim.DEFAULT_CHUNK_SIZE,
             n_particles: int | None = None,
             root=season_mod.SEASON_ROOT, out_root=None,
             fit: FitBundle | None = None, matches=None, store=None,
             observed_by=None, published_arm: str = PUBLISHED_ARM,
             gate: bool = True, gate_kwargs: dict | None = None,
             witness_states: Sequence[season_mod.SeasonState] = (),
             require_verified_adjustments: bool = False,
             verbose: bool = True) -> dict:
    """Issue one forecast: fit, simulate every arm, write, gate.

    Returns the issuance record (also written as ``issuance.json``) with the
    live :class:`epl.leaguesim.SimRun` objects under ``runs`` for callers that
    want them in memory.
    """
    arms = tuple(dict.fromkeys(arms))
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        raise CliError(f"unknown arm(s) {unknown}; the arms are {list(ARMS)}")
    if not arms:
        raise CliError("no arms requested")
    if published_arm not in arms:
        published_arm = arms[0]

    started = time.perf_counter()
    season_obj = season_mod.Season.load(season, root=root)
    state = season_obj.at(cutoff, observed_by,
                          require_verified_adjustments=require_verified_adjustments)

    if fit is None:
        fit = live_fit(season_obj, cutoff, matches=matches, store=store,
                       observed_by=observed_by, verbose=verbose)
    book = fit.book
    n_particles = book.n_particles if n_particles is None else int(n_particles)

    unpriceable = [c for c in state.clubs if c not in book.idx]
    if unpriceable:
        raise CliError(
            f"the posterior cannot price {unpriceable}: the fit's team index "
            "and the season manifest disagree, which is the cold-start path "
            "failing (plan v2 D5/D11)")

    archive = fit.matches if matches is None else matches
    needs_bridge = bool({"dc_wdl_bridge", "elo_wdl_bridge"} & set(arms))
    if needs_bridge and archive is None:
        raise CliError(
            "the bridge arms need pre-cutoff match history to estimate "
            "P(scoreline | outcome) point-in-time; none was supplied")

    bridge = None
    if needs_bridge:
        bridge = bridge_mod.EmpiricalBridge.fit(archive, cutoff)

    directory = issuance_dir(season, cutoff, out_root)
    directory.mkdir(parents=True, exist_ok=True)

    runs: dict[str, leaguesim.SimRun] = {}
    providers: dict[str, Any] = {}
    written: dict[str, list[str]] = {}
    for arm in arms:
        provider = providers[arm] = _provider(arm, fit, bridge, state, cutoff,
                                              n_particles)
        run = leaguesim.simulate(arm, state, provider, n_sims, seed,
                                 chunk_size=chunk_size, season=season_obj,
                                 boundaries=season_obj.manifest.material_boundaries,
                                 rule_id=season_obj.manifest.tiebreak_rule_id,
                                 n_particles=n_particles)
        table_mod.check_doubly_stochastic(run.matrix)
        runs[arm] = run
        if verbose:
            print(f"[forecast] {arm}: {run.envelope['wall_seconds']:.1f}s", flush=True)

    # Per-arm outputs first, then the published arm's envelope and limitations
    # LAST and explicitly — so which arm the issuance speaks for is a decision,
    # not an artefact of iteration order.
    for arm, run in runs.items():
        paths_written = leaguesim.write_outputs(run, directory)
        written[arm] = [p.name for p in paths_written.values()]
    published = runs[published_arm]
    limitations = leaguesim.limitations_markdown(published)
    (directory / "envelope.json").write_text(
        leaguesim.canonical_json(published.envelope) + "\n")
    (directory / "limitations.md").write_text(limitations)
    book.save(directory / "particles.npz")
    if fit.info:
        (directory / "fit.json").write_text(
            leaguesim.canonical_json(_plain(fit.info)) + "\n")

    gate_report = None
    if gate:
        gate_report = acceptance_gate(
            run=published, state=state, manifest=season_obj.manifest,
            book=book, post=fit.post, limitations=limitations,
            # the re-run must go through the arm's OWN provider; falling back to
            # the book would silently re-run a different arm
            provider=providers[published_arm],
            witness_states=witness_states, verbose=verbose,
            **(gate_kwargs or {}))
        (directory / "acceptance.json").write_text(
            leaguesim.canonical_json(_plain(gate_report)) + "\n")

    record = {
        "schema_version": ISSUANCE_SCHEMA_VERSION,
        "season": season,
        "cutoff": str(state.cutoff),
        "observed_by": str(state.observed_by),
        "published_arm": published_arm,
        "arms": list(arms),
        "n_sims": int(n_sims),
        "n_particles": int(n_particles),
        "seed": int(seed),
        "chunk_size": int(chunk_size),
        "effective_posterior_hash": book.content_hash(),
        "bridge_hash": None if bridge is None else bridge.content_hash(),
        "n_played": len(state.played),
        "n_unplayed": len(state.unplayed),
        "n_unresolved": len(state.unresolved),
        "results_lag": bool(state.results_lag),
        "digests": {arm: run.digest() for arm, run in runs.items()},
        "numbers_digests": {arm: simcanary._numbers_digest(run)
                            for arm, run in runs.items()},
        "files": written,
        "gate_PASS": None if gate_report is None else bool(gate_report["PASS"]),
        "wall_seconds": round(time.perf_counter() - started, 2),
    }
    (directory / "issuance.json").write_text(
        leaguesim.canonical_json(record) + "\n")

    summary = summary_markdown(record, runs, gate_report)
    (directory / "summary.md").write_text(summary)

    return {**record, "directory": str(directory), "runs": runs,
            "gate": gate_report, "state": state, "summary": summary}


def _provider(arm: str, fit: FitBundle, bridge, state, cutoff, n_particles: int):
    """The arm, exactly as :class:`epl.simretro.ArchiveRunner` builds it."""
    if arm == "dc_native":
        return fit.book
    if arm == "dc_wdl_bridge":
        return bridge_mod.DCWDLProvider(fit.book, bridge)
    if arm == "elo_wdl_bridge":
        if fit.anchor is None:
            raise CliError(
                "the Elo arm needs the anchor the fit was built on; none was "
                "supplied with the fit bundle")
        anchor_state = fit.anchor.state(cutoff, list(state.clubs))
        history = (fit.anchor.history_frame(cutoff)
                   if hasattr(fit.anchor, "history_frame")
                   else fit.anchor.history)
        return bridge_mod.EloOutcomeProvider.fit(
            anchor_state, history,
            [state.fixtures[fid] for fid in sorted(state.fixtures)],
            bridge, n_particles=n_particles)
    raise CliError(f"unknown arm {arm!r}")


# ==========================================================================
# 3. the acceptance gate — one function per criterion, all of them fallible
# ==========================================================================

def _ok(name: str, passed: bool, detail: dict, note: str = "") -> dict:
    return {"name": name, "status": "PASS" if passed else "FAIL",
            "PASS": bool(passed), "detail": detail, "note": note}


def _skipped(name: str, why: str) -> dict:
    return {"name": name, "status": "SKIPPED", "PASS": False,
            "detail": {}, "note": why}


def check_clubs_and_fixtures(state, manifest) -> dict:
    """20 clubs, 380 fixtures, one ordered pair each, 38 matches per club."""
    problems: list[str] = []
    clubs = tuple(state.clubs)
    if len(clubs) != 20:
        problems.append(f"{len(clubs)} clubs, not 20")
    if set(clubs) != set(manifest.clubs):
        problems.append("the state's clubs are not the manifest's clubs")
    if len(state.fixtures) != 380:
        problems.append(f"{len(state.fixtures)} fixtures, not 380")

    pairs = [(f.home_key, f.away_key) for f in state.fixtures.values()]
    if len(set(pairs)) != len(pairs):
        problems.append("a home/away pair appears more than once")
    expected = {(h, a) for h in clubs for a in clubs if h != a}
    if set(pairs) != expected:
        problems.append("the fixture list is not a complete double round-robin")

    counts = {c: 0 for c in clubs}
    home = {c: 0 for c in clubs}
    for h, a in pairs:
        if h in counts:
            counts[h] += 1
            home[h] += 1
        if a in counts:
            counts[a] += 1
    wrong = sorted(c for c, n in counts.items() if n != 38)
    if wrong:
        problems.append(f"{wrong} do not play 38 matches")
    lopsided = sorted(c for c, n in home.items() if n != 19)
    if lopsided:
        problems.append(f"{lopsided} do not play 19 at home")

    played, unplayed = set(state.played), set(state.unplayed)
    if played & unplayed:
        problems.append("a fixture is both played and unplayed")
    if played | unplayed != set(state.fixtures):
        problems.append("played and unplayed do not cover the fixture list")

    return _ok("clubs_and_fixtures", not problems, {
        "n_clubs": len(clubs), "n_fixtures": len(state.fixtures),
        "n_played": len(played), "n_unplayed": len(unplayed),
        "problems": problems,
    }, "the season snapshot is a complete, well-formed double round-robin")


def check_promoted_complete(run: leaguesim.SimRun, manifest) -> dict:
    """Every promoted club is in the matrix and plays a whole season."""
    plan = run.plan
    index = {club: i for i, club in enumerate(plan.clubs)}
    promoted = tuple(manifest.promoted)
    problems: list[str] = []
    per_club: dict[str, int] = {}
    row_sums: dict[str, float] = {}

    home = np.bincount(plan.home_idx, minlength=len(plan.clubs))
    for club in promoted:
        if club not in index:
            problems.append(f"{club} never reached the simulated table")
            continue
        i = index[club]
        per_club[club] = int(plan.fixtures_per_club[i])
        row_sums[club] = float(run.matrix[i].sum())
        if per_club[club] != 38:
            problems.append(f"{club} plays {per_club[club]} matches, not 38")
        if int(home[i]) != 19:
            problems.append(f"{club} plays {int(home[i])} at home, not 19")
        if abs(row_sums[club] - 1.0) > 1e-8:
            problems.append(f"{club}'s position row sums to {row_sums[club]:.9f}")
        if float(run.matrix[i].min()) < -1e-12:
            problems.append(f"{club} holds negative position mass")

    return _ok("promoted_complete", not problems, {
        "promoted": list(promoted),
        "fixtures_per_club": per_club,
        "matrix_row_sums": row_sums,
        "expected_relegations": float(sum(
            run.consequences[c]["relegated"]["p"] for c in promoted
            if c in run.consequences)),
        "problems": problems,
    }, "a promoted club is the case the cold-start path exists for; if one is "
       "missing from the table the fit never priced it")


def check_cutoff_table(state) -> dict:
    """Played results plus known adjustments must BE ``table_so_far``."""
    rebuilt = {c: {"played": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0}
               for c in state.clubs}
    for fid, (hg, ag) in state.played.items():
        fixture = state.fixtures[fid]
        h, a = fixture.home_key, fixture.away_key
        for club, scored, conceded in ((h, hg, ag), (a, ag, hg)):
            row = rebuilt[club]
            row["played"] += 1
            row["gf"] += int(scored)
            row["ga"] += int(conceded)
            row["w" if scored > conceded else "d" if scored == conceded else "l"] += 1

    adjustments = dict(state.adjustments_known or {})
    mismatched: list[str] = []
    for club, row in rebuilt.items():
        actual = state.table_so_far.get(club)
        if actual is None:
            mismatched.append(club)
            continue
        expected_pts = 3 * row["w"] + row["d"] + int(adjustments.get(club, 0))
        if (actual.played != row["played"] or actual.w != row["w"]
                or actual.d != row["d"] or actual.l != row["l"]
                or actual.gf != row["gf"] or actual.ga != row["ga"]
                or actual.adjustment != int(adjustments.get(club, 0))
                or actual.pts != expected_pts
                or actual.gd != row["gf"] - row["ga"]):
            mismatched.append(club)

    n_played = len(state.played)
    return _ok("cutoff_table", not mismatched, {
        "n_played": n_played,
        "non_degenerate": n_played > 0,
        "adjustments_known": adjustments,
        "mismatched": sorted(mismatched),
        "total_points": sum(r.pts for r in state.table_so_far.values()),
    }, "an opener has no results to reconstruct, so this check is only "
       "non-degenerate where a witness state with played matches is supplied")


def check_mc_uncertainty(run: leaguesim.SimRun) -> dict:
    """Every published headline carries a finite cluster-by-particle SE."""
    problems: list[str] = []
    worst = 0.0
    for club, markets in run.consequences.items():
        for market, cell in markets.items():
            for key in ("p", "se", "outer", "inner"):
                if key not in cell:
                    problems.append(f"{club} {market}: no {key}")
                    continue
                value = float(cell[key])
                if not np.isfinite(value):
                    problems.append(f"{club} {market}: {key} is not finite")
            if "se" in cell and np.isfinite(float(cell["se"])):
                worst = max(worst, float(cell["se"]))

    matrix_se = np.asarray(run.matrix_se, float)
    if matrix_se.shape != np.asarray(run.matrix).shape:
        problems.append("matrix_se does not have the matrix's shape")
    if not np.all(np.isfinite(matrix_se)):
        problems.append("the position matrix carries a non-finite standard error")
    for club, row in run.points_summary.items():
        if "se" not in row or not np.isfinite(float(row["se"])):
            problems.append(f"{club}: the points mean has no standard error")

    mc = run.mc
    for key in ("cluster", "outer", "inner", "cluster_se_max",
                "identity_max_abs_error"):
        if key not in mc or not np.isfinite(float(mc[key])):
            problems.append(f"mc.{key} missing or not finite")
    if float(mc.get("identity_max_abs_error", 1.0)) > 1e-9:
        problems.append("the outer/inner decomposition does not sum to the total")

    return _ok("mc_uncertainty", not problems, {
        "worst_market_se": worst,
        "matrix_se_max": float(matrix_se.max()) if matrix_se.size else 0.0,
        "outer": float(mc.get("outer", float("nan"))),
        "inner": float(mc.get("inner", float("nan"))),
        "identity_max_abs_error": float(mc.get("identity_max_abs_error",
                                               float("nan"))),
        "problems": problems,
    }, "Monte-Carlo error only; it says nothing about model error")


def check_limitations(text: str, run: leaguesim.SimRun) -> dict:
    """The note exists, has every section, and carries THIS run's numbers."""
    missing = [s for s in LIMITATIONS_SECTIONS if s not in text]
    missing += [p for p in LIMITATIONS_PHRASES if p not in text]

    n_clubs = len(run.clubs)
    playoff = float(run.unresolved_playoff_mass.sum() / n_clubs)
    multiway = float(run.unresolved_multiway_mass.sum() / n_clubs)
    numbers = {
        "unresolved_playoff_mass": f"{playoff:.5f}",
        "unresolved_multiway_mass": f"{multiway:.5f}",
        "n_played": str(run.envelope["n_played"]),
        "n_unplayed": str(run.envelope["n_unplayed"]),
        "tiebreak_rule_id": run.envelope["tiebreak_rule_id"],
    }
    absent = sorted(k for k, v in numbers.items() if v not in text)

    return _ok("limitations", not missing and not absent, {
        "missing_sections": missing,
        "numbers_not_found": absent,
        "unresolved_playoff_mass_per_club": playoff,
        "unresolved_multiway_mass_per_club": multiway,
        "chars": len(text),
    }, "auto-filled from the run, not a template a human forgot to complete")


def check_reproducibility(arm: str, state, provider, *, n_sims: int, seed: int,
                          chunk_size: int, n_particles: int, season=None,
                          boundaries=None, rule_id: str | None = None,
                          parallel_workers: int = 2) -> dict:
    """Serial == chunk-concatenation == parallel, and a different seed moves it.

    The chunking is part of the run's DEFINITION, not a scheduling artefact:
    every stream is keyed by ``(chunk_index, fixture_ordinal)`` (plan v2 D14),
    so two runs at different chunk sizes are different runs and are *supposed*
    to differ. What must agree is the same specification computed three ways —
    in one process, chunk by chunk by hand, and across processes.

    The seed control is the positive half: without it "the runs agree" is also
    what a sampler that ignored its uniforms would report.
    """
    import concurrent.futures as cf

    chunk_size = int(chunk_size) if 0 < int(chunk_size) <= n_sims else int(n_sims)
    kwargs = dict(season=season, boundaries=boundaries, rule_id=rule_id,
                  n_particles=n_particles, chunk_size=chunk_size)

    serial = leaguesim.simulate(arm, state, provider, n_sims, seed, **kwargs)
    repeat = leaguesim.simulate(arm, state, provider, n_sims, seed, **kwargs)
    control = leaguesim.simulate(arm, state, provider, n_sims, seed + 1, **kwargs)

    # the run IS the concatenation of its chunks
    resolved = leaguesim.resolve_provider(arm, provider)
    chunks = [leaguesim.simulate_chunk(resolved, serial.plan, i)
              for i in range(serial.plan.n_chunks)]
    stacked = np.concatenate([c.scorelines for c in chunks], axis=0)
    concatenation_ok = bool(
        stacked.tobytes() == serial.retained_rows.scorelines.tobytes())

    parallel_digest = None
    parallel_error = None
    if parallel_workers and serial.plan.n_chunks > 1:
        try:
            with cf.ProcessPoolExecutor(max_workers=parallel_workers) as pool:
                parallel = leaguesim.simulate(arm, state, provider, n_sims, seed,
                                              executor=pool, **kwargs)
            parallel_digest = simcanary._numbers_digest(parallel)
        except Exception as exc:                            # pragma: no cover
            parallel_error = f"{type(exc).__name__}: {exc}"

    serial_digest = simcanary._numbers_digest(serial)
    repeat_digest = simcanary._numbers_digest(repeat)
    control_digest = simcanary._numbers_digest(control)

    deterministic = serial_digest == repeat_digest
    parallel_ok = parallel_digest is None or parallel_digest == serial_digest
    moved = control_digest != serial_digest
    passed = bool(deterministic and concatenation_ok and parallel_ok and moved
                  and parallel_error is None)

    return _ok("serial_equals_chunked", passed, {
        "n_sims": int(n_sims),
        "chunk_size": chunk_size,
        "n_chunks": int(serial.plan.n_chunks),
        "serial_digest": serial_digest,
        "repeat_digest": repeat_digest,
        "parallel_digest": parallel_digest,
        "parallel_workers": int(parallel_workers),
        "parallel_error": parallel_error,
        "seed_control_digest": control_digest,
        "deterministic": bool(deterministic),
        "chunk_concatenation_matches": concatenation_ok,
        "parallel_equals_serial": bool(parallel_ok),
        "seed_control_changed": bool(moved),
    }, "the same specification computed serially, chunk by chunk and across "
       "processes gives the same bytes; a different seed does not")


def check_tiebreak_oracle(*, test_path: str = "epl/tests/test_table.py",
                          timeout: int = 900) -> dict:
    """The T3 ladder suite, run as itself rather than described."""
    cmd = [sys.executable, "-m", "pytest", test_path, "-q"]
    env_note = "PYTHONPATH=src:."
    try:
        proc = subprocess.run(cmd, cwd=paths.REPO_ROOT, capture_output=True,
                              text=True, timeout=timeout,
                              env=_subprocess_env())
    except Exception as exc:                                # pragma: no cover
        return _ok("tiebreak_oracle", False, {"error": repr(exc)}, env_note)
    tail = (proc.stdout or proc.stderr).strip().splitlines()
    return _ok("tiebreak_oracle", proc.returncode == 0, {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "summary": tail[-1] if tail else "",
    }, env_note)


def check_repo_untouched(*, base: str = "main") -> dict:
    """``git diff --stat <base> -- src scripts`` must print nothing."""
    proc = _git(["diff", "--stat", base, "--", "src", "scripts"])
    if proc is None:                                        # pragma: no cover
        return _ok("src_scripts_untouched", False, {"error": "git unavailable"})
    clean = proc.returncode == 0 and not proc.stdout.strip()
    return _ok("src_scripts_untouched", clean, {
        "base": base,
        "returncode": proc.returncode,
        "diff": proc.stdout.strip(),
    }, "the frozen stack is imported read-only; nothing under src/ or scripts/ "
       "is written by this package")


def check_lock(*, script: str = "scripts/oa_lock.py", timeout: int = 900) -> dict:
    """The preregistration lock chain still verifies."""
    cmd = [sys.executable, script]
    try:
        proc = subprocess.run(cmd, cwd=paths.REPO_ROOT, capture_output=True,
                              text=True, timeout=timeout, env=_subprocess_env())
    except Exception as exc:                                # pragma: no cover
        return _ok("lock_valid", False, {"error": repr(exc)})
    first = (proc.stdout or "").strip().splitlines()
    head = first[0] if first else ""
    return _ok("lock_valid", head.strip() == "LOCK VALID", {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "first_line": head,
    }, "nothing polls this chain; it is verified after every commit")


def _subprocess_env() -> dict:
    import os
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    src = str(paths.REPO_ROOT / "src")
    root = str(paths.REPO_ROOT)
    parts = [src, root] + ([existing] if existing else [])
    env["PYTHONPATH"] = ":".join(parts)
    return env


def _git(args: list[str]):
    try:
        return subprocess.run(["git", *args], cwd=paths.REPO_ROOT,
                              capture_output=True, text=True, timeout=120)
    except Exception:                                       # pragma: no cover
        return None


def acceptance_gate(*, run: leaguesim.SimRun, state, manifest, book=None,
                    post=None, limitations: str = "", provider=None,
                    parity_fixtures=None,
                    witness_states: Sequence[Any] = (),
                    tiebreak_oracle: bool = True, repo: bool = True,
                    repro_n_sims: int | None = None,
                    repro_chunk: int | None = None,
                    verbose: bool = False) -> dict:
    """Every criterion of plan v2 T9, each one able to fail.

    A criterion that cannot be evaluated comes back ``SKIPPED`` and the gate
    does not pass. Exceptions inside a check are recorded as failures rather
    than propagated: an operator reading a gate wants the whole list.
    """
    criteria: dict[str, dict] = {}

    def _run(name: str, fn):
        if verbose:
            print(f"[gate] {name}", flush=True)
        try:
            criteria[name] = fn()
        except Exception as exc:
            criteria[name] = _ok(name, False, {"error": f"{type(exc).__name__}: {exc}"})

    _run("clubs_and_fixtures", lambda: check_clubs_and_fixtures(state, manifest))
    _run("promoted_complete", lambda: check_promoted_complete(run, manifest))

    if book is None:
        criteria["marginal_parity"] = _skipped(
            "marginal_parity", "no particle book was supplied")
    elif run.arm != "dc_native":
        # The check asks whether the SAMPLER reproduces the published
        # Dixon-Coles per-fixture law. A bridge arm samples a different law on
        # purpose (plan v2 D18), so running it here would report a difference
        # that is the design rather than a defect.
        criteria["marginal_parity"] = _skipped(
            "marginal_parity",
            f"arm {run.arm!r} samples an outcome model plus the empirical "
            "scoreline bridge, not the DC per-fixture grid; per-fixture parity "
            "with the published DC forecast is only defined for dc_native")
    else:
        _run("marginal_parity", lambda: _parity(book, post, run, parity_fixtures))

    if tiebreak_oracle:
        _run("tiebreak_oracle", check_tiebreak_oracle)
    else:
        criteria["tiebreak_oracle"] = _skipped(
            "tiebreak_oracle", "not requested for this gate run")

    _run("cutoff_table", lambda: _cutoff_table(state, witness_states))
    _run("matrix_and_markets", lambda: _coherence(run))

    repro_provider = provider if provider is not None else book
    if repro_provider is None:
        criteria["serial_equals_chunked"] = _skipped(
            "serial_equals_chunked", "no provider was supplied to re-run with")
    else:
        n = int(repro_n_sims or run.plan.n_sims)
        chunk = int(repro_chunk or run.plan.chunk_size)
        _run("serial_equals_chunked", lambda: check_reproducibility(
            run.arm, state, repro_provider, n_sims=n, seed=run.plan.seed,
            chunk_size=chunk, n_particles=run.plan.n_particles,
            boundaries=run.plan.boundaries, rule_id=run.plan.rule_id))

    _run("mc_uncertainty", lambda: check_mc_uncertainty(run))
    _run("limitations", lambda: check_limitations(limitations, run))

    if repo:
        _run("src_scripts_untouched", check_repo_untouched)
        _run("lock_valid", check_lock)
    else:
        criteria["src_scripts_untouched"] = _skipped(
            "src_scripts_untouched", "not requested for this gate run")
        criteria["lock_valid"] = _skipped(
            "lock_valid", "not requested for this gate run")

    ordered = {name: criteria[name] for name in GATE_CRITERIA}
    failed = [n for n, c in ordered.items() if c["status"] == "FAIL"]
    skipped = [n for n, c in ordered.items() if c["status"] == "SKIPPED"]
    return {
        "arm": run.arm,
        "season": run.plan.season,
        "cutoff": run.plan.cutoff,
        "criteria": ordered,
        "failed": failed,
        "skipped": skipped,
        "PASS": not failed and not skipped,
        "note": ("A SKIPPED criterion is not a passing criterion: the gate only "
                 "passes when every one of the eleven ran and held."),
    }


def _parity(book, post, run, fixtures) -> dict:
    report = simcanary.marginal_parity(book, post, run, fixtures)
    return _ok("marginal_parity", bool(report["PASS"]), report,
               "simulated per-fixture marginals ARE the published per-fixture "
               "forecast, at 4 cluster-by-particle standard errors")


def _coherence(run) -> dict:
    report = simcanary.coherence(run)
    return _ok("matrix_and_markets", bool(report["PASS"]), report,
               "rows and columns each sum to 1 and every consequence market is "
               "its own column sum")


def _cutoff_table(state, witness_states) -> dict:
    primary = check_cutoff_table(state)
    witnesses = [check_cutoff_table(w) for w in witness_states]
    problems = [] if primary["PASS"] else ["the issuance state"]
    problems += [f"witness {i}" for i, w in enumerate(witnesses) if not w["PASS"]]
    non_degenerate = bool(primary["detail"]["non_degenerate"]
                          or any(w["detail"]["non_degenerate"] for w in witnesses))
    detail = dict(primary["detail"])
    detail["witnesses"] = [w["detail"] for w in witnesses]
    detail["non_degenerate_anywhere"] = non_degenerate
    detail["problems"] = problems
    return _ok("cutoff_table", not problems, detail,
               primary["note"] if non_degenerate else
               "WARNING: every state checked has zero played matches, so this "
               "criterion is consistent but carries no evidence")


# ==========================================================================
# 4. re-checking a written issuance
# ==========================================================================

def check_issuance(directory, *, verbose: bool = True) -> dict:
    """Re-run a written issuance from its own bundle and demand it reproduces.

    Rebuilds the season state from the snapshot at the recorded cutoff, reloads
    the persisted particle book, re-runs the published arm at the recorded seed
    and N, and compares the number digest with the one the issuance wrote. Then
    the T6 checks: coherence, and per-fixture marginal parity against the book's
    own published law.
    """
    directory = Path(directory)
    record = json.loads((directory / "issuance.json").read_text())
    arm = record["published_arm"]
    if arm != "dc_native":
        return {"PASS": False, "detail": {
            "error": f"published arm {arm!r} cannot be rebuilt from the bundle "
                     "alone: only the DC-native arm is fully described by the "
                     "particle book"}}

    season_obj = season_mod.Season.load(record["season"])
    state = season_obj.at(record["cutoff"], record["observed_by"])
    book = particles.ParticleBook.load(directory / "particles.npz")

    if verbose:
        print(f"[check] re-running {arm} at {record['cutoff']} "
              f"(N={record['n_sims']}, seed={record['seed']})", flush=True)
    run = leaguesim.simulate(
        arm, state, book, record["n_sims"], record["seed"],
        chunk_size=record["chunk_size"], season=season_obj,
        boundaries=season_obj.manifest.material_boundaries,
        rule_id=season_obj.manifest.tiebreak_rule_id,
        n_particles=record["n_particles"])

    digest = simcanary._numbers_digest(run)
    expected = record["numbers_digests"][arm]
    matches = digest == expected
    coherence = simcanary.coherence(run)
    try:
        parity = simcanary.marginal_parity(book, None, run)
    except Exception as exc:
        parity = {"PASS": False, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "PASS": bool(matches and coherence["PASS"] and parity["PASS"]),
        "directory": str(directory),
        "arm": arm,
        "detail": {
            "digest_matches": bool(matches),
            "recorded_digest": expected,
            "recomputed_digest": digest,
            "book_hash": book.content_hash(),
            "recorded_book_hash": record["effective_posterior_hash"],
        },
        "coherence": coherence,
        "marginal_parity": parity,
    }


# ==========================================================================
# 5. ingest
# ==========================================================================

def ingest_results(*, season: str = DEFAULT_SEASON, root=season_mod.SEASON_ROOT,
                   from_openfootball: bool = False,
                   openfootball_file=None, openfootball_text: str | None = None,
                   manual_file=None, observed_at=None,
                   write: bool = False, verbose: bool = True) -> list[dict]:
    """Append results to the season ledger. Idempotent; a conflict STOPs.

    Exactly one source: the network (``from_openfootball``), a local file in
    openfootball's own format (``openfootball_file`` / ``openfootball_text`` —
    the same parser and the same conflict rule, without the fetch), or a JSONL
    file of hand-entered ledger rows (``manual_file``).
    """
    season_obj = season_mod.Season.load(season, root=root)
    chosen = [bool(from_openfootball), openfootball_file is not None,
              openfootball_text is not None, manual_file is not None]
    if sum(chosen) != 1:
        raise CliError(
            "choose exactly one source: --from-openfootball, "
            "--openfootball-file or --manual")

    observed_at = pd.Timestamp.now() if observed_at is None else observed_at

    if manual_file is not None:
        rows = _manual_rows(Path(manual_file), season_obj, observed_at)
        if write and rows:
            season_mod._append_jsonl(
                Path(root) / season_mod.season_dir_name(season)
                / season_mod.RESULTS_FILENAME, rows)
        if verbose:
            print(f"[ingest] {len(rows)} manual row(s)"
                  f"{' written' if write else ' (dry run)'}", flush=True)
        return rows

    if from_openfootball:
        text = _fetch_openfootball(season_obj)
    elif openfootball_file is not None:
        text = Path(openfootball_file).read_text(encoding="utf-8")
    else:
        text = openfootball_text

    source_id = season_mod.openfootball_source_id(text)
    rows = season_obj.ingest_openfootball_results(
        text, observed_at=observed_at, source_id=source_id, write=write)
    if verbose:
        print(f"[ingest] {len(rows)} row(s) from {source_id}"
              f"{' written' if write else ' (dry run)'}", flush=True)
    return rows


def _manual_rows(path: Path, season_obj, observed_at) -> list[dict]:
    """Validate hand-entered ledger rows against the fixture list."""
    fixtures = {f.fixture_id for f in season_obj.fixtures}
    existing = {r["fixture_id"]: (int(r["hg"]), int(r["ag"]))
                for r in season_obj.results
                if r.get("status") is None and r.get("hg") is not None}
    observed = season_mod._timestamp(observed_at).isoformat()

    out: list[dict] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        fid = str(row.get("fixture_id", ""))
        if fid not in fixtures:
            raise season_mod.SeasonError(
                f"{path}:{lineno}: {fid!r} is not a fixture of "
                f"{season_obj.season}")
        if fid in seen:
            raise season_mod.ResultConflict(f"{path}: {fid} appears twice")
        seen.add(fid)
        try:
            hg, ag = int(row["hg"]), int(row["ag"])
        except (KeyError, TypeError, ValueError) as exc:
            raise season_mod.SeasonError(
                f"{path}:{lineno}: {fid} has no integer hg/ag") from exc
        if hg < 0 or ag < 0:
            raise season_mod.SeasonError(f"{path}:{lineno}: {fid} has negative goals")
        if fid in existing:
            if existing[fid] != (hg, ag):
                raise season_mod.ResultConflict(
                    f"{fid}: ledger holds {existing[fid][0]}-{existing[fid][1]}, "
                    f"{path} says {hg}-{ag}. STOP: check which is right and "
                    "correct the ledger deliberately.")
            continue
        if not row.get("date_played"):
            raise season_mod.SeasonError(f"{path}:{lineno}: {fid} has no date_played")
        out.append({
            "fixture_id": fid,
            "date_played": str(row["date_played"]),
            "hg": hg, "ag": ag,
            "source": "manual",
            "observed_at": str(row.get("observed_at") or observed),
            "note": str(row.get("note", "")),
        })
    out.sort(key=lambda r: r["fixture_id"])
    return out


def _fetch_openfootball(season_obj) -> str:
    """Download the season's openfootball file (CC0) and verify it is one."""
    import requests

    source = season_obj.manifest.raw.get("fixtures_source") or {}
    url = source.get("url")
    if not url:
        raise CliError(
            f"{season_obj.season}: the manifest names no fixtures_source.url to "
            "fetch from")
    response = requests.get(url, timeout=30,
                            headers={"User-Agent": "epl-table-simulator"})
    response.raise_for_status()
    text = response.text
    if len(text) < 1000 or "Matchday" not in text and "Regular Season" not in text:
        raise CliError(f"{url} did not return an openfootball league file")
    return text


# ==========================================================================
# 6. the summary a human reads
# ==========================================================================

def summary_markdown(record: dict, runs: dict, gate: dict | None) -> str:
    published = runs[record["published_arm"]]
    clubs = published.clubs
    order = sorted(clubs, key=lambda c: -published.consequences[c]["champion"]["p"])
    relegation_order = sorted(clubs,
                              key=lambda c: -published.consequences[c]["relegated"]["p"])

    def line(club, market):
        cell = published.consequences[club][market]
        return f"{cell['p'] * 100:5.1f}% ± {cell['se'] * 100:4.2f}"

    lines = [
        f"# {record['season']} table forecast — cutoff {record['cutoff'][:10]}",
        "",
        f"Published arm **{record['published_arm']}**; arms run: "
        f"{', '.join(record['arms'])}. N = {record['n_sims']:,} simulated "
        f"seasons over S = {record['n_particles']:,} posterior draws, "
        f"seed {record['seed']}.",
        "",
        f"Fixtures played and conditioned on: **{record['n_played']}**; "
        f"simulated: **{record['n_unplayed']}**; unresolved: "
        f"**{record['n_unresolved']}**; results-lag flag: "
        f"**{record['results_lag']}**.",
        "",
        "Every percentage carries a Monte-Carlo standard error "
        "(cluster-by-particle). It is Monte-Carlo error only: it does not "
        "describe model error. Positions are positions — \"top 4\", \"top 5\" "
        "and \"top 7\" are not claims about qualification for any competition. "
        "No betting content, no odds, no market comparison.",
        "",
        "## Title",
        "",
        "| Club | P(champion) | P(top 4) | E[points] |",
        "| --- | ---: | ---: | ---: |",
    ]
    for club in order[:8]:
        pts = published.points_summary[club]
        lines.append(f"| {club} | {line(club, 'champion')} | "
                     f"{line(club, 'top4')} | {pts['mean']:.1f} ± {pts['se']:.2f} |")

    lines += ["", "## Relegation", "",
              "| Club | P(relegated) | E[points] |", "| --- | ---: | ---: |"]
    for club in relegation_order[:8]:
        pts = published.points_summary[club]
        lines.append(f"| {club} | {line(club, 'relegated')} | "
                     f"{pts['mean']:.1f} ± {pts['se']:.2f} |")

    cut = published.cut_lines
    lines += ["", "## Cut lines (points, from the simulated seasons)", "",
              "| Line | 5% | 50% | 95% |", "| --- | ---: | ---: | ---: |"]
    for name, row in cut.items():
        lines.append(f"| {name} | {row.get('q05', '')} | {row.get('q50', '')} "
                     f"| {row.get('q95', '')} |")

    lines += ["", "## Acceptance gate", ""]
    if gate is None:
        lines.append("Not run for this issuance.")
    else:
        lines += [f"**{'PASS' if gate['PASS'] else 'NOT PASSED'}** — "
                  f"{len(gate['failed'])} failed, {len(gate['skipped'])} skipped.",
                  "", "| Criterion | Status | Note |", "| --- | --- | --- |"]
        for name, cell in gate["criteria"].items():
            note = cell.get("note", "").replace("\n", " ")
            lines.append(f"| `{name}` | {cell['status']} | {note[:90]} |")

    lines += ["", "## Provenance", "",
              f"- effective posterior: `{record['effective_posterior_hash']}`",
              f"- bridge: `{record['bridge_hash']}`",
              f"- digests: " + ", ".join(f"`{a}`={d[:12]}"
                                         for a, d in record["digests"].items()),
              f"- wall: {record['wall_seconds']}s",
              "",
              "See `limitations.md` beside this file. Nothing here has been "
              "scored against the preregistered retrospective; until it has, "
              "this is a demonstration of the pipeline, not an accuracy claim.",
              ""]
    return "\n".join(lines)


def _plain(obj):
    """JSON-safe: numpy scalars and arrays out, plain Python in."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return [_plain(v) for v in obj.tolist()]
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj)
    return obj


# ==========================================================================
# 7. the CLI
# ==========================================================================

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m epl.simcli",
        description="EPL league-table simulator: forecast, ingest, retro, check.")
    sub = parser.add_subparsers(dest="command", required=True)

    f = sub.add_parser("forecast", help="issue one forecast")
    f.add_argument("--season", default=DEFAULT_SEASON)
    f.add_argument("--cutoff", required=True)
    f.add_argument("--arm", default=PUBLISHED_ARM, choices=list(ARMS))
    f.add_argument("--all-arms", action="store_true")
    f.add_argument("--n-sims", type=int, default=DEFAULT_N_SIMS)
    f.add_argument("--seed", type=int, default=DEFAULT_SEED)
    f.add_argument("--chunk-size", type=int, default=leaguesim.DEFAULT_CHUNK_SIZE)
    f.add_argument("--out-root", default=None)
    f.add_argument("--no-gate", action="store_true")
    f.add_argument("--skip-oracle", action="store_true",
                   help="skip the pytest ladder suite inside the gate")
    f.add_argument("--witness-season", default=None,
                   help="archive season used to make the cutoff-table check "
                        "non-degenerate at an opener (e.g. 2025/26)")
    f.add_argument("--witness-cutoff", default=None)

    i = sub.add_parser("ingest-results", help="append to the results ledger")
    i.add_argument("--season", default=DEFAULT_SEASON)
    i.add_argument("--root", default=str(season_mod.SEASON_ROOT))
    i.add_argument("--from-openfootball", action="store_true")
    i.add_argument("--openfootball-file", default=None,
                   help="a local file in openfootball's format (same parser and "
                        "same conflict rule as --from-openfootball, no network)")
    i.add_argument("--manual", default=None, help="JSONL of hand-entered rows")
    i.add_argument("--observed-at", default=None)
    i.add_argument("--write", action="store_true")

    r = sub.add_parser("retro", help="the preregistered retrospective (smoke)")
    r.add_argument("--smoke", action="store_true")
    r.add_argument("--n-sims", type=int, default=None)
    r.add_argument("--seed", type=int, default=DEFAULT_SEED)

    c = sub.add_parser("check", help="re-run and re-check a written issuance")
    c.add_argument("--directory", default=None)
    c.add_argument("--season", default=DEFAULT_SEASON)
    c.add_argument("--cutoff", default=None)
    c.add_argument("--out-root", default=None)

    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.command == "forecast":
            return _cmd_forecast(args)
        if args.command == "ingest-results":
            return _cmd_ingest(args)
        if args.command == "retro":
            return _cmd_retro(args)
        if args.command == "check":
            return _cmd_check(args)
    except (CliError, season_mod.SeasonError, leaguesim.SimError,
            particles.ParticleError, simcanary.CanaryError) as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 1                                                # pragma: no cover


def _cmd_forecast(args) -> int:
    arms = ARMS if args.all_arms else (args.arm,)
    witnesses = []
    if args.witness_season:
        from epl import baseline
        witnesses.append(season_mod.archive_season_state(
            baseline.load_matches(), args.witness_season,
            args.witness_cutoff or args.cutoff,
            require_verified_adjustments=False))

    gate_kwargs = {"tiebreak_oracle": not args.skip_oracle}
    issue = forecast(season=args.season, cutoff=args.cutoff, arms=arms,
                     n_sims=args.n_sims, seed=args.seed,
                     chunk_size=args.chunk_size, out_root=args.out_root,
                     gate=not args.no_gate, gate_kwargs=gate_kwargs,
                     witness_states=witnesses, verbose=True)
    print(f"[forecast] wrote {issue['directory']}")
    if issue["gate"] is not None:
        print(f"[forecast] acceptance gate: "
              f"{'PASS' if issue['gate']['PASS'] else 'NOT PASSED'} "
              f"(failed: {issue['gate']['failed'] or 'none'}; "
              f"skipped: {issue['gate']['skipped'] or 'none'})")
        return 0 if issue["gate"]["PASS"] else 3
    return 0


def _cmd_ingest(args) -> int:
    rows = ingest_results(
        season=args.season, root=Path(args.root),
        from_openfootball=args.from_openfootball,
        openfootball_file=args.openfootball_file, manual_file=args.manual,
        observed_at=args.observed_at, write=args.write, verbose=True)
    for row in rows:
        print(leaguesim.canonical_json(row))
    return 0


def _cmd_retro(args) -> int:
    from epl import simretro

    if not args.smoke:
        raise CliError(
            "the full seven-season retrospective is v1.1 R1 (plan v2 §6); "
            "T8 ships the harness and `retro --smoke`")
    argv = ["--smoke", "--seed", str(args.seed)]
    if args.n_sims is not None:
        argv += ["--n-sims", str(args.n_sims)]
    simretro._cli(argv)
    return 0


def _cmd_check(args) -> int:
    directory = (Path(args.directory) if args.directory
                 else _last_issuance(args.season, args.out_root, args.cutoff))
    report = check_issuance(directory, verbose=True)
    print(leaguesim.canonical_json(_plain(report)))
    return 0 if report["PASS"] else 4


def _last_issuance(season: str, out_root=None, cutoff=None) -> Path:
    root = (ISSUANCE_ROOT if out_root is None else Path(out_root)) \
        / season_mod.season_dir_name(season)
    if cutoff:
        return root / pd.Timestamp(cutoff).normalize().date().isoformat()
    candidates = sorted(p for p in root.glob("*") if (p / "issuance.json").exists())
    if not candidates:
        raise CliError(f"no issuance under {root}")
    return candidates[-1]


if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(main())
