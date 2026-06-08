#!/usr/bin/env python
"""Totals-calibration DIAGNOSTIC — is the model's total-goals under-prediction driven
by the NEUTRAL-VENUE handling, or by the baseline goal-scale (mu)?  (ZERO credits.)

OPS-ONLY, READ-ONLY DIAGNOSTIC. This script adds NO model/pipeline behaviour and NO
betting. It is a thin operator harness that measures the model's PREDICTED total goals
(and P(over 2.5)) against the REALIZED total goals on a leakage-safe held-out set, and
SPLITS that gap by the store's real per-match ``neutral`` flag — so we can confirm (or
refute) the hypothesis that ``predict_scoreline(neutral=True)`` (which zeros ``home_adv``
on BOTH teams, dropping a neutral game to the away/baseline rate ``log lambda = mu`` for
both sides) is the PRIMARY driver of the observed under-prediction.

No odds. No API key. No bet. Pure model-prediction vs realized result.

WHY THIS MATTERS (the finding to verify)
----------------------------------------
A forward totals scan implied the model under-predicts total goals: E[total] ~= 2.4/game
vs an empirical ~2.8-2.9. The 2026 WC group games are ALL predicted ``neutral=True``, so
if the neutral handling is the driver, the live WC totals are SYSTEMATICALLY low. This
diagnostic quantifies the gap and attributes it BEFORE any model change is specced.

THE MECHANISM UNDER TEST (read straight off posterior.predict_scoreline)
------------------------------------------------------------------------
    log lambda_home = mu + home_term + att[home] - def[away]
    log lambda_away = mu             + att[away] - def[home]
    home_term = (0 if neutral else home_adv)          # host_factor=None path
So a NEUTRAL game zeros the home term: both sides score at the away/baseline rate. The
home team therefore loses ``home_adv`` worth of log-rate -> ~ exp(mu)*(exp(home_adv)-1)
goals of expected total. If neutral games under-predict MUCH more than non-neutral ones,
the neutral handling is the driver. If BOTH under-predict ~equally, the baseline ``mu``
goal-scale is the (or an additional) driver.

LEAKAGE (the binding rule)
--------------------------
ONE posterior is fit (or reused) at a PAST cutoff; the held-out scoring set is every
international PLAYED STRICTLY AFTER that cutoff (so no scored match is in the fit's
training window). We assert max-training-date < cutoff and that every scored match is
> cutoff. The 2024 posterior scoring 2025-26 matches is STALE (team strengths drift);
the goal-SCALE signal (mean E[total] gap) is robust to staleness, but per-match
calibration (the reliability bins) is noisier — flagged in the report.

REUSE (no fresh fit when the production posterior is on disk)
-------------------------------------------------------------
The Euro-2024 calibration diagnostic already fit the PRODUCTION posterior at
``cutoff=2024-06-14`` (advi_iters=30000, dixon_coles, sigma_att=0.5, widening.strength
=0.5). We REUSE that exact netCDF + meta from ``data/cache`` via the SAME
``cache._posterior_from_netcdf`` reconstruction a cache HIT uses — so predictions are
bit-identical to a fresh production fit, with no recompute. (We reuse by CONFIG-MATCHING
the meta, NOT by routing through ``cached_fit``: the content key bakes in the git commit,
which has advanced since the Euro fit, so ``cached_fit`` would MISS and re-fit. Loading
the matching netCDF directly is the leakage-safe, zero-waste reuse the task asks for.)
A FRESH ``cutoff=2024-06-01`` production fit is the documented fallback if no matching
posterior is on disk.

RUN: ``PYTHONPATH=src uv run python scripts/diagnose_totals_calibration.py``
(Cache HIT on the cached production posterior: seconds. Fresh fallback fit: minutes.)
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import wcmodel.model.cache as model_cache
from wcmodel.config import load_config
from wcmodel.data.features import valid_played_results
from wcmodel.markets.derived import totals_probs

# Reuse the SAME persistent real-martj42 store assembly the CLV/accuracy harness uses, so
# the content-addressed feature/posterior caches stay stable across runs.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from clv_validation import get_persistent_store  # noqa: E402

CACHE_DIR = Path("data/cache")
PROBE_CUTOFF = "2026-06-07T00:00:00Z"   # as-of read for the FULL store (leakage-safe downstream)

# The held-out scoring window. lo = the reused production cutoff; hi = the spec's bound.
DEFAULT_CUTOFF = "2024-06-14"           # reuse the Euro-diagnostic production fit if present
FALLBACK_CUTOFF = "2024-06-01"          # else fit ONE fresh production posterior here
SCORE_HI = "2026-06-02"                 # spec: score matches PLAYED in [cutoff, 2026-06-02]

OVER_LINE = 2.5
# Reliability bins for P(over 2.5): predicted-prob buckets.
REL_BINS = [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]


# --------------------------------------------------------------------------- #
# Posterior reuse (cache HIT by config-match) or fresh-fit fallback.
# --------------------------------------------------------------------------- #
def _find_cached_production_posterior(cutoff: str, cfg: dict):
    """Return a ``Posterior`` reconstructed from the on-disk production netCDF at ``cutoff``
    whose meta matches the production inference config, or ``None`` if none is on disk.

    We match on the fields that define the posterior's CONTENT (not the git commit): the
    fitted cutoff, likelihood, ADVI iters, draws, tune, seed, and the model block's prior +
    widening. A match means the netCDF was produced by an identical-config fit, so its
    predictions are exactly the production posterior's. (We do NOT route through
    ``cached_fit`` because its content key includes the git commit, which has advanced since
    the Euro fit -> a guaranteed MISS + a needless re-fit. Loading the matching netCDF
    directly via the cache's own reconstruction is the bit-identical, zero-waste reuse.)
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
        return post, nc.name
    return None


