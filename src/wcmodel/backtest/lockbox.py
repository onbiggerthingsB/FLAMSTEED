"""The single-use lockbox as a MECHANISM, not an adjective (spec §2.7).

A committed pre-registration registry (``config/lockbox.json``) is pinned BEFORE
any tuning/evaluation logic. It records the held-out boundary as a FROZEN rule
(the final 18% BY DATE of the odds-covered ``backtest_window`` universe), the
pre-registered config budget (the 9 DOF), and a single-use ``used`` flag.

``LockboxRegistry`` loads that registry, exposes the frozen boundary + config
count, and on a REAL lockbox evaluation flips ``used -> true`` ON DISK and
PHYSICALLY REFUSES (raises ``LockboxUsedError``) any second evaluation — even in a
fresh process / re-loaded registry. Enforcement is persisted disk state, NOT a
comment/convention: a sabotaged in-memory-only flag would let a 2nd eval through,
which the single-use test catches.

``resolved_cutoff_date`` is written ONCE, immutably, the first time the real
odds-covered universe is materialized (``resolve_cutoff``); until then the registry
holds the rule + ``resolved: false`` (D1: the real pull is gated).
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path

#: The committed, pre-registered registry. Pinned before any tuning code runs.
REGISTRY_PATH = Path(__file__).resolve().parents[3] / "config" / "lockbox.json"


class LockboxUsedError(RuntimeError):
    """Raised when a SECOND lockbox evaluation is attempted (single-use is spent)."""


class LockboxResolvedError(RuntimeError):
    """Raised on an attempt to re-resolve an already-frozen lockbox cutoff date."""


class LockboxBusyError(RuntimeError):
    """Raised when another process holds the registry lock (a concurrent claim is
    in flight). The single-use critical section is interprocess-exclusive."""


class LockboxRegistry:
    """Single-use lockbox registry, single-use ENFORCED by persisted disk state."""

    def __init__(self, data: dict, *, path: Path):
        self._data = data
        self._path = path

    # ---- loading -----------------------------------------------------------
    @classmethod
    def load(cls, *, path: Path | str | None = None) -> "LockboxRegistry":
        """Load the registry from ``path`` (defaults to the committed REGISTRY_PATH)."""
        p = Path(path) if path is not None else REGISTRY_PATH
        return cls(json.loads(p.read_text()), path=p)

    def _flush(self) -> None:
        """Persist the registry to disk (atomic-ish: write then replace)."""
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2) + "\n")
        tmp.replace(self._path)

    def _reload(self) -> None:
        """Re-read the on-disk registry into ``self._data``.

        Called before the single-use / write-once guards so a STALE in-memory
        object (loaded while ``used``/``resolved`` was false, then another process
        burned/resolved the registry on disk) cannot slip a second evaluation or a
        cutoff overwrite past a cached check. The guarantee is the CURRENT disk
        state at the moment of the guard, not the state captured at ``load`` time.
        """
        self._data = json.loads(self._path.read_text())

    @contextlib.contextmanager
    def _claim_lock(self):
        """Interprocess-exclusive lock around the WHOLE reload→guard→burn→flush
        critical section, so the check-and-burn is ATOMIC across concurrent
        processes (not just sequential re-loads).

        Uses ``O_CREAT | O_EXCL`` on a sibling ``.lock`` file: POSIX guarantees
        exactly ONE creator wins the race; every other concurrent claimant gets
        ``FileExistsError`` and is refused with ``LockboxBusyError``. Without this,
        two processes could both ``_reload()`` and observe ``used=false`` before
        either ``_flush()`` lands — and both would burn the single shot. The lock is
        always released in ``finally`` (a crash leaves the burned ``used=true`` on
        disk, fail-closed, and at most a stale lockfile — never a second live eval).
        """
        lock_path = self._path.with_suffix(".lock")
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as exc:
            raise LockboxBusyError(
                f"another process holds the lockbox lock ({lock_path.name}); the "
                "single-use critical section is interprocess-exclusive. Retry once the "
                "in-flight evaluation completes (or remove a stale lockfile after a crash)."
            ) from exc
        try:
            os.write(fd, str(time.time()).encode())
            os.close(fd)
            yield
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(str(lock_path))

    # ---- frozen, pre-registered fields ------------------------------------
    @property
    def lockbox_fraction(self) -> float:
        return self._data["lockbox_fraction"]

    @property
    def boundary_rule(self) -> str:
        return self._data["boundary_rule"]

    @property
    def preregistered_config_count(self) -> int:
        return self._data["preregistered_config_count"]

    @property
    def preregistered_dof(self) -> list[str]:
        return list(self._data["preregistered_dof"])

    @property
    def resolved(self) -> bool:
        return bool(self._data["resolved"])

    @property
    def resolved_cutoff_date(self):
        return self._data["resolved_cutoff_date"]

    @property
    def used(self) -> bool:
        return bool(self._data["used"])

    # ---- the held-out boundary (write-once) -------------------------------
    def resolve_cutoff(self, cutoff_date: str) -> None:
        """Freeze the held-out boundary date ONCE, the first time the real universe
        is materialized. Refuses to overwrite an already-resolved cutoff (immutable
        once written) — the boundary is a committed artifact, not a moving target.

        The on-disk ``resolved`` flag is RE-READ before the guard under the same
        interprocess lock as the single-use burn, so neither a stale object nor two
        CONCURRENT processes can overwrite the frozen cutoff date (atomic
        check-and-write)."""
        with self._claim_lock():
            self._reload()                          # current disk state, not stale cache
            if self._data["resolved"]:
                raise LockboxResolvedError(
                    f"lockbox cutoff already frozen at {self._data['resolved_cutoff_date']!r} "
                    "— the held-out boundary is write-once and immutable."
                )
            self._data["resolved"] = True
            self._data["resolved_cutoff_date"] = str(cutoff_date)
            self._flush()

    # ---- the single-use evaluation (single-use ENFORCED ON DISK) ----------
    def evaluate_on_lockbox(self, eval_fn) -> dict:
        """Run the ONE permitted lockbox evaluation, then BURN the flag on disk.

        If ``used`` is already true (in this object OR persisted from a prior
        process), PHYSICALLY REFUSE: raise ``LockboxUsedError``. The flip to
        ``used=true`` is flushed to disk BEFORE returning, so a crash mid-eval still
        spends the shot (fail-closed) and no second run can ever slip through.

        The on-disk flag is RE-READ immediately before the guard, so even a stale
        registry object (loaded while ``used=false``, then burned by another
        process) is refused — the single-use guarantee is the CURRENT disk state,
        not a value cached at ``load`` time.

        The whole reload→guard→burn→flush→run is held under an interprocess lock
        (``_claim_lock``), so two CONCURRENT processes cannot both observe
        ``used=false`` before one of them flushes — the check-and-burn is atomic.
        """
        with self._claim_lock():
            self._reload()                          # current disk state, not stale cache
            if self.used:
                raise LockboxUsedError(
                    "the single-use lockbox has already been evaluated (used=true on disk) "
                    "— a second evaluation is REFUSED. Re-tuning against the lockbox would "
                    "destroy its purpose. STOP."
                )
            self._data["used"] = True
            self._flush()                           # burn the shot ON DISK first (fail-closed)
            return eval_fn()
