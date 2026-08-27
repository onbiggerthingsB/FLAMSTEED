"""EVIDENCE-MASS WIDENING. Is the predicate that decides predict-time widening
keyed on the wrong quantity?

This module executes the design preregistered in
``reports/epl_widening_prereg.md`` (f26b760) and computes the estimand fixed in
its §2.3. It chooses nothing. The corpus, the archive, the walk-forward ledger
and the configuration are pinned by digest; the rule, its one constant
(``e* = 10.0``), the grid, the two-gate adoption rule, the refusal semantics and
the scope were written down before this file existed; and §4.5 makes adoption an
owner ruling that no script may take.

THE RULE, ONCE (§2.1)::

    provisional'(C) = provisional_incumbent(C) u { t : e(t, C) < 10.0 }

ADD, never REPLACE. Binary, never continuous. ``alpha`` stays 0.5 and the mix is
the incumbent one, so a treated fixture is mechanically indistinguishable from a
fixture the incumbent predicate already widens.

WHAT THE TWO ARMS ARE (§2.3, AS R-B1 REPAIRS IT). Both arms are computed from
the SAME newly fitted posterior and the SAME base grid, at every one of the 78
block openings. The superseded design read Arm B out of the corpus — an old
ROUNDED 1X2 projection — while Arm A came from a new fit; mechanism (c) acts on
the full scoreline grid BEFORE that projection, so two grids could agree at
eight decimals after projection and respond differently to
``inflate_predictive``, and "same draws, only membership differs" was asserted
about an object the control never bound.

* **Arm B**, ``dc_native``, is the block's fixtures predicted from the fitted
  posterior under **the fit's own recomputed incumbent provisional set** —
  predict pass 1. Nothing about it is read from the corpus.
* **Arm A**, ``dc_evwiden``, is the same block's fixtures predicted from **the
  same posterior object** under the §2.1 union — predict pass 2. No refit, no
  re-seed, no second sampler call: the two passes differ only in the set handed
  to ``provisional_as``. §0.2 establishes the fact the whole design stands on:
  under mechanism (c) the likelihood weight is untouched (``widening.py:48-62``
  copies ``d.weight`` and modifies it only for mechanism "a"), so **the fitted
  posterior is identical for any provisional set**.
* **The delta** is ``rps(Arm A) − rps(Arm B)``, both arms from one posterior.

THE CORPUS IS THE EXTERNAL IDENTITY CONTROL, at full strength and in no
estimand. All 820 fixtures of the 78 openings must equal Arm B at their eight
decimals (:class:`ControlMismatch`), and each stored ``dc_rps`` must equal the
RPS of its own stored probabilities to 1e-12 (:class:`ScoreMismatch`). Every row
publishes ``delta`` and ``delta_vs_corpus`` side by side, so a reader can
confirm the equality rather than take it.

THREE PREDICT PASSES PER FIT, AND WHY EACH ONE EXISTS. A fit is expensive and a
prediction is not, so this module spends predictions on making the controls real
rather than on making them cheap:

1. ``provisional = the fit's own recomputed incumbent set`` -> every fixture of
   the block, compared against the corpus at its own eight decimals. That is
   §3.2's identity control, 820 fixtures across the 78 openings, and it runs
   FIRST: not one treated probability is produced until it passes.
2. ``provisional = the §2.1 union at e* = 10`` -> every fixture of the block
   again. A fixture outside the treated set that moves is :class:`UntreatedMoved`
   — the check that the treatment touches exactly the fixtures the rule names,
   and the check that enlarging the set perturbs nothing else.
3. ``provisional = every club`` -> only the fixtures thin at some grid point and
   not already widened. This is what the grid secondaries are assembled from,
   and pass 2's treated fixtures must equal it exactly, which is how "widening
   is per fixture and does not depend on WHICH club is flagged" stops being an
   assumption.

WHAT THIS FILE MAY NOT DO (§6). It writes ``data/epl/fit/evwiden*``,
``data/epl/sim/evwiden*`` and the evidence files under ``reports/evidence/``,
and nothing else. It authors no verdict prose — ``reports/epl_widening_result.md``
is a human act after the numbers exist, required by §4.4 whichever way they
fall. It does not touch the corpus, the archive, the walk-forward ledger or
``data/epl/sim/retro_r1.jsonl``, all of which are read-only to this experiment.
And it does not run the preregistered experiment before the harness-hash freeze
commit of §6 exists: :func:`harness_freeze_status` reads that commit's own
record and :func:`merge` refuses without it, because a run that precedes the
freeze is, by §7, not the run this document preregisters.

PRE-FREEZE CONTACT WITH THE REAL ARTIFACTS, DISCLOSED. §5.3 rules that before
§6's freeze commit "no harness code touches the real archive, the real corpus,
or the real ledger except to hash them". That clause is about FITS — its own
sentence ends "and the merge would refuse their rows anyway", and §6 step 2
requires the frozen membership digests to be "recomputed by the harness's own
code from the pinned artifacts", which cannot be done without reading them. What
is therefore permitted pre-freeze, and what this harness did:

* ``--membership`` and ``--plan``, which read the pinned corpus, archive and
  ledger and compute §2.2's cells, §2.3's population and §3.3's table cells.
  Read-only, no fit, no simulation, and the output is exactly what the freeze
  commit records.
* ``--canary --no-results-canary``, which runs §5.3's evidence canary on the
  real archive. It builds a point-in-time store — in a TEMPORARY root, never the
  shared one — and runs ``count_volatility_arm``. No fit, no simulation.
* The ``@pinned`` tests in ``epl/tests/test_evwiden.py``, which check the four
  digests and re-derive the document's census, grid table, membership and table
  cells. Read-only, no fit.

NOT ONE FIT ON THE REAL ARCHIVE PRECEDED THE FREEZE. Every fitting path is
gated: :func:`_guard_ledger_location` closes the preregistered run directory
until §6's commit lands, and every row an audit writes elsewhere is stamped
``harness_frozen: false`` and refused by the merge.

NO MARKET DATA. The corpus's price columns are not read by this module at all.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# BLAS FIRST, AND ONLY AT THE ENTRY POINT — the freshness precedent, verbatim
# in its reasoning. OpenBLAS reads its thread count when it is loaded, which
# happens on `import numpy`, so a pin applied afterwards did nothing to the pool
# already running while still reconfiguring every library imported later.
# `python -m epl.evwiden` pins unconditionally and before numpy; IMPORTING this
# module does not pin, because a library that rewrites the process environment
# on import changes the behaviour of code it knows nothing about. What replaces
# the mutation is evidence: :func:`blas_threads` records what the process
# ACTUALLY has on every ledger row (§5.2) and :func:`assert_blas_pinned` refuses
# to run real fits in a process that is not pinned (§2.4).
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
import csv                                                        # noqa: E402
import hashlib                                                    # noqa: E402
import json                                                       # noqa: E402
import re                                                         # noqa: E402
import socket                                                     # noqa: E402
import tempfile                                                   # noqa: E402
import time                                                       # noqa: E402
from contextlib import contextmanager                             # noqa: E402
from dataclasses import dataclass                                 # noqa: E402
from pathlib import Path                                          # noqa: E402
from typing import Any, Callable, Iterable, Sequence              # noqa: E402

import numpy as np                                                # noqa: E402
import pandas as pd                                               # noqa: E402

from epl import paths, recalfit                                   # noqa: E402
from epl import score as score_mod                                # noqa: E402

__all__ = [
    "EvWidenError", "SCHEMA_ID", "SEED", "BOOTSTRAP_SEED", "E_STAR", "E_GRID",
    "ARM_NAME", "ADOPT_DELTA", "TABLE_TOLERANCE", "RUN_ORDER",
    "REALISED_CONFIG_SHA256", "realised_config_sha256", "assert_config_frozen",
    "load_corpus", "load_archive", "load_walk_ledger", "effective_evidence",
    "evidence_table", "prior_rows", "Membership", "membership",
    "membership_digests",
    "FitPoint", "fit_points", "shard_points", "shard_name", "fit_key",
    "canonical", "run_digest", "load_ledger", "run_fits", "Engine",
    "evidence_canary", "identity_canary", "direction_canary", "run_canary",
    "require_run_preconditions", "estimand", "adoption", "merge",
    "table_cells", "run_table", "score_table", "table_gate",
    "assert_table_identity",
    "write_evidence", "verify", "freeze_block", "harness_freeze_status",
    "require_harness_freeze",
    "launch_script", "main",
]


# ==========================================================================
# 0. THE PINS — §0.1's table, and the constants §2 fixed
# ==========================================================================

#: §0.1: the corpus is A8's own object, bound by identity and not copied, so
#: there is one place where "which corpus" is defined and one digest to break.
CORPUS_PATH = recalfit.CORPUS_PATH
CORPUS_SHA256 = recalfit.CORPUS_SHA256
CORPUS_ROWS = recalfit.CORPUS_ROWS
CORPUS_SEASONS = recalfit.CORPUS_SEASONS
CORPUS_Y_COUNTS = recalfit.CORPUS_Y_COUNTS

#: §0.1: the archive is pinned because — unlike in the freshness and anchoring
#: experiments — it is an INPUT TO THE PREDICATE UNDER TEST, not only to the
#: fits: `e(t, C)` is a sum over its rows. A parquet whose bytes have moved is a
#: different predicate input.
ARCHIVE_PATH = paths.MATCHES_PARQUET
ARCHIVE_SHA256 = \
    "323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf"
ARCHIVE_ROWS = 4560

#: §0.1: the walk-forward ledger carries `provisional_teams` **as the published
#: fits actually computed them**. It is the incumbent arm's own record, and
#: §3.2 checks each refit against it.
WALK_LEDGER_PATH = paths.FIT_DIR / "walkforward_ledger.jsonl"
WALK_LEDGER_SHA256 = \
    "869a558ce7f84ef0f4a4ebdd8f781a4a72213fd5946b4e7088d716d99e82ba9e"
WALK_LEDGER_ROWS = 212

CONFIG_PATH = paths.REPO_ROOT / "epl" / "config_frozen.json"
CONFIG_SHA256 = \
    "9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc"
SEED = 20260611

#: §0.1's realised configuration, the two fields this experiment depends on.
FROZEN_WIDENING = {"mechanism": "c", "strength": 0.5}
DECAY_HALF_LIFE_DAYS = 365.0

#: R-I1's repaired pin. `epl.freeze.frozen_wcmodel_config()` loads the LIVE
#: `config/config.yaml` and overlays only the frozen EPL Elo block, so the
#: superseded three-condition check bound `epl/config_frozen.json`, the realised
#: seed and the realised widening block AND NOTHING ELSE — not the decay
#: half-life that DEFINES `e`, not the volatility window `e* = 10.0` is taken
#: from, not the likelihood, not the ADVI block. Drift there would change `e`,
#: the posteriors or reproducibility while the documented refusal passed.
#:
#: The value is the SHA-256 of `json.dumps(frozen_wcmodel_config(),
#: sort_keys=True, default=str)`, computed 2026-08-27 under the pinned frozen
#: file and pinned by R-I1.
REALISED_CONFIG_SHA256 = \
    "78a51cd92c48838a57e3d6832b7661aad7a5b231425572214a067c2a35edbdcd"

#: §2.6-equivalent: the project's own block bootstrap, percentile, at the
#: standard resampling seed. §2.3 requires BOTH blockings and §4.1 gates on both.
BOOTSTRAP_SEED = 20260814
N_BOOT = 10_000
ALPHA = 0.05

#: §2.1's ONE FROZEN CONSTANT. It is `config/config.yaml`'s
#: `elo.volatility_window: 10` — the ten-match window this codebase already uses
#: twice as its operational definition of the informative recent past. It is not
#: tuned, not swept, and §7 makes moving it an invalidation.
E_STAR = 10.0

#: §3.1's grid. It exists to be REPORTED and never selected from; §2.1 pre-states
#: the cost of a neighbour looking better, and :func:`adoption` reads only
#: :data:`E_STAR`.
E_GRID: tuple[float, ...] = (1.0, 3.0, 5.0, 8.0, 12.0)

#: The grid points at which §3.1 pre-states a delta of exactly 0.000000 with a
#: degenerate interval BY CONSTRUCTION (zero treated fixtures), so an identically
#: zero row cannot be presented as either a finding or a failure.
E_GRID_DEGENERATE: tuple[float, ...] = (1.0, 3.0)

#: §0.1 / §2.1: the incumbent mix strength, unchanged. A treated fixture receives
#: exactly the one incumbent mix.
WIDENING_ALPHA = 0.5

#: §2.3's arm name, ruled in the document and grep-verified not to collide.
ARM_NAME = "dc_evwiden"
BASELINE_ARM = "dc_native"

#: §4.1 (i) — the HOUSE model-change bar, argued in §4.2 and not lowered to
#: freshness's operational -0.00030, because this changes the published
#: probabilities themselves.
ADOPT_DELTA = -0.0010

#: §4.1 (iv) — the table gate, invented from R1's own recorded scale and
#: disclosed as invented in §4.3.
TABLE_TOLERANCE = 0.0002

#: §0.1 / §0.4's counts. A corpus, archive or ledger that does not produce them
#: is a different object, not a smaller experiment.
EXPECTED_BLOCKS = 212
EXPECTED_CELLS = 4240                  # 20 season clubs x 212 cutoffs
EXPECTED_INCUMBENT_FIXTURES = 46       # §0.4: 46 of 2,280 (2.02%)

#: §2.2 / §2.3's frozen membership at `e* = 10`.
EXPECTED_THIN = 85
EXPECTED_TREATED = 52
EXPECTED_NEW_CELLS = 51
EXPECTED_NEW_CELLS_PLAYING = 47
EXPECTED_PRIMARY_BLOCKS = 62
#: §2.3: one fit at each of the 78 block openings whose block holds a thin
#: fixture at ANY grid `e*` (the `e* < 12` union); §3.2's control covers all 820
#: fixtures of those blocks.
EXPECTED_FIT_OPENINGS = 78
EXPECTED_CONTROL_FIXTURES = 820

#: §2.3's per-season split of the 85, pre-stated so a corpus that reshuffles
#: them is caught rather than averaged over.
EXPECTED_THIN_BY_SEASON = {"2019/20": 26, "2020/21": 11, "2021/22": 12,
                           "2022/23": 12, "2023/24": 12, "2024/25": 12}

#: §3.3's table leg: `SEASONS` x `COMPARISON_CUTOFFS`, of which 16 change and
#: 19 are unchanged BY CONSTRUCTION and the harness must prove it.
EXPECTED_TABLE_CELLS = 35
EXPECTED_TABLE_TREATED = 16
EXPECTED_TABLE_UNTOUCHED = 19

#: §3.1's movement diagnostic prints the treatment beside the ADVI re-seed scale
#: from `reports/epl_walkforward.md`, so "did the treatment move more than
#: re-seeding does" is on the record whichever way the estimand lands.
RESEED_SCALE = {"per_match_mean": 0.0032, "per_match_p99": 0.0139,
                "per_match_max": 0.0229, "pooled_shift": 0.000075,
                "source": "reports/epl_walkforward.md"}

#: The schema identifier §6 step 2's freeze commit must name alongside the
#: hashes.
SCHEMA_ID = "epl-evwiden-1"

#: §6: "all code lands in `epl/evwiden.py` and `epl/tests/test_evwiden.py`".
#: The document names exactly two files and this module adds no third: the
#: detached-launch runner is GENERATED by :func:`launch_script` into the run
#: directory, so the launcher's bytes are a function of these hashed bytes
#: rather than a source file nobody hashed. The tests are in the list because a
#: test that stops asserting is a guard that stopped guarding.
HARNESS_FILES = ("epl/evwiden.py", "epl/tests/test_evwiden.py")

#: §3.2 runs the identity control FIRST among the fits; §5.3 puts the canaries
#: before even that. ENFORCED by :func:`require_run_preconditions` from the
#: written records, because an order declared in a constant and checked by
#: nobody is a comment.
RUN_ORDER = ("canary", "run", "table", "merge")

#: §5.2's list, fixed in the document before any row existed: recorded on the
#: row, excluded from the canonical form and from every digest.
_VOLATILE = ("wall_seconds", "fit_seconds", "seconds", "shard_id",
             "started_at", "host")

#: Where the run writes. §6 closes the set to `data/epl/fit/evwiden*`,
#: `data/epl/sim/evwiden*`, the result document and the evidence files.
EVWIDEN_DIR = paths.FIT_DIR / "evwiden"
EVWIDEN_JSON = paths.FIT_DIR / "evwiden.json"
TABLE_DIR = paths.DATA_DIR / "sim" / "evwiden"
TABLE_LEDGER = TABLE_DIR / "table_cells.jsonl"
CANARY_NAME = "canary.json"
CANARY_JSON = EVWIDEN_DIR / CANARY_NAME
LAUNCH_NAME = "launch.sh"

#: §6's evidence contract, regardless of outcome (ultra-review lesson 1: the
#: verdict's machine-readable basis is COMMITTED, not gitignored).
EVIDENCE_DIR = paths.REPO_ROOT / "reports" / "evidence"
EVIDENCE_JSON = EVIDENCE_DIR / "widening.json"
EVIDENCE_PER_FIXTURE = EVIDENCE_DIR / "widening_per_fixture.csv"
EVIDENCE_TABLE_CELLS = EVIDENCE_DIR / "widening_table_cells.csv"
EVIDENCE_GRID_MEANS = EVIDENCE_DIR / "widening_grid_means.csv"
EVIDENCE_MANIFEST = EVIDENCE_DIR / "MANIFEST.sha256"

WRITES = (EVWIDEN_DIR, EVWIDEN_JSON, TABLE_DIR, TABLE_LEDGER, CANARY_JSON,
          EVIDENCE_JSON, EVIDENCE_PER_FIXTURE, EVIDENCE_TABLE_CELLS,
          EVIDENCE_GRID_MEANS, EVIDENCE_MANIFEST)

#: Where §6's freeze commit records the harness hashes.
PREREG_PATH = paths.REPO_ROOT / "reports" / "epl_widening_prereg.md"
AMENDMENTS_PATH = paths.REPO_ROOT / "reports" / "epl_sim_amendments.md"

#: §5.2's row contract, at the two levels the ledger carries it.
REQUIRED_ROW_FIELDS = (
    "schema", "key", "match_id", "season", "block", "cutoff", "date",
    "home_key", "away_key", "y", "e_home", "e_away", "e_min", "e_star",
    "thin_at", "thin", "treated", "incumbent_widened",
    "probs_native", "probs_incumbent", "probs_arm", "probs_widened",
    "rps_native", "rps_native_recomputed", "rps_B", "rps_arm", "delta",
    "delta_vs_corpus", "max_abs_dp_vs_corpus",
    "seed", "config_sha256", "arm_a", "arm_b", "corpus_control", "fit",
    "harness_frozen", "shard_id", "seconds",
)
REQUIRED_FIT_FIELDS = (
    "cutoff", "seed", "config_sha256", "realised_config_sha256",
    "n_training_matches", "n_teams", "n_fixtures", "match_ids",
    "cold_start_teams", "provisional_incumbent", "provisional_enlarged",
    "provisional_ledger", "evidence", "anchor_spec", "warnings",
    "unpriceable", "health", "harness_sha256", "archive_rows",
    "archive_sha256", "ledger_sha256", "blas_threads", "wall_seconds",
    "latest_training_date", "control_max_abs_diff", "control_mean_abs_diff",
    "identity_canary", "direction_canary",
)

_PROB_COLUMNS = ("dc_home", "dc_draw", "dc_away")

#: The eight decimals `epl/walkforward.py::_one_cutoff` wrote the corpus with.
#: §2.3 rules exact equality AT THEM, and §7 makes widening the tolerance after
#: a mismatch an invalidation.
ROUND_DP = 8


# ==========================================================================
# 1. THE TYPED REFUSALS — §5.1, by name
# ==========================================================================

class EvWidenError(RuntimeError):
    """Anything this experiment refuses.

    §5.1 names the subclasses and this module does not invent one the document
    never wrote. A condition the preregistration pre-stated as an INVALIDATION
    but never gave an error name — §7's "a real-archive fit runs before the §6
    freeze commit" is the one that matters in practice — is refused as this base
    class instead, which is `epl.freshsweep`'s ruling on the same question,
    applied here for the same reason: a typed name is a promise the
    preregistration made, and inventing one after the fact is the small end of
    the wedge this whole apparatus exists to block.
    """


class CorpusMissing(EvWidenError):
    """The pinned parquet is not on disk."""


class CorpusDigestMismatch(EvWidenError):
    """The corpus is not the corpus the experiment was preregistered on."""


class CorpusShapeMismatch(EvWidenError):
    """Rows, seasons, blocks or outcome counts are not the pinned ones."""


class ArchiveDigestMismatch(EvWidenError):
    """`data/epl/matches.parquet` is not `323aa54af0…` or not 4,560 rows.

    §0.1: the archive is an INPUT TO THE PREDICATE here, not only to the fits.
    """


class LedgerDigestMismatch(EvWidenError):
    """The walk-forward ledger is not `869a558ce7…` or not 212 rows."""


class ConfigNotFrozen(EvWidenError):
    """The config is not `9f2e086d…`, the seed is not 20260611, widening is not
    `{mechanism: c, strength: 0.5}`, or — R-I1's fourth condition — the REALISED
    configuration does not hash to `78a51cd9…`."""


class MembershipMismatch(EvWidenError):
    """The recomputed enumeration differs from the §6 frozen digests."""


class PredicateMismatch(EvWidenError):
    """A fit's own provisional set differs from the ledger's record at that
    cutoff (§3.2) — the control that the incumbent arm being re-keyed is the
    incumbent arm that published."""


class EvidenceLeak(EvWidenError):
    """A match dated on or after its cutoff contributes to some `e(t, C)`."""


class CutoffLeak(EvWidenError):
    """A training frame holds a match dated on or after its cutoff, or a fixture
    appears in the fit that prices it."""


class CanaryFailed(EvWidenError):
    """`epl.walkforward.point_in_time_canary` did not pass (§5.3)."""


class EvidenceCanaryFailed(EvWidenError):
    """Either leg of the two-legged evidence canary failed (§5.3).

    A canary that cannot fail is not a canary, so the positive control is as
    much a part of this refusal as the negative leg.
    """


class ControlMismatch(EvWidenError):
    """One of the 820 identity-control probabilities differs from the corpus at
    eight decimals (§3.2)."""


class UntreatedMoved(EvWidenError):
    """An Arm-A fixture outside the treated set differs from the corpus."""


class TableIdentityBreak(EvWidenError):
    """An untouched table cell's treatment digest differs from its control's."""


class FitFailed(EvWidenError):
    """`fit_epl` raised, or the posterior it produced is not usable."""


class UnpriceableFixture(EvWidenError):
    """A club is absent from the posterior index at a cutoff that prices it.

    §2.3 fixes the population at 85 and forbids dropping a fixture, so this is a
    defect by construction and never a dropped row.
    """


class ScoreMismatch(EvWidenError):
    """Stored RPS does not re-derive from the stored probabilities."""


class SchemaMismatch(EvWidenError):
    """A ledger row lacks a field §5.2 requires."""


class RowConflict(EvWidenError):
    """Two rows share a key and disagree on a non-volatile field."""


class ShardFailed(EvWidenError):
    """A shard is missing, empty, or still carries a poison row."""


class MergeIncomplete(EvWidenError):
    """The merged key set is not exactly the pre-stated one."""


class TableMCImprecise(EvWidenError):
    """R-B3's paired Monte-Carlo error cannot be computed (R2-X, the 23rd).

    R2-B3 step 2 names the structural conditions: unequal per-particle season
    counts, or an ``n_particles`` that differs across the 16 deciding cells or
    between a cell's two arms. Joint resampling is undefined without a common
    index space and this document will not approximate one.

    R2-X is explicit that gate (iv) being left UNRESOLVED by the precision rule
    (P1)-(P5) is **not** a refusal and raises nothing: UNRESOLVED is a published
    verdict, it blocks adoption, and conflating the two would make the harness
    raise on a result it is required to publish.
    """


# ==========================================================================
# 2. DIGESTS, THE CORPUS, THE ARCHIVE, THE LEDGER, THE CONFIGURATION
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


def realised_config_sha256(cfg: dict) -> str:
    """R-I1's digest of the configuration the run actually realises.

    One definition, in one place, so the constant, the check and the ledger row
    cannot drift apart: ``sha256(json.dumps(cfg, sort_keys=True,
    default=str))``.
    """
    return hashlib.sha256(
        json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def assert_config_frozen(path: Path | str | None = None,
                         cfg: dict | None = None) -> str:
    """Refuse a configuration that is not the frozen one (§5.1, as R-I1 repairs it).

    FOUR things, not three: the file's digest, the realised seed, the realised
    widening block, and — R-I1's repair — a digest of the WHOLE realised
    configuration.

    The widening block is not decoration: this experiment is defined on
    mechanism (c) at strength 0.5, and under mechanism (a) the widening would
    move into the LIKELIHOOD, the posterior would stop being arm-invariant, and
    every pairing claim in §2.3 would be false.

    The fourth condition is the one R-I1 added, and it is the one that binds
    everything §0.1 quoted and the superseded check held none of:
    ``windows.decay_half_life_days = 365`` (which DEFINES `e`),
    ``elo.volatility_window = 10`` (which `e* = 10.0` is taken from),
    ``model.inference`` and the rest of the live YAML.
    """
    path = Path(path) if path is not None else CONFIG_PATH
    if not path.exists():
        raise ConfigNotFrozen(f"{paths.rel(path)} is not on disk: this "
                              "experiment is defined on the frozen config")
    got = sha256_file(path)
    if got != CONFIG_SHA256:
        raise ConfigNotFrozen(
            f"{paths.rel(path)} is {got[:10]}…, not {CONFIG_SHA256[:10]}…: a "
            "different configuration answers a different question")
    if cfg is not None:
        if int(cfg.get("seed", -1)) != SEED:
            raise ConfigNotFrozen(
                f"the realised configuration's seed is {cfg.get('seed')!r}, not "
                f"{SEED}: §0.1 pins the seed as one constant")
        widening = dict((cfg.get("model") or {}).get("widening") or {})
        realised = {"mechanism": str(widening.get("mechanism")),
                    "strength": float(widening.get("strength", -1))}
        if realised != FROZEN_WIDENING:
            raise ConfigNotFrozen(
                f"the realised widening is {realised}, not {FROZEN_WIDENING}. "
                "§0.2's whole design rests on mechanism (c) being a PREDICT-TIME "
                "mix that leaves the likelihood weight untouched, which is what "
                "makes the fitted posterior identical across arms. Under (a) it "
                "is not, and the pairing this experiment reports would be a "
                "comparison of two different posteriors.")
        realised_digest = realised_config_sha256(cfg)
        if realised_digest != REALISED_CONFIG_SHA256:
            raise ConfigNotFrozen(
                f"the realised configuration hashes to {realised_digest}, not "
                f"the pinned {REALISED_CONFIG_SHA256}. R-I1 pins the digest of "
                "`freeze.frozen_wcmodel_config()` itself, because that function "
                "loads the LIVE config/config.yaml and overlays only the frozen "
                "EPL Elo block: the decay half-life that DEFINES `e`, the "
                "volatility window `e* = 10.0` is taken from, the likelihood and "
                "the ADVI block all come from a file the frozen-file digest does "
                "not bind. A drift there changes `e`, the posteriors or "
                "reproducibility while the superseded three-condition check "
                "passes.")
    return got


def load_corpus(path: Path | str | None = None, *,
                require_digest: bool = True) -> pd.DataFrame:
    """The pinned walk-forward corpus, checked by digest before it is read.

    The shape check is not redundant beside the digest: a digest tells you the
    bytes changed and this tells you WHAT about them changed, which is the
    difference between a STOP somebody can act on and one they can only rerun.
    """
    path = Path(path) if path is not None else CORPUS_PATH
    if not path.exists():
        raise CorpusMissing(
            f"{paths.rel(path)} is not on disk. This experiment is defined on "
            "that corpus by digest; there is nothing to fall back to and "
            "nothing to recompute.")
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
        assert_corpus_shape(frame)
    return frame


def assert_corpus_shape(frame: pd.DataFrame) -> None:
    """§5.1's `CorpusShapeMismatch`: 2,280 rows, 6 seasons, 212 blocks, y counts."""
    problems: list[str] = []
    if len(frame) != CORPUS_ROWS:
        problems.append(f"{len(frame)} rows, not {CORPUS_ROWS}")
    seasons = tuple(sorted(set(frame["season"].astype(str))))
    if seasons != tuple(sorted(CORPUS_SEASONS)):
        problems.append(f"seasons {seasons}, not {tuple(sorted(CORPUS_SEASONS))}")
    if "block" in frame.columns and frame["block"].nunique() != EXPECTED_BLOCKS:
        problems.append(f"{frame['block'].nunique()} blocks, not {EXPECTED_BLOCKS}")
    counts = tuple(int((frame["y"].to_numpy() == k).sum()) for k in (0, 1, 2))
    if counts != tuple(CORPUS_Y_COUNTS):
        problems.append(f"y counts {counts}, not {tuple(CORPUS_Y_COUNTS)}")
    missing = [c for c in (*_PROB_COLUMNS, "dc_rps", "block", "date",
                           "match_id", "home_key", "away_key", "y", "season")
               if c not in frame.columns]
    if missing:
        problems.append(f"the corpus lacks {missing}")
    if problems:
        raise CorpusShapeMismatch("; ".join(problems))


