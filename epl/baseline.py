"""The baseline and the bar: walk-forward Elo against the market and the coin.

THE QUESTION. The World Cup model tied naive Elo over its 104-match replay and
lost to de-vigged market prices by ~0.010 mean RPS. Before any of that
architecture is pointed at the Premier League, the honest bar has to exist
in-repo: what does plain walk-forward Elo score here, what does the closing
market score, and how wide is the gap that a Bayesian scoreline model would
have to close? This module produces those three numbers on one complete-case
match set.

THE PROTOCOL, fixed before anything was scored.

    TUNE      2014/15-2017/18.  K, home advantage, the promoted-club seed and
                                the season carryover are chosen here and only
                                here, on mean RPS over 2015/16-2017/18 (the
                                first season is Elo burn-in and is not scored).
    FREEZE                      The winning configuration is written to
                                `tuning.json` and used verbatim below.
    SCORE     2018/19-2025/26.  Never touched during tuning. Eight seasons,
                                complete-case on closing odds.

Everything inside the scoring window is walk-forward: the ratings, the
ordered-logit head that turns them into probabilities, and the base rate. At
every cutoff block, each of the three is a function of strictly earlier matches
only (:mod:`epl.walk`). The market forecaster is the one exception and needs no
walk — a closing price is by definition information available before kickoff.

WHAT WOULD MAKE THIS WRONG, and what is done about it:

* Tuning on the scoring window. The split is a module constant, the tuner
  refuses a scoring season, and the frozen configuration is recorded with the
  grid that produced it.
* A head that has seen its own match. The head is refit per block on rows
  strictly before it, and `epl.tests` includes a canary that rewrites every
  result after a cutoff and asserts the earlier forecasts are bit-identical.
* Comparing forecasters on different matches. Everything is scored on one
  complete-case index, and :func:`epl.score.paired_gap` refuses arrays of
  different length rather than aligning them for you.
* Picking the de-vig that flatters the model. Both are reported, and
  ``proportional`` is the headline because that is the convention the published
  ~0.196 bar is quoted on.

NO BETTING. Odds are an internal accuracy benchmark and nothing else.
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from epl import devig, elo as elo_mod, ordlogit, paths, score as score_mod, walk
from epl.schema import sort_for_walk_forward

__all__ = ["TUNE_SEASONS", "SCORE_SEASONS", "tune", "run", "load_matches"]

#: Hyperparameters are chosen on these seasons and nowhere else.
TUNE_SEASONS = ("2014/15", "2015/16", "2016/17", "2017/18")

#: The first tuning season is Elo burn-in: with every club at `initial_rating`
#: the ratings carry no information, so scoring it would measure the seed.
TUNE_BURN_IN = ("2014/15",)

#: Scored, never tuned on.
SCORE_SEASONS = ("2018/19", "2019/20", "2020/21", "2021/22", "2022/23",
                 "2023/24", "2024/25", "2025/26")

#: The tuning grid. `carryover = 1.0` (no summer regression) and
#: `promoted_offset = 0` (seed promoted clubs AT the division mean) are both in
#: the grid on purpose: the two league-specific rules have to be allowed to
#: lose, or "tuned" would mean "assumed".
K_GRID = (10.0, 15.0, 20.0, 25.0, 30.0, 40.0)
HOME_ADV_GRID = (40.0, 60.0, 80.0, 100.0)
CARRYOVER_GRID = (1.0, 0.85, 0.75)
PROMOTED_OFFSET_GRID = (0.0, -75.0, -150.0, -225.0)

_ODDS = ["odds_h", "odds_d", "odds_a"]


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def load_matches(path=None) -> pd.DataFrame:
    """The tidy match table in walk-forward order, played matches only."""
    df = pd.read_parquet(path or paths.MATCHES_PARQUET)
    df = df[df["played"]].copy()
    return sort_for_walk_forward(df)


def _week_blocks(df: pd.DataFrame) -> np.ndarray:
    """Bootstrap blocks: one per (season, ISO calendar week).

    A matchweek is the natural dependence unit — the clubs in it share a rating
    state, a fixture congestion, and a slice of the season — and the source has
    no matchweek column, so the calendar week within a season stands in for it.
    Weeks carrying a midweek round are simply larger blocks, which is the right
    behaviour: those matches are more dependent, not less.
    """
    iso = pd.to_datetime(df["date"]).dt.isocalendar()
    return np.array([f"{s}|{int(y)}W{int(w):02d}" for s, y, w
                     in zip(df["season"], iso["year"], iso["week"])], dtype=object)


# --------------------------------------------------------------------------
# the three forecasters
# --------------------------------------------------------------------------
def walk_forward_head(history: pd.DataFrame, want: np.ndarray,
                      min_fit: int = ordlogit.MIN_FIT_MATCHES,
                      warm_start: bool = False,
                      ) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Per-match 1X2 from the Elo edge, the head refit at every cutoff block.

    ``history`` is :func:`epl.elo.compute_elo_history`'s first return value, in
    chronological order. ``want`` is a boolean mask of the rows a forecast is
    needed for. Rows that are not wanted, or that arrive before ``min_fit``
    earlier matches exist, come back as NaN and are dropped by the complete-case
    filter rather than being filled in with something.

    The point-in-time argument in one line: blocks partition a chronologically
    sorted frame into contiguous ranges, so "every row in a strictly earlier
    block" is exactly ``history[:rows[0]]`` — the head fitted for a block
    literally cannot address its own rows.

    ``warm_start`` is OFF by default and should stay off for anything reported.
    Warm-starting each refit from the previous block's parameters is ~15%
    faster and lands ~3e-7 away in probability, which is invisible in a
    reported RPS but makes a block's forecast depend on which EARLIER blocks
    happened to be scored — and which blocks are scored depends on ``want``.
    Cold-starting makes the forecast for a block a function of its own history
    and nothing else, which is a property worth 15%.
    """
    edge = history["elo_diff_pre"].to_numpy(float)
    y = score_mod.outcome_codes(history["ftr"].to_numpy())
    probs = np.full((len(history), 3), np.nan)
    log: list[dict[str, Any]] = []
    prev: ordlogit.OrdLogitParams | None = None
    for rows in walk.groups(history["block"].to_numpy()):
        cut = int(rows[0])
        if cut < min_fit or not want[rows].any():
            continue
        params = ordlogit.fit(edge[:cut], y[:cut],
                              init=prev if warm_start else None)
        prev = params
        probs[rows] = ordlogit.predict(params, edge[rows])
        log.append({"block_start_row": cut, **params.as_dict()})
    return probs, log


