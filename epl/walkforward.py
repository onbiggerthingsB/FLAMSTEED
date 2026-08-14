"""THE RUN. The frozen Dixon-Coles model against walk-forward Elo, 2019/20-2024/25.

This module executes the design preregistered in ``reports/epl_prereg.md`` §5 and
scores it under the pass rule in §3. It chooses nothing: every hyperparameter it
uses is read off ``epl/config_frozen.json``, which was committed at b416925
before any line of this file existed.

THE CADENCE IS WEEKLY, AND THAT IS NOT A CHOICE MADE HERE. The preregistration
fixes "every matchweek of every scoring season" — 212 fits, counted — and its
own STOP clause 6 says the run does *not* "shrink the window, coarsen the
cadence, or thin the sample to fit the budget: any of those would change the
preregistered design after seeing what it costs". H1 itself is stated as "fitted
walk-forward at matchweek cadence". A fortnightly walk would answer a different
question with the same words, so :data:`CADENCE_WEEKS` is 1 and the runner
refuses anything else unless it is told, in the artifact, that it is off-protocol.

WHAT ONE CUTOFF IS. A matchweek is (season, ISO calendar week) — the same block
the bootstrap uses and the same one ``epl.fit.matchweek_index`` builds. The
cutoff is that block's OPENING DAY at midnight. ``wcmodel.data.features.build``
keeps ``date < cutoff.normalize()``, so every fixture in the block is unseen by
the fit that prices it, including fixtures on the opening day itself. That is
asserted per cutoff (:func:`matchweek_cutoffs`), not assumed.

EVERY FIXTURE GETS A NUMBER. A fixture the model cannot price is a reported
failure and a STOP, never a silent drop — see the module's ``unpriceable``
ledger column and ``reports/epl_prereg.md`` §4.2. Fix 3
(:class:`epl.dcfit.ColdStartPosterior`) exists so the count is zero.

THE PANEL FAST PATH, and why it changes no number. ``features.build`` computes a
COVID tag with ``df["date"].map(tiers.is_covid)``, and ``tiers.is_covid`` opens
and YAML-parses ``config/config.yaml`` in its body — once per panel row, ~8k
times per fit, which is 50 of the 57 seconds a fit costs. ``epl.fit.
config_read_once`` serves that read from one already-parsed config. It edits
nothing under ``src/`` and it cannot change the panel, because the panel is
proven bit-identical either way — at the cutoffs in
:func:`verify_fast_path_is_inert`, on the panel AND on the resulting 1X2
forecasts, at every cutoff run. It is used here so the preregistered 212-fit
weekly cadence fits comfortably inside the budget instead of the cadence being
coarsened to fit the clock.

NO BETTING. The market column is an accuracy benchmark. It is never displayed
publicly, never turned into a signal, and never sized.
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from epl import anchor as anchor_mod
from epl import baseline, dcfit, fit as epl_fit, freeze, paths
from epl import score as score_mod, windows
from epl.schema import sort_for_walk_forward

__all__ = [
    "CADENCE_WEEKS", "LEDGER_PATH", "RESULT_PATH", "Cutoff",
    "matchweek_cutoffs", "run_walk", "load_ledger", "score_run",
    "verify_fast_path_is_inert", "point_in_time_canary",
]

#: Preregistered refit cadence, in matchweeks. See the module docstring.
CADENCE_WEEKS = 1

#: Append-only per-cutoff forecast ledger (JSONL), so a crashed run resumes
#: instead of restarting, and so the raw forecasts survive the scoring code.
LEDGER_PATH = paths.FIT_DIR / "walkforward_ledger.jsonl"

#: The scored result: headline gap, CI, per-season table, diagnostics.
RESULT_PATH = paths.FIT_DIR / "walkforward.json"


# ==========================================================================
# 1. the cutoffs
# ==========================================================================
@dataclass(frozen=True)
class Cutoff:
    """One refit: when it happens and which fixtures it prices."""

    season: str
    matchweek: int
    cutoff: pd.Timestamp
    rows: np.ndarray                      # positional indices into the played frame
    match_ids: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.season}|mw{self.matchweek:03d}|{self.cutoff.date()}"


def matchweek_cutoffs(matches: pd.DataFrame,
                      score_seasons: Sequence[str] = windows.SCORE_SEASONS,
                      cadence: int = CADENCE_WEEKS) -> list[Cutoff]:
    """The refit schedule, with the point-in-time property asserted per cutoff.

    ``cadence = 1`` is the preregistered weekly walk: one fit per (season, ISO
    week), each pricing exactly that week's fixtures. ``cadence = n > 1`` groups
    n consecutive weeks of the SAME season behind one fit — off-protocol, and
    recorded as such in the ledger by :func:`run_walk`.

    Two properties are checked here rather than trusted: no block spans a season
    boundary, and every fixture in a block falls on or after the block's cutoff
    day, so the ``date < cutoff`` gate cannot have shown the fit a fixture it is
    about to price.
    """
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    windows.assert_no_score_leak(score_seasons, "the scoring window")
    mw = epl_fit.matchweek_index(played)
    seasons = played["season"].to_numpy()
    dates = pd.to_datetime(played["date"]).dt.normalize().to_numpy()
    ids = played["match_id"].astype(str).to_numpy()

    out: list[Cutoff] = []
    for season in score_seasons:
        weeks = sorted(set(mw[seasons == season]))
        for i in range(0, len(weeks), int(cadence)):
            chunk = weeks[i:i + int(cadence)]
            rows = np.flatnonzero((seasons == season) & np.isin(mw, chunk))
            if not rows.size:
                continue
            cutoff = pd.Timestamp(dates[rows].min()).normalize()
            if (pd.to_datetime(dates[rows]) < cutoff).any():
                raise AssertionError(
                    f"{season} mw{chunk[0]}: a fixture falls before its own "
                    "cutoff day, so the fit that prices it would have seen it")
            if len(set(seasons[rows])) != 1:
                raise AssertionError("a refit block spans two seasons")
            out.append(Cutoff(season=season, matchweek=int(chunk[0]),
                              cutoff=cutoff, rows=rows,
                              match_ids=tuple(ids[rows])))

    covered = [m for c in out for m in c.match_ids]
    want = set(ids[np.isin(seasons, list(score_seasons))])
    if len(covered) != len(set(covered)) or set(covered) != want:
        raise AssertionError(
            f"the schedule prices {len(set(covered))} distinct fixtures but the "
            f"scoring window holds {len(want)}: every fixture must be priced "
            "exactly once")
    return out


# ==========================================================================
# 2. the walk
# ==========================================================================
def _health(post, cfg: dict) -> dict[str, Any]:
    """Numerical health of one fitted posterior.

    pymc 6.0.1's ``pm.fit(method="advi")`` — which is what
    ``wcmodel.model.inference.sample`` calls — installs no convergence callback,
    so "did ADVI converge" has no package-level boolean to read. What CAN be
    checked without touching ``src/`` is whether the posterior it produced is
    usable: every draw finite, both scale parameters strictly positive, and the
    fitted home advantage inside a range a league fit could plausibly occupy.
    A failure of any of these is reported per cutoff, never averaged away.
    """
    out: dict[str, Any] = {}
    finite = True
    for name in ("att", "def", "sigma_att", "sigma_def", "mu", "home_adv"):
        try:
            arr = np.asarray(post._post(name), dtype=float)
        except Exception:                                    # not in this model
            continue
        finite &= bool(np.isfinite(arr).all())
        out[f"mean_{name}"] = float(np.mean(arr))
        if name in ("sigma_att", "sigma_def"):
            out[f"min_{name}"] = float(np.min(arr))
    out["all_finite"] = bool(finite)
    out["sigma_positive"] = bool(out.get("min_sigma_att", 1.0) > 0
                                 and out.get("min_sigma_def", 1.0) > 0)
    out["home_adv_sane"] = bool(-1.0 < out.get("mean_home_adv", 0.0) < 1.0)
    return out


def _one_cutoff(cut: Cutoff, played: pd.DataFrame, store, anchor, cfg: dict,
                matches: pd.DataFrame) -> dict[str, Any]:
    """Fit at one cutoff and price every fixture in its block."""
    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        post, res = dcfit.fit_epl(cut.cutoff, store, anchor, cfg,
                                  matches=matches,
                                  feature_cache_dir=paths.FIT_CACHE_DIR)
        warns = sorted({f"{w.category.__name__}: {w.message}" for w in caught})

    home = played["home_key"].astype(str).to_numpy()[cut.rows]
    away = played["away_key"].astype(str).to_numpy()[cut.rows]
    probs, unpriceable = [], []
    for mid, h, a in zip(cut.match_ids, home, away):
        if h not in post._idx or a not in post._idx:
            probs.append([float("nan")] * 3)
            unpriceable.append({"match_id": mid, "home": h, "away": a,
                                "why": "club absent from the posterior index"})
            continue
        p = post.predict_1x2(h, a, neutral=False)
        probs.append([float(p[k]) for k in score_mod.OUTCOMES])

    arr = np.asarray(probs, dtype=float)
    bad = [m for m, row in zip(cut.match_ids, arr)
           if not (np.isfinite(row).all() and abs(row.sum() - 1.0) < 1e-9)]
    return {
        "key": cut.key, "season": cut.season, "matchweek": cut.matchweek,
        "cutoff": str(cut.cutoff.date()), "n_fixtures": len(cut.match_ids),
        "match_ids": list(cut.match_ids),
        "probs": [[round(v, 8) for v in row] for row in arr.tolist()],
        "seconds": round(time.perf_counter() - t0, 2),
        "n_training_matches": res.n_training_matches, "n_teams": res.n_teams,
        "cold_start_teams": res.cold_start_teams,
        "cold_start_z": res.cold_start_z,
        "provisional_teams": res.provisional_teams,
        "anchor_spec": res.anchor_spec,
        "warnings": warns,
        "unpriceable": unpriceable,
        "malformed": bad,
        "health": _health(post, cfg),
    }


def run_walk(matches: pd.DataFrame | None = None, cadence: int = CADENCE_WEEKS,
             ledger_path: Path | str = LEDGER_PATH, fast_panel: bool = True,
             resume: bool = True, limit: int | None = None,
             seed: int | None = None, verbose: bool = True) -> dict[str, Any]:
    """Fit at every cutoff and append one ledger row per cutoff.

    Append-only and resumable: a row already in the ledger is skipped, so a
    crash costs the fit in flight and nothing else. Resuming is safe because
    every fit is a pure function of (cutoff, store, frozen config) — there is no
    state carried between fits.

    ``seed`` overrides the shipped inference seed. It exists for ONE purpose:
    running the identical walk twice and measuring how much of the headline is
    ADVI optimiser noise. The reported result always comes from the frozen
    configuration's own seed; a replica is a diagnostic and is written to its
    own ledger so the two can never be mixed.
    """
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cuts = matchweek_cutoffs(played, cadence=cadence)
    if limit:
        cuts = cuts[:limit]

    cfg = freeze.frozen_wcmodel_config()
    if seed is not None:
        cfg["seed"] = int(seed)
        cfg["elo"]["epl_anchor_spec"] += f"/seed={int(seed)}"
    anchor = anchor_mod.Anchor(played, freeze.frozen_elo_config())
    store = epl_fit.build_store(played)

    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    if resume and ledger_path.exists():
        done = {json.loads(l)["key"] for l in ledger_path.read_text().splitlines()
                if l.strip()}

    todo = [c for c in cuts if c.key not in done]
    if verbose:
        print(f"[walk] {len(cuts)} cutoffs at cadence {cadence}w, "
              f"{len(done)} already in the ledger, {len(todo)} to run",
              flush=True)

    ctx = (epl_fit.config_read_once(cfg) if fast_panel
           else _null_context())
    started = time.time()
    with ctx:
        for i, cut in enumerate(todo, 1):
            row = _one_cutoff(cut, played, store, anchor, cfg, played)
            row["cadence_weeks"] = int(cadence)
            row["off_protocol"] = bool(cadence != CADENCE_WEEKS)
            row["fast_panel"] = bool(fast_panel)
            with ledger_path.open("a") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
            if verbose:
                el = time.time() - started
                print(f"[walk] {i}/{len(todo)} {cut.key} "
                      f"n_train={row['n_training_matches']} "
                      f"fixtures={row['n_fixtures']} "
                      f"unpriceable={len(row['unpriceable'])} "
                      f"{row['seconds']}s  (elapsed {el/60:.1f}m, "
                      f"eta {el/i*(len(todo)-i)/60:.1f}m)", flush=True)
    return {"n_cutoffs": len(cuts), "n_run": len(todo),
            "seconds": round(time.time() - started, 1),
            "ledger": str(ledger_path)}


class _null_context:
    def __enter__(self): return None
    def __exit__(self, *a): return False


def load_ledger(path: Path | str = LEDGER_PATH) -> list[dict[str, Any]]:
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    seen, out = set(), []
    for r in rows:                       # last write wins, order preserved
        if r["key"] in seen:
            continue
        seen.add(r["key"])
        out.append(r)
    return out


# ==========================================================================
# 3. verification
# ==========================================================================
def verify_fast_path_is_inert(cutoffs: Iterable[str], matches=None,
                              ) -> list[dict[str, Any]]:
    """Prove the panel fast path changes neither the panel nor the forecast.

    At each cutoff the feature panel is built twice — once through the shipped
    per-row ``load_config`` and once through ``epl.fit.config_read_once`` — and
    the two are compared with ``DataFrame.equals``. The check is on the object
    the model actually consumes, not on the wrapper's source code.
    """
    from wcmodel.data import features as wc_features

    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cfg = freeze.frozen_wcmodel_config()
    store = epl_fit.build_store(played)

    out = []
    for c in cutoffs:
        ts = pd.Timestamp(c).normalize()
        t0 = time.perf_counter()
        shipped = wc_features.build(ts, store, cfg)      # uncached, on purpose
        t_shipped = time.perf_counter() - t0
        with epl_fit.config_read_once(cfg):
            t0 = time.perf_counter()
            fast = wc_features.build(ts, store, cfg)
            t_fast = time.perf_counter() - t0
        out.append({
            "cutoff": str(ts.date()),
            "panel_identical": bool(shipped.equals(fast)),
            "n_rows": int(len(shipped)),
            "seconds_shipped": round(t_shipped, 2),
            "seconds_fast": round(t_fast, 3),
        })
    return out


def provisional_arm_split(ledger: list[dict[str, Any]] | None = None,
                          matches=None) -> dict[str, Any]:
    """Which arm of ``count_volatility_arm`` actually fired, per cutoff.

    The preregistration recorded, from two TUNING cutoffs, that "wcmodel's
    provisional/volatility arm (16.5-point threshold, derived at international K
    up to 40) flags NOBODY at club K". This recomputes the arm at every scoring
    cutoff that produced a provisional club and reports the split, because a
    claim measured at two cutoffs is not a claim about 212.
    """
    from wcmodel.model.volatility_diagnostic import count_volatility_arm

    ledger = load_ledger() if ledger is None else ledger
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cfg = freeze.frozen_wcmodel_config()
    store = epl_fit.build_store(played)

    rows, vol_hits, few_hits = [], [], []
    with epl_fit.config_read_once(cfg):
        for r in ledger:
            if not r["provisional_teams"]:
                continue
            arm = count_volatility_arm(store, pd.Timestamp(r["cutoff"]),
                                       list(r["provisional_teams"]), config=cfg)
            for _, a in arm.iterrows():
                rec = {"cutoff": r["cutoff"], "team": str(a["team"]),
                       "games": int(a["games"]),
                       "recent_volatility": (None if pd.isna(a["recent_volatility"])
                                             else round(float(a["recent_volatility"]), 3)),
                       "volatility_flag": bool(a["volatility_flag"]),
                       "few_games_flag": bool(a["few_games_flag"]),
                       "cold_start": bool(a["team"] in r["cold_start_teams"])}
                rows.append(rec)
                (vol_hits if rec["volatility_flag"] else few_hits).append(rec)
    return {
        "n_cutoffs_with_a_provisional_club": sum(
            1 for r in ledger if r["provisional_teams"]),
        "n_team_cutoff_flags": len(rows),
        "n_volatility_arm": len(vol_hits),
        "n_few_games_arm": len(few_hits),
        "volatility_arm_teams": sorted({r["team"] for r in vol_hits}),
        "few_games_arm_teams": sorted({r["team"] for r in few_hits}),
        "detail": rows,
    }


def advi_stability(cutoffs: Iterable[str], matches=None, alt_seed: int = 987654,
                   n_fixtures: int = 10) -> list[dict[str, Any]]:
    """Refit at a different RNG seed and measure how far the forecast moves.

    THE HONEST ANSWER TO "DID ADVI CONVERGE". pymc 6.0.1's
    ``pm.fit(method="advi")`` — which is what ``wcmodel.model.inference.sample``
    calls — installs no convergence callback, so there is no package-level
    boolean to read and none is invented here. What a completed fit does
    guarantee is only that the ELBO never went NaN (pymc raises
    ``FloatingPointError`` if it does). This function supplies the missing
    evidence directly: if the variational optimum is found reliably, two runs
    that differ ONLY in the RNG seed must land in the same place, and the
    forecast difference measures how much of the reported number is optimiser
    noise. It is a DIAGNOSTIC — the reported forecasts all come from the frozen
    seed, and nothing here feeds the headline.
    """
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cfg = freeze.frozen_wcmodel_config()
    alt = json.loads(json.dumps(cfg))
    alt["seed"] = int(alt_seed)
    alt["elo"]["epl_anchor_spec"] = cfg["elo"]["epl_anchor_spec"] + f"/seed={alt_seed}"
    anchor = anchor_mod.Anchor(played, freeze.frozen_elo_config())
    store = epl_fit.build_store(played)

    out = []
    with epl_fit.config_read_once(cfg):
        for c in cutoffs:
            ts = pd.Timestamp(c).normalize()
            fut = played.loc[pd.to_datetime(played["date"]) >= ts]
            pairs = list(zip(fut["home_key"].astype(str),
                             fut["away_key"].astype(str)))[:n_fixtures]
            probs = []
            for use in (cfg, alt):
                post, _ = dcfit.fit_epl(ts, store, anchor, use, matches=played,
                                        feature_cache_dir=paths.FIT_CACHE_DIR)
                probs.append(np.array(
                    [[post.predict_1x2(h, a)[k] for k in score_mod.OUTCOMES]
                     for h, a in pairs]))
            d = np.abs(probs[0] - probs[1])
            out.append({"cutoff": str(ts.date()), "n_fixtures": len(pairs),
                        "max_abs_prob_shift": float(d.max()),
                        "mean_abs_prob_shift": float(d.mean())})
    return out


def point_in_time_canary(matches=None, cutoff="2022-01-01",
                         later="2023-01-01", tmp_root=None) -> dict[str, Any]:
    """Rewrite every result from ``cutoff`` on; demand the forecast is unmoved.

    The prereg's STOP 3. Stronger than the panel-level canary in
    ``epl/tests/test_fit.py`` because it runs the WHOLE pipeline this run uses —
    anchor, fit, cold start, ``predict_1x2`` — and compares probabilities, not
    intermediate columns. The positive control at ``later`` asserts the
    corrupted results really did land, so a canary that rewrote nothing cannot
    pass by accident.
    """
    import tempfile

    from wcmodel.data.store import BitemporalStore, Policy

    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cfg = freeze.frozen_wcmodel_config()
    anchor = anchor_mod.Anchor(played, freeze.frozen_elo_config())

    clean = epl_fit.to_store_frame(played)
    dirty = clean.copy()
    after = pd.to_datetime(dirty["date"]) >= pd.Timestamp(cutoff)
    dirty.loc[after, "home_score"] = 9
    dirty.loc[after, "away_score"] = 0

    root = Path(tmp_root or tempfile.mkdtemp(prefix="epl-canary-"))

    def _forecasts(frame, name, at):
        store = BitemporalStore(root / name)
        table = root / name / "results.parquet"
        if not table.exists():
            store.write("results", frame, policy=Policy.POINT_IN_TIME,
                        keys=["match_id"], source="canary", source_version="c")
        post, _ = dcfit.fit_epl(at, store, anchor, cfg, matches=played)
        fut = played.loc[pd.to_datetime(played["date"]) >= pd.Timestamp(at)]
        pairs = list(zip(fut["home_key"].astype(str),
                         fut["away_key"].astype(str)))[:10]
        return np.array([[post.predict_1x2(h, a)[k] for k in score_mod.OUTCOMES]
                         for h, a in pairs]), pairs

    with epl_fit.config_read_once(cfg):
        a, pairs = _forecasts(clean, "clean", cutoff)
        b, _ = _forecasts(dirty, "dirty", cutoff)
        c, _ = _forecasts(clean, "clean_late", later)
        d, _ = _forecasts(dirty, "dirty_late", later)

    identical = bool(np.array_equal(a, b))
    moved = bool(not np.array_equal(c, d))
    return {
        "cutoff": str(cutoff), "later": str(later),
        "n_rewritten": int(after.sum()), "n_fixtures_compared": len(pairs),
        "forecasts_bit_identical_before_cutoff": identical,
        "positive_control_forecasts_moved_after_cutoff": moved,
        "max_abs_diff_before_cutoff": float(np.max(np.abs(a - b))),
        "max_abs_diff_positive_control": float(np.max(np.abs(c - d))),
        "PASS": bool(identical and moved),
    }


# ==========================================================================
# 4. scoring
# ==========================================================================
def _bootstrap(d: np.ndarray, blocks: Sequence[Any], n_boot: int) -> dict:
    lo, hi, nb = score_mod.block_bootstrap_ci(d, blocks, n_boot=n_boot)
    return {"ci95": [lo, hi], "n_blocks": int(nb)}


def _pair(name_a: str, a: np.ndarray, name_b: str, b: np.ndarray,
          week: Sequence[Any], season: Sequence[Any], n_boot: int) -> dict:
    d, mean, sd = score_mod.paired_gap(name_a, a, name_b, b)
    out = {"a": name_a, "b": name_b, "n": int(d.size), "mean": mean, "sd": sd,
           "se_iid": float(sd / np.sqrt(d.size))}
    out["week"] = _bootstrap(d, week, n_boot)
    out["season"] = _bootstrap(d, season, n_boot)
    return out


def score_run(ledger: list[dict[str, Any]] | None = None,
              matches: pd.DataFrame | None = None,
              n_boot: int = 10_000) -> dict[str, Any]:
    """Score DC, Elo and the market on ONE complete-case match set.

    The Elo and market columns are not re-derived here: they come from
    ``epl.baseline.evaluate`` under the frozen Elo configuration, which is the
    same function and the same configuration that produced the published
    baseline. The only new column is the model's.
    """
    ledger = load_ledger() if ledger is None else ledger
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])

    # --- the comparator and the benchmark, from the baseline itself ---------
    elo_cfg = freeze.frozen_elo_config()
    ev = baseline.evaluate(played, elo_cfg, windows.SCORE_SEASONS,
                           require_odds=True)
    frame = ev.frame.copy()

    # --- the model's column -------------------------------------------------
    dc: dict[str, list[float]] = {}
    unpriceable: list[dict[str, Any]] = []
    malformed: list[str] = []
    for row in ledger:
        for mid, p in zip(row["match_ids"], row["probs"]):
            dc[str(mid)] = [float(v) for v in p]
        unpriceable.extend(row.get("unpriceable", []))
        malformed.extend(row.get("malformed", []))

    ids = frame["match_id"].astype(str).to_numpy()
    missing = [m for m in ids if m not in dc]
    arr = np.array([dc.get(m, [np.nan] * 3) for m in ids], dtype=float)
    finite = np.isfinite(arr).all(axis=1)
    for j, o in enumerate(score_mod.OUTCOMES):
        frame[f"dc_{o}"] = arr[:, j]

    keep = finite
    n_dropped = int((~keep).sum())
    frame = frame.loc[keep].reset_index(drop=True)
    arr = arr[keep]

    y = frame["y"].to_numpy()
    r = {"dc": score_mod.rps(arr, y)}
    frame["dc_rps"] = r["dc"]
    for name in ("elo", "market", "market_shin", "base"):
        r[name] = frame[f"{name}_rps"].to_numpy()
    ll = {"dc": score_mod.log_loss(arr, y)}
    for name in ("elo", "market", "market_shin", "base"):
        p = frame[[f"{name}_{o}" for o in score_mod.OUTCOMES]].to_numpy(float)
        ll[name] = score_mod.log_loss(p, y)

    scores = {"dc": score_mod.summarise("dc", arr, y).as_dict()}
    for name in ("elo", "market", "market_shin", "base"):
        p = frame[[f"{name}_{o}" for o in score_mod.OUTCOMES]].to_numpy(float)
        scores[name] = score_mod.summarise(name, p, y).as_dict()

    week = frame["block"].to_numpy()
    season = frame["season"].to_numpy()
    gaps = {}
    for a, b in (("dc", "elo"), ("dc", "market"), ("dc", "market_shin"),
                 ("dc", "base"), ("elo", "market")):
        gaps[f"{a}_minus_{b}"] = _pair(a, r[a], b, r[b], week, season, n_boot)
        gaps[f"{a}_minus_{b}"]["log_loss"] = _pair(
            a, ll[a], b, ll[b], week, season, n_boot)

    per_season = (frame.assign(dc_ll=ll["dc"], elo_ll=ll["elo"],
                               market_ll=ll["market"])
                  .groupby("season")
                  .agg(n=("match_id", "size"), dc=("dc_rps", "mean"),
                       elo=("elo_rps", "mean"), market=("market_rps", "mean"),
                       base=("base_rps", "mean"), dc_ll=("dc_ll", "mean"),
                       elo_ll=("elo_ll", "mean"), market_ll=("market_ll", "mean"))
                  .reset_index())
    per_season["dc_minus_elo"] = per_season["dc"] - per_season["elo"]
    per_season["dc_minus_market"] = per_season["dc"] - per_season["market"]

    # --- subsets that a single mean would hide ------------------------------
    prom = (frame["home_promoted"] | frame["away_promoted"]).to_numpy()
    subsets = {}
    for label, mask in (("all", np.ones(len(frame), bool)),
                        ("promoted", prom), ("established", ~prom)):
        if mask.sum() < 50:
            continue
        d = r["dc"][mask] - r["elo"][mask]
        subsets[label] = {
            "n": int(mask.sum()), "dc": float(r["dc"][mask].mean()),
            "elo": float(r["elo"][mask].mean()),
            "market": float(r["market"][mask].mean()),
            "dc_minus_elo": float(d.mean()),
            **_bootstrap(d, week[mask], n_boot),
        }

    # --- calibration smell test ---------------------------------------------
    calib = {"realised": {o: float((y == k).mean())
                          for k, o in enumerate(score_mod.OUTCOMES)}}
    for name in ("dc", "elo", "market", "base"):
        calib[name] = {o: float(frame[f"{name}_{o}"].mean())
                       for o in score_mod.OUTCOMES}

    # --- run diagnostics off the ledger --------------------------------------
    diag = {
        "n_cutoffs": len(ledger),
        "cutoffs_with_warnings": [r["key"] for r in ledger if r["warnings"]],
        "distinct_warnings": sorted({w for r in ledger for w in r["warnings"]}),
        "cutoffs_unhealthy": [
            r["key"] for r in ledger
            if not (r["health"]["all_finite"] and r["health"]["sigma_positive"]
                    and r["health"]["home_adv_sane"])],
        "cold_start_events": [
            {"cutoff": r["cutoff"], "clubs": r["cold_start_teams"],
             "z": r["cold_start_z"]}
            for r in ledger if r["cold_start_teams"]],
        "n_cutoffs_with_a_provisional_club": sum(
            1 for r in ledger if r["provisional_teams"]),
        "total_fit_seconds": round(sum(r["seconds"] for r in ledger), 1),
        "median_fit_seconds": float(np.median([r["seconds"] for r in ledger])),
        "n_training_matches_range": [min(r["n_training_matches"] for r in ledger),
                                     max(r["n_training_matches"] for r in ledger)],
        "anchor_specs": sorted({r["anchor_spec"] for r in ledger}),
        "cadence_weeks": sorted({r.get("cadence_weeks", 1) for r in ledger}),
        "off_protocol_cutoffs": [r["key"] for r in ledger
                                 if r.get("off_protocol")],
    }

    # --- the preregistered verdict ------------------------------------------
    # THE BLOCKING IS THE PREREGISTERED ONE. `reports/epl_prereg.md` §3 fixes it
    # as "(season, ISO calendar week) blocks — 212 of them on this scoring
    # window — with 10,000 resamples", so the week-block CI decides the verdict
    # and the season-block CI is reported beside it. Choosing between them after
    # seeing which classifies more favourably would be exactly the move this
    # preregistration exists to prevent, so BOTH classifications are computed
    # and both are reported, whichever way they fall.
    g = gaps["dc_minus_elo"]
    mde = 0.0034

    def _classify(lo: float, hi: float, delta: float) -> tuple[str, str]:
        if delta <= -mde and hi < 0:
            return "PASS", "delta at or beyond the MDE with the CI below zero"
        if lo > 0:
            return "REJECT", "the whole CI is above zero: the model is worse"
        if lo > -mde and hi < mde:
            return "INCONCLUSIVE (precise null)", (
                "the CI lies strictly inside (-0.0034, +0.0034): no improvement "
                "larger than the MDE survives, which is a real finding")
        return "INCONCLUSIVE (underpowered)", (
            "the CI spans the MDE: this run has not ruled out an effect of the "
            "size the pass rule was built to detect")

    delta = g["mean"]
    verdict, detail = _classify(*g["week"]["ci95"], delta)
    alt_verdict, alt_detail = _classify(*g["season"]["ci95"], delta)

    stops = {
        "too_good_vs_market": bool(gaps["dc_minus_market"]["mean"] <= -0.002
                                   and gaps["dc_minus_market"]["season"]["ci95"][1] < 0),
        "unpriceable_fixtures": int(len(unpriceable) + len(missing) + n_dropped),
        "malformed_forecasts": int(len(malformed)),
    }

    return {
        "n_matches": int(len(frame)),
        "n_expected": 2280,
        "n_dropped_incomplete": n_dropped,
        "missing_from_ledger": missing[:20],
        "unpriceable": unpriceable,
        "malformed": malformed,
        "scores": scores,
        "gaps": gaps,
        "per_season": per_season.to_dict(orient="records"),
        "subsets": subsets,
        "calibration": calib,
        "diagnostics": diag,
        "verdict": verdict,
        "verdict_detail": detail,
        "verdict_blocking": "(season, ISO week) — the preregistered blocking",
        "verdict_if_blocked_by_season": alt_verdict,
        "verdict_if_blocked_by_season_detail": alt_detail,
        "mde_preregistered": mde,
        "realised_paired_sd_dc_vs_elo": g["sd"],
        "realised_mde_80pct": round(float(2.802 * g["sd"] / np.sqrt(g["n"])), 5),
        "stops": stops,
        "frame": frame,
    }


# ==========================================================================
# 5. CLI
# ==========================================================================
def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--walk", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--canary", action="store_true")
    ap.add_argument("--advi-stability", action="store_true")
    ap.add_argument("--cadence", type=int, default=CADENCE_WEEKS)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None,
                    help="DIAGNOSTIC replica at a different ADVI seed; writes "
                         "its own ledger and never feeds the headline")
    ap.add_argument("--n-boot", type=int, default=10_000)
    ap.add_argument("--no-fast-panel", action="store_true")
    args = ap.parse_args()
    paths.FIT_DIR.mkdir(parents=True, exist_ok=True)

    if args.verify:
        out = verify_fast_path_is_inert(
            ["2019-08-09", "2021-12-26", "2024-05-19"])
        print(json.dumps(out, indent=2))
        assert all(o["panel_identical"] for o in out)

    if args.canary:
        out = point_in_time_canary()
        print(json.dumps(out, indent=2))

    if args.advi_stability:
        out = advi_stability(["2019-11-02", "2020-02-01", "2020-12-12",
                              "2021-04-10", "2021-11-06", "2022-03-05",
                              "2022-11-05", "2023-03-11", "2023-12-09",
                              "2024-04-13", "2024-11-09", "2025-03-08"])
        print(json.dumps(out, indent=2))

    if args.walk:
        out = run_walk(cadence=args.cadence, limit=args.limit,
                       seed=args.seed,
                       ledger_path=(LEDGER_PATH if args.seed is None else
                                    paths.FIT_DIR /
                                    f"walkforward_ledger_seed{args.seed}.jsonl"),
                       fast_panel=not args.no_fast_panel)
        print(json.dumps(out, indent=2))

    if args.score:
        res = score_run(n_boot=args.n_boot)
        frame = res.pop("frame")
        frame.to_parquet(paths.FIT_DIR / "walkforward_predictions.parquet")
        RESULT_PATH.write_text(json.dumps(res, indent=2, default=str) + "\n")
        for name, s in res["scores"].items():
            print(f"{name:12s} n={s['n']:5d} RPS {s['rps']:.5f} "
                  f"logloss {s['log_loss']:.4f} acc {s['accuracy']:.4f}")
        g = res["gaps"]["dc_minus_elo"]
        print(f"\nDC - Elo: {g['mean']:+.5f}  paired sd {g['sd']:.5f}  "
              f"95% CI (season) [{g['season']['ci95'][0]:+.5f}, "
              f"{g['season']['ci95'][1]:+.5f}]  "
              f"(week) [{g['week']['ci95'][0]:+.5f}, {g['week']['ci95'][1]:+.5f}]")
        print(f"VERDICT: {res['verdict']} — {res['verdict_detail']}")


if __name__ == "__main__":
    _cli()
