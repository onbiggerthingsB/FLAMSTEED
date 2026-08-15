"""THE FRESH HOLDOUT (2025/26) AND THE DECLARED SECOND LOOK (2019/20-2024/25).

WHAT THIS MODULE IS. ``reports/epl_prereg_v2.md`` was committed at ``f4c16a8``
with three things fixed in advance: a final stack (the frozen configuration,
because nothing was adopted), a pass rule for the fresh 2025/26 holdout (§5.2),
and a rule for any future SECOND LOOK at the confirmatory window (§6). This
module executes exactly those and nothing else. It chooses nothing, tunes
nothing, and touches 2025/26 once.

THE THREE WINDOWS, WHICH MUST NOT BLUR.

===========  =====================  ======  ===================================
window       seasons                n       what this module does with it
===========  =====================  ======  ===================================
TUNE         2015/16-2018/19         1,520  reads the ledgers the selection
                                            phase already wrote; runs no fit
CONFIRM      2019/20-2024/25         2,280  SECOND LOOK, re-scored from run 1's
                                            ledger; runs no fit (see below)
HOLDOUT      2025/26                   380  36 fits, scored ONCE, never tuned on
===========  =====================  ======  ===================================

WHY THE SECOND LOOK RUNS NO FIT. The final stack is ``Improvements()`` — every
gate off — and ``improve.wcmodel_config(OFF)`` is byte-identical to
``freeze.frozen_wcmodel_config()``, which is the configuration run 1 scored on
that window. Re-fitting 212 cutoffs would reproduce run 1's forecasts and
therefore run 1's numbers; it would be the same look recomputed, not a second
one. So the confirm-window numbers here are RE-SCORED from run 1's committed
ledger (``data/epl/fit/walkforward_ledger.jsonl``) — deterministic, because
``score.block_bootstrap_ci`` carries a fixed seed — and every one of them is
labelled SECOND LOOK, with the multiplicity that already exists (the levers were
chosen after reading run 1's report) stated rather than implied.

WHAT IS DEVIATED FROM, AND WHY. Preregistration v2 §5.4 names the holdout
command as ``epl.select.run_sweep(OFF, window="holdout", holdout=True)``. That
command's DEFAULT grid prices nine predict-time variants off each fit, which
contradicts the same table's "touched exactly once ... no second variant". This
module resolves the inconsistency the only way that keeps the stronger clause:
it calls the named function with the one-point grid ``({},)`` — the same
``--control-only`` restriction the selection phase used for its seed replica —
so exactly one forecaster ever sees 2025/26. It additionally wraps each fit in
``warnings.catch_warnings(record=True)``, as ``epl.walkforward._one_cutoff``
does, because ADVI warnings are to be reported PER FIT and ``run_sweep`` does
not record them. Neither change can move a number: the warning capture is
passive, and the grid restriction only removes variants.

NO BETTING, AND ON THIS WINDOW NO ODDS AT ALL. The DC-versus-Elo question needs
no prices. 2025/26's odds coverage is a biased contiguous tail (210 of 380,
prices stop 2026-01-08), which is why ``epl.windows`` excluded the season from
both of the earlier windows in the first place; ``improve.score_walk`` scores
with ``require_odds=False`` and reads no market column, so no odds-derived
number for 2025/26 exists anywhere in this module's output.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from epl import baseline, freeze, improve, paths, select, walkforward, windows
from epl import score as score_mod
from epl.improve import OFF
from epl.schema import sort_for_walk_forward

__all__ = [
    "RULE", "LEDGER_PATH", "RESULT_PATH", "assert_stack_is_frozen",
    "run_holdout", "score_holdout", "second_look_confirm", "ablation",
]

#: One JSONL per variant, as everything else in this probe. The name is
#: ``select.ledger_path(OFF, "holdout")`` so the file is discoverable from the
#: preregistered command rather than from this module.
LEDGER_PATH: Path = select.ledger_path(OFF, "holdout")
WARNINGS_PATH: Path = improve.IMPROVE_DIR / "holdout_off_warnings.json"
RESULT_PATH: Path = improve.IMPROVE_DIR / "holdout_result.json"
CONFIRM_PATH: Path = improve.IMPROVE_DIR / "second_look_confirm.json"
ABLATION_PATH: Path = improve.IMPROVE_DIR / "ablation.json"

#: The commit that carries the preregistration and the frozen configuration.
#: STOP 4 ("a frozen value needing to change") is checked against it, from git,
#: rather than against a copy of the numbers pasted into this file.
FROZEN_AT = "b416925"

#: ``reports/epl_prereg_v2.md`` §5.2, as numbers, restated in executable form.
#: The thresholds are NOT recomputed from anything this run measures.
RULE: dict[str, Any] = {
    "primary": ("Delta_H = mean RPS(final stack) - mean RPS(walk-forward Elo) "
                "over all 380 matches of 2025/26, negative = the model is "
                "better, with a 95% block-bootstrap CI over (season, ISO-week) "
                "blocks and 10,000 resamples."),
    "REGRESSION": ("Delta_H >= +0.0057 (the holdout's own 80%-power two-sided "
                   "MDE at the confirm window's paired SD) OR the 95% CI lies "
                   "entirely above zero. The guard fires and the probe STOPS."),
    "DIRECTIONAL_PASS": ("Delta_H <= 0. Weak and explicitly NOT confirmation: "
                         "under the null this happens half the time."),
    "INDETERMINATE": ("everything else, i.e. 0 < Delta_H < +0.0057 with a CI "
                      "crossing zero. This is the EXPECTED outcome and is the "
                      "correct report, not a failed one."),
    "mde80_holdout": 0.0057,
    "secondary_deciding_nothing": [
        "mean natural-log loss on the same 380",
        "Delta_S = mean RPS(final stack) - mean RPS(frozen stack), identically "
        "0.000000 by construction because nothing was adopted",
        "the inverse-variance pooled three-window estimate",
    ],
    "no_subsets": ("v2 §9 fixes what the holdout report contains and no subset "
                   "is in it. In particular the promoted-club slice that run 1 "
                   "flagged (-0.0033 on 648) is NOT computed here: it was "
                   "generated by reading the confirm window, its holdout "
                   "counterpart would carry an MDE near 0.010 on ~100 matches, "
                   "and computing it now would be exactly the post-hoc "
                   "subgroup confirmation the preregistration forbids."),
}

#: v2 §7. Each is checked and reported with its status, whichever way it falls.
STOPS = ("regression_on_the_holdout", "unpriceable_fixture",
         "failed_point_in_time_canary", "a_frozen_value_needing_to_change",
         "too_good", "cost_above_one_hour")


# ==========================================================================
# 0. the stack, proved to be the frozen one before anything is scored
# ==========================================================================
def assert_stack_is_frozen() -> dict[str, Any]:
    """Prove the thing about to be scored IS the frozen configuration.

    Three checks, none of them a restatement of the other:

    1. the selected stack has every gate off (``Improvements().is_off()``);
    2. the wcmodel config it produces is byte-identical, as JSON with sorted
       keys, to ``freeze.frozen_wcmodel_config()`` — the config run 1 used;
    3. ``epl/config_frozen.json`` on disk is byte-identical to the blob
       committed at :data:`FROZEN_AT`, which is STOP 4 checked against git
       rather than against a transcription.
    """
    a = json.dumps(improve.wcmodel_config(OFF), sort_keys=True, default=str)
    b = json.dumps(freeze.frozen_wcmodel_config(), sort_keys=True, default=str)
    on_disk = freeze.FROZEN_PATH.read_bytes()
    committed = subprocess.run(
        ["git", "show", f"{FROZEN_AT}:{paths.rel(freeze.FROZEN_PATH)}"],
        cwd=paths.REPO_ROOT, capture_output=True, check=True).stdout
    out = {
        "stack_spec": OFF.spec,
        "gates_enabled": list(OFF.enabled),
        "stack_is_off": bool(OFF.is_off()),
        "wcmodel_config_byte_identical_to_frozen": bool(a == b),
        "config_frozen_json_identical_to_" + FROZEN_AT: bool(on_disk == committed),
        "elo_config": freeze.frozen_elo_config().as_dict(),
    }
    if not all(v for k, v in out.items()
               if isinstance(v, bool)):
        raise AssertionError(
            f"the stack about to be scored is not the frozen configuration: "
            f"{out}. Preregistration v2 §7.4 makes that a STOP.")
    return out


# ==========================================================================
# 1. the holdout walk — 36 fits, one variant, warnings captured per fit
# ==========================================================================
def _cutoffs(matches: pd.DataFrame) -> list[walkforward.Cutoff]:
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    return walkforward.matchweek_cutoffs(played,
                                         score_seasons=windows.EXCLUDED_SEASONS,
                                         cadence=walkforward.CADENCE_WEEKS,
                                         allow_excluded=True)


def run_holdout(matches: pd.DataFrame | None = None, resume: bool = True,
                budget_seconds: float = 3600.0, verbose: bool = True,
                ) -> dict[str, Any]:
    """The preregistered holdout walk: 36 weekly fits, one forecaster.

    Each cutoff is run by ``epl.select.run_sweep`` — the function v2 §5.4 names
    — restricted to the one-point grid, one cutoff per call, inside a warning
    recorder. Calling it once per cutoff is what makes the ADVI warnings
    attributable to a fit; ``run_sweep``'s own resume logic makes it exact (a
    cutoff already in the ledger is skipped, so call ``k`` fits cutoff ``k`` and
    nothing else).

    STOP 2 (an unpriceable fixture) and STOP 6 (cost) are enforced here, in the
    loop, so the run halts on them rather than reporting around them.
    """
    matches = baseline.load_matches() if matches is None else matches
    cuts = _cutoffs(matches)
    started = time.time()
    rows: list[dict[str, Any]] = []
    per_fit: list[dict[str, Any]] = []

    for k, cut in enumerate(cuts, 1):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = select.run_sweep(OFF, grid=({},), window="holdout",
                                   holdout=True, matches=matches,
                                   resume=resume, limit=k, verbose=False)
            warns = sorted({f"{w.category.__name__}: {w.message}"
                            for w in caught})
        if out["n_fitted"] > 1:
            raise AssertionError(
                f"call {k} fitted {out['n_fitted']} cutoffs; the per-fit "
                "warning attribution assumes exactly one")
        row = json.loads(LEDGER_PATH.read_text().splitlines()[-1])
        if row["key"] != cut.key:
            raise AssertionError(f"ledger tail is {row['key']}, expected {cut.key}")
        if row["unpriceable"]:
            raise AssertionError(
                f"STOP 2: {len(row['unpriceable'])} unpriceable fixture(s) at "
                f"{cut.key}: {row['unpriceable']}. Scoring 379 would bias the "
                "sample toward matches the model finds easy.")
        # The ledger stores probabilities ROUNDED TO 8 DECIMALS, so three of
        # them can sum to 1 +/- 1.5e-8 without anything being wrong. (The
        # unrounded array is normalised by construction inside
        # ``predict_1x2``; ``walkforward._one_cutoff`` applies its own 1e-9
        # check BEFORE rounding, which is why the two tolerances differ.)
        # 1e-7 is loose enough for the rounding and ~seven orders of magnitude
        # tighter than any error that would move a score.
        arr = np.asarray(row["probs"], dtype=float)
        bad = [m for m, p in zip(row["match_ids"], arr)
               if not (np.isfinite(p).all() and abs(p.sum() - 1.0) < 1e-7)]
        if bad:
            raise AssertionError(f"malformed forecast(s) at {cut.key}: {bad}")
        per_fit.append({
            "key": row["key"], "cutoff": row["cutoff"],
            "n_fixtures": row["n_fixtures"],
            "n_training_matches": row["n_training_matches"],
            "n_teams": row["n_teams"],
            "cold_start_teams": row["cold_start_teams"],
            "provisional_teams": row["provisional_teams"],
            "fit_seconds": row["fit_seconds"],
            "refitted_now": bool(out["n_fitted"] == 1),
            "advi_warnings": warns,
        })
        rows.append(row)
        elapsed = time.time() - started
        if elapsed > budget_seconds:
            raise AssertionError(
                f"STOP 6: the walk has cost {elapsed/60:.1f} minutes, past the "
                f"preregistered {budget_seconds/60:.0f}-minute budget, after "
                f"{k} of {len(cuts)} fits. The cadence is NOT coarsened to fit "
                "the clock.")
        if verbose:
            print(f"[holdout] {k}/{len(cuts)} {cut.key} "
                  f"n_train={row['n_training_matches']} "
                  f"fixtures={row['n_fixtures']} "
                  f"warn={len(warns)} {row['fit_seconds']}s "
                  f"(elapsed {elapsed/60:.1f}m)", flush=True)

    out = {
        "window": "holdout", "seasons": list(windows.EXCLUDED_SEASONS),
        "n_cutoffs": len(cuts),
        "n_fixtures": int(sum(r["n_fixtures"] for r in rows)),
        "n_refitted_now": int(sum(p["refitted_now"] for p in per_fit)),
        "seconds": round(time.time() - started, 1),
        "total_fit_seconds": round(sum(r["fit_seconds"] for r in rows), 1),
        "median_fit_seconds": float(np.median([r["fit_seconds"] for r in rows])),
        "n_training_matches_range": [min(r["n_training_matches"] for r in rows),
                                     max(r["n_training_matches"] for r in rows)],
        "cutoffs_with_warnings": [p["key"] for p in per_fit if p["advi_warnings"]],
        "distinct_warnings": sorted({w for p in per_fit
                                     for w in p["advi_warnings"]}),
        "cold_start_events": [{"cutoff": p["cutoff"], "clubs": p["cold_start_teams"]}
                              for p in per_fit if p["cold_start_teams"]],
        "n_cutoffs_with_a_provisional_club": sum(
            1 for p in per_fit if p["provisional_teams"]),
        "unpriceable_fixtures": 0,
        "per_fit": per_fit,
        "ledger": str(LEDGER_PATH),
    }
    WARNINGS_PATH.write_text(json.dumps(out, indent=2, default=str) + "\n")
    return out


# ==========================================================================
# 2. the holdout score — the rule of §5.2, executed
# ==========================================================================
def _mde80(sd: float, n: int) -> float:
    """80%-power two-sided MDE for a paired mean; the package's one constant."""
    return float(2.802 * sd / np.sqrt(n))


