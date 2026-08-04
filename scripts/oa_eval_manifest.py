#!/usr/bin/env python
"""Eval-set acquisition manifest generator (OA Plan 2 v2, V3 input).

``scripts/oa_acquire.py --fixtures`` needs, for every scored fixture,
``{fixture_id, pool, date (venue-LOCAL matchday), home, away, kickoff_utc}``.
The frozen scored inventory (``config/oa_scored_inventory.yaml``) carries the
first five but NOT ``kickoff_utc`` — and kickoff is load-bearing: the T-24h
snapshot is requested at ``kickoff_utc - 24h`` and that instant is baked into
the journal's call ids, so a wrong kickoff buys a mispriced reference line
that a later correction would have to re-buy. Kickoffs therefore come from
sources with per-fixture times:

- **wc2026** (104): ``config/tournament_2026.yaml`` — venue-local ``date`` +
  ``time: HH:MM UTC±N`` per fixture. Group fixtures join by
  ``(date, home, away)`` (the yaml's names were reconciled to the martj42
  store when it was built); knockout fixtures carry placeholder slots
  (``W101``), so they join the store's played rows by ``(date, city)``, the
  city read from the venue string (either the parenthesized part or the
  outer name — the store is inconsistent about which it ingested).
- **wc2022** (63) / **euro2024** (50): openfootball fixture text (public
  domain, the same source and fetch-programmatically pattern as the WC-2026
  loader), times venue-local with a FIXED tournament offset (Qatar UTC+3,
  Germany CEST UTC+2). Every fetched byte is archived content-addressed under
  ``data/cache/openfootball/`` and its sha256 recorded in the manifest
  header.

Refusal checks (all hard — a manifest that fails any of them is not written):

1. fixture ids are EXACTLY the inventory's 217; per-pool counts 63/50/104.
2. distinct ``(sport_key, matchday)`` discovery days == the plan's modeled
   77, split {wc2022: 22, euro2024: 21, wc2026: 34} — wc2022 and wc2026
   share ``soccer_fifa_world_cup`` but never share a day, so the union is
   the sum.
3. ``t_issue (09:00Z on date) < kickoff_utc`` strictly, every fixture.
4. wc2022/euro2024: the venue-local calendar day of ``kickoff_utc`` equals
   the manifest ``date`` (these pools never roll — offsets +3/+2 with
   afternoon kickoffs); wc2026: the yaml date is used verbatim and the count
   of fixtures whose UTC date differs from it is pinned to the known 36.
5. every wc2022 kickoff that the Phase-4 CLV cache holds (22 fixtures,
   kickoffs straight from The Odds API) matches EXACTLY.

Default action verifies the committed manifest against the inventory and
these checks; ``--emit`` (re)builds it from sources.
"""
# No `from __future__ import annotations`: loaded by PATH in tests, matching
# the oa_probe.py / oa_acquire.py convention.
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

INVENTORY_PATH = Path("config/oa_scored_inventory.yaml")
TOURNAMENT_2026_PATH = Path("config/tournament_2026.yaml")
STORE_PATH = Path("data/stores/full_final/results.parquet")
CLV_CACHE_PATH = Path("data/clv_odds_cache.json")
OUT_PATH = Path("config/oa_eval_manifest.yaml")
RAW_CACHE_DIR = Path("data/cache/openfootball")

#: openfootball sources: (pool, url, fixed venue-local UTC offset hours, year)
OPENFOOTBALL_SOURCES = (
    ("wc2022",
     "https://raw.githubusercontent.com/openfootball/worldcup/master/2022--qatar/cup.txt",
     3, 2022),
    ("wc2022",
     "https://raw.githubusercontent.com/openfootball/worldcup/master/2022--qatar/cup_finals.txt",
     3, 2022),
    ("euro2024",
     "https://raw.githubusercontent.com/openfootball/euro/master/2024--germany/euro.txt",
     2, 2024),
)

#: The plan's modeled discovery-day counts — the spend model the G-A cap was
#: approved against. A generated manifest that disagrees is a STOP, not a fix.
EXPECTED_DISCOVERY_DAYS = {"wc2022": 22, "euro2024": 21, "wc2026": 34}
EXPECTED_POOL_COUNTS = {"wc2022": 63, "euro2024": 50, "wc2026": 104}
#: Fixtures whose kickoff instant crosses midnight UTC relative to the
#: venue-local matchday — the finding-7 rollover population, known to be 36.
EXPECTED_UTC_ROLLOVERS = 36

