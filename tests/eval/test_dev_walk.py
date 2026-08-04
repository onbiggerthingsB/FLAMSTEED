"""Tests for the G-B development walk (scripts/oa_acquire.py, V4).

The eval acquisition executes a FIXED plan; the dev walk is adaptive —
THE_RULE says "the first N_dev with admissible coverage", and admissibility
is only knowable after the cut snapshot is bought. Everything below pins the
properties that make an adaptive paid walk safe: it stops at n_dev, it buys
exactly one snapshot per walked candidate, it never re-buys on resume, the
cap binds per call, and the acquisition scope bounds spend without touching
selection.
"""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def mod():
    sys.path.insert(0, str(_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "oa_acquire_devtest", _ROOT / "scripts" / "oa_acquire.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["oa_acquire_devtest"] = module
    spec.loader.exec_module(module)
    return module


def _candidates(n=6, sport_key="soccer_x", tournament="T"):
    return [{"match_id": f"m{i:03d}", "date": f"2023-03-{10 + i:02d}",
             "home": f"H{i}", "away": f"A{i}", "tournament": tournament,
             "sport_key": sport_key}
            for i in range(n)]


def _transport(mod, candidates, *, admissible=None, listed=None):
    """Mock wire: `admissible` / `listed` are match_id sets (None = all)."""
    calls = []
    used = {"n": 0}
    by_day, by_event = {}, {}
    for c in candidates:
        by_day.setdefault((c["sport_key"], f"{c['date']}T00:00:00Z"),
                          []).append(c)
        by_event[f"dev_{c['match_id']}"] = c

    def respond(payload, price):
        used["n"] += price
        return httpx.Response(200, json=payload, headers={
            "x-requests-last": str(price), "x-requests-used": str(used["n"]),
            "x-requests-remaining": str(20000 - used["n"])})

    def handler(request):
        calls.append((request.url.path, request.url.params["date"]))
        parts = request.url.path.split("/")
        requested = request.url.params["date"]
        if request.url.path.endswith("/events"):
            rows = [c for c in by_day.get((parts[4], requested), [])
                    if listed is None or c["match_id"] in listed]
            return respond({
                "timestamp": requested, "previous_timestamp": requested,
                "next_timestamp": requested,
                "data": [{"id": f"dev_{c['match_id']}",
                          "sport_key": c["sport_key"],
                          "commence_time": f"{c['date']}T19:00:00Z",
                          "home_team": c["home"], "away_team": c["away"]}
                         for c in rows]}, 1)
        c = by_event[parts[6]]
        stamp = datetime.strptime(requested, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc) - timedelta(minutes=3)
        ok = admissible is None or c["match_id"] in admissible
        # an inadmissible fixture: no sharp book in the payload at all
        books = ([{"key": "pinnacle",
                   "last_update": mod._iso(stamp - timedelta(minutes=5)),
                   "markets": [{"key": "h2h",
                                "last_update": mod._iso(
                                    stamp - timedelta(minutes=5)),
                                "outcomes": [
                                    {"name": c["home"], "price": 2.1},
                                    {"name": "Draw", "price": 3.3},
                                    {"name": c["away"], "price": 3.6}]}]}]
                 if ok else [])
        return respond({
            "timestamp": mod._iso(stamp),
            "previous_timestamp": mod._iso(stamp),
            "next_timestamp": mod._iso(stamp),
            "data": {"id": parts[6], "sport_key": c["sport_key"],
                     "commence_time": f"{c['date']}T19:00:00Z",
                     "home_team": c["home"], "away_team": c["away"],
                     "bookmakers": books}}, 10)

    return httpx.MockTransport(handler), calls


def _run(mod, tmp_path, candidates, *, n_dev, transport, max_credits=None):
    return mod.run_dev_acquisition(
        api_key="k", transport=transport, max_credits=max_credits,
        raw_dir=tmp_path / "raw", journal_path=tmp_path / "j.jsonl",
        candidates=candidates, n_dev=n_dev, aliases={}, mode="dry-run")


# ------------------------------------------------------- the stopping rule
def test_walk_stops_at_n_dev_and_leaves_the_tail_unbought(mod, tmp_path):
    cands = _candidates(6)
    transport, calls = _transport(mod, cands)
    out = _run(mod, tmp_path, cands, n_dev=3, transport=transport)
    assert out["covered"] == 3
    assert out["walked"] == 3            # candidates 4-6 never touched
    # 3 listings (one per day) + 3 cut snapshots
    assert len(calls) == 6
    assert out["spent"] == 3 * 1 + 3 * 10


def test_only_the_cut_is_bought_per_candidate(mod, tmp_path):
    # The 2026-08-01 cut-only ruling: no T-24h call exists on the dev path
    # (nothing preregistered reads it), so a walked candidate costs exactly
    # one snapshot.
    cands = _candidates(2)
    transport, calls = _transport(mod, cands)
    out = _run(mod, tmp_path, cands, n_dev=2, transport=transport)
    snapshot_calls = [c for c in calls if "/odds" in c[0]]
    assert len(snapshot_calls) == 2
    for row in out["results"]:
        assert set(row["snapshots"]) == {mod.CUT_TAG}
    assert out["spent"] == 2 * 1 + 2 * 10


def test_inadmissible_candidate_costs_one_snapshot_and_is_skipped(mod,
                                                                  tmp_path):
    cands = _candidates(4)
    # only the 3rd and 4th have a sharp quote
    transport, calls = _transport(mod, cands,
                                  admissible={"m002", "m003"})
    out = _run(mod, tmp_path, cands, n_dev=2, transport=transport)
    assert out["covered"] == 2
    assert out["walked"] == 4            # walked past the two misses
    covered_ids = [r["match_id"] for r in out["results"] if r["covered"]]
    assert covered_ids == ["m002", "m003"]
    # 4 listings + 4 cuts: a miss still pays for its own cut, never more
    assert out["spent"] == 4 * 1 + 4 * 10


def test_unlisted_candidate_costs_nothing_beyond_its_listing(mod, tmp_path):
    cands = _candidates(3)
    transport, calls = _transport(mod, cands, listed={"m000", "m002"})
    out = _run(mod, tmp_path, cands, n_dev=3, transport=transport)
    missed = next(r for r in out["results"] if r["match_id"] == "m001")
    assert missed["event_found"] is False
    assert missed["snapshots"] == {}
    assert out["covered"] == 2
    assert out["spent"] == 3 * 1 + 2 * 10


def test_one_listing_serves_every_candidate_on_its_day(mod, tmp_path):
    cands = [dict(c, date="2023-03-10") for c in _candidates(4)]
    transport, calls = _transport(mod, cands)
    out = _run(mod, tmp_path, cands, n_dev=4, transport=transport)
    listings = [c for c in calls if c[0].endswith("/events")]
    assert len(listings) == 1            # ONE paid listing for the day
    assert out["covered"] == 4
    assert out["spent"] == 1 + 4 * 10


# ------------------------------------------------------------- the journal
def test_every_call_is_journaled_to_the_gb_gate(mod, tmp_path):
    cands = _candidates(2)
    transport, _ = _transport(mod, cands)
    _run(mod, tmp_path, cands, n_dev=2, transport=transport)
    records = mod.read_journal(tmp_path / "j.jsonl")
    assert {r["gate"] for r in records} == {"gb"}
    intents = [r for r in records if r["type"] == "intent"]
    receipts = [r for r in records if r["type"] == "receipt"]
    assert len(intents) == len(receipts) == 4      # 2 listings + 2 cuts
    assert all(len(r["raw_sha256"]) == 64 for r in receipts)


def test_resume_rebuys_nothing_and_restores_the_covered_count(mod, tmp_path):
    cands = _candidates(3)
    transport, _ = _transport(mod, cands)
    first = _run(mod, tmp_path, cands, n_dev=3, transport=transport)
    lines = (tmp_path / "j.jsonl").read_text().splitlines()

    transport2, calls2 = _transport(mod, cands)
    second = _run(mod, tmp_path, cands, n_dev=3, transport=transport2)
    assert calls2 == []                                   # nothing re-bought
    assert (tmp_path / "j.jsonl").read_text().splitlines() == lines
    assert second["covered"] == first["covered"] == 3
    assert second["prior_spent"] == first["spent"]


def test_cap_refuses_before_placing_the_call_that_would_breach_it(mod,
                                                                 tmp_path):
    cands = _candidates(5)
    transport, calls = _transport(mod, cands)
    out = _run(mod, tmp_path, cands, n_dev=5, transport=transport,
               max_credits=25)
    # 1 + 10 + 1 = 12, then the 2nd cut would make 22, then day 3 -> 23,
    # then its cut -> 33 > 25: refused there.
    assert out["aborted"] is not None
    assert out["spent"] <= 25
    assert out["covered"] < 5
    records = mod.read_journal(tmp_path / "j.jsonl")     # journal stays sane
    assert mod.orphan_intents(records) == []


def test_resume_under_a_spent_cap_refuses_outright(mod, tmp_path):
    cands = _candidates(2)
    transport, _ = _transport(mod, cands)
    _run(mod, tmp_path, cands, n_dev=2, transport=transport)
    transport2, _ = _transport(mod, cands)
    with pytest.raises(mod.CreditCapError, match="already exceeds"):
        _run(mod, tmp_path, cands, n_dev=2, transport=transport2,
             max_credits=5)


# ------------------------------------------- selection vs acquisition scope
def _results_frame(rows):
    return pd.DataFrame([
        {"match_id": r[0], "date": pd.Timestamp(r[1]), "home_team": r[2],
         "away_team": r[3], "home_score": 1, "away_score": 0,
         "tournament": r[4]}
        for r in rows])


def test_participants_filter_bounds_spend_without_reordering(mod):
    frame = _results_frame([
        ("a", "2023-03-10", "Brazil", "Peru", "FIFA World Cup qualification"),
        ("b", "2023-03-11", "Japan", "Iraq", "FIFA World Cup qualification"),
        ("c", "2023-03-12", "Chile", "Bolivia",
         "FIFA World Cup qualification"),
    ])
    cfg = {"competitions": ["FIFA World Cup qualification"],
           "acquisition": {
               "sport_keys": {"FIFA World Cup qualification": "soccer_wcq"},
               "participants": {"FIFA World Cup qualification": [
                   "Brazil", "Peru", "Chile", "Bolivia"]}}}
    walkable, out_of_scope = mod.dev_candidates(frame, cfg)
    assert [c["match_id"] for c in walkable] == ["a", "c"]   # order kept
    assert [c["match_id"] for c in out_of_scope] == ["b"]
    # the split never re-ranks: walkable is a SUBSEQUENCE of THE_RULE's order
    assert [c["date"] for c in walkable] == ["2023-03-10", "2023-03-12"]


def test_missing_sport_key_refuses_before_any_call(mod):
    frame = _results_frame([
        ("a", "2023-03-10", "Brazil", "Peru", "Copa América")])
    cfg = {"competitions": ["Copa América"],
           "acquisition": {"sport_keys": {}}}
    with pytest.raises(mod.FixtureManifestError, match="sport_keys lacks"):
        mod.dev_candidates(frame, cfg)


def test_post_issuance_kickoff_is_skipped_without_buying(mod, tmp_path):
    # A fixture kicking off before 09:00Z on its matchday has no
    # pre-issuance quote; the walk records it and buys nothing (OA F2).
    cands = _candidates(1)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        requested = request.url.params["date"]
        if request.url.path.endswith("/events"):
            c = cands[0]
            return httpx.Response(200, json={
                "timestamp": requested, "previous_timestamp": requested,
                "next_timestamp": requested,
                "data": [{"id": "dev_m000", "sport_key": c["sport_key"],
                          "commence_time": f"{c['date']}T07:00:00Z",
                          "home_team": c["home"], "away_team": c["away"]}]},
                headers={"x-requests-last": "1"})
        raise AssertionError("no snapshot may be bought for this candidate")

    out = _run(mod, tmp_path, cands, n_dev=1,
               transport=httpx.MockTransport(handler))
    assert out["covered"] == 0
    assert "not strictly before" in out["results"][0]["error"]
    assert [c for c in calls if "/odds" in c] == []
