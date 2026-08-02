#!/usr/bin/env python
"""H1 — is the model's deficit concentrated outside UEFA/CONMEBOL?

CORRECTED RERUN. The first version of this test was wrong in two ways that a
Codex review caught, and both are fixed upstream in ``oa_devslate.py`` and
``oa_stats.py``:

- it excluded shootouts (selection ON the outcome, and they were the fixtures
  whose 90' result was certain), and scored knockout ties on extra-time-
  inclusive finals. Now the population is restricted BY STAGE to fixtures
  where extra time was structurally impossible.
- it resampled individual fixtures. Now whole (pool, matchday) blocks are
  resampled, matching the programme's tested primitive.

THE HYPOTHESIS (unchanged, still pre-committed)
-----------------------------------------------
Formed on the 217-fixture eval pool, where both-UEFA/CONMEBOL fixtures showed
the model level with the market (+0.0003) and everything else showed it losing
(−0.0182):

    H1  the deficit is concentrated in fixtures involving a team outside
        UEFA/CONMEBOL, where the model's rating history is thinnest.

DIRECTION PRE-COMMITTED: H1 predicts gap < 0, where
``gap = mean(delta | non-core) − mean(delta | core)`` and
``delta = RPS(book) − RPS(model)``. A positive gap means H1
fails to replicate in the predicted direction.

PROVENANCE, STATED HONESTLY: this is out-of-sample relative to where H1 was
generated, but the repository cannot PROVE the direction was fixed before the
numbers were seen — the original hypothesis code and its result landed in one
commit. Treat it as a replication attempt, not an auditable preregistration.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "analysis"))

from oa_devslate import build                                  # noqa: E402
from oa_stats import ALPHA, block_ci, two_group_gap             # noqa: E402

OUT = _ROOT / "reports" / "oa_confed_test.md"


def main() -> int:
    frame, counts = build()
    non = frame[~frame["core"]]
    core = frame[frame["core"]]
    res = two_group_gap(non, core, alternative="less")

    verdict = ("SUPPORTED" if (res.significant and res.gap < 0)
               else "FAILS TO REPLICATE (direction reversed)" if res.gap > 0
               else "FAILS TO REPLICATE")

    lines = [
        "# H1 — confederation hypothesis, out-of-sample on the dev slate", "",
        f"## {verdict}", "",
        "H1 predicts a NEGATIVE gap (non-core loses more). Direction was "
        "pre-committed; a positive gap means it fails to replicate in "
        "that direction, which is NOT the same as refuting it.", "",
    ]
    if res.gap > 0:
        lines += [
            "> **On the reversal.** The gap points the opposite way to H1, "
            f"and the one-sided tail in THAT direction is {res.p:.4f}. That "
            "is not a finding: the direction was not predicted in advance, "
            "so reading significance off it is the same post-hoc move H1 was "
            "supposed to test. What is supported is the narrow claim that H1 "
            "does not replicate — nothing about a reverse effect.", "",
        ]
    lines += [
        "### Population", "",
        f"- dev-slate fixtures: **{counts['total']}**",
        f"- excluded as knockout (extra time possible, no verified 90' table "
        f"for these competitions): **{counts["extra_time_excluded"]}**",
        f"- admitted (group/league only, so full time IS 90'): "
        f"**{counts['admitted']}**", "",
        "Exclusion is BY STAGE, decidable before kickoff. The earlier version "
        "excluded on `winner_override`, which is selection on the result and "
        "dropped exactly the fixtures whose 90' outcome was certain.", "",
        "### Result", "",
        f"- gap (non-core − core): **{res.gap:+.5f}**",
        f"- {int((1 - 2 * ALPHA) * 100)}% block-bootstrap CI (dual to the "
        f"one-sided α={ALPHA} test): [{res.ci_low:+.5f}, {res.ci_high:+.5f}]",
        f"- one-sided null-centred p: **{res.p:.4f}**",
        f"- blocks: {res.n_blocks} pool × matchday, of which "
        f"{res.n_shared_blocks} contain BOTH groups and are drawn whole", "",
        "**Identification limit.** Confederation is nearly collinear with "
        "competition here: all 84 AFCON rows are non-core, all Nations League "
        "and World Cup qualification rows are core, and only Copa América "
        "contains both. The aggregate gap therefore cannot cleanly separate "
        "a confederation effect from a competition effect — no amount of "
        "resampling fixes that, and it is a limit of the sample, not of the "
        "estimator.", "",
        "| group | n | RPS model | RPS book | book − model | CI |",
        "|---|---|---|---|---|---|",
    ]
    for label, sub in (("non-core", non), ("core", core)):
        mean, lo, hi = block_ci(sub)
        lines.append(f"| {label} | {len(sub)} | {sub['rps_model'].mean():.4f} "
                     f"| {sub['rps_book'].mean():.4f} | {mean:+.5f} | "
                     f"[{lo:+.5f}, {hi:+.5f}] |")

    lines += ["", "### By competition", "",
              "| tournament | n | book − model |", "|---|---|---|"]
    for name, grp in frame.groupby("tournament", observed=True):
        lines.append(f"| {name} | {len(grp)} | {grp['delta'].mean():+.5f} |")

    lines += ["", "### Held at fixed favourite strength", "",
              "| favourite band | non-core mean (n) | core mean (n) |",
              "|---|---|---|"]
    banded = frame.assign(band=pd.cut(
        frame["fav_p_book"], [0, 0.40, 0.50, 0.60, 0.75, 1.01],
        labels=["<40%", "40-50%", "50-60%", "60-75%", ">75%"], right=False))
    for band, grp in banded.groupby("band", observed=True):
        a, b = grp[~grp["core"]]["delta"], grp[grp["core"]]["delta"]
        lines.append(f"| {band} | {a.mean():+.5f} ({len(a)}) | "
                     f"{b.mean():+.5f} ({len(b)}) |")
    lines.append("")

    OUT.write_text("\n".join(lines))
    print(f"{verdict} | gap {res.gap:+.5f} "
          f"[{res.ci_low:+.5f}, {res.ci_high:+.5f}] p {res.p:.4f} "
          f"| n={len(frame)} | wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