def walk_forward_base_rate(history: pd.DataFrame, want: np.ndarray,
                           min_fit: int = ordlogit.MIN_FIT_MATCHES,
                           ) -> np.ndarray:
    """The home-advantage-only forecaster: earlier H/D/A frequencies.

    Constant across fixtures within a block and updated as results arrive, so
    it is the honest "know nothing except that home teams win more often"
    reference rather than a full-sample frequency that has seen the matches it
    is scored on.
    """
    y = score_mod.outcome_codes(history["ftr"].to_numpy())
    onehot = np.zeros((len(history), 3))
    onehot[np.arange(y.size), y] = 1.0
    cumulative = np.cumsum(onehot, axis=0)
    probs = np.full((len(history), 3), np.nan)
    for rows in walk.groups(history["block"].to_numpy()):
        cut = int(rows[0])
        if cut < min_fit or not want[rows].any():
            continue
        counts = cumulative[cut - 1]
        probs[rows] = counts / counts.sum()
    return probs


def market_probabilities(df: pd.DataFrame, method: str = "proportional",
                         ) -> np.ndarray:
    """De-vigged closing prices. BENCHMARK ONLY. NaN where a price is missing."""
    prices = df[_ODDS].to_numpy(float)
    have = np.isfinite(prices).all(axis=1)
    probs = np.full((len(df), 3), np.nan)
    if have.any():
        fn = {"proportional": devig.proportional, "shin": devig.shin}[method]
        probs[have] = fn(prices[have])
    return probs


