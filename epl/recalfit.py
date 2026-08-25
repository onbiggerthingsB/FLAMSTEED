"""A8 — the frozen rule behind `dc_1x2_recal`, and the grounding it stands on.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_recal.py -q
    PYTHONPATH=src:. .venv/bin/python -m epl.recalfit        # regenerate grounding

WHAT IS FROZEN IS THE RULE, NOT THE NUMBER
------------------------------------------
Amendment A8 (``reports/epl_sim_amendments.md``) freezes six things, and this
module is the executable half of all six:

1. **The transform class, closed at one parameter.**
   ``q_i = p_i^a / (p_home^a + p_draw^a + p_away^a)``. No intercept, no
   per-outcome parameter, no covariate, no second exponent — adding one is a
   new amendment and not an implementation detail.
2. **The corpus, by sha256.** :data:`CORPUS_SHA256`, checked BEFORE any fit.
   A missing corpus and a differing corpus are typed refusals, never skips.
3. **The objective, pinned to one.** Mean RPS by this project's own literal —
   :func:`epl.matchboard.rps` — which :func:`rps_rows` is held against row by
   row in the tests rather than re-expressed here and assumed equal.
4. **The procedure.** A root-find of the objective's ANALYTIC first derivative,
   ``scipy.optimize.brentq`` on :data:`BRACKET` at :data:`XTOL` / :data:`RTOL`.
   Not a minimiser: the objective is flat enough that fourteen scipy scalar
   minimisers spanned ``1.95e-07`` on this corpus, while the derivative has a
   non-zero slope at its root (``f'' ~ 0.0649``) and five different brackets
   return the identical double.
5. **The constant**, :data:`A`, recorded to twelve decimals as a LITERAL —
   because ``probs_recal`` must be a bit-reproducible function of ``probs_raw``,
   which is the only requirement those decimals serve. The corpus itself
   resolves ``a`` to about ±0.03 (see :func:`loso`), so ten of the twelve are
   bookkeeping, and nothing here claims otherwise.
6. **The schedule**: an annual expanding-window refit before each season's
   first issuance and at no other time; any change to decay, widening,
   inference or scoreline-model semantics invalidates ``a`` until it is
   revalidated; **no drift trigger, explicitly**; and weekly in-season
   refitting — measured at ``-0.0000056`` mean RPS — is REFUSED and not built.

THE CONSTANT IS NOT THE ARGMIN AT TWELVE DECIMALS, AND THIS FILE SAYS SO
-----------------------------------------------------------------------
The pinned procedure's root on the pinned corpus is ``0.9063507710098762``;
:data:`A` sits ``+2.66e-08`` above it. Both evaluate to mean RPS
``0.20167260332083187`` — the same double, to the last bit. That is why
verification is TWO legs (:func:`verify_fit`): a bound on the parameter, which
can never see the difference between an RPS fit and an NLL fit, and an exact
one-ulp comparison on the OBJECTIVE, which is the only place the pinned
criterion bites.

WHAT THIS FILE MAY NOT SAY
--------------------------
A8 (e)'s language rule is binding on every surface, including the grounding
report this module writes: ``dc_1x2_recal`` is *a low-cost calibration
challenger with forward-supportive evidence* and never *an established
improvement*; the published law is *historically recalibrated under the pinned
criterion* and never *calibrated by construction*. Both validation intervals
cross zero and the report says so as the finding rather than as a footnote.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from epl import leaguesim, matchboard, paths

#: The challenger's name, on every row it ever files.
ARM = "dc_1x2_recal"

#: A8 (b) — the rule this constant was obtained under, carried on every row so
#: a reader can tell a row fitted under one rule from a row filed under
#: another's name.
RULE_VERSION = "dc-1x2-recal-1"

#: The ordered outcomes, from the module that already defines them. ORDER IS
#: PART OF THE SCORE and there is one definition of it in this project.
OUTCOMES = matchboard.OUTCOMES

#: A8 (b) — THIS SEASON'S FROZEN CONSTANT, to twelve decimals, as a literal.
A = 0.906350797598

#: ...and its reciprocal, recorded to the precision it is written at:
#: ``1/A = 1.1033255585477368``, which truncates here, and ``|1/A - T| =
#: 7.37e-13``.
T = 1.103325558547

#: A8 item 1 — the corpus, by path and by digest. The digest is the corpus's
#: identity: a file with this name and different bytes fits perfectly well and
#: answers a different question.
CORPUS_PATH = paths.FIT_DIR / "walkforward_predictions.parquet"
CORPUS_SHA256 = \
    "f31580073eb3a7f0deca59b45d1576fb262272efc6d1893ce8c9931b9eff451a"
CORPUS_ROWS = 2280
CORPUS_SEASONS = ("2019/20", "2020/21", "2021/22", "2022/23", "2023/24",
                  "2024/25")
#: ``y`` encodes the ordered outcome as 0 = home, 1 = draw, 2 = away.
CORPUS_Y_COUNTS = (993, 525, 762)

#: The three columns the transform is fitted on: the AGGREGATED per-match 1X2,
#: which is exactly the object the shadow layer applies the constant to. A8 (a)
#: is explicit that fitting on aggregates and applying to particles would be
#: applying a constant somewhere it was never measured.
PROBS_COLUMNS = ("dc_home", "dc_draw", "dc_away")

#: A8 (b) — the procedure's bracket and tolerances. `RTOL` is scipy's floor,
#: ``4 * eps``.
BRACKET = (0.5, 2.0)
XTOL = 1e-15
RTOL = 8.881784197001252e-16

#: A8 (d) leg 1 — the parameter window, fixed with its justification and NOT
#: from any observed gap. At ``|da| = 1e-6`` the objective moves
#: ``0.5 * f'' * da^2 ~ 3.2e-14``, which is ``1.6e-13`` of its own value; and
#: the corpus resolves ``a`` only to ``±0.03``, so this window is 5.7e4 times
#: tighter than the data's own resolution. It admits any faithful
#: implementation and refuses a different corpus, a different transform class,
#: or a bug.
PARAM_TOLERANCE = 1e-6

#: A8 (d) step 3 — the EXACT leg. ``probs_recal`` is arithmetic on the row's
#: own ``probs_raw`` and the row's own ``a``: no optimiser, no corpus, nothing
#: to disagree about, which is why this one is held twelve orders further down.
RECAL_TOLERANCE = 1e-12

#: A8 item 5 — ``sum q = 1`` within this.
SUM_TOLERANCE = 1e-9

#: A8 (e), binding on every surface including the grounding report below.
CHALLENGER_PHRASE = ("a low-cost calibration challenger with forward-supportive "
                     "evidence")
PUBLISHED_LAW_PHRASE = "historically recalibrated under the pinned criterion"

#: Phrases A8 (e) forbids by name. Held against the rendered grounding report
#: by a test, because a language rule nothing checks is a language rule that
#: survives exactly as long as nobody is in a hurry.
FORBIDDEN_PHRASES = ("established improvement", "calibrated by construction")

#: A8 (e) — measured WORSE out of sample and rejected BY NAME, so that nobody
#: re-proposes one as a new idea. They are not alternatives awaiting a second
#: look; they were looked at.
REJECTED_VARIANTS = ("Platt scaling", "vector scaling",
                     "affine (intercept-carrying) recalibration")

#: A8 (e), quoted from the grounding session that measured them and NOT
#: re-derived here — the forward season is outside the pinned corpus by
#: ``epl/config_frozen.json``, so this file could not re-derive it if it tried.
#: Positive means the transform scored better: a reduction in mean RPS.
QUOTED_VALIDATION = {
    "calibration_slope_published_law": 0.9035,
    "calibration_slope_p_value": 0.023,
    "loso_slope_after_transform": 1.0008,
    "loso_mean_rps_difference": 0.000153,
    "loso_ci_95": (-0.000353, 0.000646),
    "loso_seasons_better": 4,
    "loso_seasons_total": 6,
    "forward_2025_26_mean_rps_difference": 0.000667,
    "forward_2025_26_ci_crosses_zero": True,
    "forward_slope": (0.810, 0.899),
    "weekly_refit_mean_rps_difference": -0.0000056,
}

#: Where the machine-readable grounding and its short report are written.
GROUNDING_JSON = paths.REPO_ROOT / "reports" / "epl_recal_grounding.json"
GROUNDING_MD = paths.REPO_ROOT / "reports" / "epl_recal_grounding.md"


# ==========================================================================
# the typed refusals
# ==========================================================================

class RecalError(RuntimeError):
    """Anything the recalibration rule refuses.

    A8 (d) names eight subclasses and this project does not invent a ninth: an
    input that is none of those eight conditions — a non-finite probability, a
    corpus missing the columns the rule is defined on — is refused as this base
    class rather than under a name the amendment never pre-stated.
    """


class CorpusMissing(RecalError):
    """The corpus is not on disk. A8 (d): a typed refusal, never a skip."""


class CorpusDigestMismatch(RecalError):
    """The corpus is not the corpus the constant was fitted on."""


class RefitOutOfBounds(RecalError):
    """A8 (d) leg 1: the re-fit is further than :data:`PARAM_TOLERANCE` away."""


class ObjectiveInferior(RecalError):
    """A8 (d) leg 2: the ledger's constant scores worse than the re-fit by more
    than one unit in the last place — which is what a constant fitted to a
    DIFFERENT objective looks like, and what leg 1 provably cannot see."""


class RecalMismatch(RecalError):
    """A recorded number does not re-derive from the row's own inputs."""


