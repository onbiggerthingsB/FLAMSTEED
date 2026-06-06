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


def _finite_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def assert_uncertainty_companion(node: dict) -> None:
    """Every emitted probability must carry a REAL uncertainty companion — a finite ``se``
    (an MC SE; 0.0 is valid for a certain p in {0,1}) or a ``ci`` of two finite bounds.
    A missing OR degenerate (NaN/inf/empty/wrong-length) companion is a naked number."""
    if "value" not in node:
        return
    se, ci = node.get("se"), node.get("ci")
    se_ok = _finite_number(se)
    ci_ok = (isinstance(ci, (list, tuple)) and len(ci) == 2
             and all(_finite_number(b) for b in ci))
    if not (se_ok or ci_ok):
        raise ValueError(
            f"naked number: {node!r} has a value but no REAL uncertainty companion "
            "(need a finite se or a 2-bound finite ci) — the no-naked-numbers rule applies"
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
