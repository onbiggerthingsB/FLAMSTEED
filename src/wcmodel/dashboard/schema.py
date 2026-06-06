"""Serializer-side guards: the data-layer enforcement of the spec's no-naked-numbers,
coherence, coverage-gap, and no-imputation discipline. An artifact that violates these
must not be written (build.py gates on them)."""
from __future__ import annotations

import math

# The cumulative knockout ladder, shallow -> deep. Each must be >= the next. Mirrors the
# sim's documented cumulative ladder champion <= reach_final <= reach_sf <= reach_qf <=
# reach_r16 <= advance_from_group, so EVERY rung team_progression emits is gated here
# (reach_r16 included — omitting it silently skipped a real coherence rung).
_LADDER = ["advance_from_group", "reach_r16", "reach_qf", "reach_sf", "reach_final", "champion"]


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
    # An explicit null value is NOT a naked number. A legitimate coverage_gap ALWAYS
    # carries value=None, so the null-value exemption covers it. We deliberately do NOT
    # exempt on the coverage_gap flag alone: a contradictory {coverage_gap: True, value: 0.1}
    # carries a real number that must still be companion-checked (it would otherwise slip).
    if "value" not in node:
        return
    if node.get("value") is None:
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


def gate_fixture_forecast(f: dict, *, tol: float = 0.05) -> None:
    """A fixture forecast's uncertainty IS its scoreline distribution: the full grid must be
    present and sum to ~1, the most-likely score must carry its prob, and the 1X2 must show
    ALL THREE outcomes (never a lone score). (No per-outcome CI — the distribution is the
    uncertainty, per the approved design.)"""
    grid = f.get("grid")
    if not grid or not all(isinstance(row, (list, tuple)) and row for row in grid):
        raise ValueError("fixture forecast: grid must be a non-empty list of non-empty rows")
    width = len(grid[0])
    if not all(len(row) == width for row in grid):
        raise ValueError("fixture forecast: grid must be rectangular (all rows equal length)")
    if not all(_finite_number(c) for row in grid for c in row):
        raise ValueError("fixture forecast: every grid cell must be a finite number")
    total = sum(sum(row) for row in grid)
    if abs(total - 1.0) > tol:
        raise ValueError("fixture forecast: grid does not sum to ~1 (the scoreline distribution is the uncertainty)")
    ml = f.get("most_likely") or {}
    if "prob" not in ml:
        raise ValueError("fixture forecast: most_likely score is naked (no prob)")
    oxt = f.get("one_x_two") or {}
    if not all(k in oxt for k in ("home", "draw", "away")):
        raise ValueError("fixture forecast: 1x2 must show all three outcomes, never a lone score")


def gate_track(t: dict) -> None:
    """Track-record metrics must be finite numbers or explicit null/coverage_gap — never a
    NaN/inf token (the JSON gate uses allow_nan=False; a NaN must be sanitized to null first)."""
    def _check(x):
        if isinstance(x, dict):
            if x.get("coverage_gap"):
                return
            for v in x.values():
                _check(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                _check(v)
        elif isinstance(x, float) and not math.isfinite(x):
            raise ValueError(f"track metric is not finite ({x!r}) — sanitize NaN/inf to null first")
    _check(t)
