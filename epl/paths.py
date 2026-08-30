"""Filesystem locations for the EPL probe.

Everything the probe writes lives under `data/epl/`, which is covered by the
repo-root-anchored `/data/` rule in .gitignore (verified with `git check-ignore`).
Raw source CSVs are cached verbatim and are never rewritten in place.
"""

from __future__ import annotations

from pathlib import Path

# epl/paths.py -> epl/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = REPO_ROOT / "data" / "epl"
RAW_DIR = DATA_DIR / "raw"

#: Verbatim source CSVs plus the provenance sidecar that describes them.
PROVENANCE_PATH = RAW_DIR / "provenance.json"

#: Tidy match table — the one artifact downstream code should read.
MATCHES_PARQUET = DATA_DIR / "matches.parquet"
MATCHES_CSV = DATA_DIR / "matches.csv"

#: Per-season row counts, date ranges, odds coverage, hashes, check results.
MANIFEST_PATH = DATA_DIR / "manifest.json"

#: raw club name -> canonical name -> stable key, with per-season occurrences.
TEAM_MAPPING_PATH = DATA_DIR / "team_name_mapping.json"

# --- second division (E1, EFL Championship) --------------------------------
# A SEPARATE FILE PER ARTIFACT, not a division column inside the E0 ones. Two
# reasons, and the first is the one that matters: `data/epl/matches.parquet` is
# pinned byte-for-byte and read by the Elo anchor, so nothing this ingest does
# may rewrite it, and the safest way to guarantee that is for the E1 build to
# have nowhere to write except its own paths. The second is that the provenance
# sidecar is keyed by season code alone, so an E1 record written into it would
# OVERWRITE the E0 record for the same season rather than sit beside it.
#
# The E1 match table carries the SAME columns as the E0 one — the division is
# carried by the file name, the manifest and the id recipe, not by a column —
# so any reader of one reads the other unchanged.
MATCHES_E1_PARQUET = DATA_DIR / "matches_e1.parquet"
MANIFEST_E1_PATH = DATA_DIR / "manifest_e1.json"
TEAM_MAPPING_E1_PATH = DATA_DIR / "team_name_mapping_e1.json"
PROVENANCE_E1_PATH = RAW_DIR / "provenance_e1.json"

#: division -> artifact kind -> (which directory, file name). Names rather than
#: assembled paths, so the accessors read DATA_DIR / RAW_DIR at CALL time: a
#: test can point the whole data root at a temporary directory and be certain
#: nothing it does can reach the pinned archive.
_DIVISION_ARTIFACTS: dict[str, dict[str, tuple[str, str]]] = {
    "E0": {
        "matches": ("data", "matches.parquet"),
        "manifest": ("data", "manifest.json"),
        "team_mapping": ("data", "team_name_mapping.json"),
        "provenance": ("raw", "provenance.json"),
    },
    "E1": {
        "matches": ("data", "matches_e1.parquet"),
        "manifest": ("data", "manifest_e1.json"),
        "team_mapping": ("data", "team_name_mapping_e1.json"),
        "provenance": ("raw", "provenance_e1.json"),
    },
}


def _artifact(division: str, kind: str) -> Path:
    try:
        where, name = _DIVISION_ARTIFACTS[division][kind]
    except KeyError as exc:
        raise KeyError(
            f"no {kind} path registered for division {division!r}; known "
            f"divisions are {sorted(_DIVISION_ARTIFACTS)}. Register its paths "
            f"here rather than composing one at the call site — a composed "
            f"path is how two divisions end up sharing a file."
        ) from exc
    return (DATA_DIR if where == "data" else RAW_DIR) / name


def matches_parquet(division: str = "E0") -> Path:
    """The tidy match table for one division. E0 is the pinned archive."""
    return _artifact(division, "matches")


def manifest_path(division: str = "E0") -> Path:
    return _artifact(division, "manifest")


def team_mapping_path(division: str = "E0") -> Path:
    return _artifact(division, "team_mapping")


def provenance_path(division: str = "E0") -> Path:
    """Provenance sidecar for one division's raw CSVs. One file per division."""
    return _artifact(division, "provenance")

# --- baseline (walk-forward Elo vs the market) -----------------------------
#: Everything the baseline writes. Under data/, so gitignored like the rest.
BASELINE_DIR = DATA_DIR / "baseline"

#: The frozen Elo hyperparameters plus the whole grid that produced them.
#: Written by `python -m epl.baseline --tune` on the TUNING seasons only.
TUNING_PATH = BASELINE_DIR / "tuning.json"

#: Per-match probabilities for every forecaster on the complete-case scoring
#: set, with the realised outcome and the bootstrap block label.
BASELINE_PREDICTIONS = BASELINE_DIR / "predictions.parquet"

#: Headline scores, paired gaps, bootstrap CIs, per-season breakdown.
SCORES_PATH = BASELINE_DIR / "scores.json"

# --- the Bayesian scoreline model (src/wcmodel) wired to EPL ---------------
#: Everything the fit probe writes. Under data/, so gitignored like the rest.
FIT_DIR = DATA_DIR / "fit"

#: A `wcmodel.data.store.BitemporalStore` root holding ONE table, `results`,
#: rebuilt from `MATCHES_PARQUET`. This is the design input `wcmodel.model.
#: scoreline.fit` consumes; it is derived, never a second source of truth.
STORE_DIR = FIT_DIR / "store"

#: Content-addressed posterior + feature-panel cache for EPL fits. Deliberately
#: NOT the World Cup cache dir (`data/cache`): same directory, same filename
#: namespace, and a corrupted or confusingly-named artifact in one project's
#: cache is a debugging cost in the other. The keys themselves cannot collide
#: (they hash the panel content), so this is hygiene, not correctness.
FIT_CACHE_DIR = FIT_DIR / "cache"

#: Timings, warnings, the smoke-test scores, and the walk-forward cost model
#: from one `python -m epl.fit` run.
FIT_REPORT_PATH = FIT_DIR / "single_fit.json"

#: Measured cost of letting the forecaster go stale between refits — an Elo
#: proxy for the Bayesian model's refit cadence (see `epl.fit.staleness_curve`).
STALENESS_PATH = FIT_DIR / "staleness.json"


def ensure_dirs() -> None:
    """Create the data directories if they do not exist yet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    """Repo-relative POSIX string for a path, for recording in manifests."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
