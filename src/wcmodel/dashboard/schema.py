"""Serializer-side guards: the data-layer enforcement of the spec's no-naked-numbers,
coherence, coverage-gap, and no-imputation discipline. An artifact that violates these
must not be written (build.py gates on them)."""
from __future__ import annotations

import math

# The cumulative knockout ladder, shallow -> deep. Each must be >= the next. Mirrors the
# sim's documented cumulative ladder champion <= reach_final <= reach_sf <= reach_qf <=
# reach_r16 <= advance_from_group, so EVERY rung team_progression emits is gated here
# (reach_r16 included — omitting it silently skipped a real coherence rung).
_LADDER = ["advance_from_group", "reach_r16", "reach_qf", "reach_sf", "reach_final", "champion"]


def validate_progression_coherence(markets: dict, *, tol: float = 1e-9) -> None:
    """Raise if the cumulative ladder is non-monotone (deeper stage more likely than a
    shallower one is impossible). Only checks the markets present."""
    present = [m for m in _LADDER if m in markets]
    for shallower, deeper in zip(present, present[1:]):
        if markets[deeper] > markets[shallower] + tol:
            raise ValueError(
                f"progression coherence violated: {deeper}={markets[deeper]} > "
                f"{shallower}={markets[shallower]} (a deeper stage cannot exceed a shallower one)"
            )


def _finite_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _prob_in_unit(x) -> bool:
    """A finite probability in [0, 1] (the no-naked / coherence range check)."""
    return _finite_number(x) and 0.0 <= x <= 1.0


def _check_most_likely_prob(ml: dict, *, where: str) -> None:
    """SHARED (FIX C + FIX D): the headline ``most_likely.prob`` must be a finite number in
    [0, 1] — never naked (missing) and never out-of-range/NaN. ``_write``'s ``sanitize_nans``
    turns a NaN -> null BEFORE ``allow_nan=False``, so a NaN headline is MASKED to null on
    disk; this gate is the only real STOP."""
    if not isinstance(ml, dict) or "prob" not in ml:
        raise ValueError(f"{where}: most_likely score is naked (no prob)")
    if not _prob_in_unit(ml["prob"]):
        raise ValueError(f"{where}: most_likely.prob {ml['prob']!r} is not a finite probability in [0,1]")


def _check_shortlist_probs(shortlist, *, where: str) -> None:
    """SHARED: every shortlist entry is a ``{home_goals, away_goals, prob}`` with ``prob`` a
    finite probability in [0,1] — never a naked entry (missing prob) and never out-of-range/NaN.
    A scoreline shortlist (the spec-D3 "predicted score = shortlist, never a lone score") is the
    distribution-as-uncertainty, so there is NO monotonicity / sum constraint here — only the
    per-entry prob bound. This is the IDENTICAL discipline ``gate_fixture_forecast`` applies to
    the full forecast's shortlist; ``gate_schedule`` reuses it for the row's projected top-3."""
    if not isinstance(shortlist, (list, tuple)):
        raise ValueError(f"{where}: shortlist must be a list of scoreline entries")
    for entry in shortlist:
        if not isinstance(entry, dict) or "prob" not in entry:
            raise ValueError(f"{where}: shortlist entry is naked (no prob): {entry!r}")
        if not _prob_in_unit(entry["prob"]):
            raise ValueError(
                f"{where}: shortlist prob {entry['prob']!r} is not a finite probability in [0,1]")


def _check_1x2_distribution(oxt: dict, *, where: str, tol: float = 0.05) -> None:
    """SHARED (FIX C + FIX D): the 1X2 split must show ALL THREE outcomes (never a lone
    score), each a finite probability in [0,1], AND sum to ~1 — a coherent all-three
    distribution. (No per-outcome CI — the distribution IS the uncertainty, per the approved
    design.)"""
    if not isinstance(oxt, dict) or not all(k in oxt for k in ("home", "draw", "away")):
        raise ValueError(f"{where}: 1x2 must show all three outcomes, never a lone score")
    vals = [oxt["home"], oxt["draw"], oxt["away"]]
    if not all(_prob_in_unit(v) for v in vals):
        raise ValueError(f"{where}: each 1x2 outcome must be a finite probability in [0,1] (got {vals!r})")
    if abs(sum(vals) - 1.0) > tol:
        raise ValueError(f"{where}: 1x2 outcomes must sum to ~1 (the distribution is the uncertainty); got {sum(vals)!r}")


