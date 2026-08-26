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
    "FitPoint", "assert_config_frozen", "assert_on_grid",
    "assert_no_odds_leak", "corrupt_odds", "read_jsonl",
    "poison_rows", "repair_tail", "z_from_strength",
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

#: §5.2's row contract, at the two levels the ledger carries it. `w`, the
#: market panel's digest and the recovered `eta` are on it because they are
#: what makes THIS experiment's row different from the walk's, and a field
#: nobody wrote is a field nobody can check afterwards.
REQUIRED_ROW_FIELDS = (
    "schema", "key", "match_id", "season", "block", "date", "cutoff", "w",
    "home_key", "away_key", "y", "probs_market_prior", "probs_native",
    "rps_market_prior", "rps_native", "rps_native_recomputed", "delta",
    "seed", "config_sha256", "arm_a", "arm_b", "fit", "harness_frozen",
    "shard_id", "seconds",
)
REQUIRED_FIT_FIELDS = (
    "cutoff", "w", "seed", "config_sha256", "realised_config_sha256",
    "n_training_matches", "n_teams", "n_fixtures", "wall_seconds",
    "match_ids", "cold_start_teams", "provisional_teams", "anchor_spec",
    "warnings", "unpriceable", "health", "harness_sha256", "archive_rows",
    "archive_sha256", "blas_threads", "latest_training_date",
    "panel_sha256", "market_eta", "market_window_matches", "z_blend",
)

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


