"""Unit tests for the headroom analysis helpers (Phase 1 §4).

PURE helpers only — synthetic inputs, NO fits, NO odds file, NO network. Each
test pins one helper's contract:

  * ``paired_rps``           — hand-computed RPS for known triples; means + delta.
  * ``bootstrap_delta_ci``   — seeded paired bootstrap is deterministic.
  * ``assign_slices``        — confed pairing / tier / neutral / provisional cases.
  * ``add_gap_quartiles``    — qcut on |elo_gap| over the full frame -> Q1..Q4.
  * ``reliability_table``    — bin counts + frequencies sum; perfect calibration.
  * ``market_probs_from_odds`` — Shin de-vig sums to 1, orders pH>pD>pA.

The headroom helpers wrap the project-audited ``backtest.baselines.rps`` and
``data.devig.shin`` so the numbers are apples-to-apples with the rest of the
pipeline; the tests assert the WRAPPER's bookkeeping (means, delta, ordering),
not a re-derivation of RPS/Shin.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from wcmodel.backtest import headroom
from wcmodel.backtest.baselines import rps


# --------------------------------------------------------------------------- #
# paired_rps
# --------------------------------------------------------------------------- #
def test_paired_rps_perfect_vs_uniform_known_values():
    """A point-mass forecast on the realised outcome scores RPS 0; the model is a
    perfect (1,0,0)->H call, the ref a flat (1/3,1/3,1/3). Means + delta match a
    hand computation via the audited ``baselines.rps``."""
    rows = [
        {"p_model": (1.0, 0.0, 0.0), "p_ref": (1 / 3, 1 / 3, 1 / 3), "outcome": "H"},
        {"p_model": (0.0, 0.0, 1.0), "p_ref": (1 / 3, 1 / 3, 1 / 3), "outcome": "A"},
    ]
    out = headroom.paired_rps(rows)
    assert out["n"] == 2
    # Perfect point-mass on the outcome -> RPS 0 for both model rows.
    assert out["rps_model"] == pytest.approx(0.0, abs=1e-12)
    # Uniform RPS for an H outcome (and symmetrically for A): cumulative loop.
    uni = {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}
    ref_each = (rps(uni, "home") + rps(uni, "away")) / 2
    assert out["rps_ref"] == pytest.approx(ref_each, abs=1e-12)
    assert out["delta"] == pytest.approx(out["rps_model"] - out["rps_ref"], abs=1e-12)
    # Model strictly better than uniform here -> negative delta.
    assert out["delta"] < 0


def test_paired_rps_matches_baselines_rps_per_row():
    """Each row's RPS equals ``baselines.rps`` on the dict-shaped forecast, and the
    aggregate is the mean (the wrapper only re-shapes + averages)."""
    rows = [
        {"p_model": (0.6, 0.25, 0.15), "p_ref": (0.5, 0.3, 0.2), "outcome": "H"},
        {"p_model": (0.2, 0.3, 0.5), "p_ref": (0.34, 0.33, 0.33), "outcome": "D"},
    ]
    out = headroom.paired_rps(rows)
    o = ("home", "draw", "away")
    letter = {"H": "home", "D": "draw", "A": "away"}
    m = [rps(dict(zip(o, r["p_model"])), letter[r["outcome"]]) for r in rows]
    rf = [rps(dict(zip(o, r["p_ref"])), letter[r["outcome"]]) for r in rows]
    assert out["rps_model"] == pytest.approx(sum(m) / 2)
    assert out["rps_ref"] == pytest.approx(sum(rf) / 2)


# --------------------------------------------------------------------------- #
# bootstrap_delta_ci
# --------------------------------------------------------------------------- #
def test_bootstrap_delta_ci_is_seeded_deterministic():
    """Same seed -> byte-identical CI; the point delta equals ``paired_rps`` delta."""
    rows = [
        {"p_model": (0.6, 0.25, 0.15), "p_ref": (0.5, 0.3, 0.2), "outcome": "H"},
        {"p_model": (0.2, 0.3, 0.5), "p_ref": (0.34, 0.33, 0.33), "outcome": "A"},
        {"p_model": (0.33, 0.34, 0.33), "p_ref": (0.3, 0.4, 0.3), "outcome": "D"},
    ]
    a = headroom.bootstrap_delta_ci(rows, n_boot=2000, seed=0)
    b = headroom.bootstrap_delta_ci(rows, n_boot=2000, seed=0)
    assert a == b
    assert a["lo95"] <= a["delta"] <= a["hi95"]
    assert a["delta"] == pytest.approx(headroom.paired_rps(rows)["delta"])


def test_bootstrap_delta_ci_two_row_fixed():
    """A 2-row paired bootstrap with seed 0 returns a fixed, reproducible interval
    (regression guard on the Generator(seed) wiring)."""
    rows = [
        {"p_model": (1.0, 0.0, 0.0), "p_ref": (1 / 3, 1 / 3, 1 / 3), "outcome": "H"},
        {"p_model": (0.0, 0.0, 1.0), "p_ref": (1 / 3, 1 / 3, 1 / 3), "outcome": "A"},
    ]
    out = headroom.bootstrap_delta_ci(rows, n_boot=5000, seed=0)
    # Both rows have an identical per-row delta, so every resample mean equals it
    # -> a degenerate (zero-width) CI exactly at the point delta.
    point = headroom.paired_rps(rows)["delta"]
    assert out["delta"] == pytest.approx(point)
    assert out["lo95"] == pytest.approx(point)
    assert out["hi95"] == pytest.approx(point)


# --------------------------------------------------------------------------- #
# assign_slices  +  add_gap_quartiles
# --------------------------------------------------------------------------- #
def _match(elo_gap, hc, ac, mt="friendly", neutral=False, prov=False):
    return {
        "elo_gap": elo_gap, "home_confed": hc, "away_confed": ac,
        "match_type": mt, "neutral": neutral, "any_provisional": prov,
    }


def test_assign_slices_confed_pairing_cases():
    """UEFA-UEFA / UEFA-CONMEBOL (either order) / cross-confed / intra-other."""
    assert headroom.assign_slices(_match(50, "UEFA", "UEFA"))["confed_pair"] == "UEFA-UEFA"
    # UEFA-CONMEBOL is order-insensitive.
    assert headroom.assign_slices(_match(50, "UEFA", "CONMEBOL"))["confed_pair"] == "UEFA-CONMEBOL"
    assert headroom.assign_slices(_match(50, "CONMEBOL", "UEFA"))["confed_pair"] == "UEFA-CONMEBOL"
    # CONMEBOL-AFC is a cross-confederation pairing (neither intra nor the named pairs).
    assert headroom.assign_slices(_match(50, "CONMEBOL", "AFC"))["confed_pair"] == "cross-confed"
    # AFC-AFC is intra-other (same confed, not UEFA-UEFA).
    assert headroom.assign_slices(_match(50, "AFC", "AFC"))["confed_pair"] == "intra-other"


def test_assign_slices_passthrough_fields():
    """tier == match_type; |elo_gap| is the raw magnitude; neutral + provisional
    pass through (provisional is the OR already computed by the caller)."""
    s = headroom.assign_slices(_match(-120.0, "AFC", "CAF", mt="wc_finals",
                                       neutral=True, prov=True))
    assert s["tier"] == "wc_finals"
    assert s["elo_gap_q"] == pytest.approx(120.0)   # raw |gap|, quartile assigned later
    assert s["neutral"] is True
    assert s["provisional"] is True
    # provisional False passes through unchanged.
    s2 = headroom.assign_slices(_match(10, "UEFA", "UEFA", prov=False))
    assert s2["provisional"] is False


def test_add_gap_quartiles_labels_over_full_frame():
    """qcut on |elo_gap| over the WHOLE frame -> Q1..Q4 (not per-row)."""
    df = pd.DataFrame({"elo_gap": [-400, -100, -10, 10, 50, 200, 300, 800]})
    out = headroom.add_gap_quartiles(df)
    assert "elo_gap_q" in out.columns
    assert set(out["elo_gap_q"].unique()) <= {"Q1", "Q2", "Q3", "Q4"}
    # Monotone: a larger |gap| never lands in a lower quartile than a smaller one.
    g = out.assign(abs_gap=out["elo_gap"].abs()).sort_values("abs_gap")
    order = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
    ranks = [order[q] for q in g["elo_gap_q"]]
    assert ranks == sorted(ranks)
    # The smallest |gap| is Q1, the largest is Q4.
    assert out.loc[out["elo_gap"].abs().idxmin(), "elo_gap_q"] == "Q1"
    assert out.loc[out["elo_gap"].abs().idxmax(), "elo_gap_q"] == "Q4"


# --------------------------------------------------------------------------- #
# reliability_table
# --------------------------------------------------------------------------- #
def test_reliability_table_counts_sum_and_perfect_calibration():
    """Bin counts sum to N; a perfectly-calibrated synthetic gives freq == p_mean."""
    # For bin b put all 10 probs at the integer-tenths value b/10 (lands inside
    # bin b) and make exactly b of the 10 a hit -> p_mean == freq == b/10 exactly.
    probs, hits = [], []
    for b in range(10):
        val = b / 10.0   # 0.0, 0.1, ... 0.9 -> integer hit count b, freq == val
        for i in range(10):
            probs.append(val)
            hits.append(i < b)
    table = headroom.reliability_table(probs, hits, bins=10)
    assert sum(r["n"] for r in table) == len(probs)
    for r in table:
        if r["n"] > 0:
            assert r["freq"] == pytest.approx(r["p_mean"], abs=1e-9)
    # Bin labels are the 10 decile edges.
    assert table[0]["bin"] == "0.0-0.1"
    assert table[-1]["bin"] == "0.9-1.0"


def test_reliability_table_empty_bins_are_zero():
    """A bin with no probs reports n=0 (and does not blow up on the mean)."""
    table = headroom.reliability_table([0.05, 0.05, 0.95], [False, True, True], bins=10)
    assert sum(r["n"] for r in table) == 3
    first = next(r for r in table if r["bin"] == "0.0-0.1")
    assert first["n"] == 2
    mid = next(r for r in table if r["bin"] == "0.4-0.5")
    assert mid["n"] == 0


# --------------------------------------------------------------------------- #
# market_probs_from_odds
# --------------------------------------------------------------------------- #
def test_market_probs_from_odds_sums_to_one_and_orders():
    """Shin de-vig of (2.0, 3.5, 4.0): probs sum to 1 and order pH > pD > pA."""
    pH, pD, pA = headroom.market_probs_from_odds(2.0, 3.5, 4.0)
    assert pH + pD + pA == pytest.approx(1.0, abs=1e-9)
    assert pH > pD > pA
    assert all(0.0 < p < 1.0 for p in (pH, pD, pA))


def test_market_probs_from_odds_matches_shin():
    """The wrapper is exactly ``data.devig.shin`` on the (home, draw, away) order."""
    from wcmodel.data.devig import shin
    got = headroom.market_probs_from_odds(1.5, 4.2, 7.0)
    want = tuple(shin([1.5, 4.2, 7.0]))
    assert got == pytest.approx(want, abs=1e-12)
    assert not math.isnan(sum(got))


# --------------------------------------------------------------------------- #
# confed_pairing_detail (G1 follow-up: per-pairing model-vs-Elo + reliability)
# --------------------------------------------------------------------------- #
def _sc(pair, p_model, p_ref, outcome):
    return {"slice": {"confed_pair": pair}, "row": {"p_model": p_model, "p_ref": p_ref, "outcome": outcome}}


def test_confed_pairing_detail_groups_and_scores():
    # 3 UEFA-UEFA rows (model sharp + right), 2 cross-confed rows (model wrong-ish).
    scored = [
        _sc("UEFA-UEFA", (0.7, 0.2, 0.1), (0.5, 0.3, 0.2), "H"),
        _sc("UEFA-UEFA", (0.6, 0.25, 0.15), (0.4, 0.3, 0.3), "H"),
        _sc("UEFA-UEFA", (0.2, 0.3, 0.5), (0.3, 0.3, 0.4), "A"),
        _sc("cross-confed", (0.8, 0.15, 0.05), (0.4, 0.3, 0.3), "A"),
        _sc("cross-confed", (0.1, 0.2, 0.7), (0.3, 0.3, 0.4), "H"),
    ]
    out = headroom.confed_pairing_detail(scored, seed=0, bins=5, min_n_rel=3)
    assert [d["pair"] for d in out] == ["UEFA-UEFA", "cross-confed"]   # sorted by n desc
    uu = out[0]
    assert uu["n"] == 3
    # model beat elo on the UEFA-UEFA subset (sharper + right) -> delta < 0
    assert uu["rps_model"] < uu["rps_elo"] and uu["delta"] < 0
    assert uu["lo95"] <= uu["delta"] <= uu["hi95"]
    # reliability present at n >= min_n_rel, absent (None) below it
    assert uu["rel_model"] is not None and uu["rel_elo"] is not None
    assert sum(r["n"] for r in uu["rel_model"]) == 3
    cc = out[1]
    assert cc["n"] == 2 and cc["rel_model"] is None and cc["rel_elo"] is None
    # model badly wrong on cross-confed -> trails elo
    assert cc["delta"] > 0
