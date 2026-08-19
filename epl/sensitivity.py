"""D19 — is mean-field ADVI visibly under-dispersed, and does it move the table?

WHAT PLAN v2 D19 ASKS FOR. Three layers of uncertainty are named: parameter
(D1), future strength evolution (D2, unmodelled), and match randomness (the
sampler). The first is delivered by mean-field ADVI, which is known to
UNDERESTIMATE posterior variance, and everything downstream of the particle book
inherits that: the title spread, the relegation spread, the points intervals.
The plan's remedy is one cutoff refit with a richer posterior and a side-by-side
comparison — "before any public uncertainty language".

WHAT IS REACHABLE WITHOUT TOUCHING ``src/``. ``epl.dcfit.fit_epl`` passes
``cfg["model"]["inference"]["backend"]`` straight to
``wcmodel.model.inference.sample``, which dispatches ``{"nuts", "advi",
"pathfinder"}``; ``pathfinder`` raises ``NotImplementedError`` on the installed
pymc (it is not built), and ``pm.fit``'s ``fullrank_advi`` is not in the
dispatch at all. NUTS therefore IS the richer posterior, and it is selected by a
config value this package already builds — :func:`richer_config` deep-copies the
frozen config and swaps the inference block. Nothing under ``src/`` is written,
and the production path is untouched: the frozen config still says ``advi``.

WHAT THIS MODULE IS, AND IS NOT. It is the comparison arithmetic and the report
builder — posterior standard deviations per parameter, their ratios, the
consequence probabilities side by side with their Monte-Carlo standard errors,
the per-club points spread, and TRPS against a realised table. It is NOT a claim
that NUTS is the truth: 1,000 NUTS draws from two chains are themselves an
estimate, and a ratio near one is evidence of agreement at THIS cutoff on THIS
panel, not a general result. The report says so.
"""
from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

__all__ = ["SensitivityError", "BACKENDS", "PARAMS", "HYPERPARAMS",
           "CONVERGENCE_PARAMS", "richer_config", "draw_count",
           "check_draw_count", "posterior_sds", "align_by_name", "sd_ratios",
           "ess_inflation", "consequence_table", "points_sds",
           "expected_relegations_among", "report_markdown", "run_d19"]

#: The cutoff D19 is run at: a settled season, so both arms can also be scored
#: against the table that actually happened.
D19_SEASON = "2025/26"
D19_CUTOFF_LABEL = "MW0"

#: NUTS draws PER CHAIN. Two chains (``inference.sample`` hardcodes it) makes
#: 1,000 posterior draws, which is exactly the production ADVI draw count — so
#: the two books carry the same number of particles and any difference in
#: Monte-Carlo error is not a difference in S.
D19_NUTS_DRAWS = 500
D19_NUTS_TUNE = 3000

#: Backends ``wcmodel.model.inference.sample`` actually dispatches on the
#: installed stack. ``pathfinder`` is a named branch there that raises
#: ``NotImplementedError`` (no ``pymc_experimental``, no ``nutpie``), and
#: ``fullrank_advi`` — which ``pm.fit`` itself supports — is NOT reachable,
#: because the dispatch never passes ``method`` through. Selecting anything not
#: in this tuple would be selecting a ``ValueError``.
BACKENDS = ("advi", "nuts")

#: The parameters the particle book carries and the sim actually samples from.
#: ``sigma_att``/``sigma_def`` are hyperparameters and are reported separately:
#: a change in THEIR spread is a different statement from a change in the
#: spread of the team effects they govern.
PARAMS = ("att", "def", "home_adv", "mu", "rho")
HYPERPARAMS = ("sigma_att", "sigma_def")

#: What the convergence check covers: EVERY quantity the report puts a ratio
#: beside. It used to cover ``PARAMS`` alone, so the report quoted `sigma_att`
#: and `sigma_def` ratios — 1.32x and 1.25x, among the largest gaps it found —
#: from a reference whose mixing on those very blocks had never been looked at.
CONVERGENCE_PARAMS = PARAMS + HYPERPARAMS


class SensitivityError(RuntimeError):
    """The sensitivity refuses to produce or compare a number."""


# ==========================================================================
# 1. selecting the richer backend — without touching src/
# ==========================================================================
def richer_config(base: dict, *, backend: str = "nuts", draws: int | None = None,
                  tune: int | None = None) -> dict:
    """A DEEP COPY of ``base`` with the inference block swapped.

    Deep-copied on purpose: the frozen config is shared by the production fit
    path in the same process, and a sensitivity run that mutated it would
    silently re-point production at the richer backend. The test beside this
    asserts the input is unchanged.
    """
    if backend not in BACKENDS:
        raise SensitivityError(
            f"backend {backend!r} is not reachable on this stack; "
            f"wcmodel.model.inference.sample dispatches {list(BACKENDS)} "
            "(pathfinder raises NotImplementedError, and fullrank_advi is not "
            "in the dispatch). Selecting it would raise, not produce a fit.")
    cfg = copy.deepcopy(base)
    inference = cfg["model"]["inference"]
    inference["backend"] = backend
    if draws is not None:
        inference["draws"] = int(draws)
    if tune is not None:
        inference["tune"] = int(tune)
    return cfg


