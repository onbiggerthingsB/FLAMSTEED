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
