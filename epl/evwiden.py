"""EVIDENCE-MASS WIDENING. Is the predicate that decides predict-time widening
keyed on the wrong quantity?

This module executes the design preregistered in
``reports/epl_widening_prereg_v3.md`` — **v3, the sole law** — and computes the
estimand fixed in its §2.3. It chooses nothing. The corpus, the archive, the
walk-forward ledger and the configuration are pinned by digest; the rule, its
one constant (``e* = 10.0``), the grid, the four-gate adoption rule, the refusal
semantics and the scope were written down before this file existed; and §4.5
makes adoption an owner ruling that no script may take.

**v1 AND v2 ARE LINEAGE AND DECIDE NOTHING.**
``reports/epl_widening_prereg.md`` (v1) was invalidated on 2026-08-28 under
v1's own R-B6: two real ADVI fits occurred on the pinned archive through
protected :class:`epl.simretro.ArchiveRunner` during v1's conformance work, and
the parity leg is a mandatory leg of this experiment.
``reports/epl_widening_prereg_v2.md`` was **defeated by the one pass it
authorised for exactly that purpose**: its §8.2 pass 7 ran on 2026-08-28 and
measured three of its thirty-five mandatory parity cells as UNPRICEABLE on the
shipped stack, all three ``excluded_mass_ceiling`` against amendment A1's 0.02
ceiling. v2 pre-stated, before that pass ran, that one unpriceable cell is
enough — the document cannot be run as written and the remedy is a new
preregistration, "not a quiet narrowing of the 35 cells here". So v2 was closed
with a dated note, nothing else in it changed, and v3 carries the whole of its
law against the MEASURED census.

**THE CENSUS, WHICH IS WHY THIS MODULE'S TABLE CONSTANTS ARE WHAT THEY ARE**
(v3 §0.6): 32 priceable cells, 15 treated, 17 untouched; the three excluded are
:data:`EXCLUDED_CELLS` and they are excluded by MEASUREMENT and by nothing a
caller can name. MW6 is 7 of 7 and remains the ONLY all-treated label, so §4.1's
ground for naming it the deciding horizon survives a measurement that was under
no obligation to spare it.

**v3's NO-FIT CLOCK STARTS AT v3's OWN FREEZE COMMIT** (§8.3), and **v3
authorises no pre-freeze pass that fits or simulates**: the one question such a
pass existed to answer has been answered. The two v1 fits and pass 7's
thirty-five preceded this document; §8.8 names them inside the attestation
rather than beside it and §2.4 counts them, and §8.7 binds changes to hashed
files after the first real fit **of this document** — which §8.4 makes the
results canary of step 1.

THE RULE, ONCE (§2.1)::

    provisional'(C) = provisional_incumbent(C) u { t : e(t, C) < 10.0 }

ADD, never REPLACE. Binary, never continuous. ``alpha`` stays 0.5 and the mix is
the incumbent one, so a treated fixture is mechanically indistinguishable from a
fixture the incumbent predicate already widens.

WHAT THE TWO ARMS ARE (§2.3). Both arms are computed from
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

WHAT THIS FILE MAY NOT DO (§8.3). It writes ``data/epl/fit/evwiden*``,
``data/epl/sim/evwiden*`` and the evidence files under ``reports/evidence/``,
and nothing else. It authors no verdict prose — ``reports/epl_widening_result.md``
is a human act after the numbers exist, required by §4.4 whichever way they
fall. It does not touch the corpus, the archive, the walk-forward ledger or
``data/epl/sim/retro_r1.jsonl``, all of which are read-only to this experiment.
And it does not run the preregistered experiment before the harness-hash freeze
commit of §8.3 exists: :func:`harness_freeze_status` reads that commit's own
record and :func:`merge` refuses without it, because a run that precedes the
freeze is, by §10, not the run this document preregisters.

PRE-FREEZE CONTACT WITH THE REAL ARTIFACTS, DISCLOSED. §8.2 states one rule and
v2 carries no other clause to read against it: **pre-freeze, no harness code
fits and no harness code simulates; reading the pinned artifacts is permitted,
is read-only, and is enumerated by name in the freeze commit.**
:data:`PRE_FREEZE_RUNS` carries v3's six authorised passes, **all six
read-only**, and :data:`PRIOR_PASSES` carries v2 §8.2 pass 7 as named prior
HISTORY — the pass that produced §0.6's census, run under v2's authorisation on
2026-08-28 and not repeatable here. :func:`freeze_block` prints both, in two
sections, so the enumeration stays complete without pretending the pass was v3's
to authorise. "Read-only" is a property of code here and not
of intent: :func:`read_only_store` is the single route to a point-in-time store
and it raises :class:`StoreNotBuilt` rather than building one.

NOT ONE FIT ON THE REAL ARCHIVE PRECEDES THE FREEZE, AND THE GUARD IS NOT THE
DIRECTORY. v1's preamble claimed the harness's guards made a pre-freeze
delta impossible; v1's second review withdrew that sentence as FALSE, because
:func:`_guard_ledger_location` is keyed to the run directory and a ``--dir``
outside the defaults escaped it. :func:`assert_may_fit` is keyed to the freeze
state and to the ARTIFACT IDENTITY being read — the pinned archive's own
module-level digest and the pinned corpus's frozen shape — and it gates
:class:`Engine`, :class:`TableRunner`, :class:`ParityRunner` and the results
canary. A synthetic world fits freely; the pinned one does not, and no ``--dir``
moves that. The directory guard is kept beside it, because a pre-freeze
``canary.json`` in the run directory is still what a later ``--run`` reads as
"the canary passed".

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
# ACTUALLY has on every ledger row (§7.2) and :func:`assert_blas_pinned` refuses
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
import shutil                                                     # noqa: E402
import socket                                                     # noqa: E402
import subprocess                                                 # noqa: E402
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
    "assert_table_identity", "assert_provisional_fields",
    "particle_tallies", "assert_tally_binds_the_matrix", "paired_mc_bootstrap",
    "sampler_digest", "substantive_digest", "plan_state",
    "ParityRunner", "run_parity_oracle", "assert_native_parity", "simulate_arm",
    "MC_BOOT", "MC_SEED", "MW6_LABEL", "POINT_GATE_LABELS", "SHARDS",
    "write_evidence", "verify", "freeze_block", "harness_freeze_status",
    "claim_sequence_step",
    "require_harness_freeze",
    "power_simulation", "power_structure", "power_reproduces",
    "committed_power_run",
    "bootstrap_shortcut_matches", "implementation_report",
    # `write_conformance_artifact` is deliberately ABSENT (adjudication F22):
    # §8.5's artifact is a record of what a pytest SESSION did, and a writer
    # exported as part of this module's public surface is an invitation to
    # produce one without a session. It is called by the committed pytest
    # session fixture and by nothing else.
    "conformance_row", "pytest_session_id",
    "conformance_artifact_status", "assert_conformance_artifact",
    "CONFORMANCE_ROWS", "conformance_test_id",
    "assert_implements_document", "assert_may_fit", "evidence_object",
    "assert_manifest_complete", "MANIFEST_PATHS",
    "launch_script", "main",
    # §8.6's public-surface closure, and the surfaces it stands over
    "feasibility_status", "assert_feasibility_permits_a_freeze",
    "assert_seam_allowed", "archive_provenance", "is_pinned_archive",
    "is_derived_from_pinned_archive", "frozen_table_constants",
    "unanimity", "unanimity_is_valid", "iv_c_verdict",
    # §3.2's three checks, extracted so §8.5's L12 executes them
    "assert_identity_control", "assert_untreated_unmoved",
    "assert_pass_two_three_agree",
    # §8.2's passes 4 and 7
    "partial_engine_pass",
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

#: §0.1's repaired pin. `epl.freeze.frozen_wcmodel_config()` loads the LIVE
#: `config/config.yaml` and overlays only the frozen EPL Elo block, so the
#: superseded three-condition check bound `epl/config_frozen.json`, the realised
#: seed and the realised widening block AND NOTHING ELSE — not the decay
#: half-life that DEFINES `e`, not the volatility window `e* = 10.0` is taken
#: from, not the likelihood, not the ADVI block. Drift there would change `e`,
#: the posteriors or reproducibility while the documented refusal passed.
#:
#: The value is the SHA-256 of `json.dumps(frozen_wcmodel_config(),
#: sort_keys=True, default=str)`, computed 2026-08-27 under the pinned frozen
#: file and pinned by §0.1.
REALISED_CONFIG_SHA256 = \
    "78a51cd92c48838a57e3d6832b7661aad7a5b231425572214a067c2a35edbdcd"

#: §2.3's primary interval: the project's own block bootstrap, percentile, at
#: the frozen resampling seed. §2.3 requires BOTH blockings and §4.1 gates on
#: both.
BOOTSTRAP_SEED = 20260814
N_BOOT = 10_000
ALPHA = 0.05

#: §2.1's ONE FROZEN CONSTANT. It is `config/config.yaml`'s
#: `elo.volatility_window: 10` — the ten-match window this codebase already uses
#: twice as its operational definition of the informative recent past. It is not
#: tuned, not swept, and §10 makes moving it an invalidation.
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

#: §4.1 (i). §4.2 renames it and §4.2 rebuilds its justification: this is an
#: **invented thin-population threshold**, not the house bar applied. It takes
#: its numeral from `reports/epl_improved.md` §5.2's model-change bar, which was
#: set over a full evaluation window; this one is set over 85 fixtures chosen to
#: be where the effect is largest, a difference in system-level materiality of
#: about 26.8x. **The numeral is borrowed, the authority is not.**
#:
#: §4.2 withdraws v1's ground 1 as a unit error — `-0.0016` is a mean
#: RPS demand and `0.0032 / 0.0139 / 0.0229` are absolute probability shifts —
#: and rebuilds it in RPS against RPS: the bar sits at about 2.2 standard errors
#: of its own estimator under the optimistic scenario and INSIDE one standard
#: error under both pessimistic ones. Ground 3 is "Law, not cadence" and claims
#: nothing more: the product value of this rule is not quantified anywhere in
#: this repository and this experiment does not quantify it. Ground 4 is the
#: concession — a passing result is -0.000037 pooled over the corpus, smaller in
#: magnitude than the +0.000075 re-seed shift.
ADOPT_DELTA = -0.0010

#: §4.1 (iv) as §4.1 repairs it — the per-horizon tolerance, invented from R1's
#: own recorded scale (paired dc-family TRPS differences of "two parts in a
#: thousand" on a TRPS of order 0.08, i.e. ~2e-4 PER CELL) and disclosed as
#: invented. The superseded gate applied that per-cell scale to an average over
#: 32 cells of which 17 are exact zeros, which permitted about +0.00042667 of
#: average degradation across the 15 treated cells; the repaired gates apply it
#: to treated-cell means directly, 2.13x tighter. (The 16-cell / 2.19x figures
#: this comment carried were v2's, computed over v2's 35-cell census; §4.3's
#: arithmetic is 0.0002 x 32/15 = 0.00042667, ratio 32/15 = 2.1333.
#: Adjudication F18.)
TABLE_TOLERANCE = 0.0002

#: §4.1's named horizon. MW6 is the only one of the five labels at which EVERY
#: cell is treated, so it is the only horizon at which the do-no-harm question
#: is asked with no structural zero in the denominator; and the early-season
#: table forecast is where a thin-evidence club's dispersion is widest. Named
#: before any fit exists, and §10 makes replacing it after any table run an
#: invalidation.
MW6_LABEL = "MW6"

#: §4.1 (iv-b)'s point-gate labels, and the structural zero that decides nothing.
POINT_GATE_LABELS: tuple[str, ...] = ("MW0", "MW3", "MW10")
STRUCTURAL_ZERO_LABEL = "MW19"

#: §4.1's census, recomputed by the read-only pass §8.2 authorises: how many of
#: each label's seven cells the rule treats. MW19 holds zero and enters nothing.
EXPECTED_TREATED_BY_LABEL = {"MW0": 2, "MW3": 2, "MW6": 7, "MW10": 4, "MW19": 0}

#: v3 §3.3's per-label CELL census — **a pin v2 never needed**, because v2's
#: labels held seven cells each and v3's do not. It is load-bearing rather than
#: decorative: §4.1's ground for the deciding horizon is "MW6 is the only label
#: at which EVERY cell is treated", and after §0.6 that is a statement about two
#: censuses. A label could become all-treated by losing its untouched cells,
#: which is not the same fact and would not carry the same ground.
EXPECTED_CELLS_BY_LABEL = {"MW0": 5, "MW3": 6, "MW6": 7, "MW10": 7, "MW19": 7}

#: v3 §0.6: the three cells v2 §8.2 pass 7 measured as UNPRICEABLE, named by key
#: so that the population is decidable from the document rather than from a
#: gitignored file. Every one is a Manchester City fixture against a promoted
#: side and every one refuses with the same typed kind.
EXCLUDED_CELLS: tuple[str, ...] = ("2019/20|MW0", "2020/21|MW0", "2023/24|MW3")

#: ...and what the protected code said about each, so a reader can check the
#: exclusion rather than take it. `excluded_mass` is the particle-mean mass the
#: 10-goal truncation discards; `ceiling` is amendment A1's 0.02.
EXCLUDED_CELL_DETAIL: dict[str, dict[str, Any]] = {
    "2019/20|MW0": {"refusal_kind": "excluded_mass_ceiling",
                    "fixture": "man_city v sheffield_united",
                    "excluded_mass": 0.0234, "ceiling": 0.02},
    "2020/21|MW0": {"refusal_kind": "excluded_mass_ceiling",
                    "fixture": "man_city v leeds",
                    "excluded_mass": 0.0216, "ceiling": 0.02},
    "2023/24|MW3": {"refusal_kind": "excluded_mass_ceiling",
                    "fixture": "man_city v luton",
                    "excluded_mass": 0.0328, "ceiling": 0.02},
}

#: v3 §3.3's SCHEDULE, cell by cell: `(season, cutoff_label, cutoff date,
#: treated clubs)` for each of the thirty-two priceable cells, recomputed from
#: the pinned artifacts by §8.2's read-only pass and frozen here.
#:
#: The adjudication of 2026-08-29 (F6, V3-B1) made this a pin rather than a
#: derivation: "the active aggregate constants are right, but no single
#: production assertion establishes the frozen exact schedule, unique keys,
#: cutoff dates, and treated-club membership. `assert_table_census` permits a
#: bogus same-label season or altered cutoff/treated club [...] This defeats the
#: core v3 promise that the experiment is exactly the measured 32, not merely
#: any 32 with the same aggregate census."
#:
#: Every aggregate this document pins — 32/15/17, both per-label censuses, the
#: three exclusions, MW6's all-treated ground — is a consequence of this table
#: and is checked against it. A cell substituted for another at the same label,
#: a cutoff moved by a week, or a treated club exchanged for a neighbour leaves
#: every one of those aggregates intact, and none of them survives this.
FROZEN_TABLE_SCHEDULE: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("2019/20", "MW3", "2019-08-31", ("aston_villa", "norwich")),
    ("2019/20", "MW6", "2019-09-28",
     ("aston_villa", "norwich", "sheffield_united")),
    ("2019/20", "MW10", "2019-11-02", ("sheffield_united",)),
    ("2019/20", "MW19", "2020-01-01", ()),
    ("2020/21", "MW3", "2020-10-17", ()),
    ("2020/21", "MW6", "2020-11-02", ("leeds",)),
    ("2020/21", "MW10", "2020-12-07", ()),
    ("2020/21", "MW19", "2021-02-02", ()),
    ("2021/22", "MW0", "2021-08-13", ()),
    ("2021/22", "MW3", "2021-09-11", ()),
    ("2021/22", "MW6", "2021-10-16", ("brentford",)),
    ("2021/22", "MW10", "2021-11-20", ("brentford",)),
    ("2021/22", "MW19", "2022-01-03", ()),
    ("2022/23", "MW0", "2022-08-05", ()),
    ("2022/23", "MW3", "2022-08-30", ()),
    ("2022/23", "MW6", "2022-09-16", ("nottm_forest",)),
    ("2022/23", "MW10", "2022-10-24", ()),
    ("2022/23", "MW19", "2023-01-23", ()),
    ("2023/24", "MW0", "2023-08-11", ("sheffield_united",)),
    ("2023/24", "MW6", "2023-10-02", ("luton",)),
    ("2023/24", "MW10", "2023-11-04", ("luton",)),
    ("2023/24", "MW19", "2024-01-01", ()),
    ("2024/25", "MW0", "2024-08-16", ()),
    ("2024/25", "MW3", "2024-09-14", ()),
    ("2024/25", "MW6", "2024-10-19", ("ipswich",)),
    ("2024/25", "MW10", "2024-11-23", ("ipswich",)),
    ("2024/25", "MW19", "2025-01-06", ()),
    ("2025/26", "MW0", "2025-08-15", ("sunderland",)),
    ("2025/26", "MW3", "2025-09-13", ("sunderland",)),
    ("2025/26", "MW6", "2025-10-18", ("sunderland",)),
    ("2025/26", "MW10", "2025-11-22", ()),
    ("2025/26", "MW19", "2026-01-06", ()),
)


def schedule_tuple(cell: dict[str, Any]) -> tuple[str, str, str, tuple[str, ...]]:
    """One cell's place in :data:`FROZEN_TABLE_SCHEDULE`, from a cell or a row.

    Table cells and table-ledger rows carry the same four fields, which is why
    the same assertion can stand on the enumeration path and on every path that
    reads the ledger back.
    """
    return (str(cell["season"]), str(cell["cutoff_label"]), str(cell["cutoff"]),
            tuple(sorted(str(c) for c in (cell.get("treated_clubs") or ()))))


def table_schedule_digest(cells: Sequence[dict[str, Any]]) -> str:
    """The canonical digest of the exact schedule — cutoffs and clubs included.

    §8.3's frozen membership digests recorded `season|cutoff_label` alone, so
    two schedules differing only in a cutoff date or a treated club hashed the
    same and §8.6 condition (3)'s equality could not see the difference (F6).
    """
    return _digest_list("|".join((s, lab, cut, ",".join(clubs)))
                        for s, lab, cut, clubs in map(schedule_tuple, cells))


#: §5.3's season-block interval of the MW6 mean: `epl.score.block_bootstrap_ci`,
#: the seven season strings one cell per block, B = 10,000, alpha = 0.05, the
#: standard resampling seed. A seven-block percentile bootstrap has poor
#: coverage, is not claimed to have good coverage, and has the narrow job both
#: predecessors gave season blocks: to refuse a verdict carried by one season.
TABLE_CI_BLOCKS = 7

#: §5's paired particle bootstrap, pre-stated before any table run existed.
#: A2-N4 leaves B and the resampling seed to "the amendment that accompanies the
#: first run to report the bootstrap SE, before that run"; §5.3 is that
#: statement.
MC_BOOT = 2_000
MC_SEED = 20260827

#: §5 (P1): any deciding MC SE above a quarter of the tolerance leaves gate
#: (iv) UNRESOLVED. UNRESOLVED blocks adoption and can never grant one, which is
#: the direction that cannot be gamed.
MC_PRECISION_FRACTION = 0.25
MC_PRECISION_LIMIT = MC_PRECISION_FRACTION * TABLE_TOLERANCE      # 5e-5

#: §5 (P2)-(P5): a deciding comparison inside this many simulation standard
#: errors of its own boundary is UNRESOLVED.
MC_BOUNDARY_SIGMAS = 2.0

#: §5.4's P5 — the unanimity rule, frozen. "The whole of iv-c is recomputed on
#: `K = 200` particle-resampled tally sets. `rng = numpy.random.default_rng(
#: 20260828)`. [...] **P5 fires — and gate (iv) is UNRESOLVED — unless all 200
#: verdicts agree with each other and with the point-estimate verdict.** One
#: dissenting `k` is enough."
UNANIMITY_K = 200
UNANIMITY_SEED = 20260828

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
#: fixture at ANY grid `e*` — the union THROUGH `e* = 12` (that is,
#: `e* <= 12`); §3.2's control covers all 820
#: fixtures of those blocks.
EXPECTED_FIT_OPENINGS = 78
EXPECTED_CONTROL_FIXTURES = 820

#: §2.3's per-season split of the 85, pre-stated so a corpus that reshuffles
#: them is caught rather than averaged over.
EXPECTED_THIN_BY_SEASON = {"2019/20": 26, "2020/21": 11, "2021/22": 12,
                           "2022/23": 12, "2023/24": 12, "2024/25": 12}

#: v3 §3.3's table leg: `SEASONS` x `COMPARISON_CUTOFFS` MINUS §0.6's three
#: unpriceable cells, of which 15 change and 17 are unchanged BY CONSTRUCTION
#: and the harness must prove it. v2's were 35/16/19; the difference is the
#: census and not a choice, and exactly ONE treated cell was lost (2019/20 MW0).
EXPECTED_TABLE_CELLS = 32
EXPECTED_TABLE_TREATED = 15
EXPECTED_TABLE_UNTOUCHED = 17

#: §3.1's movement diagnostic prints the treatment beside the ADVI re-seed scale
#: from `reports/epl_walkforward.md`, so "did the treatment move more than
#: re-seeding does" is on the record whichever way the estimand lands.
RESEED_SCALE = {"per_match_mean": 0.0032, "per_match_p99": 0.0139,
                "per_match_max": 0.0229, "pooled_shift": 0.000075,
                "source": "reports/epl_walkforward.md"}

#: The schema identifier §8.3 step 2's freeze commit must name alongside the
#: hashes. **v3**, and the change of number is not cosmetic: v2's §3.3 required
#: a 35-cell oracle its own executed pass measured as unrunnable (§0.6), and a
#: harness that still stamped `epl-evwiden-2` on its rows would be claiming to
#: implement a document whose closing note says it cannot be run as written.
SCHEMA_ID = "epl-evwiden-3"

#: §8.3: "All code lands in `epl/evwiden.py` and `epl/tests/test_evwiden.py`".
#: The document names exactly two files and this module adds no third: the
#: detached-launch runner is GENERATED by :func:`launch_script` into the run
#: directory, so the launcher's bytes are a function of these hashed bytes
#: rather than a source file nobody hashed. The tests are in the list because a
#: test that stops asserting is a guard that stopped guarding.
HARNESS_FILES = ("epl/evwiden.py", "epl/tests/test_evwiden.py")

#: §8.4's frozen post-freeze sequence, in its own order, and **nothing else may
#: run on the real archive between the steps**. v1's `RUN_ORDER` was
#: `("canary", "run", "table", "merge")` — table BEFORE merge, and no
#: single-opening step at all — which is not the order the document names and
#: not the order the launcher should emit.
RUN_ORDER = ("canary", "single_opening", "shards", "merge",
             "parity_and_table")

#: The five completion markers, by file name, in order. "Each step **refuses
#: unless its predecessor's completion marker exists**; the refusal is
#: `SequenceViolation`."
SEQUENCE_STEPS: tuple[str, ...] = (
    "step1_results_canary", "step2_single_opening", "step3_shards",
    "step4_merge", "step5_parity")

#: §7.2's list, fixed in the document before any row existed: recorded on the
#: row, excluded from the canonical form and from every digest.
_VOLATILE = ("wall_seconds", "fit_seconds", "seconds", "shard_id",
             "started_at", "host")

#: Where the run writes. §8.3 closes the set to `data/epl/fit/evwiden*`,
#: `data/epl/sim/evwiden*`, the result document and the evidence files.
EVWIDEN_DIR = paths.FIT_DIR / "evwiden"
EVWIDEN_JSON = paths.FIT_DIR / "evwiden.json"
TABLE_DIR = paths.DATA_DIR / "sim" / "evwiden"
TABLE_LEDGER = TABLE_DIR / "table_cells.jsonl"
CANARY_NAME = "canary.json"
CANARY_JSON = EVWIDEN_DIR / CANARY_NAME
LAUNCH_NAME = "launch.sh"

#: §8.4: "Markers live at ONE FIXED LOCATION, `data/epl/fit/evwiden/sequence/`,
#: one JSON file per step." Fixed, and not under `--dir`: step 2 runs into a
#: SCRATCH directory and writes its marker to the preregistered run directory,
#: which only means anything if the marker location is not the run's own.
SEQUENCE_DIR = EVWIDEN_DIR / "sequence"

#: §9's evidence contract, regardless of outcome (ultra-review lesson 1: the
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

#: §9.3: the shard count is a PREREGISTERED CONSTANT, not a runtime choice.
#: §9's closing paragraph declared a list and then wrote a category — "each
#: shard ledger" names no count and no filename, while the shard count was a CLI
#: argument and the filename a format string, so the promised MANIFEST
#: membership was not decidable from the document. Four is the harness's own
#: default and it is fixed here: a run at any other shard count is not the run
#: this document preregisters. Shards still run SEQUENTIALLY (§2.4) — the
#: partition buys resumability and per-shard poisoning, not parallelism.
SHARDS = 4

#: v3 §8.2's SIX authorised pre-freeze passes, "authorised for this document,
#: prospectively": they are v3's own pre-freeze passes, to be run under v3
#: before v3's freeze commit. **All six are read-only** — v3 authorises no pass
#: that fits or simulates, because the one question such a pass existed to
#: answer has been answered (§0.6). The freeze block's list stays binding and
#: must be complete — an unenumerated pre-freeze pass is a protocol deviation
#: whether or not it touched anything.
PRE_FREEZE_RUNS: tuple[str, ...] = (
    "`python -m epl.evwiden --membership` and `--plan` — read the pinned "
    "corpus, archive and ledger; compute §2.2's cells, §2.3's population, "
    "§3.3's table cells and the digests above. Neither reaches "
    "`epl.fit.build_store`: §8.2's read-only store accessor opens the existing "
    "store parquet and raises `StoreNotBuilt` if it is absent",
    "`python -m epl.evwiden --canary --no-results-canary --dir <scratch>` — "
    "§7.3's evidence canary on the real archive, with any point-in-time store "
    "built in a `tempfile.TemporaryDirectory` and never under `paths.STORE_DIR`",
    "`pytest epl/tests/test_evwiden.py` — the synthetic corpora, the `@pinned` "
    "tests that re-derive the census, the grid table, the membership and the "
    "table cells, and §8.5's CONFORMANCE SCENARIO RUN: eighteen committed "
    "tests, one per row L1-L18, whose JSON report at "
    "`data/epl/fit/evwiden_conformance.json` is the artifact `--conformance` "
    "and `--freeze-block` consume. §8.5: the report may not be its own witness",
    "`python -m epl.evwiden --partial-engine` — one partial engine pass at the "
    "first opening (2019-08-09): construction, `fit_points`, the enlarged set, "
    "`assert_cutoff_clean` and `assert_point_in_time` — the whole of the fit "
    "path EXCEPT the call to `dcfit.fit_epl`. The Engine is constructed in a "
    "mode that CANNOT fit and its store comes from the read-only accessor, so "
    "no sampler runs; the pass compares the shared point-in-time store's bytes "
    "and mtime before and after and refuses if either moved",
    "`python -m epl.evwiden --freeze-block`, which reads the pinned artifacts "
    "to render §8.3's commit rather than have a human transcribe digests",
    "`python -m epl.evwiden --power`, which reads only the frozen SDs and the "
    "frozen structure recomputed from the pinned artifacts, and reproduces "
    "§6.3",
)

#: v3 §8.2: "The seventh pass is prior history and is enumerated as such." The
#: freeze block prints this in a HISTORY section, DISTINCT from the six above,
#: "so that the enumeration stays complete without pretending the pass was v3's
#: to authorise". §10 makes a feasibility pass run under THIS document — before
#: or after its freeze commit — an invalidation.
PRIOR_PASSES: tuple[str, ...] = (
    "**v2 §8.2 pass 7 — the `dc_native` parity feasibility pass.** Run on "
    "2026-08-28 under **v2's** authorisation, once, at HEAD `9adc3bc`, arm "
    "`dc_native` only, over all 35 of v2 §3.3's cells under `run_retro`'s own "
    "typed per-cell contract, quarantined outside the repository with its "
    "outputs deleted on close. Product: the CENSUS — 32 priceable, 3 "
    "unpriceable, all three `excluded_mass_ceiling` against amendment A1's "
    "0.02 ceiling (2019/20 MW0 man_city v sheffield_united 0.0234; 2020/21 MW0 "
    "man_city v leeds 0.0216; 2023/24 MW3 man_city v luton 0.0328). It carries "
    "no delta, no table cell, no arm comparison and no estimand. **v3 is "
    "SCOPED by it** (§0.6) and does not re-authorise it: the record is "
    "read-only here and §0.1 pins it by digest",
)

#: Where §8.3's freeze commit records the harness hashes. **v3 and only v3**:
#: §8.1 invalidates v1 under its own R-B6 and closes v2 over §0.6's census, and
#: both "decide nothing", so a guard that read either one's freeze block would
#: be binding this run to a document that cannot be run.
PREREG_PATH = paths.REPO_ROOT / "reports" / "epl_widening_prereg_v3.md"
PREREG_V2_PATH = paths.REPO_ROOT / "reports" / "epl_widening_prereg_v2.md"
PREREG_V1_PATH = paths.REPO_ROOT / "reports" / "epl_widening_prereg.md"

#: §4.5's home for an ADOPTION ruling, and **not** a freeze source. The
#: superseded guard accepted it alongside the prereg and then checked §8.6
#: condition (1)'s commit-and-ancestry against whichever file carried the hash
#: table — which is not the file the law names. §8.6 condition (1) names
#: `reports/epl_widening_prereg_v2.md` and nothing else, and §8.3 expressly
#: forbids appending an amendment-ledger cross-reference for this document.
AMENDMENTS_PATH = paths.REPO_ROOT / "reports" / "epl_sim_amendments.md"

#: §7.2's row contract, at the two levels the ledger carries it.
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
#: §2.3 rules exact equality AT THEM, and §10 makes widening the tolerance after
#: a mismatch an invalidation.
ROUND_DP = 8


# ==========================================================================
# 1. THE TYPED REFUSALS — §7.1, by name
# ==========================================================================

class EvWidenError(RuntimeError):
    """Anything this experiment refuses.

    §7.1 names the subclasses and this module does not invent one the document
    never wrote. A condition the preregistration pre-stated as an INVALIDATION
    but never gave an error name — §10's "a real-archive fit runs before the §8.3
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
    `{mechanism: c, strength: 0.5}`, or — §0.1's fourth condition — the REALISED
    configuration does not hash to `78a51cd9…`."""


class MembershipMismatch(EvWidenError):
    """The recomputed enumeration differs from the §8.3's frozen digests."""


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
    """`epl.walkforward.point_in_time_canary` did not pass (§7.3)."""


class EvidenceCanaryFailed(EvWidenError):
    """Either leg of the two-legged evidence canary failed (§7.3).

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
    """A ledger row lacks a field §7.2 requires."""


class RowConflict(EvWidenError):
    """Two rows share a key and disagree on a non-volatile field."""


class ShardFailed(EvWidenError):
    """A shard is missing, empty, or still carries a poison row."""


class MergeIncomplete(EvWidenError):
    """The merged key set is not exactly the pre-stated one."""


class TableMCImprecise(EvWidenError):
    """§5's paired Monte-Carlo error cannot be computed.

    §5.2 names the structural conditions: unequal per-particle season counts, or
    an ``n_particles`` that differs across the 15 deciding cells or between a
    cell's two arms, or a tally that fails either binding check of §5.1, or —
    §8.7 — **a tally file that is absent or fails its recorded digest**. Joint
    resampling is undefined without a common index space and this document will
    not approximate one.

    §5.4 is explicit that gate (iv) being left UNRESOLVED by the precision rule
    (P1)-(P5) is **not** a refusal and raises nothing: UNRESOLVED is a published
    verdict, it blocks adoption, and conflating the two would make the harness
    raise on a result it is required to publish.
    """


class StoreNotBuilt(EvWidenError):
    """A read-only pass needed a point-in-time store and the parquet is absent.

    §8.2, and it names a defect rather than a preference. v1's harness violated
    its own read-only clause without anyone noticing: ``--membership``,
    ``--plan`` and ``--freeze-block`` all reached ``table_cells``, which called
    ``epl.fit.build_store(played)`` at the DEFAULT root, and ``build_store`` can
    unlink and rewrite the shared ``results.parquet``
    (``epl/fit.py:177-203``). A pre-freeze command that can delete and rebuild
    the project's point-in-time store is not read-only in any sense the word
    carries.

    The read-only accessor "opens the existing store parquet and returns it. If
    the store parquet is absent it raises :class:`StoreNotBuilt` and stops. It
    never builds, never writes, never unlinks, and takes no 'build if missing'
    argument."
    """


class SequenceViolation(EvWidenError):
    """§8.4's frozen five-step sequence ran out of order.

    "Each step **refuses unless its predecessor's completion marker exists**."
    A marker written under a different freeze commit is not a marker for this
    run, and is refused the same way an absent one is.
    """


class FreezeStateUnverified(EvWidenError):
    """§8.6: the freeze / first-fit state could not be ESTABLISHED.

    Not "was asserted False" — could not be established from committed bytes and
    Git ancestry. The prereg blob is uncommitted or its commit is not an
    ancestor of HEAD; a hashed file's bytes differ from the committed table; the
    recorded membership or schema digests do not match a fresh recomputation; or
    a first-fit record names a different prereg blob.

    v1's guard trusted a caller-supplied ``harness_frozen=True`` on five public
    fit surfaces and performed no verification when it was True — "a guard that
    trusts a caller-supplied True performs no verification at exactly the moment
    verification matters". §8.6 removes the parameter and makes the guard
    establish the state itself, every time it is asked.
    """


# ==========================================================================
# 2. DIGESTS, THE CORPUS, THE ARCHIVE, THE LEDGER, THE CONFIGURATION
# ==========================================================================

def assert_not_overridable(**supplied: Any) -> None:
    """§2.3's closure on the frozen constants, enforced at the surface.

    > **`B = 10,000` is frozen and is not overridable.** No CLI flag, keyword or
    > environment variable may pass a different `B`, `alpha`, block definition
    > or resampling seed into any deciding computation — the two match
    > intervals, the MW6 table interval of §5, or the power simulation of §6. A
    > harness that accepts one is not the harness this document preregisters.
    > The same closure applies to `n_sims` (20,000), `MC_BOOT` (2,000),
    > `SHARDS` (4) and `K` (200, §5.4).

    v1 left ``--n-boot`` on the CLI and passed it into ``score_table``,
    ``merge`` and ``verify`` "without refusal", which is the whole of the
    remaining B3 code leg. The parameters survive here — a keyword that names
    the constant is how a caller says which computation it means — but a
    DIFFERENT value is refused rather than honoured.

    Called with ``name=(got, want)`` pairs.
    """
    wrong = {name: pair for name, pair in supplied.items()
             if pair is not None and pair[0] is not None and pair[0] != pair[1]}
    if wrong:
        detail = "; ".join(f"{n} = {got!r}, frozen at {want!r}"
                           for n, (got, want) in sorted(wrong.items()))
        raise EvWidenError(
            f"a frozen constant is not overridable and one was overridden: "
            f"{detail}. §2.3: 'No CLI flag, keyword or environment variable may "
            "pass a different B, alpha, block definition or resampling seed "
            "into any deciding computation [...] A harness that accepts one is "
            "not the harness this document preregisters.' The same closure "
            "covers n_sims, MC_BOOT, SHARDS and K.")


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
    """§0.1's digest of the configuration the run actually realises.

    One definition, in one place, so the constant, the check and the ledger row
    cannot drift apart: ``sha256(json.dumps(cfg, sort_keys=True,
    default=str))``.
    """
    return hashlib.sha256(
        json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def assert_config_frozen(path: Path | str | None = None,
                         cfg: dict | None = None) -> str:
    """Refuse a configuration that is not the frozen one (§7.1, as §0.1 repairs it).

    FOUR things, not three: the file's digest, the realised seed, the realised
    widening block, and — §0.1's repair — a digest of the WHOLE realised
    configuration.

    The widening block is not decoration: this experiment is defined on
    mechanism (c) at strength 0.5, and under mechanism (a) the widening would
    move into the LIKELIHOOD, the posterior would stop being arm-invariant, and
    every pairing claim in §2.3 would be false.

    The fourth condition is the one §0.1 added, and it is the one that binds
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
                f"the pinned {REALISED_CONFIG_SHA256}. §0.1 pins the digest of "
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
    """§7.1's `CorpusShapeMismatch`: 2,280 rows, 6 seasons, 212 blocks, y counts."""
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
    """What this process ACTUALLY has, recorded on every row (§7.2).

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
            "condition and §7.2 records it per row. Run as `python -u -m "
            "epl.evwiden`, which pins before numpy loads, or export the three "
            "variables before starting the worker.")
    return threads


#: The archive fields the module-level digest binds — the freshness
#: preregistration's own step-4 lesson, adopted from day one (§7.2). A digest that silently narrows to the
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

    One function, one comparison, one place for §7.3's seeded defect to replace
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

    ``check_leak`` is §7.1's :class:`EvidenceLeak`, and it is placed where it
    can actually fail. A guard that re-applied the same ``date < C`` comparison
    to the frame that comparison just produced would be a tautology, and the one
    thing a leak guard may not be is unable to go red. So the check is made on
    the AGES THAT WEIGHT THE SUM, downstream of the filter: a match dated on the
    cutoff has ``age_days = 0`` and would enter at full weight ``0.5 ** 0 = 1``,
    and a later one enters at MORE than full weight. Demanding every contributing
    age be strictly positive therefore catches a filter that admits either —
    which is exactly what :func:`prior_rows` being replaced by a ``<=`` variant
    does, and what §7.3's seeded defect does to it.
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
    grid `e*` — the union THROUGH `e* = 12` (that is, `e* <= 12`), of which the
    primary's 62 are a subset.

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
    """The serialisation §8.3 step 2 hashes. Sorted, explicit, no dict order."""
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
    """§8.3 step 2's frozen membership digests, recomputed by the harness's own
    code from the pinned artifacts.

    "Each serialised canonically and hashed" — the 85 thin fixture keys, the 52
    treated keys, the 51 newly-flagged club-cutoff cells, the 78 fit openings and
    the 15 treated / 17 untouched table cells. THE COUNTS ARE CHECKED HERE:
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
            "§10 makes dropping a fixture after the run starts an invalidation: a "
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
        # ...and the two digests carry the CUTOFF DATE and the TREATED CLUBS
        # (adjudication F6). `season|cutoff_label` alone hashed two schedules
        # differing by a week or by a club to the same value, so §8.6 condition
        # (3)'s equality could not see the difference it exists to see.
        out["digests"]["table_treated"] = table_schedule_digest(treated_cells)
        out["digests"]["table_untouched"] = table_schedule_digest(untouched)
        out["digests"]["table_schedule"] = table_schedule_digest(table)
        out["keys"]["table_treated"] = [
            f"{c['season']}|{c['cutoff_label']}" for c in treated_cells]
        out["keys"]["table_untouched"] = [
            f"{c['season']}|{c['cutoff_label']}" for c in untouched]
        # v3 §8.3: the freeze block records BOTH per-label censuses and the
        # three excluded keys, so §8.6 condition (3) — which asks for EQUALITY
        # in both directions between the block and a fresh recomputation — has
        # something to recompute them from. A digest the block records and no
        # recomputation produces is as much a failure as the reverse.
        census = assert_table_census(table)
        out["counts"]["table_cells_by_label"] = dict(census["cells_by_label"])
        out["counts"]["table_treated_by_label"] = dict(census["by_label"])
        out["digests"]["table_cells_by_label"] = _digest_list(
            f"{k}={v}" for k, v in sorted(census["cells_by_label"].items()))
        out["digests"]["table_treated_by_label"] = _digest_list(
            f"{k}={v}" for k, v in sorted(census["by_label"].items()))
        out["digests"]["table_excluded"] = _digest_list(EXCLUDED_CELLS)
        out["keys"]["table_excluded"] = list(EXCLUDED_CELLS)
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
    """§7.2's resume key: ``cutoff|seed|config_sha256``."""
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
    """§7.2's canonical form: sorted, volatile fields removed, `sort_keys=True`.

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


def load_ledger(path: Path | str, *, complete_only: bool = True
                ) -> list[dict[str, Any]]:
    """Every fixture row in a shard, de-duplicated, schema-checked, ordered.

    **There is no `allow_poison` parameter.** §7.1 makes a poison row
    :class:`ShardFailed` and §2.4 makes a poisoned shard unmergeable and
    unscorable; a keyword that admits one is the refusal with an off switch. The
    one caller that legitimately reads past poison is :func:`completed_keys`,
    which is asking which fits are DONE and decides nothing, and it goes through
    the private reader below.

    Three refusals the preregistration named, in one place: a duplicated key
    that DISAGREES is :class:`RowConflict`; a row missing a §7.2 field is
    :class:`SchemaMismatch`; a poison row is :class:`ShardFailed` unless the
    caller is the one collecting poison.

    ``complete_only`` drops a fit whose fixture rows are short of the count the
    rows themselves declare — the signature of a crash mid-append. It is how
    resume knows a fit is unfinished rather than trusting the file's length.
    """
    return _load_ledger(path, allow_poison=False, complete_only=complete_only)


def _load_ledger(path: Path | str, *, allow_poison: bool = False,
                 complete_only: bool = True) -> list[dict[str, Any]]:
    """:func:`load_ledger`'s body, plus the resume reader's poison tolerance."""
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
                    f"cutoff {row.get('cutoff')!r} lacks {field!r}. §7.2 fixes "
                    "what a row records; a field nobody wrote is a field nobody "
                    "can check afterwards.")
        for field in REQUIRED_FIT_FIELDS:
            if field not in (row.get("fit") or {}):
                raise SchemaMismatch(
                    f"{paths.rel(path)}: the fit provenance of "
                    f"{row.get('match_id')!r} at cutoff {row.get('cutoff')!r} "
                    f"lacks {field!r}. §7.2 fixes what a row records at BOTH "
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
            _load_ledger(path, allow_poison=True, complete_only=True)}


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
    """Refuse a fit that can see the fixtures it is about to price (§7.1).

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


def assert_identity_control(cutoff: str, match_ids: Sequence[str],
                            probs_incumbent: np.ndarray,
                            stored: np.ndarray) -> dict[str, float]:
    """§3.2's identity control: EXACT equality at the corpus's eight decimals.

    Extracted from :meth:`Engine.fit` so §8.5's L12 can execute it rather than
    read it. The in-tree audit's finding was precise: loosening the comparison
    to `1e-4` turned a test red for the WRONG reason — `CanaryFailed` from the
    identity-canary branch, which only runs on the 16 of 78 openings where the
    §2.1 union adds nobody — so the site §10 names ("The identity control's
    tolerance is widened after a mismatch, anywhere") was uncovered on the 62
    openings that carry treated fixtures. The comparison is one function now,
    called unconditionally, and a loosened one is red at its own scenario.
    """
    diff = np.abs(np.asarray(probs_incumbent, dtype=float)
                  - np.asarray(stored, dtype=float))
    worst = float(diff.max()) if diff.size else 0.0
    mean_diff = float(diff.mean()) if diff.size else 0.0
    if not np.array_equal(probs_incumbent, stored):
        offenders = [match_ids[i] for i in
                     sorted(set(np.flatnonzero(diff.max(axis=1) > 0)))]
        raise ControlMismatch(
            f"{cutoff}: {len(offenders)} of {len(match_ids)} identity-"
            f"control probabilities differ from the corpus (max |Δp| = "
            f"{worst:.3g}), first at {offenders[:5]}. §3.2 rules EXACT "
            "equality at the corpus's eight decimals and §10 makes widening "
            "the tolerance after a mismatch an invalidation. This is most "
            "likely archive drift since the walk, and it invalidates the "
            "pairing the whole design rests on: STOP, and write the "
            "amendment before anything continues.")
    return {"max_abs_diff": worst, "mean_abs_diff": mean_diff}


def assert_untreated_unmoved(cutoff: str, match_ids: Sequence[str],
                             probs_arm: np.ndarray,
                             probs_incumbent: np.ndarray,
                             treated: Iterable[str]) -> int:
    """§2.3: a fixture outside the treated set that moved is `UntreatedMoved`.

    Against ARM B — the same posterior's incumbent pass — and not against the
    corpus, which is now the external control.
    """
    treated = set(str(t) for t in treated)
    checked = 0
    for i, mid in enumerate(match_ids):
        if str(mid) in treated:
            continue
        checked += 1
        if not np.array_equal(probs_arm[i], probs_incumbent[i]):
            raise UntreatedMoved(
                f"{cutoff}: {mid} is outside the treated set and its "
                f"Arm-A probabilities {np.asarray(probs_arm[i]).tolist()} "
                f"differ from Arm B's "
                f"{np.asarray(probs_incumbent[i]).tolist()}. The treatment must "
                "touch exactly the fixtures the rule names — a fixture that "
                "moves without being named means the predicate is not "
                "per-fixture, and every untreated delta this run reports "
                "would be noise dressed as zero.")
    return checked


def assert_pass_two_three_agree(cutoff: str, match_id: str,
                                union_probs: np.ndarray,
                                all_clubs_probs: np.ndarray) -> None:
    """A treated fixture's union-pass value and its all-clubs value are ONE number.

    `finalize_grid` keys on a boolean and cannot see WHICH club carried it. §7.1
    gives this no name, so it refuses as the base class rather than under an
    invented one.
    """
    if not np.array_equal(union_probs, all_clubs_probs):
        raise EvWidenError(
            f"{cutoff}: {match_id} is widened under both the §2.1 "
            f"union and the all-clubs predicate but the two "
            f"probabilities differ ({np.asarray(union_probs).tolist()} "
            f"vs {np.asarray(all_clubs_probs).tolist()}). Widening is a "
            "per-fixture boolean and the mix does not read which club carried "
            "it; if it did, the grid secondaries assembled from this pass "
            "would not be the arms they claim to be.")


class Engine:
    """The walk-forward's own machinery, built once and reused per fit.

    Everything is read from `epl.freeze`, `epl.fit`, `epl.anchor` and
    `epl.dcfit` rather than rebuilt: the same frozen config, the same `Anchor`
    over the same played frame, the same `build_store`, the same
    `config_read_once` fast panel, and the same `fit_epl` with
    `feature_cache_dir=paths.FIT_CACHE_DIR`. §2.3 names that call sequence and
    this class is it.

    `walkforward.verify_fast_path_is_inert` is NOT cited for the fast panel's
    inertness at FORECAST level, and §3.2 says why: it builds the feature panel
    twice and compares the two with `DataFrame.equals`, which is a check on
    feature frames rather than on repeated fitted forecasts. What supports the
    forecast-level claim is §3.2's own 820-fixture identity control, and §3.2 is
    equally plain that the control "is not supported by an assumption; it is the
    claim under test".

    Byte-parity with the walk's own results is therefore not something this
    class proves and not something it assumes: it is what calling the same
    functions with the same inputs is EXPECTED to get, and §3.2's identity
    control is the check that it did.
    """

    def __init__(self, corpus: pd.DataFrame, played: pd.DataFrame | None = None,
                 *, ledger: dict[str, set[str]] | None = None,
                 verbose: bool = True,
                 construction_only: bool = False,
                 directory: Path | str | None = None):
        from epl import anchor as anchor_mod, freeze
        from epl import fit as epl_fit

        # §8.2's binding obligation, BEFORE the store and the anchor are built:
        # the refusal is keyed to the freeze state and to the artifact identity,
        # never to the output directory, and a run that is going to be refused
        # should be refused before it spends anything.
        #
        # §8.6: THERE IS NO `harness_frozen` PARAMETER. The state is established
        # by the guard from committed bytes and Git ancestry, every time it is
        # asked, and `self.harness_frozen` records what the guard established —
        # never what a caller asserted (§7.2).
        #
        # `construction_only` is §8.2's PASS 4, and it is not a seam: it can
        # only ever make this object LESS capable. It skips the guard because
        # the object it builds cannot fit — :meth:`fit` refuses on
        # ``self.can_fit`` before it touches `dcfit` — and it takes its store
        # from §8.2's read-only accessor, which never builds one. The review's
        # NEW-B5 found pass 4 unexecutable: `__init__` called the guard, the
        # guard refused the pinned archive while unfrozen, and the enumeration
        # named a pass no command could run.
        self.directory = Path(directory) if directory is not None else EVWIDEN_DIR
        self.can_fit = not bool(construction_only)
        self.may_fit = (
            assert_may_fit("epl.evwiden.Engine", played=played, corpus=corpus,
                           directory=self.directory) if self.can_fit else
            {"guarded": True, "frozen": _frozen_now(), "real_artifacts": False,
             "construction_only": True,
             "why": "§8.2 pass 4: this Engine cannot fit, so there is nothing "
                    "for the pre-freeze refusal to prevent"})
        self.harness_frozen = bool(self.may_fit["frozen"])
        self._epl_fit = epl_fit
        self.cfg = freeze.frozen_wcmodel_config()
        self.config_sha256 = assert_config_frozen(cfg=self.cfg)
        self.realised_config_sha256 = realised_config_sha256(self.cfg)

        self.played = load_archive() if played is None else played
        self.ledger = load_walk_ledger() if ledger is None else ledger
        self.anchor = anchor_mod.Anchor(self.played, freeze.frozen_elo_config())
        # §8.2's read-only clause, mechanically: pass 4 may not build a store
        # under `paths.STORE_DIR`, and `build_store` can unlink and rewrite the
        # shared `results.parquet`.
        self.store = (epl_fit.build_store(self.played) if self.can_fit
                      else read_only_store())
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
        # §8.2 pass 4's stopping point is STRUCTURAL, and this is where it is:
        # BEFORE the `dcfit` import below, so a construction-only Engine cannot
        # reach the sampler's module, let alone the sampler. The in-tree audit's
        # finding 7 was that v2 claimed exactly this while the import ran at
        # entry and `can_fit` was tested after it — a false sentence about a
        # stopping point, in the document that authorises the pass.
        if not self.can_fit:
            raise EvWidenError(
                "this Engine was constructed for §8.2's pass 4 — the PARTIAL "
                "engine pass — and it cannot fit. The pass runs construction, "
                "`fit_points`, the enlarged set, `assert_cutoff_clean` and "
                "`assert_point_in_time`, and stops STRUCTURALLY before "
                "`dcfit.fit_epl` — before this function imports `epl.dcfit` at "
                "all; that is why §8.2 authorises it before the freeze and why "
                "the guard lets it construct at all. A fit needs an ordinary "
                "Engine, and an ordinary Engine is refused until §8.3's commit "
                "lands.")

        from epl import dcfit
        from epl import walkforward as wf
        import warnings

        t0 = time.perf_counter()
        # §2.3's closure reaches the estimand's own constant: `e*` is 10.0,
        # frozen, and §8.6 makes a production path resolve it rather than
        # accept one.
        assert_not_overridable(e_star=(float(e_star), E_STAR))
        # Re-checked at every fit, not only at construction: the freeze state
        # and the first-real-fit regime are properties of the moment the
        # sampler runs, and a long run must not carry a stale verdict.
        may = assert_may_fit(
            "epl.evwiden.Engine.fit", played=self.played, corpus=self.corpus,
            directory=self.directory)
        self.harness_frozen = bool(may["frozen"])
        cutoff = pd.Timestamp(point.cutoff).normalize()
        assert_cutoff_clean(cutoff, self.played, point.match_ids)
        pit = self._epl_fit.assert_point_in_time(self.store, cutoff)
        if str(pit["latest_training_date"]) >= point.cutoff:
            raise CutoffLeak(
                f"the STORE's latest training date at {point.cutoff} is "
                f"{pit['latest_training_date']}")

        # §8.6: "the UTC instant of the first real fit". The record is written
        # HERE, at the call that performs it, and not during the permission
        # check that precedes it — a timestamp taken while deciding whether a
        # fit may happen is not the instant one did.
        if may["frozen"] and may["real_artifacts"]:
            record_first_real_fit(where="epl.evwiden.Engine.fit")

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
        control = assert_identity_control(point.cutoff, point.match_ids,
                                          probs_incumbent, stored)
        worst = control["max_abs_diff"]
        mean_diff = control["mean_abs_diff"]

        # ---- pass 2: the §2.1 union at the primary e* --------------------
        enlarged = self.enlarged(point, incumbent, e_star)
        with provisional_as(post, enlarged):
            probs_arm = predict_rows(post, pairs)

        treated_here = {m for m, (h, a) in zip(point.match_ids, pairs)
                        if (h in enlarged or a in enlarged)
                        and not (h in incumbent or a in incumbent)}
        assert_untreated_unmoved(point.cutoff, point.match_ids, probs_arm,
                                 probs_incumbent, treated_here)

        # ---- the identity canary, on every block the union does not touch --
        # §7.3: "An `e*` low enough to add nobody must yield `np.array_equal`
        # with the corpus rows." On 16 of the 78 blocks the §2.1 union adds
        # nobody, and pass 2 IS that canary — checked here rather than bought
        # with a second fit at `e* = 0`.
        #
        # WHAT IT CAN AND CANNOT CATCH, said plainly rather than assumed. Its
        # refusal is unreachable while the two checks above hold: with an empty
        # `added` every fixture is untreated, so `assert_untreated_unmoved` has
        # already required Arm A to equal Arm B and `assert_identity_control`
        # has already required Arm B to equal the corpus. This is a restatement
        # whose force comes from those two, which is why §8.5's L12 tests THEM
        # directly and why the audit was right that a constant PASS here would
        # leave a suite green. What a committed test can assert about this line
        # is that it RUNS where the union adds nobody and does not run where it
        # adds somebody, and that is what one does.
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
        # §7.3: the comparator is the production path, the documented edge
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
                if mid in treated_here:
                    assert_pass_two_three_agree(point.cutoff, str(mid),
                                                probs_arm[idx[mid]], row)

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
            #: §7.3 requires the branch every fixture took to be recorded, so
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

#: §8.2 pass 4's opening, named in the document and not chosen here.
PARTIAL_ENGINE_OPENING = "2019-08-09"


def partial_engine_pass(corpus: pd.DataFrame | None = None,
                        played: pd.DataFrame | None = None,
                        ledger: dict[str, set[str]] | None = None, *,
                        opening: str = PARTIAL_ENGINE_OPENING,
                        verbose: bool = False) -> dict[str, Any]:
    """§8.2's PASS 4, executable: the whole fit path except the fit.

    > One partial engine pass at the first opening (2019-08-09): construction,
    > `fit_points`, the enlarged set, `assert_cutoff_clean` and
    > `assert_point_in_time` — the whole of the fit path **except** the call to
    > `dcfit.fit_epl`. No sampler runs; the shared point-in-time store must be
    > byte-identical afterwards.

    The review's NEW-B5 found the pass unexecutable and the enumeration
    therefore untrue. It is executable now, and the reason the guard permits it
    before the freeze is structural rather than attested: the Engine it builds
    has ``can_fit = False``, :meth:`Engine.fit` refuses on that flag **before**
    it imports `dcfit` or touches the sampler, and the store comes from §8.2's
    read-only accessor, which never builds one. There is no argument by which
    this pass can fit; that is what makes it a pass and not a fit.

    It returns what the pass established, including the store's bytes and mtime
    before and after, which §8.2 asks for in the same sentence.
    """
    corpus = load_corpus() if corpus is None else corpus
    played = load_archive() if played is None else played
    ledger = load_walk_ledger() if ledger is None else ledger

    store_table = paths.STORE_DIR / STORE_TABLE_PARQUET
    before = ((sha256_file(store_table), store_table.stat().st_mtime_ns)
              if store_table.exists() else (None, None))

    engine = Engine(corpus, played, ledger=ledger, verbose=verbose,
                    construction_only=True)
    point = fit_points(corpus, [str(opening)], check=False)[0]
    incumbent = set(engine.ledger.get(point.cutoff) or ())
    enlarged = engine.enlarged(point, incumbent)
    cutoff = pd.Timestamp(point.cutoff).normalize()
    assert_cutoff_clean(cutoff, engine.played, point.match_ids)
    pit = engine._epl_fit.assert_point_in_time(engine.store, cutoff)

    stopped = False
    try:
        engine.fit(point)
    except EvWidenError as exc:
        stopped = "cannot fit" in str(exc)

    after = ((sha256_file(store_table), store_table.stat().st_mtime_ns)
             if store_table.exists() else (None, None))
    if before != after:
        raise EvWidenError(
            f"§8.2 pass 4 moved {paths.rel(store_table)}: the pass is read-only "
            "and the shared point-in-time store must be byte-identical "
            "afterwards.")
    return {
        "schema": SCHEMA_ID, "pass": "§8.2 pass 4 — the partial engine pass",
        "opening": point.cutoff, "season": point.season, "block": point.block,
        "n_fixtures": len(point.match_ids),
        "provisional_incumbent": sorted(incumbent),
        "provisional_enlarged": sorted(enlarged),
        "added": sorted(enlarged - incumbent),
        "latest_training_date": str(pit["latest_training_date"]),
        "cutoff_clean": True, "point_in_time": True,
        "stopped_before": "epl.dcfit.fit_epl",
        "fit_refused": bool(stopped),
        "store_unchanged": True,
        "store": paths.rel(store_table),
        "note": ("no sampler ran: the Engine was constructed with "
                 "`can_fit = False` and `Engine.fit` refuses on that flag "
                 "before it imports `dcfit`"),
    }


def thin_at(e_min: float, grid: Sequence[float] = (*E_GRID, E_STAR)
            ) -> list[str]:
    """The grid points this fixture is thin at, as the keys the ledger uses."""
    return [f"{g:g}" for g in sorted(float(g) for g in grid) if e_min < float(g)]


#: §8.7's first-real-fit event. Once this file exists, a real fit on the real
#: archive exists — whether or not it produced a delta, whether or not it was
#: merged, whether or not anyone looked at it — and any change to any hashed
#: file invalidates the preregistration. No note, no dated appendix, no
#: disclosure and no owner ruling restores it.
#:
#: **ONE FIXED REPO-ROOT-KEYED PATH** (§8.6), derived from ``paths.REPO_ROOT``
#: and from nothing else, and **no function that reads or writes it takes a
#: directory argument.** v1's record was written below the caller's chosen
#: directory, so a fresh or deleted ``--dir`` reset the entire §8.7 regime: the
#: one-way ratchet had a way back, and the way back was a flag.
FIRST_FIT_JSON = paths.FIT_DIR / "evwiden_first_real_fit.json"

#: §8.6's APPEND-ONLY WITNESS, because a deletable file is not a ratchet.
#:
#: Two review rounds found the same hole and neither the document nor the
#: harness closed it: absence of :data:`FIRST_FIT_JSON` returned ``None`` and
#: restored the pre-fit state, so **deleting the record reset the entire §8.7
#: regime**. v3 §8.6 makes the transition durable instead: every write of the
#: record is accompanied by an append here, the harness opens this file for
#: APPEND and never for truncation, and each line carries a CHAIN DIGEST over
#: the previous line's, so a line removed from the middle breaks every digest
#: after it.
#:
#: What it buys, stated as v3 states it: deletion becomes VISIBLE rather than
#: impossible. Someone who deletes the record must also delete the witness, and
#: someone who deletes both has deleted an append-only file whose absence §8.8's
#: attestation speaks to. That is strictly more than a single deletable file. It
#: is **not** a global proof and §8.6 does not claim it is.
FIRST_FIT_WITNESS = paths.FIT_DIR / "evwiden_first_fit_witness.jsonl"

#: §8.6's closure, for a seam that names no directory because it WRITES
#: nothing. ``target=None`` means "the caller is about to use the default, and
#: the default is the preregistered run directory", which is why it is refused;
#: a seam with no directory at all is a different case and is judged on the
#: ARTIFACTS alone. Passing this sentinel is the way a caller says so, and every
#: use of it is a surface that produces no file.
NO_TARGET = "<no directory: this seam writes nothing>"

#: §8.6's public-surface closure: the directories this document preregisters.
#: A seam aimed at one of them is a seam aimed at the preregistered run, and
#: :func:`assert_seam_allowed` refuses it whatever the caller intends.
#: v3 §8.6 consequence 5: **this experiment's artifacts, not every artifact.**
#: The review's P5-I2 found the guard refusing unrelated scratch work anywhere
#: beneath the SHARED ``paths.FIT_DIR``, which is where every experiment in this
#: repository writes — over-refusal that blocks the audit passes §8.2 authorises
#: and that gets worked around rather than obeyed. What replaces the breadth is
#: exactness: a closed enumeration a committed test reads back, so a new evwiden
#: artifact that is not in it is caught at the test rather than covered by a
#: wildcard.
#:
#: The adjudication of 2026-08-29 (F12) took ``reports/evidence/`` out of this
#: tuple for the same reason v2's version had to give up ``paths.FIT_DIR``: it
#: is a SHARED tree. The anchoring and freshness experiments publish there, its
#: README and its MANIFEST are theirs as much as this document's, and refusing
#: every seam beneath it is over-refusal that blocks work §8.2 authorises. What
#: replaces the breadth is the same exactness: this experiment's evidence files
#: are named one by one below.
PREREGISTERED_DIRS: tuple[Path, ...] = (EVWIDEN_DIR, TABLE_DIR, SEQUENCE_DIR)

#: ...and the files this document names by path, which sit beside those
#: directories rather than inside them. It is a function rather than a tuple
#: because :data:`FEASIBILITY_RECORD` is defined further down and because §8.5's
#: rows rebind these constants to a scratch tree — a tuple frozen at import
#: would name the real paths after the rebinding.
def preregistered_files() -> tuple[Path, ...]:
    """The individual artifacts §8.6's closure names, as they stand now.

    Eleven: the merged verdict, the first-fit record and its witness, §0.6's
    census record and the committed copy of it, §8.5's conformance artifact, and
    this experiment's five published files inside the shared
    ``reports/evidence/`` tree (adjudication F12). The list is what a committed
    test reads back, so a new evwiden artifact outside it is caught at the test
    rather than covered by a wildcard over somebody else's directory.
    """
    return (EVWIDEN_JSON, FIRST_FIT_JSON, FIRST_FIT_WITNESS,
            FEASIBILITY_RECORD, FEASIBILITY_COMMITTED, CONFORMANCE_ARTIFACT,
            EVIDENCE_JSON, EVIDENCE_PER_FIXTURE, EVIDENCE_TABLE_CELLS,
            EVIDENCE_GRID_MEANS, EVIDENCE_MANIFEST)

_PINNED_ARCHIVE_IDENTITY: dict[str, str | None] = {}
_PINNED_ARCHIVE_ANCESTRY: dict[str, frozenset[str] | None] = {}


def pinned_archive_identity() -> str | None:
    """The module-level digest of the PINNED archive, or ``None`` if it is absent.

    §8.2's binding obligation is keyed "to the freeze state and to
    the artifact identity being read, never to the output directory", so it
    needs a way to answer "is this frame the real archive?" that no ``--dir``
    can move. It is the same digest §7.2 already records on every row — over
    ``match_id, date, fthg, ftag`` — computed once from the pinned bytes.
    """
    if "value" not in _PINNED_ARCHIVE_IDENTITY:
        value: str | None = None
        try:
            if ARCHIVE_PATH.exists() and sha256_file(ARCHIVE_PATH) == ARCHIVE_SHA256:
                value = archive_digest(load_archive(require_digest=False))
        except Exception:                                  # noqa: BLE001
            value = None
        _PINNED_ARCHIVE_IDENTITY["value"] = value
    return _PINNED_ARCHIVE_IDENTITY["value"]


def pinned_archive_ancestry() -> frozenset[str] | None:
    """Every club key the PINNED archive names, or ``None`` if it is absent.

    §7.4 defines SYNTHETIC by ancestry — "no value may be read, copied,
    sampled, transformed, or otherwise derived from `data/epl/matches.parquet`"
    — and the five invented club names are absent from the pinned archive by a
    committed test. That makes the club set the mechanical ancestry test: a
    frame naming one of the pinned archive's own clubs was derived from it,
    whatever its digest says.
    """
    if "clubs" not in _PINNED_ARCHIVE_ANCESTRY:
        value: frozenset[str] | None = None
        try:
            if ARCHIVE_PATH.exists() and sha256_file(ARCHIVE_PATH) == ARCHIVE_SHA256:
                frame = load_archive(require_digest=False)
                value = frozenset(str(c) for c in
                                  (set(frame["home_key"].astype(str))
                                   | set(frame["away_key"].astype(str))))
        except Exception:                                  # noqa: BLE001
            value = None
        _PINNED_ARCHIVE_ANCESTRY["clubs"] = value
    return _PINNED_ARCHIVE_ANCESTRY["clubs"]


def archive_provenance(played: pd.DataFrame | None) -> str:
    """``pinned`` / ``derived`` / ``synthetic`` / ``absent`` / ``unknown``.

    The review's NEW-B2 named the hole this closes: "a real-derived archive
    differing by one value is neither byte-identical pinned input nor v2-literal
    synthetic input, yet `is_pinned_archive` can classify it as non-pinned and
    allow it before freeze". A three-way classification is what §7.4 actually
    writes — synthetic is *literal*, everything touched by the pinned artifacts
    is not — and the ambiguous middle is refused rather than allowed, because a
    guard that resolves its own doubt in favour of fitting is not a guard.
    """
    if played is None:
        return "absent"
    want = pinned_archive_identity()
    clubs = pinned_archive_ancestry()
    if want is None or clubs is None:
        return "unknown"
    try:
        if archive_digest(played) == want:
            return "pinned"
    except Exception:                                      # noqa: BLE001
        return "unknown"
    try:
        named = (set(played["home_key"].astype(str))
                 | set(played["away_key"].astype(str)))
    except Exception:                                      # noqa: BLE001
        return "unknown"
    return "derived" if (named & set(clubs)) else "synthetic"


def is_pinned_archive(played: pd.DataFrame | None) -> bool:
    """Is this played frame the pinned archive, whatever it is called?"""
    return archive_provenance(played) == "pinned"


def is_derived_from_pinned_archive(played: pd.DataFrame | None) -> bool:
    """Is this frame near-real — the pinned archive's rows, altered?

    Refused pre-freeze on the same terms as the pinned archive itself: §7.4
    admits only frames whose every value is written literally in
    `epl/tests/test_evwiden.py`, and a frame carrying the archive's own clubs
    is not one of them.
    """
    return archive_provenance(played) == "derived"


def is_pinned_corpus(corpus: pd.DataFrame | None) -> bool:
    """Is this frame the pinned walk-forward corpus, by its own frozen shape?"""
    if corpus is None or "y" not in getattr(corpus, "columns", ()):
        return False
    if len(corpus) != CORPUS_ROWS:
        return False
    seasons = tuple(sorted(set(corpus["season"].astype(str))))
    counts = tuple(int((corpus["y"].to_numpy() == k).sum()) for k in (0, 1, 2))
    return (seasons == tuple(sorted(CORPUS_SEASONS))
            and counts == tuple(CORPUS_Y_COUNTS))


#: v2 §8.2 pass 7 — the `dc_native`-ONLY parity feasibility pass, authorised by
#: name UNDER v2, run once on 2026-08-28, and PRIOR HISTORY for this document
#: (v3 §8.1). v2's §3.3 made a 35-cell parity leg mandatory and could not assume
#: it would complete; the pass established which of the thirty-five the
#: protected runner can price. **v3 authorises no equivalent** — §10 makes one
#: run under this document an invalidation — and what remains here is a READER.
FEASIBILITY_PASS_NAME = "v2 §8.2 pass 7 — the dc_native parity feasibility pass"

#: The pass's one record, and its PRODUCT is the CENSUS it carries: every one of
#: v2 §3.3's 35 attempted cells, priceable or not, each unpriceable one with its
#: refusal kind, the fixture the protected code names and its measured excluded
#: mass. **v3 §0.6 is written against it and §0.1 pins it**; it is READ-ONLY to
#: this module, §8.8's attestation excepts it by name, and it carries no delta,
#: no table cell, no arm comparison and no estimand.
FEASIBILITY_RECORD = paths.DATA_DIR / "sim" / "evwiden_parity_feasibility.json"

#: v3 §0.1 pins the record BY DIGEST, and §8.3 binds that digest into the
#: freeze block. This document's table leg is SCOPED by the census (§0.6), and
#: `data/` is gitignored: a scope resting on an unhashed local file rests on
#: nothing, and the review's P5-B2 found the record "non-atomic, forgeable, not
#: bound to the archive/store/config/harness digest". A reader checks the block.
FEASIBILITY_SHA256 = ("07ee00d798cb0f01f29bc5bb5ba885c41e26d5494e9755c73a038a2"
                      "777bad329")
FEASIBILITY_BYTES = 18128

#: ...and the COMMITTED COPY of those bytes (adjudication F13, V3-I3). The
#: digest makes the local record tamper-evident and nothing more: "a
#: repository-only reader has neither the evidence bytes nor an archival
#: locator. Git cannot independently inspect the masses, execution commit,
#: completion, timings, or provenance, and cannot recover the file if deleted."
#: The census is the scope of this document's whole table leg, so the bytes
#: themselves are committed here, under version control, byte-identical to the
#: gitignored record; the freeze block binds BOTH paths and the one digest they
#: share. This is a copy of an existing measurement, not a new one — v3
#: authorises no pass that could produce a census (§8.2).
FEASIBILITY_COMMITTED = (paths.REPO_ROOT / "reports" / "evidence"
                         / "widening_parity_feasibility.json")

#: What the record has to SAY, so that a record which is not the record scopes
#: nothing. The priceable set is v3's 32 cells; the unpriceable set is §0.6's
#: three, and a census that suddenly prices all thirty-five is as much a refusal
#: as one that prices thirty-one — either way this document is scoped against a
#: measurement that is no longer the measurement.
FEASIBILITY_EXPECTED_ATTEMPTED = 35
FEASIBILITY_EXPECTED_UNPRICEABLE: tuple[str, ...] = EXCLUDED_CELLS

#: **v3 AUTHORISES NO PRE-FREEZE PASS THAT FITS OR SIMULATES**, so there is no
#: `parity_feasibility_pass`, no `parity_feasibility_census`, no CLI action
#: that could run one, no `FEASIBILITY_SURFACES` permission set and no
#: `_FEASIBILITY` mutable state anywhere in this module. v2 §8.2 authorised one
#: such pass; it ran on 2026-08-28 and answered the only question it existed to
#: answer (§0.6), and §10 makes a pass run under THIS document an invalidation.
#: The review's P5-B2 found the permission set and the pass state to be mutable
#: module globals a caller could rebind, the record deletable and forgeable, and
#: a constructed runner able to carry its permission out of the closed context.
#: Deleting the surface closes all four at once: there is no permission to
#: rebind, no context to leave open and no runner to construct under one.
FEASIBILITY_SURFACE_CLOSED = True


def _frozen_table_cell_keys() -> list[str] | None:
    """§3.3's 32 cell keys, RECOMPUTED from the pinned artifacts, or ``None``.

    §8.2 pass 7 recomputes them rather than accepting them, because a caller who
    could name the census could name a shorter one — and "the pass completed"
    would then mean "the pass completed the cells the caller chose". The
    preregistered table merge asks the same question of its own `expected=`.
    """
    try:
        cells = default_table_cells()
        assert_table_census(cells)
        return [f"{c['season']}|{c['cutoff_label']}" for c in cells]
    except Exception:                                      # noqa: BLE001
        return None


def _is_preregistered_target(target: Path | str | None) -> bool:
    """Does this path name — or sit inside — one of the preregistered directories?

    ``None`` counts, and that is the point: a caller that named no directory is
    a caller about to use the default, and the default is the preregistered run
    directory.
    """
    if target is None:
        return True
    if target is NO_TARGET:
        return False
    try:
        path = Path(target).resolve()
    except (OSError, ValueError, TypeError):               # pragma: no cover
        return True
    for root in PREREGISTERED_DIRS:
        try:
            root = root.resolve()
        except (OSError, ValueError):                      # pragma: no cover
            continue
        if path == root or path.is_relative_to(root):
            return True
    # ...and the two files this document names by path, which sit BESIDE those
    # directories rather than inside them. Enumerating them is what replaces
    # v2's wildcard over the whole shared `paths.FIT_DIR` (P5-I2): the closure
    # is exact, and a new evwiden artifact that is not in the list is caught by
    # the committed test that reads it back rather than covered by a pattern.
    for named in preregistered_files():
        try:
            if path == named.resolve():
                return True
        except (OSError, ValueError):                      # pragma: no cover
            continue
    return False


def assert_seam_allowed(seam: str, *, played: pd.DataFrame | None = None,
                        corpus: pd.DataFrame | None = None,
                        target: Path | str | None = None,
                        detail: str = "") -> dict[str, Any]:
    """§8.6's PUBLIC-SURFACE CLOSURE, in one place, for every seam there is.

    > **No public surface of the harness accepts any parameter that can alter a
    > frozen constant, inject an alternative implementation, attest a lifecycle
    > state, or truncate a deciding population, when the target artifacts are
    > pinned or the directories are the preregistered ones. Test seams live
    > behind ONE module-level guard that inspects the target and REFUSES
    > pinned/preregistered targets; production paths resolve every constant from
    > the frozen law and take no overrides.**

    A seam is legitimate exactly where §8.2 says an audit run is legitimate: on
    SYNTHETIC artifacts, in a directory of its own. Everything else — the pinned
    archive, a frame derived from it, the pinned corpus, or any of
    :data:`PREREGISTERED_DIRS` — is the preregistered run, and a seam aimed at
    it is refused whatever the caller intends. The refusal is deliberately
    unconditional on the freeze state: before the freeze a seam could fit the
    real archive with no block anywhere, and after it a seam could put a stub's
    output into the deciding ledgers.

    v1's defects were each an individual leak — a `harness_frozen` Boolean here,
    an injected runner there, an `n_sims` keyword somewhere else — and each was
    closed on its own. This closes the CLASS: one predicate, one refusal, and
    every surface that carries a seam calls it before it honours one.
    """
    provenance = archive_provenance(played)
    reasons: list[str] = []
    if provenance == "pinned":
        reasons.append(f"the played frame IS the pinned archive "
                       f"({paths.rel(ARCHIVE_PATH)})")
    elif provenance == "derived":
        reasons.append(
            "the played frame is DERIVED from the pinned archive — it carries "
            "the archive's own club keys — and §7.4 admits only frames whose "
            "every value is written literally in epl/tests/test_evwiden.py")
    if is_pinned_corpus(corpus):
        reasons.append("the corpus IS the pinned walk-forward corpus")
    if _is_preregistered_target(target):
        reasons.append(
            "the target is one of the preregistered directories or files "
            f"({', '.join(paths.rel(d) for d in PREREGISTERED_DIRS)}; "
            f"{', '.join(paths.rel(f) for f in preregistered_files())})"
            + ("" if target is not None else
               " — no target was named, and the default is the preregistered "
               "run directory"))
    if reasons:
        raise EvWidenError(
            f"refusing the seam {seam!r}"
            + (f" ({detail})" if detail else "")
            + ": " + "; ".join(reasons) + ". §8.6's public-surface closure: no "
            "public surface accepts a parameter that can alter a frozen "
            "constant, inject an alternative implementation, attest a lifecycle "
            "state or truncate a deciding population when the target artifacts "
            "are pinned or the directories are the preregistered ones. Audit "
            "runs are legitimate and §7.3 requires them: run them on SYNTHETIC "
            "corpora, as §7.4 defines synthetic, in a directory of their own.")
    return {"seam": seam, "allowed": True, "provenance": provenance,
            "target": None if target is None else str(target)}


def assert_may_fit(where: str, *,
                   played: pd.DataFrame | None = None,
                   corpus: pd.DataFrame | None = None,
                   directory: Path | str | None = None) -> dict[str, Any]:
    """§8.2's binding obligation: **no real fit or simulation before the freeze,
    ANYWHERE** — and §8.6's guard, which ESTABLISHES the state it needs.

    **There is no ``harness_frozen`` parameter and there may not be one.** v1's
    version took the freeze state from its caller and performed no verification
    when the caller said ``True``, so a direct harness call — ``Engine(...,
    harness_frozen=True)`` — could fit the pinned artifacts while unfrozen.
    §8.6: "A guard that trusts a caller-supplied `True` performs no verification
    at exactly the moment verification matters, and a direct harness call could
    then fit the pinned artifacts while unfrozen — which is the whole of what
    'anywhere' forbids." This function asks :func:`harness_freeze_status` itself,
    every time it is called, and that function reads committed bytes and Git
    ancestry.

    The refusal is keyed to the freeze state and to the ARTIFACT IDENTITY being
    read, **never to the output directory** — a ``--dir`` outside the defaults
    moves nothing, because `data/` is gitignored and a directory-keyed guard
    would let a scratch run fit the real archive and leave no Git trace at all.
    A synthetic corpus and a synthetic archive fit freely, before the freeze and
    after; the pinned archive does not. ``played=None`` is refused too, because a
    caller that has not loaded a frame is a caller about to load the pinned one.

    After the freeze it also records — and then enforces — §8.7's first-real-fit
    event: from the moment the first real fit completes, any change to any
    hashed file invalidates this preregistration.
    """
    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    harness_frozen = _frozen_now()
    provenance = archive_provenance(played)
    if not harness_frozen:
        reasons = []
        if played is None:
            reasons.append("no played frame was supplied, so the pinned archive "
                           "is about to be loaded")
        elif provenance == "pinned":
            reasons.append("the played frame IS the pinned archive "
                           f"({paths.rel(ARCHIVE_PATH)})")
        elif provenance == "derived":
            reasons.append(
                "the played frame is DERIVED from the pinned archive — it "
                "carries the archive's own club keys, so it is neither the "
                "pinned input nor §7.4's literal synthetic one, and the "
                "ambiguous middle is refused rather than allowed")
        if is_pinned_corpus(corpus):
            reasons.append("the corpus IS the pinned walk-forward corpus")
        if reasons:
            raise EvWidenError(
                f"refusing to fit or simulate in {where} before §8.3's "
                "harness-hash freeze commit: " + "; ".join(reasons) + ". "
                "§8.2's binding obligation is that the refusal is keyed to the "
                "FREEZE STATE and to the ARTIFACT IDENTITY being read, never to "
                "the output directory — a directory-keyed guard let a scratch "
                "--dir fit the real archive and produce a real delta with no "
                "freeze block anywhere, and `data/` is gitignored so it would "
                "leave no Git trace. §8.6 adds that the state is ESTABLISHED "
                "here and never accepted from a caller: there is no "
                "harness_frozen argument to pass. Audit runs are legitimate and "
                "§7.3 requires them: run them on SYNTHETIC corpora, as §7.4 "
                "defines synthetic.")
        return {"guarded": True, "frozen": False, "real_artifacts": False}

    real = provenance in ("pinned", "derived") or is_pinned_corpus(corpus)
    if real:
        # §8.6: one fixed repo-root-keyed path, no directory argument. `--dir`
        # moves where a run WRITES; it never moved where the first-fit regime
        # lives, and v1's version let it.
        #
        # The RECORD is not written here. This is the permission check, and
        # §8.6 fixes the record's first field as "the UTC instant of the first
        # real fit" — an instant a permission check does not know. The call
        # sites that are about to enter the sampler call
        # :func:`record_first_real_fit` themselves, immediately before they do.
        assert_no_hashed_file_moved()
    return {"guarded": True, "frozen": True, "real_artifacts": bool(real)}


def witness_lines() -> list[dict[str, Any]]:
    """§8.6's witness, read and CHAIN-CHECKED.

    A broken chain is `FreezeStateUnverified`: the whole point of the digest is
    that a line removed from the middle cannot be hidden, so a chain that does
    not verify is a witness that has been edited.
    """
    if not FIRST_FIT_WITNESS.exists():
        return []
    out: list[dict[str, Any]] = []
    prev = ""
    for i, raw in enumerate(FIRST_FIT_WITNESS.read_text().splitlines()):
        if not raw.strip():
            continue
        try:
            line = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FreezeStateUnverified(
                f"{paths.rel(FIRST_FIT_WITNESS)} line {i + 1} is not readable "
                f"JSON: {exc}. §8.6's witness is what makes the first-fit "
                "ratchet durable, and an unreadable line is not an absent one.")
        want = _witness_chain(prev, line)
        if str(line.get("chain")) != want:
            raise FreezeStateUnverified(
                f"{paths.rel(FIRST_FIT_WITNESS)} line {i + 1} carries chain "
                f"{str(line.get('chain'))[:12]}… and the digest over the "
                f"previous line's chain and this line's canonical form is "
                f"{want[:12]}…. §8.6: 'a line removed from the middle breaks "
                "every digest after it', which is the whole reason the chain "
                "exists — a witness that does not verify has been edited.")
        prev = want
        out.append(line)
    return out


def _witness_chain(prev: str, line: dict[str, Any]) -> str:
    """SHA-256 over the previous line's chain and this line's canonical form.

    ``sort_keys`` and ``default=str`` make the form a function of the line's
    content and not of the order a dict happened to be built in, which is the
    same discipline :func:`canonical` applies to a ledger row.
    """
    body = {k: v for k, v in line.items() if k != "chain"}
    payload = json.dumps(body, sort_keys=True, default=str,
                         separators=(",", ":"))
    return hashlib.sha256((str(prev) + payload).encode()).hexdigest()


def first_fit_state() -> dict[str, Any]:
    """§8.6: the record and its witness read TOGETHER, and disagreement refused.

    > * a witness with lines and **no record** is a **deleted record** — the
    >   ratchet holds, the state is post-first-fit, and the harness refuses
    >   rather than quietly reverting to pre-fit;
    > * a record with **no witness line** naming it is a forged or hand-written
    >   record and is refused;
    > * a broken chain digest is refused;
    > * both absent is pre-first-fit, which is the only state in which a fit may
    >   begin.
    """
    record = first_fit_record()
    lines = witness_lines()
    if record is None and not lines:
        return {"state": "pre_first_fit", "record": None, "witness": []}
    if record is None and lines:
        raise FreezeStateUnverified(
            f"{paths.rel(FIRST_FIT_WITNESS)} carries {len(lines)} line(s) and "
            f"{paths.rel(FIRST_FIT_JSON)} is absent. §8.6: 'a witness with "
            "lines and no record is a DELETED RECORD — the ratchet holds, the "
            "state is post-first-fit, and the harness refuses rather than "
            "quietly reverting to pre-fit'. Two review rounds found deletion "
            "resetting the whole §8.7 regime; this is what stops it.")
    if not lines:
        raise FreezeStateUnverified(
            f"{paths.rel(FIRST_FIT_JSON)} exists and "
            f"{paths.rel(FIRST_FIT_WITNESS)} carries no line naming it. §8.6: "
            "'a record with no witness line naming it is a forged or "
            "hand-written record and is refused'. The harness writes the "
            "witness line first and the record second, so this state cannot "
            "arise from an interrupted write.")
    matched = [ln for ln in lines
               if str(ln.get("at")) == str(record.get("at"))
               and str(ln.get("where")) == str(record.get("where"))]
    if not matched:
        raise FreezeStateUnverified(
            f"{paths.rel(FIRST_FIT_JSON)} records a fit at "
            f"{record.get('at')!r} from {record.get('where')!r} and no line of "
            f"{paths.rel(FIRST_FIT_WITNESS)} names it. §8.6 reads both and "
            "refuses their disagreement.")
    return {"state": "post_first_fit", "record": record, "witness": lines}


def first_fit_record() -> dict[str, Any] | None:
    """§8.6's record, read from its **one fixed repo-root-keyed path**.

    No directory argument, deliberately. What the record's PRESENCE proves is
    that a real fit happened in this checkout and what may change afterwards —
    a one-way ratchet. What its ABSENCE proves is only that no fit has been
    recorded here: `data/` is gitignored, the file can be deleted, and a fit can
    have occurred in another checkout or on another machine. §8.6 says so in
    those words, and §8.8 makes the global claim an attestation rather than a
    fact the repository can prove.
    """
    if not FIRST_FIT_JSON.exists():
        return None
    try:
        return json.loads(FIRST_FIT_JSON.read_text())
    except json.JSONDecodeError as exc:
        raise FreezeStateUnverified(
            f"{paths.rel(FIRST_FIT_JSON)} is not readable JSON: {exc}. §8.7's "
            "regime turns on this record; an unreadable one is not an absent "
            "one, and the state it would establish cannot be established.")


def record_first_real_fit(*, where: str = "") -> dict[str, Any]:
    """Write §8.7's event once, and never rewrite it.

    §8.4 puts the event at the completion of **step 1** — the post-freeze
    results canary, which performs four real fits — and not at the
    single-opening exercise. Whatever runs first records it; the record is the
    harness bytes at the moment a real fit on the real archive first existed.

    §8.6 fixes the contents: "the UTC instant of the first real fit; the entry
    point that performed it; the Git HEAD commit at that moment; **the Git blob
    id of `reports/epl_widening_prereg_v2.md` at that commit**; and the SHA-256
    of both hashed harness files."
    """
    existing = first_fit_record()
    if existing is not None:
        return existing
    record = {
        "schema": SCHEMA_ID,
        "at": pd.Timestamp.now("UTC").isoformat(), "where": str(where),
        "harness": {name: (sha256_file(paths.REPO_ROOT / name)
                           if (paths.REPO_ROOT / name).exists() else None)
                    for name in HARNESS_FILES},
        # the DOCUMENT this fit belongs to, by name and by blob, so a record
        # carried over from another preregistration cannot be mistaken for one
        # of this document's own (§8.6, and §8.1 on why that matters here)
        "prereg": paths.rel(PREREG_PATH),
        "prereg_blob": git_blob_id(paths.rel(PREREG_PATH)),
        "commit": git_head(),
        "rule": ("§8.7: from this moment, any change to any hashed file "
                 "invalidates this preregistration — no note, no dated "
                 "appendix, no disclosure and no owner ruling restores it. The "
                 "invalidated run publishes, with its numbers and with the "
                 "reason, and a new preregistration begins in a new document."),
    }
    # §8.6: THE WITNESS LINE IS APPENDED FIRST, and the record written second.
    # The order matters and it is the safe one: a process that dies between the
    # two leaves a witness with no record, which :func:`first_fit_state` reads
    # as post-first-fit — the ratchet holds. The reverse order would leave a
    # record no witness names, which reads as forged, and a crash is not a
    # forgery.
    FIRST_FIT_WITNESS.parent.mkdir(parents=True, exist_ok=True)
    prior = witness_lines()
    prev = str(prior[-1]["chain"]) if prior else ""
    line = {k: v for k, v in record.items() if k != "rule"}
    line["chain"] = _witness_chain(prev, line)
    with FIRST_FIT_WITNESS.open("a") as fh:          # APPEND, never truncate
        fh.write(json.dumps(line, sort_keys=True, default=str) + "\n")
    FIRST_FIT_JSON.parent.mkdir(parents=True, exist_ok=True)
    FIRST_FIT_JSON.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return record


def assert_no_hashed_file_moved() -> None:
    """§8.7's second regime, enforced, and §8.6's validation of the record.

    Two checks, and v1 performed only the first:

    * after any real fit, nothing hashed moves; and
    * the record must be **this document's**. "On every later fit the guard
      re-reads it and raises `FreezeStateUnverified` if the recorded prereg blob
      is not the blob of the freeze commit, or if a hashed file's current bytes
      differ from the recorded ones." A record naming another document's blob —
      v1's, say — would otherwise let this run inherit a first-fit event that
      belongs to a preregistration that decides nothing.
    """
    record = first_fit_record()
    if record is None:
        # §8.6 reads the record and its append-only witness TOGETHER: a DELETED
        # record with a standing witness is post-first-fit and refuses, rather
        # than quietly reverting the regime to pre-fit (B6/NB5). An absent
        # record with an absent witness is the pre-first-fit state, and the
        # only one in which a fit may begin.
        first_fit_state()
        return

    # §8.6 fixes the record's contents. A record that omits a field cannot be
    # validated against it, and the superseded guard read every identity field
    # conditionally — "if present" — so a record with the fields stripped out
    # passed every check by carrying none of them.
    absent = [name for name in ("schema", "at", "where", "prereg",
                                "prereg_blob", "commit", "harness")
              if not record.get(name)]
    if absent:
        raise FreezeStateUnverified(
            f"{paths.rel(FIRST_FIT_JSON)} lacks {absent}. §8.6 fixes what the "
            "record carries — the instant, the entry point, the HEAD commit, "
            "the prereg blob at that commit and both harness digests — and a "
            "record that omits one cannot be checked against it. A missing "
            "field is not an absent record: the presence of the file is the "
            "one-way ratchet, and the ratchet does not run on partial state.")
    if str(record.get("schema")) != SCHEMA_ID:
        raise FreezeStateUnverified(
            f"{paths.rel(FIRST_FIT_JSON)} carries schema "
            f"{record.get('schema')!r} and this harness implements "
            f"{SCHEMA_ID!r}: the record belongs to another document's run.")

    named = str(record.get("prereg") or "")
    if named and named != paths.rel(PREREG_PATH):
        raise FreezeStateUnverified(
            f"{paths.rel(FIRST_FIT_JSON)} records a first real fit of "
            f"{named!r}, and this harness implements "
            f"{paths.rel(PREREG_PATH)!r}. §8.6 validates the record against the "
            "document it belongs to: a record carried over from another "
            "preregistration is not this document's first-fit event, and §8.1 "
            "is exactly why — v1's two ADVI fits ended v1 and v2 does not "
            "inherit them.")
    # ...and only now the pairing: a record whose identity fields are intact
    # but which no witness line names is forged or hand-written (B6/NB5).
    first_fit_state()

    recorded_blob = record.get("prereg_blob")
    current_blob = git_blob_id(paths.rel(PREREG_PATH))
    if recorded_blob and current_blob and recorded_blob != current_blob:
        raise FreezeStateUnverified(
            f"{paths.rel(FIRST_FIT_JSON)} records the prereg blob "
            f"{str(recorded_blob)[:12]}… and {paths.rel(PREREG_PATH)}'s blob at "
            f"HEAD is {str(current_blob)[:12]}…. §8.6: the guard raises when "
            "the recorded prereg blob is not the blob of the freeze commit. "
            "Either the document moved after the first real fit — which §8.7 "
            "makes an invalidation — or this record belongs to another run.")

    moved = []
    for name in HARNESS_FILES:
        path = paths.REPO_ROOT / name
        now = sha256_file(path) if path.exists() else None
        if now != (record.get("harness") or {}).get(name):
            moved.append(name)
    if moved:
        raise FreezeStateUnverified(
            f"{moved} changed after the first real fit of this experiment "
            f"(recorded {record.get('at')}). §8.7: **after any real fit on the "
            "real archive exists — whether or not it produced a delta, whether "
            "or not it was merged, whether or not anyone looked at it — any "
            "change to any hashed file INVALIDATES this preregistration.** No "
            "note, no dated appendix, no disclosure and no owner ruling "
            "restores it. The invalidated run publishes, with its numbers and "
            "with the reason it was invalidated, and a new preregistration "
            "begins in a new document with its own freeze.")


def _guard_ledger_location(path: Path, harness_frozen: bool) -> None:
    """The preregistered run directory is closed until §8.3's freeze commit.

    §8.3 step 3: "Only then does the first real fit run." §7.3 permits — and this
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
                f"refusing to write {paths.rel(path)} before §8.3's harness-hash "
                "freeze commit exists. §10: 'A real-archive fit runs before the "
                "§8.3 freeze commit' invalidates the preregistration. Audit runs "
                "are legitimate and §7.3 requires them — give them their own "
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
    """One paired fixture: BOTH arms from the same posterior (§2.3).

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
        #: §2.3's estimand delta: Arm A minus Arm B, both from ONE posterior.
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
            #: §2.3: Arm B IS recomputed now, and that is the repair. The
            #: superseded arm was an old rounded 1X2 projection the control
            #: could only bind AFTER projection, while mechanism (c) acts on the
            #: full scoreline grid before it.
            "recomputed": True,
        },
        "corpus_control": {
            "role": "the external identity control (§3.2 as §2.3 demotes it) — "
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
             ) -> dict[str, Any]:
    """Fit every point and append one JSONL row per fixture of its block.

    Resumable per fit, keyed ``cutoff|seed|config_sha256`` (§7.2): a key already
    complete in the ledger is skipped — not re-run, not re-scored, not appended
    twice. A fit's rows are written in ONE append so a crash leaves either all of
    them or a truncated tail that :func:`load_ledger` drops and this function
    re-runs.

    **§8.6: there is no ``harness_frozen`` parameter.** v1 took it from the
    caller and stamped it on every row; §7.2 rules that ``harness_frozen``
    "records **what the guard established**, never what a caller asserted", so
    it is read here from :func:`harness_freeze_status` and from nowhere else.
    Every row records it and the merge refuses a row that says False. Writing to
    the preregistered ledger location before the freeze is refused outright,
    because §10 makes such a run not this experiment.
    """
    assert_not_overridable(e_star=(float(e_star), E_STAR),
                           grid=(tuple(float(g) for g in grid),
                                 tuple(float(g) for g in (*E_GRID, E_STAR))))
    ledger_path = Path(ledger_path)
    # §8.6's public-surface closure runs FIRST, so a seam is refused by its own
    # name rather than by whichever guard happens to fire earliest. The
    # directory guard below is kept beside it — a pre-freeze `canary.json` in
    # the run directory is exactly what a later `--run` reads as "the canary
    # passed" — but it is no longer the only guard, and §8.2 keys the real one
    # to the artifact identity. That guard lives in :class:`Engine`, which is
    # the object that fits; an injected fitter fits nothing and is not gated by
    # it, so the closure gates the INJECTION instead.
    injected = [name for name, seam, ok in
                (("fitter", fitter, fitter is None),
                 ("engine", engine, engine is None or isinstance(engine, Engine)))
                if not ok]
    if injected:
        assert_seam_allowed(f"run_fits({'=..., '.join(injected)}=...)",
                            corpus=corpus, target=ledger_path.parent,
                            detail="an injected fitter or a substituted engine "
                                   "is not the production Engine §2.3 names")
    harness_frozen = _frozen_now()
    _guard_ledger_location(ledger_path, harness_frozen)
    if fitter is None:
        engine = engine or Engine(corpus, verbose=verbose,
                                  directory=ledger_path.parent)
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
# 10. THE CANARIES — §7.3. A canary that cannot fail is not a canary.
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


def corrupt_mask(played: pd.DataFrame, cutoff: str | pd.Timestamp, *,
                 side: str) -> np.ndarray:
    """Which rows §7.3's mutation selects, by NORMALISED date.

    §7.3 froze the selection: ``after`` selects ``date >= cutoff``, ``before``
    selects ``date < cutoff``. The mask is a function of its own so both legs
    can RECORD how many rows they selected — §7.3 requires that, and an empty
    mask is a refusal rather than a pass.
    """
    if side not in ("before", "after"):
        raise EvWidenError(f"side must be 'before' or 'after', not {side!r}")
    ts = pd.Timestamp(cutoff).normalize()
    dates = pd.to_datetime(played["date"]).dt.normalize()
    mask = (dates >= ts) if side == "after" else (dates < ts)
    return mask.to_numpy(bool)


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
    ts = pd.Timestamp(cutoff).normalize()
    out = played.copy()
    mask = corrupt_mask(played, ts, side=side)
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
    """§7.3's two-legged canary, because the existing one cannot see this input.

    ``epl.walkforward.point_in_time_canary`` rewrites RESULTS and compares
    forecasts. That is the right check for a fit and the wrong one for this
    experiment: the quantity under test is a sum over archive ROWS, and a canary
    that never touches the row set cannot see whether the predicate's input
    leaks.

    * **Negative leg** — corrupt every archive row dated on or after the cutoff
      and demand every ``e(t, C)`` and BOTH provisional sets bit-identical.
    * **Positive control** — corrupt the rows BEFORE the cutoff and demand ``e``
      moves by more than 1e-9.

    §7.3 FREEZES THE COMPARISON, and the repair is that the negative leg is a
    BOUND rather than a tolerance: the evidence vector over the corpus's clubs
    is compared with ``numpy.array_equal`` on the float64 values **before
    rounding**. Both provisional sets are compared by set equality; both legs
    record the number of rows their mask selected; an empty mask is a refusal,
    never a pass.

    ``provisional_fn`` maps a played frame to the incumbent provisional set; the
    run passes the real one (a store plus ``count_volatility_arm``) and a test
    passes a stub. When it is ``None`` only the evidence legs run, and the record
    says so rather than implying a check that did not happen.
    """
    ts = pd.Timestamp(cutoff).normalize()
    clubs = [str(c) for c in clubs]
    base = effective_evidence(ts, played, clubs)
    base_vec = np.array([base[c] for c in clubs], dtype=float)

    n_after = int(corrupt_mask(played, ts, side="after").sum())
    after = corrupt_archive(played, ts, side="after")
    after_e = effective_evidence(ts, after, clubs)
    after_vec = np.array([after_e[c] for c in clubs], dtype=float)
    #: §7.3: BIT equality on the unrounded float64 vector, not a tolerance.
    negative_equal = bool(np.array_equal(after_vec, base_vec))
    negative = float(np.abs(after_vec - base_vec).max()) if clubs else 0.0

    n_before = int(corrupt_mask(played, ts, side="before").sum())
    before = corrupt_archive(played, ts, side="before")
    before_e = effective_evidence(ts, before, clubs)
    before_vec = np.array([before_e[c] for c in clubs], dtype=float)
    positive = float(np.abs(before_vec - base_vec).max()) if clubs else 0.0

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
        "comparator": "numpy.array_equal on the unrounded float64 evidence "
                      "vector (§7.3: a bound, not a tolerance)",
        "negative_leg_rows_selected": n_after,
        "positive_control_rows_selected": n_before,
        "negative_leg_array_equal": negative_equal,
        "negative_leg_max_abs_diff": float(negative),
        "positive_control_max_abs_diff": float(positive),
        "provisional_sets_identical": sets_equal,
        "provisional_checked": provisional_fn is not None,
        "mutation": {
            "home_key": f"{_CANARY_PREFIX}h{{i}}",
            "away_key": f"{_CANARY_PREFIX}a{{i}}",
            "fthg": 9, "ftag": 9, "dates": "not touched",
            "note": "per-row unique sentinels, because features' duplicate-match "
                    "dedup collapses content-identical rows (fixed at 06bd431)"},
        "detail": set_detail,
        "PASS": bool(negative_equal and n_after > 0 and n_before > 0
                     and positive > 1e-9 and (sets_equal is not False)),
    }
    if not out["PASS"]:
        raise EvidenceCanaryFailed(
            "the evidence canary did not pass: the negative leg's evidence "
            f"vector array_equal = {negative_equal!r} (must be True; largest "
            f"difference {negative:.3g}) over {n_after} corrupted row(s), the "
            f"positive control moved `e` by {positive:.3g} (must exceed 1e-9) "
            f"over {n_before} corrupted row(s), provisional sets identical "
            f"= {sets_equal!r}. §7.3: a canary that cannot fail is not a canary, "
            "and one that fails is a leak in the predicate's own input.")
    return out


def identity_canary(fitter: Callable[..., dict], point: FitPoint,
                    corpus: pd.DataFrame, *, e_star: float = 0.0
                    ) -> dict[str, Any]:
    """§7.3: an ``e*`` low enough to add nobody must reproduce the corpus rows.

    Zero widening is byte-identical, and the demand is ``np.array_equal`` rather
    than a tolerance. It is the cheapest possible statement of the experiment's
    central claim — that the treatment is a pure re-key and adds nothing on its
    own — and the one that would break loudest if the "treatment" were quietly
    doing something else as well.

    ``fitter`` is a seam §8.6 names in its own words — "inject an alternative
    implementation (fitter, engine, runner, parity, mc)" — so it asks the guard.
    The canary writes nothing, so the artifacts alone decide: a synthetic corpus
    is audited freely and the pinned one is not.
    """
    assert_seam_allowed("identity_canary(fitter=)", corpus=corpus,
                        target=NO_TARGET,
                        detail="an injected fitter in §7.3's identity canary")
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

    §7.3 binds the direction canary to the production path, and the production
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
    """§7.3's direction canary, as §7.3 repairs it on both halves.

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
            "mix at the frozen alpha, and §7.3 rules that a canary in which "
            "every fixture took the documented edge branch proved nothing.")
    return record


def run_canary(runner: Callable[[], dict[str, Any]] | None = None, *,
               played: pd.DataFrame | None = None,
               corpus: pd.DataFrame | None = None,
               directory: Path | str | None = None,
               target: Path | str | None = None) -> dict[str, Any]:
    """§7.3's results canary: `epl.walkforward.point_in_time_canary`.

    A precondition of the run, on the real archive, AFTER the freeze — never a
    result. ``PASS: false`` stops the run.

    **It is gated like every other fit surface.** The canary performs FOUR REAL
    FITS — `_forecasts` is called four times — and §8.4 makes it step 1, the
    first post-freeze act and the first real fits of this document. The review's
    NEW-B2 found it exported without :func:`assert_may_fit`: a public function
    that fits the real archive four times with no freeze check at all. The
    ``runner`` seam is closed on §8.6's terms as well, because a supplied
    runner is an alternative implementation of the precondition.

    On failure the record travels ON the exception, so the caller can publish it
    before the raise reaches the process boundary (§8.4 step 1: "`PASS: false`
    on any leg stops the experiment and **the failure publishes**").
    """
    if runner is not None:
        assert_seam_allowed("run_canary(runner=...)", played=played,
                            corpus=corpus, target=target,
                            detail="a supplied runner is not "
                                   "epl.walkforward.point_in_time_canary")
    may = assert_may_fit("epl.walkforward.point_in_time_canary (four real fits)",
                         played=played, corpus=corpus, directory=directory)
    if runner is None:
        from epl import walkforward as wf
        runner = wf.point_in_time_canary
    if may["frozen"] and may["real_artifacts"]:
        record_first_real_fit(where="the results canary (§8.4 step 1)")
    started = time.perf_counter()
    out = dict(runner())
    out.setdefault("schema", SCHEMA_ID)
    out["blas_threads"] = blas_threads()
    out["seconds"] = round(time.perf_counter() - started, 1)
    if not out.get("PASS"):
        exc = CanaryFailed(
            f"the point-in-time canary did not pass: max |Δp| before the cutoff "
            f"= {out.get('max_abs_diff_before_cutoff')!r} (must be 0), positive "
            f"control = {out.get('max_abs_diff_positive_control')!r} (must "
            "move). §7.3: the run does not start.")
        exc.record = out                                   # type: ignore[attr-defined]
        raise exc
    return out


def write_canaries(record: dict[str, Any], path: Path | str | None = None,
                   ) -> Path:
    """Every canary's full dict, on the record whichever way it fell."""
    path = Path(path) if path is not None else CANARY_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return path


def sequence_marker_path(step: str) -> Path:
    """§8.4's marker for one step, at the one fixed location."""
    if step not in SEQUENCE_STEPS:
        raise SequenceViolation(
            f"{step!r} is not one of §8.4's five steps {SEQUENCE_STEPS}. The "
            "sequence is frozen and nothing else may run on the real archive "
            "between its steps.")
    return SEQUENCE_DIR / f"{step}.json"


def read_sequence_marker(step: str) -> dict[str, Any] | None:
    path = sequence_marker_path(step)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SequenceViolation(
            f"{paths.rel(path)} is not readable JSON: {exc}. An unreadable "
            "marker is not a completed step.")


def assert_sequence_marker_wellformed(step: str, marker: dict[str, Any]
                                      ) -> dict[str, Any]:
    """§8.4 fixes what a marker records, and a file that records none of it is
    not one.

    NB6: "``{}`` is accepted because ``require_sequence`` permits missing/null
    ``freeze_commit`` and validates no step/schema/hashes/product". Nothing here
    proves the STEP happened — a marker is a file and §8.6 says plainly what a
    file can and cannot establish — but a marker that does not even claim to
    describe this step of this document under this freeze cannot unlock the
    next one.
    """
    absent = [name for name in ("schema", "step", "completed_at", "harness",
                                "produced_digest")
              if marker.get(name) in (None, "", {})]
    head = git_head()
    if head is not None and not marker.get("freeze_commit"):
        absent.append("freeze_commit")
    # v3 §8.6: "It must carry `complete: true` — a missing `complete` is FALSE,
    # never true-by-absence." NB6 found the key optional and its absence read as
    # completion, so a marker that never claimed to have finished unlocked the
    # next step. It is REQUIRED here and its value is judged in
    # :func:`require_sequence`, because `complete: false` is a legitimate marker
    # (§8.4's durable failure) and an ABSENT key is not.
    if "complete" not in marker or not isinstance(marker.get("complete"), bool):
        absent.append("complete")
    if absent:
        raise SequenceViolation(
            f"{paths.rel(sequence_marker_path(step))} lacks {absent}. §8.4 "
            "fixes what a marker records — the step name, whether it "
            "completed, the UTC time, the freeze commit under which it was "
            "written, the harness file digests at that moment, and a digest of "
            "what the step produced — and a file carrying none of it is not a "
            "marker for this run. An empty JSON object is not a completed step.")
    # ...and the product digest is RECOMPUTED rather than read (v3 §8.6): a
    # marker whose `produced` was edited while its digest was left behind
    # describes a product that no longer exists in that form, and unlocks
    # nothing.
    recomputed = hashlib.sha256(
        json.dumps(marker.get("produced"), sort_keys=True,
                   default=str).encode("utf-8")).hexdigest()
    if str(marker.get("produced_digest")) != recomputed:
        raise SequenceViolation(
            f"{paths.rel(sequence_marker_path(step))} records "
            f"produced_digest {str(marker.get('produced_digest'))[:12]}… and "
            f"the digest recomputed over its own `produced` field is "
            f"{recomputed[:12]}…. §8.6: 'the product digest it names is "
            "RECOMPUTED and compared, so a marker describing a product that no "
            "longer exists in that form unlocks nothing'.")
    # ...and THAT digest is over the marker's own dictionary, which is what the
    # adjudication of 2026-08-29 found insufficient (F10, NB6): "it recomputes a
    # digest of the marker's own embedded `produced` dictionary, not the current
    # bytes of the named product. Product deletion or mutation therefore leaves
    # the marker valid." The marker names its products by path, and every one of
    # them is RE-HASHED here against the bytes on disk right now.
    produced = marker.get("produced")
    products = (produced or {}).get(_PRODUCTS_KEY) \
        if isinstance(produced, dict) else None
    moved = []
    for rel_path, recorded_sha in sorted((products or {}).items()):
        target = paths.REPO_ROOT / str(rel_path)
        actual = sha256_file(target) if target.exists() else None
        if actual != recorded_sha:
            moved.append(f"{rel_path} recorded {str(recorded_sha)[:12]}… and "
                         + ("is not on disk" if actual is None
                            else f"now hashes to {actual[:12]}…"))
    if moved:
        raise SequenceViolation(
            f"{paths.rel(sequence_marker_path(step))} names PRODUCT bytes that "
            f"are not the bytes on disk: {'; '.join(moved)}. §8.4's marker is a "
            "claim that this step produced something, and a claim about a file "
            "that is gone — or is no longer that file — unlocks nothing. The "
            "product digests are re-hashed on every read, not read back out of "
            "the marker that asserted them.")
    if str(marker.get("schema")) != SCHEMA_ID:
        raise SequenceViolation(
            f"{paths.rel(sequence_marker_path(step))} carries schema "
            f"{marker.get('schema')!r}, not {SCHEMA_ID!r}: it describes another "
            "document's run.")
    if str(marker.get("step")) != step:
        raise SequenceViolation(
            f"{paths.rel(sequence_marker_path(step))} records step "
            f"{marker.get('step')!r} and sits at {step}'s path: a marker "
            "renamed into another step's slot is not that step's completion.")
    moved = [name for name in HARNESS_FILES
             if (marker.get("harness") or {}).get(name)
             != (sha256_file(paths.REPO_ROOT / name)
                 if (paths.REPO_ROOT / name).exists() else None)]
    if moved:
        raise SequenceViolation(
            f"{paths.rel(sequence_marker_path(step))} records harness digests "
            f"for {moved} that are not the current bytes. §8.4's steps run "
            "under ONE freeze; a hashed file that moved between them means the "
            "later step is not the step the earlier marker unlocked, and §8.7 "
            "makes such a change an invalidation once a real fit exists.")
    return marker


#: The `produced` shape §8.4's OPEN CLAIM carries. A marker holding it is a
#: step that has started and not finished: it is `complete: false`, so it
#: unlocks nothing, and the only write that may replace it is that same step's
#: own completion.
_CLAIM_KEY = "claimed"

#: §8.4's PRODUCT LEDGER, inside a marker's own `produced` object: a map from
#: repo-relative path to the SHA-256 of what that file held when the step
#: finished. :func:`assert_sequence_marker_wellformed` re-hashes every one of
#: them on every read (adjudication F10), so a marker cannot outlive the bytes
#: it stands for.
_PRODUCTS_KEY = "products"


def product_digests(*targets: Path | str) -> dict[str, str]:
    """{repo-relative path: sha256} over the bytes each product actually holds.

    A product the writer cannot see is not a product: an absent file raises
    rather than recording ``None``, because a recorded ``None`` would re-hash to
    ``None`` and a marker naming a file that was never written would then verify
    against the file's continued absence.
    """
    out: dict[str, str] = {}
    for target in targets:
        path = Path(target)
        if not path.exists():
            raise SequenceViolation(
                f"{paths.rel(path)} is not on disk, so §8.4's marker cannot "
                "record what this step produced. A marker that names a product "
                "it never saw is a claim with nothing behind it.")
        out[paths.rel(path)] = sha256_file(path)
    return out


#: §8.4's RECLAIM LEDGER, inside the claim's own `produced` object. It is
#: append-only: :func:`claim_sequence_step` reads what is there and adds one
#: dated record, and :func:`write_sequence_marker` carries the whole list into
#: the completion marker, so the history of a resumed step survives the step.
_RECLAIM_KEY = "reclaims"


def claim_sequence_step(step: str, *, note: str) -> dict[str, Any]:
    """Open §8.4's write-once marker BEFORE the step spends anything.

    v3 §8.4, P5-B8:

    > **step 5 claims its marker BEFORE it simulates**, not after: the
    > write-once marker is opened at the start of the step and completed at its
    > end, so a second attempt is refused before a single fit is spent rather
    > than after a second outcome exists.

    The review found the table branch checking only that step 4 preceded step 5,
    performing the whole expensive run, and *then* attempting the marker — so a
    caller who had seen the first outcome could run the leg again and have the
    second outcome exist before the conflict was raised. An open claim inverts
    the order: the second attempt dies at the claim.

    **THE RECLAIM RULE** (adjudication of 2026-08-29, F3). The v3 arrangement
    refused an open claim as well, and the review found that this made §7.2's
    promise unkeepable: "an open `complete: false` claim permanently refuses the
    official retry while §7.2 promises resumability", and `run_table` says a
    crash costs only the in-flight cell. F3 rules the two apart, and the marker
    is what separates them:

    * a **COMPLETED** step produced an outcome. Running it again after seeing
      that outcome is the second attempt §8.4 refuses, and no reclaim reopens
      it. The sequence stays once-only here, which is the whole of §4.4.
    * a **FAILED** step — §8.4's durable failure marker, `complete: false` with
      no open claim on it — has published its failure, and a continuation after
      it still needs "a new dated pre-freeze note written BEFORE the retry".
    * an **OPEN CLAIM** is a step that started and never finished. It produced
      no complete product, so there is no outcome to condition a retry on and
      nothing to put in a file drawer; refusing it makes a crashed four-hour leg
      unresumable. It may be re-claimed **once per dated reclaim record
      appended to the claim file** — append, never overwrite — so every
      resumption is on the record and a reader can count them.
    """
    existing = read_sequence_marker(step)
    head = git_head()
    reclaims: list[dict[str, Any]] = []
    if existing is not None and existing.get("freeze_commit") in (None, head):
        produced = existing.get("produced")
        produced = produced if isinstance(produced, dict) else {}
        claimed = produced.get(_CLAIM_KEY)
        if existing.get("complete"):
            raise SequenceViolation(
                f"{step} refuses: {paths.rel(sequence_marker_path(step))} "
                "already records a COMPLETED step under this freeze commit. "
                "§8.4's markers are written ONCE and the sequence is once-only "
                "for completed steps: this step produced its outcome, and a "
                "second run after that outcome exists is the file-drawer "
                "channel §4.4 closes. A continuation needs a new dated "
                "pre-freeze note written before the retry, not a re-run.")
        if not claimed:
            raise SequenceViolation(
                f"{step} refuses: {paths.rel(sequence_marker_path(step))} "
                f"already records a FAILED step under this freeze commit "
                f"({produced.get('failure')}). §8.4's durable failure marker is "
                "not an open claim — the step ran, it published its failure, "
                "and a continuation after it needs a new dated pre-freeze note "
                "written BEFORE the retry, not a re-run. The reclaim rule "
                "reaches open claims and nothing else.")
        # ---- the reclaim (F3): append one dated record, overwrite none ------
        reclaims = [dict(r) for r in (produced.get(_RECLAIM_KEY) or ())]
        reclaims.append({
            "at": pd.Timestamp.now("UTC").isoformat(),
            "note": str(note),
            "reclaimed": str(claimed),
            "freeze_commit": head,
            "harness": {name: (sha256_file(paths.REPO_ROOT / name)
                               if (paths.REPO_ROOT / name).exists() else None)
                        for name in HARNESS_FILES},
        })
    return _marker_bytes(step, produced={_CLAIM_KEY: str(note),
                                         _RECLAIM_KEY: reclaims},
                         complete=False)


def write_sequence_marker(step: str, *, produced: Any = None,
                          complete: bool = True) -> dict[str, Any]:
    """§8.4's marker, with everything the document asks it to carry.

    > Each marker records the step name, the UTC completion time, the freeze
    > commit under which it was written, the harness file digests at that
    > moment, and a digest of what the step produced. **A marker written under a
    > different freeze commit is not a marker for this run.**

    The freeze commit is what makes the last sentence mechanical: a marker left
    over from a run under an earlier freeze reads as absent, so the step it
    would have unlocked refuses.

    **It writes once.** The markers are MANIFEST members (§9.3), and §9.3's
    manifest is computed at publication; the review's NEW-B7 found the
    publication pass rewriting `step4_merge.json` after hashing it, which left
    the manifest describing a file that no longer existed in that form. A second
    call under the same freeze commit therefore RE-VERIFIES: it compares what
    the step produced against what the marker records, returns the marker
    unchanged, and refuses if the two disagree.

    ``complete=False`` records a step that RAN AND FAILED. It is not a
    completion marker — :func:`require_sequence` refuses on it exactly as it
    refuses on an absent one — and its job is to make a failure durable
    (§8.4 step 1: "the failure publishes") and a silent retry impossible.
    """
    path = sequence_marker_path(step)
    head = git_head()
    existing = read_sequence_marker(step)
    # §8.4's reclaim ledger travels with the step (adjudication F3): whatever
    # the open claim — or an already-written completion — recorded is carried
    # into what this call writes, so a resumed step's history survives its
    # completion and the re-verification below compares like with like.
    if existing is not None and existing.get("freeze_commit") in (None, head) \
            and isinstance(produced, dict):
        prior = existing.get("produced")
        carried = list((prior or {}).get(_RECLAIM_KEY) or ()) \
            if isinstance(prior, dict) else []
        if carried:
            produced = {**produced, _RECLAIM_KEY: carried}
    digest = hashlib.sha256(
        json.dumps(produced, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    if existing is not None and existing.get("freeze_commit") in (None, head):
        # ...unless it is this step's own OPEN CLAIM, in which case this write
        # is the completion the claim was opened for and is the ONE legal
        # transition (§8.4, P5-B8). Any other second write is a re-run.
        if (not existing.get("complete")
                and (existing.get("produced") or {}).get(_CLAIM_KEY)):
            existing = None
        elif existing.get("produced_digest") != digest or \
                bool(existing.get("complete", False)) != bool(complete):
            raise SequenceViolation(
                f"{paths.rel(path)} already records {step} under this freeze "
                f"commit and what it recorded is not what this call produced "
                f"({str(existing.get('produced_digest'))[:12]}… against "
                f"{digest[:12]}…). §8.4's markers are written once and re-read "
                "afterwards: a step that runs twice under one freeze and "
                "produces two different things has not been resumed, it has "
                "been re-run, and the second run is not the step the first "
                "marker unlocked.")
        if existing is not None:
            return existing
    return _marker_bytes(step, produced=produced, complete=complete)


def _marker_bytes(step: str, *, produced: Any = None,
                  complete: bool = True) -> dict[str, Any]:
    """Write §8.4's marker file. The write-once decision is the caller's — it
    belongs to :func:`write_sequence_marker` and :func:`claim_sequence_step`,
    which make it differently."""
    path = sequence_marker_path(step)
    marker = {
        "schema": SCHEMA_ID, "step": step, "complete": bool(complete),
        "completed_at": pd.Timestamp.now("UTC").isoformat(),
        "freeze_commit": git_head(),
        "prereg": paths.rel(PREREG_PATH),
        "harness": {name: (sha256_file(paths.REPO_ROOT / name)
                           if (paths.REPO_ROOT / name).exists() else None)
                    for name in HARNESS_FILES},
        "produced": produced,
        "produced_digest": hashlib.sha256(
            json.dumps(produced, sort_keys=True,
                       default=str).encode("utf-8")).hexdigest(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker, indent=2, default=str) + "\n")
    return marker


def sequence_report() -> dict[str, dict[str, Any]]:
    """§9.1's `sequence` field: the five markers, each with what it recorded.

    "`sequence` — the five markers of §8.4, each with its recorded freeze commit
    and completion time." A step that never ran says `present: false` rather
    than being absent from the object, so a reader can see which of the five the
    run reached.
    """
    out: dict[str, dict[str, Any]] = {}
    for step in SEQUENCE_STEPS:
        marker = read_sequence_marker(step)
        out[step] = {
            "present": marker is not None,
            "path": paths.rel(sequence_marker_path(step)),
            "freeze_commit": (marker or {}).get("freeze_commit"),
            "completed_at": (marker or {}).get("completed_at"),
            "produced_digest": (marker or {}).get("produced_digest"),
            "produced": (marker or {}).get("produced"),
        }
    return out


def require_sequence(step: str, *, enforce: bool | None = None
                     ) -> dict[str, Any]:
    """§8.4: a step refuses unless its predecessor's completion marker exists.

    ``enforce`` left at ``None`` derives from the freeze state, because §8.4 is
    *the frozen post-freeze sequence*: before §8.3's commit there is no run for
    the markers to describe, and the synthetic audit that §8.2 requires would
    otherwise have to fabricate them.

    v1 had no markers at all — ``require_run_preconditions`` checked only the
    canary — so a merge could run without shards and a table could run before a
    merge, which is precisely what its launcher did.
    """
    if step not in SEQUENCE_STEPS:
        raise SequenceViolation(f"{step!r} is not one of §8.4's five steps")
    if enforce is False and _frozen_now():
        # §8.6: attesting a lifecycle state is one of the four closed effects,
        # and "the sequence does not apply" is that attestation. It is legitimate
        # exactly where `enforce=None` would DERIVE it — before §8.3's commit,
        # when there is no run for the markers to describe and §8.2's synthetic
        # audit would otherwise have to fabricate them. Under the freeze there is
        # a run, and no caller turns §8.4 off for it.
        raise SequenceViolation(
            f"{step} refuses `enforce=False`: §8.3's freeze commit has landed, "
            "so §8.4's five steps are the run this document preregisters and "
            "their markers describe it. The flag exists for the pre-freeze "
            "audit, where `enforce=None` derives the same answer; under the "
            "freeze it would be a caller attesting a lifecycle state, which "
            "§8.6 closes.")
    if enforce is None:
        enforce = bool(harness_freeze_status()["frozen"])
    index = SEQUENCE_STEPS.index(step)
    if index == 0 or not enforce:
        return {"step": step, "enforced": bool(enforce), "predecessor": None,
                "PASS": True}
    predecessor = SEQUENCE_STEPS[index - 1]
    marker = read_sequence_marker(predecessor)
    if marker is None:
        raise SequenceViolation(
            f"{step} refuses: {predecessor}'s completion marker is not at "
            f"{paths.rel(sequence_marker_path(predecessor))}. §8.4 freezes five "
            "steps in one order and nothing else may run on the real archive "
            "between them; each step refuses unless its predecessor's marker "
            "exists.")
    assert_sequence_marker_wellformed(predecessor, marker)
    head = git_head()
    if head is not None and marker.get("freeze_commit") not in (None, head):
        raise SequenceViolation(
            f"{step} refuses: {predecessor}'s marker was written under a "
            f"different freeze commit ({str(marker.get('freeze_commit'))[:12]}… "
            f"against {head[:12]}…). §8.4: a marker written under a different "
            "freeze commit is not a marker for this run — it describes a step "
            "of a run the current freeze does not cover.")
    # v3 §8.6: "It must carry `complete: true` — a missing `complete` is FALSE,
    # never true-by-absence." The review's NB6 found the opposite default, so a
    # marker that never claimed completion unlocked the next step.
    if not bool(marker.get("complete", False)):
        raise SequenceViolation(
            f"{step} refuses: {predecessor} RAN AND FAILED, and its marker "
            f"records the failure ({marker.get('produced', {}).get('failure')}). "
            "§8.4's markers are COMPLETION markers; a failed step has not "
            "completed and unlocks nothing. The failure has published, and a "
            "continuation after it needs a new dated pre-freeze note written "
            "BEFORE the retry — a retry conditioned on the failure is the "
            "file-drawer channel §4.4 closes.")
    return {"step": step, "enforced": True, "predecessor": predecessor,
            "marker": marker, "PASS": True}


def require_run_preconditions(directory: Path | str | None = None, *,
                              path: Path | str | None = None,
                              require_results: bool | None = None,
                              step: str | None = None,
                              require_sequence_marker: bool | None = None,
                              ) -> dict[str, Any]:
    """:data:`RUN_ORDER`, enforced rather than declared — **all of it**.

    v1's version "checks only the canary", which is how its launcher could run
    the table before the merge and how a merge could score shards that never
    ran. This one checks **both** preconditions a step has: §7.3's canary record
    and §8.4's predecessor marker.

    The canaries are read from their WRITTEN record, so the order holds across
    processes and across shards — four workers each re-running them would be
    four answers to a question with one.

    ``require_results`` decides whether §7.3's RESULTS canary
    (``walkforward.point_in_time_canary``) must be on that record. It costs real
    fits, so ``--no-results-canary`` exists for the synthetic audit — and that
    flag must not be able to follow the run past the freeze. Left at ``None`` it
    is derived from :func:`harness_freeze_status`: once §8.3's commit has
    landed, the preregistered run demands the canary §7.3 pre-states as "run
    once as a precondition on the real archive AFTER the freeze".

    ``step`` names which of §8.4's five steps is about to run; its predecessor's
    marker is then required on the same terms.
    """
    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    path = Path(path) if path is not None else directory / CANARY_NAME
    if not path.exists():
        raise CanaryFailed(
            f"no canary record at {paths.rel(path)}. §7.3 makes the canaries a "
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
            f"({failed or 'no PASS field'}). §7.3: the run does not start.")

    if require_results is None:
        require_results = bool(harness_freeze_status()["frozen"])
    if require_results and not rec.get("results_canary_run"):
        raise CanaryFailed(
            f"the canary record at {paths.rel(path)} was written with "
            "--no-results-canary, so `epl.walkforward.point_in_time_canary` "
            "never ran. §7.3 makes it a precondition of the run on the REAL "
            "archive after the freeze; skipping it is a concession to the "
            "synthetic audit's clock and may not follow the run past §8.3's "
            "commit. Re-run `--canary` without the flag.")

    # §8.4's other half, which v1 never checked at all.
    if step is not None:
        rec = dict(rec)
        rec["sequence"] = require_sequence(step,
                                           enforce=require_sequence_marker)
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

    §2.3: the baseline is ``rps_B`` — the same posterior's incumbent pass — and
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


def assert_structural_zeros(rows: Sequence[dict[str, Any]], *,
                            e_star: float = E_STAR) -> dict[str, Any]:
    """§2.3's structural-zero guard, **TWO-SIDED**, at the merge.

    > Every merged row that is **not** in the treated set must carry a delta of
    > exactly 0.0 — this covers both classes, and both are refusals:
    >
    > * a fixture whose `e_min ≥ e*` (outside the thin population entirely)
    >   carrying a non-zero delta; and
    > * a **thin but already incumbent-widened** fixture — one of the 33 §2.3
    >   states "carry a delta of exactly 0.0 by construction" — carrying a
    >   non-zero delta.
    >
    > A guard that catches only the first class leaves the arithmetic §2.3
    > relies on unenforced, because the 33 are exactly the rows whose zero-ness
    > makes the 85-population's mean a known multiple of the treated mean.

    v1 scanned only the first class. A non-zero delta on one of the 33 does not
    dilute the estimand — it falsifies the arithmetic the estimand is stated in.
    """
    stray = sorted(str(r["match_id"]) for r in rows
                   if float(r["e_min"]) >= float(e_star)
                   and float(r["delta"]) != 0.0)
    if stray:
        raise UntreatedMoved(
            f"{len(stray)} fixture(s) with e_min >= e* — outside the thin "
            f"population entirely — carry a non-zero delta (first: "
            f"{stray[:5]}). Under ADD their delta is zero by construction, and "
            "the full-population secondary is stated as an arithmetic identity "
            "that would be false if this were true.")
    already = sorted(str(r["match_id"]) for r in rows
                     if float(r["e_min"]) < float(e_star)
                     and bool(r["incumbent_widened"])
                     and float(r["delta"]) != 0.0)
    if already:
        raise UntreatedMoved(
            f"{len(already)} thin fixture(s) that the incumbent predicate "
            f"ALREADY WIDENS carry a non-zero delta (first: {already[:5]}). "
            "§2.3: 33 of the 85 'carry a delta of exactly 0.0 by construction' "
            "— they are the rows whose zero-ness makes the 85-population's mean "
            "a known multiple of the treated mean, so a non-zero one here does "
            "not dilute the estimand, it falsifies the arithmetic the estimand "
            "is stated in. This is the second half of §2.3's two-sided guard, "
            "and a guard that caught only the first half left this class "
            "averaged straight in.")
    return {"n_rows": len(rows), "stray": 0, "already_widened": 0, "PASS": True}


def measured_controls(rows: Sequence[dict[str, Any]], *,
                      e_star: float = E_STAR) -> dict[str, Any]:
    """§9.1: the two controls v1 hard-coded, **read off the merged rows**.

    > `controls.untreated_moved` and `controls.predicate_mismatch` must be
    > **read off the merged rows** — the count of merged rows whose recomputed
    > provisional set disagreed with the ledger's, and the count of non-treated
    > merged rows carrying a non-zero delta — not written as
    > `{n: 0, PASS: true}` constants. Their values are true by construction only
    > because a refusal stops the run first; **a verdict file that always prints
    > PASS for a control nobody measured is exactly the shape this document's
    > own "a test that cannot fail is not a test" objects to.**

    In a run that completed, both counts ARE zero — the refusals stopped
    anything else long before the merge. The difference is that they are now the
    answer to a question rather than the question's assumed answer.
    """
    moved = [str(r["match_id"]) for r in rows
             if not bool(r.get("treated")) and float(r.get("delta") or 0.0) != 0.0]
    mismatched = []
    for row in rows:
        fit = row.get("fit") or {}
        recomputed = fit.get("provisional_incumbent")
        recorded = fit.get("provisional_ledger")
        if recomputed is None or recorded is None:
            continue
        if sorted(str(t) for t in recomputed) != sorted(str(t) for t in recorded):
            mismatched.append(str(row.get("cutoff")))
    return {
        "untreated_moved": {
            "n": len(moved), "refusal": "UntreatedMoved",
            "PASS": not moved, "first": sorted(set(moved))[:5],
            "measured": "the count of non-treated merged rows carrying a "
                        "non-zero delta (§9.1), both classes of §2.3's "
                        "two-sided guard"},
        "predicate_mismatch": {
            "n": len(set(mismatched)), "refusal": "PredicateMismatch",
            "PASS": not mismatched, "first": sorted(set(mismatched))[:5],
            "measured": "the count of merged rows whose recomputed provisional "
                        "set disagreed with the ledger's (§9.1)"},
        "note": ("both are true by construction only because a refusal stops "
                 "the run first; §9.1 requires them measured rather than "
                 "asserted, because a control nobody measured always prints "
                 "PASS"),
    }


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
    assert_not_overridable(n_boot=(n_boot, N_BOOT), seed=(seed, BOOTSTRAP_SEED),
                           e_star=(e_star, E_STAR),
                           grid=(tuple(float(g) for g in grid),
                                 tuple(float(g) for g in E_GRID)))
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

    assert_structural_zeros(rows, e_star=e_star)

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

    treated_sd = (float(treated_deltas.std(ddof=1))
                  if treated_deltas.size > 1 else None)
    se = head.get("se_iid")
    power = {
        # §6 is the power analysis: done blind, before any delta existed, and
        # committed code at `epl.evwiden.power_simulation`. What lives HERE is
        # §6.5's other half — "after the run, the REALISED paired SD of the
        # treated deltas and the MDE recomputed at it" — which decides nothing
        # and moves no threshold. `realised_power_object` computes the joint
        # MDE at that SD where the evidence file is assembled.
        "realised": {
            "sd_paired_thin": head.get("sd"),
            "sd_paired_treated": treated_sd,
            "se_iid": se,
            "mde_80pct_two_sided_5pct": (float(_MDE_Z * se) if se else None),
            "multiplier": _MDE_Z,
            "note": "the two-sided-test-against-zero MDE, which is NOT gate "
                    "(i)'s: gate (i) is a threshold AT the bar, so an "
                    "80%-power MDE equal to the bar is unattainable by "
                    "construction at any SD. §6.5's joint-gate MDE is a "
                    "DISTINCT quantity and is recomputed at the realised SD — "
                    "the §6.2 simulation re-run with s set to this value, at "
                    "the same R, seeds, grid and interpolation rule — and it "
                    "is published beside this one as `joint_mde` in "
                    "reports/evidence/widening.json. §6.5: a result document "
                    "that reports the two-sided quantity beside the realised "
                    "SD has not discharged the obligation.",
        },
        "frozen_scenarios": [{"scenario": n, "paired_sd": s, "source": src}
                             for n, s, src in POWER_SCENARIOS],
        "warning": POWER_WARNING,
        "decides": "nothing — no threshold in §4 moves in response",
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
# 11b. THE POWER SIMULATION — §6's analysis, §6's committed code
# ==========================================================================

#: §6's frozen structure. §6 gave the counts; the ASSIGNMENT of the 85
#: thin fixtures to their 62 week blocks is the pinned corpus's own, recomputed
#: by :func:`power_structure` under §8.2's read-only authorisation and checked
#: against these numbers.
POWER_N_THIN = 85
POWER_N_TREATED = 52
POWER_N_WEEK_BLOCKS = 62
POWER_N_SEASONS = 6
POWER_THIN_BY_SEASON = (26, 11, 12, 12, 12, 12)
POWER_TREATED_BY_SEASON = (21, 4, 7, 6, 7, 7)

#: §6's three scenarios, frozen blind: no delta of this experiment exists, so
#: none of them is informed by one.
POWER_SCENARIOS: tuple[tuple[str, float, str], ...] = (
    ("A freshness-scale", 0.005262,
     "reports/epl_freshness_result.json's own sd over its 1,699 paired deltas"),
    ("B anchoring-scale", 0.014449,
     "reports/epl_anchoring_result.md's past-only estimand, paired sd over "
     "2,280 fixtures"),
    ("C mechanism-scale", 0.036,
     "a deliberately pessimistic extrapolation, named as invented: about 2.3x "
     "beyond the largest committed point of the anchoring weight ladder"),
)
POWER_RHOS: tuple[float, ...] = (0.0, 0.5)
POWER_REPLICATES = 2_000
POWER_SEED = 20260827

#: §6's MDE search grid: 101 points, step 2e-4, delta the injected TREATED
#: effect in RPS.
POWER_GRID_STEP = 2e-4
POWER_GRID_POINTS = 101

#: §6's bar on the treated scale, exactly: 0.0010 x 85 / 52. Evaluated at its
#: own seed and replicates, never interpolated from the grid.
POWER_BAR = -(0.0010 * POWER_N_THIN / POWER_N_TREATED)

#: The six published rows AS CORRECTED by the dated note of 2026-08-28 (the
#: §6 remedy: the scratch stream was unrecoverable, so the committed
#: implementation's numbers became the document's numbers before the freeze).
PUBLISHED_POWER: tuple[dict[str, Any], ...] = (
    {"scenario": "A freshness-scale", "rho": 0.0, "power_at_bar": 0.451,
     "mde_estimand": -0.001446, "ratio": 1.45, "power_at_2x": 0.976},
    {"scenario": "A freshness-scale", "rho": 0.5, "power_at_bar": 0.408,
     "mde_estimand": -0.001571, "ratio": 1.57, "power_at_2x": 0.950},
    {"scenario": "B anchoring-scale", "rho": 0.0, "power_at_bar": 0.122,
     "mde_estimand": -0.003741, "ratio": 3.74, "power_at_2x": 0.321},
    {"scenario": "B anchoring-scale", "rho": 0.5, "power_at_bar": 0.091,
     "mde_estimand": -0.004180, "ratio": 4.18, "power_at_2x": 0.267},
    {"scenario": "C mechanism-scale", "rho": 0.0, "power_at_bar": 0.050,
     "mde_estimand": -0.009309, "ratio": 9.31, "power_at_2x": 0.087},
    {"scenario": "C mechanism-scale", "rho": 0.5, "power_at_bar": 0.047,
     "mde_estimand": -0.010522, "ratio": 10.52, "power_at_2x": 0.080},
)

POWER_WARNING = (
    "This design is underpowered against effects near its own bar unless the "
    "realised paired SD comes in at or below the freshness scale. At the "
    "anchoring scale a true treated effect of -0.0016 would be missed about "
    "nine times in ten. A MISS IS THEREFORE SUBSTANTIALLY UNINFORMATIVE: 'no "
    "adoption' here means 'not detected at this power', not 'no effect', and "
    "the result document must say so in those words.")


def power_structure(corpus: pd.DataFrame | None = None,
                    played: pd.DataFrame | None = None,
                    ledger: dict[str, set[str]] | None = None,
                    ) -> dict[str, Any]:
    """§6's frozen structure, recomputed from the pinned artifacts.

    85 fixtures, 52 treated, 62 week blocks, 6 seasons; by season
    26 / 11 / 12 / 12 / 12 / 12 with treated 21 / 4 / 7 / 6 / 7 / 7. The counts
    are §6's; the ASSIGNMENT of fixtures to blocks is the corpus's own, which
    is what the week-block bootstrap actually resamples, and it is checked
    against the counts rather than typed in.
    """
    corpus = load_corpus() if corpus is None else corpus
    played = load_archive() if played is None else played
    ledger = load_walk_ledger() if ledger is None else ledger
    m = membership(corpus, played, ledger, e_star=E_STAR)
    detail = m.detail
    treated = set(m.treated)
    keys = sorted(m.thin)
    blocks = [str(detail[k]["block"]) for k in keys]
    seasons = [str(detail[k]["season"]) for k in keys]
    is_treated = np.array([k in treated for k in keys], dtype=bool)

    by_season = tuple(sum(1 for s in seasons if s == season)
                      for season in sorted(set(seasons)))
    treated_by_season = tuple(
        int(np.sum(is_treated[[i for i, s in enumerate(seasons)
                               if s == season]]))
        for season in sorted(set(seasons)))
    problems = []
    if len(keys) != POWER_N_THIN:
        problems.append(f"{len(keys)} thin, not {POWER_N_THIN}")
    if int(is_treated.sum()) != POWER_N_TREATED:
        problems.append(f"{int(is_treated.sum())} treated, not {POWER_N_TREATED}")
    if len(set(blocks)) != POWER_N_WEEK_BLOCKS:
        problems.append(f"{len(set(blocks))} week blocks, not "
                        f"{POWER_N_WEEK_BLOCKS}")
    if len(set(seasons)) != POWER_N_SEASONS:
        problems.append(f"{len(set(seasons))} seasons, not {POWER_N_SEASONS}")
    if by_season != POWER_THIN_BY_SEASON:
        problems.append(f"thin by season {by_season}, not {POWER_THIN_BY_SEASON}")
    if treated_by_season != POWER_TREATED_BY_SEASON:
        problems.append(f"treated by season {treated_by_season}, not "
                        f"{POWER_TREATED_BY_SEASON}")
    if problems:
        raise MembershipMismatch(
            "; ".join(problems) + ". §6 freezes the power simulation's "
            "structure; a different one answers a different question.")
    return {"keys": keys, "blocks": blocks, "seasons": seasons,
            "treated": is_treated, "n_thin": len(keys),
            "n_treated": int(is_treated.sum()),
            "n_week_blocks": len(set(blocks)), "n_seasons": len(set(seasons)),
            "thin_by_season": by_season,
            "treated_by_season": treated_by_season}


class _BlockResampler:
    """`epl.score.block_bootstrap_ci`'s own resample, precomputed once.

    §6 permits a vectorised inner loop **only** if a committed test asserts
    that its ``(lo, hi, n_blocks)`` equals the protected function's on the
    frozen structure, at three named noise draws, to 1e-15. This is that loop,
    and :func:`bootstrap_shortcut_matches` is that assertion.

    The resample indices depend on the seed, ``n_boot`` and ``n_blocks`` ONLY —
    never on the data — so they are drawn once and reused, which is the whole
    speedup. The estimator is unchanged: blocks resampled with replacement, the
    statistic pooled over matches, percentile quantiles at NumPy's default
    linear interpolation.
    """

    def __init__(self, labels: Sequence[Any], *, n_boot: int = N_BOOT,
                 alpha: float = ALPHA, seed: int = BOOTSTRAP_SEED):
        arr = np.asarray(list(labels), dtype=object)
        _, inverse = np.unique(arr, return_inverse=True)
        order = np.argsort(inverse, kind="mergesort")
        cuts = np.flatnonzero(np.diff(inverse[order])) + 1
        self.groups = np.split(order, cuts)
        self.sizes = np.array([g.size for g in self.groups], dtype=float)
        self.n_blocks = int(self.sizes.size)
        self.alpha = float(alpha)
        rng = np.random.default_rng(int(seed))
        draw = rng.integers(0, self.n_blocks, size=(int(n_boot), self.n_blocks))
        self.denominator = self.sizes[draw].sum(axis=1)
        counts = np.zeros((int(n_boot), self.n_blocks), dtype=float)
        np.add.at(counts, (np.arange(int(n_boot))[:, None], draw), 1.0)
        self.counts = counts

    def block_sums(self, values: np.ndarray) -> np.ndarray:
        """`[..., n_fixtures]` -> `[..., n_blocks]`, in the function's own order."""
        values = np.asarray(values, dtype=float)
        return np.stack([values[..., g].sum(axis=-1) for g in self.groups],
                        axis=-1)

    def quantiles(self, block_sums: np.ndarray) -> np.ndarray:
        """`[..., n_blocks]` -> `[..., 2]` percentile bounds."""
        means = (np.asarray(block_sums, dtype=float) @ self.counts.T) \
            / self.denominator
        return np.quantile(means, [self.alpha / 2.0, 1.0 - self.alpha / 2.0],
                           axis=-1).T


def bootstrap_shortcut_matches(deltas: np.ndarray, labels: Sequence[Any], *,
                               n_boot: int = N_BOOT, alpha: float = ALPHA,
                               seed: int = BOOTSTRAP_SEED,
                               tolerance: float = 1e-15) -> dict[str, Any]:
    """§6's condition on the shortcut: equal to the protected function.

    "Absent that test, the shortcut is removed, not trusted."
    """
    want_lo, want_hi, want_blocks = score_mod.block_bootstrap_ci(
        deltas, list(labels), n_boot=n_boot, alpha=alpha, seed=seed)
    sampler = _BlockResampler(labels, n_boot=n_boot, alpha=alpha, seed=seed)
    got_lo, got_hi = sampler.quantiles(sampler.block_sums(np.asarray(deltas)))
    out = {"lo": [float(want_lo), float(got_lo)],
           "hi": [float(want_hi), float(got_hi)],
           "n_blocks": [int(want_blocks), int(sampler.n_blocks)],
           "max_abs_diff": float(max(abs(got_lo - want_lo),
                                     abs(got_hi - want_hi))),
           "tolerance": float(tolerance)}
    out["PASS"] = bool(out["max_abs_diff"] <= tolerance
                       and want_blocks == sampler.n_blocks)
    return out


def power_simulation(structure: dict[str, Any] | None = None, *,
                     replicates: int = POWER_REPLICATES,
                     seed: int = POWER_SEED, n_boot: int = N_BOOT,
                     bootstrap_seed: int = BOOTSTRAP_SEED,
                     scenarios: Sequence[tuple[str, float, str]] | None = None,
                     verbose: bool = False) -> dict[str, Any]:
    """§6's power analysis, as §6 makes it committed, runnable code.

    §6's six numbers were produced by uncommitted scratch code: the
    correlated-Gaussian construction, the correlation scope, the MDE search
    grid, the interpolation rule, the tie rule and the claimed 1e-15 shortcut
    equivalence existed nowhere a reader could run. A preregistration that
    publishes six deciding-adjacent numbers from code no one can execute is
    doing the thing it exists to stop.

    THE CONSTRUCTION, FROZEN.

    * **Structure** — :func:`power_structure`, checked against §6's counts.
      Untreated deltas are exactly 0.0, never noisy, as the ADD design makes
      them.
    * **Noise** — for a treated fixture *i* in week block *b*, the delta is
      ``δ + s · ( sqrt(ρ)·u_b + sqrt(1−ρ)·z_i )`` with ``u_b`` and ``z_i``
      independent standard normals: an equicorrelated Gaussian whose
      correlation scope is **the week block and nothing else**. Season
      correlation is not modelled and is not claimed; ρ ∈ {0, 0.5} brackets it.
    * **Replicates** — ``R = 2,000``, one ``numpy.random.default_rng(20260827)``
      consumed in scenario order (A ρ=0, A ρ=0.5, B ρ=0, B ρ=0.5, C ρ=0,
      C ρ=0.5), and within a scenario one noise draw per replicate **reused
      across every grid point of δ** — common random numbers, so the power curve
      is monotone in δ up to Monte-Carlo error.
    * **Gates** — all three deciding match gates exactly as §4.1 states them,
      through ``epl.score.block_bootstrap_ci``'s own resample at B = 10,000,
      α = 0.05, seed 20260814, on the 62 week blocks and on the 6 seasons.
    * **The MDE** — grid ``δ ∈ {0, −0.0002, …, −0.0200}``; power at a grid point
      is the fraction of replicates at which ALL THREE gates pass; MDE80 is the
      linear interpolation in δ between the first adjacent pair bracketing 0.80,
      scanning from δ = 0 downward; a grid point at exactly 0.80 IS the MDE; and
      if power never reaches 0.80 the MDE is reported as ``< −0.0200`` with no
      interpolated value rather than extrapolated. Reported on the estimand's
      scale, treated effect × 52/85.
    * **Power at the bar** is evaluated at ``δ = −0.0016346153846153847``
      exactly, which is not on the grid and is not interpolated from it.

    A STRUCTURAL FACT, so no one reads the table as a defect in the simulation:
    gate (i) is a threshold AT the bar, not a test against zero, so at a true
    effect exactly equal to the bar the probability of clearing it is about one
    half whatever the variance is. An 80%-power MDE equal to the bar is
    unattainable by construction, at any SD; the honest quantity is the ratio.

    This function WRITES NOTHING. It prints the table and returns the `power`
    object `reports/evidence/widening.json` carries.
    """
    assert_not_overridable(replicates=(replicates, POWER_REPLICATES),
                           seed=(seed, POWER_SEED), n_boot=(n_boot, N_BOOT),
                           bootstrap_seed=(bootstrap_seed, BOOTSTRAP_SEED))
    structure = power_structure() if structure is None else structure
    treated_mask = np.asarray(structure["treated"], dtype=bool)
    blocks = list(structure["blocks"])
    seasons = list(structure["seasons"])
    n_thin = len(blocks)
    n_treated = int(treated_mask.sum())
    scale = n_treated / float(n_thin)

    week = _BlockResampler(blocks, n_boot=n_boot, alpha=ALPHA,
                           seed=bootstrap_seed)
    season = _BlockResampler(seasons, n_boot=n_boot, alpha=ALPHA,
                             seed=bootstrap_seed)
    # the treated-count vector per block, which is what δ multiplies
    unit = np.zeros(n_thin, dtype=float)
    unit[treated_mask] = 1.0
    t_week = week.block_sums(unit)
    t_season = season.block_sums(unit)

    block_index = {b: i for i, b in enumerate(sorted(set(blocks)))}
    treated_block = np.array([block_index[b] for i, b in enumerate(blocks)
                              if treated_mask[i]], dtype=int)
    grid = np.array([-POWER_GRID_STEP * i for i in range(POWER_GRID_POINTS)],
                    dtype=float)

    rng = np.random.default_rng(int(seed))
    rows: list[dict[str, Any]] = []
    # §6.5 re-runs this simulation "with `s` set to the realised value, at the
    # same R, the same seeds, the same grid and the same interpolation rule".
    # The SD is the one thing that moves; everything §2.3 freezes is closed
    # above by `assert_not_overridable`.
    for name, sd, source in (scenarios or POWER_SCENARIOS):
        for rho in POWER_RHOS:
            u = rng.standard_normal((int(replicates), len(block_index)))
            z = rng.standard_normal((int(replicates), n_treated))
            noise = float(sd) * (np.sqrt(rho) * u[:, treated_block]
                                 + np.sqrt(1.0 - rho) * z)
            full = np.zeros((int(replicates), n_thin), dtype=float)
            full[:, treated_mask] = noise
            s_week = week.block_sums(full)
            s_season = season.block_sums(full)
            noise_total = full.sum(axis=1)

            def passes(delta: np.ndarray) -> np.ndarray:
                delta = np.asarray(delta, dtype=float).reshape(-1)
                mean = (delta * n_treated + noise_total) / float(n_thin)
                ok = mean <= ADOPT_DELTA
                hi_w = week.quantiles(delta[:, None] * t_week + s_week)[:, 1]
                hi_s = season.quantiles(delta[:, None] * t_season
                                        + s_season)[:, 1]
                return ok & (hi_w < 0.0) & (hi_s < 0.0)

            # the pass indicator is monotone in delta — every gate is — so the
            # whole power curve follows from each replicate's own critical grid
            # index, found by a bisection that evaluates the gates 7 times
            # rather than 101.
            deepest = passes(np.full(int(replicates), grid[-1]))
            lo = np.zeros(int(replicates), dtype=int)
            hi = np.full(int(replicates), POWER_GRID_POINTS - 1, dtype=int)
            while np.any(lo < hi):
                mid = (lo + hi) // 2
                ok = passes(grid[mid])
                hi = np.where(ok, mid, hi)
                lo = np.where(ok, lo, np.minimum(mid + 1, hi))
            critical = np.where(deepest, lo, POWER_GRID_POINTS)
            curve = np.array([float(np.mean(critical <= k))
                              for k in range(POWER_GRID_POINTS)], dtype=float)

            at_bar = float(np.mean(passes(np.full(int(replicates), POWER_BAR))))
            at_two = float(np.mean(passes(np.full(int(replicates),
                                                  2.0 * POWER_BAR))))
            mde, note = _mde_from_curve(grid, curve)
            rows.append({
                "scenario": name, "sd": float(sd), "source": source,
                "rho": float(rho),
                "power_at_bar": at_bar,
                "mde_treated": (None if mde is None else float(mde)),
                "mde_estimand": (None if mde is None else float(mde * scale)),
                "ratio_to_bar": (None if mde is None
                                 else float(mde * scale / ADOPT_DELTA)),
                "power_at_2x_bar": at_two,
                "exhausted": bool(mde is None), "note": note,
                "curve": [float(v) for v in curve],
            })
            if verbose:
                print(f"[evwiden-power] {name} rho={rho} power@bar={at_bar:.3f} "
                      f"MDE={rows[-1]['mde_estimand']}", flush=True)

    return {
        "schema": SCHEMA_ID,
        "structure": {k: v for k, v in structure.items()
                      if k not in ("keys", "blocks", "seasons", "treated")},
        "definition": ("MDE80 is the injected treated effect at which ALL THREE "
                       "deciding match gates pass with probability 0.80, "
                       "reported on the estimand's scale (treated effect x "
                       f"{n_treated}/{n_thin})"),
        "replicates": int(replicates), "simulation_seed": int(seed),
        "bootstrap": {"function": "epl.score.block_bootstrap_ci",
                      "B": int(n_boot), "alpha": ALPHA,
                      "seed": int(bootstrap_seed)},
        "grid": {"step": POWER_GRID_STEP, "points": POWER_GRID_POINTS,
                 "from": 0.0, "to": float(grid[-1]),
                 "interpolation": "linear in delta between the FIRST adjacent "
                                  "pair bracketing 0.80, scanning from 0 "
                                  "downward; a grid point at exactly 0.80 IS "
                                  "the MDE; if 0.80 is never reached the MDE is "
                                  "reported as < -0.0200 with no interpolated "
                                  "value"},
        "bar": {"treated": POWER_BAR, "estimand": ADOPT_DELTA,
                "evaluated": "at its own seed and replicates, never "
                             "interpolated from the grid"},
        "structural_fact": ("gate (i) is a threshold AT the bar, not a test "
                            "against zero, so at a true effect exactly equal to "
                            "the bar the probability of clearing it is about "
                            "one half whatever the variance is. An 80%-power "
                            "MDE equal to the bar is unattainable by "
                            "construction, at any SD; the honest quantity is "
                            "the ratio."),
        "scenarios": [{"scenario": n, "paired_sd": s, "source": src}
                      for n, s, src in (scenarios or POWER_SCENARIOS)],
        "rows": rows, "published": [dict(r) for r in PUBLISHED_POWER],
        "warning": POWER_WARNING,
        "decides": "nothing — no threshold in §4 moves in response",
    }


def realised_power(sd: float, *, structure: dict[str, Any] | None = None,
                   verbose: bool = False) -> dict[str, Any]:
    """§6.5: **the joint-gate MDE recomputed at the REALISED paired SD.**

    > After the run, the **realised paired SD of the treated deltas** is
    > reported, and **the joint-gate MDE is recomputed at that realised SD** —
    > the fixed-scenario simulation of §6.2 re-run with `s` set to the realised
    > value, at the same `R`, the same seeds, the same grid and the same
    > interpolation rule, producing a realised `power@bar`, realised `MDE80` and
    > realised ratio in the same columns as §6.3's table.

    **It is a distinct quantity from the two-sided-test-against-zero MDE**,
    which is not what gate (i) is: gate (i) is a threshold AT the bar, so an
    80%-power MDE equal to the bar is unattainable by construction at any SD.
    "A result document that reports the latter beside the realised SD has not
    discharged this obligation" — and v1 reported exactly the latter, beside a
    sentence saying the joint MDE "remains the fixed-scenario simulation's".

    The realised numbers decide nothing and no threshold moves in response
    (§6.5). They exist so the reader can size the null §6.3's warning
    pre-announces.
    """
    return power_simulation(
        structure, verbose=verbose,
        scenarios=(("realised", float(sd),
                    "the realised paired SD of the treated deltas, §6.5"),))


def _mde_from_curve(grid: np.ndarray, curve: np.ndarray
                    ) -> tuple[float | None, str]:
    """§6's interpolation, tie and exhaustion rules, in that order."""
    for k in range(len(grid)):
        if curve[k] == 0.80:
            return float(grid[k]), "tie rule: the grid point IS the MDE"
        if k and curve[k - 1] < 0.80 < curve[k]:
            lo_d, hi_d = float(grid[k - 1]), float(grid[k])
            lo_p, hi_p = float(curve[k - 1]), float(curve[k])
            frac = (0.80 - lo_p) / (hi_p - lo_p)
            return lo_d + frac * (hi_d - lo_d), "linear interpolation in delta"
    return None, ("exhaustion rule: power does not reach 0.80 anywhere on the "
                  "grid, so the MDE is < -0.0200 and the table says so rather "
                  "than extrapolating")


def committed_power_run() -> dict[str, Any]:
    """The committed :func:`power_simulation` at the frozen constants, EXECUTED.

    §6.3's comparison is against "the numbers the committed `power_simulation()`
    produces at the frozen constants above", and L16's whole obligation is that
    those numbers came out of that code on this occasion.

    **There is no memo.** The adjudication of 2026-08-29 (F9, V3-B3) removed the
    module-level ``_POWER_RUN`` cache: it was "an unbound authority over
    `committed_power_run()` — pre-populating it skips the committed power
    simulation and supplies L16's result", and the conformance artifact recorded
    only the wrapper's passed outcome, never whether the simulation ran. A cache
    is a place to put numbers the committed code did not produce, and the one
    thing this row exists to catch is numbers the committed code did not
    produce. The simulation costs about twenty seconds and is paid every time it
    is asked for.

    It takes no arguments. A caller who could choose the structure, the
    replicate count or either seed would be choosing the numbers §6.3 publishes.
    """
    return power_simulation()


def power_reproduces(power: dict[str, Any] | None = None, *,
                     places: int = 3) -> dict[str, Any]:
    """Does the committed implementation reproduce §6's six published rows?

    §6.3: "These are the numbers the committed `power_simulation()` produces at
    the frozen constants above, and they are the document's numbers.
    `power_reproduces()` must compare the committed run against this table
    through the REAL comparison — not a stubbed power object."

    **Every published column is compared, `ratio` included.** The review found
    `PUBLISHED_POWER` carrying a `ratio` the comparison never read, which left
    one sixth of the frozen table unbound. And every check records the length of
    the power curve the row was derived from, so the caller's anti-stub test
    reads a number this function produced rather than one it hoped the supplied
    object carried — L16's own check was vacuously `all([])` on an absent
    ``rows`` key.

    ``power`` survives for ONE caller — :func:`evidence_object`, which compares
    the run's own published power object against §6.3 — and **no deciding path
    supplies it**: :func:`implementation_report`, :func:`assert_implements_document`
    and :func:`freeze_block` took a ``power=`` parameter and the in-tree audit
    rendered the §8.3 block in 11.5 s with a fabricated six-row object, all
    eighteen conformance rows green, L16 among them. The parameter is gone from
    all three; L16 calls this function with nothing and gets
    :func:`committed_power_run`.
    """
    power = committed_power_run() if power is None else power
    rows = list(power.get("rows") or ())
    if len(rows) != len(PUBLISHED_POWER):
        return {"schema": SCHEMA_ID, "checks": [], "PASS": False,
                "why": f"{len(rows)} simulated row(s) against "
                       f"{len(PUBLISHED_POWER)} published: a comparison that "
                       "runs out of rows is not a comparison that passed"}
    checks = []
    for want, got in zip(PUBLISHED_POWER, rows):
        same_row = (want["scenario"] == got["scenario"]
                    and float(want["rho"]) == float(got["rho"]))
        mde = got.get("mde_estimand")
        ratio = got.get("ratio_to_bar")
        checks.append({
            "scenario": want["scenario"], "rho": want["rho"],
            "row_matches": bool(same_row),
            "curve_points": len(got.get("curve") or ()),
            "power_at_bar": {"published": want["power_at_bar"],
                             "reproduced": round(float(got["power_at_bar"]),
                                                 places)},
            "mde_estimand": {"published": want["mde_estimand"],
                             "reproduced": (None if mde is None
                                            else round(float(mde), 6))},
            "ratio": {"published": want["ratio"],
                      "reproduced": (None if ratio is None
                                     else round(float(ratio), 2))},
            "power_at_2x": {"published": want["power_at_2x"],
                            "reproduced": round(float(got["power_at_2x_bar"]),
                                                places)},
        })
        checks[-1]["PASS"] = bool(
            same_row
            and checks[-1]["curve_points"] == POWER_GRID_POINTS
            and checks[-1]["power_at_bar"]["reproduced"] == want["power_at_bar"]
            and checks[-1]["mde_estimand"]["reproduced"] == want["mde_estimand"]
            and checks[-1]["ratio"]["reproduced"] == want["ratio"]
            and checks[-1]["power_at_2x"]["reproduced"] == want["power_at_2x"])
    return {"schema": SCHEMA_ID, "checks": checks,
            "PASS": all(c["PASS"] for c in checks),
            "rule": ("§8.3: `--freeze-block` refuses to render while §6.3's "
                     "table is unreproduced. §6.3 makes the committed "
                     "implementation's numbers the document's numbers, so the "
                     "remedy is to correct §6.3 before the freeze commit or to "
                     "find what in the construction moved — v1's dated-note "
                     "remedy is retired with v1.")}


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
    > zero; (iv) the table gate holds — **per horizon**, as §4.1 repairs it:
    > (iv-a) MW6's seven-cell mean ≤ +0.0002, (iv-b) the treated-cell means at
    > MW0, MW3 and MW10 each ≤ +0.0002, and (iv-c) the MW6 mean is not
    > resolvably positive.
    >
    > Otherwise ``dc_native`` stands unchanged, Hull's forecast included.

    ``table`` is :func:`table_gate`'s verdict. It is REQUIRED for an ADOPT:
    §4.1 makes all four necessary, so a match-level result with no table leg
    behind it cannot adopt, and this function says MISSING rather than
    quietly treating an absent gate as a passed one. An UNRESOLVED gate (iv) is
    a published VERDICT rather than a refusal (§7.1): it blocks adoption and can
    never grant one.
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
    unresolved = bool(table is not None
                      and str(table.get("verdict")) == "UNRESOLVED")
    if iv is None:
        verdict = "INCOMPLETE — the table gate of §4.1 (iv) has not been measured"
    elif unresolved:
        # §5: UNRESOLVED is a published VERDICT, not a refusal. It blocks
        # adoption and can never grant one, and the result document names which
        # of (P1)-(P5) fired.
        verdict = ("UNRESOLVED — gate (iv) falls inside the simulation's own "
                   "error; ADOPT is refused and dc_native stands")
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
                f"corpus's {want_native}. §2.3 demotes the corpus to an "
                "EXTERNAL identity control; a row that copies different numbers "
                "under that name has nothing left to control against.")
        arm_b = [float(v) for v in row["probs_incumbent"]]
        if arm_b != want_native:
            raise ControlMismatch(
                f"{mid}: Arm B — the same posterior's incumbent pass — is "
                f"{arm_b} and the corpus's own row is {want_native}. §3.2 rules "
                "EXACT equality at the corpus's eight decimals over all 820 "
                "fixtures, and §10 makes widening that tolerance after a "
                "mismatch an invalidation.")
        # §2.3's own demand: Arm B's RPS is RECOMPUTED here from Arm B's own
        # stored probabilities, and the two comparisons that follow are kept
        # apart (adjudication F17, seed d). The audit found the recomputation
        # unbound: replacing `recomputed` with the stored `rps_native` left the
        # first term identically zero, and the leg still refused — but only
        # through the corpus comparison beside it, which is a different clause
        # answering a different question. A conjunction that survives its own
        # first half being deleted has not tested that half, and §2.3's
        # "recomputes it at the merge" is precisely that half.
        recomputed = float(score_mod.rps(np.array([native]),
                                         np.array([int(row["y"])]))[0])
        drift_stored = abs(recomputed - float(row["rps_native"]))
        drift_corpus = abs(recomputed - float(stored["dc_rps"]))
        worst_rps = max(worst_rps, drift_stored, drift_corpus)
        if drift_stored > 1e-12:
            raise ScoreMismatch(
                f"{mid}: Arm B's stored RPS does not re-derive from Arm B's own "
                f"stored probabilities (|ΔRPS| = {drift_stored:.3g}). §2.3 "
                "recomputes it at the merge and refuses past 1e-12. This is a "
                "check on the LEDGER ROW alone: what the corpus recorded for "
                "the same fixture is the separate identity control below, and "
                "a ledger that copied a wrong number from a wrong corpus would "
                "satisfy that one.")
        if drift_corpus > 1e-12:
            raise ScoreMismatch(
                f"{mid}: the RPS recomputed from Arm B's stored probabilities "
                f"is not the corpus's own `dc_rps` (|ΔRPS| = "
                f"{drift_corpus:.3g}). §2.3 demotes the corpus to an EXTERNAL "
                "identity control and refuses past 1e-12.")
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

    §7.1: a shard that exits non-zero or writes nothing is :class:`ShardFailed`,
    and a merged key set that is not EXACTLY the pre-stated one — not a superset,
    not a subset — is :class:`MergeIncomplete`. Partial results never silently
    merge and a partial ledger is never scored.

    This function authors no verdict prose. It writes machine-readable numbers;
    ``reports/epl_widening_result.md`` is written afterwards, by a person, and
    §4.4 requires it to be written whichever way the numbers fall.
    """
    assert_not_overridable(n_boot=(n_boot, N_BOOT), seed=(seed, BOOTSTRAP_SEED),
                           shards=(int(shards), SHARDS) if expected is None
                           else None)
    # §8.6's public-surface closure. `harness_frozen` and `require_canaries`
    # are lifecycle ATTESTATIONS — "the same 'trusts the Boolean it must
    # establish' shape §8.6 objects to", as the in-tree audit put it — and
    # `expected` truncates the deciding population. All three are seams, all
    # three are refused at a pinned or preregistered target, and none of them is
    # reachable from the CLI.
    seams = [name for name, supplied in
             (("harness_frozen", harness_frozen is not None),
              ("require_canaries", not require_canaries),
              ("expected", expected is not None),
              ("expected_thin", expected_thin is not None),
              ("expected_treated", expected_treated is not None),
              ("expected_fixtures", expected_fixtures is not None),
              ("freeze_sources", freeze_sources is not None))
             if supplied]
    if seams:
        assert_seam_allowed(f"merge({'=..., '.join(seams)}=...)", corpus=corpus,
                            played=played, target=directory,
                            detail="a lifecycle attestation or a truncated "
                                   "population is not the run this document "
                                   "preregisters")
    freeze = (harness_freeze_status(freeze_sources) if harness_frozen is None
              else {"frozen": bool(harness_frozen), "why": "asserted by caller",
                    "files": {}, "where": None})
    if not freeze["frozen"]:
        if harness_frozen is None:
            require_harness_freeze(freeze_sources)
        raise EvWidenError(
            "refusing to merge: the §8.3 harness-hash freeze commit does not cover "
            "this harness, so these fits are not the run the preregistration "
            "describes (§10).")

    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    preregistered = expected is None
    if preregistered:
        # v3 §8.6, NB6: step 4's own marker check, on every invocation and not
        # only through `main`. The review found `merge` "callable without the
        # CLI sequence", so a direct call scored a ledger that §8.4 had not
        # unlocked. An audit merge over a caller-stated `expected` census is
        # §8.2's own synthetic run and is not step 4.
        require_sequence(SEQUENCE_STEPS[3])
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
            "merge's clock: a fit run during the §7.3 audit is not a fit of the "
            "preregistered run, and re-stamping it would be exactly the "
            "back-dating §8.3 exists to prevent.")

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
        # §9.1: measured off THESE rows, not asserted. Both counts are zero in
        # a run that completed, because the refusals stopped anything else long
        # before the merge — but they are now the answer to a question rather
        # than the question's assumed answer.
        "controls": measured_controls(rows),
        "identity_control": {
            "n_fixtures": len(rows),
            "max_abs_diff": max((float(r["fit"]["control_max_abs_diff"])
                                 for r in rows), default=0.0),
            "mean_abs_diff": (float(np.mean([float(r["max_abs_dp_vs_corpus"])
                                             for r in rows])) if rows else 0.0),
            "tolerance": "exact equality at the corpus's 8 decimals",
            "role": "external — §2.3 demotes the corpus out of the contrast",
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
                     "provisional_enlarged", "provisional_control",
                     "provisional_treatment", "evidence", "n_sims", "seed",
                     "arms", "identical", "realised_hash", "realised_positions",
                     "realised_spans", "realised_points",
                     "consequence_weights", "parity",
                     "parity_digest_simretro", "config_sha256",
                     "harness_sha256", "harness_frozen",
                     # §7.2 and §8.7: "the SHA-256 of its own tally file",
                     # written at the same moment as the row.
                     "tally_sha256")


def table_cutoffs(matches: pd.DataFrame, seasons: Sequence[str] | None = None,
                  labels: Sequence[str] | None = None,
                  ) -> list[tuple[str, str, pd.Timestamp]]:
    """v3 §3.3's 32 cells, from `simretro`'s own `SEASONS`,
    `COMPARISON_CUTOFFS` and `cutoff_schedule` — never from a remembered list of
    dates — **minus §0.6's three unpriceable cells**.

    > The cells are `SEASONS x COMPARISON_CUTOFFS` **minus the three §0.6's
    > census measured as unpriceable**, and those three are named by key here so
    > that the population is decidable from this document rather than from a
    > file. [...] The exclusion is by measurement (§0.6) and is not a parameter:
    > no caller may name, restore or extend it.

    The exclusion happens HERE, at the one place the schedule is derived, rather
    than at each consumer, so a caller cannot reach an excluded cell by calling
    a different entry point. :data:`EXCLUDED_CELLS` is a module constant and not
    an argument for the same reason §2.3's constants are not arguments.
    """
    from epl import simretro

    seasons = tuple(simretro.SEASONS) if seasons is None else tuple(seasons)
    labels = (tuple(simretro.COMPARISON_CUTOFFS) if labels is None
              else tuple(labels))
    out = []
    for season in seasons:
        schedule = simretro.cutoff_schedule(matches, season)
        for label in labels:
            if f"{season}|{label}" in EXCLUDED_CELLS:
                continue
            out.append((season, label, pd.Timestamp(schedule[label]).normalize()))
    return out


#: The one table `epl.fit.build_store` materialises under `paths.STORE_DIR`.
#: Named here so the read-only accessor can answer "is there a store?" without
#: importing anything that could build one.
STORE_TABLE_PARQUET = "results.parquet"


def read_only_store(root: Path | str | None = None):
    """§8.2's read-only store accessor — the mechanism, not the promise.

    > A single **read-only store accessor** is the only route by which any
    > pre-freeze path may obtain a point-in-time store. It opens the existing
    > store parquet and returns it. **If the store parquet is absent it raises
    > `StoreNotBuilt` and stops. It never builds, never writes, never unlinks,
    > and takes no "build if missing" argument.**

    "Read-only" is a property of code, not of intent, and v1's harness violated
    its own clause without anyone noticing: ``--membership``, ``--plan`` and
    ``--freeze-block`` all reached :func:`table_cells`, which called
    ``epl.fit.build_store(played)`` at the **default** root, and ``build_store``
    can unlink and rewrite the shared ``results.parquet``
    (``epl/fit.py:177-203``). A pre-freeze command that can delete and rebuild
    the project's point-in-time store is not read-only in any sense the word
    carries.

    This function constructs a :class:`wcmodel.data.store.BitemporalStore` over
    an **existing** root. `BitemporalStore.__init__` opens; `write` is what
    creates, and nothing here calls it. There is deliberately no `build=`
    parameter: an escape hatch that a caller can flip is the same defect wearing
    a keyword.

    **And it may not create the store's directory as a side effect of checking
    it** (v3 §8.2, MIN-READ-ONLY-STORE-TOCTOU). The check-then-construct shape
    was a time-of-check/time-of-use hole and not a theoretical one:
    ``BitemporalStore.__init__`` **creates its root directory**
    (``src/wcmodel/data/store.py:20-23``), so an accessor that verified
    ``results.parquet`` existed and then constructed the store would create the
    very directory tree it had just found missing whenever the two disagreed —
    a pre-freeze command writing into ``paths.STORE_DIR`` while the document
    claims nothing has been touched. Four facts are recorded before anything is
    constructed and re-verified afterwards, **and the refusal path removes a
    directory the constructor created** (adjudication F11): re-checking makes
    the write visible, it does not undo it, and §8.2's clause is that an absent
    store stays absent.
    """
    from wcmodel.data import store as _store_mod

    if root is not None:
        # An alternate root is how §8.2's passes prove the accessor never
        # builds; it is not a way to point a pre-freeze read at the shared
        # store's neighbours inside the preregistered tree.
        assert_seam_allowed("read_only_store(root=)", target=root,
                            detail="a point-in-time store root other than "
                                   "paths.STORE_DIR")
    root = Path(root) if root is not None else paths.STORE_DIR
    table = root / STORE_TABLE_PARQUET
    if not table.exists():
        raise StoreNotBuilt(
            f"{paths.rel(table)} is not on disk, and §8.2's read-only accessor "
            "is the only route a pre-freeze path has to a point-in-time store. "
            "It opens the existing store parquet and returns it; it never "
            "builds, never writes, never unlinks, and takes no 'build if "
            "missing' argument. Build the store by the ordinary route "
            "(`epl.fit.build_store`) from a command that is authorised to write "
            "one, then re-run this read-only pass.")

    def _seen() -> tuple:
        """The four facts §8.2 requires: both existences, the size, the mtime."""
        stat = table.stat() if table.exists() else None
        return (root.is_dir(), table.exists(),
                stat.st_size if stat else None,
                stat.st_mtime_ns if stat else None)

    before = _seen()
    store = _store_mod.BitemporalStore(root)
    after = _seen()
    if before != after:
        # ...and the refusal UNDOES the construction's write (adjudication F11).
        # Re-checking makes the write visible; it does not undo it, and §8.2's
        # clause is that an absent store stays absent. A refusal that leaves
        # `paths.STORE_DIR` standing where the accessor found nothing has built
        # one and then complained about it. Only a tree this call caused to
        # appear is removed, and only while it is empty: `rmdir` refuses a
        # directory with contents, so nothing anybody else wrote can be lost
        # here.
        removed = "the store parquet is still there, so nothing was removed"
        try:
            if not after[1] and root.is_dir():
                root.rmdir()
                removed = (f"the empty tree at {paths.rel(root)} was REMOVED on "
                           "the way out")
        except OSError as exc:                             # pragma: no cover
            removed = (f"{paths.rel(root)} could not be removed ({exc}); it is "
                       "not empty, so this call is not what created it")
        raise StoreNotBuilt(
            f"{paths.rel(root)} was CREATED OR MOVED between §8.2's existence "
            f"check and the store's construction ({before} -> {after}) — "
            f"{removed}. `BitemporalStore.__init__` creates its root directory, "
            "so an accessor that checked and then constructed would build the "
            "very tree it had just found missing — a pre-freeze command writing "
            "under paths.STORE_DIR while §8.8 attests that nothing has been "
            "touched. The accessor never builds, so this is a refusal, and the "
            "refusal leaves the disk as it found it.")
    return store


def table_cells(matches: pd.DataFrame, played: pd.DataFrame | None = None, *,
                store=None, cfg: dict | None = None,
                seasons: Sequence[str] | None = None,
                labels: Sequence[str] | None = None,
                e_star: float = E_STAR, check: bool = True) -> list[dict[str, Any]]:
    """Which cells the re-key changes, enumerated WITHOUT fitting anything.

    §3.3 pre-states 15 treated and 17 untouched, and the 17 are "unchanged by
    construction, and the harness must prove it". This function is the
    enumeration half of that: the incumbent predicate is read through
    ``count_volatility_arm`` at each scheduled cutoff — the same function
    ``epl/dcfit.py:273-274`` calls — and the evidence rule through §0.3's recipe,
    so the membership can be frozen by the §8.3 commit before a single simulated
    season exists.

    **The store comes from §8.2's read-only accessor and from nowhere else.**
    This function is on the call path of every pre-freeze command, and v1's
    version called ``epl.fit.build_store`` at the default root — which can
    unlink and rewrite the shared ``results.parquet``. It now raises
    :class:`StoreNotBuilt` rather than building one, at any depth, from any
    caller. A post-freeze caller that legitimately has a store passes it in.
    """
    from epl import freeze
    from wcmodel.model.volatility_diagnostic import count_volatility_arm

    cfg = freeze.frozen_wcmodel_config() if cfg is None else cfg
    if played is None:
        played = matches.loc[matches["played"]].copy()
        played["date"] = pd.to_datetime(played["date"]).dt.normalize()
    store = read_only_store() if store is None else store

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
        assert_table_census(out)
    return out


def assert_table_census(cells: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """§3.3's census — the totals **and the per-label pin**.

    > **This per-label census is a binding pin, not a table in prose.**
    > `EXPECTED_TREATED_BY_LABEL = {MW0: 3, MW3: 2, MW6: 7, MW10: 4, MW19: 0}`
    > must be verified by `table_cells(check=True)`, which today verifies only
    > the 35/16 totals. The reason is not tidiness: **"MW6 is the only label at
    > which every cell is treated" is the entire stated ground for naming MW6
    > the deciding horizon** (§4.1). If that stops being true, the ground for
    > the deciding horizon has moved and the harness must refuse rather than
    > carry on. A departure from the pin is `MembershipMismatch`.

    The audit found ``EXPECTED_TREATED_BY_LABEL`` "referenced nowhere in the
    module or the tests" — a dead pin, correct today and unable to say so
    tomorrow. A perturbation that moves one treated cell from MW0 to MW3 keeps
    both totals and is invisible to a totals-only check.
    """
    treated = [c for c in cells if c["treated_clubs"]]
    # §10: "a cell §0.6's census measured as unpriceable is added back to the
    # oracle" is an invalidation, and it is checked FIRST: a thirty-third cell
    # would otherwise be reported as an arithmetic slip, and a SUBSTITUTED one
    # keeps the total intact and would pass every other check here. Naming the
    # cell is the whole content of the refusal.
    back = sorted({f"{c['season']}|{c['cutoff_label']}" for c in cells}
                  & set(EXCLUDED_CELLS))
    if back:
        raise MembershipMismatch(
            f"the census carries {back}, which §0.6 measured as UNPRICEABLE on "
            "the shipped stack: " + "; ".join(
                f"{k} — {EXCLUDED_CELL_DETAIL[k]['fixture']}, particle-mean "
                f"excluded mass {EXCLUDED_CELL_DETAIL[k]['excluded_mass']} "
                f"against A1's {EXCLUDED_CELL_DETAIL[k]['ceiling']} ceiling"
                for k in back)
            + ". §10 makes adding one back an invalidation, and §3.3 makes the "
            "exclusion a measurement rather than a parameter: no caller may "
            "name, restore or extend it.")

    if len(cells) != EXPECTED_TABLE_CELLS or \
            len(treated) != EXPECTED_TABLE_TREATED:
        raise MembershipMismatch(
            f"{len(cells)} table cells of which {len(treated)} change; §3.3 "
            f"pre-states {EXPECTED_TABLE_CELLS} and {EXPECTED_TABLE_TREATED}")

    cells_by_label: dict[str, int] = {lab: 0 for lab in EXPECTED_CELLS_BY_LABEL}
    by_label: dict[str, int] = {label: 0 for label in EXPECTED_TREATED_BY_LABEL}
    for cell in cells:
        label = str(cell["cutoff_label"])
        cells_by_label[label] = cells_by_label.get(label, 0) + 1
        if cell["treated_clubs"]:
            by_label[label] = by_label.get(label, 0) + 1
    if by_label != dict(EXPECTED_TREATED_BY_LABEL):
        raise MembershipMismatch(
            f"the per-label treated census is {by_label} and §3.3 pins it at "
            f"{dict(EXPECTED_TREATED_BY_LABEL)}. This pin is binding and not a "
            "table in prose: 'MW6 is the only label at which every cell is "
            "treated' is the entire stated ground for naming MW6 the deciding "
            "horizon (§4.1), so if that stops being true the ground for the "
            "deciding horizon has moved and this harness refuses rather than "
            "carrying on. The 32/15 totals can be intact while this is wrong — "
            "moving one treated cell from one label to another keeps both.")
    if cells_by_label != dict(EXPECTED_CELLS_BY_LABEL):
        raise MembershipMismatch(
            f"the per-label cell census is {cells_by_label} and §3.3 pins it "
            f"at {dict(EXPECTED_CELLS_BY_LABEL)}. **Both** per-label censuses "
            "are binding pins under v3, and this one is the pin v2 never "
            "needed: v2's labels held seven cells each, and after §0.6's "
            "measurement MW0 holds five and MW3 six. §4.1's ground is 'MW6 is "
            "the only label at which EVERY cell is treated', which after the "
            "census is a statement about two censuses rather than one — a "
            "label could become all-treated by losing its UNTOUCHED cells, "
            "which is not the same fact and would not carry the same ground. "
            "The 32/15 totals and the treated census can all be intact while "
            "this is wrong.")
    all_treated = sorted(lab for lab, n in by_label.items()
                         if n and n == cells_by_label[lab])
    if all_treated != [MW6_LABEL]:
        raise MembershipMismatch(                          # pragma: no cover
            f"the all-treated labels are {all_treated} and §4.1's ground for "
            f"the deciding horizon requires exactly [{MW6_LABEL!r}].")

    # ---- THE EXACT THIRTY-TWO (adjudication F6, V3-B1) --------------------
    # Everything above is an AGGREGATE, and V3-B1's finding is that every one of
    # them survives a substitution: "a bogus same-label season or altered
    # cutoff/treated club" keeps the totals, both per-label censuses and MW6's
    # ground intact. This is the check that does not: the frozen
    # (season, label, cutoff-date, treated-club) tuples, exactly, as §8.2's
    # read-only pass measured them.
    want = sorted(FROZEN_TABLE_SCHEDULE)
    got = sorted(schedule_tuple(c) for c in cells)
    if got != want:
        short = [t for t in want if t not in got]
        stray = [t for t in got if t not in want]
        raise MembershipMismatch(
            f"the schedule is not §3.3's exact thirty-two: {len(stray)} cell(s) "
            f"this census carries are not in it (first: {stray[:3]}) and "
            f"{len(short)} of its own are missing (first: {short[:3]}). Every "
            "count above — 32/15/17, both per-label censuses, MW6's "
            "all-treated ground — survives a substituted season, a cutoff moved "
            "by a week or a treated club exchanged for a neighbour, and this is "
            "the check that does not. §3.3's population is the exact thirty-two "
            "the read-only pass measured, not any thirty-two with the same "
            "aggregate census, and §10 makes changing one an invalidation.")

    return {"n_cells": len(cells), "n_treated": len(treated),
            "by_label": by_label, "cells_by_label": cells_by_label,
            "excluded": list(EXCLUDED_CELLS), "all_treated": all_treated,
            "schedule_digest": table_schedule_digest(cells),
            "PASS": True,
            "ground": ("MW6 is the only label at which every cell is treated, "
                       "which is why §4.1 names it the deciding horizon")}


def table_key(cell: dict[str, Any], config_sha: str, n_sims: int,
              seed: int) -> str:
    """The table leg's resume key: one cell, one configuration, one budget."""
    return (f"{cell['season']}|{cell['cutoff_label']}|{cell['cutoff']}|"
            f"{int(n_sims)}|{int(seed)}|{config_sha}")


def cell_key(row: dict[str, Any]) -> str:
    """`season|cutoff_label` — the identity a cell keeps across legs."""
    return f"{row['season']}|{row['cutoff_label']}"


def frozen_table_constants() -> dict[str, int]:
    """§0.1's table-leg budget, resolved from the protected modules that own it.

    §2.3's closure "applies to `n_sims` (20,000)" as much as to `B`, and §8.6's
    public-surface closure makes production paths RESOLVE every constant from
    the frozen law rather than accept one. There is therefore no ``n_sims``,
    ``seed`` or ``chunk_size`` parameter anywhere on the table surfaces: this
    function is where those three come from, and it reads them off
    ``epl.simretro`` and ``epl.leaguesim`` — the modules §0.1 pins them in.
    """
    from epl import leaguesim, simretro

    return {"n_sims": int(simretro.DEFAULT_N_SIMS), "seed": int(simretro.SEED),
            "chunk_size": int(leaguesim.DEFAULT_CHUNK_SIZE)}


def simulate_arm(state, book, *, played: pd.DataFrame,
                 directory: Path | str | None = None,
                 n_particles: int | None = None):
    """THE one call into protected :func:`epl.leaguesim.simulate`, in one place.

    §3.3 recorded the defect rather than fixing it quietly: at the time of that
    repair the harness called ``simulate`` with the particle book in ``state``'s
    argument position and no ``seed`` argument at all, while protected
    ``epl/simretro.py:555`` calls it ``simulate(arm, state, provider, n_sims,
    seed, …)``. No test exercised the real call and no fit had run, so the
    parity oracle would have caught it on its first cell and nothing
    else in the harness would have.

    Funnelling the call through one function is what lets a test bind the
    argument tuple against ``inspect.signature(leaguesim.simulate)`` without a
    fit — the check that the positional order is the protected one.

    Both arms are labelled ``dc_native`` to ``leaguesim``, and that is the
    document's rule rather than a harness convenience: the provider IS
    ``DCNativeProvider`` in both arms — a ``ParticleBook`` may not wear another
    arm's name — and what differs between them is the BOOK, which is the
    treatment.

    **It is gated and it takes no constants.** The review's NEW-B2 found this
    function calling protected ``leaguesim.simulate`` directly, with `n_sims`,
    `seed` and `chunk_size` supplied by its caller: a public surface that could
    simulate the real archive without passing :func:`assert_may_fit`, at a
    budget nobody froze. The three constants now come from
    :func:`frozen_table_constants` and the played frame is required so the guard
    can key on the artifact identity, exactly as it does for :class:`Engine`.
    """
    from epl import leaguesim

    assert_may_fit("epl.evwiden.simulate_arm", played=played,
                   directory=directory)
    frozen = frozen_table_constants()
    # §8.6's first-fit record is NOT written here (adjudication F7). This
    # function draws seasons from a posterior somebody else fitted: it performs
    # no fit, and a clock named "the UTC instant of the first real fit" that a
    # non-fitting surface can start is recording something other than what it
    # names. On the table leg it would always be started by the wrong one of the
    # two — `TableRunner` fits and then simulates, so the instant recorded would
    # be the simulation's rather than the fit's. The record is written at the
    # true fit sites: `Engine.fit`, `TableRunner.__call__`,
    # `ParityRunner.__call__` and §8.4 step 1's results canary.
    return leaguesim.simulate(TABLE_ARM_LABEL, state, book,
                              frozen["n_sims"], frozen["seed"],
                              frozen["chunk_size"], n_particles=n_particles)


# --------------------------------------------------------------------------
# §5.1 — the per-particle FRACTIONAL rank-mass tally
# --------------------------------------------------------------------------

def particle_tallies(run, *, chunk_size: int = 2048) -> np.ndarray:
    """``[P, C, C]`` — each particle's share of the mass TRPS actually scores.

    §5.1 fixes the object this bootstrap resamples, and it is not ``.order``. ``epl/table.py`` says of it in its own
    docstring that *"inside a shared block its sequence carries no meaning and
    is only the deterministic club-index order"* (`epl/table.py:374-377`). The
    matrix TRPS scores is built from FRACTIONAL RANK MASS:
    ``epl.table.position_mass`` spreads ``1/span`` across the ``span``
    positions a tie block occupies (`epl/table.py:550-593`). A bootstrap over
    ``.order`` would resample a different object from the one the point
    estimate scores.

    The tally is therefore built through the protected code that DEFINES it: a
    :class:`epl.table.Ranking` over the run's own retained rows and plan, then
    ``position_mass``. ``order`` is passed because the dataclass requires the
    field; **it is never read** — ``position_mass`` reads ``block_start`` and
    ``block_span`` and nothing else.

    Accumulation is chunked the way ``position_mass_sums`` chunks, in ascending
    season order. ``numpy.add.at`` is unbuffered and applies its indices in
    order, so a chunked accumulation over contiguous ascending ranges performs
    exactly the same sequence of additions as an unchunked one and the sums are
    bit-identical — a committed test asserts that equality at 0.0.
    """
    from epl import table as table_mod

    rows, plan = run.retained_rows, run.plan
    n_particles = int(run.n_particles)
    n_clubs = len(plan.clubs)
    n = int(np.asarray(rows.block_start).shape[0])
    out = np.zeros((n_particles, n_clubs * n_clubs), dtype=float)
    particle = np.asarray(rows.particle)
    for lo in range(0, n, max(1, int(chunk_size))):
        hi = min(lo + max(1, int(chunk_size)), n)
        ranking = table_mod.Ranking(
            block_start=rows.block_start[lo:hi], block_span=rows.block_span[lo:hi],
            resolution_code=rows.resolution_code[lo:hi], order=rows.order[lo:hi],
            boundaries=plan.boundaries, rule_id=plan.rule_id)
        mass = table_mod.position_mass(ranking).reshape(hi - lo, -1)
        np.add.at(out, particle[lo:hi], mass)
    return out.reshape(n_particles, n_clubs, n_clubs)


def assert_tally_binds_the_matrix(tallies: np.ndarray, run,
                                  *, tolerance: float = 1e-9) -> dict[str, Any]:
    """§5's two committed checks, which bind the tally to the point estimate.

    * ``max |T.sum(axis=0)/n_sims − run.matrix| ≤ 1e-9`` — the tally reproduces
      the scored matrix. The tolerance rather than bit equality is deliberate:
      the protected accumulator sums in CHUNK order and this one sums in
      PARTICLE order. (``run.matrix`` is ``mass.matrix / n_sims``, so the
      comparison is made on the normalised scale the run publishes.)
    * every particle's tally has **every row and every column** equal to
      ``k = n_sims / P`` to within 1e-9 — a league season is a bijection
      between clubs and ranks, and this is the same equal-cluster condition the
      protected ``epl.simmetrics.trps_se_cluster`` enforces on its own input.
    """
    tallies = np.asarray(tallies, dtype=float)
    n_sims, n_particles = int(run.n_sims), int(run.n_particles)
    matrix = np.asarray(run.matrix, dtype=float)
    d_matrix = float(np.abs(tallies.sum(axis=0) / n_sims - matrix).max())
    if d_matrix > float(tolerance):
        raise TableMCImprecise(
            f"the per-particle tally does not reproduce the scored matrix: "
            f"max |T.sum(0)/n_sims − matrix| = {d_matrix:.3g} > {tolerance:g}. "
            "§5 binds the bootstrapped object to the object the point "
            "estimate scores; a tally that describes something else would give "
            "a standard error for a statistic nobody reported.")
    k = n_sims / float(n_particles)
    rows_ok = float(np.abs(tallies.sum(axis=2) - k).max())
    cols_ok = float(np.abs(tallies.sum(axis=1) - k).max())
    if max(rows_ok, cols_ok) > float(tolerance):
        raise TableMCImprecise(
            f"a particle's tally is not an equal cluster of {k:g} seasons: the "
            f"worst club-row deviation is {rows_ok:.3g} and the worst rank-column "
            f"deviation {cols_ok:.3g}. A league season is a bijection between "
            "clubs and ranks, and §5.2 makes an unequal cluster a "
            "refusal rather than something to reweight.")
    return {"max_abs_matrix_diff": d_matrix, "sims_per_particle": k,
            "max_abs_row_dev": rows_ok, "max_abs_col_dev": cols_ok,
            "n_particles": n_particles, "n_sims": n_sims}


# --------------------------------------------------------------------------
# §3.3 — the two digests, with disjoint jobs
# --------------------------------------------------------------------------

def sampler_digest(run, tallies: np.ndarray) -> str:
    """SAMPLER OUTPUT ONLY — comparable within one cell, between its two arms.

    §3.3's digest split ends v1's tautology. The superseded digest INCLUDED
    the provisional set and the treated-cell identity then required every
    treated cell's two digests to DIFFER as
    proof that the treatment reached the sampler; together those prove nothing,
    because the digests differ the moment the metadata names a different set,
    whether or not one scoreline changed. A test that cannot fail is not a test.

    Four items, in this order, and **nothing else** — no club list, no plan, no
    seed, no posterior hash, **no provisional set**, no arm label, no clocks, no
    host, no shard id, no free text:

    1. the scored position matrix at full stored precision;
    2. the per-particle fractional rank-mass tallies of §5.1;
    3. the retained points, goal-difference and goals-for vectors;
    4. the tie-block record — ``block_start``, ``block_span``,
       ``resolution_code``.
    """
    from epl import leaguesim

    rows = run.retained_rows
    payload = [
        np.asarray(run.matrix, dtype=float),
        np.asarray(tallies, dtype=float),
        [np.asarray(rows.points), np.asarray(rows.gd), np.asarray(rows.gf)],
        [np.asarray(rows.block_start), np.asarray(rows.block_span),
         np.asarray(rows.resolution_code)],
    ]
    return hashlib.sha256(
        leaguesim.canonical_json(payload).encode("utf-8")).hexdigest()


def plan_state(run) -> dict[str, Any]:
    """§3.3's item 9: the complete field set of :class:`epl.leaguesim.SimPlan`.

    Season, cutoff and ``observed_by`` identity; the fixture-and-result snapshot
    the run was built on; the points adjustments; the ranking rule id; the
    chunking, which fixes the RNG chunk keys and therefore the numbers; and the
    results-lag state. A run that differs from another in any of them is a
    different run, and the substantive digest now says so.
    """
    plan = run.plan
    return {
        "season": str(plan.season), "season_code": str(plan.season_code),
        "cutoff": str(plan.cutoff), "observed_by": str(plan.observed_by),
        "clubs": list(plan.clubs),
        "fixtures": [[str(f.fixture_id), int(f.ordinal), str(f.home_key),
                      str(f.away_key),
                      None if f.result is None else [int(f.result[0]),
                                                     int(f.result[1])]]
                     for f in plan.fixtures],
        "adjustments": [int(v) for v in np.asarray(plan.adjustments).tolist()],
        "boundaries": [[int(a), int(b)] for a, b in plan.boundaries],
        "rule_id": str(plan.rule_id), "n_sims": int(plan.n_sims),
        "n_particles": int(plan.n_particles), "seed": int(plan.seed),
        "chunk_size": int(plan.chunk_size),
        "n_unresolved": int(plan.n_unresolved),
        "results_lag": bool(plan.results_lag),
    }


def substantive_digest(run, tallies: np.ndarray, *, weights: Sequence[float],
                       boundaries: Sequence[Sequence[int]],
                       realised_hash: str,
                       realised_positions: Sequence[int],
                       realised_points: Sequence[int]) -> str:
    """EVERYTHING A RERUN MUST REPRODUCE — the parity oracle's comparator.

    §3.3: ``sampler_digest``'s four items **plus** the club list, the
    consequence weights and the boundary definition, the realised-truth
    identity, ``n_sims`` / ``n_particles`` / ``seed``, and the full
    :class:`epl.leaguesim.SimPlan` state.

    **Excluded by name:** the arm label, the provisional set,
    ``effective_posterior_hash``, wall clocks, host, shard id, and any free-text
    note.

    **Why ``effective_posterior_hash`` is excluded, and it is arithmetic rather
    than taste.** It is supplied as ``ParticleBook.content_hash()``, and
    ``content_hash`` hashes ``sorted(self.provisional)``
    (``epl/particles.py:331-358``). Embedding it would re-admit the provisional
    set into a digest the document says excludes it — directly contradicting the
    definition, whatever the downstream consequence. v1 passed it in as item 8,
    so its digest hashed the provisional set at one remove while its own
    docstring said it did not.

    The posterior identity is not discarded: it becomes a separately-recorded
    and separately-compared provenance field on every table row
    (``effective_posterior_control``, ``effective_posterior_treatment``),
    checked by :func:`assert_native_parity` the way the provisional sets are.
    **Metadata is checked as metadata; the sampler is checked by its output.**
    """
    from epl import leaguesim

    rows = run.retained_rows
    payload = [
        np.asarray(run.matrix, dtype=float),
        np.asarray(tallies, dtype=float),
        [np.asarray(rows.points), np.asarray(rows.gd), np.asarray(rows.gf)],
        [np.asarray(rows.block_start), np.asarray(rows.block_span),
         np.asarray(rows.resolution_code)],
        list(run.plan.clubs),
        [[float(w) for w in weights],
         [[int(a), int(b)] for a, b in boundaries]],
        [str(realised_hash), [int(p) for p in realised_positions],
         [int(p) for p in realised_points]],
        [int(run.n_sims), int(run.n_particles), int(run.plan.seed)],
        plan_state(run),
    ]
    return hashlib.sha256(
        leaguesim.canonical_json(payload).encode("utf-8")).hexdigest()


def arm_record(run, tallies: np.ndarray, book, *, clubs: Sequence[str],
               positions: np.ndarray, spans: np.ndarray, truth: np.ndarray,
               weights: Sequence[float], realised_hash: str,
               treated_clubs: Sequence[str]) -> dict[str, Any]:
    """One arm of one cell, as :class:`TableRunner` records it.

    Factored out of ``TableRunner.__call__`` so that §3.3's second committed
    test can be made **at TableRunner level without a real fit**, which is the
    level the in-tree audit of v1 named. That audit's seed (o) was
    ``sampler_digest(run, tallies, *, provisional=())`` with the runner passing
    ``book.provisional``: at a treated cell ``control.provisional !=
    treatment.provisional``, so the two arms' digests differed because the
    METADATA differed, and ``assert_table_identity``'s treated-cell condition
    became a test that could not fail. The whole suite stayed green.

    The two committed tests §3.3 requires are therefore: the signature pin on
    :func:`sampler_digest`, and a call through THIS function with two books
    differing only in ``provisional`` over one run and one tally, which must
    produce **equal** sampler digests. A test that only checks which *existing*
    fields move the digest cannot see a new input channel; these two can.

    The book reaches the record only as metadata — ``provisional``,
    ``effective_posterior_hash``, ``alpha`` — and never as an input to either
    digest.
    """
    from epl import simmetrics, table as table_mod

    matrix = simmetrics.scored_matrix(run.matrix, len(clubs))
    points = np.asarray(run.retained_rows.points)
    return {
        "trps": float(simmetrics.trps(matrix, positions, spans=spans)),
        "wtrps": float(simmetrics.wtrps(matrix, positions, weights,
                                        spans=spans)),
        "flat_trps": float(simmetrics.flat_trps(positions, spans=spans)),
        # (run, tallies) and nothing else — §3.3's pinned signature
        "sampler_digest": sampler_digest(run, tallies),
        "substantive_digest": substantive_digest(
            run, tallies, weights=weights, boundaries=run.plan.boundaries,
            realised_hash=realised_hash, realised_positions=positions,
            realised_points=truth),
        # metadata, checked AS metadata (§3.3)
        "effective_posterior_hash": book.content_hash(),
        "provisional": sorted(book.provisional),
        "coverage": simmetrics.interval_coverage(points, truth),
        "coverage_treated": _coverage_for(points, truth, clubs, treated_clubs),
        "clubs_detail": _club_detail(matrix, points, clubs, treated_clubs,
                                     truth),
        "n_sims": int(run.n_sims), "n_particles": int(run.n_particles),
        "tally_check": assert_tally_binds_the_matrix(tallies, run),
        "widening_mode": f"per_fixture_bernoulli@alpha={book.alpha:g}",
    }


def run_cell_arms(cell_key_: str, *, simulate: Callable[[str, Any], Any],
                  record: Callable[[str, Any, Any], dict[str, Any]],
                  books: dict[str, Any],
                  parity_row: dict[str, Any] | None,
                  provisional_control: Sequence[str],
                  ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """One cell's two arms, IN THE ORDER §3.3's closure 1 fixes.

    > **A design in which the new runner simulates control and treatment and
    > only then compares the control against protected output has already
    > executed the treatment before establishing parity, and does not satisfy
    > this clause.**

    That was v1's design and it survived into v2's harness: ``TableRunner``
    simulated both arms and ``run_table`` compared afterwards, so the first
    treated simulation of every cell ran before that cell's parity was
    established. The order here is the document's, and it is a property of the
    code rather than of a comment:

    1. simulate the CONTROL arm and build its record;
    2. establish native parity against protected ``ArchiveRunner`` at this
       cell — :func:`assert_native_parity`, which raises
       :class:`TableIdentityBreak` on any disagreement;
    3. **only then** simulate the TREATMENT arm.

    ``simulate`` and ``record`` are supplied by the caller so that the ORDER can
    be executed and observed without a real fit: a spy passed here records
    exactly how many arms were simulated before the refusal, which is the only
    way "before" is checkable at all.

    **What that means this function can and cannot establish**, since the review
    (P5-B5) is right that a callback labelled "control" could do treatment work
    inside itself. What is mechanical here is the sequence of THIS function's own
    calls — one arm, then the parity comparison, then the second arm — and that
    each record came back labelled as the arm it was asked for; what is not
    mechanical is the inside of a callback. It is not a public surface for that
    reason: the production caller is :meth:`TableRunner.__call__`, whose two
    callbacks close over the protected sampler, and §8.5's rows drive it with
    spies that count. It is out of ``__all__``.
    """
    if not parity_row or not (parity_row or {}).get("substantive_digest"):
        raise TableIdentityBreak(
            f"{cell_key_}: no protected parity row was supplied to the cell, so "
            "the control arm has nothing to be compared against and §3.3's "
            "closure 1 — parity established BEFORE one treated simulation — "
            "cannot hold. The oracle runs to completion first and its rows are "
            "the precondition of this leg, not its by-product.")

    arms: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    control_run = simulate("control", books["control"])
    order.append("control")
    arms["control"] = record("control", books["control"], control_run)
    if str(arms["control"].get("arm", "control")) != "control":
        raise TableIdentityBreak(
            f"{cell_key_}: the record returned for the control arm calls itself "
            f"{arms['control'].get('arm')!r}. §3.3's closure 1 orders the two "
            "arms and an arm that is not the one it was asked for makes the "
            "order meaningless.")
    parity = assert_native_parity(
        cell_key_, arms["control"]["substantive_digest"], parity_row,
        provisional_control,
        effective_posterior=arms["control"].get("effective_posterior_hash"))
    if order != ["control"]:                                # pragma: no cover
        raise TableIdentityBreak(
            f"{cell_key_}: {len(order)} arm(s) were simulated before parity was "
            "established, and §3.3's closure 1 permits exactly one — the "
            "control.")
    treatment_run = simulate("treatment", books["treatment"])
    order.append("treatment")
    arms["treatment"] = record("treatment", books["treatment"], treatment_run)
    return arms, parity


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
                 config: dict | None = None,
                 require_verified_adjustments: bool = True,
                 verbose: bool = True,
                 directory: Path | str | None = None):
        from epl import anchor as anchor_mod, baseline, freeze
        from epl import fit as epl_fit
        from epl.schema import sort_for_walk_forward

        self.matches = baseline.load_matches() if matches is None else matches
        self.played = (sort_for_walk_forward(self.matches.loc[self.matches["played"]])
                       if played is None else played)
        # §8.6: no freeze-state boolean on any public fit surface. The guard
        # establishes the state; this object records what it established.
        self.directory = Path(directory) if directory is not None else TABLE_DIR
        self.may_fit = assert_may_fit(
            "epl.evwiden.TableRunner", played=self.played,
            directory=self.directory)
        self.harness_frozen = bool(self.may_fit["frozen"])
        self.config = freeze.frozen_wcmodel_config() if config is None else config
        self.config_sha256 = assert_config_frozen(cfg=self.config)
        self.store = epl_fit.build_store(self.played) if store is None else store
        self.anchor = (anchor_mod.Anchor(self.played, freeze.frozen_elo_config())
                       if anchor is None else anchor)
        # §2.3's closure, and §8.6's: the budget is RESOLVED from the frozen
        # law, never accepted. There is no `n_sims`, `seed` or `chunk_size`
        # parameter on this surface and there may not be one.
        frozen = frozen_table_constants()
        self.n_sims, self.seed = frozen["n_sims"], frozen["seed"]
        self.chunk_size = frozen["chunk_size"]
        self.require_verified_adjustments = bool(require_verified_adjustments)
        self.verbose = bool(verbose)
        self.harness_sha256 = sha256_file(paths.REPO_ROOT / HARNESS_FILES[0])
        self._epl_fit = epl_fit

    def __call__(self, cell: dict[str, Any],
                 parity_row: dict[str, Any] | None = None) -> dict[str, Any]:
        import dataclasses

        from epl import dcfit, particles, season as season_mod
        from epl import simmetrics, simretro, table as table_mod

        season, label = str(cell["season"]), str(cell["cutoff_label"])
        cutoff = pd.Timestamp(cell["cutoff"]).normalize()
        started = time.perf_counter()
        may = assert_may_fit("epl.evwiden.TableRunner", played=self.played,
                             directory=self.directory)

        state = season_mod.archive_season_state(
            self.matches, season, cutoff,
            require_verified_adjustments=self.require_verified_adjustments)
        with self._epl_fit.config_read_once(self.config):
            # §8.6: "the record is written after the call that performs the fit
            # has been entered and IMMEDIATELY BEFORE THE SAMPLER IS INVOKED".
            # It used to sit above `archive_season_state`, which can refuse on
            # an unverified adjustment — an attempt timestamp dressed as an
            # occurrence timestamp, which is what the review found at this site
            # and at two others.
            if may["frozen"] and may["real_artifacts"]:
                record_first_real_fit(where="epl.evwiden.TableRunner")
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
                "treated cells are pinned by the §8.3 commit; a run in which a "
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

        tallies: dict[str, np.ndarray] = {}

        def _simulate(name: str, book):
            run = simulate_arm(state, book, played=self.played,
                               directory=self.directory,
                               n_particles=book.n_particles)
            table_mod.check_doubly_stochastic(run.matrix)
            return run

        def _record(name: str, book, run):
            tally = particle_tallies(run)
            tallies[name] = tally
            # §8.7's rebinding read needs the matrix and the two counts back;
            # they travel inside the sidecar so `load_tallies` can re-run §5.1's
            # binding checks without a live SimRun.
            tallies[f"matrix_{name}"] = np.asarray(run.matrix, dtype=float)
            record = arm_record(
                run, tally, book, clubs=clubs, positions=positions, spans=spans,
                truth=truth, weights=weights,
                realised_hash=realised.realised_hash,
                treated_clubs=cell["treated_clubs"])
            if self.verbose:
                print(f"[evwiden-table] {season} {label} {name} "
                      f"TRPS={record['trps']:.6f}", flush=True)
            return record

        arms, parity = run_cell_arms(
            f"{season}|{label}", simulate=_simulate, record=_record,
            books={"control": control, "treatment": treatment},
            parity_row=parity_row,
            provisional_control=sorted(control.provisional))

        identical = assert_table_identity(
            cell["treated_clubs"], arms["control"]["sampler_digest"],
            arms["treatment"]["sampler_digest"], where=f"{season} {label}")
        assert_provisional_fields(cell["treated_clubs"],
                                  arms["control"]["provisional"],
                                  arms["treatment"]["provisional"],
                                  where=f"{season} {label}")

        return {
            "schema": SCHEMA_ID, "season": season, "cutoff_label": label,
            "cutoff": str(cutoff.date()), "clubs": clubs,
            "treated_clubs": sorted(cell["treated_clubs"]),
            "provisional_incumbent": sorted(incumbent),
            "provisional_enlarged": sorted(enlarged),
            # §3.3: the provisional set left both digests and became a
            # COMPARED FIELD, checked three ways — against the protected
            # runner's own provenance at the parity oracle, against the frozen
            # 16/19 census here, and by `assert_provisional_fields`.
            "provisional_control": sorted(control.provisional),
            "provisional_treatment": sorted(treatment.provisional),
            "evidence": dict(cell["evidence"]),
            "n_sims": self.n_sims, "seed": self.seed,
            "arms": arms, "identical": identical, "parity": parity,
            "realised_hash": realised.realised_hash,
            "realised_positions": {c: int(p) for c, p in
                                   zip(clubs, positions.tolist())},
            "realised_spans": {c: int(s) for c, s in zip(clubs, spans.tolist())},
            "realised_points": {c: int(p) for c, p in zip(clubs, truth.tolist())},
            "consequence_weights": [float(w) for w in weights],
            "n_training_matches": int(info.n_training_matches),
            "cold_start_teams": list(info.cold_start_teams),
            "config_sha256": self.config_sha256,
            "harness_sha256": self.harness_sha256,
            "wall_seconds": round(time.perf_counter() - started, 2),
            #: Not written to the ledger — `run_table` lifts it out and saves
            #: the arrays beside it, because the joint bootstrap of §5 needs
            #: all thirty tallies at once and a JSONL row is not where a
            #: [1000, 20, 20] float64 array belongs.
            "_tallies": tallies,
        }


def assert_table_identity(treated_clubs: Sequence[str], control_digest: str,
                          treatment_digest: str, *, where: str) -> bool:
    """§3.3's two-sided cell identity, restated on ``sampler_digest``.

    The 17 untouched cells are "unchanged by construction, **and the harness
    must prove it**": an untouched cell whose two arms' sampler digests differ
    is :class:`TableIdentityBreak`.

    The other direction is equally required by §3.3: a treated cell whose two
    arms' sampler digests are EQUAL is :class:`TableIdentityBreak` too. A
    treatment that changes no sampler output where the rule says it must is not
    a null result; it is a treatment that never reached the sampler, and
    reporting its zero delta as evidence of no harm would be reporting the
    absence of the experiment.

    **The digest this reads must be ``sampler_digest``, and that is the whole
    repair.** v1's digest included the provisional set, so a treated
    cell's two digests differed the moment the metadata named a different set —
    whether or not one scoreline changed. With the provisional set outside the
    digest the second condition is a statement about scorelines, tie blocks and
    points, the things the D12 branch actually moves, and it can fail.
    """
    identical = bool(str(control_digest) == str(treatment_digest))
    if not treated_clubs and not identical:
        raise TableIdentityBreak(
            f"{where} carries no treated club, so the two books are the same "
            "book and the two runs must be the same run — but their sampler "
            f"digests differ ({str(control_digest)[:12]}… vs "
            f"{str(treatment_digest)[:12]}…). §3.3 rules the 17 untouched cells "
            "unchanged BY CONSTRUCTION and requires the harness to prove it; a "
            "break here means the treatment reaches further than the rule names.")
    if treated_clubs and identical:
        raise TableIdentityBreak(
            f"{where} carries treated clubs {sorted(treated_clubs)} and the two "
            "arms produced byte-identical SAMPLER OUTPUT. A treatment that "
            "changes nothing where the rule says it should is not a null result "
            "— it is a treatment that never reached the sampler, and its zero "
            "delta is the absence of the experiment rather than evidence of no "
            "harm.")
    return identical


def assert_provisional_fields(treated_clubs: Sequence[str],
                              provisional_control: Sequence[str],
                              provisional_treatment: Sequence[str], *,
                              where: str) -> None:
    """§3.3: metadata is checked AS METADATA, the sampler by its output.

    The provisional set left both digests, so it is compared directly: the
    treatment's set must be a strict superset of the control's at a treated
    cell and equal to it at an untouched one, and the difference must be exactly
    the clubs the rule names.
    """
    control = {str(c) for c in provisional_control}
    treatment = {str(c) for c in provisional_treatment}
    treated = {str(c) for c in treated_clubs}
    if treated:
        if not treatment > control or (treatment - control) != treated:
            raise TableIdentityBreak(
                f"{where}: the treatment book's provisional set adds "
                f"{sorted(treatment - control)} to the control's, and §3.3's "
                f"frozen enumeration names {sorted(treated)}. §3.3 makes the "
                "provisional set a compared field precisely so a mismatch here "
                "is caught as metadata rather than smuggled into a digest.")
    elif treatment != control:
        raise TableIdentityBreak(
            f"{where} is one of the 17 untouched cells, so the two books carry "
            f"the same provisional set — and they do not: the treatment adds "
            f"{sorted(treatment - control)} and drops "
            f"{sorted(control - treatment)}.")


# --------------------------------------------------------------------------
# §3.3 — the 32-cell native-parity oracle against PROTECTED code
# --------------------------------------------------------------------------

class ParityRunner:
    """Protected :class:`epl.simretro.ArchiveRunner`, `dc_native`, one cell.

    §3.3: binding the SCHEDULE to protected code binds neither
    ``ArchiveRunner``'s semantics — verified adjustments, ``config_read_once``,
    particle-book construction, boundaries, chunking, refusal handling, ranker
    checks, provenance — nor its call. The 19-untouched-cell control compares
    two arms produced by the SAME new code, so any drift shared by both arms
    passes it silently. The oracle is the answer: the new runner must reproduce
    the protected runner's ``dc_native`` output at ALL THIRTY-FIVE cells, no
    sampling, before one treated simulation is executed.

    §2.4 budgets the oracle its own 35 fits, because ``ArchiveRunner`` owns its
    own fit (`epl/simretro.py:520-527,536`), exposes no posterior and no
    ``ParticleBook`` for reuse, and returns ``CutoffResult``/``ArmResult`` — so
    the parity leg cannot ride the new runner's fits.

    ``data/epl/sim/retro_r1.jsonl`` stays read-only and is not the comparison
    object: the parity run is EXECUTED, not read off the archive ledger.
    """

    def __init__(self, matches: pd.DataFrame | None = None, *,
                 store=None, anchor=None, config: dict | None = None,
                 require_verified_adjustments: bool = True,
                 verbose: bool = True,
                 directory: Path | str | None = None):
        from epl import baseline, simretro

        self.matches = baseline.load_matches() if matches is None else matches
        # §8.6: no freeze-state boolean here either. The parity oracle runs
        # protected `ArchiveRunner`, which performs REAL ADVI fits — and two of
        # those, taken through this very path while v1's guard was not yet in
        # place, are what invalidated v1 (§8.1).
        self.directory = (directory if directory is NO_TARGET
                          else Path(directory) if directory is not None
                          else TABLE_DIR)
        # Asked HERE so that a run which cannot be permitted dies before it
        # builds a store and an anchor — and asked AGAIN at every cell (see
        # :meth:`__call__`). The verdict is deliberately NOT stored.
        may = self._permit()
        self.harness_frozen = bool(may["frozen"])
        # §2.3's closure: resolved from the frozen law, never accepted.
        frozen = frozen_table_constants()
        self.n_sims, self.seed = frozen["n_sims"], frozen["seed"]
        self.chunk_size = frozen["chunk_size"]
        self.require_verified_adjustments = bool(require_verified_adjustments)
        self.verbose = bool(verbose)
        self._runner = simretro.ArchiveRunner(
            self.matches, store=store, anchor=anchor, config=config,
            chunk_size=self.chunk_size,
            require_verified_adjustments=self.require_verified_adjustments,
            verbose=verbose)

    def _permit(self) -> dict[str, Any]:
        """§8.6's permission, asked fresh. Nothing here is cached (F8).

        The adjudication of 2026-08-29 found ``__init__`` caching one
        ``assert_may_fit`` and one instance then executing all thirty-two cells
        "without rereading the current document, witness, or record", against
        §8.6's every-fit promise. `assert_may_fit` re-reads the preregistration's
        current bytes, its committed blob, the first-fit record and the witness
        on every call; a stored verdict is a verdict from before the fits began.
        """
        return assert_may_fit(
            "epl.evwiden.ParityRunner",
            played=self.matches.loc[self.matches["played"]],
            directory=self.directory)

    def __call__(self, cell: dict[str, Any]) -> dict[str, Any]:
        from epl import simmetrics, simretro

        season, label = str(cell["season"]), str(cell["cutoff_label"])
        cutoff = pd.Timestamp(cell["cutoff"]).normalize()
        started = time.perf_counter()
        # §8.6, at THIS cell and not at construction (adjudication F8).
        may = self._permit()
        self.harness_frozen = bool(may["frozen"])
        if may["frozen"] and may["real_artifacts"]:
            record_first_real_fit(where="epl.evwiden.ParityRunner")
        result = self._runner(season=season, cutoff_label=label, cutoff=cutoff,
                              arms=(TABLE_ARM_LABEL,), nulls=(),
                              n_sims=self.n_sims, seed=self.seed)
        arm = result.arms[TABLE_ARM_LABEL]
        run = arm.run
        if run is None:
            raise TableIdentityBreak(
                f"{season} {label}: the protected runner returned no SimRun for "
                f"{TABLE_ARM_LABEL}, so there is nothing to compare against and "
                "§3.3's oracle cannot be executed.")
        realised = simretro.realised_positions(
            self.matches, season,
            require_verified=self.require_verified_adjustments)
        clubs = list(result.clubs)
        tally = particle_tallies(run)
        assert_tally_binds_the_matrix(tally, run)
        return {
            "schema": SCHEMA_ID, "season": season, "cutoff_label": label,
            "cutoff": str(cutoff.date()), "key": f"{season}|{label}",
            "arm": TABLE_ARM_LABEL,
            "substantive_digest": substantive_digest(
                run, tally, weights=simmetrics.consequence_weights(len(clubs)),
                boundaries=run.plan.boundaries,
                realised_hash=realised.realised_hash,
                realised_positions=realised.position_vector(clubs),
                realised_points=realised.points_vector(clubs)),
            "provisional_teams": sorted(
                str(t) for t in result.provenance["provisional_teams"]),
            "effective_posterior_hash":
                result.provenance["effective_posterior_hash"],
            "n_sims": int(run.n_sims), "n_particles": int(run.n_particles),
            "seed": self.seed, "source": "epl.simretro.ArchiveRunner (protected)",
            "wall_seconds": round(time.perf_counter() - started, 2),
        }


def run_parity_oracle(cells: Sequence[dict[str, Any]],
                      path: Path | str, *,
                      runner: Callable[[dict], dict] | None = None,
                      resume: bool = True, verbose: bool = True,
                      directory: Path | str | None = None,
                      ) -> dict[str, dict[str, Any]]:
    """Execute the protected runner at every cell and record its digest.

    Resumable per cell and never sampled: §3.3's closure 2 folds "sampling the
    parity oracle" into §2.4's standing refusal to thin the run.
    """
    path = Path(path)
    # The EXACT thirty-two, on the oracle path too (adjudication F6): the oracle
    # is what "all thirty-two priceable cells" names, and it was reachable with
    # any thirty-two that hit the aggregate census.
    assert_table_census(cells)
    # v3 §8.6, NB6: "`merge`, `run_table` and `run_parity_oracle` require the
    # sequence THEMSELVES. Each calls §8.4's marker check for its own step on
    # every invocation — not only when reached through `main` — so a direct API
    # call is exactly as ordered as a command line." The oracle is the first
    # half of step 5.
    require_sequence(SEQUENCE_STEPS[4])
    if runner is not None:
        assert_seam_allowed("run_parity_oracle(runner=...)", target=path.parent,
                            detail="an injected oracle is not protected "
                                   "epl.simretro.ArchiveRunner")
    runner = ParityRunner(verbose=verbose,
                          directory=directory or path.parent
                          ) if runner is None else runner
    done: dict[str, dict[str, Any]] = {}
    if resume and path.exists():
        rows, poison, _ = read_jsonl(path)
        if poison:
            raise ShardFailed(
                f"{paths.rel(path)} carries {len(poison)} poison row(s); the "
                f"first is {poison[0].get('error_type')}")
        done = {str(r["key"]): r for r in rows}

    path.parent.mkdir(parents=True, exist_ok=True)
    for i, cell in enumerate(cells, 1):
        key = f"{cell['season']}|{cell['cutoff_label']}"
        if key in done:
            continue
        row = runner(cell)
        with path.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        done[key] = row
        if verbose:
            print(f"[evwiden-parity] {i}/{len(cells)} {key} "
                  f"{row['substantive_digest'][:12]}…", flush=True)
    missing = [f"{c['season']}|{c['cutoff_label']}" for c in cells
               if f"{c['season']}|{c['cutoff_label']}" not in done]
    if missing:
        raise MergeIncomplete(
            f"the parity oracle is short {len(missing)} cell(s) "
            f"(first: {missing[:3]}). §3.3 requires native parity at ALL "
            "thirty-two priceable cells before one treated simulation is "
            "executed, and "
            "§3.3's closure 2 makes sampling it an amendment rather than an "
            "optimisation.")
    return done


def assert_native_parity(cell_key_: str, new_digest: str, oracle: dict[str, Any],
                         provisional_control: Sequence[str], *,
                         effective_posterior: str | None = None,
                         ) -> dict[str, Any]:
    """One cell of §3.3's oracle: the new runner's control arm against protected.

    The comparator is the ``substantive_digest``, computed by the SAME harness
    function from the protected runner's ``SimRun`` and from the new runner's
    control-arm ``SimRun``. Two things sit OUTSIDE that digest and are therefore
    compared here, directly, as fields: the provisional set (against
    ``ArchiveRunner``'s own ``provenance["provisional_teams"]``) and — §3.3's
    replacement for the excluded payload item — the effective posterior hash.
    Metadata is checked as metadata; the sampler is checked by its output.
    """
    want = str(oracle["substantive_digest"])
    if str(new_digest) != want:
        raise TableIdentityBreak(
            f"{cell_key_}: the new runner's control arm hashes to "
            f"{str(new_digest)[:12]}… and protected epl.simretro.ArchiveRunner's "
            f"own dc_native run hashes to {want[:12]}…. §3.3 requires native "
            "parity at all thirty-two priceable cells before one treated "
            "simulation "
            "runs: binding the schedule to protected code binds neither its "
            "semantics nor its call, and the 19-untouched-cell control cannot "
            "see a drift both arms share.")
    theirs = sorted(str(t) for t in oracle["provisional_teams"])
    ours = sorted(str(t) for t in provisional_control)
    if ours != theirs:
        raise TableIdentityBreak(
            f"{cell_key_}: the control book's provisional set {ours} is not "
            f"the protected runner's {theirs}. §3.3 takes the provisional set "
            "out of the digest and compares it as a field, so this is the "
            "check that the control arm IS the incumbent arm.")
    their_book = oracle.get("effective_posterior_hash")
    if effective_posterior is None or their_book is None:
        raise TableIdentityBreak(
            f"{cell_key_}: the effective posterior hash is missing on "
            f"{'the new runner' if effective_posterior is None else ''}"
            f"{' and ' if effective_posterior is None and their_book is None else ''}"
            f"{'the protected oracle' if their_book is None else ''} side. §3.3 "
            "takes this hash OUT of the substantive digest — `content_hash` "
            "hashes `sorted(self.provisional)` and embedding it would re-admit "
            "the provisional set into a digest that excludes it — and makes it "
            "a separately-COMPARED provenance field instead. A comparison that "
            "runs only when both sides happen to be present fails OPEN, which "
            "is the one thing the exclusion cannot afford: it is what makes "
            "excluding it cost nothing.")
    if str(effective_posterior) != str(their_book):
        raise TableIdentityBreak(
            f"{cell_key_}: the control book's effective posterior hashes to "
            f"{str(effective_posterior)[:12]}… and the protected runner's to "
            f"{str(their_book)[:12]}…. §3.3 excludes this hash from the "
            "substantive digest — `ParticleBook.content_hash()` hashes "
            "`sorted(self.provisional)`, and embedding it would re-admit the "
            "provisional set into a digest that excludes it — and makes it a "
            "separately-COMPARED provenance field instead. This is that "
            "comparison, and it is the reason excluding it costs nothing.")
    return {"key": cell_key_, "parity_digest_simretro": want,
            "effective_posterior_simretro": their_book, "PASS": True}


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


PARITY_NAME = "parity.jsonl"


def parity_path(ledger_path: Path | str) -> Path:
    """§3.3's completion marker, beside the table ledger."""
    return Path(ledger_path).parent / PARITY_NAME


def assert_parity_complete(cells: Sequence[dict[str, Any]],
                           parity: dict[str, dict[str, Any]] | None,
                           *, where: str = "run_table") -> dict[str, Any]:
    """§3.3's closure 1: **completion, not interleaving** — and it runs FIRST.

    > The parity oracle runs to completion over all 32 priceable cells and writes
    > `data/epl/sim/evwiden/parity.jsonl` (35 rows) as its completion marker.
    > `run_table` refuses to simulate any arm until that file exists and carries
    > all 32 cells with matching digests. **A design in which the new runner
    > simulates control and treatment and only then compares the control against
    > protected output has already executed the treatment before establishing
    > parity, and does not satisfy this clause.**

    v1 was exactly that design: `run_parity_oracle` produced protected rows
    first, but `TableRunner` then simulated BOTH arms and `run_table` compared
    the control afterwards, per cell. The first treated simulation therefore ran
    before the oracle had been checked against anything.

    Three demands, in order: the oracle covers **every** cell of the run; the
    run covers **all thirty-two** priceable cells (a 31-cell run is not this
    run, and "all 32 is the whole content of the control"); and every oracle row
    carries
    a digest to compare against.
    """
    parity = dict(parity or {})
    want = [f"{c['season']}|{c['cutoff_label']}" for c in cells]
    short = [k for k in want if k not in parity]
    if short:
        raise TableIdentityBreak(
            f"{where}: the parity oracle covers {len(parity)} of the "
            f"{len(want)} cells about to be simulated and is short "
            f"{len(short)} (first: {short[:3]}). §3.3 requires native parity at "
            "ALL THIRTY-FIVE cells, established **before** one treated "
            "simulation is executed — not interleaved with it. Run the oracle "
            "to completion first; it writes parity.jsonl as its completion "
            "marker, and that file is the precondition of this leg.")
    if len(want) != EXPECTED_TABLE_CELLS:
        raise TableIdentityBreak(
            f"{where}: the table leg was handed {len(want)} cells, not the "
            f"pre-stated {EXPECTED_TABLE_CELLS}. §3.3: 'All 32' is the whole "
            "content of the control, and §2.4 makes dropping cells to fit a "
            "clock an amendment rather than an optimisation — expressly "
            "including sampling or truncating the parity oracle.")
    blank = [k for k in want if not (parity[k] or {}).get("substantive_digest")]
    if blank:
        raise TableIdentityBreak(
            f"{where}: {len(blank)} oracle row(s) carry no substantive digest "
            f"(first: {blank[:3]}), so there is nothing for the control arm to "
            "be compared against before it is simulated.")
    return {"n_cells": len(want), "PASS": True,
            "established": "before one treated simulation (§3.3)"}


def tallies_dir(ledger_path: Path | str) -> Path:
    """Where the per-particle tallies live, beside the table ledger.

    §5.2 applies ONE resample index to all thirty tallies at once,
    so the estimator needs every deciding cell's tallies simultaneously and a
    JSONL row is not where a ``[1000, 20, 20]`` float64 array belongs. They are
    written beside the ledger, inside §8.3's `data/epl/sim/evwiden*` write set.
    """
    return Path(ledger_path).parent / "tallies"


def tally_path(ledger_path: Path | str, row: dict[str, Any]) -> Path:
    key = f"{row['season']}|{row['cutoff_label']}".replace("/", "-")
    return tallies_dir(ledger_path) / f"{key}.npz"


class _ReboundRun:
    """The three fields §5.1's binding checks read, recovered from the sidecar.

    :func:`assert_tally_binds_the_matrix` was written against a live
    :class:`epl.leaguesim.SimRun`; on a reload there is no run, so the scored
    matrix and the two counts travel INSIDE the npz and this stands in for it.
    That is what lets §8.7's "re-runs §5.1's two binding checks before the
    arrays are used to decide anything" be literally true rather than aspirational.
    """

    __slots__ = ("matrix", "n_sims", "n_particles")

    def __init__(self, matrix, n_sims, n_particles):
        self.matrix = np.asarray(matrix, dtype=float)
        self.n_sims = int(n_sims)
        self.n_particles = int(n_particles)


def write_tallies(ledger_path: Path | str, row: dict[str, Any],
                  arms: dict[str, Any]) -> tuple[Path, str]:
    """Write one cell's two tallies, with the matrices that bind them.

    Returns the path and its SHA-256, which §8.7 puts on the ledger row **at the
    same moment as the row**: a digest written later is a digest of whatever the
    file had become by then.
    """
    target = tally_path(ledger_path, row)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "control": np.asarray(arms["control"], dtype=float),
        "treatment": np.asarray(arms["treatment"], dtype=float),
    }
    for arm in ("control", "treatment"):
        leg = (row.get("arms") or {}).get(arm) or {}
        payload[f"matrix_{arm}"] = np.asarray(
            arms.get(f"matrix_{arm}",
                     payload[arm].sum(axis=0) / float(row["n_sims"])),
            dtype=float)
        payload[f"n_sims_{arm}"] = np.asarray(
            int(leg.get("n_sims", row["n_sims"])))
        payload[f"n_particles_{arm}"] = np.asarray(
            int(leg.get("n_particles", payload[arm].shape[0])))
    np.savez_compressed(target, **payload)
    return target, sha256_file(target)


def load_tallies(ledger_path: Path | str, row: dict[str, Any],
                 ) -> dict[str, np.ndarray]:
    """§8.7's rebinding read. **Every read rebinds.**

    > The 35 per-cell tally files are written beside the table ledger [...] Each
    > is a live deciding input: §5's estimator and §5.4's unanimity rule read
    > them, and a structurally valid replacement could alter the MC standard
    > errors — and turn UNRESOLVED into PASS — without changing any other
    > digest.
    >
    > * **every read rebinds**: `load_tallies` recomputes the file's digest and
    >   refuses (`TableMCImprecise`) on any disagreement, and re-runs §5.1's two
    >   binding checks before the arrays are used to decide anything.

    v1 wrote the sidecars and reloaded them checking neither. A swapped file
    that was still a legal tally passed straight into P1–P5.
    """
    path = tally_path(ledger_path, row)
    if not path.exists():
        raise TableMCImprecise(
            f"{paths.rel(path)} is not on disk, so cell "
            f"{cell_key(row)}'s per-particle tallies cannot be resampled. "
            "§5's estimator is jointly paired across cells and there is no "
            "per-cell fallback: a missing tally is a refusal, not a smaller "
            "bootstrap.")

    recorded = row.get("tally_sha256")
    actual = sha256_file(path)
    if not recorded:
        raise TableMCImprecise(
            f"cell {cell_key(row)}'s ledger row records no `tally_sha256`, so "
            f"{paths.rel(path)} is not bound to anything. §8.7: 'every table "
            "ledger row records the SHA-256 of its own tally file, written at "
            "the same moment as the row' and 'every read rebinds'. A read that "
            "treats an absent digest as nothing to check is a read that binds "
            "nothing, and a structurally valid replacement could then alter the "
            "MC standard errors — and turn UNRESOLVED into PASS — without "
            "changing any other digest.")
    if str(recorded) != actual:
        raise TableMCImprecise(
            f"{paths.rel(path)}'s digest is {actual[:12]}… and cell "
            f"{cell_key(row)}'s ledger row records {str(recorded)[:12]}…. §8.7 "
            "binds every deciding tally to the row written at the same moment: "
            "'a structurally valid replacement could alter the MC standard "
            "errors — and turn UNRESOLVED into PASS — without changing any "
            "other digest'. This read rebinds, and the binding does not hold.")

    with np.load(path) as data:
        out = {"control": np.asarray(data["control"], dtype=float),
               "treatment": np.asarray(data["treatment"], dtype=float)}
        bound = {}
        for arm in ("control", "treatment"):
            if f"matrix_{arm}" in data.files:
                bound[arm] = _ReboundRun(
                    data[f"matrix_{arm}"],
                    int(np.asarray(data[f"n_sims_{arm}"]).item()),
                    int(np.asarray(data[f"n_particles_{arm}"]).item()))

    # §5.1's two binding checks, re-run BEFORE the arrays decide anything.
    for arm, run in bound.items():
        assert_tally_binds_the_matrix(out[arm], run)
    return out


def run_table(cells: Sequence[dict[str, Any]],
              ledger_path: Path | str | None = None, *,
              runner: Callable[..., dict] | None = None,
              parity: dict[str, dict[str, Any]] | None = None,
              parity_runner: Callable[[dict], dict] | None = None,
              config_sha: str | None = None, resume: bool = True,
              verbose: bool = True,
              ) -> dict[str, Any]:
    """Run both arms at every cell and append one JSONL row per cell.

    THE PARITY ORACLE RUNS TO COMPLETION FIRST, at all thirty-two cells, and
    :func:`assert_parity_complete` is checked **before the loop that simulates
    anything** (§3.3's closure 1). v1 checked it per cell, inside the loop and
    after the runner had already produced both arms — so the first treated
    simulation ran before parity was established anywhere. There is no
    ``require_parity`` parameter: "an exposed boolean that turns the oracle off
    is a bypass; the document does not permit one and the harness may not carry
    one. Parity is a property of the run, not an option of the caller."

    Resumable per cell and poisoned per cell, exactly as the match-level shard
    is: §2.4's budget for this leg is 64 fits and 96 runs of 20,000 simulated
    seasons — bounded by ~4 hours — and a crash two hours in should cost the
    cell in flight and nothing else.
    """
    ledger_path = Path(ledger_path) if ledger_path is not None else TABLE_LEDGER
    # §8.6's closure first, so a seam is refused by its own name.
    for name, seam in (("runner", runner), ("parity", parity),
                       ("parity_runner", parity_runner)):
        if seam is not None:
            assert_seam_allowed(f"run_table({name}=...)",
                                target=ledger_path.parent,
                                detail="an injected implementation or a "
                                       "supplied oracle is not the run this "
                                       "document preregisters")
    harness_frozen = _frozen_now()
    # The EXACT thirty-two, here and not only where they were enumerated
    # (adjudication F6, V3-B1: "direct table/oracle paths bypass it"). A direct
    # `run_table(cells, ...)` is the deciding leg however it was reached.
    assert_table_census(cells)
    # v3 §8.6, NB6: step 5's own marker check, on every invocation and not only
    # through `main`. A direct `run_table(...)` used to be as unordered as a
    # function call.
    require_sequence(SEQUENCE_STEPS[4])
    _guard_ledger_location(ledger_path, harness_frozen)
    if parity is None:
        parity = run_parity_oracle(
            cells, parity_path(ledger_path), runner=parity_runner,
            resume=resume, verbose=verbose,
            directory=ledger_path.parent)
    parity = dict(parity)
    # BEFORE the runner is even constructed, and long before the loop: a cell
    # simulated without a complete oracle is `TableIdentityBreak` (§7.1), and
    # §10 makes an oracle "established after any treated simulation" an
    # invalidation. The check is cheap; the thing it guards costs four hours.
    parity_check = assert_parity_complete(cells, parity)
    runner = TableRunner(verbose=verbose, directory=ledger_path.parent
                         ) if runner is None else runner
    frozen_budget = frozen_table_constants()
    n_sims = int(getattr(runner, "n_sims", frozen_budget["n_sims"]))
    seed = int(getattr(runner, "seed", frozen_budget["seed"]))
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
            row = runner(cell, parity[cell_key(cell)])
        except EvWidenError as exc:
            _poison_table(ledger_path, cell, key, exc)
            raise
        except Exception as exc:                     # noqa: BLE001 — typed below
            wrapped = FitFailed(
                f"{cell['season']} {cell['cutoff_label']}: "
                f"{type(exc).__name__}: {exc}")
            _poison_table(ledger_path, cell, key, wrapped)
            raise wrapped from exc

        arm_tallies = row.pop("_tallies", None)
        ck = cell_key(row)
        # The oracle's completeness was established before the loop and the
        # per-cell comparison ran INSIDE `run_cell_arms`, between the control
        # arm and the treatment arm (§3.3's closure 1). This is the same
        # comparison re-run on the row that was actually returned, so an
        # injected runner cannot skip it either — there is no branch here in
        # which a cell publishes a null parity.
        row["parity"] = assert_native_parity(
            ck, row["arms"]["control"]["substantive_digest"], parity[ck],
            row["provisional_control"],
            effective_posterior=(row["arms"]["control"]
                                 .get("effective_posterior_hash")))
        row["parity_digest_simretro"] = parity[ck]["substantive_digest"]
        # §8.7: the tally is written and its digest goes onto the row AT THE
        # SAME MOMENT. A digest computed later is a digest of whatever the file
        # had become by then, which is the thing the binding exists to refuse.
        tally_sha = None
        if arm_tallies is not None:
            _, tally_sha = write_tallies(ledger_path, row, arm_tallies)
        if not tally_sha:
            raise SchemaMismatch(
                f"the cell {ck} produced no per-particle tallies, so its row "
                "would carry `tally_sha256: null`. §8.7 makes every deciding "
                "tally a live input bound to the row written at the same "
                "moment; a row with nothing to bind is not a row this leg may "
                "write.")
        row.update({"key": key, "harness_frozen": bool(harness_frozen),
                    "config_sha256": config_sha, "tally_sha256": tally_sha})
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
            "ledger": str(ledger_path), "parity": parity_check,
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
    if expected is not None and _is_preregistered_target(path.parent):
        # §8.6: a caller-supplied census is a caller-supplied deciding
        # population, and §3.3's is 32 cells recomputed from the pinned
        # artifacts. At the PREREGISTERED ledger the supplied one has to BE
        # that census — the production caller derives it and passes what it
        # derived, and anything else is a caller choosing which cells the merge
        # demands. An audit reading its own rows in its own directory states
        # its own, which is what §8.2 says an audit run is.
        want = _frozen_table_cell_keys()
        got = sorted(f"{c['season']}|{c['cutoff_label']}" for c in expected)
        if want is None or sorted(want) != got:
            raise EvWidenError(
                f"refusing the expected cell census supplied for "
                f"{paths.rel(path)}: it names {len(got)} cell(s) and §3.3's, "
                f"recomputed here from the pinned artifacts, names "
                f"{len(want or ())}. §8.6's public-surface closure covers any "
                "parameter that can truncate a deciding population, and the "
                "census the preregistered merge demands is the document's, not "
                "the caller's. An audit states its own census on its own rows "
                "in its own directory.")
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


def _cell_positions(row: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """The cell's own realised position vector and realised block widths.

    §5.2: ``positions_c`` and ``spans_c`` are "the same two arrays the
    cell's point estimate is scored with" — read back off the row in the club
    order the run used, never re-derived from a schedule.
    """
    clubs = [str(c) for c in row["clubs"]]
    positions = np.array([int(row["realised_positions"][c]) for c in clubs],
                         dtype=int)
    spans = np.array([int(row["realised_spans"][c]) for c in clubs], dtype=int)
    return positions, spans


def paired_mc_bootstrap(cells: Sequence[dict[str, Any]], *,
                        n_boot: int = MC_BOOT, seed: int = MC_SEED,
                        ) -> dict[str, Any]:
    """§5's estimator: tie-aware, jointly resampled, covariance by construction.

    ``cells`` is one entry per DECIDING cell — §5 runs the estimator over the
    15 treated cells and MW19 enters nothing — each carrying ``key``,
    ``cutoff_label``, ``positions``, ``spans`` and the two arms' per-particle
    fractional rank-mass tallies.

    STEP 2, the preconditions and the refusal that guards them. All tallies must
    report the same ``n_particles`` ``P`` and every particle must carry the same
    whole number of simulated seasons. Joint resampling is undefined without a
    common index space and this document will not approximate one, so a
    violation is :class:`TableMCImprecise` and stops the table leg.

    STEP 3, one resample per replicate applied to all thirty tallies. The
    same ``picked`` is applied to both arms of a cell — the CRN pairing, since
    the arms share particles and streams and differ only on the D12 branch — AND
    to every other cell, which is §5's repair of v1's false
    independence: ``epl.leaguesim.streams(seed, chunk, fixture_ordinal)`` reads
    only those three things, not the season and not the cell, and all 32 cells
    run at the same seed, so simulated season *n* of one cell consumes the same
    uniforms as simulated season *n* of another. **There is no quadrature step
    and no independence claim anywhere in this estimator**: the label means are
    computed INSIDE each replicate and their spread is read directly, so
    whatever covariance the shared streams induce is reproduced within every
    replicate rather than modelled.

    Resampling the particle INDEX does not claim that particle *s* of one cell
    is the same posterior draw as particle *s* of another — it plainly is not.
    It uses the fact that the shared randomness is indexed by
    ``(particle index, chunk, fixture_ordinal)`` and the particle index is
    deterministic in the season index, so two cells that share uniforms move
    together inside a replicate exactly as they move together in the run.

    HONEST LIMITS, stated here as §5 states them: the particle is the
    cluster, as it is in every Monte-Carlo error this repository publishes;
    within-particle match randomness at fixed particle is resampled only through
    the seasons each particle carries; and a 7-, 4-, 3- or 2-cell label mean is
    a small average however it is estimated. This is a BOUND on how much of the
    gate's margin is simulation noise, not a model of the fit's own uncertainty,
    which no table statistic in this experiment sees.
    """
    assert_not_overridable(n_boot=(n_boot, MC_BOOT), seed=(seed, MC_SEED))
    if not cells:
        raise TableMCImprecise(
            "the paired Monte-Carlo estimator was handed no deciding cell. "
            "§5.2 runs it over the 15 treated cells; an empty set means the "
            "table leg's own census disagrees with §3.3's.")

    particles = {int(np.asarray(c["control"]).shape[0]) for c in cells} | \
                {int(np.asarray(c["treatment"]).shape[0]) for c in cells}
    if len(particles) != 1:
        raise TableMCImprecise(
            f"the deciding cells carry {sorted(particles)} particles. §5 "
            "step 2 requires ONE common index space across all thirty-two "
            "tallies; joint resampling is undefined without it.")
    n_particles = particles.pop()
    if n_particles < 2:
        raise TableMCImprecise(
            f"a bootstrap over {n_particles} particle(s) resamples nothing")

    seasons_per_particle: set[float] = set()
    for cell in cells:
        for arm in ("control", "treatment"):
            tally = np.asarray(cell[arm], dtype=float)
            if tally.ndim != 3 or tally.shape[1] != tally.shape[2]:
                raise TableMCImprecise(
                    f"{cell['key']} {arm}: a tally is [particles, clubs, ranks] "
                    f"with clubs == ranks; got {tally.shape}")
            per = tally.sum(axis=2)
            if not np.allclose(per, per.flat[0], atol=1e-9):
                raise TableMCImprecise(
                    f"{cell['key']} {arm}: the particles carry unequal season "
                    "counts. §5.2 makes that a refusal, not something "
                    "to reweight.")
            seasons_per_particle.add(round(float(per.flat[0]), 9))
    if len(seasons_per_particle) != 1:
        raise TableMCImprecise(
            f"the deciding cells carry {sorted(seasons_per_particle)} simulated "
            "seasons per particle; §5.2 requires one whole number, "
            "shared.")
    per_particle = seasons_per_particle.pop()
    if abs(per_particle - round(per_particle)) > 1e-9:
        raise TableMCImprecise(
            f"{per_particle} simulated seasons per particle is not a whole "
            "number, so the particle is not a cluster of complete seasons.")

    order = list(cells)
    labels = sorted({str(c["cutoff_label"]) for c in order})
    rng = np.random.default_rng(int(seed))
    per_cell = {str(c["key"]): np.empty(int(n_boot), dtype=float) for c in order}
    per_label = {lab: np.empty(int(n_boot), dtype=float) for lab in labels}

    for r in range(int(n_boot)):
        picked = rng.integers(0, n_particles, n_particles)
        for key, delta in _resampled_cell_deltas(order, picked).items():
            per_cell[key][r] = delta
        for lab in labels:
            keys = [str(c["key"]) for c in order
                    if str(c["cutoff_label"]) == lab]
            per_label[lab][r] = float(np.mean([per_cell[k][r] for k in keys]))

    return {
        "schema": SCHEMA_ID, "mc_boot": int(n_boot), "mc_seed": int(seed),
        "n_particles": int(n_particles),
        "sims_per_particle": float(per_particle),
        "n_deciding_cells": len(order),
        "mc_se_label": {lab: float(np.std(per_label[lab], ddof=1))
                        for lab in labels},
        "mc_se_per_cell": {k: float(np.std(v, ddof=1))
                           for k, v in per_cell.items()},
        "estimator": ("§5: tie-aware fractional rank mass, one resample "
                      "index per replicate applied to every tally, label means "
                      "computed inside the replicate — no quadrature, no "
                      "independence claim"),
        "decides": "only ever to REFUSE — an UNRESOLVED gate blocks adoption "
                   "and can never grant one",
    }


def _resampled_cell_deltas(cells: Sequence[dict[str, Any]],
                           picked: np.ndarray) -> dict[str, float]:
    """One joint particle resample, applied to every tally, scored per cell.

    §5.2's inner two loops, factored out so §5.4's unanimity rule can apply its
    own draw "**exactly as §5.2 applies its own draw**" rather than by a second
    implementation that might drift from it.
    """
    from epl import simmetrics

    out: dict[str, float] = {}
    for cell in cells:
        scores = {}
        for arm in ("control", "treatment"):
            matrix = np.asarray(cell[arm], dtype=float)[picked].sum(axis=0)
            matrix = matrix / matrix.sum(axis=1, keepdims=True)
            scores[arm] = float(simmetrics.trps(matrix, cell["positions"],
                                                spans=cell["spans"]))
        out[str(cell["key"])] = scores["treatment"] - scores["control"]
    return out


def iv_c_verdict(mw6_deltas: Sequence[float], seasons: Sequence[str], *,
                 n_boot: int = N_BOOT, seed: int = BOOTSTRAP_SEED) -> bool:
    """Clause (iv-c)'s own verdict: **FAIL iff `mean_MW6 > 0` and
    `ci_lo_MW6 > 0`.**

    The interval is §5.3's, exactly — same function, same seven season blocks,
    B = 10,000, alpha = 0.05, seed 20260814 — because §5.4 recomputes *the whole
    of iv-c*, not an approximation of it.

    §2.3 names this computation inside the closure — "the two match intervals,
    **the MW6 table interval of §5**, or the power simulation of §6" — and the
    in-tree audit found it the one deciding surface that took ``n_boot`` and
    ``seed`` and refused neither: ``iv_c_verdict([...], n_boot=5)`` returned a
    verdict. Every sibling refuses; so does this now.
    """
    assert_not_overridable(n_boot=(n_boot, N_BOOT), seed=(seed, BOOTSTRAP_SEED))
    deltas = np.asarray(mw6_deltas, dtype=float)
    if deltas.size == 0:
        return False
    lo, _, _ = score_mod.block_bootstrap_ci(deltas, list(seasons),
                                            n_boot=n_boot, alpha=ALPHA,
                                            seed=seed)
    return bool(float(deltas.mean()) > 0.0 and float(lo) > 0.0)


def unanimity_fired(verdicts: Sequence[bool], *, point_verdict: bool) -> bool:
    """§5.4's counting rule, alone: **one dissenting `k` is enough.**

    "P5 fires — and gate (iv) is UNRESOLVED — unless all 200 verdicts agree with
    each other and with the point-estimate verdict."
    """
    return any(bool(v) != bool(point_verdict) for v in verdicts)


def unanimity_is_valid(unan: dict[str, Any] | None, *,
                       point_verdict: bool | None = None) -> dict[str, Any]:
    """Is this a §5.4 unanimity run at all, or an object that says it is?

    §5.4 freezes the rule completely — `K = 200`, seed 20260828, the whole of
    iv-c recomputed on 200 particle-resampled tally sets, and the verdict itself
    required to be stable — and the review's NEW-B3 found the gate trusting
    "any truthy `mc.unanimity` with `fired=False`", validating "neither `K=200`,
    seed, 200 verdicts, nor dissent consistency". A fabricated `k=1` object
    could resolve PASS.

    Every condition here is checked against the frozen law and against the
    point-estimate verdict the gate has just derived, and the answer is used
    ONE-DIRECTIONALLY: an object that fails any of them makes P5 fire, which is
    UNRESOLVED. §5.4 can only ever refuse, so an unverifiable unanimity run is
    unresolved rather than small — exactly as an absent one is.
    """
    unan = dict(unan or {})
    why: list[str] = []
    if not unan:
        why.append("no unanimity run reached the gate")
    else:
        if int(unan.get("k", -1)) != UNANIMITY_K:
            why.append(f"k = {unan.get('k')!r}, and §5.4 freezes K = "
                       f"{UNANIMITY_K}")
        if int(unan.get("seed", -1)) != UNANIMITY_SEED:
            why.append(f"seed = {unan.get('seed')!r}, and §5.4 freezes "
                       f"{UNANIMITY_SEED}")
        verdicts = unan.get("verdicts")
        if not isinstance(verdicts, (list, tuple)) or len(verdicts) != UNANIMITY_K:
            why.append(
                f"{0 if verdicts is None else len(verdicts)} recomputed iv-c "
                f"verdicts, and §5.4 requires all {UNANIMITY_K} — 'one "
                "dissenting k is enough' is a statement about a run that "
                "happened")
        else:
            pv = bool(unan.get("point_verdict"))
            dissent = sum(1 for v in verdicts if bool(v) != pv)
            if int(unan.get("dissenting", -1)) != dissent:
                why.append(
                    f"dissenting = {unan.get('dissenting')!r} against "
                    f"{dissent} verdicts that actually disagree")
            if bool(unan.get("fired")) != bool(dissent):
                why.append(f"fired = {unan.get('fired')!r} against "
                           f"{dissent} dissenting verdict(s)")
            if point_verdict is not None and pv != bool(point_verdict):
                why.append(
                    f"the run was scored against point_verdict = {pv!r} and "
                    f"this gate's own iv-c point verdict is "
                    f"{bool(point_verdict)!r}")
    return {"valid": not why, "why": "; ".join(why),
            "k": unan.get("k"), "seed": unan.get("seed"),
            "n_verdicts": (len(unan.get("verdicts"))
                           if isinstance(unan.get("verdicts"), (list, tuple))
                           else 0)}


def unanimity(cells: Sequence[dict[str, Any]], *, point_verdict: bool,
              k: int = UNANIMITY_K, seed: int = UNANIMITY_SEED,
              n_boot: int = N_BOOT, boot_seed: int = BOOTSTRAP_SEED,
              ) -> dict[str, Any]:
    """§5.4's P5, frozen, and it replaces a comparison that was invalid.

    > **The whole of iv-c is recomputed on `K = 200` particle-resampled tally
    > sets.** `rng = numpy.random.default_rng(20260828)`. For each `k` in
    > `0 … 199`: draw **one** joint particle resample
    > `picked_k = rng.integers(0, P, P)` and apply it to **all thirty
    > tallies** exactly as §5.2 applies its own draw [...] From the resulting
    > seven MW6 cell deltas compute the season-block interval of §5.3 [...] and
    > evaluate iv-c's verdict: **FAIL iff `mean_MW6 > 0` and `ci_lo_MW6 > 0`.**
    >
    > **P5 fires — and gate (iv) is UNRESOLVED — unless all 200 verdicts agree
    > with each other and with the point-estimate verdict.** One dissenting `k`
    > is enough.

    **Why this bounds what the superseded proxy could not.** v1's P5 compared
    ``|ci_lo_MW6 − 0|`` with ``2 × mc_se_mw6``. That comparison is invalid, and
    demonstrably rather than stylistically: ``mc_se_mw6`` is the Monte-Carlo
    standard error of a **linear** statistic — the equal-weight mean of seven
    cell deltas — while ``ci_lo_MW6`` is a **nonlinear quantile of a season
    bootstrap over those same seven values**. Take cross-cell Monte-Carlo error
    proportional to ``(+h, −h, 0, 0, 0, 0, 0)``: the mean error is identically
    zero, so ``mc_se_mw6`` can be arbitrarily small, while the season
    bootstrap's unequal resample multiplicities give the ``(+h, −h)`` pair
    unequal weight in most replicates and can move the lower quantile across
    zero. The proxy then fails to fire while iv-c flips from FAIL to PASS —
    precisely the direction that must never be available.

    This rule does not bound the endpoint by a scale that does not describe it;
    it **propagates the Monte-Carlo uncertainty through the actual
    computation**, re-deriving the interval endpoint 200 times from resampled
    tallies and requiring the verdict itself to be stable. It shares §5.2's own
    construction — one joint particle draw per replicate, applied to all 30
    tallies — so it carries the same cross-cell covariance for free, and it can
    only ever refuse.
    """
    assert_not_overridable(k=(k, UNANIMITY_K), seed=(seed, UNANIMITY_SEED),
                           n_boot=(n_boot, N_BOOT),
                           boot_seed=(boot_seed, BOOTSTRAP_SEED))
    cells = list(cells)
    mw6 = [c for c in cells if str(c["cutoff_label"]) == MW6_LABEL]
    if not cells or not mw6:
        return {"k": int(k), "seed": int(seed), "verdicts": [],
                "dissenting": None, "point_verdict": bool(point_verdict),
                "fired": True,
                "why": "no deciding cell carried MW6, so iv-c cannot be "
                       "recomputed and P5 cannot resolve"}

    n_particles = int(np.asarray(cells[0]["control"]).shape[0])
    seasons = [str(c["season"]) for c in mw6]
    rng = np.random.default_rng(int(seed))
    verdicts: list[bool] = []
    for _ in range(int(k)):
        picked = rng.integers(0, n_particles, n_particles)
        deltas = _resampled_cell_deltas(cells, picked)
        verdicts.append(iv_c_verdict([deltas[str(c["key"])] for c in mw6],
                                     seasons, n_boot=n_boot, seed=boot_seed))
    dissent = sum(1 for v in verdicts if bool(v) != bool(point_verdict))
    return {
        "k": int(k), "seed": int(seed), "n_boot": int(n_boot),
        "boot_seed": int(boot_seed), "n_mw6_cells": len(mw6),
        "verdicts": [bool(v) for v in verdicts],
        "point_verdict": bool(point_verdict), "dissenting": int(dissent),
        "fired": unanimity_fired(verdicts, point_verdict=point_verdict),
        "rule": ("§5.4 P5: the whole of iv-c recomputed on K = 200 "
                 "particle-resampled tally sets; P5 fires unless all 200 "
                 "verdicts agree with each other and with the point-estimate "
                 "verdict. One dissenting k is enough."),
        "decides": "only ever to REFUSE",
    }


def score_table(rows: Sequence[dict[str, Any]], *, n_boot: int = N_BOOT,
                seed: int = BOOTSTRAP_SEED,
                ledger_path: Path | str | None = None,
                mc_boot: int = MC_BOOT, mc_seed: int = MC_SEED,
                expected_cells: int | None = None) -> dict[str, Any]:
    """§3.4's table-side numbers, and §4.1's per-horizon deciding statistics.

    **The pooled ΔTRPS and pooled ΔwTRPS are WITHDRAWN** — not demoted
    to secondaries, withdrawn from the published outputs entirely (§4.1).
    `epl/simretro.py:41` and `epl/simmetrics.py:44` both freeze *"Never averaged
    across cutoffs"*: a forecast at the opener and one at matchweek 19 answer
    different questions and their average describes neither. Publishing an
    aggregate that protected code forbids as a verdict invites it to be quoted
    as one. What publishes in its place is every cell's ΔTRPS and ΔwTRPS
    individually, and the four treated-cell label means.

    What decides is (iv-a) the MW6 mean over its seven cells with §5.3's frozen
    season-block interval, (iv-b) the treated-cell means at MW0, MW3 and MW10,
    and (iv-c) the significance-and-precision clause. Everything else here is a
    SECONDARY and decides nothing.

    TRPS IS PROPER FOR THE DISPLAYED MARGINALS ONLY — `epl/simmetrics.py` says so
    in its own docstring. Two forecasts with the same position matrix and a
    different correlation structure score identically; widening changes the joint
    too, and no table metric here can see that. Disclosed, not solved.
    """
    assert_not_overridable(n_boot=(n_boot, N_BOOT), seed=(seed, BOOTSTRAP_SEED),
                           mc_boot=(mc_boot, MC_BOOT),
                           mc_seed=(mc_seed, MC_SEED))
    # v3 §8.6 consequence 6, NB7. There is **no `tallies=` and no `mc=`**, at
    # any target. The guard that used to stand over them was keyed to
    # `ledger_path`, so a caller who pointed at a scratch ledger while supplying
    # REAL deciding evidence was permitted — "the alternative evidence path
    # remains". §5's estimator and §5.4's unanimity rule are COMPUTED here from
    # the rebound tally files and from nothing else, which is what makes §8.7's
    # rebinding load-bearing rather than optional.
    if not rows:
        raise MergeIncomplete("no table cells to score")
    if expected_cells is not None and len(rows) != int(expected_cells):
        raise MergeIncomplete(
            f"{len(rows)} table cells, not the pre-stated {expected_cells}. §10 "
            "makes dropping a cell after the run starts an invalidation.")
    # The EXACT thirty-two (adjudication F6, V3-B1: "gate/bootstrap/unanimity
    # accept wrong populations"). This is the choke point for all three: NB7
    # closed `tallies=` and `mc=`, so §5's estimator and §5.4's unanimity rule
    # are computed HERE, from these rows and from nothing else, and the label
    # populations `table_gate` reads are these rows' own.
    assert_table_census(rows)

    per_cell = []
    for row in rows:
        control, treatment = row["arms"]["control"], row["arms"]["treatment"]
        per_cell.append({
            "key": cell_key(row),
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
            "provisional_control": list(row.get("provisional_control") or ()),
            "provisional_treatment": list(row.get("provisional_treatment") or ()),
            "sampler_digest_control": control.get("sampler_digest"),
            "sampler_digest_treatment": treatment.get("sampler_digest"),
            "substantive_digest_control": control.get("substantive_digest"),
            "substantive_digest_treatment": treatment.get("substantive_digest"),
            "parity_digest_simretro": row.get("parity_digest_simretro"),
            "realised_hash": row.get("realised_hash"),
            "coverage_control": dict(control.get("coverage") or {}),
            "coverage_treatment": dict(treatment.get("coverage") or {}),
            "coverage_treated_control": dict(control.get("coverage_treated") or {}),
            "coverage_treated_treatment":
                dict(treatment.get("coverage_treated") or {}),
        })

    deltas = np.array([c["delta_trps"] for c in per_cell], dtype=float)
    wdeltas = np.array([c["delta_wtrps"] for c in per_cell], dtype=float)
    by_row = {cell_key(r): r for r in rows}

    # ---- (iv-a) the named horizon, MW6 -----------------------------------
    mw6_idx = [i for i, c in enumerate(per_cell)
               if c["cutoff_label"] == MW6_LABEL]
    mw6_deltas = deltas[mw6_idx]
    mw6_seasons = [per_cell[i]["season"] for i in mw6_idx]
    if mw6_deltas.size:
        lo, hi, n_blocks = score_mod.block_bootstrap_ci(
            mw6_deltas, mw6_seasons, n_boot=n_boot, alpha=ALPHA, seed=seed)
    else:
        lo, hi, n_blocks = 0.0, 0.0, 0
    mw6 = {
        "cutoff_label": MW6_LABEL, "n": len(mw6_idx),
        "mean": float(mw6_deltas.mean()) if mw6_deltas.size else 0.0,
        "ci95": [float(lo), float(hi)], "n_blocks": int(n_blocks),
        "bootstrap": {"function": "epl.score.block_bootstrap_ci",
                      "blocks": "the seven season strings, one cell per block",
                      "B": int(n_boot), "alpha": ALPHA, "seed": int(seed),
                      "quantile": "np.quantile(means, [alpha/2, 1 - alpha/2]), "
                                  "NumPy's default linear interpolation"},
        "per_cell": [per_cell[i] for i in mw6_idx],
    }

    # ---- (iv-b) the per-horizon point gates, treated cells only ----------
    label_means: dict[str, dict[str, Any]] = {}
    for label in POINT_GATE_LABELS:
        idx = [i for i, c in enumerate(per_cell)
               if c["cutoff_label"] == label and c["treated_clubs"]]
        label_means[label] = {
            "cutoff_label": label, "n_treated": len(idx),
            "mean": float(deltas[idx].mean()) if idx else 0.0,
            "cells": [per_cell[i]["key"] for i in idx],
            "interval": "none — §4.1 computes no interval at these labels and "
                        "requires none; two cells do not carry one",
        }

    structural = {
        "cutoff_label": STRUCTURAL_ZERO_LABEL,
        "n": sum(1 for c in per_cell
                 if c["cutoff_label"] == STRUCTURAL_ZERO_LABEL),
        "n_treated": sum(1 for c in per_cell
                         if c["cutoff_label"] == STRUCTURAL_ZERO_LABEL
                         and c["treated_clubs"]),
        "structural_zero": True, "decides": "nothing",
    }

    # ---- §5.2's paired Monte-Carlo error, over the 15 deciding cells ------
    deciding = [c for c in per_cell if c["treated_clubs"]]
    payload = []
    for c in deciding:
        row = by_row[c["key"]]
        if ledger_path is None:
            raise TableMCImprecise(
                f"{c['key']}: no ledger path was given to load the "
                "per-particle tallies from, and there is no way to supply "
                "them. Gate (iv) may not be evaluated without §5's paired "
                "error: §10 makes an MC estimator that is not the "
                "jointly-resampled tie-aware one an invalidation.")
        arms = load_tallies(ledger_path, row)
        positions, spans = _cell_positions(row)
        payload.append({"key": c["key"], "season": c["season"],
                        "cutoff_label": c["cutoff_label"],
                        "positions": positions, "spans": spans,
                        "control": arms["control"],
                        "treatment": arms["treatment"]})
    mc = paired_mc_bootstrap(payload, n_boot=mc_boot, seed=mc_seed)
    # §5.4's P5, computed HERE because it needs the same 30 tallies and the
    # point-estimate verdict of iv-c that this function has just derived.
    mc["unanimity"] = unanimity(
        payload,
        point_verdict=bool(mw6["mean"] > 0.0 and mw6["ci95"][0] > 0.0),
        n_boot=n_boot, boot_seed=seed)
    for c in per_cell:
        c["mc_se_paired"] = mc["mc_se_per_cell"].get(c["key"])

    by_label: list[dict[str, Any]] = []
    for label in sorted({c["cutoff_label"] for c in per_cell}):
        idx = [i for i, c in enumerate(per_cell) if c["cutoff_label"] == label]
        treated_idx = [i for i in idx if per_cell[i]["treated_clubs"]]
        by_label.append({
            "cutoff_label": label, "n": len(idx), "n_treated": len(treated_idx),
            "mean_delta_trps_treated": (float(deltas[treated_idx].mean())
                                        if treated_idx else 0.0),
            "mean_delta_wtrps_treated": (float(wdeltas[treated_idx].mean())
                                         if treated_idx else 0.0),
            "decides": ("gate (iv-a)" if label == MW6_LABEL else
                        "gate (iv-b)" if label in POINT_GATE_LABELS
                        else "nothing")})

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
        #: §4.1: the pooled ΔTRPS and ΔwTRPS are WITHDRAWN from the
        #: published outputs entirely, not demoted. Protected code freezes
        #: "Never averaged across cutoffs", and publishing an aggregate that
        #: protected code forbids as a verdict invites it to be quoted as one.
        "withdrawn": {
            "pooled_delta_trps":
                "withdrawn by §4.1 — epl/simretro.py:41 and "
                "epl/simmetrics.py:44 both freeze 'Never averaged across "
                "cutoffs'; 17 of 32 cells are structural zeros and all seven "
                "MW19 cells are among them, so the average diluted harm at the "
                "horizons where the treatment fires",
            "pooled_delta_wtrps": "withdrawn by §4.1, same reason"},
        "mw6": mw6, "per_label": label_means, "mw19": structural,
        "mc": mc,
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
    """§4.1 (iv) as §4.1 repairs it — per horizon, and nothing on an average.

    > **(iv-a) The named-horizon gate — MW6.** The equal-weight mean over the
    > seven MW6 cells of ΔTRPS must be ≤ +0.0002.
    >
    > **(iv-b) The per-horizon point gates.** At each of MW0, MW3 and MW10, the
    > equal-weight mean over THAT LABEL'S TREATED CELLS ONLY must be ≤ +0.0002.
    > No interval is computed at these labels and none is required; two cells do
    > not carry one. MW19 holds zero treated cells, is a structural zero by
    > construction, is reported as such, and decides nothing.
    >
    > **(iv-c) The significance-and-precision clause, at MW6 only.** The gate
    > FAILS if the MW6 mean is > 0 **and** the lower bound of §5.3's frozen
    > season-block interval is > 0.

    THE PRECISION RULE OF §5, at EVERY deciding boundary. Gate (iv) is
    UNRESOLVED — and ADOPT is refused — if any of (P1)–(P5) holds. Every one is
    one-directional: UNRESOLVED blocks adoption and can never grant one, so
    simulation noise is only ever able to REFUSE, which is the direction that
    cannot be gamed.

    (P4) and (P5) exist because (iv-c) is a FAILURE clause: noise that pushes
    the MW6 mean or its lower bound below zero converts a failure into a
    passage, and that is the one direction this document may not leave open.

    (P5) IS §5.4'S UNANIMITY RULE AND NOT A SCALE COMPARISON. The
    natural-looking guard — comparing ``|ci_lo_MW6 - 0|`` with
    ``2 x mc_se_mw6`` — is invalid, and demonstrably rather than stylistically:
    ``mc_se_mw6`` is the Monte-Carlo standard error of a LINEAR statistic while
    ``ci_lo_MW6`` is a NONLINEAR quantile of a season bootstrap over the same
    seven values, and cross-cell error proportional to ``(+h, -h, 0, ...)``
    leaves the former arbitrarily small while moving the latter across zero.
    §5.4 replaces it with the whole of iv-c recomputed on K = 200
    particle-resampled tally sets: it does not bound the endpoint by a scale
    that does not describe it, it PROPAGATES the Monte-Carlo uncertainty
    through the actual computation. The gate validates the run it is handed
    (:func:`unanimity_is_valid`) and treats an unverifiable one as unresolved.

    §4.3, reissued by §4.1: R1 has no pass rule (`reports/epl_sim_retro_v1_1.md`
    §10: *"Nothing, by itself"*), so both the tolerance and the significance
    construction are INVENTED, invented blind, in a place where the house had
    none. What is new is that they are invented for a SINGLE NAMED HORIZON
    rather than for an average protected code forbids, and that the simulation
    error of that horizon is a published, deciding-capable quantity.
    """
    # The EXACT thirty-two, on the gate's own object (adjudication F6). The gate
    # reads label populations off `scored`, and a `scored` describing any other
    # thirty-two cells would be gated as if it described these.
    assert_table_census(scored["per_cell"])
    mw6 = scored["mw6"]
    mc_se = dict(scored.get("mc", {}).get("mc_se_label") or {})
    mean_mw6 = float(mw6["mean"])
    lo_mw6, hi_mw6 = (float(v) for v in mw6["ci95"])
    se_mw6 = mc_se.get(MW6_LABEL)

    iv_a = {"cutoff_label": MW6_LABEL, "n": int(mw6["n"]), "mean": mean_mw6,
            "bar": TABLE_TOLERANCE, "PASS": bool(mean_mw6 <= TABLE_TOLERANCE)}
    iv_b = {}
    for label in POINT_GATE_LABELS:
        leg = scored["per_label"][label]
        iv_b[label] = {"n_treated": int(leg["n_treated"]),
                       "mean": float(leg["mean"]), "bar": TABLE_TOLERANCE,
                       "PASS": bool(float(leg["mean"]) <= TABLE_TOLERANCE)}
    resolvable_harm = bool(mean_mw6 > 0.0 and lo_mw6 > 0.0)
    iv_c = {"cutoff_label": MW6_LABEL, "mean": mean_mw6,
            "ci95_season": [lo_mw6, hi_mw6], "n_blocks": int(mw6["n_blocks"]),
            "significant_worsening": resolvable_harm,
            "PASS": bool(not resolvable_harm)}

    conditions: list[dict[str, Any]] = []

    def _cond(name: str, fired: bool | None, value: Any, rule: str) -> None:
        conditions.append({"condition": name, "value": value, "rule": rule,
                           "fired": fired})

    deciding_se = {MW6_LABEL: se_mw6,
                   **{lab: mc_se.get(lab) for lab in POINT_GATE_LABELS}}
    missing = [lab for lab, v in deciding_se.items() if v is None]
    worst_se = max((float(v) for v in deciding_se.values() if v is not None),
                   default=None)
    _cond("P1", (True if missing else bool(worst_se > MC_PRECISION_LIMIT)),
          {"mc_se_label": deciding_se, "limit": MC_PRECISION_LIMIT,
           "missing": missing},
          "any deciding MC SE > 0.25 x 0.0002 = 5e-5 (a missing one is treated "
          "as unresolved, never as small)")
    _cond("P2", (None if se_mw6 is None else
                 bool(abs(mean_mw6 - TABLE_TOLERANCE)
                      < MC_BOUNDARY_SIGMAS * float(se_mw6))),
          {"mean_MW6": mean_mw6, "mc_se_mw6": se_mw6},
          "|mean_MW6 - 0.0002| < 2 x mc_se_mw6")
    for label in POINT_GATE_LABELS:
        se = mc_se.get(label)
        _cond(f"P3.{label}",
              (None if se is None else
               bool(abs(float(iv_b[label]["mean"]) - TABLE_TOLERANCE)
                    < MC_BOUNDARY_SIGMAS * float(se))),
              {"mean": iv_b[label]["mean"], "mc_se": se},
              f"|mean_{label} - 0.0002| < 2 x mc_se_{label.lower()}")
    _cond("P4", (None if se_mw6 is None else
                 bool(abs(mean_mw6) < MC_BOUNDARY_SIGMAS * float(se_mw6))),
          {"mean_MW6": mean_mw6, "mc_se_mw6": se_mw6},
          "|mean_MW6 - 0| < 2 x mc_se_mw6 — iv-c's zero boundary on the mean")
    # (P5) — §5.4's UNANIMITY RULE, and not a scale comparison. v1 compared
    # |ci_lo_MW6| against 2 x mc_se_mw6; §5.4 shows that comparison is invalid:
    # mc_se_mw6 is the MC standard error of a LINEAR statistic while ci_lo_MW6
    # is a NONLINEAR quantile of a season bootstrap over the same seven values,
    # and cross-cell error proportional to (+h, -h, 0, ...) leaves the former
    # arbitrarily small while moving the latter across zero.
    unan = dict(scored.get("mc", {}).get("unanimity") or {})
    checked = unanimity_is_valid(unan, point_verdict=resolvable_harm)
    _cond("P5", (True if not checked["valid"] else bool(unan.get("fired"))),
          {"k": unan.get("k"), "seed": unan.get("seed"),
           "dissenting": unan.get("dissenting"),
           "point_verdict": unan.get("point_verdict"),
           "valid": bool(checked["valid"]), "why": checked["why"],
           "n_verdicts": checked["n_verdicts"]},
          "§5.4's unanimity rule: the WHOLE of iv-c recomputed on K = 200 "
          "particle-resampled tally sets at seed 20260828; P5 fires unless all "
          "200 verdicts agree with each other and with the point-estimate "
          "verdict. One dissenting k is enough. An absent unanimity run is "
          "unresolved rather than small, and so is one that cannot be verified "
          "against the frozen K, the frozen seed, 200 recorded verdicts, its "
          "own dissent count and this gate's own iv-c point verdict.")

    fired = [c["condition"] for c in conditions if c["fired"]]
    resolved = not fired
    gates_pass = bool(iv_a["PASS"] and all(v["PASS"] for v in iv_b.values())
                      and iv_c["PASS"])
    verdict = ("PASS" if resolved and gates_pass else
               "UNRESOLVED" if not resolved else "FAIL")
    return {
        # An UNRESOLVED gate blocks adoption and can never grant one, so it
        # reaches `adoption` as a False that names itself.
        "PASS": bool(verdict == "PASS"),
        "verdict": verdict, "resolved": bool(resolved),
        "iv_a": iv_a, "iv_b": iv_b, "iv_c": iv_c,
        "mw19": scored["mw19"],
        "tolerance": TABLE_TOLERANCE,
        "n_cells": int(scored["n_cells"]),
        "n_treated_cells": int(scored["n_treated_cells"]),
        "precision": {
            "mc_boot": int(scored.get("mc", {}).get("mc_boot", MC_BOOT)),
            "mc_seed": int(scored.get("mc", {}).get("mc_seed", MC_SEED)),
            "n_particles": scored.get("mc", {}).get("n_particles"),
            "sims_per_particle": scored.get("mc", {}).get("sims_per_particle"),
            "mc_se_mw6": se_mw6,
            "mc_se_mw0": mc_se.get("MW0"), "mc_se_mw3": mc_se.get("MW3"),
            "mc_se_mw10": mc_se.get("MW10"),
            "mc_se_per_cell": dict(
                scored.get("mc", {}).get("mc_se_per_cell") or {}),
            # §5.4's named precision fields, and the three the unanimity rule
            # adds: "the precision object also carries mc_boot, mc_seed,
            # unanimity_k, unanimity_seed, unanimity_dissenting, ..."
            "unanimity_k": unan.get("k", UNANIMITY_K),
            "unanimity_seed": unan.get("seed", UNANIMITY_SEED),
            "unanimity_dissenting": unan.get("dissenting"),
            "conditions": conditions, "fired": fired, "resolved": bool(resolved),
            "rule": "§5.4 (P1)-(P5). The structural conditions of §5.2 raise "
                    "TableMCImprecise and stop the leg rather than publishing "
                    "an UNRESOLVED verdict, so this list carries SEVEN entries "
                    "and only seven — P1, P2, P3.MW0, P3.MW3, P3.MW10, P4, P5 "
                    "— and there is no P6 and there must not be one: a "
                    "structural refusal that stops the leg cannot also be a row "
                    "in a file the stopped leg never writes",
        },
        "withdrawn": "the pooled ΔTRPS over the 32 cells decides nothing and "
                     "is not published at all (§4.1)",
        "disclosure": ("§4.3 as §4.1 reissues it: both the tolerance and the "
                       "significance construction are invented — R1 has no pass "
                       "rule — from R1's own recorded per-cell scale, blind, in "
                       "a place where the house had none. They are now invented "
                       "for a single named horizon rather than for an average "
                       "protected code forbids, and the simulation error of "
                       "that horizon is published and deciding-capable. A "
                       "seven-block percentile bootstrap has poor coverage and "
                       "is not claimed to have good coverage."),
    }


# ==========================================================================
# 15. THE EVIDENCE CONTRACT — §9, regardless of outcome
# ==========================================================================

#: §9's per-fixture columns, frozen field by field. `block` and `season` are
#: columns because both bootstraps need them, and the corpus's own probabilities
#: sit beside Arm B's so a reader can confirm the eight-decimal equality rather
#: than take it (§2.3).
_PER_FIXTURE_COLUMNS = (
    "key", "match_id", "season", "block", "cutoff", "date",
    "home_key", "away_key", "e_home", "e_away", "e_min", "thin_at",
    "treated", "incumbent_widened",
    "p_home_B", "p_draw_B", "p_away_B",
    "p_home_A", "p_draw_A", "p_away_A",
    "p_home_corpus", "p_draw_corpus", "p_away_corpus",
    "y", "rps_B", "rps_A", "delta", "delta_vs_corpus",
    "max_abs_dp_vs_corpus")

#: §9's table-cell columns, one row per CELL (35, not 70): the paired shape
#: the deltas actually have. §9.3 adds the sampler digests and the two
#: provisional sets, and `mc_se_paired` is §5's per-cell `mc_se_cell`.
_TABLE_COLUMNS = (
    "season", "cutoff_label", "cutoff", "treated_clubs", "n_treated_clubs",
    "trps_control", "trps_treatment", "delta_trps",
    "wtrps_control", "wtrps_treatment", "delta_wtrps",
    "mc_se_paired", "identical",
    "sampler_digest_control", "sampler_digest_treatment",
    "substantive_digest_control", "substantive_digest_treatment",
    "parity_digest_simretro",
    "provisional_control", "provisional_treatment",
    "effective_posterior_control", "effective_posterior_treatment",
    "tally_sha256",
    "cov50_control", "cov90_control", "cov50_treatment", "cov90_treatment",
    "cov50_treated_control", "cov90_treated_control",
    "cov50_treated_treatment", "cov90_treated_treatment",
    "realised_hash")

_GRID_COLUMNS = ("e_star", "n_thin", "n_treated", "mean_delta", "ci_lo",
                 "ci_hi", "n_blocks", "degenerate", "decides")

#: §9.3's MANIFEST membership, frozen as an exact list of **FIFTY-TWO** paths.
#: "The list is decidable from this document: the count is 52, the shard count
#: is fixed at 4, the tally naming function is literal and its 35 members are
#: the product of two enumerated sets, and the five markers are named
#: individually. 'Bulky local artifacts' is not a category here; it is a list."
#:
#: v1's list was ELEVEN and substantively incomplete: the 35 deciding tally
#: sidecars, `parity.jsonl` and the five sequence markers were all absent, so a
#: swapped tally changed no manifested digest and a missing marker left no
#: trace. Files 5-52 are not committed — what is committed is their digest AND
#: BYTE SIZE, which is the point of the manifest.
TALLY_SEASONS: tuple[str, ...] = ("2019-20", "2020-21", "2021-22", "2022-23",
                                  "2023-24", "2024-25", "2025-26")
TALLY_LABELS: tuple[str, ...] = ("MW0", "MW3", "MW6", "MW10", "MW19")

MANIFEST_PATHS: tuple[str, ...] = (
    "reports/evidence/widening.json",
    "reports/evidence/widening_per_fixture.csv",
    "reports/evidence/widening_table_cells.csv",
    "reports/evidence/widening_grid_means.csv",
    *(f"data/epl/fit/evwiden/{shard_name(i, SHARDS)}" for i in range(SHARDS)),
    "data/epl/fit/evwiden.json",
    "data/epl/sim/evwiden/table_cells.jsonl",
    "data/epl/fit/evwiden/canary.json",
    "data/epl/sim/evwiden/parity.jsonl",
    *(f"data/epl/sim/evwiden/tallies/{season}|{label}.npz"
      for season in TALLY_SEASONS for label in TALLY_LABELS
      # §9.3: "exactly 32 [...] the product of two enumerated sets MINUS three
      # cells this document names by key". `TALLY_SEASONS` carries the season
      # string with `/` replaced by `-`, so the key is rebuilt to compare.
      if f"{season.replace('-', '/')}|{label}" not in EXCLUDED_CELLS),
    *(f"data/epl/fit/evwiden/sequence/{step}.json" for step in SEQUENCE_STEPS),
)

#: The namespace this experiment owns inside the SHARED manifest. §9.3 refuses
#: "an entry inside this experiment's namespace (`widening`, `evwiden`) outside
#: the 49"; `reports/evidence/MANIFEST.sha256` is a file two earlier experiments
#: already wrote, so the closure is scoped to the paths this experiment could
#: have written.
_MANIFEST_NAMESPACE = ("widening", "evwiden")


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
    """§9.2's 85 thin-fixture rows, projected from the ledger without loss.

    A reader holding this file and nothing else can recompute the estimand with
    arithmetic alone — average ``delta`` over the 85 — and both bootstrap
    intervals, which is why ``block`` and ``season`` are columns rather than
    something to be joined back from a parquet nobody committed.
    """
    out = []
    for row in sorted(rows, key=lambda r: (str(r["cutoff"]), str(r["match_id"]))):
        if float(row["e_min"]) >= float(e_star):
            continue
        corpus = [float(v) for v in row["probs_native"]]
        arm_b = [float(v) for v in row["probs_incumbent"]]
        arm_a = [float(v) for v in row["probs_arm"]]
        out.append({
            "key": row["key"], "match_id": row["match_id"],
            "season": row["season"], "block": row["block"],
            "cutoff": row["cutoff"], "date": row["date"],
            "home_key": row["home_key"], "away_key": row["away_key"],
            "e_home": row["e_home"], "e_away": row["e_away"],
            "e_min": row["e_min"],
            "thin_at": ";".join(row["thin_at"]),
            "treated": bool(row["treated"]),
            "incumbent_widened": bool(row["incumbent_widened"]),
            "p_home_B": arm_b[0], "p_draw_B": arm_b[1], "p_away_B": arm_b[2],
            "p_home_A": arm_a[0], "p_draw_A": arm_a[1], "p_away_A": arm_a[2],
            "p_home_corpus": corpus[0], "p_draw_corpus": corpus[1],
            "p_away_corpus": corpus[2],
            "y": int(row["y"]), "rps_B": float(row["rps_B"]),
            "rps_A": float(row["rps_arm"]), "delta": float(row["delta"]),
            "delta_vs_corpus": float(row["delta_vs_corpus"]),
            "max_abs_dp_vs_corpus": float(row["max_abs_dp_vs_corpus"]),
        })
    return out


def table_evidence(rows: Sequence[dict[str, Any]],
                   mc_se: dict[str, Any] | None = None,
                   ) -> list[dict[str, Any]]:
    """§9's 35 table-cell rows — one per CELL, the shape the deltas have."""
    mc_se = dict(mc_se or {})
    out = []
    for row in sorted(rows, key=lambda r: (str(r["season"]), str(r["cutoff"]))):
        control, treatment = row["arms"]["control"], row["arms"]["treatment"]

        def cov(leg, key, club=None):
            if club is None:
                return (leg.get("coverage") or {}).get(key)
            per = (leg.get("coverage_treated") or {})
            values = [v.get(key) for v in per.values() if v.get(key) is not None]
            return float(np.mean(values)) if values else None

        out.append({
            "season": row["season"], "cutoff_label": row["cutoff_label"],
            "cutoff": row["cutoff"],
            "treated_clubs": ";".join(row["treated_clubs"]),
            "n_treated_clubs": len(row["treated_clubs"]),
            "trps_control": float(control["trps"]),
            "trps_treatment": float(treatment["trps"]),
            "delta_trps": float(treatment["trps"]) - float(control["trps"]),
            "wtrps_control": float(control["wtrps"]),
            "wtrps_treatment": float(treatment["wtrps"]),
            "delta_wtrps": float(treatment["wtrps"]) - float(control["wtrps"]),
            "mc_se_paired": mc_se.get(cell_key(row)),
            "identical": bool(row["identical"]),
            "sampler_digest_control": control.get("sampler_digest"),
            "sampler_digest_treatment": treatment.get("sampler_digest"),
            "substantive_digest_control": control.get("substantive_digest"),
            "substantive_digest_treatment": treatment.get("substantive_digest"),
            "parity_digest_simretro": row.get("parity_digest_simretro"),
            "provisional_control": ";".join(row.get("provisional_control") or ()),
            "provisional_treatment":
                ";".join(row.get("provisional_treatment") or ()),
            # §3.3: `effective_posterior_hash` left the substantive digest and
            # "becomes a separately-recorded and separately-compared provenance
            # field on every table row".
            "effective_posterior_control":
                control.get("effective_posterior_hash"),
            "effective_posterior_treatment":
                treatment.get("effective_posterior_hash"),
            "tally_sha256": row.get("tally_sha256"),
            "cov50_control": cov(control, "coverage50"),
            "cov90_control": cov(control, "coverage90"),
            "cov50_treatment": cov(treatment, "coverage50"),
            "cov90_treatment": cov(treatment, "coverage90"),
            "cov50_treated_control": cov(control, "coverage50", club=True),
            "cov90_treated_control": cov(control, "coverage90", club=True),
            "cov50_treated_treatment": cov(treatment, "coverage50", club=True),
            "cov90_treated_treatment": cov(treatment, "coverage90", club=True),
            "realised_hash": row.get("realised_hash"),
        })
    return out


def grid_evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    """§9's grid file: `e_star, n_thin, n_treated, mean_delta, ci_lo, ci_hi,
    n_blocks, degenerate, decides`."""
    return [{
        "e_star": g["e_star"], "n_thin": g["population"],
        "n_treated": g["treated"],
        "mean_delta": g["mean"],
        "ci_lo": g["ci95"][0], "ci_hi": g["ci95"][1],
        "n_blocks": g["n_blocks"],
        "degenerate": bool(g["degenerate_by_construction"]),
        "decides": "nothing",
    } for g in result["secondaries"]["grid"]]


def realised_power_object(result: dict[str, Any], *,
                          structure: dict[str, Any] | None = None
                          ) -> dict[str, Any] | None:
    """§6.5's obligation on ``widening.json``'s ``power.realised``.

    The harness's ``estimand`` records the realised paired SD, which is cheap;
    the joint-gate MDE at that SD is a 2,000-replicate simulation and is
    computed **here**, where the evidence file is assembled, because §6.5 places
    the obligation "on the **result document and on
    `reports/evidence/widening.json`'s `power.realised` object**, not on the
    pre-run harness, because the realised SD does not exist until the fits do".

    The two-sided quantity stays beside it under its own name, labelled as the
    thing gate (i) is not.
    """
    realised = dict((result.get("power") or {}).get("realised") or {})
    if not realised:
        return None
    sd = realised.get("sd_paired_treated")
    if sd is None:
        realised["joint_mde"] = {
            "computed": False,
            "why": "no treated delta carried a paired SD, so there is no "
                   "realised value to re-run §6.2 at"}
        return realised
    joint = realised_power(float(sd), structure=structure)
    realised["joint_mde"] = {
        "computed": True, "sd": float(sd),
        "replicates": joint["replicates"],
        "simulation_seed": joint["simulation_seed"],
        "bootstrap": joint["bootstrap"], "grid": joint["grid"],
        "bar": joint["bar"],
        "rows": [{k: r.get(k) for k in
                  ("scenario", "sd", "rho", "power_at_bar", "mde_treated",
                   "mde_estimand", "ratio_to_bar", "power_at_2x_bar",
                   "exhausted", "note")}
                 for r in joint["rows"]],
        "definition": joint["definition"],
        "structural_fact": joint["structural_fact"],
        "decides": "nothing — §6.5: the realised numbers decide nothing and no "
                   "threshold moves in response. They exist so the reader can "
                   "size the null §6.3's warning pre-announces.",
    }
    return realised


def evidence_object(result: dict[str, Any], *,
                    power: dict[str, Any] | None = None) -> dict[str, Any]:
    """§9's `reports/evidence/widening.json`, frozen field by field.

    The superseded contract said "both CIs" where there are **three** deciding
    intervals, left the 820-fixture control without a committed home, promised
    Sunderland and coverage diagnostics no column held, and froze no MANIFEST
    membership. Every name below is the document's own, and §5.4's `precision`
    object carries the standard errors under their own names.
    """
    table = result.get("table") or {}
    scored = table.get("scored") or {}
    gate = table.get("gate") or {}
    secondaries = result.get("secondaries") or {}
    adoption_ = result.get("adoption") or {}
    conditions = adoption_.get("conditions") or {}
    control = result.get("identity_control") or {}
    mw6 = scored.get("mw6") or {}
    boot = result.get("bootstrap") or {}

    def _ci(values, n_blocks, *, blocks: str):
        lo, hi = ((float(values[0]), float(values[1])) if values else (None, None))
        return {"function": "epl.score.block_bootstrap_ci", "blocks": blocks,
                "n_blocks": (int(n_blocks) if n_blocks is not None else None),
                "B": int(boot.get("n_boot", N_BOOT)),
                "alpha": float(boot.get("alpha", ALPHA)),
                "seed": int(boot.get("seed", BOOTSTRAP_SEED)),
                "lo": lo, "hi": hi}

    out: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "prereg_commit": git_commit_touching(paths.rel(PREREG_PATH)),
        "prereg_blob": git_blob_id(paths.rel(PREREG_PATH)),
        # §9.1 names `prereg_commit` and `prereg_blob`; the document they
        # identify is v2, and v1 is lineage that decides nothing (§8.1).
        "prereg": paths.rel(PREREG_PATH),
        "pins": {
            "corpus_sha256": CORPUS_SHA256, "corpus_rows": CORPUS_ROWS,
            "corpus_seasons": list(CORPUS_SEASONS),
            "archive_sha256": ARCHIVE_SHA256, "archive_rows": ARCHIVE_ROWS,
            "ledger_sha256": WALK_LEDGER_SHA256, "ledger_rows": WALK_LEDGER_ROWS,
            "config_sha256": CONFIG_SHA256,
            "realised_config_sha256": REALISED_CONFIG_SHA256,
            "seed": SEED, "widening": dict(FROZEN_WIDENING),
            "e_star": E_STAR, "shards": SHARDS,
            # §9.1 / §0.1: the census record is a PIN, because v3's table leg
            # is SCOPED by it (§0.6) and `data/` is gitignored. The verdict
            # file carries the digest and the 32 keys so a reader can check the
            # scope against the freeze block rather than against a local file.
            "feasibility_sha256": FEASIBILITY_SHA256,
            "feasibility_bytes": FEASIBILITY_BYTES,
            "feasibility_priceable": _v3_priceable_keys(),
            "feasibility_unpriceable": {
                k: dict(EXCLUDED_CELL_DETAIL[k]) for k in EXCLUDED_CELLS}},
        "estimand": {"n": result.get("n"), "mean": result.get("mean"),
                     "sd": result.get("sd"), "se_iid": result.get("se_iid"),
                     "definition": result.get("estimand")},
        "ci_week": _ci(result.get("ci95"), result.get("n_blocks"),
                       blocks="the corpus's own (season, ISO week) labels"),
        "ci_season": _ci(result.get("ci95_season"),
                         result.get("n_season_blocks"), blocks="the 6 seasons"),
        "ci_table_mw6": _ci(mw6.get("ci95"), mw6.get("n_blocks") or None,
                            blocks="the seven season strings, one MW6 cell per "
                                   "block"),
        "gate_i": {"value": conditions.get("i_point_estimate", {}).get("value"),
                   "bar": ADOPT_DELTA,
                   "PASS": conditions.get("i_point_estimate", {}).get("PASS")},
        "gate_ii": {"value": conditions.get(
            "ii_block_ci_excludes_zero", {}).get("ci95"),
            "bar": "upper bound strictly < 0",
            "PASS": conditions.get("ii_block_ci_excludes_zero", {}).get("PASS")},
        "gate_iii": {"value": conditions.get(
            "iii_season_ci_excludes_zero", {}).get("ci95"),
            "bar": "upper bound strictly < 0",
            "PASS": conditions.get("iii_season_ci_excludes_zero", {}).get("PASS")},
        "gate_iv": {
            "mw6": {"n": mw6.get("n"), "mean": mw6.get("mean"),
                    "ci": mw6.get("ci95"),
                    "per_cell": [{k: c.get(k) for k in
                                  ("season", "cutoff_label", "delta_trps",
                                   "delta_wtrps", "mc_se_paired")}
                                 for c in (mw6.get("per_cell") or [])]},
            "per_label": {lab: {
                "n_treated": (scored.get("per_label", {}).get(lab, {})
                              .get("n_treated")),
                "mean": scored.get("per_label", {}).get(lab, {}).get("mean"),
                "PASS": gate.get("iv_b", {}).get(lab, {}).get("PASS")}
                for lab in POINT_GATE_LABELS},
            "mw19": scored.get("mw19") or {"structural_zero": True,
                                           "decides": "nothing"},
            "precision": gate.get("precision"),
            "PASS_or_UNRESOLVED": gate.get("verdict"),
            "withdrawn": scored.get("withdrawn")},
        "controls": {
            "identity": {"n": control.get("n_fixtures"),
                         "max_abs_diff": control.get("max_abs_diff"),
                         "mean_abs_diff": control.get("mean_abs_diff"),
                         "PASS": (None if control.get("max_abs_diff") is None
                                  else float(control["max_abs_diff"]) == 0.0)},
            # §9.1: MEASURED off the merged rows by `measured_controls`, never
            # written as `{n: 0, PASS: true}` constants. v1 hard-coded both, and
            # "a verdict file that always prints PASS for a control nobody
            # measured is exactly the shape this document's own 'a test that
            # cannot fail is not a test' objects to".
            "untreated_moved": (result.get("controls") or {}).get(
                "untreated_moved",
                {"n": None, "refusal": "UntreatedMoved", "PASS": None,
                 "why": "no merged rows were supplied to measure it from"}),
            "predicate_mismatch": (result.get("controls") or {}).get(
                "predicate_mismatch",
                {"n": None, "refusal": "PredicateMismatch", "PASS": None,
                 "why": "no merged rows were supplied to measure it from"}),
            "table_parity": {
                "n_cells": len(scored.get("per_cell") or []),
                # None only when the table leg has not run; False when a cell
                # carries no protected-runner digest, never "or None" — an
                # absent parity is a failure, not an unknown.
                "PASS": (None if not scored.get("per_cell") else
                         all(bool((c or {}).get("parity_digest_simretro"))
                             for c in scored["per_cell"])),
                "per_cell_digests": {
                    c["key"]: c.get("parity_digest_simretro")
                    for c in (scored.get("per_cell") or [])}},
        },
        "canaries": result.get("canaries"),
        # §9.1: "`sequence` — the five markers of §8.4, each with its recorded
        # freeze commit and completion time". A step that never ran says so;
        # v1 had no markers at all, so it had no field either.
        "sequence": sequence_report(),
        # §9.1: "`conformance` — §8.5's pytest artifact identity: path, SHA-256,
        # the eighteen test ids and the pass count, as the freeze block records
        # them." The verdict file names WHICH RUN certified the freeze the
        # numbers beside it were produced under, so a reader is not left to
        # take the block's word for a file the repository does not carry.
        "conformance": {k: v for k, v in conformance_artifact_status().items()
                        if k in ("path", "sha256", "test_ids", "count", "ok",
                                 "produced_at", "harness")},
        "grid": [{"e_star": g["e_star"], "n_thin": g["population"],
                  "n_treated": g["treated"], "mean": g["mean"],
                  "ci": g["ci95"], "degenerate":
                      bool(g["degenerate_by_construction"]),
                  "decides": "nothing"}
                 for g in (secondaries.get("grid") or [])],
        "strata": {k: [{**s, "decides": "nothing"} for s in v]
                   for k, v in (secondaries.get("strata") or {}).items()},
        "movement": secondaries.get("movement"),
        "coverage": {c["key"]: {
            "control": c.get("coverage_treated_control"),
            "treatment": c.get("coverage_treated_treatment")}
            for c in (scored.get("per_cell") or []) if c.get("treated_clubs")},
        "sunderland": scored.get("hull_analogue"),
        # §9.1: "`power` — §6's object: the frozen scenarios, structure, MDE
        # definition, R, both seeds, the six rows of §6.3, and `power.realised`
        # per §6.5" — which is the REALISED paired SD *and the joint-gate MDE
        # recomputed at it*, not the two-sided-test-against-zero MDE beside it.
        "power": ({**power, "realised": realised_power_object(result),
                   "reproduces": power_reproduces(power)}
                  if power is not None else result.get("power")),
        "materiality": {
            "pooled_corpus": (secondaries.get("full_population") or {}).get("mean"),
            "reseed_shift": RESEED_SCALE["pooled_shift"],
            "required_sentence": MATERIALITY_SENTENCE},
        "verdict": adoption_.get("verdict"),
        "which_gate_decided": [name for name, leg in conditions.items()
                               if isinstance(leg, dict)
                               and leg.get("PASS") is False],
        "secondaries_decide": "nothing",
    }
    return out


#: §4.2's required disclosure, in the result document, in these words.
MATERIALITY_SENTENCE = (
    "the rule's corpus-level effect is below this model's own re-seed noise, "
    "and its value is a claim about the fixtures it touches, not about the "
    "model's aggregate accuracy")


def manifest_entries(directory: Path | str | None = None,
                     table_ledger: Path | str | None = None,
                     ) -> dict[str, Path]:
    """§9.3's forty-nine paths, resolved. The list, not a category."""
    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    table_ledger = (Path(table_ledger) if table_ledger is not None
                    else TABLE_LEDGER)
    table_dir = table_ledger.parent
    out: dict[str, Path] = {}
    for rel in MANIFEST_PATHS:
        if rel.startswith("reports/evidence/"):
            out[rel] = EVIDENCE_DIR / Path(rel).name
        elif rel.endswith("table_cells.jsonl"):
            out[rel] = table_ledger
        elif rel == "data/epl/fit/evwiden.json":
            out[rel] = EVWIDEN_JSON
        elif rel.endswith("/parity.jsonl"):
            out[rel] = table_dir / PARITY_NAME
        elif "/tallies/" in rel:
            out[rel] = table_dir / "tallies" / Path(rel).name
        elif "/sequence/" in rel:
            out[rel] = SEQUENCE_DIR / Path(rel).name
        else:
            out[rel] = directory / Path(rel).name
    return out


def update_manifest(entries: dict[str, str], path: Path | str | None = None, *,
                    require: Sequence[str] | None = None) -> Path:
    """§9.3: the manifest's digests AND byte sizes, both validated.

    Existing lines are preserved in their existing order and updated in place;
    new ones are appended. The manifest is a shared file that two earlier
    experiments already wrote, and rewriting it from scratch would silently drop
    their entries — which is the opposite of what a manifest is for.

    §9.3: **a missing artifact is a refusal, never a silent omission.** Every
    path in ``require`` must exist; the superseded writer skipped what it could
    not find, which is how a "complete" manifest ends up describing ten files.
    """
    path = Path(path) if path is not None else EVIDENCE_MANIFEST
    absent = [rel for rel in (require or ())
              if not Path(entries.get(rel, "/nonexistent")).exists()]
    if absent:
        raise MergeIncomplete(
            f"the manifest is missing {len(absent)} promised artifact(s) "
            f"(first: {absent[:3]}). §9.3 freezes the membership as an exact "
            f"list of {len(MANIFEST_PATHS)} paths and refuses to skip a file it "
            "cannot find: a missing artifact is a refusal, never a silent "
            "omission.")
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


def read_manifest(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """`path -> {sha256, bytes}` for every line of the shared manifest."""
    path = Path(path) if path is not None else EVIDENCE_MANIFEST
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out[parts[1]] = {"sha256": parts[0],
                             "bytes": (int(parts[2]) if len(parts) > 2
                                       and parts[2].isdigit() else None)}
    return out


def assert_manifest_complete(path: Path | str | None = None, *,
                             entries: dict[str, Path] | None = None,
                             ) -> dict[str, Any]:
    """§9.3: exactly the 49, every digest AND BYTE SIZE agreeing, nothing else
    of ours.

    ``--verify`` refuses if any of the 49 is missing from the manifest, if any
    digest disagrees, **if any byte size disagrees**, if the manifest carries an
    entry inside this experiment's namespace outside the 49, or if a promised
    file is not on disk. v1 recorded the byte sizes and never compared them,
    which made half of every entry decoration.

    The namespace closure is scoped: ``reports/evidence/MANIFEST.sha256`` is a
    shared file two earlier experiments already wrote, and refusing THEIR
    entries would be refusing the manifest for doing its job.
    """
    path = Path(path) if path is not None else EVIDENCE_MANIFEST
    entries = manifest_entries() if entries is None else entries
    recorded = read_manifest(path)
    missing = [rel for rel in MANIFEST_PATHS if rel not in recorded]
    ours = [rel for rel in recorded
            if any(tag in rel for tag in _MANIFEST_NAMESPACE)]
    extra = sorted(set(ours) - set(MANIFEST_PATHS))
    disagree: list[str] = []
    wrong_size: list[str] = []
    absent: list[str] = []
    for rel in MANIFEST_PATHS:
        target = Path(entries.get(rel, "/nonexistent"))
        if not target.exists():
            absent.append(rel)
            continue
        if rel not in recorded:
            continue
        if recorded[rel]["sha256"] != sha256_file(target):
            disagree.append(rel)
        size = recorded[rel].get("bytes")
        if size is None or int(size) != int(target.stat().st_size):
            wrong_size.append(rel)
    out = {"path": paths.rel(path), "n_required": len(MANIFEST_PATHS),
           "missing": missing, "extra": extra, "disagree": disagree,
           "wrong_size": wrong_size, "absent_on_disk": absent,
           "PASS": not (missing or extra or disagree or wrong_size or absent)}
    if not out["PASS"]:
        raise MergeIncomplete(
            f"{paths.rel(path)} does not carry §9.3's {len(MANIFEST_PATHS)} "
            f"paths: {len(missing)} missing {missing[:3]}, {len(extra)} outside "
            f"the list {extra[:3]}, {len(disagree)} whose digest disagrees "
            f"{disagree[:3]}, {len(wrong_size)} whose recorded byte size "
            f"disagrees or is absent {wrong_size[:3]}, {len(absent)} promised "
            f"but absent on disk {absent[:3]}. §9.3: each entry carries a "
            "SHA-256 AND a byte size and both are VALIDATED, not merely "
            "recorded; 'Bulky local artifacts' is not a category here, it is a "
            "list, and a run that cannot produce one of them has not finished.")
    return out


def write_evidence(result: dict[str, Any],
                   rows: Sequence[dict[str, Any]] | None = None,
                   table_rows: Sequence[dict[str, Any]] | None = None, *,
                   directory: Path | str | None = None,
                   manifest: bool = True, power: dict[str, Any] | None = None,
                   require_manifest_complete: bool = True) -> dict[str, str]:
    """§9's evidence contract, written whichever way the numbers fell.

    ULTRA-REVIEW LESSON 1, applied from day one: the verdict's machine-readable
    basis is COMMITTED under `reports/evidence/`, not left in a gitignored
    `data/`. `reports/evidence/README.md` records why that directory exists —
    two experiments shipped verdicts whose every machine artifact sat where a
    reader could not check a single number.

    §4.4: there is no file drawer. This function is called on a miss exactly as
    it is called on a hit, including the two embarrassing cases §4.4 pre-names.

    **`manifest=False` and `require_manifest_complete=False` are SEAMS.** The
    review's P5-B7: "a public production surface can publish `widening.json`
    without the supposedly mandatory 52-member manifest". They survive because
    the synthetic audits of §8.2 publish into their own directories and have no
    manifest to complete — and §8.6's guard is what tells the two apart, at the
    target, exactly as it does for every other seam.
    """
    directory = Path(directory) if directory is not None else EVIDENCE_DIR
    if not manifest or not require_manifest_complete:
        # Keyed to the FILE this call would write and not to the directory
        # holding it (adjudication F12): `reports/evidence/` is shared with two
        # earlier experiments, so the closed target is `widening.json` itself.
        assert_seam_allowed(
            "write_evidence(manifest=, require_manifest_complete=)",
            target=directory / EVIDENCE_JSON.name,
            detail="publishing §9's evidence without §9.3's manifest")
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    json_path = directory / EVIDENCE_JSON.name
    published = (result if isinstance(result.get("estimand"), dict)
                 else evidence_object(result, power=power))
    json_path.write_text(json.dumps(published, indent=2, default=str) + "\n")
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
        mc_se = ((result.get("table") or {}).get("scored") or {}).get(
            "mc", {}).get("mc_se_per_cell")
        p = _write_csv(directory / EVIDENCE_TABLE_CELLS.name, _TABLE_COLUMNS,
                       table_evidence(table_rows, mc_se))
        written["widening_table_cells.csv"] = paths.rel(p)
    if manifest:
        # §9.3: exactly the 49 MANIFEST_PATHS, and a missing artifact is a
        # refusal. (The count was eleven when §9.3 was drafted and the comment
        # outlived it by forty-one paths.)
        entries = manifest_entries()
        for rel in ("reports/evidence/widening.json",
                    "reports/evidence/widening_per_fixture.csv",
                    "reports/evidence/widening_table_cells.csv",
                    "reports/evidence/widening_grid_means.csv"):
            entries[rel] = directory / Path(rel).name
        require = (MANIFEST_PATHS
                   if directory == EVIDENCE_DIR and require_manifest_complete
                   else None)
        p = update_manifest({k: str(v) for k, v in entries.items()},
                            directory / EVIDENCE_MANIFEST.name, require=require)
        written["MANIFEST.sha256"] = paths.rel(p)
    return written


def table_projection(scored: dict[str, Any],
                     gate: dict[str, Any]) -> dict[str, Any]:
    """What the merge carries as its ``table`` — **with ``per_cell`` intact**.

    §9.1: "**`scored.per_cell` is not stripped.** The top-level per-cell
    structure must survive into the JSON projection: it is what fills the
    required table-parity and coverage diagnostics, and removing it before
    projection empties fields this contract promises."

    v1's ``main`` built this dictionary inline as
    ``{k: v for k, v in scored.items() if k != "per_cell"}``, so
    ``controls.table_parity.per_cell_digests`` and ``coverage`` were published
    empty on every real run. It is a named function now so the omission cannot
    come back as an inline comprehension nobody reads.
    """
    return {"gate": gate, "scored": scored}


def verify(directory: Path | str | None = None, *, shards: int = SHARDS,
           evidence: Path | str | None = None,
           table_ledger: Path | str | None = None,
           n_boot: int = N_BOOT, seed: int = BOOTSTRAP_SEED,
           tolerance: float = 1e-12,
           check_manifest: bool | None = None) -> dict[str, Any]:
    """Re-derive the published headline from the COMMITTED evidence, and from
    the shard ledgers, and demand they agree.

    This is the check a reader of the repository can run. `widening.json` is a
    verdict somebody wrote down; `widening_per_fixture.csv` is the 85 rows it
    rests on. Averaging one column of the CSV must reproduce the JSON's mean to
    1e-12, and re-scoring the shard ledgers must reproduce it again — so the
    three ways of arriving at the number are three, and not one number copied
    twice.

    **And it re-derives the VERDICT, not only the headline** (§8.7, §9.3). v1's
    ``--verify`` "does not reproduce the table/MC/adoption decision": it
    averaged one CSV column and compared it with one JSON field, leaving gate
    (iv) — the half of the adoption rule that four hours of simulation paid for
    — unchecked. This one rebinds every tally to its recorded digest, re-runs
    §5's estimator and §5.4's unanimity rule, recomputes the table gate, and
    refuses if the recomputed verdict, the recomputed standard errors or the
    recomputed precision conditions differ from the published ones. **A
    verification that re-reads a JSON file it does not re-derive verifies
    nothing.**

    It fits nothing, simulates nothing and writes nothing.
    """
    assert_not_overridable(n_boot=(n_boot, N_BOOT), seed=(seed, BOOTSTRAP_SEED))
    evidence = Path(evidence) if evidence is not None else EVIDENCE_JSON
    if check_manifest is not None:
        # §9.3's manifest validation is derived from WHERE the evidence is, and
        # a caller who could turn it off at the preregistered directory could
        # verify the published evidence without it.
        assert_seam_allowed("verify(check_manifest=)", target=evidence.parent,
                            detail="§9.3's MANIFEST validation, turned off by "
                                   "a caller rather than derived")
    # The shard closure binds the PREREGISTERED verification — the one that
    # reads reports/evidence/. A synthetic audit verifying its own scratch
    # evidence is §8.2's business and has whatever shards it made.
    if evidence.parent.resolve() == EVIDENCE_DIR.resolve():
        assert_not_overridable(shards=(int(shards), SHARDS))
    if not evidence.exists():
        raise MergeIncomplete(
            f"{paths.rel(evidence)} is not on disk: there is no published "
            "verdict to verify. §9's evidence contract is written by the merge "
            "regardless of outcome, so an absent file is a run that never "
            "finished rather than a result that went the wrong way.")
    published = json.loads(evidence.read_text())
    estimand_block = published.get("estimand")
    headline = (dict(estimand_block) if isinstance(estimand_block, dict)
                else dict(published))

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

    # ---- §8.7: the table gate, RE-DERIVED from the rebound tallies --------
    table_ledger_path = (Path(table_ledger) if table_ledger is not None
                         else TABLE_LEDGER)
    table_check: dict[str, Any] = {
        "checked": False, "path": paths.rel(table_ledger_path),
        "why": "the table ledger is not on disk"}
    if table_ledger_path.exists():
        cell_rows = load_table_ledger(table_ledger_path)
        # `load_tallies` inside `score_table` rebinds each file to the digest
        # its row recorded and re-runs §5.1's binding checks; `unanimity`
        # re-derives the whole of iv-c 200 times. Nothing here is read off the
        # published JSON.
        rescored = score_table(cell_rows, ledger_path=table_ledger_path)
        regate = table_gate(rescored)
        was = (published.get("gate_iv") or {})
        want_precision = dict(was.get("precision") or {})
        got_precision = dict(regate["precision"])
        differs = []
        # ---- F15 (I6): NO CONDITIONAL SKIPS ------------------------------
        # §9's contract is that "every missing or disagreeing published value
        # refuses", and the review found this loop weaker than that text: the SE
        # comparisons, the fired set and the dissent count each switched
        # themselves OFF when the published side was absent, so a publisher
        # could pass this verification by publishing less. Every field this
        # function is DEFINED to re-derive is listed once, here, and a field
        # that is absent from the published evidence is a refusal in exactly the
        # way a field that disagrees is. What it genuinely cannot check — the
        # adoption verdict with no shard ledgers on disk — is NAMED in the
        # report rather than silently dropped.
        checked_fields: list[str] = []
        unchecked_fields: list[dict[str, str]] = []

        # A published verdict this evidence does not carry is not a verdict
        # that agreed: §8.7 asks `--verify` to re-derive the decision, and a
        # missing field is a decision nobody can check.
        if not was:
            differs.append(
                "the published evidence carries no `gate_iv` block while a "
                "table ledger exists — there is no published verdict to "
                "re-derive against")
        else:
            checked_fields.append("gate_iv.PASS_or_UNRESOLVED")
            if "PASS_or_UNRESOLVED" not in was:
                differs.append(
                    "gate_iv.PASS_or_UNRESOLVED is ABSENT from the published "
                    f"evidence and re-derives to {regate['verdict']!r}")
            elif was.get("PASS_or_UNRESOLVED") != regate["verdict"]:
                differs.append(
                    f"verdict {was.get('PASS_or_UNRESOLVED')!r} != "
                    f"{regate['verdict']!r}")
            if "precision" not in was:
                differs.append(
                    "gate_iv.precision is ABSENT from the published evidence, "
                    "so §5's precision conditions and standard errors have "
                    "nothing to be re-derived against")
        for field in ("mc_se_mw6", "mc_se_mw0", "mc_se_mw3", "mc_se_mw10"):
            if not was:
                continue
            checked_fields.append(f"gate_iv.precision.{field}")
            a, b = want_precision.get(field), got_precision.get(field)
            if field not in want_precision:
                differs.append(f"{field} is ABSENT from the published "
                               f"evidence and re-derives to {b!r}")
            elif (a is None) != (b is None):
                differs.append(f"{field} {a!r} != {b!r}")
            elif a is not None and b is not None and \
                    abs(float(a) - float(b)) > float(tolerance):
                differs.append(f"{field} {a} != {b}")
        fired_then = set(want_precision.get("fired") or ())
        fired_now = set(got_precision.get("fired") or ())
        if was:
            checked_fields.append("gate_iv.precision.fired")
            if "fired" not in want_precision:
                differs.append("fired is ABSENT from the published evidence "
                               f"and re-derives to {sorted(fired_now)}")
            elif fired_then != fired_now:
                differs.append(f"precision conditions {sorted(fired_then)} != "
                               f"{sorted(fired_now)}")
            # §5.4's dissent count is REPORTED by the published object and BOUND
            # here: an unanimity run whose dissent count moved is a different
            # run, and one that omits the count is a run nobody can check.
            checked_fields.append("gate_iv.precision.unanimity_dissenting")
            if "unanimity_dissenting" not in want_precision:
                differs.append(
                    "unanimity_dissenting is ABSENT from the published evidence "
                    f"and re-derives to "
                    f"{got_precision.get('unanimity_dissenting')!r}")
            elif want_precision.get("unanimity_dissenting") != \
                    got_precision.get("unanimity_dissenting"):
                differs.append(
                    f"unanimity dissent "
                    f"{want_precision.get('unanimity_dissenting')!r} != "
                    f"{got_precision.get('unanimity_dissenting')!r}")
        # §9.3: "`--verify` also re-derives the verdict". The ADOPTION decision
        # is recomputed from the re-derived gate and the ledger's own estimand
        # rather than echoed out of the JSON.
        readoption = None
        if from_ledger.get("present"):
            checked_fields.append("verdict")
            readoption = adoption(float(scored["mean"]), scored["ci95"],
                                  scored["ci95_season"], table=regate)
            if "verdict" not in published:
                differs.append(
                    "the published adoption verdict is ABSENT and re-derives "
                    f"to {readoption['verdict']!r}")
            elif published.get("verdict") != readoption["verdict"]:
                differs.append(f"adoption verdict "
                               f"{published.get('verdict')!r} != "
                               f"{readoption['verdict']!r}")
        else:
            unchecked_fields.append({
                "field": "verdict",
                "why": ("the shard ledgers are not on disk, so §4.1's adoption "
                        "rule has no re-derived estimand to be evaluated "
                        "against")})
        table_check = {
            "checked": True, "path": paths.rel(table_ledger_path),
            "n_cells": int(rescored["n_cells"]),
            "checked_fields": checked_fields,
            "unchecked_fields": unchecked_fields,
            "recomputed": {"verdict": regate["verdict"],
                           "mc_se_mw6": got_precision.get("mc_se_mw6"),
                           "fired": sorted(fired_now),
                           "unanimity_dissenting":
                               got_precision.get("unanimity_dissenting"),
                           "adoption": (None if readoption is None
                                        else readoption["verdict"])},
            "published": {"verdict": was.get("PASS_or_UNRESOLVED"),
                          "mc_se_mw6": want_precision.get("mc_se_mw6"),
                          "fired": sorted(fired_then),
                          "adoption": published.get("verdict")},
            "differs": differs, "PASS": not differs}

    checks = []
    if table_check["checked"]:
        checks.append({"source": "table_gate", "checked": True,
                       "PASS": bool(table_check["PASS"]),
                       "differs": table_check["differs"]})
    for name, got in (("per_fixture_csv", from_csv), ("shard_ledgers", from_ledger)):
        if not got.get("present"):
            checks.append({"source": name, "checked": False,
                           "why": "not on disk"})
            continue
        d_mean = abs(float(got["mean"]) - float(headline["mean"]))
        d_n = int(got["n"]) - int(headline["n"])
        checks.append({"source": name, "checked": True,
                       "delta_mean": d_mean, "delta_n": d_n,
                       "PASS": bool(d_mean <= tolerance and d_n == 0)})

    # §9.3: `--verify` validates MANIFEST completeness — the 49 paths, no digest
    # disagreeing, no byte size disagreeing, and no entry of ours outside them.
    if check_manifest is None:
        check_manifest = evidence.parent.resolve() == EVIDENCE_DIR.resolve()
    manifest: dict[str, Any] = {"checked": False,
                                "why": "the evidence is not the committed "
                                       "reports/evidence/ directory"}
    if check_manifest:
        manifest = assert_manifest_complete(
            evidence.with_name(EVIDENCE_MANIFEST.name))
        manifest["checked"] = True
        checks.append({"source": "manifest", "checked": True,
                       "PASS": bool(manifest["PASS"])})

    ran = [c for c in checks if c.get("checked")]
    # F15: what this verification could NOT check is named in what it prints,
    # so "PASS" never quietly means "there was less to look at than the contract
    # promises". The two sources that are simply absent from disk are already on
    # `checks` as `checked: false`; this collects them beside the gate's own.
    unchecked = [{"field": c["source"], "why": c.get("why", "not on disk")}
                 for c in checks if not c.get("checked")]
    unchecked += list(table_check.get("unchecked_fields") or ())
    if not table_check.get("checked"):
        unchecked.append({"field": "gate_iv",
                          "why": table_check.get("why", "")})
    out = {"schema": SCHEMA_ID, "evidence": paths.rel(evidence),
           "unchecked": unchecked,
           "published": {"mean": headline.get("mean"), "n": headline.get("n"),
                         "ci_week": published.get("ci_week"),
                         "ci_season": published.get("ci_season"),
                         "verdict": published.get("verdict")},
           "per_fixture_csv": from_csv, "shard_ledgers": from_ledger,
           "manifest": manifest, "table_gate": table_check,
           "checks": checks, "tolerance": tolerance,
           "PASS": bool(ran) and all(c["PASS"] for c in ran)}
    if not out["PASS"]:
        raise MergeIncomplete(
            f"the published verdict does not re-derive from its own evidence: "
            f"{[c for c in checks if not c.get('PASS', True)]}. Either the "
            "committed files disagree with the ledger they were projected from, "
            "the table gate does not recompute from the rebound tallies, or "
            "nothing was available to check them against — and a verdict nobody "
            "can recompute is exactly what reports/evidence/ exists to prevent. "
            "§8.7: a verification that re-reads a JSON file it does not "
            "re-derive verifies nothing.")
    return out


# ==========================================================================
# 16. THE HARNESS-HASH FREEZE OF §8.3
# ==========================================================================

_HEX64 = re.compile(r"\b([0-9a-f]{64})\b")


def _git(*args: str) -> str | None:
    """One read-only `git` call, or ``None`` when git cannot answer.

    Never raises: an absent repository, an untracked file or a missing binary
    are all "not committed", which is the answer the freeze guard needs.
    """
    try:
        out = subprocess.run(("git", "-C", str(paths.REPO_ROOT), *args),
                             capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


def git_head(rev: str = "HEAD") -> str | None:
    out = _git("rev-parse", rev)
    return out.strip() if out else None


def git_blob_id(relpath: str, rev: str = "HEAD") -> str | None:
    out = _git("rev-parse", f"{rev}:{relpath}")
    return out.strip() if out else None


def git_committed_bytes(relpath: str, rev: str = "HEAD") -> bytes | None:
    """The file's COMMITTED bytes, which is the only version a freeze can bind."""
    try:
        out = subprocess.run(
            ("git", "-C", str(paths.REPO_ROOT), "show", f"{rev}:{relpath}"),
            capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def git_commit_touching(relpath: str, rev: str = "HEAD") -> str | None:
    out = _git("rev-list", "-1", rev, "--", relpath)
    return out.strip() if out and out.strip() else None


def git_is_ancestor(commit: str, rev: str = "HEAD") -> bool:
    try:
        out = subprocess.run(
            ("git", "-C", str(paths.REPO_ROOT), "merge-base", "--is-ancestor",
             commit, rev), capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


#: The committed block's own membership table header — the anchor that makes
#: "the recorded membership digests" a bounded set rather than every 64-hex
#: string in the prose.
_MEMBERSHIP_TABLE_HEADER = "| membership | count | SHA-256 of the canonical "

#: The committed block's conformance table header (§8.5).
_CONFORMANCE_TABLE_HEADER = "| row | § | obligation | green |"


def _recorded_membership_digests(text: str) -> set[str]:
    """The digests the committed freeze block's MEMBERSHIP TABLE records.

    Scoped to that one table, and that is the repair: the superseded reader
    scraped every backticked 64-hex string in the block — the harness hashes and
    the four pinned artifact digests among them — so §8.6 condition (3) could
    only ever check `fresh - recorded`, a containment. Bounded to the membership
    table, the check §8.6 actually asks for — that the recorded digests "equal a
    fresh recomputation" — is an EQUALITY, and a recorded digest that no fresh
    recomputation produces is as much a failure as a missing one.

    Reading them as a SET rather than by row label is still deliberate: a
    recomputation that produces the same values in a different order is the same
    membership.
    """
    out: set[str] = set()
    inside = False
    for line in text.splitlines():
        if line.startswith(_MEMBERSHIP_TABLE_HEADER):
            inside = True
            continue
        if inside:
            if not line.lstrip().startswith("|"):
                break
            for m in _HEX64.finditer(line):
                out.add(m.group(1))
    return out


def _recorded_conformance(text: str) -> dict[str, bool]:
    """The committed block's §8.5 conformance table, row id -> green."""
    out: dict[str, bool] = {}
    inside = False
    for line in text.splitlines():
        if line.startswith(_CONFORMANCE_TABLE_HEADER):
            inside = True
            continue
        if inside:
            if not line.lstrip().startswith("|"):
                break
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4 and re.fullmatch(r"L\d+", cells[0]):
                out[cells[0]] = cells[-1].lower() == "yes"
    return out


def _only_the_prereg(sources: Sequence[Path] | None, rev: str, where: str
                     ) -> list[Path]:
    """§8.6 condition (1): **this file and no other**, at HEAD and no other rev.

    The in-tree audit's finding 10 and the closure review's N-FREEZE-COMMIT are
    the same one: the guard "accepts arbitrary `sources` and `rev`", so a caller
    could choose which blob the freeze state is read out of. §8.6 names
    `reports/epl_widening_prereg_v2.md`; the keyword survives because a caller
    that names the file it means is clearer than one that cannot, but a
    DIFFERENT file is refused rather than honoured — the same treatment §2.3
    gives a frozen constant.
    """
    if str(rev) != "HEAD":
        raise EvWidenError(
            f"{where}: the freeze state is read at HEAD and at no other "
            f"revision, and {rev!r} was supplied. §8.6 condition (1) asks "
            "whether the commit that last touched the preregistration is an "
            "ancestor of HEAD; a caller-selected revision answers a different "
            "question about a different tree.")
    if sources is None:
        return [PREREG_PATH]
    got = [Path(x) for x in sources]
    if [x.resolve() for x in got] != [PREREG_PATH.resolve()]:
        raise EvWidenError(
            f"{where}: §8.6 condition (1) names "
            f"{paths.rel(PREREG_PATH)} — 'this file and no other. No second "
            f"source is accepted' — and {[paths.rel(x) for x in got]} was "
            "supplied. The superseded guard accepted any list of blobs and read "
            "the harness hash table out of whichever one carried it, which is "
            "not the file the law names.")
    return [PREREG_PATH]


def working_tree_bytes(relpath: str) -> bytes | None:
    """The bytes of a repository file as the WORKING TREE holds them.

    The counterpart of :func:`git_committed_bytes`, and it exists as its own
    function for the same reason that one does: §8.6 condition (1) compares the
    two, and a comparison whose two halves are read by two named functions can
    be exercised. It is a READER — it takes no argument that could alter a
    constant, inject an implementation, attest a lifecycle state or truncate a
    population — so §8.6's public-surface closure does not reach it.
    """
    path = paths.REPO_ROOT / relpath
    return path.read_bytes() if path.exists() else None


def harness_freeze_status(sources: Sequence[Path] | None = None, *,
                          rev: str = "HEAD") -> dict[str, Any]:
    """§8.6's guard. Has §8.3 step 2's follow-up commit landed, does it describe
    THESE bytes, and does it describe THIS document?

    §8.3 step 2: the commit appends a table of file, line count and SHA-256 for
    every harness file, the schema identifier, and the frozen membership
    digests, carrying 07b5871's sentence — *if any hash differs at the time the
    run is executed, it is not the run this document preregisters*.

    **Five conditions, all of them, or the state is not established** — §8.6's
    four, and (5) the committed block's own conformance table, added when the
    renderer's bypass parameters were closed:

    1. ``reports/epl_widening_prereg_v2.md`` is **committed**, and the commit
       that last touched it is an **ancestor of HEAD**;
    2. the freeze block in that **committed blob** carries a harness hash table
       whose two SHA-256 values equal the current bytes of ``epl/evwiden.py``
       and ``epl/tests/test_evwiden.py`` — and the committed bytes too, so a
       dirty tree is not frozen either;
    3. the **schema identifier** in that block is ``epl-evwiden-2``, and the
       **membership digests** it records equal a fresh recomputation from the
       pinned artifacts;
    4. the first-fit record, if present, is consistent with (1)–(3);
    5. the conformance report inside that committed block is **all green** — a
       block rendered over a red report cannot establish the state it attests.

    v1's guard performed (1) and (2) and stopped: "the guard parses only the two
    harness hashes; schema/membership are not validated and first-fit is merely
    returned", and its own test accepted a mocked committed source containing
    nothing but two hash lines. "Parsing two hash lines out of current prose is
    not a freeze" — and parsing two out of committed prose is not one either.

    Condition (3) needs the pinned artifacts. Where they are absent the state
    **cannot be established**, and this function reports so rather than
    assuming: a machine that cannot recompute the membership cannot check that
    the frozen one is the one this run would use, and it is not going to fit
    anything either.

    It asserts nothing about itself: an unfrozen harness is a fact to report,
    and the refusal is :func:`require_harness_freeze`'s job.
    """
    sources = _only_the_prereg(sources, rev, "harness_freeze_status")
    found: dict[str, dict[str, Any]] = {}
    where = None
    where_text = ""
    git_sources: list[dict[str, Any]] = []
    # §8.6 condition (1), and the half v2 was missing (IMP-POST-FIT-PROSE):
    # the document is bound to its committed blob AND its current bytes must
    # equal that blob's. v2 bound the blob and then checked current bytes only
    # for the two harness files, so an UNCOMMITTED post-fit edit to the
    # preregistration itself — the one edit §8.7's whole regime exists to
    # forbid — went undetected. A working tree in which the document has been
    # edited is a working tree in which no further fit of it may run.
    prereg_bytes_match_blob: bool | None = None
    for source in sources:
        rel = paths.rel(source)
        blob = git_committed_bytes(rel, rev)
        git_sources.append({"path": rel, "committed": blob is not None,
                            "blob": git_blob_id(rel, rev)})
        if blob is None:
            continue
        if source.resolve() == PREREG_PATH.resolve():
            prereg_bytes_match_blob = working_tree_bytes(rel) == blob
        text = blob.decode("utf-8", "replace")
        for line in text.splitlines():
            for name in HARNESS_FILES:
                if name in line and name not in found:
                    m = _HEX64.search(line)
                    if m:
                        found[name] = {"recorded": m.group(1), "source": rel}
                        if where is None:
                            where, where_text = rel, text

    missing = [f for f in HARNESS_FILES if f not in found]
    for name, rec in found.items():
        path = paths.REPO_ROOT / name
        rec["actual"] = sha256_file(path) if path.exists() else None
        committed = git_committed_bytes(name, rev)
        rec["committed"] = (hashlib.sha256(committed).hexdigest()
                            if committed is not None else None)
        rec["lines"] = (len(path.read_text().splitlines())
                        if path.exists() else None)
        rec["match"] = bool(rec["actual"] == rec["recorded"]
                            and rec["committed"] == rec["recorded"])

    differs = [n for n, r in found.items() if not r["match"]]
    commit = git_commit_touching(where, rev) if where else None
    ancestor = bool(commit and git_is_ancestor(commit, rev))
    uncommitted = [s["path"] for s in git_sources if not s["committed"]]

    # ---- condition (3): the schema identifier and the membership digests ----
    # Only computed once (1) and (2) hold, because recomputing the membership
    # reads the pinned artifacts and a run that has already failed the hash
    # table has no use for the answer.
    schema_ok: bool | None = None
    membership_ok: bool | None = None
    membership_why = ""
    if not missing and not differs and ancestor:
        schema_ok = f"Schema identifier: `{SCHEMA_ID}`" in where_text
    if schema_ok:
        recorded = _recorded_membership_digests(where_text)
        try:
            from epl import baseline

            corpus, played = load_corpus(), load_archive()
            walk = load_walk_ledger()
            cells = table_cells(baseline.load_matches(), played)
            digests = membership_digests(corpus, played, walk, table=cells)
            census = assert_table_census(cells)
            fresh = set(digests["digests"].values())
            fresh.add(_digest_list(f"{k}={v}" for k, v in
                                   sorted(census["by_label"].items())))
        except Exception as exc:                       # noqa: BLE001
            membership_ok = None
            membership_why = (
                f"the membership could not be recomputed from the pinned "
                f"artifacts ({type(exc).__name__}: {exc}), so §8.6 condition "
                "(3) cannot be established here — and a machine that cannot "
                "recompute the membership cannot check that the frozen one is "
                "the one this run would use")
        else:
            short = sorted(fresh - recorded)
            stray = sorted(recorded - fresh)
            membership_ok = not short and not stray
            if short or stray:
                membership_why = (
                    f"§8.6 condition (3) asks for EQUALITY, not containment: "
                    f"{len(short)} recomputed membership digest(s) are not in "
                    f"the committed freeze block (first: "
                    f"{[d[:12] for d in short[:3]]}) and {len(stray)} recorded "
                    f"digest(s) are not produced by a fresh recomputation "
                    f"(first: {[d[:12] for d in stray[:3]]})")

    # ---- condition (5): the committed block's conformance report is green ----
    # §8.5 makes a green report the precondition of RENDERING the block, and
    # the review's NEW-B4 observed that "the later freeze guard does not
    # validate report greenness" — so a block rendered through the bypass that
    # existed would still have established the freeze state. The block carries
    # the report; the guard reads it back.
    conformance_ok: bool | None = None
    conformance_why = ""
    if membership_ok:
        recorded_rows = _recorded_conformance(where_text)
        red = sorted(r for r, ok in recorded_rows.items() if not ok)
        # v3 §8.6 condition (5): **exactly** §8.5's eighteen rows, L1-L18, and
        # a nonempty all-green SUBSET fails. v2's guard accepted one, which
        # meant a block that had simply dropped a row it could not satisfy read
        # back as green.
        wrong_set = sorted(set(recorded_rows) ^ set(CONFORMANCE_ROWS))
        conformance_ok = bool(recorded_rows) and not red and not wrong_set
        if recorded_rows and wrong_set:
            conformance_why = (
                f"the committed freeze block's conformance table is not "
                f"exactly §8.5's eighteen rows: it differs at {wrong_set}. A "
                "nonempty all-green SUBSET is a refusal, not a pass — the "
                "superseded guard accepted one, so a block that had dropped "
                "the rows it could not satisfy read back as green.")
        elif not recorded_rows:
            conformance_why = (
                "the committed freeze block carries no §8.5 conformance table. "
                "§8.3 step 2 requires 'the conformance report of §8.5, all rows "
                "green' inside the block, and a block without one freezes a "
                "harness nothing graded")
        elif red:
            conformance_why = (
                f"the committed freeze block's conformance report is red at "
                f"{red}. §8.5: 'A hash table committed over code that does not "
                "implement the document freezes the wrong thing, which is the "
                "one thing a hash table must never do.'")

    # ---- condition (4): the first-fit record and its witness --------------
    record = first_fit_record()
    first_fit_ok: bool | None = None
    first_fit_why = ""
    if record is not None:
        try:
            assert_no_hashed_file_moved()
        except FreezeStateUnverified as exc:
            first_fit_ok, first_fit_why = False, str(exc)
        else:
            first_fit_ok = True

    if missing:
        why = (f"no COMMITTED harness-hash table names {missing} — §8.3 step "
               "2's follow-up commit has not landed, and step 3 says not one "
               "real fit of this document runs before it does. §8.6: a hash "
               "table that is not in a commit freezes nothing, because an "
               "uncommitted paste satisfies a check on prose beside bytes")
    elif differs:
        why = (f"the recorded digest for {differs} differs from the committed "
               "bytes or from the working tree: if any hash differs at the time "
               "the run is executed, it is not the run this document "
               "preregisters (§8.3 step 2)")
    elif not commit:
        why = ("the harness-hash table's source resolves to no commit, so there "
               "is no Git identity to bind the freeze to")
    elif not ancestor:
        why = (f"the commit {commit[:12]} that carries the harness-hash table is "
               f"not an ancestor of {rev}")
    elif prereg_bytes_match_blob is False:
        why = (f"§8.6 condition (1): {paths.rel(PREREG_PATH)}'s CURRENT bytes "
               f"differ from its committed blob at {rev}. The document is bound "
               "to the blob and to the working tree both, because §8.7 forbids "
               "any note appended after the first real fit 'prose or otherwise' "
               "— and an UNCOMMITTED edit is exactly the note a blob-only check "
               "cannot see")
    elif not schema_ok:
        why = (f"the committed freeze block does not carry the schema "
               f"identifier {SCHEMA_ID!r}. §8.6 condition (3): parsing two hash "
               "lines out of prose is not a freeze — the block must name the "
               "schema and the membership it froze, or it describes a different "
               "document's run")
    elif not membership_ok:
        why = ("§8.6 condition (3), the membership digests: " + membership_why)
    elif not conformance_ok:
        why = ("§8.6 condition (5), the conformance report: " + conformance_why)
    elif first_fit_ok is False:
        why = ("§8.6 condition (4), the first-fit record: " + first_fit_why)
    else:
        why = ""
    return {"frozen": bool(not missing and not differs and ancestor
                           and prereg_bytes_match_blob is not False
                           and schema_ok and membership_ok and conformance_ok
                           and first_fit_ok is not False),
            "prereg_bytes_match_blob": prereg_bytes_match_blob,
            "where": where, "files": found, "missing": missing, "why": why,
            "commit": commit, "is_ancestor": ancestor,
            "schema_ok": schema_ok, "membership_ok": membership_ok,
            "membership_why": membership_why,
            "conformance_ok": conformance_ok,
            "conformance_why": conformance_why,
            "first_fit_ok": first_fit_ok, "first_fit_why": first_fit_why,
            "sources": git_sources, "uncommitted_sources": uncommitted,
            "rev": rev, "first_real_fit": record,
            "schema": SCHEMA_ID}


def _refused(exc_types, fn) -> bool:
    """Did this scenario raise the class it is supposed to raise?

    §8.5's grading unit. "A row that cannot go red is not a row": every row of
    the report calls this with a scenario that only a conforming harness
    refuses, so a row goes red exactly when its own defect class is present.
    """
    try:
        fn()
    except exc_types:
        return True
    except Exception:                                  # noqa: BLE001
        return False
    return False


def _accepted(fn) -> bool:
    """The other half: did a legitimate call go through?"""
    try:
        fn()
    except Exception:                                  # noqa: BLE001
        return False
    return True


def _silently(fn, *args, **kwargs):
    """Call `fn` with stdout swallowed.

    §8.5's L18 probes the CLI by calling :func:`main`, which prints a `STOP:`
    line for every refusal — correct behaviour, and noise in a hash table that
    §8.3 step 2 says is PASTED into the document rather than transcribed. The
    return value is what the row grades; the print is not.
    """
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _cli_arguments() -> list[str]:
    """Every `add_argument` line of :func:`main`, as source text.

    §2.3's closure is about what a CALLER can name, and the CLI's surface is
    exactly its `add_argument` calls. Reading them is how L18 says that a
    retired flag is gone rather than merely ignored.
    """
    import inspect

    return [line.strip() for line in inspect.getsource(main).splitlines()
            if "add_argument" in line]


def _calls_made(fn) -> set[str]:
    """Every name this function CALLS, read off its syntax tree.

    A source-text check would be defeated by the docstrings and refusal messages
    that name the defect a function cures — which is most of them here.
    """
    import ast
    import inspect
    import textwrap

    out: set[str] = set()
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, SyntaxError, TypeError):          # pragma: no cover
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            out.add(f.attr if isinstance(f, ast.Attribute)
                    else getattr(f, "id", ""))
    return out


def _no_parameter(fn, *names: str) -> bool:
    import inspect

    try:
        params = set(inspect.signature(fn).parameters)
    except (TypeError, ValueError):                    # pragma: no cover
        return False
    return not any(n in params for n in names)


# ---- §8.5's synthetic table world, built here so the ROWS can execute ------
#
# §8.5 demands that "every row of v2's report executes a scenario that fails
# under its own defect class", and half of those scenarios are about the table
# leg — the scorer, the estimator, the unanimity rule, the parity ordering. A
# row cannot execute one of those against a hand-built dict without becoming
# the "names, not obligations" shape §8.5 condemns, so the report builds a
# complete SYNTHETIC 32-cell table leg and runs the production code over it.
#
# Every value below is written literally here, in the harness the freeze commit
# hashes; nothing is read, copied or derived from the pinned artifacts, so §7.4
# is satisfied for the same reason it is satisfied in the test module.

_CONF_SEASONS: tuple[str, ...] = ("2019/20", "2020/21", "2021/22", "2022/23",
                                  "2023/24", "2024/25", "2025/26")
_CONF_CLUBS: tuple[str, ...] = ("sunderland", "rich", "mid")
_CONF_PARTICLES = 8
_CONF_SEASONS_PER_PARTICLE = 4
_CONF_N_SIMS = _CONF_PARTICLES * _CONF_SEASONS_PER_PARTICLE


def _conf_tally(shift: int, *, jitter: int = 0,
                particles: int = _CONF_PARTICLES,
                k: int = _CONF_SEASONS_PER_PARTICLE,
                clubs: int = 3) -> np.ndarray:
    """A per-particle fractional rank-mass tally with honest margins.

    Every particle carries ``k`` times a permutation matrix, so every club row
    and every rank column sums to ``k`` — §5.1's equal-cluster condition.
    ``jitter = 0`` makes every particle identical and the bootstrap variance
    exactly zero, so a gate scenario can be about the gate; ``jitter > 0`` makes
    the particles differ and the standard error real.
    """
    out = np.zeros((particles, clubs, clubs), dtype=float)
    for s in range(particles):
        rot = (int(shift) + (s % (int(jitter) + 1))) % clubs
        for c in range(clubs):
            out[s, c, (c + rot) % clubs] = float(k)
    return out


def _conf_cells() -> list[dict[str, Any]]:
    """v3 §3.3's 32 cells — :data:`FROZEN_TABLE_SCHEDULE`, tuple by tuple.

    The synthetic leg carries the EXACT schedule (adjudication F6): the same
    seasons, labels, cutoff dates and treated-club identities the read-only pass
    measured, so a conformance row running over it is running over the
    population the production path produces, and `assert_table_census` is the
    same assertion here as there.

    The club UNIVERSE stays synthetic — three invented rows carry the tallies —
    and every value here is still written literally in this file, which is what
    §7.4 asks: the schedule is a constant the freeze commit hashes, not a read
    of `data/epl/matches.parquet`.
    """
    out: list[dict[str, Any]] = []
    for season, label, cutoff, treated_tuple in FROZEN_TABLE_SCHEDULE:
        treated = list(treated_tuple)
        out.append({
            "season": season, "cutoff_label": label, "cutoff": cutoff,
            "clubs": list(_CONF_CLUBS),
            "provisional_incumbent": ["rich"],
            "provisional_enlarged": sorted(["rich"] + treated),
            "treated_clubs": treated,
            "evidence": {**{c: 0.17 for c in treated},
                         "sunderland": 0.17, "rich": 50.0, "mid": 5.0},
        })
    return out


def _conf_parity(cells: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The protected oracle's rows, as :func:`run_parity_oracle` returns them."""
    return {f"{c['season']}|{c['cutoff_label']}": {
        "key": f"{c['season']}|{c['cutoff_label']}",
        "substantive_digest": f"sub-{c['season']}-{c['cutoff_label']}",
        "provisional_teams": ["rich"],
        "effective_posterior_hash": "book"} for c in cells}


def _conf_runner(*, delta: float = 0.0004, jitter: int = 0,
                 calls: list | None = None, break_parity: bool = False,
                 break_identity: str | None = None):
    """A cell runner that goes through :func:`run_cell_arms` and nothing else.

    It simulates nothing — ``simulate`` returns a label — but it drives the
    REAL paired-arm sequence, so the order §3.3's closure 1 fixes is the order
    this runner obeys, and ``calls`` records exactly which arms were reached
    before any refusal.
    """
    def run(cell: dict[str, Any],
            parity_row: dict[str, Any] | None = None) -> dict[str, Any]:
        treated = list(cell["treated_clubs"])
        key = f"{cell['season']}|{cell['cutoff_label']}"
        base = 0.08 + 0.0001 * TALLY_LABELS.index(cell["cutoff_label"])
        sub_c = f"sub-{cell['season']}-{cell['cutoff_label']}"
        if break_parity:
            sub_c += "-drifted"
        prov = {"control": ["rich"],
                "treatment": sorted({"rich"} | set(treated))}
        tallies = {
            "control": _conf_tally(0, jitter=jitter),
            "treatment": _conf_tally(1 if treated else 0, jitter=jitter)}
        tallies["matrix_control"] = (tallies["control"].sum(axis=0)
                                     / float(_CONF_N_SIMS))
        tallies["matrix_treatment"] = (tallies["treatment"].sum(axis=0)
                                       / float(_CONF_N_SIMS))

        def _simulate(name, book):
            if calls is not None:
                calls.append((key, name))
            return name

        def _record(name, book, run_):
            sampler = f"sampler-{key}"
            if name == "treatment" and treated:
                sampler += "-t"
            if break_identity == "untouched" and not treated \
                    and name == "treatment":
                sampler += "-moved"
            if break_identity == "treated" and treated and name == "treatment":
                sampler = f"sampler-{key}"
            trps = base + (delta if (treated and name == "treatment") else 0.0)
            return {
                "trps": trps, "wtrps": trps * 1.1, "flat_trps": 0.2,
                "sampler_digest": sampler,
                "substantive_digest": sub_c + ("-t" if name == "treatment"
                                               else ""),
                "effective_posterior_hash": "book",
                "provisional": list(prov[name]),
                "coverage": {"coverage50": 0.5, "coverage90": 0.9},
                "coverage_treated": {c: {"coverage50": 0.6, "coverage90": 0.95}
                                     for c in treated},
                "clubs_detail": {c: {"p_relegated": 0.6, "points_mean": 30.0,
                                     "points_sd": 14.1, "points_p5": 12.0,
                                     "points_p95": 50.0, "points_realised": 25}
                                 for c in treated},
                "n_sims": _CONF_N_SIMS, "n_particles": _CONF_PARTICLES,
                "tally_check": {"sims_per_particle": _CONF_SEASONS_PER_PARTICLE},
                "widening_mode": f"per_fixture_bernoulli@alpha={WIDENING_ALPHA:g}",
            }

        arms, parity = run_cell_arms(
            key, simulate=_simulate, record=_record,
            books={"control": prov["control"], "treatment": prov["treatment"]},
            parity_row=parity_row, provisional_control=prov["control"])
        return {
            "schema": SCHEMA_ID, "season": cell["season"],
            "cutoff_label": cell["cutoff_label"], "cutoff": cell["cutoff"],
            "clubs": list(cell["clubs"]), "treated_clubs": treated,
            "provisional_incumbent": list(cell["provisional_incumbent"]),
            "provisional_enlarged": list(cell["provisional_enlarged"]),
            "provisional_control": list(prov["control"]),
            "provisional_treatment": list(prov["treatment"]),
            "evidence": dict(cell["evidence"]),
            "n_sims": _CONF_N_SIMS, "seed": frozen_table_constants()["seed"],
            "arms": arms, "parity": parity,
            "identical": assert_table_identity(
                treated, arms["control"]["sampler_digest"],
                arms["treatment"]["sampler_digest"], where=key),
            "realised_hash": "realised",
            "realised_positions": {c: i + 1 for i, c in enumerate(_CONF_CLUBS)},
            "realised_spans": {c: 1 for c in _CONF_CLUBS},
            "realised_points": {c: 40 - 5 * i
                                for i, c in enumerate(_CONF_CLUBS)},
            "consequence_weights": [1.0, 1.0],
            "harness_sha256": "conformance",
            "_tallies": tallies,
        }

    return run


def _conf_table(scratch: Path, *, jitter: int = 0, delta: float = 0.0004,
                name: str = "table.jsonl") -> tuple[Path, list[dict[str, Any]]]:
    """Run the whole synthetic table leg through the production `run_table`."""
    cells = _conf_cells()
    path = Path(scratch) / name
    run_table(cells, path, runner=_conf_runner(delta=delta, jitter=jitter),
              parity=_conf_parity(cells), verbose=False)
    rows = [json.loads(line) for line in path.read_text().splitlines()
            if line.strip()]
    return path, rows


def _conf_mc_payload(rows: Sequence[dict[str, Any]],
                     path: Path) -> list[dict[str, Any]]:
    """The 32 deciding tallies §5.2 resamples, rebound off disk."""
    payload = []
    for row in rows:
        if not row.get("treated_clubs"):
            continue
        arms = load_tallies(path, row)
        positions, spans = _cell_positions(row)
        payload.append({"key": cell_key(row), "season": str(row["season"]),
                        "cutoff_label": str(row["cutoff_label"]),
                        "positions": positions, "spans": spans,
                        "control": arms["control"],
                        "treatment": arms["treatment"]})
    return payload


def _per_cell_resampled_unanimity(cells: Sequence[dict[str, Any]], *,
                                  point_verdict: bool) -> list[bool]:
    """§5.4's rule with the joint draw DE-PAIRED — the defect, implemented here.

    The in-tree audit's seed (k): "K resamples skipped or made per-cell". §5.4
    draws ONE ``picked`` per replicate and applies it to all thirty tallies;
    this draws one per cell. It exists so L3 and L4 can require the committed
    construction to DISAGREE with it — a scenario the committed rule cannot
    pass by accident, and the one the audit found nothing testing, because the
    only test of the rule used zero-variance tallies under which the two
    constructions are indistinguishable.
    """
    from epl import simmetrics

    cells = list(cells)
    mw6 = [c for c in cells if str(c["cutoff_label"]) == MW6_LABEL]
    n_particles = int(np.asarray(cells[0]["control"]).shape[0])
    seasons = [str(c["season"]) for c in mw6]
    rng = np.random.default_rng(UNANIMITY_SEED)
    verdicts: list[bool] = []
    for _ in range(UNANIMITY_K):
        deltas = {}
        for cell in cells:
            picked = rng.integers(0, n_particles, n_particles)
            scores = {}
            for arm in ("control", "treatment"):
                m = np.asarray(cell[arm], dtype=float)[picked].sum(axis=0)
                m = m / m.sum(axis=1, keepdims=True)
                scores[arm] = float(simmetrics.trps(m, cell["positions"],
                                                   spans=cell["spans"]))
            deltas[str(cell["key"])] = scores["treatment"] - scores["control"]
        verdicts.append(iv_c_verdict([deltas[str(c["key"])] for c in mw6],
                                     seasons))
    return verdicts


#: §8.5's eighteen rows, by id, in order. The set is EXACT at both ends —
#: `--freeze-block` refuses to render over anything but these eighteen, and
#: §8.6 condition (5) refuses to read the committed block back over anything
#: but these eighteen. "A nonempty all-green SUBSET is a refusal, not a pass: a
#: renderer that accepted any green subset would render over a report that had
#: simply dropped the rows it could not satisfy, and a review found that exact
#: acceptance in v2's harness."
CONFORMANCE_ROWS: tuple[str, ...] = tuple(f"L{i}" for i in range(1, 19))

#: Where §8.5's pytest run records what it did. v3 §8.2 pass 3 names it: the
#: `@pinned` tests plus "§8.5's conformance scenario run, whose JSON report is
#: the artifact `--conformance` and `--freeze-block` consume".
CONFORMANCE_ARTIFACT = paths.FIT_DIR / "evwiden_conformance.json"

#: The pytest node id of each row's committed test. Fixed here so that the
#: harness cannot invent an id and then find it: the ids the artifact carries
#: must be exactly these.
def conformance_test_id(row_id: str) -> str:
    """`epl/tests/test_evwiden.py::test_conformance_L5`, and nothing else."""
    return f"{HARNESS_FILES[1]}::test_conformance_{row_id}"


_CONFORMANCE_RUN: list[dict[str, Any]] | None = None


def conformance_row(row_id: str) -> dict[str, Any]:
    """Execute §8.5's scenarios and return ONE row — the pytest tests' entry.

    The scenarios are deterministic at the frozen constants and build a
    synthetic leg from literals, so the run is MEMOISED per process: eighteen
    committed tests calling this share one execution rather than paying for
    eighteen. What the eighteen tests establish is that each named row was
    reached and was green **in a pytest process**, which is what §8.5's artifact
    then records and the freeze reads back.

    A row this function cannot find is an ERROR rather than a silent absence:
    "a scenario that did not run" is red, and a row dropped from the report must
    take its own test down with it rather than disappearing from a subset the
    guard would have accepted.
    """
    global _CONFORMANCE_RUN
    if _CONFORMANCE_RUN is None:
        _CONFORMANCE_RUN = implementation_report()
    for row in _CONFORMANCE_RUN:
        if row["id"] == row_id:
            return row
    raise EvWidenError(
        f"§8.5 has no row {row_id!r}: the report carries "
        f"{[r['id'] for r in _CONFORMANCE_RUN]} and this document fixes "
        f"{list(CONFORMANCE_ROWS)}. A row that is not in the report is a "
        "scenario that did not run, which §8.5 grades red rather than absent.")


def pytest_session_id() -> str | None:
    """The identity of the pytest session running in THIS process, or ``None``.

    §8.5's artifact is a record of what a pytest **session** did, and the seed
    audit demonstrated that nothing tied it to one: "in a fresh process that ran
    no L-row, `write_conformance_artifact({r: 'passed' …})` followed by
    `assert_conformance_artifact()` returns ok=True, count=18". The writer
    stamped the current harness hashes, so the digest cross-check could never
    catch a fabrication.

    The id is a digest of the running process and its invocation. It does not —
    and cannot — prove that the eighteen scenarios executed; an operator inside
    a pytest process remains able to call the writer, which is recorded as
    limitation **L3** under the adjudication's threat model. What it does is
    make the artifact a claim about a session, refusable when there is no
    session at all, so the fabrication route the audit actually walked is shut.
    """
    if _sys.modules.get("pytest") is None or \
            _sys.modules.get("_pytest.config") is None:
        return None
    return hashlib.sha256(json.dumps(
        {"pid": _os.getpid(), "argv": [str(a) for a in _sys.argv],
         "pytest": str(getattr(_sys.modules["pytest"], "__version__", ""))},
        sort_keys=True).encode("utf-8")).hexdigest()


def write_conformance_artifact(outcomes: dict[str, str]) -> Path:
    """Record what §8.5's pytest run actually did, one line per row.

    Written by the pytest session at teardown, from the outcomes its own tests
    reached — not by the reporting code, which is the whole point: "the chain
    now terminates outside the reporting code: the report is a READING of a
    pytest run, the pytest run is committed code that either executed the
    scenario or did not, and the freeze block records which run it read."

    **It is not part of this module's public surface** and it refuses outside a
    pytest session (adjudication F22): see :func:`pytest_session_id`.
    """
    session = pytest_session_id()
    if session is None:
        raise EvWidenError(
            "refusing to write §8.5's conformance artifact: there is no pytest "
            "session in this process. The artifact records what a pytest "
            "SESSION did — §8.2 pass 3 is `pytest epl/tests/test_evwiden.py`, "
            "and §8.5's rows are green iff their own committed tests passed in "
            "that run. A process that ran no row has nothing to report, and an "
            "artifact it wrote would be a claim about a session that never "
            "existed.")
    CONFORMANCE_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": SCHEMA_ID,
        "produced_at": pd.Timestamp.now("UTC").isoformat(),
        "session": {"id": session, "runner": "pytest"},
        "harness": {name: (sha256_file(paths.REPO_ROOT / name)
                           if (paths.REPO_ROOT / name).exists() else None)
                    for name in HARNESS_FILES},
        "tests": [{"id": conformance_test_id(rid),
                   "row": rid, "outcome": str(outcome)}
                  for rid, outcome in sorted(
                      outcomes.items(),
                      key=lambda kv: (len(kv[0]), kv[0]))],
    }
    body["passed"] = sum(1 for x in body["tests"] if x["outcome"] == "passed")
    CONFORMANCE_ARTIFACT.write_text(
        json.dumps(body, indent=2, sort_keys=True, default=str) + "\n")
    return CONFORMANCE_ARTIFACT


def conformance_artifact_status() -> dict[str, Any]:
    """Read §8.5's artifact and CROSS-CHECK it three ways.

    > 1. **the test ids are exactly the eighteen** — no more, no fewer, none
    >    renamed;
    > 2. **every one of the eighteen outcomes is `passed`** — a skip, an error,
    >    an xfail and an absence are all red, because each is a scenario that
    >    did not run;
    > 3. **the reported count is eighteen.**
    """
    out: dict[str, Any] = {"path": paths.rel(CONFORMANCE_ARTIFACT),
                           "ok": False, "count": 0, "test_ids": [],
                           "sha256": None, "why": ""}
    if not CONFORMANCE_ARTIFACT.exists():
        return {**out, "why": (
            f"there is no pytest artifact at {paths.rel(CONFORMANCE_ARTIFACT)}. "
            "§8.5: a row is green IFF its own test id is present and passed in "
            "that artifact, and the harness may not mark a row green from "
            "anything it computed itself. Run `pytest epl/tests/test_evwiden.py` "
            "(§8.2 pass 3) and render again.")}
    raw = CONFORMANCE_ARTIFACT.read_bytes()
    out["sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        body = json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:  # pragma: no cover
        return {**out, "why": f"the artifact is not readable: {exc}"}
    tests = list(body.get("tests") or ())
    got = [str(x.get("id")) for x in tests]
    want = [conformance_test_id(r) for r in CONFORMANCE_ROWS]
    out["test_ids"] = got
    out["count"] = len(got)
    out["outcomes"] = {str(x.get("id")): str(x.get("outcome")) for x in tests}
    if got != want:
        return {**out, "why": (
            f"the artifact carries {len(got)} test id(s) and §8.5 fixes exactly "
            f"{len(want)}, L1-L18 in order. Missing "
            f"{[w for w in want if w not in got]}; unexpected "
            f"{[g for g in got if g not in want]}. A nonempty all-green SUBSET "
            "is a refusal, not a pass — a report that simply dropped the rows "
            "it could not satisfy would otherwise read as green.")}
    unpassed = [x["id"] for x in tests if str(x.get("outcome")) != "passed"]
    if unpassed:
        return {**out, "why": (
            f"the artifact records {unpassed} as not passed. §8.5: 'a skip, an "
            "error, an xfail and an absence are all red, because each is a "
            "scenario that did not run'.")}
    if int(body.get("passed") or 0) != len(CONFORMANCE_ROWS):
        return {**out, "why": (
            f"the artifact reports {body.get('passed')!r} passing and §8.5 "
            f"fixes {len(CONFORMANCE_ROWS)}.")}
    # ...and it names the PYTEST SESSION that produced it (adjudication F22).
    # §8.5's rows are green iff their own committed tests passed in a pytest
    # run; an artifact carrying no session is not a report of one.
    session = dict(body.get("session") or {})
    out["session"] = session
    if str(session.get("runner")) != "pytest" or \
            not re.fullmatch(r"[0-9a-f]{64}", str(session.get("id") or "")):
        return {**out, "why": (
            f"the artifact records session {session!r} and §8.5's artifact is "
            "written by a pytest SESSION at teardown, from the outcomes its own "
            "eighteen tests reached. An artifact with no session on it is not a "
            "report of a pytest run; run `pytest epl/tests/test_evwiden.py` "
            "(§8.2 pass 3) and render again.")}
    # ...and it names the harness it ran against. §8.5 says "an artifact from a
    # different harness fails §8.6's harness-hash condition alongside it", and
    # that is true of a COMMITTED block — but a block rendered NOW from a stale
    # artifact would carry current harness digests beside a run of older bytes,
    # and condition (2) compares the block to the tree rather than the artifact
    # to either. The artifact carries its own, so the comparison exists here.
    now = {name: (sha256_file(paths.REPO_ROOT / name)
                  if (paths.REPO_ROOT / name).exists() else None)
           for name in HARNESS_FILES}
    if dict(body.get("harness") or {}) != now:
        return {**out, "why": (
            "the artifact records a run of different harness bytes than the "
            "ones on disk: it saw "
            + ", ".join(f"{k} {str(v)[:12]}…"
                        for k, v in sorted((body.get("harness") or {}).items()))
            + " and the tree carries "
            + ", ".join(f"{k} {str(v)[:12]}…" for k, v in sorted(now.items()))
            + ". §8.5's rows are green iff THESE bytes' scenarios passed, so a "
            "run of other bytes certifies nothing. Re-run `pytest "
            "epl/tests/test_evwiden.py` (§8.2 pass 3).")}
    return {**out, "ok": True, "harness": body.get("harness"),
            "produced_at": body.get("produced_at")}


def assert_conformance_artifact() -> dict[str, Any]:
    """§8.3: the block does not render without §8.5's artifact behind it."""
    status = conformance_artifact_status()
    if not status["ok"]:
        raise EvWidenError(
            "refusing to render §8.3 step 2's freeze block: " + status["why"]
            + " §8.5's report may not be its own witness — v2's arrangement "
            "was circular in a way no amount of strengthening the rows could "
            "fix, because `implementation_report` executed the scenarios AND "
            "reported on itself, the principal test asserted its own `ok` "
            "fields, `freeze_block` consumed the same object, and the "
            "committed-block guard accepted any nonempty all-green subset.")
    return status


def implementation_report() -> list[dict[str, Any]]:
    """§8.5's conformance report — **behavioural predicates, not names**.

    **It takes no arguments.** The superseded signature accepted a ``power``
    object and handed it to :func:`power_reproduces`, so L16 graded whatever the
    caller supplied: the in-tree audit built a six-row dict carrying
    ``PUBLISHED_POWER``'s own numbers and a 101-long dummy curve and watched the
    row go green without a simulation. Every row's evidence is now computed
    here, from the committed code, or it is not evidence.

    > `--freeze-block` requires a green conformance report, and a conformance
    > report is worthless if its rows check that names exist. v1's fourteen rows
    > checked field names, constants, callables, a subclass count and a
    > substring — they could all be green while the obligations they were named
    > for failed, and they were. **Every row of v2's report executes a scenario
    > that fails under its own defect class. A row that cannot go red is not a
    > row.**

    Eighteen rows, L1-L18, each naming its section, its obligation and the
    scenario it executes — and each of them now EXECUTING that scenario. The
    cross-model review's behavioural table found seven rows that did not:
    two that could not go red at all (L1's disjunct greened from an equality its
    own fixture forced; L18 claimed an `n_sims` case it did not contain), one
    that was false (L5 graded existence while the production ordering was
    wrong), and four that graded names, signatures or source substrings. The
    in-tree audit proved L1's tautology by seeding the exact defect its scenario
    names and watching the row stay green.

    What replaces them is a synthetic 32-cell table leg — every value written
    literally above, §7.4-synthetic for the same reason the test module's world
    is — run through the production `run_table`, `score_table`, `table_gate`,
    `paired_mc_bootstrap` and `unanimity`. The rows that could not previously
    reach the production path now go through it.

    §8.5's closing clause then requires the TEST that reads this report to
    independently execute at least L5, L6, L7, L9, L11, L12 and L13's
    scenarios, "so that a report which lies about itself is caught by something
    other than itself"; ``epl/tests/test_evwiden.py`` carries those as tests of
    its own.

    This function writes nothing inside the repository. The scenarios that need
    a directory get a `tempfile.TemporaryDirectory`, which is §8.2's own
    convention for the pre-freeze passes.
    """
    import inspect

    from epl import leaguesim

    refusals = {name for name, obj in globals().items()
                if inspect.isclass(obj) and issubclass(obj, EvWidenError)
                and obj is not EvWidenError}
    rows: list[dict[str, Any]] = []

    def row(rid: str, section: str, obligation: str, scenario: str,
            ok: bool, **extra: Any) -> None:
        rows.append({"id": rid, "section": section, "obligation": obligation,
                     "scenario": scenario, "ok": bool(ok), **extra})

    with tempfile.TemporaryDirectory(prefix="evwiden-conformance-") as tmp:
        scratch = Path(tmp)

        # ---- L1: both arms from one posterior ---------------------------
        # The corpus row is DELIBERATELY not Arm B: the superseded row's
        # fixture set `probs_incumbent` equal to the corpus's own
        # probabilities, so `rps_B == rps_native` held by construction and the
        # predicate's `or` disjunct carried it whatever the delta did. With the
        # two distinct, pairing the delta against the corpus is a change the
        # row can SEE.
        fit_out = {
            "cutoff": "2019-08-09", "season": "2019/20", "block": "b",
            "match_ids": ["m0"], "pairs": [("a", "b")],
            "probs_incumbent": np.array([[0.5, 0.25, 0.25]]),
            "probs_arm": np.array([[0.4, 0.3, 0.3]]),
            "probs_widened": {}, "treated": ["m0"],
            "provisional_incumbent": [], "provisional_enlarged": ["a"],
            "provisional_ledger": [], "evidence": {"a": 1.0, "b": 50.0},
        }
        _native = [0.52, 0.24, 0.24]
        corpus_row = pd.Series({
            "match_id": "m0", "season": "2019/20", "block": "b",
            "date": "2019-08-10", "home_key": "a", "away_key": "b", "y": 0,
            "dc_home": _native[0], "dc_draw": _native[1], "dc_away": _native[2],
            "dc_rps": float(score_mod.rps(np.array([_native]),
                                          np.array([0]))[0])})
        made = _fixture_row(
            FitPoint(cutoff="2019-08-09", season="2019/20", block="b",
                     match_ids=("m0",)), 0, fit_out, corpus_row,
            {name: 0.0 if name in ("wall_seconds", "control_max_abs_diff",
                                   "control_mean_abs_diff") else
             ([] if name in ("match_ids", "cold_start_teams",
                             "provisional_incumbent", "provisional_enlarged",
                             "provisional_ledger", "warnings", "unpriceable")
              else ({} if name in ("evidence", "health", "blas_threads")
                    else "conformance"))
             for name in REQUIRED_FIT_FIELDS}, key="k",
            config_sha="c", shard_id="0/4", harness_frozen=False, e_star=E_STAR,
            grid=E_GRID)
        paired_b = float(made["rps_arm"]) - float(made["rps_B"])
        paired_corpus = float(made["rps_arm"]) - float(made["rps_native"])
        l1 = (abs(float(made["delta"]) - paired_b) < 1e-15
              and abs(float(made["delta_vs_corpus"]) - paired_corpus) < 1e-15
              # ...and the two are genuinely different numbers, so a rewiring
              # of the enlarged pass to read the corpus MOVES the delta
              and abs(paired_b - paired_corpus) > 1e-9
              and float(made["rps_B"]) != float(made["rps_native"]))
        row("L1", "§2.3", "both arms from one posterior; the corpus an external "
            "control",
            "build a row whose corpus probabilities DIFFER from Arm B, then "
            "require `delta` to equal `rps_A − rps_B` exactly, "
            "`delta_vs_corpus` to equal `rps_A − rps_native` exactly, and the "
            "two to be different numbers — so pairing the delta against the "
            "corpus, the defect this row names, changes it", l1,
            detail={"delta": made["delta"], "rps_A": made["rps_arm"],
                    "rps_B": made["rps_B"], "rps_native": made["rps_native"],
                    "delta_vs_corpus": made["delta_vs_corpus"]})

        # ---- the synthetic 32-cell table leg, scored for real -------------
        flat_path, flat_rows = _conf_table(scratch, jitter=0, name="flat.jsonl")
        flat_scored = score_table(flat_rows, ledger_path=flat_path,
                                  expected_cells=EXPECTED_TABLE_CELLS)
        flat_gate = table_gate(flat_scored)

        # ---- L2: per-horizon gate, no cross-horizon average --------------
        # 17 structural zeros and 15 treated cells at +0.0004 pool to
        # +0.000183, which a pooled gate would pass; MW6's own mean is
        # +0.0004 and must FAIL. The object is the one `score_table` produced.
        pooled = float(np.mean([c["delta_trps"]
                                for c in flat_scored["per_cell"]]))
        published = json.dumps({k: v for k, v in flat_gate.items()
                                if k != "withdrawn"})
        l2 = (pooled <= TABLE_TOLERANCE
              and flat_scored["mw6"]["mean"] > TABLE_TOLERANCE
              and flat_gate["verdict"] == "FAIL"
              and flat_gate["resolved"] is True
              and flat_gate["iv_a"]["PASS"] is False
              and "pooled" not in published
              and "pooled_delta_trps" not in json.dumps(flat_scored)
              .replace(json.dumps(flat_scored["withdrawn"]), ""))
        row("L2", "§4.1", "the per-horizon gate; no cross-horizon average on "
            "any deciding path",
            "score a real 32-cell leg whose pooled mean passes while MW6's "
            "treated mean exceeds +0.0002; `score_table` must produce it, "
            "`table_gate` must FAIL it, and no pooled figure may appear "
            "anywhere outside the `withdrawn` note", l2,
            detail={"pooled": pooled, "mw6_mean": flat_scored["mw6"]["mean"],
                    "verdict": flat_gate["verdict"]})

        # ---- L3: the MC estimator is tie-aware and jointly resampled ------
        payload = _conf_mc_payload(flat_rows, flat_path)
        jitter_path, jitter_rows = _conf_table(scratch, jitter=1,
                                               name="jitter.jsonl")
        jitter_payload = _conf_mc_payload(jitter_rows, jitter_path)
        joint = paired_mc_bootstrap(jitter_payload)
        per_cell_se = [v for k, v in joint["mc_se_per_cell"].items()
                       if k in {str(c["key"]) for c in jitter_payload
                                if c["cutoff_label"] == MW6_LABEL}]
        quadrature = float(np.sqrt(sum(v ** 2 for v in per_cell_se))
                           / max(len(per_cell_se), 1))

        # ...and the tally is FRACTIONAL RANK MASS, not ordinal `.order`: a tie
        # block of span 2 must spread 1/2 across the two positions it occupies.
        class _TiedRows:
            block_start = np.array([[0, 0, 2]])
            block_span = np.array([[2, 2, 1]])
            resolution_code = np.array([[0, 0, 0]])
            order = np.array([[0, 1, 2]])
            particle = np.array([0])

        class _TiedPlan:
            clubs = ("a", "b", "c")
            boundaries = ((0, 1),)
            rule_id = "epl-1"

        class _TiedRun:
            retained_rows = _TiedRows()
            plan = _TiedPlan()
            n_particles = 1

        tied = particle_tallies(_TiedRun())
        fractional = bool(abs(float(tied[0, 0, 0]) - float(tied[0, 1, 0])) < 1e-12
                          and abs(float(tied[0, 0, 0]) - 0.5) < 1e-12)
        l3 = (len(jitter_payload) == EXPECTED_TABLE_TREATED
              and joint["n_deciding_cells"] == EXPECTED_TABLE_TREATED
              and joint["mc_se_label"][MW6_LABEL] > quadrature
              and fractional)
        row("L3", "§5.1–5.2", "the MC estimator is tie-aware and jointly "
            "resampled",
            "run the estimator over the whole 32-tally object of the 16 "
            "deciding cells: a per-cell (quadrature) combination shrinks the "
            "MW6 label SE and the joint one does not; and tally a tie block of "
            "span 2, which must carry 1/2 on each position rather than an "
            "ordinal 1 and 0", l3,
            detail={"n_deciding_cells": joint["n_deciding_cells"],
                    "label_se": joint["mc_se_label"][MW6_LABEL],
                    "quadrature": quadrature, "tied_mass": float(tied[0, 0, 0])})

        # ---- L4: the unanimity rule --------------------------------------
        # The REAL rule, over the real 32-tally object, three ways: it agrees
        # with a point verdict it was scored against; it dissents from the
        # inverted one and the gate then comes back UNRESOLVED with P5 fired;
        # and the joint construction DISAGREES with the de-paired one, which is
        # the audit's own seed (k).
        point = bool(flat_scored["mw6"]["mean"] > 0.0
                     and flat_scored["mw6"]["ci95"][0] > 0.0)
        agree = unanimity(payload, point_verdict=point)
        against = unanimity(payload, point_verdict=not point)
        gate_unresolved = table_gate({
            **flat_scored,
            "mc": {**flat_scored["mc"], "unanimity": against}})
        one_flip = [False] * UNANIMITY_K
        one_flip[UNANIMITY_K // 2] = True
        fabricated = table_gate({
            **flat_scored,
            "mc": {**flat_scored["mc"],
                   "unanimity": {"k": 1, "seed": UNANIMITY_SEED,
                                 "verdicts": [point], "dissenting": 0,
                                 "point_verdict": point, "fired": False}}})
        joint_verdicts = list(agree["verdicts"])
        depaired = _per_cell_resampled_unanimity(jitter_payload,
                                                 point_verdict=point)
        jitter_joint = unanimity(jitter_payload, point_verdict=point)
        l4 = (len(agree["verdicts"]) == UNANIMITY_K
              and agree["k"] == UNANIMITY_K == 200
              and agree["seed"] == UNANIMITY_SEED == 20260828
              and agree["fired"] is False and agree["dissenting"] == 0
              and against["fired"] is True
              and against["dissenting"] == UNANIMITY_K
              and gate_unresolved["verdict"] == "UNRESOLVED"
              and "P5" in gate_unresolved["precision"]["fired"]
              # a fabricated K = 1 object cannot resolve the gate
              and fabricated["verdict"] == "UNRESOLVED"
              and "P5" in fabricated["precision"]["fired"]
              # the counting rule: one dissenting k is enough
              and unanimity_fired(one_flip, point_verdict=False) is True
              and unanimity_fired([False] * UNANIMITY_K,
                                  point_verdict=False) is False
              # ...and the draw is JOINT, not per-cell
              and list(jitter_joint["verdicts"]) != list(depaired)
              and len(joint_verdicts) == UNANIMITY_K)
        row("L4", "§5.4", "P5, the unanimity rule at K = 200",
            "run the real rule over the real 32-tally object: 200 recomputed "
            "iv-c verdicts at the frozen K and seed; inverting the point "
            "verdict must make every one dissent and gate (iv) come back "
            "UNRESOLVED with P5 fired; a fabricated K = 1 object must not "
            "resolve it; and the joint per-replicate draw must disagree with "
            "the same rule de-paired per cell", l4,
            detail={"n_verdicts": len(agree["verdicts"]),
                    "dissenting_against": against["dissenting"],
                    "joint_vs_depaired_differ":
                        list(jitter_joint["verdicts"]) != list(depaired)})

        # ---- L5: parity complete before treatment ------------------------
        oracle_cells = _conf_cells()
        full = _conf_parity(oracle_cells)
        short = dict(list(full.items())[:-1])
        # ...and the ORDER, executed: a cell whose control arm does not match
        # protected output must raise BEFORE its treatment arm is simulated.
        seen: list[tuple[str, str]] = []
        drifted = _conf_runner(calls=seen, break_parity=True)
        ordered = _refused(
            TableIdentityBreak,
            lambda: run_table(oracle_cells, scratch / "ordering.jsonl",
                              runner=drifted, parity=full, verbose=False))
        untouched: list[tuple[str, str]] = []
        never_ran = _refused(
            TableIdentityBreak,
            lambda: run_table(oracle_cells, scratch / "shortoracle.jsonl",
                              runner=_conf_runner(calls=untouched),
                              parity=short, verbose=False))
        l5 = (_accepted(lambda: assert_parity_complete(oracle_cells, full))
              and _refused(TableIdentityBreak,
                           lambda: assert_parity_complete(oracle_cells, short))
              and _refused(TableIdentityBreak,
                           lambda: assert_parity_complete(oracle_cells, {}))
              and _refused(TableIdentityBreak,
                           lambda: assert_parity_complete(oracle_cells[:-1],
                                                          full))
              # the treatment arm of the drifted cell never ran
              and ordered and seen == [(seen[0][0], "control")]
              # and a short oracle stops the leg before ANY arm is simulated
              and never_ran and untouched == []
              # ...and `run_cell_arms` refuses a cell with no parity row at all
              and _refused(TableIdentityBreak,
                           lambda: run_cell_arms(
                               "k", simulate=lambda *a: None,
                               record=lambda *a: {}, books={},
                               parity_row=None, provisional_control=()))
              and _no_parameter(run_table, "require_parity", "limit")
              and _no_parameter(run_parity_oracle, "limit", "sample", "subset"))
        row("L5", "§3.3", "parity complete at all 32 cells before one treated "
            "simulation, and established per cell before its treatment arm",
            "run the leg with an oracle of 34 cells and with none — each must "
            "raise TableIdentityBreak before ANY arm is simulated; run it with "
            "a control arm that drifted from protected output — the refusal "
            "must arrive after exactly one simulate call, the control's; and "
            "assert no `require_parity` parameter and no oracle `--limit` "
            "exist", l5,
            detail={"arms_simulated_before_refusal": len(seen),
                    "arms_simulated_short_oracle": len(untouched)})

        # ---- L6: pre-freeze read-only ------------------------------------
        store_table = paths.STORE_DIR / STORE_TABLE_PARQUET
        store_before = ((sha256_file(store_table),
                         store_table.stat().st_mtime_ns)
                        if store_table.exists() else (None, None))
        empty = scratch / "store"
        kept_store_dir = paths.STORE_DIR
        try:
            paths.STORE_DIR = empty                        # type: ignore[misc]
            # the accessor, and the pre-freeze command path that reaches it:
            # `table_cells` is what `--membership`, `--plan` and
            # `--freeze-block` all call, and it must raise rather than build.
            l6 = (_refused(StoreNotBuilt, lambda: read_only_store())
                  and _refused(StoreNotBuilt, lambda: read_only_store(root=empty))
                  and _refused(StoreNotBuilt,
                               lambda: table_cells(pd.DataFrame(
                                   {"season": ["2019/20"], "date": ["2019-08-09"],
                                    "home_key": ["a"], "away_key": ["b"],
                                    "played": [True], "match_id": ["m"],
                                    "fthg": [1], "ftag": [0]})))
                  and not empty.exists())
        finally:
            paths.STORE_DIR = kept_store_dir               # type: ignore[misc]
        store_after = ((sha256_file(store_table), store_table.stat().st_mtime_ns)
                       if store_table.exists() else (None, None))
        l6 = (l6
              and store_before == store_after
              and _no_parameter(read_only_store, "build", "rebuild", "create")
              # the CALLS `table_cells` makes, read off the syntax tree: its
              # docstring names `build_store` as the defect it cures
              and "build_store" not in _calls_made(table_cells)
              and "read_only_store" in _calls_made(table_cells))
        row("L6", "§8.2", "the pre-freeze commands are mechanically read-only",
            "point the store root at an empty directory and call both the "
            "accessor and `table_cells` — the function every pre-freeze "
            "command reaches: StoreNotBuilt from each, nothing created, no "
            "build parameter, `table_cells` never naming `build_store`, and "
            "the shared store's bytes and mtime unchanged across the row", l6,
            detail={"store_unchanged": store_before == store_after})

        # ---- L7: no freeze-state boolean on any fit surface --------------
        surfaces = (Engine.__init__, TableRunner.__init__, ParityRunner.__init__,
                    run_fits, run_table, assert_may_fit, run_parity_oracle,
                    simulate_arm, run_canary, freeze_block, merge)
        l7 = all(_no_parameter(fn, "harness_frozen", "frozen", "freeze",
                               "check_implementation")
                 for fn in surfaces if fn is not merge)
        # ...and the renderer takes NOTHING it is supposed to compute: the
        # audit's seed (u) rendered this block over a fabricated power object
        # and a fabricated pre-freeze enumeration, with all eighteen rows
        # green. Both parameters are gone, from the renderer and from the two
        # functions it renders through.
        l7 = l7 and all(_no_parameter(fn, "power", "pre_freeze_runs")
                        for fn in (freeze_block, assert_implements_document,
                                   implementation_report))
        # `merge` keeps the two lifecycle keywords the audit describes, but
        # they are seams now: §8.6's closure refuses them at a preregistered
        # target, and they are unreachable from the CLI.
        l7 = l7 and _refused(
            EvWidenError,
            lambda: merge(shards=SHARDS, harness_frozen=True,
                          require_canaries=False))
        if l7 and not _frozen_now():
            # ...and while unfrozen EVERY public fit and simulation surface
            # refuses the pinned artifacts, not only the guard.
            try:
                played = load_archive()
            except Exception:                              # noqa: BLE001
                played = None
            checks = [lambda: assert_may_fit("conformance", played=played),
                      lambda: assert_may_fit("conformance", played=None),
                      lambda: simulate_arm(None, None, played=played),
                      lambda: run_canary(played=played, directory=scratch)]
            if played is not None:
                corpus_frame = None
                try:
                    corpus_frame = load_corpus()
                except Exception:                          # noqa: BLE001
                    corpus_frame = None
                checks.append(lambda: Engine(corpus_frame, played,
                                             directory=scratch))
                checks.append(lambda: TableRunner(directory=scratch))
                checks.append(lambda: ParityRunner(directory=scratch))
                checks.append(lambda: run_fits(
                    [], scratch / "s.jsonl", corpus_frame))
                checks.append(lambda: run_table(_conf_cells(),
                                                scratch / "t.jsonl"))
            l7 = all(_refused(EvWidenError, fn) for fn in checks)
            # ...and §8.2's pass 7 unlocks the parity oracle and NOTHING else
            # v3 §8.2 authorises NO pass that fits or simulates, so there
            # is no feasibility surface left to unlock anything (P5-B2).
            l7 = l7 and FEASIBILITY_SURFACE_CLOSED and not any(
                hasattr(_sys.modules[__name__], n) for n in
                ("parity_feasibility_pass", "parity_feasibility_census",
                 "FEASIBILITY_SURFACES", "_FEASIBILITY"))
        row("L7", "§8.6", "the guard establishes the freeze state and never "
            "accepts it, on every surface",
            "assert no fit or simulation surface accepts a freeze-state or "
            "implementation-check argument, and that merge's two lifecycle "
            "keywords are refused at a preregistered target; then call the "
            "guard, Engine, TableRunner, ParityRunner, run_fits, run_table, "
            "simulate_arm and run_canary on the pinned artifacts while "
            "unfrozen and require refusal from each", l7)

        # ---- L8: first-fit state global and validated --------------------
        kept_first_fit = FIRST_FIT_JSON
        kept_witness = FIRST_FIT_WITNESS
        globals()["FIRST_FIT_JSON"] = scratch / "first_real_fit.json"
        globals()["FIRST_FIT_WITNESS"] = scratch / "first_fit_witness.jsonl"
        try:
            record_first_real_fit(where="the conformance report")
            planted = json.loads(FIRST_FIT_JSON.read_text())
            planted["prereg_blob"] = "0" * 40
            FIRST_FIT_JSON.write_text(json.dumps(planted))
            l8 = (_no_parameter(first_fit_record, "directory", "dir", "path")
                  and _no_parameter(record_first_real_fit, "directory", "dir",
                                    "path")
                  and _no_parameter(assert_no_hashed_file_moved, "directory",
                                    "dir", "path")
                  and _refused(FreezeStateUnverified,
                               assert_no_hashed_file_moved))
            stripped = {k: v for k, v in planted.items()
                        if k not in ("prereg", "prereg_blob")}
            FIRST_FIT_JSON.write_text(json.dumps(stripped))
            l8 = l8 and _refused(FreezeStateUnverified,
                                 assert_no_hashed_file_moved)
            # ...and the RATCHET: deleting the record while its witness stands
            # must NOT revert the regime to pre-fit (B6/NB5). Two review rounds
            # found deletion resetting the whole lifecycle.
            FIRST_FIT_JSON.unlink()
            l8 = (l8 and first_fit_record() is None
                  and bool(witness_lines())
                  and _refused(FreezeStateUnverified, first_fit_state)
                  and _refused(FreezeStateUnverified,
                               assert_no_hashed_file_moved))
            # a record no witness line names is forged or hand-written
            FIRST_FIT_WITNESS.unlink()
            FIRST_FIT_JSON.write_text(json.dumps(planted))
            l8 = l8 and _refused(FreezeStateUnverified, first_fit_state)
            # ...and a line removed from the middle breaks the chain after it
            FIRST_FIT_JSON.unlink()
            for i in range(3):
                FIRST_FIT_JSON.unlink(missing_ok=True)
                record_first_real_fit(where=f"the conformance report {i}")
            raw = FIRST_FIT_WITNESS.read_text().splitlines()
            FIRST_FIT_WITNESS.write_text("\n".join([raw[0], raw[2]]) + "\n")
            l8 = (l8 and len(raw) == 3
                  and _refused(FreezeStateUnverified, witness_lines))
        finally:
            globals()["FIRST_FIT_JSON"] = kept_first_fit
            globals()["FIRST_FIT_WITNESS"] = kept_witness
        l8 = (l8
              and FIRST_FIT_JSON == paths.FIT_DIR / "evwiden_first_real_fit.json"
              and FIRST_FIT_WITNESS == (paths.FIT_DIR
                                        / "evwiden_first_fit_witness.jsonl")
              and _no_parameter(witness_lines, "directory", "dir", "path")
              and _no_parameter(first_fit_state, "directory", "dir", "path"))
        row("L8", "§8.6",
            "the first-fit state is one fixed path, validated, and RATCHETED",
            "assert the record's and the witness's functions take no directory "
            "argument; plant a record naming a different prereg blob and "
            "require FreezeStateUnverified; strip its identity fields and "
            "require it again; DELETE the record while its witness stands and "
            "require the post-first-fit state to hold; plant a record with no "
            "witness line and require refusal; and break the witness's chain "
            "digest and require refusal", l8)

        # ---- L9: the frozen sequence -------------------------------------
        kept_seq = SEQUENCE_DIR
        globals()["SEQUENCE_DIR"] = scratch / "sequence"
        try:
            for step in SEQUENCE_STEPS:
                write_sequence_marker(step, produced={"step": step})
            l9 = True
            for i, step in enumerate(SEQUENCE_STEPS[1:], 1):
                marker = sequence_marker_path(SEQUENCE_STEPS[i - 1])
                text = marker.read_text()
                marker.unlink()
                l9 = l9 and _refused(
                    SequenceViolation,
                    lambda s=step: require_sequence(s, enforce=True))
                marker.write_text(text)
            # ...and a step that RAN AND FAILED unlocks nothing either
            failed = sequence_marker_path(SEQUENCE_STEPS[0])
            kept_text = failed.read_text()
            failed.unlink()
            write_sequence_marker(SEQUENCE_STEPS[0], complete=False,
                                  produced={"failure": "the canary did not pass"})
            l9 = l9 and _refused(
                SequenceViolation,
                lambda: require_sequence(SEQUENCE_STEPS[1], enforce=True))
            failed.unlink()
            failed.write_text(kept_text)
            # ...and a marker is written ONCE: a second write of a different
            # product under the same freeze commit refuses rather than
            # silently replacing a file §9.3's MANIFEST has already hashed.
            l9 = l9 and _refused(
                SequenceViolation,
                lambda: write_sequence_marker(SEQUENCE_STEPS[0],
                                              produced={"step": "different"}))
            l9 = l9 and _accepted(
                lambda: write_sequence_marker(
                    SEQUENCE_STEPS[0], produced={"step": SEQUENCE_STEPS[0]}))
            # ...and a marker that never CLAIMS completion unlocks nothing:
            # NB6 found a missing `complete` read as true-by-absence
            silent = sequence_marker_path(SEQUENCE_STEPS[0])
            kept_silent = silent.read_text()
            body = json.loads(kept_silent)
            body.pop("complete")
            silent.write_text(json.dumps(body))
            l9 = l9 and _refused(
                SequenceViolation,
                lambda: require_sequence(SEQUENCE_STEPS[1], enforce=True))
            # ...and a marker whose `produced` was edited while its digest was
            # left behind describes a product that no longer exists in that form
            body = json.loads(kept_silent)
            body["produced"] = {"step": "edited after the fact"}
            silent.write_text(json.dumps(body))
            l9 = l9 and _refused(
                SequenceViolation,
                lambda: require_sequence(SEQUENCE_STEPS[1], enforce=True))
            silent.write_text(kept_silent)
            # ...and step 5's OPEN CLAIM is opened BEFORE it spends anything
            # (P5-B8), unlocks nothing while it stands, and is RECLAIMABLE once
            # per dated record (adjudication F3) — while a COMPLETED step is
            # once-only, which is the half §4.4 rests on.
            sequence_marker_path(SEQUENCE_STEPS[4]).unlink()
            l9 = (l9
                  and _accepted(lambda: claim_sequence_step(SEQUENCE_STEPS[4],
                                                            note="opened"))
                  # an open claim unlocks nothing while it stands...
                  and not read_sequence_marker(SEQUENCE_STEPS[4])["complete"]
                  # ...a crash may resume, and the resumption writes itself down
                  and _accepted(lambda: claim_sequence_step(
                      SEQUENCE_STEPS[4], note="reopened after a crash"))
                  and [r["note"] for r in
                       read_sequence_marker(SEQUENCE_STEPS[4])
                       ["produced"][_RECLAIM_KEY]] == ["reopened after a crash"]
                  # ...the completion carries that history forward...
                  and _accepted(lambda: write_sequence_marker(
                      SEQUENCE_STEPS[4], produced={"step": "done"}))
                  and len(read_sequence_marker(SEQUENCE_STEPS[4])
                          ["produced"][_RECLAIM_KEY]) == 1
                  # ...and no reclaim reopens an outcome
                  and _refused(SequenceViolation,
                               lambda: claim_sequence_step(SEQUENCE_STEPS[4],
                                                           note="after")))
        finally:
            globals()["SEQUENCE_DIR"] = kept_seq
        script = launch_script(scratch / "run")
        # the precondition must be a COMMAND before the step's command, and a
        # comment naming the marker is not one: the in-tree audit found the
        # committed test satisfied by `#   marker: sequence/stepN_*.json`
        # inside the preceding block, so every `need_marker` line could be
        # deleted with the row and twelve tests still green.
        commands = [line for line in script.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
        need = [i for i, line in enumerate(commands)
                if line.startswith("need_marker ")]
        steps_at = [script.find(f"# STEP {i}") for i in range(1, 6)]
        ordered_steps = all(v >= 0 for v in steps_at) and steps_at == sorted(steps_at)
        guarded = True
        for predecessor, command in (("step1_results_canary",
                                      "run_step single_opening"),
                                     ("step2_single_opening", "run_step shard_00"),
                                     ("step3_shards", "run_step merge"),
                                     ("step4_merge", "run_step table"),
                                     ("step5_parity", "run_step evidence")):
            marker_at = [i for i, line in enumerate(commands)
                         if line.startswith(f"need_marker {predecessor} ")]
            guarded = guarded and len(marker_at) == 1
            if command is not None and marker_at:
                at = [i for i, line in enumerate(commands)
                      if line.startswith(command)]
                guarded = guarded and bool(at) and marker_at[0] < at[0]
        # v3 §8.4, N-RH-FIRST-ACT: step 2's own COMMAND is among them, with a
        # scratch --dir the launcher creates. The review found the launcher
        # carrying only comments for that step.
        step2 = [line for line in commands if "--limit 1" in line]
        l9 = (l9 and ordered_steps and guarded and len(need) == 5
              and len(step2) == 1
              and "--dir \"$SCRATCH\"" in step2[0]
              and any(line.startswith("SCRATCH=") for line in commands)
              and any(line.startswith('mkdir -p "$SCRATCH"')
                      for line in commands)
              # ...and the canary is COPIED into it, before step 2's command:
              # without it `require_run_preconditions` refuses the step's own
              # scratch and the step is not executable (adjudication F2)
              and any(line.startswith(f'cp "$DIR/{CANARY_NAME}" '
                                      f'"$SCRATCH/{CANARY_NAME}"')
                      for line in commands[:commands.index(step2[0])])
              and commands.index("run_step merge $PY -u -m epl.evwiden --merge "
                                 f"--shards {SHARDS} --dir \"$DIR\"")
              < [i for i, line in enumerate(commands)
                 if line.startswith("run_step table")][0]
              and sum(1 for line in commands
                      if line.startswith("run_step shard_")) == SHARDS
              and _refused(EvWidenError, lambda: launch_script(scratch / "run",
                                                               shards=2)))
        row("L9", "§8.4", "the frozen five-step sequence and its markers",
            "remove each marker in turn and require the corresponding step "
            "to raise SequenceViolation; record a FAILED step and require it "
            "to unlock nothing; strip a marker's `complete` key and require "
            "the next step to refuse; edit a marker's `produced` while leaving "
            "its digest and require the recomputation to catch it; open step "
            "5's CLAIM before it spends anything, reclaim it once and require "
            "the dated record to be appended, complete it and require the "
            "history to survive, then require a claim after the outcome to "
            "refuse; require a second, different marker write under one "
            "freeze commit to refuse; read the generated launch.sh as "
            "COMMANDS — every precondition must be a `need_marker` command "
            "line before its step's command, not a comment naming the marker — "
            "and require step 2's own command to be among them, with the "
            "scratch --dir the launcher creates and the canary copied into it",
            l9, detail={"need_marker_commands": len(need)})

        # ---- L10: tallies bound and rebound ------------------------------
        swap = scratch / "swap.jsonl"
        cell_row = {"season": "2019/20", "cutoff_label": MW6_LABEL,
                    "n_sims": _CONF_N_SIMS, "arms": {}}
        tally = _conf_tally(0)
        target, sha = write_tallies(swap, cell_row,
                                    {"control": tally, "treatment": tally})
        bound = dict(cell_row, tally_sha256=sha)
        l10 = _accepted(lambda: load_tallies(swap, bound))
        with np.load(target) as data:
            payload_npz = {k: np.asarray(data[k]) for k in data.files}
        # THE REPLACEMENT IS A LEGAL TALLY, BOUND TO ITS OWN MATRIX. The
        # in-tree audit found this leg unable to fail for its own reason:
        # disabling the recorded-digest comparison left the row green, because
        # the swapped array no longer matched the STORED matrix and §5.1's
        # binding check raised the same class on the same object. With the
        # sidecar's matrix replaced too, the only thing left that can refuse
        # this read is the recorded digest — and the proof that it is the
        # digest is that the SAME file loads once the row records its new one.
        replacement = _conf_tally(1)
        payload_npz["treatment"] = replacement
        payload_npz["matrix_treatment"] = (replacement.sum(axis=0)
                                           / float(cell_row["n_sims"]))
        np.savez_compressed(target, **payload_npz)
        l10 = (l10
               and _refused(TableMCImprecise, lambda: load_tallies(swap, bound))
               and _accepted(lambda: load_tallies(
                   swap, dict(cell_row, tally_sha256=sha256_file(target)))))
        # ...and now the other half of the row's own scenario: an array the
        # sidecar's matrix does NOT bind, with the row's digest forged to match
        # it, is refused by §5.1's binding checks instead
        payload_npz["treatment"] = _conf_tally(2)
        np.savez_compressed(target, **payload_npz)
        l10 = (l10
               and _refused(TableMCImprecise,
                            lambda: load_tallies(
                                swap, dict(cell_row,
                                           tally_sha256=sha256_file(target)))))
        # ...and the whole recomputation refuses too: swap one deciding cell's
        # tally under a scored leg and `score_table` must not re-derive a gate.
        rescore_path = scratch / "rescore.jsonl"
        _, rescore_rows = _conf_table(scratch, jitter=0, name="rescore.jsonl")
        victim = next(r for r in rescore_rows if r["treated_clubs"])
        victim_file = tally_path(rescore_path, victim)
        with np.load(victim_file) as data:
            swapped = {k: np.asarray(data[k]) for k in data.files}
        swapped["treatment"] = _conf_tally(2)
        np.savez_compressed(victim_file, **swapped)
        l10 = (l10
               and _refused(TableMCImprecise,
                            lambda: score_table(rescore_rows,
                                                ledger_path=rescore_path))
               and "tally_sha256" in _TABLE_ROW_FIELDS
               and "tally_sha256" in _TABLE_COLUMNS
               and "score_table" in _calls_made(verify)
               and "table_gate" in _calls_made(verify))
        row("L10", "§8.7, §9.3", "every deciding tally is bound to its row and "
            "rebound on every read",
            "replace a tally with a structurally valid different one after the "
            "run: the read must refuse on the recorded digest, and refuse "
            "again on §5.1's binding checks when the row's digest is forged "
            "too; then swap one deciding cell's tally under a scored leg and "
            "require `score_table` to refuse rather than re-derive a gate",
            l10)

        # ---- L11: sampler_digest purity ----------------------------------
        # The signature pin, and the equal-digest check AT THE LEVEL THE
        # RUNNER USES: two books differing only in `provisional`, over ONE run
        # and ONE tally, driven through `run_cell_arms` — the paired-arm
        # sequence `TableRunner.__call__` is built from.
        class _PureBook:
            def __init__(self, provisional):
                self.provisional = frozenset(provisional)
                self.alpha = WIDENING_ALPHA

            def content_hash(self):
                return "book-" + ",".join(sorted(self.provisional))

        class _PureRows:
            block_start = np.array([[0, 1, 2]])
            block_span = np.array([[1, 1, 1]])
            resolution_code = np.array([[0, 0, 0]])
            order = np.array([[0, 1, 2]])
            particle = np.array([0])
            points = np.array([[30, 25, 20]])
            gd = np.array([[10, 0, -10]])
            gf = np.array([[40, 35, 30]])

        class _PurePlan:
            season = "2019/20"
            season_code = "2019-20"
            cutoff = "2019-08-09"
            observed_by = "2019-08-09"
            clubs = ("a", "b", "c")
            fixtures = ()
            adjustments = ()
            boundaries = ((0, 1),)
            rule_id = "epl-1"
            n_sims = 1
            n_particles = 1
            seed = 1
            chunk_size = 1
            n_unresolved = 0
            results_lag = 0

        class _PureRun:
            matrix = np.eye(3)
            n_sims = 1
            n_particles = 1
            retained_rows = _PureRows()
            plan = _PurePlan()

        pure_run, pure_tally = _PureRun(), particle_tallies(_PureRun())
        seen_arms: list[str] = []

        def _pure_simulate(name, book):
            seen_arms.append(name)
            return pure_run

        def _pure_record(name, book, run_):
            return {"substantive_digest": "same",
                    "effective_posterior_hash": book.content_hash(),
                    "sampler_digest": sampler_digest(run_, pure_tally),
                    "provisional": sorted(book.provisional)}

        pure_arms, _ = run_cell_arms(
            "pure", simulate=_pure_simulate, record=_pure_record,
            books={"control": _PureBook(["rich"]),
                   "treatment": _PureBook(["rich", "sunderland"])},
            parity_row={"substantive_digest": "same",
                        "provisional_teams": ["rich"],
                        "effective_posterior_hash": "book-rich"},
            provisional_control=["rich"])
        l11 = (list(inspect.signature(sampler_digest).parameters)
               == ["run", "tallies"]
               and seen_arms == ["control", "treatment"]
               and (pure_arms["control"]["provisional"]
                    != pure_arms["treatment"]["provisional"])
               and (pure_arms["control"]["sampler_digest"]
                    == pure_arms["treatment"]["sampler_digest"]))
        row("L11", "§3.3", "`sampler_digest` is a pure function of "
            "(run, tallies)",
            "assert the pinned signature; and drive the runner's own "
            "paired-arm sequence with two books differing only in "
            "`provisional` over one run and one tally — the two arms' "
            "provisional fields must differ and their sampler digests must be "
            "EQUAL", l11)

        # ---- L12: the identity control is exercised, not stubbed ---------
        # The three checks are functions now, and the row EXECUTES all three
        # with their own seeded inputs. The in-tree audit's finding was that
        # loosening the eight-decimal comparison went red for the wrong reason
        # — CanaryFailed from the identity-canary branch, which only runs on
        # the 16 of 78 openings where the union adds nobody — so on the 62
        # openings that carry treated fixtures the site §10 names was
        # uncovered. Called unconditionally and tested directly, it is not.
        stored_probs = np.array([[0.5, 0.25, 0.25], [0.3, 0.4, 0.3]])
        drift = stored_probs.copy()
        drift[0, 0] += 1e-9
        drift[0, 1] -= 1e-9
        moved = np.array([[0.5, 0.25, 0.25], [0.31, 0.39, 0.30]])
        l12 = (_accepted(lambda: assert_identity_control(
                   "2019-08-09", ("m0", "m1"), stored_probs, stored_probs))
               and _refused(ControlMismatch, lambda: assert_identity_control(
                   "2019-08-09", ("m0", "m1"), drift, stored_probs))
               and _accepted(lambda: assert_untreated_unmoved(
                   "2019-08-09", ("m0", "m1"), stored_probs, stored_probs, ()))
               and _refused(UntreatedMoved, lambda: assert_untreated_unmoved(
                   "2019-08-09", ("m0", "m1"), moved, stored_probs, {"m0"}))
               and _accepted(lambda: assert_pass_two_three_agree(
                   "2019-08-09", "m0", stored_probs[0], stored_probs[0]))
               and _refused(EvWidenError, lambda: assert_pass_two_three_agree(
                   "2019-08-09", "m0", stored_probs[0], drift[0]))
               # ...and the production path calls all three, read off its own
               # syntax tree rather than its source text
               and {"assert_identity_control", "assert_untreated_unmoved",
                    "assert_pass_two_three_agree"} <= _calls_made(Engine.fit))
        row("L12", "§3.2", "the identity control is exercised in the production "
            "path, not reimplemented by a stub",
            "execute all three checks `Engine.fit` makes — the exact "
            "eight-decimal comparison against a 1e-9 drift, the "
            "`UntreatedMoved` loop against a fixture that moved, and the "
            "pass-2/pass-3 agreement — and require `Engine.fit` to call all "
            "three", l12)

        # ---- L13: the structural-zero guard is two-sided ------------------
        def _zero_row(**over):
            base = {"match_id": "m", "e_min": 99.0, "delta": 0.0,
                    "incumbent_widened": False, "treated": False}
            base.update(over)
            return base

        l13 = (_accepted(lambda: assert_structural_zeros([_zero_row()]))
               and _refused(UntreatedMoved,
                            lambda: assert_structural_zeros(
                                [_zero_row(delta=1e-9)]))
               and _refused(UntreatedMoved,
                            lambda: assert_structural_zeros(
                                [_zero_row(e_min=1.0, incumbent_widened=True,
                                           delta=1e-9)])))
        row("L13", "§2.3", "the structural-zero guard is two-sided at the merge",
            "merge a row with `e_min >= e*` and a non-zero delta, and a "
            "thin-but-incumbent-widened row with a non-zero delta; each must "
            "raise UntreatedMoved", l13)

        # ---- L14: both per-label censuses, and §0.6's exclusion ----------
        census = _conf_cells()
        moved_cells = [dict(c) for c in census]
        give = next(c for c in moved_cells
                    if c["cutoff_label"] == "MW0" and c["treated_clubs"])
        take = next(c for c in moved_cells
                    if c["cutoff_label"] == "MW3" and not c["treated_clubs"])
        take["treated_clubs"], give["treated_clubs"] = \
            list(give["treated_clubs"]), []
        # a cell moved between LABELS keeps 32/15 and the TREATED census intact
        relabelled = [dict(c) for c in census]
        shift = next(c for c in relabelled
                     if c["cutoff_label"] == "MW19" and not c["treated_clubs"]
                     and f"{c['season']}|MW10" not in EXCLUDED_CELLS
                     and c["season"] not in ("2019/20", "2020/21"))
        shift["cutoff_label"] = "MW10"
        restored = [dict(c) for c in census
                    if f"{c['season']}|{c['cutoff_label']}" != "2019/20|MW3"]
        restored.append(dict(census[0], season="2019/20", cutoff_label="MW0",
                             treated_clubs=list(census[0]["treated_clubs"])))
        l14 = (_accepted(lambda: assert_table_census(census))
               and _refused(MembershipMismatch,
                            lambda: assert_table_census(moved_cells))
               and _refused(MembershipMismatch,
                            lambda: assert_table_census(relabelled))
               and _refused(MembershipMismatch,
                            lambda: assert_table_census(restored))
               and _refused(FeasibilityRecordMismatch,
                            assert_feasibility_permits_a_freeze
                            if not feasibility_status()["ok"] else
                            lambda: (_ for _ in ()).throw(
                                FeasibilityRecordMismatch("x")))
               and "assert_table_census" in _calls_made(table_cells))
        row("L14", "§0.6/§3.3",
            "both per-label censuses and the feasibility scope are pinned",
            "perturb one cell's treated set between labels, keeping the 32/15 "
            "totals intact; move a cell between labels keeping 32 intact; "
            "restore one of §0.6's three excluded keys; and refuse a census "
            "record that is not the record — each must refuse", l14)

        # ---- L15: the evidence contract is closed -------------------------
        manifest = scratch / "MANIFEST.sha256"
        entries = {}
        for rel in MANIFEST_PATHS:
            target_file = scratch / Path(rel).name
            target_file.write_text(rel)
            entries[rel] = target_file
        update_manifest({k: str(v) for k, v in entries.items()}, manifest,
                        require=MANIFEST_PATHS)
        l15 = _accepted(lambda: assert_manifest_complete(manifest,
                                                         entries=entries))
        lines = manifest.read_text().splitlines()
        sha_l, rel_l, size_l = lines[0].split()
        lines[0] = f"{sha_l}  {rel_l}  {int(size_l) + 1}"
        manifest.write_text("\n".join(lines) + "\n")
        l15 = l15 and _refused(MergeIncomplete,
                               lambda: assert_manifest_complete(
                                   manifest, entries=entries))
        dropped = dict(entries)
        dropped[MANIFEST_PATHS[-1]] = scratch / "absent"
        l15 = l15 and _refused(
            MergeIncomplete,
            lambda: update_manifest({k: str(v) for k, v in dropped.items()},
                                    scratch / "other.sha256",
                                    require=MANIFEST_PATHS))
        kept = table_projection({"per_cell": [{"key": "k"}]}, {"verdict": "PASS"})
        l15 = (l15 and len(MANIFEST_PATHS) == 49
               # §9.3: exactly 32 tallies — the schedule minus §0.6's three
               and len([m for m in MANIFEST_PATHS if "/tallies/" in m]) == 32
               and not any(f"{k.split('|')[0].replace('/', '-')}|"
                           f"{k.split('|')[1]}.npz" in m
                           for k in EXCLUDED_CELLS for m in MANIFEST_PATHS)
               and bool(kept["scored"].get("per_cell"))
               and _silently(main, ["--shards", "2", "--merge"]) == 2
               # every sequence marker is a manifest member, so publication
               # cannot rewrite one after hashing it (§9.3)
               and all(f"data/epl/fit/evwiden/sequence/{step}.json"
                       in MANIFEST_PATHS for step in SEQUENCE_STEPS))
        row("L15", "§9", "the evidence contract is closed",
            "drop one of the 49 MANIFEST paths; corrupt a byte size; check "
            "`scored.per_cell` survives the projection; pass `--shards 2`; and "
            "require all five sequence markers to be manifest members — each "
            "must refuse", l15)

        # ---- L16: the power table reproduces, through the REAL comparison -
        reproduced = power_reproduces()
        l16 = (bool(reproduced["PASS"])
               and len(reproduced["checks"]) == len(PUBLISHED_POWER)
               # ...and the object compared is a real simulation, not a stub:
               # every check carries the 101-point curve `power_simulation`
               # computes, read off the comparison rather than off a key the
               # caller may simply have omitted
               and all(c.get("curve_points") == POWER_GRID_POINTS
                       for c in reproduced["checks"])
               # ...and every published column was compared, `ratio` included
               and all("ratio" in c for c in reproduced["checks"]))
        row("L16", "§6.3", "the six published power rows reproduce",
            "run the committed `power_simulation()` at the frozen constants "
            "through the REAL comparison — not a stubbed power object — and "
            "require all six rows, every published column including `ratio`, "
            "and a 101-point curve behind each", l16, detail=reproduced)

        # ---- L17: the always-PASS controls are measured -------------------
        dirty = [
            {"match_id": "m0", "e_min": 99.0, "delta": 1e-9, "treated": False,
             "incumbent_widened": False, "cutoff": "2019-08-09",
             "fit": {"provisional_incumbent": ["rich"],
                     "provisional_ledger": ["mid"]}},
        ]
        measured = measured_controls(dirty)
        publishable = {
            "n": 1, "mean": 0.0, "sd": 0.0, "se_iid": 0.0,
            "ci95": [0.0, 0.0], "ci95_season": [0.0, 0.0],
            "n_blocks": 1, "n_blocks_season": 1,
            "controls": measured, "adoption": {"ADOPT": False},
            "secondaries": {}, "n_fixtures": 1,
        }
        published_controls = (evidence_object(publishable)
                              .get("controls") or {})
        l17 = (measured["untreated_moved"]["n"] == 1
               and measured["untreated_moved"]["PASS"] is False
               and measured["predicate_mismatch"]["n"] == 1
               and measured["predicate_mismatch"]["PASS"] is False
               and measured_controls([])["untreated_moved"]["PASS"] is True
               # ...and the measured counts reach the published object
               and (published_controls.get("untreated_moved") or {}).get("n") == 1
               and (published_controls.get("untreated_moved") or {}).get(
                   "PASS") is False
               and "measured_controls" in _calls_made(merge))
        row("L17", "§9.1", "the two always-PASS controls are measured off the "
            "merged rows and published",
            "measure a run containing one UntreatedMoved-class row and one "
            "PredicateMismatch-class row, then project it through "
            "`evidence_object`: the published counts must be non-zero and "
            "their PASS false, and `merge` must call the measurement", l17)

        # ---- L18: the frozen constants are not overridable ----------------
        frozen_budget = frozen_table_constants()
        l18 = all([
            _refused(EvWidenError, lambda: estimand([], n_boot=N_BOOT + 1)),
            _refused(EvWidenError, lambda: score_table([], n_boot=N_BOOT + 1)),
            _refused(EvWidenError, lambda: score_table([], mc_boot=MC_BOOT + 1)),
            _refused(EvWidenError,
                     lambda: paired_mc_bootstrap([], seed=MC_SEED + 1)),
            _refused(EvWidenError,
                     lambda: power_simulation(replicates=POWER_REPLICATES + 1)),
            _refused(EvWidenError, lambda: unanimity([], point_verdict=False,
                                                     k=UNANIMITY_K + 1)),
            _refused(EvWidenError, lambda: merge(shards=SHARDS + 1)),
            _refused(EvWidenError, lambda: run_fits([], scratch / "x.jsonl",
                                                    None, e_star=E_STAR + 1)),
            _refused(EvWidenError, lambda: estimand([], e_star=E_STAR + 1)),
            _refused(EvWidenError,
                     lambda: estimand([], grid=tuple(E_GRID) + (99.0,))),
            # ...the MW6 table interval of §5, which §2.3 names and which took
            # both of its constants without refusing either
            _refused(EvWidenError,
                     lambda: iv_c_verdict([0.0], ["s"], n_boot=N_BOOT + 1)),
            _refused(EvWidenError,
                     lambda: iv_c_verdict([0.0], ["s"], seed=BOOTSTRAP_SEED + 1)),
            # ...and the seams that carried an effect §8.6 closes: an
            # alternative freeze source, an alternative interpreter in the
            # post-freeze launcher, evidence published without §9.3's manifest,
            # a supplied cell census, an injected canary fitter, and the
            # marker check turned off
            _refused(EvWidenError,
                     lambda: harness_freeze_status([AMENDMENTS_PATH])),
            _refused(EvWidenError,
                     lambda: harness_freeze_status(rev="HEAD~1")),
            _refused(EvWidenError,
                     lambda: require_harness_freeze([AMENDMENTS_PATH])),
            _no_parameter(launch_script, "python"),
            _no_parameter(write_launch_script, "python", "kwargs"),
            _no_parameter(load_ledger, "allow_poison"),
            _refused(EvWidenError,
                     lambda: write_evidence({}, manifest=False)),
            _refused(EvWidenError,
                     lambda: load_table_ledger(TABLE_LEDGER, expected=[])),
            # ...and `require_sequence(enforce=False)` under the freeze, which
            # cannot be attempted here because the freeze has not landed:
            # `epl/tests/test_evwiden.py` drives it with the freeze mocked
            "_frozen_now" in _calls_made(require_sequence),
            # `n_sims`, the simulation seed and the chunk size are not
            # overridable because they are not PARAMETERS: every table surface
            # resolves them from the frozen law.
            _no_parameter(TableRunner.__init__, "n_sims", "seed", "chunk_size"),
            _no_parameter(ParityRunner.__init__, "n_sims", "seed", "chunk_size"),
            _no_parameter(run_table, "n_sims", "seed", "chunk_size"),
            _no_parameter(simulate_arm, "n_sims", "seed", "chunk_size"),
            frozen_budget == {"n_sims": 20_000, "seed": 20260611,
                              "chunk_size": frozen_budget["chunk_size"]},
            frozen_budget["n_sims"] == 20_000,
            # §8.3 step 2's block is PASTED into the document, so the rows
            # that probe the CLI may not print their refusals onto the render.
            # Each of these `main` calls writes a STOP line to stdout, which is
            # the CLI behaving correctly and is noise in a hash table.
            _silently(main, ["--n-boot", "500", "--merge"]) == 2,
            _silently(main, ["--shard", "0/2", "--run"]) == 2,
            _silently(main, ["--limit", "2", "--run"]) == 2,
            _silently(main, ["--limit", "1", "--table"]) == 2,
            # v3 §8.4, P5-B8: the table ledger is RESOLVED and no flag names it
            not any("table-ledger" in line or "table_ledger" in line
                    for line in _cli_arguments()),
            # v3 §8.2, IMP-PREFREEZE-SCRIPT: `--script` is refused pre-freeze at
            # EVERY target, not only the default one, and takes no interpreter
            _refused(EvWidenError, lambda: write_launch_script(scratch)),
            _refused(EvWidenError, lambda: write_launch_script(None)),
            _no_parameter(write_launch_script, "python", "kwargs"),
            _no_parameter(launch_script, "python", "kwargs"),
            not (scratch / LAUNCH_NAME).exists(),
        ])
        row("L18", "§2.3", "the frozen constants are not overridable",
            "attempt to pass a different B, alpha seed, MC_BOOT, MC_SEED, K, "
            "e*, replicate count or shard count through every public surface "
            "and CLI flag; require `n_sims`, the simulation seed and the chunk "
            "size to be absent from every table surface and resolved from the "
            "frozen law; and require `--limit` to name nothing but §8.4 "
            "step 2", l18, detail={"frozen_budget": frozen_budget})

    # the refusal inventory closes the set the document wrote (§7.1)
    if len(refusals) != 27:                            # pragma: no cover
        rows.append({"id": "L0", "section": "§7.1",
                     "obligation": "27 named refusals",
                     "scenario": "count the EvWidenError subclasses",
                     "ok": False, "detail": sorted(refusals)})
    assert list(inspect.signature(leaguesim.simulate).parameters)[:6] == [
        "arm", "state", "book_or_provider", "n_sims", "seed", "chunk_size"]
    return rows


def assert_implements_document() -> list[dict[str, Any]]:
    """§8.3 step 2's binding order, enforced: no freeze block before conformance.

    "**`--freeze-block` refuses to render** while the conformance report has a
    red row, while §7.4's ancestry test is absent, or while §6.3's table is
    unreproduced. A hash table committed over code that does not implement the
    document freezes the wrong thing, which is the one thing a hash table must
    never do."
    """
    # v3 §8.5: a row is green IFF its own committed pytest test is present and
    # passed in the artifact that run produced. The harness's own execution of
    # the scenarios still happens — it is what the eighteen tests call — but it
    # is not what certifies the freeze.
    artifact = assert_conformance_artifact()
    report = implementation_report()
    ids = [r["id"] for r in report]
    if ids != list(CONFORMANCE_ROWS):
        raise EvWidenError(
            f"refusing to render §8.3 step 2's freeze block: §8.5's report "
            f"carries {ids} and this document fixes exactly "
            f"{list(CONFORMANCE_ROWS)}. A nonempty all-green SUBSET is a "
            "refusal, not a pass.")
    broken = [r for r in report if not r["ok"]]
    if broken:
        detail = "; ".join(f"{r['id']} ({r['section']}): {r['obligation']}"
                           for r in broken)
        raise EvWidenError(
            "refusing to render §8.3 step 2's freeze block: this harness does "
            f"not yet implement the document — {detail}. §8.3 step 1: the "
            "harness is revised and audited, §8.5's conformance report must be "
            "green on BEHAVIOURAL predicates, and only then may step 2's block "
            "be rendered. A hash table committed over code that does not "
            "implement the document freezes the wrong thing, which is the one "
            "thing a hash table must never do."
            + ("" if not any(r["id"] == "L16" for r in broken) else
               " On the power numbers specifically (L16), §6.3 makes the "
               "committed implementation's numbers the document's numbers: "
               "correct §6.3's table before the freeze commit, or find what in "
               "the construction moved."))
    return report


def freeze_block(corpus: pd.DataFrame | None = None,
                 played: pd.DataFrame | None = None,
                 ledger: dict[str, set[str]] | None = None,
                 table: Sequence[dict[str, Any]] | None = None,
                 ) -> str:
    """§8.3 step 2's follow-up commit, RENDERED BY THE HARNESS'S OWN CODE.

    §8.3 asks that commit for five things: the **harness hash table** ("file,
    line count and SHA-256 for each of `epl/evwiden.py` and
    `epl/tests/test_evwiden.py`, and the schema identifier `epl-evwiden-2`");
    the **membership digests** ("the 85 thin fixture keys, the 52 treated keys,
    the 51 newly-flagged club-cutoff cells, the 78 fit openings, the 15 treated
    and 17 untouched table cells, and BOTH per-label censuses of §3.3, each
    serialised canonically and hashed, recomputed by the harness's own code from
    the pinned artifacts"); the four pinned artifact digests of §0.1 and
    `realised_config_sha256`; the **enumeration of every pre-freeze pass**
    actually run, complete; and the **conformance report of §8.5, all rows
    green**.

    Every one of those is computed here, so the freeze commit is a paste rather
    than a transcription. A transcribed digest is a digest with a typo in it,
    and §8.3's whole point is that "the design was fixed first" be checkable by
    a reader who runs `shasum` — which it is not if the recorded hash and the
    file disagree because somebody's clipboard truncated a hex string.

    **It refuses to render** "while the conformance report has a red row, while
    §7.4's ancestry test is absent, or while §6.3's table is unreproduced. A
    hash table committed over code that does not implement the document freezes
    the wrong thing, which is the one thing a hash table must never do."

    **There is no bypass parameter, and this function computes every input it
    renders.** v2's harness carried ``check_implementation=False``, which
    rendered the block over a red report; the review's NEW-B4 named it, so it
    went — and two survived it. ``power=`` reached
    :func:`power_reproduces` through the conformance report, and the in-tree
    audit rendered this block in 11.5 s from a fabricated six-row object with
    all eighteen rows green, L16 among them. ``pre_freeze_runs=`` replaced §8.3's
    "enumeration of every pre-freeze pass actually run, complete" with the
    caller's own string. Both defeat §8.6 condition (5), which reads this
    block's conformance table back to establish the freeze state: a
    bypass-rendered block becomes the committed evidence for its own freeze
    state. §8.5's precondition is unconditional, so this function consumes the
    report through :func:`assert_implements_document` and through nothing else,
    the report computes its own power run from :func:`committed_power_run`, and
    the enumeration is :data:`PRE_FREEZE_RUNS` and cannot be anything else.

    This function READS the pinned artifacts and fits nothing.
    """
    # §8.3: the census is checked FIRST. It scopes this document's whole table
    # leg (§0.6), so a block rendered over a record that is not the record is a
    # hash table for a design the measurement no longer supports — the question
    # comes before the conformance of the code that answers it.
    feasibility = assert_feasibility_permits_a_freeze()
    report = assert_implements_document()
    artifact = conformance_artifact_status()
    corpus = load_corpus() if corpus is None else corpus
    played = load_archive() if played is None else played
    ledger = load_walk_ledger() if ledger is None else ledger
    if table is None:
        from epl import baseline

        table = table_cells(baseline.load_matches(), played)
    digests = membership_digests(corpus, played, ledger, table=table)

    lines = [
        "### §8.3 step 2 — the harness hashes, the frozen membership and the "
        "conformance report",
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
             "table_untouched"),
            # the adjudication's F6: the EXACT schedule — season, label, cutoff
            # DATE and treated-club identity — so §8.6 condition (3)'s equality
            # is an equality about the thirty-two cells the read-only pass
            # measured and not about counts that happen to agree
            ("the exact schedule: season, label, cutoff date, treated clubs "
             "(§3.3)", "table_cells", "table_schedule"))
    for label, count_key, digest_key in rows:
        count = digests["counts"].get(count_key)
        digest = digests["digests"].get(digest_key)
        if count is None or digest is None:
            continue
        lines.append(f"| {label} | {count} | `{digest}` |")
    census = assert_table_census(table)
    lines += [
        f"| the membership as one object | — | "
        f"`{digests['digests']['membership']}` |",
        f"| the per-label treated census (§3.3) | "
        f"{json.dumps(census['by_label'])} | "
        f"`{_digest_list(f'{k}={v}' for k, v in sorted(census['by_label'].items()))}` |",
        # v3 §8.3: the block carries "the three excluded cell keys of §0.6, and
        # BOTH per-label censuses". The CELL census is the pin v2 never needed,
        # and after §0.6 §4.1's ground is a claim about the two together.
        f"| the per-label CELL census (§3.3) | "
        f"{json.dumps(census['cells_by_label'])} | "
        f"`{_digest_list(f'{k}={v}' for k, v in sorted(census['cells_by_label'].items()))}` |",
        # ...with the `|` in each key ESCAPED. A cell key is `season|label`,
        # and an unescaped pipe inside a markdown cell splits the row — which
        # would leave §8.6 condition (3) reading a membership table whose
        # columns had shifted. §9.3's tally names carry the same escape for the
        # same reason.
        f"| the cells §0.6 measured as UNPRICEABLE | "
        f"{len(EXCLUDED_CELLS)} — "
        f"{', '.join(k.replace('|', chr(92) + '|') for k in EXCLUDED_CELLS)} | "
        f"`{_digest_list(EXCLUDED_CELLS)}` |",
        "",
        "| pinned artifact | SHA-256 |",
        "|---|---|",
        f"| `{paths.rel(CORPUS_PATH)}` | `{CORPUS_SHA256}` |",
        f"| `{paths.rel(ARCHIVE_PATH)}` | `{ARCHIVE_SHA256}` |",
        f"| `{paths.rel(WALK_LEDGER_PATH)}` | `{WALK_LEDGER_SHA256}` |",
        f"| `{paths.rel(CONFIG_PATH)}` | `{CONFIG_SHA256}` |",
        f"| the realised configuration (§0.1) | `{REALISED_CONFIG_SHA256}` |",
        "",
        "Pre-freeze passes authorised under v3 and enumerated (§8.2 — all six "
        "fit nothing and simulate nothing; v3 authorises no pass that could "
        "enter an estimand):",
        "",
    ]
    for run in PRE_FREEZE_RUNS:
        lines.append(f"* {run}")
    lines += [
        "",
        "Prior history — passes run under an EARLIER document, enumerated here "
        "because §8.3 asks for every pre-freeze pass actually run and because "
        "this document is scoped by what one of them measured (§0.6). They are "
        "**not** authorised by v3 and §10 makes running one under this "
        "document an invalidation:",
        "",
    ]
    for run in PRIOR_PASSES:
        lines.append(f"* {run}")
    lines += [
        "",
        f"| §0.6's census record (§0.1's pin, bound here) | value |",
        "|---|---|",
        f"| path (gitignored, on this machine) | `{feasibility['record']}` |",
        # adjudication F13: the committed copy of the same bytes, so a reader of
        # the REPOSITORY can inspect the census this document is scoped by —
        # and recover it — rather than take a digest of a file only one machine
        # holds
        f"| path (COMMITTED, byte-identical) | `{feasibility['committed']}` |",
        f"| SHA-256 (both) | `{feasibility['sha256']}` |",
        f"| bytes | {feasibility['bytes']} |",
        f"| cells attempted | {feasibility['cells_attempted']} |",
        f"| priceable | {feasibility['n_priceable']} |",
        f"| unpriceable | {feasibility['n_unpriceable']} — "
        + "; ".join(f"{k.replace('|', chr(92) + '|')} "
                    f"({EXCLUDED_CELL_DETAIL[k]['fixture']}, mass "
                    f"{EXCLUDED_CELL_DETAIL[k]['excluded_mass']} vs the "
                    f"{EXCLUDED_CELL_DETAIL[k]['ceiling']} A1 ceiling)"
                    for k in feasibility["unpriceable"]) + " |",
        "",
        "The conformance report of §8.5 — every row a scenario that fails under "
        "its own defect class, and every row read from the pytest run below "
        "rather than from anything this renderer computed:",
        "",
        f"| §8.5's pytest artifact | value |",
        "|---|---|",
        f"| path | `{artifact['path']}` |",
        f"| SHA-256 | `{artifact['sha256']}` |",
        f"| tests passed | {artifact['count']} of "
        f"{len(CONFORMANCE_ROWS)} |",
        f"| test ids | " + "; ".join(f"`{i}`" for i in artifact["test_ids"])
        + " |",
        "",
        "| row | § | obligation | green |",
        "|---|---|---|---|",
    ]
    for entry in report:
        lines.append(f"| {entry['id']} | {entry['section']} | "
                     f"{entry['obligation']} | "
                     f"{'yes' if entry['ok'] else 'NO'} |")
    lines.append("")
    lines.append("*If any hash differs at the time the run is executed, it is "
                 "not the run this document preregisters.*")
    return "\n".join(lines) + "\n"


#: v3 §8.3: the block refuses to render while §0.6's census record is absent,
#: digest-mismatched, incomplete, or reporting a priceable set that is not
#: exactly this document's 32 cells. v2's block refused over an INFEASIBLE
#: census, which was the right refusal for a document claiming thirty-five; v3
#: claims thirty-two BECAUSE three cells are unpriceable, so the condition
#: inverts. There is no "NOT RUN" state any more: the pass ran, under v2, and
#: this document is scoped by what it measured.
FEASIBILITY_ABSENT = "the census record is absent"


class FeasibilityRecordMismatch(EvWidenError):
    """§7.1 / §0.1: §0.6's census record is not the record this document is
    scoped by.

    > This document's table leg is SCOPED by that record, so a record that is
    > not the record scopes nothing.

    Fires when the record is absent, fails the digest §8.3's freeze block binds,
    reports ``completed: false``, or reports a priceable census that is not
    exactly v3's 32 cells. **A census that suddenly prices all thirty-five is as
    much a refusal as one that prices thirty-one** — either way this document is
    scoped against a measurement that is no longer the measurement.
    """


def feasibility_status() -> dict[str, Any]:
    """§0.6's census record, read and CHECKED against the pins that scope v3.

    The record is READ-ONLY to this document: nothing in this module writes it,
    and v3 §8.2 authorises no pass that could (P5-B2). What this function does
    is establish whether the file on disk is the file §0.1 pins and §8.3 binds,
    and it reports rather than raises so that the freeze renderer and the
    conformance row can each say which condition failed.
    """
    out: dict[str, Any] = {"record": paths.rel(FEASIBILITY_RECORD),
                           "committed": paths.rel(FEASIBILITY_COMMITTED),
                           "expected_sha256": FEASIBILITY_SHA256,
                           "expected_bytes": FEASIBILITY_BYTES}
    if not FEASIBILITY_RECORD.exists():
        return {**out, "present": False, "ok": False, "why": FEASIBILITY_ABSENT}
    raw = FEASIBILITY_RECORD.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    out.update({"present": True, "sha256": sha, "bytes": len(raw)})
    if sha != FEASIBILITY_SHA256 or len(raw) != FEASIBILITY_BYTES:
        return {**out, "ok": False,
                "why": (f"the record's digest is {sha[:12]}… over {len(raw)} "
                        f"bytes and §0.1 pins {FEASIBILITY_SHA256[:12]}… over "
                        f"{FEASIBILITY_BYTES}")}
    try:
        rec = json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:  # pragma: no cover
        return {**out, "ok": False, "why": f"the record is not readable: {exc}"}
    priceable = sorted(str(k) for k in (rec.get("priceable") or ()))
    unpriceable = sorted(str(u.get("key")) for u in (rec.get("unpriceable") or ()))
    out.update({"completed": bool(rec.get("completed")),
                "feasible": bool(rec.get("feasible")),
                "cells_attempted": rec.get("cells_attempted"),
                "cells_expected": rec.get("cells_expected"),
                "n_priceable": len(priceable), "n_unpriceable": len(unpriceable),
                "priceable": priceable, "unpriceable": unpriceable})
    want_priceable = sorted(_v3_priceable_keys())
    want_unpriceable = sorted(FEASIBILITY_EXPECTED_UNPRICEABLE)
    if not out["completed"]:
        return {**out, "ok": False,
                "why": (f"the record says the pass did NOT complete "
                        f"({out['cells_attempted']} of "
                        f"{out['cells_expected']} cells attempted)")}
    if int(rec.get("cells_attempted") or 0) != FEASIBILITY_EXPECTED_ATTEMPTED:
        return {**out, "ok": False,
                "why": (f"the record attempted {out['cells_attempted']} cells "
                        f"and v2 §8.2's pass attempted "
                        f"{FEASIBILITY_EXPECTED_ATTEMPTED}")}
    if priceable != want_priceable or unpriceable != want_unpriceable:
        return {**out, "ok": False,
                "why": (f"the record's census is {len(priceable)} priceable / "
                        f"{len(unpriceable)} unpriceable and v3 is scoped to "
                        f"{len(want_priceable)} / {len(want_unpriceable)}; "
                        f"unexpected priceable "
                        f"{sorted(set(priceable) ^ set(want_priceable))[:4]}")}
    # ---- the COMMITTED copy (adjudication F13, V3-I3) --------------------
    # The pinned digest makes the gitignored record tamper-evident and nothing
    # more: a repository-only reader "has neither the evidence bytes nor an
    # archival locator [...] and cannot recover the file if deleted". The same
    # bytes are committed under `reports/evidence/`, checked here on the same
    # terms, and bound beside the local path in the freeze block — because a
    # scope that rests on a file only one machine holds rests on that machine.
    if not FEASIBILITY_COMMITTED.exists():
        return {**out, "committed_ok": False, "ok": False,
                "why": (f"{paths.rel(FEASIBILITY_COMMITTED)} is not on disk. "
                        "§0.6's census scopes this document's whole table leg, "
                        "and the COMMITTED copy is what lets a reader of the "
                        "repository inspect and recover it rather than take a "
                        "digest of a file only this machine holds.")}
    committed_raw = FEASIBILITY_COMMITTED.read_bytes()
    committed_sha = hashlib.sha256(committed_raw).hexdigest()
    out.update({"committed_sha256": committed_sha,
                "committed_bytes": len(committed_raw)})
    if committed_sha != FEASIBILITY_SHA256 or \
            len(committed_raw) != FEASIBILITY_BYTES:
        return {**out, "committed_ok": False, "ok": False,
                "why": (f"the committed copy's digest is {committed_sha[:12]}… "
                        f"over {len(committed_raw)} bytes and §0.1 pins "
                        f"{FEASIBILITY_SHA256[:12]}… over {FEASIBILITY_BYTES}: "
                        f"{paths.rel(FEASIBILITY_COMMITTED)} is not the census "
                        "this document is scoped to.")}
    return {**out, "committed_ok": True, "ok": True, "why": None}


def _v3_priceable_keys() -> list[str]:
    """v3 §3.3's 32 keys, in schedule order, from the module's own constants.

    Written out here rather than derived from the archive because
    :func:`feasibility_status` runs on machines that have the record and not the
    parquet, and because the keys are a property of the DOCUMENT (§0.6 names the
    three exclusions) rather than of a file.
    """
    from epl import simretro

    return [f"{s}|{lab}" for s in simretro.SEASONS
            for lab in simretro.COMPARISON_CUTOFFS
            if f"{s}|{lab}" not in EXCLUDED_CELLS]


def assert_feasibility_permits_a_freeze() -> dict[str, Any]:
    """v3 §8.3, at the one moment the census decides anything.

    > **§0.6's feasibility census record is absent, fails its pinned digest,
    > says it did not complete, or reports a priceable census that is not
    > exactly this document's thirty-two cells.** v2's block refused over an
    > *infeasible* census, which was the right refusal for a document claiming
    > thirty-five. This document claims thirty-two **because** three cells are
    > unpriceable, so the condition inverts: the block refuses unless the record
    > says exactly that, cell for cell.

    The review's P5-B4 found v2's `freeze_block` indifferent to the record while
    the feasibility context refused to open after the freeze, so freezing first
    could "immortalize an unrun, possibly unrunnable design". Under v3 there is
    no pass left to run, and the failure mode inverts with it: the danger is not
    a design frozen before its census exists but a design frozen against a census
    it is not scoped to. That is what this refuses.
    """
    status = feasibility_status()
    if not status["ok"]:
        raise FeasibilityRecordMismatch(
            f"refusing to render §8.3's freeze block: {status['record']} — "
            f"{status['why']}. v3 §0.6's census is what scopes this document's "
            "table leg to 32 cells, 15 treated and 17 untouched, and §0.1 pins "
            "the record by digest precisely because `data/` is gitignored. A "
            "record that is not the record scopes nothing, and a hash table "
            "committed over it would freeze a design against a measurement "
            "that is no longer the measurement.")
    return status



def require_harness_freeze(sources: Sequence[Path] | None = None,
                           ) -> dict[str, Any]:
    """Refuse anything that would score fits taken before §8.3's freeze commit.

    Raised as the base :class:`EvWidenError`: §10 pre-states this condition as an
    invalidation but §7.1 never gave it a typed name, and this module does not
    invent one after the fact.
    """
    sources = _only_the_prereg(sources, "HEAD", "require_harness_freeze")
    status = harness_freeze_status(sources)
    if not status["frozen"]:
        raise EvWidenError(
            "the harness-hash freeze of §8.3 is not in place — " + status["why"]
            + ". The harness may be audited on SYNTHETIC corpora to a scratch "
            "directory, but its result may not be merged or scored until the "
            "hash table and the membership digests are committed.")
    return status


# ==========================================================================
# 17. THE DETACHED LAUNCH — §2.4's runner, GENERATED rather than committed
# ==========================================================================

#: The interpreter the generated launcher runs, fixed. The review's P5-B6:
#: ``launch_script(python=...)`` "accepts an arbitrary interpreter/command, and
#: `write_launch_script(**kwargs)` forwards it into the post-freeze production
#: launcher" — a public parameter injecting an alternative implementation into
#: the one artifact §2.4 generates from the hashed module precisely so that
#: nothing outside the hash table can decide what runs.
LAUNCH_PYTHON = ".venv/bin/python"

#: §8.4 step 2's scratch target, named here rather than left to the operator.
#: The step writes its rows OUTSIDE the preregistered run directory and its
#: MARKER inside it, and "a step whose only legal target the guard refuses is
#: not a step; it is a sentence" (v3 §8.4). Naming it in the generated launcher
#: is what makes the step a command rather than a comment.
SCRATCH_STEP2_NAME = "data/epl/fit/evwiden_step2_scratch"


def launch_script(directory: Path | str | None = None,
                  shards: int = SHARDS) -> str:
    """The nohup'd runner, as text. §8.3 names two harness files and this is not
    a third.

    **It emits exactly §8.4's five steps, in §8.4's order** (conformance row
    L9). v1's launcher ran canary → shards → table → merge: table BEFORE merge,
    no step-2 marker anywhere, and — because the once-only results canary was
    its first line — it would have re-run that canary after a manual step 2.

    **`SHARDS = 4` is enforced, not defaulted.** "A run at any other shard count
    is not the run this document preregisters", so a different count is refused
    here rather than generated.

    A loose ``run_evwiden.sh`` would be code whose bytes nothing hashes, sitting
    outside the §8.3 hash table while being able to change which shards run and in
    what order. Generating it from the hashed module instead makes the launcher
    a function of the frozen harness, and the launcher itself lands under
    ``data/epl/fit/evwiden/`` — inside §8.3's write set.

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
    shards = int(shards)
    if shards != SHARDS:
        raise EvWidenError(
            f"refusing to generate a launcher for {shards} shard(s). §8.4: "
            f"'`SHARDS = {SHARDS}` is enforced, not defaulted. `--shards` may "
            "not be passed a different value: the CLI refuses it, the launcher "
            "generates four, and the MANIFEST's shard filenames are the four of "
            "§9.3.' A run at any other shard count is not the run this document "
            "preregisters.")
    seq = f"{rel_dir}/sequence"
    lines = [
        "#!/bin/sh",
        "# GENERATED by `python -m epl.evwiden --script`. Do not edit: §8.3",
        "# names epl/evwiden.py and epl/tests/test_evwiden.py as the harness",
        "# files, and this launcher's bytes are a function of theirs.",
        "#",
        "# Launch DETACHED, from a script file and never a stdin heredoc — macOS",
        "# spawn re-imports <stdin> and kills the gate's parallel leg:",
        f"#     nohup sh {rel_dir}/{LAUNCH_NAME} > {rel_dir}/run.log 2>&1 &",
        "set -u",
        f"cd {paths.REPO_ROOT}",
        "export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1",
        "export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1",
        "export PYTHONPATH=src:.",
        f'PY="{LAUNCH_PYTHON}"',
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
        "need_marker() {",
        "  # §8.4: each step refuses unless its predecessor's completion marker",
        "  # exists. The harness refuses too — this is the launcher saying WHY",
        "  # before it spends an hour finding out.",
        f'  if [ ! -f "{seq}/$1.json" ]; then',
        '    echo "STOP: SequenceViolation — $2 needs $1'"'"'s completion marker at '
        f'{seq}/$1.json."',
        '    exit 2',
        "  fi",
        "}",
        "",
        '# STEP 1 — the post-freeze RESULTS CANARY. This is the first',
        '# post-freeze act and it performs the FIRST REAL FITS of this',
        '# document: `walkforward.point_in_time_canary` calls `_forecasts`',
        '# four times. §8.7 comes into force at its completion, not at the',
        '# single-opening exercise. `PASS: false` on any leg stops the',
        '# experiment and the failure publishes.',
        '#   marker: sequence/step1_results_canary.json',
        'run_step canary $PY -u -m epl.evwiden --canary --dir "$DIR"',
        "",
        '# STEP 2 — the single-opening exercise, into a SCRATCH directory',
        '# outside this one. Its numbers enter no estimand and its rows are',
        '# never merged; it exercises the one path no test can execute without',
        '# a real fit. Its MARKER is written to "$DIR" and step 3 refuses',
        '# without it. It is a COMMAND and it runs here: the review found the',
        '# launcher carrying only comments for this step while the sequence',
        '# guard refused the scratch --dir the step is REQUIRED to use, so the',
        '# step was not executable as written (N-RH-FIRST-ACT).',
        '#   marker: sequence/step2_single_opening.json',
        'need_marker step1_results_canary "step 2, the single opening"',
        f'SCRATCH="{SCRATCH_STEP2_NAME}"',
        'mkdir -p "$SCRATCH"',
        '# §8.4: "the step\'s scratch directory carries its own copy of step 1\'s',
        '# canary record". §7.3 reads the canaries from their WRITTEN record so',
        '# the order holds across processes, and `require_run_preconditions`',
        '# looks for that record in the directory it was given. Without this',
        "# copy the step refuses its own canary's absence and is not executable",
        '# as written (N-RH-FIRST-ACT; adjudication F2).',
        f'cp "$DIR/{CANARY_NAME}" "$SCRATCH/{CANARY_NAME}"',
        'run_step single_opening $PY -u -m epl.evwiden '
        '--run --limit 1 --dir "$SCRATCH"',
        "",
        "# STEP 3 — the four shards, SEQUENTIALLY (§2.4: parallel shards crash",
        "# on the featpanel .tmp rename race in the locked path, and the fix is",
        "# held for lock-v11). Refuses without step 2's marker.",
        '#   marker: sequence/step3_shards.json',
        'need_marker step2_single_opening "step 3, the four shards"',
    ]
    for i in range(shards):
        lines.append(
            f'run_step shard_{i:02d}_of_{shards:02d} $PY -u -m epl.evwiden '
            f'--run --shard {i}/{shards} --dir "$DIR"')
    lines += [
        "",
        "# STEP 4 — the merge. Refuses without step 3's marker. The merged key",
        "# set must be exactly the pre-stated keys — not a superset, not a",
        "# subset — and §2.3's structural-zero guard runs here, in BOTH",
        "# directions. The evidence files are written whichever way it falls.",
        '#   marker: sequence/step4_merge.json',
        'need_marker step3_shards "step 4, the merge"',
        f'run_step merge $PY -u -m epl.evwiden --merge --shards '
        f'{shards} --dir "$DIR"',
        "",
        "# STEP 5 — the parity oracle at all 32 priceable cells to COMPLETION,",
        "# and only then the table's 32 cells (§3.3). Refuses without step 4's",
        "# marker.",
        "# §2.4's budget for this leg: 64 fits and 96 runs of 20,000 seasons,",
        "# bounded by ~4 hours.",
        '#   marker: sequence/step5_parity.json',
        'need_marker step4_merge "step 5, the parity oracle and the table"',
        'run_step table $PY -u -m epl.evwiden --table --dir "$DIR"',
        "",
        "# PUBLICATION — §9's evidence files, written once gate (iv) exists.",
        "# The merge at step 4 writes its own product,",
        "# data/epl/fit/evwiden.json; the evidence carries the table gate, so",
        "# it cannot be written before step 5 has produced one. §4.4: the",
        "# result publishes either way, and there is no file drawer. This",
        "# fits nothing and simulates nothing — it re-scores what steps 3-5",
        "# already wrote.",
        'need_marker step5_parity "the evidence"',
        f'run_step evidence $PY -u -m epl.evwiden --merge --shards '
        f'{shards} --evidence --dir "$DIR"',
        "", 'echo "[launch] done"', ""]
    return "\n".join(lines)


def write_launch_script(directory: Path | str | None = None,
                        shards: int = SHARDS) -> Path:
    """Write the launcher — and never before §8.3's freeze commit.

    §8.2's enumeration of pre-freeze passes is complete and closed, and none of
    its entries writes anything inside the repository. The review's
    IMP-PREFREEZE-SCRIPT found the enumeration FALSE anyway: this function
    refused the default production target pre-freeze but "permits a scratch
    directory and writes inside the repository if that scratch path is outside
    the narrowly tested evwiden directories". A path-keyed refusal cannot make a
    statement about WRITES true, because the statement is not about paths.

    v3 §8.2 rules it in two clauses and both are here:

    > **`--script` writes the launcher only AFTER the freeze commit.** It is a
    > post-freeze operational artifact — §8.4 step 1 is the first thing the
    > launcher runs — so a pre-freeze `--script` is refused at **every** target,
    > not only the default one. The refusal is on the freeze state and not on
    > the path.
    >
    > **After the freeze, `--script` writes to the preregistered run directory
    > and nowhere else.** [...] and it takes no interpreter, no command prefix
    > and no forwarded keyword arguments: [...] a caller who could name the
    > Python that runs it could substitute an alternative implementation into
    > every post-freeze step at once.
    """
    directory = Path(directory) if directory is not None else EVWIDEN_DIR
    if not _frozen_now():
        raise EvWidenError(
            f"refusing to write {LAUNCH_NAME} to {paths.rel(directory)} before "
            "§8.3's freeze commit, and the refusal is on the FREEZE STATE and "
            "not on the path: §8.2's enumeration of pre-freeze passes is "
            "complete and none of its six entries writes anything inside the "
            "repository, so a pre-freeze --script at ANY target is a write the "
            "enumeration does not carry. The launcher is a post-freeze "
            "operational artifact — §8.4 step 1 is the first thing it runs — "
            "and there is nothing for it to run until the freeze exists.")
    if directory.resolve() != EVWIDEN_DIR.resolve():
        raise EvWidenError(
            f"refusing to write {LAUNCH_NAME} to {paths.rel(directory)}: §8.2 "
            "gives the post-freeze launcher one target, "
            f"{paths.rel(EVWIDEN_DIR / LAUNCH_NAME)}, and no other. The "
            "launcher's contents are a function of the frozen constants and of "
            "the harness bytes §8.3 hashes; a copy somewhere else is a second "
            "runner whose bytes nothing in the hash table describes.")
    path = directory / LAUNCH_NAME
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(launch_script(directory, shards))
    path.chmod(0o755)
    return path


# ==========================================================================
# 18. THE CLI
# ==========================================================================

def default_table_cells(played: pd.DataFrame | None = None,
                        ) -> list[dict[str, Any]]:
    """§3.3's 32 cells from the pinned archive — read-only, fits nothing.

    §8.2 pass 1 authorises `--membership` and `--plan` to read the pinned
    corpus, archive and ledger and compute "§2.2's cells, §2.3's population,
    §3.3's TABLE CELLS and the digests the freeze commit records". The table
    cells were the half the CLI omitted.
    """
    from epl import baseline

    return table_cells(baseline.load_matches(), played)


def _plan(corpus: pd.DataFrame, played: pd.DataFrame,
          ledger: dict[str, set[str]], shards: int,
          directory: Path,
          table: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    table = default_table_cells(played) if table is None else table
    frozen = membership_digests(corpus, played, ledger, table=table)
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
        # §2.4's table-leg budget: `ArchiveRunner` owns its own fit and exposes
        # no posterior or ParticleBook for reuse, so the parity oracle cannot
        # ride the new runner's fits and needs its own 32.
        "budget": {"match_fits": len(points),
                   "table_fits": 2 * EXPECTED_TABLE_CELLS,
                   "table_parity_fits": EXPECTED_TABLE_CELLS,
                   "table_runner_fits": EXPECTED_TABLE_CELLS,
                   "table_simulations": 3 * EXPECTED_TABLE_CELLS,
                   # §2.4 counts the results canary's four fits and the
                   # single-opening exercise, "because they are real fits on
                   # the real archive: §8.4 makes them the first two steps of
                   # the frozen sequence, and a budget that omits them would
                   # understate both the clock and the moment §8.7's regime
                   # comes into force". v1 reported 148 and was five fits short.
                   "canary_fits": 4, "single_opening_fits": 1,
                   "total_fits": (4 + 1 + len(points)
                                  + 2 * EXPECTED_TABLE_CELLS),
                   # v3 §2.4 states the WHOLE-LIFECYCLE figure as well as the
                   # post-freeze one, which v2's did not: the review's P5-I1
                   # found v2 labelling its post-freeze legs "whole experiment"
                   # while v2 §8.2 pass 7 had already spent 35 real fits and 35
                   # real simulations on the protected control path (§0.6).
                   # They are PRIOR HISTORY for this document (§8.1) and they
                   # are counted here rather than dropped.
                   "prior_history_fits": FEASIBILITY_EXPECTED_ATTEMPTED,
                   "prior_history_simulations": FEASIBILITY_EXPECTED_ATTEMPTED,
                   "lifecycle_fits": (4 + 1 + len(points)
                                      + 2 * EXPECTED_TABLE_CELLS
                                      + FEASIBILITY_EXPECTED_ATTEMPTED),
                   "lifecycle_simulations": (3 * EXPECTED_TABLE_CELLS
                                             + FEASIBILITY_EXPECTED_ATTEMPTED),
                   "bound": "the table leg is bounded by ~4 hours (§2.4)",
                   "shards": SHARDS,
                   "note": "§2.4: shards run SEQUENTIALLY and the run may not "
                           "be thinned — dropping cutoffs, fixtures, cells or "
                           "grid points to fit a clock is an amendment, not an "
                           "optimisation, and §3.3's closure 2 folds sampling the "
                           "parity oracle into that refusal."},
    }


def _frozen_now() -> bool:
    """Has §8.3's freeze commit landed for THESE bytes? One place, one answer."""
    return bool(harness_freeze_status()["frozen"])


def _run_all_canaries(corpus: pd.DataFrame, played: pd.DataFrame,
                      ledger: dict[str, set[str]], *,
                      results_canary: bool = True,
                      directory: Path | str | None = None) -> dict[str, Any]:
    """§7.3's canaries, in one record, all of them able to fail.

    §8.4: the RESULTS canary is **step 1**, the first post-freeze act, and it
    performs the first real fits of this document — `walkforward
    .point_in_time_canary` calls `_forecasts` four times. It is therefore gated
    by :func:`assert_may_fit` exactly as the sampler legs are, and §8.7's regime
    comes into force at its completion rather than at the single-opening
    exercise. No freeze-state boolean reaches it: §8.6 makes that the guard's
    own finding.

    The EVIDENCE canary is not a fit and is authorised pre-freeze by name under
    §8.2 (pass 2), with any point-in-time store built in a temporary root.
    """
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

    # The store root is a TEMPORARY directory, and that is a §8.2 requirement
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
        # §8.6's closure: the guard lives inside `run_canary` now, so the four
        # real fits are gated wherever they are called from and not only here.
        try:
            record["results"] = run_canary(played=played, corpus=corpus,
                                           directory=directory)
        except CanaryFailed as exc:
            record["results"] = dict(getattr(exc, "record", None) or {})
            record["PASS"] = False
            record["results_canary_run"] = True
            exc.record = record                            # type: ignore[attr-defined]
            raise
        record["may_fit"] = {"guarded": True,
                             "where": "epl.evwiden.run_canary"}
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
                    help="print §8.3 step 2's frozen membership digests, "
                         "recomputed from the pinned artifacts; fits nothing")
    ap.add_argument("--canary", action="store_true",
                    help="§7.3's canaries; the first thing in RUN_ORDER")
    ap.add_argument("--run", action="store_true",
                    help="Arm A's fits — the identity control runs first, "
                         "inside every fit")
    ap.add_argument("--table", action="store_true",
                    help="§3.3's table-retro leg: 32 cells, both arms")
    ap.add_argument("--merge", action="store_true",
                    help="verify every shard, then compute the estimand")
    ap.add_argument("--verify", action="store_true",
                    help="re-derive the published estimand from the committed "
                         "evidence and the shard ledgers; changes nothing")
    ap.add_argument("--evidence", action="store_true",
                    help="write §9's evidence files under reports/evidence/")
    ap.add_argument("--power", action="store_true",
                    help="§6's power simulation: prints the table and the "
                         "`power` object; fits nothing, simulates no season, "
                         "writes nothing")
    ap.add_argument("--conformance", action="store_true",
                    help="§8.5's conformance report: eighteen behavioural "
                         "rows, each executing a scenario that fails under its "
                         "own defect class")
    ap.add_argument("--feasibility", dest="feasibility", action="store_true",
                    help="print §0.6's census record status — present, digest, "
                         "completed, and whether its priceable set is exactly "
                         "v3's 32 cells. READ-ONLY: v3 authorises no "
                         "pre-freeze pass that fits or simulates, so there is "
                         "no command here that could produce a census")
    ap.add_argument("--freeze-block", dest="freeze_block", action="store_true",
                    help="print §8.3 step 2's hash table and membership digests, "
                         "recomputed from the pinned artifacts; fits nothing")
    ap.add_argument("--script", action="store_true",
                    help="write the detached-launch runner into the run "
                         "directory and print the nohup line")
    ap.add_argument("--shard", default=f"0/{SHARDS}",
                    help=f"i/{SHARDS} — this worker's slice of the fit points. "
                         f"§8.4 enforces N = {SHARDS}")
    ap.add_argument("--shards", type=int, default=SHARDS,
                    help="how many shards the merge must find. §8.4 ENFORCES "
                         f"this at {SHARDS} rather than defaulting to it: a run "
                         "at any other shard count is not the run this document "
                         "preregisters")
    # §8.4 step 2 is `--run --limit 1` and it is the ONLY population this flag
    # may name. The review's NEW-B1 found generic `--limit` able to truncate
    # step 3's real 78 openings: "Dropping cutoffs, fixtures, cells or grid
    # points to fit a clock is an amendment, not an optimisation" (§2.4), and a
    # deciding population a flag can shorten is not a preregistered one.
    ap.add_argument("--limit", type=int, default=None,
                    help="only `--run --limit 1`, which IS §8.4 step 2's "
                         "single-opening exercise. Any other value is refused "
                         "on every path")
    ap.add_argument("--partial-engine", dest="partial_engine",
                    action="store_true",
                    help="§8.2 pass 4: construction, fit_points, the enlarged "
                         "set, assert_cutoff_clean and assert_point_in_time at "
                         "the first opening, stopping before dcfit.fit_epl")
    ap.add_argument("--dir", dest="directory", default=None,
                    help="the run directory: the canary record and the shard "
                         f"ledgers (default {paths.rel(EVWIDEN_DIR)})")
    # §2.3: `B = 10,000` is frozen and IS NOT OVERRIDABLE. v1 carried a
    # `--n-boot` flag and passed it straight into `score_table`, `merge` and
    # `verify` without refusal. The flag is kept only so that passing it is a
    # STOP rather than an unrecognised-argument traceback.
    ap.add_argument("--n-boot", type=int, default=None,
                    help=argparse.SUPPRESS)
    ap.add_argument("--no-results-canary", action="store_true",
                    help="skip `walkforward.point_in_time_canary` (it refits); "
                         "the evidence canary still runs and still refuses")
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        index, count = (int(x) for x in str(args.shard).split("/"))
    except ValueError:
        print(f"STOP: --shard must be i/N, not {args.shard!r}", flush=True)
        return 2

    # §8.4: "**`SHARDS = 4` is enforced, not defaulted.** `--shards` may not be
    # passed a different value: the CLI refuses it, the launcher generates four,
    # and the MANIFEST's shard filenames are the four of §9.3." v1 accepted any
    # count here and in the launcher, so a two-shard run would have written two
    # ledgers the manifest's four-path list could never describe.
    if int(args.shards) != SHARDS or count != SHARDS:
        print(f"STOP: this experiment runs at exactly {SHARDS} shards, and was "
              f"asked for --shards {args.shards} / --shard {args.shard}. §8.4: "
              "a run at any other shard count is not the run this document "
              "preregisters, and §9.3's MANIFEST names the four shard files by "
              "name.", flush=True)
        return 2

    if args.limit is not None and not (args.run and int(args.limit) == 1):
        print(f"STOP: --limit {args.limit} is refused. §8.4 step 2 is "
              "`--run --limit 1` — one fit at the first opening by date, into a "
              "scratch directory, whose numbers enter no estimand — and that is "
              "the only population this flag may name. §2.4: 'Dropping "
              "cutoffs, fixtures, cells or grid points to fit a clock is an "
              "amendment, not an optimisation', and §3.3's closure 2 makes "
              "reducing the parity oracle's 32 cells the same thing.", flush=True)
        return 2

    if args.n_boot is not None:
        print(f"STOP: --n-boot is refused. §2.3 freezes B = {N_BOOT} and makes "
              "it not overridable: 'No CLI flag, keyword or environment "
              "variable may pass a different B, alpha, block definition or "
              "resampling seed into any deciding computation.'", flush=True)
        return 2

    directory = Path(args.directory) if args.directory else EVWIDEN_DIR
    # v3 §8.4, P5-B8: **the table ledger is RESOLVED and no flag names it.**
    # The CLI used to accept an arbitrary ledger path, and the table branch
    # checked only that step 4 preceded step 5 — performing the whole expensive
    # run and only THEN attempting the write-once step-5 marker. A caller who
    # had seen the first table's outcome could point at a second ledger, run the
    # leg again, and have the second outcome exist before the marker conflict
    # was raised: an outcome-conditioned second run of the deciding leg, wearing
    # the clothes of a path argument. It follows `--dir` so that §8.2's
    # synthetic audit keeps its own tree, and nothing else may name it.
    table_ledger = (TABLE_LEDGER if directory == EVWIDEN_DIR
                    else directory / TABLE_LEDGER.name)

    try:
        if args.script:
            path = write_launch_script(directory, args.shards)
            print(json.dumps({
                "written": paths.rel(path),
                "launch": f"nohup sh {paths.rel(path)} > "
                          f"{paths.rel(directory)}/run.log 2>&1 &",
                "note": "§2.4: a detached run goes through a nohup'd SCRIPT "
                        "FILE, never a stdin heredoc.",
            }, indent=2))

        if args.power:
            out = power_simulation(verbose=True)
            print("| scenario | rho | power at the bar | joint MDE (estimand) "
                  "| ratio to the bar | power at 2x the bar |")
            print("|---|---:|---:|---:|---:|---:|")
            for row in out["rows"]:
                mde = ("< -0.0200" if row["mde_estimand"] is None
                       else f"{row['mde_estimand']:.6f}")
                ratio = ("—" if row["ratio_to_bar"] is None
                         else f"{row['ratio_to_bar']:.2f}x")
                print(f"| {row['scenario']} | {row['rho']} | "
                      f"{row['power_at_bar']:.3f} | {mde} | {ratio} | "
                      f"{row['power_at_2x_bar']:.3f} |")
            print(json.dumps(power_reproduces(out), indent=2, default=str))

        if args.conformance:
            print(json.dumps(implementation_report(), indent=2, default=str))

        if args.freeze_block:
            print(freeze_block(), end="")

        if args.plan or args.membership:
            corpus, played = load_corpus(), load_archive()
            ledger = load_walk_ledger()
            assert_ledger_covers(corpus, ledger)
            # §8.2 pass 1: `--membership` and `--plan` compute §2.2's cells,
            # §2.3's population AND §3.3's table cells. All three are what the
            # freeze commit records, so all three are computed here.
            cells = default_table_cells(played)
            if args.membership:
                out = membership_digests(corpus, played, ledger, table=cells)
                out.pop("keys", None)
                print(json.dumps(out, indent=2, default=str))
            if args.plan:
                print(json.dumps(
                    _plan(corpus, played, ledger, max(count, args.shards),
                          directory, table=cells), indent=2, default=str))

        if args.partial_engine:
            print(json.dumps(partial_engine_pass(), indent=2, default=str))

        if args.feasibility:
            # READ-ONLY. v3 §8.2 authorises no pass that fits or simulates, so
            # there is nothing here that could produce a census — only a report
            # on whether the record on disk is the one §0.1 pins and §8.3 binds.
            print(json.dumps(feasibility_status(), indent=2, default=str))

        if args.canary:
            frozen_now = _frozen_now()
            _guard_ledger_location(directory / CANARY_NAME, frozen_now)
            # §8.4 step 1 runs ONCE. A step-1 marker of either kind means it
            # has already run, and NEW-B8's outcome-dependent retry channel is
            # exactly a second attempt after a first one failed.
            prior = read_sequence_marker(SEQUENCE_STEPS[0]) if frozen_now else None
            if prior is not None:
                raise SequenceViolation(
                    f"§8.4 step 1 has already run under this freeze "
                    f"({paths.rel(sequence_marker_path(SEQUENCE_STEPS[0]))}, "
                    f"complete={prior.get('complete', True)!r}). The results "
                    "canary is run ONCE, after the freeze commit, and its "
                    "result — including its failure — is published. A second "
                    "attempt is a retry conditioned on the first one's outcome; "
                    "if the experiment is to continue after a failed canary it "
                    "continues under a NEW dated pre-freeze note that says so "
                    "before the retry, not after it.")
            corpus, played = load_corpus(), load_archive()
            ledger = load_walk_ledger()
            try:
                record = _run_all_canaries(
                    corpus, played, ledger,
                    results_canary=not args.no_results_canary,
                    directory=directory)
            except CanaryFailed as exc:
                # §8.4 step 1: "`PASS: false` on any leg stops the experiment
                # and THE FAILURE PUBLISHES." It publishes BEFORE the raise:
                # NEW-B8 found a failed canary leaving no durable result and no
                # marker, so the run could simply be attempted again.
                failed = dict(getattr(exc, "record", None) or {})
                failed.setdefault("schema", SCHEMA_ID)
                failed["PASS"] = False
                failed["results_canary_run"] = not args.no_results_canary
                failed["failure"] = f"{type(exc).__name__}: {exc}"
                write_canaries(failed, directory / CANARY_NAME)
                if frozen_now and not args.no_results_canary:
                    write_sequence_marker(
                        SEQUENCE_STEPS[0], complete=False,
                        produced={"canary": paths.rel(directory / CANARY_NAME),
                                  "digest": sha256_file(directory / CANARY_NAME),
                                  "failure": failed["failure"],
                                  _PRODUCTS_KEY: product_digests(
                                      directory / CANARY_NAME)})
                raise
            write_canaries(record, directory / CANARY_NAME)
            # §8.4 step 1's completion marker. §8.7 comes into force HERE — the
            # canary's four fits are the first real fits of this document — so
            # the marker records the harness digests at that moment.
            if record.get("PASS") and not args.no_results_canary:
                write_sequence_marker(
                    SEQUENCE_STEPS[0],
                    produced={"canary": paths.rel(directory / CANARY_NAME),
                              "digest": sha256_file(directory / CANARY_NAME),
                              # §8.4's product bytes, re-hashed on every later
                              # read of this marker (adjudication F10)
                              _PRODUCTS_KEY: product_digests(
                                  directory / CANARY_NAME)})
            print(json.dumps({k: v for k, v in record.items() if k != "detail"},
                             indent=2, default=str))

        if args.run:
            corpus, played = load_corpus(), load_archive()
            ledger = load_walk_ledger()
            assert_ledger_covers(corpus, ledger)
            check_corpus_scores(corpus)
            frozen = harness_freeze_status()
            # §8.4: `--run --limit 1` IS step 2, the single-opening exercise,
            # and a full `--run` is step 3. Each refuses without its
            # predecessor's marker.
            step = (SEQUENCE_STEPS[1] if args.limit == 1 else SEQUENCE_STEPS[2])
            if args.limit == 1 and directory.resolve() == EVWIDEN_DIR.resolve():
                # v3 §8.4, N-RH-FIRST-ACT: "**The step's own scratch target is
                # part of the step.** `--run --limit 1` requires a `--dir` that
                # is NOT the preregistered run directory, refuses one that is,
                # and writes its marker to the preregistered directory
                # regardless of where its rows went. A step whose only legal
                # target the guard refuses is not a step; it is a sentence."
                print("STOP: §8.4 step 2 runs into a SCRATCH directory outside "
                      f"the preregistered run directory ({paths.rel(EVWIDEN_DIR)}) "
                      "— 'its numbers enter no estimand; its rows are never "
                      "merged' — and its marker is written to the preregistered "
                      "directory regardless. Pass --dir <scratch>. The "
                      "generated launcher names one and creates it.", flush=True)
                return 2
            require_run_preconditions(directory,
                                      require_results=bool(frozen["frozen"]),
                                      step=step)
            assert_blas_pinned("the evidence-widening sweep")
            digests = membership_digests(corpus, played, ledger)
            points = shard_points(fit_points(corpus,
                                             digests["keys"]["fit_openings"]),
                                  index, count)
            if args.limit:
                # §8.4 step 2 names its opening — "the FIRST OPENING BY DATE,
                # 2019-08-09 [...] the opening is named here, before the fit,
                # and it is first by date and not by anything else, so it is
                # not a selection step". A different shard's first point is a
                # different opening, so the flag is bound to the named one
                # rather than to whatever this worker's slice happens to start
                # with.
                points = points[:args.limit]
                if not points or points[0].cutoff != PARTIAL_ENGINE_OPENING:
                    print(f"STOP: `--run --limit 1` is §8.4 step 2 and step 2 "
                          f"is the opening 2019-08-09, named in the document "
                          f"before the fit. This shard's first point is "
                          f"{points[0].cutoff if points else 'nothing'}. Run "
                          "step 2 from the shard that holds the first opening "
                          "by date; choosing an opening here would make step 2 "
                          "a selection step, which §8.4 says it is not.",
                          flush=True)
                    return 2
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
            with Engine(corpus, played, ledger=ledger,
                        directory=directory) as engine:
                out = run_fits(points, ledger_path, corpus, engine=engine,
                               grid_treated=grid_treated,
                               shard_id=f"{index}/{count}")
            # Step 2's marker is written to the PREREGISTERED run directory and
            # not to the scratch one (§8.4), which is the whole reason
            # SEQUENCE_DIR is a fixed location rather than a function of --dir.
            # Step 3's is written only when ALL FOUR shards have exited zero and
            # written their expected key sets.
            if frozen["frozen"]:
                if step == SEQUENCE_STEPS[1]:
                    write_sequence_marker(step, produced={
                        "opening": points[0].cutoff if points else None,
                        "n_rows": out["n_rows_written"],
                        "row_digest": out["run_digest"],
                        "scratch": paths.rel(directory),
                        _PRODUCTS_KEY: product_digests(ledger_path)})
                else:
                    # §8.4 step 3's marker "is written only when all four
                    # shards have exited zero AND WRITTEN THEIR EXPECTED KEY
                    # SETS". File existence establishes neither: a shard that
                    # crashed on its second fit leaves a file too.
                    all_points = fit_points(corpus,
                                            digests["keys"]["fit_openings"])
                    complete = {}
                    for i in range(SHARDS):
                        path_i = EVWIDEN_DIR / shard_name(i, SHARDS)
                        if not path_i.exists():
                            break
                        want_i = {fit_key(p.cutoff, config_sha=config_sha256())
                                  for p in shard_points(all_points, i, SHARDS)}
                        if completed_keys(path_i) != want_i:
                            break
                        complete[shard_name(i, SHARDS)] = run_digest(
                            load_ledger(path_i))
                    if len(complete) == SHARDS:
                        write_sequence_marker(step, produced={
                            "shards": complete,
                            _PRODUCTS_KEY: product_digests(
                                *(EVWIDEN_DIR / shard_name(i, SHARDS)
                                  for i in range(SHARDS)))})
            print(json.dumps(out, indent=2, default=str))

        if args.table:
            from epl import baseline

            frozen = harness_freeze_status()
            _guard_ledger_location(table_ledger, bool(frozen["frozen"]))
            require_run_preconditions(directory,
                                      require_results=bool(frozen["frozen"]),
                                      step=SEQUENCE_STEPS[4])
            assert_blas_pinned("the table-retro leg")
            matches = baseline.load_matches()
            cells = table_cells(matches)
            # §3.3's closure 2: **no `--limit` on the oracle.** "No CLI flag,
            # keyword or subset argument may reduce the oracle's 32 cells. 'All
            # 35' is the whole content of the control." v1's `--table --limit`
            # truncated the run AND its oracle together, so a subset looked
            # internally consistent while proving nothing about the other cells.
            if args.limit:
                print("STOP: --limit does not apply to --table. §3.3 requires "
                      "native parity at ALL THIRTY-TWO priceable cells with no "
                      "sampling, and §2.4 makes thinning the run an amendment "
                      "rather than an optimisation — expressly including "
                      "sampling or truncating the parity oracle.", flush=True)
                return 2
            # v3 §8.4: **step 5 claims its write-once marker BEFORE it
            # simulates**, so a second attempt is refused before a single fit is
            # spent rather than after a second outcome exists (P5-B8). The claim
            # is `complete: false` — §8.4's durable-failure shape — and the same
            # marker is completed below once the leg finishes. A run that dies
            # in between leaves the failure on disk, which is the file-drawer
            # channel §4.4 exists to close.
            if frozen["frozen"]:
                claim_sequence_step(
                    SEQUENCE_STEPS[4],
                    note="step 5 opened; the parity oracle and the table leg "
                         "have not completed")
            out = run_table(cells, table_ledger)
            if frozen["frozen"]:
                # ...and it CARRIES THE LEDGER SHA (adjudication F10). The
                # deciding leg's marker recorded a path, a cell count and a
                # parity check and nothing that bound the four hours of
                # simulation it stands for; both ledgers are hashed here and
                # re-hashed on every later read of the marker.
                write_sequence_marker(SEQUENCE_STEPS[4], produced={
                    "parity": paths.rel(parity_path(table_ledger)),
                    "n_cells": out["n_cells"], "parity_check": out["parity"],
                    _PRODUCTS_KEY: product_digests(
                        table_ledger, parity_path(table_ledger))})
            print(json.dumps(out, indent=2, default=str))

        if args.merge or args.verify:
            corpus, played = load_corpus(), load_archive()
            ledger = load_walk_ledger()
            table_out = None
            if table_ledger.exists():
                from epl import baseline

                cells = table_cells(baseline.load_matches())
                rows = load_table_ledger(table_ledger, expected=cells)
                scored = score_table(rows, ledger_path=table_ledger,
                                     expected_cells=EXPECTED_TABLE_CELLS)
                table_out = {**table_projection(scored, table_gate(scored)),
                             "rows": rows}
            if args.verify and not args.merge:
                print(json.dumps(
                    verify(directory, shards=args.shards,
                           table_ledger=table_ledger), indent=2, default=str))
                return 0
            require_run_preconditions(directory, step=SEQUENCE_STEPS[3])
            result = merge(shards=args.shards, directory=directory,
                           corpus=corpus, played=played, ledger=ledger,
                           # §9.1: `scored.per_cell` is NOT stripped — it is
                           # what fills the table-parity and coverage
                           # diagnostics the evidence contract promises.
                           table=(None if table_out is None
                                  else table_projection(table_out["scored"],
                                                        table_out["gate"])),
                           write=args.merge)
            # §9.3's MANIFEST hashes the five sequence markers, so EVERY marker
            # lands before the manifest is computed. NEW-B7 found the
            # publication pass rewriting `step4_merge.json` AFTER hashing it,
            # which left a manifest that was invalid the moment it was written.
            # `write_sequence_marker` re-verifies rather than rewrites on the
            # publication pass, and the write happens here — before `--evidence`
            # — rather than after it.
            if args.merge and result.get("harness_freeze", {}).get("frozen"):
                # The product bytes this step's verdict is a function of
                # (adjudication F10). They are the four shard ledgers, and not
                # `data/epl/fit/evwiden.json`: the merge runs TWICE by §8.4's
                # own order — once as step 4, before the table exists, and once
                # at publication with §3.3's gate in it — so the merged verdict
                # is not a byte-constant of step 4 while the ledgers it scored
                # are, and `run_digest` beside them is recomputable from exactly
                # these bytes.
                write_sequence_marker(SEQUENCE_STEPS[3], produced={
                    "n_fits": result["n_fits"], "n_fixtures": result["n_fixtures"],
                    "run_digest": result["run_digest"],
                    _PRODUCTS_KEY: product_digests(
                        *(directory / shard_name(i, args.shards)
                          for i in range(args.shards)))})
            if args.evidence:
                merged = [r for shard in range(args.shards)
                          for r in load_ledger(
                              directory / shard_name(shard, args.shards))]
                # §6's `power` object is computed HERE, from committed code,
                # so the verdict file carries numbers a reader can re-run rather
                # than numbers a scratch script once printed.
                written = write_evidence(
                    result, merged,
                    None if table_out is None else table_out["rows"],
                    power=power_simulation())
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
