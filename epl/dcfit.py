"""One Dixon-Coles fit, with a league-shaped anchor and no unpriceable fixture.

This module holds FIX 3 (cold start) and the fit orchestration that carries
FIXES 1 AND 2 (:mod:`epl.anchor`) into ``wcmodel``'s model.

WHAT IS IMPORTED, UNCHANGED, FROM ``src/wcmodel``: the leakage-safe feature
panel, the match panel, the covariate transforms, the design, the
provisional-widening weights, the Dixon-Coles likelihood, the priors, the ADVI
backend, and the ``Posterior``. The architecture under test is theirs. What
lives here is the two lines the international model has no answer for on a
domestic league — which rating anchors the prior, and what happens to a club
that has never played in the league before — plus the plumbing that connects
them. Nothing under ``src/`` or ``scripts/`` is written.

WHY NOT CALL ``scoreline.fit`` DIRECTLY. ``fit`` builds the strength anchor
internally from the panel's ``elo_pre`` column
(``wcmodel.model.strength.team_elo_z``), and that column is ``wcmodel``'s
international Elo — the thing Fixes 1 and 2 exist to replace. There is no
parameter that redirects it. The alternative to this thirty-line orchestration
would be monkey-patching ``team_elo_z`` at run time, which would (a) hide the
substitution from a reader of the code and (b) leave ``wcmodel``'s posterior
cache unable to tell two anchors apart, since its key hashes the config and the
match panel but not the ratings. An explicit call sequence is auditable; a
patched import is not.

FIX 3 — THE COLD START, AND WHY DROPPING THE FIXTURE IS NOT AN OPTION
--------------------------------------------------------------------
A club promoted into the league has no pre-cutoff match, so it is absent from
the feature panel, absent from the design's team index, and absent from
``Posterior._idx``. ``predict_1x2`` then raises ``KeyError`` — verified on this
archive at 2024/25 Ipswich, 2023/24 Luton and 2021/22 Brentford, one of ten
opening fixtures each time. Six of the six scoring seasons open with exactly
one such club.

Dropping those fixtures would be the easy fix and it would invalidate the
result. The dropped matches are not a random sample: they are the matches
involving the club the model knows least about, which are the matches it would
price worst. Removing them biases the model's score downward — that is, in its
own favour — against a market benchmark that prices them fine. A comparison run
on "every match except the hard ones" answers a question nobody asked.

Nor can the club be seeded at the league mean, which is what ``wcmodel`` does
today (``initial_rating``, and ``team_elo_z`` maps an absent club to z = 0, the
no-information shrink-to-mean). A promoted club is not an average Premier
League club; it is, on this archive's evidence, close to the relegation zone.

WHAT IS CHOSEN INSTEAD: the club is priced from the model's OWN hierarchical
prior, evaluated at the fitted hyperparameters and anchored at the club's
promoted seed. Concretely, for each posterior draw ``s``::

    att_new[s] = k_att * z_new + sigma_att[s] * eps
    def_new[s] = k_def * z_new + sigma_def[s] * eps'

which is exactly the distribution ``wcmodel.model.scoreline._priors`` assigns a
team before it sees that team's matches — ``att_raw ~ Normal(k_att * elo_z,
sigma_att)`` — with ``sigma`` carrying the posterior's own estimate of how far
apart clubs in this league are, and ``z_new`` the promoted seed from Fix 2
placed on the fitted teams' z-scale. The centering ``wcmodel`` applies (``att =
att_raw - mean(att_raw)``) drops out identically rather than approximately: the
anchor is z-scored over the fitted teams, so its mean over them is zero, and
the estimator of the centering constant is ``k * mean(z) = 0``.

Three properties make this the defensible choice rather than a convenient one.
It introduces NO parameter that was not already fitted — ``k_att``, ``k_def``,
``sigma_att`` and ``sigma_def`` all come from the model. It is what the model
itself says about an exchangeable club it has no data on, so it is the
architecture's answer, not an answer bolted onto it. And it is strictly WIDER
than a point estimate: the club is additionally flagged provisional, so the
predict-time mechanism-(c) widening the package already implements applies to
its fixtures, which is the honest response to knowing nothing about a club
beyond where it was seeded.

THE HONEST LIMITATION, stated here rather than discovered later: a prior draw
is not a posterior. The model has no more information about a promoted club
than its Elo seed, so on these fixtures the DC forecast is a smeared version of
the Elo forecast and should not be expected to beat it. The point of Fix 3 is
that every fixture gets a number, not that the number is good.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from epl.anchor import Anchor, AnchorState

# --- READ-ONLY imports from the attested package ---------------------------
from wcmodel.data import features as wc_features
from wcmodel.model.panel import build_design, to_match_panel
from wcmodel.model.posterior import Posterior
from wcmodel.model.scoreline import _build_covariates, build_model
from wcmodel.model.inference import sample
from wcmodel.model.volatility_diagnostic import count_volatility_arm
from wcmodel.model.widening import likelihood_weight

__all__ = ["ColdStartPosterior", "cold_start_clubs", "fit_epl", "EplFit"]


# ==========================================================================
# FIX 3 — the cold start
# ==========================================================================
class ColdStartPosterior(Posterior):
    """A fitted posterior extended with clubs the fit never saw.

    Every extension row is a draw from the model's own prior at the fitted
    hyperparameters (see the module docstring). The base posterior is not
    mutated and not copied — its ``idata`` is read through the same ``_post``
    accessor the production predict path uses, so a fitted club's forecast is
    bit-identical whether or not any cold-start club was added.
    """

    def __init__(self, base: Posterior, extra: dict[str, np.ndarray]):
        self.idata = base.idata
        self.likelihood = base.likelihood
        self.covariate_transforms = dict(base.covariate_transforms)
        self._cfg = base._cfg
        self._extra = {k: {n: np.asarray(v) for n, v in d.items()}
                       for k, d in extra.items()}
        cold = tuple(self._extra)
        self.teams = list(base.teams) + list(cold)
        self._idx = {t: i for i, t in enumerate(self.teams)}
        # A cold-start club IS low-information by definition, so it takes the
        # same predict-time widening the package already applies to a
        # provisional team. This is the model's existing uncertainty machinery,
        # not a new one.
        self.provisional_teams = set(base.provisional_teams) | set(cold)
        self.cold_start_teams = set(cold)
        self._base_n = len(base.teams)

    def _post(self, name):
        arr = super()._post(name)
        if not self._extra or name not in ("att", "def"):
            return arr
        rows = [self._extra[t][name] for t in self.teams[self._base_n:]]
        return np.concatenate([arr, np.stack(rows, axis=0)], axis=0)


def _prior_draws(state: AnchorState, club: str, cfg: dict, post: Posterior,
                 seed: int) -> dict[str, np.ndarray]:
    """One club's ``att`` / ``def`` draws from the model's prior. See module doc."""
    strength = cfg["model"].get("strength_prior") or {}
    z = state.z(club) if strength.get("enabled") else 0.0
    k_att = float(strength.get("k_att", 0.0)) if strength.get("enabled") else 0.0
    k_def = float(strength.get("k_def", 0.0)) if strength.get("enabled") else 0.0
    sigma_att = np.asarray(post._post("sigma_att"), dtype=float).ravel()
    sigma_def = np.asarray(post._post("sigma_def"), dtype=float).ravel()
    # Deterministic per (seed, club): the same fit and the same club always
    # produce the same draws, so a re-run reproduces the forecast exactly.
    rng = np.random.default_rng(
        (int(seed) * 1_000_003 + zlib.crc32(club.encode())) % (2 ** 63))
    return {
        "att": k_att * z + sigma_att * rng.standard_normal(sigma_att.size),
        "def": k_def * z + sigma_def * rng.standard_normal(sigma_def.size),
        "_z": np.array([z]),
    }


def cold_start_clubs(matches: pd.DataFrame, cutoff, teams: Sequence[str],
                     ) -> list[str]:
    """Clubs in the cutoff's season that the fit at ``cutoff`` has never seen.

    "Never seen" is a property of the ARCHIVE, not of football: a club can be
    absent because it is genuinely new to the top flight (Bournemouth 2015/16)
    or because its previous spell predates 2014/15 (Norwich 2015/16). Both are
    handled the same way and for the same reason — the model has no matches for
    it either way — but the distinction is why no separate "debutant" parameter
    is carried; see ``epl.elo.EloConfig.debut_offset``.
    """
    cutoff = pd.Timestamp(cutoff).normalize()
    played = matches.loc[matches["played"]]
    dates = pd.to_datetime(played["date"])
    future = played.loc[dates >= cutoff]
    if future.empty:
        return []
    season = future["season"].iloc[0]
    in_season = played.loc[played["season"] == season]
    clubs = set(in_season["home_key"]) | set(in_season["away_key"])
    return sorted(clubs - set(teams))


# ==========================================================================
# the fit
# ==========================================================================
@dataclass
class EplFit:
    """What one fit did, in numbers a report can quote."""

    cutoff: str
    seconds: float
    n_training_matches: int
    n_teams: int
    teams: list[str]
    cold_start_teams: list[str]
    cold_start_z: dict[str, float]
    provisional_teams: list[str]
    anchor_spec: str
    elo_z: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def fit_epl(cutoff, store, anchor: Anchor, cfg: dict,
            matches: pd.DataFrame | None = None,
            cold_start: Iterable[str] | None = None,
            feature_cache_dir=None) -> tuple[ColdStartPosterior, EplFit]:
    """``wcmodel``'s Dixon-Coles fit, anchored on this package's Elo.

    Step for step this is ``wcmodel.model.scoreline.fit`` — the same panel, the
    same covariate transforms, the same design, the same widening weights, the
    same model builder, the same sampler, the same provisional arm, the same
    ``Posterior`` — with exactly two substitutions, both of them the point of
    the exercise:

    1. ``elo_z`` comes from :class:`epl.anchor.Anchor` (Fixes 1 and 2) instead
       of from ``team_elo_z`` on the panel's international-Elo column.
    2. The returned posterior is extended so that a club with no pre-cutoff
       match is priceable (Fix 3) instead of raising ``KeyError``.

    Everything else — including which matches are visible, which is the only
    thing that could leak — is ``wcmodel``'s code and ``wcmodel``'s config.
    """
    import time

    if cfg["model"]["covariates"]["enabled"]:
        raise NotImplementedError(
            "covariates are enabled in the config; this probe reproduces the "
            "published World Cup baseline, which has none, and the covariate "
            "path is not wired for EPL (rest_days/travel/altitude are absent). "
            "Enabling them would make this a different architecture.")

    t0 = time.perf_counter()
    inf = cfg["model"]["inference"]
    likelihood = cfg["model"]["likelihood"]

    feats = wc_features.build_cached(cutoff, store, cfg,
                                     cache_dir=feature_cache_dir)
    mp = to_match_panel(feats)
    cov, cov_mask, cov_transforms = _build_covariates(
        mp, cfg["model"]["covariates"])
    teams = sorted(set(mp["home_team"]) | set(mp["away_team"]))
    state = anchor.state(cutoff, teams)
    elo_z = state.elo_z(teams)

    d = build_design(mp, cov=cov, cov_mask=cov_mask, elo_z=elo_z)
    w = likelihood_weight(d, mechanism=cfg["model"]["widening"]["mechanism"],
                          strength=cfg["model"]["widening"]["strength"])
    model = build_model(d, likelihood=likelihood, weight=w, config=cfg)
    idata = sample(model, backend=inf["backend"], draws=int(inf["draws"]),
                   tune=int(inf["tune"]), seed=int(cfg["seed"]),
                   advi_iters=int(inf["advi_iters"]))
    arm = count_volatility_arm(store, cutoff, d.teams, config=cfg)
    prov = set(arm.loc[arm["volatility_flag"] | arm["few_games_flag"], "team"])
    base = Posterior(idata, d.teams, likelihood, provisional_teams=prov,
                     config=cfg, covariate_transforms=cov_transforms)

    cold = (list(cold_start) if cold_start is not None
            else cold_start_clubs(matches, cutoff, d.teams)
            if matches is not None else [])
    extra = {c: _prior_draws(state, c, cfg, base, int(cfg["seed"]))
             for c in cold}
    post = ColdStartPosterior(base, extra)

    return post, EplFit(
        cutoff=str(pd.Timestamp(cutoff).normalize().date()),
        seconds=round(time.perf_counter() - t0, 2),
        n_training_matches=int(len(mp)), n_teams=len(d.teams),
        teams=list(d.teams), cold_start_teams=list(cold),
        cold_start_z={c: float(extra[c]["_z"][0]) for c in cold},
        provisional_teams=sorted(post.provisional_teams),
        anchor_spec=str(cfg["elo"].get("epl_anchor_spec", "")),
        elo_z={t: float(z) for t, z in zip(teams, elo_z)},
    )


# ==========================================================================
# one fit, end to end — the evidence behind the prereg's Fix-3 claim
# ==========================================================================
def _cli() -> None:
    """Fit at a season opener and price every fixture of that matchweek.

    Defaults to a TUNING-window opener. Fix 3's failure mode is identical in
    either window — a club with no pre-cutoff match is absent from the team
    index — so there is no reason to demonstrate it on the scoring window, and
    every reason not to.
    """
    import argparse
    import json

    from epl import baseline, fit as epl_fit, freeze, paths, score as score_mod
    from epl import windows as epl_windows

    ap = argparse.ArgumentParser(description=_cli.__doc__.splitlines()[0])
    ap.add_argument("--cutoff", default="2016-08-13",
                    help="a season opener; default 2016/17 (Middlesbrough is "
                         "the cold-start club)")
    ap.add_argument("--fixtures", type=int, default=10)
    args = ap.parse_args()

    matches = baseline.load_matches()
    season = matches.loc[pd.to_datetime(matches["date"])
                         >= pd.Timestamp(args.cutoff), "season"].iloc[0]
    if season in epl_windows.SCORE_SEASONS:
        raise SystemExit(
            f"refusing to run a demonstration fit in scoring season {season}; "
            "the fix behaves identically in the tuning window, which is where "
            "it should be shown")

    cfg = freeze.frozen_wcmodel_config()
    anchor = Anchor(matches, freeze.frozen_elo_config())
    store = epl_fit.build_store(matches)
    fixtures = epl_fit.next_matchweek(matches, args.cutoff, args.fixtures)

    post, res = fit_epl(args.cutoff, store, anchor, cfg, matches=matches,
                        feature_cache_dir=paths.FIT_CACHE_DIR)
    probs = np.array([
        [np.nan] * 3 if (h not in post._idx or a not in post._idx) else
        [post.predict_1x2(str(h), str(a))[k] for k in score_mod.OUTCOMES]
        for h, a in zip(fixtures["home_key"], fixtures["away_key"])])

    unpriceable_before = sum(
        1 for h, a in zip(fixtures["home_key"], fixtures["away_key"])
        if h in post.cold_start_teams or a in post.cold_start_teams)
    out = {
        "fit": res.as_dict(),
        "n_fixtures": int(len(fixtures)),
        "n_priced": int(np.isfinite(probs).all(axis=1).sum()),
        "n_that_would_raise_KeyError_without_fix_3": unpriceable_before,
        "fixtures": [
            {"home": str(h), "away": str(a), "ftr": str(f),
             "p": [round(float(v), 4) for v in row],
             "cold_start": bool(h in post.cold_start_teams
                                or a in post.cold_start_teams)}
            for h, a, f, row in zip(fixtures["home_key"], fixtures["away_key"],
                                    fixtures["ftr"], probs)],
    }
    out["fit"].pop("elo_z", None)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    _cli()