# ==========================================================================
# 8. the corpus — Arm B, read and never written
# ==========================================================================
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

    §2.6: **Arm B is not recomputed.** This file IS Arm B, and §6 closes the
    set of things this module writes without it in them — the pinned parquet is
    read-only here and two standing preregistrations check its digest in code.
    """
    path = Path(path) if path is not None else CORPUS_PATH
    if not path.exists():
        raise CorpusMissing(
            f"{paths.rel(path)} is not on disk. This experiment is defined on "
            "that corpus by digest; there is nothing to fall back to and "
            "nothing to recompute — §2.6 forbids regenerating it.")
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

    §2.6 rules the tolerance at 1e-12 and records that the realised maximum
    across all 2,280 rows is 0.0 — a guard against a future corpus, not a
    tolerance this one needs.
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
# 9. the schedule — 212 openings x 5 fitted weights = 1,060 fit points
# ==========================================================================
@dataclass(frozen=True)
class FitPoint:
    """One fit: a block opening, a grid weight, and the fixtures it prices.

    ``w`` is part of the POINT and not a setting of the run, which is what
    makes the budget honest: §2.8's 1,060 is 212 cutoffs times the five
    weights that need a fit, and a schedule that carried the weight elsewhere
    could quietly re-run a cutoff under a different one and merge both.
    """

    season: str
    block: str
    cutoff: str                       # ISO date; the cutoff is midnight on it
    w: float
    match_ids: tuple[str, ...]

    def key(self, config_sha: str) -> str:
        return fit_key(self.cutoff, self.w, config_sha=config_sha)


def fit_key(cutoff: str, w: float, seed: int = SEED,
            config_sha: str | None = None) -> str:
    """§5.2's resume key: ``cutoff|w|seed|config_sha256``.

    ``w`` is IN the key. Two fits of the same cutoff at different weights are
    different fits with different answers, and a key that omitted the weight
    would let a resume skip the second one because the first had finished.
    ``w`` is formatted at two decimals — the grid's own resolution — so the key
    is a stable string rather than a float repr.
    """
    return (f"{cutoff}|{assert_on_grid(w):.2f}|{int(seed)}|"
            f"{config_sha or config_sha256()}")


def block_openings(corpus: pd.DataFrame) -> dict[str, str]:
    """block label -> its opening day, as an ISO date string.

    Recomputing the cutoff as each block's minimum fixture date reproduces the
    walk-forward ledger's own ``cutoff`` field for all 2,280 rows, which is why
    the schedule can be derived from the corpus alone.
    """
    opens = corpus.groupby("block")["date"].min()
    return {str(b): str(pd.Timestamp(d).date()) for b, d in opens.items()}


def fit_points(corpus: pd.DataFrame, w: float = 0.0, *,
               check: bool = True) -> list[FitPoint]:
    """The 212 block openings at ONE weight."""
    weight = assert_on_grid(w)
    opens = block_openings(corpus)
    points: list[FitPoint] = []
    for block, part in corpus.groupby(corpus["block"].astype(str), sort=True):
        seasons = sorted(set(part["season"].astype(str)))
        if len(seasons) != 1:
            raise CorpusShapeMismatch(f"block {block} spans seasons {seasons}")
        points.append(FitPoint(
            season=seasons[0], block=str(block), cutoff=opens[str(block)],
            w=weight,
            match_ids=tuple(sorted(str(m) for m in part["match_id"]))))
    points.sort(key=lambda p: (p.cutoff, p.block))
    if check:
        n_fix = sum(len(p.match_ids) for p in points)
        problems = []
        if len(points) != EXPECTED_BLOCKS:
            problems.append(f"{len(points)} blocks, not {EXPECTED_BLOCKS}")
        if n_fix != EXPECTED_FIXTURES:
            problems.append(f"{n_fix} fixtures, not {EXPECTED_FIXTURES}")
        if problems:
            raise CorpusShapeMismatch(
                "; ".join(problems) + ". §0.1 pre-states the counts: a corpus "
                "that does not produce them is a different corpus, not a "
                "smaller experiment.")
    return points


def grid_points(corpus: pd.DataFrame, *, check: bool = True) -> list[FitPoint]:
    """§2.8's whole budget: every block opening at every weight that needs a fit.

    ``w = 0.00`` is on the grid (§2.4) and is NOT here, because a ``w = 0`` fit
    is the corpus's own row (§2.2) and costs nothing. That is the difference
    between 1,272 fits and 1,060, and it is the reason the grid could afford
    six points instead of five.
    """
    points = [p for w in W_GRID if w > 0.0
              for p in fit_points(corpus, w, check=check)]
    points.sort(key=lambda p: (p.cutoff, p.w, p.block))
    if check and len(points) != EXPECTED_FIT_POINTS:
        raise CorpusShapeMismatch(
            f"{len(points)} fit points, not the pre-stated "
            f"{EXPECTED_FIT_POINTS} (§2.8: 212 cutoffs x "
            f"{len([w for w in W_GRID if w > 0])} fitted weights)")
    return points


def fit_point_digest(points: Sequence[FitPoint]) -> str:
    """§6's freeze of the enumerated fit points, by digest.

    The (cutoff, w) pairs and nothing else: the fixtures are a function of the
    corpus, which is already pinned, and the seed and config are already in
    every key.
    """
    body = ";".join(f"{p.cutoff}|{p.w:.2f}"
                    for p in sorted(points, key=lambda p: (p.cutoff, p.w)))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def control_dates(corpus: pd.DataFrame, n: int = N_CONTROL_DATES,
                  seed: int = CONTROL_SEED) -> list[str]:
    """§3.2's twenty dates — **freshness's own**, by freshness's own recipe.

    REUSED VERBATIM so the choice cannot have been made to suit this
    experiment: the same 212 block openings, the same
    ``default_rng(20260826).choice(212, size=20, replace=False)``, the same
    sort. If `epl.freshsweep` is importable the list is taken from IT rather
    than recomputed, so the two can never drift apart silently.
    """
    openings = sorted(set(block_openings(corpus).values()))
    if n > len(openings):
        raise MarketPriorError(f"{n} control dates asked of {len(openings)} "
                               "block openings")
    idx = np.random.default_rng(seed).choice(len(openings), size=n,
                                             replace=False)
    mine = sorted(openings[int(i)] for i in idx)
    try:
        from epl import freshsweep as _fresh
    except Exception:                                    # pragma: no cover
        return mine
    theirs = list(_fresh.control_dates(corpus, n=n, seed=seed))
    if theirs != mine:
        raise ControlMismatch(
            "this module's control dates and epl.freshsweep's disagree: "
            f"{mine[:3]}… against {theirs[:3]}…. §3.2 reuses freshness's own "
            "twenty VERBATIM, and a divergence means one of the two recipes "
            "moved — which would make the reuse a coincidence rather than a "
            "guarantee that the dates were not chosen to suit this run.")
    return theirs


def shard_name(index: int, count: int) -> str:
    return f"shard_{int(index):02d}_of_{int(count):02d}.jsonl"


def shard_points(points: Sequence[FitPoint], index: int,
                 count: int) -> list[FitPoint]:
    """A partition of the fit points — union everything, overlap nothing.

    Strided over ``(cutoff, w)`` rather than blocked, so every shard carries
    the same mix of early and late cutoffs AND the same mix of weights: a
    blocked split would put the cheapest fits (smallest training frames) in one
    shard and the most expensive in another, and the run would be as slow as
    its unluckiest quarter.
    """
    count, index = int(count), int(index)
    if count < 1:
        raise MarketPriorError(f"a shard count of {count} is not a partition")
    if not 0 <= index < count:
        raise MarketPriorError(
            f"shard {index} of {count} does not exist: shards are 0-based and "
            f"the last one is {count - 1}")
    ordered = sorted(points, key=lambda p: (p.cutoff, p.w, p.block))
    return ordered[index::count]


# ==========================================================================
# 10. the ledger — canonical form, digests, conflicts, poison
# ==========================================================================
def _strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in _VOLATILE}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def canonical(rows: Sequence[dict[str, Any]]) -> str:
    """§5.2's canonical form: sorted, volatile fields removed, ``sort_keys``.

    The demand that a resumed run reproduce an uninterrupted one is made HERE
    and not on the raw file, because a row records its own wall clock and its
    own shard and two runs will never agree on those.
    """
    clean = [_strip_volatile(r) for r in rows]
    clean.sort(key=lambda r: (str(r.get("cutoff", "")), float(r.get("w", 0.0)),
                              str(r.get("match_id", "")),
                              str(r.get("key", ""))))
    return json.dumps(clean, sort_keys=True, separators=(",", ":"),
                      default=str)


def run_digest(rows: Sequence[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical(rows).encode("utf-8")).hexdigest()


def _row_identity(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("key", "")), str(row.get("match_id", "")))


def read_jsonl(path: Path | str) -> tuple[list[dict], list[dict], int]:
    """Parse a shard ledger into (rows, poison, dropped-truncated-lines)."""
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
            raise MarketPriorError(
                f"{paths.rel(path)} line {i + 1} is not JSON, and it is not "
                "the last line: only an interrupted append can truncate a "
                "ledger, so this file is corrupted rather than partial")
        (poison if obj.get("poison") else rows).append(obj)
    return rows, poison, dropped


def poison_rows(path: Path | str) -> list[dict]:
    return read_jsonl(path)[1]


def repair_tail(path: Path | str) -> int:
    """Drop a torn final line, and say so. Returns the bytes discarded."""
    path = Path(path)
    if not path.exists():
        return 0
    raw = path.read_bytes()
    if not raw or raw.endswith(b"\n"):
        read_jsonl(path)
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
    """Every fixture row in a shard, de-duplicated, schema-checked, ordered."""
    path = Path(path)
    rows, poison, _ = read_jsonl(path)
    if poison and not allow_poison:
        first = poison[0]
        raise ShardFailed(
            f"{paths.rel(path)} carries {len(poison)} poison row(s); the first "
            f"is {first.get('error_type')} at cutoff {first.get('cutoff')} "
            f"w={first.get('w')}: {first.get('error')}. A failed fit poisons "
            "its shard, and a poisoned shard is never merged or scored.")

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
            a = json.dumps(_strip_volatile(keep[ident]), sort_keys=True,
                           default=str)
            b = json.dumps(_strip_volatile(row), sort_keys=True, default=str)
            if a != b:
                raise RowConflict(
                    f"{paths.rel(path)} holds two rows for {ident} that "
                    "disagree on a scored field. Two fits of the same cutoff "
                    "at the same weight under the same seed and the same "
                    "config are the same fit; if they are not, something moved "
                    "that this experiment holds fixed.")
            continue
        keep[ident] = row

    out = list(keep.values())
    if complete_only:
        by_key: dict[str, list[dict]] = {}
        for row in out:
            by_key.setdefault(str(row["key"]), []).append(row)
        out = [r for group in by_key.values() for r in group
               if len(group) == int(group[0]["fit"]["n_fixtures"])]
    out.sort(key=lambda r: (str(r["cutoff"]), float(r["w"]),
                            str(r["match_id"])))
    return out


def completed_keys(path: Path | str) -> set[str]:
    """The fit keys a shard has FINISHED — partial fits excluded."""
    return {str(r["key"]) for r in load_ledger(path, allow_poison=True,
                                               complete_only=True)}


# ==========================================================================
# 11. Arm A — `epl.dcfit.fit_epl`'s call sequence, with one vector replaced
# ==========================================================================
def fit_market_prior(cutoff, store, anchor, cfg: dict, panel: OddsPanel,
                     w: float, *, matches: pd.DataFrame | None = None,
                     cold_start: Iterable[str] | None = None,
                     feature_cache_dir=None,
                     observed_by=None) -> tuple[Any, Any, dict[str, Any]]:
    """``epl.dcfit.fit_epl``, step for step, with ``z_blend(w)`` in one slot.

    THE SUBSTITUTION IS ONE LINE AND IT IS THE WHOLE EXPERIMENT.
    ``epl/dcfit.py:264-266`` reads::

        state = anchor_state_at(anchor, cutoff, teams, observed_by)
        elo_z = state.elo_z(teams)
        d = build_design(mp, cov=cov, cov_mask=cov_mask, elo_z=elo_z)

    and this function is those three lines with ``blend(elo_z, z_mkt, w)``
    where ``elo_z`` stood. Everything downstream — ``_priors``'
    ``mean_att = k_att * z``, ``mean_def = k_def * z``, the likelihood, the
    widening, the sampler, the posterior, the cold-start extension — is
    ``wcmodel``'s and ``epl.dcfit``'s own code, unmodified and un-patched.

    WHY A CALL SEQUENCE AND NOT A PATCHED IMPORT. ``epl/dcfit.py``'s docstring
    rules on exactly this question — *"an explicit call sequence is auditable;
    a patched import is not"* — and the price of obeying it is that this
    function must be kept in step with ``fit_epl`` by hand. §3.2's control is
    what makes that price safe rather than hopeful: it re-fits at ``w = 0`` and
    demands the corpus's own eight-decimal rows back EXACTLY, so a drift
    between this sequence and ``fit_epl``'s is a STOP and not a silent
    difference in the estimand.

    AT ``w = 0`` NO ODDS ARE READ AT ALL. ``z_blend(0)`` is ``elo_z``
    literally (§2.2), so the market panel cannot reach the design, and this
    function computes no window and inverts nothing. That is deliberate: it
    makes the control a check on the REPLICATION — does this call sequence
    still equal ``fit_epl``'s? — rather than a check that also happens to
    depend on whether the odds archive still parses.
    """
    import time as _time

    from epl.dcfit import (EPL_COVARIATES, ColdStartPosterior, EplFit,
                           _prior_draws, anchor_state_at, cold_start_clubs)
    from wcmodel.data import features as wc_features
    from wcmodel.model.inference import sample
    from wcmodel.model.panel import build_design, to_match_panel
    from wcmodel.model.posterior import Posterior
    from wcmodel.model.scoreline import _build_covariates, build_model
    from wcmodel.model.volatility_diagnostic import count_volatility_arm
    from wcmodel.model.widening import likelihood_weight

    weight = assert_on_grid(w)
    unsupported = [c for c in cfg["model"]["covariates"]["enabled"]
                   if c not in EPL_COVARIATES]
    if unsupported:
        raise FitFailed(
            f"covariate(s) {unsupported} are enabled but have no EPL analogue; "
            "the frozen config enables none, so this guard is inert on the "
            "preregistered path")

    t0 = _time.perf_counter()
    inf = cfg["model"]["inference"]
    likelihood = cfg["model"]["likelihood"]

    feats = wc_features.build_cached(cutoff, store, cfg,
                                     cache_dir=feature_cache_dir)
    mp_panel = to_match_panel(feats)
    assert_panel_in_time(mp_panel, cutoff)
    cov, cov_mask, cov_transforms = _build_covariates(
        mp_panel, cfg["model"]["covariates"])
    teams = sorted(set(mp_panel["home_team"]) | set(mp_panel["away_team"]))
    state = anchor_state_at(anchor, cutoff, teams, observed_by)
    elo_z = state.elo_z(teams)

    # ---- the one substitution -------------------------------------------
    if weight == 0.0:
        z_used = np.asarray(elo_z, dtype=float)
        market: dict[str, Any] = {"w": 0.0, "read_odds": False,
                                  "panel_sha256": None, "eta": None,
                                  "n_window": 0, "condition": None,
                                  "n_window_avg": 0}
    else:
        window = market_window(panel, cutoff)
        assert_no_odds_leak(window, cutoff)
        rec = recover_strength(window, cutoff)
        assert_strength_disperses(rec)
        z_mkt = z_from_strength(rec, teams)
        z_used = blend(elo_z, z_mkt, weight)
        market = {"w": weight, "read_odds": True,
                  "panel_sha256": panel.sha256, "eta": rec.eta,
                  "n_window": rec.n_matches, "condition": rec.condition,
                  "n_window_avg": rec.n_avg,
                  "z_mkt": {t: float(v) for t, v in zip(teams, z_mkt)}}

    d = build_design(mp_panel, cov=cov, cov_mask=cov_mask, elo_z=z_used)
    # ----------------------------------------------------------------------

    wgt = likelihood_weight(d, mechanism=cfg["model"]["widening"]["mechanism"],
                            strength=cfg["model"]["widening"]["strength"])
    model = build_model(d, likelihood=likelihood, weight=wgt, config=cfg)
    idata = sample(model, backend=inf["backend"], draws=int(inf["draws"]),
                   tune=int(inf["tune"]), seed=int(cfg["seed"]),
                   advi_iters=int(inf["advi_iters"]))
    arm = count_volatility_arm(store, cutoff, d.teams, config=cfg)
    prov = set(arm.loc[arm["volatility_flag"] | arm["few_games_flag"], "team"])
    base = Posterior(idata, d.teams, likelihood, provisional_teams=prov,
                     config=cfg, covariate_transforms=cov_transforms)

    cold = (list(cold_start) if cold_start is not None
            else cold_start_clubs(matches, cutoff, d.teams)
            if matches is not None else [])
    # THE COLD-START DRAWS STAY ON THE ELO ANCHOR, and there is no choice to
    # make. §2.2 rules the substitution into `build_design`'s slot and names no
    # other. A cold-start club is one with NO pre-cutoff match, so it is absent
    # from `teams` and from `z_used` alike — there is no market direction to
    # give it, and inventing one would be a second mechanism the document never
    # preregistered.
    extra = {c: _prior_draws(state, c, cfg, base, int(cfg["seed"]))
             for c in cold}
    post = ColdStartPosterior(base, extra)

    market["z_blend"] = {t: float(z) for t, z in zip(teams, z_used)}
    return post, EplFit(
        cutoff=str(pd.Timestamp(cutoff).normalize().date()),
        seconds=round(_time.perf_counter() - t0, 2),
        n_training_matches=int(len(mp_panel)), n_teams=len(d.teams),
        teams=list(d.teams), cold_start_teams=list(cold),
        cold_start_z={c: float(extra[c]["_z"][0]) for c in cold},
        provisional_teams=sorted(post.provisional_teams),
        anchor_spec=str(cfg["elo"].get("epl_anchor_spec", "")),
        elo_z={t: float(z) for t, z in zip(teams, elo_z)},
    ), market


def assert_panel_in_time(match_panel: pd.DataFrame, cutoff) -> str:
    """§5.1's `PanelOutOfDate`, checked where the panel is actually used.

    The feature panel is cached on ``(cutoff, store, config)`` and NOT on ``w``
    — which is correct, and is what lets five weights share one panel and makes
    §2.8's warm budget achievable. It is also the one way that sharing could go
    wrong: a cache entry written under a different bound would be reused here
    without a word. So the panel is checked against its own cutoff every time
    it is read, not once when it is built.
    """
    ts = pd.Timestamp(cutoff).normalize()
    col = next((c for c in ("date", "match_date", "kickoff")
                if c in match_panel.columns), None)
    if col is None:
        raise PanelOutOfDate(
            f"the match panel at {ts.date()} carries no date column "
            f"({list(match_panel.columns)[:8]}…): the point-in-time bound "
            "cannot be checked, and an unchecked bound is not a bound")
    latest = pd.to_datetime(match_panel[col]).max()
    if pd.notna(latest) and latest >= ts:
        raise PanelOutOfDate(
            f"the cached feature panel at cutoff {ts.date()} holds a match "
            f"dated {pd.Timestamp(latest).date()}, on or after it. The panel "
            "cache is keyed on (cutoff, store, config) and shared across the "
            "five weights; a stale entry would leak into every one of them.")
    return str(pd.Timestamp(latest).date()) if pd.notna(latest) else ""


#: The archive fields the digest binds. `epl/schema.py` names the scores
#: `fthg`/`ftag`; the first implementation asked for `home_score`/`away_score`
#: and filtered the absent columns away, so the digest bound ids and dates and
#: NOTHING ELSE — every score in the archive could change under it without
#: moving a hex digit. A digest that silently narrows to the columns it happens
#: to find is not a digest, so the fields are named and their absence refuses.
ARCHIVE_DIGEST_COLUMNS = ("match_id", "date", "fthg", "ftag")


def archive_digest(played: "pd.DataFrame") -> str:
    """SHA-256 over the archive rows that decide a fit: ids, dates, SCORES.

    `archive_sha256` sits on every ledger row to answer one question — *was
    the results archive the same object when this fit ran?* An archive whose
    2-1 became a 3-1 trains a different model, so it must produce a different
    digest or the field is decoration.
    """
    missing = [c for c in ARCHIVE_DIGEST_COLUMNS if c not in played.columns]
    if missing:
        raise SchemaMismatch(
            f"the results archive lacks {missing}, which "
            f"{list(ARCHIVE_DIGEST_COLUMNS)} names: the digest binds the "
            "scores a fit trains on, and a column filter that quietly drops "
            "them would bind ids and dates and nothing else.")
    frame = played[list(ARCHIVE_DIGEST_COLUMNS)].astype(str)
    frame = frame.sort_values("match_id")
    return hashlib.sha256(
        frame.to_csv(index=False).encode("utf-8")).hexdigest()


# ==========================================================================
# 12. the engine — the walk's own machinery, one market prior substituted
# ==========================================================================
class Engine:
    """Built once, reused per fit: the store, the anchor, the panel, the config.

    Everything here is read from `epl.walkforward`, `epl.fit` and `epl.freeze`
    rather than rebuilt — the same frozen config, the same `Anchor` over the
    same played frame, the same `build_store`, the same `config_read_once` fast
    panel. What it does NOT reuse is `walkforward._one_cutoff`, because that
    function calls `fit_epl` and this arm's whole content is the vector
    `fit_epl` does not take. :meth:`fit` is `_one_cutoff`'s pricing loop over
    :func:`fit_market_prior`, and §3.2's control at ``w = 0`` is the check that
    the two still agree to the corpus's last decimal.
    """

    def __init__(self, corpus: pd.DataFrame, matches: pd.DataFrame | None = None,
                 *, panel: OddsPanel | None = None, verbose: bool = True):
        from epl import anchor as anchor_mod, baseline, fit as epl_fit, freeze
        from epl.schema import sort_for_walk_forward

        self._epl_fit = epl_fit
        self.config_sha256 = assert_config_frozen()
        self.cfg = freeze.frozen_wcmodel_config()
        if int(self.cfg["seed"]) != SEED:
            raise ConfigNotFrozen(
                f"the realised configuration's seed is {self.cfg['seed']}, not "
                f"{SEED}: §2.6 fixes the seed as ONE CONSTANT")
        strength = self.cfg["model"].get("strength_prior") or {}
        if not (strength.get("enabled")
                and float(strength.get("k_att", -1)) == K_ATT
                and float(strength.get("k_def", -1)) == K_DEF):
            raise ConfigNotFrozen(
                f"the realised strength_prior is {strength!r}, not enabled at "
                f"k_att = k_def = {K_ATT}. §2.2 rules the anchor scale FROZEN "
                "and this experiment does not move it: `w` changes which "
                "direction the prior pulls, never how hard.")
        self.realised_config_sha256 = hashlib.sha256(
            json.dumps(self.cfg, sort_keys=True, default=str).encode()
        ).hexdigest()

        matches = baseline.load_matches() if matches is None else matches
        self.played = sort_for_walk_forward(matches.loc[matches["played"]])
        self.matches = matches
        self.anchor = anchor_mod.Anchor(self.played, freeze.frozen_elo_config())
        self.store = epl_fit.build_store(self.played)
        self.panel = panel if panel is not None else build_panel()
        assert_panel(self.panel)
        self._ids = self.played["match_id"].astype(str).to_numpy()
        self._pos = {m: i for i, m in enumerate(self._ids)}
        self.archive_rows = int(len(self.played))
        self.archive_sha256 = self._archive_digest()
        self.harness_sha256 = sha256_file(paths.REPO_ROOT / HARNESS_FILES[0])
        self._ctx = None
        self.verbose = verbose
        missing = [m for m in corpus["match_id"].astype(str)
                   if m not in self._pos]
        if missing:
            raise UnpriceableFixture(
                f"{len(missing)} corpus fixtures are absent from the archive "
                f"(first: {missing[:3]}): Arm A cannot price a fixture the "
                "archive does not carry, and §2.6 forbids dropping one")

    def _archive_digest(self) -> str:
        return archive_digest(self.played)

    def __enter__(self) -> "Engine":
        self._ctx = self._epl_fit.config_read_once(self.cfg)
        self._ctx.__enter__()
        return self

    def __exit__(self, *exc) -> bool:
        ctx, self._ctx = self._ctx, None
        return bool(ctx.__exit__(*exc)) if ctx is not None else False

    def fit(self, point: FitPoint) -> dict[str, Any]:
        """One fit at ``point.cutoff`` under ``point.w``, then price the block."""
        import warnings as _warnings

        t0 = time.perf_counter()
        cutoff = pd.Timestamp(point.cutoff).normalize()
        pit = self._epl_fit.assert_point_in_time(self.store, cutoff)
        if str(pit["latest_training_date"]) >= point.cutoff:
            raise CutoffLeak(
                f"the STORE's latest training date at {point.cutoff} is "
                f"{pit['latest_training_date']}, on or after the cutoff")

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            post, res, market = fit_market_prior(
                cutoff, self.store, self.anchor, self.cfg, self.panel, point.w,
                matches=self.matches,
                feature_cache_dir=paths.FIT_CACHE_DIR)
            warns = sorted({f"{w.category.__name__}: {w.message}"
                            for w in caught})

        rows = np.array([self._pos[m] for m in point.match_ids], dtype=int)
        home = self.played["home_key"].astype(str).to_numpy()[rows]
        away = self.played["away_key"].astype(str).to_numpy()[rows]
        probs, unpriceable = [], []
        for mid, h, a in zip(point.match_ids, home, away):
            if h not in post._idx or a not in post._idx:
                probs.append([float("nan")] * 3)
                unpriceable.append({"match_id": mid, "home": h, "away": a,
                                    "why": "club absent from the posterior "
                                           "index"})
                continue
            p = post.predict_1x2(h, a, neutral=False)
            probs.append([float(p[k]) for k in score_mod.OUTCOMES])

        arr = np.asarray(probs, dtype=float)
        return {
            "cutoff": point.cutoff, "w": point.w, "season": point.season,
            "block": point.block, "n_fixtures": len(point.match_ids),
            "match_ids": list(point.match_ids),
            "probs": [[round(v, 8) for v in row] for row in arr.tolist()],
            "seconds": round(time.perf_counter() - t0, 2),
            "n_training_matches": res.n_training_matches,
            "n_teams": res.n_teams,
            "cold_start_teams": res.cold_start_teams,
            "cold_start_z": res.cold_start_z,
            "provisional_teams": res.provisional_teams,
            "anchor_spec": res.anchor_spec, "warnings": warns,
            "unpriceable": unpriceable,
            "latest_training_date": pit["latest_training_date"],
            "n_training_matches_store": pit["n_training_matches"],
            "market": market,
            "health": self._health(post),
        }

    def _health(self, post) -> dict[str, Any]:
        from epl import walkforward as wf
        return wf._health(post, self.cfg)


# ==========================================================================
# 13. the runner
# ==========================================================================
def _fit_provenance(point: FitPoint, out: dict, *, config_sha: str,
                    realised_sha: str, harness_sha: str, archive_rows: int,
                    archive_sha: str, wall: float) -> dict[str, Any]:
    market = dict(out.get("market") or {})
    return {
        "cutoff": point.cutoff, "w": float(point.w), "seed": SEED,
        "config_sha256": config_sha, "realised_config_sha256": realised_sha,
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
        "panel_sha256": market.get("panel_sha256"),
        "market_eta": market.get("eta"),
        "market_window_matches": market.get("n_window"),
        "market_window_avg": market.get("n_window_avg"),
        "market_condition": market.get("condition"),
        "read_odds": market.get("read_odds"),
        "z_blend": market.get("z_blend", {}),
        "z_mkt": market.get("z_mkt", {}),
        "wall_seconds": round(wall, 3),
        "fit_seconds": out.get("seconds"),
    }


def _check_fit(point: FitPoint, out: dict) -> np.ndarray:
    """Everything that makes a fit unusable, refused by its own name."""
    if out.get("unpriceable"):
        raise UnpriceableFixture(
            f"{point.cutoff} w={point.w}: {out['unpriceable']}. §2.6 fixes the "
            "denominator at 2,280 and Arm A sees the same matches as Arm B, so "
            "an unpriceable fixture here is a defect, never a dropped row.")
    health = out.get("health", {})
    bad = [k for k in ("all_finite", "sigma_positive", "home_adv_sane")
           if not health.get(k, True)]
    if bad:
        raise FitFailed(f"{point.cutoff} w={point.w}: the posterior fails "
                        f"{bad} — {health}")
    probs = np.asarray(out["probs"], dtype=float)
    if probs.shape != (len(point.match_ids), 3):
        raise FitFailed(f"{point.cutoff} w={point.w}: {probs.shape} "
                        f"probabilities for {len(point.match_ids)} fixtures")
    if not np.isfinite(probs).all() or \
            not np.allclose(probs.sum(axis=1), 1.0, atol=1e-9):
        raise FitFailed(
            f"{point.cutoff} w={point.w}: a forecast is non-finite or does not "
            "sum to 1 (worst |sum-1| = "
            f"{float(np.max(np.abs(probs.sum(axis=1) - 1.0))):.3g})")
    return probs


def _poison(ledger_path: Path, point: FitPoint, key: str, exc: BaseException,
            shard_id: str) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a") as fh:
        fh.write(json.dumps({
            "schema": SCHEMA_ID, "poison": True, "key": key,
            "cutoff": point.cutoff, "w": float(point.w),
            "season": point.season, "match_ids": list(point.match_ids),
            "error_type": type(exc).__name__, "error": str(exc),
            "shard_id": shard_id,
            "started_at": pd.Timestamp.now("UTC").isoformat(),
        }, default=str) + "\n")


def _fixture_row(point: FitPoint, match_id: str, probs: np.ndarray,
                 corpus_row: pd.Series, fit: dict, *, key: str,
                 config_sha: str, shard_id: str, wall: float,
                 harness_frozen: bool) -> dict[str, Any]:
    """One paired fixture: Arm A computed, Arm B copied, both with provenance."""
    a = [float(v) for v in probs]
    b = [float(corpus_row[c]) for c in _PROB_COLUMNS]
    y = int(corpus_row["y"])
    rps_a = float(score_mod.rps(np.array([a]), np.array([y]))[0])
    rps_b_recomputed = float(score_mod.rps(np.array([b]), np.array([y]))[0])
    rps_b = float(corpus_row["dc_rps"])
    if abs(rps_b_recomputed - rps_b) > 1e-12:
        raise ScoreMismatch(
            f"{match_id}: stored dc_rps {rps_b!r} and the RPS of the stored "
            f"probabilities {rps_b_recomputed!r} differ by "
            f"{abs(rps_b_recomputed - rps_b):.3g}")
    return {
        "schema": SCHEMA_ID, "key": key, "match_id": match_id,
        "season": point.season, "block": point.block,
        "date": point.cutoff, "cutoff": point.cutoff, "w": float(point.w),
        "home_key": str(corpus_row["home_key"]),
        "away_key": str(corpus_row["away_key"]), "y": y,
        "probs_market_prior": a, "probs_native": b,
        "rps_market_prior": rps_a, "rps_native": rps_b,
        "rps_native_recomputed": rps_b_recomputed,
        "delta": rps_a - rps_b,
        "seed": SEED, "config_sha256": config_sha,
        "arm_a": {
            "arm": ARM_NAME,
            "source": "epl.mktprior.fit_market_prior (epl.dcfit.fit_epl's "
                      "call sequence with z_blend(w) in build_design's elo_z "
                      "slot)",
            "cutoff": point.cutoff, "w": float(point.w), "seed": SEED,
            "config_sha256": config_sha,
            "realised_config_sha256": fit["realised_config_sha256"],
            "harness_sha256": fit["harness_sha256"],
            "archive_rows": fit["archive_rows"],
            "archive_sha256": fit["archive_sha256"],
            "panel_sha256": fit["panel_sha256"],
            "odds_columns": "Avg opening (AvgH/AvgD/AvgA), PS before 2019/20",
            "predict": "post.predict_1x2(home, away, neutral=False)",
            "rounding": "round(v, 8)",
        },
        "arm_b": {
            "arm": BASELINE_ARM, "source": paths.rel(CORPUS_PATH),
            "corpus_sha256": CORPUS_SHA256, "cutoff": point.cutoff,
            "columns": list(_PROB_COLUMNS) + ["dc_rps"],
            "recomputed": False,
        },
        "fit": fit, "harness_frozen": bool(harness_frozen),
        "shard_id": shard_id, "seconds": round(wall, 3),
        "wall_seconds": round(wall, 3),
        "started_at": pd.Timestamp.now("UTC").isoformat(),
        "host": socket.gethostname(),
    }


def _guard_ledger_location(path: Path, harness_frozen: bool) -> None:
    """The preregistered run directory is closed until §6's freeze commit.

    Not only the ledger. The canaries and the control are fits too, and §6 step
    3 is *"only then does the first fit run"*. More to the point, a pre-freeze
    `control.json` left in the run directory is exactly what a later `--run`
    reads as *the control passed*: the record does not carry the harness bytes
    it was produced under, so the directory has to.
    """
    if harness_frozen:
        return
    try:
        inside = path.resolve().is_relative_to(MKTPRIOR_DIR.resolve())
    except (OSError, ValueError):
        inside = False
    if inside:
        raise MarketPriorError(
            f"refusing to write {paths.rel(path)} before §6's harness-hash "
            "freeze commit exists. §7: a fit that runs before the "
            "harness-hash commit of §6 exists invalidates the "
            "preregistration. Audit runs are legitimate — give them their own "
            f"directory outside {paths.rel(MKTPRIOR_DIR)} with --dir, where "
            "every row is stamped harness_frozen: false and the merge will "
            "not score them.")


def run_fits(points: Sequence[FitPoint], ledger_path: Path | str,
             corpus: pd.DataFrame, *,
             fitter: Callable[[FitPoint], dict] | None = None,
             engine: "Engine | None" = None,
             shard_id: str = "0/1", resume: bool = True, verbose: bool = True,
             harness_frozen: bool = True) -> dict[str, Any]:
    """Fit every point and append one JSONL row per fixture.

    Resumable per fit, keyed ``cutoff|w|seed|config_sha256`` (§5.2): a key
    already complete in the ledger is skipped — not re-run, not re-scored, not
    appended twice. A fit's rows are written in ONE append so a crash leaves
    either all of them or a truncated tail that :func:`load_ledger` drops and
    this function re-runs.

    A FAILED FIT POISONS ITS SHARD and re-raises. Nothing here catches a
    failure and carries on: §5.1 rules that a failed shard poisons the merge,
    and a runner that skipped a bad fit would produce a ledger that is short by
    exactly the fits most likely to matter.
    """
    ledger_path = Path(ledger_path)
    _guard_ledger_location(ledger_path, harness_frozen)

    if fitter is None:
        engine = engine or Engine(corpus, verbose=verbose)
        fitter = engine.fit
    config_sha = engine.config_sha256 if engine else config_sha256()
    realised_sha = (engine.realised_config_sha256 if engine
                    else "injected-fitter")
    harness_sha = engine.harness_sha256 if engine else "stub-harness"
    archive_rows = engine.archive_rows if engine else -1
    archive_sha = engine.archive_sha256 if engine else "stub-archive"

    torn = repair_tail(ledger_path)
    if torn and verbose:
        print(f"[mkt] dropped {torn} torn byte(s) from the tail of "
              f"{paths.rel(ledger_path)}: that fit is incomplete and re-runs",
              flush=True)

    stale = poison_rows(ledger_path)
    if stale:
        first = stale[0]
        raise ShardFailed(
            f"{paths.rel(ledger_path)} still carries {len(stale)} poison "
            f"row(s) — the first is {first.get('error_type')} at "
            f"{first.get('cutoff')} w={first.get('w')}: {first.get('error')}. "
            "Fail closed: re-running over poison would leave the poison in "
            "place, the merge would refuse anyway, and the fits would have "
            "been paid for twice. Inspect the failure, then remove this "
            "shard's ledger and re-run the shard.")

    done = completed_keys(ledger_path) if resume else set()
    by_id = corpus.set_index(corpus["match_id"].astype(str))
    todo = [p for p in points if p.key(config_sha) not in done]
    if verbose:
        print(f"[mkt] shard {shard_id}: {len(points)} fit points, "
              f"{len(points) - len(todo)} already complete, {len(todo)} to run",
              flush=True)

    started = time.time()
    n_rows = 0
    for i, point in enumerate(todo, 1):
        key = point.key(config_sha)
        t0 = time.perf_counter()
        try:
            out = fitter(point)
            probs = _check_fit(point, out)
        except MarketPriorError as exc:
            _poison(ledger_path, point, key, exc, shard_id)
            raise
        except Exception as exc:                     # noqa: BLE001 — typed below
            wrapped = FitFailed(f"{point.cutoff} w={point.w}: "
                                f"{type(exc).__name__}: {exc}")
            _poison(ledger_path, point, key, wrapped, shard_id)
            raise wrapped from exc

        wall = time.perf_counter() - t0
        fit = _fit_provenance(point, out, config_sha=config_sha,
                              realised_sha=realised_sha,
                              harness_sha=harness_sha,
                              archive_rows=archive_rows,
                              archive_sha=archive_sha, wall=wall)
        lines = [json.dumps(
            _fixture_row(point, str(mid), prob, by_id.loc[str(mid)], fit,
                         key=key, config_sha=config_sha, shard_id=shard_id,
                         wall=wall, harness_frozen=harness_frozen),
            default=str) for mid, prob in zip(point.match_ids, probs)]
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
        n_rows += len(lines)
        if verbose:
            el = time.time() - started
            print(f"[mkt] {i}/{len(todo)} {point.cutoff} w={point.w:.2f} "
                  f"n_train={fit['n_training_matches']} "
                  f"fixtures={len(point.match_ids)} {wall:.1f}s "
                  f"(elapsed {el / 60:.1f}m, eta "
                  f"{el / i * (len(todo) - i) / 60:.1f}m)", flush=True)

    rows = load_ledger(ledger_path)
    return {"shard_id": shard_id, "n_fits": len(todo), "n_rows_written": n_rows,
            "repaired_bytes": int(torn), "n_fixtures": len(rows),
            "n_skipped": len(points) - len(todo),
            "seconds": round(time.time() - started, 1),
            "ledger": str(ledger_path), "run_digest": run_digest(rows),
            "harness_frozen": bool(harness_frozen)}


# ==========================================================================
# 14. the preconditions — two canaries (§5.3, §5.4), then the control (§3.2)
# ==========================================================================
def run_canary(runner: Callable[[], dict[str, Any]] | None = None, *,
               path: Path | str | None = None,
               write: bool = True) -> dict[str, Any]:
    """§5.3's point-in-time canary — the RESULTS leg, unchanged and reused.

    ``epl.walkforward.point_in_time_canary`` rewrites every result from a
    cutoff onward and demands ``np.array_equal`` on the forecasts a fit at that
    cutoff produces, with a positive control proving the corruption landed. It
    is reused verbatim rather than re-implemented, and it is NOT sufficient on
    its own: it is blind to the odds panel, which is why §5.4's
    :func:`run_odds_canary` exists beside it.
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
            "flatter Arm A, which is the arm an adoption would be granted on. "
            f"The full dict is on the record at {paths.rel(path)}.")
    return out


