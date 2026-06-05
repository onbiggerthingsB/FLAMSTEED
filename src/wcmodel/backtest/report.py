"""Stratified reporting + the single-use lockbox + the permutation null (spec §2.8).

Every metric is STRATIFIED by tier (``tiers.py``: match_type × confederation ×
strength band); a stratum with too few sharp-priced fixtures (< ``MIN_STRATUM_N``)
is rendered as an explicit COVERAGE GAP — ``render_stratum`` emits the literal
string ``"insufficient coverage (n=<k>)"`` (the coverage denominator ``k`` = the
count of sharp-priced fixtures in the tier), NEVER a CLV/ROI number — so a thin
tier can never be silently dropped OR averaged into a headline (the obtainable
universe is selection-biased toward big matches; the minnow/progression tail is
thin). The report leads with CLV, states the baseline-beat verdict ("beat both or
say so"), and labels the whole thing a big-match REVISION-CONTAMINATED UPPER BOUND
(live forward-test is authoritative).

THE LOCKBOX (D4): the final 18% of odds-covered history BY DATE is frozen and
untouched during all tuning; the pre-registered config count = the 9 DOF. A
lockbox ROI ≈ the tuned-window ROI => the edge is real; a collapse => overfit.

THE PERMUTATION NULL (D4): 200 label shuffles; the model's real RPS must sit at
~the 99th percentile of the null (i.e. it beats ~99% of shuffles).
"""
from __future__ import annotations

import numpy as np

from wcmodel.backtest.clv import clv_summary
from wcmodel.backtest.odds_ingest import OUTCOMES
from wcmodel.backtest.staking import roi_metrics

#: A stratum with fewer than this many sharp-priced bets is a COVERAGE GAP, never
#: averaged into a headline (Phase-0 §5 selection-bias discipline).
MIN_STRATUM_N = 30


def lockbox_split(bets: list[dict], *, lockbox_fraction: float) -> tuple[list, list]:
    """Split bets into (tuned, lockbox) — the lockbox is the final ``lockbox_fraction``
    strictly BY DATE (the ``cutoff`` field), frozen. Returns ``(tuned, lockbox)``.

    The split is on a DATE THRESHOLD, never a raw bet-count slice: all bets sharing
    the boundary ``cutoff`` date go together into the lockbox, so a date with
    multiple bets can never straddle the split (a late date can never bleed into the
    tuned set). The target lockbox size ``n_lock`` is ``round(N * lockbox_fraction)``
    bets; the threshold is the date of the ``n_lock``-th bet from the end, and the
    lockbox is EVERY bet on or after that date. When dates are distinct this reduces
    exactly to the final ``n_lock`` bets.
    """
    if not bets:
        return [], []
    ordered = sorted(bets, key=lambda b: b["cutoff"])
    n_lock = int(round(len(ordered) * lockbox_fraction))
    if n_lock == 0:
        return ordered, []
    # Snap to a date threshold so same-date bets are never split across the boundary:
    # take the cutoff of the n_lock-th-from-end bet, then pull EVERY bet >= that date.
    threshold = ordered[-n_lock]["cutoff"]
    lock = [b for b in ordered if b["cutoff"] >= threshold]
    tuned = [b for b in ordered if b["cutoff"] < threshold]
    return tuned, lock


def _stratum_metrics(bets: list[dict]) -> dict:
    """CLV + ROI + RPS-vs-baselines + n for one stratum's bets."""
    clv = clv_summary([{"entry_odds": b["entry_odds"], "close_odds": b["close_odds"]}
                       for b in bets])
    roi = roi_metrics(pnls=[b["pnl"] for b in bets],
                      stakes=[b["stake"] for b in bets], start=1.0)
    out = {"n_bets": len(bets),
           **{f"clv_{k}": v for k, v in clv.items() if k != "n_bets"},
           **{f"roi_{k}": v for k, v in roi.items()}}
    for tag in ("model", "market", "elo"):
        key = f"rps_{tag}"
        vals = [b[key] for b in bets if key in b]
        out[f"mean_rps_{tag}"] = float(np.mean(vals)) if vals else float("nan")
    return out


def stratify(bets: list[dict], *, by: str) -> dict:
    """Group bets by a tier key (``match_type`` / ``confederation_home`` / …) and
    compute per-stratum metrics. Thin strata are still returned (with their small
    ``n``) so ``stratum_is_coverage_gap`` can flag them — never silently dropped."""
    groups: dict[str, list] = {}
    for b in bets:
        groups.setdefault(b[by], []).append(b)
    return {k: _stratum_metrics(v) for k, v in groups.items()}


def stratum_is_coverage_gap(stratum: dict) -> bool:
    """True iff the stratum has too few sharp-priced bets to report a number."""
    return stratum["n_bets"] < MIN_STRATUM_N