def check_corpus_scores(frame: pd.DataFrame) -> dict[str, Any]:
    """Arm B's stored RPS, re-derived from Arm B's own stored probabilities.

    §2.3: the harness recomputes it and refuses a disagreement beyond 1e-12. A
    corpus whose own columns disagree cannot be one arm of a paired comparison.
    """
    recomputed = score_mod.rps(frame[list(_PROB_COLUMNS)].to_numpy(float),
                               frame["y"].to_numpy())
    diff = np.abs(recomputed - frame["dc_rps"].to_numpy(float))
    worst = float(diff.max()) if diff.size else 0.0
    if worst > 1e-12:
        bad = frame["match_id"].to_numpy()[int(np.argmax(diff))]
        raise ScoreMismatch(
            f"stored dc_rps and the RPS of the stored probabilities differ by "
            f"{worst:.3g} at match {bad}: Arm B is the corpus's own number.")
    return {"n": int(len(frame)), "max_abs_diff": worst}


def load_archive(path: Path | str | None = None, *,
                 require_digest: bool = True) -> pd.DataFrame:
    """The pinned results archive — the predicate's own input (§0.1).

    Returns the PLAYED frame, date-normalised, because `e(t, C)` is defined on
    "the same played frame the fit trains on" (§0.3) and a fixture with no
    result carries no evidence about anybody.
    """
    path = Path(path) if path is not None else ARCHIVE_PATH
    if not path.exists():
        raise ArchiveDigestMismatch(
            f"{paths.rel(path)} is not on disk. §0.1 pins the archive by digest "
            "because the effective-evidence quantity of §0.3 is a sum over its "
            "rows: without it the predicate under test has no input.")
    if require_digest:
        got = sha256_file(path)
        if got != ARCHIVE_SHA256:
            raise ArchiveDigestMismatch(
                f"{paths.rel(path)} hashes to {got}, not {ARCHIVE_SHA256}. The "
                "archive is an INPUT TO THE PREDICATE here, not only to the "
                "fits: a parquet whose bytes have moved is a different "
                "predicate input and a different experiment.")
    frame = pd.read_parquet(path)
    if require_digest and len(frame) != ARCHIVE_ROWS:
        raise ArchiveDigestMismatch(
            f"{paths.rel(path)} holds {len(frame)} rows, not {ARCHIVE_ROWS}")
    played = frame.loc[frame["played"]].copy()
    played["date"] = pd.to_datetime(played["date"]).dt.normalize()
    return played


def load_walk_ledger(path: Path | str | None = None, *,
                     require_digest: bool = True) -> dict[str, set[str]]:
    """cutoff -> the provisional set the PUBLISHED fit actually computed (§0.1).

    This is not a recomputation and must not become one: §3.2's
    :class:`PredicateMismatch` compares each refit against this record, and a
    "ledger" this module derived from the same code it is checking would check
    nothing.
    """
    path = Path(path) if path is not None else WALK_LEDGER_PATH
    if not path.exists():
        raise LedgerDigestMismatch(
            f"{paths.rel(path)} is not on disk. §3.2's predicate control is "
            "defined against the published fits' own record of who was "
            "provisional; without it there is no control.")
    if require_digest:
        got = sha256_file(path)
        if got != WALK_LEDGER_SHA256:
            raise LedgerDigestMismatch(
                f"{paths.rel(path)} hashes to {got}, not {WALK_LEDGER_SHA256}")
    rows = [json.loads(line) for line in path.read_text().splitlines()
            if line.strip()]
    if require_digest and len(rows) != WALK_LEDGER_ROWS:
        raise LedgerDigestMismatch(
            f"{paths.rel(path)} holds {len(rows)} rows, not {WALK_LEDGER_ROWS}")
    out: dict[str, set[str]] = {}
    for row in rows:
        cutoff = str(row["cutoff"])
        teams = {str(t) for t in (row.get("provisional_teams") or ())}
        if cutoff in out and out[cutoff] != teams:
            raise LedgerDigestMismatch(
                f"the walk-forward ledger holds two rows for {cutoff} with "
                "different provisional sets")
        out[cutoff] = teams
    return out


def blas_threads() -> dict[str, Any]:
    """What this process ACTUALLY has, recorded on every row (§5.2).

    Not what it asked for: the environment is read back, and
    ``pinned_before_numpy`` says whether the pin could have reached the BLAS
    pool at all.
    """
    out: dict[str, Any] = {v: _os.environ.get(v) for v in BLAS_VARS}
    out["pinned_before_numpy"] = bool(_IS_ENTRY_POINT
                                      and not _NUMPY_ALREADY_IMPORTED)
    out["entry_point"] = bool(_IS_ENTRY_POINT)
    return out


def assert_blas_pinned(where: str) -> dict[str, Any]:
    """§2.4's pre-stated condition: one BLAS thread per worker, for real fits."""
    threads = blas_threads()
    unpinned = [v for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                            "MKL_NUM_THREADS") if threads.get(v) != "1"]
    if unpinned:
        raise EvWidenError(
            f"{where} runs real fits and this process is not pinned to one BLAS "
            f"thread per worker: {unpinned} are "
            f"{[threads.get(v) for v in unpinned]}. §2.4 pre-states the "
            "condition and §5.2 records it per row. Run as `python -u -m "
            "epl.evwiden`, which pins before numpy loads, or export the three "
            "variables before starting the worker.")
    return threads


#: The archive fields the module-level digest binds — the freshness §6-step-4
#: lesson, adopted from day one (§5.2). A digest that silently narrows to the
#: columns it happens to find is not a digest, so the fields are named and their
#: absence refuses.
ARCHIVE_DIGEST_COLUMNS = ("match_id", "date", "fthg", "ftag")


def archive_digest(played: pd.DataFrame) -> str:
    """SHA-256 over the archive rows that decide a fit: ids, dates, SCORES."""
    missing = [c for c in ARCHIVE_DIGEST_COLUMNS if c not in played.columns]
    if missing:
        raise SchemaMismatch(
            f"the results archive lacks {missing}, which "
            f"{list(ARCHIVE_DIGEST_COLUMNS)} names: the digest binds the scores "
            "a fit trains on, and a column filter that quietly drops them would "
            "bind ids and dates and nothing else.")
    frame = played[list(ARCHIVE_DIGEST_COLUMNS)].astype(str).sort_values("match_id")
    return hashlib.sha256(frame.to_csv(index=False).encode("utf-8")).hexdigest()


# ==========================================================================
# 3. EFFECTIVE EVIDENCE — §0.3's quantity, defined once and computed once
# ==========================================================================

def prior_rows(played: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """The archive rows an evidence sum at ``cutoff`` may see: ``date < C``.

    One function, one comparison, one place for §5.3's seeded defect to replace
    — and one place a future reader has to look to answer "what could this fit
    see?". ``features.build`` keeps ``date < cutoff.normalize()`` and this is the
    same rule on the same frame.
    """
    dates = pd.to_datetime(played["date"]).dt.normalize()
    return played.loc[dates < pd.Timestamp(cutoff).normalize()]


def effective_evidence(cutoff: str | pd.Timestamp, played: pd.DataFrame,
                       clubs: Sequence[str] | None = None,
                       *, half_life_days: float = DECAY_HALF_LIFE_DAYS,
                       check_leak: bool = True) -> dict[str, float]:
    """§0.3, verbatim::

        e(t, C) = SUM  0.5 ** (age_days / 365)   over archive matches of t with
                                                 date < C, age_days = (C - date)

    THIS IS THE FIT'S OWN LIKELIHOOD WEIGHT, NOT A NEW NUMBER.
    ``src/wcmodel/data/features.py:297`` computes ``decay_weight = 0.5 **
    (age_days / half_life)`` with ``half_life = 365`` and
    ``src/wcmodel/model/panel.py:34-36`` renames it to the panel's ``weight`` —
    the weight every training match carries in the likelihood. ``e(t, C)`` is
    the summed weight of the club's own matches: how much decayed evidence about
    this club the likelihood actually holds.

    It is venue-blind (a club accrues evidence home and away alike), it covers
    EVERY archive row — deliberately **not** restricted to ``in_feature_window``,
    because the likelihood is not — it is computed on the played frame the fit
    trains on, and it is recomputed at every cutoff, so it drifts upward within a
    season as the club plays. Units: match-equivalents at full weight.

    ``check_leak`` is §5.1's :class:`EvidenceLeak`, and it is placed where it
    can actually fail. A guard that re-applied the same ``date < C`` comparison
    to the frame that comparison just produced would be a tautology, and the one
    thing a leak guard may not be is unable to go red. So the check is made on
    the AGES THAT WEIGHT THE SUM, downstream of the filter: a match dated on the
    cutoff has ``age_days = 0`` and would enter at full weight ``0.5 ** 0 = 1``,
    and a later one enters at MORE than full weight. Demanding every contributing
    age be strictly positive therefore catches a filter that admits either —
    which is exactly what :func:`prior_rows` being replaced by a ``<=`` variant
    does, and what §5.3's seeded defect does to it.
    """
    ts = pd.Timestamp(cutoff).normalize()
    prior = prior_rows(played, ts)
    keys = (clubs if clubs is not None
            else sorted(set(prior["home_key"].astype(str))
                        | set(prior["away_key"].astype(str))))
    out = {str(c): 0.0 for c in keys}
    if not len(prior):
        return out
    age = (ts - pd.to_datetime(prior["date"]).dt.normalize()).dt.days.to_numpy(float)
    if check_leak and age.size and float(np.nanmin(age)) <= 0.0:
        n_bad = int((age <= 0).sum())
        raise EvidenceLeak(
            f"{n_bad} match(es) dated on or after cutoff {ts.date()} contribute "
            f"to the evidence sum (smallest age {float(np.nanmin(age)):.0f} "
            "days). `e(t, C)` sums matches with date < C at weight "
            "0.5 ** (age/365); an age of zero enters at FULL weight and a "
            "negative age at more than full, so this is the predicate under "
            "test seeing the future it is supposed to be blind to.")
    weight = 0.5 ** (age / float(half_life_days))
    for column in ("home_key", "away_key"):
        side = prior[column].astype(str).to_numpy()
        for club, w in zip(side, weight):
            if club in out:
                out[club] += float(w)
    return out


def block_openings(corpus: pd.DataFrame) -> dict[str, str]:
    """block label -> its opening day, as an ISO date string.

    Recomputing the cutoff as each block's minimum fixture date reproduces the
    walk-forward ledger's own ``cutoff`` field for all 2,280 rows — checked
    rather than assumed by :func:`assert_ledger_covers`.
    """
    opens = corpus.groupby("block")["date"].min()
    return {str(b): str(pd.Timestamp(d).date()) for b, d in opens.items()}


def assert_ledger_covers(corpus: pd.DataFrame,
                         ledger: dict[str, set[str]]) -> None:
    """Every block opening must be a cutoff the published walk actually ran.

    If the corpus's own minimum-date recipe produced a cutoff the ledger has
    never heard of, the two objects are not describing the same run and §3.2's
    predicate control would be comparing a refit against nothing.
    """
    missing = sorted(set(block_openings(corpus).values()) - set(ledger))
    if missing:
        raise LedgerDigestMismatch(
            f"{len(missing)} block opening(s) are absent from the walk-forward "
            f"ledger (first: {missing[:3]}): the corpus and the ledger do not "
            "describe the same run, so the predicate control has nothing to "
            "compare a refit against.")


def evidence_table(corpus: pd.DataFrame, played: pd.DataFrame,
                   ) -> dict[str, dict[str, float]]:
    """`e` for every season club at every block opening — §0.4's 4,240 cells.

    A cell is one (block, club) pair where the club plays in the block's OWN
    SEASON, which is the population §0.4 measured and §2.2 counts the 51
    newly-flagged cells out of. It is deliberately wider than "clubs that play
    in this block": the predicate is a property of a club at a cutoff, not of a
    fixture, and a club that is evidence-thin in a week it does not play is
    still evidence-thin.
    """
    opens = block_openings(corpus)
    season_of = {str(b): str(part["season"].iloc[0])
                 for b, part in corpus.groupby("block")}
    clubs_of: dict[str, list[str]] = {}
    for season, part in corpus.groupby("season"):
        clubs_of[str(season)] = sorted(set(part["home_key"].astype(str))
                                       | set(part["away_key"].astype(str)))
    return {block: effective_evidence(cut, played, clubs_of[season_of[block]])
            for block, cut in sorted(opens.items())}


# ==========================================================================
# 4. THE MEMBERSHIP — §2.2's cells, §2.3's 85 and 52, §3.1's grid
# ==========================================================================

def fixture_key(match_id: str) -> str:
    """The pairing key. The corpus's own `match_id`, and nothing derived.

    A key built out of clubs and a date would let a substitution — the same two
    clubs on the same day, a different fixture — rejoin silently; the corpus
    carries an id and the merge uses it.
    """
    return str(match_id)


@dataclass(frozen=True)
class Membership:
    """Who is thin, who is treated, and which fits that costs — §2.2 and §2.3.

    Every collection is sorted, so the digests of :func:`membership_digests` are
    a function of the membership and not of a dict's insertion order.
    """

    e_star: float
    #: (block, club) pairs with `e < e*` and no incumbent flag in the ledger.
    new_cells: tuple[tuple[str, str], ...]
    #: the subset of `new_cells` whose club actually plays in that block.
    new_cells_playing: tuple[tuple[str, str], ...]
    #: match ids whose thinner side has `e < e*`.
    thin: tuple[str, ...]
    #: thin fixtures the incumbent predicate does not already widen.
    treated: tuple[str, ...]
    #: the block openings holding a thin fixture, as ISO dates.
    blocks: tuple[str, ...]
    #: per-fixture facts, keyed by match id.
    detail: dict[str, dict[str, Any]]

    @property
    def already_widened(self) -> tuple[str, ...]:
        treated = set(self.treated)
        return tuple(m for m in self.thin if m not in treated)


def _fixture_frame(corpus: pd.DataFrame, played: pd.DataFrame,
                   ledger: dict[str, set[str]],
                   evidence: dict[str, dict[str, float]] | None = None,
                   ) -> pd.DataFrame:
    """The corpus with `e` on both sides and the incumbent verdict per fixture."""
    evidence = evidence_table(corpus, played) if evidence is None else evidence
    opens = block_openings(corpus)
    frame = corpus.copy()
    frame["block"] = frame["block"].astype(str)
    frame["cutoff"] = frame["block"].map(opens)
    frame["home_key"] = frame["home_key"].astype(str)
    frame["away_key"] = frame["away_key"].astype(str)
    frame["e_home"] = [evidence[b][h] for b, h in
                       zip(frame["block"], frame["home_key"])]
    frame["e_away"] = [evidence[b][a] for b, a in
                       zip(frame["block"], frame["away_key"])]
    frame["e_min"] = np.minimum(frame["e_home"].to_numpy(float),
                                frame["e_away"].to_numpy(float))
    frame["incumbent"] = [
        (h in ledger[c]) or (a in ledger[c])
        for h, a, c in zip(frame["home_key"], frame["away_key"], frame["cutoff"])]
    return frame


def membership(corpus: pd.DataFrame, played: pd.DataFrame,
               ledger: dict[str, set[str]], *, e_star: float = E_STAR,
               evidence: dict[str, dict[str, float]] | None = None,
               frame: pd.DataFrame | None = None) -> Membership:
    """§2.1's rule, applied: who is newly flagged, which fixtures that reaches.

    THIN is a property of the FIXTURE — "a fixture whose thinner side has
    `e < e*`" (§1.4) — and TREATED is the thin fixtures the incumbent predicate
    does not already widen. The distinction is the whole reason §2.3 states the
    dilution up front: 33 of the 85 carry a delta of exactly 0.0 by
    construction, and the estimand's sign equals the treated subset's by
    arithmetic at 52/85 of its size.
    """
    evidence = evidence_table(corpus, played) if evidence is None else evidence
    frame = (_fixture_frame(corpus, played, ledger, evidence)
             if frame is None else frame)
    opens = block_openings(corpus)

    plays: set[tuple[str, str]] = set()
    for block, part in frame.groupby("block"):
        for club in (set(part["home_key"]) | set(part["away_key"])):
            plays.add((str(block), str(club)))

    cells = [(block, club) for block, per_club in sorted(evidence.items())
             for club, value in sorted(per_club.items())
             if value < float(e_star) and club not in ledger[opens[block]]]

    thin_frame = frame.loc[frame["e_min"] < float(e_star)]
    thin = tuple(sorted(fixture_key(m) for m in thin_frame["match_id"]))
    treated = tuple(sorted(fixture_key(m) for m in
                           thin_frame.loc[~thin_frame["incumbent"], "match_id"]))
    blocks = tuple(sorted({opens[b] for b in thin_frame["block"]}))

    detail = {
        fixture_key(row.match_id): {
            "season": str(row.season), "block": str(row.block),
            "cutoff": str(row.cutoff), "home_key": str(row.home_key),
            "away_key": str(row.away_key),
            "e_home": float(row.e_home), "e_away": float(row.e_away),
            "e_min": float(row.e_min),
            "incumbent_widened": bool(row.incumbent),
        }
        for row in thin_frame.itertuples()}

    return Membership(e_star=float(e_star), new_cells=tuple(cells),
                      new_cells_playing=tuple(c for c in cells if c in plays),
                      thin=thin, treated=treated, blocks=blocks, detail=detail)


def fit_openings(corpus: pd.DataFrame, played: pd.DataFrame,
                 ledger: dict[str, set[str]], *,
                 grid: Sequence[float] = (*E_GRID, E_STAR),
                 evidence: dict[str, dict[str, float]] | None = None,
                 frame: pd.DataFrame | None = None) -> list[str]:
    """§2.3's 78: the block openings whose block holds a thin fixture at ANY
    grid `e*` — the `e* < 12` union, of which the primary's 62 are a subset.

    One fit serves every grid point and both controls, because the posterior is
    arm-invariant (§0.2): a `w`-style per-arm refit does not exist here.
    """
    evidence = evidence_table(corpus, played) if evidence is None else evidence
    frame = (_fixture_frame(corpus, played, ledger, evidence)
             if frame is None else frame)
    opens = block_openings(corpus)
    ceiling = max(float(g) for g in grid)
    hit = frame.loc[frame["e_min"] < ceiling, "block"]
    return sorted({opens[str(b)] for b in hit})


def canonical_membership(m: Membership) -> str:
    """The serialisation §6 step 2 hashes. Sorted, explicit, no dict order."""
    return json.dumps({
        "e_star": float(m.e_star),
        "new_cells": [list(c) for c in m.new_cells],
        "new_cells_playing": [list(c) for c in m.new_cells_playing],
        "thin": list(m.thin), "treated": list(m.treated),
        "blocks": list(m.blocks),
    }, sort_keys=True, separators=(",", ":"))


def membership_digests(corpus: pd.DataFrame, played: pd.DataFrame,
                       ledger: dict[str, set[str]], *,
                       table: Sequence[dict[str, Any]] | None = None,
                       ) -> dict[str, Any]:
    """§6 step 2's frozen membership digests, recomputed by the harness's own
    code from the pinned artifacts.

    "Each serialised canonically and hashed" — the 85 thin fixture keys, the 52
    treated keys, the 51 newly-flagged club-cutoff cells, the 78 fit openings and
    the 16 treated / 19 untouched table cells. THE COUNTS ARE CHECKED HERE:
    §2.2 and §2.3 pre-state them, so a recomputation that produces different
    ones is :class:`MembershipMismatch` and not a smaller experiment.
    """
    evidence = evidence_table(corpus, played)
    frame = _fixture_frame(corpus, played, ledger, evidence)
    primary = membership(corpus, played, ledger, e_star=E_STAR,
                         evidence=evidence, frame=frame)
    openings = fit_openings(corpus, played, ledger, evidence=evidence,
                            frame=frame)

    problems: list[str] = []
    if len(primary.thin) != EXPECTED_THIN:
        problems.append(f"{len(primary.thin)} thin fixtures, not {EXPECTED_THIN}")
    if len(primary.treated) != EXPECTED_TREATED:
        problems.append(f"{len(primary.treated)} treated, not {EXPECTED_TREATED}")
    if len(primary.new_cells) != EXPECTED_NEW_CELLS:
        problems.append(f"{len(primary.new_cells)} newly-flagged cells, not "
                        f"{EXPECTED_NEW_CELLS}")
    if len(primary.new_cells_playing) != EXPECTED_NEW_CELLS_PLAYING:
        problems.append(f"{len(primary.new_cells_playing)} of them in blocks "
                        f"where the club plays, not {EXPECTED_NEW_CELLS_PLAYING}")
    if len(primary.blocks) != EXPECTED_PRIMARY_BLOCKS:
        problems.append(f"{len(primary.blocks)} primary blocks, not "
                        f"{EXPECTED_PRIMARY_BLOCKS}")
    if len(openings) != EXPECTED_FIT_OPENINGS:
        problems.append(f"{len(openings)} fit openings, not "
                        f"{EXPECTED_FIT_OPENINGS}")
    n_cells = sum(len(v) for v in evidence.values())
    if n_cells != EXPECTED_CELLS:
        problems.append(f"{n_cells} club-cutoff cells, not {EXPECTED_CELLS}")
    n_incumbent = int(frame["incumbent"].sum())
    if n_incumbent != EXPECTED_INCUMBENT_FIXTURES:
        problems.append(f"{n_incumbent} fixtures carry incumbent widening, not "
                        f"{EXPECTED_INCUMBENT_FIXTURES}")
    by_season = {str(s): int(n) for s, n in
                 frame.loc[frame["e_min"] < E_STAR].groupby("season").size().items()}
    if by_season != EXPECTED_THIN_BY_SEASON:
        problems.append(f"thin fixtures by season {by_season}, not "
                        f"{EXPECTED_THIN_BY_SEASON}")
    n_control = int(frame["cutoff"].isin(openings).sum())
    if n_control != EXPECTED_CONTROL_FIXTURES:
        problems.append(f"{n_control} fixtures in the fitted blocks, not "
                        f"{EXPECTED_CONTROL_FIXTURES}")
    if problems:
        raise MembershipMismatch(
            "; ".join(problems) + ". §2.2 and §2.3 pre-state the membership and "
            "§7 makes dropping a fixture after the run starts an invalidation: a "
            "different enumeration is a different experiment, not a smaller one.")

    out: dict[str, Any] = {
        "schema": SCHEMA_ID, "e_star": E_STAR,
        "corpus_sha256": CORPUS_SHA256, "archive_sha256": ARCHIVE_SHA256,
        "ledger_sha256": WALK_LEDGER_SHA256, "config_sha256": CONFIG_SHA256,
        "counts": {
            "thin": len(primary.thin), "treated": len(primary.treated),
            "new_cells": len(primary.new_cells),
            "new_cells_playing": len(primary.new_cells_playing),
            "fit_openings": len(openings),
            "control_fixtures": n_control,
            "primary_blocks": len(primary.blocks),
            "cells": n_cells, "incumbent_fixtures": n_incumbent,
        },
        "thin_by_season": by_season,
        "digests": {
            "thin": _digest_list(primary.thin),
            "treated": _digest_list(primary.treated),
            "new_cells": _digest_list(["|".join(c) for c in primary.new_cells]),
            "fit_openings": _digest_list(openings),
            "membership": hashlib.sha256(
                canonical_membership(primary).encode("utf-8")).hexdigest(),
        },
        "grid": {},
        "keys": {"thin": list(primary.thin), "treated": list(primary.treated),
                 "new_cells": ["|".join(c) for c in primary.new_cells],
                 "fit_openings": list(openings)},
    }
    for star in sorted({*E_GRID, E_STAR}):
        m = membership(corpus, played, ledger, e_star=star, evidence=evidence,
                       frame=frame)
        out["grid"][f"{star:g}"] = {
            "thin": len(m.thin), "treated": len(m.treated),
            "already_widened": len(m.already_widened),
            "blocks": len(m.blocks),
            "digest": _digest_list(m.thin),
        }
    if table is not None:
        treated_cells = [c for c in table if c["treated_clubs"]]
        untouched = [c for c in table if not c["treated_clubs"]]
        if len(table) != EXPECTED_TABLE_CELLS or \
                len(treated_cells) != EXPECTED_TABLE_TREATED or \
                len(untouched) != EXPECTED_TABLE_UNTOUCHED:
            raise MembershipMismatch(
                f"{len(table)} table cells, {len(treated_cells)} treated and "
                f"{len(untouched)} untouched — §3.3 pre-states "
                f"{EXPECTED_TABLE_CELLS}, {EXPECTED_TABLE_TREATED} and "
                f"{EXPECTED_TABLE_UNTOUCHED}")
        out["counts"]["table_cells"] = len(table)
        out["counts"]["table_treated"] = len(treated_cells)
        out["counts"]["table_untouched"] = len(untouched)
        out["digests"]["table_treated"] = _digest_list(
            [f"{c['season']}|{c['cutoff_label']}" for c in treated_cells])
        out["digests"]["table_untouched"] = _digest_list(
            [f"{c['season']}|{c['cutoff_label']}" for c in untouched])
        out["keys"]["table_treated"] = [
            f"{c['season']}|{c['cutoff_label']}" for c in treated_cells]
        out["keys"]["table_untouched"] = [
            f"{c['season']}|{c['cutoff_label']}" for c in untouched]
    return out


def _digest_list(items: Iterable[str]) -> str:
    payload = json.dumps(sorted(str(i) for i in items), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ==========================================================================
# 5. THE FIT SCHEDULE — §2.3's 78 openings, sharded
# ==========================================================================

@dataclass(frozen=True)
class FitPoint:
    """One fit: the block opening, and every fixture of that block.

    ``match_ids`` is the WHOLE block, not the thin subset, because §3.2's
    identity control is defined over all 820 fixtures of the 78 affected
    blocks — "a strictly stronger control than the predecessors' 20-date samples
    because this experiment must refit these very cutoffs anyway".
    """

    season: str
    block: str
    cutoff: str                       # ISO date; the cutoff is midnight on it
    match_ids: tuple[str, ...]

    def key(self, config_sha: str) -> str:
        return fit_key(self.cutoff, config_sha=config_sha)


def fit_key(cutoff: str, seed: int = SEED, config_sha: str | None = None) -> str:
    """§5.2's resume key: ``cutoff|seed|config_sha256``."""
    return f"{cutoff}|{int(seed)}|{config_sha or config_sha256()}"


def fit_points(corpus: pd.DataFrame, openings: Sequence[str] | None = None,
               *, played: pd.DataFrame | None = None,
               ledger: dict[str, set[str]] | None = None,
               check: bool = True) -> list[FitPoint]:
    """The 78 fit points, each carrying its block's whole fixture list."""
    if openings is None:
        if played is None or ledger is None:
            raise EvWidenError(
                "fit_points needs either an explicit opening list or the "
                "archive and ledger to derive one")
        openings = fit_openings(corpus, played, ledger)
    wanted = {str(o) for o in openings}
    opens = block_openings(corpus)
    frame = corpus.copy()
    frame["block"] = frame["block"].astype(str)
    frame["cutoff"] = frame["block"].map(opens)

    points: list[FitPoint] = []
    for cutoff, part in frame.loc[frame["cutoff"].isin(wanted)].groupby("cutoff"):
        blocks = sorted(set(part["block"]))
        if len(blocks) != 1:
            raise CorpusShapeMismatch(
                f"cutoff {cutoff} opens blocks {blocks}: a block opening that "
                "belongs to two blocks is not a fit point")
        seasons = sorted(set(part["season"].astype(str)))
        if len(seasons) != 1:
            raise CorpusShapeMismatch(f"cutoff {cutoff} spans seasons {seasons}")
        points.append(FitPoint(
            season=seasons[0], block=blocks[0], cutoff=str(cutoff),
            match_ids=tuple(sorted(str(m) for m in part["match_id"]))))
    points.sort(key=lambda p: p.cutoff)

    missing = sorted(wanted - {p.cutoff for p in points})
    if missing:
        raise CorpusShapeMismatch(
            f"{len(missing)} requested opening(s) are not block openings of "
            f"this corpus (first: {missing[:3]})")
    if check:
        n_fixtures = sum(len(p.match_ids) for p in points)
        if len(points) != EXPECTED_FIT_OPENINGS or \
                n_fixtures != EXPECTED_CONTROL_FIXTURES:
            raise MembershipMismatch(
                f"{len(points)} fit points over {n_fixtures} fixtures; §2.3 "
                f"pre-states {EXPECTED_FIT_OPENINGS} openings and §3.2 "
                f"{EXPECTED_CONTROL_FIXTURES} control fixtures")
    return points


def shard_name(index: int, count: int) -> str:
    return f"shard_{int(index):02d}_of_{int(count):02d}.jsonl"


def shard_points(points: Sequence[FitPoint], index: int,
                 count: int) -> list[FitPoint]:
    """A partition of the fit points by cutoff — union everything, overlap nothing.

    Strided rather than blocked so every shard carries the same mix of early and
    late cutoffs: a blocked split would put the cheapest fits (smallest training
    frames) in one shard and the most expensive in another. §2.4 runs the shards
    SEQUENTIALLY — the featpanel `.tmp` rename race in the locked path crashes
    parallel ones — so the partition buys resumability and per-shard poison
    rather than wall-clock.
    """
    count, index = int(count), int(index)
    if count < 1:
        raise EvWidenError(f"a shard count of {count} is not a partition")
    if not 0 <= index < count:
        raise EvWidenError(
            f"shard {index} of {count} does not exist: shards are 0-based and "
            f"the last one is {count - 1}")
    return sorted(points, key=lambda p: p.cutoff)[index::count]


# ==========================================================================
# 6. THE LEDGER — canonical form, digests, conflicts, poison, resume
# ==========================================================================

def _strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in _VOLATILE}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def canonical(rows: Sequence[dict[str, Any]]) -> str:
    """§5.2's canonical form: sorted, volatile fields removed, `sort_keys=True`.

    The demand that a resumed run reproduce an uninterrupted one byte for byte
    is made HERE and not on the raw file, because a row records its own wall
    clock and its own shard and two runs will never agree on those. Everything
    that can change a number is inside this string; everything that cannot is
    outside it, and which is which was fixed in the preregistration before any
    row existed.
    """
    clean = [_strip_volatile(r) for r in rows]
    clean.sort(key=lambda r: (str(r.get("cutoff", "")),
                              str(r.get("match_id", "")), str(r.get("key", ""))))
    return json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str)


