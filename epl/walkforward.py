"""THE RUN. The frozen Dixon-Coles model against walk-forward Elo, 2019/20-2024/25.

This module executes the design preregistered in ``reports/epl_prereg.md`` §5 and
scores it under the pass rule in §3. It chooses nothing: every hyperparameter it
uses is read off ``epl/config_frozen.json``, which was committed at b416925
before any line of this file existed.

THE CADENCE IS WEEKLY, AND THAT IS NOT A CHOICE MADE HERE. The preregistration
fixes "every matchweek of every scoring season" — 212 fits, counted — and its
own STOP clause 6 says the run does *not* "shrink the window, coarsen the
cadence, or thin the sample to fit the budget: any of those would change the
preregistered design after seeing what it costs". H1 itself is stated as "fitted
walk-forward at matchweek cadence". A fortnightly walk would answer a different
question with the same words, so :data:`CADENCE_WEEKS` is 1 and the runner
refuses anything else unless it is told, in the artifact, that it is off-protocol.

WHAT ONE CUTOFF IS. A matchweek is (season, ISO calendar week) — the same block
the bootstrap uses and the same one ``epl.fit.matchweek_index`` builds. The
cutoff is that block's OPENING DAY at midnight. ``wcmodel.data.features.build``
keeps ``date < cutoff.normalize()``, so every fixture in the block is unseen by
the fit that prices it, including fixtures on the opening day itself. That is
asserted per cutoff (:func:`matchweek_cutoffs`), not assumed.

EVERY FIXTURE GETS A NUMBER. A fixture the model cannot price is a reported
failure and a STOP, never a silent drop — see the module's ``unpriceable``
ledger column and ``reports/epl_prereg.md`` §4.2. Fix 3
(:class:`epl.dcfit.ColdStartPosterior`) exists so the count is zero.

THE PANEL FAST PATH, and why it changes no number. ``features.build`` computes a
COVID tag with ``df["date"].map(tiers.is_covid)``, and ``tiers.is_covid`` opens
and YAML-parses ``config/config.yaml`` in its body — once per panel row, ~8k
times per fit, which is 50 of the 57 seconds a fit costs. ``epl.fit.
config_read_once`` serves that read from one already-parsed config. It edits
nothing under ``src/`` and it cannot change the panel, because the panel is
proven bit-identical either way — at the cutoffs in
:func:`verify_fast_path_is_inert`, on the panel AND on the resulting 1X2
forecasts, at every cutoff run. It is used here so the preregistered 212-fit
weekly cadence fits comfortably inside the budget instead of the cadence being
coarsened to fit the clock.

NO BETTING. The market column is an accuracy benchmark. It is never displayed
publicly, never turned into a signal, and never sized.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
import re
import sys
import tempfile
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from epl import anchor as anchor_mod
from epl import baseline, dcfit, fit as epl_fit, freeze, paths
from epl import score as score_mod, windows
from epl.schema import sort_for_walk_forward

__all__ = [
    "CADENCE_WEEKS", "LEDGER_PATH", "NEXT_LEDGER_PATH", "RESULT_PATH",
    "NEXT_RESULT_PATH", "NEXT_PREDICTIONS_PATH", "SCHEDULE_MANIFEST_PATH",
    "RUN_ENVELOPE_SCHEMA",
    "Cutoff", "WalkLedger", "EvidenceIntegrityError",
    "ResumeIdentityMismatch", "VerdictPublicationBlocked",
    "matchweek_cutoffs", "run_walk", "load_ledger", "score_run",
    "verify_fast_path_is_inert", "point_in_time_canary",
]

#: Preregistered refit cadence, in matchweeks. See the module docstring.
CADENCE_WEEKS = 1

#: Append-only per-cutoff forecast ledger (JSONL), so a crashed run resumes
#: instead of restarting, and so the raw forecasts survive the scoring code.
LEDGER_PATH = paths.FIT_DIR / "walkforward_ledger.jsonl"

#: The historical path above is a headerless, already-published v1 artifact.
#: A chained run is issued at a new path; it never rewrites or appends to v1.
NEXT_LEDGER_PATH = paths.FIT_DIR / "walkforward_ledger_v2.jsonl"

#: The scored result: headline gap, CI, per-season table, diagnostics.
RESULT_PATH = paths.FIT_DIR / "walkforward.json"
NEXT_RESULT_PATH = paths.FIT_DIR / "walkforward_v2.json"
NEXT_PREDICTIONS_PATH = paths.FIT_DIR / "walkforward_predictions_v2.parquet"

#: Outcome-free schedule commitment extracted from the already-published run.
SCHEDULE_MANIFEST_PATH = (
    paths.REPO_ROOT / "reports" / "epl_walkforward_schedule_v1.json")
SCHEDULE_MANIFEST_SCHEMA = "epl-walkforward-schedule-1"
EXPECTED_SCHEDULE_MANIFEST_SHA256 = (
    "b2a38ca5179df048d2763c4612e16aadaf708767629c394d8f27c806e1075e6f")
EXPECTED_PUBLISHABLE_CUTOFFS = 212
EXPECTED_PUBLISHABLE_FIXTURES = 2_280

#: A ledger carrying this envelope can support a verdict. Older ledgers remain
#: readable only when a caller explicitly asks for non-verdict compatibility.
RUN_ENVELOPE_SCHEMA = "epl-walkforward-run-envelope-2"
_ENVELOPE_RECORD = "run_envelope"
_CUTOFF_RECORD = "cutoff"
_TERMINAL_RECORD = "terminal_seal"
_SCORE_SEAL_SCHEMA = "epl-walkforward-score-seal-1"
_HASH_FIELDS = (
    "code_sha256", "data_sha256", "store_sha256", "config_sha256",
    "dependencies_sha256",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Cutoff probabilities are deliberately persisted at eight decimals. Three
# independently rounded cells can therefore miss one by at most 1.5e-8.
_STORED_PROB_SUM_ATOL = 1.5e-8


class EvidenceIntegrityError(ValueError):
    """The append-only evidence is ambiguous or internally inconsistent."""


class ResumeIdentityMismatch(EvidenceIntegrityError):
    """A resume attempted to mix two different immutable run envelopes."""


class VerdictPublicationBlocked(EvidenceIntegrityError):
    """The run may be inspected, but no verdict may be published from it."""

    def __init__(self, blockers: Mapping[str, Any]):
        self.blockers = dict(blockers)
        detail = "; ".join(f"{k}={v}" for k, v in self.blockers.items())
        super().__init__(f"walk-forward verdict publication blocked: {detail}")


class WalkLedger(list):
    """Cutoff rows plus the immutable envelope read from their JSONL header."""

    def __init__(self, rows: Iterable[dict[str, Any]] = (), *,
                 run_envelope: Mapping[str, Any] | None = None,
                 run_envelope_sha256: str | None = None,
                 terminal_seal: Mapping[str, Any] | None = None,
                 chain_head_sha256: str | None = None,
                 header_record_sha256: str | None = None):
        super().__init__(rows)
        self.run_envelope = (dict(run_envelope)
                             if run_envelope is not None else None)
        self.run_envelope_sha256 = run_envelope_sha256
        self.terminal_seal = (dict(terminal_seal)
                              if terminal_seal is not None else None)
        self.chain_head_sha256 = chain_head_sha256
        self.header_record_sha256 = header_record_sha256


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _frame_sha256(frame: pd.DataFrame) -> str:
    """Hash values, order, column names and dtypes of a model input frame."""
    payload = {
        "columns": [str(c) for c in frame.columns],
        "dtypes": [str(t) for t in frame.dtypes],
        "data": frame.to_json(orient="split", date_format="iso",
                              date_unit="ns", double_precision=15),
    }
    return _json_sha256(payload)


def _code_sha256() -> str:
    """Hash executable EPL/model Python, including dirty working-tree bytes."""
    roots = (paths.REPO_ROOT / "epl", paths.REPO_ROOT / "src" / "wcmodel")
    files = []
    for root in roots:
        if root.exists():
            files.extend(p for p in root.rglob("*.py")
                         if "tests" not in p.relative_to(root).parts)
    h = hashlib.sha256()
    for path in sorted(files):
        rel = path.relative_to(paths.REPO_ROOT).as_posix().encode("utf-8")
        blob = path.read_bytes()
        h.update(len(rel).to_bytes(8, "big")); h.update(rel)
        h.update(len(blob).to_bytes(8, "big")); h.update(blob)
    return h.hexdigest()


def _dependencies_sha256() -> str:
    """Hash both intended locks and the dependency versions actually imported."""
    packages = ("numpy", "pandas", "pyarrow", "duckdb", "scipy", "pymc",
                "arviz")
    versions = {}
    for name in packages:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "MISSING"
    locks = {}
    for name in ("pyproject.toml", "uv.lock"):
        path = paths.REPO_ROOT / name
        locks[name] = _file_sha256(path) if path.exists() else "MISSING"
    return _json_sha256({"python": sys.version, "versions": versions,
                         "locks": locks})


def _schedule_payload(cuts: Sequence["Cutoff"]) -> list[dict[str, Any]]:
    return [{"key": c.key, "season": c.season,
             "matchweek": int(c.matchweek),
             "cutoff": str(c.cutoff.date()),
             "match_ids": list(c.match_ids)} for c in cuts]


def _record_sha256(record: Mapping[str, Any]) -> str:
    """Hash one canonical record without trying to include its own digest."""
    payload = dict(record)
    payload.pop("record_sha256", None)
    return _json_sha256(payload)


def _chain_record(record: Mapping[str, Any], previous: str | None = None,
                  ) -> dict[str, Any]:
    out = dict(record)
    if previous is not None:
        out["previous_record_sha256"] = previous
    out["record_sha256"] = _record_sha256(out)
    return out


def _normalise_committed_schedule(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise EvidenceIntegrityError("schedule manifest schedule must be a list")
    out = []
    for i, row in enumerate(value, 1):
        if not isinstance(row, dict):
            raise EvidenceIntegrityError(
                f"schedule manifest entry {i} is not an object")
        try:
            normalised = {
                "key": str(row["key"]), "season": str(row["season"]),
                "matchweek": int(row["matchweek"]),
                "cutoff": str(row["cutoff"]),
                "match_ids": [str(m) for m in row["match_ids"]],
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceIntegrityError(
                f"schedule manifest entry {i} is malformed") from exc
        if normalised != row:
            raise EvidenceIntegrityError(
                f"schedule manifest entry {i} is not in canonical schema")
        out.append(normalised)
    _validate_unique_rows(out)
    return out


def _load_schedule_manifest(
        path: Path | str | None = None) -> tuple[dict[str, Any], str]:
    """Load and internally verify the outcome-free publication commitment."""
    manifest_path = Path(path or SCHEDULE_MANIFEST_PATH)
    try:
        raw = manifest_path.read_text()
        manifest = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceIntegrityError(
            f"cannot read schedule commitment {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise EvidenceIntegrityError("schedule commitment is not a JSON object")
    manifest_sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if manifest_sha256 != EXPECTED_SCHEDULE_MANIFEST_SHA256:
        raise EvidenceIntegrityError(
            "schedule commitment does not match the independently pinned digest")
    if manifest.get("schema") != SCHEDULE_MANIFEST_SCHEMA:
        raise EvidenceIntegrityError("invalid schedule commitment schema")
    schedule = _normalise_committed_schedule(manifest.get("schedule"))
    n_cutoffs = len(schedule)
    n_fixtures = sum(len(r["match_ids"]) for r in schedule)
    declared = (manifest.get("n_cutoffs"), manifest.get("n_fixtures"))
    if declared != (n_cutoffs, n_fixtures):
        raise EvidenceIntegrityError(
            "schedule commitment declared counts do not match its rows")
    if (n_cutoffs, n_fixtures) != (
            EXPECTED_PUBLISHABLE_CUTOFFS, EXPECTED_PUBLISHABLE_FIXTURES):
        raise EvidenceIntegrityError(
            "schedule commitment must contain exactly "
            f"{EXPECTED_PUBLISHABLE_CUTOFFS} cutoffs and "
            f"{EXPECTED_PUBLISHABLE_FIXTURES} fixtures")
    digest = _json_sha256(schedule)
    if manifest.get("schedule_sha256") != digest:
        raise EvidenceIntegrityError(
            "schedule commitment digest does not cover the ordered schedule")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise EvidenceIntegrityError("schedule commitment has no source block")
    if not _SHA256_RE.fullmatch(str(source.get("played_frame_sha256", ""))):
        raise EvidenceIntegrityError(
            "schedule commitment has no valid played-frame digest")
    for name in ("matches_parquet", "source_ledger"):
        item = source.get(name)
        if (not isinstance(item, dict) or not item.get("path")
                or not _SHA256_RE.fullmatch(str(item.get("sha256", "")))):
            raise EvidenceIntegrityError(
                f"schedule commitment has no valid {name} source identity")
    return manifest, manifest_sha256


def _source_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else paths.REPO_ROOT / path


def _publication_commitment(
        played: pd.DataFrame, actual_cuts: Sequence["Cutoff"] | None = None,
        ) -> tuple[list["Cutoff"], str, dict[str, Any]]:
    """Return the fixed schedule and every mismatch against its source lock."""
    manifest, manifest_sha256 = _load_schedule_manifest()
    schedule = manifest["schedule"]
    committed = [
        Cutoff(season=row["season"], matchweek=row["matchweek"],
               cutoff=pd.Timestamp(row["cutoff"]),
               rows=np.array([], dtype=int),
               match_ids=tuple(row["match_ids"]))
        for row in schedule
    ]
    blockers: dict[str, Any] = {}
    source = manifest["source"]
    actual_played_sha = _frame_sha256(played)
    if actual_played_sha != source["played_frame_sha256"]:
        blockers["committed_data_mismatch"] = {
            "expected": source["played_frame_sha256"],
            "actual": actual_played_sha,
        }
    for field in ("matches_parquet", "source_ledger"):
        item = source[field]
        source_path = _source_path(str(item["path"]))
        actual = _file_sha256(source_path) if source_path.is_file() else "MISSING"
        if actual != item["sha256"]:
            blockers[f"committed_{field}_mismatch"] = {
                "path": str(source_path), "expected": item["sha256"],
                "actual": actual,
            }
    if actual_cuts is not None:
        actual_payload = _schedule_payload(actual_cuts)
        if actual_payload != schedule:
            blockers["committed_schedule_mismatch"] = {
                "expected_sha256": manifest["schedule_sha256"],
                "actual_sha256": _json_sha256(actual_payload),
                "expected_cutoffs": len(schedule),
                "actual_cutoffs": len(actual_payload),
                "expected_fixtures": EXPECTED_PUBLISHABLE_FIXTURES,
                "actual_fixtures": sum(len(r["match_ids"])
                                       for r in actual_payload),
            }
    return committed, manifest_sha256, blockers


def _identity_hashes(*, played: pd.DataFrame, cfg: Mapping[str, Any],
                     elo_cfg: Any,
                     supplied: Mapping[str, str] | None = None,
                     ) -> tuple[dict[str, str], dict[str, str]]:
    supplied = dict(supplied or {})
    unknown = set(supplied) - set(_HASH_FIELDS)
    if unknown:
        raise ValueError(f"unknown run identity hash field(s): {sorted(unknown)}")
    for name, digest in supplied.items():
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ValueError(f"{name} must be a lowercase 64-hex SHA-256")

    computed = {
        "code_sha256": _code_sha256,
        "data_sha256": lambda: _frame_sha256(played),
        "store_sha256": lambda: _frame_sha256(epl_fit.to_store_frame(played)),
        "config_sha256": lambda: _json_sha256({"wcmodel": cfg,
                                                 "elo": elo_cfg}),
        "dependencies_sha256": _dependencies_sha256,
    }
    values, sources = {}, {}
    for name in _HASH_FIELDS:
        if name in supplied:
            values[name], sources[name] = supplied[name], "supplied"
        else:
            values[name], sources[name] = computed[name](), "computed"
    return values, sources


def _build_run_envelope(*, played: pd.DataFrame, cfg: Mapping[str, Any],
                        elo_cfg: Any, eligible_cuts: Sequence["Cutoff"],
                        run_cuts: Sequence["Cutoff"], cadence: int,
                        seed: int | None, fast_panel: bool, publishable: bool,
                        identity_hashes: Mapping[str, str] | None = None,
                        schedule_manifest_sha256: str | None = None,
                        ) -> dict[str, Any]:
    if publishable and identity_hashes:
        raise VerdictPublicationBlocked({
            "supplied_identity_hashes": sorted(identity_hashes)})
    identity, sources = _identity_hashes(
        played=played, cfg=cfg, elo_cfg=elo_cfg, supplied=identity_hashes)
    eligible = _schedule_payload(eligible_cuts)
    selected = _schedule_payload(run_cuts)
    return {
        "schema": RUN_ENVELOPE_SCHEMA,
        "identity": identity,
        "identity_sources": sources,
        "eligible_schedule_sha256": _json_sha256(eligible),
        "run_schedule_sha256": _json_sha256(selected),
        "schedule_manifest_sha256": schedule_manifest_sha256,
        "n_eligible_cutoffs": len(eligible_cuts),
        "n_eligible_fixtures": sum(len(c.match_ids) for c in eligible_cuts),
        "n_run_cutoffs": len(run_cuts),
        "n_run_fixtures": sum(len(c.match_ids) for c in run_cuts),
        "score_seasons": list(windows.SCORE_SEASONS),
        "cadence_weeks": int(cadence),
        "seed_override": None if seed is None else int(seed),
        "fast_panel": bool(fast_panel),
        "publishable": bool(publishable),
    }


# ==========================================================================
# 1. the cutoffs
# ==========================================================================
@dataclass(frozen=True)
class Cutoff:
    """One refit: when it happens and which fixtures it prices."""

    season: str
    matchweek: int
    cutoff: pd.Timestamp
    rows: np.ndarray                      # positional indices into the played frame
    match_ids: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.season}|mw{self.matchweek:03d}|{self.cutoff.date()}"


def matchweek_cutoffs(matches: pd.DataFrame,
                      score_seasons: Sequence[str] = windows.SCORE_SEASONS,
                      cadence: int = CADENCE_WEEKS,
                      allow_excluded: bool = False) -> list[Cutoff]:
    """The refit schedule, with the point-in-time property asserted per cutoff.

    ``cadence = 1`` is the preregistered weekly walk: one fit per (season, ISO
    week), each pricing exactly that week's fixtures. ``cadence = n > 1`` groups
    n consecutive weeks of the SAME season behind one fit — off-protocol, and
    recorded as such in the ledger by :func:`run_walk`.

    Two properties are checked here rather than trusted: no block spans a season
    boundary, and every fixture in a block falls on or after the block's cutoff
    day, so the ``date < cutoff`` gate cannot have shown the fit a fixture it is
    about to price.

    ``allow_excluded`` opens the schedule to ``windows.EXCLUDED_SEASONS``. It
    defaults to False, so THIS run and everything that reuses it keeps the guard
    that stops 2025/26 drifting into a scored frame. The one sanctioned caller is
    ``epl.improve.run_walk(window="holdout", holdout=True)``, where 2025/26 is
    the deliberate fresh holdout for the DC-versus-Elo question — a question that
    needs no odds and is therefore untouched by the odds-coverage bias that
    excluded the season in the first place (``epl.windows``).
    """
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    if not allow_excluded:
        windows.assert_no_score_leak(score_seasons, "the scoring window")
    mw = epl_fit.matchweek_index(played)
    seasons = played["season"].to_numpy()
    dates = pd.to_datetime(played["date"]).dt.normalize().to_numpy()
    ids = played["match_id"].astype(str).to_numpy()

    out: list[Cutoff] = []
    for season in score_seasons:
        weeks = sorted(set(mw[seasons == season]))
        for i in range(0, len(weeks), int(cadence)):
            chunk = weeks[i:i + int(cadence)]
            rows = np.flatnonzero((seasons == season) & np.isin(mw, chunk))
            if not rows.size:
                continue
            cutoff = pd.Timestamp(dates[rows].min()).normalize()
            if (pd.to_datetime(dates[rows]) < cutoff).any():
                raise AssertionError(
                    f"{season} mw{chunk[0]}: a fixture falls before its own "
                    "cutoff day, so the fit that prices it would have seen it")
            if len(set(seasons[rows])) != 1:
                raise AssertionError("a refit block spans two seasons")
            out.append(Cutoff(season=season, matchweek=int(chunk[0]),
                              cutoff=cutoff, rows=rows,
                              match_ids=tuple(ids[rows])))

    covered = [m for c in out for m in c.match_ids]
    want = set(ids[np.isin(seasons, list(score_seasons))])
    if len(covered) != len(set(covered)) or set(covered) != want:
        raise AssertionError(
            f"the schedule prices {len(set(covered))} distinct fixtures but the "
            f"scoring window holds {len(want)}: every fixture must be priced "
            "exactly once")
    return out


# ==========================================================================
# 2. the walk
# ==========================================================================
def _health(post, cfg: dict) -> dict[str, Any]:
    """Numerical health of one fitted posterior.

    pymc 6.0.1's ``pm.fit(method="advi")`` — which is what
    ``wcmodel.model.inference.sample`` calls — installs no convergence callback,
    so "did ADVI converge" has no package-level boolean to read. What CAN be
    checked without touching ``src/`` is whether the posterior it produced is
    usable: every draw finite, both scale parameters strictly positive, and the
    fitted home advantage inside a range a league fit could plausibly occupy.
    A failure of any of these is reported per cutoff, never averaged away.
    """
    out: dict[str, Any] = {}
    finite = True
    for name in ("att", "def", "sigma_att", "sigma_def", "mu", "home_adv"):
        try:
            arr = np.asarray(post._post(name), dtype=float)
        except Exception:                                    # not in this model
            continue
        finite &= bool(np.isfinite(arr).all())
        out[f"mean_{name}"] = float(np.mean(arr))
        if name in ("sigma_att", "sigma_def"):
            out[f"min_{name}"] = float(np.min(arr))
    out["all_finite"] = bool(finite)
    out["sigma_positive"] = bool(out.get("min_sigma_att", 1.0) > 0
                                 and out.get("min_sigma_def", 1.0) > 0)
    out["home_adv_sane"] = bool(-1.0 < out.get("mean_home_adv", 0.0) < 1.0)
    return out


def _one_cutoff(cut: Cutoff, played: pd.DataFrame, store, anchor, cfg: dict,
                matches: pd.DataFrame) -> dict[str, Any]:
    """Fit at one cutoff and price every fixture in its block."""
    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        post, res = dcfit.fit_epl(cut.cutoff, store, anchor, cfg,
                                  matches=matches,
                                  feature_cache_dir=paths.FIT_CACHE_DIR)
        warns = sorted({f"{w.category.__name__}: {w.message}" for w in caught})

    home = played["home_key"].astype(str).to_numpy()[cut.rows]
    away = played["away_key"].astype(str).to_numpy()[cut.rows]
    probs, unpriceable = [], []
    for mid, h, a in zip(cut.match_ids, home, away):
        if h not in post._idx or a not in post._idx:
            probs.append([float("nan")] * 3)
            unpriceable.append({"match_id": mid, "home": h, "away": a,
                                "why": "club absent from the posterior index"})
            continue
        p = post.predict_1x2(h, a, neutral=False)
        probs.append([float(p[k]) for k in score_mod.OUTCOMES])

    arr = np.asarray(probs, dtype=float)
    bad = [m for m, row in zip(cut.match_ids, arr)
           if not (np.isfinite(row).all() and abs(row.sum() - 1.0) < 1e-9)]
    return {
        "key": cut.key, "season": cut.season, "matchweek": cut.matchweek,
        "cutoff": str(cut.cutoff.date()), "n_fixtures": len(cut.match_ids),
        "match_ids": list(cut.match_ids),
        "probs": [[round(v, 8) for v in row] for row in arr.tolist()],
        "seconds": round(time.perf_counter() - t0, 2),
        "n_training_matches": res.n_training_matches, "n_teams": res.n_teams,
        "cold_start_teams": res.cold_start_teams,
        "cold_start_z": res.cold_start_z,
        "provisional_teams": res.provisional_teams,
        "anchor_spec": res.anchor_spec,
        "warnings": warns,
        "unpriceable": unpriceable,
        "malformed": bad,
        "health": _health(post, cfg),
    }


def _validate_unique_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    """Refuse every duplicate cutoff or fixture; no first/last-write rule."""
    keys: dict[str, int] = {}
    cutoff_ids: dict[tuple[str, int, str], int] = {}
    fixtures: dict[str, tuple[int, str]] = {}
    for line_no, row in enumerate(rows, 1):
        key = str(row.get("key", ""))
        if not key:
            raise EvidenceIntegrityError(
                f"cutoff row {line_no} has no non-empty key")
        if key in keys:
            raise EvidenceIntegrityError(
                f"duplicate cutoff key {key!r} at rows {keys[key]} and "
                f"{line_no}; append-only evidence has no first/last winner")
        keys[key] = line_no

        try:
            ident = (str(row["season"]), int(row["matchweek"]),
                     str(row["cutoff"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceIntegrityError(
                f"cutoff row {line_no} lacks a valid season/matchweek/cutoff "
                f"identity") from exc
        if ident in cutoff_ids:
            raise EvidenceIntegrityError(
                f"duplicate cutoff identity {ident!r} at rows "
                f"{cutoff_ids[ident]} and {line_no}")
        cutoff_ids[ident] = line_no

        mids = [str(m) for m in row.get("match_ids", [])]
        local: set[str] = set()
        for mid in mids:
            if mid in local:
                raise EvidenceIntegrityError(
                    f"cutoff {key!r} contains duplicate fixture {mid!r}")
            local.add(mid)
            if mid in fixtures:
                prior_line, prior_key = fixtures[mid]
                raise EvidenceIntegrityError(
                    f"fixture {mid!r} appears in cutoff {prior_key!r} (row "
                    f"{prior_line}) and {key!r} (row {line_no}); it may be "
                    "priced exactly once")
            fixtures[mid] = (line_no, key)


def _read_ledger(path: Path, *, allow_legacy: bool) -> WalkLedger:
    records = []
    for line_no, text in enumerate(path.read_text().splitlines(), 1):
        if not text.strip():
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError as exc:
            raise EvidenceIntegrityError(
                f"{path}: invalid JSON on line {line_no}: {exc.msg}") from exc
        if not isinstance(record, dict):
            raise EvidenceIntegrityError(
                f"{path}: line {line_no} is not a JSON object")
        records.append((line_no, record))

    if not records:
        if allow_legacy:
            return WalkLedger()
        raise EvidenceIntegrityError(f"{path}: empty ledger has no run envelope")

    envelope_records = [(n, r) for n, r in records
                        if r.get("record_type") == _ENVELOPE_RECORD]
    if not envelope_records:
        if not allow_legacy:
            raise EvidenceIntegrityError(
                f"{path}: legacy ledger has no immutable run envelope; read it "
                "only with allow_legacy=True for non-verdict diagnostics")
        rows = [r for _, r in records]
        _validate_unique_rows(rows)
        return WalkLedger(rows)
    if len(envelope_records) != 1 or envelope_records[0][0] != records[0][0]:
        raise EvidenceIntegrityError(
            f"{path}: the run envelope must be the first and only envelope record")

    _, header = envelope_records[0]
    envelope = header.get("run_envelope")
    digest = header.get("run_envelope_sha256")
    if not isinstance(envelope, dict) or envelope.get("schema") != RUN_ENVELOPE_SCHEMA:
        raise EvidenceIntegrityError(f"{path}: invalid run envelope schema")
    if digest != _json_sha256(envelope):
        raise EvidenceIntegrityError(
            f"{path}: run envelope digest does not cover the stored envelope")

    previous: str | None = None
    for line_no, record in records:
        stored_record_sha = record.get("record_sha256")
        if (not isinstance(stored_record_sha, str)
                or not _SHA256_RE.fullmatch(stored_record_sha)
                or stored_record_sha != _record_sha256(record)):
            raise EvidenceIntegrityError(
                f"{path}: record digest mismatch on line {line_no}")
        if previous is None:
            if record.get("previous_record_sha256") is not None:
                raise EvidenceIntegrityError(
                    f"{path}: first record unexpectedly has a predecessor")
        elif record.get("previous_record_sha256") != previous:
            raise EvidenceIntegrityError(
                f"{path}: broken record chain on line {line_no}")
        previous = stored_record_sha

    rows = []
    terminal: dict[str, Any] | None = None
    for line_no, record in records[1:]:
        kind = record.get("record_type")
        if kind == _TERMINAL_RECORD:
            if terminal is not None or line_no != records[-1][0]:
                raise EvidenceIntegrityError(
                    f"{path}: terminal seal must be the final and only seal")
            terminal = record
            continue
        if kind != _CUTOFF_RECORD:
            raise EvidenceIntegrityError(
                f"{path}: unknown record_type {kind!r} on line {line_no}")
        if record.get("run_envelope_sha256") != digest:
            raise EvidenceIntegrityError(
                f"{path}: cutoff row on line {line_no} is not bound to the "
                "ledger's run envelope")
        rows.append(record)
    _validate_unique_rows(rows)
    if terminal is not None:
        n_fixtures = sum(len(r.get("match_ids", [])) for r in rows)
        expected = {
            "run_envelope_sha256": digest,
            "n_cutoffs": len(rows),
            "n_fixtures": n_fixtures,
            "run_schedule_sha256": envelope.get("run_schedule_sha256"),
            "cutoff_chain_sha256": terminal.get("previous_record_sha256"),
        }
        mismatched = {k: {"expected": v, "actual": terminal.get(k)}
                      for k, v in expected.items() if terminal.get(k) != v}
        if mismatched:
            raise EvidenceIntegrityError(
                f"{path}: terminal seal disagrees with chained evidence: "
                f"{mismatched}")
    return WalkLedger(rows, run_envelope=envelope,
                      run_envelope_sha256=str(digest),
                      terminal_seal=terminal,
                      chain_head_sha256=previous,
                      header_record_sha256=header["record_sha256"])


def _append_record(path: Path, record: Mapping[str, Any]) -> None:
    with path.open("a") as fh:
        fh.write(_canonical_json(record) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _acquire_ledger_lock(path: Path):
    """Hold one process across read/resume, every fit, append and final seal."""
    lock_path = path.with_name(path.name + ".lock")
    handle = lock_path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise EvidenceIntegrityError(
            f"{path}: another process holds the walk-forward run lock") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({"pid": os.getpid(), "ledger": str(path)}) + "\n")
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def _append_terminal_seal(path: Path, ledger: WalkLedger) -> None:
    if ledger.terminal_seal is not None:
        return
    if ledger.chain_head_sha256 is None or ledger.run_envelope is None:
        raise EvidenceIntegrityError(
            f"{path}: cannot seal a ledger without a chained envelope")
    cutoff_chain = ledger.chain_head_sha256
    record = _chain_record({
        "record_type": _TERMINAL_RECORD,
        "run_envelope_sha256": ledger.run_envelope_sha256,
        "n_cutoffs": len(ledger),
        "n_fixtures": sum(len(r.get("match_ids", [])) for r in ledger),
        "run_schedule_sha256": ledger.run_envelope.get("run_schedule_sha256"),
        "cutoff_chain_sha256": cutoff_chain,
    }, cutoff_chain)
    _append_record(path, record)
    ledger.terminal_seal = record
    ledger.chain_head_sha256 = record["record_sha256"]


def _prepare_ledger(path: Path, envelope: Mapping[str, Any], *,
                    resume: bool, publishable: bool) -> WalkLedger:
    digest = _json_sha256(envelope)
    if not path.exists() or not path.read_text().strip():
        header = _chain_record({
            "record_type": _ENVELOPE_RECORD,
            "run_envelope_sha256": digest,
            "run_envelope": dict(envelope),
        })
        _append_record(path, header)
        return WalkLedger(run_envelope=envelope,
                          run_envelope_sha256=digest,
                          chain_head_sha256=header["record_sha256"],
                          header_record_sha256=header["record_sha256"])

    if not resume:
        raise EvidenceIntegrityError(
            f"{path}: non-empty append-only ledger cannot be reused with "
            "resume=False; choose a new path")
    try:
        ledger = _read_ledger(path, allow_legacy=True)
    except EvidenceIntegrityError:
        raise
    if ledger.run_envelope is None:
        raise EvidenceIntegrityError(
            f"{path}: legacy ledgers are strictly read-only diagnostics; "
            "choose a fresh chained-ledger path")
    if ledger.run_envelope_sha256 != digest or ledger.run_envelope != dict(envelope):
        old = ledger.run_envelope.get("identity", {})
        new = envelope.get("identity", {})
        changed = sorted(k for k in set(old) | set(new)
                         if old.get(k) != new.get(k))
        if not changed:
            changed = ["schedule_or_run_parameters"]
        raise ResumeIdentityMismatch(
            f"{path}: resume envelope mismatch in {changed}; existing rows "
            "must not be mixed with a different code/data/store/config/"
            "dependency identity")
    return ledger


def _resume_schedule_blockers(
        rows: Sequence[Mapping[str, Any]], cuts: Sequence[Cutoff],
        ) -> dict[str, Any]:
    """Validate every persisted row before its key is treated as completed."""
    expected = {c.key: c for c in cuts}
    observed_keys = [str(r.get("key", "")) for r in rows]
    blockers: dict[str, Any] = {}
    extra = [key for key in observed_keys if key not in expected]
    mismatched = []
    for row in rows:
        key = str(row.get("key", ""))
        cut = expected.get(key)
        if cut is None:
            continue
        try:
            identity = (str(row.get("season")), int(row.get("matchweek")),
                        str(row.get("cutoff")))
        except (TypeError, ValueError):
            identity = ("INVALID", -1, "INVALID")
        wanted = (cut.season, int(cut.matchweek), str(cut.cutoff.date()))
        if (identity != wanted
                or [str(m) for m in row.get("match_ids", [])]
                != list(cut.match_ids)):
            mismatched.append(key)
    wanted_prefix = [c.key for c in cuts[:len(rows)]]
    if observed_keys != wanted_prefix:
        blockers["non_prefix_cutoff_order"] = {
            "expected": wanted_prefix[:20], "observed": observed_keys[:20]}
    if extra:
        blockers["extra_cutoffs"] = extra[:20]
    if mismatched:
        blockers["cutoff_schedule_mismatches"] = mismatched[:20]
    return blockers


def run_walk(matches: pd.DataFrame | None = None, cadence: int = CADENCE_WEEKS,
             ledger_path: Path | str = NEXT_LEDGER_PATH, fast_panel: bool = True,
             resume: bool = True, limit: int | None = None,
             seed: int | None = None, verbose: bool = True,
             publishable: bool = True,
             identity_hashes: Mapping[str, str] | None = None,
             ) -> dict[str, Any]:
    """Fit at every cutoff and append one ledger row per cutoff.

    Append-only and resumable: a row already in the ledger is skipped, so a
    crash costs the fit in flight and nothing else. The first JSONL record binds
    the run to code, data, logical store, configuration, dependencies and the
    exact schedule; resume refuses if any component changes. Every cutoff row
    is bound back to that envelope digest.

    ``seed`` overrides the shipped inference seed. It exists for ONE purpose:
    running the identical walk twice and measuring how much of the headline is
    ADVI optimiser noise. The reported result always comes from the frozen
    configuration's own seed; a replica is a diagnostic and is written to its
    own ledger so the two can never be mixed. A seed, limit or off-protocol
    cadence additionally requires ``publishable=False``.
    """
    if publishable and cadence != CADENCE_WEEKS:
        raise VerdictPublicationBlocked(
            {"off_protocol_cadence": int(cadence)})
    if publishable and limit is not None:
        raise VerdictPublicationBlocked({"partial_limit": int(limit)})
    if publishable and seed is not None:
        raise VerdictPublicationBlocked({"diagnostic_seed": int(seed)})
    if publishable and identity_hashes:
        raise VerdictPublicationBlocked({
            "supplied_identity_hashes": sorted(identity_hashes)})

    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    eligible_cuts = matchweek_cutoffs(played, cadence=CADENCE_WEEKS)
    cuts = matchweek_cutoffs(played, cadence=cadence)
    if limit is not None:
        if int(limit) < 0:
            raise ValueError("limit must be non-negative")
        cuts = cuts[:int(limit)]

    schedule_manifest_sha256 = None
    if publishable:
        _, schedule_manifest_sha256, schedule_blockers = (
            _publication_commitment(played, eligible_cuts))
        if schedule_blockers:
            raise VerdictPublicationBlocked(schedule_blockers)

    cfg = freeze.frozen_wcmodel_config()
    if seed is not None:
        cfg["seed"] = int(seed)
        cfg["elo"]["epl_anchor_spec"] += f"/seed={int(seed)}"
    elo_cfg = freeze.frozen_elo_config()
    envelope = _build_run_envelope(
        played=played, cfg=cfg, elo_cfg=elo_cfg,
        eligible_cuts=eligible_cuts, run_cuts=cuts, cadence=cadence,
        seed=seed, fast_panel=fast_panel, publishable=publishable,
        identity_hashes=identity_hashes,
        schedule_manifest_sha256=schedule_manifest_sha256)

    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = _acquire_ledger_lock(ledger_path)
    try:
        return _run_walk_under_lock(
            played=played, cuts=cuts, envelope=envelope, cfg=cfg,
            elo_cfg=elo_cfg, cadence=cadence, ledger_path=ledger_path,
            fast_panel=fast_panel, resume=resume,
            identity_hashes=identity_hashes, verbose=verbose,
            publishable=publishable)
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


def _run_walk_under_lock(*, played: pd.DataFrame, cuts: Sequence[Cutoff],
                         envelope: Mapping[str, Any], cfg: dict[str, Any],
                         elo_cfg: Any, cadence: int, ledger_path: Path,
                         fast_panel: bool, resume: bool,
                         identity_hashes: Mapping[str, str] | None,
                         verbose: bool, publishable: bool) -> dict[str, Any]:
    ledger = _prepare_ledger(ledger_path, envelope, resume=resume,
                             publishable=publishable)
    resume_blockers = _resume_schedule_blockers(ledger, cuts)
    if resume_blockers:
        raise EvidenceIntegrityError(
            f"{ledger_path}: persisted rows do not match the run schedule: "
            f"{resume_blockers}")
    done = {str(r["key"]) for r in ledger}

    todo = [c for c in cuts if c.key not in done]
    if ledger.terminal_seal is not None and todo:
        raise EvidenceIntegrityError(
            f"{ledger_path}: terminally sealed ledger is incomplete for this run")
    if verbose:
        print(f"[walk] {len(cuts)} cutoffs at cadence {cadence}w, "
              f"{len(done)} already in the ledger, {len(todo)} to run",
              flush=True)
    if not todo:
        _append_terminal_seal(ledger_path, ledger)
        return {"n_cutoffs": len(cuts), "n_run": 0, "seconds": 0.0,
                "ledger": str(ledger_path),
                "run_envelope_sha256": _json_sha256(envelope),
                "terminal_seal_sha256": ledger.terminal_seal["record_sha256"],
                "publishable": bool(publishable)}

    # The immutable envelope is checked before anything can fit or mutate the
    # store. A mismatch therefore refuses at the resume boundary, not after a
    # new row has already contaminated the ledger.
    store = epl_fit.build_store(played)
    if "store_sha256" not in (identity_hashes or {}):
        table = Path(store.root) / "results.parquet"
        if not table.exists():
            raise EvidenceIntegrityError(
                f"the built store has no results table at {table}")
        raw = pd.read_parquet(table)
        logical = epl_fit.to_store_frame(played)
        missing_store = set(logical.columns) - set(raw.columns)
        if missing_store:
            raise EvidenceIntegrityError(
                f"the built store lacks logical columns {sorted(missing_store)}")
        actual = raw[list(logical.columns)].copy()
        actual = actual.sort_values("match_id", kind="mergesort").reset_index(drop=True)
        want = logical.sort_values("match_id", kind="mergesort").reset_index(drop=True)
        if _frame_sha256(actual) != _frame_sha256(want):
            raise EvidenceIntegrityError(
                "the on-disk results store does not match the store identity "
                "in the run envelope")
    anchor = anchor_mod.Anchor(played, elo_cfg)

    ctx = (epl_fit.config_read_once(cfg) if fast_panel
           else _null_context())
    started = time.time()
    with ctx:
        for i, cut in enumerate(todo, 1):
            row = _one_cutoff(cut, played, store, anchor, cfg, played)
            row["cadence_weeks"] = int(cadence)
            row["off_protocol"] = bool(cadence != CADENCE_WEEKS)
            row["fast_panel"] = bool(fast_panel)
            row["record_type"] = _CUTOFF_RECORD
            row["run_envelope_sha256"] = _json_sha256(envelope)
            chained = _chain_record(row, ledger.chain_head_sha256)
            _validate_unique_rows([*ledger, chained])
            _append_record(ledger_path, chained)
            ledger.append(chained)
            ledger.chain_head_sha256 = chained["record_sha256"]
            if verbose:
                el = time.time() - started
                print(f"[walk] {i}/{len(todo)} {cut.key} "
                      f"n_train={row['n_training_matches']} "
                      f"fixtures={row['n_fixtures']} "
                      f"unpriceable={len(row['unpriceable'])} "
                      f"{row['seconds']}s  (elapsed {el/60:.1f}m, "
                      f"eta {el/i*(len(todo)-i)/60:.1f}m)", flush=True)
    _append_terminal_seal(ledger_path, ledger)
    return {"n_cutoffs": len(cuts), "n_run": len(todo),
            "seconds": round(time.time() - started, 1),
            "ledger": str(ledger_path),
            "run_envelope_sha256": _json_sha256(envelope),
            "terminal_seal_sha256": ledger.terminal_seal["record_sha256"],
            "publishable": bool(publishable)}


class _null_context:
    def __enter__(self): return None
    def __exit__(self, *a): return False


def load_ledger(path: Path | str = LEDGER_PATH, *,
                allow_legacy: bool = False) -> WalkLedger:
    """Read an unambiguous ledger; legacy input is diagnostic-only and explicit."""
    return _read_ledger(Path(path), allow_legacy=allow_legacy)


# ==========================================================================
# 3. verification
# ==========================================================================
def verify_fast_path_is_inert(cutoffs: Iterable[str], matches=None,
                              ) -> list[dict[str, Any]]:
    """Prove the panel fast path changes neither the panel nor the forecast.

    At each cutoff the feature panel is built twice — once through the shipped
    per-row ``load_config`` and once through ``epl.fit.config_read_once`` — and
    the two are compared with ``DataFrame.equals``. The check is on the object
    the model actually consumes, not on the wrapper's source code.
    """
    from wcmodel.data import features as wc_features

    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cfg = freeze.frozen_wcmodel_config()
    store = epl_fit.build_store(played)

    out = []
    for c in cutoffs:
        ts = pd.Timestamp(c).normalize()
        t0 = time.perf_counter()
        shipped = wc_features.build(ts, store, cfg)      # uncached, on purpose
        t_shipped = time.perf_counter() - t0
        with epl_fit.config_read_once(cfg):
            t0 = time.perf_counter()
            fast = wc_features.build(ts, store, cfg)
            t_fast = time.perf_counter() - t0
        out.append({
            "cutoff": str(ts.date()),
            "panel_identical": bool(shipped.equals(fast)),
            "n_rows": int(len(shipped)),
            "seconds_shipped": round(t_shipped, 2),
            "seconds_fast": round(t_fast, 3),
        })
    return out


def provisional_arm_split(ledger: list[dict[str, Any]] | None = None,
                          matches=None) -> dict[str, Any]:
    """Which arm of ``count_volatility_arm`` actually fired, per cutoff.

    The preregistration recorded, from two TUNING cutoffs, that "wcmodel's
    provisional/volatility arm (16.5-point threshold, derived at international K
    up to 40) flags NOBODY at club K". This recomputes the arm at every scoring
    cutoff that produced a provisional club and reports the split, because a
    claim measured at two cutoffs is not a claim about 212.
    """
    from wcmodel.model.volatility_diagnostic import count_volatility_arm

    # This is a diagnostic over the historical ledger, not a verdict path.
    ledger = load_ledger(allow_legacy=True) if ledger is None else ledger
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cfg = freeze.frozen_wcmodel_config()
    store = epl_fit.build_store(played)

    rows, vol_hits, few_hits = [], [], []
    with epl_fit.config_read_once(cfg):
        for r in ledger:
            if not r["provisional_teams"]:
                continue
            arm = count_volatility_arm(store, pd.Timestamp(r["cutoff"]),
                                       list(r["provisional_teams"]), config=cfg)
            for _, a in arm.iterrows():
                rec = {"cutoff": r["cutoff"], "team": str(a["team"]),
                       "games": int(a["games"]),
                       "recent_volatility": (None if pd.isna(a["recent_volatility"])
                                             else round(float(a["recent_volatility"]), 3)),
                       "volatility_flag": bool(a["volatility_flag"]),
                       "few_games_flag": bool(a["few_games_flag"]),
                       "cold_start": bool(a["team"] in r["cold_start_teams"])}
                rows.append(rec)
                (vol_hits if rec["volatility_flag"] else few_hits).append(rec)
    return {
        "n_cutoffs_with_a_provisional_club": sum(
            1 for r in ledger if r["provisional_teams"]),
        "n_team_cutoff_flags": len(rows),
        "n_volatility_arm": len(vol_hits),
        "n_few_games_arm": len(few_hits),
        "volatility_arm_teams": sorted({r["team"] for r in vol_hits}),
        "few_games_arm_teams": sorted({r["team"] for r in few_hits}),
        "detail": rows,
    }


def advi_stability(cutoffs: Iterable[str], matches=None, alt_seed: int = 987654,
                   n_fixtures: int = 10) -> list[dict[str, Any]]:
    """Refit at a different RNG seed and measure how far the forecast moves.

    THE HONEST ANSWER TO "DID ADVI CONVERGE". pymc 6.0.1's
    ``pm.fit(method="advi")`` — which is what ``wcmodel.model.inference.sample``
    calls — installs no convergence callback, so there is no package-level
    boolean to read and none is invented here. What a completed fit does
    guarantee is only that the ELBO never went NaN (pymc raises
    ``FloatingPointError`` if it does). This function supplies the missing
    evidence directly: if the variational optimum is found reliably, two runs
    that differ ONLY in the RNG seed must land in the same place, and the
    forecast difference measures how much of the reported number is optimiser
    noise. It is a DIAGNOSTIC — the reported forecasts all come from the frozen
    seed, and nothing here feeds the headline.
    """
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cfg = freeze.frozen_wcmodel_config()
    alt = json.loads(json.dumps(cfg))
    alt["seed"] = int(alt_seed)
    alt["elo"]["epl_anchor_spec"] = cfg["elo"]["epl_anchor_spec"] + f"/seed={alt_seed}"
    anchor = anchor_mod.Anchor(played, freeze.frozen_elo_config())
    store = epl_fit.build_store(played)

    out = []
    with epl_fit.config_read_once(cfg):
        for c in cutoffs:
            ts = pd.Timestamp(c).normalize()
            fut = played.loc[pd.to_datetime(played["date"]) >= ts]
            pairs = list(zip(fut["home_key"].astype(str),
                             fut["away_key"].astype(str)))[:n_fixtures]
            probs = []
            for use in (cfg, alt):
                post, _ = dcfit.fit_epl(ts, store, anchor, use, matches=played,
                                        feature_cache_dir=paths.FIT_CACHE_DIR)
                probs.append(np.array(
                    [[post.predict_1x2(h, a)[k] for k in score_mod.OUTCOMES]
                     for h, a in pairs]))
            d = np.abs(probs[0] - probs[1])
            out.append({"cutoff": str(ts.date()), "n_fixtures": len(pairs),
                        "max_abs_prob_shift": float(d.max()),
                        "mean_abs_prob_shift": float(d.mean())})
    return out


def point_in_time_canary(matches=None, cutoff="2022-01-01",
                         later="2023-01-01", tmp_root=None) -> dict[str, Any]:
    """Rewrite every result from ``cutoff`` on; demand the forecast is unmoved.

    The prereg's STOP 3. Stronger than the panel-level canary in
    ``epl/tests/test_fit.py`` because it runs the WHOLE pipeline this run uses —
    anchor, fit, cold start, ``predict_1x2`` — and compares probabilities, not
    intermediate columns. The positive control at ``later`` asserts the
    corrupted results really did land, so a canary that rewrote nothing cannot
    pass by accident.
    """
    import tempfile

    from wcmodel.data.store import BitemporalStore, Policy

    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cfg = freeze.frozen_wcmodel_config()
    anchor = anchor_mod.Anchor(played, freeze.frozen_elo_config())

    clean = epl_fit.to_store_frame(played)
    dirty = clean.copy()
    after = pd.to_datetime(dirty["date"]) >= pd.Timestamp(cutoff)
    dirty.loc[after, "home_score"] = 9
    dirty.loc[after, "away_score"] = 0

    root = Path(tmp_root or tempfile.mkdtemp(prefix="epl-canary-"))

    def _forecasts(frame, name, at):
        store = BitemporalStore(root / name)
        table = root / name / "results.parquet"
        if not table.exists():
            store.write("results", frame, policy=Policy.POINT_IN_TIME,
                        keys=["match_id"], source="canary", source_version="c")
        post, _ = dcfit.fit_epl(at, store, anchor, cfg, matches=played)
        fut = played.loc[pd.to_datetime(played["date"]) >= pd.Timestamp(at)]
        pairs = list(zip(fut["home_key"].astype(str),
                         fut["away_key"].astype(str)))[:10]
        return np.array([[post.predict_1x2(h, a)[k] for k in score_mod.OUTCOMES]
                         for h, a in pairs]), pairs

    with epl_fit.config_read_once(cfg):
        a, pairs = _forecasts(clean, "clean", cutoff)
        b, _ = _forecasts(dirty, "dirty", cutoff)
        c, _ = _forecasts(clean, "clean_late", later)
        d, _ = _forecasts(dirty, "dirty_late", later)

    identical = bool(np.array_equal(a, b))
    moved = bool(not np.array_equal(c, d))
    return {
        "cutoff": str(cutoff), "later": str(later),
        "n_rewritten": int(after.sum()), "n_fixtures_compared": len(pairs),
        "forecasts_bit_identical_before_cutoff": identical,
        "positive_control_forecasts_moved_after_cutoff": moved,
        "max_abs_diff_before_cutoff": float(np.max(np.abs(a - b))),
        "max_abs_diff_positive_control": float(np.max(np.abs(c - d))),
        "PASS": bool(identical and moved),
    }


# ==========================================================================
# 4. scoring
# ==========================================================================
def _bootstrap(d: np.ndarray, blocks: Sequence[Any], n_boot: int) -> dict:
    lo, hi, nb = score_mod.block_bootstrap_ci(d, blocks, n_boot=n_boot)
    return {"ci95": [lo, hi], "n_blocks": int(nb)}


def _pair(name_a: str, a: np.ndarray, name_b: str, b: np.ndarray,
          week: Sequence[Any], season: Sequence[Any], n_boot: int) -> dict:
    d, mean, sd = score_mod.paired_gap(name_a, a, name_b, b)
    out = {"a": name_a, "b": name_b, "n": int(d.size), "mean": mean, "sd": sd,
           "se_iid": float(sd / np.sqrt(d.size))}
    out["week"] = _bootstrap(d, week, n_boot)
    out["season"] = _bootstrap(d, season, n_boot)
    return out


def _schedule_blockers(rows: Sequence[Mapping[str, Any]],
                       expected: Sequence[Cutoff]) -> dict[str, Any]:
    expected_keys = [c.key for c in expected]
    observed_keys = [str(r.get("key", "")) for r in rows]
    expected_by_key = {c.key: list(c.match_ids) for c in expected}
    observed_by_key = {str(r.get("key", "")):
                       [str(m) for m in r.get("match_ids", [])]
                       for r in rows}
    out: dict[str, Any] = {}
    missing = [k for k in expected_keys if k not in observed_by_key]
    extra = [k for k in observed_keys if k not in expected_by_key]
    mismatched = [k for k in expected_keys
                  if k in observed_by_key
                  and observed_by_key[k] != expected_by_key[k]]
    if missing:
        out["missing_cutoffs"] = missing[:20]
    if extra:
        out["extra_cutoffs"] = extra[:20]
    if mismatched:
        out["cutoff_fixture_mismatches"] = mismatched[:20]
    identity_mismatches = []
    expected_identity = {
        c.key: (c.season, int(c.matchweek), str(c.cutoff.date()))
        for c in expected
    }
    for row in rows:
        key = str(row.get("key", ""))
        if key not in expected_identity:
            continue
        try:
            observed = (str(row.get("season")), int(row.get("matchweek")),
                        str(row.get("cutoff")))
        except (TypeError, ValueError):
            observed = ("INVALID", -1, "INVALID")
        if observed != expected_identity[key]:
            identity_mismatches.append(key)
    if identity_mismatches:
        out["cutoff_identity_mismatches"] = identity_mismatches[:20]
    if not missing and not extra and observed_keys != expected_keys:
        out["cutoff_order_mismatch"] = True
    shape = []
    for row in rows:
        mids = list(row.get("match_ids", []))
        probs = list(row.get("probs", []))
        declared = row.get("n_fixtures")
        if declared != len(mids) or len(probs) != len(mids):
            shape.append({"key": row.get("key"), "n_fixtures": declared,
                          "n_match_ids": len(mids), "n_probs": len(probs)})
    if shape:
        out["cutoff_row_shape_mismatches"] = shape[:20]
    return out


def _collect_predictions(rows: Sequence[Mapping[str, Any]],
                         ) -> tuple[dict[str, list[float]], dict[str, Any],
                                    list[dict[str, Any]], list[str]]:
    dc: dict[str, list[float]] = {}
    unpriceable: list[dict[str, Any]] = []
    declared_malformed: list[str] = []
    nonfinite, nonsimplex, unparseable = [], [], []
    unhealthy, off_protocol, declared_stop = [], [], []
    missing_evidence_fields = []

    def _active_stop(value: Any) -> bool:
        if isinstance(value, Mapping):
            return any(_active_stop(v) for v in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(_active_stop(v) for v in value)
        return bool(value)

    for row in rows:
        key = str(row.get("key", ""))
        required = {"match_ids", "probs", "unpriceable", "malformed",
                    "health", "off_protocol"}
        absent = sorted(required - set(row))
        if absent:
            missing_evidence_fields.append({"key": key, "fields": absent})
        mids = [str(m) for m in row.get("match_ids", [])]
        probs = list(row.get("probs", []))
        for mid, p in zip(mids, probs):
            try:
                values = [float(v) for v in p]
            except (TypeError, ValueError):
                unparseable.append(mid)
                continue
            if len(values) != len(score_mod.OUTCOMES):
                unparseable.append(mid)
                continue
            arr = np.asarray(values, dtype=float)
            if not np.isfinite(arr).all():
                nonfinite.append(mid)
                continue
            if ((arr < 0).any() or (arr > 1).any()
                    or abs(float(arr.sum()) - 1.0) > _STORED_PROB_SUM_ATOL):
                nonsimplex.append(mid)
                continue
            dc[mid] = values
        unpriceable.extend(row.get("unpriceable", []) or [])
        declared_malformed.extend(str(m) for m in
                                  (row.get("malformed", []) or []))
        health = row.get("health") or {}
        if not (health.get("all_finite", False)
                and health.get("sigma_positive", False)
                and health.get("home_adv_sane", False)):
            unhealthy.append(key)
        if row.get("off_protocol"):
            off_protocol.append(key)
        status = str(row.get("status", row.get("outcome", ""))).upper()
        if (_active_stop(row.get("stop")) or _active_stop(row.get("stopped"))
                or _active_stop(row.get("stops"))
                or status in {"STOP", "STOPPED", "FAIL", "FAILED"}):
            declared_stop.append(key)

    blockers: dict[str, Any] = {}
    if unpriceable:
        blockers["unpriceable_fixtures"] = len(unpriceable)
    if declared_malformed:
        blockers["declared_malformed_forecasts"] = len(declared_malformed)
    if nonfinite:
        blockers["nonfinite_forecasts"] = nonfinite[:20]
    if nonsimplex:
        blockers["non_simplex_forecasts"] = nonsimplex[:20]
    if unparseable:
        blockers["unparseable_forecasts"] = unparseable[:20]
    if unhealthy:
        blockers["unhealthy_cutoffs"] = unhealthy[:20]
    if off_protocol:
        blockers["off_protocol_cutoffs"] = off_protocol[:20]
    if declared_stop:
        blockers["declared_stop_cutoffs"] = declared_stop[:20]
    if missing_evidence_fields:
        blockers["missing_evidence_fields"] = missing_evidence_fields[:20]
    return dc, blockers, unpriceable, declared_malformed


def _ledger_envelope(ledger: Sequence[Mapping[str, Any]],
                     supplied: Mapping[str, Any] | None,
                     ) -> tuple[dict[str, Any] | None, str | None]:
    embedded = getattr(ledger, "run_envelope", None)
    embedded_digest = getattr(ledger, "run_envelope_sha256", None)
    if embedded is not None and supplied is not None and dict(embedded) != dict(supplied):
        raise EvidenceIntegrityError(
            "the supplied run envelope disagrees with the ledger header")
    envelope = dict(embedded or supplied) if (embedded or supplied) else None
    digest = _json_sha256(envelope) if envelope is not None else None
    if embedded_digest is not None and embedded_digest != digest:
        raise EvidenceIntegrityError(
            "the ledger's envelope digest disagrees with its envelope")
    return envelope, digest


def _ledger_chain_blockers(ledger: Sequence[Mapping[str, Any]],
                           envelope: Mapping[str, Any] | None,
                           envelope_digest: str | None) -> dict[str, Any]:
    """Recheck the in-memory chain; publication never trusts list attributes."""
    if not isinstance(ledger, WalkLedger):
        return {"chained_ledger": "publishable scoring requires a loaded ledger"}
    if envelope is None or envelope_digest is None:
        return {"chained_ledger": "missing envelope"}
    header_sha = ledger.header_record_sha256
    expected_header = _chain_record({
        "record_type": _ENVELOPE_RECORD,
        "run_envelope_sha256": envelope_digest,
        "run_envelope": dict(envelope),
    })["record_sha256"]
    if header_sha != expected_header:
        return {"chained_ledger": "header record digest mismatch"}
    previous = header_sha
    for i, row in enumerate(ledger, 1):
        if (row.get("previous_record_sha256") != previous
                or row.get("record_sha256") != _record_sha256(row)):
            return {"chained_ledger": f"broken cutoff record {i}"}
        previous = row.get("record_sha256")
    terminal = ledger.terminal_seal
    if not isinstance(terminal, dict):
        return {"terminal_seal": "missing"}
    if (terminal.get("previous_record_sha256") != previous
            or terminal.get("record_sha256") != _record_sha256(terminal)):
        return {"terminal_seal": "broken record chain"}
    expected_terminal = {
        "run_envelope_sha256": envelope_digest,
        "n_cutoffs": len(ledger),
        "n_fixtures": sum(len(r.get("match_ids", [])) for r in ledger),
        "run_schedule_sha256": envelope.get("run_schedule_sha256"),
        "cutoff_chain_sha256": previous,
    }
    bad = {k: {"expected": v, "actual": terminal.get(k)}
           for k, v in expected_terminal.items() if terminal.get(k) != v}
    return {"terminal_seal": bad} if bad else {}


def score_run(ledger: list[dict[str, Any]] | None = None,
              matches: pd.DataFrame | None = None,
              n_boot: int = 10_000, *, publishable: bool = True,
              strict_diagnostic: bool = False,
              run_envelope: Mapping[str, Any] | None = None,
              identity_hashes: Mapping[str, str] | None = None,
              ) -> dict[str, Any]:
    """Score DC, Elo and the market on ONE complete-case match set.

    The Elo and market columns are not re-derived here: they come from
    ``epl.baseline.evaluate`` under the frozen Elo configuration, which is the
    same function and the same configuration that produced the published
    baseline. The only new column is the model's. In the default publishable
    mode, an envelope mismatch, a schedule difference, any recorded STOP, or a
    missing/malformed/nonfinite forecast raises before a verdict can be
    returned. ``publishable=False`` is explicit development compatibility: it
    may compute diagnostics on a partial ledger, but returns no verdict.
    ``strict_diagnostic=True`` is the legacy-replay path: it remains a
    non-verdict, but fails closed unless the committed schedule and sources are
    complete and unchanged.
    """
    if publishable and identity_hashes:
        raise VerdictPublicationBlocked({
            "supplied_identity_hashes": sorted(identity_hashes)})
    ledger = load_ledger(allow_legacy=not publishable) if ledger is None else ledger
    _validate_unique_rows(ledger)
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])

    schedule_manifest_sha256 = None
    commitment_blockers: dict[str, Any] = {}
    if publishable or strict_diagnostic:
        actual_cuts = matchweek_cutoffs(played, cadence=CADENCE_WEEKS)
        expected_cuts, schedule_manifest_sha256, commitment_blockers = (
            _publication_commitment(played, actual_cuts))
    else:
        expected_cuts = matchweek_cutoffs(played, cadence=CADENCE_WEEKS)
    envelope, envelope_digest = _ledger_envelope(ledger, run_envelope)
    blockers: dict[str, Any] = dict(commitment_blockers)
    if publishable:
        if (isinstance(n_boot, bool) or not isinstance(n_boot, (int, np.integer))
                or int(n_boot) != 10_000):
            blockers["bootstrap_resamples"] = {
                "required": 10_000, "received": n_boot}
        if envelope is None:
            blockers["run_envelope"] = "missing"
        else:
            if envelope.get("schema") != RUN_ENVELOPE_SCHEMA:
                blockers["run_envelope_schema"] = envelope.get("schema")
            if not envelope.get("publishable", False):
                blockers["run_envelope_publishable"] = False
            supplied_sources = [
                name for name, source in
                (envelope.get("identity_sources") or {}).items()
                if source != "computed"]
            if supplied_sources:
                blockers["run_envelope_supplied_identity"] = supplied_sources
            cfg = freeze.frozen_wcmodel_config()
            elo_cfg_for_envelope = freeze.frozen_elo_config()
            current = _build_run_envelope(
                played=played, cfg=cfg, elo_cfg=elo_cfg_for_envelope,
                eligible_cuts=expected_cuts, run_cuts=expected_cuts,
                cadence=CADENCE_WEEKS, seed=None,
                fast_panel=bool(envelope.get("fast_panel", True)),
                publishable=True, identity_hashes=None,
                schedule_manifest_sha256=schedule_manifest_sha256)
            if current != envelope:
                changed = [k for k in current.get("identity", {})
                           if current["identity"].get(k)
                           != envelope.get("identity", {}).get(k)]
                blockers["run_envelope_mismatch"] = (
                    changed or ["schedule_or_run_parameters"])
            unbound = [str(r.get("key")) for r in ledger
                       if r.get("run_envelope_sha256") != envelope_digest]
            if unbound:
                blockers["cutoffs_not_bound_to_envelope"] = unbound[:20]
        blockers.update(_ledger_chain_blockers(
            ledger, envelope, envelope_digest))
    blockers.update(_schedule_blockers(ledger, expected_cuts))
    dc, forecast_blockers, unpriceable, malformed = _collect_predictions(ledger)
    blockers.update(forecast_blockers)
    expected_ids = [mid for cut in expected_cuts for mid in cut.match_ids]
    missing_expected = [mid for mid in expected_ids if mid not in dc]
    extra_forecasts = [mid for mid in dc if mid not in set(expected_ids)]
    if missing_expected:
        blockers["missing_forecasts"] = missing_expected[:20]
    if extra_forecasts:
        blockers["extra_forecasts"] = extra_forecasts[:20]
    if blockers:
        if publishable:
            raise VerdictPublicationBlocked(blockers)
        if strict_diagnostic:
            raise EvidenceIntegrityError(
                f"strict diagnostic scoring blocked: {blockers}")

    # --- the comparator and the benchmark, from the baseline itself ---------
    elo_cfg = freeze.frozen_elo_config()
    ev = baseline.evaluate(played, elo_cfg, windows.SCORE_SEASONS,
                           require_odds=True)
    frame = ev.frame.copy()

    # --- the model's column -------------------------------------------------
    ids = frame["match_id"].astype(str).to_numpy()
    if list(ids) != expected_ids:
        same_members = (len(ids) == len(set(ids)) == len(expected_ids)
                        and set(ids) == set(expected_ids))
        blockers["eligible_frame_schedule_mismatch"] = {
            "expected": len(expected_ids), "eligible": len(ids),
            "same_members": same_members,
        }
        if same_members:
            frame = (frame.assign(match_id=frame["match_id"].astype(str))
                     .set_index("match_id", drop=False)
                     .loc[expected_ids].reset_index(drop=True))
            ids = frame["match_id"].astype(str).to_numpy()
            blockers.pop("eligible_frame_schedule_mismatch", None)
        elif publishable:
            raise VerdictPublicationBlocked(blockers)
        elif strict_diagnostic:
            raise EvidenceIntegrityError(
                f"strict diagnostic scoring blocked: {blockers}")
    missing = [m for m in ids if m not in dc]
    arr = np.array([dc.get(m, [np.nan] * 3) for m in ids], dtype=float)
    finite = (np.isfinite(arr).all(axis=1)
              & (arr >= 0).all(axis=1) & (arr <= 1).all(axis=1)
              & np.isclose(arr.sum(axis=1), 1.0,
                           atol=_STORED_PROB_SUM_ATOL, rtol=0.0))
    for j, o in enumerate(score_mod.OUTCOMES):
        frame[f"dc_{o}"] = arr[:, j]

    keep = finite
    n_dropped = int((~keep).sum())
    frame = frame.loc[keep].reset_index(drop=True)
    arr = arr[keep]

    y = frame["y"].to_numpy()
    r = {"dc": score_mod.rps(arr, y)}
    frame["dc_rps"] = r["dc"]
    for name in ("elo", "market", "market_shin", "base"):
        r[name] = frame[f"{name}_rps"].to_numpy()
    ll = {"dc": score_mod.log_loss(arr, y)}
    for name in ("elo", "market", "market_shin", "base"):
        p = frame[[f"{name}_{o}" for o in score_mod.OUTCOMES]].to_numpy(float)
        ll[name] = score_mod.log_loss(p, y)

    scores = {"dc": score_mod.summarise("dc", arr, y).as_dict()}
    for name in ("elo", "market", "market_shin", "base"):
        p = frame[[f"{name}_{o}" for o in score_mod.OUTCOMES]].to_numpy(float)
        scores[name] = score_mod.summarise(name, p, y).as_dict()

    week = frame["block"].to_numpy()
    season = frame["season"].to_numpy()
    gaps = {}
    for a, b in (("dc", "elo"), ("dc", "market"), ("dc", "market_shin"),
                 ("dc", "base"), ("elo", "market")):
        gaps[f"{a}_minus_{b}"] = _pair(a, r[a], b, r[b], week, season, n_boot)
        gaps[f"{a}_minus_{b}"]["log_loss"] = _pair(
            a, ll[a], b, ll[b], week, season, n_boot)

    per_season = (frame.assign(dc_ll=ll["dc"], elo_ll=ll["elo"],
                               market_ll=ll["market"])
                  .groupby("season")
                  .agg(n=("match_id", "size"), dc=("dc_rps", "mean"),
                       elo=("elo_rps", "mean"), market=("market_rps", "mean"),
                       base=("base_rps", "mean"), dc_ll=("dc_ll", "mean"),
                       elo_ll=("elo_ll", "mean"), market_ll=("market_ll", "mean"))
                  .reset_index())
    per_season["dc_minus_elo"] = per_season["dc"] - per_season["elo"]
    per_season["dc_minus_market"] = per_season["dc"] - per_season["market"]

    # --- subsets that a single mean would hide ------------------------------
    prom = (frame["home_promoted"] | frame["away_promoted"]).to_numpy()
    subsets = {}
    for label, mask in (("all", np.ones(len(frame), bool)),
                        ("promoted", prom), ("established", ~prom)):
        if mask.sum() < 50:
            continue
        d = r["dc"][mask] - r["elo"][mask]
        subsets[label] = {
            "n": int(mask.sum()), "dc": float(r["dc"][mask].mean()),
            "elo": float(r["elo"][mask].mean()),
            "market": float(r["market"][mask].mean()),
            "dc_minus_elo": float(d.mean()),
            **_bootstrap(d, week[mask], n_boot),
        }

    # --- calibration smell test ---------------------------------------------
    calib = {"realised": {o: float((y == k).mean())
                          for k, o in enumerate(score_mod.OUTCOMES)}}
    for name in ("dc", "elo", "market", "base"):
        calib[name] = {o: float(frame[f"{name}_{o}"].mean())
                       for o in score_mod.OUTCOMES}

    # --- run diagnostics off the ledger --------------------------------------
    seconds = [float(r.get("seconds", 0.0)) for r in ledger]
    training = [int(r.get("n_training_matches", 0)) for r in ledger]
    diag = {
        "n_cutoffs": len(ledger),
        "cutoffs_with_warnings": [r["key"] for r in ledger
                                  if r.get("warnings")],
        "distinct_warnings": sorted({w for r in ledger
                                     for w in (r.get("warnings") or [])}),
        "cutoffs_unhealthy": [
            r["key"] for r in ledger
            if r.get("health") and not (
                r["health"].get("all_finite", False)
                and r["health"].get("sigma_positive", False)
                and r["health"].get("home_adv_sane", False))],
        "cold_start_events": [
            {"cutoff": r["cutoff"], "clubs": r["cold_start_teams"],
             "z": r["cold_start_z"]}
            for r in ledger if r.get("cold_start_teams")],
        "n_cutoffs_with_a_provisional_club": sum(
            1 for r in ledger if r.get("provisional_teams")),
        "total_fit_seconds": round(sum(seconds), 1),
        "median_fit_seconds": (float(np.median(seconds)) if seconds else None),
        "n_training_matches_range": ([min(training), max(training)]
                                     if training else None),
        "anchor_specs": sorted({str(r.get("anchor_spec")) for r in ledger
                                if r.get("anchor_spec") is not None}),
        "cadence_weeks": sorted({r.get("cadence_weeks", 1) for r in ledger}),
        "off_protocol_cutoffs": [r["key"] for r in ledger
                                 if r.get("off_protocol")],
        "run_envelope_sha256": envelope_digest,
    }

    # --- the preregistered verdict ------------------------------------------
    # THE BLOCKING IS THE PREREGISTERED ONE. `reports/epl_prereg.md` §3 fixes it
    # as "(season, ISO calendar week) blocks — 212 of them on this scoring
    # window — with 10,000 resamples", so the week-block CI decides the verdict
    # and the season-block CI is reported beside it. Choosing between them after
    # seeing which classifies more favourably would be exactly the move this
    # preregistration exists to prevent, so BOTH classifications are computed
    # and both are reported, whichever way they fall.
    g = gaps["dc_minus_elo"]
    mde = 0.0034

    def _classify(lo: float, hi: float, delta: float) -> tuple[str, str]:
        if delta <= -mde and hi < 0:
            return "PASS", "delta at or beyond the MDE with the CI below zero"
        if lo > 0:
            return "REJECT", "the whole CI is above zero: the model is worse"
        if lo > -mde and hi < mde:
            return "INCONCLUSIVE (precise null)", (
                "the CI lies strictly inside (-0.0034, +0.0034): no improvement "
                "larger than the MDE survives, which is a real finding")
        return "INCONCLUSIVE (underpowered)", (
            "the CI spans the MDE: this run has not ruled out an effect of the "
            "size the pass rule was built to detect")

    delta = g["mean"]
    classified, classified_detail = _classify(*g["week"]["ci95"], delta)
    alt_classified, alt_classified_detail = _classify(
        *g["season"]["ci95"], delta)

    stops = {
        "too_good_vs_market": bool(gaps["dc_minus_market"]["mean"] <= -0.002
                                   and gaps["dc_minus_market"]["season"]["ci95"][1] < 0),
        "unpriceable_fixtures": int(len(unpriceable)),
        "missing_forecasts": int(len(missing)),
        "invalid_or_nonfinite_forecasts": int(n_dropped),
        "malformed_forecasts": int(len(malformed)),
        "input_blockers": blockers,
    }
    active_stops = {k: v for k, v in stops.items()
                    if ((isinstance(v, bool) and v)
                        or (isinstance(v, int) and not isinstance(v, bool) and v > 0)
                        or (k == "input_blockers" and bool(v)))}
    if active_stops:
        if publishable:
            raise VerdictPublicationBlocked(active_stops)
        if strict_diagnostic:
            raise EvidenceIntegrityError(
                f"strict diagnostic scoring blocked: {active_stops}")

    verdict = classified if publishable else None
    detail = (classified_detail if publishable else
              "not published: explicit non-verdict/development scoring mode")
    alt_verdict = alt_classified if publishable else None
    alt_detail = (alt_classified_detail if publishable else
                  "not published: explicit non-verdict/development scoring mode")

    return {
        "n_matches": int(len(frame)),
        "n_expected": int(len(expected_ids)),
        "n_dropped_incomplete": n_dropped,
        "missing_from_ledger": missing[:20],
        "unpriceable": unpriceable,
        "malformed": malformed,
        "scores": scores,
        "gaps": gaps,
        "per_season": per_season.to_dict(orient="records"),
        "subsets": subsets,
        "calibration": calib,
        "diagnostics": diag,
        "verdict": verdict,
        "verdict_detail": detail,
        "verdict_publishable": bool(publishable),
        "diagnostic_integrity_complete": bool(
            not publishable and strict_diagnostic),
        "diagnostic_classification": (None if publishable else classified),
        "diagnostic_classification_detail": (
            None if publishable else classified_detail),
        "diagnostic_classification_if_blocked_by_season": (
            None if publishable else alt_classified),
        "diagnostic_classification_if_blocked_by_season_detail": (
            None if publishable else alt_classified_detail),
        "verdict_blocking": "(season, ISO week) — the preregistered blocking",
        "verdict_if_blocked_by_season": alt_verdict,
        "verdict_if_blocked_by_season_detail": alt_detail,
        "mde_preregistered": mde,
        "realised_paired_sd_dc_vs_elo": g["sd"],
        "realised_mde_80pct": round(float(2.802 * g["sd"] / np.sqrt(g["n"])), 5),
        "stops": stops,
        "run_envelope": envelope,
        "ledger_terminal_seal": (
            getattr(ledger, "terminal_seal", None) if publishable else None),
        "frame": frame,
    }


# ==========================================================================
# 5. CLI
# ==========================================================================
def _default_score_seal_path(result_path: Path) -> Path:
    return result_path.with_name(result_path.name + ".seal.json")


def _write_scored_outputs_no_clobber(
        result: Mapping[str, Any], frame: pd.DataFrame, *,
        result_path: Path | str, predictions_path: Path | str,
        seal_path: Path | str | None = None) -> dict[str, Any]:
    """Write a result pair once, then bind both outputs in a sidecar seal."""
    result_path = Path(result_path)
    predictions_path = Path(predictions_path)
    seal_path = Path(seal_path or _default_score_seal_path(result_path))
    targets = (result_path, predictions_path, seal_path)
    resolved = [path.resolve(strict=False) for path in targets]
    if len(set(resolved)) != len(resolved):
        raise EvidenceIntegrityError(
            f"scored evidence paths must be distinct: {[str(p) for p in targets]}")
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise EvidenceIntegrityError(
            f"refusing to overwrite scored evidence: {existing}")
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)

    result_text = json.dumps(dict(result), indent=2, default=str) + "\n"
    temporary: list[Path] = []
    try:
        with tempfile.NamedTemporaryFile(
                dir=result_path.parent, prefix=f".{result_path.name}.",
                suffix=".tmp", delete=False) as fh:
            result_tmp = Path(fh.name)
            temporary.append(result_tmp)
            fh.write(result_text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        with tempfile.NamedTemporaryFile(
                dir=predictions_path.parent,
                prefix=f".{predictions_path.name}.", suffix=".tmp",
                delete=False) as fh:
            predictions_tmp = Path(fh.name)
            temporary.append(predictions_tmp)
        frame.to_parquet(predictions_tmp)
        with predictions_tmp.open("rb") as fh:
            os.fsync(fh.fileno())

        # Hard links are an atomic no-replace publication primitive. The seal is
        # written last, so two data files without a seal are visibly incomplete.
        os.link(result_tmp, result_path)
        os.link(predictions_tmp, predictions_path)
        result_tmp.unlink()
        predictions_tmp.unlink()
        temporary.clear()

        terminal = result.get("ledger_terminal_seal") or {}
        seal = {
            "schema": _SCORE_SEAL_SCHEMA,
            "result": {"path": str(result_path),
                       "sha256": _file_sha256(result_path)},
            "predictions": {"path": str(predictions_path),
                            "sha256": _file_sha256(predictions_path)},
            "ledger_terminal_record_sha256": terminal.get("record_sha256"),
        }
        with seal_path.open("x") as fh:
            fh.write(json.dumps(seal, indent=2, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except FileExistsError as exc:
        raise EvidenceIntegrityError(
            "scored evidence appeared concurrently; nothing was overwritten") from exc
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return {**seal, "seal_path": str(seal_path)}


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--walk", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--canary", action="store_true")
    ap.add_argument("--advi-stability", action="store_true")
    ap.add_argument("--cadence", type=int, default=CADENCE_WEEKS)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None,
                    help="DIAGNOSTIC replica at a different ADVI seed; writes "
                         "its own ledger and never feeds the headline")
    ap.add_argument("--n-boot", type=int, default=10_000)
    ap.add_argument("--no-fast-panel", action="store_true")
    ap.add_argument("--ledger-path", type=Path, default=None,
                    help="explicit chained ledger; publishable default is the "
                         "versioned v2 path")
    ap.add_argument("--result-path", type=Path, default=None)
    ap.add_argument("--predictions-path", type=Path, default=None)
    ap.add_argument("--seal-path", type=Path, default=None)
    ap.add_argument("--diagnostic-score", action="store_true",
                    help="score a legacy/partial ledger without publishing a "
                         "verdict; writes nothing unless output paths are explicit")
    args = ap.parse_args()
    paths.FIT_DIR.mkdir(parents=True, exist_ok=True)

    if args.verify:
        out = verify_fast_path_is_inert(
            ["2019-08-09", "2021-12-26", "2024-05-19"])
        print(json.dumps(out, indent=2))
        assert all(o["panel_identical"] for o in out)

    if args.canary:
        out = point_in_time_canary()
        print(json.dumps(out, indent=2))

    if args.advi_stability:
        out = advi_stability(["2019-11-02", "2020-02-01", "2020-12-12",
                              "2021-04-10", "2021-11-06", "2022-03-05",
                              "2022-11-05", "2023-03-11", "2023-12-09",
                              "2024-04-13", "2024-11-09", "2025-03-08"])
        print(json.dumps(out, indent=2))

    if args.walk:
        # Supplying any of these flags is the explicit request for a diagnostic
        # run. Such a ledger is envelope-bound but can never publish a verdict.
        dev_run = bool(args.seed is not None or args.limit is not None
                       or args.cadence != CADENCE_WEEKS)
        if dev_run and args.ledger_path is None:
            ap.error("diagnostic --walk runs require an explicit --ledger-path")
        ledger_path = args.ledger_path or NEXT_LEDGER_PATH
        out = run_walk(cadence=args.cadence, limit=args.limit,
                       seed=args.seed,
                       ledger_path=ledger_path,
                       fast_panel=not args.no_fast_panel,
                       publishable=not dev_run)
        print(json.dumps(out, indent=2))

    if args.score:
        score_ledger = args.ledger_path or (
            LEDGER_PATH if args.diagnostic_score else NEXT_LEDGER_PATH)
        loaded = load_ledger(
            score_ledger, allow_legacy=bool(args.diagnostic_score))
        res = score_run(ledger=loaded, n_boot=args.n_boot,
                        publishable=not args.diagnostic_score,
                        strict_diagnostic=bool(args.diagnostic_score))
        frame = res.pop("frame")
        explicit_outputs = any((args.result_path, args.predictions_path,
                                args.seal_path))
        if args.diagnostic_score and explicit_outputs and not (
                args.result_path and args.predictions_path):
            ap.error("diagnostic output requires both --result-path and "
                     "--predictions-path")
        if not args.diagnostic_score or explicit_outputs:
            result_path = args.result_path or NEXT_RESULT_PATH
            predictions_path = (args.predictions_path
                                or NEXT_PREDICTIONS_PATH)
            seal = _write_scored_outputs_no_clobber(
                res, frame, result_path=result_path,
                predictions_path=predictions_path,
                seal_path=args.seal_path)
            print(f"sealed scored outputs: {seal['seal_path']}")
        for name, s in res["scores"].items():
            print(f"{name:12s} n={s['n']:5d} RPS {s['rps']:.5f} "
                  f"logloss {s['log_loss']:.4f} acc {s['accuracy']:.4f}")
        g = res["gaps"]["dc_minus_elo"]
        print(f"\nDC - Elo: {g['mean']:+.5f}  paired sd {g['sd']:.5f}  "
              f"95% CI (season) [{g['season']['ci95'][0]:+.5f}, "
              f"{g['season']['ci95'][1]:+.5f}]  "
              f"(week) [{g['week']['ci95'][0]:+.5f}, {g['week']['ci95'][1]:+.5f}]")
        if args.diagnostic_score:
            print("DIAGNOSTIC ONLY: "
                  f"{res['diagnostic_classification']} — "
                  f"{res['diagnostic_classification_detail']}")
        else:
            print(f"VERDICT: {res['verdict']} — {res['verdict_detail']}")


if __name__ == "__main__":
    _cli()
