"""The snapshot orchestrator: runs read(cutoff)->cached_fit->simulate->scan, assembles the
artifacts, GATES each on the schema guards (a violating artifact is never written), stamps
provenance on EVERY file, NaN-sanitizes + stringifies tuple keys, and writes JSON with
allow_nan=False (a stray NaN fails loud, never invalid JSON). A snapshot IS a read(cutoff)
-> leakage-safe by construction; nothing is recomputed at render time.

THE GATE (the discipline made executable). ``build_snapshot`` is the one place every
dashboard artifact passes through before it lands on disk, so the spec's serializer-side
rules are ENFORCED here, never trusted to hold upstream:

  * ``gate_artifact`` is a true STOP — a naked (no uncertainty companion) or incoherent
    (non-monotone progression ladder) team-progression table RAISES before any write, so
    a violating artifact is never persisted (T2 Codex).
  * ``_write`` stamps provenance on EVERY file (T1 Codex), NaN/inf-sanitizes to JSON
    ``null`` (no imputation), and writes with ``allow_nan=False`` so a residual NaN raises
    rather than emitting an invalid ``NaN`` token (T7 review).
  * ``stringify_keys`` makes any event-tuple-keyed dict (e.g. edges) JSON-safe (T4 review).

LEAKAGE-SAFE BY CONSTRUCTION. The heavy compute is delegated to the already-leakage-gated
producers: ``cached_fit``/``simulate`` read ONLY ``store.read(cutoff)`` (the strict
``date < cutoff`` set), so a result observed AFTER the cutoff cannot touch the bundle — the
dashboard-layer analog of the P2-P5 leakage canaries (``test_leakage_dashboard.py``).
``build.py`` itself never reads a raw result or recomputes a number; it only assembles,
GATES, stamps, and writes.

REPRODUCIBLE. ``cached_fit`` is content-addressed + seeded and ``simulate`` is seeded, so
the same ``cutoff`` + ``seed`` yields a byte-identical bundle. The fit cache defaults to the
shared project cache ``paths.cache`` — OUTSIDE the dashboard output tree entirely (never
under ``out_root``, never inside the per-cutoff bundle dir) — so a production run reuses the
content-addressed posteriors across cutoffs while the output tree holds ONLY stamped bundle
dirs. Because the default cache is no longer under ``out_root``, two builds into distinct
``out_root``s now SHARE that default cache; the leakage/reproducibility canaries that depend
on a genuine fresh re-fit therefore pass an EXPLICIT, DISTINCT ``fit_kwargs["cache_dir"]`` per
build (``cache_dir`` always wins over the default) so each build re-fits rather than
short-circuiting on a shared cache hit — which is what keeps the leakage canary NON-VACUOUS
(the post-cutoff-mutation build re-fits against the mutated store)."""
from __future__ import annotations

import json
import math
from pathlib import Path

from wcmodel.backtest.walkforward import _sample_is_synthetic
from wcmodel.dashboard.provenance import Provenance, _git_rev, stamp
from wcmodel.dashboard.schema import (
    assert_uncertainty_companion,
    gate_fixture_forecast,
    gate_track,
    validate_progression_coherence,
)
from wcmodel.dashboard.tournament_view import ko_slot_occupants


def _bundle_is_synthetic(items) -> bool:
    """Fail-safe bundle taint (C2): NON-REAL unless EVERY item is explicitly real.

    A NON-REAL bundle must NEVER read as real (the banner must never be dropped on
    synthetic data), so the taint is the producer-side ANY, not an ``all(...)``: a MIXED
    batch (some synthetic, some not) taints the WHOLE bundle. ``items is None`` (no real
    feed wired) OR an EMPTY batch is synthetic-by-default — there is no explicitly-real
    sample to clear the taint, and the leakage/repro canaries build synthetic brackets
    with ``items=[]`` that must stay stamped NON-REAL. An item taints if it carries a
    taint flag at the ITEM/wrapper level OR its sample (wrapper+nested) is synthetic per
    the canonical ``walkforward._sample_is_synthetic`` — a marker can never be STRIPPED by
    passing only the inner sample to the detector. A bare item (no ``"sample"`` key) is
    treated as its own sample. An unknown (non-dict) item shape fails safe to NON-REAL.
    The per-item sample detector is reused — never re-implemented."""
    if not items:                       # None OR empty -> no real feed -> synthetic
        return True

    def _item_synth(it) -> bool:
        if not isinstance(it, dict):
            return True                                   # unknown shape -> fail safe to NON-REAL
        if it.get("is_synthetic") or it.get("_is_synthetic"):
            return True                                   # item/wrapper-level taint
        return _sample_is_synthetic(it.get("sample", it)) # sample (wrapper+nested) via canonical detector

    return any(_item_synth(it) for it in items)