# --------------------------------------------------------------------------
# one evaluation
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Evaluation:
    """Everything one (config, window) evaluation produced."""

    config: elo_mod.EloConfig
    frame: pd.DataFrame                 # complete-case rows, with probabilities
    scores: dict[str, score_mod.Score]
    head_log: list[dict[str, Any]]
    season_starts: list[dict[str, Any]]


def evaluate(matches: pd.DataFrame, config: elo_mod.EloConfig,
             score_seasons: Iterable[str], require_odds: bool = True,
             warm_start: bool = False) -> Evaluation:
    """Run all three forecasters over `matches`, score them on `score_seasons`.

    The Elo walk always covers the WHOLE frame — a forecast for 2018/19 needs
    2014/15 in its history — while scoring is restricted to `score_seasons`.
    """
    history, season_starts = elo_mod.compute_elo_history(matches, config)
    wanted = set(score_seasons)
    want = matches["season"].isin(wanted).to_numpy()

    elo_probs, head_log = walk_forward_head(history, want,
                                            warm_start=warm_start)
    base_probs = walk_forward_base_rate(history, want)
    mkt_prop = market_probabilities(matches, "proportional")
    mkt_shin = market_probabilities(matches, "shin")

    complete = (want
                & np.isfinite(elo_probs).all(axis=1)
                & np.isfinite(base_probs).all(axis=1))
    if require_odds:
        complete &= np.isfinite(mkt_prop).all(axis=1)

    idx = np.flatnonzero(complete)
    frame = pd.DataFrame({
        "match_id": matches["match_id"].to_numpy()[idx],
        "season": matches["season"].to_numpy()[idx],
        "date": matches["date"].to_numpy()[idx],
        "home_key": matches["home_key"].to_numpy()[idx],
        "away_key": matches["away_key"].to_numpy()[idx],
        "ftr": matches["ftr"].astype(str).to_numpy()[idx],
        "elo_diff_pre": history["elo_diff_pre"].to_numpy()[idx],
        "home_promoted": history["home_promoted"].to_numpy()[idx],
        "away_promoted": history["away_promoted"].to_numpy()[idx],
    })
    frame["block"] = _week_blocks(matches.iloc[idx])
    y = score_mod.outcome_codes(frame["ftr"].to_numpy())
    frame["y"] = y

    columns = {"elo": elo_probs, "base": base_probs,
               "market": mkt_prop, "market_shin": mkt_shin}
    scores: dict[str, score_mod.Score] = {}
    for name, p in columns.items():
        sub = p[idx]
        for j, outcome in enumerate(score_mod.OUTCOMES):
            frame[f"{name}_{outcome}"] = sub[:, j]
        if np.isfinite(sub).all():
            frame[f"{name}_rps"] = score_mod.rps(sub, y)
            scores[name] = score_mod.summarise(name, sub, y)
    return Evaluation(config=config, frame=frame, scores=scores,
                      head_log=head_log, season_starts=season_starts)