def draw_count(cfg: dict) -> int:
    """How many posterior draws ``cfg`` will produce.

    NUTS in this stack runs TWO chains (``inference.sample`` hardcodes
    ``chains=2``) and the posterior is stacked over chain and draw, so ``draws``
    means draws PER CHAIN there and total draws under ADVI. Getting this wrong
    is how two arms end up with different particle counts and an unexplained
    difference in Monte-Carlo error.
    """
    inference = cfg["model"]["inference"]
    n = int(inference["draws"])
    return 2 * n if inference["backend"] == "nuts" else n


def check_draw_count(label: str, cfg: dict, n_particles: int) -> int:
    """Refuse a book that does not carry the draw count its config promised.

    :func:`run_d19` calls this on both arms, which is what makes
    :func:`draw_count` load-bearing rather than decorative: the whole comparison
    rests on the two books carrying the SAME S, so that a difference in
    Monte-Carlo error between them is a property of the posterior and not of how
    many draws each arm happened to get. A silent mismatch — ``draws`` read as a
    total when NUTS means per chain — would show up as the richer arm being
    mysteriously tighter.
    """
    expected = draw_count(cfg)
    inference = cfg["model"]["inference"]
    chains = 2 if inference["backend"] == "nuts" else 1
    if int(n_particles) != expected:
        raise SensitivityError(
            f"{label}: the config promises {expected} posterior draw(s) "
            f"({int(inference['draws'])} x {chains} chain(s) under "
            f"{inference['backend']!r}) but the particle book carries "
            f"{int(n_particles)}. The two arms would not be compared at the "
            "same S, and the difference in Monte-Carlo error between them "
            "would be a difference in draw count.")
    return expected


# ==========================================================================
# 2. dispersion
# ==========================================================================
def posterior_sds(post, params: Sequence[str] = PARAMS) -> dict[str, np.ndarray]:
    """Posterior sd per parameter, over the draw axis.

    Read through ``post._post`` — the same accessor the particle book and
    ``draw_api`` use — so a :class:`epl.dcfit.ColdStartPosterior`'s prior-drawn
    rows are included exactly as they are when the model is sampled from. A
    team-indexed parameter comes back ``(T,)``; a scalar one comes back ``(1,)``.
    """
    out: dict[str, np.ndarray] = {}
    for name in params:
        arr = np.asarray(post._post(name), dtype=float)
        if arr.ndim == 1:
            out[name] = np.array([float(arr.std(ddof=1))])
        elif arr.ndim == 2:
            out[name] = arr.std(axis=1, ddof=1)
        else:                                              # pragma: no cover
            raise SensitivityError(
                f"{name!r} came back with shape {arr.shape}; the accessor "
                "returns (S,) or (T, S)")
    return out


def align_by_name(values: np.ndarray, *, source: Sequence[str],
                  target: Sequence[str], what: str) -> np.ndarray:
    """``values`` (indexed by ``source``) reordered into ``target``'s order.

    The two arms are two separate fits, and each carries its OWN team index.
    Nothing guarantees the two indices are in the same order, and when they are
    not, an element-wise ratio silently divides one club's spread by another's —
    same shape, same n, plausible-looking numbers, wrong club on every row. So
    the alignment is by NAME and a set mismatch refuses rather than truncating
    to the overlap.
    """
    source, target = [str(s) for s in source], [str(t) for t in target]
    if sorted(source) != sorted(target):
        only_source = sorted(set(source) - set(target))
        only_target = sorted(set(target) - set(source))
        raise SensitivityError(
            f"{what}: the two fits index different clubs — "
            f"{len(only_source)} only in one ({only_source[:5]}), "
            f"{len(only_target)} only in the other ({only_target[:5]}). The "
            "ratio is defined on the shared set or not at all.")
    position = {club: i for i, club in enumerate(source)}
    return np.asarray(values, dtype=float)[[position[c] for c in target]]


def sd_ratios(rich: dict[str, np.ndarray], mean_field: dict[str, np.ndarray],
              *, teams: Sequence[str] | None = None,
              mean_field_teams: Sequence[str] | None = None) -> dict[str, dict]:
    """``richer / mean-field`` posterior sd, per parameter.

    A ratio above 1 means mean-field was TIGHTER than the reference — the
    under-dispersion D19 names. The per-team spread is reported (mean, min, max,
    and which team is at each end) rather than only its average, because a
    parameter can be well matched on average and badly matched on the one club
    whose spread reaches a cut line.

    ``teams`` labels the RICHER arm's team axis and ``mean_field_teams`` the
    production arm's. Give both and the team-indexed parameters are aligned by
    NAME before the division: the two arms are two fits, each with its own
    index, and a same-size reordering would otherwise divide one club's spread
    by another's without changing a single shape.
    """
    out: dict[str, dict] = {}
    for name, rich_sd in rich.items():
        mf = np.asarray(mean_field[name], dtype=float)
        rich_sd = np.asarray(rich_sd, dtype=float)
        if (teams is not None and mean_field_teams is not None
                and mf.shape == (len(mean_field_teams),)):
            mf = align_by_name(mf, source=mean_field_teams, target=teams,
                               what=repr(name))
        if rich_sd.shape != mf.shape:
            raise SensitivityError(
                f"{name!r}: richer sds are {rich_sd.shape} and mean-field "
                f"{mf.shape} — the two fits do not describe the same objects. "
                "The team index is the usual cause; compare on the shared set.")
        if not np.all(mf > 0):
            raise SensitivityError(
                f"{name!r}: a mean-field sd is zero, so the ratio is undefined; "
                "a degenerate posterior is a finding, not a denominator")
        ratio = rich_sd / mf
        entry = {
            "n": int(ratio.size),
            "mean": float(ratio.mean()),
            "median": float(np.median(ratio)),
            "min": float(ratio.min()),
            "max": float(ratio.max()),
            "mean_field_sd_mean": float(mf.mean()),
            "richer_sd_mean": float(rich_sd.mean()),
        }
        if teams is not None and ratio.size == len(teams):
            entry["min_team"] = str(teams[int(np.argmin(ratio))])
            entry["max_team"] = str(teams[int(np.argmax(ratio))])
        out[name] = entry
    return out