def score_holdout(matches: pd.DataFrame | None = None, n_boot: int = 10_000,
                  ) -> dict[str, Any]:
    """Score the 380 once, apply §5.2, and report everything §9 asks for."""
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    walk = improve.score_walk(LEDGER_PATH, matches=matches, n_boot=n_boot)

    # the same frame the scorer built, so calibration and log loss are on the
    # identical complete case rather than on a re-derived one
    ev = baseline.evaluate(played, freeze.frozen_elo_config(),
                           sorted({r["season"] for r in
                                   (json.loads(l) for l in
                                    LEDGER_PATH.read_text().splitlines() if l.strip())}),
                           require_odds=False)
    frame = ev.frame.copy()
    dc = {str(m): [float(v) for v in p]
          for l in LEDGER_PATH.read_text().splitlines() if l.strip()
          for m, p in zip(json.loads(l)["match_ids"], json.loads(l)["probs"])}
    ids = frame["match_id"].astype(str).to_numpy()
    arr = np.array([dc.get(m, [np.nan] * 3) for m in ids], dtype=float)
    keep = np.isfinite(arr).all(axis=1)
    frame, arr = frame.loc[keep].reset_index(drop=True), arr[keep]
    y = frame["y"].to_numpy()
    elo = frame[[f"elo_{o}" for o in score_mod.OUTCOMES]].to_numpy(float)

    dc_s = score_mod.summarise("dc", arr, y).as_dict()
    elo_s = score_mod.summarise("elo", elo, y).as_dict()
    d = score_mod.rps(arr, y) - score_mod.rps(elo, y)
    lo, hi, nb = score_mod.block_bootstrap_ci(d, frame["block"].to_numpy(),
                                              n_boot=n_boot)
    dll = score_mod.log_loss(arr, y) - score_mod.log_loss(elo, y)
    llo, lhi, _ = score_mod.block_bootstrap_ci(dll, frame["block"].to_numpy(),
                                               n_boot=n_boot)
    delta = float(d.mean())
    sd = float(d.std(ddof=1))

    thr = float(RULE["mde80_holdout"])
    regression = bool(delta >= thr or lo > 0)
    too_good = bool(delta <= -thr)
    if regression:
        verdict = "REGRESSION"
    elif delta <= 0:
        verdict = "DIRECTIONAL PASS (weak, NOT confirmation)"
    else:
        verdict = "INDETERMINATE"

    calib = {"realised": {o: float((y == k).mean())
                          for k, o in enumerate(score_mod.OUTCOMES)},
             "dc": {o: float(arr[:, j].mean())
                    for j, o in enumerate(score_mod.OUTCOMES)},
             "elo": {o: float(elo[:, j].mean())
                     for j, o in enumerate(score_mod.OUTCOMES)}}

    # --- the pooled three-window estimate (SECONDARY; decides nothing) -------
    # Every input is READ FROM THE ARTIFACT THAT PRODUCED IT rather than
    # transcribed from a report: the tuning window from its own OFF ledger, the
    # confirmatory window from run 1's saved result, the holdout from the lines
    # above. A transcription error would otherwise be invisible.
    tune = improve.score_walk(select.ledger_path(OFF, "tune"), matches=matches,
                              n_boot=1_000)
    run1 = json.loads((paths.FIT_DIR / "walkforward.json").read_text())
    g1 = run1["gaps"]["dc_minus_elo"]
    pooled = _pool([("TUNE 2015/16-2018/19", int(tune["n"]),
                     float(tune["dc_minus_elo"]), float(tune["paired_sd"])),
                    ("CONFIRM 2019/20-2024/25 (run 1)", int(g1["n"]),
                     float(g1["mean"]), float(g1["sd"])),
                    ("HOLDOUT 2025/26", int(len(frame)), delta, sd)])

    out = {
        "window": "HOLDOUT 2025/26 — scored once, never tuned on",
        "n": int(len(frame)), "n_expected": 380,
        "n_dropped_incomplete": int(walk["n_dropped"]),
        "odds_read": False,
        "scores": {"dc": dc_s, "elo": elo_s},
        "delta_H": delta, "paired_sd": sd,
        "se": float(sd / np.sqrt(len(d))),
        "ci95_week": [lo, hi], "n_blocks": int(nb),
        "realised_mde80": _mde80(sd, len(d)),
        "delta_H_log_loss": float(dll.mean()),
        "ci95_week_log_loss": [llo, lhi],
        "delta_S_stack_minus_frozen_stack": 0.0,
        "delta_S_note": ("identically 0.000000 by construction: nothing was "
                         "adopted, so the final stack IS the frozen stack and "
                         "the two forecasters are the same object, not two "
                         "objects that happen to agree"),
        "rule": RULE,
        "verdict": verdict,
        "regression_guard_fired": regression,
        "too_good_guard_fired": too_good,
        "calibration": calib,
        "per_season": walk["per_season"],
        "pooled_three_window_secondary": pooled,
        "cross_check_score_walk": {k: walk[k] for k in
                                   ("dc_rps", "elo_rps", "dc_minus_elo",
                                    "paired_sd", "ci95_week", "n_blocks",
                                    "dc_log_loss", "n", "spec")},
    }
    RESULT_PATH.write_text(json.dumps(out, indent=2, default=str) + "\n")
    return out