def _check_cover_pair(cov: dict, *, where: str, tol: float = 0.05) -> None:
    """SHARED: the ±1.5 goal-line cover pair (Derived from the scoreline grid) must show BOTH
    sides — ``{home, away}`` — each a finite probability in [0,1], AND sum to ~1 (a half-goal
    line has no push, so the two cover outcomes partition the space). This is the IDENTICAL
    all-sides-present + value + sum~1 discipline ``_check_1x2_distribution`` applies; the cover
    distribution IS its own uncertainty (no per-side CI), exactly like the 1X2 and shortlist."""
    if not isinstance(cov, dict) or not all(k in cov for k in ("home", "away")):
        raise ValueError(f"{where}: cover must show both sides (home/away), never a lone side")
    vals = [cov["home"], cov["away"]]
    if not all(_prob_in_unit(v) for v in vals):
        raise ValueError(f"{where}: each cover side must be a finite probability in [0,1] (got {vals!r})")
    if abs(sum(vals) - 1.0) > tol:
        raise ValueError(f"{where}: cover pair must sum to ~1 (±1.5 is a half line, no push); got {sum(vals)!r}")


def assert_uncertainty_companion(node: dict) -> None:
    """Every emitted probability must carry a REAL uncertainty companion — a finite ``se``
    (an MC SE; 0.0 is valid for a certain p in {0,1}) or a ``ci`` of two finite bounds.
    A missing OR degenerate (NaN/inf/empty/wrong-length) companion is a naked number."""
    # An explicit null value is NOT a naked number. A legitimate coverage_gap ALWAYS
    # carries value=None, so the null-value exemption covers it. We deliberately do NOT
    # exempt on the coverage_gap flag alone: a contradictory {coverage_gap: True, value: 0.1}
    # carries a real number that must still be companion-checked (it would otherwise slip).
    if "value" not in node:
        return
    if node.get("value") is None:
        return
    se, ci = node.get("se"), node.get("ci")
    se_ok = _finite_number(se)
    ci_ok = (isinstance(ci, (list, tuple)) and len(ci) == 2
             and all(_finite_number(b) for b in ci))
    if not (se_ok or ci_ok):
        raise ValueError(
            f"naked number: {node!r} has a value but no REAL uncertainty companion "
            "(need a finite se or a 2-bound finite ci) — the no-naked-numbers rule applies"
        )


def coverage_gap(reason: str) -> dict:
    """An explicit coverage gap (thin/absent data) — NEVER a fabricated number."""
    return {"coverage_gap": True, "reason": reason, "value": None}


def no_impute(x):
    """NULL-safe: a NaN/None becomes JSON ``null``, never 0 (no imputation, ever)."""
    if x is None:
        return None
    try:
        return None if math.isnan(float(x)) else float(x)
    except (TypeError, ValueError):
        return None


