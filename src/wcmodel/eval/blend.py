"""E' per-draw blend + the frozen (w, de-vig) selection (OA Plan 2 v2, V6).

The blend arm E' is the PRODUCTION map evaluated at per-draw blended rates::

    lam_blend_d = (1 - w) * lam_model_d + w * lam_book

with ``lam_book`` from V2's :func:`wcmodel.eval.implied.solve_implied_rates`
and ``rho_d`` UNTOUCHED — then per-draw dependence correction, per-draw
renormalization, mean over draws, widening: the same legs, in the same code
(:mod:`wcmodel.model.draw_api`), as every production forecast. The blend
enters at the RATE leg and nothing downstream forks, which is what makes the
endpoints THEOREMS rather than aspirations:

* ``w=0``: ``(1-0)*lam + 0*book`` is an IEEE identity for finite positive
  rates, so the blended per-draw rates ARE the model's and the mean grid is
  BITWISE the incumbent ``production_grid`` (pinned on a real Posterior).
* ``w=1``: the blended rates are ``lam_book`` broadcast across the fixture
  posterior's own rho draws, finalized — EXACTLY the map the solver inverted
  (B2-1 ruling: the solve goes through ``finalize_grid``, widening included,
  with the same fixture context) — so the 1X2 reproduces the de-vigged
  vector within the solver's 1e-6 residual tolerance for EVERY fixture,
  provisional ones included: for those the solved rates already compensate
  for the widening the blend applies.

There is deliberately NO monotonicity-in-w guarantee and no test asserting
one — finding 15 ruled it unsound (the map is nonlinear in the rates); the
pinned properties are endpoints, continuity, normalization and determinism.

``select_w`` is the FROZEN selection procedure (finding 9: no researcher
degrees of freedom left at selection time). It consumes ONLY the V5 dev
ledger — T5-schema rows whose arms are ``dev_``-prefixed, containing one
``dev_blend_{method}_w{w:.2f}`` row per fixture per candidate (V5 evaluates
the blend while it holds each fixture's walk-forward posterior; this module
owns the arm-name convention so writer and selector cannot drift) — and
refuses anything else at runtime: a fixture outside the committed dev
manifest, an arm without the dev_ prefix, a row stamped with a scored pool's
name. Fold spec, verbatim in :data:`FOLD_SPEC` and pinned by test: monthly
chronological folds, burn-in = first 2 LEDGER months — THE single burn-in of
the programme (B2-3 ruling): V5 archives OOF rows for EVERY feasible
dev-slate month and must not pre-trim, so no second burn-in can stack
underneath this one — fold t scored with the candidate chosen on folds < t,
objective = mean canonical RPS (:func:`wcmodel.model.calibration.rps`),
odds-absent fixtures excluded (they carry no signal about w), grid w in
{0.00..1.00} step 0.05, ties to the smaller w (less market dependence) then
the lexicographically smaller de-vig method. The FINAL (w, method) is the
argmin over ALL dev months — the same
rule extended one fold past the slate, which is exactly what deployment is.
The de-vig choice runs through the same protocol over the OA set {shin,
multiplicative} only (finding 13; labels like "basic" are reporting names,
never arm names).

:func:`write_selection_trace` emits the JSON artifact the V8 lock hashes:
selected (w, de-vig), the stacking-arm parameters (from
:mod:`wcmodel.eval.arms`), the full fold trace, the frozen spec text and the
grid table — serialized deterministically so the hash is a function of the
selection, not of the writing session.
"""
from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from wcmodel.eval.dev_slate import SCORED_POOL_WINDOWS
from wcmodel.eval.implied import OA_DEVIG_METHODS
from wcmodel.eval.ledger import LEDGER_DTYPES, load_ledger
from wcmodel.model.calibration import rps
from wcmodel.model.draw_api import (
    PRODUCTION_MAX_GOALS,
    finalize_grid,
    grid_one_x_two,
    mean_grid_over_draws,
    per_draw_rates,
)

#: The frozen selection grid. 21 two-decimal weights; every dev-ledger blend
#: arm carries one of these in its name, so an off-grid candidate cannot even
#: be spelled.
W_GRID = tuple(round(i * 0.05, 2) for i in range(21))

#: First N distinct LEDGER months are training-only. This is THE single
#: burn-in of the programme (B2-3 ruling): V5 archives OOF rows for EVERY
#: feasible dev-slate month into the dev ledger — it must NOT pre-trim its
#: first months — and the selection then reserves the first two LEDGER
#: months as training-only history for the walk-forward. A V5 that trimmed
#: months before archiving would silently compound two burn-ins and shrink
#: the scoreable folds.
SELECTION_BURN_IN_MONTHS = 2

