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
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from epl import (bridge as bridge_mod, leaguesim, particles, paths,
                 season as season_mod, simbundle, simcanary, table as table_mod)

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
    # D11 v1.0.1 (owner ruling 2026-08-19, reports/epl_sim_amendments.md A1):
    # the flag list is part of the note, present even when it is empty.
    "## Truncation-flagged fixtures",
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

#: Phrases the note may NOT carry when the envelope flags a fixture. Every other
#: check here is a presence check over the whole document, and presence cannot
#: see a contradiction: a note that listed all five flagged ids AND said "no
#: fixture exceeds the flag threshold" satisfied every one of them, because the
#: required strings were all there and so was their denial. These are the
#: sentences `epl.leaguesim._truncation_section` emits when nothing is flagged,
#: so their appearance beside a flag is the note disagreeing with the run.
LIMITATIONS_TRUNCATION_DENIALS = (
    "no fixture exceeds the flag threshold",
    "every fixture is played at this cutoff",
    "there is no truncation tail to measure",
)

#: Bumped to -2 when `output_digests` and `provider_hashes` were added to the
#: record (round-2 Codex review of d6a1a91): `check` now holds the FILE a reader
#: downloads against the run it claims to describe, and refuses a provider that
#: is not the one the issuance recorded. An `epl-issuance-1` record carries
#: neither, and `check` reports them as unrecorded rather than failing it.
#:
#: Bumped to -3 when `arms_manifest_hash` was added (Codex review of 262ef98):
#: the bridge arms' rebuild is now anchored to the hashes RECORDED HERE rather
#: than only to what each sidecar says about itself, and the arms manifest is
#: the last of the three that had no anchor.
#:
#: ON -3 ALL THREE ARE MANDATORY for an arm that reads a sidecar (Codex review
#: of 04b26a2). Reporting a missing one as "unanchored" made the fail-closed
#: anchor downgradeable by deleting a line: a current record with
#: `arms_manifest_hash` removed sent `arms.json` back to being checked against
#: itself — the file an editor rewrites to make a doctored bridge look coherent
#: — and `check` still returned PASS. A -1 or -2 record predates the field and
#: keeps the leniency that exists for exactly that.
ISSUANCE_SCHEMA_VERSION = "epl-issuance-3"


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
    #: The completed-season archive (football-data). For a season in progress it
    #: has NO rows of that season — which is why it is not what the bridge is
    #: fitted on.
    matches: pd.DataFrame | None = None
    #: The frame the fit actually TRAINED on: the archive PLUS the target
    #: season's own observed results (plan v2 D5/D18). The empirical bridge must
    #: see every valid played match before the cutoff, and mid-season those
    #: include the results ledger's rows; feeding it `matches` alone would
    #: estimate P(scoreline | outcome) from a frame that stops at last season.
    training: pd.DataFrame | None = None
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
    # THE anchor's own resolution, not a second reading of the same file. The
    # ledger used to be normalised eagerly in `LiveAnchor.__init__` and the
    # whole normalised tuple handed here, which had two consequences: a row
    # filed AFTER this forecast — an unknown club, a status v1 does not model —
    # broke the construction and so broke every historical forecast that reruns
    # through it; and the fit's frame was filtered by one function while the Elo
    # walk was filtered by another. One call, behind the known-at bound, feeds
    # both.
    live_rows = anchor.visible_rows(cutoff, observed_by=observed_by)
    train, _ = live_training_frame(archive, live_rows, season, cutoff,
                                   observed_by=observed_by)

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
        book=book, post=post, anchor=anchor, matches=played, training=train,
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


