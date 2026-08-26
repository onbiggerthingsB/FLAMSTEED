"""THE MARKET PRIOR. Does a market-informed strength prior price a fixture
better than the Elo-anchored one that prices it today?

This module executes the design preregistered in
``reports/epl_anchoring_prereg.md`` (ed40f27) and computes the estimand fixed
in its §2.6. It chooses nothing. The corpus is pinned by digest, the odds panel
is pinned by digest, the configuration is frozen, the grid was written down
before this file existed, the selection is leave-one-season-out and in-fold,
and the adoption rule is evaluated but never applied — §4.5: *"No script, no
agent and no report may change the model on the strength of these numbers."*

WHAT THE TWO ARMS ARE.

* **Arm B — ``dc_native``** is **not recomputed**. It is the walk-forward's own
  ``dc_home``/``dc_draw``/``dc_away``/``dc_rps``, read out of
  ``data/epl/fit/walkforward_predictions.parquet`` at the eight decimals
  ``epl/walkforward.py::_one_cutoff`` wrote them with.
* **Arm A — ``dc_market_prior``** is a new fit at each of the 212 block
  openings, through the identical pipeline, with one substitution: the vector
  handed to ``build_design``'s ``elo_z`` slot is ``z_blend(w)`` instead of
  ``elo_z``. Everything downstream — the prior code in
  ``wcmodel.model.scoreline._priors``, the likelihood, the widening, the
  sampler, the posterior — is ``wcmodel``'s own and is untouched.

WHERE THE SUBSTITUTION HAPPENS, AND WHY IT IS NOT A PATCH. §2.7 verified that
``config/config.yaml``'s ``strength_prior.source`` key is **inert**: nothing
reads it, and setting it to ``market`` would change no computed value. The
reachable seam is one layer down and already ``epl/``-side —
``epl/dcfit.py:264`` builds ``elo_z`` itself and hands it to ``build_design``,
which accepts any correctly-shaped vector. :func:`fit_market_prior` is
``epl.dcfit.fit_epl``'s call sequence with that one vector replaced; it imports
``epl.dcfit``'s own cold-start machinery rather than restating it, and it
monkey-patches nothing. ``epl/dcfit.py``'s docstring rules on this exact
question — *"an explicit call sequence is auditable; a patched import is not"* —
and this module obeys it. **The check that the replication is faithful is not
a claim: it is §3.2's control**, which re-fits at ``w = 0`` and demands the
corpus's own eight-decimal rows back exactly.

WHAT ``w = 0`` MEANS HERE. §2.2 defines ``z_blend(0)`` as ``elo_z``
*literally*, not as ``zscore(elo_z)``, so the baseline identity is exact by
construction rather than to float round-off. That is what makes the control a
check on archive drift instead of a check on arithmetic.

THE ONE DANGEROUS DIRECTION. Arm A's prior sees information Arm B's does not,
so **any leak biases the result toward adoption** — the direction the model
change would be made on (§1.6 (b)). Four guards, none optional: the
``date < cutoff`` bound on the training frame, canaried by
``epl.walkforward.point_in_time_canary`` (§5.3); the market window's own bound,
canaried separately by :func:`run_odds_canary` because the existing canary
rewrites RESULTS and is blind to odds (§5.4); the ``w = 0`` control (§3.2); and
the in-fold selection of ``w``, which never touches the scored season (§2.4).

WHAT THIS FILE MAY NOT DO. It writes ``data/epl/fit/`` and nothing else (§6).
It authors no verdict prose — ``reports/epl_anchoring_result.md`` is a human
act after the numbers exist, and §4.4 requires it whichever way they fall. It
does not touch the pinned corpus, which is read-only here and whose digest A8
also depends on. It does not modify ``epl/parse.py``: the existing Pinnacle
benchmark columns keep their existing meaning so that ``dc_native``-versus-
market stays exactly the comparison it already is (§3.4). And it does not run
the preregistered sweep before §6's harness-hash freeze commit exists.

NO BETTING (A9 (d)). This module reads market prices as a **model input** and
as nothing else. It computes no stake, no edge, no price, no recommendation,
and it never scores any arm against a closing market — §3.4 bans that by
construction, and :class:`ClosingOddsRead` is the refusal that makes the ban
mechanical rather than editorial.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# BLAS FIRST, AND ONLY AT THE ENTRY POINT — `epl/freshsweep.py`'s ruling,
# adopted here for the same reason. OpenBLAS reads its thread count when it is
# loaded, which happens on `import numpy`, so a pin applied afterwards is a pin
# that did nothing to the pool already running. The house rule from the sharded
# OA runs is one thread per worker: an N-way shard on a machine whose BLAS also
# wants N threads thrashes at a fraction of the CPU each.
#
# Importing this module does NOT pin. A library that rewrites the process
# environment on import changes the behaviour of code it knows nothing about.
# What replaces the mutation is evidence: :func:`blas_threads` records what the
# process ACTUALLY has on every ledger row (§5.2), and :func:`assert_blas_pinned`
# refuses to run real fits in a process that is not pinned (§3.2's pre-stated
# condition).
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
import io                                                         # noqa: E402
import json                                                       # noqa: E402
import re                                                         # noqa: E402
import socket                                                     # noqa: E402
import time                                                       # noqa: E402
from contextlib import ExitStack as _ExitStack                    # noqa: E402
from dataclasses import dataclass                                 # noqa: E402
from pathlib import Path                                          # noqa: E402
from typing import Any, Callable, Iterable, Mapping, Sequence     # noqa: E402

import numpy as np                                                # noqa: E402
import pandas as pd                                               # noqa: E402

from epl import devig, fetch, paths, recalfit                     # noqa: E402
from epl import parse as epl_parse                                # noqa: E402
from epl import score as score_mod                                # noqa: E402
from epl import teams as epl_teams                                # noqa: E402

__all__ = [
    "MarketPriorError", "SCHEMA_ID", "SEED", "BOOTSTRAP_SEED", "ADOPT_DELTA",
    "W_GRID", "ARM_NAME", "RUN_ORDER",
    "AVG_OPENING", "PS_OPENING", "assert_opening_columns",
    "read_opening_odds", "read_season_opening_odds", "OddsPanel",
    "build_panel", "assert_panel", "assert_source_digests", "sha256_file",
    "market_window", "recover_strength", "market_z", "blend",
    "run_odds_canary", "require_odds_canary",
    "load_corpus", "check_corpus_scores", "block_openings", "fit_points",
    "grid_points", "fit_point_digest", "control_dates", "fit_key",
    "shard_points", "shard_name", "canonical", "run_digest", "load_ledger",
    "completed_keys", "blas_threads", "assert_blas_pinned", "Engine",
    "fit_market_prior", "run_fits", "run_canary", "require_canary",
    "run_control", "require_control", "require_run_preconditions",
    "select_w", "estimand", "adoption", "harness_freeze_status",
    "require_harness_freeze", "merge", "main",
]


# ==========================================================================
# 0. the pins — the corpus, the config, the panel, the constants §2 fixed
# ==========================================================================
#: A8's own objects, bound by identity and not copied, so there is one place
#: where "which corpus" is defined and one digest to break (§0.1).
CORPUS_PATH = recalfit.CORPUS_PATH
CORPUS_SHA256 = recalfit.CORPUS_SHA256
CORPUS_ROWS = recalfit.CORPUS_ROWS
CORPUS_SEASONS = recalfit.CORPUS_SEASONS
CORPUS_Y_COUNTS = recalfit.CORPUS_Y_COUNTS

CONFIG_PATH = paths.REPO_ROOT / "epl" / "config_frozen.json"
CONFIG_SHA256 = \
    "9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc"

#: §2.6: one seed, and `epl/walkforward.py` derives nothing per cutoff.
SEED = 20260611

#: §2.6's interval: the project's own block bootstrap, percentile, at the
#: standard resampling seed. Both blockings, both required by §4.1.
BOOTSTRAP_SEED = 20260814
N_BOOT = 10_000
ALPHA = 0.05

#: §4.1/§4.2's threshold — the HOUSE model-change bar, not scaled to the
#: +0.0050 output-blend prize and not lowered to freshness's -0.00030.
ADOPT_DELTA = -0.0010

#: §2.4's grid, fixed before any fit. `0.00` is on it deliberately: the
#: selection must be allowed to say "no market term", and it costs no fits.
W_GRID: tuple[float, ...] = (0.00, 0.15, 0.30, 0.50, 0.75, 1.00)

#: §2.1's two window constants. NEITHER IS TUNED and neither may be: §7 makes
#: tuning `M`, `L`, `lambda`, the de-vig, `k_att` or `k_def` an invalidation.
#: `M` is `config/config.yaml:11`'s `elo.volatility_window`, read on this very
#: path by `count_volatility_arm`; `L` is the model's own
#: `decay_half_life_days`, so the anchor's memory is the likelihood's memory.
MARKET_WINDOW_MATCHES = 10
MARKET_WINDOW_DAYS = 365

#: §2.1 Step 3: ridge on the club coefficients only, NEVER on `eta`.
RIDGE_LAMBDA = 1.0

#: §2.1 Step 3's decay weight — `src/wcmodel/data/features.py:297`'s own, not a
#: second free knob.
DECAY_HALF_LIFE_DAYS = 365.0

#: §5.1's `RecoveryUnstable` band, pre-stated: the market's implied home
#: advantage in log-odds ran 0.2519-0.4429 across the 212 cutoffs.
ETA_BAND = (0.10, 0.70)
MAX_CONDITION = 1e10

#: §2.1'S PUBLISHED SANITY STATISTICS DO NOT REPRODUCE UNDER §2.1'S OWN RULE,
#: and this is the harness recording the fact rather than quietly picking a
#: side. The document states the window twice and the two statements disagree:
#:
#: * THE DEFINITION — "keep a row if it is among the 10 most recent such
#:   matches of *either* club", "`M = 10` matches per club", "one club-quarter
#:   of a 38-match season" — is venue-blind, and so is the thing it cites for
#:   the constant: `config/config.yaml:11`'s `volatility_window` counts "most
#:   recent PRIOR rating deltas", which a club accrues home and away alike.
#: * THE MEASUREMENTS — "min 201, median 233, max 262 matches", `eta` "0.2519
#:   to 0.4429, median 0.3740", cross-club sd "0.6693 to 0.8181, median
#:   0.7514" — were produced by a PER-VENUE window (each club's 10 most recent
#:   HOME matches *and* 10 most recent AWAY matches, so 20 per club) whose sd
#:   was then taken over the season's twenty rather than over every club the
#:   window holds. Reproduced under exactly that variant, all three trios come
#:   back to the last digit; under the ruled definition none of them does.
#:
#: THE DEFINITION BINDS AND THE ANNOTATIONS ARE STALE. A prose rule with a
#: cited constant behind it is the mechanism; a sanity statistic is a check ON
#: the mechanism, and a check that was run against a different window is
#: evidence about that window and not about this one. Choosing the other way —
#: fitting the mechanism to the numbers already printed — would silently double
#: `M` to 20, which §7 makes an invalidation.
#:
#: :data:`MEASURED_WINDOW` / :data:`MEASURED_ETA` / :data:`MEASURED_SD` are
#: what the RULED definition actually gives over the 212 cutoffs, recomputed
#: here so that §2.1's numbers can be corrected by amendment against a recorded
#: quantity rather than against a fresh script. The one claim of §2.1 that is
#: rule-INVARIANT — 7 cutoffs and 19 fixtures where a fitted club has no window
#: match at all — reproduces exactly, because being absent from the window
#: does not depend on how many of a club's matches are kept.
MEASURED_WINDOW = (101, 129, 138)
MEASURED_ETA = (0.2350, 0.3764, 0.4445)
MEASURED_SD = (0.6308, 0.7349, 0.8402)
MEASURED_ZERO_WINDOW_CUTOFFS = 7
MEASURED_ZERO_WINDOW_FIXTURES = 19

#: The per-venue variant, kept ONLY so the test that diagnoses the stale
#: annotations can name what produced them. Nothing on the fit path calls it.
DOCUMENTED_WINDOW = (201, 233, 262)
DOCUMENTED_ETA = (0.2519, 0.3740, 0.4429)
DOCUMENTED_SD = (0.6693, 0.7514, 0.8181)

#: §2.2's frozen anchor scale. Recorded here so a reader can see that this
#: experiment does not move it; the value the fit uses is read from the frozen
#: config, never from this constant.
K_ATT = 0.6
K_DEF = 0.6

#: §0.3's odds columns. Opening only, and the `assert_opening_columns` guard
#: below is what makes "opening only" mechanical rather than editorial.
AVG_OPENING = ("AvgH", "AvgD", "AvgA")
PS_OPENING = ("PSH", "PSD", "PSA")

#: The last cutoff of the experiment. A panel row dated on or after it can
#: reach no cutoff, so the pinned panel stops here (§0.3).
PANEL_MAX_DATE = "2025-05-19"

#: §0.3's panel pins, recomputed on 2026-08-26 from the archive by the recipe
#: in :func:`OddsPanel.digest`.
PANEL_SHA256 = \
    "84ea5621e1aaa45bd43c3063897d79525103ae74dd51eb071b777bae9618235c"
PANEL_ROWS = 4167
PANEL_AVG_ROWS = 2267
PANEL_PS_ROWS = 1900

#: §0.3's source-file digests. The document's prose says "ten"; its table lists
#: ELEVEN, and the table is what binds — a count is not a digest. `E0_2526` is
#: absent because its earliest match (2025-08-15) is after the last cutoff
#: (2025-05-19), so no cutoff in this experiment can reach it.
ODDS_SOURCE_SHA256: dict[str, str] = {
    "1415": "76b7858051ff6b17f46f49f26fdc70c1f29537270492606f5cc63d67fad5d149",
    "1516": "bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085",
    "1617": "9625a7652b5f98fbd3e2e4d378c851fc246693f3343e34a72428d5b6e864d3e0",
    "1718": "4f3389365ef3f7ac966764ed8ba67cf3b79f5aebed18dd224099c4b2c98bc67b",
    "1819": "7c096b3c2ecd54c6993d22eeea73450c2bde11e3457238b226b8f43c62dfc35e",
    "1920": "100037618b94f94057400bb02bf6bac4ef74ddaa58cde4b38370839c39caee61",
    "2021": "5afe63f69401457b8354eaacee24f9a3e520b3c3af6329564a9783e20d789c62",
    "2122": "335afcbabeb2939fa10ab39ba3e8215072d0b577cb8d0705c1e44c56e934e703",
    "2223": "8442792d3b614c94ea3cf381bd2736805889cc1713169035368fff19c3d02380",
    "2324": "b2e057b0ed959f198b0f63d2391c01239f3608e6de5db68edab3f88e04d07ff3",
    "2425": "d0c8ce4a96d886cf60cf101f570f4a3893844226f91c7bd769eb568c49edbfa4",
}

#: §2.6's arm name, ruled in the document and grep-verified not to collide
#: with "anchor" (the Elo prior + the G3 digest regime) or with `market_*`
#: (the de-vigged benchmark). It names the MECHANISM — a prior — so it can
#: never be read as a market-derived forecast.
ARM_NAME = "dc_market_prior"
BASELINE_ARM = "dc_native"

#: §0.1's counts. A corpus that does not produce them is a different corpus,
#: not a smaller experiment.
EXPECTED_BLOCKS = 212
EXPECTED_FIXTURES = 2280

#: §2.8's budget: 212 cutoffs x the five weights that need a fit.
EXPECTED_FIT_POINTS = 1060

#: §3.2's control, reused VERBATIM from freshness §3.2 so the choice cannot
#: have been made to suit this experiment.
CONTROL_SEED = 20260826
N_CONTROL_DATES = 20
EXPECTED_CONTROL_FIXTURES = 227
EXPECTED_CONTROL_PROBABILITIES = 681

#: The schema identifier §6's freeze commit must name alongside the hashes.
SCHEMA_ID = "epl-market-prior-1"

#: The files whose bytes can change a number, and which the §6 hash table
#: therefore has to name (§2.7 names exactly these two). The tests are in the
#: list because a test that stops asserting is a guard that stopped guarding.
HARNESS_FILES = ("epl/mktprior.py", "epl/tests/test_mktprior.py")

#: §3.2 runs the control FIRST among the fits; §5.3 and §5.4 put two canaries
#: before even that. Enforced by :func:`require_run_preconditions` from the
#: written records, because an order declared in a constant and checked by
#: nobody is a comment.
RUN_ORDER = ("canary", "odds_canary", "control", "run", "merge")

#: §5.5's list, fixed in the document before any row existed: recorded on the
#: row, excluded from the canonical form and from every digest.
_VOLATILE = ("wall_seconds", "fit_seconds", "seconds", "shard_id",
             "started_at", "host")

#: Where the run writes. §6 closes the set.
MKTPRIOR_DIR = paths.FIT_DIR / "market_prior"
PREDICTIONS_PARQUET = paths.FIT_DIR / "dc_market_prior_predictions.parquet"
ANCHORING_JSON = paths.FIT_DIR / "anchoring.json"
CONTROL_NAME = "control.json"
CANARY_NAME = "canary.json"
ODDS_CANARY_NAME = "odds_canary.json"
CONTROL_JSON = MKTPRIOR_DIR / CONTROL_NAME
CANARY_JSON = MKTPRIOR_DIR / CANARY_NAME
ODDS_CANARY_JSON = MKTPRIOR_DIR / ODDS_CANARY_NAME
WRITES = (MKTPRIOR_DIR, PREDICTIONS_PARQUET, ANCHORING_JSON, CONTROL_JSON,
          CANARY_JSON, ODDS_CANARY_JSON)

#: Where §6's freeze commit records the harness hashes.
PREREG_PATH = paths.REPO_ROOT / "reports" / "epl_anchoring_prereg.md"
AMENDMENTS_PATH = paths.REPO_ROOT / "reports" / "epl_sim_amendments.md"

_PROB_COLUMNS = ("dc_home", "dc_draw", "dc_away")


# ==========================================================================
# 1. the typed refusals — §5.1's twenty-five, and not a twenty-sixth
# ==========================================================================
class MarketPriorError(RuntimeError):
    """Anything this experiment refuses.

    §5.1 names twenty-five subclasses and this module does not invent a
    twenty-sixth. A condition the preregistration pre-stated as an
    INVALIDATION but never gave an error name — §7's "a fit runs before the
    harness-hash commit of §6 exists" is the one that matters in practice — is
    refused as this base class rather than under a name the document never
    wrote. That is `epl.recalfit`'s ruling and `epl.freshsweep`'s, applied here
    for the same reason: a typed name is a promise the preregistration made,
    and inventing one after the fact is the small end of the wedge this whole
    apparatus exists to block.
    """


class CorpusMissing(MarketPriorError):
    """The pinned parquet is not on disk."""


class CorpusDigestMismatch(MarketPriorError):
    """The corpus is not the corpus the experiment was preregistered on."""


class CorpusShapeMismatch(MarketPriorError):
    """Rows, seasons, outcome counts or block count are not the pinned ones."""


class ConfigNotFrozen(MarketPriorError):
    """`epl/config_frozen.json` is not `9f2e086d…`, or the seed is not 20260611,
    or `strength_prior` is not `{enabled: true, k_att: 0.6, k_def: 0.6}`."""


class OddsSourceDigestMismatch(MarketPriorError):
    """A pinned `E0_*.csv` digest differs."""


class OddsPanelMismatch(MarketPriorError):
    """The built panel is not the pinned 4,167 / 2,267 / 1,900 / `84ea5621…`."""


class OddsTripleIncomplete(MarketPriorError):
    """A panel row has a missing or <= 1.0 price.

    The panel imputes nothing and half-uses nothing: a de-vig needs all three
    prices or none.
    """


class ClosingOddsRead(MarketPriorError):
    """A closing column was asked for anywhere in the anchor path.

    §0.2 measures the close-to-open gap at +0.001385 on `Avg`. An anchor that
    read it would be credited with a timing advantage no live system has.
    """


class OddsLeak(MarketPriorError):
    """A window row is dated on or after its cutoff, or a scored fixture's own
    odds appear in the window of the fit that prices it (§2.3)."""


class CutoffLeak(MarketPriorError):
    """A fit can see a match dated on or after its own cutoff.

    The one failure mode with a direction: it flatters Arm A, which is the arm
    an adoption would be granted on (§1.6 (b)).
    """


class PanelOutOfDate(MarketPriorError):
    """A cached feature panel's maximum match date is on or after its cutoff."""


