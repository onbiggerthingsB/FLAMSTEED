"""Phase-2b host-effect estimator — unit tests (TDD RED→GREEN).

The estimator is PURE (value-in / value-out): given finals-tier host games as
``{rating_home, rating_away, outcome}`` rows it returns the MLE ``k_elo`` (host
advantage as a multiple of the standard Elo home advantage) and a seeded
bootstrap CI. ``k_elo = 1.0`` ≡ "hosts behave like an ordinary home team";
``k_elo = 0.0`` ≡ neutral.

The MANDATORY test here is the estimator-RECOVERY test: synthesise host games
from a KNOWN injected ``k_true`` and assert the estimator recovers it. That
proves the estimator is non-vacuous and unbiased before it is ever pointed at
real history.
"""
import math

import numpy as np
import pytest

from wcmodel.backtest.host_k import (
    bootstrap_k_ci,
    elo_host_probs,
    estimate_k_elo,
    neg_loglik,
)
from wcmodel.data.elo import elo_1x2_baseline

D0 = 0.28          # the pinned config draw_base
HA = 100.0         # the Elo home-advantage unit (config elo.home_advantage)


# --------------------------------------------------------------------------- #
# elo_host_probs — the win-expectancy mapping with a VARIABLE home advantage.
# --------------------------------------------------------------------------- #
def test_elo_host_probs_sums_to_one():
    p = elo_host_probs(1600.0, 1500.0, 0.5, draw_base=D0, home_advantage=HA)
    assert len(p) == 3
    assert abs(sum(p) - 1.0) < 1e-12


def test_elo_host_probs_neutral_symmetric_at_k_zero():
    """Equal ratings + k_elo=0 (no home term) -> a symmetric H/A split, and the
    draw mass peaks at draw_base for an even match (its maximum value)."""
    pH, pD, pA = elo_host_probs(1500.0, 1500.0, 0.0, draw_base=D0, home_advantage=HA)
    assert abs(pH - pA) < 1e-12         # E == 0.5 -> H and A masses equal
    # even match -> draw mass is exactly draw_base (renormalised; the |2E-1| term
    # is 0 here so it is the peak of the draw mass over all rating gaps).
    assert abs(pD - D0) < 1e-12


def test_elo_host_probs_positive_k_shifts_mass_home():
    """A bigger host advantage strictly raises the home win probability."""
    p_lo = elo_host_probs(1500.0, 1500.0, 0.5, draw_base=D0, home_advantage=HA)
    p_hi = elo_host_probs(1500.0, 1500.0, 1.5, draw_base=D0, home_advantage=HA)
    assert p_hi[0] > p_lo[0]            # pH increases with k_elo
    assert p_hi[2] < p_lo[2]            # pA decreases


def test_elo_host_probs_equals_audited_baseline_when_magnitudes_align():
    """Equivalence lock: at k_elo*home_advantage == config home_advantage and the
    non-neutral branch, the re-derived mapping == the audited elo_1x2_baseline.

    (elo_1x2_baseline hard-codes the config home_advantage and a neutral flag; our
    estimator needs a VARIABLE magnitude, so we re-derive the 3-line mapping. They
    must agree where the magnitudes line up — proven here, not assumed.)"""
    rh, ra = 1623.0, 1488.0
    cfg = {"elo": {"home_advantage": HA}, "baseline": {"draw_base": D0}}
    audited = elo_1x2_baseline(rh, ra, neutral=False, config=cfg)   # uses +HA home term
    ours = elo_host_probs(rh, ra, 1.0, draw_base=D0, home_advantage=HA)  # k_elo=1 -> +HA
    assert abs(ours[0] - audited["home"]) < 1e-12
    assert abs(ours[1] - audited["draw"]) < 1e-12
    assert abs(ours[2] - audited["away"]) < 1e-12