def require_canary(path: Path | str | None = None) -> dict[str, Any]:
    """Refuse a fit that has no passing point-in-time canary (§5.3)."""
    path = Path(path) if path is not None else CANARY_JSON
    if not path.exists():
        raise CanaryFailed(
            f"no point-in-time canary on the record at {paths.rel(path)}. §5.3 "
            "makes it a precondition of the run, and an absent canary is not a "
            "passing one: run `--canary` first.")
    try:
        rec = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise CanaryFailed(
            f"{paths.rel(path)} is not readable JSON: {exc}") from exc
    if not rec.get("PASS"):
        raise CanaryFailed(
            f"the canary on record at {paths.rel(path)} did not pass: max "
            f"|Δp| before the cutoff = "
            f"{rec.get('max_abs_diff_before_cutoff')!r}. §5.3: the run does "
            "not start.")
    return rec


def run_control(dates: Sequence[str] | None = None,
                corpus: pd.DataFrame | None = None, *,
                fitter: Callable[[FitPoint], dict] | None = None,
                engine: "Engine | None" = None,
                limit: int | None = None, verbose: bool = True,
                write: bool = False,
                path: Path | str | None = None) -> dict[str, Any]:
    """§3.2: re-fit at ``w = 0`` and demand the corpus's own rows back.

    THE TOLERANCE IS EXACT EQUALITY at the corpus's eight decimals, ruled
    before any row existed and not a number to be widened after seeing a
    difference.

    WHAT IT ACTUALLY CHECKS, and it is two things. First the REPLICATION:
    :func:`fit_market_prior` restates ``fit_epl``'s call sequence by hand
    (§2.7's seam), and at ``w = 0`` the two must be the same function — if this
    module has drifted from ``epl/dcfit.py``, this is where it shows, before
    any weighted fit has been paid for. Second ARCHIVE DRIFT: the archive grew
    after the walk, and Arm A builds its store and anchor from the archive as
    it stands at run time, relying on the point-in-time property to make later
    data irrelevant. Either way a mismatch is a STOP.

    THE TWENTY DATES ARE FRESHNESS'S OWN, reused verbatim (§3.2) so that the
    choice of control dates cannot have been made to suit this experiment.
    """
    corpus = load_corpus() if corpus is None else corpus
    threads = (assert_blas_pinned("the w = 0 identity control") if fitter is None
               else blas_threads())

    openings = {p.cutoff: p for p in fit_points(corpus, 0.0, check=False)}
    dates = list(dates) if dates is not None else control_dates(corpus)
    if limit:
        dates = dates[:limit]
    unknown = [d for d in dates if d not in openings]
    if unknown:
        raise ControlMismatch(f"{unknown} are not block-opening dates")

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
            if point.w != 0.0:                          # unreachable by design
                raise ControlMismatch(
                    f"the control point at {date} carries w = {point.w}, not "
                    "0.00: §3.2's control IS the w = 0 identity, and a control "
                    "that read odds would be checking something else")
            t0 = time.perf_counter()
            out = fitter(point)
            probs = _check_fit(point, out)
            rows = []
            for mid, prob in zip(point.match_ids, probs):
                stored = [float(by_id.loc[str(mid), c]) for c in _PROB_COLUMNS]
                got = [round(float(v), 8) for v in prob]
                d = [abs(a - b) for a, b in zip(got, stored)]
                diffs.extend(d)
                y = int(by_id.loc[str(mid), "y"])
                r = float(score_mod.rps(np.array([got]), np.array([y]))[0])
                worst_rps = max(worst_rps,
                                abs(r - float(by_id.loc[str(mid), "dc_rps"])))
                rows.append({"match_id": str(mid),
                             "exact": all(a == b for a, b in zip(got, stored)),
                             "stored": stored, "refit": got,
                             "max_abs_diff": max(d)})
            detail.append({"cutoff": date, "n_fixtures": len(point.match_ids),
                           "all_exact": all(r["exact"] for r in rows),
                           "max_abs_diff": max((r["max_abs_diff"]
                                                for r in rows), default=0.0),
                           "read_odds": bool(
                               (out.get("market") or {}).get("read_odds")),
                           "seconds": round(time.perf_counter() - t0, 2),
                           "fixtures": rows})
            if verbose:
                print(f"[control] {i}/{len(dates)} {date} "
                      f"n={len(point.match_ids)} "
                      f"max|dp|={detail[-1]['max_abs_diff']:.3g} "
                      f"{detail[-1]['seconds']}s", flush=True)

    worst = max(diffs) if diffs else 0.0
    result = {
        "schema": SCHEMA_ID, "w": 0.0,
        "n_dates": len(dates), "dates": list(dates),
        "n_fixtures": sum(d["n_fixtures"] for d in detail),
        "n_probabilities": len(diffs),
        "max_abs_prob_diff": worst,
        "mean_abs_prob_diff": float(np.mean(diffs)) if diffs else 0.0,
        "max_abs_rps_diff": worst_rps,
        "tolerance": "exact equality at the corpus's 8 decimals",
        "rps_tolerance": 1e-12,
        "dates_source": "epl.freshsweep.control_dates, reused verbatim (§3.2)",
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
            f"the w = 0 identity control does not return the corpus's own "
            f"rows: max |Δp| = {worst:.3g} ({worst!r}), max |ΔRPS| = "
            f"{worst_rps:.3g}, at {offenders[:5]}. §3.2 rules EXACT equality "
            "at the corpus's eight decimals and forbids widening the tolerance "
            "after seeing a difference. Either fit_market_prior has drifted "
            "from epl.dcfit.fit_epl's call sequence, or the archive has moved "
            "since the walk. Both invalidate the pairing the whole design "
            "rests on: STOP, and write the amendment before anything continues.")
    return result


