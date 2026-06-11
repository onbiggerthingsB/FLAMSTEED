"""P3 v0 k_squad sweep — the pure decision helpers (value-in / value-out).

These implement the PRE-REGISTERED evidence + gates of the k_squad sweep
(``docs/superpowers/specs/2026-06-11-p3v0-sweep-prereg.md`` §3-§4 + ADDENDUM 2)
mechanically, with NO I/O / NO fit / NO network — so the verdict is unit-testable
on synthetic per-match RPS arrays and the orchestration script just feeds them
real numbers.

ADDENDUM 2 (small-n decision framework, locked before any sweep number) replaces
the original §3 ``hi95<0`` G1 verdict with a BOOTSTRAP-SUPPORT-gated rule:

  * Evidence per arm k vs k=0: paired ΔRPS, **bootstrap support** (% of paired
    resamples favouring k>0, i.e. % with delta<0), and per-tournament sign split.
  * G2 — has_squad=0-slice non-regression (UNCHANGED): the chosen k's coverage-
    asymmetry slice RPS does NOT regress vs k=0 beyond noise. The prereg fixes NO
    numeric tolerance, so — as it directs — we use paired-bootstrap CI OVERLAP:
    the slice delta(chosen − k0) must NOT be a CI strictly above 0 (``lo95<=0``).
  * Sanity — over-anchoring gate (house precedent): no held-out match favourite
    above 0.95 in the chosen cell (an absurd >95% single-game favourite = a
    suspected over-anchor, NOT a win).

  Decision rule (ADDENDUM 2, defaults locked now), on the KNEE arm's support:
    - ADOPT      iff support >= 75% AND G2 holds AND sanity holds.
    - NO-LIFT    iff support <  60%  (or a binding gate — G2 / sanity — vetoes an
                 otherwise-high-support knee: the knee is rejected outright).
    - 60–75%     -> MORNING-CALL (the user's call; the harness NEVER adopts here).
  Point estimates alone NEVER adopt — the support threshold is the gate.
"""
from __future__ import annotations

import numpy as np

_K0_TOL = 1e-9

#: ADDENDUM-2 support bands (percent of paired resamples favouring k>0).
SUPPORT_ADOPT = 75.0        # >= this AND gates -> ADOPT
SUPPORT_NOLIFT = 60.0       # < this -> NO-LIFT; [60,75) -> MORNING-CALL
#: Over-anchoring sanity ceiling (house precedent: no >95% single-game favourite).
MAX_FAVORITE_CEILING = 0.95


def paired_bootstrap_delta(
    per_match_a: list[float],
    per_match_b: list[float],
    *,
    seed: int = 0,
    n_boot: int = 2000,
) -> dict:
    """Seeded PAIRED bootstrap CI of ``mean(b) − mean(a)`` over matched per-match
    RPS arrays.

    ``a`` and ``b`` are the SAME matches' RPS under two configs (e.g. k=0 vs the
    candidate k), so we resample the MATCH INDEX once per bootstrap and apply it to
    both — preserving the pairing (the right CI for "did config b beat config a on
    these matches"). Returns ``{delta, lo95, hi95, support}`` where ``support`` is
    the % of resamples with a NEGATIVE bootstrap delta (b — the k>0 arm — better,
    lower RPS); deterministic for a fixed seed; all-nan for empty input.
    """
    a = np.asarray(per_match_a, dtype=float)
    b = np.asarray(per_match_b, dtype=float)
    if a.size == 0 or b.size == 0 or a.size != b.size:
        return {"delta": float("nan"), "lo95": float("nan"),
                "hi95": float("nan"), "support": float("nan")}
    delta = float(b.mean() - a.mean())
    rng = np.random.default_rng(seed)
    n = a.size
    boots = np.empty(n_boot, dtype=float)
    diff = b - a                                    # paired per-match difference
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = float(diff[idx].mean())
    lo95, hi95 = (float(x) for x in np.percentile(boots, [2.5, 97.5]))
    support = float(100.0 * np.mean(boots < 0.0))   # % favouring k>0 (delta<0)
    return {"delta": delta, "lo95": lo95, "hi95": hi95, "support": support}


def bootstrap_support(
    per_match_a: list[float],
    per_match_b: list[float],
    *,
    seed: int = 0,
    n_boot: int = 2000,
) -> float:
    """ADDENDUM-2 evidence #2: the % of paired bootstrap resamples FAVOURING k>0.

    Favouring k>0 means the resampled paired delta ``mean(b) − mean(a) < 0`` (the
    candidate arm ``b`` scores a LOWER — better — RPS than the k=0 arm ``a``).
    Shares the exact resampling of :func:`paired_bootstrap_delta` (same seed /
    n_boot -> identical support). Returns a percent in [0, 100]; NaN for empty
    / mismatched input.
    """
    return paired_bootstrap_delta(
        per_match_a, per_match_b, seed=seed, n_boot=n_boot
    )["support"]


def knee_index(rps_by_k: list[float]) -> int:
    """Index of the knee of the RPS-vs-k curve = argmin RPS (lower = better),
    ties resolved to the SMALLEST k (least anchoring, prereg §3). NaNs are
    skipped; an all-NaN/empty input returns 0."""
    arr = np.asarray(rps_by_k, dtype=float)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return 0
    best_i, best_v = 0, float("inf")
    for i, v in enumerate(arr):
        if np.isnan(v):
            continue
        if v < best_v - _K0_TOL:                    # strictly lower -> new knee
            best_i, best_v = i, v
    return best_i