# ==========================================================================
# 3. what it does to the published numbers
# ==========================================================================
def consequence_table(run, markets: Sequence[str] = ("champion", "top4",
                                                     "relegated")) -> dict:
    """``{market: {club: (p, se)}}`` from a :class:`epl.leaguesim.SimRun`.

    The standard error is the run's own cluster-by-particle Monte-Carlo error.
    It is MC error and says nothing about model error — which is exactly why
    this comparison exists: two arms whose probabilities differ by less than a
    couple of MC standard errors have not been shown to differ at all.
    """
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for market in markets:
        row: dict[str, tuple[float, float]] = {}
        for club, by_market in run.consequences.items():
            cell = by_market.get(market)
            if cell is None:
                raise SensitivityError(
                    f"the run publishes no {market!r} market for {club}; it "
                    f"carries {sorted(by_market)}")
            row[str(club)] = (float(cell["p"]), float(cell["se"]))
        out[market] = row
    return out


def ess_inflation(convergence: dict | None, n_draws: int) -> dict:
    """How much a NUTS arm's cluster MC standard error understates itself.

    The run's per-cell standard error is a cluster-by-particle error: it treats
    the S posterior draws as S INDEPENDENT clusters. That is right for ADVI,
    whose draws are i.i.d. from one approximation, and wrong for NUTS, whose
    draws are a Markov chain. The honest count of independent clusters is the
    bulk effective sample size, so::

        SE_adjusted = SE_cluster * sqrt(S / ESS_bulk_min)

    with ``ESS_bulk_min`` the SMALLEST bulk ESS over the parameter blocks the
    convergence check covered — the worst-mixed block, because the table is a
    function of all of them together. The factor is floored at 1: an ESS above S
    (NUTS can be antithetic) is not a reason to report a SMALLER error than the
    cluster form, which is the only one actually computed from the run.

    Returns ``available: False`` when the arm recorded no multi-chain
    convergence — an ADVI arm needs no adjustment and does not get a made-up one.
    """
    conv = convergence or {}
    if not conv.get("available"):
        return {"available": False,
                "reason": "no multi-chain convergence recorded for this arm; "
                          "i.i.d. draws need no ESS adjustment"}
    ess = conv.get("min_ess")
    if ess is None or not np.isfinite(float(ess)) or float(ess) <= 0:
        return {"available": False,
                "reason": f"bulk ESS is {ess!r}, so no factor can be formed"}
    raw = math.sqrt(float(n_draws) / float(ess))
    return {
        "available": True,
        "factor": float(max(1.0, raw)),
        "raw_factor": float(raw),
        "n_draws": int(n_draws),
        "min_ess": float(ess),
        "rule": (f"SE_adjusted = SE_cluster * sqrt(S / ESS_bulk_min) = "
                 f"sqrt({int(n_draws)} / {float(ess):.0f}) = {raw:.3f}"
                 + ("" if raw >= 1.0 else ", floored at 1.000")),
    }


def points_sds(run) -> dict[str, float]:
    """Per-club standard deviation of the simulated points total.

    Computed from the run's retained integer points rows, so it is the spread of
    the seasons actually simulated rather than a summary of a summary.
    """
    points = np.asarray(run.retained_rows.points, dtype=float)
    if points.ndim != 2 or points.shape[1] != len(run.clubs):
        raise SensitivityError(
            f"points rows are {points.shape}, expected (N, {len(run.clubs)})")
    return {club: float(points[:, i].std(ddof=1))
            for i, club in enumerate(run.clubs)}


def expected_relegations_among(run, clubs: Sequence[str]) -> dict:
    """``E[# of `clubs` relegated]`` and its Monte-Carlo standard error.

    Summed over the named clubs' relegation probabilities. The standard error is
    the SUM of the per-club MC standard errors — deliberately conservative,
    because the events are negatively correlated (three go down, whoever they
    are) and the independent-sum form would understate nothing but would claim a
    covariance this function does not compute.
    """
    missing = [c for c in clubs if c not in run.consequences]
    if missing:
        raise SensitivityError(f"the run does not price {missing}")
    cells = {c: run.consequences[c]["relegated"] for c in clubs}
    return {"clubs": list(clubs),
            "expected": float(sum(v["p"] for v in cells.values())),
            "se_upper_bound": float(sum(v["se"] for v in cells.values())),
            "per_club": {c: float(v["p"]) for c, v in cells.items()}}


