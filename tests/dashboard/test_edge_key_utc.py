"""C5 (FOCAL Codex re-finding): the dashboard edge key must derive the fixture's UTC
COMMENCE DATE the same way the scan/odds path does — NOT the fixture's LOCAL ``date``.

THE PRODUCTION BUG. ``config/tournament_2026.yaml`` fixtures store a LOCAL ``date`` plus a
LOCAL ``time`` carrying a UTC offset (e.g. ``date: '2026-06-11', time: '20:00 UTC-6'`` ->
the match kicks off at ``2026-06-12T02:00:00Z``, so its UTC commence DATE is ``2026-06-12``,
ONE DAY AFTER the local ``date``). The scan/decide path keys ``edges_by_event`` on the UTC
commence date (``odds_ingest.event_key`` -> ``astimezone(utc).date()``, stringified by
``decide_live`` as ``str(ekey[2])``). ``_edge_key`` keyed on the LOCAL ``date`` string, so on
EVERY evening-kickoff production fixture in a negative-UTC-offset venue the key MISSED ->
the real model-vs-market edge silently degraded to a coverage_gap.

28 of the 72 real WC-2026 group fixtures cross the UTC date boundary, so this was not a
corner case — it killed the overlay on more than a third of production fixtures.
"""
import json

import pytest

from wcmodel.backtest.odds_ingest import event_key, synthetic_odds_sample
from wcmodel.dashboard.build import _edge_key, build_snapshot


def _scan_key(home: str, away: str, commence_utc: str) -> tuple:
    """The EXACT key ``edges_by_event`` is built with: the scan opportunity's
    ``event_key`` (``odds_ingest.event_key`` UTC ``date``) stringified by ``decide_live``
    as ``str(ekey[2])`` -> ``(home, away, "YYYY-MM-DD")`` on the UTC commence date."""
    ek = event_key({"home_team": home, "away_team": away, "commence_time": commence_utc})
    return (ek[0], ek[1], str(ek[2]))


def test_edge_key_matches_scan_key_for_utc_crossing_fixture():
    """RED before the fix, GREEN after: a production-shaped evening fixture whose LOCAL
    ``date`` is one day BEFORE its UTC commence date must produce an edge key BYTE-IDENTICAL
    to the scan/``edges_by_event`` key (which is on the UTC commence date).

    ``20:00 UTC-6`` on ``2026-06-11`` is ``2026-06-12T02:00:00Z`` -> UTC date ``2026-06-12``.
    Pre-fix ``_edge_key`` returned the LOCAL ``2026-06-11`` -> mismatch -> coverage_gap.
    """
    home, away = "South Korea", "Czech Republic"
    # The fixture as it lives in tournament_2026.yaml (local date + local time w/ UTC offset).
    fx = {"home": home, "away": away, "date": "2026-06-11", "time": "20:00 UTC-6"}
    # The odds-side commence for the SAME kickoff, in UTC (what the feed publishes).
    scan_key = _scan_key(home, away, "2026-06-12T02:00:00Z")
    assert scan_key[2] == "2026-06-12"      # sanity: the UTC date is the NEXT day

    edge_key = _edge_key(fx["home"], fx["away"], fx["date"], time=fx["time"])
    assert edge_key == scan_key, (
        f"edge key {edge_key!r} != scan key {scan_key!r} — the UTC-crossing fixture's edge "
        "would miss edges_by_event and silently become a coverage_gap"
    )


def test_edge_key_non_crossing_fixture_still_matches():
    """A non-crossing fixture (a day match, or a synthetic fixture with no ``time``) must
    still key on its own date — the fix must not break the synthetic harness."""
    # Day match: 13:00 UTC-6 on 2026-06-11 is 2026-06-11T19:00:00Z -> UTC date unchanged.
    fx = {"home": "Mexico", "away": "South Africa", "date": "2026-06-11", "time": "13:00 UTC-6"}
    assert _edge_key(fx["home"], fx["away"], fx["date"], time=fx["time"]) == _scan_key(
        "Mexico", "South Africa", "2026-06-11T19:00:00Z"
    )
    # No time (synthetic harness fixture): treat date as already-UTC, no crossing.
    assert _edge_key("Brazil", "Mexico", "2024-05-02") == ("Brazil", "Mexico", "2024-05-02")