def evaluate_gates(
    cells: list[dict],
    *,
    seed: int = 0,
    n_boot: int = 2000,
) -> dict:
    """Apply the ADDENDUM-2 support-gated decision rule to the per-k ``cells``.

    Each cell is ``{"k": float, "overall_rps": [per-match...], "slice_rps":
    [per-match... over the has_squad=0-involving matches]}`` plus an OPTIONAL
    ``"max_favorite"`` (the largest single-game favourite probability the cell
    produced on the held-out set, for the over-anchoring sanity gate; absent =
    the gate passes vacuously). There MUST be a k=0 cell (the baseline every gate
    compares against) — else ``ValueError``.

    The verdict is read on the KNEE arm's BOOTSTRAP SUPPORT over k=0 (the % of
    paired resamples favouring k>0):

      * ``support >= 75`` AND G2 holds AND sanity holds  -> ``ADOPT``.
      * ``support <  60``                                -> ``NO-LIFT``.
      * ``60 <= support < 75``                           -> ``MORNING-CALL``
        (the harness never adopts in this band).
      * a binding gate veto (G2 regressed OR sanity tripped) on an otherwise-high
        knee  -> ``NO-LIFT`` (the knee is rejected outright, no morning call).

    Point estimates never adopt — the support threshold is the gate.

    Returns::

        {verdict: "ADOPT"|"NO-LIFT"|"MORNING-CALL", k, knee_k,
         support, g1_pass (legacy hi95<0), g2_pass, sanity_pass, max_favorite,
         overall_delta_vs0: {delta,lo95,hi95,support}, slice_delta_vs0: {...},
         per_k: [{k, overall_mean, slice_mean, n_overall, n_slice, max_favorite}]}
    """
    if not cells:
        raise ValueError("evaluate_gates: no cells")
    cells = sorted(cells, key=lambda c: c["k"])
    k0 = next((c for c in cells if abs(c["k"]) < _K0_TOL), None)
    if k0 is None:
        raise ValueError("evaluate_gates: a k=0 baseline cell is required")

    overall_means = [float(np.mean(c["overall_rps"])) if len(c["overall_rps"]) else float("nan")
                     for c in cells]
    per_k = [
        {
            "k": c["k"],
            "overall_mean": float(np.mean(c["overall_rps"])) if len(c["overall_rps"]) else float("nan"),
            "slice_mean": float(np.mean(c["slice_rps"])) if len(c["slice_rps"]) else float("nan"),
            "n_overall": len(c["overall_rps"]),
            "n_slice": len(c["slice_rps"]),
            "max_favorite": (float(c["max_favorite"]) if c.get("max_favorite") is not None
                             else float("nan")),
        }
        for c in cells
    ]

    knee_i = knee_index(overall_means)
    knee = cells[knee_i]
    knee_k = float(knee["k"])

    overall_delta = paired_bootstrap_delta(
        k0["overall_rps"], knee["overall_rps"], seed=seed, n_boot=n_boot
    )
    support = overall_delta["support"]              # knee arm's support over k=0
    # Legacy G1 (hi95<0) — KEPT as a reported field (the old strict-CI read), but
    # the ADDENDUM-2 verdict is support-gated, NOT this.
    g1_pass = bool(
        abs(knee_k) > _K0_TOL
        and not np.isnan(overall_delta["hi95"])
        and overall_delta["hi95"] < 0.0
    )

    # G2: has_squad=0 slice does not regress (CI not strictly above 0 -> lo95<=0).
    slice_delta = paired_bootstrap_delta(
        k0["slice_rps"], knee["slice_rps"], seed=seed, n_boot=n_boot
    )
    # An empty/degenerate slice (no has_squad=0 matches) -> non-regression vacuously
    # holds (nothing could regress); a present slice must have lo95 <= 0.
    if np.isnan(slice_delta["lo95"]):
        g2_pass = True
    else:
        g2_pass = bool(slice_delta["lo95"] <= 0.0)

    # Sanity (over-anchoring): the knee cell's max held-out favourite <= 0.95.
    # Absent / NaN max_favorite -> vacuously passes (no data to fail on).
    knee_fav = knee.get("max_favorite")
    knee_fav = float(knee_fav) if knee_fav is not None else float("nan")
    sanity_pass = bool(np.isnan(knee_fav) or knee_fav <= MAX_FAVORITE_CEILING)

    # ADDENDUM-2 verdict (support bands + binding-gate vetoes).
    if abs(knee_k) <= _K0_TOL or np.isnan(support) or support < SUPPORT_NOLIFT:
        verdict = "NO-LIFT"
    elif support < SUPPORT_ADOPT:                   # [60, 75)
        verdict = "MORNING-CALL"
    elif g2_pass and sanity_pass:                   # >= 75 AND gates hold
        verdict = "ADOPT"
    else:                                           # >= 75 but a gate vetoed it
        verdict = "NO-LIFT"

    return {
        "verdict": verdict,
        "k": knee_k if verdict == "ADOPT" else None,
        "knee_k": knee_k,
        "support": support,
        "g1_pass": g1_pass,
        "g2_pass": g2_pass,
        "sanity_pass": sanity_pass,
        "max_favorite": knee_fav,
        "overall_delta_vs0": overall_delta,
        "slice_delta_vs0": slice_delta,
        "per_k": per_k,
    }
