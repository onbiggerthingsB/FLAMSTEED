"""The ``--slate`` dev-slate mini-probe (OA Plan 2 v2, V0).

A SECOND probe surface on the same runner: it measures whether the candidate
development competitions (2022-2025) exist in the Odds-API historical archive
at all, and whether their listings carry the sharp book — the evidence that
turns `oa_dev_slate.competitions` from empty into chosen. It is deliberately
tiny (the plan caps it at 150 credits, asked alongside G-A) and shares the
15-fixture probe's gates: dry-run by DEFAULT, ``--live`` refused without both
``ODDS_API_KEY`` and ``--max-credits``, the SpendGate before every call, the
billing-header check enforced against the cap.

NO test here touches the network — every request goes through an
``httpx.MockTransport``, behind the conftest ``no_live_network`` sentinel. The
live slate run is the USER's decision at the same STOP gate as G-A; it is
never executed by tests or agents.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _ROOT / "scripts" / "oa_probe.py"
_STORE = _ROOT / "data" / "stores" / "full_final"

_needs_store = pytest.mark.skipif(
    not _STORE.exists(),
    reason=f"{_STORE} absent (gitignored local artifact) — rebuild it to re-arm "
           "the slate-probe date grounding check")


def _load():
    spec = importlib.util.spec_from_file_location("oa_probe", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod(tmp_path, monkeypatch, isolated_odds_raw_dir):
    monkeypatch.chdir(tmp_path)
    return _load()


def _files_under(root: Path) -> set:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


# --------------------------------------------------------------------------- #
# The candidate panel + its budget.                                             #
# --------------------------------------------------------------------------- #
def test_slate_probes_are_a_separate_constant_from_the_eval_fixtures(mod):
    # The dev slate is a DIFFERENT question (which competitions exist at all)
    # from the eval panel (do these 15 known fixtures price). Sharing one
    # constant would let a dev-coverage edit silently re-plan paid eval calls.
    assert mod.SLATE_PROBES is not mod.PROBE_FIXTURES
    assert {p["sport_key"] for p in mod.SLATE_PROBES}.isdisjoint(
        {"", None})


def test_every_slate_probe_is_in_the_dev_window(mod):
    # The frozen rule's window. A probe outside it measures coverage for
    # fixtures the slate can never contain.
    for probe in mod.SLATE_PROBES:
        assert "2022-01-01" <= probe["date"] <= "2025-12-31", probe


def test_no_slate_probe_date_carries_a_scored_fixture_of_its_competition(mod):
    # 2026-08-01 pre-lock rule correction (finding 9, ratified): the old check
    # banned probe DATES from the scored pools' calendar windows — which
    # banned Copa America 2024 (inside the euro2024 window) while it shares
    # not one FIXTURE with the scored pools. The exclusion is now exact
    # scored-fixture membership, so the probe constraint follows suit: no
    # probed (tournament, date) may name a day that holds a scored fixture
    # of that competition.
    from wcmodel.eval.dev_slate import load_scored_inventory
    scored = {(f["tournament"], f["date"])
              for f in load_scored_inventory()["fixtures"]}
    for probe in mod.SLATE_PROBES:
        assert (probe["tournament"], probe["date"]) not in scored, probe


def test_copa_america_is_in_the_candidate_panel(mod):
    # The amendment's positive half: Copa America is an eligible development
    # competition (its 2024 fixtures are NOT scored), so the precommitted
    # candidate panel must probe it.
    assert any(p["tournament"] == "Copa América" for p in mod.SLATE_PROBES)


def test_slate_probe_identities_are_distinct(mod):
    # Discovery is keyed by (sport_key, date), so probes sharing both REUSE
    # one listing (never buy it twice) — allowed exactly when their `teams`
    # filters differ, because then they price DIFFERENT fixtures (the
    # 2026-08-01 marquee-NL entry). Identical (sport_key, date, teams) would
    # be one snapshot bought under two names.
    keys = [(p["sport_key"], p["date"], p.get("teams"))
            for p in mod.SLATE_PROBES]
    assert len(keys) == len(set(keys))


def test_marquee_nl_entry_reuses_the_qf_listing(mod):
    # The user-approved marquee entry must SHARE the receipted QF listing's
    # (sport_key, date) — a fresh date would buy a new discovery — and must
    # precommit its exact fixture.
    marquee = [p for p in mod.SLATE_PROBES if p.get("teams")]
    assert len(marquee) == 1
    entry = marquee[0]
    assert set(entry["teams"]) == {"Netherlands", "Spain"}
    sharers = [p for p in mod.SLATE_PROBES
               if (p["sport_key"], p["date"]) == (entry["sport_key"],
                                                  entry["date"])]
    assert len(sharers) == 2


def test_projected_slate_cost_fits_the_plan_budget(mod):
    # The plan asked <=150 alongside G-A; 2026-08-01 the user approved the
    # marquee-NL addition -> 165. The projection is DERIVED from the panel,
    # so adding a probe reprices it and trips here rather than at the spend
    # gate. (It is a CEILING: the marquee entry's shared listing is reused,
    # so its modeled 11 bills 10.)
    projected = mod.projected_slate_cost()
    assert projected == len(mod.SLATE_PROBES) * (
        mod.DISCOVERY_CREDITS + mod.SNAPSHOT_CREDITS)
    assert projected <= mod.SLATE_CREDIT_BUDGET == 165


def test_pick_slate_event_honors_the_teams_filter(mod):
    events = [
        {"event_id": "aaa", "commence_time": "2025-03-20T17:00:00Z",
         "home": "Armenia", "away": "Georgia"},
        {"event_id": "bbb", "commence_time": "2025-03-20T19:45:00Z",
         "home": "Netherlands", "away": "Spain"},
    ]
    # unfiltered: the deterministic earliest-kickoff rule
    assert mod._pick_slate_event(events)["event_id"] == "aaa"
    # filtered: the precommitted pair, either orientation
    assert mod._pick_slate_event(
        events, teams=("Netherlands", "Spain"))["event_id"] == "bbb"
    assert mod._pick_slate_event(
        events, teams=("Spain", "Netherlands"))["event_id"] == "bbb"
    # a pair the listing does not hold -> None, never a fallback fixture
    assert mod._pick_slate_event(events, teams=("France", "Croatia")) is None


@_needs_store
def test_slate_probe_dates_are_grounded_in_the_store(mod):
    # Each probe names a martj42 `tournament` and a date; the store must
    # actually hold senior men's internationals of that competition on that
    # day, or the probe buys a listing for a day nothing was played.
    import pandas as pd
    results = pd.read_parquet(_STORE / "results.parquet")
    results["date"] = pd.to_datetime(results["date"]).dt.date.astype(str)
    for probe in mod.SLATE_PROBES:
        played = results[(results["date"] == probe["date"])
                         & (results["tournament"] == probe["tournament"])]
        assert len(played) > 0, probe


# --------------------------------------------------------------------------- #
# Dry-run is the default and spends nothing.                                    #
# --------------------------------------------------------------------------- #
def test_slate_defaults_to_dry_run_and_never_reads_the_env_key(mod, tmp_path,
                                                               monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "real-key-must-not-be-read")
    assert mod.main(["--slate", "--out", "reports/oa_slate_probe.md"]) == 0
    report = (tmp_path / "reports" / "oa_slate_probe.md").read_text()
    assert "MODE: DRY-RUN" in report
    assert "real-key-must-not-be-read" not in report
    # Nothing but the report: no archive of MOCK bytes into any store.
    assert _files_under(tmp_path) == {"reports/oa_slate_probe.md"}


def test_slate_dry_run_report_covers_every_probe(mod, tmp_path):
    assert mod.main(["--slate", "--out", "reports/oa_slate_probe.md"]) == 0
    report = (tmp_path / "reports" / "oa_slate_probe.md").read_text()
    for probe in mod.SLATE_PROBES:
        assert probe["competition"] in report
        assert probe["sport_key"] in report
    assert "NOT measurements" in report


def test_slate_report_labels_the_keys_as_candidates(mod, tmp_path):
    # The sport keys are HYPOTHESES this probe exists to verify. A report that
    # presents them as established would turn a wrong key into "no coverage".
    assert mod.main(["--slate", "--out", "reports/oa_slate_probe.md"]) == 0
    report = (tmp_path / "reports" / "oa_slate_probe.md").read_text()
    assert "candidate" in report.lower()


def test_slate_and_default_modes_write_different_reports(mod, tmp_path):
    assert mod.main([]) == 0
    assert mod.main(["--slate"]) == 0
    assert (tmp_path / "reports" / "oa_probe.md").exists()
    assert (tmp_path / "reports" / "oa_slate_probe.md").exists()


# --------------------------------------------------------------------------- #
# The live gates — identical to the eval probe's, exercised through mocks.      #
# --------------------------------------------------------------------------- #
def test_slate_live_refuses_without_key(mod, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        mod.main(["--slate", "--live", "--max-credits", "150"])


def test_slate_live_refuses_without_max_credits(mod, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "k")
    with pytest.raises(SystemExit):
        mod.main(["--slate", "--live"])


def test_slate_live_and_dry_run_are_mutually_exclusive(mod):
    with pytest.raises(SystemExit):
        mod.main(["--slate", "--live", "--dry-run"])


def test_slate_cap_below_projection_aborts_before_the_first_call(mod,
                                                                 monkeypatch,
                                                                 tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    monkeypatch.setenv("ODDS_API_KEY", "k")
    monkeypatch.setattr(mod, "_live_transport",
                        lambda: httpx.MockTransport(handler))
    assert mod.main(["--slate", "--live", "--max-credits", "1"]) == 1
    assert calls == []                      # zero requests, zero credits
    assert not (tmp_path / "reports" / "oa_slate_probe.md").exists()


def test_slate_live_is_journaled_and_refuses_a_transport_without_evidence(
        mod, monkeypatch, tmp_path, capsys):
    # Finding 1 (BLOCKER): the old --slate --live path ran through an
    # invocation-local SpendGate with NO journal and NO flock — 24+ paid
    # calls invisible to the G-A cumulative cap. The live slate now routes
    # through oa_acquire's journal machinery, which (like the eval
    # acquisition) refuses a transport that cannot produce the paid evidence
    # the receipts must cite — so a mocked live run places ZERO calls and
    # journals nothing, instead of spending unjournaled.
    calls = []

    def handler(request):
        calls.append(request.url.path)
        day = request.url.params["date"][:10]
        return httpx.Response(
            200, json={"timestamp": request.url.params["date"], "data": []},
            headers={"x-requests-last": "1", "x-requests-used": "1",
                     "x-requests-remaining": "999"})

    monkeypatch.setenv("ODDS_API_KEY", "k")
    monkeypatch.setattr(mod, "_live_transport",
                        lambda: httpx.MockTransport(handler))
    assert mod.main(["--slate", "--live", "--max-credits", "150"]) == 1
    assert "paid evidence" in capsys.readouterr().err
    assert calls == []                       # no unjournaled call, ever
    assert not list(tmp_path.rglob("*.jsonl"))   # and no journal rows either


# --------------------------------------------------------------------------- #
# What the slate run actually measures.                                         #
# --------------------------------------------------------------------------- #
def _canned(mod, *, listing, book=None):
    """A mock wire: one discovery listing per probe, then one snapshot."""
    book = mod.SHARP_BOOK if book is None else book

    def handler(request):
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200, json={"timestamp": request.url.params["date"],
                           "data": listing},
                headers={"x-requests-last": "1", "x-requests-used": "1",
                         "x-requests-remaining": "999"})
        event = listing[0]
        return httpx.Response(
            200,
            json={"timestamp": request.url.params["date"],
                  "data": {**event, "bookmakers": [
                      {"key": book, "last_update": event["commence_time"],
                       "markets": [{"key": mod.MARKET,
                                    "last_update": event["commence_time"],
                                    "outcomes": [
                                        {"name": event["home_team"], "price": 2.0},
                                        {"name": "Draw", "price": 3.4},
                                        {"name": event["away_team"], "price": 3.8}]}]}]}},
            headers={"x-requests-last": "10", "x-requests-used": "11",
                     "x-requests-remaining": "989"})

    return httpx.MockTransport(handler)


def _listing(day):
    return [{"id": "ev1", "commence_time": f"{day}T19:00:00Z",
             "home_team": "Alpha", "away_team": "Beta"},
            {"id": "ev0", "commence_time": f"{day}T16:00:00Z",
             "home_team": "Gamma", "away_team": "Delta"}]


def test_slate_run_picks_the_snapshot_event_deterministically(mod):
    # The listing has no pre-listed fixture to match, so the event must be
    # chosen by a RULE, not by wire order — otherwise which fixture the paid
    # snapshot priced depends on how the API happened to sort its response.
    day = mod.SLATE_PROBES[0]["date"]
    out = mod.run_slate_probe(api_key="k", transport=_canned(mod, listing=_listing(day)),
                              max_credits=None, raw_dir=None)
    first = out["results"][0]
    assert first["event_id"] == "ev0"        # earliest kickoff, then id
    reversed_out = mod.run_slate_probe(
        api_key="k", transport=_canned(mod, listing=_listing(day)[::-1]),
        max_credits=None, raw_dir=None)
    assert reversed_out["results"][0]["event_id"] == "ev0"


def test_slate_run_records_sharp_book_presence(mod):
    day = mod.SLATE_PROBES[0]["date"]
    out = mod.run_slate_probe(api_key="k", transport=_canned(mod, listing=_listing(day)),
                              max_credits=None, raw_dir=None)
    assert out["results"][0]["snapshot"]["pinnacle_present"] is True
    soft = mod.run_slate_probe(
        api_key="k", transport=_canned(mod, listing=_listing(day), book="unibet_eu"),
        max_credits=None, raw_dir=None)
    assert soft["results"][0]["snapshot"]["pinnacle_present"] is False


def test_empty_listing_suppresses_the_paid_snapshot(mod):
    # A competition the archive does not carry must cost ONE credit, not
    # eleven: no event means no snapshot precall at all.
    def handler(request):
        assert request.url.path.endswith("/events"), "snapshot must not be placed"
        return httpx.Response(200, json={"timestamp": request.url.params["date"],
                                         "data": []},
                              headers={"x-requests-last": "1",
                                       "x-requests-used": "1",
                                       "x-requests-remaining": "9"})

    out = mod.run_slate_probe(api_key="k", transport=httpx.MockTransport(handler),
                              max_credits=None, raw_dir=None)
    assert out["spent"] == len(mod.SLATE_PROBES) * mod.DISCOVERY_CREDITS
    assert all(r["n_events_listed"] == 0 for r in out["results"])
    assert all(r["snapshot"] is None for r in out["results"])


def test_a_failing_competition_is_a_finding_not_a_crash(mod):
    # A wrong candidate sport key is exactly what this probe is for: it must
    # land in the report as a per-competition finding, with the other probes
    # still measured.
    seen = {"n": 0}

    def handler(request):
        seen["n"] += 1
        if seen["n"] == 1:
            return httpx.Response(404, json={"message": "unknown sport"},
                                  headers={"x-requests-last": "0"})
        day = request.url.params["date"][:10]
        return _canned(mod, listing=_listing(day)).handler(request)

    out = mod.run_slate_probe(api_key="k", transport=httpx.MockTransport(handler),
                              max_credits=None, raw_dir=None)
    assert "error" in out["results"][0]
    assert out["results"][1].get("event_id")


def test_slate_report_redacts_the_key_from_error_cells(mod):
    key = "SECRET-SLATE-KEY"

    def handler(request):
        raise ValueError(f"malformed payload echoing {key} back")

    out = mod.run_slate_probe(api_key=key, transport=httpx.MockTransport(handler),
                              max_credits=None, raw_dir=None)
    md = mod.assemble_slate_report(
        mode="live", mocked=True, plan=mod.build_slate_call_plan(),
        projected=out["projected"], spent=out["spent"],
        results=out["results"], usage=out["usage"], aborted=out["aborted"],
        cap=None, actual=out["actual"], overrun=out["overrun"])
    assert key not in md and "[REDACTED]" in md
