"""Per-fixture arm emission — the ONE pricing path V5 (dev) and V9 (eval) share.

The blend weight ``w`` is SELECTED on the development slate and APPLIED to the
scored pools. That transfer is only meaningful if both sides price a fixture
the same way, so the arithmetic lives here once rather than in two runners
that could drift: same production map, same de-vig set, same blend, same
arm names. The runners differ only in which fixtures they walk and which
ledger they write.

One covered fixture produces exactly 46 rows:

===========================  ====  ====================================
arm                          n     what it is
===========================  ====  ====================================
``dev_dc``                   1     the frozen incumbent, straight off
                                   ``production_grid`` (w=0 by identity)
``dev_elo_ordlogit``         1     the Elo ordered-logit reference arm
``dev_odds_{method}``        2     the de-vigged book vector itself
``dev_blend_{method}_w{w}``  42    E' at every grid point, both de-vigs
===========================  ====  ====================================

An odds-ABSENT fixture produces only the two odds-free arms; it carries no
``dev_odds_*`` and no blend rows at all, which is precisely the shape
``arms._design`` counts as excluded rather than erroring on. (The realized
dev manifest is exactly the admissible set, so this path is unexercised
there — but V9's scored pools may hold uncovered fixtures, and the same
code serves them.)

Nothing here reads an outcome. The ledger stores forecasts; outcomes are
joined at scoring time (``select_w(ledger, outcomes=...)``), so a bug in
this module cannot be one that peeked.
"""
from __future__ import annotations

from collections.abc import Mapping

from wcmodel.eval.blend import (
    OA_DEVIG_METHODS,
    W_GRID,
    blend_arm,
    blend_one_x_two,
)
from wcmodel.eval.implied import (
    book_overround,
    is_coherent_book,
    oa_devig,
    solve_implied_rates,
)
from wcmodel.eval.elo_ordlogit import predict_1x2 as ordlogit_1x2
from wcmodel.model.draw_api import FixtureCtx, grid_one_x_two, production_grid

#: The odds-free arms every dev fixture carries, covered or not.
DC_ARM = "dev_dc"
ELO_ARM = "dev_elo_ordlogit"


def odds_arm(method: str) -> str:
    """The de-vigged-book arm name for one OA method (``arms._design``'s
    ``dev_odds_{method}`` contract, restated through one constant)."""
    if method not in OA_DEVIG_METHODS:
        raise ValueError(
            f"de-vig method {method!r} is not in the OA set "
            f"{sorted(OA_DEVIG_METHODS)}")
    return f"dev_odds_{method}"


#: Every arm name a COVERED fixture must carry — derived, never listed by
#: hand, so a change to the grid or the method set reprices the block and
#: trips the completeness test instead of silently shrinking it.
def expected_arms(*, covered: bool) -> tuple[str, ...]:
    arms = [DC_ARM, ELO_ARM]
    if covered:
        for method in sorted(OA_DEVIG_METHODS):
            arms.append(odds_arm(method))
            arms.extend(blend_arm(method, w) for w in W_GRID)
    return tuple(arms)


class OofPricingError(RuntimeError):
    """A fixture cannot be priced as specified — refuse rather than emit a
    partial block that a consumer would read as coverage."""


def _check_1x2(probs: Mapping, what: str) -> dict:
    out = {k: float(probs[k]) for k in ("home", "draw", "away")}
    total = sum(out.values())
    if not all(v == v and v not in (float("inf"), float("-inf"))
               for v in out.values()):
        raise OofPricingError(f"{what}: non-finite probability {out}")
    if abs(total - 1.0) > 1e-9:
        raise OofPricingError(f"{what}: probabilities sum to {total!r}, not 1")
    return out