def require_control(path: Path | str | None = None, *,
                    dates: Sequence[str] | None = None) -> dict[str, Any]:
    """Refuse a weighted fit before the ``w = 0`` control has passed (§3.2)."""
    path = Path(path) if path is not None else CONTROL_JSON
    if not path.exists():
        raise ControlMismatch(
            f"the w = 0 identity control has not run: there is no record at "
            f"{paths.rel(path)}. §3.2: the control runs FIRST, and not one "
            "weighted fit runs until it passes. Run `--control` first.")
    try:
        rec = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ControlMismatch(
            f"{paths.rel(path)} is not readable JSON: {exc}") from exc
    if not rec.get("PASS"):
        raise ControlMismatch(
            f"the control on record at {paths.rel(path)} did not pass: max "
            f"|Δp| = {rec.get('max_abs_prob_diff')!r}. §3.2 rules EXACT "
            "equality and forbids widening the tolerance after the fact.")
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
                              odds_canary_path: Path | str | None = None,
                              control_path: Path | str | None = None,
                              dates: Sequence[str] | None = None,
                              ) -> dict[str, Any]:
    """:data:`RUN_ORDER`, enforced rather than declared.

    Both canaries, then the control. They are checked from their written
    records, so the order holds across processes and across shards — four
    workers each re-running the canary would be four answers to a question
    with one.
    """
    directory = Path(directory) if directory is not None else MKTPRIOR_DIR
    canary = require_canary(canary_path if canary_path is not None
                            else directory / CANARY_NAME)
    odds = require_odds_canary(odds_canary_path if odds_canary_path is not None
                               else directory / ODDS_CANARY_NAME)
    control = require_control(control_path if control_path is not None
                              else directory / CONTROL_NAME, dates=dates)
    return {"canary": canary, "odds_canary": odds, "control": control}