#: The fold spec, verbatim — pinned by test; editing it is a prereg
#: amendment, not a refactor (finding 9). Amended 2026-08-01 (B2-3): the
#: burn-in is stated as a LEDGER property and V5's no-pre-trim contract is
#: explicit, so a double burn-in cannot hide between the two tasks.
FOLD_SPEC = (
    "monthly chronological folds over the dev ledger, which archives "
    "EVERY feasible dev-slate month (V5 must not pre-trim: the ledger "
    "burn-in here is the programme's ONE burn-in); burn-in = first 2 "
    "ledger months (training-only); fold t is scored with the (w, "
    "de-vig) pair chosen by mean canonical RPS on folds < t; rows "
    "without admissible odds are excluded from selection; grid w in "
    "{0.00, 0.05, ..., 1.00}; ties break to the smaller w, then the "
    "lexicographically smaller de-vig method; the final (w, de-vig) is "
    "the argmin over ALL dev months")

BLEND_ARM_PREFIX = "dev_blend_"

_ARM_SUFFIX_RE = re.compile(r"^(?P<method>[a-z_]+)_w(?P<w>\d\.\d\d)$")

_W_TEXTS = tuple(f"{w:.2f}" for w in W_GRID)

_OUTCOMES = ("home", "draw", "away")

#: Selection candidates in the trace's canonical order. The TIE order is
#: (rps, w, method) — smaller w first, method lexicographic — applied at
#: argmin time; this tuple's order only fixes how the grid table reads.
_CANDIDATES = tuple(
    (method, w) for method in sorted(OA_DEVIG_METHODS) for w in W_GRID)

_SCORED_POOL_NAMES = frozenset(pool for pool, _, _ in SCORED_POOL_WINDOWS)


# ----------------------------------------------------------------- the blend


def blend_grid(posterior, fixture_ctx, lam_book, w, *,
               max_goals: int = PRODUCTION_MAX_GOALS) -> np.ndarray:
    """The E' scoreline grid: the production map at per-draw blended rates.

    ``lam_book`` is the ``(lam_h, lam_a)`` pair V2's solver recovered for
    this fixture (its acceptance box is the provenance; here the pair only
    has to be a finite positive rate pair). ``w`` is the market weight in
    [0, 1]. ``rho_d`` comes from the fixture posterior untouched, and the
    downstream legs are the draw_api implementations themselves — never a
    local copy (finding 3).

    A non-Dixon-Coles posterior is refused for the same reason the solver
    refuses one: the production dependence correction is the per-draw rho,
    and ``lam_book`` itself only exists via the DC solve — extending the
    blend to another likelihood is a prereg change, not a fallback.
    """
    if isinstance(w, bool) or not math.isfinite(float(w)) \
            or not 0.0 <= float(w) <= 1.0:
        raise ValueError(
            f"w must be a real number in [0, 1]; got {w!r} (the selection "
            "grid is W_GRID, but the map is defined on the whole interval)")
    w = float(w)
    book = tuple(lam_book)
    if len(book) != 2:
        raise ValueError(
            f"lam_book must be the (lam_h, lam_a) pair from the implied-rate "
            f"solve; got {lam_book!r}")
    lam_bh, lam_ba = (float(v) for v in book)
    if not (math.isfinite(lam_bh) and math.isfinite(lam_ba)
            and lam_bh > 0.0 and lam_ba > 0.0):
        raise ValueError(
            f"lam_book rates must be finite and strictly positive; got "
            f"{lam_book!r}")
    if posterior.likelihood != "dixon_coles":
        raise ValueError(
            "the E' blend rides the production Dixon-Coles map (per-draw "
            f"rho); a {posterior.likelihood!r} posterior carries no rho "
            "draws and no book-rate solve — extending the blend is a prereg "
            "change, not a fallback")

    lh, la = per_draw_rates(posterior, fixture_ctx)
    # This exact form is load-bearing: at w=0.0 it is an IEEE identity
    # ((1-0)*x + 0*b == x for finite positive x, b), which is what makes the
    # w=0 endpoint BITWISE the incumbent rather than merely close.
    blend_h = (1.0 - w) * lh + w * lam_bh
    blend_a = (1.0 - w) * la + w * lam_ba
    grid = mean_grid_over_draws(
        blend_h, blend_a, likelihood="dixon_coles",
        rho=posterior._post("rho"), max_goals=max_goals)
    provisional = (fixture_ctx.home in posterior.provisional_teams) \
        or (fixture_ctx.away in posterior.provisional_teams)
    return finalize_grid(grid, posterior, provisional=provisional)