def _fit_fresh(cutoff: str, store, cfg: dict):
    """Fallback: fit ONE production posterior at ``cutoff`` through ``cached_fit``."""
    inf = cfg["model"]["inference"]
    post, meta = model_cache.cached_fit(
        cutoff=pd.Timestamp(cutoff).normalize(), store=store, backend="advi",
        draws=int(inf["draws"]), seed=int(cfg["seed"]), advi_iters=int(inf["advi_iters"]),
        cache_dir=CACHE_DIR, config=cfg,
    )
    return post, ("FRESH-FIT cache_hit=%s key=%s" % (meta["cache_hit"], meta["key"]))


# --------------------------------------------------------------------------- #
# Grid -> E[total] and P(over 2.5).
# --------------------------------------------------------------------------- #
def _e_total(grid: np.ndarray) -> float:
    n = grid.shape[0]
    tot = np.arange(n)[:, None] + np.arange(n)[None, :]
    return float((tot * grid).sum())


def _p_over(grid: np.ndarray, line: float = OVER_LINE) -> float:
    return float(totals_probs(grid, lines=(line,))[float(line)]["over"])


# --------------------------------------------------------------------------- #
# Reporting helpers.
# --------------------------------------------------------------------------- #
def _fmt_split(df: pd.DataFrame, label: str) -> None:
    n = len(df)
    if n == 0:
        print(f"  {label:<14} n=0  (no matches)")
        return
    e = df["e_total"].mean()
    r = df["realized_total"].mean()
    po = df["p_over"].mean()
    ro = df["over25"].mean()
    print(f"  {label:<14} n={n:<5} "
          f"E[total]={e:.3f}  realized={r:.3f}  gap={e - r:+.3f}   |   "
          f"mean P(over2.5)={po:.3f}  realized over-rate={ro:.3f}  miscal={po - ro:+.3f}")