# ==========================================================================
# 15. the selection — §2.4's leave-one-season-out, in-fold, never on `s`
# ==========================================================================
def select_w(rows: Sequence[dict[str, Any]], *,
             seasons: Sequence[str] | None = None,
             corpus: pd.DataFrame | None = None) -> dict[str, Any]:
    """§2.4: for each season, the argmin over the OTHER five, ties to smaller `w`.

    The rows are every fitted fixture at every grid weight. For season ``s``:

    1. Score every grid ``w`` on the other five seasons' fixtures by mean RPS.
    2. Take the argmin; **ties break toward the smaller ``w``**, which is
       ``src/wcmodel/eval/blend.py``'s own frozen tie order, adopted rather
       than invented.
    3. Season ``s``'s fixtures are priced at THAT ``w``.

    ``w = 0.00`` is on the grid and needs no fits — its RPS in any fold is the
    corpus's own ``rps_native``, which every row carries. So the selection can
    genuinely answer *"no market term"*, and it costs nothing to let it.

    FOLDLEAK IS THE POINT OF THE FUNCTION. A fold that contained one fixture of
    the season it prices would make the selection an in-sample choice, and the
    estimand would be the maximum of six grid points rather than an honest
    out-of-fold number. It is checked per fold, by season label, and refused.
    """
    if not rows:
        raise MarketPriorError("no rows to select on")
    seasons = (list(seasons) if seasons is not None
               else sorted({str(r["season"]) for r in rows}))

    # THE FOLD IS BUILT BY SEASON LABEL, SO THE LABEL IS WHAT HAS TO BE
    # CHECKED. Splitting on `season != s` cannot itself admit a fixture of
    # season `s` — that much is arithmetic — so a guard phrased against the
    # split would be a guard that can never fire. The reachable failure is one
    # layer earlier: a ledger row carrying the WRONG season for its fixture
    # puts a season-`s` match into every other season's fold under another
    # name, and the split would never notice. So the labels are checked
    # against the corpus, which is the only independent record of which season
    # a fixture belongs to.
    if corpus is not None:
        truth = {str(m): str(s) for m, s in zip(corpus["match_id"],
                                                corpus["season"])}
        # The absent fixture is reported FIRST and by its own name: it would
        # also trip the label check (a missing truth is not the row's season),
        # but "the corpus does not carry this match" is the actionable fact
        # and "its season disagrees with None" is not.
        unknown = sorted({str(r["match_id"]) for r in rows
                          if str(r["match_id"]) not in truth})
        if unknown:
            raise FoldLeak(
                f"{len(unknown)} ledger row(s) price a fixture the corpus does "
                f"not carry (first: {unknown[:3]}): it belongs to no fold and "
                "no season, and §2.6 fixes the denominator on the corpus.")
        wrong = sorted({(str(r["match_id"]), str(r["season"]),
                         truth[str(r["match_id"])])
                        for r in rows
                        if truth[str(r["match_id"])] != str(r["season"])})
        if wrong:
            raise FoldLeak(
                f"{len(wrong)} ledger row(s) carry a season the corpus does "
                f"not agree with (first: {wrong[:3]}). The folds are built by "
                "season label, so a mislabelled fixture is a fixture of the "
                "scored season sitting inside its own selection fold under "
                "another name — which would make §2.4's selection in-sample "
                "and the estimand the maximum of six grid points.")

    # w = 0 is Arm B: its per-fixture RPS is the corpus's own stored number,
    # taken from whichever fitted row carries the fixture (they all carry it).
    native: dict[str, tuple[str, float]] = {}
    scored: dict[float, dict[str, tuple[str, float]]] = {}
    for r in rows:
        mid, season = str(r["match_id"]), str(r["season"])
        native[mid] = (season, float(r["rps_native"]))
        scored.setdefault(float(r["w"]), {})[mid] = (
            season, float(r["rps_market_prior"]))
    scored[0.0] = native

    missing = [w for w in W_GRID if w not in scored]
    if missing:
        raise GridEscape(
            f"the ledger carries no rows at w = {missing}: §2.4's selection "
            "compares all six grid points and cannot choose among a subset. "
            "A grid silently shortened by a failed shard would select the best "
            "of what survived.")

    folds, selected = [], {}
    for season in seasons:
        means = []
        for w in W_GRID:
            fold = [(mid, rps) for mid, (s, rps) in scored[w].items()
                    if s != season]
            held_out = sum(1 for _, (s, _) in scored[w].items() if s == season)
            if held_out == 0:
                raise FoldLeak(
                    f"season {season} has no fixtures at w = {w} to hold out, "
                    "so leaving it out leaves nothing out: the fold is the "
                    "whole ledger and the selection is not out-of-fold")
            if len(fold) + held_out != len(scored[w]):
                raise FoldLeak(
                    f"the fold for season {season} at w = {w} holds "
                    f"{len(fold)} of {len(scored[w])} fixtures with "
                    f"{held_out} held out: the split is not a partition")
            if not fold:
                raise FoldLeak(
                    f"the fold for season {season} at w = {w} is empty: a "
                    "selection made on no data is not an out-of-fold selection")
            means.append((float(np.mean([rps for _, rps in fold])), float(w)))
        # (mean RPS, w) ascending — blend.py's own frozen tie order, so a tie
        # goes to the SMALLER w and therefore to less market dependence.
        best_mean, best_w = min(means, key=lambda t: (t[0], t[1]))
        selected[season] = assert_on_grid(best_w)
        folds.append({"season": season, "selected_w": best_w,
                      "fold_mean_rps": best_mean,
                      "n_fold_fixtures": len(scored[best_w]) -
                      sum(1 for _, (s, _) in scored[best_w].items()
                          if s == season),
                      "grid": [{"w": w, "fold_mean_rps": m}
                               for m, w in sorted(means, key=lambda t: t[1])]})

    at_max = [f["season"] for f in folds if f["selected_w"] == max(W_GRID)]
    at_zero = [f["season"] for f in folds if f["selected_w"] == 0.0]
    return {
        "schema": SCHEMA_ID, "method": "leave-one-season-out, in-fold",
        "grid": list(W_GRID), "tie_order": "(mean RPS, w) ascending — "
        "src/wcmodel/eval/blend.py's frozen order; ties go to the smaller w",
        "selected": selected, "folds": folds,
        "n_folds_at_grid_max": len(at_max), "folds_at_grid_max": at_max,
        "n_folds_at_zero": len(at_zero), "folds_at_zero": at_zero,
        "saturated": bool(at_max),
        "all_zero": bool(len(at_zero) == len(folds)),
    }


