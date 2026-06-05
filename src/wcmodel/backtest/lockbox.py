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

import json
from pathlib import Path

#: The committed, pre-registered registry. Pinned before any tuning code runs.
REGISTRY_PATH = Path(__file__).resolve().parents[3] / "config" / "lockbox.json"


class LockboxUsedError(RuntimeError):
    """Raised when a SECOND lockbox evaluation is attempted (single-use is spent)."""


class LockboxResolvedError(RuntimeError):
    """Raised on an attempt to re-resolve an already-frozen lockbox cutoff date."""


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
        once written) — the boundary is a committed artifact, not a moving target."""
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
        """
        if self.used:
            raise LockboxUsedError(
                "the single-use lockbox has already been evaluated (used=true on disk) "
                "— a second evaluation is REFUSED. Re-tuning against the lockbox would "
                "destroy its purpose. STOP."
            )
        self._data["used"] = True
        self._flush()                               # burn the shot ON DISK first (fail-closed)
        return eval_fn()