def _pool(windows_: list[tuple[str, int, float, float]]) -> dict[str, Any]:
    """Inverse-variance pool of the same paired quantity on disjoint fixtures.

    SECONDARY, and flagged as such: the three inputs have different provenance
    (the tuning window chose the Elo hyperparameters in an earlier phase; the
    confirm window has been read once), so this is reported for its precision
    and enters no pass rule.
    """
    rows = [{"window": w, "n": n, "delta": dl, "paired_sd": s,
             "se": float(s / np.sqrt(n))} for w, n, dl, s in windows_]
    wts = np.array([1.0 / r["se"] ** 2 for r in rows])
    est = float(np.sum(wts * np.array([r["delta"] for r in rows])) / wts.sum())
    se = float(np.sqrt(1.0 / wts.sum()))
    return {"inputs": rows, "pooled_delta": est, "pooled_se": se,
            "ci95_normal": [est - 1.96 * se, est + 1.96 * se],
            "n_total": int(sum(r["n"] for r in rows)),
            "mde80": float(2.802 * se),
            "status": "SECONDARY — reported for precision, decides nothing"}


# ==========================================================================
# 3. the SECOND LOOK at the confirmatory window
# ==========================================================================
def second_look_confirm(n_boot: int = 10_000) -> dict[str, Any]:
    """Re-score 2019/20-2024/25 from run 1's ledger. Every number is a SECOND LOOK.

    No fit is run: v2 §6's condition for executing a second look is that the
    final stack DIFFERS from the stack run 1 already scored there, and it does
    not. What this produces is therefore run 1's own answer recomputed from its
    committed forecasts — deterministic, because the bootstrap seed is fixed —
    together with the two contrasts §6 requires of any differing stack, both of
    which are degenerate here and are reported as such rather than omitted.
    """
    ledger = walkforward.load_ledger(walkforward.LEDGER_PATH)
    res = walkforward.score_run(ledger=ledger, n_boot=n_boot)
    frame = res.pop("frame")
    g = res["gaps"]["dc_minus_elo"]
    return {
        "LABEL": "SECOND LOOK — 2019/20-2024/25, declared and conditional",
        "executed_a_new_fit": False,
        "why": ("the final stack is bit-identical to the stack run 1 scored on "
                "this window, so a re-fit would reproduce run 1 exactly; that "
                "is the same look recomputed, not a second test"),
        "n": res["n_matches"],
        "n_cutoffs_in_ledger": len(ledger),
        "scores": res["scores"],
        "stack_minus_elo": {"mean": g["mean"], "sd": g["sd"],
                            "ci95_week": g["week"]["ci95"],
                            "n_blocks_week": g["week"]["n_blocks"],
                            "ci95_season": g["season"]["ci95"],
                            "log_loss_mean": g["log_loss"]["mean"],
                            "log_loss_ci95_week": g["log_loss"]["week"]["ci95"]},
        "stack_minus_market": {
            "mean": res["gaps"]["dc_minus_market"]["mean"],
            "ci95_week": res["gaps"]["dc_minus_market"]["week"]["ci95"]},
        "elo_minus_market": {
            "mean": res["gaps"]["elo_minus_market"]["mean"],
            "ci95_week": res["gaps"]["elo_minus_market"]["week"]["ci95"]},
        "stack_minus_frozen_stack": 0.0,
        "stack_minus_frozen_stack_note": (
            "identically zero on all 2,280: the same configuration, hence the "
            "same forecasts. This is the contrast v2 §6 calls 'far better "
            "powered', and it is uninformative precisely because nothing was "
            "adopted."),
        "verdict_under_v1_rule": res["verdict"],
        "verdict_if_blocked_by_season": res["verdict_if_blocked_by_season"],
        "per_season": res["per_season"],
        "subsets": res["subsets"],
        "calibration": res["calibration"],
        "diagnostics": res["diagnostics"],
        "stops": res["stops"],
        "realised_paired_sd": res["realised_paired_sd_dc_vs_elo"],
        "realised_mde80": res["realised_mde_80pct"],
        "multiplicity_acknowledged": (
            "this window is NOT blind with respect to the selection phase: I2 "
            "and I3 were designed after reading run 1's promoted-club subset "
            "and its calibration/over-confidence finding, so a nominal 95% "
            "interval computed here is not a 95% interval"),
    }