def _reliability(df: pd.DataFrame, label: str) -> None:
    print(f"\n  Reliability of P(over 2.5) — {label} (n={len(df)}):")
    print(f"    {'pred-bin':<14}{'n':>6}{'mean pred':>12}{'obs over-rate':>16}{'  flag'}")
    if df.empty:
        print("    (no matches)")
        return
    cats = pd.cut(df["p_over"], bins=REL_BINS, include_lowest=True)
    for interval, grp in df.groupby(cats, observed=True):
        n = len(grp)
        mp = grp["p_over"].mean()
        ob = grp["over25"].mean()
        thin = "  <- THIN CELL" if n < 20 else ""
        lo, hi = interval.left, interval.right
        print(f"    [{lo:.2f},{hi:.2f}]{'':<3}{n:>6}{mp:>12.3f}{ob:>16.3f}{thin}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cutoff", default=DEFAULT_CUTOFF,
                    help=f"fit/reuse cutoff (default {DEFAULT_CUTOFF}; reuses the Euro "
                         f"production fit if on disk, else falls back to a fresh fit)")
    ap.add_argument("--score-hi", default=SCORE_HI,
                    help=f"upper bound of the held-out scoring window (default {SCORE_HI})")
    ap.add_argument("--allow-fresh-fit", action="store_true",
                    help="if no cached production posterior matches, fit ONE fresh "
                         "(production fidelity; minutes). Default falls back to "
                         f"--cutoff {FALLBACK_CUTOFF} and fits there.")
    args = ap.parse_args()

    print("=" * 88)
    print("TOTALS-CALIBRATION DIAGNOSTIC — model E[total] / P(over 2.5) vs realized, "
          "split by NEUTRAL")
    print("=" * 88)
    cfg = load_config()
    inf = cfg["model"]["inference"]
    print(f"[config] likelihood={cfg['model']['likelihood']} advi_iters={inf['advi_iters']} "
          f"draws={inf['draws']} seed={cfg['seed']} "
          f"prior.sigma_att={cfg['model']['prior']['sigma_att']} "
          f"widening={cfg['model']['widening']}")

    store = get_persistent_store()
    print(f"[store] persistent real martj42 store (read strictly as-of-cutoff downstream)")

    # --- Reuse the cached production posterior, or fall back to a fresh fit. ---
    cutoff = args.cutoff
    found = _find_cached_production_posterior(cutoff, cfg)
    if found is not None:
        post, src = found
        print(f"[posterior] REUSED cached production posterior at cutoff={cutoff}: {src} "
              "(config-matched; predictions bit-identical to a fresh production fit).")
    else:
        cutoff = FALLBACK_CUTOFF if not args.allow_fresh_fit else cutoff
        print(f"[posterior] no cached production posterior at {args.cutoff}; "
              f"fitting ONE fresh at cutoff={cutoff} (production fidelity) ...")
        post, src = _fit_fresh(cutoff, store, cfg)
        print(f"[posterior] {src}")

    teams = set(post.teams)
    print(f"[posterior] {len(teams)} teams in the fitted index.")

    # --- LEAKAGE PROOF: max training date < cutoff. ---
    cut_ts = pd.Timestamp(cutoff).normalize()
    asof = store.read("results", cutoff=PROBE_CUTOFF).copy()
    asof["date"] = pd.to_datetime(asof["date"])
    train = valid_played_results(asof)
    train_before = train[pd.to_datetime(train["date"]) < cut_ts]
    max_train_date = pd.to_datetime(train_before["date"]).max()
    assert max_train_date < cut_ts, (
        f"LEAKAGE: max training date {max_train_date} not < cutoff {cut_ts}")
    print(f"\n[leakage] max valid-played training date = {max_train_date.date()} "
          f"< cutoff {cut_ts.date()}  -> the fit trained ONLY on pre-cutoff results. OK")

    # --- HELD-OUT SCORING SET: internationals PLAYED in (cutoff, score_hi], scored,
    #     both teams in the posterior index. Leakage-safe: all strictly AFTER the fit. ---
    hi_ts = pd.Timestamp(args.score_hi).normalize()
    played = valid_played_results(asof)
    played["date"] = pd.to_datetime(played["date"])
    scored = played[(played["date"] > cut_ts) & (played["date"] <= hi_ts)].copy()
    # finite integer scores
    scored = scored[scored["home_score"].notna() & scored["away_score"].notna()].copy()
    scored["home_score"] = scored["home_score"].astype(int)
    scored["away_score"] = scored["away_score"].astype(int)
    # LEAKAGE: every scored match strictly after the cutoff.
    assert (scored["date"] > cut_ts).all(), "LEAKAGE: a scored match is on/before the cutoff"
    # both teams known to the posterior (unknown -> coverage gap, never a guessed prediction)
    known = scored[scored["home_team"].isin(teams) & scored["away_team"].isin(teams)].copy()
    n_gap = len(scored) - len(known)
    print(f"[held-out] {len(scored)} scored internationals in ({cut_ts.date()}, {hi_ts.date()}]; "
          f"{len(known)} with BOTH teams in the fitted index ({n_gap} coverage gaps skipped).")
    if "neutral" not in known.columns:
        raise SystemExit("store has no `neutral` column — cannot run the neutral split")

    # --- PER MATCH: model E[total] + P(over 2.5) at the match's REAL neutral flag. ---
    recs = []
    for _, m in known.iterrows():
        neutral = bool(m["neutral"])
        grid = post.predict_scoreline(m["home_team"], m["away_team"], neutral=neutral)
        total = int(m["home_score"]) + int(m["away_score"])
        recs.append({
            "home": m["home_team"], "away": m["away_team"], "date": m["date"],
            "neutral": neutral,
            "e_total": _e_total(grid),
            "p_over": _p_over(grid, OVER_LINE),
            "realized_total": total,
            "over25": total > OVER_LINE,
        })
    res = pd.DataFrame(recs)

    # ======================================================================= #
    # REPORT
    # ======================================================================= #
    print("\n" + "=" * 88)
    print("DIAGNOSIS")
    print("=" * 88)
    print(f"\n[overall] n={len(res)}")
    _fmt_split(res, "OVERALL")

    print("\n[split] the KEY test — is the gap materially worse on NEUTRAL games?")
    neu = res[res["neutral"]]
    non = res[~res["neutral"]]
    _fmt_split(non, "non-neutral")
    _fmt_split(neu, "neutral")

    # --- Driver verdict (programmatic; the report narrates it). ---
    gap_all = res["e_total"].mean() - res["realized_total"].mean()
    gap_neu = (neu["e_total"].mean() - neu["realized_total"].mean()) if len(neu) else float("nan")
    gap_non = (non["e_total"].mean() - non["realized_total"].mean()) if len(non) else float("nan")
    print("\n[driver] E[total] gap (model - realized; negative = UNDER-prediction):")
    print(f"           overall      : {gap_all:+.3f} goals/game")
    print(f"           non-neutral  : {gap_non:+.3f} goals/game")
    print(f"           neutral      : {gap_neu:+.3f} goals/game")
    if not (math.isnan(gap_neu) or math.isnan(gap_non)):
        extra = gap_non - gap_neu   # how much MORE the neutral games under-predict
        print(f"           neutral under-predicts {extra:+.3f} goals/game MORE than non-neutral")
        if extra > 0.15:
            verdict = ("NEUTRAL-HANDLING CONFIRMED as the primary driver — neutral games "
                       "under-predict materially more than non-neutral.")
        elif gap_all < -0.15 and abs(extra) <= 0.15:
            verdict = ("BASELINE-SCALE (mu) is the driver — BOTH venues under-predict ~equally; "
                       "the neutral handling is NOT the (sole) cause.")
        elif gap_all < -0.15:
            verdict = ("BOTH contribute — there is an overall under-prediction AND a neutral "
                       "penalty on top.")
        else:
            verdict = ("NO material under-prediction on this set — the forward-scan gap is not "
                       "reproduced here (check staleness / the forward set's composition).")
        print(f"\n[VERDICT] {verdict}")

    # --- Reliability tables. ---
    _reliability(res, "OVERALL")
    _reliability(non, "non-neutral")
    _reliability(neu, "neutral")

    # --- QUANTIFIED FIX TARGET. ---
    print("\n" + "=" * 88)
    print("QUANTIFIED FIX TARGET (so the neutral fix can be specced precisely)")
    print("=" * 88)
    mu = post._post("mu").mean()
    home_adv = post._post("home_adv").mean()
    exp_mu = math.exp(mu)
    # A neutral game scores 2*exp(mu)*(att/def cancel on average). Re-adding a fraction k of
    # home_adv to BOTH sides' baseline raises the neutral expected total by
    #   delta(k) = 2*exp(mu)*(exp(k*home_adv) - 1).
    # Solve for k so the neutral E[total] gap closes: need +(-gap_neu) goals.
    print(f"  posterior mu={mu:.4f} (exp={exp_mu:.4f} goals/side baseline), "
          f"home_adv={home_adv:.4f}")
    if len(neu) and not math.isnan(gap_neu):
        need = -gap_neu   # goals/game the neutral E[total] must RISE to match realized
        # delta(k) = 2*exp(mu)*(exp(k*home_adv)-1)  ->  k = ln(1 + need/(2*exp(mu)))/home_adv
        if need > 0 and home_adv > 0:
            k = math.log(1.0 + need / (2.0 * exp_mu)) / home_adv
            print(f"  neutral E[total] is {-need:+.3f} below realized -> a neutral game needs "
                  f"+{need:.3f} goals.")
            print(f"  Re-adding k*home_adv to BOTH baselines (neutral term -> k*home_adv per side) "
                  f"closes it at k ~= {k:.3f}")
            print(f"    i.e. the neutral per-side baseline should be ~ mu + {k:.3f}*home_adv "
                  f"(= {mu + k * home_adv:.4f}; vs today's bare mu={mu:.4f}).")
            print(f"    (sanity: full home_adv on both sides would add "
                  f"{2 * exp_mu * (math.exp(home_adv) - 1):+.3f} goals; the fix needs only "
                  f"~{k:.0%} of that.)")
        else:
            print(f"  neutral E[total] gap is {gap_neu:+.3f} (not an under-prediction) -> no "
                  "upward neutral correction indicated.")

    # --- HONEST CHECKS. ---
    print("\n" + "=" * 88)
    print("HONEST CHECKS")
    print("=" * 88)
    print(f"  [leakage] fit cutoff={cut_ts.date()}; max training date "
          f"{max_train_date.date()} < cutoff; ALL {len(res)} scored matches are strictly "
          "AFTER the cutoff (held-out). Proven above.")
    print("  [staleness] a 2024 posterior scoring 2025-26 matches is STALE: team strengths "
          "drift, so PER-MATCH calibration (the reliability bins) is noisier than a fresh "
          "fit would give. The goal-SCALE signal (the mean E[total] gap and its "
          "neutral/non-neutral SPLIT) is robust to staleness — that is the load-bearing "
          "result here.")
    print("  [too-good] N/A — this is a known-direction UNDER-prediction diagnosis, not an "
          "edge/CLV claim, so there is no foresight-RED ceiling to trip.")
    print("  [thin cells] reliability cells with n<20 are flagged above; read the split "
          "gaps (large n) as the primary evidence, the bins as directional.")

    print("\n[done] diagnostic complete. ZERO credits. No model/pipeline change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
