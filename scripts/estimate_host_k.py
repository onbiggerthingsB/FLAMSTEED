#!/usr/bin/env python
"""Phase-2b host-effect calibration — empirical ``host_k`` + sim sensitivity. OFFLINE.

OPS-ONLY, READ-ONLY. Adds NO model behaviour, changes NO config, spends ZERO
Odds-API credits. It only MEASURES: it replaces the *assumption*
``model.covariates.host_k = 0.5`` with an empirical estimate ``k_elo ± CI`` from
finals-tier host history (in the units the model uses), then reports the WC-2026
champion/advance sensitivity at the current 0.5 vs the empirical value — and
prints an explicit **ADOPT <value> / NO-CHANGE** recommendation. The USER adopts
at the checkpoint (NO ``model:`` config edit here).

THE SAMPLE (spec §2): finals-tier host games — ``tiers.match_type(tournament) ∈
{wc_finals, continental_championship}`` (WC finals + the continental
championships), ``neutral == False`` AND venue ``country == home_team`` (the
martj42 host marker — both asserted), ``date < 2026-01-01`` (the WC-2026 host
games have not been played). Each match's ratings are the point-in-time
``rating_pre`` from the SAME ``compute_elo_history`` the model feature uses
(leakage-safe by construction). Scoping pass: n ≈ 873; H/D/A ≈ 0.60/0.21/0.19.

THE UNIT MAPPING (spec §1, pitfall 2): ``host_k`` is "host advantage as a
multiple of standard home advantage" — exactly the quantity ``k_elo`` estimates.
So the mapping is the IDENTITY: ``host_k_model = k_elo`` (no rescaling).

DATA INPUTS (all read-only, no fetch):
  * the persistent martj42 results store (realized outcomes + per-match neutral
    flag + venue country) via ``clv_validation.get_persistent_store``;
  * the in-house point-in-time Elo (``compute_elo_history``) — the SAME ratings
    the model feature consumes;
  * (``--sensitivity`` only) the on-disk config-matched production posterior
    (reused, NOT re-fit) — ``model_market_gap._find_cached_production_posterior``.

RUN
---
    PYTHONPATH=src .venv/bin/python scripts/estimate_host_k.py \
        --out reports/host_k_2026-06-10.md                       # estimator, fast/offline
    nohup env PYTHONPATH=src .venv/bin/python scripts/estimate_host_k.py \
        --sensitivity --append --out reports/host_k_2026-06-10.md \
        > logs/host_k_sensitivity.log 2>&1 &                     # sim sensitivity, detached
"""
from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.backtest.host_k import bootstrap_k_ci, estimate_k_elo
from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.elo import compute_elo_history
from wcmodel.data.features import valid_played_results
from wcmodel.sim.run import SimConfig, simulate

# scripts/ is not a package on sys.path -> path-insert then import (house pattern).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from clv_validation import get_persistent_store  # noqa: E402
from model_market_gap import _find_cached_production_posterior  # noqa: E402

# --------------------------------------------------------------------------- #
# Constants.
# --------------------------------------------------------------------------- #
FULL_CUTOFF = "2026-06-10T00:00:00Z"      # as-of read for the FULL settled store.
EXCLUDE_FROM = "2026-01-01"               # WC-2026 host games not yet played.
FINALS_TIERS = ("wc_finals", "continental_championship")
N_BOOT = 2000                             # the brief: bootstrap n_boot >= 2000.
CURRENT_HOST_K = 0.5                      # config/config.yaml model.covariates.host_k.

# The sensitivity sim reuses a config-matched production posterior; prefer the
# 2026-06-10 cutoff (matches the current production state) and fall back to 06-07.
SENSITIVITY_CUTOFFS = ("2026-06-10T00:00:00Z", "2026-06-07T00:00:00Z")

# Tournament family labels for the per-tournament breakdown (informational; the
# binding tier filter is tiers.match_type above — these only label the n).
def _family(tournament: str) -> str:
    tl = (tournament or "").lower()
    if "world cup" in tl:
        return "WC finals"
    if "uefa euro" in tl:
        return "Euro"
    if "copa am" in tl:           # copa américa / copa america
        return "Copa América"
    if "african cup" in tl:
        return "AFCON"
    if "asian cup" in tl:
        return "AFC Asian Cup"
    if "gold cup" in tl:
        return "Gold Cup"
    return f"other: {tournament}"


