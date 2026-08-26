"""The one-command live cycle: sequencing, sourcing, cross-checking, refusal.

WHAT THESE TESTS ARE ABOUT. :mod:`epl.livecycle` computes no forecast, no
table and no score of its own — every number it reports is produced by
machinery that already has its own suite. What is under test here is the part
that has never had one: the ORDER the steps run in, the two clocks they run
under, the rule that decides a result is real enough to ingest, and the
refusals that fire instead of a guess.

CI-SAFE BY CONSTRUCTION. Every source is injected: the two result fetchers, the
odds fetcher, and the four heavy steps (forecast, check, matchboard score,
shadow score) are parameters with the real ones as defaults. No test here opens
a socket, and none of them runs a simulation. The tests that assert the
DEFAULTS are the real callables read them without calling them.

The season is always a writable copy of ``epl/season/`` with its live ledgers
emptied — the tracked one fills up weekly for nine months, and a test about
ingest mechanics must not break the week MW7 lands.
"""
from __future__ import annotations

import datetime as _dt
import itertools
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

from epl import (leaguesim, livecycle, oddscapture, paths,
                 season as season_mod, simcli)

SEASON = "2026/27"
SEASON_CODE = "2627"

#: The wall-clock instant every test runs "at". `run_cycle` takes `now` as an
#: INPUT — the library reads no clock, the CLI boundary does — so this is the
#: only clock in the suite and nothing here is a function of when it ran.
NOW = pd.Timestamp("2026-08-25T18:20:31Z")


# ==========================================================================
# fixtures and builders
# ==========================================================================

def _season_copy(tmp_path, name: str = "season") -> Path:
    """A writable copy of `epl/season/` with its LIVE ledgers reset to empty.

    Same helper, same reason, as `test_simcli._season_copy`: the copy protects
    the repo from the tests, and emptying the ledgers protects the tests from
    the repo.
    """
    root = tmp_path / name
    shutil.copytree(season_mod.SEASON_ROOT, root)
    for season_dir in root.iterdir():
        if season_dir.is_dir():
            for ledger in ("results_ledger.jsonl", "kickoff_amendments.jsonl"):
                path = season_dir / ledger
                if path.exists():
                    path.write_text("")
    return root


#: Matchweek 1 exactly as the vendored openfootball file prints it — the same
#: day headers, the same kickoff times, the same club long forms. Copied rather
#: than invented so that a synthetic re-ingest moves no kickoff and appends no
#: amendment: a test that quietly rewrote the calendar would be testing a
#: different season from the one the operator runs.
MW1 = (
    ("Fri Aug 21 2026", (("20:00", "Arsenal FC", "Coventry City FC"),)),
    ("Sat Aug 22", (("12:30", "Hull City AFC", "Manchester United FC"),
                    ("15:00", "Ipswich Town FC", "Sunderland AFC"),
                    (None, "Nottingham Forest FC", "Leeds United FC"),
                    (None, "Everton FC", "Crystal Palace FC"),
                    ("17:30", "Brentford FC", "Tottenham Hotspur FC"))),
    ("Sun Aug 23", (("14:00", "Manchester City FC", "AFC Bournemouth"),
                    (None, "Brighton & Hove Albion FC", "Aston Villa FC"),
                    ("16:30", "Newcastle United FC", "Liverpool FC"))),
    ("Mon Aug 24", (("20:00", "Fulham FC", "Chelsea FC"),)),
)

#: Matchweek 2, same source, same shape — the round that arrives with MW1
#: already on the ledger, which is the ordinary weekly picture and the one the
#: MW1-only fixtures could never reach.
MW2 = (
    ("Sat Aug 29", (("15:00", "Liverpool FC", "Nottingham Forest FC"),
                    (None, "Manchester United FC", "Ipswich Town FC"),
                    (None, "Sunderland AFC", "Fulham FC"),
                    (None, "Crystal Palace FC", "Manchester City FC"),
                    (None, "Chelsea FC", "Brighton & Hove Albion FC"),
                    (None, "Aston Villa FC", "Arsenal FC"),
                    (None, "Tottenham Hotspur FC", "Newcastle United FC"),
                    (None, "Leeds United FC", "Brentford FC"),
                    (None, "AFC Bournemouth", "Everton FC"),
                    (None, "Coventry City FC", "Hull City AFC"))),
)

#: fixture id -> (kickoff date, football-data short names) for the same ten.
MW1_META = {
    "2627:arsenal:coventry": ("21/08/2026", "Arsenal", "Coventry"),
    "2627:hull:man_united": ("22/08/2026", "Hull", "Man United"),
    "2627:ipswich:sunderland": ("22/08/2026", "Ipswich", "Sunderland"),
    "2627:nottm_forest:leeds": ("22/08/2026", "Nott'm Forest", "Leeds"),
    "2627:everton:crystal_palace": ("22/08/2026", "Everton", "Crystal Palace"),
    "2627:brentford:tottenham": ("22/08/2026", "Brentford", "Tottenham"),
    "2627:man_city:bournemouth": ("23/08/2026", "Man City", "Bournemouth"),
    "2627:brighton:aston_villa": ("23/08/2026", "Brighton", "Aston Villa"),
    "2627:newcastle:liverpool": ("23/08/2026", "Newcastle", "Liverpool"),
    "2627:fulham:chelsea": ("24/08/2026", "Fulham", "Chelsea"),
}

MW2_META = {
    "2627:liverpool:nottm_forest": ("29/08/2026", "Liverpool", "Nott'm Forest"),
    "2627:man_united:ipswich": ("29/08/2026", "Man United", "Ipswich"),
    "2627:sunderland:fulham": ("29/08/2026", "Sunderland", "Fulham"),
    "2627:crystal_palace:man_city": ("29/08/2026", "Crystal Palace", "Man City"),
    "2627:chelsea:brighton": ("29/08/2026", "Chelsea", "Brighton"),
    "2627:aston_villa:arsenal": ("29/08/2026", "Aston Villa", "Arsenal"),
    "2627:tottenham:newcastle": ("29/08/2026", "Tottenham", "Newcastle"),
    "2627:leeds:brentford": ("29/08/2026", "Leeds", "Brentford"),
    "2627:bournemouth:everton": ("29/08/2026", "Bournemouth", "Everton"),
    "2627:coventry:hull": ("29/08/2026", "Coventry", "Hull"),
}

ALL_META = {**MW1_META, **MW2_META}

MW2_SCORES = {
    "2627:liverpool:nottm_forest": (3, 1),
    "2627:crystal_palace:man_city": (1, 2),
    "2627:bournemouth:everton": (0, 0),
}

#: The ten real MW1 scorelines, as both live sources carry them.
MW1_SCORES = {
    "2627:arsenal:coventry": (3, 0),
    "2627:hull:man_united": (2, 0),
    "2627:ipswich:sunderland": (2, 1),
    "2627:nottm_forest:leeds": (0, 1),
    "2627:everton:crystal_palace": (2, 0),
    "2627:brentford:tottenham": (3, 0),
    "2627:man_city:bournemouth": (2, 1),
    "2627:brighton:aston_villa": (4, 0),
    "2627:newcastle:liverpool": (2, 2),
    "2627:fulham:chelsea": (2, 3),
}


def _fid(home_long: str, away_long: str) -> str:
    from epl import teams
    return season_mod.fixture_id(SEASON_CODE, teams.team_key(home_long),
                                 teams.team_key(away_long))


def openfootball_text(scores: dict[str, tuple[int, int]] | None = None) -> str:
    """The MW1 block in the layout openfootball ACTUALLY writes.

    `v`-separated, score APPENDED at the end of the line, half-time bracket
    included — the layout that crashed the ingest until 287a64b, and the reason
    this builder is not the middle-layout one every older fixture was written in.
    """
    scores = {} if scores is None else scores
    lines = ["= English Premier League 2026/27", ""]
    for matchday, block in ((1, MW1), (2, MW2)):
        lines.append(f"▪ Matchday {matchday}")
        lines.extend(_matchday_lines(block, scores))
    return "\n".join(lines) + "\n"


def _matchday_lines(block, scores) -> list[str]:
    lines: list[str] = []
    for header, matches in block:
        lines.append(f"  {header}")
        for time, home, away in matches:
            slot = f"    {time:>5}  " if time else "           "
            fid = _fid(home, away)
            # openfootball pads the home name to a column and keeps ONE space
            # before `v` when the name overruns it — `Brighton & Hove Albion
            # FC v Aston Villa FC` is the real line, and the single space is
            # exactly what the parser's two-space discriminator has to survive.
            left = home.ljust(24) if len(home) < 24 else home + " "
            body = f"{left}v {away.ljust(24)}  {_score(scores.get(fid))}"
            lines.append(body_line(slot, body))
    return lines


def _score(pair) -> str:
    if pair is None:
        return ""
    hg, ag = pair
    return f"{hg}-{ag} ({hg}-{ag})"


def body_line(slot: str, body: str) -> str:
    return (slot + body).rstrip()


E0_COLUMNS = ("Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG",
              "FTR", "AvgH", "AvgD", "AvgA")


def football_data_text(scores: dict[str, tuple[int, int]] | None = None,
                       *, dates: dict[str, str] | None = None) -> str:
    """An `E0.csv` with the columns and the dd/mm/yyyy dates the feed publishes.

    Short club names on purpose: `Nott'm Forest` is the spelling that has to go
    through the repository's own alias registry, and a reader that slugged it
    would invent a second Nottingham Forest.
    """
    scores = {} if scores is None else scores
    dates = {} if dates is None else dates
    rows = [",".join(E0_COLUMNS)]
    for fid, (date, home, away) in ALL_META.items():
        if fid not in scores:
            continue
        hg, ag = scores[fid]
        ftr = "H" if hg > ag else ("A" if ag > hg else "D")
        rows.append(",".join([
            "E0", dates.get(fid, date), "15:00", f'"{home}"', f'"{away}"',
            str(hg), str(ag), ftr, "2.10", "3.40", "3.20"]))
    return "\r\n".join(rows) + "\r\n"


def _fetchers(of_text: str | None = None, e0_text: str | None = None):
    """Injected source adapters, recording the URL they were handed.

    Both default to a source carrying NO results — the fixture list and an
    empty E0 — which is what a source looks like before a round is played.
    """
    seen: dict[str, str] = {}

    def openfootball(url: str) -> str:
        seen["openfootball"] = url
        return openfootball_text() if of_text is None else of_text

    def football_data(url: str) -> str:
        seen["football-data"] = url
        return football_data_text() if e0_text is None else e0_text

    return openfootball, football_data, seen


# ==========================================================================
# 1. the source adapters — the layouts the two feeds actually publish
# ==========================================================================

def test_the_openfootball_reader_reads_the_end_layout_the_source_writes():
    """END layout, `v`-separated, score appended. This is the shape that broke
    the ingest before 287a64b, so it is the shape the reader is tested on."""
    got = livecycle.read_openfootball(openfootball_text(MW1_SCORES), SEASON_CODE)
    assert set(got) == set(MW1_SCORES)
    row = got["2627:brighton:aston_villa"]
    assert (row.hg, row.ag) == (4, 0)
    assert row.date == "2026-08-23"
    assert row.source == livecycle.SOURCE_A


