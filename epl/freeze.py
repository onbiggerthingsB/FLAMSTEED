"""Choose the three fixed values on the tuning window, then freeze them.

WHAT IS CHOSEN HERE, AND WHERE IT IS ALLOWED TO LOOK
---------------------------------------------------
Three configuration defects were found while wiring the World Cup model to
Premier League data — an international K factor inherited by accident, promoted
clubs seeded at the division mean, and a hard failure on any club with no prior
league match. Each is fixed in :mod:`epl.anchor` and :mod:`epl.dcfit`; the
numbers those fixes need are chosen HERE, on :data:`epl.windows.TUNE_SEASONS`
and nothing else, and written to ``epl/config_frozen.json`` together with the
whole search that produced them.

THE OBJECTIVE is the same one the Elo baseline was tuned on: mean normalised
RPS of the walk-forward Elo + ordered-logit forecaster over the scored tuning
seasons (2015/16–2018/19, 1,520 matches; 2014/15 is rating burn-in). Using the
Elo objective to choose the MODEL's anchor is deliberate and is the reason the
comparison is not confounded — the anchor and the baseline are then literally
the same rating table, so a Dixon-Coles win cannot be a better rating system
wearing a Bayesian coat. It is also the only objective available at this cost:
selecting these values against the Bayesian model's own out-of-sample score
would need hundreds of ADVI fits per grid point.

THE ANTI-DOMAIN-SHOPPING RECORD. Every specification evaluated is written to
the frozen file, not just the winner — the full grid, the marginal curves, the
two rules that were allowed to lose, and each rejected alternative with the
number that rejected it. A reader can therefore see the search, and can check
whether the winner won by a distance that means anything (mostly it does not,
and that is said out loud).
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from epl import anchor as anchor_mod, baseline, elo as elo_mod, ordlogit
from epl import score as score_mod, walk, windows
from epl.schema import sort_for_walk_forward

__all__ = ["FROZEN_PATH", "tune", "load_frozen", "frozen_elo_config",
           "frozen_wcmodel_config", "K_GRID", "HOME_ADV_GRID",
           "CARRYOVER_GRID", "PROMOTED_OFFSET_GRID", "DEBUT_OFFSET_GRID"]

#: Committed, not gitignored: the freeze must exist in version control BEFORE
#: the scoring run does, or "preregistered" means nothing.
FROZEN_PATH = Path(__file__).resolve().parent / "config_frozen.json"

# --- the grid -------------------------------------------------------------
#: FIX 1. Spans the plausible league range and includes 40 — the international
#: default this probe is replacing — so the defect can be shown to be a defect
#: rather than asserted to be one.
K_GRID = (10.0, 15.0, 20.0, 25.0, 30.0, 40.0)

#: Update-side home advantage. Known not to be identified by this objective
#: (the 1X2 head absorbs any constant shift into its thresholds, since every
#: league match has a home side); carried anyway so the flatness is measured
#: and reported rather than assumed.
HOME_ADV_GRID = (40.0, 60.0, 80.0, 100.0)

#: Summer regression toward the division mean. 1.0 = no regression, i.e. the
#: rule is allowed to lose.
CARRYOVER_GRID = (1.0, 0.85, 0.75)

#: FIX 2. 0.0 = seed promoted clubs AT the division mean, i.e. the defect
#: itself is in the grid and has to be beaten on the data.
PROMOTED_OFFSET_GRID = (0.0, -50.0, -75.0, -100.0, -150.0, -225.0)

#: FIX 3's tunable, swept separately at the chosen configuration: extra points
#: for a club with NO prior match in the archive, over and above the promoted
#: seed. 0.0 = no special case, which is the hypothesis under test.
DEBUT_OFFSET_GRID = (75.0, 0.0, -75.0, -150.0)


# --------------------------------------------------------------------------
# the objective
# --------------------------------------------------------------------------
def _tuning_frame(matches: pd.DataFrame) -> pd.DataFrame:
    frame = matches.loc[matches["season"].isin(windows.TUNE_SEASONS)].copy()
    windows.assert_tuning_only(frame["season"], "the tuning frame")
    return sort_for_walk_forward(frame)


def _objective(frame: pd.DataFrame, cfg: elo_mod.EloConfig) -> dict[str, Any]:
    """Mean RPS of walk-forward Elo + ordered logit over the scored seasons.

    The window guard lives HERE, at the only place a hyperparameter is ever
    given a number, rather than at the callers. A frame carrying a scoring
    season raises instead of quietly widening the search.
    """
    windows.assert_tuning_only(frame["season"], "the objective's frame")
    ev = baseline.evaluate(frame, cfg, windows.TUNE_SCORED, require_odds=False)
    s = ev.scores["elo"]
    return {"n": s.n, "rps": s.rps, "log_loss": s.log_loss,
            "accuracy": s.accuracy}


def _grid(k=K_GRID, h=HOME_ADV_GRID, c=CARRYOVER_GRID, o=PROMOTED_OFFSET_GRID,
          ) -> list[elo_mod.EloConfig]:
    return [elo_mod.EloConfig(k=kk, home_advantage=hh, carryover=cc,
                              promoted_offset=oo)
            for kk, hh, cc, oo in itertools.product(k, h, c, o)]


def _sweep(frame: pd.DataFrame, configs: Iterable[elo_mod.EloConfig],
           verbose: bool = True) -> pd.DataFrame:
    rows, started = [], time.time()
    configs = list(configs)
    for i, cfg in enumerate(configs):
        rows.append({**cfg.as_dict(), **_objective(frame, cfg)})
        if verbose and (i + 1) % 48 == 0:
            print(f"  [{i + 1}/{len(configs)}] best "
                  f"{min(r['rps'] for r in rows):.5f} "
                  f"({time.time() - started:.0f}s)", flush=True)
    return pd.DataFrame(rows)


def _marginal(table: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    """Best achievable RPS at each level of one parameter — the honest curve.

    Reporting the MINIMUM over the other parameters rather than the mean is the
    right summary for a grid search, because that is the number the search
    itself compares.
    """
    return [{"value": float(v), "best_rps": float(g["rps"].min()),
             "median_rps": float(g["rps"].median())}
            for v, g in table.groupby(column, sort=True)]


# --------------------------------------------------------------------------
# rejected specifications, each with the number that rejected it
# --------------------------------------------------------------------------
def _stale_anchor_edge(history: pd.DataFrame) -> np.ndarray:
    """The rating edge ``wcmodel``'s anchor would use: one match stale.

    ``wcmodel.model.strength.team_elo_z`` takes each club's LAST ``elo_pre`` in
    the panel — the rating it carried INTO its most recent match, not the
    rating it carries out of it. That is one match of information behind what
    the Elo baseline uses to price the same fixture. This reconstructs it so
    the cost can be measured instead of argued about.
    """
    n = len(history)
    home = history["home_key"].to_numpy()
    away = history["away_key"].to_numpy()
    pre_h = history["elo_home_pre"].to_numpy(float)
    pre_a = history["elo_away_pre"].to_numpy(float)
    last_pre: dict[str, float] = {}
    edge = np.full(n, np.nan)
    for rows in walk.groups(history["block"].to_numpy()):
        for i in rows:
            h, a = home[i], away[i]
            edge[i] = last_pre.get(h, pre_h[i]) - last_pre.get(a, pre_a[i])
        for i in rows:
            last_pre[home[i]] = pre_h[i]
            last_pre[away[i]] = pre_a[i]
    return edge


def _score_edge(history: pd.DataFrame, edge: np.ndarray,
                want: np.ndarray) -> dict[str, Any]:
    """Score an arbitrary rating edge through the SAME walk-forward head."""
    h = history.copy()
    h["elo_diff_pre"] = edge
    probs, _ = baseline.walk_forward_head(h, want)
    y = score_mod.outcome_codes(h["ftr"].to_numpy())
    keep = want & np.isfinite(probs).all(axis=1)
    idx = np.flatnonzero(keep)
    s = score_mod.summarise("edge", probs[idx], y[idx])
    return {"n": s.n, "rps": s.rps, "log_loss": s.log_loss,
            "accuracy": s.accuracy}


def _rejected(frame: pd.DataFrame, chosen: elo_mod.EloConfig,
              table: pd.DataFrame) -> list[dict[str, Any]]:
    """Every alternative specification tried, and why it lost."""
    out: list[dict[str, Any]] = []
    base = _objective(frame, chosen)["rps"]

    def add(name: str, detail: str, rps: float | None, **extra: Any) -> None:
        out.append({"spec": name, "why_rejected": detail,
                    "tune_rps": None if rps is None else round(float(rps), 6),
                    "delta_vs_chosen": None if rps is None
                    else round(float(rps) - base, 6), **extra})

    # --- FIX 1: the K the model would have inherited ----------------------
    # STATED PRECISELY, because the loose version flatters the fix. An EPL
    # match falls through `tiers.match_type` to the 'other' bucket, whose
    # multiplier is 0.5, so the NOMINAL K it inherits is 40 * 0.5 = 20 — which
    # is also the K this search chose. The inherited number is therefore not
    # wrong; it is unjustified, and it is unjustified in a way that would move
    # silently if that table were ever edited. Both readings are scored: the
    # bare k_base, and the multiplier's own effect.
    add("K = 40 (wcmodel k_base with the 'other' multiplier removed)",
        "not what an EPL match actually receives today — recorded because "
        "'k_base: 40' is the number in the shipped config and a reader will "
        "look for it",
        _objective(frame, chosen.replace(k=40.0))["rps"])
    add("K = 20 inherited (wcmodel k_base 40 x k_by_match_type['other'] 0.5)",
        "this IS the nominal K an EPL match receives today, and it coincides "
        "with the chosen value: Fix 1 buys nothing in the number, only in the "
        "number's provenance and in the anchor now being the same rating "
        "table the Elo baseline prices with. wcmodel's Elo additionally "
        "multiplies every update by a margin-of-victory index (mean 1.25 on "
        "this archive), which this package's Elo does not, so the effective "
        "update scale differs even where the nominal K does not",
        _objective(frame, chosen.replace(k=20.0))["rps"])
    for k in K_GRID:
        if k != chosen.k:
            add(f"K = {k:g}", "beaten at the chosen (H, carryover, offset)",
                _objective(frame, chosen.replace(k=k))["rps"])

    # --- FIX 2: the promoted seed, including the defect itself -------------
    for off in PROMOTED_OFFSET_GRID:
        if off != chosen.promoted_offset:
            why = ("seeds a promoted club AT the division mean — the defect "
                   "this fix exists to remove; kept in the grid so it had to "
                   "lose on data") if off == 0.0 else \
                  "beaten at the chosen (K, H, carryover)"
            add(f"promoted_offset = {off:g}", why,
                _objective(frame, chosen.replace(promoted_offset=off))["rps"])

    # --- FIX 3: a separate seed for a club new to the archive --------------
    for extra in DEBUT_OFFSET_GRID:
        if extra != 0.0:
            add(f"debut_offset = {extra:g}",
                "a club with no prior match in the archive seeded away from "
                "the ordinary promoted seed; see the debut_sweep block",
                _objective(frame, chosen.replace(debut_offset=extra))["rps"])

    # --- season carryover, allowed to lose --------------------------------
    for c in CARRYOVER_GRID:
        if c != chosen.carryover:
            add(f"carryover = {c:g}",
                "summer regression toward the division mean",
                _objective(frame, chosen.replace(carryover=c))["rps"])

    # --- margin of victory -------------------------------------------------
    add("margin-of-victory multiplier ON",
        "a goal-difference term makes this a different, stronger baseline "
        "wearing the name 'plain Elo'; the published ~0.203 bar is plain Elo, "
        "and the K it needs is not the K without it",
        _objective(frame, chosen.replace(mov=True, k=chosen.k * 7.5))["rps"])

    # --- the anchor's staleness -------------------------------------------
    history, _ = elo_mod.compute_elo_history(frame, chosen)
    want = frame["season"].isin(windows.TUNE_SCORED).to_numpy()
    fresh = _score_edge(history, history["elo_diff_pre"].to_numpy(float), want)
    stale = _score_edge(history, _stale_anchor_edge(history), want)
    add("anchor = last elo_pre (wcmodel.model.strength.team_elo_z)",
        "the rating a club carried INTO its most recent match, i.e. one match "
        "behind the rating the Elo baseline prices with; using it would make "
        "the model's anchor weaker than its own comparator's",
        stale["rps"], fresh_rps=round(fresh["rps"], 6))

    # --- cold start: the alternatives ---------------------------------------
    add("cold start = drop the fixture",
        "the dropped matches are exactly the ones involving the club the model "
        "knows least about, so removing them moves the model's score in its "
        "own favour against a market benchmark that prices them fine; a "
        "comparison run on 'every match except the hard ones' answers a "
        "different question. Rejected on design grounds — deliberately NOT "
        "scored, because scoring it would require the scoring window.",
        None)
    add("cold start = league mean (elo_z = 0, wcmodel's shrink-to-mean)",
        "asserts that a club arriving from the second tier is an average "
        "Premier League club; the promoted-offset sweep in this same file "
        "rejects that claim at the Elo level, and nothing about the Bayesian "
        "head makes it truer",
        _objective(frame, chosen.replace(promoted_offset=0.0))["rps"],
        note="scored via its Elo-level equivalent (promoted_offset = 0), "
             "since the cold-start prior IS the promoted seed placed on the "
             "fitted teams' z-scale")
    return out


# --------------------------------------------------------------------------
# the freeze
# --------------------------------------------------------------------------
def tune(matches: pd.DataFrame, verbose: bool = True) -> dict[str, Any]:
    """Run the whole search on the tuning window and return the freeze record."""
    frame = _tuning_frame(matches)
    started = time.time()

    table = _sweep(frame, _grid(), verbose=verbose)
    ordered = table.sort_values(
        # RPS first, then parsimony — smaller K, less summer regression,
        # smaller seeding intervention, smaller update-side home advantage —
        # so a numerical tie never resolves on row order. home_advantage is in
        # the key because this objective cannot identify it (every league match
        # has a home side, so the 1X2 head absorbs any constant shift into its
        # thresholds); leaving it out would let an unidentified parameter be
        # settled by the order the grid happened to be generated in.
        ["rps", "k", "carryover", "promoted_offset", "home_advantage"],
        ascending=[True, True, False, False, True], kind="mergesort")
    best = ordered.iloc[0]
    chosen = elo_mod.EloConfig(k=float(best["k"]),
                               home_advantage=float(best["home_advantage"]),
                               carryover=float(best["carryover"]),
                               promoted_offset=float(best["promoted_offset"]))

    # FIX 3's own sweep, at the chosen configuration and only there.
    debut = [{"debut_offset": float(x),
              **_objective(frame, chosen.replace(debut_offset=x))}
             for x in DEBUT_OFFSET_GRID]
    debut_best = min(debut, key=lambda r: r["rps"])
    debut_zero = next(r for r in debut if r["debut_offset"] == 0.0)
    # The rule is adopted ONLY if it beats "no special case" by more than the
    # window can resolve. It cannot: see `power` below. Stated as an explicit
    # decision rule evaluated in code, not as a judgement call made afterwards.
    take_debut = (debut_best["debut_offset"] != 0.0
                  and debut_zero["rps"] - debut_best["rps"] > _mde(frame))
    if take_debut:
        chosen = chosen.replace(debut_offset=debut_best["debut_offset"])

    ev = baseline.evaluate(frame, chosen, windows.TUNE_SCORED,
                           require_odds=False)
    seeds = [{k: r[k] for k in ("season", "division_mean", "promoted",
                                "promoted_seed", "debuts", "debut_seed",
                                "mean_after")}
             for r in ev.season_starts]

    record: dict[str, Any] = {
        "objective": ("mean normalised (halved) three-outcome RPS, "
                      "walk-forward Elo + ordered logit"),
        "tune_seasons": list(windows.TUNE_SEASONS),
        "burn_in_seasons": list(windows.TUNE_BURN_IN),
        "objective_seasons": list(windows.TUNE_SCORED),
        "score_seasons_NOT_LOOKED_AT": list(windows.SCORE_SEASONS),
        "excluded_seasons": list(windows.EXCLUDED_SEASONS),
        "n_tuning_matches": int(ev.scores["elo"].n),
        "n_configs": int(len(table)),
        "chosen": chosen.as_dict(),
        "chosen_tune_rps": float(_objective(frame, chosen)["rps"]),
        "grid_best_rps": float(table["rps"].min()),
        "grid_median_rps": float(table["rps"].median()),
        "grid_worst_rps": float(table["rps"].max()),
        "grid_spread_rps": float(table["rps"].max() - table["rps"].min()),
        "tuning_mde_80pct": _mde(frame),
        "marginals": {c: _marginal(table, c)
                      for c in ("k", "home_advantage", "carryover",
                                "promoted_offset")},
        "debut_sweep": debut,
        "debut_rule_adopted": bool(take_debut),
        "season_starts": seeds,
        "rejected": _rejected(frame, chosen, table),
        "grid": ordered.to_dict(orient="records"),
        "seconds": round(time.time() - started, 1),
    }
    record["anchor_spec"] = _anchor_spec(chosen)
    record["wcmodel_config_delta"] = _wcmodel_delta(chosen, matches)
    return record


def _mde(frame: pd.DataFrame) -> float:
    """Smallest paired RPS difference this TUNING window could resolve.

    Two-sided, 80% power, alpha 0.05: ``(1.96 + 0.84) * sd / sqrt(n)``. The sd
    used is the measured paired Elo-versus-market SD on this archive, 0.0577 —
    the only paired SD available before any model is fitted, and the right
    order of magnitude for any two forecasters that agree as often as these do.
    """
    n = int(frame["season"].isin(windows.TUNE_SCORED).sum())
    return round(float(2.802 * 0.0577 / np.sqrt(n)), 5)


def _anchor_spec(cfg: elo_mod.EloConfig) -> str:
    d = cfg.as_dict()
    return ("epl.elo/" + "/".join(f"{k}={d[k]:g}" if isinstance(d[k], float)
                                  else f"{k}={d[k]}"
                                  for k in sorted(d)))


def _wcmodel_delta(cfg: elo_mod.EloConfig, matches: pd.DataFrame,
                   ) -> dict[str, Any]:
    from wcmodel.config import load_config
    base = load_config()
    out = anchor_mod.wcmodel_config(base, cfg, _anchor_spec(cfg))
    return {
        "elo": {k: out["elo"][k] for k in ("k_base", "home_advantage",
                                           "initial_rating",
                                           "k_by_match_type",
                                           "epl_anchor_spec")},
        "effective_k_for_an_epl_match": float(
            out["elo"]["k_base"] * out["elo"]["k_by_match_type"]["other"]),
        "shipped_effective_k": float(
            base["elo"]["k_base"] * base["elo"]["k_by_match_type"]["other"]),
        "mean_mov_multiplier_on_this_archive": round(
            anchor_mod.mean_mov_multiplier(matches.loc[matches["played"]]), 4),
        "note": ("wcmodel's Elo multiplies every update by an unconditional "
                 "margin-of-victory index, which this package's Elo does not, "
                 "so at equal nominal K its updates are that factor larger on "
                 "average. After the anchor substitution the only live "
                 "consumer of wcmodel's Elo is the provisional/volatility arm, "
                 "so the difference changes which clubs get predict-time "
                 "widening and nothing else."),
    }


# --------------------------------------------------------------------------
# reading the freeze back
# --------------------------------------------------------------------------
def load_frozen(path: Path | str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or FROZEN_PATH).read_text())


def frozen_elo_config(path: Path | str | None = None) -> elo_mod.EloConfig:
    return elo_mod.EloConfig(**load_frozen(path)["chosen"])


def frozen_wcmodel_config(base: dict | None = None,
                          path: Path | str | None = None) -> dict:
    """The shipped wcmodel config with the frozen EPL ``elo`` block written in."""
    from wcmodel.config import load_config
    rec = load_frozen(path)
    return anchor_mod.wcmodel_config(copy.deepcopy(base or load_config()),
                                     elo_mod.EloConfig(**rec["chosen"]),
                                     rec["anchor_spec"])


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--out", default=str(FROZEN_PATH))
    args = ap.parse_args()
    if not args.tune:
        ap.error("nothing to do; pass --tune")
    matches = baseline.load_matches()
    record = tune(matches)
    Path(args.out).write_text(json.dumps(record, indent=2, default=str) + "\n")
    print(f"chosen: {record['chosen']}")
    print(f"tune RPS {record['chosen_tune_rps']:.5f}  "
          f"(grid best {record['grid_best_rps']:.5f} / median "
          f"{record['grid_median_rps']:.5f} / worst "
          f"{record['grid_worst_rps']:.5f}) over {record['n_configs']} "
          f"configs in {record['seconds']}s")
    print(f"tuning-window MDE at 80% power: {record['tuning_mde_80pct']}")


if __name__ == "__main__":
    _cli()
