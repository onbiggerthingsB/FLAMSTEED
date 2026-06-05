"""Walk-forward backtest engine (spec §2.1) — the integration heart.

``walkforward(store, odds_samples, config) -> Metrics`` sweeps ``cutoff`` FORWARD
over the match dates inside ``backtest_window(matches, odds_start)``. At each
cutoff, for each fixture decided after it:
  1. refit the posterior (``cached_fit``, per-matchday cadence) with the Elo
     recompute MEMOISED (``EloMemo``, the ``features.build`` Phase-4 hook), so the
     O(N)-per-cutoff Elo is not re-paid every fixture;
  2. model fair price — ``predict_1x2`` (1X2, the PRIMARY D2 surface) or a
     ``SimResult`` progression column (outrights, SECONDARY/coverage-gated);
  3. join the de-vigged market (entry + close) via ``odds_ingest``;
  4. ``edge = model_fair − devigged_market``; apply the non-bet filters; size the
     stake (``staking``); settle against the ACTUAL result.

LEAKAGE is impossible by construction: every read is the bitemporal
``store.read(cutoff)`` + strict ``date < cutoff`` (mirrored from ``features.build``
/ ``sim/run.py``), already proven by the P1/P2/P3 canaries and re-asserted by the
backtest-layer canary (Task 6). Seeded throughout.

D1: runs on the real parse path over a fixture / the labelled-NON-REAL synthetic
harness; ``odds_samples`` carrying ``is_synthetic=True`` taint the whole
``Metrics`` (``is_synthetic`` propagates), so no number off the harness is ever a
real edge.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.data import tiers
from wcmodel.data.elo import compute_elo_history
from wcmodel.data.features import valid_played_results
from wcmodel.data.windows import backtest_window
from wcmodel.backtest.baselines import (
    edge_vector, elo_baseline_1x2, market_fair_1x2, model_fair_1x2, rps,
)
from wcmodel.backtest.cache import cached_walkforward, walkforward_key
from wcmodel.backtest.clv import clv_summary
from wcmodel.backtest.devig_select import devig
from wcmodel.backtest.odds_ingest import (
    OUTCOMES, entry_close_prices, event_key, non_bet_snapshot,
)
from wcmodel.backtest.staking import roi_metrics, settle_bet, stake_fraction


@dataclass
class Metrics:
    """Walk-forward output. ``bets`` is the per-bet ledger (entry/close odds,
    edge, stake, P&L, tier tags, model/market/elo probs, realised outcome, AND a
    per-record ``synthetic`` marker); ``summary`` folds CLV + ROI metrics + an
    ``is_synthetic`` flag; ``non_bets`` counts each filter reason; ``is_synthetic``
    taints everything if any odds input was synthetic (D1 rider — every emitted
    record carries an unmissable SYNTHETIC marker so a synthetic number can never be
    mistaken for a real one)."""

    bets: list = field(default_factory=list)
    non_bets: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    is_synthetic: bool = False

    def to_dict(self) -> dict:
        return {"bets": self.bets, "non_bets": self.non_bets,
                "summary": self.summary, "is_synthetic": self.is_synthetic}


class EloMemo:
    """Per-cutoff Elo recompute, MEMOISED on the < cutoff result-set hash.

    ``features.build`` recomputes ``compute_elo_history`` O(N) every cutoff
    (correctness over speed; the documented Phase-4 hook at features.py:174). The
    per-matchday refit cadence means many cutoffs share the SAME < cutoff result
    set, so we cache the Elo frame keyed by that set's content hash: a cache hit
    skips the recompute, a new < cutoff result misses. Correctness is identical to
    ``features.build``'s Elo (same leakage-safe < cutoff_day, valid-played,
    K-wired input; same config-threaded ``compute_elo_history``)."""

    def __init__(self, store, config: dict | None = None):
        self._store = store
        self._cfg = config or load_config()
        self._cache: dict[str, pd.DataFrame] = {}
        self.hits = 0

    def _played_as_of(self, cutoff) -> pd.DataFrame:
        cutoff = pd.Timestamp(cutoff)
        if cutoff.tz is not None:
            cutoff = cutoff.tz_convert("UTC").tz_localize(None)
        res = self._store.read("results", cutoff=cutoff)
        res["date"] = pd.to_datetime(res["date"])
        if getattr(res["date"].dt, "tz", None) is not None:
            res["date"] = res["date"].dt.tz_convert("UTC").dt.tz_localize(None)
        res = res.loc[res["date"] < cutoff.normalize()].copy()
        res = valid_played_results(res)
        res["match_type"] = res["tournament"].map(tiers.match_type)
        return res

    def elo_as_of(self, cutoff) -> pd.DataFrame:
        res = self._played_as_of(cutoff)
        import hashlib
        blob = pd.util.hash_pandas_object(
            res[["match_id", "home_score", "away_score"]].sort_values("match_id"),
            index=False,
        ).values.tobytes()
        key = hashlib.sha256(blob).hexdigest()[:16]
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        elo = compute_elo_history(
            res[["match_id", "date", "home_team", "away_team",
                 "home_score", "away_score", "neutral", "match_type"]],
            config=self._cfg,
        )
        self._cache[key] = elo
        return elo

    def latest_ratings(self, cutoff) -> dict:
        """Each team's latest pre-cutoff ``rating_pre`` (for the Elo baseline)."""
        elo = self.elo_as_of(cutoff)
        last = (elo.sort_values("date", kind="mergesort")
                   .groupby("team", sort=False)["rating_pre"].last())
        return last.to_dict()