# ==========================================================================
# 4. the report
# ==========================================================================
@dataclass
class Arm:
    """One backend's fit, its book and its run, plus what each cost."""

    name: str
    backend: str
    n_draws: int
    fit_seconds: float
    sim_seconds: float
    sds: dict[str, np.ndarray]
    consequences: dict
    points_sd: dict[str, float]
    trps: float
    promoted: dict
    provenance: dict = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict) -> "Arm":
        """Rebuild an arm from the run's JSON dump — no refit.

        The run costs two fits and two 20,000-season simulations, so the report
        must be rewritable from what the run wrote (a conclusion is a sentence a
        human writes AFTER seeing the numbers). ``sds`` is not carried: the
        report reads the RATIOS, which the dump stores already reduced.
        """
        return cls(
            name=str(payload["name"]), backend=str(payload["backend"]),
            n_draws=int(payload["n_draws"]),
            fit_seconds=float(payload["fit_seconds"]),
            sim_seconds=float(payload["sim_seconds"]), sds={},
            consequences={m: {c: tuple(v) for c, v in row.items()}
                          for m, row in payload["consequences"].items()},
            points_sd={str(k): float(v)
                       for k, v in payload["points_sd"].items()},
            trps=float(payload["trps"]), promoted=dict(payload["promoted"]),
            provenance=dict(payload.get("provenance") or {}))


def _f(value, digits: int = 4) -> str:
    return "n/a" if value is None else f"{float(value):.{digits}f}"