# ==========================================================================
# 16. the estimand — §2.6, and §4.1's bar, evaluated by nobody
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


def opening_market_probs(panel: OddsPanel,
                         corpus: pd.DataFrame) -> dict[str, list[float]]:
    """De-vigged OPENING market probabilities per corpus fixture (§3.4).

    THE ONLY MARKET COMPARISON THIS MODULE MAY MAKE, and it is same-timing by
    construction — the anchor's own Avg-at-the-open panel, not the closing
    columns the published benchmark uses. §3.4 bans anchored-versus-closing
    outright and permits this one ONLY as a labelled model-contribution
    diagnostic, which is why the key it returns under says so.
    """
    frame = panel.frame
    key = {(str(pd.Timestamp(d).date()), str(h), str(a)): i
           for i, (d, h, a) in enumerate(zip(frame["date"], frame["home"],
                                             frame["away"]))}
    p = frame[["p_home", "p_draw", "p_away"]].to_numpy(dtype=float)
    out: dict[str, list[float]] = {}
    for mid, d, h, a in zip(corpus["match_id"].astype(str), corpus["date"],
                            corpus["home_key"], corpus["away_key"]):
        i = key.get((str(pd.Timestamp(d).date()), str(h), str(a)))
        if i is not None:
            out[str(mid)] = [float(v) for v in p[i]]
    return out


def _saturation_diagnostic(rows: Sequence[dict[str, Any]],
                           panel: OddsPanel | None,
                           corpus: pd.DataFrame | None) -> dict[str, Any]:
    """§2.5's *"model contributes nothing"* diagnostic, at the grid boundary.

    Runs when LOSO selects ``w = 1.00`` in any fold. It is the input-level
    answer to the question the output blend's saturation raised, and §2.5
    already ruled what it may and may not say: **`w = 1` is NOT the market's
    forecast.** At `w = 1` only the prior's DIRECTION is the market's; the
    likelihood, the decay, the widening, the correlation term and the scoreline
    structure are all still the model's, so this arm can be better or worse
    than the market and the two saturations are not the same event.

    THE THRESHOLD DOES NOT MOVE ON ACCOUNT OF THIS. §2.5: a grid-maximum
    selection is a fact printed beside the number, not an adjustment to the
    bar.
    """
    top = [r for r in rows if float(r["w"]) == max(W_GRID)]
    if not top:
        return {"ran": False,
                "why": "no fold selected the grid maximum (§2.5)"}
    arm = np.array([r["probs_market_prior"] for r in top], dtype=float)
    out: dict[str, Any] = {
        "ran": True,
        "label": "MODEL-CONTRIBUTION DIAGNOSTIC (§3.4). Not a market "
                 "comparison of the anchored arm's skill, not a claim about "
                 "beating any market, and not comparable with the published "
                 "dc_native-versus-closing-market benchmark.",
        "w": max(W_GRID), "n": len(top),
        "arm_mean_rps": float(np.mean([r["rps_market_prior"] for r in top])),
        "native_mean_rps": float(np.mean([r["rps_native"] for r in top])),
        "w1_is_not_the_markets_forecast": (
            "At w = 1 the PRIOR's direction is the market's. The likelihood, "
            "the decay, the widening, the correlation term and the scoreline "
            "structure remain the model's, so this arm is a fitted DC model "
            "and not a de-vigged price vector (§2.5)."),
    }
    if panel is None or corpus is None:
        out["same_timing_market"] = {"available": False}
        return out
    market = opening_market_probs(panel, corpus)
    paired = [(r, market[str(r["match_id"])]) for r in top
              if str(r["match_id"]) in market]
    if not paired:
        out["same_timing_market"] = {"available": False}
        return out
    m = np.array([p for _, p in paired], dtype=float)
    a = np.array([r["probs_market_prior"] for r, _ in paired], dtype=float)
    y = np.array([int(r["y"]) for r, _ in paired])
    out["same_timing_market"] = {
        "available": True, "n": len(paired),
        "source": "Avg opening, de-vigged multiplicatively — the anchor's own "
                  "panel, so the timing is the arm's own",
        "market_mean_rps": float(np.mean(score_mod.rps(m, y))),
        "arm_mean_rps": float(np.mean(score_mod.rps(a, y))),
        "correlation": float(np.corrcoef(a.ravel(), m.ravel())[0, 1]),
        "mean_abs_prob_gap": float(np.mean(np.abs(a - m))),
        "collapsed_onto_market": bool(np.mean(np.abs(a - m)) < 0.01),
        "reading": "If the arm has collapsed onto the market the finding is "
                   "that the prior has stopped being a prior — a reason to "
                   "report, not a reason to hide (§2.5).",
    }
    return out