def test_the_openfootball_reader_returns_nothing_when_the_source_lags():
    """Zero results is NORMAL for openfootball and is not an error: the file
    carries the whole season's fixtures from the day it is published."""
    assert livecycle.read_openfootball(openfootball_text(), SEASON_CODE) == {}


def test_the_football_data_reader_uses_the_repo_alias_mapping():
    """`Nott'm Forest` resolves through `epl.teams`, not through a slugger.

    A reader that invented its own mapping would give one club two keys the
    first time the feed changed a spelling, and the model would look fine while
    quietly splitting that club's history in half.
    """
    got = livecycle.read_football_data(football_data_text(MW1_SCORES), SEASON_CODE)
    assert set(got) == set(MW1_SCORES)
    row = got["2627:nottm_forest:leeds"]
    assert (row.hg, row.ag) == (0, 1)
    assert row.date == "2026-08-22"                 # dd/mm/yyyy, read as such
    assert row.source == livecycle.SOURCE_B


def test_the_football_data_reader_skips_a_row_with_no_score_yet():
    """The feed carries a fixture row before it carries the result."""
    text = football_data_text({"2627:arsenal:coventry": (3, 0)})
    text += 'E0,28/08/2026,20:00,"Crystal Palace","Man City",,,,2.10,3.40,3.20\r\n'
    got = livecycle.read_football_data(text, SEASON_CODE)
    assert set(got) == {"2627:arsenal:coventry"}


def test_the_football_data_reader_ignores_other_divisions():
    text = football_data_text({"2627:arsenal:coventry": (3, 0)})
    text += 'E1,22/08/2026,15:00,"Hull","Leeds",1,1,D,2.10,3.40,3.20\r\n'
    assert set(livecycle.read_football_data(text, SEASON_CODE)) == {
        "2627:arsenal:coventry"}


def test_an_unregistered_club_spelling_is_refused_not_slugged():
    text = 'Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\r\nE0,22/08/2026,"Man Utd FC","Leeds",1,0\r\n'
    with pytest.raises(livecycle.SourceMalformed, match="Man Utd FC"):
        livecycle.read_football_data(text, SEASON_CODE)


def test_a_football_data_file_missing_a_required_column_is_refused():
    text = 'Div,Date,HomeTeam,AwayTeam\r\nE0,22/08/2026,"Hull","Leeds"\r\n'
    with pytest.raises(livecycle.SourceMalformed, match="FTHG"):
        livecycle.read_football_data(text, SEASON_CODE)


def test_the_two_source_urls_come_from_the_repo_not_from_a_new_constant():
    """The openfootball URL is the manifest's own `fixtures_source.url` and the
    E0 URL is `epl.fetch`'s published pattern. Neither is retyped here."""
    from epl import fetch
    season_obj = season_mod.Season.load(SEASON)
    assert livecycle.openfootball_url(season_obj) == \
        season_obj.manifest.raw["fixtures_source"]["url"]
    assert livecycle.football_data_url(season_obj) == \
        fetch.BASE_URL.format(season_code=SEASON_CODE)


def test_the_real_fetchers_are_the_defaults():
    """The injectable parameters exist for the tests; the operator gets the
    network. Read, never called."""
    assert livecycle.DEFAULT_FETCHERS[livecycle.SOURCE_A] is \
        livecycle.fetch_openfootball
    assert livecycle.DEFAULT_FETCHERS[livecycle.SOURCE_B] is \
        livecycle.fetch_football_data


# ==========================================================================
# 2. the two clocks
# ==========================================================================

def test_the_knowledge_clock_is_never_before_the_ingest_that_preceded_it():
    """THE MW1 MISTAKE, as an assertion.

    `--observed-by` at minute precision, FLOORED, lands before an ingest
    stamped seconds earlier in the same minute — and a fit blind to the ingest
    that just ran is the bundle that had to be discarded on MW1 day. Ceiling,
    not flooring, and the ingest instant is an input to the choice.
    """
    ingest_at = pd.Timestamp("2026-08-25T12:55:44")
    got = livecycle.knowledge_clock(pd.Timestamp("2026-08-25T12:55:03"), ingest_at)
    assert got >= ingest_at
    assert got == pd.Timestamp("2026-08-25T12:56:00")
    assert got.second == 0                              # minute precision


def test_the_knowledge_clock_ceils_a_later_now_too():
    got = livecycle.knowledge_clock(pd.Timestamp("2026-08-25T18:20:31"),
                                    pd.Timestamp("2026-08-25T12:55:44"))
    assert got == pd.Timestamp("2026-08-25T18:21:00")


def test_the_knowledge_clock_leaves_an_exact_minute_alone():
    got = livecycle.knowledge_clock(pd.Timestamp("2026-08-25T18:21:00"),
                                    pd.Timestamp("2026-08-25T12:55:44"))
    assert got == pd.Timestamp("2026-08-25T18:21:00")


# ==========================================================================
# 3. the cross-check
# ==========================================================================

_COPIES = itertools.count()


def _cross(tmp_path, of_scores, e0_scores, **kwargs):
    """One cross-check over a virgin season. A fresh copy each call, so a test
    that cross-checks twice does not collide with its own first season."""
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    season_obj = season_mod.Season.load(SEASON, root=root)
    return livecycle.cross_check(
        season_obj,
        livecycle.read_openfootball(openfootball_text(of_scores), SEASON_CODE),
        livecycle.read_football_data(football_data_text(e0_scores), SEASON_CODE),
        **kwargs)


def test_where_both_sources_agree_the_result_is_ingestable(tmp_path):
    plan = _cross(tmp_path, MW1_SCORES, MW1_SCORES)
    assert set(plan.agreed) == set(MW1_SCORES)
    assert plan.single_source == {}
    assert plan.already_resolved == ()
    assert set(plan.ingestable) == set(MW1_SCORES)


def test_a_disagreement_on_a_covered_fixture_is_an_unconditional_stop(tmp_path):
    """Named fixture, BOTH scores, and no flag turns it off."""
    wrong = dict(MW1_SCORES, **{"2627:fulham:chelsea": (2, 2)})
    with pytest.raises(livecycle.SourceDisagreement) as exc:
        _cross(tmp_path, MW1_SCORES, wrong)
    message = str(exc.value)
    assert "2627:fulham:chelsea" in message
    assert "2-3" in message and "2-2" in message
    assert livecycle.SOURCE_A in message and livecycle.SOURCE_B in message

    # ...and --allow-single-source is not a way around it.
    with pytest.raises(livecycle.SourceDisagreement):
        _cross(tmp_path, MW1_SCORES, wrong, allow_single_source=True)


def test_a_disagreement_about_the_DATE_played_is_a_stop_too(tmp_path):
    """The scoreline is not the only thing a ledger row records: `date_played`
    is what places the result on one side of a cutoff, and picking one source's
    date over the other's would be the cycle guessing."""
    root = _season_copy(tmp_path)
    season_obj = season_mod.Season.load(SEASON, root=root)
    with pytest.raises(livecycle.SourceDisagreement, match="date"):
        livecycle.cross_check(
            season_obj,
            livecycle.read_openfootball(openfootball_text(MW1_SCORES), SEASON_CODE),
            livecycle.read_football_data(
                football_data_text(MW1_SCORES,
                                   dates={"2627:fulham:chelsea": "25/08/2026"}),
                SEASON_CODE))


def test_a_fixture_only_one_source_covers_is_a_coverage_gap_by_default(tmp_path):
    """Default OFF: missing-from-one STOPs and LISTS the uncovered fixtures."""
    thin = {k: v for k, v in MW1_SCORES.items() if k != "2627:fulham:chelsea"}
    with pytest.raises(livecycle.CoverageGap) as exc:
        _cross(tmp_path, MW1_SCORES, thin)
    assert "2627:fulham:chelsea" in str(exc.value)
    assert "allow-single-source" in str(exc.value)


def test_the_flag_lets_a_single_covered_source_through(tmp_path):
    thin = {k: v for k, v in MW1_SCORES.items() if k != "2627:fulham:chelsea"}
    plan = _cross(tmp_path, MW1_SCORES, thin, allow_single_source=True)
    assert set(plan.agreed) == set(thin)
    assert set(plan.single_source) == {"2627:fulham:chelsea"}
    assert plan.single_source["2627:fulham:chelsea"].source == livecycle.SOURCE_A


def test_a_lagging_openfootball_leaves_every_fixture_single_sourced(tmp_path):
    """Zero results from A is normal, and under the default it is a STOP that
    lists ten fixtures rather than an ingest of ten unconfirmed ones."""
    with pytest.raises(livecycle.CoverageGap) as exc:
        _cross(tmp_path, {}, MW1_SCORES)
    assert str(exc.value).count("2627:") == len(MW1_SCORES)

    plan = _cross(tmp_path, {}, MW1_SCORES, allow_single_source=True)
    assert set(plan.single_source) == set(MW1_SCORES)
    assert all(r.source == livecycle.SOURCE_B
               for r in plan.single_source.values())


def test_a_result_the_ledger_already_resolves_is_nothing_to_do(tmp_path):
    """THE DAILY CASE. openfootball catches up and carries a round the ledger
    resolved days ago; agreeing with what is already on file is not new work
    and is certainly not a conflict."""
    root = _season_copy(tmp_path)
    _ingest_manual(root, MW1_SCORES)
    season_obj = season_mod.Season.load(SEASON, root=root)
    plan = livecycle.cross_check(
        season_obj,
        livecycle.read_openfootball(openfootball_text(MW1_SCORES), SEASON_CODE),
        livecycle.read_football_data(football_data_text(MW1_SCORES), SEASON_CODE))
    assert plan.agreed == {}
    assert plan.single_source == {}
    assert plan.ingestable == {}
    assert set(plan.already_resolved) == set(MW1_SCORES)


def test_a_source_that_disagrees_with_the_resolved_ledger_is_a_ledger_conflict(
        tmp_path):
    """Both sources now say 3-3 for a fixture the ledger resolves 2-3. That is
    an upstream correction or a bad ledger row, and either way it is a decision
    a human makes — the cycle names it and stops."""
    root = _season_copy(tmp_path)
    _ingest_manual(root, MW1_SCORES)
    season_obj = season_mod.Season.load(SEASON, root=root)
    revised = dict(MW1_SCORES, **{"2627:fulham:chelsea": (3, 3)})
    with pytest.raises(livecycle.LedgerConflict) as exc:
        livecycle.cross_check(
            season_obj,
            livecycle.read_openfootball(openfootball_text(revised), SEASON_CODE),
            livecycle.read_football_data(football_data_text(revised), SEASON_CODE))
    assert "2627:fulham:chelsea" in str(exc.value)
    assert "2-3" in str(exc.value) and "3-3" in str(exc.value)


def _kickoff(fid: str) -> str:
    """The MW1 kickoff day, read the way the feed writes it: dd/mm/yyyy."""
    return _dt.datetime.strptime(
        ALL_META[fid][0], "%d/%m/%Y").date().isoformat()


