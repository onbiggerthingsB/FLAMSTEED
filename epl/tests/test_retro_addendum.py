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
    # A2-N4: the generator must NOT re-emit the withdrawn claim. Regenerating
    # this section used to restore "Conservative, not exact" and "overstates"
    # over the report's own relabelling, with the suite green throughout.
    assert "conservative" not in text.lower()
    assert "overstates" not in text.lower()
    assert "conservative rather than exact" not in text
    assert "can raise or lower the variance" in text
    assert "the direction of the approximation is not known" in text
    # ...and the OTHER omitted covariance, which the mean-of-seasons form makes
    # and which nothing had stated (Codex review of 31dac41, item 2): R1 runs
    # every cell at one seed, so the seasons are not independent draws.
    assert "The seasons share a seed" in text
    assert "direction is unknown" in text
    assert "`epl.leaguesim`" in text
    # the pre-statement it departs from is named, not left for a reader to find
    assert "A2-N1" in text
    # every cell carries its error, and the nulls carry `n/a` rather than 0
    assert "0.0400 ± 0.00283" in text
    assert "± n/a" in text
    # MW28 is present and labelled as being in no comparison
    assert "MW28" in text and "in no comparison" in text


def test_the_addendum_reports_a_mean_row_per_cutoff_with_its_season_count():
    text = retro_addendum.addendum_markdown(_cells(), dated="2026-08-19")
    assert ("### Per-cutoff mean TRPS ± TRPS MC SE (diagonal approx.) "
            "of the mean") in text
    assert "sqrt(Σ se²) / n" in text
    # two seasons per cutoff in this fixture, and the mean of two identical
    # cells is that cell with sqrt(2 se^2)/2 beside it
    assert "| MW0 | 2 | 0.0400 ± 0.00200" in text


def test_an_empty_set_of_cells_refuses_rather_than_rendering_an_empty_table():
    with pytest.raises(retro_addendum.AddendumError):
        retro_addendum.addendum_markdown([], dated="2026-08-19")


# ==========================================================================
# 5. the deviation is recorded where the record lives
# ==========================================================================
# Addendum A departs from two pre-statements: A2's "A TRPS Monte-Carlo error is
# **not** part of v2", and A2-N1's "No score in reports/epl_sim_retro_v1_1.md
# gains an SE retroactively." It declares that departure in its own prose, which
# is honest but is not the record: reports/epl_sim_amendments.md is the artifact
# whose whole purpose is to hold what was pre-stated against what departed from
# it, and a reader auditing THAT file was told the deviation had not happened.
#
# So: if the addendum is present, the ledger must carry a dated note recording
# it — and the two sentences it departs from must still stand, wrong, unedited,
# in the entries that wrote them, for the reason A1-C1 gives.
#
# Both "still stands" checks look INSIDE the owning entry, not anywhere in the
# file. A later note quoting a sentence in order to contradict it must not be
# able to stand in for the original — that is precisely the substitution this
# guard exists to catch. The check is a pure function of the two texts, so every
# way of failing it can be driven RED on synthetic input rather than by
# vandalising the repo.

_REPO_ROOT = Path(__file__).resolve().parents[2]

# A2-N1's claim, verbatim modulo line wrapping. It is false of HEAD; it stays.
_A2N1_CLAIM = "gains an SE retroactively. R1 ran under harness v1, which computed none"
# A2's pre-statement, as A2 wrote it.
_A2_PRESTATEMENT = "A TRPS Monte-Carlo error is **not** part of v2."
_ADDENDUM_HEADING = "## Addendum A — TRPS Monte-Carlo error per cell"


def _squash(text: str) -> str:
    """Collapse whitespace, so a line-wrapped sentence matches an unwrapped one."""
    return " ".join(text.split())