SPORT_KEYS = {"wc2022": "soccer_fifa_world_cup",
              "euro2024": "soccer_uefa_european_championship",
              "wc2026": "soccer_fifa_world_cup"}

T_ISSUE_UTC_HOUR = 9

#: openfootball spelling -> martj42/store spelling (the inventory's names).
#: Only entries that DIFFER are listed; identity is the default.
OPENFOOTBALL_ALIASES = {
    "USA": "United States",
    "Türkiye": "Turkey",
    "Czechia": "Czech Republic",
}

#: The Odds API spelling -> store spelling, for the CLV kickoff cross-check.
ODDS_API_ALIASES = {"USA": "United States"}

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

_DAY_LINE = re.compile(
    r"^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s*$")

#: The score/annotation block between the two team names: one or more of a
#: score, "a.e.t"/"a.e.t.", "pen."/"pen", or a parenthesized group, with
#: optional commas — covers "1-1 (1-0)", "3-0 pen. 0-0 a.e.t. (0-0)" (euro
#: order) and "1-1 a.e.t (1-1, 1-0), 1-3 pen." (wc2022 order).
_MID_TOKEN = r"(?:\d{1,2}-\d{1,2}|a\.e\.t\.?|pen\.?|\([^)]*\))"
_MATCH_LINE = re.compile(
    r"^\s*(?:(?P<time>\d{1,2}:\d{2})\s+)?"
    r"(?P<home>[^\d(@#]+?)\s+"
    r"(?P<mid>" + _MID_TOKEN + r"(?:\s*,?\s*" + _MID_TOKEN + r")*)\s+"
    r"(?P<away>[^\d(@#]+?)\s*$")


class ManifestError(RuntimeError):
    """A refusal — the manifest cannot be built or does not verify."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------- openfootball
def fetch_source(url: str, cache_dir: Path = RAW_CACHE_DIR) -> tuple:
    """Fetch (or reuse) one openfootball file; returns (text, sha256).

    The bytes are archived content-addressed so the committed manifest's
    provenance hashes stay checkable offline forever.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    index = cache_dir / "index.json"
    mapping = json.loads(index.read_text()) if index.exists() else {}
    if url in mapping:
        blob = cache_dir / f"{mapping[url]}.txt"
        if blob.exists():
            data = blob.read_bytes()
            if sha256_bytes(data) == mapping[url]:
                return data.decode("utf-8"), mapping[url]
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        data = resp.read()
    digest = sha256_bytes(data)
    (cache_dir / f"{digest}.txt").write_bytes(data)
    mapping[url] = digest
    index.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n")
    return data.decode("utf-8"), digest


def parse_openfootball(text: str, year: int, offset_hours: int) -> list:
    """Parse one openfootball fixture file into rows with UTC kickoffs.

    Grammar (verified against the three source files):
    - a day line ("Wed Jun 19") sets the current venue-local matchday;
    - a match line holds an optional HH:MM venue-local time, home, a
      score/annotation block, away, then " @ venue" (and maybe "# comment");
      a missing time inherits the previous match's (simultaneous kickoffs);
    - everything else (scorers, lineups, headers) has no " @ " with a score
      and is skipped.
    """
    rows = []
    current_day = None
    current_time = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        day_match = _DAY_LINE.match(line)
        if day_match:
            month, day = _MONTHS[day_match.group(1)], int(day_match.group(2))
            current_day = date_cls(year, month, day)
            current_time = None  # a new day never inherits yesterday's time
            continue
        if " @ " not in line:
            continue
        before_venue = line.split(" @ ", 1)[0]
        match = _MATCH_LINE.match(before_venue)
        if not match:
            continue
        if current_day is None:
            raise ManifestError(
                f"match line before any day line: {raw_line!r}")
        time_str = match.group("time") or current_time
        if time_str is None:
            raise ManifestError(
                f"match line has no time and none to inherit: {raw_line!r}")
        current_time = time_str
        hour, minute = (int(p) for p in time_str.split(":"))
        local = datetime(current_day.year, current_day.month,
                         current_day.day, hour, minute, tzinfo=timezone.utc)
        kickoff = local - timedelta(hours=offset_hours)
        home = OPENFOOTBALL_ALIASES.get(match.group("home").strip(),
                                        match.group("home").strip())
        away = OPENFOOTBALL_ALIASES.get(match.group("away").strip(),
                                        match.group("away").strip())
        rows.append({"date": current_day.isoformat(), "home": home,
                     "away": away, "kickoff_utc": kickoff})
    return rows