def report_markdown(*, season: str, cutoff: str, cutoff_label: str,
                    mean_field: Arm, richer: Arm, ratios: dict,
                    hyper_ratios: dict, clubs: Sequence[str],
                    realised: dict, n_sims: int, seed: int,
                    conclusion: str, revision_note: str = "") -> str:
    """The D19 report: the ratios, the two sets of numbers, and the honest read.

    ``revision_note`` is a dated paragraph about THIS rewriting of the report —
    what changed in it and what did not — printed under the header. It is empty
    for a report that has never been revised, and it is written by a human for
    the same reason the conclusion is.
    """
    lines: list[str] = []
    add = lines.append

    add("# D19 sensitivity — mean-field ADVI against a NUTS reference")
    add("")
    add(f"One cutoff: **{season} {cutoff_label}** (cutoff `{cutoff}`), a settled "
        "season, so the two arms can also be scored against the table that "
        "actually happened.")
    add("")
    add(f"- production arm: `{mean_field.backend}`, {mean_field.n_draws} draws — "
        "the frozen config, unchanged")
    add(f"- reference arm: `{richer.backend}`, {richer.n_draws} draws "
        "(2 chains) — selected through the config, no `src/` change")
    add(f"- both books simulated through the same engine and ranker at "
        f"N = {n_sims:,}, seed {seed}, S = the arm's own draw count")
    add("")
    add("Monte-Carlo error is not model error. A probability difference smaller "
        "than a couple of the standard errors printed beside it has not been "
        "shown to be a difference. Positional thresholds are not claims about "
        "qualification for any competition, and nothing here is a betting "
        "signal.")
    add("")
    if revision_note.strip():
        add(revision_note.strip())
        add("")

    add("## 1. Posterior dispersion — richer / mean-field")
    add("")
    add("A ratio above 1 means mean-field was tighter than the reference: the "
        "under-dispersion D19 names. `n` is how many quantities the ratio is "
        "taken over (one per club for the team effects, one for a scalar).")
    add("")
    add("| parameter | n | mean | median | min | max | mean-field sd | reference sd |")
    add("|---|---|---|---|---|---|---|---|")
    for name in list(PARAMS) + list(HYPERPARAMS):
        cell = ratios.get(name) or hyper_ratios.get(name)
        if cell is None:
            continue
        add(f"| `{name}` | {cell['n']} | {_f(cell['mean'], 3)} | "
            f"{_f(cell['median'], 3)} | {_f(cell['min'], 3)} | "
            f"{_f(cell['max'], 3)} | {_f(cell['mean_field_sd_mean'], 4)} | "
            f"{_f(cell['richer_sd_mean'], 4)} |")
    add("")
    for name in ("att", "def"):
        cell = ratios.get(name)
        if cell and "min_team" in cell:
            add(f"- `{name}`: tightest relative to the reference at "
                f"**{cell['max_team']}** (ratio {_f(cell['max'], 3)}), widest at "
                f"**{cell['min_team']}** ({_f(cell['min'], 3)}).")
    add("")

    inflation = ess_inflation((richer.provenance or {}).get("convergence"),
                              richer.n_draws)
    factor = inflation["factor"] if inflation["available"] else None

    add("## 2. Consequence probabilities, side by side")
    add("")
    add("Every figure carries its cluster-by-particle Monte-Carlo standard "
        "error. `Δ` is reference minus production, and `Δ ±` is the error on "
        "that DIFFERENCE rather than on either column beside it: "
        "`sqrt(se_mean-field² + se_NUTS²)`.")
    add("")
    if factor is not None:
        add(f"**`NUTS ± (ESS-adj)`** is the NUTS column's error scaled by "
            f"**{factor:.3f}**. A cluster-by-particle error counts the S "
            "posterior draws as S INDEPENDENT clusters, which is right for "
            "mean-field ADVI — i.i.d. draws from one approximation — and wrong "
            "for NUTS, whose draws are a Markov chain. The rule is "
            f"`{inflation['rule']}`, taking the SMALLEST bulk ESS over the "
            "parameter blocks the reference arm's convergence check covered. "
            "The unadjusted NUTS `±` is therefore a lower bound on that arm's "
            "Monte-Carlo error, and the adjusted one is the honest column to "
            "read it by.")
    else:
        add("No ESS-adjusted column for this run: "
            + str(inflation.get("reason", "no factor could be formed")) + ".")
    add("")
    add("Both arms were simulated at the same seed and the same N, so their "
        "Monte-Carlo errors are coupled rather than independent. `Δ ±` ignores "
        "that covariance. Where common random numbers couple the two arms "
        "positively — the usual case — the independent-sum form OVERSTATES the "
        "error of the difference, so it is conservative rather than exact.")
    add("")
    for market in ("champion", "top4", "relegated"):
        add(f"### {market}")
        add("")
        add("| club | mean-field | ± | NUTS | ± | NUTS ± (ESS-adj) | Δ | Δ ± |")
        add("|---|---|---|---|---|---|---|---|")
        rows = []
        for club in clubs:
            p_mf, se_mf = mean_field.consequences[market][club]
            p_r, se_r = richer.consequences[market][club]
            rows.append((p_mf, club, se_mf, p_r, se_r))
        for p_mf, club, se_mf, p_r, se_r in sorted(rows, reverse=True):
            adjusted = "n/a" if factor is None else _f(se_r * factor)
            add(f"| {club} | {_f(p_mf)} | {_f(se_mf)} | {_f(p_r)} | "
                f"{_f(se_r)} | {adjusted} | {p_r - p_mf:+.4f} | "
                f"{_f(float(np.hypot(se_mf, se_r)))} |")
        add("")

    add("## 3. Points-total spread per club")
    add("")
    add("| club | mean-field sd | NUTS sd | ratio |")
    add("|---|---|---|---|")
    for club in clubs:
        a = mean_field.points_sd[club]
        b = richer.points_sd[club]
        add(f"| {club} | {_f(a, 2)} | {_f(b, 2)} | {_f(b / a if a else None, 3)} |")
    add("")

    add("## 4. Promoted clubs and the drop")
    add("")
    add("| arm | E[relegations among promoted] | MC SE (upper bound) | "
        "ESS-adjusted |")
    add("|---|---|---|---|")
    for arm in (mean_field, richer):
        adjusted = ("n/a" if factor is None or arm is not richer
                    else _f(arm.promoted["se_upper_bound"] * factor, 3))
        add(f"| {arm.name} | {_f(arm.promoted['expected'], 3)} | "
            f"{_f(arm.promoted['se_upper_bound'], 3)} | {adjusted} |")
    add("")
    add("The MC SE is the SUM of the per-club relegation standard errors, "
        "deliberately an upper bound: the events are negatively correlated "
        "(three clubs go down, whoever they are) and the independent-sum form "
        "would claim a covariance this report does not compute. The NUTS row "
        "carries the same ESS adjustment as §2; `n/a` on the ADVI row is not a "
        "missing number — i.i.d. draws need no adjustment.")
    add("")
    add(f"Promoted into {season}: "
        + ", ".join(f"`{c}`" for c in mean_field.promoted["clubs"]) + ".")
    add("")

    add("## 5. Score against the realised table, and what each fit cost")
    add("")
    add("| arm | TRPS | fit wall (s) | sim wall (s) | draws |")
    add("|---|---|---|---|---|")
    for arm in (mean_field, richer):
        add(f"| {arm.name} | {_f(arm.trps)} | {_f(arm.fit_seconds, 1)} | "
            f"{_f(arm.sim_seconds, 1)} | {arm.n_draws} |")
    add("")
    conv = (richer.provenance or {}).get("convergence") or {}
    if conv.get("available"):
        flagged = conv.get("flagged") or []
        # What the RECORDED numbers cover — read off the record, not assumed.
        # A run written before the check covered the hyperparameters says so.
        covered = [str(p) for p in (conv.get("params") or PARAMS)]
        uncovered = [p for p in CONVERGENCE_PARAMS if p not in covered]
        add(f"Reference-arm convergence: worst r-hat "
            f"{_f(conv.get('max_rhat'), 4)}, smallest bulk ESS "
            f"{_f(conv.get('min_ess'), 0)} over {len(covered)} parameter "
            f"block(s) ({', '.join(f'`{p}`' for p in covered)})"
            + (f" — **flagged**: {', '.join(str(f['param']) for f in flagged)}."
               " A reference that has not mixed is not a reference, and the "
               "ratios above inherit that doubt."
               if flagged else " — nothing flagged above 1.01."))
        if uncovered:
            add("")
            add("The check this run ran did **not** cover "
                + ", ".join(f"`{p}`" for p in uncovered)
                + ", so the r-hat and ESS above say nothing about how the "
                  "reference mixed on blocks §1 nevertheless reports ratios "
                  "for. The check now covers every quantity the report puts a "
                  "ratio beside, and a re-run reports all "
                + str(len(CONVERGENCE_PARAMS)) + "; these figures are the ones "
                  "this run recorded and are not restated as if they were.")
        add("")
    add("TRPS is the plan's primary league-table score (Ekstrom, Van Eetvelde, "
        "Ley & Brefeld, *Evaluating one-shot tournament predictions*, "
        "arXiv:1912.07364, eq. 2), unweighted at 1/(20·19), scored against the "
        f"realised {season} table through the sim's own ranker "
        f"({realised.get('n_shared', 0)} shared finishing position(s)). ONE "
        "season and ONE cutoff: there is no interval on this difference and "
        "none is implied.")
    add("")

    add("## 6. Conclusion")
    add("")
    add(conclusion)
    add("")

    add("## 7. Provenance")
    add("")
    add("| arm | effective posterior hash | numbers digest | fitted teams | training matches |")
    add("|---|---|---|---|---|")
    for arm in (mean_field, richer):
        prov = arm.provenance or {}
        add(f"| {arm.name} | `{prov.get('effective_posterior_hash', 'n/a')}` | "
            f"`{prov.get('numbers_digest', 'n/a')}` | "
            f"{prov.get('n_teams', 'n/a')} | "
            f"{prov.get('n_training_matches', 'n/a')} |")
    add("")
    cold = (mean_field.provenance or {}).get("cold_start_teams")
    prov_teams = (mean_field.provenance or {}).get("provisional_teams")
    if cold is not None:
        add(f"Cold-start clubs at this cutoff: "
            + (", ".join(f"`{c}`" for c in cold) if cold else "**none**")
            + "; provisional clubs: "
            + (", ".join(f"`{c}`" for c in prov_teams) if prov_teams
               else "**none**")
            + ". Both arms fit the same panel with the same team index, so the "
              "only difference between them is the sampler.")
        add("")
    add("Reproduce with:")
    add("")
    add("```")
    add("PYTHONPATH=src:. python -u -m epl.sensitivity \\")
    add(f"  --season '{season}' --cutoff-label {cutoff_label} "
        f"--n-sims {n_sims} --seed {seed} \\")
    add("  --json-out data/epl/d19/d19_2025_26_MW0.json \\")
    add("  --report-out reports/epl_sim_d19_sensitivity.md "
        "--conclusion-file <file>"
        + (" \\" if revision_note.strip() else ""))
    if revision_note.strip():
        add("  --note-file <file>")
    add("```")
    add("")
    add("The two fits are seeded and deterministic: a re-run reproduces both "
        "TRPS figures and both digests exactly. `--from-json` rewrites this "
        "report from the dump without paying for the fits again.")
    add("")
    return "\n".join(lines) + "\n"