def run_digest(rows: Sequence[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical(rows).encode("utf-8")).hexdigest()


def _row_identity(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("key", "")), str(row.get("match_id", "")))


def read_jsonl(path: Path | str) -> tuple[list[dict], list[dict], int]:
    """Parse a shard ledger into (rows, poison, dropped-truncated-lines).

    A crash between the write and the fsync leaves half a JSON object on the
    last line. That fit is incomplete, so the fragment is dropped and the fit is
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
            raise EvWidenError(
                f"{paths.rel(path)} line {i + 1} is not JSON, and it is not the "
                "last line: only an interrupted append can truncate a ledger, so "
                "this file is corrupted rather than partial")
        (poison if obj.get("poison") else rows).append(obj)
    return rows, poison, dropped


def poison_rows(path: Path | str) -> list[dict]:
    return read_jsonl(path)[1]


def repair_tail(path: Path | str) -> int:
    """Drop a torn final line, and say so. Returns the bytes discarded.

    The next append would glue itself onto an unterminated fragment and turn ONE
    unreadable line into two, which is how a resumable log quietly becomes a
    corrupted one. This is the only place this module rewrites a ledger, and it
    removes only bytes that provably cannot be parsed as a row.
    """
    path = Path(path)
    if not path.exists():
        return 0
    raw = path.read_bytes()
    if not raw or raw.endswith(b"\n"):
        read_jsonl(path)                      # refuses a mid-file malformation
        return 0
    head, _, tail = raw.rpartition(b"\n")
    try:
        json.loads(tail.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        tmp = path.with_suffix(path.suffix + ".repair")
        tmp.write_bytes(head + b"\n" if head else b"")
        tmp.replace(path)
        return len(tail)
    path.write_bytes(raw + b"\n")             # intact, merely unterminated
    return 0


def load_ledger(path: Path | str, *, allow_poison: bool = False,
                complete_only: bool = True) -> list[dict[str, Any]]:
    """Every fixture row in a shard, de-duplicated, schema-checked, ordered.

    Three refusals the preregistration named, in one place: a duplicated key
    that DISAGREES is :class:`RowConflict`; a row missing a §5.2 field is
    :class:`SchemaMismatch`; a poison row is :class:`ShardFailed` unless the
    caller is the one collecting poison.

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
                    "what a row records; a field nobody wrote is a field nobody "
                    "can check afterwards.")
        for field in REQUIRED_FIT_FIELDS:
            if field not in (row.get("fit") or {}):
                raise SchemaMismatch(
                    f"{paths.rel(path)}: the fit provenance of "
                    f"{row.get('match_id')!r} at cutoff {row.get('cutoff')!r} "
                    f"lacks {field!r}. §5.2 fixes what a row records at BOTH "
                    "levels; the fit block is where the archive digest, the two "
                    "provisional sets and the identity control's residual live, "
                    "and a run nobody can re-identify is a run nobody can check.")
        ident = _row_identity(row)
        if ident in keep:
            a = json.dumps(_strip_volatile(keep[ident]), sort_keys=True,
                           default=str)
            b = json.dumps(_strip_volatile(row), sort_keys=True, default=str)
            if a != b:
                raise RowConflict(
                    f"{paths.rel(path)} holds two rows for {ident} that disagree "
                    "on a scored field. Two fits of the same cutoff under the "
                    "same seed and the same config are the same fit; if they "
                    "are not, something moved that this experiment holds fixed.")
            continue
        keep[ident] = row

    out = list(keep.values())
    if complete_only:
        by_key: dict[str, list[dict]] = {}
        for row in out:
            by_key.setdefault(str(row["key"]), []).append(row)
        out = [r for group in by_key.values() for r in group
               if len(group) == int(group[0]["fit"]["n_fixtures"])]
    out.sort(key=lambda r: (str(r["cutoff"]), str(r["match_id"])))
    return out


def completed_keys(path: Path | str) -> set[str]:
    """The fit keys a shard has FINISHED — partial fits excluded."""
    return {str(r["key"]) for r in
            load_ledger(path, allow_poison=True, complete_only=True)}


# ==========================================================================
# 7. THE LEAKAGE GUARD
# ==========================================================================

def visible_training_frame(cutoff: str | pd.Timestamp,
                           played: pd.DataFrame) -> pd.DataFrame:
    """What a fit at ``cutoff`` may see, by the walk-forward's own rule.

    ``wcmodel.data.features.build`` keeps ``date < cutoff.normalize()``. This
    reproduces that rule on the played frame so the property can be asserted
    against a FRAME instead of quoted from a source file.
    """
    ts = pd.Timestamp(cutoff).normalize()
    return played.loc[pd.to_datetime(played["date"]) < ts]


def assert_cutoff_clean(cutoff: str | pd.Timestamp, played: pd.DataFrame,
                        match_ids: Iterable[str]) -> dict[str, Any]:
    """Refuse a fit that can see the fixtures it is about to price (§5.1).

    Unlike the freshness sweep, this experiment's two arms share a training set
    exactly, so a leak has no direction: it would move BOTH arms and mostly
    cancel in the pairing. That is a reason to check anyway and not a reason to
    relax — the identity control compares Arm A's fit against a corpus produced
    by a DIFFERENT process, so a leak here would surface as a control mismatch
    with a confusing explanation attached.
    """
    ts = pd.Timestamp(cutoff).normalize()
    ids = tuple(str(m) for m in match_ids)
    train = visible_training_frame(ts, played)
    if train.empty:
        raise CutoffLeak(f"no training matches before {ts.date()}")

    leaked = sorted(set(ids) & set(train["match_id"].astype(str)))
    if leaked:
        raise CutoffLeak(
            f"{len(leaked)} fixture(s) priced at cutoff {ts.date()} are inside "
            f"the training frame of the fit that prices them: {leaked[:5]}")

    latest = pd.to_datetime(train["date"]).max()
    if not latest < ts:
        raise CutoffLeak(f"latest training date {latest.date()} is not strictly "
                         f"before cutoff {ts.date()}")
    return {"cutoff": str(ts.date()), "n_training_matches": int(len(train)),
            "latest_training_date": str(latest.date()), "n_priced": len(ids)}


# ==========================================================================
# 8. THE FIT — one posterior, three predicate settings, the same code path
# ==========================================================================

@contextmanager
def provisional_as(post, teams: Iterable[str]):
    """Read the posterior under a different provisional set, then put it back.

    THIS IS THE TREATMENT, and it is deliberately the smallest possible one.
    ``draw_api.production_grid`` computes ``provisional = fixture_ctx.home in
    posterior.provisional_teams or fixture_ctx.away in
    posterior.provisional_teams`` and hands the answer to ``finalize_grid``,
    which applies the ONE incumbent mix. So re-keying the predicate is exactly
    "put a different set on the posterior and ask again" — no patched import, no
    second mix, no per-fixture strength, nothing in ``src/``.

    The restore is in a ``finally`` because a posterior left with the wrong set
    on it would silently contaminate every later pass over the same fit.
    """
    before = post.provisional_teams
    post.provisional_teams = set(str(t) for t in teams)
    try:
        yield post
    finally:
        post.provisional_teams = before


def predict_rows(post, pairs: Sequence[tuple[str, str]]) -> np.ndarray:
    """``post.predict_1x2`` for each (home, away), in OUTCOMES order, at 8 dp.

    The rounding is ``round(v, 8)`` — the corpus's own, from
    ``epl/walkforward.py::_one_cutoff`` — applied here so that "equal to the
    corpus at its eight decimals" is a comparison of two numbers written the
    same way rather than a comparison with a tolerance.
    """
    out = np.empty((len(pairs), 3), dtype=float)
    for i, (home, away) in enumerate(pairs):
        if home not in post._idx or away not in post._idx:
            raise UnpriceableFixture(
                f"{home} v {away}: a club is absent from the posterior index. "
                "§2.3 fixes the population and forbids dropping a fixture, so "
                "this is a defect, never a dropped row.")
        p = post.predict_1x2(home, away, neutral=False)
        out[i] = [round(float(p[k]), ROUND_DP) for k in score_mod.OUTCOMES]
    return out


class Engine:
    """The walk-forward's own machinery, built once and reused per fit.

    Everything is read from `epl.freeze`, `epl.fit`, `epl.anchor` and
    `epl.dcfit` rather than rebuilt: the same frozen config, the same `Anchor`
    over the same played frame, the same `build_store`, the same
    `config_read_once` fast panel (proven inert at panel and forecast level by
    `walkforward.verify_fast_path_is_inert`), and the same `fit_epl` with
    `feature_cache_dir=paths.FIT_CACHE_DIR`. §2.3 names that call sequence and
    this class is it.

    Byte-parity with the walk's own results is not something this class tries to
    achieve; it is what calling the same functions with the same inputs gets for
    free, and §3.2's identity control is the check that it did.
    """

    def __init__(self, corpus: pd.DataFrame, played: pd.DataFrame | None = None,
                 *, ledger: dict[str, set[str]] | None = None,
                 verbose: bool = True):
        from epl import anchor as anchor_mod, freeze
        from epl import fit as epl_fit

        self._epl_fit = epl_fit
        self.cfg = freeze.frozen_wcmodel_config()
        self.config_sha256 = assert_config_frozen(cfg=self.cfg)
        self.realised_config_sha256 = realised_config_sha256(self.cfg)

        self.played = load_archive() if played is None else played
        self.ledger = load_walk_ledger() if ledger is None else ledger
        self.anchor = anchor_mod.Anchor(self.played, freeze.frozen_elo_config())
        self.store = epl_fit.build_store(self.played)
        self.archive_rows = int(len(self.played))
        self.archive_sha256 = archive_digest(self.played)
        self.ledger_sha256 = (sha256_file(WALK_LEDGER_PATH)
                              if WALK_LEDGER_PATH.exists() else "absent")
        self.harness_sha256 = sha256_file(paths.REPO_ROOT / HARNESS_FILES[0])
        self.corpus = corpus
        self.evidence = evidence_table(corpus, self.played)
        self.verbose = bool(verbose)
        self._ctx = None

    def __enter__(self) -> "Engine":
        self._ctx = self._epl_fit.config_read_once(self.cfg)
        self._ctx.__enter__()
        return self

    def __exit__(self, *exc) -> bool:
        ctx, self._ctx = self._ctx, None
        return bool(ctx.__exit__(*exc)) if ctx is not None else False

    # -- the enlarged set -------------------------------------------------
    def enlarged(self, point: FitPoint, incumbent: Iterable[str],
                 e_star: float = E_STAR) -> set[str]:
        """§2.1: ``provisional_incumbent(C) u { t : e(t, C) < e* }``.

        ADD, not REPLACE (§2.1's ruling, with the measurement behind it): the
        union keeps every club the volatility and few-games arms flag. The
        evidence rule adds; it removes nothing.
        """
        thin = {club for club, value in self.evidence[point.block].items()
                if value < float(e_star)}
        return set(str(t) for t in incumbent) | thin

    # -- one fit ----------------------------------------------------------
    def fit(self, point: FitPoint, *, grid_treated: Sequence[str] = (),
            e_star: float = E_STAR) -> dict[str, Any]:
        """Fit once at ``point.cutoff``; predict the block under three predicates.

        The order is the preregistration's and it is not an implementation
        detail: §3.2 rules that the identity control runs FIRST and that "not
        one treated prediction is produced until it passes". The control is
        therefore evaluated inside this function, before the union pass runs,
        and a mismatch raises before Arm A exists at all.
        """
        from epl import dcfit
        from epl import walkforward as wf
        import warnings

        t0 = time.perf_counter()
        cutoff = pd.Timestamp(point.cutoff).normalize()
        assert_cutoff_clean(cutoff, self.played, point.match_ids)
        pit = self._epl_fit.assert_point_in_time(self.store, cutoff)
        if str(pit["latest_training_date"]) >= point.cutoff:
            raise CutoffLeak(
                f"the STORE's latest training date at {point.cutoff} is "
                f"{pit['latest_training_date']}")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            post, info = dcfit.fit_epl(cutoff, self.store, self.anchor, self.cfg,
                                       matches=self.played,
                                       feature_cache_dir=paths.FIT_CACHE_DIR)
            warns = sorted({f"{w.category.__name__}: {w.message}" for w in caught})

        health = wf._health(post, self.cfg)
        bad = [k for k in ("all_finite", "sigma_positive", "home_adv_sane")
               if not health.get(k, True)]
        if bad:
            raise FitFailed(f"{point.cutoff}: the posterior fails {bad} — {health}")

        by_id = self.corpus.set_index(self.corpus["match_id"].astype(str))
        pairs = [(str(by_id.loc[m, "home_key"]), str(by_id.loc[m, "away_key"]))
                 for m in point.match_ids]

        incumbent = set(str(t) for t in info.provisional_teams)
        recorded = self.ledger.get(point.cutoff)
        if recorded is not None and incumbent != recorded:
            raise PredicateMismatch(
                f"{point.cutoff}: this fit's provisional set "
                f"{sorted(incumbent)} differs from the walk-forward ledger's "
                f"{sorted(recorded)}. §3.2 makes this the control that the "
                "incumbent arm being re-keyed IS the incumbent arm that "
                "published; a difference here means the two are not the same "
                "arm and nothing paired against the corpus is meaningful.")

        # ---- pass 1: the identity control, and it runs FIRST -------------
        with provisional_as(post, incumbent):
            probs_incumbent = predict_rows(post, pairs)
        stored = np.array([[float(by_id.loc[m, c]) for c in _PROB_COLUMNS]
                           for m in point.match_ids], dtype=float)
        diff = np.abs(probs_incumbent - stored)
        worst = float(diff.max()) if diff.size else 0.0
        mean_diff = float(diff.mean()) if diff.size else 0.0
        if not np.array_equal(probs_incumbent, stored):
            offenders = [point.match_ids[i] for i in
                         sorted(set(np.flatnonzero(diff.max(axis=1) > 0)))]
            raise ControlMismatch(
                f"{point.cutoff}: {len(offenders)} of {len(pairs)} identity-"
                f"control probabilities differ from the corpus (max |Δp| = "
                f"{worst:.3g}), first at {offenders[:5]}. §3.2 rules EXACT "
                "equality at the corpus's eight decimals and §7 makes widening "
                "the tolerance after a mismatch an invalidation. This is most "
                "likely archive drift since the walk, and it invalidates the "
                "pairing the whole design rests on: STOP, and write the "
                "amendment before anything continues.")

        # ---- pass 2: the §2.1 union at the primary e* --------------------
        enlarged = self.enlarged(point, incumbent, e_star)
        with provisional_as(post, enlarged):
            probs_arm = predict_rows(post, pairs)

        treated_here = {m for m, (h, a) in zip(point.match_ids, pairs)
                        if (h in enlarged or a in enlarged)
                        and not (h in incumbent or a in incumbent)}
        for i, mid in enumerate(point.match_ids):
            if mid in treated_here:
                continue
            # R-B1: against ARM B — the same posterior's incumbent pass — and
            # not against the corpus, which is now the external control.
            if not np.array_equal(probs_arm[i], probs_incumbent[i]):
                raise UntreatedMoved(
                    f"{point.cutoff}: {mid} is outside the treated set and its "
                    f"Arm-A probabilities {probs_arm[i].tolist()} differ from "
                    f"Arm B's {probs_incumbent[i].tolist()}. The treatment must "
                    "touch exactly the fixtures the rule names — a fixture that "
                    "moves without being named means the predicate is not "
                    "per-fixture, and every untreated delta this run reports "
                    "would be noise dressed as zero.")

        # ---- the identity canary, on every block the union does not touch --
        # §5.3: "An `e*` low enough to add nobody must yield `np.array_equal`
        # with the corpus rows." On 16 of the 78 blocks the §2.1 union adds
        # nobody, and pass 2 IS that canary — checked here rather than bought
        # with a second fit at `e* = 0`.
        added = sorted(enlarged - incumbent)
        identity = None
        if not added:
            identity = bool(np.array_equal(probs_arm, probs_incumbent)
                            and np.array_equal(probs_arm, stored))
            if not identity:
                raise CanaryFailed(
                    f"{point.cutoff}: the §2.1 union adds no club, so Arm A must "
                    "be byte-identical to the corpus, and it is not (max |Δp| = "
                    f"{float(np.abs(probs_arm - stored).max()):.3g}). Zero "
                    "widening that is not zero is a treatment doing something "
                    "the rule does not describe.")

        # ---- the direction canary, on EVERY fixture of the block ----------
        # R-M2: the comparator is the production path, the documented edge
        # branch is a correct result rather than a failure, the branch every
        # fixture took is recorded, and at least one TREATED fixture must have
        # taken the interior branch — a canary in which every fixture no-ops
        # proved nothing. Run on every fixture of every fit, so the mechanism's
        # own guarantee is evidence on 820 real grids rather than on one.
        direction = direction_canary(post, pairs, treated=added) if pairs else None

        # ---- pass 3: the widened value, for the grid ---------------------
        wanted = [m for m in point.match_ids if str(m) in set(grid_treated)]
        probs_widened: dict[str, list[float]] = {}
        if wanted:
            all_clubs = set(str(t) for t in post.teams)
            idx = {m: i for i, m in enumerate(point.match_ids)}
            with provisional_as(post, all_clubs):
                widened = predict_rows(post, [pairs[idx[m]] for m in wanted])
            for mid, row in zip(wanted, widened):
                probs_widened[str(mid)] = [float(v) for v in row]
                # A treated fixture's union-pass value and its all-clubs value
                # must be the SAME number: `finalize_grid` keys on a boolean and
                # cannot see WHICH club carried it. §5.1 gives this no name, so
                # it refuses as the base class rather than under an invented one.
                if mid in treated_here and \
                        not np.array_equal(probs_arm[idx[mid]], row):
                    raise EvWidenError(
                        f"{point.cutoff}: {mid} is widened under both the §2.1 "
                        f"union and the all-clubs predicate but the two "
                        f"probabilities differ ({probs_arm[idx[mid]].tolist()} "
                        f"vs {row.tolist()}). Widening is a per-fixture boolean "
                        "and the mix does not read which club carried it; if it "
                        "did, the grid secondaries assembled from this pass "
                        "would not be the arms they claim to be.")

        return {
            "cutoff": point.cutoff, "season": point.season, "block": point.block,
            "match_ids": list(point.match_ids), "pairs": pairs,
            "probs_incumbent": probs_incumbent, "probs_arm": probs_arm,
            "probs_widened": probs_widened,
            "provisional_incumbent": sorted(incumbent),
            "provisional_enlarged": sorted(enlarged),
            "provisional_ledger": sorted(recorded or ()),
            "treated": sorted(treated_here),
            "cold_start_teams": list(info.cold_start_teams),
            "evidence": {c: round(float(v), ROUND_DP)
                         for c, v in sorted(self.evidence[point.block].items())},
            "n_training_matches": int(info.n_training_matches),
            "n_teams": int(info.n_teams), "anchor_spec": str(info.anchor_spec),
            "latest_training_date": str(pit["latest_training_date"]),
            "warnings": warns, "unpriceable": [], "health": health,
            "control_max_abs_diff": worst,
            "control_mean_abs_diff": mean_diff,
            "identity_canary": identity,
            #: R-M2 requires the branch every fixture took to be recorded, so
            #: `branches` stays on the row; only the full per-fixture entropies
            #: are dropped, and they are recomputable from the grids.
            "direction_canary": (None if direction is None else
                                 {k: v for k, v in direction.items()
                                  if k != "detail"}),
            "wall_seconds": round(time.perf_counter() - t0, 3),
            "fit_seconds": float(info.seconds),
        }


