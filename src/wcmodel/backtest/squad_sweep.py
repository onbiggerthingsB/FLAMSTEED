"""P3 v0 k_squad sweep — the pure decision helpers (value-in / value-out).

These implement the two PRE-REGISTERED gates of the k_squad sweep
(``docs/superpowers/specs/2026-06-11-p3v0-sweep-prereg.md`` §3-§4) mechanically,
with NO I/O / NO fit / NO network — so the verdict is unit-testable on synthetic
per-match RPS arrays and the orchestration script just feeds them real numbers.

The gates (evaluated against the k=0 cell):
  G1 — knee-beats-zero: the adopted k is the KNEE of the held-out 1X2 RPS curve
       (argmin RPS, ties to the smallest k) AND its overall RPS STRICTLY beats
       k=0 (the paired-bootstrap delta vs k=0 has its 95% upper bound < 0).
  G2 — has_squad=0-slice non-regression: the adopted k's coverage-asymmetry slice
       RPS does NOT regress vs k=0 beyond noise. The prereg fixes NO numeric
       tolerance for this slice, so — as the prereg explicitly directs — we use
       paired-bootstrap CI OVERLAP: the slice delta(chosen − k0) must NOT be a CI
       strictly above 0 (i.e. ``lo95 <= 0``). This implementation choice is stated
       in the sweep report.

Adoption (prereg §3): ADOPT k=<knee> iff G1 AND G2 both pass; else NO-LIFT.
"""
from __future__ import annotations

import numpy as np

_K0_TOL = 1e-9


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
    these matches"). Returns ``{delta, lo95, hi95}``; deterministic for a fixed
    seed; all-nan for empty input.
    """
    a = np.asarray(per_match_a, dtype=float)
    b = np.asarray(per_match_b, dtype=float)
    if a.size == 0 or b.size == 0 or a.size != b.size:
        return {"delta": float("nan"), "lo95": float("nan"), "hi95": float("nan")}
    delta = float(b.mean() - a.mean())
    rng = np.random.default_rng(seed)
    n = a.size
    boots = np.empty(n_boot, dtype=float)
    diff = b - a                                    # paired per-match difference
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = float(diff[idx].mean())
    lo95, hi95 = (float(x) for x in np.percentile(boots, [2.5, 97.5]))
    return {"delta": delta, "lo95": lo95, "hi95": hi95}


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
    """Apply the two pre-registered gates to the per-k ``cells`` -> a verdict dict.

    Each cell is ``{"k": float, "overall_rps": [per-match...], "slice_rps":
    [per-match... over the has_squad=0-involving matches]}``. There MUST be a k=0
    cell (the baseline every gate compares against) — else ``ValueError``.

    Returns::

        {verdict: "ADOPT"|"NO-LIFT", k, knee_k,
         g1_pass, g2_pass,
         overall_delta_vs0: {delta,lo95,hi95}, slice_delta_vs0: {...},
         per_k: [{k, overall_mean, slice_mean, n_overall, n_slice}, ...]}
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
        }
        for c in cells
    ]

    knee_i = knee_index(overall_means)
    knee = cells[knee_i]
    knee_k = float(knee["k"])

    # G1: knee is not k=0 AND strictly beats k=0 (paired-bootstrap hi95 < 0).
    overall_delta = paired_bootstrap_delta(
        k0["overall_rps"], knee["overall_rps"], seed=seed, n_boot=n_boot
    )
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

    verdict = "ADOPT" if (g1_pass and g2_pass) else "NO-LIFT"
    return {
        "verdict": verdict,
        "k": knee_k if verdict == "ADOPT" else None,
        "knee_k": knee_k,
        "g1_pass": g1_pass,
        "g2_pass": g2_pass,
        "overall_delta_vs0": overall_delta,
        "slice_delta_vs0": slice_delta,
        "per_k": per_k,
    }