def blend_one_x_two(posterior, fixture_ctx, lam_book, w, *,
                    max_goals: int = PRODUCTION_MAX_GOALS) -> dict:
    """The E' 1X2 — the production projection of :func:`blend_grid`."""
    return grid_one_x_two(
        blend_grid(posterior, fixture_ctx, lam_book, w, max_goals=max_goals))


# ------------------------------------------------------- the arm-name contract


def blend_arm(method: str, w: float) -> str:
    """The dev-ledger arm name for blend candidate ``(method, w)`` — the
    V5 (writer) <-> V6 (selector) interface, owned here so the two cannot
    drift. ``method`` must be a REAL OA method: 'basic' is the reporting
    label for multiplicative (finding 13) and never names an arm."""
    if method not in OA_DEVIG_METHODS:
        raise ValueError(
            f"de-vig method {method!r} cannot name a blend arm; the OA set "
            f"is exactly {OA_DEVIG_METHODS} ('basic' is a reporting label, "
            "'power' stays a Phase-4 backtest method — finding 13)")
    text = f"{float(w):.2f}"
    if text not in _W_TEXTS or abs(float(w) - float(text)) > 1e-9:
        raise ValueError(
            f"w={w!r} is not on the frozen selection grid "
            "{0.00, 0.05, ..., 1.00}")
    return f"{BLEND_ARM_PREFIX}{method}_w{text}"


def parse_blend_arm(arm: str) -> tuple[str, float] | None:
    """``(method, w)`` for a blend arm; ``None`` for any other arm (somebody
    else's row, not an error). A MALFORMED blend-prefixed arm — bad shape,
    non-OA method, off-grid w — raises: it is a foreign candidate wearing
    the prefix, and scoring it would widen the frozen grid silently."""
    if not arm.startswith(BLEND_ARM_PREFIX):
        return None
    match = _ARM_SUFFIX_RE.match(arm[len(BLEND_ARM_PREFIX):])
    if match is None:
        raise ValueError(
            f"malformed blend arm {arm!r}; expected "
            f"{BLEND_ARM_PREFIX}<method>_w<0.00-1.00>")
    method, text = match.group("method"), match.group("w")
    if method not in OA_DEVIG_METHODS:
        raise ValueError(
            f"blend arm {arm!r} names de-vig method {method!r}, which is not "
            f"OA-choosable; the OA set is exactly {OA_DEVIG_METHODS} "
            "(finding 13)")
    if text not in _W_TEXTS:
        raise ValueError(
            f"blend arm {arm!r} carries w={text}, which is off the frozen "
            "selection grid {0.00, 0.05, ..., 1.00}")
    return method, float(text)


# ----------------------------------------------------------- the dev-only diet


def _manifest_ids(manifest) -> frozenset[str]:
    """The committed dev manifest's match_ids. ``manifest`` is the parsed
    YAML doc or a path to it (``config/oa_dev_manifest.yaml``)."""
    doc = manifest
    if isinstance(manifest, (str, Path)):
        doc = yaml.safe_load(Path(manifest).read_text())
    if not isinstance(doc, Mapping) or "fixtures" not in doc:
        raise ValueError(
            "dev manifest must be the generated document with a 'fixtures' "
            f"list; got {type(doc).__name__}")
    fixtures = doc["fixtures"]
    if not fixtures:
        raise ValueError("dev manifest lists no fixtures")
    try:
        ids = [entry["match_id"] for entry in fixtures]
    except (TypeError, KeyError):
        raise ValueError(
            "every dev-manifest fixture entry must carry a match_id") from None
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate match_id(s) in the dev manifest")
    return frozenset(str(i) for i in ids)