# ==========================================================================
# 9. THE RUNNER — one JSONL row per fixture, resumable, poison-on-failure
# ==========================================================================

def thin_at(e_min: float, grid: Sequence[float] = (*E_GRID, E_STAR)
            ) -> list[str]:
    """The grid points this fixture is thin at, as the keys the ledger uses."""
    return [f"{g:g}" for g in sorted(float(g) for g in grid) if e_min < float(g)]


def _guard_ledger_location(path: Path, harness_frozen: bool) -> None:
    """The preregistered run directory is closed until §6's freeze commit.

    §6 step 3: "Only then does the first real fit run." §5.3 permits — and this
    experiment genuinely needs — pre-freeze audit runs, but on SYNTHETIC corpora
    and in their own directory, where every row is stamped
    ``harness_frozen: false`` and the merge refuses it by name.

    Not only the shard ledger. A pre-freeze ``canary.json`` left in the run
    directory is exactly what a later ``--run`` reads as *the canary passed*: the
    record does not carry the harness bytes it was produced under, so the
    directory has to.
    """
    if harness_frozen:
        return
    for root in (EVWIDEN_DIR, TABLE_DIR):
        try:
            inside = path.resolve().is_relative_to(root.resolve())
        except (OSError, ValueError):
            inside = False
        if inside:
            raise EvWidenError(
                f"refusing to write {paths.rel(path)} before §6's harness-hash "
                "freeze commit exists. §7: 'A real-archive fit runs before the "
                "§6 freeze commit' invalidates the preregistration. Audit runs "
                "are legitimate and §5.3 requires them — give them their own "
                f"directory outside {paths.rel(root)} with --dir, where every "
                "row is stamped harness_frozen: false and the merge will not "
                "score them.")


def _fit_provenance(point: FitPoint, out: dict, *, config_sha: str,
                    realised_sha: str, harness_sha: str, archive_rows: int,
                    archive_sha: str, ledger_sha: str) -> dict[str, Any]:
    return {
        "cutoff": point.cutoff, "seed": SEED, "config_sha256": config_sha,
        "realised_config_sha256": realised_sha,
        "n_training_matches": int(out.get("n_training_matches", -1)),
        "latest_training_date": out.get("latest_training_date"),
        "n_teams": int(out.get("n_teams", -1)),
        "n_fixtures": len(point.match_ids),
        "match_ids": list(point.match_ids),
        "cold_start_teams": list(out.get("cold_start_teams", [])),
        "provisional_incumbent": list(out.get("provisional_incumbent", [])),
        "provisional_enlarged": list(out.get("provisional_enlarged", [])),
        "provisional_ledger": list(out.get("provisional_ledger", [])),
        "evidence": dict(out.get("evidence", {})),
        "anchor_spec": str(out.get("anchor_spec", "")),
        "warnings": list(out.get("warnings", [])),
        "unpriceable": list(out.get("unpriceable", [])),
        "health": dict(out.get("health", {})),
        "control_max_abs_diff": float(out.get("control_max_abs_diff", 0.0)),
        "control_mean_abs_diff": float(out.get("control_mean_abs_diff", 0.0)),
        "identity_canary": out.get("identity_canary"),
        "direction_canary": out.get("direction_canary"),
        "harness_sha256": harness_sha,
        "archive_rows": int(archive_rows), "archive_sha256": archive_sha,
        "ledger_sha256": ledger_sha,
        "blas_threads": blas_threads(),
        "wall_seconds": out.get("wall_seconds"),
        "fit_seconds": out.get("fit_seconds"),
    }


def _fixture_row(point: FitPoint, index: int, out: dict, corpus_row: pd.Series,
                 fit: dict, *, key: str, config_sha: str, shard_id: str,
                 harness_frozen: bool, e_star: float,
                 grid: Sequence[float]) -> dict[str, Any]:
    """One paired fixture: BOTH arms from the same posterior (R-B1).

    Arm B is predict pass 1 — the block's fixtures under the fit's own
    recomputed incumbent provisional set — and Arm A is predict pass 2 under the
    §2.1 union. Nothing about either is read from the corpus. The corpus's
    stored row survives as the EXTERNAL identity control, recorded beside them
    with its own delta so a reader can confirm the equality rather than take it.
    """
    match_id = str(point.match_ids[index])
    home, away = out["pairs"][index]
    evidence = out["evidence"]
    e_home, e_away = float(evidence[home]), float(evidence[away])
    e_min = min(e_home, e_away)

    native = [float(corpus_row[c]) for c in _PROB_COLUMNS]
    arm_b = [float(v) for v in out["probs_incumbent"][index]]
    arm = [float(v) for v in out["probs_arm"][index]]
    y = int(corpus_row["y"])
    rps_native = float(corpus_row["dc_rps"])
    rps_native_recomputed = float(
        score_mod.rps(np.array([native]), np.array([y]))[0])
    if abs(rps_native_recomputed - rps_native) > 1e-12:
        raise ScoreMismatch(
            f"{match_id}: stored dc_rps {rps_native!r} and the RPS of the "
            f"stored probabilities {rps_native_recomputed!r} differ by "
            f"{abs(rps_native_recomputed - rps_native):.3g}")
    rps_b = float(score_mod.rps(np.array([arm_b]), np.array([y]))[0])
    rps_arm = float(score_mod.rps(np.array([arm]), np.array([y]))[0])
    max_abs_dp_vs_corpus = max((abs(a - b) for a, b in zip(arm_b, native)),
                               default=0.0)

    incumbent = set(out["provisional_incumbent"])
    return {
        "schema": SCHEMA_ID, "key": key, "match_id": match_id,
        "season": point.season, "block": point.block,
        "cutoff": point.cutoff,
        "date": str(pd.Timestamp(corpus_row["date"]).date()),
        "home_key": home, "away_key": away, "y": y,
        "e_home": round(e_home, ROUND_DP), "e_away": round(e_away, ROUND_DP),
        "e_min": round(e_min, ROUND_DP), "e_star": float(e_star),
        "thin_at": thin_at(e_min, grid),
        "thin": bool(e_min < float(e_star)),
        "treated": bool(match_id in set(out["treated"])),
        "incumbent_widened": bool(home in incumbent or away in incumbent),
        "probs_native": native,
        "probs_incumbent": arm_b,
        "probs_arm": arm,
        "probs_widened": out["probs_widened"].get(match_id),
        "rps_native": rps_native,
        "rps_native_recomputed": rps_native_recomputed,
        "rps_B": rps_b,
        "rps_arm": rps_arm,
        #: R-B1's estimand delta: Arm A minus Arm B, both from ONE posterior.
        "delta": rps_arm - rps_b,
        #: The same fixture against the corpus's stored row — the external
        #: control's delta, published beside the estimand's so a reader can
        #: confirm the eight-decimal equality rather than take it.
        "delta_vs_corpus": rps_arm - rps_native,
        "max_abs_dp_vs_corpus": float(max_abs_dp_vs_corpus),
        "seed": SEED, "config_sha256": config_sha,
        "arm_a": {
            "arm": ARM_NAME,
            "source": "epl.evwiden: epl.dcfit.fit_epl, then the §2.1 union on "
                      "post.provisional_teams (predict pass 2)",
            "rule": f"provisional' = incumbent u {{ t : e(t, C) < {e_star:g} }}",
            "alpha": WIDENING_ALPHA, "mechanism": "c",
            "cutoff": point.cutoff, "seed": SEED,
            "config_sha256": config_sha,
            "realised_config_sha256": fit["realised_config_sha256"],
            "harness_sha256": fit["harness_sha256"],
            "archive_rows": fit["archive_rows"],
            "archive_sha256": fit["archive_sha256"],
            "ledger_sha256": fit["ledger_sha256"],
            "predict": "post.predict_1x2(home, away, neutral=False)",
            "rounding": f"round(v, {ROUND_DP})",
        },
        "arm_b": {
            "arm": BASELINE_ARM,
            "source": "epl.evwiden: the SAME posterior under the fit's own "
                      "recomputed incumbent provisional set (predict pass 1)",
            "rule": "provisional = provisional_incumbent(C)",
            "alpha": WIDENING_ALPHA, "mechanism": "c",
            "cutoff": point.cutoff, "seed": SEED,
            "config_sha256": config_sha,
            "realised_config_sha256": fit["realised_config_sha256"],
            "harness_sha256": fit["harness_sha256"],
            "predict": "post.predict_1x2(home, away, neutral=False)",
            "rounding": f"round(v, {ROUND_DP})",
            #: R-B1: Arm B IS recomputed now, and that is the repair. The
            #: superseded arm was an old rounded 1X2 projection the control
            #: could only bind AFTER projection, while mechanism (c) acts on the
            #: full scoreline grid before it.
            "recomputed": True,
        },
        "corpus_control": {
            "role": "the external identity control (§3.2 as R-B1 demotes it) — "
                    "the corpus enters no estimand",
            "source": paths.rel(CORPUS_PATH), "corpus_sha256": CORPUS_SHA256,
            "columns": list(_PROB_COLUMNS) + ["dc_rps"],
            "probs": native, "rps": rps_native,
            "max_abs_dp_vs_arm_b": float(max_abs_dp_vs_corpus),
        },
        "fit": fit, "harness_frozen": bool(harness_frozen),
        "shard_id": shard_id, "seconds": fit.get("wall_seconds"),
        "wall_seconds": fit.get("wall_seconds"),
        "started_at": pd.Timestamp.now("UTC").isoformat(),
        "host": socket.gethostname(),
    }


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
             fitter: Callable[..., dict] | None = None,
             engine: "Engine | None" = None,
             grid_treated: Sequence[str] = (),
             e_star: float = E_STAR, grid: Sequence[float] = (*E_GRID, E_STAR),
             shard_id: str = "0/1", resume: bool = True, verbose: bool = True,
             harness_frozen: bool = True) -> dict[str, Any]:
    """Fit every point and append one JSONL row per fixture of its block.

    Resumable per fit, keyed ``cutoff|seed|config_sha256`` (§5.2): a key already
    complete in the ledger is skipped — not re-run, not re-scored, not appended
    twice. A fit's rows are written in ONE append so a crash leaves either all of
    them or a truncated tail that :func:`load_ledger` drops and this function
    re-runs.

    ``harness_frozen`` is the caller's assertion about §6, not a guess this
    function makes: the CLI computes it from :func:`harness_freeze_status` and
    passes it, every row records it, and the merge refuses a row that says False.
    Writing to the preregistered ledger location before the freeze is refused
    outright, because §7 makes such a run not this experiment.
    """
    ledger_path = Path(ledger_path)
    _guard_ledger_location(ledger_path, harness_frozen)

    if fitter is None:
        engine = engine or Engine(corpus, verbose=verbose)
        fitter = engine.fit
    if engine is not None:
        config_sha = engine.config_sha256
        realised_sha = engine.realised_config_sha256
        harness_sha = engine.harness_sha256
        archive_rows, archive_sha = engine.archive_rows, engine.archive_sha256
        ledger_sha = engine.ledger_sha256
    else:
        # An injected fitter still keys on the REAL config digest: the resume key
        # is a fact about the configuration, not about who computed the forecast.
        config_sha = config_sha256()
        realised_sha, harness_sha = "injected-fitter", "stub-harness"
        archive_rows, archive_sha, ledger_sha = -1, "stub-archive", "stub-ledger"

    torn = repair_tail(ledger_path)
    if torn and verbose:
        print(f"[evwiden] dropped {torn} torn byte(s) from the tail of "
              f"{paths.rel(ledger_path)}: that fit is incomplete and re-runs",
              flush=True)

    stale = poison_rows(ledger_path)
    if stale:
        first = stale[0]
        raise ShardFailed(
            f"{paths.rel(ledger_path)} still carries {len(stale)} poison row(s) "
            f"— the first is {first.get('error_type')} at {first.get('cutoff')}: "
            f"{first.get('error')}. Fail closed: re-running over poison would "
            "leave the poison in place, the merge would refuse anyway, and the "
            "fits would have been paid for twice. Inspect the failure, then "
            "remove this shard's ledger and re-run the shard.")

    done = completed_keys(ledger_path) if resume else set()
    by_id = corpus.set_index(corpus["match_id"].astype(str))
    todo = [p for p in points
            if fit_key(p.cutoff, config_sha=config_sha) not in done]
    if verbose:
        print(f"[evwiden] shard {shard_id}: {len(points)} fit points, "
              f"{len(points) - len(todo)} already complete, {len(todo)} to run",
              flush=True)

    started = time.time()
    n_rows = 0
    for i, point in enumerate(todo, 1):
        key = fit_key(point.cutoff, config_sha=config_sha)
        try:
            out = fitter(point, grid_treated=grid_treated, e_star=e_star)
            _check_fit(point, out)
        except EvWidenError as exc:
            _poison(ledger_path, point, key, exc, shard_id)
            raise
        except Exception as exc:                     # noqa: BLE001 — typed below
            wrapped = FitFailed(f"{point.cutoff}: {type(exc).__name__}: {exc}")
            _poison(ledger_path, point, key, wrapped, shard_id)
            raise wrapped from exc

        fit = _fit_provenance(point, out, config_sha=config_sha,
                              realised_sha=realised_sha, harness_sha=harness_sha,
                              archive_rows=archive_rows, archive_sha=archive_sha,
                              ledger_sha=ledger_sha)
        lines = [json.dumps(
            _fixture_row(point, j, out, by_id.loc[str(mid)], fit, key=key,
                         config_sha=config_sha, shard_id=shard_id,
                         harness_frozen=harness_frozen, e_star=e_star,
                         grid=grid), default=str)
            for j, mid in enumerate(point.match_ids)]
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
        n_rows += len(lines)
        if verbose:
            el = time.time() - started
            print(f"[evwiden] {i}/{len(todo)} {point.cutoff} "
                  f"n_train={fit['n_training_matches']} "
                  f"fixtures={len(point.match_ids)} "
                  f"treated={len(out['treated'])} "
                  f"{out.get('wall_seconds', 0)}s (elapsed {el / 60:.1f}m, eta "
                  f"{el / i * (len(todo) - i) / 60:.1f}m)", flush=True)

    rows = load_ledger(ledger_path)
    return {"shard_id": shard_id, "n_fits": len(todo), "n_rows_written": n_rows,
            "repaired_bytes": int(torn), "n_fixtures": len(rows),
            "n_skipped": len(points) - len(todo),
            "seconds": round(time.time() - started, 1),
            "ledger": str(ledger_path), "run_digest": run_digest(rows),
            "harness_frozen": bool(harness_frozen)}


def _check_fit(point: FitPoint, out: dict) -> None:
    """Everything that makes a fit's output unusable, refused by its own name."""
    if out.get("unpriceable"):
        raise UnpriceableFixture(f"{point.cutoff}: {out['unpriceable']}")
    for name in ("probs_incumbent", "probs_arm"):
        probs = np.asarray(out[name], dtype=float)
        if probs.shape != (len(point.match_ids), 3):
            raise FitFailed(f"{point.cutoff}: {name} has shape {probs.shape} for "
                            f"{len(point.match_ids)} fixtures")
        if not np.isfinite(probs).all() or \
                not np.allclose(probs.sum(axis=1), 1.0, atol=1e-7):
            raise FitFailed(
                f"{point.cutoff}: a {name} forecast is non-finite or does not "
                "sum to 1 (worst |sum-1| = "
                f"{float(np.max(np.abs(probs.sum(axis=1) - 1.0))):.3g})")


# ==========================================================================
# 10. THE CANARIES — §5.3. A canary that cannot fail is not a canary.
# ==========================================================================

#: The prefix a corrupted archive row's clubs are reassigned to. No archive
#: carries these names, so a leak shows up as evidence attributed to clubs that
#: do not exist rather than as a small numerical drift somebody might excuse.
#:
#: The names are made unique PER ROW, and that is not cosmetic:
#: ``wcmodel.data.features.valid_played_results`` collapses rows that are
#: content-identical — same normalised date, same unordered team pair, same
#: team-to-goals map — as its duplicate-match dedup. A corruption that gave
#: every row the SAME two clubs and the same score therefore deleted a thousand
#: rows on the way into the store instead of rewriting them, and the canary
#: crashed rather than measuring anything.
_CANARY_PREFIX = "__canary_corrupt__"


def corrupt_archive(played: pd.DataFrame, cutoff: str | pd.Timestamp, *,
                    side: str) -> pd.DataFrame:
    """Rewrite the archive on one side of ``cutoff``, clubs and scores alike.

    ``side='after'`` rewrites every row dated ON OR AFTER the cutoff — the rows
    a point-in-time quantity must not be able to see. ``side='before'`` rewrites
    the rows before it, which is the positive control: those rows are exactly
    what ``e`` is a sum over, so a canary that leaves them alone proves nothing.

    Both the CLUBS and the SCORES are rewritten. Scores alone would be a weak
    corruption for this quantity — ``e`` never reads a score — so a canary built
    on scores would pass on a broken filter. Reassigning the clubs is what makes
    the negative leg able to fail.
    """
    if side not in ("before", "after"):
        raise EvWidenError(f"side must be 'before' or 'after', not {side!r}")
    ts = pd.Timestamp(cutoff).normalize()
    out = played.copy()
    dates = pd.to_datetime(out["date"]).dt.normalize()
    mask = (dates >= ts) if side == "after" else (dates < ts)
    if not bool(mask.any()):
        raise EvWidenError(
            f"the canary has nothing to corrupt {side} {ts.date()}: a canary "
            "run over an empty mask passes by accident, which is the one thing "
            "a canary may never do")
    n = int(mask.sum())
    tag = np.arange(n)
    out.loc[mask, "home_key"] = [f"{_CANARY_PREFIX}h{i}" for i in tag]
    out.loc[mask, "away_key"] = [f"{_CANARY_PREFIX}a{i}" for i in tag]
    for column in ("fthg", "ftag"):
        if column in out.columns:
            out.loc[mask, column] = 9
    return out


def evidence_canary(played: pd.DataFrame, cutoff: str | pd.Timestamp,
                    clubs: Sequence[str], *,
                    provisional_fn: Callable[[pd.DataFrame], set[str]] | None = None,
                    e_star: float = E_STAR) -> dict[str, Any]:
    """§5.3's two-legged canary, because the existing one cannot see this input.

    ``epl.walkforward.point_in_time_canary`` rewrites RESULTS and compares
    forecasts. That is the right check for a fit and the wrong one for this
    experiment: the quantity under test is a sum over archive ROWS, and a canary
    that never touches the row set cannot see whether the predicate's input
    leaks.

    * **Negative leg** — corrupt every archive row dated on or after the cutoff
      and demand every ``e(t, C)`` and BOTH provisional sets bit-identical.
    * **Positive control** — corrupt the rows BEFORE the cutoff and demand ``e``
      moves by more than 1e-9.

    ``provisional_fn`` maps a played frame to the incumbent provisional set; the
    run passes the real one (a store plus ``count_volatility_arm``) and a test
    passes a stub. When it is ``None`` only the evidence legs run, and the record
    says so rather than implying a check that did not happen.
    """
    ts = pd.Timestamp(cutoff).normalize()
    clubs = [str(c) for c in clubs]
    base = effective_evidence(ts, played, clubs)

    after = corrupt_archive(played, ts, side="after")
    after_e = effective_evidence(ts, after, clubs)
    negative = max((abs(after_e[c] - base[c]) for c in clubs), default=0.0)

    before = corrupt_archive(played, ts, side="before")
    before_e = effective_evidence(ts, before, clubs)
    positive = max((abs(before_e[c] - base[c]) for c in clubs), default=0.0)

    sets_equal: bool | None = None
    set_detail: dict[str, Any] = {}
    if provisional_fn is not None:
        base_inc = {str(t) for t in provisional_fn(played)}
        after_inc = {str(t) for t in provisional_fn(after)}
        base_enl = base_inc | {c for c in clubs if base[c] < float(e_star)}
        after_enl = after_inc | {c for c in clubs if after_e[c] < float(e_star)}
        sets_equal = bool(base_inc == after_inc and base_enl == after_enl)
        set_detail = {
            "incumbent_before": sorted(base_inc),
            "incumbent_after": sorted(after_inc),
            "enlarged_before": sorted(base_enl),
            "enlarged_after": sorted(after_enl)}

    out = {
        "schema": SCHEMA_ID, "cutoff": str(ts.date()), "n_clubs": len(clubs),
        "e_star": float(e_star),
        "negative_leg_max_abs_diff": float(negative),
        "positive_control_max_abs_diff": float(positive),
        "provisional_sets_identical": sets_equal,
        "provisional_checked": provisional_fn is not None,
        "detail": set_detail,
        "PASS": bool(negative == 0.0 and positive > 1e-9
                     and (sets_equal is not False)),
    }
    if not out["PASS"]:
        raise EvidenceCanaryFailed(
            "the evidence canary did not pass: the negative leg moved `e` by "
            f"{negative:.3g} (must be exactly 0), the positive control moved it "
            f"by {positive:.3g} (must exceed 1e-9), provisional sets identical "
            f"= {sets_equal!r}. §5.3: a canary that cannot fail is not a canary, "
            "and one that fails is a leak in the predicate's own input.")
    return out


