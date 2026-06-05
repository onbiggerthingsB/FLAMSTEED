"""The anti-overfit gates (spec §2.7, §3) — the load-bearing leakage gate of the
phase + the foresight-RED hard-STOP.

TWO gates:
  * BACKTEST-LAYER LEAKAGE CANARY (``assert_leakage_invariant``) — a post-cutoff
    odds OR result mutation must NOT move any as-of-cutoff price/edge/stake/settled
    P&L. Seeded, so a leakage-free backtest is BIT-IDENTICAL across the mutation;
    the canary asserts ``before == after``. Non-vacuity teeth live in the test (a
    leak WOULD move it). This mirrors the P2 model canary + the P3 tournament
    canary.
  * FORESIGHT-RED HARD-STOP (``check_foresight_red``) — RED ceilings in config
    (``backtest.foresight_red``). Any metric past RED => SUSPECTED LEAK => raise
    ``ForesightRedError`` and STOP. "Treat any too-good result as a suspected bug,
    not a success." Never celebrate a RED-tripping number.

Foresight-RED is a COARSE backstop for GROSS leaks, NOT proof of cleanliness. A
clean foresight pass means nothing on its own — the permutation null (Task 7) and
the leakage canary (this task) are the real catches. RED is a halt-and-inspect
trip, never a green light.
"""
from __future__ import annotations

import numpy as np

from wcmodel.config import load_config


class ForesightRedError(RuntimeError):
    """Raised when a backtest metric crosses a foresight-RED ceiling (suspected leak)."""


def check_foresight_red(summary: dict, *, config: dict | None = None) -> None:
    """STOP if any metric in ``summary`` crosses its RED ceiling.

    Checks (when present): ``roi_roi`` vs ``foresight_red.roi``,
    ``clv_beat_close_rate`` vs ``beat_close_rate``, ``clv_avg_clv`` vs ``avg_clv``.
    Raises ``ForesightRedError`` naming every tripped metric; returns ``None`` when
    all are plausible.
    """
    red = (config or load_config())["backtest"]["foresight_red"]
    tripped = []
    checks = [
        ("roi_roi", "roi"),
        ("clv_beat_close_rate", "beat_close_rate"),
        ("clv_avg_clv", "avg_clv"),
    ]
    for metric_key, red_key in checks:
        val = summary.get(metric_key)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        if val > red[red_key]:
            tripped.append(f"{metric_key}={val:.4f} > RED {red_key}={red[red_key]}")
    if tripped:
        raise ForesightRedError(
            "foresight-RED tripped (SUSPECTED LEAK — STOP, do not celebrate): "
            + "; ".join(tripped)
        )


def leaked_feature_metrics(*, seed: int = 0) -> dict:
    """Synthetic metrics from a DELIBERATELY LEAKED model (sees the realised label).

    Stands in for "a synthetic leaked feature": a model fed the outcome bets the
    right side every time at a generous entry, so ROI + beat-close + CLV all blow
    past their RED ceilings. Used by the foresight-RED trip test to prove the gate
    fires; this is NOT a real backtest path (no store read, deterministic)."""
    rng = np.random.default_rng(seed)
    # ~100% hit at avg odds 2.0 -> ROI ~ +100%; beat-close ~100%; CLV large.
    n = 200
    pnls = np.where(rng.random(n) < 0.99, 1.0, -1.0)   # near-perfect
    return {
        "roi_roi": float(np.mean(pnls)),
        "clv_beat_close_rate": 0.99,
        "clv_avg_clv": 0.20,
    }


def assert_leakage_invariant(run_fn, mutate_fn, *, seed: int = 0) -> None:
    """Backtest-layer leakage canary: a post-cutoff mutation must not move the run.

    ``run_fn()`` returns a ``Metrics`` (seeded); ``mutate_fn()`` mutates a
    POST-cutoff odds or result in place. Asserts the per-bet ledger + summary are
    IDENTICAL before and after the mutation. Raises ``AssertionError`` (a real
    leak) otherwise. The non-vacuity teeth (the mutation fires; a leaky variant
    WOULD differ) are asserted in the calling test.
    """
    before = run_fn()
    mutate_fn()
    after = run_fn()
    assert before.summary == after.summary, (
        "BACKTEST LEAKAGE: a post-cutoff mutation moved the as-of-cutoff summary "
        "-> the backtest is peeking past the cutoff. STOP and investigate."
    )
    assert before.bets == after.bets, (
        "BACKTEST LEAKAGE: a post-cutoff mutation moved the per-bet ledger "
        "(price/edge/stake/P&L) -> look-ahead. STOP and investigate."
    )
