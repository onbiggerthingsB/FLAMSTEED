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


def ensure_dirs() -> None:
    """Create the data directories if they do not exist yet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    """Repo-relative POSIX string for a path, for recording in manifests."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