def live_training_frame(archive, rows, season: str, cutoff, *, observed_by=None):
    """``(train, live_rows)`` — the frame a live fit trains on (plan v2 D5/D18).

    The archive plus the target season's OWN observed results, where "observed"
    is :func:`epl.liveanchor.visible_rows`'s bitemporal rule: played strictly
    before the cutoff DAY and known by ``observed_by``. A row dated on or after
    the cutoff is not in the frame, whatever the ledger says about it.

    Extracted from :func:`live_fit` so the point-in-time property can be tested
    without paying for a fit, and so the empirical bridge and the Dixon-Coles
    fit provably read the SAME frame: the bug this closes is a bridge fitted on
    the archive alone, which for a season in progress means a bridge that has
    never seen a match of the season it is pricing.
    """
    from epl import liveanchor
    from epl.schema import sort_for_walk_forward

    live_rows = liveanchor.visible_rows(rows, cutoff, observed_by)
    frames = [archive]
    if live_rows:
        frames.append(liveanchor.rows_to_frame(live_rows, season))
    return (sort_for_walk_forward(pd.concat(frames, ignore_index=True)),
            live_rows)


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

    # D18: the bridge is estimated from every valid played match before the
    # cutoff, and mid-season those INCLUDE the target season's results ledger.
    # `fit.training` is the frame the fit itself trained on; `fit.matches` is
    # the completed-season archive and has no rows of a season in progress.
    trained_on = fit.matches if fit.training is None else fit.training
    # D18: the bridge is estimated on the frame the FIT trained on, and an
    # explicit `matches` does not override it. `matches` is the archive a caller
    # hands in for the season state and the fit; `fit.training` is what the fit
    # actually saw, which mid-season is archive PLUS the season's own results
    # ledger. Letting `matches` win here re-opened the exact defect D18 closed —
    # a bridge that has never seen a match of the season it is pricing — and did
    # it only on the code path that passes `matches`, which is every retrospective
    # and every test.
    archive = trained_on
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

    # v1.1 R2: what a BRIDGE arm needs to be re-derived from this directory
    # alone — the fitted bridge's counts, the Elo arm's ratings and head, the
    # provisional/cold-start sets. New files beside the existing ones; nothing
    # already written changes, and a dc_native-only issuance writes none of them.
    simbundle.write_sidecars(directory, arms=arms, bridge=bridge, book=book,
                             providers=providers, fit_info=fit.info)

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
        # The anchor for the arms manifest: `check` holds `arms.json` against
        # this rather than against itself, so an editor who rewrites the arm
        # hashes there to make a doctored bridge look coherent is still refused.
        "arms_manifest_hash": simbundle.arms_manifest_hash(directory),
        "n_played": len(state.played),
        "n_unplayed": len(state.unplayed),
        "n_unresolved": len(state.unresolved),
        "results_lag": bool(state.results_lag),
        "digests": {arm: run.digest() for arm, run in runs.items()},
        "numbers_digests": {arm: simcanary._numbers_digest(run)
                            for arm, run in runs.items()},
        # the digest of the FILE each arm published, so `check` can hold the
        # bytes a reader downloads against the run they claim to describe
        "output_digests": {arm: output_numbers_digest(run.to_json())
                           for arm, run in runs.items()},
        "provider_hashes": {arm: provider.content_hash()
                            for arm, provider in providers.items()},
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
    # NEGATIVE is refused as well as non-finite. A standard error is a square
    # root and cannot be below zero; a negative one is a broken estimator, and
    # `abs()` or a print format would hide it while the number stayed wrong.
    # `outer` and `inner` are variance COMPONENTS, not standard errors — an
    # unbiased `outer = (between - within/k)/S` can legitimately come out
    # negative on a cell with almost no between-particle spread — so they are
    # required finite and are deliberately NOT required non-negative.
    for club, markets in run.consequences.items():
        for market, cell in markets.items():
            for key in ("p", "se", "outer", "inner"):
                if key not in cell:
                    problems.append(f"{club} {market}: no {key}")
                    continue
                value = float(cell[key])
                if not np.isfinite(value):
                    problems.append(f"{club} {market}: {key} is not finite")
                elif key in ("p", "se") and value < 0.0:
                    problems.append(f"{club} {market}: {key} is negative ({value:.3e})")
            if "se" in cell and np.isfinite(float(cell["se"])):
                worst = max(worst, float(cell["se"]))

    matrix_se = np.asarray(run.matrix_se, float)
    if matrix_se.shape != np.asarray(run.matrix).shape:
        problems.append("matrix_se does not have the matrix's shape")
    if not np.all(np.isfinite(matrix_se)):
        problems.append("the position matrix carries a non-finite standard error")
    elif np.any(matrix_se < 0.0):
        problems.append(
            f"the position matrix carries a negative standard error "
            f"(worst {float(matrix_se.min()):.3e})")
    for club, row in run.points_summary.items():
        if "se" not in row or not np.isfinite(float(row["se"])):
            problems.append(f"{club}: the points mean has no standard error")
        elif float(row["se"]) < 0.0:
            problems.append(f"{club}: the points mean's standard error is negative")

    mc = run.mc
    for key in ("cluster", "outer", "inner", "cluster_se_max",
                "identity_max_abs_error"):
        if key not in mc or not np.isfinite(float(mc[key])):
            problems.append(f"mc.{key} missing or not finite")
    for key in ("cluster", "cluster_se_max", "matrix_cluster_se_max"):
        if key in mc and np.isfinite(float(mc[key])) and float(mc[key]) < 0.0:
            problems.append(f"mc.{key} is a negative standard error")
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

    # D11 v1.0.1: the "Truncation-flagged fixtures" section is the one part of
    # the note whose CONTENT is a finding rather than a restatement, and the
    # heading check above passes on a section that says the opposite of what the
    # envelope holds. So the flagged ids and the max/mean/p90 are read out of
    # the envelope and required verbatim in the text — a note listing three
    # flagged fixtures for a run whose envelope flags five is a failure, and so
    # is one claiming "none" when the envelope names any.
    block = run.envelope.get("excluded_mass") or {}
    flagged_ids = [str(row["fixture"]) for row in (block.get("flagged") or [])]
    if block.get("measured") and block.get("n_fixtures"):
        for key in ("max", "mean", "p90"):
            value = block.get(key)
            if value is not None:
                numbers[f"excluded_mass_{key}"] = f"{float(value):.3g}"
        numbers["excluded_mass_n_fixtures"] = str(block["n_fixtures"])
    for fid in flagged_ids:
        numbers[f"flagged:{fid}"] = fid
    if block.get("measured") and block.get("n_fixtures") and not flagged_ids:
        numbers["flagged:none"] = "no fixture exceeds the flag threshold"

    absent = sorted(k for k, v in numbers.items() if v not in text)
    # ... and nothing may be listed as flagged that the envelope does not flag.
    listed = set(re.findall(r"`(\d{4}:[a-z0-9_]+:[a-z0-9_]+)`", text))
    extra = sorted(listed - set(flagged_ids))
    # ... and nothing may CLAIM there is nothing to flag when there is. Every
    # check above is a presence check over the whole document, so a note that
    # listed all five flagged ids AND said "no fixture exceeds the flag
    # threshold" satisfied every one of them: the required strings were all
    # there, and so was their contradiction. Presence cannot see a false
    # statement, so the false statement is named.
    denials = sorted(
        phrase for phrase in LIMITATIONS_TRUNCATION_DENIALS
        if flagged_ids and phrase in text)

    return _ok("limitations",
               not missing and not absent and not extra and not denials, {
        "missing_sections": missing,
        "numbers_not_found": absent,
        "flagged_in_note_not_in_envelope": extra,
        "denies_its_own_flags": denials,
        "flagged_fixtures": flagged_ids,
        "excluded_mass": {k: block.get(k) for k in
                          ("measured", "n_fixtures", "max", "mean", "p90")},
        "unresolved_playoff_mass_per_club": playoff,
        "unresolved_multiway_mass_per_club": multiway,
        "chars": len(text),
    }, "auto-filled from the run, not a template a human forgot to complete")


