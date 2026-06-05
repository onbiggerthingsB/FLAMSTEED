"""The live operational-leakage gates (Phase-5 §3) — THE load-bearing gate of the
phase + the focal Codex target. The live analog of the Phase-4 close-line leak.

THREE gates:
  * LIVE MIS-LOG CANARY (``assert_entry_logged_at_decision_time``) — the logged
    ENTRY price must equal the snapshot available AT the decision cutoff (the
    EARLIEST snapshot <= kickoff = the price when the signal fired), and must NOT be
    the CLOSE (the kickoff-1min line, info from AFTER the decision) when they differ.
    A mis-log that recorded the close as the entry would FAKE the edge; the canary
    RAISES ``MisLogError``. Realized CLV is defined from the LOGGED entry vs the LATER
    close, so a correct entry is load-bearing for an honest CLV.
  * APPEND-ONLY-LOG IMMUTABILITY (``AppendOnlyLedger``) — a signal once logged cannot
    be silently re-written/re-priced; a second append on the same key RAISES
    ``ImmutableLogError``. Enforcement is by the persisted on-disk records, not a
    convention.
  * REPRODUCIBILITY + FORESIGHT-RED (``assert_live_reproducible`` /
    ``check_live_foresight_red``) — same cutoff+seed -> identical decision;
    ``check_foresight_red`` (REUSED from Phase-4) raises on a too-good live number (a
    suspected feed/logging bug). "Treat any too-good result as a suspected bug."

Foresight-RED is a COARSE backstop for GROSS leaks, NOT proof of cleanliness — the
mis-log canary is the real catch. RED is a halt-and-inspect trip, never a green light.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from wcmodel.backtest.odds_ingest import (
    OUTCOMES, _bookmaker_prices, _parse_ts, _snapshot_has_book, book_aware_close,
)
from wcmodel.backtest.validation import check_foresight_red  # REUSED verbatim (§2.5, §3)
from wcmodel.live.decide import _decision_time_entry  # the SAME entry path decide_live logs


class MisLogError(AssertionError):
    """Raised when a logged entry price is NOT the decision-time snapshot (a mis-log
    — e.g. the close logged as the entry, which would fake the edge)."""


class ImmutableLogError(RuntimeError):
    """Raised on an attempt to re-write/re-price an already-logged signal (the bet log
    is append-only / immutable)."""


def _entry_matches_non_close_le_cutoff_snapshot(
    sample: dict, *, bookmaker: str, cutoff, logged: dict, close_ts: str | None
) -> bool:
    """True iff ``logged`` (the decision's logged entry prices) equals the book prices of
    SOME snapshot that is ``<= cutoff`` AND is NOT the book-aware close snapshot.

    INDEPENDENT of ``_decision_time_entry`` (the function under test): it enumerates the
    candidate snapshots directly from the low-level parse primitives (``_parse_ts`` /
    ``_snapshot_has_book`` / ``_bookmaker_prices``) and compares prices, rather than asking
    ``_decision_time_entry`` which one it would have SELECTED. So a bug IN
    ``_decision_time_entry`` (e.g. selecting the CLOSE as the entry) cannot be reproduced
    here — the close snapshot is excluded by its ``close_ts`` and a logged close price will
    therefore match NO candidate (when the line moved), making this return False -> the
    caller RAISES. An empty ``logged`` (a counted non-bet) is handled by the caller before
    this is reached.
    """
    ct = pd.Timestamp(cutoff)
    if ct.tzinfo is None:
        ct = ct.tz_localize("UTC")
    cutoff_dt = ct.to_pydatetime()
    close_dt = _parse_ts(close_ts) if close_ts is not None else None
    snaps = [
        v for v in sample.values()
        if isinstance(v, dict) and "timestamp" in v and "data" in v
    ]
    for s in snaps:
        ts = _parse_ts(s["timestamp"])
        if ts > cutoff_dt or ts == close_dt:  # not <= cutoff, or IS the book-aware close
            continue
        if not _snapshot_has_book(s, bookmaker):
            continue
        ev = s["data"][0]
        prices = _bookmaker_prices(s, bookmaker, ev["home_team"], ev["away_team"])
        if all(logged.get(o) == prices[o] for o in OUTCOMES):
            return True
    return False


def assert_entry_logged_at_decision_time(decision, sample: dict, *, bookmaker: str) -> None:
    """LIVE MIS-LOG CANARY: the decision's logged ENTRY must be the DECISION-TIME
    snapshot price (the latest snapshot ``<= cutoff`` WITH the book, close-excluded —
    the price transactable AT ``cutoff``), NEVER the close, never re-priced.

    WIRING NOTE (adapted to T3's REAL contract). ``decide_live`` logs the entry via
    ``_decision_time_entry`` = the LATEST snapshot ``<= cutoff`` that contains the book,
    EXCLUDING the kickoff close. The plan's draft canary instead re-derived the entry
    from ``entry_close_prices['entry']`` = the EARLIEST snapshot ``<= kickoff``, which is
    ``cutoff``-UNAWARE: on a 3+-snapshot sample at a late cutoff the two DIVERGE, so that
    draft would (a) false-positive on a correctly-logged decision AND (b) MISS a real
    mis-log that recorded a STALE earliest-``<=``-kickoff price as the entry. This canary
    re-derives the reference through the SAME ``_decision_time_entry`` path keyed off
    ``decision.cutoff`` — so it is an EXACT, non-driftable mirror of what ``decide_live``
    logs (same code path) and cannot be evaded by a stale- or future-priced entry.

    Asserts:
      1. (MIRROR) ``decision.entry_odds`` == the DECISION-TIME (latest ``<= cutoff``,
         book-aware, close-excluded) snapshot price re-derived via the SAME
         ``_decision_time_entry`` path — caught per-outcome (a stale, future, or
         single-leg-swapped entry trips it).
      2. (INDEPENDENT PIN — the FOCAL close-as-entry catch) The logged entry must match
         SOME snapshot that is ``<= cutoff`` AND is NOT the BOOK-AWARE close snapshot
         (the entry is strictly not the close). This check does NOT route through
         ``_decision_time_entry``, so it catches a bug IN ``_decision_time_entry`` (e.g. a
         regression that selects the CLOSE as the entry) instead of blindly mirroring it.
    Raises ``MisLogError`` on either violation. The non-vacuity teeth (a sabotaged
    close-as-entry decision DOES raise) live in the calling test.

    WHY THE INDEPENDENT PIN (the FOCAL constructed miss). The mirror in (1) re-derives the
    reference through the SAME function ``decide_live`` uses; a bug in that function (e.g.
    when the missing-earliest-book case made ``close_ts`` None and the close was wrongly
    selected as the entry) is REPRODUCED by the mirror, so a pure mirror would PASS the
    leak. (2) derives the close BOOK-AWARE (``book_aware_close``, independent of the
    crashing earliest-entry leg) and asserts the logged entry is a genuine ``<= cutoff``
    non-close price — so even if (1) regressed in lockstep, (2) RAISES.
    """
    # The BOOK-AWARE close (CLV-only) + its timestamp, derived INDEPENDENTLY of the
    # earliest-entry leg (which raises on a missing-earliest-book). This is the close to
    # EXCLUDE from the entry candidates — and the reference the independent pin uses.
    bac = book_aware_close(sample, bookmaker=bookmaker)
    if bac is not None:
        close, close_ts = bac["close"], bac["close_ts"]
    else:
        close, close_ts = {}, None
    # (1) MIRROR: the decision-time entry via the SAME selection decide_live uses (latest
    # <= cutoff WITH the book, close-excluded). Keyed off the decision's OWN logged cutoff.
    entry, _entry_ts = _decision_time_entry(
        sample, bookmaker=bookmaker, cutoff=decision.cutoff, close_ts=close_ts,
    )
    if entry is None:
        # decide_live logs an EMPTY entry as a counted non-bet when no <= cutoff snapshot
        # has the book; a non-empty logged entry then is itself a mis-log (a price that
        # could not have been transacted at the cutoff).
        if decision.entry_odds:
            raise MisLogError(
                "live mis-log: a non-empty entry was logged though NO snapshot <= cutoff "
                f"{decision.cutoff!r} contains the book {bookmaker!r} — the logged entry "
                "could not have been transacted at the decision time. STOP and investigate."
            )
        return
    # (1) the logged entry IS the decision-time entry snapshot (per-outcome teeth).
    for o in OUTCOMES:
        if decision.entry_odds.get(o) != entry[o]:
            raise MisLogError(
                f"live mis-log: logged entry {decision.entry_odds.get(o)!r} for {o!r} "
                f"!= the decision-time (latest <= cutoff) snapshot price {entry[o]!r} — "
                "the entry must be the price available AT the decision cutoff, never "
                "re-priced, never a stale or post-cutoff snapshot"
            )
    # (2) INDEPENDENT PIN (does NOT route through _decision_time_entry): the logged entry
    # must be (a) <= cutoff AND (b) strictly NOT the BOOK-AWARE close snapshot. We match the
    # logged prices directly against the prices of the <= cutoff snapshots WITH the book,
    # EXCLUDING the book-aware close snapshot (by its timestamp). If the logged entry equals
    # NO such non-close <= cutoff snapshot — in particular if it equals ONLY the close (the
    # focal close-as-entry mis-log, which the mirror in (1) would reproduce and miss) — RAISE.
    if not _entry_matches_non_close_le_cutoff_snapshot(
        sample, bookmaker=bookmaker, cutoff=decision.cutoff,
        logged=decision.entry_odds, close_ts=close_ts,
    ):
        if close and decision.entry_odds == close:
            raise MisLogError(
                "live mis-log: logged entry equals the CLOSE — the close is information "
                "from AFTER the entry decision (kickoff-1min); logging it as the entry "
                "fakes the edge. STOP and investigate (the focal operational-leakage gate)."
            )
        raise MisLogError(
            "live mis-log: logged entry matches NO <= cutoff "
            f"{decision.cutoff!r} snapshot (close-excluded) for book {bookmaker!r} — the "
            "entry must be a price transactable AT the decision cutoff and never the close. "
            "STOP and investigate."
        )


class AppendOnlyLedger:
    """An append-only / immutable paper bet-log (JSONL on disk).

    Each record is keyed by ``(event_key, staked)`` (a signal on a side of an event).
    ``append`` REFUSES (raises ``ImmutableLogError``) a second record on an existing
    key — a logged signal can never be silently re-written or re-priced. Enforcement
    is the persisted on-disk records (re-loaded on construction), not memory.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._keys = {self._key(r) for r in self.records()}

    @staticmethod
    def _key(rec: dict) -> tuple:
        return (tuple(rec.get("event_key", [])), rec.get("staked", ""))

    def records(self) -> list[dict]:
        if not self._path.exists():
            return []
        return [json.loads(line) for line in self._path.read_text().splitlines() if line.strip()]

    def append(self, rec: dict) -> None:
        key = self._key(rec)
        if key in self._keys:
            raise ImmutableLogError(
                f"signal {key!r} is already logged — the bet log is append-only / "
                "immutable; a logged entry can never be silently re-written or re-priced. "
                "STOP (a re-write attempt is a suspected mis-log)."
            )
        with self._path.open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        self._keys.add(key)


def check_live_foresight_red(summary: dict, *, config: dict | None = None) -> None:
    """REUSE the Phase-4 foresight-RED hard-STOP on the live tracker (§2.5, §3).

    A suspiciously-good live CLV/ROI => SUSPECTED feed/logging bug => raise (STOP, do
    not celebrate). Delegates to the Phase-4 ``check_foresight_red`` so the live and
    backtest gates share one ceiling set + one implementation.
    """
    check_foresight_red(summary, config=config)


def assert_live_reproducible(run_fn) -> None:
    """Reproducibility gate: ``run_fn()`` (a seeded ``decide_live`` call) twice must
    yield bit-identical decisions. Raises ``AssertionError`` otherwise."""
    a = run_fn()
    b = run_fn()
    assert a.to_dict() == b.to_dict(), (
        "live decision is NOT reproducible at the same cutoff+seed -> a non-seeded "
        "path leaked in. STOP and investigate (provenance must be auditable)."
    )
