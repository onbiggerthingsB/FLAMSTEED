"""Pure analysis helpers for the Phase-1 headroom diagnostic.

Frame-in / value-out: NO I/O, NO network, NO fit, NO odds-file read. Every
function takes synthetic-or-real Python data and returns plain dicts / tuples /
frames, so they unit-test with hand-computed values and compose into the
``scripts/model_market_gap.py`` orchestration without dragging the heavy model
or the Odds API into a test.

The two number-defining primitives are REUSED, never re-derived:
  * RPS is the project-audited ``backtest.baselines.rps`` (the same ranked
    probability score the de-vig selection uses, on the ordered
    ``OUTCOMES = (home, draw, away)``).
  * The market de-vig is ``data.devig.shin`` (Shin 1992; counters the
    favourite-longshot bias), the production de-vig method.

So the headroom numbers are apples-to-apples with the CLV harness and the
backtest engine; these helpers only do the bookkeeping around them (per-row
means, a seeded paired bootstrap, slice labels, reliability binning).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wcmodel.backtest.baselines import rps
from wcmodel.data.devig import shin

#: 1X2 outcome order, shared with ``baselines.rps`` / ``odds_ingest.OUTCOMES``.
_OUTCOMES = ("home", "draw", "away")
#: Letter outcome (``"H"|"D"|"A"``) -> the dict key ``baselines.rps`` expects.
_LETTER = {"H": "home", "D": "draw", "A": "away"}


def _row_rps(triple, outcome_letter: str) -> float:
    """RPS of a ``(home, draw, away)`` probability triple vs an ``"H"|"D"|"A"``
    realised outcome, via the audited ``baselines.rps``."""
    probs = dict(zip(_OUTCOMES, (float(x) for x in triple)))
    return rps(probs, _LETTER[outcome_letter])


def paired_rps(rows: list[dict]) -> dict:
    """Mean model RPS, mean reference RPS, and their delta over paired rows.

    ``rows``: ``[{"p_model": (h, d, a), "p_ref": (h, d, a), "outcome":
    "H"|"D"|"A"}, ...]``. Each row is scored through ``baselines.rps`` (so the
    score is identical to the rest of the pipeline); the helper only averages and
    differences. ``delta = rps_model - rps_ref`` (negative = the model beats the
    reference). An empty ``rows`` yields ``n=0`` and ``nan`` means/delta.
    """
    if not rows:
        return {"n": 0, "rps_model": float("nan"), "rps_ref": float("nan"),
                "delta": float("nan")}
    m = [_row_rps(r["p_model"], r["outcome"]) for r in rows]
    rf = [_row_rps(r["p_ref"], r["outcome"]) for r in rows]
    rps_model = float(np.mean(m))
    rps_ref = float(np.mean(rf))
    return {"n": len(rows), "rps_model": rps_model, "rps_ref": rps_ref,
            "delta": rps_model - rps_ref}


def bootstrap_delta_ci(rows: list[dict], n_boot: int = 10_000, seed: int = 0) -> dict:
    """Seeded paired bootstrap of ``mean(rps_model - rps_ref)`` over matches.

    Resamples MATCHES with replacement (the pairing is preserved — a resample
    draws whole (model, ref) rows), recomputes the mean per-match delta, and
    returns the point delta plus the 2.5 / 97.5 percentile bounds. Deterministic
    for a fixed ``seed`` (``numpy.random.default_rng(seed)``). Empty ``rows`` ->
    all ``nan``.
    """
    if not rows:
        return {"delta": float("nan"), "lo95": float("nan"), "hi95": float("nan")}
    per_row = np.array(
        [_row_rps(r["p_model"], r["outcome"]) - _row_rps(r["p_ref"], r["outcome"])
         for r in rows],
        dtype=float,
    )
    point = float(per_row.mean())
    n = len(per_row)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boot_means = per_row[idx].mean(axis=1)
    lo = float(np.percentile(boot_means, 2.5))
    hi = float(np.percentile(boot_means, 97.5))
    return {"delta": point, "lo95": lo, "hi95": hi}


def assign_slices(match: dict) -> dict:
    """Per-match stratification tags (the |gap| quartile is assigned LATER).

    ``match``: ``{"elo_gap": float, "home_confed": str, "away_confed": str,
    "match_type": str, "neutral": bool, "any_provisional": bool}``. Returns:

      * ``elo_gap_q``    — the RAW ``|elo_gap|`` (quartile cut happens over the
        full frame in :func:`add_gap_quartiles`, never per-row).
      * ``confed_pair``  — one of ``UEFA-UEFA`` / ``UEFA-CONMEBOL`` (order-
        insensitive) / ``cross-confed`` (different confederations, not the named
        pair) / ``intra-other`` (same confederation, not UEFA-UEFA).
      * ``tier``         — the ``match_type`` verbatim.
      * ``neutral`` / ``provisional`` — pass-through (``provisional`` is the OR
        the caller already computed in ``any_provisional``).
    """
    hc, ac = match["home_confed"], match["away_confed"]
    pair = {hc, ac}
    if pair == {"UEFA"}:
        confed_pair = "UEFA-UEFA"
    elif pair == {"UEFA", "CONMEBOL"}:
        confed_pair = "UEFA-CONMEBOL"
    elif hc == ac:
        confed_pair = "intra-other"
    else:
        confed_pair = "cross-confed"
    return {
        "elo_gap_q": abs(float(match["elo_gap"])),
        "confed_pair": confed_pair,
        "tier": match["match_type"],
        "neutral": bool(match["neutral"]),
        "provisional": bool(match["any_provisional"]),
    }


def add_gap_quartiles(df: pd.DataFrame, col: str = "elo_gap") -> pd.DataFrame:
    """Add an ``elo_gap_q`` column = the |``col``| quartile (Q1..Q4) over the frame.

    Quartiles are cut on the WHOLE frame (``pd.qcut`` on ``|elo_gap|``) so the
    bands are comparable across slices — never a per-row decision. Q1 is the
    smallest |gap| band, Q4 the largest. Returns a copy (the input is untouched).
    Falls back to rank-based binning if duplicate edges make ``qcut`` ambiguous.
    """
    out = df.copy()
    absgap = out[col].abs()
    labels = ["Q1", "Q2", "Q3", "Q4"]
    try:
        out["elo_gap_q"] = pd.qcut(absgap, 4, labels=labels)
    except ValueError:
        # Heavily-tied |gap| -> qcut can't form 4 unique edges; rank then cut.
        ranks = absgap.rank(method="first")
        out["elo_gap_q"] = pd.qcut(ranks, 4, labels=labels)
    out["elo_gap_q"] = out["elo_gap_q"].astype(str)
    return out


def reliability_table(probs: list[float], hits: list[bool], bins: int = 10) -> list[dict]:
    """Binned reliability rows: ``[{"bin", "n", "p_mean", "freq"}, ...]``.

    ``probs`` are predicted probabilities in [0, 1]; ``hits[i]`` is whether the
    predicted event occurred for ``probs[i]``. The [0, 1] range is split into
    ``bins`` equal-width buckets (``"0.0-0.1"`` .. ``"0.9-1.0"`` for the default
    10); each row carries the bucket's count, the mean predicted prob, and the
    observed hit frequency. ``sum(n) == len(probs)``. An empty bucket reports
    ``n=0`` with ``nan`` ``p_mean``/``freq`` (no division by zero).
    """
    p = np.asarray(probs, dtype=float)
    h = np.asarray(hits, dtype=bool)
    edges = np.linspace(0.0, 1.0, bins + 1)
    # Right-closed only on the final bin so p == 1.0 lands in the last bucket.
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    table: list[dict] = []
    for b in range(bins):
        sel = idx == b
        n = int(sel.sum())
        lo, hi = edges[b], edges[b + 1]
        label = f"{lo:.1f}-{hi:.1f}"
        if n == 0:
            table.append({"bin": label, "n": 0, "p_mean": float("nan"),
                          "freq": float("nan")})
        else:
            table.append({"bin": label, "n": n,
                          "p_mean": float(p[sel].mean()),
                          "freq": float(h[sel].mean())})
    return table


def market_probs_from_odds(h_odds: float, d_odds: float, a_odds: float) -> tuple:
    """Shin-de-vigged (pH, pD, pA) from a ``(home, draw, away)`` decimal-odds triple.

    Wraps ``data.devig.shin`` (the production de-vig — counters the favourite-
    longshot bias) on the fixed ``(home, draw, away)`` order; the result sums to 1.
    """
    p = shin([float(h_odds), float(d_odds), float(a_odds)])
    return (float(p[0]), float(p[1]), float(p[2]))


def confed_pairing_detail(scored: list[dict], *, seed: int = 0, bins: int = 5,
                          min_n_rel: int = 30) -> list[dict]:
    """Per confederation-pairing detail: paired model-vs-Elo RPS (+ bootstrap CI)
    AND a favorite-prob reliability table for BOTH the model and the Elo reference.

    ``scored`` rows are ``{"slice": {"confed_pair": str, ...}, "row": {p_model,
    p_ref, outcome}}`` exactly as Part B builds them. Reliability is shown only
    where the pairing has ``n >= min_n_rel`` (a reliability curve on a handful of
    matches is noise — below the floor it is an explicit None / coverage gap,
    never a tiny misleading table). Output sorted by n descending.
    """
    _OUT = ("H", "D", "A")
    by_pair: dict[str, list[dict]] = {}
    for sc in scored:
        by_pair.setdefault(str(sc["slice"]["confed_pair"]), []).append(sc["row"])

    def _rel(rows: list[dict], key: str) -> list[dict]:
        probs, hits = [], []
        for r in rows:
            triple = r[key]
            i = max(range(3), key=lambda j: triple[j])
            probs.append(float(triple[i]))
            hits.append(_OUT[i] == r["outcome"])
        return reliability_table(probs, hits, bins=bins)

    out: list[dict] = []
    for pair, rows in by_pair.items():
        pr = paired_rps(rows)
        ci = bootstrap_delta_ci(rows, n_boot=2_000, seed=seed)
        has_rel = pr["n"] >= min_n_rel
        out.append({
            "pair": pair, "n": pr["n"],
            "rps_model": pr["rps_model"], "rps_elo": pr["rps_ref"],
            "delta": ci["delta"], "lo95": ci["lo95"], "hi95": ci["hi95"],
            "rel_model": _rel(rows, "p_model") if has_rel else None,
            "rel_elo": _rel(rows, "p_ref") if has_rel else None,
        })
    out.sort(key=lambda d: -d["n"])
    return out