def identity_canary(fitter: Callable[..., dict], point: FitPoint,
                    corpus: pd.DataFrame, *, e_star: float = 0.0
                    ) -> dict[str, Any]:
    """§5.3: an ``e*`` low enough to add nobody must reproduce the corpus rows.

    Zero widening is byte-identical, and the demand is ``np.array_equal`` rather
    than a tolerance. It is the cheapest possible statement of the experiment's
    central claim — that the treatment is a pure re-key and adds nothing on its
    own — and the one that would break loudest if the "treatment" were quietly
    doing something else as well.
    """
    out = fitter(point, grid_treated=(), e_star=float(e_star))
    added = sorted(set(out["provisional_enlarged"])
                   - set(out["provisional_incumbent"]))
    by_id = corpus.set_index(corpus["match_id"].astype(str))
    stored = np.array([[float(by_id.loc[str(m), c]) for c in _PROB_COLUMNS]
                       for m in point.match_ids], dtype=float)
    arm = np.asarray(out["probs_arm"], dtype=float)
    equal = bool(np.array_equal(arm, stored))
    worst = float(np.abs(arm - stored).max()) if arm.size else 0.0
    record = {"schema": SCHEMA_ID, "cutoff": point.cutoff,
              "e_star": float(e_star), "clubs_added": added,
              "n_fixtures": len(point.match_ids),
              "max_abs_diff": worst, "PASS": bool(equal and not added)}
    if not record["PASS"]:
        raise CanaryFailed(
            f"the identity canary did not pass at {point.cutoff}: e* = "
            f"{e_star:g} added {added} and the arm differs from the corpus by "
            f"{worst:.3g}. Zero widening must be byte-identical; if it is not, "
            "the treatment is doing something the rule does not describe.")
    return record


def grid_entropy(grid: np.ndarray) -> float:
    """Shannon entropy of a normalised scoreline pmf, in nats."""
    g = np.asarray(grid, dtype=float).ravel()
    nz = g[g > 0.0]
    return float(-(nz * np.log(nz)).sum())


def pre_widening_grid(post, home: str, away: str, *,
                      neutral: bool = False) -> np.ndarray:
    """The production map's scoreline grid BEFORE ``finalize_grid`` runs on it.

    R-M2 binds the direction canary to the production path, and the production
    path's own last leg is ``finalize_grid(grid, posterior, provisional=…)`` —
    so the canary needs the ``grid`` that leg is handed. It is read out of
    ``wcmodel.model.draw_api``'s own functions (``per_draw_rates`` then
    ``mean_grid_over_draws``, the two legs ``production_grid`` calls before
    finalization) and never re-implemented here: a canary built on a second
    implementation of the map checks the second implementation.
    """
    from wcmodel.model import draw_api

    ctx = draw_api.FixtureCtx(home=home, away=away, neutral=bool(neutral),
                              covariates=None, host_factor=None)
    lh, la = draw_api.per_draw_rates(post, ctx)
    if str(getattr(post, "likelihood", "dixon_coles")) == "dixon_coles":
        return draw_api.mean_grid_over_draws(
            lh, la, likelihood="dixon_coles", rho=post._post("rho"),
            max_goals=draw_api.PRODUCTION_MAX_GOALS)
    return draw_api.mean_grid_over_draws(
        lh, la, likelihood="bivariate_poisson",
        l3=np.exp(post._post("log_lambda3")),
        max_goals=draw_api.PRODUCTION_MAX_GOALS)


def direction_canary(post, pairs: Sequence[tuple[str, str]], *,
                     treated: Sequence[str] = (),
                     strength: float = WIDENING_ALPHA) -> dict[str, Any]:
    """§5.3's direction canary, as R-M2 repairs it on both halves.

    The superseded canary compared the widened grid with a bare
    ``inflate_predictive`` call and demanded strictly higher entropy
    UNCONDITIONALLY. Both halves were wrong. ``finalize_grid``
    (``src/wcmodel/model/draw_api.py:218-231``) applies ``inflate_predictive``
    and then an **unconditional** renormalisation, so the bare call is a
    comparison against something the production map does not emit; and
    ``inflate_predictive`` documents an EDGE NO-OP — a marginal mean at ~0 or at
    the largest representable score has no interior max-entropy solution and the
    grid is returned unchanged (``widening.py:225-233``), so "strictly higher
    entropy" is not unconditional.

    THE REPAIRED COMPARATOR, three demands, every fixture:

    1. the posterior's own widened output equals ``finalize_grid(grid,
       posterior, provisional=True)`` at **bit equality** (``np.array_equal``);
    2. that production output equals the frozen mix — ``inflate_predictive(grid,
       is_provisional=True, strength=0.5)`` renormalised the way
       ``finalize_grid`` renormalises it — which is what keeps §2.1's "EXACTLY
       the one incumbent mix at the frozen alpha" checkable after the comparator
       moved onto the production path;
    3. entropy strictly higher than ``finalize_grid(grid, posterior,
       provisional=False)`` **except** where the documented edge branch fires,
       in which case an unchanged grid and an equal entropy are the correct
       result.

    THE BRANCH IS RECORDED FOR EVERY FIXTURE, and at least one fixture must have
    taken the INTERIOR branch with a strictly higher entropy and a strictly
    positive ``max |Δp|``; when the block carries treated fixtures, at least one
    of THEM must have. A direction canary in which every fixture took the edge
    branch is :class:`CanaryFailed`: it proved nothing.
    """
    from wcmodel.model.draw_api import finalize_grid
    from wcmodel.model.widening import inflate_predictive

    treated = {str(t) for t in treated}
    detail: list[dict[str, Any]] = []
    worst_production, worst_frozen = 0.0, 0.0
    for home, away in pairs:
        grid = np.asarray(pre_widening_grid(post, home, away), dtype=float)
        base = finalize_grid(grid.copy(), post, provisional=False)
        expected = finalize_grid(grid.copy(), post, provisional=True)
        with provisional_as(post, (home,)):
            wide = np.asarray(post.predict_scoreline(home, away, neutral=False),
                              dtype=float)

        raw = inflate_predictive(grid.copy(), is_provisional=True,
                                 strength=float(strength))
        edge = bool(np.array_equal(raw, grid))
        frozen = raw / raw.sum()

        d_production = float(np.abs(wide - expected).max())
        d_frozen = float(np.abs(expected - frozen).max())
        worst_production = max(worst_production, d_production)
        worst_frozen = max(worst_frozen, d_frozen)
        gain = grid_entropy(wide) - grid_entropy(base)
        moved = float(np.abs(wide - base).max())
        interior = not edge
        ok = (bool(np.array_equal(wide, expected))
              and bool(np.array_equal(expected, frozen))
              and (gain > 0.0 and moved > 0.0 if interior
                   else bool(np.array_equal(wide, base)) and gain == 0.0))
        detail.append({
            "home": home, "away": away,
            "treated": bool(str(home) in treated or str(away) in treated),
            "branch": "edge" if edge else "interior",
            "max_abs_diff_vs_production": d_production,
            "max_abs_diff_vs_frozen_alpha": d_frozen,
            "entropy_base": grid_entropy(base),
            "entropy_widened": grid_entropy(wide),
            "entropy_gain": gain, "max_abs_dp": moved, "ok": bool(ok)})

    interior_rows = [d for d in detail if d["branch"] == "interior" and d["ok"]]
    treated_interior = [d for d in interior_rows if d["treated"]]
    has_interior = bool(interior_rows)
    has_treated_interior = bool(treated_interior) or not (
        treated and any(d["treated"] for d in detail))

    gains = [d["entropy_gain"] for d in detail if d["branch"] == "interior"]
    record = {
        "schema": SCHEMA_ID, "n_fixtures": len(pairs),
        "alpha": float(strength),
        "comparator": "wcmodel.model.draw_api.finalize_grid(grid, posterior, "
                      "provisional=…) — the production path",
        "n_interior": sum(1 for d in detail if d["branch"] == "interior"),
        "n_edge": sum(1 for d in detail if d["branch"] == "edge"),
        "n_treated_interior": len(treated_interior),
        "max_abs_grid_diff": worst_production,
        "max_abs_diff_vs_frozen_alpha": worst_frozen,
        "min_entropy_gain_interior": (min(gains) if gains else None),
        "branches": [{k: d[k] for k in ("home", "away", "treated", "branch",
                                        "entropy_gain", "max_abs_dp", "ok")}
                     for d in detail],
        "detail": detail,
        "PASS": bool(pairs and all(d["ok"] for d in detail)
                     and has_interior and has_treated_interior),
    }
    if not record["PASS"]:
        broken = [f"{d['home']} v {d['away']} ({d['branch']})"
                  for d in detail if not d["ok"]]
        raise CanaryFailed(
            "the direction canary did not pass. max |Δgrid| against the "
            f"production path = {worst_production:.3g} and against the frozen "
            f"alpha = {worst_frozen:.3g} (both must be exactly 0); the smallest "
            f"interior entropy gain was {record['min_entropy_gain_interior']!r} "
            f"(must be strictly positive); {len(broken)} fixture(s) failed "
            f"{broken[:3]}; interior branch reached = {has_interior}, treated "
            f"fixture in the interior branch = {has_treated_interior}. §2.1 "
            "rules that a treated fixture receives EXACTLY the one incumbent "
            "mix at the frozen alpha, and R-M2 rules that a canary in which "
            "every fixture took the documented edge branch proved nothing.")
    return record


