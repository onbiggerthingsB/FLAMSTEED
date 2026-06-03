"""Feature vs backtest windows — the corrected two-window framing (spec §5 / §10.4).

These are TWO DISTINCT date windows over the same match panel, and conflating
them is the bug this module exists to prevent:

* **Feature / model window** (:func:`feature_window`) — the recent, time-decayed
  slice (~``config['windows']['feature_years']`` years) that *informs* a single
  prediction. Bounded above by the prediction ``cutoff`` and below by
  ``cutoff - years``. This is the data a model is allowed to *learn from* for one
  as-of date.

* **Backtest window** (:func:`backtest_window`) — the **maximum odds-covered
  history available**. It is bounded ONLY below, by ``odds_start`` (the date the
  odds feed's coverage begins), and is **deliberately NOT cropped to
  ``feature_years``**: cropping it would throw away years of evaluable
  closing-line history. The number of *backtestable* matches is set by odds
  coverage, not by the feature window.

  ``odds_start`` magnitude is UNVERIFIED in Phase 0 — the headline The-Odds-API
  snapshot start is 2020-06-06, but the usable per-bookmaker depth for
  ``pinnacle`` / ``betfair_ex_*`` may begin later (per-bookmaker add-date caveat,
  Phase 0 §3e item 6). It must be set from the verified depth, not assumed; see
  ``reports/phase1_odds_depth.md``.

Both functions are pure (no I/O, no mutation of the input) and operate on a
``date`` column.
"""
from __future__ import annotations

import pandas as pd

from wcmodel.config import load_config


def feature_window(
    matches: pd.DataFrame,
    cutoff,
    years: float | None = None,
    config: dict | None = None,
) -> pd.DataFrame:
    """Recent, bounded slice that informs a prediction as of ``cutoff``.

    Returns the rows with ``cutoff - years*365 days <= date < cutoff``. The lower
    bound makes this a *finite* (bounded) window — the deliberate contrast with
    :func:`backtest_window`, which has no such crop. The upper bound is strict
    (``< cutoff``) so a match's own kickoff date is never fed to its prediction.

    Parameters
    ----------
    matches
        DataFrame with a ``date`` column (any pandas-parseable date dtype).
    cutoff
        As-of date; rows on or after it are excluded.
    years
        Window length in years (defaults to ``config['windows']['feature_years']``).
        A year is treated as 365 days, matching ``features.build``'s
        ``in_feature_window`` (``age_days <= feature_years * 365``).
    config
        Optional pre-loaded config dict (defaults to :func:`load_config`).
    """
    if years is None:
        cfg = config or load_config()
        years = float(cfg["windows"]["feature_years"])

    cutoff = pd.Timestamp(cutoff)
    start = cutoff - pd.Timedelta(days=years * 365)

    dates = pd.to_datetime(matches["date"])
    mask = (dates >= start) & (dates < cutoff)
    return matches.loc[mask].copy()


def backtest_window(matches: pd.DataFrame, odds_start) -> pd.DataFrame:
    """Maximum odds-covered history — bounded ONLY by ``odds_start``.

    Returns every row with ``date >= odds_start``. There is **no upper crop to
    ``feature_years``** — that omission is the entire point of this function. The
    backtest evaluates against the full odds-covered history (which keeps
    pre-feature-window matches), even though each individual prediction within
    that backtest only *learns* from its own :func:`feature_window`.

    Parameters
    ----------
    matches
        DataFrame with a ``date`` column.
    odds_start
        The date odds coverage begins (magnitude UNVERIFIED — set from the
        verified per-bookmaker depth, not assumed; see
        ``reports/phase1_odds_depth.md`` and Phase 0 §3e item 6).
    """
    odds_start = pd.Timestamp(odds_start)
    dates = pd.to_datetime(matches["date"])
    return matches.loc[dates >= odds_start].copy()
