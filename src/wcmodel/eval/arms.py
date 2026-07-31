"""The stacking arm S — an ordered-logit blender over the [DC, odds,
elo-ordlogit] 1X2 forecasts (OA Plan 2 v2, V6).

Each base arm's 1X2 vector is reduced to ONE latent location: minus the mean
of its two cumulative logits, ``-(logit(P(away)) + logit(P(away or draw)))/2``
— for a forecast that IS a proportional-odds curve this recovers its latent
eta up to an affine constant, which the fitted thresholds absorb, so a base
arm that is already calibrated on this scale is reproduced at unit weight.
The head is then the same structural proportional-odds machine as the
elo-ordlogit arm (``c2 = c1 + exp(s)``: no parameterisation can put negative
mass on the draw), with one fitted weight per base arm::

    eta = b_dc * x_dc + b_odds * x_odds + b_elo * x_elo

The arm is 1X2-ONLY STRUCTURALLY: inputs are three 1X2 vectors, output is a
1X2 vector, and this module exposes no scoreline/grid surface at all — there
is nothing to ask for totals or scorelines through (pinned by the public-
surface test).

Training is on the SAME dev-ledger OOF rows the (w, de-vig) selection
consumes, under the SAME frozen monthly fold structure (finding 9, shared
constants from :mod:`wcmodel.eval.blend`): fold t is scored with a head
fitted on months < t, and the FINAL head — the deployment parameters the V8
lock hashes via the selection trace — is fitted on all dev months. Rows
without admissible odds are EXCLUDED (the odds feature does not exist for
them); a missing DC or elo-ordlogit base row is a pipeline BUG and errors
(those arms need no odds, so absence is never coverage). The de-vig feeding
the odds feature passes the OA gate: exactly {shin, multiplicative}, 'basic'
resolves as the reporting label for multiplicative, 'power' can enter
nothing (finding 13).

The three betas carry weakly-informative Gaussian priors (sd 3.0, the
elo-ordlogit remedy for the same disease): the base scores are strongly
COLLINEAR — three forecasts of the same fixture — so outcomes that separate
along some combination of them have no finite MLE, and L-BFGS-B would report
SUCCESS at wherever its stopping rule landed, emitting a point mass that
passes every downstream probability check. The features are already in
latent-logit units (b = 1 means "trust this arm as calibrated"), so sd 3.0
is weakly informative by the scale's own yardstick; the prior term is
divided by n (one fixed Gaussian on the sum scale) so it washes out as rows
accumulate. Thresholds stay plain MLE. Deterministic throughout: fixed
init, no RNG, canonical (date, fixture_id) row order — the same ledger
always yields bitwise-identical parameters.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, log_expit, logit

from wcmodel.eval.blend import (
    SELECTION_BURN_IN_MONTHS,
    _covered_fixture_ids,
    require_dev_ledger,
)
from wcmodel.eval.implied import OA_DEVIG_LABELS, OA_DEVIG_METHODS
from wcmodel.model.calibration import rps

#: The frozen feature order — column j of the design matrix and the meaning
#: of ``b_dc``/``b_odds``/``b_elo`` depend on it.
STACK_FEATURE_ORDER = ("dc", "odds", "elo_ordlogit")

_DC_ARM = "dev_dc"
_ELO_ARM = "dev_elo_ordlogit"

# The ordinal direction of the latent scale (increasing eta favours the home
# team) — the elo_ordlogit convention, and the y-index coding of the fit.
_LATENT_ORDER = ("away", "draw", "home")

# See the module docstring for why the betas are penalised and the
# thresholds are not.
_PRIOR_SD = 3.0

# Seed-free deterministic init in (c1, s, b_dc, b_odds, b_elo) order:
# thresholds at 0 and 1, the three arms at equal weight summing to a unit
# slope (an equal-trust blend of calibrated arms).
_INIT = np.array([0.0, 0.0, 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])

# Only ``s`` is bounded, and only to keep exp(s) inside float range mid-line-
# search — the elo_ordlogit rationale verbatim; the betas' problem is
# identification, which the priors handle, not range.
_BOUNDS = [(None, None), (-30.0, 30.0), (None, None), (None, None),
           (None, None)]


@dataclass(frozen=True)
class StackParams:
    """A fitted stacking head. ``s`` is the LOG width of the draw band
    (``c2 = c1 + exp(s)`` structurally); the betas follow
    :data:`STACK_FEATURE_ORDER`."""
    c1: float
    s: float
    b_dc: float
    b_odds: float
    b_elo: float


@dataclass(frozen=True)
class StackFold:
    """One scored fold: the head fitted on the months BEFORE ``month`` and
    its realized mean canonical RPS ON ``month``."""
    month: str
    n_train_fixtures: int
    n_fold_fixtures: int
    rps: float
    params: StackParams


@dataclass(frozen=True)
class StackingFit:
    """The OOF-trained stacking arm: deployment ``params`` (fitted on all
    dev months), the walk-forward fold trace, and the pooled per-fixture OOF
    RPS over every fold-scored fixture."""
    params: StackParams
    devig_method: str
    folds: tuple[StackFold, ...]
    oof_rps: float
    n_fixtures: int
    n_excluded_no_odds: int

    def trace_payload(self) -> dict:
        """The JSON-ready mapping the V6 selection trace embeds (and the V8
        lock therefore hashes)."""
        def params_of(p: StackParams) -> dict:
            return {"c1": p.c1, "s": p.s, "b_dc": p.b_dc, "b_odds": p.b_odds,
                    "b_elo": p.b_elo}
        return {
            "arm": "stacking",
            "devig_method": self.devig_method,
            "feature_order": list(STACK_FEATURE_ORDER),
            "prior_sd": _PRIOR_SD,
            "params": params_of(self.params),
            "oof_rps": self.oof_rps,
            "n_fixtures": self.n_fixtures,
            "n_excluded_no_odds": self.n_excluded_no_odds,
            "folds": [
                {"month": f.month, "n_train_fixtures": f.n_train_fixtures,
                 "n_fold_fixtures": f.n_fold_fixtures, "rps": f.rps,
                 "params": params_of(f.params)}
                for f in self.folds],
        }


def _latent_score(probs: Mapping, where: str) -> float:
    """One base arm's latent location from its 1X2 vector.

    Refuses (never clips) a non-distribution or a boundary probability: a
    cumulative at exactly 0 or 1 has an infinite logit, and every honest
    producer in this repo (DC grids at finite rates, de-vigged finite odds,
    the penalised elo-ordlogit head) emits strictly interior probabilities —
    a boundary here IS a defective pipeline, and the elo-ordlogit module
    documents exactly how such a point mass otherwise sails through
    downstream probability checks.
    """
    if set(probs) != set(_LATENT_ORDER):
        raise ValueError(
            f"{where}: 1X2 mapping must have exactly the canonical keys "
            f"('home', 'draw', 'away'); got {sorted(probs)}")
    values = {k: float(probs[k]) for k in probs}
    if not all(math.isfinite(v) and 0.0 <= v <= 1.0
               for v in values.values()):
        raise ValueError(f"{where}: 1X2 probabilities out of range: {values}")
    if abs(sum(values.values()) - 1.0) > 1e-9:
        raise ValueError(
            f"{where}: 1X2 probabilities sum to {sum(values.values())!r}, "
            "not 1")
    cum_away = values["away"]
    cum_away_draw = values["away"] + values["draw"]
    if not (0.0 < cum_away < 1.0 and 0.0 < cum_away_draw < 1.0):
        raise ValueError(
            f"{where}: boundary cumulative probability (point mass) — the "
            "latent logit is infinite; a base arm emitting this is defective")
    return -0.5 * float(logit(cum_away) + logit(cum_away_draw))


def _log_probs(theta: np.ndarray, X: np.ndarray) -> np.ndarray:
    """Rows of log P in ``_LATENT_ORDER`` — the elo_ordlogit stable-draw
    identity (``sigmoid(a) - sigmoid(b)`` factored so no category
    underflows), generalized to a feature-matrix eta."""
    c1, s = theta[0], theta[1]
    gap = np.exp(s)
    z1 = c1 - X @ theta[2:]
    z2 = z1 + gap
    log_draw = log_expit(z2) + log_expit(-z1) + np.log(-np.expm1(-gap))
    return np.stack([log_expit(z1), log_draw, log_expit(-z2)])


def _objective(theta: np.ndarray, X: np.ndarray, y: np.ndarray) -> float:
    """Mean NLL + the beta priors / (2n) — mean scale for the optimizer's
    finite differences, sum-scale priors so they wash out with n (the
    elo_ordlogit._objective reasoning, verbatim)."""
    log_p = _log_probs(theta, X)
    nll = -float(log_p[y, np.arange(y.size)].mean())
    penalty = float(np.sum(theta[2:] ** 2)) / _PRIOR_SD ** 2
    return nll + penalty / (2.0 * y.size)


def _fit(X: np.ndarray, y: np.ndarray) -> StackParams:
    absent = [label for i, label in enumerate(_LATENT_ORDER)
              if not (y == i).any()]
    if absent:
        raise ValueError(
            f"no {absent} outcome in the training months — an absent class "
            "leaves its threshold unidentified (the elo-ordlogit stance: "
            "refuse, never fit a degenerate head)")
    result = minimize(_objective, _INIT, args=(X, y), method="L-BFGS-B",
                      bounds=_BOUNDS)
    if not result.success:
        raise RuntimeError(
            f"stacking ordered-logit fit did not converge: {result.message}")
    c1, s, b_dc, b_odds, b_elo = (float(v) for v in result.x)
    return StackParams(c1=c1, s=s, b_dc=b_dc, b_odds=b_odds, b_elo=b_elo)


def _head_probs(params: StackParams, eta: float) -> dict[str, float]:
    gap = math.exp(params.s)
    z1 = params.c1 - eta
    z2 = z1 + gap
    return {"home": float(expit(-z2)),
            # The same stable difference as the likelihood — see _log_probs.
            "draw": float(expit(z2) * expit(-z1) * -math.expm1(-gap)),
            "away": float(expit(z1))}


def predict_stacked(params: StackParams, base: Mapping) -> dict[str, float]:
    """The stacked 1X2 from the three base arms' 1X2 vectors.

    ``base`` maps EXACTLY the :data:`STACK_FEATURE_ORDER` keys to canonical
    1X2 mappings. Output keys are the canonical ``('home', 'draw', 'away')``
    so the result drops straight into the canonical scorers — and a 1X2
    vector is ALL this arm can emit, structurally.
    """
    if set(base) != set(STACK_FEATURE_ORDER):
        raise ValueError(
            f"base forecasts must be keyed exactly {STACK_FEATURE_ORDER}; "
            f"got {sorted(base)}")
    scores = np.array([_latent_score(base[key], f"base arm {key!r}")
                       for key in STACK_FEATURE_ORDER])
    eta = float(scores @ np.array([params.b_dc, params.b_odds, params.b_elo]))
    return _head_probs(params, eta)


def _design(frame: pd.DataFrame, outcomes: Mapping[str, str], method: str):
    """Design matrix from the dev ledger's three base arms.

    Returns ``(X, y, month_arr, n_excluded)`` in canonical (date,
    fixture_id) row order. Exclusion vs error is the coverage boundary: no
    odds row AND the fixture is genuinely uncovered -> the odds feature does
    not exist -> EXCLUDED and counted; a missing DC/elo-ordlogit row, a
    covered fixture (any non-null odds_snapshot_hash row in the frame —
    B2-2's explicit expected set) missing its base rows or its
    ``dev_odds_{method}`` row, a null-hash odds row, disagreeing dates or a
    missing outcome -> pipeline bug -> error, never a silently smaller
    stack.
    """
    covered = _covered_fixture_ids(frame)
    odds_arm = f"dev_odds_{method}"
    keys = {_DC_ARM: "dc", odds_arm: "odds", _ELO_ARM: "elo_ordlogit"}
    rows: dict[str, dict[str, tuple]] = {}
    for row in frame[frame["arm"].isin(list(keys))].itertuples(index=False):
        rows.setdefault(str(row.fixture_id), {})[keys[str(row.arm)]] = row

    baseless = sorted(covered - set(rows))
    if baseless:
        raise ValueError(
            f"covered fixture(s) {baseless[:5]}"
            f"{' ...' if len(baseless) > 5 else ''} carry non-null "
            "odds_snapshot_hash rows but NONE of the stacking base arms — "
            "the fixture would silently vanish from the stack (B2-2); every "
            "covered fixture must carry its dc/odds/elo base block")

    included: dict[str, str] = {}
    n_excluded = 0
    for fid in sorted(rows):
        got = rows[fid]
        for arm, key in ((_DC_ARM, "dc"), (_ELO_ARM, "elo_ordlogit")):
            if key not in got:
                raise ValueError(
                    f"fixture {fid!r} is missing its {arm} row — the "
                    "odds-free base arms exist for every dev fixture, so an "
                    "absent one is a pipeline bug, never odds absence")
        if "odds" not in got:
            if fid in covered:
                raise ValueError(
                    f"fixture {fid!r} is covered (non-null "
                    "odds_snapshot_hash rows exist in the ledger) but has "
                    f"no {odds_arm} row — a covered fixture missing its "
                    "odds base is a pipeline bug (B2-2), never odds absence")
            n_excluded += 1
            continue
        if pd.isna(got["odds"].odds_snapshot_hash):
            raise ValueError(
                f"fixture {fid!r} carries a {odds_arm} row with a null "
                "odds_snapshot_hash — an odds forecast without its snapshot "
                "is incoherent (odds-absent fixtures have NO odds row)")
        dates = {str(got[key].date) for key in keys.values()}
        if len(dates) != 1:
            raise ValueError(
                f"fixture {fid!r} base rows disagree on date: "
                f"{sorted(dates)}")
        if outcomes.get(fid) not in _LATENT_ORDER:
            raise ValueError(
                f"missing or invalid outcome for dev fixture {fid!r}: got "
                f"{outcomes.get(fid)!r}, need one of {_LATENT_ORDER}")
        included[fid] = next(iter(dates))

    order = sorted(included, key=lambda fid: (included[fid], fid))
    X = np.empty((len(order), len(STACK_FEATURE_ORDER)))
    y = np.empty(len(order), dtype=int)
    for i, fid in enumerate(order):
        got = rows[fid]
        for j, key in enumerate(STACK_FEATURE_ORDER):
            row = got[key]
            X[i, j] = _latent_score(
                {"home": float(row.p_home), "draw": float(row.p_draw),
                 "away": float(row.p_away)},
                f"fixture {fid!r} arm {key!r}")
        y[i] = _LATENT_ORDER.index(outcomes[fid])
    month_arr = np.array([included[fid][:7] for fid in order])
    return X, y, month_arr, n_excluded


def oof_stacking(ledger, *, outcomes: Mapping[str, str], manifest,
                 devig_method: str) -> StackingFit:
    """Train the stacking arm out-of-fold on the V5 dev ledger.

    Same dev-only diet as ``select_w`` (manifest membership, dev_ arms, no
    scored pools — enforced by the shared :func:`require_dev_ledger`), same
    frozen monthly folds and burn-in. ``devig_method`` selects which
    ``dev_odds_{method}`` rows feed the odds feature — normally the method
    ``select_w`` chose — and passes the OA gate (finding 13): 'basic'
    resolves to multiplicative, anything outside {shin, multiplicative} is
    refused.
    """
    resolved = OA_DEVIG_LABELS.get(devig_method, devig_method)
    if resolved not in OA_DEVIG_METHODS:
        raise ValueError(
            f"de-vig method {devig_method!r} is not OA-choosable; the OA set "
            f"is exactly {OA_DEVIG_METHODS} ('basic' is the reporting label "
            "for 'multiplicative'; 'power' stays a Phase-4 backtest method — "
            "finding 13)")
    frame = require_dev_ledger(ledger, manifest)
    X, y, month_arr, n_excluded = _design(frame, outcomes, resolved)
    if X.shape[0] == 0:
        raise ValueError(
            "no odds-covered dev fixtures with all three base arms — "
            "nothing to stack")
    months = sorted({str(m) for m in month_arr})
    if len(months) < SELECTION_BURN_IN_MONTHS + 1:
        raise ValueError(
            f"only {len(months)} dev month(s) with covered fixtures; the "
            f"frozen spec needs at least {SELECTION_BURN_IN_MONTHS + 1} "
            "(burn-in + one scoreable fold) — refuse rather than degrade")

    folds: list[StackFold] = []
    oof_scores: list[float] = []
    for fold_month in months[SELECTION_BURN_IN_MONTHS:]:
        train = month_arr < fold_month
        fold_mask = month_arr == fold_month
        params = _fit(X[train], y[train])
        fold_scores = [
            rps(_head_probs(params, float(
                X[i] @ np.array([params.b_dc, params.b_odds, params.b_elo]))),
                _LATENT_ORDER[y[i]])
            for i in np.flatnonzero(fold_mask)]
        folds.append(StackFold(
            month=fold_month, n_train_fixtures=int(train.sum()),
            n_fold_fixtures=int(fold_mask.sum()),
            rps=float(np.mean(fold_scores)), params=params))
        oof_scores.extend(fold_scores)

    return StackingFit(
        params=_fit(X, y), devig_method=resolved, folds=tuple(folds),
        oof_rps=float(np.mean(oof_scores)), n_fixtures=int(X.shape[0]),
        n_excluded_no_odds=n_excluded)