def _ingest_manual(root: Path, scores: dict[str, tuple[int, int]],
                   observed_at: str = "2026-08-25T12:55:44") -> None:
    """Put results in the ledger the way the operator did: through the season's
    own manual ingest, so the rows are rows its validation accepted."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manual.jsonl"
        path.write_text("".join(
            json.dumps({"fixture_id": fid,
                        "date_played": _kickoff(fid),
                        "hg": hg, "ag": ag}) + "\n"
            for fid, (hg, ag) in scores.items()))
        simcli.ingest_results(season=SEASON, root=root, manual_file=path,
                              write=True, observed_at=observed_at, verbose=False)


# ==========================================================================
# 4. the check-report parser
# ==========================================================================

def _report(**over) -> dict:
    """A check report in the shape `simcli.check_issuance` returns for a live
    bundle: everything reproduces, and the ONE designed refusal stands."""
    base = {
        "PASS": False,
        "headline": "FAIL",
        "record_failed": [], "record_refused": [],
        "failed": [], "refused": ["dc_native"],
        "arms": {
            "dc_native": {"status": "REFUSED", "criterion_failed": [],
                          "criterion_refused": [
                              "parity_reference_is_production_grid"]},
            "dc_wdl_bridge": {"status": "PASS", "criterion_failed": [],
                              "criterion_refused": []},
            "elo_wdl_bridge": {"status": "PASS", "criterion_failed": [],
                               "criterion_refused": []},
        },
    }
    base.update(over)
    return base


def test_the_designed_refusal_is_what_the_parser_accepts():
    got = livecycle.parse_check_report(_report())
    assert got["exit_code"] == 4
    assert got["refused"] == ["dc_native"]
    assert got["designed_refusal"] is True


def test_a_failed_arm_is_a_check_unexpected():
    with pytest.raises(livecycle.CheckUnexpected, match="dc_wdl_bridge"):
        livecycle.parse_check_report(_report(failed=["dc_wdl_bridge"]))


def test_a_failed_record_criterion_is_a_check_unexpected():
    with pytest.raises(livecycle.CheckUnexpected, match="record_digest"):
        livecycle.parse_check_report(_report(record_failed=["record_digest"]))


def test_a_refused_record_criterion_is_a_check_unexpected():
    with pytest.raises(livecycle.CheckUnexpected, match="matchboard_anchored"):
        livecycle.parse_check_report(_report(record_refused=["matchboard_anchored"]))


def test_a_second_refused_arm_is_a_check_unexpected():
    with pytest.raises(livecycle.CheckUnexpected, match="dc_wdl_bridge"):
        livecycle.parse_check_report(
            _report(refused=["dc_native", "dc_wdl_bridge"]))


def test_an_extra_refused_criterion_inside_the_expected_arm_is_a_stop():
    """`dc_native` REFUSED is expected; refused for a SECOND reason is not, and
    a parser that only counted arms would have called this the designed one."""
    report = _report()
    report["arms"]["dc_native"]["criterion_refused"] = [
        "parity_reference_is_production_grid", "retained_rows"]
    with pytest.raises(livecycle.CheckUnexpected, match="retained_rows"):
        livecycle.parse_check_report(report)


def test_a_clean_pass_is_ALSO_refused_because_it_is_not_what_was_designed():
    """The expectation is exact in both directions. A bundle that suddenly
    passes in full means the parity reference became reconstructable, which is
    a change in the world the operator has to rule on — not a quiet green."""
    with pytest.raises(livecycle.CheckUnexpected, match="PASS"):
        livecycle.parse_check_report(
            _report(PASS=True, headline="PASS", refused=[],
                    arms={"dc_native": {"status": "PASS", "criterion_failed": [],
                                        "criterion_refused": []}}))


# ==========================================================================
# 5. the journal
# ==========================================================================

def test_the_journal_is_one_canonical_line_per_run_and_append_only(tmp_path):
    path = tmp_path / "journal.jsonl"
    first = livecycle.append_journal(path, {"at": "2026-08-25T18:20:31",
                                            "outcome": "no-op", "b": 1, "a": 2})
    second = livecycle.append_journal(path, {"at": "2026-08-26T18:20:31",
                                             "outcome": "ran"})
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert lines[0] == first == leaguesim.canonical_json(
        {"a": 2, "at": "2026-08-25T18:20:31", "b": 1, "outcome": "no-op",
         "chain": livecycle.JOURNAL_GENESIS})
    assert json.loads(lines[1])["outcome"] == "ran"
    # append-only: the first line is byte-identical after the second write
    assert lines[0] == first
    assert second != first


# ==========================================================================
# 6. the launch-mode guard
# ==========================================================================

def test_a_heredoc_launch_is_refused_before_anything_runs(monkeypatch):
    """`python - <<EOF` kills the gate's parallel leg on macOS: the pool comes
    back `BrokenProcessPool` and the serial, repeat and chunk digests are
    identical because nothing ever ran in parallel. The refusal is at the door,
    not before the forecast — a cycle that ingested and then refused would
    leave the operator half-done."""
    monkeypatch.setattr(sys, "argv", ["-"])
    with pytest.raises(livecycle.LaunchModeUnsafe, match="python -m epl.livecycle"):
        livecycle.refuse_an_unsafe_launch()

    monkeypatch.setattr(sys, "argv", ["-c"])
    with pytest.raises(livecycle.LaunchModeUnsafe):
        livecycle.refuse_an_unsafe_launch()


def test_a_module_launch_is_allowed(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["/x/epl/livecycle.py", "--dry-run"])
    assert livecycle.refuse_an_unsafe_launch() is None


# ==========================================================================
# 7. the cycle
# ==========================================================================

class _Steps:
    """Recording stand-ins for the four heavy steps.

    The real ones are `simcli.forecast`, `simcli.check_issuance`,
    `simcli.derive_matchboard` and `epl.recal`'s `score`; each has its own
    suite and none of them is re-tested here. What IS under test is that the
    cycle calls them, in order, with the right clocks and the right bundle.
    """

    def __init__(self, *, gate_pass: bool = True, report=None):
        self.calls: list[tuple[str, dict]] = []
        self.gate_pass = gate_pass
        self.report = _report() if report is None else report

    def as_dict(self) -> dict:
        return {"forecast": self.forecast, "check": self.check,
                "matchboard": self.matchboard, "shadow": self.shadow}

    def forecast(self, **kw):
        self.calls.append(("forecast", kw))
        directory = simcli.issuance_dir(kw["season"], kw["cutoff"], kw["out_root"])
        directory.mkdir(parents=True, exist_ok=True)
        record = {"season": kw["season"], "cutoff": str(kw["cutoff"]),
                  "observed_by": str(kw["observed_by"]),
                  "published_arm": "dc_native", "directory": str(directory),
                  "record_digest": "f" * 64,
                  "gate": {"PASS": self.gate_pass, "failed": [], "skipped": []}}
        (directory / "issuance.json").write_text(json.dumps(record))
        return record

    def check(self, directory, **kw):
        self.calls.append(("check", {"directory": str(directory), **kw}))
        return self.report

    def matchboard(self, **kw):
        # The results file lives in a temporary directory the cycle owns and
        # deletes, so it is read HERE — while the step is running, which is the
        # only moment it exists. That is the file's whole life: an input to one
        # scoring call, never an artifact.
        rows = _results_rows(kw["results_file"])
        self.calls.append(("matchboard", {**kw, "rows": rows}))
        return {"appended": len(rows), "repeated": 0,
                "json": "reports/derived.json", "md": "reports/derived.md"}

    def shadow(self, **kw):
        rows = _results_rows(kw["results_file"])
        self.calls.append(("shadow", {**kw, "rows": rows}))
        return {"appended": len(rows), "repeated": 0, "ledger": str(kw["ledger"])}

    def named(self, name: str) -> list[dict]:
        return [kw for called, kw in self.calls if called == name]


def _results_rows(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip()]


def _with_prior_issuance(tmp_path, name: str = "2026-08-21"):
    """A written bundle that priced MW1 before it kicked off."""
    out_root = tmp_path / "issuances"
    directory = out_root / "2026_27" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "issuance.json").write_text(json.dumps({"season": SEASON}))
    # Both clocks at midnight, as the real MW0 bundle carries them: the
    # admissibility rule compares them against the kickoff DAY, so an
    # `observed_by` of 09:00 on the morning of the match is already too late.
    return {name: _board(name, f"{name} 00:00:00", f"{name} 00:00:00")}


def _cycle(tmp_path, *, of_scores=None, e0_scores=None, ledger=None,
           steps=None, prior="2026-08-21", **kwargs):
    """One `run_cycle` over a virgin season with every source injected.

    `prior` is the cutoff day of a bundle that priced MW1 before it kicked off
    — the one a newly ingested round is scored against. `None` leaves the
    issuance tree empty, which is what a dry run must not create.
    """
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    boards = _with_prior_issuance(tmp_path, prior) if prior else None
    if ledger:
        _ingest_manual(root, ledger)
    of_fetch, e0_fetch, seen = _fetchers(
        openfootball_text(MW1_SCORES if of_scores is None else of_scores),
        football_data_text(MW1_SCORES if e0_scores is None else e0_scores))
    steps = _Steps() if steps is None else steps
    call = {
        "now": NOW, "root": root, "out_root": tmp_path / "issuances",
        "derived_root": tmp_path / "derived",
        "shadow_ledger": tmp_path / "derived" / "shadow.jsonl",
        "journal": tmp_path / "journal.jsonl",
        "snapshot_dir": tmp_path / "snapshots",
        "fetchers": {livecycle.SOURCE_A: of_fetch,
                     livecycle.SOURCE_B: e0_fetch},
        "odds_fetcher": lambda url: _odds_csv(),
        "steps": steps.as_dict(),
        "board_reader": (lambda d: boards[Path(d).name]) if boards else None,
        "verbose": False,
    }
    call.update(kwargs)
    out = livecycle.run_cycle(**call)
    out["_root"] = root
    out["_steps"] = steps
    out["_urls"] = seen
    return out


def _prescored(tmp_path, fixtures=MW1_META, derived: str = "derived"):
    """File scorecard and shadow rows for `fixtures`, so the cycle has NO
    backlog. Without this a hand-ingested round is outstanding work and a
    "no-op" day correctly scores it — which is the whole point of the backlog
    fix, and makes "nothing was scored" a claim a test has to earn."""
    root = tmp_path / derived
    root.mkdir(parents=True, exist_ok=True)
    for name in (simcli.SCORECARD_FILENAME, "shadow.jsonl"):
        (root / name).write_text("".join(
            json.dumps({"fixture_id": fid, "run_digest": "a" * 64}) + "\n"
            for fid in fixtures), encoding="utf-8")
    return root


def _odds_csv() -> bytes:
    head = "Div,Date,HomeTeam,AwayTeam,AvgH,AvgD,AvgA"
    row = "E0,28/08/2026,Crystal Palace,Man City,2.10,3.40,3.20"
    return ("\n".join([head, *([row] * 30)]) + "\n").encode("utf-8")


def _board(directory_name: str, cutoff: str, observed_by: str,
           fixtures=MW1_META, run_digest: str = "a" * 64) -> dict:
    return {"season": SEASON, "cutoff": cutoff, "observed_by": observed_by,
            "run_digest": run_digest, "source_bundle": directory_name,
            "rows": [{"fixture_id": fid, "date": _kickoff(fid),
                      "home": fid.split(":")[1], "away": fid.split(":")[2],
                      "probs": {"home": 0.5, "draw": 0.3, "away": 0.2}}
                     for fid in fixtures]}


# --- the no-op day --------------------------------------------------------

def test_no_new_results_and_a_fresh_issuance_is_a_clean_no_op(tmp_path):
    """RUNNING IT DAILY MUST BE SAFE. Both sources carry a round the ledger
    already resolves, an issuance exists for today's cutoff, and the cycle
    writes nothing, calls nothing heavy, and exits 0."""
    out_root = tmp_path / "issuances"
    fresh = simcli.issuance_dir(SEASON, NOW.tz_convert(livecycle.SEASON_TIMEZONE)
                               .date().isoformat(), out_root)
    fresh.mkdir(parents=True)
    (fresh / "issuance.json").write_text(json.dumps({"season": SEASON}))

    _prescored(tmp_path)
    result = _cycle(tmp_path, ledger=MW1_SCORES)
    assert result["outcome"] == "no-op"
    assert result["ingested"]["fixtures"] == []
    assert result["issuance"] is None
    assert result["_steps"].calls == []
    assert result["already_resolved"]["n"] == len(MW1_SCORES)


def test_the_no_op_day_still_fetches_both_sources(tmp_path):
    """A no-op is a CONCLUSION, not a shortcut: the cycle can only know there
    is nothing new by asking both sources."""
    result = _cycle(tmp_path, ledger=MW1_SCORES)
    assert set(result["_urls"]) == {livecycle.SOURCE_A, livecycle.SOURCE_B}
    assert result["_urls"][livecycle.SOURCE_B].endswith("/2627/E0.csv")


# --- the ingest -----------------------------------------------------------

def test_agreeing_results_are_ingested_dry_first_then_written(tmp_path):
    result = _cycle(tmp_path)
    assert result["outcome"] == "ran"
    assert set(result["ingested"]["fixtures"]) == set(MW1_SCORES)
    assert result["ingested"]["written"] is True
    assert result["ingested"]["dry_run_rows"] == len(MW1_SCORES)

    ledger = (result["_root"] / "2026_27" / "results_ledger.jsonl").read_text()
    rows = [json.loads(line) for line in ledger.splitlines() if line.strip()]
    assert {r["fixture_id"] for r in rows} == set(MW1_SCORES)
    assert all(r["source"].startswith("openfootball@") for r in rows)


def test_a_single_sourced_result_is_written_through_the_manual_overlay(tmp_path):
    """openfootball lags, football-data has the round, the operator takes it on
    one source. It enters through the season's own hand-entry path — validated
    row by row — and says in its note which source it came from."""
    result = _cycle(tmp_path, of_scores={}, allow_single_source=True)
    rows = [json.loads(line) for line in
            (result["_root"] / "2026_27" / "results_ledger.jsonl"
             ).read_text().splitlines() if line.strip()]
    assert {r["fixture_id"] for r in rows} == set(MW1_SCORES)
    assert all(r["source"] == "manual" for r in rows)
    assert all(livecycle.SOURCE_B in r["note"] for r in rows)
    assert result["ingested"]["single_source"] == sorted(MW1_SCORES)


def test_a_coverage_gap_stops_before_anything_is_written(tmp_path):
    thin = {k: v for k, v in MW1_SCORES.items() if k != "2627:fulham:chelsea"}
    with pytest.raises(livecycle.CoverageGap):
        _cycle(tmp_path, e0_scores=thin)


def test_a_disagreement_stops_before_anything_is_written(tmp_path):
    wrong = dict(MW1_SCORES, **{"2627:fulham:chelsea": (9, 9)})
    with pytest.raises(livecycle.SourceDisagreement):
        _cycle(tmp_path, e0_scores=wrong)


# --- the two clocks, on a real cycle --------------------------------------

def test_the_forecast_is_handed_both_clocks_and_the_knowledge_one_is_later(
        tmp_path):
    """THE ASSERTION THIS BUILD EXISTS FOR. `--cutoff` is the fit's DATE
    boundary; `--observed-by` is the knowledge instant, and it is at or after
    the `observed_at` the ingest just stamped its rows with."""
    result = _cycle(tmp_path)
    call = result["_steps"].named("forecast")[0]
    assert call["cutoff"] == "2026-08-25"                # the season's own day
    observed_at = pd.Timestamp(result["observed_at"])
    observed_by = pd.Timestamp(call["observed_by"])
    assert observed_by >= observed_at
    assert observed_by.second == 0

    rows = [json.loads(line) for line in
            (result["_root"] / "2026_27" / "results_ledger.jsonl"
             ).read_text().splitlines() if line.strip()]
    assert all(pd.Timestamp(r["observed_at"]) <= observed_by for r in rows), (
        "the fit would be blind to the ingest that just ran — this is the MW1 "
        "bundle that had to be discarded")


def test_the_forecast_runs_every_arm(tmp_path):
    result = _cycle(tmp_path)
    assert tuple(result["_steps"].named("forecast")[0]["arms"]) == simcli.ARMS


def test_a_gate_that_does_not_pass_is_a_stop(tmp_path):
    with pytest.raises(livecycle.GateNotPassed, match="gate"):
        _cycle(tmp_path, steps=_Steps(gate_pass=False))


def test_no_new_results_but_a_stale_issuance_still_issues(tmp_path):
    """The matchday cadence is a FIT cadence: yesterday's issuance is not
    today's, whether or not a match was played."""
    result = _cycle(tmp_path, ledger=MW1_SCORES)
    assert result["ingested"]["fixtures"] == []
    assert result["issuance"] is not None
    assert result["outcome"] == "ran"