# --------------------------------------------------------------------------
# tuning
# --------------------------------------------------------------------------
def tune(matches: pd.DataFrame, grid: Iterable[elo_mod.EloConfig] | None = None,
         verbose: bool = True) -> dict[str, Any]:
    """Grid-search the Elo hyperparameters on the TUNING seasons only.

    Objective: mean normalised RPS of the walk-forward Elo + ordered-logit
    forecaster over the tuning seasons after burn-in. Complete-case on odds is
    NOT required here — the tuner is comparing Elo configurations with each
    other, not with the market, and 2014/15-2017/18 has full odds coverage
    anyway, so the two sets coincide.

    Refuses to see a scoring season. That refusal is the whole point of the
    function existing separately from :func:`run`.
    """
    leak = sorted(set(matches["season"]) & set(SCORE_SEASONS))
    if leak:
        raise ValueError(
            f"the tuning frame contains scoring season(s) {leak}: "
            "hyperparameters chosen against the window they will be scored on "
            "are not hyperparameters, they are fitted parameters")
    scored = [s for s in TUNE_SEASONS if s not in TUNE_BURN_IN]
    configs = list(grid) if grid is not None else [
        elo_mod.EloConfig(k=k, home_advantage=h, carryover=c,
                          promoted_offset=o)
        for k, h, c, o in itertools.product(
            K_GRID, HOME_ADV_GRID, CARRYOVER_GRID, PROMOTED_OFFSET_GRID)]

    rows: list[dict[str, Any]] = []
    started = time.time()
    for i, cfg in enumerate(configs):
        ev = evaluate(matches, cfg, scored, require_odds=False)
        s = ev.scores["elo"]
        rows.append({**cfg.as_dict(), "n": s.n, "rps": s.rps,
                     "log_loss": s.log_loss, "accuracy": s.accuracy})
        if verbose and (i + 1) % 24 == 0:
            print(f"  [{i + 1}/{len(configs)}] best so far "
                  f"{min(r['rps'] for r in rows):.5f} "
                  f"({time.time() - started:.0f}s)", flush=True)

    table = pd.DataFrame(rows).sort_values(
        # Deterministic: RPS first, then a parsimony order — smaller K, less
        # summer regression, smaller seeding intervention — so a numerical tie
        # never resolves on row order.
        ["rps", "k", "carryover", "promoted_offset"],
        ascending=[True, True, False, False], kind="mergesort")
    best = table.iloc[0]
    chosen = elo_mod.EloConfig(k=float(best["k"]),
                               home_advantage=float(best["home_advantage"]),
                               carryover=float(best["carryover"]),
                               promoted_offset=float(best["promoted_offset"]))
    return {
        "objective": "mean normalised RPS, walk-forward Elo + ordered logit",
        "tune_seasons": list(TUNE_SEASONS),
        "burn_in_seasons": list(TUNE_BURN_IN),
        "scored_seasons": scored,
        "n_configs": len(configs),
        "n_matches": int(best["n"]),
        "chosen": chosen.as_dict(),
        "best_rps": float(best["rps"]),
        "worst_rps": float(table["rps"].max()),
        "median_rps": float(table["rps"].median()),
        "spread_rps": float(table["rps"].max() - table["rps"].min()),
        "table": table.to_dict(orient="records"),
        "seconds": round(time.time() - started, 1),
    }


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def run(matches: pd.DataFrame | None = None,
        config: elo_mod.EloConfig | None = None,
        n_boot: int = 10_000) -> dict[str, Any]:
    """Score the three forecasters on the frozen scoring window."""
    matches = load_matches() if matches is None else matches
    if config is None:
        with open(paths.TUNING_PATH) as fh:
            config = elo_mod.EloConfig(**{
                k: v for k, v in json.load(fh)["chosen"].items()})
    ev = evaluate(matches, config, SCORE_SEASONS)
    frame = ev.frame

    y = frame["y"].to_numpy()
    r = {name: frame[f"{name}_rps"].to_numpy()
         for name in ("elo", "base", "market", "market_shin")}
    gaps: dict[str, Any] = {}
    for a, b in (("elo", "market"), ("elo", "base"), ("market", "base"),
                 ("elo", "market_shin")):
        d, mean, sd = score_mod.paired_gap(a, r[a], b, r[b])
        out: dict[str, Any] = {"mean": mean, "sd": sd,
                               "se_iid": sd / np.sqrt(d.size), "n": int(d.size)}
        for label, blocks_ in (("week", frame["block"].to_numpy()),
                               ("season", frame["season"].to_numpy())):
            lo, hi, nb = score_mod.block_bootstrap_ci(d, blocks_, n_boot=n_boot)
            out[f"ci95_{label}"] = [lo, hi]
            out[f"n_blocks_{label}"] = nb
        gaps[f"{a}_minus_{b}"] = out

    per_season = (frame.groupby("season")
                  .agg(n=("match_id", "size"),
                       elo=("elo_rps", "mean"), market=("market_rps", "mean"),
                       market_shin=("market_shin_rps", "mean"),
                       base=("base_rps", "mean"))
                  .reset_index())
    per_season["elo_minus_market"] = per_season["elo"] - per_season["market"]

    return {
        "config": config.as_dict(),
        "score_seasons": list(SCORE_SEASONS),
        "n_matches": int(len(frame)),
        "scores": {k: v.as_dict() for k, v in ev.scores.items()},
        "gaps": gaps,
        "per_season": per_season.to_dict(orient="records"),
        "subsets": _subsets(frame, n_boot),
        "calibration": _calibration(frame),
        "season_starts": ev.season_starts,
        "head_final": ev.head_log[-1] if ev.head_log else None,
        "n_head_fits": len(ev.head_log),
        "frame": frame,
    }