# ==========================================================================
# 5. the run
# ==========================================================================
def promoted_into(matches: pd.DataFrame, season: str) -> list[str]:
    """Clubs in ``season`` that were not in the archive's previous season.

    Read off the archive rather than remembered, so it cannot drift from the
    data the fit saw. A season the archive opens with has no predecessor and
    returns ``[]`` rather than calling every club promoted.
    """
    seasons = sorted(set(matches["season"].astype(str)))
    position = seasons.index(str(season))
    if position == 0:
        return []
    clubs = lambda s: set(matches.loc[matches["season"].astype(str) == s,  # noqa: E731
                                      "home_key"].astype(str))
    return sorted(clubs(str(season)) - clubs(seasons[position - 1]))


def convergence(post, params: Sequence[str] = CONVERGENCE_PARAMS) -> dict:
    """Worst r-hat and smallest bulk ESS across ``params``, or ``None``.

    Only meaningful for a multi-chain sampler: ADVI draws are i.i.d. from one
    approximation and carry a single chain, so r-hat is not defined for them and
    is reported as ``None`` rather than as a reassuring 1.0. A NUTS reference
    that has NOT converged is not a reference, and the report has to say which
    parameters carried the warning rather than quote the ratios as if it had.

    Covers every quantity the report puts a ratio beside, hyperparameters
    included: the default used to be ``PARAMS``, which left ``sigma_att`` and
    ``sigma_def`` — the two largest gaps the D19 run reported — outside the only
    check that could have said whether the reference had mixed on them. The
    blocks actually covered are returned in ``params``, so a report rebuilt from
    a dump can say what the recorded numbers cover rather than assume.
    """
    import arviz as az

    idata = getattr(post, "idata", None)
    if idata is None or int(idata.posterior.sizes.get("chain", 1)) < 2:
        return {"available": False, "reason": "single chain: r-hat undefined",
                "params": [str(p) for p in params]}

    worst_rhat, worst_ess, flagged = 0.0, float("inf"), []
    for name in params:
        variable = "att_raw" if name == "att" else "def_raw" if name == "def" else name
        if variable not in idata.posterior:
            variable = name
        if variable not in idata.posterior:              # pragma: no cover
            continue
        r = float(np.nanmax(np.asarray(az.rhat(idata, var_names=[variable]
                                               )[variable].values)))
        e = float(np.nanmin(np.asarray(az.ess(idata, var_names=[variable]
                                              )[variable].values)))
        worst_rhat = max(worst_rhat, r)
        worst_ess = min(worst_ess, e)
        if r > 1.01:
            flagged.append({"param": name, "rhat": round(r, 4)})
    return {"available": True, "max_rhat": worst_rhat, "min_ess": worst_ess,
            "flagged": flagged, "converged": not flagged,
            "params": [str(p) for p in params]}


