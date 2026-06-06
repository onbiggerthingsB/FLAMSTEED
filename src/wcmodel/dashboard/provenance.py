"""The provenance envelope wrapped around every dashboard artifact."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from wcmodel.dashboard import DRY_RUN_BANNER


def _git_rev() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:                      # detached / no-git env -> explicit sentinel
        return "unknown"


@dataclass(frozen=True)
class Provenance:
    """As-of identity for one snapshot. ``cutoff`` is the leakage boundary; ``posterior_key``
    is the content-addressed cached_fit key; ``is_synthetic`` taints the whole bundle."""
    cutoff: str
    posterior_key: str
    git: str
    is_synthetic: bool
    n_sims: int

    def to_dict(self) -> dict:
        return {
            "as_of": self.cutoff,
            "posterior_key": self.posterior_key,
            "git": self.git,
            "is_synthetic": bool(self.is_synthetic),
            "n_sims": int(self.n_sims),
            "banner": DRY_RUN_BANNER if self.is_synthetic else None,
        }


def stamp(payload: dict, provenance: Provenance) -> dict:
    """Wrap an artifact payload in its provenance envelope: ``{provenance, data}``."""
    return {"provenance": provenance.to_dict(), "data": payload}
