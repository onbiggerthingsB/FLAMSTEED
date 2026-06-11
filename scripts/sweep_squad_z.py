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
  * REPORT (ADDENDUM-2 evidence, on the POOLED 113 held-out matches): a per-k
    table (overall RPS, the has_squad=0-involving slice RPS, n, max_favorite per
    cell) + the five pre-registered evidence items, evaluated mechanically
    (``wcmodel.backtest.squad_sweep``):
      #1 paired ΔRPS vs k=0 (seeded paired bootstrap).
      #2 BOOTSTRAP SUPPORT — % of resamples favouring k>0 (the verdict gate).
      #3 per-tournament SIGN SPLIT — does WC-2022 agree with Euro-2024 in
         direction? (per-tournament Δ point estimate + support %).
      #4 G2 has_squad=0-slice non-regression (paired-bootstrap CI overlap;
         prereg fixes no numeric tolerance so we use CI overlap and SAY SO here).
      #5 over-anchoring SANITY — no >0.95 single-game favourite (house precedent).
  * DECISION RULE (ADDENDUM-2, on the pooled knee arm's support):
      ADOPT      iff support >= 75% AND G2 holds AND sanity holds.
      NO-LIFT    iff support <  60%  (or a binding gate vetoes a high-support knee).
      60–75%     -> MORNING-CALL (default no-adopt; the harness NEVER adopts here).
    Point estimates alone never adopt — the support threshold is the gate.
  * POWER YARDSTICK (+2 authorized fits): the k_elo 0->0.6 contrast at k_squad=0
    on the SAME 113 matches — the known-real-effect ruler. Reported as a YARDSTICK
    line (dRPS + support); it is CONTEXT ONLY and NEVER affects the verdict.
  * VERDICT: exactly ONE machine-readable line — ``P3SWEEP VERDICT: ADOPT
    k_squad=<k> ...`` | ``P3SWEEP VERDICT: NO-LIFT ...`` | ``P3SWEEP VERDICT:
    MORNING-CALL (support=NN% in [60,75); default no-adopt) ...``.

Cache: each ``(tag, k_elo, k_squad)`` is a distinct ``cfg["model"]`` (the
strength_prior block carries k_att/k_def + k_squad + squad_tag) -> a distinct
posterior cache key, so reruns of an already-fit cell HIT the on-disk cache.
MIN_MATCHED is INHERITED from the data layer (prereg §6: never tuned vs sweep RPS).

PRODUCTION fidelity: each cell is ONE production-grade ADVI fit (advi_iters from
config, NOT coarsened — a coarse fit confounds the calibration). 4 k_squad × 2
cutoffs = 8 sweep cells + 2 YARDSTICK cells (k_elo=0, k_squad=0 at both cutoffs)
= 10 cells. The posterior cache key includes the git sha, so under a fresh branch
every cell is a FRESH fit -> budget 10 fresh fits (tens of min each).

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
from wcmodel.backtest.squad_sweep import (
    MAX_FAVORITE_CEILING,
    SUPPORT_ADOPT,
    SUPPORT_NOLIFT,
    bootstrap_support,
    evaluate_gates,
    paired_bootstrap_delta,
)
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

#: ADDENDUM-2 POWER YARDSTICK (+2 authorized fits): the k_elo 0->0.6 contrast at
#: k_squad=0 on the SAME held-out matches, as the known-real-effect ruler. The
#: yardstick arm fits k_elo=0.0 (a pure-uninformative-anchor model); its contrast
#: vs the k_squad=0 (k_elo=0.6) cell is context ONLY — it never moves the verdict.
K_ELO_YARDSTICK: float = 0.0

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


def _config_for_cell(base_cfg: dict, tag: str, k_squad: float,
                     k_elo: float = K_ELO) -> dict:
    """Deep-copy config with the anchor ON at (``k_elo``, ``k_squad``) for ``tag``.

    k_squad=0.0 (at k_elo=0.6) is the enabled-but-zero-squad case == today's
    Elo-anchored model (byte-identical-off for the squad term). The YARDSTICK arm
    uses k_elo=0.0 (a pure-uninformative anchor mean = the no-Elo model) at
    k_squad=0.0. The squad_tag is always set so the cache key is unambiguous; at
    k_squad=0 the fit reads NO squad data."""
    cfg = copy.deepcopy(base_cfg)
    cfg["model"]["strength_prior"] = {
        "enabled": True, "source": "elo",
        "k_att": float(k_elo), "k_def": float(k_elo),
        "k_squad": float(k_squad), "squad_tag": tag,
    }
    return cfg


def fit_and_score_cell(*, cutoff: str, tag: str, k_squad: float, base_cfg: dict,
                       store, heldout: pd.DataFrame, k_elo: float = K_ELO) -> dict:
    """ONE production-fidelity fit at ``cutoff`` (anchor k_elo, k_squad, tag) ->
    held-out per-match 1X2 RPS arrays.

    Returns ``{overall_rps:[...], slice_rps:[...over has_squad=0-involving matches],
    n_overall, n_slice, n_train, max_train_date, cache_hit, max_favorite}``. The
    has_squad=0 slice (prereg §4(i)): a held-out match where EITHER team is
    uncovered (has_squad=0) in the tag's squad anchor — the coverage-asymmetry
    slice. ``max_favorite`` is the LARGEST single-game favourite probability this
    cell produced on the held-out set (the over-anchoring sanity input — a >0.95
    single-game favourite is a suspected over-anchor)."""
    cfg = _config_for_cell(base_cfg, tag, k_squad, k_elo)
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
    max_favorite = 0.0
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
        # Over-anchoring sanity input: the biggest single-game favourite this cell
        # produced (max over the three 1X2 legs of the most lopsided match).
        max_favorite = max(max_favorite, max(probs.values()))
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
        "max_favorite": float(max_favorite) if overall else float("nan"),
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
          f"{'slice(has_sq=0)_RPS':>19} | {'n_sl':>4} | {'max_fav':>7}")
    print(f"  {'-'*7}-+-{'-'*11}-+-{'-'*4}-+-{'-'*19}-+-{'-'*4}-+-{'-'*7}")
    for c in cells:
        o = np.mean(c["overall_rps"]) if c["overall_rps"] else float("nan")
        s = np.mean(c["slice_rps"]) if c["slice_rps"] else float("nan")
        fav = c.get("max_favorite", float("nan"))
        print(f"  {c['k']:>7.2f} | {o:>11.5f} | {c['n_overall']:>4} | "
              f"{s:>19.5f} | {c['n_slice']:>4} | {fav:>7.3f}")