def require_dev_ledger(ledger, manifest) -> pd.DataFrame:
    """Load/validate a ledger and REFUSE anything that is not dev evidence.

    Three independent gates, all runtime (the selection may consume only the
    V5 dev ledger — checked, not assumed): every arm is ``dev_``-prefixed,
    no row is stamped with a scored pool's name, and every fixture is a
    member of the committed dev manifest. ``ledger`` is a path (loaded via
    the validating :func:`wcmodel.eval.ledger.load_ledger`) or an
    already-loaded frame.
    """
    if isinstance(ledger, pd.DataFrame):
        missing = [c for c in LEDGER_DTYPES if c not in ledger.columns]
        if missing:
            raise ValueError(f"ledger frame missing column(s) {missing}")
        frame = ledger
    else:
        frame = load_ledger(ledger)
    foreign = sorted({a for a in frame["arm"].astype(str)
                      if not a.startswith("dev_")})
    if foreign:
        raise ValueError(
            f"non-dev arm(s) {foreign[:5]} in the selection input — dev "
            "ledger rows are arm-prefixed 'dev_', so these rows belong to "
            "another ledger")
    scored = sorted({p for p in frame["pool"].astype(str)
                     if p in _SCORED_POOL_NAMES})
    if scored:
        raise ValueError(
            f"row(s) stamped with scored pool(s) {scored} — development "
            "selection may never consume a scored pool's rows")
    ids = _manifest_ids(manifest)
    stray = sorted(set(frame["fixture_id"].astype(str)) - ids)
    if stray:
        raise ValueError(
            f"fixture(s) {stray[:5]}{' ...' if len(stray) > 5 else ''} are "
            "not in the dev manifest — select_w consumes ONLY manifest "
            "fixtures, refuse rather than filter")
    return frame


# --------------------------------------------------------------- the selection


@dataclass(frozen=True)
class FoldRecord:
    """One scored fold: the candidate chosen on the months BEFORE ``month``
    and its realized mean RPS ON ``month``."""
    month: str
    n_train_fixtures: int
    n_fold_fixtures: int
    w: float
    devig_method: str
    fold_rps: float


@dataclass(frozen=True)
class BlendSelection:
    """The frozen procedure's full output: the deployment choice, the
    walk-forward fold trace behind it, and the grid table (mean canonical
    RPS per candidate over all dev months)."""
    w: float
    devig_method: str
    months: tuple[str, ...]
    folds: tuple[FoldRecord, ...]
    grid_mean_rps: tuple[tuple[str, float, float], ...]
    n_fixtures: int
    n_excluded_no_odds: int


def _covered_fixture_ids(frame: pd.DataFrame) -> frozenset[str]:
    """The EXPECTED covered-fixture set, derived explicitly (B2-2): every
    fixture with ANY non-null ``odds_snapshot_hash`` row in the frame —
    whatever the arm. A covered fixture that then lacks its complete block
    for some consumer is a loud error, never a silent shrink of the
    selection/stacking population."""
    return frozenset(
        frame.loc[frame["odds_snapshot_hash"].notna(), "fixture_id"]
        .astype(str))


def _blend_blocks(frame: pd.DataFrame):
    """Per-fixture candidate blocks from the dev ledger's blend rows:
    ``{fixture_id: {(method, w): (p_home, p_draw, p_away)}}`` plus the
    fixture's date, with the block-shape invariants enforced (V7's
    exact-cardinality stance — a partial block would make the candidate
    means incomparable, so it is an ERROR, never a drop):

    * every EXPECTED covered fixture (any non-null odds_snapshot_hash row in
      the frame, any arm — B2-2) carries blend rows at all: a covered
      fixture with zero blend rows used to vanish from selection silently;
    * every included fixture carries the COMPLETE candidate grid;
    * a fixture whose blend rows all carry a null odds_snapshot_hash is
      odds-absent (the V9 incumbent-fallback convention) — EXCLUDED and
      counted, because such rows carry no signal about w — UNLESS another
      row of the same fixture carries a non-null hash, which makes its
      coverage incoherent across arms: error;
    * a mixed null/non-null block is incoherent — error.
    """
    covered = _covered_fixture_ids(frame)
    blocks: dict[str, dict[tuple[str, float], tuple[float, float, float]]] = {}
    dates: dict[str, set[str]] = {}
    null_flags: dict[str, set[bool]] = {}
    parsed: dict[str, tuple[str, float]] = {}
    for row in frame.itertuples(index=False):
        if row.arm not in parsed:
            candidate = parse_blend_arm(str(row.arm))
            if candidate is None:
                continue
            parsed[row.arm] = candidate
        fid = str(row.fixture_id)
        blocks.setdefault(fid, {})[parsed[row.arm]] = (
            float(row.p_home), float(row.p_draw), float(row.p_away))
        dates.setdefault(fid, set()).add(str(row.date))
        null_flags.setdefault(fid, set()).add(
            bool(pd.isna(row.odds_snapshot_hash)))

    blockless = sorted(covered - set(blocks))
    if blockless:
        raise ValueError(
            f"covered fixture(s) {blockless[:5]}"
            f"{' ...' if len(blockless) > 5 else ''} carry non-null "
            "odds_snapshot_hash rows but NO blend-candidate rows — the "
            "fixture would silently vanish from selection (B2-2); every "
            "covered fixture must carry the complete blend block (error, "
            "never a drop)")

    full = set(_CANDIDATES)
    included: dict[str, str] = {}
    n_excluded = 0
    for fid in sorted(blocks):
        missing = sorted(full - set(blocks[fid]))
        if missing:
            raise ValueError(
                f"fixture {fid!r} has a partial blend-candidate block: "
                f"missing {len(missing)} candidate(s), first {missing[:3]} — "
                "a partial grid makes the candidate means incomparable "
                "(error, never a silent drop)")
        if len(dates[fid]) != 1:
            raise ValueError(
                f"fixture {fid!r} blend rows disagree on date: "
                f"{sorted(dates[fid])}")
        if null_flags[fid] == {True}:
            if fid in covered:
                raise ValueError(
                    f"fixture {fid!r} has an all-null-hash blend block, but "
                    "another of its rows carries a non-null "
                    "odds_snapshot_hash — its coverage is incoherent across "
                    "arms (B2-2): error, never a silent exclusion of a "
                    "covered fixture")
            n_excluded += 1
            continue
        if True in null_flags[fid]:
            raise ValueError(
                f"fixture {fid!r} mixes null and non-null "
                "odds_snapshot_hash across its blend rows — either the odds "
                "existed at the cut or they did not")
        included[fid] = next(iter(dates[fid]))
    return blocks, included, n_excluded