# --- the check ------------------------------------------------------------

def test_the_check_runs_on_the_bundle_just_written(tmp_path):
    result = _cycle(tmp_path)
    directory = result["issuance"]["directory"]
    assert result["_steps"].named("check")[0]["directory"] == directory
    assert result["check"]["exit_code"] == 4
    assert result["check"]["designed_refusal"] is True


def test_an_unexpected_check_result_stops_the_cycle(tmp_path):
    broken = _report(failed=["dc_wdl_bridge"])
    with pytest.raises(livecycle.CheckUnexpected):
        _cycle(tmp_path, steps=_Steps(report=broken))


# --- the scoring ----------------------------------------------------------

def test_the_cycle_scores_the_PRIOR_issuance_that_priced_the_fixtures(tmp_path):
    """Not the one it just issued — that one's clocks are after the kickoff and
    it never saw these matches unplayed."""
    result = _cycle(tmp_path)
    board_call = result["_steps"].named("matchboard")[0]
    assert Path(board_call["directory"]).name == "2026-08-21"
    rows = board_call["rows"]
    assert {r["fixture_id"] for r in rows} == set(MW1_SCORES)
    assert all(r["matchweek"] == 1 for r in rows)
    assert all(r["ingest"] for r in rows)
    assert result["scorecard"]["appended"] == len(MW1_SCORES)


def test_the_shadow_is_scored_from_the_same_bundle_and_the_same_rows(tmp_path):
    result = _cycle(tmp_path)
    board_call = result["_steps"].named("matchboard")[0]
    shadow_call = result["_steps"].named("shadow")[0]
    assert shadow_call["directory"] == board_call["directory"]
    assert shadow_call["rows"] == board_call["rows"]
    assert result["shadow"]["appended"] == len(MW1_SCORES)


def test_a_result_no_issuance_priced_before_kickoff_is_refused(tmp_path):
    """A scorecard row citing a forecast made AFTER the match is not a
    scorecard row, and the cycle will not go looking for a bundle to blame."""
    with pytest.raises(livecycle.ScorecardMismatch) as exc:
        _cycle(tmp_path, prior="2026-08-23")
    assert "2627:arsenal:coventry" in str(exc.value)


def test_nothing_is_scored_when_the_ledger_carries_no_backlog(tmp_path):
    """Nothing ingested AND nothing outstanding is the cheap day.

    Scoring is driven by the LEDGER's state, not by this run's written list,
    so "nothing was ingested" is no longer sufficient on its own: a round that
    is resolved but unscored is work regardless of who ingested it. Both
    scorecards already carry MW1 here, so there is genuinely nothing to do.
    """
    _prescored(tmp_path)
    result = _cycle(tmp_path, ledger=MW1_SCORES)
    assert result["_steps"].named("matchboard") == []
    assert result["_steps"].named("shadow") == []
    assert result["scorecard"] is None and result["shadow"] is None


def test_a_hand_ingested_round_is_scored_even_though_no_cycle_ingested_it(tmp_path):
    """The other half of the same rule, and the reason it is the right one.

    MW1 was entered by hand before this cycle existed. Under the old rule —
    score what THIS run ingested — no cycle would ever have scored it, because
    no cycle ever ingested it. It is resolved, a bundle priced it before
    kickoff, and it belongs on the scorecard."""
    result = _cycle(tmp_path, ledger=MW1_SCORES)
    assert result["ingested"]["written"] is False
    scored = {r["fixture_id"] for call in result["_steps"].named("matchboard")
              for r in call["rows"]}
    assert scored == set(MW1_META)
    assert result["scorecard"]["backlog"] == sorted(MW1_META)
    assert result["scorecard"]["unscoreable"] == []


# --- the odds snapshot ----------------------------------------------------

def test_the_snapshot_is_taken_on_a_capture_day(tmp_path):
    """2026-08-25 is a Tuesday."""
    result = _cycle(tmp_path, ledger=MW1_SCORES)
    assert result["odds_snapshot"]["written"] is True
    assert result["odds_snapshot"]["capture_day"] is True
    assert sorted(p.name for p in (tmp_path / "snapshots").glob("*.csv"))


def test_no_snapshot_off_the_cadence(tmp_path):
    """2026-08-26 is a Wednesday: the source has published nothing new, and a
    third capture a week would make the count of captures a lie."""
    result = _cycle(tmp_path, ledger=MW1_SCORES,
                    now=pd.Timestamp("2026-08-26T18:20:31Z"))
    assert result["odds_snapshot"] is None
    assert not list((tmp_path / "snapshots").glob("*.csv"))


def test_skip_odds_snapshot_skips_it_on_a_capture_day(tmp_path):
    result = _cycle(tmp_path, ledger=MW1_SCORES, skip_odds_snapshot=True)
    assert result["odds_snapshot"] is None


def test_a_failed_snapshot_stops_the_cycle_before_the_ingest(tmp_path):
    """The capture is step one and everything else is gated on it: a feed that
    stopped publishing `AvgH` needs a ruling, not a cycle that carried on."""
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    of_fetch, e0_fetch, _ = _fetchers()
    with pytest.raises(livecycle.OddsSnapshotFailed):
        livecycle.run_cycle(
            now=NOW, root=root, out_root=tmp_path / "issuances",
            derived_root=tmp_path / "derived",
            shadow_ledger=tmp_path / "shadow.jsonl",
            journal=tmp_path / "journal.jsonl",
            snapshot_dir=tmp_path / "snapshots",
            fetchers={livecycle.SOURCE_A: of_fetch, livecycle.SOURCE_B: e0_fetch},
            odds_fetcher=lambda url: b"<html>error</html>",
            steps=_Steps().as_dict(), verbose=False)
    assert (root / "2026_27" / "results_ledger.jsonl").read_text() == ""