def _provider_identity_gap(provider, run) -> dict:
    """Where the provider's identity disagrees with the run's own envelope.

    The envelope records the identity of the provider that produced the run —
    `provider_hash` above all, and beside it `effective_posterior_hash`,
    `bridge_hash`, `widening_mode`, `max_goals`, and the arm's name. A provider
    that differs in any of them is not the thing the run was made with, whatever
    else it reproduces. Empty dict means agreement.

    `provider_hash` IS THE IDENTITY, and it was the one thing not compared. The
    described fields are a partial view — a `describe()` that raises, or a
    provider carrying none of those keys, matched everything by matching
    nothing, and the reproduction leg could then come back `None` (a different
    `repro_n_sims` or chunk size makes the direct digest comparison
    inapplicable) leaving a DIFFERENT bridge or Elo provider to self-reproduce
    and pass. `content_hash()` covers the whole provider by construction, so it
    is compared exactly, and a provider that cannot produce one is a gap rather
    than a pass.
    """
    gap: dict = {}
    if getattr(provider, "name", run.arm) != run.arm:
        gap["arm"] = [getattr(provider, "name", None), run.arm]

    recorded = run.envelope.get("provider_hash")
    if recorded is not None:
        try:
            mine = provider.content_hash()
        except Exception as exc:                            # pragma: no cover
            mine = f"unavailable: {type(exc).__name__}: {exc}"
        if mine != recorded:
            gap["provider_hash"] = [mine, recorded]

    describe = getattr(provider, "describe", None)
    described = {}
    if describe is not None:
        try:
            described = dict(describe())
        except Exception:                                   # pragma: no cover
            described = {}
    for key in ("effective_posterior_hash", "bridge_hash", "widening_mode",
                "max_goals"):
        if key not in described or key not in run.envelope:
            continue
        if described[key] != run.envelope[key]:
            gap[key] = [described[key], run.envelope[key]]
    return gap