def run_canary(runner: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """§5.3's results canary: `epl.walkforward.point_in_time_canary`.

    A precondition of the run, on the real archive, AFTER the freeze — never a
    result. ``PASS: false`` stops the run.
    """
    if runner is None:
        from epl import walkforward as wf
        runner = wf.point_in_time_canary
    started = time.perf_counter()
    out = dict(runner())
    out.setdefault("schema", SCHEMA_ID)
    out["blas_threads"] = blas_threads()
    out["seconds"] = round(time.perf_counter() - started, 1)
    if not out.get("PASS"):
        raise CanaryFailed(
            f"the point-in-time canary did not pass: max |Δp| before the cutoff "
            f"= {out.get('max_abs_diff_before_cutoff')!r} (must be 0), positive "
            f"control = {out.get('max_abs_diff_positive_control')!r} (must "
            "move). §5.3: the run does not start.")
    return out


def write_canaries(record: dict[str, Any], path: Path | str | None = None,
                   ) -> Path:
    """Every canary's full dict, on the record whichever way it fell."""
    path = Path(path) if path is not None else CANARY_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return path


def require_run_preconditions(directory: Path | str | None = None, *,
                              path: Path | str | None = None,
                              require_results: bool | None = None,
                              ) -> dict[str, Any]:
    """:data:`RUN_ORDER`, enforced rather than declared.

    The canaries are read from their WRITTEN record, so the order holds across
    processes and across shards — four workers each re-running them would be
    four answers to a question with one.

    ``require_results`` decides whether §5.3's RESULTS canary
    (``walkforward.point_in_time_canary``) must be on that record. It costs real
    fits, so ``--no-results-canary`` exists for the synthetic audit — and that
    flag must not be able to follow the run past the freeze. Left at ``None`` it
    is derived from :func:`harness_freeze_status`: once §6's commit has landed,
    the preregistered run demands the canary §5.3 pre-states as "run once as a
    precondition on the real archive AFTER the freeze".
    """
    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    path = Path(path) if path is not None else directory / CANARY_NAME
    if not path.exists():
        raise CanaryFailed(
            f"no canary record at {paths.rel(path)}. §5.3 makes the canaries a "
            "precondition of the run, and an absent canary is not a passing "
            "one: run `--canary` first.")
    try:
        rec = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise CanaryFailed(f"{paths.rel(path)} is not readable JSON: {exc}") from exc
    failed = [name for name, leg in rec.items()
              if isinstance(leg, dict) and leg.get("PASS") is False]
    if failed or not rec.get("PASS"):
        raise CanaryFailed(
            f"the canary record at {paths.rel(path)} did not pass "
            f"({failed or 'no PASS field'}). §5.3: the run does not start.")

    if require_results is None:
        require_results = bool(harness_freeze_status()["frozen"])
    if require_results and not rec.get("results_canary_run"):
        raise CanaryFailed(
            f"the canary record at {paths.rel(path)} was written with "
            "--no-results-canary, so `epl.walkforward.point_in_time_canary` "
            "never ran. §5.3 makes it a precondition of the run on the REAL "
            "archive after the freeze; skipping it is a concession to the "
            "synthetic audit's clock and may not follow the run past §6's "
            "commit. Re-run `--canary` without the flag.")
    return rec


# ==========================================================================
# 11. THE ESTIMAND — §2.3, and §3.1's secondaries which decide nothing
# ==========================================================================

#: (z_{0.975} + z_{0.80}) — the two-sided 5% / 80% power multiplier, used only
#: to REPORT the realised MDE beside the result. §2.3: "No power claim is made
#: in advance… no threshold in §4 moves in response."
_MDE_Z = 2.8015952

#: §3.1's two strata of the 85, by club category of the thin side.
STRATA_CATEGORIES = ("returning_thin", "cold_start_tail")


def _summarise(deltas: np.ndarray, blocks: Sequence[Any], *, n_boot: int,
               seed: int) -> dict[str, Any]:
    n = int(deltas.size)
    if n == 0:
        return {"n": 0, "mean": 0.0, "sd": None, "se_iid": None,
                "ci95": [0.0, 0.0], "n_blocks": 0, "degenerate": True}
    sd = float(deltas.std(ddof=1)) if n > 1 else None
    if float(np.abs(deltas).max()) == 0.0:
        # §3.1 pre-states this row: at e* in {1, 3} every thin fixture is
        # already widened, every delta is exactly 0.0, and the interval is
        # degenerate BY CONSTRUCTION. Saying so here is what stops an
        # identically zero row being presented as either a finding or a failure.
        return {"n": n, "mean": 0.0, "sd": 0.0, "se_iid": 0.0,
                "ci95": [0.0, 0.0], "n_blocks": len(set(map(str, blocks))),
                "degenerate": True}
    lo, hi, n_blocks = score_mod.block_bootstrap_ci(
        deltas, list(blocks), n_boot=n_boot, alpha=ALPHA, seed=seed)
    return {"n": n, "mean": float(deltas.mean()), "sd": sd,
            "se_iid": (sd / np.sqrt(n)) if sd is not None else None,
            "ci95": [lo, hi], "n_blocks": int(n_blocks), "degenerate": False}


def cold_start_club_seasons(rows: Sequence[dict[str, Any]]
                            ) -> set[tuple[str, str]]:
    """(season, club) pairs the MODEL ITSELF called cold-start at some fitted cutoff.

    §3.1 strata the 85 by "club category of the thin side — *returning-thin* vs
    *cold-start tail*". The category is read off ``epl.dcfit.cold_start_clubs``'s
    own verdict, recorded on every fit row, rather than from a list of club names
    typed into this file: a cold-start club has zero pre-cutoff archive rows, so
    its ``e`` at its season opener is 0, so its opening block is inside the 78 by
    construction and the fitted rows always see it.
    """
    out: set[tuple[str, str]] = set()
    for row in rows:
        season = str(row["season"])
        for club in (row.get("fit") or {}).get("cold_start_teams") or ():
            out.add((season, str(club)))
    return out


def thin_side(row: dict[str, Any]) -> str:
    """The club that makes a fixture thin: the smaller-`e` side, home on a tie."""
    return (str(row["home_key"]) if float(row["e_home"]) <= float(row["e_away"])
            else str(row["away_key"]))


def _category(row: dict[str, Any], cold: set[tuple[str, str]]) -> str:
    return ("cold_start_tail"
            if (str(row["season"]), thin_side(row)) in cold else "returning_thin")


def _grid_delta(row: dict[str, Any], e_star: float) -> float:
    """This fixture's Arm-A minus Arm-B delta at one grid point.

    Assembled from the SAME fits (§3.1: "each point's … from the same 78 fits").
    A fixture the incumbent predicate already widens takes Arm B's own row under
    every arm and contributes exactly 0.0; a treated one takes the widened
    probabilities pass 3 computed. Nothing here refits anything.

    R-B1: the baseline is ``rps_B`` — the same posterior's incumbent pass — and
    not the corpus's stored RPS. Every delta this experiment reports is a
    difference between two predictions of one posterior.
    """
    if bool(row["incumbent_widened"]):
        return 0.0
    widened = row.get("probs_widened")
    if widened is None:
        raise MergeIncomplete(
            f"{row['match_id']} is treated at e* = {e_star:g} but carries no "
            "widened probabilities. §3.1 computes every grid point from the "
            "same 78 fits; a missing pass-3 value means the grid-treated set "
            "the run was given did not cover the grid it is being scored on.")
    y = int(row["y"])
    rps_arm = float(score_mod.rps(np.array([[float(v) for v in widened]]),
                                  np.array([y]))[0])
    return rps_arm - float(row["rps_B"])


def estimand(rows: Sequence[dict[str, Any]], *, n_boot: int = N_BOOT,
             seed: int = BOOTSTRAP_SEED, e_star: float = E_STAR,
             grid: Sequence[float] = E_GRID,
             expected_thin: int | None = None,
             expected_treated: int | None = None,
             corpus_rows: int = CORPUS_ROWS,
             cold: set[tuple[str, str]] | None = None) -> dict[str, Any]:
    """§2.3's estimand, both intervals, and §3.1's reported-never-deciding rest.

    > THE ESTIMAND: the mean paired RPS delta, ``dc_evwiden`` minus
    > ``dc_native``, over the 85 thin fixtures of the pinned corpus at
    > ``e* = 10``. Negative means the re-keyed widening helps.

    ``rows`` is every fixture of the 78 fitted blocks — all 820 — and the
    population is selected HERE, by the rule, from the rows' own recorded ``e``.
    That is the walk-forward population selection §1.4 fixed: thin is a property
    of the fixture and its block cutoff, computed from data strictly before that
    cutoff, so nothing about which fixtures enter the estimand can depend on an
    outcome. Everything under ``secondaries`` is §3: published with the result
    and deciding nothing.
    """
    if not rows:
        raise MergeIncomplete("no rows to score")
    cold = cold_start_club_seasons(rows) if cold is None else cold

    thin = [r for r in rows if float(r["e_min"]) < float(e_star)]
    treated = [r for r in thin if not bool(r["incumbent_widened"])]
    if expected_thin is not None and len(thin) != int(expected_thin):
        raise MergeIncomplete(
            f"{len(thin)} thin fixtures, not the pre-stated {expected_thin}. "
            "§2.3 fixes the population at 85 and forbids dropping a fixture for "
            "any reason: a refusal is reported, a deletion is an amendment.")
    if expected_treated is not None and len(treated) != int(expected_treated):
        raise MergeIncomplete(
            f"{len(treated)} treated fixtures, not the pre-stated "
            f"{expected_treated}")

    deltas = np.array([float(r["delta"]) for r in thin], dtype=float)
    blocks = [str(r["block"]) for r in thin]
    seasons = [str(r["season"]) for r in thin]
    head = _summarise(deltas, blocks, n_boot=n_boot, seed=seed)
    season_ci = _summarise(deltas, seasons, n_boot=n_boot, seed=seed)

    # §2.3: every untreated fixture's delta is exactly 0.0 under ADD, so the
    # zeros are ARITHMETIC, not an unverified assumption — and the run has
    # already refused any that moved (UntreatedMoved).
    stray = sorted(str(r["match_id"]) for r in rows
                   if float(r["e_min"]) >= float(e_star)
                   and float(r["delta"]) != 0.0)
    if stray:
        raise UntreatedMoved(
            f"{len(stray)} fixture(s) outside the thin population carry a "
            f"non-zero delta (first: {stray[:5]}). Under ADD their delta is "
            "zero by construction, and the full-population secondary is stated "
            "as an arithmetic identity that would be false if this were true.")

    treated_deltas = np.array([float(r["delta"]) for r in treated], dtype=float)
    treated_summary = _summarise(treated_deltas, [str(r["block"]) for r in treated],
                                 n_boot=n_boot, seed=seed)

    grid_out = []
    for star in sorted({*(float(g) for g in grid), float(e_star)}):
        pop = [r for r in rows if float(r["e_min"]) < star]
        gd = np.array([_grid_delta(r, star) for r in pop], dtype=float)
        n_treated = sum(1 for r in pop if not bool(r["incumbent_widened"]))
        summary = _summarise(gd, [str(r["block"]) for r in pop],
                             n_boot=n_boot, seed=seed)
        if star == float(e_star) and pop:
            # The grid's own assembly at the primary must reproduce the arm the
            # run actually predicted. If pass 2 and pass 3 disagree the grid is
            # not "from the same 78 fits" and the secondaries are a second,
            # separately-computed experiment wearing this one's name.
            worst = float(np.abs(gd - np.array([float(r["delta"]) for r in pop])).max())
            if worst > 0.0:
                raise EvWidenError(
                    f"the grid's assembled delta at e* = {star:g} differs from "
                    f"the run's own by {worst:.3g}: the grid claims to be "
                    "computed from the same fits and is not.")
        grid_out.append({
            "e_star": star, "population": len(pop), "treated": n_treated,
            "already_widened": len(pop) - n_treated,
            "degenerate_by_construction": star in
            [float(g) for g in E_GRID_DEGENERATE],
            **summary})

    strata = {"season": [], "category": []}
    for season in sorted({str(r["season"]) for r in thin}):
        idx = [i for i, r in enumerate(thin) if str(r["season"]) == season]
        strata["season"].append({
            "stratum": season,
            **_summarise(deltas[idx], [blocks[i] for i in idx],
                         n_boot=n_boot, seed=seed)})
    labels = [_category(r, cold) for r in thin]
    for label in STRATA_CATEGORIES:
        idx = [i for i, l in enumerate(labels) if l == label]
        if not idx:
            continue
        strata["category"].append({
            "stratum": label,
            **_summarise(deltas[idx], [blocks[i] for i in idx],
                         n_boot=n_boot, seed=seed)})

    if treated:
        shifts = np.abs(
            np.array([r["probs_arm"] for r in treated], dtype=float)
            - np.array([r["probs_native"] for r in treated], dtype=float))
        movement = {"n_treated": len(treated),
                    "mean_abs_prob_shift": float(shifts.mean()),
                    "max_abs_prob_shift": float(shifts.max()),
                    "reseed_scale": dict(RESEED_SCALE)}
    else:
        movement = {"n_treated": 0, "mean_abs_prob_shift": 0.0,
                    "max_abs_prob_shift": 0.0, "reseed_scale": dict(RESEED_SCALE)}

    se = head.get("se_iid")
    power = {
        "sd_paired": head.get("sd"), "se_iid": se,
        "mde_80pct_two_sided_5pct": (float(_MDE_Z * se) if se else None),
        "multiplier": _MDE_Z,
        "note": "§2.3: no power claim was made in advance and no threshold in "
                "§4 moves in response to these numbers. The iid SE understates "
                "the block-correlated case; the bootstrap intervals are the "
                "reported uncertainty.",
    }

    return {
        "schema": SCHEMA_ID, "arm": ARM_NAME, "baseline": BASELINE_ARM,
        "e_star": float(e_star),
        "estimand": ("mean paired RPS delta, dc_evwiden minus dc_native, over "
                     "the thin fixtures of the pinned corpus at e* = "
                     f"{e_star:g}; negative means the re-keyed widening helps"),
        **{k: v for k, v in head.items() if k != "degenerate"},
        "ci95_season": season_ci["ci95"], "n_season_blocks": season_ci["n_blocks"],
        "bootstrap": {"n_boot": int(n_boot), "seed": int(seed), "alpha": ALPHA,
                      "primary_blocks": "season|ISO week",
                      "secondary_blocks": "season", "method": "percentile"},
        "secondaries": {
            "treated_subset": treated_summary,
            "full_population": {
                "n": int(corpus_rows),
                "mean": float(deltas.sum() / float(corpus_rows)),
                "identity": ("estimand x n_thin/n_corpus — untreated deltas are "
                             "exactly zero under ADD"),
                "decides": "nothing"},
            "grid": grid_out,
            "strata": strata,
            "movement": movement,
        },
        "power": power,
        "decides": "nothing — §4.5 makes adoption an owner ruling",
        "secondaries_decide": "nothing",
    }


# ==========================================================================
# 12. THE ADOPTION RULE — §4.1, all four, none sufficient
# ==========================================================================

def adoption(delta: float, ci95_block: Sequence[float],
             ci95_season: Sequence[float],
             table: dict[str, Any] | None = None) -> dict[str, Any]:
    """§4.1, evaluated and applied by nobody.

    > ADOPT the evidence-mass re-key (as a shadow arm, §4.5) if and only if ALL
    > FOUR: (i) the point estimate is ``Δ ≤ −0.0010`` over the 85 thin fixtures;
    > (ii) the 95% (season, ISO week) block bootstrap CI excludes zero — upper
    > bound strictly < 0; (iii) the 95% season block bootstrap CI also excludes
    > zero; (iv) the table gate holds.
    >
    > Otherwise ``dc_native`` stands unchanged, Hull's forecast included.

    ``table`` is :func:`table_gate`'s verdict. It is REQUIRED for an ADOPT:
    §4.1 makes all four necessary, so a match-level result with no table leg
    behind it cannot adopt, and this function says MISSING rather than
    quietly treating an absent gate as a passed one.
    """
    i = float(delta) <= ADOPT_DELTA
    ii = float(ci95_block[1]) < 0.0
    iii = float(ci95_season[1]) < 0.0
    iv = bool(table.get("PASS")) if table is not None else None
    conditions = {
        "i_point_estimate": {"value": float(delta), "bar": ADOPT_DELTA,
                             "PASS": bool(i)},
        "ii_block_ci_excludes_zero": {"ci95": [float(v) for v in ci95_block],
                                      "PASS": bool(ii)},
        "iii_season_ci_excludes_zero": {"ci95": [float(v) for v in ci95_season],
                                        "PASS": bool(iii)},
        "iv_table_gate": (dict(table) if table is not None
                          else {"PASS": None, "why": "the table leg has not run"}),
    }
    if iv is None:
        verdict = "INCOMPLETE — the table gate of §4.1 (iv) has not been measured"
    elif i and ii and iii and iv:
        verdict = "ADOPT"
    else:
        verdict = "DC_NATIVE STANDS"
    return {"verdict": verdict, "conditions": conditions,
            "rule": "all four required, none sufficient",
            "applied_by": "nobody — §4.5 makes adoption an owner ruling "
                          "recorded in reports/epl_sim_amendments.md"}


# ==========================================================================
# 13. THE MERGE — every shard, the pre-stated key set, then the estimand
# ==========================================================================

#: The fields a merged row must reproduce from the corpus EXACTLY. This is the
#: rejoin discipline: a row is paired to the frozen schedule by ``match_id`` and
#: then has to agree about what that fixture WAS. Without it a substitution —
#: the same two clubs on the same day, a different fixture, a different result —
#: would rejoin silently and be scored as if it were the preregistered one.
_REJOIN_FIELDS = ("season", "block", "home_key", "away_key", "y")


def rejoin(rows: Sequence[dict[str, Any]], corpus: pd.DataFrame,
           openings: dict[str, str] | None = None) -> dict[str, Any]:
    """Pair every ledger row back to the frozen schedule, and refuse the rest.

    Four refusals live here and each one is a way a paired comparison quietly
    stops being paired:

    * a row whose ``match_id`` is not in the corpus at all — :class:`MergeIncomplete`;
    * two rows for the same fixture — :class:`RowConflict`;
    * a row that disagrees with the corpus about the fixture's clubs, block,
      season, outcome, probabilities or RPS — :class:`MergeIncomplete`, because
      that is a SUBSTITUTION and not a disagreement about arithmetic;
    * a stored ``dc_rps`` that does not re-derive from the stored probabilities
      at 1e-12 — :class:`ScoreMismatch`, §2.3's own demand, recomputed here
      rather than trusted.
    """
    openings = block_openings(corpus) if openings is None else openings
    by_id = corpus.set_index(corpus["match_id"].astype(str))
    known = set(by_id.index)

    seen: dict[str, dict] = {}
    worst_rps = 0.0
    for row in rows:
        mid = str(row["match_id"])
        if mid not in known:
            raise MergeIncomplete(
                f"the ledger carries {mid!r}, which the pinned corpus does not. "
                "Every scored fixture rejoins the frozen schedule by match id; a "
                "row that cannot is not a fixture of this experiment.")
        if mid in seen:
            a = json.dumps(_strip_volatile(seen[mid]), sort_keys=True, default=str)
            b = json.dumps(_strip_volatile(row), sort_keys=True, default=str)
            if a != b:
                raise RowConflict(
                    f"two ledger rows for {mid} disagree on a scored field")
            continue
        seen[mid] = row

        stored = by_id.loc[mid]
        for field in _REJOIN_FIELDS:
            want, got = str(stored[field]), str(row[field])
            if want != got:
                raise MergeIncomplete(
                    f"{mid}: the ledger says {field} = {got!r} and the corpus "
                    f"says {want!r}. A row that rejoins the schedule by id but "
                    "describes a different fixture is a substitution, and "
                    "scoring it would pair Arm A against somebody else's Arm B.")
        if str(row["cutoff"]) != str(openings[str(stored["block"])]):
            raise MergeIncomplete(
                f"{mid}: the ledger's cutoff {row['cutoff']!r} is not block "
                f"{stored['block']!r}'s opening "
                f"{openings[str(stored['block'])]!r}")
        native = [float(v) for v in row["probs_native"]]
        want_native = [float(stored[c]) for c in _PROB_COLUMNS]
        if native != want_native:
            raise MergeIncomplete(
                f"{mid}: the ledger's recorded corpus row {native} is not the "
                f"corpus's {want_native}. R-B1 demotes the corpus to an "
                "EXTERNAL identity control; a row that copies different numbers "
                "under that name has nothing left to control against.")
        arm_b = [float(v) for v in row["probs_incumbent"]]
        if arm_b != want_native:
            raise ControlMismatch(
                f"{mid}: Arm B — the same posterior's incumbent pass — is "
                f"{arm_b} and the corpus's own row is {want_native}. §3.2 rules "
                "EXACT equality at the corpus's eight decimals over all 820 "
                "fixtures, and §7 makes widening that tolerance after a "
                "mismatch an invalidation.")
        recomputed = float(score_mod.rps(np.array([native]),
                                         np.array([int(row["y"])]))[0])
        worst_rps = max(worst_rps, abs(recomputed - float(row["rps_native"])),
                        abs(recomputed - float(stored["dc_rps"])))
        if worst_rps > 1e-12:
            raise ScoreMismatch(
                f"{mid}: Arm B's stored RPS does not re-derive from Arm B's own "
                f"stored probabilities (worst |ΔRPS| = {worst_rps:.3g}). §2.3 "
                "recomputes it at the merge and refuses past 1e-12.")
    return {"n": len(seen), "max_abs_rps_diff": worst_rps,
            "rows": [seen[m] for m in sorted(seen)]}


def merge(shards: int = 1, *, directory: Path | str | None = None,
          corpus: pd.DataFrame | None = None,
          played: pd.DataFrame | None = None,
          ledger: dict[str, set[str]] | None = None,
          table: dict[str, Any] | None = None,
          write: bool = True, expected: Sequence[str] | None = None,
          expected_thin: int | None = None, expected_treated: int | None = None,
          expected_fixtures: int | None = None,
          harness_frozen: bool | None = None, n_boot: int = N_BOOT,
          seed: int = BOOTSTRAP_SEED,
          freeze_sources: Sequence[Path] | None = None,
          require_canaries: bool = True) -> dict[str, Any]:
    """Every shard, no poison, the pre-stated key set — then §2.3's estimand.

    §5.1: a shard that exits non-zero or writes nothing is :class:`ShardFailed`,
    and a merged key set that is not EXACTLY the pre-stated one — not a superset,
    not a subset — is :class:`MergeIncomplete`. Partial results never silently
    merge and a partial ledger is never scored.

    This function authors no verdict prose. It writes machine-readable numbers;
    ``reports/epl_widening_result.md`` is written afterwards, by a person, and
    §4.4 requires it to be written whichever way the numbers fall.
    """
    freeze = (harness_freeze_status(freeze_sources) if harness_frozen is None
              else {"frozen": bool(harness_frozen), "why": "asserted by caller",
                    "files": {}, "where": None})
    if not freeze["frozen"]:
        if harness_frozen is None:
            require_harness_freeze(freeze_sources)
        raise EvWidenError(
            "refusing to merge: the §6 harness-hash freeze commit does not cover "
            "this harness, so these fits are not the run the preregistration "
            "describes (§7).")

    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    preregistered = expected is None
    corpus = load_corpus() if corpus is None else corpus
    check_corpus_scores(corpus)

    # The preconditions gate the NUMBER, not the wall clock: they are re-read
    # here, from the records beside these shards, however long ago they were
    # written. `require_results` comes from THIS merge's own freeze verdict
    # rather than from a fresh look at the repository, so a merge that has
    # already decided it is scoring the preregistered run demands the
    # preregistered run's canaries.
    pre = (require_run_preconditions(directory,
                                     require_results=bool(freeze["frozen"]))
           if require_canaries else
           {"skipped": "the caller asserted the canaries"})

    if preregistered:
        played = load_archive() if played is None else played
        ledger = load_walk_ledger() if ledger is None else ledger
        assert_ledger_covers(corpus, ledger)
        frozen = membership_digests(corpus, played, ledger)
        openings = list(frozen["keys"]["fit_openings"])
        expected_thin = EXPECTED_THIN if expected_thin is None else expected_thin
        expected_treated = (EXPECTED_TREATED if expected_treated is None
                            else expected_treated)
        expected_fixtures = (EXPECTED_CONTROL_FIXTURES
                             if expected_fixtures is None else expected_fixtures)
    else:
        frozen = None
        openings = [str(o) for o in expected]

    points = fit_points(corpus, openings, check=preregistered)
    config_sha = config_sha256()
    want_keys = {fit_key(p.cutoff, config_sha=config_sha) for p in points}

    rows: list[dict] = []
    names: list[str] = []
    for i in range(int(shards)):
        path = directory / shard_name(i, shards)
        names.append(path.name)
        if not path.exists():
            raise ShardFailed(
                f"{paths.rel(path)} is not on disk. Shards are waited on per PID "
                "and a failed shard poisons the merge; a missing ledger is a "
                "shard that never finished, and its fits are not optional.")
        part = load_ledger(path)          # raises ShardFailed on poison
        if not part:
            raise ShardFailed(f"{paths.rel(path)} holds no rows")
        mine = {fit_key(p.cutoff, config_sha=config_sha)
                for p in shard_points(points, i, shards)}
        stray = sorted({str(r["key"]) for r in part} - mine)
        if stray:
            raise MergeIncomplete(
                f"{paths.rel(path)} carries {len(stray)} key(s) outside its own "
                f"partition (first: {[k.split('|')[0] for k in stray[:3]]}): the "
                "shards are a partition and a row in two of them is a fixture "
                "counted twice")
        rows.extend(part)

    unfrozen = sorted({str(r["cutoff"]) for r in rows
                       if not r.get("harness_frozen")})
    if unfrozen:
        raise EvWidenError(
            f"{len(unfrozen)} fit(s) carry harness_frozen: false (first: "
            f"{unfrozen[:3]}). The freeze is a property of the ROW, not of the "
            "merge's clock: a fit run during the §5.3 audit is not a fit of the "
            "preregistered run, and re-stamping it would be exactly the "
            "back-dating §6 exists to prevent.")

    joined = rejoin(rows, corpus)
    rows = joined["rows"]

    got_keys = {str(r["key"]) for r in rows}
    if got_keys != want_keys:
        short = sorted(want_keys - got_keys)
        extra = sorted(got_keys - want_keys)
        raise MergeIncomplete(
            f"the merged key set is {len(got_keys)}, not the pre-stated "
            f"{len(want_keys)}: {len(short)} missing (first: "
            f"{[k.split('|')[0] for k in short[:3]]}), {len(extra)} unexpected "
            f"(first: {[k.split('|')[0] for k in extra[:3]]}). Not a superset, "
            "not a subset.")
    if expected_fixtures is not None and len(rows) != int(expected_fixtures):
        raise MergeIncomplete(
            f"{len(rows)} merged fixtures, not the pre-stated {expected_fixtures}")

    if frozen is not None:
        thin_keys = sorted(str(r["match_id"]) for r in rows
                           if float(r["e_min"]) < E_STAR)
        treated_keys = sorted(str(r["match_id"]) for r in rows
                              if float(r["e_min"]) < E_STAR
                              and not bool(r["incumbent_widened"]))
        if _digest_list(thin_keys) != frozen["digests"]["thin"] or \
                _digest_list(treated_keys) != frozen["digests"]["treated"]:
            raise MembershipMismatch(
                "the merged rows' thin/treated enumeration does not hash to the "
                "frozen membership digests: the population the run scored is not "
                "the population §2.2 froze.")

    result = estimand(rows, n_boot=n_boot, seed=seed,
                      expected_thin=expected_thin,
                      expected_treated=expected_treated)
    verdict = adoption(result["mean"], result["ci95"], result["ci95_season"],
                       table=(table or {}).get("gate") if table else None)
    result.update({
        "adoption": verdict,
        "n_fits": len(got_keys), "n_fixtures": len(rows),
        "shards": sorted(names), "run_digest": run_digest(rows),
        "corpus": {"path": paths.rel(CORPUS_PATH), "sha256": CORPUS_SHA256,
                   "rows": CORPUS_ROWS},
        "archive": {"path": paths.rel(ARCHIVE_PATH), "sha256": ARCHIVE_SHA256,
                    "rows": ARCHIVE_ROWS},
        "walk_ledger": {"path": paths.rel(WALK_LEDGER_PATH),
                        "sha256": WALK_LEDGER_SHA256, "rows": WALK_LEDGER_ROWS},
        "config": {"path": paths.rel(CONFIG_PATH), "sha256": config_sha,
                   "seed": SEED, "widening": dict(FROZEN_WIDENING)},
        "membership": frozen,
        "identity_control": {
            "n_fixtures": len(rows),
            "max_abs_diff": max((float(r["fit"]["control_max_abs_diff"])
                                 for r in rows), default=0.0),
            "mean_abs_diff": (float(np.mean([float(r["max_abs_dp_vs_corpus"])
                                             for r in rows])) if rows else 0.0),
            "tolerance": "exact equality at the corpus's 8 decimals",
            "role": "external — R-B1 demotes the corpus out of the contrast",
            "rps_max_abs_diff": joined["max_abs_rps_diff"]},
        "harness_freeze": freeze,
        "canaries": pre,
        "table": table,
        "written_at": pd.Timestamp.now("UTC").isoformat(),
    })
    if write:
        EVWIDEN_JSON.parent.mkdir(parents=True, exist_ok=True)
        EVWIDEN_JSON.write_text(json.dumps(result, indent=2, default=str) + "\n")
        result["written"] = [paths.rel(EVWIDEN_JSON)]
    return result


# ==========================================================================
# 14. THE TABLE-RETRO LEG — §3.3, through `simretro`'s own public surface
# ==========================================================================

#: §3.3: `epl/simretro.py` is PROTECTED, its `ARMS` tuple is closed, and
#: `ArchiveRunner._provider` raises on any other arm — so the table leg is this
#: NEW module reusing `epl.leaguesim` / `epl.particles` / `epl.season` /
#: `epl.table` / `epl.simmetrics` (all read-only imports) and reproducing
#: `simretro`'s schedule through `simretro`'s own public surface.
#: `data/epl/sim/retro_r1.jsonl` is read-only and never appended.
TABLE_ARM_LABEL = "dc_native"

#: §3.4's illustrative cells — "the one Hull-analogue", printed under that label
#: with NO decision weight.
HULL_ANALOGUE = ("2025/26", "sunderland")

#: §3.4's relegation band: the bottom three finishing positions.
RELEGATION_RANKS = 3

_TABLE_ROW_FIELDS = ("schema", "key", "season", "cutoff_label", "cutoff",
                     "clubs", "treated_clubs", "provisional_incumbent",
                     "provisional_enlarged", "evidence", "n_sims", "seed",
                     "arms", "identical", "realised_hash", "config_sha256",
                     "harness_sha256", "harness_frozen")


def table_cutoffs(matches: pd.DataFrame, seasons: Sequence[str] | None = None,
                  labels: Sequence[str] | None = None,
                  ) -> list[tuple[str, str, pd.Timestamp]]:
    """§3.3's 35 cells, from `simretro`'s own `SEASONS`, `COMPARISON_CUTOFFS`
    and `cutoff_schedule` — never from a remembered list of dates."""
    from epl import simretro

    seasons = tuple(simretro.SEASONS) if seasons is None else tuple(seasons)
    labels = (tuple(simretro.COMPARISON_CUTOFFS) if labels is None
              else tuple(labels))
    out = []
    for season in seasons:
        schedule = simretro.cutoff_schedule(matches, season)
        for label in labels:
            out.append((season, label, pd.Timestamp(schedule[label]).normalize()))
    return out


def table_cells(matches: pd.DataFrame, played: pd.DataFrame | None = None, *,
                store=None, cfg: dict | None = None,
                seasons: Sequence[str] | None = None,
                labels: Sequence[str] | None = None,
                e_star: float = E_STAR, check: bool = True) -> list[dict[str, Any]]:
    """Which cells the re-key changes, enumerated WITHOUT fitting anything.

    §3.3 pre-states 16 treated and 19 untouched, and the 19 are "unchanged by
    construction, and the harness must prove it". This function is the
    enumeration half of that: the incumbent predicate is read through
    ``count_volatility_arm`` at each scheduled cutoff — the same function
    ``epl/dcfit.py:273-274`` calls — and the evidence rule through §0.3's recipe,
    so the membership can be frozen by the §6 commit before a single simulated
    season exists.
    """
    from epl import freeze
    from epl import fit as epl_fit
    from wcmodel.model.volatility_diagnostic import count_volatility_arm

    cfg = freeze.frozen_wcmodel_config() if cfg is None else cfg
    if played is None:
        played = matches.loc[matches["played"]].copy()
        played["date"] = pd.to_datetime(played["date"]).dt.normalize()
    store = epl_fit.build_store(played) if store is None else store

    out: list[dict[str, Any]] = []
    for season, label, cutoff in table_cutoffs(matches, seasons, labels):
        frame = matches.loc[matches["season"] == season]
        clubs = sorted(set(frame["home_key"].astype(str))
                       | set(frame["away_key"].astype(str)))
        arm = count_volatility_arm(store, cutoff, clubs, config=cfg)
        incumbent = sorted(str(t) for t in
                           arm.loc[arm["volatility_flag"]
                                   | arm["few_games_flag"], "team"])
        evidence = effective_evidence(cutoff, played, clubs)
        thin = {c for c in clubs if evidence[c] < float(e_star)}
        enlarged = sorted(set(incumbent) | thin)
        out.append({
            "season": season, "cutoff_label": label,
            "cutoff": str(cutoff.date()), "clubs": clubs,
            "provisional_incumbent": incumbent,
            "provisional_enlarged": enlarged,
            "treated_clubs": sorted(thin - set(incumbent)),
            "evidence": {c: round(float(v), ROUND_DP)
                         for c, v in sorted(evidence.items())},
        })
    if check:
        treated = [c for c in out if c["treated_clubs"]]
        if len(out) != EXPECTED_TABLE_CELLS or \
                len(treated) != EXPECTED_TABLE_TREATED:
            raise MembershipMismatch(
                f"{len(out)} table cells of which {len(treated)} change; §3.3 "
                f"pre-states {EXPECTED_TABLE_CELLS} and "
                f"{EXPECTED_TABLE_TREATED}")
    return out


def table_key(cell: dict[str, Any], config_sha: str, n_sims: int,
              seed: int) -> str:
    """The table leg's resume key: one cell, one configuration, one budget."""
    return (f"{cell['season']}|{cell['cutoff_label']}|{cell['cutoff']}|"
            f"{int(n_sims)}|{int(seed)}|{config_sha}")


class TableRunner:
    """One fit and TWO simulations per cell, CRN-paired by construction.

    §3.3's mechanics, in code: per cell **one fit** serves both arms (the
    posterior is arm-invariant, §0.2); the control book carries the incumbent
    provisional set, the treatment book the §2.1 union; the two runs use the
    same ``SimPlan``, the same seed and therefore the same per-fixture RNG
    streams (``epl.leaguesim`` keys them by ``(chunk, fixture)``, never by arm),
    so the **only** divergence is the D12 per-fixture Bernoulli widening branch
    on treated fixtures.

    BOTH RUNS ARE LABELLED ``dc_native`` TO ``leaguesim``, and that is honest
    rather than convenient: the provider IS ``DCNativeProvider`` in both arms —
    ``resolve_provider`` refuses to let a ``ParticleBook`` wear another arm's
    name — and what differs is the BOOK, which is the treatment. The experiment's
    arm name ``dc_evwiden`` names the re-keyed book and is recorded on the row.

    D2 stays static-within-fit and D12 stays per-fixture: the two standing open
    owner rulings this experiment explicitly does not touch.
    """

    def __init__(self, matches: pd.DataFrame | None = None, *,
                 played: pd.DataFrame | None = None, store=None, anchor=None,
                 config: dict | None = None, n_sims: int | None = None,
                 seed: int | None = None, chunk_size: int | None = None,
                 require_verified_adjustments: bool = True,
                 verbose: bool = True):
        from epl import anchor as anchor_mod, baseline, freeze, leaguesim
        from epl import fit as epl_fit, simretro
        from epl.schema import sort_for_walk_forward

        self.matches = baseline.load_matches() if matches is None else matches
        self.played = (sort_for_walk_forward(self.matches.loc[self.matches["played"]])
                       if played is None else played)
        self.config = freeze.frozen_wcmodel_config() if config is None else config
        self.config_sha256 = assert_config_frozen(cfg=self.config)
        self.store = epl_fit.build_store(self.played) if store is None else store
        self.anchor = (anchor_mod.Anchor(self.played, freeze.frozen_elo_config())
                       if anchor is None else anchor)
        self.n_sims = int(simretro.DEFAULT_N_SIMS if n_sims is None else n_sims)
        self.seed = int(simretro.SEED if seed is None else seed)
        self.chunk_size = int(leaguesim.DEFAULT_CHUNK_SIZE if chunk_size is None
                              else chunk_size)
        self.require_verified_adjustments = bool(require_verified_adjustments)
        self.verbose = bool(verbose)
        self.harness_sha256 = sha256_file(paths.REPO_ROOT / HARNESS_FILES[0])
        self._epl_fit = epl_fit

    def __call__(self, cell: dict[str, Any]) -> dict[str, Any]:
        import dataclasses

        from epl import dcfit, leaguesim, particles, season as season_mod
        from epl import simmetrics, simretro, table as table_mod

        season, label = str(cell["season"]), str(cell["cutoff_label"])
        cutoff = pd.Timestamp(cell["cutoff"]).normalize()
        started = time.perf_counter()

        state = season_mod.archive_season_state(
            self.matches, season, cutoff,
            require_verified_adjustments=self.require_verified_adjustments)
        with self._epl_fit.config_read_once(self.config):
            post, info = dcfit.fit_epl(cutoff, self.store, self.anchor,
                                       self.config, matches=self.played,
                                       feature_cache_dir=paths.FIT_CACHE_DIR)

        incumbent = {str(t) for t in post.provisional_teams}
        enlarged = incumbent | set(cell["treated_clubs"])
        realised_treated = sorted(enlarged - incumbent)
        if realised_treated != sorted(cell["treated_clubs"]):
            raise PredicateMismatch(
                f"{season} {label}: the fit's own incumbent set makes the "
                f"treated clubs {realised_treated}, and §3.3's frozen "
                f"enumeration says {sorted(cell['treated_clubs'])}. The 16 "
                "treated cells are pinned by the §6 commit; a run in which a "
                "different set changes is not the run this document "
                "preregisters.")

        control = particles.ParticleBook.from_posterior(post)
        missing = [c for c in state.clubs if c not in control.idx]
        if missing:
            raise UnpriceableFixture(
                f"{season} {label}: the posterior cannot price {missing}")
        treatment = dataclasses.replace(control,
                                        provisional=frozenset(enlarged))

        realised = simretro.realised_positions(
            self.matches, season,
            require_verified=self.require_verified_adjustments)
        clubs = list(state.clubs)
        positions = realised.position_vector(clubs)
        spans = realised.span_vector(clubs)
        truth = realised.points_vector(clubs)
        weights = simmetrics.consequence_weights(len(clubs))

        arms: dict[str, Any] = {}
        for name, book in (("control", control), ("treatment", treatment)):
            run = leaguesim.simulate(TABLE_ARM_LABEL, book, self.n_sims,
                                     self.seed, chunk_size=self.chunk_size,
                                     n_particles=book.n_particles)
            matrix = simmetrics.scored_matrix(run.matrix, len(clubs))
            table_mod.check_doubly_stochastic(run.matrix)
            points = np.asarray(run.retained_rows.points)
            arms[name] = {
                "trps": float(simmetrics.trps(matrix, positions, spans=spans)),
                "wtrps": float(simmetrics.wtrps(matrix, positions, weights,
                                                spans=spans)),
                "flat_trps": float(simmetrics.flat_trps(positions, spans=spans)),
                "digest": run.digest(),
                "effective_posterior_hash": book.content_hash(),
                "provisional": sorted(book.provisional),
                "coverage": simmetrics.interval_coverage(points, truth),
                "coverage_treated": _coverage_for(points, truth, clubs,
                                                  cell["treated_clubs"]),
                "clubs_detail": _club_detail(matrix, points, clubs,
                                             cell["treated_clubs"], truth),
                "n_sims": int(run.n_sims), "n_particles": int(run.n_particles),
                "widening_mode":
                    f"per_fixture_bernoulli@alpha={book.alpha:g}",
            }
            if self.verbose:
                print(f"[evwiden-table] {season} {label} {name} "
                      f"TRPS={arms[name]['trps']:.6f}", flush=True)

        identical = assert_table_identity(
            cell["treated_clubs"], arms["control"]["digest"],
            arms["treatment"]["digest"], where=f"{season} {label}")

        return {
            "schema": SCHEMA_ID, "season": season, "cutoff_label": label,
            "cutoff": str(cutoff.date()), "clubs": clubs,
            "treated_clubs": sorted(cell["treated_clubs"]),
            "provisional_incumbent": sorted(incumbent),
            "provisional_enlarged": sorted(enlarged),
            "evidence": dict(cell["evidence"]),
            "n_sims": self.n_sims, "seed": self.seed,
            "arms": arms, "identical": identical,
            "realised_hash": realised.realised_hash,
            "realised_positions": {c: int(p) for c, p in
                                   zip(clubs, positions.tolist())},
            "realised_points": {c: int(p) for c, p in zip(clubs, truth.tolist())},
            "n_training_matches": int(info.n_training_matches),
            "cold_start_teams": list(info.cold_start_teams),
            "config_sha256": self.config_sha256,
            "harness_sha256": self.harness_sha256,
            "wall_seconds": round(time.perf_counter() - started, 2),
        }


def assert_table_identity(treated_clubs: Sequence[str], control_digest: str,
                          treatment_digest: str, *, where: str) -> bool:
    """§3.3's two-sided identity demand, in one place so it can be tested.

    The 19 untouched cells are "unchanged by construction, **and the harness
    must prove it**": an untouched cell whose treatment digest differs from its
    control's is :class:`TableIdentityBreak`.

    The OTHER direction is refused too, and it is not in the document's letter
    because the document could not have anticipated a harness bug: a cell whose
    rule-named treated clubs produced a byte-identical run is not a null result
    — it is a treatment that never reached the sampler, and reporting its zero
    delta as evidence of "no harm" would be reporting the absence of the
    experiment.
    """
    identical = bool(str(control_digest) == str(treatment_digest))
    if not treated_clubs and not identical:
        raise TableIdentityBreak(
            f"{where} carries no treated club, so the two books are the same "
            "book and the two runs must be the same run — but their digests "
            f"differ ({str(control_digest)[:12]}… vs "
            f"{str(treatment_digest)[:12]}…). §3.3 rules the 19 untouched cells "
            "unchanged BY CONSTRUCTION and requires the harness to prove it; a "
            "break here means the treatment reaches further than the rule names.")
    if treated_clubs and identical:
        raise TableIdentityBreak(
            f"{where} carries treated clubs {sorted(treated_clubs)} and the two "
            "arms produced byte-identical runs. A treatment that changes nothing "
            "where the rule says it should is not a null result — it is a "
            "treatment that never reached the sampler, and its zero delta is the "
            "absence of the experiment rather than evidence of no harm.")
    return identical


def _coverage_for(points: np.ndarray, truth: np.ndarray, clubs: Sequence[str],
                  wanted: Sequence[str]) -> dict[str, Any]:
    """§3.4's per-club points-interval coverage for the TREATED clubs.

    §1.3 fixes the reading direction BEFORE any number exists: if the control
    arm's coverage for treated clubs already sits at or above nominal and the
    treatment pushes it further above, that is evidence FOR double-counting and
    AGAINST this rule. No sign is assumed here and none is implied by the
    ordering of these fields.
    """
    from epl import simmetrics

    out: dict[str, Any] = {}
    index = {c: i for i, c in enumerate(clubs)}
    for club in sorted(str(c) for c in wanted):
        if club not in index:
            continue
        i = index[club]
        out[club] = simmetrics.interval_coverage(points[:, [i]], truth[[i]])
    return out


def _club_detail(matrix: np.ndarray, points: np.ndarray, clubs: Sequence[str],
                 wanted: Sequence[str], truth: np.ndarray) -> dict[str, Any]:
    """§3.4's illustrative per-club figures for the treated clubs.

    Relegation probability, the points mean, and the 5-95 band — the three
    numbers `reports/epl_sim_issuance_2026-08-21.md` §4 used to describe Hull's
    unexplained dispersion, computed here for the one historical analogue and
    printed with NO decision weight.
    """
    out: dict[str, Any] = {}
    index = {c: i for i, c in enumerate(clubs)}
    for club in sorted(str(c) for c in wanted):
        if club not in index:
            continue
        i = index[club]
        column = np.asarray(points[:, i], dtype=float)
        out[club] = {
            "p_relegated": float(np.asarray(matrix)[i, -RELEGATION_RANKS:].sum()),
            "points_mean": float(column.mean()),
            "points_sd": float(column.std(ddof=1)),
            "points_p5": float(np.quantile(column, 0.05, method="lower")),
            "points_p95": float(np.quantile(column, 0.95, method="lower")),
            "points_realised": int(truth[i]),
        }
    return out


def run_table(cells: Sequence[dict[str, Any]],
              ledger_path: Path | str | None = None, *,
              runner: Callable[[dict], dict] | None = None,
              n_sims: int | None = None, seed: int | None = None,
              config_sha: str | None = None, resume: bool = True,
              verbose: bool = True, harness_frozen: bool = True,
              ) -> dict[str, Any]:
    """Run both arms at every cell and append one JSONL row per cell.

    Resumable per cell and poisoned per cell, exactly as the match-level shard
    is: §2.4's budget is 35 fits plus 70 runs of 20,000 simulated seasons, and a
    crash two hours in should cost the cell in flight and nothing else.
    """
    ledger_path = Path(ledger_path) if ledger_path is not None else TABLE_LEDGER
    _guard_ledger_location(ledger_path, harness_frozen)
    runner = TableRunner(n_sims=n_sims, seed=seed,
                         verbose=verbose) if runner is None else runner
    n_sims = int(getattr(runner, "n_sims", n_sims or 0))
    seed = int(getattr(runner, "seed", seed or 0))
    config_sha = (getattr(runner, "config_sha256", None) or config_sha
                  or config_sha256())

    repair_tail(ledger_path)
    stale = poison_rows(ledger_path)
    if stale:
        first = stale[0]
        raise ShardFailed(
            f"{paths.rel(ledger_path)} still carries {len(stale)} poison row(s) "
            f"— the first is {first.get('error_type')} at {first.get('key')}: "
            f"{first.get('error')}. Fail closed: inspect the failure, then "
            "remove this ledger and re-run the leg.")

    done: set[str] = set()
    if resume:
        rows, _, _ = read_jsonl(ledger_path)
        done = {str(r["key"]) for r in rows if "key" in r}

    started = time.time()
    written = 0
    for i, cell in enumerate(cells, 1):
        key = table_key(cell, config_sha, n_sims, seed)
        if key in done:
            continue
        try:
            row = runner(cell)
        except EvWidenError as exc:
            _poison_table(ledger_path, cell, key, exc)
            raise
        except Exception as exc:                     # noqa: BLE001 — typed below
            wrapped = FitFailed(
                f"{cell['season']} {cell['cutoff_label']}: "
                f"{type(exc).__name__}: {exc}")
            _poison_table(ledger_path, cell, key, wrapped)
            raise wrapped from exc
        row.update({"key": key, "harness_frozen": bool(harness_frozen),
                    "config_sha256": config_sha})
        for field in _TABLE_ROW_FIELDS:
            if field not in row:
                raise SchemaMismatch(
                    f"a table row for {key} lacks {field!r}")
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        written += 1
        if verbose:
            el = time.time() - started
            print(f"[evwiden-table] {i}/{len(cells)} {cell['season']} "
                  f"{cell['cutoff_label']} treated={len(cell['treated_clubs'])} "
                  f"(elapsed {el / 60:.1f}m)", flush=True)

    return {"n_cells": len(cells), "n_written": written,
            "n_skipped": len(cells) - written,
            "ledger": str(ledger_path),
            "seconds": round(time.time() - started, 1),
            "harness_frozen": bool(harness_frozen)}


def _poison_table(path: Path, cell: dict, key: str, exc: BaseException) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps({
            "schema": SCHEMA_ID, "poison": True, "key": key,
            "season": cell.get("season"), "cutoff_label": cell.get("cutoff_label"),
            "error_type": type(exc).__name__, "error": str(exc),
            "started_at": pd.Timestamp.now("UTC").isoformat(),
        }, default=str) + "\n")


