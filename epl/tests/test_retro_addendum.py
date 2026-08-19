"""The TRPS Monte-Carlo error added to R1 after the fact, and its arithmetic.

The R1 retrospective's headline tables print TRPS with no error beside it. Every
R1 ledger row nevertheless stores the per-cell cluster error the delta method
needs, so the column can be supplied after the fact — and this is where "the
same formula the harness uses" stops being an assertion about an import.

Two checks stand under that claim. A hand-worked 2-club case, where `g` and the
variance are written out by hand and compared with what
`epl.simmetrics.trps_se` returns. And a numerical-derivative cross-check on a
4-club matrix: `dTRPS/dm` computed by perturbing each cell against the last
column of its own row — row-sum preserving, because `trps` refuses an
inadmissible matrix — and re-evaluating TRPS, which is an independent route to
the same `g` and would catch a transposition, a dropped factor of two, or a
wrong denominator.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from epl import retro_addendum, simmetrics


# ==========================================================================
# 1. the method — checked against arithmetic written out independently
# ==========================================================================
def test_the_delta_method_matches_a_hand_worked_case():
    """Two clubs, two ranks, everything written out.

    x = cumsum(matrix)[:, :-1] = [[0.8], [0.2]]; the outcome step is [[1], [0]]
    for a table where club 0 finished first. residual = x - o = [[-0.2], [0.2]],
    and with one cumulative boundary the reverse-cumulative tail IS the
    residual, so g[:, 0] = 2 * tail / (C (R-1)) = 2 * [-0.2, 0.2] / 2 =
    [-0.2, 0.2] and g[:, 1] = 0 — the last rank drops out because every club
    reaches it. Var = 0.04 * (0.01^2 + 0.02^2), and the errors in the dropped
    column cannot contribute however large they are.
    """
    matrix = [[0.8, 0.2], [0.2, 0.8]]
    positions = [1, 2]
    matrix_se = [[0.01, 0.05], [0.02, 0.03]]

    by_hand = math.sqrt(0.04 * (0.01 ** 2 + 0.02 ** 2))
    got = simmetrics.trps_se(matrix, positions, matrix_se)
    assert got == pytest.approx(by_hand, rel=1e-12)
    assert got == pytest.approx(0.0044721359549996, rel=1e-9)

    # ...and TRPS itself, on the same case: ((o - x)^2).sum() / (C (R-1))
    assert simmetrics.trps(matrix, positions) == pytest.approx(0.04)

    # the dropped column really is dropped: move only those errors, nothing else
    louder = [[0.01, 5.0], [0.02, 9.0]]
    assert simmetrics.trps_se(matrix, positions, louder) == pytest.approx(got)


def test_the_analytic_gradient_agrees_with_a_numerical_one():
    """An independent route to `g`: perturb every cell and re-evaluate TRPS.

    This is the check that a transposition, a missing factor of two or a wrong
    denominator could not survive, because nothing in it reuses the analytic
    derivation — only `trps` itself, evaluated 24 times.
    """
    rng = np.random.default_rng(11)
    n = 4
    matrix = rng.random((n, n)) + 0.2
    matrix /= matrix.sum(axis=1, keepdims=True)
    positions = np.array([2, 1, 4, 3], dtype=np.int64)
    matrix_se = 0.001 * (1.0 + rng.random((n, n)))

    # The perturbation is row-sum preserving — `trps` refuses an inadmissible
    # matrix, and rightly — so each cell moves against the LAST column of its
    # own row. That measures `g[i, j] - g[i, R-1]`, and the last rank's
    # derivative is identically zero (every club reaches the worst rank, so the
    # paper's sum stops at R-1), which is why the difference IS `g[i, j]` and
    # why the final column contributes nothing to the variance either way.
    step = 1e-6
    variance = 0.0
    for i in range(n):
        for j in range(n - 1):
            up, down = matrix.copy(), matrix.copy()
            up[i, j] += step
            up[i, n - 1] -= step
            down[i, j] -= step
            down[i, n - 1] += step
            slope = (simmetrics.trps(up, positions)
                     - simmetrics.trps(down, positions)) / (2 * step)
            variance += (slope * matrix_se[i, j]) ** 2

    assert simmetrics.trps_se(matrix, positions, matrix_se) == pytest.approx(
        math.sqrt(variance), rel=1e-6)


def test_a_row_that_recorded_no_per_cell_error_gets_no_invented_one():
    assert simmetrics.trps_se([[0.8, 0.2], [0.2, 0.8]], [1, 2], None) is None


# ==========================================================================
# 2. reading the ledger
# ==========================================================================
def _row(season: str, cutoff_label: str, arm: str, *, p: float = 0.8,
         se: float | None = 0.01, clubs=("alpha", "beta"),
         positions=(1, 2), not_applicable: bool = False) -> dict:
    """One ledger row, shaped like the R1 harness writes them."""
    if not_applicable:
        return {"season": season, "cutoff_label": cutoff_label,
                "cutoff": "2020-01-01", "arm": arm, "not_applicable": True,
                "run_key": f"{season}|{cutoff_label}|{arm}", "is_null": True}
    matrix = [[p, 1 - p], [1 - p, p]]
    return {
        "season": season, "cutoff_label": cutoff_label, "cutoff": "2020-01-01",
        "arm": arm, "is_null": arm in ("flat", "ppg_pointmass"),
        "run_key": f"{season}|{cutoff_label}|{arm}",
        "clubs": list(clubs), "matrix": matrix,
        "matrix_se": None if se is None else [[se, se], [se, se]],
        "realised": {"position": dict(zip(clubs, positions))},
    }


def test_scored_cells_reads_trps_and_its_error_per_row():
    cells = retro_addendum.scored_cells([
        _row("2021/22", "MW0", "dc_native"),
        _row("2021/22", "MW0", "flat", p=0.5, se=None),
    ])
    assert [c["arm"] for c in cells] == ["dc_native", "flat"]
    assert cells[0]["trps"] == pytest.approx(0.04)
    assert cells[0]["trps_se"] == pytest.approx(
        math.sqrt(0.04 * (0.01 ** 2 + 0.01 ** 2)))
    # the null records no per-cell error and is reported without one
    assert cells[1]["trps_se"] is None
    assert cells[1]["is_null"] is True


def test_a_not_applicable_marker_is_skipped_as_the_harness_skips_it():
    cells = retro_addendum.scored_cells([
        _row("2021/22", "MW0", "ppg_pointmass", not_applicable=True),
        _row("2021/22", "MW3", "ppg_pointmass"),
    ])
    assert [c["cutoff_label"] for c in cells] == ["MW3"]


def test_positions_are_read_in_the_row_s_own_club_order():
    """The realised block is a mapping; the matrix is ordered by `clubs`."""
    straight = retro_addendum.scored_cells([_row("2021/22", "MW0", "dc_native")])
    swapped = _row("2021/22", "MW0", "dc_native", clubs=("beta", "alpha"),
                   positions=(2, 1))
    # the same table, described from the other club's row first
    swapped["matrix"] = [[0.2, 0.8], [0.8, 0.2]]
    got = retro_addendum.scored_cells([swapped])
    assert got[0]["trps"] == pytest.approx(straight[0]["trps"])


def test_a_missing_ledger_refuses_with_the_path(tmp_path):
    with pytest.raises(retro_addendum.AddendumError) as exc:
        retro_addendum.read_ledger(tmp_path / "not_there.jsonl")
    assert "not_there.jsonl" in str(exc.value)


def test_an_unparseable_ledger_line_refuses_with_its_number(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps(_row("2021/22", "MW0", "dc_native")) + "\n{oops\n")
    with pytest.raises(retro_addendum.AddendumError) as exc:
        retro_addendum.read_ledger(path)
    assert ":2" in str(exc.value)


# ==========================================================================
# 3. the per-cutoff means, and the error OF the mean
# ==========================================================================
def test_the_mean_carries_the_monte_carlo_error_of_the_mean():
    cells = [
        {"season": "a", "cutoff_label": "MW0", "arm": "dc_native",
         "trps": 0.10, "trps_se": 0.003},
        {"season": "b", "cutoff_label": "MW0", "arm": "dc_native",
         "trps": 0.20, "trps_se": 0.004},
    ]
    got = retro_addendum.per_cutoff_means(cells)[("MW0", "dc_native")]
    assert got["n_seasons"] == 2
    assert got["mean_trps"] == pytest.approx(0.15)
    # sqrt(0.003^2 + 0.004^2) / 2 = 0.005 / 2
    assert got["mc_se"] == pytest.approx(0.0025)
    assert got["seasons"] == ["a", "b"]


def test_one_missing_error_makes_the_mean_s_error_unavailable_not_partial():
    cells = [
        {"season": "a", "cutoff_label": "MW0", "arm": "flat", "trps": 0.175,
         "trps_se": None},
        {"season": "b", "cutoff_label": "MW0", "arm": "flat", "trps": 0.175,
         "trps_se": 0.001},
    ]
    got = retro_addendum.per_cutoff_means(cells)[("MW0", "flat")]
    assert got["mean_trps"] == pytest.approx(0.175)
    assert got["mc_se"] is None


# ==========================================================================
# 4. the section it renders
# ==========================================================================
def _cells():
    ledger = []
    for season in ("2021/22", "2022/23"):
        for cutoff in ("MW0", "MW19", "MW28"):
            ledger.append(_row(season, cutoff, "dc_native"))
            ledger.append(_row(season, cutoff, "flat", p=0.5, se=None))
    return retro_addendum.scored_cells(ledger)


def test_the_addendum_states_the_method_the_deviation_and_the_body_unchanged():
    text = retro_addendum.addendum_markdown(_cells(), dated="2026-08-19")

    assert "## Addendum A — TRPS Monte-Carlo error per cell" in text
    assert "**Added 2026-08-19.**" in text
    assert "unchanged" in text
    # the method, in full, and what it is not
    assert "Var(TRPS) ≈ Σ_{c, k} g[c, k]² · se[c, k]²" in text
    assert "epl.simmetrics.trps_se" in text
    assert "not** model error" in text
    assert "between-season spread" in text
    assert "overstates" in text
    # the pre-statement it departs from is named, not left for a reader to find
    assert "A2-N1" in text
    # every cell carries its error, and the nulls carry `n/a` rather than 0
    assert "0.0400 ± 0.00283" in text
    assert "± n/a" in text
    # MW28 is present and labelled as being in no comparison
    assert "MW28" in text and "in no comparison" in text


def test_the_addendum_reports_a_mean_row_per_cutoff_with_its_season_count():
    text = retro_addendum.addendum_markdown(_cells(), dated="2026-08-19")
    assert "### Per-cutoff mean TRPS ± MC SE of the mean" in text
    assert "sqrt(Σ se²) / n" in text
    # two seasons per cutoff in this fixture, and the mean of two identical
    # cells is that cell with sqrt(2 se^2)/2 beside it
    assert "| MW0 | 2 | 0.0400 ± 0.00200" in text


def test_an_empty_set_of_cells_refuses_rather_than_rendering_an_empty_table():
    with pytest.raises(retro_addendum.AddendumError):
        retro_addendum.addendum_markdown([], dated="2026-08-19")