# ==========================================================================
# 4. the ablation — what each lever was worth, individually and cumulatively
# ==========================================================================
def ablation(n_boot: int = 10_000, matches: pd.DataFrame | None = None,
             ) -> dict[str, Any]:
    """Execute the adoption rule again and report every lever's contribution.

    The adopted set is EMPTY, so the ablation that a reader wants — each
    adopted improvement's contribution on held-out data, individually and
    cumulatively — is identically zero and there is nothing to remove. What
    exists instead, and is published in full here, is the contribution each
    candidate WOULD have made on the window where it was measured: the tuning
    objective. Those are the losers, and publishing them is the point.
    """
    matches = baseline.load_matches() if matches is None else matches
    trace = select.selection_trace(window="tune", n_boot=n_boot, matches=matches)
    steps = []
    for st in trace["steps"]:
        v = st.get("verdict") or {}
        steps.append({
            "gate": st["gate"], "best_point": st.get("best"),
            "delta_tune": v.get("delta"),
            "delta_tune_log_loss": v.get("delta_log_loss"),
            "seasons_improved": v.get("seasons_improved"),
            "ci95_week": v.get("ci95_week"), "mde80": v.get("mde80"),
            "A": v.get("A_beats_threshold"), "B1": v.get("B1_curve_shape"),
            "B1_note": v.get("B1_note"), "B2": v.get("B2_seasons"),
            "B3": v.get("B3_log_loss_agrees"),
            "B4": v.get("B4_above_noise_floor"), "ADOPT": v.get("ADOPT"),
            "candidates": [{"spec": c["spec"], "delta": c.get("delta"),
                            "rps": c.get("challenger_rps"),
                            "seasons_improved": c.get("seasons_improved")}
                           for c in st["candidates"]],
        })
    out = {
        "adopted": [],
        "cumulative_stack_after_each_step": ["off"] * len(steps),
        "final_stack": trace["final_spec"],
        "noise_floor": trace.get("noise_floor"),
        "threshold": select.ADOPTION_RULE["threshold"],
        "steps": steps,
        "holdout_contribution_of_each_adopted_improvement": (
            "not applicable: the adopted set is empty, so every adopted "
            "improvement's individual and cumulative contribution on the "
            "holdout is 0.000000 by construction, and no ablation arm exists "
            "to remove"),
        "why_no_holdout_ablation_of_the_rejected_levers": (
            "scoring a rejected lever on 2025/26 would touch the holdout more "
            "than once and would let a variant that failed the tuning window "
            "be re-tried on fresh data — selection on the holdout, which v2 "
            "§5.4 forbids in the same sentence that grants the single touch"),
    }
    ABLATION_PATH.write_text(json.dumps(out, indent=2, default=str) + "\n")
    return out


