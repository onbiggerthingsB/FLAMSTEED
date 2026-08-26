"""THE FRESHNESS SWEEP. Would a fit taken at each fixture's own matchday have
scored better than the weekly block fit that actually priced it?

This module executes the design preregistered in
``reports/epl_freshness_prereg.md`` (01f090a) and computes the estimand fixed
in its §2. It chooses nothing. The corpus is pinned by digest, the
configuration is frozen, the schedule is arithmetic on the corpus, the
threshold and the interval were written down before this file existed, and the
adoption rule is evaluated but never applied — §4.5: *"No script, no agent and
no report may change the live cadence on the strength of these numbers."*

WHAT THE TWO ARMS ARE.

* **Arm B**, the block fit, is **not recomputed**. It is the walk-forward's own
  ``dc_home``/``dc_draw``/``dc_away``/``dc_rps``, read out of
  ``data/epl/fit/walkforward_predictions.parquet`` at the eight decimals
  ``epl/walkforward.py::_one_cutoff`` wrote them with.
* **Arm A**, the matchday fit, is a new fit at ``cutoff = the fixture's own date
  at midnight`` — run through :func:`epl.walkforward._one_cutoff`, the walk's
  own function, called with the walk's own store, anchor and frozen config.

THE SECOND OF THOSE IS THE WHOLE CREDIBILITY OF THE SWEEP, so it is worth being
blunt about: this module does **not** reimplement the fit. It builds a
``walkforward.Cutoff`` whose ``cutoff`` is a matchday instead of a block opening
and hands it to the same code path the preregistered walk ran, so that "the
pipeline is identical" is a property of the call graph rather than a claim in a
docstring. The only thing that differs between the arms is the date on the
cutoff — which is exactly the treatment.

THE DIRECTION OF THE ONLY DANGEROUS BUG. Arm A's training set is a strict
superset of Arm B's, so **any leak biases the result toward freshness**, which
is the direction adoption would be granted on (§1.3 (b)). Three guards run per
fit and none of them is optional: the cutoff is the fixture's own date at
midnight and ``features.build`` keeps ``date < cutoff.normalize()``;
:func:`assert_cutoff_clean` recomputes the visible training frame by that same
rule and refuses if a priced fixture is inside it or a training row is dated on
or after the cutoff; and ``epl.fit.assert_point_in_time`` re-asks the store
itself. On top of those, the block-parity control (:func:`run_control`) re-fits
twenty block-opening dates and demands the corpus's own rows back **exactly**,
which is where "the archive grew since the walk" stops being an assumption.

TWO THINGS RUN BEFORE ANY MATCHDAY FIT, AND BOTH REFUSE. §5.3 makes
``walkforward.point_in_time_canary`` a precondition of the run — it is the
check that the leak risk above has not materialised — and §3.2 rules that *"the
control runs first; not one matchday fit is run until it passes."*
:data:`RUN_ORDER` is ``("canary", "control", "run", "merge")`` and
:func:`require_run_preconditions` ENFORCES it from the two written records, so
the order holds across four shard processes and across the merge that scores
them. An order declared in a constant and checked by nobody is a comment.

WHAT THIS FILE MAY NOT DO. It writes ``data/epl/fit/`` and the machine-readable
result, and nothing else (§6). It authors no verdict prose — the write-up is a
human act after the numbers exist. It does not touch the corpus, which is
read-only to this experiment and whose digest A8 also depends on. And it does
not run the preregistered sweep before the harness-hash freeze commit of §6
exists: :func:`harness_freeze_status` reads that commit's own record and
:func:`merge` refuses without it, because a run that precedes the freeze is, by
§7, not the run this document preregisters.

NO BETTING. The corpus's price columns are not read by this module at all —
neither the estimand, nor a stratum, nor the movement diagnostic touches them.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# BLAS FIRST, AND ONLY AT THE ENTRY POINT. OpenBLAS reads its thread count when
# it is loaded, which happens on `import numpy` — so a pin applied afterwards
# is a pin that did nothing to the pool that is already running, while still
# reconfiguring every library imported LATER in that process. The house rule
# from the sharded OA runs is one thread per worker: an N-way shard on a
# machine whose BLAS also wants N threads thrashes at a fraction of the CPU
# each — so `python -m epl.freshsweep` pins, unconditionally and before numpy,
# because a shard inheriting 8 from a shell is not the run this experiment
# preregistered.
#
# Importing this module does NOT pin. A library that rewrites the process
# environment on import is a library that changes the behaviour of code it
# knows nothing about — the test suite imports this module, and single-
# threading everything that imports pytensor after it would be a side effect
# nobody asked for and nobody could see. What replaces the mutation is
# evidence: :func:`blas_threads` records what the process ACTUALLY has on every
# ledger row (§5.2), and :func:`run_control` refuses to run real fits in a
# process that is not pinned (§3.2's pre-stated condition). Visible rather than
# silent, which is what the preregistration asked for.
# --------------------------------------------------------------------------
import os as _os
import sys as _sys

BLAS_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
_NUMPY_ALREADY_IMPORTED = "numpy" in _sys.modules
_IS_ENTRY_POINT = __name__ == "__main__"
if _IS_ENTRY_POINT:
    for _var in BLAS_VARS:
        _os.environ[_var] = "1"

import argparse                                                   # noqa: E402
import hashlib                                                    # noqa: E402
import json                                                       # noqa: E402
from contextlib import ExitStack as _ExitStack                    # noqa: E402
import re                                                         # noqa: E402
import socket                                                     # noqa: E402
import time                                                       # noqa: E402
from dataclasses import dataclass                                 # noqa: E402
from pathlib import Path                                          # noqa: E402
from typing import Any, Callable, Iterable, Sequence              # noqa: E402

import numpy as np                                                # noqa: E402
import pandas as pd                                               # noqa: E402

from epl import paths, recalfit                                   # noqa: E402
from epl import score as score_mod                                # noqa: E402

__all__ = [
    "FreshnessError", "FitPoint", "SCHEMA_ID", "SEED", "BOOTSTRAP_SEED",
    "ADOPT_DELTA", "RUN_ORDER", "load_corpus", "block_openings", "fit_points",
    "control_dates", "shard_points", "shard_name", "fit_key", "canonical",
    "run_digest", "load_ledger", "visible_training_frame",
    "assert_cutoff_clean", "run_fits", "run_canary", "require_canary",
    "run_control", "require_control", "require_run_preconditions",
    "estimand", "adoption",
    "merge", "harness_freeze_status", "require_harness_freeze", "main",
]


# ==========================================================================
# 0. the pins — the corpus, the config, the constants the prereg fixed
# ==========================================================================

#: §0: "This experiment adopts the same constants rather than restating them,
#: so there is one place where 'which corpus' is defined and one digest to
#: break." These are A8's own objects, bound by identity and not copied.
CORPUS_PATH = recalfit.CORPUS_PATH
CORPUS_SHA256 = recalfit.CORPUS_SHA256
CORPUS_ROWS = recalfit.CORPUS_ROWS
CORPUS_SEASONS = recalfit.CORPUS_SEASONS
CORPUS_Y_COUNTS = recalfit.CORPUS_Y_COUNTS

#: The frozen configuration, by digest, and the ONE seed. §2 is explicit that
#: the seed is a single constant and that `epl/walkforward.py` derives nothing
#: per cutoff, so a per-cutoff seed here would be a different experiment.
CONFIG_PATH = paths.REPO_ROOT / "epl" / "config_frozen.json"
CONFIG_SHA256 = \
    "9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc"
SEED = 20260611

#: §2's interval, exactly: the project's own block bootstrap over the corpus's
#: own `block` column, percentile, at the standard resampling seed.
BOOTSTRAP_SEED = 20260814
N_BOOT = 10_000
ALPHA = 0.05

#: §4.1's threshold. 4 x the 0.000075 seed-replica shift published in
#: `reports/epl_walkforward.md`. It is evaluated here and applied by nobody.
ADOPT_DELTA = -0.00030

#: §3.2's control: twenty block-opening dates drawn once, printed in the
#: document, and reproduced by this recipe.
CONTROL_SEED = 20260826
N_CONTROL_DATES = 20

#: §0.1's counts. A corpus that does not produce them is a different corpus,
#: not a smaller experiment (`ScheduleMismatch`).
EXPECTED_BLOCKS = 212
EXPECTED_DATES = 719
EXPECTED_FIT_DATES = 507
EXPECTED_STALE = 1699
EXPECTED_FRESH = 581
EXPECTED_CONTROL_FIXTURES = 56
MAX_STALENESS_DAYS = 6

#: The schema identifier the §6 freeze commit must name alongside the hashes.
SCHEMA_ID = "epl-freshness-1"

#: The files whose bytes can change a number, and which the §6 hash table
#: therefore has to name. The tests are in the list because a test that stops
#: asserting is a guard that stopped guarding.
HARNESS_FILES = ("epl/freshsweep.py", "epl/tests/test_freshsweep.py")

#: §3.2: "The control runs FIRST; not one matchday fit is run until it passes."
#: §5.3 puts one thing before even that: the point-in-time canary, which is a
#: precondition of the whole run rather than of the matchday fits alone. Both
#: are ENFORCED — :func:`require_run_preconditions` refuses a fit that has
#: neither on the record — because an order declared in a constant and checked
#: by nobody is a comment.
RUN_ORDER = ("canary", "control", "run", "merge")
CONTROL_RUNS_FIRST = True

#: §5.4's list, fixed in the document before any row existed: recorded on the
#: row, excluded from the canonical form and from every digest.
_VOLATILE = ("wall_seconds", "fit_seconds", "seconds", "shard_id",
             "started_at", "host")

#: Where the sweep writes. §6 closes the set; :data:`WRITES` is that set, and
#: the tests assert it excludes everything the house rules protect.
FRESHNESS_DIR = paths.FIT_DIR / "freshness"
FRESHNESS_JSON = paths.FIT_DIR / "freshness.json"

#: The two preconditions live BESIDE the shards they gate, under one run
#: directory, so a merge reads the canary and the control that belong to the
#: fits it is merging rather than whatever happens to be at a fixed path.
CONTROL_NAME = "control.json"
CANARY_NAME = "canary.json"
CONTROL_JSON = FRESHNESS_DIR / CONTROL_NAME
CANARY_JSON = FRESHNESS_DIR / CANARY_NAME
RESULT_JSON = paths.REPO_ROOT / "reports" / "epl_freshness_result.json"
WRITES = (FRESHNESS_DIR, FRESHNESS_JSON, CONTROL_JSON, CANARY_JSON,
          RESULT_JSON)

#: Where §6's freeze commit records the harness hashes. The prereg is the
#: document the commit amends; the amendment ledger is read too, because a
#: later re-issue of the hashes belongs there (§6 step 4).
PREREG_PATH = paths.REPO_ROOT / "reports" / "epl_freshness_prereg.md"
AMENDMENTS_PATH = paths.REPO_ROOT / "reports" / "epl_sim_amendments.md"

#: §5.2's row contract, at the two levels the ledger carries it.
REQUIRED_ROW_FIELDS = (
    "schema", "key", "match_id", "season", "block", "date", "cutoff",
    "block_cutoff", "staleness_days", "home_key", "away_key", "y",
    "probs_fresh", "probs_block", "rps_fresh", "rps_block",
    "rps_block_recomputed", "delta", "seed", "config_sha256", "arm_a",
    "arm_b", "fit", "harness_frozen", "shard_id", "seconds",
)
REQUIRED_FIT_FIELDS = (
    "cutoff", "seed", "config_sha256", "realised_config_sha256",
    "n_training_matches", "n_teams", "n_fixtures", "wall_seconds",
    "match_ids", "cold_start_teams", "provisional_teams", "anchor_spec",
    "warnings", "unpriceable", "health", "harness_sha256", "archive_rows",
    "archive_sha256", "blas_threads", "latest_training_date",
)

_PROB_COLUMNS = ("dc_home", "dc_draw", "dc_away")


# ==========================================================================
# 1. the typed refusals
# ==========================================================================

class FreshnessError(RuntimeError):
    """Anything this experiment refuses.

    §5.1 names fifteen subclasses and this module does not invent a sixteenth.
    A condition the preregistration pre-stated as an INVALIDATION but never
    gave an error name — §7's "a fit runs before the harness-hash commit of §6
    exists" is the one that matters in practice — is refused as this base class
    rather than under a name the document never wrote. That is `epl.recalfit`'s
    ruling on the same question, applied here for the same reason: a typed name
    is a promise the preregistration made, and inventing one after the fact is
    the small end of the wedge this whole apparatus exists to block.
    """


class CorpusMissing(FreshnessError):
    """The pinned parquet is not on disk."""


class CorpusDigestMismatch(FreshnessError):
    """The corpus is not the corpus the experiment was preregistered on."""


class CorpusShapeMismatch(FreshnessError):
    """Rows, seasons or outcome counts are not the pinned ones."""


class ConfigNotFrozen(FreshnessError):
    """`epl/config_frozen.json` is not `9f2e086d…`, or the seed is not 20260611."""


class ScheduleMismatch(FreshnessError):
    """The recomputed schedule is not 212 / 719 / 507 / 1,699."""


class CutoffLeak(FreshnessError):
    """A fit can see a match dated on or after its own cutoff.

    The one failure mode with a direction: it would flatter Arm A, which is the
    arm an adoption would be granted on.
    """


class CanaryFailed(FreshnessError):
    """`epl.walkforward.point_in_time_canary` did not pass (§5.3)."""


class ControlMismatch(FreshnessError):
    """A block-opening re-fit did not return the corpus's own row (§3.2)."""