def _entry(ledger_text: str, heading: str) -> str:
    """One ledger entry: its heading through the next `## ` heading, or the end."""
    start = ledger_text.find(heading)
    if start < 0:
        return ""
    nxt = ledger_text.find("\n## ", start + len(heading))
    return ledger_text[start:] if nxt < 0 else ledger_text[start:nxt]


def _unrecorded_deviations(retro_text: str, ledger_text: str) -> list[str]:
    """Reasons the ledger fails to record what the retrospective report did.

    Empty means the record is complete. Reasons are returned rather than
    asserted so that a failure names which half is missing.
    """
    if _ADDENDUM_HEADING not in retro_text:
        return []  # nothing to record: the report supplies no retroactive SE

    reasons: list[str] = []
    append_only = ("this ledger is append-only (A1-C1): a deviation is recorded "
                   "by a NEW dated note, never by editing the entry it departs "
                   "from, and never by a later note quoting the sentence it "
                   "replaced")

    if _squash(_A2N1_CLAIM) not in _squash(_entry(ledger_text, "## A2-N1")):
        reasons.append(f"A2-N1 no longer contains its own claim — {append_only}")
    if _squash(_A2_PRESTATEMENT) not in _squash(_entry(ledger_text, "## A2 —")):
        reasons.append(f"A2 no longer contains its TRPS-SE pre-statement — "
                       f"{append_only}")

    head = ledger_text.find("## A2-N3")
    if head < 0:
        reasons.append(
            "no A2-N3 note: reports/epl_sim_retro_v1_1.md carries a TRPS MC SE "
            "for its scored cells, a second deviation from A2's pre-statement "
            "and a direct contradiction of A2-N1, and the ledger does not say so")
        return reasons

    if head < ledger_text.find("## A2-N1"):
        reasons.append("A2-N3 precedes A2-N1; notes are appended, not interleaved")

    note = _entry(ledger_text, "## A2-N3")
    for needed, what in (
            ("Addendum A", "the section it records"),
            ("epl_sim_retro_v1_1.md", "the report it records"),
            ("A2-N1", "the note it contradicts"),
            ("No pass rule reads", "that nothing decides on these figures")):
        if needed not in note:
            reasons.append(f"A2-N3 does not name {what} ({needed!r})")
    return reasons


# a ledger shaped like the real one: A2 states it, A2-N1 denies the retroactive
# case, A2-N3 records that it happened anyway
_LEDGER = f"""## A2 — Harness v2 (2026-08-19)

Pre-stated: {_A2_PRESTATEMENT}

## A2-N1 — one deviation from A2 (2026-08-19)

No score in `x.md` {_A2N1_CLAIM}, and there is not one yet.

## A2-N2 — something else (2026-08-19)

Unrelated.

## A2-N3 — R1's TRPS gains one after the fact (2026-08-19)

Addendum A of epl_sim_retro_v1_1.md is a second deviation, and A2-N1 said it
would not happen. No pass rule reads them.
"""
_RETRO = f"body\n\n{_ADDENDUM_HEADING}\n\nTRPS ± MC SE\n"


def test_the_check_passes_only_when_the_ledger_actually_records_it():
    assert _unrecorded_deviations(_RETRO, _LEDGER) == []
    # and with no addendum in the report there is nothing to record
    assert _unrecorded_deviations("body only\n", _LEDGER.split("## A2-N3")[0]) == []


def test_the_check_fails_when_the_note_is_missing_or_says_nothing():
    """Positive control: no note at all, and a note that records nothing."""
    absent = _LEDGER.split("## A2-N3")[0]
    assert any("no A2-N3 note" in r
               for r in _unrecorded_deviations(_RETRO, absent))

    empty = absent + "## A2-N3 — a heading and no content (2026-08-19)\n\nnothing.\n"
    assert len(_unrecorded_deviations(_RETRO, empty)) == 4