# ------------------------------------------------------------------ wc2026
_TIME_OFFSET = re.compile(r"^(\d{1,2}):(\d{2})\s+UTC([+-]\d{1,2})$")


def _kickoff_from_local(day: str, time_field: str) -> datetime:
    m = _TIME_OFFSET.match(str(time_field).strip())
    if not m:
        raise ManifestError(f"unparseable time field: {time_field!r}")
    hour, minute, offset = int(m.group(1)), int(m.group(2)), int(m.group(3))
    d = date_cls.fromisoformat(day)
    local = datetime(d.year, d.month, d.day, hour, minute,
                     tzinfo=timezone.utc)
    return local - timedelta(hours=offset)


def _venue_cities(venue: str) -> set:
    """Both spellings the store might have ingested for one venue string."""
    inner = re.search(r"\(([^)]+)\)", venue)
    outer = re.sub(r"\s*\([^)]*\)", "", venue).strip()
    cities = {outer}
    if inner:
        cities.add(inner.group(1).strip())
    return cities


def wc2026_kickoffs(tournament_path: Path = TOURNAMENT_2026_PATH,
                    store_path: Path = STORE_PATH) -> dict:
    """(date, home, away) -> kickoff for all 104 wc2026 fixtures.

    Group fixtures come straight from the yaml. Knockout fixtures carry
    placeholder slots, so their (real-team) identities come from the store's
    played rows joined by (date, city).
    """
    doc = yaml.safe_load(tournament_path.read_text())
    by_teams = {}
    ko_by_date_city = {}
    for fx in doc["fixtures"]:
        day = str(fx["date"])
        kickoff = _kickoff_from_local(day, fx["time"])
        if "group" in fx:  # group row: real team names, join by identity
            by_teams[(day, str(fx["home"]), str(fx["away"]))] = kickoff
        else:  # knockout row (`match: 73..104`): placeholder slots, join
            # the store's played row by (date, city-of-venue)
            for city in _venue_cities(str(fx.get("venue", ""))):
                key = (day, city)
                if key in ko_by_date_city:
                    raise ManifestError(
                        f"two knockout fixtures share (date, city) {key} — "
                        "the store join would be ambiguous")
                ko_by_date_city[key] = kickoff

    store = pd.read_parquet(store_path)
    store = store.assign(
        d=pd.to_datetime(store["date"]).dt.strftime("%Y-%m-%d"))
    ko_rows = store[(store["d"] >= "2026-06-28") & (store["d"] <= "2026-07-19")
                    & store["tournament"].str.contains("FIFA World Cup",
                                                       na=False)]
    for row in ko_rows.itertuples():
        key = (row.d, row.city)
        if key in ko_by_date_city:
            teams_key = (row.d, str(row.home_team), str(row.away_team))
            if teams_key in by_teams:
                raise ManifestError(
                    f"knockout fixture doubly resolved: {teams_key}")
            by_teams[teams_key] = ko_by_date_city[key]
    return by_teams


# ---------------------------------------------------------------- assembly
def load_inventory(path: Path = INVENTORY_PATH) -> list:
    doc = yaml.safe_load(path.read_text())
    return doc["fixtures"]


