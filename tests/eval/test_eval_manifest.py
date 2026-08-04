"""Tests for scripts/oa_eval_manifest.py — the eval-set acquisition manifest.

The manifest feeds `oa_acquire.py --fixtures` for the G-A eval acquisition:
every error here is a paid-credits error (a wrong kickoff buys a mispriced
T-24h snapshot whose instant is baked into the journal call id), so the
checks are pinned as tests, offline, against the COMMITTED manifest — no
network, no store rebuild.
"""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "oa_eval_manifest.py"
_MANIFEST = _ROOT / "config" / "oa_eval_manifest.yaml"
_INVENTORY = _ROOT / "config" / "oa_scored_inventory.yaml"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("oa_eval_manifest", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["oa_eval_manifest"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manifest():
    return yaml.safe_load(_MANIFEST.read_text())


@pytest.fixture(scope="module")
def inventory():
    return yaml.safe_load(_INVENTORY.read_text())


# ------------------------------------------------------ committed manifest
def test_committed_manifest_verifies(mod, manifest, monkeypatch=None):
    # THE gate: every hard check (identity, discovery days, t_issue<kickoff,
    # local-day agreement, rollover pin, CLV kickoff cross-check) in one run.
    summary = mod.verify_fixtures(manifest["fixtures"])
    assert summary["n_fixtures"] == 217
    assert summary["discovery_days"] == {"wc2022": 22, "euro2024": 21,
                                         "wc2026": 34}
    assert summary["utc_rollovers"] == 36
    assert summary["clv_kickoffs_checked"] > 0


def test_ids_are_exactly_the_scored_inventory(manifest, inventory):
    inv_ids = {str(f["match_id"]) for f in inventory["fixtures"]}
    man_ids = {f["fixture_id"] for f in manifest["fixtures"]}
    assert man_ids == inv_ids
    assert len(manifest["fixtures"]) == 217


def test_home_away_match_inventory_order(manifest, inventory):
    # The manifest keeps the INVENTORY's home/away (the scorer's identity),
    # never the kickoff source's — even where the join had to flip.
    inv = {str(f["match_id"]): f for f in inventory["fixtures"]}
    for fx in manifest["fixtures"]:
        row = inv[fx["fixture_id"]]
        assert fx["home"] == str(row["home_team"]), fx["fixture_id"]
        assert fx["away"] == str(row["away_team"]), fx["fixture_id"]
        assert fx["date"] == str(row["date"]), fx["fixture_id"]
        assert fx["pool"] == row["pool"], fx["fixture_id"]


def test_every_kickoff_strictly_after_t_issue(manifest):
    for fx in manifest["fixtures"]:
        kickoff = datetime.strptime(
            fx["kickoff_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc)
        day = datetime.strptime(fx["date"], "%Y-%m-%d")
        t_issue = day.replace(hour=9, tzinfo=timezone.utc)
        assert t_issue < kickoff, fx["fixture_id"]


def test_known_kickoffs_pinned(manifest):
    # Three independently-known instants, one per pool: the wc2026 opener
    # (Mexico City 13:00 UTC-6), England v Iran (Al Rayyan 16:00 AST) and
    # Spain v Croatia (Berlin 18:00 CEST). Both 2022 and 2024 TOURNAMENT
    # openers are absent — the scored windows are start-EXCLUSIVE, which is
    # why those pools are 63 of 64 and 50 of 51.
    by = {(f["date"], frozenset((f["home"], f["away"]))): f["kickoff_utc"]
          for f in manifest["fixtures"]}
    assert by[("2026-06-11",
               frozenset(("Mexico", "South Africa")))] == \
        "2026-06-11T19:00:00Z"
    assert ("2022-11-20", frozenset(("Qatar", "Ecuador"))) not in by
    assert ("2024-06-14", frozenset(("Germany", "Scotland"))) not in by
    assert by[("2022-11-21",
               frozenset(("England", "Iran")))] == "2022-11-21T13:00:00Z"
    assert by[("2024-06-15",
               frozenset(("Spain", "Croatia")))] == "2024-06-15T16:00:00Z"


def test_tampered_kickoff_is_refused(mod, manifest):
    # RED proof the CLV cross-check bites: shift a cache-covered wc2022
    # kickoff by one hour and the verifier must refuse.
    fixtures = [dict(f) for f in manifest["fixtures"]]
    target = next(f for f in fixtures
                  if f["date"] == "2022-11-22"
                  and {f["home"], f["away"]} == {"Argentina",
                                                 "Saudi Arabia"})
    target["kickoff_utc"] = "2022-11-22T11:00:00Z"
    with pytest.raises(mod.ManifestError, match="kickoff mismatch"):
        mod.verify_fixtures(fixtures)


def test_dropped_fixture_is_refused(mod, manifest):
    fixtures = [dict(f) for f in manifest["fixtures"][1:]]
    with pytest.raises(mod.ManifestError, match="!= inventory ids"):
        mod.verify_fixtures(fixtures)


# ------------------------------------------------------------------ parser
def test_parser_time_inheritance_and_aet_variants(mod):
    text = """
▪ Group X
Fri Dec 2
   18:00    Ghana  0-2   Uruguay   @ Al Janoub Stadium, Al Wakrah
            South Korea  2-1 (1-1)   Portugal  @ Lusail Iconic Stadium
Sun Dec 18
   18:00     Argentina    3-3 a.e.t (2-2, 1-1), 4-2 pen.  France   @ Lusail
"""
    rows = mod.parse_openfootball(text, 2022, 3)
    assert [(r["home"], r["away"]) for r in rows] == [
        ("Ghana", "Uruguay"), ("South Korea", "Portugal"),
        ("Argentina", "France")]
    # the timeless line inherits 18:00; AST(+3) 18:00 -> 15:00Z
    assert rows[1]["kickoff_utc"].strftime("%H:%M") == "15:00"
    assert rows[1]["date"] == "2022-12-02"
    assert rows[2]["date"] == "2022-12-18"


def test_parser_euro_pen_order_and_alias(mod):
    text = """
Mon Jul 1
  21:00     Portugal  3-0 pen. 0-0 a.e.t. (0-0)  Slovenia @ Frankfurt # note
Tue Jul 2
  18:00     Türkiye   2-1 (1-1)  Austria @ Leipzig
"""
    rows = mod.parse_openfootball(text, 2024, 2)
    assert (rows[0]["home"], rows[0]["away"]) == ("Portugal", "Slovenia")
    # CEST(+2) 21:00 -> 19:00Z
    assert rows[0]["kickoff_utc"].strftime("%H:%M") == "19:00"
    # the openfootball alias map lands store spellings
    assert rows[1]["home"] == "Turkey"


def test_parser_skips_scorer_and_lineup_lines(mod):
    text = """
Wed Jun 19
  18:00         Germany   2-0 (1-0)   Hungary      @ Stuttgart
                          (Musiala 22' Gündoğan 67')
    Germany:  Neuer - Kimmich, Rüdiger [Y], Tah
"""
    rows = mod.parse_openfootball(text, 2024, 2)
    assert len(rows) == 1


def test_venue_city_extraction(mod):
    assert mod._venue_cities("New York/New Jersey (East Rutherford)") == \
        {"New York/New Jersey", "East Rutherford"}
    assert mod._venue_cities("Houston") == {"Houston"}
    assert mod._venue_cities("Dallas (Arlington)") == {"Dallas", "Arlington"}


# --------------------------------------------------- acquisition interface
def test_manifest_satisfies_acquire_contract(manifest):
    # Exactly the fields scripts/oa_acquire.py validates, no datetimes in
    # `date` (its _day() refuses them), kickoff parseable.
    for fx in manifest["fixtures"]:
        assert set(fx) == {"fixture_id", "pool", "date", "home", "away",
                           "kickoff_utc"}
        assert isinstance(fx["date"], str) and len(fx["date"]) == 10
        datetime.strptime(fx["kickoff_utc"], "%Y-%m-%dT%H:%M:%SZ")
