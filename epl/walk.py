"""The single implementation of the point-in-time cutoff.

Every walk-forward object in this package — the Elo ratings, the ordered-logit
head, the base rate — reads history through :func:`blocks`. One implementation,
so there is one place to get the cutoff wrong rather than three, and one place
a leakage test has to attack.

THE RULE, restated from :data:`epl.schema.ORDERING_RULE`. A forecast for match
M may use only matches strictly earlier than M:

    kickoff known for both  ->  earlier iff kickoff < M.kickoff
    kickoff missing         ->  earlier iff date < M.date

A BLOCK is a maximal set of matches that share a cutoff key and therefore may
not inform one another; blocks are totally ordered, and a match may use every
match in every strictly earlier block and nothing else. The cutoff key is the
kickoff where one exists and the date at midnight where none does.

Collapsing the two-clause rule onto that single key is exact ONLY while no
calendar date carries both a timed and an untimed match — otherwise the untimed
row's midnight key would sort before the timed row's kickoff and be treated as
usable, when the rule's second clause says it is not. That precondition is
CHECKED (:func:`cutoff_keys`), not assumed: it holds in the 2014/15-2025/26
archive because the source's ``Time`` column is present for whole seasons at a
time, but a future season delivered half-timed would silently start leaking
same-day results into earlier kickoffs, and this is where that would be caught.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["cutoff_keys", "blocks", "block_index", "groups"]


def cutoff_keys(df: pd.DataFrame) -> pd.Series:
    """Per-row cutoff key: the kickoff where known, else the date at midnight.

    Raises if any single date carries both a timed and an untimed match, which
    is the one configuration under which a single key cannot express the rule.
    """
    if "kickoff" not in df.columns or "date" not in df.columns:
        raise ValueError("need `kickoff` and `date` columns; got "
                         f"{list(df.columns)[:12]}")
    date = pd.to_datetime(df["date"]).dt.normalize()
    kickoff = pd.to_datetime(df["kickoff"])
    timed = kickoff.notna()
    mixed = date[timed].unique()
    clash = np.intersect1d(mixed, date[~timed].unique())
    if clash.size:
        raise ValueError(
            f"{clash.size} date(s) carry both timed and untimed matches "
            f"(e.g. {pd.Timestamp(clash[0]).date()}): a single cutoff key "
            "cannot express ORDERING_RULE there, because the untimed row's "
            "midnight key sorts before a same-day kickoff while the rule says "
            "it may not inform it. Split the walk by timed/untimed instead.")
    return kickoff.where(timed, date)


def block_index(df: pd.DataFrame) -> np.ndarray:
    """Dense 0-based block id per row, ascending in time.

    Rows sharing an id are simultaneous under the rule. ``df`` must already be
    in chronological order (:func:`epl.schema.sort_for_walk_forward`); that is
    checked, because a mis-sorted frame would produce non-monotone ids and
    every downstream "strictly earlier" test would quietly compare the wrong
    rows.
    """
    keys = cutoff_keys(df).to_numpy("datetime64[ns]")
    if keys.size and (np.diff(keys) < np.timedelta64(0, "ns")).any():
        raise ValueError("frame is not in chronological order — call "
                         "epl.schema.sort_for_walk_forward first")
    # A new block starts wherever the key changes.
    starts = np.empty(keys.size, dtype=bool)
    starts[:1] = True
    starts[1:] = keys[1:] != keys[:-1]
    return np.cumsum(starts) - 1


def groups(ids: np.ndarray) -> list[np.ndarray]:
    """Split positional indices by an already-computed, non-decreasing block id.

    The consumers of a walk (the ordered-logit head, the base rate) receive a
    frame derived from the matches, not the matches themselves, so they carry
    the block id rather than re-deriving it from columns they no longer have.
    Re-deriving it in three places is how three walks end up disagreeing about
    what "earlier" means.

    Because blocks are contiguous in a chronologically sorted frame, block
    ``i``'s usable past is exactly rows ``[0, rows[0])`` — which is what makes
    "the head cannot address its own rows" a statement about slicing rather
    than a claim about care.
    """
    ids = np.asarray(ids)
    if ids.size == 0:
        return []
    if (np.diff(ids) < 0).any():
        raise ValueError("block ids must be non-decreasing — the frame is not "
                         "in chronological order")
    return np.split(np.arange(ids.size), np.flatnonzero(np.diff(ids)) + 1)


def blocks(df: pd.DataFrame) -> list[np.ndarray]:
    """Positional row indices grouped into blocks, ascending in time.

    ``for i, rows in enumerate(blocks(df))`` walks history forward: at step
    ``i`` the usable past is exactly the union of blocks ``0..i-1``, and
    ``rows`` is what may be predicted next and then learned from.
    """
    return groups(block_index(df))
