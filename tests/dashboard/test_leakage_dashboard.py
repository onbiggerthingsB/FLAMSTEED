"""Dashboard-layer leakage canary + reproducibility (the dashboard analog of the P2-P5
leakage gates), with EXPLICIT non-vacuity (a positive control proving teeth) AND PRECISION
(the canary isolates the EXACT gate it claims to test).

THE GENUINE DASHBOARD LEAK VECTOR IS BITEMPORAL. A snapshot built at cutoff ``C`` is a
``store.read(C)`` -> leakage-safe by construction. The vector that actually probes that
guarantee is a result for a REAL bracket fixture that was

  * PLAYED before the cutoff (calendar ``date = D < C``), so the downstream day-floored
    ``date < cutoff_day`` filter in ``_played_as_of`` would KEEP it — it is NOT excluded by
    the date filter; and
  * VALID before the cutoff (``valid_as_of = D <= C``, the match date), so the
    ``valid_as_of <= C`` half of the store gate would ALSO keep it; but
  * OBSERVED after the cutoff (``observed_at = D_observed > C``), so a leakage-safe
    ``store.read(C)`` EXCLUDES it via the ``observed_at <= C`` gate SPECIFICALLY (look-ahead
    is impossible), while a LEAKY read that dropped only the ``observed_at`` filter would
    include it and the sim WOULD then fix that group fixture.

This is EXACTLY the real live-result vector ``wcmodel.live.ingest_live`` records (lines
115-119): ``normalize_results`` sets ``valid_as_of = observed_at = match date``, then the
ingest OVERRIDES ``observed_at`` to the later whistle ``now`` — i.e. ``valid_as_of`` = the
match date, ``observed_at`` = the (later) observation time. A game PLAYED at its date ``D``
but only OBSERVED later.

PRECISION (T8 Codex re-review). An EARLIER rewrite set BOTH ``valid_as_of`` AND ``observed_at``
to ``D_observed`` (> C). That row is excluded from ``read(C)`` by EITHER gate, so a regression
that dropped ONLY the ``observed_at <= C`` filter (but kept ``valid_as_of <= C``) would STILL
exclude it (``valid_as_of = D_observed > C``) — the canary would pass and MISS the real leak.
Setting ``valid_as_of = D <= C`` (and only ``observed_at > C``) makes the row gated SOLELY by
``observed_at``: a structural probe below proves ``valid_as_of <= C`` ALONE would INCLUDE the
row while ``read(C)`` EXCLUDES it, so the invariance precisely tests the ``observed_at`` gate.

The OLDEST canary mutated a row dated 2026-06-20 (> the 2026-06-12 cutoff) between Brazil and
Serbia — NOT a fixture in the synthetic bracket. A post-cutoff-DATED row is excluded by BOTH
the store read AND the ``date < cutoff`` filter, and a non-bracket pair is never conditioned
on, so that canary could not detect a real leak (it passed for the wrong reason). This
rewrite exercises the bitemporal played-before/valid-before/observed-after vector on a REAL
group fixture between PANEL teams, isolates the ``observed_at`` gate, and proves teeth with a
positive control that holds the cutoff FIXED and varies ONLY the result.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from wcmodel.data.store import Policy
from wcmodel.dashboard.build import build_snapshot

# A REAL group fixture from the synthetic bracket (see tests/dashboard/conftest.py): Brazil
# vs Mexico, dated D = 2024-05-02 (its _FIXTURE_DATES entry). Both teams are in the panel the
# posterior covers, so conditioning on this result is well-defined.
_FIXTURE = ("Brazil", "Mexico")
_MATCH_ID = "bra_mex_played_before_observed_after"   # the leak row's logical key in the store
_D = pd.Timestamp("2024-05-02")                 # the fixture's calendar (play) date, D < C
# Cutoff C: D < C, so the day-floored `date < cutoff_day` filter would KEEP this fixture's
# calendar date — the played-before half of the vector.
_C = "2026-06-12T00:00:00Z"
# The result becomes VISIBLE only when OBSERVED. We set `valid_as_of = D` (the match date,
# <= C, so the `valid_as_of <= C` half of the store gate KEEPS it) and `observed_at =
# D_observed` two weeks AFTER C, so store.read(C) excludes it SOLELY via the `observed_at <=
# C` gate (proven by the structural probe below). This is the REAL ingest_live shape
# (valid_as_of = match date, observed_at = the later whistle; see ingest_live.py:115-119).
# store.read gates on `observed_at <= cutoff AND valid_as_of <= cutoff` (store.py:read), so a
# regression dropping ONLY `observed_at` would leak this row -> the canary catches it.
_D_OBSERVED = pd.Timestamp("2026-06-26")
# A LATER cutoff C2 >= observed_at: now store.read(C2) INCLUDES the result (both gates pass)
# and _played_as_of keeps it (date D < C2), so the group fixture is FIXED -> the cutoff for
# the FIXED-cutoff positive control. Both control builds use THIS cutoff (identical
# decay/time-weights/as_of); only the result's visibility differs across the two builds.
_C2 = "2026-07-01T00:00:00Z"
# A lopsided, score-bearing result for the played-before/valid-before/observed-after fixture.
# A 0-5 Brazil-Mexico group result strongly moves group qualification (proven by the
# fixed-cutoff control below: it roughly halves Brazil's advancement and lifts Mexico's), so
# the positive control shows a real, large progression difference — the canary's as-of-C
# invariance is therefore meaningful, not vacuous.
_LEAK_HOME_SCORE, _LEAK_AWAY_SCORE = 0, 5


def _bundle_bytes(bundle) -> dict:
    """The FULL bundle as ``{relative_path: bytes}`` over every ``*.json`` RECURSIVELY (sorted
    by relative path) in the bundle dir — so a byte-identical-bundle assertion covers EVERY
    artifact build_snapshot writes, INCLUDING the per-fixture ``fixtures/<id>.json`` details
    (HIGH-3 C5 Codex), not just the top-level ``tournament.json``/``meta.json``. Pre-fix this
    used ``glob("*.json")`` (top-level only), so a leak/repro regression confined to a fixture
    detail (forecast grid, the "why", the edge node) slipped the canary entirely. Keying on the
    relative path (``rglob``) keeps fixtures/ entries distinct and in the comparison."""
    bundle = Path(bundle)
    return {str(p.relative_to(bundle)): p.read_bytes()
            for p in sorted(bundle.rglob("*.json"), key=lambda q: q.relative_to(bundle).as_posix())}


def test_bundle_bytes_covers_the_fixtures_subdir_not_just_top_level(tmp_path):
    """HIGH-3 (C5 FOCAL Codex): the leakage/repro byte-identity canary must cover the FULL
    bundle, INCLUDING ``fixtures/<id>.json`` — the per-fixture details (forecast grid, the
    "why", the edge node). Pre-fix ``_bundle_bytes`` used ``bundle.glob("*.json")`` (TOP-LEVEL
    only), so a leak/repro regression confined to a fixture detail would slip through the
    canary entirely. The fix uses ``rglob`` keyed by RELATIVE path, so every artifact is in the
    comparison.

    RED before (keys are bare top-level filenames; no ``fixtures/`` key); GREEN after (a
    ``fixtures/...json`` relative-path key is present)."""
    bundle = tmp_path / "bundle"
    (bundle / "fixtures").mkdir(parents=True)
    (bundle / "tournament.json").write_text("{}")
    (bundle / "meta.json").write_text("{}")
    (bundle / "fixtures" / "bra_mex.json").write_text('{"detail": 1}')

    keys = set(_bundle_bytes(bundle))
    assert any(k.startswith("fixtures/") and k.endswith(".json") for k in keys), (
        f"_bundle_bytes does NOT cover the fixtures/ subdir (keys={sorted(keys)}) — the "
        "leakage/repro canary would miss any leak confined to a per-fixture detail"
    )
    # The top-level artifacts are still covered (now keyed by relative path).
    assert "tournament.json" in keys and "meta.json" in keys
    # The fixture detail's BYTES are actually captured (so a diff would be detected).
    fk = next(k for k in keys if k.startswith("fixtures/"))
    assert _bundle_bytes(bundle)[fk] == b'{"detail": 1}'


def _data_payload(bundle) -> dict:
    """The provenance-STRIPPED ``data`` payload of ``tournament.json`` (``stamp`` wraps every
    artifact as ``{provenance, data}`` — see dashboard/provenance.py). Comparing only
    ``["data"]`` drops the ``as_of``/``posterior_key`` envelope, so a fixed-cutoff control
    comparison cannot be confounded by provenance fields that always differ."""
    return json.loads((bundle / "tournament.json").read_text())["data"]


def _write_played_before_observed_after(store) -> None:
    """Record the Brazil-Mexico result with the PRECISE bitemporal leak shape:

      * calendar ``date = D`` (< C, so the day-floored date filter keeps it),
      * ``valid_as_of = D`` (the match date, <= C, so the ``valid_as_of <= C`` gate keeps it),
      * ``observed_at = D_observed`` (> C, so store.read(C) excludes it SOLELY via the
        ``observed_at <= C`` gate).

    This is the real ``ingest_live`` write shape (``valid_as_of`` = match date, ``observed_at``
    = the later whistle; ingest_live.py:115-119), not an invented schema. A leakage-safe
    read(C) must not see it (only ``observed_at`` excludes it); a read(C2 >= D_observed) must."""
    home, away = _FIXTURE
    store.write("results", pd.DataFrame([{
        "match_id": _MATCH_ID,
        "date": _D, "valid_as_of": _D, "observed_at": _D_OBSERVED,
        "home_team": home, "away_team": away,
        "home_score": _LEAK_HOME_SCORE, "away_score": _LEAK_AWAY_SCORE,
        "tournament": "FIFA World Cup", "neutral": True, "city": "x", "country": "y",
    }]), policy=Policy.POINT_IN_TIME, keys=["match_id"], source="t")


def _assert_gated_solely_by_observed_at(store) -> None:
    """STRUCTURAL PROBE (RED->GREEN evidence) that the leak row is gated by ``observed_at``
    SPECIFICALLY, not ``valid_as_of``:

      * filtering the RAW stored frame by ``valid_as_of <= C`` ALONE INCLUDES the row (the
        ``valid_as_of`` gate does NOT exclude it — count 1), while
      * the leakage-safe ``store.read(cutoff=C)`` EXCLUDES it (count 0 for this match_id, and
        the Brazil-Mexico pair is absent).

    So a regression that dropped the ``observed_at <= C`` filter (but kept ``valid_as_of <=
    C``) WOULD leak this row — the canary's as-of-C invariance precisely tests that gate. If
    the row were over-determined (``valid_as_of = D_observed > C`` too), the first assertion
    would FAIL (valid_as_of-only no longer includes it), exposing the imprecision."""
    cutoff = pd.Timestamp(_C).tz_convert("UTC").tz_localize(None)

    # (a) valid_as_of <= C ALONE, on the raw stored frame -> the row IS present (the
    # valid_as_of gate would NOT exclude it; it is the played-before/valid-before half).
    raw = pd.read_parquet(store._path("results"))
    valid_only = raw[pd.to_datetime(raw["valid_as_of"]) <= cutoff]
    assert (valid_only["match_id"] == _MATCH_ID).sum() == 1, (
        "PRECISION PROBE FAILED: `valid_as_of <= C` alone does NOT include the leak row, so "
        "the row is over-determined (excluded by valid_as_of too) and the canary would still "
        "pass if a regression dropped ONLY the observed_at gate — set valid_as_of = D (<= C)"
    )

    # (b) the leakage-safe read(C) EXCLUDES it -> excluded SOLELY by the observed_at gate.
    read_c = store.read("results", cutoff=_C)
    assert (read_c["match_id"] == _MATCH_ID).sum() == 0, (
        "store.read(C) unexpectedly INCLUDED the post-C-observed leak row — the observed_at "
        "<= C gate is not biting (a real leak)"
    )
    home, away = _FIXTURE
    pair = (read_c["home_team"] == home) & (read_c["away_team"] == away)
    assert pair.sum() == 0, "the Brazil-Mexico result leaked into store.read(C)"


def _progression(data: dict, team: str, market: str) -> float:
    """The point estimate ``data[team][market]["value"]`` from a stripped ``data`` payload."""
    return data[team][market]["value"]


def test_recent_form_excludes_future_dated_matches(tmp_path):
    """FIX F (defense-in-depth leakage guard): ``_recent_form`` must never surface a match
    DATED AFTER the cutoff as "recent form", even if that row slipped the store's
    observed_at/valid_as_of gate. The store read is already date-gated, but nothing asserted
    the EMITTED form-match dates are <= cutoff — so a future-dated row with valid_as_of <=
    cutoff could surface. The fix filters the team's matches to date <= cutoff BEFORE tail(n).

    RED before (no date filter -> the 2026-08-01 row appears in recent_form); GREEN after
    (only the past row appears). If the filter empties the set -> coverage_gap."""
    from wcmodel.dashboard.build import _recent_form

    cutoff = "2026-06-12T00:00:00Z"
    results = pd.DataFrame([
        # a PAST played row (date < cutoff) — must appear in recent form.
        {"date": pd.Timestamp("2026-06-01"), "home_team": "Brazil", "away_team": "Mexico",
         "home_score": 2, "away_score": 1},
        # a FUTURE played row (date AFTER cutoff) — must NOT appear (look-ahead).
        {"date": pd.Timestamp("2026-08-01"), "home_team": "Brazil", "away_team": "Argentina",
         "home_score": 3, "away_score": 0},
    ])
    form = _recent_form(results, "Brazil", cutoff=cutoff)
    dates = {m["date"] for m in form["matches"]}
    assert any(d.startswith("2026-06-01") for d in dates), "the normal past row must still appear"
    assert not any(d.startswith("2026-08-01") for d in dates), (
        "a future-dated match (date > cutoff) leaked into recent_form — look-ahead")


def test_recent_form_gaps_when_only_future_matches(tmp_path):
    """FIX F: when the date filter empties the set (the team has ONLY future-dated matches as
    of the cutoff), recent_form is an honest coverage_gap, never a fabricated/empty list."""
    from wcmodel.dashboard.build import _recent_form

    results = pd.DataFrame([
        {"date": pd.Timestamp("2026-08-01"), "home_team": "Brazil", "away_team": "Argentina",
         "home_score": 3, "away_score": 0},
    ])
    form = _recent_form(results, "Brazil", cutoff="2026-06-12T00:00:00Z")
    assert form.get("coverage_gap") is True


@pytest.mark.slow
def test_snapshot_is_leakage_safe_played_before_observed_after_does_not_leak(
        small_store, synthetic_tournament, tmp_path):
    """A snapshot built at cutoff C is UNCHANGED by a real bracket-fixture result that was
    PLAYED before C (date D < C), VALID before C (valid_as_of = D <= C) but OBSERVED after C
    (observed_at > C) — the genuine bitemporal dashboard leak vector, isolated to the
    ``observed_at`` gate. The as-of-C bundle is a store.read(C), so the post-C-observed
    result must not touch it.

    PRECISION (FIX 1): a structural probe asserts the row is gated SOLELY by ``observed_at``
    (``valid_as_of <= C`` alone INCLUDES it; ``read(C)`` EXCLUDES it), so a regression that
    dropped only the ``observed_at`` filter would leak it -> the invariance has bite on the
    exact gate it claims.

    POSITIVE CONTROL (FIX 2): a FIXED-cutoff, data-only control (``test_..._positive_control``
    below) proves the result genuinely changes the sim conditioning, so this invariance is
    non-vacuous.

    EXPLICIT DISTINCT cache_dir per build forces a genuine re-fit (since C4, the DEFAULT fit
    cache lives OUTSIDE out_root in the shared paths.cache, so distinct out_roots alone would
    now SHARE the default cache and short-circuit build #2 — making this canary VACUOUS). With
    a distinct cache_dir per build, build #2 re-fits against the MUTATED store rather than
    short-circuiting on a shared cache hit, so a real leak would surface here."""
    fk = {"draws": 60, "advi_iters": 1500, "seed": 0}

    # Snapshot #1 at C, BEFORE the result is recorded (the game is unplayed-as-of-read at C
    # -> the sim simulates it). EXPLICIT distinct cache_dir (cache_a) so this build re-fits.
    b1 = build_snapshot(_C, store=small_store, fit_kwargs={**fk, "cache_dir": str(tmp_path / "cache_a")},
                        items=[], out_root=tmp_path / "asof_c_1", tournament=synthetic_tournament)
    asof_c = _bundle_bytes(b1)

    # Record the played-before/valid-before/observed-after result: invisible at C (observed >
    # C), visible at C2. A leakage-safe read(C) excludes it from BOTH the feature fit AND the
    # sim conditioning; a leaky read would fix the Brazil-Mexico group fixture and change the
    # bundle.
    _write_played_before_observed_after(small_store)

    # FIX 1 STRUCTURAL PROBE: prove the row is gated SOLELY by observed_at (valid_as_of <= C
    # alone includes it; read(C) excludes it), so the invariance below tests THAT gate.
    _assert_gated_solely_by_observed_at(small_store)

    # Snapshot #2 at the SAME C, with a DISTINCT cache_dir (cache_b) -> a genuine re-fit
    # against the MUTATED store (no shared-cache short-circuit). The post-C-observed result
    # must not leak: the FULL as-of-C bundle is unchanged.
    b2 = build_snapshot(_C, store=small_store, fit_kwargs={**fk, "cache_dir": str(tmp_path / "cache_b")},
                        items=[], out_root=tmp_path / "asof_c_2", tournament=synthetic_tournament)
    asof_c_again = _bundle_bytes(b2)
    assert set(asof_c_again) == set(asof_c)              # same set of artifact filenames
    assert asof_c_again == asof_c                        # byte-identical FULL bundle (no leak)


@pytest.mark.slow
def test_positive_control_result_causally_changes_progression_at_fixed_cutoff(
        small_store, synthetic_tournament, tmp_path):
    """POSITIVE CONTROL (teeth) — isolate the RESULT's causal effect by holding the cutoff
    FIXED at C2 and varying ONLY the Brazil-Mexico result's visibility:

      * BASELINE: build at C2 with the result NOT yet recorded (invisible).
      * WITH-RESULT: build at C2 AFTER recording it (observed_at = D_observed <= C2 -> visible).

    Same cutoff C2 for both -> identical decay / time-weights / as_of / posterior_key
    structure; the ONLY difference between the two stores is the inserted result, so any delta
    is its CAUSAL effect. We compare the provenance-STRIPPED ``data`` payloads (drop the
    ``as_of``/``posterior_key`` envelope that always differs), and assert the Brazil and
    Mexico group-progression values genuinely differ by FAR more than Monte-Carlo noise. This
    is what makes the as-of-C invariance (FIX 1) meaningful: the result is load-bearing, so
    its ABSENCE from the as-of-C bundle is a real (not vacuous) guarantee.

    EXPLICIT DISTINCT cache_dir per build forces a genuine re-fit (since C4 the default cache
    lives OUTSIDE out_root in paths.cache, so distinct out_roots alone would now SHARE it and
    short-circuit the WITH-RESULT build — making this control vacuous). Distinct cache_dirs
    keep each build a real re-fit against its own store."""
    fk = {"draws": 60, "advi_iters": 1500, "seed": 0}

    # BASELINE at C2: the Brazil-Mexico result is NOT in the store yet, so it is invisible at
    # C2 too (the sim SIMULATES that group fixture). EXPLICIT distinct cache_dir (cache_a).
    b_base = build_snapshot(_C2, store=small_store, fit_kwargs={**fk, "cache_dir": str(tmp_path / "cache_a")},
                            items=[], out_root=tmp_path / "c2_baseline", tournament=synthetic_tournament)
    base = _data_payload(b_base)

    # Record the result. observed_at = D_observed (2026-06-26) <= C2 (2026-07-01), so it is
    # VISIBLE at C2 -> the sim FIXES the Brazil-Mexico group fixture to 0-5.
    _write_played_before_observed_after(small_store)

    # WITH-RESULT at the SAME cutoff C2, with a DISTINCT cache_dir (cache_b) -> a real re-fit.
    # Identical cutoff/decay/as_of; the ONLY change vs BASELINE is the now-visible result.
    b_with = build_snapshot(_C2, store=small_store, fit_kwargs={**fk, "cache_dir": str(tmp_path / "cache_b")},
                            items=[], out_root=tmp_path / "c2_with_result",
                            tournament=synthetic_tournament)
    with_result = _data_payload(b_with)

    # The data payloads MUST differ (envelope already stripped, so this is a genuine
    # data-level change, not a provenance artifact).
    assert with_result != base, (
        "POSITIVE CONTROL FAILED: making the Brazil-Mexico result visible at the SAME cutoff "
        "C2 did not change the `data` payload — conditioning on the result is not load-bearing, "
        "so the as-of-C invariance is vacuous and the canary has no teeth"
    )

    # The teams in the fixed result move substantially (FAR above MC noise; the SE at 60 draws
    # is ~0.06). A 0-5 Brazil-Mexico group result roughly halves Brazil's advancement and
    # lifts Mexico's, so |delta| on at least one of {advance_from_group, champion} is large.
    deltas = {}
    for team in _FIXTURE:
        for market in ("advance_from_group", "champion"):
            deltas[(team, market)] = abs(
                _progression(with_result, team, market)
                - _progression(base, team, market))
    max_delta = max(deltas.values())
    assert max_delta > 0.10, (
        "POSITIVE CONTROL TOO WEAK: making the Brazil-Mexico result visible moved the "
        f"Brazil/Mexico progression by at most {max_delta:.3f} (advance_from_group/champion) "
        "— below the bar that proves a non-trivial causal effect; the control lacks teeth. "
        f"deltas={ {f'{t}.{m}': round(v, 4) for (t, m), v in deltas.items()} }"
    )


@pytest.mark.slow
def test_snapshot_is_reproducible_same_cutoff_seed_byte_identical(
        small_store, synthetic_tournament, tmp_path):
    """Same cutoff+seed -> byte-identical bundle (determinism), asserted over the ENTIRE
    bundle (every *.json, not just tournament.json), so 'byte-identical bundle' is actually
    asserted.

    EXPLICIT DISTINCT cache_dir per build forces a genuine fresh re-fit for EACH build (since
    C4 the default cache lives OUTSIDE out_root, so distinct out_roots alone would share it).
    So byte-identical here means the determinism survives two INDEPENDENT fits at the same
    cutoff+seed (content-addressed -> same posterior key -> identical bytes), not a trivial
    re-read of one shared cache entry."""
    fk = {"draws": 60, "advi_iters": 1500, "seed": 0}
    a = build_snapshot(_C, store=small_store, fit_kwargs={**fk, "cache_dir": str(tmp_path / "cache_a")},
                       items=[], out_root=tmp_path / "a", tournament=synthetic_tournament)
    b = build_snapshot(_C, store=small_store, fit_kwargs={**fk, "cache_dir": str(tmp_path / "cache_b")},
                       items=[], out_root=tmp_path / "b", tournament=synthetic_tournament)
    bundle_a, bundle_b = _bundle_bytes(a), _bundle_bytes(b)
    assert set(bundle_a) == set(bundle_b)               # same artifact filenames
    assert bundle_a == bundle_b                         # byte-identical FULL bundle