def render_stratum(stratum: dict) -> dict:
    """Render a stratum for the report, tying ``MIN_STRATUM_N`` to the coverage
    DENOMINATOR. A thin tier (n < ``MIN_STRATUM_N``) is rendered as an explicit
    coverage GAP — ``{"coverage_gap": True, "n_bets": k, "render":
    "insufficient coverage (n=k)"}`` — and carries NO CLV/ROI number (the headline
    fields are deliberately withheld so a sparse tier can never be mistaken for, or
    averaged as, a real number). A healthy tier renders its metrics with
    ``coverage_gap=False``. This is the single chokepoint the report calls per
    stratum, so the < 30 rule is enforced in ONE place, never bypassed."""
    if stratum_is_coverage_gap(stratum):
        k = stratum["n_bets"]
        return {"coverage_gap": True, "n_bets": k,
                "render": f"insufficient coverage (n={k})"}
    return {"coverage_gap": False, **stratum}


def baseline_beat_verdict(summary: dict) -> dict:
    """"Beat both or say so": did the model beat market-only AND naive-Elo on RPS,
    and earn positive ROI? Lower RPS is better.

    A baseline that is ABSENT or non-finite (``NaN``/``inf``) is treated as NOT
    beaten — a missing baseline can never silently pass the verdict. ``beats_both``
    requires the model RPS to be finite AND strictly below BOTH finite baseline RPS
    values AND positive ROI; anything missing or non-finite fails the claim.
    """
    m = summary.get("mean_rps_model", float("nan"))
    mkt = summary.get("mean_rps_market", float("nan"))
    elo = summary.get("mean_rps_elo", float("nan"))
    # `m < baseline` requires BOTH operands finite: an absent/NaN/inf baseline (or
    # model) RPS is NOT a beat, so a missing baseline can never pass by default.
    beats_market = np.isfinite(m) and np.isfinite(mkt) and m < mkt
    beats_elo = np.isfinite(m) and np.isfinite(elo) and m < elo
    positive_roi = summary.get("roi_roi", float("nan")) > 0
    return {
        "beats_market_rps": bool(beats_market),
        "beats_elo_rps": bool(beats_elo),
        "positive_roi": bool(positive_roi),
        "beats_both": bool(beats_market and beats_elo and positive_roi),
    }


def _rps(probs: dict, outcome: str) -> float:
    obs = [1.0 if o == outcome else 0.0 for o in OUTCOMES]
    cum_p = cum_o = total = 0.0
    for k in range(len(OUTCOMES) - 1):
        cum_p += probs[OUTCOMES[k]]
        cum_o += obs[k]
        total += (cum_p - cum_o) ** 2
    return total


#: Pre-registered minimum permutation-null shuffles (D4; mirrors config
#: backtest.permutation_shuffles = 200). A smaller null gives a misleadingly-
#: precise percentile, so ``permutation_null`` REFUSES it.
_MIN_PERMUTATION_SHUFFLES = 200


def permutation_null(model_probs: list[dict], outcomes: list[str], *,
                     shuffles: int, seed: int,
                     min_shuffles: int = _MIN_PERMUTATION_SHUFFLES) -> dict:
    """Label-permutation null: shuffle the realised outcomes ``shuffles`` times,
    recompute the model's mean RPS against each shuffle, and report where the REAL
    mean RPS sits in the null distribution.

    Returns ``{real_rps, n_shuffles, percentile}``. ``percentile`` is the fraction
    of shuffles the model BEATS (real RPS < shuffled RPS); a genuinely-informative
    model sits at ~0.99 (the 99th percentile). Seeded -> reproducible.

    Raises ``ValueError`` on an UNDER-SAMPLED null (``shuffles`` below the
    pre-registered minimum ``min_shuffles`` = 200, D4 — a tiny null reports a
    misleadingly-precise percentile) or on a ``model_probs``/``outcomes`` length
    mismatch / empty input / invalid outcome (a silent ``zip`` truncation would
    score only a SUBSET while looking like a full realised-outcome shuffle).
    """
    if len(model_probs) != len(outcomes):
        raise ValueError(
            f"permutation_null: model_probs ({len(model_probs)}) and outcomes "
            f"({len(outcomes)}) must be equal length -- refusing to zip-truncate"
        )
    if not outcomes:
        raise ValueError("permutation_null: empty input -- nothing to score")
    bad = sorted({o for o in outcomes if o not in OUTCOMES})
    if bad:
        raise ValueError(f"permutation_null: outcomes must be in {OUTCOMES}; got {bad}")
    if shuffles < min_shuffles:
        raise ValueError(
            f"permutation_null: shuffles={shuffles} is below the pre-registered "
            f"minimum {min_shuffles} (D4) -- an under-sampled null reports a "
            "misleadingly-precise percentile"
        )
    rng = np.random.default_rng(seed)
    real = float(np.mean([_rps(p, y) for p, y in zip(model_probs, outcomes)]))
    labels = np.array(outcomes, dtype=object)
    null = np.empty(shuffles)
    for i in range(shuffles):
        perm = labels[rng.permutation(len(labels))]
        null[i] = float(np.mean([_rps(p, y) for p, y in zip(model_probs, perm)]))
    beats = float(np.mean(real < null))
    return {"real_rps": real, "n_shuffles": shuffles, "percentile": beats}
