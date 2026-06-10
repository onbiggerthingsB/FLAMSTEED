#!/usr/bin/env python
"""P2c — paired HELD-OUT 1X2 RPS sweep for the per-tier likelihood weight.

OPS-ONLY SCRIPT. Adds NO model/pipeline behaviour — a thin operator harness that fits the
production model at a PAST cutoff under the locked friendly-weight grid and scores 1X2 RPS on
the internationals played STRICTLY AFTER that cutoff (the leakage-guarded held-out set). RPS is
RESULT-vs-prediction — fully OFFLINE: NO Odds API, NO credits.

THE KNOB (the brief's §2c). ``model.likelihood_tier_weights`` multiplies each match's
time-decay likelihood weight by a per-tier importance weight ``w = decay × tier_w[tier]``. Noisy
tiers (friendlies) can be trusted less as a strength measurement. The LOCKED GRID sweeps
``tier_w[friendly] ∈ {0.4, 0.6, 0.8, 1.0}`` with every OTHER tier fixed at 1.0. (The optional
friendly-intercept δ_f on μ is OUT OF SCOPE for tonight's staging — DEFERRED.)

THE ARMS (each a production-fidelity ADVI fit; a distinct non-default ``tier_w`` -> a distinct
posterior cache key, so reruns are free). w=1.0 is the OFF state: the tier block canonicalizes
to absent in the cache key (``cache._normalized_model_for_key``), so the w=1.0 arm is a CACHE
HIT of the existing production posterior — NOT a fresh fit.

THE GATE (the brief's §2c): the objective is TOURNAMENT prediction, so the PRIMARY metric is
held-out 1X2 RPS on NON-FRIENDLY matches ONLY. (All-matches RPS is reported as a SECONDARY
diagnostic row, never the gate.) Comparisons are PAIRED on the identical non-friendly match set
across arms (apples-to-apples). ADOPT only if the BEST candidate w STRICTLY beats w=1.0 beyond a
seeded paired-bootstrap CI (the house adoption pattern from 2a/2b) — i.e. the paired delta
(cand − baseline) is negative AND its 95% upper bound is < 0. Else NO-LIFT.

THE BRIEF'S WARNING (recorded honestly): time-decay and the friendly tier-weight BOTH downweight
old friendlies — the marginal value is RECENT friendlies — so a NULL result is plausible and is
a valid recorded outcome (leave the block off / all-1.0).

LEAKAGE (binding): the fit reads ``store.read(cutoff)`` then ``features.build`` restricts to
``< cutoff``; the scored set is every valid-played international with ``date > cutoff`` — by
construction NEVER in the fit's training window (the ``max_train_date < cutoff`` proof is
asserted). The tier label of a held-out match is a STATIC property of its competition, no future
information.

RUNTIME: up to 4 production-fidelity ADVI fits (advi_iters from config, NOT coarsened); the
w=1.0 arm is a cache hit of production, so ~3 fresh fits. Run detached, poll the log.

USAGE:
    PYTHONPATH=src .venv/bin/python scripts/sweep_tier_weights.py [--cutoff 2024-06-01T00:00:00Z]
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.backtest.baselines import rps
from wcmodel.backtest.headroom import bootstrap_delta_ci
from wcmodel.backtest.odds_ingest import OUTCOMES
from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.features import valid_played_results
import wcmodel.model.cache as _model_cache

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clv_validation import (  # noqa: E402  (script-local import, after sys.path)
    CACHE_DIR,
    _martj42_results_frame,
    get_persistent_store,
)

DEFAULT_CUTOFF = "2024-06-01T00:00:00Z"

#: The LOCKED grid on tier_w[friendly]; every other tier stays 1.0. 1.0 first so the
#: table reads baseline -> candidates and the paired reference is unambiguous.
FRIENDLY_GRID = (1.0, 0.8, 0.6, 0.4)

#: Seeded paired-bootstrap config (house adoption pattern; matches headroom's default).
N_BOOT = 10_000
BOOT_SEED = 0

#: Outcome-letter map for the paired bootstrap rows ({"H"|"D"|"A"}).
_LETTER = {"home": "H", "draw": "D", "away": "A"}


def _result_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


# --------------------------------------------------------------------------- #
# PURE: the non-friendly held-out slice selector (unit-tested).                 #
# --------------------------------------------------------------------------- #
def is_non_friendly(match_type: str) -> bool:
    """The GATE slice: a tournament-relevant (NON-friendly) match. Tournament
    prediction is the objective, so friendlies are EXCLUDED from the primary RPS
    even though their tier weight is what the sweep tunes."""
    return match_type != "friendly"


# --------------------------------------------------------------------------- #
# Config per arm + the held-out set + leakage proof (mirror sweep_altitude.py). #
# --------------------------------------------------------------------------- #
def _config_for_arm(base_cfg: dict, friendly_w: float) -> dict:
    """Production config with ``likelihood_tier_weights`` set for this arm. Only
    ``friendly`` moves; every other tier stays at the byte-identical 1.0 default.
    For w==1.0 the block is the OFF state (canonicalizes to absent in the cache
    key) -> a cache HIT of the existing production posterior."""
    cfg = copy.deepcopy(base_cfg)
    cfg["model"]["likelihood_tier_weights"] = {"friendly": float(friendly_w)}
    return cfg


def _heldout_frame(store, cutoff: str) -> pd.DataFrame:
    played = _martj42_results_frame(store, "2026-06-07T00:00:00Z").copy()
    played["date"] = pd.to_datetime(played["date"])
    ho = played[played["date"] > pd.Timestamp(cutoff[:10])].copy()
    ho["match_type"] = ho["tournament"].map(tiers.match_type)
    return ho.reset_index(drop=True)


def _assert_no_leak(store, cutoff: str) -> pd.Timestamp:
    asof = store.read("results", cutoff=cutoff)
    asof_dates = pd.to_datetime(asof["date"])
    train = valid_played_results(asof.assign(date=asof_dates))
    max_train = pd.to_datetime(train["date"])
    max_train = max_train[max_train < pd.Timestamp(cutoff[:10])].max()
    assert max_train < pd.Timestamp(cutoff[:10]), (
        f"LEAKAGE: training max {max_train} not < cutoff {cutoff[:10]}")
    return max_train


def _fit_arm(store, cutoff: str, cfg_arm: dict):
    inf = cfg_arm["model"]["inference"]
    post, meta = _model_cache.cached_fit(
        cutoff=pd.Timestamp(cutoff), store=store, backend="advi",
        draws=int(inf["draws"]), seed=int(cfg_arm["seed"]),
        advi_iters=int(inf["advi_iters"]), cache_dir=CACHE_DIR, config=cfg_arm,
    )
    return post, bool(meta["cache_hit"])


def _score_arm(post, heldout: pd.DataFrame):
    """Per-fixture forecast + RPS for the arm over the matches the posterior can price
    (both teams in the training set). Returns a list of dicts keyed by match_id with the
    fair 1X2 triple, the realised outcome, the RPS, and the non-friendly slice flag — so
    the caller can PAIR arms on the identical match set and aggregate on the gate slice."""
    known = set(post.teams)
    out = []
    for _, row in heldout.iterrows():
        home, away = str(row["home_team"]), str(row["away_team"])
        if home not in known or away not in known:
            continue
        neutral = bool(row["neutral"])
        outcome = _result_outcome(int(row["home_score"]), int(row["away_score"]))
        try:
            p = post.predict_1x2(home, away, neutral=neutral)
            fair = {o: float(p[o]) for o in OUTCOMES}
        except (KeyError, ValueError):
            continue
        out.append({
            "match_id": str(row.get("match_id", f"{home}|{away}|{row['date']}")),
            "fair": (fair["home"], fair["draw"], fair["away"]),
            "outcome": outcome,
            "rps": rps(fair, outcome),
            "non_friendly": is_non_friendly(str(row["match_type"])),
        })
    return out


def _mean(vals):
    return float(np.mean(vals)) if vals else float("nan")


# --------------------------------------------------------------------------- #
# PURE: paired rows + the ADOPT/NO-LIFT verdict (unit-tested).                  #
# --------------------------------------------------------------------------- #
def _paired_rows(cand_scored: list[dict], base_scored: list[dict], *, non_friendly_only: bool):
    """Paired ``{p_model, p_ref, outcome}`` rows over the matches BOTH arms priced,
    on the gate slice (non-friendly only when requested). ``p_model`` is the
    CANDIDATE arm, ``p_ref`` the w=1.0 baseline — so a NEGATIVE paired delta means
    the candidate BEATS the baseline (lower RPS). Pairing is by ``match_id``."""
    base_by_id = {r["match_id"]: r for r in base_scored}
    rows = []
    for r in cand_scored:
        if non_friendly_only and not r["non_friendly"]:
            continue
        b = base_by_id.get(r["match_id"])
        if b is None:
            continue
        rows.append({"p_model": r["fair"], "p_ref": b["fair"],
                     "outcome": _LETTER[r["outcome"]]})
    return rows


def _verdict(arms: list[dict]) -> tuple[str, str]:
    """The machine-readable P2C VERDICT line + a notes paragraph.

    ``arms``: one dict per grid point with keys ``friendly_w``, ``rps_nonfriendly``,
    ``n_nonfriendly``, and (for the candidates) ``paired`` = the bootstrap_delta_ci
    dict (delta/lo95/hi95) of (cand − w=1.0) on the NON-FRIENDLY slice. The w=1.0 arm
    has ``paired = None`` (it is the reference).

    ADOPT the BEST candidate (lowest non-friendly RPS) ONLY IF it STRICTLY beats
    w=1.0 beyond the paired bootstrap CI: ``paired.delta < 0`` AND ``paired.hi95 < 0``
    (the entire 95% interval of the paired improvement lies below zero). Otherwise
    NO-LIFT — the brief's expected, honestly-recorded null (decay already downweights
    old friendlies). A SUSPICIOUSLY large improvement (delta < -0.02 RPS) flags a
    manual leakage audit before believing it (too-good guard)."""
    baseline = next((a for a in arms if a["friendly_w"] == 1.0), None)
    cands = [a for a in arms if a["friendly_w"] != 1.0 and a.get("paired") is not None]
    scorable = [a for a in cands if not np.isnan(a["rps_nonfriendly"])]
    if baseline is None or not scorable:
        return ("P2C VERDICT: NO-LIFT (insufficient held-out data to judge)",
                "The non-friendly held-out slice could not be scored across the grid "
                "— leave `likelihood_tier_weights` off (all-1.0).")
    best = min(scorable, key=lambda a: a["rps_nonfriendly"])
    pd_ = best["paired"]
    beats = (pd_["delta"] < 0) and (pd_["hi95"] < 0)
    if beats:
        too_good = ("  ⚠ TOO-GOOD: |Δ|>0.02 RPS — audit for leakage/cutoff-alignment "
                    "before believing." if pd_["delta"] < -0.02 else "")
        return (
            f"P2C VERDICT: ADOPT tier_w[friendly]={best['friendly_w']} "
            f"(non-friendly held-out RPS {best['rps_nonfriendly']:.5f} vs "
            f"{baseline['rps_nonfriendly']:.5f}; paired Δ={pd_['delta']:+.5f} "
            f"95%CI[{pd_['lo95']:+.5f},{pd_['hi95']:+.5f}], n={best['n_nonfriendly']})",
            f"tier_w[friendly]={best['friendly_w']} STRICTLY beats 1.0 on the "
            f"non-friendly held-out slice beyond the paired-bootstrap CI.{too_good} "
            "NOTE: the sim's RateBook does not read the likelihood weight (it is a "
            "fit-time term only), so no sim mirroring is required — but the production "
            "posterior must be REFIT at the adopted weight before the bundle regenerates.")
    return (
        "P2C VERDICT: NO-LIFT (no friendly weight strictly beats 1.0 beyond the paired CI)",
        f"best candidate tier_w[friendly]={best['friendly_w']} gave non-friendly Δ="
        f"{pd_['delta']:+.5f} 95%CI[{pd_['lo95']:+.5f},{pd_['hi95']:+.5f}] vs 1.0 — the "
        "interval includes (or sits above) zero. Consistent with the brief's warning that "
        "time-decay already downweights old friendlies, so the marginal value of "
        "re-weighting them is small. Leave `likelihood_tier_weights` off (a valid recorded "
        "outcome).")


# --------------------------------------------------------------------------- #
# PURE: report assembler (unit-tested).                                         #
# --------------------------------------------------------------------------- #
def assemble_report(part: dict, *, cutoff: str, today: str) -> str:
    """Markdown report from the scored arms. ``part`` carries the per-arm rows
    (friendly_w, non-friendly RPS + n, all-matches RPS + n, paired delta/CI), the
    verdict + notes. Pure: dicts in, markdown out."""
    L = []
    L.append("# Phase 2c — Per-Tier Likelihood Weight — Held-out RPS Sweep\n")
    L.append(f"_Generated {today}. Cutoff {cutoff}. OFFLINE (no Odds-API credits). "
             "Lockbox untouched._\n")
    L.append("**Knob:** `model.likelihood_tier_weights` multiplies each match's time-decay "
             "likelihood weight by a per-tier importance weight `w = decay × tier_w[tier]`. "
             "The sweep tunes `tier_w[friendly]` (every other tier fixed at 1.0); the "
             "friendly-intercept δ_f is DEFERRED (out of scope for this staging).\n")
    L.append("**Gate:** the objective is TOURNAMENT prediction, so the PRIMARY metric is "
             "held-out 1X2 RPS on NON-FRIENDLY matches only. All-matches RPS is a SECONDARY "
             "diagnostic. Comparisons are PAIRED on the identical non-friendly set vs the "
             "w=1.0 baseline.\n")
    L.append(f"- Held-out set: valid-played internationals with date > {cutoff[:10]} "
             f"(non-friendly n={part['n_nonfriendly']}; all-matches n={part['n_all']}).\n")

    L.append("## Paired held-out 1X2 RPS (lower = better; PAIRED on the non-friendly set)\n")
    L.append("| tier_w[friendly] | non-friendly RPS | paired Δ vs 1.0 | 95% CI | all-matches RPS |")
    L.append("|---|---|---|---|---|")
    for a in part["arms"]:
        if a.get("paired") is not None:
            pdd = a["paired"]
            dcol = f"{pdd['delta']:+.5f}"
            cicol = f"[{pdd['lo95']:+.5f}, {pdd['hi95']:+.5f}]"
        else:
            dcol, cicol = "— (ref)", "—"
        L.append(f"| {a['friendly_w']} | {a['rps_nonfriendly']:.5f} | {dcol} | {cicol} | "
                 f"{a['rps_all']:.5f} |")
    L.append("")
    L.append("(Δ < 0 = the arm BEATS w=1.0 on the non-friendly slice. ADOPT requires the "
             "best arm's Δ < 0 AND the 95% upper bound < 0 — a strict paired-bootstrap win.)\n")

    L.append("## Verdict\n")
    L.append(f"**{part['verdict']}**\n")
    if part.get("notes"):
        L.append(part["notes"] + "\n")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cutoff", type=str, default=DEFAULT_CUTOFF)
    ap.add_argument("--out", type=str, default="reports/tier_weights_2026-06-10.md")
    args = ap.parse_args(argv)
    cutoff = args.cutoff

    print("=" * 78)
    print("TIER WEIGHTS — held-out 1X2 RPS sweep (OFFLINE, no odds, no credits)")
    print("=" * 78)
    base_cfg = load_config()
    inf = base_cfg["model"]["inference"]
    print(f"[fit] PRODUCTION fidelity: advi_iters={inf['advi_iters']} draws={inf['draws']}")
    store = get_persistent_store()
    max_train = _assert_no_leak(store, cutoff)
    print(f"[leakage] max training date < cutoff = {max_train.date()} (< {cutoff[:10]}). OK")

    heldout = _heldout_frame(store, cutoff)
    print(f"[heldout] {len(heldout)} valid-played internationals after {cutoff[:10]}.")

    scored_by_w: dict[float, list] = {}
    for friendly_w in FRIENDLY_GRID:
        print(f"\n[fit] arm tier_w[friendly]={friendly_w} ...", flush=True)
        cfg_arm = _config_for_arm(base_cfg, friendly_w)
        try:
            post, hit = _fit_arm(store, cutoff, cfg_arm)
        except Exception as exc:  # noqa: BLE001
            print(f"[fit] arm w={friendly_w} ERROR {type(exc).__name__}: {exc} — SKIP",
                  flush=True)
            scored_by_w[friendly_w] = []
            continue
        print(f"[fit] arm w={friendly_w} {'CACHE HIT' if hit else 'fresh'}; "
              f"{len(post.teams)} teams.", flush=True)
        scored_by_w[friendly_w] = _score_arm(post, heldout)
        nf = [m["rps"] for m in scored_by_w[friendly_w] if m["non_friendly"]]
        allm = [m["rps"] for m in scored_by_w[friendly_w]]
        print(f"[score] non-friendly RPS={_mean(nf):.5f} (n={len(nf)})  "
              f"all-matches RPS={_mean(allm):.5f} (n={len(allm)})", flush=True)

    base_scored = scored_by_w.get(1.0, [])
    arm_rows = []
    for friendly_w in FRIENDLY_GRID:
        scored = scored_by_w.get(friendly_w, [])
        nf = [m["rps"] for m in scored if m["non_friendly"]]
        allm = [m["rps"] for m in scored]
        paired = None
        if friendly_w != 1.0 and scored and base_scored:
            rows = _paired_rows(scored, base_scored, non_friendly_only=True)
            if rows:
                paired = bootstrap_delta_ci(rows, n_boot=N_BOOT, seed=BOOT_SEED)
        arm_rows.append({
            "friendly_w": friendly_w,
            "rps_nonfriendly": _mean(nf), "n_nonfriendly": len(nf),
            "rps_all": _mean(allm), "n_all": len(allm),
            "paired": paired,
        })

    verdict, notes = _verdict(arm_rows)
    base_row = next((a for a in arm_rows if a["friendly_w"] == 1.0), arm_rows[0])
    part = {
        "arms": arm_rows,
        "n_nonfriendly": base_row["n_nonfriendly"],
        "n_all": base_row["n_all"],
        "verdict": verdict, "notes": notes,
    }

    print("\n" + "=" * 78)
    print(verdict)
    print("=" * 78)
    md = assemble_report(part, cutoff=cutoff, today="2026-06-10")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"[done] report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