def gate_fixture_forecast(f: dict, *, tol: float = 0.05) -> None:
    """A fixture forecast's uncertainty IS its scoreline distribution: the full grid must be
    present and sum to ~1, the most-likely score must carry its prob, and the 1X2 must show
    ALL THREE outcomes (never a lone score). (No per-outcome CI — the distribution is the
    uncertainty, per the approved design.)"""
    grid = f.get("grid")
    if not isinstance(grid, (list, tuple)) or not grid:
        raise ValueError("fixture forecast: grid must be a non-empty list of rows")
    if not all(isinstance(row, (list, tuple)) and row for row in grid):
        raise ValueError("fixture forecast: grid rows must be non-empty lists")
    width = len(grid[0])
    if not all(len(row) == width for row in grid):
        raise ValueError("fixture forecast: grid must be rectangular (all rows equal length)")
    if not all(_finite_number(c) and 0.0 <= c <= 1.0 for row in grid for c in row):
        raise ValueError("fixture forecast: every grid cell must be a probability in [0, 1]")
    total = sum(sum(row) for row in grid)
    if abs(total - 1.0) > tol:
        raise ValueError("fixture forecast: grid does not sum to ~1 (the scoreline distribution is the uncertainty)")
    # The headline most-likely score must carry a finite prob in [0,1] (value-checked, not
    # merely key-present — a NaN headline is masked to null on disk, so this is the only STOP).
    _check_most_likely_prob(f.get("most_likely") or {}, where="fixture forecast")
    # The 1X2 must be a coherent all-three distribution: each outcome finite in [0,1], sum ~1.
    _check_1x2_distribution(f.get("one_x_two") or {}, where="fixture forecast", tol=tol)
    # When a shortlist is present, every entry's prob is finite in [0,1] (no monotonicity).
    shortlist = f.get("shortlist")
    if shortlist is not None:
        _check_shortlist_probs(shortlist, where="fixture forecast")
    # The ±1.5 cover pair (Derived from the grid) — when present, both sides finite in [0,1]
    # and sum ~1. Optional so a pre-feature forecast (no cover key) still gates clean.
    cover = f.get("cover")
    if cover is not None:
        _check_cover_pair(cover, where="fixture forecast", tol=tol)


def _is_gap(node) -> bool:
    """A coverage_gap node (or an explicit null/None) is an honest absence, EXEMPT from the
    value checks — a gap is never a naked number."""
    return node is None or (isinstance(node, dict) and node.get("coverage_gap"))


def _check_edge_node(edge: dict, *, where: str) -> None:
    """FIX D: a real (non-gap) edge node is a DERIVED model-vs-market comparison — finite-
    sanity only, NO uncertainty companion (edges are derived comparisons by design):
    ``edge``/``stake_signal`` finite numbers, ``entry_odds`` a finite decimal-odds number
    > 1.0 (a decimal price below evens is impossible). Fields that may legitimately be absent
    (e.g. a non-staked edge) are checked only when present."""
    if _is_gap(edge):
        return
    if not isinstance(edge, dict):
        raise ValueError(f"{where}: edge node must be a dict or a coverage_gap")
    for k in ("edge", "stake_signal"):
        if k in edge and not _finite_number(edge[k]):
            raise ValueError(f"{where}: edge.{k} {edge[k]!r} must be a finite number")
    if "entry_odds" in edge:
        eo = edge["entry_odds"]
        if not _finite_number(eo) or eo <= 1.0:
            raise ValueError(f"{where}: edge.entry_odds {eo!r} must be a finite decimal-odds number > 1.0")


def _check_occupants(occ, *, where: str) -> None:
    """FIX D: a KO row's occupant-list (or a coverage_gap) — each occupant carries
    ``{team, prob, se}`` with ``prob`` finite in [0,1] and a finite ``se`` (NO naked occupant
    prob). A coverage_gap occupant-list is an honest absence (exempt)."""
    if _is_gap(occ):
        return
    if not isinstance(occ, (list, tuple)):
        raise ValueError(f"{where}: occupants must be a list of occupant nodes or a coverage_gap")
    for o in occ:
        if not isinstance(o, dict) or "prob" not in o:
            raise ValueError(f"{where}: occupant is naked (no prob): {o!r}")
        if not _prob_in_unit(o["prob"]):
            raise ValueError(f"{where}: occupant prob {o['prob']!r} is not a finite probability in [0,1]")
        if not _finite_number(o.get("se")):
            raise ValueError(
                f"{where}: occupant {o.get('team')!r} carries a prob but no finite se — a naked "
                "occupant prob (gap the occupant-list instead of emitting it)")