# --- a source that is down ------------------------------------------------

def test_a_source_that_is_down_is_a_stop_not_a_silent_skip(tmp_path):
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")

    def dead(url):
        raise livecycle.SourceUnreachable(f"{url}: timed out")

    of_fetch, _, _ = _fetchers()
    with pytest.raises(livecycle.SourceUnreachable):
        livecycle.run_cycle(
            now=NOW, root=root, out_root=tmp_path / "issuances",
            derived_root=tmp_path / "derived",
            shadow_ledger=tmp_path / "shadow.jsonl",
            journal=tmp_path / "journal.jsonl",
            snapshot_dir=tmp_path / "snapshots", skip_odds_snapshot=True,
            fetchers={livecycle.SOURCE_A: of_fetch, livecycle.SOURCE_B: dead},
            steps=_Steps().as_dict(), verbose=False)


# --- the dry run ----------------------------------------------------------

def test_dry_run_writes_nothing_but_the_journal_line(tmp_path):
    result = _cycle(tmp_path, dry_run=True, prior=None)
    root = result["_root"]
    assert (root / "2026_27" / "results_ledger.jsonl").read_text() == ""
    assert not (tmp_path / "issuances").exists()
    assert not list((tmp_path / "snapshots").glob("*.csv"))
    assert result["_steps"].calls == []
    assert result["outcome"] == "planned"
    # ...and the plan says what it WOULD have done
    assert set(result["ingested"]["fixtures"]) == set(MW1_SCORES)
    assert result["ingested"]["written"] is False
    # the one thing a dry run does write
    assert json.loads((tmp_path / "journal.jsonl").read_text())["dry_run"] is True


# --- the flight log -------------------------------------------------------

def test_every_run_appends_exactly_one_journal_line(tmp_path):
    journal = tmp_path / "journal.jsonl"
    for _ in range(2):
        _cycle(tmp_path, ledger=MW1_SCORES, journal=journal)
    lines = journal.read_text().splitlines()
    assert len(lines) == 2
    assert all(line == leaguesim.canonical_json(json.loads(line))
               for line in lines)


def test_a_refusal_is_journalled_too(tmp_path):
    journal = tmp_path / "journal.jsonl"
    wrong = dict(MW1_SCORES, **{"2627:fulham:chelsea": (9, 9)})
    with pytest.raises(livecycle.SourceDisagreement):
        _cycle(tmp_path, e0_scores=wrong, journal=journal)
    entry = json.loads(journal.read_text().splitlines()[-1])
    assert entry["outcome"] == "STOP"
    assert entry["refused"]["type"] == "SourceDisagreement"
    assert "2627:fulham:chelsea" in entry["refused"]["message"]


def test_the_journal_records_the_digests_of_what_was_written(tmp_path):
    journal = tmp_path / "journal.jsonl"
    _cycle(tmp_path, journal=journal)
    entry = json.loads(journal.read_text().splitlines()[-1])
    assert len(entry["digests"]["results_ledger"]) == 64
    assert entry["digests"]["odds_snapshot"]


# --- the clock ------------------------------------------------------------

def test_moving_the_wall_clock_changes_nothing_the_cycle_computes(tmp_path):
    """`now` is an INPUT: the library reads no clock and the CLI boundary does.

    Same swap as `test_matchboard`'s — through `sys.modules` as well as the
    module attribute, so a function-local `import time` is intercepted too.

    Two halves, because the cycle has two kinds of output. The JOURNAL is
    compared across two runs of an identical world (a fresh issuance already on
    file, both sources carrying a round the ledger resolved, the capture out of
    it — so the second run genuinely has the same work to do as the first); the
    SUMMARY is re-rendered from a rich run's own entry, which is the renderer
    with nothing left to read but the entry.
    """
    import datetime as real_datetime
    import time as real_time

    journal = tmp_path / "journal.jsonl"
    out_root = tmp_path / "issuances"
    fresh = simcli.issuance_dir(SEASON, "2026-08-25", out_root)
    fresh.mkdir(parents=True)
    (fresh / "issuance.json").write_text(json.dumps({"season": SEASON}))

    rich = _cycle(tmp_path / "rich", journal=tmp_path / "rich.jsonl")
    before = _cycle(tmp_path, ledger=MW1_SCORES, journal=journal,
                    skip_odds_snapshot=True)

    class _FrozenTime:
        time = staticmethod(lambda: 0.0)
        monotonic = staticmethod(lambda: 0.0)
        perf_counter = staticmethod(lambda: 0.0)

    class _FrozenDatetime:
        timezone = real_datetime.timezone
        timedelta = real_datetime.timedelta

        class datetime(real_datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(1970, 1, 1, tzinfo=tz)

            @classmethod
            def utcnow(cls):
                return cls(1970, 1, 1)

        class date(real_datetime.date):
            @classmethod
            def today(cls):
                return cls(1970, 1, 1)

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setitem(sys.modules, "time", _FrozenTime)
        monkey.setitem(sys.modules, "datetime", _FrozenDatetime)
        monkey.setattr(livecycle, "_dt", _FrozenDatetime, raising=False)
        after = _cycle(tmp_path, ledger=MW1_SCORES, journal=journal,
                       skip_odds_snapshot=True)
        rerendered = livecycle.render_summary(rich)
    finally:
        monkey.undo()
        assert real_time.time() > 0 and real_datetime.date.today().year > 1970

    lines = journal.read_text().splitlines()
    # The chain field is EXPECTED to differ: line 2 commits to line 1's bytes,
    # so two consecutive lines are never byte-identical and that is the chain
    # working. Everything the cycle COMPUTED must still be identical.
    stripped = [leaguesim.canonical_json(
        {k: v for k, v in json.loads(ln).items() if k != "chain"})
        for ln in lines]
    assert json.loads(lines[0])["chain"] != json.loads(lines[1])["chain"]
    assert json.loads(lines[1])["chain"] == livecycle.journal_link(lines[0])
    assert stripped[0] == stripped[1], (
        "the cycle's own record moved when the wall clock did — something in "
        "it is reading a clock that is not `now`")
    assert before["outcome"] == after["outcome"] == "no-op"
    assert before["summary"] == after["summary"]
    assert rerendered == rich["summary"], (
        "the one-screen summary moved when the clock did, so the same cycle "
        "would not print the same page tomorrow")
    # the rich entry is worth re-rendering: it exercised every branch
    assert rich["ingested"]["written"] and rich["scorecard"]["appended"]


# ==========================================================================
# 8. the command
# ==========================================================================

def test_main_exits_0_on_a_no_op_day(tmp_path, capsys):
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    _ingest_manual(root, MW1_SCORES)
    of_fetch, e0_fetch, _ = _fetchers()
    code = livecycle.main(
        ["--dry-run", "--skip-odds-snapshot"],
        now=NOW, root=root, out_root=tmp_path / "issuances",
        journal=tmp_path / "journal.jsonl",
        fetchers={livecycle.SOURCE_A: of_fetch, livecycle.SOURCE_B: e0_fetch},
        steps=_Steps().as_dict())
    assert code == 0
    out = capsys.readouterr().out
    assert "no new results" in out.lower() or "nothing" in out.lower()


def test_main_prints_STOP_and_exits_2_on_a_refusal(tmp_path, capsys):
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    thin = {k: v for k, v in MW1_SCORES.items() if k != "2627:fulham:chelsea"}
    of_fetch, e0_fetch, _ = _fetchers(openfootball_text(MW1_SCORES),
                                      football_data_text(thin))
    code = livecycle.main(
        ["--skip-odds-snapshot"],
        now=NOW, root=root, out_root=tmp_path / "issuances",
        journal=tmp_path / "journal.jsonl",
        fetchers={livecycle.SOURCE_A: of_fetch, livecycle.SOURCE_B: e0_fetch},
        steps=_Steps().as_dict())
    assert code == 2
    err = capsys.readouterr().err
    assert err.startswith("STOP: CoverageGap:")
    assert "2627:fulham:chelsea" in err


def test_the_command_takes_the_three_documented_flags():
    parser = livecycle.build_parser()
    args = parser.parse_args(["--allow-single-source", "--dry-run",
                              "--skip-odds-snapshot"])
    assert args.allow_single_source and args.dry_run and args.skip_odds_snapshot
    plain = parser.parse_args([])
    assert not (plain.allow_single_source or plain.dry_run
                or plain.skip_odds_snapshot)


def test_the_odds_snapshot_directory_is_the_one_that_actually_holds_them():
    """`epl.oddscapture.SNAPSHOT_DIR` resolves to `data/epl/epl/odds_snapshots`
    — `paths.DATA_DIR` is already `data/epl` — and the operator's captures are
    in `data/epl/odds_snapshots`. The cycle names the real one rather than
    starting a second, empty archive beside it."""
    assert livecycle.ODDS_SNAPSHOT_DIR == paths.DATA_DIR / "odds_snapshots"
    assert livecycle.ODDS_SNAPSHOT_DIR != oddscapture.SNAPSHOT_DIR


# ==========================================================================
# 9. the headline moves
# ==========================================================================

def _issuance_with_output(directory: Path, champion: dict, relegated: dict):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "issuance.json").write_text(json.dumps({"season": SEASON}))
    (directory / "output_dc_native.json").write_text(json.dumps({
        "consequences": {
            club: {"champion": {"p": champion[club]},
                   "relegated": {"p": relegated[club]}}
            for club in champion}}))


def test_the_headline_moves_are_reported_against_the_previous_issuance(tmp_path):
    """Reported and nothing else — A7 (f): this decides nothing and gates
    nothing. It exists so a daily cadence shows what a round actually did."""
    root = tmp_path / "issuances" / "2026_27"
    _issuance_with_output(root / "2026-08-21",
                          {"arsenal": 0.40, "liverpool": 0.30, "coventry": 0.00},
                          {"arsenal": 0.00, "liverpool": 0.00, "coventry": 0.60})
    _issuance_with_output(root / "2026-08-25",
                          {"arsenal": 0.48, "liverpool": 0.26, "coventry": 0.00},
                          {"arsenal": 0.00, "liverpool": 0.00, "coventry": 0.63})

    moves = livecycle.headline_moves(root / "2026-08-25", root / "2026-08-21")
    title = moves["champion"]
    assert title[0]["club"] == "arsenal"
    assert title[0]["delta"] == pytest.approx(0.08)
    assert title[0]["was"] == pytest.approx(0.40)
    assert moves["relegated"][0]["club"] == "coventry"
    assert moves["relegated"][0]["delta"] == pytest.approx(0.03)


