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

import json
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
from wcmodel.backtest.odds_ingest import (
    OUTCOMES, _SYNTHETIC_KEY, entry_close_prices, non_bet_snapshot,
)
from wcmodel.backtest.staking import roi_metrics, settle_bet, stake_fraction

#: The default ADVI draw count for the per-cutoff refit, bound ONCE so the fit
#: knob and the posterior-SE denominator (sqrt(p(1-p)/draws)) can never read two
#: different literals (FIX 7: the coupled 200s used to live at two call sites).
_DEFAULT_DRAWS = 200


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

    #: EVERY column ``compute_elo_history`` consumes — so the memo key changes
    #: whenever ANY Elo-determining input changes. The original key hashed only
    #: ``match_id/home_score/away_score``, omitting ``date`` (orders the path),
    #: the teams (identity), ``neutral`` (home-advantage), and ``match_type``
    #: (K-factor). A revision touching any of those would have stale-served the
    #: cached Elo or bled it across cutoffs that share only the score triple.
    _ELO_KEY_COLS = ("match_id", "date", "home_team", "away_team",
                     "home_score", "away_score", "neutral", "match_type")

    def elo_as_of(self, cutoff) -> pd.DataFrame:
        res = self._played_as_of(cutoff)
        import hashlib
        blob = pd.util.hash_pandas_object(
            res[list(self._ELO_KEY_COLS)].sort_values("match_id"),
            index=False,
        ).values.tobytes()
        key = hashlib.sha256(blob).hexdigest()[:16]
        if key in self._cache:
            self.hits += 1
            # Copy-safety: hand back a COPY so a caller mutating the frame cannot
            # corrupt the cached Elo (and poison every later cutoff that shares
            # this < cutoff result set).
            return self._cache[key].copy()
        elo = compute_elo_history(
            res[["match_id", "date", "home_team", "away_team",
                 "home_score", "away_score", "neutral", "match_type"]],
            config=self._cfg,
        )
        self._cache[key] = elo
        return elo.copy()

    def latest_ratings(self, cutoff) -> dict:
        """Each team's CURRENT as-of-cutoff rating = its latest ``rating_post``.

        For a FUTURE prediction a team's current strength is the rating AFTER its
        last pre-cutoff match (``rating_post``), NOT the ``rating_pre`` of that
        match (which is one match stale — it omits the most recent result). This
        mirrors the proven leakage-safe rule in
        ``model.calibration._leakage_safe_elo`` (latest ``rating_post`` per team,
        stable mergesort) so the Elo baseline and the model fit agree on the
        same as-of-cutoff strength estimate.
        """
        elo = self.elo_as_of(cutoff)
        last = (elo.sort_values("date", kind="mergesort")
                   .groupby("team", sort=False)["rating_post"].last())
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


def _nan_to_none(_const):
    """``json.loads`` ``parse_constant`` hook: map NaN/Infinity -> None.

    A NaN aggregate (empty-bets summary) reloads as ``float('nan')``, and
    ``nan != nan`` would break ``cold == warm`` equality, so we canonicalise it
    to ``None`` (the "no bets" sentinel) on the way back in — applied to BOTH the
    cold canonicalisation and the cache HIT below.
    """
    return None


def _json_canonical(obj):
    """Round-trip ``obj`` through the EXACT JSON form the cache persists+reloads.

    ``cached_walkforward`` writes ``json.dumps(metrics, default=str)`` and reads
    ``json.loads(..., parse_constant=_nan_to_none)`` on a HIT. Applying the same
    transform to the COLD result makes a cold in-memory Metrics byte-identical to
    its cache-HIT reload, so ``cold.to_dict() == warm.to_dict()`` (FIX 4
    value-identical HIT). It folds NaN -> None (empty-bets sentinel; nan != nan
    would otherwise break equality), numpy float64 -> float, and the event_key
    date -> its ISO string, in ONE canonicalisation.
    """
    return json.loads(json.dumps(obj, default=str), parse_constant=_nan_to_none)