def _subsets(frame: pd.DataFrame, n_boot: int) -> dict[str, Any]:
    """Headline numbers on slices that a single mean would hide.

    ``no_2025_26`` exists because the last season's odds coverage is a
    CONTIGUOUS tail, not a random sample: prices stop after 2026-01-08, and the
    covered rows have a home-win rate of 0.452 against 0.394 for the uncovered
    ones. The paired gap is unaffected by that — both forecasters see the same
    fixtures — but the LEVELS are computed on a first-half-of-season slice, so
    the seven fully covered seasons are reported alongside.

    ``promoted`` splits on whether either club is in its first season up. The
    promoted-club seed is the most arbitrary number in the Elo configuration,
    and this is where its cost, if any, shows up.
    """
    out: dict[str, Any] = {}
    masks = {
        "all": np.ones(len(frame), dtype=bool),
        "no_2025_26": (frame["season"] != "2025/26").to_numpy(),
        "promoted": (frame["home_promoted"] | frame["away_promoted"]).to_numpy(),
        "established": ~(frame["home_promoted"] | frame["away_promoted"]).to_numpy(),
    }
    for name, mask in masks.items():
        sub = frame[mask]
        if len(sub) < 50:
            continue
        d = (sub["elo_rps"] - sub["market_rps"]).to_numpy()
        lo, hi, nb = score_mod.block_bootstrap_ci(
            d, sub["block"].to_numpy(), n_boot=n_boot)
        out[name] = {
            "n": int(len(sub)),
            "elo": float(sub["elo_rps"].mean()),
            "market": float(sub["market_rps"].mean()),
            "base": float(sub["base_rps"].mean()),
            "gap": float(d.mean()), "gap_sd": float(d.std(ddof=1)),
            "gap_ci95_week": [lo, hi], "n_blocks": nb,
        }
    return out


def _calibration(frame: pd.DataFrame) -> dict[str, Any]:
    """Mean forecast against realised frequency, per outcome, per forecaster.

    Not a scoring rule — a smell test. A forecaster whose mean home
    probability is 0.44 while home teams win 0.45 of the time is at least
    pointed the right way; one that is 4 points off has a bug or a bias that
    RPS will only partly reveal.
    """
    y = frame["y"].to_numpy()
    realised = [float((y == k).mean()) for k in range(3)]
    out: dict[str, Any] = {"realised": dict(zip(score_mod.OUTCOMES, realised))}
    for name in ("elo", "market", "market_shin", "base"):
        out[name] = {o: float(frame[f"{name}_{o}"].mean())
                     for o in score_mod.OUTCOMES}
    return out