class FitFailed(FreshnessError):
    """`fit_epl` raised, or the posterior it produced is not usable."""


class UnpriceableFixture(FreshnessError):
    """A club is absent from the posterior index at its own matchday.

    §2 fixes the denominator at 1,699 and Arm A sees strictly more data than
    Arm B, so this is a defect by construction and never a dropped row.
    """


class ScoreMismatch(FreshnessError):
    """Stored RPS does not re-derive from the stored probabilities."""


class SchemaMismatch(FreshnessError):
    """A ledger row lacks a field §5.2 requires."""


class RowConflict(FreshnessError):
    """Two rows share a key and disagree on a non-volatile field."""


class ShardFailed(FreshnessError):
    """A shard is missing, empty, or still carries a poison row."""


class MergeIncomplete(FreshnessError):
    """The merged key set is not exactly the pre-stated one."""


# ==========================================================================
# 2. the corpus and the configuration
# ==========================================================================

def sha256_file(path: Path | str) -> str:
    """SHA-256 of a file, streamed."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def config_sha256(path: Path | str | None = None) -> str:
    return sha256_file(Path(path) if path is not None else CONFIG_PATH)


def assert_config_frozen(path: Path | str | None = None) -> str:
    """Refuse a configuration that is not the frozen one (§5.1)."""
    path = Path(path) if path is not None else CONFIG_PATH
    if not path.exists():
        raise ConfigNotFrozen(f"{paths.rel(path)} is not on disk: this "
                              "experiment is defined on the frozen config")
    got = sha256_file(path)
    if got != CONFIG_SHA256:
        raise ConfigNotFrozen(
            f"{paths.rel(path)} is {got[:10]}…, not {CONFIG_SHA256[:10]}…: a "
            "different configuration answers a different question")
    return got


def load_corpus(path: Path | str | None = None,
                *, require_digest: bool = True) -> pd.DataFrame:
    """The pinned walk-forward corpus, checked by digest before it is read.

    §5.1's first three refusals, in the order they can fire. The shape check is
    not redundant beside the digest: a digest tells you the bytes changed, and
    these tell you what about them changed, which is the difference between a
    STOP somebody can act on and one they can only rerun.
    """
    path = Path(path) if path is not None else CORPUS_PATH
    if not path.exists():
        raise CorpusMissing(
            f"{paths.rel(path)} is not on disk. The freshness experiment is "
            "defined on that corpus by digest; there is nothing to fall back "
            "to and nothing to recompute.")
    if require_digest:
        got = sha256_file(path)
        if got != CORPUS_SHA256:
            raise CorpusDigestMismatch(
                f"{paths.rel(path)} hashes to {got}, not {CORPUS_SHA256}. A "
                "file with this name and different bytes answers a different "
                "question, and A8's constant is pinned to the same digest.")
    frame = pd.read_parquet(path)
    frame["date"] = pd.to_datetime(frame["date"])
    if require_digest:
        _assert_corpus_shape(frame)
    return frame


def _assert_corpus_shape(frame: pd.DataFrame) -> None:
    if len(frame) != CORPUS_ROWS:
        raise CorpusShapeMismatch(f"{len(frame)} rows, not {CORPUS_ROWS}")
    seasons = tuple(sorted(set(frame["season"].astype(str))))
    if seasons != tuple(sorted(CORPUS_SEASONS)):
        raise CorpusShapeMismatch(f"seasons {seasons}, not {CORPUS_SEASONS}")
    counts = tuple(int((frame["y"].to_numpy() == k).sum()) for k in (0, 1, 2))
    if counts != tuple(CORPUS_Y_COUNTS):
        raise CorpusShapeMismatch(f"y counts {counts}, not {CORPUS_Y_COUNTS}")
    missing = [c for c in (*_PROB_COLUMNS, "dc_rps", "block", "date",
                           "match_id", "home_key", "away_key", "y", "season")
               if c not in frame.columns]
    if missing:
        raise CorpusShapeMismatch(f"the corpus lacks {missing}")


def check_corpus_scores(frame: pd.DataFrame) -> dict[str, Any]:
    """Arm B's stored RPS, re-derived from Arm B's own stored probabilities.

    §2: the harness recomputes it and refuses a disagreement beyond 1e-12. On
    the pinned corpus the difference is 0.0 — this is a guard against a future
    corpus, not a tolerance the present one needs.
    """
    recomputed = score_mod.rps(frame[list(_PROB_COLUMNS)].to_numpy(float),
                               frame["y"].to_numpy())
    diff = np.abs(recomputed - frame["dc_rps"].to_numpy(float))
    worst = float(diff.max()) if diff.size else 0.0
    if worst > 1e-12:
        bad = frame["match_id"].to_numpy()[int(np.argmax(diff))]
        raise ScoreMismatch(
            f"stored dc_rps and the RPS of the stored probabilities differ by "
            f"{worst:.3g} at match {bad}: Arm B is the corpus's own number, "
            "and a corpus whose own columns disagree cannot be one arm of a "
            "paired comparison")
    return {"n": int(len(frame)), "max_abs_diff": worst}


# ==========================================================================
# 3. the schedule — 212 openings, 507 matchdays, 1,699 stale fixtures
# ==========================================================================

@dataclass(frozen=True)
class FitPoint:
    """One fit: when it happens and which fixtures it prices."""

    season: str
    block: str
    cutoff: str                       # ISO date; the cutoff is midnight on it
    block_cutoff: str                 # the block's own opening day
    match_ids: tuple[str, ...]
    staleness_days: int

    @property
    def is_opening(self) -> bool:
        return self.cutoff == self.block_cutoff

    def key(self, config_sha: str) -> str:
        return fit_key(self.cutoff, config_sha=config_sha)


def fit_key(cutoff: str, seed: int = SEED, config_sha: str | None = None) -> str:
    """§5.4's resume key: ``cutoff|seed|config_sha256``."""
    return f"{cutoff}|{int(seed)}|{config_sha or config_sha256()}"


def block_openings(corpus: pd.DataFrame) -> dict[str, str]:
    """block label -> its opening day, as an ISO date string.

    §0.1: recomputing the cutoff as each block's minimum fixture date
    reproduces the walk-forward ledger's own `cutoff` field for all 2,280 rows,
    which is why the schedule can be derived from the corpus alone.
    """
    opens = corpus.groupby("block")["date"].min()
    return {str(b): str(pd.Timestamp(d).date()) for b, d in opens.items()}