def gate_artifact(team_markets: dict) -> None:
    """Hard gate before writing a team-progression artifact: every probability node carries
    an uncertainty companion AND the coherence ladder holds. Raises on any violation.

    A true STOP (T2 Codex): a naked or incoherent table RAISES here, so ``build_snapshot``
    never reaches ``_write`` for it — a violating artifact is never persisted."""
    for team, node in team_markets.items():
        for market, cell in node.items():
            if isinstance(cell, dict) and "value" in cell:
                assert_uncertainty_companion(cell)
        validate_progression_coherence(
            {m: c["value"] for m, c in node.items()
             if isinstance(c, dict) and c.get("value") is not None}
        )


def sanitize_nans(obj):
    """Recursively replace NaN/inf floats with None so json.dumps(allow_nan=False) is valid
    (no imputation to 0 — a missing value becomes JSON null)."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: sanitize_nans(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_nans(v) for v in obj]
    return obj


def stringify_keys(d: dict) -> dict:
    """JSON-safe tuple keys: an event-key tuple (home, away, date) -> 'home|away|date'."""
    return {("|".join(map(str, k)) if isinstance(k, tuple) else k): v for k, v in d.items()}


def _write(bundle: Path, name: str, payload: dict, prov: Provenance) -> None:
    """Stamp provenance on EVERY file, stringify tuple keys, NaN-sanitize, write with
    allow_nan=False (fail loud on a residual NaN rather than emitting invalid JSON).

    ``stringify_keys`` runs on the payload FIRST so an event-tuple-keyed artifact (e.g.
    ``edges_by_event`` -> ``(home, away, date) -> node``) is JSON-safe before ``json.dumps``
    — without it ``json.dumps`` raises ``TypeError: keys must be str...`` on the tuple key
    (T4 review: ``stringify_keys`` was unit-tested but never wired in here)."""
    env = sanitize_nans(stamp(stringify_keys(payload), prov))
    (bundle / name).write_text(json.dumps(env, indent=2, allow_nan=False))


def _match_id(home: str, away: str, date) -> str:
    """A stable, filesystem-safe per-fixture id: ``home__away__date`` with any path-/JSON-
    hostile char collapsed to ``_``. Derived from the ``(home, away, date)`` event identity
    (the same triple ``edges_by_event``/``event_key`` key on), so it is deterministic across
    builds and joins back to the edge/schedule rows."""
    raw = f"{home}__{away}__{date}"
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in raw)


def _fixture_utc_commence_date(date, time) -> str:
    """Reconstruct a fixture's UTC COMMENCE DATE (ISO ``"YYYY-MM-DD"``) from the YAML row.

    The verified ``config/tournament_2026.yaml`` fixtures store a LOCAL ``date`` plus a LOCAL
    ``time`` that CARRIES its UTC offset, e.g. ``date: '2026-06-11', time: '20:00 UTC-6'`` ->
    local kickoff ``2026-06-11 20:00`` at UTC-6 -> UTC ``2026-06-12T02:00:00Z`` -> UTC date
    ``"2026-06-12"`` (ONE DAY AFTER the local ``date``). The scan/odds path keys on exactly this
    UTC date (``odds_ingest.event_key`` -> ``astimezone(utc).date()``), so the dashboard edge
    key MUST be derived the SAME way or an evening-kickoff fixture in a negative-offset venue
    misses the lookup.

    ``time`` shape: ``"HH:MM UTC±N"`` (the openfootball-published local-with-offset form; all
    104 real fixtures carry it). When ``time`` is absent (the synthetic test harness, whose
    fixtures carry only a ``date``), the ``date`` is treated as ALREADY the UTC commence date
    (no crossing) — so the synthetic harness, whose odds ``commence`` UTC date already equals
    its fixture ``date``, keeps matching unchanged."""
    import re
    from datetime import datetime, timedelta, timezone

    import pandas as pd

    if not time:
        # No local time/offset -> nothing to convert; the date is the commence date as-is.
        # (The synthetic harness fixtures; production rows always carry a time.)
        return str(pd.Timestamp(str(date)).date())
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s+UTC([+-]\d{1,2})\s*", str(time))
    if m is None:
        # An unrecognized time shape would silently mis-derive the UTC date; fail LOUD naming
        # what's missing rather than guessing a timezone (the FOCAL "report, don't guess" rule).
        raise ValueError(
            f"fixture time {time!r} for {date!r} is not 'HH:MM UTC±N'; cannot reconstruct "
            "the UTC commence date without a parseable local time + offset"
        )
    hh, mm, offset_h = int(m.group(1)), int(m.group(2)), int(m.group(3))
    d = pd.Timestamp(str(date)).date()
    # Local kickoff at the published fixed offset -> UTC -> the UTC calendar date. This mirrors
    # odds_ingest.event_key (which parses the UTC commence_time then `.astimezone(utc).date()`):
    # here we BUILD the same instant from the local wall time + offset, then take the UTC date.
    local = datetime(d.year, d.month, d.day, hh, mm,
                     tzinfo=timezone(timedelta(hours=offset_h)))
    return str(local.astimezone(timezone.utc).date())


def _edge_key(home: str, away: str, date, *, time=None) -> tuple:
    """The ``edges_by_event`` lookup key for a fixture: ``(home, away, UTC-commence-date-str)``.

    KEY-IDENTITY MATCH (C5 FOCAL Codex). ``edges_by_event`` keys on ``tuple(opp["event_key"])``,
    and the scan opportunity's ``event_key`` comes from ``LiveDecision`` which STRINGIFIES the
    UTC commence date: ``decide_live`` builds ``event_key=[home, away, str(ekey[2])]`` where
    ``ekey[2]`` is the ``odds_ingest.event_key`` UTC ``datetime.date`` (``commence_time`` parsed,
    ``astimezone(utc).date()``). So the live key's third element is the ISO ``"YYYY-MM-DD"``
    STRING of the UTC commence DATE.

    We therefore derive the fixture's UTC commence date the SAME way the scan/odds path does —
    reconstructing the UTC kickoff from the fixture's LOCAL ``date`` + ``time`` (which carries
    its UTC offset) via ``_fixture_utc_commence_date`` — NOT the raw local ``date``. On a
    negative-UTC-offset evening kickoff the local date is one day BEFORE the UTC date (e.g.
    ``'2026-06-11'`` + ``'20:00 UTC-6'`` -> UTC ``'2026-06-12'``); keying on the local date made
    EVERY such production fixture's lookup miss, silently turning its edge into a coverage_gap —
    the model-vs-market overlay was dead on more than a third of the real WC-2026 group fixtures.
    The synthetic harness (fixtures with no ``time``) is unaffected: the date is treated as
    already-UTC, matching its odds ``commence`` UTC date."""
    return (home, away, _fixture_utc_commence_date(date, time))


def _forecast_summary(forecast: dict) -> dict:
    """The schedule-ROW projection of an already-gated full ``fixture_forecast``: the
    most-likely score (WITH its prob — never naked) + the full 1X2 split. The grid lives
    only in the per-fixture detail; the row carries the headline. No separate gate is needed
    — this is a pure projection of a forecast the detail already gated."""
    return {"most_likely": forecast["most_likely"], "one_x_two": forecast["one_x_two"]}


def _recent_form(results, team: str, *, n: int = 5) -> dict:
    """Last-``n`` PLAYED matches for ``team`` from the as-of ``results`` read — RAW history
    (Derived), NULL-safe + coverage-gapped when the team has no played history as-of-cutoff.

    Reuses the SHARED ``valid_played_results`` definition (finite/non-negative/integral,
    played) so the form set matches the model's row set; nothing is fabricated. Each entry is
    ``{date, home_team, away_team, home_score, away_score}`` straight from the store."""
    from wcmodel.dashboard.schema import coverage_gap
    from wcmodel.data.features import valid_played_results

    if results is None or results.empty:
        return coverage_gap("no played history as-of cutoff")
    played = valid_played_results(results)
    mask = (played["home_team"] == team) | (played["away_team"] == team)
    mine = played.loc[mask].copy()
    if mine.empty:
        return coverage_gap("no played history as-of cutoff")
    mine = mine.sort_values("date").tail(n)
    return {"matches": [
        {"date": str(r.date), "home_team": r.home_team, "away_team": r.away_team,
         "home_score": int(r.home_score), "away_score": int(r.away_score)}
        for r in mine.itertuples(index=False)
    ]}


def _fixture_why(posterior, *, home: str, away: str, date, xg_read, features, results):
    """The match-detail "why" for one fixture: team-strength posteriors (home + away),
    xG coverage-gated, rest_days (Phase-1 feature) NULL-safe, and recent form (raw history).
    Every absent input is an explicit ``coverage_gap`` / NULL — never imputed.

    FIXTURE-IDENTITY MATCH, NO STALE REUSE (C5 FOCAL Codex HIGH-1/HIGH-2). xG and rest_days
    are emitted ONLY when THIS exact fixture has a covered/played row — matched by the fixture's
    own identity, never by team-last. The xg store is per ``(match_id, team)`` and StatsBomb is
    HISTORICAL, so a WC-2026 FUTURE fixture is never covered -> xG ALWAYS gaps. ``features.build
    (cutoff)`` DROPS future/unplayed rows, so a future fixture has no row -> rest_days ALWAYS
    gaps. Emitting a DIFFERENT match's xg/rest onto a future fixture would be fabrication."""
    import pandas as pd
    from wcmodel.dashboard.schema import coverage_gap, no_impute
    from wcmodel.dashboard.why import team_strength, xg_or_gap

    fixture_date = pd.Timestamp(str(date)).normalize()

    def _xg_node(team: str, opp: str) -> dict:
        # xG is covered ONLY if the xg read carries a row for THIS exact fixture identity
        # (team == this side, opponent == the other side, match_date == the fixture date) —
        # NEVER the team's last historical xg. A WC-2026 future fixture is never StatsBomb-
        # covered, so this is an honest gap there.
        if (xg_read is None or xg_read.empty
                or not {"team", "opponent", "match_date", "xg"} <= set(xg_read.columns)):
            return xg_or_gap(xg=None, covered=False)
        md = pd.to_datetime(xg_read["match_date"]).dt.normalize()
        rows = xg_read.loc[(xg_read["team"] == team) & (xg_read["opponent"] == opp)
                           & (md == fixture_date)]
        if rows.empty:
            return xg_or_gap(xg=None, covered=False)
        return xg_or_gap(xg=float(rows["xg"].iloc[-1]), covered=True)

    def _rest_days(team: str) -> dict:
        # rest_days is emitted ONLY if THIS fixture (by (home_team, away_team, date) identity)
        # is a PLAYED row in the features frame — features.build(cutoff) drops the unplayed
        # row, so a future fixture has no row here and gaps (never a prior match's rest).
        need = {"rest_days", "team", "home_team", "away_team", "date"}
        if features is None or features.empty or not need <= set(features.columns):
            return coverage_gap("rest_days unknown for an unplayed fixture")
        fd = pd.to_datetime(features["date"]).dt.normalize()
        rows = features.loc[(features["team"] == team)
                            & (features["home_team"] == home)
                            & (features["away_team"] == away)
                            & (fd == fixture_date)]
        if rows.empty:
            return coverage_gap("rest_days unknown for an unplayed fixture")
        v = no_impute(rows["rest_days"].iloc[-1])
        return {"value": v} if v is not None else coverage_gap("rest_days null as-of cutoff")

    return {
        "team_strength": {"home": team_strength(posterior, home),
                          "away": team_strength(posterior, away)},
        "xg": {"home": _xg_node(home, away), "away": _xg_node(away, home)},
        "rest_days": {"home": _rest_days(home), "away": _rest_days(away)},
        "recent_form": {"home": _recent_form(results, home),
                        "away": _recent_form(results, away)},
    }