def load_table_ledger(path: Path | str | None = None, *,
                      expected: Sequence[dict[str, Any]] | None = None,
                      ) -> list[dict[str, Any]]:
    """Every cell row, de-duplicated, schema-checked, and complete.

    "Complete" is the same demand the match-level merge makes: the cell set must
    be EXACTLY the pre-stated one — not a superset, not a subset — because a
    pooled mean over 34 cells is not the quantity §4.1 (iv) gates on.
    """
    path = Path(path) if path is not None else TABLE_LEDGER
    rows, poison, _ = read_jsonl(path)
    if poison:
        first = poison[0]
        raise ShardFailed(
            f"{paths.rel(path)} carries {len(poison)} poison row(s); the first "
            f"is {first.get('error_type')} at {first.get('key')}")
    keep: dict[str, dict] = {}
    for row in rows:
        for field in _TABLE_ROW_FIELDS:
            if field not in row:
                raise SchemaMismatch(
                    f"{paths.rel(path)}: a cell row for {row.get('key')!r} lacks "
                    f"{field!r}")
        key = str(row["key"])
        if key in keep:
            a = json.dumps(_strip_volatile(keep[key]), sort_keys=True, default=str)
            b = json.dumps(_strip_volatile(row), sort_keys=True, default=str)
            if a != b:
                raise RowConflict(
                    f"{paths.rel(path)} holds two rows for {key} that disagree")
            continue
        keep[key] = row
    out = sorted(keep.values(), key=lambda r: (str(r["season"]),
                                               str(r["cutoff"])))
    unfrozen = [r["key"] for r in out if not r.get("harness_frozen")]
    if unfrozen:
        raise EvWidenError(
            f"{len(unfrozen)} table cell(s) carry harness_frozen: false (first: "
            f"{unfrozen[:2]}): a cell run during the audit is not a cell of the "
            "preregistered run.")
    if expected is not None:
        want = {f"{c['season']}|{c['cutoff_label']}" for c in expected}
        got = {f"{r['season']}|{r['cutoff_label']}" for r in out}
        if want != got:
            raise MergeIncomplete(
                f"the table ledger holds {len(got)} cell(s), not the pre-stated "
                f"{len(want)}: {len(want - got)} missing "
                f"(first: {sorted(want - got)[:3]}), {len(got - want)} "
                f"unexpected (first: {sorted(got - want)[:3]}). Not a superset, "
                "not a subset.")
    return out


def score_table(rows: Sequence[dict[str, Any]], *, n_boot: int = N_BOOT,
                seed: int = BOOTSTRAP_SEED,
                expected_cells: int | None = None) -> dict[str, Any]:
    """§3.4's table-side numbers: per-cell paired deltas, pooled, and coverage.

    Everything here except the pooled ΔTRPS is a SECONDARY and decides nothing.
    The pooled ΔTRPS feeds §4.1 (iv), which is a do-no-harm gate: it can block an
    adoption and can never grant one.

    TRPS IS PROPER FOR THE DISPLAYED MARGINALS ONLY — `epl/simmetrics.py` says so
    in its own docstring. Two forecasts with the same position matrix and a
    different correlation structure score identically; widening changes the joint
    too, and no table metric here can see that. Disclosed, not solved.
    """
    if not rows:
        raise MergeIncomplete("no table cells to score")
    if expected_cells is not None and len(rows) != int(expected_cells):
        raise MergeIncomplete(
            f"{len(rows)} table cells, not the pre-stated {expected_cells}. §7 "
            "makes dropping a cell after the run starts an invalidation.")

    per_cell = []
    for row in rows:
        control, treatment = row["arms"]["control"], row["arms"]["treatment"]
        per_cell.append({
            "season": str(row["season"]), "cutoff_label": str(row["cutoff_label"]),
            "cutoff": str(row["cutoff"]),
            "treated_clubs": list(row["treated_clubs"]),
            "trps_control": float(control["trps"]),
            "trps_treatment": float(treatment["trps"]),
            "delta_trps": float(treatment["trps"]) - float(control["trps"]),
            "wtrps_control": float(control["wtrps"]),
            "wtrps_treatment": float(treatment["wtrps"]),
            "delta_wtrps": float(treatment["wtrps"]) - float(control["wtrps"]),
            "identical": bool(row["identical"]),
            "coverage_control": dict(control.get("coverage") or {}),
            "coverage_treatment": dict(treatment.get("coverage") or {}),
            "coverage_treated_control": dict(control.get("coverage_treated") or {}),
            "coverage_treated_treatment":
                dict(treatment.get("coverage_treated") or {}),
        })

    deltas = np.array([c["delta_trps"] for c in per_cell], dtype=float)
    seasons = [c["season"] for c in per_cell]
    pooled = _summarise(deltas, seasons, n_boot=n_boot, seed=seed)
    wdeltas = np.array([c["delta_wtrps"] for c in per_cell], dtype=float)
    pooled_w = _summarise(wdeltas, seasons, n_boot=n_boot, seed=seed)

    by_label: list[dict[str, Any]] = []
    for label in sorted({c["cutoff_label"] for c in per_cell}):
        idx = [i for i, c in enumerate(per_cell) if c["cutoff_label"] == label]
        by_label.append({"cutoff_label": label, "n": len(idx),
                         "mean_delta_trps": float(deltas[idx].mean()),
                         "mean_delta_wtrps": float(wdeltas[idx].mean())})

    analogue = [c for c in per_cell if c["season"] == HULL_ANALOGUE[0]
                and HULL_ANALOGUE[1] in c["treated_clubs"]]
    analogue_detail = [{
        "season": r["season"], "cutoff_label": r["cutoff_label"],
        "control": (r["arms"]["control"].get("clubs_detail") or {}).get(
            HULL_ANALOGUE[1]),
        "treatment": (r["arms"]["treatment"].get("clubs_detail") or {}).get(
            HULL_ANALOGUE[1]),
    } for r in rows if str(r["season"]) == HULL_ANALOGUE[0]
        and HULL_ANALOGUE[1] in (r.get("treated_clubs") or ())]

    untouched = [c for c in per_cell if not c["treated_clubs"]]
    broken = [f"{c['season']} {c['cutoff_label']}" for c in untouched
              if c["delta_trps"] != 0.0 or not c["identical"]]
    if broken:
        raise TableIdentityBreak(
            f"{len(broken)} untouched cell(s) moved: {broken[:5]}. §3.3 rules "
            "them unchanged BY CONSTRUCTION and requires the harness to prove it.")

    return {
        "schema": SCHEMA_ID, "n_cells": len(per_cell),
        "n_treated_cells": len(per_cell) - len(untouched),
        "n_untouched_cells": len(untouched),
        "pooled_delta_trps": pooled, "pooled_delta_wtrps": pooled_w,
        "per_cutoff_label": by_label, "per_cell": per_cell,
        "hull_analogue": {
            "label": "the one Hull-analogue — illustrative, no decision weight",
            "season": HULL_ANALOGUE[0], "club": HULL_ANALOGUE[1],
            "n_cells": len(analogue), "cells": analogue_detail},
        "coverage_reading": (
            "§1.3, fixed before the run: if the CONTROL arm's coverage for "
            "treated clubs already sits at or above nominal and the treatment "
            "pushes it further above, that is evidence FOR double-counting and "
            "AGAINST this rule, and the result document must say so in those "
            "words. No sign is assumed."),
        "trps_limitation": (
            "TRPS is proper for the DISPLAYED MARGINALS only (epl/simmetrics.py's "
            "own docstring): two forecasts with the same position matrix and a "
            "different correlation structure score identically, widening changes "
            "the joint too, and no metric here sees that."),
        "secondaries_decide": "nothing",
    }


def table_gate(scored: dict[str, Any]) -> dict[str, Any]:
    """§4.1 (iv), the do-no-harm gate the queue binds.

    > the pooled mean paired ΔTRPS (treatment − control, equal weights over the
    > 35 cells) is ≤ +0.0002, AND it is not the case that the pooled ΔTRPS is
    > > 0 with its 95% season-block CI (7 blocks) excluding zero.

    §4.3 discloses that both numbers are INVENTED — R1 has no pass rule
    (`reports/epl_sim_retro_v1_1.md` §10: *"Nothing, by itself"*) — invented from
    R1's own recorded scale before any widened table existed, and that a 7-block
    percentile bootstrap has poor coverage and is not claimed to have good
    coverage. Its job is the narrow one both predecessors gave season blocks: to
    refuse a verdict carried by one season.
    """
    pooled = scored["pooled_delta_trps"]
    mean = float(pooled["mean"])
    lo, hi = (float(v) for v in pooled["ci95"])
    within = mean <= TABLE_TOLERANCE
    resolvable_harm = bool(mean > 0.0 and lo > 0.0)
    return {
        "PASS": bool(within and not resolvable_harm),
        "pooled_delta_trps": mean, "tolerance": TABLE_TOLERANCE,
        "within_tolerance": bool(within),
        "ci95_season": [lo, hi], "n_blocks": int(pooled["n_blocks"]),
        "significant_worsening": resolvable_harm,
        "n_cells": int(scored["n_cells"]),
        "disclosure": ("§4.3: both numbers are invented — R1 has no pass rule — "
                       "from R1's own recorded scale, before any widened table "
                       "existed. A 7-block percentile bootstrap has poor "
                       "coverage and is not claimed to have good coverage."),
    }


# ==========================================================================
# 15. THE EVIDENCE CONTRACT — §6, regardless of outcome
# ==========================================================================

#: §6's per-fixture columns, in the order the file writes them.
_PER_FIXTURE_COLUMNS = (
    "key", "match_id", "season", "block", "cutoff", "date",
    "home_key", "away_key", "e_home", "e_away", "e_min", "e_star",
    "thin", "treated", "incumbent_widened", "thin_at",
    "native_home", "native_draw", "native_away",
    "arm_home", "arm_draw", "arm_away",
    "y", "rps_native", "rps_arm", "delta")

_TABLE_COLUMNS = (
    "season", "cutoff_label", "cutoff", "arm", "trps", "wtrps", "flat_trps",
    "coverage50", "coverage90", "treated_clubs", "n_treated_clubs",
    "identical", "digest", "effective_posterior_hash", "realised_hash",
    "n_sims", "seed")

_GRID_COLUMNS = ("e_star", "population", "treated", "already_widened",
                 "mean_delta", "sd", "ci95_lo", "ci95_hi", "n_blocks",
                 "degenerate_by_construction")