class RecoveryUnstable(MarketPriorError):
    """The ridge normal equations are singular, the condition number exceeds
    1e10, or the recovered `eta` falls outside [0.10, 0.70] (§5.1)."""


class DegenerateStrength(MarketPriorError):
    """The cross-club sd of the recovered `s` is <= 0, which would silently
    zero the whole market term."""


class CanaryFailed(MarketPriorError):
    """`epl.walkforward.point_in_time_canary` did not pass (§5.3)."""


class MarketCanaryFailed(MarketPriorError):
    """§5.4's odds canary failed, in either direction."""


class ControlMismatch(MarketPriorError):
    """A `w = 0` re-fit did not return the corpus's own row (§3.2)."""


class GridEscape(MarketPriorError):
    """A selected `w` is not on `{0.00, 0.15, 0.30, 0.50, 0.75, 1.00}`."""


class FoldLeak(MarketPriorError):
    """A scored season's fixtures appear in that season's own selection fold."""


class FitFailed(MarketPriorError):
    """`fit_epl` raised, or the posterior it produced is not usable."""


class UnpriceableFixture(MarketPriorError):
    """A club is absent from the posterior index at its block's cutoff.

    §2.6 fixes the denominator at 2,280 and Arm A sees the same matches as Arm
    B, so this is a defect by construction and never a dropped row.
    """