def fit_points(corpus: pd.DataFrame, *, kind: str = "matchday",
               check: bool = True) -> list[FitPoint]:
    """The fit schedule: ``matchday`` is Arm A's 507, ``opening`` is the 212.

    A fit point is a ``(season, date)`` pair — and on this corpus a date
    belongs to exactly one season, which is checked rather than assumed.
    """
    if kind not in ("matchday", "opening"):
        raise FreshnessError(f"kind must be 'matchday' or 'opening', not {kind!r}")
    opens = block_openings(corpus)
    frame = corpus.copy()
    frame["iso"] = frame["date"].dt.strftime("%Y-%m-%d")
    frame["block_cutoff"] = frame["block"].map(opens)
    frame["staleness"] = (frame["date"]
                          - pd.to_datetime(frame["block_cutoff"])).dt.days

    spans = frame.groupby("iso")["season"].nunique()
    if len(spans) and int(spans.max()) != 1:
        raise ScheduleMismatch(
            "a match date falls in two seasons, so (season, date) is not a fit "
            "point: the schedule is ambiguous and nothing downstream is safe")

    want_opening = kind == "opening"
    points: list[FitPoint] = []
    for iso, part in frame.groupby("iso", sort=True):
        blocks = sorted(set(part["block"].astype(str)))
        if len(blocks) != 1:
            raise ScheduleMismatch(f"{iso} spans blocks {blocks}")
        staleness = sorted(set(int(s) for s in part["staleness"]))
        if len(staleness) != 1:
            raise ScheduleMismatch(f"{iso} carries staleness {staleness}")
        if (staleness[0] == 0) != want_opening:
            continue
        points.append(FitPoint(
            season=str(part["season"].iloc[0]), block=blocks[0], cutoff=iso,
            block_cutoff=str(part["block_cutoff"].iloc[0]),
            match_ids=tuple(sorted(str(m) for m in part["match_id"])),
            staleness_days=staleness[0]))

    if check:
        _assert_schedule(corpus, points, kind)
    return points


def _assert_schedule(corpus: pd.DataFrame, points: Sequence[FitPoint],
                     kind: str) -> None:
    """§5.1's `ScheduleMismatch`: the counts are pre-stated, so they bind."""
    n_dates, n_fixtures = len(points), sum(len(p.match_ids) for p in points)
    want_dates = EXPECTED_FIT_DATES if kind == "matchday" else EXPECTED_BLOCKS
    want_fix = EXPECTED_STALE if kind == "matchday" else EXPECTED_FRESH
    problems = []
    if len(block_openings(corpus)) != EXPECTED_BLOCKS:
        problems.append(f"{len(block_openings(corpus))} blocks, not {EXPECTED_BLOCKS}")
    if corpus["date"].nunique() != EXPECTED_DATES:
        problems.append(f"{corpus['date'].nunique()} match dates, not {EXPECTED_DATES}")
    if n_dates != want_dates:
        problems.append(f"{n_dates} {kind} fit dates, not {want_dates}")
    if n_fixtures != want_fix:
        problems.append(f"{n_fixtures} fixtures, not {want_fix}")
    if kind == "matchday":
        worst = max((p.staleness_days for p in points), default=0)
        if worst > MAX_STALENESS_DAYS:
            problems.append(f"staleness reaches {worst} days, not "
                            f"{MAX_STALENESS_DAYS} — the ISO-week block bounds it")
    if problems:
        raise ScheduleMismatch(
            "; ".join(problems) + f". §0.1 pre-states {EXPECTED_BLOCKS} blocks, "
            f"{EXPECTED_DATES} dates, {EXPECTED_FIT_DATES} additional fit dates "
            f"and {EXPECTED_STALE} stale fixtures. A corpus that does not "
            "produce them is a different corpus, not a smaller experiment.")


def control_dates(corpus: pd.DataFrame, n: int = N_CONTROL_DATES,
                  seed: int = CONTROL_SEED) -> list[str]:
    """§3.2's twenty block-opening dates, by the recipe the document printed.

    "sort the 212 block-opening dates ascending as ISO strings, take indices
    ``numpy.random.default_rng(20260826).choice(212, size=20, replace=False)``,
    sort the result."
    """
    openings = sorted(set(block_openings(corpus).values()))
    if n > len(openings):
        raise FreshnessError(f"{n} control dates asked of {len(openings)} "
                             "block openings")
    idx = np.random.default_rng(seed).choice(len(openings), size=n,
                                             replace=False)
    return sorted(openings[int(i)] for i in idx)


def shard_name(index: int, count: int) -> str:
    return f"shard_{int(index):02d}_of_{int(count):02d}.jsonl"


def shard_points(points: Sequence[FitPoint], index: int,
                 count: int) -> list[FitPoint]:
    """A partition of the fit points by date — union everything, overlap nothing.

    Strided rather than blocked so every shard carries the same mix of early
    and late cutoffs: a blocked split would put the cheapest fits (smallest
    training frames) in one shard and the most expensive in another, and the
    run would be as slow as its unluckiest quarter.
    """
    count = int(count)
    index = int(index)
    if count < 1:
        raise FreshnessError(f"a shard count of {count} is not a partition")
    if not 0 <= index < count:
        raise FreshnessError(
            f"shard {index} of {count} does not exist: shards are 0-based and "
            f"the last one is {count - 1}")
    ordered = sorted(points, key=lambda p: p.cutoff)
    return ordered[index::count]


# ==========================================================================
# 4. the leakage guard
# ==========================================================================

def visible_training_frame(cutoff: str | pd.Timestamp,
                           played: pd.DataFrame) -> pd.DataFrame:
    """What a fit at ``cutoff`` may see, by the walk-forward's own rule.

    ``wcmodel.data.features.build`` keeps ``date < cutoff.normalize()``. This
    reproduces that rule on the played frame so the property can be asserted
    against a frame instead of quoted from a source file.
    """
    ts = pd.Timestamp(cutoff).normalize()
    return played.loc[pd.to_datetime(played["date"]) < ts]


def assert_cutoff_clean(cutoff: str | pd.Timestamp, played: pd.DataFrame,
                        match_ids: Iterable[str]) -> dict[str, Any]:
    """Refuse a fit that can see the fixtures it is about to price (§1.3 (b))."""
    ts = pd.Timestamp(cutoff).normalize()
    ids = tuple(str(m) for m in match_ids)
    train = visible_training_frame(ts, played)
    if train.empty:
        raise FreshnessError(f"no training matches before {ts.date()}")

    leaked = sorted(set(ids) & set(train["match_id"].astype(str)))
    if leaked:
        raise CutoffLeak(
            f"{len(leaked)} fixture(s) priced at cutoff {ts.date()} are inside "
            f"the training frame of the fit that prices them: {leaked[:5]}. "
            "This is the one bug with a direction — it flatters the matchday "
            "arm, which is the arm adoption would be granted on.")

    latest = pd.to_datetime(train["date"]).max()
    if not latest < ts:
        raise CutoffLeak(f"latest training date {latest.date()} is not strictly "
                         f"before cutoff {ts.date()}")

    dated = played.loc[played["match_id"].astype(str).isin(ids)]
    off = sorted(str(m) for m, d in zip(dated["match_id"].astype(str),
                                        pd.to_datetime(dated["date"]))
                 if d.normalize() != ts)
    if off:
        raise CutoffLeak(
            f"fixture(s) {off[:5]} do not kick off on their own cutoff "
            f"{ts.date()}: a matchday fit prices its own matchday, and a "
            "fixture dated elsewhere would be priced from someone else's fit")

    return {"cutoff": str(ts.date()), "n_training_matches": int(len(train)),
            "latest_training_date": str(latest.date()), "n_priced": len(ids)}


# ==========================================================================
# 5. the ledger — canonical form, digests, conflicts, poison
# ==========================================================================

def _strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in _VOLATILE}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def canonical(rows: Sequence[dict[str, Any]]) -> str:
    """§5.4's canonical form: sorted, volatile fields removed, `sort_keys=True`.

    The demand that a resumed run reproduce an uninterrupted one is made HERE
    and not on the raw file, because a row records its own wall clock and its
    own shard and two runs will never agree on those. Everything that can
    change a number is inside this string; everything that cannot is outside
    it, and the list of which is which was fixed in the preregistration before
    any row existed.
    """
    clean = [_strip_volatile(r) for r in rows]
    clean.sort(key=lambda r: (str(r.get("cutoff", "")),
                              str(r.get("match_id", "")), str(r.get("key", ""))))
    return json.dumps(clean, sort_keys=True, separators=(",", ":"),
                      default=str)


def run_digest(rows: Sequence[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical(rows).encode("utf-8")).hexdigest()


def _row_identity(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("key", "")), str(row.get("match_id", "")))


def read_jsonl(path: Path | str) -> tuple[list[dict], list[dict], int]:
    """Parse a shard ledger into (rows, poison, dropped-truncated-lines).

    A crash between the fit and the fsync leaves half a JSON object on the last
    line. That fit is incomplete, so the fragment is dropped and the fit is
    re-run; a malformed line ANYWHERE ELSE is a corrupted ledger and refused,
    because only the tail can be truncated by an interrupted append.
    """
    path = Path(path)
    if not path.exists():
        return [], [], 0
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    rows, poison, dropped = [], [], 0
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                dropped += 1
                continue
            raise FreshnessError(
                f"{paths.rel(path)} line {i + 1} is not JSON, and it is not the "
                "last line: only an interrupted append can truncate a ledger, "
                "so this file is corrupted rather than partial")
        (poison if obj.get("poison") else rows).append(obj)
    return rows, poison, dropped


def poison_rows(path: Path | str) -> list[dict]:
    return read_jsonl(path)[1]