def select_w(ledger, *, outcomes: Mapping[str, str],
             manifest) -> BlendSelection:
    """Run the FROZEN selection (:data:`FOLD_SPEC`) over the V5 dev ledger.

    ``ledger`` is the dev-ledger path or loaded frame; ``outcomes`` maps
    every included fixture_id to its canonical 1X2 label (V5 archives them
    with the OOF rows); ``manifest`` is the committed dev manifest (doc or
    path). A missing outcome is an ERROR — a silently dropped fixture would
    shrink the candidate comparison asymmetrically.
    """
    frame = require_dev_ledger(ledger, manifest)
    blocks, included, n_excluded = _blend_blocks(frame)
    if not included:
        raise ValueError(
            "no odds-covered dev fixtures with blend rows — nothing "
            "identifies w")
    for fid in included:
        if outcomes.get(fid) not in _OUTCOMES:
            raise ValueError(
                f"missing or invalid outcome for dev fixture {fid!r}: "
                f"got {outcomes.get(fid)!r}, need one of {_OUTCOMES}")

    order = sorted(included, key=lambda fid: (included[fid], fid))
    month_arr = np.array([included[fid][:7] for fid in order])
    months = sorted({str(m) for m in month_arr})
    if len(months) < SELECTION_BURN_IN_MONTHS + 1:
        raise ValueError(
            f"only {len(months)} dev month(s) with covered fixtures; the "
            f"frozen spec needs at least {SELECTION_BURN_IN_MONTHS + 1} "
            "(burn-in + one scoreable fold) — refuse rather than degrade")

    scores = np.empty((len(_CANDIDATES), len(order)))
    for j, fid in enumerate(order):
        outcome = outcomes[fid]
        for i, candidate in enumerate(_CANDIDATES):
            p_home, p_draw, p_away = blocks[fid][candidate]
            scores[i, j] = rps(
                {"home": p_home, "draw": p_draw, "away": p_away}, outcome)

    def argmin(mask: np.ndarray) -> tuple[str, float]:
        means = scores[:, mask].mean(axis=1)
        # The frozen tie order: RPS, then smaller w (less market
        # dependence), then lexicographic method. Ties are structural — at
        # w=0 both methods' blends are the same incumbent row.
        best = min(range(len(_CANDIDATES)),
                   key=lambda i: (means[i], _CANDIDATES[i][1],
                                  _CANDIDATES[i][0]))
        return _CANDIDATES[best]

    folds = []
    for fold_month in months[SELECTION_BURN_IN_MONTHS:]:
        train = month_arr < fold_month
        fold_mask = month_arr == fold_month
        method, w = argmin(train)
        fold_rps = float(scores[_CANDIDATES.index((method, w)),
                                fold_mask].mean())
        folds.append(FoldRecord(
            month=fold_month, n_train_fixtures=int(train.sum()),
            n_fold_fixtures=int(fold_mask.sum()), w=w, devig_method=method,
            fold_rps=fold_rps))

    final_method, final_w = argmin(np.ones(len(order), dtype=bool))
    grid_table = tuple(
        (method, w, float(scores[i].mean()))
        for i, (method, w) in enumerate(_CANDIDATES))
    return BlendSelection(
        w=final_w, devig_method=final_method, months=tuple(months),
        folds=tuple(folds), grid_mean_rps=grid_table,
        n_fixtures=len(order), n_excluded_no_odds=n_excluded)


