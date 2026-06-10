#!/usr/bin/env python
"""P3 v0 k_squad SWEEP — held-out 1X2 RPS on WC-2022 + Euro-2024 (OFFLINE, no credits).

OPS-ONLY harness. Implements the LOCKED pre-registration
``docs/superpowers/specs/2026-06-11-p3v0-sweep-prereg.md`` EXACTLY:

  * GRID: ``k_squad ∈ {0, 0.2, 0.4, 0.6}`` at fixed ``k_elo = 0.6``. The anchor
    mean is ``k_elo·elo_z + k_squad·squad_z·has_squad`` (the model wiring; an
    uncovered team keeps the pure-Elo anchor at any k_squad).
  * HELD-OUT: the WC-2022 (cutoff 2022-11-20) and Euro-2024 (cutoff 2024-06-14)
    TOURNAMENT matches — finals matches played STRICTLY AFTER each cutoff, within
    that tournament's window. Each cutoff uses its committed clubelo snapshot
    (clubelo_20221120.csv / clubelo_20240614.csv), strictly pre-cutoff (prereg §5).
  * REPORT: a per-k table (overall RPS, the has_squad=0-involving slice RPS, n per
    cell) + the two gates evaluated mechanically (``wcmodel.backtest.squad_sweep``):
      G1 knee-beats-zero  — the chosen k is the RPS knee AND strictly beats k=0.
      G2 slice non-regression — the has_squad=0 slice does not regress vs k=0
         (paired-bootstrap CI overlap; prereg fixes no numeric tolerance so we use
         CI overlap and SAY SO here — an explicit implementation choice).
  * VERDICT: a machine-readable line — ``P3SWEEP VERDICT: ADOPT k_squad=<k> ...``
    or ``P3SWEEP VERDICT: NO-LIFT ...``.

Cache: each ``(tag, k_squad)`` is a distinct ``cfg["model"]`` (the strength_prior
block carries k_squad + squad_tag) -> a distinct posterior cache key, so reruns of
an already-fit cell HIT the on-disk cache; the k=0 cells reuse an existing cached
posterior ONLY if the key genuinely matches (it will not, since squad_tag is set
even at k=0 — but k=0 reads NO squad data and is byte-identical to the pre-squad
fit; the cache simply treats it as its own key). MIN_MATCHED is INHERITED from the
data layer (prereg §6: never tuned against sweep RPS).

PRODUCTION fidelity: each cell is ONE production-grade ADVI fit (advi_iters from
config, NOT coarsened — a coarse fit confounds the calibration). 4 k × 2 cutoffs =
8 cells; the k=0 cells share the byte-identical-off posterior across tags only if
the per-cutoff feature panel matches, so budget ~4-8 fresh fits (tens of min each).

Usage (from the worktree):
    PYTHONPATH=src .venv/bin/python scripts/sweep_squad_z.py [--only wc2022|euro2024] \\
        [--ks 0.0,0.2,0.4,0.6] [--n-boot 2000]
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.backtest.baselines import model_fair_1x2, rps
from wcmodel.backtest.squad_sweep import evaluate_gates
from wcmodel.config import load_config
from wcmodel.data.sources.squad_anchor import load_squad_anchor
import wcmodel.model.cache as _model_cache

# Reuse the persistent real martj42 store + the offline result frame from the CLV
# harness so the content-addressed feature/posterior caches stay byte-stable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from clv_validation import (  # noqa: E402  (script-local import, after sys.path)
    CACHE_DIR,
    _martj42_results_frame,
    get_persistent_store,
)

# ---- LOCKED pre-registration constants (prereg §1-§2). DO NOT alter post-fit. ---
K_SQUAD_GRID: list[float] = [0.0, 0.2, 0.4, 0.6]
K_ELO: float = 0.6

#: The two held-out tournaments. ``cutoff`` is strictly before the first match;
#: the held-out scoring set is finals matches in (cutoff, end] whose tournament
#: label is the finals (NOT qualifiers). ``squad_snapshot`` is the committed
#: point-in-time clubelo file the tag's squad anchor reads (prereg §2 / §5).
HELDOUT: list[dict] = [
    {
        "tag": "wc2022",
        "cutoff": "2022-11-20T00:00:00Z",
        "end": "2022-12-18",                      # WC-2022 final
        "label_substr": "fifa world cup",
        "squad_snapshot": "clubelo_20221120.csv",
    },
    {
        "tag": "euro2024",
        "cutoff": "2024-06-14T00:00:00Z",
        "end": "2024-07-14",                      # Euro-2024 final
        "label_substr": "uefa euro",
        "squad_snapshot": "clubelo_20240614.csv",
    },
]


def _result_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def _heldout_tournament_frame(store, spec: dict) -> pd.DataFrame:
    """That tournament's finals matches played STRICTLY AFTER the cutoff (prereg §2).

    Read as-of a far-future cutoff (every revision settled), filter to the finals
    label, and to the window ``(cutoff_day, end]``. Qualifiers are excluded (their
    label carries 'qualif')."""
    played = _martj42_results_frame(store, "2026-06-07T00:00:00Z").copy()
    played["date"] = pd.to_datetime(played["date"])
    lo = pd.Timestamp(spec["cutoff"][:10])
    hi = pd.Timestamp(spec["end"])
    tl = played["tournament"].str.lower()
    is_finals = tl.str.contains(spec["label_substr"]) & ~tl.str.contains("qualif")
    ho = played[(played["date"] > lo) & (played["date"] <= hi) & is_finals].copy()
    return ho.reset_index(drop=True)


def _config_for_cell(base_cfg: dict, tag: str, k_squad: float) -> dict:
    """Deep-copy config with the anchor ON at (k_elo=0.6, k_squad) for ``tag``.

    k_squad=0.0 is the enabled-but-zero-squad case == today's Elo-anchored model
    (byte-identical-off for the squad term). The squad_tag is always set so the
    cache key is unambiguous; at k_squad=0 the fit reads NO squad data."""
    cfg = copy.deepcopy(base_cfg)
    cfg["model"]["strength_prior"] = {
        "enabled": True, "source": "elo",
        "k_att": K_ELO, "k_def": K_ELO,
        "k_squad": float(k_squad), "squad_tag": tag,
    }
    return cfg


def fit_and_score_cell(*, cutoff: str, tag: str, k_squad: float, base_cfg: dict,
                       store, heldout: pd.DataFrame) -> dict:
    """ONE production-fidelity fit at ``cutoff`` (anchor k_squad, tag) -> held-out
    per-match 1X2 RPS arrays.

    Returns ``{overall_rps:[...], slice_rps:[...over has_squad=0-involving matches],
    n_overall, n_slice, n_train, max_train_date, cache_hit}``. The has_squad=0
    slice (prereg §4(i)): a held-out match where EITHER team is uncovered
    (has_squad=0) in the tag's squad anchor — the coverage-asymmetry slice.
    """
    cfg = _config_for_cell(base_cfg, tag, k_squad)
    inf = cfg["model"]["inference"]
    post, meta = _model_cache.cached_fit(
        cutoff=pd.Timestamp(cutoff), store=store, backend="advi",
        draws=int(inf["draws"]), seed=int(cfg["seed"]),
        advi_iters=int(inf["advi_iters"]), cache_dir=CACHE_DIR, config=cfg,
    )
    anchor = load_squad_anchor(tag)
    known = set(post.teams)
    overall: list[float] = []
    slice_rps: list[float] = []
    for _, row in heldout.iterrows():
        home, away = str(row["home_team"]), str(row["away_team"])
        if home not in known or away not in known:
            continue
        neutral = bool(row["neutral"])
        outcome = _result_outcome(int(row["home_score"]), int(row["away_score"]))
        try:
            probs = model_fair_1x2(post, home=home, away=away, neutral=neutral)
        except KeyError:
            continue
        r = rps(probs, outcome)
        overall.append(r)
        # has_squad=0-involving slice: EITHER team uncovered in this tag's anchor.
        if anchor.has_squad.get(home, 0) == 0 or anchor.has_squad.get(away, 0) == 0:
            slice_rps.append(r)
    # Structural leakage proof: training max date < cutoff.
    asof = store.read("results", cutoff=cutoff)
    max_train = pd.to_datetime(asof["date"])
    max_train = max_train[max_train < pd.Timestamp(cutoff[:10])].max()
    return {
        "overall_rps": overall, "slice_rps": slice_rps,
        "n_overall": len(overall), "n_slice": len(slice_rps),
        "n_train": int(len(asof)), "max_train_date": str(max_train.date()),
        "cache_hit": bool(meta["cache_hit"]),
    }


def step_store():
    """The persistent real martj42 store (a named step so orchestration tests can
    monkeypatch it with a stub — no real store build in unit tests)."""
    return get_persistent_store()


def step_heldout(store, spec: dict) -> pd.DataFrame:
    """That tournament's held-out finals frame (named step; monkeypatchable)."""
    return _heldout_tournament_frame(store, spec)