def repair_tail(path: Path | str) -> int:
    """Drop a torn final line, and say so. Returns the bytes discarded.

    A crash between the write and the fsync leaves a fragment of one JSON
    object at the end of the ledger with no newline after it. The next append
    would glue itself onto that fragment and turn ONE unreadable line into two,
    which is how a resumable log quietly becomes a corrupted one — so the
    fragment is removed before anything is appended.

    This is the only place this module rewrites a ledger, and it removes only
    bytes that provably cannot be parsed as a row: the fit they belonged to is
    incomplete by definition and is re-run. A malformed line anywhere else is
    still a hard refusal, because only the tail can be torn by an interrupted
    append.
    """
    path = Path(path)
    if not path.exists():
        return 0
    raw = path.read_bytes()
    if not raw or raw.endswith(b"\n"):
        try:
            read_jsonl(path)
        except FreshnessError:
            raise
        return 0
    head, _, tail = raw.rpartition(b"\n")
    try:
        json.loads(tail.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        tmp = path.with_suffix(path.suffix + ".repair")
        tmp.write_bytes(head + b"\n" if head else b"")
        tmp.replace(path)
        return len(tail)
    path.write_bytes(raw + b"\n")            # intact, merely unterminated
    return 0


def load_ledger(path: Path | str, *, allow_poison: bool = False,
                complete_only: bool = True) -> list[dict[str, Any]]:
    """Every fixture row in a shard, de-duplicated, schema-checked, ordered.

    Three things happen here and each of them is a refusal the preregistration
    named: a duplicated key that DISAGREES is `RowConflict` (§5.4, "append
    order cannot change a number"); a row missing a §5.2 field is
    `SchemaMismatch`; and a poison row is `ShardFailed` unless the caller is
    the one collecting poison.

    ``complete_only`` drops a fit whose fixture rows are short of the count the
    rows themselves declare — the signature of a crash mid-append. It is how
    resume knows a fit is unfinished rather than trusting the file's length.
    """
    path = Path(path)
    rows, poison, _ = read_jsonl(path)
    if poison and not allow_poison:
        first = poison[0]
        raise ShardFailed(
            f"{paths.rel(path)} carries {len(poison)} poison row(s); the first "
            f"is {first.get('error_type')} at cutoff {first.get('cutoff')}: "
            f"{first.get('error')}. A failed fit poisons its shard, and a "
            "poisoned shard is never merged or scored.")

    keep: dict[tuple[str, str], dict] = {}
    for row in rows:
        for field in REQUIRED_ROW_FIELDS:
            if field not in row:
                raise SchemaMismatch(
                    f"{paths.rel(path)}: a row for {row.get('match_id')!r} at "
                    f"cutoff {row.get('cutoff')!r} lacks {field!r}. §5.2 fixes "
                    "what a row records; a field nobody wrote is a field "
                    "nobody can check afterwards.")
        ident = _row_identity(row)
        if ident in keep:
            a = _strip_volatile(keep[ident])
            b = _strip_volatile(row)
            if json.dumps(a, sort_keys=True, default=str) != \
               json.dumps(b, sort_keys=True, default=str):
                raise RowConflict(
                    f"{paths.rel(path)} holds two rows for {ident} that "
                    "disagree on a scored field. Two fits of the same cutoff "
                    "under the same seed and the same config are the same "
                    "fit; if they are not, something moved that this "
                    "experiment holds fixed.")
            continue
        keep[ident] = row

    out = list(keep.values())
    if complete_only:
        by_key: dict[str, list[dict]] = {}
        for row in out:
            by_key.setdefault(str(row["key"]), []).append(row)
        out = [r for key, group in by_key.items()
               for r in group
               if len(group) == int(group[0]["fit"]["n_fixtures"])]
    out.sort(key=lambda r: (str(r["cutoff"]), str(r["match_id"])))
    return out


def completed_keys(path: Path | str) -> set[str]:
    """The fit keys a shard has FINISHED — partial fits excluded."""
    try:
        rows = load_ledger(path, allow_poison=True, complete_only=True)
    except (SchemaMismatch, RowConflict):
        raise
    return {str(r["key"]) for r in rows}


# ==========================================================================
# 6. the fit — the walk-forward's own code path, at a matchday cutoff
# ==========================================================================

def blas_threads() -> dict[str, Any]:
    """What this process actually has, recorded on every row (§3.2).

    Not what it asked for: the environment is read back, and
    ``pinned_before_numpy`` says whether the pin could have reached the BLAS
    pool at all. A row produced in a different threading environment is
    therefore visible on the row rather than inferred from the source.
    """
    out: dict[str, Any] = {v: _os.environ.get(v) for v in BLAS_VARS}
    out["pinned_before_numpy"] = bool(_IS_ENTRY_POINT
                                      and not _NUMPY_ALREADY_IMPORTED)
    out["entry_point"] = bool(_IS_ENTRY_POINT)
    return out


def assert_blas_pinned(where: str) -> dict[str, Any]:
    """§3.2's pre-stated condition: one BLAS thread per worker, for real fits.

    Checked where fits actually happen rather than at import, because the pin
    is a property of the process that runs them. A stubbed control runs no fit
    and pins nothing; a control that is about to spend twenty ADVI fits does.
    """
    threads = blas_threads()
    unpinned = [v for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                            "MKL_NUM_THREADS") if threads.get(v) != "1"]
    if unpinned:
        raise FreshnessError(
            f"{where} runs real fits and this process is not pinned to one "
            f"BLAS thread per worker: {unpinned} are "
            f"{[threads.get(v) for v in unpinned]}. "
            "§3.2 pre-states the condition and §5.2 records it per row. Run "
            "the sweep as `python -m epl.freshsweep`, which pins before numpy "
            "loads, or export the three variables before starting the worker.")
    return threads


class Engine:
    """The walk-forward's own machinery, built once and reused per fit.

    Everything here is read from `epl.walkforward` and `epl.freeze` rather than
    rebuilt: the same frozen config, the same `Anchor` over the same played
    frame, the same `build_store`, the same `config_read_once` fast panel
    (proven inert at panel and forecast level by
    `walkforward.verify_fast_path_is_inert`), and — the point — the same
    `_one_cutoff`. Byte-parity with the walk's own results is not something
    this module tries to achieve; it is what calling the walk's function gets
    for free, and the §3.2 control is the check that it did.
    """

    def __init__(self, corpus: pd.DataFrame, matches: pd.DataFrame | None = None,
                 *, verbose: bool = True):
        from epl import anchor as anchor_mod, baseline, fit as epl_fit, freeze
        from epl.schema import sort_for_walk_forward

        self._epl_fit = epl_fit
        self.config_sha256 = assert_config_frozen()
        self.cfg = freeze.frozen_wcmodel_config()
        if int(self.cfg["seed"]) != SEED:
            raise ConfigNotFrozen(
                f"the realised configuration's seed is {self.cfg['seed']}, not "
                f"{SEED}: §2 fixes the seed as ONE CONSTANT")
        self.realised_config_sha256 = hashlib.sha256(
            json.dumps(self.cfg, sort_keys=True, default=str).encode()
        ).hexdigest()

        matches = baseline.load_matches() if matches is None else matches
        self.played = sort_for_walk_forward(matches.loc[matches["played"]])
        self.anchor = anchor_mod.Anchor(self.played, freeze.frozen_elo_config())
        self.store = epl_fit.build_store(self.played)
        self._ids = self.played["match_id"].astype(str).to_numpy()
        self._pos = {m: i for i, m in enumerate(self._ids)}
        self._mw = epl_fit.matchweek_index(self.played)
        self.archive_rows = int(len(self.played))
        self.archive_sha256 = self._archive_digest()
        self.harness_sha256 = sha256_file(paths.REPO_ROOT / HARNESS_FILES[0])
        self._ctx = None
        self.verbose = verbose
        missing = [m for p in _corpus_ids(corpus) for m in (p,)
                   if m not in self._pos]
        if missing:
            raise ScheduleMismatch(
                f"{len(missing)} corpus fixtures are absent from the archive "
                f"(first: {missing[:3]}): Arm A cannot price a fixture the "
                "archive does not carry, and §2 forbids dropping one")

    def _archive_digest(self) -> str:
        cols = [c for c in ("match_id", "date", "home_score", "away_score")
                if c in self.played.columns]
        frame = self.played[cols].astype(str).sort_values("match_id")
        return hashlib.sha256(
            frame.to_csv(index=False).encode("utf-8")).hexdigest()

    def __enter__(self) -> "Engine":
        self._ctx = self._epl_fit.config_read_once(self.cfg)
        self._ctx.__enter__()
        return self

    def __exit__(self, *exc) -> bool:
        ctx, self._ctx = self._ctx, None
        return bool(ctx.__exit__(*exc)) if ctx is not None else False

    def fit(self, point: FitPoint) -> dict[str, Any]:
        """One fit at ``point.cutoff``, priced through `walkforward._one_cutoff`."""
        from epl import walkforward as wf

        rows = np.array([self._pos[m] for m in point.match_ids], dtype=int)
        weeks = sorted(set(int(w) for w in self._mw[rows]))
        if len(weeks) != 1:
            raise ScheduleMismatch(f"{point.cutoff} spans matchweeks {weeks}")
        cut = wf.Cutoff(season=point.season, matchweek=weeks[0],
                        cutoff=pd.Timestamp(point.cutoff).normalize(),
                        rows=rows, match_ids=point.match_ids)

        pit = self._epl_fit.assert_point_in_time(self.store, cut.cutoff)
        if pit["latest_training_date"] >= point.cutoff:
            raise CutoffLeak(
                f"the STORE's latest training date at {point.cutoff} is "
                f"{pit['latest_training_date']}")

        out = wf._one_cutoff(cut, self.played, self.store, self.anchor,
                             self.cfg, self.played)
        out["latest_training_date"] = pit["latest_training_date"]
        out["n_training_matches_store"] = pit["n_training_matches"]
        return out


def _corpus_ids(corpus: pd.DataFrame) -> list[str]:
    return [str(m) for m in corpus["match_id"]]


# ==========================================================================
# 7. the runner
# ==========================================================================

def _fit_provenance(point: FitPoint, out: dict, *, config_sha: str,
                    realised_sha: str, harness_sha: str, archive_rows: int,
                    archive_sha: str, wall: float) -> dict[str, Any]:
    return {
        "cutoff": point.cutoff, "seed": SEED, "config_sha256": config_sha,
        "realised_config_sha256": realised_sha,
        "n_training_matches": int(out.get("n_training_matches", -1)),
        "n_training_matches_store": out.get("n_training_matches_store"),
        "latest_training_date": out.get("latest_training_date"),
        "n_teams": int(out.get("n_teams", -1)),
        "n_fixtures": len(point.match_ids),
        "match_ids": list(point.match_ids),
        "cold_start_teams": list(out.get("cold_start_teams", [])),
        "cold_start_z": dict(out.get("cold_start_z", {})),
        "provisional_teams": list(out.get("provisional_teams", [])),
        "anchor_spec": str(out.get("anchor_spec", "")),
        "warnings": list(out.get("warnings", [])),
        "unpriceable": list(out.get("unpriceable", [])),
        "health": dict(out.get("health", {})),
        "harness_sha256": harness_sha,
        "archive_rows": int(archive_rows), "archive_sha256": archive_sha,
        "blas_threads": blas_threads(),
        "wall_seconds": round(wall, 3),
        "fit_seconds": out.get("seconds"),
    }


