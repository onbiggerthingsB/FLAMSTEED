"""±1.5 goal-line cover probabilities, derived purely from the scoreline grid (spec §10:
Derived from the grid, no model/odds). Mirrors the discipline of ``markets/derived.py``'s
``totals_probs`` — the function takes ONLY the grid, so it is trivially testable against
hand-computed grids.

ACCEPTANCE (this file owns items 2, 3-construction, and 4; item 1 — orientation over the
real build output — lives in ``test_spread_orientation.py`` over the staged bundle's 72
full grids):

  2. cover pair sums to exactly 1.0 by construction (tested over real-shaped grids).
  3. P(home −1.5) < P(home win) strictly (a strict subset: h−a>=2 ⊂ h−a>=1).
  4. sanity cell: independent Poisson λ_home=1.5, λ_away=1.0 at the pipeline grid size
     (max_goals=10 → 11×11) yields ≈0.246 / ≈0.754.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import poisson

from wcmodel.dashboard.spread import cover_line


def _indep_poisson_grid(lh: float, la: float, n: int) -> np.ndarray:
    """An independent-Poisson scoreline grid g[h, a] = P(H=h)P(A=a), renormalised over the
    truncated n×n support — the SAME orientation (rows=home, cols=away) the pipeline's
    predict_scoreline emits, so the cover math is exercised against the production orientation."""
    g = poisson.pmf(np.arange(n), lh)[:, None] * poisson.pmf(np.arange(n), la)[None, :]
    return g / g.sum()


def test_cover_line_hand_grid_matches_h_minus_a_ge_2():
    # A tiny exact grid: home covers −1.5 iff home wins by >=2. Cells:
    #   (h=2,a=0)=0.3  -> margin +2  -> COVERS
    #   (h=3,a=1)=0.2  -> margin +2  -> COVERS
    #   (h=1,a=0)=0.4  -> margin +1  -> does NOT cover (home wins, but not by 2)
    #   (h=0,a=0)=0.1  -> draw       -> does NOT cover
    g = np.zeros((4, 4))
    g[2, 0], g[3, 1], g[1, 0], g[0, 0] = 0.3, 0.2, 0.4, 0.1
    out = cover_line(g)
    assert out["home"] == pytest.approx(0.5)          # 0.3 + 0.2
    assert out["away"] == pytest.approx(0.5)          # 1 − 0.5  (half line: no push)


def test_cover_pair_sums_to_one_exactly_over_real_shaped_grids():
    """ACCEPTANCE 2: home covers −1.5 + away covers +1.5 == 1 EXACTLY by construction
    (a half-goal line has no push; away covers iff home does NOT cover −1.5). Tested over
    several independent-Poisson grids at the pipeline 11×11 size."""
    n = 11
    for lh, la in [(1.5, 1.0), (0.8, 2.1), (2.4, 2.4), (0.3, 0.3), (3.1, 0.5)]:
        out = cover_line(_indep_poisson_grid(lh, la, n))
        assert out["home"] + out["away"] == pytest.approx(1.0, abs=1e-12)


def test_home_cover_is_strict_subset_of_home_win():
    """ACCEPTANCE 3: P(home −1.5) < P(home win) for every (non-degenerate) match — covering
    −1.5 (h−a>=2) is a STRICT subset of winning (h−a>=1); the h−a==1 cells carry real mass."""
    n = 11
    for lh, la in [(1.5, 1.0), (0.8, 2.1), (2.4, 2.4), (0.3, 0.3), (3.1, 0.5), (1.2, 1.2)]:
        g = _indep_poisson_grid(lh, la, n)
        home_win = float(np.tril(g, -1).sum())        # h > a  (same as predict_1x2)
        p_cover = cover_line(g)["home"]
        assert p_cover < home_win                     # strict: the margin==1 band has mass


def test_sanity_cell_indep_poisson_1p5_1p0():
    """ACCEPTANCE 4: independent Poisson λ_home=1.5, λ_away=1.0 at the pipeline grid size
    (max_goals=10 → 11×11) yields ≈24.6% home / ≈75.4% away.

    EXACT computed value at n=11 (renormalised truncated support): home=0.246272,
    away=0.753728. The truncation/renorm shifts the n→∞ value (0.246273) by <1e-6, so a tol
    of 5e-3 around 0.246 is generous yet unambiguous: it excludes any orientation/off-by-one
    error, which would land near 0.754 or produce a wildly different number."""
    g = _indep_poisson_grid(1.5, 1.0, 11)
    out = cover_line(g)
    # State the exact computed value so the controller can see it pinned.
    assert out["home"] == pytest.approx(0.246272, abs=5e-3)
    assert out["away"] == pytest.approx(0.753728, abs=5e-3)
    assert out["home"] + out["away"] == pytest.approx(1.0, abs=1e-12)


def test_fixture_forecast_carries_cover_consistent_with_its_grid():
    """The build layer (``fixture_forecast``) ships a ``cover`` pair Derived from the SAME grid
    it emits. The cover recomputed from the forecast's own grid must equal the shipped cover,
    and (ACCEPTANCE 3 at the build layer) P(home −1.5) < the forecast's home-win 1X2."""
    from wcmodel.dashboard.fixtures import fixture_forecast
    from tests.dashboard.test_fixtures import _FakePost

    f = fixture_forecast(_FakePost(), home="Spain", away="Morocco", neutral=True, max_goals=3)
    assert "cover" in f and set(f["cover"]) == {"home", "away"}
    recomputed = cover_line(np.asarray(f["grid"]))
    assert f["cover"]["home"] == pytest.approx(recomputed["home"])
    assert f["cover"]["away"] == pytest.approx(recomputed["away"])
    assert f["cover"]["home"] + f["cover"]["away"] == pytest.approx(1.0, abs=1e-12)
    # Strict subset of the home-win 1X2 (the _FakePost grid has a margin==1 cell: (1,0)=0.5).
    assert f["cover"]["home"] < f["one_x_two"]["home"]


def test_forecast_summary_projects_cover_into_the_row():
    """The schedule-ROW projection (``_forecast_summary``) carries the SAME cover pair the full
    fixture forecast computed — a pure projection, never recomputed (spec §10 provenance)."""
    from wcmodel.dashboard.fixtures import fixture_forecast
    from wcmodel.dashboard.build import _forecast_summary
    from tests.dashboard.test_fixtures import _FakePost

    f = fixture_forecast(_FakePost(), home="Spain", away="Morocco", neutral=True, max_goals=3)
    summary = _forecast_summary(f, {"coverage_gap": True, "reason": "x"})
    assert summary["cover"] == f["cover"]


def test_cover_line_rejects_non_square_or_broken_grid():
    """A non-square / non-finite / empty grid is a broken predictive → raise (never fabricate
    a price), mirroring totals_probs' guard."""
    with pytest.raises(ValueError):
        cover_line(np.zeros((3, 4)))                  # non-square
    with pytest.raises(ValueError):
        cover_line(np.zeros((4, 4)))                  # empty mass (sum 0)
    with pytest.raises(ValueError):
        bad = np.zeros((4, 4)); bad[0, 0] = -0.5; bad[1, 1] = 1.5
        cover_line(bad)                               # negative mass
