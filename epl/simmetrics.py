"""The scores the retrospective reports — fixed before any of them exists.

Plan v2 §5 is a preregistration. Its point is that the metric set, and the
convention behind every one of them, is written down while the answer is still
unknown, so that "which number is the headline" cannot be decided by which
number came out well. This module is that list, made executable. Nothing here
knows about arms, seasons or cutoffs; it takes a forecast and an outcome and
returns a score.

The primary metric
------------------
**TRPS** — the tournament rank probability score of Ekstrøm, Van Eetvelde, Ley
and Brefeld (arXiv:1912.07364, eq. 2):

    TRPS(O, X) = (1/T) Σ_t (1/(R−1)) Σ_{r=1..R−1} (O_rt − X_rt)²

with ``X_rt = Σ_{i≤r} X_it`` the cumulative probability that club *t* finishes
in position *r* or better, and ``O_rt = 1[position_t ≤ r]``. For a 20-club
league with a full ranking that is a flat ``1/(20·19)`` over 20 clubs × 19
boundaries — unweighted, every boundary counted once. It is proper **for the
displayed marginals**, not for the joint law over the 20! orderings: two
forecasts with the same position matrix and different correlation structure
score identically, and this document says so rather than implying more.

The primary is unweighted on purpose (adjudication item 14). A score
concentrated on the four or five boundaries the product actually publishes has
far more variance across seven seasons than one that aggregates 19 × 20 = 380
comparisons, and it needs a band map that is ours rather than the paper's. The
boundary-weighted form is reported second, because it scores what the product
shows.

Everything else here is a diagnostic beside that: consequence Briers, a floored
champion log loss demoted from headline to diagnostic (it is local — it reads
one cell of the matrix and ignores the rest — and it is undefined when the
forecast gave the realised champion no mass at all), points CRPS/MAE/coverage
from the retained rows, and the per-boundary decider rates that answer "did the
scoreline model matter at table level" directly.

Two rules that the callers must not be able to break
----------------------------------------------------
1. **A matrix is scored only if it is admissible.** Rows summing to something
   other than 1 make TRPS meaningless rather than merely bad, so every entry
   point checks (plan v2 D10, and the paper's own §2.1 condition).
2. **Nothing here averages across cutoffs.** A forecast at the opener and one
   at matchweek 19 answer different questions; pooling them produces a number
   that describes neither. This module scores one forecast at a time and
   :mod:`epl.simretro` keeps the cutoff label attached to it.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_simretro.py -q
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from epl import leaguesim, table as table_mod

__all__ = [
    "scored_matrix", "matrix_margin_errors", "trps_se", "trps_se_cluster",
    "CONSEQUENCE_RANKS", "MetricError", "SCHEMA_VERSION", "TRPS_REFERENCE",
    "boundary_decider_rates", "champion_logloss_floored", "consequence_briers",
    "consequence_weights", "cumulative_forecast", "cumulative_outcome",
    "flat_trps", "interval_coverage", "points_crps", "points_from_histogram",
    "points_histogram", "points_mae", "trps", "wtrps",
]

SCHEMA_VERSION = "epl-simmetrics-1"

#: The published score and the edition these formulas were read from.
TRPS_REFERENCE = (
    "Ekstrom, Van Eetvelde, Ley & Brefeld, 'Evaluating one-shot tournament "
    "predictions', arXiv:1912.07364 (eq. 2 TRPS, eq. 4 wTRPS)")

#: Boundaries the product publishes, as ranks r in the cumulative sum: r=1 is
#: champion|rest, 4 is top-4|5th, 5 is top-5|6th, 7 is top-7|8th and 17 is
#: safe|relegated. 6|7 is in the RANKER's materiality set (Handbook semantics)
#: but is not a published market, so it carries no weight here (plan v2 §5).
CONSEQUENCE_RANKS = (1, 4, 5, 7, 17)

_TOL = 1e-8


class MetricError(ValueError):
    """A forecast or an outcome that cannot be scored as it stands."""


# ==========================================================================
# the shared shape check
# ==========================================================================

def scored_matrix(matrix, n_clubs: int | None = None) -> np.ndarray:
    """A stored matrix, checked on BOTH margins before anything scores it.

    A2 (d): `_as_matrix` checks shape, finiteness, non-negativity and ROW sums —
    "every club must finish somewhere" — and stops there. `check_doubly_stochastic`
    checks both margins and runs on a freshly simulated result, but never on a
    matrix read back OUT of the ledger, and the scoring path is the one that
    turns a stored row into a published number. A stored matrix whose columns
    have drifted — rows still summing to 1, position mass no longer conserved —
    scored silently.

    Square shape is checked here too, and for the same reason: a 20-club league
    has 20 positions, and a matrix that is not square is not a position matrix
    at all. The tolerance is `epl.table.check_doubly_stochastic`'s own 1e-8, not
    a looser number chosen to let something through.
    """
    out = _as_matrix(matrix)
    if out.shape[0] != out.shape[1]:
        raise MetricError(
            f"a stored position matrix is square — {out.shape[0]} clubs and "
            f"{out.shape[1]} positions is not a ranking of anything")
    if n_clubs is not None and out.shape[0] != int(n_clubs):
        raise MetricError(
            f"the stored matrix is {out.shape} for {int(n_clubs)} clubs")
    table_mod.check_doubly_stochastic(out)
    return out


def matrix_margin_errors(matrix) -> tuple[float, float]:
    """``(worst row-sum deviation, worst column-sum deviation)`` from 1."""
    out = np.asarray(matrix, dtype=float)
    return (float(np.abs(out.sum(axis=1) - 1.0).max()),
            float(np.abs(out.sum(axis=0) - 1.0).max()))


def trps_se(matrix, positions, matrix_se) -> float | None:
    """The DIAGONAL APPROXIMATION to the delta-method MC variance of TRPS.

    A2 (c) relabelled the harness's misnamed `MC SE` column and recorded a TRPS
    Monte-Carlo error as an OPEN ITEM, explicitly out of scope for v2. This
    supplies it, and the deviation from that pre-statement is recorded as a
    dated note under A2 rather than made quietly.

    METHOD, stated because the number is only as good as it.
    TRPS is a smooth function of the matrix cells through the cumulative
    forecast, so with `g = dTRPS/dm` evaluated at the reported matrix::

        g[c, k] = 2 / (C (R-1)) * sum_{r >= k} (X[c, r] - O[c, r])
        Var(TRPS) ~= sum_{c, k} g[c, k]^2 * se[c, k]^2

    where `se` is the run's own cluster-by-particle per-cell error. The exact
    delta-method variance is the full quadratic form over every PAIR of cells;
    this keeps only the terms with `(c, k) == (c', k')`.

    WHAT THE APPROXIMATION IS NOT (amendment A2-N4, 2026-08-20). The cross-cell
    covariance is omitted, and because the TRPS gradient changes sign within a
    club's row the omitted terms can raise or lower the variance, so the
    direction of the approximation is not known. What is dropped is
    `g * g' * Cov`, not `Cov`: a club's cells are predominantly negatively
    correlated, but `X[c, r] - O[c, r]` is non-negative for ranks below the
    club's realised position and non-positive at and above it, so a negative
    covariance multiplied by two gradient components of opposite sign
    contributes a POSITIVE term. A2-N1 concluded from the negative correlation
    alone that this figure overstates the variance; that conclusion does not
    follow and A2-N4 withdraws it. Report the quantity as
    `TRPS MC SE (diagonal approx.)`.

    It is a Monte-Carlo error only — it says nothing about model error, and
    nothing about the fact that TRPS is proper for the displayed marginals and
    not for the joint law. :func:`trps_se_cluster` is the estimator that needs
    none of these assumptions, for runs that retain per-particle tallies.

    Returns None when the run recorded no per-cell error (the nulls do not).
    """
    if matrix_se is None:
        return None
    x = cumulative_forecast(matrix)
    n_clubs, n_ranks = np.shape(matrix)
    o = cumulative_outcome(positions, n_clubs, n_ranks)
    se = np.asarray(matrix_se, dtype=float)
    if se.shape != (n_clubs, n_ranks):
        raise MetricError(
            f"matrix_se is {se.shape}, expected {(n_clubs, n_ranks)}")
    if not np.isfinite(se).all() or (se < 0).any():
        raise MetricError("matrix_se carries a non-finite or negative entry")
    residual = x - o                                   # [clubs, ranks-1]
    # dX[c, r]/dm[c, k] = 1 for k <= r, so the derivative at cell k is the
    # reverse cumulative sum of the residuals from k to R-1.
    tail = np.cumsum(residual[:, ::-1], axis=1)[:, ::-1]
    g = np.zeros((n_clubs, n_ranks), dtype=float)
    g[:, : n_ranks - 1] = 2.0 * tail / (n_clubs * (n_ranks - 1))
    return float(np.sqrt(float((g ** 2 * se ** 2).sum())))


def trps_se_cluster(tallies, positions, *, n_boot, seed) -> float:
    """A Monte-Carlo standard error for TRPS, by cluster-by-particle bootstrap.

    Amendment A2-N4 (3). The delta method above approximates a variance whose
    direction it cannot sign. This estimator answers the question that
    approximation was approximating: resample the PARTICLES — the same cluster
    the stored per-cell `matrix_se` is already built on — with replacement,
    recompute the position matrix from the resampled tallies, recompute TRPS on
    each resample, and report the standard deviation of the resampled TRPS
    values. It needs no independence assumption, no gradient and no covariance
    matrix, and it is an error ON TRPS rather than one propagated from cells.

    `tallies` is ``[n_particles, n_clubs, n_ranks]``: how often each club
    finished in each rank, per particle. It is what a run must RETAIN to be able
    to report this number; R1's ledger stores per-cell errors, not per-particle
    tallies, which is why A2-N4 states the bootstrap as a requirement on future
    runs rather than as something the existing ledger can be made to answer.

    `n_boot` and `seed` have NO defaults, deliberately. A2-N4 pre-states that
    B and the resampling seed "are not chosen here; they are pre-stated in the
    amendment that accompanies the first run to report the bootstrap SE, before
    that run." A default here would be that choice, made by this module, after
    the fact — so the caller must supply both and no run in this repository
    reports the number yet.
    """
    counts = np.asarray(tallies, dtype=float)
    if counts.ndim != 3:
        raise MetricError(
            f"tallies is {counts.shape}, expected [particles, clubs, ranks]")
    if not np.isfinite(counts).all() or (counts < 0).any():
        raise MetricError("tallies carries a non-finite or negative entry")
    n_particles = counts.shape[0]
    if n_particles < 2:
        raise MetricError("a bootstrap over one particle resamples nothing")
    if int(n_boot) < 2:
        raise MetricError(f"n_boot={n_boot} cannot give a standard deviation")
    totals = counts.reshape(n_particles, -1).sum(axis=1)
    if totals[0] <= 0 or not np.allclose(totals, totals[0]):
        raise MetricError(
            "the particles carry unequal (or empty) tally totals; this "
            "resamples EQUAL clusters, as the stored per-cell error already "
            "does (plan v2 D15), and unequal ones would silently reweight the "
            "matrix a resample builds")

    rng = np.random.default_rng(int(seed))
    draws = np.empty(int(n_boot), dtype=float)
    for b in range(int(n_boot)):
        picked = rng.integers(0, n_particles, n_particles)
        total = counts[picked].sum(axis=0)
        row_sums = total.sum(axis=1, keepdims=True)
        if (row_sums <= 0).any():
            raise MetricError("a resampled club has no simulated position")
        draws[b] = trps(total / row_sums, positions)
    return float(draws.std(ddof=1))


def _as_matrix(matrix) -> np.ndarray:
    out = np.asarray(matrix, dtype=float)
    if out.ndim != 2:
        raise MetricError(f"a forecast matrix is [clubs, ranks], got {out.shape}")
    if out.shape[0] == 0 or out.shape[1] == 0:
        raise MetricError("a forecast matrix with no clubs or no ranks")
    if not np.isfinite(out).all():
        raise MetricError("the forecast matrix carries a non-finite entry")
    if (out < -_TOL).any():
        raise MetricError("negative mass in the forecast matrix")
    rows = out.sum(axis=1)
    if not np.all(np.abs(rows - 1.0) <= _TOL):
        raise MetricError(
            "every club must finish somewhere: worst row sum error "
            f"{float(np.abs(rows - 1.0).max()):.3e}. An inadmissible matrix is "
            "not a badly calibrated forecast, it is an unscoreable one.")
    return out


def _as_positions(positions, n_clubs: int, n_ranks: int) -> np.ndarray:
    out = np.asarray(positions)
    if out.ndim != 1 or out.size != n_clubs:
        raise MetricError(
            f"{out.size} realised positions for {n_clubs} clubs")
    if not np.issubdtype(out.dtype, np.integer):
        rounded = np.rint(out.astype(float))
        if not np.allclose(out.astype(float), rounded, atol=0, rtol=0):
            raise MetricError("realised positions must be whole ranks")
        out = rounded.astype(np.int64)
    out = out.astype(np.int64)
    if out.min() < 1 or out.max() > n_ranks:
        raise MetricError(
            f"realised positions run {out.min()}..{out.max()}, outside 1..{n_ranks}")
    return out


def cumulative_forecast(matrix) -> np.ndarray:
    """``X_rt`` for r = 1..R−1 — P(club finishes r-th or better), cumulated.

    The last rank is dropped: every club reaches at least the worst rank, so
    ``O_Rt − X_Rt`` is identically zero and the paper sums only to R−1.
    """
    out = _as_matrix(matrix)
    return np.cumsum(out, axis=1)[:, :-1]


def cumulative_outcome(positions, n_clubs: int, n_ranks: int) -> np.ndarray:
    """``O_rt`` — a step function that turns on at the rank the club obtained."""
    pos = _as_positions(positions, n_clubs, n_ranks)
    ranks = np.arange(1, n_ranks)[None, :]
    return (ranks >= pos[:, None]).astype(float)


# ==========================================================================
# 1. TRPS (primary) and wTRPS (secondary)
# ==========================================================================

def trps(matrix, positions) -> float:
    """The tournament rank probability score. Lower is better; 0 is perfect.

    `matrix` is ``[clubs, ranks]`` — the product's own orientation, one row per
    club summing to 1 — and `positions` the 1-based rank each club obtained.
    The paper writes its matrices ranks × teams; transpose at the call.

    For the 20-club league this is the unweighted ``1/(20·19)`` form: 20 clubs
    × 19 cumulative boundaries, every boundary counted once.
    """
    x = cumulative_forecast(matrix)
    n_clubs, n_ranks = np.shape(matrix)
    o = cumulative_outcome(positions, n_clubs, n_ranks)
    return float(((o - x) ** 2).sum() / (n_clubs * (n_ranks - 1)))


def consequence_weights(n_ranks: int = 20,
                        ranks: Sequence[int] = CONSEQUENCE_RANKS) -> np.ndarray:
    """Equal weight on the published consequence boundaries, zero elsewhere.

    The paper requires the weights to sum to R−1 so the weighted score stays on
    the unweighted one's scale; with five live boundaries out of nineteen that
    is 19/5 each. The band map is OURS, not the authors' — their 2019 example
    ("1 / 2-4 / 5 / 6-16 / 17-20") predates both a possible fifth Champions
    League place and this league's three-club relegation, so it is restated
    here against what the product actually publishes.
    """
    if n_ranks < 2:
        raise MetricError("weights need at least two ranks")
    ranks = tuple(int(r) for r in ranks)
    if not ranks:
        raise MetricError("weighted TRPS needs at least one live boundary")
    bad = [r for r in ranks if not 1 <= r <= n_ranks - 1]
    if bad:
        raise MetricError(f"boundary rank(s) {bad} outside 1..{n_ranks - 1}")
    if len(set(ranks)) != len(ranks):
        raise MetricError(f"duplicate boundary rank in {ranks}")
    out = np.zeros(n_ranks - 1, dtype=float)
    out[[r - 1 for r in ranks]] = (n_ranks - 1) / len(ranks)
    return out


def wtrps(matrix, positions, weights) -> float:
    """TRPS with per-boundary weights (paper eq. 4). Secondary, higher variance.

    `weights` has one entry per boundary r = 1..R−1 and must sum to R−1, which
    is the paper's scale condition and the only reason a weighted score is
    comparable to an unweighted one. Uniform weights reduce this exactly to
    :func:`trps`.
    """
    x = cumulative_forecast(matrix)
    n_clubs, n_ranks = np.shape(matrix)
    w = np.asarray(weights, dtype=float)
    if w.ndim != 1 or w.size != n_ranks - 1:
        raise MetricError(
            f"{w.size} weights for {n_ranks - 1} boundaries")
    if (w < 0).any() or not np.isfinite(w).all():
        raise MetricError("weights must be finite and non-negative")
    if abs(float(w.sum()) - (n_ranks - 1)) > 1e-9:
        raise MetricError(
            f"weights sum to {float(w.sum()):.6g}, not {n_ranks - 1}: the "
            "weighted score would not be on the unweighted score's scale")
    o = cumulative_outcome(positions, n_clubs, n_ranks)
    return float((w[None, :] * (o - x) ** 2).sum() / (n_clubs * (n_ranks - 1)))


def flat_trps(positions, n_ranks: int | None = None) -> float:
    """TRPS of the flat matrix, in closed form — the null that must be beaten.

    For the uniform ``1/R`` forecast, ``X_rt = r/R`` and the per-club sum is a
    sum of squares that telescopes. With a full ranking (R = T) of a permutation
    of 1..T the whole thing collapses to ``(T+1)/(6T)``, independent of the
    realised order — 0.175 for 20 clubs, and 0.2083 for the four-team example
    the paper prints. Computing it rather than simulating it means the null
    carries no Monte-Carlo error of its own.
    """
    pos = np.asarray(positions)
    n_clubs = int(pos.size)
    ranks = int(n_ranks if n_ranks is not None else n_clubs)
    pos = _as_positions(pos, n_clubs, ranks)
    if ranks < 2:
        raise MetricError("the flat null needs at least two ranks")

    def g(m):                      # Σ_{i=1..m} i²
        m = np.asarray(m, dtype=float)
        return m * (m + 1.0) * (2.0 * m + 1.0) / 6.0

    per_club = (g(pos - 1) + g(ranks - pos)) / float(ranks) ** 2
    return float(per_club.sum() / (n_clubs * (ranks - 1)))


# ==========================================================================
# 2. consequence markets
# ==========================================================================

def consequence_briers(matrix, positions) -> dict[str, float]:
    """Brier scores for the five markets the product publishes.

    `champion` is the 20-way multi-category Brier ``Σ_c (p_c − o_c)²`` — the
    original 1950 form, which reads the whole champion column rather than one
    cell. The other four are per-club binary Briers averaged over the clubs, so
    a market that 17 clubs are trivially out of is not flattered by them.
    """
    x = _as_matrix(matrix)
    n_clubs, n_ranks = x.shape
    pos = _as_positions(positions, n_clubs, n_ranks)
    slices = leaguesim.market_slices(n_ranks)

    out: dict[str, float] = {}
    for market in leaguesim.MARKETS:
        lo, hi = slices[market]
        p = x[:, lo:hi].sum(axis=1)
        o = ((pos > lo) & (pos <= hi)).astype(float)
        if market == "champion":
            out[market] = float(((p - o) ** 2).sum())
        else:
            out[market] = float(((p - o) ** 2).mean())
    return out


def champion_logloss_floored(p, n_sims: int) -> dict:
    """−ln p for the realised champion, floored at 0.5/N. **Diagnostic only.**

    Demoted from headline (adjudication item 13/14) for two reasons: it is
    local, so it ignores everything the forecast said about the other nineteen
    clubs, and a Monte-Carlo forecast that never once simulated the realised
    champion gives it probability exactly zero, at which point the score is
    infinite and the mean over seasons is decided entirely by that one cell.
    Flooring at half a simulation is the standard repair; the honest report is
    the floored value BESIDE the count of how often the floor was needed, so
    both are returned and :mod:`epl.simretro` prints both.
    """
    n_sims = int(n_sims)
    if n_sims <= 0:
        raise MetricError("the floor needs a positive simulation count")
    floor = 0.5 / n_sims

    values = np.atleast_1d(np.asarray(p, dtype=float))
    if values.ndim != 1:
        raise MetricError("champion probabilities must be a scalar or a vector")
    if not np.isfinite(values).all():
        raise MetricError("a non-finite champion probability")
    if (values < -_TOL).any() or (values > 1.0 + _TOL).any():
        raise MetricError("champion probabilities must lie in [0, 1]")

    floored = np.maximum(values, floor)
    per_entry = -np.log(floored)
    return {
        "value": float(per_entry.mean()),
        "floor": float(floor),
        "n": int(values.size),
        "n_floored": int((values < floor).sum()),
        "zero_hits": int((values <= 0.0).sum()),
        "per_entry": [float(v) for v in per_entry],
        "note": ("floored at 0.5/N; local and demoted to a diagnostic. "
                 "Read zero_hits before reading value."),
    }


# ==========================================================================
# 3. points
# ==========================================================================

def _points_arrays(rows, actual) -> tuple[np.ndarray, np.ndarray]:
    pts = np.asarray(rows)
    if pts.ndim != 2:
        raise MetricError(f"points rows are [sims, clubs], got {pts.shape}")
    truth = np.asarray(actual, dtype=float)
    if truth.ndim != 1 or truth.size != pts.shape[1]:
        raise MetricError(
            f"{truth.size} realised totals for {pts.shape[1]} clubs")
    return pts.astype(float), truth


def points_crps(rows, actual) -> np.ndarray:
    """Per-club CRPS of the simulated final-points distribution. Exact.

    For an empirical sample the CRPS is ``E|X − y| − ½E|X − X'|``, and the
    second term is computed from the sorted sample in O(N log N) rather than
    from the N² pairs:  ``ΣΣ|x_i − x_j| = 2 Σ_i (2i − N − 1) x_(i)``.
    """
    pts, truth = _points_arrays(rows, actual)
    n_sims = pts.shape[0]
    if n_sims == 0:
        raise MetricError("no simulated seasons to score")
    first = np.abs(pts - truth[None, :]).mean(axis=0)
    ordered = np.sort(pts, axis=0)
    i = np.arange(1, n_sims + 1, dtype=float)[:, None]
    second = ((2.0 * i - n_sims - 1.0) * ordered).sum(axis=0) / (n_sims ** 2)
    return first - second


def points_mae(rows, actual) -> float:
    """Mean absolute error of the expected points total, averaged over clubs.

    The MEAN residual is deliberately not reported: the simulated table and the
    realised one both hold the same total number of points up to adjustments,
    so a mean residual cancels to near zero however wrong the forecast is.
    """
    pts, truth = _points_arrays(rows, actual)
    return float(np.abs(pts.mean(axis=0) - truth).mean())


def interval_coverage(rows, actual, levels: Sequence[float] = (0.5, 0.9)) -> dict:
    """Share of clubs whose realised points fall inside a central interval.

    The bounds are empirical quantiles of the simulated points, taken with
    ``method="lower"`` on both sides so the interval is a set of attainable
    integer totals rather than an interpolation between them, and the test is
    inclusive of the endpoints.
    """
    pts, truth = _points_arrays(rows, actual)
    out: dict[str, float] = {}
    for level in levels:
        level = float(level)
        if not 0.0 < level < 1.0:
            raise MetricError(f"an interval level must be in (0, 1), got {level}")
        tail = (1.0 - level) / 2.0
        lo = np.quantile(pts, tail, axis=0, method="lower")
        hi = np.quantile(pts, 1.0 - tail, axis=0, method="lower")
        inside = (truth >= lo) & (truth <= hi)
        out[f"coverage{int(round(level * 100)):02d}"] = float(inside.mean())
    return out


def points_histogram(rows) -> dict:
    """Compress ``[sims, clubs]`` integer points into an exact per-club histogram.

    The retained rows are far too large for a JSONL ledger, but the metrics that
    read them — CRPS, coverage, quantiles — depend only on the empirical
    distribution, which a histogram over integer points preserves EXACTLY. The
    offset is stored because a points deduction can put a club below zero.
    """
    pts = np.asarray(rows)
    if pts.ndim != 2:
        raise MetricError(f"points rows are [sims, clubs], got {pts.shape}")
    if not np.issubdtype(pts.dtype, np.integer):
        rounded = np.rint(pts.astype(float))
        if not np.array_equal(rounded, pts.astype(float)):
            raise MetricError("a points histogram needs whole points")
        pts = rounded.astype(np.int64)
    lo = int(pts.min())
    width = int(pts.max()) - lo + 1
    counts = np.zeros((pts.shape[1], width), dtype=np.int64)
    for club in range(pts.shape[1]):
        counts[club] = np.bincount(pts[:, club] - lo, minlength=width)
    return {"lo": lo, "n_sims": int(pts.shape[0]),
            "counts": [[int(c) for c in row] for row in counts]}


def points_from_histogram(hist: dict) -> np.ndarray:
    """Rebuild a ``[sims, clubs]`` sample from :func:`points_histogram`.

    The sample comes back sorted rather than in the original sim order — the
    ledger deliberately does not keep which season produced which total, and no
    metric here needs it.
    """
    counts = np.asarray(hist["counts"], dtype=np.int64)
    lo = int(hist["lo"])
    values = np.arange(lo, lo + counts.shape[1], dtype=np.int64)
    columns = [np.repeat(values, counts[club]) for club in range(counts.shape[0])]
    sizes = {int(c.size) for c in columns}
    if len(sizes) != 1:
        raise MetricError(f"the histogram's clubs hold {sorted(sizes)} seasons each")
    if "n_sims" in hist and sizes != {int(hist["n_sims"])}:
        raise MetricError(
            f"the histogram declares {hist['n_sims']} seasons but holds {sizes.pop()}")
    return np.stack(columns, axis=1)


# ==========================================================================
# 4. "did the scorelines matter" — per-boundary deciders
# ==========================================================================

def boundary_decider_rates(ranking: table_mod.Ranking, points, gd, gf,
                           boundaries=None) -> dict[str, dict[str, float]]:
    """Per material boundary, the share of seasons each rung of the ladder settled.

    This is plan v2 §5's metric 6 and the most direct test the retrospective
    has of the question §0 asks: a boundary decided on POINTS needs no scoreline
    model at all, one decided on goal difference, goals scored or head-to-head
    does. If every consequence boundary is settled on points, native scoreline
    structure cannot be buying anything at table level whatever TRPS says.

    Signature note — plan v2 §6 writes this as ``(ranking, boundaries)``. A
    :class:`epl.table.Ranking` cannot answer the question on its own: its
    per-club ``resolution_code`` says what separated a club from ITS block, not
    what separated the two clubs straddling a given boundary, and those differ
    whenever a club is level with the club above and clear of the one below. The
    three totals arrays the retained rows already carry are therefore required
    arguments; nothing else about the contract changes.
    """
    boundaries = ranking.boundaries if boundaries is None else boundaries
    pts = np.asarray(points)
    gdiff = np.asarray(gd)
    gscored = np.asarray(gf)
    n_sims, n_clubs = pts.shape
    for name, arr in (("gd", gdiff), ("gf", gscored)):
        if arr.shape != pts.shape:
            raise MetricError(f"{name} is {arr.shape}, points {pts.shape}")
    if ranking.block_start.shape != pts.shape:
        raise MetricError(
            f"the ranking holds {ranking.block_start.shape} and the totals {pts.shape}")

    order = ranking.order.astype(np.int64)
    at_rung = lambda arr: np.take_along_axis(arr, order, axis=1)   # noqa: E731
    ladder_pts, ladder_gd, ladder_gf = at_rung(pts), at_rung(gdiff), at_rung(gscored)
    ladder_code = at_rung(ranking.resolution_code)

    out: dict[str, dict[str, float]] = {}
    for lo, hi in boundaries:
        lo, hi = int(lo), int(hi)
        if hi > n_clubs:
            continue
        a, b = lo - 1, hi - 1
        decider = np.where(
            ladder_pts[:, a] != ladder_pts[:, b], table_mod.UNIQUE,
            np.where(ladder_gd[:, a] != ladder_gd[:, b], table_mod.GD,
                     np.where(ladder_gf[:, a] != ladder_gf[:, b], table_mod.GF,
                              ladder_code[:, a])))
        counts = np.bincount(decider.astype(np.int64),
                             minlength=len(table_mod.RESOLUTION_NAMES))
        out[f"{lo}|{hi}"] = {name: float(counts[code] / n_sims)
                             for code, name in enumerate(table_mod.RESOLUTION_NAMES)}
    return out