class ScoreMismatch(MarketPriorError):
    """Stored `dc_rps` does not re-derive from the stored probabilities."""


class SchemaMismatch(MarketPriorError):
    """A ledger row lacks a field §5.2 requires."""


class RowConflict(MarketPriorError):
    """Two rows share a key and disagree on a non-volatile field."""


class ShardFailed(MarketPriorError):
    """A shard is missing, empty, or still carries a poison row."""


class MergeIncomplete(MarketPriorError):
    """The merged key set is not exactly the 1,060 pre-stated fit keys."""


# ==========================================================================
# 2. digests
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


def blas_threads() -> dict[str, Any]:
    """What this process ACTUALLY has, recorded on every row (§5.2).

    Not what it asked for: the environment is read back, and
    ``pinned_before_numpy`` says whether the pin could have reached the BLAS
    pool at all. A row produced in a different threading environment is
    therefore visible ON THE ROW rather than inferred from the source — and
    §5.2 excludes it from no digest, because the environment a row was produced
    in belongs on the record.
    """
    out: dict[str, Any] = {v: _os.environ.get(v) for v in BLAS_VARS}
    out["pinned_before_numpy"] = bool(_IS_ENTRY_POINT
                                      and not _NUMPY_ALREADY_IMPORTED)
    out["entry_point"] = bool(_IS_ENTRY_POINT)
    return out