def test_no_moves_when_there_is_nothing_to_compare_against(tmp_path):
    """An opener has no previous issuance, and a bundle written by a fake
    forecast has no output file. Neither is an error."""
    root = tmp_path / "issuances" / "2026_27"
    _issuance_with_output(root / "2026-08-25", {"arsenal": 0.48},
                          {"arsenal": 0.0})
    (root / "2026-08-21").mkdir(parents=True)
    assert livecycle.headline_moves(root / "2026-08-25",
                                    root / "2026-08-21") is None


def test_issuance_days_ignores_a_directory_that_is_not_an_issuance(tmp_path):
    """`2026-08-25-superseded-heredoc-spawn` is a real directory in the live
    tree and is not an issuance. One definition of what is — `simcli`'s."""
    root = tmp_path / "issuances" / "2026_27"
    _issuance_with_output(root / "2026-08-25", {"a": 1.0}, {"a": 0.0})
    for name in ("2026-08-25-superseded-heredoc-spawn", ".issuing-2026-08-26-x"):
        (root / name).mkdir(parents=True)
        (root / name / "issuance.json").write_text("{}")
    assert [p.name for p in livecycle.issuance_days(SEASON,
                                                    tmp_path / "issuances")] \
        == ["2026-08-25"]


# ==========================================================================
# 10. the four heavy steps, against the REAL machinery
# ==========================================================================
# The cycle's tests inject stand-ins for these so the suite costs seconds. That
# leaves exactly one thing unproven — that the wrappers call the real functions
# correctly — and it is the thing a keyword-argument typo would break silently
# in production. So the wrappers themselves are exercised here, on a bundle
# issued from a synthetic particle book: seconds, no network, no posterior.

@pytest.fixture(scope="module")
def real_bundle(tmp_path_factory) -> dict:
    """One real issuance over a real season copy, with one MW1 result in the
    ledger for it to be scored against."""
    from epl.simcanary import _synthetic_book

    tmp = tmp_path_factory.mktemp("real")
    root = tmp / "season"
    shutil.copytree(season_mod.SEASON_ROOT, root)
    for season_dir in root.iterdir():
        if season_dir.is_dir():
            for name in ("results_ledger.jsonl", "kickoff_amendments.jsonl"):
                if (season_dir / name).exists():
                    (season_dir / name).write_text("")

    season_obj = season_mod.Season.load(SEASON, root=root)
    state = season_obj.at("2026-08-21")
    issuance = simcli.forecast(
        season=SEASON, root=root, cutoff="2026-08-21", arms=("dc_native",),
        n_sims=64, seed=20260611, chunk_size=32, n_particles=16,
        out_root=tmp / "issuances",
        fit=simcli.FitBundle(post=None,
                             book=_synthetic_book(state.clubs, n_particles=16),
                             info={"synthetic": True}),
        gate_kwargs={"tiebreak_oracle": False, "repo": False,
                     "repro_n_sims": 64}, verbose=False)

    fid = "2627:arsenal:coventry"
    _ingest_manual(root, {fid: MW1_SCORES[fid]})
    results = tmp / "results.jsonl"
    results.write_text(json.dumps({
        "fixture_id": fid, "home_goals": 3, "away_goals": 0,
        "matchweek": 1, "ingest": "livecycle/2026-08-25"}) + "\n")
    return {"directory": Path(issuance["directory"]), "root": root,
            "results": results, "tmp": tmp, "fid": fid}


def test_the_matchboard_step_really_appends_a_scorecard_row(real_bundle,
                                                            tmp_path):
    out = tmp_path / "derived"
    got = livecycle._step_matchboard(
        directory=real_bundle["directory"], results_file=real_bundle["results"],
        out_dir=out, season_root=real_bundle["root"],
        derived_at="2026-08-25 18:20:31", verbose=False)
    assert got["appended"] == 1
    rows = [json.loads(line) for line in
            (out / simcli.SCORECARD_FILENAME).read_text().splitlines()]
    assert rows[0]["fixture_id"] == real_bundle["fid"]
    assert rows[0]["matchweek"] == 1
    assert rows[0]["ingest"] == "livecycle/2026-08-25"


def test_the_shadow_step_really_appends_a_shadow_row(real_bundle, tmp_path):
    ledger = tmp_path / "shadow.jsonl"
    got = livecycle._step_shadow(
        directory=real_bundle["directory"], results_file=real_bundle["results"],
        ledger=ledger, season_root=real_bundle["root"], verbose=False)
    assert got["appended"] == 1
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert rows[0]["fixture_id"] == real_bundle["fid"]


def test_the_shadow_step_turns_a_refusal_into_this_cycles_refusal(real_bundle,
                                                                  tmp_path):
    """`recal score` exits 2 on a row the season ledger does not carry. A
    non-zero exit from the operator's own command is this cycle stopping, not
    this cycle carrying on with an empty ledger."""
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({
        "fixture_id": "2627:fulham:chelsea", "home_goals": 2, "away_goals": 3,
        "matchweek": 1, "ingest": "livecycle/2026-08-25"}) + "\n")
    with pytest.raises(livecycle.ScorecardMismatch, match="exit 2"):
        livecycle._step_shadow(
            directory=real_bundle["directory"], results_file=bad,
            ledger=tmp_path / "shadow2.jsonl",
            season_root=real_bundle["root"], verbose=False)
    assert not (tmp_path / "shadow2.jsonl").exists()


def test_the_check_step_runs_and_a_synthetic_bundle_is_NOT_what_it_expects(
        real_bundle):
    """The wrapper really calls `check_issuance` — and the report it gets back
    from a SYNTHETIC-book bundle is refused by the parser, correctly.

    A bundle issued from no posterior pins no `training_frame_sha256`, so the
    parity criterion comes back UNANCHORED rather than REFUSED: `dc_native`
    PASSES and `refused` is empty. That is not the shape of a live bundle, and
    the cycle saying so is the strictness working in the direction that is easy
    to get wrong — an arm that passed because there was nothing to check.

    The live shape is verified where it lives, against the tracked
    2026-08-25 bundle, in `test_the_designed_refusal_matches_the_live_bundle`.
    """
    report = livecycle._step_check(real_bundle["directory"], verbose=False)
    assert report["refused"] == []
    assert report["arms"]["dc_native"]["status"] == "PASS"
    assert report["fully_anchored"] is False
    assert report["unanchored"] == ["dc_native.parity_reference_is_production_grid"]
    with pytest.raises(livecycle.CheckUnexpected, match="dc_native"):
        livecycle.parse_check_report(report)


LIVE_BUNDLE = (Path("data/epl/sim/issuances/2026_27/2026-08-25"))


@pytest.mark.skipif(not (LIVE_BUNDLE / "issuance.json").exists(),
                    reason="no live issuance under data/ (CI has none)")
def test_the_designed_refusal_matches_the_live_bundle():
    """THE EXPECTATION, HELD AGAINST THE THING IT DESCRIBES.

    `EXPECTED_REFUSED_ARMS` and `EXPECTED_REFUSED_CRITERIA` are a claim about
    what a healthy live bundle's `check` says, and a claim nothing holds
    against reality is a comment. This reads the tracked record rather than
    re-running the simulation: the criterion is a property of the RECORD —
    `training_frame_sha256` is pinned and no posterior reproducing
    `effective_posterior_hash` is available at check time — so the refusal can
    be shown from the record without paying for three arm rebuilds.
    """
    record = json.loads((LIVE_BUNDLE / "issuance.json").read_text())
    assert record.get("training_frame_sha256"), (
        "a live bundle pins the frame its fit trained on; without one the "
        "parity criterion is UNANCHORED, not REFUSED, and the expectation "
        "this module encodes would be the wrong one")
    assert livecycle.EXPECTED_REFUSED_ARMS == ("dc_native",)
    assert livecycle.EXPECTED_REFUSED_CRITERIA == {
        "dc_native": ("parity_reference_is_production_grid",)}
    assert record["published_arm"] == "dc_native"


def test_the_default_steps_are_the_real_ones():
    assert livecycle.DEFAULT_STEPS["forecast"] is livecycle._step_forecast
    assert livecycle.DEFAULT_STEPS["check"] is livecycle._step_check
    assert livecycle.DEFAULT_STEPS["matchboard"] is livecycle._step_matchboard
    assert livecycle.DEFAULT_STEPS["shadow"] is livecycle._step_shadow


# ==========================================================================
# 11. the kickoff moves the refreshed source carries
# ==========================================================================

def test_moved_kickoffs_are_counted_and_digested_not_listed_in_full(tmp_path):
    """REPORTED, never written here. On 2026-08-26 the live source carries 248
    moves against the vendored file, so a log that named them all would be 7KB
    a day of the same 248 lines until somebody filed them. The count and the
    digest are exact, the list is a sample, and the source sha256 recorded
    beside it is what makes the full list recoverable."""
    result = _cycle(tmp_path, ledger=MW1_SCORES)
    assert result["kickoff_moves"] == {
        "n": 0, "first": [], "written": False,
        "sha256": livecycle._sha256_text("[]")}
    # ...and the same bounding is applied to the resolved set, which by May is
    # every one of the season's 380 fixtures, every day.
    assert result["already_resolved"]["n"] == len(MW1_SCORES)
    assert len(result["already_resolved"]["first"]) == livecycle._IDS_SHOWN \
        or result["already_resolved"]["n"] < livecycle._IDS_SHOWN
    assert livecycle._IDS_SHOWN < 380, (
        "the sample must be a sample; a season is 380 fixtures")


def test_a_moved_kickoff_is_noticed_and_nothing_is_written_for_it(tmp_path):
    """The amendment overlay is `simcli ingest-results --from-openfootball`'s
    to write; this cycle's ingest writes RESULTS. What it owes the operator is
    to say that the source moved a kickoff at all — a fixture whose stale date
    has passed reads `unresolved`, and past two days raises `results_lag`."""
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    _ingest_manual(root, MW1_SCORES)
    moved = openfootball_text(MW1_SCORES).replace(
        "    20:00  Fulham FC", "    18:15  Fulham FC")
    of_fetch, e0_fetch, _ = _fetchers(moved)
    result = livecycle.run_cycle(
        now=NOW, root=root, out_root=tmp_path / "issuances",
        derived_root=tmp_path / "derived",
        shadow_ledger=tmp_path / "shadow.jsonl",
        journal=tmp_path / "journal.jsonl", skip_odds_snapshot=True,
        fetchers={livecycle.SOURCE_A: of_fetch, livecycle.SOURCE_B: e0_fetch},
        steps=_Steps().as_dict(), verbose=False)
    assert result["kickoff_moves"]["n"] == 1
    assert result["kickoff_moves"]["first"] == ["2627:fulham:chelsea"]
    assert result["kickoff_moves"]["written"] is False
    assert (root / "2026_27" / "kickoff_amendments.jsonl").read_text() == ""