def build_cutoff_grid(matches: pd.DataFrame, odds_start, *, cadence: str = "matchday"):
    """The forward cutoff grid: the sorted distinct match dates inside the
    backtest window. With ``cadence="matchday"`` the cutoff for a fixture is the
    decision date = its own match date (the per-matchday refit cadence)."""
    bw = backtest_window(matches, odds_start)
    dates = pd.to_datetime(bw["date"]).dt.normalize().drop_duplicates().sort_values()
    return list(dates)


def _settle_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def walkforward(store, odds_samples: list[dict], *, results_for_settle: pd.DataFrame,
                matches: pd.DataFrame, config: dict | None = None,
                cache_dir=None, fit_kwargs: dict | None = None) -> Metrics:
    """Run the 1X2 walk-forward backtest -> ``Metrics``.

    Parameters
    ----------
    store
        Bitemporal store (leakage-safe reads for the per-cutoff refit).
    odds_samples
        List of per-event snapshot samples (each from the real fixture or the
        labelled-non-real synthetic harness). Joined to results by ``event_key``.
    results_for_settle
        The realised results frame used ONLY to settle a bet AFTER its cutoff
        (settle is post-decision, never a feature). One row per played fixture
        with ``home_team, away_team, date, home_score, away_score, tournament``.
    matches
        The full match panel (a ``date`` column) for ``backtest_window`` / the grid.
    config
        Pre-loaded config (defaults to ``load_config``).
    cache_dir
        If set, the whole run is content-addressed via ``cached_walkforward``.
    fit_kwargs
        Sampler knobs for ``cached_fit`` (backend/draws/seed/advi_iters/cache_dir).
    """
    cfg = config or load_config()
    bt = cfg["backtest"]
    fit_kwargs = fit_kwargs or {}
    is_synth = any(s.get("is_synthetic") or s.get("sample", {}).get("_is_synthetic")
                   for s in odds_samples)

    def _compute() -> dict:
        from wcmodel.model.cache import cached_fit

        memo = EloMemo(store, config=cfg)
        # Index realised results by the odds⇄results identity triple for settle + outcome.
        rfs = results_for_settle.copy()
        rfs["date"] = pd.to_datetime(rfs["date"]).dt.normalize()
        by_key = {
            (r.home_team, r.away_team, r.date.date()): r
            for r in rfs.itertuples(index=False)
        }

        bets: list[dict] = []
        non_bets: dict[str, int] = {}

        for sample in odds_samples:
            # Normalise to the (sample-dict, is_synthetic) shape; the synthetic
            # harness wraps its snapshot under "sample".
            raw = sample.get("sample", sample)
            pc = entry_close_prices(raw, bookmaker=bt["primary_bookmaker"])
            ekey = pc["event_key"]
            realised = by_key.get(ekey)
            if realised is None:
                non_bets["no_result"] = non_bets.get("no_result", 0) + 1
                continue

            cutoff = pd.Timestamp(ekey[2])            # decision = match date (matchday cadence)
            # Non-bet snapshot filters (sign-flip / stale), logged + counted.
            reason = non_bet_snapshot(pc["entry"], entry_ts=pc["entry_ts"],
                                      commence=pc["commence_time"],
                                      max_spread=bt["max_spread"],
                                      stale_seconds=bt["stale_snapshot_seconds"])
            if reason is not None:
                non_bets[reason] = non_bets.get(reason, 0) + 1
                continue

            home, away = ekey[0], ekey[1]
            # --- Refit the posterior as-of the cutoff (memoised Elo unblocks the
            #     model; cached_fit caches the fit itself). ---
            try:
                post, _meta = cached_fit(
                    cutoff=cutoff, store=store,
                    backend=fit_kwargs.get("backend", "advi"),
                    draws=fit_kwargs.get("draws", 200),
                    seed=fit_kwargs.get("seed", cfg["seed"]),
                    advi_iters=fit_kwargs.get("advi_iters", 2000),
                    cache_dir=fit_kwargs.get("cache_dir", cache_dir or "data/cache"),
                    config=cfg,
                )
                model = model_fair_1x2(post, home=home, away=away, neutral=True)
            except KeyError:
                # A team not in the as-of-cutoff panel (debutant with no < cutoff
                # history) -> no model price -> not bettable, logged.
                non_bets["no_model_price"] = non_bets.get("no_model_price", 0) + 1
                continue

            market_close = market_fair_1x2(pc["close"], method=bt["devig_method"])
            edge = edge_vector(model, market_close)

            # Pick the single best edge outcome to stake (the strongest signal).
            staked = max(OUTCOMES, key=lambda o: edge[o])
            entry_odds = pc["entry"][staked]
            close_odds = pc["close"][staked]
            # Posterior SE on the staked 1X2 prob: bootstrap-free proxy = sqrt(p(1-p)/draws).
            p_model = model[staked]
            se = float(np.sqrt(p_model * (1 - p_model) / max(fit_kwargs.get("draws", 200), 1)))

            f = stake_fraction(prob=p_model, decimal_odds=entry_odds, edge=edge[staked],
                               se=se, kelly_fraction=bt["kelly_fraction"],
                               edge_threshold=bt["edge_threshold"])
            if f <= 0:
                non_bets["below_edge"] = non_bets.get("below_edge", 0) + 1
                continue

            outcome = _settle_outcome(int(realised.home_score), int(realised.away_score))
            won = (outcome == staked)
            stake = f                                  # fraction of a 1.0 bankroll unit
            pnl = settle_bet(stake=stake, decimal_odds=entry_odds, won=won,
                             venue=bt["primary_bookmaker"], commission=bt["commission"])

            # Tier tags + baselines (Elo from the SAME memoised ratings — coherence).
            ratings = memo.latest_ratings(cutoff)
            elo_p = elo_baseline_1x2(
                rating_home=ratings.get(home, cfg["elo"]["initial_rating"]),
                rating_away=ratings.get(away, cfg["elo"]["initial_rating"]),
                neutral=True, config=cfg,
            )
            bets.append({
                "event_key": list(ekey), "cutoff": str(cutoff), "staked": staked,
                "entry_odds": entry_odds, "close_odds": close_odds,
                "edge": edge[staked], "stake": stake, "pnl": pnl, "won": won,
                "outcome": outcome,
                "match_type": tiers.match_type(getattr(realised, "tournament", "")),
                "confederation_home": tiers.confederation(home),
                "model": model, "market": market_close, "elo": elo_p,
                "rps_model": rps(model, outcome), "rps_market": rps(market_close, outcome),
                "rps_elo": rps(elo_p, outcome),
                # SYNTHETIC marker on EVERY emitted record (D1 rider): a synthetic
                # ROI/CLV number can never be mistaken for a real backtest number.
                "synthetic": is_synth,
            })

        clv = clv_summary([{"entry_odds": b["entry_odds"], "close_odds": b["close_odds"]}
                           for b in bets])
        roi = roi_metrics(pnls=[b["pnl"] for b in bets],
                          stakes=[b["stake"] for b in bets], start=1.0)
        summary = {
            **{f"clv_{k}": v for k, v in clv.items()},
            **{f"roi_{k}": v for k, v in roi.items()},
            "mean_rps_model": float(np.mean([b["rps_model"] for b in bets])) if bets else float("nan"),
            "mean_rps_market": float(np.mean([b["rps_market"] for b in bets])) if bets else float("nan"),
            "mean_rps_elo": float(np.mean([b["rps_elo"] for b in bets])) if bets else float("nan"),
            "is_synthetic": is_synth,
        }
        return Metrics(bets=bets, non_bets=non_bets, summary=summary,
                       is_synthetic=is_synth).to_dict()

    if cache_dir is not None:
        grid = build_cutoff_grid(matches, cfg["backtest"]["odds_start"])
        dof = {k: cfg[k] for k in ("model", "elo", "windows")}
        dof["backtest"] = {k: cfg["backtest"][k] for k in
                           ("kelly_fraction", "edge_threshold", "devig_method",
                            "commission", "primary_bookmaker")}
        key = walkforward_key(
            store=store,
            odds_samples=[s.get("sample", s) for s in odds_samples],
            dof_config=dof, cutoff_grid=grid,
            odds_start=cfg["backtest"]["odds_start"],
            last_cutoff=grid[-1] if grid else pd.Timestamp(cfg["backtest"]["odds_start"]),
        )
        metrics_dict, _meta = cached_walkforward(key=key, compute=_compute,
                                                 cache_dir=cache_dir)
    else:
        metrics_dict = _compute()

    return Metrics(bets=metrics_dict["bets"], non_bets=metrics_dict["non_bets"],
                   summary=metrics_dict["summary"],
                   is_synthetic=metrics_dict["is_synthetic"])