def _pool_cells(per_tag_cells: dict[str, list[dict]], ks: list[float]) -> list[dict]:
    """Concatenate the per-tournament per-match RPS arrays into POOLED cells (one
    per k over ALL held-out matches — the 113-match set the ADDENDUM-2 evidence
    is read on). The pooled cell's ``max_favorite`` is the MAX across tournaments
    (the most lopsided single-game favourite anywhere = the over-anchoring read)."""
    pooled: list[dict] = []
    for k in ks:
        overall: list[float] = []
        slice_rps: list[float] = []
        favs: list[float] = []
        for cells in per_tag_cells.values():
            c = next((c for c in cells if abs(c["k"] - k) < 1e-9), None)
            if c is None:
                continue
            overall.extend(c["overall_rps"])
            slice_rps.extend(c["slice_rps"])
            if not np.isnan(c.get("max_favorite", float("nan"))):
                favs.append(c["max_favorite"])
        pooled.append({
            "k": k, "overall_rps": overall, "slice_rps": slice_rps,
            "n_overall": len(overall), "n_slice": len(slice_rps),
            "max_favorite": (max(favs) if favs else float("nan")),
        })
    return pooled


def _sign_split(per_tag_cells: dict[str, list[dict]], knee_k: float,
                *, seed: int, n_boot: int) -> dict[str, dict]:
    """ADDENDUM-2 evidence #3: the per-tournament Δ point estimate + support % at
    the pooled knee k (vs that tournament's own k=0 cell). The 'sign split' is
    whether the two tournaments AGREE in direction (both Δ<0 = both favour k>0)."""
    out: dict[str, dict] = {}
    for tag, cells in per_tag_cells.items():
        c0 = next((c for c in cells if abs(c["k"]) < 1e-9), None)
        ck = next((c for c in cells if abs(c["k"] - knee_k) < 1e-9), None)
        if c0 is None or ck is None:
            continue
        d = paired_bootstrap_delta(c0["overall_rps"], ck["overall_rps"],
                                   seed=seed, n_boot=n_boot)
        out[tag] = {"delta": d["delta"], "support": d["support"],
                    "sign": ("k>0" if d["delta"] < 0 else "k=0")}
    return out