def _outcome_letter(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "H"
    if home_score < away_score:
        return "A"
    return "D"


# =========================================================================== #
# Sample builder (spec §2) — point-in-time Elo joined onto finals-tier host games.
# =========================================================================== #
def build_host_rows(store, cfg: dict) -> tuple[list[dict], dict, list[str]]:
    """Build the §2 finals-tier host-game sample with point-in-time ratings.

    Computes the in-house Elo history ONCE over the valid-played store (as-of the
    FULL cutoff), joins each match's ``(rating_home, rating_away)`` from the
    home/away ``rating_pre``, selects the §2 host games, and asserts the host-game
    definition (``neutral == False`` AND ``country == home_team``) on every
    selected row.

    Returns ``(rows, breakdown, gaps)``:
      * ``rows``      : ``[{"rating_home","rating_away","outcome"}, ...]`` for the estimator.
      * ``breakdown`` : ``{"n": int, "hda": (h,d,a fracs), "by_family": {fam: n},
                            "by_tier": {tier: n}}``.
      * ``gaps``      : logged coverage gaps (a row lacking a rating is NEVER imputed).
    """
    res = store.read("results", cutoff=FULL_CUTOFF).copy()
    res["date"] = pd.to_datetime(res["date"])
    played = valid_played_results(res)
    played["match_type"] = played["tournament"].map(tiers.match_type)

    # Point-in-time Elo over the ENTIRE valid-played history (the same ratings the
    # model feature uses). rating_pre is each team's rating BEFORE the match.
    elo = compute_elo_history(
        played[["match_id", "date", "home_team", "away_team",
                "home_score", "away_score", "neutral", "match_type"]],
        config=cfg,
    )
    # Per match: the home team's rating_pre (is_home True) and away's (is_home False).
    pre = elo[["match_id", "team", "is_home", "rating_pre"]]
    home_pre = pre[pre["is_home"]].set_index("match_id")["rating_pre"]
    away_pre = pre[~pre["is_home"]].set_index("match_id")["rating_pre"]

    # §2 host-game selection: finals tier, non-neutral, country == home_team, pre-2026.
    sel = played[
        played["match_type"].isin(FINALS_TIERS)
        & (played["neutral"] == False)  # noqa: E712 (pandas mask, not `is`)
        & (played["country"] == played["home_team"])
        & (played["date"] < pd.Timestamp(EXCLUDE_FROM))
    ].copy()

    rows: list[dict] = []
    gaps: list[str] = []
    fam_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    hda = {"H": 0, "D": 0, "A": 0}
    for _, r in sel.iterrows():
        mid = r["match_id"]
        # ASSERT the host-game definition holds on every selected row (spec §2).
        assert (not bool(r["neutral"])) and (r["country"] == r["home_team"]), (
            f"non-host row leaked into the sample: {r['home_team']} v "
            f"{r['away_team']} ({r['date']}) neutral={r['neutral']} "
            f"country={r['country']}")
        if mid not in home_pre.index or mid not in away_pre.index:
            gaps.append(f"{r['home_team']} v {r['away_team']} ({str(r['date'])[:10]}) "
                        "[no point-in-time rating]")
            continue
        outcome = _outcome_letter(int(r["home_score"]), int(r["away_score"]))
        rows.append({
            "rating_home": float(home_pre.loc[mid]),
            "rating_away": float(away_pre.loc[mid]),
            "outcome": outcome,
        })
        hda[outcome] += 1
        fam = _family(str(r["tournament"]))
        fam_counts[fam] = fam_counts.get(fam, 0) + 1
        tier_counts[r["match_type"]] = tier_counts.get(r["match_type"], 0) + 1

    n = len(rows)
    hda_frac = ((hda["H"] / n, hda["D"] / n, hda["A"] / n) if n else (float("nan"),) * 3)
    breakdown = {
        "n": n,
        "hda": hda_frac,
        "hda_counts": hda,
        "by_family": dict(sorted(fam_counts.items(), key=lambda kv: -kv[1])),
        "by_tier": tier_counts,
    }
    return rows, breakdown, gaps


# =========================================================================== #
# Estimate (MLE + bootstrap CI) + the unit mapping + the verdict.
# =========================================================================== #
def run_estimate(rows: list[dict], cfg: dict) -> dict:
    """``estimate_k_elo`` + ``bootstrap_k_ci`` -> point + 95% CI; unit mapping +
    verdict logic (CI vs 0.5; the absurdity guard).

    Verdict (spec §4):
      * CI comfortably INCLUDES 0.5 -> NO-CHANGE.
      * CI EXCLUDES 0.5            -> ADOPT round(k_elo, 1).
      * k_elo > 3 or < -1          -> SUSPECTED-METHODOLOGY-BUG; withhold ADOPT.
    """
    home_advantage = float(cfg["elo"]["home_advantage"])
    draw_base = float(cfg["baseline"]["draw_base"])
    seed = int(cfg["seed"])

    ci = bootstrap_k_ci(rows, n_boot=N_BOOT, seed=seed,
                        draw_base=draw_base, home_advantage=home_advantage)
    k = ci["k"]
    lo, hi = ci["lo95"], ci["hi95"]

    suspected_bug = (not np.isnan(k)) and (k > 3.0 or k < -1.0)
    ci_excludes_half = (not np.isnan(lo)) and (not np.isnan(hi)) and (
        lo > CURRENT_HOST_K or hi < CURRENT_HOST_K)

    if suspected_bug:
        verdict = "SUSPECTED-BUG"
        adopt_value = None
    elif ci_excludes_half:
        verdict = "ADOPT"
        adopt_value = round(k, 1)
    else:
        verdict = "NO-CHANGE"
        adopt_value = None

    return {
        "k_elo": k, "lo95": lo, "hi95": hi,
        "n": len(rows), "n_boot": N_BOOT, "seed": seed,
        "home_advantage": home_advantage, "draw_base": draw_base,
        "host_k_model": k,            # identity mapping: host_k_model == k_elo.
        "current_host_k": CURRENT_HOST_K,
        "ci_excludes_half": ci_excludes_half,
        "verdict": verdict, "adopt_value": adopt_value,
    }


# =========================================================================== #
# Sensitivity (sim-only, cached posterior — NO refit).
# =========================================================================== #
HOST_TEAMS = ("United States", "Mexico", "Canada")
TOP8_N = 8


def _sim_at_host_k(cutoff: str, post, store, cfg: dict, host_k: float):
    """Deep-copy the cfg, set ``model.covariates.host_k``, build SimConfig, run the
    production sim at this host_k. Returns the ``SimResult`` (progression + se)."""
    c = deepcopy(cfg)
    c["model"]["covariates"]["host_k"] = float(host_k)
    simcfg = SimConfig.from_config(c)
    return simulate(pd.Timestamp(cutoff).normalize(), post, store, simcfg)


def run_sensitivity(store, cfg: dict, host_ks, *, allow_fresh_fit: bool = False) -> dict:
    """REUSE the config-matched production posterior (NO refit); for each host_k
    re-run the production sim with that predict-time scalar; collect champion +
    advance_from_group (+ se) for the hosts and the top-8 champion board.

    NO ``model:`` config field changes — ``host_k`` is threaded into the sim via
    ``SimConfig.config`` (a predict-time scalar), so this invalidates no posterior.
    """
    # Find the config-matched cached production posterior at the preferred cutoff.
    cutoff = post = src = None
    for cand in SENSITIVITY_CUTOFFS:
        found = _find_cached_production_posterior(cand, cfg)
        if found is not None:
            post, nc_name, _prov = found
            cutoff, src = cand, f"REUSED {nc_name} (config-matched / {cand[:10]})"
            break
    if post is None:
        if not allow_fresh_fit:
            raise RuntimeError(
                "no config-matched production posterior on disk for "
                f"{SENSITIVITY_CUTOFFS}; rerun with --allow-fresh-fit (detached).")
        # Fresh-fit fallback (detached): fit ONE at the preferred cutoff.
        from model_market_gap import _fit_one  # noqa: E402
        cutoff = SENSITIVITY_CUTOFFS[0]
        post, fit_src, _prov = _fit_one(cutoff, store, cfg)
        src = f"FRESH-FIT {fit_src} / {cutoff[:10]}"

    # Run the sim at each host_k; collect champion + advance for hosts and the board.
    per_k: dict[float, dict] = {}
    boards: dict[float, list[dict]] = {}
    for hk in host_ks:
        res = _sim_at_host_k(cutoff, post, store, cfg, hk)
        prog, se = res.progression, res.se
        hosts = {}
        for team in HOST_TEAMS:
            if team in prog.index:
                hosts[team] = {
                    "champion": float(prog.loc[team, "champion"]),
                    "champion_se": float(se.loc[team, "champion"]),
                    "advance": float(prog.loc[team, "advance_from_group"]),
                    "advance_se": float(se.loc[team, "advance_from_group"]),
                }
        per_k[float(hk)] = hosts
        # Top-8 champion board at this host_k.
        board = prog["champion"].sort_values(ascending=False).head(TOP8_N)
        boards[float(hk)] = [
            {"team": str(t), "champion": float(p),
             "champion_se": float(se.loc[t, "champion"])}
            for t, p in board.items()
        ]

    return {
        "cutoff": cutoff, "posterior_src": src,
        "host_ks": [float(h) for h in host_ks],
        "n_sims": int(cfg["sim"]["n_sims"]),
        "per_k": per_k, "boards": boards,
    }


# =========================================================================== #
# Report assembly (PURE — canned dicts in, markdown out).
# =========================================================================== #
def _fmt(x, nd=4) -> str:
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "n/a"
        return f"{x:.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def _pct(x, nd=1) -> str:
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "n/a"
        return f"{100.0 * x:.{nd}f}%"
    except (TypeError, ValueError):
        return str(x)


def _verdict_block(est: dict) -> list[str]:
    """The explicit ADOPT/NO-CHANGE/SUSPECTED-BUG recommendation lines."""
    L: list[str] = []
    k, lo, hi = est["k_elo"], est["lo95"], est["hi95"]
    cur = est["current_host_k"]
    if est["verdict"] == "SUSPECTED-BUG":
        L.append(f"### ⚠️ SUSPECTED METHODOLOGY BUG — k_elo = {_fmt(k, 2)}")
        L.append("")
        L.append(f"The estimate is outside the plausible band (k_elo > 3 or < −1). "
                 "Literature/history expect a host edge near a full home advantage "
                 "or more (k ≈ 1+), so this is a SUSPECTED bug — STOP and diagnose "
                 "(rating join, outcome coding, home-advantage unit) BEFORE believing "
                 "it. **The ADOPT recommendation is WITHHELD pending diagnosis.**")
        return L
    if est["verdict"] == "ADOPT":
        L.append(f"### ✅ RECOMMENDATION: ADOPT host_k = {est['adopt_value']}")
        L.append("")
        L.append(f"The 95% CI [{_fmt(lo, 2)}, {_fmt(hi, 2)}] EXCLUDES the current "
                 f"assumption {cur} — the host edge is empirically distinguishable "
                 f"from the guess. Adopt **host_k = {est['adopt_value']}** "
                 f"(= round(k_elo, 1)); the USER applies it to "
                 "``model.covariates.host_k`` at the checkpoint (this report makes no "
                 "config change).")
        return L
    L.append(f"### ➖ RECOMMENDATION: NO-CHANGE (keep host_k = {cur})")
    L.append("")
    L.append(f"The 95% CI [{_fmt(lo, 2)}, {_fmt(hi, 2)}] COMFORTABLY INCLUDES the "
             f"current assumption {cur} — the data cannot distinguish the host edge "
             f"from the guess at this n. **Keep host_k = {cur}**; no config change.")
    return L


def assemble_report(estimate: dict, breakdown: dict, sensitivity: dict | None,
                    *, today: str) -> str:
    """Assemble §6 of the spec into one markdown string. Pure — no I/O."""
    L: list[str] = []
    L.append(f"# Phase 2b — Host-Effect Calibration (`host_k`) — {today}")
    L.append("")
    L.append("> OFFLINE. Zero Odds-API credits. No `model:` config change (this phase "
             "only MEASURES; the USER adopts at the checkpoint). The sim sensitivity "
             "REUSES the cached production posterior and only overrides the "
             "predict-time `host_k` scalar (no refit, no posterior-cache invalidation).")
    L.append("")

    # --- The sample. ---
    L.append("## 1. The sample")
    L.append("")
    L.append(f"n = **{breakdown['n']}** finals-tier host games (non-neutral, venue "
             "country == home team, played before 2026). Tier filter = "
             "`tiers.match_type ∈ {wc_finals, continental_championship}` (WC finals + "
             "the continental championships); host-game definition asserted on every "
             "selected row.")
    L.append("")
    h, d, a = breakdown["hda"]
    hc = breakdown.get("hda_counts", {})
    L.append(f"- Realized split H/D/A = **{_pct(h)} / {_pct(d)} / {_pct(a)}** "
             f"(counts H={hc.get('H', '?')} D={hc.get('D', '?')} A={hc.get('A', '?')}).")
    L.append("")
    L.append("Per-tournament breakdown:")
    L.append("")
    L.append("| tournament | n |")
    L.append("|---|--:|")
    for fam, cnt in breakdown["by_family"].items():
        L.append(f"| {fam} | {cnt} |")
    L.append("")

    # --- The estimate + unit mapping. ---
    L.append("## 2. The estimate (k_elo MLE ± bootstrap CI)")
    L.append("")
    L.append(f"- **k_elo = {_fmt(estimate['k_elo'], 3)}** "
             f"(95% CI [{_fmt(estimate['lo95'], 3)}, {_fmt(estimate['hi95'], 3)}], "
             f"{estimate['n_boot']}-resample seeded match-bootstrap, seed "
             f"{estimate['seed']}).")
    L.append(f"- MLE of the host home advantage as a multiple of standard home "
             f"advantage (Elo unit = {_fmt(estimate['home_advantage'], 0)}, "
             f"draw_base = {_fmt(estimate['draw_base'], 2)}). k_elo = 1.0 ≡ hosts "
             "behave like an ordinary home team; k_elo = 0.0 ≡ neutral; the host "
             f"overperformance is k_elo − 1.0 = **{_fmt(estimate['k_elo'] - 1.0, 3)}** "
             "standard-home-advantage units.")
    L.append("")
    L.append("### Unit mapping into the model's `host_k`")
    L.append("")
    L.append("`host_k` multiplies the fitted home advantage for a 2026 host's "
             "in-country game; it is *exactly* \"host advantage as a multiple of "
             "standard home advantage\" — the SAME quantity `k_elo` estimates. The "
             "mapping is therefore the **identity** (no rescaling):")
    L.append("")
    L.append(f"> **host_k_model = k_elo = {_fmt(estimate['host_k_model'], 3)}** "
             f"(round to **{_fmt(round(estimate['k_elo'], 1), 1)}** for adoption).")
    L.append("")
    L.append("**Net-edge both ways** (spec §1, pitfall 2):")
    L.append("")
    L.append(f"- (a) As a multiple of standard home advantage: the host carries "
             f"`k_elo · home_adv` (k_elo = {_fmt(estimate['k_elo'], 3)}), vs an "
             "ordinary home team's `1.0 · home_adv`.")
    L.append(f"- (b) In the 2026 sim: a host group game uses `(host_k·ha, 0)` while "
             "every other group game is neutral `(0.5·ha, 0.5·ha)`. So the host's "
             "NET edge over a neutral opponent on the home side is "
             f"`(host_k − 0.5)·ha` = **({_fmt(estimate['k_elo'], 3)} − 0.5)·ha = "
             f"{_fmt(estimate['k_elo'] - 0.5, 3)}·ha**, versus the current "
             "`(0.5 − 0.5)·ha = 0` net edge at host_k = 0.5.")
    L.append("")

    # --- The sensitivity table. ---
    L.append("## 3. WC-2026 sim sensitivity (cached posterior; no refit)")
    L.append("")
    if sensitivity is None:
        L.append("_Sensitivity sim not run in this invocation (run with "
                 "`--sensitivity`). The estimator block above is complete and offline._")
        L.append("")
    else:
        host_ks = sensitivity["host_ks"]
        old_k = CURRENT_HOST_K
        new_ks = [k for k in host_ks if abs(k - old_k) > 1e-9]
        new_k = new_ks[0] if new_ks else old_k
        L.append(f"Posterior: {sensitivity['posterior_src']}; cutoff "
                 f"{sensitivity['cutoff'][:10]}; n_sims = {sensitivity['n_sims']:,}. "
                 f"host_k swept {old_k} (current) → {new_k} (empirical, round(k_elo,1)). "
                 "Each cell is P ± Monte-Carlo SE.")
        L.append("")
        # Host deltas (champion + advance).
        L.append("### Host nations — champion & advance_from_group (old → new)")
        L.append("")
        L.append("| host | market | host_k=" + f"{old_k}" + " | host_k=" +
                 f"{new_k}" + " | Δ (new − old) |")
        L.append("|---|---|--:|--:|--:|")
        per_k = sensitivity["per_k"]
        old = per_k.get(old_k, {})
        new = per_k.get(new_k, {})
        for team in HOST_TEAMS:
            o = old.get(team, {})
            nw = new.get(team, {})
            for market, lbl in (("champion", "champion"),
                                ("advance", "advance_from_group")):
                ov = o.get(market)
                nv = nw.get(market)
                ose = o.get(f"{market}_se")
                nse = nw.get(f"{market}_se")
                delta = (nv - ov) if (ov is not None and nv is not None) else None
                L.append(
                    f"| {team} | {lbl} | "
                    f"{_pct(ov)} ± {_pct(ose, 2) if ose is not None else 'n/a'} | "
                    f"{_pct(nv)} ± {_pct(nse, 2) if nse is not None else 'n/a'} | "
                    f"{('+' if (delta or 0) >= 0 else '') + _pct(delta) if delta is not None else 'n/a'} |")
        L.append("")
        # Top-8 champion board, old vs new.
        L.append("### Top-8 champion board (old vs new)")
        L.append("")
        boards = sensitivity["boards"]
        L.append(f"**host_k = {old_k} (current):**")
        L.append("")
        L.append("| rank | team | champion |")
        L.append("|--:|---|--:|")
        for i, b in enumerate(boards.get(old_k, []), 1):
            L.append(f"| {i} | {b['team']} | {_pct(b['champion'])} ± "
                     f"{_pct(b['champion_se'], 2)} |")
        L.append("")
        L.append(f"**host_k = {new_k} (empirical):**")
        L.append("")
        L.append("| rank | team | champion |")
        L.append("|--:|---|--:|")
        for i, b in enumerate(boards.get(new_k, []), 1):
            L.append(f"| {i} | {b['team']} | {_pct(b['champion'])} ± "
                     f"{_pct(b['champion_se'], 2)} |")
        L.append("")

    # --- The verdict. ---
    L.append("## 4. Recommendation")
    L.append("")
    L.extend(_verdict_block(estimate))
    L.append("")
    return "\n".join(L)


# =========================================================================== #
# main.
# =========================================================================== #
def _default_out() -> str:
    return f"reports/host_k_{date.today().isoformat()}.md"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None,
                    help="markdown output path (default reports/host_k_<today>.md)")
    ap.add_argument("--sensitivity", action="store_true",
                    help="also run the sim sensitivity (reuses the cached posterior; "
                         "~6-10 min/host_k — run detached).")
    ap.add_argument("--append", action="store_true",
                    help="append the generated markdown to --out instead of overwriting.")
    ap.add_argument("--allow-fresh-fit", action="store_true",
                    help="sensitivity: if no config-matched posterior is on disk, fit "
                         "ONE fresh (production fidelity; minutes; run detached).")
    args = ap.parse_args(argv)

    out_path = Path(args.out) if args.out else Path(_default_out())
    cfg = load_config()
    store = get_persistent_store()

    print("[estimate] building the finals-tier host-game sample ...", flush=True)
    rows, breakdown, gaps = build_host_rows(store, cfg)
    print(f"[estimate] n={breakdown['n']} host games; H/D/A="
          f"{tuple(round(x, 3) for x in breakdown['hda'])}; "
          f"by_tier={breakdown['by_tier']}", flush=True)
    if gaps:
        print(f"[estimate] coverage gaps (not imputed): {len(gaps)}", flush=True)
        for g in gaps:
            print(f"   - {g}", flush=True)

    estimate = run_estimate(rows, cfg)
    print(f"[estimate] k_elo={estimate['k_elo']:.4f} "
          f"CI=[{estimate['lo95']:.4f}, {estimate['hi95']:.4f}] "
          f"verdict={estimate['verdict']} adopt={estimate['adopt_value']}", flush=True)

    sensitivity = None
    if args.sensitivity:
        new_k = round(estimate["k_elo"], 1)
        host_ks = [CURRENT_HOST_K] + ([new_k] if abs(new_k - CURRENT_HOST_K) > 1e-9 else [])
        print(f"[sensitivity] sweeping host_k in {host_ks} on the cached posterior "
              "(no refit) ...", flush=True)
        sensitivity = run_sensitivity(store, cfg, host_ks,
                                      allow_fresh_fit=args.allow_fresh_fit)
        print(f"[sensitivity] {sensitivity['posterior_src']}", flush=True)

    md = assemble_report(estimate, breakdown, sensitivity,
                         today=date.today().isoformat())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.append:
        with out_path.open("a") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print(f"[report] appended to {out_path}", flush=True)
    else:
        out_path.write_text(md)
        print(f"[report] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