def sensitivity(matches: pd.DataFrame, configs: dict[str, elo_mod.EloConfig],
                ) -> list[dict[str, Any]]:
    """Score-window results under alternative Elo configurations. DIAGNOSTIC.

    This is reported AFTER the frozen configuration has been scored, and it
    selects nothing — its job is to answer "how much of the headline is the
    tuning?" If the conclusion survives every configuration in the grid, the
    tuning was not load-bearing and the reader should be told so; if it does
    not, the reader should be told that too. Reading a winner off this table
    would be tuning on the scoring window with extra steps.
    """
    rows = []
    for label, cfg in configs.items():
        ev = evaluate(matches, cfg, SCORE_SEASONS)
        gap = (ev.frame["elo_rps"] - ev.frame["market_rps"])
        rows.append({"label": label, **cfg.as_dict(),
                     "n": int(len(ev.frame)),
                     "elo": ev.scores["elo"].rps,
                     "market": ev.scores["market"].rps,
                     "base": ev.scores["base"].rps,
                     "gap": float(gap.mean()),
                     "log_loss": ev.scores["elo"].log_loss,
                     "accuracy": ev.scores["elo"].accuracy})
    return rows


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tune", action="store_true",
                    help="grid-search on the tuning seasons and freeze")
    ap.add_argument("--score", action="store_true",
                    help="score the frozen configuration on the score window")
    ap.add_argument("--sensitivity", action="store_true",
                    help="score-window results under alternative Elo configs "
                         "(a DIAGNOSTIC printed after the fact; it selects "
                         "nothing)")
    ap.add_argument("--n-boot", type=int, default=10_000)
    args = ap.parse_args()
    paths.BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    matches = load_matches()

    if args.tune:
        result = tune(matches[matches["season"].isin(TUNE_SEASONS)].copy())
        paths.TUNING_PATH.write_text(json.dumps(result, indent=2) + "\n")
        print(f"chosen: {result['chosen']}")
        print(f"tune RPS best {result['best_rps']:.5f} / median "
              f"{result['median_rps']:.5f} / worst {result['worst_rps']:.5f} "
              f"over {result['n_configs']} configs, {result['seconds']}s")

    if args.score:
        result = run(matches, n_boot=args.n_boot)
        frame = result.pop("frame")
        frame.to_parquet(paths.BASELINE_PREDICTIONS)
        paths.SCORES_PATH.write_text(json.dumps(result, indent=2,
                                                default=str) + "\n")
        for name, s in result["scores"].items():
            print(f"{name:12s} n={s['n']:5d}  RPS {s['rps']:.4f}  "
                  f"logloss {s['log_loss']:.4f}  acc {s['accuracy']:.4f}")
        g = result["gaps"]["elo_minus_market"]
        print(f"elo - market: {g['mean']:+.4f}  paired sd {g['sd']:.4f}  "
              f"95% CI (week blocks) [{g['ci95_week'][0]:+.4f}, "
              f"{g['ci95_week'][1]:+.4f}]")

    if args.sensitivity:
        with open(paths.TUNING_PATH) as fh:
            tuning = json.load(fh)
        chosen = elo_mod.EloConfig(**tuning["chosen"])
        table = pd.DataFrame(tuning["table"]).sort_values("rps")
        configs = {"chosen": chosen}
        # The tuning grid's own extremes, plus the two rules the grid was
        # allowed to reject, plus margin-of-victory (never the headline).
        for label, row in (("tune_worst", table.iloc[-1]),
                           ("tune_2nd", table.iloc[1]),
                           ("tune_median", table.iloc[len(table) // 2])):
            configs[label] = elo_mod.EloConfig(
                k=float(row["k"]), home_advantage=float(row["home_advantage"]),
                carryover=float(row["carryover"]),
                promoted_offset=float(row["promoted_offset"]))
        configs["no_promoted_penalty"] = chosen.replace(promoted_offset=0.0)
        configs["no_carryover_regression"] = chosen.replace(carryover=1.0)
        configs["k10"] = chosen.replace(k=10.0)
        configs["k40"] = chosen.replace(k=40.0)
        configs["mov_on"] = chosen.replace(mov=True, k=chosen.k * 7.5)
        rows = sensitivity(matches, configs)
        out = paths.BASELINE_DIR / "sensitivity.json"
        out.write_text(json.dumps(rows, indent=2) + "\n")
        for row in rows:
            print(f"{row['label']:24s} K={row['k']:<5g} H={row['home_advantage']:<5g} "
                  f"carry={row['carryover']:<5g} off={row['promoted_offset']:<7g} "
                  f"elo {row['elo']:.4f}  gap {row['gap']:+.4f}")


if __name__ == "__main__":
    _cli()
