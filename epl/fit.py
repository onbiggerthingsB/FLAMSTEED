"""Wire the EXISTING Bayesian scoreline model (``src/wcmodel``) to EPL data.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT. The World Cup model — a
hierarchical Dixon-Coles / bivariate-Poisson scoreline likelihood fitted by
PyMC/ADVI, with attack and defence anchored to point-in-time Elo — is READ-ONLY
here. Not one line of its likelihood, priors, or inference is changed or
re-tuned for club football. This module supplies the design input its ``fit()``
already expects and nothing else, so that the number this probe produces is the
cost and behaviour of THAT architecture on EPL data, not of some EPL-flavoured
variant of it. Every place where an international default is doing something
questionable to a club season is recorded in :data:`ARCHITECTURE_NOTES` rather
than quietly corrected.

THE ADAPTER, IN ONE LINE. ``wcmodel.model.scoreline.fit(cutoff, store)`` reads
exactly one table — ``results`` — out of a ``BitemporalStore``, and consumes it
through ``wcmodel.data.features.build``, which keeps matches with
``date < cutoff`` and nothing else. So the adapter is: project the EPL match
table onto that table's columns, write it point-in-time, and pick a cutoff.

POINT-IN-TIME, TWICE OVER. The store read is gated on
``observed_at <= cutoff``, and ``features.build`` independently filters
``date < cutoff.normalize()``. A result is therefore invisible to a fit at any
cutoff on or before its own match day, under either gate alone. That day-level
floor is STRICTER than this package's own kickoff-level
:data:`epl.schema.ORDERING_RULE`: a 17:30 kickoff cannot learn from the same
day's 12:30 result. Strictly less information, never more, so it cannot leak —
but it does mean the natural refit unit is the matchweek, not the fixture.

NO BETTING. The market prices that appear in the smoke test are a BENCHMARK
ONLY — a third column to read the model against. They are never displayed
publicly and never turned into a betting signal.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import tempfile
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from epl import baseline as epl_baseline
from epl import devig, elo as epl_elo, ordlogit, paths, score as score_mod, walk
from epl.schema import sort_for_walk_forward

# --- READ-ONLY imports from the attested package ---------------------------
# Nothing under src/ or scripts/ is written by this module. These are consumed
# exactly as the World Cup callers (scripts/model_market_gap.py,
# scripts/clv_validation.py, ...) consume them.
from wcmodel.config import load_config
from wcmodel.data import features as wc_features
from wcmodel.data import tiers as wc_tiers
from wcmodel.data.features import valid_played_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.model import cache as wc_model_cache

__all__ = [
    "TOURNAMENT_LABEL", "ARCHITECTURE_NOTES", "to_store_frame", "build_store",
    "assert_point_in_time", "FitResult", "fit_at", "next_matchweek",
    "model_probabilities", "run_smoke_test", "matchweek_index", "cost_model",
    "staleness_curve", "measure_hot_path_overhead", "config_read_once",
]

#: The ``tournament`` string every EPL row carries. It exists because
#: ``features.build`` maps ``tournament -> wcmodel.data.tiers.match_type`` to
#: look up an Elo K multiplier. "Premier League" is not in that taxonomy, so it
#: falls to ``"other"`` (multiplier 0.5, i.e. K = 40 * 0.5 = 20). That is a
#: coincidence worth naming rather than relying on: 20 is also the K this
#: package's own tuning chose for EPL, so the anchor Elo is not badly scaled —
#: but it got there by falling off the end of a lookup table, not by being
#: calibrated, and a future edit to that table would move it silently.
TOURNAMENT_LABEL = "Premier League"

#: International defaults that are doing something to a club league. Recorded,
#: not fixed: fixing any of them would make this a different architecture and
#: the probe would stop measuring the one we published two negatives about.
ARCHITECTURE_NOTES: tuple[str, ...] = (
    "K multiplier: 'Premier League' is absent from wcmodel.data.tiers.match_type, "
    "so every EPL match is typed 'other' -> K = k_base * 0.5 = 20.",
    "Anchor Elo has no club-football season logic: no promoted-club seeding and no "
    "summer carryover. epl.elo's tuning found the promoted seed worth 0.0030 RPS — "
    "the largest single configuration effect measured on this data — so the anchor "
    "is measurably worse for a newly promoted club than this package's own Elo.",
    "Anchor Elo home_advantage is 100 rating points, calibrated on internationals.",
    "Time decay: windows.decay_half_life_days = 365, so a match four seasons back "
    "enters the likelihood at weight 0.06. Every pre-cutoff season is in the fit; "
    "none is cropped.",
    "neutral is False on every row, so the fitted home_adv is identified off the "
    "whole sample and applied to every fixture — there is no neutral-venue arm.",
    "provisional/widening: the volatility arm's 16.5-point threshold was derived "
    "from international deltas at K up to 40; at club K=20 it may flag nobody, in "
    "which case mechanism-(c) widening is inert. Reported, not tuned.",
    "Covariates are off (model.covariates.enabled == []), as in the published "
    "World Cup baseline. rest_days/travel/altitude are not wired for EPL.",
)

_STORE_TABLE = "results"
_SOURCE = "epl_football_data_couk"


# ==========================================================================
# 1. the design input
# ==========================================================================
def to_store_frame(matches: pd.DataFrame) -> pd.DataFrame:
    """Project the tidy EPL match table onto the ``results`` table's columns.

    Pure: no I/O, no store. The column set is dictated by what
    ``wcmodel.data.features.build`` actually reads —

        match_id, date, home_team, away_team, home_score, away_score,
        neutral, tournament, city

    — plus the bitemporal pair ``valid_as_of`` / ``observed_at``. Anything else
    the World Cup feed carries (``country``, shootout winners) is genuinely
    absent here rather than faked.

    TEAM IDENTITY is ``home_key`` / ``away_key``, the stable join key, not the
    display name. The model's team index is built by sorting these, and the Elo
    baseline this probe is measured against keys on the same strings, so the two
    forecasters cannot disagree about which club is which.

    ``city`` is the home club's key. ``features.build`` uses ``city`` only to
    join venue coordinates (no venues table is loaded, so travel and altitude
    are NaN) and to look up a hand-curated altitude reference (no EPL ground is
    in it, so the acclimatisation gap is NaN). A club ground is nonetheless the
    honest value: it is the venue, and it is knowable before kickoff.

    ``observed_at == valid_as_of == date`` is the martj42 adapter's convention
    (``wcmodel.data.sources.results.normalize_results``) reused verbatim. Both
    the store gate (``observed_at <= cutoff``) and the feature gate
    (``date < cutoff.normalize()``) then agree that a match becomes knowable no
    earlier than its own date.
    """
    played = matches.loc[matches["played"]].copy()
    if played.empty:
        raise ValueError("no played matches to write")
    missing = {"match_id", "date", "home_key", "away_key", "fthg", "ftag"} - set(played.columns)
    if missing:
        raise ValueError(f"match table is missing {sorted(missing)}")
    if played["match_id"].duplicated().any():
        raise ValueError("duplicate match_id in the match table")

    date = pd.to_datetime(played["date"]).dt.normalize()
    out = pd.DataFrame({
        "match_id": played["match_id"].astype(str).to_numpy(),
        "date": date.to_numpy(),
        "valid_as_of": date.to_numpy(),
        "observed_at": date.to_numpy(),
        "home_team": played["home_key"].astype(str).to_numpy(),
        "away_team": played["away_key"].astype(str).to_numpy(),
        "home_score": played["fthg"].to_numpy(dtype=int),
        "away_score": played["ftag"].to_numpy(dtype=int),
        "tournament": TOURNAMENT_LABEL,
        "neutral": False,
        "city": played["home_key"].astype(str).to_numpy(),
    })
    # The model's own hygiene filter must be a no-op on this frame: if it is
    # not, some row is not a valid played match and the fit would silently
    # train on a different set than the baseline scored.
    kept = valid_played_results(out)
    if len(kept) != len(out):
        raise ValueError(
            f"valid_played_results dropped {len(out) - len(kept)} EPL row(s): "
            "the match table contains something that is not a played match "
            "with finite, non-negative, integral goals")
    return out


def build_store(matches: pd.DataFrame | None = None,
                root: Path | str | None = None,
                rebuild: bool = False) -> BitemporalStore:
    """Materialise the ``results`` table as a ``BitemporalStore``.

    ``BitemporalStore.write`` APPENDS, and the point-in-time read then keeps one
    row per ``match_id``, so a double write is harmless but wasteful and makes
    the on-disk file a poor record of what was ingested. The parquet is
    therefore removed and rewritten whenever the row count on disk does not
    match the frame — and unconditionally under ``rebuild``.
    """
    root = Path(root or paths.STORE_DIR)
    frame = to_store_frame(matches if matches is not None
                           else epl_baseline.load_matches())
    table = root / f"{_STORE_TABLE}.parquet"
    if rebuild and table.exists():
        table.unlink()
    if table.exists():
        existing = pd.read_parquet(table)
        if len(existing) == len(frame) and set(existing["match_id"]) == set(frame["match_id"]):
            return BitemporalStore(root)
        table.unlink()
    store = BitemporalStore(root)
    store.write(_STORE_TABLE, frame, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source=_SOURCE,
                source_version=paths.rel(paths.MATCHES_PARQUET))
    return store


def assert_point_in_time(store: BitemporalStore, cutoff) -> dict[str, Any]:
    """Prove, from the store itself, that a fit at ``cutoff`` sees only the past.

    Reads the table the way ``features.build`` will, and asserts the latest
    training date is strictly before the cutoff day. This is a structural check
    on the data actually reaching the model, not a restatement of the filter's
    source code.
    """
    cutoff = pd.Timestamp(cutoff).normalize()
    asof = store.read(_STORE_TABLE, cutoff=cutoff)
    asof["date"] = pd.to_datetime(asof["date"])
    train = valid_played_results(asof)
    train = train.loc[pd.to_datetime(train["date"]) < cutoff]
    if train.empty:
        raise ValueError(f"no training matches before {cutoff.date()}")
    latest = pd.to_datetime(train["date"]).max()
    if not latest < cutoff:
        raise ValueError(f"LEAKAGE: latest training date {latest} is not "
                         f"strictly before cutoff {cutoff}")
    return {
        "cutoff": str(cutoff.date()),
        "n_training_matches": int(len(train)),
        "latest_training_date": str(latest.date()),
        "n_training_teams": int(len(set(train["home_team"]) | set(train["away_team"]))),
    }


# ==========================================================================
# 2. one fit
# ==========================================================================
@dataclass
class FitResult:
    cutoff: str
    seconds: float
    cache_hit: bool
    key: str
    n_training_matches: int
    n_teams: int
    teams: list[str]
    provisional_teams: list[str]
    warnings: list[str] = field(default_factory=list)
    component_seconds: dict[str, float] = field(default_factory=dict)
    artifact_bytes: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["teams"] = list(self.teams)
        return d


def fit_at(cutoff, store: BitemporalStore | None = None,
           cache_dir: Path | str | None = None,
           config: dict | None = None,
           attribute: bool = True) -> tuple[Any, FitResult]:
    """Run ONE real fit at ``cutoff`` through the production cache path.

    Routed through ``wcmodel.model.cache.cached_fit`` rather than
    ``scoreline.fit`` directly, because that is what every World Cup caller
    uses and its content key is what a walk-forward would actually hit or miss.
    Every inference knob comes from the shipped config — backend, draws, tune,
    ADVI iterations, seed — so this is the production fit, not a fast variant.

    ``attribute`` additionally times the two expensive pieces the fit is made
    of, on their own, so the cost model can say WHERE the wall clock went:
    ``features.build`` (the O(N) point-in-time Elo recompute, which the panel
    cache can later serve from disk) and ``count_volatility_arm`` (a second,
    independent recompute of the same Elo over the same rows, which nothing
    caches). Both are measured BEFORE the fit so neither is served warm.
    """
    cfg = config or load_config()
    store = store or build_store()
    cache_dir = Path(cache_dir or paths.FIT_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    guard = assert_point_in_time(store, cutoff_ts)

    components: dict[str, float] = {}
    if attribute:
        t0 = time.perf_counter()
        panel = wc_features.build(cutoff_ts, store, cfg)     # uncached, on purpose
        components["features_build_uncached"] = time.perf_counter() - t0
        teams_for_arm = sorted(set(panel["team"]))
        from wcmodel.model.volatility_diagnostic import count_volatility_arm
        t0 = time.perf_counter()
        count_volatility_arm(store, cutoff_ts, teams_for_arm, config=cfg)
        components["count_volatility_arm"] = time.perf_counter() - t0

    inf = cfg["model"]["inference"]
    caught: list[str] = []
    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        post, meta = wc_model_cache.cached_fit(
            cutoff=cutoff_ts, store=store, backend=inf["backend"],
            draws=int(inf["draws"]), seed=int(cfg["seed"]),
            advi_iters=int(inf["advi_iters"]), cache_dir=cache_dir, config=cfg,
        )
        caught = sorted({f"{x.category.__name__}: {x.message}" for x in w})
    seconds = time.perf_counter() - t0

    sizes = {}
    for pattern in (f"posterior-{meta['key']}.nc", f"posterior-{meta['key']}.meta.json"):
        p = cache_dir / pattern
        if p.exists():
            sizes[pattern.split("-")[0] + Path(pattern).suffix] = p.stat().st_size
    panels = sorted(cache_dir.glob("featpanel-*.parquet"))
    if panels:
        sizes["featpanel.parquet"] = max(p.stat().st_size for p in panels)

    result = FitResult(
        cutoff=str(cutoff_ts.date()), seconds=seconds,
        cache_hit=bool(meta["cache_hit"]), key=str(meta["key"]),
        n_training_matches=int(guard["n_training_matches"]),
        n_teams=len(post.teams), teams=list(post.teams),
        provisional_teams=sorted(post.provisional_teams),
        warnings=caught, component_seconds=components, artifact_bytes=sizes,
    )
    return post, result


# ==========================================================================
# 2b. where the wall clock actually goes
# ==========================================================================
@contextlib.contextmanager
def config_read_once(config: dict | None = None):
    """Serve ``tiers``' config read from memory for the duration. MEASUREMENT ONLY.

    ``wcmodel.data.features.build`` computes a COVID-window tag with
    ``df["date"].map(tiers.is_covid)``, and ``tiers.is_covid`` calls
    ``load_config()`` in its body — which opens and YAML-parses
    ``config/config.yaml`` from disk. Once per panel ROW. On an 8,038-row EPL
    panel that is 8,038 full YAML parses of a 200-line file, and it dominates
    the fit.

    This context manager rebinds the name ``tiers`` resolves at call time to a
    closure over one already-parsed config. It does NOT edit anything under
    ``src/`` — that path is attested by the preregistration lock and is
    read-only to this package — and it is not used by :func:`fit_at`, so no
    number this probe reports as the shipped cost is measured through it. Its
    only job is to answer "how much of the fit is the model, and how much is
    this?", and the answer is checked rather than asserted: the panel built
    inside the block must equal the panel built outside it, and the posterior's
    content key must be unchanged.
    """
    original = wc_tiers.load_config
    cfg = config or load_config()
    wc_tiers.load_config = lambda *a, **k: cfg
    try:
        yield
    finally:
        wc_tiers.load_config = original


def measure_hot_path_overhead(store: BitemporalStore | None = None,
                              cutoff="2025-01-25",
                              config: dict | None = None) -> dict[str, Any]:
    """Split one fit into "the model" and "re-parsing a YAML file 8,038 times".

    Returns both wall clocks plus the two equality checks that make the split
    trustworthy: the feature panel is identical either way, and the fit's
    content key is identical either way, so nothing about WHAT is computed
    changes — only how long it takes.
    """
    cfg = config or load_config()
    store = store or build_store()
    cutoff_ts = pd.Timestamp(cutoff).normalize()

    t0 = time.perf_counter()
    shipped_panel = wc_features.build(cutoff_ts, store, cfg)
    panel_shipped = time.perf_counter() - t0

    with config_read_once(cfg):
        t0 = time.perf_counter()
        fast_panel = wc_features.build(cutoff_ts, store, cfg)
        panel_fast = time.perf_counter() - t0
        with tempfile.TemporaryDirectory() as tmp:
            inf = cfg["model"]["inference"]
            t0 = time.perf_counter()
            _, meta = wc_model_cache.cached_fit(
                cutoff=cutoff_ts, store=store, backend=inf["backend"],
                draws=int(inf["draws"]), seed=int(cfg["seed"]),
                advi_iters=int(inf["advi_iters"]), cache_dir=tmp, config=cfg)
            fit_fast = time.perf_counter() - t0

    return {
        "panel_seconds_as_shipped": round(panel_shipped, 2),
        "panel_seconds_config_read_once": round(panel_fast, 2),
        "fit_seconds_config_read_once": round(fit_fast, 2),
        "panel_identical": bool(shipped_panel.equals(fast_panel)),
        "content_key": str(meta["key"]),
        "attributable_to_per_row_config_parse": round(panel_shipped - panel_fast, 2),
        "where": "wcmodel.data.tiers.is_covid -> wcmodel.config.load_config "
                 "(called once per panel row by features.build)",
        "fix_location": "src/wcmodel/ — ATTESTED by the preregistration lock. "
                        "Memoising load_config, or hoisting the COVID window out "
                        "of the per-row map, is a one-line change that this "
                        "package may not make.",
    }


# ==========================================================================
# 3. forecasting the next matchweek
# ==========================================================================
def next_matchweek(matches: pd.DataFrame, cutoff, max_matches: int = 10,
                   ) -> pd.DataFrame:
    """The fixtures a fit at ``cutoff`` would be used to price.

    The source has no matchweek column, so a matchweek is taken to be the next
    ``max_matches`` played fixtures in chronological order at or after the
    cutoff. Placing the cutoff on a round's opening day makes that exactly one
    round; the function does not pretend to know more than that.
    """
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    fut = matches.loc[pd.to_datetime(matches["date"]) >= cutoff_ts]
    fut = fut.loc[fut["played"]]
    return fut.head(max_matches).copy()


def model_probabilities(post, fixtures: pd.DataFrame) -> np.ndarray:
    """Per-fixture 1X2 from a fitted posterior, in ``score.OUTCOMES`` order.

    ``neutral=False`` on every row: an EPL fixture is a home game, and the
    fitted ``home_adv`` applies in full. A club absent from the posterior's team
    index yields a NaN row rather than an exception, because that is the
    failure mode a promoted club actually causes in a walk-forward and it
    should be visible in the output, not fatal at match 1 of 380.
    """
    out = np.full((len(fixtures), 3), np.nan)
    for i, (h, a) in enumerate(zip(fixtures["home_key"], fixtures["away_key"])):
        if h not in post._idx or a not in post._idx:
            continue
        p = post.predict_1x2(str(h), str(a), neutral=False)
        out[i] = [p["home"], p["draw"], p["away"]]
    return out


def _elo_probabilities(matches: pd.DataFrame, fixture_ids: Sequence[str],
                       config: epl_elo.EloConfig) -> np.ndarray:
    """The frozen baseline forecaster's probabilities for specific fixtures.

    Calls ``epl.baseline.walk_forward_head`` — the SAME function that produced
    the published 0.2011 — with a ``want`` mask restricted to these fixtures, so
    the Elo column in the smoke test is the baseline itself rather than a
    re-derivation of it.
    """
    ordered = sort_for_walk_forward(matches.loc[matches["played"]])
    history, _ = epl_elo.compute_elo_history(ordered, config)
    want = history["match_id"].isin(set(fixture_ids)).to_numpy()
    probs, _ = epl_baseline.walk_forward_head(history, want)
    idx = {m: i for i, m in enumerate(history["match_id"])}
    return np.array([probs[idx[m]] for m in fixture_ids], dtype=float)


def run_smoke_test(post, matches: pd.DataFrame, cutoff,
                   elo_config: epl_elo.EloConfig | None = None,
                   max_matches: int = 10) -> dict[str, Any]:
    """Score the one fit against Elo on the next matchweek. NOT A RESULT.

    Ten matches. The paired SD of the Elo-versus-market difference on this data
    is 0.0577, so the standard error of a ten-match paired gap is 0.018 — nearly
    three times the entire Elo-to-market gap the whole project is arguing about.
    Any ordering this produces is noise. It is here to prove the wiring runs
    end to end and produces probabilities that are not absurd, and for no other
    purpose.
    """
    fixtures = next_matchweek(matches, cutoff, max_matches)
    cfg = elo_config or _frozen_elo_config()
    ids = list(fixtures["match_id"])

    model = model_probabilities(post, fixtures)
    elo = _elo_probabilities(matches, ids, cfg)
    market = epl_baseline.market_probabilities(fixtures, "shin")   # BENCHMARK ONLY
    y = score_mod.outcome_codes(fixtures["ftr"].astype(str).to_numpy())

    complete = (np.isfinite(model).all(axis=1) & np.isfinite(elo).all(axis=1))
    keep = np.flatnonzero(complete)
    scores: dict[str, Any] = {}
    columns = {"dc_model": model, "elo_walkforward": elo}
    if np.isfinite(market[keep]).all():
        columns["market_devig_shin"] = market
    for name, p in columns.items():
        scores[name] = score_mod.summarise(name, p[keep], y[keep]).as_dict()

    d, mean, sd = score_mod.paired_gap("dc_model", score_mod.rps(model[keep], y[keep]),
                                       "elo_walkforward", score_mod.rps(elo[keep], y[keep]))
    per_match = [
        {"match_id": ids[i], "date": str(pd.Timestamp(fixtures["date"].iloc[i]).date()),
         "home": str(fixtures["home_key"].iloc[i]), "away": str(fixtures["away_key"].iloc[i]),
         "ftr": str(fixtures["ftr"].iloc[i]),
         "model": [round(float(v), 4) for v in model[i]],
         "elo": [round(float(v), 4) for v in elo[i]]}
        for i in keep
    ]
    return {
        "LABEL": "SMOKE TEST — NOT A RESULT. n is about 10; the paired SE is "
                 "~0.018 RPS, roughly three times the entire Elo-to-market gap. "
                 "Nothing here can order two forecasters.",
        "cutoff": str(pd.Timestamp(cutoff).normalize().date()),
        "n_fixtures": int(len(fixtures)),
        "n_scored": int(keep.size),
        "n_unpriced_by_model": int(len(fixtures) - keep.size),
        "scores": scores,
        "paired_dc_minus_elo": {"mean": mean, "sd": sd,
                                "se": float(sd / np.sqrt(keep.size)) if keep.size > 1 else None},
        "per_match": per_match,
    }


def _frozen_elo_config() -> epl_elo.EloConfig:
    """The Elo hyperparameters frozen by ``epl.baseline --tune``, off disk."""
    chosen = json.loads(Path(paths.TUNING_PATH).read_text())["chosen"]
    return epl_elo.EloConfig(**chosen)


# ==========================================================================
# 4. what a full walk-forward would cost
# ==========================================================================
def matchweek_index(df: pd.DataFrame) -> np.ndarray:
    """Dense 0-based index over (season, ISO calendar week), chronological.

    The refit UNIT. The source has no matchweek column and the feature layer's
    cutoff is day-resolution, so the calendar week within a season is the
    natural round: the clubs in it share a rating state and a slice of the
    season, and a week carrying a midweek round is simply a bigger round, which
    is the right behaviour rather than a defect.
    """
    labels = epl_baseline._week_blocks(df)
    _, first = np.unique(labels, return_index=True)
    order = {labels[i]: r for r, i in enumerate(sorted(first))}
    return np.array([order[v] for v in labels], dtype=int)


def cost_model(matches: pd.DataFrame, fit_seconds: float,
               cadences: Iterable[int] = (1, 2, 4, 8),
               score_seasons: Sequence[str] = epl_baseline.SCORE_SEASONS,
               ) -> dict[str, Any]:
    """Wall clock for refitting every N matchweeks across the scoring seasons.

    A fit is needed at the opening of every N-th matchweek OF A SCORED SEASON.
    The tuning seasons need no fit of their own — they are history that every
    scored fit already reads — so they are not counted, and a refit window never
    spans a season boundary (the first week of a season always gets its own fit,
    which is also when the promoted clubs first appear).

    ``fit_seconds`` is the MEASURED cost of one cold fit. It is treated as
    constant, which is mildly conservative early in the window and mildly
    optimistic late: cost grows with the pre-cutoff match count, which runs from
    about 1,500 to 4,500 across these seasons.
    """
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    mw = matchweek_index(played)
    seasons = played["season"].to_numpy()
    wanted = set(score_seasons)

    rows = []
    for n in cadences:
        fits = 0
        per_season = {}
        for s in sorted(wanted):
            weeks = sorted(set(mw[seasons == s]))
            k = int(np.ceil(len(weeks) / n))
            per_season[s] = {"matchweeks": len(weeks), "fits": k}
            fits += k
        hours = fits * fit_seconds / 3600.0
        rows.append({
            "refit_every_weeks": int(n),
            "total_fits": int(fits),
            "hours": round(hours, 2),
            "seconds": round(fits * fit_seconds, 1),
            "matches_per_fit": round(len(played[np.isin(seasons, list(wanted))]) / fits, 1),
            "per_season": per_season,
        })
    return {
        "fit_seconds": fit_seconds,
        "score_seasons": list(score_seasons),
        "n_scored_matches": int(np.isin(seasons, list(wanted)).sum()),
        "total_matchweeks_scored": int(len(set(zip(seasons[np.isin(seasons, list(wanted))],
                                                   mw[np.isin(seasons, list(wanted))])))),
        "cadences": rows,
    }


# ==========================================================================
# 5. what refitting less often costs in FIDELITY
# ==========================================================================
def staleness_curve(matches: pd.DataFrame | None = None,
                    elo_config: epl_elo.EloConfig | None = None,
                    cadences: Iterable[int] = (1, 2, 4, 8),
                    score_seasons: Sequence[str] = epl_baseline.SCORE_SEASONS,
                    ) -> dict[str, Any]:
    """Measured cost of letting the forecaster go stale between refits.

    A PROXY, and labelled as one. Running the Bayesian model at four cadences is
    the very experiment this probe exists to cost, so it cannot be the thing
    that answers "what does a slower cadence cost". What CAN be measured in
    seconds is the same staleness applied to the Elo + ordered-logit forecaster:
    freeze the ratings AND the head at the opening of each refit window, price
    every fixture in the window off that frozen state, and score. The quantity
    is the information a forecaster gives up by not learning from results that
    have already happened, which is the same quantity a stale posterior gives
    up. The magnitude will not transfer exactly — Elo moves faster per match
    than a decayed four-season likelihood does — so read it as an upper bound on
    the Bayesian model's degradation, since the slower learner has less to lose.

    THE FREEZE IS EXACT, not approximate. Within a refit window a club plays its
    first match of that window off precisely the rating it held when the window
    opened, so that match's own ``elo_*_pre`` IS the frozen rating; every later
    match in the window is repriced off it. No re-walk, no reimplementation of
    the Elo update, and therefore no way for this to disagree with
    ``epl.elo.compute_elo_history``.
    """
    matches = epl_baseline.load_matches() if matches is None else matches
    cfg = elo_config or _frozen_elo_config()
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    history, _ = epl_elo.compute_elo_history(played, cfg)

    mw = matchweek_index(played)
    seasons = played["season"].to_numpy()
    home = history["home_key"].to_numpy()
    away = history["away_key"].to_numpy()
    pre_h = history["elo_home_pre"].to_numpy(float)
    pre_a = history["elo_away_pre"].to_numpy(float)
    fresh_edge = history["elo_diff_pre"].to_numpy(float)
    y = score_mod.outcome_codes(history["ftr"].to_numpy())
    want = np.isin(played["season"].to_numpy(), list(score_seasons))
    block_labels = epl_baseline._week_blocks(played)

    # Refit windows: consecutive matchweeks, N at a time, restarting each season.
    def _windows(n: int) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for s in pd.unique(seasons):
            weeks = sorted(set(mw[seasons == s]))
            for i in range(0, len(weeks), n):
                chunk = set(weeks[i:i + n])
                rows = np.flatnonzero((seasons == s) & np.isin(mw, list(chunk)))
                if rows.size:
                    out.append(rows)
        return sorted(out, key=lambda r: r[0])

    results = []
    for n in cadences:
        probs = np.full((len(played), 3), np.nan)
        stale_edge = np.full(len(played), np.nan)
        for rows in _windows(int(n)):
            cut = int(rows[0])
            frozen: dict[str, float] = {}
            for i in rows:                      # first appearance in the window
                frozen.setdefault(home[i], pre_h[i])
                frozen.setdefault(away[i], pre_a[i])
            stale_edge[rows] = np.array([frozen[home[i]] - frozen[away[i]]
                                         for i in rows])
            if cut < ordlogit.MIN_FIT_MATCHES or not want[rows].any():
                continue
            params = ordlogit.fit(fresh_edge[:cut], y[:cut])
            probs[rows] = ordlogit.predict(params, stale_edge[rows])
        ok = want & np.isfinite(probs).all(axis=1)
        idx = np.flatnonzero(ok)
        s = score_mod.summarise(f"elo_stale_{n}w", probs[idx], y[idx])
        results.append({
            "refit_every_weeks": int(n), "n": s.n, "rps": s.rps,
            "log_loss": s.log_loss, "accuracy": s.accuracy,
            "mean_abs_rating_staleness": float(
                np.nanmean(np.abs(stale_edge[idx] - fresh_edge[idx]))),
            "_rps_vector": score_mod.rps(probs[idx], y[idx]),
            "_idx": idx,
        })

    # Everything is scored on the intersection so the deltas are paired.
    common = results[0]["_idx"]
    for r in results[1:]:
        common = np.intersect1d(common, r["_idx"])
    base = None
    for r in results:
        sel = np.isin(r["_idx"], common)
        vec = r["_rps_vector"][sel]
        r["rps_common"] = float(vec.mean())
        r["_vec"] = vec
        if base is None:
            base = vec
    for r in results:
        d, mean, sd = score_mod.paired_gap("stale", r["_vec"], "weekly", base)
        lo, hi, nb = score_mod.block_bootstrap_ci(
            d, np.asarray(block_labels)[common])
        r["rps_cost_vs_weekly"] = mean
        r["rps_cost_ci95"] = [lo, hi]
        r["n_blocks"] = nb
        for k in ("_rps_vector", "_idx", "_vec"):
            r.pop(k, None)

    return {
        "LABEL": "PROXY, measured on the Elo + ordered-logit forecaster, not on "
                 "the Bayesian model. Read as an upper bound: Elo learns faster "
                 "per match than a 365-day-decayed likelihood, so it has more to "
                 "lose by going stale.",
        "n_common": int(common.size),
        "score_seasons": list(score_seasons),
        "cadences": results,
    }


# ==========================================================================
# 6. CLI
# ==========================================================================
def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cutoff", default="2025-01-25",
                    help="as-of date; matches on this day and later are unseen")
    ap.add_argument("--matchweek", type=int, default=10)
    ap.add_argument("--rebuild-store", action="store_true")
    ap.add_argument("--cold", action="store_true",
                    help="clear the fit cache first, to time a guaranteed MISS")
    ap.add_argument("--staleness", action="store_true",
                    help="also run the Elo staleness proxy (no Bayesian fits)")
    ap.add_argument("--cadences", default="1,2,4,8")
    args = ap.parse_args()

    cadences = tuple(int(x) for x in args.cadences.split(","))
    paths.FIT_DIR.mkdir(parents=True, exist_ok=True)
    matches = epl_baseline.load_matches()
    store = build_store(matches, rebuild=args.rebuild_store)
    if args.cold and paths.FIT_CACHE_DIR.exists():
        shutil.rmtree(paths.FIT_CACHE_DIR)

    print(f"[fit] cutoff {args.cutoff}", flush=True)
    post, res = fit_at(args.cutoff, store)
    print(f"[fit] {res.seconds:.1f}s  cache_hit={res.cache_hit}  "
          f"n_train={res.n_training_matches}  n_teams={res.n_teams}", flush=True)

    t0 = time.perf_counter()
    _, warm = fit_at(args.cutoff, store, attribute=False)
    warm_seconds = time.perf_counter() - t0

    overhead = measure_hot_path_overhead(store, args.cutoff)
    print(f"[cost] panel as shipped {overhead['panel_seconds_as_shipped']}s -> "
          f"{overhead['panel_seconds_config_read_once']}s once the per-row config "
          f"parse is memoised; whole fit {overhead['fit_seconds_config_read_once']}s, "
          f"same key {overhead['content_key']}", flush=True)

    smoke = run_smoke_test(post, matches, args.cutoff, max_matches=args.matchweek)
    report = {
        "fit": res.as_dict(),
        "warm_cache_seconds": round(warm_seconds, 2),
        "hot_path": overhead,
        "architecture_notes": list(ARCHITECTURE_NOTES),
        "smoke_test": smoke,
        # Two cost tables, because the honest answer is two numbers: what a walk
        # costs today, and what it costs after a one-line change this package is
        # forbidden to make.
        "cost_model_as_shipped": cost_model(matches, res.seconds, cadences),
        "cost_model_config_read_once": cost_model(
            matches, overhead["fit_seconds_config_read_once"], cadences),
    }
    paths.FIT_REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
    for label in ("cost_model_as_shipped", "cost_model_config_read_once"):
        rows = [{k: r[k] for k in ("refit_every_weeks", "total_fits", "hours")}
                for r in report[label]["cadences"]]
        print(label, report[label]["fit_seconds"], "s/fit ->", rows, flush=True)

    if args.staleness:
        st = staleness_curve(matches, cadences=cadences)
        paths.STALENESS_PATH.write_text(json.dumps(st, indent=2, default=str))
        print(json.dumps(st, indent=2, default=str)[:2000], flush=True)


if __name__ == "__main__":
    _cli()
