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

RPS DRY note
------------
This module's public ``rps`` (dict-keyed) computes the SAME cumulative ranked
probability score as the private ``devig_select._rps`` (list-indexed) that
``devig_select.rps_of_devig`` calls during empirical de-vig selection (Task 1).
The two are numerically identical — same K-1 cumulative-squared-error loop on
the same ordered ``OUTCOMES``, same [0, 2] range — differing ONLY in input
container (this one takes a ``{home, draw, away}`` dict, the de-vig one takes a
positional ``list[float]``).

We KEEP both rather than consolidate. Making ``devig_select`` reuse this public
``rps`` would create a circular import: ``baselines`` imports ``devig`` from
``devig_select``, so ``devig_select`` importing ``rps`` from ``baselines`` closes
the cycle (``baselines -> devig_select -> baselines``) and breaks the package's
import — and Task 1's de-vig tests with it. A shared third module would be the
only clean consolidation, but that is more churn than a single 6-line loop
warrants. Instead the equivalence is LOCKED by a test
(``test_baselines_rps_equals_devig_select_rps``) that asserts the two agree on
randomised forecasts, so the public copy can never silently diverge.
"""
from __future__ import annotations

from wcmodel.data.elo import elo_1x2_baseline
from wcmodel.backtest.devig_select import devig
from wcmodel.backtest.odds_ingest import OUTCOMES


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
    """Ranked Probability Score of a 1X2 forecast vs the realised outcome.

    Ordered categories ``OUTCOMES`` = (home, draw, away); RPS in [0, 2], lower is
    better. ``probs`` is ``{home, draw, away}``; ``outcome`` is one of OUTCOMES.
    """
    obs = [1.0 if o == outcome else 0.0 for o in OUTCOMES]
    cum_p = cum_o = total = 0.0
    for k in range(len(OUTCOMES) - 1):
        cum_p += probs[OUTCOMES[k]]
        cum_o += obs[k]
        total += (cum_p - cum_o) ** 2
    return total