def _check_fit(point: FitPoint, out: dict) -> np.ndarray:
    """Everything that makes a fit unusable, refused by its own name."""
    if out.get("unpriceable"):
        raise UnpriceableFixture(
            f"{point.cutoff}: {out['unpriceable']}. §2 fixes the denominator "
            "at 1,699 and Arm A sees strictly more data than Arm B, so an "
            "unpriceable fixture here is a defect, never a dropped row.")
    health = out.get("health", {})
    bad = [k for k in ("all_finite", "sigma_positive", "home_adv_sane")
           if not health.get(k, True)]
    if bad:
        raise FitFailed(f"{point.cutoff}: the posterior fails {bad} — "
                        f"{health}")
    probs = np.asarray(out["probs"], dtype=float)
    if probs.shape != (len(point.match_ids), 3):
        raise FitFailed(f"{point.cutoff}: {probs.shape} probabilities for "
                        f"{len(point.match_ids)} fixtures")
    if not np.isfinite(probs).all() or \
            not np.allclose(probs.sum(axis=1), 1.0, atol=1e-9):
        raise FitFailed(
            f"{point.cutoff}: a forecast is non-finite or does not sum to 1 "
            "(worst |sum-1| = "
            f"{float(np.max(np.abs(probs.sum(axis=1) - 1.0))):.3g})")
    return probs


def _poison(ledger_path: Path, point: FitPoint, key: str, exc: BaseException,
            shard_id: str) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a") as fh:
        fh.write(json.dumps({
            "schema": SCHEMA_ID, "poison": True, "key": key,
            "cutoff": point.cutoff, "season": point.season,
            "match_ids": list(point.match_ids),
            "error_type": type(exc).__name__, "error": str(exc),
            "shard_id": shard_id,
            "started_at": pd.Timestamp.now("UTC").isoformat(),
        }, default=str) + "\n")


def run_fits(points: Sequence[FitPoint], ledger_path: Path | str,
             corpus: pd.DataFrame, *,
             fitter: Callable[[FitPoint], dict] | None = None,
             played: pd.DataFrame | None = None,
             engine: "Engine | None" = None,
             shard_id: str = "0/1", resume: bool = True, verbose: bool = True,
             harness_frozen: bool = True) -> dict[str, Any]:
    """Fit every point and append one JSONL row per fixture.

    Resumable per fit, keyed ``cutoff|seed|config_sha256`` (§5.4): a key
    already complete in the ledger is skipped — not re-run, not re-scored, not
    appended twice. A fit's rows are written in ONE append so a crash leaves
    either all of them or a truncated tail that :func:`load_ledger` drops and
    this function re-runs.

    ``harness_frozen`` is the caller's assertion about §6, not a guess this
    function makes: the CLI computes it from :func:`harness_freeze_status` and
    passes it, every row records it, and the merge refuses a row that says
    False. Writing to the preregistered ledger location before the freeze is
    refused outright, because §7 makes such a run not this experiment.
    """
    ledger_path = Path(ledger_path)
    _guard_ledger_location(ledger_path, harness_frozen)

    if fitter is None:
        engine = engine or Engine(corpus, verbose=verbose)
        fitter = engine.fit
        played = engine.played if played is None else played
        config_sha = engine.config_sha256
        realised_sha = engine.realised_config_sha256
        harness_sha = engine.harness_sha256
        archive_rows, archive_sha = engine.archive_rows, engine.archive_sha256
    else:
        # An injected fitter still keys on the REAL config digest: the resume
        # key is a fact about the configuration, not about who computed the
        # forecast, and a test that keyed differently would be testing a
        # different ledger from the one the run writes.
        config_sha = engine.config_sha256 if engine else config_sha256()
        realised_sha = (engine.realised_config_sha256 if engine
                        else "injected-fitter")
        harness_sha = engine.harness_sha256 if engine else "stub-harness"
        archive_rows = engine.archive_rows if engine else -1
        archive_sha = engine.archive_sha256 if engine else "stub-archive"

    torn = repair_tail(ledger_path)
    if torn and verbose:
        print(f"[fresh] dropped {torn} torn byte(s) from the tail of "
              f"{paths.rel(ledger_path)}: that fit is incomplete and re-runs",
              flush=True)

    stale = poison_rows(ledger_path)
    if stale:
        first = stale[0]
        raise ShardFailed(
            f"{paths.rel(ledger_path)} still carries {len(stale)} poison "
            f"row(s) — the first is {first.get('error_type')} at "
            f"{first.get('cutoff')}: {first.get('error')}. Fail closed: "
            "re-running over poison would leave the poison in place, the merge "
            "would refuse anyway, and the fits would have been paid for twice. "
            "Inspect the failure, then remove this shard's ledger and re-run "
            "the shard.")

    done = completed_keys(ledger_path) if resume else set()
    by_id = corpus.set_index(corpus["match_id"].astype(str))
    todo = [p for p in points if fit_key(p.cutoff, config_sha=config_sha)
            not in done]
    if verbose:
        print(f"[fresh] shard {shard_id}: {len(points)} fit points, "
              f"{len(points) - len(todo)} already complete, {len(todo)} to run",
              flush=True)

    started = time.time()
    n_rows = 0
    for i, point in enumerate(todo, 1):
        key = fit_key(point.cutoff, config_sha=config_sha)
        t0 = time.perf_counter()
        try:
            if played is not None:
                assert_cutoff_clean(point.cutoff, played, point.match_ids)
            out = fitter(point)
            probs = _check_fit(point, out)
        except FreshnessError as exc:
            _poison(ledger_path, point, key, exc, shard_id)
            raise
        except Exception as exc:                      # noqa: BLE001 — typed below
            wrapped = FitFailed(f"{point.cutoff}: {type(exc).__name__}: {exc}")
            _poison(ledger_path, point, key, wrapped, shard_id)
            raise wrapped from exc

        wall = time.perf_counter() - t0
        fit = _fit_provenance(point, out, config_sha=config_sha,
                              realised_sha=realised_sha, harness_sha=harness_sha,
                              archive_rows=archive_rows, archive_sha=archive_sha,
                              wall=wall)
        lines = []
        for mid, prob in zip(point.match_ids, probs):
            lines.append(json.dumps(
                _fixture_row(point, str(mid), prob, by_id.loc[str(mid)], fit,
                             key=key, config_sha=config_sha,
                             shard_id=shard_id, wall=wall,
                             harness_frozen=harness_frozen), default=str))
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
        n_rows += len(lines)
        if verbose:
            el = time.time() - started
            print(f"[fresh] {i}/{len(todo)} {point.cutoff} "
                  f"n_train={fit['n_training_matches']} "
                  f"fixtures={len(point.match_ids)} {wall:.1f}s "
                  f"(elapsed {el / 60:.1f}m, eta {el / i * (len(todo) - i) / 60:.1f}m)",
                  flush=True)

    rows = load_ledger(ledger_path)
    return {"shard_id": shard_id, "n_fits": len(todo), "n_rows_written": n_rows,
            "repaired_bytes": int(torn),
            "n_fixtures": len(rows), "n_skipped": len(points) - len(todo),
            "seconds": round(time.time() - started, 1),
            "ledger": str(ledger_path), "run_digest": run_digest(rows),
            "harness_frozen": bool(harness_frozen)}


def _guard_ledger_location(ledger_path: Path, harness_frozen: bool) -> None:
    """The preregistered ledger is off limits until §6's freeze commit exists."""
    if harness_frozen:
        return
    try:
        inside = ledger_path.resolve().is_relative_to(FRESHNESS_DIR.resolve())
    except (OSError, ValueError):
        inside = False
    if inside:
        raise FreshnessError(
            f"refusing to write {paths.rel(ledger_path)} before §6's "
            "harness-hash freeze commit exists. §7: 'A fit runs before the "
            "harness-hash commit of §6 exists' invalidates the "
            "preregistration. Audit fits are legitimate — run them to a "
            "scratch ledger outside "
            f"{paths.rel(FRESHNESS_DIR)}, where every row is stamped "
            "harness_frozen: false and the merge will not score them.")


def _fixture_row(point: FitPoint, match_id: str, probs: np.ndarray,
                 corpus_row: pd.Series, fit: dict, *, key: str,
                 config_sha: str, shard_id: str, wall: float,
                 harness_frozen: bool) -> dict[str, Any]:
    """One paired fixture: Arm A computed, Arm B copied, both with provenance."""
    fresh = [float(v) for v in probs]
    block = [float(corpus_row[c]) for c in _PROB_COLUMNS]
    y = int(corpus_row["y"])
    rps_fresh = float(score_mod.rps(np.array([fresh]), np.array([y]))[0])
    rps_block_recomputed = float(
        score_mod.rps(np.array([block]), np.array([y]))[0])
    rps_block = float(corpus_row["dc_rps"])
    if abs(rps_block_recomputed - rps_block) > 1e-12:
        raise ScoreMismatch(
            f"{match_id}: stored dc_rps {rps_block!r} and the RPS of the "
            f"stored probabilities {rps_block_recomputed!r} differ by "
            f"{abs(rps_block_recomputed - rps_block):.3g}")
    return {
        "schema": SCHEMA_ID, "key": key, "match_id": match_id,
        "season": point.season, "block": point.block,
        "date": point.cutoff, "cutoff": point.cutoff,
        "block_cutoff": point.block_cutoff,
        "staleness_days": int(point.staleness_days),
        "home_key": str(corpus_row["home_key"]),
        "away_key": str(corpus_row["away_key"]), "y": y,
        "probs_fresh": fresh, "probs_block": block,
        "rps_fresh": rps_fresh, "rps_block": rps_block,
        "rps_block_recomputed": rps_block_recomputed,
        "delta": rps_fresh - rps_block,
        "seed": SEED, "config_sha256": config_sha,
        "arm_a": {
            "arm": "matchday fit", "source": "epl.freshsweep via "
            "epl.walkforward._one_cutoff", "cutoff": point.cutoff,
            "seed": SEED, "config_sha256": config_sha,
            "realised_config_sha256": fit["realised_config_sha256"],
            "harness_sha256": fit["harness_sha256"],
            "archive_rows": fit["archive_rows"],
            "archive_sha256": fit["archive_sha256"],
            "predict": "post.predict_1x2(home, away, neutral=False)",
            "rounding": "round(v, 8)",
        },
        "arm_b": {
            "arm": "block fit", "source": paths.rel(CORPUS_PATH),
            "corpus_sha256": CORPUS_SHA256, "cutoff": point.block_cutoff,
            "columns": list(_PROB_COLUMNS) + ["dc_rps"],
            "recomputed": False,
        },
        "fit": fit, "harness_frozen": bool(harness_frozen),
        "shard_id": shard_id, "seconds": round(wall, 3),
        "wall_seconds": round(wall, 3),
        "started_at": pd.Timestamp.now("UTC").isoformat(),
        "host": socket.gethostname(),
    }


