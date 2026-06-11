"""C5 end-to-end: the FULL dashboard bundle (schedule + fixtures/<id> + tournament +
track + meta) is emitted, GATED per-surface, STAMPED on every file, and NON-REAL-tainted
when the live items are synthetic. track.json is an honest coverage-gap when no backtest
records are supplied (the build NEVER re-runs the heavy walk-forward backtest)."""
import json

import pytest

from wcmodel.dashboard.build import build_snapshot
from wcmodel.backtest.odds_ingest import synthetic_odds_sample


@pytest.mark.slow
def test_full_bundle_emitted_gated_and_stamped(small_store, synthetic_tournament, tmp_path, cfg):
    s = synthetic_odds_sample(home="Brazil", away="Mexico", commence="2026-06-12T19:00:00Z",
                              entry=(2.5, 3.4, 3.0), close=(2.1, 3.5, 3.4), seed=0)
    b = build_snapshot("2026-06-12T12:00:00Z", store=small_store,
                       items=[{"sample": s["sample"], "liquidity": 50.0}],
                       config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                               "cache_dir": str(tmp_path / "fc")},
                       tournament=synthetic_tournament, out_root=tmp_path / "out")
    names = {p.name for p in b.glob("*.json")}
    assert {"schedule.json", "tournament.json", "standings.json", "track.json", "meta.json"} <= names
    assert (b / "fixtures").is_dir() and any((b / "fixtures").glob("*.json"))
    for p in b.rglob("*.json"):                       # every file stamped + NON-REAL (synthetic items)
        env = json.loads(p.read_text())
        assert env["provenance"]["is_synthetic"] is True and env["provenance"]["banner"]
        assert "data" in env
    # track is an honest coverage-gap when no backtest records supplied
    track = json.loads((b / "track.json").read_text())["data"]
    assert track.get("coverage_gap") is True

    # Item A: standings.json carries per-group, per-team rows; every row's probability node is
    # an {value, se} envelope and the fate partition is coherent (gate_standings enforced this
    # at build time — re-assert the on-disk shape here).
    standings = json.loads((b / "standings.json").read_text())["data"]
    assert standings and isinstance(standings, dict)          # {group: [rows]}
    for rows in standings.values():
        for row in rows:
            for fld in ("exp_points", "exp_gd", "p_top2", "p_third_qualify",
                        "p_eliminated", "p_advance"):
                assert "value" in row[fld] and "se" in row[fld]      # no naked number
            top2, q3 = row["p_top2"]["value"], row["p_third_qualify"]["value"]
            elim = row["p_eliminated"]["value"]
            if None not in (top2, q3, elim):
                assert abs((top2 + q3 + elim) - 1.0) < 1e-6           # acceptance #1 on disk


def _is_real_edge(node: dict) -> bool:
    """A REAL (attached) edge node carries the decision-time fields and is NOT a gap."""
    return (
        not node.get("coverage_gap")
        and node.get("is_synthetic") is True
        and {"staked", "edge", "stake_signal", "entry_odds"} <= set(node)
    )


@pytest.mark.slow
def test_edge_actually_attaches_to_matching_fixture(small_store, synthetic_tournament,
                                                    tmp_path, cfg):
    """C5 FOCAL: the live edge ACTUALLY ATTACHES to the matching group fixture.

    The synthetic odds sample's identity (home/away + UTC commence DATE) is chosen to
    EXACTLY match a real group fixture in ``synthetic_tournament`` (``Brazil`` vs
    ``Mexico`` on ``2024-05-02`` — see conftest ``_FIXTURE_DATES``), so the edge SHOULD
    attach. This is the assertion the original e2e never made: it only checked the bundle
    was emitted/stamped, never that an edge survived the lookup. Before the key fix,
    ``_edge_key`` built the lookup key with a ``datetime.date`` object while the scan's
    ``event_key`` (stringified by ``decide_live``) keys ``edges_by_event`` with a date
    STRING — so the lookup ALWAYS missed and EVERY edge silently became a coverage_gap.

    A genuinely-absent fixture (no odds item) still gaps HONESTLY — the fix attaches a
    REAL edge only where one exists, never fabricates one.
    """
    # commence DATE == the (Brazil, Mexico) group fixture date in conftest (_FIXTURE_DATES).
    # 6h-before-kickoff entry is well within stale_snapshot_seconds (86400), so bettable.
    s = synthetic_odds_sample(home="Brazil", away="Mexico",
                              commence="2024-05-02T19:00:00Z",
                              entry=(2.5, 3.4, 3.0), close=(2.1, 3.5, 3.4), seed=0)
    b = build_snapshot("2026-06-12T12:00:00Z", store=small_store,
                       items=[{"sample": s["sample"], "liquidity": 50.0}],
                       config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                               "cache_dir": str(tmp_path / "fc")},
                       tournament=synthetic_tournament, out_root=tmp_path / "out")

    # The matching fixture's per-fixture detail carries a REAL edge (NOT a coverage_gap).
    matched = None
    for p in (b / "fixtures").glob("*.json"):
        d = json.loads(p.read_text())["data"]
        if d["home"] == "Brazil" and d["away"] == "Mexico":
            matched = d
    assert matched is not None, "the Brazil-vs-Mexico group fixture was not emitted"
    assert _is_real_edge(matched["edge"]), (
        f"edge did NOT attach to the matching fixture; got {matched['edge']!r} "
        "(the edge key never matched edges_by_event's stringified-date key)"
    )

    # ±1.5 COVER (the new Derived scalar): the freshly-built fixture detail carries a coherent
    # cover pair, and the row summary projects the SAME pair. Acceptance 2 (sum~1) + 3 (strict
    # subset of home win) verified over a REAL build, not just the staged bundle.
    cov = matched["forecast"]["cover"]
    assert set(cov) == {"home", "away"}
    assert abs(cov["home"] + cov["away"] - 1.0) < 1e-9, "cover pair must sum to 1 (half line, no push)"
    assert cov["home"] < matched["forecast"]["one_x_two"]["home"], "P(home −1.5) must be < P(home win)"

    # And the schedule ROW for the same fixture carries the same REAL edge.
    sched = json.loads((b / "schedule.json").read_text())["data"]["group"]
    rows = [r for r in sched if r["home"] == "Brazil" and r["away"] == "Mexico"]
    assert rows and _is_real_edge(rows[0]["edge"]), "edge did NOT attach to the schedule row"
    # The row summary projects the SAME cover pair the fixture detail computed (pure projection).
    assert rows[0]["forecast_summary"]["cover"] == cov, "row cover must project the fixture cover"

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