def assert_blas_pinned(where: str) -> dict[str, Any]:
    """§3.2's pre-stated condition: one BLAS thread per worker, for real fits.

    Checked where fits actually happen rather than at import, because the pin is
    a property of the process that runs them. A stubbed control runs no fit and
    pins nothing; a control about to spend twenty ADVI fits does.
    """
    threads = blas_threads()
    unpinned = [v for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                            "MKL_NUM_THREADS") if threads.get(v) != "1"]
    if unpinned:
        raise MarketPriorError(
            f"{where} runs real fits and this process is not pinned to one "
            f"BLAS thread per worker: {unpinned} are "
            f"{[threads.get(v) for v in unpinned]}. §3.2 pre-states the "
            "condition and §5.2 records it per row. Run the sweep as "
            "`python -m epl.mktprior`, which pins before numpy loads, or "
            "export the three variables before starting the worker.")
    return threads


# ==========================================================================
# 3. the odds reader — Avg at the open, PS where Avg is not born yet
# ==========================================================================
#: football-data marks a CLOSING column with a `C` immediately after the book's
#: prefix: `PSH` -> `PSCH`, `AvgH` -> `AvgCH`, `B365H` -> `B365CH`. The guard
#: is written against that shape rather than against a list of names, so a book
#: this experiment has never read cannot slip a closing price past it.
_CLOSING_SHAPE = re.compile(r"^(?P<book>[A-Za-z0-9&]*?)C(?P<outcome>[HDA])$")


def assert_opening_columns(columns: Sequence[str]) -> tuple[str, ...]:
    """Refuse a closing triple anywhere in the anchor path (§5.1).

    Mechanical, not editorial: §3.4 bans scoring any arm against a closing
    market, and the cheapest way for that ban to be broken is for the ANCHOR to
    read a close by accident. `AvgCH` and `AvgH` differ by one character.
    """
    cols = tuple(str(c) for c in columns)
    bad = [c for c in cols if _CLOSING_SHAPE.match(c)]
    if bad:
        raise ClosingOddsRead(
            f"{bad} name closing prices, and the anchor reads OPENING prices "
            "only. §0.2 measures the close-to-open gap at +0.001385 on Avg: an "
            "anchor that read the close would be credited with a timing "
            "advantage no live system has, and §3.4 bans the comparison that "
            "would follow.")
    return cols


def _triple(frame: pd.DataFrame, cols: tuple[str, str, str]) -> pd.DataFrame | None:
    """Three decimal-odds columns as floats; invalid triples become all-NaN.

    A price at or below 1.0 implies a probability of 1 or more, so its presence
    means the cell is a placeholder rather than a quote. The whole triple is
    voided together — `epl/parse.py`'s ruling, adopted here because a de-vig
    needs all three prices or none (§5.1 `OddsTripleIncomplete`).
    """
    assert_opening_columns(cols)
    if not all(c in frame.columns for c in cols):
        return None
    out = frame[list(cols)].apply(pd.to_numeric, errors="coerce")
    usable = out.notna().all(axis=1) & (out > 1.0).all(axis=1)
    return out.where(usable, np.nan)


