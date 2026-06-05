"""Empirical de-vig selection — Shin prior, best-calibrated-of-close chosen by RPS.

The benchmark price comes from de-vigging the bookmaker's overround OUT of the
quoted odds. THREE methods are choosable — Shin (the prior; counteracts the
favourite-longshot bias football runs WITH), multiplicative, and power — and the
best-calibrated de-vig of the close is chosen EMPIRICALLY by Ranked Probability
Score on the realised 1X2 outcomes (lockbox DOF #7), NOT assumed.

Buchdahl / odds-proportional is DELIBERATELY ABSENT from ``DEVIG_METHODS``: it is
sensitivity-only and NEVER promoted, because it manufactures phantom value in the
favourite-longshot direction. Including it as a choosable method would let the
selection pick a biased de-vig that flatters the model — exactly the overfit this
guards against.

A de-vig that yields a negative / sign-flipped implied probability is handled
upstream as a non-bet (``odds_ingest.non_bet_snapshot``); here the de-vig
functions are the pure ``wcmodel.data.devig`` ones, which already pin the
zero-vig Shin limit and renormalise to sum 1.
"""
from __future__ import annotations

from wcmodel.config import load_config
from wcmodel.data import devig as _devig
from wcmodel.backtest.odds_ingest import OUTCOMES

#: The ONLY choosable de-vig methods. Buchdahl is never here (see module docstring).
DEVIG_METHODS = ("shin", "multiplicative", "power")

_FUNCS = {
    "shin": _devig.shin,
    "multiplicative": _devig.multiplicative,
    "power": _devig.power,
}


def devig(odds: list[float], *, method: str) -> list[float]:
    """De-vig ``odds`` (ordered by ``OUTCOMES``) -> implied probs summing to 1.

    ``method`` must be one of ``DEVIG_METHODS``; Buchdahl is rejected (never
    promoted).
    """
    if method not in _FUNCS:
        raise ValueError(
            f"de-vig method {method!r} not choosable; pick from {DEVIG_METHODS} "
            f"(Buchdahl/odds-proportional is sensitivity-only, never promoted)"
        )
    return _FUNCS[method](odds)


def _rps(probs: list[float], outcome: str) -> float:
    """Ranked Probability Score for one 3-way forecast vs the realised outcome.

    RPS = sum over the first K-1 categories of (cumulative_pred - cumulative_obs)^2,
    on the ordered categories ``OUTCOMES`` = (home, draw, away). For a 3-way market
    RPS lies in [0, 2]; lower is better-calibrated.
    """
    obs = [1.0 if o == outcome else 0.0 for o in OUTCOMES]
    cum_p = cum_o = 0.0
    total = 0.0
    for k in range(len(OUTCOMES) - 1):           # K-1 = 2 cumulative terms
        cum_p += probs[k]
        cum_o += obs[k]
        total += (cum_p - cum_o) ** 2
    return total


def rps_of_devig(odds_list: list[list[float]], outcomes: list[str],
                 *, method: str) -> float:
    """Mean RPS of ``method``'s de-vigged probabilities over realised ``outcomes``.

    Raises ``ValueError`` on any length/shape mismatch: ``odds_list`` and
    ``outcomes`` must have the SAME length (a silent ``zip`` truncation would score
    only a subset and report a wrong calibration number), and every odds row must
    be exactly ``len(OUTCOMES)`` (= 3) wide (a malformed 1X2 vector).
    """
    if not odds_list:
        return float("nan")
    if len(odds_list) != len(outcomes):
        raise ValueError(
            f"rps_of_devig length mismatch: {len(odds_list)} odds rows vs "
            f"{len(outcomes)} realised outcomes — refusing to zip-truncate"
        )
    n = len(OUTCOMES)
    for o in odds_list:
        if len(o) != n:
            raise ValueError(
                f"rps_of_devig: each decimal-odds row must have len(OUTCOMES)={n} "
                f"entries (got {len(o)})"
            )
    scores = [_rps(devig(o, method=method), y) for o, y in zip(odds_list, outcomes)]
    return sum(scores) / len(scores)


def choose_devig(odds_list: list[list[float]], outcomes: list[str],
                 *, config: dict | None = None) -> tuple[str, dict]:
    """Pick the empirically best-calibrated de-vig of the close (lockbox DOF #7).

    Scores EVERY method in ``DEVIG_METHODS`` by mean RPS on the realised closing
    odds + outcomes (the sensitivity table) and returns ``(best_method, table)``.
    Ties (or an empty calibration set) fall back to the configured prior
    (``backtest.devig_method``, default Shin) — never a silent arbitrary pick.

    The configured prior is VALIDATED ∈ ``DEVIG_METHODS`` (which excludes Buchdahl):
    a config that (mis)sets ``devig_method`` to ``"buchdahl"`` or anything not
    choosable is NOT promoted — it falls back to ``"shin"``. Buchdahl manufactures
    phantom favourite-longshot value, so it can never be promoted via the config
    prior, not even on the empty-calibration path.
    """
    cfg = config or load_config()
    prior = cfg["backtest"]["devig_method"]
    if prior not in DEVIG_METHODS:
        # Never promote an un-choosable prior (e.g. buchdahl) — fall back to Shin.
        prior = "shin"
    if not odds_list:
        return prior, {m: float("nan") for m in DEVIG_METHODS}
    table = {m: rps_of_devig(odds_list, outcomes, method=m) for m in DEVIG_METHODS}
    best_rps = min(table.values())
    # Deterministic tie-break: prefer the prior, else the DEVIG_METHODS order.
    if abs(table[prior] - best_rps) < 1e-12:
        return prior, table
    for m in DEVIG_METHODS:
        if abs(table[m] - best_rps) < 1e-12:
            return m, table
    return prior, table
