"""The parser against REAL openfootball bytes, not bytes we wrote ourselves.

Every result fixture elsewhere in the suite is hand-written with the score in the
MIDDLE (``Home  4-2 (1-0)  Away``). openfootball does not publish that layout while
a season is live: when the fixture line is ``v``-separated it appends the score at
the END (``Home  v Away   4-2 (1-0)``), and it omits the half-time bracket on 0-0.
So 543 green tests agreed with each other and with nothing upstream.

The fixture here is the real 2025/26 Premier League file at openfootball/england
commit 097ab4fe — a complete 380-match season in the END layout, CC0-1.0.
"""
import hashlib
from pathlib import Path

import pytest

from epl import season as S

FIXTURE = Path(__file__).parent / "fixtures" / "openfootball_2025-26_end_layout.txt"
REAL = FIXTURE.read_text(encoding="utf-8")

# openfootball/england @ 097ab4fe, 2025-26/1-premierleague.txt, CC0-1.0.
# Pinned because the row/score counts alone do not identify a real season: a corpus
# of 353 copies of one fabricated result plus 27 copies of one fabricated draw
# satisfies every count below. The hash and the topology assertions together are
# what make "real upstream bytes" a fact rather than a claim.
FIXTURE_SHA256 = "380ca97719718deaef324c32c0d7d0a79134cb17323432af76b29c7d4b843c57"


def test_the_fixture_is_the_pinned_upstream_bytes():
    got = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert got == FIXTURE_SHA256, (
        "the vendored corpus is not the pinned openfootball file; re-fetch it from "
        "openfootball/england @ 097ab4fe rather than editing the hash")


def test_the_corpus_has_the_topology_of_a_real_league_season():
    rows = S.parse_openfootball(REAL)
    teams = {r.home_raw for r in rows} | {r.away_raw for r in rows}
    pairs = {(r.home_raw, r.away_raw) for r in rows}
    assert len(teams) == 20, f"expected 20 clubs, got {len(teams)}"
    assert len(pairs) == 380, f"expected 380 distinct ordered pairs, got {len(pairs)}"
    for t in teams:
        home = sum(1 for r in rows if r.home_raw == t)
        away = sum(1 for r in rows if r.away_raw == t)
        assert home == 19 and away == 19, f"{t}: {home} home / {away} away, expected 19/19"


def test_the_real_end_layout_season_parses_as_380_played_matches():
    rows = S.parse_openfootball(REAL)
    played = [r for r in rows if r.hg is not None and r.ag is not None]
    assert len(rows) == 380, f"expected 380 rows, got {len(rows)}"
    assert len(played) == 380, (
        f"only {len(played)}/380 rows carry a score — the END layout is being "
        "read as unplayed")


def test_the_real_end_layout_does_not_smuggle_the_separator_into_a_team_name():
    for r in S.parse_openfootball(REAL):
        assert " v " not in r.home_raw, f"home_raw swallowed the separator: {r.home_raw!r}"
        assert not r.away_raw.startswith("("), f"away_raw is a HT bracket: {r.away_raw!r}"
        assert not any(ch.isdigit() for ch in r.away_raw), (
            f"away_raw carries a score: {r.away_raw!r}")


def test_the_bracket_less_nil_nil_is_a_played_match_not_an_unplayed_one():
    # openfootball prints "Home  v Away   0-0" with no half-time bracket.
    rows = S.parse_openfootball(REAL)
    nil_nil = [r for r in rows if r.hg == 0 and r.ag == 0]
    assert len(nil_nil) == 27, f"expected 27 goalless draws, got {len(nil_nil)}"


@pytest.mark.parametrize("line,home,away,hg,ag", [
    # END, with the half-time bracket — openfootball's live in-season layout
    ("  20:00  Arsenal FC              v Coventry City FC        2-0 (1-0)",
     "Arsenal FC", "Coventry City FC", 2, 0),
    # END, goalless: openfootball omits the bracket entirely
    ("  20:00  Newcastle United FC      v Liverpool FC             0-0",
     "Newcastle United FC", "Liverpool FC", 0, 0),
    # MIDDLE — the archival regeneration layout, must keep working
    ("  20:00  Arsenal FC              2-0 (1-0)  Coventry City FC",
     "Arsenal FC", "Coventry City FC", 2, 0),
])
def test_both_score_placements_parse(line, home, away, hg, ag):
    hdr = "= English Premier League 2026/27\n\n▪ Matchday 1\n  Fri Aug 21 2026\n"
    r = S.parse_openfootball(hdr + line + "\n")[0]
    assert (r.home_raw, r.away_raw, r.hg, r.ag) == (home, away, hg, ag)


@pytest.mark.parametrize("line,why", [
    ("  20:00  Arsenal FC v Chelsea FC 2-0 (1-0)",
     "single-space result boundary: openfootball's spec requires two, so the split "
     "point is ambiguous and must not be guessed"),
    ("  20:00  Arsenal FC              v Chelsea FC  1-1 aet (1-1, 0-0) 3-4 pen",
     "extra-time / penalties: a Football.TXT form this parser does not model"),
])
def test_an_ambiguous_v_separated_result_refuses_instead_of_fabricating(line, why):
    hdr = "= English Premier League 2026/27\n\n▪ Matchday 1\n  Fri Aug 21 2026\n"
    with pytest.raises(S.ParseError):
        S.parse_openfootball(hdr + line + "\n")