# ==========================================================================
# 8. the preconditions — the canary (§5.3), then the block-parity control
# ==========================================================================

def run_canary(runner: Callable[[], dict[str, Any]] | None = None, *,
               path: Path | str | None = None,
               write: bool = True) -> dict[str, Any]:
    """§5.3's point-in-time canary, run once before anything else.

    ``epl.walkforward.point_in_time_canary`` rewrites every result from a
    cutoff onward to 9-0 and demands ``np.array_equal`` on the forecasts a fit
    at that cutoff produces, with a positive control at a later cutoff proving
    the corrupted results really did land — so a canary that rewrote nothing
    cannot pass by accident. On the preregistered walk it returned max |Δp| =
    0.0 against a positive control of 0.812.

    IT IS A PRECONDITION AND NOT A RESULT. Arm A's training set is a strict
    superset of Arm B's, so any leak in the pipeline biases this experiment
    toward freshness — the direction an adoption would be granted on (§1.3
    (b)). This is the check that the risk has not materialised, and §5.3 makes
    ``PASS: false`` a :class:`CanaryFailed` that stops the run before a single
    matchday fit.

    The full dict is written whichever way it falls: a refusal that leaves no
    record is a refusal nobody can audit.
    """
    if runner is None:
        from epl import walkforward as wf
        runner = wf.point_in_time_canary
    started = time.perf_counter()
    out = dict(runner())
    out.setdefault("schema", SCHEMA_ID)
    out["blas_threads"] = blas_threads()
    out["seconds"] = round(time.perf_counter() - started, 1)
    path = Path(path) if path is not None else CANARY_JSON
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2, default=str) + "\n")
    if not out.get("PASS"):
        raise CanaryFailed(
            f"the point-in-time canary did not pass: max |Δp| before the "
            f"cutoff = {out.get('max_abs_diff_before_cutoff')!r} (must be 0), "
            f"positive control = {out.get('max_abs_diff_positive_control')!r} "
            "(must move). §5.3: the run does not start. A leak here would "
            "flatter the matchday arm, which is the arm adoption would be "
            f"granted on. The full dict is on the record at {paths.rel(path)}.")
    return out


def require_canary(path: Path | str | None = None) -> dict[str, Any]:
    """Refuse a fit that has no passing canary on the record (§5.3)."""
    path = Path(path) if path is not None else CANARY_JSON
    if not path.exists():
        raise CanaryFailed(
            f"no point-in-time canary on the record at {paths.rel(path)}. §5.3 "
            "makes it a precondition of the run, and an absent canary is not a "
            "passing one: run `--canary` first.")
    try:
        rec = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise CanaryFailed(f"{paths.rel(path)} is not readable JSON: {exc}") from exc
    if not rec.get("PASS"):
        raise CanaryFailed(
            f"the canary on record at {paths.rel(path)} did not pass: max "
            f"|Δp| before the cutoff = "
            f"{rec.get('max_abs_diff_before_cutoff')!r} (must be 0), positive "
            f"control = {rec.get('max_abs_diff_positive_control')!r} (must "
            "move). §5.3: the run does not start.")
    return rec


def run_control(dates: Sequence[str] | None = None,
                corpus: pd.DataFrame | None = None, *,
                fitter: Callable[[FitPoint], dict] | None = None,
                engine: "Engine | None" = None,
                limit: int | None = None, verbose: bool = True,
                write: bool = False,
                path: Path | str | None = None) -> dict[str, Any]:
    """§3.2: re-fit block-opening dates and demand the corpus's own rows back.

    THE TOLERANCE IS EXACT EQUALITY at the corpus's eight decimals, ruled
    before any row existed and not a number to be widened after seeing a
    difference. The reasoning is read off the code rather than assumed: the
    seed is one constant, a fit is a pure function of (cutoff, store, frozen
    config), and the project already demands and gets bit equality from two
    separate `fit_epl` calls (`walkforward.point_in_time_canary` compares with
    `np.array_equal` and returned max |Δp| = 0.0).

    ITS REAL JOB IS ARCHIVE DRIFT. The archive grew after the walk — 2025/26
    and 2026/27 results landed — and Arm A builds its store and anchor from the
    archive as it stands at run time, relying on the point-in-time property to
    make later data irrelevant. This is where that reliance becomes a check,
    and a mismatch is most likely drift rather than sampler noise. Either way
    it is a STOP.
    """
    corpus = load_corpus() if corpus is None else corpus
    threads = (assert_blas_pinned("the block-parity control") if fitter is None
               else blas_threads())

    openings = {p.cutoff: p for p in fit_points(corpus, kind="opening",
                                                check=False)}
    dates = list(dates) if dates is not None else control_dates(corpus)
    if limit:
        dates = dates[:limit]
    unknown = [d for d in dates if d not in openings]
    if unknown:
        raise ControlMismatch(f"{unknown} are not block-opening dates")

    # An engine this function BUILDS is an engine this function owns, and
    # §3.2's pre-stated condition is `fast_panel=True` — so the
    # `config_read_once` context is entered here. An engine the CALLER passes
    # in is the caller's: `main --run` opens the context around its own engine,
    # and entering it twice would nest `config_read_once` inside itself.
    owned = None
    if fitter is None:
        if engine is None:
            engine = owned = Engine(corpus, verbose=verbose)
        fitter = engine.fit

    by_id = corpus.set_index(corpus["match_id"].astype(str))
    detail, diffs, worst_rps = [], [], 0.0
    started = time.time()
    with _ExitStack() as stack:
        if owned is not None:
            stack.enter_context(owned)
        for i, date in enumerate(dates, 1):
            point = openings[date]
            t0 = time.perf_counter()
            out = fitter(point)
            probs = _check_fit(point, out)
            rows = []
            for mid, prob in zip(point.match_ids, probs):
                stored = [float(by_id.loc[str(mid), c]) for c in _PROB_COLUMNS]
                got = [round(float(v), 8) for v in prob]
                exact = [a == b for a, b in zip(got, stored)]
                d = [abs(a - b) for a, b in zip(got, stored)]
                diffs.extend(d)
                y = int(by_id.loc[str(mid), "y"])
                r = float(score_mod.rps(np.array([got]), np.array([y]))[0])
                worst_rps = max(worst_rps,
                                abs(r - float(by_id.loc[str(mid), "dc_rps"])))
                rows.append({"match_id": str(mid), "exact": all(exact),
                             "stored": stored, "refit": got,
                             "max_abs_diff": max(d)})
            detail.append({"cutoff": date, "n_fixtures": len(point.match_ids),
                           "all_exact": all(r["exact"] for r in rows),
                           "max_abs_diff": max((r["max_abs_diff"] for r in rows),
                                               default=0.0),
                           "seconds": round(time.perf_counter() - t0, 2),
                           "fixtures": rows})
            if verbose:
                print(f"[control] {i}/{len(dates)} {date} "
                      f"n={len(point.match_ids)} "
                      f"max|dp|={detail[-1]['max_abs_diff']:.3g} "
                      f"{detail[-1]['seconds']}s", flush=True)

    worst = max(diffs) if diffs else 0.0
    result = {
        "schema": SCHEMA_ID,
        "n_dates": len(dates), "dates": list(dates),
        "n_fixtures": sum(d["n_fixtures"] for d in detail),
        "n_probabilities": len(diffs),
        "max_abs_prob_diff": worst,
        "mean_abs_prob_diff": float(np.mean(diffs)) if diffs else 0.0,
        "max_abs_rps_diff": worst_rps,
        "tolerance": "exact equality at the corpus's 8 decimals",
        "rps_tolerance": 1e-12,
        "blas_threads": threads,
        "seconds": round(time.time() - started, 1),
        "PASS": bool(worst == 0.0 and worst_rps <= 1e-12),
        "detail": detail,
    }
    path = Path(path) if path is not None else CONTROL_JSON
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, default=str) + "\n")
    if not result["PASS"]:
        offenders = [d["cutoff"] for d in detail if not d["all_exact"]]
        raise ControlMismatch(
            f"the block-parity control does not return the corpus's own rows: "
            f"max |Δp| = {worst:.3g} ({worst!r}), max |ΔRPS| = "
            f"{worst_rps:.3g}, at {offenders[:5]}. §3.2 rules EXACT equality "
            "at the corpus's eight decimals and forbids widening the "
            "tolerance after seeing a difference. This is most likely archive "
            "drift since the walk, and it invalidates the pairing the whole "
            "design rests on: STOP, and write the amendment before anything "
            "continues.")
    return result