def pick_at_selected_weights(rows: Sequence[dict[str, Any]],
                             selection: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per fixture, at ITS OWN season's selected ``w`` — w = 0 included.

    THE ONE PLACE THE SELECTED SET IS BUILT. §2.6's estimand and §2.6's
    predictions file are the same set of fixtures priced the same way, and
    they used to compute it separately: the estimand synthesised the ``w = 0``
    pair, the predictions writer filtered `float(r["w"]) == selected[season]`
    against a ledger that has no ``w = 0`` rows, and a season the selection
    priced at zero vanished from the file without a word. Sharing the picker
    is what makes the two provably the same set rather than two readings that
    happened to agree in the one run where no fold chose zero.

    A season priced at ``w = 0.00`` has no fitted rows of its own, because
    ``z_blend(0)`` IS ``elo_z`` and §2.4 spends no fits on a specification the
    corpus already contains. Its pair is the corpus's row against itself:
    Arm A's probabilities ARE Arm B's and the delta is exactly ``0.0``. That
    is not a missing row — it is the selection saying *no market term*, and
    §2.5 rules that it publishes.
    """
    selected = {str(k): float(v) for k, v in selection["selected"].items()}
    by_fixture: dict[str, dict[str, Any]] = {}
    for r in rows:
        season, mid = str(r["season"]), str(r["match_id"])
        if season not in selected:
            raise FoldLeak(f"season {season} has no selected weight")
        if float(r["w"]) == selected[season]:
            by_fixture[mid] = r
    for r in rows:
        mid, season = str(r["match_id"]), str(r["season"])
        if mid not in by_fixture and selected[season] == 0.0:
            by_fixture[mid] = {**r, "w": 0.0,
                               "probs_market_prior": list(r["probs_native"]),
                               "rps_market_prior": float(r["rps_native"]),
                               "delta": 0.0}
    return sorted(by_fixture.values(), key=lambda r: str(r["match_id"]))


def estimand(rows: Sequence[dict[str, Any]], selection: dict[str, Any], *,
             n_boot: int = N_BOOT, seed: int = BOOTSTRAP_SEED,
             expected_fixtures: int | None = None,
             panel: OddsPanel | None = None,
             corpus: pd.DataFrame | None = None) -> dict[str, Any]:
    """§2.6's mean paired RPS delta at the LOSO-selected weights.

    Every fixture is priced at ITS OWN season's selected ``w`` — the weight
    chosen without a single fixture of that season in the fold. A season whose
    fold selected ``w = 0.00`` contributes a delta of exactly ``0.0`` for every
    one of its fixtures, because ``z_blend(0)`` is ``elo_z`` literally and Arm A
    IS Arm B there (§2.2). That is not a missing row; it is the selection
    saying *no market term*, and §2.5 rules that it publishes.
    """
    selected = {str(k): float(v) for k, v in selection["selected"].items()}
    picked = pick_at_selected_weights(rows, selection)
    if expected_fixtures is not None and len(picked) != int(expected_fixtures):
        raise MergeIncomplete(
            f"{len(picked)} paired fixtures at the selected weights, not the "
            f"pre-stated {expected_fixtures}. §2.6 fixes the denominator and "
            "forbids dropping a fixture for any reason: a refusal is reported, "
            "a deletion is an amendment.")

    deltas = np.array([float(r["delta"]) for r in picked], dtype=float)
    week_blocks = [str(r["block"]) for r in picked]
    season_blocks = [str(r["season"]) for r in picked]
    head = _summarise(deltas, week_blocks, n_boot=n_boot, seed=seed)
    by_season = _summarise(deltas, season_blocks, n_boot=n_boot, seed=seed)

    strata = []
    for season in sorted({str(r["season"]) for r in picked}):
        idx = [i for i, r in enumerate(picked) if str(r["season"]) == season]
        strata.append({"stratum": season, "selected_w": selected[season],
                       **_summarise(deltas[idx],
                                    [week_blocks[i] for i in idx],
                                    n_boot=n_boot, seed=seed)})

    shifts = np.abs(np.array([r["probs_market_prior"] for r in picked],
                             dtype=float)
                    - np.array([r["probs_native"] for r in picked],
                               dtype=float))
    verdict = adoption(head["mean"], head["ci95"], by_season["ci95"])
    return {
        "schema": SCHEMA_ID,
        "estimand": (f"mean paired RPS delta, {ARM_NAME} minus {BASELINE_ARM}, "
                     "over all 2,280 fixtures of the pinned corpus at the "
                     "LOSO-selected weights; negative means the market prior "
                     "helps"),
        **head,
        "season_block_ci95": by_season["ci95"],
        "season_blocks": by_season,
        "bootstrap": {"n_boot": int(n_boot), "seed": int(seed), "alpha": ALPHA,
                      "primary_blocks": "season|ISO week",
                      "secondary_blocks": "season", "method": "percentile"},
        "selection": {k: v for k, v in selection.items() if k != "folds"},
        "selected_weights": selected,
        "folds": selection.get("folds", []),
        "adoption_rule": {
            "threshold": ADOPT_DELTA,
            "conditions": "delta <= -0.0010 AND the 212-week-block 95% CI "
                          "excludes zero AND the 6-season-block 95% CI "
                          "excludes zero",
            "not_scaled_to": "the +0.0050 output-blend prize; and freshness's "
                             "-0.00030 is refused as precedent — that was "
                             "operational, with zero new parameters and one "
                             "candidate, where this is a model change with a "
                             "six-point grid and in-fold selection, which is "
                             "exactly the pair of things the house bar buys",
            "verdict": verdict,
            "applied_by": "nobody — adoption is an owner ruling"},
        "strata": {"season": strata},
        "saturation": _saturation_diagnostic(picked, panel, corpus),
        "movement": {"mean_abs_prob_shift": float(shifts.mean()),
                     "max_abs_prob_shift": float(shifts.max()),
                     "seed_replica_scale": {"mean": 0.0032, "max": 0.0229,
                                            "source": "reports/"
                                                      "epl_walkforward.md"}},
        "power": {"realised_paired_sd": head["sd"],
                  "se_iid": head["se_iid"],
                  "mde_80pct_two_sided": (
                      2.802 * head["se_iid"] if head["n"] > 1 else None),
                  "note": "reported WITH the result; §2.6 makes no power claim "
                          "in advance and no threshold moves in response"},
        "comparison_policy": {
            "estimand": f"{ARM_NAME} vs {BASELINE_ARM}",
            "context": f"{ARM_NAME} vs elo",
            "public_benchmark": f"{BASELINE_ARM} vs closing market — "
                                "UNCHANGED; epl/parse.py is not modified",
            "diagnostic_only": f"{ARM_NAME} vs same-timing OPENING market",
            "banned_by_construction": [
                f"{ARM_NAME} vs closing market",
                "any claim that any arm beats any market"]},
        "decides": "nothing",
    }


def adoption(delta: float, ci95_block: Sequence[float],
             ci95_season: Sequence[float]) -> str:
    """§4.1's bar: the house model-change bar, all three conditions.

    Evaluated here and applied by nobody. The bar is NOT scaled to the prize
    the output blend showed, and freshness's -0.00030 is not precedent for it.
    """
    if (float(delta) <= ADOPT_DELTA
            and float(ci95_block[1]) < 0.0 and float(ci95_block[0]) < 0.0
            and float(ci95_season[1]) < 0.0 and float(ci95_season[0]) < 0.0):
        return "ADOPT"
    return "DC NATIVE STANDS"


# ==========================================================================
# 17. §6's harness-hash freeze
# ==========================================================================
_HEX64 = re.compile(r"\b([0-9a-f]{64})\b")


def harness_freeze_status(sources: Sequence[Path] | None = None,
                          ) -> dict[str, Any]:
    """Has §6's follow-up commit landed, and does it describe THESE bytes?

    §6 step 2: a commit adds file, line count and SHA-256 for every harness
    file, carrying 07b5871's sentence widened — *if ANY hash differs at the
    time the run is executed, it is not the run this document preregisters*.
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
               "disk: if ANY hash differs at the time the run is executed, it "
               "is not the run this document preregisters (§6 step 2). §6 "
               "step 4 requires an amendment BEFORE the change, with the "
               "hashes reissued alongside it")
    else:
        why = ""
    return {"frozen": not missing and not differs, "where": where,
            "files": found, "missing": missing, "why": why,
            "schema": SCHEMA_ID}


def require_harness_freeze(sources: Sequence[Path] | None = None,
                           ) -> dict[str, Any]:
    """Refuse anything that would score fits taken before §6's freeze commit.

    Raised as the base :class:`MarketPriorError`: §7 pre-states this condition
    as an invalidation but §5.1 never gave it a typed name, and this module
    does not invent one after the fact.
    """
    status = harness_freeze_status(sources)
    if not status["frozen"]:
        raise MarketPriorError(
            "the harness-hash freeze of §6 is not in place — " + status["why"]
            + ". The harness may be audited and smoke-tested to a scratch "
            "ledger, but its result may not be merged or scored until the "
            "hash table is committed.")
    return status


# ==========================================================================
# 18. the merge, and the new corpus file §2.6 names
# ==========================================================================
def write_predictions(rows: Sequence[dict[str, Any]],
                      path: Path | str | None = None) -> dict[str, Any]:
    """§2.6's NEW file — `data/epl/fit/dc_market_prior_predictions.parquet`.

    A file that does not exist today. **The pinned corpus is never
    regenerated**: two standing preregistrations check its digest in code, this
    experiment reads it, and Arm A's rows go somewhere else entirely.
    """
    path = Path(path) if path is not None else PREDICTIONS_PARQUET
    if path.resolve() == CORPUS_PATH.resolve():
        raise CorpusDigestMismatch(
            f"refusing to write Arm A's predictions over {paths.rel(CORPUS_PATH)}. "
            "§2.6: the pinned corpus is never regenerated, and two standing "
            "preregistrations check its digest in code.")
    frame = pd.DataFrame([{
        "match_id": str(r["match_id"]), "season": str(r["season"]),
        "block": str(r["block"]), "cutoff": str(r["cutoff"]),
        "w": float(r["w"]), "home_key": str(r["home_key"]),
        "away_key": str(r["away_key"]), "y": int(r["y"]),
        "dc_market_prior_home": float(r["probs_market_prior"][0]),
        "dc_market_prior_draw": float(r["probs_market_prior"][1]),
        "dc_market_prior_away": float(r["probs_market_prior"][2]),
        "dc_market_prior_rps": float(r["rps_market_prior"]),
        "dc_native_rps": float(r["rps_native"]),
        "delta": float(r["delta"]),
    } for r in sorted(rows, key=lambda r: (str(r["match_id"]), float(r["w"])))])
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return {"path": paths.rel(path), "rows": int(len(frame)),
            "sha256": sha256_file(path)}


