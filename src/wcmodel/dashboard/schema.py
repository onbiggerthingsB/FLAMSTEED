"""Serializer-side guards: the data-layer enforcement of the spec's no-naked-numbers,
coherence, coverage-gap, and no-imputation discipline. An artifact that violates these
must not be written (build.py gates on them)."""
from __future__ import annotations

import math

# The cumulative knockout ladder, shallow -> deep. Each must be >= the next.
_LADDER = ["advance_from_group", "reach_qf", "reach_sf", "reach_final", "champion"]


def validate_progression_coherence(markets: dict, *, tol: float = 1e-9) -> None:
    """Raise if the cumulative ladder is non-monotone (deeper stage more likely than a
    shallower one is impossible). Only checks the markets present."""
    present = [m for m in _LADDER if m in markets]
    for shallower, deeper in zip(present, present[1:]):
        if markets[deeper] > markets[shallower] + tol:
            raise ValueError(
                f"progression coherence violated: {deeper}={markets[deeper]} > "
                f"{shallower}={markets[shallower]} (a deeper stage cannot exceed a shallower one)"
            )


def assert_uncertainty_companion(node: dict) -> None:
    """Every emitted probability must carry an uncertainty companion — an ``se`` (MC SE)
    or a ``ci`` interval. A bare ``{"value": p}`` is a naked number and is rejected."""
    if "value" not in node:
        return
    if node.get("se") is None and node.get("ci") is None:
        raise ValueError(
            f"naked number: {node!r} has a value but no uncertainty companion (se or ci) "
            "— the no-naked-numbers rule applies at the source"
        )


def coverage_gap(reason: str) -> dict:
    """An explicit coverage gap (thin/absent data) — NEVER a fabricated number."""
    return {"coverage_gap": True, "reason": reason, "value": None}


def no_impute(x):
    """NULL-safe: a NaN/None becomes JSON ``null``, never 0 (no imputation, ever)."""
    if x is None:
        return None
    try:
        return None if math.isnan(float(x)) else float(x)
    except (TypeError, ValueError):
        return None
