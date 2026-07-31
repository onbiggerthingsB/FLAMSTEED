"""The FROZEN development-slate rule (OA Plan 2 v2, V0 / Codex finding 9).

Frozen before any coverage was inspected, and implemented here exactly once so
the config comment, the generator script and the V8 lock all describe the same
selection. Competition KEYS are an evidence choice; fixture SELECTION within
them is this rule and nothing else.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from wcmodel.config import load_config

#: The rule, verbatim. Pinned by tests — editing it is a prereg amendment, not
#: a refactor.
THE_RULE = (
    "every completed senior men's international in the probed competitions "
    "with kickoff in [2022-01-01, 2025-12-31], excluding any fixture in the "
    "scored pools' windows, ordered chronologically, truncated to the first "
    "N_dev with admissible coverage")

DEV_WINDOW = (date(2022, 1, 1), date(2025, 12, 31))

#: The CONFIRMATORY pools. Both end days are INSIDE the window (they are the
#: pools' own first and last match days), so a dev fixture on them is excluded.
SCORED_POOL_WINDOWS = (
    ("wc2022", date(2022, 11, 20), date(2022, 12, 18)),
    ("euro2024", date(2024, 6, 14), date(2024, 7, 14)),
    ("wc2026", date(2026, 6, 11), date(2026, 7, 19)),
)

_COLUMNS = ("match_id", "date", "home_team", "away_team",
            "home_score", "away_score", "tournament")


class DevSlateError(ValueError):
    """The slate cannot be built as specified — refuse rather than yield a
    slate whose size or membership silently differs from the rule."""


def load_dev_slate_config() -> dict:
    """The `oa_dev_slate:` block. Its window/exclusions must agree with the
    constants above; the generator asserts that before emitting."""
    return load_config()["oa_dev_slate"]


def _completed(frame: pd.DataFrame) -> pd.Series:
    """A played fixture: both scores present, finite, non-negative, integral.
    A float score is a parse artefact, not a 2.5-goal match — the same
    convention the Elo path applies."""
    ok = pd.Series(True, index=frame.index)
    for col in ("home_score", "away_score"):
        goals = pd.to_numeric(frame[col], errors="coerce")
        ok &= goals.notna() & (goals >= 0) & (goals == goals.round())
    return ok


def eligible_dev_fixtures(results: pd.DataFrame, *, competitions,
                          window=DEV_WINDOW,
                          scored_pool_windows=SCORED_POOL_WINDOWS
                          ) -> pd.DataFrame:
    """The rule up to (not including) truncation: filtered and ORDERED.

    Truncation needs coverage admissibility, which does not exist until the
    odds are acquired — so it is a separate step (``truncate_to_n_dev``) and
    this one is fully determined pre-acquisition."""
    competitions = list(competitions)
    if not competitions:
        raise DevSlateError(
            "no competitions given: the slate's competition keys are a "
            "coverage-evidence choice and must be set explicitly — an empty "
            "set silently yields an empty slate that reads as 'no coverage'")
    missing = [c for c in _COLUMNS if c not in results.columns]
    if missing:
        raise DevSlateError(f"results frame missing column(s) {missing}")
    frame = results.copy()
    # Unquoted YAML/parquet dates arrive as date, datetime or str: one padded
    # ISO form for the comparisons AND the manifest (same idiom as
    # eval/regulation.py).
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    keep = (frame["tournament"].isin(competitions)
            & (frame["date"] >= window[0]) & (frame["date"] <= window[1])
            & _completed(frame))
    for _pool, start, end in scored_pool_windows:
        keep &= ~((frame["date"] >= start) & (frame["date"] <= end))
    frame = frame[keep]
    dupes = frame["match_id"].duplicated()
    if dupes.any():
        raise DevSlateError(
            "duplicate match_id(s) in the candidate slate — the manifest is "
            f"keyed by it:\n{frame[frame['match_id'].duplicated(keep=False)]}")
    # Chronological, then match_id: same-day fixtures need a tie-break or the
    # order inherits whatever the store handed us. match_id is a content hash
    # of fixture identity — arbitrary, but stable and pre-committed.
    return frame.sort_values(["date", "match_id"], kind="mergesort") \
                .reset_index(drop=True)


def truncate_to_n_dev(ordered: pd.DataFrame, *, admissible, n_dev: int
                      ) -> pd.DataFrame:
    """"...truncated to the first N_dev with admissible coverage."

    ``admissible`` is the set of match_ids with an admissible cut quote (and,
    downstream, a solver success). Refuses rather than returning a short slate:
    the manifest is hash-bound into the V8 lock, so N_dev is a pre-registered
    quantity, never a yield."""
    ids = set(ordered["match_id"])
    stray = sorted(set(admissible) - ids)
    if stray:
        raise DevSlateError(
            f"admissible id(s) {stray} are not in the ordered slate — the "
            "coverage input and the rule disagree about which fixtures exist")
    covered = ordered[ordered["match_id"].isin(set(admissible))]
    if len(covered) < n_dev:
        raise DevSlateError(
            f"only {len(covered)} fixture(s) have admissible coverage but "
            f"N_dev is {n_dev}: truncating short would change a "
            "pre-registered quantity after the fact")
    return covered.head(n_dev).reset_index(drop=True)
