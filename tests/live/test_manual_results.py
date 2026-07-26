"""Unit tests for the matchday-1 MANUAL results-ingest fallback (Phase 0).

Pins the STRICT, fail-loud, NEVER-fuzzy CSV validation (unknown team, unscheduled
fixture, bad scores, KO-level missing/spurious shootout_winner, bad header), the
ingest-through-``ingest_live_result`` path, the file-hash provenance helper, and
the store-level supersede-by-upstream tie-break. No network, no data/ — a tiny
synthetic CSV against the real (committed) ``config/tournament_2026.yaml`` draw.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.data.tournament import WC2026_SOURCE
from wcmodel.live.manual_results import (
    ManualResultsError,
    ingest_manual_rows,
    manual_file_sha256,
    validate_manual_csv,
)

# A real matchday-1 GROUP fixture from the committed draw (group A, host opener).
_HOME, _AWAY, _DATE = "Mexico", "South Africa", "2026-06-11"
# A real KNOCKOUT fixture date (Round of 32) — placeholder feeders, so a
# concrete-team KO result is accepted by date (spec §2.2).
_KO_DATE = "2026-06-28"


def _write_csv(tmp_path: Path, body: str, name: str = "day1.csv") -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


# --------------------------------------------------------------------------- #
# Happy path                                                                   #
# --------------------------------------------------------------------------- #
def test_validate_accepts_a_real_group_fixture(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_HOME},{_AWAY},3,1,\n")
    rows = validate_manual_csv(csv)
    assert len(rows) == 1
    r = rows[0]
    assert (r.home_team, r.away_team, r.home_score, r.away_score) == (_HOME, _AWAY, 3, 1)
    assert r.is_knockout is False
    assert r.shootout_winner is None
    # Mexico hosting at Mexico City -> NON-neutral (host rule), city/country resolved.
    assert r.city == "Mexico City" and r.country == "MX" and r.neutral is False


def test_validate_header_without_optional_shootout_column(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score\n"
        f"{_DATE},{_HOME},{_AWAY},2,0\n")
    rows = validate_manual_csv(csv)
    assert len(rows) == 1 and rows[0].home_score == 2


# --------------------------------------------------------------------------- #
# STRICT rejections (fail-loud, never fuzzy)                                   #
# --------------------------------------------------------------------------- #
def test_reject_unknown_team(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},Mexcio,{_AWAY},1,0,\n")  # typo: Mexcio
    with pytest.raises(ManualResultsError, match="(?i)drawn nation|exactly|fuzzy"):
        validate_manual_csv(csv)


def test_reject_unscheduled_fixture_flipped_home_away(tmp_path):
    # The real fixture is Mexico (home) v South Africa (away); flipping it is NOT a
    # scheduled fixture and must be rejected (no fuzzy / order-agnostic match).
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_AWAY},{_HOME},1,3,\n")
    with pytest.raises(ManualResultsError, match="(?i)not a scheduled|home/away|date"):
        validate_manual_csv(csv)


def test_reject_unscheduled_fixture_wrong_date(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"2026-06-12,{_HOME},{_AWAY},1,0,\n")  # right teams, wrong date
    with pytest.raises(ManualResultsError, match="(?i)not a scheduled"):
        validate_manual_csv(csv)


def test_reject_fractional_score(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_HOME},{_AWAY},2.5,1,\n")
    with pytest.raises(ManualResultsError, match="(?i)goal count|integral|finite"):
        validate_manual_csv(csv)


def test_reject_negative_score(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_HOME},{_AWAY},-1,0,\n")
    with pytest.raises(ManualResultsError, match="(?i)goal count|non-negative|finite"):
        validate_manual_csv(csv)


def test_reject_nonnumeric_score(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_HOME},{_AWAY},two,0,\n")
    with pytest.raises(ManualResultsError, match="(?i)goal count|valid"):
        validate_manual_csv(csv)


def test_reject_bad_header(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home,away,home_score,away_score\n"  # 'home'/'away' not the required names
        f"{_DATE},{_HOME},{_AWAY},1,0\n")
    with pytest.raises(ManualResultsError, match="(?i)header|required|unknown|missing"):
        validate_manual_csv(csv)


def test_reject_ko_level_missing_shootout_winner(tmp_path):
    # A KO-date level score with NO shootout_winner -> must be rejected.
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_KO_DATE},{_HOME},{_AWAY},1,1,\n")
    with pytest.raises(ManualResultsError, match="(?i)level knockout|shootout_winner"):
        validate_manual_csv(csv)


def test_ko_level_with_valid_shootout_winner_accepted(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_KO_DATE},{_HOME},{_AWAY},1,1,{_HOME}\n")
    rows = validate_manual_csv(csv)
    assert rows[0].is_knockout is True
    assert rows[0].shootout_winner == _HOME


def test_reject_ko_shootout_winner_not_a_team(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_KO_DATE},{_HOME},{_AWAY},1,1,Brazil\n")  # Brazil isn't in this match
    with pytest.raises(ManualResultsError, match="(?i)one of the two teams"):
        validate_manual_csv(csv)


def test_reject_group_draw_with_spurious_shootout_winner(tmp_path):
    # A level GROUP score is a legal draw — a shootout_winner is nonsensical there.
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_HOME},{_AWAY},1,1,{_HOME}\n")
    with pytest.raises(ManualResultsError, match="(?i)group.*draw|must NOT carry"):
        validate_manual_csv(csv)


def test_reject_nonlevel_score_with_shootout_winner(tmp_path):
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_KO_DATE},{_HOME},{_AWAY},2,1,{_HOME}\n")  # decisive score + shootout
    with pytest.raises(ManualResultsError, match="(?i)not level|shootout decides"):
        validate_manual_csv(csv)


# --------------------------------------------------------------------------- #
# Provenance helper                                                           #
# --------------------------------------------------------------------------- #
def test_manual_file_sha256_is_stable_and_content_bearing(tmp_path):
    body = ("date,home_team,away_team,home_score,away_score,shootout_winner\n"
            f"{_DATE},{_HOME},{_AWAY},3,1,\n")
    a = _write_csv(tmp_path, body, "a.csv")
    b = _write_csv(tmp_path, body, "b.csv")
    c = _write_csv(tmp_path, body.replace("3,1", "2,1"), "c.csv")
    assert manual_file_sha256(a) == manual_file_sha256(b)   # same bytes -> same hash
    assert manual_file_sha256(a) != manual_file_sha256(c)   # different content -> different


# --------------------------------------------------------------------------- #
# Ingest path (through ingest_live_result)                                     #
# --------------------------------------------------------------------------- #
def test_ingest_manual_rows_writes_point_in_time(tmp_path):
    store = BitemporalStore(tmp_path / "store")
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_HOME},{_AWAY},3,1,\n")
    rows = validate_manual_csv(csv)
    n = ingest_manual_rows(store, rows, observed_at="2026-06-11T23:30:00Z")
    assert n == 1
    # Visible at/after the operator's entry time; absent before it (observed_at gate).
    after = store.read("results", cutoff="2026-06-12T00:00:00Z")
    hit = after[(after["home_team"] == _HOME) & (after["away_team"] == _AWAY)]
    assert len(hit) == 1
    assert int(hit["home_score"].iloc[0]) == 3 and int(hit["away_score"].iloc[0]) == 1
    before = store.read("results", cutoff="2026-06-11T20:00:00Z")
    assert before[(before["home_team"] == _HOME)
                  & (before["away_team"] == _AWAY)].empty


def test_manual_row_keys_same_match_id_as_schedule_row(tmp_path):
    """A manual row keys identically (sha1 date|home|away|city) to the upstream
    schedule row for the same fixture — an UPDATE of the same logical key, not a
    duplicate fixture."""
    store = BitemporalStore(tmp_path / "store")
    # The upstream schedule row, exactly as ingest_wc_group_fixtures writes it.
    sched_raw = pd.DataFrame([{
        "date": _DATE, "home_team": _HOME, "away_team": _AWAY,
        "home_score": np.nan, "away_score": np.nan, "tournament": "FIFA World Cup",
        "neutral": False, "city": "Mexico City", "country": "MX"}],
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "neutral", "city", "country"])
    sched = normalize_results(sched_raw)
    sched_id = sched["match_id"].iloc[0]
    store.write("results", sched, policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source=WC2026_SOURCE, source_version=WC2026_SOURCE)

    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_HOME},{_AWAY},3,1,\n")
    ingest_manual_rows(store, validate_manual_csv(csv), observed_at="2026-06-11T23:30:00Z")

    raw = pd.read_parquet(store._path("results"))
    assert raw["match_id"].nunique() == 1                       # one logical fixture
    manual_id = raw[raw["source"] == "wc2026_live"]["match_id"].iloc[0]
    assert manual_id == sched_id                                # same key as schedule


# --------------------------------------------------------------------------- #
# Reconciliation honesty: supersede-by-upstream tie-break                      #
# --------------------------------------------------------------------------- #
def test_upstream_supersedes_manual_at_read_when_observed_later(tmp_path):
    """Manual row ingested FIRST (observed_at = entry time); the upstream martj42
    row arrives LATER for the SAME match_id with a DIFFERENT (corrected) score and
    a LATER observed_at. The store's deterministic tie-break (observed_at DESC,
    then valid_as_of DESC, then _ingest_seq DESC) must surface the LATER-observed
    upstream value at a post-both read — the documented reconciliation direction."""
    store = BitemporalStore(tmp_path / "store")
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_HOME},{_AWAY},3,1,\n")
    rows = validate_manual_csv(csv)
    # 1) Manual first: observed at the operator's (evening) entry time.
    ingest_manual_rows(store, rows, observed_at="2026-06-11T23:30:00Z")
    manual_id = pd.read_parquet(store._path("results"))["match_id"].iloc[0]

    # 2) Upstream LATER: the next-morning martj42 pull carries a corrected 2-1,
    #    same match_id, observed_at strictly AFTER the manual one.
    upstream = pd.DataFrame([{
        "match_id": manual_id, "date": pd.Timestamp(_DATE),
        "valid_as_of": pd.Timestamp(_DATE), "observed_at": pd.Timestamp("2026-06-12T07:00:00"),
        "home_team": _HOME, "away_team": _AWAY, "home_score": 2, "away_score": 1,
        "tournament": "FIFA World Cup", "neutral": False, "city": "Mexico City",
        "country": "MX", "winner_override": np.nan}])
    store.write("results", upstream, policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source="martj42", source_version="test")

    # Read AFTER both observations: the later-observed UPSTREAM value (2-1) wins.
    out = store.read("results", cutoff="2026-06-13T00:00:00Z")
    row = out[out["match_id"] == manual_id]
    assert len(row) == 1
    assert int(row["home_score"].iloc[0]) == 2 and int(row["away_score"].iloc[0]) == 1, (
        "supersede-by-upstream failed: the later-observed martj42 row must win the "
        "deterministic tie-break (observed_at DESC) at a post-both read")


# --------------------------------------------------------------------------- #
# Phase-2A Task 6 (F11): tournament_path — validate manual results against a  #
# NON-WC edition; hosts/neutral + the tournament tag come from its format.    #
# --------------------------------------------------------------------------- #
# The hosts' opener from the committed real AC-2027 draw (group A, matchday 1).
_AC_YAML = "config/tournament_ac2027.yaml"
_AC_HOME, _AC_AWAY, _AC_DATE = "Saudi Arabia", "Palestine", "2027-01-07"


def test_ac_tournament_path_validates_ac_fixture(tmp_path):
    """An AC-2027 group result validates against the AC draw when tournament_path
    is given: venue/country resolved from ITS venues block, neutral=False via ITS
    format hosts (Saudi Arabia at a SA venue), and the row tagged with ITS
    competition name (so tier mapping sees a continental cup, not a World Cup)."""
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_AC_DATE},{_AC_HOME},{_AC_AWAY},2,0,\n")
    rows = validate_manual_csv(csv, tournament_path=_AC_YAML)
    assert len(rows) == 1
    r = rows[0]
    assert (r.home_team, r.away_team, r.home_score, r.away_score) == (
        _AC_HOME, _AC_AWAY, 2, 0)
    assert r.is_knockout is False
    assert r.city == "Riyadh (King Fahd)" and r.country == "SA"
    assert r.neutral is False                      # format hosts, not the WC literal
    assert r.tournament == "AFC Asian Cup"         # format competition_name


def test_ac_fixture_rejected_against_default_wc_draw(tmp_path):
    """The SAME CSV without tournament_path must fail against the default WC
    draw (Saudi Arabia v Palestine 2027-01-07 is not a 2026 fixture; Palestine
    is not a drawn-48 nation) — the default path is unchanged."""
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_AC_DATE},{_AC_HOME},{_AC_AWAY},2,0,\n")
    with pytest.raises(ManualResultsError):
        validate_manual_csv(csv)


def test_wc_default_rows_keep_fifa_world_cup_tag(tmp_path):
    """Byte-identical WC default: with NO tournament_path a validated row still
    carries tournament='FIFA World Cup' and ingests with that exact literal."""
    store = BitemporalStore(tmp_path / "store")
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_DATE},{_HOME},{_AWAY},3,1,\n")
    rows = validate_manual_csv(csv)
    assert rows[0].tournament == "FIFA World Cup"
    ingest_manual_rows(store, rows, observed_at="2026-06-11T23:00:00Z")
    out = store.read("results", cutoff="2026-06-13T00:00:00Z")
    assert (out["tournament"] == "FIFA World Cup").all()


def test_ac_rows_ingest_with_ac_tournament_tag(tmp_path):
    """An AC manual row reaches the store tagged 'AFC Asian Cup' (the format's
    competition_name), through the SAME leakage-safe ingest_live path."""
    store = BitemporalStore(tmp_path / "store")
    csv = _write_csv(tmp_path,
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{_AC_DATE},{_AC_HOME},{_AC_AWAY},2,0,\n")
    rows = validate_manual_csv(csv, tournament_path=_AC_YAML)
    ingest_manual_rows(store, rows, observed_at="2027-01-07T23:00:00Z")
    out = store.read("results", cutoff="2027-01-09T00:00:00Z")
    assert len(out) == 1
    assert (out["tournament"] == "AFC Asian Cup").all()
    assert bool(out["neutral"].iloc[0]) is False
