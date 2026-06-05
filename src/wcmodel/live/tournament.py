"""Tiny live-layer helper re-exports. The live loop settles a played result into a
1X2 outcome using the SAME rule the Phase-4 engine uses (``_settle_outcome``); this
module re-exports it under ``_settle`` so the live e2e + the CLI share one settler and
never re-derive the home/away/draw rule."""
from __future__ import annotations

from wcmodel.backtest.walkforward import _settle_outcome as _settle  # noqa: F401
