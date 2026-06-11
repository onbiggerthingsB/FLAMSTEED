#!/usr/bin/env python
"""P5 — inference-backend comparison harness (ONE backend per invocation).

WHAT THIS DOES
--------------
For the requested backend (``--backend advi|fullrank_advi|nuts``) it runs the
HOUSE held-out protocol — IDENTICAL to ``scripts/sweep_strength_k.py`` (and the
P2a/P2b sweeps): fit the production model at the ``2024-06-01`` cutoff
(production fidelity, NOT coarsened), then score held-out 1X2 RPS over the
valid-played internationals with ``date > cutoff`` (the leakage-guarded set,
n≈2,111 — never in the ``< cutoff`` fit). It additionally emits:

  * the mean held-out 1X2 RPS for the backend AND the Elo baseline over the
    matches both can price (apples-to-apples with every other house sweep);
  * FAVORITE and DRAW reliability curves (the binned tables, via the audited
    ``backtest.headroom.reliability_table`` — printed into the report);
  * wall-clock per fit (measured);
  * NUTS diagnostics (divergences / min-ESS / max-R-hat) where applicable, from
    ``model.inference.nuts_diagnostics`` on the FRESH fit (never a cache hit —
    sample_stats are not cached);
  * a PAIRED-BOOTSTRAP ΔRPS vs the advi baseline (the P2 ``headroom.bootstrap_delta_ci``
    machinery): ``delta = rps_backend − rps_advi`` with a seeded 95% CI. The
    baseline backend (advi) is read from an on-disk artifact written by the advi
    run, so each invocation stays single-backend (the controller runs them one at
    a time); the advi run writes the baseline, later runs read it.

PRE-REGISTERED ADOPTION GATES (encoded in the report)
-----------------------------------------------------
A backend is ADOPTED for the nightly loop IFF BOTH hold:

  (1) RPS LIFT beyond the paired-bootstrap CI: ``delta < 0`` AND ``hi95 < 0``
      (the whole 95% CI of ``rps_backend − rps_advi`` is below zero — a real,
      not-noise improvement over the advi baseline);
  (2) NIGHTLY-LOOP COMPATIBILITY: the PROJECTED full ``daily_update`` wall-clock
      ``<= ~60 min`` — computed as ``measured_fit_min + SIM_STAGE_REMAINDER_MIN``
      (the known ~10–15 min sim/stage/provenance tail) and PRINTED.

The machine-readable verdict is ONE line beginning ``P5 VERDICT: ``:

  * ``P5 VERDICT: ADOPT <backend> (...)``                      — (1) AND (2).
  * ``P5 VERDICT: DEEP-REFIT-ONLY CANDIDATE (<backend>; ...)`` — (1) holds but
    (2) fails (wins RPS, blows the runtime budget): recorded, NOT adopted nightly.
  * ``P5 VERDICT: NO-ADOPT <backend> (...)``                   — (1) fails (no
    RPS lift beyond the CI), regardless of runtime.
  * ``P5 VERDICT: BASELINE advi (...)``                        — the advi run
    itself (the reference; nothing to adopt over).

WIDENING RE-ABLATION (conditional second phase — controller-triggered)
----------------------------------------------------------------------
``--reablate-widening <backend>`` runs the P2-T6/M-T7 widening on/off ablation
UNDER that backend: two arms differing ONLY in ``model.widening`` (ON = the
configured mechanism/strength; OFF = strength 0.0, the in-range no-op the widening
module documents) scored with the SAME paired held-out RPS + paired bootstrap as
the main comparison. Emitted as a SEPARATE phase so the controller triggers it
only for the backend that wins on RPS.

COMPUTE / CREDITS
-----------------
OFFLINE: NO Odds API call, NO bet, NO spend (RPS is result-vs-prediction). The
real martj42 store + content-addressed caches are reused from ``clv_validation``
so a re-run of an already-fit (backend, cutoff) HITS disk. A single invocation
runs ONE backend (the watchdog/one-at-a-time design); see the LAUNCH BLOCK in the
staging report.

RUN: ``PYTHONPATH=src python scripts/compare_inference.py --backend nuts``
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.backtest.baselines import elo_baseline_1x2, model_fair_1x2, rps
from wcmodel.backtest.headroom import bootstrap_delta_ci, reliability_table
from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.elo import compute_elo_history
from wcmodel.data.features import valid_played_results
import wcmodel.model.cache as _model_cache
from wcmodel.model.inference import nuts_diagnostics

# Reuse the persistent real martj42 store + the offline result frame + the on-disk
# caches from the CLV harness so the held-out protocol is byte-stable with the
# rest of the house sweeps (a re-fit of an already-cached (backend, cutoff) HITS).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from clv_validation import (  # noqa: E402  (script-local import, after sys.path)
    CACHE_DIR,
    _martj42_results_frame,
    get_persistent_store,
)

#: The house held-out calibration cutoff (same as sweep_strength_k / P2a/P2b).
DEFAULT_CUTOFF = "2024-06-01T00:00:00Z"

#: The backends this harness compares. advi is the BASELINE every other backend is
#: scored against (paired bootstrap ΔRPS). pathfinder is excluded (unavailable).
BACKENDS = ("advi", "fullrank_advi", "nuts")

#: Known non-fit remainder of a full daily_update (sim 20k-MC + viewer stage +
#: provenance), in MINUTES. The runtime projection is measured_fit_min + this.
#: ~10–15 min in practice; we use the upper end (15) so the gate is CONSERVATIVE
#: (it must not ADOPT a backend that would in fact blow the budget on a bad night).
SIM_STAGE_REMAINDER_MIN = 15.0

#: The nightly-loop wall-clock budget (minutes). A backend whose projected full
#: daily_update exceeds this is runtime-INCOMPATIBLE -> at best DEEP-REFIT-ONLY.
NIGHTLY_BUDGET_MIN = 60.0

#: Where the advi BASELINE per-fixture (prob, outcome) rows are persisted so a
#: later single-backend run can compute the paired bootstrap ΔRPS against it.
def _baseline_path(cache_dir: Path, cutoff: str) -> Path:
    return Path(cache_dir) / f"p5-advi-baseline-{cutoff[:10]}.json"


# --------------------------------------------------------------------------- #
# Held-out protocol — IDENTICAL to scripts/sweep_strength_k.py (reused verbatim) #
# --------------------------------------------------------------------------- #
def _result_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def _heldout_frame(store, cutoff: str) -> pd.DataFrame:
    """Valid-played internationals with ``date > cutoff`` (the held-out set).

    Read as-of a far-future cutoff (every revision settled), then filter strictly
    after the calibration cutoff so the set is disjoint from the ``< cutoff`` fit
    window (the leakage guard). MIRRORS sweep_strength_k._heldout_frame."""
    played = _martj42_results_frame(store, "2026-06-07T00:00:00Z").copy()
    played["date"] = pd.to_datetime(played["date"])
    return played[played["date"] > pd.Timestamp(cutoff[:10])].reset_index(drop=True)


def _elo_as_of_cutoff(store, cutoff: str, config: dict) -> dict[str, float]:
    """Each team's LATEST pre-cutoff ``rating_pre`` (the Elo baseline strength).

    The SAME compute_elo_history the model feature uses, on the ``< cutoff``
    valid-played results (leakage-safe). MIRRORS sweep_strength_k._elo_as_of_cutoff."""
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


def _assert_no_leak(store, cutoff: str) -> pd.Timestamp:
    """Structural leakage proof: max valid-played training date < the cutoff.
    MIRRORS sweep_strength_k._assert_no_leak."""
    asof = store.read("results", cutoff=cutoff)
    asof_dates = pd.to_datetime(asof["date"])
    train = valid_played_results(asof.assign(date=asof_dates))
    max_train = pd.to_datetime(train["date"])
    max_train = max_train[max_train < pd.Timestamp(cutoff[:10])].max()
    assert max_train < pd.Timestamp(cutoff[:10]), (
        f"LEAKAGE: training max {max_train} not < cutoff {cutoff[:10]}")
    return max_train


# --------------------------------------------------------------------------- #
# PURE scoring + reliability + report (no fit / no I/O) — unit-tested.          #
# --------------------------------------------------------------------------- #
def score_backend(post, heldout: pd.DataFrame, elo_ratings: dict, config: dict) -> dict:
    """Held-out 1X2 RPS + per-fixture rows + reliability inputs for ONE posterior.

    Over every held-out match BOTH the model and Elo can price (both teams in the
    posterior's training set AND Elo-rated — the SAME priceable-set discipline as
    sweep_strength_k._score_k), score the model and Elo 1X2 RPS. Returns:

      ``{"model_rps", "elo_rps", "n", "rows", "fav_probs", "fav_hits",
         "draw_probs", "draw_hits"}``

    where ``rows`` is ``[{"p_model": (h,d,a), "p_ref": (h,d,a), "outcome":
    "H"|"D"|"A"}, ...]`` in the ``headroom`` row contract (so the SAME rows feed
    both the Elo-baseline paired delta AND, later, the cross-backend paired
    bootstrap), and the ``fav_*`` / ``draw_*`` lists feed the reliability tables:
      * FAVORITE: predicted prob of the model's most-likely 1X2 outcome vs whether
        that outcome occurred;
      * DRAW: predicted draw prob vs whether the match drew.
    """
    known = set(post.teams)
    model_rps_vals: list[float] = []
    elo_rps_vals: list[float] = []
    rows: list[dict] = []
    fav_probs: list[float] = []
    fav_hits: list[bool] = []
    draw_probs: list[float] = []
    draw_hits: list[bool] = []
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
        elo = elo_baseline_1x2(rating_home=elo_ratings[home],
                               rating_away=elo_ratings[away],
                               neutral=neutral, config=config)
        model_rps_vals.append(rps(model, outcome))
        elo_rps_vals.append(rps(elo, outcome))
        # headroom row contract: ordered (home, draw, away) triples + H/D/A label.
        letter = {"home": "H", "draw": "D", "away": "A"}[outcome]
        rows.append({
            "p_model": (model["home"], model["draw"], model["away"]),
            "p_ref": (elo["home"], elo["draw"], elo["away"]),
            "outcome": letter,
        })
        # FAVORITE reliability: the model's argmax outcome + whether it landed.
        fav_outcome = max(("home", "draw", "away"), key=lambda o: model[o])
        fav_probs.append(float(model[fav_outcome]))
        fav_hits.append(fav_outcome == outcome)
        # DRAW reliability: predicted draw prob vs realised draw.
        draw_probs.append(float(model["draw"]))
        draw_hits.append(outcome == "draw")
        n += 1
    return {
        "model_rps": float(np.mean(model_rps_vals)) if model_rps_vals else float("nan"),
        "elo_rps": float(np.mean(elo_rps_vals)) if elo_rps_vals else float("nan"),
        "n": n,
        "rows": rows,
        "fav_probs": fav_probs, "fav_hits": fav_hits,
        "draw_probs": draw_probs, "draw_hits": draw_hits,
    }


def paired_delta_vs_baseline(backend_rows: list[dict], baseline_rows: list[dict],
                             *, seed: int, n_boot: int = 10_000) -> dict:
    """Paired-bootstrap ΔRPS = ``rps_backend − rps_advi`` over the COMMON fixtures.

    Reuses the audited P2 ``headroom.bootstrap_delta_ci`` by re-pairing: a single
    eval row is ``{"p_model": backend_probs, "p_ref": advi_probs, "outcome": ...}``
    so the bootstrap's ``delta = rps_model − rps_ref`` is exactly the backend-minus-
    advi paired difference. The two row-lists MUST be aligned over the same fixtures
    in the same order (the harness scores both arms over the identical held-out
    frame, so they are). A negative ``delta`` with ``hi95 < 0`` is the RPS-lift gate.

    Returns ``{"delta", "lo95", "hi95", "n"}``. Mismatched lengths (a backend
    priced a different sub-set, e.g. fewer teams) are intersected to the common
    prefix length defensively and flagged via ``n``."""
    n = min(len(backend_rows), len(baseline_rows))
    paired = [
        {"p_model": backend_rows[i]["p_model"],
         "p_ref": baseline_rows[i]["p_ref" if "p_ref" in baseline_rows[i] else "p_model"],
         "outcome": backend_rows[i]["outcome"]}
        for i in range(n)
    ]
    ci = bootstrap_delta_ci(paired, n_boot=n_boot, seed=seed)
    ci["n"] = n
    return ci


def project_runtime_min(fit_min: float, remainder_min: float = SIM_STAGE_REMAINDER_MIN) -> float:
    """Projected full daily_update wall-clock = measured fit + known sim/stage tail."""
    return float(fit_min) + float(remainder_min)


def rps_lift_passes(delta_ci: dict) -> bool:
    """Gate (1): the WHOLE paired-bootstrap 95% CI of (rps_backend − rps_advi) is
    below zero (delta<0 AND hi95<0) — a real RPS lift, not noise. NaN -> False."""
    d, hi = delta_ci.get("delta"), delta_ci.get("hi95")
    if d is None or hi is None:
        return False
    try:
        return float(d) < 0.0 and float(hi) < 0.0
    except (TypeError, ValueError):
        return False


def runtime_compatible(projected_min: float, budget_min: float = NIGHTLY_BUDGET_MIN) -> bool:
    """Gate (2): projected full daily_update wall-clock within the nightly budget."""
    try:
        return float(projected_min) <= float(budget_min)
    except (TypeError, ValueError):
        return False


def verdict_line(*, backend: str, is_baseline: bool, delta_ci: dict | None,
                 projected_min: float | None) -> str:
    """The ONE machine-readable ``P5 VERDICT: ...`` line (the grammar the
    controller greps). See the module docstring for the four forms."""
    if is_baseline:
        return (f"P5 VERDICT: BASELINE {backend} "
                "(reference for the paired-bootstrap ΔRPS; nothing to adopt over)")
    lift = rps_lift_passes(delta_ci or {})
    compat = runtime_compatible(projected_min if projected_min is not None else float("inf"))
    d = (delta_ci or {}).get("delta")
    hi = (delta_ci or {}).get("hi95")
    rps_note = (f"ΔRPS={d:+.5f} (95% CI hi={hi:+.5f})"
                if d is not None and hi is not None else "ΔRPS=unavailable")
    rt_note = (f"projected daily_update≈{projected_min:.1f} min vs budget "
               f"{NIGHTLY_BUDGET_MIN:.0f} min"
               if projected_min is not None else "runtime=unavailable")
    if lift and compat:
        return f"P5 VERDICT: ADOPT {backend} ({rps_note}; {rt_note})"
    if lift and not compat:
        return (f"P5 VERDICT: DEEP-REFIT-ONLY CANDIDATE ({backend}; wins RPS "
                f"{rps_note} but blows the runtime budget — {rt_note})")
    return f"P5 VERDICT: NO-ADOPT {backend} (no RPS lift beyond the CI — {rps_note}; {rt_note})"


def _fmt_reliability(title: str, table: list[dict]) -> list[str]:
    """Render a binned reliability table to printable lines (bin | n | p_mean | freq)."""
    out = [f"  {title}", f"  {'bin':>9} | {'n':>5} | {'p_mean':>7} | {'obs_freq':>8}",
           f"  {'-'*9}-+-{'-'*5}-+-{'-'*7}-+-{'-'*8}"]
    for r in table:
        pm = "  nan  " if r["p_mean"] != r["p_mean"] else f"{r['p_mean']:.4f}"
        fr = "  nan   " if r["freq"] != r["freq"] else f"{r['freq']:.4f}"
        out.append(f"  {r['bin']:>9} | {r['n']:>5} | {pm:>7} | {fr:>8}")
    return out


def assemble_report(part: dict) -> str:
    """Pure report assembler — frame-in / markdown-out (NO fit, NO I/O).

    ``part`` keys: ``backend``, ``cutoff``, ``is_baseline``, ``model_rps``,
    ``elo_rps``, ``n``, ``fit_seconds``, ``projected_min``, ``delta_ci`` (or None),
    ``nuts_diag`` (or None), ``fav_table``, ``draw_table``, ``verdict``,
    ``reablation`` (or None). The verdict line is included VERBATIM so the report is
    the single machine-readable artifact the controller reads."""
    L: list[str] = []
    L.append("=" * 78)
    L.append(f"P5 INFERENCE COMPARISON — backend={part['backend']}  cutoff={part['cutoff']}")
    L.append("=" * 78)
    L.append(f"[heldout] n={part['n']} matches (date > {part['cutoff'][:10]}, "
             "leakage-guarded; both teams priceable by model AND Elo).")
    L.append(f"[rps] model_RPS={part['model_rps']:.5f}   elo_baseline_RPS={part['elo_rps']:.5f}")
    L.append(f"[wall-clock] fit took {part['fit_seconds']:.1f} s "
             f"({part['fit_seconds']/60.0:.2f} min).")
    if part.get("projected_min") is not None:
        L.append(f"[runtime] projected full daily_update ≈ {part['projected_min']:.1f} min "
                 f"(= {part['fit_seconds']/60.0:.2f} fit + {SIM_STAGE_REMAINDER_MIN:.0f} "
                 f"sim/stage) vs nightly budget {NIGHTLY_BUDGET_MIN:.0f} min.")
    # NUTS diagnostics (only for nuts; None otherwise).
    diag = part.get("nuts_diag")
    if diag is not None:
        L.append("[nuts] diagnostics (FRESH fit; sample_stats are NOT cached):")
        L.append(f"        divergences={diag.get('divergences')}  "
                 f"min_ess_bulk={diag.get('min_ess_bulk')}  "
                 f"max_rhat={diag.get('max_rhat')}  "
                 f"chains={diag.get('n_chains')} draws={diag.get('n_draws')}")
    # Paired bootstrap ΔRPS vs advi baseline.
    dci = part.get("delta_ci")
    if part.get("is_baseline"):
        L.append("[paired-bootstrap] this IS the advi baseline (ΔRPS reference).")
    elif dci is not None:
        L.append(f"[paired-bootstrap] ΔRPS (backend − advi) = {dci['delta']:+.5f}  "
                 f"95% CI [{dci['lo95']:+.5f}, {dci['hi95']:+.5f}]  n={dci.get('n')}")
        L.append(f"        RPS-lift gate (delta<0 AND hi95<0): "
                 f"{'PASS' if rps_lift_passes(dci) else 'FAIL'}")
    else:
        L.append("[paired-bootstrap] advi baseline artifact NOT found — run the advi "
                 "backend FIRST so later backends can score ΔRPS against it.")
    # Reliability tables.
    L.append("")
    L.append("[reliability] FAVORITE + DRAW (binned; via backtest.headroom.reliability_table)")
    L.extend(_fmt_reliability("FAVORITE (model argmax prob vs realised):", part["fav_table"]))
    L.append("")
    L.extend(_fmt_reliability("DRAW (model draw prob vs realised draw):", part["draw_table"]))
    # Optional widening re-ablation phase.
    re = part.get("reablation")
    if re is not None:
        L.append("")
        L.append("-" * 78)
        L.append(f"WIDENING RE-ABLATION (under backend={part['backend']}) — on vs off")
        L.append("-" * 78)
        L.append(f"  widening ON : model_RPS={re['on_rps']:.5f}  (mechanism="
                 f"{re['mechanism']}, strength={re['strength']})")
        L.append(f"  widening OFF: model_RPS={re['off_rps']:.5f}  (strength=0.0, in-range no-op)")
        L.append(f"  ΔRPS (on − off) = {re['delta_ci']['delta']:+.5f}  "
                 f"95% CI [{re['delta_ci']['lo95']:+.5f}, {re['delta_ci']['hi95']:+.5f}]  "
                 f"n={re['delta_ci'].get('n')}")
        L.append(f"  => widening {'HELPS' if rps_lift_passes(re['delta_ci']) else 'does NOT help'} "
                 f"under {part['backend']} on this held-out set.")
    # The single machine-readable verdict line (verbatim).
    L.append("")
    L.append(part["verdict"])
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Config arms.                                                                  #
# --------------------------------------------------------------------------- #
def _config_for_backend(base_cfg: dict, backend: str) -> dict:
    """Deep copy of the config with ``model.inference.backend`` set. Each backend is
    a DISTINCT ``cfg["model"]`` -> a distinct posterior cache key, so reruns are free
    and the backends never collide on disk."""
    cfg = copy.deepcopy(base_cfg)
    cfg["model"]["inference"]["backend"] = backend
    return cfg


def _config_widening_off(base_cfg: dict) -> dict:
    """Deep copy with widening turned OFF (strength 0.0 — the in-range no-op the
    widening module documents for both mechanism 'a' and 'c'). The widening-ON arm
    is the base config as-is."""
    cfg = copy.deepcopy(base_cfg)
    cfg["model"]["widening"]["strength"] = 0.0
    return cfg


def _fit(store, cutoff: str, cfg: dict):
    """ONE production-fidelity fit at ``cutoff`` under ``cfg`` via cached_fit.

    Threads the FULL inference block (backend + NUTS knobs) so the production
    fidelity (advi_iters / draws / chains / target_accept) is never coarsened.
    Returns ``(posterior, cache_hit, fit_seconds)``."""
    inf = cfg["model"]["inference"]
    t0 = time.monotonic()
    post, meta = _model_cache.cached_fit(
        cutoff=pd.Timestamp(cutoff), store=store,
        backend=str(inf["backend"]), draws=int(inf["draws"]),
        seed=int(cfg["seed"]), advi_iters=int(inf["advi_iters"]),
        tune=int(inf.get("tune", 1000)),
        chains=int(inf.get("chains", 2)),
        target_accept=float(inf.get("target_accept", 0.9)),
        nuts_sampler=inf.get("nuts_sampler"),
        cache_dir=CACHE_DIR, config=cfg,
    )
    return post, bool(meta["cache_hit"]), time.monotonic() - t0


def _run_reablation(store, cutoff, heldout, elo_ratings, base_cfg, backend, seed):
    """The conditional widening on/off re-ablation under ``backend`` (P2-T6/M-T7).

    Two arms differing ONLY in ``model.widening`` (ON=config, OFF=strength 0.0)
    scored with the SAME paired held-out RPS + paired bootstrap. Returns the
    re-ablation dict the report renders."""
    cfg_backend = _config_for_backend(base_cfg, backend)
    cfg_on = cfg_backend
    cfg_off = _config_widening_off(cfg_backend)
    post_on, _, _ = _fit(store, cutoff, cfg_on)
    post_off, _, _ = _fit(store, cutoff, cfg_off)
    sc_on = score_backend(post_on, heldout, elo_ratings, base_cfg)
    sc_off = score_backend(post_off, heldout, elo_ratings, base_cfg)
    # Paired (on − off) over the common fixtures.
    n = min(len(sc_on["rows"]), len(sc_off["rows"]))
    paired = [{"p_model": sc_on["rows"][i]["p_model"],
               "p_ref": sc_off["rows"][i]["p_model"],
               "outcome": sc_on["rows"][i]["outcome"]} for i in range(n)]
    ci = bootstrap_delta_ci(paired, seed=seed); ci["n"] = n
    return {
        "on_rps": sc_on["model_rps"], "off_rps": sc_off["model_rps"],
        "mechanism": base_cfg["model"]["widening"]["mechanism"],
        "strength": base_cfg["model"]["widening"]["strength"],
        "delta_ci": ci,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=BACKENDS, required=True,
                    help="the single backend to fit + score this invocation")
    ap.add_argument("--cutoff", default=DEFAULT_CUTOFF,
                    help=f"held-out calibration cutoff (default {DEFAULT_CUTOFF})")
    ap.add_argument("--reablate-widening", metavar="BACKEND", default=None,
                    help="ALSO run the widening on/off re-ablation under this backend "
                         "(controller triggers this only for the RPS-winning backend)")
    ap.add_argument("--out", default=None,
                    help="optional path to also write the text report to")
    args = ap.parse_args(argv)

    backend = args.backend
    cutoff = args.cutoff
    is_baseline = backend == "advi"

    print("=" * 78)
    print(f"P5 INFERENCE COMPARISON — backend={backend} (OFFLINE; no odds, no credits)")
    print("=" * 78)
    base_cfg = load_config()
    inf = base_cfg["model"]["inference"]
    print(f"[fit] PRODUCTION fidelity: advi_iters={inf['advi_iters']} draws={inf['draws']} "
          f"tune={inf.get('tune')} chains={inf.get('chains')} "
          f"target_accept={inf.get('target_accept')} (NOT coarsened).")

    store = get_persistent_store()
    max_train = _assert_no_leak(store, cutoff)
    print(f"[leakage] max training date < cutoff = {max_train.date()} (strictly < "
          f"{cutoff[:10]}). Held-out (date > cutoff) disjoint from train. OK")

    heldout = _heldout_frame(store, cutoff)
    print(f"[heldout] {len(heldout)} valid-played internationals after {cutoff[:10]}.")
    elo_ratings = _elo_as_of_cutoff(store, cutoff, base_cfg)

    # The fit + score for THIS backend.
    cfg_b = _config_for_backend(base_cfg, backend)
    print(f"[fit] cached_fit backend={backend} at {cutoff} ...", flush=True)
    post, cache_hit, fit_seconds = _fit(store, cutoff, cfg_b)
    print(f"[fit] {'CACHE HIT' if cache_hit else 'fresh fit'} in {fit_seconds:.1f}s; "
          f"{len(post.teams)} teams.", flush=True)
    sc = score_backend(post, heldout, elo_ratings, base_cfg)
    print(f"[score] model_RPS={sc['model_rps']:.5f}  elo_RPS={sc['elo_rps']:.5f}  n={sc['n']}")

    # NUTS diagnostics — only meaningful on a FRESH nuts fit (sample_stats absent
    # on a cache hit). On a hit we record that they are unavailable.
    nuts_diag = None
    if backend == "nuts":
        nuts_diag = nuts_diagnostics(post.idata) if not cache_hit else {
            "divergences": None, "min_ess_bulk": None, "max_rhat": None,
            "n_chains": None, "n_draws": None, "note": "cache hit — sample_stats not cached",
        }

    # Paired bootstrap ΔRPS vs the advi baseline (read from disk; the advi run wrote it).
    bpath = _baseline_path(CACHE_DIR, cutoff)
    delta_ci = None
    if is_baseline:
        # Persist this run's per-fixture rows AS the baseline for later backends.
        bpath.parent.mkdir(parents=True, exist_ok=True)
        bpath.write_text(json.dumps({"cutoff": cutoff, "rows": sc["rows"]}))
        print(f"[baseline] wrote advi baseline rows -> {bpath}")
    elif bpath.exists():
        baseline_rows = json.loads(bpath.read_text())["rows"]
        # p_model in the stored advi rows is the advi model prob; re-key to p_ref.
        baseline_rows = [{"p_ref": r["p_model"], "outcome": r["outcome"]}
                         for r in baseline_rows]
        delta_ci = paired_delta_vs_baseline(
            sc["rows"], baseline_rows, seed=int(base_cfg["seed"]))
        print(f"[paired] ΔRPS (backend−advi)={delta_ci['delta']:+.5f} "
              f"CI[{delta_ci['lo95']:+.5f},{delta_ci['hi95']:+.5f}]")
    else:
        print("[paired] no advi baseline on disk — run --backend advi FIRST.")

    projected_min = project_runtime_min(fit_seconds / 60.0)

    # Optional widening re-ablation (controller-triggered second phase).
    reablation = None
    if args.reablate_widening:
        rb = args.reablate_widening
        print(f"[reablate] widening on/off under backend={rb} ...", flush=True)
        reablation = _run_reablation(store, cutoff, heldout, elo_ratings,
                                     base_cfg, rb, int(base_cfg["seed"]))

    verdict = verdict_line(backend=backend, is_baseline=is_baseline,
                           delta_ci=delta_ci, projected_min=projected_min)

    report = assemble_report({
        "backend": backend, "cutoff": cutoff, "is_baseline": is_baseline,
        "model_rps": sc["model_rps"], "elo_rps": sc["elo_rps"], "n": sc["n"],
        "fit_seconds": fit_seconds, "projected_min": projected_min,
        "delta_ci": delta_ci, "nuts_diag": nuts_diag,
        "fav_table": reliability_table(sc["fav_probs"], sc["fav_hits"]),
        "draw_table": reliability_table(sc["draw_probs"], sc["draw_hits"]),
        "verdict": verdict, "reablation": reablation,
    })
    print("\n" + report)
    if args.out:
        Path(args.out).write_text(report)
        print(f"\n[out] report written -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
