"""ACCEPTANCE 1 (matrix ORIENTATION, verified at the layer where the FULL grid exists) +
ACCEPTANCE 2/3 over the REAL build output.

The spec's HARD REQUIREMENT: do NOT assume grid orientation from variable names. Recompute
H/D/A from the SAME matrix and match the ``one_x_two`` the build already emits, per fixture —
AND, because the staged production bundle's per-fixture JSON carries the FULL scoreline grid
(verified: all 72 group fixtures ship an 11×11 grid summing to 1), verify orientation against
the staged bundle's displayed one_x_two too (read-only).

We recompute with the IDENTICAL convention ``Posterior.predict_1x2`` documents:
    home = Σ grid[h,a] over h>a  (lower triangle, np.tril(g,-1))
    draw = Σ grid[h,a] over h==a (diagonal,        np.trace(g))
    away = Σ grid[h,a] over h<a  (upper triangle,  np.triu(g,1))
If this matches the emitted one_x_two for EVERY fixture, rows=home / cols=away is confirmed —
which is exactly the orientation ``cover_line`` (h−a>=2) relies on.

This test reads the staged PRODUCTION bundle READ-ONLY (never writes, never fits/sims). If the
staged bundle is absent (a fresh checkout), it skips — the construction-level orientation proof
lives in ``test_spread.py`` (cover_line over hand grids) and the build-wiring test in
``test_spread.test_fixture_forecast_carries_cover_consistent_with_its_grid``.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from wcmodel.dashboard.spread import cover_line

# The staged production bundle the dashboard reads (read-only per the controller's instruction).
_BUNDLE = Path(__file__).resolve().parents[2] / "dashboard-ui" / "public" / "bundle"
_FIXTURES_DIR = _BUNDLE / "fixtures"


def _load_fixture_grids():
    """Every staged group fixture that carries a FULL (square, sum~1) grid + its one_x_two."""
    if not _FIXTURES_DIR.is_dir():
        return []
    out = []
    for fp in sorted(_FIXTURES_DIR.glob("*.json")):
        data = json.loads(fp.read_text())["data"]
        fc = data.get("forecast") or {}
        grid = fc.get("grid")
        oxt = fc.get("one_x_two")
        if not grid or not oxt:
            continue
        g = np.asarray(grid, dtype=float)
        if g.ndim == 2 and g.shape[0] == g.shape[1] and abs(g.sum() - 1.0) < 1e-6:
            out.append((fp.name, g, oxt))
    return out


_GRIDS = _load_fixture_grids()
_skip_no_bundle = pytest.mark.skipif(
    not _GRIDS, reason="staged production bundle not present (read-only orientation check skipped)"
)


@_skip_no_bundle
def test_staged_bundle_has_all_72_full_grids():
    """The staged bundle's per-fixture JSON carries the FULL scoreline grid (NOT a truncated
    top-K) — so orientation IS verifiable against the displayed one_x_two read-only. Records
    the count the controller needs (72 group fixtures, all full)."""
    assert len(_GRIDS) == 72, f"expected 72 full-grid group fixtures, got {len(_GRIDS)}"


@_skip_no_bundle
def test_orientation_recomputed_1x2_matches_displayed_for_every_fixture():
    """ACCEPTANCE 1: recompute H/D/A from each grid (rows=home / cols=away convention) and
    match the one_x_two the build emitted, for EVERY one of the 72 staged fixtures. A match
    proves the orientation cover_line relies on; a mismatch (a transposed grid) would surface
    here as home/away swapped."""
    for name, g, oxt in _GRIDS:
        home = float(np.tril(g, -1).sum())
        draw = float(np.trace(g))
        away = float(np.triu(g, 1).sum())
        assert home == pytest.approx(oxt["home"], abs=1e-9), f"{name}: home mismatch (transposed grid?)"
        assert draw == pytest.approx(oxt["draw"], abs=1e-9), f"{name}: draw mismatch"
        assert away == pytest.approx(oxt["away"], abs=1e-9), f"{name}: away mismatch (transposed grid?)"


@_skip_no_bundle
def test_cover_pair_sums_to_one_and_is_strict_subset_of_home_win_for_every_fixture():
    """ACCEPTANCE 2 + 3 over the REAL build output: for every staged fixture the cover pair
    sums to ~1 and P(home −1.5) < P(home win)."""
    for name, g, oxt in _GRIDS:
        cov = cover_line(g)
        assert cov["home"] + cov["away"] == pytest.approx(1.0, abs=1e-12), f"{name}: cover pair !sum 1"
        assert cov["home"] < oxt["home"] + 1e-12, f"{name}: home cover not a subset of home win"
        # Strict where the margin==1 band carries mass (true for every real WC fixture).
        if oxt["home"] > 1e-6:
            assert cov["home"] < oxt["home"], f"{name}: home cover not STRICTLY < home win"


@_skip_no_bundle
def test_staged_displayed_one_x_two_is_self_consistent_with_cover_orientation():
    """Belt-and-suspenders: the cover computed from the staged grid is internally consistent
    with the displayed home-win (P(home −1.5) <= P(home win), both off the SAME grid). This is
    the read-only orientation cross-check the spec asks for against the staged bundle."""
    for name, g, oxt in _GRIDS:
        p_home_cover = cover_line(g)["home"]
        # Home covers −1.5 ⊆ home wins → never exceeds the displayed home-win probability.
        assert p_home_cover <= oxt["home"] + 1e-12, f"{name}: cover exceeds displayed home win"