def _sample_is_synthetic(sample: dict) -> bool:
    """Authoritative non-real taint for one odds sample (FIX 5).

    Mirrors EXACTLY what ``entry_close_prices`` reads, so a WRAPPED sample, a
    BARE inner snapshot mapping, OR a nested snapshot carrying ``_is_synthetic``
    all self-identify as non-real — a synthetic price can never be lost on the
    way to the ``Metrics`` taint. Cheap (no full parse); pure dict inspection.
    """
    if sample.get("is_synthetic") or sample.get(_SYNTHETIC_KEY):
        return True
    raw = sample.get("sample", sample)
    if not isinstance(raw, dict):
        return False
    if raw.get(_SYNTHETIC_KEY):
        return True
    return any(
        isinstance(v, dict) and v.get(_SYNTHETIC_KEY)
        for v in raw.values()
    )


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
    draws = fit_kwargs.get("draws", _DEFAULT_DRAWS)    # FIX 7: bound ONCE; the
    # fit knob AND the posterior-SE denominator below read this same value.

    # FIX 5: the AUTHORITATIVE taint mirrors what `entry_close_prices` reads —
    # the wrapper `is_synthetic`/`_is_synthetic` flag OR a nested snapshot's
    # `_is_synthetic` — so an UNWRAPPED/nested synthetic sample (no wrapper flag)
    # still taints the whole Metrics. Computed at the top so the no-bets /
    # no-result / odds-less cases (where no per-bet flag is emitted) are still
    # tainted, and OR'd with each per-bet flag below.
    is_synth = any(_sample_is_synthetic(s) for s in odds_samples)

    # FIX 2: the cutoff grid is the ACTUAL driver — the per-matchday refit
    # cadence over `backtest_window(matches, odds_start)`. A fixture whose
    # matchday is NOT in the grid (e.g. before `odds_start`) is OUT OF WINDOW and
    # counted, never bet. Built for BOTH the cache and non-cache paths.
    grid = build_cutoff_grid(matches, bt["odds_start"])
    grid_days = {pd.Timestamp(c).normalize() for c in grid}

    def _compute() -> dict:
        import wcmodel.model.cache as _model_cache

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

        def _bump(reason: str) -> None:
            non_bets[reason] = non_bets.get(reason, 0) + 1

        # --- Stage 1: parse each sample's odds (GUARDED) and bucket by cutoff. ---
        # FIX 6: `entry_close_prices` + the de-vig can raise on an odds-less /
        # malformed fixture (no primary-bookmaker quote, no snapshot <= kickoff).
        # That must be a COUNTED non-bet, never a crash that aborts the whole run.
        # FIX 2: bucket the bettable fixtures by their matchday cutoff so the
        # refit happens ONCE per cutoff (reused across that cutoff's fixtures).
        by_cutoff: dict[pd.Timestamp, list] = {}
        for sample in odds_samples:
            # Normalise to the inner snapshot mapping; the synthetic harness wraps
            # its snapshot under "sample".
            raw = sample.get("sample", sample)
            try:
                pc = entry_close_prices(raw, bookmaker=bt["primary_bookmaker"])
            except (ValueError, KeyError):
                # No primary-bookmaker quote / no snapshot <= kickoff / malformed.
                _bump("no_odds")
                continue

            ekey = pc["event_key"]
            realised = by_key.get(ekey)
            if realised is None:
                _bump("no_result")
                continue

            cutoff = pd.Timestamp(ekey[2]).normalize()   # decision = matchday
            # FIX 2: only fixtures whose matchday is IN the swept grid are
            # eligible (the grid is bounded by `odds_start`); others are counted.
            if cutoff not in grid_days:
                _bump("out_of_window")
                continue

            # Non-bet snapshot filters (sign-flip / stale), logged + counted. The
            # de-vig of the ENTRY price can also reject a malformed line -> no_odds.
            reason = non_bet_snapshot(pc["entry"], entry_ts=pc["entry_ts"],
                                      commence=pc["commence_time"],
                                      max_spread=bt["max_spread"],
                                      stale_seconds=bt["stale_snapshot_seconds"])
            if reason is not None:
                _bump(reason)
                continue
            try:
                market_entry = market_fair_1x2(pc["entry"], method=bt["devig_method"])
            except (ValueError, KeyError, ZeroDivisionError):
                _bump("no_odds")
                continue

            by_cutoff.setdefault(cutoff, []).append((pc, realised, market_entry))

        # --- Stage 2: walk the cutoff grid; refit ONCE per cutoff, reuse it for
        #     every fixture decided at that cutoff (the per-matchday cadence). ---
        for cutoff in sorted(by_cutoff):
            fixtures = by_cutoff[cutoff]
            # Refit the posterior as-of the cutoff ONCE (memoised Elo unblocks the
            # model; cached_fit caches the fit itself). Referenced via the module
            # so a test can monkeypatch `cached_fit` and observe the refit cadence.
            try:
                post, _meta = _model_cache.cached_fit(
                    cutoff=cutoff, store=store,
                    backend=fit_kwargs.get("backend", "advi"),
                    draws=draws,
                    seed=fit_kwargs.get("seed", cfg["seed"]),
                    advi_iters=fit_kwargs.get("advi_iters", 2000),
                    cache_dir=fit_kwargs.get("cache_dir", cache_dir or "data/cache"),
                    config=cfg,
                )
            except KeyError:
                # The as-of-cutoff panel could not be built/fit -> no model price
                # for ANY fixture at this cutoff -> all counted, not bet.
                for _pc, _realised, _mkt in fixtures:
                    _bump("no_model_price")
                continue

            ratings = memo.latest_ratings(cutoff)        # ONCE per cutoff (coherence).

            for pc, realised, market_entry in fixtures:
                home, away = pc["event_key"][0], pc["event_key"][1]
                ekey = pc["event_key"]
                try:
                    model = model_fair_1x2(post, home=home, away=away, neutral=True)
                except KeyError:
                    # A team absent from the as-of-cutoff panel (debutant with no
                    # < cutoff history) -> no model price -> not bettable, logged.
                    _bump("no_model_price")
                    continue

                # FIX 1 (CRITICAL — the leakage fix): the edge, the staked side,
                # and the stake are decided against the de-vigged ENTRY price (the
                # price we transact at at T_bet) — NEVER the CLOSE, which is the
                # kickoff-1min line, information from AFTER the entry decision.
                # The close is used ONLY for CLV (entry/close - 1) and the
                # close-market baseline in reporting.
                edge = edge_vector(model, market_entry)

                # Pick the single best edge outcome to stake (the strongest signal).
                staked = max(OUTCOMES, key=lambda o: edge[o])
                entry_odds = pc["entry"][staked]
                close_odds = pc["close"][staked]
                # Posterior SE on the staked 1X2 prob: bootstrap-free proxy
                # sqrt(p(1-p)/draws) (FIX 7: `draws` is the single bound value).
                p_model = model[staked]
                se = float(np.sqrt(p_model * (1 - p_model) / max(draws, 1)))

                f = stake_fraction(prob=p_model, decimal_odds=entry_odds, edge=edge[staked],
                                   se=se, kelly_fraction=bt["kelly_fraction"],
                                   edge_threshold=bt["edge_threshold"])
                if f <= 0:
                    _bump("below_edge")
                    continue

                outcome = _settle_outcome(int(realised.home_score), int(realised.away_score))
                won = (outcome == staked)
                stake = f                                  # fraction of a 1.0 bankroll unit
                pnl = settle_bet(stake=stake, decimal_odds=entry_odds, won=won,
                                 venue=bt["primary_bookmaker"], commission=bt["commission"])

                # The CLOSE market baseline (reporting only — NOT the edge driver).
                market_close = market_fair_1x2(pc["close"], method=bt["devig_method"])
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
                    # SYNTHETIC marker on EVERY emitted record (D1 rider): a
                    # synthetic ROI/CLV number can never be mistaken for a real
                    # one. FIX 5: derived from the authoritative per-sample flag.
                    "synthetic": bool(pc["is_synthetic"]) or is_synth,
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
        out = Metrics(bets=bets, non_bets=non_bets, summary=summary,
                      is_synthetic=is_synth).to_dict()
        # FIX 4 (value-identical HIT). Canonicalise the COLD result through the
        # EXACT JSON round-trip the cache persists+reloads, so the cold in-memory
        # Metrics is byte-identical to its cache-HIT reload. This subsumes three
        # otherwise-divergent representations: (a) NaN aggregates on the empty-
        # bets path -> JSON `null` -> None (NaN != NaN would break equality);
        # (b) numpy float64 from the de-vig -> plain float; (c) the event_key
        # date -> its ISO string. HIT equality is thereby DEFINED as structural
        # dict equality over the JSON-canonical form.
        return _json_canonical(out)

    if cache_dir is not None:
        # FIX 4: the key folds EVERYTHING that determines the Metrics. Beyond the
        # model/elo/windows DOF it now also keys `baseline` (the Elo-baseline
        # draw_base) and the global `seed`; the backtest subset adds the non-bet
        # thresholds `max_spread`/`stale_snapshot_seconds` (they gate which
        # fixtures bet) alongside the staking/de-vig DOF.
        dof = {k: cfg[k] for k in ("model", "elo", "windows", "baseline")}
        dof["seed"] = cfg["seed"]
        dof["backtest"] = {k: cfg["backtest"][k] for k in
                           ("kelly_fraction", "edge_threshold", "devig_method",
                            "commission", "primary_bookmaker", "max_spread",
                            "stale_snapshot_seconds")}
        # The fit knobs actually used (backend/draws/seed/advi_iters) change the
        # posterior -> the Metrics, so they MUST key the run; `draws` is the
        # single bound default so the key matches the SE denominator.
        fit_key = {
            "backend": fit_kwargs.get("backend", "advi"),
            "draws": draws,
            "seed": fit_kwargs.get("seed", cfg["seed"]),
            "advi_iters": fit_kwargs.get("advi_iters", 2000),
        }
        key = walkforward_key(
            store=store,
            odds_samples=[s.get("sample", s) for s in odds_samples],
            dof_config=dof, cutoff_grid=grid,
            odds_start=cfg["backtest"]["odds_start"],
            last_cutoff=grid[-1] if grid else pd.Timestamp(cfg["backtest"]["odds_start"]),
            fit_kwargs=fit_key,
            # The settled-results identity: a revised result that flips an outcome
            # changes the Metrics, so the settle frame must key the run too.
            settle_results=results_for_settle,
        )
        metrics_dict, _meta = cached_walkforward(key=key, compute=_compute,
                                                 cache_dir=cache_dir)
    else:
        metrics_dict = _compute()

    return Metrics(bets=metrics_dict["bets"], non_bets=metrics_dict["non_bets"],
                   summary=metrics_dict["summary"],
                   is_synthetic=metrics_dict["is_synthetic"])