def test_a_moved_kickoff_IS_filed_when_the_same_run_ingests_a_result(tmp_path):
    """THE SIDE EFFECT, STATED. `simcli.ingest_results` files the source's
    kickoff moves alongside the results it writes — that is what it is for, and
    the cycle inherits it rather than reimplementing or suppressing it. So on a
    day with results the moves are FILED, and the flight log says so."""
    moved = openfootball_text(MW1_SCORES).replace(
        "    20:00  Fulham FC", "    18:15  Fulham FC")
    result = _cycle(tmp_path, of_scores=None)
    assert result["kickoff_moves"]["n"] == 0

    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    of_fetch, e0_fetch, _ = _fetchers(moved, football_data_text(MW1_SCORES))
    _with_prior_issuance(tmp_path, "2026-08-21")
    result = livecycle.run_cycle(
        now=NOW, root=root, out_root=tmp_path / "issuances",
        derived_root=tmp_path / "derived",
        shadow_ledger=tmp_path / "shadow.jsonl",
        journal=tmp_path / "journal2.jsonl", skip_odds_snapshot=True,
        fetchers={livecycle.SOURCE_A: of_fetch, livecycle.SOURCE_B: e0_fetch},
        board_reader=lambda d: _board(
            Path(d).name, "2026-08-21 00:00:00", "2026-08-21 00:00:00"),
        steps=_Steps().as_dict(), verbose=False)
    assert result["ingested"]["written"] is True
    assert result["kickoff_moves"]["written"] is True
    filed = [json.loads(line) for line in
             (root / "2026_27" / "kickoff_amendments.jsonl"
              ).read_text().splitlines() if line.strip()]
    assert [row["fixture_id"] for row in filed] == ["2627:fulham:chelsea"]
    assert filed[0]["time"] == "18:15"


# ==========================================================================
# 12. the knowledge clock against a ledger stamped on another clock
# ==========================================================================

def test_the_knowledge_clock_clears_a_ledger_row_stamped_ahead_of_utc(tmp_path):
    """THE SECOND ROUTE TO THE MW1 BLINDNESS, closed.

    This cycle stamps UTC. MW1 was entered by hand, and a hand-entered stamp is
    whatever clock the operator was reading — Europe/London runs an hour ahead
    of UTC for most of a season. An `observed_by` computed from `now` alone can
    therefore land BEFORE a row that is already on file, and a row observed
    after the knowledge bound is invisible to the fit. Everything the ledger
    holds is known, so the bound is at or after the latest thing it holds.
    """
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    ahead = (NOW.tz_localize(None) + pd.Timedelta(minutes=40)).isoformat()
    _ingest_manual(root, MW1_SCORES, observed_at=ahead)
    of_fetch, e0_fetch, _ = _fetchers()
    steps = _Steps()
    result = livecycle.run_cycle(
        now=NOW, root=root, out_root=tmp_path / "issuances",
        derived_root=tmp_path / "derived",
        shadow_ledger=tmp_path / "shadow.jsonl",
        journal=tmp_path / "journal.jsonl", skip_odds_snapshot=True,
        fetchers={livecycle.SOURCE_A: of_fetch, livecycle.SOURCE_B: e0_fetch},
        steps=steps.as_dict(), verbose=False)
    observed_by = pd.Timestamp(steps.named("forecast")[0]["observed_by"])
    assert observed_by >= pd.Timestamp(ahead), (
        "the fit would not see the round that is already in the ledger")
    assert observed_by == pd.Timestamp(ahead).ceil("min")
    assert pd.Timestamp(result["observed_by"]) == observed_by


def test_a_ledger_stamp_a_year_out_is_refused_rather_than_reached_for(tmp_path):
    """A day of slack covers every timezone; nothing covers 2027. Pulling the
    bound out to meet a typo would publish an issuance whose knowledge clock is
    in the future, and bury the bad row inside it."""
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    _ingest_manual(root, {"2627:arsenal:coventry": (3, 0)},
                   observed_at="2027-08-25T12:00:00")
    of_fetch, e0_fetch, _ = _fetchers()
    # ...and it refuses BEFORE the ingest, so a ledger nothing can compute a
    # knowledge bound over does not get nine more rows added to it.
    with pytest.raises(livecycle.LedgerConflict, match="2027"):
        livecycle.run_cycle(
            now=NOW, root=root, out_root=tmp_path / "issuances",
            derived_root=tmp_path / "derived",
            shadow_ledger=tmp_path / "shadow.jsonl",
            journal=tmp_path / "journal.jsonl", skip_odds_snapshot=True,
            allow_single_source=True,
            fetchers={livecycle.SOURCE_A: of_fetch,
                      livecycle.SOURCE_B: e0_fetch},
            steps=_Steps().as_dict(), verbose=False)
    rows = (root / "2026_27" / "results_ledger.jsonl").read_text().splitlines()
    assert len([r for r in rows if r.strip()]) == 1


# ==========================================================================
# 13. one run, both writers
# ==========================================================================

def test_a_mixed_round_writes_through_both_doors_in_one_run(tmp_path):
    """HALF THE ROUND IN BOTH SOURCES, HALF IN ONE. Under
    `--allow-single-source` the agreeing half is ingested from openfootball's
    OWN FILE — so those ledger rows carry its `openfootball@<sha>` provenance,
    which is honest about which bytes they came from — and the half only
    football-data covers goes through the season's hand-entry door, validated
    row by row, with a note naming the source and the flag.

    Both writers in one run is the composition nothing else here exercises,
    and it is the shape of a real Saturday when openfootball is halfway
    through catching up.
    """
    both = dict(sorted(MW1_SCORES.items())[:5])
    e0_only = dict(sorted(MW1_SCORES.items())[5:])
    result = _cycle(tmp_path, of_scores=both, e0_scores=MW1_SCORES,
                    allow_single_source=True)

    rows = {r["fixture_id"]: r for r in (
        json.loads(line) for line in
        (result["_root"] / "2026_27" / "results_ledger.jsonl"
         ).read_text().splitlines() if line.strip())}
    assert set(rows) == set(MW1_SCORES)
    assert all(rows[fid]["source"].startswith("openfootball@") for fid in both)
    assert all(rows[fid]["source"] == "manual" for fid in e0_only)
    assert all(livecycle.SOURCE_B in rows[fid]["note"] for fid in e0_only)
    assert result["ingested"]["single_source"] == sorted(e0_only)
    assert result["ingested"]["dry_run_rows"] == len(MW1_SCORES)

    # ...and every one of them is scored against the bundle that priced it
    board_call = result["_steps"].named("matchboard")[0]
    assert {r["fixture_id"] for r in board_call["rows"]} == set(MW1_SCORES)


# ==========================================================================
# 14. the second round, with the first already on the ledger
# ==========================================================================
# THE ORDINARY WEEKLY PICTURE, which the MW1-only fixtures could never reach:
# both sources carry MW1 AND part of MW2, the ledger resolves MW1 already, and
# exactly the new part may be written. This is where the dry run's CONTRACT
# earns its keep — the openfootball file offered thirteen results and only
# three of them were authorised.

def test_a_second_round_ingests_only_what_the_ledger_lacks(tmp_path):
    both = {**MW1_SCORES, **MW2_SCORES}
    prior = tmp_path / "issuances" / "2026_27" / "2026-08-28"
    prior.mkdir(parents=True)
    (prior / "issuance.json").write_text(json.dumps({"season": SEASON}))
    board = _board("2026-08-28", "2026-08-28 00:00:00", "2026-08-28 00:00:00",
                   fixtures=MW2_META)

    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    _ingest_manual(root, MW1_SCORES)
    of_fetch, e0_fetch, _ = _fetchers(openfootball_text(both),
                                      football_data_text(both))
    steps = _Steps()
    now = pd.Timestamp("2026-08-31T09:05:00Z")
    result = livecycle.run_cycle(
        now=now, root=root, out_root=tmp_path / "issuances",
        derived_root=tmp_path / "derived",
        shadow_ledger=tmp_path / "shadow.jsonl",
        journal=tmp_path / "journal.jsonl", skip_odds_snapshot=True,
        fetchers={livecycle.SOURCE_A: of_fetch, livecycle.SOURCE_B: e0_fetch},
        board_reader=lambda d: board, steps=steps.as_dict(), verbose=False)

    assert set(result["ingested"]["fixtures"]) == set(MW2_SCORES)
    assert result["ingested"]["dry_run_rows"] == len(MW2_SCORES)
    assert result["already_resolved"]["n"] == len(MW1_SCORES)

    rows = {r["fixture_id"] for r in (
        json.loads(line) for line in
        (root / "2026_27" / "results_ledger.jsonl").read_text().splitlines()
        if line.strip())}
    assert rows == set(MW1_SCORES) | set(MW2_SCORES)

    # scored against the bundle that priced MW2, at MW2's matchweek
    scored = steps.named("matchboard")[0]
    assert Path(scored["directory"]).name == "2026-08-28"
    assert {r["fixture_id"] for r in scored["rows"]} == set(MW2_SCORES)
    assert all(r["matchweek"] == 2 for r in scored["rows"])
    assert all(r["ingest"] == "livecycle/2026-08-31" for r in scored["rows"])


def test_re_running_the_same_day_ingests_nothing_a_second_time(tmp_path):
    """IDEMPOTENT. The operator runs this daily and sometimes twice; the second
    run must add no row, and it must reach that conclusion through the ledger
    rather than by remembering what the first run did."""
    both = {**MW1_SCORES, **MW2_SCORES}
    prior = tmp_path / "issuances" / "2026_27" / "2026-08-28"
    prior.mkdir(parents=True)
    (prior / "issuance.json").write_text(json.dumps({"season": SEASON}))
    board = _board("2026-08-28", "2026-08-28 00:00:00", "2026-08-28 00:00:00",
                   fixtures=MW2_META)
    root = _season_copy(tmp_path, f"season{next(_COPIES)}")
    _ingest_manual(root, MW1_SCORES)
    of_fetch, e0_fetch, _ = _fetchers(openfootball_text(both),
                                      football_data_text(both))
    now = pd.Timestamp("2026-08-31T09:05:00Z")

    def once():
        return livecycle.run_cycle(
            now=now, root=root, out_root=tmp_path / "issuances",
            derived_root=tmp_path / "derived",
            shadow_ledger=tmp_path / "shadow.jsonl",
            journal=tmp_path / "journal.jsonl", skip_odds_snapshot=True,
            fetchers={livecycle.SOURCE_A: of_fetch,
                      livecycle.SOURCE_B: e0_fetch},
            board_reader=lambda d: board, steps=_Steps().as_dict(),
            verbose=False)

    first = once()
    ledger = (root / "2026_27" / "results_ledger.jsonl").read_text()
    second = once()
    assert (root / "2026_27" / "results_ledger.jsonl").read_text() == ledger
    assert first["ingested"]["fixtures"] == sorted(MW2_SCORES)
    assert second["ingested"]["fixtures"] == []
    assert second["already_resolved"]["n"] == len(MW1_SCORES) + len(MW2_SCORES)
    # the issuance for this cutoff now exists, so the second run is a no-op
    assert second["outcome"] == "no-op"


# ==========================================================================
# 14. the flight log verifies itself (L1)
# ==========================================================================
#: An append-only log is only evidence if a past line cannot be quietly
#: rewritten. Nothing polled this file, so a line edited after the fact — by a
#: bad merge, a stray editor, or a hand that wanted a STOP to read `no-op` —
#: was indistinguishable from the line the run actually wrote. Each line now
#: carries `chain`: the SHA-256 of the PREVIOUS line's canonical form, genesis
#: constant for the first. Every run verifies the whole chain before it
#: appends, so tampering is caught by the next cycle rather than by nobody.