def book_1x2(prices: Mapping[str, float], *, method: str) -> dict:
    """De-vig one book's ``{home, draw, away}`` decimal prices.

    Order is EXPLICIT (a mapping, not a positional list) because the wire
    labels outcomes by team name and the home/away designation can flip
    between the API and the store — a positional convention here is exactly
    where that flip would silently invert a forecast.
    """
    triple = [float(prices["home"]), float(prices["draw"]),
              float(prices["away"])]
    # Defence in depth: admissibility already rejects an incoherent book
    # (overround < 1 is an arbitrage no operator posts, i.e. corrupt data),
    # but pricing must never be the place that silently accepts one — a
    # de-vig of a corrupt price yields a confident forecast from a number
    # nobody quoted.
    if not is_coherent_book(triple):
        raise OofPricingError(
            f"book {prices} is not a coherent market (overround "
            f"{book_overround(triple):.3f} < 1) — a corrupt archived price, "
            "never de-vigged")
    devig = oa_devig(triple, method=method)
    return _check_1x2(dict(zip(("home", "draw", "away"), devig)),
                      f"de-vigged book ({method})")


def price_fixture(*, posterior, fixture_ctx: FixtureCtx, elo_home: float,
                  elo_away: float, hfa: float, ordlogit_params,
                  book_prices: Mapping[str, float] | None) -> dict:
    """Every arm's 1X2 for ONE fixture: ``{arm: {home, draw, away}}``.

    ``book_prices`` is ``None`` for an odds-absent fixture, which yields the
    two odds-free arms and nothing else. A book that is present but cannot
    be inverted through the finalized production map (``solve_implied_rates``
    returns ``None``) is an ERROR, not a silent demotion to odds-absent: the
    fixture HAS a quote, so reporting it as uncovered would misstate the
    population the analysis is conditioned on.
    """
    out: dict[str, dict] = {}
    grid = production_grid(posterior, fixture_ctx)
    out[DC_ARM] = _check_1x2(grid_one_x_two(grid), DC_ARM)
    out[ELO_ARM] = _check_1x2(
        ordlogit_1x2(ordlogit_params, elo_home, elo_away, hfa), ELO_ARM)
    if book_prices is None:
        return out

    for method in sorted(OA_DEVIG_METHODS):
        devigged = book_1x2(book_prices, method=method)
        out[odds_arm(method)] = devigged
        # positional (home, draw, away) — the solver's contract
        lam_book = solve_implied_rates(
            posterior, fixture_ctx,
            (devigged["home"], devigged["draw"], devigged["away"]))
        if lam_book is None:
            raise OofPricingError(
                f"{fixture_ctx.home} v {fixture_ctx.away}: the de-vigged "
                f"{method} vector {devigged} is not reachable through the "
                "finalized production map (solve_implied_rates failed) — a "
                "covered fixture whose book cannot be inverted must be a "
                "loud refusal, never a quiet demotion to odds-absent")
        for w in W_GRID:
            out[blend_arm(method, w)] = _check_1x2(
                blend_one_x_two(posterior, fixture_ctx, lam_book, w),
                blend_arm(method, w))
    return out


def ledger_rows(*, fixture: Mapping, priced: Mapping[str, Mapping],
                t_issue, training_cutoff, issued_git: str,
                odds_snapshot_hash: str | None) -> list[dict]:
    """Turn one fixture's priced arms into ledger rows.

    ``odds_snapshot_hash`` is stamped on the odds-DERIVED arms only. The two
    odds-free arms carry ``None`` even on a covered fixture, because they
    did not read the snapshot — and ``_covered_fixture_ids`` derives the
    covered set from ANY non-null hash in the frame, so the fixture still
    reads as covered without claiming the incumbent used a price it never
    saw.
    """
    rows = []
    for arm, probs in priced.items():
        odds_derived = arm not in (DC_ARM, ELO_ARM)
        if odds_derived and odds_snapshot_hash is None:
            raise OofPricingError(
                f"{fixture['fixture_id']}: arm {arm!r} is odds-derived but "
                "no snapshot hash was supplied — an odds forecast without "
                "its provenance is unauditable")
        rows.append({
            "fixture_id": str(fixture["fixture_id"]),
            "pool": str(fixture["pool"]),
            "date": str(fixture["date"]),
            "home": str(fixture["home"]),
            "away": str(fixture["away"]),
            "kickoff_utc": fixture["kickoff_utc"],
            "t_issue": t_issue,
            "training_cutoff": training_cutoff,
            "arm": arm,
            "p_home": probs["home"],
            "p_draw": probs["draw"],
            "p_away": probs["away"],
            "issued_git": issued_git,
            "odds_snapshot_hash": (odds_snapshot_hash if odds_derived
                                   else None),
        })
    return rows