def _yardstick(per_tag_yard: dict[str, list[float]],
               per_tag_k0: dict[str, list[float]],
               *, seed: int, n_boot: int) -> dict:
    """ADDENDUM-2 POWER YARDSTICK: the k_elo 0->0.6 contrast at k_squad=0, pooled
    over ALL held-out matches. ``a`` = the k_elo=0 (yardstick) RPS, ``b`` = the
    k_elo=0.6 (k_squad=0 baseline) RPS — so support is the % of resamples favouring
    k_elo=0.6 (the known-real Elo effect). Returns ``{delta, support, n}``."""
    a: list[float] = []     # k_elo=0
    b: list[float] = []     # k_elo=0.6
    for tag in per_tag_yard:
        if tag in per_tag_k0:
            a.extend(per_tag_yard[tag])
            b.extend(per_tag_k0[tag])
    d = paired_bootstrap_delta(a, b, seed=seed, n_boot=n_boot)
    return {"delta": d["delta"], "support": d["support"], "n": len(a)}


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
    print(f"[ADDENDUM-2] decision on POOLED held-out bootstrap SUPPORT (% of "
          f"resamples favouring k>0): ADOPT>={SUPPORT_ADOPT:.0f}% AND G2 AND "
          f"sanity; NO-LIFT<{SUPPORT_NOLIFT:.0f}%; [{SUPPORT_NOLIFT:.0f},"
          f"{SUPPORT_ADOPT:.0f}%)=MORNING-CALL (default no-adopt). Sanity: no "
          f">{MAX_FAVORITE_CEILING:.2f} single-game favourite (over-anchoring).")

    store = step_store()
    seed = int(base_cfg["seed"])

    per_tag_cells: dict[str, list[dict]] = {}
    per_tag_yard: dict[str, list[float]] = {}     # k_elo=0 (yardstick) overall RPS
    per_tag_k0: dict[str, list[float]] = {}       # k_elo=0.6, k_squad=0 overall RPS

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
                  f"max_fav={res['max_favorite']:.3f} "
                  f"(train max {res['max_train_date']} < {spec['cutoff'][:10]})",
                  flush=True)
        per_tag_cells[tag] = cells
        if any(abs(c["k"]) < 1e-9 for c in cells):
            per_tag_k0[tag] = next(c["overall_rps"] for c in cells if abs(c["k"]) < 1e-9)

        # YARDSTICK arm: k_elo=0.0, k_squad=0.0 at this cutoff (same held-out set).
        yres = fit_and_score_cell(cutoff=spec["cutoff"], tag=tag, k_squad=0.0,
                                  base_cfg=base_cfg, store=store, heldout=heldout,
                                  k_elo=K_ELO_YARDSTICK)
        per_tag_yard[tag] = yres["overall_rps"]
        yo = np.mean(yres["overall_rps"]) if yres["overall_rps"] else float("nan")
        print(f"  [YARDSTICK k_elo={K_ELO_YARDSTICK:.2f},k_squad=0.00] "
              f"{'HIT' if yres.get('cache_hit') else 'fit'}  overall_RPS={yo:.5f} "
              f"n={yres['n_overall']}", flush=True)

        _print_table(tag, cells)

    # ---- POOLED evidence over ALL held-out matches (the 113-match set). ----
    pooled = _pool_cells(per_tag_cells, ks)
    n_pool = pooled[0]["n_overall"] if pooled else 0
    print(f"\n[POOLED] {'+'.join(per_tag_cells)} -> {n_pool} held-out matches.")
    _print_table("POOLED", [{**c} for c in pooled])

    try:
        v = evaluate_gates(pooled, seed=seed, n_boot=args.n_boot)
    except ValueError as exc:
        print("\n" + "=" * 78)
        print(f"P3SWEEP VERDICT: NO-LIFT (keep model.strength_prior.k_squad=0.0). "
              f"Reasons: cannot evaluate gates: {exc}.")
        print("=" * 78)
        return 0

    od, sd = v["overall_delta_vs0"], v["slice_delta_vs0"]
    knee_k, support = v["knee_k"], v["support"]
    print(f"\n[POOLED] knee k_squad={knee_k:.2f}  SUPPORT={support:.1f}% "
          f"(% of resamples favouring k>0; evidence #2)")
    print(f"  paired ΔRPS vs k=0 = {od['delta']:+.5f} "
          f"CI95({od['lo95']:+.5f},{od['hi95']:+.5f})  [evidence #1]")
    print(f"  G2(has_sq=0 slice non-regression) = {'PASS' if v['g2_pass'] else 'FAIL'} "
          f"[slice Δvs0={sd['delta']:+.5f} CI({sd['lo95']:+.5f},{sd['hi95']:+.5f})]  "
          f"[evidence #4]")
    print(f"  sanity(no >{MAX_FAVORITE_CEILING:.2f} favourite) = "
          f"{'PASS' if v['sanity_pass'] else 'FAIL'} "
          f"[knee max_fav={v['max_favorite']:.3f}]  [evidence #5]")

    # Evidence #3: per-tournament sign split at the pooled knee.
    split = _sign_split(per_tag_cells, knee_k, seed=seed, n_boot=args.n_boot)
    agree = (len({s["sign"] for s in split.values()}) == 1) if split else False
    print(f"\n[SIGN SPLIT] per-tournament Δ at pooled knee k={knee_k:.2f} "
          f"(evidence #3) — directions {'AGREE' if agree else 'DISAGREE'}:")
    for tag, s in split.items():
        print(f"  {tag:>9}: ΔRPS={s['delta']:+.5f} support={s['support']:.1f}% "
              f"-> favours {s['sign']}")

    # POWER YARDSTICK (context only — NEVER affects the verdict).
    yard = _yardstick(per_tag_yard, per_tag_k0, seed=seed, n_boot=args.n_boot)
    print(f"\n[YARDSTICK] k_elo 0->0.6 (at k_squad=0) on the SAME {yard['n']} "
          f"matches — the known-real-effect ruler; read the k_squad arms against "
          f"this (it NEVER affects the verdict):")
    print(f"  k_elo 0->0.6: dRPS={yard['delta']:+.5f}, support={yard['support']:.1f}%")

    # ---- The single machine-readable verdict line (ADOPT/NO-LIFT/MORNING-CALL). ----
    print("\n" + "=" * 78)
    tags_str = "+".join(per_tag_cells)
    if v["verdict"] == "ADOPT":
        k = v["k"]
        print(f"P3SWEEP VERDICT: ADOPT k_squad={k:.2f} (support={support:.0f}% "
              f">={SUPPORT_ADOPT:.0f}% on pooled held-out 1X2 RPS AND G2 slice "
              f"non-regression AND over-anchoring sanity hold, on {tags_str}). "
              f"Set model.strength_prior.k_squad={k:.2f} + squad_tag per cutoff.")
    elif v["verdict"] == "MORNING-CALL":
        print(f"P3SWEEP VERDICT: MORNING-CALL (support={support:.0f}% in "
              f"[{SUPPORT_NOLIFT:.0f},{SUPPORT_ADOPT:.0f}); default no-adopt) "
              f"k_squad={knee_k:.2f} knee on {tags_str} — the user's call.")
    else:                                           # NO-LIFT
        why = []
        if np.isnan(support) or abs(knee_k) <= 1e-9:
            why.append("knee is k=0 / no support")
        elif support < SUPPORT_NOLIFT:
            why.append(f"support={support:.0f}%<{SUPPORT_NOLIFT:.0f}%")
        else:                                       # high support but a gate vetoed
            if not v["g2_pass"]:
                why.append("G2 slice regressed")
            if not v["sanity_pass"]:
                why.append(f"sanity: >{MAX_FAVORITE_CEILING:.2f} favourite "
                           f"({v['max_favorite']:.3f})")
        print(f"P3SWEEP VERDICT: NO-LIFT (keep model.strength_prior.k_squad=0.0). "
              f"Reasons: {'; '.join(why) or 'no held-out adopted'}.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