def gate_schedule(payload: dict, *, tol: float = 0.05) -> None:
    """FIX D: the HOMEPAGE (``schedule.json`` = ``{"group": [...], "knockout": [...]}``) is a
    true STOP — no naked number escapes. For each GROUP row's ``forecast_summary`` (when not a
    coverage_gap): value-check the headline prob + the 1X2 triple + the top-3 scoreline
    SHORTLIST (the SHARED helpers FIX C uses, so C and D agree — every shortlist entry's prob
    is a finite probability in [0,1], spec D3 "predicted score = shortlist, never a lone score"
    projected into the row). For each row's ``edge`` node (when not a gap): finite-sanity only
    (edges are DERIVED comparisons — NO uncertainty companion). For each KO row's
    ``home_occupants``/``away_occupants`` (when not a gap): every occupant carries
    ``{team, prob, se}`` with prob finite in [0,1] and a finite se (NO naked occupant prob)."""
    for row in payload.get("group", []) or []:
        fs = row.get("forecast_summary")
        if not _is_gap(fs):
            _check_most_likely_prob((fs or {}).get("most_likely") or {}, where="schedule group row")
            _check_1x2_distribution((fs or {}).get("one_x_two") or {}, where="schedule group row", tol=tol)
            # The row's projected top-3 shortlist: every entry's prob finite in [0,1] (same
            # discipline as the fixture gate; STOP on a bad shortlist prob). When present.
            shortlist = (fs or {}).get("shortlist")
            if shortlist is not None:
                _check_shortlist_probs(shortlist, where="schedule group row")
            # The ±1.5 cover pair projected into the row (Derived from the grid). When present:
            # both sides finite in [0,1], sum ~1. Optional (a pre-feature row has no cover key).
            cover = (fs or {}).get("cover")
            if cover is not None:
                _check_cover_pair(cover, where="schedule group row", tol=tol)
            # GHOST LINE: the OPTIONAL de-vigged ENTRY market 1X2 (a DERIVED comparison ghosted
            # into the win-bar). When present it must be a coherent all-three sum~1 distribution
            # — value-checked like the model 1X2 — but it carries NO uncertainty companion (a
            # derived comparison, like the edge, by design). Absent -> nothing to check.
            market = (fs or {}).get("market_1x2")
            if market is not None:
                _check_1x2_distribution(market, where="schedule group row market_1x2 (ghost line)", tol=tol)
        _check_edge_node(row.get("edge"), where="schedule group row")
    for row in payload.get("knockout", []) or []:
        _check_occupants(row.get("home_occupants"), where="schedule KO row (home)")
        _check_occupants(row.get("away_occupants"), where="schedule KO row (away)")


def gate_standings(payload: dict, *, tol: float = 1e-6) -> None:
    """Item A: the predicted GROUP STANDINGS artifact (``{group: [team_row, ...]}``) is a true
    STOP — no naked number, and the qualification partition is coherent. For each team row:

      * every ``{value, se}`` envelope (exp_points/exp_gd/p_top2/p_third_qualify/p_eliminated/
        p_advance) carries its uncertainty companion (``assert_uncertainty_companion``) — a
        value with no finite se is a naked number and RAISES;
      * each PROBABILITY field is a finite probability in [0,1] when present (exp_points/exp_gd
        are NOT probabilities — they are unbounded counts/differences — so they are companion-
        checked but NOT [0,1]-bounded);
      * the 3-way fate partition is coherent: when all three of P(top2), P(3rd qualify),
        P(eliminated) are present they sum to ~1 (every sim draw lands in exactly one fate),
        and P(advance) == P(top2) + P(3rd qualify) (~tol);
      * ``fate`` (when present) is one of the three known fate labels.

    A null (value=None) field is an honest absence (exempt from the value/sum checks), never a
    naked number. ``standings_view`` produces null-safe rows, so this gate holds on real data
    and STOPS a regression that emitted a naked or incoherent standings row."""
    _PROB_FIELDS = ("p_top2", "p_third_qualify", "p_eliminated", "p_advance")
    _FATES = {"advance", "possible_third", "eliminated"}
    for group, rows in (payload or {}).items():
        if not isinstance(rows, (list, tuple)):
            raise ValueError(f"standings group {group!r}: rows must be a list of team rows")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"standings group {group!r}: a team row must be a dict")
            # No-naked: every {value, se} envelope carries a real uncertainty companion.
            for field in ("exp_points", "exp_gd", *_PROB_FIELDS):
                cell = row.get(field)
                if isinstance(cell, dict) and "value" in cell:
                    assert_uncertainty_companion(cell)
            # Each PROBABILITY field is a finite probability in [0,1] when present.
            for field in _PROB_FIELDS:
                v = (row.get(field) or {}).get("value")
                if v is not None and not _prob_in_unit(v):
                    raise ValueError(
                        f"standings {group!r}/{row.get('team')!r}: {field}={v!r} is not a "
                        "finite probability in [0,1]")
            # Coherent 3-way partition (sum ~1) + the advance identity, when all present.
            top2 = (row.get("p_top2") or {}).get("value")
            q3 = (row.get("p_third_qualify") or {}).get("value")
            elim = (row.get("p_eliminated") or {}).get("value")
            adv = (row.get("p_advance") or {}).get("value")
            if None not in (top2, q3, elim):
                if abs((top2 + q3 + elim) - 1.0) > tol:
                    raise ValueError(
                        f"standings {group!r}/{row.get('team')!r}: fate partition "
                        f"P(top2)+P(3rd qualify)+P(eliminated)={top2 + q3 + elim!r} != 1")
            if None not in (top2, q3, adv) and abs(adv - (top2 + q3)) > tol:
                raise ValueError(
                    f"standings {group!r}/{row.get('team')!r}: P(advance)={adv!r} != "
                    f"P(top2)+P(3rd qualify)={top2 + q3!r}")
            fate = row.get("fate")
            if fate is not None and fate not in _FATES:
                raise ValueError(
                    f"standings {group!r}/{row.get('team')!r}: unknown fate {fate!r}")