# --------------------------------------------------------------------------- #
# neg_loglik — the multinomial NLL of realized H/D/A.
# --------------------------------------------------------------------------- #
def test_neg_loglik_one_row_hand_value():
    row = {"rating_home": 1500.0, "rating_away": 1500.0, "outcome": "H"}
    pH, _, _ = elo_host_probs(1500.0, 1500.0, 0.5, draw_base=D0, home_advantage=HA)
    nll = neg_loglik(0.5, [row], draw_base=D0, home_advantage=HA)
    assert abs(nll - (-math.log(pH))) < 1e-12


def test_neg_loglik_bowl_around_truth():
    """NLL is lower at the truth than away from it on data generated at the truth."""
    rng = np.random.default_rng(7)
    k_true = 1.3
    rows = _synth_rows(rng, n=3000, k_true=k_true)
    here = neg_loglik(k_true, rows, draw_base=D0, home_advantage=HA)
    assert here < neg_loglik(k_true - 0.6, rows, draw_base=D0, home_advantage=HA)
    assert here < neg_loglik(k_true + 0.6, rows, draw_base=D0, home_advantage=HA)


# --------------------------------------------------------------------------- #
# estimate_k_elo — the MLE.   *** the MANDATORY recovery test ***
# --------------------------------------------------------------------------- #
def _synth_rows(rng, *, n, k_true):
    """N synthetic host games: deterministic-ish rating spreads + outcomes drawn
    from elo_host_probs(k_true). The seeded rng makes the whole thing reproducible."""
    rows = []
    for _ in range(n):
        rh = 1500.0 + rng.normal(0.0, 120.0)
        ra = 1500.0 + rng.normal(0.0, 120.0)
        pH, pD, pA = elo_host_probs(rh, ra, k_true, draw_base=D0, home_advantage=HA)
        outcome = rng.choice(["H", "D", "A"], p=[pH, pD, pA])
        rows.append({"rating_home": rh, "rating_away": ra, "outcome": str(outcome)})
    return rows


@pytest.mark.parametrize("k_true", [0.5, 1.4])
def test_estimate_recovers_injected_k(k_true):
    """RECOVERY (mandatory): the MLE recovers a known injected k_true within a tight
    tolerance on a large synthetic host-game sample drawn from that exact k."""
    rng = np.random.default_rng(20260611)
    rows = _synth_rows(rng, n=6000, k_true=k_true)
    k_hat = estimate_k_elo(rows, draw_base=D0, home_advantage=HA)
    assert abs(k_hat - k_true) < 0.12, f"recovered {k_hat} for true {k_true}"


def test_estimate_empty_rows_is_nan():
    assert math.isnan(estimate_k_elo([], draw_base=D0, home_advantage=HA))


# --------------------------------------------------------------------------- #
# bootstrap_k_ci — seeded, deterministic, covers the truth.
# --------------------------------------------------------------------------- #
def test_bootstrap_ci_deterministic_and_brackets_point():
    rng = np.random.default_rng(3)
    rows = _synth_rows(rng, n=2000, k_true=1.2)
    a = bootstrap_k_ci(rows, n_boot=300, seed=0, draw_base=D0, home_advantage=HA)
    b = bootstrap_k_ci(rows, n_boot=300, seed=0, draw_base=D0, home_advantage=HA)
    assert a == b                                   # deterministic for a fixed seed
    assert a["lo95"] <= a["k"] <= a["hi95"]


def test_bootstrap_ci_covers_injected_truth():
    rng = np.random.default_rng(11)
    k_true = 1.4
    rows = _synth_rows(rng, n=4000, k_true=k_true)
    ci = bootstrap_k_ci(rows, n_boot=400, seed=0, draw_base=D0, home_advantage=HA)
    assert ci["lo95"] <= k_true <= ci["hi95"]


def test_bootstrap_empty_rows_all_nan():
    ci = bootstrap_k_ci([], n_boot=50, seed=0, draw_base=D0, home_advantage=HA)
    assert all(math.isnan(ci[k]) for k in ("k", "lo95", "hi95"))