def build_manifest_fixtures() -> tuple:
    """Assemble all 217 rows; returns (fixtures, provenance)."""
    inventory = load_inventory()
    provenance = []

    kickoffs = {"wc2026": wc2026_kickoffs()}
    for pool in ("wc2022", "euro2024"):
        rows = []
        for src_pool, url, offset, year in OPENFOOTBALL_SOURCES:
            if src_pool != pool:
                continue
            text, digest = fetch_source(url)
            provenance.append({"pool": pool, "url": url, "sha256": digest})
            rows.extend(parse_openfootball(text, year, offset))
        kickoffs[pool] = {(r["date"], r["home"], r["away"]): r["kickoff_utc"]
                          for r in rows}

    fixtures, misses, flips = [], [], 0
    for inv in inventory:
        pool = inv["pool"]
        key = (str(inv["date"]), str(inv["home_team"]),
               str(inv["away_team"]))
        kickoff = kickoffs[pool].get(key)
        if kickoff is None:
            # martj42's home/away designation sometimes flips the official
            # one (e.g. store "Qatar v Netherlands" vs official
            # "Netherlands v Qatar"). Kickoff is order-independent; the
            # manifest keeps the INVENTORY's order — that is the identity
            # the scorer joins on.
            kickoff = kickoffs[pool].get((key[0], key[2], key[1]))
            if kickoff is not None:
                flips += 1
        if kickoff is None:
            misses.append((pool,) + key)
            continue
        fixtures.append({
            "fixture_id": str(inv["match_id"]), "pool": pool,
            "date": key[0], "home": key[1], "away": key[2],
            "kickoff_utc": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")})
    if misses:
        lines = "\n".join(f"  {m}" for m in misses)
        raise ManifestError(
            f"{len(misses)} inventory fixture(s) found no kickoff source "
            f"row (name/date mismatch?):\n{lines}")
    fixtures.sort(key=lambda f: f["fixture_id"])
    if flips:
        print(f"note: {flips} fixture(s) joined with home/away flipped "
              "(martj42 vs official designation); inventory order kept")
    return fixtures, provenance


# ------------------------------------------------------------------ checks
def verify_fixtures(fixtures: list) -> dict:
    """All refusal checks; returns the summary the manifest header records."""
    inventory = load_inventory()
    inv_ids = {str(f["match_id"]) for f in inventory}
    got_ids = {f["fixture_id"] for f in fixtures}
    if got_ids != inv_ids:
        raise ManifestError(
            f"fixture ids != inventory ids (missing {sorted(inv_ids - got_ids)[:4]}, "
            f"extra {sorted(got_ids - inv_ids)[:4]})")

    pool_counts = {}
    for fx in fixtures:
        pool_counts[fx["pool"]] = pool_counts.get(fx["pool"], 0) + 1
    if pool_counts != EXPECTED_POOL_COUNTS:
        raise ManifestError(
            f"pool counts {pool_counts} != expected {EXPECTED_POOL_COUNTS}")

    days = {}
    for fx in fixtures:
        days.setdefault(fx["pool"], set()).add(
            (SPORT_KEYS[fx["pool"]], fx["date"]))
    day_counts = {pool: len(v) for pool, v in days.items()}
    if day_counts != EXPECTED_DISCOVERY_DAYS:
        raise ManifestError(
            f"discovery-day counts {day_counts} != the plan's modeled "
            f"{EXPECTED_DISCOVERY_DAYS} — the G-A spend model would be wrong; "
            "STOP and reconcile before any live run")
    shared = days["wc2022"] & days["wc2026"]
    if shared:
        raise ManifestError(
            f"wc2022 and wc2026 share discovery days {sorted(shared)[:3]} — "
            "the modeled 77 assumed disjoint days on the shared sport key")

    rollovers = 0
    for fx in fixtures:
        kickoff = datetime.strptime(fx["kickoff_utc"],
                                    "%Y-%m-%dT%H:%M:%SZ").replace(
                                        tzinfo=timezone.utc)
        day = date_cls.fromisoformat(fx["date"])
        t_issue = datetime(day.year, day.month, day.day, T_ISSUE_UTC_HOUR,
                           tzinfo=timezone.utc)
        if not t_issue < kickoff:
            raise ManifestError(
                f"{fx['fixture_id']}: t_issue {t_issue} not strictly before "
                f"kickoff {kickoff}")
        offset = {"wc2022": 3, "euro2024": 2}.get(fx["pool"])
        if offset is not None:
            local_day = (kickoff + timedelta(hours=offset)).date()
            if local_day != day:
                raise ManifestError(
                    f"{fx['fixture_id']}: venue-local day {local_day} != "
                    f"manifest date {day}")
        if kickoff.date() != day:
            rollovers += 1
    if rollovers != EXPECTED_UTC_ROLLOVERS:
        raise ManifestError(
            f"UTC-rollover count {rollovers} != the known "
            f"{EXPECTED_UTC_ROLLOVERS} (finding-7 population)")

    clv_checked = _crosscheck_clv(fixtures)
    return {"n_fixtures": len(fixtures), "discovery_days": day_counts,
            "utc_rollovers": rollovers, "clv_kickoffs_checked": clv_checked}


def _crosscheck_clv(fixtures: list, cache_path: Path = CLV_CACHE_PATH) -> int:
    """Every kickoff the Phase-4 CLV cache knows (wc2022 AND euro2024
    entries, kickoffs straight from The Odds API) must match exactly.

    Keys are orderless: the manifest keeps martj42's home/away designation,
    the cache keeps the API's, and they disagree on a handful of fixtures —
    but a (date, {teams}) pair is unique in both."""
    if not cache_path.exists():
        raise ManifestError(f"CLV cache missing at {cache_path} — the "
                            "Odds-API kickoff cross-check cannot run")
    cache = json.loads(cache_path.read_text())
    by_key = {}
    for f in fixtures:
        by_key[(f["date"], frozenset((f["home"], f["away"])))] = f
    checked = 0
    windows = (("2022-11-20", "2022-12-18"), ("2024-06-14", "2024-07-14"),
               ("2026-06-11", "2026-07-19"))
    for entry in cache.values():
        home = ODDS_API_ALIASES.get(entry["home"], entry["home"])
        away = ODDS_API_ALIASES.get(entry["away"], entry["away"])
        kickoff = entry["kickoff"].replace("+00:00", "Z")
        day = kickoff.split("T", 1)[0]
        if not any(lo <= day <= hi for lo, hi in windows):
            continue  # cache also holds non-eval fixtures (e.g. NL games)
        fx = by_key.get((day, frozenset((home, away))))
        if fx is None:
            # cache day is the UTC day; Qatar/Germany kickoffs never roll,
            # so a within-window miss is a real name mismatch
            raise ManifestError(
                f"CLV cache fixture not found in manifest: "
                f"{day} {home} v {away}")
        if fx["kickoff_utc"] != kickoff:
            raise ManifestError(
                f"kickoff mismatch for {home} v {away} {day}: manifest "
                f"{fx['kickoff_utc']} vs Odds-API (CLV cache) {kickoff}")
        checked += 1
    if checked == 0:
        raise ManifestError("CLV cross-check matched zero fixtures — "
                            "the check is vacuous, refuse")
    return checked


# ---------------------------------------------------------------- emission
def emit(out_path: Path = OUT_PATH) -> dict:
    fixtures, provenance = build_manifest_fixtures()
    summary = verify_fixtures(fixtures)
    doc = {
        "derived_by": "scripts/oa_eval_manifest.py",
        "inventory": str(INVENTORY_PATH),
        "sources": ({"file": str(TOURNAMENT_2026_PATH),
                     "role": "wc2026 venue-local date + time + UTC offset"},
                    {"file": str(STORE_PATH),
                     "role": "wc2026 knockout identities via (date, city)"},
                    *({"url": p["url"], "sha256": p["sha256"],
                       "role": f"{p['pool']} kickoffs (openfootball, "
                               "venue-local times, fixed offset)"}
                      for p in provenance),
                    {"file": str(CLV_CACHE_PATH),
                     "role": "wc2022 kickoff cross-check (Odds-API ground "
                             "truth, exact-match required)"}),
        "checks": summary,
        "n_fixtures": len(fixtures),
        "fixtures": fixtures,
    }
    header = (
        "# OA eval-set acquisition manifest — the 217 scored fixtures WITH\n"
        "# kickoff_utc, consumed by scripts/oa_acquire.py --fixtures.\n"
        "# DERIVED — regenerate with `oa_eval_manifest.py --emit`; do not\n"
        "# edit by hand. kickoff_utc is load-bearing (the T-24h snapshot\n"
        "# instant is baked into journal call ids). date is the venue-LOCAL\n"
        "# matchday (finding 7), never commence_time.date().\n")
    out_path.write_text(header + yaml.safe_dump(doc, sort_keys=False,
                                                allow_unicode=True))
    return summary


def verify_committed(path: Path = OUT_PATH) -> dict:
    if not path.exists():
        raise ManifestError(f"no manifest at {path}; run --emit")
    doc = yaml.safe_load(path.read_text())
    return verify_fixtures(doc["fixtures"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--emit", action="store_true",
                        help="(re)build the manifest from sources")
    args = parser.parse_args(argv)
    try:
        summary = emit() if args.emit else verify_committed()
    except ManifestError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    action = "emitted" if args.emit else "verified"
    print(f"{action} {OUT_PATH}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
