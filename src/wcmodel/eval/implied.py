"""Book-implied goal rates through the REAL finalized production map, plus the
OA de-vig set (OA Plan 2 v2, V2 / Codex findings 13 & 15, B2-1 ruling).

:func:`solve_implied_rates` INVERTS the same per-draw map production forecasts
come from, END TO END: find ``(lam_h, lam_a)`` such that::

    finalize(mean_d grid(lam_h, lam_a, rho_d))  ->  1X2  ==  the de-vigged
                                                             book vector

with ``rho_d`` the fixture posterior's OWN rho draws — never a single
collapsed rho, never a Skellam/independent-Poisson stand-in (the incoherence
finding 15 closed), and never a different truncation (``max_goals`` defaults
to the frozen production constant and is pinned by the draw-api caller test).
``finalize`` is the production finalization leg
(:func:`wcmodel.model.draw_api.finalize_grid`): mechanism-'c' widening when
the fixture is provisional, final renormalization always — which is why the
solve takes the FIXTURE CONTEXT, whose team identities decide the provisional
flag. The E' blend (V6) substitutes ``lam_book`` into the per-draw rate blend
and finalizes identically, so at ``w=1`` the blended forecast reproduces the
de-vigged vector BY THIS DEFINITION — for EVERY fixture, provisional ones
included. (B2-1 closed the earlier incoherence: inverting the unwidened map
while the blend widens put the w=1 endpoint ~0.029 off the de-vigged vector
on provisional fixtures.)

Acceptance is deliberately strict (finding 15): ``least_squares`` within the
rate box ``RATE_BOUNDS``, residual below ``RESIDUAL_TOL`` in EVERY 1X2
component, AND two well-separated starts agreeing. Every failure mode — a
start that does not converge, a converged residual above tolerance, or
disagreeing starts (an ambiguous inversion) — returns ``None``, fail closed:
the fixture is then odds-uncovered for the blend (V7's covered-only
population), and there is NO symmetric-split or best-effort fallback, ever. A
MALFORMED target, by contrast, raises ``ValueError``: ``None`` is reserved
for "well-posed but unreachable", because downstream population accounting
counts ``None`` rows as uncovered (finding 10).

De-vig (finding 13): the OA-choosable set is EXACTLY ``{shin,
multiplicative}``. ``"basic"`` names NO distinct algorithm — it is the
REPORTING LABEL for ``multiplicative`` (the naive proportional
normalization), resolved before validation. ``"power"`` exists in the Phase-4
backtest trio (``backtest.devig_select``) but is NOT OA-choosable: it can
enter neither the de-vig selection nor the Holm family — pinned by test.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from wcmodel.data import devig as _devig
from wcmodel.model.draw_api import (
    PRODUCTION_MAX_GOALS,
    finalize_grid,
    grid_one_x_two,
    mean_grid_over_draws,
)

#: The OA-choosable de-vig methods — EXACTLY these two (finding 13). "power"
#: is a Phase-4 backtest method, never OA-choosable; Buchdahl was never
#: choosable anywhere.
OA_DEVIG_METHODS = ("shin", "multiplicative")

#: Reporting labels -> real methods. "basic" is the label the OA reports use
#: for the naive proportional normalization; the algorithm IS multiplicative
#: (there is no distinct 'basic' de-vig — finding 13). Nothing else may ever
#: be labeled: a second entry here is a prereg change.
OA_DEVIG_LABELS = {"basic": "multiplicative"}

_OA_DEVIG_FUNCS = {
    "shin": _devig.shin,
    "multiplicative": _devig.multiplicative,
}

#: Rate box for the solve. 0.05 goals keeps the per-draw Poisson grids healthy
#: (no underflow) and 8.0 sits far above any credible international 1X2 line;
#: a de-vigged vector whose inversion needs a rate OUTSIDE this box is treated
#: as unreachable (solver returns None — the fixture is odds-uncovered).
RATE_BOUNDS = (0.05, 8.0)

#: Acceptance: the solved rates must reproduce the target in EVERY 1X2
#: component to better than this, through the exact averaged map.
RESIDUAL_TOL = 1e-6

#: Two-start agreement tolerance on each rate. At an accepted root the map's
#: local sensitivity |d p / d lam| is O(0.1) or larger, so two residual-
#: accepted solutions in the SAME basin sit within ~1e-5 of each other, while
#: genuinely distinct crossings of a two-parameter map differ at O(0.1+):
#: 1e-4 separates the regimes with margin both ways.
_AGREEMENT_TOL = 1e-4

#: Deterministic, well-separated starts — a low-scoring and a high-scoring
#: basin. Uniqueness is CHECKED (two-start agreement), not assumed.
_STARTS = ((0.7, 0.7), (2.5, 2.5))


def oa_devig(odds: list[float], *, method: str) -> list[float]:
    """De-vig ``odds`` (decimal, ordered home/draw/away) with an OA method.

    ``method`` must resolve into ``OA_DEVIG_METHODS`` after the reporting-label
    map (``"basic"`` -> ``"multiplicative"``). Anything else — including
    ``"power"``, which IS choosable in the Phase-4 backtest — is refused
    loudly: the OA set is exactly ``{shin, multiplicative}`` (finding 13), so
    a wider method can enter neither the V6 de-vig selection nor the V7 Holm
    family through this gate.
    """
    resolved = OA_DEVIG_LABELS.get(method, method)
    if resolved not in _OA_DEVIG_FUNCS:
        raise ValueError(
            f"de-vig method {method!r} is not OA-choosable; the OA set is "
            f"exactly {OA_DEVIG_METHODS} ('basic' is the reporting label for "
            "'multiplicative'; 'power' stays a Phase-4 backtest method and can "
            "enter neither selection nor the Holm family — finding 13)")
    return _OA_DEVIG_FUNCS[resolved](odds)


def solve_implied_rates(posterior, fixture_ctx, target, *,
                        max_goals: int = PRODUCTION_MAX_GOALS
                        ) -> tuple[float, float] | None:
    """Solve ``(lam_h, lam_a)`` so the FINALIZED production map hits ``target``.

    ``target`` is the de-vigged ``(p_home, p_draw, p_away)``; ``posterior`` is
    the fixture's OWN posterior (its rho draws define the map — finding 3);
    ``fixture_ctx`` is the fixture's :class:`~wcmodel.model.draw_api.FixtureCtx`
    (B2-1 ruling): the map inverted is candidate rates broadcast across the
    posterior's rho draws -> per-draw correction + renorm -> mean ->
    ``finalize_grid`` (mechanism-'c' widening when the fixture is provisional,
    final renormalization always) -> 1X2. Only the ctx's team identities enter
    (they decide the provisional flag); neutral/host/covariates shape the
    MODEL rates, not the rate->1X2 map, so they cannot move the inversion.
    Returns the rate pair, or ``None`` when the solve fails ANY acceptance leg
    (non-convergence, residual >= ``RESIDUAL_TOL``, or the two starts
    disagreeing) — fail closed, the fixture is odds-uncovered downstream.
    Widening compresses the reachable 1X2 set, so a target reachable through
    the unwidened map may be unreachable for a provisional fixture: that is
    the CORRECT fail-closed outcome, never a reason to invert a different map.

    A MALFORMED target (wrong shape, non-finite, a component outside the open
    interval (0, 1), or a sum off 1 by more than 1e-6 — beyond which no
    distribution can match every component to ``RESIDUAL_TOL`` anyway) is a
    caller bug and raises ``ValueError``; ``None`` is reserved for well-posed
    but unreachable targets (finding 10's population accounting counts None
    rows as uncovered). An unknown team raises ``KeyError`` (the predict
    contract — a silent not-provisional guess would invert the wrong map). A
    non-Dixon-Coles posterior is refused loudly: the solve inverts the
    PRODUCTION map, whose dependence correction is the per-draw rho —
    extending it to another likelihood is a prereg change, not a silent
    fallback.
    """
    t = np.asarray(target, dtype=float)
    if t.shape != (3,) or not np.all(np.isfinite(t)):
        raise ValueError(
            "target must be three finite probabilities (home, draw, away); "
            f"got {target!r}")
    if np.any(t <= 0.0) or np.any(t >= 1.0) or abs(float(t.sum()) - 1.0) > 1e-6:
        raise ValueError(
            "target must be a strict 1X2 distribution (each component in "
            f"(0, 1), sum within 1e-6 of 1); got {target!r}")
    if posterior.likelihood != "dixon_coles":
        raise ValueError(
            "solve_implied_rates inverts the production Dixon-Coles map "
            f"(per-draw rho); a {posterior.likelihood!r} posterior carries no "
            "rho draws — extending the OA solve to another likelihood is a "
            "prereg change, not a fallback")
    for team in (fixture_ctx.home, fixture_ctx.away):
        if team not in posterior._idx:
            raise KeyError(team)
    provisional = (fixture_ctx.home in posterior.provisional_teams) \
        or (fixture_ctx.away in posterior.provisional_teams)

    rho = posterior._post("rho")
    S = rho.shape[-1]

    def residual(x):
        lam_h, lam_a = x
        # Constant candidate rates broadcast across the fixture posterior's
        # draws, through the EXACT production averaging (per-draw tau at each
        # rho_d, per-draw renorm, mean), the finalization leg (widening iff
        # the fixture is provisional, renorm always — B2-1) and the 1X2
        # projection: the very map the E' blend evaluates at w=1.
        grid = mean_grid_over_draws(
            np.full(S, lam_h), np.full(S, lam_a),
            likelihood="dixon_coles", rho=rho, max_goals=max_goals)
        grid = finalize_grid(grid, posterior, provisional=provisional)
        p = grid_one_x_two(grid)
        return np.array([p["home"] - t[0], p["draw"] - t[1], p["away"] - t[2]])

    lo, hi = RATE_BOUNDS
    solutions = []
    for x0 in _STARTS:
        res = least_squares(residual, x0, bounds=([lo, lo], [hi, hi]))
        if not res.success or float(np.max(np.abs(res.fun))) >= RESIDUAL_TOL:
            return None
        solutions.append(np.asarray(res.x, dtype=float))
    if float(np.max(np.abs(solutions[0] - solutions[1]))) > _AGREEMENT_TOL:
        return None
    return float(solutions[0][0]), float(solutions[0][1])
