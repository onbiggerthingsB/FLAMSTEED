"""Model fair price, the two baselines, edge, and the RPS diagnostic.

``edge = model_fair_p - devigged_market_p`` (north-star §5.4), per outcome,
ordered by ``OUTCOMES``. The model's 1X2 fair price comes from
``Posterior.predict_1x2`` (Phase-2); the outright/progression fair price comes
from a ``SimResult`` progression column (Phase-3) and is handled in the
walk-forward engine (Task 5), not here.

TWO baselines, both scored through the IDENTICAL settle/RPS path so "beat both or
say so" is an apples-to-apples assertion (north-star §5.5):
  * MARKET-ONLY — the de-vigged close itself (``market_fair_1x2``).
  * NAIVE ELO   — ``elo_1x2_baseline`` on the SAME computed ratings the model
    feature uses (``elo_baseline_1x2`` — the coherence requirement: there is no
    second, divergent Elo).

RPS is the PRIMARY calibration diagnostic (never the target); it is the same
ranked-probability score the de-vig selection uses, on the ordered
``OUTCOMES`` = (home, draw, away).

RPS DRY note (OA finding 16)
----------------------------
There is now ONE canonical RPS codebase-wide: ``wcmodel.model.calibration.rps``,
the ÷2-normalized convention with range [0, 1]. This module's public ``rps``, the
private ``devig_select._rps``, and the private ``report._rps`` (the permutation
null's scorer) are thin container adapters that DELEGATE to it (dict-keyed here
and in ``report``, positional ``list[float]`` in ``devig_select``) — none carries
its own loop, so they cannot silently diverge. ``headroom._row_rps`` reaches the
same convention through this module's ``rps``. ``tests/eval/test_rps_canonical.py``
pins each adapter to the canonical value.

``calibration`` is the shared third module the earlier note called for: routing
through it avoids the circular import that blocked consolidation before
(``baselines`` imports ``devig`` from ``devig_select``, so ``devig_select``
importing from ``baselines`` would close a cycle; ``calibration`` imports neither).

SCALE CHANGE: RPS values reported by this module are HALF their pre-F16 values.
Sign, ordering and ratios are preserved; every RPS LEVEL and every RPS DIFFERENCE is
halved (Δ_new = Δ_old / 2). Any absolute threshold on a level OR on a delta must be
re-derived — a threshold left on the old [0, 2] scale silently demands twice the true
effect to fire, and any absolute RPS figure read from a pre-2026-07-28 report is on
that old scale. (Re-derived at the 2026-07-28 boundary: ``scripts/model_market_gap.py``
G1_SMALL/G1_LARGE, ``scripts/sweep_altitude.py`` TOL/TOO_GOOD,
``scripts/clv_validation.py`` RED_GAP; pinned by ``tests/eval/test_rps_scale_consumers.py``.)
"""
from __future__ import annotations

from wcmodel.data.elo import elo_1x2_baseline
from wcmodel.backtest.devig_select import devig
from wcmodel.backtest.odds_ingest import OUTCOMES
from wcmodel.model.calibration import rps as _canonical_rps


def model_fair_1x2(posterior, *, home: str, away: str, neutral: bool) -> dict:
    """The model's fair 1X2 price: ``Posterior.predict_1x2`` (Phase-2), ordered."""
    p = posterior.predict_1x2(home, away, neutral)
    return {o: float(p[o]) for o in OUTCOMES}


def market_fair_1x2(close_odds: dict, *, method: str) -> dict:
    """MARKET-ONLY baseline: de-vig the close into a fair 1X2 distribution.

    ``close_odds`` is ``{home, draw, away}`` decimal odds; the de-vig (lockbox
    DOF #7 method) removes the overround. Returns ``{home, draw, away}`` summing
    to 1.
    """
    probs = devig([close_odds[o] for o in OUTCOMES], method=method)
    return dict(zip(OUTCOMES, probs))


def elo_baseline_1x2(*, rating_home: float, rating_away: float, neutral: bool,
                     config: dict | None = None) -> dict:
    """NAIVE-ELO baseline: the SAME computed ratings -> 1X2 (coherence requirement).

    Wraps ``elo_1x2_baseline`` (config-threaded as of Task 0) and re-orders to
    ``OUTCOMES``.
    """
    p = elo_1x2_baseline(rating_home, rating_away, neutral, config=config)
    return {o: float(p[o]) for o in OUTCOMES}


def edge_vector(model: dict, market: dict) -> dict:
    """``edge = model - market`` per outcome, ordered by ``OUTCOMES``."""
    return {o: float(model[o]) - float(market[o]) for o in OUTCOMES}


def rps(probs: dict, outcome: str) -> float:
    """Canonical ÷2-normalized Ranked Probability Score in [0,1], lower better.

    Ordered categories ``OUTCOMES`` = (home, draw, away). ``probs`` is
    ``{home, draw, away}``; ``outcome`` is one of OUTCOMES. Delegates to
    ``wcmodel.model.calibration.rps`` — ONE convention codebase-wide (OA F16).
    """
    return _canonical_rps(probs, outcome)