# ------------------------------------------------------------------ the trace


def write_selection_trace(path, selection: BlendSelection, *,
                          stacking: Mapping) -> Path:
    """Write the selection-trace JSON the V8 lock hashes.

    Carries the deployment choice, the stacking arm's parameters (a
    ``StackingFit.trace_payload()`` mapping — required, the lock binds them
    together), the fold trace, the frozen spec text and the grid table.
    Serialization is deterministic (sorted keys, fixed layout) so the
    artifact's sha256 is a function of the selection alone.

    The writer VALIDATES the pair before the lock can hash it (B2-2): the
    stacking payload must be trained under the SELECTED de-vig method, over
    the SAME fold months, with the SAME fixture accounting — both consume
    the same dev ledger under the complete-block enforcement, so any
    disagreement means the two halves of the artifact came from different
    inputs. A missing payload key is an error, not a smaller trace.
    """
    if not isinstance(stacking, Mapping):
        raise ValueError(
            "stacking must be the stacking arm's trace payload mapping — "
            "the V8 lock binds (w, de-vig, stacking params) as ONE artifact")
    required = ("devig_method", "folds", "n_fixtures", "n_excluded_no_odds")
    absent = [k for k in required if k not in stacking]
    if absent:
        raise ValueError(
            f"stacking trace payload is missing key(s) {absent} — pass the "
            "full StackingFit.trace_payload() mapping, never a subset")
    if stacking["devig_method"] != selection.devig_method:
        raise ValueError(
            f"stacking payload was trained under de-vig method "
            f"{stacking['devig_method']!r} but the selection chose "
            f"{selection.devig_method!r} — the trace binds ONE deployment "
            "pair (B2-2)")
    stack_months = [f["month"] for f in stacking["folds"]]
    sel_months = [f.month for f in selection.folds]
    if stack_months != sel_months:
        raise ValueError(
            f"stacking fold months {stack_months} disagree with the "
            f"selection's {sel_months} — both consume the same dev ledger, "
            "so the folds must coincide (B2-2)")
    if int(stacking["n_fixtures"]) != selection.n_fixtures:
        raise ValueError(
            f"stacking n_fixtures {stacking['n_fixtures']} disagrees with "
            f"the selection's {selection.n_fixtures} — same ledger, same "
            "covered population (B2-2)")
    if int(stacking["n_excluded_no_odds"]) != selection.n_excluded_no_odds:
        raise ValueError(
            f"stacking n_excluded_no_odds {stacking['n_excluded_no_odds']} "
            f"disagrees with the selection's "
            f"{selection.n_excluded_no_odds} — same ledger, same odds-absent "
            "set (B2-2)")
    doc = {
        "schema": "oa-selection-trace-v1",
        "fold_spec": FOLD_SPEC,
        "objective": "mean canonical RPS (wcmodel.model.calibration.rps)",
        "burn_in_months": SELECTION_BURN_IN_MONTHS,
        "w_grid": list(W_GRID),
        "devig_methods": list(OA_DEVIG_METHODS),
        "selected": {"w": selection.w, "devig_method": selection.devig_method},
        "months": [str(m) for m in selection.months],
        "folds": [
            {"month": f.month, "w": f.w, "devig_method": f.devig_method,
             "fold_rps": f.fold_rps, "n_train_fixtures": f.n_train_fixtures,
             "n_fold_fixtures": f.n_fold_fixtures}
            for f in selection.folds],
        "grid_mean_rps": [
            {"devig_method": method, "w": w, "mean_rps": mean}
            for method, w, mean in selection.grid_mean_rps],
        "n_fixtures": selection.n_fixtures,
        "n_excluded_no_odds": selection.n_excluded_no_odds,
        "stacking": dict(stacking),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n")
    return path