# --- The minimal UTC-crossing tournament for the full-bundle e2e. ---
# One group of the small_store PANEL teams; one Final placeholder. The (Brazil, Mexico)
# group fixture carries a LOCAL date one day BEFORE its UTC commence date, exactly like a
# real evening WC fixture. Every group date is a pre-2026 sentinel < the cutoff so no
# fixture is "played as of" the cutoff (all-simulated read), mirroring conftest.
_PANEL_TEAMS = ["Brazil", "Argentina", "Mexico", "Malta"]
# Brazil-vs-Mexico is the UTC-crosser: local 2024-05-02 + 20:00 UTC-6 -> 2024-05-03T02:00Z.
_LOCAL_DATES = {
    ("Brazil", "Argentina"): ("2024-05-01", None),
    ("Mexico", "Malta"): ("2024-05-06", None),
    ("Brazil", "Mexico"): ("2024-05-02", "20:00 UTC-6"),   # crosses to UTC 2024-05-03
    ("Argentina", "Malta"): ("2024-05-03", None),
    ("Brazil", "Malta"): ("2024-05-04", None),
    ("Argentina", "Mexico"): ("2024-05-05", None),
}


@pytest.fixture
def utc_crossing_tournament() -> dict:
    fixtures = []
    for (h, a), (d, t) in _LOCAL_DATES.items():
        fx = {"home": h, "away": a, "date": d, "round": "Matchday 1"}
        if t is not None:
            fx["time"] = t
        fixtures.append(fx)
    fixtures.append({"match": 104, "home": "1A", "away": "2A", "round": "Final"})
    return {"groups": [{"name": "A", "teams": list(_PANEL_TEAMS)}], "fixtures": fixtures}


def _is_real_edge(node: dict) -> bool:
    return (
        not node.get("coverage_gap")
        and node.get("is_synthetic") is True
        and {"staked", "edge", "stake_signal", "entry_odds"} <= set(node)
    )


@pytest.mark.slow
def test_utc_crossing_fixture_edge_attaches_end_to_end(small_store, utc_crossing_tournament,
                                                       tmp_path, cfg):
    """C5 production case: the live edge ACTUALLY ATTACHES to a UTC-crossing group fixture.

    The scan opportunity is keyed on the UTC commence date (``2024-05-03``), while the
    fixture's LOCAL ``date`` is ``2024-05-02``. RED before the fix (``_edge_key`` on the
    local date -> the edge becomes a coverage_gap); GREEN after (``_edge_key`` reconstructs
    the UTC date from ``date`` + ``time`` + offset -> the edge attaches).

    CONTROL: a fixture with NO live odds item still gaps HONESTLY — the fix attaches a REAL
    edge only where one exists, never fabricates one.
    """
    # commence is the UTC kickoff for the local 2024-05-02 20:00 UTC-6 Brazil-Mexico fixture.
    # 6h-before-kickoff entry is well within stale_snapshot_seconds (86400), so bettable.
    s = synthetic_odds_sample(home="Brazil", away="Mexico",
                              commence="2024-05-03T02:00:00Z",
                              entry=(2.5, 3.4, 3.0), close=(2.1, 3.5, 3.4), seed=0)
    assert _scan_key("Brazil", "Mexico", "2024-05-03T02:00:00Z")[2] == "2024-05-03"

    b = build_snapshot("2026-06-12T12:00:00Z", store=small_store,
                       items=[{"sample": s["sample"], "liquidity": 50.0}],
                       config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                               "cache_dir": str(tmp_path / "fc")},
                       tournament=utc_crossing_tournament, out_root=tmp_path / "out")

    # The UTC-crossing fixture's per-fixture detail carries a REAL edge (NOT a coverage_gap).
    matched = None
    for p in (b / "fixtures").glob("*.json"):
        d = json.loads(p.read_text())["data"]
        if d["home"] == "Brazil" and d["away"] == "Mexico":
            matched = d
    assert matched is not None, "the Brazil-vs-Mexico group fixture was not emitted"
    assert _is_real_edge(matched["edge"]), (
        f"edge did NOT attach to the UTC-crossing fixture; got {matched['edge']!r} "
        "(the local-date edge key missed the UTC-date scan key -> silent coverage_gap)"
    )

    # The schedule ROW for the same fixture carries the same REAL edge.
    sched = json.loads((b / "schedule.json").read_text())["data"]["group"]
    rows = [r for r in sched if r["home"] == "Brazil" and r["away"] == "Mexico"]
    assert rows and _is_real_edge(rows[0]["edge"]), "edge did NOT attach to the schedule row"

    # CONTROL: a fixture with NO live odds item still gaps HONESTLY (no fabricated edge).
    other = None
    for p in (b / "fixtures").glob("*.json"):
        d = json.loads(p.read_text())["data"]
        if not (d["home"] == "Brazil" and d["away"] == "Mexico"):
            other = d
            break
    assert other is not None
    assert other["edge"].get("coverage_gap") is True, (
        "a fixture with no live odds must stay an honest coverage_gap"
    )