def _write_csv(path: Path, columns: Sequence[str],
               rows: Iterable[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns),
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def per_fixture_evidence(rows: Sequence[dict[str, Any]], *,
                         e_star: float = E_STAR) -> list[dict[str, Any]]:
    """§6's 85 thin-fixture rows, projected from the ledger without loss.

    A reader holding this file and nothing else can recompute the estimand with
    arithmetic alone — average ``delta`` over the 85 — and both bootstrap
    intervals, which is why ``block`` and ``season`` are columns rather than
    something to be joined back from a parquet nobody committed.
    """
    out = []
    for row in sorted(rows, key=lambda r: (str(r["cutoff"]), str(r["match_id"]))):
        if float(row["e_min"]) >= float(e_star):
            continue
        native = [float(v) for v in row["probs_native"]]
        arm = [float(v) for v in row["probs_arm"]]
        out.append({
            "key": row["key"], "match_id": row["match_id"],
            "season": row["season"], "block": row["block"],
            "cutoff": row["cutoff"], "date": row["date"],
            "home_key": row["home_key"], "away_key": row["away_key"],
            "e_home": row["e_home"], "e_away": row["e_away"],
            "e_min": row["e_min"], "e_star": float(e_star),
            "thin": bool(row["thin"]), "treated": bool(row["treated"]),
            "incumbent_widened": bool(row["incumbent_widened"]),
            "thin_at": ";".join(row["thin_at"]),
            "native_home": native[0], "native_draw": native[1],
            "native_away": native[2],
            "arm_home": arm[0], "arm_draw": arm[1], "arm_away": arm[2],
            "y": int(row["y"]), "rps_native": float(row["rps_native"]),
            "rps_arm": float(row["rps_arm"]), "delta": float(row["delta"]),
        })
    return out


def table_evidence(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """§6's 35 cells x both arms, one CSV row per (cell, arm)."""
    out = []
    for row in sorted(rows, key=lambda r: (str(r["season"]), str(r["cutoff"]))):
        for arm in ("control", "treatment"):
            leg = row["arms"][arm]
            coverage = leg.get("coverage") or {}
            out.append({
                "season": row["season"], "cutoff_label": row["cutoff_label"],
                "cutoff": row["cutoff"],
                "arm": BASELINE_ARM if arm == "control" else ARM_NAME,
                "trps": leg["trps"], "wtrps": leg["wtrps"],
                "flat_trps": leg.get("flat_trps"),
                "coverage50": coverage.get("coverage50"),
                "coverage90": coverage.get("coverage90"),
                "treated_clubs": ";".join(row["treated_clubs"]),
                "n_treated_clubs": len(row["treated_clubs"]),
                "identical": bool(row["identical"]),
                "digest": leg.get("digest"),
                "effective_posterior_hash": leg.get("effective_posterior_hash"),
                "realised_hash": row.get("realised_hash"),
                "n_sims": row.get("n_sims"), "seed": row.get("seed"),
            })
    return out


def grid_evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    """§6's grid file: every grid point's population, treated count, mean, CI."""
    return [{
        "e_star": g["e_star"], "population": g["population"],
        "treated": g["treated"], "already_widened": g["already_widened"],
        "mean_delta": g["mean"], "sd": g.get("sd"),
        "ci95_lo": g["ci95"][0], "ci95_hi": g["ci95"][1],
        "n_blocks": g["n_blocks"],
        "degenerate_by_construction": bool(g["degenerate_by_construction"]),
    } for g in result["secondaries"]["grid"]]


def update_manifest(entries: dict[str, str], path: Path | str | None = None,
                    ) -> Path:
    """§6: the bulky local artifacts' digests AND byte sizes, in the manifest.

    Existing lines are preserved in their existing order and updated in place;
    new ones are appended. The manifest is a shared file that two earlier
    experiments already wrote, and rewriting it from scratch would silently drop
    their entries — which is the opposite of what a manifest is for.
    """
    path = Path(path) if path is not None else EVIDENCE_MANIFEST
    fresh: dict[str, str] = {}
    for rel, target in entries.items():
        target = Path(target)
        if not target.exists():
            continue
        fresh[rel] = f"{sha256_file(target)}  {rel}  {target.stat().st_size}"

    lines: list[str] = []
    seen: set[str] = set()
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] in fresh:
                lines.append(fresh[parts[1]])
                seen.add(parts[1])
            elif line.strip():
                lines.append(line)
    lines.extend(v for k, v in sorted(fresh.items()) if k not in seen)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def write_evidence(result: dict[str, Any],
                   rows: Sequence[dict[str, Any]] | None = None,
                   table_rows: Sequence[dict[str, Any]] | None = None, *,
                   directory: Path | str | None = None,
                   manifest: bool = True) -> dict[str, str]:
    """§6's evidence contract, written whichever way the numbers fell.

    ULTRA-REVIEW LESSON 1, applied from day one: the verdict's machine-readable
    basis is COMMITTED under `reports/evidence/`, not left in a gitignored
    `data/`. `reports/evidence/README.md` records why that directory exists —
    two experiments shipped verdicts whose every machine artifact sat where a
    reader could not check a single number.

    §4.4: there is no file drawer. This function is called on a miss exactly as
    it is called on a hit, including the two embarrassing cases §4.4 pre-names.
    """
    directory = Path(directory) if directory is not None else EVIDENCE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    json_path = directory / EVIDENCE_JSON.name
    json_path.write_text(json.dumps(result, indent=2, default=str) + "\n")
    written["widening.json"] = paths.rel(json_path)

    if rows is not None:
        p = _write_csv(directory / EVIDENCE_PER_FIXTURE.name,
                       _PER_FIXTURE_COLUMNS, per_fixture_evidence(rows))
        written["widening_per_fixture.csv"] = paths.rel(p)
    if "secondaries" in result:
        p = _write_csv(directory / EVIDENCE_GRID_MEANS.name, _GRID_COLUMNS,
                       grid_evidence(result))
        written["widening_grid_means.csv"] = paths.rel(p)
    if table_rows is not None:
        p = _write_csv(directory / EVIDENCE_TABLE_CELLS.name, _TABLE_COLUMNS,
                       table_evidence(table_rows))
        written["widening_table_cells.csv"] = paths.rel(p)
    if manifest:
        p = update_manifest({paths.rel(EVWIDEN_JSON): EVWIDEN_JSON,
                             paths.rel(TABLE_LEDGER): TABLE_LEDGER,
                             paths.rel(CANARY_JSON): CANARY_JSON,
                             **{paths.rel(s): s for s in
                                sorted(EVWIDEN_DIR.glob("shard_*.jsonl"))}},
                            directory / EVIDENCE_MANIFEST.name)
        written["MANIFEST.sha256"] = paths.rel(p)
    return written


def verify(directory: Path | str | None = None, *, shards: int = 1,
           evidence: Path | str | None = None,
           n_boot: int = N_BOOT, seed: int = BOOTSTRAP_SEED,
           tolerance: float = 1e-12) -> dict[str, Any]:
    """Re-derive the published headline from the COMMITTED evidence, and from
    the shard ledgers, and demand they agree.

    This is the check a reader of the repository can run. `widening.json` is a
    verdict somebody wrote down; `widening_per_fixture.csv` is the 85 rows it
    rests on. Averaging one column of the CSV must reproduce the JSON's mean to
    1e-12, and re-scoring the shard ledgers must reproduce it again — so the
    three ways of arriving at the number are three, and not one number copied
    twice.

    It fits nothing, simulates nothing and writes nothing.
    """
    evidence = Path(evidence) if evidence is not None else EVIDENCE_JSON
    if not evidence.exists():
        raise MergeIncomplete(
            f"{paths.rel(evidence)} is not on disk: there is no published "
            "verdict to verify. §6's evidence contract is written by the merge "
            "regardless of outcome, so an absent file is a run that never "
            "finished rather than a result that went the wrong way.")
    published = json.loads(evidence.read_text())

    per_fixture = evidence.with_name(EVIDENCE_PER_FIXTURE.name)
    from_csv: dict[str, Any] = {"path": paths.rel(per_fixture), "present": False}
    if per_fixture.exists():
        with per_fixture.open() as fh:
            rows = list(csv.DictReader(fh))
        deltas = np.array([float(r["delta"]) for r in rows], dtype=float)
        lo, hi, n_blocks = score_mod.block_bootstrap_ci(
            deltas, [str(r["block"]) for r in rows], n_boot=n_boot,
            alpha=ALPHA, seed=seed)
        from_csv = {"path": paths.rel(per_fixture), "present": True,
                    "n": len(rows), "mean": float(deltas.mean()),
                    "ci95": [lo, hi], "n_blocks": int(n_blocks)}

    from_ledger: dict[str, Any] = {"present": False}
    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    paths_present = [directory / shard_name(i, shards) for i in range(int(shards))]
    if all(p.exists() for p in paths_present):
        ledger_rows = [r for p in paths_present for r in load_ledger(p)]
        scored = estimand(ledger_rows, n_boot=n_boot, seed=seed,
                          corpus_rows=CORPUS_ROWS)
        from_ledger = {"present": True, "n": scored["n"],
                       "mean": scored["mean"], "ci95": scored["ci95"],
                       "run_digest": run_digest(ledger_rows)}

    checks = []
    for name, got in (("per_fixture_csv", from_csv), ("shard_ledgers", from_ledger)):
        if not got.get("present"):
            checks.append({"source": name, "checked": False,
                           "why": "not on disk"})
            continue
        d_mean = abs(float(got["mean"]) - float(published["mean"]))
        d_n = int(got["n"]) - int(published["n"])
        checks.append({"source": name, "checked": True,
                       "delta_mean": d_mean, "delta_n": d_n,
                       "PASS": bool(d_mean <= tolerance and d_n == 0)})
    ran = [c for c in checks if c.get("checked")]
    out = {"schema": SCHEMA_ID, "evidence": paths.rel(evidence),
           "published": {k: published.get(k) for k in
                         ("mean", "n", "ci95", "ci95_season", "run_digest")},
           "per_fixture_csv": from_csv, "shard_ledgers": from_ledger,
           "checks": checks, "tolerance": tolerance,
           "PASS": bool(ran) and all(c["PASS"] for c in ran)}
    if not out["PASS"]:
        raise MergeIncomplete(
            f"the published verdict does not re-derive from its own evidence: "
            f"{[c for c in checks if not c.get('PASS', True)]}. Either the "
            "committed files disagree with the ledger they were projected from, "
            "or nothing was available to check them against — and a verdict "
            "nobody can recompute is exactly what reports/evidence/ exists to "
            "prevent.")
    return out


# ==========================================================================
# 16. THE HARNESS-HASH FREEZE OF §6
# ==========================================================================

_HEX64 = re.compile(r"\b([0-9a-f]{64})\b")


def harness_freeze_status(sources: Sequence[Path] | None = None,
                          ) -> dict[str, Any]:
    """Has §6 step 2's follow-up commit landed, and does it describe THESE bytes?

    §6 step 2: the commit appends a table of file, line count and SHA-256 for
    every harness file plus the frozen membership digests, carrying 07b5871's
    sentence — *if any hash differs at the time the run is executed, it is not
    the run this document preregisters*. This function reads that record and
    compares it with the files on disk. It asserts nothing about itself: an
    unfrozen harness is a fact to report, and the refusal is
    :func:`require_harness_freeze`'s job.
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
               "commit has not landed, and step 3 says not one real fit of this "
               "experiment runs before it does")
    elif differs:
        why = (f"the recorded digest for {differs} differs from the file on "
               "disk: if any hash differs at the time the run is executed, it is "
               "not the run this document preregisters (§6 step 2). §6 step 4 "
               "requires a dated note appended BEFORE the change, with the "
               "hashes reissued")
    else:
        why = ""
    return {"frozen": not missing and not differs, "where": where,
            "files": found, "missing": missing, "why": why,
            "schema": SCHEMA_ID}


def freeze_block(corpus: pd.DataFrame | None = None,
                 played: pd.DataFrame | None = None,
                 ledger: dict[str, set[str]] | None = None,
                 table: Sequence[dict[str, Any]] | None = None,
                 *, pre_freeze_runs: Sequence[str] | None = None) -> str:
    """§6 step 2's follow-up commit, RENDERED BY THE HARNESS'S OWN CODE.

    The document asks that commit for a hash table over every harness file —
    "file, line count, SHA-256" — the schema identifier, the frozen membership
    digests "each serialised canonically and hashed, recomputed by the harness's
    own code from the pinned artifacts", and an enumeration of every pre-freeze
    run.

    Every one of those is computed here, so the freeze commit is a paste rather
    than a transcription. A transcribed digest is a digest with a typo in it,
    and §6's whole point is that "the design was fixed first" be checkable by a
    reader who runs `shasum` — which it is not if the recorded hash and the file
    disagree because somebody's clipboard truncated a hex string.

    This function READS the pinned artifacts and fits nothing.
    """
    corpus = load_corpus() if corpus is None else corpus
    played = load_archive() if played is None else played
    ledger = load_walk_ledger() if ledger is None else ledger
    if table is None:
        from epl import baseline

        table = table_cells(baseline.load_matches(), played)
    digests = membership_digests(corpus, played, ledger, table=table)

    lines = [
        "### §6 step 2 — the harness hashes and the frozen membership",
        "",
        f"Schema identifier: `{SCHEMA_ID}`. Recomputed by "
        "`python -m epl.evwiden --freeze-block` from the pinned artifacts of "
        "§0.1, whose digests are unchanged.",
        "",
        "| file | lines | SHA-256 |",
        "|---|---:|---|",
    ]
    for name in HARNESS_FILES:
        path = paths.REPO_ROOT / name
        lines.append(f"| `{name}` | {len(path.read_text().splitlines())} | "
                     f"`{sha256_file(path)}` |")
    lines += [
        "",
        "| membership | count | SHA-256 of the canonical serialisation |",
        "|---|---:|---|",
    ]
    rows = (("the thin fixtures (§2.3)", "thin", "thin"),
            ("the treated fixtures (§2.3)", "treated", "treated"),
            ("the newly-flagged club-cutoff cells (§2.2)", "new_cells",
             "new_cells"),
            ("the fit openings (§2.3)", "fit_openings", "fit_openings"),
            ("the treated table cells (§3.3)", "table_treated", "table_treated"),
            ("the untouched table cells (§3.3)", "table_untouched",
             "table_untouched"))
    for label, count_key, digest_key in rows:
        count = digests["counts"].get(count_key)
        digest = digests["digests"].get(digest_key)
        if count is None or digest is None:
            continue
        lines.append(f"| {label} | {count} | `{digest}` |")
    lines += [
        f"| the membership as one object | — | "
        f"`{digests['digests']['membership']}` |",
        "",
        "Pre-freeze runs, enumerated (§5.3 — none of them a fit, none of them "
        "able to enter an estimand):",
        "",
    ]
    for run in (pre_freeze_runs or (
            "`python -m epl.evwiden --membership` and `--plan` — read the "
            "pinned corpus, archive and ledger; compute the digests above",
            "`python -m epl.evwiden --canary --no-results-canary --dir "
            "<scratch>` — §5.3's evidence canary on the real archive, store "
            "built in a temporary root",
            "`pytest epl/tests/test_evwiden.py` — the synthetic corpora, plus "
            "the `@pinned` tests that re-derive the census and the membership",
            "one `Engine(...)` construction plus `fit_points`, `enlarged`, "
            "`assert_cutoff_clean` and `assert_point_in_time` at the first "
            "opening — the whole of `Engine.fit` EXCEPT the call to "
            "`dcfit.fit_epl`, run to check the wiring. No sampler ran and the "
            "shared point-in-time store was byte-identical afterwards",
    )):
        lines.append(f"* {run}")
    lines.append("")
    lines.append("*If any hash differs at the time the run is executed, it is "
                 "not the run this document preregisters.*")
    return "\n".join(lines) + "\n"


def require_harness_freeze(sources: Sequence[Path] | None = None,
                           ) -> dict[str, Any]:
    """Refuse anything that would score fits taken before §6's freeze commit.

    Raised as the base :class:`EvWidenError`: §7 pre-states this condition as an
    invalidation but §5.1 never gave it a typed name, and this module does not
    invent one after the fact.
    """
    status = harness_freeze_status(sources)
    if not status["frozen"]:
        raise EvWidenError(
            "the harness-hash freeze of §6 is not in place — " + status["why"]
            + ". The harness may be audited on SYNTHETIC corpora to a scratch "
            "directory, but its result may not be merged or scored until the "
            "hash table and the membership digests are committed.")
    return status


# ==========================================================================
# 17. THE DETACHED LAUNCH — §2.4's runner, GENERATED rather than committed
# ==========================================================================

def launch_script(directory: Path | str | None = None, shards: int = 4, *,
                  python: str = ".venv/bin/python",
                  table: bool = True, merge: bool = True) -> str:
    """The nohup'd runner, as text. §6 names two harness files and this is not
    a third.

    A loose ``run_evwiden.sh`` would be code whose bytes nothing hashes, sitting
    outside the §6 hash table while being able to change which shards run and in
    what order. Generating it from the hashed module instead makes the launcher
    a function of the frozen harness, and the launcher itself lands under
    ``data/epl/fit/evwiden/`` — inside §6's write set.

    Four things §2.4 pre-states, all of them here rather than in a habit:

    * ``OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1``, exported
      BEFORE python starts, so the pin reaches the BLAS pool at load;
    * ``python -u``, so a detached run's log is readable while it runs;
    * **sequential shards** — the featpanel ``.tmp`` rename race in the locked
      path crashes parallel ones, and the fix is held for lock-v11;
    * **waited per PID, never a bare ``wait``** — a bare wait returns the status
      of the last job and a failed shard would sail past it, which is precisely
      the "failed shard poisons the merge" guarantee going quiet.
    """
    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    rel_dir = paths.rel(directory) if directory.is_absolute() else str(directory)
    shards = max(1, int(shards))
    lines = [
        "#!/bin/sh",
        "# GENERATED by `python -m epl.evwiden --script`. Do not edit: §6 names",
        "# epl/evwiden.py and epl/tests/test_evwiden.py as the harness files, and",
        "# this launcher's bytes are a function of theirs.",
        "#",
        "# Launch DETACHED, from a script file and never a stdin heredoc — macOS",
        "# spawn re-imports <stdin> and kills the gate's parallel leg:",
        f"#     nohup sh {rel_dir}/{LAUNCH_NAME} > {rel_dir}/run.log 2>&1 &",
        "set -u",
        f"cd {paths.REPO_ROOT}",
        "export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1",
        "export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1",
        "export PYTHONPATH=src:.",
        f'PY="{python}"',
        f'DIR="{rel_dir}"',
        'mkdir -p "$DIR"',
        "",
        "run_step() {",
        "  # one step, one child, one PID, waited on by that PID. A bare `wait`",
        "  # returns the LAST job's status and would let a failed shard through.",
        '  label="$1"; shift',
        '  "$@" > "$DIR/$label.log" 2>&1 &',
        "  pid=$!",
        '  if wait "$pid"; then',
        '    echo "[launch] $label ok"',
        "  else",
        '    status=$?',
        '    echo "STOP: $label exited $status — see $DIR/$label.log."',
        '    echo "A failed fit poisons its shard and a failed shard poisons the merge."',
        '    exit 2',
        "  fi",
        "}",
        "",
        '# RUN_ORDER, enforced by the module too: the canaries are a precondition',
        '# of the run and the identity control runs first among the fits.',
        'run_step canary $PY -u -m epl.evwiden --canary --dir "$DIR"',
        "",
        "# §2.4: SEQUENTIALLY. Parallel shards crash on the featpanel .tmp rename",
        "# race in the locked path.",
    ]
    for i in range(shards):
        lines.append(
            f'run_step shard_{i:02d}_of_{shards:02d} $PY -u -m epl.evwiden '
            f'--run --shard {i}/{shards} --dir "$DIR"')
    if table:
        lines += ["", "# §3.3's table leg: 35 fits, 70 runs of 20,000 seasons.",
                  'run_step table $PY -u -m epl.evwiden --table --dir "$DIR"']
    if merge:
        lines += ["", "# The merge refuses an incomplete or poisoned shard set,",
                  "# and writes the §6 evidence files whichever way it falls.",
                  f'run_step merge $PY -u -m epl.evwiden --merge --shards '
                  f'{shards} --evidence --dir "$DIR"']
    lines += ["", 'echo "[launch] done"', ""]
    return "\n".join(lines)


def write_launch_script(directory: Path | str | None = None, shards: int = 4,
                        **kwargs) -> Path:
    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LAUNCH_NAME
    path.write_text(launch_script(directory, shards, **kwargs))
    path.chmod(0o755)
    return path


# ==========================================================================
# 18. THE CLI
# ==========================================================================

def _plan(corpus: pd.DataFrame, played: pd.DataFrame,
          ledger: dict[str, set[str]], shards: int,
          directory: Path) -> dict[str, Any]:
    frozen = membership_digests(corpus, played, ledger)
    points = fit_points(corpus, frozen["keys"]["fit_openings"])
    return {
        "schema": SCHEMA_ID, "arm": ARM_NAME, "e_star": E_STAR,
        "counts": frozen["counts"], "digests": frozen["digests"],
        "grid": frozen["grid"], "thin_by_season": frozen["thin_by_season"],
        "shards": {str(i): len(shard_points(points, i, shards))
                   for i in range(shards)},
        "run_order": list(RUN_ORDER), "directory": paths.rel(directory),
        "preconditions": {"canary": (directory / CANARY_NAME).exists()},
        "harness_freeze": harness_freeze_status(),
        "blas_threads": blas_threads(),
        "budget": {"fits": len(points),
                   "table_fits": EXPECTED_TABLE_CELLS,
                   "table_runs": 2 * EXPECTED_TABLE_CELLS,
                   "note": "§2.4: shards run SEQUENTIALLY and the run may not "
                           "be thinned — dropping cutoffs, fixtures, cells or "
                           "grid points to fit a clock is an amendment, not an "
                           "optimisation."},
    }


def _frozen_now() -> bool:
    """Has §6's freeze commit landed for THESE bytes? One place, one answer."""
    return bool(harness_freeze_status()["frozen"])


def _run_all_canaries(corpus: pd.DataFrame, played: pd.DataFrame,
                      ledger: dict[str, set[str]], *,
                      results_canary: bool = True) -> dict[str, Any]:
    """§5.3's canaries, in one record, all of them able to fail."""
    from epl import freeze
    from epl import fit as epl_fit
    from wcmodel.model.volatility_diagnostic import count_volatility_arm

    cfg = freeze.frozen_wcmodel_config()
    opens = block_openings(corpus)
    cutoff = sorted(opens.values())[len(opens) // 2]
    season = next(str(part["season"].iloc[0])
                  for b, part in corpus.groupby("block")
                  if opens[str(b)] == cutoff)
    clubs = sorted(set(corpus.loc[corpus["season"] == season,
                                  "home_key"].astype(str))
                   | set(corpus.loc[corpus["season"] == season,
                                    "away_key"].astype(str)))

    # The store root is a TEMPORARY directory, and that is a §6 requirement
    # rather than tidiness: `epl.fit.build_store` unlinks and rewrites the
    # shared `data/epl/fit/store/results.parquet` whenever the row set differs,
    # so building a store from the CORRUPTED frame under the default root would
    # overwrite production state this experiment is not allowed to write.
    with tempfile.TemporaryDirectory(prefix="evwiden-canary-") as scratch:
        roots = {}

        def provisional_fn(frame: pd.DataFrame) -> set[str]:
            root = Path(scratch) / f"store{len(roots)}"
            roots[len(roots)] = root
            store = epl_fit.build_store(frame, root=root)
            arm = count_volatility_arm(store, cutoff, clubs, config=cfg)
            return set(arm.loc[arm["volatility_flag"]
                               | arm["few_games_flag"], "team"])

        record: dict[str, Any] = {
            "schema": SCHEMA_ID, "cutoff": str(pd.Timestamp(cutoff).date()),
            "season": season,
            "evidence": evidence_canary(played, cutoff, clubs,
                                        provisional_fn=provisional_fn),
            "blas_threads": blas_threads(),
        }
    if results_canary:
        record["results"] = run_canary()
    record["PASS"] = all(bool(v.get("PASS")) for v in record.values()
                         if isinstance(v, dict) and "PASS" in v)
    record["results_canary_run"] = bool(results_canary)
    return record


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", action="store_true",
                    help="print the membership, the digests and the shard "
                         "sizes; fits nothing")
    ap.add_argument("--membership", action="store_true",
                    help="print §6 step 2's frozen membership digests, "
                         "recomputed from the pinned artifacts; fits nothing")
    ap.add_argument("--canary", action="store_true",
                    help="§5.3's canaries; the first thing in RUN_ORDER")
    ap.add_argument("--run", action="store_true",
                    help="Arm A's fits — the identity control runs first, "
                         "inside every fit")
    ap.add_argument("--table", action="store_true",
                    help="§3.3's table-retro leg: 35 cells, both arms")
    ap.add_argument("--merge", action="store_true",
                    help="verify every shard, then compute the estimand")
    ap.add_argument("--verify", action="store_true",
                    help="re-derive the published estimand from the committed "
                         "evidence and the shard ledgers; changes nothing")
    ap.add_argument("--evidence", action="store_true",
                    help="write §6's evidence files under reports/evidence/")
    ap.add_argument("--freeze-block", dest="freeze_block", action="store_true",
                    help="print §6 step 2's hash table and membership digests, "
                         "recomputed from the pinned artifacts; fits nothing")
    ap.add_argument("--script", action="store_true",
                    help="write the detached-launch runner into the run "
                         "directory and print the nohup line")
    ap.add_argument("--shard", default="0/1",
                    help="i/N — this worker's slice of the fit points")
    ap.add_argument("--shards", type=int, default=1,
                    help="how many shards the merge must find")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dir", dest="directory", default=None,
                    help="the run directory: the canary record and the shard "
                         f"ledgers (default {paths.rel(EVWIDEN_DIR)})")
    ap.add_argument("--table-ledger", default=None)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--no-results-canary", action="store_true",
                    help="skip `walkforward.point_in_time_canary` (it refits); "
                         "the evidence canary still runs and still refuses")
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        index, count = (int(x) for x in str(args.shard).split("/"))
    except ValueError:
        print(f"STOP: --shard must be i/N, not {args.shard!r}", flush=True)
        return 2

    directory = Path(args.directory) if args.directory else EVWIDEN_DIR
    table_ledger = (Path(args.table_ledger) if args.table_ledger
                    else (TABLE_LEDGER if directory == EVWIDEN_DIR
                          else directory / TABLE_LEDGER.name))

    try:
        if args.script:
            path = write_launch_script(directory, max(count, args.shards))
            print(json.dumps({
                "written": paths.rel(path),
                "launch": f"nohup sh {paths.rel(path)} > "
                          f"{paths.rel(directory)}/run.log 2>&1 &",
                "note": "§2.4: a detached run goes through a nohup'd SCRIPT "
                        "FILE, never a stdin heredoc.",
            }, indent=2))

        if args.freeze_block:
            print(freeze_block(), end="")

        if args.plan or args.membership:
            corpus, played = load_corpus(), load_archive()
            ledger = load_walk_ledger()
            assert_ledger_covers(corpus, ledger)
            if args.membership:
                out = membership_digests(corpus, played, ledger)
                out.pop("keys", None)
                print(json.dumps(out, indent=2, default=str))
            if args.plan:
                print(json.dumps(
                    _plan(corpus, played, ledger, max(count, args.shards),
                          directory), indent=2, default=str))

        if args.canary:
            _guard_ledger_location(directory / CANARY_NAME, _frozen_now())
            corpus, played = load_corpus(), load_archive()
            ledger = load_walk_ledger()
            record = _run_all_canaries(
                corpus, played, ledger,
                results_canary=not args.no_results_canary)
            write_canaries(record, directory / CANARY_NAME)
            print(json.dumps({k: v for k, v in record.items() if k != "detail"},
                             indent=2, default=str))

        if args.run:
            corpus, played = load_corpus(), load_archive()
            ledger = load_walk_ledger()
            assert_ledger_covers(corpus, ledger)
            check_corpus_scores(corpus)
            frozen = harness_freeze_status()
            require_run_preconditions(directory,
                                      require_results=bool(frozen["frozen"]))
            assert_blas_pinned("the evidence-widening sweep")
            digests = membership_digests(corpus, played, ledger)
            points = shard_points(fit_points(corpus,
                                             digests["keys"]["fit_openings"]),
                                  index, count)
            if args.limit:
                points = points[:args.limit]
            ledger_path = directory / shard_name(index, count)
            # Guard BEFORE the engine: building the store and the anchor costs
            # real time, and a run that is going to be refused should be refused
            # before it spends it.
            _guard_ledger_location(ledger_path, bool(frozen["frozen"]))
            if not frozen["frozen"]:
                print("[evwiden] WARNING: " + frozen["why"] + " — every row of "
                      "this run is stamped harness_frozen: false and the merge "
                      "will refuse to score it.", flush=True)
            grid_treated = membership(corpus, played, ledger,
                                      e_star=max(E_GRID)).treated
            with Engine(corpus, played, ledger=ledger) as engine:
                out = run_fits(points, ledger_path, corpus, engine=engine,
                               grid_treated=grid_treated,
                               shard_id=f"{index}/{count}",
                               harness_frozen=bool(frozen["frozen"]))
            print(json.dumps(out, indent=2, default=str))

        if args.table:
            from epl import baseline

            frozen = harness_freeze_status()
            _guard_ledger_location(table_ledger, bool(frozen["frozen"]))
            require_run_preconditions(directory,
                                      require_results=bool(frozen["frozen"]))
            assert_blas_pinned("the table-retro leg")
            matches = baseline.load_matches()
            cells = table_cells(matches)
            if args.limit:
                cells = cells[:args.limit]
            out = run_table(cells, table_ledger,
                            harness_frozen=bool(frozen["frozen"]))
            print(json.dumps(out, indent=2, default=str))

        if args.merge or args.verify:
            corpus, played = load_corpus(), load_archive()
            ledger = load_walk_ledger()
            table_out = None
            if table_ledger.exists():
                from epl import baseline

                cells = table_cells(baseline.load_matches())
                rows = load_table_ledger(table_ledger, expected=cells)
                scored = score_table(rows, n_boot=args.n_boot,
                                     expected_cells=EXPECTED_TABLE_CELLS)
                table_out = {"scored": scored, "gate": table_gate(scored),
                             "rows": rows}
            if args.verify and not args.merge:
                print(json.dumps(verify(directory, shards=args.shards,
                                        n_boot=args.n_boot), indent=2,
                                 default=str))
                return 0
            result = merge(shards=args.shards, directory=directory,
                           corpus=corpus, played=played, ledger=ledger,
                           table=(None if table_out is None
                                  else {"gate": table_out["gate"],
                                        "scored": {k: v for k, v in
                                                   table_out["scored"].items()
                                                   if k != "per_cell"}}),
                           n_boot=args.n_boot, write=args.merge)
            if args.evidence:
                merged = [r for shard in range(args.shards)
                          for r in load_ledger(
                              directory / shard_name(shard, args.shards))]
                written = write_evidence(
                    result, merged,
                    None if table_out is None else table_out["rows"])
                result["evidence"] = written
            summary = {k: v for k, v in result.items()
                       if k not in ("membership", "canaries", "harness_freeze",
                                    "table")}
            print(json.dumps(summary, indent=2, default=str))

    except EvWidenError as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
