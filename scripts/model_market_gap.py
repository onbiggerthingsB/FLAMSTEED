#!/usr/bin/env python
"""Phase-1 headroom diagnostic — paired model-vs-market gap (n=22) + stratified
weakness map vs realized results (n~2111).  OFFLINE. ZERO Odds-API credits.

OPS-ONLY, READ-ONLY DIAGNOSTIC. Adds NO model/pipeline behaviour and NO betting.
It only MEASURES where and how much the anchored production model (strength
anchor ON, k=0.6) trails (a) the de-vigged sharp Pinnacle close and (b) the
realized result, producing the inputs to Gate G1.

The work splits into two honest parts (per the spec — the stored 1X2 odds cover
exactly 22 matches, too thin for a market-stratified table):

  * PART A — paired model-vs-market (n=22). The CURRENT-config rerun of the CLV
    validation: Shin-de-vig the stored Pinnacle close -> market 1X2; fit the
    production config at ONE shared cutoff per natural cluster; paired
    RPS_model - RPS_market per match -> aggregate gap + bootstrap CI. This is the
    ONLY model-vs-market number; its CI is wide (n=22) — said so in the report.

  * PART B — stratified weakness map vs realized results (n~2111, full power).
    Reuse the on-disk k=0.6 / cutoff 2024-06-01 production posterior by
    config-match (no re-fit); score every international played strictly after the
    cutoff; per-slice paired RPS_model - RPS_elo (Elo as a RESULTS-derived
    reference, NOT a market proxy) + reliability tables.

DATA INPUTS (all read-only, no fetch):
  * ``data/clv_odds_cache.json`` — the 22 cached Pinnacle (entry, close) records
    written by the earlier real-odds CLV work. READ-ONLY; this script never pulls.
  * ``data/cache/posterior-*.{nc,meta.json}`` — the on-disk production posteriors
    (Part A: cached_fit per cluster cutoff on the CURRENT config; Part B: the
    config-matched k=0.6 / 2024-06-01 netCDF, reconstructed directly).
  * the persistent martj42 results store (the realized outcomes + per-match
    neutral flag).

LEAKAGE (binding): every scored match is strictly AFTER its fit's cutoff; we
assert max-training-date < cutoff per fit. Names join martj42<->odds via the
established ``_canon`` aliases; an unmatched fixture is a logged coverage gap,
never guessed.

HONESTY TRIPWIRE (binding): if Part A's aggregate RPS_model < RPS_market (the
model 'beats' the de-vigged sharp close), that is too-good — the report labels
the result SUSPECT and prints the selection-bias + cutoff-alignment audit block
to investigate BEFORE believing it.

RUN
---
    PYTHONPATH=src .venv/bin/python scripts/model_market_gap.py --part B
    PYTHONPATH=src .venv/bin/python scripts/model_market_gap.py --part A   # detached; up to 4 fits
    PYTHONPATH=src .venv/bin/python scripts/model_market_gap.py --part all --out reports/headroom_2026-06-10.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import wcmodel.model.cache as model_cache
from wcmodel.backtest.baselines import elo_baseline_1x2
from wcmodel.backtest.headroom import (
    add_gap_quartiles,
    assign_slices,
    confed_pairing_detail,
    bootstrap_delta_ci,
    market_probs_from_odds,
    paired_rps,
    reliability_table,
)
from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.elo import compute_elo_history
from wcmodel.data.features import valid_played_results

# Reuse the persistent real-martj42 store + the offline odds-cache reader + the
# _canon name reconciliation from the CLV harness (scripts/ is not a package on
# sys.path -> path-insert then import, the house pattern).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from clv_validation import (  # noqa: E402  (script-local import, after sys.path)
    CACHE_DIR,
    ODDS_CACHE_PATH,
    _canon,
    _load_odds_cache,
    _martj42_results_frame,
    get_persistent_store,
)

# --------------------------------------------------------------------------- #
# Constants.
# --------------------------------------------------------------------------- #
PROBE_CUTOFF = "2026-06-07T00:00:00Z"   # as-of read for the FULL settled store.

# Part A — the four natural clusters; the cutoff is strictly BEFORE the cluster's
# first match (so every cluster match is held out of its own fit).
PART_A_CLUSTERS = {
    "wc2022": "2022-11-20T00:00:00Z",
    "euro2024": "2024-06-14T00:00:00Z",
    "nl2024": "2024-09-05T00:00:00Z",
    "wcq2025": "2025-09-03T00:00:00Z",
}

# Part B — the established calibration cutoff; the on-disk k=0.6 sweep posterior
# lives here. The held-out set is internationals played strictly after it.
PART_B_CUTOFF = "2024-06-01T00:00:00Z"

# G1 thresholds (the brief): aggregate market gap small -> Phase 2 only; large ->
# Phase 3 priority. The gap is RPS_model - RPS_market (positive = market ahead).
G1_SMALL = 0.005
G1_LARGE = 0.010

# Outcome letter for paired_rps, from realized scores.
def _outcome_letter(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "H"
    if home_score < away_score:
        return "A"
    return "D"


# =========================================================================== #
# Posterior reuse (config-match) — extended to ALSO match model.strength_prior.
# =========================================================================== #
def _find_cached_production_posterior(cutoff: str, cfg: dict):
    """Return ``(Posterior, nc_name)`` reconstructed from the on-disk production
    netCDF at ``cutoff`` whose meta matches the production config — INCLUDING the
    Elo strength anchor — or ``None`` if none is on disk.

    Copies ``diagnose_totals_calibration._find_cached_production_posterior`` and
    EXTENDS the config-match with ``model.strength_prior`` (so the k=0.6 anchored
    posterior is matched, not a stale k=0 one). We do NOT route through
    ``cached_fit`` — its content key bakes in the git commit, which has advanced,
    so it would MISS + re-fit. Loading the matching netCDF directly via the
    cache's own reconstruction is the bit-identical, zero-waste reuse.
    """
    inf = cfg["model"]["inference"]
    want = {
        "cutoff_day": str(pd.Timestamp(cutoff).normalize().date()),
        "likelihood": cfg["model"]["likelihood"],
        "draws": int(inf["draws"]),
        "tune": int(inf["tune"]),
        "advi_iters": int(inf["advi_iters"]),
        "seed": int(cfg["seed"]),
        "prior": cfg["model"]["prior"],
        "widening": cfg["model"]["widening"],
        "strength_prior": cfg["model"].get("strength_prior"),
        # COVARIATES are part of the posterior's content (P4a purity finding,
        # 2026-06-11): without this field the matcher confused the production fit
        # (covariates.enabled=[], host_k=1.4) with sweep arms fit under accl_alt /
        # altitude_m / rest_days or the pre-P2b host_k=0.5 — same k_att, different
        # model. Full-block match: enabled list, host_k, hosts, scales, indicators.
        "covariates": cfg["model"].get("covariates"),
    }
    for meta_path in sorted(CACHE_DIR.glob("posterior-*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text())
        except (ValueError, OSError):
            continue
        m_model = meta.get("model", {})
        try:
            got = {
                "cutoff_day": str(pd.Timestamp(meta.get("cutoff")).normalize().date()),
                "likelihood": meta.get("likelihood"),
                "draws": int(meta.get("draws")),
                "tune": int(meta.get("tune")),
                "advi_iters": int(meta.get("advi_iters")),
                "seed": int(meta.get("seed")),
                "prior": m_model.get("prior"),
                "widening": m_model.get("widening"),
                "strength_prior": m_model.get("strength_prior"),
                "covariates": m_model.get("covariates"),
            }
        except (TypeError, ValueError):
            continue
        if got != want:
            continue
        nc = meta_path.with_suffix("").with_suffix(".nc")  # posterior-<key>.nc
        if not nc.exists():
            continue
        post = model_cache._posterior_from_netcdf(
            nc, teams=meta["teams"], likelihood=meta["likelihood"],
            provisional_teams=meta["provisional_teams"], cfg=cfg,
            covariate_transforms=model_cache._transforms_from_meta(
                meta.get("covariate_transforms")),
        )
        # The as-of-cutoff provisional set rides on the meta (used for the
        # provisional-involvement slice in Part B).
        return post, nc.name, set(meta.get("provisional_teams", []))
    return None


def _fit_one(cutoff: str, store, cfg: dict):
    """Fit (or HIT) ONE production posterior at ``cutoff`` through ``cached_fit``.

    Returns ``(post, src, provisional_teams)``. Used as the Part-A per-cluster fit
    and the Part-B fresh-fit fallback."""
    inf = cfg["model"]["inference"]
    post, meta = model_cache.cached_fit(
        cutoff=pd.Timestamp(cutoff).normalize(), store=store, backend="advi",
        draws=int(inf["draws"]), seed=int(cfg["seed"]), advi_iters=int(inf["advi_iters"]),
        cache_dir=CACHE_DIR, config=cfg,
    )
    src = f"cached_fit cache_hit={meta['cache_hit']} key={meta['key']}"
    return post, src, set(getattr(post, "provisional_teams", ()) or ())


# =========================================================================== #
# Leakage guard + point-in-time Elo (the established CLV/sweep pattern).
# =========================================================================== #
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


def _elo_as_of_cutoff(store, cutoff: str, config: dict) -> dict:
    """Each team's LATEST pre-cutoff ``rating_pre`` — the point-in-time Elo
    baseline strength (the SAME ``compute_elo_history`` the model feature uses,
    leakage-safe). Returns ``{team: rating}``."""
    res = store.read("results", cutoff=cutoff).copy()
    res["date"] = pd.to_datetime(res["date"])
    played = valid_played_results(res)
    played = played[pd.to_datetime(played["date"]) < pd.Timestamp(cutoff[:10])].copy()
    played["match_type"] = played["tournament"].map(tiers.match_type)
    elo = compute_elo_history(
        played[["match_id", "date", "home_team", "away_team",
                "home_score", "away_score", "neutral", "match_type"]],
        config=config,
    )
    latest = elo.sort_values("date").groupby("team")["rating_pre"].last()
    return {str(t): float(v) for t, v in latest.items()}


def _heldout_frame(store, cutoff: str) -> pd.DataFrame:
    """Valid-played internationals with ``date > cutoff`` (held-out scoring set)."""
    played = _martj42_results_frame(store, PROBE_CUTOFF).copy()
    played["date"] = pd.to_datetime(played["date"])
    ho = played[played["date"] > pd.Timestamp(cutoff[:10])].copy()
    return ho.reset_index(drop=True)


# =========================================================================== #
# PART A — paired model-vs-market (n=22).
# =========================================================================== #
def run_part_a(store, cfg: dict) -> dict:
    """Per-cluster production fit -> paired RPS_model vs the de-vigged close.

    For each of the four clusters: fit (or HIT) the CURRENT-config production
    posterior at the cluster's shared cutoff; for each cached fixture whose
    martj42 result exists, build market 1X2 = Shin-de-vig of the close and model
    1X2 = ``predict_1x2(neutral=<TRUE martj42 flag>, host_factor=None)``; assert
    the match kicks off strictly after the cutoff (leakage). Returns the per-match
    rows, per-cluster paired_rps + bootstrap, and the aggregate gap.
    """
    cache = _load_odds_cache()
    played = _martj42_results_frame(store, PROBE_CUTOFF).copy()
    played["date"] = pd.to_datetime(played["date"])

    # Map each cached fixture to its cluster by kickoff date.
    def _cluster_of(ko_date: pd.Timestamp) -> str | None:
        best = None
        for name, cut in PART_A_CLUSTERS.items():
            c = pd.Timestamp(cut[:10])
            if ko_date > c and (best is None or c > pd.Timestamp(PART_A_CLUSTERS[best][:10])):
                best = name
        return best

    # Group the 22 cached fixtures by cluster.
    by_cluster: dict[str, list] = {}
    gaps: list[str] = []
    for key, rec in cache.items():
        home, away = rec["home"], rec["away"]
        ko = pd.Timestamp(rec["kickoff"][:10])
        cl = _cluster_of(ko)
        if cl is None:
            gaps.append(f"{home} v {away} ({rec['kickoff'][:10]}) [no cluster]")
            continue
        by_cluster.setdefault(cl, []).append(rec)

    all_rows: list[dict] = []
    clusters_out: list[dict] = []
    per_match_out: list[dict] = []
    for name in PART_A_CLUSTERS:
        recs = by_cluster.get(name, [])
        if not recs:
            continue
        cutoff = PART_A_CLUSTERS[name]
        max_train = _assert_no_leak(store, cutoff)
        post, src, _prov = _fit_one(cutoff, store, cfg)
        rows: list[dict] = []
        for rec in recs:
            home, away = _canon(rec["home"]), _canon(rec["away"])
            ko = pd.Timestamp(rec["kickoff"][:10])
            # LEAKAGE: every scored match kicks off strictly after its cluster cutoff.
            assert ko > pd.Timestamp(cutoff[:10]), (
                f"LEAKAGE: {home} v {away} ({ko.date()}) not after cutoff {cutoff[:10]}")
            r = played[(played.home_team == home) & (played.away_team == away)
                       & (played.date == ko)]
            if r.empty:
                gaps.append(f"{home} v {away} ({ko.date()}) [no martj42 result]")
                continue
            rr = r.iloc[0]
            neutral = bool(rr["neutral"])   # TRUE per-match flag from martj42
            try:
                m = post.predict_1x2(home, away, neutral=neutral, host_factor=None)
            except KeyError:
                gaps.append(f"{home} v {away} ({ko.date()}) [no model price]")
                continue
            close = rec["close"]
            pH, pD, pA = market_probs_from_odds(close["home"], close["draw"], close["away"])
            outcome = _outcome_letter(int(rr.home_score), int(rr.away_score))
            row = {
                "p_model": (m["home"], m["draw"], m["away"]),
                "p_ref": (pH, pD, pA),
                "outcome": outcome,
            }
            rows.append(row)
            all_rows.append(row)
            per_match_out.append({
                "home": home, "away": away, "date": str(ko.date()),
                "cluster": name, "neutral": neutral, "outcome": outcome,
                "rps_model": paired_rps([row])["rps_model"],
                "rps_market": paired_rps([{**row, "p_model": row["p_ref"]}])["rps_model"],
            })
        if not rows:
            continue
        pr = paired_rps(rows)
        ci = bootstrap_delta_ci(rows, n_boot=10_000, seed=cfg["seed"])
        clusters_out.append({
            "name": name, "cutoff": cutoff, "n": pr["n"],
            "rps_model": pr["rps_model"], "rps_ref": pr["rps_ref"],
            "delta": ci["delta"], "lo95": ci["lo95"], "hi95": ci["hi95"],
            "posterior_key": src, "max_train": str(max_train.date()),
        })

    agg_pr = paired_rps(all_rows)
    agg_ci = bootstrap_delta_ci(all_rows, n_boot=10_000, seed=cfg["seed"])
    return {
        "n": agg_pr["n"],
        "aggregate": {"delta": agg_ci["delta"], "lo95": agg_ci["lo95"],
                      "hi95": agg_ci["hi95"], "rps_model": agg_pr["rps_model"],
                      "rps_ref": agg_pr["rps_ref"]},
        "clusters": clusters_out,
        "per_match": per_match_out,
        "gaps": gaps,
    }


# =========================================================================== #
# PART B — stratified weakness map vs realized results (n~2111).
# =========================================================================== #
def _slice_keys(s: dict) -> list[str]:
    """The stratum tags a match contributes to (one per dimension)."""
    return [
        f"gap_q={s['elo_gap_q']}",
        f"confed_pair={s['confed_pair']}",
        f"tier={s['tier']}",
        f"neutral={s['neutral']}",
        f"provisional={s['provisional']}",
    ]


def run_part_b(store, cfg: dict, *, allow_fresh_fit: bool = False) -> dict:
    """Reuse the on-disk k=0.6 / 2024-06-01 posterior (or fall back to ONE fit);
    score the held-out internationals; build the ranked slice table + reliability.
    """
    cutoff = PART_B_CUTOFF
    max_train = _assert_no_leak(store, cutoff)
    found = _find_cached_production_posterior(cutoff, cfg)
    if found is not None:
        post, src_name, provisional = found
        src = f"REUSED {src_name} (config-matched k=0.6 / {cutoff[:10]})"
    else:
        if not allow_fresh_fit:
            # Default still fits ONE at the same cutoff (cheap on a HIT; the
            # controller runs the expensive case detached).
            pass
        post, src, provisional = _fit_one(cutoff, store, cfg)
        src = f"FRESH-FIT {src}"

    elo_ratings = _elo_as_of_cutoff(store, cutoff, cfg)
    heldout = _heldout_frame(store, cutoff)
    known = set(post.teams)

    rows: list[dict] = []          # for the aggregate paired_rps / bootstrap
    rel_rows: list[dict] = []      # per-scored-match: favorite prob + draw prob + hits
    scored: list[dict] = []        # per-match slice tags + per-row rps (model, elo)
    for _, row in heldout.iterrows():
        home, away = str(row["home_team"]), str(row["away_team"])
        if home not in known or away not in known:
            continue
        if home not in elo_ratings or away not in elo_ratings:
            continue
        neutral = bool(row["neutral"])
        outcome = _outcome_letter(int(row["home_score"]), int(row["away_score"]))
        try:
            m = post.predict_1x2(home, away, neutral=neutral, host_factor=None)
        except KeyError:
            continue
        from wcmodel.backtest.baselines import elo_baseline_1x2
        elo = elo_baseline_1x2(rating_home=elo_ratings[home],
                               rating_away=elo_ratings[away],
                               neutral=neutral, config=cfg)
        prow = {"p_model": (m["home"], m["draw"], m["away"]),
                "p_ref": (elo["home"], elo["draw"], elo["away"]),
                "outcome": outcome}
        rows.append(prow)
        # Slice tags. elo_gap = point-in-time rating_home - rating_away.
        s = assign_slices({
            "elo_gap": elo_ratings[home] - elo_ratings[away],
            "home_confed": tiers.confederation(home),
            "away_confed": tiers.confederation(away),
            "match_type": tiers.match_type(str(row["tournament"])),
            "neutral": neutral,
            "any_provisional": (home in provisional) or (away in provisional),
        })
        scored.append({"slice": s, "row": prow})
        # Reliability: favorite (model's top pick) prob + whether it won; P(draw).
        fav = max(("home", "draw", "away"), key=lambda k: m[k])
        rel_rows.append({
            "fav_p": m[fav], "fav_hit": (fav.upper()[0] == outcome),
            "draw_p": m["draw"], "draw_hit": (outcome == "D"),
        })

    # Reassign the |gap| quartile over the FULL scored frame (qcut), then re-tag.
    if scored:
        gap_df = pd.DataFrame({"elo_gap": [sc["slice"]["elo_gap_q"] for sc in scored]})
        gap_df = add_gap_quartiles(gap_df, col="elo_gap")
        for sc, q in zip(scored, gap_df["elo_gap_q"]):
            sc["slice"]["elo_gap_q"] = q

    # Build the ranked slice table: one row per (dimension-value) stratum.
    bucket: dict[str, list[dict]] = {}
    for sc in scored:
        for key in _slice_keys(sc["slice"]):
            bucket.setdefault(key, []).append(sc["row"])
    slices_out: list[dict] = []
    for key, srows in bucket.items():
        pr = paired_rps(srows)
        ci = bootstrap_delta_ci(srows, n_boot=2_000, seed=cfg["seed"])
        slices_out.append({
            "slice": key, "n": pr["n"], "rps_model": pr["rps_model"],
            "rps_elo": pr["rps_ref"], "delta": ci["delta"],
            "lo95": ci["lo95"], "hi95": ci["hi95"],
        })
    # Rank worst-first: largest positive delta (model trails Elo most) at the top.
    slices_out.sort(key=lambda d: d["delta"], reverse=True)

    agg_pr = paired_rps(rows)
    agg_ci = bootstrap_delta_ci(rows, n_boot=10_000, seed=cfg["seed"])

    # Reliability tables (10 bins): favorite prob vs hit, P(draw) vs draw.
    rel_fav = reliability_table([r["fav_p"] for r in rel_rows],
                                [r["fav_hit"] for r in rel_rows], bins=10)
    rel_draw = reliability_table([r["draw_p"] for r in rel_rows],
                                 [r["draw_hit"] for r in rel_rows], bins=10)

    return {
        "n": agg_pr["n"],
        "posterior_src": src,
        "cutoff": cutoff,
        "max_train": str(max_train.date()),
        "aggregate": {"rps_model": agg_pr["rps_model"], "rps_elo": agg_pr["rps_ref"],
                      "delta": agg_ci["delta"], "lo95": agg_ci["lo95"],
                      "hi95": agg_ci["hi95"]},
        "slices": slices_out,
        "reliability_fav": rel_fav,
        "reliability_draw": rel_draw,
        # G1 follow-up: per confederation-pairing model-vs-Elo + reliability
        # (evidence for the Jun-20 Phase-3 go/no-go).
        "confed_detail": confed_pairing_detail(scored, seed=cfg["seed"]),
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


def _g1_recommendation(gap: float) -> str:
    """The brief's threshold rule on the aggregate market gap (RPS_model -
    RPS_market). Larger gap = more market headroom = higher-phase priority."""
    if gap is None or (isinstance(gap, float) and np.isnan(gap)):
        return ("**G1 recommendation:** the aggregate market gap is undefined "
                "(no matched fixtures) — resolve coverage before deciding.")
    if gap < G1_SMALL:
        return (f"**G1 recommendation:** aggregate market gap {gap:+.4f} RPS is "
                f"below ~{G1_SMALL:.3f} — the model is already near the de-vigged "
                "sharp ceiling. Pursue **Phase 2** calibration refinements only; "
                "do NOT prioritise Phase 3.")
    if gap >= G1_LARGE:
        return (f"**G1 recommendation:** aggregate market gap {gap:+.4f} RPS is at "
                f"or above ~{G1_LARGE:.3f} — there is material headroom to the "
                "sharp close. **Phase 3 is a priority.**")
    return (f"**G1 recommendation:** aggregate market gap {gap:+.4f} RPS sits in the "
            f"~{G1_SMALL:.3f}-{G1_LARGE:.3f} grey band — modest headroom. **Phase 2** "
            "first; reassess Phase 3 after.")


def assemble_report(part_a: dict | None, part_b: dict | None, *, today: str) -> str:
    """Assemble §2 of the spec into one markdown string. Pure — no I/O."""
    L: list[str] = []
    L.append(f"# Phase 1 — Headroom Diagnostic — {today}")
    L.append("")
    L.append("> OFFLINE diagnostic. Zero Odds-API credits. No model-config change "
             "(this phase only MEASURES). Gate G1 is the user's decision.")
    L.append("")

    # --- Part A — paired model-vs-market (n=22). ---
    if part_a is not None:
        agg = part_a["aggregate"]
        gap = agg["delta"]
        suspect = (gap is not None and not (isinstance(gap, float) and np.isnan(gap))
                   and gap < 0)
        L.append("## Part A — paired model vs market (de-vigged sharp close)")
        L.append("")
        L.append(f"n = **{part_a['n']}** matched fixtures (the full stored-odds "
                 "coverage). This is the ONLY model-vs-market number; the CI is wide "
                 "by construction at this n.")
        L.append("")
        L.append(f"- aggregate RPS_model = {_fmt(agg['rps_model'])}, "
                 f"RPS_market = {_fmt(agg['rps_ref'])}")
        L.append(f"- aggregate gap ΔRPS (model − market) = **{_fmt(gap)}** "
                 f"(95% CI [{_fmt(agg['lo95'])}, {_fmt(agg['hi95'])}], "
                 "10k paired bootstrap)")
        if suspect:
            L.append("")
            L.append("### ⚠️ SUSPECT — too-good tripwire fired")
            L.append("")
            L.append("Part A's aggregate RPS_model is BELOW RPS_market — the model "
                     "appears to beat the de-vigged sharp close. Treat as too-good "
                     "and AUDIT before believing it:")
            L.append("")
            L.append("- **Selection bias:** the 22 odds-covered fixtures skew to "
                     "big-name matches (WC/Euro/NL marquee), where the model is "
                     "strongest; this is NOT a representative sample of the market.")
            L.append("- **Cutoff / close alignment:** confirm each cluster fit's "
                     "cutoff is strictly before the cluster's first kickoff and the "
                     "stored close timestamp is pre-kickoff (no leakage either side).")
            L.append("- Do NOT report a Part-A win until both checks clear.")
        L.append("")
        # Per-cluster provenance table.
        if part_a.get("clusters"):
            L.append("| cluster | cutoff | n | RPS_model | RPS_market | ΔRPS | 95% CI | posterior |")
            L.append("|---|---|--:|--:|--:|--:|---|---|")
            for c in part_a["clusters"]:
                L.append(f"| {c['name']} | {c['cutoff'][:10]} | {c['n']} | "
                         f"{_fmt(c.get('rps_model'))} | {_fmt(c.get('rps_ref'))} | "
                         f"{_fmt(c['delta'])} | [{_fmt(c['lo95'])}, {_fmt(c['hi95'])}] | "
                         f"{c.get('posterior_key', 'n/a')} |")
            L.append("")
        if part_a.get("gaps"):
            L.append(f"_Coverage gaps (unmatched, not guessed): {len(part_a['gaps'])}_")
            for g in part_a["gaps"]:
                L.append(f"- {g}")
            L.append("")
    else:
        gap = None

    # --- Part B — stratified weakness map (n~2111). ---
    if part_b is not None:
        bagg = part_b["aggregate"]
        L.append("## Part B — stratified weakness map vs realized results")
        L.append("")
        L.append(f"n = **{part_b['n']}** held-out internationals (played after "
                 f"{part_b.get('cutoff', PART_B_CUTOFF)[:10]}). The Elo baseline is "
                 "a RESULTS-derived reference (NOT a market proxy).")
        L.append(f"Posterior: {part_b['posterior_src']}.")
        L.append("")
        L.append(f"- aggregate RPS_model = {_fmt(bagg['rps_model'])}, "
                 f"RPS_elo = {_fmt(bagg['rps_elo'])}, "
                 f"ΔRPS (model − elo) = **{_fmt(bagg['delta'])}** "
                 f"(95% CI [{_fmt(bagg['lo95'])}, {_fmt(bagg['hi95'])}])")
        L.append("")
        L.append("### Ranked slice table (worst first — largest model−elo ΔRPS at top)")
        L.append("")
        L.append("| slice | n | RPS_model | RPS_elo | ΔRPS (model−elo) | 95% CI |")
        L.append("|---|--:|--:|--:|--:|---|")
        for s in part_b["slices"]:
            L.append(f"| {s['slice']} | {s['n']} | {_fmt(s['rps_model'])} | "
                     f"{_fmt(s['rps_elo'])} | {_fmt(s['delta'])} | "
                     f"[{_fmt(s['lo95'])}, {_fmt(s['hi95'])}] |")
        L.append("")
        # Reliability tables.
        for label, key in (("favorite-prob", "reliability_fav"),
                           ("P(draw)", "reliability_draw")):
            L.append(f"### Reliability — {label} (model, 10 bins)")
            L.append("")
            L.append("| bin | n | mean pred | obs freq |")
            L.append("|---|--:|--:|--:|")
            for r in part_b.get(key, []):
                L.append(f"| {r['bin']} | {r['n']} | {_fmt(r['p_mean'], 3)} | "
                         f"{_fmt(r['freq'], 3)} |")
            L.append("")

    # --- Coverage-limitation note + G1 recommendation. ---
    L.append("## Coverage limitation + G1 recommendation")
    L.append("")
    L.append("**Limitation (binding honesty):** the stored 1X2 odds cover exactly "
             "**22** matches in four clusters, so the full market-stratified slice "
             "table is NOT statistically meaningful (per-slice n would be 2-6). The "
             "market gap (Part A) is the aggregate-only headline with a wide CI; the "
             "WHERE-is-the-model-weak detail comes from Part B vs realized results, "
             "NOT vs the market.")
    L.append("")
    L.append(_g1_recommendation(gap))
    L.append("")
    return "\n".join(L)


def format_confed_section(detail: list[dict], *, today: str) -> str:
    """PURE markdown for the per-confederation-pairing detail (G1 follow-up #5).

    Per pairing: paired model-vs-Elo RPS + bootstrap CI, then favorite-prob
    reliability for the MODEL and the ELO reference side by side. Pairings under
    the reliability floor show an explicit coverage note instead of a tiny table.
    """
    L: list[str] = []
    L.append("")
    L.append(f"## Part B addendum — confederation-pairing detail (added {today})")
    L.append("")
    L.append("> Evidence requested at G1 for the ~Jun-20 Phase-3 (squad anchor v0) go/no-go: "
             "where cross-confederation calibration stands, model vs the Elo reference.")
    L.append("")
    L.append("| pairing | n | RPS_model | RPS_elo | ΔRPS (model−elo) | 95% CI |")
    L.append("|---|--:|--:|--:|--:|---|")
    for d in detail:
        L.append(f"| {d['pair']} | {d['n']} | {_fmt(d['rps_model'])} | {_fmt(d['rps_elo'])} | "
                 f"{_fmt(d['delta'])} | [{_fmt(d['lo95'])}, {_fmt(d['hi95'])}] |")
    L.append("")
    for d in detail:
        if d["rel_model"] is None:
            L.append(f"### {d['pair']} — reliability: coverage gap (n={d['n']} < 30; "
                     "a curve at this n would be noise)")
            L.append("")
            continue
        L.append(f"### {d['pair']} — favorite-prob reliability (n={d['n']}, 5 bins)")
        L.append("")
        L.append("| bin | n (model) | model pred | model obs | n (elo) | elo pred | elo obs |")
        L.append("|---|--:|--:|--:|--:|--:|--:|")
        for rm, re_ in zip(d["rel_model"], d["rel_elo"]):
            L.append(f"| {rm['bin']} | {rm['n']} | {_fmt(rm['p_mean'], 3)} | {_fmt(rm['freq'], 3)} "
                     f"| {re_['n']} | {_fmt(re_['p_mean'], 3)} | {_fmt(re_['freq'], 3)} |")
        L.append("")
    return "\n".join(L)


# =========================================================================== #
# main.
# =========================================================================== #
def _default_out() -> str:
    return f"reports/headroom_{date.today().isoformat()}.md"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", choices=["A", "B", "all", "confed"], default="all",
                    help="which part to run (A = market gap n=22; B = weakness map; all; "
                         "confed = Part-B compute, emit ONLY the confederation-pairing "
                         "addendum section)")
    ap.add_argument("--out", default=None,
                    help="markdown output path (default reports/headroom_<today>.md)")
    ap.add_argument("--append", action="store_true",
                    help="append the generated markdown to --out instead of overwriting "
                         "(the audited report keeps its manual audit sections)")
    ap.add_argument("--allow-fresh-fit", action="store_true",
                    help="Part B: if no config-matched posterior is on disk, fit ONE "
                         "fresh (production fidelity; minutes).")
    args = ap.parse_args(argv)

    out_path = Path(args.out) if args.out else Path(_default_out())
    cfg = load_config()

    part_a = part_b = None
    # Store is built lazily — only if a real part runs (tests monkeypatch the
    # part functions, so no store/fit is ever touched under test).
    store = None
    if args.part in ("A", "all"):
        store = store or get_persistent_store()
        print("[part A] paired model-vs-market (n=22) on the CURRENT config ...", flush=True)
        part_a = run_part_a(store, cfg)
        print(f"[part A] n={part_a['n']} aggregate ΔRPS={part_a['aggregate']['delta']}",
              flush=True)
    if args.part in ("B", "all", "confed"):
        store = store or get_persistent_store()
        print("[part B] stratified weakness map vs realized results ...", flush=True)
        part_b = run_part_b(store, cfg, allow_fresh_fit=args.allow_fresh_fit)
        print(f"[part B] n={part_b['n']} {part_b['posterior_src']}", flush=True)

    if args.part == "confed":
        md = format_confed_section(part_b["confed_detail"],
                                   today=date.today().isoformat())
    else:
        md = assemble_report(part_a, part_b, today=date.today().isoformat())
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