def _fit_one(cfg, cutoff, store, anchor, played, *, label: str, verbose: bool):
    """One fit through the frozen stack, timed. Only the config differs."""
    from epl import dcfit, fit as epl_fit, paths

    started = time.perf_counter()
    if verbose:
        print(f"[d19] fitting {label} "
              f"(backend={cfg['model']['inference']['backend']}, "
              f"draws={cfg['model']['inference']['draws']})", flush=True)
    with epl_fit.config_read_once(cfg):
        post, info = dcfit.fit_epl(cutoff, store, anchor, cfg, matches=played,
                                   feature_cache_dir=paths.FIT_CACHE_DIR)
    return post, info, round(time.perf_counter() - started, 2)


def run_d19(*, season: str = D19_SEASON, cutoff_label: str = D19_CUTOFF_LABEL,
            n_sims: int = 20_000, seed: int = 20260611,
            nuts_draws: int = D19_NUTS_DRAWS, nuts_tune: int = D19_NUTS_TUNE,
            matches: pd.DataFrame | None = None, out_path=None,
            verbose: bool = True) -> dict:
    """Fit the cutoff twice, simulate both, and write the D19 report.

    The two arms differ in ONE place — ``inference.backend`` — and in nothing
    else: same archive, same store, same anchor, same panel, same cold-start
    set, same engine, same ranker, same N and same seed. That is what makes the
    difference between them a property of the posterior approximation rather
    than of anything else in the stack.
    """
    from epl import (baseline, fit as epl_fit, freeze, leaguesim, particles,
                     season as season_mod, simmetrics, simretro)
    from epl.anchor import Anchor
    from epl.schema import sort_for_walk_forward

    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cutoff = simretro.cutoff_schedule(matches, season, labels=(cutoff_label,)
                                      )[cutoff_label]
    store = epl_fit.build_store(played)
    anchor = Anchor(played, freeze.frozen_elo_config())
    state = season_mod.archive_season_state(matches, season, cutoff)
    realised = simretro.realised_positions(matches, season)
    promoted = promoted_into(matches, season)

    production = freeze.frozen_wcmodel_config()
    richer_cfg = richer_config(production, backend="nuts", draws=nuts_draws,
                               tune=nuts_tune)
    specs = (("mean-field ADVI", production), ("NUTS", richer_cfg))

    arms: dict[str, Arm] = {}
    raw: dict[str, Any] = {}
    for name, cfg in specs:
        backend = cfg["model"]["inference"]["backend"]
        post, info, fit_seconds = _fit_one(cfg, cutoff, store, anchor, played,
                                           label=name, verbose=verbose)
        book = particles.ParticleBook.from_posterior(post)
        # The comparison rests on both arms carrying the same S; a book that is
        # not the draw count its own config promised breaks that silently.
        check_draw_count(name, cfg, book.n_particles)
        missing = [c for c in state.clubs if c not in book.idx]
        if missing:
            raise SensitivityError(
                f"{name}: the posterior cannot price {missing}; the cold-start "
                "path did not fire and the two arms would not be comparable")
        started = time.perf_counter()
        run = leaguesim.simulate("dc_native", state, book, n_sims, seed,
                                 n_particles=book.n_particles)
        sim_seconds = round(time.perf_counter() - started, 2)
        if verbose:
            print(f"[d19] {name}: S={book.n_particles}, fit {fit_seconds}s, "
                  f"sim {sim_seconds}s", flush=True)

        positions = realised.position_vector(list(run.clubs))
        arms[name] = Arm(
            name=name, backend=backend, n_draws=int(book.n_particles),
            fit_seconds=fit_seconds, sim_seconds=sim_seconds,
            sds=posterior_sds(post, list(PARAMS) + list(HYPERPARAMS)),
            consequences=consequence_table(run),
            points_sd=points_sds(run),
            trps=float(simmetrics.trps(run.matrix, positions)),
            promoted=expected_relegations_among(run, promoted),
            provenance={
                "convergence": convergence(post),
                "effective_posterior_hash": book.content_hash(),
                "numbers_digest": run.digest(),
                "n_teams": int(info.n_teams),
                "n_training_matches": int(info.n_training_matches),
                "cold_start_teams": list(info.cold_start_teams),
                "provisional_teams": list(info.provisional_teams),
                "fitted_teams": list(info.teams),
            })
        raw[name] = {"post_teams": list(post.teams), "run": run}

    mean_field, richer = arms["mean-field ADVI"], arms["NUTS"]
    teams = raw["NUTS"]["post_teams"]
    # By NAME, not by position: the two arms are two fits and each carries its
    # own team index, so a same-size reordering would divide one club's spread
    # by another's without changing a single shape.
    ratios = sd_ratios({k: richer.sds[k] for k in PARAMS},
                       {k: mean_field.sds[k] for k in PARAMS}, teams=teams,
                       mean_field_teams=raw["mean-field ADVI"]["post_teams"])
    hyper = sd_ratios({k: richer.sds[k] for k in HYPERPARAMS},
                      {k: mean_field.sds[k] for k in HYPERPARAMS})
    return {"season": season, "cutoff": str(pd.Timestamp(cutoff).date()),
            "cutoff_label": cutoff_label, "n_sims": int(n_sims),
            "seed": int(seed), "clubs": list(state.clubs),
            "promoted": promoted, "realised": {"n_shared": realised.n_shared},
            "ratios": ratios, "hyper_ratios": hyper,
            "arms": {"mean_field": mean_field, "richer": richer},
            "teams": teams, "out_path": out_path}