class SchemaMismatch(RecalError):
    """A row's frozen-rule fields are not the frozen rule's."""


class RowInadmissible(RecalError):
    """A7 (e): the forecast did not precede the kickoff it is scored against.

    REFUSED, naming the fixture and the stamp — never dropped. In an
    append-only file a silent omission is invisible.
    """


class RowConflict(RecalError):
    """An append-only ledger already carries a DIFFERENT row for this key."""


# ==========================================================================
# 1. the transform
# ==========================================================================

def _finite(value: Any, label: str) -> float:
    number = float(value)
    if not np.isfinite(number):
        raise RecalError(f"{label} is {value!r}: the transform is defined on "
                         "finite positive probabilities, and a non-finite cell "
                         "renormalises to a non-finite vector and scores as one")
    return number


def transform(probs: Mapping[str, float], a: float) -> dict[str, float]:
    """A8 (b): ``q_i = p_i^a / (p_home^a + p_draw^a + p_away^a)``.

    Renormalised exactly — the denominator is the sum of the three transformed
    cells and never an assumption that the input summed to one. ``a = 1`` is
    the identity.

    A ZERO CELL IS REFUSED, not transformed. ``0 ** a`` is ``0`` for every
    ``a > 0``, so a cell that starts at zero can never come back, and ``ln 0``
    is what the fit's own derivative would then take. A published matchboard
    marginal can legitimately be zero — no retained season had that outcome —
    and A8's rule is not defined there, so the refusal is the honest answer
    rather than a quiet ``-inf``.
    """
    exponent = _finite(a, "the exponent")
    if exponent <= 0:
        raise RecalError(f"the exponent is {a!r}: A8 (b) closes the class at "
                         "one real a > 0")
    powered = {}
    for key in OUTCOMES:
        if key not in probs:
            raise RecalError(f"the vector carries no {key!r} cell; A8 (b) is "
                             f"defined on the ordered triple {OUTCOMES}")
        cell = _finite(probs[key], f"probs[{key!r}]")
        if cell <= 0.0:
            raise RecalError(
                f"probs[{key!r}] is {cell!r}: the transform is a power law on "
                "strictly positive cells, and a zero cell can never come back "
                "from one")
        powered[key] = cell ** exponent
    total = sum(powered.values())
    if not np.isfinite(total) or total <= 0.0:
        raise RecalError(f"the transformed cells sum to {total!r}, which is "
                         "not a vector anything can be renormalised against")
    return {key: powered[key] / total for key in OUTCOMES}


