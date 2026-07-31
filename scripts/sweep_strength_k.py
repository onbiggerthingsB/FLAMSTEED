#!/usr/bin/env python
"""Calibrate the Elo strength-anchor `k` by HELD-OUT 1X2 RPS (the MOST ACCURATE k).

OPS-ONLY SCRIPT (Task 5 of the strength-anchored-predictions plan). Adds NO
model/pipeline behaviour — a thin operator harness that, for each candidate `k`,
fits the production model at a PAST cutoff with the Elo att/def anchor switched on
(``model.strength_prior = {enabled: true, source: elo, k_att: k, k_def: k}``) and
scores 1X2 RPS on the internationals played STRICTLY AFTER that cutoff (the
leakage-guarded held-out set). RPS is RESULT-vs-prediction — fully OFFLINE: NO
Odds API, NO credits.

Why this is the right knob and the right metric
-----------------------------------------------
`k` sets the anchor strength: too small -> still flat (Germany ~= Curacao);
too large -> the model collapses toward Elo and ignores match data
(over-confident). We pick `k` empirically by the LOWEST held-out 1X2 RPS — the
most *accurate* forecast, never the most *confident* one. ``k=0.0`` is the
enabled-but-zero-anchor case == today's baseline (the model with the prior
plumbing on but no Elo pull), so the table directly answers "did the anchor help
vs the current model?".

Leakage discipline (binding)
----------------------------
* The fit reads ``store.read(cutoff)`` then ``features.build`` restricts to
  ``< cutoff`` — so ``elo_z`` (and every training row) is strictly pre-cutoff.
* The scored set is every valid-played international with ``date > cutoff`` — by
  construction NEVER in the fit's training window. We assert ``max_train_date <
  cutoff`` per k as the structural proof.
* Each ``(k, cutoff)`` is a DISTINCT posterior cache key (``cfg["model"]`` is
  hashed whole), so reruns of an already-fit k are free.

Runtime
-------
Each k is ONE production-fidelity ADVI fit (``advi_iters`` from
``cfg["model"]["inference"]``, NOT coarsened — a coarse fit collapses the model
toward uniform and would confound the calibration). A fit is minutes; a 3-6 point
grid is 15-40 min. Run it in the background and poll the log.

Usage
-----
    PYTHONPATH=src .venv/bin/python scripts/sweep_strength_k.py [--ks 0.0,0.2,0.4] \\
        [--cutoff 2024-06-01T00:00:00Z]

Prints a table ``k | model_RPS | elo_baseline_RPS | n_matches`` over the held-out
set, plus the chosen k (lowest model RPS that beats k=0 AND matches/beats Elo).
Every RPS printed is the CANONICAL ÷2-normalized value — half the pre-F16 levels
``config/config.yaml``'s ``k_att`` note quotes; see ``SCALE_BANNER`` below.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.backtest.baselines import elo_baseline_1x2, model_fair_1x2, rps
from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.elo import compute_elo_history
from wcmodel.data.features import valid_played_results
import wcmodel.model.cache as _model_cache

# Reuse the persistent real martj42 store + the offline result frame from the CLV
# harness so the content-addressed feature/posterior caches stay byte-stable across
# runs (a 2nd run of an already-fit k HITS the on-disk cache and spends seconds).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from clv_validation import (  # noqa: E402  (script-local import, after sys.path)
    CACHE_DIR,
    _martj42_results_frame,
    get_persistent_store,
)

# The past cutoff for the held-out calibration. Strictly-after-cutoff played
# internationals are the leakage-guarded scoring set (never in the < cutoff fit).
DEFAULT_CUTOFF = "2024-06-01T00:00:00Z"

# COARSE grid first (3 fits) per the runtime budget. The picker flags edge/interior
# so we know whether to refine (interior best -> add a neighbour) or extend (edge).
DEFAULT_KS = [0.0, 0.2, 0.4]

# Printed with the table. The shipped k=0.6 is justified in config.yaml by absolute
# RPS LEVELS recorded before the canonical-RPS consolidation, so a re-run prints half
# of them; unmarked, that reads as a 2x accuracy gain or as the decision failing to
# reproduce. (The picker itself is unaffected — it compares arms with ±1e-9 float-noise
# epsilons, never an absolute threshold.)
SCALE_BANNER = (
    "  SCALE: canonical /2-normalized RPS in [0, 1] (OA finding 16, 2026-07-28).\n"
    "  config/config.yaml's k_att note quotes the PRE-F16 [0, 2] levels 0.359 /\n"
    "  0.340 / 0.333; this table prints their halves (~0.1795 / 0.170 / 0.1665).\n"
    "  Half is the UNIT, not the accuracy — sign, ordering and the k ranking hold."
)


def _result_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def _heldout_frame(store, cutoff: str) -> pd.DataFrame:
    """Valid-played internationals with ``date > cutoff`` (the held-out scoring set).

    Read as-of a far-future cutoff (every revision is settled), then filtered to
    strictly after the calibration cutoff — so the set is disjoint from the fit's
    ``< cutoff`` training window (the leakage guard)."""
    played = _martj42_results_frame(store, "2026-06-07T00:00:00Z")
    played = played.copy()
    played["date"] = pd.to_datetime(played["date"])
    ho = played[played["date"] > pd.Timestamp(cutoff[:10])].copy()
    return ho.reset_index(drop=True)


def _elo_as_of_cutoff(store, cutoff: str, config: dict) -> dict[str, float]:
    """Each team's LATEST pre-cutoff ``rating_pre`` (the Elo-baseline strength).

    The SAME ``compute_elo_history`` the model feature uses, on the ``< cutoff``
    valid-played results (leakage-safe). Returns ``{team: rating}``; a team with no
    pre-cutoff match is absent (the baseline then skips that fixture — it cannot
    score a team it has never rated, exactly like the model)."""
    res = store.read("results", cutoff=cutoff).copy()
    res["date"] = pd.to_datetime(res["date"])
    played = valid_played_results(res)
    played = played[pd.to_datetime(played["date"]) < pd.Timestamp(cutoff[:10])].copy()
    # ``match_type`` drives the Elo K multiplier (same derivation as features.build).
    played["match_type"] = played["tournament"].map(tiers.match_type)
    elo = compute_elo_history(
        played[["match_id", "date", "home_team", "away_team",
                "home_score", "away_score", "neutral", "match_type"]],
        config=config,
    )
    latest = (elo.sort_values("date").groupby("team")["rating_pre"].last())
    return {str(t): float(v) for t, v in latest.items()}


def _config_for_k(base_cfg: dict, k: float) -> dict:
    """A deep copy of the config with the Elo anchor ON at strength ``k``.

    ``k=0.0`` == enabled-but-zero-anchor == today's baseline (prior plumbing on,
    no Elo pull). Each distinct ``k`` is a distinct ``cfg["model"]`` -> a distinct
    posterior cache key, so the sweep never collides and reruns are free."""
    cfg = copy.deepcopy(base_cfg)
    cfg["model"]["strength_prior"] = {
        "enabled": True,
        "source": "elo",
        "k_att": float(k),
        "k_def": float(k),
    }
    return cfg


def _fit_for_k(store, cutoff: str, k: float, cfg_k: dict):
    """One production-fidelity ADVI fit at ``cutoff`` with the anchor at ``k``.

    PRODUCTION ``advi_iters`` (from ``cfg['model']['inference']``) — never
    coarsened. Returns ``(posterior, cache_hit)``."""
    inf = cfg_k["model"]["inference"]
    post, meta = _model_cache.cached_fit(
        cutoff=pd.Timestamp(cutoff),
        store=store,
        backend="advi",
        draws=int(inf["draws"]),
        seed=int(cfg_k["seed"]),
        advi_iters=int(inf["advi_iters"]),
        cache_dir=CACHE_DIR,
        config=cfg_k,
    )
    return post, bool(meta["cache_hit"])


def _assert_no_leak(store, cutoff: str) -> pd.Timestamp:
    """Structural leakage proof: max valid-played training date < the cutoff."""
    asof = store.read("results", cutoff=cutoff)
    asof_dates = pd.to_datetime(asof["date"])
    train = valid_played_results(asof.assign(date=asof_dates))
    max_train = pd.to_datetime(train["date"])
    max_train = max_train[max_train < pd.Timestamp(cutoff[:10])].max()
    assert max_train < pd.Timestamp(cutoff[:10]), (
        f"LEAKAGE: training max {max_train} not < cutoff {cutoff[:10]}")
    return max_train


def _score_k(post, heldout: pd.DataFrame, elo_ratings: dict, config: dict):
    """Mean held-out 1X2 RPS for the model and the Elo baseline over the matches
    BOTH can price (both teams in the posterior's training set AND Elo-rated).

    The scored set is identical across k (same cutoff -> same training teams +
    same Elo ratings), so the model RPS comparison across k is apples-to-apples.
    Returns ``(model_rps, elo_rps, n, n_model_only)``."""
    known = set(post.teams)
    model_rps_vals: list[float] = []
    elo_rps_vals: list[float] = []
    n = 0
    for _, row in heldout.iterrows():
        home, away = str(row["home_team"]), str(row["away_team"])
        if home not in known or away not in known:
            continue
        if home not in elo_ratings or away not in elo_ratings:
            continue
        neutral = bool(row["neutral"])
        outcome = _result_outcome(int(row["home_score"]), int(row["away_score"]))
        try:
            model = model_fair_1x2(post, home=home, away=away, neutral=neutral)
        except KeyError:
            continue
        elo = elo_baseline_1x2(
            rating_home=elo_ratings[home], rating_away=elo_ratings[away],
            neutral=neutral, config=config)
        model_rps_vals.append(rps(model, outcome))
        elo_rps_vals.append(rps(elo, outcome))
        n += 1
    model_rps = float(np.mean(model_rps_vals)) if model_rps_vals else float("nan")
    elo_rps = float(np.mean(elo_rps_vals)) if elo_rps_vals else float("nan")
    return model_rps, elo_rps, n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ks", type=str, default=None,
                    help="comma-separated k grid (default: 0.0,0.2,0.4 — coarse first)")
    ap.add_argument("--cutoff", type=str, default=DEFAULT_CUTOFF,
                    help=f"past calibration cutoff (default {DEFAULT_CUTOFF})")
    args = ap.parse_args(argv)

    ks = ([float(x) for x in args.ks.split(",")] if args.ks else list(DEFAULT_KS))
    cutoff = args.cutoff

    print("=" * 78)
    print("STRENGTH-ANCHOR k CALIBRATION — held-out 1X2 RPS (OFFLINE, no odds, no credits)")
    print("=" * 78)
    base_cfg = load_config()
    inf = base_cfg["model"]["inference"]
    print(f"[fit] PRODUCTION fidelity: advi_iters={inf['advi_iters']} draws={inf['draws']} "
          f"backend={inf['backend']} (NOT coarsened — coarse ADVI confounds calibration).")
    print(f"[cutoff] {cutoff}  ->  scored set = valid-played internationals with date > "
          f"{cutoff[:10]} (leakage-guarded; never in the < cutoff fit).")
    print(f"[grid] k in {ks}  (k=0.0 == enabled-but-zero-anchor == today's baseline)")

    store = get_persistent_store()
    print(f"[store] persistent real martj42 store.")
    max_train = _assert_no_leak(store, cutoff)
    print(f"[leakage] max training date < cutoff = {max_train.date()} (strictly < "
          f"{cutoff[:10]}). Held-out (date > cutoff) is disjoint from train. OK")

    heldout = _heldout_frame(store, cutoff)
    print(f"[heldout] {len(heldout)} valid-played internationals after {cutoff[:10]} "
          f"({heldout['date'].min().date()} .. {heldout['date'].max().date()}).")

    # Elo-as-of-cutoff is k-INDEPENDENT (the cutoff is fixed) -> compute once.
    elo_ratings = _elo_as_of_cutoff(store, cutoff, base_cfg)
    print(f"[elo-baseline] {len(elo_ratings)} teams rated as-of {cutoff[:10]} "
          "(latest pre-cutoff rating_pre; same compute_elo_history as the feature).")

    results: list[dict] = []
    elo_rps_ref: float | None = None
    n_ref: int | None = None
    for k in ks:
        print(f"\n[fit k={k:.2f}] cached_fit at {cutoff} (strength_prior.enabled=True, "
              f"k_att=k_def={k:.2f}) ...", flush=True)
        cfg_k = _config_for_k(base_cfg, k)
        try:
            post, cache_hit = _fit_for_k(store, cutoff, k, cfg_k)
        except Exception as exc:   # noqa: BLE001 — one k erroring must not abort the sweep
            print(f"[fit k={k:.2f}] ERROR: {type(exc).__name__}: {exc} — SKIPPING this k, "
                  "continuing the sweep.", flush=True)
            results.append({"k": k, "model_rps": float("nan"), "elo_rps": float("nan"),
                            "n": 0, "error": f"{type(exc).__name__}: {exc}"})
            continue
        print(f"[fit k={k:.2f}] {'CACHE HIT' if cache_hit else 'fresh fit'}; "
              f"{len(post.teams)} teams in posterior.", flush=True)
        model_rps, elo_rps, n = _score_k(post, heldout, elo_ratings, base_cfg)
        # The Elo baseline + scored-n are k-independent (same cutoff -> same set);
        # capture once for the report (assert stability if a k yielded a set).
        if n:
            if elo_rps_ref is None:
                elo_rps_ref, n_ref = elo_rps, n
        results.append({"k": k, "model_rps": model_rps, "elo_rps": elo_rps, "n": n})
        print(f"[score k={k:.2f}] model_RPS={model_rps:.5f}  elo_RPS={elo_rps:.5f}  n={n}",
              flush=True)

    # --- The table. ---
    print("\n" + "=" * 78)
    print("k-CALIBRATION TABLE — mean held-out 1X2 RPS (lower = better forecast)")
    print(SCALE_BANNER)
    print("=" * 78)
    print(f"  {'k':>6} | {'model_RPS':>10} | {'elo_baseline_RPS':>16} | {'n_matches':>9}")
    print(f"  {'-'*6}-+-{'-'*10}-+-{'-'*16}-+-{'-'*9}")
    for r in results:
        if r.get("error"):
            print(f"  {r['k']:>6.2f} | {'ERROR':>10} | {'ERROR':>16} | {r['n']:>9}  "
                  f"({r['error']})")
        else:
            print(f"  {r['k']:>6.2f} | {r['model_rps']:>10.5f} | {r['elo_rps']:>16.5f} | "
                  f"{r['n']:>9}")

    # --- Pick: lowest model RPS that BEATS k=0 AND matches/beats the Elo baseline. ---
    ok = [r for r in results if not r.get("error") and r["n"] > 0
          and not np.isnan(r["model_rps"])]
    base = next((r for r in ok if abs(r["k"]) < 1e-9), None)
    print("\n" + "=" * 78)
    print("PICK")
    print("=" * 78)
    if base is None:
        print("  [warn] no k=0 baseline row scored — cannot judge 'beats baseline'. "
              "Re-run including k=0.0.")
        return 0
    base_rps = base["model_rps"]
    elo_rps = base["elo_rps"]
    print(f"  k=0 baseline model_RPS = {base_rps:.5f}   |   Elo-baseline RPS = {elo_rps:.5f}")
    candidates = [r for r in ok if r["k"] > 1e-9
                  and r["model_rps"] < base_rps - 1e-9        # (a) beats k=0
                  and r["model_rps"] <= elo_rps + 1e-9]       # (b) matches/beats Elo
    if not candidates:
        improving = [r for r in ok if r["k"] > 1e-9 and r["model_rps"] < base_rps - 1e-9]
        if improving:
            best_imp = min(improving, key=lambda r: r["model_rps"])
            print(f"  [no-ship] best k={best_imp['k']:.2f} beats the k=0 baseline "
                  f"({best_imp['model_rps']:.5f} < {base_rps:.5f}) but does NOT match the Elo "
                  f"baseline ({elo_rps:.5f}). Per the gate, do NOT enable — flag for the user.")
        else:
            print(f"  [no-ship] NO k beat the k=0 baseline ({base_rps:.5f}). The anchor did "
                  "NOT help on this held-out set — leave strength_prior.enabled=false.")
        return 0
    winner = min(candidates, key=lambda r: r["model_rps"])
    edge_pts = [r["k"] for r in ok]
    at_edge = abs(winner["k"] - max(edge_pts)) < 1e-9
    print(f"  [ship] WINNER k={winner['k']:.2f}: model_RPS={winner['model_rps']:.5f} "
          f"< k=0 baseline {base_rps:.5f} (beats baseline) AND <= Elo {elo_rps:.5f} "
          "(matches/beats Elo).")
    if at_edge:
        print(f"  [note] winner is at the grid EDGE (k={winner['k']:.2f}) — consider extending "
              "the grid upward (e.g. --ks {0.0,...,higher}) to confirm it's not still climbing.")
    else:
        print("  [note] winner is an INTERIOR point — optionally refine with a neighbour.")
    print(f"\n  => set config/config.yaml model.strength_prior.k_att=k_def={winner['k']:.2f}, "
          "enabled: true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