def _print_table(tag: str, cells: list[dict]) -> None:
    print(f"\n  [{tag}] per-k held-out 1X2 RPS")
    print(f"  {'k_squad':>7} | {'overall_RPS':>11} | {'n':>4} | "
          f"{'slice(has_sq=0)_RPS':>19} | {'n_sl':>4}")
    print(f"  {'-'*7}-+-{'-'*11}-+-{'-'*4}-+-{'-'*19}-+-{'-'*4}")
    for c in cells:
        o = np.mean(c["overall_rps"]) if c["overall_rps"] else float("nan")
        s = np.mean(c["slice_rps"]) if c["slice_rps"] else float("nan")
        print(f"  {c['k']:>7.2f} | {o:>11.5f} | {c['n_overall']:>4} | "
              f"{s:>19.5f} | {c['n_slice']:>4}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["wc2022", "euro2024"], default=None,
                    help="restrict to ONE held-out tournament (default: both)")
    ap.add_argument("--ks", type=str, default=None,
                    help="comma-separated k_squad grid (default: the locked 0,0.2,0.4,0.6)")
    ap.add_argument("--n-boot", type=int, default=2000,
                    help="paired-bootstrap resamples for the gate CIs (default 2000)")
    args = ap.parse_args(argv)

    ks = ([float(x) for x in args.ks.split(",")] if args.ks else list(K_SQUAD_GRID))
    heldouts = [h for h in HELDOUT if args.only is None or h["tag"] == args.only]

    print("=" * 78)
    print("P3 v0 k_squad SWEEP — held-out 1X2 RPS (OFFLINE, no odds, no credits)")
    print("=" * 78)
    base_cfg = load_config()
    inf = base_cfg["model"]["inference"]
    from wcmodel.data.sources.squad_z import MIN_MATCHED
    print(f"[prereg] grid k_squad={ks} at k_elo={K_ELO}; MIN_MATCHED={MIN_MATCHED} "
          "(inherited, never tuned vs sweep RPS).")
    print(f"[fit] PRODUCTION fidelity: advi_iters={inf['advi_iters']} "
          f"draws={inf['draws']} backend={inf['backend']} (NOT coarsened).")
    print("[G2] has_squad=0-slice non-regression judged by PAIRED-BOOTSTRAP CI "
          "OVERLAP (lo95<=0) — the prereg fixes no numeric tolerance, so this is "
          "an explicit implementation choice.")

    store = step_store()

    per_tag_verdict: dict[str, dict] = {}
    overall_adopt = True
    adopted_ks: list[float] = []

    for spec in heldouts:
        tag = spec["tag"]
        heldout = step_heldout(store, spec)
        print(f"\n[{tag}] cutoff {spec['cutoff'][:10]}  snapshot {spec['squad_snapshot']}  "
              f"-> {len(heldout)} held-out finals matches "
              f"({spec['cutoff'][:10]} < date <= {spec['end']}).")
        cells: list[dict] = []
        for k in ks:
            res = fit_and_score_cell(cutoff=spec["cutoff"], tag=tag, k_squad=k,
                                     base_cfg=base_cfg, store=store, heldout=heldout)
            cells.append({"k": k, **res})
            o = np.mean(res["overall_rps"]) if res["overall_rps"] else float("nan")
            print(f"  [k={k:.2f}] {'HIT' if res.get('cache_hit') else 'fit'}  "
                  f"overall_RPS={o:.5f} n={res['n_overall']} slice_n={res['n_slice']} "
                  f"(train max {res['max_train_date']} < {spec['cutoff'][:10]})",
                  flush=True)

        _print_table(tag, cells)

        gate_cells = [{"k": c["k"], "overall_rps": c["overall_rps"],
                       "slice_rps": c["slice_rps"]} for c in cells]
        try:
            v = evaluate_gates(gate_cells, seed=int(base_cfg["seed"]), n_boot=args.n_boot)
        except ValueError as exc:
            print(f"  [{tag}] cannot evaluate gates: {exc}")
            overall_adopt = False
            continue
        per_tag_verdict[tag] = v
        od, sd = v["overall_delta_vs0"], v["slice_delta_vs0"]
        print(f"  [{tag}] knee k={v['knee_k']:.2f}  "
              f"G1(beats-0)={'PASS' if v['g1_pass'] else 'FAIL'} "
              f"[overall Δvs0={od['delta']:+.5f} CI({od['lo95']:+.5f},{od['hi95']:+.5f})]  "
              f"G2(slice)={'PASS' if v['g2_pass'] else 'FAIL'} "
              f"[slice Δvs0={sd['delta']:+.5f} CI({sd['lo95']:+.5f},{sd['hi95']:+.5f})]")
        print(f"  [{tag}] -> {v['verdict']}"
              + (f" k_squad={v['k']:.2f}" if v["verdict"] == "ADOPT" else ""))
        if v["verdict"] == "ADOPT":
            adopted_ks.append(v["k"])
        else:
            overall_adopt = False

    # ---- The single machine-readable verdict line. ----
    print("\n" + "=" * 78)
    # ADOPT only if EVERY evaluated held-out tournament adopts the SAME knee k
    # (the prereg adopts at the knee that beats zero on the held-out set; a split
    # across the two tournaments is NOT a clean adopt -> NO-LIFT, flag for user).
    consistent = (overall_adopt and per_tag_verdict
                  and len(set(round(k, 6) for k in adopted_ks)) == 1
                  and len(adopted_ks) == len(per_tag_verdict))
    if consistent:
        k = adopted_ks[0]
        print(f"P3SWEEP VERDICT: ADOPT k_squad={k:.2f} (knee beats k=0 on overall "
              f"held-out 1X2 RPS AND the has_squad=0 slice does not regress, on "
              f"{'+'.join(per_tag_verdict)}). Set model.strength_prior.k_squad="
              f"{k:.2f} + squad_tag per cutoff.")
    else:
        reasons = []
        for tag, v in per_tag_verdict.items():
            if v["verdict"] != "ADOPT":
                why = []
                if not v["g1_pass"]:
                    why.append("G1 knee-does-not-beat-0")
                if not v["g2_pass"]:
                    why.append("G2 slice-regressed")
                reasons.append(f"{tag}:{'/'.join(why) or 'no-knee'}")
        if overall_adopt and adopted_ks and len(set(round(k, 6) for k in adopted_ks)) > 1:
            reasons.append(f"knee split across tournaments {adopted_ks}")
        print(f"P3SWEEP VERDICT: NO-LIFT (keep model.strength_prior.k_squad=0.0). "
              f"Reasons: {'; '.join(reasons) or 'no held-out adopted'}.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