def transform_rows(probs: np.ndarray, a: float) -> np.ndarray:
    """:func:`transform`, vectorised over an ``[n, 3]`` array of triples."""
    array = np.asarray(probs, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3:
        raise RecalError(f"probabilities must be [n, 3] over {OUTCOMES}, got "
                         f"{array.shape}")
    if not np.isfinite(array).all() or (array <= 0.0).any():
        raise RecalError("every cell must be finite and strictly positive: the "
                         "transform is a power law and its derivative takes "
                         "`ln p`")
    powered = array ** _finite(a, "the exponent")
    return powered / powered.sum(axis=1, keepdims=True)


# ==========================================================================
# 2. the objective — this project's own literal
# ==========================================================================

def rps(probs: Mapping[str, float], outcome: str) -> float:
    """The project's ranked probability score, from the module that owns it.

    :func:`epl.matchboard.rps` is THE literal (A8 (b) pins it by file and
    line). This wrapper exists only to keep the refusal typed on this surface;
    it computes nothing.
    """
    try:
        return matchboard.rps(probs, outcome)
    except matchboard.MatchboardError as exc:
        raise RecalError(str(exc)) from exc


def rps_rows(probs: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The same literal, vectorised: ``(1/(r-1)) sum_i (CP_i - CO_i)^2``, r = 3.

    Held against :func:`rps` row by row in the tests. A second implementation
    of a score that nobody compares is how two surfaces end up publishing
    different numbers under one name.
    """
    p = np.asarray(probs, dtype=float)
    labels = np.asarray(y).ravel().astype(int)
    if p.ndim != 2 or p.shape[1] != 3:
        raise RecalError(f"probabilities must be [n, 3] over {OUTCOMES}, got "
                         f"{p.shape}")
    if labels.size != p.shape[0]:
        raise RecalError(f"{labels.size} outcomes for {p.shape[0]} forecasts")
    if labels.min() < 0 or labels.max() > 2:
        raise RecalError("`y` encodes the ordered outcome as 0 = home, "
                         "1 = draw, 2 = away")
    observed = np.zeros_like(p)
    observed[np.arange(labels.size), labels] = 1.0
    cum_p = np.cumsum(p, axis=1)[:, :2]
    cum_o = np.cumsum(observed, axis=1)[:, :2]
    return ((cum_p - cum_o) ** 2).sum(axis=1) / (len(OUTCOMES) - 1)


def mean_rps(probs: np.ndarray, y: np.ndarray, a: float = 1.0) -> float:
    """Mean RPS over the rows, at exponent ``a`` — ALWAYS through the transform.

    ``a = 1`` is the identity of the transform and not a short circuit around
    it, and on this corpus the difference is visible: the published
    ``dc_home/dc_draw/dc_away`` sum to one only to floating-point precision, so
    scoring them raw gives ``0.20194241066255245`` and scoring
    ``transform(p, 1)`` gives ``0.20194241064214688`` — which is the figure A8
    (b) records for the published law untransformed. The objective is a
    function of the transform at every ``a``, including one.
    """
    return float(np.mean(rps_rows(transform_rows(probs, a), y)))


def d_mean_rps(probs: np.ndarray, y: np.ndarray, a: float) -> float:
    """The objective's ANALYTIC first derivative — what the procedure roots.

    ``dq_i/da = q_i (ln p_i - sum_j q_j ln p_j)``, and

        ``d(RPS)/da = mean over rows of sum_{i=1,2} (CP_i - CO_i) dCP_i/da``

    where the score's ``1/(r-1)`` and the chain rule's factor of two cancel
    exactly, which is why neither appears.
    """
    p = np.asarray(probs, dtype=float)
    labels = np.asarray(y).ravel().astype(int)
    q = transform_rows(p, a)
    log_p = np.log(p)
    dq = q * (log_p - (q * log_p).sum(axis=1, keepdims=True))
    observed = np.zeros_like(p)
    observed[np.arange(labels.size), labels] = 1.0
    cum_p = np.cumsum(q, axis=1)[:, :2]
    cum_o = np.cumsum(observed, axis=1)[:, :2]
    d_cum_p = np.cumsum(dq, axis=1)[:, :2]
    return float(np.mean(((cum_p - cum_o) * d_cum_p).sum(axis=1)))


# ==========================================================================
# 3. the corpus and the fit
# ==========================================================================

def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_corpus(path=None, *, expect_sha256: str = CORPUS_SHA256):
    """The corpus, CHECKED BY DIGEST BEFORE ANYTHING READS IT.

    ``expect_sha256`` has no ``None``: there is no way to ask this function to
    fit a file whose identity the caller has not declared. A synthetic corpus
    passes its own digest; the pinned one passes A8's, which is the default.
    """
    corpus = Path(CORPUS_PATH if path is None else path)
    if not corpus.exists():
        raise CorpusMissing(
            f"{corpus} does not exist. A8 (b) pins the corpus by sha256 "
            f"{expect_sha256}, and a fit against a file that is not there is "
            "not a fit — this refuses rather than skipping, because a "
            "verification that quietly declines to verify is worse than one "
            "that was never run")
    digest = sha256_file(corpus)
    if digest != expect_sha256:
        raise CorpusDigestMismatch(
            f"{corpus} hashes to {digest}, and the rule was fitted on "
            f"{expect_sha256}. A file with the right name and different bytes "
            "fits perfectly well and answers a different question")
    frame = pd.read_parquet(corpus)
    missing = [c for c in (*PROBS_COLUMNS, "y") if c not in frame.columns]
    if missing:
        raise RecalError(f"{corpus} carries no {', '.join(missing)}: A8 (b) "
                         f"names {PROBS_COLUMNS} (the aggregated per-match "
                         "1X2) and `y` as the columns the rule is defined on")
    probs = frame[list(PROBS_COLUMNS)].to_numpy(dtype=float)
    y = frame["y"].to_numpy(dtype=int)
    return probs, y, frame, digest


def fit_from_rows(probs: np.ndarray, y: np.ndarray, *,
                  bracket: Sequence[float] = BRACKET) -> float:
    """A8 (b)'s deterministic procedure: ``brentq`` on :func:`d_mean_rps`.

    NOT a minimiser. The objective is flat — fourteen scipy scalar minimisers
    spanned ``1.95e-07`` on the pinned corpus and three general ones landed as
    far out as ``0.90639…`` — while the derivative has a non-zero slope at its
    root, so the root-find is well conditioned exactly where the minimisation
    is not.
    """
    low, high = (float(bracket[0]), float(bracket[1]))
    try:
        return float(brentq(lambda a: d_mean_rps(probs, y, a), low, high,
                            xtol=XTOL, rtol=RTOL))
    except ValueError as exc:
        raise RecalError(
            f"the pinned procedure could not root the objective's derivative "
            f"on [{low}, {high}]: {exc}. A bracket that does not contain the "
            "root is not a looser fit, it is no fit at all") from exc


def fit_a(path=None, *, expect_sha256: str = CORPUS_SHA256,
          bracket: Sequence[float] = BRACKET) -> dict:
    """The whole fit, reported: the root, the objective there and at ``a = 1``.

    The digest is checked first and always (:func:`load_corpus`).
    """
    probs, y, frame, digest = load_corpus(path, expect_sha256=expect_sha256)
    a = fit_from_rows(probs, y, bracket=bracket)
    return {"a": a, "T": 1.0 / a,
            "mean_rps": mean_rps(probs, y, a),
            "mean_rps_at_one": mean_rps(probs, y, 1.0),
            "n_rows": int(len(frame)), "sha256": digest,
            "bracket": [float(bracket[0]), float(bracket[1])]}


def mean_rps_at(path=None, a: float = A, *,
                expect_sha256: str = CORPUS_SHA256) -> float:
    """Mean RPS on the pinned corpus at one exponent — leg 2's arithmetic."""
    probs, y, _frame, _digest = load_corpus(path, expect_sha256=expect_sha256)
    return mean_rps(probs, y, a)


def loso(path=None, *, expect_sha256: str = CORPUS_SHA256,
         bracket: Sequence[float] = BRACKET) -> list[dict]:
    """Six leave-one-season-out refits, each scored on the season it never saw.

    This is the measurement that says the corpus resolves ``a`` to about
    ``±0.03`` — and therefore that ten of the twelve recorded decimals are
    bookkeeping and not information. Nothing in this project may claim the
    corpus knows ``a`` to twelve decimals.
    """
    probs, y, frame, _digest = load_corpus(path, expect_sha256=expect_sha256)
    seasons = list(dict.fromkeys(frame["season"].tolist()))
    rows: list[dict] = []
    for season in seasons:
        held = (frame["season"] == season).to_numpy()
        a = fit_from_rows(probs[~held], y[~held], bracket=bracket)
        raw = rps_rows(probs[held], y[held])
        recal = rps_rows(transform_rows(probs[held], a), y[held])
        rows.append({"season": str(season), "a": a,
                     "n_rows": int(held.sum()),
                     "mean_rps_raw": float(raw.mean()),
                     "mean_rps_recal": float(recal.mean()),
                     "mean_rps_gain": float((raw - recal).mean())})
    return rows


def loso_pooled(path=None, *, expect_sha256: str = CORPUS_SHA256,
                bracket: Sequence[float] = BRACKET) -> dict:
    """The pooled out-of-fold difference and a normal-approximation interval.

    RE-DERIVED HERE, and reported beside — never instead of — the interval A8
    (e) quotes from the grounding session. The two point estimates agree to
    ``1e-6``; the interval BOUNDS differ in the third significant figure
    because the interval method is not the same one, and A8's quoted figures
    are the authority. Both cross zero, which is the finding either way.
    """
    probs, y, frame, _digest = load_corpus(path, expect_sha256=expect_sha256)
    seasons = list(dict.fromkeys(frame["season"].tolist()))
    diffs = []
    for season in seasons:
        held = (frame["season"] == season).to_numpy()
        a = fit_from_rows(probs[~held], y[~held], bracket=bracket)
        raw = rps_rows(probs[held], y[held])
        recal = rps_rows(transform_rows(probs[held], a), y[held])
        diffs.append(raw - recal)
    pooled = np.concatenate(diffs)
    se = float(pooled.std(ddof=1) / np.sqrt(pooled.size))
    mean = float(pooled.mean())
    return {"mean_rps_gain": mean, "n_rows": int(pooled.size),
            "se": se, "ci_95": [mean - 1.96 * se, mean + 1.96 * se],
            "seasons_better": int(sum(1 for d in diffs if d.mean() > 0)),
            "seasons_total": len(diffs)}


# ==========================================================================
# 4. verification — the two legs (A8 (d) step 2)
# ==========================================================================

def verify_fit(path=None, *, a_ledger: float = A,
               expect_sha256: str = CORPUS_SHA256,
               bracket: Sequence[float] = BRACKET) -> dict:
    """Re-derive ``a`` from the corpus and hold the ledger's constant to it.

    **Leg 1 — the parameter.** ``|a_ledger - a_refit| <= PARAM_TOLERANCE``,
    else :class:`RefitOutOfBounds`. A bound and NOT an equality, and A8 (d)
    records that as a deviation from the design it was asked to implement: the
    design pre-stated an exact comparison, which is not satisfiable — fourteen
    scipy minimisers span ``1.95e-07`` around the constant and the pinned
    root-find lands ``2.66e-08`` away from it.

    **Leg 2 — the objective, with no tolerance to choose.** Mean RPS at
    ``a_ledger`` must not exceed mean RPS at ``a_refit`` by more than ONE unit
    in the last place, else :class:`ObjectiveInferior`. One ulp is the smallest
    representable slack, so it is not a number anything was tuned to. This leg
    is what makes the pinned objective load-bearing: the NLL-fitted constant
    ``0.9063511680814477`` sits ``3.97e-07`` from the RPS root — invisible to
    any honest parameter window — and fails here by 184 ulps.
    """
    probs, y, frame, digest = load_corpus(path, expect_sha256=expect_sha256)
    a_refit = fit_from_rows(probs, y, bracket=bracket)
    gap = float(a_ledger) - a_refit
    at_ledger = mean_rps(probs, y, a_ledger)
    at_refit = mean_rps(probs, y, a_refit)
    slack = float(np.nextafter(at_refit, np.inf))
    report = {
        "corpus": str(Path(CORPUS_PATH if path is None else path)),
        "sha256": digest, "n_rows": int(len(frame)),
        "a_ledger": float(a_ledger), "a_refit": a_refit, "gap": gap,
        "param_tolerance": PARAM_TOLERANCE,
        "mean_rps_at_ledger": at_ledger, "mean_rps_at_refit": at_refit,
        "one_ulp_above_refit": slack,
        "mean_rps_at_one": mean_rps(probs, y, 1.0),
    }
    if abs(gap) > PARAM_TOLERANCE:
        raise RefitOutOfBounds(
            f"the ledger's a = {a_ledger!r} and a re-fit of {digest[:12]}… by "
            f"the pinned procedure gives {a_refit!r}: a gap of {gap!r}, which "
            f"is wider than {PARAM_TOLERANCE}. That window is 5.7e4 times "
            "tighter than the corpus's own resolution of a and admits any "
            "faithful implementation, so a gap this wide is a different "
            "corpus, a different transform class, or a bug")
    if at_ledger > slack:
        raise ObjectiveInferior(
            f"mean RPS at the ledger's a = {a_ledger!r} is {at_ledger!r} and "
            f"at the re-fit {a_refit!r} it is {at_refit!r}: worse by more than "
            "one unit in the last place. The objective is pinned to ONE — mean "
            "RPS by this project's literal — precisely so that a constant "
            "fitted to a different objective fails here, where the parameter "
            "leg provably cannot see it")
    return report


# ==========================================================================
# 5. the grounding — the numbers as an artifact, not as prose
# ==========================================================================

#: A8 item 3 — the published Arsenal-Coventry MW0 marginals, which are A7's
#: exact counts 15278 / 3235 / 1487 over 20,000. Carried here so the control
#: is regenerated from the file's own probabilities and never from a rendered
#: four-decimal string (A8 item 4: the rendered triple transforms to a vector
#: that renders IDENTICALLY at 4dp and differs at the sixth decimal).
CONTROL_FIXTURE = "2627:arsenal:coventry"
CONTROL_PROBS = {"home": 0.763900, "draw": 0.161750, "away": 0.074350}
CONTROL_OUTCOME = "home"

#: The five brackets A8 (b) measured, which all give the identical double on
#: the pinned corpus.
GROUNDING_BRACKETS = ((0.5, 2.0), (0.1, 3.0), (0.5, 1.5), (0.8, 1.0),
                      (0.0001, 5.0))


def grounding(corpus=None, *, expect_sha256: str = CORPUS_SHA256) -> dict:
    """Everything the frozen rule stands on, as one machine-readable document.

    A PURE FUNCTION of the corpus and this module: no clock, no environment,
    nothing that drifts. A regeneration that changes a byte is a change in the
    corpus or in the rule, and never in the weather — which is what makes the
    committed artifact checkable rather than decorative.
    """
    probs, y, frame, digest = load_corpus(corpus, expect_sha256=expect_sha256)
    root = fit_from_rows(probs, y)
    at_root = mean_rps(probs, y, root)
    at_literal = mean_rps(probs, y, A)
    at_one = mean_rps(probs, y, 1.0)
    table = loso(corpus, expect_sha256=expect_sha256)
    pooled = loso_pooled(corpus, expect_sha256=expect_sha256)
    span = max(row["a"] for row in table) - min(row["a"] for row in table)
    counts = frame["y"].value_counts().sort_index()
    control = transform(CONTROL_PROBS, A)

    return {
        "arm": ARM,
        "rule_version": RULE_VERSION,
        "amendment": "A8, reports/epl_sim_amendments.md",
        "a": A,
        "T": T,
        "transform": "q_i = p_i^a / (p_home^a + p_draw^a + p_away^a)",
        "class_closed_at": ("one parameter: no intercept, no per-outcome "
                            "parameter, no covariate, no second exponent"),
        "objective": {
            "name": "mean RPS",
            "literal": "epl/matchboard.py:674",
            "r": len(OUTCOMES),
            "ordered": list(OUTCOMES),
            "weighting": "unweighted",
        },
        "procedure": {
            "method": "scipy.optimize.brentq on the analytic first derivative",
            "derivative": ("dq_i/da = q_i (ln p_i - sum_j q_j ln p_j); "
                           "d(RPS)/da = mean_rows sum_{i=1,2} (CP_i - CO_i) "
                           "dCP_i/da"),
            "bracket": list(BRACKET), "xtol": XTOL, "rtol": RTOL,
            "not_a_minimiser": True,
        },
        "corpus": {
            "path": paths.rel(Path(CORPUS_PATH if corpus is None else corpus)),
            "sha256": digest,
            "n_rows": int(len(frame)),
            "seasons": [str(s) for s in dict.fromkeys(frame["season"].tolist())],
            "rows_per_season": {str(k): int(v) for k, v in
                                frame["season"].value_counts()
                                .sort_index().items()},
            "y_encoding": {"0": "home", "1": "draw", "2": "away"},
            "y_counts": [int(counts.get(i, 0)) for i in range(3)],
            "columns": list(PROBS_COLUMNS),
            "excluded_seasons": ["2025/26"],
        },
        "fit": {
            "root": root,
            "literal": A,
            "literal_minus_root": A - root,
            "mean_rps_at_root": at_root,
            "mean_rps_at_literal": at_literal,
            "mean_rps_at_one": at_one,
            "in_sample_gain": at_one - at_literal,
            "one_ulp_of_objective": float(np.nextafter(at_root, np.inf)
                                          - at_root),
            "derivative_at_literal": d_mean_rps(probs, y, A),
            "brackets": [{"bracket": list(b),
                          "a": fit_from_rows(probs, y, bracket=b)}
                         for b in GROUNDING_BRACKETS],
        },
        "loso": table,
        "loso_span": span,
        "loso_pooled_rederived": pooled,
        "validation_quoted": {
            "note": ("quoted from the grounding session that measured them and "
                     "NOT re-derived here; the forward season is outside the "
                     "pinned corpus by epl/config_frozen.json. Positive means "
                     "a reduction in mean RPS."),
            "calibration_slope_published_law":
                QUOTED_VALIDATION["calibration_slope_published_law"],
            "calibration_slope_p_value":
                QUOTED_VALIDATION["calibration_slope_p_value"],
            "loso_slope_after_transform":
                QUOTED_VALIDATION["loso_slope_after_transform"],
            "loso_mean_rps_difference":
                QUOTED_VALIDATION["loso_mean_rps_difference"],
            "loso_ci_95": list(QUOTED_VALIDATION["loso_ci_95"]),
            "loso_seasons_better": QUOTED_VALIDATION["loso_seasons_better"],
            "loso_seasons_total": QUOTED_VALIDATION["loso_seasons_total"],
            "forward_2025_26_mean_rps_difference":
                QUOTED_VALIDATION["forward_2025_26_mean_rps_difference"],
            "forward_2025_26_ci_crosses_zero":
                QUOTED_VALIDATION["forward_2025_26_ci_crosses_zero"],
            "forward_slope": list(QUOTED_VALIDATION["forward_slope"]),
            "weekly_refit_mean_rps_difference":
                QUOTED_VALIDATION["weekly_refit_mean_rps_difference"],
            "both_intervals_cross_zero": True,
        },
        "rejected_variants": list(REJECTED_VARIANTS),
        "schedule": {
            "refit": ("annual expanding window, before each season's first "
                      "issuance and at no other time"),
            "refit_corpus": ("the pinned parquet plus the shadow ledger's own "
                             "rows admissible at that cutoff"),
            "invalidation": ("any change to decay, widening, inference or "
                             "scoreline-model semantics invalidates a until it "
                             "is revalidated"),
            "drift_trigger": None,
            "weekly_refit": "REFUSED, not built",
        },
        "control": {
            "fixture_id": CONTROL_FIXTURE,
            "probs_raw": dict(CONTROL_PROBS),
            "probs_recal": control,
            "sum_minus_one": sum(control.values()) - 1.0,
            "outcome": CONTROL_OUTCOME,
            "rps_raw": rps(CONTROL_PROBS, CONTROL_OUTCOME),
            "rps_recal": rps(control, CONTROL_OUTCOME),
            "change": rps(control, CONTROL_OUTCOME)
                      - rps(CONTROL_PROBS, CONTROL_OUTCOME),
            "note": ("the transform scored WORSE on this fixture, recorded "
                     "deliberately; A8 pre-states no expectation about the "
                     "sign of any live difference"),
        },
        "language_rule": {
            "challenger": CHALLENGER_PHRASE,
            "published_law": PUBLISHED_LAW_PHRASE,
            "forbidden": list(FORBIDDEN_PHRASES),
        },
    }


def render_grounding_markdown(doc: Mapping[str, Any]) -> str:
    """The same numbers in the house voice, short, and bound by A8 (e)."""
    fit = doc["fit"]
    corpus = doc["corpus"]
    quoted = doc["validation_quoted"]
    control = doc["control"]
    pooled = doc["loso_pooled_rederived"]

    lines = [
        f"# `{doc['arm']}` — the grounding under the frozen rule",
        "",
        "*Regenerated by "
        "`PYTHONPATH=src:. .venv/bin/python -m epl.recalfit`. This file carries "
        "no clock and no environment: every number is computed from the pinned "
        "corpus, so a regeneration that changes a byte is a change in the "
        "corpus or in the rule.*",
        "",
        f"Amendment {doc['amendment']} is the authority; this file is its "
        "arithmetic, kept as an artifact rather than as prose in a design "
        "document. The challenger it grounds is "
        f"**{doc['language_rule']['challenger']}**, and the published law it "
        f"is measured against is **{doc['language_rule']['published_law']}**.",
        "",
        "## The rule, closed at one parameter",
        "",
        "```",
        f"{doc['transform']}",
        "```",
        "",
        f"Closed at {doc['class_closed_at']}. `a = 1` is the identity.",
        "",
        f"- **Corpus** `{corpus['path']}`, sha256 `{corpus['sha256']}` — "
        f"{corpus['n_rows']} rows, {len(corpus['seasons'])} seasons "
        f"({corpus['seasons'][0]}–{corpus['seasons'][-1]}), `y` counts "
        f"{' / '.join(str(c) for c in corpus['y_counts'])} over "
        f"{', '.join(corpus['y_encoding'][k] for k in ('0', '1', '2'))}. "
        f"{corpus['excluded_seasons'][0]} is excluded by "
        "`epl/config_frozen.json`, which is what makes the forward check a "
        "season the fit never saw.",
        f"- **Objective** {doc['objective']['name']}, this project's own "
        f"literal (`{doc['objective']['literal']}`), r = "
        f"{doc['objective']['r']}, ordered "
        f"({', '.join(doc['objective']['ordered'])}), "
        f"{doc['objective']['weighting']}.",
        f"- **Procedure** {doc['procedure']['method']}, bracket "
        f"`{doc['procedure']['bracket']}`, `xtol = {doc['procedure']['xtol']}`, "
        f"`rtol = {doc['procedure']['rtol']}`. Not a minimiser.",
        f"- **Constant** `a = {doc['a']}` (`T = 1/a = {doc['T']}`), "
        f"`rule_version = {doc['rule_version']}`.",
        f"- **Schedule** {doc['schedule']['refit']}; refit corpus is "
        f"{doc['schedule']['refit_corpus']}; {doc['schedule']['invalidation']}; "
        "drift trigger **NONE, explicitly**; weekly in-season refitting "
        f"**{doc['schedule']['weekly_refit']}**.",
        "",
        "## The fit",
        "",
        "| quantity | value |",
        "|---|---:|",
        f"| mean RPS at `a = 1` (the published law, untransformed) | "
        f"`{fit['mean_rps_at_one']!r}` |",
        f"| mean RPS at the pinned procedure's root | `{fit['mean_rps_at_root']!r}` |",
        f"| the transform's entire in-sample gain | `{fit['in_sample_gain']!r}` |",
        f"| the root, from {len(fit['brackets'])} brackets | `{fit['root']!r}` |",
        f"| the frozen literal | `{fit['literal']!r}` |",
        f"| literal − root | `{fit['literal_minus_root']!r}` |",
        f"| mean RPS at the frozen literal | `{fit['mean_rps_at_literal']!r}` |",
        f"| one ulp of the objective there | "
        f"`{fit['one_ulp_of_objective']!r}` |",
        "",
        "**The frozen literal is not the argmin at twelve decimals, and this "
        "file says so rather than implying otherwise.** The derivative at the "
        f"literal is `{fit['derivative_at_literal']!r}` and not zero. The "
        "objective cannot tell the two apart — both evaluate to the same "
        "double — but the procedure can, and a claim that they are equal would "
        "be false.",
        "",
        "## What the corpus resolves, and what it does not",
        "",
        "| season dropped | `a` | out-of-fold mean-RPS gain |",
        "|---|---:|---:|",
    ]
    for row in doc["loso"]:
        lines.append(f"| {row['season']} | `{row['a']!r}` | "
                     f"`{row['mean_rps_gain']:+.6f}` |")
    lines += [
        "",
        f"A span of `{doc['loso_span']:.4e}`. **The corpus resolves `a` to "
        "roughly ±0.03, so about ten of the twelve recorded decimals are "
        "bookkeeping and not information.** They are recorded to twelve places "
        "for one reason: so that `probs_recal` is a bit-reproducible function "
        "of `probs_raw`. Nothing in this project may claim the corpus knows "
        "`a` to twelve decimals.",
        "",
        f"Pooled over all {pooled['n_rows']} out-of-fold rows, re-derived here: "
        f"`{pooled['mean_rps_gain']:+.6f}`, 95% normal-approximation interval "
        f"`[{pooled['ci_95'][0]:+.6f}, {pooled['ci_95'][1]:+.6f}]`, better in "
        f"{pooled['seasons_better']} of {pooled['seasons_total']} seasons. "
        "The interval below is the one A8 (e) quotes and is the authority; the "
        "two point estimates agree, and the bounds differ in the third "
        "significant figure because the interval method is not the same one. "
        "Both cross zero either way.",
        "",
        "## Validation — quoted, and not re-derived here",
        "",
        f"*{quoted['note']}*",
        "",
        "| | |",
        "|---|---|",
        f"| Calibration slope, published law, pinned no-intercept exponent test "
        f"| **{quoted['calibration_slope_published_law']}**, "
        f"p = **{quoted['calibration_slope_p_value']}** |",
        f"| LOSO slope after the transform | "
        f"**{quoted['calibration_slope_published_law']} → "
        f"{quoted['loso_slope_after_transform']}** |",
        f"| LOSO mean-RPS difference | "
        f"**+{quoted['loso_mean_rps_difference']}**, 95% CI "
        f"**[{quoted['loso_ci_95'][0]}, +{quoted['loso_ci_95'][1]}]**, better "
        f"in **{quoted['loso_seasons_better']} of "
        f"{quoted['loso_seasons_total']}** seasons |",
        f"| Forward, 2025/26 (out of corpus) | "
        f"**+{quoted['forward_2025_26_mean_rps_difference']}**, CI **crossing "
        "zero** |",
        f"| Forward slope | **{quoted['forward_slope'][0]} → "
        f"{quoted['forward_slope'][1]}** |",
        f"| Weekly in-season refitting | "
        f"**{quoted['weekly_refit_mean_rps_difference']}** — refused, not "
        "built |",
        "",
        "**Both intervals cross zero. That is the finding, not a footnote to "
        "it.** Four of six seasons improved, which is two short of six. The "
        "slope evidence is the more direct half — a slope moving from 0.9035 "
        "to 1.0008 out of sample is the defect being corrected on the axis it "
        "was diagnosed on — and it is still one statistic on six seasons.",
        "",
        "**Rejected by name, so nobody re-proposes one as a new idea:** "
        + ", ".join(f"**{name}**" for name in doc["rejected_variants"])
        + " were each measured worse out of sample. They are not alternatives "
        "awaiting a second look; they were looked at.",
        "",
        "## The control A8 pre-stated",
        "",
        f"`{control['fixture_id']}` at the frozen `a`, from the **published** "
        "marginals and never from a rendered four-decimal string:",
        "",
        "```",
        "probs_raw   = " + " / ".join(
            f"{k} {control['probs_raw'][k]:.6f}" for k in OUTCOMES),
        "probs_recal = " + " / ".join(
            f"{k} {control['probs_recal'][k]:.12f}" for k in OUTCOMES),
        f"sum - 1     = {control['sum_minus_one']:.2e}",
        f"rps_raw     = {control['rps_raw']:.12f}",
        f"rps_recal   = {control['rps_recal']:.12f}",
        f"change      = {control['change']:+.12f}",
        "```",
        "",
        f"**{control['note'][0].upper()}{control['note'][1:]}.**",
        "",
        "A four-decimal control cannot tell two different inputs apart: the "
        "rendered triple `0.7639 / 0.1618 / 0.0743` transforms to a vector "
        "that renders identically at 4dp and differs at the sixth decimal. "
        "Derive from the file's own probabilities and assert at 1e-9 or "
        "better.",
        "",
        "## The language rule",
        "",
        f"`{doc['arm']}` is **{doc['language_rule']['challenger']}**. The "
        f"published law is **{doc['language_rule']['published_law']}**. "
        "Neither of the two phrases A8 (e) forbids appears on any surface this "
        "project writes, here included. No arm switch this season: `dc_native` "
        "remains the published arm through 2026/27 whatever the shadow ledger "
        "accumulates, and a switch is a new amendment written before the "
        "switch. Quarterly summaries have no pass rule, no trigger and no "
        "threshold.",
        "",
        f"Machine-readable beside this file: `{GROUNDING_JSON.name}`.",
        "",
    ]
    return "\n".join(lines)


def write_grounding(json_path=None, md_path=None, *, corpus=None,
                    expect_sha256: str = CORPUS_SHA256) -> tuple[Path, Path]:
    """Write both grounding artifacts and give back their paths, JSON first."""
    doc = grounding(corpus, expect_sha256=expect_sha256)
    json_out = Path(GROUNDING_JSON if json_path is None else json_path)
    md_out = Path(GROUNDING_MD if md_path is None else md_path)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(leaguesim.canonical_json(doc) + "\n")
    md_out.write_text(render_grounding_markdown(doc))
    return json_out, md_out


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m epl.recalfit` — regenerate the grounding artifacts.

    A refusal prints `STOP: <TypeName>: …` and exits 2, like every other typed
    refusal in this project. A refusal an operator cannot tell from a crash
    teaches them to ignore crashes.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m epl.recalfit",
        description="regenerate the dc_1x2_recal grounding artifacts")
    parser.add_argument("--corpus", default=None,
                        help=f"the pinned corpus (default {CORPUS_PATH})")
    parser.add_argument("--json", default=None)
    parser.add_argument("--md", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        json_out, md_out = write_grounding(args.json, args.md,
                                           corpus=args.corpus)
    except RecalError as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"[recalfit] {json_out}")
    print(f"[recalfit] {md_out}")
    return 0


__all__ = [
    "ARM", "RULE_VERSION", "OUTCOMES", "A", "T", "CORPUS_PATH",
    "CORPUS_SHA256", "CORPUS_ROWS", "CORPUS_SEASONS", "CORPUS_Y_COUNTS",
    "PROBS_COLUMNS", "BRACKET", "XTOL", "RTOL", "PARAM_TOLERANCE",
    "RECAL_TOLERANCE", "SUM_TOLERANCE", "CHALLENGER_PHRASE",
    "PUBLISHED_LAW_PHRASE", "FORBIDDEN_PHRASES", "REJECTED_VARIANTS",
    "QUOTED_VALIDATION", "GROUNDING_JSON", "GROUNDING_MD",
    "RecalError", "CorpusMissing", "CorpusDigestMismatch", "RefitOutOfBounds",
    "ObjectiveInferior", "RecalMismatch", "SchemaMismatch", "RowInadmissible",
    "RowConflict",
    "transform", "transform_rows", "rps", "rps_rows", "mean_rps", "d_mean_rps",
    "sha256_file", "load_corpus", "fit_from_rows", "fit_a", "mean_rps_at",
    "loso", "loso_pooled", "verify_fit", "CONTROL_FIXTURE", "CONTROL_PROBS",
    "CONTROL_OUTCOME", "GROUNDING_BRACKETS", "grounding",
    "render_grounding_markdown", "write_grounding", "main",
]


if __name__ == "__main__":                                  # pragma: no cover
    import sys

    sys.exit(main())