def _journal_lines(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip()]


def test_the_chain_links_each_line_to_the_one_before_it(tmp_path):
    journal = tmp_path / "j.jsonl"
    first = livecycle.append_journal(journal, {"outcome": "no-op", "n": 1})
    second = livecycle.append_journal(journal, {"outcome": "ran", "n": 2})

    rows = _journal_lines(journal)
    assert rows[0]["chain"] == livecycle.JOURNAL_GENESIS
    assert rows[1]["chain"] == livecycle.journal_link(first)
    assert livecycle.journal_link(first) != livecycle.journal_link(second)
    # and the whole file verifies
    assert livecycle.verify_journal_chain(journal) == 2


def test_a_tampered_past_line_is_a_typed_stop(tmp_path):
    """THE POINT OF THE CHAIN. Rewrite a line that is already on file and the
    next run must refuse, by name, rather than append beside it."""
    journal = tmp_path / "j.jsonl"
    livecycle.append_journal(journal, {"outcome": "STOP", "n": 1})
    livecycle.append_journal(journal, {"outcome": "ran", "n": 2})
    assert livecycle.verify_journal_chain(journal) == 2

    rows = _journal_lines(journal)
    rows[0]["outcome"] = "no-op"                 # the lie a chain exists to catch
    journal.write_text("".join(leaguesim.canonical_json(r) + "\n" for r in rows),
                       encoding="utf-8")

    with pytest.raises(livecycle.JournalTampered) as exc:
        livecycle.verify_journal_chain(journal)
    assert "line 2" in str(exc.value)
    # and appending is refused too — the verification is not advisory
    with pytest.raises(livecycle.JournalTampered):
        livecycle.append_journal(journal, {"outcome": "ran", "n": 3})


def test_a_deleted_line_is_caught_too(tmp_path):
    journal = tmp_path / "j.jsonl"
    for i in range(3):
        livecycle.append_journal(journal, {"outcome": "ran", "n": i})
    rows = _journal_lines(journal)
    del rows[1]
    journal.write_text("".join(leaguesim.canonical_json(r) + "\n" for r in rows),
                       encoding="utf-8")
    with pytest.raises(livecycle.JournalTampered):
        livecycle.verify_journal_chain(journal)


def test_the_two_pre_chain_lines_migrate_by_genesis_note_not_by_rewrite(tmp_path):
    """The committed journal has two lines written before the chain existed.
    History is not rewritten to give them one: a line carrying no `chain` at
    all is PRE-CHAIN and is accepted, and the chain begins at the first line
    that has one."""
    journal = tmp_path / "j.jsonl"
    legacy = [{"outcome": "planned", "n": 1}, {"outcome": "planned", "n": 2}]
    journal.write_text("".join(leaguesim.canonical_json(r) + "\n" for r in legacy),
                       encoding="utf-8")
    assert livecycle.verify_journal_chain(journal) == 2       # tolerated

    livecycle.append_journal(journal, {"outcome": "ran", "n": 3})
    rows = _journal_lines(journal)
    assert "chain" not in rows[0] and "chain" not in rows[1]
    # the first CHAINED line anchors to the last pre-chain line, so the
    # migration point is itself covered rather than being a free seam
    assert rows[2]["chain"] == livecycle.journal_link(
        leaguesim.canonical_json(legacy[1]))
    assert livecycle.verify_journal_chain(journal) == 3

    # …and tampering with a pre-chain line is now caught, because the first
    # chained line commits to it
    rows[1]["outcome"] = "ran"
    journal.write_text("".join(leaguesim.canonical_json(r) + "\n" for r in rows),
                       encoding="utf-8")
    with pytest.raises(livecycle.JournalTampered):
        livecycle.verify_journal_chain(journal)


def test_the_cycle_verifies_the_chain_before_it_runs(tmp_path):
    """A tampered journal stops the CYCLE, not merely the append."""
    journal = tmp_path / "journal.jsonl"
    livecycle.append_journal(journal, {"outcome": "ran", "n": 1})
    livecycle.append_journal(journal, {"outcome": "ran", "n": 2})
    rows = _journal_lines(journal)
    rows[0]["outcome"] = "STOP"                  # a PAST line, not the tip
    journal.write_text("".join(leaguesim.canonical_json(r) + "\n" for r in rows),
                       encoding="utf-8")
    with pytest.raises(livecycle.JournalTampered):
        _cycle(tmp_path, journal=journal)


def test_the_tip_is_the_one_line_the_chain_cannot_protect(tmp_path):
    """STATED, NOT HIDDEN. A hash chain commits each line to its PARENT, so
    the newest line has nothing after it to vouch for it: edit the tip alone
    and the file still verifies. The protection arrives with the next run,
    which chains to whatever the tip's bytes then are. The tip's real anchor
    is outside this file — the journal is committed, so git holds it."""
    journal = tmp_path / "j.jsonl"
    livecycle.append_journal(journal, {"outcome": "ran", "n": 1})
    livecycle.append_journal(journal, {"outcome": "STOP", "n": 2})
    rows = _journal_lines(journal)
    rows[-1]["outcome"] = "no-op"
    journal.write_text("".join(leaguesim.canonical_json(r) + "\n" for r in rows),
                       encoding="utf-8")
    assert livecycle.verify_journal_chain(journal) == 2      # not detected

    # but every EARLIER line is protected, which is what the chain is for
    rows[0]["outcome"] = "no-op"
    journal.write_text("".join(leaguesim.canonical_json(r) + "\n" for r in rows),
                       encoding="utf-8")
    with pytest.raises(livecycle.JournalTampered):
        livecycle.verify_journal_chain(journal)


# ==========================================================================
# 15. a late refusal leaves work, and the next run picks it up (L2)
# ==========================================================================
#: The ingest writes at step 4 and the scoring runs at steps 7-8, so every
#: refusal in between — `GateNotPassed` above all, which is a DESIGNED refusal
#: on a bundle that failed its acceptance gate — leaves results on the ledger
#: that were never scored. Scoring used to take its work from `ingestable`,
#: THIS RUN's written list, and the next run's `ingestable` is empty because
#: the ledger already resolves those fixtures. Nothing ever came back for them.
#: The work is now read from the LEDGER STATE — resolved but absent from the
#: scorecards — so a backlog clears itself on the next successful cycle.

class _ScoringSteps(_Steps):
    """`_Steps`, but the scoring stubs actually file rows, so "already scored"
    is a fact on disk rather than a fact in a list."""

    def __init__(self, *, scorecard: Path, shadow: Path, **kw):
        super().__init__(**kw)
        self.scorecard, self.shadow_path = Path(scorecard), Path(shadow)

    def _file(self, path, rows, digest):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps({"fixture_id": row["fixture_id"],
                                     "run_digest": digest}) + "\n")

    def matchboard(self, **kw):
        out = super().matchboard(**kw)
        self._file(self.scorecard, _results_rows(kw["results_file"]), "a" * 64)
        return out

    def shadow(self, **kw):
        out = super().shadow(**kw)
        self._file(self.shadow_path, _results_rows(kw["results_file"]), "a" * 64)
        return out


def test_a_refusal_after_the_ingest_write_leaves_a_backlog_the_next_run_clears(tmp_path):
    root = _season_copy(tmp_path, "backlog")
    derived = tmp_path / "derived"
    scorecard = derived / simcli.SCORECARD_FILENAME
    shadow = derived / "shadow.jsonl"

    # --- run 1: the ingest writes, then the gate refuses ------------------
    failing = _ScoringSteps(scorecard=scorecard, shadow=shadow, gate_pass=False)
    with pytest.raises(livecycle.GateNotPassed):
        _cycle(tmp_path, root=root, steps=failing,
               derived_root=derived, shadow_ledger=shadow)

    assert not failing.named("matchboard"), "nothing should have been scored"
    written_ids = {r["fixture_id"] for r in _results_rows(
        Path(root) / season_mod.season_dir_name(SEASON)
        / season_mod.RESULTS_FILENAME)}
    assert written_ids, "the ingest must have written before the refusal"
    assert not scorecard.exists()

    # --- run 2: a clean cycle. The sources carry the SAME round, which the
    # ledger already resolves, so this run writes nothing at all. ----------
    clean = _ScoringSteps(scorecard=scorecard, shadow=shadow)
    out = _cycle(tmp_path, root=root, steps=clean,
                 derived_root=derived, shadow_ledger=shadow)
    assert out["ingested"]["written"] is False       # nothing new was written

    scored = {r["fixture_id"] for call in clean.named("matchboard")
              for r in call["rows"]}
    assert scored == written_ids, (
        "the orphaned fixtures were never scored by any run")
    assert {r["fixture_id"] for r in _results_rows(scorecard)} == written_ids

    # --- run 3: nothing is left, so nothing is re-scored -------------------
    third = _ScoringSteps(scorecard=scorecard, shadow=shadow)
    _cycle(tmp_path, root=root, steps=third,
           derived_root=derived, shadow_ledger=shadow)
    assert not third.named("matchboard"), "a cleared backlog must stay cleared"


def test_the_backlog_is_read_from_the_ledger_not_from_this_runs_list(tmp_path):
    """The unit the fix turns on, tested directly."""
    scorecard = tmp_path / "scorecard.jsonl"
    shadow = tmp_path / "shadow.jsonl"
    scorecard.write_text(json.dumps({"fixture_id": "a", "run_digest": "d"}) + "\n")
    shadow.write_text(json.dumps({"fixture_id": "a", "run_digest": "d"}) + "\n")

    assert livecycle.unscored_fixtures(
        ["a", "b", "c"], scorecard=scorecard, shadow=shadow) == ["b", "c"]
    # scored on one ledger but not the other is still unscored
    shadow.write_text("")
    assert livecycle.unscored_fixtures(
        ["a"], scorecard=scorecard, shadow=shadow) == ["a"]
    # absent files mean nothing has been scored yet
    assert livecycle.unscored_fixtures(
        ["a"], scorecard=tmp_path / "nope.jsonl",
        shadow=tmp_path / "nope2.jsonl") == ["a"]


def test_the_committed_journal_verifies_and_its_history_was_not_rewritten():
    """The real flight log, held to its own chain.

    The two lines that predate the chain keep their exact bytes — no `chain`
    key was added to them — and the dated `chain-genesis` line that follows
    anchors to line 2, so the migration seam is covered rather than being a
    free place to edit."""
    path = livecycle.JOURNAL_PATH
    assert path.exists(), "the flight log is committed; it should be here"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    assert livecycle.verify_journal_chain(path) == len(lines)

    rows = [json.loads(ln) for ln in lines]
    pre = [r for r in rows if "chain" not in r]
    assert len(pre) == 2, "the two pre-chain lines must keep their bytes"
    assert rows[:2] == pre, "pre-chain lines belong at the head, unedited"

    genesis = rows[2]
    assert genesis["outcome"] == "chain-genesis"
    assert genesis["pre_chain_lines"] == 2
    assert genesis["chain"] == livecycle.journal_link(lines[1])