# ==========================================================================
# 5. CLI
# ==========================================================================
def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--assert-frozen", action="store_true")
    ap.add_argument("--canary", action="store_true")
    ap.add_argument("--walk", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--second-look", action="store_true")
    ap.add_argument("--ablation", action="store_true")
    ap.add_argument("--n-boot", type=int, default=10_000)
    args = ap.parse_args()

    if args.assert_frozen:
        print(json.dumps(assert_stack_is_frozen(), indent=2))
    if args.canary:
        print(json.dumps(walkforward.point_in_time_canary(), indent=2))
    if args.walk:
        assert_stack_is_frozen()
        out = run_holdout()
        out.pop("per_fit")
        print(json.dumps(out, indent=2, default=str))
    if args.score:
        out = score_holdout(n_boot=args.n_boot)
        print(json.dumps({k: v for k, v in out.items()
                          if k not in ("rule", "per_season")},
                         indent=2, default=str))
    if args.second_look:
        out = second_look_confirm(n_boot=args.n_boot)
        CONFIRM_PATH.write_text(json.dumps(out, indent=2, default=str) + "\n")
        print(json.dumps({k: v for k, v in out.items()
                          if k not in ("per_season", "diagnostics", "subsets",
                                       "calibration")},
                         indent=2, default=str))
    if args.ablation:
        out = ablation(n_boot=args.n_boot)
        for s in out["steps"]:
            print(f"{s['gate']:32s} best={s['best_point']} "
                  f"delta={s['delta_tune']} ADOPT={s['ADOPT']}")
        print("FINAL STACK:", out["final_stack"])


if __name__ == "__main__":
    _cli()