def require_control(path: Path | str | None = None, *,
                    dates: Sequence[str] | None = None) -> dict[str, Any]:
    """Refuse a matchday fit before the block-parity control has passed (§3.2).

    ``dates`` is the coverage the caller demands. The preregistered run demands
    all twenty of §3.2's dates by name, so a three-date smoke control cannot
    stand in for it; an audit run demands only that a control passed, which is
    still the ORDER the document fixes.
    """
    path = Path(path) if path is not None else CONTROL_JSON
    if not path.exists():
        raise ControlMismatch(
            f"the block-parity control has not run: there is no record at "
            f"{paths.rel(path)}. §3.2: 'The control runs FIRST; not one "
            "matchday fit is run until it passes.' Run `--control` first.")
    try:
        rec = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ControlMismatch(
            f"{paths.rel(path)} is not readable JSON: {exc}") from exc
    if not rec.get("PASS"):
        raise ControlMismatch(
            f"the control on record at {paths.rel(path)} did not pass: max "
            f"|Δp| = {rec.get('max_abs_prob_diff')!r}. §3.2 rules EXACT "
            "equality at the corpus's eight decimals and forbids widening the "
            "tolerance after seeing a difference.")
    if dates is not None:
        have = {str(d) for d in rec.get("dates", [])}
        missing = sorted({str(d) for d in dates} - have)
        if missing:
            raise ControlMismatch(
                f"the control on record covers {len(have)} date(s) and does "
                f"not cover {missing[:5]} ({len(missing)} missing). The "
                "preregistered run demands §3.2's twenty by name: a shorter "
                "control is a smoke test, not the control.")
    return rec


def require_run_preconditions(*, directory: Path | str | None = None,
                              canary_path: Path | str | None = None,
                              control_path: Path | str | None = None,
                              dates: Sequence[str] | None = None,
                              ) -> dict[str, Any]:
    """:data:`RUN_ORDER`, enforced rather than declared.

    The canary (§5.3) is a precondition of the run; the control (§3.2) is what
    runs first among the fits. Both are checked from their written records, so
    the order holds across processes and across shards — four workers each
    re-running the canary would be four answers to a question with one.
    """
    directory = Path(directory) if directory is not None else FRESHNESS_DIR
    canary = require_canary(canary_path if canary_path is not None
                            else directory / CANARY_NAME)
    control = require_control(control_path if control_path is not None
                              else directory / CONTROL_NAME, dates=dates)
    return {"canary": canary, "control": control}


# ==========================================================================
# 9. the estimand
# ==========================================================================

def _summarise(deltas: np.ndarray, blocks: Sequence[Any], *, n_boot: int,
               seed: int) -> dict[str, Any]:
    n = int(deltas.size)
    sd = float(deltas.std(ddof=1)) if n > 1 else float("nan")
    lo, hi, n_blocks = score_mod.block_bootstrap_ci(
        deltas, list(blocks), n_boot=n_boot, alpha=ALPHA, seed=seed)
    return {"n": n, "mean": float(deltas.mean()), "sd": sd,
            "se_iid": (sd / np.sqrt(n)) if n > 1 else float("nan"),
            "ci95": [lo, hi], "n_blocks": int(n_blocks)}


def _stratum_label(days: int) -> str:
    return {1: "1", 2: "2"}.get(int(days), "3+")


def estimand(rows: Sequence[dict[str, Any]], *, n_boot: int = N_BOOT,
             seed: int = BOOTSTRAP_SEED,
             expected_fixtures: int | None = None) -> dict[str, Any]:
    """§2's mean paired RPS delta, its interval, and §3's secondaries.

    The primary is the pooled mean over fixtures — not a mean of block means —
    with a percentile block bootstrap over the corpus's own (season, ISO week)
    labels at B = 10,000 and seed 20260814. Everything under ``strata`` and
    ``movement`` is §3: published with the result and deciding nothing. A
    stratum that clears the threshold while the estimand misses it does NOT
    license a staleness-conditional cadence — that is a different rule and it
    would need its own preregistration.
    """
    if not rows:
        raise MergeIncomplete("no rows to score")
    if expected_fixtures is not None and len(rows) != int(expected_fixtures):
        raise MergeIncomplete(
            f"{len(rows)} paired fixtures, not the pre-stated "
            f"{expected_fixtures}. §2 fixes the denominator and forbids "
            "dropping a fixture for any reason: a refusal is reported, a "
            "deletion is an amendment.")

    deltas = np.array([float(r["delta"]) for r in rows], dtype=float)
    blocks = [str(r["block"]) for r in rows]
    head = _summarise(deltas, blocks, n_boot=n_boot, seed=seed)

    strata: dict[str, list[dict]] = {"staleness": [], "season": []}
    labels = [_stratum_label(r["staleness_days"]) for r in rows]
    for label in ("1", "2", "3+"):
        idx = [i for i, l in enumerate(labels) if l == label]
        if not idx:
            continue
        strata["staleness"].append({
            "stratum": label,
            **_summarise(deltas[idx], [blocks[i] for i in idx],
                         n_boot=n_boot, seed=seed)})
    for season in sorted({str(r["season"]) for r in rows}):
        idx = [i for i, r in enumerate(rows) if str(r["season"]) == season]
        strata["season"].append({
            "stratum": season,
            **_summarise(deltas[idx], [blocks[i] for i in idx],
                         n_boot=n_boot, seed=seed)})

    shifts = np.abs(
        np.array([r["probs_fresh"] for r in rows], dtype=float)
        - np.array([r["probs_block"] for r in rows], dtype=float))
    interior = {}
    for days in sorted({int(r["staleness_days"]) for r in rows}):
        interior[str(days)] = int(sum(1 for r in rows
                                      if int(r["staleness_days"]) == days))

    return {
        "schema": SCHEMA_ID,
        "estimand": ("mean paired RPS delta, matchday-fit minus block-fit, "
                     "over the stale fixtures of the pinned corpus; negative "
                     "means freshness helps"),
        **head,
        "bootstrap": {"n_boot": int(n_boot), "seed": int(seed), "alpha": ALPHA,
                      "blocks": "season|ISO week", "method": "percentile"},
        "adoption_rule": {
            "threshold": ADOPT_DELTA,
            "conditions": "delta <= -0.00030 AND ci95 upper bound < 0",
            "verdict": adoption(head["mean"], head["ci95"]),
            "applied_by": "nobody — §4.5 makes adoption an owner ruling"},
        "strata": strata,
        "staleness_interior": interior,
        "movement": {
            "mean_abs_prob_shift": float(shifts.mean()),
            "max_abs_prob_shift": float(shifts.max()),
            "seed_replica_scale": {"mean": 0.0032, "p99": 0.0139,
                                   "max": 0.0229,
                                   "source": "reports/epl_walkforward.md"}},
        "decides": "nothing",
        "secondaries_decide": "nothing",
    }


def adoption(delta: float, ci95: Sequence[float]) -> str:
    """§4.1, both conditions, neither sufficient. Evaluated, never applied."""
    if float(delta) <= ADOPT_DELTA and float(ci95[1]) < 0.0:
        return "ADOPT"
    return "WEEKLY STANDS"


# ==========================================================================
# 10. the harness-hash freeze of §6
# ==========================================================================

_HEX64 = re.compile(r"\b([0-9a-f]{64})\b")


def harness_freeze_status(sources: Sequence[Path] | None = None,
                          ) -> dict[str, Any]:
    """Has §6's follow-up commit landed, and does it describe THESE bytes?

    §6 step 2: the commit adds a table of file, line count and SHA-256 for
    every harness file, carrying 07b5871's sentence — *if any hash differs at
    the time the run is executed, it is not the run this document
    preregisters*. This function reads that record and compares it with the
    files on disk. It asserts nothing about itself: an unfrozen harness is a
    fact to report, and the refusal is :func:`require_harness_freeze`'s job.
    """
    sources = [Path(s) for s in (sources or (PREREG_PATH, AMENDMENTS_PATH))]
    found: dict[str, dict[str, Any]] = {}
    where = None
    for source in sources:
        if not source.exists():
            continue
        for line in source.read_text().splitlines():
            for name in HARNESS_FILES:
                if name in line and name not in found:
                    m = _HEX64.search(line)
                    if m:
                        found[name] = {"recorded": m.group(1),
                                       "source": paths.rel(source)}
                        where = where or paths.rel(source)

    missing = [f for f in HARNESS_FILES if f not in found]
    for name, rec in found.items():
        path = paths.REPO_ROOT / name
        rec["actual"] = sha256_file(path) if path.exists() else None
        rec["lines"] = (len(path.read_text().splitlines())
                        if path.exists() else None)
        rec["match"] = bool(rec["actual"] == rec["recorded"])

    differs = [n for n, r in found.items() if not r["match"]]
    if missing:
        why = (f"no harness-hash table names {missing} — §6 step 2's follow-up "
               "commit has not landed, and step 3 says not one fit of this "
               "experiment runs before it does")
    elif differs:
        why = (f"the recorded digest for {differs} differs from the file on "
               "disk: if any hash differs at the time the run is executed, it "
               "is not the run this document preregisters (§6 step 2). §6 step "
               "4 requires an amendment BEFORE the change, with the hashes "
               "reissued alongside it")
    else:
        why = ""
    return {"frozen": not missing and not differs, "where": where,
            "files": found, "missing": missing, "why": why,
            "schema": SCHEMA_ID}


def require_harness_freeze(sources: Sequence[Path] | None = None,
                           ) -> dict[str, Any]:
    """Refuse anything that would score fits taken before §6's freeze commit.

    Raised as the base :class:`FreshnessError`: §7 pre-states this condition as
    an invalidation but §5.1 never gave it a typed name, and this module does
    not invent one after the fact.
    """
    status = harness_freeze_status(sources)
    if not status["frozen"]:
        raise FreshnessError(
            "the harness-hash freeze of §6 is not in place — " + status["why"]
            + ". The sweep may be audited and smoke-tested to a scratch "
            "ledger, but its result may not be merged or scored until the "
            "hash table is committed.")
    return status


# ==========================================================================
# 11. the merge
# ==========================================================================