def test_the_check_fails_when_a_pre_statement_was_edited_instead_of_superseded():
    """Positive control, and the one that matters most.

    Rewriting A2-N1 to agree with the report — rather than leaving it wrong and
    appending a note — must fail even though A2-N3 quotes the deleted sentence
    back, which is exactly how such an edit would look from a whole-file search.
    """
    edited = _LEDGER.replace(f"No score in `x.md` {_A2N1_CLAIM}, and there is "
                             "not one yet.",
                             "Scores may gain an SE retroactively.")
    # the sentence still appears in the file — in A2-N3, quoting it
    edited = edited.replace("A2-N1 said it\nwould not happen.",
                            f"A2-N1 once said no score {_A2N1_CLAIM}.")
    assert _A2N1_CLAIM in edited
    assert any("A2-N1 no longer contains its own claim" in r
               for r in _unrecorded_deviations(_RETRO, edited))

    # the same substitution against A2's pre-statement
    gutted = _LEDGER.replace(f"Pre-stated: {_A2_PRESTATEMENT}",
                             "Pre-stated: a TRPS MC SE is part of v2.")
    gutted = gutted.replace("is a second deviation,",
                            f"is a second deviation from "
                            f"{_A2_PRESTATEMENT},")
    assert _A2_PRESTATEMENT in gutted
    assert any("A2 no longer contains its TRPS-SE pre-statement" in r
               for r in _unrecorded_deviations(_RETRO, gutted))


def test_the_amendment_ledger_records_the_addendum_s_deviation():
    """The real files: reports/epl_sim_amendments.md against Addendum A."""
    retro = _REPO_ROOT / "reports" / "epl_sim_retro_v1_1.md"
    ledger = _REPO_ROOT / "reports" / "epl_sim_amendments.md"
    if not (retro.exists() and ledger.exists()):  # pragma: no cover
        pytest.skip("reports/ is not in this checkout")

    reasons = _unrecorded_deviations(retro.read_text(encoding="utf-8"),
                                     ledger.read_text(encoding="utf-8"))
    assert reasons == [], "; ".join(reasons)


def test_the_generated_headings_are_the_ones_the_published_report_prints():
    """The generator and the report it generated must not drift apart.

    Addendum A was edited IN PLACE to carry A2-N4's label while
    `epl/retro_addendum.py` still emitted the withdrawn wording, and the suite
    pinned the generator's old string — so regenerating the section would have
    silently reverted the whole relabelling and restored the "Conservative, not
    exact" bullet, with CI green from start to finish. A note in a file is not a
    guard; this is the guard, and it is the same docs/code coupling shape used
    above to hold A2-N3's note against the report.
    """
    report = _REPO_ROOT / "reports" / "epl_sim_retro_v1_1.md"
    if not report.exists():                                 # pragma: no cover
        pytest.skip("reports/ is not in this checkout")
    published = report.read_text(encoding="utf-8")
    generated = retro_addendum.addendum_markdown(_cells(), dated="2026-08-19")

    headings = [line for line in generated.splitlines()
                if line.startswith("### ") or line.startswith("## Addendum")]
    assert headings, "the generator emits headings"
    for heading in headings:
        assert heading in published, (
            f"the generator emits {heading!r}, which Addendum A does not print "
            "— regenerating the section would rewrite the published report")

    # POSITIVE CONTROL: the check really compares the two texts
    assert "### Every scored cell — TRPS ± MC SE" not in published
    assert not any(h in published.replace(
        "### Every scored cell — TRPS ± TRPS MC SE (diagonal approx.)", "")
        for h in headings if "Every scored cell" in h)

    # and the withdrawn claim is not what the generator would write back
    assert "conservative" not in generated.lower()
    assert "conservative rather than exact" not in generated

    # the SOURCE too, not only its output: a phrase withdrawn in the report and
    # left in the code is one regeneration away from coming back (Codex review
    # of d2263c6, item 4).
    import inspect

    from epl import simmetrics

    for module in (retro_addendum, simmetrics):
        assert "conservative rather than exact" not in inspect.getsource(module), \
            module.__name__