def check_reproducibility(arm: str, state, provider, *, n_sims: int, seed: int,
                          chunk_size: int, n_particles: int, season=None,
                          boundaries=None, rule_id: str | None = None,
                          parallel_workers: int = 2, run=None) -> dict:
    """Serial == chunk-concatenation == parallel, and a different seed moves it.

    The chunking is part of the run's DEFINITION, not a scheduling artefact:
    every stream is keyed by ``(chunk_index, fixture_ordinal)`` (plan v2 D14),
    so two runs at different chunk sizes are different runs and are *supposed*
    to differ. What must agree is the same specification computed three ways —
    in one process, chunk by chunk by hand, and across processes.

    The seed control is the positive half: without it "the runs agree" is also
    what a sampler that ignored its uniforms would report.

    Pass `run` — the gate does — and two more things are required: the provider
    must BE the one the run's envelope names (`_provider_identity_gap`), and,
    when the specification matches the run's own, the serial re-run must
    reproduce the run's number digest. Without those the criterion measures the
    provider it was handed against itself and says nothing about the issuance.
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
    # `parallel_ok` used to be `digest is None or digest == serial`, which is
    # True whenever the parallel leg did not run — including when it was asked
    # for. Whether it was asked for is now recorded and required: with workers
    # and more than one chunk, a missing digest is a failure, not a pass.
    parallel_requested = bool(parallel_workers) and serial.plan.n_chunks > 1
    parallel_ran = parallel_digest is not None
    parallel_ok = bool(parallel_ran and parallel_digest == serial_digest) \
        if parallel_requested else True
    moved = control_digest != serial_digest

    # The gate's re-run must reproduce THE RUN BEING GATED, not merely itself.
    # Without this a caller could hand the gate any provider at all — a stub, a
    # different book, the wrong arm's provider — and the criterion would pass on
    # its own internal consistency while measuring nothing about the issuance.
    identity: dict = {}
    reproduces_run = None
    if run is not None:
        # `resolved`, not `provider`: a bare ParticleBook has no `describe`, and
        # comparing an object with no identity to an envelope would find no gap
        # in anything.
        identity = _provider_identity_gap(resolved, run)
        same_spec = (int(n_sims) == int(run.plan.n_sims)
                     and int(chunk_size) == int(run.plan.chunk_size)
                     and int(seed) == int(run.plan.seed))
        reproduces_run = (serial_digest == simcanary._numbers_digest(run)
                          if same_spec else None)

    passed = bool(deterministic and concatenation_ok and parallel_ok and moved
                  and parallel_error is None and not identity
                  and reproduces_run is not False)

    return _ok("serial_equals_chunked", passed, {
        "provider_identity_gap": identity,
        "reproduces_the_gated_run": reproduces_run,
        "parallel_requested": parallel_requested,
        "parallel_ran": parallel_ran,
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
    head = (first[0] if first else "").strip()
    # BOTH. The text alone passes a run that printed LOCK VALID and then died
    # on the next line — an exception after the first check, a partial walk of
    # the chain, a non-zero exit nobody read. The exit code alone passes a
    # script that was replaced by something that exits 0. Neither is the claim
    # being made, which is that the whole chain verified.
    passed = bool(proc.returncode == 0 and head == "LOCK VALID")
    return _ok("lock_valid", passed, {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "first_line": head,
        "stderr_tail": (proc.stderr or "").strip()[-400:],
    }, "nothing polls this chain; it is verified after every commit. The check "
       "requires exit 0 AND the text: either alone can be true while the chain "
       "did not verify")


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
            boundaries=run.plan.boundaries, rule_id=run.plan.rule_id, run=run))

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


#: The fields of ``output_<arm>.json`` that are NUMBERS rather than provenance.
#: The envelope is excluded on purpose: it carries wall time, git state and
#: package versions, which differ between the issuance and any re-run and say
#: nothing about whether the published numbers moved.
OUTPUT_NUMBER_FIELDS = (
    "arm", "season", "cutoff", "clubs", "positions", "n_sims", "n_particles",
    "matrix", "matrix_se", "shared_mass", "unresolved_playoff_mass",
    "unresolved_multiway_mass", "consequences", "points_summary", "cut_lines",
    "tie_diagnostics", "mc",
)


def output_numbers_digest(payload: dict) -> str:
    """sha256 over the published numbers of one ``output_<arm>.json`` payload.

    The point is to compare the FILE on disk with what a re-run produces, which
    `numbers_digests` in `issuance.json` cannot do: that digest is taken over
    live arrays, so it says the re-run agrees with the run — not that the file
    a reader downloads agrees with either. An edited matrix cell in
    `output_dc_native.json` left every existing check passing.
    """
    missing = [k for k in OUTPUT_NUMBER_FIELDS if k not in payload]
    if missing:
        raise CliError(f"the output payload is missing {missing}")
    return hashlib.sha256(leaguesim.canonical_json(
        {k: payload[k] for k in OUTPUT_NUMBER_FIELDS}).encode("utf-8")).hexdigest()


def _parity(book, post, run, fixtures) -> dict:
    """The note states what HAPPENED, not what a passing run would have said.

    It used to be a fixed sentence claiming `|Z| <= z*` and `p > floor`, written
    whether or not either held — and it travels into the issuance report through
    `summary_markdown`. A criterion that prints its own success text on failure
    is worse than one with no note: the gate's verdict says FAIL two columns
    away, and the sentence beside it says the thing passed.
    """
    report = simcanary.marginal_parity(book, post, run, fixtures)
    passed = bool(report["PASS"])
    if passed:
        leg1 = (f"per-cell |Z| <= z* = {report['z_star']:.4f} "
                f"(alpha = {report['alpha']:g}, family-wise in m) with "
                f"max |Z| = {report['max_sigma']:.3f}")
        head = ("simulated per-fixture marginals ARE the published per-fixture "
                f"forecast: {report['n_cells_compared']} cells, ")
    else:
        leg1 = (f"{len(report['failures'])} cell(s) exceed z* = "
                f"{report['z_star']:.4f} (alpha = {report['alpha']:g}, "
                f"family-wise in m); max |Z| = {report['max_sigma']:.3f}")
        head = ("simulated per-fixture marginals are NOT the published "
                f"per-fixture forecast: {report['n_cells_compared']} cells, ")
    # Leg 2 is a reported diagnostic (amendment A3-N1) and gates nothing, so it
    # is quoted with its own label rather than as a second criterion.
    return _ok("marginal_parity", passed, report,
               head + "amendment A3 leg 1 (A3-N1 demoted leg 2 to a "
               f"diagnostic) — {leg1}. Diagnostic only: chi2 = "
               f"{report['chi2']:.1f} on df = {report['df']}, "
               f"p = {report['p_value']:.3g} against the "
               f"{report['chi2_min_p']:g} reference.")


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

def check_issuance(directory, *, arms: Sequence[str] | None = None,
                   verbose: bool = True) -> dict:
    """Re-run a written issuance from its own bundle and demand it reproduces.

    EVERY arm the issuance carries, not only the published one (v1.1 R2). The
    season state is rebuilt from the snapshot at the recorded cutoff and the
    particle book is reloaded from ``particles.npz``; each arm's provider is
    then rebuilt — ``dc_native`` is the book itself, the two bridge arms come
    from :mod:`epl.simbundle`'s sidecars, re-derived rather than replayed — and
    re-run at the recorded seed, N and chunk size. The number digest must match
    what the issuance wrote.

    The rebuild is ANCHORED to the hashes this record holds — ``bridge_hash``,
    ``provider_hashes[arm]`` and ``arms_manifest_hash`` — and not only to what
    each sidecar says about itself. Doubling every count in ``bridge.json``
    leaves the cdf exactly where it was, so a cross-file edit that also rewrites
    that file's own hash and the arm hashes in ``arms.json`` is coherent
    everywhere inside the bundle; it is refused here because the bridge it
    rebuilds to is not the one the issuance recorded.

    On ``epl-issuance-3`` every one of those anchors is REQUIRED for an arm that
    reads a sidecar, and a record missing one FAILs that arm naming the field
    rather than reporting it unanchored — otherwise the strongest check in the
    bundle could be switched off by deleting a line from the record it is
    supposed to be held against.

    Three verdicts per arm, and only one of them is agreement:

    ``PASS``      rebuilt, re-run, same digest, coherent.
    ``FAIL``      rebuilt but the numbers moved, or a sidecar does not describe
                  what it claims (an edited cdf cell, a changed rating).
    ``REFUSED``   the arm cannot be rebuilt here at all — an issuance written
                  before the sidecars existed carries no record of the fitted
                  bridge or the Elo head. A refusal is NOT a pass, and the
                  overall verdict is False while one stands; narrowing to the
                  arms that can be rebuilt (`arms=...`) is an explicit act.

    Per-fixture marginal parity is a DC-native question — it asks whether the
    simulated marginals ARE ``draw_api``'s published grids — so it is reported
    ``NOT_APPLICABLE`` for an arm that samples another law on purpose, rather
    than being computed against a reference that is not that arm's.
    """
    directory = Path(directory)
    record = json.loads((directory / "issuance.json").read_text())
    requested = tuple(arms) if arms else tuple(record["arms"])
    unknown = [a for a in requested if a not in record["numbers_digests"]]
    if unknown:
        raise CliError(
            f"{directory} has no recorded digest for arm(s) {unknown}; it "
            f"carries {sorted(record['numbers_digests'])}")

    season_obj = season_mod.Season.load(record["season"])
    state = season_obj.at(record["cutoff"], record["observed_by"])
    book = particles.ParticleBook.load(directory / "particles.npz")

    results = {arm: _check_arm(arm, directory, record, season_obj, state, book,
                               verbose=verbose)
               for arm in requested}
    failed = [a for a, r in results.items() if r["status"] == "FAIL"]
    refused = [a for a, r in results.items() if r["status"] == "REFUSED"]
    published = record["published_arm"]
    headline = results.get(published, results[requested[0]])

    return {
        "PASS": not failed and not refused,
        "directory": str(directory),
        "arm": headline["arm"],
        "arms": results,
        "failed": failed,
        "refused": refused,
        "note": ("A REFUSED arm is not a passing arm: an issuance whose bridge "
                 "sidecars are absent cannot be shown to reproduce, and saying "
                 "so is the check working."),
        # the published arm's view, kept at the top level so a caller that only
        # ever asked about one arm still reads the same keys
        "detail": headline["detail"],
        "coherence": headline["coherence"],
        "marginal_parity": headline["marginal_parity"],
    }


def _check_arm(arm: str, directory: Path, record: dict, season_obj, state, book,
               *, verbose: bool) -> dict:
    """One arm, rebuilt from the bundle and re-run. Never raises."""
    # A provider that is not the one the issuance recorded cannot answer for
    # this arm, however well it reproduces itself.
    recorded_provider = (record.get("provider_hashes") or {}).get(arm)
    # LEGACY LENIENCY IS CONDITIONED ON THE SCHEMA, STRICTLY.
    # `output_digests` and `provider_hashes` arrived with `epl-issuance-2` and
    # are mandatory from there on. Treating "absent" as "no anchor to hold this
    # against" regardless of version meant a schema-2 or -3 record stripped of
    # both mandatory anchors passed exactly as an honest schema-1 record does:
    # the leniency that exists for records written before the fields existed was
    # extended to records that are missing them. Only `epl-issuance-1` may lack
    # them; anything else must carry them or FAIL.
    #
    # `bridge_hash` and `arms_manifest_hash` arrived with `epl-issuance-3` and
    # are the same story one version later (Codex review of 04b26a2). Reporting
    # them as "unanchored" on a -3 record made the fail-closed anchor
    # DOWNGRADEABLE: delete `arms_manifest_hash`, and the arms manifest — the
    # file whose arm hashes an editor has to rewrite to make a doctored bridge
    # look coherent — went back to being checked against itself, with `check`
    # still returning PASS. On -3 they are required, per BRIDGE ARM: `dc_native`
    # is the particle book and reads no sidecar, so neither hash exists for it
    # and demanding them would be a criterion no honest record could satisfy.
    schema = str(record.get("schema_version") or "")
    legacy = schema == "epl-issuance-1"
    mandatory: list[tuple[str, object]] = [
        ("provider_hashes", recorded_provider),
        ("output_digests", (record.get("output_digests") or {}).get(arm))]
    if not legacy and schema != "epl-issuance-2" and simbundle.ARM_SIDECARS.get(arm):
        mandatory += [("bridge_hash", record.get("bridge_hash")),
                      ("arms_manifest_hash", record.get("arms_manifest_hash"))]
    missing_anchors = [] if legacy else sorted(
        name for name, value in mandatory if value is None)
    # Which recorded hashes this arm's REBUILD was held against. An arm whose
    # record carried no anchor was checked against its own bundle only, and
    # saying which is the difference between a check and a claim. Computed
    # before anything can fail, so a FAILED or REFUSED arm reports it too.
    anchored = ([] if arm == "dc_native" else sorted(
        name for name, value in (
            ("bridge_hash", record.get("bridge_hash")),
            ("arms_manifest_hash", record.get("arms_manifest_hash")),
            ("provider_hash", recorded_provider))
        if value is not None))
    blank = {"arm": arm, "detail": {"sidecar_anchors": anchored},
             "coherence": {"PASS": False}, "marginal_parity": {"PASS": False}}

    why = simbundle.refusal(arm, directory)
    if why is not None:
        return {**blank, "status": "REFUSED", "PASS": False,
                "detail": {**blank["detail"], "error": why}}
    try:
        provider = simbundle.rebuild_provider(
            arm, directory, book=book, state=state,
            n_particles=record["n_particles"],
            # The sidecars are held against what THIS record says the forecast
            # produced, not only against each other: a cross-file edit that is
            # coherent everywhere inside the bundle still has to agree with the
            # bridge, provider and manifest hashes written here at issue time.
            anchors=simbundle.recorded_anchors(record))
    except (simbundle.BundleError, bridge_mod.BridgeError,
            particles.ParticleError, KeyError) as exc:
        return {**blank, "status": "FAIL", "PASS": False,
                "detail": {**blank["detail"],
                           "error": f"{type(exc).__name__}: {exc}"}}

    if verbose:
        # stderr, so `check`'s stdout is the report and nothing else
        print(f"[check] re-running {arm} at {record['cutoff']} "
              f"(N={record['n_sims']}, seed={record['seed']})",
              file=sys.stderr, flush=True)
    run = leaguesim.simulate(
        arm, state, provider, record["n_sims"], record["seed"],
        chunk_size=record["chunk_size"], season=season_obj,
        boundaries=season_obj.manifest.material_boundaries,
        rule_id=season_obj.manifest.tiebreak_rule_id,
        n_particles=record["n_particles"])

    digest = simcanary._numbers_digest(run)
    expected = record["numbers_digests"][arm]
    matches = digest == expected

    # The published FILE, read back off disk and held against both the record
    # and the re-run. `numbers_digests` compares live arrays to live arrays; it
    # cannot see an edited cell in `output_<arm>.json`, which is the artefact a
    # reader actually downloads.
    output_path = directory / f"output_{arm}.json"
    file_digest = recorded_output = None
    output_matches: bool | None = None
    try:
        payload = json.loads(output_path.read_text())
        file_digest = output_numbers_digest(payload)
        rerun_digest = output_numbers_digest(run.to_json())
        recorded_output = (record.get("output_digests") or {}).get(arm)
        output_matches = bool(
            file_digest == rerun_digest
            and (recorded_output is None or file_digest == recorded_output))
    except (OSError, ValueError, CliError) as exc:
        output_matches = False
        file_digest = f"unreadable: {type(exc).__name__}: {exc}"

    provider_matches = (None if recorded_provider is None
                        else provider.content_hash() == recorded_provider)

    coherence = simcanary.coherence(run)
    if arm == "dc_native":
        try:
            parity = simcanary.marginal_parity(book, None, run)
        except Exception as exc:
            parity = {"PASS": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        parity = {"PASS": True, "status": "NOT_APPLICABLE", "note": (
            f"{arm} samples the empirical bridge's conditional on purpose, so "
            "its per-fixture scoreline marginal is not the particle book's and "
            "comparing them would measure the arm's definition, not its "
            "reproduction. Its evidence here is the numbers digest.")}

    passed = bool(matches and coherence["PASS"] and parity["PASS"]
                  and output_matches is not False
                  and provider_matches is not False
                  and not missing_anchors)
    return {
        "arm": arm,
        "status": "PASS" if passed else "FAIL",
        "PASS": passed,
        "detail": {
            "schema_version": schema or None,
            "legacy_schema_leniency": legacy,
            "missing_mandatory_anchors": missing_anchors,
            "digest_matches": bool(matches),
            "recorded_digest": expected,
            "recomputed_digest": digest,
            "output_file_matches": output_matches,
            "output_file_digest": file_digest,
            "recorded_output_digest": recorded_output,
            "provider_hash": provider.content_hash(),
            "provider_hash_matches": provider_matches,
            "recorded_provider_hash": recorded_provider,
            "sidecar_anchors": anchored,
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
                   manual_file=None, observed_at=None, allow_revisions: bool = False,
                   write: bool = False, verbose: bool = True) -> list[dict]:
    """Append results to the season ledger. Idempotent; a conflict STOPs.

    Exactly one source: the network (``from_openfootball``), a local file in
    openfootball's own format (``openfootball_file`` / ``openfootball_text`` —
    the same parser and the same conflict rule, without the fetch), or a JSONL
    file of hand-entered ledger rows (``manual_file``).

    An openfootball ingest ALSO diffs the refreshed file's kickoffs against the
    ones the season currently knows and appends any move to
    ``kickoff_amendments.jsonl`` with ``known_at`` = the ingest time.
    :func:`epl.season.detect_kickoff_amendments` has existed since T2 and
    nothing called it, so a moved kickoff left the old date in place — and a
    fixture whose stale date has passed reads as ``unresolved`` and, past two
    days, raises ``results_lag``. The ingest is the only step that sees a fresh
    parse of the source, so it is the only step that can notice.

    ``allow_revisions`` is passed through to
    :func:`epl.season.ingest_openfootball_results` and does not affect the
    kickoff diff, which appends new knowledge rather than superseding a result.
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
    moves = new_kickoff_amendments(season_obj, text, known_at=observed_at,
                                   source_id=source_id)
    if write and moves:
        season_mod._append_jsonl(
            Path(root) / season_mod.season_dir_name(season)
            / season_mod.AMENDMENTS_FILENAME, moves)
    rows = season_obj.ingest_openfootball_results(
        text, observed_at=observed_at, source_id=source_id, write=write,
        allow_revisions=allow_revisions)
    if verbose:
        print(f"[ingest] {len(rows)} row(s) and {len(moves)} kickoff amendment(s) "
              f"from {source_id}"
              f"{' written' if write else ' (dry run)'}", flush=True)
    return rows


