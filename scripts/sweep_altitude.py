#!/usr/bin/env python
"""P2a — paired HELD-OUT 1X2 RPS gate for the acclimatized-altitude covariate.

OPS-ONLY SCRIPT. Adds NO model/pipeline behaviour — a thin operator harness that fits the
production model at a PAST cutoff under three arms and scores 1X2 RPS on the internationals
played STRICTLY AFTER that cutoff (the leakage-guarded held-out set). RPS is RESULT-vs-
prediction — fully OFFLINE: NO Odds API, NO credits.

THE THREE ARMS (each a production-fidelity ADVI fit; distinct ``cfg["model"]`` -> distinct
posterior cache key, so reruns are free):
  - OFF          : ``covariates.enabled = []``                — today's baseline.
  - accl_alt     : ``enabled = ["accl_alt"]``                 — the PRIMARY acclimatized-home
                   term (per-team gap = venue_alt − accustomed_alt). The brief's hypothesis.
  - altitude_m   : ``enabled = ["altitude_m"]``               — the SECONDARY symmetric venue
                   term (already wired; expect possible no-lift, recorded honestly).

THE GATE (the brief's §2a): ADOPT only if held-out RPS IMPROVES on the CONMEBOL-qualifier
slice AND does NOT regress overall. The ON arms supply the per-fixture covariates at predict
time (so the forecast actually uses them); a fixture whose venue city is unknown -> masked ->
the miss intercept fires (consistent with fit).

LEAKAGE (binding): the fit reads ``store.read(cutoff)`` then ``features.build`` restricts to
``< cutoff``; the scored set is every valid-played international with ``date > cutoff`` — by
construction NEVER in the fit's training window (the ``max_train_date < cutoff`` proof is
asserted). The held-out fixture's per-fixture covariate values are STATIC venue properties
(``accl_gap`` off the row's own ``city``), no future information.

RUNTIME: 3 production-fidelity ADVI fits (advi_iters from config, NOT coarsened). ~18 min for
the OFF/accl_alt pair; the altitude_m arm is a 3rd fit. Run detached, poll the log.

USAGE:
    PYTHONPATH=src .venv/bin/python scripts/sweep_altitude.py [--cutoff 2024-06-01T00:00:00Z]
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.backtest.baselines import rps
from wcmodel.backtest.odds_ingest import OUTCOMES
from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.altitude_ref import CITY_ELEVATION_M, accl_gap
import wcmodel.model.cache as _model_cache

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clv_validation import (  # noqa: E402  (script-local import, after sys.path)
    CACHE_DIR,
    _martj42_results_frame,
    get_persistent_store,
)

DEFAULT_CUTOFF = "2024-06-01T00:00:00Z"

# The three arms: (label, enabled list). OFF first so the table reads baseline -> candidates.
ARMS = [
    ("OFF (baseline)", []),
    ("accl_alt (acclimatized-home, PRIMARY)", ["accl_alt"]),
    ("altitude_m (symmetric venue, SECONDARY)", ["altitude_m"]),
]


def _result_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


# --------------------------------------------------------------------------- #
# PURE: the CONMEBOL-qualifier slice selector (unit-tested).                    #
# --------------------------------------------------------------------------- #
def is_conmebol_qualifier(row) -> bool:
    """A WC-qualifier match with BOTH teams in CONMEBOL — the slice the acclimatized-home
    effect should help (the CONMEBOL natural experiment). ``row`` has home_team/away_team
    and a ``match_type`` (``tiers.match_type(tournament)``)."""
    if row.get("match_type") != "wc_qualifier":
        return False
    return (tiers.confederation(str(row["home_team"])) == "CONMEBOL"
            and tiers.confederation(str(row["away_team"])) == "CONMEBOL")


def _fixture_covariates(arm_enabled, city, home, away):
    """Per-fixture covariate dict for an ON arm at predict time (None for the OFF arm).

    accl_alt is PER-TEAM (home gap on ``accl_alt``, away gap on ``accl_alt__away``);
    altitude_m is PER-MATCH (single venue altitude). An unknown city -> NaN -> masked ->
    the miss intercept fires (consistent with fit). The OFF arm supplies nothing (baseline).
    """
    if not arm_enabled:
        return None
    cov = {}
    if "accl_alt" in arm_enabled:
        cov["accl_alt"] = accl_gap(city, home)
        cov["accl_alt__away"] = accl_gap(city, away)
    if "altitude_m" in arm_enabled:
        cov["altitude_m"] = CITY_ELEVATION_M.get(city, float("nan"))
    return cov


# --------------------------------------------------------------------------- #
# Held-out set + leakage proof (mirror sweep_strength_k.py).                    #
# --------------------------------------------------------------------------- #
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


def _config_for_arm(base_cfg: dict, enabled: list) -> dict:
    cfg = copy.deepcopy(base_cfg)
    cfg["model"]["covariates"]["enabled"] = list(enabled)
    return cfg


def _fit_arm(store, cutoff: str, cfg_arm: dict):
    inf = cfg_arm["model"]["inference"]
    post, meta = _model_cache.cached_fit(
        cutoff=pd.Timestamp(cutoff), store=store, backend="advi",
        draws=int(inf["draws"]), seed=int(cfg_arm["seed"]),
        advi_iters=int(inf["advi_iters"]), cache_dir=CACHE_DIR, config=cfg_arm,
    )
    return post, bool(meta["cache_hit"])


def _score_arm(post, heldout: pd.DataFrame, arm_enabled):
    """Per-fixture RPS for the arm over the matches the posterior can price (both teams
    in the training set). Returns ``(per_match: list[dict])`` with rps + slice flags, so
    the caller can aggregate overall and on the CONMEBOL-qualifier slice — the SAME match
    set across arms (apples-to-apples)."""
    known = set(post.teams)
    out = []
    for _, row in heldout.iterrows():
        home, away = str(row["home_team"]), str(row["away_team"])
        if home not in known or away not in known:
            continue
        neutral = bool(row["neutral"])
        city = row.get("city")
        outcome = _result_outcome(int(row["home_score"]), int(row["away_score"]))
        cov = _fixture_covariates(arm_enabled, city, home, away)
        try:
            # predict_1x2 consumes the per-fixture covariates (None for OFF -> baseline,
            # byte-identical to model_fair_1x2). A degenerate grid raises ValueError ->
            # skip that fixture rather than fabricate a forecast.
            p = post.predict_1x2(home, away, neutral=neutral, covariates=cov)
            fair = {o: float(p[o]) for o in OUTCOMES}
        except (KeyError, ValueError):
            continue
        out.append({
            "home": home, "away": away,
            "rps": rps(fair, outcome),
            "is_conmebol_q": is_conmebol_qualifier(row),
            "city_known": (city in CITY_ELEVATION_M),
        })
    return out


def _mean(vals):
    return float(np.mean(vals)) if vals else float("nan")


# --------------------------------------------------------------------------- #
# PURE: report assembler (unit-tested).                                         #
# --------------------------------------------------------------------------- #
def assemble_report(part: dict, *, cutoff: str, today: str) -> str:
    """Markdown report from the scored arms. ``part`` carries: arm rows (label, overall
    RPS, n_overall, conmebol RPS, n_conmebol), coverage %, the OFF baselines, and the
    verdict string. Pure: dicts in, markdown out."""
    L = []
    L.append("# Phase 2a — Altitude Covariate — Held-out RPS Gate\n")
    L.append(f"_Generated {today}. Cutoff {cutoff}. OFFLINE (no Odds-API credits). "
             "Lockbox untouched._\n")
    L.append("**Hypothesis (mechanism honesty):** the acclimatized-home advantage — a "
             "high-altitude home side vs a lowland visitor — measured as the INCREMENT "
             "beyond the model's standard home advantage. PRIMARY = `accl_alt` (per-team "
             "gap `venue_alt − accustomed_alt`); SECONDARY = `altitude_m` (symmetric venue "
             "term, expect possible no-lift).\n")
    L.append(f"- Held-out set: valid-played internationals with date > {cutoff[:10]} "
             f"(n={part['n_overall']}); CONMEBOL-qualifier slice n={part['n_conmebol']}.")
    L.append(f"- Venue-city coverage of the scored set: {part['coverage_pct']:.1f}% "
             "(rows with a known venue elevation; the rest masked, never imputed).\n")

    L.append("## Paired held-out 1X2 RPS (lower = better; SAME match set across arms)\n")
    L.append("| arm | overall RPS | Δ vs OFF | CONMEBOL-q RPS | Δ vs OFF | n_conmebol |")
    L.append("|---|---|---|---|---|---|")
    off = part["arms"][0]
    for a in part["arms"]:
        d_all = a["rps_overall"] - off["rps_overall"]
        d_con = a["rps_conmebol"] - off["rps_conmebol"]
        L.append(f"| {a['label']} | {a['rps_overall']:.5f} | {d_all:+.5f} | "
                 f"{a['rps_conmebol']:.5f} | {d_con:+.5f} | {a['n_conmebol']} |")
    L.append("")
    L.append("(Δ < 0 = the arm IMPROVES on OFF. The gate: CONMEBOL-q Δ < 0 AND overall Δ "
             "≤ 0 for the PRIMARY accl_alt arm.)\n")

    L.append("## Verdict\n")
    L.append(f"**{part['verdict']}**\n")
    if part.get("notes"):
        L.append(part["notes"] + "\n")
    return "\n".join(L)


# Both constants are absolute RPS DIFFERENCES on the canonical ÷2 scale (OA finding 16,
# 2026-07-28): ``rps`` now delegates to ``calibration.rps`` ([0, 1]), and a uniform ÷2
# halves every difference, so the pre-F16 values are re-derived here rather than left to
# silently demand twice the true effect. (The recorded run predates the rescale — see
# reports/altitude_2026-06-10.md, overall RPS 0.332 / CONMEBOL 0.431.)
TOL = 5e-5          # overall-no-regression tolerance (MC noise); = pre-F16 1e-4
TOO_GOOD = -0.01    # CONMEBOL improvement past which we audit for leakage; = pre-F16 -0.02


def _verdict(arms: list[dict]) -> tuple[str, str]:
    """ADOPT only if the PRIMARY accl_alt arm IMPROVES the CONMEBOL-q slice (Δ<0) AND does
    not regress overall (Δ≤~0, a tiny tolerance for MC noise). Else NO-LIFT. Too-good guard:
    a CONMEBOL improvement larger than ~0.01 RPS flags a manual audit."""
    off = arms[0]
    primary = next((a for a in arms if a["enabled"] == ["accl_alt"]), None)
    if primary is None or np.isnan(primary["rps_conmebol"]) or np.isnan(off["rps_conmebol"]):
        return ("NO-LIFT (insufficient data to judge)",
                "The CONMEBOL-qualifier held-out slice could not be scored — leave "
                "`enabled: []`.")
    d_con = primary["rps_conmebol"] - off["rps_conmebol"]
    d_all = primary["rps_overall"] - off["rps_overall"]
    if d_con < 0 and d_all <= TOL:
        too_good = ("  ⚠ TOO-GOOD: audit for leakage before believing."
                    if d_con < TOO_GOOD else "")
        return ("ADOPT (CONMEBOL-q RPS improves, overall does not regress)",
                f"accl_alt improves the CONMEBOL-qualifier slice by {-d_con:.5f} RPS with "
                f"overall Δ={d_all:+.5f}.{too_good} NOTE: per the spec, ADOPT here means the "
                "covariate earns its place by RPS; the sim's RateBook must be threaded to "
                "apply the per-team offset (sim-covariate-blindness tripwire) BEFORE flipping "
                "`enabled`. This phase leaves `enabled: []`.")
    return ("NO-LIFT (held-out RPS does not clear the gate)",
            f"accl_alt CONMEBOL-q Δ={d_con:+.5f}, overall Δ={d_all:+.5f} — does not improve "
            "the slice without regressing overall. Leave `enabled: []` (a valid recorded "
            "outcome).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cutoff", type=str, default=DEFAULT_CUTOFF)
    ap.add_argument("--out", type=str, default="reports/altitude_2026-06-10.md")
    args = ap.parse_args(argv)
    cutoff = args.cutoff

    print("=" * 78)
    print("ALTITUDE COVARIATE — held-out 1X2 RPS gate (OFFLINE, no odds, no credits)")
    print("=" * 78)
    base_cfg = load_config()
    inf = base_cfg["model"]["inference"]
    print(f"[fit] PRODUCTION fidelity: advi_iters={inf['advi_iters']} draws={inf['draws']}")
    store = get_persistent_store()
    max_train = _assert_no_leak(store, cutoff)
    print(f"[leakage] max training date < cutoff = {max_train.date()} (< {cutoff[:10]}). OK")

    heldout = _heldout_frame(store, cutoff)
    print(f"[heldout] {len(heldout)} valid-played internationals after {cutoff[:10]}.")

    arm_rows = []
    per_match_off = None
    for label, enabled in ARMS:
        print(f"\n[fit] arm={label!r} enabled={enabled} ...", flush=True)
        cfg_arm = _config_for_arm(base_cfg, enabled)
        try:
            post, hit = _fit_arm(store, cutoff, cfg_arm)
        except Exception as exc:  # noqa: BLE001
            print(f"[fit] arm={label!r} ERROR {type(exc).__name__}: {exc} — SKIP", flush=True)
            arm_rows.append({"label": label, "enabled": enabled,
                             "rps_overall": float("nan"), "n_overall": 0,
                             "rps_conmebol": float("nan"), "n_conmebol": 0})
            continue
        print(f"[fit] arm={label!r} {'CACHE HIT' if hit else 'fresh'}; "
              f"{len(post.teams)} teams.", flush=True)
        pm = _score_arm(post, heldout, enabled)
        if per_match_off is None:
            per_match_off = pm
        overall = [m["rps"] for m in pm]
        conmebol = [m["rps"] for m in pm if m["is_conmebol_q"]]
        arm_rows.append({
            "label": label, "enabled": enabled,
            "rps_overall": _mean(overall), "n_overall": len(overall),
            "rps_conmebol": _mean(conmebol), "n_conmebol": len(conmebol),
        })
        print(f"[score] overall RPS={_mean(overall):.5f} (n={len(overall)})  "
              f"CONMEBOL-q RPS={_mean(conmebol):.5f} (n={len(conmebol)})", flush=True)

    coverage_pct = (100.0 * np.mean([m["city_known"] for m in per_match_off])
                    if per_match_off else float("nan"))
    verdict, notes = _verdict(arm_rows)
    part = {
        "arms": arm_rows,
        "n_overall": arm_rows[0]["n_overall"],
        "n_conmebol": arm_rows[0]["n_conmebol"],
        "coverage_pct": coverage_pct,
        "verdict": verdict, "notes": notes,
    }

    print("\n" + "=" * 78)
    print(f"VERDICT: {verdict}")
    print("=" * 78)
    md = assemble_report(part, cutoff=cutoff, today="2026-06-10")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"[done] report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