def _placing_for_group(team_progression: dict, teams) -> dict:
    """Slice ``{team: {pos: {value, se}}}`` for a group's teams out of the full
    ``team_progression`` table — the ``first``/``second``/``third`` {value,se} nodes
    ``ko_slot_occupants`` consumes (C3). A team absent from the table is skipped."""
    out = {}
    for t in teams:
        node = team_progression.get(t)
        if not node:
            continue
        out[t] = {pos: node[pos] for pos in ("first", "second", "third") if pos in node}
    return out


def _ko_row(match_no: int, bracket, team_progression: dict) -> dict:
    """One UNRESOLVED-knockout schedule row: per feeder ref, the probable slot occupants
    DERIVED from the group-placing markets via ``ko_slot_occupants`` (C3). Feeder refs:

      * ``1X``/``2X`` — group-position slot: occupants are group X's first/second placers.
      * ``3rd-XXXXX`` — best-third slot: occupants are the THIRD placers of the eligible
        groups (the verified eligible-set the bracket parsed in ``third_place_slots``). We do
        NOT re-derive FIFA Annex C: the slot->eligible-groups mapping is read straight from
        the bracket, and the per-sim Annex-C assignment (``assign_thirds_to_slots``) is a
        random tournament outcome not knowable at build time, so the schedule shows every
        eligible third's probability (most-likely first), never a fabricated single occupant.
    """
    import re

    home_ref, away_ref = bracket.knockout_feeders[match_no]
    eligible = bracket.third_place_slots.get(match_no)

    def _occupants_for(ref: str):
        m = re.fullmatch(r"([12])([A-L])", ref)
        if m:
            placing = _placing_for_group(team_progression, bracket.groups.get(m.group(2), []))
            return ko_slot_occupants(slot_source=ref, placing=placing)
        if re.fullmatch(r"3rd-([A-L]{5})", ref) and eligible:
            # Eligible-group thirds (verified slot->eligible mapping from the bracket).
            teams = [t for g in sorted(eligible) for t in bracket.groups.get(g, [])]
            placing = _placing_for_group(team_progression, teams)
            return ko_slot_occupants(slot_source="3", placing=placing)
        # A winner/loser feeder ("W74"/"L101") resolves only deeper in the bracket — no
        # placing-derived occupant exists yet, so it is an explicit (non-fabricated) gap.
        return {"coverage_gap": True, "reason": f"feeder {ref} resolves from a later match"}

    return {
        "match": match_no, "stage": bracket.match_round.get(match_no), "status": "upcoming",
        "home_ref": home_ref, "away_ref": away_ref,
        "home_occupants": _occupants_for(home_ref),
        "away_occupants": _occupants_for(away_ref),
    }


