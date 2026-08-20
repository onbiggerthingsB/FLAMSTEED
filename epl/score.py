"""Scoring rules and the paired comparison, with the conventions written down.

THE RPS CONVENTION, EXPLICITLY. Publications differ by a factor of two, so
which one is in use has to be stated rather than implied. This module uses the
NORMALISED (halved) three-outcome ranked probability score::

                1     r-1  /  i          i        \\ 2
    RPS  =  ---------  SUM |  SUM p_j  -  SUM o_j  |          r = 3
              r - 1    i=1 \\ j=1        j=1       /

over the categories in the fixed order ``(home, draw, away)``, where ``o`` is
the one-hot realised outcome. With ``r = 3`` the leading factor is ``1/2``, the
score lies in ``[0, 1]``, and a uniform ``(1/3, 1/3, 1/3)`` forecast scores
5/18 = 0.2778 on a home or away result and 1/9 = 0.1111 on a draw. The
un-normalised convention omits the ``1/(r-1)`` and is exactly twice these
numbers.

The bar this probe is measured against — de-vigged market ~0.196, walk-forward
Elo ~0.203, base rate ~0.234 — is on THIS convention. A silent factor of two
would put every forecaster at ~0.4 and make the whole comparison look like a
catastrophe, so :func:`rps` is pinned by unit tests against hand-computed values
and against ``wcmodel.model.calibration.rps``, the World Cup model's own
implementation, which is the same convention.

ORDER MATTERS. RPS is defined on ORDERED categories, and the order is
home < draw < away — the natural ordering of a result. Cumulating in any other
order (e.g. home, away, draw) silently produces a different, larger score that
punishes a correct favourite. The order is a module constant, not a caller
choice.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Sequence

import numpy as np

__all__ = [
    "OUTCOMES", "outcome_codes", "rps", "log_loss", "hit", "Score",
    "summarise", "paired_gap", "block_bootstrap_ci", "PairedGap",
]

#: The fixed cumulation order. Also the column order of every probability array
#: in this package.
OUTCOMES = ("home", "draw", "away")

_FTR_TO_CODE = {"H": 0, "D": 1, "A": 2}

#: Log loss clips probabilities away from zero. A forecaster that puts exactly
#: 0 on the realised outcome is infinitely wrong, and averaging infinities
#: destroys the whole column rather than the one match; 1e-15 is the same clip
#: the World Cup model uses, so the two projects' log losses are comparable.
_LOG_CLIP = 1e-15


def outcome_codes(ftr: Sequence[str] | np.ndarray) -> np.ndarray:
    """Map the source's ``H``/``D``/``A`` labels to codes in OUTCOMES order."""
    labels = np.asarray(ftr, dtype=object)
    unknown = sorted({str(v) for v in labels} - set(_FTR_TO_CODE))
    if unknown:
        raise ValueError(f"unknown result label(s) {unknown}; expected H/D/A")
    return np.array([_FTR_TO_CODE[str(v)] for v in labels], dtype=int)


