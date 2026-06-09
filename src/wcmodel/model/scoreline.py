"""ScorelineModel interface + the two PyMC likelihoods.

Hierarchical attack/defense with SOFT sum-to-zero centering (att = att_raw -
mean(att_raw)); baseline mu; home_adv applied only on non-neutral matches; the
likelihood is TIME-DECAY-WEIGHTED via a Potential (weight = design.weight, which
carries the Phase-1 decay_weight). This file is mechanism-AGNOSTIC: it consumes
whatever `weight` array it is given. Widening is applied in a LATER task —
mechanism (a) (likelihood down-weight) would multiply into this weight, while the
Phase-2 default mechanism (c) (predictive-variance inflation) leaves weight =
decay only and acts at predict time. Elo is the att/def prior ANCHOR when
``model.strength_prior.enabled`` (att/def prior mean = k·elo_z, the z-scored
point-in-time Elo strength threaded through ``DesignData.elo_z``); when DISABLED
(the default) Elo is NOT used here and the model learns attack/defense from goals
+ team indices + the decay weight only — the prior mean is the scalar 0.0 exactly
as before (byte-identical off path).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pymc as pm
import pytensor.tensor as pt

from wcmodel.config import load_config
from wcmodel.data import features
from wcmodel.model.covariates import CovariateTransform
from wcmodel.model.inference import sample
from wcmodel.model.likelihoods import bp_loglik_pt, dc_loglik_pt
from wcmodel.model.panel import DesignData, build_design, to_match_panel
from wcmodel.model.posterior import Posterior
from wcmodel.model.volatility_diagnostic import count_volatility_arm
from wcmodel.model.widening import likelihood_weight


# Which side(s) a covariate modifies. A per-team covariate's array (d.cov[name])
# is the HOME team's value for that feature; the AWAY team's own value for the
# same feature is supplied as "<name>__away" in d.cov (assembled upstream from
# the panel's home/away rows). Per-match covariates use a single array applied to
# both rates. A name absent from BOTH sets is ignored (no offset) — adding a new
# covariate requires classifying it here, so it can never silently no-op.
_PER_TEAM_COVS = {"rest_days", "travel_km"}
_PER_MATCH_COVS = {"altitude_m"}


def _build_covariates(mp, p_cov: dict):
    """Assemble the leakage-safe covariate transforms + cov/cov_mask design arrays
    from the < cutoff TRAINING panel ``mp``.

    For each enabled covariate present in the panel, ONE CovariateTransform is fit
    on the HOME-side training column (``mp[name]``) and then applied to BOTH sides:
    the home column -> cov[name], and (for a per-team covariate) the away team's own
    column ``mp[f"{name}__away"]`` -> cov[f"{name}__away"], via the SAME fitted
    transform (home + away share one standardization). The transform is fit on the
    SAME rows the model trains on, so it can never see past the cutoff
    (leakage-safe). A per-match covariate has no ``__away`` column (identical on both
    rows), so only the single array is produced.

    Returns ``(cov, cov_mask, transforms)``: the per-name standardized arrays, their
    masks, and ``{name: CovariateTransform}`` for the Posterior to persist. All
    empty when ``enabled == []`` (or no enabled covariate column is in the panel),
    so the design is byte-identical to today's baseline.
    """
    cov: dict = {}
    cov_mask: dict = {}
    transforms: dict = {}
    for name in p_cov.get("enabled", []):
        if name not in mp.columns:
            continue  # enabled but not produced upstream -> no covariate term
        train = mp[name].to_numpy()
        t = CovariateTransform.fit(name, train)        # fit on < cutoff training rows
        transforms[name] = t
        z, mask = t.apply(train)
        cov[name] = z
        cov_mask[name] = mask
        away_col = f"{name}__away"                      # per-team covariate: away side
        if away_col in mp.columns:                      # (per-match has no __away col)
            z_away, mask_away = t.apply(mp[away_col].to_numpy())  # SAME fitted transform
            cov[away_col] = z_away
            cov_mask[away_col] = mask_away
    return cov, cov_mask, transforms


def _covariate_betas(d: DesignData, p_cov: dict):
    """Return {name: (beta_RV, miss_beta_RV_or_None)} for each enabled covariate
    that is actually present in d.cov.

    No-op when enabled is empty OR no enabled covariate is in d.cov: returns {},
    so NO beta_* RV is created and _cov_offset contributes exactly 0.0 — the
    linear predictor (and the set of model RVs) is byte-identical to today.
    """
    betas = {}
    for name in p_cov.get("enabled", []):
        if name not in d.cov:
            continue  # enabled but no data supplied -> add nothing (still baseline)
        # FIX 1 (taxonomy): a covariate present in d.cov MUST be declared in
        # exactly one of the two side-wiring sets. Without this guard a typo'd or
        # undeclared name falls through _cov_offset's per-match `else` branch and
        # is silently mis-wired as a symmetric per-match term. Fail loud instead.
        if name not in (_PER_TEAM_COVS | _PER_MATCH_COVS):
            raise ValueError(
                f"unknown covariate {name!r}: not in _PER_TEAM_COVS or _PER_MATCH_COVS"
            )
        # FIX 3 (per-team both-sides): a per-team covariate is read on BOTH sides
        # — home reads d.cov[name], away reads d.cov[f"{name}__away"] — each with a
        # matching cov_mask key. Validate both arrays/masks exist up front so a
        # caller that supplies only one side fails clearly here, not with a deep
        # KeyError inside _cov_offset. (T3's fit() always supplies both.)
        if name in _PER_TEAM_COVS:
            away_key = f"{name}__away"
            if away_key not in d.cov or away_key not in d.cov_mask:
                raise ValueError(
                    f"per-team covariate {name!r} missing its '__away' array/mask in DesignData.cov"
                )
            if name not in d.cov_mask:
                raise ValueError(
                    f"per-team covariate {name!r} missing its home mask in DesignData.cov_mask"
                )
        beta = pm.Normal(f"beta_{name}", 0.0, p_cov["beta_scale"])
        miss = (
            pm.Normal(f"beta_{name}_miss", 0.0, p_cov["beta_scale"])
            if name in p_cov.get("missing_indicator_for", [])
            else None
        )
        betas[name] = (beta, miss)
    return betas


def _cov_offset(d: DesignData, betas, side):  # side in {"home", "away"}
    """Sum of covariate contributions for one side's log-rate.

    Each term is beta * x * mask, so a row where the feature is MISSING
    (mask == 0) contributes EXACTLY zero — the standardized value is never
    imputed. The optional missing-indicator term miss * (1 - mask) lets the
    model carry a separate intercept shift for missing rows without imputing x.
    For a per-team covariate the "home" side reads d.cov[name] (the home team's
    own feature) and the "away" side reads d.cov["<name>__away"] (the away team's
    own feature); a per-match covariate uses the single d.cov[name] on both sides.
    """
    off = 0.0
    for name, (beta, miss) in betas.items():
        if name in _PER_TEAM_COVS:
            key = name if side == "home" else f"{name}__away"
        else:  # per-match: same array both sides
            key = name
        x = pt.as_tensor_variable(d.cov[key])
        mask = pt.as_tensor_variable(d.cov_mask[key])
        off = off + beta * x * mask
        if miss is not None:
            off = off + miss * (1.0 - mask)
    return off


def _rates(d: DesignData, att, defe, mu, home_adv, betas=None):
    # log lambda_home = mu + home_adv*(non-neutral) + att[home] - def[away] + home_off
    # log lambda_away = mu + att[away] - def[home] + away_off   (no home term)
    # home_off/away_off are the masked covariate offsets (0.0 when betas is empty/
    # None), so with no enabled covariates the rates are byte-identical to today.
    neutral = d.neutral.astype(float)
    home_off = _cov_offset(d, betas, "home") if betas else 0.0
    away_off = _cov_offset(d, betas, "away") if betas else 0.0
    log_lh = mu + home_adv * (1.0 - neutral) + att[d.home_idx] - defe[d.away_idx] + home_off
    log_la = mu + att[d.away_idx] - defe[d.home_idx] + away_off
    return pt.exp(log_lh), pt.exp(log_la)


def _priors(d: DesignData, p, strength=None):
    sigma_att = pm.HalfNormal("sigma_att", sigma=p["sigma_att"])
    sigma_def = pm.HalfNormal("sigma_def", sigma=p["sigma_def"])
    # Elo-anchored prior MEAN (gated). When strength_prior.enabled, the att/def
    # prior mean leans toward each team's z-scored Elo strength: a strong team
    # wants HIGH att AND HIGH def (since lambda_home = exp(mu + att[home] -
    # def[away] + ...)), so BOTH anchor to +k·elo_z. When OFF, the mean is the
    # SCALAR 0.0 exactly as today — the off path never reads d.elo_z, so the model
    # is byte-identical to the pre-anchor baseline (and identical to elo_z=zeros).
    if strength and strength.get("enabled"):
        ez = np.asarray(
            d.elo_z if d.elo_z is not None else np.zeros(d.n_teams), dtype=float
        )
        mean_att = float(strength["k_att"]) * ez       # per-team prior mean (n_teams,)
        mean_def = float(strength["k_def"]) * ez
    else:
        mean_att = 0.0                                  # today's path -> byte-identical when off
        mean_def = 0.0
    att_raw = pm.Normal("att_raw", mean_att, sigma_att, shape=d.n_teams)
    def_raw = pm.Normal("def_raw", mean_def, sigma_def, shape=d.n_teams)
    # Soft sum-to-zero. elo_z is mean~0 across teams, so the per-team anchor
    # survives the centering (it shifts the RELATIVE means, which mean(att_raw)
    # does not flatten).
    att = pm.Deterministic("att", att_raw - pt.mean(att_raw))
    defe = pm.Deterministic("def", def_raw - pt.mean(def_raw))
    mu = pm.Normal("mu", p["mu_loc"], p["mu_scale"])
    home_adv = pm.Normal("home_adv", p["home_loc"], p["home_scale"])
    return att, defe, mu, home_adv


class ScorelineModel(ABC):
    @abstractmethod
    def build(self, d: DesignData, weight: np.ndarray, config: dict | None = None) -> pm.Model: ...


class DixonColesModel(ScorelineModel):
    def build(self, d, weight, config=None):
        cfg = config or load_config()
        p = cfg["model"]["prior"]
        with pm.Model() as m:
            att, defe, mu, home_adv = _priors(d, p, strength=cfg["model"].get("strength_prior"))
            # No-op when covariates.enabled == [] (or none present in d.cov):
            # betas == {} -> _rates adds a 0.0 offset, RV set unchanged.
            betas = _covariate_betas(d, cfg["model"]["covariates"])
            # rho CONTRACT (likelihoods.dc_loglik_pt): a tau cell <= 0 -> log(tau)
            # = NaN. This TruncatedNormal keeps |rho| small (<=0.15) so that for
            # realistic international goal rates (~<=2.5 each, lh*la <~ 6.25)
            # tau(0,0)=1-lh*la*rho stays positive. But the rates lh,la=exp(...) are
            # UNBOUNDED: a tail draw with lh*la*|rho| >= 1 can still push tau(0,0)<=0,
            # so the bound makes that RARE, not impossible. The actual structural NaN
            # guard for the unbounded-rate tail is the `_TAU_FLOOR` soft barrier in
            # dc_loglik_pt (a tau<=0 draw yields a finite penalty -> NUTS is repelled,
            # not crashed). The bound stays as a good weakly-informative prior (safe
            # Phase-2 default; Phase-4 may tune) that keeps the floor essentially never
            # active on realistic rates.
            rho = pm.TruncatedNormal(
                "rho", mu=0.0, sigma=p["rho_scale"], lower=-0.15, upper=0.15
            )
            lh, la = _rates(d, att, defe, mu, home_adv, betas=betas)
            ll = dc_loglik_pt(d.home_goals, d.away_goals, lh, la, rho)
            pm.Potential("like", pt.sum(pt.as_tensor_variable(weight) * ll))
        return m


class BivariatePoissonModel(ScorelineModel):
    def build(self, d, weight, config=None):
        cfg = config or load_config()
        p = cfg["model"]["prior"]
        # kmax = max over matches of min(home,away) goals (the convolution depth).
        # bp_loglik_pt handles kmax==0 as the independent case.
        kmax = int(np.minimum(d.home_goals, d.away_goals).max()) if len(d.home_goals) else 0
        with pm.Model() as m:
            att, defe, mu, home_adv = _priors(d, p, strength=cfg["model"].get("strength_prior"))
            # No-op when covariates.enabled == [] (or none present in d.cov):
            # betas == {} -> _rates adds a 0.0 offset, RV set unchanged.
            betas = _covariate_betas(d, cfg["model"]["covariates"])
            # l3 CONTRACT (likelihoods.bp_loglik_pt): l3 must be > 0 when kmax>0
            # (the k=0 term computes 0*log(l3); l3=0 yields NaN in the vectorized
            # graph). Parameterise l3 = exp(log_l3) so l3>0 ALWAYS. Centered at
            # log(0.1): a small covariance default, consistent with rho_scale.
            log_l3 = pm.Normal("log_lambda3", np.log(0.1), p["rho_scale"])
            l3 = pt.exp(log_l3)
            lh, la = _rates(d, att, defe, mu, home_adv, betas=betas)
            ll = bp_loglik_pt(d.home_goals, d.away_goals, lh, la, l3, kmax)
            pm.Potential("like", pt.sum(pt.as_tensor_variable(weight) * ll))
        return m


_REGISTRY = {
    "dixon_coles": DixonColesModel,
    "bivariate_poisson": BivariatePoissonModel,
}


def build_model(
    d: DesignData,
    likelihood: str | None = None,
    weight: np.ndarray | None = None,
    config: dict | None = None,
) -> pm.Model:
    likelihood = likelihood or (config or load_config())["model"]["likelihood"]
    if likelihood not in _REGISTRY:
        raise ValueError(f"unknown likelihood {likelihood!r}; choose from {sorted(_REGISTRY)}")
    w = d.weight if weight is None else weight
    return _REGISTRY[likelihood]().build(d, w, config)


def fit(
    cutoff,
    store,
    *,
    likelihood: str | None = None,
    backend: str | None = None,
    draws: int | None = None,
    tune: int | None = None,
    seed: int | None = None,
    advi_iters: int | None = None,
    config: dict | None = None,
    feature_cache_dir=None,
) -> Posterior:
    """Fit the scoreline model on the leakage-safe per-cutoff panel -> Posterior.

    Consumes ONLY ``features.build(cutoff, store, cfg)`` -- the Phase-1
    leakage-safe panel (matches strictly before the cutoff day, played-filtered).
    No future data and no other store table is read here, so a fit at ``cutoff``
    can never peek past it (Phase-2 Task 9 adds a model-layer leakage canary on
    top of this). The match-level design feeds the (a)/(c) widening switch and the
    PyMC scoreline model; ``sample`` (ADVI by default) produces the posterior. The
    provisional-team set (for mechanism-(c) predict-time widening) is the
    AS-OF-CUTOFF status -- each team's would-be provisional flag at its NEXT match
    -- via the Task-0 ``count_volatility_arm`` (volatility OR few-games arm), NOT
    the per-match panel flags. Those panel flags are PRE-MATCH states, so a team
    provisional only in its first few (historical) matches would otherwise be
    flagged "ever provisional" and widened at predict time forever; the
    as-of-cutoff status widens only teams genuinely low-information NOW.
    ``count_volatility_arm`` reads only matches strictly before the cutoff (the
    same leakage-safe slice ``features.build`` uses), so this stays leakage-safe;
    the duplicate sub-cutoff Elo recompute is acceptable for Phase 2.

    All sampler knobs default to ``config["model"]`` (or the global config) and
    can be overridden per-call; ``seed`` falls back to the global ``config["seed"]``.
    """
    cfg = config or load_config()
    likelihood = likelihood or cfg["model"]["likelihood"]
    inf = cfg["model"]["inference"]
    backend = backend or inf["backend"]
    draws = draws or inf["draws"]
    tune = tune or inf["tune"]
    advi_iters = advi_iters or inf["advi_iters"]
    seed = cfg["seed"] if seed is None else seed
    # Route the panel build through the content-addressed feature-panel cache
    # (``build_cached``): the per-cutoff Elo recompute over the full < cutoff
    # history is ~5 min, so a re-fit that already paid it (or a sibling cutoff
    # sharing the < cutoff slice) reads the panel from disk instead. With
    # ``feature_cache_dir=None`` this is exactly ``features.build`` — unchanged.
    feats = features.build_cached(cutoff, store, cfg, cache_dir=feature_cache_dir)
    mp = to_match_panel(feats)
    # Build the leakage-safe covariate transforms on the SAME < cutoff training
    # panel `mp` (before build_design / sampling), and thread the standardized
    # arrays + masks into the design. Empty dicts when covariates.enabled == [],
    # so the design (and the fitted model) is byte-identical to today's baseline.
    cov, cov_mask, cov_transforms = _build_covariates(mp, cfg["model"]["covariates"])
    # Per-team Elo strength anchor (leakage-safe): team_elo_z reads only `feats`,
    # the < cutoff panel, so a post-cutoff result is invisible to elo_z (proven by
    # tests/model/test_fit_strength_leakage.py). `teams` here is the SAME sorted
    # unique set build_design computes internally, so the elo_z array aligns to the
    # design team index. When strength_prior is OFF (default) _priors ignores elo_z
    # entirely, so this is byte-identical to today's baseline.
    from wcmodel.model.strength import team_elo_z
    teams = sorted(set(mp["home_team"]) | set(mp["away_team"]))
    elo_z = team_elo_z(feats, teams)
    d = build_design(mp, cov=cov, cov_mask=cov_mask, elo_z=elo_z)
    w = likelihood_weight(
        d,
        mechanism=cfg["model"]["widening"]["mechanism"],
        strength=cfg["model"]["widening"]["strength"],
    )
    model = build_model(d, likelihood=likelihood, weight=w, config=cfg)
    idata = sample(
        model, backend=backend, draws=draws, tune=tune, seed=seed, advi_iters=advi_iters
    )
    # Provisional set is the AS-OF-CUTOFF status (each team's would-be flag at its
    # NEXT match), NOT the per-match panel flags (which are pre-match states, so a
    # team provisional only in its early history would be widened forever).
    # count_volatility_arm reads only matches strictly before the cutoff -> the
    # same leakage-safe slice features.build uses; a team is provisional-for-
    # prediction iff its volatility OR few-games arm trips.
    # Thread the resolved `cfg` so the provisional set is computed under the
    # PASSED elo config (not global disk) — a custom cfg["elo"] (lockbox K/T
    # sweep) thus actually changes the provisional set, matching the posterior
    # cache key (closes the Task-0 stale-serve finding). count_volatility_arm
    # keeps its own `< cutoff` filter, so leakage-safety is unchanged; only the
    # K/T params it feeds to compute_elo_history move.
    arm = count_volatility_arm(store, cutoff, d.teams, config=cfg)
    prov = set(arm.loc[arm["volatility_flag"] | arm["few_games_flag"], "team"])
    return Posterior(
        idata, d.teams, likelihood, provisional_teams=prov, config=cfg,
        covariate_transforms=cov_transforms,    # persist for predict (T4) to reuse
    )