def read_opening_odds(csv_text: str, *, label: str) -> pd.DataFrame:
    """One source file's OPENING prices, `Avg` preferred, `PS` where it is not.

    Returns `date`, `home`, `away`, `src`, `h`, `d`, `a` — one row per match
    with a complete opening triple, in file order.

    THIS IS A NEW `epl/`-SIDE READER AND `epl/parse.py` IS NOT MODIFIED.
    `parse.py` extracts Pinnacle only and, where both exist, prefers the CLOSE
    (`_CLOSING_ODDS` before `_OPENING_ODDS`). It therefore cannot feed this
    anchor on two counts. Changing it would move the published benchmark, which
    §3.4 rules stays exactly where it is.

    THE `PS` BACKFILL IS HISTORY ONLY (§0.3). `AvgH` does not exist before
    2019/20 and the market window at a 2019/20 cutoff reaches back into seasons
    that have only Pinnacle. The two sources agree to 8.55e-6 in pooled RPS and
    disagree per match by mean 0.0034 / max 0.0224 — the scale of this model's
    own ADVI re-seed noise. A live arm reads `Avg` and only `Avg`, because
    Pinnacle is absent as a column from the live feed.
    """
    raw = pd.read_csv(io.StringIO(csv_text))
    required = ["Date", "HomeTeam", "AwayTeam"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise OddsPanelMismatch(
            f"{label}: the source file lacks {missing}; there is no match to "
            "attach a price to")
    blank = (raw["Date"].isna() & raw["HomeTeam"].isna()
             & raw["AwayTeam"].isna())
    raw = raw[~blank].reset_index(drop=True)

    avg = _triple(raw, AVG_OPENING)
    ps = _triple(raw, PS_OPENING)
    if avg is None and ps is None:
        raise OddsPanelMismatch(
            f"{label}: neither {list(AVG_OPENING)} nor {list(PS_OPENING)} is "
            "present. §0.3 rules Avg-opening as the anchor's column with a PS "
            "backfill for history; a file with neither carries no opening "
            "price this experiment may read, and the anchor imputes nothing.")

    date = epl_parse.parse_dates(raw["Date"])
    if date.isna().any():
        offenders = raw.loc[date.isna(), "Date"].astype(str).unique().tolist()
        raise OddsPanelMismatch(
            f"{label}: {int(date.isna().sum())} date(s) match neither "
            f"DD/MM/YYYY nor DD/MM/YY: {offenders[:5]}")

    rows: list[dict[str, Any]] = []
    for i in range(len(raw)):
        if avg is not None and bool(avg.iloc[i].notna().all()):
            src, tri = "Avg", avg.iloc[i].to_numpy(dtype=float)
        elif ps is not None and bool(ps.iloc[i].notna().all()):
            src, tri = "PS", ps.iloc[i].to_numpy(dtype=float)
        else:
            continue
        home = epl_teams.resolve(
            epl_teams.normalise_spelling(raw["HomeTeam"].iloc[i]))[1]
        away = epl_teams.resolve(
            epl_teams.normalise_spelling(raw["AwayTeam"].iloc[i]))[1]
        rows.append({"date": date.iloc[i], "home": home, "away": away,
                     "src": src, "h": float(tri[0]), "d": float(tri[1]),
                     "a": float(tri[2])})
    return pd.DataFrame(rows, columns=["date", "home", "away", "src",
                                       "h", "d", "a"])


def read_season_opening_odds(season_code: str) -> pd.DataFrame:
    """One cached archive season, through :func:`read_opening_odds`."""
    return read_opening_odds(fetch.read_raw(season_code),
                             label=fetch.season_label(season_code))


# ==========================================================================
# 4. the panel — one object, one digest, no imputation
# ==========================================================================
@dataclass(frozen=True)
class OddsPanel:
    """Every archive match this experiment may read, de-vigged once.

    `frame` carries the raw opening prices (`h`, `d`, `a`), their source
    (`src`), the proportional de-vig (`p_home`, `p_draw`, `p_away`) and the
    draw-excluded market log-odds `m = log(p_home / p_away)` that §2.1's
    inversion is defined on. The de-vig happens ONCE, here, so no downstream
    caller can pick a different one: §2.1 rules multiplicative per the OA
    precedent, and preferring whichever de-vig scores better would be choosing
    the input to suit the answer.
    """

    frame: pd.DataFrame
    sha256: str
    n_avg: int
    n_ps: int
    max_date: str
    sources: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.frame)

    @staticmethod
    def digest(frame: pd.DataFrame) -> str:
        """§0.3's canonical form, exactly.

        `json.dumps` over records `{date, home, away, src, h, d, a}` sorted by
        `(date, home, away)`, PRICES rounded to 4 dp, `sort_keys=True`,
        `separators=(",", ":")`. The prices and not the de-vigged
        probabilities: the panel's identity is what the book published, and a
        digest over a derived quantity would move if the de-vig ever did.
        """
        records = [{"date": str(pd.Timestamp(d).date()), "home": str(h),
                    "away": str(a), "src": str(s), "h": round(float(x), 4),
                    "d": round(float(y), 4), "a": round(float(z), 4)}
                   for d, h, a, s, x, y, z in zip(
                       frame["date"], frame["home"], frame["away"],
                       frame["src"], frame["h"], frame["d"], frame["a"])]
        records.sort(key=lambda r: (r["date"], r["home"], r["away"]))
        return hashlib.sha256(json.dumps(
            records, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def build_panel(sources: Mapping[str, str] | None = None, *,
                max_date: str = PANEL_MAX_DATE) -> OddsPanel:
    """The pinned odds panel (§0.3), or a synthetic one from CSV text.

    `sources` maps a season code to raw CSV TEXT; passing it is how the tests
    build a panel without an archive. The default reads the eleven cached
    archive files the document pins — the only files any cutoff in this
    experiment can reach.

    `max_date` is EXCLUSIVE and defaults to the last cutoff: a match dated on
    or after it can reach no cutoff, so carrying it would put rows in the
    digest that no fit can ever use.
    """
    if sources is None:
        sources = {code: fetch.read_raw(code) for code in ODDS_SOURCE_SHA256}
    parts = [read_opening_odds(text, label=code)
             for code, text in sorted(sources.items())]
    frame = (pd.concat(parts, ignore_index=True) if parts
             else pd.DataFrame(columns=["date", "home", "away", "src",
                                        "h", "d", "a"]))
    frame = frame.loc[frame["date"] < pd.Timestamp(max_date)]
    frame = (frame.sort_values(["date", "home", "away"], kind="mergesort")
             .reset_index(drop=True))

    prices = frame[["h", "d", "a"]].to_numpy(dtype=float)
    if prices.size and (not np.isfinite(prices).all() or (prices <= 1.0).any()):
        raise OddsTripleIncomplete(
            "a panel row carries a missing or <= 1.0 price after the reader "
            "voided incomplete triples, which cannot happen: the panel imputes "
            "nothing and half-uses nothing")
    if prices.size:
        p = devig.proportional(prices)
    else:
        p = np.zeros((0, 3))
    frame["p_home"], frame["p_draw"], frame["p_away"] = p[:, 0], p[:, 1], p[:, 2]
    frame["m"] = np.log(frame["p_home"].to_numpy(float)
                        / frame["p_away"].to_numpy(float))

    return OddsPanel(
        frame=frame, sha256=OddsPanel.digest(frame),
        n_avg=int((frame["src"] == "Avg").sum()),
        n_ps=int((frame["src"] == "PS").sum()),
        max_date=str(max_date), sources=tuple(sorted(sources)))


def assert_panel(panel: OddsPanel, *, rows: int = PANEL_ROWS,
                 n_avg: int = PANEL_AVG_ROWS, n_ps: int = PANEL_PS_ROWS,
                 sha256: str = PANEL_SHA256) -> str:
    """§5.1's `OddsPanelMismatch`: the panel this document measured and the
    panel the harness builds must be provably the same object."""
    problems = []
    if len(panel) != rows:
        problems.append(f"{len(panel)} rows, not {rows}")
    if panel.n_avg != n_avg:
        problems.append(f"Avg {panel.n_avg}, not {n_avg}")
    if panel.n_ps != n_ps:
        problems.append(f"PS {panel.n_ps}, not {n_ps}")
    if panel.sha256 != sha256:
        problems.append(f"digest {panel.sha256[:10]}…, not {sha256[:10]}…")
    if problems:
        raise OddsPanelMismatch(
            "; ".join(problems) + ". §0.3 pins the panel by row count, by "
            "source split and by canonical digest, and §6 freezes that digest "
            "as recomputed by this reader. A panel that differs is a different "
            "input, not a smaller one.")
    return panel.sha256


def assert_source_digests(files: Mapping[str, Path | str] | None = None,
                          expected: Mapping[str, str] | None = None,
                          ) -> dict[str, str]:
    """§5.1's `OddsSourceDigestMismatch`, so a re-download cannot change a
    number silently."""
    expected = dict(expected if expected is not None else ODDS_SOURCE_SHA256)
    files = ({code: fetch.raw_path(code) for code in expected}
             if files is None else {k: Path(v) for k, v in files.items()})
    got: dict[str, str] = {}
    problems = []
    for code, want in sorted(expected.items()):
        path = Path(files[code]) if code in files else None
        if path is None or not path.exists():
            problems.append(f"{code}: not on disk")
            continue
        got[code] = sha256_file(path)
        if got[code] != want:
            problems.append(f"{code}: {got[code][:10]}… != {want[:10]}…")
    if problems:
        raise OddsSourceDigestMismatch(
            "; ".join(problems) + ". §0.3 pins the source files by digest "
            "precisely so that a re-download cannot move a price without "
            "anybody noticing.")
    return got


# ==========================================================================
# 5. z_mkt — §2.1, the four steps, and the leakage clause of §2.3
# ==========================================================================
def market_window(panel: OddsPanel, cutoff: str | pd.Timestamp) -> pd.DataFrame:
    """§2.1 Step 1: which panel rows a fit at ``cutoff`` may read.

    Strictly before ``C``, within ``L = 365`` days of it, then the ``M = 10``
    most recent of EITHER club. Both constants are fixed by §2.1 and neither is
    tuned: ``M`` is ``config/config.yaml:11``'s ``elo.volatility_window``, read
    on this very path by ``count_volatility_arm``, and ``L`` is the model's own
    ``decay_half_life_days``, so the anchor's memory is the likelihood's memory
    and not a second free knob. §7 makes tuning either an invalidation.

    THE STRICT BOUND IS §2.3'S WHOLE RULING, and it is conservative on purpose.
    A live system at ``C`` really does hold opening prices for the coming
    weekend, and reading them would roughly double the correlation with the
    model's own errors (§1.5: +0.0982 against +0.1712). It is refused because
    the archive carries no publication timestamp, because it would put a
    fixture's own price into the prior that prices it, and because the
    conservative rule inherits a bound that is already proven: a match's odds
    are published before the match, so odds legality follows from match
    legality, which is ``features.build``'s ``date < cutoff.normalize()``.
    """
    ts = pd.Timestamp(cutoff).normalize()
    frame = panel.frame if isinstance(panel, OddsPanel) else panel
    dates = frame["date"].to_numpy()
    lo = (ts - pd.Timedelta(days=MARKET_WINDOW_DAYS)).to_datetime64()
    sel = np.flatnonzero((dates < ts.to_datetime64()) & (dates >= lo))
    if sel.size == 0:
        return frame.iloc[sel].copy()

    home = frame["home"].to_numpy()[sel]
    away = frame["away"].to_numpy()[sel]
    when = dates[sel]
    keep = np.zeros(sel.size, dtype=bool)
    for club in sorted(set(home) | set(away)):
        idx = np.flatnonzero((home == club) | (away == club))
        # `mergesort` is stable, so the ranking of a club's own matches is a
        # function of the panel's canonical order and of nothing else. A club
        # plays at most once a day, so there is no tie to break.
        recent = idx[np.argsort(when[idx], kind="mergesort")][::-1]
        keep[recent[:MARKET_WINDOW_MATCHES]] = True
    return frame.iloc[sel[keep]].copy()


def assert_no_odds_leak(window: pd.DataFrame,
                        cutoff: str | pd.Timestamp) -> int:
    """§5.1's `OddsLeak`: no window row may be dated on or after its cutoff."""
    ts = pd.Timestamp(cutoff).normalize()
    if len(window) == 0:
        return 0
    late = window.loc[window["date"] >= ts]
    if len(late):
        first = late.iloc[0]
        raise OddsLeak(
            f"{len(late)} window row(s) are dated on or after the cutoff "
            f"{ts.date()} — the first is {first['home']} v {first['away']} on "
            f"{pd.Timestamp(first['date']).date()}. §2.3: a fixture kicking "
            "off at or after C contributes nothing to the prior of the fit "
            "that prices it, and this is the leak that would bias the result "
            "toward adoption.")
    return int(len(window))


@dataclass(frozen=True)
class StrengthRecovery:
    """What §2.1 Step 3's weighted ridge least squares recovered at one cutoff."""

    cutoff: str
    strength: dict[str, float]
    eta: float
    condition: float
    n_matches: int
    n_avg: int
    sd: float

    @property
    def avg_share(self) -> float:
        return (self.n_avg / self.n_matches) if self.n_matches else 0.0


def recover_strength(window: pd.DataFrame, cutoff: str | pd.Timestamp, *,
                     check: bool = True) -> StrengthRecovery:
    """§2.1 Steps 2-3: de-vigged market log-odds -> per-club strength.

    ``m_i = log(p_H / p_A) = eta + s[home] - s[away] + residual`` by weighted
    least squares with weights ``0.5 ** (age_days / 365)`` — the pipeline's own
    decay weight (``src/wcmodel/data/features.py:297``) — and a ridge penalty
    ``lambda = 1.0`` on the club coefficients ONLY, never on ``eta``::

        s, eta = solve( X'WX + diag(lam, …, lam, 0),  X'W m )

    ``lambda = 1.0`` is fixed by §2.1, is not selected, and exists to shrink a
    club with few window matches toward the league mean rather than to fit
    anything. Leaving ``eta`` unpenalised matters: ``eta`` is the market's
    implied home advantage, it is a level and not a contrast, and shrinking it
    toward zero would push that level into the club coefficients where §2.2's
    rotation would then treat it as strength.

    The de-vig is ``epl.devig.proportional`` — multiplicative, per the OA
    precedent — applied ONCE when the panel is built, so no caller here can
    choose a different one. Shin is not used and is not swept.
    """
    ts = pd.Timestamp(cutoff).normalize()
    n = int(len(window))
    if n == 0:
        return StrengthRecovery(cutoff=str(ts.date()), strength={}, eta=0.0,
                                condition=0.0, n_matches=0, n_avg=0, sd=0.0)

    home = window["home"].to_numpy()
    away = window["away"].to_numpy()
    clubs = sorted(set(home) | set(away))
    index = {c: i for i, c in enumerate(clubs)}
    k = len(clubs)

    X = np.zeros((n, k + 1), dtype=float)
    X[np.arange(n), [index[c] for c in home]] += 1.0
    X[np.arange(n), [index[c] for c in away]] -= 1.0
    X[:, k] = 1.0

    age = (ts - pd.to_datetime(window["date"])).dt.days.to_numpy(dtype=float)
    weight = 0.5 ** (age / DECAY_HALF_LIFE_DAYS)
    m = window["m"].to_numpy(dtype=float)

    penalty = np.full(k + 1, RIDGE_LAMBDA)
    penalty[k] = 0.0                                   # never on eta
    A = X.T @ (X * weight[:, None]) + np.diag(penalty)
    b = X.T @ (weight * m)
    condition = float(np.linalg.cond(A))
    try:
        solution = np.linalg.solve(A, b)
    except np.linalg.LinAlgError as exc:
        raise RecoveryUnstable(
            f"the ridge normal equations at {ts.date()} are singular over "
            f"{k} club(s) and {n} match(es): {exc}") from exc

    s = solution[:k]
    eta = float(solution[k])
    rec = StrengthRecovery(
        cutoff=str(ts.date()),
        strength={c: float(v) for c, v in zip(clubs, s)},
        eta=eta, condition=condition, n_matches=n,
        n_avg=int((window["src"].to_numpy() == "Avg").sum()),
        sd=float(np.std(s)))

    if check:
        if not np.isfinite(condition) or condition > MAX_CONDITION:
            raise RecoveryUnstable(
                f"the solve at {ts.date()} has condition number "
                f"{condition:.3g} > {MAX_CONDITION:.0g}: the recovered "
                "strengths would be noise dressed as an anchor")
        if not (ETA_BAND[0] <= eta <= ETA_BAND[1]):
            raise RecoveryUnstable(
                f"the recovered home advantage at {ts.date()} is "
                f"{eta:.4f} log-odds, outside the pre-stated band {ETA_BAND}. "
                "§2.1 published 0.2519-0.4429 over the 212 cutoffs, measured "
                "under a per-venue window it did not rule; under the window it "
                "DID rule the same cutoffs give 0.2350-0.4445 "
                "(:data:`MEASURED_ETA`). The band contains both, so it is the "
                "band that was pre-stated and not a band chosen to fit either. "
                "A value outside it means the inversion is not recovering what "
                "it was checked to recover.")
    return rec


def assert_strength_disperses(rec: StrengthRecovery) -> float:
    """§5.1's `DegenerateStrength`: a flat `s` would silently zero the anchor."""
    if not np.isfinite(rec.sd) or rec.sd <= 0.0:
        raise DegenerateStrength(
            f"the cross-club sd of the recovered strengths at {rec.cutoff} is "
            f"{rec.sd!r} over {len(rec.strength)} club(s). z_mkt would be all "
            "zeros and the market term would do nothing — silently, and in a "
            "direction nobody would notice from the estimand.")
    return rec.sd


def z_from_strength(rec: StrengthRecovery,
                    teams: Sequence[str]) -> np.ndarray:
    """§2.1 Step 4: `s` z-scored over the fitted teams, `team_elo_z`'s contract.

    ``wcmodel.model.strength.team_elo_z`` takes ``nanmean``/``nanstd`` over the
    teams it HAS and then sets an absent team to exactly ``0`` — not to
    ``(0 - mean) / sd``. This mirrors that clause for clause, which is what §2.1
    means by "a fitted club with no window match gets z_mkt = 0, the
    no-information shrink to the mean": the absent club sits at the mean of the
    clubs that DO have a window, exactly as an absent club sits at the mean of
    the clubs that do have a rating.

    Population sd (ddof = 0), and all zeros when the dispersion is zero — so
    ``z_mkt`` and ``elo_z`` live on the same scale and can be mixed.
    """
    want = tuple(str(t) for t in teams)
    r = np.array([rec.strength.get(t, np.nan) for t in want], dtype=float)
    present = ~np.isnan(r)
    if not present.any():
        return np.zeros(len(want), dtype=float)
    sd = float(np.std(r[present]))
    if not np.isfinite(sd) or sd == 0.0:
        return np.zeros(len(want), dtype=float)
    z = (r - float(np.mean(r[present]))) / sd
    z[~present] = 0.0
    return z


def market_z(panel: OddsPanel, cutoff: str | pd.Timestamp,
             teams: Sequence[str], *, check: bool = True) -> np.ndarray:
    """``z_mkt(·, cutoff)`` over ``teams`` — §2.1, all four steps."""
    window = market_window(panel, cutoff)
    assert_no_odds_leak(window, cutoff)
    return z_from_strength(recover_strength(window, cutoff, check=check),
                           teams)


# ==========================================================================
# 6. the blend — §2.2's ruling: rotation, not addition
# ==========================================================================
def assert_on_grid(w: float) -> float:
    """§5.1's `GridEscape`: the six points, and no seventh."""
    for point in W_GRID:
        if abs(float(w) - point) < 1e-12:
            return float(point)
    raise GridEscape(
        f"w = {w!r} is not on the frozen grid {list(W_GRID)}. §2.4 fixes six "
        "points and §7 makes an extended grid an invalidation: a weight "
        "chosen after the deltas exist is a weight chosen to suit them.")


def blend(elo_z: Sequence[float], z_mkt: Sequence[float],
          w: float) -> np.ndarray:
    """§2.2: ``z_blend(w) = zscore((1-w)·elo_z + w·z_mkt)``, and
    ``z_blend(0) := elo_z`` EXACTLY.

    THE MARKET TERM DOES NOT ADD A SECOND ANCHOR — IT ROTATES THE ONE THAT
    EXISTS, and four things follow that the additive alternative would have
    left open:

    (i) It enters ``att`` and ``def`` symmetrically at the same ``k``, so the
    SUM of the two log-rates is exactly invariant and the anchor moves the
    MARGIN only. An att-only entry would push expected total goals with a 1X2
    signal that says nothing about totals.

    (ii) The doubled anchor of §0.4 — ``2 x 0.6 = 1.2`` on the strength
    difference — is neither fixed nor widened. Because the output is unit-sd at
    every ``w``, no ``w`` changes how hard the prior pulls; ``w`` changes only
    which direction it pulls in.

    (iii) ``scripts/sweep_strength_k.py``'s settled ``k = 0.6`` is not
    re-opened by accident. The additive form ``0.6·elo_z + k_mkt·z_mkt`` would
    have confounded "the market's information helps" with "a tighter anchor
    helps", because ``z_mkt`` is 91% collinear with ``elo_z`` (§1.4): at
    ``k_mkt = 0.6`` the Elo-direction pull would nearly double to ~1.17 without
    one word of the design saying so.

    (iv) ``w = 1`` becomes the exact input-level analogue of the output blend's
    saturation endpoint — a pure market DIRECTION for the prior, which §2.5
    pre-rules and which is emphatically not the market's forecast.

    ``z_blend(0)`` is ``elo_z`` literally rather than ``zscore(elo_z)`` so that
    §3.2's control is a check on archive drift and not on float round-off.
    """
    weight = assert_on_grid(w)
    ez = np.asarray(elo_z, dtype=float)
    zm = np.asarray(z_mkt, dtype=float)
    if ez.shape != zm.shape:
        raise MarketPriorError(
            f"elo_z has shape {ez.shape} and z_mkt has shape {zm.shape}: the "
            "two vectors are indexed by the same fitted teams or they are not "
            "mixable at all")
    if weight == 0.0:
        return ez.copy()
    mix = (1.0 - weight) * ez + weight * zm
    sd = float(np.std(mix))
    if not np.isfinite(sd) or sd == 0.0:
        return np.zeros(mix.shape, dtype=float)
    return (mix - float(np.mean(mix))) / sd


# ==========================================================================
# 7. the odds canary — §5.4, new because the existing one cannot see odds
# ==========================================================================
#: THE PERTURBATION, and why it is a swap rather than a multiplier. It has to
#: move the de-vigged vector materially AND leave a triple `epl.devig` will
#: accept, or the canary would be testing the de-vig's input validation instead
#: of the leakage rule — a multiplier on one price changes the inverse-price
#: sum and can push it below 1, which no real book has and which
#: `devig.proportional` refuses outright. Exchanging the home and away prices
#: preserves the overround EXACTLY (it is the same three numbers), leaves every
#: price above 1.0 by construction, and moves `m = log(p_H/p_A)` to `-m` — a
#: change of `2|m|`, which is material on every row a real 1X2 book prices.
CANARY_PERTURBATION = "home and away prices exchanged"


def corrupt_odds(panel: OddsPanel, *, on_or_after: str | pd.Timestamp | None = None,
                 before: str | pd.Timestamp | None = None) -> OddsPanel:
    """A copy of ``panel`` with home and away prices exchanged on selected rows."""
    frame = panel.frame.copy()
    dates = frame["date"].to_numpy()
    mask = np.ones(len(frame), dtype=bool)
    if on_or_after is not None:
        mask &= dates >= pd.Timestamp(on_or_after).normalize().to_datetime64()
    if before is not None:
        mask &= dates < pd.Timestamp(before).normalize().to_datetime64()
    home = frame["h"].to_numpy(dtype=float).copy()
    away = frame["a"].to_numpy(dtype=float).copy()
    home[mask], away[mask] = away[mask].copy(), home[mask].copy()
    frame["h"], frame["a"] = home, away

    prices = frame[["h", "d", "a"]].to_numpy(dtype=float)
    p = devig.proportional(prices)
    frame["p_home"], frame["p_draw"], frame["p_away"] = p[:, 0], p[:, 1], p[:, 2]
    frame["m"] = np.log(frame["p_home"].to_numpy(float)
                        / frame["p_away"].to_numpy(float))
    return OddsPanel(frame=frame, sha256=OddsPanel.digest(frame),
                     n_avg=panel.n_avg, n_ps=panel.n_ps,
                     max_date=panel.max_date, sources=panel.sources)


def _canary_z(panel: OddsPanel, cutoff, teams) -> np.ndarray:
    """The real ``z_mkt`` path with §5.1's stability band relaxed.

    The band is relaxed and nothing else is: the same window, the same de-vig,
    the same solve, the same z-score. The positive leg deliberately corrupts
    prices until they are not a book any more, and refusing them for being
    implausible would make the leg that gives the canary its meaning
    unreachable.
    """
    return market_z(panel, cutoff, teams, check=False)


def run_odds_canary(panel: OddsPanel, cutoff: str | pd.Timestamp,
                    teams: Sequence[str], *,
                    z_fn: Callable[..., np.ndarray] | None = None,
                    elo_z: Sequence[float] | None = None,
                    path: Path | str | None = None,
                    write: bool = True) -> dict[str, Any]:
    """§5.4's odds canary — a precondition of the run, not a result.

    ``epl.walkforward.point_in_time_canary`` rewrites RESULTS from a cutoff
    onward and demands identical forecasts. It is blind to the odds panel, so
    it cannot detect a market leak, and this is its analogue:

    * **Negative leg.** Corrupt every panel row dated on or after the cutoff
      and demand ``np.array_equal`` against the uncorrupted anchor. Under §2.3
      this must hold by construction; the canary proves the code IMPLEMENTS the
      rule rather than describing it.
    * **Positive control.** Corrupt panel rows BEFORE the cutoff and demand the
      anchor MOVE by more than 1e-9. A canary that cannot fail is not a canary,
      and this leg is what makes the negative leg mean something.

    Where ``elo_z`` is supplied the same two legs are also run on ``z_blend``
    at every ``w`` on the grid, which is the object §5.4 names. Where it is not,
    the legs run on ``z_mkt``, of which ``z_blend`` is a deterministic function
    at fixed ``elo_z``: a ``z_mkt`` that does not move cannot move ``z_blend``,
    and a ``z_mkt`` that moves moves ``z_blend`` at every ``w > 0``.
    """
    started = time.perf_counter()
    fn = z_fn or _canary_z
    teams = [str(t) for t in teams]
    ts = pd.Timestamp(cutoff).normalize()

    base = np.asarray(fn(panel, ts, teams), dtype=float)
    after = corrupt_odds(panel, on_or_after=ts)
    before = corrupt_odds(panel, before=ts)
    z_after = np.asarray(fn(after, ts, teams), dtype=float)
    z_before = np.asarray(fn(before, ts, teams), dtype=float)

    negative = float(np.max(np.abs(z_after - base))) if base.size else 0.0
    positive = float(np.max(np.abs(z_before - base))) if base.size else 0.0
    identical = bool(np.array_equal(z_after, base))

    blend_legs: list[dict[str, Any]] = []
    if elo_z is not None:
        for w in W_GRID:
            if w == 0.0:
                continue
            b0 = blend(elo_z, base, w)
            blend_legs.append({
                "w": w,
                "identical_after_cutoff": bool(
                    np.array_equal(blend(elo_z, z_after, w), b0)),
                "max_abs_diff_after_cutoff": float(
                    np.max(np.abs(blend(elo_z, z_after, w) - b0))),
                "max_abs_diff_positive_control": float(
                    np.max(np.abs(blend(elo_z, z_before, w) - b0))),
            })

    out: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "cutoff": str(ts.date()),
        "n_teams": len(teams),
        "n_corrupted_after": int(
            (panel.frame["date"] >= ts).sum()),
        "n_corrupted_before": int((panel.frame["date"] < ts).sum()),
        "perturbation": CANARY_PERTURBATION,
        "identical_after_cutoff": identical,
        "max_abs_diff_after_cutoff": negative,
        "max_abs_diff_positive_control": positive,
        "z_blend_legs": blend_legs,
        "panel_sha256": panel.sha256,
        "blas_threads": blas_threads(),
        "seconds": round(time.perf_counter() - started, 2),
    }
    # A leg with nothing to corrupt is not a leg. §5.4's negative leg is only
    # evidence if there WERE odds on or after the cutoff to hide, and the
    # positive control is only a control if there were odds before it to move.
    vacuous = [name for name, n in (("negative", out["n_corrupted_after"]),
                                    ("positive control",
                                     out["n_corrupted_before"])) if n == 0]
    out["vacuous_legs"] = vacuous
    out["PASS"] = bool(
        not vacuous and identical and negative == 0.0 and positive > 1e-9
        and all(leg["identical_after_cutoff"]
                and leg["max_abs_diff_positive_control"] > 1e-9
                for leg in blend_legs))

    path = Path(path) if path is not None else ODDS_CANARY_JSON
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2, default=str) + "\n")
    if not out["PASS"]:
        if vacuous:
            raise MarketCanaryFailed(
                f"the odds canary's {vacuous} leg(s) had nothing to corrupt at "
                f"cutoff {ts.date()}: {out['n_corrupted_after']} panel row(s) "
                f"on or after it and {out['n_corrupted_before']} before it. A "
                "canary run where the corruption cannot reach anything passes "
                "for the wrong reason, which is worse than failing.")
        raise MarketCanaryFailed(
            "the odds canary did not pass: corrupting odds dated on or after "
            f"{ts.date()} moved the anchor by {negative!r} (must be exactly 0) "
            f"and corrupting odds BEFORE it moved the anchor by {positive!r} "
            "(must exceed 1e-9). §5.4: the run does not start. The negative "
            "leg failing is a market leak, which biases toward adoption; the "
            "positive leg failing means the anchor is not reading odds at all, "
            "and a canary that cannot fail is not a canary.")
    return out


def require_odds_canary(path: Path | str | None = None) -> dict[str, Any]:
    """Refuse a fit that has no passing odds canary on the record (§5.4)."""
    path = Path(path) if path is not None else ODDS_CANARY_JSON
    if not path.exists():
        raise MarketCanaryFailed(
            f"no odds canary on the record at {paths.rel(path)}. §5.4 makes it "
            "a precondition of the run, and an absent canary is not a passing "
            "one: run `--odds-canary` first.")
    try:
        rec = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise MarketCanaryFailed(
            f"{paths.rel(path)} is not readable JSON: {exc}") from exc
    if not rec.get("PASS"):
        raise MarketCanaryFailed(
            f"the odds canary on record at {paths.rel(path)} did not pass: "
            f"max |Δz| after the cutoff = "
            f"{rec.get('max_abs_diff_after_cutoff')!r} (must be 0), positive "
            f"control = {rec.get('max_abs_diff_positive_control')!r} (must "
            "move). §5.4: the run does not start.")
    return rec
