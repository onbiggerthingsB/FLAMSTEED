# EPL shots/SOT challenger — preregistration Amendment 1

**Written and owner-approved:** 2026-09-01

**Applies to:** `reports/epl_shots_prereg.md` at commit
`20dbd59ef784a932473aa2768d8f34d418ea00cf`

**Lifecycle point:** prospective amendment before harness freeze `H`; no real
native training prediction, coefficient fit, decision prediction, scoring, or
result artifact existed when this ruling was made

The owner approved this amendment with the following ruling:

> Approve Amendment 1 as proposed, classify the training-goal read as a
> disclosed non-tuning breach, and continue.

Except for the changes below, the original preregistration remains binding.
This amendment is committed as parent-state governance before `H`. The `H`
manifest and verifier must bind both this amendment's exact commit and its
SHA-256; a working-tree copy or an uncommitted ruling is not sufficient.

## A1. Native stored probabilities and model probabilities

The original text combined independent eight-decimal storage with a `1e-12`
row-sum condition. Three independently rounded cells can legitimately miss one
by much more than `1e-12`, so the two representations are now distinguished.

For every training and decision native row:

1. `native_stored` is the three independently stored eight-decimal cells. Each
   cell must be finite, strictly positive, at most one, and exactly equal to
   its own float64 eight-decimal rounding. No cell may be derived by repairing
   another cell.
2. A `native_stored` row is accepted only when
   `abs(sum(native_stored) - 1) <= 1.5e-8`. This tolerance covers the maximum
   three-cell independent-rounding discrepancy; it is not a general
   probability-simplex tolerance.
3. `native_model = native_stored / sum(native_stored)` is computed in float64.
   Only `native_model` enters the residual-logit calculation, including the
   zero-tilt identity check. The native comparator continues to use
   `native_stored` unchanged.
4. Candidate, market, and `native_model` probabilities remain subject to the
   original `1e-12` row-sum tolerance. Candidate rows are the direct softmax
   output. Market rows are the frozen stored market comparator.
5. There is no last-cell repair, proportional repair of `native_stored`, row
   deletion, alternate tolerance, or other fallback. A row outside its
   representation-specific contract is `ProbabilityInvalid`.

Thus a zero coefficient vector reproduces `native_model` within `1e-12`; it is
not required to reproduce a slightly off-simplex `native_stored` vector.

## A2. Optimizer convergence certification

The frozen method, objective, start, penalty, dtype, analytic Jacobian, and
SciPy options remain unchanged: L-BFGS-B from eight zeroes with
`maxiter=10000`, `ftol=1e-12`, and `gtol=1e-10`.

An optimizer result is accepted only when both conditions hold:

1. SciPy reports `success is True`; and
2. the harness independently recomputes the exact frozen objective gradient at
   the returned coefficient vector and obtains
   `max(abs(gradient)) <= 1e-5`.

The independent gradient must agree with the optimizer-reported Jacobian under
`rtol=1e-11, atol=1e-10`, and the independently recomputed objective must agree
with the reported objective under `rtol=1e-13, atol=1e-10`. The receipt
preserves the exact SciPy `success`, `status`, coefficient vector, objective,
Jacobian, `nit`, `nfev`, `njev`, and message, and additionally records the
independent gradient, its maximum absolute component, the `1e-5` acceptance
threshold, whether gradient certification passed, and the strong-convexity
coefficient-distance ceiling
`sqrt(8) * 1e-5 = 2.8284271247461906e-5` in L2 norm.

A finite `success=False` result or a finite result failing the independent
gradient condition is written once as the exact optimizer receipt and then
raises `FitFailure`. Resume must load that receipt and refuse without invoking
the optimizer again. Nonfinite or malformed optimizer output remains an
immediate typed refusal.

This amendment treats SciPy's configured `gtol` as optimizer intent, not as a
claim that every success termination used that condition; L-BFGS-B may report
success through its function-reduction condition. The independent `1e-5`
condition is the experiment's acceptance certificate.

## A3. Disclosed pre-H procedural breach

During development before `H`, an earlier test invoked the full production K
reference and projected the pinned coefficient-training archive columns
`fthg`, `ftag`, and `played`. It did not print, serialize, or report their
values; did not run a native prediction, coefficient fit, candidate prediction,
score, bootstrap, or result calculation; did not open decision-period outcomes
or market values; and did not create a K, prediction, score, evidence, or result
artifact. The call was removed, and the pre-H real-data guard now permits only
the outcome-free identity projection.

The owner classifies this as a disclosed non-tuning procedural breach and rules
that it does not require restarting the experiment. It supplies no permission
to repeat the read before `H`, tune a model, change a bar, or use training
outcomes outside the post-H one-shot training subphase. The disclosure and
owner ruling must be bound into `H` through this amendment's committed bytes.

## A4. Write set and lifecycle effect

This amendment authorizes one additional pre-H governance path:
`reports/epl_shots_prereg_amendment_1.md`. Its governance commit must precede
`H` and contain no harness, coefficient, prediction, score, or result artifact.
The subsequent `H` commit still adds exactly the three audited harness files
and `reports/evidence/epl_shots/harness_manifest.json` from that artifact-free
parent. The later K and decision write sets and the requirement to publish
regardless of sign are unchanged.

Approval of this amendment authorizes completion and freezing of the harness.
It does not authorize the real post-H training run. That run still requires a
separate owner authorization naming the committed `H`.