def merge(shards: int = 1, *, directory: Path | str | None = None,
          corpus: pd.DataFrame | None = None, panel: OddsPanel | None = None,
          write: bool = True, expected: int | None = None,
          expected_fixtures: int | None = None,
          harness_frozen: bool | None = None, n_boot: int = N_BOOT,
          seed: int = BOOTSTRAP_SEED,
          freeze_sources: Sequence[Path] | None = None) -> dict[str, Any]:
    """Every shard, no poison, the pre-stated key set — then select, then score.

    §5.1: the merge takes the union of shard ledgers ONLY if every shard exited
    0 and the union's key set equals the 1,060 expected keys exactly — not a
    superset, not a subset. Partial results never silently merge, and a partial
    ledger is never scored.

    This function authors no verdict prose. It writes machine-readable numbers;
    `reports/epl_anchoring_result.md` is written afterwards, by a person, and
    §4.4 requires it to be written whichever way the numbers fall.
    """
    freeze = (harness_freeze_status(freeze_sources) if harness_frozen is None
              else {"frozen": bool(harness_frozen), "why": "asserted by caller",
                    "files": {}, "where": None})
    if not freeze["frozen"]:
        if harness_frozen is None:
            require_harness_freeze(freeze_sources)
        raise MarketPriorError(
            "refusing to merge: the §6 harness-hash freeze commit does not "
            "cover this harness, so these fits are not the run the "
            "preregistration describes (§7).")

    directory = Path(directory) if directory is not None else MKTPRIOR_DIR
    corpus = load_corpus() if corpus is None else corpus
    preregistered = expected is None
    points = grid_points(corpus, check=preregistered)
    pre = require_run_preconditions(
        directory=directory,
        dates=(control_dates(corpus) if preregistered else None))
    expected = int(expected if expected is not None else EXPECTED_FIT_POINTS)
    expected_fixtures = int(expected_fixtures if expected_fixtures is not None
                            else EXPECTED_FIXTURES)
    if len(points) != expected:
        raise MergeIncomplete(f"{len(points)} fit points, not {expected}")

    config_sha = config_sha256()
    want_keys = {p.key(config_sha) for p in points}

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
        mine = {p.key(config_sha) for p in shard_points(points, i, shards)}
        stray = sorted({str(r["key"]) for r in part} - mine)
        if stray:
            raise MergeIncomplete(
                f"{paths.rel(path)} carries {len(stray)} key(s) outside its "
                f"own partition (first: {stray[:3]}): the shards are a "
                "partition and a row in two of them is a fixture counted twice")
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

    unfrozen = sorted({f"{r['cutoff']}@{r['w']}" for r in rows
                       if not r.get("harness_frozen")})
    if unfrozen:
        raise MarketPriorError(
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
            f"{[k.rsplit('|', 2)[0] for k in short[:3]]}), {len(extra)} "
            f"unexpected (first: {[k.rsplit('|', 2)[0] for k in extra[:3]]}). "
            "Not a superset, not a subset.")

    check_corpus_scores(corpus)
    panel = panel if panel is not None else build_panel()
    selection = select_w(rows, corpus=corpus)
    result = estimand(rows, selection, n_boot=n_boot, seed=seed,
                      expected_fixtures=expected_fixtures, panel=panel,
                      corpus=corpus)
    result.update({
        "n_fits": len(got_keys), "n_ledger_rows": len(rows),
        "shards": sorted(names), "run_digest": run_digest(rows),
        "fit_point_digest": fit_point_digest(points),
        "corpus": {"path": paths.rel(CORPUS_PATH), "sha256": CORPUS_SHA256,
                   "rows": CORPUS_ROWS},
        "odds_panel": {"sha256": panel.sha256, "rows": int(len(panel.frame)),
                       "avg_rows": panel.n_avg, "ps_rows": panel.n_ps},
        "config": {"path": paths.rel(CONFIG_PATH), "sha256": config_sha,
                   "seed": SEED},
        "harness_freeze": freeze,
        "control": {k: v for k, v in pre["control"].items() if k != "detail"},
        "canary": dict(pre["canary"]),
        "odds_canary": dict(pre["odds_canary"]),
        "written_at": pd.Timestamp.now("UTC").isoformat(),
    })

    if write:
        result["predictions"] = write_predictions(
            pick_at_selected_weights(rows, selection))
        ANCHORING_JSON.parent.mkdir(parents=True, exist_ok=True)
        ANCHORING_JSON.write_text(json.dumps(result, indent=2, default=str)
                                  + "\n")
        result["written"] = [paths.rel(ANCHORING_JSON),
                             result["predictions"]["path"]]
    return result


# ==========================================================================
# 19. the CLI
# ==========================================================================
def _plan(corpus: pd.DataFrame, shards: int, directory: Path) -> dict[str, Any]:
    points = grid_points(corpus)
    return {
        "n_block_openings": len(block_openings(corpus)),
        "n_fixtures": EXPECTED_FIXTURES,
        "grid": list(W_GRID),
        "n_fit_points": len(points),
        "fit_point_digest": fit_point_digest(points),
        # §2.8's budget covers the CONTROL fits too — they are fits, they are
        # paid for, and a budget that hid them would be the small dishonesty
        # that makes a run overrun its window.
        "budget": {"fits": len(points), "control_fits": N_CONTROL_DATES,
                   "total": len(points) + N_CONTROL_DATES,
                   "warm_hours": round((len(points) + N_CONTROL_DATES)
                                       * 8.8 / 3600, 1),
                   "cold_hours": round((len(points) + N_CONTROL_DATES)
                                       * 57.24 / 3600, 1),
                   "per_fit_seconds": {"warm": 8.8, "cold": 57.24},
                   "shardable_by": "(cutoff, w), BLAS pinned, per-PID waits",
                   "thinnable": False},
        "n_control_dates": N_CONTROL_DATES,
        "control_dates": control_dates(corpus),
        "shards": {str(i): len(shard_points(points, i, shards))
                   for i in range(shards)},
        "run_order": list(RUN_ORDER),
        "directory": paths.rel(directory),
        "preconditions": {
            "canary": (directory / CANARY_NAME).exists(),
            "odds_canary": (directory / ODDS_CANARY_NAME).exists(),
            "control": (directory / CONTROL_NAME).exists()},
        "harness_freeze": harness_freeze_status(),
        "blas_threads": blas_threads(),
    }


def _frozen_now() -> bool:
    """Has §6's freeze commit landed for THESE bytes? One place, one answer."""
    return bool(harness_freeze_status()["frozen"])


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", action="store_true",
                    help="print the schedule, the budget and the shard sizes; "
                         "fits nothing")
    ap.add_argument("--canary", action="store_true",
                    help="§5.3's point-in-time canary (results)")
    ap.add_argument("--odds-canary", action="store_true",
                    help="§5.4's odds canary — new, because the existing one "
                         "is blind to the odds panel")
    ap.add_argument("--control", action="store_true",
                    help="§3.2's w = 0 identity control; runs FIRST among fits")
    ap.add_argument("--run", action="store_true",
                    help="Arm A's fits over this shard's (cutoff, w) points")
    ap.add_argument("--merge", action="store_true",
                    help="verify every shard, select w, then compute the "
                         "estimand")
    ap.add_argument("--shard", default="0/1",
                    help="i/N — this worker's slice of the fit points")
    ap.add_argument("--shards", type=int, default=1,
                    help="how many shards the merge must find")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dates", default=None,
                    help="comma-separated control dates (default: the twenty)")
    ap.add_argument("--cutoff", default=None,
                    help="the odds canary's cutoff (default: a mid-archive "
                         "block opening)")
    ap.add_argument("--dir", dest="directory", default=None,
                    help="the run directory (default "
                         f"{paths.rel(MKTPRIOR_DIR)})")
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

    directory = Path(args.directory) if args.directory else MKTPRIOR_DIR

    try:
        if args.plan:
            print(json.dumps(_plan(load_corpus(), max(count, args.shards),
                                   directory), indent=2, default=str))

        if args.canary:
            _guard_ledger_location(directory / CANARY_NAME, _frozen_now())
            print(json.dumps(run_canary(path=directory / CANARY_NAME),
                             indent=2, default=str))

        if args.odds_canary:
            _guard_ledger_location(directory / ODDS_CANARY_NAME, _frozen_now())
            corpus = load_corpus()
            panel = build_panel()
            assert_panel(panel)
            openings = sorted(set(block_openings(corpus).values()))
            cutoff = args.cutoff or openings[len(openings) // 2]
            teams = sorted(set(corpus["home_key"].astype(str))
                           | set(corpus["away_key"].astype(str)))
            out = run_odds_canary(panel, cutoff, teams,
                                  elo_z=np.zeros(len(teams)),
                                  path=directory / ODDS_CANARY_NAME)
            print(json.dumps(out, indent=2, default=str))

        if args.control:
            _guard_ledger_location(directory / CONTROL_NAME, _frozen_now())
            corpus = load_corpus()
            check_corpus_scores(corpus)
            require_canary(directory / CANARY_NAME)      # RUN_ORDER, enforced
            require_odds_canary(directory / ODDS_CANARY_NAME)
            out = run_control(
                dates=(args.dates.split(",") if args.dates else None),
                corpus=corpus, limit=args.limit, write=True,
                path=directory / CONTROL_NAME)
            print(json.dumps({k: v for k, v in out.items() if k != "detail"},
                             indent=2, default=str))

        if args.run:
            corpus = load_corpus()
            check_corpus_scores(corpus)
            frozen = harness_freeze_status()
            require_run_preconditions(
                directory=directory,
                dates=(control_dates(corpus) if frozen["frozen"] else None))
            assert_blas_pinned("the market-prior sweep")
            points = shard_points(grid_points(corpus), index, count)
            if args.limit:
                points = points[:args.limit]
            ledger = (Path(args.ledger) if args.ledger
                      else directory / shard_name(index, count))
            # Guard BEFORE the engine: building the store, the anchor and the
            # panel costs real time, and a run that is going to be refused
            # should be refused before it spends it.
            _guard_ledger_location(ledger, bool(frozen["frozen"]))
            if not frozen["frozen"]:
                print("[mkt] WARNING: " + frozen["why"] + " — every row of "
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
            print(json.dumps({k: v for k, v in out.items()
                              if k not in ("control", "canary", "odds_canary",
                                           "harness_freeze", "folds")},
                             indent=2, default=str))

    except MarketPriorError as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