def new_kickoff_amendments(season_obj, text: str, *, known_at,
                           source_id: str) -> list[dict]:
    """Kickoff moves the refreshed source carries that are not already recorded.

    Two filters, and both matter. :func:`epl.season.detect_kickoff_amendments`
    diffs the refreshed parse against the VENDORED bytes, which never change, so
    on its own it would re-report the same move at every ingest until the end of
    the season — noise in an append-only overlay. The second filter holds each
    candidate against the kickoff the season KNOWS at the ingest time (base plus
    every amendment already on file) and keeps only the ones that actually move
    it.
    """
    stamp = season_mod._require_stamp(known_at, "known_at")
    candidates = season_mod.detect_kickoff_amendments(
        season_mod.parse_openfootball(season_obj.fixtures_text),
        season_mod.parse_openfootball(text),
        stamp, source_id, season_code=season_obj.season_code)
    known = season_mod._kickoffs_known(season_obj.fixtures, season_obj.amendments,
                                       stamp)
    out: list[dict] = []
    for row in candidates:
        current = known.get(row["fixture_id"])
        if current is None:
            continue
        date = (pd.Timestamp(row["date"]).date() if row.get("date")
                else current[0])
        if (date, row.get("time")) == current:
            continue
        out.append(row)
    return out


def _manual_rows(path: Path, season_obj, observed_at) -> list[dict]:
    """Validate hand-entered ledger rows against the fixture list.

    The hand overlay writes all three kinds of row the ledger's resolution
    already understands, and validates every one of them at WRITE time:

    * a **result** — `{fixture_id, date_played, hg, ag}`;
    * a **status** — `{fixture_id, status: "postponed"|"abandoned"}`, carrying no
      goals, which makes the fixture unplayed from this observation on;
    * a **correction** — a result that disagrees with what the ledger currently
      says, which must set `"correction": true`. Without the marker a
      disagreement is still :class:`ResultConflict`, because the overwhelmingly
      likelier explanation for one is a typo, and the append-only ledger has no
      undo. The marker is a directive to this reader and is not written to the
      ledger; the row's note records what it supersedes.

    Everything here is refused before a byte reaches the file. `_timestamp` maps
    `None`, `""`, `nan` and the string `"NaT"` to `NaT` rather than raising, so a
    malformed stamp used to be committed to an append-only ledger and only
    refused the next time anything read it — by which point every later snapshot
    fails closed on a row that is never meant to be edited. Goals go through
    :func:`epl.season.goal_count` for the same reason in the other direction:
    `int(1.9)` is `1`, and read-time validation cannot tell that `1` was never
    reported by anybody.
    """
    fixtures = {f.fixture_id for f in season_obj.fixtures}
    winners = season_mod.current_ledger_view(season_obj).winners
    observed = season_mod._require_stamp(observed_at, "observed_at")

    out: list[dict] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        where = f"{path}:{lineno}"
        fid = str(row.get("fixture_id", ""))
        if fid not in fixtures:
            raise season_mod.SeasonError(
                f"{where}: {fid!r} is not a fixture of {season_obj.season}")
        if fid in seen:
            raise season_mod.ResultConflict(f"{path}: {fid} appears twice")
        seen.add(fid)

        stamp = observed
        if row.get("observed_at") is not None:
            stamp = season_mod._require_stamp(row["observed_at"],
                                              f"{where}: {fid} observed_at")
        winner = winners.get(fid)

        if row.get("status") is not None:
            status = str(row["status"])
            if status not in season_mod._LEDGER_STATUSES:
                raise season_mod.UnsupportedResultStatus(
                    f"{where}: {fid} status {status!r} is out of v1 scope (only "
                    f"{sorted(season_mod._LEDGER_STATUSES)} are modelled)")
            if row.get("hg") is not None or row.get("ag") is not None:
                raise season_mod.SeasonError(
                    f"{where}: {fid} carries both a {status!r} status and a "
                    "scoreline. One row says one thing.")
            if winner is not None:
                season_mod._refuse_a_stale_revision(fid, winner, stamp)
            out.append({
                "fixture_id": fid,
                "status": status,
                "source": "manual",
                "observed_at": stamp.isoformat(),
                "note": str(row.get("note", "")),
            })
            continue

        if "hg" not in row or "ag" not in row:
            raise season_mod.SeasonError(
                f"{where}: {fid} carries neither a scoreline nor a status")
        hg = season_mod.goal_count(row["hg"], f"{where}: {fid} hg")
        ag = season_mod.goal_count(row["ag"], f"{where}: {fid} ag")
        note = str(row.get("note", ""))

        if winner is not None and winner.get("status") is None:
            have = (season_mod.goal_count(winner.get("hg"), f"{fid} hg"),
                    season_mod.goal_count(winner.get("ag"), f"{fid} ag"))
            if have == (hg, ag):
                continue
            if row.get("correction") is not True:
                raise season_mod.ResultConflict(
                    f"{fid}: ledger holds {have[0]}-{have[1]}, {path} says "
                    f"{hg}-{ag}. STOP: check which is right, then re-file the row "
                    'with "correction": true to append the correction.')
            season_mod._refuse_a_stale_revision(fid, winner, stamp)
            note = (note + "; " if note else "") + (
                f"correction: supersedes {have[0]}-{have[1]} observed "
                f"{winner.get('observed_at')}")
        elif winner is not None:
            season_mod._refuse_a_stale_revision(fid, winner, stamp)

        if not row.get("date_played"):
            raise season_mod.SeasonError(f"{where}: {fid} has no date_played")
        season_mod._require_stamp(row["date_played"],
                                  f"{where}: {fid} date_played")
        out.append({
            "fixture_id": fid,
            "date_played": str(row["date_played"]),
            "hg": hg, "ag": ag,
            "source": "manual",
            "observed_at": stamp.isoformat(),
            "note": note,
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
    i.add_argument("--allow-revisions", action="store_true",
                   help="let the source revise its OWN earlier statement: a "
                        "changed scoreline appends a correction row, and a "
                        "fixture the refreshed file no longer scores appends a "
                        "postponed status row. It never overrules another "
                        "source's row (plan v2 D4) — that stays a STOP, and its "
                        "remedy is a --manual correction.")
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
    c.add_argument("--arm", action="append", choices=list(ARMS), default=None,
                   help="check only this arm (repeatable). The default is every "
                        "arm the issuance recorded; narrowing is how an issuance "
                        "written before the bridge sidecars existed is checked "
                        "for the arms it CAN account for.")

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
        observed_at=args.observed_at, allow_revisions=args.allow_revisions,
        write=args.write, verbose=True)
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
    report = check_issuance(directory, arms=args.arm, verbose=True)
    print(leaguesim.canonical_json(_plain(report)))
    for arm, cell in report["arms"].items():
        print(f"[check] {arm}: {cell['status']}"
              + (f" — {cell['detail']['error']}" if cell["status"] != "PASS"
                 and cell["detail"].get("error") else ""), file=sys.stderr)
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
