"""Phase 4a + 4b — scoreline-distribution tail diagnostics (OFFLINE, READ-ONLY).

OPS-ONLY runner for the accuracy-upgrade mission's Phase 4. Spends ZERO Odds-API
credits (results store + cached posteriors only), makes NO ``model:`` / ``config:``
change, and never refits a production posterior (both posteriors are cached +
config-matched; a config-match MISS STOPS rather than refits — see
``_find_cached_production_posterior``). The 4b perturbation is a SIM-ONLY override
threaded through ``SimConfig.tail_fatten`` (off-state byte-identical), exactly the
``estimate_host_k.py::run_sensitivity`` pattern.

Pieces (THIN; the heavy ``run_4a`` / ``run_4b`` reuse the existing harness):

  * ``run_4a``         — REUSE the ``2024-06-01`` cached posterior; score the
                         held-out internationals; per |Elo-gap| bucket (Q1..Q4 +
                         a top-decile mismatch row) compare PREDICTED vs REALIZED
                         mass for the four tail markets (favorite scores >= 4,
                         |GD| >= 3, total >= 5, favorite wins by >= 2) with Wilson
                         CIs on the realized freq and a seeded paired-bootstrap CI
                         on the predicted-realized gap.
  * ``size_transform`` — PURE: the documented bucket-alpha sizing rule from the 4a
                         realized/predicted blowout ratios (clip(c*(ratio-1), 0,
                         ALPHA_MAX), monotone non-decreasing in |gap|, ALPHA_MAX cap).
  * ``run_4b``         — REUSE the CURRENT ``2026-06-10`` (fallback ``2026-06-07``)
                         cached posterior; build a per-fixture alpha closure from
                         its point-in-time ratings; run the production sim twice on
                         the SAME seed — baseline (``tail_fatten=None``) and perturbed
                         (the alpha closure) — and collect ``advance_from_group`` /
                         ``third`` (best-8) / ``champion`` (+ MC SE) for the hosts,
                         the top-8 champion board, and the third-place best-8 row.
  * ``decision``       — PURE: the brief's 2*SE rule (every |delta| < 2*SE -> NO-LIFT
                         and SKIP 4c; else 4c-GO naming the moved markets).
  * ``assemble_report``— PURE (dicts -> markdown): the 4a table, the transform +
                         alpha-vector, the before/after sim table, and EXACTLY ONE
                         of NO-LIFT / 4c-GO.

Usage (scripts run via ``PYTHONPATH=src .venv/bin/python``, NEVER ``uv run``)::

    PYTHONPATH=src .venv/bin/python scripts/diagnose_tails.py \
        --part 4a --out reports/tails_2026-06-10.md            # fast, offline (minutes)

    nohup env PYTHONPATH=src .venv/bin/python scripts/diagnose_tails.py \
        --part 4b --append --out reports/tails_2026-06-10.md \
        > logs/diagnose_tails_4b.log 2>&1 &                    # two 20k sims (detached)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.backtest import tails
from wcmodel.backtest.headroom import add_gap_quartiles
from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.sim.run import SimConfig, simulate
from wcmodel.sim.scoreline import bucket_alpha

# scripts/ is not a package on sys.path -> path-insert then import the established
# posterior-reuse + persistent-store + point-in-time Elo helpers (the house pattern,
# mirroring estimate_host_k.py). These spend ZERO credits.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_market_gap import (  # noqa: E402  (script-local import, after sys.path)
    _assert_no_leak,
    _elo_as_of_cutoff,
    _find_cached_production_posterior,
    _heldout_frame,
    get_persistent_store,
)

# --------------------------------------------------------------------------- #
# Constants.
# --------------------------------------------------------------------------- #
# 4a — the established calibration cutoff (the on-disk k=0.6 sweep posterior lives
# here; the held-out set is internationals played strictly after it).
PART_4A_CUTOFF = "2024-06-01T00:00:00Z"

# 4b — the CURRENT production posterior cutoffs (preferred first), mirroring the
# host_k sensitivity runner so the same on-disk netCDF is reused (no refit).
SENSITIVITY_CUTOFFS = ("2026-06-10T00:00:00Z", "2026-06-07T00:00:00Z")

HOST_TEAMS = ("United States", "Mexico", "Canada")
TOP8_N = 8
THIRD_BEST8_N = 8   # the 8 best third-placed teams advance from the group stage.

# The 4b decision rule's noise band: a market delta beyond ``DECISION_K * SE`` is
# "beyond Monte-Carlo noise" (the brief's ~2x SE rule).
DECISION_K = 2.0

# Transform sizing (spec 3.1): alpha_bucket = clip(SIZING_C * max(ratio - 1, 0), 0,
# ALPHA_MAX), markets' ratios averaged per bucket, monotone non-decreasing in |gap|,
# the worst bucket reaching the conservative cap ALPHA_MAX.
ALPHA_MAX = 0.5
# The blowout markets whose realized/predicted ratios drive the per-bucket sizing.
SIZING_MARKETS = ("fav_score_ge4", "abs_gd_ge3", "total_ge5", "fav_margin_ge2")

# The four tail markets in report order (key -> human label).
TAIL_MARKETS = {
    "fav_score_ge4": "P(fav scores >= 4)",
    "abs_gd_ge3": "P(|GD| >= 3)",
    "total_ge5": "P(total >= 5)",
    "fav_margin_ge2": "P(fav wins by >= 2)",
}

# The downstream markets compared baseline-vs-perturbed in 4b (the GD-tiebreaker-
# sensitive ``third`` best-8 occupancy is the most likely to move).
SIM_MARKETS = ("advance_from_group", "third", "champion")


# =========================================================================== #
# 4a — the tail diagnostic.
# =========================================================================== #
def _row_event_masses(post, home, away, neutral, *, max_goals=10):
    """The four PREDICTED tail masses for one fixture (favorite-oriented).

    ``predict_scoreline(neutral=<flag>, host_factor=None)`` exactly mirrors the
    headroom/host_k neutral handling — a historical international is never a 2026
    host game, so ``host_factor=None`` always; the per-match ``neutral`` flag drives
    the average-environment term. ``fav_is_home`` is decided by the caller (the
    point-in-time Elo gap) so predicted and realized are scored on the SAME favorite
    side. Returns ``None`` if either team is unknown to the posterior (coverage gap).
    """
    grid = post.predict_scoreline(home, away, neutral=neutral, max_goals=max_goals,
                                  host_factor=None)
    return grid


def run_4a(store, cfg: dict, *, allow_fresh_fit: bool = False) -> dict:
    """REUSE the ``2024-06-01`` cached posterior (config-match; STOP if miss); score
    the held-out internationals; per |Elo-gap| bucket compare predicted vs realized
    tail mass for the four markets with Wilson + bootstrap CIs.

    NO refit, NO model/config change — read-only diagnostic. A team unknown to the
    posterior or lacking a point-in-time rating is logged as a coverage gap, never
    imputed.
    """
    cutoff = PART_4A_CUTOFF
    max_train = _assert_no_leak(store, cutoff)   # structural leakage proof
    found = _find_cached_production_posterior(cutoff, cfg)
    if found is None:
        if not allow_fresh_fit:
            raise RuntimeError(
                "no config-matched production posterior on disk for the 4a cutoff "
                f"{cutoff[:10]} (k=0.6 sweep posterior); STOP — do NOT refit. Rerun "
                "with --allow-fresh-fit only if a fresh fit is intended (detached).")
        from model_market_gap import _fit_one  # noqa: E402
        post, fit_src, _prov = _fit_one(cutoff, store, cfg)
        src = f"FRESH-FIT {fit_src} / {cutoff[:10]}"
    else:
        post, nc_name, _prov = found
        src = f"REUSED {nc_name} (config-matched k=0.6 / {cutoff[:10]})"

    elo_ratings = _elo_as_of_cutoff(store, cutoff, cfg)
    heldout = _heldout_frame(store, cutoff)
    known = set(post.teams)

    # Per scored match: the bucket key (|gap|), predicted masses, realized indicators.
    recs: list[dict] = []
    gaps: list[str] = []
    for _, row in heldout.iterrows():
        home, away = str(row["home_team"]), str(row["away_team"])
        if home not in known or away not in known:
            gaps.append(f"{home} v {away} [team unknown to posterior]")
            continue
        if home not in elo_ratings or away not in elo_ratings:
            gaps.append(f"{home} v {away} [no point-in-time rating]")
            continue
        neutral = bool(row["neutral"])
        gap = elo_ratings[home] - elo_ratings[away]     # signed (home - away)
        fav_is_home = gap >= 0.0
        try:
            grid = _row_event_masses(post, home, away, neutral)
        except KeyError:
            gaps.append(f"{home} v {away} [predict_scoreline KeyError]")
            continue
        pred = tails.tail_masses(grid, fav_is_home=fav_is_home)
        real = tails.realized_tail_events(int(row["home_score"]), int(row["away_score"]),
                                          fav_is_home=fav_is_home)
        recs.append({"abs_gap": abs(float(gap)), "pred": pred, "real": real})

    # Quartile-bucket over the WHOLE scored frame (never per-row), then add the
    # top-decile mismatch row (the sharpest blowout test; overlaps Q4 by construction).
    n = len(recs)
    rows: list[dict] = []
    ratio_by_bucket: list[float] = [1.0, 1.0, 1.0, 1.0]
    buckets = ["Q1", "Q2", "Q3", "Q4", "top-decile"]
    if n:
        gap_df = add_gap_quartiles(pd.DataFrame({"elo_gap": [r["abs_gap"] for r in recs]}),
                                   col="elo_gap")
        for r, q in zip(recs, gap_df["elo_gap_q"]):
            r["bucket"] = q
        decile_cut = float(np.quantile([r["abs_gap"] for r in recs], 0.9))
        for r in recs:
            r["top_decile"] = r["abs_gap"] >= decile_cut

        seed = int(cfg["seed"])
        for bi, bname in enumerate(["Q1", "Q2", "Q3", "Q4"]):
            members = [r for r in recs if r["bucket"] == bname]
            mrows, bratios = _bucket_rows(bname, members, seed)
            rows.extend(mrows)
            ratio_by_bucket[bi] = bratios
        dec_members = [r for r in recs if r.get("top_decile")]
        drows, _dr = _bucket_rows("top-decile", dec_members, seed)
        rows.extend(drows)

    return {
        "n": n,
        "posterior_src": src,
        "cutoff": cutoff,
        "max_train": str(max_train.date()),
        "buckets": buckets,
        "edges": None,   # filled in by size_transform's caller from the quartile cuts
        "rows": rows,
        "ratio_by_bucket": ratio_by_bucket,
        "gaps": gaps,
    }


def _bucket_rows(bname: str, members: list[dict], seed: int):
    """Per-(bucket, market) rows + the bucket's average blowout ratio.

    For each market: n, mean predicted mass, realized freq + Wilson CI, the
    realized-predicted gap + a seeded paired-bootstrap CI, and the realized/predicted
    ratio. Returns ``(rows, avg_ratio)``.
    """
    rows: list[dict] = []
    nb = len(members)
    ratios: list[float] = []
    for mkey in TAIL_MARKETS:
        preds = np.array([m["pred"][mkey] for m in members], dtype=float)
        reals = np.array([m["real"][mkey] for m in members], dtype=float)
        pred_mean = float(preds.mean()) if nb else float("nan")
        k_real = int(reals.sum())
        real_freq = float(reals.mean()) if nb else float("nan")
        real_lo, real_hi = tails.wilson_ci(k_real, nb)
        gap = real_freq - pred_mean if nb else float("nan")
        gap_lo, gap_hi = _bootstrap_gap_ci(preds, reals, seed=seed)
        ratio = (real_freq / pred_mean) if (nb and pred_mean > 0) else float("nan")
        if np.isfinite(ratio):
            ratios.append(ratio)
        rows.append({
            "bucket": bname, "market": mkey, "n": nb,
            "pred": pred_mean, "real": real_freq, "real_lo": real_lo, "real_hi": real_hi,
            "gap": gap, "gap_lo": gap_lo, "gap_hi": gap_hi, "ratio": ratio,
        })
    avg_ratio = float(np.mean(ratios)) if ratios else 1.0
    return rows, avg_ratio


def _bootstrap_gap_ci(preds: np.ndarray, reals: np.ndarray, *, seed: int,
                      n_boot: int = 10_000) -> tuple:
    """Seeded paired bootstrap of ``mean(realized) - mean(predicted)`` over matches.

    Resamples whole matches with replacement (the (pred, real) pairing is preserved),
    recomputes the mean realized-minus-predicted gap, and returns the 2.5 / 97.5
    percentile bounds. Empty input -> ``(nan, nan)``. Deterministic for a fixed seed.
    """
    nb = len(preds)
    if nb == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, nb, size=(n_boot, nb))
    boot = reals[idx].mean(axis=1) - preds[idx].mean(axis=1)
    return (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5)))


# =========================================================================== #
# size_transform — the bucket-alpha sizing rule (PURE).
# =========================================================================== #
def size_transform(table_4a: dict) -> dict:
    """The documented per-|gap|-bucket tail-fatten alpha vector from the 4a ratios.

    ``alpha_bucket = clip(c * max(ratio - 1, 0), 0, ALPHA_MAX)`` with the blowout
    markets' realized/predicted ratios already averaged per bucket
    (``ratio_by_bucket``), the scale ``c`` chosen so the WORST bucket's alpha reaches
    the conservative cap ``ALPHA_MAX`` (when any misfit exists), and alpha forced
    monotone non-decreasing in |gap| (the high-mismatch buckets get the most
    fattening). If NO misfit (ratios <= 1 everywhere) -> alpha == 0 everywhere (the
    honest NO-MISFIT near-no-op). PURE.
    """
    ratios = [float(r) for r in table_4a["ratio_by_bucket"]]
    excess = [max(r - 1.0, 0.0) for r in ratios]
    worst = max(excess) if excess else 0.0
    if worst <= 0.0:
        # No bucket under-predicts blowouts -> identity transform (NO-MISFIT path).
        alpha = [0.0 for _ in excess]
    else:
        # Scale so the worst bucket hits the cap; clip; then enforce monotone-in-|gap|
        # by a running max (Q1..Q4 are ascending |gap| bands).
        c = ALPHA_MAX / worst
        raw = [min(max(c * e, 0.0), ALPHA_MAX) for e in excess]
        alpha, run = [], 0.0
        for a in raw:
            run = max(run, a)
            alpha.append(run)
    return {"edges": table_4a["edges"], "alpha_by_bucket": alpha}


# =========================================================================== #
# 4b — sim-only sensitivity orchestration.
# =========================================================================== #
def _ratings_for_fixtures(post, store, cutoff: str, cfg: dict) -> dict:
    """Point-in-time ``{team: rating_pre}`` as of ``cutoff`` for the alpha closure.

    The SAME leakage-safe ``_elo_as_of_cutoff`` ratings 4a buckets on; the 4b alpha
    closure reads them to map each in-sim fixture's |Elo gap| to its bucket alpha.
    (``post`` is accepted for symmetry with the host_k pattern / future overrides.)
    """
    return _elo_as_of_cutoff(store, cutoff, cfg)


def _make_alpha_closure(ratings: dict, alpha_by_bucket, edges):
    """Build the per-fixture ``(home, away) -> alpha`` closure threaded into
    ``SimConfig.tail_fatten``.

    Reads the point-in-time ``ratings`` to form the signed Elo gap, then maps |gap|
    to its bucket alpha via the sim's own ``bucket_alpha`` (same edges as 4a). A
    fixture with an unrated team falls back to alpha 0.0 (no fattening — the honest
    no-info default).
    """
    def alpha(home, away) -> float:
        rh, ra = ratings.get(home), ratings.get(away)
        if rh is None or ra is None:
            return 0.0
        return bucket_alpha(rh - ra, alpha_by_bucket, edges)
    return alpha


def run_4b(store, cfg: dict, alpha_by_bucket, edges, *,
           allow_fresh_fit: bool = False) -> dict:
    """REUSE the CURRENT cached production posterior (NO refit); run the production
    sim baseline (``tail_fatten=None``) vs perturbed (the alpha closure) at the SAME
    seed; collect the downstream markets + the 2*SE decision.

    The perturbation is a SIM-ONLY override (``SimConfig.tail_fatten``), the
    ``host_factor`` class of change — NO ``model:`` / ``config:`` field, NO fitted
    parameter, NO posterior change. If no config-matched posterior is on disk -> STOP
    (raise) unless ``allow_fresh_fit`` (detached fresh fit at the preferred cutoff).
    """
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
                f"{SENSITIVITY_CUTOFFS}; STOP — do NOT refit. Rerun with "
                "--allow-fresh-fit (detached) only if a fresh fit is intended.")
        from model_market_gap import _fit_one  # noqa: E402
        cutoff = SENSITIVITY_CUTOFFS[0]
        post, fit_src, _prov = _fit_one(cutoff, store, cfg)
        src = f"FRESH-FIT {fit_src} / {cutoff[:10]}"

    ratings = _ratings_for_fixtures(post, store, cutoff, cfg)
    alpha_fn = _make_alpha_closure(ratings, list(alpha_by_bucket), list(edges))

    # Paired comparison: baseline + perturbed on the SAME cached posterior + SAME seed,
    # so the only difference is the grid reshape (shared MC noise).
    base_cfg = SimConfig.from_config(cfg)                       # tail_fatten=None
    fat_cfg = SimConfig.from_config(cfg)
    fat_cfg = _with_tail_fatten(fat_cfg, alpha_fn)
    cut_ts = pd.Timestamp(cutoff).normalize()
    base = simulate(cut_ts, post, store, base_cfg)
    fat = simulate(cut_ts, post, store, fat_cfg)

    out = _shape_4b(base, fat, cutoff=cutoff, posterior_src=src, n_sims=base_cfg.n_sims,
                    seed=base_cfg.seed)
    return out


def _with_tail_fatten(simcfg: SimConfig, alpha_fn) -> SimConfig:
    """Return a copy of ``simcfg`` with ``tail_fatten`` set (SimConfig is frozen)."""
    import dataclasses
    return dataclasses.replace(simcfg, tail_fatten=alpha_fn)


def _shape_4b(base, fat, *, cutoff, posterior_src, n_sims, seed) -> dict:
    """Collect the before/after downstream markets + the 2*SE decision from the two
    ``SimResult``s (baseline vs perturbed).

    Hosts: champion + advance_from_group (base/fat/SE). Board: the top-8 champion
    board (base ordering). Third best-8: the 8 highest ``third`` occupancies. The
    decision feeds ``decision`` the per-market |delta| vs the baseline SE for every
    team's tracked markets.
    """
    pb, sb = base.progression, base.se
    pf = fat.progression

    hosts: dict[str, dict] = {}
    for team in HOST_TEAMS:
        if team in pb.index:
            hosts[team] = {
                m: {"base": float(pb.loc[team, m]), "fat": float(pf.loc[team, m]),
                    "se": float(sb.loc[team, m])}
                for m in ("champion", "advance_from_group")
            }

    board_idx = pb["champion"].sort_values(ascending=False).head(TOP8_N).index
    board_base = [{"team": str(t), "champion": float(pb.loc[t, "champion"]),
                   "se": float(sb.loc[t, "champion"])} for t in board_idx]
    board_fat = [{"team": str(t), "champion": float(pf.loc[t, "champion"]),
                  "se": float(sb.loc[t, "champion"])} for t in board_idx]

    third_idx = pb["third"].sort_values(ascending=False).head(THIRD_BEST8_N).index
    third_best8 = [{"team": str(t), "base": float(pb.loc[t, "third"]),
                    "fat": float(pf.loc[t, "third"]), "se": float(sb.loc[t, "third"])}
                   for t in third_idx]

    # Build the deltas / SEs the decision rule consumes: per market, every team's
    # |perturbed - baseline| against the baseline MC SE.
    deltas: dict[str, dict] = {m: {} for m in SIM_MARKETS}
    ses: dict[str, dict] = {m: {} for m in SIM_MARKETS}
    for m in SIM_MARKETS:
        if m not in pb.columns:
            continue
        for team in pb.index:
            deltas[m][str(team)] = float(pf.loc[team, m] - pb.loc[team, m])
            ses[m][str(team)] = float(sb.loc[team, m])

    return {
        "cutoff": cutoff,
        "posterior_src": posterior_src,
        "n_sims": int(n_sims),
        "seed": int(seed),
        "hosts": hosts,
        "board_base": board_base,
        "board_fat": board_fat,
        "third_best8": third_best8,
        "decision": decision(deltas, ses),
    }


# =========================================================================== #
# decision — the brief's 2*SE rule (PURE).
# =========================================================================== #
def decision(deltas: dict, ses: dict) -> dict:
    """The brief's go/no-go: every market |delta| < ``DECISION_K`` * SE -> NO-LIFT
    (recommend SKIP 4c); else 4c-GO naming the markets/entities that moved.

    ``deltas`` / ``ses`` are ``{market: {entity: value}}`` (entity = team). PURE — no
    I/O, no sim. The verdict is EXACTLY ONE of ``NO-LIFT`` / ``4c-GO``.
    """
    moved: list[str] = []
    max_ratio = 0.0
    arg = None
    for market, by_entity in deltas.items():
        for entity, d in by_entity.items():
            se = float(ses.get(market, {}).get(entity, float("nan")))
            if not np.isfinite(se) or se <= 0.0:
                continue
            ratio = abs(float(d)) / se
            if ratio > max_ratio:
                max_ratio, arg = ratio, (market, entity, float(d), se)
            if ratio >= DECISION_K:
                moved.append(f"{market}: {entity} {100.0 * d:+.1f}pp "
                             f"(|delta|/SE = {ratio:.1f})")
    verdict = "4c-GO" if moved else "NO-LIFT"
    return {
        "verdict": verdict,
        "moved": moved,
        "max_ratio": float(max_ratio),
        "argmax": arg,
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


def _verdict_line(dec: dict) -> str:
    """The single machine-readable verdict line printed in the report + on stdout.

    Format::

        P4B VERDICT: NO-LIFT (max |delta|/SE = 1.3 < 2.0)
        P4B VERDICT: ABOVE-THRESHOLD (max |delta|/SE = 2.7 >= 2.0) -> 4c-GO
    """
    mr = float(dec.get("max_ratio", 0.0))
    if dec["verdict"] == "NO-LIFT":
        return f"P4B VERDICT: NO-LIFT (max |delta|/SE = {mr:.1f} < {DECISION_K:.1f})"
    return (f"P4B VERDICT: ABOVE-THRESHOLD (max |delta|/SE = {mr:.1f} >= "
            f"{DECISION_K:.1f}) -> 4c-GO")


def assemble_report(part_4a: dict, transform: dict, part_4b: dict | None,
                    *, today: str) -> str:
    """Assemble the Phase-4 tail report into one markdown string. PURE — no I/O.

    Carries the 4a per-bucket predicted-vs-realized table (with CIs + ratio), the
    transform definition + the alpha-vector, and — when 4b ran — the before/after sim
    table (hosts + top-8 board + third best-8) vs the MC SE plus EXACTLY ONE of
    NO-LIFT / 4c-GO. With ``part_4b=None`` it emits the 4a table + a 4b-pending note.
    """
    L: list[str] = []
    L.append(f"# Phase 4 — Scoreline-Tail Diagnostics — {today}")
    L.append("")
    L.append("> OFFLINE. Zero Odds-API credits. No `model:` / `config:` change "
             "(4a/4b only MEASURE; the 4b perturbation is a SIM-ONLY override on the "
             "cached posterior — the `host_factor` class of change). Both posteriors "
             "are CACHED + config-matched (no refit).")
    L.append("")

    # ---- 4a -------------------------------------------------------------- #
    L.append("## 4a — Predicted vs realized scoreline-tail mass (held-out)")
    L.append("")
    L.append(f"- Held-out scored matches: **n = {part_4a['n']}**")
    L.append(f"- Posterior: {part_4a['posterior_src']}")
    L.append(f"- Cutoff: `{part_4a['cutoff'][:10]}` (max train date "
             f"`{part_4a.get('max_train', 'n/a')}` < cutoff — leakage-safe)")
    if part_4a.get("gaps"):
        L.append(f"- Coverage gaps (NOT imputed): {len(part_4a['gaps'])}")
    L.append("")
    L.append("| Bucket | Market | n | Predicted | Realized (95% CI) | "
             "Realized−Predicted gap (95% CI) | Ratio |")
    L.append("|---|---|---:|---:|---|---|---:|")
    for r in part_4a["rows"]:
        real_ci = f"{_fmt(r['real'], 3)} [{_fmt(r['real_lo'], 3)}, {_fmt(r['real_hi'], 3)}]"
        gap_ci = f"{_fmt(r['gap'], 3)} [{_fmt(r['gap_lo'], 3)}, {_fmt(r['gap_hi'], 3)}]"
        # Carry BOTH the raw market key (`total_ge5` etc. — the apples-to-apples
        # event id) and the human label, so the table is self-describing.
        label = TAIL_MARKETS.get(r["market"], r["market"])
        market = f"`{r['market']}` ({label})"
        L.append(f"| {r['bucket']} | {market} | {r['n']} | {_fmt(r['pred'], 3)} | "
                 f"{real_ci} | {gap_ci} | {_fmt(r['ratio'], 2)} |")
    L.append("")
    L.append("A real thin-tail misfit is realized **>** predicted (ratio > 1), "
             "concentrated in the high-|gap| buckets, with the gap CI excluding 0.")
    L.append("")

    # ---- transform ------------------------------------------------------- #
    L.append("## 4b transform — mean-preserving tail-fattening")
    L.append("")
    L.append("The 4b perturbation reuses the audited **mean-preserving** "
             "max-entropy mix (`widening.inflate_predictive`, mechanism-c) forced "
             "provisional, applied SIM-ONLY per fixture at a per-|gap|-bucket mix "
             "weight α (both marginal means preserved to machine precision; α=0 is "
             "the identity / byte-identical off-state).")
    L.append("")
    L.append(f"- Sizing rule: `α_bucket = clip(c·max(ratio−1, 0), 0, {ALPHA_MAX})`, "
             "blowout ratios averaged per bucket, monotone non-decreasing in |gap|.")
    edges = transform.get("edges")
    L.append(f"- |Elo-gap| bucket edges: `{edges}`")
    L.append(f"- **α-by-bucket** (Q1..Q4): `{[round(a, 3) for a in transform['alpha_by_bucket']]}`")
    L.append("")

    # ---- 4b -------------------------------------------------------------- #
    if part_4b is None:
        L.append("## 4b — sim sensitivity")
        L.append("")
        L.append("_4b sim sensitivity PENDING — run `--part 4b` (two 20k sims, "
                 "detached) to populate the before/after table + the verdict._")
        L.append("")
        return "\n".join(L) + "\n"

    nsims = part_4b["n_sims"]
    nsims_str = f"{nsims:,}"
    L.append("## 4b — tail-fatten sim sensitivity (baseline vs perturbed)")
    L.append("")
    L.append(f"- Posterior: {part_4b['posterior_src']}")
    L.append(f"- Cutoff: `{part_4b['cutoff'][:10]}` · n_sims = **{nsims_str}** · "
             f"seed = `{part_4b['seed']}` (baseline + perturbed share the seed — "
             "paired, shared MC noise).")
    L.append("")
    # Hosts.
    L.append("### Hosts")
    L.append("")
    L.append("| Host | Market | Baseline | Perturbed | Δ | MC SE | |Δ|/SE |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for team, mk in part_4b["hosts"].items():
        for m, cell in mk.items():
            d = cell["fat"] - cell["base"]
            se = cell["se"]
            ratio = abs(d) / se if se > 0 else float("nan")
            L.append(f"| {team} | {m} | {_pct(cell['base'])} | {_pct(cell['fat'])} | "
                     f"{_pct(d, 2)} | {_pct(se, 2)} | {_fmt(ratio, 1)} |")
    L.append("")
    # Champion board.
    L.append("### Top-8 champion board")
    L.append("")
    L.append("| Team | Baseline | Perturbed | Δ | MC SE | |Δ|/SE |")
    L.append("|---|---:|---:|---:|---:|---:|")
    fat_by_team = {b["team"]: b["champion"] for b in part_4b["board_fat"]}
    for b in part_4b["board_base"]:
        fatv = fat_by_team.get(b["team"], b["champion"])
        d = fatv - b["champion"]
        se = b["se"]
        ratio = abs(d) / se if se > 0 else float("nan")
        L.append(f"| {b['team']} | {_pct(b['champion'])} | {_pct(fatv)} | "
                 f"{_pct(d, 2)} | {_pct(se, 2)} | {_fmt(ratio, 1)} |")
    L.append("")
    # Third-place best-8 occupancy.
    L.append("### Third-place best-8 occupancy (the GD-tiebreaker-sensitive market)")
    L.append("")
    L.append("| Team | Baseline | Perturbed | Δ | MC SE | |Δ|/SE |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for t in part_4b["third_best8"]:
        d = t["fat"] - t["base"]
        se = t["se"]
        ratio = abs(d) / se if se > 0 else float("nan")
        L.append(f"| {t['team']} | {_pct(t['base'])} | {_pct(t['fat'])} | "
                 f"{_pct(d, 2)} | {_pct(se, 2)} | {_fmt(ratio, 1)} |")
    L.append("")

    # ---- verdict (EXACTLY ONE) ------------------------------------------- #
    dec = part_4b["decision"]
    L.append("## Recommendation")
    L.append("")
    L.append("```")
    L.append(_verdict_line(dec))
    L.append("```")
    L.append("")
    if dec["verdict"] == "NO-LIFT":
        L.append("**NO-LIFT** — every downstream market delta is within Monte-Carlo "
                 f"noise (< {DECISION_K:.0f}×SE). Thin tails are COSMETIC: the GD "
                 "tiebreakers (the only downstream consumer of grid shape) do not "
                 "move beyond noise. **Recommend SKIPPING 4c** — no likelihood/"
                 "widening change.")
    else:
        L.append(f"**4c-GO** — markets move beyond {DECISION_K:.0f}×SE; "
                 "**recommend 4c proceed**. Moved:")
        for m in dec["moved"]:
            L.append(f"- {m}")
    L.append("")
    return "\n".join(L) + "\n"


# =========================================================================== #
# CLI.
# =========================================================================== #
def _default_out() -> str:
    return f"reports/tails_{date.today().isoformat()}.md"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", choices=["4a", "4b", "all"], default="all",
                    help="which part to run (4a tail tables / 4b sim sensitivity / all).")
    ap.add_argument("--out", default=None,
                    help="markdown output path (default reports/tails_<today>.md).")
    ap.add_argument("--append", action="store_true",
                    help="append the generated markdown to --out instead of overwriting.")
    ap.add_argument("--allow-fresh-fit", action="store_true",
                    help="if no config-matched posterior is on disk, fit ONE fresh "
                         "(production fidelity; run detached). Default STOPS + reports.")
    args = ap.parse_args(argv)

    out_path = Path(args.out) if args.out else Path(_default_out())
    cfg = load_config()
    store = get_persistent_store()

    part_4a = transform = part_4b = None
    if args.part in ("4a", "all"):
        print("[4a] reusing the cached 2024-06-01 posterior; scoring the held-out "
              "internationals ...", flush=True)
        part_4a = run_4a(store, cfg, allow_fresh_fit=args.allow_fresh_fit)
        print(f"[4a] n={part_4a['n']} scored; {part_4a['posterior_src']}", flush=True)
        if part_4a["gaps"]:
            print(f"[4a] coverage gaps (not imputed): {len(part_4a['gaps'])}", flush=True)
        # The transform sizing needs the quartile edges; derive them from the cut.
        part_4a["edges"] = _quartile_edges_from_rows(store, cfg)
        transform = size_transform(part_4a)
        print(f"[4a] α-by-bucket = {[round(a, 3) for a in transform['alpha_by_bucket']]} "
              f"(edges {transform['edges']})", flush=True)

    if args.part in ("4b", "all"):
        if transform is None:
            # 4b run alone needs the α-vector + edges: derive them from a fresh 4a pass.
            print("[4b] no in-memory transform; running 4a to derive the α-vector ...",
                  flush=True)
            part_4a = run_4a(store, cfg, allow_fresh_fit=args.allow_fresh_fit)
            part_4a["edges"] = _quartile_edges_from_rows(store, cfg)
            transform = size_transform(part_4a)
        print("[4b] reusing the cached production posterior; running the 20k sim "
              "baseline + perturbed (same seed) ...", flush=True)
        part_4b = run_4b(store, cfg, transform["alpha_by_bucket"], transform["edges"],
                         allow_fresh_fit=args.allow_fresh_fit)
        print(f"[4b] {part_4b['posterior_src']}", flush=True)
        print(_verdict_line(part_4b["decision"]), flush=True)

    md = assemble_report(part_4a, transform, part_4b, today=date.today().isoformat())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.append:
        with out_path.open("a") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print(f"[report] appended to {out_path}", flush=True)
    else:
        out_path.write_text(md)
        print(f"[report] wrote {out_path}", flush=True)
    return 0


def _quartile_edges_from_rows(store, cfg: dict) -> list:
    """The interior |Elo-gap| quartile edges over the held-out scored frame.

    The transform's ``bucket_alpha`` maps a |gap| to its bucket via these interior
    cut points (``len == n_buckets - 1 == 3``). Computed from the SAME held-out frame
    + point-in-time ratings 4a buckets on, so the sim alpha closure and the 4a table
    share the bands. Coverage gaps are dropped (matching 4a). Returns three floats.
    """
    cutoff = PART_4A_CUTOFF
    elo = _elo_as_of_cutoff(store, cutoff, cfg)
    heldout = _heldout_frame(store, cutoff)
    found = _find_cached_production_posterior(cutoff, cfg)
    known = set(found[0].teams) if found is not None else None
    absgaps = []
    for _, row in heldout.iterrows():
        h, a = str(row["home_team"]), str(row["away_team"])
        if known is not None and (h not in known or a not in known):
            continue
        if h not in elo or a not in elo:
            continue
        absgaps.append(abs(elo[h] - elo[a]))
    if not absgaps:
        return [100.0, 250.0, 450.0]
    qs = np.quantile(absgaps, [0.25, 0.5, 0.75])
    return [float(q) for q in qs]


if __name__ == "__main__":
    raise SystemExit(main())