def _check(probs: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = np.asarray(probs, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError(f"probabilities must be (n, 3) in {OUTCOMES} order; "
                         f"got {p.shape}")
    codes = np.asarray(y, dtype=int)
    if codes.shape != (p.shape[0],):
        raise ValueError(f"outcome shape {codes.shape} does not match "
                         f"{p.shape[0]} forecasts")
    if not np.isfinite(p).all():
        raise ValueError("non-finite probability")
    if (p < -1e-12).any() or (p > 1.0 + 1e-12).any():
        raise ValueError("probability outside [0, 1]")
    total = p.sum(axis=1)
    if not np.allclose(total, 1.0, atol=1e-9):
        worst = float(np.max(np.abs(total - 1.0)))
        raise ValueError(f"probabilities do not sum to 1 (worst |sum-1| = "
                         f"{worst:.3g}) — an unnormalised forecaster scores "
                         "better or worse than it deserves under every metric "
                         "here, silently")
    if not np.isin(codes, (0, 1, 2)).all():
        raise ValueError("outcome codes must be 0=home, 1=draw, 2=away")
    return p, codes


def rps(probs: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per-match normalised RPS — see the module docstring for the formula."""
    p, codes = _check(probs, y)
    onehot = np.zeros_like(p)
    onehot[np.arange(codes.size), codes] = 1.0
    cp = np.cumsum(p, axis=1)[:, :-1]        # r-1 = 2 cumulative terms
    co = np.cumsum(onehot, axis=1)[:, :-1]
    return ((cp - co) ** 2).sum(axis=1) / (len(OUTCOMES) - 1)


def log_loss(probs: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per-match natural-log loss, ``-ln P(realised)``, clipped at 1e-15."""
    p, codes = _check(probs, y)
    taken = p[np.arange(codes.size), codes]
    return -np.log(np.maximum(taken, _LOG_CLIP))


def hit(probs: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per-match 0/1 top-pick accuracy.

    Ties go to the earlier category in OUTCOMES order, which is what
    ``argmax`` does; exact ties do not occur on real forecasts here. Accuracy
    is reported because it is legible, not because it is a proper scoring rule
    — it ignores everything about a forecast except its argmax, and a
    forecaster can improve it while getting worse at RPS.
    """
    p, codes = _check(probs, y)
    return (p.argmax(axis=1) == codes).astype(float)


@dataclass(frozen=True)
class Score:
    forecaster: str
    n: int
    rps: float
    rps_se: float
    log_loss: float
    accuracy: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarise(name: str, probs: np.ndarray, y: np.ndarray) -> Score:
    """Mean RPS (with its naive iid standard error), log loss, and accuracy."""
    r = rps(probs, y)
    return Score(
        forecaster=name,
        n=int(r.size),
        rps=float(r.mean()),
        # Across-match SE of the MEAN, iid — honest for a level, not for a
        # difference between two forecasters on the same matches (see
        # `paired_gap`, whose paired SD is far smaller).
        rps_se=float(r.std(ddof=1) / np.sqrt(r.size)) if r.size > 1 else float("nan"),
        log_loss=float(log_loss(probs, y).mean()),
        accuracy=float(hit(probs, y).mean()),
    )


@dataclass(frozen=True)
class PairedGap:
    """``a`` minus ``b``, per match, summarised. Positive means ``a`` is WORSE
    (RPS is a loss)."""

    a: str
    b: str
    n: int
    mean: float
    sd: float
    se: float
    ci_low: float
    ci_high: float
    n_blocks: int
    block_by: str
    n_boot: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def paired_gap(name_a: str, rps_a: np.ndarray, name_b: str, rps_b: np.ndarray,
               ) -> tuple[np.ndarray, float, float]:
    """Per-match RPS differences ``a - b`` with their mean and paired SD.

    The paired SD is the number that decides whether a gap is real. Two
    forecasters scored on the same fixtures share almost all of the variance
    that the unpaired SE carries — the match was a 1-0 or it was not — so the
    unpaired SE on either level is roughly 0.19 while the SD of the DIFFERENCE
    is roughly a third of that. Comparing a gap of 0.007 against the unpaired
    number would declare every real difference invisible.
    """
    a = np.asarray(rps_a, dtype=float)
    b = np.asarray(rps_b, dtype=float)
    if a.shape != b.shape:
        raise ValueError(
            f"{name_a} scored {a.shape[0]} matches and {name_b} scored "
            f"{b.shape[0]}: a paired comparison requires the SAME matches in "
            "the same order — filter to the complete case first")
    d = a - b
    return d, float(d.mean()), float(d.std(ddof=1))


def block_bootstrap_ci(diffs: np.ndarray, block_labels: Sequence[Any],
                       n_boot: int = 10_000, alpha: float = 0.05,
                       seed: int = 20260814) -> tuple[float, float, int]:
    """Percentile CI for the mean of ``diffs`` under a moving-block resample.

    Blocks are resampled WITH REPLACEMENT, as many as there are, and the
    statistic is the pooled mean over the resampled matches. Blocking matters
    here because matches are not independent draws: a matchweek shares weather,
    fatigue, and — more to the point — a rating state, so a forecaster having a
    bad week produces a run of correlated differences that an iid bootstrap
    would treat as independent evidence and report a CI roughly ``sqrt(block
    size)`` too narrow.

    Blocks of unequal size are handled by pooling rather than by averaging
    block means: the estimator being bootstrapped is the mean over MATCHES, so
    the resample must reproduce that weighting.
    """
    d = np.asarray(diffs, dtype=float)
    labels = np.asarray(block_labels, dtype=object)
    if labels.shape != d.shape:
        raise ValueError(f"{labels.shape[0]} block labels for {d.shape[0]} "
                         "differences")
    if d.size == 0:
        raise ValueError("nothing to bootstrap")
    _, inverse = np.unique(labels, return_inverse=True)
    order = np.argsort(inverse, kind="mergesort")
    grouped = np.split(d[order], np.flatnonzero(np.diff(inverse[order])) + 1)
    sums = np.array([g.sum() for g in grouped])
    sizes = np.array([g.size for g in grouped])
    n_blocks = sums.size
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, n_blocks, size=(n_boot, n_blocks))
    means = sums[draw].sum(axis=1) / sizes[draw].sum(axis=1)
    lo, hi = np.quantile(means, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(lo), float(hi), int(n_blocks)