def build_snapshot(cutoff, *, store, config=None, fit_kwargs=None, items=None,
                   out_root=None, tournament=None, backtest_records=None) -> Path:
    """Build + write the FULL snapshot bundle for ``cutoff``. Returns the bundle dir. Heavy
    compute is delegated to cached_fit/simulate/scan; build.py only assembles, GATES every
    artifact, stamps the SAME provenance on every file, and writes.

    THE BUNDLE (each file stamped via ``_write`` -> provenance + NaN-safe + stringify-keys):

      * ``tournament.json`` — ``team_progression(sim)``, gated by ``gate_artifact`` (per-team
        uncertainty companion + coherence; a coverage_gap node is exempt per C1).
      * ``schedule.json`` — ``build_schedule`` over the GROUP fixtures, each row carrying a
        forecast summary (a projection of the GATED full forecast) + the edge node (or a
        coverage_gap) by event key; PLUS one row per UNRESOLVED knockout fixture with its
        slot occupants (``ko_slot_occupants``, C3).
      * ``fixtures/<match_id>.json`` — per GROUP fixture: the FULL ``fixture_forecast`` (incl
        the grid) GATED by ``gate_fixture_forecast`` + the "why" (team strength / xG / rest /
        recent form, all NULL-safe + coverage-gapped) + the edge node (or a gap).
      * ``track.json`` — ``track_record`` GATED by ``gate_track`` when ``backtest_records`` is
        supplied; else an honest ``coverage_gap`` ("no backtest records supplied"). The build
        NEVER re-runs the heavy walk-forward backtest.
      * ``meta.json`` — markets list + provenance.

    GATING IS A TRUE STOP. ``gate_fixture_forecast`` (each fixture forecast), ``gate_artifact``
    (tournament), and ``gate_track`` (track) RAISE before any write, so a violating artifact is
    never persisted. The edges dict (tuple keys) is JSON-safed by ``_write``'s ``stringify_keys``.

    GLOB CONTRACT. The bundle dir contains ONLY stamped JSON artifacts (top-level ``*.json`` +
    the ``fixtures/`` dir); model fit caches live OUTSIDE the bundle (default ``paths.cache``,
    the shared project cache), so a reader globbing the bundle's ``*.json`` never picks up a
    cache file, and the whole ``out_root`` tree a production run reuses holds only bundle dirs.

    ``tournament`` (default ``None`` -> the verified ``config/tournament_2026.yaml``) is
    threaded straight to ``SimConfig`` AND reused to build the schedule + bracket, so a minimal
    synthetic bracket can be simulated over a compact posterior (the leakage/repro canaries
    pass one; production passes nothing and gets the real 48-team draw). Without this hook
    ``RateBook(posterior)`` would ``KeyError`` whenever the posterior misses a bracket team."""
    from wcmodel.config import load_config
    from wcmodel.model.cache import cached_fit
    from wcmodel.sim.bracket import build_bracket
    from wcmodel.sim.run import SimConfig, _load_tournament, simulate

    cfg = config or load_config()
    fk = fit_kwargs or {}
    out_root = Path(out_root or cfg["dashboard"]["output_dir"])
    # The fit cache defaults to the shared project cache (paths.cache) — OUTSIDE the dashboard
    # output tree entirely, never under out_root and never inside the per-cutoff bundle dir.
    # So the bundle dir holds ONLY stamped JSON artifacts (a frontend globbing the bundle's
    # *.json never trips over a cache file) AND a production run reuses the content-addressed
    # posteriors across cutoffs. CONSEQUENCE FOR THE CANARIES: because the default is no longer
    # under out_root, two builds into distinct out_roots now SHARE this default cache; the
    # leakage/repro canaries that must genuinely RE-FIT therefore pass an EXPLICIT, DISTINCT
    # fit_kwargs["cache_dir"] per build (cache_dir always wins) so each build re-fits instead
    # of short-circuiting on a shared cache hit (keeps the leakage canary NON-VACUOUS).
    fit_cache = fk.get("cache_dir", cfg["paths"]["cache"])
    posterior, meta = cached_fit(
        cutoff=cutoff, store=store, backend=fk.get("backend", "advi"),
        draws=fk.get("draws", 200), seed=fk.get("seed", cfg["seed"]),
        advi_iters=fk.get("advi_iters", 2000),
        cache_dir=fit_cache, config=cfg,
    )
    sim = simulate(cutoff, posterior, store,
                   SimConfig.from_config(cfg, n_sims=cfg["dashboard"]["n_sims"],
                                         tournament=tournament))

    from wcmodel.dashboard.tournament_view import team_progression
    tournament_view = team_progression(sim)
    gate_artifact(tournament_view)                  # STOP: never write a naked/incoherent table

    # Resolve the SAME tournament dict the sim used (None -> the verified 2026 draw) so the
    # schedule + bracket are built from the identical structure — never re-derived here.
    repo_root = Path(__file__).resolve().parents[3]
    tdict = _load_tournament(tournament, repo_root)
    bracket = build_bracket(tdict)

    # --- Live edges (PRIMARY 1X2 surface), re-keyed by event. Heavy compute stays in scan ->
    # decide_live -> cached_fit/simulate; a missing/odds-less item is a counted non-bet (the
    # scan batch-guard), never a crash. An empty/None items list yields no edges (and a
    # synthetic-by-default bundle taint below). edges_by_event propagates the per-edge taint.
    from wcmodel.dashboard.edges import edges_by_event
    from wcmodel.live.scan import scan

    ranked = scan(store, list(items or []), cutoff=cutoff, config=cfg, fit_kwargs=fk)
    edges = edges_by_event(ranked)

    # --- The as-of reads the "why" projects from (NULL-safe / coverage-gapped when absent).
    # These are pure store.read(cutoff)/features.build(cutoff) — no recompute beyond the
    # already-leakage-gated producers.
    from wcmodel.data.features import build as features_build

    def _safe_read(name):
        try:
            return store.read(name, cutoff=cutoff)
        except FileNotFoundError:
            return None

    xg_read = _safe_read("xg")
    results_read = _safe_read("results")
    try:
        features = features_build(cutoff, store, config=cfg)
    except Exception:
        features = None                              # NULL-safe: rest_days simply coverage-gaps

    # --- Per-fixture forecasts (FULL, gated) + schedule rows. GROUP fixtures only feed
    # build_schedule (the KO fixtures carry placeholder feeders + no date). neutral=True per
    # the confirmed WC design (group stage is on neutral ground; the host exception is a
    # downstream refinement, not modelled here).
    from wcmodel.dashboard.fixtures import build_schedule, fixture_forecast

    group_fixtures = [fx for fx in tdict["fixtures"] if fx.get("match") is None]
    schedule = build_schedule(group_fixtures, cutoff=str(cutoff))

    fixture_details: dict[str, dict] = {}
    by_pair_date: dict[tuple, dict] = {}
    for fx in group_fixtures:
        home, away, date = fx["home"], fx["away"], fx["date"]
        forecast = fixture_forecast(posterior, home=home, away=away, neutral=True)
        gate_fixture_forecast(forecast)              # STOP: never write a naked/degenerate forecast
        # The edge lookup keys on the fixture's UTC COMMENCE DATE (reconstructed from the
        # local date + local time-with-offset), matching the scan event_key — NOT the local
        # date (C5 FOCAL Codex: a negative-offset evening kickoff's local date != UTC date).
        ekey = _edge_key(home, away, date, time=fx.get("time"))
        edge_node = edges.get(ekey, {"coverage_gap": True,
                                     "reason": "no live edge for this fixture as-of cutoff"})
        detail = {
            "match_id": _match_id(home, away, date),
            "home": home, "away": away, "date": str(date), "stage": "group",
            "forecast": forecast,
            "why": _fixture_why(posterior, home=home, away=away, date=date,
                                xg_read=xg_read, features=features, results=results_read),
            "edge": edge_node,
        }
        fixture_details[detail["match_id"]] = detail
        by_pair_date[(home, away, str(date))] = {
            "forecast_summary": _forecast_summary(forecast), "edge": edge_node,
            "match_id": detail["match_id"],
        }

    # Attach the forecast summary + edge to each GROUP schedule row by (home, away, date).
    for row in schedule:
        attach = by_pair_date.get((row["home"], row["away"], str(row["date"])))
        if attach is not None:
            row.update(attach)
        else:                                        # a fixture the forecaster skipped -> gap
            row["forecast_summary"] = {"coverage_gap": True,
                                       "reason": "no forecast for this fixture"}
            row["edge"] = {"coverage_gap": True, "reason": "no live edge for this fixture"}

    # UNRESOLVED knockout rows: slot occupants derived from the group-placing markets.
    ko_rows = [_ko_row(m, bracket, tournament_view)
               for m in sorted(bracket.knockout_feeders)]

    # --- Track record: track_record(gated) when records supplied, else an honest coverage_gap
    # (the build NEVER re-runs the heavy walk-forward backtest).
    from wcmodel.dashboard.schema import coverage_gap
    from wcmodel.dashboard.track import track_record

    if backtest_records:
        track = track_record(bets=backtest_records["bets"], preds=backtest_records["preds"])
        gate_track(track)                            # STOP: never write a non-finite track metric
    else:
        track = coverage_gap("no backtest records supplied")

    # C2 + MED-6: fail-safe taint — NON-REAL unless EVERY item is explicitly real AND the
    # dashboard is NOT in dry-run. ``dashboard.dry_run`` (the v1 synthetic-odds posture) taints
    # the WHOLE bundle so a paper track (``track_record`` hardcodes ``is_synthetic=True``) can
    # never sit under a real-looking banner. ANY synthetic / nested-synthetic item also taints
    # (items None/empty -> synthetic), and the scan's own synthetic flag is ORed in so a
    # synthetic odds feed taints even a real-shaped items list. In v1 (dry_run=True) the bundle
    # is therefore ALWAYS NON-REAL, consistent with the embedded paper track.
    is_synth = (bool(cfg["dashboard"]["dry_run"])
                or _bundle_is_synthetic(items)
                or bool(getattr(ranked, "is_synthetic", False)))
    prov = Provenance(cutoff=str(cutoff), posterior_key=meta["key"], git=_git_rev(),
                      is_synthetic=is_synth, n_sims=sim.n_sims)
    bundle = out_root / str(cutoff).replace(":", "").replace(" ", "T")
    bundle.mkdir(parents=True, exist_ok=True)

    _write(bundle, "tournament.json", tournament_view, prov)
    _write(bundle, "schedule.json", {"group": schedule, "knockout": ko_rows}, prov)
    _write(bundle, "track.json", track, prov)
    _write(bundle, "meta.json",
           {"markets": list(next(iter(tournament_view.values())).keys())
                       if tournament_view else [],
            "provenance_note": "every artifact carries the SAME as-of provenance envelope"},
           prov)

    fixtures_dir = bundle / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    for mid, detail in fixture_details.items():
        _write(fixtures_dir, f"{mid}.json", detail, prov)

    return bundle
