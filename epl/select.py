"""SELECTION. Tune the gated improvements on 2014/15-2018/19 and nowhere else.

WHAT THIS MODULE IS. :mod:`epl.improve` built five gates and proved that with
every gate off it is byte-identical to the frozen configuration. It deliberately
ran no sweep and made no adoption decision. This module runs the sweep, on the
TUNING window only, and records every specification it tried — including the
ones it rejected — so that the final stack can be read as a decision rather than
as a search that stopped when it found a number it liked.

THE WINDOW RULE IS THE POINT. 2015/16-2018/19 (1,520 matches) is the tuning
objective. 2019/20-2024/25 has been scored once already and any further look
there is a SECOND LOOK. 2025/26 is a fresh holdout that must be touched exactly
once, at the end. :func:`run_sweep` defaults to ``window="tune"`` and calls
``windows.assert_tuning_only`` on the frame it actually built, so a mis-sliced
frame fails loudly instead of quietly widening the window.

ONE FIT, MANY FORECASTS — AND WHY THAT IS A DESIGN CHOICE, NOT AN OPTIMISATION.
``Improvements.touches_the_fit()`` splits the gates in two. I1a (decay) and I4
(congestion) change the panel or the design, so each needs its own fit. I2
(break widening) and I3 (home term) act only at predict time, so every one of
them can be evaluated against the SAME posterior. Doing it that way is cheaper,
but the reason it is done is that it makes the comparison exact: two predict-time
variants scored off one posterior differ by the lever and by nothing else, with
zero ADVI optimiser noise between them. A variant that needs its own fit does NOT
get that, and its gain must therefore be read against the measured seed-replica
noise floor (:func:`noise_floor`), which is why the floor is measured here rather
than assumed.

WHAT IS RECORDED. One JSONL ledger per variant, in exactly the row schema
``epl.improve.run_walk`` writes, so ``epl.improve.score_walk`` scores them
unchanged and nothing about the scoring path is special-cased for this module.
Every row carries the variant spec, the window, and the fit arm it shared, so two
ledgers can never be silently pooled.

NO BETTING. Nothing here reads or produces a price.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from epl import anchor as anchor_mod
from epl import baseline, dcfit, fit as epl_fit, freeze, improve, paths
from epl import score as score_mod, walkforward, windows
from epl.improve import Improvements, OFF
from epl.schema import sort_for_walk_forward

__all__ = [
    "ADOPTION_RULE", "PREDICT_GRID", "DECAY_GRID", "fit_arm", "compose",
    "run_sweep", "ledger_path", "score_variant", "compare", "tuning_mde",
    "noise_floor", "adopt",
]

# ==========================================================================
# 0. THE ADOPTION RULE — written here BEFORE the first sweep was run
# ==========================================================================
#: The decision procedure, fixed in code before any tuning number existed. It is
#: in this module rather than in prose because a rule that lives only in a report
#: can be rewritten to match the answer; this one is executed by :func:`adopt`,
#: so the report and the arithmetic cannot drift apart.
#:
#: The sweep writes nothing outside ``data/`` (gitignored), so the presence of
#: this constant in the committed source is checkable evidence of the ordering:
#: the rule is part of the same file that produced the numbers.
ADOPTION_RULE: dict[str, Any] = {
    "objective": (
        "mean normalised (halved) three-outcome RPS over the tuning objective "
        "seasons 2015/16-2018/19, n = 1,520, every fixture priced, complete "
        "case. Secondary: mean natural-log loss, reported on every row, "
        "entering the decision ONLY through the sign-agreement condition B3."),
    "comparison": (
        "PAIRED, challenger minus current stack, restricted to the fixtures "
        "BOTH priced, so a variant can never be scored on an easier subset "
        "than the stack it is challenging. Negative = the challenger is "
        "better."),
    "threshold": -0.0010,
    "why_that_threshold": [
        "0.0010 RPS is 13% of the measured Elo-to-market headroom (0.0077) and "
        "15% of the gap the model still owes the market (0.0065). A lever "
        "worth less than that cannot move the question this probe asks.",
        "It is more than ten times the ADVI seed noise measured on run 1's "
        "headline mean (0.000075 over 2,280 matches), and the same noise is "
        "re-measured on THIS window by noise_floor() rather than assumed.",
        "It is BELOW the tuning window's own DC-versus-Elo MDE (about 0.0029 "
        "at n = 1,520 and a paired SD near 0.040). This is stated as a "
        "limitation, not hidden: a gain at this threshold is NOT established "
        "by the tuning window, which is exactly the position promoted_offset "
        "was in (0.00131 against an MDE of 0.00415) and it was adopted on "
        "curve shape plus independent replication, not on the raw gap. The "
        "conditions below are that same standard of evidence.",
    ],
    "conditions_all_required": {
        "A": "delta <= -0.0010 on the tuning objective.",
        "B1": (
            "CURVE SHAPE. For a continuous dial the chosen point must be an "
            "interior optimum of the swept grid, or an endpoint reached "
            "monotonically whose NEIGHBOUR also beats the incumbent by at "
            "least half the threshold. No adoption off an isolated point. "
            "A BINARY gate (I4 congestion) has no curve and is judged on A, "
            "B2, B3 and — being fit-touching — B4; that exemption is stated "
            "here rather than discovered when it becomes convenient. "
            "COMPLETING a dial is allowed and EXTENDING one is not: if the "
            "winning point sits on a dial whose interior was not swept, the "
            "missing INTERIOR point may be run to test the shape, because it "
            "lies between values already swept. Adding a value beyond the "
            "grid's ends after seeing results would be shopping and is "
            "forbidden."),
        "B2": (
            "SEASON STABILITY. The sign must hold in at least 3 of the 4 "
            "tuning seasons. Declared in advance, on the same objective; this "
            "is a robustness condition, not a search for a favourable slice."),
        "B3": "SIGN AGREEMENT. Mean log loss must move the same way as RPS.",
        "B4": (
            "NOISE FLOOR, for fit-touching gates only (I1a, I4: they re-run "
            "ADVI over a changed panel or design). |delta| must exceed 3x the "
            "measured |seed-replica delta| on this same objective. I2 and I3 "
            "act at predict time and share their arm's posterior exactly, so "
            "no optimiser noise separates them from their control and B4 does "
            "not apply."),
    },
    "order": [
        "GREEDY FORWARD SELECTION in a fixed order, decided before any tuning "
        "number was seen: I1a (decay) -> I4 (congestion) -> I3 (home term) -> "
        "I2 (break widening).",
        "WHY THIS ORDER. Gates that change the FIT are settled first, so that "
        "every predict-time gate is tuned against the posterior it will "
        "actually wrap rather than against a posterior the final stack will "
        "not use. Within each tier the order is by expected magnitude: "
        "recency weighting is the largest lever in the literature; congestion "
        "is the weakest fit-level candidate but must still be settled before "
        "the predict-time gates because it changes the posterior.",
        "Each step compares the BEST point of that gate's grid against the "
        "current stack. If no point satisfies every condition, the gate is "
        "REJECTED and the stack is unchanged. That is the default.",
    ],
    "not_eligible": {
        "I1b": (
            "REFIT CADENCE is measured for the record and cannot be adopted. "
            "The preregistered weekly walk is already the finest cadence the "
            "day-resolution feature layer supports, so the only reachable "
            "direction is staler, i.e. worse. It is run once at cadence 2 to "
            "put a number on what staleness costs, and that number can only "
            "ever be a cost."),
        "I1c": (
            "A genuine time-varying-strength state was not built (see "
            "epl.improve): it is a different likelihood, not a gated variant "
            "of this model."),
        "I5": "Managerial change: investigated against the live source and dropped.",
    },
    "multiplicity": (
        "The sweep evaluates on the order of 30 specifications on one window "
        "with a threshold below that window's MDE. That is a SCREEN, not a "
        "test: its outputs are hypotheses about which levers are worth "
        "carrying to a held-out window, and the anti-domain-shopping ledger "
        "in the report lists every specification tried, adopted or not."),
}

# ==========================================================================
# 1. the grids, declared here so the anti-domain-shopping ledger is in code
# ==========================================================================
#: I2/I3 settings evaluated at EVERY fit arm. They cost one predict pass each
#: and share the arm's posterior exactly, so their comparison against the arm's
#: own control carries no optimiser noise at all.
#:
#: The grid is fixed BEFORE any tuning number is seen and it is not extended
#: afterwards. Three points on each dial plus the zero point is what "the curve
#: has a shape" needs; a two-point dial cannot distinguish an interior optimum
#: from a monotone drift and would license adoption off a single gap.
PREDICT_GRID: tuple[dict[str, Any], ...] = (
    {},                                                              # control
    # --- I3: how fast the league home term is allowed to move ---------------
    {"home_term_blend": 0.5, "home_term_half_life_days": 90.0},
    {"home_term_blend": 1.0, "home_term_half_life_days": 90.0},
    {"home_term_blend": 1.0, "home_term_half_life_days": 180.0},
    # --- I2: how much to widen after a squad break --------------------------
    {"break_widen_strength": 0.10, "break_widen_half_life_matches": 3.0},
    {"break_widen_strength": 0.20, "break_widen_half_life_matches": 3.0},
    {"break_widen_strength": 0.35, "break_widen_half_life_matches": 3.0},
    {"break_widen_strength": 0.20, "break_widen_half_life_matches": 6.0},
    {"break_widen_strength": 0.20, "break_widen_half_life_matches": 3.0,
     "break_widen_january": True},
)

#: I1a values swept at stage 1. 365 is the shipped value and is the OFF arm
#: (``decay_half_life_days=None`` writes nothing), so it appears here as None.
DECAY_GRID: tuple[float | None, ...] = (None, 270.0, 180.0, 120.0)


def fit_arm(imp: Improvements) -> Improvements:
    """``imp`` with every predict-time gate stripped: what determines the FIT.

    Two variants with the same fit arm can and must share one posterior. The
    stripped fields are set back to their dataclass defaults rather than merely
    zeroed, so the arm of a variant is a function of the variant alone and two
    arms compare equal iff they really do produce the same fit.
    """
    return replace(imp,
                   break_widen_strength=0.0,
                   break_widen_half_life_matches=3.0,
                   break_widen_january=False,
                   home_term_blend=0.0,
                   home_term_half_life_days=120.0)


def compose(arm: Improvements, over: dict[str, Any]) -> Improvements:
    """One predict-grid point applied on top of a fit arm."""
    return replace(arm, **over)


# ==========================================================================
# 2. a pass-through posterior view
# ==========================================================================
class _SharedView(dcfit.ColdStartPosterior):
    """A per-variant view of ONE fitted posterior.

    ``improve.Forecaster`` rebinds ``post._cfg`` when I2 is on (it deep-copies
    before swapping the per-fixture widening strength). That is contained when
    the Forecaster owns its posterior, which is true of ``improve.fit_improved``
    and false here, where one posterior is shared by every variant in the pass.
    This view gives each variant its own attribute namespace over the SAME
    arrays: ``__dict__`` is copied, the ``idata`` inside it is not. It overrides
    nothing, so ``predict_1x2`` through a view is bit-identical to
    ``predict_1x2`` on the base — asserted at the first cutoff of every pass by
    :func:`_assert_view_is_inert`, not assumed.
    """

    def __init__(self, base: dcfit.ColdStartPosterior):
        self.__dict__.update(base.__dict__)


def _assert_view_is_inert(post: dcfit.ColdStartPosterior,
                          pairs: Sequence[tuple[str, str]]) -> None:
    view = _SharedView(post)
    a = np.array([[post.predict_1x2(h, x, neutral=False)[k]
                   for k in score_mod.OUTCOMES] for h, x in pairs])
    b = np.array([[view.predict_1x2(h, x, neutral=False)[k]
                   for k in score_mod.OUTCOMES] for h, x in pairs])
    if not np.array_equal(a, b):
        raise AssertionError(
            "the shared-posterior view changed the forecast; every variant in "
            "this pass would then be measuring the view as well as its lever")


# ==========================================================================
# 3. the sweep
# ==========================================================================
def ledger_path(imp: Improvements, window: str = "tune",
                seed: int | None = None) -> Path:
    """One file per (variant, window, seed). Under ``data/``, gitignored."""
    name = f"{window}_{imp.label()}"
    if seed is not None:
        name += f"_seed{int(seed)}"
    return improve.IMPROVE_DIR / f"{name}.jsonl"


def run_sweep(arm: Improvements = OFF,
              grid: Sequence[dict[str, Any]] = PREDICT_GRID,
              window: str = "tune", second_look: bool = False,
              holdout: bool = False, seed: int | None = None,
              matches: pd.DataFrame | None = None, resume: bool = True,
              limit: int | None = None, verbose: bool = True,
              fast_panel: bool = True) -> dict[str, Any]:
    """Walk ONE fit arm across ``window``, pricing every predict-grid variant.

    The fit happens once per cutoff. Each grid point is then a wrapper over that
    one posterior, so the whole grid costs one fit plus one cheap predict pass
    per point, and every within-pass comparison is free of optimiser noise.

    Resumable at pass granularity: a cutoff is refitted only if at least one
    variant is missing it. Partial rows are never mixed, because a variant's
    ledger is appended to only after that variant has priced the whole block.
    """
    if fit_arm(arm) != arm:
        raise ValueError(
            f"{arm.spec} carries predict-time gates; a fit ARM must not. Pass "
            "the arm and let the grid supply I2/I3.")
    seasons = improve._resolve_seasons(window, second_look, holdout)
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    frame = played.loc[played["season"].isin(seasons)]
    if window == "tune":
        windows.assert_tuning_only(frame["season"], "the selection frame")

    variants = [compose(arm, over) for over in grid]
    cfg = improve.wcmodel_config(arm)
    if seed is not None:
        cfg["seed"] = int(seed)
        cfg["elo"]["epl_anchor_spec"] += f"/seed={int(seed)}"
    cadence = improve.cadence_weeks(arm)
    cuts = walkforward.matchweek_cutoffs(played, score_seasons=seasons,
                                         cadence=cadence,
                                         allow_excluded=(window == "holdout"))
    if limit:
        cuts = cuts[:limit]

    anc = anchor_mod.Anchor(played, freeze.frozen_elo_config())
    store = epl_fit.build_store(played)
    # I2's break epochs are baked into the clock at construction, so a variant
    # asking for the January break and one that is not CANNOT share a clock. One
    # per flag, built only if some variant wants it.
    clocks = {j: improve.BreakClock(played, january=j)
              for j in sorted({v.break_widen_january for v in variants if v.i2})}
    rest = improve.RestSchedule(played) if arm.i4 else None
    model_hl = float(cfg["windows"]["decay_half_life_days"])

    improve.IMPROVE_DIR.mkdir(parents=True, exist_ok=True)
    paths_by_spec = {v.spec: ledger_path(v, window, seed) for v in variants}
    done: dict[str, set[str]] = {}
    for spec, p in paths_by_spec.items():
        done[spec] = set()
        if resume and p.exists():
            done[spec] = {json.loads(l)["key"]
                          for l in p.read_text().splitlines() if l.strip()}

    todo = [c for c in cuts
            if any(c.key not in done[v.spec] for v in variants)]
    if verbose:
        print(f"[select] arm={arm.spec} seed={seed} window={window} "
              f"{len(variants)} variants, {len(cuts)} cutoffs, "
              f"{len(todo)} to fit", flush=True)

    home = played["home_key"].astype(str).to_numpy()
    away = played["away_key"].astype(str).to_numpy()
    dates = pd.to_datetime(played["date"]).to_numpy()
    started = time.time()
    ctx = epl_fit.config_read_once(cfg) if fast_panel else walkforward._null_context()
    checked = False
    with ctx:
        for i, cut in enumerate(todo, 1):
            t0 = time.perf_counter()
            post, res = dcfit.fit_epl(cut.cutoff, store, anc, cfg,
                                      matches=played,
                                      feature_cache_dir=paths.FIT_CACHE_DIR)
            fit_seconds = time.perf_counter() - t0
            block = list(zip(cut.match_ids, home[cut.rows], away[cut.rows],
                             dates[cut.rows]))
            if not checked:
                pairs = [(h, a) for _, h, a, _ in block
                         if h in post._idx and a in post._idx][:5]
                _assert_view_is_inert(post, pairs)
                checked = True

            shift = improve.home_term_shift  # bound once, read below
            for v in variants:
                if cut.key in done[v.spec]:
                    continue
                view: Any = _SharedView(post)
                hs = 0.0
                if v.i3:
                    hs = shift(played, cut.cutoff, v, model_hl)
                    view = improve.HomeShiftedPosterior(view, hs)
                fc = improve.Forecaster(
                    view, v, cut.cutoff,
                    clock=clocks.get(v.break_widen_january), rest=rest)
                probs, unpriceable = [], []
                for mid, h, a, dt in block:
                    if h not in view._idx or a not in view._idx:
                        probs.append([float("nan")] * 3)
                        unpriceable.append({"match_id": mid, "home": h,
                                            "away": a})
                        continue
                    p = fc.predict_1x2(h, a, date=pd.Timestamp(dt))
                    probs.append([float(p[k]) for k in score_mod.OUTCOMES])
                arr = np.asarray(probs, dtype=float)
                row = {
                    "key": cut.key, "season": cut.season,
                    "matchweek": cut.matchweek,
                    "cutoff": str(cut.cutoff.date()),
                    "spec": v.spec, "improvements": v.as_dict(),
                    "window": window, "second_look": bool(window == "confirm"),
                    "holdout": bool(window == "holdout"),
                    "seed": seed, "fit_arm": arm.spec,
                    "shared_fit": True,
                    "cadence_weeks": int(cadence),
                    "off_protocol": bool(cadence != walkforward.CADENCE_WEEKS),
                    "n_fixtures": len(cut.match_ids),
                    "match_ids": list(cut.match_ids),
                    "probs": [[round(x, 8) for x in r] for r in arr.tolist()],
                    "fit_seconds": round(fit_seconds, 2),
                    "n_training_matches": res.n_training_matches,
                    "n_teams": res.n_teams,
                    "cold_start_teams": res.cold_start_teams,
                    "provisional_teams": res.provisional_teams,
                    "home_shift": float(hs),
                    "unpriceable": unpriceable,
                }
                with paths_by_spec[v.spec].open("a") as fh:
                    fh.write(json.dumps(row, default=str) + "\n")
            if verbose and (i % 10 == 0 or i == len(todo)):
                el = time.time() - started
                print(f"[select] {i}/{len(todo)} {cut.key} "
                      f"fit {fit_seconds:.1f}s (elapsed {el/60:.1f}m, "
                      f"eta {el/i*(len(todo)-i)/60:.1f}m)", flush=True)

    return {"arm": arm.spec, "seed": seed, "window": window,
            "n_variants": len(variants), "n_cutoffs": len(cuts),
            "n_fitted": len(todo), "seconds": round(time.time() - started, 1),
            "ledgers": {s: str(p) for s, p in paths_by_spec.items()}}


# ==========================================================================
# 4. scoring and the adoption arithmetic
# ==========================================================================
def _probs(path: Path | str) -> tuple[str, dict[str, list[float]], list[str]]:
    rows = [json.loads(l) for l in Path(path).read_text().splitlines()
            if l.strip()]
    if not rows:
        raise ValueError(f"{path} is empty")
    specs = sorted({r["spec"] for r in rows})
    if len(specs) != 1:
        raise ValueError(f"{path} mixes variants {specs}")
    seasons = sorted({r["season"] for r in rows})
    out: dict[str, list[float]] = {}
    for r in rows:
        for m, p in zip(r["match_ids"], r["probs"]):
            out[str(m)] = [float(v) for v in p]
    return specs[0], out, seasons


def score_variant(path: Path | str, matches: pd.DataFrame | None = None,
                  n_boot: int = 10_000) -> dict[str, Any]:
    """One variant against walk-forward Elo on the same fixtures. No odds."""
    return improve.score_walk(path, matches=matches, n_boot=n_boot)


def tuning_mde(paired_sd: float, n: int, power: float = 0.80) -> float:
    """Two-sided alpha = 0.05 minimum detectable effect for a paired mean.

    ``2.802`` is ``z(0.975) + z(0.80)``. The same constant
    ``epl.walkforward.score_run`` uses, so the tuning and confirmatory windows
    quote MDEs on one convention.
    """
    if power != 0.80:
        raise ValueError("only the 80% power constant is pinned here")
    return float(2.802 * paired_sd / np.sqrt(n))


def compare(challenger: Path | str, incumbent: Path | str,
            matches: pd.DataFrame | None = None, n_boot: int = 10_000,
            ) -> dict[str, Any]:
    """The adoption arithmetic: challenger minus incumbent, paired, on TUNE.

    Both ledgers are reduced to the fixtures BOTH priced, so a variant can never
    be scored on an easier subset than the stack it is challenging. Negative
    ``delta`` means the challenger is better.
    """
    spec_a, pa, seasons_a = _probs(challenger)
    spec_b, pb, seasons_b = _probs(incumbent)
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    seasons = sorted(set(seasons_a) & set(seasons_b))
    ev = baseline.evaluate(played, freeze.frozen_elo_config(), seasons,
                           require_odds=False)
    frame = ev.frame.copy()
    ids = frame["match_id"].astype(str).to_numpy()

    A = np.array([pa.get(m, [np.nan] * 3) for m in ids], dtype=float)
    B = np.array([pb.get(m, [np.nan] * 3) for m in ids], dtype=float)
    keep = np.isfinite(A).all(axis=1) & np.isfinite(B).all(axis=1)
    frame, A, B = frame.loc[keep].reset_index(drop=True), A[keep], B[keep]
    y = frame["y"].to_numpy()

    ra, rb = score_mod.rps(A, y), score_mod.rps(B, y)
    la, lb = score_mod.log_loss(A, y), score_mod.log_loss(B, y)
    elo = frame["elo_rps"].to_numpy()
    d = ra - rb
    lo, hi, nb = score_mod.block_bootstrap_ci(d, frame["block"].to_numpy(),
                                              n_boot=n_boot)
    per_season = (frame.assign(a=ra, b=rb)
                  .groupby("season")
                  .agg(n=("match_id", "size"), a=("a", "mean"),
                       b=("b", "mean"))
                  .assign(delta=lambda t: t["a"] - t["b"])
                  .reset_index().to_dict(orient="records"))
    sd = float(d.std(ddof=1))
    return {
        "challenger": spec_a, "incumbent": spec_b, "seasons": seasons,
        "n": int(len(frame)),
        "challenger_rps": float(ra.mean()), "incumbent_rps": float(rb.mean()),
        "elo_rps": float(elo.mean()),
        "challenger_minus_elo": float((ra - elo).mean()),
        "incumbent_minus_elo": float((rb - elo).mean()),
        "delta": float(d.mean()), "paired_sd": sd,
        "se": float(sd / np.sqrt(len(d))),
        "mde80": tuning_mde(sd, len(d)),
        "ci95_week": [lo, hi], "n_blocks": int(nb),
        "delta_log_loss": float((la - lb).mean()),
        "challenger_log_loss": float(la.mean()),
        "incumbent_log_loss": float(lb.mean()),
        "seasons_improved": int(sum(1 for r in per_season if r["delta"] < 0)),
        "per_season": per_season,
    }


def noise_floor(control: Path | str, replica: Path | str,
                matches: pd.DataFrame | None = None) -> dict[str, Any]:
    """How far the tuning objective moves when ONLY the ADVI seed changes.

    The number every fit-touching gate (I1a, I4) has to clear before its gain
    can be called a lever rather than an optimiser. Predict-time gates (I2, I3)
    share their arm's posterior exactly and are not subject to it.
    """
    out = compare(replica, control, matches=matches, n_boot=2_000)
    return {
        "control": out["incumbent"], "replica": out["challenger"],
        "n": out["n"],
        "control_rps": out["incumbent_rps"], "replica_rps": out["challenger_rps"],
        "delta_rps_from_seed_alone": out["delta"],
        "abs_delta": abs(out["delta"]),
        "paired_sd": out["paired_sd"],
        "mean_abs_per_match_prob_shift": None,
    }


def adopt(cmp: dict[str, Any], *, touches_the_fit: bool, floor: float,
          shape_ok: bool, shape_note: str = "") -> dict[str, Any]:
    """Execute :data:`ADOPTION_RULE` on one challenger-versus-stack comparison.

    Returns the verdict AND every condition's own answer, so a rejected variant
    records WHY it was rejected instead of merely disappearing.
    """
    thr = float(ADOPTION_RULE["threshold"])
    a = bool(cmp["delta"] <= thr)
    b2 = bool(cmp["seasons_improved"] >= 3)
    b3 = bool(np.sign(cmp["delta_log_loss"]) == np.sign(cmp["delta"])
              or cmp["delta_log_loss"] == 0.0 == cmp["delta"])
    b4 = True if not touches_the_fit else bool(abs(cmp["delta"]) > 3.0 * floor)
    ok = bool(a and shape_ok and b2 and b3 and b4)
    return {
        "spec": cmp["challenger"], "delta": cmp["delta"],
        "delta_log_loss": cmp["delta_log_loss"],
        "seasons_improved": cmp["seasons_improved"],
        "paired_sd": cmp["paired_sd"], "mde80": cmp["mde80"],
        "ci95_week": cmp["ci95_week"],
        "A_beats_threshold": a, "B1_curve_shape": bool(shape_ok),
        "B1_note": shape_note, "B2_seasons": b2, "B3_log_loss_agrees": b3,
        "B4_above_noise_floor": b4, "noise_floor_used": (floor if
                                                         touches_the_fit else None),
        "ADOPT": ok,
    }


def dial_shape(points: Sequence[tuple[float, float]], threshold: float,
               ) -> tuple[bool, str]:
    """B1 on one dial. ``points`` = (dial value, delta vs incumbent), any order.

    The incumbent's own point (delta 0 at its own dial value) must be included
    by the caller — a dial's shape is only meaningful with the zero point on it.
    """
    pts = sorted(points)
    if len(pts) < 3:
        return False, (f"only {len(pts)} points on this dial; a shape needs "
                       "three, so B1 cannot be established")
    deltas = [d for _, d in pts]
    j = int(np.argmin(deltas))
    if 0 < j < len(pts) - 1:
        return True, (f"interior optimum at {pts[j][0]:g}, flanked by "
                      f"{pts[j-1][1]:+.5f} and {pts[j+1][1]:+.5f}")
    side = deltas[1:] if j == 0 else deltas[:-1][::-1]
    monotone = all(b >= a for a, b in zip(side, side[1:]))
    nb = deltas[1] if j == 0 else deltas[-2]
    if monotone and nb <= threshold / 2.0:
        return True, (f"endpoint optimum at {pts[j][0]:g}, approached "
                      f"monotonically, neighbour {nb:+.5f} also beats half "
                      "the threshold")
    return False, (f"endpoint optimum at {pts[j][0]:g}: "
                   f"monotone={monotone}, neighbour {nb:+.5f} "
                   f"(needs <= {threshold/2:+.5f})")


def _step(name: str, challengers: Sequence[Improvements],
          stack: Improvements, stack_path: Path, window: str,
          dial: str | None, floor: float, n_boot: int,
          matches: pd.DataFrame) -> dict[str, Any]:
    """One greedy step: score every challenger, apply the rule to the best."""
    thr = float(ADOPTION_RULE["threshold"])
    rows = []
    for c in challengers:
        p = ledger_path(c, window)
        if not p.exists():
            rows.append({"spec": c.spec, "status": "NOT RUN", "path": str(p)})
            continue
        cmp = compare(p, stack_path, matches=matches, n_boot=n_boot)
        rows.append({"spec": c.spec, "imp": c.as_dict(), "status": "scored",
                     **{k: cmp[k] for k in
                        ("n", "challenger_rps", "incumbent_rps",
                         "challenger_minus_elo", "incumbent_minus_elo",
                         "delta", "delta_log_loss", "paired_sd", "mde80",
                         "ci95_week", "seasons_improved")},
                     "per_season": cmp["per_season"], "_cmp": cmp,
                     "_imp": c})
    scored = [r for r in rows if r["status"] == "scored"]
    if not scored:
        return {"gate": name, "candidates": rows, "adopted": None,
                "why": "no ledger for this gate"}

    best = min(scored, key=lambda r: r["delta"])
    if dial is None:
        shape_ok, note = True, ("binary gate: no dial, so B1 does not apply "
                                "(see ADOPTION_RULE B1)")
    else:
        chosen = best["_imp"]
        pts = [(_dial_value(stack, dial), 0.0)]           # the incumbent's own
        for r in scored:                                  # point, delta 0
            if _same_dial(r["_imp"], chosen, dial):
                pts.append((_dial_value(r["_imp"], dial), r["delta"]))
        shape_ok, note = dial_shape(pts, thr)

    verdict = adopt(best["_cmp"], touches_the_fit=best["_imp"].touches_the_fit(),
                    floor=floor, shape_ok=shape_ok, shape_note=note)
    for r in rows:
        r.pop("_cmp", None), r.pop("_imp", None)
    return {"gate": name, "dial": dial, "candidates": rows,
            "best": best["spec"], "verdict": verdict,
            "adopted": best["spec"] if verdict["ADOPT"] else None}


#: What a dial reads when the gate is OFF. ``decay_half_life_days=None`` is not
#: "no decay": it is the SHIPPED 365, which is the incumbent's point on that
#: curve and must sit on the curve for the shape test to mean anything.
_DIAL_OFF_VALUE = {"decay_half_life_days": 365.0,
                   "home_term_blend": 0.0,
                   "break_widen_strength": 0.0}


def _dial_value(imp: Improvements, dial: str) -> float:
    v = getattr(imp, dial)
    return float(_DIAL_OFF_VALUE[dial] if v is None else v)


def _same_dial(a: Improvements, b: Improvements, dial: str) -> bool:
    """True iff a and b differ only in ``dial`` (so they lie on one curve)."""
    da, db = a.as_dict(), b.as_dict()
    da.pop(dial), db.pop(dial)
    if dial == "break_widen_strength":       # the strength curve is read at
        da.pop("break_widen_half_life_matches")   # ONE half-life / flag pair,
        db.pop("break_widen_half_life_matches")   # which _step pins via b
        return (da == db
                and a.break_widen_half_life_matches == b.break_widen_half_life_matches
                and a.break_widen_january == b.break_widen_january)
    if dial == "home_term_blend":
        return da == db and a.home_term_half_life_days == b.home_term_half_life_days
    return da == db


def selection_trace(window: str = "tune", n_boot: int = 10_000,
                    matches: pd.DataFrame | None = None,
                    decays: Sequence[float] = tuple(
                        d for d in DECAY_GRID if d is not None),
                    ) -> dict[str, Any]:
    """Execute :data:`ADOPTION_RULE` end to end and return the whole trace.

    Greedy, in the rule's stated order, over whatever ledgers exist. Every
    candidate is recorded with its tuning score whether it was adopted or not:
    that record IS the anti-domain-shopping ledger, and it is produced by the
    same code that made the decision.
    """
    matches = baseline.load_matches() if matches is None else matches
    stack = OFF
    stack_path = ledger_path(stack, window)
    trace: dict[str, Any] = {"window": window,
                             "rule": ADOPTION_RULE,
                             "control": str(stack_path), "steps": []}

    # --- the seed-replica noise floor, measured before any gate is judged ---
    rep = ledger_path(OFF, window, seed=987654)
    floor = 0.0
    if rep.exists():
        nf = noise_floor(stack_path, rep, matches=matches)
        trace["noise_floor"] = nf
        floor = float(nf["abs_delta"])

    # --- step 1: I1a, the decay half-life ----------------------------------
    s = _step("I1a decay_half_life_days",
              [Improvements(decay_half_life_days=float(d)) for d in decays],
              stack, stack_path, window, "decay_half_life_days", floor,
              n_boot, matches)
    trace["steps"].append(s)
    if s["adopted"]:
        stack = next(Improvements(decay_half_life_days=float(d))
                     for d in decays
                     if Improvements(decay_half_life_days=float(d)).spec
                     == s["adopted"])
        stack_path = ledger_path(stack, window)

    # --- step 2: I4, congestion (binary) -----------------------------------
    s = _step("I4 congestion", [replace(stack, congestion=True)], stack,
              stack_path, window, None, floor, n_boot, matches)
    trace["steps"].append(s)
    if s["adopted"]:
        stack = replace(stack, congestion=True)
        stack_path = ledger_path(stack, window)

    # --- step 3: I3, the home term -----------------------------------------
    i3 = [compose(stack, o) for o in PREDICT_GRID if "home_term_blend" in o]
    s = _step("I3 home_term_blend", i3, stack, stack_path, window,
              "home_term_blend", floor, n_boot, matches)
    trace["steps"].append(s)
    if s["adopted"]:
        stack = next(v for v in i3 if v.spec == s["adopted"])
        stack_path = ledger_path(stack, window)

    # --- step 4: I2, break widening ----------------------------------------
    i2 = [compose(stack, o) for o in PREDICT_GRID
          if "break_widen_strength" in o]
    s = _step("I2 break_widen_strength", i2, stack, stack_path, window,
              "break_widen_strength", floor, n_boot, matches)
    trace["steps"].append(s)
    if s["adopted"]:
        stack = next(v for v in i2 if v.spec == s["adopted"])
        stack_path = ledger_path(stack, window)

    trace["final_stack"] = stack.as_dict()
    trace["final_spec"] = stack.spec
    trace["final_ledger"] = str(stack_path)
    if stack_path.exists():
        trace["final_vs_elo"] = {
            k: v for k, v in score_variant(stack_path, matches=matches,
                                           n_boot=n_boot).items()
            if k != "per_season"}
    return trace


# ==========================================================================
# 5. CLI
# ==========================================================================
def _arm_from_args(a) -> Improvements:
    return Improvements(decay_half_life_days=a.decay,
                        refit_cadence_weeks=a.cadence,
                        congestion=a.congestion)


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--window", default="tune",
                    choices=sorted(improve._WINDOWS))
    ap.add_argument("--second-look", action="store_true")
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--decay", type=float, default=None)
    ap.add_argument("--cadence", type=int, default=None)
    ap.add_argument("--congestion", action="store_true")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--control-only", action="store_true",
                    help="price only the arm's own control variant")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--trace", action="store_true",
                    help="execute ADOPTION_RULE over the ledgers on disk")
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--compare", nargs=2, metavar=("CHALLENGER", "INCUMBENT"))
    ap.add_argument("--score", type=str, default=None, metavar="LEDGER")
    ap.add_argument("--n-boot", type=int, default=10_000)
    args = ap.parse_args()

    if args.sweep:
        grid = ({},) if args.control_only else PREDICT_GRID
        print(json.dumps(run_sweep(_arm_from_args(args), grid=grid,
                                   window=args.window,
                                   second_look=args.second_look,
                                   holdout=args.holdout, seed=args.seed,
                                   limit=args.limit), indent=2))
    if args.trace:
        tr = selection_trace(window=args.window, n_boot=args.n_boot)
        text = json.dumps(tr, indent=2, default=str)
        if args.out:
            Path(args.out).write_text(text + "\n")
        for st in tr["steps"]:
            v = st.get("verdict") or {}
            print(f"{st['gate']:32s} best={st.get('best')} "
                  f"delta={v.get('delta')} ADOPT={v.get('ADOPT')}")
        print("FINAL STACK:", tr["final_spec"])
        if not args.out:
            print(text)
    if args.compare:
        out = compare(args.compare[0], args.compare[1], n_boot=args.n_boot)
        out.pop("per_season", None)
        print(json.dumps(out, indent=2))
    if args.score:
        out = score_variant(args.score, n_boot=args.n_boot)
        out.pop("per_season", None)
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    _cli()