def gate_track(t: dict) -> None:
    """Track-record metrics must be finite numbers or explicit null/coverage_gap — never a
    NaN/inf token (the JSON gate uses allow_nan=False; a NaN must be sanitized to null first)
    — AND the headline metrics must be BOUNDED (FIX E): the 'too-good is a suspected bug' law
    made structural. A coverage_gap track (or any coverage_gap subtree) and an explicit None
    are EXEMPT — a gap/null is an honest absence, never a number to bound-check.

    Bounds (when present and not None):
      * ``beat_close_rate`` in [0,1] (a rate);
      * each ``rps.{model,market,elo}`` finite and >= 0 (a Ranked Probability Score is >= 0);
      * ``n_bets`` / ``n`` >= 0 (a count);
      * a reliability bin's ``forecast_mean`` / ``empirical`` in [0,1] (probabilities)."""
    # (1) finiteness everywhere (the JSON allow_nan=False prerequisite), gap subtrees exempt.
    def _check(x):
        if isinstance(x, dict):
            if x.get("coverage_gap"):
                return
            for v in x.values():
                _check(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                _check(v)
        elif isinstance(x, float) and not math.isfinite(x):
            raise ValueError(f"track metric is not finite ({x!r}) — sanitize NaN/inf to null first")
    _check(t)

    # A coverage_gap track is an honest absence — no metrics to bound.
    if not isinstance(t, dict) or t.get("coverage_gap"):
        return

    def _bounded(v, lo, hi, name):
        if v is None:                                    # honest null -> exempt
            return
        if not _finite_number(v) or not (lo <= v <= hi):
            raise ValueError(f"track metric {name}={v!r} out of bounds [{lo}, {hi}] (too-good/impossible)")

    # (2) bounded headline metrics (only when the key is present; None stays exempt).
    if "beat_close_rate" in t:
        _bounded(t["beat_close_rate"], 0.0, 1.0, "beat_close_rate")
    if "n_bets" in t:
        _bounded(t["n_bets"], 0.0, float("inf"), "n_bets")
    rps = t.get("rps")
    if isinstance(rps, dict):
        for k in ("model", "market", "elo"):
            if k in rps:
                _bounded(rps[k], 0.0, float("inf"), f"rps.{k}")
    reliability = t.get("reliability")
    if isinstance(reliability, (list, tuple)):
        for b in reliability:
            if not isinstance(b, dict):
                continue
            if "n" in b:
                _bounded(b["n"], 0.0, float("inf"), "reliability.n")
            for k in ("forecast_mean", "empirical"):
                if k in b:
                    _bounded(b[k], 0.0, 1.0, f"reliability.{k}")
