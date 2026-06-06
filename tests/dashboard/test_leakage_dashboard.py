"""Dashboard-layer leakage canary + reproducibility (the dashboard analog of the P2-P5
leakage gates), with EXPLICIT non-vacuity (a positive control proving teeth).

THE GENUINE DASHBOARD LEAK VECTOR IS BITEMPORAL. A snapshot built at cutoff ``C`` is a
``store.read(C)`` -> leakage-safe by construction. The vector that actually probes that
guarantee is a result for a REAL bracket fixture that was

  * PLAYED before the cutoff (calendar ``date = D < C``), so the downstream day-floored
    ``date < cutoff_day`` filter in ``_played_as_of`` would KEEP it — it is NOT excluded by
    the date filter; but
  * OBSERVED after the cutoff (``observed_at = valid_as_of = D_observed > C``), so a
    leakage-safe ``store.read(C)`` EXCLUDES it (``observed_at <= C AND valid_as_of <= C``),
    while a LEAKY read would include it and the sim WOULD then fix that group fixture.

The OLD canary mutated a row dated 2026-06-20 (> the 2026-06-12 cutoff) between Brazil and
Serbia — NOT a fixture in the synthetic bracket. A post-cutoff-DATED row is excluded by BOTH
the store read AND the ``date < cutoff`` filter, and a non-bracket pair is never conditioned
on, so that canary could not detect a real leak (it passed for the wrong reason). This
rewrite exercises the bitemporal played-before/observed-after vector on a REAL group fixture
between PANEL teams, and proves teeth with a positive control.
"""
import json

import pandas as pd
import pytest

from wcmodel.data.store import Policy
from wcmodel.dashboard.build import build_snapshot

# A REAL group fixture from the synthetic bracket (see tests/dashboard/conftest.py): Brazil
# vs Mexico, dated D = 2024-05-02 (its _FIXTURE_DATES entry). Both teams are in the panel the
# posterior covers, so conditioning on this result is well-defined.
_FIXTURE = ("Brazil", "Mexico")
_D = pd.Timestamp("2024-05-02")                 # the fixture's calendar (play) date, D < C
# Cutoff C: D < C, so the day-floored `date < cutoff_day` filter would KEEP this fixture's
# calendar date — the played-before half of the vector.
_C = "2026-06-12T00:00:00Z"
# The result becomes VISIBLE only when OBSERVED — set observed_at = valid_as_of two weeks
# AFTER C, so store.read(C) excludes it (observed after the cutoff) but a read at a later
# cutoff includes it. (store.read gates on observed_at <= cutoff AND valid_as_of <= cutoff;
# setting BOTH > C makes the row invisible at C — see wcmodel/data/store.py:read.)
_D_OBSERVED = pd.Timestamp("2026-06-26")
# A LATER cutoff C2 > observed_at: now store.read(C2) INCLUDES the result and _played_as_of
# keeps it (date D < C2), so the group fixture is FIXED -> the positive control.
_C2 = "2026-07-01T00:00:00Z"
# A lopsided, score-bearing result for the played-before/observed-after fixture. A 0-5
# Brazil-Mexico group result strongly moves group qualification (proven below: it nearly
# halves Brazil's advancement and lifts Mexico's), so the positive control shows a real,
# large progression difference — the canary's as-of-C invariance is therefore meaningful.
_LEAK_HOME_SCORE, _LEAK_AWAY_SCORE = 0, 5


def _bundle_bytes(bundle) -> dict:
    """The FULL bundle as ``{filename: bytes}`` over every ``*.json`` (sorted) in the bundle
    dir — so a byte-identical-bundle assertion covers EVERY artifact build_snapshot writes
    (tournament.json AND meta.json), not just tournament.json."""
    return {p.name: p.read_bytes() for p in sorted(bundle.glob("*.json"))}


def _write_played_before_observed_after(store) -> None:
    """Record the Brazil-Mexico result with the bitemporal leak shape: calendar ``date = D``
    (< C, so the date filter keeps it) but ``observed_at = valid_as_of = D_observed`` (> C, so
    store.read(C) excludes it). Matches the BitemporalStore.write contract (both time columns
    present); a leakage-safe read(C) must not see it, a read(C2) must."""
    home, away = _FIXTURE
    store.write("results", pd.DataFrame([{
        "match_id": "bra_mex_played_before_observed_after",
        "date": _D, "valid_as_of": _D_OBSERVED, "observed_at": _D_OBSERVED,
        "home_team": home, "away_team": away,
        "home_score": _LEAK_HOME_SCORE, "away_score": _LEAK_AWAY_SCORE,
        "tournament": "FIFA World Cup", "neutral": True, "city": "x", "country": "y",
    }]), policy=Policy.POINT_IN_TIME, keys=["match_id"], source="t")


