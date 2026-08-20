"""A Monte-Carlo standard error beside every headline TRPS of the R1 ledger.

WHAT THIS IS FOR. The v1.1 R1 retrospective's headline tables report TRPS per
(cutoff, season, arm) with no error beside it. The only error column those tables
carry is `MC SE`, which is the position matrix's worst per-cell
cluster-by-particle error — a different quantity, and one amendment A2 (c)
relabelled precisely so it would stop being read as an error on TRPS. R1 ran
under harness v1, which computed no TRPS error; harness v2 computes one, by the
delta method, and every R1 row already stores the per-cell error that method
needs. This module reads those stored errors and supplies the missing column
after the fact.

THE METHOD IS NOT REIMPLEMENTED HERE. :func:`epl.simmetrics.trps_se` is public,
is the function harness v2 scores with, and is imported and called unchanged —
so the addendum cannot drift from the harness by a factor or a transposition. A
hand-worked case beside this module checks that function against an arithmetic
written out independently, so "the same formula" is a claim with a test under it
rather than an assertion about an import.

WHAT THE NUMBER IS, AND IS NOT. It is Monte-Carlo error only: how much this TRPS
would move if the same forecast were re-simulated at another seed. It says
nothing about model error, nothing about the fact that TRPS is proper for the
displayed marginals rather than for the joint law, and nothing about how much a
different SEASON might have disagreed — that last one is what R1's season-block
bootstrap reports, and the two must not be read as versions of each other. It is
the DIAGONAL APPROXIMATION to the delta-method variance: the cross-cell
covariance is omitted, and because the TRPS gradient changes sign within a
club's row the omitted terms can raise or lower the variance, so the direction
of the approximation is not known (amendment A2-N4, which withdraws the earlier
claim that it errs on the safe side).

The nulls record no per-cell error, so their TRPS carries none here. `flat` is
closed-form and has no Monte-Carlo error to report; `ppg_pointmass` is a point
mass. Both are `n/a` rather than 0.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from epl import simmetrics

__all__ = ["AddendumError", "DEFAULT_LEDGER", "CUTOFF_ORDER", "ARM_ORDER",
           "read_ledger", "scored_cells", "per_cutoff_means",
           "addendum_markdown"]

#: The R1 ledger. Under ``data/``, which is gitignored: the report and the
#: preregistration are the committed artifacts, the ledger is reproducible.
DEFAULT_LEDGER = Path("data/epl/sim/retro_r1.jsonl")

#: Cutoffs in the order the report prints them. MW28 is the sanity cutoff and is
#: in no comparison; it is carried here because it is scored, and labelled.
CUTOFF_ORDER = ("MW0", "MW3", "MW6", "MW10", "MW19", "MW28")
COMPARISON_CUTOFFS = ("MW0", "MW3", "MW6", "MW10", "MW19")
SANITY_CUTOFF = "MW28"

ARM_ORDER = ("dc_native", "dc_wdl_bridge", "elo_wdl_bridge", "flat",
             "ppg_pointmass")


class AddendumError(RuntimeError):
    """The addendum refuses to produce a number."""


def read_ledger(path=DEFAULT_LEDGER) -> list[dict]:
    """Every row of a JSONL ledger, in file order."""
    path = Path(path)
    if not path.exists():
        raise AddendumError(
            f"{path} is not there. `data/` is gitignored, so the R1 ledger sits "
            "beside this checkout rather than in it; re-run the retrospective, "
            "or point --ledger at the file.")
    rows = []
    for n, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AddendumError(f"{path}:{n} is not valid JSON ({exc})") from exc
    if not rows:
        raise AddendumError(f"{path} holds no rows")
    return rows


def scored_cells(ledger: Iterable[dict]) -> list[dict]:
    """``TRPS`` and its Monte-Carlo standard error, per (season, cutoff, arm).

    Scored the way the harness scores: the matrix through
    :func:`epl.simmetrics.scored_matrix`, the realised positions read off the
    row's own ``realised`` block in the row's own club order, and the error
    through :func:`epl.simmetrics.trps_se` — the harness's function, imported.
    A row the run marked ``not_applicable`` is skipped, as ``score_retro`` skips
    it: it is a claimed key, not a forecast.
    """
    out: list[dict] = []
    for row in ledger:
        if row.get("not_applicable"):
            continue
        clubs = list(row["clubs"])
        matrix = simmetrics.scored_matrix(row["matrix"], len(clubs))
        realised = row["realised"]
        positions = np.array([int(realised["position"][c]) for c in clubs],
                             dtype=np.int64)
        out.append({
            "season": str(row["season"]),
            "cutoff_label": str(row["cutoff_label"]),
            "cutoff": str(row["cutoff"]),
            "arm": str(row["arm"]),
            "is_null": bool(row.get("is_null", False)),
            "run_key": str(row["run_key"]),
            "trps": float(simmetrics.trps(matrix, positions)),
            "trps_se": simmetrics.trps_se(matrix, positions,
                                          row.get("matrix_se")),
        })
    return out


def per_cutoff_means(cells: Sequence[dict]) -> dict[tuple[str, str], dict]:
    """Mean TRPS per (cutoff, arm), with the Monte-Carlo error OF THAT MEAN.

    The mean of `n` per-season figures, each carrying its own Monte-Carlo error,
    has Monte-Carlo error ``sqrt(sum(se^2)) / n`` — the runs are separate
    simulations and their sampling errors do not cancel with the season index.

    That is NOT the spread across seasons, which is a different and much larger
    quantity: R1's season-block bootstrap (§4) reports that one, and reading
    this number as if it were an interval on 'how a season might have gone'
    would understate the uncertainty by an order of magnitude. Means are taken
    WITHIN a cutoff and never across cutoffs, the rule the report already holds.

    THE SEASONS SHARE A SEED (Codex review of 31dac41, item 2). ``sqrt(sum(se^2))
    / n`` is the error of a mean of INDEPENDENT terms, and R1's seasons are not
    independent draws: ``epl.simretro.run_retro`` runs every cell at one seed,
    and ``epl.leaguesim`` keys its streams on ``(seed, chunk, fixture ordinal)``
    — so two seasons at the same cutoff reuse the same RNG streams on
    differently-numbered fixtures. Whatever covariance that induces is omitted
    here. Its sign is not computed and is not asserted: with a positive
    covariance this figure understates the error of the mean and with a negative
    one it overstates it, and nothing in this addendum establishes which. The
    number is reported as what it is — a mean-of-independent-terms form — and
    the omission is stated rather than argued away.
    """
    grouped: dict[tuple[str, str], list[dict]] = {}
    for cell in cells:
        grouped.setdefault((cell["cutoff_label"], cell["arm"]), []).append(cell)

    out: dict[tuple[str, str], dict] = {}
    for key, group in grouped.items():
        values = [c["trps"] for c in group]
        errors = [c["trps_se"] for c in group]
        complete = all(e is not None for e in errors)
        out[key] = {
            "n_seasons": len(group),
            "mean_trps": float(np.mean(values)),
            "mc_se": (float(math.sqrt(sum(float(e) ** 2 for e in errors))
                            / len(group)) if complete else None),
            "seasons": sorted(c["season"] for c in group),
        }
    return out


def _pm(value: float | None, se: float | None, digits: int = 4) -> str:
    """``TRPS ± SE``. The error carries one more decimal than the score.

    These errors run to a few parts in ten thousand, and at the score's own four
    decimals most of them would print as a single significant figure — a column
    of 0.0003s that cannot be told apart. §4 of the report already quotes paired
    differences at five decimals for the same reason.
    """
    if value is None:
        return "n/a"
    if se is None:
        return f"{value:.{digits}f} ± n/a"
    return f"{value:.{digits}f} ± {se:.{digits + 1}f}"


def addendum_markdown(cells: Sequence[dict], *, ledger_path=DEFAULT_LEDGER,
                      dated: str) -> str:
    """The addendum section, ready to append to the R1 report."""
    if not cells:
        raise AddendumError("no scored cells: there is nothing to report")
    means = per_cutoff_means(cells)
    arms = [a for a in ARM_ORDER if any(c["arm"] == a for c in cells)]
    lines: list[str] = []
    add = lines.append

    add("## Addendum A — TRPS Monte-Carlo error per cell")
    add("")
    add(f"**Added {dated}.** The R1 body above is unchanged: not one TRPS, "
        "wTRPS, Brier, CRPS, coverage, mean, bootstrap interval, count or hash "
        "in §1–§10 has moved, and nothing here is a new run. This section adds "
        "the column those tables did not carry — a Monte-Carlo standard error "
        "on TRPS itself — computed from the per-cell errors the R1 ledger "
        f"already stored (`{Path(ledger_path)}`).")
    add("")

    add("### Method, and what the number is not")
    add("")
    add("TRPS is a smooth function of the position matrix through the "
        "cumulative forecast, so with `X` the cumulative forecast, `O` the "
        "cumulative outcome and `g = dTRPS/dm` evaluated at the reported "
        "matrix:")
    add("")
    add("```")
    add("g[c, k] = 2 / (C (R−1)) · Σ_{r ≥ k} (X[c, r] − O[c, r])")
    add("Var(TRPS) ≈ Σ_{c, k} g[c, k]² · se[c, k]²")
    add("```")
    add("")
    add("`se` is the run's own cluster-by-particle per-cell error, stored on "
        "every R1 row as `matrix_se`. The arithmetic is not reimplemented "
        "here: `epl.simmetrics.trps_se` — the function harness v2 scores with — "
        "is imported and called unchanged, and a hand-worked case in "
        "`epl/tests/test_retro_addendum.py` checks that function against an "
        "independently written-out computation, so 'the same formula' has a "
        "test under it.")
    add("")
    add("- **Monte-Carlo error only.** It is how much this TRPS would move if "
        "the same forecast were re-simulated at another seed. It is **not** "
        "model error: a tight standard error on a badly specified model is "
        "still a badly specified model.")
    add("- **Not the between-season spread.** How much an unseen season might "
        "have disagreed is what §4's season-block bootstrap reports, and it is "
        "one to two orders of magnitude larger. These two numbers are not "
        "versions of each other and must not be read as if they were.")
    add("- **Direction unknown.** This is the DIAGONAL approximation to the "
        "delta-method variance: the cross-cell covariance is omitted, and "
        "because the TRPS gradient changes sign within a club's row the "
        "omitted terms can raise or lower the variance, so the direction of "
        "the approximation is not known. What is dropped is "
        "`g · g' · Cov(·, ·)`, not `Cov(·, ·)`; a club's cells are indeed "
        "predominantly negatively correlated, but a negative covariance "
        "multiplied by two gradient components of opposite sign contributes a "
        "**positive** term. Recorded as amendment **A2-N4**, which withdraws "
        "the claim that this figure errs on the safe side.")
    add("- **`n/a` for the nulls.** `flat` is closed-form and `ppg_pointmass` "
        "is a point mass; neither records a per-cell Monte-Carlo error, so "
        "neither gets an invented one.")
    add("")
    add("**Relation to amendment A2-N1.** That note, recording harness v2's "
        "TRPS SE as a declared deviation, said no score in this report *gains "
        "an SE retroactively*, on the ground that R1 ran under harness v1 and "
        "the column is `n/a` for it by construction. This addendum supplies "
        "one anyway, from the per-cell errors R1 did record, and that is a "
        "second deviation from a pre-statement — recorded here rather than made "
        "quietly. What A2-N1 was protecting is preserved: the R1 body's numbers "
        "are untouched, the harness that produced R1 still computed no TRPS SE, "
        "and nothing below is presented as something the R1 run reported. These "
        "are figures computed after the fact, by a later formula, from stored "
        "errors — an addendum, not a revision.")
    add("")

    add("### Every scored cell — TRPS ± TRPS MC SE (diagonal approx.)")
    add("")
    add("Comparison cutoffs first, then the MW28 sanity cutoff, which is in no "
        "comparison (§7). `±` is the Monte-Carlo standard error described "
        "above.")
    add("")
    for block, cutoffs in (("Comparison cutoffs", COMPARISON_CUTOFFS),
                           ("MW28 — sanity only, in no comparison",
                            (SANITY_CUTOFF,))):
        add(f"#### {block}")
        add("")
        add("| cutoff | season | " + " | ".join(f"`{a}`" for a in arms) + " |")
        add("|---" * (2 + len(arms)) + "|")
        rows = {(c["cutoff_label"], c["season"], c["arm"]): c for c in cells}
        seasons = sorted({c["season"] for c in cells})
        for cutoff in cutoffs:
            for season in seasons:
                present = [rows.get((cutoff, season, a)) for a in arms]
                if not any(present):
                    continue
                body = " | ".join(
                    "—" if cell is None
                    else _pm(cell["trps"], cell["trps_se"])
                    for cell in present)
                add(f"| {cutoff} | {season} | {body} |")
        add("")

    add("### Per-cutoff mean TRPS ± TRPS MC SE (diagonal approx.) of the mean")
    add("")
    add("Means are taken **within** a cutoff and never across cutoffs, and the "
        "season count is on every row because it is not the same at every "
        "cutoff (§2). The error is the Monte-Carlo error of the mean, "
        "`sqrt(Σ se²) / n` over the seasons in that cell — again not the "
        "between-season spread.")
    add("")
    add("**The seasons share a seed, and this form assumes they do not.** "
        "`sqrt(Σ se²) / n` is the error of a mean of INDEPENDENT terms. R1 ran "
        "every cell at one seed (`epl.simretro.run_retro`), and the engine keys "
        "its random streams on `(seed, chunk, fixture ordinal)` "
        "(`epl.leaguesim`), so two seasons at the same cutoff reuse the same "
        "streams on differently-numbered fixtures. Whatever covariance that "
        "induces is **omitted** here, and its **direction is unknown**: a "
        "positive covariance would make this figure too small and a negative "
        "one too large, and nothing in this addendum computes which. Stated "
        "rather than argued away — the same discipline as A2-N4 above.")
    add("")
    add("| cutoff | seasons | " + " | ".join(f"`{a}`" for a in arms) + " |")
    add("|---" * (2 + len(arms)) + "|")
    for cutoff in CUTOFF_ORDER:
        present = [means.get((cutoff, a)) for a in arms]
        if not any(present):
            continue
        n_seasons = max((m["n_seasons"] for m in present if m), default=0)
        body = " | ".join(
            "—" if m is None else _pm(m["mean_trps"], m["mc_se"])
            for m in present)
        add(f"| {cutoff} | {n_seasons} | {body} |")
    add("")
    add("Read these against §3 and §7: the TRPS values are the same numbers "
        "those tables print, recomputed from the same ledger rows, and the "
        "column added is the error beside them. No pass rule reads any figure "
        "in this addendum — there is none to read (prereg §7) — and the "
        "published-arm question is unchanged by it.")
    add("")
    return "\n".join(lines) + "\n"


def _cli(argv: Sequence[str] | None = None) -> None:                # pragma: no cover
    """Print the addendum, or append it to the report."""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    ap.add_argument("--dated", required=True,
                    help="the date this addendum was added, e.g. 2026-08-19")
    ap.add_argument("--append-to", default=None,
                    help="a report to append the section to (default: stdout)")
    args = ap.parse_args(list(argv) if argv is not None else None)

    cells = scored_cells(read_ledger(args.ledger))
    text = addendum_markdown(cells, ledger_path=args.ledger, dated=args.dated)
    if args.append_to is None:
        print(text)
        return
    path = Path(args.append_to)
    body = path.read_text()
    path.write_text(body.rstrip("\n") + "\n\n---\n\n" + text)
    print(f"[addendum] appended {len(cells)} scored cell(s) to {path}")


if __name__ == "__main__":                                          # pragma: no cover
    _cli()