def payload_of(got: dict) -> dict:
    """The run reduced to plain JSON — everything the report needs, no arrays.

    The run costs two fits and two 20,000-season simulations. The conclusion is
    a sentence a human writes AFTER reading the numbers, so the report has to be
    rewritable from this dump without paying for the run again.
    """
    return {
        "season": got["season"], "cutoff": got["cutoff"],
        "cutoff_label": got["cutoff_label"], "n_sims": got["n_sims"],
        "seed": got["seed"], "clubs": list(got["clubs"]),
        "promoted": list(got["promoted"]), "realised": dict(got["realised"]),
        "ratios": got["ratios"], "hyper_ratios": got["hyper_ratios"],
        "arms": {key: {
            "name": arm.name, "backend": arm.backend, "n_draws": arm.n_draws,
            "fit_seconds": arm.fit_seconds, "sim_seconds": arm.sim_seconds,
            "trps": arm.trps, "points_sd": arm.points_sd,
            "promoted": arm.promoted,
            "consequences": {m: {c: list(v) for c, v in row.items()}
                             for m, row in arm.consequences.items()},
            "provenance": arm.provenance,
        } for key, arm in got["arms"].items()},
    }


def report_from_payload(payload: dict, *, conclusion: str,
                        revision_note: str = "") -> str:
    """Rebuild the D19 report from :func:`payload_of`'s dump — no refit."""
    return report_markdown(
        season=payload["season"], cutoff=payload["cutoff"],
        cutoff_label=payload["cutoff_label"],
        mean_field=Arm.from_payload(payload["arms"]["mean_field"]),
        richer=Arm.from_payload(payload["arms"]["richer"]),
        ratios=payload["ratios"], hyper_ratios=payload["hyper_ratios"],
        clubs=list(payload["clubs"]), realised=payload.get("realised") or {},
        n_sims=int(payload["n_sims"]), seed=int(payload["seed"]),
        conclusion=conclusion, revision_note=revision_note)


def _cli(argv: Sequence[str] | None = None) -> None:
    """Run D19 and dump the numbers the report is written from."""
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season", default=D19_SEASON)
    ap.add_argument("--cutoff-label", default=D19_CUTOFF_LABEL)
    ap.add_argument("--n-sims", type=int, default=20_000)
    ap.add_argument("--seed", type=int, default=20260611)
    ap.add_argument("--nuts-draws", type=int, default=D19_NUTS_DRAWS)
    ap.add_argument("--nuts-tune", type=int, default=D19_NUTS_TUNE)
    ap.add_argument("--json-out", default=None,
                    help="where to dump the raw numbers (default: none)")
    ap.add_argument("--report-out", default=None,
                    help="where to write the markdown report")
    ap.add_argument("--conclusion-file", default=None,
                    help="a file holding the one-paragraph conclusion; the "
                         "report refuses to invent one")
    ap.add_argument("--from-json", default=None,
                    help="rebuild the report from an earlier run's dump "
                         "instead of refitting")
    ap.add_argument("--note-file", default=None,
                    help="a file holding a dated note about THIS rewriting of "
                         "the report — what changed in it and what did not; "
                         "printed under the header, omitted when absent")
    args = ap.parse_args(list(argv) if argv is not None else None)

    note = "" if not args.note_file else Path(args.note_file).read_text().strip()

    if args.from_json:
        payload = json.loads(Path(args.from_json).read_text())
        if not args.report_out or not args.conclusion_file:
            ap.error("--from-json needs --report-out and --conclusion-file")
        Path(args.report_out).write_text(report_from_payload(
            payload, conclusion=Path(args.conclusion_file).read_text().strip(),
            revision_note=note))
        print(f"[d19] wrote {args.report_out} from {args.from_json}", flush=True)
        return

    got = run_d19(season=args.season, cutoff_label=args.cutoff_label,
                  n_sims=args.n_sims, seed=args.seed,
                  nuts_draws=args.nuts_draws, nuts_tune=args.nuts_tune)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(payload_of(got), indent=1, sort_keys=True) + "\n")
        print(f"[d19] wrote {args.json_out}", flush=True)
    if args.report_out:
        if not args.conclusion_file:
            ap.error("--report-out needs --conclusion-file: the conclusion is "
                     "a sentence a human writes after reading the numbers")
        Path(args.report_out).write_text(report_from_payload(
            payload_of(got),
            conclusion=Path(args.conclusion_file).read_text().strip(),
            revision_note=note))
        print(f"[d19] wrote {args.report_out}", flush=True)
    print(json.dumps({k: got["ratios"][k]["mean"] for k in PARAMS}, indent=1))


if __name__ == "__main__":                                  # pragma: no cover
    _cli()