@pytest.mark.slow
def test_snapshot_is_leakage_safe_played_before_observed_after_does_not_leak(
        small_store, synthetic_tournament, tmp_path):
    """A snapshot built at cutoff C is UNCHANGED by a real bracket-fixture result that was
    PLAYED before C (date D < C) but OBSERVED after C — the genuine bitemporal dashboard leak
    vector. The as-of-C bundle is a store.read(C), so the post-C-observed result must not
    touch it. The POSITIVE CONTROL (a third build at a LATER cutoff where the result IS
    visible) proves the result genuinely changes the sim conditioning, so this invariance is
    non-vacuous, not trivial.

    Distinct out_roots force a genuine re-fit per build (the fit cache lands under each
    out_root), so build #2 re-fits against the mutated store rather than short-circuiting on
    a shared cache hit — a real leak would surface here."""
    fk = {"draws": 60, "advi_iters": 1500, "seed": 0}

    # Snapshot #1 at C, BEFORE the result is recorded (the game is unplayed-as-of-read at C
    # -> the sim simulates it).
    b1 = build_snapshot(_C, store=small_store, fit_kwargs=fk, items=[],
                        out_root=tmp_path / "asof_c_1", tournament=synthetic_tournament)
    asof_c = _bundle_bytes(b1)

    # Record the played-before/observed-after result: invisible at C (observed > C), visible
    # at C2. A leakage-safe read(C) excludes it from BOTH the feature fit AND the sim
    # conditioning; a leaky read would fix the Brazil-Mexico group fixture and change the
    # bundle.
    _write_played_before_observed_after(small_store)

    # Snapshot #2 at the SAME C (distinct out_root -> a real re-fit against the mutated
    # store). The post-C-observed result must not leak: the FULL as-of-C bundle is unchanged.
    b2 = build_snapshot(_C, store=small_store, fit_kwargs=fk, items=[],
                        out_root=tmp_path / "asof_c_2", tournament=synthetic_tournament)
    asof_c_again = _bundle_bytes(b2)
    assert set(asof_c_again) == set(asof_c)              # same set of artifact filenames
    assert asof_c_again == asof_c                        # byte-identical FULL bundle (no leak)

    # POSITIVE CONTROL (teeth): a third build at a LATER cutoff C2 > observed_at, where the
    # result IS visible. Its tournament.json MUST differ from the as-of-C bundle — proving
    # the recorded Brazil-Mexico result genuinely changes the sim conditioning (so the
    # as-of-C invariance above is meaningful, not vacuous). Empirically this is a large move
    # (Brazil advance_from_group ~0.52 -> ~0.26; Mexico ~0.56 -> ~0.83; max |delta| ~0.27).
    b3 = build_snapshot(_C2, store=small_store, fit_kwargs=fk, items=[],
                        out_root=tmp_path / "asof_c2", tournament=synthetic_tournament)
    asof_c2_tournament = (b3 / "tournament.json").read_bytes()
    assert asof_c2_tournament != asof_c["tournament.json"], (
        "POSITIVE CONTROL FAILED: making the played-before/observed-after Brazil-Mexico "
        "result visible (at cutoff C2) did NOT change tournament.json — conditioning on it "
        "is not load-bearing, so the as-of-C invariance is vacuous and the canary has no "
        "teeth"
    )


@pytest.mark.slow
def test_snapshot_is_reproducible_same_cutoff_seed_byte_identical(
        small_store, synthetic_tournament, tmp_path):
    """Same cutoff+seed -> byte-identical bundle (determinism), asserted over the ENTIRE
    bundle (every *.json, not just tournament.json), so 'byte-identical bundle' is actually
    asserted."""
    fk = {"draws": 60, "advi_iters": 1500, "seed": 0}
    a = build_snapshot(_C, store=small_store, fit_kwargs=fk, items=[],
                       out_root=tmp_path / "a", tournament=synthetic_tournament)
    b = build_snapshot(_C, store=small_store, fit_kwargs=fk, items=[],
                       out_root=tmp_path / "b", tournament=synthetic_tournament)
    bundle_a, bundle_b = _bundle_bytes(a), _bundle_bytes(b)
    assert set(bundle_a) == set(bundle_b)               # same artifact filenames
    assert bundle_a == bundle_b                         # byte-identical FULL bundle