def merge(shards: int = 1, *, directory: Path | str | None = None,
          corpus: pd.DataFrame | None = None, write: bool = True,
          expected: int | None = None, expected_fixtures: int | None = None,
          harness_frozen: bool | None = None, n_boot: int = N_BOOT,
          seed: int = BOOTSTRAP_SEED,
          freeze_sources: Sequence[Path] | None = None) -> dict[str, Any]:
    """Every shard, no poison, the pre-stated key set — then the estimand.

    §5.1: "The merge takes the union of shard ledgers ONLY if every shard
    exited 0 and the union's key set equals the 507 expected keys exactly — not
    a superset, not a subset. Partial results never silently merge, and a
    partial ledger is never scored."

    This function authors no verdict prose. It writes machine-readable numbers;
    `reports/epl_freshness_result.md` is written afterwards, by a person, and
    §4.4 requires it to be written whichever way the numbers fall.
    """
    freeze = (harness_freeze_status(freeze_sources) if harness_frozen is None
              else {"frozen": bool(harness_frozen), "why": "asserted by caller",
                    "files": {}, "where": None})
    if not freeze["frozen"]:
        if harness_frozen is None:
            require_harness_freeze(freeze_sources)
        raise FreshnessError(
            "refusing to merge: the §6 harness-hash freeze commit does not "
            "cover this harness, so these fits are not the run the "
            "preregistration describes (§7).")

    directory = Path(directory) if directory is not None else FRESHNESS_DIR
    corpus = load_corpus() if corpus is None else corpus
    preregistered = expected is None
    points = fit_points(corpus, check=(expected is None))
    # The preconditions gate the NUMBER, not the wall clock. A merge that
    # scored fits taken without a passing canary and a passing control would
    # publish an estimand nobody checked — so they are re-read here, from the
    # records beside these shards, however long ago they were written.
    pre = require_run_preconditions(
        directory=directory,
        dates=(control_dates(corpus) if preregistered else None))
    expected = int(expected if expected is not None else EXPECTED_FIT_DATES)
    expected_fixtures = int(expected_fixtures if expected_fixtures is not None
                            else EXPECTED_STALE)
    if len(points) != expected:
        raise ScheduleMismatch(f"{len(points)} fit points, not {expected}")

    config_sha = config_sha256()
    want_keys = {fit_key(p.cutoff, config_sha=config_sha) for p in points}

    rows: list[dict] = []
    names: list[str] = []
    for i in range(int(shards)):
        path = directory / shard_name(i, shards)
        names.append(path.name)
        if not path.exists():
            raise ShardFailed(
                f"{paths.rel(path)} is not on disk. Shards are waited on per "
                "PID and a failed shard poisons the merge; a missing ledger is "
                "a shard that never finished, and its fits are not optional.")
        part = load_ledger(path)            # raises ShardFailed on poison
        if not part:
            raise ShardFailed(f"{paths.rel(path)} holds no rows")
        mine = {fit_key(p.cutoff, config_sha=config_sha)
                for p in shard_points(points, i, shards)}
        stray = sorted({str(r["key"]) for r in part} - mine)
        if stray:
            raise MergeIncomplete(
                f"{paths.rel(path)} carries {len(stray)} key(s) outside its own "
                f"partition (first: {stray[:3]}): the shards are a partition "
                "and a row in two of them is a fixture counted twice")
        rows.extend(part)

    by_ident: dict[tuple[str, str], dict] = {}
    for row in rows:
        ident = _row_identity(row)
        if ident in by_ident:
            a = json.dumps(_strip_volatile(by_ident[ident]), sort_keys=True,
                           default=str)
            b = json.dumps(_strip_volatile(row), sort_keys=True, default=str)
            if a != b:
                raise RowConflict(f"two shards disagree about {ident}")
            continue
        by_ident[ident] = row
    rows = list(by_ident.values())

    unfrozen = sorted({str(r["cutoff"]) for r in rows
                       if not r.get("harness_frozen")})
    if unfrozen:
        raise FreshnessError(
            f"{len(unfrozen)} fit(s) carry harness_frozen: false (first: "
            f"{unfrozen[:3]}). The freeze is a property of the ROW, not of the "
            "merge's clock: a fit run during the audit is not a fit of the "
            "preregistered run, and re-stamping it would be exactly the "
            "back-dating §6 exists to prevent.")

    got_keys = {str(r["key"]) for r in rows}
    if got_keys != want_keys:
        short, extra = sorted(want_keys - got_keys), sorted(got_keys - want_keys)
        raise MergeIncomplete(
            f"the merged key set is {len(got_keys)}, not the pre-stated "
            f"{len(want_keys)}: {len(short)} missing (first: "
            f"{[k.split('|')[0] for k in short[:3]]}), {len(extra)} unexpected "
            f"(first: {[k.split('|')[0] for k in extra[:3]]}). Not a superset, "
            "not a subset.")

    check_corpus_scores(corpus)
    result = estimand(rows, n_boot=n_boot, seed=seed,
                      expected_fixtures=expected_fixtures)
    result.update({
        "n_fits": len(got_keys), "n_fixtures": len(rows),
        "shards": sorted(names), "run_digest": run_digest(rows),
        "corpus": {"path": paths.rel(CORPUS_PATH), "sha256": CORPUS_SHA256,
                   "rows": CORPUS_ROWS},
        "config": {"path": paths.rel(CONFIG_PATH), "sha256": config_sha,
                   "seed": SEED},
        "harness_freeze": freeze,
        "control": dict(pre["control"]),
        "canary": dict(pre["canary"]),
        "written_at": pd.Timestamp.now("UTC").isoformat(),
    })
    result["control"].pop("detail", None)

    if write:
        FRESHNESS_JSON.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(result, indent=2, default=str) + "\n"
        FRESHNESS_JSON.write_text(text)
        RESULT_JSON.parent.mkdir(parents=True, exist_ok=True)
        RESULT_JSON.write_text(text)
        result["written"] = [paths.rel(FRESHNESS_JSON), paths.rel(RESULT_JSON)]
    return result


# ==========================================================================
# 12. the CLI
# ==========================================================================

def _plan(corpus: pd.DataFrame, shards: int,
          directory: Path) -> dict[str, Any]:
    points = fit_points(corpus)
    return {
        "n_fit_dates": len(points),
        "n_stale_fixtures": sum(len(p.match_ids) for p in points),
        "n_blocks": len(block_openings(corpus)),
        "n_control_dates": N_CONTROL_DATES,
        "control_dates": control_dates(corpus),
        "shards": {str(i): len(shard_points(points, i, shards))
                   for i in range(shards)},
        "run_order": list(RUN_ORDER),
        "directory": paths.rel(directory),
        "preconditions": {
            "canary": (directory / CANARY_NAME).exists(),
            "control": (directory / CONTROL_NAME).exists()},
        "harness_freeze": harness_freeze_status(),
        "blas_threads": blas_threads(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", action="store_true",
                    help="print the schedule and shard sizes; fits nothing")
    ap.add_argument("--canary", action="store_true",
                    help="the point-in-time canary; §5.3's precondition, and "
                         "the first thing in RUN_ORDER")
    ap.add_argument("--control", action="store_true",
                    help="the block-parity positive control; runs FIRST (§3.2)")
    ap.add_argument("--run", action="store_true", help="Arm A's matchday fits")
    ap.add_argument("--merge", action="store_true",
                    help="verify every shard, then compute the estimand")
    ap.add_argument("--shard", default="0/1",
                    help="i/N — this worker's slice of the fit points")
    ap.add_argument("--shards", type=int, default=1,
                    help="how many shards the merge must find")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dates", default=None,
                    help="comma-separated control dates (default: the twenty)")
    ap.add_argument("--dir", dest="directory", default=None,
                    help="the run directory: the canary, the control and the "
                         f"shard ledgers (default {paths.rel(FRESHNESS_DIR)})")
    ap.add_argument("--ledger", default=None,
                    help="scratch ledger for an audit run; the preregistered "
                         "location is refused until §6's freeze commit lands")
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        index, count = (int(x) for x in str(args.shard).split("/"))
    except ValueError:
        print(f"STOP: --shard must be i/N, not {args.shard!r}", flush=True)
        return 2

    directory = Path(args.directory) if args.directory else FRESHNESS_DIR

    try:
        if args.plan:
            print(json.dumps(_plan(load_corpus(), max(count, args.shards),
                                   directory), indent=2, default=str))

        if args.canary:
            out = run_canary(path=directory / CANARY_NAME)
            print(json.dumps(out, indent=2, default=str))

        if args.control:
            corpus = load_corpus()
            check_corpus_scores(corpus)
            require_canary(directory / CANARY_NAME)     # RUN_ORDER, enforced
            out = run_control(
                dates=(args.dates.split(",") if args.dates else None),
                corpus=corpus, limit=args.limit, write=True,
                path=directory / CONTROL_NAME)
            summary = {k: v for k, v in out.items() if k != "detail"}
            print(json.dumps(summary, indent=2, default=str))

        if args.run:
            corpus = load_corpus()
            check_corpus_scores(corpus)
            frozen = harness_freeze_status()
            # §3.2 and §5.3, before a single fit: the preregistered run demands
            # the control cover all twenty of §3.2's dates by name; an audit
            # run demands only that a control passed, which is still the order.
            require_run_preconditions(
                directory=directory,
                dates=(control_dates(corpus) if frozen["frozen"] else None))
            assert_blas_pinned("the matchday sweep")
            points = shard_points(fit_points(corpus), index, count)
            if args.limit:
                points = points[:args.limit]
            ledger = Path(args.ledger) if args.ledger else \
                directory / shard_name(index, count)
            # Guard BEFORE the engine: building the store and the anchor costs
            # real time, and a run that is going to be refused should be
            # refused before it spends it.
            _guard_ledger_location(ledger, bool(frozen["frozen"]))
            if not frozen["frozen"]:
                print("[fresh] WARNING: " + frozen["why"] + " — every row of "
                      "this run is stamped harness_frozen: false and the merge "
                      "will refuse to score it.", flush=True)
            with Engine(corpus) as engine:
                out = run_fits(points, ledger, corpus, engine=engine,
                               shard_id=f"{index}/{count}",
                               harness_frozen=bool(frozen["frozen"]))
            print(json.dumps(out, indent=2, default=str))

        if args.merge:
            out = merge(shards=args.shards, n_boot=args.n_boot,
                        directory=directory)
            summary = {k: v for k, v in out.items()
                       if k not in ("control", "canary", "harness_freeze")}
            print(json.dumps(summary, indent=2, default=str))

    except FreshnessError as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
